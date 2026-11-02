"""Camada de evidências (demanda 005): claims, fontes, consultas e conflitos."""

from __future__ import annotations

import csv

import pytest

from conftest import ROOT
from flavorlab.evidence import (CONFIDENCE_LEVELS, EVIDENCE_TYPES, EvidenceClaim, EvidenceError, EvidenceStore,
                                Source, SourceRegistry, new_claim, validate_claim)


@pytest.fixture(scope="module")
def sources() -> SourceRegistry:
    return SourceRegistry.load()


def measured(cid="m1", value=63.0, unit="°C", **kw):
    base = dict(claim_id=cid, subject_id="lote:1", predicate="internal_temperature", value=value, unit=unit,
                evidence_type="experimental_measurement", confidence="high", method="termômetro de espeto, centro",
                observed_at="2026-11-02T12:00:00")
    base.update(kw)
    return new_claim(**base)


def test_vocabularies_match_spec():
    assert set(EVIDENCE_TYPES) == {
        "experimental_measurement", "official_food_table", "recipe_association", "molecular_presence",
        "documented_physical_rule", "derived_calculation", "culinary_heuristic", "human_observation",
        "user_preference", "unvalidated_hypothesis"}
    assert CONFIDENCE_LEVELS == ("high", "moderate", "low", "qualitative", "unknown")


def test_06_measured_claims_need_unit_and_source_or_method():
    assert validate_claim(measured()) == []
    assert any("unidade" in e for e in validate_claim(measured(unit=None)))
    assert any("método" in e for e in validate_claim(measured(method=None)))
    # tabela oficial exige fonte registrada, não basta método
    table = measured(evidence_type="official_food_table", method="consulta", source_id=None)
    assert any("source_id" in e for e in validate_claim(table))


def test_07_heuristic_is_never_experimental(sources):
    heur = new_claim(claim_id="h1", subject_id="sl:ingredient:onion", predicate="browning_likely_at_high_heat",
                     value=True, unit=None, evidence_type="culinary_heuristic", confidence="moderate",
                     limitations="depende de umidade, açúcar e panela; não comprovado para este preparo")
    store = EvidenceStore([heur], sources)
    info = store.explain("h1")
    assert info["is_measurement"] is False and "culinary_heuristic" in info["text"]
    with pytest.raises(EvidenceError):  # heurística não pode ter confiança alta nem omitir limitações
        EvidenceStore([new_claim(**{**heur.to_dict(), "claim_id": "h2", "confidence": "high"})])
    with pytest.raises(EvidenceError):
        EvidenceStore([new_claim(**{**heur.to_dict(), "claim_id": "h3", "limitations": None})])
    with pytest.raises(EvidenceError):  # medição não aceita valor não numérico
        EvidenceStore([measured(value="rosada")])


def test_08_conflicts_are_preserved_and_queryable(sources):
    table = new_claim(claim_id="t1", subject_id="sl:ingredient:x", predicate="water_g_per_100g", value=70.0,
                      unit="g/100 g", evidence_type="official_food_table", confidence="high", source_id="taco_4ed",
                      observed_at=None)
    table2 = new_claim(**{**table.to_dict(), "claim_id": "t2", "value": 74.5, "source_id": "usda_sr_legacy"})
    obs = new_claim(claim_id="o1", subject_id="sl:ingredient:x", predicate="water_g_per_100g", value=60.0,
                    unit="g/100 g", evidence_type="human_observation", confidence="low", method="estimativa visual")
    store = EvidenceStore([obs, table2, table], sources)
    best = store.best_available("sl:ingredient:x", "water_g_per_100g")
    assert best.conflict and best.known
    assert best.selected.claim_id == "t1"          # tabela > observação; empate desfeito por claim_id
    assert {c.claim_id for c in best.alternatives} == {"t2", "o1"}   # divergentes não somem
    assert len(store.for_claim("water_g_per_100g")) == 3
    assert [c.claim_id for c in store.for_claim("water_g_per_100g", value=74.5)] == ["t2"]
    # valores dentro da incerteza declarada não são conflito
    a = measured("a", 63.0, uncertainty=0.5)
    b = measured("b", 63.4, uncertainty=0.5, observed_at="2026-11-02T12:01:00")
    assert not EvidenceStore([a, b]).best_available("lote:1", "internal_temperature").conflict


def test_best_available_prefers_recent_measurement_and_handles_absence():
    store = EvidenceStore([measured("old", 60.0, observed_at="2026-11-02T11:00:00"),
                           measured("new", 66.0, observed_at="2026-11-02T12:30:00"),
                           measured("nodate", 61.0, observed_at=None)])
    assert store.best_available("lote:1", "internal_temperature").selected.claim_id == "new"
    empty = store.best_available("lote:1", "ph")
    assert empty.selected is None and not empty.known and not empty.conflict


def test_claims_are_append_only():
    store = EvidenceStore([measured()])
    store.add(measured())                       # idêntico: idempotente
    with pytest.raises(EvidenceError):
        store.add(measured(value=70.0))         # mesmo ID, valor diferente: proibido sobrescrever


def test_10_json_round_trip_keeps_none_limitations_and_ids(sources):
    claims = [measured(uncertainty=0.5, context="peça de 2 cm"),
              new_claim(claim_id="hyp", subject_id="dish:1", predicate="sauce_may_split", value=True, unit=None,
                        evidence_type="unvalidated_hypothesis", confidence="low",
                        limitations="kefir pode coagular acima de fervura branda; não testado")]
    store = EvidenceStore(claims, sources)
    again = EvidenceStore.from_json(store.to_json(), sources)
    assert [c.to_dict() for c in again] == [c.to_dict() for c in store]
    hyp = again.get("hyp")
    assert hyp.source_id is None and hyp.observed_at is None and hyp.limitations.startswith("kefir")


def test_source_registry_has_no_invented_urls(sources):
    assert len(sources) >= 10
    for s in sources:
        if s.url or s.doi:
            assert s.verification_status == "verified" and s.accessed_at
    with pytest.raises(EvidenceError):
        SourceRegistry([Source("fake", "Algo", "Alguém", "peer_reviewed", url="https://example.org/x")])
    with pytest.raises(EvidenceError):
        EvidenceStore([new_claim(claim_id="x", subject_id="s", predicate="p", value=1.0, unit="g",
                                 evidence_type="official_food_table", confidence="high", source_id="nao_existe")],
                      sources)


def test_source_registry_matches_catalog_datasets(sources):
    """Registro único: datasets do catálogo usam os mesmos IDs e versões."""
    with open(ROOT / "data" / "catalog" / "sources.csv", newline="", encoding="utf-8") as fh:
        datasets = list(csv.DictReader(fh))
    for row in datasets:
        assert row["dataset"] in sources, row["dataset"]
        reg = sources.get(row["dataset"])
        assert row["version"].split(" ")[0] in reg.version


def test_explain_resolves_source(sources):
    c = new_claim(claim_id="n1", subject_id="sl:form:common_bean_black_raw", predicate="energia_kcal_per_100g",
                  value=324.0, unit="kcal/100 g", evidence_type="official_food_table", confidence="high",
                  source_id="taco_4ed")
    info = EvidenceStore([c], sources).explain("n1")
    assert info["source"]["source_id"] == "taco_4ed"
    assert "324.0 kcal/100 g" in info["text"]
    assert isinstance(EvidenceClaim.from_dict(info["claim"]), EvidenceClaim)
