# [SaborLab] Catálogo universal de alimentos, ingredientes, variedades e formas

## Responsável e branch

Claude Code, em `claude/ingredient-catalog`. Abrir PR e não fazer merge.

## Problema

O repositório já contém 8.826 registros nutricionais e 7.588 ingredientes de
sabor. Queijo, arroz e feijão são apenas exemplos visíveis de um problema que
atinge todo o catálogo: as fontes trazem milhares de descrições planas e
heterogêneas. O mesmo ocorre com milho, trigo, peixes, frutos do mar, carnes,
aves, frutas, hortaliças, cogumelos, castanhas, sementes, ervas, especiarias,
óleos, bebidas e alimentos preparados. O sistema não distingue de forma
estruturada:

- conceito culinário: `arroz`, `milho`, `salmão`, `queijo`;
- variedade, espécie, cultivar ou tipo culinário: `basmati`, `milho-pipoca`,
  `salmão-do-atlântico`, `parmesão`;
- parte ou corte: filé, lombo, peito, folha, raiz, fruto, grão;
- espécie/cultivar quando conhecido;
- estado: cru, cozido, seco, maturado;
- forma: grão, farinha, ralado, pasta;
- produto ou prato: risoto, pão de queijo, arroz carreteiro;
- identificadores nutricionais e de sabor correspondentes.

O `data/dicionario_ingredientes.csv` tem 82 mapeamentos curados e apenas algumas
variedades. Correspondência por texto não é uma ontologia e não pode sustentar
recomendação, substituição ou contexto cultural.

## Objetivo

Criar um catálogo canônico, versionado e rastreável para **todos os registros das
fontes atuais**, conectando conceitos, espécies, variedades, partes, cortes,
formas e produtos culinários. O catálogo deve aceitar expansão contínua sem
alterar IDs existentes. Não copiar bases externas antes de confirmar licença,
compatibilidade e utilidade.

“Cobrir todos” nesta etapa significa:

1. inventariar 100% dos registros atuais;
2. mapear automaticamente apenas correspondências seguras;
3. preservar todos os não mapeados em uma fila explícita de curadoria;
4. medir cobertura por fonte, grupo alimentar, idioma e confiança;
5. fornecer estrutura para incorporar novos alimentos e fontes no futuro.

Não significa forçar uma classificação incorreta para obter 100% de mapeamento.

## Pesquisa obrigatória antes da implementação

Produzir `docs/research/ingredient-taxonomy-sources.md` comparando:

1. **TACO e USDA FoodData Central**, já presentes: composição e descrições;
2. **FlavorDB2 e FlavorGraph**, já presentes: sabor e associação culinária;
3. **FoodOn**, candidato a ontologia de alimentos e relações hierárquicas;
4. **Wikidata**, candidato CC0 para espécie, origem, relações e identificadores;
5. **Open Food Facts**, apenas como candidato para produtos embalados e suas
   taxonomias, considerando obrigações ODbL e separação de derivados;
6. fontes biológicas e agrícolas públicas, como Catalogue of Life, GBIF,
   GRIN/FAO, listas oficiais de espécies pesqueiras ou registros nacionais,
   somente se agregarem espécie/cultivar útil e tiverem licença compatível;
7. fontes específicas por domínio — pescados, cortes de carne, cultivares,
   queijos e fermentados — apenas após avaliação de licença e autoridade.

Para cada fonte: escopo, licença, versão, atualização, formato, idioma, IDs,
atribuição, restrições de redistribuição e exemplo de mapeamento. Não raspar
sites comerciais de queijos, receitas ou cultura. Licença incerta bloqueia a
importação e deve ser registrada como pendência.

## Modelo de dados

Definir dataclasses/tipos e tabelas independentes da interface:

```python
IngredientConcept(
    concept_id, canonical_name_pt, canonical_name_en,
    entity_type, parent_id, food_group, scientific_taxon_id,
    description, status
)

IngredientVariant(
    variant_id, concept_id, name_pt, name_en,
    variant_kind, biological_rank, origin_region, attributes,
    default_state, confidence
)

CulinaryPart(
    part_id, concept_id, name_pt, anatomical_or_botanical_part,
    cut_geometry, edible_portion, attributes
)

IngredientForm(
    form_id, variant_id, state, physical_form,
    preparation, hydration, edible_portion
)

SourceMapping(
    entity_id, source, source_id, mapping_type,
    confidence, evidence, reviewed_by, reviewed_at
)
```

IDs internos devem ser estáveis e sem significado posicional, por exemplo:

```text
sl:ingredient:rice
sl:variant:rice_basmati
sl:form:rice_basmati_cooked
sl:ingredient:atlantic_salmon
sl:part:atlantic_salmon_fillet
sl:ingredient:corn
sl:variant:corn_popcorn
```

Não usar índice de linha, nome traduzido ou ID de uma fonte como ID canônico.

## Relações mínimas

- `is_a`: parmesão é uma variedade/tipo de queijo;
- `variant_of`: basmati é variante de arroz;
- `taxon_of`: uma espécie biológica sustenta um conceito culinário;
- `part_of`: filé é parte/corte de um peixe; peito é parte de uma ave;
- `form_of`: arroz cozido é forma de uma variante/conceito;
- `derived_from`: farinha de arroz deriva de arroz;
- `dish_contains`: risoto contém arroz, mas não é variedade de arroz;
- `source_mapping`: entidade canônica corresponde a registros externos;
- `substitutable_with`: somente com contexto e evidência, nunca implícito.

Impedir ciclos e relações semanticamente inválidas.

## Cobertura obrigatória

### Inventário completo

Criar um ledger que contenha **cada registro** de TACO, USDA, FlavorDB e
FlavorGraph com um dos estados:

```text
mapped_reviewed
mapped_high_confidence
mapped_low_confidence
ambiguous
unmapped
excluded_with_reason
```

Cada linha deve manter fonte, ID, descrição original, grupo original, candidatos,
confiança, regra usada e motivo. O relatório de cobertura deve ser reproduzível
e falhar se um novo registro desaparecer do inventário.

### Grupos alimentares

O esquema, pipeline e amostra curada devem cobrir todos estes grupos:

- cereais e pseudocereais;
- leguminosas;
- tubérculos e raízes;
- hortaliças, folhas, flores e algas;
- frutas;
- cogumelos e outros fungos culinários;
- castanhas, sementes e derivados;
- ervas, especiarias, sais e condimentos;
- óleos e gorduras;
- leite, laticínios e queijos;
- ovos;
- bovinos, suínos, caprinos, ovinos e caça;
- aves;
- peixes, moluscos, crustáceos e outros frutos do mar;
- bebidas e infusões;
- açúcares e adoçantes;
- fermentados e conservas;
- produtos processados;
- pratos preparados e receitas compostas.

Para a primeira PR, curar um conjunto de referência distribuído, com pelo menos
200 entidades entre os grupos, sem concentrar a maioria em uma única família.
Esse conjunto é benchmark do pipeline, não limite do produto.

### Queijos

Incluir pelo menos 25 tipos realmente presentes nas fontes atuais, cobrindo:

- leite: vaca, cabra, ovelha, búfala ou mistura quando conhecido;
- família/processo: fresco, massa filada, azul, duro, semiduro, casca lavada;
- maturação e umidade quando houver fonte;
- origem geográfica como dado separado, sem inferir autenticidade;
- formas nutricionais distintas: inteiro, ralado, processado, cremoso.

### Arroz

Incluir pelo menos 15 entidades entre variedades e formas: branco, integral,
parboilizado, basmati, jasmim, arbório, negro, vermelho, selvagem e estados
cru/cozido quando a fonte os distinguir. Não tratar `integral` automaticamente
como cultivar; modelar corretamente como processamento/estado quando aplicável.

### Feijões

Incluir pelo menos 15 entidades: carioca, preto, fradinho, branco, vermelho,
rajado, jalo, roxo, azuki, mungo, lima e outros presentes nas fontes. Registrar
espécie separadamente do nome culinário e distinguir cru, cozido e enlatado.

### Milho

Cobrir conceito, espécies quando aplicável, milho-verde, milho seco, milho-pipoca,
farinha, fubá, canjica/hominy, amido, óleo e formas cozidas. Separar variedade,
processamento e prato preparado.

### Peixes e frutos do mar

Cobrir exemplos de água doce e salgada, espécie comercial quando conhecida,
origem selvagem/cultivo apenas quando a fonte informar, partes/cortes e formas
crua, cozida, defumada, seca e enlatada. Nome comercial ambíguo deve manter
candidatos, região e confiança; não escolher espécie por suposição.

### Demais grupos

Selecionar casos de referência de frutas, hortaliças, fungos, carnes, aves,
ovos, sementes, castanhas, ervas, especiarias, óleos, bebidas, fermentados e
alimentos preparados. Incluir casos difíceis: nomes regionais, homônimos,
ingredientes compostos, estados cru/cozido e produtos derivados.

## Arquivos propostos

```text
data/catalog/ingredient_concepts.csv
data/catalog/ingredient_variants.csv
data/catalog/ingredient_forms.csv
data/catalog/culinary_parts.csv
data/catalog/source_mappings.csv
data/catalog/source_inventory.csv
data/catalog/SOURCES.md
flavorlab/catalog.py
scripts/build_catalog.py
```

CSV é aceitável para a camada curada revisável; o build pode gerar Parquet para
consulta. Não colocar dumps externos grandes no Git.

## API mínima

```python
catalog.get(entity_id)
catalog.children(entity_id)
catalog.variants(concept_id)
catalog.forms(variant_id)
catalog.parts(concept_id)
catalog.resolve_source(source, source_id)
catalog.mappings(entity_id, source=None)
catalog.search_by_category(category_id)
catalog.coverage(source=None, food_group=None, status=None)
```

Resolução ambígua deve retornar candidatos e confiança, sem escolher o primeiro
silenciosamente.

## Validações e testes

1. IDs únicos, estáveis e no formato definido.
2. Nenhum pai inexistente e nenhum ciclo.
3. IDs TACO/USDA/FlavorDB/FlavorGraph apontam para registros existentes.
4. Uma forma não pode ser pai de um conceito.
5. Pratos preparados não aparecem como variedades.
6. `arroz integral` é modelado conforme a fonte, sem falsa espécie/cultivar.
7. Queijo parmesão conecta sabor e nutrição atuais.
8. Feijão preto cru e cozido continuam entidades nutricionais distintas sob um
   conceito/variante coerente.
9. Mapeamento automático abaixo do limite de confiança exige revisão.
10. Toda linha externa possui fonte, versão e licença registradas.
11. Todos os registros das fontes aparecem no ledger, inclusive não mapeados.
12. Nomes comerciais ambíguos de pescado não viram espécie sem evidência.
13. Milho-pipoca não é tratado como prato pronto nem sinônimo universal de milho.
14. Cortes de carne/peixe são partes, não variedades biológicas.
15. Relatório de cobertura apresenta contagens por grupo, fonte e status.
16. Toda a suíte existente continua passando.

## Fora de escopo

- revisar manualmente todos os alimentos do mundo em uma única PR;
- importar produtos de supermercado;
- sugerir receitas;
- traduzir automaticamente milhares de nomes;
- criar informações de textura ou cocção;
- assumir equivalência nutricional entre variedades.

## Critérios de aceite

- [ ] Pesquisa de fontes e licenças revisável.
- [ ] Esquema canônico independente das fontes.
- [ ] 100% dos registros atuais inventariados, sem perdas silenciosas.
- [ ] Amostra curada distribuída por todos os grandes grupos alimentares.
- [ ] Queijo, arroz, feijão, milho e pescados exercitam aspectos diferentes do modelo.
- [ ] Proveniência e confiança presentes em todos os mapeamentos.
- [ ] API e build documentados e testados.
- [ ] Sem dados inventados ou scraping incompatível.
- [ ] PR informa lacunas e decisões que exigem curadoria futura.

## Entrega

Abrir PR com commits separados para pesquisa/esquema, dados curados e API/testes.
Não alterar o recomendador ou a interface neste PR.
