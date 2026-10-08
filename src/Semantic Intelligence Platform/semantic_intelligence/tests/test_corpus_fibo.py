"""Real-corpus regression: the Protégé translation against the local FIBO checkout.

Skipped when ``Ontology Repository/FIBO/fibo`` is absent. Thresholds are the measured
values of 2026-10-04 (290 files, 131,893 triples): every anonymous class expression is
read by the axiom view, and ≥ 99.5% of anonymous superclass expressions survive
render → parse unchanged. The residue is FIBO's use of OMG Commons terms whose
declarations are not in the local checkout, which makes a few datatype/class readings
genuinely ambiguous.
"""

import glob
import logging
from pathlib import Path

import pytest
from rdflib import BNode, Graph
from rdflib.namespace import OWL, RDFS

from semantic_intelligence.owl import manchester
from semantic_intelligence.owl.hierarchy import ClassHierarchy
from semantic_intelligence.owl.model import axioms, parse_ce
from semantic_intelligence.owl.rendering import ShortFormProvider

FIBO = Path(__file__).resolve().parents[4] / "Ontology Repository" / "FIBO" / "fibo"


@pytest.fixture(scope="module")
def fibo():
    if not FIBO.exists():
        pytest.skip("FIBO corpus not present")
    logging.getLogger("rdflib").setLevel(logging.ERROR)
    g = Graph()
    for f in glob.glob(str(FIBO / "**" / "*.rdf"), recursive=True):
        if "About" in f or f"{FIBO.name}{'/'}etc" in f.replace("\\", "/"):
            continue
        g.parse(f, format="xml")
    return g


def test_axiom_view_reads_every_class_expression(fibo):
    nodes = [o for p in (RDFS.subClassOf, OWL.equivalentClass)
             for o in fibo.objects(None, p) if isinstance(o, BNode)]
    assert len(nodes) > 3000
    for n in nodes:
        parse_ce(fibo, n)                    # raises on anything unsupported


def test_manchester_round_trip_on_fibo(fibo):
    sfp = ShortFormProvider(fibo)
    sample = [a.args[1] for a in axioms(fibo, include_annotations=False)
              if a.kind == "SubClassOf" and not isinstance(a.args[1], type(a.args[0]))]
    ok = 0
    for ce in sample:
        try:
            ok += manchester.parse(manchester.render(ce, sfp), sfp) == ce
        except manchester.ManchesterError:
            pass
    assert ok / len(sample) >= 0.995, f"{ok}/{len(sample)}"


def test_hierarchy_scale(fibo):
    h = ClassHierarchy(fibo)
    assert len(h.classes) > 3000 and not h.cycles()
