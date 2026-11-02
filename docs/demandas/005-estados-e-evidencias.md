# [SaborLab] Estados dos ingredientes e camada de evidências

## Responsável, branch e dependência

Claude Code, em `claude/states-evidence`, depois da demanda 002. Abrir PR e não
fazer merge.

## Objetivo

Criar a fundação comum para representar o estado real de um alimento e a
natureza de cada afirmação produzida pelo sistema. Todos os módulos posteriores
devem conseguir responder:

1. o que sabemos sobre este ingrediente agora;
2. de onde veio cada valor ou afirmação;
3. qual a confiança e a precisão;
4. o que permanece desconhecido;
5. que técnica ou observação mudou o estado.

## Compatibilidade

Receitas antigas possuem apenas nome, quantidade, unidade, preparo e momento.
Elas devem continuar funcionando por um adaptador que preserve campos ausentes
como desconhecidos. Não preencher temperatura, armazenamento, umidade ou ponto
de cocção sem dado explícito.

## Modelo de estado

Criar `flavorlab/states.py` com tipos imutáveis ou cópias versionadas:

```python
IngredientState(
    entity_id,
    display_name,
    mass_g,
    preparation_state,
    cooking_method,
    doneness,
    storage_state,
    storage_duration_s,
    measured_temperature_c,
    process_temperature_c,
    process_duration_s,
    moisture_fraction,
    yield_factor,
    texture_attributes,
    state_version,
    observations,
)
```

Campos numéricos não conhecidos usam `None`, acompanhados de estado de
conhecimento. Não usar zero, string vazia ou média genérica para representar
ausência.

### Vocabulários iniciais

`preparation_state`:

```text
raw, cooked, baked, roasted, grilled, fried, sauteed, steamed,
boiled, pressure_cooked, fermented, marinated, cured, smoked,
dried, frozen, thawed, reheated, mixed, unknown
```

`storage_state`:

```text
freshly_prepared, ambient, refrigerated, frozen, thawed, unknown
```

Vocabulários devem ser enums extensíveis ou registros versionados. Não modelar
“rosada” universalmente: `doneness` precisa de contexto do grupo alimentar e
observação, sem virar temperatura implícita.

## Transições

Criar uma função pura:

```python
transition_state(
    previous: IngredientState,
    event: ProcessEvent,
    evidence: list[EvidenceClaim],
) -> IngredientState
```

Cada transição:

- preserva o estado anterior;
- registra técnica, tempo e temperatura apenas quando fornecidos;
- mantém propriedades não afetadas ou marca a incerteza criada;
- não declara que uma transformação ocorreu apenas porque a técnica costuma
  causá-la;
- produz histórico auditável.

## Camada de evidências

Criar `flavorlab/evidence.py`:

```python
EvidenceClaim(
    claim_id,
    subject_id,
    predicate,
    value,
    unit,
    evidence_type,
    confidence,
    source_id,
    method,
    limitations,
    observed_at,
)
```

`evidence_type`:

```text
experimental_measurement
official_food_table
recipe_association
molecular_presence
documented_physical_rule
derived_calculation
culinary_heuristic
human_observation
user_preference
unvalidated_hypothesis
```

`confidence` deve separar qualidade de evidência de precisão numérica. Usar
categorias explícitas (`high`, `moderate`, `low`, `qualitative`, `unknown`) com
definição documentada. Não criar um percentual sem calibração.

## Registro de fontes

Criar um registro único de fontes com ID estável, título, autor/organização,
URL/DOI, licença, versão, data de acesso e escopo. Claims referenciam `source_id`;
não repetem citações livres em cada regra.

Fontes inexistentes ou não verificadas não podem receber URL inventada. Uma
heurística sem fonte fica declarada como heurística e informa sua limitação.

## Consultas mínimas

```python
evidence.for_subject(subject_id)
evidence.for_claim(predicate, value=None)
evidence.explain(claim_id)
evidence.best_available(subject_id, predicate)
state.history(entity_instance_id)
state.known_fields()
state.unknown_fields()
```

Conflitos entre fontes devem ser preservados e retornados, com regra de seleção
documentada; não apagar o valor divergente.

## Caso mínimo

Representar “350 g de fraldinha já feita na air fryer, rosada e suculenta”:

- massa informada pelo usuário;
- estado cozido e método air fryer informados;
- ponto e textura como observação humana;
- temperatura interna, tempo, armazenamento e segurança como desconhecidos;
- nenhuma inferência automática de temperatura ou retenção de nutrientes.

## Arquivos propostos

```text
flavorlab/states.py
flavorlab/evidence.py
data/knowledge/sources.csv
docs/architecture/states-and-evidence.md
tests/test_ingredient_states.py
tests/test_evidence.py
```

## Testes obrigatórios

1. Cru e cozido são estados diferentes do mesmo conceito canônico.
2. Campos desconhecidos sobrevivem a serialização e transição.
3. Air fryer não gera temperatura interna implícita.
4. Observação “suculenta” não vira medição instrumental.
5. Transição preserva histórico e estado anterior.
6. Claims medidos têm unidade e fonte/método.
7. Heurística não aparece como dado experimental.
8. Conflitos entre fontes permanecem consultáveis.
9. Receita antiga é adaptada sem inventar campos.
10. JSON round-trip preserva enums, `None`, limitações e IDs.
11. Toda a suíte existente continua passando.

## Fora de escopo

- regras físico-químicas;
- scheduler de preparo;
- nutrição pós-cocção;
- recomendação de pratos;
- inferência por LLM;
- migração manual de todo o histórico.

## Critérios de aceite

- [ ] Estado, evento, claim e fonte têm contratos documentados.
- [ ] Desconhecidos são explícitos e não viram defaults científicos.
- [ ] Evidência e confiança acompanham valores e recomendações.
- [ ] Compatibilidade com receitas existentes demonstrada.
- [ ] Caso mínimo da fraldinha representado corretamente.
- [ ] Testes determinísticos e suíte completa passando.

## Entrega

Commits separados para contratos, registro de fontes/adaptador e testes. Atualizar
as demandas 003, 006–008 somente se uma mudança de contrato for necessária e
explicada no PR.
