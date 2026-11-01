"""Acesso ao banco de sabores (data/processed/) e perfis moleculares.

Conceito central: cada ingrediente tem um *conjunto de moléculas*. A
composição vem da união de FlavorGraph e FlavorDB (ligados por nome). Quando
um ingrediente não tem moléculas próprias (ex.: "ground_cinnamon"), ele
*herda* as do ingrediente base ("cinnamon"), retirando palavras do início do
nome até achar uma correspondência.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

# Unifica variações de descritores sensoriais (singular/plural, sinônimos).
DESCRIPTOR_ALIASES = {
    "fruit": "fruity", "fat": "fatty", "spice": "spicy", "nut": "nutty",
    "herb": "herbal", "flower": "floral", "wood": "woody", "roast": "roasted",
    "oil": "oily", "sulfur": "sulfurous", "sulfury": "sulfurous", "must": "musty",
    "ether": "ethereal", "balsam": "balsamic", "meat": "meaty", "fish": "fishy",
    "smoke": "smoky", "earth": "earthy", "mint": "minty", "wax": "waxy",
    "camphor": "camphoreous", "vanillin": "vanilla", "citric": "citrus",
}
DESCRIPTOR_DROP = {"odorless", "mild", "none", "characteristic", "slight", "faint"}


def norm_name(text: str) -> str:
    text = str(text).lower().replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Resolved:
    """Resultado de procurar um ingrediente pelo nome."""
    query: str
    ingredient_id: str
    name: str
    molecules_from: str  # ingredient_id de onde vieram as moléculas
    note: str = ""


class FlavorDB:
    def __init__(self, path: Path = PROCESSED):
        self.path = Path(path)
        self.ingredients = pd.read_csv(self.path / "ingredients.csv")
        self.molecules = pd.read_csv(self.path / "molecules.csv").set_index("pubchem_id")
        self.links = pd.read_csv(self.path / "ingredient_molecules.csv")
        self.pairs = pd.read_csv(self.path / "ingredient_pairs.csv")
        self.crosswalk = pd.read_csv(self.path / "ingredient_crosswalk.csv")
        desc = pd.read_csv(self.path / "molecule_descriptors.csv")
        desc["descriptor"] = desc["descriptor"].replace(DESCRIPTOR_ALIASES)
        noisy = (desc["descriptor"].str.split().str.len() > 3) | desc["descriptor"].str.contains("odor")
        self.descriptors = (desc[~desc["descriptor"].isin(DESCRIPTOR_DROP) & ~noisy]
                            .drop_duplicates(["pubchem_id", "descriptor"]))

        self._names = dict(zip(self.ingredients["ingredient_id"], self.ingredients["name"]))
        self._category = dict(zip(self.ingredients["ingredient_id"], self.ingredients["category"]))

    # ------------------------------------------------------------------ perfis
    @cached_property
    def profiles(self) -> dict[str, frozenset[int]]:
        """ingredient_id -> conjunto de pubchem_ids (FlavorGraph ∪ FlavorDB)."""
        own = self.links.groupby("ingredient_id")["pubchem_id"].agg(frozenset).to_dict()
        merged = dict(own)
        # FlavorGraph herda moléculas do mesmo ingrediente no FlavorDB e vice-versa
        for fdb_id, fg_id in zip(self.crosswalk["fdb_id"], self.crosswalk["fg_id"]):
            union = own.get(fdb_id, frozenset()) | own.get(fg_id, frozenset())
            merged[fg_id] = merged[fdb_id] = union
        return {k: v for k, v in merged.items() if v}

    @cached_property
    def _by_name(self) -> dict[str, list[str]]:
        """name_norm -> ingredient_ids (FlavorGraph primeiro: tem dados de receitas)."""
        out: dict[str, list[str]] = {}
        df = self.ingredients.sort_values("source", ascending=False)  # flavorgraph antes
        for iid, name in zip(df["ingredient_id"], df["name_norm"]):
            out.setdefault(name, []).append(iid)
        for iid, syn in zip(self.ingredients["ingredient_id"], self.ingredients.get("synonyms")):
            if isinstance(syn, str):
                for s in syn.split(","):
                    out.setdefault(norm_name(s), []).append(iid)
        return out

    def name(self, iid: str) -> str:
        return self._names.get(iid, iid)

    def category(self, iid: str):
        return self._category.get(iid)

    def molecules_of(self, iid: str) -> frozenset[int]:
        return self.profiles.get(iid, frozenset())

    # -------------------------------------------------------------- resolução
    def resolve(self, query: str) -> Resolved:
        """Acha o ingrediente pelo id ('fg:1368') ou nome em inglês ('cinnamon')."""
        query = str(query).strip()
        if query in self._names:
            iid = query
        else:
            ids = self._by_name.get(norm_name(query))
            if not ids:
                raise KeyError(f"ingrediente não encontrado: {query!r}. "
                               f"Parecidos: {self.search(query, 8)['name'].tolist()}")
            # prefere um id que tenha moléculas
            iid = next((i for i in ids if i in self.profiles), ids[0])

        if iid in self.profiles:
            return Resolved(query, iid, self.name(iid), iid)

        # herança: tira palavras do início ("ground cinnamon" -> "cinnamon")
        words = norm_name(self.name(iid)).split()
        for k in range(1, len(words)):
            base = " ".join(words[k:])
            for cand in self._by_name.get(base, []):
                if cand in self.profiles:
                    return Resolved(query, iid, self.name(iid), cand,
                                    note=f"moléculas herdadas de '{self.name(cand)}'")
        return Resolved(query, iid, self.name(iid), iid, note="sem dados moleculares")

    def search(self, text: str, limit: int = 20) -> pd.DataFrame:
        """Busca por trecho do nome (inglês). Mostra quem tem dados moleculares."""
        pat = norm_name(text)
        df = self.ingredients[self.ingredients["name_norm"].str.contains(pat, regex=False, na=False)]
        df = df.assign(has_molecules=df["ingredient_id"].isin(self.profiles.keys()),
                       name_len=df["name_norm"].str.len())
        return (df.sort_values(["has_molecules", "name_len"], ascending=[False, True])
                  .head(limit)[["ingredient_id", "name", "source", "category", "has_molecules"]])

    # ------------------------------------------------------------ co-ocorrência
    @cached_property
    def _npmi(self) -> dict[frozenset, float]:
        return {frozenset((a, b)): s for a, b, s in
                zip(self.pairs["ingredient_a"], self.pairs["ingredient_b"], self.pairs["npmi_score"])}

    def _fg_id(self, iid: str) -> str | None:
        if iid.startswith("fg:"):
            return iid
        hit = self.crosswalk.loc[self.crosswalk["fdb_id"] == iid, "fg_id"]
        return hit.iloc[0] if len(hit) else None

    def npmi(self, a: str, b: str) -> float:
        """Co-ocorrência em receitas (FlavorGraph). 0 = não aparecem juntos com frequência."""
        fa, fb = self._fg_id(a), self._fg_id(b)
        if not fa or not fb:
            return np.nan
        return self._npmi.get(frozenset((fa, fb)), 0.0)

    def recipe_neighbors(self, iid: str) -> dict[str, float]:
        """Todos os ingredientes que co-ocorrem com iid em receitas -> score."""
        f = self._fg_id(iid)
        if not f:
            return {}
        p = self.pairs
        a = p.loc[p["ingredient_a"] == f, ["ingredient_b", "npmi_score"]].to_numpy()
        b = p.loc[p["ingredient_b"] == f, ["ingredient_a", "npmi_score"]].to_numpy()
        return {k: float(v) for k, v in np.vstack([a, b])} if len(a) + len(b) else {}

    # ------------------------------------------------------------- descritores
    @cached_property
    def descriptors_by_molecule(self) -> dict[int, list[str]]:
        return self.descriptors.groupby("pubchem_id")["descriptor"].agg(list).to_dict()

    def molecule_info(self, cid: int) -> dict:
        row = self.molecules.loc[cid] if cid in self.molecules.index else None
        get = (lambda c: row[c] if row is not None and c in row and pd.notna(row[c]) else None)
        return {
            "pubchem_id": cid,
            "name": get("name") or str(cid),
            "descriptors": self.descriptors_by_molecule.get(cid, []),
            "molecular_weight": get("molecular_weight"),
            "xlogp": get("xlogp"),
            "functional_groups": get("functional_groups"),
        }
