"""The named-graph layout — the single source of truth for graph IRIs.

One dataset per environment; per project ``p`` a reserved IRI namespace. This is
the layout of ``architecture/ontology_builder/GOVERNANCE_FOUNDATION.md`` §3.1,
generalised from one ontology per project to the platform's two content kinds
(the ontology/TBox and the knowledge graph/ABox), which the Semantic Intelligence
Platform keeps in separate graphs so that a KG population run can never touch an
axiom.

Why named graphs carry the workflow: Semantic Turkey's change-tracking SAIL keeps
*proposed* additions and removals in dedicated staging graphs. A triple that is
still in ``staging-add`` *is* a proposal — no status flag on content, ever.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from rdflib import URIRef

_SAFE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")

#: Content graphs a principal edits (the rest are system-owned).
CONTENT_ROLES = ("main", "kg")


def check_project_id(project_id: str) -> str:
    if not _SAFE.match(project_id):
        raise ValueError(
            f"project id {project_id!r} must start with a letter and contain only "
            "letters, digits, '_', '.', '-' (max 64)")
    return project_id


@dataclass(frozen=True)
class ProjectLayout:
    """Graph IRIs for one project."""

    project: str

    def __post_init__(self) -> None:
        check_project_id(self.project)

    def _g(self, role: str) -> URIRef:
        return URIRef(f"urn:sip:p:{self.project}:{role}")

    # -- content ------------------------------------------------------------ #
    @property
    def main(self) -> URIRef:
        """Stable, validated ontology (TBox + vocabulary)."""
        return self._g("main")

    @property
    def kg(self) -> URIRef:
        """Stable, validated knowledge-graph instance data (ABox)."""
        return self._g("kg")

    # -- workflow ----------------------------------------------------------- #
    def staging_add(self, content: URIRef) -> URIRef:
        """Proposed additions to *content* (``main`` or ``kg``)."""
        return URIRef(f"{content}:staging-add")

    def staging_del(self, content: URIRef) -> URIRef:
        """Proposed removals from *content*."""
        return URIRef(f"{content}:staging-del")

    # -- derived / system --------------------------------------------------- #
    def imported(self, ontology_iri: str) -> URIRef:
        digest = hashlib.sha1(ontology_iri.encode("utf-8")).hexdigest()[:12]
        return self._g(f"imports:{digest}")

    @property
    def inferred(self) -> URIRef:
        return self._g("inferred")

    @property
    def mappings(self) -> URIRef:
        return self._g("mappings")

    @property
    def shapes(self) -> URIRef:
        return self._g("shapes")

    @property
    def metadata(self) -> URIRef:
        return self._g("metadata")

    @property
    def history(self) -> URIRef:
        return self._g("history")

    @property
    def cq(self) -> URIRef:
        """Competency questions and their executable SPARQL tests."""
        return self._g("cq")

    @property
    def evidence(self) -> URIRef:
        """Provenance of agent proposals: source spans, prompts, model ids."""
        return self._g("evidence")

    def content_graphs(self) -> tuple[URIRef, URIRef]:
        return (self.main, self.kg)

    def is_staging(self, graph: URIRef) -> bool:
        s = str(graph)
        return s.endswith(":staging-add") or s.endswith(":staging-del")

    def owns(self, graph: URIRef) -> bool:
        return str(graph).startswith(f"urn:sip:p:{self.project}:")


GOV_PROJECTS = URIRef("urn:sip:gov:projects")
GOV_USERS = URIRef("urn:sip:gov:users")
GOV_SETTINGS = URIRef("urn:sip:gov:settings")
