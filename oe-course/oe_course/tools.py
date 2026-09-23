"""Function tools: the action surface an ontology-engineering agent acts through.

Three ideas are load-bearing for the course and are worth naming before the code:

**Tools are bound to a workspace, not to globals.** :class:`ToolContext` holds the
SPARQL store and the artefact under study. ``build_toolset(ctx)`` closes each
tool over it. That is what makes an agent reproducible: two students, two
contexts, no shared state.

**Every call is logged.** :class:`ToolCallLog` records name, arguments, latency
and result size. The log *is* the agent's trajectory — Chapter labs replay it as
an MDP episode (:mod:`oe_course.mdp`) and charge it against the reward.

**Decomposition is explicit.** The toolset is deliberately factored into narrow,
composable actions (fetch, measure, classify, scan) rather than one
``analyse_ontology`` mega-tool. Students compare both and measure the difference
in trajectory length, cost and accuracy.
"""

from __future__ import annotations

import functools
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from langchain_core.tools import StructuredTool, tool

from oe_course import ontology as ont
from oe_course.sparql import SparqlStore

__all__ = ["ToolContext", "ToolCallLog", "ToolCall", "build_toolset",
           "monolithic_toolset", "instrument"]


# --------------------------------------------------------------------------- #
# Call logging
# --------------------------------------------------------------------------- #
@dataclass
class ToolCall:
    name: str
    args: dict
    ok: bool
    seconds: float
    result_chars: int
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "args": self.args,
            "ok": self.ok,
            "seconds": round(self.seconds, 4),
            "result_chars": self.result_chars,
            "error": self.error,
        }


@dataclass
class ToolCallLog:
    """An append-only record of what an agent did."""

    calls: list[ToolCall] = field(default_factory=list)

    def record(self, call: ToolCall) -> None:
        self.calls.append(call)

    def reset(self) -> None:
        self.calls.clear()

    def names(self) -> list[str]:
        return [c.name for c in self.calls]

    def cost(self, per_call: float = 1.0, per_second: float = 0.0) -> float:
        """A simple, explicit cost model — the reward's negative term."""
        return sum(per_call + per_second * c.seconds for c in self.calls)

    def summary(self) -> dict:
        return {
            "n_calls": len(self.calls),
            "distinct_tools": sorted({c.name for c in self.calls}),
            "failures": sum(1 for c in self.calls if not c.ok),
            "seconds": round(sum(c.seconds for c in self.calls), 3),
        }

    def to_list(self) -> list[dict]:
        return [c.to_dict() for c in self.calls]


# --------------------------------------------------------------------------- #
# Context
# --------------------------------------------------------------------------- #
@dataclass
class ToolContext:
    """The workspace a toolset acts on."""

    store: SparqlStore = field(default_factory=SparqlStore.in_memory)
    log: ToolCallLog = field(default_factory=ToolCallLog)
    #: Name of the artefact currently loaded (set by ``load_artefact``).
    artefact: str | None = None
    #: The parsed graph of the loaded artefact, for the non-SPARQL tools.
    graph: Any = None

    @classmethod
    def for_artefact(cls, name: str) -> "ToolContext":
        """A context with one corpus artefact already loaded."""
        from oe_course.data import corpus

        art = corpus.get(name)
        ctx = cls(store=SparqlStore.in_memory(art.turtle))
        ctx.artefact = name
        ctx.graph = ont.load_graph(art.turtle)
        return ctx

    def require_graph(self):
        if self.graph is None:
            raise ValueError(
                "No artefact loaded. Call load_artefact(name) first."
            )
        return self.graph


def instrument(fn: Callable, name: str, log: ToolCallLog) -> Callable:
    """Wrap a tool implementation so every invocation lands in the log.

    ``functools.wraps`` matters here: LangChain infers each tool's argument
    schema via ``inspect.signature``, which follows ``__wrapped__``. Without it
    every tool would advertise ``(*args, **kwargs)`` and the model would have
    nothing to fill in.
    """

    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        started = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:  # surfaced to the agent as an error string
            log.record(
                ToolCall(name, kwargs or {"args": args}, False,
                         time.perf_counter() - started, 0, str(exc))
            )
            return f"ERROR: {exc}"
        text = result if isinstance(result, str) else json.dumps(result, default=str)
        log.record(
            ToolCall(name, kwargs or {"args": list(args)}, True,
                     time.perf_counter() - started, len(text))
        )
        return text

    return wrapped


#: Chapters build their own toolsets; ``instrument`` is the shared seam that
#: gives every one of them the same call log.
_instrument = instrument  # backwards-compatible alias


# --------------------------------------------------------------------------- #
# The decomposed toolset
# --------------------------------------------------------------------------- #
def build_toolset(ctx: ToolContext) -> list[StructuredTool]:
    """Narrow, composable tools bound to ``ctx``.

    Each tool's description states *when* to reach for it, not just what it
    does — the trigger condition is what drives correct tool selection.
    """
    from oe_course.data import corpus

    def load_artefact(name: str) -> str:
        """Load a named ontology from the course corpus into the workspace.

        Call this first, before any other tool. `name` must be one of the
        corpus names; call list_artefacts if you do not know them.
        """
        art = corpus.get(name)
        ctx.store = SparqlStore.in_memory(art.turtle)
        ctx.graph = ont.load_graph(art.turtle)
        ctx.artefact = name
        return json.dumps({"loaded": name, "triples": len(ctx.graph)})

    def list_artefacts() -> str:
        """List the ontology names available in the course corpus."""
        return json.dumps(sorted(corpus.BY_NAME))

    def graph_metrics() -> str:
        """Count the loaded ontology's classes, properties, axioms and annotations.

        Call this when you need quantitative evidence about what the artefact
        contains — for example before judging how formal it is.
        """
        return json.dumps(ont.graph_metrics(ctx.require_graph()))

    def spectrum_position() -> str:
        """Classify the loaded ontology on the ontology spectrum, with evidence.

        Returns one of: controlled-vocabulary, taxonomy, thesaurus,
        formal-ontology, plus the specific counts that justified the placement.
        """
        result = ont.classify_spectrum(ctx.require_graph())
        return json.dumps({"level": result["level"], "evidence": result["evidence"]})

    def scan_smells() -> str:
        """Detect known modelling defects in the loaded ontology.

        Call this whenever asked to review, critique or assess the quality of an
        ontology. Returns one entry per defect found, each naming the term that
        triggered it.
        """
        findings = ont.scan_smells(ctx.require_graph())
        return json.dumps([f.to_dict() for f in findings])

    def smell_catalogue() -> str:
        """Explain every defect the scanner can detect and why each one matters.

        Call this when you need to justify a finding or decide whether a defect
        is worth reporting.
        """
        return json.dumps(
            [{"id": s.id, "title": s.title, "why": s.why} for s in ont.SMELLS]
        )

    def sparql_select(query: str) -> str:
        """Run a SPARQL SELECT against the loaded ontology and return the rows.

        Use this for questions the fixed tools do not answer — specific classes,
        specific axioms, or ad-hoc counts. Standard prefixes (rdf, rdfs, owl,
        skos, awo, ex) are already declared; do not redeclare them.
        """
        return json.dumps(ctx.store.select(query)[:100])

    def sparql_ask(query: str) -> str:
        """Run a SPARQL ASK against the loaded ontology; returns true or false.

        Use this to check a specific claim before asserting it.
        """
        return json.dumps({"answer": ctx.store.ask(query)})

    impls = [
        load_artefact, list_artefacts, graph_metrics, spectrum_position,
        scan_smells, smell_catalogue, sparql_select, sparql_ask,
    ]
    return [tool(instrument(fn, fn.__name__, ctx.log)) for fn in impls]


def monolithic_toolset(ctx: ToolContext) -> list[StructuredTool]:
    """One do-everything tool — the baseline students compare against.

    Faster per episode, but it hides which evidence the agent actually used and
    gives the reward function nothing to shape. The contrast is the lesson.
    """

    def analyse_ontology(name: str) -> str:
        """Load a corpus ontology and return every available analysis at once."""
        from oe_course.data import corpus

        art = corpus.get(name)
        g = ont.load_graph(art.turtle)
        ctx.graph, ctx.artefact = g, name
        ctx.store = SparqlStore.in_memory(art.turtle)
        spectrum = ont.classify_spectrum(g)
        return json.dumps(
            {
                "metrics": spectrum["metrics"],
                "level": spectrum["level"],
                "evidence": spectrum["evidence"],
                "smells": [f.to_dict() for f in ont.scan_smells(g)],
            }
        )

    return [tool(instrument(analyse_ontology, "analyse_ontology", ctx.log))]
