"""Description frames (Protégé) and the resource view (Semantic Turkey).

Two presentations of "everything about one resource", kept side by side because
each tool got something right the other did not:

**Protégé frames** (``OWLClassDescriptionFrame`` & co.) are *axiom*-oriented and
render class expressions in Manchester syntax. The class frame has eight
sections — Equivalent To, SubClass Of, General class axioms, SubClass Of
(Anonymous Ancestor), Instances, Target for Key, Disjoint With, Disjoint Union
Of; object properties have seven (here: Equivalent To, SubProperty Of, Inverse Of,
Domains, Ranges, Disjoint With, SuperProperty Of (Chain)) plus characteristics.

**Semantic Turkey's resource view** is *triple*-oriented, has 29 sections chosen
by a per-role template, consumes each statement once (``properties`` is last and
takes the rest), follows sub-properties (so ``skos:definition`` lands in
``notes``), and tags every value with its **tripleScope** — ``local``,
``staged``, ``del_staged``, ``imported`` or ``inferred`` — which is what lets the
UI show a proposal green-italic and a staged deletion struck through.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from ..core.namespaces import ONTOLEX, SKOSXL
from .manchester import render, render_literal
from .model import (Axiom, Inverse, UnsupportedConstruct, axioms, parse_ce, parse_prop)
from .rendering import ShortFormProvider, entity_role

# --------------------------------------------------------------------------- #
# Protégé frames
# --------------------------------------------------------------------------- #

CLASS_FRAME_SECTIONS = ("Equivalent To", "SubClass Of", "General class axioms",
                        "SubClass Of (Anonymous Ancestor)", "Instances", "Target for Key",
                        "Disjoint With", "Disjoint Union Of")


def class_frame(g: Graph, c: URIRef, sfp: ShortFormProvider,
                inferred: Graph | None = None) -> dict[str, list[dict]]:
    """Rows per section; each row ``{text, inferred}``. Inferred rows (Protégé's
    yellow rows) come from *inferred* when supplied."""
    out: dict[str, list[dict]] = {s: [] for s in CLASS_FRAME_SECTIONS}
    axs = list(axioms(g, include_annotations=False, include_declarations=False))

    def row(text, inf=False):
        return {"text": text, "inferred": inf}
    named_supers = []
    for a in axs:
        k, args = a.kind, a.args
        if k == "EquivalentClasses" and c in args:
            for x in args:
                if x != c:
                    out["Equivalent To"].append(row(render(x, sfp)))
        elif k == "SubClassOf" and args[0] == c:
            out["SubClass Of"].append(row(render(args[1], sfp)))
            if isinstance(args[1], URIRef):
                named_supers.append(args[1])
        elif k == "SubClassOf" and not isinstance(args[0], URIRef) and c in _sig(args[0]):
            out["General class axioms"].append(
                row(f"{render(args[0], sfp)} SubClassOf {render(args[1], sfp)}"))
        elif k == "ClassAssertion" and args[0] == c:
            out["Instances"].append(row(sfp.rendering(args[1])))
        elif k == "HasKey" and args[0] == c:
            out["Target for Key"].append(row(", ".join(sfp.rendering(p) for p in args[1])))
        elif k == "DisjointClasses" and c in args:
            out["Disjoint With"].append(row(", ".join(render(x, sfp) for x in args if x != c)))
        elif k == "DisjointUnion" and args[0] == c:
            out["Disjoint Union Of"].append(row(", ".join(render(x, sfp) for x in args[1])))
    # anonymous ancestors: restrictions inherited from named ancestors
    seen, stack = {c}, list(named_supers)
    while stack:
        a_cls = stack.pop()
        if a_cls in seen:
            continue
        seen.add(a_cls)
        for a in axs:
            if a.kind == "SubClassOf" and a.args[0] == a_cls:
                if isinstance(a.args[1], URIRef):
                    stack.append(a.args[1])
                else:
                    out["SubClass Of (Anonymous Ancestor)"].append(row(render(a.args[1], sfp)))
    if inferred is not None:
        asserted = {r["text"] for r in out["SubClass Of"]}
        for o in inferred.objects(c, RDFS.subClassOf):
            if isinstance(o, URIRef) and o not in (c, OWL.Thing):
                t = sfp.rendering(o)
                if t not in asserted:
                    out["SubClass Of"].append(row(t, True))
        for i in inferred.subjects(RDF.type, c):
            if isinstance(i, URIRef):
                out["Instances"].append(row(sfp.rendering(i), True))
    return out


def property_frame(g: Graph, p: URIRef, sfp: ShortFormProvider) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {k: [] for k in (
        "Characteristics", "Equivalent To", "SubProperty Of", "Inverse Of", "Domains",
        "Ranges", "Disjoint With", "SuperProperty Of (Chain)")}
    for t, name in ((OWL.FunctionalProperty, "Functional"),
                    (OWL.InverseFunctionalProperty, "Inverse functional"),
                    (OWL.TransitiveProperty, "Transitive"), (OWL.SymmetricProperty, "Symmetric"),
                    (OWL.AsymmetricProperty, "Asymmetric"), (OWL.ReflexiveProperty, "Reflexive"),
                    (OWL.IrreflexiveProperty, "Irreflexive")):
        if (p, RDF.type, t) in g:
            out["Characteristics"].append(name)
    for o in g.objects(p, OWL.equivalentProperty):
        out["Equivalent To"].append(sfp.rendering(o))
    for o in g.objects(p, RDFS.subPropertyOf):
        out["SubProperty Of"].append(sfp.rendering(o))
    for o in set(g.objects(p, OWL.inverseOf)) | set(g.subjects(OWL.inverseOf, p)):
        if isinstance(o, URIRef):
            out["Inverse Of"].append(sfp.rendering(o))
    for pred, sec in ((RDFS.domain, "Domains"), (RDFS.range, "Ranges")):
        for o in g.objects(p, pred):
            try:
                out[sec].append(render(parse_ce(g, o), sfp) if not isinstance(o, URIRef)
                                else sfp.rendering(o) if not str(o).startswith(
                                    "http://www.w3.org/2001/XMLSchema#") else sfp.prefixed(o))
            except UnsupportedConstruct:
                out[sec].append(str(o))
    for o in g.objects(p, OWL.propertyDisjointWith):
        out["Disjoint With"].append(sfp.rendering(o))
    for a in axioms(g, include_annotations=False, include_declarations=False):
        if a.kind == "SubPropertyChainOf" and a.args[1] == p:
            out["SuperProperty Of (Chain)"].append(" o ".join(
                f"inverse ({sfp.rendering(x.prop)})" if isinstance(x, Inverse)
                else sfp.rendering(x) for x in a.args[0]))
    return out


def _sig(ce) -> set:
    from .model import signature
    return signature(ce)


def render_axiom(ax: Axiom, sfp: ShortFormProvider) -> str:
    """Manchester-style axiom rendering (the justification / usage formatter)."""
    k, a = ax.kind, ax.args
    r = lambda x: render(x, sfp) if not isinstance(x, (tuple, list)) else ", ".join(
        render(y, sfp) for y in x)
    n = sfp.rendering
    table = {
        "SubClassOf": lambda: f"{r(a[0])} SubClassOf {r(a[1])}",
        "EquivalentClasses": lambda: " EquivalentTo ".join(r(x) for x in a),
        "DisjointClasses": lambda: "DisjointClasses: " + ", ".join(r(x) for x in a),
        "DisjointUnion": lambda: f"{n(a[0])} DisjointUnionOf {r(a[1])}",
        "SubPropertyOf": lambda: f"{_p(a[0], sfp)} SubPropertyOf {_p(a[1], sfp)}",
        "SubPropertyChainOf": lambda: " o ".join(_p(x, sfp) for x in a[0])
                                      + f" SubPropertyOf {n(a[1])}",
        "PropertyDomain": lambda: f"{n(a[0])} Domain {r(a[1])}",
        "PropertyRange": lambda: f"{n(a[0])} Range {r(a[1])}",
        "DataPropertyRange": lambda: f"{n(a[0])} Range {r(a[1])}",
        "InverseProperties": lambda: f"{n(a[0])} InverseOf {n(a[1])}",
        "ClassAssertion": lambda: f"{n(a[1])} Type {r(a[0])}",
        "ObjectPropertyAssertion": lambda: f"{n(a[1])} {n(a[0])} {n(a[2])}",
        "DataPropertyAssertion": lambda: f"{n(a[1])} {n(a[0])} {render_literal(a[2], sfp)}",
        "AnnotationAssertion": lambda: f"{n(a[1])} {n(a[0])} " + (
            render_literal(a[2], sfp) if isinstance(a[2], Literal) else n(a[2])),
        "SameIndividual": lambda: "SameIndividual: " + ", ".join(n(x) for x in a),
        "DifferentIndividuals": lambda: "DifferentIndividuals: " + ", ".join(n(x) for x in a),
        "Declaration": lambda: f"{a[0]}: {n(a[1])}",
        "HasKey": lambda: f"{r(a[0])} HasKey {', '.join(n(x) for x in a[1])}",
    }
    if k in table:
        return table[k]()
    return f"{n(a[0])} {k.replace('Property', '')}"


def _p(p, sfp) -> str:
    return f"inverse ({sfp.rendering(p.prop)})" if isinstance(p, Inverse) else sfp.rendering(p)

# --------------------------------------------------------------------------- #
# Semantic Turkey resource view
# --------------------------------------------------------------------------- #

DECOMP = "http://www.w3.org/ns/lemon/decomp#"
SECTIONS: dict[str, tuple[URIRef, ...]] = {
    "types": (RDF.type,),
    "classaxioms": (OWL.equivalentClass, RDFS.subClassOf, OWL.disjointWith, OWL.complementOf,
                    OWL.intersectionOf, OWL.oneOf, OWL.unionOf),
    "datatypeDefinitions": (OWL.equivalentClass,),
    "lexicalizations": (RDFS.label, SKOS.prefLabel, SKOS.altLabel, SKOS.hiddenLabel,
                        SKOSXL.prefLabel, SKOSXL.altLabel, SKOSXL.hiddenLabel, ONTOLEX.isDenotedBy),
    "broaders": (SKOS.broader,),
    "equivalentProperties": (OWL.equivalentProperty,),
    "disjointProperties": (OWL.propertyDisjointWith,),
    "superproperties": (RDFS.subPropertyOf,),
    "subPropertyChains": (OWL.propertyChainAxiom,),
    "facets": (OWL.inverseOf,),
    "domains": (RDFS.domain,),
    "ranges": (RDFS.range,),
    "imports": (OWL.imports,),
    "topconceptof": (SKOS.topConceptOf,),
    "schemes": (SKOS.inScheme,),
    "members": (SKOS.member,),
    "membersOrdered": (SKOS.memberList,),
    "labelRelations": (SKOSXL.labelRelation,),
    "notes": (SKOS.note,),
    "lexicalForms": (ONTOLEX.lexicalForm,),
    "lexicalSenses": (ONTOLEX.sense,),
    "denotations": (ONTOLEX.denotes,),
    "evokedLexicalConcepts": (ONTOLEX.evokes,),
    "subterms": (URIRef(DECOMP + "subterm"),),
    "constituents": (URIRef(DECOMP + "constituent"),),
    "formRepresentations": (ONTOLEX.representation,),
    "rdfsMembers": (RDFS.member,),
    "collections": (),
    "properties": (),          # everything not yet consumed — always last
}
_PROP_TPL = ("types", "equivalentProperties", "superproperties", "subPropertyChains", "facets",
             "disjointProperties", "domains", "ranges", "lexicalizations", "properties")
TEMPLATES: dict[str, tuple[str, ...]] = {
    "cls": ("types", "classaxioms", "lexicalizations", "properties"),
    "dataRange": ("types", "datatypeDefinitions", "lexicalizations", "properties"),
    "concept": ("types", "topconceptof", "schemes", "broaders", "lexicalizations", "notes",
                "collections", "properties"),
    "property": _PROP_TPL, "objectProperty": _PROP_TPL,
    "datatypeProperty": tuple(s for s in _PROP_TPL if s != "subPropertyChains"),
    "annotationProperty": ("types", "superproperties", "domains", "ranges", "lexicalizations",
                           "properties"),
    "ontologyProperty": ("types", "superproperties", "domains", "ranges", "lexicalizations",
                         "properties"),
    "conceptScheme": ("types", "lexicalizations", "notes", "collections", "properties"),
    "ontology": ("types", "lexicalizations", "imports", "properties"),
    "skosCollection": ("types", "lexicalizations", "notes", "members", "collections",
                       "properties"),
    "skosOrderedCollection": ("types", "lexicalizations", "notes", "membersOrdered",
                              "collections", "properties"),
    "individual": ("types", "lexicalizations", "properties"),
    "xLabel": ("types", "labelRelations", "notes", "properties"),
    "ontolexLexicalEntry": ("types", "lexicalForms", "subterms", "constituents", "rdfsMembers",
                            "lexicalSenses", "denotations", "evokedLexicalConcepts",
                            "properties"),
    "ontolexForm": ("types", "formRepresentations", "properties"),
}


@dataclass
class ViewValue:
    predicate: str
    value: str
    show: str
    scope: str            # local | staged | del_staged | imported | inferred
    is_literal: bool
    lang: str | None = None


@dataclass
class ResourceView:
    resource: str
    role: str
    show: str
    sections: dict[str, list[ViewValue]] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"resource": self.resource, "role": self.role, "show": self.show,
                "sections": {k: [v.__dict__ for v in vs] for k, vs in self.sections.items()}}


def _sub_props(g: Graph, props: Iterable[URIRef]) -> set[URIRef]:
    out = set(props)
    stack = list(out)
    while stack:
        p = stack.pop()
        for s in g.subjects(RDFS.subPropertyOf, p):
            if isinstance(s, URIRef) and s not in out:
                out.add(s)
                stack.append(s)
    return out


def resource_view(resource: URIRef, graphs: dict[str, Graph], sfp: ShortFormProvider
                  ) -> ResourceView:
    """``ResourceView.getResourceView``.

    *graphs* maps scope names to graphs: ``local`` (the working graph), ``staged``
    (staging-add), ``del_staged`` (staging-del), ``imported`` (union of imports),
    ``inferred``. A statement's scope follows ``computeTripleScopeFromGraphs``:
    a staged deletion wins over local, local wins over staged, imported over inferred.
    """
    union = Graph()
    for g in graphs.values():
        for t in g:
            union.add(t)
    role = entity_role(union, resource)
    template = TEMPLATES.get(role) or TEMPLATES["individual"]
    statements = list(union.triples((resource, None, None)))

    def scope(t) -> str:
        if t in graphs.get("del_staged", ()):
            return "del_staged"
        if t in graphs.get("local", ()):
            return "local"
        if t in graphs.get("staged", ()):
            return "staged"
        if t in graphs.get("imported", ()):
            return "imported"
        return "inferred"

    consumed: set = set()
    view = ResourceView(str(resource), role, sfp.render(resource))
    for sec in template:
        if sec == "collections":
            colls = [c for c in union.subjects(SKOS.member, resource)]
            view.sections[sec] = [ViewValue(str(SKOS.member), str(c), sfp.render(c), "local",
                                            False) for c in colls]
            continue
        props = SECTIONS[sec]
        matched = (_sub_props(union, props) if props else None)
        vals = []
        for t in statements:
            if t in consumed:
                continue
            if matched is not None and t[1] not in matched:
                continue
            consumed.add(t)
            o = t[2]
            if isinstance(o, BNode):
                try:
                    show = render(parse_ce(union, o), sfp)
                except UnsupportedConstruct:
                    show = "_:" + str(o)[:8]
            elif isinstance(o, Literal):
                show = str(o)
            else:
                show = sfp.render(o)
            vals.append(ViewValue(str(t[1]), str(o), show, scope(t), isinstance(o, Literal),
                                  o.language if isinstance(o, Literal) else None))
        view.sections[sec] = sorted(vals, key=lambda v: (v.predicate, v.show))
    return view
