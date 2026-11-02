# SaborLab

Banco de dados experimental de **sabor e nutrição** dos alimentos, para
elaborar e testar receitas com embasamento científico.

O nome público do projeto é **SaborLab**: sabor molecular, nutrição e cultura
para criar receitas calculadas. A visão completa do produto é publicada na
página `site/sobre.html`.

- **Sabor, em nível molecular:** que moléculas aromáticas cada ingrediente tem
  e quais ingredientes compartilham moléculas. É a hipótese do *food pairing*
  (Ahn et al. 2011): ingredientes que compartilham moléculas tendem a combinar.
  Somamos a isso o que cozinheiros de fato combinam em mais de 1 milhão de
  receitas (FlavorGraph).
- **Nutrição:** energia, proteínas, carboidratos, açúcares, gorduras, fibra,
  sódio, vitaminas e minerais de cada ingrediente (TACO e USDA), somados para a
  receita inteira e por porção, com %VD da ANVISA.
- **Tudo em português e no sistema métrico:** você escreve "2 colheres de sopa
  de azeite" ou "1 cup flour" e o sistema converte para gramas. Unidades
  imperiais (cup, tbsp, oz, lb, °F, inch) são sempre convertidas.

## Estrutura

```
data/
  raw/                           dados brutos (USDA fica fora do git: re-baixável)
    flavordb/entities.jsonl.gz   FlavorDB2 (1 JSON por ingrediente)
    flavorgraph/*.csv            FlavorGraph (nós e arestas do grafo)
    taco/*.csv                   TACO 4ª ed. + medidas caseiras POF/IBGE
  processed/                     tabelas de sabor em Parquet
    nutrition/                   tabelas de nutrição em Parquet
  dicionario_ingredientes.csv    nomes em português -> sabor + nutrição (82 itens)
  ingredient_aliases.csv         apelidos curados com justificativa
  catalog/                       catálogo canônico de alimentos (conceitos, variedades,
                                 partes, formas, táxons, mapeamentos) + inventário das fontes
  experiments/                   suas receitas
  SOURCES.md                     fontes, licenças e citações
flavorlab/                       pacote Python
  db.py                          banco de sabores: nomes, perfis moleculares
  analysis.py                    química (Jaccard), prática (NPMI), sugestões
  nutrition.py                   banco nutricional, conversão de unidades, cálculo
  catalog.py                     catálogo canônico: tipos, validação e API de consulta
  catalog_mapping.py             inventário das fontes e mapeamento lexical conservador
  units.py                       unidades métricas/imperiais, °F->°C, polegadas->cm
  report.py, nutrition_report.py relatório HTML interativo (vis-network + plotly)
scripts/                         download, build e relatório
reports/                         relatórios gerados
tests/                           testes automatizados (pytest)
```

## Instalação e reconstrução

```bash
pip install -r requirements.txt          # pandas, numpy, pyarrow, plotly

# sabor
python scripts/download_flavorgraph.py
python scripts/download_flavordb.py      # ~2 h, 1 requisição/s, retomável
python scripts/build_database.py

# nutrição
python scripts/download_nutrition.py     # USDA (~10 MB) + TACO/POF
python scripts/build_nutrition.py
```

Testes: `pip install -r requirements-dev.txt && pytest`. A maioria usa bancos
sintéticos com respostas conhecidas; há também verificações no banco real,
como "1 cup de farinha = 125 g" e "nenhuma unidade imperial sobrando".

## Publicação na web

O workflow `.github/workflows/pages.yml` testa o projeto, regenera os relatórios
e publica um site estático no GitHub Pages a cada atualização da branch `main`.
Não é necessário manter um servidor Python em execução.

Para conferir o mesmo artefato localmente:

```bash
python scripts/recipe_report.py
python scripts/build_site.py --output _site
python -m http.server 8000 --directory _site
```

No GitHub, selecione **Settings → Pages → Source: GitHub Actions** uma única vez.
Depois disso, a publicação é automática e também pode ser iniciada manualmente
na aba **Actions**.

## Suas receitas (`data/experiments/`)

`receitas.csv`, com uma receita por linha:

| coluna | exemplo |
|---|---|
| `recipe_id` | R001 |
| `nome`, `data`, `tecnica` | "forno a 350°F" vira "forno a 177 °C" no relatório |
| `porcoes` | 4 (divide os nutrientes) |
| `nota_geral`, **`por_que_gostei`**, `observacoes` | texto livre |

`receita_ingredientes.csv`, com um ingrediente por linha:

| coluna | exemplo | observação |
|---|---|---|
| `ingrediente` | canela | **em português**, resolvido pelo dicionário |
| `quantidade` | 2, 1/2, 2 1/4, 0,5 | aceita frações e vírgula |
| `unidade` | g, kg, ml, l, xícara, colher de sopa, colher de chá, unidade, dente, fatia, folha, pitada, cup, tbsp, tsp, oz, lb, fl oz | |
| `gramas` | 3 | opcional: vale sobre quantidade+unidade (ex.: "1 pau de canela") |
| `preparo`, `momento`, `observacoes` | tostado, início | texto livre |
| `nome_no_banco` | black_pepper | opcional: força o ingrediente de sabor |
| `alimento` | taco:157, usda:170457 | opcional: força o alimento nutricional |

Gerar os relatórios:

```bash
python scripts/recipe_report.py                     # todas as receitas
python scripts/recipe_report.py --recipe R001       # uma receita
python scripts/recipe_report.py --search-food "queijo minas"   # achar alimento (nutrição)
python scripts/recipe_report.py --search pepper     # achar ingrediente (sabor, inglês)
```

EX01 (molho de tomate), EX02 (chai) e EX03 (cookies americanos, em unidades
imperiais) são exemplos e podem ser apagados.

## O relatório (`reports/<recipe_id>.html`)

**Nutrição**
- Destaques por porção: kcal, proteínas, carboidratos, açúcares, gorduras,
  fibra e sódio.
- Tabela por ingrediente com a **conversão usada para chegar aos gramas**, por
  exemplo "45 ml × densidade 0,91 g/ml" ou "medida caseira IBGE: dente = 4,4 g".
- Energia por ingrediente e origem da energia (proteína/carboidrato/gordura).
- **%VD** por porção (ANVISA, IN 75/2020, dieta de 2.000 kcal).

**Sabor**
- **Rede de sabor interativa:** ingredientes ligados pelas moléculas que
  compartilham e pelos pares associados em receitas. Dá para arrastar, dar zoom,
  clicar para destacar as conexões, buscar e filtrar por **nota de sabor**
  (woody, citrus, spicy…).
- **Química × prática:**
  - *Jaccard*: moléculas em comum sobre o total, de 0 a 1.
  - *NPMI*: associação acima do acaso em receitas, de 0 a 1.
- **Perfil sensorial**, **moléculas-ponte** e sugestões **clássicas, químicas e
  ousadas** do que acrescentar.

Todas as tabelas são ordenáveis com um clique no cabeçalho.

## Como cada ingrediente é resolvido

1. **Dicionário** (`data/dicionario_ingredientes.csv`): nome em português →
   ingrediente de sabor + alimento nutricional (TACO de preferência) +
   complemento USDA (preenche o que a TACO não mede, como açúcares) + nome nas
   medidas caseiras do IBGE. Acentos e maiúsculas são ignorados.
2. Fora do dicionário: busca automática na TACO/USDA, com aviso "confira".
3. **Sabor sem moléculas próprias** herda de um ingrediente base, sempre com aviso:
   - apelidos curados com justificativa (`olive_oil → olive`);
   - heurística (`ground_cinnamon → cinnamon`), que respeita o gênero botânico.
     "chili/bell pepper" vão para *Capsicum*, "black pepper" para *Piper*, e
     "sichuan pepper" fica sem dados em vez de herdar algo errado.

**Conversão para gramas:**
- massa (g, kg, oz, lb) converte direto;
- volume (ml, xícara, cup, tbsp…) é multiplicado pela **densidade do próprio
  alimento**, derivada das porções do USDA (azeite 0,91 g/ml, farinha 0,53 g/ml);
  sem densidade, usa a medida caseira do IBGE; em último caso, 1 g/ml, com aviso;
- unidade/dente/fatia/folha usam as medidas do IBGE ou as porções do USDA.

As medidas brasileiras usam xícara = 240 ml, colher de sopa = 15 ml e colher de
chá = 5 ml. As americanas usam as definições exatas: cup = 236,6 ml,
tbsp = 14,8 ml, tsp = 4,9 ml, oz = 28,35 g, lb = 453,6 g.

## Catálogo canônico de alimentos (`data/catalog/`)

Camada que organiza **todos** os registros das fontes (TACO, USDA, FlavorDB e
FlavorGraph) em entidades com IDs estáveis (`sl:ingredient:rice`,
`sl:variant:rice_basmati`, `sl:part:atlantic_salmon_fillet`,
`sl:form:common_bean_black_raw`), separando conceito, variedade/tipo, parte/corte,
forma (estado, forma física, preparo) e produto/prato. Fontes, licenças e
decisões: `data/catalog/SOURCES.md` e `docs/research/ingredient-taxonomy-sources.md`.

```bash
python scripts/build_catalog.py           # valida e regenera o inventário + reports/catalog_coverage.md
python scripts/build_catalog.py --check   # falha se o inventário versionado estiver desatualizado
```

```python
from flavorlab.catalog import Catalog
cat = Catalog.load()
cat.variants("sl:ingredient:rice")             # basmati, jasmim, arbório, tipo 1...
cat.forms("sl:variant:common_bean_black")      # cru, cozido, enlatado, base seca
cat.resolve_source("taco", "568")              # Feijão, preto, cru -> forma canônica + confiança
cat.resolve_source("flavorgraph", "7043")      # "yam": ambíguo, devolve candidatos
cat.coverage(source="usda")                    # contagem por grupo e status
```

O inventário (`source_inventory.csv`) tem uma linha por registro de fonte, com
status `mapped_reviewed`, `mapped_high_confidence`, `mapped_low_confidence`,
`ambiguous`, `unmapped` ou `excluded_with_reason`. Mapeamentos abaixo de 0,85 de
confiança exigem revisão; registros não mapeados ficam na fila de curadoria.

## Tabelas

**Sabor** (`data/processed/`)

| Arquivo | Uma linha por | Colunas principais |
|---|---|---|
| `ingredients.parquet` | ingrediente | `ingredient_id` (`fdb:`/`fg:`), `name`, `category`, `scientific_name`, `n_molecules` |
| `molecules.parquet` | molécula | `pubchem_id`, `name`, `smiles`, `molecular_weight`, `xlogp`, `flavor_profile`, `functional_groups` |
| `ingredient_molecules.parquet` | ingrediente × molécula | `ingredient_id`, `pubchem_id` |
| `molecule_descriptors.parquet` | molécula × descritor | `pubchem_id`, `descriptor` (woody, sweet…) |
| `ingredient_pairs.parquet` | par de ingredientes | `ingredient_a`, `ingredient_b`, `npmi_score` |

**Nutrição** (`data/processed/nutrition/`), por 100 g e em unidades métricas

| Arquivo | Uma linha por | Colunas principais |
|---|---|---|
| `foods.parquet` | alimento (8.826) | `food_id` (`taco:`/`usda:`), `nome`, `fonte`, `categoria`, `densidade_g_ml` |
| `nutrients.parquet` | nutriente | `nutrient_key` (ex.: `acucares_g`), `nome` (português), `unidade` |
| `food_nutrients.parquet` | alimento × nutriente | `food_id`, `nutrient_key`, `valor`, `traco` |
| `portions.parquet` | porção USDA | `food_id`, `medida_pt` ("1 xícara EUA (236,6 ml) = 125 g"), `gramas`, `ml` |
| `household.parquet` | medida caseira IBGE | `alimento`, `medida` (COLHER DE SOPA, UNIDADE…), `gramas` |

Uso em Python/notebook:

```python
from flavorlab import FlavorDB, analyze_recipe
from flavorlab.nutrition import NutritionDB

a = analyze_recipe(FlavorDB(), ["canela", "cravo", "laranja"])
a.pairs; a.bridges; a.suggestions["ousadas"]

n = NutritionDB()
r = n.recipe([{"nome": "farinha de trigo", "quantidade": "2 1/4", "unidade": "cup"},
              {"nome": "manteiga", "quantidade": 1, "unidade": "cup"}], portions=12)
r.total; r.per_portion; r.vd
```

## Licença

- **Código:** MIT (ver [`LICENSE`](LICENSE)).
- **Dados:** cada fonte mantém a sua licença (ver [`data/SOURCES.md`](data/SOURCES.md)):
  - os dados de **sabor** derivados do FlavorDB são **CC BY-NC-SA 3.0** (uso
    não comercial, com atribuição);
  - USDA é domínio público;
  - TACO e IBGE exigem citação da fonte;
  - FlavorGraph é Apache 2.0.
