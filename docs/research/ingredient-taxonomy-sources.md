# Fontes para taxonomia de ingredientes — pesquisa e decisão (demanda 002)

Data da verificação: **2026-11-02**. "NV" = não verificado em fonte primária nesta
pesquisa. Nenhuma base externa foi importada nesta PR: a pesquisa define o que pode
ser importado, com que licença e com que ganho. **Licença incerta bloqueia a
importação** e fica registrada como pendência (seção final).

## Resumo da decisão

| Fonte | Papel no catálogo | Licença | Decisão nesta PR |
|---|---|---|---|
| TACO 4ª ed. (via brolesi/taco) | composição BR, nomes PT | reprodução permitida com citação; código brolesi MIT | **já presente**: 100% inventariado e principal alvo da curadoria |
| USDA FoodData Central | composição EUA, nomes EN | CC0 1.0 | **já presente**: 100% inventariado |
| FlavorDB2 | sabor (moléculas) | CC BY-NC-SA 3.0 (registro do projeto; site fora do ar em 2026-11 → **NV**) | **já presente**: inventariado; derivados herdam NC-SA |
| FlavorGraph | co-ocorrência em receitas | Apache-2.0 | **já presente**: 100% inventariado |
| FoodOn | ontologia de alimentos (hierarquia, xrefs) | CC BY 4.0 | **candidata**: importar xrefs `FOODON:` para conceitos curados (próxima etapa) |
| Wikidata | táxon, nomes PT, IDs cruzados | CC0 (dados estruturados) | **candidata prioritária** para `taxa.external_ids` |
| Open Food Facts | produtos embalados | ODbL (base), DbCL (conteúdo), CC BY-SA (imagens) | **fora de escopo** (produtos de supermercado); exigiria separar derivados ODbL |
| Catalogue of Life (COL) | nomes científicos aceitos | "cc by" (versão **NV**) | candidata para validar `taxa.scientific_name` |
| GBIF Backbone | taxonomia | CC BY 4.0 — **congelado desde 2023**; GBIF migrou para COL XR (jun/2026) | não usar; preferir COL |
| GRIN Taxonomy (USDA ARS) | espécies cultivadas, usos, nomes PT | CC0 1.0 (registro no GBIF) | candidata para plantas cultivadas |
| FAO ASFIS | espécies de pescado (código 3-alfa) | CC BY 4.0 + termos FAO (declaração específica do ASFIS **NV**) | candidata para pescado após confirmar termo |
| FishBase / SeaLifeBase | biologia de peixes | CC BY-NC 4.0 / **NV** | **evitar** (não comercial) |
| LanguaL / FoodEx2 | facetas de descrição de alimentos | **NV** | bloqueadas até confirmar licença |
| Portaria MPA nº 532/2025 | nomes comuns × científicos de pescado no Brasil | ato normativo público | **usada como evidência** em descrições de nomes comerciais (sem importar a tabela) |
| eAmbrosia (UE) | registros DOP/IGP de queijos | aviso geral da Comissão: CC BY 4.0; termo do site **NV** | não usada; autenticidade de origem não é inferida |

## 1. TACO e USDA FoodData Central (já presentes)

**TACO 4ª ed. (NEPA/UNICAMP, 2011)** — 597 alimentos brasileiros, descrições em
português no padrão `Alimento, qualificador, estado` ("Feijão, preto, cru").
- Licença: "É permitida a reprodução total ou parcial…, desde que citada a fonte"
  (confirmado só em cópia secundária do PDF; página oficial do NEPA **NV**).
- Repositório brolesi/taco: **código MIT**; o próprio repositório remete aos termos
  das fontes primárias para os dados. Commit fixado no projeto:
  `b800c910dfc9d2e8e6bab45dd42e5b8f5167b466`.
- Atualização: estática desde 2011. IDs: número sequencial (`taco:568`).
- Exemplo de mapeamento: `taco:568 "Feijão, preto, cru"` → `sl:form:common_bean_black_raw`
  (variante `sl:variant:common_bean_black`, espécie em `sl:ingredient:common_bean` →
  *Phaseolus vulgaris*).

**USDA FoodData Central** — SR Legacy (2018-04, final) + Foundation Foods (o projeto
usa 2025-12-18; existe release de outubro/2026). 8.229 alimentos em inglês, padrão
`Grupo, tipo, subtipo, estado` ("Fish, salmon, Atlantic, wild, raw").
- Licença: **CC0 1.0**; pedem citação do FDC. Formatos CSV/JSON/API.
- IDs: `fdc_id` (`usda:173686`). Sem rótulos em português.
- Exemplo: `usda:173686 "Fish, salmon, Atlantic, wild, raw"` →
  `sl:form:atlantic_salmon_wild_raw` (origem selvagem informada pela fonte).
- Observação: Foundation Foods publica feijões em **base seca (0% umidade)**; o
  catálogo cria formas `*_dry_matter` para não misturá-las com o grão cru comum.

## 2. FlavorDB2 e FlavorGraph (já presentes)

**FlavorDB2** (CosyLab, IIIT-Delhi) — 935 entidades com moléculas de sabor; campo
`scientific_name` às vezes traz espécie, às vezes gênero/família ou texto livre
("Cattle", "Poacceae"), por isso é tratado como evidência fraca, não como táxon.
- Licença registrada no projeto: **CC BY-NC-SA 3.0**. Em 2026-11-02 o site respondeu
  HTTP 503 em todas as tentativas: a licença dos dados **não foi reconfirmada**.
- Consequência: linhas do ledger com descrições do FlavorDB herdam NC-SA; o catálogo
  curado não copia moléculas, só referencia `flavordb:<entity_id>`.
- Casos que exigem cuidado: nós taxonômicos ("perciformes", "scombridae"), mamíferos
  marinhos classificados como "Fish/Seafood", algas como "Seafood", "Tobacco".
- Exemplo: `flavordb:78 "Parmesan cheese"` → `sl:variant:cheese_parmesan`.

**FlavorGraph** (Park et al., 2021) — 6.653 nós de ingrediente em snake_case
(`black_bean`, `dry_parmesan_cheese`), extraídos de receitas (Recipe1M).
- Licença: **Apache-2.0**. Snapshot `nodes_191120`/`edges_191120`.
- Só ~600 nós têm categoria (`dict_ingr2cate`). Nomes misturam marca, estado e
  preparo ("10_inch_flour_tortilla").
- Exemplo: `flavorgraph:470 "black_bean"` → `sl:variant:common_bean_black`.

## 3. FoodOn

- Escopo: ontologia OBO de alimentos (~40 mil termos no OLS), hierarquia de produtos,
  facetas e xrefs (LanguaL, FoodEx2, FAO).
- Licença: **CC BY 4.0**. Formatos OWL (`foodon.owl`, `foodon-base.owl`), TSV de sinônimos.
- Versão: inconsistente entre `versionIRI` (2026-09-20), `versionInfo` (2026-02-02)
  e a última tag do GitHub (`v2025-02-01`) — registrar a versão pelo IRI no import.
- IDs: `FOODON:02022069` (atlantic salmon), `FOODON:00003247` (parmesan cheese food
  product), `FOODON:00002889` (black turtle bean). Arroz: **NV**.
- Idioma: praticamente só inglês (termos verificados sem rótulo `pt`).
- Limitação observada: o termo verificado de salmão não tinha link para NCBITaxon.
- Uso proposto: coluna de xref `FOODON:` nos conceitos/variantes curados (mapeamento
  `close`/`exact` com revisão), sem copiar a hierarquia inteira.

## 4. Wikidata

- Licença: dados estruturados **CC0**. API/SPARQL ao vivo.
- Propriedades verificadas: P225 (taxon name), P1843 (taxon common name), P685
  (NCBI Taxonomy), P10585 (Catalogue of Life ID), **P6767 (FoodOn ID)**, P1978 (USDA
  NDB number), P12917 (FoodData Central ID), P1421 (GRIN URL), P938 (FishBase), P6018
  (SeaLifeBase). **P846** foi renomeada "GBIF-species-ID (before 2026 update)"; a nova é
  **P14607**. Não há propriedade para ASFIS.
- Exemplos: Q188879 (*Salmo salar*: NCBI 8030, COL 6XCXT, FishBase 236);
  Q161426 (*Oryza sativa*, rótulo PT "Arroz": NCBI 4530, GRIN 26077).
- Cuidado: rótulos podem sofrer vandalismo (o rótulo EN de Q161426 estava incorreto
  na data da consulta) — importar só IDs e nomes científicos, com data e revisão.
- Uso proposto: preencher `taxa.external_ids` (`wikidata:Q…;ncbi:…;col:…`).

## 5. Open Food Facts

- Escopo: produtos embalados (código de barras), taxonomias de categorias e
  ingredientes em `openfoodfacts-server/taxonomies`.
- Licenças: base **ODbL**, conteúdos **DbCL**, imagens **CC BY-SA**; código do
  servidor AGPL-3.0; licença específica dos arquivos de taxonomia **NV** (tratar como ODbL).
- Obrigação: base derivada usada publicamente deve sair em ODbL (share-alike) e com
  atribuição — exigiria **separar fisicamente** qualquer derivado OFF do catálogo.
- Decisão: fora de escopo ("não importar produtos de supermercado").

## 6. Fontes biológicas e agrícolas

- **Catalogue of Life**: release COL26.10 (2026-10-14) e XR 2026-10-16; licença "cc by"
  (versão **NV**). Exemplo: *Salmo salar* = `6XCXT`. Útil para validar nomes aceitos.
- **GBIF Backbone**: CC BY 4.0, mas **congelado desde 2023**; o GBIF passou a usar o
  COL XR (IDs alfanuméricos). Não adotar como referência nova.
- **GRIN Taxonomy**: CC0 1.0; *Oryza sativa* id 26077 com nome comum PT "arroz" e usos
  alimentares. Cultivares aparecem nos acessos de germoplasma, não na taxonomia.
- **FAO ASFIS** 2026.1 (13.965 espécies; códigos 3-alfa, nomes EN/FR/ES, sem PT).
  Termos gerais da FAO: CC BY 4.0 + termos adicionais; declaração do ASFIS **NV**.
- **FishBase**: CC BY-NC 4.0 → evitar se o produto puder ser comercial.

## 7. Fontes por domínio

- **Pescado (Brasil)**: Portaria MPA nº 532, de 23/09/2025 (revoga a IN MAPA 53/2020).
  Lista nomes comuns por espécie; exige nome científico para Salmonidae e Gadidae.
  Evidências usadas no catálogo: "Cação" = dezenas de tubarões; "Pescada" =
  *Cynoscion* spp.; "Abadejo" = *Genypterus* spp.; "Bacalhau" = *Gadus* spp.;
  "Porquinho" = *Balistes*/*Aluterus*/*Monacanthus*; "Manjuba", "Lambari",
  "Curimbatá", "Tucunaré", "Dourada" com gêneros. **Uso**: descrição/evidência dos
  nomes comerciais (`market_name`), nunca para escolher espécie de um registro que
  não a informa.
- **Cortes de carne**: não foi encontrada fonte aberta com licença clara que
  relacione cortes brasileiros e norte-americanos; o catálogo mantém dois sistemas
  (`cut_system=BR|US`) **sem equivalência**.
- **Queijos**: registros DOP/IGP (eAmbrosia) servem para origem protegida, não para
  composição; termo do site **NV**. O catálogo guarda `origin_region` como "origem do
  tipo" e **não infere autenticidade**. Sites comerciais de queijos não foram usados.
- **Cultivares/variedades** (arroz, feijão, manga, maçã): nomes vêm das fontes
  atuais; nenhum registro de cultivar externo foi consultado. Classes comerciais
  (carioca, preto) ficam como `market_class` sem rank biológico.

## Pendências de licença e próximos passos

1. Reconfirmar a licença do FlavorDB2 quando o site voltar (bloqueia redistribuição
   ampliada de dados de sabor).
2. Confirmar o termo oficial da TACO no site do NEPA.
3. Confirmar a licença específica do ASFIS e da taxonomia do Open Food Facts.
4. LanguaL e FoodEx2: licença **NV** → bloqueados.
5. Próximo passo técnico sugerido: importar `wikidata`/`col` IDs para `taxa.csv` e
   `FOODON:` xrefs para conceitos, em PR própria, com revisão por amostragem.
