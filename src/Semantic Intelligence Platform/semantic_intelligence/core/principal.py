"""Principals — people and machines are the same kind of thing.

VocBench 3 added *machine* accounts (``Machines`` service) so that scripts call
the API under their own identity; the Semantic Intelligence Platform makes every
agent such a principal. That single decision is what lets the agent layer reuse
the human governance model unchanged: an agent's write is authorised by the same
PDP, recorded in the same history and — because machines are forced through
staging — reviewed in the same validation queue as a junior editor's.
"""

from __future__ import annotations

from dataclasses import dataclass

from rdflib import URIRef


@dataclass(frozen=True)
class Principal:
    id: str
    display_name: str = ""
    is_admin: bool = False
    is_machine: bool = False
    #: For machines: the human on whose behalf the agent acts (delegation chain).
    on_behalf_of: str | None = None

    @property
    def iri(self) -> URIRef:
        kind = "machine" if self.is_machine else "user"
        return URIRef(f"urn:sip:{kind}:{self.id}")

    def __str__(self) -> str:
        return self.display_name or self.id


SYSTEM = Principal("system", "System", is_admin=True, is_machine=True)
