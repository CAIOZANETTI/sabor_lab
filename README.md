# science_spice

Banco de dados experimental de **sabores em nível molecular**: ingredientes,
as moléculas que eles contêm e os descritores sensoriais dessas moléculas.
O objetivo é encontrar relações entre sabores para elaborar e testar novos
pratos.

A ideia central (hipótese do *food pairing*, Ahn et al. 2011): ingredientes
que **compartilham moléculas aromáticas** tendem a combinar. Somamos a isso o
que **cozinheiros de verdade combinam** em mais de 1 milhão de receitas
(FlavorGraph).

## Estrutura

```
data/
  raw/
    flavordb/entities.jsonl.gz   FlavorDB2 bruto (1 JSON por ingrediente)
    flavorgraph/*.csv            FlavorGraph bruto (nós e arestas do grafo)
  processed/                     tabelas unificadas (geradas pelo build)
  experiments/                   seus testes de receitas (modelo)
  SOURCES.md                     fontes, licenças e citações
flavorlab/                       pacote Python (análise + relatório)
  db.py                          carrega o banco, resolve nomes, perfis moleculares
  analysis.py                    química (Jaccard), prática (NPMI), sugestões
  report.py                      relatório HTML interativo (plotly)
scripts/
  download_flavordb.py           baixa o FlavorDB2 (lento, retomável)
  download_flavorgraph.py        baixa o FlavorGraph
  build_database.py              monta data/processed/
  recipe_report.py               gera reports/<receita>.html
reports/                         relatórios gerados
```

## Reconstruir do zero

```bash
python scripts/download_flavorgraph.py
python scripts/download_flavordb.py      # ~2 h, 1 requisição/s, retomável
python scripts/build_database.py
```

Requer `pip install -r requirements.txt` (pandas, numpy, plotly, networkx).

## Tabelas em `data/processed/`

| Arquivo | Uma linha por | Colunas principais |
|---|---|---|
| `ingredients.csv` | ingrediente | `ingredient_id`, `source`, `name`, `category`, `scientific_name`, `n_molecules` |
| `molecules.csv` | molécula | `pubchem_id`, `name`, `smiles`, `molecular_weight`, `xlogp`, `flavor_profile`, `odor`, `taste`, `functional_groups` |
| `ingredient_molecules.csv` | ingrediente × molécula | `ingredient_id`, `pubchem_id`, `source` |
| `molecule_descriptors.csv` | molécula × descritor | `pubchem_id`, `descriptor` (ex.: *woody*, *sweet*, *pungent*), `origin` |
| `ingredient_pairs.csv` | par de ingredientes | `ingredient_a`, `ingredient_b`, `npmi_score` (co-ocorrência em receitas, −1 a 1) |
| `ingredient_crosswalk.csv` | ingrediente nas duas fontes | `fdb_id`, `fg_id`, `matched_name` |

**Chaves de ligação**

- `ingredient_id`: `fdb:<id>` (FlavorDB) ou `fg:<id>` (FlavorGraph).
- `pubchem_id`: identificador PubChem da molécula, **comum às duas fontes** —
  é por ele que o banco se conecta (e que se pode buscar mais dados no PubChem).

Algumas colunas úteis para engenharia de sabor:

- `xlogp` — lipofilicidade: valores altos indicam molécula solúvel em
  **gordura** (aroma que "abre" quando a especiaria é frita no óleo).
- `molecular_weight` — moléculas leves tendem a ser mais **voláteis**
  (perdem-se com cozimento longo; adicionar no fim).
- `functional_groups` — família química (terpeno, fenol, aldeído, pirazina...).

## Embasamento científico de uma receita

```bash
python scripts/recipe_report.py                     # todas as receitas de data/experiments/
python scripts/recipe_report.py --recipe EX02       # uma receita
python scripts/recipe_report.py --ingredients "tomato,basil,garlic" --name "teste"
python scripts/recipe_report.py --search pepper     # achar o nome certo no banco
```

O relatório (`reports/<recipe_id>.html`) mostra:

- **Rede de sabor** — ingredientes ligados pelas moléculas que compartilham
  (passe o mouse: aroma, peso molecular, xlogP) e pelos pares associados em receitas.
- **Química × Prática** — dois mapas de calor por par de ingredientes:
  - *Química*: Jaccard = moléculas em comum / moléculas no total (0–1).
  - *Prática*: NPMI do FlavorGraph — associação **acima do acaso** em >1 milhão
    de receitas. Ingredientes onipresentes (alho, cebola) têm NPMI baixo mesmo
    aparecendo juntos sempre; 0 = "sem associação especial".
- **Perfil sensorial** — quais notas (doce, amadeirado, picante…) cada ingrediente traz.
- **Moléculas-ponte** — presentes em 2+ ingredientes, priorizando as mais
  específicas (raras no banco), que dão a "assinatura" da combinação.
- **O que acrescentar** — sugestões *clássicas* (prática), *químicas* e
  *ousadas* (química alta, sem associação em receitas: território a explorar).

Ingredientes sem moléculas próprias (ex.: `ground_cinnamon`) herdam as do
ingrediente base (`cinnamon`); o relatório avisa quando isso acontece.

Uso em Python/notebook:

```python
from flavorlab import FlavorDB, analyze_recipe
db = FlavorDB()
a = analyze_recipe(db, ["cinnamon", "clove", "orange"])
a.pairs; a.bridges; a.profile; a.suggestions["ousadas"]
```

## Seus experimentos (`data/experiments/`)

Registre aqui as receitas que você fez e gostou (EX01 e EX02 são exemplos — pode apagar):

- `receitas.csv` — uma receita por linha: data, nome, técnica, nota 1–5,
  **por que gostei**, observações.
- `receita_ingredientes.csv` — ingredientes de cada receita: nome em português
  (`ingrediente`), **nome no banco em inglês** (`nome_no_banco`, ex.: `black_pepper`
  — use `--search` para achar), quantidade, preparo (cru/tostado/moído/frito no
  óleo) e momento de adição.

## Fontes

Ver [`data/SOURCES.md`](data/SOURCES.md). FlavorDB é **CC BY-NC-SA 3.0**
(não comercial); FlavorGraph é **Apache 2.0**.
