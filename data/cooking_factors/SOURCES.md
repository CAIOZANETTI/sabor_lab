# Fontes dos fatores de preparo

| arquivo | fonte | versão | licença | acesso |
|---|---|---|---|---|
| `retention_factors.csv` | USDA ARS NDL, *Table of Nutrient Retention Factors* — https://www.ars.usda.gov/ARSUserFiles/80400535/Data/retn/retn06.txt | Release 6 (dez. 2007) | domínio público | 2026-11-03 |
| `cooking_yields.csv` | USDA ARS NDL, *Table of Cooking Yields for Meat and Poultry* — https://ars.usda.gov/ARSUserFiles/80400535/Data/retn/USDA_CookingYields_MeatPoultry02.xlsx | Release 2 (set. 2014) | domínio público | 2026-11-03 |
| ligação NDB → FDC | USDA FoodData Central, SR Legacy `sr_legacy_food.csv` | 2018-04 | CC0 1.0 | 2026-11-03 |
| `methods.csv`, `retention_map.csv` | curadoria SaborLab sobre as descrições da USDA; método de cálculo de Reinivuo & Laitinen (EuroFIR 2007) | demanda 007 | licença do repositório | — |

Cópias brutas, com hash SHA-256, ficam em `data/raw/usda_factors/`:

- `retn06.txt` — `5b71867f6649e801db3bf88c6cd1887b0673e853d4ba94aa0af2b3c091e983f9`
- `USDA_CookingYields_MeatPoultry02.xlsx` — `13bd2cec633841867bf8532ed57114c81f3791b9bcd35a396dec6a1b960773ff`
- `sr_legacy_food.csv` — `ff0fe85a469aa6d6702d68348850fc79dee35e9515324026964f1209a0e3544d`

Os CSV são gerados por `scripts/build_cooking_factors.py`. O registro único de fontes, usado
pelos claims, está em `data/knowledge/sources.csv`: `usda_retention_r6`,
`usda_cooking_yields_r2`, `eurofir_recipe_calc_2007`, `bognar_2002` e
`fao_infoods_recipe_calc_2021`.

Decisões de leitura:

- **Fatores em branco** na fonte (código 5005) ficam vazios. Não viram zero.
- **Vitamina A** em UI ou RE não equivale a RAE, então não é mapeada.
- **Ligação do rendimento ao registro cru:** só por igualdade exata de nome, retirando o
  trecho "cooked, <método>" do registro cozido e acrescentando ", raw". Sem igualdade
  exata, não há ligação.
