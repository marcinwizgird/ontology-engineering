"""The ``viz.*`` operations, registered with SIP's operation registry.

Importing this module adds the operations to ``semantic_intelligence.platform.OPERATIONS``
with the same decorator SIP's own operations use, so they are reached only through
``Platform.call`` (PDP check, discovery via ``GET /operations``, the generic
``POST /projects/{p}/ops/{op}`` route). Phase 1 of the integration moves this file into
``sip/semantic_intelligence`` unchanged apart from the imports.

All four are reads (``crudv="R"``) under the plain ``rdf`` capability, the same one
``validation.pending`` and ``browse.metrics`` declare: a view spans many resources, so a
per-resource role (``rdf(%resource_role%)``) would not describe it, and resolving one
would materialise the staged ontology on every call.
"""

from __future__ import annotations

from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS, SKOS

from . import _paths  # noqa: F401
from semantic_intelligence.platform import _cq_graph, _icv_ctx, _iri, operation
from semantic_intelligence.quality import cq as cqmod
from semantic_intelligence.quality import icv
from semantic_intelligence.owl.rendering import local_name

from .contract import to_playground
from .index import DEFAULT_KINDS, EDGE_KINDS, OntologyIndex, _text
from .neighbourhood import neighbourhood
from .overlays import OverlayInputs, annotate, inferred_edges
from .svg import render_svg

OVERLAYS = ("staged", "inferred", "findings", "cq")
_CACHE: dict[str, dict] = {}


def _key(ctx) -> tuple:
    return (ctx.tracker._revision, tuple(c.id for c in ctx.tracker.pending()),
            id(ctx.reasoner.last), id(ctx.preview))


def bundle(ctx) -> dict:
    """Indexes and overlay inputs for the project's current revision (cached)."""
    key = _key(ctx)
    b = _CACHE.get(ctx.name)
    if b is not None and b["key"] == key:
        return b
    langs = tuple(ctx.config.languages) + ("",)
    stable, staged = ctx.ontology(staged=False), ctx.ontology(staged=True)
    differs = bool(ctx.tracker.pending()) and (len(staged - stable) or len(stable - staged))
    if differs:
        union = Graph()
        for g in (stable, staged):
            for t in g:
                union.add(t)
        b = {"index": OntologyIndex(union, langs), "stable": OntologyIndex(stable, langs),
             "staged": OntologyIndex(staged, langs)}
    else:
        b = {"index": OntologyIndex(staged, langs), "stable": None, "staged": None}
    for i, _, t in ctx.kg(staged=True).triples((None, RDF.type, None)):   # ABox is in kg
        n = b["index"].nodes.get(str(t))
        if n is not None and isinstance(i, URIRef):
            n.instances += 1
    b["key"] = key
    _CACHE[ctx.name] = b
    return b


def _findings(ctx, b) -> list[dict]:
    if "findings" not in b:
        b["findings"] = [f.__dict__ for f in icv.run_checks(_icv_ctx(ctx))]
    return b["findings"]


def _cqs(ctx, b) -> list[dict]:
    if "cqs" not in b:
        qs = cqmod.CompetencyQuestion.from_graph(ctx.tracker.view(ctx.layout.cq, staged=True))
        stable_g, staged_g = _cq_graph(ctx, False), _cq_graph(ctx, True)
        for t in ctx.kg(staged=True):
            staged_g.add(t)
        out = []
        for q in qs:
            a, s = cqmod.run_cq(q, stable_g), cqmod.run_cq(q, staged_g)
            out.append({"id": q.id, "question": q.question, "priority": q.priority,
                        "passed": a.passed, "passedStaged": s.passed, "detail": a.detail,
                        "terms": sorted(str(t) for t in cqmod.terms(q))})
        b["cqs"] = out
    return b["cqs"]


def _inputs(ctx, b, overlays) -> OverlayInputs:
    inp = OverlayInputs()
    if "staged" in overlays and b["stable"] is not None:
        inp.stable, inp.staged = b["stable"], b["staged"]
        inp.pending = [{"id": c.id, "operation": c.operation, "principal": c.principal,
                        "machine": c.is_machine,
                        "additions": [[str(x) for x in q[:3]] for q in c.additions],
                        "removals": [[str(x) for x in q[:3]] for q in c.removals]}
                       for c in ctx.tracker.pending()]
    if "inferred" in overlays:
        c, src = (ctx.preview, "preview") if ctx.preview is not None else \
            (ctx.reasoner.last, "stable")
        if c is not None:
            inp.inferred, inp.inferred_source = c.inferred, src
            inp.unsatisfiable = {str(u) for u in c.unsatisfiable}
    if "findings" in overlays:
        inp.findings = _findings(ctx, b)
    if "cq" in overlays:
        inp.cqs = _cqs(ctx, b)
    return inp


def _check(kinds, overlays):
    kinds = tuple(kinds or DEFAULT_KINDS)
    bad = [k for k in kinds if k not in EDGE_KINDS]
    if bad:
        raise ValueError(f"unknown edge kinds {bad}; use {list(EDGE_KINDS)}")
    overlays = tuple(OVERLAYS if overlays is None else overlays)
    bad = [o for o in overlays if o not in OVERLAYS]
    if bad:
        raise ValueError(f"unknown overlays {bad}; use {list(OVERLAYS)}")
    return kinds, overlays


def build_view(ctx, seed: str, hops: int = 2, cap: int = 40, kinds=None,
               hub_limit: int = 25, expand=None, overlays=None) -> dict:
    kinds, overlays = _check(kinds, overlays)
    if not 1 <= cap <= 2000:
        raise ValueError("cap must be between 1 and 2000")
    b = bundle(ctx)
    ix = b["index"]
    inp = _inputs(ctx, b, overlays)
    extra = []
    if inp.inferred is not None:
        cache_key = ("inferred", inp.inferred_source, id(inp.inferred))
        if cache_key not in b:
            b[cache_key] = inferred_edges(ix, inp.inferred)
        extra = b[cache_key]
    view = neighbourhood(ix, str(_iri(ctx, seed)), hops=hops, cap=cap, kinds=kinds,
                         hub_limit=hub_limit,
                         expand=[str(_iri(ctx, e)) for e in (expand or [])], extra=extra)
    out = to_playground(view, ix, annotate(view, ix, inp))
    out["sip"]["overlays"] = list(overlays)
    if "cq" in overlays:
        out["sip"]["cqs"] = [q for q in inp.cqs
                             if any(t in view.nodes for t in q["terms"])]
    return out


@operation("viz.neighbourhood", capability="rdf", crudv="R", stage="model")
def neighbourhood_op(self, ctx, seed: str, hops: int = 2, cap: int = 40,
                     kinds: list[str] | None = None, hub_limit: int = 25,
                     expand: list[str] | None = None,
                     overlays: list[str] | None = None) -> dict:
    """Search-first ego view of a class or concept, capped, with review-gate overlays."""
    return build_view(ctx, seed, hops, cap, kinds, hub_limit, expand, overlays)


@operation("viz.search", capability="rdf", crudv="R", stage="model")
def search_op(self, ctx, text: str, limit: int = 20) -> list[dict]:
    """Classes and concepts whose label or local name contains the text (view seeds)."""
    ix = bundle(ctx)["index"]
    return [{"iri": n.iri, "label": n.label, "kind": n.kind, "module": n.module,
             "degree": len(ix.adj.get(n.iri, ())), "badges": len(n.complex)}
            for n in ix.search(text, limit)]


@operation("viz.individuals", capability="rdf(individual)", crudv="R", stage="populate")
def individuals_op(self, ctx, cls: str, include_subclasses: bool = False, limit: int = 50,
                   offset: int = 0) -> dict:
    """Individuals typed with a class (optionally its subclasses), paged."""
    ix = bundle(ctx)["index"]
    c = str(_iri(ctx, cls))
    classes = {c}
    if include_subclasses:
        todo = [c]
        while todo:
            x = todo.pop()
            for m, e in ix.adj.get(x, ()):
                if e.kind == "subClassOf" and e.target == x and m not in classes:
                    classes.add(m)
                    todo.append(m)
    g = ctx.kg(staged=True)
    for t in ctx.ontology(staged=True).triples((None, RDF.type, None)):
        g.add(t)
    found = sorted({str(i) for k in classes for i in g.subjects(RDF.type, URIRef(k))
                    if isinstance(i, URIRef)})
    page = found[offset:offset + max(0, min(limit, 500))]
    return {"cls": c, "classes": len(classes), "total": len(found), "offset": offset,
            "items": [{"iri": i, "label": _text(g, URIRef(i), (RDFS.label, SKOS.prefLabel))
                       or local_name(i),
                       "types": sorted(str(t) for t in g.objects(URIRef(i), RDF.type))}
                      for i in page]}


@operation("viz.exportSVG", capability="rdf", crudv="R", stage="publish")
def export_svg_op(self, ctx, seed: str, hops: int = 1, cap: int = 40,
                  kinds: list[str] | None = None, hub_limit: int = 25,
                  overlays: list[str] | None = None, title: str | None = None) -> str:
    """A static, deterministic layered SVG of a view (for PRs, release notes, RESULTS.md)."""
    return render_svg(build_view(ctx, seed, hops, cap, kinds, hub_limit, None, overlays),
                      title=title)


@operation("viz.stats", capability="rdf", crudv="R", stage="model")
def stats_op(self, ctx) -> dict:
    """Size of the view index (nodes, typed edges, badged nodes, maximum degree)."""
    b = bundle(ctx)
    return {**b["index"].stats(), "stagedDifferences": b["stable"] is not None}
