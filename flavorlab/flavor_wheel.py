"""Roda de aromas: gráfico radial de um ingrediente em destaque (Plotly).

Leitura do gráfico:

* **centro** — ingrediente em destaque;
* **anel interno** — descritores sensoriais das moléculas que a fonte registra
  para o ingrediente (FlavorDB). A largura de cada setor é o número de moléculas
  com o descritor. É dado da molécula isolada, **não** percepção no prato;
* **barras externas** — ingredientes que compartilham moléculas com o destaque.
  Comprimento = Jaccard (moléculas compartilhadas / união). Cada barra fica no
  setor do descritor que mais concentra as moléculas compartilhadas;
* **cor** — NPMI (co-ocorrência em receitas, FlavorGraph). Cinza = sem dado.

Nenhuma das métricas mede gosto, qualidade da combinação ou preferência (mesmo
princípio de ``flavorlab.sensory.pair_metrics``). Os dados vêm de
``flavorlab.db.FlavorDB``; a figura é separada dos dados para ser testável.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import plotly.graph_objects as go

DESCRIPTOR_PT = {
    "sweet": "doce", "bitter": "amargo", "floral": "floral", "woody": "amadeirado", "spicy": "especiado",
    "green": "verde", "herbal": "herbáceo", "balsamic": "balsâmico", "fruity": "frutado", "fresh": "fresco",
    "citrus": "cítrico", "minty": "mentolado", "oily": "oleoso", "honey": "mel", "waxy": "ceroso",
    "fatty": "gorduroso", "nutty": "amendoado", "roasted": "tostado", "earthy": "terroso", "smoky": "defumado",
    "sulfurous": "sulfurado", "caramel": "caramelo", "vanilla": "baunilha", "creamy": "cremoso",
    "pungent": "pungente", "sour": "ácido", "meaty": "cárneo", "cheesy": "queijo", "buttery": "amanteigado",
    "fishy": "peixe", "rose": "rosa", "camphoreous": "canforado", "musty": "mofado", "phenolic": "fenólico",
    "medicinal": "medicinal", "ethereal": "etéreo", "winey": "vínico", "cinnamon": "canela", "almond": "amêndoa",
    "coconut": "coco", "apple": "maçã", "pineapple": "abacaxi", "banana": "banana", "tropical": "tropical",
    "anise": "anis", "clove": "cravo", "mushroom": "cogumelo", "potato": "batata", "onion": "cebola",
    "garlic": "alho", "cocoa": "cacau", "coffee": "café", "bready": "pão", "popcorn": "pipoca", "tea": "chá",
    "vegetable": "vegetal", "lemon": "limão", "orange": "laranja", "berry": "frutas vermelhas", "grape": "uva",
    "peach": "pêssego", "cucumber": "pepino", "tomato": "tomate", "pepper": "pimenta", "leafy": "folhoso",
    "grassy": "relva", "hay": "feno", "tobacco": "tabaco", "leather": "couro", "animal": "animal",
    "burnt": "queimado", "caramellic": "caramelo", "brown": "tostado", "malty": "malte", "toasted": "tostado",
}
OTHER = "outros"
NOTE_HTML = ("Comprimento: moléculas do descritor compartilhadas com o destaque (Jaccard no setor, escala relativa)."
             "<br>Cor: NPMI, co-ocorrência em receitas (FlavorGraph); claro = sem dado. Anel: descritores das moléculas"
             " (FlavorDB),<br>não percepção no prato. Nenhuma métrica mede gosto ou preferência.")
NOTE = ("Comprimento = moléculas do descritor compartilhadas (Jaccard no setor; FlavorDB/FlavorGraph). "
        "Cor = NPMI (co-ocorrência em receitas). Anel = descritores das moléculas da fonte, não percepção no prato. "
        "Nenhuma métrica mede gosto ou preferência.")


def pt(descriptor: str) -> str:
    return DESCRIPTOR_PT.get(descriptor, descriptor)


@dataclass
class Sector:
    descriptor: str
    n_molecules: int
    start_deg: float
    width_deg: float

    @property
    def center_deg(self) -> float:
        return self.start_deg + self.width_deg / 2


@dataclass
class Partner:
    ingredient_id: str
    name: str
    jaccard: float
    shared: int
    npmi: float | None
    descriptor: str
    theta_deg: float = 0.0
    overall_jaccard: float | None = None


@dataclass
class WheelData:
    ingredient_id: str
    name: str
    n_molecules: int
    sectors: list[Sector]
    partners: list[Partner]
    notes: list[str] = field(default_factory=lambda: [NOTE])


def _key(name: str) -> str:
    """Chave de deduplicação: minúsculas, sem '_' e no singular ('Green Beans' == 'green_bean')."""
    from .catalog_mapping import tokens
    return " ".join(tokens(name))


def _label(db, pid: str, catalog=None) -> str:
    """Nome em português pelo catálogo (só mapeamento aceito); senão o nome da fonte."""
    if catalog is not None:
        src = "flavordb" if pid.startswith("fdb:") else "flavorgraph"
        res = catalog.resolve_source(src, pid)
        if res.is_mapped and res.status != "mapped_low_confidence":
            return catalog.name(catalog.concept_of(res.entity_id) if res.entity_id.startswith("sl:form:")
                                else res.entity_id, "pt")
    return db.display_name(pid).replace("_", " ")


def _descriptor_counts(db, molecules) -> dict[str, int]:
    counts: dict[str, int] = {}
    for cid in molecules:
        for d in set(db.descriptors_by_molecule.get(cid, [])):
            counts[d] = counts.get(d, 0) + 1
    return counts


def wheel_data(db, ingredient: str, *, n_descriptors: int = 8, n_partners: int = 48,
               min_molecules: int = 10, catalog=None) -> WheelData:
    """Dados da roda. ``ingredient`` é nome (português ou inglês) ou ID ``fdb:``/``fg:``.

    Setores = os ``n_descriptors`` descritores mais frequentes nas moléculas do destaque
    (largura proporcional ao número de moléculas com o descritor). Em cada setor entram
    os ingredientes que mais compartilham **as moléculas daquele descritor**
    (Jaccard restrito ao descritor); cada ingrediente aparece em um único setor
    (atribuição gulosa determinística pelo maior Jaccard do descritor).
    """
    if ingredient.startswith(("fdb:", "fg:")):
        iid, name, source = ingredient, db.display_name(ingredient), ingredient
    else:
        try:
            res = db.resolve(ingredient)
        except KeyError as exc:
            raise ValueError(str(exc)) from None
        if res.ingredient_id is None:
            raise ValueError(f"ingrediente não encontrado no banco de sabores: {ingredient!r}")
        iid, name, source = res.ingredient_id, ingredient, res.molecules_from
    mols = set(db.molecules_of(source))
    if not mols:
        raise ValueError(f"{ingredient!r} não tem moléculas registradas")

    desc = db.descriptors_by_molecule
    counts = _descriptor_counts(db, mols)
    top = [d for d, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n_descriptors]]
    total = sum(counts[d] for d in top) or 1
    sectors, start = [], 0.0
    for d in top:
        width = 360.0 * counts[d] / total
        sectors.append(Sector(d, counts[d], start, width))
        start += width
    by_desc = {d: {c for c in mols if d in desc.get(c, [])} for d in top}

    # candidatos: ingredientes com moléculas próprias, sem variantes do próprio destaque e sem
    # duplicatas FlavorDB/FlavorGraph do mesmo ingrediente (prefere fg:, que tem NPMI)
    fdb2fg = dict(zip(db.crosswalk["fdb_id"], db.crosswalk["fg_id"])) if hasattr(db, "crosswalk") else {}
    base = _key(db.name(source))
    cands: dict[str, str] = {}
    for pid in sorted(db.profiles, key=lambda x: (not x.startswith("fg:"), x)):
        if pid in (source, iid) or len(db.profiles[pid]) < min_molecules:
            continue
        fg = fdb2fg.get(pid)
        key = _key(db.name(fg)) if fg else _key(db.name(pid))
        if base and (base in key or key in base) or key in cands:
            continue
        cands[key] = pid

    scored = []   # (jaccard_do_descritor, descritor, pid)
    for pid in cands.values():
        pm = db.profiles[pid]
        for d in top:
            pd_ = {c for c in pm if d in desc.get(c, [])}
            inter = by_desc[d] & pd_
            if inter:
                scored.append((len(inter) / len(by_desc[d] | pd_), d, pid))
    per_sector = max(1, n_partners // max(1, len(top)))
    filled = {d: 0 for d in top}
    used: set[str] = set()
    partners: list[Partner] = []
    for jd, d, pid in sorted(scored, key=lambda t: (-t[0], top.index(t[1]), t[2])):
        if pid in used or filled[d] >= per_sector:
            continue
        pm = db.profiles[pid]
        npmi = db.npmi(iid, pid)
        npmi = None if npmi is None or (isinstance(npmi, float) and math.isnan(npmi)) or npmi <= 0 else float(npmi)
        p = Partner(pid, _label(db, pid, catalog), jd, len(by_desc[d] & pm), npmi, d)
        p.overall_jaccard = len(mols & pm) / len(mols | pm)
        partners.append(p)
        used.add(pid)
        filled[d] += 1

    for s in sectors:
        group = sorted((p for p in partners if p.descriptor == s.descriptor), key=lambda p: (-p.jaccard, p.ingredient_id))
        for i, p in enumerate(group):
            p.theta_deg = s.start_deg + s.width_deg * (i + 0.5) / len(group)
    partners.sort(key=lambda p: (p.theta_deg, p.ingredient_id))
    return WheelData(iid, name, len(mols), sectors, partners)


# --------------------------------------------------------------------------- figura
RING_INNER, RING_OUTER, BAR_SPAN = 0.35, 0.6, 1.0
GREYS = ["#d9d9d9", "#c8c8c8", "#b8b8b8", "#a8a8a8"]


def wheel_figure(data: WheelData, *, title: str | None = None) -> go.Figure:
    fig = go.Figure()
    # anel interno: descritores
    fig.add_trace(go.Barpolar(
        r=[RING_OUTER - RING_INNER] * len(data.sectors), base=[RING_INNER] * len(data.sectors),
        theta=[s.center_deg for s in data.sectors], width=[s.width_deg for s in data.sectors],
        marker=dict(color=[GREYS[i % len(GREYS)] for i in range(len(data.sectors))], line=dict(color="white", width=2)),
        text=[pt(s.descriptor) for s in data.sectors],
        customdata=[[s.descriptor, s.n_molecules] for s in data.sectors],
        hovertemplate="<b>%{text}</b> (%{customdata[0]})<br>%{customdata[1]} moléculas com o descritor"
                      "<br><i>descritor da molécula, não percepção</i><extra></extra>",
        name="descritores", showlegend=False))
    # barras externas: parceiros
    js = [p.jaccard for p in data.partners] or [1.0]
    lo, hi = min(js), max(js)

    def length(j: float) -> float:
        """Escala linear relativa aos ingredientes mostrados: [mín, máx] -> [25%, 100%] do raio."""
        return BAR_SPAN * (0.25 + 0.75 * ((j - lo) / (hi - lo) if hi > lo else 1.0))
    npmis = [p.npmi for p in data.partners if p.npmi is not None]
    cmax = max(npmis) if npmis else 1.0
    colors = [p.npmi if p.npmi is not None else np.nan for p in data.partners]
    widths = []
    for p in data.partners:
        sec = next((s for s in data.sectors if s.descriptor == p.descriptor), None)
        n = sum(1 for q in data.partners if q.descriptor == p.descriptor)
        widths.append(0.8 * (sec.width_deg / n if sec and n else 4.0))
    fig.add_trace(go.Barpolar(
        r=[length(p.jaccard) for p in data.partners], base=[RING_OUTER + 0.03] * len(data.partners),
        theta=[p.theta_deg for p in data.partners], width=widths,
        marker=dict(color=[c if not np.isnan(c) else 0 for c in colors], colorscale=[[0, "#efe3e6"], [1, "#6d0f2c"]],
                    cmin=0, cmax=cmax, line=dict(width=0),
                    colorbar=dict(title="NPMI<br>(receitas)", thickness=12, len=0.45, x=1.0, xanchor="left")),
        text=[p.name for p in data.partners],
        customdata=[[p.jaccard, p.shared, ("sem dado" if p.npmi is None else f"{p.npmi:.2f}"), pt(p.descriptor),
                     p.overall_jaccard if p.overall_jaccard is not None else float("nan")] for p in data.partners],
        hovertemplate="<b>%{text}</b><br>setor %{customdata[3]}: Jaccard %{customdata[0]:.3f} "
                      "(%{customdata[1]} moléculas do descritor em comum)<br>Jaccard total %{customdata[4]:.3f}"
                      " · NPMI %{customdata[2]}<extra></extra>",
        name="ingredientes", showlegend=False))
    # rótulo do mais forte de cada setor
    top = []
    for s in data.sectors:
        group = sorted((p for p in data.partners if p.descriptor == s.descriptor), key=lambda p: (-p.jaccard, p.ingredient_id))
        top += group[:1]
    fig.add_trace(go.Scatterpolar(
        r=[RING_OUTER + 0.03 + length(p.jaccard) + 0.1 for p in top], theta=[p.theta_deg for p in top],
        mode="text", text=[p.name.split(" (")[0] for p in top], textfont=dict(size=11, color="#6d0f2c"),
        hoverinfo="skip", showlegend=False))
    # rótulos dos setores
    fig.add_trace(go.Scatterpolar(
        r=[(RING_INNER + RING_OUTER) / 2] * len(data.sectors), theta=[s.center_deg for s in data.sectors],
        mode="text", text=[pt(s.descriptor) for s in data.sectors], textfont=dict(size=10, color="#333"),
        hoverinfo="skip", showlegend=False))
    fig.update_layout(
        title=dict(text=title or f"Roda de aromas — {data.name}", x=0.5),
        polar=dict(domain=dict(x=[0.02, 0.86]), radialaxis=dict(visible=False, range=[0, RING_OUTER + BAR_SPAN + 0.35]),
                   angularaxis=dict(visible=False, direction="clockwise", rotation=90), bgcolor="white"),
        annotations=[dict(text=f"<b>{data.name}</b><br><span style='font-size:11px'>{data.n_molecules} moléculas</span>",
                          x=0.44, y=0.5, xref="paper", yref="paper", showarrow=False, font=dict(size=16)),
                     dict(text=NOTE_HTML, x=0.44, y=-0.1, xref="paper", yref="paper", showarrow=False,
                          align="center", font=dict(size=10, color="#555"))],
        height=820, width=860, margin=dict(t=70, b=120, l=60, r=130), paper_bgcolor="white")
    return fig


def flavor_wheel(db, ingredient: str, **kwargs) -> go.Figure:
    data_kwargs = {k: kwargs.pop(k) for k in ("n_descriptors", "n_partners", "min_molecules", "catalog") if k in kwargs}
    return wheel_figure(wheel_data(db, ingredient, **data_kwargs), **kwargs)
