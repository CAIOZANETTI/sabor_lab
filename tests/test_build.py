import importlib.util

import numpy as np
import pandas as pd

from conftest import ROOT

spec = importlib.util.spec_from_file_location("build_database", ROOT / "scripts" / "build_database.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


ENTITY = {
    "entity_id": "7", "category_readable": "Spice", "entity_alias_readable": "Black Pepper",
    "entity_alias_synonyms": "Pepper, Black Peppercorn", "natural_source_name": "Piper nigrum",
    "entity_alias_url": "https://en.wikipedia.org/wiki/Black_pepper",
    "molecules": [
        {"pubchem_id": "638024", "common_name": "Piperine", "flavor_profile": "pungent@spicy",
         "fema_flavor_profile": "Pungent, Woody", "odor": "None", "taste": "None",
         "molecular_weight": "285.34", "xlogp": "3.5"},
        {"pubchem_id": "638024", "common_name": "Piperine"},   # duplicada
        {"pubchem_id": "not-a-number", "common_name": "lixo"},  # descartada
    ],
}


def test_clean_and_split_terms():
    assert np.isnan(build.clean("None"))
    assert build.split_terms("sweet@ Woody @none", "@") == ["sweet", "woody"]
    assert build.split_terms(None, "@") == []


def test_build_flavordb_from_entity():
    ing, lnk, mol = build.build_flavordb([ENTITY])
    assert ing.loc[0, "ingredient_id"] == "fdb:7"
    assert ing.loc[0, "name_norm"] == "black pepper"
    assert len(lnk) == 1 and lnk.iloc[0]["pubchem_id"] == 638024
    assert mol.loc[0, "molecular_weight"] == 285.34


def test_descriptors_long_format():
    _, _, mol = build.build_flavordb([ENTITY])
    d = build.build_descriptors(mol)
    assert set(d["descriptor"]) == {"pungent", "spicy", "woody"}
    assert not d.duplicated().any()


def test_crosswalk_matches_name_and_synonym():
    fdb = pd.DataFrame({"ingredient_id": ["fdb:7", "fdb:8"], "name_norm": ["black pepper", "kokum"],
                        "synonyms": [None, "Garcinia, Kokum Butter"]})
    fg = pd.DataFrame({"ingredient_id": ["fg:1", "fg:2"], "name_norm": ["black pepper", "garcinia"]})
    cw = build.build_crosswalk(fdb, fg)
    assert dict(zip(cw["fdb_id"], cw["fg_id"])) == {"fdb:7": "fg:1", "fdb:8": "fg:2"}
    assert list(cw["match"]) == ["name", "synonym"]


def test_processed_tables_are_consistent():
    """Integridade do banco real: chaves estrangeiras válidas e tipos corretos."""
    import pytest
    path = ROOT / "data" / "processed"
    if not (path / "ingredients.parquet").exists():
        pytest.skip("banco real não construído")
    ing = pd.read_parquet(path / "ingredients.parquet")
    mol = pd.read_parquet(path / "molecules.parquet")
    lnk = pd.read_parquet(path / "ingredient_molecules.parquet")
    pairs = pd.read_parquet(path / "ingredient_pairs.parquet")
    assert ing["ingredient_id"].is_unique and mol["pubchem_id"].is_unique
    assert lnk["ingredient_id"].isin(ing["ingredient_id"]).all()
    assert lnk["pubchem_id"].isin(mol["pubchem_id"]).all()
    assert pairs["ingredient_a"].isin(ing["ingredient_id"]).all()
    assert pairs["npmi_score"].between(0, 1).all()
    assert pd.api.types.is_integer_dtype(lnk["pubchem_id"])
