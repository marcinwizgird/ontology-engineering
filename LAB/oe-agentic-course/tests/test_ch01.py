"""Chapter 1: the ontology engine, the corpus, the toolkit, the registry, and the
agentlab modules the problem set relies on. None of these call a model."""

import json

import dspy
import pytest

from agentlab import evaluation as ev, llm, ontology as ont
from agentlab.grading import Grader
from agentlab.sparql import SparqlStore
from conftest import chapter_path

chapter_path("ch01")
import ch01_agentic as A  # noqa: E402
import ch01_toolkit as ch1  # noqa: E402
import corpus  # noqa: E402


def test_detectors_agree_with_every_hand_label():
    assert corpus.verify_corpus() == []
    assert A.validate_gold() == []


def test_spectrum_reasons_from_counts():
    res = ont.classify_spectrum(ont.load_graph(corpus.get("food-thesaurus").turtle))
    assert res["level"] == "thesaurus" and res["evidence"]
    m = ont.graph_metrics(ont.load_graph(corpus.get("awo").turtle))
    assert m["classes"] > 10 and m["restrictions"] > 0


def test_integration_needs_the_reasoner():
    rows = ch1.integration_report()["rows"]
    assert [r["recall"] for r in rows] == [0.0, 0.0, 1.0]


def test_sparql_store_returns_plain_rows():
    store = SparqlStore.in_memory(corpus.get("awo").turtle)
    rows = store.select("SELECT ?c WHERE { ?c a owl:Class } LIMIT 3")
    assert rows and all(isinstance(v, str) for r in rows for v in r.values())
    assert store.ask("ASK { awo:Giraffe rdfs:subClassOf ?x }")


def test_evidence_bundle_is_the_measurements():
    ev_ = json.loads(A.gather_evidence("safety-incidents"))
    assert set(ev_) == {"submission", "metrics", "spectrum", "scanner_counts",
                       "scanner_findings", "imports"}
    g = ont.load_graph(A.get("safety-incidents").turtle)
    assert ev_["spectrum"]["level"] == ont.classify_spectrum(g)["level"]
    assert sorted({f["smell"] for f in ev_["scanner_findings"]}) == sorted(ont.smell_summary(g))


def test_score_reports_and_rulebook():
    assert ev.set_f1(["a", "b"], ["b", "c"])[2] == pytest.approx(0.5)
    assert ev.parse_label_list('["a", "b"]') == ["a", "b"] == ev.parse_label_list("a, b")
    line = A.INTAKE_RULEBOOK["apply-waivers"].feedback_line()
    assert line.startswith("VIOLATED GUIDELINE apply-waivers:")
    text = A.INTAKE_RULEBOOK.as_guidelines("Preamble.")
    assert text.startswith("Preamble.\n- ") and text.count("\n- ") == len(A.INTAKE_RULEBOOK)


def test_evaluate_dataset_counts_violations():
    rows = A.build_dataset("dev")[:3]
    program = lambda submission: dspy.Prediction(level="taxonomy")       # noqa: E731
    scorer = lambda gold, pred: ev.ScoreReport(                         # noqa: E731
        float(pred.level == gold.level), [], [] if pred.level == gold.level else ["x"])
    out = ev.evaluate_dataset(program, rows, scorer)
    assert out["n"] == 3 and {r["item"] for r in out["rows"]} == {r.id for r in rows}
    assert sum(out["violations"].values()) == sum(r.level != "taxonomy" for r in rows)


def test_grader_records_without_raising(capsys):
    g = Grader("t")
    with g.check("P1", points=2):
        assert True
    with g.check("P2", points=3):
        raise NotImplementedError
    assert g.earned == 2 and g.available == 5 and not g.all_passed()
    assert "NOT RUN" in g.summary(["P1", "P2", "P3"])


def test_meter_reads_history():
    fake = type("LM", (), {"history": []})()
    with llm.meter(fake) as cost:
        fake.history.append({"usage": {"prompt_tokens": 10, "completion_tokens": 2},
                             "cost": 0.001})
        fake.history.append({"usage": {}, "cost": None})               # a cached answer
    assert cost == {"calls": 2, "input_tokens": 10, "output_tokens": 2, "usd": 0.001}


def test_credentials_are_required_before_a_call(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        llm.dspy_lm()


# ------------------------------------------------------------------ report checks (B3)
def test_report_measurements():
    assert A.offending_terms("signalling-equipment") == {
        "subsumption-cycle": ["LinesideEquipment"], "no-disjointness": ["Signal"]}
    assert {"Signal", "LinesideEquipment"} <= A.terms_in("signalling-equipment")
    assert A.REPORT_RULEBOOK.ids == ["state-the-decision", "name-offending-terms",
                                     "no-invented-terms", "cite-a-measurement"]


# ------------------------------------------------------------------ real submissions (D, E)
def test_fibo_sample_and_import_report():
    real = A.build_real_dataset()
    assert len(real) == 40 and len({r.id for r in real}) == 40
    assert all(r.level in ont.SPECTRUM_LEVELS for r in real)
    with_undeclared = [r for r in real if "undeclared-term" in r.raw_smells]
    assert len(with_undeclared) > 20                      # judged without its imports
    explained = 0
    for r in with_undeclared:
        rep = A.import_report(r.id)
        assert set(rep["undeclared_terms_declared_in_imports"]) | \
            set(rep["undeclared_terms_unexplained"]) == set(A.undeclared_terms(r.id))
        explained += bool(rep["undeclared_terms_declared_in_imports"])
    assert explained > 10                                  # the imports do declare them
    assert any("omg.org" in i for r in real for i in A.unresolved_imports(r.id))


def test_evidence_is_bounded_and_carries_imports():
    rows = A.build_real_dataset()
    ev_ = json.loads(A.gather_evidence(rows[0].id))
    assert len(ev_["scanner_findings"]) <= A.MAX_FINDINGS
    assert sum(ev_["scanner_counts"].values()) >= len(ev_["scanner_findings"])
    assert ev_["imports"]["declared"]
    assert json.loads(A.gather_evidence("safety-incidents"))["imports"]["declared"] == []


def test_register_an_outside_ontology():
    sub = A.register("t-outside", corpus.get("animals-taxonomy").turtle, team="t",
                     declared_level="taxonomy", purpose="test")
    assert A.get("t-outside") is sub
    assert json.loads(A.gather_evidence("t-outside"))["spectrum"]["level"] == "taxonomy"
    with pytest.raises(ValueError):
        A.register("t-bad", "x", team="t", declared_level="ontology", purpose="p")


def test_meter_prices_real_calls_and_not_cache_hits():
    hit = type("R", (), {"cache_hit": True})()
    fake = type("LM", (), {"history": []})()
    with llm.meter(fake) as cost:
        fake.history.append({"usage": {}, "cost": 0.5, "response": hit})       # replayed
        fake.history.append({"model": "anthropic/claude-sonnet-5-5", "cost": None,
                             "usage": {"prompt_tokens": 1_000, "completion_tokens": 100}})
    assert cost["calls"] == 2 and cost["usd"] == round((1_000 * 2 + 100 * 10) / 1e6, 4)
