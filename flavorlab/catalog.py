"""Catálogo canônico de alimentos: conceitos, variedades, partes, formas e mapeamentos.

Camada de domínio, independente da interface e das fontes. Os dados curados
ficam em ``data/catalog/*.csv`` (revisáveis em diff); o inventário de todas as
fontes (``source_inventory.csv``) é gerado por ``scripts/build_catalog.py``.

Entidades e IDs (estáveis, sem significado posicional, nunca IDs de fonte)::

    sl:group:<slug>       grupo alimentar (classificação de navegação)
    sl:taxon:<slug>       táxon biológico (espécie, gênero...)
    sl:ingredient:<slug>  conceito culinário (ingrediente, produto, prato, categoria)
    sl:variant:<slug>     variedade/tipo culinário/classe comercial de um conceito
    sl:part:<slug>        parte anatômica/botânica ou corte de um conceito
    sl:form:<slug>        forma: estado + forma física + preparo de um conceito/variante/parte

Relações estruturais vêm das colunas (``parent_id`` → ``is_a``;
``variant.concept_id`` → ``variant_of``; ``part.concept_id`` → ``part_of``;
``form.*`` → ``form_of``; ``scientific_taxon_id`` → ``taxon_of``). Relações
não estruturais (``derived_from``, ``dish_contains``, ``substitutable_with``)
ficam em ``relations.csv``.

Uso::

    from flavorlab.catalog import Catalog
    cat = Catalog.load()
    cat.variants("sl:ingredient:rice")
    cat.resolve_source("taco", "568")      # feijão preto cru
    cat.coverage(source="usda")
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import MISSING, dataclass, field, fields
from functools import cached_property
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "data" / "catalog"

# Limite de confiança: abaixo dele um mapeamento (automático ou curado) exige revisão.
CONFIDENCE_THRESHOLD = 0.85

ID_RE = re.compile(r"^sl:(group|taxon|ingredient|variant|part|form):[a-z0-9]+(?:_[a-z0-9]+)*$")
PREFIX_OF = {"group": "sl:group:", "taxon": "sl:taxon:", "concept": "sl:ingredient:",
             "variant": "sl:variant:", "part": "sl:part:", "form": "sl:form:"}

# --------------------------------------------------------------------------- vocabulários
ENTITY_TYPES = {
    "category",     # nó classificatório (ex.: "peixes", "feijões"); não é um alimento único
    "ingredient",   # ingrediente culinário de base (arroz, salmão-do-atlântico, tomate)
    "product",      # produto derivado com identidade própria (farinha, óleo, queijo, fubá)
    "dish",         # prato/receita composta (risoto, feijoada, arroz carreteiro)
    "market_name",  # nome comercial que cobre várias espécies (pescada, cação); sem espécie
}
CONCEPT_STATUS = {"active", "provisional"}
VARIANT_KINDS = {
    "market_class",    # classe comercial (feijão carioca, preto, rajado)
    "culinary_type",   # tipo culinário/varietal (basmati, arbório, milho-pipoca)
    "cultivar",        # cultivar registrada
    "cultivar_group",  # grupo de cultivares
    "cheese_type",     # tipo de queijo (parmesão, minas frescal)
    "grain_class",     # classe de grão (longo, médio, curto)
    "color_type",      # tipo por cor quando é só isso que a fonte informa
    "commercial_grade",  # classificação comercial (arroz tipo 1/tipo 2)
}
BIOLOGICAL_RANKS = {"kingdom", "phylum", "class", "order", "family", "genus", "species",
                    "subspecies", "variety", "cultivar_group", "cultivar", "none", "unknown"}
STATES = {"raw", "cooked", "dried", "aged", "cured", "smoked", "canned", "fermented",
          "frozen", "fresh", "toasted", "processed", "unknown"}
PHYSICAL_FORMS = {"whole", "grain", "kernel", "flour", "meal", "grated", "shredded", "sliced",
                  "ground", "paste", "powder", "liquid", "flakes", "pieces", "puree", "block",
                  "spread", "cream", "popped", "sprouts", "unknown"}
HYDRATION = {"fresh", "dry", "rehydrated", "drained", "in_liquid", "not_applicable", "unknown"}
PART_KINDS = {"anatomical", "botanical", "cut", "organ", "product_fraction"}
MAPPING_TYPES = {"exact", "close", "broad", "narrow", "related"}
LEDGER_STATUSES = ("mapped_reviewed", "mapped_high_confidence", "mapped_low_confidence",
                   "ambiguous", "unmapped", "excluded_with_reason")
MAPPED_STATUSES = {"mapped_reviewed", "mapped_high_confidence", "mapped_low_confidence"}

# predicado -> (tipos de sujeito, tipos de objeto) aceitos (por prefixo de ID)
RELATION_RULES = {
    "derived_from": ({"concept", "variant", "form"}, {"concept", "variant", "part", "form"}),
    "dish_contains": ({"concept", "variant"}, {"concept", "variant", "part", "form"}),
    "substitutable_with": ({"concept", "variant", "form"}, {"concept", "variant", "form"}),
}
STRUCTURAL_PREDICATES = {"is_a", "variant_of", "part_of", "form_of", "taxon_of", "source_mapping"}


# --------------------------------------------------------------------------- tipos
@dataclass(frozen=True)
class FoodGroup:
    group_id: str
    name_pt: str
    name_en: str
    scope_note: str = ""
    sort_order: str = ""


@dataclass(frozen=True)
class Taxon:
    taxon_id: str
    scientific_name: str
    rank: str
    parent_taxon_id: str = ""
    common_name_pt: str = ""
    evidence: str = ""
    confidence: str = ""
    external_ids: str = ""


@dataclass(frozen=True)
class IngredientConcept:
    concept_id: str
    canonical_name_pt: str
    canonical_name_en: str
    entity_type: str
    parent_id: str
    food_group: str
    scientific_taxon_id: str
    description: str
    status: str
    aliases_pt: str = ""
    aliases_en: str = ""
    ambiguous_aliases: str = ""
    evidence: str = ""

    @property
    def entity_id(self) -> str:
        return self.concept_id


@dataclass(frozen=True)
class IngredientVariant:
    variant_id: str
    concept_id: str
    name_pt: str
    name_en: str
    variant_kind: str
    biological_rank: str
    origin_region: str
    attributes: str
    default_state: str
    confidence: str
    scientific_taxon_id: str = ""
    aliases_pt: str = ""
    aliases_en: str = ""
    evidence: str = ""

    @property
    def entity_id(self) -> str:
        return self.variant_id


@dataclass(frozen=True)
class CulinaryPart:
    part_id: str
    concept_id: str
    name_pt: str
    name_en: str
    anatomical_or_botanical_part: str
    cut_geometry: str
    edible_portion: str
    attributes: str
    aliases_pt: str = ""
    aliases_en: str = ""
    evidence: str = ""

    @property
    def entity_id(self) -> str:
        return self.part_id


@dataclass(frozen=True)
class IngredientForm:
    form_id: str
    concept_id: str
    variant_id: str
    part_id: str
    name_pt: str
    name_en: str
    state: str
    physical_form: str
    preparation: str
    hydration: str
    edible_portion: str
    attributes: str = ""
    evidence: str = ""

    @property
    def entity_id(self) -> str:
        return self.form_id


@dataclass(frozen=True)
class Relation:
    subject_id: str
    predicate: str
    object_id: str
    context: str = ""
    evidence: str = ""
    confidence: str = ""


@dataclass(frozen=True)
class SourceMapping:
    entity_id: str
    source: str
    source_id: str
    mapping_type: str
    confidence: float
    evidence: str
    reviewed_by: str = ""
    reviewed_at: str = ""
    curated_by: str = ""
    curated_at: str = ""
    rule: str = "curated"

    @property
    def needs_review(self) -> bool:
        return not self.reviewed_by and self.confidence < CONFIDENCE_THRESHOLD


@dataclass
class Resolution:
    """Resultado de ``resolve_source``. Ambíguo => ``entity_id`` vazio e candidatos preenchidos."""
    source: str
    source_id: str
    status: str
    entity_id: str = ""
    confidence: float = 0.0
    mapping_type: str = ""
    candidates: list[tuple[str, float]] = field(default_factory=list)
    rule: str = ""
    reason: str = ""

    @property
    def needs_review(self) -> bool:
        return self.status in {"mapped_low_confidence", "ambiguous", "unmapped"}

    @property
    def is_mapped(self) -> bool:
        return self.status in MAPPED_STATUSES


Entity = IngredientConcept | IngredientVariant | CulinaryPart | IngredientForm | FoodGroup | Taxon


def kind_of(entity_id: str) -> str:
    """'sl:variant:rice_basmati' -> 'variant' (concept para sl:ingredient:)."""
    for kind, prefix in PREFIX_OF.items():
        if entity_id.startswith(prefix):
            return kind
    return ""


def split_list(value: str) -> list[str]:
    return [v.strip() for v in str(value or "").split("|") if v.strip()]


def parse_attributes(value: str) -> dict[str, str]:
    """'milk=cow;texture=hard' -> {'milk': 'cow', 'texture': 'hard'}."""
    out = {}
    for item in str(value or "").split(";"):
        if "=" in item:
            k, v = item.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _read(path: Path, cls) -> list:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    names = {f.name for f in fields(cls)}
    missing = [f.name for f in fields(cls) if f.name not in df.columns
               and f.default is MISSING and f.default_factory is MISSING]  # obrigatórios
    if missing:
        raise ValueError(f"{path.name}: colunas ausentes {missing}")
    cols = [c for c in df.columns if c in names]
    return [cls(**{c: row[c].strip() for c in cols}) for row in df[cols].to_dict("records")]


# --------------------------------------------------------------------------- catálogo
class Catalog:
    """Catálogo em memória. ``Catalog.load()`` lê ``data/catalog``."""

    def __init__(self, groups, taxa, concepts, variants, parts, forms, relations, mappings,
                 sources: pd.DataFrame | None = None, inventory: pd.DataFrame | None = None,
                 exclusions: pd.DataFrame | None = None):
        self.groups: dict[str, FoodGroup] = {g.group_id: g for g in groups}
        self.taxa: dict[str, Taxon] = {t.taxon_id: t for t in taxa}
        self.concepts: dict[str, IngredientConcept] = {c.concept_id: c for c in concepts}
        self.variant_rows: dict[str, IngredientVariant] = {v.variant_id: v for v in variants}
        self.part_rows: dict[str, CulinaryPart] = {p.part_id: p for p in parts}
        self.form_rows: dict[str, IngredientForm] = {f.form_id: f for f in forms}
        self.relation_rows: list[Relation] = list(relations)
        self.curated_mappings: list[SourceMapping] = list(mappings)
        self.sources = sources if sources is not None else pd.DataFrame()
        self.inventory = inventory
        self.exclusions = exclusions if exclusions is not None else pd.DataFrame(
            columns=["source", "source_id", "reason"])
        self._raw_counts = {"groups": len(groups), "taxa": len(taxa), "concepts": len(concepts),
                            "variants": len(variants), "parts": len(parts), "forms": len(forms)}

    # ------------------------------------------------------------------ carga
    @classmethod
    def load(cls, path: Path | str = CATALOG_DIR, with_inventory: bool = True) -> "Catalog":
        path = Path(path)
        mappings_df = pd.read_csv(path / "source_mappings.csv", dtype=str, keep_default_na=False)
        mappings = [SourceMapping(
            entity_id=r["entity_id"], source=r["source"], source_id=r["source_id"],
            mapping_type=r["mapping_type"], confidence=float(r["confidence"]), evidence=r["evidence"],
            reviewed_by=r.get("reviewed_by", ""), reviewed_at=r.get("reviewed_at", ""),
            curated_by=r.get("curated_by", ""), curated_at=r.get("curated_at", ""))
            for r in mappings_df.to_dict("records")]
        inv_path = path / "source_inventory.csv"
        inventory = (pd.read_csv(inv_path, dtype=str, keep_default_na=False)
                     if with_inventory and inv_path.exists() else None)
        excl_path = path / "source_exclusions.csv"
        exclusions = (pd.read_csv(excl_path, dtype=str, keep_default_na=False)
                      if excl_path.exists() else None)
        return cls(
            groups=_read(path / "food_groups.csv", FoodGroup),
            taxa=_read(path / "taxa.csv", Taxon),
            concepts=_read(path / "ingredient_concepts.csv", IngredientConcept),
            variants=_read(path / "ingredient_variants.csv", IngredientVariant),
            parts=_read(path / "culinary_parts.csv", CulinaryPart),
            forms=_read(path / "ingredient_forms.csv", IngredientForm),
            relations=_read(path / "relations.csv", Relation),
            mappings=mappings,
            sources=pd.read_csv(path / "sources.csv", dtype=str, keep_default_na=False),
            inventory=inventory, exclusions=exclusions,
        )

    # ------------------------------------------------------------------ acesso
    @cached_property
    def _entities(self) -> dict[str, Entity]:
        out: dict[str, Entity] = {}
        for table in (self.groups, self.taxa, self.concepts, self.variant_rows, self.part_rows,
                      self.form_rows):
            out.update(table)
        return out

    def __contains__(self, entity_id: str) -> bool:
        return entity_id in self._entities

    def __len__(self) -> int:
        return len(self.concepts) + len(self.variant_rows) + len(self.part_rows) + len(self.form_rows)

    def get(self, entity_id: str) -> Entity:
        try:
            return self._entities[entity_id]
        except KeyError:
            raise KeyError(f"entidade inexistente no catálogo: {entity_id}") from None

    def name(self, entity_id: str, lang: str = "pt") -> str:
        e = self.get(entity_id)
        if isinstance(e, IngredientConcept):
            return e.canonical_name_pt if lang == "pt" else e.canonical_name_en
        if isinstance(e, Taxon):
            return e.scientific_name
        return getattr(e, f"name_{lang}")

    def concept_of(self, entity_id: str) -> str:
        """Conceito ao qual uma variante/parte/forma pertence (ou o próprio conceito)."""
        e = self.get(entity_id)
        return e.concept_id if hasattr(e, "concept_id") else entity_id

    def food_group(self, entity_id: str) -> str:
        e = self.get(entity_id)
        if isinstance(e, FoodGroup):
            return e.group_id
        return self.concepts[self.concept_of(entity_id)].food_group

    @cached_property
    def _children(self) -> dict[str, list[str]]:
        ch: dict[str, list[str]] = defaultdict(list)
        for c in self.concepts.values():
            if c.parent_id:
                ch[c.parent_id].append(c.concept_id)
        for v in self.variant_rows.values():
            ch[v.concept_id].append(v.variant_id)
        for p in self.part_rows.values():
            ch[p.concept_id].append(p.part_id)
        for f in self.form_rows.values():
            ch[f.part_id or f.variant_id or f.concept_id].append(f.form_id)
        return ch

    def children(self, entity_id: str) -> list[str]:
        """Filhos estruturais diretos: subconceitos, variantes, partes e formas."""
        self.get(entity_id)
        return sorted(self._children.get(entity_id, []))

    def descendants(self, entity_id: str) -> list[str]:
        out, stack = [], list(self.children(entity_id))
        while stack:
            e = stack.pop()
            out.append(e)
            stack.extend(self._children.get(e, []))
        return sorted(set(out))

    def parent(self, entity_id: str) -> str:
        e = self.get(entity_id)
        if isinstance(e, IngredientConcept):
            return e.parent_id
        if isinstance(e, IngredientForm):
            return e.part_id or e.variant_id or e.concept_id
        return getattr(e, "concept_id", "")

    def ancestors(self, entity_id: str) -> list[str]:
        """Cadeia até a raiz (mais próximo primeiro). Para em ciclo, se houver."""
        out, seen, cur = [], {entity_id}, self.parent(entity_id)
        while cur and cur not in seen and cur in self:
            out.append(cur)
            seen.add(cur)
            cur = self.parent(cur)
        return out

    def variants(self, concept_id: str) -> list[IngredientVariant]:
        self.get(concept_id)
        return sorted((v for v in self.variant_rows.values() if v.concept_id == concept_id),
                      key=lambda v: v.variant_id)

    def forms(self, variant_id: str) -> list[IngredientForm]:
        """Formas de uma variante (ou de um conceito/parte: formas ligadas diretamente a ele)."""
        kind = kind_of(variant_id)
        self.get(variant_id)
        key = {"variant": "variant_id", "part": "part_id"}.get(kind, "concept_id")
        rows = [f for f in self.form_rows.values() if getattr(f, key) == variant_id]
        if kind == "concept":  # só as formas que não pertencem a variante/parte
            rows = [f for f in rows if not f.variant_id and not f.part_id]
        return sorted(rows, key=lambda f: f.form_id)

    def parts(self, concept_id: str) -> list[CulinaryPart]:
        self.get(concept_id)
        return sorted((p for p in self.part_rows.values() if p.concept_id == concept_id),
                      key=lambda p: p.part_id)

    def search_by_category(self, category_id: str) -> list[str]:
        """Entidades de um grupo alimentar (sl:group:...) ou descendentes de um conceito."""
        if kind_of(category_id) == "group":
            self.get(category_id)
            concepts = {c for c, row in self.concepts.items() if row.food_group == category_id}
            out = set(concepts)
            for c in concepts:
                out.update(e for e in self.descendants(c) if self.food_group(e) == category_id)
            return sorted(out)
        return self.descendants(category_id)

    # ------------------------------------------------------------------ relações
    def relations(self, entity_id: str | None = None, predicate: str | None = None) -> list[Relation]:
        """Relações estruturais (derivadas das colunas) + explícitas (relations.csv)."""
        rels = list(self.relation_rows)
        for c in self.concepts.values():
            if c.parent_id:
                rels.append(Relation(c.concept_id, "is_a", c.parent_id))
            if c.scientific_taxon_id:
                rels.append(Relation(c.scientific_taxon_id, "taxon_of", c.concept_id))
        for v in self.variant_rows.values():
            rels.append(Relation(v.variant_id, "variant_of", v.concept_id))
            if v.scientific_taxon_id:
                rels.append(Relation(v.scientific_taxon_id, "taxon_of", v.variant_id))
        for p in self.part_rows.values():
            rels.append(Relation(p.part_id, "part_of", p.concept_id))
        for f in self.form_rows.values():
            rels.append(Relation(f.form_id, "form_of", f.part_id or f.variant_id or f.concept_id))
        if entity_id is not None:
            rels = [r for r in rels if entity_id in (r.subject_id, r.object_id)]
        if predicate is not None:
            rels = [r for r in rels if r.predicate == predicate]
        return rels

    # ------------------------------------------------------------------ fontes
    @staticmethod
    def _split_key(source: str, source_id: str) -> tuple[str, str]:
        """Aceita ('taco', '568') ou ('taco', 'taco:568'); fdb/fg viram flavordb/flavorgraph."""
        alias = {"fdb": "flavordb", "fg": "flavorgraph"}
        source = alias.get(source, source)
        sid = str(source_id)
        if ":" in sid:
            sid = sid.split(":", 1)[1]
        return source, sid

    @cached_property
    def _inventory_index(self) -> dict[tuple[str, str], dict]:
        if self.inventory is None:
            return {}
        return {(r["source"], r["source_id"]): r for r in self.inventory.to_dict("records")}

    def mappings(self, entity_id: str, source: str | None = None,
                 include_auto: bool = True) -> list[SourceMapping]:
        """Mapeamentos curados (e, opcionalmente, automáticos do inventário) de uma entidade."""
        self.get(entity_id)
        out = [m for m in self.curated_mappings if m.entity_id == entity_id]
        if include_auto and self.inventory is not None:
            inv = self.inventory
            auto = inv[(inv["entity_id"] == entity_id) & (inv["rule"] != "curated")]
            out += [SourceMapping(entity_id=entity_id, source=r["source"], source_id=r["source_id"],
                                  mapping_type=r["mapping_type"], confidence=float(r["confidence"] or 0),
                                  evidence=r["reason"], rule=r["rule"])
                    for r in auto.to_dict("records")]
        if source is not None:
            source = self._split_key(source, "x")[0]
            out = [m for m in out if m.source == source]
        return out

    def resolve_source(self, source: str, source_id: str | int) -> Resolution:
        """Entidade canônica de um registro de fonte. Nunca escolhe silenciosamente entre candidatos."""
        source, sid = self._split_key(source, str(source_id))
        row = self._inventory_index.get((source, sid))
        if row is not None:
            cands = []
            for item in split_list(row["candidates"]):
                eid, _, score = item.rpartition("@")
                cands.append((eid, float(score or 0)))
            return Resolution(source, sid, row["status"], row["entity_id"],
                              float(row["confidence"] or 0), row["mapping_type"], cands,
                              row["rule"], row["reason"])
        curated = [m for m in self.curated_mappings if m.source == source and m.source_id == sid
                   and m.mapping_type != "related"]
        if len(curated) == 1:
            m = curated[0]
            status = ("mapped_reviewed" if m.reviewed_by else
                      "mapped_high_confidence" if m.confidence >= CONFIDENCE_THRESHOLD
                      else "mapped_low_confidence")
            return Resolution(source, sid, status, m.entity_id, m.confidence, m.mapping_type,
                              [(m.entity_id, m.confidence)], "curated", m.evidence)
        if len(curated) > 1:
            return Resolution(source, sid, "ambiguous", candidates=[(m.entity_id, m.confidence) for m in curated],
                              rule="curated", reason="mais de um mapeamento curado")
        return Resolution(source, sid, "unmapped", reason="registro fora do inventário carregado")

    def coverage(self, source: str | None = None, food_group: str | None = None,
                 status: str | None = None, by: Iterable[str] = ("source", "food_group", "status"),
                 ) -> pd.DataFrame:
        """Contagem de registros do inventário por fonte, grupo alimentar e status."""
        if self.inventory is None:
            raise RuntimeError("inventário não carregado: rode scripts/build_catalog.py")
        inv = self.inventory
        if source is not None:
            inv = inv[inv["source"] == self._split_key(source, "x")[0]]
        if food_group is not None:
            inv = inv[inv["food_group"] == food_group]
        if status is not None:
            inv = inv[inv["status"] == status]
        by = list(by)
        return (inv.groupby(by, dropna=False).size().rename("records").reset_index()
                .sort_values(by).reset_index(drop=True))

    def curation_queue(self, source: str | None = None) -> pd.DataFrame:
        """Registros que exigem curadoria: baixa confiança, ambíguos e não mapeados."""
        if self.inventory is None:
            raise RuntimeError("inventário não carregado")
        inv = self.inventory
        queue = inv[inv["status"].isin(["mapped_low_confidence", "ambiguous", "unmapped"])]
        if source is not None:
            queue = queue[queue["source"] == self._split_key(source, "x")[0]]
        return queue.reset_index(drop=True)

    # ------------------------------------------------------------------ validação
    def validate(self, source_records: pd.DataFrame | None = None) -> list[str]:
        """Lista de erros de integridade (vazia = catálogo válido).

        ``source_records`` (colunas source, source_id) permite conferir se os
        mapeamentos apontam para registros que existem nas fontes atuais.
        """
        errors: list[str] = []
        err = errors.append
        all_ids: list[str] = []
        for kind, table in (("group", self.groups), ("taxon", self.taxa), ("concept", self.concepts),
                            ("variant", self.variant_rows), ("part", self.part_rows),
                            ("form", self.form_rows)):
            for eid in table:
                all_ids.append(eid)
                if not ID_RE.match(eid):
                    err(f"ID fora do formato: {eid}")
                if not eid.startswith(PREFIX_OF[kind]):
                    err(f"ID {eid} na tabela errada ({kind})")
        dup = {i for i in all_ids if all_ids.count(i) > 1} if len(all_ids) != len(set(all_ids)) else set()
        for k, n in self._raw_counts.items():
            table = {"groups": self.groups, "taxa": self.taxa, "concepts": self.concepts,
                     "variants": self.variant_rows, "parts": self.part_rows, "forms": self.form_rows}[k]
            if len(table) != n:
                err(f"IDs duplicados em {k}")
        for i in sorted(dup):
            err(f"ID duplicado entre tabelas: {i}")

        for t in self.taxa.values():
            if t.rank not in BIOLOGICAL_RANKS:
                err(f"{t.taxon_id}: rank inválido {t.rank!r}")
            if t.parent_taxon_id and t.parent_taxon_id not in self.taxa:
                err(f"{t.taxon_id}: táxon pai inexistente {t.parent_taxon_id}")

        for c in self.concepts.values():
            if c.entity_type not in ENTITY_TYPES:
                err(f"{c.concept_id}: entity_type inválido {c.entity_type!r}")
            if c.status not in CONCEPT_STATUS:
                err(f"{c.concept_id}: status inválido {c.status!r}")
            if c.food_group not in self.groups:
                err(f"{c.concept_id}: grupo alimentar inexistente {c.food_group!r}")
            if c.scientific_taxon_id and c.scientific_taxon_id not in self.taxa:
                err(f"{c.concept_id}: táxon inexistente {c.scientific_taxon_id}")
            if c.entity_type == "market_name" and c.scientific_taxon_id:
                err(f"{c.concept_id}: nome comercial multiespécie não pode ter espécie única")
            if c.parent_id:
                if c.parent_id not in self:
                    err(f"{c.concept_id}: pai inexistente {c.parent_id}")
                elif kind_of(c.parent_id) != "concept":
                    err(f"{c.concept_id}: pai {c.parent_id} não é conceito (forma/variante/parte não pode ser pai)")
                elif c.entity_type == "dish" and self.concepts[c.parent_id].entity_type not in {"dish", "category"}:
                    err(f"{c.concept_id}: prato não pode ser subtipo do ingrediente {c.parent_id}")
                elif (c.entity_type != "dish" and c.entity_type != "category"
                      and self.concepts[c.parent_id].entity_type == "dish"):
                    err(f"{c.concept_id}: ingrediente não pode ser subtipo do prato {c.parent_id}")
            if not c.canonical_name_pt or not c.canonical_name_en:
                err(f"{c.concept_id}: nome canônico pt/en obrigatório")
        # ciclos na hierarquia de conceitos
        for cid in self.concepts:
            seen, cur = set(), cid
            while cur:
                if cur in seen:
                    err(f"ciclo na hierarquia a partir de {cid}")
                    break
                seen.add(cur)
                cur = self.concepts[cur].parent_id if cur in self.concepts else ""

        for v in self.variant_rows.values():
            if v.concept_id not in self.concepts:
                err(f"{v.variant_id}: conceito inexistente {v.concept_id}")
                continue
            if v.variant_kind not in VARIANT_KINDS:
                err(f"{v.variant_id}: variant_kind inválido {v.variant_kind!r}")
            if v.biological_rank not in BIOLOGICAL_RANKS:
                err(f"{v.variant_id}: biological_rank inválido {v.biological_rank!r}")
            if v.default_state and v.default_state not in STATES:
                err(f"{v.variant_id}: default_state inválido {v.default_state!r}")
            if self.concepts[v.concept_id].entity_type == "category":
                err(f"{v.variant_id}: variante de categoria {v.concept_id}; use um conceito concreto")
            if v.scientific_taxon_id and v.scientific_taxon_id not in self.taxa:
                err(f"{v.variant_id}: táxon inexistente {v.scientific_taxon_id}")
            if v.biological_rank in {"species", "subspecies", "variety"} and not v.scientific_taxon_id:
                err(f"{v.variant_id}: rank biológico {v.biological_rank} sem táxon")
            _check_conf(v.variant_id, v.confidence, err, required=True)

        for p in self.part_rows.values():
            if p.concept_id not in self.concepts:
                err(f"{p.part_id}: conceito inexistente {p.concept_id}")
            elif self.concepts[p.concept_id].entity_type == "dish":
                err(f"{p.part_id}: prato não tem partes anatômicas/botânicas")
            if p.anatomical_or_botanical_part not in PART_KINDS:
                err(f"{p.part_id}: tipo de parte inválido {p.anatomical_or_botanical_part!r}")

        for f in self.form_rows.values():
            if f.concept_id not in self.concepts:
                err(f"{f.form_id}: conceito inexistente {f.concept_id}")
            if f.variant_id:
                v = self.variant_rows.get(f.variant_id)
                if v is None:
                    err(f"{f.form_id}: variante inexistente {f.variant_id}")
                elif v.concept_id != f.concept_id:
                    err(f"{f.form_id}: variante {f.variant_id} não pertence a {f.concept_id}")
            if f.part_id:
                p = self.part_rows.get(f.part_id)
                if p is None:
                    err(f"{f.form_id}: parte inexistente {f.part_id}")
                elif p.concept_id != f.concept_id:
                    err(f"{f.form_id}: parte {f.part_id} não pertence a {f.concept_id}")
            if f.state not in STATES:
                err(f"{f.form_id}: estado inválido {f.state!r}")
            if f.physical_form not in PHYSICAL_FORMS:
                err(f"{f.form_id}: forma física inválida {f.physical_form!r}")
            if f.hydration not in HYDRATION:
                err(f"{f.form_id}: hidratação inválida {f.hydration!r}")

        derived_edges: dict[str, set[str]] = defaultdict(set)
        for r in self.relation_rows:
            rule = RELATION_RULES.get(r.predicate)
            if rule is None:
                err(f"relação com predicado inválido {r.predicate!r} ({r.subject_id})")
                continue
            for role, eid, allowed in (("sujeito", r.subject_id, rule[0]), ("objeto", r.object_id, rule[1])):
                if eid not in self:
                    err(f"{r.predicate}: {role} inexistente {eid}")
                elif kind_of(eid) not in allowed:
                    err(f"{r.predicate}: {role} {eid} de tipo {kind_of(eid)} não permitido")
            if r.subject_id == r.object_id:
                err(f"{r.predicate}: relação reflexiva em {r.subject_id}")
            if r.predicate == "dish_contains" and r.subject_id in self:
                if self.concepts.get(self.concept_of(r.subject_id), None) is None or \
                        self.concepts[self.concept_of(r.subject_id)].entity_type != "dish":
                    err(f"dish_contains: sujeito {r.subject_id} não é prato")
            if r.predicate == "substitutable_with" and (not r.context or not r.evidence):
                err(f"substitutable_with {r.subject_id}->{r.object_id} exige contexto e evidência")
            if r.predicate == "derived_from":
                derived_edges[r.subject_id].add(r.object_id)
            _check_conf(f"{r.predicate}:{r.subject_id}", r.confidence, err, required=False)
        if _has_cycle(derived_edges):
            err("ciclo em derived_from")

        registered = set(self.sources.get("source", pd.Series(dtype=str)))
        rec_keys = None
        if source_records is not None:
            rec_keys = set(zip(source_records["source"], source_records["source_id"]))
        for m in self.curated_mappings:
            tag = f"mapeamento {m.source}:{m.source_id}->{m.entity_id}"
            if m.entity_id not in self:
                err(f"{tag}: entidade inexistente")
            if m.source not in registered:
                err(f"{tag}: fonte não registrada em sources.csv")
            if m.mapping_type not in MAPPING_TYPES:
                err(f"{tag}: mapping_type inválido {m.mapping_type!r}")
            if not 0 <= m.confidence <= 1:
                err(f"{tag}: confiança fora de [0,1]")
            if not m.evidence:
                err(f"{tag}: evidência obrigatória")
            if rec_keys is not None and (m.source, m.source_id) not in rec_keys:
                err(f"{tag}: registro inexistente na fonte")
        seen_map = set()
        for m in self.curated_mappings:
            k = (m.entity_id, m.source, m.source_id)
            if k in seen_map:
                err(f"mapeamento duplicado {k}")
            seen_map.add(k)

        for col in ("source", "dataset", "version", "license", "url"):
            if col not in self.sources.columns:
                err(f"sources.csv sem coluna {col}")
            elif (self.sources[col].str.strip() == "").any():
                err(f"sources.csv com {col} vazio")
        return errors


def _check_conf(tag: str, value: str, err, required: bool) -> None:
    if value in ("", None):
        if required:
            err(f"{tag}: confiança obrigatória")
        return
    try:
        x = float(value)
    except ValueError:
        err(f"{tag}: confiança não numérica {value!r}")
        return
    if not 0 <= x <= 1:
        err(f"{tag}: confiança fora de [0,1]")


def _has_cycle(edges: dict[str, set[str]]) -> bool:
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = defaultdict(int)

    def visit(n: str) -> bool:
        color[n] = GRAY
        for m in edges.get(n, ()):
            if color[m] == GRAY or (color[m] == WHITE and visit(m)):
                return True
        color[n] = BLACK
        return False

    return any(color[n] == WHITE and visit(n) for n in list(edges))
