"""Chapter 8 agentic lab — writing mappings, and choosing an execution strategy.

Two decisions an OBDA engineer makes constantly, and an agent can get wrong in
two very different ways:

1. **Mapping shape.** Does a column become an IRI or a literal? Get it wrong and
   the graph is silently disconnected — every join through that column fails,
   and no error is raised anywhere.
2. **Execution strategy.** Materialise, or rewrite? Get it wrong and the system
   is either slow or *stale*, and stale is worse: it returns confident wrong
   answers.

The MDP is the second decision made honest. A known workload interleaves queries
with updates; serving from a stale materialisation is cheap and **wrong**, so the
optimal policy has to decide when re-materialising is worth its price. That is
§8.2's trade-off with numbers attached.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import ch08_toolkit as ch8

__all__ = [
    "MAPPING_CASES", "build_dataset", "obda_scorer", "OBDA_RULEBOOK",
    "obda_responder", "OBDAProgram", "BASELINE_INSTRUCTION",
    "build_toolset", "Ch8Context", "MaterialisationMDP",
]


# --------------------------------------------------------------------------- #
# Dataset
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MappingCase:
    """One mapping decision plus one strategy decision."""

    id: str
    predicate: str
    column_description: str
    foreign_key: bool
    workload: str
    read_heavy: bool


#: Each case pairs a column (foreign key or plain attribute) with a workload
#: (read-heavy and static, or volatile). The two halves are independent so the
#: metric can say which decision an agent is getting wrong.
MAPPING_CASES = [
    MappingCase("inward-static", "med:inWard",
                "patient.ward_id references ward.id", True,
                "A nightly reporting dashboard; the data is loaded once a day and "
                "read thousands of times.", True),
    MappingCase("inward-live", "med:inWard",
                "patient.ward_id references ward.id", True,
                "A live bed-management screen; admissions and transfers are written "
                "continuously and answers must be current.", False),
    MappingCase("speciality-static", "med:speciality",
                "ward.speciality holds a plain text value", False,
                "A quarterly audit extract, read many times, data frozen at "
                "quarter end.", True),
    MappingCase("speciality-live", "med:speciality",
                "ward.speciality holds a plain text value", False,
                "An operational console over a source that changes minute by "
                "minute; freshness is required.", False),
    MappingCase("hasdisorder-static", "med:hasDisorder",
                "diagnosis.code references code_lookup.code", True,
                "A research cohort export from a frozen snapshot, queried "
                "repeatedly by analysts.", True),
    MappingCase("hasdisorder-live", "med:hasDisorder",
                "diagnosis.code references code_lookup.code", True,
                "A clinical alerting service reading a constantly updated "
                "transactional database.", False),
    MappingCase("category-static", "med:category",
                "code_lookup.category holds a plain text value", False,
                "A published reference dataset, never updated, heavily queried.", True),
    MappingCase("category-live", "med:category",
                "code_lookup.category holds a plain text value", False,
                "A staging environment where the coding scheme is edited daily and "
                "queries must reflect the latest edits.", False),
    MappingCase("label-static", "rdfs:label",
                "patient.name holds a plain text value", False,
                "An archival index built once and read for years.", True),
    MappingCase("wardref-live", "med:inWard",
                "patient.ward_id references ward.id", True,
                "A real-time transfer tracker; every write must be visible "
                "immediately.", False),
]


def build_dataset(split: str = "all"):
    """Each example: a column description and a workload, with both gold answers."""
    import dspy

    examples = [
        dspy.Example(
            predicate=case.predicate,
            column=case.column_description,
            workload=case.workload,
            gold_object_kind="iri" if case.foreign_key else "literal",
            gold_strategy="materialise" if case.read_heavy else "rewrite",
            id=case.id,
        ).with_inputs("predicate", "column", "workload")
        for case in MAPPING_CASES
    ]
    if split == "all":
        return examples

    # Stratify on BOTH dimensions, not on list order. Alternating over the raw
    # list would put every static workload in train and every live one in dev,
    # leaving each half unable to teach one of the two strategies -- the failure
    # Chapter 5 Exercise 4.1 isolates. Grouping first makes that impossible by
    # construction rather than by careful ordering.
    groups: dict = {}
    for example in examples:
        key = (example.gold_object_kind, example.gold_strategy)
        groups.setdefault(key, []).append(example)

    train, dev = [], []
    for key in sorted(groups):
        for index, example in enumerate(groups[key]):
            (train if index % 2 == 0 else dev).append(example)
    return train if split == "train" else dev


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def obda_scorer(gold, pred):
    """Half for the mapping shape, half for the execution strategy."""
    from oe_course.evaluation import ScoreReport

    object_kind = str(getattr(pred, "object_kind", "") or "").strip().lower()
    strategy = str(getattr(pred, "strategy", "") or "").strip().lower()

    notes, violated = [], []

    kind_ok = object_kind == gold.gold_object_kind
    if not kind_ok:
        notes.append(
            f"Mapping shape wrong: answered {object_kind!r}, correct is "
            f"{gold.gold_object_kind!r} for a column where {gold.column}."
        )
        violated.append("iri-for-foreign-keys" if gold.gold_object_kind == "iri"
                        else "literal-for-attributes")
        if gold.gold_object_kind == "iri":
            notes.append(
                "  A foreign key mapped to a literal silently disconnects the graph: "
                "no join through it will ever match, and nothing raises an error."
            )

    strategy_ok = strategy == gold.gold_strategy
    if not strategy_ok:
        notes.append(
            f"Strategy wrong: answered {strategy!r}, correct is {gold.gold_strategy!r} "
            f"for this workload."
        )
        violated.append("rewrite-for-volatile-data" if gold.gold_strategy == "rewrite"
                        else "materialise-for-read-heavy")

    notes.append(f"mapping_ok={int(kind_ok)} strategy_ok={int(strategy_ok)}")
    return ScoreReport(0.5 * kind_ok + 0.5 * strategy_ok, notes,
                       list(dict.fromkeys(violated)))


# --------------------------------------------------------------------------- #
# Rulebook + offline simulator
# --------------------------------------------------------------------------- #
def _rulebook():
    from oe_course.llm import Rule, RuleBook

    return RuleBook(
        [
            Rule("iri-for-foreign-keys",
                 "When the object column is a foreign key referencing another table, map it "
                 "to an IRI built from that table's template (a referencing object map). A "
                 "literal there disconnects the graph silently."),
            Rule("literal-for-attributes",
                 "When the object column holds a plain attribute value rather than a "
                 "reference, map it to a literal, not to an IRI."),
            Rule("rewrite-for-volatile-data",
                 "When the source changes continuously and answers must be current, use "
                 "query rewriting: a materialised copy would serve stale answers."),
            Rule("materialise-for-read-heavy",
                 "When the data is static and read many times, materialise: pay the "
                 "transformation once and make every later query cheap."),
        ]
    )


OBDA_RULEBOOK = _rulebook()

BASELINE_INSTRUCTION = (
    "You are an OBDA engineer. Decide how to map the column and how to run the "
    "queries."
)


def obda_responder(inputs: dict, active: set[str]) -> dict:
    """A weak OBDA engineer: everything is a literal, and everything is ETL'd.

    The naive defaults are the ones real projects fall into — a mapping tool that
    emits literals unless told otherwise, and a data team whose reflex is to load
    everything into a warehouse.
    """
    column = (inputs.get("column", "") or "").lower()
    workload = (inputs.get("workload", "") or "").lower()

    is_foreign_key = "references" in column
    volatile = any(
        signal in workload
        for signal in ("continuously", "current", "minute by minute", "constantly",
                       "daily", "latest", "immediately", "real-time", "freshness")
    )

    if is_foreign_key:
        object_kind = "iri" if "iri-for-foreign-keys" in active else "literal"
    else:
        object_kind = "literal"

    if volatile:
        strategy = "rewrite" if "rewrite-for-volatile-data" in active else "materialise"
    else:
        strategy = "materialise"

    return {
        "object_kind": object_kind,
        "strategy": strategy,
        "justification": f"Mapped as {object_kind}; will {strategy}.",
    }


# --------------------------------------------------------------------------- #
# DSPy program
# --------------------------------------------------------------------------- #
_SIG = None


def OBDASignature():
    global _SIG
    if _SIG is None:
        import dspy

        class _OBDASignature(dspy.Signature):
            """Choose a mapping shape and an execution strategy."""

            predicate: str = dspy.InputField(desc="the ontology property being mapped")
            column: str = dspy.InputField(desc="what the source column holds")
            workload: str = dspy.InputField(desc="how the data is written and read")
            object_kind: str = dspy.OutputField(desc="iri or literal")
            strategy: str = dspy.OutputField(desc="materialise or rewrite")
            justification: str = dspy.OutputField(desc="one sentence")

        _SIG = _OBDASignature
    return _SIG


def OBDAProgram(instruction: str | None = BASELINE_INSTRUCTION):
    import dspy

    class _Program(dspy.Module):
        def __init__(self):
            super().__init__()
            self.decide = dspy.Predict(OBDASignature())
            if instruction:
                self.decide.signature = self.decide.signature.with_instructions(instruction)

        def forward(self, predicate: str, column: str, workload: str):
            return self.decide(predicate=predicate, column=column, workload=workload)

    return _Program()


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@dataclass
class Ch8Context:
    conn: object = None
    log: object = None

    def __post_init__(self):
        from oe_course.tools import ToolCallLog

        self.conn = self.conn if self.conn is not None else ch8.build_database()
        self.log = self.log or ToolCallLog()


def build_toolset(ctx: Ch8Context):
    from langchain_core.tools import tool

    from oe_course.tools import instrument

    def inspect_schema() -> str:
        """List the source tables, their columns and their foreign keys.

        Call this before writing any mapping: whether a column is a foreign key
        decides whether it maps to an IRI or a literal.
        """
        out = {}
        for (table,) in ctx.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"):
            columns = [
                {"name": row[1], "type": row[2], "primary_key": bool(row[5])}
                for row in ctx.conn.execute(f"PRAGMA table_info({table})")
            ]
            keys = [
                {"column": row[3], "references": f"{row[2]}.{row[4]}"}
                for row in ctx.conn.execute(f"PRAGMA foreign_key_list({table})")
            ]
            out[table] = {"columns": columns, "foreign_keys": keys}
        return json.dumps(out)

    def show_mappings() -> str:
        """Show the current mappings and what each one produces."""
        return json.dumps(ch8.mapping_report())

    def materialise_now() -> str:
        """Run every mapping and report the size of the resulting graph."""
        graph = ch8.materialise(ctx.conn)
        return json.dumps({"triples": len(graph)})

    def run_query(name: str, strategy: str = "rewrite") -> str:
        """Answer one of the chapter's named queries by 'rewrite' or 'materialise'.

        Use this to check a strategy actually returns what you expect.
        """
        query = ch8.QUERIES.get(name)
        if query is None:
            return json.dumps({"error": f"unknown query {name!r}",
                               "available": sorted(ch8.QUERIES)})
        if strategy == "materialise":
            rows = ch8.answers_via_materialisation(ctx.conn, query)
        else:
            rows = ch8.answers_via_rewriting(ctx.conn, query)
        return json.dumps({"strategy": strategy, "rows": len(rows), "answers": rows[:5]})

    def compare_strategies(name: str) -> str:
        """Check that materialisation and rewriting agree on a query.

        Call this before shipping a mapping. Disagreement means the mapping is
        wrong, and it is the only cheap way to find that out.
        """
        query = ch8.QUERIES.get(name)
        if query is None:
            return json.dumps({"error": f"unknown query {name!r}"})
        left = ch8.answers_via_materialisation(ctx.conn, query)
        right = ch8.answers_via_rewriting(ctx.conn, query)
        return json.dumps({"agree": left == right, "materialised": len(left),
                           "rewritten": len(right)})

    def show_sql(name: str) -> str:
        """Show the SQL a query rewrites to — useful for explaining a plan."""
        query = ch8.QUERIES.get(name)
        if query is None:
            return json.dumps({"error": f"unknown query {name!r}"})
        return ch8.to_sql(query)

    impls = [inspect_schema, show_mappings, materialise_now, run_query,
             compare_strategies, show_sql]
    return [tool(instrument(fn, fn.__name__, ctx.log)) for fn in impls]


# --------------------------------------------------------------------------- #
# The materialise-or-rewrite MDP
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ServeState:
    """Where we are in the workload, and whether the materialisation is fresh."""

    index: int
    fresh: bool

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"t{self.index}{'+' if self.fresh else '-'}"


class MaterialisationMDP:
    """Serve a workload of queries and updates: materialise, or rewrite?

    The workload is a known sequence of ``'q'`` (a query to answer) and ``'u'``
    (an update to the source). An update makes any materialisation **stale**.

    | | |
    |---|---|
    | **S** | position in the workload, and whether the copy is fresh |
    | **A** | on a query: serve by rewriting, serve from the copy, or refresh then serve |
    | **T** | deterministic |
    | **R** | ``+1`` for a **correct** answer, minus the cost of serving it |

    The trap is deliberate: serving from a stale copy is the *cheapest* action
    and earns nothing, because the answer is wrong. An agent optimising latency
    alone will take it. This is §8.2's trade-off with the staleness risk priced
    in rather than described.
    """

    def __init__(self, workload: str = "qquqqquq", cost_rewrite: float = 0.30,
                 cost_materialised: float = 0.05, cost_refresh: float = 0.50,
                 gamma: float = 1.0):
        self.workload = workload
        self.cost_rewrite = cost_rewrite
        self.cost_materialised = cost_materialised
        self.cost_refresh = cost_refresh
        self.gamma = gamma

    def initial_state(self) -> ServeState:
        return ServeState(0, False)

    def is_terminal(self, state: ServeState) -> bool:
        return state.index >= len(self.workload)

    def states(self):
        return [ServeState(i, f)
                for i in range(len(self.workload) + 1)
                for f in (False, True)]

    def actions(self, state: ServeState):
        if self.is_terminal(state):
            return []
        if self.workload[state.index] == "u":
            return ["apply-update"]
        return ["serve:rewrite", "serve:materialised", "serve:refresh-first"]

    def transition(self, state: ServeState, action: str):
        nxt_index = state.index + 1
        if action == "apply-update":
            # An update invalidates any materialised copy.
            return [(1.0, ServeState(nxt_index, False), 0.0)]
        if action == "serve:rewrite":
            return [(1.0, ServeState(nxt_index, state.fresh), 1.0 - self.cost_rewrite)]
        if action == "serve:materialised":
            correct = 1.0 if state.fresh else 0.0
            return [(1.0, ServeState(nxt_index, state.fresh),
                     correct - self.cost_materialised)]
        # refresh, then serve from the fresh copy
        reward = 1.0 - self.cost_refresh - self.cost_materialised
        return [(1.0, ServeState(nxt_index, True), reward)]

    def step(self, state: ServeState, action: str):
        _, nxt, reward = self.transition(state, action)[0]
        return nxt, reward, self.is_terminal(nxt)

    def describe(self, state: ServeState, action: str) -> str:
        event = "update" if self.workload[state.index] == "u" else "query"
        return f"[{state.index}] {event:6s} fresh={state.fresh!s:5s} -> {action}"
