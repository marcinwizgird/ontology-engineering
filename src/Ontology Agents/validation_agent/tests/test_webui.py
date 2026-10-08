"""The review web UI API: a full walk through every step."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from validation_agent.webui.app import create_app

from .conftest import SAMPLES


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv("OVA_ASSISTANT_MODEL", raising=False)
    return TestClient(create_app())


def test_front_end_served(client):
    assert "Ontology Review" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    meta = client.get("/api/meta").json()
    assert [s["id"] for s in meta["steps"]] == ["intake", "structure", "reasoning", "shacl",
                                               "custom", "triage", "expert", "verdict"]
    assert meta["assistant"]["mode"] == "offline"


def test_full_review_walk(client):
    s = client.post("/api/sessions", data={"sample": "rail"}).json()
    sid = s["session_id"]
    assert s["verdict"] == "reject"
    for step in [x["id"] for x in s["steps"]]:
        a = client.get(f"/api/sessions/{sid}/steps/{step}").json()
        assert a["step"]["id"] == step and a["status"]
        r = client.post(f"/api/sessions/{sid}/chat", json={"step": step, "message": a["step"]["questions"][0]})
        assert r.status_code == 200 and r.json()["answer"]
        assert client.post(f"/api/sessions/{sid}/signoff", json={"step": step}).status_code == 200
    tri = client.get(f"/api/sessions/{sid}/steps/triage").json()
    fid = tri["clusters"][0]["findings"][0]["finding_id"]
    r = client.post(f"/api/sessions/{sid}/marks", json={"finding_id": fid, "mark": "dispute", "comment": "deliberate"})
    assert r.status_code == 200
    assert client.get(f"/api/sessions/{sid}/steps/triage").json()["marks"][fid]["mark"] == "dispute"
    expert = client.get(f"/api/sessions/{sid}/steps/expert").json()
    assert [f["finding_id"] for f in expert["disputed"]] == [fid]
    for q in expert["checklist"]:
        client.post(f"/api/sessions/{sid}/checklist", json={"id": q["id"], "answer": "yes"})
    assert client.get(f"/api/sessions/{sid}/steps/expert").json()["status"] == "done"
    r = client.post(f"/api/sessions/{sid}/final", json={"reviewer": "Reviewer", "decision": "escalate", "note": "n"})
    assert r.json()["final"]["verdict"] == "reject"
    assert client.get(f"/api/sessions/{sid}").json()["verdict"] == "reject"    # review never changes it
    md = client.get(f"/api/sessions/{sid}/report.md").text
    assert "Review record" in md and "deliberate" in md
    j = client.get(f"/api/sessions/{sid}/report.json").json()
    assert j["review"]["final"]["decision"] == "escalate"
    assert len(client.get(f"/api/sessions/{sid}/chat/intake").json()["messages"]) == 2   # per step
    card = client.get(f"/api/sessions/{sid}/entity", params={"iri": "https://example.org/rail#Wagon"}).json()
    assert card["label"] == "wagon"


def test_upload_and_rerun(client):
    data = (SAMPLES / "transport_thesaurus.ttl").read_bytes()
    r = client.post("/api/sessions", files={"file": ("t.ttl", data, "text/turtle")},
                    data={"declared_level": "thesaurus", "policy": "ci-lenient-v1"})
    s = r.json()
    assert s["verdict"] == "revise" and s["policy"] == "ci-lenient-v1"
    r2 = client.post(f"/api/sessions/{s['session_id']}/rerun", data={"policy": "registry-default-v1"}).json()
    assert r2["policy"] == "registry-default-v1" and r2["session_id"] != s["session_id"]


def test_bad_input(client):
    assert client.post("/api/sessions", data={}).status_code == 400
    assert client.post("/api/sessions", data={"sample": "nope"}).status_code == 400
    assert client.post("/api/sessions", data={"sample": "rail", "policy": "x"}).status_code == 400
    assert client.get("/api/sessions/unknown").status_code == 404
    sid = client.post("/api/sessions", data={"sample": "clean_rail"}).json()["session_id"]
    assert client.get(f"/api/sessions/{sid}/steps/nope").status_code == 404
    assert client.post(f"/api/sessions/{sid}/marks", json={"finding_id": "f-9999", "mark": "agree"}).status_code == 404
    assert client.post(f"/api/sessions/{sid}/final", json={"reviewer": "x", "decision": "approve"}).status_code == 400
    bad = client.post("/api/sessions", files={"file": ("x.ttl", b"<a> <b> ", "text/turtle")}).json()
    assert bad["verdict"] == "reject"
    a = client.get(f"/api/sessions/{bad['session_id']}/steps/intake").json()
    assert a["load"]["loaded"] is False and a["status"] == "blocked"
