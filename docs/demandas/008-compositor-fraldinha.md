# [SaborLab] Compositor de pratos e integração FRALDINHA_001

## Responsável, branch e dependências

Claude Code, em `claude/plate-composer`, somente depois das demandas 001–007.
Abrir PR e não fazer merge.

## Objetivo

Compor pratos completos em vez de sugerir ingredientes isolados, integrando
catálogo, estado, preparo, física, sensorial, nutrição, pessoas, restrições e
evidência. Validar o sistema ponta a ponta com `FRALDINHA_001`.

## Componentes de um prato

```text
principal/proteína
molho ou elemento de ligação
acompanhamento
contraste sensorial/textural
finalização
```

Nem todo prato precisa de todos os componentes, mas ausências e razões devem ser
explicadas. Um menu pode conter entrada, principal e sobremesa por contrato da
demanda 001.

## API

Criar `flavorlab/plate_composer.py`:

```python
compose_plate(
    people,
    available_states,
    equipment,
    dietary_rules,
    goal,
    time_budget=None,
) -> PlateCompositionResult
```

Resultado:

```python
PlateCompositionResult(
    alternatives,
    components,
    individual_portions,
    total_quantities,
    process_plan,
    nutrition,
    sensory_assessment,
    stability_assessment,
    evidence_claims,
    assumptions,
    missing_information,
)
```

O resultado também deve expor IDs estáveis para prato, componentes e claims.
Esses IDs serão a única entrada factual da camada de storytelling da demanda
009; texto livre do compositor não deve ser reinterpretado como evidência.

Gerar mais de uma alternativa quando escolhas relevantes dependem de preferência
ou dados ausentes. Não esconder trade-offs em uma pontuação única.

## Geração de candidatos

Usar regras e dados existentes:

- FlavorDB/Jaccard para moléculas compartilhadas;
- FlavorGraph/NPMI para associação culinária, sem tratar ausência como rejeição;
- restrições eliminatórias do recomendador;
- textura e oportunidades de contraste da demanda 006;
- nutrição e porções das demandas 001 e 007;
- equipamentos, dependências e duração da demanda 003;
- catálogo e disponibilidade reais da demanda 002.

Heurísticas gastronômicas precisam de rótulo, fonte/justificativa e confiança.

## Ingredientes específicos do caso

Mapear com proveniência e sem equivalência indevida:

- fraldinha bovina crua e preparada;
- kefir de leite;
- queijo azul genérico;
- Dana Blue somente quando houver composição verificável;
- brócolis;
- amêndoas laminadas;
- cebola, alho, manteiga e limão já presentes ou mapeados.

Dana Blue não herda automaticamente nutrição exata de “queijo azul”. Se apenas
uma aproximação de categoria estiver disponível, ela deve ser opcional,
identificada como estimativa e nunca usada como rótulo do produto real.

## Caso FRALDINHA_001

Entrada:

```json
{
  "people": [
    {"weight_kg": 80},
    {"weight_kg": 63}
  ],
  "available_ingredients": [
    {"name": "fraldinha", "mass_g": 350, "state": "cooked", "method": "air_fryer", "observations": ["rosada", "suculenta"]},
    {"name": "kefir de leite"},
    {"name": "Dana Blue"},
    {"name": "cebola"},
    {"name": "alho"},
    {"name": "manteiga"}
  ],
  "equipment": ["frigideira"],
  "dietary_preferences": ["low_carb"],
  "goal": "prato principal"
}
```

Peso isolado não permite necessidade energética. O resultado deve solicitar os
dados faltantes ou usar porção culinária configurável com limitação explícita.

## Comportamentos esperados

1. Reconhecer carne já cozida.
2. Não propor selagem longa nem recocção automática.
3. Tratar armazenamento, tempo e temperatura como desconhecidos.
4. Separar orientação de reaquecimento de alerta de segurança.
5. Analisar douramento de cebola/alho como possibilidade condicionada.
6. Avaliar qualitativamente estabilidade do kefir/queijo.
7. Propor sequência que proteja ingredientes sensíveis ao calor.
8. Identificar possível intensidade/gordura, conforme dados disponíveis.
9. Oferecer acompanhamentos com contraste de textura e alternativas.
10. Calcular nutrição apenas para mapeamentos suficientes.
11. Separar conhecido, medido, derivado, estimado e heurístico.
12. Mostrar fontes e limitações por recomendação relevante.

Uma alternativa candidata é fraldinha com molho de queijo azul e kefir,
brócolis tostados, amêndoas e limão. O teste não exige essa receita; exige que
qualquer alternativa satisfaça os critérios com justificativa.

## Otimização

Restrições obrigatórias são filtros. Critérios comparáveis podem ordenar
alternativas, mas o resultado também mostra os componentes:

- compatibilidade molecular;
- associação culinária;
- adequação nutricional;
- contraste e textura;
- estabilidade física;
- viabilidade com equipamento/tempo;
- uso dos ingredientes disponíveis;
- confiança/evidência.

Não apresentar score arbitrário como verdade científica. Pesos configuráveis
ficam documentados e o usuário consegue ver por que uma alternativa venceu.

## Testes obrigatórios

```text
tests/test_plate_composer.py
tests/test_fraldinha_integration.py
```

Cobrir:

1. composição de componentes completos;
2. restrição low carb como regra configurável;
3. equipamento indisponível elimina ou adapta processo;
4. carne já cozida não recebe técnica incompatível;
5. dados de armazenamento ausentes aparecem no resultado;
6. molho retorna análise de estabilidade;
7. Dana Blue não recebe composição exata inventada;
8. acompanhamento oferece contraste explicável;
9. pesos corporais isolados não geram meta calórica;
10. alternativa candidata não é hardcoded como única saída;
11. claims e fontes acompanham justificativas;
12. resultado é determinístico e sem chamadas externas;
13. toda a suíte existente passa.
14. fatos narráveis e seus IDs ficam disponíveis sem alertas técnicos embutidos.

## Interface e relatório

Adicionar uma demonstração ao relatório ou site sem quebrar o modo atual. Mostrar
alternativas, componentes, preparo, nutrição, evidências, incertezas e espaço
para avaliação humana após cozinhar.

## Fora de escopo

- LLM como fonte de fatos;
- diagnóstico nutricional;
- afirmar segurança sem histórico/medição;
- prever preferência individual sem avaliação;
- hardcode do caso como resposta especial;
- merge automático.

## Critérios de aceite

- [ ] Compositor usa contratos anteriores sem duplicar motores.
- [ ] Prato completo e alternativas explicáveis.
- [ ] FRALDINHA_001 cobre o fluxo ponta a ponta.
- [ ] Dados ausentes e estimativas visíveis.
- [ ] Evidência acompanha recomendações.
- [ ] Compatibilidade e suíte completa demonstradas.

## Entrega

Commits separados para compositor, mapeamentos específicos, caso integrador e
interface/relatório. Incluir comparação das capacidades antes/depois e backlog
das lacunas que permanecerem.
