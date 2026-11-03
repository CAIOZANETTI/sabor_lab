"""Análise sensorial qualitativa: gosto, aroma, textura, excessos e contrastes (demanda 006).

Categorias de evidência mantidas separadas (nunca fundidas numa nota):

``molecule_presence``
    molécula registrada para o ingrediente na fonte (FlavorDB/FlavorGraph).
``molecule_descriptor``
    descritor sensorial associado à molécula na fonte; não implica percepção no prato.
``inferred_property``
    propriedade esperada da preparação por regra curada (``sensory_rules.csv``).
``human_observation``
    avaliação de quem provou.
``user_preference``
    gosto pessoal; nunca vira propriedade do alimento.

Jaccard (moléculas compartilhadas) e NPMI (co-ocorrência em receitas) continuam
métricas próprias: não viram "gostoso", "equilibrado" nem incompatibilidade.
"""

from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Mapping

from .evidence import EvidenceClaim
from .texture import TextureAttribute, TEXTURE_TERMS, status_of, texture_profile

ROOT = Path(__file__).resolve().parents[1]
SENSORY_RULES_CSV = ROOT / "data" / "knowledge" / "sensory_rules.csv"

TASTE_AXES = ("doce", "salgado", "acido", "amargo", "umami", "picancia", "adstringencia", "sensacao_de_gordura")
AROMA_TERMS = ("herbaceo", "citrico", "terroso", "defumado", "sulfurado", "floral", "tostado")
EVIDENCE_CATEGORIES = ("molecule_presence", "molecule_descriptor", "inferred_property", "human_observation",
                       "user_preference")
INTENSITY = ("present", "high")


@dataclass(frozen=True)
class SensoryRule:
    rule_id: str
    subject: str            # ID do catálogo (sl:...) ou grupo (sl:group:...)
    axis: str               # eixo de gosto ou "aroma:<termo>"
    intensity: str          # present | high
    statement_pt: str
    source_id: str
    evidence_type: str
    limitations: str


def load_sensory_rules(path: Path | str = SENSORY_RULES_CSV) -> list[SensoryRule]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [SensoryRule(**{k: (v or "").strip() for k, v in r.items()}) for r in csv.DictReader(fh)]


def validate_sensory_rules(rules: list[SensoryRule], sources) -> list[str]:
    errors = []
    for r in rules:
        axis_ok = r.axis in TASTE_AXES or (r.axis.startswith("aroma:") and r.axis[6:] in AROMA_TERMS)
        if not axis_ok:
            errors.append(f"{r.rule_id}: eixo inválido {r.axis}")
        if r.intensity not in INTENSITY:
            errors.append(f"{r.rule_id}: intensidade inválida {r.intensity}")
        if r.source_id not in sources:
            errors.append(f"{r.rule_id}: fonte não registrada {r.source_id}")
        if r.evidence_type not in {"documented_physical_rule", "official_food_table", "culinary_heuristic"}:
            errors.append(f"{r.rule_id}: evidence_type inválido")
        if r.evidence_type == "culinary_heuristic" and not r.limitations:
            errors.append(f"{r.rule_id}: heurística exige limitação")
    return errors


@dataclass(frozen=True)
class SensoryEvidence:
    category: str
    subject_id: str
    attribute: str
    value: str
    source_id: str | None
    method: str
    confidence: str
    note: str = ""

    def __post_init__(self):
        if self.category not in EVIDENCE_CATEGORIES:
            raise ValueError(f"categoria inválida: {self.category}")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SensoryComponent:
    component_id: str
    entity_id: str | None
    role: str                                   # main | sauce | side | garnish
    food_group: str | None = None
    observations: list[EvidenceClaim] = field(default_factory=list)   # gosto/aroma observados
    preferences: list[EvidenceClaim] = field(default_factory=list)
    textures: list[TextureAttribute] = field(default_factory=list)
    ancestors: tuple[str, ...] = ()            # linhagem no catálogo, para regras por conceito/grupo


@dataclass
class SensoryAssessment:
    dominant_attributes: list[dict]
    supporting_attributes: list[dict]
    possible_excesses: list[dict]
    contrast_opportunities: list[dict]
    texture_profile: dict[str, list[dict]]
    aroma_evidence: list[dict]
    unknowns: list[str]
    evidence: list[dict] = field(default_factory=list)
    preferences: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- inferências por regra
def inferred_properties(component: SensoryComponent, rules: list[SensoryRule]) -> list[SensoryEvidence]:
    keys = {component.entity_id, component.food_group, *component.ancestors} - {None}
    out = []
    for r in rules:
        if r.subject in keys:
            out.append(SensoryEvidence("inferred_property", component.component_id, r.axis, r.intensity,
                                       r.source_id, f"regra {r.rule_id}: {r.statement_pt}",
                                       "low" if r.evidence_type == "culinary_heuristic" else "moderate",
                                       r.limitations))
    return out


def observed_properties(component: SensoryComponent) -> list[SensoryEvidence]:
    out = []
    for c in component.observations:
        if c.evidence_type not in {"human_observation", "experimental_measurement"}:
            continue
        out.append(SensoryEvidence("human_observation", component.component_id, c.predicate, str(c.value),
                                   c.source_id, c.method or "", c.confidence, c.limitations or ""))
    return out


# --------------------------------------------------------------------------- aroma (FlavorDB)
def aroma_evidence(db, ingredient_id: str, *, component_id: str | None = None, top: int = 8) -> list[SensoryEvidence]:
    """Moléculas e descritores da fonte, em categorias separadas. Não é percepção no prato."""
    mols = sorted(db.molecules_of(ingredient_id))
    subject = component_id or ingredient_id
    source = "flavordb2" if ingredient_id.startswith("fdb:") else "flavorgraph_191120"
    out = [SensoryEvidence("molecule_presence", subject, "n_molecules", str(len(mols)), source,
                           f"perfil molecular de {ingredient_id}", "moderate",
                           "presença registrada na fonte; concentração e percepção desconhecidas")]
    counts: dict[str, int] = {}
    for cid in mols:
        for d in db.descriptors_by_molecule.get(cid, []):
            counts[d] = counts.get(d, 0) + 1
    for d, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]:
        out.append(SensoryEvidence("molecule_descriptor", subject, d, str(n), "flavordb2",
                                   f"{n} molécula(s) com o descritor '{d}'", "low",
                                   "descritor da molécula isolada; não indica que o prato tenha esse aroma"))
    return out


def pair_metrics(db, a: str, b: str) -> dict:
    """Jaccard e NPMI como métricas próprias, com interpretação que não vira preferência."""
    ma, mb = db.molecules_of(a), db.molecules_of(b)
    union = ma | mb
    jac = len(ma & mb) / len(union) if union else None
    npmi = db.npmi(a, b)
    npmi = None if npmi is None or (isinstance(npmi, float) and math.isnan(npmi)) else float(npmi)
    if npmi is None:
        interp = "sem dados de co-ocorrência: não implica incompatibilidade"
    elif npmi <= 0:
        interp = "sem associação acima do acaso em receitas: não implica incompatibilidade"
    else:
        interp = "associação positiva em receitas (frequência), não preferência"
    return {"jaccard": jac, "npmi": npmi, "npmi_interpretation": interp, "incompatible": None,
            "note": "Jaccard mede moléculas compartilhadas; NPMI mede co-ocorrência. Nenhum mede gosto."}


# --------------------------------------------------------------------------- avaliação
CONTRAST_RULES = {
    # alvo ausente quando predominam -> oportunidade (heurísticas declaradas)
    "crocante": {"when_any": ("macio", "cremoso", "suculento"),
                 "statement": "elemento crocante pode contrastar com componentes macios/cremosos",
                 "source_id": "saborlab_sensory_heuristics",
                 "limitation": "heurística culinária; evidência de que contraste aumenta preferência é limitada"},
}
ACID_FAT_RULE = {"statement": "acidez pode contrapor sensação de gordura intensa",
                 "source_id": "saborlab_sensory_heuristics",
                 "limitation": "heurística culinária; não é regra quantitativa"}


def assess(components: Iterable[SensoryComponent], *, rules: list[SensoryRule] | None = None,
           aroma: Iterable[SensoryEvidence] = ()) -> SensoryAssessment:
    rules = rules if rules is not None else load_sensory_rules()
    components = list(components)
    evidence: list[SensoryEvidence] = []
    by_axis: dict[str, list[SensoryEvidence]] = {}
    for comp in components:
        props = inferred_properties(comp, rules) + observed_properties(comp)
        evidence.extend(props)
        for p in props:
            by_axis.setdefault(p.attribute, []).append(p)
    main_ids = {c.component_id for c in components if c.role in {"main", "sauce"}}

    dominant, supporting, excesses = [], [], []
    for axis in sorted(by_axis):
        items = by_axis[axis]
        contributors = sorted({e.subject_id for e in items})
        high = sorted({e.subject_id for e in items if e.value == "high"})
        entry = {"attribute": axis, "contributors": contributors,
                 "evidence_categories": sorted({e.category for e in items}),
                 "confidence": "low" if all(e.confidence in {"low", "qualitative"} for e in items) else "moderate"}
        if high and set(high) & main_ids:
            dominant.append(entry)
        else:
            supporting.append(entry)
        if len(high) >= 2:
            excesses.append({**entry, "reason": f"intensidade alta esperada em {len(high)} componentes",
                             "note": "possível excesso; depende de quantidades e composição reais (desconhecidas)"})

    textures: list[TextureAttribute] = [t for c in components for t in c.textures]
    profile = texture_profile([t for t in textures if t.status == "observed"],
                              [t for t in textures if t.status == "expected"])
    opportunities = []
    present = {t for t in TEXTURE_TERMS if status_of(t, profile) != "unknown"}
    for target, rule in CONTRAST_RULES.items():
        if target not in present and present & set(rule["when_any"]):
            opportunities.append({"opportunity": f"adicionar textura {target}", "because": sorted(present & set(rule["when_any"])),
                                  "statement": rule["statement"], "source_id": rule["source_id"],
                                  "evidence_type": "culinary_heuristic", "limitations": rule["limitation"],
                                  "kind": "oportunidade, não requisito"})
    fat_high = any(e.value == "high" for e in by_axis.get("sensacao_de_gordura", []))
    if fat_high:
        opportunities.append({"opportunity": "equilibrar gordura com acidez", "because": ["sensacao_de_gordura"],
                              "statement": ACID_FAT_RULE["statement"], "source_id": ACID_FAT_RULE["source_id"],
                              "evidence_type": "culinary_heuristic", "limitations": ACID_FAT_RULE["limitation"],
                              "kind": "oportunidade, não requisito",
                              "already_present": bool(by_axis.get("acido"))})

    unknowns = [f"{axis}: sem evidência" for axis in TASTE_AXES if axis not in by_axis]
    unknowns += [f"textura {t}: desconhecida" for t in TEXTURE_TERMS if status_of(t, profile) == "unknown"]
    unknowns.append("quantidades, temperatura de serviço e composição exata dos componentes")
    prefs = [{"component": c.component_id, "claim": p.to_dict(), "category": "user_preference"}
             for c in components for p in c.preferences]
    return SensoryAssessment(dominant, supporting, excesses, opportunities, profile,
                             [a.to_dict() for a in aroma], unknowns, [e.to_dict() for e in evidence], prefs)
