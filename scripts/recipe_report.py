"""Gera o relatório HTML (grafo + embasamento científico) de receitas.

Lê data/experiments/receitas.csv e receita_ingredientes.csv e grava um HTML
por receita em reports/<recipe_id>.html.

Para cada ingrediente, o banco é consultado nesta ordem:
    ingredient_id  ->  nome_no_banco (inglês, ex.: "black_pepper")  ->  ingrediente

Uso:
    python scripts/recipe_report.py                    # todas as receitas
    python scripts/recipe_report.py --recipe R001      # uma receita
    python scripts/recipe_report.py --ingredients "tomato,basil,garlic" --name "teste rápido"
    python scripts/recipe_report.py --search pepper    # procurar nomes no banco
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flavorlab import FlavorDB, analyze_recipe  # noqa: E402
from flavorlab.report import render_html  # noqa: E402

EXP = ROOT / "data" / "experiments"
REPORTS = ROOT / "reports"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_") or "receita"


def pick_query(row: pd.Series) -> str | None:
    for col in ("ingredient_id", "nome_no_banco", "ingrediente"):
        val = row.get(col)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--recipe", help="recipe_id a gerar (padrão: todas)")
    ap.add_argument("--ingredients", help="lista separada por vírgula (modo rápido)")
    ap.add_argument("--name", default="teste rápido")
    ap.add_argument("--search", help="procura ingredientes no banco pelo nome (inglês)")
    args = ap.parse_args()

    db = FlavorDB()

    if args.search:
        print(db.search(args.search, 30).to_string(index=False))
        return

    if args.ingredients:
        items = [s.strip() for s in args.ingredients.split(",") if s.strip()]
        out = REPORTS / f"{slug(args.name)}.html"
        render_html(analyze_recipe(db, items, args.name), out=out)
        print(f"-> {out.relative_to(ROOT)}")
        return

    recipes = pd.read_csv(EXP / "receitas.csv", dtype=str)
    lines = pd.read_csv(EXP / "receita_ingredientes.csv", dtype=str)
    if args.recipe:
        recipes = recipes[recipes["recipe_id"] == args.recipe]
    if recipes.empty:
        sys.exit("nenhuma receita encontrada em data/experiments/receitas.csv")

    for rec in recipes.to_dict("records"):
        rows = lines[lines["recipe_id"] == rec["recipe_id"]]
        queries = [q for q in (pick_query(r) for _, r in rows.iterrows()) if q]
        analysis = analyze_recipe(db, queries, rec.get("nome") or rec["recipe_id"])
        meta = {
            "Data": rec.get("data"), "Técnica": rec.get("tecnica"),
            "Nota": rec.get("nota_geral"), "Por que gostei": rec.get("por_que_gostei"),
            "Observações": rec.get("observacoes"),
        }
        out = REPORTS / f"{rec['recipe_id']}.html"
        render_html(analysis, meta, out=out)
        print(f"{rec['recipe_id']}: {len(analysis.items)} ingredientes -> {out.relative_to(ROOT)}")
        for w in analysis.warnings:
            print(f"   aviso: {w}")


if __name__ == "__main__":
    main()
