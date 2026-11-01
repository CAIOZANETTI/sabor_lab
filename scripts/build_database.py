"""Monta o banco de dados unificado de sabores a partir de FlavorDB + FlavorGraph.

Entradas (geradas pelos scripts de download):
    data/raw/flavordb/entities/*.json      (ou o pacote entities.jsonl.gz)
    data/raw/flavorgraph/nodes_191120.csv
    data/raw/flavorgraph/edges_191120.csv
    data/raw/flavorgraph/dict_ingr2cate.csv

Saídas (data/processed/, Parquet — ~4x menor e ~3x mais rápido de ler que CSV,
e preserva os tipos das colunas; use --csv para exportar também em CSV):
    ingredients.parquet           um ingrediente por linha (FlavorDB e FlavorGraph)
    molecules.parquet             uma molécula por linha (chave: pubchem_id)
    ingredient_molecules.parquet  ingrediente -> molécula (a "composição química")
    molecule_descriptors.parquet  molécula -> descritor sensorial (sweet, woody...)
    ingredient_pairs.parquet      co-ocorrência de ingredientes em receitas (FlavorGraph)
    ingredient_crosswalk.parquet  mesmo ingrediente nas duas fontes (por nome)

Chaves:
    ingredient_id = "fdb:<entity_id>" (FlavorDB) ou "fg:<node_id>" (FlavorGraph)
    pubchem_id    = PubChem CID (inteiro), comum às duas fontes

Uso:
    python scripts/build_database.py          # Parquet
    python scripts/build_database.py --csv    # Parquet + cópia em CSV
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_FDB = ROOT / "data" / "raw" / "flavordb"
RAW_FG = ROOT / "data" / "raw" / "flavorgraph"
OUT = ROOT / "data" / "processed"

FDB_PACK = RAW_FDB / "entities.jsonl.gz"

# Campos de molécula do FlavorDB que vão para molecules.csv (renomeados).
MOLECULE_FIELDS = {
    "pubchem_id": "pubchem_id",
    "common_name": "name",
    "iupac_name": "iupac_name",
    "cas_id": "cas_id",
    "fema_number": "fema_number",
    "smile": "smiles",
    "inchi": "inchi",
    "molecular_weight": "molecular_weight",
    "exact_mass": "exact_mass",
    "xlogp": "xlogp",
    "heavy_atom_count": "heavy_atom_count",
    "complexity": "complexity",
    "topological_polor_surfacearea": "tpsa",
    "hbd_count": "hbd_count",
    "hba_count": "hba_count",
    "num_rotatablebonds": "rotatable_bonds",
    "volume3d": "volume3d",
    "functional_groups": "functional_groups",
    "flavor_profile": "flavor_profile",
    "fema_flavor_profile": "fema_flavor_profile",
    "odor": "odor",
    "taste": "taste",
    "bitter": "bitter",
    "super_sweet": "super_sweet",
    "natural": "natural",
    "synthetic": "synthetic",
    "fooddb_id": "foodb_id",
    "flavornet_id": "flavornet_id",
}
NUMERIC = ["molecular_weight", "exact_mass", "xlogp", "heavy_atom_count", "complexity",
           "tpsa", "hbd_count", "hba_count", "rotatable_bonds", "volume3d"]
EMPTY = {"", "none", "null", "nan", "na", "n/a"}


# ----------------------------------------------------------------------------
# utilidades
# ----------------------------------------------------------------------------
def norm_name(text: str) -> str:
    """'Ground_Cinnamon ' -> 'ground cinnamon' (para cruzar fontes por nome)."""
    text = str(text).lower().replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def clean(value):
    if value is None:
        return np.nan
    if isinstance(value, str) and value.strip().lower() in EMPTY:
        return np.nan
    return value


def split_terms(value, sep: str) -> list[str]:
    value = clean(value)
    if not isinstance(value, str):
        return []
    terms = (t.strip().lower() for t in value.split(sep))
    return [t for t in terms if t and t not in EMPTY]


# ----------------------------------------------------------------------------
# FlavorDB
# ----------------------------------------------------------------------------
def pack_flavordb() -> None:
    """Consolida os JSON individuais num único entities.jsonl.gz (versionado)."""
    src = RAW_FDB / "entities"
    files = sorted(src.glob("*.json"), key=lambda p: int(p.stem)) if src.exists() else []
    if not files:
        return
    with gzip.open(FDB_PACK, "wt", encoding="utf-8") as fh:
        for path in files:
            fh.write(path.read_text(encoding="utf-8").strip() + "\n")
    print(f"FlavorDB: {len(files)} entidades consolidadas em {FDB_PACK.relative_to(ROOT)}")


def load_flavordb() -> list[dict]:
    with gzip.open(FDB_PACK, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def build_flavordb(entities: list[dict]):
    ingredients, links, molecules = [], [], {}
    for ent in entities:
        iid = f"fdb:{ent['entity_id']}"
        mols = ent.get("molecules") or []
        ingredients.append({
            "ingredient_id": iid,
            "source": "flavordb",
            "name": ent.get("entity_alias_readable"),
            "name_norm": norm_name(ent.get("entity_alias_readable", "")),
            "category": ent.get("category_readable"),
            "synonyms": clean(ent.get("entity_alias_synonyms")),
            "scientific_name": clean(ent.get("natural_source_name")),
            "wikipedia_url": clean(ent.get("entity_alias_url")),
            "n_molecules": len(mols),
        })
        for mol in mols:
            cid = pd.to_numeric(mol.get("pubchem_id"), errors="coerce")
            if pd.isna(cid):
                continue
            cid = int(cid)
            links.append({"ingredient_id": iid, "pubchem_id": cid, "source": "flavordb"})
            if cid not in molecules:
                molecules[cid] = {new: clean(mol.get(old)) for old, new in MOLECULE_FIELDS.items()}
                molecules[cid]["pubchem_id"] = cid

    ing = pd.DataFrame(ingredients)
    lnk = pd.DataFrame(links).drop_duplicates()
    mol = pd.DataFrame(list(molecules.values()))
    for col in NUMERIC:
        mol[col] = pd.to_numeric(mol[col], errors="coerce")
    return ing, lnk, mol


def build_descriptors(mol: pd.DataFrame) -> pd.DataFrame:
    """Formato longo: uma linha por (molécula, descritor, origem do descritor)."""
    rows = []
    specs = [("flavor_profile", "@"), ("odor", "@"), ("taste", "@"), ("fema_flavor_profile", ",")]
    for rec in mol.itertuples(index=False):
        for col, sep in specs:
            for term in split_terms(getattr(rec, col), sep):
                rows.append({"pubchem_id": rec.pubchem_id, "descriptor": term, "origin": col})
    return pd.DataFrame(rows).drop_duplicates()


# ----------------------------------------------------------------------------
# FlavorGraph
# ----------------------------------------------------------------------------
def build_flavorgraph():
    nodes = pd.read_csv(RAW_FG / "nodes_191120.csv")
    edges = pd.read_csv(RAW_FG / "edges_191120.csv")
    cats = pd.read_csv(RAW_FG / "dict_ingr2cate.csv")
    cat_map = dict(zip(cats["ingredient"].map(norm_name), cats["category"]))

    ingr = nodes[nodes["node_type"] == "ingredient"].copy()
    ing = pd.DataFrame({
        "ingredient_id": "fg:" + ingr["node_id"].astype(str),
        "source": "flavorgraph",
        "name": ingr["name"],
        "name_norm": ingr["name"].map(norm_name),
        "category": ingr["name"].map(norm_name).map(cat_map),
        "is_hub": ingr["is_hub"].eq("hub"),
    })

    comp = nodes[nodes["node_type"] == "compound"].copy()
    comp["pubchem_id"] = pd.to_numeric(comp["id"], errors="coerce").astype("Int64")
    node2cid = dict(zip(comp["node_id"], comp["pubchem_id"]))
    fg_mol = pd.DataFrame({
        "pubchem_id": comp["pubchem_id"],
        "fg_name": comp["name"],
        "fg_compound_type": comp["is_hub"].map({"food": "flavor", "drug": "drug-like"}),
    }).dropna(subset=["pubchem_id"])

    # ingrediente -> composto
    ic = edges[edges["edge_type"].isin(["ingr-fcomp", "ingr-dcomp"])].copy()
    ic["pubchem_id"] = ic["id_2"].map(node2cid)
    lnk = pd.DataFrame({
        "ingredient_id": "fg:" + ic["id_1"].astype(str),
        "pubchem_id": ic["pubchem_id"],
        "source": "flavorgraph",
    }).dropna(subset=["pubchem_id"])

    # ingrediente <-> ingrediente (co-ocorrência em receitas)
    ii = edges[edges["edge_type"] == "ingr-ingr"]
    pairs = pd.DataFrame({
        "ingredient_a": "fg:" + ii["id_1"].astype(str),
        "ingredient_b": "fg:" + ii["id_2"].astype(str),
        "npmi_score": ii["score"],
    })
    names = dict(zip(ing["ingredient_id"], ing["name"]))
    pairs.insert(2, "name_a", pairs["ingredient_a"].map(names))
    pairs.insert(3, "name_b", pairs["ingredient_b"].map(names))
    return ing, lnk, fg_mol, pairs.sort_values("npmi_score", ascending=False)


# ----------------------------------------------------------------------------
# cruzamento FlavorDB <-> FlavorGraph
# ----------------------------------------------------------------------------
def build_crosswalk(fdb_ing: pd.DataFrame, fg_ing: pd.DataFrame) -> pd.DataFrame:
    """Casa ingredientes por nome normalizado (nome principal ou sinônimo)."""
    fg_by_name = dict(zip(fg_ing["name_norm"], fg_ing["ingredient_id"]))
    rows = []
    for rec in fdb_ing.itertuples(index=False):
        candidates = [(rec.name_norm, "name")]
        if isinstance(rec.synonyms, str):
            candidates += [(norm_name(s), "synonym") for s in rec.synonyms.split(",")]
        for cand, how in candidates:
            if cand in fg_by_name:
                rows.append({"fdb_id": rec.ingredient_id, "fg_id": fg_by_name[cand],
                             "matched_name": cand, "match": how})
                break
    return pd.DataFrame(rows)


def build() -> dict[str, pd.DataFrame]:
    """Monta todas as tabelas em memória (sem gravar)."""
    pack_flavordb()

    fdb_ing, fdb_lnk, fdb_mol = build_flavordb(load_flavordb())
    fg_ing, fg_lnk, fg_mol, pairs = build_flavorgraph()

    # molecules: união das duas fontes pela chave PubChem
    fg_mol = fg_mol.drop_duplicates("pubchem_id")
    fdb_mol["pubchem_id"] = fdb_mol["pubchem_id"].astype("Int64")
    molecules = fdb_mol.merge(fg_mol, on="pubchem_id", how="outer")
    molecules["name"] = molecules["name"].fillna(molecules["fg_name"])
    molecules["in_flavordb"] = molecules["pubchem_id"].isin(fdb_mol["pubchem_id"])
    molecules["in_flavorgraph"] = molecules["pubchem_id"].isin(fg_mol["pubchem_id"])
    molecules = molecules.drop(columns="fg_name").sort_values("pubchem_id", ignore_index=True)
    # colunas de texto com mistura de tipos (ex.: fema_number) -> string
    for col in molecules.columns:
        if molecules[col].dtype == object:
            molecules[col] = molecules[col].astype("string")

    ingredients = pd.concat([fdb_ing, fg_ing], ignore_index=True)
    fg_counts = fg_lnk.groupby("ingredient_id").size()
    mask = ingredients["source"].eq("flavorgraph")
    ingredients.loc[mask, "n_molecules"] = (
        ingredients.loc[mask, "ingredient_id"].map(fg_counts).fillna(0))
    ingredients["n_molecules"] = ingredients["n_molecules"].astype(int)
    ingredients["is_hub"] = ingredients["is_hub"].astype("boolean")

    links = pd.concat([fdb_lnk, fg_lnk], ignore_index=True)
    links["pubchem_id"] = links["pubchem_id"].astype("int64")
    links = links.drop_duplicates(ignore_index=True)
    descriptors = build_descriptors(fdb_mol)
    descriptors["pubchem_id"] = descriptors["pubchem_id"].astype("int64")
    crosswalk = build_crosswalk(fdb_ing, fg_ing)

    return {
        "ingredients": ingredients,
        "molecules": molecules,
        "ingredient_molecules": links,
        "molecule_descriptors": descriptors,
        "ingredient_pairs": pairs.reset_index(drop=True),
        "ingredient_crosswalk": crosswalk,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Monta data/processed/ (Parquet).")
    ap.add_argument("--csv", action="store_true", help="exporta também em CSV")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    for name, df in build().items():
        path = OUT / f"{name}.parquet"
        df.to_parquet(path, index=False, compression="zstd")
        extra = ""
        if args.csv:
            df.to_csv(OUT / f"{name}.csv", index=False)
            extra = " (+ CSV)"
        print(f"{path.name:30s} {len(df):>8,d} linhas  {path.stat().st_size / 1e6:6.2f} MB{extra}")


if __name__ == "__main__":
    main()
