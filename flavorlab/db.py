"""Acesso ao banco de sabores (data/processed/) e perfis moleculares.

Conceito central: cada ingrediente tem um *conjunto de moléculas*. A
composição vem da união de FlavorGraph e FlavorDB (ligados por nome). Quando
um ingrediente não tem moléculas próprias (ex.: "ground_cinnamon"), ele
*herda* as do ingrediente base ("cinnamon"), retirando palavras do início do
nome até achar uma correspondência.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
ALIASES = ROOT / "data" / "ingredient_aliases.csv"
DICTIONARY = ROOT / "data" / "dicionario_ingredientes.csv"  # nomes em português -> ingrediente de sabor

# Unifica variações de descritores sensoriais (singular/plural, sinônimos).
DESCRIPTOR_ALIASES = {
    "fruit": "fruity", "fat": "fatty", "spice": "spicy", "nut": "nutty",
    "herb": "herbal", "flower": "floral", "wood": "woody", "roast": "roasted",
    "oil": "oily", "sulfur": "sulfurous", "sulfury": "sulfurous", "must": "musty",
    "ether": "ethereal", "balsam": "balsamic", "meat": "meaty", "fish": "fishy",
    "smoke": "smoky", "earth": "earthy", "mint": "minty", "wax": "waxy",
    "camphor": "camphoreous", "vanillin": "vanilla", "citric": "citrus",
}
# Nomes ambíguos na herança: "pepper" sozinho é Piper (pimenta-do-reino), mas
# "chili pepper", "bell pepper" etc. são Capsicum, e "sichuan pepper" é Zanthoxylum.
CAPSICUM_HINTS = {
    "chili", "chile", "chilies", "chiles", "bell", "jalapeno", "cayenne", "habanero", "chipotle", "ancho",
    "pasilla", "poblano", "serrano", "banana", "cubanelle", "fresno", "aleppo", "italian", "peppadew",
    "pepperoncini", "pimento", "piquillo", "scotch", "bonnet", "thai", "mexico", "hot", "sweet", "red",
    "green", "yellow", "orange", "roasted", "pickled", "paprika",
}
NO_DATA_HINTS = {"sansho", "szechwan", "sichuan"}  # Zanthoxylum: gênero sem dados no banco

DESCRIPTOR_DROP = {"odorless", "mild", "none", "characteristic", "slight", "faint"}


def norm_name(text: str) -> str:
    text = str(text).lower().replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def alias_key(text: str) -> str:
    """Chave de apelido: sem acento e normalizada ('Açúcar' == 'acucar')."""
    return norm_name(unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode())


@dataclass
class Resolved:
    """Resultado de procurar um ingrediente pelo nome."""
    query: str
    ingredient_id: str
    name: str
    molecules_from: str  # ingredient_id de onde vieram as moléculas
    note: str = ""


class FlavorDB:
    """Banco de sabores em memória. Carregue uma vez e reutilize (consultas em ms)."""

    def __init__(self, path: Path = PROCESSED, aliases: Path | None = ALIASES,
                 dictionary: Path | None = DICTIONARY):
        self.path = Path(path)
        if not (self.path / "ingredients.parquet").exists():
            raise FileNotFoundError(
                f"banco não encontrado em {self.path}. Rode: python scripts/build_database.py")
        read = lambda name: pd.read_parquet(self.path / f"{name}.parquet")  # noqa: E731
        self.ingredients = read("ingredients")
        self.molecules = read("molecules").set_index("pubchem_id")
        self.links = read("ingredient_molecules")
        self.pairs = read("ingredient_pairs")
        self.crosswalk = read("ingredient_crosswalk")
        desc = read("molecule_descriptors")
        desc["descriptor"] = desc["descriptor"].replace(DESCRIPTOR_ALIASES)
        noisy = (desc["descriptor"].str.split().str.len() > 3) | desc["descriptor"].str.contains("odor")
        self.descriptors = (desc[~desc["descriptor"].isin(DESCRIPTOR_DROP) & ~noisy]
                            .drop_duplicates(["pubchem_id", "descriptor"]))

        # índices em dicionário: consultas O(1) em vez de filtrar DataFrames
        self._names = dict(zip(self.ingredients["ingredient_id"], self.ingredients["name"]))
        self._category = dict(zip(self.ingredients["ingredient_id"], self.ingredients["category"]))
        self._fdb2fg = dict(zip(self.crosswalk["fdb_id"], self.crosswalk["fg_id"]))

        # apelidos curados (editáveis): nome -> ingrediente base, com justificativa
        self.aliases: dict[str, tuple[str, str]] = {}
        # nomes em português do dicionário: redirecionam por completo para o ingrediente de sabor
        self.pt_names: dict[str, str] = {}
        if dictionary and Path(dictionary).exists():
            d = pd.read_csv(dictionary, dtype=str).fillna("")
            self.pt_names = {alias_key(n): b for n, b in zip(d["nome"], d["sabor"]) if b}
            # inverso (inglês -> português), para exibir sugestões em português
            self._pt_label: dict[str, str] = {}
            for n, b in zip(d["nome"], d["sabor"]):
                self._pt_label.setdefault(alias_key(b), n)
        if aliases and Path(aliases).exists():
            al = pd.read_csv(aliases, dtype=str).fillna("")
            self.aliases.update({alias_key(n): (norm_name(b), j)
                                 for n, b, j in zip(al["nome"], al["base"], al["justificativa"])})

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

    def display_name(self, iid: str) -> str:
        """'noz-moscada (nutmeg)' quando há nome em português no dicionário."""
        en = self.name(iid)
        pt = getattr(self, "_pt_label", {}).get(alias_key(en))
        return f"{pt} ({en})" if pt else en

    def category(self, iid: str):
        return self._category.get(iid)

    def molecules_of(self, iid: str) -> frozenset[int]:
        return self.profiles.get(iid, frozenset())

    # -------------------------------------------------------------- resolução
    def resolve(self, query: str) -> Resolved:
        """Acha o ingrediente pelo id ('fg:1368') ou nome em inglês ('cinnamon')."""
        query = str(query).strip()
        target = self.pt_names.get(alias_key(query))
        if target and alias_key(target) != alias_key(query):
            r = self.resolve(target)
            # exibe o nome em português digitado; o id/moléculas são do ingrediente de sabor
            return Resolved(query, r.ingredient_id, query, r.molecules_from, r.note)
        if query in self._names:
            iid = query
        else:
            ids = self._by_name.get(norm_name(query))
            if not ids:
                alias = self.aliases.get(alias_key(query))
                if alias:  # nome fora do banco (ex.: em português) -> ingrediente base
                    r = self.resolve(alias[0])
                    return Resolved(query, r.ingredient_id, r.name, r.molecules_from, r.note)
                raise KeyError(f"ingrediente não encontrado: {query!r}. "
                               f"Parecidos: {self.search(query, 8)['name'].tolist()}")
            # prefere um id que tenha moléculas
            iid = next((i for i in ids if i in self.profiles), ids[0])

        if iid in self.profiles:
            return Resolved(query, iid, self.name(iid), iid)

        # apelido curado (data/ingredient_aliases.csv) tem prioridade sobre a heurística
        alias = self.aliases.get(alias_key(self.name(iid)))
        if alias:
            for cand in self._by_name.get(alias[0], []):
                if cand in self.profiles:
                    # apelidos do dicionário (sem justificativa) não geram aviso
                    note = f"moléculas de '{self.name(cand)}' — {alias[1]}" if alias[1] else ""
                    return Resolved(query, iid, self.name(iid), cand, note=note)

        # herança: tira palavras do início ("ground cinnamon" -> "cinnamon")
        words = norm_name(self.name(iid)).split()
        for k in range(1, len(words)):
            base = " ".join(words[k:])
            if base == "pepper":  # ambíguo: decide o gênero botânico pelo resto do nome
                if NO_DATA_HINTS & set(words):
                    break
                if CAPSICUM_HINTS & set(words):
                    base = "capsicum"
            for cand in self._by_name.get(base, []):
                if cand in self.profiles:
                    note = f"moléculas herdadas de '{self.name(cand)}'"
                    if base == "capsicum":
                        note += " (gênero Capsicum: pimentas e pimentões)"
                    return Resolved(query, iid, self.name(iid), cand, note=note)
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
    def _fg_id(self, iid: str) -> str | None:
        return iid if iid.startswith("fg:") else self._fdb2fg.get(iid)

    def npmi(self, a: str, b: str) -> float:
        """Co-ocorrência em receitas (FlavorGraph). 0 = sem associação acima do acaso."""
        fa, fb = self._fg_id(a), self._fg_id(b)
        if not fa or not fb:
            return np.nan
        return self.recipe_neighbors(fa).get(fb, 0.0)

    @cached_property
    def _neighbors(self) -> dict[str, dict[str, float]]:
        """fg_id -> {fg_id vizinho: NPMI} (grafo de receitas como lista de adjacência)."""
        adj: dict[str, dict[str, float]] = {}
        for a, b, w in zip(self.pairs["ingredient_a"], self.pairs["ingredient_b"],
                           self.pairs["npmi_score"]):
            adj.setdefault(a, {})[b] = w
            adj.setdefault(b, {})[a] = w
        return adj

    def recipe_neighbors(self, iid: str) -> dict[str, float]:
        """Todos os ingredientes que co-ocorrem com iid em receitas -> score."""
        f = self._fg_id(iid)
        return self._neighbors.get(f, {}) if f else {}

    # ------------------------------------------------------------- descritores
    @cached_property
    def descriptors_by_molecule(self) -> dict[int, list[str]]:
        return self.descriptors.groupby("pubchem_id")["descriptor"].agg(list).to_dict()

    @cached_property
    def _molecule_records(self) -> dict[int, dict]:
        cols = ["name", "molecular_weight", "xlogp", "functional_groups"]
        df = self.molecules[cols].astype(object).where(self.molecules[cols].notna(), None)
        return df.to_dict("index")

    def molecule_info(self, cid: int) -> dict:
        rec = self._molecule_records.get(cid, {})
        return {
            "pubchem_id": cid,
            "name": rec.get("name") or str(cid),
            "descriptors": self.descriptors_by_molecule.get(cid, []),
            "molecular_weight": rec.get("molecular_weight"),
            "xlogp": rec.get("xlogp"),
            "functional_groups": rec.get("functional_groups"),
        }
