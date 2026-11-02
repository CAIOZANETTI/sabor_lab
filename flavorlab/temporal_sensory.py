"""Registro e análise exploratória de degustações ligadas à temperatura."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Iterable, Mapping

import numpy as np


SENSORY_FIELDS = (
    "overall_score", "aroma_score", "saltiness_score", "acidity_score",
    "umami_score", "smokiness_score", "juiciness_score", "texture_score",
)


@dataclass(frozen=True)
class Tasting:
    taster_id: str
    elapsed_min: float
    temperature_c: float
    overall_score: float | None = None
    aroma_score: float | None = None
    saltiness_score: float | None = None
    acidity_score: float | None = None
    umami_score: float | None = None
    smokiness_score: float | None = None
    juiciness_score: float | None = None
    texture_score: float | None = None
    presentation_order: int | None = None
    sample_condition: str = ""
    composition: str = ""
    holding_method: str = ""
    notes: str = ""


@dataclass
class SensoryAnalysis:
    status: str
    n_observations: int
    n_unique_temperatures: int
    observed_range_c: tuple[float, float] | None
    preferred_temperature_c: float | None
    coefficients: tuple[float, float, float] | None
    rmse: float | None
    r_squared: float | None
    reason: str
    temperature_bands: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def parse_tastings(records: Iterable[Mapping]) -> list[Tasting]:
    parsed = []
    for row in records:
        values = {name: row.get(name) for name in SENSORY_FIELDS}
        for name, value in values.items():
            if value is not None and not 0 <= float(value) <= 10:
                raise ValueError(f"{name} deve estar entre 0 e 10")
        parsed.append(Tasting(
            taster_id=str(row.get("taster_id") or ""),
            elapsed_min=float(row["elapsed_min"]), temperature_c=float(row["temperature_c"]),
            presentation_order=(int(row["presentation_order"]) if row.get("presentation_order") is not None else None),
            sample_condition=str(row.get("sample_condition") or ""),
            composition=str(row.get("composition") or ""),
            holding_method=str(row.get("holding_method") or ""),
            notes=str(row.get("notes") or ""),
            **{name: (float(value) if value is not None else None) for name, value in values.items()},
        ))
    return parsed


def _bands(tastings: list[Tasting], width_c: float = 5.0) -> list[dict]:
    groups: dict[float, list[float]] = {}
    for tasting in tastings:
        if tasting.overall_score is None:
            continue
        lower = math.floor(tasting.temperature_c / width_c) * width_c
        groups.setdefault(lower, []).append(tasting.overall_score)
    return [{
        "from_c": lower, "to_c": lower + width_c,
        "n": len(scores), "mean_overall": float(np.mean(scores)),
        "standard_deviation": float(np.std(scores, ddof=1)) if len(scores) > 1 else None,
    } for lower, scores in sorted(groups.items())]


def analyze_preference(
    records: Iterable[Tasting | Mapping], *, min_observations: int = 6,
    min_unique_temperatures: int = 4, min_temperature_span_c: float = 5.0,
) -> SensoryAnalysis:
    tastings = [r if isinstance(r, Tasting) else parse_tastings([r])[0] for r in records]
    scored = [r for r in tastings if r.overall_score is not None]
    bands = _bands(scored)
    if not scored:
        return SensoryAnalysis("insufficient_data", 0, 0, None, None, None, None, None,
                               "nenhuma nota geral registrada", bands)
    x = np.array([r.temperature_c for r in scored], dtype=float)
    y = np.array([r.overall_score for r in scored], dtype=float)
    observed = (float(x.min()), float(x.max()))
    unique = len(np.unique(x))
    if len(scored) < min_observations or unique < min_unique_temperatures or np.ptp(x) < min_temperature_span_c:
        return SensoryAnalysis(
            "insufficient_data", len(scored), unique, observed, None, None, None, None,
            "amostra, temperaturas únicas ou amplitude insuficientes para estimar preferência", bands,
            ["uma observação individual não identifica efeito causal nem ótimo reproduzível"],
        )
    beta2, beta1, beta0 = (float(v) for v in np.polyfit(x, y, 2))
    predicted = beta0 + beta1 * x + beta2 * x**2
    residuals = y - predicted
    rmse = float(math.sqrt(float(np.mean(residuals**2))))
    total = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - float(np.sum(residuals**2)) / total if total > 0 else None
    coefficients = (beta0, beta1, beta2)
    if beta2 >= 0:
        return SensoryAnalysis("inadequate_model", len(scored), unique, observed, None,
                               coefficients, rmse, r2, "parábola não é côncava", bands)
    vertex = -beta1 / (2 * beta2)
    if not observed[0] <= vertex <= observed[1]:
        return SensoryAnalysis("inadequate_model", len(scored), unique, observed, None,
                               coefficients, rmse, r2, "vértice fora da faixa observada", bands)
    return SensoryAnalysis(
        "exploratory_fit", len(scored), unique, observed, float(vertex), coefficients,
        rmse, r2, "estimativa exploratória dentro da faixa observada", bands,
        ["temperatura e tempo podem estar correlacionados; o ajuste não demonstra causalidade"],
    )
