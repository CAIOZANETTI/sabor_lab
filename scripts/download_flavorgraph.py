"""Baixa os dados do FlavorGraph (Park et al., Scientific Reports, 2021).

Repositório: https://github.com/lamypark/FlavorGraph  (licença Apache 2.0)

O FlavorGraph é um grafo com ~8,3 mil nós e ~147 mil arestas:
  - nós: 6.653 ingredientes (de >1 milhão de receitas, Recipe1M)
         1.645 compostos químicos (id = PubChem CID)
  - arestas:
      ingr-ingr   -> co-ocorrência em receitas (score = PMI normalizado)
      ingr-fcomp  -> ingrediente contém composto de sabor (food compound)
      ingr-dcomp  -> ingrediente contém composto "drug-like"

Uso:
    python scripts/download_flavorgraph.py
"""

from __future__ import annotations

import urllib.parse
import urllib.request
from pathlib import Path

RAW_BASE = "https://raw.githubusercontent.com/lamypark/FlavorGraph/master/"
FILES = [
    "LICENSE",
    "input/nodes_191120.csv",
    "input/edges_191120.csv",
    "input/node_classification_hub.csv",
    "input/dict_ingr2cate - Top300+FDB400+HyperFoods104=616.csv",
]
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "raw" / "flavorgraph"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for rel in FILES:
        url = RAW_BASE + urllib.parse.quote(rel)
        name = Path(rel).name
        if name.startswith("dict_ingr2cate"):
            name = "dict_ingr2cate.csv"  # nome original tem espaços e '+'
        out = OUT_DIR / name
        with urllib.request.urlopen(url, timeout=120) as resp:
            out.write_bytes(resp.read())
        print(f"{rel} -> {out.relative_to(ROOT)} ({out.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
