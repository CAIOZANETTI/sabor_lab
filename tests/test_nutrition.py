"""Nutrição: banco sintético com respostas conhecidas + verificações no banco real."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from flavorlab.nutrition import NutritionDB

from conftest import ROOT

REAL = ROOT / "data" / "processed" / "nutrition" / "foods.parquet"


@pytest.fixture()
def tiny_ndb(tmp_path):
    """
    taco:1  Azeite (TACO): 884 kcal, 100 g gordura; sem açúcares; sem densidade
    usda:9  Olive oil (USDA): açúcares 0, sódio 2 mg; densidade 0,9 g/ml
    taco:2  Alho (TACO): 113 kcal, carbo 24 g; medida IBGE 'ALHO' unidade = 4 g
    usda:7  Garlic (USDA): açúcares 1 g; porção 'clove' = 3 g
    """
    foods = pd.DataFrame([
        ("taco:1", "taco", "1", "Azeite, de oliva", None, "Óleos", np.nan),
        ("usda:9", "usda_sr_legacy", "9", "Oil, olive", "Oil, olive", "Óleos e gorduras", 0.9),
        ("taco:2", "taco", "2", "Alho, cru", None, "Hortaliças", np.nan),
        ("usda:7", "usda_sr_legacy", "7", "Garlic, raw", "Garlic, raw", "Hortaliças", np.nan),
    ], columns=["food_id", "fonte", "codigo", "nome", "nome_en", "categoria", "densidade_g_ml"])
    foods["n_nutrientes"] = 3
    nutrients = pd.DataFrame([
        ("energia_kcal", "Energia", "kcal", "energia"), ("lipideos_g", "Gorduras totais", "g", "macro"),
        ("carboidrato_g", "Carboidratos", "g", "macro"), ("acucares_g", "Açúcares totais", "g", "macro"),
        ("sodio_mg", "Sódio", "mg", "minerais"),
    ], columns=["nutrient_key", "nome", "unidade", "grupo"])
    vals = pd.DataFrame([
        ("taco:1", "energia_kcal", 884.0), ("taco:1", "lipideos_g", 100.0),
        ("usda:9", "energia_kcal", 880.0), ("usda:9", "lipideos_g", 100.0), ("usda:9", "acucares_g", 0.0),
        ("usda:9", "sodio_mg", 2.0),
        ("taco:2", "energia_kcal", 113.0), ("taco:2", "carboidrato_g", 24.0),
        ("usda:7", "energia_kcal", 149.0), ("usda:7", "acucares_g", 1.0),
    ], columns=["food_id", "nutrient_key", "valor"]).assign(traco=False)
    portions = pd.DataFrame([("usda:7", 1.0, "clove", "1 dente = 3 g", 3.0, np.nan)],
                            columns=["food_id", "quantidade", "medida_original", "medida_pt", "gramas", "ml"])
    household = pd.DataFrame([("ALHO", "NAO SE APLICA", "UNIDADE", 4.0)],
                             columns=["alimento", "preparacao", "medida", "gramas"])
    for name, df in [("foods", foods), ("nutrients", nutrients), ("food_nutrients", vals),
                     ("portions", portions), ("household", household)]:
        df.to_parquet(tmp_path / f"{name}.parquet", index=False)
    dic = tmp_path / "dic.csv"
    pd.DataFrame([
        ("azeite", "olive_oil", "taco:1", "usda:9", "", ""),
        ("alho", "garlic", "taco:2", "usda:7", "ALHO", ""),
    ], columns=["nome", "sabor", "nutricao", "complemento", "medidas_pof", "observacao"]).to_csv(dic, index=False)
    return NutritionDB(tmp_path, dictionary=dic)


def test_missing_db_message(tmp_path):
    with pytest.raises(FileNotFoundError, match="build_nutrition"):
        NutritionDB(tmp_path)


def test_complement_fills_gaps_only(tiny_ndb):
    per100, filled = tiny_ndb.per100g("taco:1", "usda:9")
    assert per100["energia_kcal"] == 884.0          # valor da TACO mantido
    assert per100["acucares_g"] == 0.0 and per100["sodio_mg"] == 2.0
    assert set(filled) == {"acucares_g", "sodio_mg"}


def test_volume_uses_density_from_complement(tiny_ndb):
    food = tiny_ndb.lookup("Azeite")                 # sem acento/maiúscula
    g, how = tiny_ndb.to_grams(2, "colher de sopa", food)
    assert g == pytest.approx(2 * 15 * 0.9) and "densidade" in how
    g, _ = tiny_ndb.to_grams(1, "tbsp", food)
    assert g == pytest.approx(14.78676478125 * 0.9)


def test_volume_without_density_assumes_water_and_warns(tiny_ndb):
    r = tiny_ndb.recipe([{"nome": "alho", "quantidade": 100, "unidade": "ml"}])
    assert r.lines[0].gramas == pytest.approx(100.0)
    assert any("assumida" in w for w in r.warnings)


def test_count_units_household_then_usda(tiny_ndb):
    food = tiny_ndb.lookup("alho")
    g, how = tiny_ndb.to_grams(3, "dentes", food)
    assert g == pytest.approx(12.0) and "IBGE" in how       # POF 'UNIDADE' = 4 g
    no_pof = tiny_ndb.lookup("alho"); no_pof.pof = None
    g, how = tiny_ndb.to_grams(3, "dentes", no_pof)
    assert g == pytest.approx(9.0) and "USDA" in how        # porção 'clove' = 3 g


def test_imperial_mass(tiny_ndb):
    g, how = tiny_ndb.to_grams(1, "lb", tiny_ndb.lookup("alho"))
    assert g == pytest.approx(453.59237) and how == "massa"


def test_recipe_totals_portions_and_vd(tiny_ndb):
    rows = [{"nome": "azeite", "quantidade": "50", "unidade": "g"},
            {"nome": "alho", "quantidade": "1/2", "unidade": "kg"},
            {"nome": "alho", "quantidade": "x", "unidade": "g", "gramas": "10"}]  # gramas vale
    r = tiny_ndb.recipe(rows, portions=2)
    assert [round(line.gramas, 3) for line in r.lines] == [50.0, 500.0, 10.0]
    assert r.total["energia_kcal"] == pytest.approx(884 * 0.5 + 113 * 5 + 113 * 0.1)
    assert r.per_portion["energia_kcal"] == pytest.approx(r.total["energia_kcal"] / 2)
    assert r.vd["energia_kcal"] == pytest.approx(r.per_portion["energia_kcal"] / 2000 * 100)
    assert "acucares_g" not in r.vd  # sem %VD para açúcares totais


def test_unknown_unit_and_food_are_reported(tiny_ndb):
    r = tiny_ndb.recipe([{"nome": "alho", "quantidade": 1, "unidade": "punhado"},
                         {"nome": "unobtainium", "quantidade": 10, "unidade": "g"}])
    assert r.lines == []
    assert any("punhado" in w for w in r.warnings) and any("unobtainium" in w for w in r.warnings)


# ------------------------------------------------------------- banco real
@pytest.fixture(scope="module")
def real_ndb():
    if not REAL.exists():
        pytest.skip("banco nutricional não construído")
    return NutritionDB()


def test_real_reference_values(real_ndb):
    m = real_ndb.matrix
    # USDA SR Legacy: açúcar granulado 387 kcal e 99,8 g de açúcares por 100 g
    sugar = real_ndb.lookup("açúcar")
    per100, filled = real_ndb.per100g(sugar.food_id, sugar.complement)
    assert per100["energia_kcal"] == pytest.approx(386.57, abs=1)   # TACO
    assert per100["acucares_g"] == pytest.approx(99.8, abs=0.5) and "acucares_g" in filled
    assert m.loc["usda:171413", "lipideos_g"] == pytest.approx(100.0)   # azeite


def test_real_classic_conversions(real_ndb):
    def g(name, qty, unit):
        return real_ndb.to_grams(qty, unit, real_ndb.lookup(name))[0]
    assert g("farinha de trigo", 1, "cup") == pytest.approx(125, abs=3)     # 1 cup = 125 g
    assert g("manteiga", 1, "cup") == pytest.approx(227, abs=3)             # 1 cup = 227 g
    assert g("açúcar", 1, "cup") == pytest.approx(200, abs=3)               # 1 cup = 200 g
    assert g("azeite", 1, "colher de sopa") == pytest.approx(13.7, abs=0.5)


def test_real_dictionary_is_valid(real_ndb):
    d = pd.read_csv(ROOT / "data" / "dicionario_ingredientes.csv", dtype=str).fillna("")
    assert d["nome"].is_unique
    for col in ("nutricao", "complemento"):
        ids = [x for x in d[col] if x]
        assert set(ids) <= set(real_ndb.foods.index), f"ids inválidos em {col}"
    pof = set(real_ndb.household["alimento"])
    assert all(p in pof for p in d["medidas_pof"] if p)


def test_real_everything_metric(real_ndb):
    units = set(real_ndb.nutrients["unidade"])
    assert not units & {"IU", "iu", "UI"}
    assert {"g", "mg", "µg", "kcal"} <= units
    p = real_ndb.portions
    imperial = r"\b(?:inch|inches|cups?|oz|tbsp|tsp|lbs?|fl oz|pints?|quarts?)\b"
    leftover = p[p["medida_pt"].str.contains(imperial, regex=True)]
    assert leftover.empty, leftover["medida_pt"].head().tolist()
