"""Entity rendering — Protégé's ``OWLEntityRenderer`` family, ported.

Protégé ships three renderers, selected in *Preferences ▸ Renderer*:

* ``OWLEntityAnnotationValueRenderer`` — the value of an annotation property
  (``rdfs:label`` by default; ``skos:prefLabel`` is a common addition), chosen by
  an ordered **language preference** list, falling back to the short form;
* ``PrefixedNameRenderer`` — ``prefix:localName`` from the active prefix map;
* ``OWLEntityRendererImpl`` — the IRI fragment / last path segment.

Whatever renders a name must also *resolve* it back, or a Manchester expression
typed with labels cannot be parsed: Protégé keeps an ``OWLEntityFinder`` index in
step with the renderer for exactly that reason. :class:`ShortFormProvider` does
both, and quotes renderings that are not Manchester-safe tokens (``'has part'``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

_SAFE_TOKEN = re.compile(r"^[A-Za-z_][A-Za-z0-9_\-.:]*$")
_KEYWORDS = {"and", "or", "not", "some", "only", "value", "min", "max", "exactly",
             "that", "Self", "inverse", "integer", "decimal", "float", "string"}

ENTITY_TYPES = {
    OWL.Class: "class", RDFS.Class: "class", OWL.ObjectProperty: "objectProperty",
    OWL.DatatypeProperty: "dataProperty", OWL.AnnotationProperty: "annotationProperty",
    OWL.NamedIndividual: "individual", RDFS.Datatype: "datatype",
    SKOS.Concept: "concept", SKOS.ConceptScheme: "conceptScheme",
    SKOS.Collection: "skosCollection", SKOS.OrderedCollection: "skosOrderedCollection",
    OWL.Ontology: "ontology",
}
_PROP_SUBTYPES = (OWL.TransitiveProperty, OWL.SymmetricProperty, OWL.FunctionalProperty,
                  OWL.InverseFunctionalProperty, OWL.AsymmetricProperty,
                  OWL.ReflexiveProperty, OWL.IrreflexiveProperty)

BUILTIN_DATATYPES = {f"xsd:{n}": XSD[n] for n in (
    "string", "integer", "int", "long", "short", "decimal", "float", "double", "boolean",
    "date", "dateTime", "time", "anyURI", "nonNegativeInteger", "positiveInteger",
    "gYear", "duration", "language", "token", "normalizedString")}
BUILTIN_DATATYPES["rdfs:Literal"] = RDFS.Literal
BUILTIN_DATATYPES.update({f"rdf:{n}": RDF[n] for n in ("PlainLiteral", "langString",
                                                       "XMLLiteral", "HTML")})
BUILTIN_DATATYPES.update({"owl:real": OWL.real, "owl:rational": OWL.rational})
BUILTIN_DATATYPES.update({"integer": XSD.integer, "decimal": XSD.decimal,
                          "float": XSD.float, "string": XSD.string})


def local_name(iri: str) -> str:
    s = str(iri)
    for sep in ("#", "/", ":"):
        if sep in s:
            tail = s.rsplit(sep, 1)[1]
            if tail:
                return tail
    return s


def quote(name: str) -> str:
    """Manchester quoting: names that are not single safe tokens go in '...'."""
    if _SAFE_TOKEN.match(name) and name not in _KEYWORDS:
        return name
    return "'" + name.replace("'", "\\'") + "'"


def entity_role(g: Graph, iri: URIRef) -> str:
    """Semantic Turkey's ``RDFResourceRole`` for *iri* (cls, property, …).

    Order matters: an IRI typed both ``owl:Class`` and ``skos:Concept`` (punning)
    reports ``cls``, as Semantic Turkey's ``RoleRecognitionOrchestrator`` does.
    """
    types = set(g.objects(iri, RDF.type))
    for t in (OWL.Class, RDFS.Class, OWL.ObjectProperty, OWL.DatatypeProperty,
              OWL.AnnotationProperty, OWL.OntologyProperty, RDFS.Datatype,
              SKOS.ConceptScheme, SKOS.OrderedCollection, SKOS.Collection,
              SKOS.Concept, OWL.Ontology):
        if t in types:
            return {OWL.Class: "cls", RDFS.Class: "cls", OWL.ObjectProperty: "objectProperty",
                    OWL.DatatypeProperty: "datatypeProperty",
                    OWL.AnnotationProperty: "annotationProperty",
                    OWL.OntologyProperty: "ontologyProperty", RDFS.Datatype: "dataRange",
                    SKOS.ConceptScheme: "conceptScheme",
                    SKOS.OrderedCollection: "skosOrderedCollection",
                    SKOS.Collection: "skosCollection", SKOS.Concept: "concept",
                    OWL.Ontology: "ontology"}[t]
    if types & set(_PROP_SUBTYPES) or RDF.Property in types:
        return "property"
    if (iri, RDFS.subClassOf, None) in g:
        return "cls"
    if (iri, RDFS.subPropertyOf, None) in g:
        return "property"
    if types:
        return "individual"
    return "individual" if (iri, None, None) in g else "unknown"


@dataclass
class ShortFormProvider:
    """Render IRIs to short names and resolve short names back to IRIs.

    ``mode``: ``"label"`` (annotation value, Protégé's default for most users),
    ``"prefixed"`` or ``"fragment"``.
    """

    graph: Graph
    mode: str = "label"
    annotation_properties: tuple[URIRef, ...] = (RDFS.label, SKOS.prefLabel)
    languages: tuple[str, ...] = ("en", "")
    prefixes: dict[str, str] = field(default_factory=dict)
    _render: dict[URIRef, str] = field(default_factory=dict, init=False, repr=False)
    _index: dict[str, set[URIRef]] = field(default_factory=dict, init=False, repr=False)
    _types: dict[URIRef, set[str]] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.prefixes:
            self.prefixes = {p: str(n) for p, n in self.graph.namespaces()}
        self.rebuild()

    # -- index maintenance (Protégé rebuilds on every ontology change event) --
    def rebuild(self) -> None:
        self._render.clear()
        self._index.clear()
        self._types.clear()
        for s, t in self.graph.subject_objects(RDF.type):
            if not isinstance(s, URIRef):
                continue
            kind = ENTITY_TYPES.get(t)
            if kind is None and t in _PROP_SUBTYPES:
                kind = "objectProperty" if t != OWL.FunctionalProperty else None
            if kind is None and isinstance(t, URIRef) and t not in (OWL.Restriction,):
                # typed by a user class -> an individual
                if (t, RDF.type, OWL.Class) in self.graph or (t, RDF.type, RDFS.Class) in self.graph:
                    kind = "individual"
            if kind:
                self._types.setdefault(s, set()).add(kind)
        self._infer_undeclared()
        for s in self._types:
            name = self.render(s)
            self._index.setdefault(name, set()).add(s)
            self._index.setdefault(self.prefixed(s), set()).add(s)
            self._index.setdefault(local_name(s), set()).add(s)

    def _infer_undeclared(self) -> None:
        """Type entities that are *used* but not declared, as the OWL API's RDF consumer
        does in lax mode: imported vocabularies are often absent (FIBO uses OMG Commons
        properties without the Commons files being loaded). Declared kinds always win."""
        g, T = self.graph, self._types

        def add(x, kind):
            if isinstance(x, URIRef) and not T.get(x) and not str(x).startswith(
                    ("http://www.w3.org/2001/XMLSchema#", str(OWL), str(RDF), str(RDFS))):
                T.setdefault(x, set()).add(kind)
        data_fillers = (OWL.someValuesFrom, OWL.allValuesFrom, OWL.onDataRange)
        for r in g.subjects(RDF.type, OWL.Restriction):
            p = g.value(r, OWL.onProperty)
            if not isinstance(p, URIRef) or T.get(p):
                continue
            filler = next((g.value(r, f) for f in data_fillers + (OWL.onClass,)
                           if g.value(r, f) is not None), None)
            hv = g.value(r, OWL.hasValue)
            is_data = (isinstance(hv, Literal) or g.value(r, OWL.onDataRange) is not None
                       or (isinstance(filler, URIRef) and (
                           str(filler).startswith("http://www.w3.org/2001/XMLSchema#")
                           or filler == RDFS.Literal
                           or (filler, RDF.type, RDFS.Datatype) in g)))
            add(p, "dataProperty" if is_data else "objectProperty")
        for p in (RDFS.subClassOf, OWL.equivalentClass, OWL.disjointWith, OWL.someValuesFrom,
                  OWL.allValuesFrom, OWL.onClass, RDFS.domain):
            for s, o in g.subject_objects(p):
                if p in (RDFS.subClassOf, OWL.equivalentClass, OWL.disjointWith):
                    add(s, "class")
                if p != RDFS.domain or isinstance(o, URIRef):
                    if not (isinstance(o, URIRef) and str(o).startswith(
                            "http://www.w3.org/2001/XMLSchema#")):
                        add(o, "class")
        for s, o in g.subject_objects(RDFS.subPropertyOf):
            kind = next(iter(T.get(s, set()) | T.get(o, set())), None)
            if kind in ("objectProperty", "dataProperty", "annotationProperty"):
                add(s, kind)
                add(o, kind)
        # second pass, now that property kinds are known: fillers and values
        for r in g.subjects(RDF.type, OWL.Restriction):
            p = g.value(r, OWL.onProperty)
            kinds = T.get(p, set()) if isinstance(p, URIRef) else set()
            for f in data_fillers:
                filler = g.value(r, f)
                if "dataProperty" in kinds and isinstance(filler, URIRef):
                    if "class" in T.get(filler, set()) and not (filler, RDF.type, OWL.Class) in g:
                        T[filler].discard("class")
                    add(filler, "datatype")
            hv = g.value(r, OWL.hasValue)
            if isinstance(hv, URIRef) and "objectProperty" in kinds:
                add(hv, "individual")
        for p, rng in g.subject_objects(RDFS.range):
            if "dataProperty" in T.get(p, set()):
                add(rng, "datatype")

    def types_of(self, iri: URIRef) -> set[str]:
        return self._types.get(iri, set())

    # -- rendering ---------------------------------------------------------- #
    def label(self, iri: URIRef) -> str | None:
        """The best annotation value by (property order × language preference)."""
        for prop in self.annotation_properties:
            values = [o for o in self.graph.objects(iri, prop) if isinstance(o, Literal)]
            if not values:
                continue
            for lang in self.languages:
                for v in values:
                    if (v.language or "") == lang:
                        return str(v)
            return str(values[0])
        return None

    def prefixed(self, iri: URIRef) -> str:
        s = str(iri)
        best = None
        for p, ns in self.prefixes.items():
            if s.startswith(ns) and (best is None or len(ns) > len(best[1])):
                best = (p, ns)
        if best:
            return f"{best[0]}:{s[len(best[1]):]}" if best[0] else s[len(best[1]):]
        return local_name(s)

    def render(self, iri: URIRef) -> str:
        cached = self._render.get(iri)
        if cached is not None:
            return cached
        if iri in (OWL.Thing, OWL.Nothing):
            out = "owl:" + local_name(iri)
        elif self.mode == "label":
            out = self.label(iri) or local_name(iri)
        elif self.mode == "prefixed":
            out = self.prefixed(iri)
        else:
            out = local_name(iri)
        self._render[iri] = out
        return out

    def rendering(self, iri: URIRef) -> str:
        """Render and quote — what goes into Manchester text.

        Lossless by construction: when the preferred rendering is shared by several
        entities (FIBO has many properties labelled "identifies"), the prefixed name is
        used, else the full IRI. Protégé instead resolves an ambiguous name to the most
        used entity, which can silently change the meaning of an edited axiom."""
        name = self.render(iri)
        if len(self._index.get(name, ())) <= 1:
            return quote(name)
        pref = self.prefixed(iri)
        if ":" in pref and len(self._index.get(pref, ())) <= 1:
            return pref
        return f"<{iri}>"

    # -- resolution (OWLEntityFinder) --------------------------------------- #
    def resolve(self, name: str, kinds: Iterable[str] | None = None) -> list[URIRef]:
        name = name[1:-1].replace("\\'", "'") if name.startswith("'") else name
        if name.startswith("<") and name.endswith(">"):
            return [URIRef(name[1:-1])]
        if name in ("owl:Thing", "Thing"):
            return [OWL.Thing]
        if name in ("owl:Nothing", "Nothing"):
            return [OWL.Nothing]
        hits = set(self._index.get(name, set()))
        if not hits and ":" in name:
            p, _, rest = name.partition(":")
            if p in self.prefixes:
                cand = URIRef(self.prefixes[p] + rest)
                hits = {cand} if cand in self._types else set()
        if kinds is not None:
            ks = set(kinds)
            hits = {h for h in hits if self._types.get(h, set()) & ks}
        return sorted(hits)

    def find(self, pattern: str, kinds: Iterable[str] | None = None,
             limit: int = 50) -> list[URIRef]:
        """``OWLEntityFinder.getMatchingOWLEntities``: ``*`` wildcards, else
        case-insensitive *prefix* match on any rendering — Protégé's search box."""
        if "*" in pattern:
            rx = re.compile("^" + ".*".join(map(re.escape, pattern.split("*"))) + "$", re.I)
        else:
            rx = re.compile("^" + re.escape(pattern), re.I)
        ks = set(kinds) if kinds is not None else None
        out = []
        for name, iris in sorted(self._index.items()):
            if rx.search(name):
                for i in iris:
                    if (ks is None or self._types.get(i, set()) & ks) and i not in out:
                        out.append(i)
            if len(out) >= limit:
                break
        return out[:limit]
