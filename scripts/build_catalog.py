"""Valida o catálogo curado e gera o inventário completo das fontes (ledger).

Entradas:
    data/catalog/*.csv                         camada curada (revisável em diff)
    data/processed/nutrition/foods.parquet     TACO + USDA (scripts/build_nutrition.py)
    data/processed/ingredients.parquet         FlavorDB + FlavorGraph (scripts/build_database.py)

Saídas:
    data/catalog/source_inventory.csv          1 linha por registro de fonte (100%), com estado,
                                               entidade, candidatos, confiança, regra e motivo
    reports/catalog_coverage.md                cobertura por fonte, grupo, idioma, status e confiança
    data/processed/catalog/*.parquet           (opcional, --parquet) cópia para consulta rápida

O build falha se:
    - a validação do catálogo encontrar erros (IDs, ciclos, tipos, fontes, licenças...);
    - algum registro presente no inventário anterior desaparecer (use --allow-removal
      somente quando a fonte realmente removeu o registro, e explique no PR).

Uso:
    python scripts/build_catalog.py             # valida, gera ledger e relatório
    python scripts/build_catalog.py --check     # só confere se o ledger versionado está atualizado
    python scripts/build_catalog.py --parquet   # também grava Parquet em data/processed/catalog/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flavorlab.catalog import CATALOG_DIR, Catalog  # noqa: E402
from flavorlab.catalog_mapping import (build_inventory, check_no_loss, coverage_report,  # noqa: E402
                                       load_source_records)

LEDGER = CATALOG_DIR / "source_inventory.csv"
REPORT = ROOT / "reports" / "catalog_coverage.md"
PARQUET_DIR = ROOT / "data" / "processed" / "catalog"


def build(catalog_dir: Path = CATALOG_DIR) -> tuple[Catalog, pd.DataFrame, list[str]]:
    cat = Catalog.load(catalog_dir, with_inventory=False)
    records = load_source_records()
    errors = cat.validate(records)
    inv = build_inventory(cat, records)
    return cat, inv, errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="falha se o ledger versionado estiver desatualizado")
    ap.add_argument("--allow-removal", action="store_true", help="aceita registros que sumiram da fonte")
    ap.add_argument("--parquet", action="store_true", help="grava cópia Parquet para consulta")
    args = ap.parse_args(argv)

    cat, inv, errors = build()
    if errors:
        print(f"catálogo inválido ({len(errors)} erros):")
        for e in errors[:200]:
            print("  -", e)
        return 1

    previous = pd.read_csv(LEDGER, dtype=str, keep_default_na=False) if LEDGER.exists() else None
    lost = check_no_loss(previous, inv)
    if lost and not args.allow_removal:
        print(f"{len(lost)} registros sumiram do inventário (ex.: {lost[:10]}). "
              "Investigue a fonte ou rode com --allow-removal.")
        return 1

    if args.check:
        if previous is None or not previous.equals(inv.astype(str)):
            print("source_inventory.csv desatualizado: rode python scripts/build_catalog.py")
            return 1
        print(f"ledger atualizado: {len(inv)} registros")
        return 0

    inv.to_csv(LEDGER, index=False)
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(coverage_report(cat, inv), encoding="utf-8")
    if args.parquet:
        PARQUET_DIR.mkdir(parents=True, exist_ok=True)
        inv.to_parquet(PARQUET_DIR / "source_inventory.parquet", index=False)
        for name in ("ingredient_concepts", "ingredient_variants", "culinary_parts", "ingredient_forms",
                     "source_mappings", "relations", "taxa"):
            pd.read_csv(CATALOG_DIR / f"{name}.csv", dtype=str, keep_default_na=False) \
                .to_parquet(PARQUET_DIR / f"{name}.parquet", index=False)

    counts = inv["status"].value_counts()
    print(f"catálogo: {len(cat.concepts)} conceitos, {len(cat.variant_rows)} variantes, "
          f"{len(cat.part_rows)} partes, {len(cat.form_rows)} formas, {len(cat.curated_mappings)} mapeamentos curados")
    print(f"inventário: {len(inv)} registros -> {LEDGER.relative_to(ROOT)}")
    for status, n in counts.items():
        print(f"  {status:<24} {n:>6}")
    print(f"relatório: {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
