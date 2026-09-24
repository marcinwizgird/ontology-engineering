"""The worked reference task: ontology triage as a DSPy program.

This is the task Chapter 1's agentic lab builds and optimises, and the template
later chapters copy. It has the three parts every task in the course needs:

1. **a signature** — the typed contract between evidence and answer;
2. **a program** — deterministic tool calls to gather evidence, then one LM call
   to interpret it (tools do what tools do well; the model does judgement);
3. **a rulebook** — the named guidelines the scorer can report as violated, so
   the GEPA feedback says which guideline failed and what to do instead.

The split in (2) is a deliberate design lesson. Putting the *measurement* in
code and only the *interpretation* in the model makes the system cheaper, more
reproducible, and far easier to evaluate — and it makes the optimiser's job
tractable, because there is exactly one instruction that matters.
"""

from __future__ import annotations

import json

from oe_course.evaluation import TRIAGE_RULES, Rule, RuleBook

__all__ = [
    "TRIAGE_RULEBOOK",
    "TriageSignature",
    "TriageProgram",
    "BASELINE_INSTRUCTION",
    "gather_evidence",
]

# --------------------------------------------------------------------------- #
# The rulebook — ids match evaluation.TRIAGE_RULES exactly
# --------------------------------------------------------------------------- #
TRIAGE_RULEBOOK = RuleBook(
    Rule(rule_id, description) for rule_id, description in TRIAGE_RULES.items()
)

#: What a competent-but-uninstructed prompt looks like. Optimisation starts here.
BASELINE_INSTRUCTION = (
    "You are reviewing an ontology. Given the gathered evidence, say how formal "
    "the ontology is and what is wrong with it."
)


# --------------------------------------------------------------------------- #
# Evidence gathering (deterministic — no model involved)
# --------------------------------------------------------------------------- #
def gather_evidence(artefact: str, ctx=None) -> tuple[str, object]:
    """Run the analysis tools over one artefact; return (evidence JSON, context).

    Passing an existing :class:`oe_course.tools.ToolContext` reuses its call log,
    which is what lets a whole dataset run be costed as one budget.
    """
    from oe_course.tools import ToolContext, build_toolset

    ctx = ctx or ToolContext()
    tools = {t.name: t for t in build_toolset(ctx)}
    tools["load_artefact"].invoke({"name": artefact})
    evidence = {
        "artefact": artefact,
        "metrics": json.loads(tools["graph_metrics"].invoke({})),
        "spectrum": json.loads(tools["spectrum_position"].invoke({})),
        "scanner_findings": json.loads(tools["scan_smells"].invoke({})),
    }
    return json.dumps(evidence, indent=1), ctx


# --------------------------------------------------------------------------- #
# The DSPy program
# --------------------------------------------------------------------------- #
def _signature():
    import dspy

    class TriageSignature(dspy.Signature):
        """Assess an ontology from gathered evidence."""

        evidence: str = dspy.InputField(
            desc="JSON with metrics, spectrum classification and scanner findings"
        )
        level: str = dspy.OutputField(desc="the ontology's position on the spectrum")
        smells: str = dspy.OutputField(desc="a JSON array of defect identifiers")
        justification: str = dspy.OutputField(desc="why, citing the evidence")

    return TriageSignature


_SIGNATURE = None


def TriageSignature():
    """The task's signature (built lazily so importing does not require dspy)."""
    global _SIGNATURE
    if _SIGNATURE is None:
        _SIGNATURE = _signature()
    return _SIGNATURE


def TriageProgram(instruction: str | None = BASELINE_INSTRUCTION, share_context: bool = True):
    """Build the triage program: gather evidence with tools, then interpret it.

    ``share_context=True`` reuses one :class:`ToolContext` across every call so
    the whole run's tool cost is visible in a single log.
    """
    import dspy

    from oe_course.tools import ToolContext

    class _TriageProgram(dspy.Module):
        def __init__(self):
            super().__init__()
            self.interpret = dspy.Predict(TriageSignature())
            if instruction:
                self.interpret.signature = self.interpret.signature.with_instructions(
                    instruction
                )
            self.ctx = ToolContext() if share_context else None

        def forward(self, artefact: str):
            evidence, ctx = gather_evidence(artefact, self.ctx)
            if share_context:
                self.ctx = ctx
            return self.interpret(evidence=evidence)

    return _TriageProgram()
