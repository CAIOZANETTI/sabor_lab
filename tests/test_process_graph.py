"""Grafo de preparo e scheduler (demanda 003).

Grafos sintéticos com respostas conhecidas + processos EX01–EX03 reais.
Durações em minutos nos claims; o scheduler trabalha em segundos.
"""

from __future__ import annotations

import pytest

from conftest import ROOT
from flavorlab.catalog import Catalog
from flavorlab.evidence import EvidenceError
from flavorlab.process import (PROCESSES_DIR, CulinaryKnowledge, ProcessError, RecipeProcess, find_cycle,
                               load_processes, step_controls, thermally_cooked, validate_process)
from flavorlab.scheduler import critical_path, reschedule, schedule
from flavorlab.states import (IngredientState, ProcessEvent, StateError, state_from_claims, transition_state)
from flavorlab.evidence import new_claim

MIN = 60.0


@pytest.fixture(scope="module")
def knowledge() -> CulinaryKnowledge:
    return CulinaryKnowledge.load()


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.load(with_inventory=False)


def build(steps, resources=(("pan", "frying_pan", 1),), ingredients=(), cooks=1, recipe_id="T"):
    """steps: (id, phase, active_min, passive_min, deps, equipment, attention, extra)."""
    claims, out = [], []
    for sid, phase, act, pas, deps, eq, att, *extra in steps:
        extra = extra[0] if extra else {}
        cids = {}
        for name, val in (("active_duration_s", act), ("passive_duration_s", pas)):
            if val is not None:
                cid = f"{recipe_id}:{sid}:{name}"
                claims.append(dict(claim_id=cid, subject_id=f"process:{recipe_id}:{sid}", predicate="process_duration_s",
                                   value=val, unit="min", evidence_type="culinary_heuristic", confidence="low",
                                   method="teste", limitations="grafo sintético", source_id=None, observed_at=None))
                cids[name] = cid
        for name, (val, unit) in extra.pop("temps", {}).items():
            cid = f"{recipe_id}:{sid}:{name}"
            claims.append(dict(claim_id=cid, subject_id=f"process:{recipe_id}:{sid}", predicate="process_temperature_c",
                               value=val, unit=unit, evidence_type="culinary_heuristic", confidence="moderate",
                               method="teste", limitations="grafo sintético", source_id=None, observed_at=None))
            cids[name] = cid
        out.append(dict(step_id=sid, phase=phase, title=sid, instruction=sid, dependencies=list(deps),
                        equipment_refs=list(eq), attention=att, claim_ids=cids, **extra))
    return RecipeProcess.from_dict(dict(
        recipe_id=recipe_id, servings=1, cooks=cooks, provenance="teste", claims=claims, steps=out,
        resources=[dict(resource_id=r, equipment_id=e, capacity=c) for r, e, c in resources],
        ingredients=[dict(ref_id=i, entity_id=e, display_name=n) for i, e, n in ingredients]))


# --------------------------------------------------------------------------- 1
def test_01_cycle_is_rejected_with_clear_message(knowledge):
    proc = build([("a", "coccao", 1, None, ("c",), (), "active"),
                  ("b", "coccao", 1, None, ("a",), (), "active"),
                  ("c", "coccao", 1, None, ("b",), (), "active")])
    assert find_cycle(proc.steps) == ["a", "c", "b", "a"]
    with pytest.raises(ProcessError, match="ciclo de dependências: a -> c -> b -> a"):
        schedule(proc)
    assert any("ciclo" in e for e in validate_process(proc, knowledge))


# --------------------------------------------------------------------------- 2
def test_02_preheat_runs_in_parallel_and_finishes_before_oven_use():
    proc = build([("prep", "mise_en_place", 20, None, (), (), "active"),
                  ("preheat", "preaquecimento", 1, 14, (), ("oven",), "passive"),
                  ("bake", "coccao", None, 12, ("prep", "preheat"), ("oven",), "check")],
                 resources=(("oven", "oven", 1),))
    s = schedule(proc)
    ph, bake, prep = s.tasks["preheat"], s.tasks["bake"], s.tasks["prep"]
    assert ph.planned_end_s <= bake.planned_start_s == prep.planned_end_s == 20 * MIN
    assert ph.planned_end_s == bake.planned_start_s               # termina exatamente quando o forno é usado
    assert ph.planned_start_s == 5 * MIN                          # o mais tarde possível, em paralelo ao preparo
    assert ph.planned_start_s < prep.planned_end_s
    assert s.makespan_s == 32 * MIN


def test_02b_long_preheat_delays_consumer_instead_of_being_skipped():
    proc = build([("prep", "mise_en_place", 5, None, (), (), "active"),
                  ("preheat", "preaquecimento", 1, 19, (), ("oven",), "passive"),
                  ("bake", "coccao", None, 12, ("prep", "preheat"), ("oven",), "check")],
                 resources=(("oven", "oven", 1),))
    s = schedule(proc)
    assert s.tasks["preheat"].planned_start_s == 0
    assert s.tasks["bake"].planned_start_s == 20 * MIN


# --------------------------------------------------------------------------- 3
def test_03_two_tasks_never_share_the_same_pan():
    proc = build([("sear_a", "coccao", 5, None, (), ("pan",), "active"),
                  ("sear_b", "coccao", None, 6, (), ("pan",), "passive")])
    s = schedule(proc)
    a, b = s.tasks["sear_a"], s.tasks["sear_b"]
    assert a.planned_end_s <= b.planned_start_s or b.planned_end_s <= a.planned_start_s
    assert s.makespan_s == 11 * MIN
    two = build([("sear_a", "coccao", 5, None, (), ("pan",), "active"),
                 ("sear_b", "coccao", None, 6, (), ("pan",), "passive")], resources=(("pan", "frying_pan", 2),))
    assert schedule(two).makespan_s == 6 * MIN                    # capacidade 2: paralelo


def test_03b_single_cook_cannot_do_two_active_tasks_at_once():
    proc = build([("chop", "mise_en_place", 4, None, (), (), "active"),
                  ("whisk", "mise_en_place", 3, None, (), (), "active")])
    s = schedule(proc)
    assert s.makespan_s == 7 * MIN
    assert schedule(build([("chop", "mise_en_place", 4, None, (), (), "active"),
                           ("whisk", "mise_en_place", 3, None, (), (), "active")], cooks=2)).makespan_s == 4 * MIN


# --------------------------------------------------------------------------- 4
def test_04_passive_rest_does_not_block_mise_en_place():
    proc = build([("marinate", "descanso", 2, 30, (), ("bowl",), "passive"),
                  ("chop", "mise_en_place", 10, None, (), ("board",), "active"),
                  ("cook", "coccao", 8, None, ("marinate", "chop"), ("pan",), "active")],
                 resources=(("bowl", "mixing_bowl", 1), ("board", "cutting_board", 1), ("pan", "frying_pan", 1)))
    s = schedule(proc)
    assert s.tasks["chop"].planned_start_s < s.tasks["marinate"].planned_end_s     # sobrepõe o descanso
    assert s.makespan_s == 32 * MIN + 8 * MIN
    assert any({"marinate", "chop"} <= set(g) for g in s.parallel_groups)


# --------------------------------------------------------------------------- 5
def test_05_critical_path_and_total_duration_of_known_graph():
    #   a(3) ─┬─ b(4) ─┐
    #         └─ c(10) ┴─ d(2)        caminho crítico a-c-d = 15 min
    proc = build([("a", "mise_en_place", 3, None, (), (), "active"),
                  ("b", "coccao", None, 4, ("a",), (), "passive"),
                  ("c", "coccao", None, 10, ("a",), (), "passive"),
                  ("d", "finalizacao", 2, None, ("b", "c"), (), "active")])
    path, total = critical_path(proc)
    assert path == ["a", "c", "d"] and total == 15 * MIN
    s = schedule(proc)
    assert s.makespan_s == 15 * MIN and s.critical_path == ["a", "c", "d"]
    assert s.cook_active_s == 5 * MIN and s.passive_s == 14 * MIN


# --------------------------------------------------------------------------- 6
def test_06_delay_recomputes_only_dependents():
    proc = build([("a", "mise_en_place", 3, None, (), (), "active"),
                  ("b", "coccao", None, 4, ("a",), (), "passive"),
                  ("c", "coccao", None, 10, ("a",), (), "passive"),
                  ("d", "finalizacao", 2, None, ("b", "c"), (), "active"),
                  ("x", "mise_en_place", None, 5, (), (), "passive")])
    s = schedule(proc)
    late = reschedule(proc, s, "b", actual_end_s=s.tasks["b"].planned_end_s + 20 * MIN)
    assert late.tasks["b"].status == "done" and late.tasks["b"].actual_end_s == 27 * MIN
    assert late.tasks["b"].planned_end_s == s.tasks["b"].planned_end_s     # planejado preservado, real separado
    for unrelated in ("a", "c", "x"):
        assert late.tasks[unrelated].planned_start_s == s.tasks[unrelated].planned_start_s
        assert late.tasks[unrelated].status == "planned"
    assert late.tasks["d"].planned_start_s == 27 * MIN and late.tasks["d"].status == "rescheduled"
    early = reschedule(proc, s, "c", actual_end_s=s.tasks["c"].planned_end_s - 5 * MIN)
    assert early.tasks["d"].planned_start_s == 8 * MIN                      # b termina aos 7; c aos 8


# --------------------------------------------------------------------------- 7
def test_07_time_and_temperature_units_are_preserved():
    proc = build([("p", "preaquecimento", 1, 14, (), ("oven",), "passive",
                   {"temps": {"target_temp_c": (350, "°F")}}),
                  ("b", "coccao", None, 12, ("p",), ("oven",), "check", {"temps": {"target_temp_c": (180, "°C")}})],
                 resources=(("oven", "oven", 1),))
    p, b = proc.step("p"), proc.step("b")
    assert p.target_temp_c == pytest.approx(176.6667, rel=1e-4) and b.target_temp_c == 180
    assert p.active_duration_s == 60 and p.passive_duration_s == 14 * MIN
    assert proc.claims.get(p.claim_ids["target_temp_c"]).unit == "°F"      # valor original preservado
    with pytest.raises(ProcessError, match="sem claim"):
        RecipeProcess.from_dict(dict(recipe_id="X", steps=[dict(step_id="s", phase="coccao", title="s",
                                                                instruction="s", target_temp_c=200)]))


# --------------------------------------------------------------------------- 8
def test_08_incompatible_cut_is_a_validation_error(knowledge, catalog):
    proc = build([("cut", "mise_en_place", 2, None, (), ("board",), "active",
                   {"cut_id": "chiffonade", "technique_id": "knife_cut",
                    "ingredient_refs": ["ing:egg"]})],
                 resources=(("board", "cutting_board", 1),),
                 ingredients=(("ing:egg", "sl:ingredient:chicken_egg", "ovo"),))
    errors = validate_process(proc, knowledge, catalog)
    assert any("chiffonade" in e and "não se aplica" in e for e in errors)
    assert proc.step("cut").cut_id == "chiffonade"                           # nada corrigido silenciosamente


# --------------------------------------------------------------------------- 9, 10
def test_09_safety_and_culinary_target_are_distinct_controls(knowledge):
    control = sorted(c for c, sc in knowledge.safety_controls.items() if sc.control_type == "min_internal_temp")[0]
    proc = build([("roast", "coccao", None, 40, (), ("oven",), "check",
                   {"technique_id": "roast_oven", "safety_control_id": control,
                    "temps": {"target_temp_c": (200, "°C")}})],
                 resources=(("oven", "oven", 1),))
    ctl = step_controls(proc.step("roast"), proc, knowledge)
    assert ctl.culinary_target["kind"] == "culinary_target" and ctl.culinary_target["target_temp_c"] == 200
    assert ctl.safety["kind"] == "safety_control" and ctl.safety["url"].startswith("https://")
    assert ctl.safety["value"] != ctl.culinary_target["target_temp_c"]      # forno ≠ temperatura interna
    no_ctl = step_controls(build([("roast", "coccao", None, 40, (), ("oven",), "check",
                                   {"technique_id": "roast_oven"})], resources=(("oven", "oven", 1),)).step("roast"),
                           proc, knowledge)
    assert no_ctl.safety is None and any("indeterminada" in w for w in no_ctl.warnings)


def test_10_ceviche_is_not_thermally_cooked_nor_automatically_safe(knowledge):
    proc = RecipeProcess.load(PROCESSES_DIR / "CEVICHE_DEMO.json")
    marinate = next(s for s in proc.steps if s.technique_id == "acid_marinate")
    assert not thermally_cooked(marinate, knowledge)
    ctl = step_controls(marinate, proc, knowledge)
    assert any("não equivale a cocção" in w for w in ctl.warnings)
    tr = knowledge.transformations["acid_denaturation"]
    assert "não" in tr.limitations.lower() and tr.sources
    # executar a marinada não marca o peixe como cozido: o estado vem só de claims
    fish = next(iter(proc.ingredients))
    s0 = state_from_claims(fish, proc.ingredients[fish].entity_id, "peixe", [new_claim(
        claim_id="f0", subject_id=fish, predicate="preparation_state", value="raw", unit=None,
        evidence_type="human_observation", confidence="moderate", method="relato")])
    ev = marinate.planned_events(knowledge)[0]
    assert ev.planned and ev.kind == "marinate"
    with pytest.raises(StateError):
        transition_state(s0, ev, [])                                        # planejado não altera estado
    done = ProcessEvent("exec:marinate", fish, "marinate", ("f1",))
    s1 = transition_state(s0, done, [new_claim(claim_id="f1", subject_id=fish, predicate="preparation_state",
                                               value="marinated", unit=None, evidence_type="human_observation",
                                               confidence="moderate", method="relato")])
    assert s1.preparation_state == "marinated" and s1.preparation_state != "cooked"
    assert s1.process_temperature_c is None
    # se houver controle de parasitas/congelamento, ele vem de fonte oficial, separado
    for step in proc.steps:
        if step.safety_control_id:
            sc = knowledge.safety_controls[step.safety_control_id]
            assert knowledge.sources.get(sc.source_id).source_type in {"official_regulation", "official_guidance"}


# --------------------------------------------------------------------------- 11
@pytest.mark.parametrize("rid", ["EX01", "EX02", "EX03"])
def test_11_examples_are_valid_and_resolved_in_catalog(rid, knowledge, catalog):
    proc = load_processes()[rid]
    assert validate_process(proc, knowledge, catalog) == []
    for ing in proc.ingredients.values():
        assert ing.entity_id in catalog, ing
    s = schedule(proc)
    assert set(s.tasks) == {st.step_id for st in proc.steps}
    for st in proc.steps:                                                   # dependências respeitadas
        for d in st.dependencies:
            if proc.step(d).phase == "preaquecimento":
                assert s.tasks[d].planned_end_s <= s.tasks[st.step_id].planned_start_s
            else:
                assert s.tasks[d].planned_end_s <= s.tasks[st.step_id].planned_start_s
    assert s.mise_en_place and s.cooking_sequence
    for claim in proc.claims:                                              # tempos sem fonte = heurística declarada
        assert claim.evidence_type == "culinary_heuristic" and claim.limitations


def test_11b_ex03_parallelism_matches_spec(knowledge):
    proc = load_processes()["EX03"]
    s = schedule(proc)
    t = s.tasks
    assert t["p01"].planned_end_s <= t["s09"].planned_start_s               # forno pronto antes de assar
    assert t["p01"].planned_start_s > 0                                     # preaquecimento não começa cedo demais
    assert t["s03"].planned_start_s < t["s02"].planned_end_s                # secos misturados enquanto a manteiga amolece
    assert t["s04"].planned_start_s < t["s02"].planned_end_s                # chocolate picado no mesmo intervalo
    assert proc.step("s09").target_temp_c == pytest.approx(176.6667, rel=1e-4)   # 350 °F
    assert s.critical_path[-1] == "s10" and s.makespan_s == s.critical_path_s


def test_11c_examples_do_not_change_nutrition():
    """Os processos não tocam no cálculo nutricional: mesmos totais da receita EX01."""
    import pandas as pd
    from flavorlab.nutrition import NutritionDB
    rows = pd.read_csv(ROOT / "data" / "experiments" / "receita_ingredientes.csv", dtype=str, keep_default_na=False)
    db = NutritionDB()
    lines = [{"nome": r["ingrediente"], "quantidade": r["quantidade"], "unidade": r["unidade"],
              "gramas": r["gramas"] or None} for r in rows[rows.recipe_id == "EX01"].to_dict("records")]
    before = db.recipe(lines, portions=4).total
    load_processes()
    after = db.recipe(lines, portions=4).total
    assert before.equals(after)


# --------------------------------------------------------------------------- dados curados
def test_culinary_data_is_valid_and_sourced(knowledge):
    assert knowledge.validate() == []
    assert {"oven", "convection_oven", "stovetop_burner", "frying_pan", "saucepan", "baking_sheet",
            "pressure_cooker", "blender", "food_processor", "refrigerator", "countertop",
            "kitchen_thermometer"} <= set(knowledge.equipment)
    thermo = knowledge.equipment["kitchen_thermometer"]
    assert thermo.type == "instrument" and not thermo.is_heat_source
    assert all(e.min_temp_c is None and e.max_temp_c is None for e in knowledge.equipment.values())  # sem potência inventada
    assert {"rough_chop", "mince", "dice_small", "slice", "julienne", "brunoise", "chiffonade", "wedge", "round",
            "strips", "mash", "grate", "crush"} <= set(knowledge.cuts)
    assert all(c.effect for c in knowledge.cuts.values())
    assert {"maillard_reaction", "caramelization", "starch_gelatinization", "protein_denaturation_heat",
            "acid_denaturation", "emulsification", "evaporation_reduction", "hydration_rest",
            "fermentation_concept"} <= set(knowledge.transformations)
    for sc in knowledge.safety_controls.values():
        src = knowledge.sources.get(sc.source_id)
        assert src.url and src.accessed_at and src.verification_status == "verified"


def test_transformations_have_no_universal_temperature(knowledge):
    """Uma temperatura só aparece acompanhada de aviso de variação; nunca como limiar único."""
    import re
    for tr in knowledge.transformations.values():
        assert tr.conditions and tr.limitations and tr.sources
        if re.search(r"\d+\s*°C", tr.conditions):
            assert re.search(r"vari|diverg", tr.conditions + tr.limitations), tr.transformation_id
    assert knowledge.transformations["acid_denaturation"].evidence_type == "documented_physical_rule"
    assert knowledge.transformations["hydration_rest"].evidence_type == "culinary_heuristic"
