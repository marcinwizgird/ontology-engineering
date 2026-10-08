"""The one write path: change sets, commits, history, staging, undo/redo.

This module merges the two change models the platform inherits:

**Semantic Turkey** (``st-changetracking-sail``). Every write passes the
``ChangeTrackerConnection``; on commit, the *effective* delta (additions not
already present, removals actually present) is stored in the history repository
as a ``cl:Commit`` with ``cl:addedStatement``/``cl:removedStatement``
``cl:Quadruple``\\ s and a ``cl:parentCommit`` chain from ``cl:tip``. With
validation enabled the delta is *not* applied: additions go to the
``staging-add-graph``, removals to the ``staging-remove-graph`` and the commit is
recorded as pending; a holder of the ``V`` capability accepts (apply, keep in
history) or rejects (drop staged triples and the commit — "as if the operation
was never performed").

**Protégé** (``HistoryManagerImpl``). An undo stack and a redo stack of change
lists; ``undo`` applies the *reverse* of the most recent change list and pushes it
on the redo stack; any new change clears the redo stack.

Here undo/redo are per principal and are themselves commits (``operation =
"undo"``/``"redo"``), so the audit trail stays append-only — Semantic Turkey's
history never forgets, which Protégé's in-memory stacks do on restart.

Invariant enforced in code (not by convention): ``Store.apply`` is called from
:meth:`ChangeTracker._write` and nowhere else in the platform. The content delta
and the history record are a single ``apply`` — one transaction on Fuseki.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Iterator

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import PROV, RDF, XSD
from rdflib.term import Node

from . import events as ev
from .layout import ProjectLayout
from .namespaces import CL, SIP
from .principal import Principal
from .store import Quad, Store, materialise

__all__ = ["ChangeSet", "Commit", "ChangeTracker", "ValidationError", "ConflictError"]


class ValidationError(PermissionError):
    """Raised when accept/reject is attempted on something that is not pending."""


class ConflictError(RuntimeError):
    """A staged removal no longer matches the content it was proposed against."""


@dataclass
class ChangeSet:
    """A logical edit under construction (Protégé: ``List<OWLOntologyChange>``).

    ``graph`` defaults to the project's main ontology graph; KG population writes
    target ``layout.kg``.
    """

    operation: str
    parameters: dict = field(default_factory=dict)
    default_graph: URIRef | None = None
    additions: list[Quad] = field(default_factory=list)
    removals: list[Quad] = field(default_factory=list)
    comment: str | None = None
    #: Agent evidence: source spans, model id, prompt hash, confidence…
    evidence: dict | None = None

    def _q(self, s, p, o, graph) -> Quad:
        g = graph or self.default_graph
        if g is None:
            raise ValueError("no target graph")
        return (s, p, o, URIRef(g))

    def add(self, s: Node, p: Node, o: Node, graph: URIRef | None = None) -> "ChangeSet":
        self.additions.append(self._q(s, p, o, graph))
        return self

    def remove(self, s: Node, p: Node, o: Node, graph: URIRef | None = None) -> "ChangeSet":
        self.removals.append(self._q(s, p, o, graph))
        return self

    def add_all(self, triples: Iterable[tuple], graph: URIRef | None = None) -> "ChangeSet":
        for t in triples:
            self.add(*t, graph=graph)
        return self

    def remove_all(self, triples: Iterable[tuple], graph: URIRef | None = None) -> "ChangeSet":
        for t in triples:
            self.remove(*t, graph=graph)
        return self

    def inverse(self, operation: str) -> "ChangeSet":
        """Protégé ``HistoryManagerImpl.undo``: reverse each change, reverse order."""
        return ChangeSet(operation, {}, self.default_graph,
                         additions=list(reversed(self.removals)),
                         removals=list(reversed(self.additions)))

    def __len__(self) -> int:
        return len(self.additions) + len(self.removals)


@dataclass
class Commit:
    id: str
    project: str
    principal: str
    is_machine: bool
    operation: str
    parameters: dict
    started: datetime
    ended: datetime
    additions: list[Quad]
    removals: list[Quad]
    status: str                      # committed | staged | accepted | undone
    revision: int
    parent: str | None = None
    comment: str | None = None
    evidence: dict | None = None
    validated_by: str | None = None
    reverts: str | None = None

    @property
    def iri(self) -> URIRef:
        return URIRef(f"urn:sip:commit:{self.id}")

    def summary(self) -> str:
        return (f"r{self.revision} {self.operation} by {self.principal} "
                f"[{self.status}] +{len(self.additions)}/-{len(self.removals)}")


class ChangeTracker:
    """Per-project change tracking + validation (Semantic Turkey) + undo (Protégé)."""

    def __init__(self, store: Store, layout: ProjectLayout, *,
                 validation_enabled: bool = False, history_enabled: bool = True,
                 events: ev.EventBus | None = None) -> None:
        self.store = store
        self.layout = layout
        self.validation_enabled = validation_enabled
        self.history_enabled = history_enabled
        self.events = events or ev.EventBus()
        self._commits: dict[str, Commit] = {}
        self._order: list[str] = []
        self._undo: dict[str, list[str]] = {}
        self._redo: dict[str, list[str]] = {}
        self._revision = 0
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # reads
    # ------------------------------------------------------------------ #
    def view(self, content: URIRef | None = None, *, staged: bool = False) -> Graph:
        """The content graph; with ``staged=True`` the would-be state
        ``content ∪ staging-add ∖ staging-del`` (VocBench's validation preview)."""
        g = content or self.layout.main
        if not staged:
            return self.store.graph(g)
        return materialise(self.store, [g, self.layout.staging_add(g)],
                           [self.layout.staging_del(g)])

    def triple_status(self, s, p, o, content: URIRef | None = None) -> str:
        """``local`` | ``staged-add`` | ``staged-del`` | ``absent`` — the per-value
        ``tripleScope`` flag the resource view renders (green/red, italic)."""
        g = content or self.layout.main
        if self.store.contains((s, p, o, self.layout.staging_del(g))):
            return "staged-del"
        if self.store.contains((s, p, o, g)):
            return "local"
        if self.store.contains((s, p, o, self.layout.staging_add(g))):
            return "staged-add"
        return "absent"

    @property
    def commits(self) -> list[Commit]:
        return [self._commits[i] for i in self._order]

    def get(self, commit_id: str) -> Commit:
        try:
            return self._commits[commit_id]
        except KeyError:
            raise KeyError(f"no commit {commit_id!r} in project {self.layout.project}") from None

    def pending(self) -> list[Commit]:
        return [c for c in self.commits if c.status == "staged"]

    def history(self, *, principal: str | None = None, operation: str | None = None,
                resource: Node | None = None, status: str | None = None) -> list[Commit]:
        """``History.getCommits`` with the VocBench filters."""
        out = []
        for c in self.commits:
            if principal and c.principal != principal:
                continue
            if operation and c.operation != operation:
                continue
            if status and c.status != status:
                continue
            if resource is not None and not any(resource in q[:3] for q in
                                                c.additions + c.removals):
                continue
            out.append(c)
        return out

    # ------------------------------------------------------------------ #
    # the write path
    # ------------------------------------------------------------------ #
    def _effective(self, cs: ChangeSet) -> tuple[list[Quad], list[Quad]]:
        """The effective delta: what the store does not already say.

        Mirrors the SAIL, which records a statement as added only if it was not
        already present and as removed only if it was. Add-then-remove of the same
        quad inside one change set cancels out.
        """
        add, rem = dict.fromkeys(cs.additions), dict.fromkeys(cs.removals)
        for q in list(add):
            if q in rem:
                del add[q]
                del rem[q]
        eff_add = [q for q in add if not self.store.contains(q)]
        eff_rem = [q for q in rem if self.store.contains(q)]
        return eff_add, eff_rem

    def commit(self, cs: ChangeSet, principal: Principal, *,
               force_staging: bool = False) -> Commit | None:
        """Apply (or stage) *cs* as one commit. Returns ``None`` for a no-op.

        Machine principals are always staged: an agent never writes to stable
        content, whatever the project's validation setting.
        """
        stage = self.validation_enabled or force_staging or principal.is_machine
        with self._lock:
            started = _now()
            if stage:
                add, rem = self._staged_effective(cs)
            else:
                add, rem = self._effective(cs)
            if not add and not rem:
                return None
            self._revision += 1
            commit = Commit(
                id=uuid.uuid4().hex, project=self.layout.project, principal=principal.id,
                is_machine=principal.is_machine, operation=cs.operation,
                parameters=dict(cs.parameters), started=started, ended=_now(),
                additions=add, removals=rem, status="staged" if stage else "committed",
                revision=self._revision, parent=self._order[-1] if self._order else None,
                comment=cs.comment, evidence=cs.evidence)
            if stage:
                content_add = [(s, p, o, self.layout.staging_add(g)) for s, p, o, g in add]
                content_rem = [(s, p, o, self.layout.staging_del(g)) for s, p, o, g in rem]
                self._write(content_add + content_rem, [], commit)
            else:
                self._write(add, rem, commit)
                self._undo.setdefault(principal.id, []).append(commit.id)
                if cs.operation not in ("undo", "redo"):
                    self._redo.pop(principal.id, None)   # Protégé: new edit clears redo
            self._register(commit)
        self.events.publish(ev.Event(ev.STAGED if stage else ev.COMMITTED,
                                     self.layout.project,
                                     {"commit": commit.id, "operation": commit.operation,
                                      "principal": principal.id}))
        return commit

    def _staged_effective(self, cs: ChangeSet) -> tuple[list[Quad], list[Quad]]:
        """Effective delta against the *staged view*, so a proposal on top of a
        proposal is recorded relative to what the proposer was looking at."""
        add, rem = dict.fromkeys(cs.additions), dict.fromkeys(cs.removals)
        for q in list(add):
            if q in rem:
                del add[q], rem[q]

        def present(q: Quad) -> bool:
            s, p, o, g = q
            return self.triple_status(s, p, o, g) in ("local", "staged-add")
        return [q for q in add if not present(q)], [q for q in rem if present(q)]

    def _write(self, additions: list[Quad], removals: list[Quad], commit: Commit,
               drop_history: Commit | None = None) -> None:
        """THE call to ``Store.apply`` — content + history in one transaction."""
        hist_add: list[Quad] = []
        hist_rem: list[Quad] = []
        if self.history_enabled:
            hist_add = list(_commit_quads(commit, self.layout.history))
            old = self._commits.get(commit.id)
            if old is not None:   # status transition: replace the record
                hist_rem = list(_commit_quads(old, self.layout.history))
            if drop_history is not None:
                hist_rem += list(_commit_quads(drop_history, self.layout.history))
                hist_add = []
        self.store.apply(additions + hist_add, removals + hist_rem)

    def replace_derived(self, graph: URIRef, triples: Iterable[tuple]) -> int:
        """Replace a *derived* graph (inferred closure, materialised import) wholesale.

        The one sanctioned write that is not a commit: derived graphs are never edited,
        are recomputable from content, and recording a materialisation triple by triple
        would bury the history. Content graphs are refused.
        """
        lay = self.layout
        derived = {lay.inferred} | {g for g in self.store.graphs()
                                    if str(g).startswith(f"urn:sip:p:{lay.project}:imports:")}
        if graph not in derived and not str(graph).startswith(
                f"urn:sip:p:{lay.project}:imports:"):
            raise PermissionError(f"{graph} is not a derived graph of {lay.project}")
        with self._lock:
            old = [(s, p, o, graph) for s, p, o in self.store.graph(graph)]
            new = [(s, p, o, graph) for s, p, o in triples]
            self.store.apply(new, old)
        return len(new)

    def _register(self, commit: Commit) -> None:
        if commit.id not in self._commits:
            self._order.append(commit.id)
        self._commits[commit.id] = commit

    # ------------------------------------------------------------------ #
    # validation (Semantic Turkey Validation service)
    # ------------------------------------------------------------------ #
    def accept(self, commit_id: str, validator: Principal) -> Commit:
        """Apply a staged commit to stable content.

        Conflict check first: a staged removal whose triple has meanwhile vanished
        from content, or an addition that some other accepted commit already made,
        is reported rather than silently merged.
        """
        with self._lock:
            c = self.get(commit_id)
            if c.status != "staged":
                raise ValidationError(f"commit {commit_id} is {c.status}, not staged")
            missing = [q for q in c.removals if not self.store.contains(q)]
            if missing:
                raise ConflictError(f"{len(missing)} staged removal(s) no longer present "
                                    f"in content, e.g. {missing[0][:3]}")
            stage_rem = ([(s, p, o, self.layout.staging_add(g)) for s, p, o, g in c.additions]
                         + [(s, p, o, self.layout.staging_del(g)) for s, p, o, g in c.removals])
            new = _replace(c, status="accepted", validated_by=validator.id, ended=_now())
            add = [q for q in c.additions if not self.store.contains(q)]
            self._write(add, c.removals + stage_rem, new)
            self._register(new)
            self._undo.setdefault(c.principal, []).append(c.id)
        self.events.publish(ev.Event(ev.ACCEPTED, self.layout.project,
                                     {"commit": commit_id, "validator": validator.id}))
        return new

    def reject(self, commit_id: str, validator: Principal) -> None:
        """Drop a staged commit: staged triples go, and so does its history record."""
        with self._lock:
            c = self.get(commit_id)
            if c.status != "staged":
                raise ValidationError(f"commit {commit_id} is {c.status}, not staged")
            stage_rem = ([(s, p, o, self.layout.staging_add(g)) for s, p, o, g in c.additions]
                         + [(s, p, o, self.layout.staging_del(g)) for s, p, o, g in c.removals])
            self._write([], stage_rem, c, drop_history=c)
            self._order.remove(c.id)
            del self._commits[c.id]
        self.events.publish(ev.Event(ev.REJECTED, self.layout.project,
                                     {"commit": commit_id, "validator": validator.id,
                                      "operation": c.operation, "principal": c.principal}))

    # ------------------------------------------------------------------ #
    # undo / redo (Protégé HistoryManager, persisted)
    # ------------------------------------------------------------------ #
    def can_undo(self, principal: Principal) -> bool:
        return bool(self._undo.get(principal.id))

    def can_redo(self, principal: Principal) -> bool:
        return bool(self._redo.get(principal.id))

    def undo(self, principal: Principal) -> Commit | None:
        stack = self._undo.get(principal.id)
        if not stack:
            return None
        target = self.get(stack.pop())
        cs = ChangeSet("undo", {"reverts": target.id}, self.layout.main,
                       additions=list(reversed(target.removals)),
                       removals=list(reversed(target.additions)))
        undo_commit = self._commit_direct(cs, principal, reverts=target.id)
        if undo_commit is not None:
            self._redo.setdefault(principal.id, []).append(target.id)
            self._set_status(target, "undone")
            self.events.publish(ev.Event(ev.UNDONE, self.layout.project,
                                         {"commit": target.id}))
        return undo_commit

    def redo(self, principal: Principal) -> Commit | None:
        stack = self._redo.get(principal.id)
        if not stack:
            return None
        target = self.get(stack.pop())
        cs = ChangeSet("redo", {"reapplies": target.id}, self.layout.main,
                       additions=list(target.additions), removals=list(target.removals))
        c = self._commit_direct(cs, principal, reverts=target.id)
        if c is not None:
            self._set_status(target, "committed")
        return c

    def _set_status(self, c: Commit, status: str) -> None:
        with self._lock:
            new = _replace(c, status=status)
            self._write([], [], new)
            self._register(new)

    def _commit_direct(self, cs: ChangeSet, principal: Principal, reverts: str) -> Commit | None:
        """Undo/redo bypass staging: they restore a state that was already validated."""
        with self._lock:
            add, rem = self._effective(cs)
            if not add and not rem:
                return None
            self._revision += 1
            c = Commit(uuid.uuid4().hex, self.layout.project, principal.id,
                       principal.is_machine, cs.operation, cs.parameters, _now(), _now(),
                       add, rem, "committed", self._revision,
                       self._order[-1] if self._order else None, reverts=reverts)
            self._write(add, rem, c)
            self._register(c)
            if cs.operation == "redo":
                self._undo.setdefault(principal.id, []).append(c.id)
            return c


# --------------------------------------------------------------------------- #
# RDF serialisation of commits (CHANGELOG vocabulary)
# --------------------------------------------------------------------------- #

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _replace(c: Commit, **kw) -> Commit:
    d = dict(c.__dict__)
    d.update(kw)
    return Commit(**d)


def _commit_quads(c: Commit, g: URIRef) -> Iterator[Quad]:
    s = c.iri
    agent = URIRef(f"urn:sip:{'machine' if c.is_machine else 'user'}:{c.principal}")
    yield (s, RDF.type, CL.Commit, g)
    yield (s, CL.status, Literal(c.status), g)
    yield (s, CL.revisionNumber, Literal(c.revision), g)
    yield (s, PROV.startedAtTime, Literal(c.started.isoformat(), datatype=XSD.dateTime), g)
    yield (s, PROV.endedAtTime, Literal(c.ended.isoformat(), datatype=XSD.dateTime), g)
    yield (s, PROV.wasAssociatedWith, agent, g)
    yield (s, SIP.operation, Literal(c.operation), g)
    if c.parameters:
        yield (s, SIP.parameters, Literal(json.dumps(c.parameters, default=str,
                                                     sort_keys=True)), g)
    if c.parent:
        yield (s, CL.parentCommit, URIRef(f"urn:sip:commit:{c.parent}"), g)
    if c.comment:
        yield (s, SIP.comment, Literal(c.comment), g)
    if c.validated_by:
        yield (s, SIP.validatedBy, URIRef(f"urn:sip:user:{c.validated_by}"), g)
    if c.reverts:
        yield (s, SIP.reverts, URIRef(f"urn:sip:commit:{c.reverts}"), g)
    if c.evidence:
        yield (s, SIP.evidence, Literal(json.dumps(c.evidence, default=str,
                                                   sort_keys=True)), g)
    for kind, quads in ((CL.addedStatement, c.additions), (CL.removedStatement, c.removals)):
        for n, (qs, qp, qo, qg) in enumerate(quads):
            q = URIRef(f"{s}:{'a' if kind == CL.addedStatement else 'r'}{n}")
            yield (s, kind, q, g)
            yield (q, RDF.type, CL.Quadruple, g)
            yield (q, CL.subject, qs, g)
            yield (q, CL.predicate, qp, g)
            yield (q, CL.object, qo, g)
            yield (q, CL.context, qg, g)
