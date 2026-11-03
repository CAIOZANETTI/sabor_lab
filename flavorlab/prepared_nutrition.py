"""Nutrição após preparo: rendimento, retenção, água, gordura e porção servida (demanda 007).

Separa três origens de valor, que nunca se misturam na saída:

``measured`` (medido)
    composição de tabela oficial **do próprio alimento no estado servido** (mesma entidade
    e método compatível) multiplicada por massa pesada/informada.
``derived`` (derivado)
    cálculo com fator documentado: rendimento e variação de água/gordura da USDA,
    retenção da USDA, massa cozida obtida por rendimento de tabela, energia ajustada
    pela gordura perdida.
``estimated`` (estimado)
    aproximação declarada: componente transportado sem fator (convenção do método do
    fator de retenção), gordura sem dado de perda/absorção, registro preparado de
    outro método.

O que não tem dado nem convenção aplicável fica em ``unknown_nutrients`` — nunca zero.

Método de cálculo — "retention factor method" (Powers & Hoover 1989; USDA; descrito em
Reinivuo & Laitinen, EuroFIR 2007, §3.4), aplicado por ingrediente:

    nutriente_cozido_total = nutriente_cru_por_100g × massa_crua / 100 × retenção
    água_cozida_total      = água_crua_total + Δágua      (Δágua = %variação_umidade × massa_crua / 100)
    gordura_cozida_total   = gordura_crua_total + Δgordura (idem, com %variação de gordura)
    energia_cozida         = energia_crua + 9 × Δgordura    (fator geral de Atwater, kcal/g)
    massa_cozida           = massa_crua × rendimento         (rendimento = Wcozido/Wcru, base crua)
    concentração_servida   = total / massa_cozida × 100

Peso muda concentração, não massa de nutriente: sem fator, o total de um componente
não é aumentado nem reduzido pelo rendimento. Registro já preparado nunca recebe fator
de novo (proteção contra dupla contagem).
"""

from __future__ import annotations

import operator
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from .evidence import EvidenceClaim, new_claim
from .nutrition import NutritionDB, norm_text

ROOT = Path(__file__).resolve().parents[1]
FACTORS = ROOT / "data" / "cooking_factors"

CATEGORIES = ("measured", "derived", "estimated")
ATWATER_FAT_KCAL_G = 9.0       # fator geral de Atwater (mesmo de nutrition_report.ATWATER)
ATWATER_ALCOHOL_KCAL_G = 7.0
KCAL_TO_KJ = 4.184

WATER, FAT, ALCOHOL = "agua_g", "lipideos_g", "alcool_g"
ENERGY = ("energia_kcal", "energia_kj")
FAT_FRACTIONS = ("gordura_saturada_g", "gordura_monoinsaturada_g", "gordura_poliinsaturada_g",
                 "gordura_trans_g", "colesterol_mg")
# Componentes transportados sem fator, como no método do fator de retenção da USDA (que só
# publica fatores para vitaminas, minerais e álcool). Bognár (2002) documenta retenções < 1
# para alguns deles: por isso entram como ``estimated`` e com limitação explícita.
CARRIED = ("proteina_g", "carboidrato_g", "acucares_g", "fibra_g", "amido_g", "sacarose_g", "glicose_g",
           "frutose_g", "lactose_g", "cinzas_g")
# Minerais sem fator: transportados só quando o líquido de cocção não é descartado (convenção do
# EPIC, EuroFIR 2007 §3.7: "minerais assumidos 100% retidos"); com descarte, perdas por lixiviação
# são documentadas na própria tabela USDA, então ficam desconhecidos.
MINERALS = ("sodio_mg", "potassio_mg", "calcio_mg", "ferro_mg", "magnesio_mg", "fosforo_mg", "zinco_mg",
            "cobre_mg", "manganes_mg", "selenio_ug")
NO_LEACHING_FAMILIES = {"dry_heat", "dry_heat_fat", "microwave"}
CARRIED_LIMITATION = ("transportado sem fator (método do fator de retenção: a USDA não publica retenção "
                      "para macronutrientes); Bognár 2002 indica perdas possíveis em alguns métodos")

SOURCE_OF_RECORD = {"taco": "taco_4ed", "usda_sr_legacy": "usda_sr_legacy", "usda_foundation": "usda_foundation"}

# preparação do catálogo (demanda 002) / palavra do nome do registro -> método
CATALOG_PREPARATION = {"boiled": "boil", "poached": "boil", "fried": "fried_unspecified", "sauteed": "pan_fry",
                       "grilled": "grill_broil", "baked": "roast_bake", "roasted": "roast_bake",
                       "steamed": "steam", "cooked": "", "breaded;fried": "fried_unspecified"}
NAME_METHOD = [  # (regex sobre o nome normalizado, estado, método)
    (r"\b(cru|crua|crus|cruas|raw)\b", "raw", ""),
    (r"\b(grelhad[oa]s?|grilled|broiled)\b", "cooked", "grill_broil"),
    (r"\b(assad[oa]s?|roasted|baked)\b", "cooked", "roast_bake"),
    (r"\b(frit[oa]s?|fried)\b", "cooked", "fried_unspecified"),
    (r"\b(refogad[oa]s?|saute|sauteed|pan browned|pan broiled|pan fried)\b", "cooked", "pan_fry"),
    (r"\b(braised)\b", "cooked", "braise"),
    (r"\b(cozid[oa]s?|boiled|simmered|stewed|poached)\b", "cooked", "boil"),
    (r"\b(steamed|no vapor)\b", "cooked", "steam"),
    (r"\b(microwaved)\b", "cooked", "microwave"),
    (r"\b(cooked)\b", "cooked", ""),
]

MASS_BASES = ("raw", "cooked", "served")


class PreparedNutritionError(ValueError):
    """Entrada inconsistente para o cálculo pós-preparo."""


# --------------------------------------------------------------------------- contratos
@dataclass(frozen=True)
class YieldFactor:
    """Rendimento de massa: massa no ``final_state`` ÷ massa no ``initial_state``."""
    entity_id: str | None
    technique_id: str                 # method_key de data/cooking_factors/methods.csv
    initial_state: str
    final_state: str
    factor: float
    basis: str                        # "raw_mass": o fator multiplica a massa crua
    conditions: str
    evidence_claim_id: str
    food_id: str | None = None        # registro cru ao qual o rendimento se refere
    moisture_change: float | None = None   # Δágua em fração da massa crua (ex.: -0.2255)
    fat_change: float | None = None        # Δgordura em fração da massa crua
    origin: str = "table"             # table | observed (pesagem antes/depois)
    reference: str = ""               # yield_id da tabela

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass(frozen=True)
class RetentionFactor:
    """Retenção verdadeira (%TR/100) de um nutriente para um alimento/grupo e método."""
    entity_id_or_group: str
    nutrient_key: str
    technique_id: str
    factor: float
    conditions: str
    evidence_claim_id: str
    retn_code: str = ""
    match_level: str = ""             # specific | group
    confidence: str = "low"

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass(frozen=True)
class FatTransfer:
    """Gordura que passa do meio de cocção para o alimento (absorvida) ou sai dele (perdida).

    ``None`` significa desconhecido — nunca zero. Só a gordura absorvida entra na porção
    (EuroFIR 2007, §3.6/§4.4: em fritura, registra-se apenas a gordura absorvida).
    """
    source_entity_id: str | None      # gordura de cocção (ex.: óleo de soja)
    target_entity_id: str | None      # alimento que absorve/perde
    absorbed_g: float | None
    lost_g: float | None
    method: str                       # measured | declared | unknown
    evidence_claims: tuple[str, ...] = ()
    source_food: str | None = None    # nome/ID nutricional da gordura de cocção (para a composição)


@dataclass(frozen=True)
class PreparedItem:
    """Um ingrediente e o que se sabe sobre o seu preparo.

    ``mass_basis``: ``raw`` (massa antes do preparo), ``cooked`` (lote pronto) ou
    ``served`` (o que foi para o prato). Condições (``liquid``, ``water``, ``peeled``,
    ``duration_min``) só selecionam fatores quando a fonte as distingue; ausentes, o
    fator não é escolhido e o motivo aparece em ``warnings``.
    """
    name: str
    mass_g: float | None = None
    mass_basis: str = "raw"
    food_id: str | None = None
    method: str | None = None          # method_key, technique_id (003) ou cooking_method (005)
    raw_mass_g: float | None = None    # pesagem antes do preparo (se mass_basis não for raw)
    cooked_mass_g: float | None = None # pesagem do lote pronto
    served_mass_g: float | None = None # massa servida, se diferente do lote
    liquid: str | None = None          # discarded | consumed (água/caldo de cocção)
    water: str | None = None           # cover | little
    peeled: bool | None = None
    coated: bool = False               # empanamento é ingrediente declarado; não declarado = sem
    duration_min: float | None = None
    fat_transfer: FatTransfer | None = None
    instance_id: str | None = None
    entity_id: str | None = None       # entidade do catálogo, se já resolvida


@dataclass
class PreparedNutritionResult:
    name: str
    instance_id: str
    path: str                          # measured_prepared | derived_from_raw | as_recorded | not_computable
    composition_food_id: str | None
    method_key: str | None
    method_match: str                  # same | compatible | different | not_applicable
    initial_mass_g: float | None
    cooked_mass_g: float | None
    served_mass_g: float | None
    measured_values: dict[str, float] = field(default_factory=dict)
    derived_values: dict[str, float] = field(default_factory=dict)
    estimated_values: dict[str, float] = field(default_factory=dict)
    unknown_nutrients: list[str] = field(default_factory=list)
    nutrient_totals: dict[str, float] = field(default_factory=dict)
    yield_factor: YieldFactor | None = None
    yield_status: str = "not_applicable"   # observed | table | not_reconstructible | not_applicable | unknown
    retention_factors: list[RetentionFactor] = field(default_factory=list)
    fat_transfer: FatTransfer | None = None
    warnings: list[str] = field(default_factory=list)
    evidence_claims: list[EvidenceClaim] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)   # nutriente -> como foi obtido

    def category(self, key: str) -> str:
        for cat in CATEGORIES:
            if key in getattr(self, f"{cat}_values"):
                return cat
        return "unknown"

    def per100g(self) -> dict[str, float]:
        """Concentração no alimento servido (por 100 g)."""
        mass = self.served_mass_g
        if not mass:
            return {}
        return {k: v / mass * 100 for k, v in self.nutrient_totals.items()}


@dataclass
class PreparedRecipeResult:
    items: list[PreparedNutritionResult]
    totals: dict[str, float]
    total_category: dict[str, str]     # categoria mais fraca entre os itens que contribuem
    partial: dict[str, list[str]]      # nutriente -> itens em que é desconhecido
    served_mass_g: float | None
    portions: float
    per_portion: dict[str, float]
    shares: dict[str, dict[str, float]] = field(default_factory=dict)
    share_mass_g: dict[str, float] = field(default_factory=dict)
    leftover_mass_g: float | None = None
    warnings: list[str] = field(default_factory=list)

    def table(self) -> pd.DataFrame:
        rows = []
        for it in self.items:
            for k, v in it.nutrient_totals.items():
                rows.append({"item": it.name, "nutrient_key": k, "value": v, "category": it.category(k),
                             "how": it.notes.get(k, "")})
        return pd.DataFrame(rows, columns=["item", "nutrient_key", "value", "category", "how"])


# --------------------------------------------------------------------------- dados
@dataclass(frozen=True)
class Factors:
    methods: pd.DataFrame
    yields: pd.DataFrame
    retention: pd.DataFrame
    retention_map: pd.DataFrame

    @classmethod
    def load(cls, path: Path | str = FACTORS) -> "Factors":
        p = Path(path)
        read = lambda n, **kw: pd.read_csv(p / n, dtype=str, keep_default_na=False, **kw)  # noqa: E731
        y = read("cooking_yields.csv")
        for c in ("yield_pct", "n", "sd", "yield_min_pct", "yield_max_pct", "moisture_change_pct", "fat_change_pct"):
            y[c] = pd.to_numeric(y[c].replace("", None))
        r = read("retention_factors.csv")
        r["factor"] = pd.to_numeric(r["factor"].replace("", None))
        return cls(read("methods.csv"), y, r, read("retention_map.csv"))

    @property
    def method_alias(self) -> dict[str, str]:
        out = {}
        for row in self.methods.to_dict("records"):
            out[row["method_key"]] = row["method_key"]
            for col in ("technique_ids", "cooking_methods"):
                for alias in filter(None, row[col].split("|")):
                    out.setdefault(alias, row["method_key"])
        return out

    @property
    def family(self) -> dict[str, str]:
        return dict(zip(self.methods["method_key"], self.methods["family"]))


@lru_cache(maxsize=4)
def load_factors(path: str = str(FACTORS)) -> Factors:
    return Factors.load(path)


@lru_cache(maxsize=1)
def _default_catalog():
    from .catalog import Catalog
    return Catalog.load()


# --------------------------------------------------------------------------- resolução
def resolve_method(method: str | None, factors: Factors) -> str | None:
    if not method:
        return None
    key = factors.method_alias.get(str(method).strip())
    if key is None:
        raise PreparedNutritionError(
            f"método desconhecido {method!r}: use um method_key de data/cooking_factors/methods.csv, "
            "uma técnica (data/culinary/techniques.csv) ou um cooking_method (flavorlab.states)")
    return key


def _source_and_id(food_id: str) -> tuple[str, str]:
    prefix, _, sid = food_id.partition(":")
    return prefix, sid


def resolve_entity(food_id: str | None, catalog) -> str | None:
    if not food_id or catalog is None:
        return None
    src, sid = _source_and_id(food_id)
    try:
        res = catalog.resolve_source(src, sid)
    except Exception:  # noqa: BLE001 — fonte desconhecida pelo catálogo
        return None
    return res.entity_id or None


def record_state(ndb: NutritionDB, food_id: str, catalog=None) -> tuple[str, str, str]:
    """Estado e método do registro de composição: (estado, method_key, como foi decidido).

    Primeiro a forma do catálogo (demanda 002); depois palavras do nome do registro.
    Sem indício, ``unknown`` — o motor então não aplica fator nenhum.
    """
    entity = resolve_entity(food_id, catalog)
    if entity and catalog is not None and entity.startswith("sl:form:"):
        form = catalog.get(entity)
        if form.state in {"raw", "cooked"}:
            method = CATALOG_PREPARATION.get(form.preparation, "")
            return form.state, method, f"forma do catálogo {entity}"
    name = norm_text(ndb.foods.at[food_id, "nome"]) if food_id in ndb.foods.index else ""
    for pattern, state, method in NAME_METHOD:
        if re.search(pattern, name):
            return state, method, f"nome do registro ('{ndb.foods.at[food_id, 'nome']}')"
    return "unknown", "", "estado não identificado no catálogo nem no nome do registro"


def method_match(record_method: str, wanted: str | None, factors: Factors) -> str:
    if not wanted:
        return "not_applicable"
    if record_method == wanted:
        return "same"
    fam = factors.family
    rec_fam = fam.get(record_method, "")
    if not record_method or record_method.endswith("_unspecified"):
        return "compatible" if rec_fam and rec_fam == fam.get(wanted) else "different"
    return "different"


_OPS = {"<=": operator.le, ">=": operator.ge, "<": operator.lt, ">": operator.gt, "=": operator.eq}
_COND = re.compile(r"^(\w+)(<=|>=|<|>|=)(.+)$")


def _check(condition: str, ctx: Mapping[str, Any]) -> tuple[bool | None, list[str]]:
    """True/False, ou None quando falta variável (devolvida em ``missing``)."""
    missing, ok = [], True
    for part in filter(None, condition.split("&")):
        var, op, val = _COND.match(part.strip()).groups()
        have = ctx.get(var)
        if have is None:
            missing.append(var)
            continue
        if op == "=":
            ok &= str(have) == val
        else:
            ok &= _OPS[op](float(have), float(val))
    if missing:
        return (False if not ok else None), missing
    return ok, []


# --------------------------------------------------------------------------- fatores
def find_yield(food_id: str, method_key: str, factors: Factors) -> pd.Series | None:
    y = factors.yields
    hit = y[(y["raw_food_id"] == food_id) & (y["method_key"] == method_key)]
    if len(hit) == 0:
        return None
    return hit.sort_values(["release_year", "yield_id"], ascending=[False, True]).iloc[0]


def find_retention(entity_id: str | None, method_key: str, ctx: Mapping[str, Any], factors: Factors,
                   catalog) -> tuple[pd.Series | None, str]:
    """Regra de retenção mais específica (entidade, depois ancestrais) cujas condições valem."""
    if not entity_id or catalog is None:
        return None, "alimento sem entidade no catálogo: retenção não atribuída"
    rm = factors.retention_map
    chain = [entity_id] + list(catalog.ancestors(entity_id))
    for level in chain:
        rows = rm[(rm["match"] == level) & (rm["method_key"] == method_key)]
        if len(rows) == 0:
            continue
        missing: set[str] = set()
        for row in rows.to_dict("records"):
            ok, miss = _check(row["condition"], ctx)
            if ok:
                return pd.Series(row), ""
            missing.update(miss)
        if missing:
            return None, (f"retenção para {level} e {method_key} depende de {', '.join(sorted(missing))} "
                          "(não informado)")
        return None, f"nenhuma regra de retenção para {level} e {method_key} atende às condições informadas"
    return None, f"sem regra de retenção para {entity_id} com o método {method_key}"


# --------------------------------------------------------------------------- motor
class _Builder:
    """Acumula valores por categoria, notas e claims de um item."""

    def __init__(self, item: PreparedItem, instance_id: str):
        self.item = item
        self.iid = instance_id
        self.values: dict[str, dict[str, float]] = {c: {} for c in CATEGORIES}
        self.notes: dict[str, str] = {}
        self.unknown: list[str] = []
        self.claims: list[EvidenceClaim] = []
        self.warnings: list[str] = []
        self.base_food_id: str | None = None
        self.complement: str | None = None
        self.complemented: list[str] = []

    def put(self, key: str, value: float, cat: str, how: str) -> None:
        for c in CATEGORIES:
            self.values[c].pop(key, None)
        if key in self.unknown:
            self.unknown.remove(key)
        self.values[cat][key] = float(value)
        self.notes[key] = how

    def unknown_(self, key: str, why: str) -> None:
        for c in CATEGORIES:
            self.values[c].pop(key, None)
        if key not in self.unknown:
            self.unknown.append(key)
        self.notes[key] = why

    def claim(self, predicate: str, value, unit, evidence_type, confidence, *, source_id=None, method=None,
              limitations=None, **kw) -> EvidenceClaim:
        c = new_claim(claim_id=f"{self.iid}:{predicate}:{len(self.claims) + 1}", subject_id=self.iid,
                      predicate=predicate, value=value, unit=unit, evidence_type=evidence_type,
                      confidence=confidence, source_id=source_id, method=method, limitations=limitations, **kw)
        self.claims.append(c)
        return c


def _nutrient_unit(ndb: NutritionDB, key: str) -> str:
    if key in ndb.nutrients.index:
        return str(ndb.nutrients.at[key, "unidade"])
    return "unidade da fonte"


def _per100(ndb: NutritionDB, food_id: str, b: "_Builder | None" = None) -> pd.Series:
    """Composição por 100 g. Para o registro do próprio ingrediente, lacunas vêm do complemento
    do dicionário (mesma regra de ``NutritionDB.recipe``), anotadas em ``b.complemented``."""
    if b is not None and b.complement and food_id == b.base_food_id:
        per100, filled = ndb.per100g(food_id, b.complement)
        b.complemented = sorted(set(b.complemented) | set(filled))
        return per100
    m = ndb.matrix
    return m.loc[food_id] if food_id in m.index else pd.Series(np.nan, index=m.columns)


def _record_source(ndb: NutritionDB, food_id: str) -> str | None:
    return SOURCE_OF_RECORD.get(str(ndb.foods.at[food_id, "fonte"])) if food_id in ndb.foods.index else None


def _counterpart(food_id: str, method_key: str, ndb: NutritionDB, factors: Factors, catalog):
    """Registro preparado medido da mesma entidade: (food_id, origem) ou None.

    1. registro cozido ligado ao cru na tabela de rendimento USDA (mesmo estudo, mesmo método);
    2. forma irmã no catálogo (mesmo conceito/variante/parte, estado cozido) com método compatível.
    """
    y = find_yield(food_id, method_key, factors)
    if y is not None and y["cooked_food_id"] in ndb.matrix.index:
        return y["cooked_food_id"], f"registro cozido do estudo de rendimento {y['yield_id']}", "same"
    entity = resolve_entity(food_id, catalog)
    if not (entity and entity.startswith("sl:form:")):
        return None
    form = catalog.get(entity)
    parent = form.variant_id or form.part_id or form.concept_id
    best = None
    for sib in catalog.forms(parent):
        if sib.form_id == entity or sib.state != "cooked":
            continue
        match = method_match(CATALOG_PREPARATION.get(sib.preparation, ""), method_key, factors)
        if match not in {"same", "compatible"}:
            continue
        for m in catalog.mappings(sib.form_id):
            fid = f"{'usda' if m.source == 'usda' else m.source}:{m.source_id}"
            if m.mapping_type == "exact" and fid in ndb.matrix.index:
                cand = (fid, f"forma irmã do catálogo {sib.form_id}", match)
                if best is None or (match == "same" and best[2] != "same"):
                    best = cand
    return best


def prepared_nutrition(ndb: NutritionDB, item: PreparedItem, *, factors: Factors | None = None,
                       catalog=None) -> PreparedNutritionResult:
    """Nutrientes da porção servida de um ingrediente, separando medido/derivado/estimado."""
    factors = factors or load_factors()
    catalog = catalog if catalog is not None else _default_catalog()
    if item.mass_basis not in MASS_BASES:
        raise PreparedNutritionError(f"mass_basis deve ser um de {MASS_BASES}")
    iid = item.instance_id or f"prep:{norm_text(item.name).replace(' ', '_') or 'item'}"
    b = _Builder(item, iid)
    method_key = resolve_method(item.method, factors)

    food = ndb.lookup(item.name, item.food_id)
    if food.note and "informado" not in food.note:
        b.warnings.append(f"{item.name}: {food.note}")
    base = PreparedNutritionResult(item.name, iid, "not_computable", food.food_id, method_key, "not_applicable",
                                   None, None, None)
    if food.food_id is None:
        base.warnings = b.warnings + [f"{item.name}: sem registro de composição — fora do cálculo"]
        return base
    state, rec_method, state_how = record_state(ndb, food.food_id, catalog)
    entity = item.entity_id or resolve_entity(food.food_id, catalog)
    b.base_food_id = food.food_id
    if food.complement and food.complement in ndb.matrix.index:
        c_state = record_state(ndb, food.complement, catalog)[0]
        if c_state == state or "unknown" in (c_state, state):
            b.complement = food.complement
        else:
            b.warnings.append(f"{item.name}: complemento {food.complement} é de outro estado ({c_state}) — "
                              "não usado para preencher lacunas")

    # massas informadas
    raw_mass = item.mass_g if item.mass_basis == "raw" else item.raw_mass_g
    cooked_mass = item.cooked_mass_g if item.cooked_mass_g is not None else (
        item.mass_g if item.mass_basis == "cooked" else None)
    served_mass = item.served_mass_g if item.served_mass_g is not None else (
        item.mass_g if item.mass_basis == "served" else None)
    for label, v in (("massa crua", raw_mass), ("massa cozida", cooked_mass), ("massa servida", served_mass)):
        if v is not None:
            if not np.isfinite(v) or v <= 0:
                raise PreparedNutritionError(f"{item.name}: {label} deve ser positiva")
            b.claim(f"{label.replace(' ', '_')}_g", float(v), "g", "experimental_measurement", "moderate",
                    method="massa informada pelo usuário (precisão da balança não informada)")

    def finish(path, comp_id, match, yf=None, ystatus="not_applicable", rets=(), cooked=None):
        cooked = cooked if cooked is not None else cooked_mass
        served = served_mass if served_mass is not None else cooked
        totals = {}
        # escala lote -> servido
        if served is not None and cooked is not None and served > cooked * (1 + 1e-9):
            raise PreparedNutritionError(f"{item.name}: massa servida ({served:g} g) maior que o lote ({cooked:g} g)")
        frac = (served / cooked) if (served is not None and cooked) else 1.0
        if served is not None and cooked is None and path == "derived_from_raw":
            b.warnings.append(f"{item.name}: massa do lote pronto desconhecida — não é possível saber que fração "
                              "foi servida; valores referem-se ao lote inteiro")
            frac, served = 1.0, None
        for cat in CATEGORIES:
            b.values[cat] = {k: v * frac for k, v in b.values[cat].items()}
            totals.update(b.values[cat])
        res = PreparedNutritionResult(
            item.name, iid, path, comp_id, method_key, match, raw_mass, cooked, served,
            dict(sorted(b.values["measured"].items())), dict(sorted(b.values["derived"].items())),
            dict(sorted(b.values["estimated"].items())), sorted(b.unknown), dict(sorted(totals.items())),
            yf, ystatus, list(rets), item.fat_transfer, b.warnings, b.claims, b.notes)
        for k, v in res.nutrient_totals.items():
            cat = res.category(k)
            conf = {"measured": "high", "derived": "moderate", "estimated": "low"}[cat]
            b.claims.append(new_claim(
                claim_id=f"{iid}:total:{k}", subject_id=iid, predicate=f"served_total:{k}", value=round(v, 6),
                unit=_nutrient_unit(ndb, k), evidence_type="derived_calculation", confidence=conf,
                method=f"{cat}: {b.notes.get(k, '')}".strip(),
                limitations=(None if cat == "measured" else b.notes.get(k)), context=f"path={path}"))
        return res

    # ---------- registro já preparado: nunca recebe fator de novo
    if state == "cooked":
        if item.mass_basis == "raw":
            b.warnings.append(f"{item.name}: composição de alimento preparado ({ndb.foods.at[food.food_id, 'nome']}) "
                              "com massa crua — incompatível; informe a massa pronta/servida")
            base.warnings = b.warnings
            return base
        match = method_match(rec_method, method_key, factors) if method_key else "not_applicable"
        if method_key:
            b.warnings.append(f"{item.name}: registro já é de alimento preparado; nenhum fator de rendimento ou "
                              "retenção aplicado (sem dupla contagem)")
        cat = "measured" if match in {"same", "compatible", "not_applicable"} else "estimated"
        if cat == "estimated":
            b.warnings.append(
                f"{item.name}: registro preparado por outro método ({rec_method or 'não detalhado'}; {state_how}) "
                f"usado como aproximação para {method_key}")
        if cooked_mass is None and served_mass is None:
            b.warnings.append(f"{item.name}: sem massa pronta/servida — fora do cálculo")
            base.warnings = b.warnings
            return base
        # composição × lote (ou × servido, se o lote não foi pesado); finish escala lote -> servido
        cooked_for_scale = cooked_mass if cooked_mass is not None else served_mass
        _composition(b, ndb, food.food_id, cooked_for_scale, cat, "composição do registro preparado × massa", 1.0)
        conf = {"same": "high", "compatible": "moderate", "not_applicable": "high"}.get(match, "low")
        b.claim("composition_record", food.food_id, None, "official_food_table", conf,
                source_id=_record_source(ndb, food.food_id),
                limitations=None if conf == "high" else f"método do registro: {rec_method or 'não detalhado'}")
        ystatus = "not_applicable"
        yf = None
        if raw_mass is not None and cooked_mass is not None:
            yf = _observed_yield(b, entity, method_key, raw_mass, cooked_mass, food.food_id)
            ystatus = "observed"
        elif raw_mass is None:
            ystatus = "not_reconstructible"
            b.warnings.append(f"{item.name}: massa crua desconhecida — rendimento não reconstruído "
                              "(nenhum fator de tabela é usado para inventar o peso cru)")
        return finish("measured_prepared", food.food_id, match, yf, ystatus, cooked=cooked_for_scale)

    # ---------- sem preparo (consumido como registrado)
    if not method_key:
        mass = served_mass or cooked_mass or raw_mass
        if mass is None:
            b.warnings.append(f"{item.name}: sem massa — fora do cálculo")
            base.warnings = b.warnings
            return base
        mismatch = state == "raw" and item.mass_basis in {"cooked", "served"}
        cat = "estimated" if mismatch else "measured"
        if mismatch:
            b.warnings.append(f"{item.name}: massa de alimento pronto com composição de registro cru e sem método — "
                              "informe o método ou um registro preparado; valores são aproximação")
        _composition(b, ndb, food.food_id, mass, cat, "composição do registro × massa (sem preparo)", 1.0)
        b.claim("composition_record", food.food_id, None, "official_food_table",
                "low" if mismatch else "high", source_id=_record_source(ndb, food.food_id),
                limitations=("registro cru para alimento pronto" if mismatch else None))
        return finish("as_recorded", food.food_id, "not_applicable", cooked=mass)

    # ---------- registro cru (ou sem estado declarado) + método: medido preparado > derivado
    if state == "unknown":
        b.warnings.append(f"{item.name}: {state_how} — registro tratado como estado inicial, antes do preparo")
    raw_given = raw_mass is not None
    y = find_yield(food.food_id, method_key, factors)
    table_yield = None
    if y is not None and pd.notna(y["yield_pct"]):
        table_yield = _table_yield(b, entity, method_key, y, food.food_id)
    if raw_mass is None:
        if cooked_mass is not None and table_yield is not None:
            raw_mass = cooked_mass / table_yield.factor
            b.warnings.append(f"{item.name}: massa crua estimada pela tabela de rendimento "
                              f"({raw_mass:.0f} g = {cooked_mass:g} g ÷ {table_yield.factor:.2f})")
        else:
            b.warnings.append(f"{item.name}: massa crua desconhecida e sem rendimento aplicável — "
                              "não é possível derivar o alimento preparado a partir do registro cru")
            base.warnings = b.warnings
            return base

    cp = _counterpart(food.food_id, method_key, ndb, factors, catalog)
    yf, ystatus, cooked = None, "unknown", cooked_mass
    if raw_given and cooked_mass is not None:
        yf = _observed_yield(b, entity, method_key, raw_mass, cooked_mass, food.food_id)
        ystatus = "observed"
    elif table_yield is not None:
        yf, ystatus = table_yield, "table"
        if cooked is None:
            cooked = raw_mass * table_yield.factor

    if cp is not None and cooked is not None:
        cp_id, cp_how, cp_match = cp
        b.claim("composition_record", cp_id, None, "official_food_table",
                "high" if cp_match == "same" else "moderate", source_id=_record_source(ndb, cp_id),
                method=cp_how)
        cat = "measured" if ystatus == "observed" else "derived"
        how = ("composição medida do alimento preparado × massa pesada" if cat == "measured" else
               "composição medida do alimento preparado × massa cozida estimada pelo rendimento")
        _composition(b, ndb, cp_id, cooked, cat, how, 1.0)
        b.warnings.append(f"{item.name}: usado registro preparado {cp_id} ({cp_how}); fatores de retenção "
                          "não aplicados (sem dupla contagem)")
        _fat_transfer(b, ndb, item, method_key, cooked_already_includes=True)
        return finish("measured_prepared", cp_id, cp_match, yf, ystatus, cooked=cooked)

    if cp is not None:
        b.warnings.append(f"{item.name}: existe registro preparado {cp[0]} ({cp[1]}), mas sem massa cozida "
                          "pesada nem rendimento de tabela não dá para dimensioná-lo")
    rets = _derive_from_raw(b, ndb, item, food.food_id, entity, method_key, raw_mass, yf, factors, catalog)
    if cooked is None:
        b.warnings.append(f"{item.name}: rendimento desconhecido para {method_key} — massa pronta não estimada; "
                          "totais valem para o lote inteiro e a concentração por 100 g não é calculada")
    return finish("derived_from_raw", food.food_id, "not_applicable", yf, ystatus, rets, cooked=cooked)


def _composition(b: _Builder, ndb: NutritionDB, food_id: str, mass: float, cat: str, how: str, factor: float):
    for k, v in _per100(ndb, food_id, b).items():
        if pd.isna(v):
            b.unknown_(k, "não analisado no registro")
        else:
            src = f" (valor do complemento {b.complement})" if (food_id == b.base_food_id and k in b.complemented) else ""
            b.put(k, float(v) * mass / 100 * factor, cat, how + src)


def _observed_yield(b: _Builder, entity, method_key, raw_mass, cooked_mass, food_id) -> YieldFactor:
    c = b.claim("yield_factor", round(cooked_mass / raw_mass, 6), "ratio", "derived_calculation", "moderate",
                method=f"massa pronta pesada ÷ massa crua pesada ({cooked_mass:g} g ÷ {raw_mass:g} g)")
    return YieldFactor(entity, method_key or "", "raw", "cooked", cooked_mass / raw_mass, "raw_mass",
                       "pesagem antes e depois", c.claim_id, food_id, origin="observed")


def _table_yield(b: _Builder, entity, method_key, y: pd.Series, food_id) -> YieldFactor:
    sd = float(y["sd"]) / 100 if pd.notna(y["sd"]) else None
    lo = float(y["yield_min_pct"]) / 100 if pd.notna(y["yield_min_pct"]) else None
    hi = float(y["yield_max_pct"]) / 100 if pd.notna(y["yield_max_pct"]) else None
    c = b.claim("yield_factor", float(y["yield_pct"]) / 100, "ratio", "official_food_table", "high",
                source_id="usda_cooking_yields_r2", method=f"{y['yield_id']}: {y['description']} — {y['usda_method']}",
                limitations=(y["notes"] or None), uncertainty=sd, value_min=lo, value_max=hi,
                context=f"n={y['n']}; base: massa crua")
    mc = float(y["moisture_change_pct"]) / 100 if pd.notna(y["moisture_change_pct"]) else None
    fc = float(y["fat_change_pct"]) / 100 if pd.notna(y["fat_change_pct"]) else None
    return YieldFactor(entity, method_key, "raw", "cooked", float(y["yield_pct"]) / 100, "raw_mass",
                       y["usda_method"], c.claim_id, food_id, mc, fc, "table", y["yield_id"])


def _fat_transfer(b: _Builder, ndb: NutritionDB, item: PreparedItem, method_key: str,
                  cooked_already_includes: bool = False) -> float | None:
    """Soma a gordura absorvida conhecida; avisa quando ela é desconhecida. Devolve Δ de gordura (g) ou None."""
    ft = item.fat_transfer
    fat_medium = method_key in {"pan_fry", "deep_fry", "fried_unspecified"}
    if ft is None or ft.absorbed_g is None:
        if fat_medium and not cooked_already_includes:
            b.warnings.append(f"{item.name}: absorção de gordura na fritura desconhecida — a gordura do meio de "
                              "cocção não foi somada; gordura e energia podem estar subestimadas")
        return None
    if cooked_already_includes:
        b.warnings.append(f"{item.name}: absorção informada ignorada — o registro preparado já inclui a gordura")
        return None
    if not ft.source_food:
        b.warnings.append(f"{item.name}: gordura absorvida informada sem o alimento de origem (óleo/manteiga) — "
                          "não somada")
        return None
    fat_food = ndb.lookup(ft.source_food)
    if fat_food.food_id is None:
        b.warnings.append(f"{item.name}: gordura de cocção '{ft.source_food}' sem composição — não somada")
        return None
    cat = "measured" if ft.method == "measured" else "derived"
    for k, v in _per100(ndb, fat_food.food_id).items():
        if pd.isna(v):
            continue
        add = float(v) * ft.absorbed_g / 100
        current_cat = b_category(b, k)
        if current_cat == "unknown":
            continue  # não transforma um desconhecido em conhecido parcial
        worst = _weakest(current_cat, cat)
        b.put(k, b.values[current_cat][k] + add, worst,
              b.notes.get(k, "") + f" + {ft.absorbed_g:g} g de {ft.source_food} absorvidos ({ft.method})")
    b.claim("fat_absorbed_g", float(ft.absorbed_g), "g",
            "experimental_measurement" if ft.method == "measured" else "human_observation",
            "moderate", method=f"gordura absorvida ({ft.method})")
    return ft.absorbed_g


def b_category(b: _Builder, key: str) -> str:
    for c in CATEGORIES:
        if key in b.values[c]:
            return c
    return "unknown"


def _weakest(*cats: str) -> str:
    order = {"measured": 0, "derived": 1, "estimated": 2, "unknown": 3}
    return max(cats, key=order.__getitem__)


def _derive_from_raw(b: _Builder, ndb: NutritionDB, item: PreparedItem, food_id: str, entity, method_key: str,
                     raw_mass: float, yf: YieldFactor | None, factors: Factors, catalog) -> list[RetentionFactor]:
    per100 = _per100(ndb, food_id, b)
    raw = {k: float(v) * raw_mass / 100 for k, v in per100.items() if pd.notna(v)}
    for k in per100.index[per100.isna()]:
        b.unknown_(k, "não analisado no registro cru")
    b.claim("composition_record", food_id, None, "official_food_table", "high", source_id=_record_source(ndb, food_id),
            method="registro cru (estado inicial)")

    # condições para escolher retenção
    ctx = {"liquid": item.liquid, "water": item.water, "duration_min": item.duration_min,
           "peeled": None if item.peeled is None else ("yes" if item.peeled else "no"),
           "coated": "yes" if item.coated else "no",
           "raw_fat_g": float(per100[FAT]) if FAT in per100 and pd.notna(per100[FAT]) else None}
    rule, why = find_retention(entity, method_key, ctx, factors, catalog)
    rets: list[RetentionFactor] = []
    rmap: dict[str, RetentionFactor] = {}
    if rule is None:
        b.warnings.append(f"{item.name}: {why}")
    else:
        conf = "moderate" if rule["match_level"] == "specific" else "low"
        lim = (rule["notes"] or ("fator de grupo da USDA aplicado a alimento específico: aproximação de "
                                 "baixa confiança" if rule["match_level"] == "group" else ""))
        rf = factors.retention[(factors.retention["retn_code"] == rule["retn_code"])
                               & (factors.retention["nutrient_key"] != "")]
        desc = rf["description"].iloc[0] if len(rf) else ""
        for r in rf.to_dict("records"):
            if pd.isna(r["factor"]):
                continue
            c = b.claim(f"retention:{r['nutrient_key']}", float(r["factor"]), "fraction", "official_food_table", conf,
                        source_id="usda_retention_r6", method=f"código {rule['retn_code']} {desc}",
                        limitations=lim or None, context=rule["condition"] or None)
            rfac = RetentionFactor(rule["match"], r["nutrient_key"], method_key, float(r["factor"]),
                                   rule["condition"], c.claim_id, rule["retn_code"], rule["match_level"], conf)
            rets.append(rfac)
            rmap[r["nutrient_key"]] = rfac
        if rule["match_level"] == "group":
            b.warnings.append(f"{item.name}: retenção do código USDA {rule['retn_code']} ({desc}) é fator de grupo — "
                              "baixa confiança para este alimento")

    d_water = yf.moisture_change * raw_mass if (yf and yf.moisture_change is not None) else None
    d_fat = yf.fat_change * raw_mass if (yf and yf.fat_change is not None) else None
    water_only = yf is not None and yf.origin == "observed" and (
        method_key == "reduce" or (method_key in {"boil", "steam", "pressure"} and yf.factor > 1))
    if water_only:
        # método britânico (EuroFIR 2007, §3.2): variação de peso atribuída só à água. Vale para a
        # redução (evaporação) e para o ganho de massa em cocção úmida (só entra água).
        d_water, d_fat = (yf.factor - 1) * raw_mass, 0.0
        b.claim("moisture_change_g", round(d_water, 6), "g", "derived_calculation", "moderate",
                method=("redução: perda de massa = água evaporada" if method_key == "reduce" else
                        "cocção úmida com ganho de massa: ganho = água absorvida") + " (massa pronta − massa crua)",
                limitations="assume que só a água variou; álcool, voláteis e sal da água não separados")
    elif yf and yf.origin == "observed" and d_water is None:
        b.warnings.append(f"{item.name}: rendimento pesado sem separação entre água e gordura perdidas")
    if item.fat_transfer is not None and item.fat_transfer.lost_g is not None:
        d_fat = -abs(float(item.fat_transfer.lost_g))
        b.claim("fat_lost_g", abs(d_fat), "g", "experimental_measurement", "moderate", method="gordura perdida informada")

    for k, v in raw.items():
        if k == WATER:
            if d_water is not None:
                b.put(k, max(v + d_water, 0.0), "derived", "água crua + variação de umidade")
            else:
                b.unknown_(k, "variação de água desconhecida")
        elif k == FAT:
            if d_fat is not None:
                b.put(k, max(v + d_fat, 0.0), "derived", "gordura crua + variação de gordura (tabela/medida)")
            else:
                b.put(k, v, "estimated", "gordura crua transportada; perda/ganho não informado")
        elif k in FAT_FRACTIONS:
            if d_fat:
                b.unknown_(k, "perfil da gordura perdida/ganha não informado")
            else:
                b.put(k, v, "estimated", "transportado sem fator (variação de gordura nula ou desconhecida)")
        elif k in ENERGY:
            continue
        elif k in rmap:
            b.put(k, v * rmap[k].factor, "derived",
                  f"cru × retenção {rmap[k].factor:.2f} (USDA {rmap[k].retn_code}, {rmap[k].match_level})")
        elif k == ALCOHOL and v == 0:
            b.put(k, 0.0, "derived", "ausente no cru; preparo não cria álcool")
        elif k in CARRIED:
            b.put(k, v, "estimated", CARRIED_LIMITATION)
        elif k in MINERALS and (factors.family.get(method_key) in NO_LEACHING_FAMILIES or method_key == "reduce"
                                or item.liquid == "consumed"):
            b.put(k, v, "estimated", "mineral transportado sem fator (líquido não descartado; convenção EPIC, "
                                     "EuroFIR 2007 §3.7)")
        elif v == 0:
            b.put(k, 0.0, "derived", "zero no cru; retenção ≤ 1 não cria nutriente")
        else:
            b.unknown_(k, "sem fator de retenção aplicável")

    # energia: Atwater geral sobre o que mudou de gordura (e álcool)
    for k in ENERGY:
        if k not in raw:
            continue
        delta_kcal = 0.0
        ok = d_fat is not None
        if ok:
            delta_kcal += ATWATER_FAT_KCAL_G * d_fat
        alc0 = raw.get(ALCOHOL, 0.0)
        alc1 = b.values["derived"].get(ALCOHOL)
        if alc0 and alc1 is not None:
            delta_kcal += ATWATER_ALCOHOL_KCAL_G * (alc1 - alc0)
        elif alc0:
            ok = False
        delta = delta_kcal * (KCAL_TO_KJ if k == "energia_kj" else 1.0)
        if ok:
            b.put(k, max(raw[k] + delta, 0.0), "derived", "energia crua + Atwater geral × Δgordura (9 kcal/g)")
        else:
            b.put(k, raw[k], "estimated", "energia crua transportada (variação de gordura desconhecida)")

    _fat_transfer(b, ndb, item, method_key)   # soma a composição da gordura absorvida, energia inclusive
    return rets


# --------------------------------------------------------------------------- receita e porções
def prepared_recipe(ndb: NutritionDB, items: Iterable[PreparedItem | Mapping], *, portions: float = 1.0,
                    shares: Mapping[str, float] | None = None, factors: Factors | None = None,
                    catalog=None) -> PreparedRecipeResult:
    """Soma os itens servidos; ``shares`` reparte o prato por pessoa em gramas servidos."""
    factors = factors or load_factors()
    catalog = catalog if catalog is not None else _default_catalog()
    results = [prepared_nutrition(ndb, it if isinstance(it, PreparedItem) else item_from_row(it),
                                  factors=factors, catalog=catalog) for it in items]
    totals: dict[str, float] = {}
    cat_of: dict[str, str] = {}
    partial: dict[str, list[str]] = {}
    keys = sorted({k for r in results for k in list(r.nutrient_totals) + list(r.unknown_nutrients)})
    computed = [r for r in results if r.path != "not_computable"]
    for k in keys:
        vals = [(r, r.nutrient_totals[k]) for r in computed if k in r.nutrient_totals]
        unknown_in = [r.name for r in computed if k not in r.nutrient_totals]
        if vals:
            totals[k] = float(sum(v for _, v in vals))
            cat_of[k] = _weakest(*(r.category(k) for r, _ in vals))
        if unknown_in and vals:
            partial[k] = unknown_in
    warnings = [w for r in results for w in r.warnings]
    if any(r.path == "not_computable" for r in results):
        warnings.append("itens fora do cálculo: " + ", ".join(r.name for r in results if r.path == "not_computable"))
    masses = [r.served_mass_g for r in computed]
    served = float(sum(masses)) if masses and all(m is not None for m in masses) else None
    portions = portions if portions and portions > 0 else 1.0
    per_portion = {k: v / portions for k, v in totals.items()}

    share_vals, share_mass, leftover = {}, {}, None
    if shares:
        if served is None:
            warnings.append("massa servida do prato desconhecida — divisão por pessoa não calculada")
        else:
            given = float(sum(shares.values()))
            if given > served * (1 + 1e-9):
                raise PreparedNutritionError(f"porções ({given:g} g) somam mais que o prato servido ({served:g} g)")
            for person, grams in shares.items():
                share_mass[person] = float(grams)
                share_vals[person] = {k: v * grams / served for k, v in totals.items()}
            leftover = served - given
    return PreparedRecipeResult(results, totals, cat_of, partial, served, portions, per_portion,
                                share_vals, share_mass, leftover, warnings)


ROW_KEYS = {"nome": "name", "name": "name", "massa_g": "mass_g", "gramas": "mass_g", "estado": "mass_basis",
            "metodo": "method", "método": "method", "alimento": "food_id", "massa_crua_g": "raw_mass_g",
            "massa_cozida_g": "cooked_mass_g", "massa_servida_g": "served_mass_g", "liquido": "liquid",
            "agua": "water", "descascado": "peeled", "empanado": "coated", "duracao_min": "duration_min"}
BASIS_PT = {"cru": "raw", "crua": "raw", "raw": "raw", "cozido": "cooked", "cozida": "cooked", "pronto": "cooked",
            "cooked": "cooked", "servido": "served", "served": "served"}
BOOL_PT = {"sim": True, "s": True, "yes": True, "true": True, "1": True,
           "nao": False, "não": False, "n": False, "no": False, "false": False, "0": False}


def item_from_row(row: Mapping) -> PreparedItem:
    """Linha de receita (chaves em português ou inglês) -> ``PreparedItem``."""
    kw: dict[str, Any] = {}
    for k, v in row.items():
        key = ROW_KEYS.get(str(k).strip().lower(), str(k) if str(k) in PreparedItem.__dataclass_fields__ else None)
        if key is None or v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() == "":
            continue
        if key in {"mass_g", "raw_mass_g", "cooked_mass_g", "served_mass_g", "duration_min"}:
            v = float(str(v).replace(",", "."))
        elif key == "mass_basis":
            v = BASIS_PT.get(norm_text(v), v)
        elif key in {"peeled", "coated"}:
            v = BOOL_PT.get(norm_text(v), v) if not isinstance(v, bool) else v
        kw[key] = v
    if "name" not in kw:
        raise PreparedNutritionError("linha sem nome")
    return PreparedItem(**kw)


__all__ = [
    "CATEGORIES", "FatTransfer", "Factors", "PreparedItem", "PreparedNutritionError", "PreparedNutritionResult",
    "PreparedRecipeResult", "RetentionFactor", "YieldFactor", "find_retention", "find_yield", "item_from_row",
    "load_factors", "method_match", "prepared_nutrition", "prepared_recipe", "record_state", "resolve_method",
]
