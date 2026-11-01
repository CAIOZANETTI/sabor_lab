import json
import re
import subprocess
import sys

from flavorlab import analyze_recipe
from flavorlab.report import network_data, render_html

from conftest import ROOT


def _net_json(doc: str) -> dict:
    m = re.search(r'<script type="application/json" id="net-data">(.*?)</script>', doc, re.S)
    assert m, "dados do grafo não encontrados"
    return json.loads(m.group(1))


def test_network_data_structure(tiny_db):
    a = analyze_recipe(tiny_db, ["cinnamon", "clove", "sugar"])
    d = network_data(a)
    ids = {n["id"] for n in d["nodes"]}
    assert {"i:cinnamon", "i:clove", "i:sugar", "m:2", "m:3", "m:4"} <= ids
    for e in d["edges"]:
        assert e["from"] in ids and e["to"] in ids
    recipe_edges = [e for e in d["edges"] if e["kind"] == "recipe"]
    assert {(e["from"], e["to"]) for e in recipe_edges} == {("i:cinnamon", "i:clove"), ("i:cinnamon", "i:sugar")}
    assert "woody" in d["tags"]


def test_render_html_is_complete_and_interactive(tiny_db, tmp_path):
    a = analyze_recipe(tiny_db, ["cinnamon", "clove", "tomato"])
    out = tmp_path / "r.html"
    doc = render_html(a, {"Por que gostei": "aroma quente"}, out=out)
    assert out.read_text(encoding="utf-8") == doc
    assert doc.startswith("<!DOCTYPE html>") and doc.rstrip().endswith("</html>")
    assert "vis-network" in doc and "cdn.plot.ly" in doc
    assert doc.count('class="plotly-graph-div"') == 3
    assert "aroma quente" in doc
    assert len(_net_json(doc)["nodes"]) == 3 + 3


def test_html_escapes_user_text(tiny_db):
    a = analyze_recipe(tiny_db, ["cinnamon", "clove"], name="<script>alert(1)</script>")
    doc = render_html(a, {"Observações": "</script><b>x"})
    assert "<script>alert(1)</script>" not in doc
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in doc
    _net_json(doc)  # JSON do grafo continua íntegro


def test_cli_quick_mode(real_db, tmp_path):
    name = "pytest cli"
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / "recipe_report.py"),
                          "--ingredients", "cinnamon,clove", "--name", name],
                         capture_output=True, text=True, cwd=ROOT)
    assert res.returncode == 0, res.stderr
    out = ROOT / "reports" / "pytest_cli.html"
    try:
        assert out.exists() and "cinnamon" in out.read_text(encoding="utf-8")
    finally:
        out.unlink(missing_ok=True)
