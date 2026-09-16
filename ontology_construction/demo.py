"""End-to-end demonstration of the four construction processes.

    python ontology_construction/demo.py

Runs offline and deterministically. Prints, for a small lending corpus:

1. which NeOn scenarios the available resources justify;
2. the LOT sprints, including a Chowlk-style conceptual model;
3. the LLMs4OL subtasks with the O(n^2) relation budget made explicit;
4. the NeOn-GPT pipeline with every deterministic gate decision;
5. the metrics, including an OntoAxiom-style scorecard against a gold standard;
6. the four-stage CI/CD drift gate, run twice — once on a healthy ontology and
   once after a regression, to show it actually fails.
"""

from __future__ import annotations

import os
import sys

# Runnable as `python ontology_construction/demo.py` from the repository root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ontology_construction as oc  # noqa: E402

CORPUS = [
    "A mortgage is a kind of loan. A loan is issued by a bank. "
    "Loans such as mortgages and overdrafts are offered to customers. "
    "A bank owns a portfolio. A loan requires collateral. "
    "A default causes a loss. Collateral is held by a bank.",
]

CONCEPTUAL_MODEL = """
    class Loan
    Mortgage --|> Loan
    Overdraft --|> Loan
    Loan -- issued by --> Bank
    Loan -- requires --> Collateral
    Loan.principal : xsd:decimal
    Loan.interestRate : xsd:decimal
"""

#: The gold standard, written in the naming convention the conceptual model
#: establishes — the same convention `_collapse_case_variants` canonicalises to.
GOLD = oc.OntologyDraft()
GOLD.add_subclass("Mortgage", "Loan")
GOLD.add_subclass("Overdraft", "Loan")
GOLD.add_class("Bank")
GOLD.add_class("Collateral")
GOLD.object_properties = [
    oc.RelationEdge("Loan", "issued by", "Bank"),
    oc.RelationEdge("Loan", "requires", "Collateral"),
]
GOLD.disjointness = {("Mortgage", "Overdraft")}

#: Per-step parameters threaded through `run_workflow`. Handing the expert
#: conceptual model to the implementation sprint is what makes CQ03 — an
#: attribute question — answerable at all.
PARAMS = {"lot.implementation": {"conceptual_model": CONCEPTUAL_MODEL}}


def rule(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


def fresh() -> oc.ConstructionState:
    return oc.ConstructionState(
        domain="lending",
        documents=list(CORPUS),
        use_cases=["What kinds of loan are there? Is a mortgage a loan? "
                   "What is the principal of a loan?"],
        non_ontological_resources=[
            "collateral: an asset pledged by a borrower to secure a loan\n"
            "default: failure to meet the legal obligations of a loan"],
        ontological_resources=[
            "https://spec.edmcouncil.org/fibo/ontology#terms=LegalEntity"],
        design_patterns=["participation: bank - issues -> loan"],
        target_languages=["en", "pl"],
    )


def main() -> None:
    # ------------------------------------------------------------------ 1 --- #
    rule("1. NeOn — which of the nine scenarios do our resources justify?")
    state = fresh()
    oc.step_select_scenarios(state)
    for key in state.scenarios:
        s = oc.SCENARIO_BY_ID[int(key[1:])]
        print(f"  {s.key}  {s.name}")

    # ------------------------------------------------------------------ 2 --- #
    rule("2. LOT — four sprints")
    state = fresh()
    oc.step_lot_requirements(state, require_cqs=False)
    oc.step_specify_requirements(state)          # lift CQs out of the use case
    oc.step_formalise_cqs(state)
    for cq in state.competency_questions:
        print(f"  {cq.id}  [{cq.pattern:12s}] {cq.text}")
    model = oc.parse_chowlk(CONCEPTUAL_MODEL)
    print(f"  conceptual model: {model.summary()}")
    oc.step_lot_implementation(state, conceptual_model=model)
    oc.step_run_themis(state)
    oc.step_lot_publication(state)
    pub = state.reports["publication"]
    print(f"  published at {pub['namespace']}")
    for mime, url in pub["content_negotiation"].items():
        print(f"      {mime:24s} -> {url}")

    # ------------------------------------------------------------------ 3 --- #
    rule("3. LLMs4OL — three subtasks, with the O(n^2) bound made explicit")
    state = fresh()
    oc.step_term_typing(state)
    oc.step_taxonomy_discovery(state)
    oc.step_relation_extraction(state, max_pairs=40)
    by_type: dict[str, list[str]] = {}
    for t in state.accepted_terms():
        by_type.setdefault(t.type_label, []).append(t.label)
    for type_label, members in sorted(by_type.items()):
        print(f"  {type_label:10s} {', '.join(sorted(members)[:8])}")
    print("  taxonomy:", ", ".join(f"{e.child} < {e.parent}"
                                   for e in state.accepted_taxonomy()[:6]))
    print("  relations:", ", ".join(f"{r.domain} -{r.predicate}-> {r.range}"
                                    for r in state.accepted_relations()[:6]))
    b = state.reports["relation_budget"]
    print(f"  budget: evaluated {b['evaluated_pairs']} of {b['theoretical_pairs']} "
          f"possible pairs ({b['reduction']:.1%} reduction)")

    # ------------------------------------------------------------------ 4 --- #
    rule("4. NeOn-GPT — constrained generation with deterministic gates")
    state = fresh()
    state = oc.NeOnGPTPipeline(strict=False).run(state)
    for rec in state.stages:
        if rec.gate:
            print(f"  gate {rec.gate:18s} {'ok  ' if rec.ok else 'FAIL'} {rec.detail}")
    p = state.reports["pipeline"]
    print(f"  {p['stages_run']}/{p['stages_total']} stages; "
          f"{p['rejected']} rejected, {p['repaired']} repaired")

    # ------------------------------------------------------------------ 5 --- #
    rule("5. A hallucinated axiom is rejected, not merged")

    class Hallucinating:
        name = "hallucinating-stub"

        def type_terms(self, documents):
            return [oc.CandidateTerm(label=t, type_label="Entity", score=1.0,
                                     provenance=self.name)
                    for t in ("loan", "bank", "mortgage")]

        def discover_taxonomy(self, terms, documents):
            return [
                oc.TaxonomyEdge("mortgage", "loan", 0.9, self.name),      # true
                oc.TaxonomyEdge("loan", "derivative", 0.9, self.name),    # invented
            ]

        def extract_relations(self, pairs, documents):
            return [oc.RelationEdge("loan", "orbits", "saturn", 1.0, self.name)]

    state = fresh()
    oc.step_term_typing(state, extractor=Hallucinating())
    oc.step_taxonomy_discovery(state, extractor=Hallucinating())
    oc.step_relation_extraction(state, extractor=Hallucinating())
    print("  before gates:",
          [e.as_pair() for e in state.taxonomy_edges],
          [r.as_triple() for r in state.relation_edges])
    for gate in (oc.vocabulary_gate, oc.grounding_gate):
        res = gate(state)
        print(f"  {gate.__name__:18s} rejected={res.rejected}  {res.detail}")
    print("  surviving:", [e.as_pair() for e in state.accepted_taxonomy()],
          [r.as_triple() for r in state.accepted_relations()])

    # ------------------------------------------------------------------ 6 --- #
    rule("6. Metrics")
    state = fresh()
    state = oc.run_workflow(oc.build_hybrid_workflow(), state, params=PARAMS)
    oc.step_measure(state, gold=GOLD)
    card = state.reports["axioms"]
    print("  OntoAxiom-style scorecard:")
    for row in card["per_type"]:
        print(f"    {row['axiom_type']:14s} P={row['precision']:.2f} "
              f"R={row['recall']:.2f} F1={row['f1']:.2f}  (support {row['support']})")
    print(f"    macro-F1 {card['macro_f1']:.3f} | micro-F1 {card['micro_f1']:.3f} "
          f"| weakest: {card['weakest_axiom_type']} ({card['weakest_f1']:.2f})")
    st = state.reports["structural"]
    print(f"  structural: {st['classes']} classes, {st['relations']} relations, "
          f"attribute richness {st['attribute_richness']}, "
          f"C/R ratio {st['class_relation_ratio']} -> {st['verdict']}")
    print("  cohesion by induced type:",
          {k: v for k, v in state.reports["cohesion"].items() if v})
    crit = state.reports["criteria"]
    for name, score in crit["scores"].items():
        print(f"    {name:14s} {score:.2f}   {crit['evidence'][name]}")

    # ------------------------------------------------------------------ 7 --- #
    rule("7. CI/CD drift gate — healthy, then after a regression")
    healthy = fresh()
    healthy = oc.run_workflow(oc.build_hybrid_workflow(), healthy, params=PARAMS)
    print(oc.DriftGate(fail_fast=False).run(healthy))

    print("\n  ...now delete the axiom CQ02 depends on and re-run:")
    regressed = fresh()
    regressed = oc.run_workflow(oc.build_hybrid_workflow(), regressed, params=PARAMS)
    # Match on the canonical name, whatever casing the merge settled on.
    removed = {e for e in regressed.ontology.subclass_of
               if e[0].lower() == "mortgage"}
    regressed.ontology.subclass_of -= removed
    print(f"  (removed {sorted(removed)})")
    print(oc.DriftGate(fail_fast=True).run(regressed))

    rule("Resulting ontology (Turtle, head)")
    print("\n".join(healthy.ontology.to_turtle().splitlines()[:26]))


if __name__ == "__main__":
    main()
