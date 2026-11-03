"""Textura: atributos com estado de conhecimento (observado, esperado, desconhecido).

* ``observed`` só vem de claim de observação humana ou medição (por exemplo, o
  ``texture_attributes`` de um ``IngredientState``, demanda 005);
* ``expected`` vem de regra técnica → textura (``data/knowledge/texture_rules.csv``),
  sempre como expectativa com fonte ou heurística declarada;
* ``unknown`` é o padrão.

Técnicas produzem expectativas, nunca observações automáticas.
"""

from __future__ import annotations

import csv
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .evidence import EvidenceClaim
from .states import IngredientState

ROOT = Path(__file__).resolve().parents[1]
TEXTURE_RULES_CSV = ROOT / "data" / "knowledge" / "texture_rules.csv"

TEXTURE_TERMS = ("macio", "crocante", "cremoso", "suculento", "fibroso", "firme", "granuloso", "viscoso")
TEXTURE_STATUS = ("observed", "expected", "unknown")
# formas flexionadas que aparecem em relatos ("suculenta", "macia") -> termo do vocabulário
_INFLECTIONS = {"macia": "macio", "crocantes": "crocante", "cremosa": "cremoso", "suculenta": "suculento",
                "fibrosa": "fibroso", "granulosa": "granuloso", "viscosa": "viscoso", "tenra": "macio",
                "tenro": "macio"}


def normalize_term(term: str) -> str | None:
    t = unicodedata.normalize("NFKD", str(term)).encode("ascii", "ignore").decode().lower().strip()
    t = _INFLECTIONS.get(t, t)
    ascii_terms = {unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode(): x for x in TEXTURE_TERMS}
    return ascii_terms.get(t)


@dataclass(frozen=True)
class TextureAttribute:
    term: str
    status: str
    subject_id: str
    method: str
    source_id: str | None
    confidence: str
    claim_id: str | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TextureRule:
    rule_id: str
    technique_id: str
    applicable_groups: str
    term: str
    statement_pt: str
    source_id: str
    evidence_type: str
    limitations: str


def load_texture_rules(path: Path | str = TEXTURE_RULES_CSV) -> list[TextureRule]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [TextureRule(**{k: (v or "").strip() for k, v in r.items()}) for r in csv.DictReader(fh)]


def observed_textures(state: IngredientState, claims: Iterable[EvidenceClaim] = ()) -> list[TextureAttribute]:
    """Texturas observadas: só as que vieram de claims de observação/medição."""
    by_id = {c.claim_id: c for c in claims}
    out = []
    ids = state.knowledge.get("texture_attributes").claim_ids if "texture_attributes" in state.knowledge else ()
    for cid in ids:
        c = by_id.get(cid)
        if c is None or c.evidence_type not in {"human_observation", "experimental_measurement"}:
            continue
        term = normalize_term(c.value)
        out.append(TextureAttribute(term or str(c.value), "observed", state.instance_id, c.method or "",
                                    c.source_id, c.confidence, cid,
                                    "" if term else "termo fora do vocabulário inicial; mantido como relatado"))
    return out


def expected_textures(technique_id: str, subject_id: str, food_group: str | None = None,
                      rules: list[TextureRule] | None = None) -> list[TextureAttribute]:
    """Expectativas por técnica (nunca observação)."""
    rules = rules if rules is not None else load_texture_rules()
    out = []
    for r in rules:
        if r.technique_id != technique_id:
            continue
        groups = {g for g in r.applicable_groups.split("|") if g}
        if groups and food_group not in groups:
            continue
        out.append(TextureAttribute(r.term, "expected", subject_id, f"regra {r.rule_id}: {r.statement_pt}",
                                    r.source_id, "low" if r.evidence_type == "culinary_heuristic" else "moderate",
                                    None, r.limitations))
    return out


def texture_profile(observed: Iterable[TextureAttribute], expected: Iterable[TextureAttribute]) -> dict[str, list[dict]]:
    """Perfil por termo: observado prevalece sobre esperado; nada vira observado por inferência."""
    profile: dict[str, list[dict]] = {t: [] for t in TEXTURE_TERMS}
    for a in list(observed) + list(expected):
        profile.setdefault(a.term, []).append(a.to_dict())
    return profile


def status_of(term: str, profile: dict[str, list[dict]]) -> str:
    entries = profile.get(term, [])
    if any(e["status"] == "observed" for e in entries):
        return "observed"
    if any(e["status"] == "expected" for e in entries):
        return "expected"
    return "unknown"
