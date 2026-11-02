#!/usr/bin/env python3
"""Analisa um experimento térmico/sensorial em JSON e gera HTML + JSON.

Uso:
    python scripts/temperature_report.py \
      --input data/experiments/entrevero_temperatura_sintetico.json \
      --output reports/ENTREVERO_001_temperatura.html
"""

from __future__ import annotations

import argparse
import html
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flavorlab.food_safety import check_food_safety  # noqa: E402
from flavorlab.serving_optimizer import recommend_serving_temperature  # noqa: E402
from flavorlab.temporal_sensory import analyze_preference, parse_tastings  # noqa: E402
from flavorlab.thermal import ThermalModelError, fit_cooling, predict_target_time  # noqa: E402


def analyze_experiment(document: dict) -> dict:
    synthetic = document.get("data_status") == "synthetic_example"
    components = []
    for component in document.get("components", []):
        warnings: list[str] = []
        fit = prediction = None
        try:
            fit_obj = fit_cooling(
                component.get("measurements", []), component["ambient_temperature_c"],
                sensor_resolution_c=component.get("sensor", {}).get("resolution_c"),
                probe_position=component.get("probe_position"),
            )
            fit = fit_obj.to_dict()
            warnings.extend(fit_obj.warnings)
            target = component.get("target") or {}
            if target.get("temperature_c") is not None:
                prediction_obj = predict_target_time(
                    fit_obj, target["temperature_c"],
                    target_source=target.get("source", "manual"),
                )
                prediction = prediction_obj.to_dict()
                warnings.extend(prediction_obj.warnings)
        except (ThermalModelError, KeyError, TypeError, ValueError) as exc:
            warnings.append(f"modelo térmico indisponível: {exc}")

        tastings = parse_tastings(component.get("tastings", []))
        sensory_obj = analyze_preference(tastings)
        sensory = sensory_obj.to_dict()
        target_temp = prediction["target_c"] if prediction else (
            component.get("measurements", [{}])[-1].get("temperature_c")
            if component.get("measurements") else None
        )
        target_elapsed = prediction["total_elapsed_min"] if prediction else (
            component.get("measurements", [{}])[-1].get("elapsed_min")
            if component.get("measurements") else None
        )
        out_of_control_start = component.get("out_of_control_start_elapsed_min")
        out_of_control_elapsed = (
            max(0.0, target_elapsed - float(out_of_control_start))
            if target_elapsed is not None and out_of_control_start is not None else None
        )
        safety_obj = check_food_safety(
            food_temperature_c=target_temp,
            elapsed_out_of_control_min=out_of_control_elapsed,
            ambient_c=component.get("ambient_temperature_c"),
            perishable=component.get("perishable"),
            service_mode=component.get("service_mode", "immediate_service"),
        )
        recommendation = recommend_serving_temperature(sensory_obj, safety_obj)
        component_id = component.get("component", "component")
        evidence_ids = [
            f"{document.get('experiment_id', 'experiment')}:{component_id}:temperature:{i}"
            for i, _ in enumerate(component.get("measurements", []))
        ]
        components.append({
            "component": component_id,
            "conditions": {
                "food_mass_g": component.get("food_mass_g"),
                "ambient_temperature_c": component.get("ambient_temperature_c"),
                "container": component.get("container"),
                "covered": component.get("covered"),
                "probe_position": component.get("probe_position"),
                "sensor": component.get("sensor"),
                "out_of_control_start_elapsed_min": out_of_control_start,
            },
            "thermal_fit": fit,
            "target_prediction": prediction,
            "target": component.get("target"),
            "sensory": sensory,
            "safety": safety_obj.to_dict(),
            "serving_recommendation": recommendation.to_dict(),
            "evidence_ids": evidence_ids,
            "warnings": warnings,
        })
    return {
        "experiment_id": document.get("experiment_id"),
        "recipe_id": document.get("recipe_id"),
        "batch_id": document.get("batch_id"),
        "finish_time_local": document.get("finish_time_local"),
        "data_status": "synthetic_example" if synthetic else "recorded_observations",
        "components": components,
        "model_scope": "empirical_for_recorded_batch_and_conditions",
        "generated_without_external_calls": True,
    }


def _fmt(value, digits=2) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}" if isinstance(value, (float, int)) else html.escape(str(value))


def _svg(component: dict, result: dict) -> str:
    readings = component.get("measurements", [])
    fit = result.get("thermal_fit")
    if not readings or not fit:
        return '<p class="empty">Curva indisponível para estas leituras.</p>'
    prediction = result.get("target_prediction")
    max_t = max(float(readings[-1]["elapsed_min"]), float(prediction["total_elapsed_min"]) if prediction else 0, 1)
    max_t *= 1.08
    ambient = float(component["ambient_temperature_c"])
    max_temp = max(float(r["temperature_c"]) for r in readings)
    min_temp = min(ambient, *(float(r["temperature_c"]) for r in readings))
    pad = max(3.0, (max_temp - min_temp) * .12)
    y_min, y_max = min_temp - pad, max_temp + pad
    width, height, left, top, plot_w, plot_h = 760, 310, 58, 22, 670, 235

    def xy(t, temp):
        x = left + float(t) / max_t * plot_w
        y = top + (y_max - float(temp)) / (y_max - y_min) * plot_h
        return x, y

    samples = []
    for i in range(81):
        t = max_t * i / 80
        temp = ambient + (fit["t0_estimated_c"] - ambient) * math.exp(-fit["k_per_min"] * t)
        samples.append(xy(t, temp))
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in samples)
    circles = "".join(
        f'<circle cx="{xy(r["elapsed_min"], r["temperature_c"])[0]:.1f}" '
        f'cy="{xy(r["elapsed_min"], r["temperature_c"])[1]:.1f}" r="5" />'
        for r in readings
    )
    target_line = ""
    if prediction:
        _, target_y = xy(0, prediction["target_c"])
        target_line = (f'<line class="target" x1="{left}" x2="{left + plot_w}" y1="{target_y:.1f}" '
                       f'y2="{target_y:.1f}"/><text x="{left + 5}" y="{target_y - 7:.1f}">'
                       f'meta {prediction["target_c"]:.1f} °C</text>')
    return f'''<svg viewBox="0 0 {width} {height}" role="img" aria-label="Temperatura por minuto">
      <line class="axis" x1="{left}" x2="{left}" y1="{top}" y2="{top + plot_h}"/>
      <line class="axis" x1="{left}" x2="{left + plot_w}" y1="{top + plot_h}" y2="{top + plot_h}"/>
      {target_line}<polyline class="curve" points="{polyline}"/><g class="points">{circles}</g>
      <text x="{left}" y="{height - 16}">0 min</text><text x="{left + plot_w - 54}" y="{height - 16}">{max_t:.1f} min</text>
      <text x="4" y="{top + 8}">{y_max:.0f} °C</text><text x="4" y="{top + plot_h}">{y_min:.0f} °C</text>
      <g class="legend"><circle cx="{left + 160}" cy="{height - 17}" r="4"/><text x="{left + 170}" y="{height - 13}">leitura medida</text>
      <line class="curve" x1="{left + 300}" x2="{left + 340}" y1="{height - 17}" y2="{height - 17}"/><text x="{left + 350}" y="{height - 13}">modelo calculado</text></g>
    </svg>'''


def render_report(document: dict, result: dict) -> str:
    synthetic = result["data_status"] == "synthetic_example"
    blocks = []
    by_name = {c.get("component"): c for c in document.get("components", [])}
    for item in result["components"]:
        source = by_name[item["component"]]
        fit, pred, sensory, safety = item["thermal_fit"], item["target_prediction"], item["sensory"], item["safety"]
        reading_rows = "".join(
            f'<tr><td>{i + 1}</td><td>{_fmt(r.get("elapsed_min"), 1)}</td><td>{_fmt(r.get("temperature_c"), 1)}</td><td>medido</td></tr>'
            for i, r in enumerate(source.get("measurements", []))
        )
        tasting_rows = "".join(
            f'<tr><td>{html.escape(str(t.get("taster_id", "")))}</td><td>{_fmt(t.get("elapsed_min"), 1)}</td><td>{_fmt(t.get("temperature_c"), 1)}</td><td>{_fmt(t.get("overall_score"), 1)}</td><td>{html.escape(str(t.get("notes", "")))}</td></tr>'
            for t in source.get("tastings", [])) or '<tr><td colspan="5">Nenhuma degustação registrada.</td></tr>'
        warning_list = "".join(f"<li>{html.escape(w)}</li>" for w in item["warnings"] + sensory["warnings"] + safety["warnings"])
        blocks.append(f'''<section>
          <span class="eyebrow">Componente</span><h2>{html.escape(item["component"].replace("_", " "))}</h2>
          <div class="cards">
            <article><small>Coeficiente empírico</small><strong>{_fmt(fit and fit["k_per_min"], 4)} min⁻¹</strong><span>{html.escape(fit["method"] if fit else "indisponível")}</span></article>
            <article><small>Meta</small><strong>{_fmt(pred and pred["target_c"], 1)} °C</strong><span>{html.escape(pred["target_source"] if pred else "não calculada")}</span></article>
            <article><small>Tempo total previsto</small><strong>{_fmt(pred and pred["total_elapsed_min"], 1)} min</strong><span>não é tempo recomendado de repouso</span></article>
            <article><small>Preferência sensorial</small><strong>{_fmt(sensory["preferred_temperature_c"], 1)} °C</strong><span>{html.escape(sensory["status"])}</span></article>
          </div>
          <div class="chart">{_svg(source, item)}</div>
          <div class="two"><div><h3>Leituras térmicas</h3><table><thead><tr><th>#</th><th>min</th><th>°C</th><th>tipo</th></tr></thead><tbody>{reading_rows}</tbody></table></div>
          <div><h3>Degustações</h3><table><thead><tr><th>degustador</th><th>min</th><th>°C</th><th>nota</th><th>observação</th></tr></thead><tbody>{tasting_rows}</tbody></table></div></div>
          <div class="status"><div><h3>Segurança: {html.escape(safety["status"])}</h3><p>{html.escape('; '.join(safety["reasons"]))}</p></div>
          <div><h3>Sensorial: {html.escape(sensory["status"])}</h3><p>{html.escape(sensory["reason"])}</p></div></div>
          {f'<ul class="warnings">{warning_list}</ul>' if warning_list else ''}
          <p class="meta">Massa: {_fmt(source.get("food_mass_g"), 0)} g · recipiente: {html.escape(str(source.get("container", "—")))} · sonda: {html.escape(str(source.get("probe_position", "—")))} · RMSE: {_fmt(fit and fit["rmse_c"], 3)} °C</p>
        </section>''')
    banner = ("EXEMPLO SINTÉTICO — nenhum número desta página é observação real." if synthetic
              else "DADOS DECLARADOS COMO OBSERVAÇÕES — conferir calibração, contexto e cadeia de custódia.")
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{html.escape(str(document.get("recipe_id", "Receita")))} — temperatura de serviço</title><style>
    :root{{--ink:#172019;--muted:#657067;--paper:#f5f1e7;--surface:#fffdf8;--accent:#b94b28;--green:#286044;--gold:#d79b31;--line:#d9d2c3}}*{{box-sizing:border-box}}body{{margin:0;color:var(--ink);background:var(--paper);font:16px/1.5 system-ui,sans-serif}}main{{width:min(1100px,calc(100% - 2rem));margin:auto;padding:4rem 0}}h1,h2,h3{{font-family:Georgia,serif}}h1{{font-size:clamp(2.7rem,7vw,5.5rem);line-height:.95;margin:.4rem 0 1rem}}h2{{font-size:2.2rem;margin:.25rem 0 1rem}}section{{margin-top:3rem;padding-top:3rem;border-top:1px solid var(--line)}}.eyebrow{{color:var(--accent);font-weight:800;letter-spacing:.12em;text-transform:uppercase;font-size:.76rem}}.banner{{padding:1rem;border:1px solid #dfa93e;background:#fff4ce;border-radius:14px;font-weight:750}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:.7rem}}.cards article{{display:flex;flex-direction:column;padding:1rem;background:var(--surface);border:1px solid var(--line);border-radius:14px}}.cards strong{{font-size:1.5rem}}.cards small,.cards span,.meta{{color:var(--muted)}}.chart{{margin:1rem 0;background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:1rem}}svg{{width:100%;height:auto}}svg .axis{{stroke:#888}}svg .curve{{fill:none;stroke:var(--green);stroke-width:3}}svg .points circle,.legend circle{{fill:var(--accent)}}svg .target{{stroke:var(--gold);stroke-width:2;stroke-dasharray:7 5}}svg text{{font:13px system-ui;fill:var(--muted)}}.two,.status{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}}table{{width:100%;border-collapse:collapse;background:var(--surface)}}th,td{{padding:.6rem;border-bottom:1px solid var(--line);text-align:left}}.status>div{{margin-top:1rem;padding:1rem;background:#e9e2d2;border-radius:14px}}.warnings{{padding:1rem 1rem 1rem 2rem;background:#fff4ce;border-radius:14px}}@media(max-width:760px){{.cards,.two,.status{{grid-template-columns:1fr}}}}
    </style></head><body><main><span class="eyebrow">SaborLab · temperatura e percepção</span><h1>{html.escape(str(document.get("recipe_id", "Receita")))}</h1><p>Curvas térmicas e observações sensoriais são modelos separados. A checagem de segurança tem prioridade sobre qualquer preferência.</p><div class="banner">{banner}</div>{''.join(blocks)}<section><h2>Limites</h2><p>O coeficiente de resfriamento vale apenas para massa, recipiente, tampa, ventilação, agitação e posição da sonda registrados. Jaccard, NPMI e XlogP não foram usados para inferir volatilização. Uma associação entre nota, temperatura e tempo não demonstra causalidade.</p><p>Referências: Talavera et al. (2007); Lemon (2017); revisão de liberação de aroma em <em>Molecules</em> (2023); USDA FSIS para manutenção quente e limites gerais de exposição. Ver <code>data/SOURCES.md</code>.</p></section></main></body></html>'''


def generate_report(input_path: Path, output_path: Path, result_path: Path | None = None) -> tuple[Path, Path]:
    document = json.loads(Path(input_path).read_text(encoding="utf-8"))
    result = analyze_experiment(document)
    output_path = Path(output_path)
    result_path = Path(result_path) if result_path else output_path.with_suffix(".json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_report(document, result), encoding="utf-8")
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return output_path, result_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--result-json", type=Path)
    args = parser.parse_args()
    html_path, json_path = generate_report(args.input, args.output, args.result_json)
    print(f"relatório: {html_path}")
    print(f"resultado: {json_path}")


if __name__ == "__main__":
    main()
