"""Gera a roda de aromas (HTML interativo, Plotly) de um ou mais ingredientes.

Uso:
    python scripts/flavor_wheel.py canela tomate
    python scripts/flavor_wheel.py canela --partners 64 --descriptors 10 --out reports/

Saída: reports/roda_<ingrediente>.html (Plotly via CDN, como os demais relatórios).
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flavorlab import FlavorDB  # noqa: E402
from flavorlab.catalog import Catalog  # noqa: E402
from flavorlab.flavor_wheel import wheel_data, wheel_figure  # noqa: E402


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ingredients", nargs="+", help="nomes em português ou inglês (ou IDs fdb:/fg:)")
    ap.add_argument("--descriptors", type=int, default=8)
    ap.add_argument("--partners", type=int, default=48)
    ap.add_argument("--out", type=Path, default=ROOT / "reports")
    args = ap.parse_args(argv)
    db, cat = FlavorDB(), Catalog.load()
    args.out.mkdir(parents=True, exist_ok=True)
    for ing in args.ingredients:
        data = wheel_data(db, ing, n_descriptors=args.descriptors, n_partners=args.partners, catalog=cat)
        path = args.out / f"roda_{slug(ing)}.html"
        wheel_figure(data).write_html(path, include_plotlyjs="cdn", full_html=True)
        print(f"{ing}: {len(data.partners)} ingredientes em {len(data.sectors)} setores -> {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
