"""Avaliação qualitativa de transformações culinárias (demanda 006).

Reutiliza:

* ``Transformation`` e ``Technique`` de ``flavorlab.process`` (demanda 003);
* ``IngredientState``, ``EvidenceClaim`` e o registro de fontes (demanda 005).

Regras em ``data/knowledge/transformation_rules.csv``: cada linha diz que um *fato*
é necessário, favorece, inibe ou é crítico (precisa ser conhecido) para uma
transformação, com fonte e limitação. Não há cinética: só condições.

Status:

``observed``
    há claim de observação/medição de que a transformação ocorreu nesta instância.
``likely``
    técnica compatível, entradas necessárias presentes, condições críticas
    informadas, ao menos um fator favorável e nenhum inibidor conhecido.
``possible``
    técnica compatível, mas falta dado (temperatura, tempo, composição) ou há
    inibidor; a conclusão é rebaixada e o que falta fica listado.
``unsupported``
    técnica não documentada para a transformação ou entrada necessária ausente.

Técnica compatível torna a transformação **possível**, nunca comprovada.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .evidence import EvidenceClaim, EvidenceStore, SourceRegistry, new_claim
from .process import CulinaryKnowledge
from .states import IngredientState, to_canonical

ROOT = Path(__file__).resolve().parents[1]
RULES_CSV = ROOT / "data" / "knowledge" / "transformation_rules.csv"
STATUSES = ("observed", "likely", "possible", "unsupported")
RULE_KINDS = ("necessary", "favoring", "inhibiting", "critical")
MEDIA = ("dry", "fat", "moist", "acid", "mixed", "unknown")


# --------------------------------------------------------------------------- condições
@dataclass(frozen=True)
class ProcessConditions:
    """Condições informadas. ``None`` = desconhecido (nunca um valor presumido)."""
    temperature_c: float | None = None
    duration_s: float | None = None
    medium: str = "unknown"                 # dry | fat | moist | acid | mixed | unknown
    ph: float | None = None
    agitation: str | None = None            # none | gentle | vigorous
    emulsifier_present: bool | None = None
    oxygen_exposure: bool | None = None
    claim_ids: tuple[str, ...] = ()

    def __post_init__(self):
        if self.medium not in MEDIA:
            raise ValueError(f"meio inválido: {self.medium!r}")

    @classmethod
    def from_claims(cls, claims: Iterable[EvidenceClaim], **kw) -> "ProcessConditions":
        """Temperatura e tempo a partir de claims (unidade convertida; origem preservada)."""
        values: dict[str, Any] = {}
        ids = []
        for c in claims:
            if c.predicate == "process_temperature_c":
                values["temperature_c"] = to_canonical("process_temperature_c", c.value, c.unit)
            elif c.predicate == "process_duration_s":
                values["duration_s"] = to_canonical("process_duration_s", c.value, c.unit)
            elif c.predicate == "ph":
                values["ph"] = float(c.value)
            else:
                continue
            ids.append(c.claim_id)
        values.update(kw)
        return cls(claim_ids=tuple(ids), **values)

    def provided(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items()
                if k != "claim_ids" and v is not None and v != "unknown"}


# --------------------------------------------------------------------------- composição
COMPOSITION_FACTS = ("has_protein", "has_sugar", "has_starch", "has_water", "has_fat", "is_acidified")
NUTRIENT_FACTS = {"has_protein": "proteina_g", "has_sugar": "acucares_g", "has_starch": "amido_g",
                  "has_water": "agua_g", "has_fat": "lipideos_g"}


def composition_from_claims(claims: Iterable[EvidenceClaim]) -> dict[str, bool | None]:
    """Fatos de composição (presença) a partir de claims ``has_*`` / ``is_acidified``."""
    facts: dict[str, bool | None] = {f: None for f in COMPOSITION_FACTS}
    for c in claims:
        if c.predicate in facts and c.value is not None:
            facts[c.predicate] = bool(c.value)
    return facts


# --------------------------------------------------------------------------- regras
@dataclass(frozen=True)
class TransformationRule:
    rule_id: str
    transformation_id: str
    kind: str
    fact: str
    operator: str
    value: str
    statement_pt: str
    source_id: str
    evidence_type: str
    limitations: str

    def evaluate(self, facts: Mapping[str, Any]) -> bool | None:
        """True/False quando o fato é conhecido; ``None`` quando desconhecido."""
        v = facts.get(self.fact)
        if self.operator == "known":
            return v is not None and v != "unknown"
        if v is None or v == "unknown":
            return None
        if self.operator == "true":
            return bool(v) is True
        if self.operator == "false":
            return bool(v) is False
        if self.operator == "in":
            return str(v) in {x.strip() for x in self.value.split("|")}
        if self.operator == "ge":
            return float(v) >= float(self.value)
        if self.operator == "le":
            return float(v) <= float(self.value)
        if self.operator == "lt":
            return float(v) < float(self.value)
        raise ValueError(f"{self.rule_id}: operador inválido {self.operator!r}")


def load_rules(path: Path | str = RULES_CSV) -> list[TransformationRule]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [TransformationRule(**{k: (v or "").strip() for k, v in r.items()}) for r in csv.DictReader(fh)]


def validate_rules(rules: list[TransformationRule], knowledge: CulinaryKnowledge) -> list[str]:
    errors = []
    for r in rules:
        tag = r.rule_id
        if r.transformation_id not in knowledge.transformations:
            errors.append(f"{tag}: transformação inexistente {r.transformation_id}")
        if r.kind not in RULE_KINDS:
            errors.append(f"{tag}: kind inválido {r.kind}")
        if r.operator not in {"known", "true", "false", "in", "ge", "le", "lt"}:
            errors.append(f"{tag}: operador inválido {r.operator}")
        if r.source_id not in knowledge.sources:
            errors.append(f"{tag}: fonte não registrada {r.source_id}")
        if r.evidence_type not in {"documented_physical_rule", "culinary_heuristic"}:
            errors.append(f"{tag}: evidence_type deve ser regra documentada ou heurística declarada")
        if r.evidence_type == "culinary_heuristic" and not r.limitations:
            errors.append(f"{tag}: heurística exige limitação")
        if r.operator in {"ge", "le", "lt"}:
            try:
                float(r.value)
            except ValueError:
                errors.append(f"{tag}: valor numérico inválido")
            if r.evidence_type != "documented_physical_rule":
                errors.append(f"{tag}: limiar numérico só com regra documentada")
    ids = [r.rule_id for r in rules]
    if len(ids) != len(set(ids)):
        errors.append("rule_id duplicado")
    return errors


# --------------------------------------------------------------------------- avaliação
@dataclass
class TransformationAssessment:
    transformation_id: str
    name_pt: str
    status: str
    technique_id: str | None
    provided_conditions: dict[str, Any]
    missing: list[str]
    satisfied: list[str]
    violated: list[str]
    inhibitors: list[str]
    effects: str
    evidence: list[EvidenceClaim]
    sources: list[str]
    limitations: list[str]
    needed_for_quantification: list[str]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["evidence"] = [c.to_dict() for c in self.evidence]
        return d

    def to_claim(self, subject_id: str) -> EvidenceClaim:
        """O resultado como claim: possível = hipótese; provável = regra documentada aplicada."""
        etype, conf = {"likely": ("documented_physical_rule", "moderate"),
                       "possible": ("unvalidated_hypothesis", "low"),
                       "unsupported": ("unvalidated_hypothesis", "low")}.get(self.status, (None, None))
        if self.status == "observed":
            return self.evidence[0]
        return new_claim(
            claim_id=f"{subject_id}:transformation:{self.transformation_id}", subject_id=subject_id,
            predicate="transformation_status", value=self.status, unit=None, evidence_type=etype,
            confidence=conf, source_id=self.sources[0] if (etype == "documented_physical_rule" and self.sources) else None,
            method="flavorlab.transformations.analyze_transformations",
            limitations="; ".join(self.limitations) or "avaliação qualitativa; não comprova ocorrência",
            context=self.technique_id)


QUANTIFICATION_NEEDS = {
    "maillard_reaction": ["temperatura de superfície medida", "atividade de água", "pH", "teor de açúcares redutores"],
    "caramelization": ["temperatura medida do açúcar/superfície", "tipo e teor de açúcar", "pH"],
    "starch_gelatinization": ["tipo de amido", "razão água:amido", "perfil de temperatura"],
    "protein_denaturation_heat": ["temperatura interna medida", "tempo", "tipo de proteína"],
    "acid_denaturation": ["pH medido do meio", "tempo de contato", "espessura do pedaço"],
    "emulsification": ["fração de óleo", "emulsificante e concentração", "cisalhamento"],
    "phase_separation": ["temperatura medida", "pH", "composição de gordura/proteína", "emulsificantes"],
    "evaporation_reduction": ["massa antes/depois", "área, potência e tampa"],
    "hydration_rest": ["massa de água absorvida", "tempo"],
    "fermentation_concept": ["cultura", "temperatura", "tempo", "pH"],
    "lipid_oxidation": ["valor de peróxidos/TBARS", "exposição a O2, luz e metais", "temperatura e tempo"],
    "moisture_loss_softening": ["massa antes/depois", "temperatura interna", "tempo", "corte e teor de colágeno"],
}


def analyze_transformations(state: IngredientState | None, technique_id: str, conditions: ProcessConditions,
                            *, knowledge: CulinaryKnowledge | None = None,
                            rules: list[TransformationRule] | None = None,
                            composition: Mapping[str, bool | None] | None = None,
                            observations: Iterable[EvidenceClaim] = (),
                            transformation_ids: Iterable[str] | None = None) -> list[TransformationAssessment]:
    """Avalia cada transformação para um ingrediente (estado), técnica e condições informadas."""
    knowledge = knowledge or CulinaryKnowledge.load()
    rules = rules if rules is not None else load_rules()
    technique = knowledge.techniques.get(technique_id)
    if technique is None:
        raise ValueError(f"técnica inexistente: {technique_id}")
    facts: dict[str, Any] = {f: None for f in COMPOSITION_FACTS}
    facts.update(composition or {})
    facts.update(conditions.provided())
    facts["medium"] = conditions.medium
    facts["heat_applied"] = technique.thermal
    facts["technique_category"] = technique.category
    observed = {c.value: c for c in observations
                if c.predicate == "transformation_observed"
                and c.evidence_type in {"human_observation", "experimental_measurement"}
                and (state is None or c.subject_id == state.instance_id)}

    ids = list(transformation_ids) if transformation_ids is not None else sorted(knowledge.transformations)
    out = []
    for tid in ids:
        tr = knowledge.transformations[tid]
        my_rules = [r for r in rules if r.transformation_id == tid]
        satisfied, violated, inhibitors, missing = [], [], [], []
        favoring_hit = False
        evidence = []
        for r in my_rules:
            res = r.evaluate(facts)
            label = f"{r.rule_id}: {r.statement_pt}"
            if r.kind in {"necessary", "critical"}:
                if res is True:
                    satisfied.append(label)
                elif res is False:
                    (violated if r.kind == "necessary" else missing).append(label)
                else:
                    missing.append(label)
            elif r.kind == "favoring" and res is True:
                favoring_hit = True
                satisfied.append(label)
            elif r.kind == "inhibiting" and res is True:
                inhibitors.append(label)
            if res is True or r.kind in {"necessary", "critical"}:
                evidence.append(new_claim(
                    claim_id=f"rule:{r.rule_id}", subject_id=tid, predicate=f"{r.kind}_condition",
                    value=r.statement_pt, unit=None, evidence_type=r.evidence_type,
                    confidence="moderate" if r.evidence_type == "documented_physical_rule" else "low",
                    source_id=r.source_id, method="regra curada (transformation_rules.csv)",
                    limitations=r.limitations or tr.limitations))
        in_technique = tid in technique.effects
        if tid in observed:
            status = "observed"
            evidence = [observed[tid]] + evidence
        elif not in_technique or violated:
            status = "unsupported"
        elif missing or inhibitors or not favoring_hit:
            status = "possible"
        else:
            status = "likely"
        limitations = [tr.limitations]
        if not in_technique:
            limitations.append(f"técnica {technique_id} não tem {tid} como efeito documentado")
        if missing:
            limitations.append("dados ausentes rebaixam a conclusão; nenhum valor foi presumido")
        out.append(TransformationAssessment(
            tid, tr.name_pt, status, technique_id, conditions.provided(), missing, satisfied, violated, inhibitors,
            tr.sensory_effects, evidence, sorted(set(tr.sources) | {r.source_id for r in my_rules}),
            limitations, QUANTIFICATION_NEEDS.get(tid, [])))
    return out


def by_id(assessments: Iterable[TransformationAssessment]) -> dict[str, TransformationAssessment]:
    return {a.transformation_id: a for a in assessments}
