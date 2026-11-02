# [SaborLab] Catálogo canônico de ingredientes, variedades e formas

## Responsável e branch

Claude Code, em `claude/ingredient-catalog`. Abrir PR e não fazer merge.

## Problema

O repositório já contém 8.826 registros nutricionais e 7.588 ingredientes de
sabor. As buscas atuais encontram centenas de descrições relacionadas a queijo,
arroz e feijão, mas elas são registros planos de fontes diferentes. O sistema
não distingue de forma estruturada:

- conceito culinário: `arroz`;
- variedade: `basmati`, `arbório`, `jasmim`, `integral`;
- espécie/cultivar quando conhecido;
- estado: cru, cozido, seco, maturado;
- forma: grão, farinha, ralado, pasta;
- produto ou prato: risoto, pão de queijo, arroz carreteiro;
- identificadores nutricionais e de sabor correspondentes.

O `data/dicionario_ingredientes.csv` tem 82 mapeamentos curados e apenas algumas
variedades. Correspondência por texto não é uma ontologia e não pode sustentar
recomendação, substituição ou contexto cultural.

## Objetivo

Criar um catálogo canônico, versionado e rastreável que conecte conceitos e
variedades culinárias às fontes existentes, sem copiar bases externas antes de
confirmar licença, compatibilidade e utilidade.

## Pesquisa obrigatória antes da implementação

Produzir `docs/research/ingredient-taxonomy-sources.md` comparando:

1. **TACO e USDA FoodData Central**, já presentes: composição e descrições;
2. **FlavorDB2 e FlavorGraph**, já presentes: sabor e associação culinária;
3. **FoodOn**, candidato a ontologia de alimentos e relações hierárquicas;
4. **Wikidata**, candidato CC0 para espécie, origem, relações e identificadores;
5. **Open Food Facts**, apenas como candidato para produtos embalados e suas
   taxonomias, considerando obrigações ODbL e separação de derivados;
6. fontes agrícolas públicas, como GRIN/FAO ou registros nacionais, somente se
   agregarem espécie/cultivar útil ao consumidor.

Para cada fonte: escopo, licença, versão, atualização, formato, idioma, IDs,
atribuição, restrições de redistribuição e exemplo de mapeamento. Não raspar
sites comerciais de queijos, receitas ou cultura. Licença incerta bloqueia a
importação e deve ser registrada como pendência.

## Modelo de dados

Definir dataclasses/tipos e tabelas independentes da interface:

```python
IngredientConcept(
    concept_id, canonical_name_pt, canonical_name_en,
    parent_id, food_group, scientific_taxon_id,
    description, status
)

IngredientVariant(
    variant_id, concept_id, name_pt, name_en,
    variety_type, origin_region, attributes,
    default_state, confidence
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
```

Não usar índice de linha, nome traduzido ou ID de uma fonte como ID canônico.

## Relações mínimas

- `is_a`: parmesão é uma variedade/tipo de queijo;
- `variant_of`: basmati é variante de arroz;
- `form_of`: arroz cozido é forma de uma variante/conceito;
- `derived_from`: farinha de arroz deriva de arroz;
- `dish_contains`: risoto contém arroz, mas não é variedade de arroz;
- `source_mapping`: entidade canônica corresponde a registros externos;
- `substitutable_with`: somente com contexto e evidência, nunca implícito.

Impedir ciclos e relações semanticamente inválidas.

## Cobertura inicial obrigatória

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

## Arquivos propostos

```text
data/catalog/ingredient_concepts.csv
data/catalog/ingredient_variants.csv
data/catalog/ingredient_forms.csv
data/catalog/source_mappings.csv
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
catalog.resolve_source(source, source_id)
catalog.mappings(entity_id, source=None)
catalog.search_by_category(category_id)
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
11. Toda a suíte existente continua passando.

## Fora de escopo

- cobrir todos os alimentos do mundo;
- importar produtos de supermercado;
- sugerir receitas;
- traduzir automaticamente milhares de nomes;
- criar informações de textura ou cocção;
- assumir equivalência nutricional entre variedades.

## Critérios de aceite

- [ ] Pesquisa de fontes e licenças revisável.
- [ ] Esquema canônico independente das fontes.
- [ ] Cobertura mínima de queijo, arroz e feijão concluída.
- [ ] Proveniência e confiança presentes em todos os mapeamentos.
- [ ] API e build documentados e testados.
- [ ] Sem dados inventados ou scraping incompatível.
- [ ] PR informa lacunas e decisões que exigem curadoria futura.

## Entrega

Abrir PR com commits separados para pesquisa/esquema, dados curados e API/testes.
Não alterar o recomendador ou a interface neste PR.
