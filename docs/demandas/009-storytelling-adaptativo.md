# [SaborLab] Storytelling e comunicação gastronômica adaptativa

## Responsável, branch e dependências

Claude Code, em `claude/adaptive-storytelling`, somente depois das demandas 005
e 008. Abrir PR e não fazer merge.

## Objetivo

Apresentar o mesmo prato de forma curta, sensorial e atraente para públicos com
níveis diferentes de conhecimento, sem modificar os fatos produzidos pelo
compositor. O princípio do módulo é: **o conhecimento permanece o mesmo; a
forma de comunicá-lo depende do público**.

A narrativa enriquece a degustação. Ela não é relatório técnico, propaganda ou
fonte de fatos culinários.

## Auditoria obrigatória antes do código

Antes de implementar:

1. localizar contratos de prato, componentes, estado e `EvidenceClaim`;
2. identificar explicações ou templates já existentes e reutilizá-los;
3. listar quais claims podem ser narrados e quais pertencem somente à saída
   técnica;
4. registrar incompatibilidades de contrato no PR, sem criar um compositor
   paralelo;
5. confirmar que `FRALDINHA_001` possui IDs estáveis para os fatos usados.

## Separação de saídas

O compositor alimenta duas projeções independentes:

```text
PlateCompositionResult + EvidenceClaims
                 ├── TechnicalPresentation (quem cozinha)
                 │     ingredientes, proporções, processo, temperaturas,
                 │     segurança, nutrição, fontes e incertezas
                 └── TastingNarrative (quem degusta)
                       destaques, aromas, sabores, texturas, contrastes
                       e explicações acessíveis
```

Alertas técnicos não entram automaticamente na narrativa. Eles continuam
visíveis e obrigatórios na saída do responsável pelo preparo. A camada de
comunicação não pode suprimir, reclassificar nem resolver um alerta de
segurança.

## Módulos

Criar, ajustando nomes somente se a auditoria encontrar abstração equivalente:

```text
flavorlab/audience.py
flavorlab/storytelling.py
flavorlab/ingredient_explanations.py
```

### `audience.py`

Definir `AudienceProfile` e políticas configuráveis de vocabulário e extensão.
O nível é selecionado explicitamente; o padrão é `leigo`. Nunca inferir nível
por idade, profissão, peso ou qualquer característica demográfica.

| Nível | Linguagem | Extensão padrão |
|---|---|---|
| `leigo` | cotidiana, ingredientes incomuns explicados, foco em sensação | 30–50 palavras |
| `curioso` | ingredientes, técnica breve e relação sensorial | 40–70 palavras |
| `tecnico` | terminologia culinária e relações físico-químicas sustentadas | 50–90 palavras |

Os intervalos são padrões flexíveis. `max_words` explícito tem precedência, sem
cortar frases ou remover qualificadores indispensáveis. Aceitar inicialmente
`pt-BR`; idioma não suportado deve retornar erro estruturado, nunca traduzir de
forma improvisada.

### `ingredient_explanations.py`

Recuperar descrições verificadas pelo ID canônico do catálogo. A explicação:

- usa somente atributos com `EvidenceClaim` narrável;
- considera vocabulário conhecido quando ele for fornecido explicitamente;
- explica apenas ingredientes relevantes e potencialmente desconhecidos;
- evita glossário longo e repetição;
- preserva espécie, variedade e forma de processamento;
- retorna os IDs das evidências usadas.

Cardamomo pode ser descrito como aromático, cítrico, fresco ou especiado somente
quando esses atributos estiverem sustentados. `1,8-cineol` e acetato de
alfa-terpinila podem aparecer no nível técnico se espécie e evidência molecular
forem compatíveis. Não inferir concentração, dominância ou resultado analítico.

### `storytelling.py`

Construir texto determinístico por templates versionados. Separar:

1. seleção de claims permitidos;
2. planejamento da narrativa;
3. realização linguística por perfil;
4. validação de fatos, estado e extensão;
5. montagem do resultado e rastreabilidade.

O texto pode destacar ingredientes, textura, aroma, contraste e técnicas
confirmadas. Evitar repetição e superlativos publicitários. Entradas idênticas
precisam produzir bytes idênticos.

Um LLM não é dependência desta entrega. Uma integração futura pode reformular
um rascunho, mas deverá trabalhar com uma lista fechada de claims e passar pelo
mesmo validador; nunca poderá acrescentar fatos.

## Estados e autorização de linguagem

Cada claim narrável deve indicar ao menos `claim_id`, sujeito, predicado, valor,
estado, fonte/evidência e confiança conforme a demanda 005.

| Estado do claim | Uso narrativo |
|---|---|
| observado/confirmado | pode ser afirmado com a redação compatível |
| derivado com regra válida | pode ser afirmado com rastreabilidade |
| estimado | somente com qualificador explícito, se o perfil permitir |
| esperado/provável | usar linguagem de expectativa: “deve trazer”, “tende a” |
| sugerido/planejado | não dizer que foi executado; usar “a proposta combina” |
| desconhecido | omitir da narrativa e manter na saída técnica |

Uma receita planejada não pode virar “cebola dourada” até que o estado confirme
o preparo. Uma observação “rosada e suculenta” pode ser narrada no caso
`FRALDINHA_001` porque consta na entrada, com os respectivos IDs.

## Contrato de entrada

```json
{
  "dish_id": "FRALDINHA_001",
  "audience": {
    "knowledge_level": "leigo",
    "tone": "acolhedor",
    "language": "pt-BR",
    "max_words": 60,
    "known_ingredient_ids": []
  },
  "storytelling": {
    "enabled": true,
    "focus": ["ingredientes", "textura", "contraste_sensorial"]
  }
}
```

O prato e os claims são resolvidos pelo ID no resultado estruturado do
compositor. Não aceitar uma descrição livre como substituta para esses dados.

## Contrato de saída

```json
{
  "dish_id": "FRALDINHA_001",
  "audience_level": "leigo",
  "narrative": "...",
  "explained_ingredients": [],
  "claim_ids": [],
  "evidence_ids": [],
  "template_version": "1.0",
  "language": "pt-BR",
  "word_count": 42
}
```

`claim_ids` registra exatamente os fatos realizados no texto; `evidence_ids`
aponta para suas fontes. Claims selecionados podem variar em detalhe entre os
níveis, porém nunca podem entrar em conflito. A saída não duplica as fontes nem
os dados originais.

## FRALDINHA_001

Gerar os três níveis a partir do mesmo registro. Os exemplos da especificação
são referência de tom, não strings obrigatórias. Os templates podem mencionar:

- fraldinha rosada e suculenta, se observada;
- molho de Dana Blue e kefir, se preparado/confirmado;
- cebola dourada, brócolis tostados e amêndoas, se executados;
- cremosidade, acidez, tostado e crocância somente com claims sensoriais
  sustentados.

Se o prato ainda for proposta, usar futuro ou linguagem condicional. A marca
Dana Blue não herda composição ou atributos exatos de queijo azul genérico.

## Testes obrigatórios

Criar:

```text
tests/test_audience.py
tests/test_storytelling.py
tests/test_ingredient_explanations.py
tests/test_storytelling_integration.py
```

Cobrir:

1. a mesma receita produz os três níveis;
2. claims compartilhados mantêm o mesmo significado entre níveis;
3. ingrediente desconhecido recebe explicação adequada;
4. idioma e limite configurável são respeitados;
5. texto permanece positivo e sensorial, sem tom publicitário;
6. ingrediente, técnica, procedência e propriedade não são inventados;
7. alerta técnico não aparece na narrativa e continua na saída técnica;
8. cada afirmação realizada possui `claim_id` e evidência;
9. entradas idênticas geram saídas idênticas;
10. não há chamada externa obrigatória;
11. integração reutiliza o compositor existente;
12. módulos atuais continuam compatíveis;
13. técnica sugerida não é narrada como executada;
14. claim desconhecido ou sem evidência não é realizado;
15. termos moleculares do cardamomo aparecem somente com evidência compatível;
16. `max_words` pequeno demais retorna erro ou limitação explícita, sem truncar;
17. `FRALDINHA_001` passa nos três perfis e preserva seus estados factuais;
18. toda a suíte existente passa.

## Interface demonstrativa

Integrar ao site três escolhas: **Leigo**, **Curioso gastronômico** e
**Técnico/profissional**. A troca deve atualizar a narrativa e manter visível a
lista dos fatos invariantes e suas evidências. Não pedir texto livre para a
seleção do nível.

Identificar claramente quando a demonstração usa fatos estáticos. A interface
final consumirá o resultado real do compositor.

## Personalização progressiva

Preparar contratos para preferências de linguagem, familiaridade explícita com
ingredientes, interesse por técnicas, histórico de degustações e feedback. Não
implementar inferência demográfica nem perfil oculto nesta entrega.

## Experimento futuro

O desenho para avaliar o efeito da narrativa está documentado em
[`docs/experimentos/efeito-da-narrativa.md`](../experimentos/efeito-da-narrativa.md).
Ele não faz parte da implementação operacional nem pode ser usado para afirmar
que uma narrativa melhora a percepção antes da coleta de dados.

## Fora de escopo

- texto gerado sem rastreabilidade;
- aconselhamento médico ou nutricional na narrativa;
- inferência automática do nível do público;
- alegação de preferência, autenticidade cultural ou efeito sensorial não medido;
- esconder alertas do responsável pelo preparo;
- tradução improvisada;
- merge automático.

## Definição de pronto

- [ ] Perfis configuráveis e padrão `leigo`.
- [ ] Templates determinísticos e versionados.
- [ ] Mesmos fatos, linguagem apropriada aos três públicos.
- [ ] Explicações de ingredientes baseadas no catálogo e em evidências.
- [ ] Separação entre saída técnica e narrativa demonstrada.
- [ ] Claims e evidências rastreáveis por frase realizada.
- [ ] `FRALDINHA_001`, testes novos e regressão completos.
- [ ] Limites, decisões e lacunas documentados no PR.

## Entrega

Organizar commits por contratos/perfis, seleção de fatos, templates/explicações,
integração e testes. No PR, relatar arquivos alterados, testes executados,
exemplos dos três níveis, decisões arquiteturais e pendências.
