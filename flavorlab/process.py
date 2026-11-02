"""Grafo de preparo: equipamentos, técnicas, cortes, transformações, controles de segurança
e processos de receita como DAG de etapas (demanda 003).

Separação deliberada:

* **dados** curados em ``data/culinary/*.csv`` (cada linha cita ``source_id`` do
  registro único ``data/knowledge/sources.csv``);
* **domínio** (este módulo): tipos e validação;
* **algoritmo** (``flavorlab.scheduler``): ordenação, recursos e caminho crítico;
* **estado e evidência** (``flavorlab.states``/``flavorlab.evidence``, demanda 005):
  tempos e temperaturas das etapas são ``EvidenceClaim``; executar uma etapa gera um
  ``ProcessEvent``. Etapas planejadas nunca alteram o estado do ingrediente.

Alvo culinário (dourar, amaciar) e controle de segurança alimentar são campos e
tabelas diferentes: ``target_temp_c`` vem da técnica/receita; ``safety_control_id``
aponta um controle com fonte oficial.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Iterable, Mapping

from .evidence import EvidenceClaim, EvidenceStore, SourceRegistry
from .states import ProcessEvent, to_canonical

ROOT = Path(__file__).resolve().parents[1]
CULINARY_DIR = ROOT / "data" / "culinary"
PROCESSES_DIR = CULINARY_DIR / "processes"

PHASES = ("planejamento", "mise_en_place", "preaquecimento", "coccao", "montagem", "descanso",
          "finalizacao", "servico")
ATTENTION = ("active", "check", "passive")
OFFICIAL_SOURCE_TYPES = {"official_regulation", "official_guidance"}


class ProcessError(ValueError):
    """Processo, etapa ou dado culinário inválido."""


def _split(value: str) -> tuple[str, ...]:
    return tuple(v.strip() for v in str(value or "").split("|") if v.strip())


def _attrs(value: str) -> dict[str, str]:
    out = {}
    for item in str(value or "").split(";"):
        if "=" in item:
            k, v = item.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _num(value: str) -> float | None:
    value = str(value or "").strip()
    return float(value) if value else None


# --------------------------------------------------------------------------- dados curados
@dataclass(frozen=True)
class Equipment:
    equipment_id: str
    type: str
    name_pt: str
    capacity: int | None
    capacity_unit: str
    heat_mode: str
    min_temp_c: float | None
    max_temp_c: float | None
    is_heat_source: bool
    attributes: Mapping[str, str]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class Technique:
    technique_id: str
    name_pt: str
    category: str
    compatible_equipment: tuple[str, ...]
    parameters: Mapping[str, str]
    effects: tuple[str, ...]              # transformation_ids que a técnica PODE provocar
    event_kind: str                       # tipo de ProcessEvent quando executada
    thermal: bool                         # aplica calor ao alimento
    sources: tuple[str, ...]
    limitations: str = ""


@dataclass(frozen=True)
class CutTechnique:
    cut_id: str
    name_pt: str
    geometry: str
    target_size_mm: tuple[float | None, float | None]
    applicable_groups: tuple[str, ...]    # sl:group:* do catálogo
    effect: str
    sources: tuple[str, ...]
    notes: str = ""


@dataclass(frozen=True)
class Transformation:
    transformation_id: str
    name_pt: str
    inputs: tuple[str, ...]
    conditions: str
    sensory_effects: str
    limitations: str
    evidence_type: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class SafetyControl:
    control_id: str
    name_pt: str
    control_type: str                     # min_internal_temp | hot_holding | cold_holding | time_out_of_control | parasite_freezing
    food_scope: str                       # descrição do escopo de alimento coberto
    applicable_groups: tuple[str, ...]
    value: float | None
    unit: str
    hold_time_s: float | None
    jurisdiction: str
    source_id: str
    notes: str = ""


@dataclass
class CulinaryKnowledge:
    equipment: dict[str, Equipment]
    techniques: dict[str, Technique]
    cuts: dict[str, CutTechnique]
    transformations: dict[str, Transformation]
    safety_controls: dict[str, SafetyControl]
    sources: SourceRegistry

    @classmethod
    def load(cls, path: Path | str = CULINARY_DIR, sources: SourceRegistry | None = None) -> "CulinaryKnowledge":
        path = Path(path)

        def rows(name):
            with open(path / f"{name}.csv", newline="", encoding="utf-8") as fh:
                return [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(fh)]

        equipment = {r["equipment_id"]: Equipment(
            r["equipment_id"], r["type"], r["name_pt"], int(r["capacity"]) if r["capacity"] else None,
            r["capacity_unit"], r["heat_mode"], _num(r["min_temp_c"]), _num(r["max_temp_c"]),
            r["is_heat_source"] == "true", _attrs(r["attributes"]), _split(r["sources"]))
            for r in rows("equipment")}
        techniques = {r["technique_id"]: Technique(
            r["technique_id"], r["name_pt"], r["category"], _split(r["compatible_equipment"]),
            _attrs(r["parameters"]), _split(r["effects"]), r["event_kind"], r["thermal"] == "true",
            _split(r["sources"]), r.get("limitations", "")) for r in rows("techniques")}
        cuts = {r["cut_id"]: CutTechnique(
            r["cut_id"], r["name_pt"], r["geometry"], (_num(r["size_mm_min"]), _num(r["size_mm_max"])),
            _split(r["applicable_groups"]), r["effect"], _split(r["sources"]), r.get("notes", ""))
            for r in rows("cuts")}
        transformations = {r["transformation_id"]: Transformation(
            r["transformation_id"], r["name_pt"], _split(r["inputs"]), r["conditions"], r["sensory_effects"],
            r["limitations"], r["evidence_type"], _split(r["sources"])) for r in rows("transformations")}
        controls = {r["control_id"]: SafetyControl(
            r["control_id"], r["name_pt"], r["control_type"], r["food_scope"], _split(r["applicable_groups"]),
            _num(r["value"]), r["unit"], _num(r["hold_time_s"]), r["jurisdiction"], r["source_id"], r.get("notes", ""))
            for r in rows("safety_controls")}
        return cls(equipment, techniques, cuts, transformations, controls, sources or SourceRegistry.load())

    def validate(self) -> list[str]:
        errors: list[str] = []
        err = errors.append

        def check_sources(tag, ids):
            if not ids:
                err(f"{tag}: sem fonte")
            for s in ids:
                if s not in self.sources:
                    err(f"{tag}: fonte não registrada {s!r}")

        for e in self.equipment.values():
            check_sources(e.equipment_id, e.sources)
            if e.min_temp_c is not None and e.max_temp_c is not None and e.min_temp_c > e.max_temp_c:
                err(f"{e.equipment_id}: faixa de temperatura invertida")
        for t in self.techniques.values():
            check_sources(t.technique_id, t.sources)
            for eq in t.compatible_equipment:
                if eq not in self.equipment:
                    err(f"{t.technique_id}: equipamento inexistente {eq}")
            for tr in t.effects:
                if tr not in self.transformations:
                    err(f"{t.technique_id}: transformação inexistente {tr}")
        for c in self.cuts.values():
            check_sources(c.cut_id, c.sources)
            lo, hi = c.target_size_mm
            if lo is not None and hi is not None and lo > hi:
                err(f"{c.cut_id}: faixa de tamanho invertida")
            if not c.effect:
                err(f"{c.cut_id}: efeito operacional obrigatório")
        for tr in self.transformations.values():
            check_sources(tr.transformation_id, tr.sources)
            if not tr.limitations:
                err(f"{tr.transformation_id}: limitações obrigatórias")
        for sc in self.safety_controls.values():
            if sc.source_id not in self.sources:
                err(f"{sc.control_id}: fonte não registrada {sc.source_id!r}")
                continue
            src = self.sources.get(sc.source_id)
            if src.source_type not in OFFICIAL_SOURCE_TYPES:
                err(f"{sc.control_id}: controle de segurança exige fonte oficial")
            if src.verification_status != "verified" or not src.url:
                err(f"{sc.control_id}: fonte oficial precisa de URL verificada e data de acesso")
            if sc.value is not None and not sc.unit:
                err(f"{sc.control_id}: valor sem unidade")
        return errors


# --------------------------------------------------------------------------- receita como grafo
@dataclass(frozen=True)
class ProcessStep:
    step_id: str
    recipe_id: str
    phase: str
    title: str
    instruction: str
    ingredient_refs: tuple[str, ...] = ()        # instâncias (recipe:EX01:line:1) ou IDs do catálogo
    technique_id: str | None = None
    cut_id: str | None = None
    equipment_refs: tuple[str, ...] = ()         # IDs de recursos do processo (não do catálogo)
    active_duration_s: float | None = None
    passive_duration_s: float | None = None
    target_temp_c: float | None = None           # alvo CULINÁRIO (forno, óleo...), não segurança
    acceptable_range_c: tuple[float, float] | None = None
    dependencies: tuple[str, ...] = ()
    attention: str = "active"
    completion_signal: str = ""
    safety_control_id: str | None = None
    claim_ids: Mapping[str, str] = field(default_factory=dict)   # campo -> claim_id (demanda 005)
    transformations: tuple[str, ...] = ()        # transformações BUSCADAS (possíveis, não garantidas)
    notes: str = ""

    @property
    def duration_s(self) -> float:
        return float((self.active_duration_s or 0) + (self.passive_duration_s or 0))

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("ingredient_refs", "equipment_refs", "dependencies", "transformations"):
            d[k] = list(d[k])
        d["acceptable_range_c"] = list(self.acceptable_range_c) if self.acceptable_range_c else None
        d["claim_ids"] = dict(self.claim_ids)
        return d

    def planned_events(self, knowledge: CulinaryKnowledge) -> list[ProcessEvent]:
        """Eventos PLANEJADOS por ingrediente (``planned=True``): não alteram estado até a execução."""
        if not self.technique_id:
            kind = "cut" if self.cut_id else "observe"
        else:
            kind = knowledge.techniques[self.technique_id].event_kind
        return [ProcessEvent(f"{self.step_id}:{ref}", ref, kind, tuple(self.claim_ids.values()),
                             technique_id=self.technique_id, planned=True,
                             equipment_id=self.equipment_refs[0] if self.equipment_refs else None)
                for ref in self.ingredient_refs]


@dataclass(frozen=True)
class Resource:
    resource_id: str
    equipment_id: str
    capacity: int = 1


@dataclass(frozen=True)
class IngredientRef:
    ref_id: str
    entity_id: str | None
    display_name: str
    legacy_line: int | None = None


@dataclass
class RecipeProcess:
    recipe_id: str
    servings: int | None
    steps: list[ProcessStep]
    resources: dict[str, Resource]
    ingredients: dict[str, IngredientRef]
    provenance: str
    claims: EvidenceStore
    cooks: int = 1
    notes: str = ""

    def step(self, step_id: str) -> ProcessStep:
        for s in self.steps:
            if s.step_id == step_id:
                return s
        raise ProcessError(f"etapa inexistente: {step_id}")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], sources: SourceRegistry | None = None) -> "RecipeProcess":
        claims = EvidenceStore((EvidenceClaim.from_dict(c) for c in data.get("claims", [])), sources)
        steps = []
        for s in data["steps"]:
            s = dict(s)
            for k in ("ingredient_refs", "equipment_refs", "dependencies", "transformations"):
                s[k] = tuple(s.get(k) or ())
            if s.get("acceptable_range_c"):
                s["acceptable_range_c"] = tuple(s["acceptable_range_c"])
            s.setdefault("recipe_id", data["recipe_id"])
            s["claim_ids"] = dict(s.get("claim_ids") or {})
            steps.append(_step_from_claims(ProcessStep(**s), claims))
        resources = {r["resource_id"]: Resource(r["resource_id"], r["equipment_id"], int(r.get("capacity", 1)))
                     for r in data.get("resources", [])}
        ingredients = {i["ref_id"]: IngredientRef(i["ref_id"], i.get("entity_id"), i["display_name"],
                                                  i.get("legacy_line")) for i in data.get("ingredients", [])}
        return cls(data["recipe_id"], data.get("servings"), steps, resources, ingredients,
                   data.get("provenance", ""), claims, int(data.get("cooks", 1)), data.get("notes", ""))

    @classmethod
    def load(cls, path: Path | str, sources: SourceRegistry | None = None) -> "RecipeProcess":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")), sources)

    def to_dict(self) -> dict:
        return {"recipe_id": self.recipe_id, "servings": self.servings, "cooks": self.cooks,
                "provenance": self.provenance, "notes": self.notes,
                "resources": [asdict(r) for r in self.resources.values()],
                "ingredients": [asdict(i) for i in self.ingredients.values()],
                "claims": [c.to_dict() for c in self.claims],
                "steps": [s.to_dict() for s in self.steps]}


# Campos numéricos da etapa que vêm de claims (valor + unidade convertidos)
STEP_CLAIM_FIELDS = {"active_duration_s": "process_duration_s", "passive_duration_s": "process_duration_s",
                     "target_temp_c": "process_temperature_c"}


def _step_from_claims(step: ProcessStep, claims: EvidenceStore) -> ProcessStep:
    """Preenche durações/temperaturas a partir dos claims citados, convertendo unidades.

    Um número escrito direto na etapa sem claim é recusado: tempo e temperatura são
    dados críticos e precisam de origem (receita, heurística declarada, medição).
    """
    values = {}
    for name, canonical in STEP_CLAIM_FIELDS.items():
        cid = step.claim_ids.get(name)
        if cid is None:
            if getattr(step, name) is not None:
                raise ProcessError(f"{step.step_id}: {name} sem claim de origem")
            continue
        c = claims.get(cid)
        values[name] = to_canonical(canonical, c.value, c.unit)
    if values:
        data = {f.name: getattr(step, f.name) for f in fields(step)}
        data.update(values)
        return ProcessStep(**data)
    return step


# --------------------------------------------------------------------------- validação
def find_cycle(steps: Iterable[ProcessStep]) -> list[str] | None:
    """Um ciclo de dependências (lista de step_ids fechando no primeiro) ou ``None``."""
    deps = {s.step_id: list(s.dependencies) for s in steps}
    color: dict[str, int] = {}
    stack: list[str] = []

    def visit(n: str) -> list[str] | None:
        color[n] = 1
        stack.append(n)
        for m in sorted(deps.get(n, [])):
            if m not in deps:
                continue
            if color.get(m) == 1:
                return stack[stack.index(m):] + [m]
            if color.get(m) is None:
                found = visit(m)
                if found:
                    return found
        stack.pop()
        color[n] = 2
        return None

    for n in sorted(deps):
        if color.get(n) is None:
            found = visit(n)
            if found:
                return found
    return None


def validate_process(proc: RecipeProcess, knowledge: CulinaryKnowledge, catalog=None) -> list[str]:
    errors: list[str] = []
    err = errors.append
    ids = [s.step_id for s in proc.steps]
    if len(ids) != len(set(ids)):
        err(f"{proc.recipe_id}: step_id duplicado")
    known = set(ids)
    for s in proc.steps:
        tag = f"{proc.recipe_id}/{s.step_id}"
        if s.phase not in PHASES:
            err(f"{tag}: fase inválida {s.phase!r}")
        if s.attention not in ATTENTION:
            err(f"{tag}: atenção inválida {s.attention!r}")
        for d in s.dependencies:
            if d not in known:
                err(f"{tag}: dependência inexistente {d}")
        if s.step_id in s.dependencies:
            err(f"{tag}: depende de si mesma")
        for r in s.equipment_refs:
            if r not in proc.resources:
                err(f"{tag}: recurso inexistente {r}")
        for ref in s.ingredient_refs:
            if ref not in proc.ingredients:
                err(f"{tag}: ingrediente inexistente {ref}")
        for v in ("active_duration_s", "passive_duration_s"):
            x = getattr(s, v)
            if x is not None and x < 0:
                err(f"{tag}: {v} negativo")
        if s.duration_s <= 0:
            err(f"{tag}: duração total desconhecida ou zero (informe claim; desconhecido não vira zero)")
        technique = knowledge.techniques.get(s.technique_id) if s.technique_id else None
        if s.technique_id and technique is None:
            err(f"{tag}: técnica inexistente {s.technique_id}")
        if technique is not None and technique.compatible_equipment:
            used = {proc.resources[r].equipment_id for r in s.equipment_refs if r in proc.resources}
            tools = {e for e in used if knowledge.equipment.get(e) and knowledge.equipment[e].type != "instrument"}
            wrong = tools - set(technique.compatible_equipment)
            if wrong:
                err(f"{tag}: técnica {s.technique_id} incompatível com {sorted(wrong)}")
        for tr in s.transformations:
            if tr not in knowledge.transformations:
                err(f"{tag}: transformação inexistente {tr}")
            elif technique is not None and tr not in technique.effects:
                err(f"{tag}: {tr} não é efeito documentado da técnica {s.technique_id}")
        if s.cut_id:
            cut = knowledge.cuts.get(s.cut_id)
            if cut is None:
                err(f"{tag}: corte inexistente {s.cut_id}")
            elif catalog is not None:
                for ref in s.ingredient_refs:
                    ing = proc.ingredients.get(ref)
                    if ing and ing.entity_id and ing.entity_id in catalog:
                        group = catalog.food_group(ing.entity_id)
                        if cut.applicable_groups and group not in cut.applicable_groups:
                            err(f"{tag}: corte {s.cut_id} não se aplica a {ing.display_name} ({group})")
        if s.safety_control_id:
            sc = knowledge.safety_controls.get(s.safety_control_id)
            if sc is None:
                err(f"{tag}: controle de segurança inexistente {s.safety_control_id}")
        if s.target_temp_c is not None and s.acceptable_range_c is not None:
            lo, hi = s.acceptable_range_c
            if not lo <= s.target_temp_c <= hi:
                err(f"{tag}: alvo fora da faixa aceitável")
        for name, cid in s.claim_ids.items():
            if cid not in {c.claim_id for c in proc.claims}:
                err(f"{tag}: claim inexistente {cid}")
    cycle = find_cycle(proc.steps)
    if cycle:
        err(f"{proc.recipe_id}: ciclo de dependências: {' -> '.join(cycle)}")
    for ing in proc.ingredients.values():
        if catalog is not None and ing.entity_id and ing.entity_id not in catalog:
            err(f"{proc.recipe_id}: ingrediente {ing.ref_id} com ID fora do catálogo {ing.entity_id}")
    return errors


# --------------------------------------------------------------------------- segurança × alvo
@dataclass
class StepControls:
    """Controles de uma etapa, separados por natureza."""
    step_id: str
    culinary_target: dict | None
    safety: dict | None
    warnings: list[str]


def step_controls(step: ProcessStep, proc: RecipeProcess, knowledge: CulinaryKnowledge) -> StepControls:
    warnings: list[str] = []
    culinary = None
    if step.target_temp_c is not None:
        cid = step.claim_ids.get("target_temp_c")
        claim = proc.claims.get(cid) if cid else None
        culinary = {"kind": "culinary_target", "target_temp_c": step.target_temp_c,
                    "acceptable_range_c": step.acceptable_range_c,
                    "evidence_type": claim.evidence_type if claim else None,
                    "note": "alvo culinário (equipamento/meio); não é critério de segurança"}
    safety = None
    if step.safety_control_id:
        sc = knowledge.safety_controls[step.safety_control_id]
        src = knowledge.sources.get(sc.source_id)
        safety = {"kind": "safety_control", "control_id": sc.control_id, "control_type": sc.control_type,
                  "value": sc.value, "unit": sc.unit, "hold_time_s": sc.hold_time_s,
                  "jurisdiction": sc.jurisdiction, "source_id": sc.source_id, "url": src.url,
                  "accessed_at": src.accessed_at, "note": sc.notes}
    technique = knowledge.techniques.get(step.technique_id) if step.technique_id else None
    if technique is not None and not technique.thermal and technique.event_kind == "marinate":
        warnings.append("marinada ácida desnatura proteínas mas não equivale a cocção térmica nem garante "
                        "eliminação de patógenos/parasitas")
    if technique is not None and technique.thermal and safety is None:
        warnings.append("sem controle de segurança associado a esta etapa térmica: segurança indeterminada")
    return StepControls(step.step_id, culinary, safety, warnings)


def thermally_cooked(step: ProcessStep, knowledge: CulinaryKnowledge) -> bool:
    """A técnica aplica calor ao alimento? (marinada ácida: não)."""
    t = knowledge.techniques.get(step.technique_id) if step.technique_id else None
    return bool(t and t.thermal)


def load_processes(directory: Path | str = PROCESSES_DIR, sources: SourceRegistry | None = None) -> dict[str, RecipeProcess]:
    sources = sources or SourceRegistry.load()
    out = {}
    for p in sorted(Path(directory).glob("*.json")):
        proc = RecipeProcess.load(p, sources)
        out[proc.recipe_id] = proc
    return out
