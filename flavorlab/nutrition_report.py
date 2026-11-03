"""Seção de nutrição do relatório HTML (tabelas + gráficos plotly)."""

from __future__ import annotations

import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .nutrition import MAIN, VDR, NutritionDB, NutritionResult
from .units import fmt_num

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
SURFACE, TEXT, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
LAYOUT = dict(
    paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
    font=dict(family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif", color=TEXT, size=13),
    margin=dict(l=10, r=10, t=50, b=10),
    hoverlabel=dict(bgcolor="white", font_color=TEXT, bordercolor=GRID),
)
# fatores gerais de Atwater (kcal/g)
ATWATER = [("proteina_g", "Proteínas", 4), ("carboidrato_g", "Carboidratos", 4),
           ("lipideos_g", "Gorduras", 9), ("alcool_g", "Álcool", 7)]
TILES = ["energia_kcal", "proteina_g", "carboidrato_g", "acucares_g", "lipideos_g", "fibra_g", "sodio_mg"]

CSS = f"""
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:.6rem;margin:1rem 0}}
.tile{{background:#fff;border:1px solid {GRID};border-radius:8px;padding:.6rem .8rem}}
.tile .v{{font-size:1.45rem;font-weight:600;font-variant-numeric:tabular-nums}} .tile .l{{color:{MUTED};font-size:.85em}}
.num{{text-align:right;font-variant-numeric:tabular-nums}} tr.tot td{{font-weight:600;border-top:2px solid {GRID}}}
.vdbar{{background:#eef3fb;border-radius:3px;height:10px;width:160px;display:inline-block;vertical-align:middle}}
.vdbar i{{display:block;height:10px;border-radius:3px;background:{SERIES[0]}}}
.scroll{{overflow-x:auto}}
"""


def _v(x, nd=1) -> str:
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else fmt_num(float(x), nd)


def _fig_energy_by_ingredient(nr: NutritionResult) -> go.Figure:
    e = nr.table.get("energia_kcal", pd.Series(dtype=float)).fillna(0).sort_values()
    fig = go.Figure(go.Bar(
        x=e.values, y=e.index, orientation="h", marker=dict(color=SERIES[0], line=dict(color=SURFACE, width=2)),
        text=[f"{fmt_num(v, 0)} kcal" for v in e.values], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: %{x:.0f} kcal<extra></extra>"))
    fig.update_layout(**LAYOUT, title="Energia por ingrediente (receita inteira)", height=120 + 30 * len(e),
                      xaxis=dict(title="kcal", gridcolor=GRID, range=[0, max(e.max(), 1) * 1.25]), showlegend=False)
    return fig


def _fig_energy_origin(nr: NutritionResult) -> go.Figure:
    kcal = {name: float(nr.total.get(key, 0) or 0) * f for key, name, f in ATWATER}
    tot = sum(kcal.values()) or 1.0
    kcal = {k: v for k, v in kcal.items() if v / tot >= 0.005}  # omite fatias < 0,5%
    names = list(kcal)[::-1]
    fig = go.Figure(go.Bar(
        x=[kcal[n] / tot * 100 for n in names], y=names, orientation="h",
        marker=dict(color=SERIES[1], line=dict(color=SURFACE, width=2)),
        text=[f"{kcal[n] / tot:.0%}" for n in names], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: %{x:.1f}% da energia<extra></extra>"))
    fig.update_layout(**LAYOUT, title="De onde vem a energia (fatores de Atwater)", height=120 + 34 * len(names),
                      xaxis=dict(title="% das kcal", gridcolor=GRID, range=[0, 100]), showlegend=False)
    return fig


CAT_LABEL = {"measured": ("M", "medido"), "derived": ("D", "derivado"), "estimated": ("E", "estimado"),
             "unknown": ("?", "desconhecido")}
PATH_LABEL = {"measured_prepared": "registro do alimento preparado", "derived_from_raw": "derivado do cru",
              "as_recorded": "como registrado (sem preparo)", "not_computable": "fora do cálculo"}
YIELD_LABEL = {"observed": "pesado", "table": "tabela USDA", "not_reconstructible": "não reconstruível (sem peso cru)",
               "unknown": "desconhecido", "not_applicable": "—"}


def _cell(value, cat: str, nd=1) -> str:
    mark, name = CAT_LABEL[cat]
    if cat == "unknown":
        return f"<td class='num muted' title='{name}'>?</td>"
    return f"<td class='num' title='{name}'>{_v(value, nd)} <sup>{mark}</sup></td>"


def prepared_section(pr, ndb: NutritionDB) -> str:
    """Nutrição após preparo (demanda 007): medido, derivado e estimado lado a lado, nunca somados às cegas."""
    keys = [k for k in MAIN]
    head = "".join(f"<th class='num'>{html.escape(ndb.label(k))}</th>" for k in keys)
    body = []
    for it in pr.items:
        ylab = YIELD_LABEL.get(it.yield_status, it.yield_status)
        yf = f"{fmt_num(it.yield_factor.factor, 2)} ({ylab})" if it.yield_factor else ylab
        masses = " / ".join(_v(m, 0) for m in (it.initial_mass_g, it.cooked_mass_g, it.served_mass_g))
        body.append(f"<tr><td><b>{html.escape(it.name)}</b><br><span class='muted'>"
                    f"{html.escape(PATH_LABEL.get(it.path, it.path))} · <code>{it.composition_food_id or '—'}</code>"
                    f"</span></td><td>{html.escape(it.method_key or '—')}</td><td class='num'>{masses}</td>"
                    f"<td>{html.escape(yf)}</td>"
                    + "".join(_cell(it.nutrient_totals.get(k), it.category(k)) for k in keys) + "</tr>")
    tot = "".join(_cell(pr.per_portion.get(k), pr.total_category.get(k, "unknown")) for k in keys)
    body.append(f"<tr class='tot'><td>Por porção (÷ {fmt_num(pr.portions, 0)})</td><td></td>"
                f"<td class='num'>{_v(pr.served_mass_g / pr.portions if pr.served_mass_g else None, 0)}</td><td></td>"
                f"{tot}</tr>")
    partial = "".join(f"<li>{html.escape(ndb.label(k))}: desconhecido em {html.escape(', '.join(v))} "
                      "(total parcial)</li>" for k, v in pr.partial.items() if k in keys)
    warn = "".join(f"<li>{html.escape(w)}</li>" for w in pr.warnings)
    return (f"<h3>Nutrição após preparo</h3>"
            "<p class='muted'><sup>M</sup> medido (registro do alimento no estado servido × massa) · "
            "<sup>D</sup> derivado (fatores USDA de rendimento/retenção) · <sup>E</sup> estimado (aproximação "
            "declarada) · ? desconhecido. Massas: crua / pronta / servida (g).</p>"
            f"<div class='scroll'><table class='tbl'><thead><tr><th>ingrediente</th><th>método</th>"
            f"<th class='num'>massas</th><th>rendimento</th>{head}</tr></thead><tbody>{''.join(body)}</tbody>"
            f"</table></div>"
            + (f"<ul class='muted'>{partial}</ul>" if partial else "")
            + (f"<div class='warn'><ul>{warn}</ul></div>" if warn else ""))


def nutrition_section(nr: NutritionResult, ndb: NutritionDB) -> str:
    if not nr.lines:
        return "<h2>Nutrição</h2><p class='muted'>Nenhum ingrediente com quantidade para calcular.</p>"
    pp = nr.per_portion
    tiles = "".join(
        f"<div class='tile'><div class='v'>{_v(pp.get(k), 0 if k in ('energia_kcal', 'sodio_mg') else 1)}"
        f"</div><div class='l'>{html.escape(ndb.label(k))}</div></div>" for k in TILES)

    # tabela por ingrediente
    head = "".join(f"<th class='num'>{html.escape(ndb.label(k))}</th>" for k in MAIN)
    body = []
    for line in nr.lines:
        row = nr.table.loc[line.nome]
        alimento = ndb.foods.at[line.food.food_id, "nome"] if line.food.food_id in ndb.foods.index else "—"
        qty = f"{fmt_num(line.quantidade, 2).rstrip('0').rstrip(',')} {line.unidade}" \
            if not np.isnan(line.quantidade) else "—"
        body.append(
            f"<tr><td><b>{html.escape(line.nome)}</b><br><span class='muted'>{html.escape(str(alimento))}"
            f" · <code>{line.food.food_id}</code></span></td><td>{html.escape(qty)}</td>"
            f"<td class='num'>{_v(line.gramas)}</td><td class='muted'>{html.escape(line.metodo)}</td>"
            + "".join(f"<td class='num'>{_v(row.get(k))}</td>" for k in MAIN) + "</tr>")
    grams = sum(line.gramas for line in nr.lines)
    for label, s in (("Total", nr.total), (f"Por porção (÷ {fmt_num(nr.portions, 0)})", nr.per_portion)):
        g = grams if label == "Total" else grams / nr.portions
        body.append(f"<tr class='tot'><td>{label}</td><td></td><td class='num'>{_v(g)}</td><td></td>"
                    + "".join(f"<td class='num'>{_v(s.get(k))}</td>" for k in MAIN) + "</tr>")
    table = (f"<div class='scroll'><table class='tbl'><thead><tr><th>ingrediente</th><th>quantidade</th>"
             f"<th class='num'>gramas</th><th>conversão</th>{head}</tr></thead><tbody>{''.join(body)}"
             f"</tbody></table></div>")

    vd_rows = "".join(
        f"<tr><td>{html.escape(ndb.label(k))}</td><td class='num'>{_v(pp.get(k))}</td>"
        f"<td class='num'>{fmt_num(ref, 0)}</td><td class='num'>{_v(nr.vd.get(k), 0)}%</td>"
        f"<td><span class='vdbar'><i style='width:{min(float(np.nan_to_num(nr.vd.get(k))), 100):.0f}%'></i>"
        f"</span></td></tr>" for k, ref in VDR.items())
    vd = (f"<table class='tbl'><thead><tr><th>nutriente</th><th class='num'>por porção</th>"
          f"<th class='num'>referência</th><th class='num'>%VD</th><th></th></tr></thead><tbody>{vd_rows}</tbody></table>"
          "<p class='muted'>%VD: valores diários de referência para adultos, dieta de 2.000 kcal "
          "(ANVISA, IN nº 75/2020). Açúcares totais não têm %VD (a referência é para açúcares adicionados).</p>")

    notes = []
    for nome, keys in nr.complemented.items():
        main = [k for k in keys if any(ndb.label(m).startswith(k) for m in MAIN)]
        if main:
            notes.append(f"<b>{html.escape(nome)}</b>: {html.escape(', '.join(main))} vieram do complemento USDA")
    notes_html = ("<p class='muted'>Lacunas preenchidas: " + "; ".join(notes) + ".</p>") if notes else ""
    warn = ("<div class='warn'>" + "<br>".join(html.escape(w) for w in nr.warnings) + "</div>") if nr.warnings else ""

    figs = [f.to_html(full_html=False, include_plotlyjs=False, config={"displaylogo": False, "responsive": True})
            for f in (_fig_energy_by_ingredient(nr), _fig_energy_origin(nr))]
    return (f"<style>{CSS}</style><h2>Nutrição</h2>"
            f"<p class='muted'>Valores por porção ({fmt_num(nr.portions, 0)} porção(ões)), unidades métricas. "
            f"Composição: TACO 4ª ed. (NEPA/UNICAMP) e USDA FoodData Central.</p>"
            f"{warn}<div class='tiles'>{tiles}</div>{table}"
            f"<div class='grid2'>{figs[0]}{figs[1]}</div><h3>% do valor diário (por porção)</h3>{vd}{notes_html}"
            + (prepared_section(nr.prepared, ndb) if getattr(nr, "prepared", None) is not None else ""))
