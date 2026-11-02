"""Relatório HTML interativo do embasamento científico de uma receita.

- Grafo: vis-network (nós arrastáveis, clique destaca vizinhos, busca, filtro por nota)
- Gráficos: plotly (mapas de calor e perfil sensorial, com hover e zoom)
- Tabelas: ordenáveis com clique no cabeçalho
"""

from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs_version

from .analysis import RecipeAnalysis, npmi_label

# Paleta categórica validada (ordem fixa) + rampas sequenciais de uma cor.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
BLUE_SEQ = [[0, "#f3f7fd"], [0.5, "#6da7ec"], [1, "#104281"]]
ORANGE_SEQ = [[0, "#fdf4ef"], [0.5, "#f19a6f"], [1, "#9a3a12"]]
SURFACE, TEXT, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
PLOTLY_CDN = f"https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js"  # mesma versão do pacote
VIS_CDN = "https://unpkg.com/vis-network@10.1.4/standalone/umd/vis-network.min.js"

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
def _fmt(v, f):
    return "—" if v is None or (isinstance(v, float) and np.isnan(v)) else format(v, f)


def network_data(a: RecipeAnalysis, n_tags: int = 16) -> dict:
    """Nós e arestas do grafo (formato vis-network) + notas de sabor para filtro."""
    nodes, edges = [], []
    names = [r.name for r in a.items]
    for k, r in enumerate(a.items):
        ang = 2 * np.pi * k / max(len(names), 1) - np.pi / 2
        n_mol = a.n_molecules[r.ingredient_id]
        nodes.append({
            "id": f"i:{r.name}", "label": r.name.replace("_", " "), "kind": "ingredient",
            "x": float(380 * np.cos(ang)), "y": float(300 * np.sin(ang)),
            "shape": "dot", "size": 26,
            "color": {"background": SERIES[0], "border": SURFACE,
                      "highlight": {"background": SERIES[0], "border": TEXT}},
            "font": {"size": 17, "color": TEXT, "face": "system-ui", "strokeWidth": 4, "strokeColor": SURFACE},
            "title": f"{r.name} ({r.ingredient_id})\n{n_mol} moléculas" + (f"\n{r.note}" if r.note else ""),
            "info": (f"<h4>{html.escape(r.name)}</h4><p>Ingrediente da receita · <code>{r.ingredient_id}</code></p>"
                     f"<p><b>{n_mol}</b> moléculas de sabor no banco</p>"
                     + (f"<p class='muted'>{html.escape(r.note)}</p>" if r.note else "")),
            "desc": [],
        })
    for b in a.bridges.itertuples():
        desc = list(b.descriptors)
        nodes.append({
            "id": f"m:{b.pubchem_id}", "label": str(b.name)[:24], "kind": "molecule",
            "shape": "dot", "size": 6 + 2.5 * b.n_ingredients,
            "color": {"background": SERIES[1], "border": SURFACE,
                      "highlight": {"background": SERIES[1], "border": TEXT}},
            "font": {"size": 11, "color": MUTED, "face": "system-ui"},
            "title": f"{b.name}\naroma/sabor: {_wrap(desc, 6) or '—'}\npresente em: {_wrap(b.ingredients, 6)}",
            "info": (f"<h4>{html.escape(str(b.name))}</h4>"
                     f"<p>Molécula · <a href='https://pubchem.ncbi.nlm.nih.gov/compound/{b.pubchem_id}' "
                     f"target='_blank' rel='noopener'>PubChem {b.pubchem_id}</a></p>"
                     f"<p><b>Aroma/sabor:</b> {html.escape(', '.join(desc)) or '—'}</p>"
                     f"<p><b>Presente em:</b> {html.escape(', '.join(b.ingredients))}</p>"
                     f"<p><b>Peso molecular:</b> {_fmt(b.molecular_weight, '.1f')} · "
                     f"<b>xlogP:</b> {_fmt(b.xlogp, '.2f')}</p>"
                     f"<p class='muted'>xlogP &gt; 3 → solúvel em gordura (libera aroma no óleo/manteiga); "
                     f"peso &lt; 150 → volátil (some com cozimento longo).</p>"
                     f"<p class='muted'>Aparece em {b.db_frequency} ingredientes do banco "
                     f"(quanto menor, mais característica).</p>"),
            "desc": desc,
        })
        for owner in b.ingredients:
            edges.append({"from": f"i:{owner}", "to": f"m:{b.pubchem_id}", "kind": "chem",
                          "color": {"color": "#c9c8c3", "highlight": MUTED}, "width": 1})
    for p in a.pairs.itertuples():
        if pd.notna(p.npmi) and p.npmi > 0:
            edges.append({"from": f"i:{p.a}", "to": f"i:{p.b}", "kind": "recipe",
                          "color": {"color": SERIES[2], "highlight": "#0e7a52", "opacity": 0.8},
                          "width": 2 + 16 * float(p.npmi),
                          "title": f"{p.a} + {p.b}\nNPMI {p.npmi:.2f} — {npmi_label(p.npmi)}"})
    tags = Counter(d for b in a.bridges.itertuples() for d in b.descriptors).most_common(n_tags) \
        if len(a.bridges) else []
    return {"nodes": nodes, "edges": edges, "tags": [t for t, _ in tags]}


NETWORK_HTML = """
<div class="net-tools">
  <input id="net-search" list="net-labels" placeholder="buscar ingrediente ou molécula…">
  <datalist id="net-labels"></datalist>
  <button id="net-reset" type="button">limpar destaque</button>
  <button id="net-physics" type="button">reorganizar</button>
</div>
<div class="net-tags"><span class="muted">notas de sabor:</span> <span id="net-tags"></span></div>
<div class="net-legend">
  <span><i class="dot" style="background:%(ing)s"></i>ingrediente da receita</span>
  <span><i class="dot" style="background:%(mol)s"></i>molécula compartilhada (tamanho = nº de ingredientes)</span>
  <span><i class="bar" style="background:#c9c8c3"></i>contém a molécula</span>
  <span><i class="bar thick" style="background:%(rec)s"></i>associados em receitas (espessura = força)</span>
</div>
<div class="net-wrap"><div id="net"></div>
  <aside id="net-info"><p class="muted">Clique num nó para ver os detalhes e destacar as conexões.
  Arraste para reorganizar; role para dar zoom.</p></aside></div>
<script type="application/json" id="net-data">%(data)s</script>
"""

NETWORK_JS = r"""
(function () {
  const D = JSON.parse(document.getElementById('net-data').textContent);
  if (!window.vis) { document.getElementById('net').innerHTML =
      '<p class="muted">Não foi possível carregar o vis-network (sem internet?).</p>'; return; }
  const FADE = {background: '#ecebe7', border: '#ecebe7'};
  const nodes = new vis.DataSet(D.nodes.map(n => Object.assign({}, n, {orig: n.color, origFont: n.font})));
  const edges = new vis.DataSet(D.edges.map((e, i) => Object.assign({id: i}, e, {orig: e.color})));
  const net = new vis.Network(document.getElementById('net'), {nodes, edges}, {
    physics: {solver: 'forceAtlas2Based', stabilization: {iterations: 300},
              forceAtlas2Based: {gravitationalConstant: -60, springLength: 110, springConstant: 0.05}},
    interaction: {hover: true, tooltipDelay: 120, keyboard: true},
    edges: {smooth: false}, nodes: {borderWidth: 2}
  });
  net.once('stabilizationIterationsDone', () => net.setOptions({physics: false}));
  const info = document.getElementById('net-info'), initialInfo = info.innerHTML;

  function highlight(ids) {
    const keep = new Set(ids);
    nodes.update(nodes.get().map(n => keep.has(n.id)
      ? {id: n.id, color: n.orig, font: n.origFont}
      : {id: n.id, color: FADE, font: Object.assign({}, n.origFont, {color: '#c9c8c3'})}));
    edges.update(edges.get().map(e => (keep.has(e.from) && keep.has(e.to))
      ? {id: e.id, color: e.orig} : {id: e.id, color: {color: '#f1f0ec', opacity: 0.4}}));
  }
  function reset() {
    nodes.update(nodes.get().map(n => ({id: n.id, color: n.orig, font: n.origFont})));
    edges.update(edges.get().map(e => ({id: e.id, color: e.orig})));
    info.innerHTML = initialInfo; net.unselectAll();
    document.querySelectorAll('#net-tags button').forEach(b => b.classList.remove('on'));
  }
  function focusNode(id) {
    const n = nodes.get(id); if (!n) return;
    highlight([id].concat(net.getConnectedNodes(id)));
    info.innerHTML = n.info;
    net.selectNodes([id]);
  }
  net.on('click', p => p.nodes.length ? focusNode(p.nodes[0]) : reset());

  const dl = document.getElementById('net-labels');
  D.nodes.forEach(n => { const o = document.createElement('option'); o.value = n.label; dl.appendChild(o); });
  document.getElementById('net-search').addEventListener('change', ev => {
    const q = ev.target.value.trim().toLowerCase();
    const n = D.nodes.find(n => n.label.toLowerCase() === q) ||
              D.nodes.find(n => n.label.toLowerCase().includes(q));
    if (n) { focusNode(n.id); net.focus(n.id, {scale: 1.2, animation: true}); }
  });
  document.getElementById('net-reset').addEventListener('click', reset);
  document.getElementById('net-physics').addEventListener('click', () => {
    net.setOptions({physics: true}); net.stabilize(200);
    net.once('stabilizationIterationsDone', () => net.setOptions({physics: false}));
  });

  const tagBox = document.getElementById('net-tags');
  D.tags.forEach(t => {
    const b = document.createElement('button'); b.type = 'button'; b.textContent = t;
    b.addEventListener('click', () => {
      const on = !b.classList.contains('on');
      reset(); if (!on) return; b.classList.add('on');
      const mols = D.nodes.filter(n => n.desc.includes(t)).map(n => n.id);
      const ids = new Set(mols); mols.forEach(m => net.getConnectedNodes(m).forEach(x => ids.add(x)));
      highlight([...ids]);
      info.innerHTML = '<h4>nota: ' + t + '</h4><p>' + mols.length +
        ' molécula(s) compartilhada(s) com essa nota, e os ingredientes que as trazem.</p>';
    });
    tagBox.appendChild(b);
  });
})();
"""

SORT_JS = r"""
document.querySelectorAll('table.tbl').forEach(t => {
  t.querySelectorAll('th').forEach((th, i) => {
    th.title = 'clique para ordenar';
    th.addEventListener('click', () => {
      const tb = t.tBodies[0], rows = [...tb.rows], asc = th.dataset.asc !== '1';
      t.querySelectorAll('th').forEach(h => { h.dataset.asc = ''; h.classList.remove('asc', 'desc'); });
      th.dataset.asc = asc ? '1' : '0'; th.classList.add(asc ? 'asc' : 'desc');
      rows.sort((a, b) => {
        const x = a.cells[i].innerText.trim(), y = b.cells[i].innerText.trim();
        const nx = parseFloat(x), ny = parseFloat(y);
        const r = (!isNaN(nx) && !isNaN(ny)) ? nx - ny : x.localeCompare(y, 'pt');
        return asc ? r : -r;
      });
      rows.forEach(r => tb.appendChild(r));
    });
  });
});
"""


def network_html(a: RecipeAnalysis) -> str:
    data = json.dumps(network_data(a), ensure_ascii=False).replace("</", "<\\/")
    return NETWORK_HTML % {"ing": SERIES[0], "mol": SERIES[1], "rec": SERIES[2], "data": data}


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
.tbl th{{cursor:pointer;user-select:none}} .tbl th.asc::after{{content:" ▲"}} .tbl th.desc::after{{content:" ▼"}}
.net-tools{{display:flex;gap:.5rem;flex-wrap:wrap;margin:.5rem 0}}
.net-tools input{{flex:1;min-width:220px;padding:.45rem .6rem;border:1px solid {GRID};border-radius:6px;font:inherit}}
button{{font:inherit;padding:.35rem .7rem;border:1px solid {GRID};border-radius:6px;background:#fff;cursor:pointer}}
button:hover{{border-color:{MUTED}}} #net-tags button{{margin:.15rem;padding:.15rem .55rem;border-radius:999px;font-size:.88em}}
#net-tags button.on{{background:{TEXT};color:#fff;border-color:{TEXT}}}
.net-legend{{display:flex;gap:1.2rem;flex-wrap:wrap;font-size:.88em;color:{MUTED};margin:.5rem 0}}
.net-legend .dot{{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:.35rem;vertical-align:-1px}}
.net-legend .bar{{display:inline-block;width:22px;height:2px;margin-right:.35rem;vertical-align:3px}}
.net-legend .bar.thick{{height:6px;vertical-align:1px}}
.net-wrap{{display:grid;grid-template-columns:1fr 280px;gap:1rem}} @media(max-width:800px){{.net-wrap{{grid-template-columns:1fr}}}}
#net{{height:620px;background:#fff;border:1px solid {GRID};border-radius:8px}}
#net-info{{background:#fff;border:1px solid {GRID};border-radius:8px;padding:.8rem 1rem;font-size:.92em;overflow:auto;max-height:620px}}
#net-info h4{{margin:.2rem 0 .4rem}} #net-info p{{margin:.35rem 0}}
div.vis-tooltip{{white-space:pre-line;font-family:system-ui,sans-serif;font-size:13px;padding:6px 8px;
background:#fff;border:1px solid {GRID};border-radius:6px;box-shadow:0 2px 8px rgba(0,0,0,.08)}}
"""


def render_html(a: RecipeAnalysis, meta: dict | None = None, out: Path | None = None) -> str:
    meta = meta or {}
    figs = [heatmap(a, "jaccard", "Química: similaridade molecular (Jaccard)", BLUE_SEQ, ".2f"),
            heatmap(a, "npmi", "Prática: co-ocorrência em receitas (NPMI)", ORANGE_SEQ, ".2f"),
            profile_figure(a)]
    fh = [f.to_html(full_html=False, include_plotlyjs=False,
                    config={"displaylogo": False, "responsive": True}) for f in figs]

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
<title>{html.escape(a.name)} — embasamento científico</title><style>{CSS}</style>
<script src="{PLOTLY_CDN}"></script><script src="{VIS_CDN}"></script></head><body>
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
{network_html(a)}
<h2>Química × prática</h2>
<div class="grid2">{fh[0]}{fh[1]}</div>
<h2>Perfil sensorial</h2>{fh[2]}
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
<script>{NETWORK_JS}</script><script>{SORT_JS}</script>
</body></html>"""
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(doc, encoding="utf-8")
    return doc
