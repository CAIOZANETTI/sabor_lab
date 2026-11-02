# Estados de ingredientes e camada de evidências (demanda 005)

Contratos compartilhados por todas as demandas seguintes (003, 006–009). Nenhum
módulo posterior deve criar outro formato de confiança, fonte, desconhecido ou
estado.

## Visão geral

```text
data/knowledge/sources.csv ── SourceRegistry ─┐
                                              ▼
EvidenceClaim (valor + unidade + tipo + confiança + fonte/método + limitações)
        │  predicate = nome do campo, subject_id = instância
        ▼
IngredientState vN ──ProcessEvent + claims──▶ transition_state ──▶ IngredientState vN+1
        │                                                           │
        └──────────────────────── StateTracker.history ─────────────┘
```

- `flavorlab/evidence.py` — `EvidenceClaim`, `Source`, `SourceRegistry`,
  `EvidenceStore` (consultas, conflitos, JSON).
- `flavorlab/states.py` — `IngredientState`, `FieldKnowledge`, `Doneness`,
  `ProcessEvent`, `transition_state`, `StateTracker`, vocabulários versionados,
  adaptador de receitas antigas e delegação para `flavorlab.food_safety`.

## EvidenceClaim

| campo | significado |
|---|---|
| `claim_id` | ID estável e único; claims nunca são sobrescritos (mesmo ID com conteúdo diferente é erro) |
| `subject_id` | o que é descrito: instância (`user:fraldinha_001`), entidade do catálogo (`sl:...`), prato |
| `predicate` / `value` / `unit` | a afirmação; valor numérico exige unidade |
| `evidence_type` | um dos 10 tipos da tabela abaixo |
| `confidence` | qualidade da evidência (`high`, `moderate`, `low`, `qualitative`, `unknown`) |
| `uncertainty`, `value_min`, `value_max` | **precisão numérica**, separada da confiança |
| `source_id` / `method` | origem: fonte registrada e/ou método (quem/como mediu, observou, calculou) |
| `limitations` | condições e limites; obrigatório para heurística e hipótese |
| `observed_at`, `context` | quando e em que condição (lote, equipamento, grupo do alimento) |

### Tipos de evidência e regras

| tipo | exige | confiança permitida |
|---|---|---|
| `experimental_measurement` | valor numérico com unidade; método ou fonte | todas |
| `official_food_table` | `source_id` registrado | todas |
| `documented_physical_rule` | `source_id` registrado | todas |
| `recipe_association`, `molecular_presence` | `source_id` registrado | todas |
| `derived_calculation` | método (ou fonte) | todas |
| `human_observation` | método (quem observou) | `moderate`, `low`, `qualitative`, `unknown` |
| `user_preference` | método | `qualitative`, `unknown` |
| `culinary_heuristic` | limitações | não pode ser `high` |
| `unvalidated_hypothesis` | limitações | `low`, `unknown` |

### Confiança (definições)

- **high**: medição direta ou tabela oficial aplicável ao mesmo sujeito e contexto.
- **moderate**: fonte confiável com transferência de contexto, ou cálculo derivado
  de dados de alta confiança; relato direto de quem cozinhou.
- **low**: associação indireta, analogia ou fonte fraca.
- **qualitative**: afirmação sem escala calibrada (sensorial, relato).
- **unknown**: qualidade não avaliada.

Não há percentual de confiança: isso exigiria calibração que o projeto não tem.

### Seleção e conflitos (`best_available`)

Ordem: tipo de evidência (medição > tabela oficial > regra física > cálculo >
observação > associação > presença molecular > heurística > preferência >
hipótese), depois confiança, depois `observed_at` mais recente, por fim `claim_id`
(determinismo). Todos os demais claims voltam em `alternatives`; `conflict=True`
quando algum valor diverge além da soma das incertezas declaradas. Nada é apagado.

## Registro de fontes

`data/knowledge/sources.csv` é o **registro único**: ID estável, título,
autor/organização, tipo, URL/DOI, licença, versão, data de acesso, escopo e
`verification_status`. Regras:

- URL ou DOI só com `verification_status=verified` e `accessed_at` — nenhum link
  inventado; fontes ainda não verificadas ficam sem URL.
- Os datasets do catálogo (`data/catalog/sources.csv`: `taco_4ed`,
  `usda_sr_legacy`, `usda_foundation`, `flavordb2`, `flavorgraph_191120`) usam os
  mesmos IDs e versões aqui (teste de consistência).
- `usda_fsis_general` registra a referência citada por `flavorlab.food_safety` sem
  URL, pendente de verificação.

## IngredientState

Campos da demanda + `instance_id` (a peça concreta), `knowledge` (status por campo),
`events`, `parent_version` e `legacy` (texto original de receitas antigas).

- Todo valor conhecido tem `FieldKnowledge(status="known", claim_ids=...)`.
- Ausência: `None` (ou `"unknown"` nos campos de vocabulário) e status `unknown`.
- `uncertain`: valor anterior que um evento pode ter mudado, ou claims em conflito.
- `doneness` é `Doneness(term, context, claim_id)`: "rosada" só tem sentido com o
  contexto do alimento e **nunca** gera temperatura.
- `texture_attributes` vem de claims `texture_attribute` (um por atributo).
- Vocabulários (`preparation_state`, `storage_state`, `cooking_method`,
  `event_kind`) são `Vocabulary` versionados; `extend()` cria nova versão.

### Unidades canônicas

`mass_g` g · `*_temperature_c` °C · `*_duration_s` s · `moisture_fraction`
fração 0–1 · `yield_factor` razão. `to_canonical` converte °F, min/h/dia,
kg/oz/lb pelas definições exatas e recusa unidades incompatíveis.

## Transições

`transition_state(previous, event, evidence)` é pura:

1. aplica apenas os claims citados em `event.claim_ids` (sujeito = instância);
2. campos que o tipo de evento pode alterar (`EVENT_EFFECTS`) e não foram
   informados viram `uncertain`, guardando o valor anterior na nota — **sem
   valor presumido**;
3. temperatura medida é instantânea e fica obsoleta após qualquer evento que não
   seja `measure`;
4. demais campos são mantidos; `state_version` incrementa; `events` acumula;
5. evento `planned=True` é recusado: planejado não é executado.

Um evento `cook` sem claim de estado resultante deixa `preparation_state`
`unknown/uncertain`: a técnica não declara sozinha que uma transformação ocorreu.

`StateTracker` guarda todas as versões (`history(instance_id)`) e os claims.

## Compatibilidade com receitas antigas

`from_legacy_line` / `adapt_legacy_recipe` convertem linhas de
`receita_ingredientes.csv`:

- massa só com coluna `gramas` ou unidade de massa (g, kg, oz, lb); volume e
  contagem ficam com massa desconhecida e nota (a densidade é estimativa do
  módulo de nutrição, não fato do estado);
- `preparo` vira estado apenas quando nomeia um estado ("cru", "frito");
  cortes e textos livres ("picado", "amolecida") ficam em `legacy`;
- entidade do catálogo por igualdade de nome/apelido; mais de um candidato não é
  escolhido;
- temperatura, armazenamento, umidade, ponto e rendimento permanecem desconhecidos.

O cálculo nutricional existente (`flavorlab.nutrition`) não foi alterado.

## Caso mínimo: FRALDINHA_001

"350 g de fraldinha já feita na air fryer, rosada e suculenta":

| campo | valor | origem |
|---|---|---|
| `mass_g` | 350 | `human_observation` (relato) |
| `preparation_state` / `cooking_method` | `cooked` / `air_fryer` | relato |
| `doneness` | "rosada" (contexto `sl:group:meat`) | observação qualitativa |
| `texture_attributes` | "suculenta" | observação qualitativa |
| temperatura interna e de processo, tempo, armazenamento, umidade, rendimento | `None` / `unknown` | — |
| segurança | `indeterminate` (`flavorlab.food_safety`) | sem dados |

Nenhuma temperatura ou retenção de nutrientes é inferida.

## Lacunas

- `observed_at` é texto ISO 8601; fuso horário não é normalizado.
- O registro de fontes ainda tem itens sem URL verificada (TACO/NEPA, FlavorDB2,
  POF/IBGE, ANVISA IN 75/2020, USDA FSIS geral).
- Não há regras físico-químicas, scheduler, nutrição pós-preparo nem inferência
  por LLM nesta camada (demandas 003, 006 e 007).
