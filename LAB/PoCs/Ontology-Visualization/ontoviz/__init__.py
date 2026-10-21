"""ontoviz: search-first ontology views with review-gate overlays (PoC for SIP).

The modules split along the future SIP integration seam:

* ``index``         typed TBox edge index over an rdflib graph (pure, no SIP state)
* ``neighbourhood`` degree-of-interest ego view under a hard cap, with a hub guard
* ``overlays``      staged / inferred / findings / CQ-coverage annotations
* ``contract``      the view as a superset of the Ontology-Playground JSON
* ``svg``           deterministic layered SVG for static artifacts
* ``sip_ops``       the ``viz.*`` operations, registered with SIP's ``Platform.call``
* ``demo``          demo platform (fleet project with staged commits, FIBO project)
* ``server``        SIP's FastAPI app plus the static viewer under ``/viz``
* ``bench``         extraction and browser rendering benchmarks
"""

from . import _paths  # noqa: F401  (puts sip/ on sys.path)

__all__ = ["index", "neighbourhood", "overlays", "contract", "svg", "sip_ops"]
