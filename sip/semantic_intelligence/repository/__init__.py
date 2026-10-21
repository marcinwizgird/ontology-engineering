"""Ontology Repository (design: sip/architecture/components/ONTOLOGY_REPOSITORY.md).

Layer 2, like ``scope``: pure functions over graphs and plain data. The operations that
use them (``catalog.*``, ``repo.*``, the guarded ``sparql.query``) live in ``platform.py``.
"""
