"""Cálculo nutricional de receitas (TACO + USDA), tudo em unidades métricas.

Fluxo de uma linha de receita ("2 colheres de sopa de azeite"):
  1. nome em português -> dicionário (data/dicionario_ingredientes.csv)
     -> alimento principal (TACO de preferência) + complemento USDA
  2. quantidade + unidade -> gramas (massa direta; volume x densidade; contagem
     pelas medidas caseiras do IBGE ou porções do USDA)
  3. gramas / 100 x composição por 100 g -> contribuição de cada nutriente
Lacunas do alimento principal (ex.: açúcares, que a TACO não mede) são
preenchidas pelo complemento USDA, e o relatório informa quais.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from fractions import Fraction
from functools import cached_property
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .units import COUNT_UNITS, classify, fmt_num, norm_unit

ROOT = Path(__file__).resolve().parents[1]
NUTRITION = ROOT / "data" / "processed" / "nutrition"
DICTIONARY = ROOT / "data" / "dicionario_ingredientes.csv"

# colunas opcionais que ativam o cálculo pós-preparo (flavorlab.prepared_nutrition)
PREP_KEYS = ("estado", "metodo", "método", "massa_crua_g", "massa_cozida_g", "massa_servida_g")

# nutrientes mostrados por padrão (ordem do relatório)
MAIN = ["energia_kcal", "proteina_g", "carboidrato_g", "acucares_g", "fibra_g", "lipideos_g",
        "gordura_saturada_g", "gordura_trans_g", "colesterol_mg", "sodio_mg"]

# Valores diários de referência para adultos — ANVISA, IN nº 75/2020, Anexo II.
# Açúcares: a referência é para açúcares *adicionados* (50 g); aqui temos açúcares
# *totais*, então não calculamos %VD para eles.
VDR = {"energia_kcal": 2000.0, "carboidrato_g": 300.0, "proteina_g": 50.0, "lipideos_g": 65.0,
       "gordura_saturada_g": 20.0, "fibra_g": 25.0, "sodio_mg": 2000.0}

DEFAULT_DENSITY = 1.0  # g/ml (água), usada só quando não há dado melhor — com aviso


def strip_accents(text: str) -> str:
    return unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()


def norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", strip_accents(text).lower())).strip()


def parse_quantity(value) -> float:
    """'1/2' -> 0.5 ; '1 1/2' -> 1.5 ; '0,25' -> 0.25 ; 3 -> 3.0"""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return np.nan
    try:
        return float(sum(Fraction(part) for part in text.split()))
    except (ValueError, ZeroDivisionError):
        return np.nan


@dataclass
class Food:
    """Ingrediente resolvido para fins nutricionais."""
    query: str
    food_id: str | None
    complement: str | None = None
    pof: str | None = None
    note: str = ""


@dataclass
class Line:
    nome: str
    food: Food
    quantidade: float
    unidade: str
    gramas: float
    metodo: str


@dataclass
class NutritionResult:
    lines: list[Line]
    table: pd.DataFrame          # uma linha por ingrediente, colunas = nutrientes (contribuição)
    total: pd.Series
    per_portion: pd.Series
    portions: float
    vd: pd.Series                # %VD por porção
    complemented: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    # demanda 007: só preenchido quando a receita informa estado/método de preparo
    prepared: Any = None


class NutritionDB:
    def __init__(self, path: Path = NUTRITION, dictionary: Path | None = DICTIONARY):
        self.path = Path(path)
        if not (self.path / "foods.parquet").exists():
            raise FileNotFoundError(
                f"banco nutricional não encontrado em {self.path}. "
                "Rode: python scripts/download_nutrition.py && python scripts/build_nutrition.py")
        read = lambda n: pd.read_parquet(self.path / f"{n}.parquet")  # noqa: E731
        self.foods = read("foods").set_index("food_id")
        self.nutrients = read("nutrients").set_index("nutrient_key")
        self.values = read("food_nutrients")
        self.portions = read("portions")
        self.household = read("household")
        self.dictionary: dict[str, dict] = {}
        if dictionary and Path(dictionary).exists():
            d = pd.read_csv(dictionary, dtype=str).fillna("")
            self.dictionary = {norm_text(r["nome"]): r for r in d.to_dict("records")}

    # ----------------------------------------------------------- consultas
    @cached_property
    def matrix(self) -> pd.DataFrame:
        """alimento x nutriente (por 100 g). NaN = não analisado."""
        return self.values.pivot(index="food_id", columns="nutrient_key", values="valor")

    @cached_property
    def _search_index(self) -> pd.Series:
        return self.foods["nome"].map(norm_text)

    def search(self, text: str, limit: int = 20) -> pd.DataFrame:
        """Busca por palavras (sem acento), TACO primeiro, descrições curtas antes."""
        words = norm_text(text).split()
        mask = np.ones(len(self.foods), dtype=bool)
        for w in words:
            mask &= self._search_index.str.contains(rf"\b{re.escape(w)}", regex=True).to_numpy()
        df = self.foods[mask].reset_index()
        df = df.assign(_taco=df["fonte"].ne("taco"), _len=df["nome"].str.len(),
                       _cru=~df["nome"].str.contains(r"\bcru|\braw\b", regex=True, na=False))
        df = df.sort_values(["_taco", "_cru", "_len"])
        return df.head(limit)[["food_id", "nome", "fonte", "categoria", "n_nutrientes"]]

    def per100g(self, food_id: str, complement: str | None = None) -> tuple[pd.Series, list[str]]:
        """Composição por 100 g; lacunas preenchidas pelo complemento (e quais foram)."""
        m = self.matrix
        base = m.loc[food_id] if food_id in m.index else pd.Series(np.nan, index=m.columns)
        filled: list[str] = []
        if complement and complement in m.index:
            comp = m.loc[complement]
            gaps = base.isna() & comp.notna()
            filled = [k for k in gaps[gaps].index if k in self.nutrients.index and not k.startswith("usda_")]
            base = base.where(~gaps, comp)
        return base, filled

    def density(self, food: Food) -> float | None:
        for fid in (food.food_id, food.complement):
            if fid and fid in self.foods.index:
                d = self.foods.at[fid, "densidade_g_ml"]
                if pd.notna(d) and d > 0:
                    return float(d)
        return None

    # ------------------------------------------------------------ resolução
    def lookup(self, name: str, override: str | None = None) -> Food:
        """Nome em português -> alimento (dicionário, id direto ou busca automática)."""
        if override and override in self.foods.index:
            return Food(name, override, note="alimento informado na receita")
        key = norm_text(name)
        if key in self.dictionary:
            r = self.dictionary[key]
            return Food(name, r["nutricao"] or None, r["complemento"] or None, r["medidas_pof"] or None)
        if name in self.foods.index:
            return Food(name, name)
        hits = self.search(name, 1)
        if len(hits):
            fid = hits.iloc[0]["food_id"]
            return Food(name, fid, note=f"correspondência automática: '{self.foods.at[fid, 'nome']}' — confira")
        return Food(name, None, note="alimento não encontrado")

    # ----------------------------------------------------------- unidades
    def to_grams(self, qty: float, unit: str, food: Food) -> tuple[float | None, str]:
        """Converte quantidade+unidade para gramas. Retorna (gramas, como foi feito)."""
        if np.isnan(qty):
            return None, "quantidade inválida"
        kind, factor = classify(unit or "g")
        if kind == "massa":
            return qty * factor, "massa"
        if kind == "volume":
            ml = qty * factor
            dens = self.density(food)
            if dens:
                return ml * dens, f"{fmt_num(ml)} ml × densidade {fmt_num(dens, 2)} g/ml"
            pof_g = self._pof(food, [norm_unit(unit).upper()])
            if pof_g:
                return qty * pof_g, f"medida caseira IBGE ({fmt_num(pof_g)} g)"
            return ml * DEFAULT_DENSITY, f"{fmt_num(ml)} ml × densidade assumida {fmt_num(DEFAULT_DENSITY)} g/ml (sem dado)"
        if kind == "contagem":
            pof_names, usda_words = COUNT_UNITS[factor]
            pof_g = self._pof(food, pof_names)
            if pof_g:
                return qty * pof_g, f"medida caseira IBGE: {factor} = {fmt_num(pof_g)} g"
            usda_g = self._usda_portion(food, usda_words)
            if usda_g:
                return qty * usda_g, f"porção USDA: {factor} = {fmt_num(usda_g)} g"
            return None, f"sem peso conhecido para '{unit}' — preencha a coluna 'gramas'"
        return None, f"unidade desconhecida: '{unit}' — use g, ml, xícara, colher... ou preencha 'gramas'"

    def _pof(self, food: Food, measures: list[str]) -> float | None:
        if not food.pof:
            return None
        h = self.household[self.household["alimento"] == food.pof]
        for m in measures:
            hit = h.loc[h["medida"] == m, "gramas"]
            if len(hit):
                return float(hit.median())
        return None

    def _usda_portion(self, food: Food, words: list[str]) -> float | None:
        for fid in (food.complement, food.food_id):
            if not fid or not fid.startswith("usda:"):
                continue
            p = self.portions[self.portions["food_id"] == fid]
            for w in words:
                hit = p[p["medida_original"].str.contains(rf"\b{w}\b", regex=True, na=False)]
                if len(hit):
                    return float((hit["gramas"] / hit["quantidade"]).iloc[0])
        return None

    # ------------------------------------------------------------- receita
    def recipe(self, rows: list[dict], portions: float = 1.0) -> NutritionResult:
        """rows: [{'nome', 'quantidade', 'unidade', 'gramas'?, 'alimento'?}, ...]

        Colunas opcionais de preparo (``estado``, ``metodo``, ``massa_cozida_g``...) ativam
        ``NutritionResult.prepared`` (demanda 007); sem elas o resultado é o de sempre.
        """
        lines, contrib, warnings, complemented, prep_rows = [], [], [], {}, []
        for r in rows:
            nome = str(r.get("nome", "")).strip()
            food = self.lookup(nome, r.get("alimento") or None)
            if food.note and "informado" not in food.note:
                warnings.append(f"{nome}: {food.note}")
            qty, unit = parse_quantity(r.get("quantidade")), str(r.get("unidade") or "g")
            g_override = parse_quantity(r.get("gramas"))
            if not np.isnan(g_override):
                grams, how = g_override, "informado em gramas"
            else:
                grams, how = self.to_grams(qty, unit, food)
            if grams is None or food.food_id is None:
                warnings.append(f"{nome}: {how if grams is None else food.note} — fora do cálculo")
                continue
            if "assumida" in how:
                warnings.append(f"{nome}: {how}")
            per100, filled = self.per100g(food.food_id, food.complement)
            if filled:
                complemented[nome] = [self.nutrients.at[k, "nome"] for k in filled]
            lines.append(Line(nome, food, qty, unit, grams, how))
            contrib.append((per100 * grams / 100.0).rename(nome))
            prep_rows.append({**{k: r.get(k) for k in PREP_KEYS if k in r}, "nome": nome, "massa_g": grams,
                              "alimento": food.food_id if r.get("alimento") else None,
                              **{k: r.get(k) for k in ("liquido", "agua", "descascado", "empanado", "duracao_min")
                                 if k in r}})

        table = pd.DataFrame(contrib) if contrib else pd.DataFrame(columns=self.matrix.columns)
        total = table.sum(min_count=1)
        portions = portions if portions and portions > 0 else 1.0
        per_portion = total / portions
        vd = pd.Series({k: per_portion.get(k, np.nan) / v * 100 for k, v in VDR.items()})
        result = NutritionResult(lines, table, total, per_portion, portions, vd, complemented, warnings)
        if any(str(r.get(k) or "").strip() and str(r.get(k)) != "nan" for r in rows for k in PREP_KEYS):
            result.prepared = self.prepared(prep_rows, portions=portions)
        return result

    def prepared(self, items, portions: float = 1.0, shares: dict[str, float] | None = None, **kw):
        """Nutrição após preparo (rendimento, retenção, porção servida). Ver flavorlab.prepared_nutrition."""
        from .prepared_nutrition import prepared_recipe
        return prepared_recipe(self, items, portions=portions, shares=shares, **kw)

    def label(self, key: str) -> str:
        if key in self.nutrients.index:
            n = self.nutrients.loc[key]
            return f"{n['nome']} ({n['unidade']})"
        return key
