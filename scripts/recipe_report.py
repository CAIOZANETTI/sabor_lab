"""Gera o relatório HTML (sabor + nutrição) de receitas.

Lê data/experiments/receitas.csv e receita_ingredientes.csv e grava um HTML
por receita em reports/<recipe_id>.html.

Cada ingrediente é escrito em português (coluna `ingrediente`) e resolvido pelo
dicionário data/dicionario_ingredientes.csv. Colunas opcionais:
    gramas         peso em g (vale sobre quantidade+unidade)
    nome_no_banco  ingrediente do banco de sabores (inglês), se quiser forçar
    alimento       id nutricional (taco:<n> ou usda:<fdc_id>), se quiser forçar
Unidades aceitas: g, kg, mg, ml, l, xícara, colher de sopa/chá/sobremesa/café,
copo americano, pitada, unidade, dente, fatia, folha... e imperiais
(cup, tbsp, tsp, oz, lb, fl oz, pint, quart) — tudo convertido para o métrico.

Uso:
    python scripts/recipe_report.py                    # todas as receitas
    python scripts/recipe_report.py --recipe R001      # uma receita
    python scripts/recipe_report.py --ingredients "tomate,manjericão,alho" --name "teste"
    python scripts/recipe_report.py --search pimenta   # procurar no banco de sabores
    python scripts/recipe_report.py --search-food "queijo minas"   # procurar alimento (nutrição)
    python scripts/recipe_report.py --temperature-experiment data/experiments/exemplo.json
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
from flavorlab.nutrition import NutritionDB  # noqa: E402
from flavorlab.nutrition_report import nutrition_section  # noqa: E402
from flavorlab.report import render_html  # noqa: E402
from flavorlab.units import metricize_text  # noqa: E402

EXP = ROOT / "data" / "experiments"
REPORTS = ROOT / "reports"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_") or "receita"


def _get(row: dict, col: str) -> str | None:
    val = row.get(col)
    return val.strip() if isinstance(val, str) and val.strip() else None


def flavor_query(row: dict) -> str | None:
    for col in ("nome_no_banco", "ingredient_id", "ingrediente"):
        if _get(row, col):
            return _get(row, col)
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--recipe", help="recipe_id a gerar (padrão: todas)")
    ap.add_argument("--ingredients", help="lista separada por vírgula (modo rápido, só sabor)")
    ap.add_argument("--name", default="teste rápido")
    ap.add_argument("--search", help="procura ingredientes no banco de sabores (inglês)")
    ap.add_argument("--search-food", help="procura alimentos no banco nutricional (português ou inglês)")
    ap.add_argument("--temperature-experiment", type=Path,
                    help="JSON térmico/sensorial; gera relatório separado sem recalcular sabor/nutrição")
    ap.add_argument("--temperature-output", type=Path, help="HTML do relatório térmico")
    args = ap.parse_args()

    if args.temperature_experiment:
        from scripts.temperature_report import generate_report
        output = args.temperature_output or REPORTS / f"{args.temperature_experiment.stem}.html"
        html_path, json_path = generate_report(args.temperature_experiment, output)
        print(f"relatório térmico: {html_path}")
        print(f"resultado térmico: {json_path}")
        return

    if args.search_food:
        print(NutritionDB().search(args.search_food, 30).to_string(index=False))
        return

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

    ndb = NutritionDB()
    recipes = pd.read_csv(EXP / "receitas.csv", dtype=str).fillna("")
    lines = pd.read_csv(EXP / "receita_ingredientes.csv", dtype=str).fillna("")
    if args.recipe:
        recipes = recipes[recipes["recipe_id"] == args.recipe]
    if recipes.empty:
        sys.exit("nenhuma receita encontrada em data/experiments/receitas.csv")

    for rec in recipes.to_dict("records"):
        rows = lines[lines["recipe_id"] == rec["recipe_id"]].to_dict("records")
        analysis = analyze_recipe(db, [q for q in map(flavor_query, rows) if q], rec.get("nome") or rec["recipe_id"])
        nutri_rows = [{"nome": r["ingrediente"], "quantidade": r.get("quantidade"), "unidade": r.get("unidade"),
                       "gramas": r.get("gramas"), "alimento": _get(r, "alimento")}
                      for r in rows if _get(r, "ingrediente") and (_get(r, "quantidade") or _get(r, "gramas"))]
        porcoes = pd.to_numeric(rec.get("porcoes"), errors="coerce")
        nutri = ndb.recipe(nutri_rows, portions=float(porcoes) if pd.notna(porcoes) else 1.0)
        meta = {
            "Data": rec.get("data"), "Técnica": metricize_text(rec.get("tecnica")), "Porções": rec.get("porcoes"),
            "Nota": rec.get("nota_geral"), "Por que gostei": rec.get("por_que_gostei"),
            "Observações": metricize_text(rec.get("observacoes")),
        }
        out = REPORTS / f"{rec['recipe_id']}.html"
        render_html(analysis, meta, out=out, extra_html=nutrition_section(nutri, ndb))
        kcal = nutri.per_portion.get("energia_kcal")
        print(f"{rec['recipe_id']}: {len(analysis.items)} ingredientes (sabor), {len(nutri.lines)} (nutrição), "
              f"{kcal:.0f} kcal/porção -> {out.relative_to(ROOT)}")
        for w in analysis.warnings + nutri.warnings:
            print(f"   aviso: {w}")


if __name__ == "__main__":
    main()
