"""Merge an edited projection back onto the FULL base graph.

`merge(base, projection, edited)` returns a new graph that is `base` plus exactly the changes
the user made in Playground -- nothing else. It starts from a copy of every base triple and
mutates only the fields the projection surfaced, using the projection's provenance (the exact
literal/IRI each value came from) so unrelated triples -- restrictions, imports, individuals,
untouched annotations -- are preserved verbatim.

The result is intended to be handed to GraphSynchronizer.sync(graph_uri, merged, old_graph=base):
because merged and base differ only in the edited ground triples, the diff is small, ground-only
(no blank nodes are ever touched here), and verifiable.
"""
from __future__ import annotations

import re
from typing import Optional

from rdflib import Graph, RDF, RDFS, OWL, URIRef, Literal
from rdflib.namespace import SKOS

from .model import Ontology, EntityType, Property, Relationship
from .project import (Projection, DPropProv, NodeProv, EdgeProv, PG_TO_XSD, MAPPING_PREDS)

_PRED_BY_LABEL = {v: k for k, v in MAPPING_PREDS.items()}
_SLUG = re.compile(r"[^A-Za-z0-9]+")


def _copy(base: Graph) -> Graph:
    g = Graph()
    for prefix, ns in base.namespaces():
        g.bind(prefix, ns, replace=True)
    for t in base:
        g.add(t)
    return g


def _is_absolute_iri(s: str) -> bool:
    return "://" in s or s.startswith("urn:")


def _mint(node_id: str, base_ns: str) -> URIRef:
    """A stable IRI for a newly-added node/edge: its id if already absolute, else base_ns+slug."""
    if _is_absolute_iri(node_id):
        return URIRef(node_id)
    slug = _SLUG.sub("-", node_id).strip("-") or "unnamed"
    return URIRef(base_ns + slug)


def _name_pred(kind: str) -> URIRef:
    return RDFS.label if kind == "class" else SKOS.prefLabel


def _desc_pred(kind: str) -> URIRef:
    return RDFS.comment if kind == "class" else SKOS.definition


# --------------------------------------------------------------------------- #
# Attribute (datatype property) merge                                          #
# --------------------------------------------------------------------------- #

def _apply_props(g: Graph, owner: URIRef, orig: list[Property], edited: list[Property],
                 prov: Optional[NodeProv], base_ns: str) -> None:
    orig_by = {p.name: p for p in orig}
    edit_by = {p.name: p for p in edited}
    prov_props = prov.props if prov else {}

    for name in edit_by.keys() - orig_by.keys():                 # added
        p = edit_by[name]
        iri = _mint(f"{owner}-{name}", base_ns)
        g.add((iri, RDF.type, OWL.DatatypeProperty))
        g.add((iri, RDFS.domain, owner))
        g.add((iri, RDFS.range, PG_TO_XSD.get(p.type, PG_TO_XSD["string"])))
        g.add((iri, RDFS.label, Literal(name)))
        if p.description:
            g.add((iri, RDFS.comment, Literal(p.description)))

    for name in orig_by.keys() - edit_by.keys():                 # removed (unclassify this attr)
        dp = prov_props.get(name)
        if dp is None:
            continue
        g.remove((dp.iri, RDFS.domain, dp.owner))
        # only strip type/range/label/desc if this was its sole surfaced domain
        if not any(o != dp.owner for o in g.objects(dp.iri, RDFS.domain)):
            g.remove((dp.iri, RDF.type, OWL.DatatypeProperty))
            if dp.range_iri is not None:
                g.remove((dp.iri, RDFS.range, dp.range_iri))
            if dp.name_lit is not None:
                g.remove((dp.iri, RDFS.label, dp.name_lit))
            if dp.desc_lit is not None:
                g.remove((dp.iri, dp.desc_pred, dp.desc_lit))

    for name in edit_by.keys() & orig_by.keys():                 # changed
        dp = prov_props.get(name)
        if dp is None:
            continue
        oe, ne = orig_by[name], edit_by[name]
        if ne.type != oe.type:
            target = PG_TO_XSD.get(ne.type)
            # only rewrite a range that was a known xsd type; preserve non-xsd ranges verbatim
            if dp.range_mapped and target is not None and target != dp.range_iri:
                g.remove((dp.iri, RDFS.range, dp.range_iri))
                g.add((dp.iri, RDFS.range, target))
            elif dp.range_iri is None and target is not None:
                g.add((dp.iri, RDFS.range, target))
        if (ne.description or "") != (oe.description or ""):
            pred = dp.desc_pred or RDFS.comment
            if dp.desc_lit is not None:
                g.remove((dp.iri, dp.desc_pred, dp.desc_lit))
            if ne.description:
                g.add((dp.iri, pred, Literal(ne.description)))


# --------------------------------------------------------------------------- #
# Edge merge                                                                    #
# --------------------------------------------------------------------------- #

def _add_edge(g: Graph, r: Relationship, base_ns: str) -> None:
    frm = URIRef(r.from_)
    to = URIRef(r.to)
    if r.kind == "subClassOf":
        g.add((frm, RDFS.subClassOf, to))
    elif r.kind == "broader":
        g.add((frm, SKOS.broader, to))
    elif r.kind == "narrower":
        g.add((frm, SKOS.narrower, to))
    elif r.kind == "mapping":
        pred = _PRED_BY_LABEL.get(r.name, SKOS.exactMatch)
        g.add((frm, pred, to))
    elif r.kind == "objectProperty":
        iri = _mint(r.id, base_ns)
        g.add((iri, RDF.type, OWL.ObjectProperty))
        g.add((iri, RDFS.domain, frm))
        g.add((iri, RDFS.range, to))
        if r.name:
            g.add((iri, RDFS.label, Literal(r.name)))
        if r.description:
            g.add((iri, RDFS.comment, Literal(r.description)))


def _remove_edge(g: Graph, prov: EdgeProv) -> None:
    if prov.kind == "objectProperty":
        g.remove((prov.iri, RDF.type, OWL.ObjectProperty))
        if prov.domain_iri is not None:
            g.remove((prov.iri, RDFS.domain, prov.domain_iri))
        if prov.range_iri is not None:
            g.remove((prov.iri, RDFS.range, prov.range_iri))
        if prov.name_lit is not None:
            g.remove((prov.iri, RDFS.label, prov.name_lit))
        if prov.desc_lit is not None:
            g.remove((prov.iri, prov.desc_pred, prov.desc_lit))
    else:
        for t in prov.triples:
            g.remove(t)


# --------------------------------------------------------------------------- #
# Top-level merge                                                               #
# --------------------------------------------------------------------------- #

def merge(base: Graph, proj: Projection, edited: Ontology) -> Graph:
    g = _copy(base)

    # -- ontology header ---------------------------------------------------- #
    if proj.ontology_iri:
        ont = URIRef(proj.ontology_iri)
        if edited.name != proj.ontology.name:
            if proj.ont_name_lit is not None:
                g.remove((ont, RDFS.label, proj.ont_name_lit))
            if edited.name:
                g.add((ont, RDFS.label, Literal(edited.name)))
        if (edited.description or "") != (proj.ontology.description or ""):
            pred = proj.ont_desc_pred or RDFS.comment
            if proj.ont_desc_lit is not None:
                g.remove((ont, proj.ont_desc_pred, proj.ont_desc_lit))
            if edited.description:
                g.add((ont, pred, Literal(edited.description)))

    # -- nodes -------------------------------------------------------------- #
    orig_nodes = {et.id: et for et in proj.ontology.entityTypes}
    edit_nodes = {et.id: et for et in edited.entityTypes}

    for nid in edit_nodes.keys() - orig_nodes.keys():            # added
        et = edit_nodes[nid]
        iri = _mint(nid, proj.base_ns)
        kind = et.kind or "class"
        g.add((iri, RDF.type, OWL.Class if kind == "class" else SKOS.Concept))
        if et.name:
            g.add((iri, _name_pred(kind), Literal(et.name)))
        if et.description:
            g.add((iri, _desc_pred(kind), Literal(et.description)))
        _apply_props(g, iri, [], et.properties, None, proj.base_ns)

    for nid in orig_nodes.keys() - edit_nodes.keys():            # removed (unclassify)
        prov = proj.nodes[nid]
        for t in prov.type_triples:
            g.remove(t)
        if prov.name_lit is not None:
            g.remove((prov.iri, prov.name_pred, prov.name_lit))
        if prov.desc_lit is not None:
            g.remove((prov.iri, prov.desc_pred, prov.desc_lit))

    for nid in edit_nodes.keys() & orig_nodes.keys():            # changed
        prov = proj.nodes[nid]
        oet, net = orig_nodes[nid], edit_nodes[nid]
        if net.name != oet.name:
            pred = prov.name_pred or _name_pred(prov.kind)
            if prov.name_lit is not None:
                g.remove((prov.iri, prov.name_pred, prov.name_lit))
            if net.name:
                g.add((prov.iri, pred, Literal(net.name)))
        if (net.description or "") != (oet.description or ""):
            pred = prov.desc_pred or _desc_pred(prov.kind)
            if prov.desc_lit is not None:
                g.remove((prov.iri, prov.desc_pred, prov.desc_lit))
            if net.description:
                g.add((prov.iri, pred, Literal(net.description)))
        _apply_props(g, prov.iri, oet.properties, net.properties, prov, proj.base_ns)

    # -- edges -------------------------------------------------------------- #
    orig_edges = {r.id: r for r in proj.ontology.relationships}
    edit_edges = {r.id: r for r in edited.relationships}

    for eid in edit_edges.keys() - orig_edges.keys():            # added
        _add_edge(g, edit_edges[eid], proj.base_ns)

    for eid in orig_edges.keys() - edit_edges.keys():            # removed
        _remove_edge(g, proj.edges[eid])

    for eid in edit_edges.keys() & orig_edges.keys():            # changed (objectProperty only)
        prov = proj.edges[eid]
        if prov.kind != "objectProperty":
            continue                       # triple edges have endpoint identity: change == re-id
        oe, ne = orig_edges[eid], edit_edges[eid]
        if ne.from_ != oe.from_:
            if prov.domain_iri is not None:
                g.remove((prov.iri, RDFS.domain, prov.domain_iri))
            g.add((prov.iri, RDFS.domain, URIRef(ne.from_)))
        if ne.to != oe.to:
            if prov.range_iri is not None:
                g.remove((prov.iri, RDFS.range, prov.range_iri))
            g.add((prov.iri, RDFS.range, URIRef(ne.to)))
        if ne.name != oe.name:
            if prov.name_lit is not None:
                g.remove((prov.iri, RDFS.label, prov.name_lit))
            if ne.name:
                g.add((prov.iri, RDFS.label, Literal(ne.name)))
        if (ne.description or "") != (oe.description or ""):
            pred = prov.desc_pred or RDFS.comment
            if prov.desc_lit is not None:
                g.remove((prov.iri, prov.desc_pred, prov.desc_lit))
            if ne.description:
                g.add((prov.iri, pred, Literal(ne.description)))

    return g
