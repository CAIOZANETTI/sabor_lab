"""Combina preferência observada com a checagem independente de segurança."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .food_safety import SafetyAssessment
from .temporal_sensory import SensoryAnalysis


@dataclass
class ServingRecommendation:
    status: str
    preferred_temperature_c: float | None
    target_source: str | None
    reason: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def recommend_serving_temperature(
    sensory: SensoryAnalysis, safety: SafetyAssessment,
) -> ServingRecommendation:
    """Só expõe uma estimativa sensorial quando dados e segurança permitem."""
    if not safety.allows_serving_optimization:
        return ServingRecommendation(
            "blocked_by_safety", None, None,
            "checagem de segurança precisa ser resolvida antes da recomendação sensorial",
            safety.reasons,
        )
    if sensory.preferred_temperature_c is None:
        return ServingRecommendation(
            "insufficient_data", None, None, sensory.reason, sensory.warnings,
        )
    return ServingRecommendation(
        "exploratory_preference", sensory.preferred_temperature_c, "measured_preference",
        "estimativa exploratória dentro da faixa observada sob estas condições",
        sensory.warnings + ["não tratar como temperatura perfeita ou universal"],
    )
