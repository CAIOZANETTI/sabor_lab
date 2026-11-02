# [SaborLab] Nutrição após preparo, rendimento e retenção

## Responsável, branch e dependências

Claude Code, em `claude/cooked-nutrition`, depois das demandas 002, 003 e 005.
Abrir PR e não fazer merge.

## Objetivo

Evoluir o cálculo nutricional para distinguir alimento cru, cozido medido e
estimativa derivada de preparo. Calcular nutrientes da porção efetivamente
servida considerando rendimento, água, gordura e retenção somente quando houver
dados aplicáveis e rastreáveis.

## Princípios

1. Preferir registro nutricional medido do alimento preparado quando ele
   corresponder à entidade e ao método.
2. Não aplicar fator de cocção sobre alimento que já possui composição cozida.
3. Peso muda concentração; não cria ou remove automaticamente massa de nutriente.
4. Retenção de nutrientes e rendimento são fatores distintos.
5. Absorção/perda de gordura precisa de modelo ou dado específico.
6. Medido, derivado e estimado aparecem separados na saída.
7. Ausência de fator aplicável mantém cálculo parcial e aviso.

## Pesquisa de fontes

Comparar fontes oficiais de fatores de rendimento e retenção, incluindo USDA e
FAO/INFOODS quando compatíveis, além de literatura por alimento/técnica. Para
cada fonte registrar licença, versão, alimento, método, faixa e limitações.

Não reutilizar fator genérico de “carne” para todo corte, ponto e método sem
mostrar que é aproximação de baixa confiança.

## Modelo

```python
YieldFactor(
    entity_id, technique_id, initial_state, final_state,
    factor, basis, conditions, evidence_claim_id
)

RetentionFactor(
    entity_id_or_group, nutrient_key, technique_id,
    factor, conditions, evidence_claim_id
)

FatTransfer(
    source_entity_id, target_entity_id,
    absorbed_g, lost_g, method, evidence_claims
)

PreparedNutritionResult(
    initial_mass_g, served_mass_g,
    measured_values, derived_values, estimated_values,
    nutrient_totals, warnings, evidence_claims
)
```

## Algoritmo

1. Resolver a forma/estado canônico do alimento.
2. Verificar se existe composição medida no estado final.
3. Se existir, usar a composição final e impedir dupla transformação.
4. Caso contrário, localizar fator de rendimento aplicável.
5. Aplicar retenção nutriente a nutriente somente quando disponível.
6. Modelar água e gordura separadamente.
7. Reconciliar massa inicial, ingredientes adicionados/removidos e massa servida.
8. Produzir porção individual usando o motor atual sem perder proveniência.

Fórmulas devem estar documentadas com bases (massa crua, massa cozida, porção)
e testes numéricos simples.

## Integração

Estender `NutritionDB` por composição, serviço ou funções novas, preservando as
APIs existentes. O relatório atual continua funcionando. Novos campos aparecem
somente quando o estado/preparo foi fornecido.

## Casos obrigatórios

- alimento cru com fator de rendimento conhecido;
- alimento cozido já medido, sem dupla contagem;
- redução de água aumentando concentração por 100 g sem aumentar total;
- fritura com absorção desconhecida gerando aviso;
- fraldinha já preparada com 350 g servidos, mas sem peso cru: usar dados
  cozidos compatíveis ou declarar que não é possível reconstruir o rendimento;
- porções diferentes para pessoas, quando os perfis completos existirem.

## Testes obrigatórios

1. Rendimento e retenção usam bases corretas.
2. Alimento cozido medido não recebe fator novamente.
3. Perda de água conserva massa de nutriente antes da retenção.
4. Nutriente sem fator permanece com estado conhecido/unknown apropriado.
5. Gordura absorvida não é inventada.
6. Valores medidos têm precedência sobre estimados compatíveis.
7. Fator de grupo informa baixa confiança e limitações.
8. Totais por receita e porção fecham numericamente.
9. Fraldinha sem peso cru não produz rendimento fictício.
10. APIs e relatórios existentes permanecem compatíveis.
11. Toda a suíte passa sem chamadas externas.

## Fora de escopo

- prever composição química completa por simulação;
- fatores sem fonte;
- necessidades energéticas individuais, tratadas na demanda 001;
- recomendar técnicas ou pratos;
- alterar retrospectivamente relatórios versionados sem necessidade.

## Critérios de aceite

- [ ] Fontes, fórmulas e bases auditáveis.
- [ ] Medido/derivado/estimado separado em código e relatório.
- [ ] Proteção contra dupla contagem.
- [ ] Ausências e aproximações explícitas.
- [ ] Compatibilidade com `NutritionDB` atual.
- [ ] Testes numéricos e suíte completa passando.

## Entrega

Commits separados para pesquisa/dados, motor, integração e testes. Incluir tabela
de cobertura por alimento/técnica e uma lista de fatores ainda ausentes.
