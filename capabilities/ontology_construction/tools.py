"""The construction steps as agentic function tools.

Same convention as :mod:`bottomup_ontology.tools`: every step is a plain
function over a shared state, so it can be exposed as a JSON-schema tool and
driven by an agent that chooses its own order, while the registry keeps one
consistent :class:`~ontology_construction.state.ConstructionState`.

This is what lets the ontology-construction processes be *driven* by the
Ontology Builder's authoring copilot (`OB.AGT.03`) rather than reimplemented
inside it: the agent gets the NeOn lifecycle, the LOT sprints, the LLMs4OL
subtasks and the validation gates as tools, and the gates keep its output
honest whichever order it picks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .state import ConstructionState
from .workflow import ALL_STEPS, STEP_BY_ID, ProcessStep

__all__ = ["tool_specs", "ToolRegistry"]


def tool_specs() -> list[dict[str, Any]]:
    """OpenAI/Anthropic-style JSON tool specifications, one per step."""
    specs: list[dict[str, Any]] = []
    for step in ALL_STEPS:
        properties = {
            name: {"type": schema.get("type", "string"),
                   "description": schema.get("description", "")}
            for name, schema in step.parameters.items()
        }
        gate_note = ""
        if step.gates:
            gate_note = (" Output is checked by deterministic gates: "
                         + ", ".join(g.__name__ for g in step.gates) + ".")
        specs.append({
            "name": step.step_id.replace(".", "_"),
            "description": (f"[{step.process}] {step.name}. {step.description}"
                            f"{gate_note}"),
            "input_schema": {"type": "object", "properties": properties,
                             "required": []},
        })
    return specs


@dataclass
class ToolRegistry:
    """Invoke construction steps by name against one shared state."""

    state: ConstructionState = field(default_factory=ConstructionState)
    #: Injected once and passed to every learning step that accepts it.
    extractor: Optional[Any] = None
    calls: list[tuple[str, dict]] = field(default_factory=list)

    _LEARNING = {"llms4ol.term_typing", "llms4ol.taxonomy_discovery",
                 "llms4ol.relation_extraction"}

    def names(self) -> list[str]:
        return [s.step_id for s in ALL_STEPS]

    def invoke(self, name: str, arguments: Optional[dict[str, Any]] = None
               ) -> ConstructionState:
        """Run one step. ``name`` accepts either ``a.b`` or ``a_b`` form."""
        step = self._resolve(name)
        kwargs = dict(arguments or {})
        if self.extractor is not None and step.step_id in self._LEARNING:
            kwargs.setdefault("extractor", self.extractor)
        self.calls.append((step.step_id, dict(kwargs)))
        self.state = step.run(self.state, **kwargs)
        return self.state

    def _resolve(self, name: str) -> ProcessStep:
        if name in STEP_BY_ID:
            return STEP_BY_ID[name]
        dotted = name.replace("_", ".", 1)
        if dotted in STEP_BY_ID:
            return STEP_BY_ID[dotted]
        for step in ALL_STEPS:
            if step.step_id.replace(".", "_") == name:
                return step
        raise KeyError(f"unknown tool {name!r}; known: {sorted(STEP_BY_ID)}")

    def last_result(self) -> str:
        """A short natural-language result for the agent's next turn."""
        if not self.state.stages:
            return "no steps run yet"
        return str(self.state.stages[-1])

    def transcript(self) -> str:
        return "\n".join(str(s) for s in self.state.stages)
