# [SaborLab] Implementar perfis, metas e recomendador guiado sem entrada livre

> **Ordem:** executar depois das demandas 002 e 003. Consumir os contratos de
> catálogo, preparo e textura definidos nelas; não criar taxonomias paralelas.

## Responsável pela execução

Claude Code, em branch própria: `claude/guided-recommender`.

## Contexto

O SaborLab já calcula nutrição de receitas com TACO/USDA/IBGE, analisa sabor com
FlavorDB2/FlavorGraph e gera relatórios HTML. O próximo incremento transforma
esses motores em uma experiência guiada para pessoas que não querem preencher
formulários nem conhecer nomes técnicos.

O protótipo de referência está em `site/app.html`. Ele demonstra o fluxo e o
visual, mas seus números são ilustrativos. A implementação deve substituir a
lógica demonstrativa por cálculos testados e dados rastreáveis.

## Decisão de produto obrigatória

A experiência principal não terá campos de texto. Toda entrada será feita por:

- cartões de escolha única;
- seletores múltiplos;
- sliders ou botões `−`/`+` para valores numéricos;
- listas hierárquicas de ingredientes por categoria;
- perfis predefinidos editáveis por controles, sem teclado;
- favoritos e escolhas recentes em uma fase posterior.

Não criar caixa de prompt, busca textual, chat ou formulário livre neste PR.

## Jornada do usuário

1. Escolher o modo:
   - `Tenho ingredientes`: selecionar ingredientes por categorias visuais;
   - `Quero uma receita`: escolher cultura, curso e estilo.
2. Escolher objetivo: equilíbrio, perder peso, ganhar massa, low carb, paleo ou
   explorar cultura.
3. Montar o grupo a partir de perfis:
   - quantidade de pessoas;
   - sexo biológico usado apenas na fórmula energética;
   - idade, altura e peso por sliders/steppers;
   - atividade por escala sedentário/leve/moderado/alto;
   - gasto energético observado opcional, selecionado de faixas, para futura
     integração com relógios.
4. Escolher entrada, principal, sobremesa ou menu completo.
5. Escolher cultura: inicialmente brasileira, mediterrânea, marroquina e
   tailandesa.
6. Escolher até três sensações: crocante, cremoso, fresco, suculento, picante,
   ácido, tostado ou macio.
7. Receber proposta com porções individuais, total para preparo, justificativa
   de sabor, nutrição, textura e contexto cultural.

## Escopo técnico

### 1. Modelo de domínio

Criar tipos/dataclasses separados da interface:

```python
PersonProfile(
    id, biological_sex, age_years, height_cm, weight_kg,
    activity_level, observed_tdee_kcal=None
)

GroupProfile(people: list[PersonProfile])

MealRequest(
    mode, goal, course, culture, textures,
    selected_ingredients, dietary_rules
)

PersonTarget(
    energy_kcal, protein_g, carbohydrate_g, fat_g, fiber_g,
    source, assumptions
)

MealPlan(
    dishes, individual_portions, shopping_totals,
    nutrition_score, flavor_score, texture_score, culture_score,
    explanations, warnings
)
```

Não acoplar esses modelos a HTML, pandas DataFrames ou estado global.

### 2. Necessidade energética

- Implementar Mifflin–St Jeor com referência documentada.
- Aplicar fatores de atividade declarados em uma constante auditável.
- Quando `observed_tdee_kcal` existir, usá-lo como fonte principal e registrar
  essa origem no resultado.
- Peso isolado nunca deve produzir uma estimativa silenciosa.
- Dados incompletos devem retornar `needs_input` com os campos faltantes.
- Meta de perda ou ganho deve ser configurável e limitada a faixas conservadoras;
  não prescrever ritmo médico nem prometer resultado.
- Separar meta diária de alocação da refeição. Para o MVP, expor percentuais
  configuráveis por curso/refeição em constantes documentadas.

### 3. Metas e regras alimentares

- `equilibrio`: distribuição padrão explicitada e ajustável;
- `perder`: déficit configurável dentro de limite seguro do produto;
- `massa`: superávit configurável e meta de proteína por kg;
- `lowcarb`: teto configurável de carboidratos, sem definição única escondida;
- `paleo`: lista versionada de inclusões/exclusões; mostrar qual interpretação
  foi aplicada;
- alergias e intolerâncias serão restrições eliminatórias quando forem incluídas.

Não tratar low carb ou paleo como recomendação médica.

### 4. Grupo e porções

- Calcular cada pessoa separadamente.
- Somar somente depois de definir a parcela individual da refeição.
- Produzir quantidade individual e total de cada ingrediente.
- Nunca calcular quatro pessoas multiplicando cegamente uma porção média.
- Preservar arredondamento culinário: apresentar unidades praticáveis e manter
  valores precisos internamente.

### 5. Recomendação multiobjetivo

Criar uma interface de scoring, inicialmente determinística:

```text
restrições obrigatórias: passa/falha
pontuação final:
  30% adequação nutricional
  25% sabor molecular e associação culinária
  15% contraste e variedade de textura
  15% coerência cultural
  15% viabilidade da receita e ingredientes disponíveis
```

Os pesos devem ser constantes configuráveis e aparecer na explicação. Não criar
um modelo de IA opaco neste PR.

Reaproveitar `FlavorDB`, `NutritionDB` e as funções existentes. Não duplicar o
cálculo de nutrientes ou a resolução de ingredientes.

### 6. Textura

Consumir a taxonomia pequena e versionada criada pela demanda 003:

- crocante, cremoso, fresco, suculento, picante, ácido, tostado e macio;
- atributo original do ingrediente;
- transformações por técnica: assar, fritar, grelhar, cozinhar, bater e servir cru;
- evidência/justificativa para cada classificação.

Não duplicar os arquivos de textura ou suas regras. Ausência de dado deve ser
`unknown`, nunca inferida silenciosamente.

### 7. Cultura

- Consumir ingredientes canônicos da demanda 002 e técnicas da demanda 003 ao
  estruturar país/região, curso, prato, fontes e nível de adaptação.
- Diferenciar `tradicional`, `interpretação` e `adaptação`.
- Não declarar autenticidade a partir de moléculas ou NPMI.
- Cada afirmação cultural precisa de fonte pública registrada.
- O MVP pode ter um exemplo revisado por cultura, sem tentar cobrir toda a cozinha.

### 8. Interface estática

- Manter compatibilidade com GitHub Pages, sem backend neste PR.
- Usar HTML/CSS/JavaScript nativo ou justificar qualquer nova dependência.
- O primeiro carregamento não deve incluir os Parquets completos.
- Gerar um JSON compacto apenas com candidatos e atributos necessários ao MVP.
- Todos os controles devem funcionar com mouse, toque e teclado.
- Usar `button`, `aria-pressed`, foco visível, contraste AA e `aria-live` para o
  resultado.
- Sem entrada textual e sem valores nutricionais inventados.
- Quando o motor não puder calcular, mostrar o dado faltante e impedir a promessa.

## Integração futura com relógios

Não integrar APIs externas neste PR. Preparar apenas o campo
`observed_tdee_kcal`, a origem e a data da observação. Documentar estratégia para
Apple Health export, Health Connect, Garmin e Fitbit, incluindo consentimento,
revogação, retenção e margem de erro. Dados de saúde não devem entrar no Git.

## Fora de escopo

- login e contas;
- armazenamento de dados pessoais;
- backend público;
- diagnóstico ou prescrição médica;
- integração real com relógios;
- geração por LLM;
- promessa de autenticidade cultural automática;
- expansão massiva do dicionário de ingredientes.

## Testes obrigatórios

1. Mifflin–St Jeor para perfis masculino e feminino com valores conhecidos.
2. Perfil incompleto não gera meta.
3. `observed_tdee_kcal` substitui a estimativa e registra a origem.
4. Grupo heterogêneo é soma de cálculos individuais.
5. Casal 80/60 kg produz duas porções, não uma média duplicada.
6. Quatro homens de 90 kg produzem quatro metas individuais.
7. Perda, massa, low carb e paleo alteram restrições e explicações.
8. Restrição obrigatória elimina candidato incompatível.
9. Pontuações e pesos somam corretamente e são reproduzíveis.
10. Dado de textura ausente permanece `unknown`.
11. Interface pode ser percorrida somente por teclado.
12. Build do Pages contém app, metodologia e relatórios.
13. Toda a suíte existente continua passando.

## Critérios de aceite

- [ ] Nenhum campo de texto na jornada principal.
- [ ] Cálculo isolado do HTML e coberto por testes.
- [ ] Perfis individuais agregados corretamente.
- [ ] Resultado explica fórmula, fonte, suposições e dados faltantes.
- [ ] Nenhum número demonstrativo permanece na versão funcional.
- [ ] Dados culturais possuem fonte e rótulo de adaptação.
- [ ] Textura tem taxonomia e proveniência.
- [ ] Aplicação funciona como artefato estático do GitHub Pages.
- [ ] README e `site/sobre.html` atualizados conforme a implementação real.
- [ ] `pytest` passa integralmente.

## Entrega esperada

1. Uma PR pequena o bastante para revisão, preferindo separar motor e interface
   em commits claros.
2. Descrição do PR com exemplo antes/depois e comandos de validação.
3. Relatório dos dados ainda ausentes, sem preenchê-los com suposições.
4. Captura ou artefato do fluxo completo em desktop e celular.

Não fazer merge. A revisão e o merge serão realizados pelo Codex após validação
dos cálculos, dados, acessibilidade e compatibilidade com o Pages.
