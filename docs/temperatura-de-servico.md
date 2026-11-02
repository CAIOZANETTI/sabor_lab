# Temperatura de serviço e percepção sensorial

## Decisões do MVP

O módulo térmico usa um modelo concentrado exponencial com temperatura ambiente
fixa. Duas leituras produzem o ajuste analítico; três ou mais usam regressão
linear de `ln(T - Ta)` e publicam resíduos, RMSE, `R²`, T0 medido e estimado.

O ajuste é aceito somente para resfriamento estritamente decrescente, com todas
as temperaturas acima do ambiente e primeira leitura em `t=0`. Leituras de
aquecimento, repetidas, não finitas, indistinguíveis da resolução do sensor ou
com tempo duplicado retornam erro em vez de um coeficiente arbitrário.

O módulo sensorial é independente. Primeiro agrega notas em faixas de
temperatura. Uma parábola exploratória exige pelo menos seis observações, quatro
temperaturas distintas e amplitude de 5 °C. Esses mínimos evitam um resultado
manifestamente subdeterminado, mas não garantem validade experimental. Curva
convexa ou vértice fora da faixa medida retorna preferência nula.

A recomendação chama a checagem de segurança antes de expor qualquer estimativa
sensorial. Os estados `meets_hot_holding_reference` e
`within_time_reference` descrevem apenas comparação com referências gerais;
eles não certificam que a preparação está segura.

Tempo desde o preparo e tempo fora de controle térmico são campos diferentes.
O segundo só é calculado quando `out_of_control_start_elapsed_min` foi registrado;
sem ele, a avaliação temporal de segurança permanece `indeterminate`.

## Proveniência dos valores

Cada experimento deve marcar seu estado como `recorded_observations` ou
`synthetic_example`. O exemplo `ENTREVERO_001` é sintético em todos os níveis:
arquivo de entrada, JSON resultante e banner do HTML.

O coeficiente `k` é empírico para o conjunto de massa, recipiente, tampa,
ventilação, agitação e posição da sonda registrado. Metas usam as fontes:

- `manual`: escolhida pelo operador;
- `exploratory`: usada para planejar coleta, ainda não validada;
- `measured_preference`: derivada de avaliações suficientes nas condições do
  experimento.

## Limites e lacunas

- temperatura ambiente variável ainda não é ajustada pelo MVP;
- alimentos aquecendo exigem outro modelo;
- gradientes espaciais precisam de múltiplas sondas ou modelo distribuído;
- o intervalo de tempo usa aproximação normal do erro de `k` somente quando o
  ajuste tem graus de liberdade; amostras maiores pedem método mais robusto;
- efeitos de lote, pessoa, ordem e repetição ainda não têm modelo hierárquico;
- temperatura e tempo permanecem correlacionados em resfriamento passivo;
- regras brasileiras específicas por alimento precisam de curadoria antes de
  substituir as referências gerais USDA;
- não há modelo de concentração de voláteis no espaço de cabeça.

Jaccard, NPMI, XlogP e peso molecular não alimentam a curva térmica nem predizem
taxas de volatilização. Nenhum resultado deve ser descrito como “moléculas
fixadas” ou “temperatura perfeita”.

## Próximos estudos

1. Repetir lotes e medir temperatura ambiente ao longo do tempo.
2. Comparar o modelo concentrado com alternativas usando validação fora da
   amostra.
3. Degustar porções equivalentes em ordem randomizada/contrabalançada.
4. Comparar a mesma temperatura em tempos distintos, sob procedimento seguro.
5. Estimar diferenças por categoria de prato e degustador com incerteza.
6. Curar normas brasileiras de cocção, manutenção e resfriamento por categoria.
