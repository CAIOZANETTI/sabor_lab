"""Estados de ingredientes, transições e adaptador legado (demanda 005)."""

from __future__ import annotations

import pandas as pd
import pytest

from conftest import ROOT
from flavorlab.catalog import Catalog
from flavorlab.evidence import EvidenceError, EvidenceStore, SourceRegistry, new_claim
from flavorlab.states import (EVENT_KINDS, PREPARATION_STATES, STORAGE_STATES, TRACKED_FIELDS, IngredientState,
                              ProcessEvent, StateError, StateTracker, adapt_legacy_recipe, safety_assessment,
                              state_from_claims, to_canonical, transition_state)

INST = "user:fraldinha_001"


def obs(cid, predicate, value, unit=None, confidence="moderate", **kw):
    return new_claim(claim_id=cid, subject_id=INST, predicate=predicate, value=value, unit=unit,
                     evidence_type="human_observation", confidence=confidence, method="relato do usuário", **kw)


@pytest.fixture()
def fraldinha():
    """350 g de fraldinha já feita na air fryer, rosada e suculenta."""
    claims = [obs("c_mass", "mass_g", 350, "g"),
              obs("c_prep", "preparation_state", "cooked"),
              obs("c_meth", "cooking_method", "air_fryer"),
              obs("c_done", "doneness", "rosada", confidence="qualitative", context="sl:group:meat"),
              obs("c_tex", "texture_attribute", "suculenta", confidence="qualitative")]
    store = EvidenceStore()
    return state_from_claims(INST, "sl:part:beef_fraldinha", "fraldinha", claims, store=store), store


def test_vocabularies_match_spec():
    assert set(PREPARATION_STATES.terms) == set("""raw cooked baked roasted grilled fried sauteed steamed boiled
        pressure_cooked fermented marinated cured smoked dried frozen thawed reheated mixed unknown""".split())
    assert set(STORAGE_STATES.terms) == {"freshly_prepared", "ambient", "refrigerated", "frozen", "thawed", "unknown"}
    extended = PREPARATION_STATES.extend("sous_vide_cooked")
    assert extended.version == PREPARATION_STATES.version + 1 and "sous_vide_cooked" not in PREPARATION_STATES


def test_minimal_case_fraldinha(fraldinha):
    state, store = fraldinha
    assert state.mass_g == 350 and state.preparation_state == "cooked" and state.cooking_method == "air_fryer"
    assert state.doneness.term == "rosada" and state.doneness.context == "sl:group:meat"
    assert state.texture_attributes == ("suculenta",)
    for unknown in ("measured_temperature_c", "process_temperature_c", "process_duration_s",
                    "storage_state", "storage_duration_s", "moisture_fraction", "yield_factor"):
        assert unknown in state.unknown_fields()
    assert state.measured_temperature_c is None and state.process_temperature_c is None
    assert state.yield_factor is None and state.moisture_fraction is None   # sem retenção/rendimento inferidos
    assert safety_assessment(state).status == "indeterminate"
    assert set(state.observations) == {"c_mass", "c_prep", "c_meth", "c_done", "c_tex"}


def test_01_raw_and_cooked_are_distinct_states_of_same_concept():
    def make(prep, cid):
        return state_from_claims(f"inst:{cid}", "sl:part:beef_fraldinha", "fraldinha",
                                 [new_claim(claim_id=cid, subject_id=f"inst:{cid}", predicate="preparation_state",
                                            value=prep, unit=None, evidence_type="human_observation",
                                            confidence="moderate", method="relato")])
    raw, cooked = make("raw", "r"), make("cooked", "c")
    assert raw.entity_id == cooked.entity_id
    assert raw.preparation_state != cooked.preparation_state and raw != cooked


def test_02_unknown_fields_survive_serialization_and_transition(fraldinha):
    state, _ = fraldinha
    again = IngredientState.from_json(state.to_json())
    assert again == state and again.unknown_fields() == state.unknown_fields()
    nxt = transition_state(state, ProcessEvent("ev:obs", INST, "observe"), [])
    assert set(state.unknown_fields()) <= set(nxt.unknown_fields()) | set(nxt.known_fields())
    assert nxt.measured_temperature_c is None and nxt.status("measured_temperature_c") == "unknown"


def test_03_air_fryer_does_not_imply_internal_temperature(fraldinha):
    state, _ = fraldinha
    assert state.cooking_method == "air_fryer"
    assert state.measured_temperature_c is None and state.process_temperature_c is None
    assert {"measured_temperature_c", "process_temperature_c"} <= set(state.unknown_fields())


def test_04_juicy_observation_is_not_an_instrument_measurement(fraldinha):
    state, store = fraldinha
    tex = store.get(state.knowledge["texture_attributes"].claim_ids[0])
    assert tex.evidence_type == "human_observation" and tex.confidence == "qualitative" and tex.unit is None
    assert state.moisture_fraction is None and state.status("moisture_fraction") == "unknown"
    with pytest.raises(EvidenceError):   # observação humana não pode ter confiança alta
        EvidenceStore([new_claim(**{**tex.to_dict(), "claim_id": "x", "confidence": "high"})])


def test_05_transition_preserves_history_and_previous_state(fraldinha):
    state, _ = fraldinha
    tracker = StateTracker()
    tracker.record(state)
    store_ev = ProcessEvent("ev:store", INST, "store", ("c_store", "c_dur"))
    claims = [obs("c_store", "storage_state", "refrigerated"), obs("c_dur", "storage_duration_s", 12, "h")]
    v2 = tracker.apply(store_ev, claims)
    reheat = tracker.apply(ProcessEvent("ev:reheat", INST, "reheat"), [])
    assert [s.state_version for s in tracker.history(INST)] == [1, 2, 3]
    assert state.storage_state == "unknown" and state.events == ()       # anterior intacto
    assert v2.storage_state == "refrigerated" and v2.storage_duration_s == 12 * 3600
    assert v2.parent_version == 1 and v2.events == ("ev:store",)
    # reaquecer não informa nada: massa, ponto e textura deixam de ser certos, sem valor presumido
    assert reheat.mass_g is None and reheat.status("mass_g") == "uncertain"
    assert "350" in reheat.knowledge["mass_g"].note
    assert reheat.preparation_state == "unknown" and reheat.status("preparation_state") == "uncertain"
    assert reheat.cooking_method == "air_fryer"                             # não afetado: mantido
    assert reheat.events == ("ev:store", "ev:reheat")


def test_transition_does_not_declare_transformations(fraldinha):
    state, _ = fraldinha
    cook = transition_state(state, ProcessEvent("ev:cook", INST, "cook"), [])
    assert cook.preparation_state == "unknown"          # técnica não define o estado resultante sozinha
    assert cook.process_temperature_c is None
    with pytest.raises(StateError):
        transition_state(state, ProcessEvent("ev:plan", INST, "cook", planned=True), [])
    with pytest.raises(StateError):
        transition_state(state, ProcessEvent("ev:x", INST, "cook", ("faltando",)), [])
    with pytest.raises(StateError):
        transition_state(state, ProcessEvent("ev:y", INST, "teleport"), [])


def test_measured_temperature_with_unit_conversion_and_staleness(fraldinha):
    state, _ = fraldinha
    m = new_claim(claim_id="t1", subject_id=INST, predicate="measured_temperature_c", value=140.0, unit="°F",
                  evidence_type="experimental_measurement", confidence="high", method="termômetro no centro")
    v2 = transition_state(state, ProcessEvent("ev:measure", INST, "measure", ("t1",)), [m])
    assert v2.measured_temperature_c == pytest.approx(60.0) and v2.status("measured_temperature_c") == "known"
    v3 = transition_state(v2, ProcessEvent("ev:rest", INST, "rest"), [])
    assert v3.measured_temperature_c is None and v3.status("measured_temperature_c") == "uncertain"
    assert to_canonical("process_duration_s", 15, "min") == 900
    assert to_canonical("mass_g", 1, "lb") == pytest.approx(453.59237)
    with pytest.raises(StateError):
        to_canonical("mass_g", 1, "ml")


def test_conflicting_claims_mark_field_uncertain():
    claims = [new_claim(claim_id="a", subject_id="i", predicate="mass_g", value=350, unit="g",
                        evidence_type="human_observation", confidence="moderate", method="relato"),
              new_claim(claim_id="b", subject_id="i", predicate="mass_g", value=320, unit="g",
                        evidence_type="experimental_measurement", confidence="high", method="balança")]
    s = state_from_claims("i", None, "x", claims)
    assert s.mass_g == 320 and s.status("mass_g") == "uncertain"
    assert set(s.knowledge["mass_g"].claim_ids) == {"a", "b"}


def test_state_rejects_values_without_origin_or_invalid_terms():
    with pytest.raises(StateError):
        IngredientState("i", None, "x", mass_g=10.0)            # valor sem claim
    with pytest.raises(StateError):
        IngredientState("i", None, "x", preparation_state="rosado")
    assert EVENT_KINDS.terms >= {"cook", "store", "observe"}


def test_09_legacy_recipes_are_adapted_without_inventing_fields():
    cat = Catalog.load(with_inventory=False)
    rows = pd.read_csv(ROOT / "data" / "experiments" / "receita_ingredientes.csv", dtype=str, keep_default_na=False)
    store = EvidenceStore()
    states = {r: adapt_legacy_recipe(g.to_dict("records"), r, catalog=cat, store=store)
              for r, g in rows.groupby("recipe_id")}
    assert sum(len(v) for v in states.values()) == len(rows)
    for s in (x for v in states.values() for x in v):
        assert s.legacy is not None and s.legacy["recipe_id"]
        for name in ("measured_temperature_c", "storage_state", "moisture_fraction", "doneness", "yield_factor"):
            assert name in s.unknown_fields()
    ex01 = {s.display_name: s for s in states["EX01"]}
    assert ex01["tomate"].mass_g == 800 and ex01["tomate"].entity_id == "sl:ingredient:tomato"
    assert ex01["azeite"].mass_g is None and "volume" in ex01["azeite"].knowledge["mass_g"].note
    assert ex01["alho"].preparation_state == "unknown" and ex01["alho"].legacy["preparo"] == "picado"
    ex03 = {s.display_name: s for s in states["EX03"]}
    assert ex03["chocolate amargo"].mass_g == pytest.approx(12 * 28.349523125)   # oz por definição exata
    claim = store.get(ex03["chocolate amargo"].knowledge["mass_g"].claim_ids[0])
    assert claim.evidence_type == "human_observation" and "planejada" in claim.method


def test_10_state_json_round_trip_preserves_enums_none_and_ids(fraldinha):
    state, store = fraldinha
    text = state.to_json()
    again = IngredientState.from_json(text)
    assert again.preparation_state == "cooked" and again.storage_state == "unknown"
    assert again.mass_g == 350 and again.moisture_fraction is None
    assert again.knowledge["doneness"].claim_ids == ("c_done",)
    assert again.instance_id == INST and again.entity_id == "sl:part:beef_fraldinha"
    store2 = EvidenceStore.from_json(store.to_json())
    assert store2.get("c_done").context == "sl:group:meat"


def test_all_tracked_fields_have_knowledge(fraldinha):
    state, _ = fraldinha
    assert set(state.knowledge) == set(TRACKED_FIELDS)
    assert set(state.known_fields()) | set(state.unknown_fields()) | set(state.uncertain_fields()) == set(TRACKED_FIELDS)


def test_sources_registry_loads():
    assert "taco_4ed" in SourceRegistry.load()
