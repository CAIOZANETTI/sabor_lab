import json
import subprocess
import sys

import pytest

from flavorlab.food_safety import check_food_safety
from flavorlab.serving_optimizer import recommend_serving_temperature
from flavorlab.temporal_sensory import analyze_preference

from conftest import ROOT


def _preference():
    temperatures = [50, 55, 60, 65, 50, 55, 60, 65]
    return analyze_preference([
        {"taster_id": str(i), "elapsed_min": i, "temperature_c": t,
         "overall_score": 9 - .02 * (t - 60) ** 2}
        for i, t in enumerate(temperatures)
    ])


def test_sensory_target_cannot_override_safety():
    unsafe = check_food_safety(food_temperature_c=55, elapsed_out_of_control_min=130,
                               ambient_c=25, perishable=True, service_mode="immediate_service")
    result = recommend_serving_temperature(_preference(), unsafe)
    assert result.status == "blocked_by_safety"
    assert result.preferred_temperature_c is None


def test_supported_fit_returns_exploratory_not_perfect_temperature():
    context = check_food_safety(food_temperature_c=60, elapsed_out_of_control_min=20,
                                ambient_c=25, perishable=True, service_mode="immediate_service")
    result = recommend_serving_temperature(_preference(), context)
    assert result.status == "exploratory_preference"
    assert result.preferred_temperature_c == pytest.approx(60)
    assert result.target_source == "measured_preference"


def test_entrevero_cli_generates_machine_result_and_html(tmp_path):
    source = ROOT / "data" / "experiments" / "entrevero_temperatura_sintetico.json"
    report, result_path = tmp_path / "report.html", tmp_path / "result.json"
    completed = subprocess.run([
        sys.executable, str(ROOT / "scripts" / "temperature_report.py"),
        "--input", str(source), "--output", str(report), "--result-json", str(result_path),
    ], cwd=ROOT, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["data_status"] == "synthetic_example"
    assert [c["component"] for c in result["components"]] == ["entrevero", "cabotiá_farofa"]
    assert result["components"][0]["thermal_fit"]["k_per_min"] == pytest.approx(
        -__import__("math").log((72 - 23) / (80 - 23)) / 5
    )
    assert result["components"][0]["sensory"]["preferred_temperature_c"] is None
    assert result["components"][0]["conditions"]["sensor"]["resolution_c"] == 0.1
    assert result["components"][0]["target"]["validated_for_recipe"] is False
    doc = report.read_text(encoding="utf-8")
    assert "EXEMPLO SINTÉTICO" in doc and "leitura medida" in doc and "modelo calculado" in doc
