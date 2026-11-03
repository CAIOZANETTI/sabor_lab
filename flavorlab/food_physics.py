"""Estabilidade qualitativa de preparações (demanda 006).

Avalia sistemas com água, gordura, proteína, acidez, temperatura, emulsificantes,
agitação, concentração e sequência de adição **sem** calcular pH, atividade de
água, viscosidade ou cinética. Cada risco, fator protetor, sequência e
alternativa vem de uma regra auditável (``data/knowledge/stability_rules.csv``)
com fonte ou rótulo explícito de heurística.

Fatos de composição vêm de:

* claims de tabela oficial (TACO/USDA) via mapeamentos do catálogo (demanda 002),
  com a limitação de que o produto real pode diferir (marca ≠ categoria);
* fatos de entidade curados (``data/knowledge/entity_facts.csv``), ex.: kefir é leite
  fermentado acidificado;
* o que a pessoa informar (``EvidenceClaim``).

Desconhecido permanece desconhecido e aparece em ``missing_measurements``.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from .evidence import EvidenceClaim, new_claim
from .states import IngredientState

ROOT = Path(__file__).resolve().parents[1]
STABILITY_RULES_CSV = ROOT / "data" / "knowledge" / "stability_rules.csv"
ENTITY_FACTS_CSV = ROOT / "data" / "knowledge" / "entity_facts.csv"
NUTRITION = ROOT / "data" / "processed" / "nutrition"

HEAT_LEVELS = ("none", "low", "moderate", "high", "boil", "unknown")
RULE_KINDS = ("risk", "protective", "sequence", "alternative")
NUTRIENT_FACTS = {"has_protein": "proteina_g", "has_fat": "lipideos_g", "has_water": "agua_g",
                  "has_sugar": "acucares_g", "has_starch": "amido_g"}
DATASET_SOURCE = {"taco": "taco_4ed", "usda_sr_legacy": "usda_sr_legacy", "usda_foundation": "usda_foundation"}


# --------------------------------------------------------------------------- composição
@lru_cache(maxsize=1)
def _nutrition_tables():
    foods = pd.read_parquet(NUTRITION / "foods.parquet").set_index("food_id")
    fn = pd.read_parquet(NUTRITION / "food_nutrients.parquet")
    fn = fn[fn["nutrient_key"].isin(NUTRIENT_FACTS.values())]
    return foods, fn


def composition_claims(entity_id: str, catalog, *, subject_id: str | None = None) -> list[EvidenceClaim]:
    """Presença de proteína/gordura/água/açúcar/amido pela tabela oficial mapeada no catálogo.

    Usa o primeiro mapeamento curado ``exact``/``close``/``broad`` para TACO ou USDA da
    entidade ou de seus ancestrais. Valor ausente na tabela = fato desconhecido.
    """
    subject = subject_id or entity_id
    # entidade e ancestrais; se nenhum tiver tabela, variantes/formas do PRÓPRIO conceito (nunca de
    # subconceitos nem de categorias, que misturariam alimentos diferentes)
    chain = [entity_id] + catalog.ancestors(entity_id)
    concept = catalog.concepts.get(entity_id)
    if concept is not None and concept.entity_type != "category":
        chain += [d for d in catalog.descendants(entity_id) if catalog.concept_of(d) == entity_id]
    mapping = None
    for eid in chain:
        cands = [m for m in catalog.mappings(eid, include_auto=False)
                 if m.source in {"taco", "usda"} and m.mapping_type in {"exact", "close", "broad"}]
        if cands:
            order = {"exact": 0, "close": 1, "broad": 2}
            mapping = sorted(cands, key=lambda m: (order[m.mapping_type], m.source != "taco", m.source_id))[0]
            break
    if mapping is None:
        return []
    foods, fn = _nutrition_tables()
    food_id = f"{mapping.source}:{mapping.source_id}"
    if food_id not in foods.index:
        return []
    dataset = DATASET_SOURCE.get(foods.loc[food_id, "fonte"], "usda_sr_legacy")
    desc = foods.loc[food_id, "nome"]
    values = fn[fn["food_id"] == food_id].set_index("nutrient_key")["valor"].to_dict()
    out = []
    for fact, key in NUTRIENT_FACTS.items():
        v = values.get(key)
        if v is None or pd.isna(v):
            continue
        out.append(new_claim(
            claim_id=f"{subject}:{fact}:{food_id}", subject_id=subject, predicate=fact, value=bool(v > 0),
            unit=None, evidence_type="official_food_table", confidence="moderate", source_id=dataset,
            method=f"{key}={v:.2f} g/100 g em {food_id} '{desc}' (mapeamento {mapping.mapping_type} de {mapping.entity_id})",
            limitations="presença por 100 g na tabela; o produto real pode diferir (marca, lote, preparo)",
            context=food_id))
    return out


@dataclass(frozen=True)
class EntityFact:
    entity_id: str
    fact: str
    value: str
    statement_pt: str
    source_id: str
    evidence_type: str
    limitations: str


def load_entity_facts(path: Path | str = ENTITY_FACTS_CSV) -> list[EntityFact]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [EntityFact(**{k: (v or "").strip() for k, v in r.items()}) for r in csv.DictReader(fh)]


def entity_fact_claims(entity_id: str, catalog, facts: list[EntityFact], *, subject_id: str | None = None) -> list[EvidenceClaim]:
    subject = subject_id or entity_id
    chain = set([entity_id] + (catalog.ancestors(entity_id) if catalog is not None else []))
    out = []
    for f in facts:
        if f.entity_id in chain:
            value: Any = {"true": True, "false": False}.get(f.value, f.value)
            out.append(new_claim(
                claim_id=f"{subject}:{f.fact}:{f.entity_id}", subject_id=subject, predicate=f.fact, value=value,
                unit=None, evidence_type=f.evidence_type,
                confidence="moderate" if f.evidence_type == "documented_physical_rule" else "low",
                source_id=f.source_id, method=f"fato curado de {f.entity_id}: {f.statement_pt}",
                limitations=f.limitations or "fato de categoria; produto específico pode diferir"))
    return out


# --------------------------------------------------------------------------- preparação
@dataclass
class PreparationComponent:
    component_id: str
    entity_id: str | None
    display_name: str
    claims: list[EvidenceClaim] = field(default_factory=list)   # composição e fatos
    state: IngredientState | None = None
    specific_product: bool = False       # marca/produto específico sem composição verificada

    def fact(self, name: str) -> bool | None:
        vals = {bool(c.value) for c in self.claims if c.predicate == name and c.value is not None}
        if not vals:
            return None
        return True if True in vals else False


@dataclass
class Preparation:
    preparation_id: str
    components: list[PreparationComponent]
    heat: str = "unknown"                    # none | low | moderate | high | boil | unknown
    temperature_c: float | None = None
    ph: float | None = None
    agitation: str | None = None
    sequence: list[str] = field(default_factory=list)   # ordem de adição (component_ids)

    def __post_init__(self):
        if self.heat not in HEAT_LEVELS:
            raise ValueError(f"intensidade térmica inválida: {self.heat!r}")


# --------------------------------------------------------------------------- regras
@dataclass(frozen=True)
class StabilityRule:
    rule_id: str
    system: str
    kind: str
    triggers: str          # "fato=valor|fato=valor" (todos precisam ser verdadeiros)
    statement_pt: str
    recommendation_pt: str
    relative_risk: str     # lower | higher | n/a
    source_id: str
    evidence_type: str
    confidence: str
    limitations: str

    def trigger_items(self) -> list[tuple[str, str]]:
        return [tuple(t.split("=", 1)) for t in self.triggers.split("|") if "=" in t]


def load_stability_rules(path: Path | str = STABILITY_RULES_CSV) -> list[StabilityRule]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [StabilityRule(**{k: (v or "").strip() for k, v in r.items()}) for r in csv.DictReader(fh)]


def validate_stability_rules(rules: list[StabilityRule], sources) -> list[str]:
    errors = []
    for r in rules:
        if r.kind not in RULE_KINDS:
            errors.append(f"{r.rule_id}: kind inválido")
        if r.source_id not in sources:
            errors.append(f"{r.rule_id}: fonte não registrada {r.source_id}")
        if r.evidence_type not in {"documented_physical_rule", "culinary_heuristic"}:
            errors.append(f"{r.rule_id}: evidence_type inválido")
        if r.evidence_type == "culinary_heuristic" and (not r.limitations or r.confidence == "high"):
            errors.append(f"{r.rule_id}: heurística exige limitação e confiança não alta")
        if r.relative_risk not in {"lower", "higher", "n/a"}:
            errors.append(f"{r.rule_id}: relative_risk inválido")
        if not r.trigger_items():
            errors.append(f"{r.rule_id}: sem gatilhos")
    return errors


def preparation_facts(prep: Preparation) -> dict[str, Any]:
    """Fatos agregados da preparação (True/False/None) usados pelos gatilhos."""
    def any_fact(name: str) -> bool | None:
        vals = [c.fact(name) for c in prep.components]
        if any(v is True for v in vals):
            return True
        if vals and all(v is False for v in vals):
            return False
        return None

    facts: dict[str, Any] = {name: any_fact(name) for name in
                             ("has_fat", "has_protein", "has_water", "has_starch", "has_sugar", "is_acidified",
                              "is_fermented_dairy", "is_cheese", "is_blue_cheese", "has_emulsifying_salt",
                              "is_starch_thickener")}
    facts["acidified_dairy"] = (True if any(c.fact("is_acidified") and c.fact("is_fermented_dairy")
                                            for c in prep.components) else None)
    facts["heat_applied"] = None if prep.heat == "unknown" else prep.heat != "none"
    facts["heat"] = prep.heat
    facts["heat_high"] = None if prep.heat == "unknown" else prep.heat in {"high", "boil"}
    facts["ph_known"] = prep.ph is not None
    facts["temperature_known"] = prep.temperature_c is not None
    facts["specific_product"] = any(c.specific_product for c in prep.components) or None
    return facts


def _match(rule: StabilityRule, facts: Mapping[str, Any]) -> bool | None:
    result = True
    for k, v in rule.trigger_items():
        got = facts.get(k)
        if got is None:
            # gatilho desconhecido: a regra vale como possibilidade (não como certeza)
            result = None if result is not False else False
            continue
        expected = {"true": True, "false": False}.get(v, v)
        if got != expected:
            return False
    return result


# --------------------------------------------------------------------------- avaliação
@dataclass
class StabilityAssessment:
    preparation_id: str
    risks: list[dict]
    protective_factors: list[dict]
    sequence_options: list[dict]
    missing_measurements: list[str]
    evidence_claims: list[EvidenceClaim]
    confidence: str
    alternatives: list[dict] = field(default_factory=list)
    certainty_note: str = "avaliação qualitativa: não afirma estabilidade nem falha como certeza"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence_claims"] = [c.to_dict() for c in self.evidence_claims]
        return d

    def recommendations(self) -> list[str]:
        """Somente recomendações (sequências de menor risco e alternativas)."""
        out = [f'{s["statement"]} — {s["recommendation"]}' for s in self.sequence_options
               if s["relative_risk"] == "lower"]
        out += [a["recommendation"] for a in self.alternatives]
        return out


def assess_stability(prep: Preparation, rules: list[StabilityRule] | None = None) -> StabilityAssessment:
    rules = rules if rules is not None else load_stability_rules()
    facts = preparation_facts(prep)
    risks, protective, sequences, alternatives, claims = [], [], [], [], []
    for r in rules:
        m = _match(r, facts)
        if m is False or (m is None and r.kind == "protective"):
            # fator protetor só conta quando está presente de fato; ausente/desconhecido não protege
            continue
        certainty = "aplicável" if m is True else "possível (gatilho desconhecido)"
        entry = {"rule_id": r.rule_id, "system": r.system, "statement": r.statement_pt,
                 "recommendation": r.recommendation_pt, "relative_risk": r.relative_risk,
                 "applicability": certainty, "evidence_type": r.evidence_type, "source_id": r.source_id,
                 "confidence": r.confidence if m is True else "low", "limitations": r.limitations}
        {"risk": risks, "protective": protective, "sequence": sequences, "alternative": alternatives}[r.kind].append(entry)
        claims.append(new_claim(
            claim_id=f"{prep.preparation_id}:{r.rule_id}", subject_id=prep.preparation_id,
            predicate=f"stability_{r.kind}", value=r.statement_pt, unit=None, evidence_type=r.evidence_type,
            confidence=entry["confidence"],
            source_id=r.source_id, method="regra curada (stability_rules.csv)",
            limitations=r.limitations or "regra qualitativa", context=certainty))
    missing = []
    if prep.ph is None:
        missing.append("pH da preparação e dos componentes ácidos (desconhecido; não estimado)")
    if prep.temperature_c is None:
        missing.append("temperatura real do molho (só a intensidade do fogo é conhecida)" if prep.heat != "unknown"
                       else "temperatura e intensidade de aquecimento")
    for c in prep.components:
        if c.specific_product:
            missing.append(f"composição verificada de {c.display_name} (produto específico; usada categoria genérica)")
        if c.fact("has_fat") is None or c.fact("has_protein") is None:
            missing.append(f"teores de gordura/proteína de {c.display_name}")
    missing.append("tempo de aquecimento após cada adição")
    confidence = "qualitative" if (prep.ph is None or prep.temperature_c is None) else "low"
    sequences.sort(key=lambda s: s["relative_risk"] != "lower")   # estável: mantém a ordem das regras
    return StabilityAssessment(prep.preparation_id, risks, protective, sequences, sorted(set(missing), key=missing.index),
                               claims, confidence, alternatives)


def build_component(component_id: str, entity_id: str | None, display_name: str, catalog, *,
                    entity_facts: list[EntityFact] | None = None, extra_claims: Iterable[EvidenceClaim] = (),
                    state: IngredientState | None = None, specific_product: bool = False) -> PreparationComponent:
    """Componente com composição de tabela oficial + fatos curados + claims informados."""
    facts = entity_facts if entity_facts is not None else load_entity_facts()
    claims: list[EvidenceClaim] = []
    if entity_id and catalog is not None:
        claims += composition_claims(entity_id, catalog, subject_id=component_id)
        claims += entity_fact_claims(entity_id, catalog, facts, subject_id=component_id)
    claims += list(extra_claims)
    return PreparationComponent(component_id, entity_id, display_name, claims, state, specific_product)
