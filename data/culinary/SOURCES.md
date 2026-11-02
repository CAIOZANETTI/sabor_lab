# Dados culinários — fontes, licenças e decisões (demanda 003)

Todas as linhas citam `source_id` do registro único `data/knowledge/sources.csv`
(demanda 005). Verificação de URLs e trechos: 2026-11-02.

| Arquivo | Conteúdo | Fontes |
|---|---|---|
| `equipment.csv` | 19 equipamentos: forno, convecção, air fryer, boca, frigideira, panela, pressão, assadeira, liquidificador, processador, batedeira, tigela, tábua, ralador, coador, geladeira, bancada, grade, termômetro (instrumento) | `saborlab_culinary_curation` (modelagem de recursos; não é dado científico) |
| `techniques.csv` | 28 técnicas com equipamentos compatíveis, transformações que *podem* provocar, tipo de evento (demanda 005) e se aplicam calor | `saborlab_culinary_curation` |
| `cuts.csv` | 15 cortes com geometria, faixa de tamanho (só quando a fonte dá), grupos alimentares aplicáveis e efeito operacional | CIA (medidas), Iowa State (glossário), Wikipedia (aproximação métrica) e curadoria |
| `transformations.csv` | 9 transformações com entradas, condições qualitativas, efeitos sensoriais e limitações | artigos CC BY 4.0 (Maillard, caramelização, amido, ácido, emulsão), OpenStax, FDA, NCCEH |
| `safety_controls.csv` | 15 controles de segurança com valor, unidade, tempo e jurisdição | ANVISA RDC 216/2004, FDA Food Code 2026, FDA Fish Hazards Guidance cap. 5 |
| `processes/*.json` | EX01–EX03 e CEVICHE_DEMO como grafos de etapas com claims de tempo/temperatura | receitas do projeto + curadoria |

## Decisões

- **Segurança × alvo culinário.** `safety_controls.csv` só aceita fonte oficial
  verificada (URL e data de acesso); a validação recusa o contrário. Temperatura de
  forno/óleo da receita é alvo culinário (`target_temp_c`), nunca critério de
  segurança.
- **USDA FSIS não usado.** As páginas do FSIS (tabela de temperatura mínima e
  "Danger Zone") devolveram HTTP 403 na verificação; os valores ficaram só em
  trechos de busca. A fonte está registrada como `usda_fsis_temp_chart`
  (não verificada, sem URL) e nenhum controle a usa. Os controles vêm de ANVISA e
  FDA, verificados no texto.
- **Jurisdição explícita.** ANVISA (BR) e FDA (US) diferem (ex.: manutenção quente
  > 60 °C × ≥ 57 °C); cada controle declara `jurisdiction`. O Food Code é
  código-modelo dos EUA, não norma brasileira.
- **Ceviche.** A desnaturação ácida está documentada (Logrén et al., 2022), e a
  limitação de segurança vem do FDA (cap. 5: salmoura e marinada reduzem mas não
  eliminam parasitas) e do NCCEH. O controle `fda_acid_not_parasite_control` é um
  aviso; o congelamento (`fda_parasite_freeze_*`) é o controle aplicável.
- **Sem temperatura universal.** Gelatinização e Maillard não recebem limiar; a
  caramelização cita ~160 °C apenas como valor variável e com a inconsistência da
  fonte registrada.
- **Medidas de corte variam.** A CIA dá julienne/brunoise 1/8 in e dados 1/4–3/4 in;
  o glossário da Iowa State define dice como 1/8–1/4 in. As faixas guardam a CIA e
  as notas registram a divergência. Conversão de polegadas por definição exata.
- **Potência não inferida.** Equipamentos não têm faixa de temperatura nem potência;
  "fogo médio" não vira watts nem °C.
- **Tempos de planejamento.** Quando a receita não informa, a duração é um claim
  `culinary_heuristic` de confiança `low`, com faixa e limitação; a etapa termina pelo
  sinal de conclusão. Só "350 °F por 12 min" (EX03) vem da receita.

## Licenças das fontes

- CC BY 4.0: artigos de El Hosry 2025, Ding 2025, Wang 2016, Logrén 2022, Tan &
  McClements 2021.
- CC BY-NC-SA 4.0: OpenStax (proíbe uso para treinar LLM sem permissão) e Iowa State
  — citados, sem cópia de texto.
- CC BY-SA 4.0: Wikipedia (só aproximação métrica de chiffonade e cortes).
- © CIA: medidas citadas, imagem não reproduzida.
- Domínio público: documentos do FDA. Ato normativo público: ANVISA RDC 216/2004
  (vigente segundo fontes oficiais em 2026-11-02; revisão em Consulta Pública
  nº 1.362/2025).
- NCCEH: reprodução apenas integral — citado, não reproduzido.
