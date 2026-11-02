import math

import pytest

from flavorlab.db import FlavorDB, norm_name


def test_norm_name():
    assert norm_name("Ground_Cinnamon ") == "ground cinnamon"
    assert norm_name("extra-virgin  olive_oil") == "extra virgin olive oil"


def test_missing_database_has_helpful_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="build_database"):
        FlavorDB(tmp_path)


def test_profiles_merge_flavordb_via_crosswalk(tiny_db):
    # fg:1 tem {1,2,3,4}; fdb:10 (mesmo ingrediente) acrescenta {9}
    assert tiny_db.molecules_of("fg:1") == {1, 2, 3, 4, 9}
    assert tiny_db.molecules_of("fdb:10") == {1, 2, 3, 4, 9}
    assert tiny_db.molecules_of("fg:3") == frozenset()  # sem moléculas próprias


def test_resolve_by_name_prefers_flavorgraph(tiny_db):
    r = tiny_db.resolve("Cinnamon")
    assert r.ingredient_id == "fg:1" and r.molecules_from == "fg:1" and r.note == ""


def test_resolve_by_id_and_synonym(tiny_db):
    assert tiny_db.resolve("fg:2").name == "clove"
    assert tiny_db.resolve("zafferano").ingredient_id == "fdb:11"


def test_resolve_inherits_from_base_ingredient(tiny_db):
    r = tiny_db.resolve("ground_cinnamon")
    assert r.ingredient_id == "fg:3"
    assert r.molecules_from == "fg:1"
    assert "herdadas" in r.note


def test_resolve_unknown_suggests_similar(tiny_db):
    with pytest.raises(KeyError, match="cinnamon"):
        tiny_db.resolve("cinnamo")


def test_search_lists_ingredients_with_molecules_first(tiny_db):
    res = tiny_db.search("cinnamon")
    assert res.iloc[0]["has_molecules"]
    assert set(res["ingredient_id"]) == {"fg:1", "fg:3", "fdb:10"}


def test_npmi_is_symmetric_and_handles_missing(tiny_db):
    assert tiny_db.npmi("fg:1", "fg:2") == pytest.approx(0.4)
    assert tiny_db.npmi("fg:2", "fg:1") == pytest.approx(0.4)
    assert tiny_db.npmi("fg:2", "fg:4") == 0.0           # sem associação
    assert tiny_db.npmi("fdb:10", "fg:2") == pytest.approx(0.4)  # via crosswalk
    assert math.isnan(tiny_db.npmi("fdb:11", "fg:1"))    # só FlavorDB: sem dados de receita


def test_recipe_neighbors(tiny_db):
    assert tiny_db.recipe_neighbors("fg:1") == {"fg:2": pytest.approx(0.4), "fg:5": pytest.approx(0.2)}
    assert tiny_db.recipe_neighbors("fdb:11") == {}


def test_descriptors_are_normalized_and_cleaned(tiny_db):
    d = tiny_db.descriptors_by_molecule
    assert d[2] == ["woody"]              # alias wood -> woody
    assert d[4] == ["spicy"]              # 'odorless' descartado
    assert 5 not in d                     # frase longa descartada


def test_molecule_info(tiny_db):
    info = tiny_db.molecule_info(3)
    assert info["name"] == "mol3" and info["descriptors"] == ["sweet"]
    assert info["molecular_weight"] == pytest.approx(103.0)
    assert tiny_db.molecule_info(999)["name"] == "999"


def test_alias_for_name_outside_database(tiny_db):
    r = tiny_db.resolve("Canela")
    assert r.ingredient_id == "fg:1" and r.query == "Canela"


def test_alias_takes_priority_and_explains(tiny_db):
    # "tomato_sauce" -> heurística daria "sauce" (inexistente); apelido manda para tomato
    r = tiny_db.resolve("tomato_sauce")
    assert r.ingredient_id == "fg:6" and r.molecules_from == "fg:4"
    assert "molho é tomate" in r.note


def test_real_db_curated_aliases(real_db):
    r = real_db.resolve("olive_oil")
    assert len(real_db.molecules_of(r.molecules_from)) > 0 and "azeitona" in r.note
    assert "Piper" in real_db.resolve("black_pepper").note
