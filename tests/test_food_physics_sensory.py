"""Física de alimentos, estabilidade, sensorial e textura (demanda 006).

Os números nos nomes seguem os testes obrigatórios da demanda.
"""

from __future__ import annotations

import pytest

from flavorlab.catalog import Catalog
from flavorlab.evidence import EvidenceStore, SourceRegistry, new_claim
from flavorlab.food_physics import (Preparation, assess_stability, build_component, composition_claims,
                                    load_entity_facts, load_stability_rules, validate_stability_rules)
from flavorlab.process import CulinaryKnowledge
from flavorlab.sensory import (EVIDENCE_CATEGORIES, TASTE_AXES, SensoryComponent, aroma_evidence, assess,
                               load_sensory_rules, pair_metrics, validate_sensory_rules)
from flavorlab.states import state_from_claims
from flavorlab.texture import (TEXTURE_TERMS, TextureAttribute, expected_textures, load_texture_rules, observed_textures, status_of,
                               texture_profile)
from flavorlab.transformations import (ProcessConditions, analyze_transformations, by_id, composition_from_claims,
                                       load_rules, validate_rules)


@pytest.fixture(scope="module")
def catalog():
    return Catalog.load(with_inventory=False)


@pytest.fixture(scope="module")
def knowledge():
    return CulinaryKnowledge.load()


@pytest.fixture(scope="module")
def sauce(catalog):
    """Cebola dourada, alho, queijo azul (Dana Blue, composição não verificada), kefir e manteiga."""
    comps = [build_component("onion", "sl:ingredient:onion", "cebola dourada", catalog),
             build_component("garlic", "sl:ingredient:garlic", "alho", catalog),
             build_component("blue", "sl:variant:cheese_blue", "queijo Dana Blue", catalog, specific_product=True),
             build_component("kefir", "sl:ingredient:kefir", "kefir de leite", catalog),
             build_component("butter", "sl:ingredient:butter", "manteiga", catalog)]
    return Preparation("molho_azul_kefir", comps, heat="unknown")


def onion_composition(catalog):
    return composition_from_claims(composition_claims("sl:ingredient:onion", catalog))


# --------------------------------------------------------------------------- 1, 2, 3
def test_01_possible_differs_from_observed(catalog):
    inst = "user:cebola_001"
    comp = onion_composition(catalog)
    cond = ProcessConditions(medium="fat")
    possible = by_id(analyze_transformations(None, "saute", cond, composition=comp))["maillard_reaction"]
    assert possible.status == "possible"
    state = state_from_claims(inst, "sl:ingredient:onion", "cebola", [])
    seen = new_claim(claim_id="obs1", subject_id=inst, predicate="transformation_observed", value="maillard_reaction",
                     unit=None, evidence_type="human_observation", confidence="qualitative", method="cor dourada vista")
    observed = by_id(analyze_transformations(state, "saute", cond, composition=comp, observations=[seen]))
    assert observed["maillard_reaction"].status == "observed"
    assert observed["caramelization"].status != "observed"           # observar uma não observa outra
    assert possible.to_claim("x").evidence_type == "unvalidated_hypothesis"


def test_02_missing_temperature_downgrades_without_creating_values(catalog):
    comp = onion_composition(catalog)
    full = by_id(analyze_transformations(None, "saute", ProcessConditions(medium="fat", temperature_c=150,
                                                                          duration_s=600), composition=comp))
    partial = by_id(analyze_transformations(None, "saute", ProcessConditions(medium="fat", duration_s=600),
                                            composition=comp))
    assert full["maillard_reaction"].status == "likely"
    assert partial["maillard_reaction"].status == "possible"
    assert "temperature_c" not in partial["maillard_reaction"].provided_conditions
    assert any("mr_temp" in m for m in partial["maillard_reaction"].missing)


def test_03_evaporation_does_not_imply_caramelization(catalog):
    comp = composition_from_claims(composition_claims("sl:ingredient:tomato", catalog))
    res = by_id(analyze_transformations(None, "simmer_reduce", ProcessConditions(medium="moist", temperature_c=100,
                                                                                  duration_s=1800), composition=comp))
    assert res["evaporation_reduction"].status == "likely"
    assert res["caramelization"].status == "unsupported"
    # mesmo com técnica que permite caramelização, meio aquoso é inibidor e sem temperatura fica só possível
    bake = by_id(analyze_transformations(None, "bake", ProcessConditions(medium="moist"),
                                         composition={"has_sugar": True, "has_water": True}))
    assert bake["caramelization"].status == "possible"
    assert any("cr_water_cap" in i for i in bake["caramelization"].inhibitors)


# --------------------------------------------------------------------------- 4, 5, 6
def test_04_kefir_cheese_sauce_returns_risks_and_alternatives(sauce):
    a = assess_stability(sauce)
    risk_ids = {r["rule_id"] for r in a.risks}
    assert {"st_risk_fermented_heat", "st_risk_casein_ph", "st_risk_cheese_clumps", "st_risk_acid_fat"} <= risk_ids
    assert any("separação" in r["statement"] for r in a.risks)                    # separação de fases
    assert any("agregar" in r["statement"] for r in a.risks)                      # coagulação/agregação
    heat_risks = [r for r in a.risks if r["rule_id"] in {"st_risk_fermented_heat", "st_risk_cheese_clumps"}]
    assert all(r["applicability"].startswith("possível") for r in heat_risks)    # calor desconhecido: não é certeza
    assert len(a.sequence_options) >= 3
    assert {s["relative_risk"] for s in a.sequence_options} == {"lower", "higher"}
    assert len(a.alternatives) >= 4 and all(alt["evidence_type"] in {"documented_physical_rule", "culinary_heuristic"}
                                            for alt in a.alternatives)
    assert a.confidence == "qualitative"
    assert "certeza" in a.certainty_note
    assert any("Dana Blue" in m for m in a.missing_measurements)
    assert a.protective_factors == []                                              # nada protege sem estar presente


def test_05_boiling_kefir_is_not_a_default_recommendation(sauce):
    a = assess_stability(sauce)
    for rec in a.recommendations():
        if "ferv" in rec.lower():
            assert "não" in rec.lower()
    boiled = next(s for s in a.sequence_options if s["rule_id"] == "seq_kefir_boiled")
    assert boiled["relative_risk"] == "higher" and "não recomendada" in boiled["recommendation"]
    boil = assess_stability(Preparation("p", sauce.components, heat="boil"))
    assert any(r["rule_id"] == "st_risk_boil_kefir" and r["applicability"] == "aplicável" for r in boil.risks)


def test_06_missing_ph_stays_unknown(sauce):
    a = assess_stability(sauce)
    assert sauce.ph is None
    assert any("pH" in m for m in a.missing_measurements)
    kefir_facts = [c for c in sauce.components if c.component_id == "kefir"][0].claims
    assert not any(c.predicate == "ph" for c in kefir_facts)                      # pH não foi criado
    ph_claim = next(c for c in kefir_facts if c.predicate == "is_acidified")
    assert ph_claim.source_id == "porto_fett_2026_kefir" and "desconhecido" in ph_claim.limitations


# --------------------------------------------------------------------------- 7, 8
def test_07_molecule_descriptor_preference_stay_separate(tiny_db):
    ev = aroma_evidence(tiny_db, "fg:1")
    cats = {e.category for e in ev}
    assert cats == {"molecule_presence", "molecule_descriptor"}
    assert all("percep" in e.note or "não indica" in e.note for e in ev)           # presença ≠ percepção
    pref = new_claim(claim_id="p1", subject_id="dish", predicate="likes", value="canela", unit=None,
                     evidence_type="user_preference", confidence="qualitative", method="relato")
    comp = SensoryComponent("c", "sl:ingredient:cinnamon", "main", preferences=[pref])
    res = assess([comp], rules=[])
    assert res.preferences and res.preferences[0]["category"] == "user_preference"
    assert not res.dominant_attributes                                             # preferência não vira atributo
    assert set(EVIDENCE_CATEGORIES) == {"molecule_presence", "molecule_descriptor", "inferred_property",
                                        "human_observation", "user_preference"}


def test_08_npmi_zero_is_not_incompatibility(tiny_db):
    m = pair_metrics(tiny_db, "fg:3", "fg:4")       # sem co-ocorrência registrada
    assert m["incompatible"] is None
    assert "não implica incompatibilidade" in m["npmi_interpretation"]
    known = pair_metrics(tiny_db, "fg:1", "fg:2")
    assert known["npmi"] == pytest.approx(0.4) and known["jaccard"] == pytest.approx(0.5)
    assert "não preferência" in known["npmi_interpretation"]


# --------------------------------------------------------------------------- 9, 10
def test_09_expected_texture_never_becomes_observed():
    exp = expected_textures("air_fry", "inst:1")
    assert exp and all(t.status == "expected" for t in exp)
    profile = texture_profile([], exp)
    assert status_of("crocante", profile) == "expected"
    inst = "user:fraldinha_001"
    state = state_from_claims(inst, "sl:part:beef_fraldinha", "fraldinha", [new_claim(
        claim_id="t1", subject_id=inst, predicate="texture_attribute", value="suculenta", unit=None,
        evidence_type="human_observation", confidence="qualitative", method="relato")])
    store = EvidenceStore([new_claim(claim_id="t1", subject_id=inst, predicate="texture_attribute", value="suculenta",
                                     unit=None, evidence_type="human_observation", confidence="qualitative",
                                     method="relato")])
    obs = observed_textures(state, store)
    assert [(t.term, t.status) for t in obs] == [("suculento", "observed")]
    assert status_of("crocante", texture_profile(obs, [])) == "unknown"


def test_10_crunchy_contrast_is_an_explainable_opportunity(catalog):
    inst = "user:fraldinha_001"
    meat_obs = [TextureAttribute("suculento", "observed", inst, "relato", None, "qualitative", "t1"),
                TextureAttribute("macio", "observed", inst, "relato", None, "qualitative", "t2")]
    sauce_exp = expected_textures("gentle_heat", "molho", "sl:group:dairy")
    comps = [SensoryComponent("fraldinha", "sl:part:beef_fraldinha", "main", "sl:group:meat", textures=meat_obs,
                              ancestors=tuple(catalog.ancestors("sl:part:beef_fraldinha"))),
             SensoryComponent("molho_azul", "sl:variant:cheese_blue", "sauce", "sl:group:dairy", textures=sauce_exp,
                              ancestors=tuple(catalog.ancestors("sl:variant:cheese_blue"))),
             SensoryComponent("kefir", "sl:ingredient:kefir", "sauce", "sl:group:dairy"),
             SensoryComponent("manteiga", "sl:ingredient:butter", "sauce", "sl:group:dairy")]
    res = assess(comps)
    crunchy = [o for o in res.contrast_opportunities if "crocante" in o["opportunity"]]
    assert crunchy and crunchy[0]["kind"] == "oportunidade, não requisito"
    assert crunchy[0]["evidence_type"] == "culinary_heuristic" and crunchy[0]["limitations"]
    assert set(crunchy[0]["because"]) >= {"macio", "suculento"}
    assert status_of("cremoso", res.texture_profile) == "expected"                 # objetivo do molho
    assert status_of("suculento", res.texture_profile) == "observed"               # observação da carne
    fat = [e for e in res.possible_excesses if e["attribute"] == "sensacao_de_gordura"]
    assert fat and "desconhecidas" in fat[0]["note"]                                # depende da composição
    acid = [d for d in res.dominant_attributes + res.supporting_attributes if d["attribute"] == "acido"]
    assert acid and "kefir" in acid[0]["contributors"]                             # acidez provável, sem pH
    assert not any("ph" in str(e).lower() and "valor" in str(e).lower() for e in res.evidence)
    assert any("picancia" in u for u in res.unknowns)


# --------------------------------------------------------------------------- 11
def test_11_every_rule_has_source_or_explicit_heuristic(knowledge):
    sources = knowledge.sources
    assert validate_rules(load_rules(), knowledge) == []
    assert validate_stability_rules(load_stability_rules(), sources) == []
    assert validate_sensory_rules(load_sensory_rules(), sources) == []
    for r in load_texture_rules():
        assert r.source_id in sources and r.evidence_type in {"documented_physical_rule", "culinary_heuristic"}
        assert r.term in TEXTURE_TERMS and r.technique_id in knowledge.techniques
        if r.evidence_type == "culinary_heuristic":
            assert r.limitations
    for f in load_entity_facts():
        assert f.source_id in sources and f.evidence_type in {"documented_physical_rule", "culinary_heuristic"}
    internal = {s.source_id for s in sources if s.source_type == "internal"}
    for r in load_stability_rules() + load_rules():
        if r.source_id in internal:
            assert r.evidence_type == "culinary_heuristic"
    assert knowledge.validate() == []
    for tid in ("lipid_oxidation", "moisture_loss_softening", "phase_separation"):
        assert tid in knowledge.transformations


def test_axes_and_vocabularies_match_spec():
    assert TASTE_AXES == ("doce", "salgado", "acido", "amargo", "umami", "picancia", "adstringencia",
                          "sensacao_de_gordura")
    assert TEXTURE_TERMS == ("macio", "crocante", "cremoso", "suculento", "fibroso", "firme", "granuloso", "viscoso")


def test_composition_uses_official_table_with_limitations(catalog):
    claims = composition_claims("sl:variant:cheese_blue", catalog)
    assert {c.predicate for c in claims} >= {"has_fat", "has_protein"}
    assert all(c.evidence_type == "official_food_table" and c.source_id == "usda_sr_legacy" for c in claims)
    assert all("pode diferir" in c.limitations for c in claims)
    assert composition_claims("sl:ingredient:cereal_grains", catalog) == []        # categoria sem tabela: desconhecido


def test_phase_separation_needs_a_dairy_or_emulsion_system(catalog):
    comp = onion_composition(catalog)
    res = by_id(analyze_transformations(None, "saute", ProcessConditions(medium="fat", temperature_c=150, duration_s=600),
                                        composition=comp, food_group="sl:group:vegetables"))
    assert res["phase_separation"].status == "unsupported"
    assert res["maillard_reaction"].status == "likely"
