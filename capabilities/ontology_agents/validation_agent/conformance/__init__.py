"""Reference Conformance Suite (V-S1a, OVA-E03): four parts, one report.

    python -m validation_agent.conformance --shacl-core <data-shapes>/data-shapes-test-suite/tests/core \
        [--owl2 <dir of W3C OWL 2 test cases>] [--json out.json]

(a) W3C SHACL Core test cases through the engine's ShaclEngine settings;
(b) W3C OWL 2 RL consistency / inconsistency cases through the ReasoningEngine;
(c) the golden corpus: real ontologies whose expected S1a findings a curator signed off;
(d) differential runs against reference oracles (ROBOT ``report`` when on PATH).

The external suites are not vendored; each part reports ``not-run`` when its input is
absent, and a part that did not run never counts as passed.
"""
