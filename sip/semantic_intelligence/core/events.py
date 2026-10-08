"""In-process event bus.

The union of two listener models:

* Protégé — ``OWLModelManagerListener`` (``EventType.ACTIVE_ONTOLOGY_CHANGED``,
  ``ONTOLOGY_LOADED``, ``ENTITY_RENDERER_CHANGED``, ``REASONER_CHANGED``,
  ``ONTOLOGY_CLASSIFIED`` …) plus ``OWLOntologyChangeListener`` for the changes
  themselves. Hierarchy providers and the entity finder subscribe and update
  incrementally;
* VocBench — server-side notifications to watchers of a resource.

Subscribers are called synchronously after the write commits; an exception in a
subscriber is recorded, never propagated into the write path (Protégé logs and
continues for the same reason: a broken view must not roll back an edit).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

Handler = Callable[["Event"], None]

# Event types (Protégé EventType names where one exists).
COMMITTED = "CHANGES_COMMITTED"
STAGED = "CHANGES_STAGED"
ACCEPTED = "CHANGES_ACCEPTED"
REJECTED = "CHANGES_REJECTED"
UNDONE = "CHANGES_UNDONE"
ONTOLOGY_LOADED = "ONTOLOGY_LOADED"
ONTOLOGY_CLASSIFIED = "ONTOLOGY_CLASSIFIED"
REASONER_CHANGED = "REASONER_CHANGED"
ENTITY_RENDERER_CHANGED = "ENTITY_RENDERER_CHANGED"
PROJECT_CREATED = "PROJECT_CREATED"
AGENT_PROPOSAL = "AGENT_PROPOSAL"


@dataclass(frozen=True)
class Event:
    type: str
    project: str | None
    payload: dict[str, Any] = field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)
        self.errors: list[tuple[Event, BaseException]] = []
        self.log: list[Event] = []
        self.keep_log = 500

    def subscribe(self, event_type: str, handler: Handler) -> Callable[[], None]:
        """``"*"`` subscribes to everything. Returns an unsubscribe callable."""
        self._subs[event_type].append(handler)
        return lambda: self._subs[event_type].remove(handler)

    def publish(self, event: Event) -> None:
        self.log.append(event)
        del self.log[:-self.keep_log]
        for h in list(self._subs.get(event.type, ())) + list(self._subs.get("*", ())):
            try:
                h(event)
            except Exception as exc:  # noqa: BLE001 — isolation is the point
                self.errors.append((event, exc))
