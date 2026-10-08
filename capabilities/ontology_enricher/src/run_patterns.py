"""
Reasoning-pattern catalog -- end-to-end driver
==============================================
Loads HBIM + FIBO (+ coverage supplement), maps & reasons, then runs every
pattern in the catalog and reports how each augments HBIM. Persists:

    output/hbim_derived.ttl      MATERIALISED sound entailments (ancestry)
    output/hbim_candidates.ttl   PROPOSED concepts / parents / properties
    output/reasoning_patterns_report.json

    python run_patterns.py
"""
import json
from common import (FIBO_SUPPLEMENT, HBIM_DERIVED, HBIM_CANDIDATES, PATTERNS_REPORT)
from enricher import OntologyEnricher
from patterns import ReasoningPatternCatalog, CATALOG


def rule(t, ch="="):
    print("\n" + ch * 82); print(t); print(ch * 82)


def main():
    e = OntologyEnricher()
    e.fibo.parse(FIBO_SUPPLEMENT, format="turtle")     # extra FIBO coverage
    e.lift_skos_to_owl(); e.build_bridge(); e.assemble(); e.reason()
    cat = ReasoningPatternCatalog(e)

    rule("REASONING-PATTERN CATALOG  ·  augmenting HBIM from FIBO")
    print(f"HBIM concepts {len(cat.concepts)} | FIBO classes {len(cat.fibo_classes)} | "
          f"covered by mapping {len(cat.covered)} | asserted {len(e.asserted)} "
          f"-> inferred {len(e.inferred)}")
    print("\nPatterns:")
    for pid, name, pers, intent in CATALOG:
        print(f"  {pid}  [{pers:<11}] {name:<30} {intent}")

    # ---- P1 ancestry derivation (MATERIALISE) ---------------------------
    rule("P1 · ancestry_derivation  [MATERIALISE]  — inheritance hierarchy from FIBO")
    p1 = cat.p1_ancestry_derivation()
    for r in p1:
        line = ", ".join(r["derived_ancestors"]) or "(none)"
        eq = f"  ≡ {', '.join(r['equivalent_to'])}" if r["equivalent_to"] else ""
        print(f"  {r['concept']:<24}{eq}\n      ⊑* {line}")

    # ---- P2 correct parent (existing) -----------------------------------
    rule("P2 · correct_parent_existing  [PROPOSE]  — right parent for HBIM concepts")
    p2 = cat.p2_correct_parent_existing()
    for r in p2:
        print(f"  {r['concept']:<24} current {r['current_parent']}  "
              f"-> FIBO says {r['fibo_correct_parent']}")
    if not p2:
        print("  (all current parents already agree with FIBO)")

    # ---- P3 missing intermediate / ancestor concepts --------------------
    rule("P3 · missing_intermediate_concepts  [PROPOSE]  — concepts HBIM is missing")
    for r in cat.p3_missing_intermediate_concepts():
        print(f"  + {r['suggested_hbim_concept']:<28} ({r['category']}, ≈ {r['fibo_class']})"
              f"  parent -> {r['suggested_parent']}")

    # ---- P4 missing narrower concepts -----------------------------------
    rule("P4 · missing_narrower_concepts  [PROPOSE]  — uncovered FIBO subclasses")
    for r in cat.p4_missing_narrower_concepts():
        print(f"  + {r['suggested_hbim_concept']:<28} (≈ {r['fibo_class']})"
              f"  parent -> {r['suggested_parent']}")

    # ---- P5 missing object properties -----------------------------------
    rule("P5 · missing_object_properties  [PROPOSE]  — relationships from FIBO")
    for r in cat.p5_missing_object_properties():
        print(f"  {r['hbim_concept']:<24} needs  {r['missing_property']:<26} -> some {r['value_type']}")

    # ---- P6 missing data properties -------------------------------------
    rule("P6 · missing_data_properties  [PROPOSE]  — attributes from FIBO")
    p6 = cat.p6_missing_data_properties()
    for r in p6:
        print(f"  {r['hbim_concept']:<24} needs  {r['missing_property']:<26} : {r['value_type']}")
    if not p6:
        print("  (none in this FIBO subset)")

    # ---- P7 parent assignment for discovered concepts -------------------
    rule("P7 · parent_assignment_candidates  [PROPOSE]  — where discovered concepts sit")
    for r in cat.p7_parent_assignment_candidates():
        kids = f"  re-parent: {', '.join(r['reparent_children'])}" if r["reparent_children"] else ""
        print(f"  {r['new_concept']:<28} ⊑ {r['assign_parent']}{kids}")

    # ---- P8 validation --------------------------------------------------
    rule("P8 · parent_validation  [REPORT]  — FIBO disjointness rejects bad parents")
    p8 = cat.p8_parent_validation()
    print("  Test: place hbim:CurrentAccount under caa:NonTransactionDepositAccount")
    for c in p8:
        print(f"   REJECTED — {c['offending']} would be in disjoint "
              f"{c['disjoint_a']} & {c['disjoint_b']}")

    # ---- persist --------------------------------------------------------
    rule("PERSISTED ARTIFACTS")
    derived = cat.persist_derivations()
    derived.serialize(destination=HBIM_DERIVED, format="turtle")
    print(f"[MATERIALISE] {HBIM_DERIVED}  ({len(derived)} sound ancestry triples)")

    candidates = cat.persist_candidates()
    candidates.serialize(destination=HBIM_CANDIDATES, format="turtle")
    n_concepts = len(set(candidates.subjects(RDF_TYPE, SKOS_CONCEPT)))
    print(f"[PROPOSE]     {HBIM_CANDIDATES}  ({n_concepts} candidate concepts + properties)")

    report = {
        "catalog": [{"id": p, "name": n, "persistence": pe, "intent": i}
                    for p, n, pe, i in CATALOG],
        "P1_ancestry": p1,
        "P2_correct_parent": p2,
        "P3_missing_intermediate": cat.p3_missing_intermediate_concepts(),
        "P4_missing_narrower": cat.p4_missing_narrower_concepts(),
        "P5_missing_object_properties": cat.p5_missing_object_properties(),
        "P6_missing_data_properties": p6,
        "P7_parent_assignment": cat.p7_parent_assignment_candidates(),
        "P8_validation": p8,
    }
    with open(PATTERNS_REPORT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"[REPORT]      {PATTERNS_REPORT}")


from rdflib import RDF as _RDF
from rdflib.namespace import SKOS as _SKOS
RDF_TYPE, SKOS_CONCEPT = _RDF.type, _SKOS.Concept

if __name__ == "__main__":
    main()
