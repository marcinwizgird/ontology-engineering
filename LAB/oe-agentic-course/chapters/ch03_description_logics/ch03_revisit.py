"""Chapter 3's second problem set: the agent layer, back on Chapters 1 and 2's tasks.

Provided code for ``06_assignment.ipynb``. Chapters 1 and 2 built their tasks before the
course had tools or agents, so their problem sets stopped short of the parts that need
them: Chapter 1's **registry tools and triage agent** (original Ch 1 A2 and D1) and
Chapter 2's **compliance agent that proves its verdicts** (original Ch 2 D1). Chapter 3
introduces ``agentlab.tools`` and ``agentlab.agents``, so those parts return here.

This module *revisits* earlier chapters: it imports their support modules (Chapter 1's
registry corpus, Chapter 2's FOL engine) — backwards only, never ahead, and only from a
revisit problem set (``tests/test_incremental.py`` enforces both). It adds what those
chapters could not have:

* the **registry tools** over Chapter 1's submissions (:func:`build_registry_tools`), the
  one-call **monolithic** alternative (:func:`build_monolithic_tool`), and which evidence
  kind each tool buys (:data:`TOOL_TO_EVIDENCE`);
* Chapter 1's intake policy as code (:func:`reportable_smells`, :func:`intake_decision` —
  the reference answer to Chapter 1's A1) and a field scorer (:func:`triage_score`);
* Chapter 2's **compliance knowledge base** (the formalised policy, the audit-day facts,
  six questions), its closed-domain decision procedure (:func:`ground_entails`,
  :func:`verdict`) and the compliance agent's tools (:func:`build_policy_tools`).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

_CHAPTERS = Path(__file__).resolve().parent.parent
for _name in ("ch01_introduction", "ch02_first_order_logic"):
    _p = str(_CHAPTERS / _name)
    if _p not in sys.path:
        sys.path.append(_p)

import ch01_agentic as ch1  # noqa: E402  (Chapter 1: the registry corpus and policy)
import ch02_toolkit as fol  # noqa: E402  (Chapter 2: the FOL engine)
from agentlab import ontology as ont  # noqa: E402
from agentlab.sparql import SparqlStore  # noqa: E402
from agentlab.tools import ToolCallLog, make_tools  # noqa: E402

__all__ = [
    "RegistryWorkspace", "build_registry_tools", "build_monolithic_tool", "EVIDENCE_KINDS",
    "TOOL_TO_EVIDENCE", "registry_evidence", "reportable_smells", "intake_decision",
    "triage_score", "POLICY_KB", "FACTS", "COMPLIANCE_QUERIES", "ground_entails", "verdict",
    "PolicyWorkspace", "build_policy_tools",
]

# --------------------------------------------------------------------------- #
# Chapter 1: the registry, as tools
# --------------------------------------------------------------------------- #
_PREFIXES = ("PREFIX owl: <http://www.w3.org/2002/07/owl#>\n"
             "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\n"
             "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
             "PREFIX skos: <http://www.w3.org/2004/02/skos/core#>\n"
             "PREFIX mr: <https://data.meridianrail.example/def/>\n")


@dataclass
class RegistryWorkspace:
    """What a registry reviewer (human or agent) is working on, plus its call log."""

    store: SparqlStore | None = None
    graph: object = None
    submission: str | None = None
    log: ToolCallLog = field(default_factory=ToolCallLog)

    def load(self, submission_id: str):
        sub = ch1.get(submission_id)
        self.store = SparqlStore.in_memory(sub.turtle)
        self.graph = ont.load_graph(sub.turtle)
        self.submission = submission_id
        return sub

    def require(self):
        if self.graph is None:
            raise ValueError("No submission loaded. Call load_submission(submission_id) first.")
        return self.graph


def _prefixed(query: str) -> str:
    return query if "PREFIX" in query.upper() else _PREFIXES + query


def build_registry_tools(ws: RegistryWorkspace):
    """Narrow registry tools bound to ``ws``; every call lands in ``ws.log``."""

    def list_submissions() -> str:
        """List the ids of the submissions waiting for intake review."""
        return json.dumps(sorted(ch1.BY_ID))

    def load_submission(submission_id: str) -> str:
        """Load one submission into the workspace. Call this first, before any other tool."""
        ws.load(submission_id)
        return json.dumps({"loaded": submission_id, "triples": len(ws.graph)})

    def submission_record() -> str:
        """Read the intake form of the loaded submission: team, declared level, purpose.

        Call this before deciding, because the decision compares the measured level
        with the level the team declared.
        """
        ws.require()
        return json.dumps(ch1.get(ws.submission).record())

    def graph_metrics() -> str:
        """Count the loaded submission's classes, properties, axioms and annotations."""
        return json.dumps(ont.graph_metrics(ws.require()))

    def spectrum_position() -> str:
        """Measure where the loaded submission sits on the ontology spectrum, with evidence.

        Returns one of controlled-vocabulary, taxonomy, thesaurus, formal-ontology, and the
        counts that placed it. Call this whenever you need the submission's level.
        """
        result = ont.classify_spectrum(ws.require())
        return json.dumps({"level": result["level"], "evidence": result["evidence"]})

    def scan_smells() -> str:
        """Run the registry's defect scanner on the loaded submission.

        Call this whenever you review a submission; report defects only from its output.
        Returns one finding per defect, naming the term that triggered it.
        """
        return json.dumps([f.to_dict() for f in ont.scan_smells(ws.require())])

    def smell_catalogue() -> str:
        """Explain every defect id the scanner can report and why it matters."""
        return json.dumps([{"id": s.id, "title": s.title, "why": s.why} for s in ont.SMELLS])

    def sparql_select(query: str) -> str:
        """Run a SPARQL SELECT over the loaded submission (rdf, rdfs, owl, skos, mr declared)."""
        ws.require()
        return json.dumps(ws.store.select(_prefixed(query))[:100])

    def sparql_ask(query: str) -> str:
        """Run a SPARQL ASK over the loaded submission, to check a specific claim."""
        ws.require()
        return json.dumps({"answer": ws.store.ask(_prefixed(query))})

    impls = [list_submissions, load_submission, submission_record, graph_metrics,
             spectrum_position, scan_smells, smell_catalogue, sparql_select, sparql_ask]
    return make_tools(impls, ws.log)


def build_monolithic_tool(ws: RegistryWorkspace):
    """One do-everything tool: the design the course argues against, for comparison."""

    def review_submission(submission_id: str) -> str:
        """Load a submission and return every available analysis of it at once."""
        sub = ws.load(submission_id)
        spectrum = ont.classify_spectrum(ws.graph)
        return json.dumps({"record": sub.record(), "metrics": spectrum["metrics"],
                           "level": spectrum["level"], "evidence": spectrum["evidence"],
                           "findings": [f.to_dict() for f in ont.scan_smells(ws.graph)],
                           "catalogue": [{"id": s.id, "why": s.why} for s in ont.SMELLS]})

    return make_tools([review_submission], ws.log)


def registry_evidence(submission_id: str, ws: RegistryWorkspace | None = None) -> str:
    """Chapter 1's evidence bundle, gathered through the *logged* tools (JSON text).

    Runs the record, metrics, spectrum and scanner tools in that order, so the
    workspace log shows exactly what a fixed pipeline paid for.
    """
    ws = ws or RegistryWorkspace()
    tools = {t.name: t for t in build_registry_tools(ws)}
    tools["load_submission"].invoke({"submission_id": submission_id})
    evidence = {
        "submission": json.loads(tools["submission_record"].invoke({})),
        "metrics": json.loads(tools["graph_metrics"].invoke({})),
        "spectrum": json.loads(tools["spectrum_position"].invoke({})),
        "scanner_findings": json.loads(tools["scan_smells"].invoke({})),
    }
    return json.dumps(evidence, indent=1)


#: The kinds of evidence a reviewer can buy, one tool (family) each.
EVIDENCE_KINDS = ["record", "metrics", "spectrum", "smells", "catalogue", "sparql"]

#: Which evidence kind each registry tool call buys. Tools not listed
#: (list_submissions, load_submission, review_submission) buy nothing the log can show.
TOOL_TO_EVIDENCE = {
    "submission_record": "record",
    "graph_metrics": "metrics",
    "spectrum_position": "spectrum",
    "scan_smells": "smells",
    "smell_catalogue": "catalogue",
    "sparql_select": "sparql",
    "sparql_ask": "sparql",
}

_RANK = {level: i for i, level in enumerate(ont.SPECTRUM_LEVELS)}


def reportable_smells(raw: Iterable[str], measured_level: str) -> list[str]:
    """Policy clause 2: the scanner's ids, minus waiver W1 (Chapter 1, A1's answer)."""
    smells = set(raw)
    if measured_level in ch1.WAIVABLE_AT:
        smells.discard("no-disjointness")
    return sorted(smells)


def intake_decision(reported: Iterable[str], declared_level: str, measured_level: str) -> str:
    """Policy clause 3: reject / revise / accept (Chapter 1, A1's answer)."""
    reported = set(reported)
    if reported & ch1.BLOCKING_SMELLS:
        return "reject"
    if reported or _RANK[measured_level] < _RANK[declared_level]:
        return "revise"
    return "accept"


def triage_score(gold, pred) -> float:
    """Mean of three exact fields: level, the reported smells (as a set), the decision."""
    smells = getattr(pred, "smells", None) or []
    if isinstance(smells, str):
        smells = [s.strip() for s in smells.strip("[]").replace('"', "").split(",") if s.strip()]
    level_ok = str(getattr(pred, "level", "")).strip().lower() == gold.level
    smells_ok = {str(s).strip().lower() for s in smells} == set(gold.smells)
    decision_ok = str(getattr(pred, "decision", "")).strip().lower() == gold.decision
    return (level_ok + smells_ok + decision_ok) / 3


# --------------------------------------------------------------------------- #
# Chapter 2: the compliance knowledge base and its decision procedure
# --------------------------------------------------------------------------- #
#: The policy the checker enforces (already formalised and reviewed).
POLICY_KB: list[tuple[str, str]] = [
    ("nurses-are-clinicians", "forall x (Nurse(x) -> Clinician(x))"),
    ("clinicians-are-employees", "forall x (Clinician(x) -> Employee(x))"),
    ("contractors-no-access",
     "forall x (Contractor(x) -> ~exists y (Record(y) & CanAccess(x, y)))"),
    ("treating-clinician-access",
     "forall x forall y forall z ((Clinician(x) & Treats(x, y) & About(z, y)) -> CanAccess(x, z))"),
    ("only-clinicians-access",
     "forall x forall y ((Record(y) & CanAccess(x, y)) -> Clinician(x))"),
    ("external-auditors-no-sensitive",
     "forall x ((Auditor(x) & External(x)) -> ~exists y (Record(y) & Sensitive(y) & CanAccess(x, y)))"),
]

#: Ground facts about the hospital on the day of the audit (closed domain).
FACTS: list[str] = [
    "Nurse(Ana)", "Treats(Ana, Pia)", "Patient(Pia)", "Record(R1)", "About(R1, Pia)",
    "Clinician(Ben)", "Patient(Ole)", "Record(R2)", "About(R2, Ole)", "Sensitive(R2)",
    "Contractor(Cal)", "Auditor(Dee)", "External(Dee)",
]

#: (id, question, conclusion to test, gold verdict). Gold verdicts are recomputed
#: with :func:`verdict` in the notebook, and asserted there, so they cannot drift.
COMPLIANCE_QUERIES: list[tuple[str, str, str, str]] = [
    ("ana-r1", "May Ana read record R1?", "CanAccess(Ana, R1)", "yes"),
    ("ana-employee", "Is Ana an employee?", "Employee(Ana)", "yes"),
    ("cal-r1", "May Cal read record R1?", "CanAccess(Cal, R1)", "no"),
    ("dee-r2", "May Dee read record R2?", "CanAccess(Dee, R2)", "no"),
    ("ben-r2", "May Ben read record R2?", "CanAccess(Ben, R2)", "undetermined"),
    ("dee-r1", "May Dee read record R1?", "CanAccess(Dee, R1)", "undetermined"),
]


def _constants(formulas) -> list[str]:
    names: set[str] = set()
    for f in formulas:
        names |= fol.constants_in(f)
    return sorted(names)


def _lit_value(literal: str, assignment: dict[str, bool]):
    atom = literal.lstrip("~")
    if atom not in assignment:
        return None
    return assignment[atom] != literal.startswith("~")


def _dpll(clauses: list[frozenset[str]], assignment: dict[str, bool]) -> dict[str, bool] | None:
    """Tiny DPLL: a satisfying assignment of literal strings, or None."""
    while True:
        simplified = []
        unit = None
        for clause in clauses:
            if any(_lit_value(l, assignment) is True for l in clause):
                continue
            rest = frozenset(l for l in clause if _lit_value(l, assignment) is None)
            if not rest:
                return None
            if len(rest) == 1 and unit is None:
                unit = next(iter(rest))
            simplified.append(rest)
        clauses = simplified
        if not clauses:
            return assignment
        if unit is None:
            break
        atom, value = (unit[1:], False) if unit.startswith("~") else (unit, True)
        assignment = {**assignment, atom: value}
    literal = next(iter(clauses[0]))
    atom = literal.lstrip("~")
    for value in (True, False):
        result = _dpll(clauses, {**assignment, atom: value})
        if result is not None:
            return result
    return None


def ground_entails(premises, conclusion) -> tuple[bool, dict[str, bool] | None]:
    """Does the policy entail ``conclusion`` when the domain is the named individuals?

    The closed-domain assumption (only the constants mentioned exist) turns FOL
    entailment into propositional satisfiability, which DPLL decides. Returns
    ``(entailed, counterexample)``: when not entailed, the counterexample is a
    world consistent with the premises in which the conclusion is false.
    """
    premises = list(premises)
    names = _constants(premises + [conclusion]) or ["a"]
    clauses: list[frozenset[str]] = []
    for f in premises + [fol.Not(conclusion)]:
        clauses += fol.to_cnf_clauses(fol.ground(f, names))
    model = _dpll(clauses, {})
    return model is None, model


def verdict(premises, conclusion) -> str:
    """'yes' if entailed, 'no' if its negation is entailed, else 'undetermined'."""
    if ground_entails(premises, conclusion)[0]:
        return "yes"
    if ground_entails(premises, fol.Not(conclusion))[0]:
        return "no"
    return "undetermined"


@dataclass
class PolicyWorkspace:
    """What the compliance agent can see: the policy, the facts, and its call log."""

    policy: list[tuple[str, str]] = field(default_factory=lambda: list(POLICY_KB))
    facts: list[str] = field(default_factory=lambda: list(FACTS))
    log: ToolCallLog = field(default_factory=ToolCallLog)

    def premises(self) -> list:
        return [fol.parse(f) for _, f in self.policy] + [fol.parse(f) for f in self.facts]


def build_policy_tools(ws: PolicyWorkspace):
    """The compliance agent's tools: read the policy, read the facts, check a claim."""

    def read_policy() -> str:
        """List the formalised access policy: one (id, formula) pair per rule."""
        return json.dumps([{"id": i, "formula": f} for i, f in ws.policy])

    def read_facts() -> str:
        """List the ground facts about named people, patients and records."""
        return json.dumps(ws.facts)

    def check_entailment(conclusion: str) -> str:
        """Decide whether policy + facts entail a closed formula over the named individuals.

        Use the policy's predicate names and the capitalised constants from the facts,
        e.g. 'CanAccess(Ana, R1)' or '~CanAccess(Cal, R1)'. Returns entailed=true/false and,
        when false, a counterexample world. To answer a yes/no question, check the claim AND
        its negation: neither entailed means the policy does not settle the question.
        """
        entailed, model = ground_entails(ws.premises(), fol.parse(conclusion))
        counter = None
        if model is not None:
            counter = {k: v for k, v in sorted(model.items()) if "(" in k}
        return json.dumps({"conclusion": conclusion, "entailed": entailed,
                           "counterexample": counter})

    return make_tools([read_policy, read_facts, check_entailment], ws.log)
