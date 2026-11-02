# Grafo de preparo e scheduler (demanda 003)

## Camadas

```text
data/culinary/*.csv ──▶ CulinaryKnowledge (equipamentos, técnicas, cortes,
                        transformações, controles de segurança)  [flavorlab.process]
data/culinary/processes/*.json ──▶ RecipeProcess (DAG de ProcessStep + claims)
                                        │ validate_process / step_controls
                                        ▼
                               flavorlab.scheduler.schedule / reschedule
                                        │
                     ProcessStep.planned_events ─▶ ProcessEvent(planned=True)  [demanda 005]
```

O modelo não depende de interface nem de relatório. Nenhum LLM ordena etapas.

## Contratos reutilizados da demanda 005

- Tempos e temperaturas de etapa são `EvidenceClaim` (`process_duration_s`,
  `process_temperature_c`), referenciados em `ProcessStep.claim_ids`. Um número
  escrito direto na etapa sem claim é recusado. Unidades são convertidas por
  `flavorlab.states.to_canonical` (°F→°C, min/h→s), preservando o valor original
  no claim.
- `ProcessStep.planned_events()` gera `ProcessEvent(planned=True)` por ingrediente.
  `transition_state` recusa eventos planejados: o estado do ingrediente só muda
  quando a etapa é executada e um claim informa o resultado. Assim, uma marinada
  ácida nunca vira "cozido" automaticamente.
- Fontes: o mesmo registro `data/knowledge/sources.csv`.

## ProcessStep

Campos da demanda + `claim_ids`, `transformations` (buscadas, não garantidas) e
`notes`. Fases: `planejamento`, `mise_en_place`, `preaquecimento`, `coccao`,
`montagem`, `descanso`, `finalizacao`, `servico`. Atenção: `active` (ocupa o
cozinheiro na duração ativa), `check` (verificações periódicas) e `passive`.

`validate_process` acusa: ciclo (com o caminho), dependência/recurso/ingrediente
inexistente, duração desconhecida, técnica incompatível com o equipamento,
transformação que não é efeito documentado da técnica, corte não aplicável ao grupo
alimentar do ingrediente (catálogo da demanda 002), controle de segurança
inexistente e IDs fora do catálogo. Nada é corrigido silenciosamente.

## Segurança × alvo culinário

`step_controls(step)` devolve dois blocos separados:

- `culinary_target`: alvo do equipamento/meio (ex.: forno a 350 °F), com o tipo de
  evidência do claim;
- `safety`: controle com fonte oficial verificada (valor, unidade, tempo,
  jurisdição, URL, data de acesso).

Etapa térmica sem controle → aviso "segurança indeterminada". Marinada ácida →
aviso explícito de que não equivale a cocção térmica.

## Scheduler

1. Valida o DAG e detecta ciclos (`find_cycle`).
2. List scheduling determinístico: prioridade pela maior cauda de caminho crítico,
   desempate por `step_id`.
3. Equipamentos (`Resource.capacity`) e cozinheiros (`RecipeProcess.cooks`, padrão 1)
   são recursos; etapas `active` ocupam o cozinheiro só durante a duração ativa.
4. Preaquecimento é agendado o mais tarde possível, para terminar quando a etapa
   consumidora começa; se não couber, a consumidora espera.
5. `critical_path` (sem recursos) e `makespan_s` (com recursos), tempo ativo e
   passivo, mise en place, sequência de cocção, grupos paralelos, esperas por recurso
   e pontos de verificação.
6. `reschedule(step, actual_end_s)`: registra o fim real (`actual_*`) e recalcula
   **apenas os dependentes**; as demais etapas mantêm o planejado.

## Exemplos migrados

| Processo | Etapas | Duração planejada | Observações |
|---|---|---|---|
| EX01 molho de tomate | 7 | 43 min | redução com sinal de conclusão; parmesão ralado em paralelo |
| EX02 chai | 6 | 23 min | infusão com atenção `check` |
| EX03 cookies | 11 | 76 min | preaquecimento termina exatamente no início do forneamento; secos e chocolate em paralelo ao amolecimento da manteiga |
| CEVICHE_DEMO | 5 | 28 min | marinada ácida sem cocção térmica; controle de parasitas por congelamento como pré-requisito |

Os resultados nutricionais das receitas não mudam (teste de regressão).

## Lacunas e suposições

- Durações sem fonte são heurísticas declaradas (`culinary_heuristic`, `low`), com
  faixa; a etapa termina pelo sinal de conclusão.
- Um único cozinheiro por padrão; `check` não ocupa o cozinheiro (verificações
  curtas não são modeladas como bloqueio).
- Reagendamento só para fim real de uma etapa por vez; atrasos encadeados exigem
  chamadas sucessivas.
- Capacidade de forno modelada como recursos (forno, assadeira), sem área real.
- USDA FSIS não verificado (HTTP 403); controles usam ANVISA e FDA.
- Fermentação é só conceito; culturas e condições não são controladas.
- Interface de timers, notificações e persistência ficam para a demanda 004.
