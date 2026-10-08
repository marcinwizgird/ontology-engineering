"""Integrity Constraint Validation — Semantic Turkey's ``ICV`` service (27 checks,
11 fixes) plus the logical checks Protégé surfaces through its reasoner.

Each :class:`Check` has an id that matches the ST operation it ports
(``listDanglingConcepts`` …), the models it applies to (the client's
preconditions in ``icvListComponent.ts``), a severity, and optionally a *fix*
that returns a :class:`ChangeSet`. Fixes are change sets on purpose: the quality
agent proposes them, they are staged, a validator accepts them.

Not ported: ``listConsistencyViolations`` and ``explain`` (GraphDB-only rule
engine — replaced by ``owl.inconsistent`` / ``owl.unsatisfiable`` over the
reasoner manager, with justifications), ``listBrokenAlignments`` and the HTTP
part of ``listBrokenDefinitions`` (need the metadata registry and outbound HTTP;
the local part is ported).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from ..core.changes import ChangeSet
from ..core.namespaces import SKOSXL
from ..owl.hierarchy import ClassHierarchy

RFC3986 = re.compile(
    r"^([a-z0-9+.-]+):(?://(?:((?:[a-z0-9-._~!$&'()*+,;=:]|%[0-9A-F]{2})*)@)?((?:[a-z0-9-._~!$&'()*+,;=]"
    r"|%[0-9A-F]{2})*)(?::(\d*))?(/(?:[a-z0-9-._~!$&'()*+,;=:@/]|%[0-9A-F]{2})*)?|(/?(?:[a-z0-9-._~!$&'"
    r"()*+,;=:@]|%[0-9A-F]{2})+(?:[a-z0-9-._~!$&'()*+,;=:@/]|%[0-9A-F]{2})*)?)(?:\?((?:[a-z0-9-._~!$&'()"
    r"*+,;=:/?@]|%[0-9A-F]{2})*))?(?:#((?:[a-z0-9-._~!$&'()*+,;=:/?@]|%[0-9A-F]{2})*))?$", re.I)


@dataclass
class Finding:
    check: str
    resource: str
    message: str
    severity: str
    details: dict = field(default_factory=dict)


@dataclass
class Context:
    graph: Graph
    model: str = "owl"                 # owl | skos | rdfs | ontolex
    lexicalization: str = "rdfs"       # rdfs | skos | skosxl | ontolex
    languages: tuple[str, ...] = ("en",)
    target_graph: URIRef | None = None
    classification: object | None = None   # reasoning.reasoner.Classification

    # helpers
    def concepts(self) -> set[URIRef]:
        return {c for c in self.graph.subjects(RDF.type, SKOS.Concept) if isinstance(c, URIRef)}

    def schemes(self) -> set[URIRef]:
        return {c for c in self.graph.subjects(RDF.type, SKOS.ConceptScheme)
                if isinstance(c, URIRef)}

    def broader(self, c) -> set:
        g = self.graph
        return set(g.objects(c, SKOS.broader)) | set(g.subjects(SKOS.narrower, c))

    def in_scheme(self, c) -> set:
        g = self.graph
        return set(g.objects(c, SKOS.inScheme)) | set(g.objects(c, SKOS.topConceptOf)) \
            | set(g.subjects(SKOS.hasTopConcept, c))

    def is_top(self, c, s) -> bool:
        return (c, SKOS.topConceptOf, s) in self.graph or (s, SKOS.hasTopConcept, c) in self.graph

    def lex_resources(self) -> set[URIRef]:
        g = self.graph
        types = {"skos": (SKOS.Concept, SKOS.ConceptScheme, SKOS.Collection,
                          SKOS.OrderedCollection),
                 "skosxl": (SKOS.Concept, SKOS.ConceptScheme, SKOS.Collection,
                            SKOS.OrderedCollection)}.get(
            self.lexicalization, (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty,
                                  OWL.NamedIndividual))
        return {r for t in types for r in g.subjects(RDF.type, t) if isinstance(r, URIRef)}

    def labels(self, r, kind="pref") -> list[tuple[Literal, object]]:
        """(literal, xlabel-or-None) pairs for the project's lexicalization model."""
        g = self.graph
        if self.lexicalization == "skosxl":
            p = SKOSXL[kind + "Label"]
            return [(lf, xl) for xl in g.objects(r, p) for lf in g.objects(xl, SKOSXL.literalForm)]
        if self.lexicalization == "skos":
            return [(o, None) for o in g.objects(r, SKOS[kind + "Label"]) if isinstance(o, Literal)]
        return [(o, None) for o in g.objects(r, RDFS.label)] if kind == "pref" else []


@dataclass
class Check:
    id: str
    name: str
    group: str
    severity: str
    models: tuple[str, ...]
    run: Callable[[Context], list[Finding]]
    fix: Callable[[Context], ChangeSet] | None = None
    #: capability the fix needs — ST guards each fix operation separately
    #: (e.g. ``setAllDanglingAsTopConcept`` = ``rdf(concept, taxonomy)`` C).
    fix_capability: tuple[str, str] = ("rdf(resource)", "U")
    lexicalizations: tuple[str, ...] = ()
    source: str = "SemanticTurkey ICV"

    def applies(self, ctx: Context) -> bool:
        if self.models and ctx.model not in self.models:
            return False
        return not self.lexicalizations or ctx.lexicalization in self.lexicalizations


REGISTRY: dict[str, Check] = {}


def check(id, name, group, severity="major", models=(), lex=(), source="SemanticTurkey ICV"):
    def deco(fn):
        REGISTRY[id] = Check(id, name, group, severity, tuple(models), fn,
                             lexicalizations=tuple(lex), source=source)
        return fn
    return deco


def fix(id, capability: str = "rdf(resource)", crudv: str = "U"):
    def deco(fn):
        REGISTRY[id].fix = fn
        REGISTRY[id].fix_capability = (capability, crudv)
        return fn
    return deco


def _f(cid, r, msg, **d) -> Finding:
    return Finding(cid, str(r), msg, REGISTRY[cid].severity, d)

# ---------------------------- SKOS structure ------------------------------- #


def _dangling(ctx: Context) -> list[tuple[URIRef, URIRef]]:
    out = []
    for c in ctx.concepts():
        for s in ctx.graph.objects(c, SKOS.inScheme):
            if ctx.is_top(c, s):
                continue
            if any(s in ctx.in_scheme(b) for b in ctx.broader(c)):
                continue
            out.append((c, s))
    return sorted(out)


@check("listDanglingConcepts", "Dangling concepts", "structural", "major", ("skos",))
def _c1(ctx):
    return [_f("listDanglingConcepts", c, f"in scheme {s} but neither top concept nor "
               f"narrower of a concept in it", scheme=str(s)) for c, s in _dangling(ctx)]


@fix("listDanglingConcepts", "rdf(concept, taxonomy)", "C")
def _x1(ctx):
    cs = ChangeSet("icv.setAllDanglingAsTopConcept", {}, ctx.target_graph)
    for c, s in _dangling(ctx):
        cs.add(c, SKOS.topConceptOf, s)
    return cs


@check("listConceptSchemesWithNoTopConcept", "Omitted top concept", "structural", "major",
       ("skos",))
def _c3(ctx):
    return [_f("listConceptSchemesWithNoTopConcept", s, "scheme has no top concept")
            for s in sorted(ctx.schemes())
            if not ((s, SKOS.hasTopConcept, None) in ctx.graph
                    or (None, SKOS.topConceptOf, s) in ctx.graph)]


@check("listConceptsWithNoScheme", "Concepts with no scheme", "structural", "minor", ("skos",))
def _c4(ctx):
    return [_f("listConceptsWithNoScheme", c, "concept is in no scheme")
            for c in sorted(ctx.concepts()) if not ctx.in_scheme(c)]


@fix("listConceptsWithNoScheme", "rdf(concept, scheme)", "C")
def _x4(ctx):
    cs = ChangeSet("icv.addAllConceptsToScheme", {}, ctx.target_graph)
    schemes = sorted(ctx.schemes())
    if len(schemes) == 1:
        for c in ctx.concepts():
            if not ctx.in_scheme(c):
                cs.add(c, SKOS.inScheme, schemes[0])
    return cs


def _tops_with_broader(ctx):
    out = []
    for c in ctx.concepts():
        for s in set(ctx.graph.objects(c, SKOS.topConceptOf)) | set(
                ctx.graph.subjects(SKOS.hasTopConcept, c)):
            for b in ctx.broader(c):
                if s in ctx.in_scheme(b):
                    out.append((c, s, b))
    return sorted(out)


@check("listTopConceptsWithBroader", "Top concept with broader", "structural", "major",
       ("skos",))
def _c5(ctx):
    return [_f("listTopConceptsWithBroader", c, f"top concept of {s} has broader {b} in the "
               "same scheme", scheme=str(s), broader=str(b)) for c, s, b in _tops_with_broader(ctx)]


@fix("listTopConceptsWithBroader", "rdf(concept, taxonomy)", "D")
def _x5(ctx):
    cs = ChangeSet("icv.removeAllAsTopConceptsWithBroader", {}, ctx.target_graph)
    for c, s, _ in _tops_with_broader(ctx):
        if (c, SKOS.topConceptOf, s) in ctx.graph:
            cs.remove(c, SKOS.topConceptOf, s)
        if (s, SKOS.hasTopConcept, c) in ctx.graph:
            cs.remove(s, SKOS.hasTopConcept, c)
    return cs


def _ancestors(ctx, c) -> set:
    out, stack = set(), [c]
    while stack:
        n = stack.pop()
        for b in ctx.broader(n):
            if b not in out:
                out.add(b)
                stack.append(b)
    return out


@check("listConceptsRelatedDisjoint", "Related and hierarchical (SKOS S27)", "structural",
       "major", ("skos",))
def _c6(ctx):
    out = []
    for a, b in ctx.graph.subject_objects(SKOS.related):
        if b in _ancestors(ctx, a) or a in _ancestors(ctx, b):
            out.append(_f("listConceptsRelatedDisjoint", a, f"related to its hierarchical "
                          f"relative {b}", other=str(b)))
    return out


@check("listConceptsExactMatchDisjoint", "exactMatch with broad/relatedMatch", "structural",
       "major", ("skos",))
def _c7(ctx):
    g, out = ctx.graph, []
    for a, b in g.subject_objects(SKOS.exactMatch):
        for p in (SKOS.broadMatch, SKOS.relatedMatch):
            if (a, p, b) in g or (b, p, a) in g:
                out.append(_f("listConceptsExactMatchDisjoint", a,
                              f"exactMatch {b} and also {p.split('#')[-1]}", other=str(b)))
    return out


def _redundant(ctx):
    out = []
    for c in ctx.concepts():
        direct = ctx.broader(c)
        for b in direct:
            others = _ancestors(ctx, b)
            for o in direct:
                if o != b and o in others:
                    out.append((c, o))
    return sorted(set(out))


@check("listConceptsHierarchicalRedundancies", "Hierarchical redundancy", "structural", "minor",
       ("skos",))
def _c8(ctx):
    return [_f("listConceptsHierarchicalRedundancies", c, f"broader {o} is implied by another "
               "broader", broader=str(o)) for c, o in _redundant(ctx)]


@fix("listConceptsHierarchicalRedundancies", "rdf(concept, taxonomy)", "D")
def _x8(ctx):
    cs = ChangeSet("icv.removeAllHierarchicalRedundancy", {}, ctx.target_graph)
    for c, o in _redundant(ctx):
        if (c, SKOS.broader, o) in ctx.graph:
            cs.remove(c, SKOS.broader, o)
        if (o, SKOS.narrower, c) in ctx.graph:
            cs.remove(o, SKOS.narrower, c)
    return cs


@check("listConceptsHierarchicalCycles", "Hierarchical cycles", "structural", "blocker",
       ("skos",))
def _c9(ctx):
    seen, out = set(), []
    for c in sorted(ctx.concepts()):
        if c in seen:
            continue
        if c in _ancestors(ctx, c):
            cyc = sorted({x for x in _ancestors(ctx, c) if c in _ancestors(ctx, x)} | {c})
            seen.update(cyc)
            out.append(_f("listConceptsHierarchicalCycles", c, "broader cycle",
                          cycle=[str(x) for x in cyc]))
    return out

# ------------------------------- labels ------------------------------------ #


@check("listResourcesWithNoSKOSPrefLabel", "No skos:prefLabel", "label", "major", (),
       ("skos",))
def _c12(ctx):
    return [_f("listResourcesWithNoSKOSPrefLabel", r, "no skos:prefLabel")
            for r in sorted(ctx.lex_resources()) if not ctx.labels(r, "pref")]


@check("listResourcesWithNoSKOSXLPrefLabel", "No skosxl:prefLabel", "label", "major", (),
       ("skosxl",))
def _c13(ctx):
    return [_f("listResourcesWithNoSKOSXLPrefLabel", r, "no skosxl:prefLabel")
            for r in sorted(ctx.lex_resources()) if not ctx.labels(r, "pref")]


@check("listResourcesNoLexicalization", "No mandatory label", "label", "major")
def _c14(ctx):
    out = []
    for r in sorted(ctx.lex_resources()):
        have = {(l.language or "").lower() for l, _ in ctx.labels(r, "pref")}
        missing = [l for l in ctx.languages if l.lower() not in have]
        if missing:
            out.append(_f("listResourcesNoLexicalization", r,
                          f"no label in {','.join(missing)}", missingLang=missing))
    return out


@check("listResourcesWithAltNoPrefLabel", "Only altLabel", "label", "minor", (),
       ("skos", "skosxl"))
def _c15(ctx):
    out = []
    for r in sorted(ctx.lex_resources()):
        alt = {(l.language or "") for l, _ in ctx.labels(r, "alt")}
        pref = {(l.language or "") for l, _ in ctx.labels(r, "pref")}
        if alt - pref:
            out.append(_f("listResourcesWithAltNoPrefLabel", r, "altLabel without prefLabel in "
                          + ",".join(sorted(alt - pref)), missingLang=sorted(alt - pref)))
    return out


@check("listResourcesWithNoLanguageTagForLabel", "Label without language tag", "label", "minor")
def _c16(ctx):
    out = []
    for r in sorted(ctx.lex_resources()):
        for kind in ("pref", "alt", "hidden"):
            for l, _ in ctx.labels(r, kind):
                if not l.language:
                    out.append(_f("listResourcesWithNoLanguageTagForLabel", r,
                                  f"{kind} label {str(l)!r} has no language tag"))
    return out


@check("listResourcesWithOverlappedLabels", "Overlapped labels", "label", "minor")
def _c17(ctx):
    out = []
    for r in sorted(ctx.lex_resources()):
        pref = {l for l, _ in ctx.labels(r, "pref")}
        for kind in ("alt", "hidden"):
            for l, _ in ctx.labels(r, kind):
                if l in pref:
                    out.append(_f("listResourcesWithOverlappedLabels", r,
                                  f"{str(l)!r} is both pref and {kind} label"))
    return out


@check("listResourcesWithSameLabels", "Conflictual labels", "label", "major")
def _c18(ctx):
    by: dict = {}
    for r in ctx.lex_resources():
        for l, _ in ctx.labels(r, "pref"):
            by.setdefault(l, set()).add(r)
    out = []
    for l, rs in sorted(by.items(), key=lambda kv: str(kv[0])):
        if len(rs) < 2:
            continue
        rs_sorted = sorted(rs)
        if ctx.model == "skos" or ctx.lexicalization in ("skos", "skosxl"):
            # concepts clash only when they share a scheme
            pairs = [(a, b) for i, a in enumerate(rs_sorted) for b in rs_sorted[i + 1:]
                     if not ctx.in_scheme(a) or ctx.in_scheme(a) & ctx.in_scheme(b)]
            if not pairs:
                continue
        out.append(_f("listResourcesWithSameLabels", rs_sorted[0],
                      f"prefLabel {str(l)!r}@{l.language} shared by {len(rs)} resources",
                      resources=[str(x) for x in rs_sorted]))
    return out


def _spaced(ctx):
    out = []
    for r in ctx.lex_resources():
        for kind in ("pref", "alt", "hidden"):
            for l, xl in ctx.labels(r, kind):
                s = str(l)
                if s != s.strip() or "  " in s:
                    out.append((r, kind, l, xl))
    return sorted(out, key=lambda t: (str(t[0]), t[1], str(t[2])))


@check("listResourcesWithExtraSpacesInLabel", "Extra spaces in label", "label", "minor")
def _c19(ctx):
    return [_f("listResourcesWithExtraSpacesInLabel", r, f"{kind} label {str(l)!r} has "
               "leading/trailing/double spaces") for r, kind, l, _ in _spaced(ctx)]


@fix("listResourcesWithExtraSpacesInLabel", "rdf(resource, lexicalization)", "U")
def _x19(ctx):
    cs = ChangeSet("icv.trimLabels", {}, ctx.target_graph)
    for r, kind, l, xl in _spaced(ctx):
        fixed = Literal(re.sub(r"\s+", " ", str(l)).strip(), lang=l.language, datatype=l.datatype)
        if xl is not None:
            cs.remove(xl, SKOSXL.literalForm, l).add(xl, SKOSXL.literalForm, fixed)
        else:
            p = RDFS.label if ctx.lexicalization == "rdfs" else SKOS[kind + "Label"]
            cs.remove(r, p, l).add(r, p, fixed)
    return cs


@check("listResourcesWithMorePrefLabelSameLang", "Multiple prefLabel", "label", "major", (),
       ("skos", "skosxl"))
def _c20(ctx):
    out = []
    for r in sorted(ctx.lex_resources()):
        langs: dict = {}
        for l, _ in ctx.labels(r, "pref"):
            langs.setdefault((l.language or "").lower(), set()).add(str(l))
        dup = sorted(k for k, v in langs.items() if len(v) > 1)
        if dup:
            out.append(_f("listResourcesWithMorePrefLabelSameLang", r,
                          f"several prefLabels in {','.join(dup)}", duplicateLang=dup))
    return out


def _dangling_xl(ctx):
    g = ctx.graph
    return sorted(x for x in g.subjects(RDF.type, SKOSXL.Label)
                  if not any((None, p, x) in g for p in (SKOSXL.prefLabel, SKOSXL.altLabel,
                                                         SKOSXL.hiddenLabel)))


@check("listDanglingXLabels", "Dangling xLabels", "label", "minor", (), ("skosxl",))
def _c21(ctx):
    return [_f("listDanglingXLabels", x, "skosxl:Label not attached to any resource")
            for x in _dangling_xl(ctx)]


@fix("listDanglingXLabels", "rdf(xLabel)", "D")
def _x21(ctx):
    cs = ChangeSet("icv.deleteAllDanglingXLabel", {}, ctx.target_graph)
    for x in _dangling_xl(ctx):
        cs.remove_all(ctx.graph.triples((x, None, None)))
        cs.remove_all(ctx.graph.triples((None, None, x)))
    return cs


@check("listResourcesNoDef", "No definition", "label", "minor", ("skos",))
def _c22(ctx):
    out = []
    for c in sorted(ctx.concepts()):
        have = {(o.language or "").lower() for o in ctx.graph.objects(c, SKOS.definition)
                if isinstance(o, Literal)}
        for n in ctx.graph.objects(c, SKOS.definition):
            for v in ctx.graph.objects(n, RDF.value):
                if isinstance(v, Literal):
                    have.add((v.language or "").lower())
        missing = [l for l in ctx.languages if l.lower() not in have]
        if missing:
            out.append(_f("listResourcesNoDef", c, f"no skos:definition in {','.join(missing)}",
                          missingLang=missing))
    return out

# ------------------------------- IRIs -------------------------------------- #


@check("listLocalInvalidURIs", "Invalid IRIs", "iri", "major")
def _c26(ctx):
    out = []
    for s in sorted({s for s in ctx.graph.subjects(RDF.type, None) if isinstance(s, URIRef)}):
        if " " in str(s) or not RFC3986.match(str(s)):
            out.append(_f("listLocalInvalidURIs", s, "not a valid RFC 3986 IRI"))
    return out


@check("listResourcesURIWithSpace", "IRIs with spaces", "iri", "major")
def _c27(ctx):
    found = {t for tr in ctx.graph for t in tr if isinstance(t, URIRef) and " " in str(t)}
    return [_f("listResourcesURIWithSpace", r, "IRI contains a space") for r in sorted(found)]


@check("listBrokenDefinitions", "Broken definitions (local)", "iri", "minor")
def _c25(ctx):
    g, out = ctx.graph, []
    note_props = {SKOS.note, SKOS.definition, SKOS.scopeNote, SKOS.example, SKOS.historyNote,
                  SKOS.editorialNote, SKOS.changeNote}
    for p in note_props:
        for s, o in g.subject_objects(p):
            if isinstance(o, URIRef) and (o, None, None) not in g:
                out.append(_f("listBrokenDefinitions", s, f"{p.split('#')[-1]} points to {o}, "
                              "which has no description", target=str(o)))
    return out


@check("listAlignedNamespaces", "Aligned namespaces", "mapping", "info")
def _c23(ctx):
    g = ctx.graph
    props = {SKOS.exactMatch, SKOS.closeMatch, SKOS.broadMatch, SKOS.narrowMatch,
             SKOS.relatedMatch, OWL.equivalentClass, OWL.equivalentProperty, OWL.sameAs}
    counts: dict[str, int] = {}
    for p in props:
        for _, o in g.subject_objects(p):
            if isinstance(o, URIRef):
                ns = re.sub(r"[^#/]+$", "", str(o))
                counts[ns] = counts.get(ns, 0) + 1
    return [_f("listAlignedNamespaces", ns, f"{n} mapping(s)", count=n)
            for ns, n in sorted(counts.items())]

# ---------------------------- OWL / logical -------------------------------- #


@check("owl.classCycles", "Subclass cycles", "logical", "major", ("owl", "rdfs"),
       source="Protege AssertedClassHierarchyProvider")
def _o1(ctx):
    return [_f("owl.classCycles", cyc[0], "asserted subclass cycle: classes are equivalent",
               cycle=[str(x) for x in cyc]) for cyc in ClassHierarchy(ctx.graph).cycles()]


@check("owl.unsatisfiable", "Unsatisfiable classes", "logical", "blocker", ("owl",),
       source="Protege reasoner (unsatisfiable classes)")
def _o2(ctx):
    c = ctx.classification
    if c is None:
        return []
    return [_f("owl.unsatisfiable", u, f"unsatisfiable under {c.profile}", profile=c.profile)
            for u in c.unsatisfiable]


@check("owl.inconsistent", "Inconsistent ontology", "logical", "blocker", ("owl",),
       source="Protege ReasonerStatus.INCONSISTENT")
def _o3(ctx):
    c = ctx.classification
    if c is None or c.consistent:
        return []
    return [_f("owl.inconsistent", "ontology", m[:300], profile=c.profile) for m in c.messages]


@check("owl.undeclaredEntities", "Undeclared entities", "logical", "minor", ("owl",),
       source="OWL 2 DL typing constraints")
def _o4(ctx):
    g = ctx.graph
    declared = {s for s in g.subjects(RDF.type, None) if isinstance(s, URIRef)}
    used = set()
    for p in (RDFS.subClassOf, OWL.equivalentClass, OWL.disjointWith, RDFS.domain, RDFS.range,
              OWL.someValuesFrom, OWL.allValuesFrom, OWL.onClass, OWL.onProperty):
        for o in g.objects(None, p):
            if isinstance(o, URIRef) and not str(o).startswith(
                    ("http://www.w3.org/2001/XMLSchema#", str(OWL), str(RDFS), str(RDF))):
                used.add(o)
    return [_f("owl.undeclaredEntities", u, "used but never declared")
            for u in sorted(used - declared)]


@check("owl.missingLabel", "Entity without label", "label", "minor", ("owl", "rdfs"),
       source="OOPS! P08 (missing annotations)")
def _o5(ctx):
    g = ctx.graph
    out = []
    for t in (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty):
        for s in g.subjects(RDF.type, t):
            if isinstance(s, URIRef) and (s, RDFS.label, None) not in g \
                    and (s, SKOS.prefLabel, None) not in g:
                out.append(_f("owl.missingLabel", s, "no rdfs:label / skos:prefLabel"))
    return sorted(out, key=lambda f: f.resource)


SEVERITY_ORDER = {"blocker": 0, "major": 1, "minor": 2, "info": 3}


def run_checks(ctx: Context, ids: Iterable[str] | None = None) -> list[Finding]:
    out = []
    for cid, chk in REGISTRY.items():
        if ids is not None and cid not in ids:
            continue
        if ids is None and not chk.applies(ctx):
            continue
        out.extend(chk.run(ctx))
    return sorted(out, key=lambda f: (SEVERITY_ORDER[f.severity], f.check, f.resource))


def summary(findings: list[Finding]) -> dict[str, int]:
    out = {k: 0 for k in SEVERITY_ORDER}
    for f in findings:
        out[f.severity] += 1
    return out
