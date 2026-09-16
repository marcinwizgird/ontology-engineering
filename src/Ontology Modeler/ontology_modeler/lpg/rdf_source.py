"""Extraction strategy over local RDF files -- the second Extraction strategy.

`TboxExtractor` pulls the TBox out of Fuseki with SPARQL. `RdfFileExtractor` pulls the
same TBox out of a directory tree with rdflib, so a large ontology can be projected
without standing a triplestore up first. Both satisfy the interface `LpgConverter`
consumes (`ping`, `classes`, `taxonomy`, `object_properties`), so the Transformation,
Embedding and Loading stages are shared verbatim.

Two things this extractor captures that the SPARQL one does not, both required before
FIBO is navigable as a graph rather than a bare tree:

* **Restriction shadow edges.** FIBO states nearly all of its relations as anonymous
  `owl:Restriction` superclasses -- `Account subClassOf (isHeldBy some Party)` -- and
  declares `rdfs:domain`/`rdfs:range` comparatively rarely. An extractor that reads only
  domain/range sees a taxonomy with almost no cross-links. Unfolding the restrictions
  into `(source)-[:IS_HELD_BY {via:'restriction'}]->(target)` edges is what turns the
  projection into a graph you can traverse.

* **Module provenance.** Which `owl:Ontology` declared a class. Needed to scope retrieval
  to a module ("answer from Securities only") and to say where an answer came from.

Files are parsed one at a time into their own graph so provenance is known, then unioned
into a single graph for the class-expression walks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import rdflib
from rdflib import BNode, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS

from ..rdf import (iter_rdf_files, local_name, readable_name, rel_type_of,
                   repo_relative, short_name)
from .extract import ClassRecord, PropertyEdge, TaxonomyEdge

log = logging.getLogger("ontology_modeler.lpg")

# Quantifier keyword -> the owl predicate that carries the filler.
_QUANTIFIERS = {
    OWL.someValuesFrom: "some",
    OWL.allValuesFrom: "only",
    OWL.hasValue: "value",
    OWL.onClass: "cardinality",
}

_CARDINALITY_PREDICATES = {
    OWL.qualifiedCardinality: "exactly",
    OWL.minQualifiedCardinality: "min",
    OWL.maxQualifiedCardinality: "max",
    OWL.cardinality: "exactly",
    OWL.minCardinality: "min",
    OWL.maxCardinality: "max",
}

# Definition annotations, in preference order. FIBO standardises on skos:definition; the
# rest are fallbacks so the same extractor works on ontologies that do not.
_DEFINITION_PREDICATES = (
    SKOS.definition,
    RDFS.comment,
    DCTERMS.description,
    URIRef("http://purl.org/dc/elements/1.1/description"),
)

_LABEL_PREDICATES = (RDFS.label, SKOS.prefLabel)

_ALT_LABEL_PREDICATES = (
    SKOS.altLabel,
    URIRef("https://www.omg.org/spec/Commons/AnnotationVocabulary/abbreviation"),
    URIRef("https://www.omg.org/spec/Commons/AnnotationVocabulary/synonym"),
)


@dataclass
class FileClassRecord(ClassRecord):
    """A `ClassRecord` plus the two things only a file-level reader knows.

    `external` marks a class referenced but never declared in the parsed files -- FIBO's
    OMG Commons superclasses, which are not vendored in this repository.
    """

    external: bool = False
    module_iri: str | None = None


@dataclass
class ModuleRecord:
    """One `owl:Ontology` -- a :Module node (the Assistant roadmap's gap 3)."""

    iri: str
    name: str
    path: str | None = None
    abstract: str | None = None


@dataclass
class RestrictionEdge:
    """An `owl:Restriction` unfolded into a directed edge between two named classes."""

    source_iri: str
    target_iri: str
    prop_iri: str
    rel_type: str
    name: str | None
    quantifier: str
    cardinality: int | None = None
    origin: str = "subClassOf"          # or "equivalentClass"


@dataclass
class DefinedIn:
    """Which module declared a class."""

    class_iri: str
    module_iri: str


class RdfFileExtractor:
    """Reads the TBox from RDF files on disk. Duck-compatible with `TboxExtractor`."""

    def __init__(self, paths, *, follow_imports: bool = False,
                 include_external: bool = True):
        self.paths = [Path(p) for p in paths]
        self.follow_imports = follow_imports
        self.include_external = include_external
        self.graph = rdflib.Graph()
        self.modules: list[ModuleRecord] = []
        self._defined_in: dict[str, str] = {}
        self._files_parsed = 0
        self._files_failed: list[tuple[str, str]] = []
        self._loaded = False

    # -- loading ------------------------------------------------------------- #

    def ping(self) -> None:
        """No remote to reach; loads on first use so the converter's call still means something."""
        self.load()

    def load(self) -> "RdfFileExtractor":
        if self._loaded:
            return self
        # FIBO ships a few malformed xsd:dateTime literals; rdflib logs each with a
        # traceback. They are annotation metadata we never read, so silence the noise.
        logging.getLogger("rdflib.term").setLevel(logging.CRITICAL)
        files = iter_rdf_files(self.paths)
        log.info("parsing %d RDF file(s)", len(files))
        for path in files:
            try:
                g = rdflib.Graph()
                g.parse(path.as_posix())
            except Exception as exc:                 # a malformed or non-RDF file
                self._files_failed.append((repo_relative(path), str(exc)[:160]))
                continue
            self._files_parsed += 1
            self._register_module(g, path)
            self.graph += g

        if self.follow_imports:
            self._resolve_remote_imports()

        log.info("parsed %d file(s), %d failed; %d triples, %d module(s)",
                 self._files_parsed, len(self._files_failed), len(self.graph),
                 len(self.modules))
        self._loaded = True
        return self

    def _register_module(self, g: rdflib.Graph, path: Path) -> None:
        """Record the file's owl:Ontology and every class it declares."""
        ontologies = [s for s in g.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)]
        if not ontologies:
            return
        module_iri = str(ontologies[0])
        self.modules.append(ModuleRecord(
            iri=module_iri,
            name=_module_name(module_iri),
            path=repo_relative(path),
            abstract=(_first_literal(g, ontologies[0], (DCTERMS.abstract,))
                      or _first_literal(g, ontologies[0], _DEFINITION_PREDICATES)),
        ))
        for cls in g.subjects(RDF.type, OWL.Class):
            if isinstance(cls, URIRef):
                self._defined_in.setdefault(str(cls), module_iri)

    def _resolve_remote_imports(self) -> None:
        """Fetch owl:imports targets not already present. Opt-in: this hits the network."""
        seen = {m.iri for m in self.modules}
        pending = {str(o) for o in self.graph.objects(None, OWL.imports)} - seen
        for iri in sorted(pending):
            try:
                g = rdflib.Graph()
                g.parse(iri)
            except Exception as exc:
                log.warning("import not resolved: %s (%s)", iri, type(exc).__name__)
                continue
            self.modules.append(ModuleRecord(iri=iri, name=_module_name(iri)))
            for cls in g.subjects(RDF.type, OWL.Class):
                if isinstance(cls, URIRef):
                    self._defined_in.setdefault(str(cls), iri)
            self.graph += g
            log.info("resolved import %s (+%d triples)", iri, len(g))

    # -- the extractor interface --------------------------------------------- #

    def classes(self) -> list[FileClassRecord]:
        """Declared `owl:Class` IRIs, plus referenced-but-undeclared ones as stubs.

        FIBO's upper classes live in OMG Commons, which is not vendored here. Without the
        stubs every `subClassOf` pointing at Commons would be dropped and the taxonomy
        would fall apart at the top; with them the edge survives and the node carries
        `external = true`, so retrieval can tell a real definition from a placeholder.
        """
        self.load()
        declared = {str(c) for c in self.graph.subjects(RDF.type, OWL.Class)
                    if isinstance(c, URIRef)}
        records = [self._class_record(iri, external=False) for iri in sorted(declared)]

        if self.include_external:
            for iri in sorted(self._referenced_classes() - declared):
                records.append(self._class_record(iri, external=True))
        return records

    def _referenced_classes(self) -> set[str]:
        """Every named class the graph points at, whatever position it appears in.

        Restriction fillers count as much as `subClassOf` objects: a third of FIBO's
        restrictions target an OMG Commons class, and collecting only the taxonomy's
        endpoints silently drops those edges at load time because the loader MATCHes
        both ends.
        """
        referenced: set[str] = set()

        def keep(node) -> None:
            if isinstance(node, URIRef) and node != OWL.Thing:
                referenced.add(str(node))

        for s, o in self.graph.subject_objects(RDFS.subClassOf):
            keep(s)
            keep(o)
        for predicate in (*_QUANTIFIERS, RDFS.domain, RDFS.range, OWL.equivalentClass):
            for o in self.graph.objects(None, predicate):
                keep(o)
        # Members of the unions and intersections those fillers point at.
        for connective in (OWL.unionOf, OWL.intersectionOf):
            for lst in self.graph.objects(None, connective):
                for item in self.graph.items(lst):
                    keep(item)
        return referenced

    def _class_record(self, iri: str, *, external: bool) -> FileClassRecord:
        ref = URIRef(iri)
        alts: list[str] = []
        for pred in _ALT_LABEL_PREDICATES:
            alts += [str(o) for o in self.graph.objects(ref, pred) if isinstance(o, Literal)]
        return FileClassRecord(
            iri=iri,
            short_name=short_name(iri),
            name=_first_literal(self.graph, ref, _LABEL_PREDICATES) or readable_name(iri),
            definition=_first_literal(self.graph, ref, _DEFINITION_PREDICATES),
            alt_labels=sorted(set(alts)),
            external=external,
            module_iri=self._defined_in.get(iri),
        )

    def taxonomy(self) -> list[TaxonomyEdge]:
        self.load()
        edges = []
        for s, o in self.graph.subject_objects(RDFS.subClassOf):
            if isinstance(s, URIRef) and isinstance(o, URIRef) and o != OWL.Thing:
                edges.append(TaxonomyEdge(sub_iri=str(s), super_iri=str(o)))
        return edges

    def object_properties(self) -> list[PropertyEdge]:
        """Object properties that declare both a named domain and a named range."""
        self.load()
        out = []
        for prop in self.graph.subjects(RDF.type, OWL.ObjectProperty):
            if not isinstance(prop, URIRef):
                continue
            domains = [d for d in self.graph.objects(prop, RDFS.domain) if isinstance(d, URIRef)]
            ranges = [r for r in self.graph.objects(prop, RDFS.range) if isinstance(r, URIRef)]
            if not domains or not ranges:
                continue
            name = (_first_literal(self.graph, prop, _LABEL_PREDICATES)
                    or readable_name(str(prop)))
            definition = _first_literal(self.graph, prop, _DEFINITION_PREDICATES)
            for d in domains:
                for r in ranges:
                    out.append(PropertyEdge(
                        prop_iri=str(prop), rel_type=rel_type_of(str(prop)),
                        name=name, definition=definition,
                        domain_iri=str(d), range_iri=str(r),
                    ))
        return out

    # -- the additions ------------------------------------------------------- #

    def restrictions(self) -> list[RestrictionEdge]:
        """Unfold anonymous class expressions into edges between named classes.

        Walks `rdfs:subClassOf` and `owl:equivalentClass` from every named class. A filler
        that is itself anonymous (a union, an intersection) contributes each of its named
        members, so `serves some (Person or Organization)` yields two edges rather than none.
        """
        self.load()
        edges: list[RestrictionEdge] = []
        for origin, predicate in (("subClassOf", RDFS.subClassOf),
                                  ("equivalentClass", OWL.equivalentClass)):
            for source, expression in self.graph.subject_objects(predicate):
                if not isinstance(source, URIRef) or not isinstance(expression, BNode):
                    continue
                for restriction in self._expression_members(expression):
                    edges.extend(self._restriction_edges(str(source), restriction, origin))
        return edges

    def _expression_members(self, node: BNode, depth: int = 0) -> list[BNode]:
        """The restriction bnodes inside a class expression (itself, or its list members)."""
        if depth > 4:
            return []
        if (node, RDF.type, OWL.Restriction) in self.graph:
            return [node]
        members: list[BNode] = []
        for connective in (OWL.intersectionOf, OWL.unionOf):
            for lst in self.graph.objects(node, connective):
                for item in self.graph.items(lst):
                    if isinstance(item, BNode):
                        members += self._expression_members(item, depth + 1)
        return members

    def _restriction_edges(self, source_iri: str, restriction: BNode,
                           origin: str) -> list[RestrictionEdge]:
        prop = self.graph.value(restriction, OWL.onProperty)
        if not isinstance(prop, URIRef):
            return []                      # a property chain or an inverse expression

        filler, quantifier, cardinality = None, None, None
        for predicate, keyword in _QUANTIFIERS.items():
            value = self.graph.value(restriction, predicate)
            if value is not None:
                filler, quantifier = value, keyword
                break
        if filler is None:
            return []                      # unqualified cardinality: no target class

        if quantifier == "cardinality":
            quantifier = "exactly"
            for predicate, keyword in _CARDINALITY_PREDICATES.items():
                value = self.graph.value(restriction, predicate)
                if isinstance(value, Literal):
                    quantifier, cardinality = keyword, int(value)
                    break

        name = _first_literal(self.graph, prop, _LABEL_PREDICATES) or readable_name(str(prop))
        rel_type = rel_type_of(str(prop))
        return [
            RestrictionEdge(
                source_iri=source_iri, target_iri=target, prop_iri=str(prop),
                rel_type=rel_type, name=name, quantifier=quantifier,
                cardinality=cardinality, origin=origin,
            )
            for target in self._named_fillers(filler)
        ]

    def _named_fillers(self, node, depth: int = 0) -> list[str]:
        """Named classes inside a filler: the IRI itself, or the members of a union."""
        if isinstance(node, URIRef):
            return [] if node == OWL.Thing else [str(node)]
        if not isinstance(node, BNode) or depth > 3:
            return []
        out: list[str] = []
        for connective in (OWL.unionOf, OWL.intersectionOf):
            for lst in self.graph.objects(node, connective):
                for item in self.graph.items(lst):
                    out += self._named_fillers(item, depth + 1)
        return out

    def defined_in(self) -> list[DefinedIn]:
        self.load()
        return [DefinedIn(class_iri=c, module_iri=m)
                for c, m in sorted(self._defined_in.items())]

    def module_records(self) -> list[ModuleRecord]:
        self.load()
        return list(self.modules)

    def report(self) -> dict:
        self.load()
        return {
            "files_parsed": self._files_parsed,
            "files_failed": len(self._files_failed),
            "failures": self._files_failed[:10],
            "triples": len(self.graph),
            "modules": len(self.modules),
        }


# -- helpers ----------------------------------------------------------------- #

def _first_literal(g: rdflib.Graph, subject, predicates) -> str | None:
    """First English (or untagged) literal among the predicates, in preference order."""
    for predicate in predicates:
        values = [o for o in g.objects(subject, predicate) if isinstance(o, Literal)]
        if not values:
            continue
        for value in values:
            if value.language in (None, "en", "en-US", "en-GB"):
                return str(value).strip()
        return str(values[0]).strip()
    return None


def _module_name(iri: str) -> str:
    """'.../FBC/ProductsAndServices/FinancialProductsAndServices/' -> the last two segments."""
    parts = [p for p in iri.rstrip("/#").split("/") if p]
    return "/".join(parts[-2:]) if len(parts) >= 2 else (parts[-1] if parts else iri)
