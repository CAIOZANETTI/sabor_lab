import pytest

from flavorlab.temporal_sensory import analyze_preference, parse_tastings


def _records(temperatures, score):
    return [{"taster_id": f"t{i}", "elapsed_min": i, "temperature_c": t,
             "overall_score": score(t)} for i, t in enumerate(temperatures)]


def test_one_observation_never_returns_preference():
    result = analyze_preference(_records([60], lambda _: 8))
    assert result.status == "insufficient_data"
    assert result.preferred_temperature_c is None


def test_concave_quadratic_inside_observed_range_is_exploratory():
    result = analyze_preference(_records([50, 55, 60, 65, 50, 55, 60, 65],
                                         lambda t: 9 - 0.02 * (t - 60) ** 2))
    assert result.status == "exploratory_fit"
    assert result.preferred_temperature_c == pytest.approx(60)
    assert result.observed_range_c == (50.0, 65.0)


def test_convex_parabola_does_not_return_preference():
    result = analyze_preference(_records([45, 50, 55, 60, 65, 70],
                                         lambda t: 2 + 0.002 * (t - 58) ** 2))
    assert result.status == "inadequate_model"
    assert result.preferred_temperature_c is None
    assert result.reason == "parábola não é côncava"


def test_vertex_outside_observed_range_does_not_return_preference():
    result = analyze_preference(_records([40, 45, 50, 55, 60, 65],
                                         lambda t: 8 - 0.002 * (t - 80) ** 2))
    assert result.status == "inadequate_model"
    assert result.preferred_temperature_c is None
    assert result.reason == "vértice fora da faixa observada"


def test_scores_must_use_predefined_zero_to_ten_scale():
    with pytest.raises(ValueError):
        parse_tastings([{"taster_id": "x", "elapsed_min": 1,
                         "temperature_c": 60, "overall_score": 11}])


def test_temperature_and_elapsed_are_kept_as_separate_fields():
    tasting = parse_tastings([{"taster_id": "x", "elapsed_min": 20,
                               "temperature_c": 61, "overall_score": 7}])[0]
    assert tasting.elapsed_min == 20
    assert tasting.temperature_c == 61
