"""Nutrição após preparo (demanda 007): bases, dupla contagem, água, gordura, precedência e porções."""

from __future__ import annotations

import socket
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import pytest

from flavorlab.evidence import SourceRegistry, validate_claim
from flavorlab.nutrition import NutritionDB
from flavorlab.nutrition_report import nutrition_section
from flavorlab.prepared_nutrition import (FatTransfer, Factors, PreparedItem, PreparedNutritionError,
                                          load_factors, prepared_nutrition, prepared_recipe, resolve_method)
from flavorlab.states import COOKING_METHODS

from conftest import ROOT

REAL = ROOT / "data" / "processed" / "nutrition" / "foods.parquet"
FACTORS_DIR = ROOT / "data" / "cooking_factors"


# --------------------------------------------------------------------------- banco sintético
@dataclass
class _Form:
    form_id: str
    state: str
    preparation: str
    concept_id: str = "sl:ingredient:beef"
    variant_id: str = ""
    part_id: str = "sl:part:test_cut"


@dataclass
class _Map:
    source: str
    source_id: str
    mapping_type: str = "exact"


@dataclass
class _Res:
    entity_id: str


@dataclass
class StubCatalog:
    """Só o que o motor usa do catálogo (demanda 002)."""
    by_source: dict = field(default_factory=dict)
    forms_: dict = field(default_factory=dict)
    maps: dict = field(default_factory=dict)
    anc: dict = field(default_factory=dict)

    def resolve_source(self, source, sid):
        return _Res(self.by_source.get(f"{source}:{sid}", ""))

    def get(self, entity_id):
        return self.forms_[entity_id]

    def ancestors(self, entity_id):
        return self.anc.get(entity_id, [])

    def forms(self, parent):
        return [f for f in self.forms_.values() if f.part_id == parent]

    def mappings(self, form_id, source=None):
        return self.maps.get(form_id, [])


@pytest.fixture()
def tiny(tmp_path):
    """
    usda:1  carne crua      100 g: 20 g proteína, 10 g gordura, 70 g água, 170 kcal, tiamina 0,10 mg, sódio 60 mg,
                            vitamina C não analisada
    usda:2  carne grelhada  (registro preparado medido do mesmo corte)
    taco:3  caldo           100 g: 1 g proteína, 0 g gordura, 98 g água, 5 kcal, sódio 300 mg
    taco:4  óleo            100 g de gordura, 884 kcal
    """
    keys = [("energia_kcal", "Energia", "kcal"), ("energia_kj", "Energia", "kJ"), ("proteina_g", "Proteínas", "g"),
            ("lipideos_g", "Gorduras totais", "g"), ("agua_g", "Água", "g"), ("tiamina_mg", "Tiamina", "mg"),
            ("sodio_mg", "Sódio", "mg"), ("vitamina_c_mg", "Vitamina C", "mg"),
            ("gordura_saturada_g", "Gorduras saturadas", "g")]
    nutrients = pd.DataFrame([(k, n, u, "x") for k, n, u in keys], columns=["nutrient_key", "nome", "unidade", "grupo"])
    foods = pd.DataFrame([
        ("usda:1", "usda_sr_legacy", "1", "Beef, test cut, raw"),
        ("usda:2", "usda_sr_legacy", "2", "Beef, test cut, cooked, broiled"),
        ("taco:3", "taco", "3", "Caldo de teste"),
        ("taco:4", "taco", "4", "Óleo de teste"),
    ], columns=["food_id", "fonte", "codigo", "nome"]).assign(nome_en=None, categoria="x", densidade_g_ml=np.nan,
                                                               n_nutrientes=5)
    v = {"usda:1": {"energia_kcal": 170, "energia_kj": 711.28, "proteina_g": 20, "lipideos_g": 10, "agua_g": 70,
                    "tiamina_mg": 0.10, "sodio_mg": 60, "gordura_saturada_g": 4},
         "usda:2": {"energia_kcal": 210, "proteina_g": 26, "lipideos_g": 11, "agua_g": 62, "tiamina_mg": 0.08,
                    "sodio_mg": 75, "vitamina_c_mg": 0},
         "taco:3": {"energia_kcal": 5, "proteina_g": 1, "lipideos_g": 0, "agua_g": 98, "sodio_mg": 300},
         "taco:4": {"energia_kcal": 884, "lipideos_g": 100}}
    vals = pd.DataFrame([(f, k, float(x)) for f, d in v.items() for k, x in d.items()],
                        columns=["food_id", "nutrient_key", "valor"]).assign(traco=False)
    empty_p = pd.DataFrame(columns=["food_id", "quantidade", "medida_original", "medida_pt", "gramas", "ml"])
    empty_h = pd.DataFrame(columns=["alimento", "preparacao", "medida", "gramas"])
    for name, df in [("foods", foods), ("nutrients", nutrients), ("food_nutrients", vals),
                     ("portions", empty_p), ("household", empty_h)]:
        df.to_parquet(tmp_path / f"{name}.parquet", index=False)
    dic = tmp_path / "dic.csv"
    pd.DataFrame([("carne", "", "usda:1", "", "", ""), ("caldo", "", "taco:3", "", "", ""),
                  ("oleo", "", "taco:4", "", "", "")],
                  columns=["nome", "sabor", "nutricao", "complemento", "medidas_pof", "observacao"]).to_csv(dic, index=False)
    ndb = NutritionDB(tmp_path, dictionary=dic)

    real = load_factors()
    yields = pd.DataFrame([{
        "yield_id": "t:1", "description": "Beef, test cut", "usda_method": "Broiled or Grilled",
        "method_key": "grill_broil", "ndb_number": "", "cooked_food_id": "usda:2", "raw_food_id": "usda:1",
        "raw_link_rule": "teste", "yield_pct": 80.0, "n": 10, "sd": 3.0, "yield_min_pct": 75.0, "yield_max_pct": 85.0,
        "moisture_change_pct": -18.0, "fat_change_pct": -2.0, "release_year": "2003", "basis": "peso cru",
        "notes": "", "source_id": "usda_cooking_yields_r2"}, {
        "yield_id": "t:2", "description": "Beef, test cut", "usda_method": "Roasted",
        "method_key": "roast_bake", "ndb_number": "", "cooked_food_id": "", "raw_food_id": "usda:1",
        "raw_link_rule": "teste", "yield_pct": 75.0, "n": 10, "sd": None, "yield_min_pct": None, "yield_max_pct": None,
        "moisture_change_pct": -22.0, "fat_change_pct": -3.0, "release_year": "2003", "basis": "peso cru",
        "notes": "", "source_id": "usda_cooking_yields_r2"}])
    retention = pd.DataFrame([
        {"retn_code": "9001", "description": "BEEF,ROASTED (teste)", "nutrient_key": "tiamina_mg", "factor": 0.5},
        {"retn_code": "9001", "description": "BEEF,ROASTED (teste)", "nutrient_key": "sodio_mg", "factor": 1.0},
        {"retn_code": "9002", "description": "BEEF,FRIED (teste)", "nutrient_key": "tiamina_mg", "factor": 0.7},
    ])
    rmap = pd.DataFrame([
        {"rule_id": "x1", "match": "sl:ingredient:beef", "method_key": "roast_bake", "condition": "",
         "retn_code": "9001", "match_level": "group", "notes": ""},
        {"rule_id": "x2", "match": "sl:form:test_raw", "method_key": "deep_fry", "condition": "coated=no",
         "retn_code": "9002", "match_level": "specific", "notes": ""},
        {"rule_id": "x3", "match": "sl:form:test_raw", "method_key": "boil", "condition": "liquid=discarded",
         "retn_code": "9002", "match_level": "specific", "notes": ""},
    ])
    factors = Factors(real.methods, yields, retention, rmap)
    cat = StubCatalog(
        by_source={"usda:1": "sl:form:test_raw", "usda:2": "sl:form:test_grilled"},
        forms_={"sl:form:test_raw": _Form("sl:form:test_raw", "raw", ""),
                "sl:form:test_grilled": _Form("sl:form:test_grilled", "cooked", "grilled")},
        maps={"sl:form:test_grilled": [_Map("usda", "2")]},
        anc={"sl:form:test_raw": ["sl:part:test_cut", "sl:ingredient:beef", "sl:ingredient:meat"]})
    return ndb, factors, cat


def run(tiny, item, **kw):
    ndb, factors, cat = tiny
    return prepared_nutrition(ndb, item, factors=factors, catalog=cat, **kw)


# --------------------------------------------------------------------------- 1. bases
def test_yield_and_retention_use_raw_basis(tiny):
    r = run(tiny, PreparedItem("carne", 1000, "raw", method="roast_oven"))   # técnica 003 -> roast_bake
    assert r.path == "derived_from_raw" and r.yield_status == "table"
    assert r.yield_factor.factor == pytest.approx(0.75) and r.yield_factor.basis == "raw_mass"
    assert r.cooked_mass_g == pytest.approx(750)                 # massa cozida = crua × rendimento
    assert r.nutrient_totals["tiamina_mg"] == pytest.approx(0.10 * 10 * 0.5)   # cru × retenção, base crua
    assert r.nutrient_totals["agua_g"] == pytest.approx(700 - 220)             # Δágua = -22% de 1000 g crus
    assert r.nutrient_totals["lipideos_g"] == pytest.approx(100 - 30)          # Δgordura = -3% de 1000 g crus
    assert r.nutrient_totals["energia_kcal"] == pytest.approx(1700 - 9 * 30)   # Atwater geral
    assert r.nutrient_totals["energia_kj"] == pytest.approx(7112.8 - 9 * 30 * 4.184)
    assert r.per100g()["tiamina_mg"] == pytest.approx(0.5 / 750 * 100)        # concentração na massa cozida
    assert r.category("tiamina_mg") == "derived" and r.category("proteina_g") == "estimated"


# --------------------------------------------------------------------------- 2. dupla contagem
def test_cooked_measured_record_is_not_factored_again(tiny):
    r = run(tiny, PreparedItem("carne grelhada", 300, "served", food_id="usda:2", method="grill"))
    assert r.path == "measured_prepared" and r.retention_factors == [] and r.yield_factor is None
    assert r.nutrient_totals["tiamina_mg"] == pytest.approx(0.08 * 3)          # registro × massa, sem 0,5
    assert r.measured_values["proteina_g"] == pytest.approx(78)
    assert any("dupla contagem" in w for w in r.warnings)


def test_cooked_record_with_raw_mass_is_refused(tiny):
    r = run(tiny, PreparedItem("carne grelhada", 300, "raw", food_id="usda:2"))
    assert r.path == "not_computable" and r.nutrient_totals == {}


# --------------------------------------------------------------------------- 3. água
def test_water_reduction_raises_concentration_not_totals(tiny):
    r = run(tiny, PreparedItem("caldo", 1000, "raw", method="simmer_reduce", cooked_mass_g=600))
    assert r.yield_status == "observed" and r.yield_factor.factor == pytest.approx(0.6)
    assert r.nutrient_totals["proteina_g"] == pytest.approx(10)          # total não muda
    assert r.nutrient_totals["sodio_mg"] == pytest.approx(3000)          # mineral, líquido não descartado
    assert r.nutrient_totals["agua_g"] == pytest.approx(980 - 400)       # só a água evaporou
    assert r.per100g()["proteina_g"] == pytest.approx(1 / 0.6)           # concentração sobe
    assert r.category("agua_g") == "derived"


# --------------------------------------------------------------------------- 4. sem fator
def test_nutrient_without_factor_is_unknown_not_zero(tiny):
    r = run(tiny, PreparedItem("carne", 500, "raw", method="boil", liquid="discarded"))
    assert "sodio_mg" in r.unknown_nutrients and "sodio_mg" not in r.nutrient_totals   # lixiviação possível
    assert "vitamina_c_mg" in r.unknown_nutrients                                       # não analisado no cru
    assert r.category("tiamina_mg") == "derived"
    r = run(tiny, PreparedItem("carne", 500, "raw", method="boil"))       # condição da regra não informada
    assert "tiamina_mg" in r.unknown_nutrients
    assert any("liquid" in w for w in r.warnings)


# --------------------------------------------------------------------------- 5. gordura
def test_fat_absorption_is_not_invented(tiny):
    r = run(tiny, PreparedItem("carne", 500, "raw", method="deep_fry"))
    assert r.nutrient_totals["lipideos_g"] == pytest.approx(50)           # só a gordura do próprio alimento
    assert r.category("lipideos_g") == "estimated"
    assert any("absorção de gordura" in w for w in r.warnings)
    ft = FatTransfer("sl:ingredient:oil", None, absorbed_g=12, lost_g=None, method="measured", source_food="oleo")
    r2 = run(tiny, PreparedItem("carne", 500, "raw", method="deep_fry", fat_transfer=ft))
    assert r2.nutrient_totals["lipideos_g"] == pytest.approx(62)
    assert r2.nutrient_totals["energia_kcal"] == pytest.approx(r.nutrient_totals["energia_kcal"] + 0.12 * 884)
    assert not any("absorção de gordura" in w for w in r2.warnings)


# --------------------------------------------------------------------------- 6. precedência
def test_measured_prepared_record_wins_over_estimate(tiny):
    r = run(tiny, PreparedItem("carne", 1000, "raw", method="grill"))
    assert r.path == "measured_prepared" and r.composition_food_id == "usda:2"
    assert r.cooked_mass_g == pytest.approx(800)
    assert r.nutrient_totals["proteina_g"] == pytest.approx(26 * 8)       # medido cozido × massa cozida
    assert r.category("proteina_g") == "derived"                          # massa veio do rendimento de tabela
    r = run(tiny, PreparedItem("carne", 1000, "raw", method="grill", cooked_mass_g=790))
    assert r.category("proteina_g") == "measured" and r.yield_status == "observed"
    assert r.nutrient_totals["proteina_g"] == pytest.approx(26 * 7.9)


# --------------------------------------------------------------------------- 7. fator de grupo
def test_group_factor_reports_low_confidence(tiny):
    r = run(tiny, PreparedItem("carne", 1000, "raw", method="roast_bake"))
    assert r.retention_factors and all(f.confidence == "low" for f in r.retention_factors)
    assert all(f.match_level == "group" for f in r.retention_factors)
    claims = [c for c in r.evidence_claims if c.predicate.startswith("retention:")]
    assert claims and all(c.confidence == "low" and c.limitations for c in claims)
    assert any("fator de grupo" in w for w in r.warnings)


# --------------------------------------------------------------------------- 8. receita e porções
def test_recipe_and_portion_totals_close(tiny):
    ndb, factors, cat = tiny
    items = [PreparedItem("carne", 1000, "raw", method="grill"),
             PreparedItem("caldo", 1000, "raw", method="reduce", cooked_mass_g=600, served_mass_g=300)]
    pr = prepared_recipe(ndb, items, portions=2, shares={"Ana": 500, "Bruno": 400}, factors=factors, catalog=cat)
    assert pr.served_mass_g == pytest.approx(800 + 300)
    a, b = (r.nutrient_totals["proteina_g"] for r in pr.items)
    assert b == pytest.approx(5)                                     # metade do lote reduzido foi servida
    assert pr.totals["proteina_g"] == pytest.approx(a + b)
    assert pr.per_portion["proteina_g"] * 2 == pytest.approx(pr.totals["proteina_g"])
    shared = pr.shares["Ana"]["proteina_g"] + pr.shares["Bruno"]["proteina_g"]
    assert shared + pr.totals["proteina_g"] * pr.leftover_mass_g / pr.served_mass_g == pytest.approx(pr.totals["proteina_g"])
    assert pr.total_category["proteina_g"] == "estimated"            # categoria mais fraca entre os itens
    assert "vitamina_c_mg" in pr.partial                             # conhecido num item, desconhecido no outro
    with pytest.raises(PreparedNutritionError):
        prepared_recipe(ndb, items, shares={"Ana": 2000}, factors=factors, catalog=cat)


def test_served_more_than_batch_is_rejected(tiny):
    with pytest.raises(PreparedNutritionError):
        run(tiny, PreparedItem("caldo", 1000, "raw", method="reduce", cooked_mass_g=600, served_mass_g=700))


def test_claims_are_valid_and_registered(tiny):
    registry = SourceRegistry.load()
    for item in (PreparedItem("carne", 1000, "raw", method="roast_bake"),
                 PreparedItem("carne", 1000, "raw", method="grill"),
                 PreparedItem("caldo", 1000, "raw", method="reduce", cooked_mass_g=600)):
        r = run(tiny, item)
        assert r.evidence_claims
        for c in r.evidence_claims:
            assert validate_claim(c, registry) == [], c


def test_unknown_method_raises(tiny):
    with pytest.raises(PreparedNutritionError):
        run(tiny, PreparedItem("carne", 100, "raw", method="teletransporte"))


# --------------------------------------------------------------------------- 10. compatibilidade
def test_recipe_api_unchanged_without_preparation(tiny):
    ndb, *_ = tiny
    r = ndb.recipe([{"nome": "carne", "quantidade": 200, "unidade": "g"}])
    assert r.prepared is None
    assert r.total["proteina_g"] == pytest.approx(40)
    assert "Nutrição após preparo" not in nutrition_section(r, ndb)


def test_recipe_with_preparation_columns_adds_prepared(tiny, monkeypatch):
    ndb, factors, cat = tiny
    import flavorlab.prepared_nutrition as pn
    monkeypatch.setattr(pn, "load_factors", lambda *a, **k: factors)
    monkeypatch.setattr(pn, "_default_catalog", lambda: cat)
    r = ndb.recipe([{"nome": "carne", "quantidade": 1, "unidade": "kg", "estado": "cru", "metodo": "grill"}], portions=4)
    assert r.total["proteina_g"] == pytest.approx(200)                    # cálculo antigo intacto (cru)
    assert r.prepared.items[0].path == "measured_prepared"
    assert r.prepared.per_portion["proteina_g"] == pytest.approx(26 * 8 / 4)
    html = nutrition_section(r, ndb)
    assert "Nutrição após preparo" in html and "<sup>D</sup>" in html


# --------------------------------------------------------------------------- 11. sem rede
def test_engine_makes_no_network_calls(tiny, monkeypatch):
    def blocked(*a, **k):
        raise AssertionError("chamada de rede")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    r = run(tiny, PreparedItem("carne", 1000, "raw", method="roast_bake"))
    assert r.path == "derived_from_raw"


# --------------------------------------------------------------------------- dados versionados
def test_factor_tables_are_consistent():
    f = Factors.load(FACTORS_DIR)
    assert len(f.retention) == 7018 and f.retention["retn_code"].nunique() == 270
    assert f.retention["factor"].dropna().between(0, 1).all()
    assert set(f.retention_map["retn_code"]) <= set(f.retention["retn_code"])
    assert f.yields["yield_pct"].between(20, 130).all()          # bacon no micro-ondas: 29%
    assert (f.yields["source_id"] == "usda_cooking_yields_r2").all()
    methods = set(f.methods["method_key"])
    assert set(f.retention_map["method_key"]) <= methods
    assert set(filter(None, f.yields["method_key"])) <= methods
    techniques = set(pd.read_csv(ROOT / "data" / "culinary" / "techniques.csv")["technique_id"])
    aliases = [a for col in ("technique_ids", "cooking_methods") for v in f.methods[col] for a in v.split("|") if a]
    assert len(aliases) == len(set(aliases))                       # cada alias aponta para um só método
    for row in f.methods.to_dict("records"):
        assert set(filter(None, row["technique_ids"].split("|"))) <= techniques
        assert set(filter(None, row["cooking_methods"].split("|"))) <= COOKING_METHODS.terms
    assert resolve_method("air_fryer", f) == resolve_method("air_fry", f) == "air_fry"


def test_build_check_is_clean():
    from scripts.build_cooking_factors import main
    assert main(["--check"]) == 0


def test_retention_map_entities_exist_in_catalog():
    from flavorlab.catalog import Catalog
    c = Catalog.load(with_inventory=False)
    rm = load_factors().retention_map
    assert all(m in c for m in rm["match"])
    assert set(rm["match_level"]) <= {"specific", "group"}


# --------------------------------------------------------------------------- banco real
@pytest.fixture(scope="module")
def real_ndb():
    if not REAL.exists():
        pytest.skip("banco nutricional não construído")
    return NutritionDB()


def test_real_raw_flank_with_known_yield(real_ndb):
    r = prepared_nutrition(real_ndb, PreparedItem("flank", 500, "raw", food_id="usda:169563", method="grill"))
    assert r.yield_factor.factor == pytest.approx(0.81) and r.yield_factor.reference.startswith("usda_cy2:13948")
    assert r.cooked_mass_g == pytest.approx(405)
    assert r.composition_food_id == "usda:168733"                  # cozido medido do mesmo estudo
    assert r.retention_factors == []


def test_real_fraldinha_served_without_raw_weight(real_ndb):
    r = prepared_nutrition(real_ndb, PreparedItem("fraldinha", 350, "served", food_id="taco:361",
                                                  method="air_fryer", instance_id="FRALDINHA_001:fraldinha"))
    assert r.initial_mass_g is None and r.yield_factor is None
    assert r.yield_status == "not_reconstructible"
    assert r.served_mass_g == 350 and r.composition_food_id == "taco:361"
    assert r.method_match == "different" and not r.measured_values   # cozida em água ≠ air fryer
    assert r.estimated_values["proteina_g"] == pytest.approx(
        real_ndb.matrix.loc["taco:361", "proteina_g"] * 3.5)
    assert "usda" not in " ".join(c.value for c in r.evidence_claims if c.predicate == "composition_record")
    assert any("rendimento não reconstruído" in w for w in r.warnings)


def test_real_frying_without_absorption_warns(real_ndb):
    r = prepared_nutrition(real_ndb, PreparedItem("batata", 500, "raw", food_id="taco:92", method="deep_fry"))
    assert r.path == "derived_from_raw"
    assert any("absorção de gordura" in w for w in r.warnings)
    assert r.category("lipideos_g") == "estimated"
    assert r.retention_factors and all(f.retn_code == "3315" for f in r.retention_factors)


def test_real_rice_absorption_is_water(real_ndb):
    r = prepared_nutrition(real_ndb, PreparedItem("arroz", 200, "raw", food_id="taco:4", method="boil",
                                                  liquid="consumed", cooked_mass_g=560))
    raw = real_ndb.matrix.loc["taco:4"]
    assert r.nutrient_totals["agua_g"] == pytest.approx(raw["agua_g"] * 2 + 360)
    assert r.nutrient_totals["proteina_g"] == pytest.approx(raw["proteina_g"] * 2)
    assert {f.retn_code for f in r.retention_factors} == {"0432"}


def test_raw_factor_files_match_documented_hashes():
    import hashlib
    import re
    doc = (FACTORS_DIR / "SOURCES.md").read_text(encoding="utf-8")
    pairs = re.findall(r"- `([^`]+)` — `([0-9a-f]{64})`", doc)
    assert len(pairs) == 3
    for name, digest in pairs:
        data = (ROOT / "data" / "raw" / "usda_factors" / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest, name
