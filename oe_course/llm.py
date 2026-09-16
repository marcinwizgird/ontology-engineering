"""Language-model access for the course — live Anthropic, or a simulator.

Two families of client live here:

``chat_model()``
    A LangChain ``BaseChatModel``. Live mode returns ``ChatAnthropic``; offline
    mode returns :class:`SimulatedChatModel`, which supports ``bind_tools`` and
    emits real tool calls, so a LangChain/LangGraph agent loop actually runs.

``dspy_lm()`` / ``configure_dspy()``
    A DSPy ``LM``. Live mode routes through LiteLLM to Anthropic; offline mode
    returns :class:`SimulatedTaskLM`.

Why the offline LM is *rule-conditioned* (and not canned)
---------------------------------------------------------
A fake LM that ignores its prompt makes prompt optimisation a no-op: GEPA would
search instructions that cannot change the score, and students would watch a
loop that proves nothing. :class:`SimulatedTaskLM` instead behaves like a weak
model that *follows explicit instructions*: it starts from a naive strategy and
applies a better one only for each :class:`Rule` whose marker appears in the
instruction it was given.

Its companion, the reflection path, reads the ``MISSING RULE <id>: <text>``
lines that the course's GEPA metrics put in their feedback and writes them into
a revised instruction — exactly what a real reflection LM does when the metric
tells it what went wrong. The result is a genuine, converging optimisation loop
that costs nothing to run.

This is a **simulator, and the notebooks say so.** It teaches the mechanics of
the loop; the quality numbers it produces are about the simulator, not about
Claude. Set ``ANTHROPIC_API_KEY`` to run the identical code for real.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from oe_course import config

# --------------------------------------------------------------------------- #
# Rules — the unit of "knowledge an instruction can carry"
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Rule:
    """One piece of task knowledge that an instruction may or may not convey.

    ``id``          stable slug, used as the activation marker;
    ``description`` the human-readable rule, written into the instruction by the
                    reflection simulator and shown to students;
    ``feedback``    the sentence a metric emits when the rule was *not* applied.
    """

    id: str
    description: str

    @property
    def marker(self) -> str:
        """The token whose presence in an instruction activates the rule."""
        return f"RULE {self.id}"

    def instruction_line(self) -> str:
        return f"- {self.marker}: {self.description}"

    def missing_line(self) -> str:
        """Feedback line the reflection simulator can mine."""
        return f"MISSING RULE {self.id}: {self.description}"


class RuleBook:
    """A named collection of :class:`Rule` objects for one task."""

    def __init__(self, rules: Iterable[Rule]):
        self._rules: dict[str, Rule] = {r.id: r for r in rules}

    def __iter__(self):
        return iter(self._rules.values())

    def __len__(self) -> int:
        return len(self._rules)

    def __getitem__(self, rule_id: str) -> Rule:
        return self._rules[rule_id]

    @property
    def ids(self) -> list[str]:
        return list(self._rules)

    def active_in(self, instruction: str) -> set[str]:
        """Which rules the given instruction actually conveys."""
        return {r.id for r in self._rules.values() if r.marker in instruction}

    def full_instruction(self, preamble: str) -> str:
        """The 'oracle' instruction — what a perfect optimiser would find."""
        return preamble + "\n" + "\n".join(r.instruction_line() for r in self._rules.values())


# --------------------------------------------------------------------------- #
# DSPy side
# --------------------------------------------------------------------------- #

_REFLECTION_MARKER = "Your task is to write a new instruction for the assistant."
_MISSING_RULE_RE = re.compile(r"MISSING RULE ([A-Za-z0-9_\-]+): ([^\n]+)")
_FIELD_RE = re.compile(r"\[\[ ## ([A-Za-z0-9_]+) ## \]\]\n(.*?)(?=\n\[\[ ## |\Z)", re.DOTALL)


#: ChatAdapter appends a closing directive after the last input field. Left in
#: place it would be captured as part of that field's value (and, for a JSON
#: field, make it unparseable), so it is trimmed before matching.
_TRAILER_RE = re.compile(r"\n+Respond with the corresponding output fields.*\Z", re.DOTALL)


def parse_fields(text: str) -> dict[str, str]:
    """Parse DSPy ChatAdapter ``[[ ## name ## ]]`` blocks out of a message."""
    text = _TRAILER_RE.sub("", text or "")
    return {m.group(1): m.group(2).strip() for m in _FIELD_RE.finditer(text)}


_SIM_LM_CLASS = None


def _simulated_task_lm_class():
    """Build the ``dspy.LM`` subclass on first use (keeps import cost lazy)."""
    global _SIM_LM_CLASS
    if _SIM_LM_CLASS is not None:
        return _SIM_LM_CLASS

    import dspy
    from dspy.adapters.chat_adapter import ChatAdapter

    class _SimulatedTaskLM(dspy.LM):
        """A deterministic, instruction-sensitive stand-in for a DSPy ``LM``.

        Overrides ``__call__`` — the same seam ``dspy.utils.dummies.DummyLM``
        uses — so DSPy's adapters, optimisers and history all work unchanged.

        Parameters
        ----------
        rulebook:
            The rules this task's instruction may convey.
        responder:
            ``responder(inputs, active_rule_ids) -> dict`` producing the output
            fields. It should degrade gracefully when ``active`` is empty — that
            is the "before optimisation" behaviour students measure.
        """

        def __init__(self, rulebook: RuleBook, responder: Callable[[dict, set[str]], dict]):
            super().__init__("oe-course-simulator", "chat", 1.0, config.MAX_TOKENS, False)
            self.rulebook = rulebook
            self.responder = responder
            self.adapter = ChatAdapter()
            self.calls: list[dict] = []

        # -- the LM interface -----------------------------------------------
        def __call__(self, prompt=None, messages=None, **kwargs):
            messages = messages or [{"role": "user", "content": prompt or ""}]
            joined = "\n".join(m.get("content") or "" for m in messages)

            out = self._reflect(joined) if _REFLECTION_MARKER in joined else self._solve(messages)

            self.calls.append({"messages": messages, "output": out})
            self.update_history(
                {"messages": messages, "outputs": [out], "usage": 0, "cost": 0, "kwargs": kwargs}
            )
            return [out]

        # -- task path ------------------------------------------------------
        def _solve(self, messages: list[dict]) -> str:
            instruction = "\n".join(
                m.get("content") or "" for m in messages if m.get("role") == "system"
            )
            active = self.rulebook.active_in(instruction)
            inputs = parse_fields(messages[-1].get("content") or "")
            return self._format(self.responder(inputs, active))

        def _format(self, fields: dict[str, Any]) -> str:
            from dspy.adapters.chat_adapter import FieldInfoWithName
            from dspy.signatures.field import OutputField

            payload = {FieldInfoWithName(name=k, info=OutputField()): v for k, v in fields.items()}
            try:
                return self.adapter.format_field_with_value(payload, role="assistant")
            except TypeError:  # ChatAdapter's signature takes no `role`
                return self.adapter.format_field_with_value(payload)

        # -- reflection path ------------------------------------------------
        def _reflect(self, prompt: str) -> str:
            """Rewrite the instruction from the rules the feedback complained about.

            A real reflection LM reads the feedback and generalises. This one
            does the mechanical version of the same move: every ``MISSING RULE``
            line in the feedback becomes an explicit rule in the new instruction.
            """
            current = _extract_first_code_block(prompt)
            found = {rid: text.strip() for rid, text in _MISSING_RULE_RE.findall(prompt)}

            lines = [ln for ln in current.splitlines() if ln.strip()]
            for rule_id, text in found.items():
                marker = f"RULE {rule_id}"
                if not any(marker in ln for ln in lines):
                    lines.append(f"- {marker}: {text}")
            return "```\n" + "\n".join(lines) + "\n```"

    _SIM_LM_CLASS = _SimulatedTaskLM
    return _SIM_LM_CLASS


def SimulatedTaskLM(rulebook: RuleBook, responder: Callable[[dict, set[str]], dict]):
    """Construct the simulated DSPy LM (see :func:`_simulated_task_lm_class`)."""
    return _simulated_task_lm_class()(rulebook, responder)


def _extract_first_code_block(text: str) -> str:
    start = text.find("```")
    if start == -1:
        return text.strip()
    end = text.find("```", start + 3)
    if end == -1:
        return text[start + 3 :].strip()
    return text[start + 3 : end].strip()


def dspy_lm(rulebook: RuleBook | None = None,
            responder: Callable[[dict, set[str]], dict] | None = None,
            *, model: str | None = None):
    """The DSPy LM for the current mode.

    Offline mode needs ``rulebook`` and ``responder`` (the task simulator);
    live mode ignores them.
    """
    import dspy

    if config.offline():
        if rulebook is None or responder is None:
            raise ValueError(
                "Offline mode needs a rulebook and responder — the notebook's task "
                "module supplies them. Set ANTHROPIC_API_KEY (and unset "
                "OE_COURSE_OFFLINE) to use a live model instead."
            )
        return SimulatedTaskLM(rulebook, responder)

    # temperature=1.0 is the accepted default on claude-opus-5/sonnet-5; DSPy's
    # usual 0.0 would be rejected as a non-default sampling parameter.
    return dspy.LM(model or config.DSPY_MODEL, temperature=1.0, max_tokens=config.MAX_TOKENS)


def configure_dspy(rulebook: RuleBook | None = None,
                   responder: Callable[[dict, set[str]], dict] | None = None):
    """Install the right LM as the DSPy default and return it."""
    import dspy

    lm = dspy_lm(rulebook, responder)
    dspy.configure(lm=lm)
    return lm


def reflection_lm(rulebook: RuleBook | None = None,
                  responder: Callable[[dict, set[str]], dict] | None = None):
    """The LM GEPA uses to *propose* instructions (distinct from the task LM)."""
    import dspy

    if config.offline():
        return SimulatedTaskLM(rulebook or RuleBook([]), responder or (lambda i, a: {}))
    return dspy.LM(config.REFLECTION_MODEL, temperature=1.0, max_tokens=config.MAX_TOKENS)


# --------------------------------------------------------------------------- #
# LangChain side
# --------------------------------------------------------------------------- #


@dataclass
class ToolPlan:
    """What the simulated chat model should do on one turn."""

    tool_calls: list[dict] = field(default_factory=list)
    text: str = ""


def _simulated_chat_class():
    """Build :class:`SimulatedChatModel` lazily so importing is cheap."""
    from langchain_core.callbacks import CallbackManagerForLLMRun
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.utils.function_calling import convert_to_openai_tool

    class SimulatedChatModel(BaseChatModel):
        """A scripted chat model that can call tools.

        ``planner(messages, tools) -> ToolPlan`` decides each turn. The default
        planner (:func:`keyword_planner`) routes on keywords, which is enough to
        drive a real ReAct loop over the course's Fuseki/OWL tools offline.
        """

        planner: Any = None
        turn_log: list = None  # type: ignore[assignment]

        model_config = {"arbitrary_types_allowed": True}

        def __init__(self, planner: Callable[..., ToolPlan] | None = None, **kw):
            super().__init__(**kw)
            object.__setattr__(self, "planner", planner or keyword_planner)
            object.__setattr__(self, "turn_log", [])

        @property
        def _llm_type(self) -> str:
            return "oe-course-simulated-chat"

        def bind_tools(self, tools: Sequence[Any], **kwargs: Any):
            return self.bind(tools=[convert_to_openai_tool(t) for t in tools], **kwargs)

        def _generate(
            self,
            messages: list[BaseMessage],
            stop: list[str] | None = None,
            run_manager: CallbackManagerForLLMRun | None = None,
            **kwargs: Any,
        ) -> ChatResult:
            tools = kwargs.get("tools") or []
            plan = self.planner(messages, tools)
            self.turn_log.append(plan)
            msg = AIMessage(
                content=plan.text,
                tool_calls=[
                    {"name": c["name"], "args": c.get("args", {}), "id": c.get("id") or f"call_{i}"}
                    for i, c in enumerate(plan.tool_calls)
                ],
            )
            return ChatResult(generations=[ChatGeneration(message=msg)])

    return SimulatedChatModel


#: The evidence-gathering order the offline planner follows.
_TRIAGE_PLAN = ["graph_metrics", "spectrum_position", "scan_smells"]


def keyword_planner(messages, tools) -> ToolPlan:
    """Default offline planner: load the named artefact, gather evidence, answer.

    It is a *scripted competent agent*, not a model: it extracts the artefact
    name from the request, walks a fixed evidence plan, and emits a JSON answer
    the course's metrics can score. That makes the offline agent labs about the
    plumbing that matters — tool schemas, the loop, the trajectory, the cost —
    while keeping every run deterministic. Notebooks that want different
    behaviour (including deliberately bad behaviour, for the MDP labs) pass
    their own planner.
    """
    import json

    from langchain_core.messages import HumanMessage, ToolMessage

    observations = {m.name: m.content for m in messages if isinstance(m, ToolMessage)}
    available = {t["function"]["name"] for t in tools} if tools else set()
    request = next((m.content for m in messages if isinstance(m, HumanMessage)), "")

    if "load_artefact" in available and "load_artefact" not in observations:
        return ToolPlan(
            tool_calls=[{"name": "load_artefact", "args": {"name": _extract_artefact(request)}}]
        )

    for step in _TRIAGE_PLAN:
        if step in available and step not in observations:
            return ToolPlan(tool_calls=[{"name": step, "args": {}}])

    answer = {"level": None, "smells": [], "evidence": []}
    try:
        spectrum = json.loads(observations.get("spectrum_position", "{}"))
        answer["level"] = spectrum.get("level")
        answer["evidence"] = spectrum.get("evidence", [])
    except json.JSONDecodeError:
        pass
    try:
        findings = json.loads(observations.get("scan_smells", "[]"))
        answer["smells"] = sorted({f["smell"] for f in findings})
    except (json.JSONDecodeError, TypeError):
        pass
    return ToolPlan(text=json.dumps(answer, indent=1))


def _extract_artefact(request: str) -> str:
    """Pull a corpus artefact name out of the request text."""
    from oe_course.data import corpus

    for name in sorted(corpus.BY_NAME, key=len, reverse=True):
        if name in request:
            return name
    return request.strip().strip("'\".")


def _default_args(openai_tool_schema: dict, messages) -> dict:
    """Fill a tool's required string parameters with the user's question."""
    from langchain_core.messages import HumanMessage

    params = openai_tool_schema["function"].get("parameters", {}) or {}
    props = params.get("properties", {}) or {}
    required = params.get("required", []) or list(props)
    question = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)), ""
    )
    args: dict[str, Any] = {}
    for name in required:
        spec = props.get(name, {})
        if spec.get("type") == "integer":
            args[name] = spec.get("default", 10)
        elif spec.get("type") == "number":
            args[name] = spec.get("default", 1.0)
        elif spec.get("type") == "boolean":
            args[name] = spec.get("default", False)
        else:
            args[name] = spec.get("default", question)
    return args


def chat_model(planner: Callable[..., ToolPlan] | None = None, **kwargs):
    """The LangChain chat model for the current mode."""
    if config.offline():
        return _simulated_chat_class()(planner=planner)

    from langchain_anthropic import ChatAnthropic

    params = {"model": config.CHAT_MODEL, "max_tokens": config.MAX_TOKENS}
    params.update(kwargs)
    return ChatAnthropic(**params)
