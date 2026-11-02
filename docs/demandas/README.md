# Demandas de engenharia do SaborLab

Estas especificações são o contrato de trabalho entre o gerente técnico (Codex)
e o executor (Claude Code). Cada demanda deve resultar em uma branch e um PR
independentes. Claude não deve fazer merge.

## Estado de execução

- **Concluída:** 002 — catálogo universal, incorporada pelo
  [PR #5](https://github.com/CAIOZANETTI/sabor_lab/pull/5) no commit `cece85c`.
  O catálogo inventaria 16.414 registros e mantém a fila explícita de curadoria.
- **Concluída em paralelo:** módulo de temperatura de serviço e percepção,
  incorporado pelo [PR #6](https://github.com/CAIOZANETTI/sabor_lab/pull/6).
- **Próxima demanda para Claude Code:** 005 — estados e evidências.

As demandas seguintes devem reutilizar `flavorlab.catalog`, `flavorlab.thermal`,
`flavorlab.temporal_sensory` e `flavorlab.food_safety`; não criar modelos
paralelos para identidade, temperatura, preferência ou segurança.

## Ordem de execução

| Ordem | Demanda | Dependência | Resultado |
|---|---|---|---|
| 1 | [002 — Catálogo universal de alimentos](002-catalogo-ingredientes-variedades.md) | nenhuma | inventário completo, IDs canônicos, hierarquia e mapeamentos de fonte |
| 2 | [005 — Estados e evidências](005-estados-e-evidencias.md) | 002 | estados rastreáveis, desconhecidos explícitos e claims com fontes |
| 3 | [003 — Grafo de preparo e conhecimento culinário](003-grafo-preparo-conhecimento.md) | 002, 005 | etapas, técnicas, cortes, equipamentos, reações e scheduler |
| 4 | [006 — Física de alimentos e sensorial](006-fisica-sensorial.md) | 003, 005 | estabilidade, transformações prováveis, textura e equilíbrio qualitativo |
| 5 | [007 — Nutrição após preparo](007-nutricao-pos-preparo.md) | 002, 003, 005 | rendimento, retenção e nutrientes efetivamente servidos |
| 6 | [004 — Modo cozinha e timers](004-modo-cozinha-timers.md) | 003, 005 | interface operacional, cronograma paralelo e contadores |
| 7 | [001 — Recomendador guiado](001-recomendador-guiado.md) | 002, 003, 005–007 | pessoas, metas, candidatos e interface guiada |
| 8 | [008 — Compositor e FRALDINHA_001](008-compositor-fraldinha.md) | 001–007 | prato completo e teste de integração ponta a ponta |
| 9 | [009 — Storytelling adaptativo](009-storytelling-adaptativo.md) | 005, 008 | apresentação determinística por público, sem alterar os fatos |

## Regras de execução

1. Ler integralmente a demanda e os arquivos referenciados antes de alterar código.
2. Confirmar o estado do `main` e criar a branch indicada na demanda.
3. Não alterar dados existentes para fazer testes passarem sem investigar a fonte.
4. Manter proveniência, licença, unidade e confiança em todo dado novo.
5. Separar domínio, dados, algoritmo e interface.
6. Incluir testes que demonstrem o comportamento, além de executar a suíte completa.
7. Documentar lacunas; `unknown` é preferível a uma inferência silenciosa.
8. Abrir PR com resumo, decisões, fontes, validação e limitações.
9. Não fazer merge. Codex revisará dados, cálculos, UX e compatibilidade.

## Coordenação

As demandas 002 e 005 definem identidade, estado e evidência usados por todas as
seguintes. A demanda 003 define processos; 006 e 007 adicionam física/sensorial
e nutrição pós-preparo. Se um contrato precisar mudar, a decisão deve ser feita
no PR que o introduz, sem criar um segundo modelo incompatível.

A visão consolidada está em
[`docs/roadmap/engenharia-gastronomica.md`](../roadmap/engenharia-gastronomica.md).
O fluxo de branches, papéis, gates e mensagens de handoff está em
[`docs/demandas/PLANO-IMPLEMENTACAO.md`](PLANO-IMPLEMENTACAO.md).
