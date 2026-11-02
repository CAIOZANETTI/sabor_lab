# Catálogo canônico de alimentos — dados, proveniência e licenças

Pesquisa completa de fontes: `docs/research/ingredient-taxonomy-sources.md`.
Fontes registradas (versão, licença, atribuição): `sources.csv`.

## Arquivos

| Arquivo | Conteúdo | Origem |
|---|---|---|
| `food_groups.csv` | 19 grupos alimentares (`sl:group:*`) | curado |
| `taxa.csv` | táxons (`sl:taxon:*`): nome científico, rank, evidência, confiança; `external_ids` vazio (pendente) | curado |
| `ingredient_concepts.csv` | conceitos (`sl:ingredient:*`): ingrediente, produto, prato, categoria ou nome comercial | curado |
| `ingredient_variants.csv` | variantes (`sl:variant:*`): classe comercial, tipo culinário, cultivar, tipo de queijo | curado |
| `culinary_parts.csv` | partes/cortes (`sl:part:*`) | curado |
| `ingredient_forms.csv` | formas (`sl:form:*`): estado, forma física, preparo, hidratação | curado |
| `relations.csv` | `derived_from`, `dish_contains`, `substitutable_with` | curado |
| `source_mappings.csv` | entidade ↔ registro de fonte (tipo SKOS, confiança, evidência, curadoria/revisão) | curado |
| `source_exclusions.csv` | registros excluídos com motivo (não alimentos, nós taxonômicos) | curado |
| `sources.csv` | fontes, datasets, versões, licenças | curado |
| `source_inventory.csv` | **ledger**: 1 linha por registro de TACO, USDA, FlavorDB e FlavorGraph | **gerado** (`scripts/build_catalog.py`) |

## Proveniência e confiança

- Toda linha curada tem `evidence`; mapeamentos têm `curated_by`/`curated_at` e
  `reviewed_by`/`reviewed_at`. Nesta versão a curadoria foi feita pelo executor
  (`claude-code`) e **nenhum mapeamento está marcado como revisado** — o estado
  `mapped_reviewed` só aparece quando `reviewed_by` é preenchido por um revisor.
- `confidence` ∈ [0, 1]. Abaixo de **0,85** o mapeamento exige revisão
  (`mapped_low_confidence`), seja curado ou automático.
- Táxons sem verificação externa trazem a evidência textual e confiança < 1.
- `unknown` é preferido a inferência: nomes comerciais multiespécie são
  `market_name` sem táxon; registros compostos não viram identidade de ingrediente.

## Licenças

- **Camada curada** (conceitos, variantes, partes, formas, relações, táxons, grupos):
  trabalho original do projeto. Licença a definir pelo mantenedor (sugestão: CC BY 4.0
  para dados; o código segue MIT). Até a decisão, vale a licença do repositório.
- **Ledger e mapeamentos**: cada linha contém o identificador e a descrição original
  do registro de fonte e herda a licença dessa fonte (ver `sources.csv`):
  TACO (citação obrigatória), USDA (CC0), FlavorDB (CC BY-NC-SA 3.0, **não comercial**),
  FlavorGraph (Apache-2.0).
- Nenhuma base externa nova foi importada. Nenhum site comercial foi raspado.

## Como atualizar

```bash
python scripts/build_catalog.py            # valida, regenera ledger e relatório
python scripts/build_catalog.py --check    # falha se o ledger versionado estiver desatualizado
```

O build falha se um registro presente no ledger anterior desaparecer (proteção contra
perda silenciosa) — use `--allow-removal` apenas quando a fonte de fato removeu o registro.
