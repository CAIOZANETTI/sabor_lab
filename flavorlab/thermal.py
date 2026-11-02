"""Modelo térmico empírico para resfriamento de preparações.

O coeficiente calculado descreve somente o lote, recipiente e condições
observados. Ele não é propriedade universal da receita ou do alimento.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Iterable, Mapping, Sequence

import numpy as np


class ThermalModelError(ValueError):
    """Leituras incompatíveis com o modelo concentrado de resfriamento."""


@dataclass(frozen=True)
class TemperatureReading:
    elapsed_min: float
    temperature_c: float


@dataclass
class CoolingFit:
    ambient_c: float
    k_per_min: float
    t0_measured_c: float
    t0_estimated_c: float
    readings: list[TemperatureReading]
    predicted_c: list[float]
    residuals_c: list[float]
    rmse_c: float
    r_squared: float | None
    method: str
    adequate: bool
    k_standard_error: float | None = None
    sensor_resolution_c: float | None = None
    probe_position: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def observed_window_min(self) -> float:
        return self.readings[-1].elapsed_min - self.readings[0].elapsed_min

    def temperature_at(self, elapsed_min: float) -> float:
        if elapsed_min < 0:
            raise ThermalModelError("tempo não pode ser negativo")
        return self.ambient_c + (self.t0_estimated_c - self.ambient_c) * math.exp(
            -self.k_per_min * elapsed_min
        )

    def to_dict(self) -> dict:
        result = asdict(self)
        result["readings"] = [asdict(r) for r in self.readings]
        result["observed_window_min"] = self.observed_window_min
        result["units"] = {"temperature": "°C", "time": "min", "k": "min^-1"}
        return result


@dataclass
class TargetPrediction:
    target_c: float
    target_source: str
    total_elapsed_min: float
    remaining_min: float
    interval_95_total_min: tuple[float, float] | None
    extrapolated: bool
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _reading(value: TemperatureReading | Sequence[float] | Mapping[str, float]) -> TemperatureReading:
    if isinstance(value, TemperatureReading):
        return value
    if isinstance(value, Mapping):
        return TemperatureReading(float(value["elapsed_min"]), float(value["temperature_c"]))
    if len(value) != 2:
        raise ThermalModelError("cada leitura deve conter tempo e temperatura")
    return TemperatureReading(float(value[0]), float(value[1]))


def fit_cooling(
    readings: Iterable[TemperatureReading | Sequence[float] | Mapping[str, float]],
    ambient_c: float,
    *,
    sensor_resolution_c: float | None = None,
    probe_position: str | None = None,
) -> CoolingFit:
    """Ajusta ``T(t)=Ta+(T0-Ta) exp(-kt)`` a duas ou mais leituras.

    O MVP cobre apenas resfriamento monotônico sob temperatura ambiente fixa.
    Crescimento, platôs e temperaturas próximas/abaixo do ambiente são
    rejeitados em vez de receber um ajuste sem significado.
    """

    points = sorted((_reading(r) for r in readings), key=lambda r: r.elapsed_min)
    if len(points) < 2:
        raise ThermalModelError("são necessárias ao menos duas leituras para estimar k")
    values = np.array([(r.elapsed_min, r.temperature_c) for r in points], dtype=float)
    if not np.isfinite(values).all() or not math.isfinite(float(ambient_c)):
        raise ThermalModelError("tempos e temperaturas precisam ser números finitos")
    times, temps = values[:, 0], values[:, 1]
    if abs(times[0]) > 1e-9:
        raise ThermalModelError("a primeira leitura deve usar elapsed_min=0")
    if np.any(times < 0) or np.any(np.diff(times) <= 0):
        raise ThermalModelError("tempos precisam ser únicos e estritamente crescentes")
    resolution = float(sensor_resolution_c) if sensor_resolution_c is not None else None
    if resolution is not None and (not math.isfinite(resolution) or resolution <= 0):
        raise ThermalModelError("resolução do sensor precisa ser positiva")
    tolerance = max(1e-9, (resolution or 0.0) / 2)
    if np.any(temps - float(ambient_c) <= tolerance):
        raise ThermalModelError("todas as leituras devem estar acima do ambiente com margem mensurável")
    if np.any(np.diff(temps) >= -tolerance):
        raise ThermalModelError("leituras não representam resfriamento estritamente decrescente")

    y = np.log(temps - float(ambient_c))
    warnings: list[str] = []
    k_se = None
    if len(points) == 2:
        intercept = float(y[0])
        k = -float((y[1] - y[0]) / times[1])
        method = "two_point"
    else:
        design = np.column_stack([np.ones(len(times)), times])
        intercept, slope = np.linalg.lstsq(design, y, rcond=None)[0]
        intercept, k = float(intercept), -float(slope)
        method = "log_linear_regression"
        y_residuals = y - design @ np.array([intercept, -k])
        if len(points) > 2:
            variance = float(np.sum(y_residuals**2) / (len(points) - 2))
            centered = float(np.sum((times - times.mean()) ** 2))
            if centered > 0:
                k_se = math.sqrt(variance / centered)
    if not math.isfinite(k) or k <= 0:
        raise ThermalModelError("o ajuste não produziu k positivo")

    t0_estimated = float(ambient_c + math.exp(intercept))
    predicted = ambient_c + (t0_estimated - ambient_c) * np.exp(-k * times)
    residuals = temps - predicted
    rmse = float(math.sqrt(float(np.mean(residuals**2))))
    total_variance = float(np.sum((temps - temps.mean()) ** 2))
    r_squared = 1 - float(np.sum(residuals**2)) / total_variance if total_variance > 0 else None
    allowed_rmse = max(2 * (resolution or 0.5), 0.05 * float(temps.max() - temps.min()))
    adequate = rmse <= allowed_rmse
    if not adequate:
        warnings.append(
            "resíduos incompatíveis com o modelo concentrado; não usar para recomendação"
        )
    if abs(t0_estimated - temps[0]) > allowed_rmse:
        warnings.append("T0 estimado difere da primeira leitura além da tolerância do ajuste")

    return CoolingFit(
        ambient_c=float(ambient_c), k_per_min=k, t0_measured_c=float(temps[0]),
        t0_estimated_c=t0_estimated, readings=points,
        predicted_c=[float(v) for v in predicted], residuals_c=[float(v) for v in residuals],
        rmse_c=rmse, r_squared=r_squared, method=method, adequate=adequate,
        k_standard_error=k_se, sensor_resolution_c=resolution,
        probe_position=probe_position, warnings=warnings,
    )


def predict_target_time(
    fit: CoolingFit,
    target_c: float,
    *,
    target_source: str = "manual",
    current_elapsed_min: float | None = None,
    extrapolation_factor: float = 2.0,
) -> TargetPrediction:
    """Calcula o tempo total e restante para uma meta válida de resfriamento."""

    target = float(target_c)
    if not fit.ambient_c < target < fit.t0_estimated_c:
        raise ThermalModelError("meta deve estar estritamente entre ambiente e T0")
    if not fit.adequate:
        raise ThermalModelError("ajuste inadequado não pode sustentar previsão")
    total = math.log((fit.t0_estimated_c - fit.ambient_c) / (target - fit.ambient_c)) / fit.k_per_min
    current = fit.readings[-1].elapsed_min if current_elapsed_min is None else float(current_elapsed_min)
    if current < 0:
        raise ThermalModelError("tempo atual não pode ser negativo")
    warnings: list[str] = []
    extrapolated = total > fit.readings[-1].elapsed_min
    if fit.observed_window_min > 0 and total > extrapolation_factor * fit.observed_window_min:
        warnings.append("previsão extrapola muito além da janela observada")
    interval = None
    if fit.k_standard_error is not None and fit.k_standard_error > 0:
        low_k = fit.k_per_min - 1.96 * fit.k_standard_error
        high_k = fit.k_per_min + 1.96 * fit.k_standard_error
        numerator = math.log((fit.t0_estimated_c - fit.ambient_c) / (target - fit.ambient_c))
        if low_k > 0:
            interval = (numerator / high_k, numerator / low_k)
            warnings.append("intervalo de 95% aproximado pelo erro do coeficiente k")
    return TargetPrediction(
        target_c=target, target_source=target_source, total_elapsed_min=total,
        remaining_min=max(0.0, total - current), interval_95_total_min=interval,
        extrapolated=extrapolated, warnings=warnings,
    )
