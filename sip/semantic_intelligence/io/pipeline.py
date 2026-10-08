"""Import/export pipeline — Semantic Turkey's loader → lifter → transformers →
exporter → deployer chain (``InputOutput.loadRDF``, ``Export.export``).

* **Lifters** turn bytes into RDF: :func:`lift_rdf` (every rdflib format) and
  :func:`lift_table` (CSV → RDF via a mapping; the Sheet2RDF role — see
  ``kg.lifting`` for the mapping language).
* **Transformers** are RDF→RDF steps on a *working copy*, never on the project:
  the eight shipped by Semantic Turkey are ported as plain functions over an
  rdflib ``Graph`` and registered in :data:`TRANSFORMERS` (an extension point).
* **Exporters** serialise; the Protégé save formats are offered (RDF/XML default,
  Turtle, OWL/XML is not — rdflib has no OWL/XML writer — N-Triples, JSON-LD,
  TriG). Manchester-syntax export is a lossy rendering and is labelled as such.

Imports go through the change tracker like any other write (operation
``io.loadRDF``), so a bulk load is one commit in history: VocBench's "complete
history" requirement, which a direct GSP PUT would break.
"""

from __future__ import annotations

from typing import Callable

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS, SKOS

from ..core.namespaces import SKOSXL

FORMATS = {"turtle": "ttl", "xml": "rdf", "nt": "nt", "json-ld": "jsonld", "n3": "n3",
           "trig": "trig"}


def lift_rdf(data: str | bytes, fmt: str = "turtle", base: str | None = None) -> Graph:
    g = Graph()
    g.parse(data=data, format=fmt, publicID=base)
    return g


# ----------------------------- transformers -------------------------------- #

def t_sparql(g: Graph, filter: str) -> Graph:
    """``SPARQLRDFTransformer``: a SPARQL Update on the working copy."""
    w = _copy(g)
    w.update(filter)
    return w


def t_property_normalizer(g: Graph, normalizingProperty: str,
                          propertiesBeingNormalized: list[str]) -> Graph:
    w = _copy(g)
    norm = URIRef(normalizingProperty)
    for p in map(URIRef, propertiesBeingNormalized):
        for s, o in list(w.subject_objects(p)):
            w.remove((s, p, o))
            w.add((s, norm, o))
    return w


def t_delete_property_value(g: Graph, resource: str, property: str,
                            value: str | None = None) -> Graph:
    w = _copy(g)
    w.remove((URIRef(resource), URIRef(property), None if value is None else _term(value)))
    return w


def t_update_property_value(g: Graph, resource: str, property: str, value: str,
                            oldValue: str | None = None) -> Graph:
    w = _copy(g)
    r, p = URIRef(resource), URIRef(property)
    w.remove((r, p, None if oldValue is None else _term(oldValue)))
    w.add((r, p, _term(value)))
    return w


def t_xlabel_dereification(g: Graph, preserveReifiedLabels: bool = False) -> Graph:
    w = _copy(g)
    for kind in ("prefLabel", "altLabel", "hiddenLabel"):
        for s, xl in list(w.subject_objects(SKOSXL[kind])):
            for lf in list(w.objects(xl, SKOSXL.literalForm)):
                w.add((s, SKOS[kind], lf))
            if not preserveReifiedLabels:
                w.remove((s, SKOSXL[kind], xl))
                w.remove((xl, None, None))
    return w


def t_xnote_dereification(g: Graph, preserveReifiedNotes: bool = False) -> Graph:
    w = _copy(g)
    notes = {SKOS.note, SKOS.definition, SKOS.scopeNote, SKOS.example, SKOS.historyNote,
             SKOS.editorialNote, SKOS.changeNote}
    for p in notes:
        for c, n in list(w.subject_objects(p)):
            for v in list(w.objects(n, RDF.value)):
                w.add((c, p, v))
                if not preserveReifiedNotes:
                    w.remove((c, p, n))
                    w.remove((n, None, None))
    return w


def t_scheme_exporter(g: Graph, scheme: str) -> Graph:
    """Keep one concept scheme: drop every concept not in it, then other schemes."""
    w = _copy(g)
    s = URIRef(scheme)
    keep = set(w.subjects(SKOS.inScheme, s)) | set(w.subjects(SKOS.topConceptOf, s))
    for c in list(w.subjects(RDF.type, SKOS.Concept)):
        if c not in keep:
            for xl in list(w.objects(c, SKOSXL.prefLabel)) + list(w.objects(c, SKOSXL.altLabel)):
                w.remove((xl, None, None))
            w.remove((c, None, None))
            w.remove((None, None, c))
    for other in list(w.subjects(RDF.type, SKOS.ConceptScheme)):
        if other != s:
            w.remove((other, None, None))
            w.remove((None, None, other))
    return w


def t_edoal_flatten(g: Graph, mappingProperties: dict[str, str]) -> Graph:
    """EDOAL/Alignment cells → flat ``e1 prop e2`` triples, replacing content."""
    from ..core.namespaces import ALIGN
    out = Graph()
    for c in g.subjects(ALIGN.entity1, None):
        rel = str(g.value(c, ALIGN.relation) or "=")
        prop = mappingProperties.get(rel)
        if prop:
            out.add((g.value(c, ALIGN.entity1), URIRef(prop), g.value(c, ALIGN.entity2)))
    return out


TRANSFORMERS: dict[str, Callable[..., Graph]] = {
    "SPARQLRDFTransformer": t_sparql,
    "PropertyNormalizerTransformer": t_property_normalizer,
    "DeletePropertyValueRDFTransformer": t_delete_property_value,
    "UpdatePropertyValueRDFTransformer": t_update_property_value,
    "XLabelDereificationRDFTransformer": t_xlabel_dereification,
    "XNoteDereificationRDFTransformer": t_xnote_dereification,
    "SchemeExporterTransformer": t_scheme_exporter,
    "EDOAL2StdFlatFormatsTransformer": t_edoal_flatten,
}


def run_pipeline(g: Graph, steps: list[dict]) -> Graph:
    """``TransformationPipeline``: ``[{"filter": {"factoryId": …, "configuration": {…}}}]``."""
    w = g
    for i, step in enumerate(steps):
        spec = step["filter"]
        fn = TRANSFORMERS.get(spec["factoryId"])
        if fn is None:
            raise KeyError(f"step {i}: unknown transformer {spec['factoryId']!r}; "
                           f"known: {sorted(TRANSFORMERS)}")
        w = fn(w, **spec.get("configuration", {}))
    return w


def export(g: Graph, fmt: str = "xml", steps: list[dict] | None = None) -> str:
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {sorted(FORMATS)}")
    w = run_pipeline(g, steps or [])
    return w.serialize(format=fmt)


def _copy(g: Graph) -> Graph:
    w = Graph()
    for t in g:
        w.add(t)
    for p, n in g.namespaces():
        w.bind(p, n, override=False)
    return w


def _term(v: str):
    if v.startswith("<") and v.endswith(">"):
        return URIRef(v[1:-1])
    if v.startswith(("http://", "https://", "urn:")):
        return URIRef(v)
    return Literal(v)
