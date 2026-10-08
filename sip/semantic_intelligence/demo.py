"""End-to-end demonstration: brief + documents + a table → validated ontology →
populated knowledge graph → release gate → grounded answers.

Run offline (deterministic simulators, no key, no cost)::

    PYTHONPATH="sip" python -m semantic_intelligence.demo

With ``SIP_MODEL=claude-opus-5-5`` (and credentials) the same flow runs on Claude;
critics, staging and gates are identical.
"""

from __future__ import annotations

import json
import sys

from .agents.orchestrator import Conductor
from .core.principal import Principal
from .platform import Platform

BRIEF = (
    "The fleet team needs an ontology of vehicles and their parts. "
    "Every vehicle has one or more wheels. "
    "We need to know which manufacturers exist. "
    "Every manufacturer has a country.")

DOCUMENT = (
    "A car is a kind of vehicle. A truck is a kind of vehicle. "
    "Every vehicle has several wheels. Every vehicle has an engine. "
    "A manufacturer has a founding year recorded as an integer. "
    "Every vehicle is made by a manufacturer. "
    "Engines, such as diesel engines and electric motors, power vehicles.")

TABLE = (
    "manufacturer_id,name,foundingYear\n"
    "m1,Volvo Cars,1927\n"
    "m2,Volvo Car Corporation,1927\n"
    "m3,Scania,1891\n"
    "m4,Tatra,eighteen-fifty\n")


def run(out=sys.stdout, verbose: bool = True) -> dict:
    P = Platform()
    admin = P.registry.add_principal(Principal("admin", "Administrator", is_admin=True))
    pm = P.registry.add_principal(Principal("pat", "Pat (project manager)"))
    val = P.registry.add_principal(Principal("val", "Val (validator)"))
    P.call(admin, None, "governance.createProject", name="fleet",
           base_uri="https://example.org/fleet", languages=["en", "fr"])
    P.call(admin, "fleet", "governance.bind", principal="pat", roles=["projectmanager"])
    P.call(admin, "fleet", "governance.bind", principal="val", roles=["validator"])

    conductor = Conductor(P)
    enabled = conductor.enable_agents("fleet", by=pm)

    def say(*a):
        if verbose:
            print(*a, file=out)

    say(f"agents enabled: {', '.join(enabled)}")
    reports = conductor.run("fleet", pm, brief=BRIEF, documents={"doc-1": DOCUMENT},
                            tables={"tbl-manufacturers": TABLE},
                            model_classes=["Vehicle"])
    for r in reports:
        say(f"\n== {r.stage} [{r.state}]")
        for run_ in r.runs:
            say(f"   {run_['agent']:12} proposed={run_['proposed']} submitted={run_['submitted']}"
                f" critic-rejected={run_['rejected_by_critic']} errors={run_['errors']}")

    # ---- the human review gate ------------------------------------------- #
    reviews = reports[-1].output["reviews"]
    accepted = rejected = 0
    for rv in reviews:
        if rv["recommendation"] == "accept":
            P.call(val, "fleet", "validation.accept", commit=rv["commit"])
            accepted += 1
        else:
            P.call(val, "fleet", "validation.reject", commit=rv["commit"])
            rejected += 1
    say(f"\nvalidator: accepted {accepted}, rejected {rejected} of {len(reviews)} proposals")
    P.call(pm, "fleet", "lifecycle.setStage", stage="review", state="done",
           note="review gate closed by project manager")

    later = conductor.resume("fleet", pm, questions=[])
    for c in P.call(val, "fleet", "validation.pending"):          # KG population review
        P.call(val, "fleet", "validation.accept", commit=c["id"])
    gate = P.call(pm, "fleet", "quality.releaseGate")
    qa = [conductor.agent("fleet", "assistant").run("fleet", q).output
          for q in ("Which manufacturers exist?", "Which vehicles are there?")]

    say("\n== populate/reason/publish")
    for r in later:
        say(f"   {r.stage} [{r.state}]")
    say(f"release gate: passed={gate['passed']} reasons={gate['reasons']}")
    for a in qa:
        say(f"Q&A: {a['answer']}")
    tree = P.call(pm, "fleet", "browse.classTree")
    say("\nclass roots: " + ", ".join(n["show"] for n in tree))
    metrics = P.call(pm, "fleet", "browse.metrics")
    say("metrics: " + json.dumps(metrics["Metrics"]))
    say("agent metrics: " + json.dumps(conductor.runtime.metrics("fleet"), indent=1))
    return {"platform": P, "conductor": conductor, "reports": reports, "gate": gate,
            "qa": qa, "accepted": accepted, "rejected": rejected}


if __name__ == "__main__":
    run()
