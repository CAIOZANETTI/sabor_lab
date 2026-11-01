"""Fixtures: um banco sintético pequeno, com respostas conhecidas de antemão.

Ingredientes (FlavorGraph = fg, FlavorDB = fdb):
    fg:1  cinnamon         moléculas {1,2,3,4}  (+ {1,9} via fdb:10 -> {1,2,3,4,9})
    fg:2  clove            {2,3,4,5}
    fg:3  ground_cinnamon  sem moléculas -> herda de cinnamon
    fg:4  tomato           {6,7}
    fg:5  sugar            {8}
    fdb:10 Cinnamon        {1,9}   (mesmo ingrediente que fg:1, via crosswalk)
    fdb:11 Saffron         {2,6,10} (só no FlavorDB; sinônimo "zafferano")

cinnamon x clove: em comum {2,3,4} = 3, união {1,2,3,4,5,9} = 6 -> Jaccard 0,5
Receitas (NPMI): cinnamon-clove 0,4 ; cinnamon-sugar 0,2
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flavorlab import FlavorDB  # noqa: E402

REAL_DB = ROOT / "data" / "processed" / "ingredients.parquet"


def _write(path: Path, name: str, df: pd.DataFrame) -> None:
    df.to_parquet(path / f"{name}.parquet", index=False)


@pytest.fixture()
def tiny_db_path(tmp_path: Path) -> Path:
    ing = pd.DataFrame([
        ("fg:1", "flavorgraph", "cinnamon", "cinnamon", "Spice", None, 4),
        ("fg:2", "flavorgraph", "clove", "clove", "Spice", None, 4),
        ("fg:3", "flavorgraph", "ground_cinnamon", "ground cinnamon", None, None, 0),
        ("fg:4", "flavorgraph", "tomato", "tomato", "Vegetable", None, 2),
        ("fg:5", "flavorgraph", "sugar", "sugar", None, None, 1),
        ("fdb:10", "flavordb", "Cinnamon", "cinnamon", "Spice", "Cinnamon", 2),
        ("fdb:11", "flavordb", "Saffron", "saffron", "Spice", "Saffron, Zafferano", 3),
    ], columns=["ingredient_id", "source", "name", "name_norm", "category", "synonyms", "n_molecules"])
    links = pd.DataFrame(
        [("fg:1", c) for c in (1, 2, 3, 4)] + [("fg:2", c) for c in (2, 3, 4, 5)]
        + [("fg:4", 6), ("fg:4", 7), ("fg:5", 8)]
        + [("fdb:10", 1), ("fdb:10", 9)] + [("fdb:11", c) for c in (2, 6, 10)],
        columns=["ingredient_id", "pubchem_id"])
    links["source"] = links["ingredient_id"].str.split(":").str[0]
    mol = pd.DataFrame({
        "pubchem_id": range(1, 11),
        "name": [f"mol{i}" for i in range(1, 11)],
        "molecular_weight": [100.0 + i for i in range(1, 11)],
        "xlogp": [float(i) / 2 for i in range(1, 11)],
        "functional_groups": ["terpene"] * 10,
    })
    desc = pd.DataFrame([
        (2, "wood", "flavor_profile"),          # alias -> woody
        (3, "sweet", "flavor_profile"),
        (4, "spicy", "flavor_profile"),
        (4, "odorless", "odor"),                # descartado
        (5, "a very long noisy descriptor phrase", "odor"),  # ruído descartado
        (6, "green", "flavor_profile"),
        (1, "sweet", "flavor_profile"),
    ], columns=["pubchem_id", "descriptor", "origin"])
    pairs = pd.DataFrame([
        ("fg:1", "fg:2", "cinnamon", "clove", 0.4),
        ("fg:1", "fg:5", "cinnamon", "sugar", 0.2),
    ], columns=["ingredient_a", "ingredient_b", "name_a", "name_b", "npmi_score"])
    cross = pd.DataFrame([("fdb:10", "fg:1", "cinnamon", "name")],
                         columns=["fdb_id", "fg_id", "matched_name", "match"])

    for name, df in [("ingredients", ing), ("ingredient_molecules", links), ("molecules", mol),
                     ("molecule_descriptors", desc), ("ingredient_pairs", pairs),
                     ("ingredient_crosswalk", cross)]:
        _write(tmp_path, name, df)
    return tmp_path


@pytest.fixture()
def tiny_db(tiny_db_path: Path) -> FlavorDB:
    return FlavorDB(tiny_db_path)


@pytest.fixture(scope="session")
def real_db() -> FlavorDB:
    if not REAL_DB.exists():
        pytest.skip("banco real não construído (rode scripts/build_database.py)")
    return FlavorDB()
