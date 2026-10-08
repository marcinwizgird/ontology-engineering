"""Project a full RDF graph to Playground's model, keeping exact provenance for the merge.

`project(graph, graph_uri)` returns a `Projection`: the editable `Ontology` (nodes = named
owl:Class / skos:Concept, edges = subClassOf / broader / narrower / mapping / objectProperty,
attributes = datatype properties) PLUS a provenance record for every surfaced field -- the
exact rdflib term (with language/datatype) each name/description/range came from, and the
exact triples each edge stands for. The merge uses that provenance to change ONLY what the
user changed and leave every other triple untouched.

What is deliberately NOT surfaced (and therefore preserved verbatim on save): owl:Restriction
and other anonymous class expressions, subClassOf to blank nodes, imports, individuals/ABox,
property characteristics, and any annotation other than the name/description we lifted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from rdflib import Graph, RDF, RDFS, OWL, URIRef, Literal
from rdflib.namespace import XSD, SKOS, DCTERMS

from ..rdf import local_name
from .model import Ontology, EntityType, Property, Relationship

# xsd datatype IRI -> Playground Property.type. Only these round-trip as a type change; a
# range outside this map (e.g. a cmns datatype) is preserved and never overwritten.
XSD_TO_PG = {
    XSD.string: "string", XSD.normalizedString: "string", XSD.token: "string",
    XSD.anyURI: "string", XSD.integer: "integer", XSD.int: "integer", XSD.long: "integer",
    XSD.nonNegativeInteger: "integer", XSD.positiveInteger: "integer",
    XSD.decimal: "decimal", XSD.double: "double", XSD.float: "double",
    XSD.date: "date", XSD.dateTime: "datetime", XSD.boolean: "boolean",
}
PG_TO_XSD = {
    "string": XSD.string, "integer": XSD.integer, "decimal": XSD.decimal,
    "double": XSD.double, "date": XSD.date, "datetime": XSD.dateTime,
    "boolean": XSD.boolean, "enum": XSD.string,
}
MAPPING_PREDS = {
    SKOS.exactMatch: "exactMatch", SKOS.closeMatch: "closeMatch",
    SKOS.broadMatch: "broadMatch", SKOS.narrowMatch: "narrowMatch",
    SKOS.relatedMatch: "relatedMatch",
}
NAME_FROM = "__name_from__"  # marker: name came from IRI local name, no literal to remove

_CLASS_COLOR, _CONCEPT_COLOR = "#6366f1", "#0ea5e9"


# --------------------------------------------------------------------------- #
# Provenance                                                                  #
# --------------------------------------------------------------------------- #

@dataclass
class DPropProv:
    iri: URIRef
    owner: URIRef
    name_lit: Optional[Literal]
    range_iri: Optional[URIRef]
    range_mapped: bool
    desc_pred: Optional[URIRef]
    desc_lit: Optional[Literal]


@dataclass
class NodeProv:
    iri: URIRef
    kind: str
    type_triples: list          # the rdf:type triples we surfaced (owl:Class and/or skos:Concept)
    name_pred: Optional[URIRef]
    name_lit: Optional[Literal]
    desc_pred: Optional[URIRef]
    desc_lit: Optional[Literal]
    props: dict = field(default_factory=dict)   # property name -> DPropProv


@dataclass
class EdgeProv:
    id: str
    kind: str
    triples: list = field(default_factory=list)   # exact base triples for triple-level edges
    # objectProperty field-level provenance:
    iri: Optional[URIRef] = None
    name_lit: Optional[Literal] = None
    domain_iri: Optional[URIRef] = None
    range_iri: Optional[URIRef] = None
    desc_pred: Optional[URIRef] = None
    desc_lit: Optional[Literal] = None


@dataclass
class Projection:
    graph_uri: str
    ontology_iri: Optional[str]
    base_ns: str
    ontology: Ontology
    nodes: dict = field(default_factory=dict)   # node id (IRI str) -> NodeProv
    edges: dict = field(default_factory=dict)   # edge id (str)     -> EdgeProv
    ont_name_lit: Optional[Literal] = None
    ont_desc_pred: Optional[URIRef] = None
    ont_desc_lit: Optional[Literal] = None

    def envelope(self) -> dict:
        """The JSON payload sent to the browser (provenance stays server-side)."""
        return {
            "graphUri": self.graph_uri,
            "ontologyIri": self.ontology_iri,
            "baseNs": self.base_ns,
            "ontology": self.ontology.to_dict(),
        }


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _pick_literal(g: Graph, s, preds):
    """First literal for `s` across `preds`, preferring @en then lexicographic (deterministic)."""
    for p in preds:
        lits = [o for o in g.objects(s, p) if isinstance(o, Literal)]
        if lits:
            lits.sort(key=lambda l: (0 if l.language == "en" else 1, str(l.language or ""), str(l)))
            return p, lits[0]
    return None, None


def _single_iri(g: Graph, s, p) -> Optional[URIRef]:
    """The object of s,p iff there is exactly one and it is an IRI; else None."""
    objs = list(g.objects(s, p))
    iris = [o for o in objs if isinstance(o, URIRef)]
    if len(objs) == 1 and len(iris) == 1:
        return iris[0]
    return None


def _derive_base_ns(ont_iri: Optional[str], node_iris) -> str:
    """A namespace to mint new IRIs under: the ontology IRI, else the commonest node prefix."""
    if ont_iri:
        base = ont_iri.rstrip("/#")
        return base + ("#" if "#" in ont_iri else "/")
    from collections import Counter
    prefixes = Counter()
    for iri in node_iris:
        s = str(iri)
        for sep in ("#", "/"):
            if sep in s:
                prefixes[s.rsplit(sep, 1)[0] + sep] += 1
                break
    return prefixes.most_common(1)[0][0] if prefixes else "urn:ontology:"


# --------------------------------------------------------------------------- #
# Projection                                                                   #
# --------------------------------------------------------------------------- #

def project(graph: Graph, graph_uri: str, ontology_iri: Optional[str] = None) -> Projection:
    classes = {s for s in graph.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef)}
    concepts = {s for s in graph.subjects(RDF.type, SKOS.Concept) if isinstance(s, URIRef)}
    node_iris = classes | concepts

    onts = [s for s in graph.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)]
    ont = URIRef(ontology_iri) if ontology_iri else (onts[0] if onts else None)
    base_ns = _derive_base_ns(str(ont) if ont else None, node_iris)

    proj = Projection(graph_uri=graph_uri, ontology_iri=str(ont) if ont else None,
                      base_ns=base_ns, ontology=Ontology(name="", description=""))

    # -- ontology header ---------------------------------------------------- #
    if ont is not None:
        np, nl = _pick_literal(graph, ont, [RDFS.label, DCTERMS.title, SKOS.prefLabel])
        dp, dl = _pick_literal(graph, ont, [RDFS.comment, DCTERMS.description, SKOS.definition])
        proj.ontology.name = str(nl) if nl is not None else local_name(str(ont))
        proj.ontology.description = str(dl) if dl is not None else ""
        proj.ont_name_lit = nl
        proj.ont_desc_pred, proj.ont_desc_lit = dp, dl
    else:
        proj.ontology.name = local_name(graph_uri)

    # -- nodes (classes + concepts) ----------------------------------------- #
    for iri in sorted(node_iris, key=str):
        kind = "class" if iri in classes else "concept"
        type_triples = []
        if iri in classes:
            type_triples.append((iri, RDF.type, OWL.Class))
        if iri in concepts:
            type_triples.append((iri, RDF.type, SKOS.Concept))
        name_preds = ([RDFS.label, SKOS.prefLabel] if kind == "class"
                      else [SKOS.prefLabel, RDFS.label])
        desc_preds = ([RDFS.comment, SKOS.definition, DCTERMS.description] if kind == "class"
                      else [SKOS.definition, RDFS.comment, DCTERMS.description])
        np, nl = _pick_literal(graph, iri, name_preds)
        dp, dl = _pick_literal(graph, iri, desc_preds)
        et = EntityType(
            id=str(iri),
            name=str(nl) if nl is not None else local_name(str(iri)),
            description=str(dl) if dl is not None else "",
            kind=kind,
            color=_CLASS_COLOR if kind == "class" else _CONCEPT_COLOR,
            icon="Box" if kind == "class" else "Tag",
        )
        proj.ontology.entityTypes.append(et)
        proj.nodes[str(iri)] = NodeProv(
            iri=iri, kind=kind, type_triples=type_triples,
            name_pred=np, name_lit=nl, desc_pred=dp, desc_lit=dl,
        )

    # -- datatype properties as node attributes ----------------------------- #
    for p in graph.subjects(RDF.type, OWL.DatatypeProperty):
        if not isinstance(p, URIRef):
            continue
        owner = _single_iri(graph, p, RDFS.domain)
        if owner is None or str(owner) not in proj.nodes:
            continue                      # unattached / complex domain -> preserved untouched
        node_prov = proj.nodes[str(owner)]
        pl_p, pl = _pick_literal(graph, p, [RDFS.label, SKOS.prefLabel])
        pname = str(pl) if pl is not None else local_name(str(p))
        if pname in node_prov.props:
            continue                      # first wins; the other is preserved untouched
        rng = _single_iri(graph, p, RDFS.range)
        mapped = rng in XSD_TO_PG if rng is not None else False
        dp, dl = _pick_literal(graph, p, [RDFS.comment, SKOS.definition])
        prop = Property(
            name=pname,
            type=XSD_TO_PG.get(rng, "string") if rng is not None else "string",
            description=str(dl) if dl is not None else None,
        )
        node_prov.props[pname] = DPropProv(
            iri=p, owner=owner, name_lit=pl, range_iri=rng, range_mapped=mapped,
            desc_pred=dp, desc_lit=dl,
        )
        # attach to the owner EntityType (find it; small n, linear is fine)
        for et in proj.ontology.entityTypes:
            if et.id == str(owner):
                et.properties.append(prop)
                break

    # -- edges -------------------------------------------------------------- #
    def add_triple_edge(kind, s, pred, o, name):
        eid = f"{s}|{kind}|{o}"
        if eid in proj.edges:
            return
        proj.edges[eid] = EdgeProv(id=eid, kind=kind, triples=[(s, pred, o)])
        proj.ontology.relationships.append(Relationship(
            id=eid, name=name, from_=str(s), to=str(o), kind=kind,
            cardinality="many-to-one" if kind in ("subClassOf", "broader") else "many-to-many",
        ))

    for s, o in graph.subject_objects(RDFS.subClassOf):
        if isinstance(s, URIRef) and isinstance(o, URIRef) and str(s) in proj.nodes and str(o) in proj.nodes:
            add_triple_edge("subClassOf", s, RDFS.subClassOf, o, "subClassOf")
    for s, o in graph.subject_objects(SKOS.broader):
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            add_triple_edge("broader", s, SKOS.broader, o, "broader")
    for s, o in graph.subject_objects(SKOS.narrower):
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            add_triple_edge("narrower", s, SKOS.narrower, o, "narrower")
    for pred, label in MAPPING_PREDS.items():
        for s, o in graph.subject_objects(pred):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                add_triple_edge("mapping", s, pred, o, label)

    # object properties (schema-level: single IRI domain + range)
    for p in graph.subjects(RDF.type, OWL.ObjectProperty):
        if not isinstance(p, URIRef):
            continue
        dom = _single_iri(graph, p, RDFS.domain)
        rng = _single_iri(graph, p, RDFS.range)
        if dom is None or rng is None:
            continue                      # complex/absent domain or range -> preserved untouched
        pl_p, pl = _pick_literal(graph, p, [RDFS.label, SKOS.prefLabel])
        dp, dl = _pick_literal(graph, p, [RDFS.comment, SKOS.definition])
        eid = str(p)
        proj.edges[eid] = EdgeProv(
            id=eid, kind="objectProperty", iri=p, name_lit=pl,
            domain_iri=dom, range_iri=rng, desc_pred=dp, desc_lit=dl,
        )
        proj.ontology.relationships.append(Relationship(
            id=eid, name=str(pl) if pl is not None else local_name(str(p)),
            from_=str(dom), to=str(rng), kind="objectProperty",
            description=str(dl) if dl is not None else None,
        ))

    return proj
