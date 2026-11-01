# Fontes de dados e licenças

Este repositório é **privado** e de uso **não comercial**. Algumas fontes só
permitem esse tipo de uso — atenção antes de tornar o repositório público ou
usar os dados num produto comercial.

| Fonte | O que traz | Licença | Como obter |
|---|---|---|---|
| **FlavorDB2** — CosyLab, IIIT-Delhi | ~936 ingredientes naturais, ~2,3 mil moléculas de sabor ligadas a eles, com propriedades físico-químicas e descritores de odor/sabor (FEMA, FooDB, Flavornet) | **CC BY-NC-SA 3.0** (atribuição, não comercial, compartilha igual) | `python scripts/download_flavordb.py` |
| **FlavorGraph** — Park et al. (Korea Univ. / Sony AI) | Grafo de 6.653 ingredientes (de >1 milhão de receitas, Recipe1M) + 1.645 compostos; co-ocorrência ingrediente–ingrediente e ligações ingrediente–composto | **Apache 2.0** | `python scripts/download_flavorgraph.py` |
| **FooDB** — The Metabolomics Innovation Centre | ~70 mil compostos em ~1.000 alimentos, com **concentrações** | Uso livre não comercial; uso comercial exige permissão | **Manual** (ver abaixo) |

## FooDB — download manual

O site `foodb.ca` bloqueia downloads automatizados (desafio anti-robô), então
não dá para baixar daqui. Para incluir:

1. No seu navegador, acesse <https://foodb.ca/downloads>.
2. Baixe o pacote **CSV** (≈ 1 GB compactado).
3. Extraia em `data/raw/foodb/` (essa pasta está no `.gitignore`, fica só local).

O FlavorDB já traz, por molécula, o `foodb_id` e o perfil de sabor vindo do
FooDB — o FooDB completo acrescenta principalmente **teores** (mg/100 g), útil
para ponderar a contribuição de cada molécula.

## Citações

- Garg N. et al. *FlavorDB: a database of flavor molecules.* Nucleic Acids
  Research 46, D1210–D1216 (2018). <https://cosylab.iiitd.edu.in/flavordb2/>
- Park D. et al. *FlavorGraph: a large-scale food-chemical graph for
  generating food representations and recommending food pairings.*
  Scientific Reports 11, 931 (2021). <https://github.com/lamypark/FlavorGraph>
- Ahn Y.-Y. et al. *Flavor network and the principles of food pairing.*
  Scientific Reports 1, 196 (2011). — artigo que originou a hipótese de
  "food pairing" por compostos compartilhados.
- FooDB: <https://foodb.ca>
