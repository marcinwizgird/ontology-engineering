"""Ontology Validation Agent (OVA).

Stage S1a: the deterministic MVP engine (26 catalogue checks), policy packs, JSON and
Markdown reports, the tool belt, the CLI, and the review web UI with the Ontology Review
Assistant. Run from ``capabilities/ontology_agents``::

    python -m validation_agent validate path/to/ontology.ttl
    python -m validation_agent gate path/to/ontology.ttl --policy ci-lenient-v1
    python -m validation_agent ui            # http://127.0.0.1:8765
"""

ENGINE_VERSION = "0.1.0-s1a"

__all__ = ["ENGINE_VERSION"]
