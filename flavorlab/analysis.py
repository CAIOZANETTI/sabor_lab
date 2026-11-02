"""Análise de uma receita: por que esses ingredientes combinam?

Duas evidências independentes:
  * QUÍMICA  — moléculas de sabor compartilhadas (Jaccard entre conjuntos)
  * PRÁTICA  — co-ocorrência em >1 milhão de receitas (NPMI do FlavorGraph)

Pares com muita química e pouca prática são candidatos a combinações novas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from itertools import combinations

import numpy as np
import pandas as pd

from .db import FlavorDB, Resolved


def npmi_label(x: float) -> str:
    if pd.isna(x):
        return "sem dados de receitas"
    if x <= 0:
        return "sem associação acima do acaso em receitas"
    if x < 0.15:
        return "associação fraca em receitas"
    if x < 0.30:
        return "associação comum em receitas"
    return "associação clássica em receitas"


@lru_cache(maxsize=4)
def _pool(db: FlavorDB):
    """Ingredientes candidatos (sem duplicar FlavorDB/FlavorGraph) e matriz de moléculas."""
    dup_fdb = set(db.crosswalk["fdb_id"])
    ids = [i for i in db.profiles if i not in dup_fdb]
    cids = sorted({c for i in ids for c in db.profiles[i]})
    col = {c: k for k, c in enumerate(cids)}
    mat = np.zeros((len(ids), len(cids)), dtype=bool)
    for r, iid in enumerate(ids):
        mat[r, [col[c] for c in db.profiles[iid]]] = True
    freq = dict(zip(cids, mat.sum(axis=0)))  # em quantos ingredientes cada molécula aparece
    return ids, cids, col, mat, freq


def molecule_frequency(db: FlavorDB) -> dict[int, int]:
    return _pool(db)[4]


@dataclass
class RecipeAnalysis:
    name: str
    items: list[Resolved]
    pairs: pd.DataFrame
    bridges: pd.DataFrame
    profile: pd.DataFrame
    suggestions: dict[str, pd.DataFrame] = field(default_factory=dict)
    n_molecules: dict[str, int] = field(default_factory=dict)
    db_names: dict[str, str] = field(default_factory=dict)  # ingredient_id -> nome no banco (inglês)
    warnings: list[str] = field(default_factory=list)


def analyze_recipe(db: FlavorDB, ingredients: list[str], name: str = "receita",
                   n_bridges: int = 40, n_suggestions: int = 12) -> RecipeAnalysis:
    items, warnings = [], []
    for q in ingredients:
        try:
            r = db.resolve(q)
        except KeyError as err:
            warnings.append(str(err))
            continue
        if r.note:
            warnings.append(f"{r.name}: {r.note}")
        items.append(r)

    mols = {r.ingredient_id: db.molecules_of(r.molecules_from) for r in items}
    freq = molecule_frequency(db)

    # ---------------------------------------------------------------- pares
    rows = []
    for a, b in combinations(items, 2):
        ma, mb = mols[a.ingredient_id], mols[b.ingredient_id]
        shared = ma & mb
        union = ma | mb
        # destaques: moléculas compartilhadas com descritor, mais "raras" primeiro
        top = sorted((c for c in shared if db.descriptors_by_molecule.get(c)),
                     key=lambda c: freq.get(c, 0))[:5]
        rows.append({
            "a": a.name, "b": b.name,
            "shared_molecules": len(shared),
            "jaccard": len(shared) / len(union) if union else np.nan,
            "npmi": db.npmi(a.ingredient_id, b.ingredient_id),
            "highlights": ", ".join(
                f"{db.molecule_info(c)['name']} ({'/'.join(db.descriptors_by_molecule[c][:3])})"
                for c in top),
        })
    pairs = pd.DataFrame(rows)
    if len(pairs):
        pairs["recipes"] = pairs["npmi"].map(npmi_label)
        pairs = pairs.sort_values("jaccard", ascending=False, ignore_index=True)

    # ---------------------------------------------------- moléculas-ponte
    owners: dict[int, list[str]] = {}
    for r in items:
        for c in mols[r.ingredient_id]:
            owners.setdefault(c, []).append(r.name)
    brows = []
    for c, who in owners.items():
        if len(who) < 2:
            continue
        info = db.molecule_info(c)
        brows.append({**info, "n_ingredients": len(who), "ingredients": who,
                      "db_frequency": int(freq.get(c, 0))})
    bridges = pd.DataFrame(brows)
    if len(bridges):
        # especificidade (tipo IDF): molécula rara no banco é mais característica
        n_pool = len(_pool(db)[0])
        idf = np.log(n_pool / bridges["db_frequency"].clip(lower=1))
        bridges["score"] = bridges["n_ingredients"] * idf
        bridges["has_descriptor"] = bridges["descriptors"].map(bool)
        bridges = (bridges.sort_values(["has_descriptor", "score"], ascending=False)
                          .head(n_bridges).reset_index(drop=True))

    # ---------------------------------------------------- perfil sensorial
    # fração das moléculas (com descritor) de cada ingrediente que tem o descritor d
    prof = {}
    for r in items:
        terms = [d for c in mols[r.ingredient_id] for d in db.descriptors_by_molecule.get(c, [])]
        n_desc = sum(1 for c in mols[r.ingredient_id] if db.descriptors_by_molecule.get(c))
        if n_desc:
            prof[r.name] = pd.Series(terms, dtype=object).value_counts() / n_desc
    profile = pd.DataFrame(prof).fillna(0.0)
    if len(profile):
        profile = profile.loc[profile.mean(axis=1).sort_values(ascending=False).index]

    analysis = RecipeAnalysis(name, items, pairs, bridges, profile, warnings=warnings,
                              n_molecules={k: len(v) for k, v in mols.items()},
                              db_names={r.ingredient_id: db.name(r.ingredient_id) for r in items})
    analysis.suggestions = suggest(db, items, mols, n_suggestions)
    return analysis


def suggest(db: FlavorDB, items: list[Resolved], mols: dict, n: int) -> dict[str, pd.DataFrame]:
    """O que acrescentar? Ranqueia candidatos por química, prática e 'ousadia'.

    'ousadas' = alta química e nenhuma associação significativa em receitas.
    """
    if not items:
        return {}
    ids, cids, col, mat, _ = _pool(db)
    recipe_vecs = []
    for r in items:
        v = np.zeros(len(cids), dtype=bool)
        v[[col[c] for c in mols[r.ingredient_id] if c in col]] = True
        recipe_vecs.append(v)
    R = np.array(recipe_vecs)                               # (n_receita, n_moléculas)
    inter = mat.astype(np.int32) @ R.T.astype(np.int32)     # (n_cand, n_receita)
    union = mat.sum(1)[:, None] + R.sum(1)[None, :] - inter
    jac = np.where(union > 0, inter / np.maximum(union, 1), 0.0)

    neighbors = [db.recipe_neighbors(r.ingredient_id) for r in items]
    in_recipe = {r.ingredient_id for r in items} | {r.molecules_from for r in items}
    fg_ids = [db._fg_id(i) for i in ids]
    practice = np.array([[nb.get(f, 0.0) if f else 0.0 for nb in neighbors] for f in fg_ids])

    df = pd.DataFrame({
        "ingredient_id": ids,
        "name": [db.display_name(i) for i in ids],
        "category": [db.category(i) for i in ids],
        "chemistry": jac.mean(1),
        "practice": practice.mean(1),
        "linked_in_recipes": (practice > 0).sum(1),
    })
    df = df[~df["ingredient_id"].isin(in_recipe) & (df["chemistry"] < 0.9)]
    bold = df[(df["linked_in_recipes"] == 0)].sort_values("chemistry", ascending=False)
    cols = ["name", "category", "chemistry", "practice", "linked_in_recipes"]
    return {
        "classicas": df.sort_values("practice", ascending=False).head(n)[cols],
        "quimicas": df.sort_values("chemistry", ascending=False).head(n)[cols],
        "ousadas": bold.head(n)[cols],
    }
