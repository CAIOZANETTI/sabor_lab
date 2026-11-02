"""Inventário das fontes e mapeamento seguro para o catálogo canônico.

Algoritmo, separado do domínio (``catalog.py``) e dos dados (``data/catalog``):

1. ``load_source_records`` lê **todos** os registros atuais das fontes
   (TACO, USDA, FlavorDB, FlavorGraph) a partir das tabelas processadas.
2. ``build_inventory`` classifica cada registro em um dos estados do ledger:
   mapeamento curado > exclusão curada > regra lexical conservadora > não mapeado.
3. A regra lexical só aceita correspondência quando todas as palavras que
   definem a identidade do registro são explicadas pelo apelido da entidade,
   por um ancestral dela ou por qualificadores de estado/preparo. Na dúvida, o
   registro fica ``ambiguous`` ou ``unmapped`` com candidatos e motivo.

Nomes de fontes: ``taco``, ``usda``, ``flavordb``, ``flavorgraph``.
``source_id`` é o código nativo (sem prefixo): TACO ``568``, USDA ``173734``
(fdc_id), FlavorDB ``55`` (entity_id), FlavorGraph ``5431`` (node_id).
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .catalog import (CONFIDENCE_THRESHOLD, LEDGER_STATUSES, Catalog, IngredientConcept,
                      split_list)

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"

LEDGER_COLUMNS = [
    "source", "source_id", "record_key", "source_dataset", "language", "original_description",
    "original_group", "food_group", "food_group_basis", "status", "entity_id", "mapping_type",
    "confidence", "candidates", "rule", "reason", "state_hint",
]
PREFIX = {"taco": "taco", "usda": "usda", "flavordb": "fdb", "flavorgraph": "fg"}

# --------------------------------------------------------------------------- normalização
STOPWORDS = {"de", "da", "do", "das", "dos", "e", "em", "a", "o", "as", "os", "com", "para", "ao", "na",
             "no", "and", "or", "of", "the", "in", "with", "a", "an", "to", "for", "type", "tipo"}

# Palavras que descrevem estado, preparo, corte genérico, tamanho ou teor e não mudam
# a identidade do alimento (não podem sozinhas criar nem bloquear correspondência).
QUALIFIERS = set("""
raw cooked fresh frozen dried dry canned boiled baked fried roasted grilled steamed smoked salted
unsalted sliced chopped diced minced grated shredded ground whole crushed peeled large small medium
plain regular low fat reduced nonfat skim lean light extra unsweetened sweetened boneless skinless
without enriched unenriched mature seed immature all types drained solid liquid
cut piece finely coarsely toasted uncooked prepared cold warm softened melted packed cubed halved
quartered pitted seeded trimmed thawed store bought homemade fine coarse good quality organic fat free
part lowfat milkfat moisture high fresh pack heat moist stewed braised broiled microwaved pan
cru crua crus cozido cozida cozidos assado assada frito frita grelhado grelhada fresco fresca
congelado congelada seco seca enlatado enlatada drenado drenada refogado refogada inteiro inteira
picado picada ralado ralada moido moida natural cozimento sem pele casca grande pequeno medio
""".split())

# Segmentos USDA que só trazem procedência, classe comercial ou recorte analítico ("fresh",
# "broilers or fryers", "imported", "separable lean only"): descartados antes de montar a janela.
NOISE = set("""
broiler fryer imported new zealand australian domestic variety meat by product retail cut composite
trimmed separable lean only choice select grade prime young tom hen roasting stewing capon all class
light dark commercial includes food usda distribution program alaska native navajo mixed species
""".split())

# Marcadores de produto derivado ou preparação composta fora do 1º segmento ("Caju, suco",
# "Iogurte, sabor morango", "Frango, filé, à milanesa"): o candidato é a origem, não a identidade.
DERIVED_MARKERS = {"suco", "juice", "doce", "molho", "sauce", "milanesa", "breaded", "empanado", "escabeche",
                   "pudding", "pie", "soup", "sopa", "jam", "geleia", "nectar", "drink", "bebida", "frosting",
                   "candied"}

STATE_WORDS = {
    "raw": {"raw", "uncooked", "cru", "crua", "crus", "fresh", "fresco", "fresca"},
    "cooked": {"cooked", "boiled", "baked", "fried", "roasted", "grilled", "steamed", "broiled", "braised",
               "stewed", "microwaved", "cozido", "cozida", "assado", "assada", "frito", "frita",
               "grelhado", "grelhada", "refogado", "refogada"},
    "canned": {"canned", "enlatado", "enlatada", "conserva"},
    "dried": {"dried", "dehydrated", "desidratado", "desidratada", "seco", "seca"},
    "smoked": {"smoked", "defumado", "defumada", "kippered"},
    "frozen": {"frozen", "congelado", "congelada"},
}


def strip_accents(text: str) -> str:
    return unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()


def _singular(tok: str) -> str:
    if len(tok) <= 3 or tok.endswith(("ss", "us", "is")):
        return tok
    if tok.endswith("ies") and len(tok) > 4:
        return tok[:-3] + "y"
    if tok.endswith("oes") and len(tok) > 4:
        return tok[:-2]
    if tok.endswith("s"):
        return tok[:-1]
    return tok


def tokens(text: str) -> list[str]:
    """'Feijão, preto, cru' -> ['feijao', 'preto', 'cru']; plurais simples viram singular."""
    text = strip_accents(str(text).lower()).replace("_", " ").replace("-", " ")
    raw = re.findall(r"[a-z0-9]+", text)
    return [_singular(t) for t in raw if t not in STOPWORDS and not t.isdigit()]


def norm_tokens(text: str) -> tuple[str, ...]:
    return tuple(tokens(text))


def state_hint(toks: list[str]) -> str:
    found = [s for s, words in STATE_WORDS.items() if words & set(toks)]
    return "|".join(found)


# --------------------------------------------------------------------------- grupos
# grupo original da fonte -> grupo do catálogo (sem sufixo "sl:group:")
SOURCE_GROUP_MAP = {
    # TACO
    "Cereais e derivados": "cereals", "Verduras, hortaliças e derivados": "vegetables",
    "Frutas e derivados": "fruits", "Gorduras e óleos": "fats_oils",
    "Pescados e frutos do mar": "seafood", "Carnes e derivados": "meat",
    "Leite e derivados": "dairy", "Bebidas (alcoólicas e não alcoólicas)": "beverages",
    "Ovos e derivados": "eggs", "Produtos açucarados": "sugars_sweeteners",
    "Miscelâneas": "herbs_spices_condiments", "Outros alimentos industrializados": "processed_products",
    "Alimentos preparados": "prepared_dishes", "Leguminosas e derivados": "legumes",
    "Nozes e sementes": "nuts_seeds",
    # USDA (categorias traduzidas em build_nutrition.py)
    "Bebidas alcoólicas": "beverages", "Bebidas": "beverages", "Alimentos infantis": "processed_products",
    "Panificados": "processed_products", "Carne bovina": "meat", "Cereais matinais": "processed_products",
    "Cereais e massas": "cereals", "Laticínios e ovos": "dairy", "Fast food": "prepared_dishes",
    "Óleos e gorduras": "fats_oils", "Peixes e frutos do mar": "seafood", "Frutas e sucos": "fruits",
    "Cordeiro, vitela e caça": "meat", "Leguminosas": "legumes", "Pratos prontos": "prepared_dishes",
    "Castanhas e sementes": "nuts_seeds", "Carne suína": "meat", "Aves": "poultry",
    "Comida de restaurante": "prepared_dishes", "Embutidos": "meat", "Salgadinhos": "processed_products",
    "Sopas e molhos": "prepared_dishes", "Especiarias e ervas": "herbs_spices_condiments",
    "Doces": "sugars_sweeteners", "Hortaliças": "vegetables",
    # FlavorDB
    "Fish": "seafood", "Seafood": "seafood", "Fruit": "fruits", "Berry": "fruits", "Fruit Citrus": "fruits",
    "Fruit-Berry": "fruits", "Fruit Essence": "fruits", "Dish": "prepared_dishes", "Herb": "herbs_spices_condiments",
    "Spice": "herbs_spices_condiments", "Dairy": "dairy", "Meat": "meat",
    "Beverage Alcoholic": "beverages", "Beverage": "beverages", "Beverage Caffeinated": "beverages",
    "Essential Oil": "herbs_spices_condiments", "Bakery": "cereals", "Additive": "herbs_spices_condiments",
    "Vegetable": "vegetables", "Cabbage": "vegetables", "Gourd": "vegetables", "Vegetable Fruit": "vegetables",
    "Vegetable Stem": "vegetables", "Flower": "vegetables", "Vegetable Root": "vegetables",
    "Vegetable Tuber": "tubers_roots", "Cereal": "cereals", "Maize": "cereals", "Legume": "legumes",
    "Nut": "nuts_seeds", "Seed": "nuts_seeds", "Fungus": "fungi",
    # FlavorGraph (dict_ingr2cate)
    "Plant/Vegetable": "vegetables", "Sauce/Powder/Dressing": "herbs_spices_condiments",
    "Bakery/Dessert/Snack": "processed_products", "Meat/Animal Product": "meat", "Nut/Seed": "nuts_seeds",
    "Beverage Alcoholic ": "beverages", "Dish/End Product": "prepared_dishes", "Essential Oil/Fat": "fats_oils",
}
# grupos de origem ambíguos demais para inferir algo (ficam por palavra-chave ou unknown)
AMBIGUOUS_SOURCE_GROUPS = {"Plant", "Plant Derivative", "ETC", "Cereal/Crop/Bean",
                           "Alimentos indígenas (EUA)", "Laticínios e ovos"}
# registros cujo grupo de origem indica prato/mistura: uma correspondência lexical com um
# ingrediente indica apenas "contém", nunca identidade
COMPOSITE_SOURCE_GROUPS = {"Fast food", "Comida de restaurante", "Pratos prontos", "Alimentos preparados",
                           "Alimentos infantis", "Dish", "Dish/End Product"}

# primeira palavra/cabeça do nome -> grupo (conservador; vale só para registros não mapeados)
KEYWORD_GROUPS = {
    "egg": "eggs", "ovo": "eggs", "cheese": "dairy", "queijo": "dairy", "milk": "dairy", "leite": "dairy",
    "yogurt": "dairy", "iogurte": "dairy", "butter": "dairy", "cream": "dairy", "soup": "prepared_dishes",
    "sopa": "prepared_dishes", "sauce": "herbs_spices_condiments", "molho": "herbs_spices_condiments",
    "gravy": "herbs_spices_condiments", "juice": "beverages", "suco": "beverages", "oil": "fats_oils",
    "oleo": "fats_oils", "chicken": "poultry", "frango": "poultry", "turkey": "poultry", "duck": "poultry",
    "goose": "poultry", "beef": "meat", "pork": "meat", "lamb": "meat", "veal": "meat", "fish": "seafood",
    "mushroom": "fungi", "cogumelo": "fungi", "babyfood": "processed_products", "bread": "cereals",
    "pao": "cereals", "flour": "cereals", "farinha": "cereals", "pasta": "cereals", "macarrao": "cereals",
    "potato": "tubers_roots", "batata": "tubers_roots", "cassava": "tubers_roots", "mandioca": "tubers_roots",
    "wine": "beverages", "vinho": "beverages", "beer": "beverages", "cerveja": "beverages", "tea": "beverages",
    "cha": "beverages", "coffee": "beverages", "cafe": "beverages", "sugar": "sugars_sweeteners",
    "acucar": "sugars_sweeteners", "syrup": "sugars_sweeteners", "honey": "sugars_sweeteners",
    "candy": "sugars_sweeteners", "candie": "sugars_sweeteners", "spice": "herbs_spices_condiments",
    "seed": "nuts_seeds", "nut": "nuts_seeds", "salad": "prepared_dishes", "sandwich": "prepared_dishes",
    "pizza": "prepared_dishes", "vinegar": "fermented_preserved", "vinagre": "fermented_preserved",
    "pickle": "fermented_preserved", "seaweed": "vegetables", "bean": "legumes", "feijao": "legumes",
    "lentil": "legumes", "rice": "cereals", "arroz": "cereals", "corn": "cereals", "milho": "cereals",
}


# --------------------------------------------------------------------------- registros
def load_source_records(processed: Path = PROCESSED) -> pd.DataFrame:
    """Todos os registros atuais: TACO e USDA (nutrição), FlavorDB e FlavorGraph (sabor)."""
    foods = pd.read_parquet(processed / "nutrition" / "foods.parquet")
    ing = pd.read_parquet(processed / "ingredients.parquet")
    nut = pd.DataFrame({
        "source": foods["fonte"].map(lambda f: "taco" if f == "taco" else "usda"),
        "source_id": foods["codigo"].astype(str),
        "source_dataset": foods["fonte"].map({"taco": "taco_4ed", "usda_sr_legacy": "usda_sr_legacy",
                                              "usda_foundation": "usda_foundation"}),
        "language": foods["fonte"].map(lambda f: "pt" if f == "taco" else "en"),
        "original_description": foods["nome"].astype(str),
        "original_group": foods["categoria"].fillna("").astype(str),
    })
    src = ing["source"]
    names = ing["name"].astype(object)
    missing = names.isna()
    if missing.any():
        # FlavorGraph tem um nó chamado literalmente "nan" (provável "naan"); o build de sabor o
        # converte em nulo. O inventário preserva o texto original do arquivo bruto.
        raw_nodes = processed.parent / "raw" / "flavorgraph" / "nodes_191120.csv"
        raw = (pd.read_csv(raw_nodes, dtype=str, keep_default_na=False).set_index("node_id")["name"]
               if raw_nodes.exists() else pd.Series(dtype=str))
        ids = ing.loc[missing, "ingredient_id"].str.split(":", n=1).str[1]
        names.loc[missing] = ids.map(raw).fillna("").to_numpy()
    flav = pd.DataFrame({
        "source": src,
        "source_id": ing["ingredient_id"].str.split(":", n=1).str[1],
        "source_dataset": src.map({"flavordb": "flavordb2", "flavorgraph": "flavorgraph_191120"}),
        "language": "en",
        "original_description": names.astype(str),
        "original_group": ing["category"].fillna("").astype(str),
        "synonyms": ing["synonyms"].fillna("").astype(str),
    })
    out = pd.concat([nut, flav], ignore_index=True)
    out["synonyms"] = out["synonyms"].fillna("")
    out["record_key"] = out["source"].map(PREFIX) + ":" + out["source_id"]
    if out["record_key"].duplicated().any():
        raise ValueError("registros de fonte duplicados")
    return out


# --------------------------------------------------------------------------- índice de apelidos
@dataclass(frozen=True)
class Alias:
    entity_id: str
    toks: tuple[str, ...]
    lang: str
    ambiguous: bool = False


def _entity_aliases(cat: Catalog) -> list[Alias]:
    out: list[Alias] = []

    def add(eid, names, lang, ambiguous=()):
        amb = {norm_tokens(a) for a in ambiguous}
        for n in names:
            t = norm_tokens(n)
            if t:
                out.append(Alias(eid, t, lang, t in amb))

    for c in cat.concepts.values():
        amb = split_list(c.ambiguous_aliases)
        add(c.concept_id, [c.canonical_name_pt] + split_list(c.aliases_pt), "pt", amb)
        add(c.concept_id, [c.canonical_name_en] + split_list(c.aliases_en), "en", amb)
    for v in cat.variant_rows.values():
        add(v.variant_id, [v.name_pt] + split_list(v.aliases_pt), "pt")
        add(v.variant_id, [v.name_en] + split_list(v.aliases_en), "en")
    for p in cat.part_rows.values():
        c = cat.concepts[p.concept_id]
        # partes só valem combinadas com o nome do conceito ("chicken breast", "peito de frango")
        for cn in [c.canonical_name_en] + split_list(c.aliases_en):
            for pn in [p.name_en] + split_list(p.aliases_en):
                if pn:
                    add(p.part_id, [f"{cn} {pn}"], "en")
        for cn in [c.canonical_name_pt] + split_list(c.aliases_pt):
            for pn in [p.name_pt] + split_list(p.aliases_pt):
                if pn:
                    add(p.part_id, [f"{pn} {cn}"], "pt")
    # apelido repetido em entidades diferentes (sem relação hierárquica) também é ambíguo
    by_toks: dict[tuple, set[str]] = defaultdict(set)
    for a in out:
        by_toks[(a.lang, a.toks)].add(a.entity_id)

    def unrelated(ids: set[str]) -> bool:
        ids = set(ids)
        return any(b not in cat.ancestors(a) and a not in cat.ancestors(b)
                   for a in ids for b in ids if a < b)

    shared = {k for k, ids in by_toks.items() if len(ids) > 1 and unrelated(ids)}
    return [Alias(a.entity_id, a.toks, a.lang, a.ambiguous or (a.lang, a.toks) in shared)
            for a in out]


class Matcher:
    """Correspondência lexical conservadora entre descrições de fonte e o catálogo."""

    def __init__(self, cat: Catalog):
        self.cat = cat
        self.aliases = _entity_aliases(cat)
        self.by_token: dict[tuple[str, str], list[Alias]] = defaultdict(list)
        for a in self.aliases:
            for t in set(a.toks):
                self.by_token[(a.lang, t)].append(a)
        # tokens de apelido de cada entidade e de seus ancestrais (explicam o "Fish," de "Fish, salmon")
        own: dict[str, set[str]] = defaultdict(set)
        for a in self.aliases:
            own[a.entity_id].update(a.toks)
        self.derived = derived = defaultdict(set)
        for r in cat.relation_rows:
            if r.predicate == "derived_from" and r.object_id in cat:
                derived[r.subject_id].add(r.object_id)
                derived[r.subject_id].update(cat.ancestors(r.object_id))
        self.lineage_tokens: dict[str, set[str]] = {}
        for eid in {a.entity_id for a in self.aliases}:
            toks = set(own[eid])
            for anc in [*cat.ancestors(eid), *derived.get(eid, ())]:
                toks |= own.get(anc, set())
            self.lineage_tokens[eid] = toks

    def _depth(self, eid: str) -> int:
        return len(self.cat.ancestors(eid))

    def candidates(self, description: str, lang: str, multi_segment: bool) -> list[tuple[Alias, float, str]]:
        """Lista (apelido, confiança, regra) aceitos pelas regras de identidade."""
        if multi_segment:
            # parênteses do USDA listam sinônimos/alternativas ("blackeyes, crowder, southern"):
            # não definem identidade e quebrariam a divisão por vírgulas
            text = re.sub(r"\([^)]*\)", " ", str(description))
            pairs = [(raw, tokens(raw)) for raw in text.split(",")]
            # descarta segmentos vazios ou só de qualificadores/procedência (exceto o 1º)
            pairs = [(r, t) for i, (r, t) in enumerate(pairs) if t and (i == 0 or not set(t) <= QUALIFIERS | NOISE)]
            if not pairs:
                return []
            segs = [t for _, t in pairs]
            joined = " ".join(r for r, _ in pairs[:3]).lower()
            compound = bool(re.search(r"\b(and|&|e)\b", joined))
            seg1 = segs[0]
            window = set(seg1).union(*segs[1:3]) if len(segs) > 1 else set(seg1)
            seg12 = set(seg1).union(*segs[1:2]) if len(segs) > 1 else set(seg1)
            seg2 = set(segs[1]) if len(segs) > 1 else set()
        else:
            seg1 = tokens(description)
            if not seg1:
                return []
            window = set(seg1)
            compound = bool(re.search(r"(^|[ _])(and|&)([ _]|$)", str(description).lower()))
        pool = {a for t in window for a in self.by_token.get((lang, t), [])}
        out = []
        for a in pool:
            at = set(a.toks)
            if not at <= window:
                continue
            explained = at | self.lineage_tokens.get(a.entity_id, set()) | QUALIFIERS
            if multi_segment and (window - set(seg1) - at) & DERIVED_MARKERS:
                continue  # tratado em match(): produto derivado
            if multi_segment:
                # cada palavra do 1º segmento (onde a fonte põe o "o que é") precisa ser explicada,
                # e ao menos uma delas pela própria entidade/linhagem (não só por qualificadores:
                # "Fat, beef tallow" não é carne bovina)
                if not set(seg1) <= explained:
                    continue
                if not set(seg1) & (at | self.lineage_tokens.get(a.entity_id, set())):
                    continue
                conf, rule = (0.9, "lexical_segments") if at <= seg12 else (0.75, "lexical_segments_extended")
                lineage = self.lineage_tokens.get(a.entity_id, set())
                if conf >= CONFIDENCE_THRESHOLD and seg2 - at - lineage - QUALIFIERS - NOISE:
                    # 2º segmento traz subtipo/preparo que o catálogo não explica ("Bread, naan",
                    # "Potatoes, mashed"): a entidade pode ser só a mais ampla — exige revisão
                    conf, rule = 0.8, "lexical_segments_unexplained_subtype"
            else:
                n = len(a.toks)
                if tuple(seg1[-n:]) != a.toks:  # cabeça no final (inglês): "rice flour" é farinha
                    continue
                prefix = seg1[:-n]
                unexplained = [t for t in prefix if t not in explained]
                if not prefix:
                    conf, rule = 0.95, "lexical_exact_name"
                elif not unexplained:
                    conf, rule = 0.88, "lexical_name_with_qualifiers"
                else:
                    conf, rule = 0.6, "lexical_head_match_unexplained_modifier"
            if compound and conf >= CONFIDENCE_THRESHOLD:
                # "pork and turkey", "with rice": pode ser mistura; exige revisão
                conf, rule = 0.7, rule + "_compound"
            out.append((a, conf, rule))
        return out

    def match(self, description: str, lang: str, multi_segment: bool) -> dict:
        cands = self.candidates(description, lang, multi_segment)
        if not cands and multi_segment:
            text = re.sub(r"\([^)]*\)", " ", str(description))
            segs = [tokens(x) for x in text.split(",")][:3]
            if set().union(*segs[1:]) & DERIVED_MARKERS if len(segs) > 1 else False:
                origin = self.candidates(segs[0] and text.split(",")[0], lang, True)
                cand_list = sorted({(a.entity_id, round(c, 2)) for a, c, _ in origin}, key=lambda x: (-x[1], x[0]))
                return {"status": "unmapped", "rule": "derived_product", "candidates": cand_list,
                        "reason": "produto derivado/preparação (suco, doce, molho, sabor...): candidato é a origem "
                                  "(derived_from), não a identidade"}
        if not cands:
            return {"status": "unmapped", "rule": "no_lexical_match", "reason": "nenhum apelido do catálogo explica o nome",
                    "candidates": []}
        # especificidade: mais palavras no apelido; depois entidade mais profunda
        best_len = max(len(a.toks) for a, _, _ in cands)
        top = [(a, c, r) for a, c, r in cands if len(a.toks) == best_len]
        by_entity: dict[str, tuple[float, str, bool]] = {}
        for a, c, r in top:
            prev = by_entity.get(a.entity_id)
            if prev is None or c > prev[0]:
                by_entity[a.entity_id] = (c, r, a.ambiguous)
        # se um candidato é ancestral (ou origem derived_from) de outro, fica o mais específico:
        # "Pork, cured, ham" -> presunto, não carne suína
        ids = list(by_entity)
        for e in ids:
            if any(e in self.cat.ancestors(o) or e in self.derived.get(o, ()) for o in ids if o != e):
                by_entity.pop(e, None)
        ranked = sorted(by_entity.items(), key=lambda kv: (-kv[1][0], -self._depth(kv[0]), kv[0]))
        cand_list = [(e, v[0]) for e, v in ranked]
        if len(ranked) > 1 or any(v[2] for _, v in ranked):
            return {"status": "ambiguous", "rule": "lexical_ambiguous",
                    "reason": "apelido compartilhado por entidades sem relação hierárquica; exige curadoria",
                    "candidates": cand_list}
        eid, (conf, rule, _) = ranked[0]
        concept = self.cat.concepts.get(self.cat.concept_of(eid))
        if concept is not None and concept.entity_type == "category" and eid == concept.concept_id:
            return {"status": "unmapped", "rule": "category_only", "candidates": cand_list,
                    "reason": "só a categoria foi reconhecida (ex.: 'Fish, ...'); falta conceito específico no catálogo"}
        return {"status": "mapped", "entity_id": eid, "confidence": conf, "rule": rule,
                "mapping_type": "broad", "candidates": cand_list,
                "reason": "registro é instância mais específica da entidade (estado/preparo/marca no registro)"}


# --------------------------------------------------------------------------- inventário
def _fmt_candidates(cands) -> str:
    return "|".join(f"{e}@{c:.2f}" for e, c in cands[:5])


def _keyword_group(description: str, lang: str, multi_segment: bool) -> str:
    if multi_segment:
        seg1 = tokens(str(description).split(",")[0])
    else:
        seg1 = tokens(description)
    if not seg1:
        return ""
    head = seg1[0] if lang == "pt" else seg1[-1]
    return KEYWORD_GROUPS.get(head, "")


def build_inventory(cat: Catalog, records: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por registro de fonte, com estado, candidatos, confiança, regra e motivo."""
    matcher = Matcher(cat)
    curated: dict[tuple[str, str], list] = defaultdict(list)
    for m in cat.curated_mappings:
        curated[(m.source, m.source_id)].append(m)
    excluded = {(r["source"], r["source_id"]): r["reason"] for r in cat.exclusions.to_dict("records")}

    rows = []
    for rec in records.to_dict("records"):
        key = (rec["source"], rec["source_id"])
        lang = rec["language"]
        multi = rec["source"] in {"taco", "usda"}
        desc = rec["original_description"]
        toks = tokens(desc)
        row = {c: rec.get(c, "") for c in LEDGER_COLUMNS}
        row.update(status="unmapped", entity_id="", mapping_type="", confidence="", candidates="",
                   rule="", reason="", state_hint=state_hint(toks), food_group="", food_group_basis="")

        primary = [m for m in curated.get(key, []) if m.mapping_type != "related"]
        related = [m for m in curated.get(key, []) if m.mapping_type == "related"]
        if related and not primary:
            row.update(status="unmapped", rule="curated_related", reason=related[0].evidence,
                       candidates=_fmt_candidates([(r.entity_id, r.confidence) for r in related]))
        elif primary:
            if len(primary) > 1:
                row.update(status="ambiguous", rule="curated",
                           candidates=_fmt_candidates([(m.entity_id, m.confidence) for m in primary]),
                           reason="mais de um mapeamento curado primário; escolher um")
            else:
                m = primary[0]
                status = ("mapped_reviewed" if m.reviewed_by else
                          "mapped_high_confidence" if m.confidence >= CONFIDENCE_THRESHOLD
                          else "mapped_low_confidence")
                row.update(status=status, entity_id=m.entity_id, mapping_type=m.mapping_type,
                           confidence=f"{m.confidence:.2f}", rule="curated", reason=m.evidence,
                           candidates=_fmt_candidates([(m.entity_id, m.confidence)]
                                                      + [(r.entity_id, r.confidence) for r in related]))
        elif key in excluded:
            row.update(status="excluded_with_reason", rule="curated_exclusion", reason=excluded[key])
        else:
            res = matcher.match(desc, lang, multi)
            if res["status"] == "unmapped" and rec.get("synonyms"):
                # FlavorDB: tenta os sinônimos publicados pela própria fonte
                for syn in split_list(rec["synonyms"].replace(",", "|")):
                    alt = matcher.match(syn, lang, False)
                    if alt["status"] == "mapped":
                        alt.update(rule="lexical_source_synonym", confidence=min(alt["confidence"], 0.8),
                                   reason=f"sinônimo da fonte '{syn}'")
                        res = alt
                        break
            composite = rec["original_group"] in COMPOSITE_SOURCE_GROUPS
            cand_str = _fmt_candidates(res.get("candidates", []))
            if res["status"] == "mapped":
                eid = res["entity_id"]
                is_dish = cat.concepts[cat.concept_of(eid)].entity_type == "dish"
                if composite and not is_dish:
                    row.update(status="unmapped", rule="composite_record", candidates=cand_str,
                               reason="registro de prato/mistura: candidato indica ingrediente contido "
                                      "(dish_contains), não identidade")
                else:
                    conf = res["confidence"]
                    row.update(status="mapped_high_confidence" if conf >= CONFIDENCE_THRESHOLD
                               else "mapped_low_confidence",
                               entity_id=eid, mapping_type=res["mapping_type"], confidence=f"{conf:.2f}",
                               candidates=cand_str, rule=res["rule"], reason=res["reason"])
            else:
                row.update(status=res["status"], candidates=cand_str, rule=res["rule"], reason=res["reason"])

        # grupo alimentar: entidade mapeada > candidatos concordantes > palavra-chave > grupo da fonte
        group, basis = "", ""
        if row["entity_id"]:
            group, basis = cat.food_group(row["entity_id"]), "entity"
        else:
            cg = {cat.food_group(e) for e, _ in (
                (c.rpartition("@")[0], 0) for c in split_list(row["candidates"])) if e in cat}
            if len(cg) == 1 and row["rule"] != "composite_record":
                group, basis = cg.pop(), "candidates"
        if not group:
            kw = _keyword_group(desc, lang, multi)
            if kw and rec["original_group"] not in COMPOSITE_SOURCE_GROUPS:
                group, basis = f"sl:group:{kw}", "keyword"
        if not group and rec["original_group"] and rec["original_group"] not in AMBIGUOUS_SOURCE_GROUPS:
            g = SOURCE_GROUP_MAP.get(rec["original_group"], "")
            if g:
                group, basis = f"sl:group:{g}", "source_group"
        row["food_group"] = group or "unknown"
        row["food_group_basis"] = basis or "none"
        rows.append(row)

    inv = pd.DataFrame(rows, columns=LEDGER_COLUMNS)
    assert set(inv["status"]) <= set(LEDGER_STATUSES)
    order = {s: i for i, s in enumerate(["taco", "usda", "flavordb", "flavorgraph"])}
    inv = inv.assign(_o=inv["source"].map(order), _n=pd.to_numeric(inv["source_id"], errors="coerce"))
    return inv.sort_values(["_o", "_n", "source_id"]).drop(columns=["_o", "_n"]).reset_index(drop=True)


def check_no_loss(previous: pd.DataFrame | None, current: pd.DataFrame) -> list[str]:
    """Chaves (fonte, id) que existiam no ledger anterior e sumiram no novo."""
    if previous is None or previous.empty:
        return []
    prev = set(zip(previous["source"], previous["source_id"]))
    cur = set(zip(current["source"], current["source_id"]))
    return sorted(f"{s}:{i}" for s, i in prev - cur)


def coverage_report(cat: Catalog, inv: pd.DataFrame) -> str:
    """Relatório Markdown reproduzível de cobertura (fonte, grupo, idioma, status, confiança)."""
    statuses = list(LEDGER_STATUSES)

    def table(by: str) -> str:
        t = pd.crosstab(inv[by], inv["status"]).reindex(columns=statuses, fill_value=0)
        t["total"] = t.sum(axis=1)
        mapped = t[["mapped_reviewed", "mapped_high_confidence", "mapped_low_confidence"]].sum(axis=1)
        t["% mapeado"] = (100 * mapped / t["total"]).round(1)
        t.loc["TOTAL"] = list(t[statuses + ["total"]].sum()) + [
            round(100 * t.loc[:, ["mapped_reviewed", "mapped_high_confidence", "mapped_low_confidence"]]
                  .to_numpy().sum() / t["total"].sum(), 1)]
        header = "| " + by + " | " + " | ".join(t.columns) + " |\n"
        header += "|" + "---|" * (len(t.columns) + 1) + "\n"
        body = "".join("| " + str(i) + " | " + " | ".join(
            str(int(v)) if c != "% mapeado" else f"{v:.1f}" for c, v in r.items()) + " |\n"
            for i, r in t.iterrows())
        return header + body

    conf = pd.to_numeric(inv["confidence"], errors="coerce")
    buckets = pd.cut(conf, [0, 0.5, 0.7, CONFIDENCE_THRESHOLD, 0.9, 1.0001], right=False,
                     labels=["<0.50", "0.50–0.69", f"0.70–{CONFIDENCE_THRESHOLD:.2f}",
                             f"{CONFIDENCE_THRESHOLD:.2f}–0.89", "≥0.90"])
    conf_tab = buckets.value_counts().sort_index()

    n_curated = {"conceitos": len(cat.concepts), "variantes": len(cat.variant_rows),
                 "partes": len(cat.part_rows), "formas": len(cat.form_rows), "táxons": len(cat.taxa),
                 "relações explícitas": len(cat.relation_rows), "mapeamentos curados": len(cat.curated_mappings)}
    ent_groups = pd.Series([cat.food_group(e) for e in list(cat.concepts) + list(cat.variant_rows)
                            + list(cat.part_rows) + list(cat.form_rows)]).value_counts()

    lines = ["# Cobertura do catálogo canônico de alimentos", "",
             "Gerado por `python scripts/build_catalog.py`. Não editar à mão.", "",
             f"- Registros inventariados: **{len(inv)}** "
             f"({', '.join(f'{s}: {n}' for s, n in inv['source'].value_counts().items())})",
             f"- Limite de confiança para mapeamento automático aceito: **{CONFIDENCE_THRESHOLD}**",
             "- " + ", ".join(f"{k}: {v}" for k, v in n_curated.items()), "",
             "## Por fonte", "", table("source"), "## Por grupo alimentar", "", table("food_group"),
             "## Por idioma da descrição original", "", table("language"),
             "## Por regra", "", "| regra | registros |", "|---|---|"]
    lines += [f"| {r} | {n} |" for r, n in inv["rule"].value_counts().items()]
    lines += ["", "## Confiança dos registros mapeados", "", "| faixa | registros |", "|---|---|"]
    lines += [f"| {b} | {n} |" for b, n in conf_tab.items()]
    lines += ["", "## Base da classificação por grupo", "", "| base | registros |", "|---|---|"]
    lines += [f"| {b} | {n} |" for b, n in inv["food_group_basis"].value_counts().items()]
    lines += ["", "## Entidades curadas por grupo alimentar", "", "| grupo | entidades |", "|---|---|"]
    lines += [f"| {g} | {n} |" for g, n in ent_groups.sort_index().items()]
    queue = inv[inv["status"].isin(["unmapped", "ambiguous", "mapped_low_confidence"])]
    heads = queue["original_description"].map(lambda d: " ".join(tokens(str(d).split(",")[0])[:2]))
    lines += ["", "## Fila de curadoria — cabeças de nome mais frequentes", "",
              "Registros `unmapped`, `ambiguous` e `mapped_low_confidence` (prioridade sugerida).", "",
              "| cabeça do nome | registros |", "|---|---|"]
    lines += [f"| {h} | {n} |" for h, n in heads.value_counts().head(40).items()]
    return "\n".join(lines) + "\n"
