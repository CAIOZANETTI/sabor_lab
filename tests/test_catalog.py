"""Catálogo canônico de alimentos (demanda 002).

Os números nos nomes dos testes seguem a seção "Validações e testes" da demanda.
A maior parte roda sobre os dados reais (data/catalog + tabelas processadas);
testes de regras de validação usam cópias sintéticas modificadas em tmp_path.
"""

from __future__ import annotations

import importlib.util
import shutil

import pandas as pd
import pytest

from conftest import ROOT
from flavorlab.catalog import (CATALOG_DIR, CONFIDENCE_THRESHOLD, ID_RE, LEDGER_STATUSES, MAPPED_STATUSES,
                               Catalog, kind_of)
from flavorlab.catalog_mapping import (Matcher, build_inventory, check_no_loss, coverage_report,
                                       load_source_records, tokens)

PROCESSED = ROOT / "data" / "processed"
if not (PROCESSED / "nutrition" / "foods.parquet").exists() or not (PROCESSED / "ingredients.parquet").exists():
    pytest.skip("bancos processados ausentes", allow_module_level=True)


@pytest.fixture(scope="module")
def cat() -> Catalog:
    return Catalog.load()


@pytest.fixture(scope="module")
def records() -> pd.DataFrame:
    return load_source_records()


@pytest.fixture(scope="module")
def inv(cat) -> pd.DataFrame:
    return cat.inventory


def _copy_catalog(tmp_path):
    dst = tmp_path / "catalog"
    shutil.copytree(CATALOG_DIR, dst)
    return dst


def _edit_csv(path, fn):
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df = fn(df)
    df.to_csv(path, index=False)


# --------------------------------------------------------------------------- 1, 2, 3, 4, 10
def test_01_ids_unique_stable_format(cat):
    ids = (list(cat.groups) + list(cat.taxa) + list(cat.concepts) + list(cat.variant_rows)
           + list(cat.part_rows) + list(cat.form_rows))
    assert len(ids) == len(set(ids))
    assert all(ID_RE.match(i) for i in ids)
    # IDs canônicos nunca embutem ID de fonte nem índice de linha
    assert not any(":taco" in i or ":usda" in i or i.rsplit(":", 1)[1].isdigit() for i in ids)


def test_02_catalog_is_valid_no_missing_parent_no_cycle(cat, records):
    assert cat.validate(records) == []


def test_02_validation_detects_cycle_and_missing_parent(tmp_path):
    d = _copy_catalog(tmp_path)

    def make_cycle(df):
        df.loc[df.concept_id == "sl:ingredient:cereal_grains", "parent_id"] = "sl:ingredient:rice"
        df.loc[df.concept_id == "sl:ingredient:fish", "parent_id"] = "sl:ingredient:does_not_exist"
        return df
    _edit_csv(d / "ingredient_concepts.csv", make_cycle)
    errors = Catalog.load(d, with_inventory=False).validate()
    assert any("ciclo" in e for e in errors)
    assert any("pai inexistente" in e for e in errors)


def test_03_mappings_point_to_existing_source_records(cat, records):
    keys = set(zip(records["source"], records["source_id"]))
    assert {m.source for m in cat.curated_mappings} == {"taco", "usda", "flavordb", "flavorgraph"}
    missing = [(m.source, m.source_id) for m in cat.curated_mappings if (m.source, m.source_id) not in keys]
    assert missing == []


def test_03_validation_rejects_unknown_source_record(tmp_path, records):
    d = _copy_catalog(tmp_path)
    _edit_csv(d / "source_mappings.csv", lambda df: pd.concat(
        [df, df.head(1).assign(source_id="99999999")], ignore_index=True))
    errors = Catalog.load(d, with_inventory=False).validate(records)
    assert any("registro inexistente" in e for e in errors)


def test_04_form_cannot_be_parent_of_concept(tmp_path):
    d = _copy_catalog(tmp_path)
    _edit_csv(d / "ingredient_concepts.csv", lambda df: df.assign(parent_id=df.parent_id.where(
        df.concept_id != "sl:ingredient:rice_flour", "sl:form:rice_white_raw")))
    errors = Catalog.load(d, with_inventory=False).validate()
    assert any("não é conceito" in e for e in errors)


def test_10_every_external_row_has_source_version_license(cat, inv):
    src = cat.sources
    assert not (src[["source", "dataset", "version", "license", "url"]] == "").any().any()
    assert set(inv["source_dataset"]) <= set(src["dataset"])
    assert set(inv["source"]) <= set(src["source"])
    assert {m.source for m in cat.curated_mappings} <= set(src["source"])
    assert all(m.evidence and m.curated_by for m in cat.curated_mappings)


# --------------------------------------------------------------------------- 5, 6, 7, 8, 13, 14
def test_05_dishes_are_not_variants(cat):
    dishes = {c for c, row in cat.concepts.items() if row.entity_type == "dish"}
    assert dishes, "o catálogo deve ter pratos de referência"
    for d in dishes:
        parent = cat.concepts[d].parent_id
        assert not parent or cat.concepts[parent].entity_type in {"dish", "category"}
        assert all(cat.concepts[a].entity_type != "ingredient" for a in cat.ancestors(d))
    # risoto e arroz carreteiro contêm arroz, mas não são variedades/descendentes de arroz
    rice_desc = set(cat.descendants("sl:ingredient:rice"))
    assert "sl:ingredient:risotto" not in rice_desc and "sl:ingredient:arroz_carreteiro" not in rice_desc
    contains = {(r.subject_id, r.object_id) for r in cat.relations(predicate="dish_contains")}
    assert ("sl:ingredient:arroz_carreteiro", "sl:ingredient:rice") in contains
    assert all(cat.concepts[v.concept_id].entity_type != "dish" or v.variant_kind for v in cat.variant_rows.values())


def test_05_validation_rejects_dish_under_ingredient(tmp_path):
    d = _copy_catalog(tmp_path)
    _edit_csv(d / "ingredient_concepts.csv", lambda df: df.assign(parent_id=df.parent_id.where(
        df.concept_id != "sl:ingredient:risotto", "sl:ingredient:rice")))
    errors = Catalog.load(d, with_inventory=False).validate()
    assert any("prato não pode ser subtipo" in e for e in errors)


def test_06_brown_rice_is_processing_not_cultivar(cat):
    variants = cat.variants("sl:ingredient:rice")
    names = " ".join(f"{v.name_pt} {v.name_en}".lower() for v in variants)
    assert "integral" not in names and "brown" not in names and "parboil" not in names
    assert all(v.variant_kind != "cultivar" or v.biological_rank in {"cultivar", "cultivar_group"} for v in variants)
    brown = cat.get("sl:form:rice_brown_raw")
    assert "whole_grain" in brown.preparation and brown.variant_id == ""
    assert cat.resolve_source("taco", "2").entity_id == "sl:form:rice_brown_raw"   # Arroz, integral, cru
    parboiled = cat.get("sl:form:rice_long_grain_parboiled_raw")
    assert "parboiled" in parboiled.preparation
    # arroz-selvagem não é variedade de arroz (outro gênero)
    assert cat.concepts["sl:ingredient:wild_rice"].scientific_taxon_id != cat.concepts["sl:ingredient:rice"].scientific_taxon_id
    assert "sl:ingredient:wild_rice" not in cat.descendants("sl:ingredient:rice")


def test_07_parmesan_connects_flavor_and_nutrition(cat):
    parm = "sl:variant:cheese_parmesan"
    ids = [parm] + cat.descendants(parm)
    sources = {m.source for e in ids for m in cat.mappings(e)}
    assert {"taco", "usda", "flavordb", "flavorgraph"} <= sources
    assert cat.resolve_source("taco", "464").entity_id == parm
    assert cat.resolve_source("fdb", "78").entity_id == parm
    assert cat.resolve_source("usda", "171247").entity_id == "sl:form:cheese_parmesan_grated"


def test_08_black_bean_raw_and_cooked_are_distinct_under_one_variant(cat):
    raw, cooked = cat.resolve_source("taco", "568"), cat.resolve_source("taco", "567")
    assert raw.entity_id == "sl:form:common_bean_black_raw"
    assert cooked.entity_id == "sl:form:common_bean_black_cooked"
    r, c = cat.get(raw.entity_id), cat.get(cooked.entity_id)
    assert r.state == "raw" and c.state == "cooked"
    assert r.variant_id == c.variant_id == "sl:variant:common_bean_black"
    assert cat.get(r.variant_id).concept_id == "sl:ingredient:common_bean"
    assert cat.concepts["sl:ingredient:common_bean"].scientific_taxon_id == "sl:taxon:phaseolus_vulgaris"
    # USDA cru também resolve para a forma crua, e o canned é outra forma
    assert cat.resolve_source("usda", "173734").entity_id == raw.entity_id
    assert cat.resolve_source("usda", "2644285").entity_id == "sl:form:common_bean_black_canned"


def test_13_popcorn_is_a_corn_type_not_a_dish_nor_corn_synonym(cat, inv):
    pop = cat.get("sl:variant:corn_popcorn")
    assert pop.concept_id == "sl:ingredient:corn" and pop.variant_kind == "culinary_type"
    assert "popcorn" not in cat.concepts["sl:ingredient:corn"].aliases_en.lower()
    popped = cat.get("sl:form:corn_popcorn_popped")
    assert popped.variant_id == pop.variant_id and popped.physical_form == "popped"
    assert cat.food_group(pop.variant_id) == "sl:group:cereals"
    for key in ("fg:4958", "fdb:58", "taco:61"):
        res = cat.resolve_source(*key.split(":"))
        assert res.entity_id in {pop.variant_id, popped.form_id, "sl:form:corn_popcorn_popped_oil"}
        assert cat.concepts[cat.concept_of(res.entity_id)].entity_type != "dish"
    # o pipeline não trata "popcorn chicken" como milho
    assert cat.resolve_source("usda", "170737").entity_id == ""


def test_14_cuts_are_parts_not_biological_varieties(cat):
    cut_words = ("fillet", "filé", "picanha", "breast", "peito", "loin", "lombo", "chuck", "posta", "steak")
    for v in cat.variant_rows.values():
        group = cat.food_group(v.variant_id)
        if group in {"sl:group:meat", "sl:group:poultry", "sl:group:seafood"}:
            text = f"{v.name_pt} {v.name_en}".lower()
            assert not any(w in text for w in cut_words), v.variant_id
    assert cat.get("sl:part:beef_picanha").anatomical_or_botanical_part == "cut"
    assert cat.get("sl:part:atlantic_salmon_fillet").concept_id == "sl:ingredient:atlantic_salmon"
    assert {p.part_id for p in cat.parts("sl:ingredient:chicken")} >= {"sl:part:chicken_breast", "sl:part:chicken_thigh"}
    assert cat.resolve_source("taco", "409").entity_id == "sl:form:chicken_breast_skinless_raw"


# --------------------------------------------------------------------------- 9, 11, 12, 15
def test_09_low_confidence_mapping_requires_review(cat, inv):
    conf = pd.to_numeric(inv["confidence"], errors="coerce")
    low = inv[conf < CONFIDENCE_THRESHOLD]
    assert not low["status"].isin(["mapped_high_confidence"]).any()
    assert not low[low["rule"] != "curated"]["status"].isin(["mapped_reviewed"]).any()
    high = inv[inv["status"] == "mapped_high_confidence"]
    assert (pd.to_numeric(high["confidence"]) >= CONFIDENCE_THRESHOLD).all()
    # resolução expõe a necessidade de revisão
    res = cat.resolve_source("taco", "125")  # broto de feijão: espécie não informada
    assert res.status == "mapped_low_confidence" and res.needs_review
    assert all(m.needs_review for m in cat.curated_mappings if m.confidence < CONFIDENCE_THRESHOLD)


def test_11_every_source_record_is_in_the_ledger(records, inv):
    assert len(inv) == len(records) == 597 + 8229 + 935 + 6653
    assert set(zip(inv.source, inv.source_id)) == set(zip(records.source, records.source_id))
    assert set(inv["status"]) <= set(LEDGER_STATUSES)
    assert (inv["status"] != "").all() and (inv["rule"] != "").all()
    # não mapeados preservados com motivo
    assert (inv.loc[inv.status.isin(["unmapped", "ambiguous", "excluded_with_reason"]), "reason"] != "").all()


def test_11_ledger_is_reproducible(cat, records, inv):
    rebuilt = build_inventory(Catalog.load(with_inventory=False), records)
    pd.testing.assert_frame_equal(rebuilt.astype(str), inv.astype(str), check_dtype=False)


def test_11_check_no_loss_flags_missing_records(inv):
    assert check_no_loss(inv, inv) == []
    lost = check_no_loss(inv, inv.iloc[1:])
    assert lost == [f"{inv.iloc[0].source}:{inv.iloc[0].source_id}"]


def test_11_build_script_check_mode():
    spec = importlib.util.spec_from_file_location("build_catalog", ROOT / "scripts" / "build_catalog.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--check"]) == 0


def test_12_ambiguous_fish_market_names_never_become_species(cat, inv):
    for c in cat.concepts.values():
        if c.entity_type == "market_name":
            assert c.scientific_taxon_id == ""
    for key, concept in [("taco:304", "sl:ingredient:pescada"), ("taco:283", "sl:ingredient:dogfish_cacao"),
                         ("taco:279", "sl:ingredient:bacalhau"), ("taco:316", "sl:ingredient:salmon")]:
        res = cat.resolve_source(*key.split(":"))
        assert cat.concept_of(res.entity_id) == concept
        assert cat.concepts[concept].scientific_taxon_id == ""
    # "mixed species" do USDA nunca resolve para uma espécie
    mixed = inv[inv.original_description.str.contains("mixed species", case=False) & inv.entity_id.ne("")]
    for eid in mixed.entity_id:
        c = cat.concepts[cat.concept_of(eid)]
        taxon = c.scientific_taxon_id
        assert not taxon or cat.taxa[taxon].rank != "species", eid
    # salmão do Atlântico só quando a fonte diz "Atlantic"
    assert cat.resolve_source("usda", "173686").entity_id.startswith("sl:form:atlantic_salmon")


def test_12_shared_alias_stays_ambiguous_with_candidates(cat):
    res = cat.resolve_source("fg", "7043")  # "yam": cará (Dioscorea) ou batata-doce (uso nos EUA)
    assert res.status == "ambiguous" and res.entity_id == ""
    assert {e for e, _ in res.candidates} == {"sl:ingredient:yam", "sl:ingredient:sweet_potato"}


def test_15_coverage_counts_by_group_source_status(cat, inv):
    cov = cat.coverage()
    assert set(cov.columns) == {"source", "food_group", "status", "records"}
    assert cov["records"].sum() == len(inv)
    by_src = cat.coverage(by=["source"]).set_index("source")["records"]
    assert by_src.to_dict() == {"flavordb": 935, "flavorgraph": 6653, "taco": 597, "usda": 8229}
    assert cat.coverage(source="taco", status="mapped_high_confidence")["records"].sum() > 500
    report = coverage_report(cat, inv)
    for heading in ("## Por fonte", "## Por grupo alimentar", "## Por idioma", "## Confiança"):
        assert heading in report
    assert (ROOT / "reports" / "catalog_coverage.md").read_text(encoding="utf-8") == report


# --------------------------------------------------------------------------- amostra curada
def test_curated_reference_set_is_distributed(cat):
    entities = list(cat.concepts) + list(cat.variant_rows) + list(cat.part_rows) + list(cat.form_rows)
    assert len(entities) >= 200
    groups = pd.Series([cat.food_group(e) for e in entities]).value_counts()
    assert set(groups.index) == set(cat.groups)            # todos os 19 grupos
    assert groups.max() / groups.sum() < 0.2               # nenhum grupo concentra a amostra


def test_cheese_rice_beans_corn_fish_minimums(cat):
    cheeses = [v for v in cat.variants("sl:ingredient:cheese") if cat.mappings(v.variant_id)
               or any(cat.mappings(f.form_id) for f in cat.forms(v.variant_id))]
    assert len(cheeses) >= 25
    for v in cheeses:
        attrs = dict(a.split("=", 1) for a in v.attributes.split(";") if "=" in a)
        assert "milk" in attrs and "family" in attrs
    rice = ["sl:ingredient:rice"] + cat.descendants("sl:ingredient:rice")
    assert len(rice) >= 15
    beans = [e for c in cat.descendants("sl:ingredient:bean") for e in [c] + cat.descendants(c)]
    assert len(beans) >= 15
    assert {"sl:variant:common_bean_carioca", "sl:variant:common_bean_black", "sl:variant:cowpea_blackeyed",
            "sl:ingredient:adzuki_bean", "sl:ingredient:mung_bean", "sl:ingredient:lima_bean"} <= set(beans)
    corn = set(cat.descendants("sl:ingredient:corn"))
    assert {"sl:variant:corn_sweet", "sl:variant:corn_popcorn", "sl:form:corn_green_raw"} <= corn
    derived = {r.subject_id for r in cat.relations(predicate="derived_from") if r.object_id == "sl:ingredient:corn"}
    assert {"sl:ingredient:cornmeal", "sl:ingredient:corn_starch", "sl:ingredient:corn_oil", "sl:ingredient:hominy"} <= derived
    fish = cat.search_by_category("sl:group:seafood")
    states = {cat.get(e).state for e in fish if kind_of(e) == "form"}
    assert {"raw", "cooked", "smoked", "dried", "canned"} <= states


# --------------------------------------------------------------------------- API
def test_api_navigation(cat):
    assert cat.get("sl:ingredient:rice").canonical_name_pt == "arroz"
    with pytest.raises(KeyError):
        cat.get("sl:ingredient:nao_existe")
    assert "sl:variant:rice_basmati" in cat.children("sl:ingredient:rice")
    assert "sl:ingredient:rice" in cat.children("sl:ingredient:cereal_grains")
    assert [f.form_id for f in cat.forms("sl:variant:rice_basmati")] == ["sl:form:rice_basmati_cooked", "sl:form:rice_basmati_raw"]
    assert "sl:form:rice_brown_raw" in [f.form_id for f in cat.forms("sl:ingredient:rice")]
    assert cat.parts("sl:ingredient:rice") == []
    assert cat.ancestors("sl:form:rice_basmati_raw") == ["sl:variant:rice_basmati", "sl:ingredient:rice",
                                                         "sl:ingredient:cereal_grains"]
    assert "sl:variant:cheese_parmesan" in cat.search_by_category("sl:ingredient:cheese")
    assert "sl:ingredient:salmon" in cat.search_by_category("sl:group:seafood")


def test_api_resolve_and_mappings(cat):
    res = cat.resolve_source("taco", "taco:568")       # aceita id com prefixo
    assert res.is_mapped and not res.needs_review and res.rule == "curated"
    assert cat.resolve_source("taco", "999999").status == "unmapped"
    curated_only = cat.mappings("sl:form:common_bean_black_raw", include_auto=False)
    assert {m.source for m in curated_only} == {"taco", "usda"}
    assert cat.mappings("sl:form:common_bean_black_raw", source="usda")[0].source_id == "173734"
    auto = [m for m in cat.mappings("sl:part:beef_chuck") if m.rule != "curated"]
    assert auto and {"usda", "flavorgraph"} <= {m.source for m in auto}


def test_api_relations_and_structural_predicates(cat):
    preds = {r.predicate for r in cat.relations("sl:ingredient:corn")}
    assert {"is_a", "taxon_of", "variant_of", "derived_from"} <= preds
    assert any(r.predicate == "part_of" for r in cat.relations("sl:part:beef_picanha"))
    assert any(r.predicate == "form_of" for r in cat.relations("sl:form:rice_brown_raw"))
    # substitutable_with só com contexto e evidência
    for r in cat.relations(predicate="substitutable_with"):
        assert r.context and r.evidence


def test_matcher_rules_are_conservative(cat):
    m = Matcher(Catalog.load(with_inventory=False))
    assert m.match("Rice flour, white", "en", True)["entity_id"] == "sl:ingredient:rice_flour"
    assert m.match("rice_flour", "en", False)["entity_id"] == "sl:ingredient:rice_flour"
    assert m.match("Peanut butter, smooth", "en", True).get("entity_id") != "sl:ingredient:butter"
    assert m.match("Fat, beef tallow", "en", True).get("entity_id") != "sl:ingredient:beef"
    assert m.match("Fish, sablefish, raw", "en", True)["status"] == "unmapped"          # só a categoria
    assert m.match("corn_salad", "en", False)["entity_id"] == "sl:ingredient:corn_salad"
    assert m.match("Caju, suco concentrado, envasado", "pt", True)["status"] == "unmapped"
    vegan = m.match("vegan_parmesan_cheese", "en", False)
    assert vegan["confidence"] < CONFIDENCE_THRESHOLD
    assert tokens("Feijão, preto, cru") == ["feijao", "preto", "cru"]


def test_ledger_statuses_map_to_entities(cat, inv):
    mapped = inv[inv.status.isin(MAPPED_STATUSES)]
    assert mapped.entity_id.map(lambda e: e in cat).all()
    unmapped = inv[~inv.status.isin(MAPPED_STATUSES)]
    assert (unmapped.entity_id == "").all()
