# Nutrição após preparo (demanda 007)

`flavorlab/prepared_nutrition.py` calcula os nutrientes da porção **servida**. O cálculo
distingue o alimento cru, o alimento preparado com composição medida e a estimativa
derivada do preparo. A API antiga (`NutritionDB.recipe`) não muda. O cálculo novo só
aparece quando a receita informa o estado ou o método de preparo.

## Saída: medido, derivado, estimado e desconhecido

| categoria | quando | exemplo |
|---|---|---|
| `measured` | composição oficial do alimento **no estado servido** (mesma entidade, método igual ou compatível) × massa pesada ou informada | fraldinha cozida da TACO servida cozida em água |
| `derived` | cálculo com fator documentado: rendimento USDA, variação de água e gordura, retenção USDA, energia ajustada pela gordura perdida, massa cozida obtida pelo rendimento de tabela | tiamina do bife grelhado = cru × 0,80 |
| `estimated` | aproximação declarada: macronutriente transportado sem fator, gordura sem dado de perda ou absorção, registro preparado por outro método | proteína do frango assado; fraldinha "cozida" usada para air fryer |
| desconhecido | sem dado e sem convenção aplicável; fica em `unknown_nutrients` e **nunca vira zero** | sódio de hortaliça fervida com a água descartada, sem fator |

`PreparedNutritionResult` traz `measured_values`, `derived_values`, `estimated_values` e
`unknown_nutrients`. Um nutriente aparece em uma única dessas listas. Também traz:

- `nutrient_totals`, com os três primeiros grupos juntos;
- `notes`, que explicam como cada valor foi obtido;
- os `EvidenceClaim` (demanda 005) do registro usado, das massas, do rendimento, de cada
  retenção e de cada total servido.

Na receita (`PreparedRecipeResult`), a categoria de um total é a **mais fraca** entre os
itens que contribuem para ele. Se um nutriente é desconhecido em algum item, o total fica
em `partial`, com a lista desses itens.

## Algoritmo

1. **Registro e estado.** `NutritionDB.lookup` acha o registro; o estado (`raw`/`cooked`) e o
   método vêm da forma do catálogo (002). Sem forma, vêm das palavras do nome ("cru",
   "grelhado", "cooked, broiled"…). Sem indício, o estado fica `unknown` e o registro é
   tratado como estado inicial, com aviso.
2. **Registro já preparado.** A composição é usada como está. **Nenhum fator é aplicado de
   novo** (proteção contra dupla contagem).
   - Se o método do registro difere do informado, os valores viram `estimated`.
   - Massa crua em registro preparado é recusada.
   - Sem peso cru, `yield_status = not_reconstructible`. Nenhum rendimento de tabela é
     usado para inventar o peso cru.
3. **Registro cru com método.** Procura primeiro um registro preparado medido da mesma
   entidade:
   - o registro cozido do mesmo estudo de rendimento da USDA;
   - ou uma forma irmã do catálogo com método compatível.

   Se existir e houver massa cozida (pesada ou obtida pelo rendimento de tabela), ele vence
   a estimativa.
4. **Derivação a partir do cru** (método do fator de retenção):
   - **retenção:** nutriente a nutriente, só quando há regra aplicável;
   - **água e gordura:** separadas;
   - **energia:** ajustada pelo Atwater geral.
5. **Massas.** O rendimento observado (pesagem antes e depois) tem precedência sobre o de
   tabela. A massa servida é uma fração do lote e não pode passar dele.
6. **Porções.** `prepared_recipe(..., portions=n)` divide o total. `shares={"Ana": 200}`
   reparte por pessoa em gramas servidos. Se as porções somam mais que o prato, há erro; a
   sobra é informada. As necessidades individuais ficam para a demanda 001.

## Fórmulas e bases

Notação: `N` = nutriente por 100 g, `M` = massa (g), `cru` = antes do preparo.

| grandeza | fórmula | base |
|---|---|---|
| rendimento | `Y = M_cozido / M_cru` | massa crua (USDA: `100 × Wch/Wcr`) |
| massa cozida | `M_cozido = M_cru × Y` | massa crua |
| total retido | `T = N_cru × M_cru / 100 × R` | massa crua; `R` = retenção verdadeira (%TR/100) |
| água | `T_água = N_água,cru × M_cru/100 + Δágua`, com `Δágua = %umidade/100 × M_cru` | massa crua |
| gordura | `T_gord = N_gord,cru × M_cru/100 + Δgord`, com `Δgord = %gordura/100 × M_cru` | massa crua |
| energia | `E = E_cru + 9 × Δgord` (+ `7 × Δálcool`); kJ = kcal × 4,184 | Atwater geral |
| concentração | `N_servido = T / M_cozido × 100` | massa cozida |
| porção | `T_porção = T × M_servida / M_cozido` | massa servida |
| redução | `Δágua = M_cozido − M_cru`, `Δgord = 0` | método britânico (EuroFIR §3.2) |

Consequência testada: na redução de 1.000 g para 600 g, a proteína total fica igual e a
concentração por 100 g sobe 1/0,6 vezes.

Regras de transporte sem fator:

- **Macronutrientes** (proteína, carboidratos, açúcares, fibra, amido, cinzas) entram como
  `estimated`. A USDA não publica retenção para eles, e Bognár (2002) documenta perdas.
- **Minerais** só entram como `estimated` quando o líquido não é descartado (convenção do
  EPIC, EuroFIR §3.7). Com descarte, a própria USDA mostra perdas por lixiviação, então ficam
  desconhecidos.
- **Frações de gordura e colesterol** ficam desconhecidas quando a gordura total muda: o
  perfil do que se perdeu não é conhecido.
- **Componente zero no cru** continua zero, porque retenção ≤ 1 não cria nutriente.
- **Ganho de massa em cocção úmida** (arroz, massa) é atribuído à água.

## Gordura de fritura

`FatTransfer(absorbed_g, lost_g, method, source_food)` registra a gordura absorvida e a perdida.
Valor `None` significa desconhecido.

- Seguindo EuroFIR (§3.6 e §4.4), só a gordura **absorvida** entra na porção, com a
  composição do óleo ou da manteiga indicada.
- Em fritura sem `absorbed_g`, nada é somado e há aviso de que gordura e energia podem
  estar subestimadas.
- `lost_g` medido substitui a variação de gordura da tabela.

## Dados (`data/cooking_factors/`)

| arquivo | conteúdo | origem |
|---|---|---|
| `retention_factors.csv` | 7.018 fatores (270 códigos × 26 componentes); 4.319 com nutriente equivalente no banco | USDA Retention Factors R6 (2007), gerado |
| `cooking_yields.csv` | 173 rendimentos com DP, faixa, n e Δágua/Δgordura; 162 ligados ao registro cozido medido e 93 ao cru | USDA Cooking Yields R2 (2014), gerado |
| `methods.csv` | métodos do cálculo, família térmica e aliases para técnicas (003) e `cooking_method` (005) | curadoria |
| `retention_map.csv` | 270 regras entidade × método → código USDA, com condições e nível `specific`/`group` | curadoria |

Os arquivos brutos (domínio público) ficam em `data/raw/usda_factors/`. Para regenerar:

```bash
python scripts/build_cooking_factors.py
```

Para conferir sem regenerar:

```bash
python scripts/build_cooking_factors.py --check
```

O script também gera `reports/fatores_preparo_cobertura.md`, com a cobertura por alimento e
técnica e a lista de fatores ausentes.

Na escolha da regra de retenção, a entidade do catálogo mais específica vence (o próprio
alimento, depois os ancestrais). Condições como `liquid=discarded`, `peeled=yes`,
`raw_fat_g<5` e `duration_min>=45` só selecionam o fator quando a fonte faz a distinção.
Se a condição não foi informada, nenhum fator é escolhido e o aviso diz o que falta.

As regras de **grupo** têm confiança `low`, limitação declarada e aviso. Um exemplo é
"BEEF, BROILED CUT" aplicado a qualquer corte bovino.

## Comparação de fontes

| fonte | conteúdo | licença | uso aqui |
|---|---|---|---|
| USDA Retention Factors R6 (2007) | %TR de vitaminas, minerais e álcool; ~290 categorias e métodos; arredondado a 5%, máx. 100% | domínio público | fatores de retenção (importados inteiros) |
| USDA Cooking Yields R2 (2014) | rendimento, n, DP, faixa, Δágua e Δgordura (% do peso cru) de carnes e aves; linhas de 1975 vêm do AH-102, sem água e gordura | domínio público | rendimento e balanço de água e gordura |
| EuroFIR D2.2.12 (Reinivuo & Laitinen 2007) | comparação de métodos de cálculo (INFOODS, britânico, fator de rendimento, fator de retenção, Bognár, EPIC) | documento de projeto, sem licença aberta | fórmulas e convenções (redução, minerais, gordura de fritura) |
| Bognár (2002), BFE-R-02-03 | rendimento de ~700 alimentos; retenção, inclusive de macronutrientes | sem licença aberta declarada | citado; dados **não** importados |
| FAO/INFOODS, "Recipe and other calculations" (2021) | definições; métodos por ingrediente, receita total e misto; erros comuns | © FAO | definições e o princípio de não trocar faltante por zero |

As fontes estão em `data/knowledge/sources.csv`, com URL, versão e data de acesso.

## Casos obrigatórios

| caso | resultado |
|---|---|
| cru com rendimento conhecido | flank USDA cru, 500 g, grelhado: `Y = 0,81` (n = 20, DP 4,1), massa cozida de 405 g, registro grelhado medido do mesmo estudo |
| cozido já medido | o registro preparado não recebe rendimento nem retenção; o aviso registra a proteção |
| redução de água | o total se conserva e a concentração sobe; a água cai pela massa evaporada |
| fritura sem absorção conhecida | aviso; gordura e energia `estimated`; o óleo não é somado |
| fraldinha servida (350 g), sem peso cru | composição da TACO "fraldinha cozida" como `estimated`, porque o método difere (cocção úmida × air fryer); `not_reconstructible`; o flank da USDA não é usado |
| porções por pessoa | `shares` em gramas servidos; soma das porções + sobra = prato |

## Lacunas

- Não há fator de rendimento nem de retenção para air fryer, panela de pressão ou redução.
  O micro-ondas só tem rendimento, e para um único item (bacon).
- Rendimentos de tabela existem só para carnes e aves. Nos demais alimentos, é preciso pesar
  antes e depois.
- A USDA não tem fator de retenção para vitamina A em RAE (só em UI ou RE), carotenoides
  individuais nem colina.
- Leguminosas só têm fator nas faixas de tempo da USDA.
- A lista completa está em `reports/fatores_preparo_cobertura.md`.
