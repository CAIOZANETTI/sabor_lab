import pytest

from flavorlab.nutrition import parse_quantity
from flavorlab.units import classify, fahrenheit_to_celsius, fmt_num, metricize_text


@pytest.mark.parametrize("unit,kind,factor", [
    ("g", "massa", 1.0), ("kg", "massa", 1000.0), ("oz", "massa", 28.349523125),
    ("lb", "massa", 453.59237), ("Libras", "massa", 453.59237),
    ("ml", "volume", 1.0), ("L", "volume", 1000.0),
    ("xícara", "volume", 240.0), ("Colheres de Sopa", "volume", 15.0), ("colher de chá", "volume", 5.0),
    ("cup", "volume", 236.5882365), ("tbsp", "volume", 236.5882365 / 16), ("tsp", "volume", 236.5882365 / 48),
    ("fl oz", "volume", 29.5735295625), ("quart", "volume", 946.352946),
])
def test_classify_metric_and_imperial(unit, kind, factor):
    k, f = classify(unit)
    assert k == kind and f == pytest.approx(factor)


def test_imperial_definitions_are_exact():
    # 1 tbsp = 3 tsp ; 1 cup = 16 tbsp ; 1 lb = 16 oz
    assert classify("tbsp")[1] == pytest.approx(3 * classify("tsp")[1])
    assert classify("cup")[1] == pytest.approx(16 * classify("tbsp")[1])
    assert classify("lb")[1] == pytest.approx(16 * classify("oz")[1])


def test_count_units_and_unknown():
    assert classify("dentes") == ("contagem", "dente")
    assert classify("un") == ("contagem", "unidade")
    assert classify("cloves") == ("contagem", "dente")
    assert classify("punhado")[0] == "desconhecida"


def test_temperature_and_text():
    assert fahrenheit_to_celsius(212) == pytest.approx(100)
    assert fahrenheit_to_celsius(32) == pytest.approx(0)
    assert metricize_text("forno a 350°F, bolinhas de 2 inch") == "forno a 177 °C, bolinhas de 5,1 cm"
    assert metricize_text("assar a 400 F") == "assar a 204 °C"
    assert metricize_text("sem unidades") == "sem unidades"
    assert metricize_text("1/2 cup") == "118,3 ml"
    assert metricize_text("2-1/4 cups") == "532,3 ml"
    assert metricize_text("3 heaping tsp") == "14,8 ml"
    assert metricize_text("package 0.6 oz") == "package 17,0 g"
    assert metricize_text("8 fluid oz") == "236,6 ml"
    assert metricize_text('3-3/4" long') == "9,5 cm long"


def test_parse_quantity():
    assert parse_quantity("1/2") == 0.5
    assert parse_quantity("2 1/4") == 2.25
    assert parse_quantity("0,25") == 0.25
    assert parse_quantity(3) == 3.0
    assert parse_quantity("") != parse_quantity("")  # NaN


def test_fmt_num_brazilian():
    assert fmt_num(1234.5) == "1.234,5"
    assert fmt_num(0.53, 2) == "0,53"
