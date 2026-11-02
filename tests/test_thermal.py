import math

import pytest

from flavorlab.thermal import ThermalModelError, fit_cooling, predict_target_time


def test_two_point_fit_recovers_expected_k_and_observations():
    fit = fit_cooling([(0, 80.0), (5, 72.0)], ambient_c=23.0)
    expected = -math.log((72 - 23) / (80 - 23)) / 5
    assert fit.k_per_min == pytest.approx(expected)
    assert fit.temperature_at(0) == pytest.approx(80.0)
    assert fit.temperature_at(5) == pytest.approx(72.0)
    assert fit.rmse_c == pytest.approx(0.0, abs=1e-12)
    assert fit.method == "two_point"


def test_multi_reading_regression_and_target_prediction():
    ambient, initial, k = 22.0, 82.0, 0.04
    readings = [(t, ambient + (initial - ambient) * math.exp(-k * t)) for t in (0, 4, 8, 12)]
    fit = fit_cooling(readings, ambient)
    prediction = predict_target_time(fit, 60.0, target_source="exploratory")
    assert fit.k_per_min == pytest.approx(k)
    assert fit.t0_estimated_c == pytest.approx(initial)
    assert fit.adequate
    assert prediction.total_elapsed_min > 0
    assert prediction.target_source == "exploratory"


@pytest.mark.parametrize("readings,ambient", [
    ([(0, 80)], 23),
    ([(0, 23.01), (5, 23.0)], 23),
    ([(0, 80), (5, 82)], 23),
    ([(0, 80), (5, 80)], 23),
    ([(0, 80), (0, 72)], 23),
    ([(1, 80), (5, 72)], 23),
])
def test_invalid_or_unidentifiable_readings_are_rejected(readings, ambient):
    kwargs = {"sensor_resolution_c": 0.1} if readings[0][1] < 24 else {}
    with pytest.raises(ThermalModelError):
        fit_cooling(readings, ambient, **kwargs)


def test_target_must_be_between_ambient_and_initial():
    fit = fit_cooling([(0, 80), (5, 72)], 23)
    with pytest.raises(ThermalModelError):
        predict_target_time(fit, 20)
    with pytest.raises(ThermalModelError):
        predict_target_time(fit, 85)


def test_sensor_metadata_is_preserved():
    fit = fit_cooling([(0, 80), (5, 72)], 23, sensor_resolution_c=0.2,
                      probe_position="centro_da_massa")
    assert fit.sensor_resolution_c == 0.2
    assert fit.probe_position == "centro_da_massa"
    assert fit.to_dict()["units"]["k"] == "min^-1"


def test_large_residuals_reject_model_for_prediction():
    fit = fit_cooling([(0, 80), (1, 79), (2, 60), (3, 59)], 23)
    assert not fit.adequate
    assert any("resíduos incompatíveis" in warning for warning in fit.warnings)
    with pytest.raises(ThermalModelError):
        predict_target_time(fit, 50)
