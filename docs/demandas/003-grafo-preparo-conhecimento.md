# [SaborLab] Grafo de preparo, técnicas, equipamentos e reações

## Responsável, branch e dependência

Claude Code, em `claude/cooking-process-graph`, depois da integração das demandas
002 e 005. Abrir PR e não fazer merge.

## Problema

As receitas atuais têm apenas campos livres como `tecnica`, `preparo` e
`momento`. Isso não permite saber o que deve acontecer primeiro, quais tarefas
podem ocorrer em paralelo, quando ligar o forno, quanto tempo algo descansa ou
que transformação culinária está sendo buscada.

## Objetivo

Representar uma receita como um grafo acíclico de tarefas, recursos e
transformações. O motor deve produzir:

- mise en place;
- sequência de cocção;
- tarefas paralelas;
- caminho crítico e duração total;
- tempo ativo e passivo;
- conflitos de equipamento e de atenção do cozinheiro;
- temperaturas, durações e pontos de controle;
- descansos, marinadas e outras etapas passivas;
- explicação das transformações culinárias relevantes.

## Princípios de segurança e evidência

- Tempo e temperatura são dados críticos e precisam de unidade, faixa, fonte e
  contexto do alimento/equipamento.
- Ceviche sofre **desnaturação ácida** e muda textura e aparência; limão não deve
  ser descrito como equivalente universal a cocção térmica ou eliminação de
  patógenos.
- Orientações de segurança devem vir de fontes oficiais como ANVISA, Ministério
  da Saúde, USDA ou FDA, com link e data de acesso.
- Se não houver evidência aplicável, usar `unknown` e um aviso; não fabricar um
  número plausível.
- Separar alvo culinário (dourar, amaciar) de limite de segurança alimentar.

## Modelo de domínio

```python
Equipment(
    equipment_id, type, capacity, heat_mode,
    min_temp_c, max_temp_c, attributes
)

Technique(
    technique_id, name_pt, category,
    compatible_equipment, parameters, effects, sources
)

CutTechnique(
    cut_id, name_pt, geometry, target_size_mm,
    applicable_groups, effect, sources
)

ProcessStep(
    step_id, recipe_id, phase, title, instruction,
    ingredient_refs, technique_id, cut_id, equipment_refs,
    active_duration_s, passive_duration_s,
    target_temp_c, acceptable_range_c,
    dependencies, attention, completion_signal,
    safety_control_id=None
)

Transformation(
    transformation_id, name, inputs, conditions,
    sensory_effects, limitations, sources
)

RecipeProcess(
    recipe_id, servings, steps, resources, provenance
)
```

`ProcessStep` deve consumir os tipos de estado e evidência definidos na demanda
005. Não criar um segundo formato de confiança, fonte ou propriedade desconhecida.

### Fases controladas

```text
planejamento
mise_en_place
preaquecimento
coccao
montagem
descanso
finalizacao
servico
```

### Atenção

- `active`: ocupa o cozinheiro durante a duração;
- `check`: passiva, mas exige verificações periódicas;
- `passive`: pode transcorrer sem atenção contínua.

## Scheduler

Implementar algoritmo determinístico que:

1. valide o DAG e detecte ciclos;
2. calcule dependências e caminho crítico;
3. antecipe preaquecimento para terminar quando o alimento estiver pronto;
4. execute tarefas passivas em paralelo com tarefas ativas;
5. evite reservar o mesmo equipamento além da capacidade;
6. considere inicialmente um cozinheiro como recurso ativo;
7. calcule início/fim relativo e duração total;
8. reagende ao concluir uma etapa antes ou depois do previsto;
9. mantenha tempos reais separados de estimativas planejadas.

Não usar LLM para ordenar etapas. O grafo e o scheduler devem ser testáveis.

## Equipamentos iniciais

- forno convencional e com convecção;
- fogão/boca;
- frigideira, panela, assadeira e panela de pressão;
- liquidificador/processador;
- geladeira e bancada;
- termômetro culinário como instrumento, não fonte de calor.

Registrar capacidade quando relevante: uma boca, uma assadeira, volume da panela.
Não inferir potência exata de rótulos como “fogo médio”.

## Técnicas de corte iniciais

- picado grosseiro e fino;
- cubos com faixa de tamanho;
- fatias com espessura;
- julienne, brunoise e chiffonade;
- gomos, rodelas e tiras;
- amassar, ralar e triturar.

Cada corte precisa explicar o efeito operacional: área superficial, velocidade
de cocção, liberação de aroma ou textura. Evitar medidas rígidas quando tradições
culinárias usam definições diferentes; registrar faixa e fonte.

## Transformações iniciais

- reação de Maillard;
- caramelização;
- gelatinização de amido;
- desnaturação/coagulação de proteínas;
- desnaturação ácida e marinada;
- emulsificação;
- evaporação e redução;
- hidratação e descanso;
- fermentação apenas como conceito, sem controlar culturas neste PR.

Condições devem ser específicas. Não atribuir uma única temperatura universal a
processos que dependem de ingrediente, água, pH ou equipamento.

## Dados e proveniência

```text
data/culinary/equipment.csv
data/culinary/techniques.csv
data/culinary/cuts.csv
data/culinary/transformations.csv
data/culinary/safety_controls.csv
data/culinary/SOURCES.md
flavorlab/process.py
flavorlab/scheduler.py
```

Dados curados ficam em CSV; processos de receita podem ser JSON para preservar o
grafo. Referenciar IDs canônicos da demanda 002.

## Casos de demonstração

Modelar EX01, EX02 e EX03 sem alterar o resultado nutricional. Incluir um caso de
teste de ceviche somente se as fontes de segurança e transformação estiverem
documentadas. O caso deve dizer explicitamente que ácido não garante segurança
equivalente ao tratamento térmico.

Exemplo de paralelismo esperado para EX03:

```text
separar ingredientes ─┬─ misturar secos ───────────────┐
                      ├─ amolecer manteiga ─ bater ─────┼─ modelar ─ assar ─ esfriar
ligar forno ──────────┴──────── preaquecimento ─────────┘
picar chocolate ────────────────────────────────────────┘
```

## Testes obrigatórios

1. Ciclo de dependência é rejeitado com mensagem clara.
2. Preaquecimento ocorre em paralelo e termina antes do uso do forno.
3. Duas tarefas não ocupam a mesma frigideira simultaneamente.
4. Descanso passivo não bloqueia mise en place de outra etapa.
5. Caminho crítico e duração total correspondem a um grafo conhecido.
6. Um atraso recalcula apenas tarefas dependentes.
7. Conversões de tempo e temperatura preservam unidades.
8. Corte incompatível com ingrediente gera validação, não correção silenciosa.
9. Segurança e alvo culinário aparecem como controles distintos.
10. Ceviche não é marcado como termicamente cozido ou automaticamente seguro.
11. EX01–EX03 têm processos válidos e ingredientes resolvidos no catálogo.
12. Toda a suíte existente continua passando.

## Fora de escopo

- interface de timers;
- notificações de navegador;
- controle de eletrodomésticos;
- visão computacional;
- estimar potência real do forno;
- substituir normas sanitárias ou orientação profissional;
- gerar etapas automaticamente a partir de texto sem revisão.

## Critérios de aceite

- [ ] Modelo separado de interface e relatório.
- [ ] Scheduler determinístico com recursos e paralelismo.
- [ ] Mise en place, cocção, descanso e serviço representados.
- [ ] Técnicas, cortes, equipamentos e transformações têm fontes.
- [ ] Limites de segurança não são confundidos com preferência culinária.
- [ ] Casos demonstrativos e testes completos.
- [ ] Documentação informa lacunas e suposições.

## Entrega

Commits separados para pesquisa/dados, modelo, scheduler e migração dos exemplos.
Não implementar o modo cozinha neste PR.
