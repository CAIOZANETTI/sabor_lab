# Cobertura dos fatores de preparo (demanda 007)

Gerado por `python scripts/build_cooking_factors.py`. Fontes: USDA Table of Nutrient Retention Factors Release 6 (2007) e USDA Table of Cooking Yields for Meat and Poultry Release 2 (2014), ambas de domínio público. Regras de aplicação em `data/cooking_factors/retention_map.csv`.

- Retenção: 7018 fatores, 270 códigos, 4319 com nutriente equivalente no banco.
- Rendimento: 173 linhas; 162 ligadas ao registro cozido medido e 93 ao registro cru.
- Regras de retenção curadas: 270 (40 específicas, 230 de grupo, que têm baixa confiança).

## Rendimento por espécie e método

| espécie | método | rendimentos | ligados_ao_cru |
|---|---|---|---|
| Beef | (vários métodos; não aplicado) | 1 | 0 |
| Beef | boil | 4 | 4 |
| Beef | braise | 14 | 7 |
| Beef | grill_broil | 27 | 18 |
| Beef | pan_fry | 7 | 2 |
| Beef | roast_bake | 13 | 5 |
| Chicken | boil | 7 | 7 |
| Chicken | braise | 4 | 2 |
| Chicken | deep_fry | 1 | 1 |
| Chicken | pan_fry | 1 | 1 |
| Chicken | roast_bake | 8 | 7 |
| Emu | grill_broil | 1 | 1 |
| Game meat | grill_broil | 3 | 2 |
| Lamb | boil | 1 | 0 |
| Lamb | braise | 1 | 0 |
| Lamb | roast_bake | 1 | 0 |
| Ostrich | grill_broil | 1 | 1 |
| Pork | boil | 3 | 3 |
| Pork | braise | 8 | 4 |
| Pork | grill_broil | 10 | 4 |
| Pork | microwave | 1 | 0 |
| Pork | pan_fry | 13 | 5 |
| Pork | roast_bake | 22 | 4 |
| Pork loin | roast_bake | 1 | 1 |
| Pork sausage | pan_fry | 1 | 0 |
| Turkey | boil | 4 | 3 |
| Turkey | roast_bake | 10 | 6 |
| Turkey sausage | grill_broil | 1 | 1 |
| Veal | braise | 1 | 1 |
| Veal | grill_broil | 2 | 2 |
| Veal | pan_fry | 1 | 1 |

## Retenção por entidade e método

Código USDA aplicado; ᵍ = fator de grupo (baixa confiança). Vários códigos = escolha por condição (líquido descartado/consumido, casca, empanamento, teor de gordura do peixe, tempo das leguminosas).

| entidade | grill_broil | roast_bake | pan_fry | deep_fry | boil | braise | steam |
|---|---|---|---|---|---|---|---|
| almeirao | — | 3001ᵍ | 3015ᵍ | — | 3004ᵍ/3005ᵍ/3006ᵍ | — | — |
| arugula | — | 3001ᵍ | 3015ᵍ | — | 3004ᵍ/3005ᵍ/3006ᵍ | — | — |
| beef | 0602ᵍ | 0601ᵍ | 0604ᵍ/0605ᵍ | — | 0653ᵍ/0654ᵍ | 0651ᵍ/0652ᵍ | — |
| beet | — | 3451ᵍ | 3460ᵍ | — | 3454ᵍ/3455ᵍ/3456ᵍ | — | 3464ᵍ |
| bitter_orange | 0270ᵍ | 0270ᵍ | 0270ᵍ | — | 0270ᵍ | — | — |
| cabbage | — | 3001ᵍ | 3015ᵍ | — | 3004ᵍ/3005ᵍ/3006ᵍ | — | — |
| carrot | — | 3451ᵍ | 3460ᵍ | — | 3454ᵍ/3455ᵍ/3456ᵍ | — | 3464ᵍ |
| caruru | — | 3001ᵍ | 3015ᵍ | — | 3004ᵍ/3005ᵍ/3006ᵍ | — | — |
| cassava | — | 3451ᵍ | 3460ᵍ | — | 3454ᵍ/3455ᵍ/3456ᵍ | — | 3464ᵍ |
| catalonha | — | 3001ᵍ | 3015ᵍ | — | 3004ᵍ/3005ᵍ/3006ᵍ | — | — |
| chard | — | 3001ᵍ | 3015ᵍ | — | 3004ᵍ/3005ᵍ/3006ᵍ | — | — |
| cheese | 0003 | 0001 | — | — | — | — | — |
| chicken | 0801 | 0805 | 0803/0804 | 0803/0804 | 0855/0856 | 0851/0852 | — |
| chicoria | — | 3001ᵍ | 3015ᵍ | — | 3004ᵍ/3005ᵍ/3006ᵍ | — | — |
| crustaceans | 2753ᵍ | 2750ᵍ | 2755ᵍ/2756ᵍ | — | 2761ᵍ/2762ᵍ | — | 2770ᵍ |
| egg | — | 0101 | 0103 | — | 0105 | — | — |
| fish | 2305ᵍ/2455ᵍ | 2301ᵍ/2451ᵍ | 2309ᵍ/2310ᵍ/2459ᵍ/2460ᵍ | 2309ᵍ/2310ᵍ/2459ᵍ/2460ᵍ | 2401ᵍ/2402ᵍ/2551ᵍ/2552ᵍ | — | — |
| fruits | 0152ᵍ | 0151ᵍ | 0153ᵍ | — | 0155ᵍ | — | — |
| inhame | — | 3451ᵍ | 3460ᵍ | — | 3454ᵍ/3455ᵍ/3456ᵍ | — | 3464ᵍ |
| kale | — | 3001ᵍ | 3015ᵍ | — | 3004ᵍ/3005ᵍ/3006ᵍ | — | — |
| lamb | 1001ᵍ | 1004ᵍ | — | — | 1055ᵍ/1056ᵍ | — | — |
| legumes | — | — | — | — | 0501ᵍ/0502ᵍ/0521ᵍ/0522ᵍ/0541ᵍ/0542ᵍ | — | — |
| lemon | 0270ᵍ | 0270ᵍ | 0270ᵍ | — | 0270ᵍ | — | — |
| lettuce | — | 3001ᵍ | 3015ᵍ | — | 3004ᵍ/3005ᵍ/3006ᵍ | — | — |
| lime | 0270ᵍ | 0270ᵍ | 0270ᵍ | — | 0270ᵍ | — | — |
| mandioquinha | — | 3451ᵍ | 3460ᵍ | — | 3454ᵍ/3455ᵍ/3456ᵍ | — | 3464ᵍ |
| mollusks | 2753ᵍ | 2750ᵍ | 2755ᵍ/2756ᵍ | — | 2761ᵍ/2762ᵍ | — | 2770ᵍ |
| mustard_greens | — | 3001ᵍ | 3015ᵍ | — | 3004ᵍ/3005ᵍ/3006ᵍ | — | — |
| nz_spinach | — | 3001ᵍ | 3015ᵍ | — | 3004ᵍ/3005ᵍ/3006ᵍ | — | — |
| orange | 0270ᵍ | 0270ᵍ | 0270ᵍ | — | 0270ᵍ | — | — |
| pasta | — | — | — | — | 0381/0384 | — | — |
| pork | 1251ᵍ | 1254ᵍ | 1252ᵍ/1253ᵍ | — | 1301ᵍ/1302ᵍ | — | — |
| potato | — | 3301/3302 | 3315 | 3315 | 3307/3308/3309 | — | — |
| poultry | 0801ᵍ | 0805ᵍ | 0803ᵍ/0804ᵍ | 0803ᵍ/0804ᵍ | 0855ᵍ/0856ᵍ | 0851ᵍ/0852ᵍ | — |
| radish | — | 3451ᵍ | 3460ᵍ | — | 3454ᵍ/3455ᵍ/3456ᵍ | — | 3464ᵍ |
| rice | — | — | — | — | 0431/0432 | — | — |
| serralha | — | 3001ᵍ | 3015ᵍ | — | 3004ᵍ/3005ᵍ/3006ᵍ | — | — |
| spinach | — | 3001ᵍ | 3015ᵍ | — | 3004ᵍ/3005ᵍ/3006ᵍ | — | — |
| sweet_potato | — | 3701/3702 | 3710 | 3710 | 3707/3708/3709 | — | — |
| taioba | — | 3001ᵍ | 3015ᵍ | — | 3004ᵍ/3005ᵍ/3006ᵍ | — | — |
| tangerine | 0270ᵍ | 0270ᵍ | 0270ᵍ | — | 0270ᵍ | — | — |
| taro | — | 3451ᵍ | 3460ᵍ | — | 3454ᵍ/3455ᵍ/3456ᵍ | — | 3464ᵍ |
| tomato | 3752 | 3751 | 3752 | — | 3751 | — | — |
| turkey | — | 1805 | — | — | 1851/1852 | — | — |
| turnip | — | 3451ᵍ | 3460ᵍ | — | 3454ᵍ/3455ᵍ/3456ᵍ | — | 3464ᵍ |
| veal | 1951ᵍ | 1954ᵍ | 1952ᵍ/1953ᵍ | — | — | 2001ᵍ/2002ᵍ | — |
| vegetables | — | 3771ᵍ | 3785ᵍ | 3780ᵍ | 3774ᵍ/3775ᵍ/3776ᵍ | — | 3784ᵍ |
| watercress | — | 3001ᵍ | 3015ᵍ | — | 3004ᵍ/3005ᵍ/3006ᵍ | — | — |
| yam | — | 3451ᵍ | 3460ᵍ | — | 3454ᵍ/3455ᵍ/3456ᵍ | — | 3464ᵍ |

## Fatores ausentes

- Métodos sem rendimento USDA: air_fry, steam, pressure, reduce.
- Métodos sem regra de retenção: air_fry, microwave, pressure, reduce.
- Rendimento existe só para carnes e aves. Hortaliças, cereais, leguminosas e laticínios dependem de pesagem antes/depois (rendimento observado) ou de registro preparado medido.
- **Fraldinha** (`sl:part:beef_fraldinha`): sem rendimento nem registro grelhado/assado/air fryer. A TACO só traz fraldinha crua e cozida. O flank da USDA (`sl:part:beef_flank_us`) é outra entidade no catálogo e não é usado como equivalente.
- 80 linhas de rendimento sem registro cru correspondente por nome exato no SR Legacy (ex.: carne moída por faixa de gordura, cortes com osso, aves de 1975). Não são aplicadas automaticamente.
- 23 linhas de rendimento sem variação de água/gordura (16 de 1975, do AH-102, e médias agregadas de 'retail cuts' de 2011). Nelas, água e gordura cozidas ficam desconhecidas ou estimadas.
- 24 fatores em branco na própria fonte (código 5005, bebida alcoólica, só álcool informado).
- Componentes da tabela USDA sem equivalente no banco: Vitamin A, IU (vitamina A em UI (o banco usa RAE)); Carotene, beta (betacaroteno ausente no banco); Carotene, alpha (alfacaroteno ausente no banco); Cryptoxanthin, beta (betacriptoxantina ausente no banco); Lycopene (licopeno ausente no banco); Lutein + zeaxanthin (luteína + zeaxantina ausente no banco); Vitamin A, RE (vitamina A em RE (o banco usa RAE)); Choline, total (colina ausente no banco); Folic acid (ácido fólico ausente no banco (só folato total)); Folate, food (folato alimentar ausente no banco).
- Macronutrientes (proteína, carboidratos, fibra, açúcares, amido, cinzas) não têm fator na USDA. Por isso são transportados como **estimados**; Bognár (2002) mostra perdas em alguns métodos.
- Leguminosas: só há fator nas faixas de tempo da USDA (15–20 min, 45–75 min, 2–2,5 h). Panela de pressão não tem fator.
- Absorção de óleo em fritura e perda de gordura sem dado da tabela exigem medição (`FatTransfer`).
