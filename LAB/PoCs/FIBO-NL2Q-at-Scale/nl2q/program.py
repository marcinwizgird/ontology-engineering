"""The NL -> SPARQL program as DSPy modules (arm S), plus the direct-generation arms.

Language-model steps (each a DSPy predictor GEPA can optimise):

* M1 ``mentions``  — phrases that refer to concepts, values, operations;
* M2 ``planner``   — a plan (:class:`nl2q.ir.Plan`) chosen from the grounding context;
* M3 ``repair``    — a corrected plan, given only the checker's messages.

Deterministic steps in between: grounding (retrieval + graph re-ranking), the ontology
query check, rendering, compilation (Ontop). Refusal is a plan with ``answerable=false``.

Models: ``NL2Q_MODEL`` (e.g. ``anthropic/claude-sonnet-5-5``) configures the program;
without it the rule planner (``nl2q.planner_rules``) stands in — offline by default.
Live runs are opt-in and billed: ask before running them.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

import dspy
from pydantic import BaseModel

from . import grounding as G
from . import ir, knowledge, obqc, planner_rules, render
from .querygraph import load as load_graph

# ----------------------------------------------------------------------------- #
# models
# ----------------------------------------------------------------------------- #


def make_lm(model: str | None = None, **kw) -> dspy.LM | None:
    """A DSPy LM for an Anthropic model via LiteLLM, or None when no model is configured.
    Current Claude models reject non-default sampling parameters and always think, so no
    temperature is sent; ``max_tokens`` is generous because thinking counts against it."""
    model = model or os.environ.get("NL2Q_MODEL")
    if not model:
        return None
    if "/" not in model:
        model = "anthropic/" + model
    return dspy.LM(model, temperature=None, max_tokens=kw.pop("max_tokens", 16000),
                   cache=kw.pop("cache", True), timeout=kw.pop("timeout", 180),
                   num_retries=kw.pop("num_retries", 2), **kw)


# ----------------------------------------------------------------------------- #
# signatures
# ----------------------------------------------------------------------------- #
class MentionOut(BaseModel):
    text: str
    kind: str  # concept | value | any


class ExtractMentions(dspy.Signature):
    """List the phrases of a banking/markets question that must be grounded in the data:
    concepts (entities, attributes, relations, measures), values (names of companies or
    people, tickers, codes, places, dates, numbers used as filters) and nothing else.
    Copy each phrase verbatim from the question. kind is "concept", "value" or "any"."""

    question: str = dspy.InputField()
    mentions: list[MentionOut] = dspy.OutputField()


class PlanQuery(dspy.Signature):
    """Write a query plan that answers the question over the FIBEN knowledge graph.

    Use only the ontology terms listed in the grounding context (classes, object properties
    as links between nodes, datatype properties as attributes) and respect link directions
    exactly as listed. Prefer one of the candidate paths (T1, T2, ...) when it fits the
    question. Values must be copied from the grounding's value list when one matches.
    Dates use ISO format (YYYY-MM-DD). Never expand subclasses yourself: a class includes
    its subclasses. Project the attributes the question asks for (names rather than
    internal ids). Use negations for "not / never / no", comparisons for "more than the
    same person's ..." or "above the average", group/aggregate for "per / each / total /
    average / how many". If the data cannot answer the question, return answerable=false
    with a reason instead of guessing."""

    question: str = dspy.InputField()
    grounding: str = dspy.InputField(desc="candidate terms, connecting paths, values, glossary")
    plan: ir.Plan = dspy.OutputField()


class RepairPlan(dspy.Signature):
    """The plan failed deterministic checks. Fix exactly the reported problems; keep what
    is right. If the problems show the question cannot be answered from this data, return
    answerable=false with the reason."""

    question: str = dspy.InputField()
    grounding: str = dspy.InputField()
    plan_json: str = dspy.InputField()
    problems: str = dspy.InputField()
    plan: ir.Plan = dspy.OutputField()


class DirectSPARQL(dspy.Signature):
    """Write one SPARQL 1.1 SELECT query over the FIBEN ontology that answers the question.
    Use the prefix fiben: <https://example.org/fiben/voc#>. A class includes its subclasses
    (a reasoner handles the hierarchy). Return only the query."""

    question: str = dspy.InputField()
    ontology: str = dspy.InputField(desc="classes, properties, allowed edges, glossary")
    sparql: str = dspy.OutputField()


class RepairSPARQL(dspy.Signature):
    """The SPARQL query failed checks against the ontology or did not compile. Fix the
    reported problems and return the corrected query only."""

    question: str = dspy.InputField()
    ontology: str = dspy.InputField()
    sparql_in: str = dspy.InputField()
    problems: str = dspy.InputField()
    sparql: str = dspy.OutputField()


class TextToSQL(dspy.Signature):
    """Write one DuckDB SQL SELECT over the given schema (schema FIBEN, quoted upper-case
    identifiers) that answers the question. Return only the SQL."""

    question: str = dspy.InputField()
    schema_ddl: str = dspy.InputField()
    sql: str = dspy.OutputField()


# ----------------------------------------------------------------------------- #
# context rendering
# ----------------------------------------------------------------------------- #
def grounding_context(gr: G.GroundingResult, level: int = 4, max_trees: int = 5) -> str:
    pack = knowledge.load()
    g = load_graph()
    lines = ["# Candidate terms per phrase"]
    shown_classes: set[str] = set()
    for m in gr.mentions:
        items = []
        for c in m.candidates:
            t = pack.term(c.local)
            if c.kind == "value":
                items.append(f'value "{c.value}" = {c.cls}.{c.local}')
                shown_classes.add(c.cls)
            else:
                desc = ""
                if t is not None and level >= 1 and t.definition:
                    desc = f" — {t.definition[:140]}"
                items.append(f"{c.kind} {c.local}{desc}")
                if c.kind == "class":
                    shown_classes.add(c.local)
        lines.append(f'- "{m.text}": ' + "; ".join(items))
    if level >= 3:
        lines.append("# Candidate paths (subject property object), cheapest first")
        for t in gr.trees[:max_trees]:
            if not t.connected:
                lines.append(f"- {t.handle}: NOT CONNECTED — {'; '.join(t.notes)}")
                continue
            lines.append(f"- {t.handle} (cost {t.cost:.1f}): " +
                         (" ; ".join(f"{s} {p} {o}" for s, p, o in t.tree) or "single class ") +
                         f"  [classes: {', '.join(t.classes)}]")
            shown_classes |= set(t.classes)
            for s, _, o in t.tree:
                shown_classes |= {s, o}
    if level >= 3:
        # recall over pruning: every link touching an involved class (and its ancestors), so
        # the planner can complete a path the candidate trees missed instead of refusing
        lines.append("# All links touching the involved classes (subject property object; a class "
                     "inherits the links of its superclasses)")
        seen_links = set()
        for c in sorted(shown_classes):
            if c not in g.classes:
                continue
            chain = [c] + g.ancestors(c)
            for e in g.obj_edges:
                if (e.src in chain or e.dst in chain) and (e.src, e.prop, e.dst) not in seen_links:
                    seen_links.add((e.src, e.prop, e.dst))
                    lines.append(f"- {e.src} {e.prop} {e.dst}")
            if c in g.parent:
                lines.append(f"- ({c} is a subclass of {' < '.join(g.ancestors(c))})")
        for s_, _, o_ in list(seen_links):
            shown_classes |= {s_, o_}
    lines.append("# Attributes available on the involved classes (incl. inherited)")
    for c in sorted(shown_classes):
        if c in g.classes:
            lines.append(f"- {c}: {', '.join(sorted(g.attributes(c))) or '(none)'}")
    if level >= 4:
        _, gl = G.path_hints(gr.question, level)
        if gl:
            lines.append("# Curated glossary entries matching the question")
            for e in gl:
                lines.append(f"- {e['term']}: {e['means']}")
    if gr.unmapped_hints:
        lines.append("# Not mapped in this data")
        lines += [f"- {h}" for h in gr.unmapped_hints]
    return "\n".join(lines)


def ontology_card(level: int = 4) -> str:
    """The whole mapped ontology, compact (for the direct-generation arms A/B)."""
    pack = knowledge.load()
    g = load_graph()
    core = [c for c in sorted(g.classes) if c not in pack.subclass or
            pack.subclass[c] not in ("Disclosure",)]
    lines = ["# Classes (Disclosure has 118 further subclasses for individual disclosures)"]
    for c in core:
        t = pack.term(c)
        parent = f" ⊑ {pack.subclass[c]}" if c in pack.subclass else ""
        d = f" — {t.definition[:100]}" if t and t.definition and level >= 1 else ""
        lines.append(f"- {c}{parent}{d}; attributes: {', '.join(sorted(g.data_props.get(c, ()))) or '-'}")
    lines.append("# Object properties (subject property object)")
    lines += [f"- {e.src} {e.prop} {e.dst}" for e in g.obj_edges]
    if level >= 4:
        lines.append("# Glossary")
        lines += [f"- {e['term']}: {e['means']}" for e in pack.glossary]
    return "\n".join(lines)


# ----------------------------------------------------------------------------- #
# the program
# ----------------------------------------------------------------------------- #
@dataclass
class Trace:
    steps: list[dict] = field(default_factory=list)

    def add(self, name: str, **kw) -> None:
        self.steps.append({"step": name, **kw})


class NL2SPARQL(dspy.Module):
    """Arm S (with an LM) / arm R (rules, no LM)."""

    def __init__(self, level: int = 4, use_lm: bool = True, max_repairs: int = 2,
                 scorer: str = "steiner", lm_mentions: bool = True):
        super().__init__()
        self.level, self.use_lm, self.max_repairs = level, use_lm, max_repairs
        self.scorer, self.lm_mentions = scorer, lm_mentions
        self.mentions = dspy.Predict(ExtractMentions)
        self.planner = dspy.Predict(PlanQuery)
        self.repair = dspy.Predict(RepairPlan)

    def _lm_active(self) -> bool:
        return self.use_lm and dspy.settings.lm is not None

    def forward(self, question: str):
        tr = Trace()
        t0 = time.perf_counter()
        if self._lm_active() and self.lm_mentions:
            try:
                ms = self.mentions(question=question).mentions
                specs = [G.MentionSpec(m.text, m.kind if m.kind in ("concept", "value", "any") else "any")
                         for m in ms if m.text.strip()]
            except Exception as exc:  # noqa: BLE001
                tr.add("mentions_failed", error=str(exc)[:200])
                specs = G.rule_mentions(question)
        else:
            specs = G.rule_mentions(question)
        tr.add("mentions", mentions=[(s.text, s.kind) for s in specs])
        gr = G.ground(question, specs, level=self.level, scorer=self.scorer)
        ctx = grounding_context(gr, self.level)
        tr.add("grounding", best=gr.best.tree if gr.best else None,
               classes=gr.best.classes if gr.best else [])
        if self._lm_active():
            try:
                plan = self.planner(question=question, grounding=ctx).plan
            except Exception as exc:  # noqa: BLE001
                tr.add("plan_failed", error=str(exc)[:300])
                plan = ir.Plan(answerable=False, reason=f"planner output invalid: {str(exc)[:120]}")
        else:
            plan = planner_rules.plan(question, gr)
        sparql, problems = None, []
        for attempt in range(self.max_repairs + 1):
            problems = obqc.check_plan(plan)
            if not problems and plan.answerable:
                try:
                    sparql = render.render(plan)
                    from .vkg import compile_error_type, compile_sparql
                    try:
                        compile_sparql(sparql)
                    except compile_error_type() as exc:
                        problems = [f"compiler ({exc.stage}): {str(exc)[:300]}"]
                        sparql = None
                except render.RenderError as exc:
                    problems = [f"render: {exc}"]
            tr.add("check", attempt=attempt, problems=problems, answerable=plan.answerable)
            if not problems or not plan.answerable:
                break
            if not self._lm_active() or attempt == self.max_repairs:
                break
            try:
                plan = self.repair(question=question, grounding=ctx,
                                   plan_json=plan.model_dump_json(exclude_defaults=True),
                                   problems="\n".join(problems)).plan
            except Exception as exc:  # noqa: BLE001
                tr.add("repair_failed", error=str(exc)[:200])
                break
        refused = not plan.answerable or sparql is None
        reason = plan.reason if not plan.answerable else ("; ".join(problems) if sparql is None else "")
        cands = {c.local for m in gr.mentions for c in m.candidates} | \
                {c.cls for m in gr.mentions for c in m.candidates if c.cls}
        for t in gr.trees:
            cands |= set(t.classes) | {x for s, p, o in t.tree for x in (s, p, o)}
        return dspy.Prediction(question=question, plan=plan, sparql=sparql, refused=refused,
                               reason=reason, problems=problems, grounding=ctx, trace=tr.steps,
                               candidates=sorted(cands), ms=round((time.perf_counter() - t0) * 1e3))


class DirectArm(dspy.Module):
    """Arms A (direct SPARQL) and B (A + OBQC/compile checks + repair)."""

    def __init__(self, level: int = 4, repair: bool = False, max_repairs: int = 3):
        super().__init__()
        self.level, self.do_repair, self.max_repairs = level, repair, max_repairs
        self.gen = dspy.Predict(DirectSPARQL)
        self.fix = dspy.Predict(RepairSPARQL)
        self._card = None

    def forward(self, question: str):
        from .vkg import PREFIXES, compile_error_type, compile_sparql
        self._card = self._card or ontology_card(self.level)
        t0 = time.perf_counter()
        q = _strip_fence(self.gen(question=question, ontology=self._card).sparql)
        if "PREFIX fiben:" not in q:
            q = PREFIXES + q
        problems: list[str] = []
        for attempt in range(self.max_repairs + 1):
            problems = obqc.check_sparql(q) if self.do_repair else []
            if not problems:
                try:
                    compile_sparql(q)
                except compile_error_type() as exc:
                    problems = [f"compiler ({exc.stage}): {str(exc)[:300]}"]
            if not problems or not self.do_repair or attempt == self.max_repairs:
                break
            q = _strip_fence(self.fix(question=question, ontology=self._card, sparql_in=q,
                                      problems="\n".join(problems)).sparql)
            if "PREFIX fiben:" not in q:
                q = PREFIXES + q
        refused = bool(problems) and self.do_repair     # Allemang & Sequeda: "I don't know"
        return dspy.Prediction(question=question, sparql=None if refused else q, refused=refused,
                               reason="; ".join(problems) if refused else "", problems=problems,
                               ms=round((time.perf_counter() - t0) * 1e3))


class TextToSQLArm(dspy.Module):
    """Arm T: SQL straight from the DDL (no ontology)."""

    def __init__(self):
        super().__init__()
        self.gen = dspy.Predict(TextToSQL)
        from . import paths
        self.ddl = paths.FIBEN_DDL.read_text(encoding="utf-8")

    def forward(self, question: str):
        t0 = time.perf_counter()
        sql = _strip_fence(self.gen(question=question, schema_ddl=self.ddl).sql)
        return dspy.Prediction(question=question, sql=sql, refused=False, reason="",
                               ms=round((time.perf_counter() - t0) * 1e3))


class ToolAgentArm(dspy.Module):
    """Arm G: a generic tool-using agent (browse schema, run SQL), no ontology."""

    def __init__(self, max_iters: int = 12):
        super().__init__()
        from .load_fiben import connect
        from . import schema as S
        self._con = connect()
        self._s = S.load()

        def list_tables() -> str:
            """List all tables of schema FIBEN."""
            return ", ".join(self._s.tables)

        def describe_table(name: str) -> str:
            """Columns, primary key and foreign keys of a table."""
            t = self._s.tables.get(name.upper())
            if t is None:
                return f"no table {name}"
            fks = "; ".join(f"{f.column} -> {f.ref_table}.{f.ref_column}" for f in t.fks)
            return f"{t.name}({', '.join(c.name + ' ' + c.sql_type for c in t.columns)}) PK {t.pk}; FK {fks}"

        def run_sql(sql: str) -> str:
            """Run a read-only SELECT (first 20 rows returned)."""
            if not sql.strip().lower().startswith(("select", "with")):
                return "only SELECT is allowed"
            # killable worker process: an agent's runaway query must not hang the run
            from .sqlworker import worker
            status, cols, rows = worker().run(
                f"SELECT * FROM ({sql.rstrip().rstrip(';')}) AS agent_q LIMIT 20", timeout_s=20)
            if status != "ok":
                return f"error: {cols}"
            return json.dumps({"columns": cols, "rows": [[str(v) for v in r] for r in rows]})[:3000]

        self.agent = dspy.ReAct("question -> sql", tools=[list_tables, describe_table, run_sql],
                                max_iters=max_iters)

    def forward(self, question: str):
        t0 = time.perf_counter()
        sql = _strip_fence(self.agent(question=question).sql)
        return dspy.Prediction(question=question, sql=sql, refused=False, reason="",
                               ms=round((time.perf_counter() - t0) * 1e3))


def _strip_fence(s: str) -> str:
    s = (s or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s.rsplit("```", 1)[0]
    return s.strip()


ARMS = {
    "R": lambda: NL2SPARQL(use_lm=False),
    "S": lambda: NL2SPARQL(use_lm=True),
    "A": lambda: DirectArm(repair=False),
    "B": lambda: DirectArm(repair=True),
    "T": lambda: TextToSQLArm(),
    "G": lambda: ToolAgentArm(),
}
LIVE_ARMS = {"S", "A", "B", "T", "G"}
