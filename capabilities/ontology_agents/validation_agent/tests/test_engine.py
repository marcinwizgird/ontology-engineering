"""S1a engine: fixtures per check, determinism, policy, reports, CLI."""

from __future__ import annotations

import json

import pytest

from validation_agent.cli import main as cli_main
from validation_agent.engine import report
from validation_agent.engine.policy import apply_policy, load_policy
from validation_agent.engine.registry import CHECKS, implemented
from validation_agent.spec import check_catalogue as catalogue

from .conftest import FIXTURES, SAMPLES, run_file

S1A = [c.id for c in catalogue.CHECKS if c.stage == "S1a"]
CASES = [(cid, p.stem) for cid in S1A for p in sorted((FIXTURES / cid).glob("*.ttl"))
         if p.stem in ("positive", "negative", "near_miss")]


def test_every_s1a_check_has_a_detector_and_fixtures():
    assert implemented("S1a") == S1A
    for cid in S1A:
        names = {p.stem for p in (FIXTURES / cid).glob("*.ttl")}
        assert "positive" in names, cid
        if CHECKS[cid].mutation:                       # verdict-changing checks need all three
            assert {"negative", "near_miss"} <= names, cid


@pytest.mark.parametrize("check_id,variant", CASES)
def test_fixture(check_id, variant):
    ws = run_file(FIXTURES / check_id / f"{variant}.ttl")
    fired = [f for f in ws.findings if f.check_id == check_id]
    run = ws.runs[check_id]
    if variant == "positive":
        assert fired, f"{check_id} did not fire on its positive fixture ({run})"
    else:
        assert not fired, f"{check_id} fired on {variant}: {[f.message for f in fired]}"
        assert run.status in ("passed", "not-applicable"), run


def test_determinism(rail_ws):
    again = run_file(SAMPLES / "rail.ttl", declared="formal-ontology",
                     shapes=SAMPLES / "rail_shapes.ttl")
    assert [f.to_dict() for f in again.findings] == [f.to_dict() for f in rail_ws.findings]
    assert again.run_id == rail_ws.run_id
    assert again.decision == rail_ws.decision


def test_rail_sample_verdict(rail_ws):
    d = rail_ws.decision
    assert d.verdict == "reject"
    blockers = {f.check_id for f in rail_ws.findings if f.severity == "blocker"}
    assert {"SYN-03", "SYN-06", "DECL-01", "DECL-04", "HIER-05", "RSN-01"} <= blockers
    assert rail_ws.runs["RSN-02"].status == "skipped"            # inconsistent: never "passed"


def test_clean_sample_accepts():
    ws = run_file(SAMPLES / "clean_rail.ttl", declared="formal-ontology")
    assert ws.decision.verdict == "accept", [f.message for f in ws.findings if f.severity != "info"]


def test_unparseable_short_circuits():
    ws = run_file(FIXTURES / "SYN-01" / "positive.ttl")
    assert ws.decision.verdict == "reject"
    assert [f.check_id for f in ws.findings] == ["SYN-01"]
    assert all(r.status == "skipped" for cid, r in ws.runs.items() if cid != "SYN-01")


def test_waiver_w1_keyed_on_measured_level(tmp_path):
    p = tmp_path / "vocab.ttl"
    # declared formal, measured taxonomy: W1 does NOT apply (only CV and thesaurus)
    p.write_text((FIXTURES / "HIER-08" / "positive.ttl").read_text(), encoding="utf-8")
    ws = run_file(p)
    assert ws.profile.spectrum_level == "taxonomy"
    assert any(f.check_id == "HIER-08" and f.status == "confirmed" for f in ws.findings)
    # the same finding under a measured thesaurus level is waived
    findings = [f for f in ws.findings if f.check_id == "HIER-08"]
    out, d = apply_policy(findings, "thesaurus", None, ws.profile.applies, ws.policy)
    assert out[0].status == "waived" and d.waived[0]["waiver"] == "W1" and d.verdict == "accept"


def test_policy_is_pure_and_lenient_caps(rail_ws):
    lenient = load_policy("ci-lenient-v1")
    before = [f.to_dict() for f in rail_ws.findings]
    out1, d1 = apply_policy(rail_ws.findings, "formal-ontology", None, [], lenient)
    out2, d2 = apply_policy(out1, "formal-ontology", None, [], lenient)
    assert [f.to_dict() for f in rail_ws.findings] == before          # input untouched
    assert d1 == d2                                                    # idempotent
    assert {f.severity for f in out1} <= {"blocker", "minor", "info"}


def test_adjudication_cap(rail_ws):
    import copy
    f = copy.deepcopy(next(f for f in rail_ws.findings if f.severity == "blocker"))
    f.status = "adjudicatedTrue"
    out, d = apply_policy([f], "formal-ontology", None, [], rail_ws.policy)
    assert out[0].severity == "major" and d.verdict == "revise"       # OVA-T03


def test_metric01_revises_below_declared():
    ws = run_file(FIXTURES / "METRIC-01" / "positive.ttl")
    assert ws.decision.verdict == "revise"
    assert any("below the declared" in r for r in ws.decision.reasons)


def test_reports(rail_ws):
    j = report.to_json(rail_ws)
    json.dumps(j)
    assert j["verdict"]["verdict"] == "reject" and len(j["findings"]) == len(rail_ws.findings)
    md = report.to_markdown(rail_ws, review={"marks": {"f-0001": {"mark": "agree", "comment": ""}}})
    assert md.startswith("# Validation report") and "**Verdict: REJECT**" in md and "Review record" in md


def test_cli_gate_exit_codes(capsys):
    assert cli_main(["gate", str(SAMPLES / "clean_rail.ttl"), "--declared", "formal-ontology"]) == 0
    assert cli_main(["gate", str(SAMPLES / "transport_thesaurus.ttl")]) == 1
    assert cli_main(["gate", str(SAMPLES / "rail.ttl")]) == 2
    assert "REJECT" in capsys.readouterr().out
