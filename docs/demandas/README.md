# Demandas de engenharia do SaborLab

Estas especificações são o contrato de trabalho entre o gerente técnico (Codex)
e o executor (Claude Code). Cada demanda deve resultar em uma branch e um PR
independentes. Claude não deve fazer merge.

## Ordem de execução

| Ordem | Demanda | Dependência | Resultado |
|---|---|---|---|
| 1 | [002 — Catálogo universal de alimentos](002-catalogo-ingredientes-variedades.md) | nenhuma | inventário completo, IDs canônicos, hierarquia e mapeamentos de fonte |
| 2 | [003 — Grafo de preparo e conhecimento culinário](003-grafo-preparo-conhecimento.md) | 002 | etapas, técnicas, cortes, equipamentos, reações e scheduler |
| 3 | [004 — Modo cozinha e timers](004-modo-cozinha-timers.md) | 003 | interface operacional, cronograma paralelo e contadores |
| 4 | [001 — Recomendador guiado](001-recomendador-guiado.md) | 002, 003 e contratos da 004 | integração de pessoas, metas, receitas e interface guiada |

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

As demandas 002 e 003 definem contratos usados pelas seguintes. Se uma decisão
de esquema precisar mudar, ela deve ser discutida no PR que introduz o contrato,
sem criar um segundo modelo incompatível em outra demanda.
