"""The deterministic validation engine: the only source of findings and verdicts.

It depends on rdflib, owlrl, pyshacl and networkx only (OVA-Q01) and has no dependency
on the agent, tools or web UI packages, so it can ship alone as the R1 library.
"""
