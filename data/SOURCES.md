# Fontes de dados e licenças

O **código** deste repositório é MIT (ver `LICENSE`). Os **dados** mantêm a
licença de cada fonte:

| Fonte | O que traz | Licença | Arquivos aqui | Como obter |
|---|---|---|---|---|
| **FlavorDB2** (CosyLab, IIIT-Delhi) | ~936 ingredientes naturais, ~2,3 mil moléculas de sabor, propriedades físico-químicas e descritores de odor/sabor | **CC BY-NC-SA 3.0**: atribuição, **não comercial**, compartilha igual | `data/raw/flavordb/`, tabelas de sabor em `data/processed/*.parquet` | `python scripts/download_flavordb.py` |
| **FlavorGraph** (Park et al., Korea Univ./Sony AI) | 6.653 ingredientes de >1 milhão de receitas (Recipe1M) + 1.645 compostos; co-ocorrência (NPMI) | **Apache 2.0** | `data/raw/flavorgraph/` | `python scripts/download_flavorgraph.py` |
| **USDA FoodData Central** (SR Legacy 2018-04 + Foundation Foods 2025-12) | 8.229 alimentos, ~150 nutrientes (inclui açúcares), porções em gramas | **Domínio público (CC0 1.0)** | `data/processed/nutrition/` (bruto fora do git) | `python scripts/download_nutrition.py` |
| **TACO 4ª ed.** (NEPA/UNICAMP, 2011) | 597 alimentos brasileiros: energia, macronutrientes, fibra, minerais, vitaminas, ácidos graxos, aminoácidos | Reprodução permitida com citação da fonte (folha de rosto da publicação) | `data/raw/taco/`, `data/processed/nutrition/` | idem |
| **POF 2008-2009, Medidas Referidas** (IBGE) | ~7,9 mil medidas caseiras (colher, xícara, unidade, fatia...) em gramas | Dado público do IBGE, com citação | `data/raw/taco/pof_medidas_caseiras.csv` | idem |
| **brolesi/taco** (F. F. Brolesi) | normalização da TACO e da POF em CSV | **MIT** (ver `data/raw/taco/LICENSE-brolesi-taco`) | `data/raw/taco/` | idem (commit fixado) |

**Consequências práticas**
- O repositório pode ser **público**.
- Qualquer uso dos dados de **sabor** (derivados do FlavorDB) precisa ser
  **não comercial**, citar a fonte e manter a licença CC BY-NC-SA 3.0.
- Os dados **nutricionais** (USDA, TACO e IBGE) não têm essa restrição; basta
  citar as fontes.
- Para um produto comercial, seria preciso retirar o FlavorDB ou obter licença
  dos autores.

## Catálogo canônico de alimentos

`data/catalog/` organiza os registros das fontes acima em conceitos, variedades,
partes e formas com proveniência e confiança. Detalhes de licença por arquivo em
`data/catalog/SOURCES.md`; pesquisa de fontes candidatas (FoodOn, Wikidata, Open
Food Facts, COL, GRIN, ASFIS...) em `docs/research/ingredient-taxonomy-sources.md`.
Nenhuma base nova foi importada.

## Decisões de tratamento (nutrição)

- Valores por **100 g de parte comestível**, em unidades **métricas** (g, mg, µg, kcal, kJ).
- Nutrientes do USDA em **UI** (vitaminas A e D) foram descartados. O USDA já
  traz os equivalentes métricos: vitamina A em µg RAE e vitamina D em µg.
- TACO: "Tr" (traço) vira 0 com a marcação `traco=True`. Célula vazia significa
  "não analisado" (NaN).
- TACO não mede **açúcares**: o dicionário de ingredientes liga cada alimento
  da TACO a um equivalente do USDA, que preenche só as lacunas.
- Porções do USDA (cup, tbsp, oz, lb…) foram convertidas para g e ml, com
  descrição em português. As medidas americanas usam as definições exatas
  (1 cup = 236,5882365 ml; 1 oz = 28,349523125 g).

## FooDB (opcional, download manual)

O site `foodb.ca` bloqueia downloads automatizados. Para incluir: baixe o
pacote CSV em <https://foodb.ca/downloads> no navegador e extraia em
`data/raw/foodb/`, pasta que fica fora do git. Uso comercial exige permissão.

## Citações

- Garg N. et al. *FlavorDB: a database of flavor molecules.* Nucleic Acids
  Research 46, D1210–D1216 (2018). <https://cosylab.iiitd.edu.in/flavordb2/>
- Park D. et al. *FlavorGraph: a large-scale food-chemical graph for
  generating food representations and recommending food pairings.*
  Scientific Reports 11, 931 (2021). <https://github.com/lamypark/FlavorGraph>
- Ahn Y.-Y. et al. *Flavor network and the principles of food pairing.*
  Scientific Reports 1, 196 (2011).
- U.S. Department of Agriculture, Agricultural Research Service. *FoodData
  Central*, 2019–2025. <https://fdc.nal.usda.gov>
- NEPA/UNICAMP. *Tabela Brasileira de Composição de Alimentos (TACO)*. 4ª ed.
  Campinas: NEPA-UNICAMP, 2011.
- IBGE. *Pesquisa de Orçamentos Familiares 2008-2009: Tabela de Medidas
  Referidas para os Alimentos Consumidos no Brasil*. Rio de Janeiro, 2011.
- Brolesi F. F. *TACO: repositório para acesso facilitado aos dados da TACO e
  POF*. <https://github.com/brolesi/taco> (DOI 10.5281/zenodo.22145839)
- ANVISA. *Instrução Normativa nº 75/2020* (valores diários de referência).
