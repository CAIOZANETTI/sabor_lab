"""Baixa as bases de composição nutricional.

USDA FoodData Central (domínio público, CC0) -> data/raw/usda/   (fora do git; ~10 MB)
    - SR Legacy (2018-04): 7.793 alimentos, ~150 nutrientes, porções em gramas
    - Foundation Foods (2025-12-18): 436 alimentos com análise laboratorial recente

TACO 4ª ed. (NEPA/UNICAMP) + Medidas Referidas da POF 2008-2009 (IBGE)
    normalizadas pelo repositório brolesi/taco (MIT) -> data/raw/taco/  (versionado)
    Fixamos um commit para o build ser reprodutível.

Uso:
    python scripts/download_nutrition.py
"""

from __future__ import annotations

import io
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

USDA = {
    "sr_legacy": "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip",
    "foundation": "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_foundation_food_csv_2025-12-18.zip",
}
# só os arquivos que o build usa
USDA_FILES = {"food.csv", "nutrient.csv", "food_nutrient.csv", "food_category.csv",
              "food_portion.csv", "measure_unit.csv"}

TACO_COMMIT = "b800c910dfc9d2e8e6bab45dd42e5b8f5167b466"
TACO_BASE = f"https://raw.githubusercontent.com/brolesi/taco/{TACO_COMMIT}/"
TACO_FILES = {
    "data/processed/taco/taco_composicao.csv": "taco_composicao.csv",
    "data/processed/taco/taco_acidos_graxos.csv": "taco_acidos_graxos.csv",
    "data/processed/taco/taco_aminoacidos.csv": "taco_aminoacidos.csv",
    "data/processed/pof/pof_medidas_caseiras.csv": "pof_medidas_caseiras.csv",
    "LICENSE": "LICENSE-brolesi-taco",
}


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=300) as resp:
        return resp.read()


def download_usda() -> None:
    for name, url in USDA.items():
        out = RAW / "usda" / name
        out.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(fetch(url))) as zf:
            for member in zf.namelist():
                fname = Path(member).name
                if fname in USDA_FILES:
                    (out / fname).write_bytes(zf.read(member))
        print(f"USDA {name}: {sorted(p.name for p in out.glob('*.csv'))}")


def download_taco() -> None:
    out = RAW / "taco"
    out.mkdir(parents=True, exist_ok=True)
    for src, dst in TACO_FILES.items():
        (out / dst).write_bytes(fetch(TACO_BASE + src))
        print(f"TACO {dst} ({(out / dst).stat().st_size / 1e3:.0f} kB)")


if __name__ == "__main__":
    download_usda()
    download_taco()
