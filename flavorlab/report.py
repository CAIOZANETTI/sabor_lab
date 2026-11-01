"""Relatório HTML interativo (plotly) do embasamento científico de uma receita."""

from __future__ import annotations

import html
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .analysis import RecipeAnalysis, npmi_label

# Paleta categórica validada (ordem fixa) + rampas sequenciais de uma cor.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
BLUE_SEQ = [[0, "#f3f7fd"], [0.5, "#6da7ec"], [1, "#104281"]]
ORANGE_SEQ = [[0, "#fdf4ef"], [0.5, "#f19a6f"], [1, "#9a3a12"]]
SURFACE, TEXT, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"

LAYOUT = dict(
    paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
    font=dict(family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif", color=TEXT, size=13),
    margin=dict(l=10, r=10, t=50, b=10),
    hoverlabel=dict(bgcolor="white", font_color=TEXT, bordercolor=GRID),
)


def _wrap(items, n=4) -> str:
    items = list(items)
    return ", ".join(items[:n]) + (f" +{len(items) - n}" if len(items) > n else "")


# ------------------------------------------------------------------- grafo
def network_figure(a: RecipeAnalysis) -> go.Figure:
    """Ingredientes (grandes) ligados pelas moléculas que compartilham."""
    G = nx.Graph()
    names = [r.name for r in a.items]
    for n in names:
        G.add_node(("i", n))
    for b in a.bridges.itertuples():
        G.add_node(("m", b.pubchem_id))
        for owner in b.ingredients:
            G.add_edge(("i", owner), ("m", b.pubchem_id), kind="chem")
    for p in a.pairs.itertuples():
        if p.npmi and p.npmi > 0:
            G.add_edge(("i", p.a), ("i", p.b), kind="recipe", w=p.npmi)
    # ingredientes fixos num círculo; cada molécula fica no centro de gravidade
    # dos ingredientes que a contêm (ponte entre 2 = no meio do caminho entre eles)
    pos = {("i", n): np.array([np.cos(2 * np.pi * k / len(names) + np.pi / 2),
                               np.sin(2 * np.pi * k / len(names) + np.pi / 2)])
           for k, n in enumerate(names)}
    groups: dict[tuple, list[int]] = {}
    for b in a.bridges.itertuples():
        groups.setdefault(tuple(sorted(b.ingredients)), []).append(b.pubchem_id)
    for owners, cids in groups.items():
        center = np.mean([pos[("i", o)] for o in owners], axis=0) * 0.8
        for j, cid in enumerate(cids):  # espalha moléculas do mesmo grupo numa espiral
            ang, rad = 2.4 * j, 0.07 * np.sqrt(j)
            pos[("m", cid)] = center + rad * np.array([np.cos(ang), np.sin(ang)])

    fig = go.Figure()
    # arestas química (finas, recessivas)
    xs, ys = [], []
    for u, v, d in G.edges(data=True):
        if d["kind"] == "chem":
            xs += [pos[u][0], pos[v][0], None]
            ys += [pos[u][1], pos[v][1], None]
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color="#c9c8c3", width=1),
                             hoverinfo="skip", name="contém a molécula"))
    # arestas receita (espessura = NPMI)
    first = True
    for u, v, d in G.edges(data=True):
        if d["kind"] == "recipe":
            fig.add_trace(go.Scatter(
                x=[pos[u][0], pos[v][0]], y=[pos[u][1], pos[v][1]], mode="lines",
                line=dict(color=SERIES[2], width=2 + 14 * d["w"]), opacity=0.75,
                name="associados em receitas (espessura = força)", legendgroup="recipe",
                showlegend=first, hoverinfo="text",
                text=f"{u[1]} + {v[1]}<br>NPMI {d['w']:.2f} — {npmi_label(d['w'])}"))
            first = False
    # nós molécula
    if len(a.bridges):
        b = a.bridges
        fig.add_trace(go.Scatter(
            x=[pos[("m", c)][0] for c in b.pubchem_id], y=[pos[("m", c)][1] for c in b.pubchem_id],
            mode="markers+text", name="molécula compartilhada",
            marker=dict(size=10 + 3 * b.n_ingredients, color=SERIES[1], line=dict(color=SURFACE, width=2)),
            text=[str(n)[:22] if k < 10 else "" for k, n in enumerate(b.name)],
            textposition="bottom center",
            textfont=dict(size=10, color=MUTED),
            hovertext=[
                f"<b>{html.escape(str(r.name))}</b> (PubChem {r.pubchem_id})"
                f"<br>sabor/aroma: {html.escape(_wrap(r.descriptors, 6)) or '—'}"
                f"<br>presente em: {html.escape(_wrap(r.ingredients, 6))}"
                f"<br>MW {r.molecular_weight or '—'} · xlogP {r.xlogp if r.xlogp is not None else '—'}"
                f"<br>aparece em {r.db_frequency} ingredientes do banco"
                for r in b.itertuples()],
            hoverinfo="text"))
    # nós ingrediente
    fig.add_trace(go.Scatter(
        x=[pos[("i", n)][0] for n in names], y=[pos[("i", n)][1] for n in names],
        mode="markers+text", name="ingrediente da receita",
        marker=dict(size=34, color=SERIES[0], line=dict(color=SURFACE, width=3)),
        text=[f"<b>{n.replace('_', ' ')}</b>" for n in names], textposition="top center",
        textfont=dict(size=14, color=TEXT), hoverinfo="text",
        hovertext=[f"<b>{html.escape(r.name)}</b> ({r.ingredient_id})<br>{a.n_molecules[r.ingredient_id]} moléculas"
                   + (f"<br>{html.escape(r.note)}" if r.note else "") for r in a.items]))
    fig.update_layout(**LAYOUT, height=640, title="Rede de sabor da receita",
                      legend=dict(orientation="h", y=-0.02, x=0),
                      xaxis=dict(visible=False, range=[-1.35, 1.35]),
                      yaxis=dict(visible=False, range=[-1.25, 1.3], scaleanchor="x"))
    return fig


# -------------------------------------------------------------- heatmaps
def _matrix(a: RecipeAnalysis, col: str) -> pd.DataFrame:
    names = [r.name for r in a.items]
    m = pd.DataFrame(np.nan, index=names, columns=names)
    for p in a.pairs.itertuples():
        m.loc[p.a, p.b] = m.loc[p.b, p.a] = getattr(p, col)
    return m


def heatmap(a: RecipeAnalysis, col: str, title: str, scale, fmt: str) -> go.Figure:
    m = _matrix(a, col)
    labels = [n.replace("_", " ") for n in m.index]
    text = m.map(lambda v: "" if pd.isna(v) else format(v, fmt))
    fig = go.Figure(go.Heatmap(
        z=m.values, x=labels, y=labels, colorscale=scale, zmin=0,
        text=text.values, texttemplate="%{text}", xgap=2, ygap=2,
        hovertemplate="%{y} + %{x}<br>" + title + ": %{z:" + fmt + "}<extra></extra>",
        colorbar=dict(thickness=10, outlinewidth=0)))
    fig.update_layout(**LAYOUT, height=120 + 46 * len(m), title=title,
                      yaxis=dict(autorange="reversed"))
    return fig


# --------------------------------------------------------- perfil sensorial
def profile_figure(a: RecipeAnalysis, top: int = 14) -> go.Figure:
    prof = a.profile.head(top) / max(len(a.profile.columns), 1)  # contribuição média
    cols = list(prof.columns)
    if len(cols) > len(SERIES):  # nunca gerar cor nova: agrupa o excesso em "outros"
        keep = cols[: len(SERIES) - 1]
        prof = prof[keep].assign(outros=prof[cols[len(SERIES) - 1:]].sum(axis=1))
        cols = list(prof.columns)
    prof = prof.iloc[::-1]
    fig = go.Figure()
    for k, c in enumerate(cols):
        fig.add_trace(go.Bar(
            y=prof.index, x=prof[c], name=c.replace("_", " "), orientation="h",
            marker=dict(color=SERIES[k] if c != "outros" else "#a3a29c",
                        line=dict(color=SURFACE, width=2)),
            hovertemplate=f"{c}: " + "%{x:.0%} do perfil — %{y}<extra></extra>"))
    fig.update_layout(**LAYOUT, barmode="stack", height=140 + 28 * len(prof),
                      title="Perfil sensorial: quem traz cada nota",
                      xaxis=dict(tickformat=".0%", gridcolor=GRID, title="fração média das moléculas com o descritor"),
                      legend=dict(orientation="h", y=-0.15, x=0))
    return fig


# ------------------------------------------------------------------ HTML
def _table(df: pd.DataFrame, fmt: dict | None = None) -> str:
    if df is None or not len(df):
        return "<p class='muted'>—</p>"
    df = df.copy()
    for c, f in (fmt or {}).items():
        if c in df:
            df[c] = df[c].map(lambda v: "" if pd.isna(v) else format(v, f))
    return df.to_html(index=False, escape=True, border=0, classes="tbl")


def narrative(a: RecipeAnalysis) -> str:
    parts = []
    for p in a.pairs.head(8).itertuples():
        parts.append(
            f"<li><b>{html.escape(p.a)} + {html.escape(p.b)}</b>: {p.shared_molecules} moléculas em comum "
            f"(Jaccard {p.jaccard:.2f}); {html.escape(p.recipes)}"
            f"{f' (NPMI {p.npmi:.2f})' if pd.notna(p.npmi) and p.npmi > 0 else ''}."
            f"{'<br><span class=muted>destaques: ' + html.escape(p.highlights) + '</span>' if p.highlights else ''}</li>")
    return "<ul>" + "".join(parts) + "</ul>"


CSS = f"""
body{{background:{SURFACE};color:{TEXT};font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
max-width:1100px;margin:2rem auto;padding:0 1rem;line-height:1.5}}
h1{{margin-bottom:.2rem}} h2{{margin-top:2.2rem;border-bottom:1px solid {GRID};padding-bottom:.3rem}}
.muted{{color:{MUTED};font-size:.92em}} .card{{background:#fff;border:1px solid {GRID};border-radius:8px;padding:1rem;margin:1rem 0}}
.tbl{{border-collapse:collapse;width:100%;font-size:.9em}} .tbl th{{text-align:left;color:{MUTED};border-bottom:1px solid {GRID};padding:.35rem}}
.tbl td{{border-bottom:1px solid #f0efec;padding:.35rem;vertical-align:top}}
.warn{{background:#fff7e6;border-left:3px solid #eda100;padding:.5rem 1rem}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}} @media(max-width:800px){{.grid2{{grid-template-columns:1fr}}}}
"""


def render_html(a: RecipeAnalysis, meta: dict | None = None, out: Path | None = None) -> str:
    meta = meta or {}
    figs = [network_figure(a),
            heatmap(a, "jaccard", "Química: similaridade molecular (Jaccard)", BLUE_SEQ, ".2f"),
            heatmap(a, "npmi", "Prática: co-ocorrência em receitas (NPMI)", ORANGE_SEQ, ".2f"),
            profile_figure(a)]
    fh = [f.to_html(full_html=False, include_plotlyjs=("cdn" if k == 0 else False),
                    config={"displaylogo": False, "responsive": True}) for k, f in enumerate(figs)]

    head = "".join(
        f"<p><b>{html.escape(k)}:</b> {html.escape(str(v))}</p>" for k, v in meta.items()
        if v is not None and str(v).strip() and str(v) != "nan")
    warn = ("<div class='warn'>" + "<br>".join(html.escape(w) for w in a.warnings) + "</div>"
            if a.warnings else "")
    ing = pd.DataFrame([{"ingrediente": r.query, "no banco": r.name, "id": r.ingredient_id,
                         "moléculas": a.n_molecules[r.ingredient_id], "obs.": r.note}
                        for r in a.items])
    bridges = a.bridges.assign(
        descriptors=a.bridges["descriptors"].map(lambda d: _wrap(d, 6)) if len(a.bridges) else None,
        ingredients=a.bridges["ingredients"].map(", ".join) if len(a.bridges) else None,
    )[["name", "descriptors", "ingredients", "molecular_weight", "xlogp", "db_frequency"]] \
        if len(a.bridges) else a.bridges
    bridges = bridges.rename(columns={
        "name": "molécula", "descriptors": "aroma/sabor", "ingredients": "presente em",
        "molecular_weight": "peso molecular", "xlogp": "xlogP", "db_frequency": "nº alimentos no banco"})
    sug_cols = {"name": "ingrediente", "category": "categoria", "chemistry": "química",
                "practice": "prática", "linked_in_recipes": "ligações em receitas"}
    sug = {k: v.rename(columns=sug_cols) for k, v in a.suggestions.items()}
    fmt = {"química": ".3f", "prática": ".2f"}
    pairs = a.pairs.rename(columns={
        "shared_molecules": "moléculas em comum", "highlights": "destaques", "recipes": "em receitas"})

    doc = f"""<!DOCTYPE html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(a.name)} — embasamento científico</title><style>{CSS}</style></head><body>
<h1>{html.escape(a.name)}</h1>
<p class="muted">Embasamento científico da receita · FlavorDB2 + FlavorGraph</p>
{head}{warn}
<h2>Ingredientes</h2>{_table(ing)}
<h2>Por que combina</h2>
<p class="muted"><b>Química</b> = fração de moléculas de sabor compartilhadas (Jaccard, 0–1).
<b>Prática</b> = associação do par em &gt;1 milhão de receitas (NPMI, 0–1): mede se aparecem juntos
<i>mais do que o acaso</i>. Ingredientes onipresentes (alho, cebola, sal) têm NPMI baixo mesmo aparecendo
juntos com frequência — 0 significa "sem associação especial", não "nunca juntos".</p>
<div class="card">{narrative(a)}</div>
<h2>Rede de sabor</h2>
<p class="muted">Azul: ingredientes. Laranja: moléculas presentes em 2+ ingredientes (passe o mouse
para ver aroma, peso molecular e xlogP — xlogP alto = solúvel em gordura). Verde: par associado em receitas.</p>
{fh[0]}
<div class="grid2">{fh[1]}{fh[2]}</div>
<h2>Perfil sensorial</h2>{fh[3]}
<h2>Moléculas-ponte</h2>
<p class="muted">Moléculas presentes em 2 ou mais ingredientes, priorizando as mais específicas
(raras no banco) — são elas que dão "assinatura" à combinação.</p>
{_table(bridges, {"peso molecular": ".1f", "xlogP": ".2f"})}
<h2>O que acrescentar?</h2>
<div class="grid2"><div><h3>Clássicas (prática)</h3>{_table(sug.get("classicas"), fmt)}</div>
<div><h3>Química parecida</h3>{_table(sug.get("quimicas"), fmt)}</div></div>
<h3>Ousadas — química alta, sem associação em receitas (combinações pouco exploradas)</h3>
{_table(sug.get("ousadas"), fmt)}
<h2>Tabela de pares</h2>{_table(pairs, {"jaccard": ".3f", "npmi": ".2f"})}
<p class="muted">Fontes: FlavorDB2 (CC BY-NC-SA 3.0) · FlavorGraph (Apache 2.0). Ver data/SOURCES.md.</p>
</body></html>"""
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(doc, encoding="utf-8")
    return doc
