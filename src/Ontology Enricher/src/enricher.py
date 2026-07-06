"""
Ontology Enricher -- core engine
================================
Enrich the HBIM business-assets taxonomy with FIBO by:

  1. LIFT     : turn the SKOS taxonomy into OWL classes (skos:broader -> rdfs:subClassOf)
  2. BRIDGE   : turn SKOS mapping properties into OWL axioms
                (exactMatch -> equivalentClass, close/broad/narrowMatch -> subClassOf)
  3. REASON   : run an OWL RL reasoner over FIBO + HBIM-as-OWL + bridge axioms
  4. ENRICH   : read the inferred closure and derive concrete HBIM enrichments
                (subsumption, relationships, annotations, instance types, validation)

The same merged graph produced here (FIBO + HBIM-as-OWL + bridge) is what gets
written for Protege, so a DL reasoner (HermiT/ELK) reproduces these inferences.
"""
from __future__ import annotations

from rdflib import Graph, RDF, RDFS, OWL, URIRef, BNode, Literal
from rdflib.namespace import SKOS
from owlrl import DeductiveClosure, OWLRL_Semantics

from common import (DATA, FIBO, MAPPINGS, HBIM, CAA, REL, CMNS_ID,
                    bind_all, is_fibo, is_hbim)

# How each SKOS mapping property is bridged to OWL for reasoning.
#   value = (edge, direction)  where direction 'h2f' = HBIM subClassOf FIBO
BRIDGE_RULES = {
    SKOS.exactMatch:  ("equivalent", None),
    SKOS.closeMatch:  ("subclass", "h2f"),
    SKOS.broadMatch:  ("subclass", "h2f"),   # FIBO is broader -> HBIM ⊑ FIBO
    SKOS.narrowMatch: ("subclass", "f2h"),   # FIBO is narrower -> FIBO ⊑ HBIM
    # skos:relatedMatch -> intentionally NOT bridged (kept as annotation only)
}


def q(g: Graph, node) -> str:
    try:
        return g.qname(node)
    except Exception:  # noqa: BLE001
        return str(node)


class OntologyEnricher:
    def __init__(self, data=DATA, fibo=FIBO, mappings=MAPPINGS):
        self.hbim = bind_all(Graph()).parse(data, format="turtle")
        self.fibo = bind_all(Graph()).parse(fibo, format="turtle")
        self.maps = bind_all(Graph()).parse(mappings, format="turtle")
        self.hbim_owl = None      # OWL lift of the taxonomy
        self.bridge = None        # OWL bridge axioms from SKOS mappings
        self.asserted = None      # merged graph (reasoning + Protege input)
        self.inferred = None      # deductive closure
        self.new = None           # inferred - asserted
        self.bridge_log: list[dict] = []

    # -- concept discovery -------------------------------------------------
    def hbim_concepts(self) -> list[URIRef]:
        return sorted({s for s in self.hbim.subjects(RDF.type, SKOS.Concept)}, key=str)

    def hbim_individuals(self) -> list[URIRef]:
        concepts = set(self.hbim_concepts())
        inds = set()
        for s, _, o in self.hbim.triples((None, RDF.type, None)):
            if is_hbim(o) and o in concepts and s not in concepts:
                inds.add(s)
        return sorted(inds, key=str)

    # -- STEP 1: SKOS -> OWL lift ------------------------------------------
    def lift_skos_to_owl(self) -> Graph:
        g = bind_all(Graph())
        g.bind("skos", SKOS)
        for c in self.hbim_concepts():
            g.add((c, RDF.type, OWL.Class))
            for parent in self.hbim.objects(c, SKOS.broader):
                g.add((c, RDFS.subClassOf, parent))   # taxonomy -> class hierarchy
        # keep instance typings (already rdf:type hbim:Concept)
        for ind in self.hbim_individuals():
            for t in self.hbim.objects(ind, RDF.type):
                g.add((ind, RDF.type, t))
        self.hbim_owl = g
        return g

    # -- STEP 2: SKOS mappings -> OWL bridge -------------------------------
    def build_bridge(self) -> Graph:
        g = bind_all(Graph())
        for prop, (kind, direction) in BRIDGE_RULES.items():
            for hb, fb in self.maps.subject_objects(prop):
                if kind == "equivalent":
                    g.add((hb, OWL.equivalentClass, fb))
                    axiom = f"{q(self.maps, hb)} owl:equivalentClass {q(self.maps, fb)}"
                elif direction == "h2f":
                    g.add((hb, RDFS.subClassOf, fb))
                    axiom = f"{q(self.maps, hb)} rdfs:subClassOf {q(self.maps, fb)}"
                else:  # f2h
                    g.add((fb, RDFS.subClassOf, hb))
                    axiom = f"{q(self.maps, fb)} rdfs:subClassOf {q(self.maps, hb)}"
                self.bridge_log.append({
                    "mapping": q(self.maps, prop), "hbim": q(self.maps, hb),
                    "fibo": q(self.maps, fb), "owl_axiom": axiom})
        # related matches are recorded but NOT bridged
        for hb, fb in self.maps.subject_objects(SKOS.relatedMatch):
            self.bridge_log.append({
                "mapping": "skos:relatedMatch", "hbim": q(self.maps, hb),
                "fibo": q(self.maps, fb), "owl_axiom": "(none - annotation only)"})
        self.bridge = g
        return g

    # -- assemble + STEP 3: reason ----------------------------------------
    def assemble(self) -> Graph:
        if self.hbim_owl is None:
            self.lift_skos_to_owl()
        if self.bridge is None:
            self.build_bridge()
        g = bind_all(Graph())
        g.bind("skos", SKOS)
        for src in (self.fibo, self.hbim, self.hbim_owl, self.bridge, self.maps):
            g += src
        self.asserted = g
        return g

    def reason(self):
        if self.asserted is None:
            self.assemble()
        inferred = Graph()
        for t in self.asserted:
            inferred.add(t)
        DeductiveClosure(OWLRL_Semantics).expand(inferred)
        bind_all(inferred)
        inferred.bind("skos", SKOS)
        self.inferred = inferred
        self.new = inferred - self.asserted
        return inferred, self.new

    # -- STEP 4a: subsumption enrichment ----------------------------------
    def enrich_subsumption(self) -> dict:
        out = {}
        for c in self.hbim_concepts():
            equiv_nodes = {e for e in self.inferred.objects(c, OWL.equivalentClass) if is_fibo(e)}
            equivalents = [q(self.inferred, e) for e in equiv_nodes]
            mapped, inferred_supers = [], []
            for s in self.inferred.objects(c, RDFS.subClassOf):
                if not is_fibo(s) or s == c or s in equiv_nodes:
                    continue  # don't repeat an equivalent class as a superclass
                if (c, RDFS.subClassOf, s) in self.new:
                    inferred_supers.append(q(self.inferred, s))
                else:
                    mapped.append(q(self.inferred, s))
            if mapped or inferred_supers or equivalents:
                out[q(self.inferred, c)] = {
                    "equivalentTo": sorted(set(equivalents)),
                    "mapped_parent": sorted(set(mapped)),
                    "inferred_ancestors": sorted(set(inferred_supers)),
                }
        return out

    # -- STEP 4b: instance-level enrichment -------------------------------
    def enrich_instances(self) -> dict:
        out = {}
        for ind in self.hbim_individuals():
            types = sorted({q(self.inferred, t) for t in self.inferred.objects(ind, RDF.type)
                            if is_fibo(t)})
            new_types = sorted({q(self.inferred, t) for t in self.inferred.objects(ind, RDF.type)
                                if is_fibo(t) and (ind, RDF.type, t) in self.new})
            if types:
                out[q(self.inferred, ind)] = {"inferred_fibo_types": types,
                                              "newly_inferred": new_types}
        return out

    # -- STEP 4c: relationship (property) enrichment ----------------------
    def enrich_relationships(self, concept: URIRef) -> list[dict]:
        supers = set(self.inferred.objects(concept, RDFS.subClassOf)) | {concept}
        found = {}
        for sup in supers:
            for r in self.inferred.objects(sup, RDFS.subClassOf):
                if (r, RDF.type, OWL.Restriction) in self.inferred:
                    prop = next(self.inferred.objects(r, OWL.onProperty), None)
                    filler = next(self.inferred.objects(r, OWL.someValuesFrom), None)
                    if prop is not None and filler is not None and is_fibo(filler):
                        if prop not in found or not is_hbim(filler):
                            found[prop] = filler
        return [{"property": q(self.inferred, p), "value_type": q(self.inferred, f)}
                for p, f in sorted(found.items(), key=lambda kv: str(kv[0]))]

    # -- STEP 4d: annotation enrichment (copy FIBO definitions) -----------
    def enrich_annotations(self) -> list[dict]:
        out = []
        for c in self.hbim_concepts():
            if next(self.hbim.objects(c, SKOS.definition), None) is not None:
                continue  # already has a definition
            # find the FIBO class this concept is mapped to
            target = None
            for prop in (SKOS.exactMatch, SKOS.closeMatch, SKOS.broadMatch):
                target = next(self.maps.objects(c, prop), None)
                if target is not None:
                    break
            if target is None:
                continue
            definition = next(self.fibo.objects(target, SKOS.definition), None)
            if definition is not None:
                out.append({"concept": q(self.inferred, c),
                            "source": q(self.inferred, target),
                            "definition": str(definition)})
        return out

    # -- STEP 4e: consistency validation (FIBO catches HBIM errors) -------
    def validate_with_disjointness(self) -> list[dict]:
        """Inject a plausible modelling error and show FIBO disjointness rejects it."""
        bad = Graph()
        for t in self.asserted:
            bad.add(t)
        bind_all(bad)
        # ERROR: map the (transactional) Current Account also to a
        # NON-transaction deposit account -> disjoint with its real parent.
        bad.add((HBIM.CurrentAccount, RDFS.subClassOf, CAA.NonTransactionDepositAccount))
        DeductiveClosure(OWLRL_Semantics).expand(bad)

        clashes, pairs = [], {frozenset(p) for p in bad.subject_objects(OWL.disjointWith)}
        for pair in pairs:
            a, b = tuple(pair)
            ma = set(bad.subjects(RDF.type, a)) | set(bad.subjects(RDFS.subClassOf, a))
            mb = set(bad.subjects(RDF.type, b)) | set(bad.subjects(RDFS.subClassOf, b))
            for n in (ma & mb):
                if n in (a, b) or n == OWL.Nothing or isinstance(n, BNode):
                    continue
                clashes.append({"offending": q(bad, n),
                                "disjoint_a": q(bad, a), "disjoint_b": q(bad, b)})
        return clashes

    # -- write-back: the ENRICHED HBIM ------------------------------------
    def build_enriched_hbim(self, subsumption: dict, annotations: list[dict]) -> Graph:
        """Original HBIM + materialised enrichments (the deliverable taxonomy)."""
        g = bind_all(Graph())
        g.bind("skos", SKOS)
        g += self.hbim
        g += self.maps                      # carry the alignment with the taxonomy
        # 1. materialise inferred FIBO ancestry as rdfs:subClassOf + skos:broadMatch
        for c in self.hbim_concepts():
            key = q(self.inferred, c)
            info = subsumption.get(key)
            if not info:
                continue
            for anc_q in info["inferred_ancestors"]:
                anc = self._resolve(anc_q)
                if anc is not None:
                    g.add((c, RDFS.subClassOf, anc))
                    g.add((c, SKOS.broadMatch, anc))
        # 2. copy FIBO definitions where HBIM lacked them
        for rec in annotations:
            c = self._resolve(rec["concept"])
            g.add((c, SKOS.definition, Literal(rec["definition"], lang="en")))
            g.add((c, SKOS.editorialNote,
                   Literal(f"Definition enriched from FIBO {rec['source']}.", lang="en")))
        return g

    def _resolve(self, qname: str):
        if ":" not in qname:
            return None
        pfx, local = qname.split(":", 1)
        ns = dict(self.inferred.namespaces()).get(pfx)
        return URIRef(str(ns) + local) if ns else None
