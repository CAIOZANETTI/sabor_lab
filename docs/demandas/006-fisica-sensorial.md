# [SaborLab] Física de alimentos, estabilidade, sensorial e textura

## Responsável, branch e dependências

Claude Code, em `claude/food-physics-sensory`, depois das demandas 003 e 005.
Abrir PR e não fazer merge.

## Objetivo

Criar regras qualitativas, fundamentadas e testáveis para analisar
transformações, estabilidade de preparações, equilíbrio sensorial e textura.
O sistema deve informar condições, efeitos prováveis, riscos, alternativas,
evidência e incerteza sem fingir simulação química quantitativa.

## Módulos

```text
flavorlab/transformations.py
flavorlab/food_physics.py
flavorlab/sensory.py
flavorlab/texture.py
```

Reutilizar `Transformation`, `IngredientState`, `EvidenceClaim`, técnicas e
fontes das demandas 003 e 005. Não duplicar taxonomias.

## Transformações

Representar inicialmente:

- Maillard;
- caramelização;
- evaporação e concentração;
- desnaturação/coagulação proteica;
- gelatinização e espessamento;
- emulsificação e separação de fases;
- fermentação;
- oxidação;
- amaciamento e perda de umidade por aquecimento;
- desnaturação ácida.

API sugerida:

```python
analyze_transformations(
    state: IngredientState,
    technique_id: str,
    conditions: ProcessConditions,
) -> list[TransformationAssessment]
```

Cada avaliação informa:

- `possible`, `likely`, `observed` ou `unsupported`;
- condições necessárias e quais foram realmente fornecidas;
- efeitos prováveis em sabor e textura;
- evidências e fontes;
- limitações e dados necessários para quantificação.

Uma técnica compatível torna a transformação possível, não comprovada. Tempo ou
temperatura ausentes reduzem a conclusão e permanecem visíveis.

## Física e estabilidade

`food_physics.py` deve avaliar qualitativamente sistemas com:

- água e gordura;
- proteína e sólidos;
- acidez/pH medido ou desconhecido;
- temperatura;
- emulsificantes/estabilizantes;
- agitação e cisalhamento;
- concentração e evaporação;
- sequência de adição.

Saída:

```python
StabilityAssessment(
    preparation_id,
    risks,
    protective_factors,
    sequence_options,
    missing_measurements,
    evidence_claims,
    confidence,
)
```

Não calcular pH, atividade de água, viscosidade ou cinética sem parâmetros.

## Caso obrigatório de molho

Analisar cebola dourada, alho, queijo azul e kefir de leite. O motor deve:

1. apontar possibilidade de separação de fases;
2. apontar risco de coagulação/agregação de proteínas sob calor/acidez;
3. explicar que composição, pH e temperatura exatos são desconhecidos;
4. comparar sequências de adição e intensidade térmica;
5. propor alternativas culinárias para cremosidade;
6. não recomendar fervura do kefir como técnica padrão de redução;
7. não afirmar estabilidade ou falha como certeza sem dados.

As alternativas devem ser geradas a partir de regras documentadas, por exemplo
reduzir a base antes, baixar temperatura e incorporar componente sensível ao
final, sempre qualificando a recomendação e sua fonte.

## Sensorial

Manter eixos independentes:

```text
doce, salgado, ácido, amargo, umami,
picância, adstringência, sensação de gordura
```

Aromas:

```text
herbáceo, cítrico, terroso, defumado, sulfurado,
floral, tostado e descritores existentes do FlavorDB
```

Separar:

- molécula presente na fonte;
- descritor associado à molécula;
- propriedade inferida da preparação;
- avaliação humana observada;
- preferência individual.

Jaccard e NPMI permanecem métricas próprias. Não convertê-los em “gostoso”,
“equilibrado” ou preferência.

## Textura

Vocabulário inicial:

```text
macio, crocante, cremoso, suculento, fibroso,
firme, granuloso, viscoso
```

Cada atributo tem estado (`observed`, `expected`, `unknown`), método/fonte e
confiança. Técnicas podem produzir efeitos esperados, nunca observação automática.

## Contraste e equilíbrio

Retornar descrição estruturada e oportunidades, sem pontuação arbitrária:

```python
SensoryAssessment(
    dominant_attributes,
    supporting_attributes,
    possible_excesses,
    contrast_opportunities,
    texture_profile,
    aroma_evidence,
    unknowns,
)
```

Exemplo fraldinha + molho azul/kefir:

- macio/suculento são observações da carne;
- cremosidade é objetivo/expectativa do molho;
- gordura e intensidade podem ser altas, com confiança dependente da composição;
- acidez é provável no kefir, sem valor de pH;
- crocância é oportunidade de contraste, não requisito científico.

## Dados e fontes

Criar regras pequenas e auditáveis em arquivos versionados. Toda faixa de
temperatura, condição de estabilidade ou relação causal precisa de fonte e
escopo. Literatura secundária confiável pode orientar regras; alegações de
segurança seguem fontes oficiais.

## Testes obrigatórios

1. Transformação possível difere de observada.
2. Ausência de temperatura reduz a conclusão sem criar valor.
3. Evaporação não implica caramelização.
4. Molho kefir/queijo retorna riscos e alternativas qualitativas.
5. Fervura do kefir não é recomendação padrão.
6. pH ausente permanece desconhecido.
7. Molécula/descritor/preferência permanecem categorias separadas.
8. NPMI zero não vira incompatibilidade.
9. Textura esperada não vira observada.
10. Contraste crocante aparece como oportunidade explicável.
11. Toda regra possui claim/fonte ou rótulo explícito de heurística.
12. Toda a suíte existente continua passando.

## Fora de escopo

- dinâmica de fluidos ou cinética química quantitativa;
- prescrição de segurança sem fonte oficial;
- compositor de pratos;
- cálculo de nutrição pós-preparo;
- pontuação sensorial treinada sem dados calibrados;
- chamadas externas ou LLM em testes.

## Critérios de aceite

- [ ] Módulos pequenos e contratos reutilizáveis.
- [ ] Caso do molho produz análise útil sem falsa precisão.
- [ ] Sensorial, aroma e textura preservam tipo de evidência.
- [ ] Regras, condições, fontes e limitações auditáveis.
- [ ] Testes críticos determinísticos.

## Entrega

Commits separados para transformações, estabilidade e sensorial/textura. Incluir
documento com regras implementadas e lacunas que impedem análise quantitativa.
