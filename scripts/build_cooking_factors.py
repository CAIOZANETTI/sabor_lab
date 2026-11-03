"""Gera as tabelas de fatores de preparo (demanda 007) a partir das fontes oficiais da USDA.

Entradas (domínio público, versionadas em data/raw/usda_factors/):
    retn06.txt                              USDA Table of Nutrient Retention Factors, Release 6 (2007)
    USDA_CookingYields_MeatPoultry02.xlsx   USDA Table of Cooking Yields for Meat and Poultry, Release 2 (2014)
    sr_legacy_food.csv                      FoodData Central SR Legacy: fdc_id <-> NDB_number

Saídas (data/cooking_factors/ e reports/fatores_preparo_cobertura.md):
    retention_factors.csv   todos os 7.018 fatores (270 códigos x 26 componentes), fração 0–1,
                            com a chave de nutriente do SaborLab quando a expressão é a mesma
    cooking_yields.csv      173 rendimentos com perda/ganho de água e gordura (% do peso cru),
                            o registro cozido medido (usda:<fdc_id>) e o cru correspondente,
                            quando o nome do registro cru existe exatamente no SR Legacy

Uso:
    python scripts/build_cooking_factors.py            # regenera
    python scripts/build_cooking_factors.py --check    # falha se os CSV versionados divergirem
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "usda_factors"
OUT = ROOT / "data" / "cooking_factors"

# Nutr_No (numeração antiga do SR) -> chave canônica do SaborLab.
# Só entra quando a expressão é a mesma: vitamina A em UI/RE não equivale a RAE; carotenoides,
# colina, ácido fólico e folato alimentar não existem no banco nutricional atual.
NUTR_KEYS = {
    "221": "alcool_g", "301": "calcio_mg", "303": "ferro_mg", "304": "magnesio_mg", "305": "fosforo_mg",
    "306": "potassio_mg", "307": "sodio_mg", "309": "zinco_mg", "312": "cobre_mg",
    "401": "vitamina_c_mg", "404": "tiamina_mg", "405": "riboflavina_mg", "406": "niacina_mg",
    "415": "vitamina_b6_mg", "417": "folato_ug", "418": "vitamina_b12_ug",
}
UNMAPPED_REASON = {
    "318": "vitamina A em UI (o banco usa RAE)", "392": "vitamina A em RE (o banco usa RAE)",
    "321": "betacaroteno ausente no banco", "322": "alfacaroteno ausente no banco",
    "334": "betacriptoxantina ausente no banco", "337": "licopeno ausente no banco",
    "338": "luteína + zeaxantina ausente no banco", "421": "colina ausente no banco",
    "431": "ácido fólico ausente no banco (só folato total)", "432": "folato alimentar ausente no banco",
}

# "Preparation Method" da tabela de rendimento -> método do SaborLab (data/cooking_factors/methods.csv)
YIELD_METHODS = {
    "baked or roasted, unspecified": "roast_bake", "baked or roasted, specified time": "roast_bake",
    "roasted": "roast_bake", "broiled or grilled": "grill_broil", "grilled": "grill_broil",
    "broiled": "grill_broil", "braised": "braise", "poached, simmered or stewed": "boil",
    "pan-fried": "pan_fry", "pan-broiled": "pan_fry", "pan broiled": "pan_fry", "pan-browned": "pan_fry",
    "pan-fried or sauteed": "pan_fry", "fried in deep fat": "deep_fry", "microwaved": "microwave",
    "multiple cooking methods": "",
}

_COOKED_TAIL = re.compile(r",?\s*(patty\s+)?cooked\b.*$", re.I)


def build_retention() -> pd.DataFrame:
    cols = ["retn_code", "usda_food_group", "description", "nutr_no", "nutrient_usda", "percent", "date"]
    r = pd.read_csv(RAW / "retn06.txt", sep="^", quotechar="~", header=None, names=cols, dtype=str,
                    encoding="latin-1", keep_default_na=False)
    r["description"] = r["description"].str.strip()
    # campo vazio na fonte (código 5005, exceto álcool) = fator não informado, nunca zero
    r["percent"] = pd.to_numeric(r["percent"].replace("", None)).astype("Int64")
    r["factor"] = (r["percent"] / 100).round(2)
    r["nutrient_key"] = r["nutr_no"].map(NUTR_KEYS).fillna("")
    r["unmapped_reason"] = r["nutr_no"].map(UNMAPPED_REASON).fillna("")
    r["basis"] = "true_retention"  # %TR = (Nc*Gc)/(Nr*Gr)*100; arredondado a 5%, máximo 100%
    r["source_id"] = "usda_retention_r6"
    out = r[["retn_code", "usda_food_group", "description", "nutr_no", "nutrient_usda", "nutrient_key",
             "unmapped_reason", "percent", "factor", "basis", "date", "source_id"]]
    return out.sort_values(["retn_code", "nutr_no"]).reset_index(drop=True)


def build_yields() -> pd.DataFrame:
    x = pd.read_excel(RAW / "USDA_CookingYields_MeatPoultry02.xlsx")
    x.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in x.columns]
    x = x[x["Yield Description"].notna() & x["Cooking Yield %"].notna()].copy()
    sr = pd.read_csv(RAW / "sr_legacy_food.csv", dtype=str)
    ndb_to_fdc = dict(zip(sr["NDB_number"], sr["fdc_id"]))
    foods = pd.read_parquet(ROOT / "data" / "processed" / "nutrition" / "foods.parquet")
    usda = foods[foods["fonte"] == "usda_sr_legacy"]
    name_of = dict(zip(usda["food_id"], usda["nome"]))
    by_name = {n.lower(): fid for fid, n in name_of.items()}

    rows = []
    for _, r in x.iterrows():
        ndb = str(int(r["NDB"])) if pd.notna(r["NDB"]) else ""
        cooked_id = f"usda:{ndb_to_fdc[ndb]}" if ndb in ndb_to_fdc else ""
        if cooked_id and cooked_id not in name_of:
            cooked_id = ""
        raw_id, raw_rule = "", ""
        if cooked_id:
            raw_name = _COOKED_TAIL.sub("", name_of[cooked_id]).strip(" ,") + ", raw"
            raw_id = by_name.get(raw_name.lower(), "")
            raw_rule = "nome do registro cozido sem o trecho 'cooked, <método>' + ', raw' (igualdade exata)" if raw_id else ""
        method_usda = re.sub(r"\s+", " ", str(r["Preparation Method1"])).strip()
        year = int(r["Release Year2"]) if pd.notna(r["Release Year2"]) else None

        def num(col):
            v = r.get(col)
            return round(float(v), 3) if pd.notna(v) else None

        rows.append({
            "yield_id": f"usda_cy2:{ndb or 'sem_ndb'}:{YIELD_METHODS.get(method_usda.lower(), 'nd')}:{len(rows):03d}",
            "description": str(r["Yield Description"]).strip(),
            "usda_method": method_usda,
            "method_key": YIELD_METHODS.get(method_usda.lower(), ""),
            "ndb_number": ndb,
            "cooked_food_id": cooked_id,
            "raw_food_id": raw_id,
            "raw_link_rule": raw_rule,
            "yield_pct": num("Cooking Yield %"),
            "n": num("n"),
            "sd": num("SD"),
            "yield_min_pct": num("Yield Minimum %"),
            "yield_max_pct": num("Yield Maximum %"),
            "moisture_change_pct": num("Moisture Gain/ Loss %"),
            "fat_change_pct": num("Fat Gain/ Loss %"),
            "release_year": year,
            "basis": "peso cru (Wcr); rendimento = 100 x Wch/Wcr; variação = 100 x (Nc*Ec - Nr*Er)/Wcr",
            "notes": ("dado de 1975 (AH-102): sem variação de água/gordura, n ou DP" if year == 1975 else ""),
            "source_id": "usda_cooking_yields_r2",
        })
    return pd.DataFrame(rows)


REPORT = ROOT / "reports" / "fatores_preparo_cobertura.md"


def _md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def coverage_report(retention: pd.DataFrame, yields: pd.DataFrame) -> str:
    methods = pd.read_csv(OUT / "methods.csv", dtype=str, keep_default_na=False)
    rmap = pd.read_csv(OUT / "retention_map.csv", dtype=str, keep_default_na=False)
    order = [m for m in methods["method_key"] if not m.endswith("_unspecified")]

    y = yields.copy()
    y["espécie"] = y["description"].str.split(",").str[0].str.strip()
    y["method_key"] = y["method_key"].replace("", "(vários métodos; não aplicado)")
    ytab = (y.assign(com_cru=y["raw_food_id"].ne("") & y["raw_food_id"].notna())
            .groupby(["espécie", "method_key"]).agg(rendimentos=("yield_id", "size"), ligados_ao_cru=("com_cru", "sum"))
            .reset_index().rename(columns={"method_key": "método"}))

    r = rmap.copy()
    r["entidade"] = r["match"].str.replace("sl:ingredient:", "", regex=False)
    piv = (r.assign(v=r["retn_code"] + r["match_level"].map({"specific": "", "group": "ᵍ"}))
           .groupby(["entidade", "method_key"])["v"].apply(lambda s: "/".join(sorted(set(s)))).unstack(fill_value="—"))
    piv = piv.reindex(columns=[m for m in order if m in piv.columns]).fillna("—").reset_index()

    no_yield = [m for m in order if m not in set(yields["method_key"])]
    no_ret = [m for m in order if m not in set(rmap["method_key"])]
    blank = retention[retention["factor"].isna()]
    unmapped = retention[retention["nutrient_key"] == ""].drop_duplicates("nutr_no")
    no_raw = yields[(yields["raw_food_id"].isna()) | (yields["raw_food_id"] == "")]
    no_water = yields[yields["moisture_change_pct"].isna()]

    parts = [
        "# Cobertura dos fatores de preparo (demanda 007)",
        "",
        "Gerado por `python scripts/build_cooking_factors.py`. Fontes: USDA Table of Nutrient Retention Factors "
        "Release 6 (2007) e USDA Table of Cooking Yields for Meat and Poultry Release 2 (2014), ambas de domínio "
        "público. Regras de aplicação em `data/cooking_factors/retention_map.csv`.",
        "",
        f"- Retenção: {len(retention)} fatores, {retention['retn_code'].nunique()} códigos, "
        f"{retention['nutrient_key'].ne('').sum()} com nutriente equivalente no banco.",
        f"- Rendimento: {len(yields)} linhas; {int((yields['cooked_food_id'].fillna('') != '').sum())} ligadas ao "
        f"registro cozido medido e {int((yields['raw_food_id'].fillna('') != '').sum())} ao registro cru.",
        f"- Regras de retenção curadas: {len(rmap)} ({(rmap['match_level'] == 'specific').sum()} específicas, "
        f"{(rmap['match_level'] == 'group').sum()} de grupo, que têm baixa confiança).",
        "",
        "## Rendimento por espécie e método",
        "",
        _md(ytab),
        "",
        "## Retenção por entidade e método",
        "",
        "Código USDA aplicado; ᵍ = fator de grupo (baixa confiança). Vários códigos = escolha por condição "
        "(líquido descartado/consumido, casca, empanamento, teor de gordura do peixe, tempo das leguminosas).",
        "",
        _md(piv),
        "",
        "## Fatores ausentes",
        "",
        f"- Métodos sem rendimento USDA: {', '.join(no_yield)}.",
        f"- Métodos sem regra de retenção: {', '.join(no_ret)}.",
        "- Rendimento existe só para carnes e aves. Hortaliças, cereais, leguminosas e laticínios dependem de "
        "pesagem antes/depois (rendimento observado) ou de registro preparado medido.",
        "- **Fraldinha** (`sl:part:beef_fraldinha`): sem rendimento nem registro grelhado/assado/air fryer. "
        "A TACO só traz fraldinha crua e cozida. O flank da USDA (`sl:part:beef_flank_us`) é outra entidade "
        "no catálogo e não é usado como equivalente.",
        f"- {len(no_raw)} linhas de rendimento sem registro cru correspondente por nome exato no SR Legacy "
        "(ex.: carne moída por faixa de gordura, cortes com osso, aves de 1975). Não são aplicadas automaticamente.",
        f"- {len(no_water)} linhas de rendimento sem variação de água/gordura ({int((no_water['release_year'] == 1975).sum())} "
        "de 1975, do AH-102, e médias agregadas de 'retail cuts' de 2011). Nelas, água e gordura cozidas ficam "
        "desconhecidas ou estimadas.",
        f"- {len(blank)} fatores em branco na própria fonte (código 5005, bebida alcoólica, só álcool informado).",
        "- Componentes da tabela USDA sem equivalente no banco: "
        + "; ".join(f"{r.nutrient_usda} ({r.unmapped_reason})" for r in unmapped.itertuples()) + ".",
        "- Macronutrientes (proteína, carboidratos, fibra, açúcares, amido, cinzas) não têm fator na USDA. Por "
        "isso são transportados como **estimados**; Bognár (2002) mostra perdas em alguns métodos.",
        "- Leguminosas: só há fator nas faixas de tempo da USDA (15–20 min, 45–75 min, 2–2,5 h). Panela de "
        "pressão não tem fator.",
        "- Absorção de óleo em fritura e perda de gordura sem dado da tabela exigem medição (`FatTransfer`).",
        "",
    ]
    return "\n".join(parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="só confere se os CSV versionados estão atualizados")
    args = ap.parse_args(argv)
    retention, yields = build_retention(), build_yields()
    tables = {OUT / "retention_factors.csv": retention.to_csv(index=False, lineterminator="\n"),
              OUT / "cooking_yields.csv": yields.to_csv(index=False, lineterminator="\n"),
              REPORT: coverage_report(retention, yields)}
    stale = []
    for path, text in tables.items():
        name = path.name
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"{path.relative_to(ROOT)}: {text.count(chr(10))} linhas")
    if stale:
        print("desatualizado: " + ", ".join(stale) + " — rode python scripts/build_cooking_factors.py")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
