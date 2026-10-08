"""Expose the workflow steps as **function tools** for an agentic system.

Because every workflow step is the invocation of a single
``state -> state`` function (see ``steps.py``), the same functions can be
surfaced to an LLM agent as callable tools.  This module:

* generates OpenAI/Anthropic-style JSON tool specifications from the step
  metadata (:func:`tool_specs`), and
* provides a :class:`ToolRegistry` that holds the shared
  :class:`~bottomup_ontology.state.WorkflowState` and dispatches tool calls by
  name (:meth:`ToolRegistry.invoke`).

The agent therefore "drives" the bottom-up pipeline by calling
``step_text_cleaning``, ``step_term_extraction``, ... in whatever order its
policy dictates, while the registry keeps the evolving ontology in one place.
"""

from __future__ import annotations

from typing import Any, Callable

from .state import WorkflowState
from .steps import STEP_CLASSES, WorkflowStep


def _step_tool_spec(cls: type[WorkflowStep]) -> dict[str, Any]:
    """Build a single JSON tool spec from a step class."""
    properties = {k: dict(v) for k, v in cls.parameters.items()}
    # strip non-JSON-schema "default" hints into description-friendly schema
    required = [k for k, v in properties.items() if "default" not in v]
    techniques = ", ".join(cls.techniques) if cls.techniques else "—"
    description = (
        f"{cls.description} "
        f"[{'mandatory' if cls.mandatory else 'optional'} step; "
        f"techniques: {techniques}]. "
        f"Operates on the shared workflow state and returns updated artifacts."
    )
    return {
        "type": "function",
        "function": {
            "name": cls.func.__name__,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
            "x-step-id": cls.step_id,
            "x-mandatory": cls.mandatory,
        },
    }


def tool_specs(step_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Return JSON tool specs for the requested steps (default: all)."""
    ids = step_ids or list(STEP_CLASSES)
    return [_step_tool_spec(STEP_CLASSES[sid]) for sid in ids]


# Map tool (function) name -> step id, for dispatching agent tool calls.
TOOL_NAME_TO_STEP_ID: dict[str, str] = {
    cls.func.__name__: cls.step_id for cls in STEP_CLASSES.values()
}


class ToolRegistry:
    """Holds the shared state and lets an agent call steps by tool name."""

    def __init__(self, state: WorkflowState | None = None) -> None:
        self.state = state or WorkflowState()
        self._steps: dict[str, WorkflowStep] = {
            sid: cls() for sid, cls in STEP_CLASSES.items()
        }

    # discovery -------------------------------------------------------------- #
    def specs(self, step_ids: list[str] | None = None) -> list[dict[str, Any]]:
        return tool_specs(step_ids)

    def tool_names(self) -> list[str]:
        return list(TOOL_NAME_TO_STEP_ID)

    def callables(self) -> dict[str, Callable[..., WorkflowState]]:
        """Return ``{tool_name: bound_callable(**params)}`` for direct use."""
        return {
            cls.func.__name__: (lambda c=cls, s=self: lambda **p: c().run(s.state, **p))()
            for cls in STEP_CLASSES.values()
        }

    # invocation ------------------------------------------------------------- #
    def invoke(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a tool call by name and return a JSON-serialisable result.

        This is the shape an agent loop expects: it hands back a small summary
        plus the latest trace line, not the whole state object.
        """
        if tool_name not in TOOL_NAME_TO_STEP_ID:
            raise KeyError(f"unknown tool {tool_name!r}. Available: {self.tool_names()}")
        step = self._steps[TOOL_NAME_TO_STEP_ID[tool_name]]
        self.state = step.run(self.state, **(arguments or {}))
        return {
            "tool": tool_name,
            "step_id": step.step_id,
            "ontology": self.state.ontology.summary(),
            "trace": self.state.log[-1] if self.state.log else "",
        }
