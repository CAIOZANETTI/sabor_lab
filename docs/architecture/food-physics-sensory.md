# Física de alimentos, estabilidade, sensorial e textura (demanda 006)

Regras **qualitativas**, pequenas e auditáveis. Nada aqui é simulação química:
não há cálculo de pH, atividade de água, viscosidade nem cinética.

## Módulos

| módulo | papel | reutiliza |
|---|---|---|
| `flavorlab/transformations.py` | `analyze_transformations(state, technique_id, conditions)` → `TransformationAssessment` | `Transformation`/`Technique` (003), `IngredientState`/`EvidenceClaim` (005) |
| `flavorlab/food_physics.py` | `assess_stability(preparation)` → `StabilityAssessment`; composição por tabela oficial | catálogo (002), TACO/USDA, registro de fontes (005) |
| `flavorlab/sensory.py` | `assess(components)` → `SensoryAssessment`; `aroma_evidence`, `pair_metrics` | `FlavorDB` (moléculas/descritores), NPMI/Jaccard existentes |
| `flavorlab/texture.py` | atributos `observed`/`expected`/`unknown` | `IngredientState.texture_attributes` (005), técnicas (003) |

## Dados (`data/knowledge/`)

| arquivo | conteúdo |
|---|---|
| `transformation_rules.csv` | 53 regras: fato necessário, favorável, inibidor ou crítico por transformação |
| `entity_facts.csv` | 11 fatos curados (kefir/iogurte acidificados e fermentados; classificação de queijos; amidos) |
| `stability_rules.csv` | 16 regras de risco, proteção, sequência e alternativa |
| `sensory_rules.csv` | 14 propriedades sensoriais esperadas por entidade |
| `texture_rules.csv` | 10 expectativas de textura por técnica |
| `sources.csv` | +22 fontes (20 artigos/textos verificados em 2026-11-03, 2 internas/não verificadas) |

`data/culinary/transformations.csv` ganhou `lipid_oxidation`,
`moisture_loss_softening` e `phase_separation`; `techniques.csv` ganhou a técnica
`gentle_heat` e os novos efeitos possíveis das técnicas existentes.

Cada regra cita `source_id`. Regras sem fonte científica direta usam a fonte
interna `saborlab_sensory_heuristics`/`saborlab_culinary_curation`, são
`culinary_heuristic` e exigem limitação (validado em teste). Limiar numérico só em
regra documentada, e sempre com a faixa/contexto da fonte.

## Transformações

Status:

- **observed** — claim de observação/medição de que ocorreu nesta instância;
- **likely** — técnica compatível, entradas necessárias presentes, condições
  críticas informadas, ≥1 fator favorável, nenhum inibidor;
- **possible** — técnica compatível, mas falta dado ou há inibidor;
- **unsupported** — técnica não documentada para a transformação ou entrada
  necessária ausente.

Temperatura/tempo ausentes rebaixam a conclusão e aparecem em `missing`; nenhum
valor é presumido. `to_claim()` publica o resultado como `unvalidated_hypothesis`
(possível) ou `documented_physical_rule` (provável).

Composição (proteína, gordura, água, açúcar, amido) vem de TACO/USDA pelo
mapeamento do catálogo: **presença = teor > 0 na tabela**, sem limiar. "Açúcares
totais" é usado como indício de açúcares redutores (limitação explícita).

Separação de fases só se aplica a sistemas lácteos/emulsões (fato curado ou grupo
`sl:group:dairy`).

## Estabilidade — caso do molho (cebola dourada, alho, queijo azul, kefir, manteiga)

Resultado de `assess_stability` com intensidade de fogo desconhecida:

| tipo | regra | aplicabilidade |
|---|---|---|
| risco | leite fermentado acidificado aquecido pode agregar e ficar granuloso (Gao 2023) | possível (calor desconhecido) |
| risco | caseína agrega perto do pH isoelétrico 4,6; kefir termina em pH 4,0–4,6 (Deshwal 2023; Porto-Fett 2026) | aplicável |
| risco | queijo aquecido em meio aquoso pode formar grumos (Bartolucci 2025) | possível |
| risco | acidez aumenta separação de gordura em queijo processado (Deshwal 2023) | aplicável, confiança baixa (transferência) |
| sequência | A: reduzir a base, baixar o fogo, queijo mexendo, kefir por último fora do fogo | menor risco relativo (heurística) |
| sequência | B: queijo no calor residual antes do kefir | menor risco relativo (heurística) |
| sequência | C: kefir no início e fervura para reduzir | **maior risco; não recomendada como padrão** |
| alternativas | reduzir a base antes; amido (1–4% da massa de queijo no estudo); citrato de sódio (≥2%); bater a cebola; kefir frio por cima | fonte ou heurística declarada |

Faltam: pH, temperatura real, composição verificada do Dana Blue (usada a categoria
genérica da USDA), tempo após cada adição. Confiança geral: `qualitative`.
Nenhuma regra afirma estabilidade ou falha como certeza. Fatores protetores só
aparecem quando presentes de fato.

## Sensorial e textura

- Eixos independentes: doce, salgado, ácido, amargo, umami, picância,
  adstringência, sensação de gordura. Picância é quimestesia (TRPV1) e
  adstringência é sensação tátil (fontes); gordura como gosto é debatida.
- Categorias de evidência nunca fundidas: `molecule_presence`,
  `molecule_descriptor`, `inferred_property`, `human_observation`,
  `user_preference`.
- `pair_metrics`: Jaccard e NPMI como métricas próprias; NPMI zero/ausente não é
  incompatibilidade; nenhuma métrica é preferência.
- `SensoryAssessment`: dominantes (componente principal/molho com intensidade
  alta), de apoio, possíveis excessos (≥2 componentes com intensidade alta),
  oportunidades de contraste (heurísticas) e desconhecidos — sem pontuação.
- Textura: técnica gera `expected`; só claim humano/medição gera `observed`.

Exemplo fraldinha + molho azul/kefir: macio/suculento observados na carne;
cremoso esperado no molho; sensação de gordura com possível excesso (queijo azul +
manteiga, dependente da composição real); ácido do kefir sem valor de pH; crocância
como oportunidade de contraste (heurística de evidência fraca).

## Lacunas que impedem análise quantitativa

1. pH, atividade de água e temperatura real não são medidos nas receitas.
2. Composição de produtos específicos (ex.: Dana Blue) não verificada; usada
   categoria genérica com limitação.
3. Limiar de agregação/grumos vem de sistemas específicos (pecorino em água; leite
   fermentado industrial) e não vira limiar culinário.
4. Não há fonte aberta verificada sobre: reaquecer iogurte/kefir causando sinérese;
   farinha/roux impedindo coagulação de leite com ácido; caramelização de cebola
   refogada; textura de queijo azul ao derreter.
5. Intensidades "altas" são julgamentos culinários sobre teores de tabela, sem
   limiar sensorial calibrado.
6. Evidência de que contraste de textura aumenta preferência é fraca (opinião de
   especialistas citada de segunda mão).
7. ISO 5492 (vocabulário sensorial) é paga e não foi verificada; só nomes de termos.
