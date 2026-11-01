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
scripts/
  download_flavordb.py           baixa o FlavorDB2 (lento, retomável)
  download_flavorgraph.py        baixa o FlavorGraph
  build_database.py              monta data/processed/
```

## Reconstruir do zero

```bash
python scripts/download_flavorgraph.py
python scripts/download_flavordb.py      # ~2 h, 1 requisição/s, retomável
python scripts/build_database.py
```

Requer apenas `pandas` e `numpy`.

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

## Seus experimentos (`data/experiments/`)

Modelo inicial para registrar testes de receitas — a proposta é discutir e
ajustar antes de usar:

- `receitas.csv` — um teste por linha (data, prato, técnica, nota 1–5).
- `receita_ingredientes.csv` — ingredientes de cada teste, com quantidade,
  preparo (cru/tostado/moído/frito no óleo) e momento de adição; a coluna
  `ingredient_id` liga ao banco molecular.

## Fontes

Ver [`data/SOURCES.md`](data/SOURCES.md). FlavorDB é **CC BY-NC-SA 3.0**
(não comercial); FlavorGraph é **Apache 2.0**.
