"""Camada de evidências: afirmações (claims) rastreáveis e registro único de fontes.

Toda afirmação do sistema — um valor medido, um dado de tabela, uma observação
de quem cozinha, uma heurística culinária ou uma hipótese — vira um
``EvidenceClaim`` com tipo de evidência, confiança qualitativa, fonte ou
método e limitações. Os módulos posteriores (preparo, física, nutrição pós-preparo,
compositor, storytelling) consomem estes contratos; não criam outro formato de
confiança, fonte ou desconhecido.

Confiança (qualidade da evidência, **não** precisão numérica):

``high``
    medição direta ou tabela oficial aplicável ao mesmo sujeito e contexto.
``moderate``
    fonte confiável, mas com transferência de contexto (outra cultivar, outro
    lote, outro equipamento) ou cálculo derivado de dados de alta confiança.
``low``
    associação indireta, analogia ou fonte fraca; útil só como indício.
``qualitative``
    afirmação sem escala numérica calibrada (observação sensorial, relato).
``unknown``
    qualidade não avaliada.

A precisão numérica vai em ``uncertainty`` (mesma unidade de ``value``) ou em
``value_min``/``value_max``. Nenhum percentual de confiança é criado sem calibração.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
SOURCES_CSV = ROOT / "data" / "knowledge" / "sources.csv"

EVIDENCE_TYPES = (
    "experimental_measurement",
    "official_food_table",
    "recipe_association",
    "molecular_presence",
    "documented_physical_rule",
    "derived_calculation",
    "culinary_heuristic",
    "human_observation",
    "user_preference",
    "unvalidated_hypothesis",
)
CONFIDENCE_LEVELS = ("high", "moderate", "low", "qualitative", "unknown")

# Tipos que exigem fonte registrada (um método sozinho não basta).
REQUIRES_SOURCE = {"official_food_table", "documented_physical_rule", "molecular_presence", "recipe_association"}
# Tipos que exigem método descrito (quem/como mediu, observou ou calculou).
REQUIRES_METHOD = {"experimental_measurement", "derived_calculation", "human_observation", "user_preference"}
# Tipos que não podem declarar confiança alta: não são observação/medição do próprio sujeito.
CAPPED_CONFIDENCE = {"culinary_heuristic": {"moderate", "low", "qualitative", "unknown"},
                     "unvalidated_hypothesis": {"low", "unknown"},
                     "user_preference": {"qualitative", "unknown"},
                     "human_observation": {"moderate", "low", "qualitative", "unknown"}}

# Ordem documentada para ``best_available``: medição > tabela oficial > regra física
# documentada > cálculo derivado > observação humana > associação/presença molecular >
# heurística > preferência > hipótese. Empates: confiança, data mais recente, claim_id.
TYPE_PRIORITY = {
    "experimental_measurement": 0, "official_food_table": 1, "documented_physical_rule": 2,
    "derived_calculation": 3, "human_observation": 4, "recipe_association": 5,
    "molecular_presence": 6, "culinary_heuristic": 7, "user_preference": 8,
    "unvalidated_hypothesis": 9,
}
CONFIDENCE_PRIORITY = {c: i for i, c in enumerate(CONFIDENCE_LEVELS)}
SELECTION_RULE = ("prioridade por tipo de evidência (medição > tabela oficial > regra física > cálculo > "
                  "observação > associação > heurística > preferência > hipótese), depois confiança, "
                  "depois observação mais recente e, por fim, claim_id; valores divergentes são preservados")


class EvidenceError(ValueError):
    """Claim ou fonte inválida."""


# --------------------------------------------------------------------------- fontes
@dataclass(frozen=True)
class Source:
    source_id: str
    title: str
    author_org: str
    source_type: str
    url: str = ""
    doi: str = ""
    license: str = ""
    version: str = ""
    accessed_at: str = ""
    scope: str = ""
    verification_status: str = "unverified"   # verified | unverified
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


SOURCE_TYPES = {"official_regulation", "official_guidance", "official_food_table", "scientific_database",
                "peer_reviewed", "textbook", "dataset", "internal", "other"}


class SourceRegistry:
    """Registro único de fontes (``data/knowledge/sources.csv``). Claims referenciam ``source_id``."""

    def __init__(self, sources: Iterable[Source] = ()):
        self._sources: dict[str, Source] = {}
        for s in sources:
            self.add(s)

    @classmethod
    def load(cls, path: Path | str = SOURCES_CSV) -> "SourceRegistry":
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        names = {f.name for f in fields(Source)}
        return cls(Source(**{k: (v or "").strip() for k, v in row.items() if k in names}) for row in rows)

    def add(self, source: Source) -> None:
        errors = validate_source(source)
        if errors:
            raise EvidenceError("; ".join(errors))
        if source.source_id in self._sources:
            raise EvidenceError(f"fonte duplicada: {source.source_id}")
        self._sources[source.source_id] = source

    def get(self, source_id: str) -> Source:
        try:
            return self._sources[source_id]
        except KeyError:
            raise EvidenceError(f"fonte não registrada: {source_id}") from None

    def __contains__(self, source_id: str) -> bool:
        return source_id in self._sources

    def __iter__(self):
        return iter(self._sources.values())

    def __len__(self) -> int:
        return len(self._sources)


def validate_source(s: Source) -> list[str]:
    errors = []
    tag = s.source_id or "<sem id>"
    if not s.source_id or not s.source_id.replace("_", "").isalnum() or s.source_id != s.source_id.lower():
        errors.append(f"{tag}: source_id deve ser minúsculo, alfanumérico com '_'")
    if not s.title or not s.author_org:
        errors.append(f"{tag}: título e autor/organização são obrigatórios")
    if s.source_type not in SOURCE_TYPES:
        errors.append(f"{tag}: source_type inválido {s.source_type!r}")
    if s.verification_status not in {"verified", "unverified"}:
        errors.append(f"{tag}: verification_status deve ser verified|unverified")
    # URL/DOI só com verificação registrada: nada de link inventado
    if (s.url or s.doi) and (s.verification_status != "verified" or not s.accessed_at):
        errors.append(f"{tag}: URL/DOI exige verification_status=verified e accessed_at")
    if s.url and not s.url.startswith(("https://", "http://")):
        errors.append(f"{tag}: URL inválida")
    return errors


# --------------------------------------------------------------------------- claims
@dataclass(frozen=True)
class EvidenceClaim:
    claim_id: str
    subject_id: str
    predicate: str
    value: Any
    unit: str | None
    evidence_type: str
    confidence: str
    source_id: str | None
    method: str | None
    limitations: str | None
    observed_at: str | None
    uncertainty: float | None = None      # precisão numérica, na unidade de ``value``
    value_min: float | None = None
    value_max: float | None = None
    context: str | None = None            # condições em que o valor vale (lote, equipamento...)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EvidenceClaim":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})

    @property
    def is_numeric(self) -> bool:
        return isinstance(self.value, (int, float)) and not isinstance(self.value, bool)


def validate_claim(c: EvidenceClaim, sources: SourceRegistry | None = None) -> list[str]:
    errors = []
    tag = c.claim_id or "<sem id>"
    if not c.claim_id or not c.subject_id or not c.predicate:
        errors.append(f"{tag}: claim_id, subject_id e predicate são obrigatórios")
    if c.evidence_type not in EVIDENCE_TYPES:
        errors.append(f"{tag}: evidence_type inválido {c.evidence_type!r}")
    if c.confidence not in CONFIDENCE_LEVELS:
        errors.append(f"{tag}: confidence inválida {c.confidence!r} (use {', '.join(CONFIDENCE_LEVELS)})")
    allowed = CAPPED_CONFIDENCE.get(c.evidence_type)
    if allowed is not None and c.confidence not in allowed:
        errors.append(f"{tag}: {c.evidence_type} não pode ter confiança {c.confidence!r}")
    if c.is_numeric and not c.unit:
        errors.append(f"{tag}: valor numérico exige unidade")
    if c.evidence_type in REQUIRES_SOURCE and not c.source_id:
        errors.append(f"{tag}: {c.evidence_type} exige source_id registrado")
    if c.evidence_type in REQUIRES_METHOD and not (c.method or c.source_id):
        errors.append(f"{tag}: {c.evidence_type} exige método (ou fonte)")
    if c.evidence_type == "experimental_measurement" and not c.is_numeric and c.value is not None:
        errors.append(f"{tag}: medição experimental deve ter valor numérico")
    if c.evidence_type in {"culinary_heuristic", "unvalidated_hypothesis"} and not c.limitations:
        errors.append(f"{tag}: {c.evidence_type} exige limitações declaradas")
    if c.uncertainty is not None and (not c.is_numeric or c.uncertainty < 0):
        errors.append(f"{tag}: incerteza só para valor numérico e não negativa")
    if (c.value_min is not None or c.value_max is not None) and not c.unit:
        errors.append(f"{tag}: faixa exige unidade")
    if c.value_min is not None and c.value_max is not None and c.value_min > c.value_max:
        errors.append(f"{tag}: value_min > value_max")
    if sources is not None and c.source_id and c.source_id not in sources:
        errors.append(f"{tag}: fonte não registrada {c.source_id!r}")
    return errors


@dataclass
class BestAvailable:
    """Resultado de ``best_available``: o selecionado e tudo o que diverge dele."""
    subject_id: str
    predicate: str
    selected: EvidenceClaim | None
    alternatives: list[EvidenceClaim]
    conflict: bool
    rule: str = SELECTION_RULE

    @property
    def known(self) -> bool:
        return self.selected is not None and self.selected.value is not None


class _Desc:
    """Inverte a ordem de uma string (ISO 8601 mais recente primeiro; sem data por último)."""
    __slots__ = ("v",)

    def __init__(self, v: str):
        self.v = v

    def __lt__(self, other: "_Desc") -> bool:
        return self.v > other.v

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Desc) and self.v == other.v


def _rank(c: EvidenceClaim) -> tuple:
    return (TYPE_PRIORITY[c.evidence_type], CONFIDENCE_PRIORITY[c.confidence], _Desc(c.observed_at or ""),
            c.claim_id)


class EvidenceStore:
    """Coleção de claims com consultas determinísticas. Claims nunca são sobrescritos."""

    def __init__(self, claims: Iterable[EvidenceClaim] = (), sources: SourceRegistry | None = None):
        self.sources = sources
        self._claims: dict[str, EvidenceClaim] = {}
        for c in claims:
            self.add(c)

    def add(self, claim: EvidenceClaim) -> EvidenceClaim:
        errors = validate_claim(claim, self.sources)
        if errors:
            raise EvidenceError("; ".join(errors))
        if claim.claim_id in self._claims:
            if self._claims[claim.claim_id] == claim:
                return claim
            raise EvidenceError(f"claim_id já usado com conteúdo diferente: {claim.claim_id}")
        self._claims[claim.claim_id] = claim
        return claim

    def extend(self, claims: Iterable[EvidenceClaim]) -> None:
        for c in claims:
            self.add(c)

    def __len__(self) -> int:
        return len(self._claims)

    def __iter__(self):
        return iter(sorted(self._claims.values(), key=lambda c: c.claim_id))

    def get(self, claim_id: str) -> EvidenceClaim:
        try:
            return self._claims[claim_id]
        except KeyError:
            raise EvidenceError(f"claim inexistente: {claim_id}") from None

    # ------------------------------------------------------------- consultas
    def for_subject(self, subject_id: str) -> list[EvidenceClaim]:
        return sorted((c for c in self._claims.values() if c.subject_id == subject_id), key=_rank)

    def for_claim(self, predicate: str, value: Any = None) -> list[EvidenceClaim]:
        out = [c for c in self._claims.values() if c.predicate == predicate
               and (value is None or c.value == value)]
        return sorted(out, key=lambda c: (c.subject_id, _rank(c)))

    def explain(self, claim_id: str) -> dict:
        """Claim + fonte resolvida + texto explicando natureza, confiança e limitações."""
        c = self.get(claim_id)
        source = None
        if c.source_id and self.sources is not None and c.source_id in self.sources:
            source = self.sources.get(c.source_id).to_dict()
        value = f"{c.value} {c.unit}" if c.unit else f"{c.value}"
        if c.uncertainty is not None:
            value += f" ± {c.uncertainty} {c.unit}"
        origin = (f"fonte {c.source_id}" if c.source_id else "sem fonte registrada") + \
            (f"; método: {c.method}" if c.method else "")
        text = (f"{c.subject_id} · {c.predicate} = {value} — {c.evidence_type}, confiança {c.confidence}; "
                f"{origin}" + (f"; limitações: {c.limitations}" if c.limitations else ""))
        return {"claim": c.to_dict(), "source": source, "text": text,
                "is_measurement": c.evidence_type == "experimental_measurement"}

    def best_available(self, subject_id: str, predicate: str) -> BestAvailable:
        cands = sorted((c for c in self._claims.values()
                        if c.subject_id == subject_id and c.predicate == predicate), key=_rank)
        if not cands:
            return BestAvailable(subject_id, predicate, None, [], False)
        selected, rest = cands[0], cands[1:]
        conflict = any(_differs(selected, c) for c in rest)
        return BestAvailable(subject_id, predicate, selected, rest, conflict)

    # ------------------------------------------------------------- serialização
    def to_json(self) -> str:
        return json.dumps([c.to_dict() for c in self], ensure_ascii=False, indent=2, sort_keys=True)

    @classmethod
    def from_json(cls, text: str, sources: SourceRegistry | None = None) -> "EvidenceStore":
        return cls((EvidenceClaim.from_dict(d) for d in json.loads(text)), sources)


def _differs(a: EvidenceClaim, b: EvidenceClaim) -> bool:
    """Valores divergentes, considerando a incerteza declarada quando numéricos e na mesma unidade."""
    if a.is_numeric and b.is_numeric and a.unit == b.unit:
        tol = (a.uncertainty or 0.0) + (b.uncertainty or 0.0)
        return abs(float(a.value) - float(b.value)) > tol
    return (a.value, a.unit) != (b.value, b.unit)


def new_claim(**kwargs) -> EvidenceClaim:
    """Atalho com defaults explícitos (todos os campos opcionais ausentes viram ``None``)."""
    base = {f.name: None for f in fields(EvidenceClaim)}
    base.update(kwargs)
    return EvidenceClaim(**base)


__all__ = [
    "BestAvailable", "CONFIDENCE_LEVELS", "EVIDENCE_TYPES", "EvidenceClaim", "EvidenceError",
    "EvidenceStore", "SELECTION_RULE", "Source", "SourceRegistry", "new_claim", "replace",
    "validate_claim", "validate_source",
]
