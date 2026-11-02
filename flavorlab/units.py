"""Unidades: tudo convertido para o sistema métrico (g, ml, °C, cm).

Aceita unidades métricas, medidas caseiras brasileiras e unidades imperiais/EUA
(cup, tbsp, tsp, oz, lb, fl oz, pint, quart, gallon, °F, inch). As imperiais são
convertidas com os fatores exatos de definição (NIST).

Medidas caseiras brasileiras usam as capacidades padrão de receituário:
xícara 240 ml, colher de sopa 15 ml, de sobremesa 10 ml, de chá 5 ml,
de café 2,5 ml, copo americano 190 ml.
"""

from __future__ import annotations

import re
import unicodedata

# ----------------------------------------------------------------- massa (g)
MASS_G = {
    "g": 1.0, "grama": 1.0, "gramas": 1.0, "gr": 1.0,
    "kg": 1000.0, "quilo": 1000.0, "quilos": 1000.0, "kilo": 1000.0,
    "mg": 0.001, "miligrama": 0.001, "miligramas": 0.001,
    # imperiais (definição exata: 1 lb = 453,59237 g; 1 oz = lb/16)
    "oz": 28.349523125, "onca": 28.349523125, "oncas": 28.349523125, "ounce": 28.349523125,
    "ounces": 28.349523125,
    "lb": 453.59237, "lbs": 453.59237, "libra": 453.59237, "libras": 453.59237,
    "pound": 453.59237, "pounds": 453.59237,
}

# --------------------------------------------------------------- volume (ml)
US_CUP = 236.5882365  # 1 cup EUA = 8 fl oz
VOLUME_ML = {
    "ml": 1.0, "mililitro": 1.0, "mililitros": 1.0,
    "l": 1000.0, "litro": 1000.0, "litros": 1000.0, "lt": 1000.0,
    "dl": 100.0, "cl": 10.0,
    # medidas caseiras brasileiras (padrão de receituário)
    "xicara": 240.0, "xicaras": 240.0, "xicara de cha": 240.0, "xic": 240.0,
    "xicara de cafe": 50.0,
    "colher de sopa": 15.0, "colheres de sopa": 15.0, "csp": 15.0, "c sopa": 15.0,
    "colher de sobremesa": 10.0, "colheres de sobremesa": 10.0,
    "colher de cha": 5.0, "colheres de cha": 5.0, "cch": 5.0, "c cha": 5.0,
    "colher de cafe": 2.5, "colheres de cafe": 2.5,
    "copo americano": 190.0, "copo": 200.0,
    "pitada": 0.3, "pitadas": 0.3,
    # EUA (definições exatas a partir do cup)
    "cup": US_CUP, "cups": US_CUP,
    "tbsp": US_CUP / 16, "tablespoon": US_CUP / 16, "tablespoons": US_CUP / 16, "tbs": US_CUP / 16,
    "tsp": US_CUP / 48, "teaspoon": US_CUP / 48, "teaspoons": US_CUP / 48,
    "fl oz": US_CUP / 8, "fluid ounce": US_CUP / 8, "fluid ounces": US_CUP / 8, "floz": US_CUP / 8,
    "pint": US_CUP * 2, "pints": US_CUP * 2, "pt": US_CUP * 2,
    "quart": US_CUP * 4, "quarts": US_CUP * 4, "qt": US_CUP * 4,
    "gallon": US_CUP * 16, "gallons": US_CUP * 16, "gal": US_CUP * 16,
    "dash": US_CUP / 48 / 8, "pinch": US_CUP / 48 / 16,
}

# nome em português para exibição das unidades EUA
US_NAMES_PT = {
    "cup": "xícara EUA", "tbsp": "colher de sopa EUA", "tablespoon": "colher de sopa EUA",
    "tsp": "colher de chá EUA", "teaspoon": "colher de chá EUA", "fl oz": "onça fluida",
    "oz": "onça", "lb": "libra", "pint": "pinta EUA", "quart": "quarto de galão EUA", "gallon": "galão EUA",
}

# unidades de contagem: pt -> (medidas POF/IBGE, palavras nas porções do USDA)
COUNT_UNITS = {
    "unidade": (["UNIDADE", "UNIDADE MEDIA"], ["medium", "whole", "each", "large", "fruit", "item"]),
    "dente": (["DENTE", "UNIDADE"], ["clove"]),
    "fatia": (["FATIA"], ["slice"]),
    "folha": (["FOLHA"], ["leaf", "leaves"]),
    "ramo": (["RAMO", "MACO"], ["sprig", "stalk", "stem"]),
    "talo": (["TALO"], ["stalk"]),
    "pedaco": (["PEDACO"], ["piece"]),
    "pau": ([], ["stick"]),
    "rodela": (["RODELA"], ["slice"]),
    "file": (["FILE", "BIFE"], ["fillet", "steak"]),
    "lata": (["LATA"], ["can"]),
}
COUNT_ALIASES = {
    "un": "unidade", "und": "unidade", "unid": "unidade", "unidades": "unidade", "u": "unidade",
    "dentes": "dente", "fatias": "fatia", "folhas": "folha", "ramos": "ramo", "talos": "talo",
    "pedacos": "pedaco", "paus": "pau", "rodelas": "rodela", "files": "file", "latas": "lata",
    "each": "unidade", "clove": "dente", "cloves": "dente", "slice": "fatia", "slices": "fatia",
    "leaf": "folha", "leaves": "folha", "sprig": "ramo", "stick": "pau", "piece": "pedaco",
}


def norm_unit(unit: str) -> str:
    """'Colheres de Sopa.' -> 'colheres de sopa' (sem acento, minúsculo)."""
    text = unicodedata.normalize("NFKD", str(unit)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def classify(unit: str) -> tuple[str, float | str | None]:
    """Retorna ('massa', g por unidade), ('volume', ml por unidade),
    ('contagem', nome canônico) ou ('desconhecida', None)."""
    u = norm_unit(unit)
    if u in MASS_G:
        return "massa", MASS_G[u]
    if u in VOLUME_ML:
        return "volume", VOLUME_ML[u]
    if u in COUNT_UNITS:
        return "contagem", u
    if u in COUNT_ALIASES:
        return "contagem", COUNT_ALIASES[u]
    return "desconhecida", None


# ------------------------------------------------- texto livre (técnica etc.)
_F = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*°?\s*F\b")
_INCH = re.compile(_NUM_INCH := r"(\d+[\s-]\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)" + r"\s*-?\s*(?:inches|inch|in\.|\")")
_NUM = r"(\d+[\s-]\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)"  # 1 1/2 | 2-1/4 | 1/2 | 0.25 | 2
_US_QTY = re.compile(_NUM + r"\s*-?\s*(?:heaping|level|rounded|scant)?\s*(fl\.? oz|fluid ounces?|fluid oz|cups?|tablespoons?|tbsp|teaspoons?|tsp|"
                     r"ounces?|oz|pounds?|lbs?|pints?|quarts?|gallons?)\b", re.IGNORECASE)


def _num(text: str) -> float:
    text = re.sub(r"(\d)-(\d+/)", r"\1 \2", text.replace(",", ".").strip())
    total = 0.0
    for part in text.split():
        if "/" in part:
            a, b = part.split("/")
            total += float(a) / float(b)
        else:
            total += float(part)
    return total


def _us_qty(m: re.Match) -> str:
    qty, unit = _num(m.group(1)), norm_unit(m.group(2))
    unit = {"fl": "fl oz", "fluid oz": "fl oz"}.get(unit, unit)
    if unit in MASS_G:
        return f"{fmt_num(qty * MASS_G[unit])} g"
    if unit in VOLUME_ML:
        return f"{fmt_num(qty * VOLUME_ML[unit])} ml"
    return m.group(0)


def fahrenheit_to_celsius(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0


def metricize_text(text: str) -> str:
    """Converte unidades imperiais em texto livre para o métrico:
    '350°F' -> '177 °C' ; '2 inch' -> '5,1 cm' ; '1/2 cup' -> '118,3 ml' ; '0.6 oz' -> '17,0 g'."""
    if not isinstance(text, str):
        return text
    text = _F.sub(lambda m: f"{fahrenheit_to_celsius(float(m.group(1).replace(',', '.'))):.0f} °C", text)
    text = _INCH.sub(lambda m: f"{fmt_num(_num(m.group(1)) * 2.54, 1)} cm", text)
    return _US_QTY.sub(_us_qty, text)


def fmt_num(x: float, nd: int = 1) -> str:
    """Formato brasileiro: 1234.5 -> '1.234,5'."""
    s = f"{x:,.{nd}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")
