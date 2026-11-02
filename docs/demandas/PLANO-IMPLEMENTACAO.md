# Plano de implementação e divisão de trabalho — SaborLab

## Objetivo operacional

Evoluir o motor em entregas pequenas, revisáveis e determinísticas, preservando
Jaccard, NPMI, nutrição, catálogo, temperatura de serviço e relatórios atuais.
Cada demanda gera uma branch e um PR próprios. Nenhuma etapa dependente começa
antes de seu contrato-base entrar na `main`.

## Linha de base

Antes da próxima implementação:

- catálogo universal concluído no PR #5, com 16.414 registros inventariados;
- temperatura de serviço concluída no PR #6;
- 121 testes passando na `main`;
- `flavorlab.catalog`, `thermal`, `temporal_sensory` e `food_safety` são
  contratos existentes e devem ser reutilizados;
- a branch de arquitetura precisa entrar na `main` antes da demanda 005.

## Papéis

### Claude Code — executor

Para cada demanda:

1. atualizar a `main` e criar somente a branch indicada;
2. auditar módulos e dados referenciados na especificação;
3. implementar domínio, dados, algoritmo, testes e documentação previstos;
4. manter compatibilidade e não criar contratos paralelos;
5. executar a suíte completa e checks específicos;
6. abrir PR com decisões, fontes, limitações e resultados;
7. parar no PR, sem fazer merge nem iniciar a próxima demanda.

### Codex — gerente técnico e revisor

Para cada PR do Claude:

1. comparar a entrega com os critérios de aceite;
2. revisar arquitetura, ciência, unidades, proveniência e licenças;
3. verificar desconhecidos, hipóteses, estimativas e segurança;
4. procurar duplicação de catálogo, evidência, estado ou cálculo;
5. executar regressão e casos adversos independentes;
6. solicitar correções ou aplicar ajustes pequenos e identificados como Codex;
7. fazer o merge, atualizar o roadmap e liberar a próxima demanda.

### Usuário — direção do produto

- escolher prioridades quando houver trade-offs de produto;
- encaminhar ao Claude a mensagem da demanda liberada;
- criar o PR manualmente quando a API do GitHub desta sessão estiver bloqueada;
- avaliar protótipos e resultados gastronômicos reais.

## Regras de fluxo

- Um PR implementa uma demanda, sem “aproveitar” para antecipar a seguinte.
- Branches partem da `main` depois do merge da dependência.
- Mudança em contrato compartilhado deve ser resolvida no PR que o introduz.
- Dados científicos novos exigem fonte, escopo, unidade, confiança e licença.
- `unknown` permanece explícito; testes não são satisfeitos com dados inventados.
- LLM não participa de cálculos críticos nem é dependência de testes.
- Claude não faz merge. Codex não libera a próxima etapa antes da regressão.

## Fases e gates

### Gate 0 — arquitetura publicada

**Responsável:** Codex.

Incorporar a branch `codex/gastronomy-engine-roadmap` e confirmar os 121 testes.
Somente então liberar a demanda 005.

### Fase 1 — fundação de estado e evidência

| Campo | Definição |
|---|---|
| Demanda | [005 — Estados e evidências](005-estados-e-evidencias.md) |
| Executor | Claude Code |
| Branch | `claude/states-evidence` |
| Dependência | catálogo 002 já incorporado |
| Resultado | `IngredientState`, `ProcessEvent`, `EvidenceClaim`, fontes e adaptador legado |
| Gate Codex | desconhecidos preservados, histórico auditável, conflitos de fonte e caso mínimo da fraldinha |

Esta fase congela os contratos que todas as regras posteriores usarão. Nenhum
trabalho de física, nutrição pós-preparo ou storytelling deve criar seu próprio
tipo de confiança ou evidência.

### Fase 2 — processo culinário e scheduler

| Campo | Definição |
|---|---|
| Demanda | [003 — Grafo de preparo](003-grafo-preparo-conhecimento.md) |
| Executor | Claude Code |
| Branch | `claude/cooking-process-graph` |
| Dependência | 005 incorporada |
| Resultado | técnicas, cortes, equipamentos, transformações possíveis, DAG e scheduler |
| Gate Codex | paralelismo determinístico, recursos, caminho crítico, unidades e segurança separada |

O PR deve reutilizar o estado e as evidências da fase 1 e integrar o termômetro
como instrumento. Não criar interface de timer nesta fase.

### Fase 3 — capacidades especializadas

Após a fase 2, as três trilhas abaixo podem ser executadas separadamente. Se
houver apenas uma sessão do Claude, seguir a ordem da tabela.

| Ordem | Demanda/branch | Trabalho do Claude | Revisão do Codex |
|---|---|---|---|
| 3A | [006 — Física e sensorial](006-fisica-sensorial.md) · `claude/food-physics-sensory` | transformações avaliadas, estabilidade do molho, textura, sensorial | regras qualitativas, molho kefir/queijo, possível ≠ observado |
| 3B | [007 — Nutrição pós-preparo](007-nutricao-pos-preparo.md) · `claude/post-cook-nutrition` | rendimento, retenção, absorção/perda e porção servida | balanço de massa, dupla contagem, fontes e incerteza |
| 3C | [004 — Modo cozinha](004-modo-cozinha-timers.md) · `claude/cook-mode` | execução do grafo, timers, persistência e acessibilidade | não inventar dados, retomada, atraso e segurança visível |

As branches não devem importar código umas das outras antes do merge. Caso 3A,
3B e 3C ocorram em paralelo, cada PR será atualizado com a `main` pelo Codex na
ordem de integração: **006 → 007 → 004**.

### Fase 4 — pessoas, objetivos e seleção de candidatos

| Campo | Definição |
|---|---|
| Demanda | [001 — Recomendador guiado](001-recomendador-guiado.md) |
| Executor | Claude Code |
| Branch | `claude/guided-recommender` |
| Dependências | 006, 007 e contratos de 003/005 |
| Resultado | pessoas, restrições, objetivos, porções e alternativas guiadas |
| Gate Codex | peso isolado não gera calorias, restrições eliminatórias e métricas explicáveis |

### Fase 5 — integração ponta a ponta

| Campo | Definição |
|---|---|
| Demanda | [008 — Compositor e FRALDINHA_001](008-compositor-fraldinha.md) |
| Executor | Claude Code |
| Branch | `claude/plate-composer` |
| Dependências | 001–007 incorporadas |
| Resultado | prato completo, alternativas, processo, nutrição, sensorial e evidências |
| Gate Codex | carne já cozida, Dana Blue sem equivalência inventada, molho e contraste, rastreabilidade completa |

O caso candidato não pode ser resposta hardcoded. O teste avalia critérios e
justificativas para diferentes alternativas válidas.

### Fase 6 — comunicação adaptativa

| Campo | Definição |
|---|---|
| Demanda | [009 — Storytelling adaptativo](009-storytelling-adaptativo.md) |
| Executor | Claude Code |
| Branch | `claude/adaptive-storytelling` |
| Dependências | 005 e 008 incorporadas |
| Resultado | narrativas leiga, curiosa e técnica a partir dos mesmos claims |
| Gate Codex | texto determinístico, fatos invariantes, técnica planejada ≠ executada e saída técnica preservada |

## Validação comum a todos os PRs

Executar, conforme aplicável:

```bash
python -m pytest -q
python scripts/build_catalog.py --check
python scripts/build_site.py --output /tmp/saborlab-site
```

O PR informa:

- número de testes e comandos executados;
- arquivos e contratos alterados;
- fontes e licenças adicionadas;
- exemplos de entrada e saída;
- limitações, dados ausentes e hipóteses;
- comparação objetiva antes/depois;
- riscos de compatibilidade e migração.

## Critérios que bloqueiam merge

- teste existente removido ou relaxado sem justificativa;
- dado científico sem fonte ou unidade;
- temperatura, pH, concentração ou preferência inventados;
- equivalência silenciosa entre marca e categoria genérica;
- hipótese apresentada como observação;
- segurança misturada com preferência culinária;
- novo modelo paralelo de ingrediente, evidência, temperatura ou nutrição;
- chamada externa obrigatória em teste;
- branch com mais de uma demanda funcional.

## Mensagens prontas para o Claude

Enviar apenas a mensagem da demanda liberada.

### Agora — demanda 005

```text
No repositório CAIOZANETTI/sabor_lab, atualize a main e leia integralmente
docs/demandas/README.md, docs/demandas/PLANO-IMPLEMENTACAO.md e
docs/demandas/005-estados-e-evidencias.md. Execute somente a demanda 005 na
branch claude/states-evidence. Reutilize flavorlab.catalog, thermal,
temporal_sensory e food_safety; não implemente transformações, compositor ou
storytelling. Crie os testes especificados, execute toda a suíte, abra o PR com
fontes, decisões e limitações, e não faça merge. Ao terminar, envie o link do PR.
```

### Próximas demandas

Substituir o arquivo e a branch da mensagem acima pelos pares:

```text
003-grafo-preparo-conhecimento.md  -> claude/cooking-process-graph
006-fisica-sensorial.md            -> claude/food-physics-sensory
007-nutricao-pos-preparo.md        -> claude/post-cook-nutrition
004-modo-cozinha-timers.md         -> claude/cook-mode
001-recomendador-guiado.md         -> claude/guided-recommender
008-compositor-fraldinha.md        -> claude/plate-composer
009-storytelling-adaptativo.md     -> claude/adaptive-storytelling
```

Não liberar uma mensagem futura enquanto o gate anterior estiver aberto.

## Definição de conclusão do programa

O programa termina quando uma descrição de ingredientes e seus estados produz
alternativas completas, processo coerente, segurança separada, nutrição
rastreável, análise sensorial qualitativa e narrativa adequada ao público, sem
converter desconhecidos ou hipóteses em fatos.
