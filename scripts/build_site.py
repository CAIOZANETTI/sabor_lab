"""Monta o site estático publicado pelo GitHub Pages."""

from __future__ import annotations

import argparse
import html
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
STATIC = ROOT / "site"


def report_title(path: Path) -> str:
    document = path.read_text(encoding="utf-8")
    match = re.search(r"<title>(.*?)</title>", document, flags=re.IGNORECASE | re.DOTALL)
    return html.unescape(match.group(1)).strip() if match else path.stem


def build_site(output: Path) -> list[Path]:
    output = output.resolve()
    reports_output = output / "reports"
    reports_output.mkdir(parents=True, exist_ok=True)

    for page in STATIC.glob("*.html"):
        shutil.copy2(page, output / page.name)

    reports = sorted(REPORTS.glob("*.html"))
    if not reports:
        raise SystemExit("nenhum relatório HTML encontrado em reports/")

    cards = []
    for report in reports:
        shutil.copy2(report, reports_output / report.name)
        cards.append(
            f'<a class="card" href="reports/{html.escape(report.name)}">'
            f'<span class="tag">Relatório interativo</span>'
            f'<strong>{html.escape(report_title(report))}</strong>'
            f'<span>Explorar moléculas, combinações e nutrição →</span></a>'
        )

    page = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="SaborLab: sabor molecular, nutrição e cultura para criar receitas calculadas.">
  <title>SaborLab</title>
  <style>
    :root {{ color-scheme: light; --ink:#18221c; --muted:#56635a; --paper:#f5f2e9;
      --card:#fffdf7; --accent:#b94824; --line:#d9d4c6; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:var(--paper);
      font:17px/1.6 system-ui,-apple-system,Segoe UI,sans-serif; }}
    main {{ width:min(980px, calc(100% - 2rem)); margin:0 auto; padding:5rem 0; }}
    .eyebrow {{ color:var(--accent); font-weight:750; letter-spacing:.12em;
      text-transform:uppercase; font-size:.8rem; }}
    h1 {{ max-width:800px; margin:.4rem 0 1rem; font:700 clamp(3rem,9vw,6.8rem)/.92 Georgia,serif; }}
    .intro {{ max-width:720px; color:var(--muted); font-size:1.15rem; }}
    .actions {{ display:flex; gap:.8rem; flex-wrap:wrap; margin:1.5rem 0 0; }}
    .button {{ display:inline-block; padding:.7rem 1rem; border-radius:999px; color:#fff;
      background:var(--accent); text-decoration:none; font-weight:700; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
      gap:1rem; margin:3rem 0; }}
    .card {{ min-height:210px; display:flex; flex-direction:column; gap:.7rem;
      padding:1.4rem; color:inherit; text-decoration:none; background:var(--card);
      border:1px solid var(--line); border-radius:18px; transition:.18s ease; }}
    .card:hover {{ transform:translateY(-3px); border-color:var(--accent); box-shadow:0 12px 30px #352b1a12; }}
    .card strong {{ font:700 1.45rem/1.2 Georgia,serif; }}
    .card span:last-child {{ margin-top:auto; color:var(--muted); }}
    .tag {{ color:var(--accent); font-size:.78rem; font-weight:700; text-transform:uppercase; }}
    footer {{ margin-top:4rem; padding-top:1.2rem; border-top:1px solid var(--line); color:var(--muted); }}
    a {{ color:var(--accent); }}
  </style>
</head>
<body>
  <main>
    <span class="eyebrow">Sabor molecular + nutrição + cultura</span>
    <h1>SaborLab</h1>
    <p class="intro">Um laboratório para transformar ingredientes em receitas e receitas em escolhas calculadas, combinando sabor, nutrição, porções e contexto cultural.</p>
    <div class="actions"><a class="button" href="sobre.html">Entenda como funciona</a></div>
    <section class="grid" aria-label="Relatórios disponíveis">
      {''.join(cards)}
    </section>
    <footer>
      <p>Projeto experimental e não comercial. Consulte as <a href="https://github.com/CAIOZANETTI/science_spice/blob/main/data/SOURCES.md">fontes, licenças e referências</a> ou veja o <a href="https://github.com/CAIOZANETTI/science_spice">código no GitHub</a>.</p>
    </footer>
  </main>
</body>
</html>
"""
    (output / "index.html").write_text(page, encoding="utf-8")
    (output / ".nojekyll").touch()
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "_site")
    args = parser.parse_args()
    reports = build_site(args.output)
    print(f"site criado em {args.output.resolve()} com {len(reports)} relatório(s)")


if __name__ == "__main__":
    main()
