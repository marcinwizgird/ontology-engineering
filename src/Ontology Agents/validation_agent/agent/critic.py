"""Grounding critic for assistant answers (deterministic, SPECIFICATION.md s.7).

The assistant's prose may only refer to things that exist in the evidence. The critic
checks every IRI, check id and finding id the answer mentions, and every verdict it
states, against the workspace. It does not rewrite the answer; it attaches one
correction per problem, which the UI shows under the answer and the session counts
(in a healthy system the count trends to zero).
"""

from __future__ import annotations

import re

from rdflib import URIRef

from ..engine import vocab as V
from ..engine.registry import CHECKS

IRI_RE = re.compile(r"(?:https?://|urn:)[^\s`'\"<>()\[\]{}|,;]+")
CHECK_RE = re.compile(r"\b(SYN|DECL|DL|RSN|SHC|HIER|PHIER|PROP|LEX|SKOS|META|ABOX|EVO|CQ|MOD|METRIC|X)-\d{2}\b")
FINDING_RE = re.compile(r"\bf-\d{4}\b")
VERDICT_RE = re.compile(r"\bverdict (?:is|would be|will be|=)\s*\**\s*(accept|revise|reject)", re.IGNORECASE)


def ground(answer: str, ws) -> list[str]:
    corrections: list[str] = []
    g = ws.graph
    for iri in sorted(set(m.rstrip(".:") for m in IRI_RE.findall(answer))):
        if V.is_builtin(URIRef(iri)) or iri.startswith("urn:ova:"):
            continue
        ref = URIRef(iri)
        if g is None or ((ref, None, None) not in g and (None, None, ref) not in g
                         and (None, ref, None) not in g):
            corrections.append(f"<{iri}> does not occur in the ontology.")
    for m in sorted(set(CHECK_RE.finditer(answer)), key=lambda m: m.group(0)):
        if m.group(0) not in CHECKS:
            corrections.append(f"{m.group(0)} is not a check in the catalogue.")
    known = {f.finding_id for f in ws.findings}
    for fid in sorted(set(FINDING_RE.findall(answer))):
        if fid not in known:
            corrections.append(f"{fid} is not a finding of this run.")
    if ws.decision is not None:
        for v in sorted({m.lower() for m in VERDICT_RE.findall(answer)}):
            if v != ws.decision.verdict and "what-if" not in answer.lower() \
                    and "would" not in answer.lower():
                corrections.append(f"The run's verdict is {ws.decision.verdict}, not {v} "
                                   f"(policy {ws.decision.policy}).")
    return corrections
