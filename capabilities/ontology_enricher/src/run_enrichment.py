"""
Ontology Enricher -- end-to-end driver
======================================
Runs the whole FIBO -> HBIM enrichment pipeline and prints a scenario-by-scenario
report, then writes the artifacts (enriched HBIM + Protege-ready OWL + closure).

    python run_enrichment.py
"""
import json
from rdflib import RDFS, OWL
from rdflib.namespace import SKOS

from common import (HBIM, HBIM_ENRICHED, PROTEGE_TTL, PROTEGE_RDF,
                    INFERRED_TTL, REPORT_JSON)
from enricher import OntologyEnricher, q


def rule(title, ch="="):
    print("\n" + ch * 78)
    print(title)
    print(ch * 78)


def main():
    e = OntologyEnricher()
    e.lift_skos_to_owl()
    e.build_bridge()
    e.assemble()
    e.reason()

    rule("ONTOLOGY ENRICHER  ·  FIBO  ->  HBIM (business assets)")
    print(f"HBIM concepts        : {len(e.hbim_concepts())}")
    print(f"HBIM instances       : {len(e.hbim_individuals())}")
    print(f"Asserted triples     : {len(e.asserted)}")
    print(f"After FIBO reasoning : {len(e.inferred)}  (+{len(e.new)} inferred)")

    # ---- Scenario 1: taxonomy -> ontology lift --------------------------
    rule("SCENARIO 1 · Lift the SKOS taxonomy to OWL (skos:broader -> rdfs:subClassOf)")
    print(f"Lifted {len(e.hbim_concepts())} skos:Concept -> owl:Class, "
          f"{len(list(e.hbim_owl.triples((None, RDFS.subClassOf, None))))} subclass axioms.")
    for c in e.hbim_concepts():
        parents = [q(e.hbim, p) for p in e.hbim.objects(c, SKOS.broader)]
        if parents:
            print(f"   {q(e.hbim, c):<22} ⊑ {', '.join(parents)}")

    # ---- Scenario 2: SKOS mapping -> OWL bridge -------------------------
    rule("SCENARIO 2 · Map HBIM -> FIBO with SKOS, bridge to OWL for reasoning")
    print(f"{'mapping':<18}{'HBIM':<24}{'FIBO':<28}{'OWL axiom'}")
    print("-" * 108)
    for b in e.bridge_log:
        print(f"{b['mapping']:<18}{b['hbim']:<24}{b['fibo']:<28}{b['owl_axiom']}")

    # ---- Scenario 3: subsumption enrichment -----------------------------
    rule("SCENARIO 3 · Subsumption enrichment (new FIBO ancestry inferred for HBIM)")
    subsumption = e.enrich_subsumption()
    for concept, info in subsumption.items():
        print(f"\n  {concept}")
        if info["equivalentTo"]:
            print(f"      ≡ (exact)   {', '.join(info['equivalentTo'])}")
        if info["mapped_parent"]:
            print(f"      ⊑ (mapped)  {', '.join(info['mapped_parent'])}")
        if info["inferred_ancestors"]:
            print(f"      ⊑ (INFERRED) {', '.join(info['inferred_ancestors'])}")

    # ---- Scenario 4: relationship (property) enrichment -----------------
    rule("SCENARIO 4 · Relationship enrichment (FIBO restrictions inherited by HBIM)")
    for concept in (HBIM.FinancialAccount, HBIM.CurrentAccount, HBIM.SavingsAccount):
        rels = e.enrich_relationships(concept)
        if rels:
            print(f"\n  {q(e.inferred, concept)} — every instance must be linked via:")
            for r in rels:
                print(f"      {r['property']:<26} -> some {r['value_type']}")
    print("\n  => these become HBIM relationship attributes / data-quality rules.")

    # ---- Scenario 5: annotation enrichment ------------------------------
    rule("SCENARIO 5 · Annotation enrichment (copy real FIBO definitions into HBIM)")
    annotations = e.enrich_annotations()
    for a in annotations:
        print(f"\n  {a['concept']}  (was undefined)")
        print(f"      <- {a['source']}")
        print(f"      \"{a['definition'][:90]}{'…' if len(a['definition']) > 90 else ''}\"")

    # ---- Scenario 6: instance classification ----------------------------
    rule("SCENARIO 6 · Instance classification (a real account reclassified via FIBO)")
    instances = e.enrich_instances()
    for ind, info in instances.items():
        print(f"\n  {ind}")
        for t in info["inferred_fibo_types"]:
            tag = "NEW" if t in info["newly_inferred"] else "   "
            print(f"      [{tag}] a {t}")

    # ---- Scenario 7: consistency validation -----------------------------
    rule("SCENARIO 7 · Validation — FIBO disjointness catches an HBIM mapping error")
    clashes = e.validate_with_disjointness()
    print("Injected error: hbim:CurrentAccount ⊑ caa:NonTransactionDepositAccount")
    if clashes:
        print("[INCONSISTENT] FIBO reasoning rejected it:")
        for c in clashes:
            print(f"   {c['offending']} forced into disjoint "
                  f"{c['disjoint_a']} & {c['disjoint_b']}")
        print("=> A current account is transactional; the bad mapping is caught automatically.")

    # ---- write artifacts -------------------------------------------------
    rule("ARTIFACTS")
    enriched = e.build_enriched_hbim(subsumption, annotations)
    enriched.serialize(destination=HBIM_ENRICHED, format="turtle")
    print(f"[written] {HBIM_ENRICHED}   (enriched HBIM taxonomy)")

    e.asserted.serialize(destination=PROTEGE_TTL, format="turtle")
    e.asserted.serialize(destination=PROTEGE_RDF, format="xml")
    print(f"[written] {PROTEGE_TTL}   (open in Protege, run HermiT/ELK)")
    print(f"[written] {PROTEGE_RDF}   (RDF/XML for Protege)")

    e.inferred.serialize(destination=INFERRED_TTL, format="turtle")
    print(f"[written] {INFERRED_TTL}   (full deductive closure)")

    report = {
        "counts": {"concepts": len(e.hbim_concepts()),
                   "asserted": len(e.asserted), "inferred": len(e.inferred),
                   "new_triples": len(e.new)},
        "bridge": e.bridge_log,
        "subsumption": subsumption,
        "annotations": annotations,
        "instances": instances,
        "validation_clashes": clashes,
    }
    with open(REPORT_JSON, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"[written] {REPORT_JSON}   (machine-readable enrichment report)")


if __name__ == "__main__":
    main()
