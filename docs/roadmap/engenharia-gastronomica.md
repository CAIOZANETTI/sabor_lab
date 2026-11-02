# SaborLab — evolução do motor de engenharia gastronômica

## Visão

O SaborLab deve analisar, elaborar e otimizar pratos completos combinando:

- moléculas aromáticas e associação culinária;
- nutrição e restrições;
- estado real dos ingredientes;
- transformações físico-químicas;
- sabor, textura e contraste;
- técnicas, equipamentos, tempo e temperatura;
- componentes de um prato completo;
- evidências, confiança, hipóteses e lacunas.

As capacidades atuais de Jaccard, NPMI, moléculas-ponte, resolução de
ingredientes, nutrição TACO/USDA e relatórios permanecem compatíveis. As novas
camadas devem compor esses motores, não substituí-los.

## Separação arquitetural

```text
Dados
  catálogo + nutrientes + moléculas + propriedades + fontes
       ↓
Estado e evidência
  o que se sabe, como se sabe e o que permanece desconhecido
       ↓
Regras
  preparo + transformações + física + segurança + textura
       ↓
Otimização
  pessoas + restrições + alternativas + prato completo
       ↓
Explicação e execução
  saída técnica + justificativas + incertezas + modo cozinha
       ↓
Comunicação
  narrativa para quem degusta + linguagem adaptada + fatos rastreáveis
```

Um LLM pode interpretar pedidos e explicar alternativas, mas os cálculos e
regras críticas precisam ser determinísticos. Nenhum módulo pode inventar
temperaturas, concentrações, propriedades ou referências.

A comunicação recebe somente fatos estruturados e evidências liberados pelas
camadas anteriores. Ela pode selecionar, ordenar e reformular esses fatos, mas
não criar ingredientes, procedências, técnicas executadas ou efeitos sensoriais.
O mesmo prato pode ser apresentado em linguagem leiga, curiosa ou técnica sem
que seu estado factual mude.

## Princípios

1. `unknown` é dado válido; ausência não autoriza inferência.
2. Medido, derivado, estimado e heurístico são categorias diferentes.
3. Uma transformação possível não é uma transformação comprovadamente ocorrida.
4. Jaccard não mede preferência; NPMI ausente não significa incompatibilidade.
5. Marca comercial não herda composição exata de uma categoria genérica.
6. Segurança alimentar fica separada de preferência culinária.
7. Peso corporal isolado não determina necessidade energética.
8. Recomendações mostram fonte, confiança, limitações e alternativas.
9. O conhecimento permanece constante; a linguagem muda por escolha explícita.
10. A saída para quem cozinha e a apresentação para quem degusta são produtos
    distintos do mesmo registro estruturado.

## Caso integrador FRALDINHA_001

Duas pessoas, 80 kg e 63 kg, têm 350 g de fraldinha já preparada na air fryer,
rosada e suculenta, além de kefir de leite, queijo Dana Blue, cebola, alho e
manteiga. O objetivo é um prato principal completo, cremoso e com contraste de
textura.

O caso valida se o sistema:

- preserva o estado “já cozida” e não propõe selagem prolongada;
- pede histórico ausente de armazenamento/temperatura ou explicita a lacuna;
- avalia qualitativamente douramento de cebola e alho;
- identifica risco de separação e coagulação em kefir/queijo;
- não recomenda ferver kefir como redução padrão;
- diferencia queijo azul genérico de Dana Blue sem composição verificada;
- propõe acompanhamentos contrastantes e alternativas;
- calcula nutrição somente onde há mapeamento suficiente;
- separa fatos, estimativas, heurísticas e hipóteses.
- apresenta os mesmos fatos em níveis leigo, curioso e técnico;
- não descreve como executada uma técnica apenas sugerida.

“Fraldinha com molho de queijo azul e kefir, brócolis tostados, amêndoas e
limão” é candidato de avaliação, não resposta obrigatória.

## Entregas incrementais

As demandas em `docs/demandas/` são executadas na ordem publicada. Cada uma
gera branch e PR próprios, testes determinísticos e documentação de lacunas.
Claude Code implementa; Codex revisa arquitetura, ciência, dados e integração.

## Definição de evolução funcional

O motor estará integrado quando transformar ingredientes disponíveis e seus
estados em alternativas completas de prato, com sequência técnica coerente,
alertas físico-químicos, contraste sensorial, nutrição rastreável, evidência
explícita e comunicação adequada ao público — sem apresentar hipóteses como
fatos científicos.
