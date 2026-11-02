"""Monta o banco nutricional unificado (TACO + USDA) em data/processed/nutrition/.

Tudo por 100 g de parte comestível e em unidades métricas (g, mg, µg, kcal, kJ).
Nutrientes em UI (unidades internacionais) do USDA são descartados: o USDA já
fornece os equivalentes métricos (vitamina A em µg RAE, vitamina D em µg).

Saídas (Parquet):
    foods.parquet           um alimento por linha (taco:<n>, usda:<fdc_id>)
    nutrients.parquet       catálogo de nutrientes (chave, nome em português, unidade)
    food_nutrients.parquet  alimento x nutriente -> valor por 100 g (formato longo)
    portions.parquet        porções do USDA convertidas para g e ml (com nome em português)
    household.parquet       medidas caseiras da POF/IBGE em gramas

Uso:
    python scripts/download_nutrition.py   # uma vez
    python scripts/build_nutrition.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flavorlab.units import US_NAMES_PT, VOLUME_ML, MASS_G, fmt_num, metricize_text, norm_unit  # noqa: E402

RAW_USDA = ROOT / "data" / "raw" / "usda"
RAW_TACO = ROOT / "data" / "raw" / "taco"
OUT = ROOT / "data" / "processed" / "nutrition"

TRACE = 1e-5  # na TACO normalizada, 1e-05 = "Tr" (traço)

# chave, nome em português, unidade, grupo, ids USDA (prioridade, nome esperado), coluna TACO
CORE = [
    ("energia_kcal", "Energia", "kcal", "energia", [(1008, "Energy"), (2048, "Energy (Atwater Specific"), (2047, "Energy (Atwater General")], "energia_kcal"),
    ("energia_kj", "Energia", "kJ", "energia", [(1062, "Energy")], "energia_kj"),
    ("proteina_g", "Proteínas", "g", "macro", [(1003, "Protein")], "proteina_g"),
    ("carboidrato_g", "Carboidratos", "g", "macro", [(1005, "Carbohydrate, by difference"), (1050, "Carbohydrate, by summation")], "carboidrato_g"),
    ("acucares_g", "Açúcares totais", "g", "macro", [(2000, "Sugars, Total"), (1063, "Sugars, Total"), (2000, "Total Sugars")], None),
    ("fibra_g", "Fibra alimentar", "g", "macro", [(1079, "Fiber, total dietary")], "fibra_g"),
    ("lipideos_g", "Gorduras totais", "g", "macro", [(1004, "Total lipid (fat)"), (1085, "Total fat (NLEA)")], "lipideos_g"),
    ("gordura_saturada_g", "Gorduras saturadas", "g", "gorduras", [(1258, "Fatty acids, total saturated")], "saturados_g"),
    ("gordura_monoinsaturada_g", "Gorduras monoinsaturadas", "g", "gorduras", [(1292, "Fatty acids, total monounsaturated")], "monoinsaturados_g"),
    ("gordura_poliinsaturada_g", "Gorduras poli-insaturadas", "g", "gorduras", [(1293, "Fatty acids, total polyunsaturated")], "poliinsaturados_g"),
    ("gordura_trans_g", "Gorduras trans", "g", "gorduras", [(1257, "Fatty acids, total trans")], "trans_g"),
    ("colesterol_mg", "Colesterol", "mg", "gorduras", [(1253, "Cholesterol")], "colesterol_mg"),
    ("amido_g", "Amido", "g", "carboidratos", [(1009, "Starch")], None),
    ("sacarose_g", "Sacarose", "g", "carboidratos", [(1010, "Sucrose")], None),
    ("glicose_g", "Glicose", "g", "carboidratos", [(1011, "Glucose")], None),
    ("frutose_g", "Frutose", "g", "carboidratos", [(1012, "Fructose")], None),
    ("lactose_g", "Lactose", "g", "carboidratos", [(1013, "Lactose")], None),
    ("agua_g", "Água", "g", "outros", [(1051, "Water")], "umidade_pct"),
    ("cinzas_g", "Cinzas (minerais totais)", "g", "outros", [(1007, "Ash")], "cinzas_g"),
    ("alcool_g", "Álcool", "g", "outros", [(1018, "Alcohol, ethyl")], None),
    ("cafeina_mg", "Cafeína", "mg", "outros", [(1057, "Caffeine")], None),
    ("sodio_mg", "Sódio", "mg", "minerais", [(1093, "Sodium, Na")], "sodio_mg"),
    ("potassio_mg", "Potássio", "mg", "minerais", [(1092, "Potassium, K")], "potassio_mg"),
    ("calcio_mg", "Cálcio", "mg", "minerais", [(1087, "Calcium, Ca")], "calcio_mg"),
    ("ferro_mg", "Ferro", "mg", "minerais", [(1089, "Iron, Fe")], "ferro_mg"),
    ("magnesio_mg", "Magnésio", "mg", "minerais", [(1090, "Magnesium, Mg")], "magnesio_mg"),
    ("fosforo_mg", "Fósforo", "mg", "minerais", [(1091, "Phosphorus, P")], "fosforo_mg"),
    ("zinco_mg", "Zinco", "mg", "minerais", [(1095, "Zinc, Zn")], "zinco_mg"),
    ("cobre_mg", "Cobre", "mg", "minerais", [(1098, "Copper, Cu")], "cobre_mg"),
    ("manganes_mg", "Manganês", "mg", "minerais", [(1101, "Manganese, Mn")], "manganes_mg"),
    ("selenio_ug", "Selênio", "µg", "minerais", [(1103, "Selenium, Se")], None),
    ("vitamina_a_rae_ug", "Vitamina A (RAE)", "µg", "vitaminas", [(1106, "Vitamin A, RAE")], "RAE_mcg"),
    ("retinol_ug", "Retinol", "µg", "vitaminas", [(1105, "Retinol")], "retinol_mcg"),
    ("vitamina_c_mg", "Vitamina C", "mg", "vitaminas", [(1162, "Vitamin C, total ascorbic acid")], "vitamina_c_mg"),
    ("vitamina_d_ug", "Vitamina D", "µg", "vitaminas", [(1114, "Vitamin D (D2 + D3)")], None),
    ("vitamina_e_mg", "Vitamina E", "mg", "vitaminas", [(1109, "Vitamin E (alpha-tocopherol)")], None),
    ("vitamina_k_ug", "Vitamina K", "µg", "vitaminas", [(1185, "Vitamin K (phylloquinone)")], None),
    ("tiamina_mg", "Tiamina (B1)", "mg", "vitaminas", [(1165, "Thiamin")], "tiamina_mg"),
    ("riboflavina_mg", "Riboflavina (B2)", "mg", "vitaminas", [(1166, "Riboflavin")], "riboflavina_mg"),
    ("niacina_mg", "Niacina (B3)", "mg", "vitaminas", [(1167, "Niacin")], "niacina_mg"),
    ("vitamina_b6_mg", "Vitamina B6", "mg", "vitaminas", [(1175, "Vitamin B-6")], "piridoxina_mg"),
    ("folato_ug", "Folato", "µg", "vitaminas", [(1177, "Folate, total")], None),
    ("vitamina_b12_ug", "Vitamina B12", "µg", "vitaminas", [(1178, "Vitamin B-12")], None),
]

UNIT_MAP = {"G": "g", "MG": "mg", "UG": "µg", "KCAL": "kcal", "kJ": "kJ", "KJ": "kJ",
            "MG_ATE": "mg", "MG_GAE": "mg", "UMOL_TE": "µmol TE", "PH": "pH"}
DROP_UNITS = {"IU", "SP_GR"}  # UI (não métrico) e densidade (vai para foods.densidade_g_ml)

CATEGORY_PT = {
    "Alcoholic Beverages": "Bebidas alcoólicas", "American Indian/Alaska Native Foods": "Alimentos indígenas (EUA)",
    "Baby Foods": "Alimentos infantis", "Baked Products": "Panificados", "Beef Products": "Carne bovina",
    "Beverages": "Bebidas", "Branded Food Products Database": "Produtos de marca",
    "Breakfast Cereals": "Cereais matinais", "Cereal Grains and Pasta": "Cereais e massas",
    "Dairy and Egg Products": "Laticínios e ovos", "Fast Foods": "Fast food", "Fats and Oils": "Óleos e gorduras",
    "Finfish and Shellfish Products": "Peixes e frutos do mar", "Fruits and Fruit Juices": "Frutas e sucos",
    "Lamb, Veal, and Game Products": "Cordeiro, vitela e caça", "Legumes and Legume Products": "Leguminosas",
    "Meals, Entrees, and Side Dishes": "Pratos prontos", "Nut and Seed Products": "Castanhas e sementes",
    "Pork Products": "Carne suína", "Poultry Products": "Aves", "Quality Control Materials": "Materiais de controle",
    "Restaurant Foods": "Comida de restaurante", "Sausages and Luncheon Meats": "Embutidos",
    "Snacks": "Salgadinhos", "Soups, Sauces, and Gravies": "Sopas e molhos", "Spices and Herbs": "Especiarias e ervas",
    "Sweets": "Doces", "Vegetables and Vegetable Products": "Hortaliças",
}

# unidades EUA reconhecidas no texto das porções (mais longas primeiro)
_US_UNIT = re.compile(r"^(fl oz|fluid ounce|tablespoons?|tbsp|teaspoons?|tsp|cups?|oz|lbs?|pints?|quarts?|gallons?)\b")
# palavras comuns das porções do USDA -> português
PORTION_WORDS = {
    "serving": "porção", "servings": "porções", "piece": "pedaço", "pieces": "pedaços", "slice": "fatia",
    "slices": "fatias", "medium": "médio", "large": "grande", "small": "pequeno", "extra large": "extra grande",
    "whole": "inteiro", "each": "unidade", "chop": "costeleta", "roast": "peça (assado)", "steak": "bife",
    "fillet": "filé", "leaf": "folha", "leaves": "folhas", "clove": "dente", "stalk": "talo", "sprig": "ramo",
    "can": "lata", "package": "embalagem", "container": "pote", "stick": "tablete", "wedge": "gomo",
    "link": "gomo", "patty": "hambúrguer", "breast": "peito", "thigh": "sobrecoxa", "drumstick": "coxa",
    "wing": "asa", "fruit": "fruta", "head": "cabeça", "bunch": "maço", "spear": "lança", "pod": "vagem",
    "chopped": "picado", "sliced": "fatiado", "diced": "em cubos", "grated": "ralado", "shredded": "ralado",
    "mashed": "amassado", "ground": "moído", "packed": "compactado", "pureed": "em purê", "raw": "cru",
    "cooked": "cozido", "drained": "escorrido", "with": "com", "without": "sem", "and": "e", "or": "ou",
    "dia": "diâmetro", "long": "de comprimento", "thick": "de espessura", "yield": "rende", "from": "de",
    "whole kernel": "grão inteiro", "halves": "metades", "pieces or slices": "pedaços ou fatias",
    "nlea serving": "porção NLEA", "unit": "unidade", "cubic inch": "polegada cúbica", "of": "de", "bar": "barra",
    "approx": "aprox.", "about": "cerca de", "portion": "porção", "amount to make": "quantidade para", "peeled": "descascado",
    "per": "por", "lb": "libra (453,6 g)", "as purchased": "como comprado", "yields": "rende", "heaping": "cheia", "envelope": "envelope", "individual": "individual",
    "cup": "copinho", "cups": "copinhos", "pkg": "pacote", "sub": "sanduíche", "pudding": "pudim",
    "icing": "cobertura", "roll": "rolinho", "cookie": "biscoito", "muffin": "muffin", "tortilla": "tortilha",
}
_WORD = re.compile(r"\b(" + "|".join(sorted(map(re.escape, PORTION_WORDS), key=len, reverse=True)) + r")\b")


def translate_portion(text: str) -> str:
    # primeiro converte quantidades imperiais ("1/2 cup" -> ml), depois traduz palavras soltas
    return _WORD.sub(lambda m: PORTION_WORDS[m.group(1)], metricize_text(text))


_CANON = {"tablespoon": "tbsp", "tablespoons": "tbsp", "teaspoon": "tsp", "teaspoons": "tsp", "cups": "cup",
          "fluid ounce": "fl oz", "lbs": "lb", "pints": "pint", "quarts": "quart", "gallons": "gallon"}


# ---------------------------------------------------------------- USDA
def _check_ids(nut: pd.DataFrame) -> dict[int, str]:
    """usda nutrient_id -> chave canônica, conferindo o nome de cada id."""
    names = dict(zip(nut["id"], nut["name"]))
    out = {}
    for key, *_, ids, _taco in CORE:
        for nid, expected in ids:
            if nid in names and names[nid].startswith(expected):
                out.setdefault(nid, key)
    return out


def load_usda(dataset: str):
    d = RAW_USDA / dataset
    food = pd.read_csv(d / "food.csv")
    if dataset == "foundation":
        food = food[food["data_type"] == "foundation_food"]
    cat = pd.read_csv(d / "food_category.csv").set_index("id")["description"]
    nut = pd.read_csv(d / "nutrient.csv")
    fn = pd.read_csv(d / "food_nutrient.csv", usecols=["fdc_id", "nutrient_id", "amount"])
    fn = fn[fn["fdc_id"].isin(food["fdc_id"])].dropna(subset=["amount"])

    foods = pd.DataFrame({
        "food_id": "usda:" + food["fdc_id"].astype(str),
        "fonte": "usda_" + dataset,
        "codigo": food["fdc_id"].astype(str),
        "nome": food["description"],
        "nome_en": food["description"],
        "categoria": food["food_category_id"].map(cat).map(CATEGORY_PT),
    })

    # densidade (g/ml) pela gravidade específica, quando analisada
    sg_ids = nut.loc[nut["unit_name"] == "SP_GR", "id"]
    sg = fn[fn["nutrient_id"].isin(sg_ids)].groupby("fdc_id")["amount"].first()
    foods["densidade_g_ml"] = food["fdc_id"].map(sg).to_numpy()

    # nutrientes: chaves canônicas (prioridade por id) + demais em formato usda_<id>
    core_ids = _check_ids(nut)
    unit = dict(zip(nut["id"], nut["unit_name"]))
    fn = fn[~fn["nutrient_id"].map(unit).isin(DROP_UNITS)]
    # prioridade dentro de cada chave (ex.: energia 1008 antes de 2048)
    prio = {nid: rank for *_, ids, _t in CORE for rank, (nid, _name) in enumerate(ids)}
    fn = fn.assign(
        nutrient_key=fn["nutrient_id"].map(core_ids).fillna("usda_" + fn["nutrient_id"].astype(str)),
        prio=fn["nutrient_id"].map(prio).fillna(0),
    )
    fn = (fn.sort_values("prio").drop_duplicates(["fdc_id", "nutrient_key"])
            .assign(food_id="usda:" + fn["fdc_id"].astype(str), traco=False))
    values = fn[["food_id", "nutrient_key", "amount"]].rename(columns={"amount": "valor"}).assign(traco=False)

    extra = nut[~nut["id"].isin(core_ids) & ~nut["unit_name"].isin(DROP_UNITS)]
    extra = pd.DataFrame({
        "nutrient_key": "usda_" + extra["id"].astype(str), "nome": extra["name"],
        "unidade": extra["unit_name"].map(UNIT_MAP).fillna(extra["unit_name"].str.lower()),
        "grupo": "outros (USDA)", "nome_en": extra["name"],
    })
    portions = usda_portions(d, food)
    return foods, values, extra, portions


def usda_portions(d: Path, food: pd.DataFrame) -> pd.DataFrame:
    """Porções do USDA (cup, tbsp, oz...) convertidas para g e ml, nome em português."""
    p = pd.read_csv(d / "food_portion.csv")
    p = p[p["fdc_id"].isin(food["fdc_id"])]
    mu = pd.read_csv(d / "measure_unit.csv").set_index("id")["name"]
    unit_name = p["measure_unit_id"].map(mu).fillna("undetermined")
    rows = []
    for rec, uname in zip(p.itertuples(index=False), unit_name):
        amount = rec.amount if pd.notna(rec.amount) and rec.amount > 0 else 1.0
        text = " ".join(str(x) for x in (uname if uname != "undetermined" else "", rec.modifier, rec.portion_description)
                        if isinstance(x, str) and x and x != "nan").strip().lower()
        m = _US_UNIT.match(text)
        ml, unit_pt, rest = np.nan, None, text
        if m:
            u = _CANON.get(m.group(1), m.group(1))
            rest = text[m.end():].strip(" ,")
            unit_pt = US_NAMES_PT.get(u, u)
            if norm_unit(u) in VOLUME_ML:
                ml = amount * VOLUME_ML[norm_unit(u)]
        qty = fmt_num(amount, 2).rstrip("0").rstrip(",")
        if unit_pt and not np.isnan(ml):
            label = f"{qty} {unit_pt} ({fmt_num(ml, 1)} ml)"
        elif unit_pt:  # massa (oz, lb): mostra só o equivalente métrico
            label = f"{qty} {unit_pt}"
        else:
            label = translate_portion(f"{qty} {text}") if amount != 1 else translate_portion(text)
        if unit_pt and rest:
            label += f", {translate_portion(rest)}"
        label += f" = {fmt_num(rec.gram_weight, 1)} g"
        rows.append({"food_id": f"usda:{rec.fdc_id}", "quantidade": amount, "medida_original": text,
                     "medida_pt": label, "gramas": rec.gram_weight, "ml": ml})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- TACO
def load_taco():
    comp = pd.read_csv(RAW_TACO / "taco_composicao.csv")
    fat = pd.read_csv(RAW_TACO / "taco_acidos_graxos.csv")
    fat["trans_g"] = fat[["c18_1t_g", "c18_2t_g"]].sum(axis=1, min_count=1)
    df = comp.merge(fat[["numero_alimento", "saturados_g", "monoinsaturados_g", "poliinsaturados_g", "trans_g"]],
                    on="numero_alimento", how="left")
    foods = pd.DataFrame({
        "food_id": "taco:" + df["numero_alimento"].astype(str),
        "fonte": "taco",
        "codigo": df["numero_alimento"].astype(str),
        "nome": df["descricao"],
        "nome_en": None,
        "categoria": df["categoria"],
        "densidade_g_ml": np.nan,
    })
    rows = []
    for key, *_, taco_col in CORE:
        if not taco_col:
            continue
        v = pd.to_numeric(df[taco_col], errors="coerce")
        part = pd.DataFrame({"food_id": foods["food_id"], "nutrient_key": key, "valor": v})
        part = part.dropna(subset=["valor"])
        part["traco"] = np.isclose(part["valor"], TRACE)
        part.loc[part["traco"], "valor"] = 0.0
        rows.append(part)
    return foods, pd.concat(rows, ignore_index=True)


def load_household() -> pd.DataFrame:
    pof = pd.read_csv(RAW_TACO / "pof_medidas_caseiras.csv")
    out = pd.DataFrame({
        "alimento": pof["descricao_alimento"].str.strip(),
        "preparacao": pof["descricao_preparacao"].str.strip(),
        "medida": pof["descricao_medida"].str.strip(),
        "gramas": pd.to_numeric(pof["quantidade_g"], errors="coerce"),
    }).dropna(subset=["gramas"])
    out = out[~out["medida"].isin(["GRAMA", "QUILO"])]
    return out.drop_duplicates(["alimento", "preparacao", "medida"]).reset_index(drop=True)


def build() -> dict[str, pd.DataFrame]:
    t_foods, t_vals = load_taco()
    parts = [load_usda(ds) for ds in ("sr_legacy", "foundation")]
    foods = pd.concat([t_foods] + [p[0] for p in parts], ignore_index=True)
    values = pd.concat([t_vals] + [p[1] for p in parts], ignore_index=True)
    portions = pd.concat([p[3] for p in parts], ignore_index=True)

    # densidade derivada das porções em volume (mediana g/ml), se não houver gravidade específica
    vol = portions.dropna(subset=["ml"]).query("ml > 0 and gramas > 0")
    dens = (vol["gramas"] / vol["ml"]).groupby(vol["food_id"]).median()
    foods["densidade_g_ml"] = foods["densidade_g_ml"].fillna(foods["food_id"].map(dens))

    core = pd.DataFrame([{"nutrient_key": k, "nome": n, "unidade": u, "grupo": g, "nome_en": None}
                         for k, n, u, g, _ids, _t in CORE])
    extra = pd.concat([p[2] for p in parts]).drop_duplicates("nutrient_key")
    nutrients = pd.concat([core, extra], ignore_index=True)
    nutrients["ordem"] = range(len(nutrients))

    values = values[values["nutrient_key"].isin(nutrients["nutrient_key"])]
    # catálogo só com nutrientes que têm algum valor medido
    nutrients = nutrients[nutrients["nutrient_key"].isin(values["nutrient_key"])].reset_index(drop=True)
    nutrients["ordem"] = range(len(nutrients))
    values = values.drop_duplicates(["food_id", "nutrient_key"]).reset_index(drop=True)
    foods["n_nutrientes"] = foods["food_id"].map(values.groupby("food_id").size()).fillna(0).astype(int)
    return {"foods": foods, "nutrients": nutrients, "food_nutrients": values,
            "portions": portions, "household": load_household()}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, df in build().items():
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype("string")
        path = OUT / f"{name}.parquet"
        df.to_parquet(path, index=False, compression="zstd")
        print(f"{path.name:24s} {len(df):>9,d} linhas  {path.stat().st_size / 1e6:6.2f} MB")


if __name__ == "__main__":
    main()
