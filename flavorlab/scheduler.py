"""Scheduler determinístico para o grafo de preparo (demanda 003).

Modelo de recursos:

* cada etapa ocupa seus equipamentos (``equipment_refs``) por toda a duração
  (ativa + passiva), respeitando a capacidade do recurso;
* o cozinheiro é um recurso: etapas ``active`` o ocupam durante a duração ativa
  (início da etapa); ``check`` e ``passive`` não o bloqueiam (``check`` gera
  pontos de verificação);
* preaquecimento é agendado o mais tarde possível para terminar exatamente quando
  a etapa que o consome começa (ou antes, se o recurso estiver ocupado);
* empates são desfeitos pela maior cauda de caminho crítico e depois por ``step_id``.

Tempos em segundos relativos ao início do processo. Tempos reais (``actual_*``)
ficam separados dos planejados (``planned_*``). Nenhum LLM participa.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Mapping

from .process import ProcessError, RecipeProcess, find_cycle


@dataclass
class ScheduledTask:
    step_id: str
    phase: str
    attention: str
    planned_start_s: float
    planned_end_s: float
    active_end_s: float
    resources: tuple[str, ...]
    actual_start_s: float | None = None
    actual_end_s: float | None = None
    status: str = "planned"             # planned | done | rescheduled

    @property
    def start_s(self) -> float:
        return self.actual_start_s if self.actual_start_s is not None else self.planned_start_s

    @property
    def end_s(self) -> float:
        return self.actual_end_s if self.actual_end_s is not None else self.planned_end_s


@dataclass
class Schedule:
    recipe_id: str
    tasks: dict[str, ScheduledTask]
    makespan_s: float
    critical_path: list[str]
    critical_path_s: float
    cook_active_s: float
    passive_s: float
    mise_en_place: list[str]
    cooking_sequence: list[str]
    parallel_groups: list[list[str]]
    resource_waits: dict[str, float]
    check_points: dict[str, list[float]]
    warnings: list[str] = field(default_factory=list)

    def order(self) -> list[str]:
        return sorted(self.tasks, key=lambda s: (self.tasks[s].start_s, s))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["units"] = {"time": "s"}
        return d


# --------------------------------------------------------------------------- utilitários do grafo
def _graph(proc: RecipeProcess):
    cycle = find_cycle(proc.steps)
    if cycle:
        raise ProcessError(f"ciclo de dependências: {' -> '.join(cycle)}")
    steps = {s.step_id: s for s in proc.steps}
    for s in proc.steps:
        for d in s.dependencies:
            if d not in steps:
                raise ProcessError(f"{s.step_id}: dependência inexistente {d}")
    children: dict[str, list[str]] = {sid: [] for sid in steps}
    for s in proc.steps:
        for d in s.dependencies:
            children[d].append(s.step_id)
    return steps, children


def _topo(steps, children) -> list[str]:
    indeg = {sid: len(s.dependencies) for sid, s in steps.items()}
    ready = sorted(sid for sid, n in indeg.items() if n == 0)
    out = []
    while ready:
        n = ready.pop(0)
        out.append(n)
        for c in sorted(children[n]):
            indeg[c] -= 1
            if indeg[c] == 0:
                ready.append(c)
                ready.sort()
    return out


def critical_path(proc: RecipeProcess) -> tuple[list[str], float]:
    """Maior caminho por duração no DAG (sem recursos). Determinístico."""
    steps, children = _graph(proc)
    order = _topo(steps, children)
    best: dict[str, tuple[float, str | None]] = {}
    for sid in order:
        s = steps[sid]
        prev = max(((best[d][0], d) for d in s.dependencies), default=(0.0, None), key=lambda x: (x[0], x[1] or ""))
        best[sid] = (prev[0] + s.duration_s, prev[1])
    end = max(best, key=lambda k: (best[k][0], k))
    path, cur = [], end
    while cur is not None:
        path.append(cur)
        cur = best[cur][1]
    return list(reversed(path)), best[end][0]


def _tails(steps, children) -> dict[str, float]:
    """Duração do maior caminho a partir de cada etapa (prioridade do list scheduling)."""
    tails: dict[str, float] = {}
    for sid in reversed(_topo(steps, children)):
        tails[sid] = steps[sid].duration_s + max((tails[c] for c in children[sid]), default=0.0)
    return tails


class _Calendar:
    """Ocupação por recurso: lista de intervalos (início, fim) com capacidade."""

    def __init__(self, capacity: Mapping[str, int]):
        self.capacity = dict(capacity)
        self.busy: dict[str, list[tuple[float, float]]] = {r: [] for r in capacity}

    def free(self, rid: str, start: float, end: float) -> bool:
        if end <= start:
            return True
        # pior sobreposição no intervalo (checa nos pontos de início que caem dentro dele)
        points = [start] + [a for a, b in self.busy[rid] if start < a < end]
        for p in points:
            used = sum(1 for a, b in self.busy[rid] if a <= p < b)
            if used >= self.capacity[rid]:
                return False
        return True

    def next_change(self, rid: str, after: float) -> float | None:
        ends = sorted(b for a, b in self.busy[rid] if b > after)
        return ends[0] if ends else None

    def book(self, rid: str, start: float, end: float) -> None:
        if end > start:
            self.busy[rid].append((start, end))


def _fits(cal: _Calendar, needs: list[tuple[str, float, float]], t: float) -> bool:
    return all(cal.free(r, t + a, t + b) for r, a, b in needs)


def _earliest(cal: _Calendar, needs: list[tuple[str, float, float]], t: float) -> float:
    guard = 0
    while not _fits(cal, needs, t):
        candidates = [cal.next_change(r, t) for r, _, _ in needs]
        candidates = [c for c in candidates if c is not None and c > t]
        if not candidates:
            raise ProcessError("recursos insuficientes: capacidade nunca libera")
        t = min(candidates)
        guard += 1
        if guard > 10000:
            raise ProcessError("scheduler não convergiu")
    return t


def _needs(step, cook_id: str) -> list[tuple[str, float, float]]:
    """(recurso, início relativo, fim relativo) que a etapa precisa."""
    needs = [(r, 0.0, step.duration_s) for r in step.equipment_refs]
    if step.attention == "active" and (step.active_duration_s or 0) > 0:
        needs.append((cook_id, 0.0, float(step.active_duration_s)))
    return needs


# --------------------------------------------------------------------------- agendamento
COOK = "__cook__"


def schedule(proc: RecipeProcess, *, check_interval_s: float = 300.0) -> Schedule:
    steps, children = _graph(proc)
    tails = _tails(steps, children)
    capacity = {rid: r.capacity for rid, r in proc.resources.items()}
    capacity[COOK] = proc.cooks
    cal = _Calendar(capacity)
    preheat = {sid for sid, s in steps.items() if s.phase == "preaquecimento"}

    tasks: dict[str, ScheduledTask] = {}
    waits: dict[str, float] = {}
    remaining = set(steps) - preheat
    # 1) etapas comuns por list scheduling; preaquecimento entra como restrição do consumidor
    while remaining:
        def is_ready(sid: str) -> bool:
            for d in steps[sid].dependencies:
                if d in preheat:
                    if not all(dd in tasks for dd in steps[d].dependencies):
                        return False
                elif d not in tasks:
                    return False
            return True

        ready = [sid for sid in remaining if is_ready(sid)]
        if not ready:
            raise ProcessError("nenhuma etapa pronta: dependências de preaquecimento inconsistentes")
        sid = sorted(ready, key=lambda x: (-tails[x], x))[0]
        s = steps[sid]
        est = 0.0
        for d in s.dependencies:
            if d in preheat:
                ph = steps[d]
                # o preaquecimento precisa caber antes: consumidor não começa antes de
                # (fim das dependências do preaquecimento + duração do preaquecimento)
                ph_ready = max((tasks[x].planned_end_s for x in ph.dependencies), default=0.0)
                est = max(est, ph_ready + ph.duration_s)
            else:
                est = max(est, tasks[d].planned_end_s)
        start = _earliest(cal, _needs(s, COOK), est)
        waits[sid] = start - est
        for r, a, b in _needs(s, COOK):
            cal.book(r, start + a, start + b)
        tasks[sid] = ScheduledTask(sid, s.phase, s.attention, start, start + s.duration_s,
                                   start + float(s.active_duration_s or 0), s.equipment_refs)
        remaining.discard(sid)

    # 2) preaquecimento o mais tarde possível: termina quando o primeiro consumidor começa
    for sid in sorted(preheat):
        s = steps[sid]
        consumers = [c for c in children[sid]]
        deadline = min((tasks[c].planned_start_s for c in consumers), default=None)
        ready_at = max((tasks[d].planned_end_s for d in s.dependencies if d in tasks), default=0.0)
        if deadline is None:
            start = ready_at
        else:
            start = max(ready_at, deadline - s.duration_s)
        # recuo até caber nos recursos (sem passar do deadline); se não couber, avisa
        needs = _needs(s, COOK)
        t = start
        while t >= ready_at and not _fits(cal, needs, t):
            t -= 60.0
        if t < ready_at or not _fits(cal, needs, t):
            t = _earliest(cal, needs, start)
        for r, a, b in needs:
            cal.book(r, t + a, t + b)
        tasks[sid] = ScheduledTask(sid, s.phase, s.attention, t, t + s.duration_s,
                                   t + float(s.active_duration_s or 0), s.equipment_refs)
        waits[sid] = 0.0

    return _summarize(proc, steps, tasks, waits, check_interval_s)


def _summarize(proc, steps, tasks, waits, check_interval_s, warnings=None) -> Schedule:
    cp, cp_s = critical_path(proc)
    makespan = max((t.end_s for t in tasks.values()), default=0.0)
    cook_active = sum(float(steps[s].active_duration_s or 0) for s in steps if steps[s].attention == "active")
    passive = sum(float(steps[s].passive_duration_s or 0) for s in steps)
    order = sorted(tasks, key=lambda s: (tasks[s].start_s, s))
    mise = [s for s in order if steps[s].phase in {"planejamento", "mise_en_place"}]
    cooking = [s for s in order if steps[s].phase in {"preaquecimento", "coccao", "descanso"}]
    groups: list[list[str]] = []
    for s in order:
        overlapping = [o for o in order if o != s and tasks[o].start_s < tasks[s].end_s and tasks[s].start_s < tasks[o].end_s]
        if overlapping:
            g = sorted([s] + overlapping)
            if g not in groups:
                groups.append(g)
    checks = {}
    for s in order:
        if steps[s].attention == "check":
            t, pts = tasks[s].start_s + check_interval_s, []
            while t < tasks[s].end_s:
                pts.append(t)
                t += check_interval_s
            checks[s] = pts
    warns = list(warnings or [])
    for s in order:
        if not steps[s].claim_ids.get("active_duration_s") and not steps[s].claim_ids.get("passive_duration_s"):
            warns.append(f"{s}: duração sem claim de origem")
    return Schedule(proc.recipe_id, tasks, makespan, cp, cp_s, cook_active, passive, mise, cooking, groups,
                    {k: v for k, v in waits.items() if v > 0}, checks, warns)


def descendants(proc: RecipeProcess, step_id: str) -> set[str]:
    _, children = _graph(proc)
    out, stack = set(), list(children[step_id])
    while stack:
        n = stack.pop()
        if n not in out:
            out.add(n)
            stack.extend(children[n])
    return out


def reschedule(proc: RecipeProcess, sched: Schedule, step_id: str, *, actual_start_s: float | None = None,
               actual_end_s: float) -> Schedule:
    """Registra o fim real de uma etapa e recalcula **só** as etapas dependentes.

    Etapas sem relação de dependência mantêm seus horários planejados. Dependentes são
    empurradas para depois do novo fim (ou antecipadas, se terminou cedo), respeitando
    recursos já reservados pelas demais. Tempos reais ficam em ``actual_*``.
    """
    steps, children = _graph(proc)
    if step_id not in sched.tasks:
        raise ProcessError(f"etapa não agendada: {step_id}")
    affected = descendants(proc, step_id)
    tasks = {k: ScheduledTask(**asdict(v)) for k, v in sched.tasks.items()}
    done = tasks[step_id]
    done.actual_start_s = done.planned_start_s if actual_start_s is None else actual_start_s
    done.actual_end_s = actual_end_s
    done.status = "done"
    capacity = {rid: r.capacity for rid, r in proc.resources.items()}
    capacity[COOK] = proc.cooks
    cal = _Calendar(capacity)
    for sid, t in tasks.items():
        if sid in affected:
            continue
        s = steps[sid]
        for r, a, b in _needs(s, COOK):
            if sid == step_id and r != COOK:
                cal.book(r, t.start_s, t.end_s)          # equipamento ocupado até o fim real
            else:
                cal.book(r, t.start_s + a, t.start_s + b)
    order = [s for s in _topo(steps, children) if s in affected]
    waits = {}
    for sid in order:
        s = steps[sid]
        est = max((tasks[d].end_s for d in s.dependencies), default=0.0)
        start = _earliest(cal, _needs(s, COOK), est)
        waits[sid] = start - est
        for r, a, b in _needs(s, COOK):
            cal.book(r, start + a, start + b)
        t = tasks[sid]
        if (start, start + s.duration_s) != (t.planned_start_s, t.planned_end_s):
            t.status = "rescheduled"
        t.planned_start_s, t.planned_end_s = start, start + s.duration_s
        t.active_end_s = start + float(s.active_duration_s or 0)
    return _summarize(proc, steps, tasks, waits, 300.0)
