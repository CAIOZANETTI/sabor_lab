# Cobertura do catálogo canônico de alimentos

Gerado por `python scripts/build_catalog.py`. Não editar à mão.

- Registros inventariados: **16414** (usda: 8229, flavorgraph: 6653, flavordb: 935, taco: 597)
- Limite de confiança para mapeamento automático aceito: **0.85**
- conceitos: 548, variantes: 168, partes: 89, formas: 361, táxons: 241, relações explícitas: 182, mapeamentos curados: 1601

## Por fonte

| source | mapped_reviewed | mapped_high_confidence | mapped_low_confidence | ambiguous | unmapped | excluded_with_reason | total | % mapeado |
|---|---|---|---|---|---|---|---|---|
| flavordb | 0 | 311 | 146 | 7 | 458 | 13 | 935 | 48.9 |
| flavorgraph | 0 | 1231 | 1616 | 126 | 3680 | 0 | 6653 | 42.8 |
| taco | 0 | 572 | 13 | 0 | 12 | 0 | 597 | 98.0 |
| usda | 0 | 2211 | 1992 | 245 | 3781 | 0 | 8229 | 51.1 |
| TOTAL | 0 | 4325 | 3767 | 378 | 7931 | 13 | 16414 | 49.3 |

## Por grupo alimentar

| food_group | mapped_reviewed | mapped_high_confidence | mapped_low_confidence | ambiguous | unmapped | excluded_with_reason | total | % mapeado |
|---|---|---|---|---|---|---|---|---|
| sl:group:beverages | 0 | 105 | 198 | 0 | 470 | 0 | 773 | 39.2 |
| sl:group:cereals | 0 | 303 | 337 | 6 | 160 | 0 | 806 | 79.4 |
| sl:group:dairy | 0 | 331 | 337 | 10 | 61 | 0 | 739 | 90.4 |
| sl:group:eggs | 0 | 41 | 15 | 0 | 0 | 0 | 56 | 100.0 |
| sl:group:fats_oils | 0 | 73 | 85 | 3 | 210 | 0 | 371 | 42.6 |
| sl:group:fermented_preserved | 0 | 51 | 54 | 0 | 0 | 0 | 105 | 100.0 |
| sl:group:fruits | 0 | 282 | 256 | 3 | 291 | 0 | 832 | 64.7 |
| sl:group:fungi | 0 | 63 | 20 | 0 | 42 | 0 | 125 | 66.4 |
| sl:group:herbs_spices_condiments | 0 | 257 | 211 | 66 | 348 | 0 | 882 | 53.1 |
| sl:group:legumes | 0 | 367 | 192 | 0 | 137 | 0 | 696 | 80.3 |
| sl:group:meat | 0 | 1213 | 808 | 72 | 260 | 1 | 2354 | 85.9 |
| sl:group:nuts_seeds | 0 | 146 | 63 | 0 | 102 | 0 | 311 | 67.2 |
| sl:group:poultry | 0 | 232 | 184 | 51 | 59 | 0 | 526 | 79.1 |
| sl:group:prepared_dishes | 0 | 85 | 61 | 0 | 864 | 0 | 1010 | 14.5 |
| sl:group:processed_products | 0 | 57 | 166 | 76 | 973 | 0 | 1272 | 17.5 |
| sl:group:seafood | 0 | 273 | 115 | 0 | 239 | 10 | 637 | 60.9 |
| sl:group:sugars_sweeteners | 0 | 82 | 134 | 1 | 369 | 0 | 586 | 36.9 |
| sl:group:tubers_roots | 0 | 49 | 138 | 7 | 5 | 0 | 199 | 94.0 |
| sl:group:vegetables | 0 | 315 | 393 | 23 | 342 | 0 | 1073 | 66.0 |
| unknown | 0 | 0 | 0 | 60 | 2999 | 2 | 3061 | 0.0 |
| TOTAL | 0 | 4325 | 3767 | 378 | 7931 | 13 | 16414 | 49.3 |

## Por idioma da descrição original

| language | mapped_reviewed | mapped_high_confidence | mapped_low_confidence | ambiguous | unmapped | excluded_with_reason | total | % mapeado |
|---|---|---|---|---|---|---|---|---|
| en | 0 | 3753 | 3754 | 378 | 7919 | 13 | 15817 | 47.5 |
| pt | 0 | 572 | 13 | 0 | 12 | 0 | 597 | 98.0 |
| TOTAL | 0 | 4325 | 3767 | 378 | 7931 | 13 | 16414 | 49.3 |

## Por regra

| regra | registros |
|---|---|
| no_lexical_match | 6708 |
| lexical_segments | 1801 |
| lexical_head_match_unexplained_modifier | 1680 |
| lexical_segments_unexplained_subtype | 1595 |
| curated | 1589 |
| category_only | 995 |
| lexical_name_with_qualifiers | 641 |
| lexical_ambiguous | 378 |
| lexical_exact_name | 344 |
| lexical_segments_extended | 338 |
| derived_product | 203 |
| lexical_segments_compound | 56 |
| lexical_source_synonym | 47 |
| composite_record | 13 |
| curated_exclusion | 13 |
| curated_related | 12 |
| lexical_name_with_qualifiers_compound | 1 |

## Confiança dos registros mapeados

| faixa | registros |
|---|---|
| <0.50 | 0 |
| 0.50–0.69 | 1723 |
| 0.70–0.85 | 2044 |
| 0.85–0.89 | 733 |
| ≥0.90 | 3592 |

## Base da classificação por grupo

| base | registros |
|---|---|
| entity | 8092 |
| source_group | 3106 |
| none | 3061 |
| candidates | 1326 |
| keyword | 829 |

## Entidades curadas por grupo alimentar

| grupo | entidades |
|---|---|
| sl:group:beverages | 31 |
| sl:group:cereals | 104 |
| sl:group:dairy | 97 |
| sl:group:eggs | 17 |
| sl:group:fats_oils | 20 |
| sl:group:fermented_preserved | 18 |
| sl:group:fruits | 114 |
| sl:group:fungi | 15 |
| sl:group:herbs_spices_condiments | 57 |
| sl:group:legumes | 136 |
| sl:group:meat | 123 |
| sl:group:nuts_seeds | 21 |
| sl:group:poultry | 41 |
| sl:group:prepared_dishes | 70 |
| sl:group:processed_products | 20 |
| sl:group:seafood | 125 |
| sl:group:sugars_sweeteners | 28 |
| sl:group:tubers_roots | 24 |
| sl:group:vegetables | 105 |

## Fila de curadoria — cabeças de nome mais frequentes

Registros `unmapped`, `ambiguous` e `mapped_low_confidence` (prioridade sugerida).

| cabeça do nome | registros |
|---|---|
| beef | 380 |
| beverage | 237 |
| babyfood | 236 |
| pork | 180 |
| fish | 172 |
| soup | 166 |
| snack | 148 |
| candy | 136 |
| lamb | 126 |
| chicken | 121 |
| cereal ready | 108 |
| fast food | 106 |
| infant formula | 100 |
| potato | 82 |
| cooky | 80 |
| cereal | 80 |
| turkey | 70 |
| alcoholic beverage | 66 |
| bread | 62 |
| oil | 62 |
| salad dressing | 60 |
| restaurant | 59 |
| game meat | 59 |
| sauce | 51 |
| yogurt | 49 |
| cracker | 48 |
| pudding | 48 |
| ice cream | 47 |
| seed | 46 |
| nut | 45 |
| mcdonald s | 45 |
| cake | 44 |
| milk | 42 |
| pepper | 40 |
| bean | 37 |
| sausage | 36 |
| veal | 35 |
| pie | 29 |
| margarine like | 28 |
| whole wheat | 26 |
