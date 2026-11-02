import pytest

from flavorlab import analyze_recipe


def test_pair_chemistry_and_practice(tiny_db):
    a = analyze_recipe(tiny_db, ["cinnamon", "clove"])
    p = a.pairs.iloc[0]
    assert {p.a, p.b} == {"cinnamon", "clove"}
    assert p.shared_molecules == 3
    assert p.jaccard == pytest.approx(0.5)
    assert p.npmi == pytest.approx(0.4)
    assert "clássica" in p.recipes


def test_unknown_ingredient_becomes_warning(tiny_db):
    a = analyze_recipe(tiny_db, ["cinnamon", "unobtainium"])
    assert [r.name for r in a.items] == ["cinnamon"]
    assert any("unobtainium" in w for w in a.warnings)


def test_inherited_ingredient_is_reported(tiny_db):
    a = analyze_recipe(tiny_db, ["ground_cinnamon", "clove"])
    assert a.pairs.iloc[0].shared_molecules == 3
    assert any("herdadas" in w for w in a.warnings)


def test_bridges_only_shared_molecules(tiny_db):
    a = analyze_recipe(tiny_db, ["cinnamon", "clove", "tomato"])
    assert set(a.bridges["pubchem_id"]) == {2, 3, 4}
    assert (a.bridges["n_ingredients"] >= 2).all()
    # moléculas com descritor vêm antes
    assert a.bridges["has_descriptor"].iloc[0]


def test_profile_fractions(tiny_db):
    a = analyze_recipe(tiny_db, ["cinnamon", "clove"])
    assert ((a.profile >= 0) & (a.profile <= 1)).all().all()
    # cinnamon: moléculas com descritor = {1,2,3,4}; 'sweet' em {1,3} -> 0,5
    assert a.profile.loc["sweet", "cinnamon"] == pytest.approx(0.5)


def test_suggestions(tiny_db):
    a = analyze_recipe(tiny_db, ["cinnamon"])
    sug = a.suggestions
    assert set(sug) == {"classicas", "quimicas", "ousadas"}
    for df in sug.values():
        assert "cinnamon" not in set(df["name"])          # não sugere o que já está na receita
    assert sug["classicas"].iloc[0]["name"] == "clove"    # NPMI 0,4 é o maior
    assert (sug["ousadas"]["linked_in_recipes"] == 0).all()
    # saffron compartilha a molécula 2 com cinnamon e não tem dados de receita -> ousada
    assert "Saffron" in set(sug["ousadas"]["name"])


def test_empty_recipe(tiny_db):
    a = analyze_recipe(tiny_db, [])
    assert a.items == [] and a.pairs.empty and a.suggestions == {}


def test_real_db_classic_pair(real_db):
    a = analyze_recipe(real_db, ["cinnamon", "clove"])
    p = a.pairs.iloc[0]
    assert p.jaccard > 0.3 and p.npmi > 0.3
    assert len(a.bridges) > 0


def test_real_db_query_is_fast(real_db):
    import time
    analyze_recipe(real_db, ["tomato", "basil"])  # aquece os índices
    t = time.perf_counter()
    analyze_recipe(real_db, ["tomato", "basil", "garlic", "parmesan_cheese"])
    assert time.perf_counter() - t < 1.0
