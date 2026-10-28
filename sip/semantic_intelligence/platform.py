"""The Semantic Intelligence Platform facade — one typed operation surface.

Every capability of the platform is an **operation** registered with
:func:`operation`, declaring

* the VocBench capability it needs (``rdf(cls)``, ``rdf(concept, lexicalization)``,
  ``pm(project)`` …) and the CRUDV letters — the ``@PreAuthorize`` of Semantic
  Turkey's services, made data;
* the lifecycle stage it belongs to (for the orchestrator and the UI perspectives);
* whether it writes.

:meth:`Platform.call` is the only entry point: it resolves the principal, asks the
PDP, runs the operation, and — when the operation returns a :class:`ChangeSet` —
commits it through the project's :class:`ChangeTracker` (staged for machines).
The API layer, the CLI, notebooks and every agent call the same method, so there
is exactly one place where authorization and history are enforced. A test fails
the build if an operation lacks a capability (QR-SEC-01).
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from .core import events as ev
from .core.changes import ChangeSet, ChangeTracker, Commit
from .core.layout import ProjectLayout
from .core.principal import SYSTEM, Principal
from .core.store import InMemoryStore, Store, materialise
from .governance.registry import (AuthorizationError, Lexicalization, ModelType,
                                  PolicyDecisionPoint, ProjectConfig, ProjectTemplate,
                                  Registry)
from .governance.settings import SettingsStore
from .governance.urigen import EntityCreationPreferences, TemplateURIGenerator
from .owl import manchester, refactor
from .owl.frames import class_frame, property_frame, render_axiom, resource_view
from .owl.hierarchy import ClassHierarchy, PropertyHierarchy
from .owl.model import Axiom, axiom_triples, axioms
from .owl.rendering import ShortFormProvider, entity_role
from .quality import cq as cqmod
from .quality import icv, metrics as metricsmod, semantic
from .reasoning.explanation import Entailment, explain
from .reasoning.reasoner import ReasonerManager
from .scope import orsd
from .search.search import search_resource
from .skos.skos import SkosService

STAGES = ("scope", "acquire", "model", "validate", "review", "populate", "reason",
          "publish", "consume", "govern")


@dataclass
class OperationSpec:
    name: str
    fn: Callable
    capability: str
    crudv: str
    stage: str
    writes: bool
    description: str
    params: list[str]
    resource_param: str | None = None    # parameter whose role fills %resource_role%
    lang_param: str | None = None        # parameter whose language tag is checked
    as_caller: bool = False              # the operation acts as the calling principal


OPERATIONS: dict[str, OperationSpec] = {}


def operation(name: str, *, capability: str, crudv: str, stage: str, writes: bool = False,
              resource_param: str | None = None, lang_param: str | None = None,
              as_caller: bool = False):
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}")

    def deco(fn):
        params = [p for p in inspect.signature(fn).parameters
                  if p not in ("self", "ctx", "caller")]
        doc = (inspect.getdoc(fn) or "").split("\n")[0]
        OPERATIONS[name] = OperationSpec(name, fn, capability, crudv, stage, writes, doc,
                                         params, resource_param, lang_param, as_caller)
        fn._sip_operation = name
        return fn
    return deco


@dataclass
class ProjectContext:
    """Everything one project needs at runtime."""

    config: ProjectConfig
    layout: ProjectLayout
    tracker: ChangeTracker
    reasoner: ReasonerManager
    entity_prefs: EntityCreationPreferences
    urigen: TemplateURIGenerator
    sources: dict[str, dict] = field(default_factory=dict)
    lifecycle: dict[str, str] = field(default_factory=dict)
    alignments: dict[str, Any] = field(default_factory=dict)
    #: classification of the *staged* view (what would hold if every proposal were
    #: accepted) — kept apart from ``reasoner.last`` so previews never pose as content.
    preview: Any = None
    #: registered relational databases of the virtual knowledge graph (vkg.source)
    databases: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.config.name

    def imports(self) -> list[URIRef]:
        return sorted(g for g in self.tracker.store.graphs()
                      if str(g).startswith(f"urn:sip:p:{self.name}:imports:"))

    def ontology(self, *, staged: bool = False, with_imports: bool = True) -> Graph:
        """``main`` (∪ imports), optionally in the staged view."""
        lay, st = self.layout, self.tracker.store
        inc = [lay.main] + (self.imports() if with_imports else [])
        exc = []
        if staged:
            inc.append(lay.staging_add(lay.main))
            exc.append(lay.staging_del(lay.main))
        g = materialise(st, inc, exc)
        for p, ns in (("owl", OWL), ("rdfs", RDFS), ("skos", SKOS), ("rdf", RDF)):
            g.bind(p, ns)
        g.bind("", self.config.default_namespace)
        return g

    def kg(self, *, staged: bool = False) -> Graph:
        lay = self.layout
        inc, exc = [lay.kg], []
        if staged:
            inc.append(lay.staging_add(lay.kg))
            exc.append(lay.staging_del(lay.kg))
        return materialise(self.tracker.store, inc, exc)

    def sfp(self, staged: bool = False) -> ShortFormProvider:
        return ShortFormProvider(self.ontology(staged=staged),
                                 languages=tuple(self.config.languages) + ("",))

    def exists(self, iri: URIRef) -> bool:
        st, lay = self.tracker.store, self.layout
        for g in (lay.main, lay.kg, lay.staging_add(lay.main), lay.staging_add(lay.kg)):
            gr = st.graph(g)
            if (iri, None, None) in gr or (None, None, iri) in gr:
                return True
        return False


class Platform:
    def __init__(self, store: Store | None = None) -> None:
        self.store = store or InMemoryStore()
        self.registry = Registry()
        self.pdp = PolicyDecisionPoint(self.registry)
        self.settings = SettingsStore()
        self.events = ev.EventBus()
        self.projects: dict[str, ProjectContext] = {}
        self.registry.add_principal(SYSTEM)

    # ------------------------------------------------------------------ #
    # the one entry point
    # ------------------------------------------------------------------ #
    def call(self, principal: Principal | str, project: str | None, op: str, /, **kwargs):
        spec = OPERATIONS.get(op)
        if spec is None:
            raise KeyError(f"unknown operation {op!r}")
        p = self.registry.principal(principal) if isinstance(principal, str) else principal
        evidence = kwargs.pop("_evidence", None)
        ctx = self.projects.get(project) if project else None
        if spec.capability == "admin":
            if not (p.is_admin or p.id in self.registry.superusers) or p.is_machine:
                raise AuthorizationError(f"{op} requires an administrator or superuser")
        else:
            if ctx is None:
                raise KeyError(f"unknown project {project!r}")
            cap = spec.capability
            if "%resource_role%" in cap:
                res = kwargs.get(spec.resource_param or "")
                role = entity_role(ctx.ontology(staged=True), URIRef(res)) if res else "resource"
                cap = cap.replace("%resource_role%", role if role != "unknown" else "resource")
            langs = []
            if spec.lang_param and kwargs.get(spec.lang_param):
                langs = [kwargs[spec.lang_param]]
            self.pdp.require(p, project, cap, spec.crudv, languages=langs)
        if spec.as_caller:
            kwargs["caller"] = p
        result = spec.fn(self, ctx, **kwargs)
        if isinstance(result, ChangeSet):
            if not len(result):
                return None
            if evidence is not None:
                result.evidence = evidence
            return ctx.tracker.commit(result, p)
        return result

    def operations(self, stage: str | None = None) -> list[OperationSpec]:
        return [o for o in OPERATIONS.values() if stage is None or o.stage == stage]

    # ------------------------------------------------------------------ #
    # project bootstrap (not an operation: called by create_project)
    # ------------------------------------------------------------------ #
    def _open(self, cfg: ProjectConfig) -> ProjectContext:
        lay = ProjectLayout(cfg.name)
        tracker = ChangeTracker(self.store, lay, validation_enabled=cfg.validation_enabled,
                                history_enabled=cfg.history_enabled, events=self.events)
        rm = ReasonerManager(revision=lambda t=tracker: t._revision)
        ctx = ProjectContext(cfg, lay, tracker, rm,
                             EntityCreationPreferences(base=cfg.base_uri),
                             TemplateURIGenerator(cfg.default_namespace),
                             lifecycle={s: "not-started" for s in STAGES[:-1]})
        self.projects[cfg.name] = ctx
        return ctx


def _iri(ctx: ProjectContext, x: str) -> URIRef:
    """Accept a full IRI, a ``prefix:local`` or a bare local name."""
    if x.startswith(("http://", "https://", "urn:")):
        return URIRef(x)
    if ":" in x:
        p, _, rest = x.partition(":")
        for pref, ns in ctx.ontology(with_imports=False).namespaces():
            if pref == p:
                return URIRef(str(ns) + rest)
    return URIRef(ctx.config.default_namespace + x)


def _lit(text: str, lang: str | None) -> Literal:
    return Literal(text, lang=lang)

# =========================================================================== #
# Governance
# =========================================================================== #


@operation("governance.createProject", capability="admin", crudv="C", stage="govern",
           writes=True)
def create_project(self: Platform, ctx, name: str, base_uri: str, model: str | None = None,
                   lexicalization: str | None = None, languages: list[str] | None = None,
                   validation: bool | None = None, description: str | None = None,
                   template: str | None = None) -> dict:
    """Create a project (Semantic Turkey ProjectManager.createProject), optionally from a
    template; arguments given explicitly override the template's."""
    t = self.registry.templates.get(template) if template else ProjectTemplate("")
    if t is None:
        raise KeyError(f"unknown template {template!r}")
    cfg = ProjectConfig(name, base_uri, ModelType[(model or t.model).upper()],
                        Lexicalization[(lexicalization or t.lexicalization).upper()],
                        languages=tuple(languages or t.languages),
                        validation_enabled=t.validation if validation is None else validation,
                        description=t.description if description is None else description)
    self.registry.add_project(cfg)
    c = self._open(cfg)
    c.tracker.commit(ChangeSet("governance.createProject", {"name": name}, c.layout.main)
                     .add(URIRef(base_uri), RDF.type, OWL.Ontology), SYSTEM)
    if t.specification or t.reuse:
        cs = ChangeSet("scope.applyTemplate", {"template": template}, c.layout.metadata)
        if t.specification:
            add, _ = orsd.spec_delta(c.tracker.view(c.layout.metadata), orsd.spec_node(name),
                                     URIRef(base_uri), t.specification)
            cs.add_all(add)
        for r in t.reuse:
            cs.add_all(orsd.ReuseCandidate(**r).triples())
        c.tracker.commit(cs, SYSTEM)
    self.events.publish(ev.Event(ev.PROJECT_CREATED, name, {}))
    return {"project": name, "template": template,
            "graphs": {"main": str(c.layout.main), "kg": str(c.layout.kg)}}


@operation("governance.saveTemplate", capability="admin", crudv="C", stage="govern",
           writes=True)
def save_template(self: Platform, ctx, name: str, model: str = "owl",
                  lexicalization: str = "rdfs", languages: list[str] | None = None,
                  validation: bool = False, description: str = "",
                  specification: dict | None = None, reuse: list[dict] | None = None) -> dict:
    """Save a project template (VocBench ProjectTemplates), with an optional scope skeleton."""
    ModelType[model.upper()], Lexicalization[lexicalization.upper()]   # fail early
    orsd.spec_delta(Graph(), orsd.spec_node("template"), URIRef("urn:x"), specification or {})
    for r in reuse or []:
        orsd.ReuseCandidate(**r)
    t = ProjectTemplate(name, model, lexicalization, tuple(languages or ["en"]), validation,
                        description, dict(specification or {}), list(reuse or []))
    self.registry.templates[name] = t
    return {"template": name}


@operation("governance.listTemplates", capability="admin", crudv="R", stage="govern")
def list_templates(self: Platform, ctx) -> list[dict]:
    """The saved project templates."""
    return [dict(t.__dict__, languages=list(t.languages))
            for t in sorted(self.registry.templates.values(), key=lambda t: t.name)]


@operation("governance.bind", capability="rbac", crudv="C", stage="govern", writes=True)
def bind(self: Platform, ctx, principal: str, roles: list[str],
         languages: list[str] | None = None) -> dict:
    """Bind a principal to the project with roles and optional languages."""
    b = self.registry.bind(principal, ctx.name, roles, languages or ())
    return {"principal": b.principal, "roles": list(b.roles), "languages": list(b.languages)}


@operation("governance.setValidation", capability="pm(project)", crudv="U", stage="govern",
           writes=True)
def set_validation(self: Platform, ctx, enabled: bool) -> dict:
    """Switch the project's validation (staging) workflow on or off."""
    ctx.config.validation_enabled = enabled
    ctx.tracker.validation_enabled = enabled
    return {"validation": enabled}

# =========================================================================== #
# Browsing (Protégé hierarchies / frames, ST resource view)
# =========================================================================== #


@operation("browse.classTree", capability="rdf(cls)", crudv="R", stage="model")
def class_tree(self: Platform, ctx, parent: str | None = None, staged: bool = True) -> list[dict]:
    """Children of a class (roots when no parent) with a 'more' flag."""
    g = ctx.ontology(staged=staged)
    h, sfp = ClassHierarchy(g), ShortFormProvider(g, languages=tuple(ctx.config.languages))
    nodes = h.children(_iri(ctx, parent)) if parent else h.roots()
    return [{"iri": str(n), "show": sfp.render(n), "more": bool(h.children(n)),
             "instances": len(h.instances(n))} for n in nodes]


@operation("browse.propertyTree", capability="rdf(property)", crudv="R", stage="model")
def property_tree(self: Platform, ctx, kind: str = "object", parent: str | None = None) -> list:
    """Object/data/annotation property hierarchy."""
    g = ctx.ontology(staged=True)
    h = PropertyHierarchy(g, kind)
    sfp = ShortFormProvider(g)
    nodes = h.children(_iri(ctx, parent)) if parent else h.roots()
    return [{"iri": str(n), "show": sfp.render(n), "more": bool(h.children(n))} for n in nodes]


@operation("browse.classFrame", capability="rdf(cls)", crudv="R", stage="model")
def class_frame_op(self: Platform, ctx, cls: str, include_inferred: bool = True) -> dict:
    """Protégé class description frame (Manchester-rendered sections)."""
    g = ctx.ontology(staged=True)
    inferred = ctx.reasoner.last.inferred if (include_inferred and ctx.reasoner.last) else None
    return class_frame(g, _iri(ctx, cls), ShortFormProvider(g), inferred)


@operation("browse.propertyFrame", capability="rdf(property)", crudv="R", stage="model")
def property_frame_op(self: Platform, ctx, prop: str) -> dict:
    """Protégé property description frame."""
    g = ctx.ontology(staged=True)
    return property_frame(g, _iri(ctx, prop), ShortFormProvider(g))


@operation("browse.resourceView", capability="rdf(%resource_role%)", crudv="R", stage="model",
           resource_param="resource")
def resource_view_op(self: Platform, ctx, resource: str) -> dict:
    """Semantic Turkey resource view with per-value tripleScope."""
    st, lay = self.store, ctx.layout
    r = _iri(ctx, resource)
    content = lay.kg if (r, None, None) in st.graph(lay.kg) or \
        (r, None, None) in st.graph(lay.staging_add(lay.kg)) else lay.main
    graphs = {"local": st.graph(content), "staged": st.graph(lay.staging_add(content)),
              "del_staged": st.graph(lay.staging_del(content)),
              "imported": materialise(st, ctx.imports()),
              "inferred": ctx.reasoner.last.inferred if ctx.reasoner.last else Graph()}
    return resource_view(r, graphs, ctx.sfp(staged=True)).as_dict()


@operation("browse.usage", capability="rdf(%resource_role%)", crudv="R", stage="model",
           resource_param="entity")
def usage_op(self: Platform, ctx, entity: str) -> list[str]:
    """Protégé Usage view: axioms referencing an entity."""
    g = ctx.ontology(staged=True)
    sfp = ShortFormProvider(g)
    return [render_axiom(a, sfp) for a in refactor.usage(g, _iri(ctx, entity))]


@operation("browse.metrics", capability="rdf", crudv="R", stage="validate")
def metrics_op(self: Platform, ctx) -> dict:
    """Protégé ontology metrics (6 tables) plus a DL-expressivity hint."""
    return metricsmod.metrics(ctx.ontology(staged=False))


@operation("search.searchResource", capability="rdf(resource)", crudv="R", stage="consume")
def search_op(self: Platform, ctx, text: str, mode: str = "contains",
              roles: list[str] | None = None, use_local_name: bool = True,
              use_uri: bool = False, use_notes: bool = False,
              langs: list[str] | None = None) -> list[dict]:
    """Semantic Turkey searchResource (startsWith/contains/endsWith/exact/fuzzy)."""
    g = ctx.ontology(staged=True)
    for t in ctx.kg(staged=True):
        g.add(t)
    lex = {"SKOS": "skos", "SKOSXL": "skosxl"}.get(ctx.config.lexicalization.name, "rdfs")
    hits = search_resource(g, text, roles=roles or (), mode=mode, use_local_name=use_local_name,
                           use_uri=use_uri, use_notes=use_notes, langs=langs or (),
                           lexicalization=lex)
    return [h.__dict__ for h in hits]


@operation("sparql.query", capability="rdf(sparql, core)", crudv="R", stage="consume")
def sparql_query(self: Platform, ctx, query: str, include_kg: bool = True,
                 include_inferred: bool = False) -> list[dict]:
    """Read-only SPARQL over ontology (+ KG, + inferred)."""
    g = ctx.ontology()
    if include_kg:
        for t in ctx.kg():
            g.add(t)
    if include_inferred and ctx.reasoner.last:
        for t in ctx.reasoner.last.inferred:
            g.add(t)
    res = g.query(query)
    if res.type == "ASK":
        return [{"ask": bool(res.askAnswer)}]
    if res.type in ("CONSTRUCT", "DESCRIBE"):
        return [{"s": str(s), "p": str(p), "o": str(o)} for s, p, o in res.graph]
    return [{str(k): (str(v) if v is not None else None) for k, v in row.asdict().items()}
            for row in res]


@operation("history.list", capability="rdf", crudv="R", stage="review")
def history_op(self: Platform, ctx, principal: str | None = None,
               operation_name: str | None = None, resource: str | None = None) -> list[dict]:
    """Semantic Turkey History.getCommits with filters."""
    res = _iri(ctx, resource) if resource else None
    return [_commit_dict(c) for c in ctx.tracker.history(principal=principal,
                                                         operation=operation_name,
                                                         resource=res)]


@operation("validation.pending", capability="rdf", crudv="R", stage="review")
def pending_op(self: Platform, ctx) -> list[dict]:
    """Staged commits awaiting validation."""
    return [_commit_dict(c, delta=True) for c in ctx.tracker.pending()]


def _commit_dict(c: Commit, delta: bool = False) -> dict:
    d = {"id": c.id, "revision": c.revision, "operation": c.operation,
         "principal": c.principal, "machine": c.is_machine, "status": c.status,
         "added": len(c.additions), "removed": len(c.removals),
         "started": c.started.isoformat(), "parameters": c.parameters}
    if c.evidence:
        d["evidence"] = c.evidence
    if delta:
        d["additions"] = [[str(x) for x in q[:3]] for q in c.additions]
        d["removals"] = [[str(x) for x in q[:3]] for q in c.removals]
    return d

# =========================================================================== #
# Validation / undo (Semantic Turkey Validation, Protégé HistoryManager)
# =========================================================================== #


@operation("validation.accept", capability="rdf", crudv="V", stage="review", writes=True,
           as_caller=True)
def accept_op(self: Platform, ctx, commit: str, caller: Principal) -> dict:
    """Accept a staged commit (requires V; machines never hold it)."""
    return _commit_dict(ctx.tracker.accept(commit, caller))


@operation("validation.reject", capability="rdf", crudv="V", stage="review", writes=True,
           as_caller=True)
def reject_op(self: Platform, ctx, commit: str, caller: Principal) -> dict:
    """Reject a staged commit (requires V); it leaves no history trace."""
    ctx.tracker.reject(commit, caller)
    return {"rejected": commit}


@operation("history.undo", capability="rdf", crudv="R", stage="model", writes=True,
           as_caller=True)
def undo_op(self: Platform, ctx, caller: Principal) -> dict:
    """Undo the caller's last commit (Protégé HistoryManager.undo).

    Like Semantic Turkey's ``Undo.undo`` this needs no edit capability: it can only
    revert the caller's *own* last change, which the tracker enforces."""
    c = ctx.tracker.undo(caller)
    return _commit_dict(c) if c else {"nothing": "undo"}


@operation("history.redo", capability="rdf", crudv="R", stage="model", writes=True,
           as_caller=True)
def redo_op(self: Platform, ctx, caller: Principal) -> dict:
    """Redo the caller's last undone commit."""
    c = ctx.tracker.redo(caller)
    return _commit_dict(c) if c else {"nothing": "redo"}


# =========================================================================== #
# Authoring — OWL (Protégé)
# =========================================================================== #


@operation("owl.createClass", capability="rdf(cls)", crudv="C", stage="model", writes=True,
           lang_param="lang")
def create_class(self: Platform, ctx, name: str, parent: str | None = None,
                 label: str | None = None, lang: str | None = "en",
                 comment: str | None = None, iri: str | None = None) -> ChangeSet:
    """Create an OWL class (Protégé CustomOWLEntityFactory)."""
    c = URIRef(iri) if iri else ctx.entity_prefs.mint(name, "class", ctx.exists)
    cs = ChangeSet("owl.createClass", {"iri": str(c), "parent": parent}, ctx.layout.main)
    cs.add(c, RDF.type, OWL.Class)
    if parent:
        cs.add(c, RDFS.subClassOf, _iri(ctx, parent))
    if label or ctx.entity_prefs.create_label:
        cs.add(c, RDFS.label, _lit(label or name, lang))
    if comment:
        cs.add(c, RDFS.comment, _lit(comment, lang))
    return cs


@operation("owl.createProperty", capability="rdf(property)", crudv="C", stage="model",
           writes=True)
def create_property(self: Platform, ctx, name: str, kind: str = "object",
                    domain: str | None = None, range: str | None = None,
                    parent: str | None = None, label: str | None = None,
                    characteristics: list[str] | None = None, iri: str | None = None
                    ) -> ChangeSet:
    """Create an object/data/annotation property with optional domain/range."""
    t = {"object": OWL.ObjectProperty, "data": OWL.DatatypeProperty,
         "annotation": OWL.AnnotationProperty}[kind]
    p = URIRef(iri) if iri else ctx.entity_prefs.mint(name, f"{kind}Property", ctx.exists)
    cs = ChangeSet("owl.createProperty", {"iri": str(p), "kind": kind}, ctx.layout.main)
    cs.add(p, RDF.type, t)
    cs.add(p, RDFS.label, _lit(label or name, "en"))
    if domain:
        cs.add(p, RDFS.domain, _iri(ctx, domain))
    if range:
        rng = URIRef("http://www.w3.org/2001/XMLSchema#" + range[4:]) if range.startswith(
            "xsd:") else _iri(ctx, range)
        cs.add(p, RDFS.range, rng)
    if parent:
        cs.add(p, RDFS.subPropertyOf, _iri(ctx, parent))
    for ch in characteristics or []:
        cs.add(p, RDF.type, OWL[ch if ch.endswith("Property") else ch + "Property"])
    return cs


@operation("owl.createIndividual", capability="rdf(individual)", crudv="C", stage="populate",
           writes=True)
def create_individual(self: Platform, ctx, name: str, cls: str, label: str | None = None,
                      graph: str = "kg") -> ChangeSet:
    """Create a named individual of a class (in the KG graph by default)."""
    target = ctx.layout.kg if graph == "kg" else ctx.layout.main
    i = ctx.entity_prefs.mint(name, "individual", ctx.exists)
    cs = ChangeSet("owl.createIndividual", {"iri": str(i), "cls": cls}, target)
    cs.add(i, RDF.type, OWL.NamedIndividual).add(i, RDF.type, _iri(ctx, cls))
    cs.add(i, RDFS.label, _lit(label or name, "en"))
    return cs


def _parse_axiom(ctx: ProjectContext, kind: str, subject: str, expression: str) -> Axiom:
    sfp = ctx.sfp(staged=True)
    ce = manchester.parse(expression, sfp)
    s = _iri(ctx, subject)
    if kind == "SubClassOf":
        return Axiom("SubClassOf", (s, ce))
    if kind == "EquivalentTo":
        return Axiom("EquivalentClasses", (s, ce))
    if kind == "DisjointWith":
        return Axiom("DisjointClasses", (s, ce))
    if kind in ("Domain", "Range"):
        return Axiom("PropertyDomain" if kind == "Domain" else "PropertyRange", (s, ce))
    if kind == "Type":
        return Axiom("ClassAssertion", (ce, s))
    raise ValueError("kind is SubClassOf | EquivalentTo | DisjointWith | Domain | Range | Type")


@operation("owl.addAxiom", capability="rdf(%resource_role%, taxonomy)", crudv="C",
           stage="model", writes=True, resource_param="subject")
def add_axiom(self: Platform, ctx, subject: str, kind: str, expression: str) -> ChangeSet:
    """Add an axiom written in Manchester syntax (e.g. SubClassOf 'has part' some Wheel)."""
    ax = _parse_axiom(ctx, kind, subject, expression)
    cs = ChangeSet("owl.addAxiom", {"subject": subject, "kind": kind,
                                    "expression": expression}, ctx.layout.main)
    return cs.add_all(axiom_triples(ax))


@operation("owl.removeAxiom", capability="rdf(%resource_role%, taxonomy)", crudv="D",
           stage="model", writes=True, resource_param="subject")
def remove_axiom(self: Platform, ctx, subject: str, kind: str, expression: str) -> ChangeSet:
    """Remove an axiom (exact, including its blank-node structure)."""
    ax = _parse_axiom(ctx, kind, subject, expression)
    g = ctx.ontology(staged=True, with_imports=False)
    triples = axiom_triples(ax, g)
    if not triples:
        raise ValueError(f"axiom not found: {kind} {expression}")
    return ChangeSet("owl.removeAxiom", {"subject": subject, "kind": kind,
                                         "expression": expression}, ctx.layout.main
                     ).remove_all(triples)


@operation("owl.setAnnotation", capability="rdf(%resource_role%, lexicalization)", crudv="C",
           stage="model", writes=True, resource_param="subject", lang_param="lang")
def set_annotation(self: Platform, ctx, subject: str, property: str, value: str,
                   lang: str | None = "en", replace: bool = False) -> ChangeSet:
    """Add (or replace, per language) an annotation value."""
    s, p = _iri(ctx, subject), _iri(ctx, property) if not property.startswith(
        ("rdfs:", "skos:")) else {"rdfs:label": RDFS.label, "rdfs:comment": RDFS.comment,
                                  "skos:definition": SKOS.definition,
                                  "skos:prefLabel": SKOS.prefLabel,
                                  "skos:altLabel": SKOS.altLabel}[property]
    g = ctx.ontology(staged=True, with_imports=False)
    target = ctx.layout.kg if (s, None, None) in ctx.kg(staged=True) else ctx.layout.main
    cs = ChangeSet("owl.setAnnotation", {"subject": str(s), "property": str(p)}, target)
    if replace:
        for o in g.objects(s, p):
            if isinstance(o, Literal) and (o.language or None) == lang:
                cs.remove(s, p, o)
    return cs.add(s, p, _lit(value, lang))


@operation("owl.checkExpression", capability="rdf", crudv="R", stage="model")
def check_expression(self: Platform, ctx, expression: str) -> dict:
    """Protégé OWLExpressionChecker: parse a Manchester class expression."""
    sfp = ctx.sfp(staged=True)
    err = manchester.check(expression, sfp)
    if err is None:
        return {"ok": True, "rendering": manchester.render(manchester.parse(expression, sfp), sfp)}
    return {"ok": False, "message": str(err), "offset": err.offset,
            "expected": sorted(err.expected)}


@operation("owl.complete", capability="rdf", crudv="R", stage="model")
def complete_expression(self: Platform, ctx, text: str, caret: int | None = None) -> dict:
    """Protégé AutoCompleter proposals at the caret."""
    word, props = manchester.complete(text, len(text) if caret is None else caret,
                                      ctx.sfp(staged=True))
    return {"word": word, "proposals": [p.__dict__ for p in props]}

# =========================================================================== #
# Refactoring (Protégé + ST Refactor)
# =========================================================================== #


def _g(ctx):
    return ctx.ontology(staged=True, with_imports=False)


@operation("refactor.renameIRI", capability="rdf(%resource_role%)", crudv="U", stage="model",
           writes=True, resource_param="old")
def rename_iri_op(self: Platform, ctx, old: str, new: str) -> ChangeSet:
    """Change an entity IRI everywhere (ST changeResourceURI / Protégé rename)."""
    from .vkg.validate import rename_in_mappings
    o, n = _iri(ctx, old), _iri(ctx, new)
    cs = refactor.rename_iri(_g(ctx), o, n, ctx.layout.main)
    # FR-VKG-01: R2RML maps and alignment cells follow the rename in the same commit.
    rem, add = rename_in_mappings(ctx.tracker.view(ctx.layout.mappings, staged=True), o, n)
    return cs.remove_all(rem, graph=ctx.layout.mappings).add_all(add, graph=ctx.layout.mappings)


@operation("refactor.mergeEntities", capability="rdf(%resource_role%)", crudv="UD",
           stage="model", writes=True, resource_param="target")
def merge_op(self: Platform, ctx, sources: list[str], target: str) -> ChangeSet:
    """Merge source entities into a target (Protégé Merge into entity)."""
    return refactor.merge_entities(_g(ctx), [_iri(ctx, s) for s in sources], _iri(ctx, target),
                                   ctx.layout.main)


@operation("refactor.deleteEntity", capability="rdf(%resource_role%)", crudv="D",
           stage="model", writes=True, resource_param="entity")
def delete_op(self: Platform, ctx, entity: str, include_descendants: bool = False) -> ChangeSet:
    """Delete an entity and every axiom referencing it (Protégé OWLEntityDeleter)."""
    return refactor.delete_entities(_g(ctx), [_iri(ctx, entity)], ctx.layout.main,
                                    include_descendants=include_descendants)


@operation("refactor.convertToDefined", capability="rdf(cls, taxonomy)", crudv="U",
           stage="model", writes=True)
def to_defined_op(self: Platform, ctx, cls: str) -> ChangeSet:
    """Turn necessary conditions into a definition."""
    return refactor.convert_to_defined(_g(ctx), _iri(ctx, cls), ctx.layout.main)


@operation("refactor.convertToPrimitive", capability="rdf(cls, taxonomy)", crudv="U",
           stage="model", writes=True)
def to_primitive_op(self: Platform, ctx, cls: str) -> ChangeSet:
    """Turn a definition into necessary conditions."""
    return refactor.convert_to_primitive(_g(ctx), _iri(ctx, cls), ctx.layout.main)


@operation("refactor.makeSiblingsDisjoint", capability="rdf(cls, taxonomy)", crudv="C",
           stage="model", writes=True)
def siblings_disjoint_op(self: Platform, ctx, cls: str) -> ChangeSet:
    """Make primitive siblings disjoint."""
    return refactor.make_primitive_siblings_disjoint(_g(ctx), _iri(ctx, cls), ctx.layout.main)


@operation("refactor.addClosureAxiom", capability="rdf(cls, taxonomy)", crudv="C",
           stage="model", writes=True)
def closure_op(self: Platform, ctx, cls: str) -> ChangeSet:
    """Add universal closure axioms for existential restrictions."""
    return refactor.create_closure_axiom(_g(ctx), _iri(ctx, cls), ctx.layout.main)


@operation("refactor.addCoveringAxiom", capability="rdf(cls, taxonomy)", crudv="C",
           stage="model", writes=True)
def covering_op(self: Platform, ctx, cls: str) -> ChangeSet:
    """Add a covering axiom C ⊑ C1 ⊔ … ⊔ Cn over the children."""
    return refactor.add_covering_axiom(_g(ctx), _iri(ctx, cls), ctx.layout.main)


@operation("refactor.replaceBaseURI", capability="rdf", crudv="U", stage="model", writes=True)
def base_uri_op(self: Platform, ctx, old_base: str, new_base: str) -> ChangeSet:
    """Move every IRI from one namespace to another."""
    return refactor.replace_base_uri(_g(ctx), old_base, new_base, ctx.layout.main)


@operation("refactor.deprecate", capability="rdf(%resource_role%)", crudv="U", stage="model",
           writes=True, resource_param="entity")
def deprecate_op(self: Platform, ctx, entity: str, replaced_by: str | None = None,
                 reason: str | None = None) -> ChangeSet:
    """Deprecate an entity (Protégé basic profile)."""
    return refactor.deprecate(_g(ctx), _iri(ctx, entity), ctx.layout.main,
                              replaced_by=_iri(ctx, replaced_by) if replaced_by else None,
                              reason=reason)

# =========================================================================== #
# SKOS (VocBench)
# =========================================================================== #


def _skos(ctx) -> SkosService:
    lex = "skosxl" if ctx.config.lexicalization == Lexicalization.SKOSXL else "skos"
    return SkosService(ctx.ontology(staged=True, with_imports=False), lexicalization=lex)


def _xl_minter(ctx):
    return lambda: ctx.urigen.generate("xLabel", {"lexicalForm": Literal("x", lang="en")},
                                       ctx.exists)


@operation("skos.createConceptScheme", capability="rdf(conceptScheme)", crudv="C",
           stage="model", writes=True, lang_param="lang")
def create_scheme(self: Platform, ctx, label: str, lang: str = "en",
                  iri: str | None = None) -> ChangeSet:
    """Create a concept scheme."""
    s = URIRef(iri) if iri else ctx.urigen.generate("conceptScheme", {}, ctx.exists)
    return _skos(ctx).create_scheme(s, _lit(label, lang), ctx.layout.main, _xl_minter(ctx))


@operation("skos.createConcept", capability="rdf(concept)", crudv="C", stage="model",
           writes=True, lang_param="lang")
def create_concept(self: Platform, ctx, label: str, schemes: list[str], lang: str = "en",
                   broader: str | None = None, iri: str | None = None) -> ChangeSet:
    """Create a SKOS concept (ST SKOS.createConcept with label-clash checks)."""
    c = URIRef(iri) if iri else ctx.urigen.generate("concept", {"label": Literal(label)},
                                                    ctx.exists)
    return _skos(ctx).create_concept(c, _lit(label, lang), [_iri(ctx, s) for s in schemes],
                                     ctx.layout.main, broader=_iri(ctx, broader) if broader
                                     else None, mint_xlabel=_xl_minter(ctx))


@operation("skos.setPrefLabel", capability="rdf(concept, lexicalization)", crudv="C",
           stage="model", writes=True, lang_param="lang")
def set_pref_label(self: Platform, ctx, concept: str, label: str, lang: str = "en") -> ChangeSet:
    """Set a prefLabel (demoting the existing same-language one to altLabel)."""
    return _skos(ctx).set_pref_label(_iri(ctx, concept), _lit(label, lang), ctx.layout.main,
                                     _xl_minter(ctx))


@operation("skos.addAltLabel", capability="rdf(concept, lexicalization)", crudv="C",
           stage="model", writes=True, lang_param="lang")
def add_alt_label(self: Platform, ctx, concept: str, label: str, lang: str = "en") -> ChangeSet:
    """Add an altLabel."""
    return _skos(ctx).add_alt_label(_iri(ctx, concept), _lit(label, lang), ctx.layout.main,
                                    _xl_minter(ctx))


@operation("skos.addBroader", capability="rdf(concept, taxonomy)", crudv="C", stage="model",
           writes=True)
def add_broader(self: Platform, ctx, concept: str, broader: str) -> ChangeSet:
    """Add a broader concept (refuses cycles)."""
    return _skos(ctx).add_broader(_iri(ctx, concept), _iri(ctx, broader), ctx.layout.main)


@operation("skos.removeBroader", capability="rdf(concept, taxonomy)", crudv="D",
           stage="model", writes=True)
def remove_broader(self: Platform, ctx, concept: str, broader: str) -> ChangeSet:
    """Remove a broader link in both directions."""
    return _skos(ctx).remove_broader(_iri(ctx, concept), _iri(ctx, broader), ctx.layout.main)


@operation("skos.deleteConcept", capability="rdf(concept)", crudv="D", stage="model",
           writes=True)
def delete_concept(self: Platform, ctx, concept: str) -> ChangeSet:
    """Delete a concept without narrowers (cascading its SKOS-XL labels)."""
    return _skos(ctx).delete_concept(_iri(ctx, concept), ctx.layout.main)


@operation("skos.topConcepts", capability="rdf(concept)", crudv="R", stage="model")
def top_concepts(self: Platform, ctx, schemes: list[str] | None = None) -> list[dict]:
    """Top concepts (declared, when schemes are given)."""
    return [n.__dict__ | {"iri": str(n.iri)} for n in _skos(ctx).top_concepts(
        [_iri(ctx, s) for s in schemes or []])]


@operation("skos.narrowerConcepts", capability="rdf(concept)", crudv="R", stage="model")
def narrower_concepts(self: Platform, ctx, concept: str,
                      schemes: list[str] | None = None) -> list[dict]:
    """Narrower concepts with 'more' flags."""
    return [n.__dict__ | {"iri": str(n.iri)} for n in _skos(ctx).narrower_concepts(
        _iri(ctx, concept), [_iri(ctx, s) for s in schemes or []])]

# =========================================================================== #
# Reasoning (Protégé)
# =========================================================================== #


@operation("reasoning.classify", capability="rdf", crudv="R", stage="reason")
def classify_op(self: Platform, ctx, reasoner: str | None = None,
                materialise_inferred: bool = True, staged: bool = False) -> dict:
    """Run the selected reasoner; optionally materialise the inferred graph.

    ``staged=True`` classifies the staged view as a *preview* (never materialised)."""
    if reasoner:
        ctx.reasoner.select(reasoner)
    if staged:
        c = ReasonerManager(current=ctx.reasoner.current).classify(ctx.ontology(staged=True))
        ctx.preview = c
        sfp = ctx.sfp(staged=True)
        return {"status": "PREVIEW", **c.provenance(), "consistent": c.consistent,
                "messages": c.messages[:20], "inferred_triples": len(c.inferred),
                "unsatisfiable": [sfp.render(u) for u in c.unsatisfiable]}
    c = ctx.reasoner.classify(ctx.ontology())
    if materialise_inferred and c.consistent:
        ctx.tracker.replace_derived(ctx.layout.inferred, c.inferred)
    self.events.publish(ev.Event(ev.ONTOLOGY_CLASSIFIED, ctx.name, c.provenance()))
    sfp = ctx.sfp()
    return {"status": ctx.reasoner.status.name, **c.provenance(), "consistent": c.consistent,
            "messages": c.messages[:20], "inferred_triples": len(c.inferred),
            "unsatisfiable": [sfp.render(u) for u in c.unsatisfiable]}


@operation("reasoning.status", capability="rdf", crudv="R", stage="reason")
def reasoner_status(self: Platform, ctx) -> dict:
    """Protégé ReasonerStatus (derived) and available backends with profiles."""
    return {"status": ctx.reasoner.status.name, "text": ctx.reasoner.status.value,
            "current": ctx.reasoner.current, "available": ctx.reasoner.available()}


@operation("reasoning.explain", capability="rdf", crudv="R", stage="reason")
def explain_op(self: Platform, ctx, kind: str, sub: str | None = None,
               sup: str | None = None, limit: int = 5, staged: bool = False) -> dict:
    """Justifications for SubClassOf / ClassAssertion / unsatisfiability / inconsistency."""
    e = Entailment(kind, _iri(ctx, sub) if sub else None, _iri(ctx, sup) if sup else None)
    g = ctx.ontology(staged=staged)
    if kind == "type":
        for t in ctx.kg():
            g.add(t)
    r = explain(g, e, limit=limit)
    sfp = ShortFormProvider(g)
    d = r.as_dict()
    d["justifications"] = [[render_axiom(a, sfp) for a in j] for j in r.justifications]
    return d

# =========================================================================== #
# Quality
# =========================================================================== #


def _icv_ctx(ctx: ProjectContext, staged: bool = True) -> icv.Context:
    model = {ModelType.SKOS: "skos", ModelType.RDFS: "rdfs", ModelType.ONTOLEX: "ontolex"}.get(
        ctx.config.model, "owl")
    lex = ctx.config.lexicalization.name.lower()
    g = ctx.ontology(staged=staged, with_imports=False)
    cls = ctx.preview if (staged and ctx.preview is not None) else ctx.reasoner.last
    return icv.Context(g, model, lex, tuple(ctx.config.languages), ctx.layout.main, cls)


@operation("quality.runChecks", capability="rdf", crudv="R", stage="validate")
def run_checks_op(self: Platform, ctx, checks: list[str] | None = None) -> dict:
    """Run the ICV + logical checks applicable to the project's model."""
    findings = icv.run_checks(_icv_ctx(ctx), checks)
    return {"summary": icv.summary(findings), "findings": [f.__dict__ for f in findings]}


@operation("quality.applyFix", capability="rdf", crudv="R", stage="validate", writes=True,
           as_caller=True)
def apply_fix_op(self: Platform, ctx, check: str, caller: Principal) -> ChangeSet:
    """Apply the fix of an ICV check (one change set), under the fix's own capability."""
    chk = icv.REGISTRY[check]
    if chk.fix is None:
        raise ValueError(f"check {check} has no fix")
    self.pdp.require(caller, ctx.name, *chk.fix_capability)
    return chk.fix(_icv_ctx(ctx))


@operation("quality.addCompetencyQuestion", capability="rdf(resource, cq)", crudv="C",
           stage="scope",
           writes=True)
def add_cq(self: Platform, ctx, id: str, question: str, sparql: str,
           expectation: str = "non-empty", priority: str = "must",
           source: str | None = None) -> ChangeSet:
    """Store a competency question with its executable SPARQL test and its priority."""
    q = cqmod.CompetencyQuestion(id, question, sparql, expectation, source=source,
                                 priority=priority)
    # A draft CQ whose SPARQL does not parse yet may be stored: it fails the scope exit
    # criteria (SCP-06) and the release gate until it is fixed.
    bad = [p for p in cqmod.problems(q, _namespaces(ctx)) if not p.startswith("SPARQL")]
    if bad:
        raise ValueError("; ".join(bad))
    return ChangeSet("quality.addCompetencyQuestion", {"id": id}, ctx.layout.cq).add_all(
        q.triples())


@operation("quality.removeCompetencyQuestion", capability="rdf(resource, cq)", crudv="D",
           stage="scope", writes=True)
def remove_cq(self: Platform, ctx, id: str) -> ChangeSet:
    """Remove a competency question."""
    s = cqmod.CompetencyQuestion(id, "", "").iri
    g = ctx.tracker.view(ctx.layout.cq, staged=True)
    triples = list(g.triples((s, None, None)))
    if not triples:
        raise ValueError(f"no competency question {id!r}")
    return ChangeSet("quality.removeCompetencyQuestion", {"id": id}, ctx.layout.cq
                     ).remove_all(triples)


@operation("quality.runCompetencyQuestions", capability="rdf", crudv="R", stage="validate")
def run_cqs(self: Platform, ctx) -> list[dict]:
    """Run every competency question against ontology ∪ KG ∪ inferred."""
    g = _cq_graph(ctx)
    return [cqmod.run_cq(q, g).__dict__ for q in cqmod.CompetencyQuestion.from_graph(
        self.store.graph(ctx.layout.cq))]


@operation("quality.checkCompetencyQuestions", capability="rdf", crudv="R", stage="validate")
def check_cqs(self: Platform, ctx, staged: bool = False) -> list[dict]:
    """FR-QA-03: run every CQ and say whether it could have failed (vacuous/insensitive).
    ``staged=True`` includes proposed CQs and axioms not yet validated."""
    g = _cq_graph(ctx, staged)
    cqg = ctx.tracker.view(ctx.layout.cq, staged=True) if staged \
        else self.store.graph(ctx.layout.cq)
    return [{"priority": q.priority, **cqmod.discrimination(q, g)}
            for q in cqmod.CompetencyQuestion.from_graph(cqg)]


@operation("quality.verbaliseAxioms", capability="rdf", crudv="R", stage="validate")
def verbalise_axioms(self: Platform, ctx, mutants: bool = False, limit: int = 200,
                     staged: bool = True) -> dict:
    """FR-QA-04: the verifiable axioms as controlled English (+ seeded wrong ones)."""
    g, sfp = ctx.ontology(staged=staged), ctx.sfp(staged=staged)
    out = {"axioms": [s.as_dict() for s in semantic.statements(g, sfp, limit)]}
    if mutants:
        out["mutants"] = [s.as_dict() for s in semantic.mutants(g, sfp, limit)]
    return out


def _cq_graph(ctx, staged: bool = False):
    g = ctx.ontology(staged=staged)
    for t in ctx.kg():
        g.add(t)
    if ctx.reasoner.last:
        for t in ctx.reasoner.last.inferred:
            g.add(t)
    return g


@operation("quality.releaseGate", capability="rdf", crudv="R", stage="publish")
def release_gate_op(self: Platform, ctx) -> dict:
    """FR-QA-02: consistent, no blocker, all CQs pass."""
    c = ctx.reasoner.last
    if c is None or c.revision != ctx.tracker._revision:
        c = ctx.reasoner.classify(ctx.ontology())
    findings = icv.run_checks(_icv_ctx(ctx, staged=False))
    cqs = cqmod.CompetencyQuestion.from_graph(self.store.graph(ctx.layout.cq))
    return cqmod.release_gate(findings, c, cqs, _cq_graph(ctx)).as_dict()

# =========================================================================== #
# Scope (NeOn ORSD; reuse candidates as in the Semantic Turkey metadata registry)
# =========================================================================== #


def _namespaces(ctx: ProjectContext) -> dict[str, str]:
    return {"": ctx.config.default_namespace, "rdf": str(RDF), "rdfs": str(RDFS),
            "owl": str(OWL), "skos": str(SKOS)}


def _scope_state(ctx: ProjectContext, staged: bool):
    meta = ctx.tracker.view(ctx.layout.metadata, staged=staged)
    cqg = ctx.tracker.view(ctx.layout.cq, staged=staged)
    spec = orsd.Specification.from_graph(meta, orsd.spec_node(ctx.name))
    if not spec.implementation_language:
        spec.implementation_language = {ModelType.OWL: "OWL 2", ModelType.SKOS: "SKOS",
                                        ModelType.RDFS: "RDFS",
                                        ModelType.ONTOLEX: "OntoLex-Lemon"}[ctx.config.model]
    cqs = cqmod.CompetencyQuestion.from_graph(cqg)
    glossary = orsd.GlossaryTerm.from_graph(cqg)
    reuse = orsd.ReuseCandidate.from_graph(meta)
    ns = _namespaces(ctx)
    ready = orsd.readiness(spec, cqs, glossary, reuse, ctx.config.default_namespace,
                           {q.id: cqmod.problems(q, ns) for q in cqs})
    return spec, cqs, glossary, reuse, ready


@operation("scope.setSpecification", capability="rdf(ontology, metadata)", crudv="U",
           stage="scope", writes=True)
def set_specification(self: Platform, ctx, purpose: str | None = None,
                      scope: str | None = None, implementation_language: str | None = None,
                      intended_users: list[str] | None = None,
                      intended_uses: list[str] | None = None,
                      non_functional: list[str] | None = None) -> ChangeSet:
    """Set fields of the Ontology Requirements Specification (NeOn ORSD); omitted fields
    are kept, given ones are replaced."""
    values = {k: v for k, v in (("purpose", purpose), ("scope", scope),
                                ("implementation_language", implementation_language),
                                ("intended_users", intended_users),
                                ("intended_uses", intended_uses),
                                ("non_functional", non_functional)) if v is not None}
    if not values:
        raise ValueError("no specification field given")
    add, rem = orsd.spec_delta(ctx.tracker.view(ctx.layout.metadata, staged=True),
                               orsd.spec_node(ctx.name), URIRef(ctx.config.base_uri), values)
    return ChangeSet("scope.setSpecification", {"fields": sorted(values)},
                     ctx.layout.metadata).add_all(add).remove_all(rem)


@operation("scope.addReuseCandidate", capability="rdf(ontology, metadata)", crudv="C",
           stage="scope", writes=True)
def add_reuse(self: Platform, ctx, iri: str, title: str, mode: str = "reference",
              uri_space: str = "", rationale: str = "", sparql_endpoint: str = "") -> ChangeSet:
    """Record an ontology or dataset considered for reuse (import | module | align |
    reference), described as a void:Dataset."""
    r = orsd.ReuseCandidate(iri, title, mode, uri_space, rationale, sparql_endpoint)
    return ChangeSet("scope.addReuseCandidate", {"iri": iri, "mode": mode},
                     ctx.layout.metadata).add_all(r.triples())


@operation("scope.removeReuseCandidate", capability="rdf(ontology, metadata)", crudv="D",
           stage="scope", writes=True)
def remove_reuse(self: Platform, ctx, iri: str) -> ChangeSet:
    """Withdraw a reuse candidate."""
    g = ctx.tracker.view(ctx.layout.metadata, staged=True)
    triples = list(g.triples((URIRef(iri), None, None)))
    if not triples:
        raise ValueError(f"no reuse candidate {iri!r}")
    return ChangeSet("scope.removeReuseCandidate", {"iri": iri}, ctx.layout.metadata
                     ).remove_all(triples)


@operation("scope.addGlossaryTerms", capability="rdf(resource, cq)", crudv="C",
           stage="scope", writes=True)
def add_terms(self: Platform, ctx, terms: list) -> ChangeSet:
    """Add pre-glossary terms: strings, or {label, definition, quote} objects."""
    cs = ChangeSet("scope.addGlossaryTerms", {"terms": len(terms)}, ctx.layout.cq)
    for t in terms:
        term = orsd.GlossaryTerm(t) if isinstance(t, str) else orsd.GlossaryTerm(**t)
        if not term.label.strip():
            raise ValueError("a glossary term needs a label")
        cs.add_all(term.triples())
    return cs


@operation("scope.removeGlossaryTerm", capability="rdf(resource, cq)", crudv="D",
           stage="scope", writes=True)
def remove_term(self: Platform, ctx, label: str) -> ChangeSet:
    """Remove a pre-glossary term."""
    s = orsd.GlossaryTerm(label).iri
    triples = list(ctx.tracker.view(ctx.layout.cq, staged=True).triples((s, None, None)))
    if not triples:
        raise ValueError(f"no glossary term {label!r}")
    return ChangeSet("scope.removeGlossaryTerm", {"label": label}, ctx.layout.cq
                     ).remove_all(triples)


@operation("scope.specification", capability="rdf", crudv="R", stage="scope")
def specification_op(self: Platform, ctx, staged: bool = False) -> dict:
    """The ORSD: specification, CQs, pre-glossary, reuse candidates and readiness.
    ``staged=True`` includes proposals not yet validated."""
    spec, cqs, glossary, reuse, ready = _scope_state(ctx, staged)
    return {"specification": spec.as_dict(),
            "competency_questions": [dict(q.__dict__) for q in cqs],
            "glossary": [t.__dict__ for t in glossary],
            "reuse": [r.__dict__ for r in reuse], "readiness": ready.as_dict()}


@operation("scope.readiness", capability="rdf", crudv="R", stage="scope")
def readiness_op(self: Platform, ctx, staged: bool = False) -> dict:
    """The scope stage's exit criteria: required ones decide, advisory ones inform."""
    return _scope_state(ctx, staged)[-1].as_dict()


@operation("scope.exportSpecification", capability="rdf", crudv="R", stage="scope")
def export_specification(self: Platform, ctx, staged: bool = False) -> str:
    """The ORSD as a Markdown document in NeOn's template layout."""
    return orsd.render_markdown(ctx.name, *_scope_state(ctx, staged))

# =========================================================================== #
# I/O, KG construction, alignment, publication
# =========================================================================== #


@operation("io.loadRDF", capability="rdf", crudv="C", stage="acquire", writes=True)
def load_rdf(self: Platform, ctx, data: str, format: str = "turtle",
             target: str = "main", as_import: str | None = None,
             pipeline: list[dict] | None = None) -> ChangeSet | dict:
    """Load RDF into main/kg through the change tracker, or as a read-only import."""
    from .io.pipeline import lift_rdf, run_pipeline
    g = run_pipeline(lift_rdf(data, format), pipeline or [])
    if as_import:
        n = ctx.tracker.replace_derived(ctx.layout.imported(as_import), g)
        cs = ChangeSet("io.addImport", {"ontology": as_import}, ctx.layout.main)
        onto = next(iter(ctx.ontology(with_imports=False).subjects(RDF.type, OWL.Ontology)),
                    None)
        if onto is not None:
            cs.add(onto, OWL.imports, URIRef(as_import))
        commit = ctx.tracker.commit(cs, SYSTEM) if len(cs) else None
        return {"import": as_import, "triples": n, "commit": commit.id if commit else None}
    graph = ctx.layout.kg if target == "kg" else ctx.layout.main
    return ChangeSet("io.loadRDF", {"triples": len(g), "format": format}, graph).add_all(g)


@operation("io.export", capability="rdf", crudv="R", stage="publish")
def export_op(self: Platform, ctx, format: str = "turtle", include_kg: bool = False,
              include_inferred: bool = False, pipeline: list[dict] | None = None) -> str:
    """Export with an optional transformer pipeline (ST Export.export)."""
    from .io.pipeline import export
    g = ctx.ontology(with_imports=False)
    if include_kg:
        for t in ctx.kg():
            g.add(t)
    if include_inferred and ctx.reasoner.last:
        for t in ctx.reasoner.last.inferred:
            g.add(t)
    return export(g, format, pipeline)


@operation("acquire.registerSource", capability="rdf", crudv="C", stage="acquire", writes=True)
def register_source(self: Platform, ctx, source_id: str, kind: str, content: str,
                    title: str = "") -> dict:
    """Register a document or table as a project source (FR-ACQ-01)."""
    import hashlib
    if kind not in ("document", "table", "rdf"):
        raise ValueError("kind is document | table | rdf")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    ctx.sources[source_id] = {"id": source_id, "kind": kind, "content": content,
                              "title": title or source_id, "sha256": digest}
    return {"source": source_id, "sha256": digest, "chars": len(content)}


@operation("kg.liftTable", capability="rdf(individual)", crudv="C", stage="populate",
           writes=True)
def lift_table_op(self: Platform, ctx, source_id: str, mapping: dict) -> ChangeSet:
    """Lift a registered CSV source into the KG via a TableMapping (Sheet2RDF role)."""
    from .kg.lifting import ColumnMap, TableMapping, lift_table
    src = ctx.sources[source_id]
    m = TableMapping(mapping["cls"], mapping["iri_template"],
                     [ColumnMap(**c) for c in mapping.get("columns", [])],
                     mapping.get("label_column"))
    existing = ctx.kg(staged=True)
    triples, warnings = lift_table(src["content"], m, ctx.ontology(staged=True), existing)
    cs = ChangeSet("kg.liftTable", {"source": source_id, "sha256": src["sha256"],
                                    "warnings": warnings[:50]}, ctx.layout.kg)
    return cs.add_all(triples)


@operation("kg.resolveEntities", capability="rdf(individual)", crudv="R", stage="populate")
def resolve_op(self: Platform, ctx, threshold: float = 0.85,
               key_properties: list[str] | None = None) -> list[dict]:
    """Duplicate-individual candidates (owl:sameAs proposals)."""
    from .kg.lifting import resolve_entities
    return [{"a": str(d.a), "b": str(d.b), "score": d.score, "evidence": d.evidence}
            for d in resolve_entities(ctx.kg(staged=True), threshold,
                                      [_iri(ctx, k) for k in key_properties or []])]


@operation("kg.assertSameAs", capability="rdf(individual)", crudv="C", stage="populate",
           writes=True)
def same_as_op(self: Platform, ctx, a: str, b: str) -> ChangeSet:
    """Assert owl:sameAs between two individuals."""
    return ChangeSet("kg.assertSameAs", {"a": a, "b": b}, ctx.layout.kg).add(
        URIRef(a), OWL.sameAs, URIRef(b))


@operation("kg.projectLPG", capability="rdf", crudv="R", stage="publish")
def lpg_op(self: Platform, ctx) -> dict:
    """Property-graph projection of the KG (FalkorDB contract)."""
    from .kg.lifting import project_lpg
    return project_lpg(ctx.kg(), ctx.ontology())


@operation("alignment.generate", capability="rdf(resource, alignment)", crudv="C",
           stage="model")
def align_generate(self: Platform, ctx, target_project: str | None = None,
                   target_data: str | None = None, threshold: float = 0.8,
                   alignment_id: str = "default") -> dict:
    """Lexical matching against another project or an RDF document."""
    from .alignment.alignment import Alignment, lexical_match
    left = ctx.ontology(staged=True, with_imports=False)
    if target_project:
        right = self.projects[target_project].ontology()
        onto2 = self.projects[target_project].config.base_uri
    else:
        right = Graph().parse(data=target_data, format="turtle")
        onto2 = str(next(iter(right.subjects(RDF.type, OWL.Ontology)), "urn:target"))
    kinds = (OWL.Class, SKOS.Concept, OWL.ObjectProperty, OWL.DatatypeProperty)
    le = sorted({s for k in kinds for s in left.subjects(RDF.type, k) if isinstance(s, URIRef)})
    re_ = sorted({s for k in kinds for s in right.subjects(RDF.type, k) if isinstance(s, URIRef)})
    cells = lexical_match(left, right, le, re_, threshold)
    al = Alignment(ctx.config.base_uri, onto2, cells)
    ctx.alignments[alignment_id] = al
    return {"alignment": alignment_id, "cells": [
        {"entity1": str(c.entity1), "entity2": str(c.entity2), "measure": c.measure,
         "relation": c.relation} for c in cells]}


@operation("alignment.validateCell", capability="rdf(resource, alignment)", crudv="U",
           stage="model")
def align_validate(self: Platform, ctx, entity1: str, entity2: str, decision: str,
                   alignment_id: str = "default", forced_property: str | None = None) -> dict:
    """Accept or reject one cell (ST Alignment.acceptAlignment / rejectAlignment)."""
    al = ctx.alignments[alignment_id]
    cell = next(c for c in al.cells if str(c.entity1) == entity1 and str(c.entity2) == entity2)
    if decision == "accept":
        al.accept(cell, lambda e: entity_role(ctx.ontology(), e),
                  URIRef(forced_property) if forced_property else None)
    else:
        cell.status = "rejected"
    return {"status": cell.status, "property": str(cell.mapping_property or ""),
            "comment": cell.comment}


@operation("alignment.apply", capability="rdf(resource, alignment)", crudv="C", stage="model",
           writes=True)
def align_apply(self: Platform, ctx, alignment_id: str = "default",
                delete_rejected: bool = False) -> ChangeSet:
    """Write accepted cells into the mappings graph (ST applyValidation)."""
    al = ctx.alignments[alignment_id]
    cs, _ = al.apply_validation(ctx.layout.mappings, self.store.graph(ctx.layout.mappings),
                                lambda e: entity_role(ctx.ontology(), e), delete_rejected)
    return cs


@operation("sparql.update", capability="rdf(sparql)", crudv="U", stage="model",
           writes=True)
def sparql_update(self: Platform, ctx, update: str, target: str = "main") -> ChangeSet:
    """SPARQL Update executed on a scratch copy, diffed, committed as a change set."""
    graph = ctx.layout.kg if target == "kg" else ctx.layout.main
    before = ctx.kg(staged=True) if target == "kg" else ctx.ontology(staged=True,
                                                                     with_imports=False)
    after = Graph()
    for t in before:
        after.add(t)
    after.update(update)
    cs = ChangeSet("sparql.update", {"update": update[:2000]}, graph)
    cs.remove_all(t for t in before if t not in after)
    cs.add_all(t for t in after if t not in before)
    return cs


@operation("lifecycle.status", capability="rdf", crudv="R", stage="govern")
def lifecycle_status(self: Platform, ctx) -> dict:
    """Lifecycle stage states of the project."""
    return dict(ctx.lifecycle)


@operation("lifecycle.setStage", capability="rdf", crudv="R", stage="govern",
           writes=True, as_caller=True)
def lifecycle_set(self: Platform, ctx, stage: str, state: str, caller: Principal,
                  note: str = "") -> dict:
    """Record a stage transition; closing review/publish requires a human (FR-LC-01)."""
    if caller.is_machine and stage in ("review", "publish") and state == "done":
        raise AuthorizationError(f"closing the {stage} gate is a human decision")
    if stage not in ctx.lifecycle:
        raise ValueError(f"unknown stage {stage!r}")
    if state not in ("not-started", "in-progress", "awaiting-gate", "done"):
        raise ValueError("state is not-started | in-progress | awaiting-gate | done")
    ctx.lifecycle[stage] = state
    return {"stage": stage, "state": state, "note": note}

# =========================================================================== #
# Virtual knowledge graph: R2RML mappings (Ontop role) — FR-VKG-01, FR-VKG-02
#
# Mapping edits are change sets on the ``mappings`` graph, the graph alignment.apply
# writes too, so they take the capability Semantic Turkey's *mapper* role holds,
# rdf(resource, alignment) (ontologist, rdfgeek and project manager hold it as well).
# Reads take rdf R; querying the mapped data takes sparql.query's capability.
# =========================================================================== #

_VKG_W = "rdf(resource, alignment)"


def _map_iri(ctx: ProjectContext, map_id: str) -> str:
    import re
    if map_id.startswith(("http://", "https://", "urn:")):
        return map_id
    if not re.match(r"^[A-Za-z][A-Za-z0-9_.-]{0,99}$", map_id):
        raise ValueError(f"triples map id {map_id!r}: letters, digits, '_', '.', '-'")
    return f"urn:sip:p:{ctx.name}:r2rml#{map_id}"


def _vkg_graph(ctx: ProjectContext, staged: bool = True) -> Graph:
    return ctx.tracker.view(ctx.layout.mappings, staged=staged)


def _vkg_maps(ctx: ProjectContext, staged: bool = True, warnings: list | None = None):
    from .vkg.r2rml import parse_maps
    return parse_maps(_vkg_graph(ctx, staged), warnings)


def _vkg_build(ctx: ProjectContext, m: dict, source_id: str | None):
    from .vkg.r2rml import TriplesMap
    from .vkg.source import check_select, check_table_name
    tm = TriplesMap.from_dict(m, mint=lambda i: _map_iri(ctx, i),
                              resolve=lambda x: str(_iri(ctx, x)))
    if source_id:
        tm.source = source_id
    if tm.sql_query is not None:
        check_select(tm.sql_query)          # UnsafeSQL: non-SELECT logical tables refused
    else:
        check_table_name(tm.table_name)
    return tm


def _vkg_source(ctx: ProjectContext, source_id: str):
    try:
        return ctx.databases[source_id]
    except KeyError:
        raise KeyError(f"no registered database {source_id!r}") from None


@operation("mapping.registerDatabase", capability=_VKG_W, crudv="C", stage="populate",
           writes=True)
def map_register_db(self: Platform, ctx, source_id: str, kind: str = "sqlite",
                    path: str | None = None, script: str | None = None, title: str = "",
                    ontop_endpoint: str | None = None) -> dict:
    """Register a relational database (sqlite file or DDL+INSERT script; duckdb if installed)."""
    from .vkg.source import RelationalSource
    old = ctx.databases.get(source_id)
    src = RelationalSource(source_id, kind, path, script, title, ontop_endpoint)
    if old is not None:
        old.close()
    ctx.databases[source_id] = src
    return src.describe()


@operation("mapping.introspect", capability="rdf", crudv="R", stage="populate")
def map_introspect(self: Platform, ctx, source_id: str | None = None) -> dict:
    """Schema of a registered database (tables, columns, types, keys), or the database list."""
    if source_id is None:
        return {"databases": [s.describe() for _, s in sorted(ctx.databases.items())]}
    src = _vkg_source(ctx, source_id)
    return {"source": source_id, **src.schema(refresh=True).as_dict()}


@operation("mapping.suggest", capability="rdf", crudv="R", stage="populate")
def map_suggest(self: Platform, ctx, source_id: str, threshold: float = 0.75,
                tables: list[str] | None = None, staged: bool = True) -> list[dict]:
    """Scored R2RML proposals from schema + ontology (table/class, column/property, FK,
    subclass tables, discriminators, IRI templates); writes nothing."""
    from .vkg.suggest import suggest
    base = ctx.config.base_uri.rstrip("/#") + "/data/"
    return suggest(_vkg_source(ctx, source_id), ctx.ontology(staged=staged), data_base=base,
                   threshold=threshold, tables=tables)


@operation("mapping.addTriplesMap", capability=_VKG_W, crudv="C", stage="populate",
           writes=True)
def map_add(self: Platform, ctx, map: dict, source_id: str | None = None) -> ChangeSet:
    """Add an R2RML triples map (dict form; see vkg.r2rml.TriplesMap.from_dict)."""
    tm = _vkg_build(ctx, map, source_id)
    if URIRef(tm.iri) in {URIRef(m.iri) for m in _vkg_maps(ctx)}:
        raise ValueError(f"triples map {tm.id!r} exists; use mapping.updateTriplesMap")
    return ChangeSet("mapping.addTriplesMap", {"map": tm.iri, "source": tm.source},
                     ctx.layout.mappings).add_all(tm.triples())


@operation("mapping.updateTriplesMap", capability=_VKG_W, crudv="U", stage="populate",
           writes=True)
def map_update(self: Platform, ctx, map: dict, source_id: str | None = None) -> ChangeSet:
    """Replace a triples map; only the triples that differ are recorded."""
    from .vkg.r2rml import map_nodes
    tm = _vkg_build(ctx, map, source_id)
    g = _vkg_graph(ctx)
    old = map_nodes(g, URIRef(tm.iri))
    if not old:
        raise ValueError(f"no triples map {tm.id!r}")
    if tm.source is None:
        from .core.namespaces import SIP
        tm.source = next((str(o) for s, p, o in old if p == SIP.source
                          and s == URIRef(tm.iri)), None)
    return ChangeSet("mapping.updateTriplesMap", {"map": tm.iri}, ctx.layout.mappings
                     ).remove_all(old).add_all(tm.triples())


@operation("mapping.removeTriplesMap", capability=_VKG_W, crudv="D", stage="populate",
           writes=True)
def map_remove(self: Platform, ctx, map_id: str, force: bool = False) -> ChangeSet:
    """Remove a triples map (refused while another map uses it as parent, unless forced)."""
    from .vkg.r2rml import map_nodes
    iri = _map_iri(ctx, map_id)
    triples = map_nodes(_vkg_graph(ctx), URIRef(iri))
    if not triples:
        raise ValueError(f"no triples map {map_id!r}")
    users = [m.id for m in _vkg_maps(ctx) if any(p.ref and p.ref.parent == iri for p in m.poms)]
    if users and not force:
        raise ValueError(f"{map_id} is the parent map of {users}; remove those or force=True")
    return ChangeSet("mapping.removeTriplesMap", {"map": iri}, ctx.layout.mappings
                     ).remove_all(triples)


@operation("mapping.list", capability="rdf", crudv="R", stage="populate")
def map_list(self: Platform, ctx, staged: bool = True) -> dict:
    """The project's triples maps (staged view by default) with their review status."""
    warnings: list[str] = []
    maps = _vkg_maps(ctx, staged, warnings)
    committed = {m.iri for m in _vkg_maps(ctx, False)}
    return {"maps": [dict(m.as_dict(), status="committed" if m.iri in committed else "staged")
                     for m in maps], "warnings": warnings}


@operation("mapping.export", capability="rdf", crudv="R", stage="publish")
def map_export(self: Platform, ctx, staged: bool = False, format: str = "turtle") -> str:
    """The mappings as an R2RML document (blank-node form, as Ontop expects)."""
    from .vkg.r2rml import to_graph
    prefixes = {"": ctx.config.default_namespace, "owl": str(OWL), "skos": str(SKOS)}
    return to_graph(_vkg_maps(ctx, staged), prefixes=prefixes).serialize(format=format)


@operation("mapping.import", capability=_VKG_W, crudv="C", stage="populate", writes=True)
def map_import(self: Platform, ctx, data: str, format: str = "turtle",
               source_id: str | None = None, replace: bool = False) -> ChangeSet:
    """Load an R2RML document into the mappings graph as one change set (maps with the same
    IRI are replaced; ``replace=True`` also drops every other map)."""
    from .vkg.r2rml import map_nodes, parse_maps
    from .vkg.source import check_select, check_table_name
    warnings: list[str] = []
    maps = parse_maps(Graph().parse(data=data, format=format,
                                    publicID=f"urn:sip:p:{ctx.name}:r2rml"), warnings)
    if not maps:
        raise ValueError("no triples map in the document" + (f": {warnings}" if warnings else ""))
    cs = ChangeSet("mapping.import", {"maps": [m.iri for m in maps], "warnings": warnings[:50]},
                   ctx.layout.mappings)
    g = _vkg_graph(ctx)
    new = {m.iri for m in maps}
    for m in _vkg_maps(ctx):
        if replace or m.iri in new:
            cs.remove_all(map_nodes(g, URIRef(m.iri)))
    for m in maps:
        if source_id and not m.source:
            m.source = source_id
        if m.sql_query is not None:
            check_select(m.sql_query)
        else:
            check_table_name(m.table_name)
        cs.add_all(m.triples())
    return cs


@operation("mapping.validate", capability="rdf", crudv="R", stage="validate")
def map_validate(self: Platform, ctx, staged: bool = True, source_id: str | None = None,
                 data_limit: int | None = 1000) -> dict:
    """Static checks of the maps against the (staged) ontology and the schemas, the
    conformance rules M04-M12, data checks D1-D4 on a sample (``data_limit=None`` skips
    them) and coverage."""
    from .vkg.validate import coverage, validate
    warnings: list[str] = []
    maps = _vkg_maps(ctx, staged, warnings)
    onto = ctx.ontology(staged=staged)
    findings = validate(maps, onto, ctx.databases, default_source=source_id,
                        data_limit=data_limit)
    summary = {s: sum(f["severity"] == s for f in findings) for s in ("error", "warning", "info")}
    return {"maps": len(maps), "summary": summary, "findings": findings,
            "coverage": coverage(maps, onto, ctx.config.default_namespace),
            "warnings": warnings}


@operation("mapping.preview", capability="rdf", crudv="R", stage="populate")
def map_preview(self: Platform, ctx, map_id: str | None = None, term: str | None = None,
                limit: int = 20, staged: bool = True) -> dict:
    """Sample triples (with the producing map) for one triples map or one ontology term."""
    from .vkg.materialise import materialise
    from .vkg.validate import impact
    maps = _vkg_maps(ctx, staged)
    if map_id:
        only = {_map_iri(ctx, map_id)}
    elif term:
        only = {a["map"] for a in impact(maps, [str(_iri(ctx, term))])}
    else:
        only = None
    if only is not None and not only & {m.iri for m in maps}:
        raise ValueError(f"no triples map for {map_id or term!r}")
    res = materialise(maps, ctx.databases, limit=limit, only=only)
    triples = sorted(res.provenance.items(), key=lambda kv: tuple(map(str, kv[0])))
    return {"triples": [{"s": str(s), "p": str(p), "o": str(o), "maps": sorted(tms)}
                        for (s, p, o), tms in triples],
            "rows": res.rows, "warnings": res.warnings}


@operation("mapping.queryData", capability="rdf(sparql, core)", crudv="R", stage="consume")
def map_query(self: Platform, ctx, query: str, staged: bool = True, entailment: str = "rdfs",
              limit: int | None = None, row_limit: int | None = None,
              include_kg: bool = False, engine: str = "local",
              endpoint: str | None = None) -> dict:
    """SPARQL over the virtual graph: mapped data + the (staged) ontology, with entailment,
    so ontology edits change the answers without re-mapping. ``engine="ontop"`` sends the
    query to an external Ontop endpoint instead (off by default)."""
    from .vkg import query as vq
    if engine == "ontop":
        url = endpoint or next((s.ontop_endpoint for s in ctx.databases.values()
                                if s.ontop_endpoint), None)
        if not url:
            raise ValueError("engine 'ontop' needs an endpoint (argument or registerDatabase)")
        return vq.ontop_query(url, query)
    if engine != "local":
        raise ValueError("engine is local | ontop")
    from .vkg.materialise import materialise
    res = materialise(_vkg_maps(ctx, staged), ctx.databases, limit=row_limit)
    data = res.graph
    if include_kg:
        for t in ctx.kg(staged=staged):
            data.add(t)
    g = vq.virtual_graph(ctx.ontology(staged=staged), data, entailment)
    out = vq.run_sparql(g, query, limit)
    out.update({"engine": "local", "staged": staged, "entailment": entailment,
                "mapped_triples": len(res.graph), "warnings": res.warnings})
    return out


@operation("mapping.impact", capability="rdf", crudv="R", stage="model")
def map_impact(self: Platform, ctx, entities: list[str], staged: bool = True) -> dict:
    """Triples maps affected by renaming or deleting the given ontology entities."""
    from .vkg.validate import impact
    iris = [str(_iri(ctx, e)) for e in entities]
    return {"entities": iris, "affected": impact(_vkg_maps(ctx, staged), iris)}


# --------------------------------------------------------------------------- #
# Mapping Studio R0: IRI policy (EntityDefs), patterns, lifting, the YAML spec
# (sip/architecture/components/MAPPING_STUDIO.md §6-§7). EntityDefs live in the
# mappings graph next to the maps; a map compiled from a pattern carries sip:pattern.
# --------------------------------------------------------------------------- #

def _vkg_entities(ctx: ProjectContext, staged: bool = True):
    from .vkg.patterns import parse_entities
    return parse_entities(_vkg_graph(ctx, staged))


def _vkg_policy(ctx: ProjectContext, maps, staged: bool = True):
    """(entities, default schema, inferred?) — stored EntityDefs, else inferred from maps."""
    from .vkg.patterns import infer_entities
    inferred, schema = infer_entities(maps)
    stored = _vkg_entities(ctx, staged)
    return (stored or inferred), schema, not stored


def _data_base(ctx: ProjectContext) -> str:
    return ctx.config.base_uri.rstrip("/#") + "/data/"


def _pattern_params(ctx: ProjectContext, params: dict) -> dict:
    """Resolve CURIEs / local names of ontology terms in pattern parameters."""
    from rdflib.namespace import XSD as _XSD

    def term(x: str) -> str:
        return str(_XSD) + x[4:] if x.startswith("xsd:") else str(_iri(ctx, x))
    out = dict(params)
    if out.get("class"):
        out["class"] = term(out["class"])
    if out.get("properties"):
        out["properties"] = [dict(p, predicate=term(p["predicate"]),
                                  **({"datatype": term(p["datatype"])} if p.get("datatype")
                                     else {})) for p in out["properties"]]
    if out.get("cases"):
        out["cases"] = {v: dict(c, **{"class": term(c["class"])})
                        for v, c in out["cases"].items()}
    if out.get("links"):
        out["links"] = [dict(ln, predicate=term(ln["predicate"])) for ln in out["links"]]
    return out


@operation("mapping.setEntity", capability=_VKG_W, crudv="C", stage="populate", writes=True)
def map_set_entity(self: Platform, ctx, name: str, path: str, table: str, key,
                   base: str | None = None) -> ChangeSet:
    """Define or change one identity of the IRI policy; maps compiled from it are
    recompiled in the same commit, so one undo reverts both."""
    import re
    from .core.namespaces import SIP
    from .vkg.patterns import EntityDef, compile_map, entity_iri, entity_triples, lift
    from .vkg.r2rml import map_nodes
    if not re.match(r"^[A-Za-z][A-Za-z0-9_.-]{0,99}$", name):
        raise ValueError(f"entity name {name!r}: letters, digits, '_', '.', '-'")
    new = EntityDef(name, path.strip("/"), table, key, base or _data_base(ctx))
    g = _vkg_graph(ctx)
    old_ents = _vkg_entities(ctx)
    cs = ChangeSet("mapping.setEntity", {"entity": name, **new.as_dict()}, ctx.layout.mappings)
    cs.remove_all(list(g.triples((entity_iri(ctx.name, name), None, None))))
    cs.add_all(entity_triples(ctx.name, new))
    if name in old_ents:
        ents = dict(old_ents, **{name: new})
        maps = _vkg_maps(ctx)
        _, schema, _ = _vkg_policy(ctx, maps)
        for tm in maps:
            got = lift(tm, old_ents, schema=schema)
            uses = got and (got[1]["subject"] == name or any(
                p.get("ref") == name for p in got[1].get("properties", [])))
            if uses:
                again = compile_map(got[1], ents, schema=schema)
                cs.remove_all([t for t in map_nodes(g, URIRef(tm.iri))
                               if t[1] != SIP.pattern])
                cs.add_all(again.triples())
    return cs


@operation("mapping.removeEntity", capability=_VKG_W, crudv="D", stage="populate",
           writes=True)
def map_remove_entity(self: Platform, ctx, name: str, force: bool = False) -> ChangeSet:
    """Remove an identity of the IRI policy (refused while maps are compiled from it)."""
    from .vkg.patterns import entity_iri, lift
    triples = list(_vkg_graph(ctx).triples((entity_iri(ctx.name, name), None, None)))
    if not triples:
        raise ValueError(f"no entity {name!r}")
    ents = _vkg_entities(ctx)
    maps = _vkg_maps(ctx)
    _, schema, _ = _vkg_policy(ctx, maps)
    users = [tm.id for tm in maps if (got := lift(tm, ents, schema=schema)) and (
        got[1]["subject"] == name or any(p.get("ref") == name
                                         for p in got[1].get("properties", [])))]
    if users and not force:
        raise ValueError(f"maps {users} are compiled from entity {name!r}; remove them or "
                         "force=True")
    return ChangeSet("mapping.removeEntity", {"entity": name}, ctx.layout.mappings
                     ).remove_all(triples)


@operation("mapping.applyPattern", capability=_VKG_W, crudv="C", stage="populate",
           writes=True)
def map_apply_pattern(self: Platform, ctx, pattern: str, params: dict,
                      source_id: str | None = None, schema: str | None = None) -> ChangeSet:
    """Compile a mapping pattern (P01-P08) with its parameters into triples maps, adding
    them or replacing maps with the same id, as one change set."""
    from .core.namespaces import SIP
    from .vkg.patterns import PatternError, compile_pattern
    from .vkg.r2rml import map_nodes
    ents = _vkg_entities(ctx)
    if not ents:
        raise ValueError("define the IRI policy first (mapping.setEntity)")
    try:
        maps = compile_pattern(pattern, _pattern_params(ctx, params), ents, schema=schema,
                               mint=lambda i: _map_iri(ctx, i))
    except (PatternError, KeyError) as e:
        raise ValueError(f"pattern {pattern}: {e}") from None
    g = _vkg_graph(ctx)
    cs = ChangeSet("mapping.applyPattern", {"pattern": pattern, "maps": [m.iri for m in maps]},
                   ctx.layout.mappings)
    for tm in maps:
        if source_id:
            tm.source = source_id
        cs.remove_all(map_nodes(g, URIRef(tm.iri)))
        cs.add_all(tm.triples())
        cs.add(URIRef(tm.iri), SIP.pattern, Literal(pattern))
    return cs


@operation("mapping.lift", capability="rdf", crudv="R", stage="populate")
def map_lift(self: Platform, ctx, staged: bool = True) -> dict:
    """Pattern view of the maps: each map's pattern and parameters, or ``custom`` when no
    pattern reproduces it exactly. Uses the stored IRI policy, else one inferred from the
    maps' templates."""
    from .vkg.patterns import lift_all
    maps = _vkg_maps(ctx, staged)
    ents, schema, inferred = _vkg_policy(ctx, maps, staged)
    db = next(iter(ctx.databases.values())).schema() if len(ctx.databases) == 1 else None
    out = lift_all(maps, ents, schema=schema, db_schema=db)
    out.update({"entities": {n: e.as_dict() for n, e in sorted(ents.items())},
                "entities_inferred": inferred, "schema": schema})
    return out


@operation("mapping.importSpec", capability=_VKG_W, crudv="C", stage="populate", writes=True)
def map_import_spec(self: Platform, ctx, spec, source_id: str | None = None,
                    replace: bool = False) -> ChangeSet:
    """Load a YAML mapping spec (text or dict, the SPARQL-2-SQL PoC's format): its
    entities become the IRI policy and its maps are compiled through the patterns.
    Maps and entities with the same names are replaced; ``replace=True`` drops all others."""
    from .vkg.patterns import entity_iri, entity_triples, parse_entities
    from .vkg.r2rml import map_nodes
    from .vkg.spec import compile_spec, load_spec
    data = load_spec(spec) if isinstance(spec, str) else spec
    ents, maps = compile_spec(data, mint=lambda i: _map_iri(ctx, i))
    g = _vkg_graph(ctx)
    cs = ChangeSet("mapping.importSpec", {"maps": [m.iri for m in maps],
                                          "entities": sorted(ents)}, ctx.layout.mappings)
    new = {m.iri for m in maps}
    for m in _vkg_maps(ctx):
        if replace or m.iri in new:
            cs.remove_all(map_nodes(g, URIRef(m.iri)))
    for name in parse_entities(g):
        if replace or name in ents:
            cs.remove_all(list(g.triples((entity_iri(ctx.name, name), None, None))))
    for e in ents.values():
        cs.add_all(entity_triples(ctx.name, e))
    for m in maps:
        if source_id:
            m.source = source_id
        cs.add_all(m.triples())
    return cs


@operation("mapping.exportSpec", capability="rdf", crudv="R", stage="publish")
def map_export_spec(self: Platform, ctx, staged: bool = False, format: str = "yaml"):
    """The mappings as a YAML spec (``format="dict"`` for the parsed form). Maps no
    pattern reproduces are listed under ``custom`` in R2RML dict form."""
    import re
    from rdflib.namespace import XSD as _XSD
    from .vkg.spec import dump_spec, maps_to_spec
    maps = _vkg_maps(ctx, staged)
    ents, schema, _ = _vkg_policy(ctx, maps, staged)
    used = {u for m in maps for u in m.terms()}
    prefixes = {"xsd": str(_XSD)}
    if any(u.startswith(ctx.config.default_namespace) for u in used):
        prefixes[re.sub(r"[^A-Za-z0-9_-]", "-", ctx.name)] = ctx.config.default_namespace
    for p, ns in ctx.ontology(with_imports=False).namespaces():
        if p and any(u.startswith(str(ns)) for u in used) and str(ns) not in prefixes.values():
            prefixes[p] = str(ns)
    bases = [e.base for e in ents.values()]
    base = max(set(bases), key=bases.count) if bases else _data_base(ctx)
    out = maps_to_spec(maps, ents, base_iri=base, prefixes=prefixes, schema=schema)
    if format == "dict":
        return out
    if format != "yaml":
        raise ValueError("format is yaml | dict")
    return dump_spec(out)


def describe_operations() -> list[dict]:
    return [{"name": o.name, "stage": o.stage, "capability": o.capability, "crudv": o.crudv,
             "writes": o.writes, "params": o.params, "description": o.description}
            for o in sorted(OPERATIONS.values(), key=lambda o: (STAGES.index(o.stage), o.name))]


def dumps(obj) -> str:
    return json.dumps(obj, indent=2, default=str)
