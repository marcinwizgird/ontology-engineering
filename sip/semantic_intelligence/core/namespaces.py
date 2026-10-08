"""Vocabularies used across the platform.

Two of these are not ours:

* ``CL`` — Semantic Turkey's change-log vocabulary
  (``it.uniroma2.art.semanticturkey.changetracking.vocabulary.CHANGELOG``). The
  history graph uses it unchanged so that a history exported from this platform
  reads the same as one exported from VocBench 3.
* ``VALIDATION`` — Semantic Turkey's staging vocabulary, likewise kept.

``SIP`` is the platform's own namespace for things neither tool had a term for
(agent runs, proposals, competency questions, project metadata).
"""

from __future__ import annotations

from rdflib import Namespace
from rdflib.namespace import DCTERMS, OWL, PROV, RDF, RDFS, SKOS, XSD

#: Semantic Turkey change log (st-changetracking-sail, CHANGELOG.java).
CL = Namespace("http://semanticturkey.uniroma2.it/ns/changelog#")
#: Semantic Turkey validation/staging vocabulary (VALIDATION.java).
VALIDATION = Namespace("http://semanticturkey.uniroma2.it/ns/validation#")
#: SKOS-XL.
SKOSXL = Namespace("http://www.w3.org/2008/05/skos-xl#")
#: Alignment API format.
ALIGN = Namespace("http://knowledgeweb.semanticweb.org/heterogeneity/alignment#")
#: OntoLex-Lemon and LIME.
ONTOLEX = Namespace("http://www.w3.org/ns/lemon/ontolex#")
LIME = Namespace("http://www.w3.org/ns/lemon/lime#")
#: VoID and DCAT for the metadata registry.
VOID = Namespace("http://rdfs.org/ns/void#")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
#: The platform's own vocabulary.
SIP = Namespace("https://w3id.org/sip/ns#")

__all__ = ["CL", "VALIDATION", "SKOSXL", "ALIGN", "ONTOLEX", "LIME", "VOID", "DCAT",
           "SIP", "OWL", "RDF", "RDFS", "SKOS", "XSD", "DCTERMS", "PROV"]
