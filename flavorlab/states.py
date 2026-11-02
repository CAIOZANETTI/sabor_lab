"""Estado real de um ingrediente, transições auditáveis e adaptador de receitas antigas.

Princípios (demanda 005):

* Todo valor conhecido vem de um ``EvidenceClaim`` (``flavorlab.evidence``) cujo
  ``predicate`` é o nome do campo e cujo ``subject_id`` é a instância do ingrediente.
  Não existe valor sem origem.
* Ausência é ``None`` + ``FieldKnowledge(status="unknown")``. Nunca zero, string
  vazia ou média genérica.
* ``transition_state`` é pura: devolve uma nova versão, preserva a anterior e
  registra o evento. Ela aplica apenas o que o evento e seus claims informam; o que
  a técnica *costuma* mudar e não foi informado vira ``uncertain`` — nunca um valor
  presumido. Uma transformação provável não é declarada como ocorrida.
* Ponto (``doneness``) é observação contextual ("rosada" para carne), nunca uma
  temperatura implícita.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field, fields, replace
from fractions import Fraction
from typing import Any, Iterable, Mapping

from .evidence import EvidenceClaim, EvidenceError, EvidenceStore, new_claim
from .units import MASS_G, VOLUME_ML, classify, fahrenheit_to_celsius, norm_unit


# --------------------------------------------------------------------------- vocabulários
@dataclass(frozen=True)
class Vocabulary:
    """Vocabulário controlado e versionado; ``extend`` cria nova versão, não altera a atual."""
    name: str
    version: int
    terms: frozenset

    def __contains__(self, term: object) -> bool:
        return term in self.terms

    def extend(self, *terms: str) -> "Vocabulary":
        new = frozenset(t for t in terms if t not in self.terms)
        if not new:
            return self
        return Vocabulary(self.name, self.version + 1, self.terms | new)


PREPARATION_STATES = Vocabulary("preparation_state", 1, frozenset("""
raw cooked baked roasted grilled fried sauteed steamed boiled pressure_cooked fermented
marinated cured smoked dried frozen thawed reheated mixed unknown""".split()))
STORAGE_STATES = Vocabulary("storage_state", 1, frozenset(
    "freshly_prepared ambient refrigerated frozen thawed unknown".split()))
COOKING_METHODS = Vocabulary("cooking_method", 1, frozenset("""
air_fryer oven convection_oven stovetop_pan grill broiler boiling steaming pressure_cooker
deep_fryer sous_vide microwave smoker raw_preparation unknown""".split()))
EVENT_KINDS = Vocabulary("event_kind", 1, frozenset(
    "cook reheat store thaw rest cut mix marinate measure observe".split()))
KNOWLEDGE_STATUS = ("known", "unknown", "uncertain", "not_applicable")

VOCABULARIES = {v.name: v for v in (PREPARATION_STATES, STORAGE_STATES, COOKING_METHODS, EVENT_KINDS)}

# campo -> unidade canônica (claims em outras unidades compatíveis são convertidos)
FIELD_UNITS = {
    "mass_g": "g", "storage_duration_s": "s", "measured_temperature_c": "°C",
    "process_temperature_c": "°C", "process_duration_s": "s", "moisture_fraction": "fraction",
    "yield_factor": "ratio",
}
TERM_FIELDS = {"preparation_state": PREPARATION_STATES, "storage_state": STORAGE_STATES,
               "cooking_method": COOKING_METHODS}
TRACKED_FIELDS = ("mass_g", "preparation_state", "cooking_method", "doneness", "storage_state",
                  "storage_duration_s", "measured_temperature_c", "process_temperature_c",
                  "process_duration_s", "moisture_fraction", "yield_factor", "texture_attributes")
LIST_PREDICATES = {"texture_attribute": "texture_attributes"}

# Campos que cada tipo de evento pode alterar. Se o evento não informar um novo valor,
# o valor anterior deixa de ser confiável e vira ``uncertain`` (sem valor presumido).
EVENT_EFFECTS = {
    "cook": {"mass_g", "preparation_state", "cooking_method", "doneness", "measured_temperature_c",
             "process_temperature_c", "process_duration_s", "moisture_fraction", "yield_factor",
             "texture_attributes", "storage_state", "storage_duration_s"},
    "reheat": {"mass_g", "preparation_state", "measured_temperature_c", "process_temperature_c",
               "process_duration_s", "moisture_fraction", "texture_attributes", "doneness",
               "storage_state", "storage_duration_s"},
    "store": {"storage_state", "storage_duration_s", "measured_temperature_c"},
    "thaw": {"storage_state", "storage_duration_s", "measured_temperature_c", "preparation_state", "moisture_fraction"},
    "rest": {"measured_temperature_c", "moisture_fraction"},
    "cut": {"texture_attributes"},
    "mix": {"mass_g", "moisture_fraction", "texture_attributes", "preparation_state"},
    "marinate": {"preparation_state", "moisture_fraction", "texture_attributes", "mass_g"},
    "measure": set(),
    "observe": set(),
}
# Toda medição de temperatura é instantânea: qualquer evento posterior a torna obsoleta.
INSTANTANEOUS = {"measured_temperature_c"}


class StateError(ValueError):
    """Estado, evento ou transição inválidos."""


# --------------------------------------------------------------------------- tipos
@dataclass(frozen=True)
class FieldKnowledge:
    status: str
    claim_ids: tuple[str, ...] = ()
    note: str | None = None

    def to_dict(self) -> dict:
        return {"status": self.status, "claim_ids": list(self.claim_ids), "note": self.note}

    @classmethod
    def from_dict(cls, d: Mapping) -> "FieldKnowledge":
        return cls(d["status"], tuple(d.get("claim_ids") or ()), d.get("note"))


UNKNOWN = FieldKnowledge("unknown")


@dataclass(frozen=True)
class Doneness:
    """Ponto observado, sempre com contexto (ex.: grupo/conceito do catálogo). Não é temperatura."""
    term: str
    context: str
    claim_id: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProcessEvent:
    """Algo que aconteceu (ou foi relatado) com uma instância de ingrediente.

    ``claim_ids`` aponta os claims que descrevem o resultado do evento (estado após,
    duração, temperatura de processo...). ``technique_id``/``equipment_id`` são
    referências opcionais para o grafo de preparo (demanda 003).
    """
    event_id: str
    instance_id: str
    kind: str
    claim_ids: tuple[str, ...] = ()
    technique_id: str | None = None
    equipment_id: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    planned: bool = False          # True = etapa planejada, ainda não executada
    notes: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["claim_ids"] = list(self.claim_ids)
        return d

    @classmethod
    def from_dict(cls, d: Mapping) -> "ProcessEvent":
        names = {f.name for f in fields(cls)}
        data = {k: v for k, v in d.items() if k in names}
        data["claim_ids"] = tuple(data.get("claim_ids") or ())
        return cls(**data)


@dataclass(frozen=True)
class IngredientState:
    instance_id: str                      # instância concreta (esta peça de fraldinha)
    entity_id: str | None                 # ID canônico do catálogo (demanda 002), se resolvido
    display_name: str
    mass_g: float | None = None
    preparation_state: str = "unknown"
    cooking_method: str | None = None
    doneness: Doneness | None = None
    storage_state: str = "unknown"
    storage_duration_s: float | None = None
    measured_temperature_c: float | None = None
    process_temperature_c: float | None = None
    process_duration_s: float | None = None
    moisture_fraction: float | None = None
    yield_factor: float | None = None
    texture_attributes: tuple[str, ...] = ()
    state_version: int = 1
    observations: tuple[str, ...] = ()    # claim_ids de observações humanas
    knowledge: Mapping[str, FieldKnowledge] = field(default_factory=dict)
    events: tuple[str, ...] = ()          # event_ids aplicados até esta versão
    parent_version: int | None = None
    legacy: Mapping[str, Any] | None = None   # campos originais de receita antiga (texto livre)

    def __post_init__(self):
        errors = validate_state(self)
        if errors:
            raise StateError("; ".join(errors))

    # ------------------------------------------------------------- conhecimento
    def status(self, name: str) -> str:
        return self.knowledge.get(name, UNKNOWN).status

    def known_fields(self) -> list[str]:
        return [f for f in TRACKED_FIELDS if self.status(f) == "known"]

    def unknown_fields(self) -> list[str]:
        return [f for f in TRACKED_FIELDS if self.status(f) == "unknown"]

    def uncertain_fields(self) -> list[str]:
        return [f for f in TRACKED_FIELDS if self.status(f) == "uncertain"]

    # ------------------------------------------------------------- serialização
    def to_dict(self) -> dict:
        d = {f.name: getattr(self, f.name) for f in fields(self)}
        d["doneness"] = self.doneness.to_dict() if self.doneness else None
        d["texture_attributes"] = list(self.texture_attributes)
        d["observations"] = list(self.observations)
        d["events"] = list(self.events)
        d["knowledge"] = {k: v.to_dict() for k, v in sorted(self.knowledge.items())}
        d["legacy"] = dict(self.legacy) if self.legacy is not None else None
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)

    @classmethod
    def from_dict(cls, d: Mapping) -> "IngredientState":
        data = dict(d)
        data["doneness"] = Doneness(**data["doneness"]) if data.get("doneness") else None
        for k in ("texture_attributes", "observations", "events"):
            data[k] = tuple(data.get(k) or ())
        data["knowledge"] = {k: FieldKnowledge.from_dict(v) for k, v in (data.get("knowledge") or {}).items()}
        return cls(**data)

    @classmethod
    def from_json(cls, text: str) -> "IngredientState":
        return cls.from_dict(json.loads(text))


def validate_state(s: IngredientState) -> list[str]:
    errors = []
    tag = f"{s.instance_id}@v{s.state_version}"
    if not s.instance_id:
        errors.append("instance_id obrigatório")
    for name, vocab in TERM_FIELDS.items():
        value = getattr(s, name)
        if value is not None and value not in vocab:
            errors.append(f"{tag}: {name} fora do vocabulário v{vocab.version}: {value!r}")
    for name in ("mass_g", "storage_duration_s", "process_duration_s"):
        v = getattr(s, name)
        if v is not None and v < 0:
            errors.append(f"{tag}: {name} negativo")
    if s.moisture_fraction is not None and not 0 <= s.moisture_fraction <= 1:
        errors.append(f"{tag}: moisture_fraction fora de [0, 1]")
    if s.yield_factor is not None and s.yield_factor <= 0:
        errors.append(f"{tag}: yield_factor deve ser positivo")
    if s.doneness is not None and not s.doneness.context:
        errors.append(f"{tag}: ponto exige contexto do alimento")
    for name, k in s.knowledge.items():
        if name not in TRACKED_FIELDS:
            errors.append(f"{tag}: conhecimento de campo desconhecido {name}")
        elif k.status not in KNOWLEDGE_STATUS:
            errors.append(f"{tag}: status inválido {k.status!r} em {name}")
    for name in TRACKED_FIELDS:
        value = getattr(s, name)
        empty = value is None or value == () or value == "unknown"
        status = s.status(name)
        if empty and status == "known":
            errors.append(f"{tag}: {name} marcado known sem valor")
        if not empty and status == "unknown":
            errors.append(f"{tag}: {name} tem valor mas status unknown")
        if not empty and not s.knowledge.get(name, UNKNOWN).claim_ids and s.legacy is None:
            errors.append(f"{tag}: {name} sem claim de origem")
    if s.state_version < 1 or (s.parent_version is not None and s.parent_version >= s.state_version):
        errors.append(f"{tag}: versão inválida")
    return errors


# --------------------------------------------------------------------------- claims -> valores
_TIME_S = {"s": 1.0, "sec": 1.0, "seg": 1.0, "min": 60.0, "h": 3600.0, "hora": 3600.0, "horas": 3600.0,
           "dia": 86400.0, "dias": 86400.0, "d": 86400.0}


def to_canonical(name: str, value: Any, unit: str | None) -> float:
    """Converte o valor de um claim para a unidade canônica do campo (preserva unidade explícita)."""
    target = FIELD_UNITS[name]
    if unit is None:
        raise StateError(f"{name}: valor numérico sem unidade")
    u = unit.strip()
    if target == "°C":
        if u in {"°C", "C", "degC"}:
            return float(value)
        if u in {"°F", "F", "degF"}:
            return fahrenheit_to_celsius(float(value))
    elif target == "s":
        factor = _TIME_S.get(norm_unit(u))
        if factor is not None:
            return float(value) * factor
    elif target == "g":
        factor = MASS_G.get(norm_unit(u))
        if factor is not None:
            return float(value) * factor
    elif u == target:
        return float(value)
    raise StateError(f"{name}: unidade {unit!r} incompatível com {target}")


def _resolve_field(store: EvidenceStore, instance_id: str, name: str):
    """Valor + conhecimento de um campo a partir dos claims; conflito vira ``uncertain``."""
    best = store.best_available(instance_id, name)
    if best.selected is None:
        return None, UNKNOWN
    ids = tuple(c.claim_id for c in [best.selected, *best.alternatives])
    c = best.selected
    if c.value is None:
        return None, FieldKnowledge("unknown", ids, c.limitations)
    if name == "doneness":
        if not c.context:
            raise StateError(f"{c.claim_id}: ponto sem contexto do alimento")
        value = Doneness(str(c.value), c.context, c.claim_id)
    elif name in FIELD_UNITS:
        value = to_canonical(name, c.value, c.unit)
    else:
        value = c.value
    status = "uncertain" if best.conflict else "known"
    note = "fontes divergentes; selecionado pela regra de best_available" if best.conflict else None
    return value, FieldKnowledge(status, ids, note)


def state_from_claims(instance_id: str, entity_id: str | None, display_name: str,
                      claims: Iterable[EvidenceClaim], *, store: EvidenceStore | None = None) -> IngredientState:
    """Primeira versão de um estado a partir de claims sobre a instância."""
    store = store if store is not None else EvidenceStore()
    claims = list(claims)
    store.extend(claims)
    values, knowledge = _values_from_store(store, instance_id, [c.predicate for c in claims])
    obs = tuple(sorted(c.claim_id for c in store.for_subject(instance_id) if c.evidence_type == "human_observation"))
    return IngredientState(instance_id=instance_id, entity_id=entity_id, display_name=display_name,
                           observations=obs, knowledge=knowledge, **values)


def _values_from_store(store: EvidenceStore, instance_id: str, predicates: Iterable[str],
                       base: Mapping[str, Any] | None = None, base_knowledge: Mapping[str, FieldKnowledge] | None = None):
    values = dict(base or {})
    knowledge = dict(base_knowledge or {})
    for pred in sorted(set(predicates)):
        if pred in LIST_PREDICATES:
            target = LIST_PREDICATES[pred]
            claims = [c for c in store.for_subject(instance_id) if c.predicate == pred and c.value is not None]
            values[target] = tuple(sorted({str(c.value) for c in claims}))
            knowledge[target] = FieldKnowledge("known" if claims else "unknown", tuple(sorted(c.claim_id for c in claims)))
        elif pred in TRACKED_FIELDS:
            value, k = _resolve_field(store, instance_id, pred)
            values[pred] = value if value is not None else ("unknown" if pred in ("preparation_state", "storage_state") else None)
            knowledge[pred] = k
    for name in TRACKED_FIELDS:
        knowledge.setdefault(name, UNKNOWN)
    return values, knowledge


# --------------------------------------------------------------------------- transições
def transition_state(previous: IngredientState, event: ProcessEvent,
                     evidence: list[EvidenceClaim]) -> IngredientState:
    """Nova versão do estado após ``event``. Função pura: ``previous`` não é alterado.

    * campos informados por ``evidence`` (claims sobre a instância, citados em
      ``event.claim_ids``) são aplicados com sua origem;
    * campos que o tipo de evento pode alterar, mas não foram informados, viram
      ``uncertain`` com o valor anterior registrado na nota — sem valor presumido;
    * medições instantâneas (temperatura medida) ficam obsoletas após qualquer evento;
    * demais campos são mantidos.
    """
    if event.kind not in EVENT_KINDS:
        raise StateError(f"tipo de evento inválido: {event.kind!r}")
    if event.instance_id != previous.instance_id:
        raise StateError("evento de outra instância")
    if event.event_id in previous.events:
        raise StateError(f"evento já aplicado: {event.event_id}")
    by_id = {c.claim_id: c for c in evidence}
    missing = [cid for cid in event.claim_ids if cid not in by_id]
    if missing:
        raise StateError(f"claims do evento ausentes: {missing}")
    foreign = [c.claim_id for c in evidence if c.subject_id != previous.instance_id]
    if foreign:
        raise StateError(f"claims de outro sujeito: {foreign}")
    if event.planned:
        raise StateError("evento planejado não altera estado; registre-o no processo e aplique só ao executar")

    store = EvidenceStore()
    store.extend(by_id[cid] for cid in event.claim_ids)
    provided = {c.predicate for c in store.for_subject(previous.instance_id)}
    provided_fields = {LIST_PREDICATES.get(p, p) for p in provided}

    base = {f: getattr(previous, f) for f in TRACKED_FIELDS}
    knowledge = dict(previous.knowledge)
    affected = (EVENT_EFFECTS[event.kind] | (INSTANTANEOUS if event.kind != "measure" else set())) - provided_fields
    for name in sorted(affected):
        old = base[name]
        if old in (None, (), "unknown"):
            continue
        shown = old.term if isinstance(old, Doneness) else old
        base[name] = () if name == "texture_attributes" else ("unknown" if name in ("preparation_state", "storage_state") else None)
        knowledge[name] = FieldKnowledge(
            "uncertain", previous.knowledge.get(name, UNKNOWN).claim_ids,
            f"valor anterior {shown!r} pode ter mudado com o evento {event.event_id} ({event.kind}); não informado")

    # valores informados pelo evento: claims do evento sobrepõem os anteriores do mesmo campo
    values, knowledge = _values_from_store(store, previous.instance_id, provided, base, knowledge)
    obs = tuple(sorted(set(previous.observations) | {
        c.claim_id for c in store.for_subject(previous.instance_id) if c.evidence_type == "human_observation"}))
    return IngredientState(
        instance_id=previous.instance_id, entity_id=previous.entity_id, display_name=previous.display_name,
        state_version=previous.state_version + 1, parent_version=previous.state_version,
        observations=obs, knowledge=knowledge, events=previous.events + (event.event_id,),
        legacy=previous.legacy, **values)


class StateTracker:
    """Histórico auditável de versões por instância (nenhuma versão é sobrescrita)."""

    def __init__(self):
        self._versions: dict[str, dict[int, IngredientState]] = {}
        self._events: dict[str, ProcessEvent] = {}
        self.evidence = EvidenceStore()

    def record(self, state: IngredientState) -> IngredientState:
        versions = self._versions.setdefault(state.instance_id, {})
        if state.state_version in versions and versions[state.state_version] != state:
            raise StateError(f"versão {state.state_version} de {state.instance_id} já registrada")
        versions[state.state_version] = state
        return state

    def start(self, instance_id: str, entity_id: str | None, display_name: str,
              claims: Iterable[EvidenceClaim]) -> IngredientState:
        return self.record(state_from_claims(instance_id, entity_id, display_name, claims, store=self.evidence))

    def apply(self, event: ProcessEvent, evidence: list[EvidenceClaim]) -> IngredientState:
        current = self.current(event.instance_id)
        self.evidence.extend(evidence)
        new = transition_state(current, event, evidence)
        self._events[event.event_id] = event
        return self.record(new)

    def current(self, instance_id: str) -> IngredientState:
        versions = self._versions.get(instance_id)
        if not versions:
            raise StateError(f"instância sem estado: {instance_id}")
        return versions[max(versions)]

    def history(self, instance_id: str) -> list[IngredientState]:
        return [v for _, v in sorted(self._versions.get(instance_id, {}).items())]

    def event(self, event_id: str) -> ProcessEvent:
        return self._events[event_id]


# --------------------------------------------------------------------------- segurança (reuso)
def safety_assessment(state: IngredientState, *, perishable: bool | None = None, ambient_c: float | None = None,
                      elapsed_out_of_control_min: float | None = None, service_mode: str = "immediate_service"):
    """Delegação a ``flavorlab.food_safety``: usa só o que o estado conhece; o resto segue ``None``."""
    from .food_safety import check_food_safety
    temp = state.measured_temperature_c if state.status("measured_temperature_c") == "known" else None
    return check_food_safety(food_temperature_c=temp, elapsed_out_of_control_min=elapsed_out_of_control_min,
                             ambient_c=ambient_c, perishable=perishable, service_mode=service_mode)


# --------------------------------------------------------------------------- receitas antigas
LEGACY_SOURCE = "receita_ingredientes.csv"
# Só termos que *nomeiam* um estado; corte, forma física e textos livres ficam em ``legacy``.
LEGACY_PREPARATION = {
    "cru": "raw", "crua": "raw", "crus": "raw", "cruas": "raw", "cozido": "cooked", "cozida": "cooked",
    "assado": "roasted", "assada": "roasted", "frito": "fried", "frita": "fried", "refogado": "sauteed",
    "refogada": "sauteed", "grelhado": "grilled", "grelhada": "grilled", "cozido no vapor": "steamed",
    "congelado": "frozen", "congelada": "frozen", "descongelado": "thawed", "descongelada": "thawed",
    "defumado": "smoked", "defumada": "smoked", "seco": "dried", "seca": "dried", "fermentado": "fermented",
    "marinado": "marinated", "marinada": "marinated", "curado": "cured", "curada": "cured",
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text)).strip()


def _quantity(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and value != value):
        return None
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(sum(Fraction(p) for p in text.split()))
    except (ValueError, ZeroDivisionError):
        return None


def resolve_catalog_entity(name: str, catalog=None) -> tuple[str | None, list[str]]:
    """Nome em português -> ID do catálogo por igualdade de nome/apelido (nunca por aproximação).

    Retorna (id, candidatos). Mais de um candidato não é escolhido: id fica ``None``.
    """
    if catalog is None:
        return None, []
    from .catalog import split_list
    key = _norm(name)
    hits = set()
    for c in catalog.concepts.values():
        if key in {_norm(n) for n in [c.canonical_name_pt, *split_list(c.aliases_pt)]}:
            hits.add(c.concept_id)
    for v in catalog.variant_rows.values():
        if key in {_norm(n) for n in [v.name_pt, *split_list(v.aliases_pt)]}:
            hits.add(v.variant_id)
    for f in catalog.form_rows.values():
        if key == _norm(f.name_pt):
            hits.add(f.form_id)
    # um variante e seu próprio conceito com o mesmo nome: fica o mais específico
    for h in list(hits):
        if any(h in catalog.ancestors(o) for o in hits if o != h):
            hits.discard(h)
    ordered = sorted(hits)
    return (ordered[0] if len(ordered) == 1 else None), ordered


def from_legacy_line(row: Mapping[str, Any], *, recipe_id: str, line: int, catalog=None,
                     store: EvidenceStore | None = None) -> IngredientState:
    """Adapta uma linha de ``receita_ingredientes.csv`` sem inventar campos.

    * massa só quando a linha traz ``gramas`` ou unidade de massa (g, kg, oz, lb);
      volume e contagem ficam com massa desconhecida (a conversão por densidade é
      estimativa do módulo de nutrição, não um fato do estado);
    * ``preparo`` só vira ``preparation_state`` quando nomeia um estado ("cru",
      "frito"); cortes e textos ("picado", "amolecida", "infusão") ficam em ``legacy``;
    * temperatura, armazenamento, umidade e ponto permanecem desconhecidos.
    """
    store = store if store is not None else EvidenceStore()
    name = str(row.get("ingrediente") or row.get("nome") or "").strip()
    instance_id = f"recipe:{recipe_id}:line:{line}"
    entity_id, candidates = resolve_catalog_entity(name, catalog)
    claims: list[EvidenceClaim] = []
    method = f"quantidade da receita {recipe_id} ({LEGACY_SOURCE}, linha {line}); planejada, não pesada"
    grams = _quantity(row.get("gramas"))
    qty, unit = _quantity(row.get("quantidade")), str(row.get("unidade") or "").strip()
    kind, factor = classify(unit) if unit else ("desconhecida", None)
    if grams is not None:
        claims.append(new_claim(claim_id=f"{instance_id}:mass", subject_id=instance_id, predicate="mass_g",
                                value=grams, unit="g", evidence_type="human_observation", confidence="moderate",
                                method=method + "; coluna 'gramas'", observed_at=None,
                                limitations="valor declarado na receita"))
    elif qty is not None and kind == "massa":
        claims.append(new_claim(claim_id=f"{instance_id}:mass", subject_id=instance_id, predicate="mass_g",
                                value=qty, unit=unit, evidence_type="human_observation", confidence="moderate",
                                method=method + f"; {row.get('quantidade')} {unit} convertido por definição exata",
                                limitations="valor declarado na receita"))
    preparo = str(row.get("preparo") or "").strip()
    prep_state = LEGACY_PREPARATION.get(_norm(preparo))
    if prep_state:
        claims.append(new_claim(claim_id=f"{instance_id}:prep", subject_id=instance_id, predicate="preparation_state",
                                value=prep_state, unit=None, evidence_type="human_observation",
                                confidence="moderate", method=method + f"; preparo={preparo!r}",
                                limitations="termo da receita; não confirma execução"))
    state = state_from_claims(instance_id, entity_id, name, claims, store=store)
    legacy = {k: (None if row.get(k) is None or (isinstance(row.get(k), float) and row.get(k) != row.get(k))
                  else str(row.get(k))) for k in ("ingrediente", "quantidade", "unidade", "gramas", "preparo",
                                                    "momento", "nome_no_banco", "alimento", "observacoes")}
    legacy["recipe_id"] = recipe_id
    legacy["catalog_candidates"] = "|".join(candidates)
    knowledge = dict(state.knowledge)
    if kind == "volume" and grams is None and qty is not None:
        knowledge["mass_g"] = FieldKnowledge("unknown", (), f"volume informado ({row.get('quantidade')} {unit}); "
                                             "massa depende de densidade e não é preenchida no estado")
    elif kind == "contagem" and grams is None:
        knowledge["mass_g"] = FieldKnowledge("unknown", (), f"contagem informada ({row.get('quantidade')} {unit})")
    if preparo and not prep_state:
        knowledge["preparation_state"] = FieldKnowledge("unknown", (), f"preparo em texto livre: {preparo!r}")
    return replace(state, legacy=legacy, knowledge=knowledge)


def adapt_legacy_recipe(rows: Iterable[Mapping[str, Any]], recipe_id: str, *, catalog=None,
                        store: EvidenceStore | None = None) -> list[IngredientState]:
    store = store if store is not None else EvidenceStore()
    return [from_legacy_line(r, recipe_id=recipe_id, line=i, catalog=catalog, store=store)
            for i, r in enumerate(rows, start=1)]


__all__ = [
    "COOKING_METHODS", "Doneness", "EVENT_EFFECTS", "EVENT_KINDS", "FieldKnowledge", "IngredientState",
    "PREPARATION_STATES", "ProcessEvent", "STORAGE_STATES", "StateError", "StateTracker", "TRACKED_FIELDS",
    "Vocabulary", "adapt_legacy_recipe", "from_legacy_line", "resolve_catalog_entity", "safety_assessment",
    "state_from_claims", "to_canonical", "transition_state", "validate_state", "EvidenceError",
]
