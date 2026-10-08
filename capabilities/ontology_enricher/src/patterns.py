"""
Catalog of reasoning patterns for augmenting a local ontology mapped to FIBO
============================================================================
Each *pattern* takes the reasoned graph (FIBO + HBIM-as-OWL + SKOS→OWL bridge,
produced by `OntologyEnricher`) and turns an entailment into an actionable
augmentation of HBIM. Every pattern declares a PERSISTENCE policy:

    MATERIALISE -> sound entailment, written straight into `hbim_derived.ttl`
    PROPOSE     -> a change needing steward review, written to `hbim_candidates.ttl`
    REPORT      -> surfaced in the report only (e.g. validation findings)

Patterns
--------
    P1  ancestry_derivation          MATERIALISE   inheritance hierarchy → FIBO
    P2  correct_parent_existing      PROPOSE       tighter/right parent for HBIM concepts
    P3  missing_intermediate_concepts PROPOSE      concepts FIBO has between mapped ones
    P4  missing_narrower_concepts     PROPOSE      FIBO subclasses HBIM doesn't cover
    P5  missing_object_properties      PROPOSE     relationships FIBO attaches to mapped classes
    P6  missing_data_properties        PROPOSE     attributes FIBO attaches to mapped classes
    P7  parent_assignment_candidates   PROPOSE     where each discovered concept should sit
    P8  parent_validation              REPORT      disjointness rejects impossible parents
"""
from __future__ import annotations

import networkx as nx
from rdflib import Graph, Literal, RDF, RDFS, OWL, URIRef, BNode
from rdflib.namespace import SKOS, XSD

from common import (HBIM, bind_all, is_fibo, is_hbim)
from enricher import q

CATALOG = [
    ("P1", "ancestry_derivation", "MATERIALISE",
     "Derive the full FIBO inheritance chain for every mapped HBIM concept."),
    ("P2", "correct_parent_existing", "PROPOSE",
     "Use FIBO to find the correct (most specific) parent for existing HBIM concepts."),
    ("P3", "missing_intermediate_concepts", "PROPOSE",
     "Surface FIBO classes that sit between mapped HBIM concepts but have no HBIM twin."),
    ("P4", "missing_narrower_concepts", "PROPOSE",
     "Surface FIBO subclasses of mapped concepts that HBIM does not cover."),
    ("P5", "missing_object_properties", "PROPOSE",
     "Surface object properties (relationships) FIBO attaches to mapped classes."),
    ("P6", "missing_data_properties", "PROPOSE",
     "Surface datatype properties (attributes) FIBO attaches to mapped classes."),
    ("P7", "parent_assignment_candidates", "PROPOSE",
     "Assign each discovered concept its correct HBIM parent / re-parent existing ones."),
    ("P8", "parent_validation", "REPORT",
     "Use FIBO disjointness to reject impossible parent assignments."),
]


def localname(uri) -> str:
    return str(uri).rsplit("/", 1)[-1].rsplit("#", 1)[-1]


class ReasoningPatternCatalog:
    def __init__(self, enricher):
        self.e = enricher
        self._prep()

    # -- precompute shared structures -------------------------------------
    def _prep(self):
        e = self.e
        self.concepts = e.hbim_concepts()

        # FIBO named-class taxonomy as a DAG (child -> parent), asserted subclass
        self.dag = nx.DiGraph()
        for s, o in e.fibo.subject_objects(RDFS.subClassOf):
            if isinstance(s, URIRef) and isinstance(o, URIRef):
                self.dag.add_edge(str(s), str(o))
        self.fibo_classes = {str(c) for c in e.fibo.subjects(RDF.type, OWL.Class)
                             if isinstance(c, URIRef)}

        # HBIM concept  <->  FIBO class, split by mapping strength
        self.covered = {}          # FIBO class (str) -> HBIM concept  (exact/close = "same level")
        self.broadened = {}        # HBIM concept -> FIBO class it is *narrower* than (broadMatch)
        for prop in (SKOS.exactMatch, SKOS.closeMatch):
            for hb, fb in e.maps.subject_objects(prop):
                if is_fibo(fb):
                    self.covered[str(fb)] = hb
        for hb, fb in e.maps.subject_objects(SKOS.broadMatch):
            if is_fibo(fb):
                self.broadened[str(hb)] = str(fb)
        # concept -> its FIBO anchor (the class that defines "what it is")
        self.anchor = {}
        for prop in (SKOS.exactMatch, SKOS.closeMatch):
            for hb, fb in e.maps.subject_objects(prop):
                self.anchor[str(hb)] = str(fb)

    # -- taxonomy helpers --------------------------------------------------
    def onto_ancestors(self, u):   # FIBO superclasses of u
        return set(nx.descendants(self.dag, u)) if u in self.dag else set()

    def onto_descendants(self, u):  # FIBO subclasses of u
        return set(nx.ancestors(self.dag, u)) if u in self.dag else set()

    def nearest_in(self, u, universe):
        """Closest members of `universe` among u's FIBO ancestors."""
        anc = self.onto_ancestors(u) & universe
        return {a for a in anc if not (self.onto_descendants(a) & anc)}

    def ql(self, uri):
        return q(self.e.inferred, URIRef(uri) if isinstance(uri, str) else uri)

    # ========================================================================
    # P1  ancestry derivation  (MATERIALISE)
    # ========================================================================
    def p1_ancestry_derivation(self):
        rows = []
        for c in self.concepts:
            anc = sorted({s for s in self.e.inferred.objects(c, RDFS.subClassOf)
                          if is_fibo(s) and s != c}, key=str)
            equ = sorted({s for s in self.e.inferred.objects(c, OWL.equivalentClass)
                          if is_fibo(s)}, key=str)
            if anc or equ:
                rows.append({"concept": q(self.e.inferred, c),
                             "equivalent_to": [self.ql(x) for x in equ],
                             "derived_ancestors": [self.ql(x) for x in anc]})
        return rows

    # ========================================================================
    # missing-concept discovery (shared computation for P3/P4/P7)
    # ========================================================================
    def _missing_concepts(self):
        covered = set(self.covered)
        missing = {}
        for u in self.fibo_classes - covered:
            up = bool(self.onto_descendants(u) & covered)     # u is ABOVE some covered class
            down = bool(self.onto_ancestors(u) & covered)     # u is BELOW some covered class
            broad_target = u in set(self.broadened.values())
            if not (up or down or broad_target):
                continue
            category = ("intermediate" if (up and down)
                        else "ancestor" if up else "narrower")
            missing[u] = {"category": category}
        # object-property value types that are uncovered FIBO classes are also
        # concepts HBIM lacks (referenced only through a relationship).
        for _cl, _p, filler, kind in self._declared_properties():
            fs = str(filler)
            if kind == "object" and fs in self.fibo_classes and fs not in covered and fs not in missing:
                missing[fs] = {"category": "referenced"}
        return missing

    def p3_missing_intermediate_concepts(self):
        m = self._missing_concepts()
        return [self._concept_row(u, info) for u, info in sorted(m.items())
                if info["category"] in ("intermediate", "ancestor")]

    def p4_missing_narrower_concepts(self):
        m = self._missing_concepts()
        return [self._concept_row(u, info) for u, info in sorted(m.items())
                if info["category"] in ("narrower", "referenced")]

    def _concept_row(self, u, info):
        return {"fibo_class": self.ql(u), "category": info["category"],
                "label": str(self.e.fibo.value(URIRef(u), RDFS.label) or localname(u)),
                "suggested_hbim_concept": f"hbim:{localname(u)}",
                "suggested_parent": self._placement(u)[1]}

    # ========================================================================
    # P2 correct parent (existing)  &  P7 parent assignment (discovered)
    # ========================================================================
    def _placement(self, u):
        """(parent_node_uri_or_None, parent_qname) for a FIBO class u, using the
        nearest ancestor that will exist in HBIM (covered OR another missing)."""
        universe = set(self.covered) | set(self._missing_concepts())
        near = self.nearest_in(u, universe)
        if not near:
            return None, "hbim:BusinessAsset"
        pick = sorted(near)[0]
        if pick in self.covered:
            return self.covered[pick], q(self.e.inferred, self.covered[pick])
        return URIRef(f"{HBIM}{localname(pick)}"), f"hbim:{localname(pick)}"

    def p2_correct_parent_existing(self):
        rows = []
        for c in self.concepts:
            cs = str(c)
            anchor = self.anchor.get(cs) or self.broadened.get(cs)
            if not anchor:
                continue
            # FIBO says the direct parent(s) of the anchor / of c
            if cs in self.broadened:       # c is narrower than the broadMatch target
                fibo_parents = {self.broadened[cs]}
            else:
                fibo_parents = set(self.dag.successors(anchor)) if anchor in self.dag else set()
            if not fibo_parents:
                continue
            recommended = []
            for fp in sorted(fibo_parents):
                if fp in self.covered:
                    recommended.append(q(self.e.inferred, self.covered[fp]))
                else:
                    recommended.append(f"hbim:{localname(fp)} (propose)")
            current = [q(self.e.hbim, p) for p in self.e.hbim.objects(c, SKOS.broader)]
            changed = set(r.replace(" (propose)", "") for r in recommended) != set(current)
            if changed:
                rows.append({"concept": q(self.e.inferred, c),
                             "current_parent": current or ["(none)"],
                             "fibo_correct_parent": recommended})
        return rows

    def p7_parent_assignment_candidates(self):
        m = self._missing_concepts()
        rows = []
        for u, info in sorted(m.items()):
            _, parent_q = self._placement(u)
            children = []
            # existing covered concepts whose nearest existing-ancestor is u -> re-parent
            for fb, hb in self.covered.items():
                if u in self.nearest_in(fb, set(self.covered) | set(m)):
                    children.append(q(self.e.inferred, hb))
            rows.append({"new_concept": f"hbim:{localname(u)}",
                         "assign_parent": parent_q,
                         "reparent_children": sorted(children)})
        return rows

    # ========================================================================
    # P5 / P6  property discovery
    # ========================================================================
    def _kind(self, prop, filler):
        if (URIRef(str(prop)), RDF.type, OWL.DatatypeProperty) in self.e.fibo:
            return "data"
        return "data" if str(filler).startswith(str(XSD)) else "object"

    def _declared_properties(self):
        """(declaring_fibo_class, property, value_type, kind) for properties FIBO
        attaches to a class via a someValuesFrom restriction or via rdfs:domain."""
        e = self.e
        out = []
        for cl in self.fibo_classes:
            for r in e.fibo.objects(URIRef(cl), RDFS.subClassOf):
                if isinstance(r, BNode) and (r, RDF.type, OWL.Restriction) in e.fibo:
                    p = e.fibo.value(r, OWL.onProperty)
                    f = e.fibo.value(r, OWL.someValuesFrom)
                    if p is not None and f is not None:
                        out.append((cl, str(p), f, self._kind(p, f)))
        for p in set(e.fibo.subjects(RDFS.domain, None)):
            dom = e.fibo.value(p, RDFS.domain)
            rng = e.fibo.value(p, RDFS.range)
            if dom is not None and rng is not None and str(dom) in self.fibo_classes:
                out.append((str(dom), str(p), rng, self._kind(p, rng)))
        return out

    def _owner(self, fibo_cls):
        """HBIM concept that owns a FIBO class: the mapped concept, else the
        candidate concept if the class is itself missing."""
        if fibo_cls in self.covered:
            return self.covered[fibo_cls]
        if fibo_cls in self._missing_concepts():
            return URIRef(f"{HBIM}{localname(fibo_cls)}")
        return None

    def _property_rows(self, kind):
        # attach each property once, to the most general class that declares it
        chosen = {}
        for cl, p, filler, k in self._declared_properties():
            if k != kind or self._owner(cl) is None:
                continue
            if p not in chosen or cl in self.onto_ancestors(chosen[p][2]):
                chosen[p] = (self._owner(cl), filler, cl)
        return [{"hbim_concept": q(self.e.inferred, owner),
                 "missing_property": q(self.e.inferred, URIRef(p)),
                 "value_type": q(self.e.inferred, filler)}
                for p, (owner, filler, _cl) in sorted(chosen.items())]

    def p5_missing_object_properties(self):
        return self._property_rows("object")

    def p6_missing_data_properties(self):
        return self._property_rows("data")

    # ========================================================================
    # P8  validation
    # ========================================================================
    def p8_parent_validation(self):
        return self.e.validate_with_disjointness()

    # ========================================================================
    # persistence
    # ========================================================================
    def persist_derivations(self) -> Graph:
        """MATERIALISE P1: sound ancestry written back into HBIM."""
        g = bind_all(Graph()); g.bind("skos", SKOS)
        for c in self.concepts:
            for anc in self.e.inferred.objects(c, RDFS.subClassOf):
                if is_fibo(anc) and anc != c:
                    g.add((c, RDFS.subClassOf, anc))
                    g.add((c, SKOS.broaderTransitive, anc))
        return g

    def persist_candidates(self) -> Graph:
        """PROPOSE P3–P7: new concepts, parents, re-parenting, properties."""
        g = bind_all(Graph()); g.bind("skos", SKOS)
        SUGG = HBIM.suggestedBroader
        g.add((SUGG, RDF.type, OWL.AnnotationProperty))
        g.add((SUGG, RDFS.label, Literal("suggested broader (auto-proposed)")))

        missing = self._missing_concepts()
        # new concepts + placement
        for u, info in missing.items():
            new = HBIM[localname(u)]
            g.add((new, RDF.type, SKOS.Concept))
            g.add((new, RDF.type, OWL.Class))
            lbl = self.e.fibo.value(URIRef(u), RDFS.label)
            if lbl:
                g.add((new, SKOS.prefLabel, Literal(str(lbl), lang="en")))
            defn = self.e.fibo.value(URIRef(u), SKOS.definition)
            if defn:
                g.add((new, SKOS.definition, Literal(str(defn), lang="en")))
            g.add((new, SKOS.closeMatch, URIRef(u)))
            g.add((new, SKOS.editorialNote,
                   Literal(f"Candidate concept proposed from FIBO {self.ql(u)} "
                           f"(category: {info['category']}).", lang="en")))
            parent_uri, _ = self._placement(u)
            if parent_uri is not None:
                g.add((new, SKOS.broader, parent_uri))
            else:
                g.add((new, SKOS.broader, HBIM.BusinessAsset))
        # re-parent existing concepts under a nearer (new or covered) parent
        for row in self.p2_correct_parent_existing():
            c = self._concept_uri(row["concept"])
            for rp in row["fibo_correct_parent"]:
                name = rp.replace(" (propose)", "").split(":", 1)[-1]
                g.add((c, SUGG, HBIM[name]))
        # properties (object + data) as proposed owl properties on HBIM concepts
        for kind, ptype in (("object", OWL.ObjectProperty), ("data", OWL.DatatypeProperty)):
            for r in self._property_rows(kind):
                p = self._resolve_q(r["missing_property"])
                c = self._concept_uri(r["hbim_concept"])
                if p is None:
                    continue
                g.add((p, RDF.type, ptype))
                g.add((p, RDFS.domain, c))
                rng = self._resolve_q(r["value_type"])
                if rng is not None:
                    g.add((p, RDFS.range, rng))
                g.add((p, RDFS.comment,
                       Literal(f"Proposed for {r['hbim_concept']} from FIBO restriction/domain.",
                               lang="en")))
        return g

    # -- tiny resolvers ----------------------------------------------------
    def _concept_uri(self, qname):
        return self._resolve_q(qname)

    def _resolve_q(self, qname):
        if not qname or ":" not in qname:
            return None
        qname = qname.replace(" (propose)", "")
        pfx, local = qname.split(":", 1)
        ns = dict(self.e.inferred.namespaces()).get(pfx)
        return URIRef(str(ns) + local) if ns else None
