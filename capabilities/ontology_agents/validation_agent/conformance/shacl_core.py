"""(a) W3C SHACL Core test suite runner (``data-shapes-test-suite/tests/core``).

Each test file is its own manifest. For ``sht:Validate`` entries the data and shapes graph
are run through :func:`engine.shacl.validate` (the same settings SHC-02/SHC-08 use), and
the outcome is compared with the expected ``sh:ValidationReport`` on ``sh:conforms`` and
on the multiset of (focus node, path, constraint component, severity, value) per result.
``sh:resultMessage`` and ``sh:sourceShape`` are not compared (the W3C suite allows
implementations to differ there). Blank nodes are compared by their owning entity.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from rdflib import Graph, Namespace
from rdflib.namespace import RDF

from ..engine import shacl
from ..engine.vocab import SH, local_name, rdf_list

MF = Namespace("http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#")
SHT = Namespace("http://www.w3.org/ns/shacl-test#")


def _key(focus, path, component, severity, value) -> tuple:
    return (focus or "", path or "", component or "", severity or "", value or "")


def _expected(g: Graph, report_node) -> tuple[bool, Counter]:
    conforms = str(g.value(report_node, SH.conforms)).lower() == "true"
    keys = Counter()
    for r in g.objects(report_node, SH.result):
        keys[_key(shacl._render(g.value(r, SH.focusNode), g),
                  shacl._render(g.value(r, SH.resultPath)),
                  local_name(g.value(r, SH.sourceConstraintComponent) or ""),
                  local_name(g.value(r, SH.resultSeverity) or ""),
                  shacl._render(g.value(r, SH.value), g))] += 1
    return conforms, keys


def run_file(path: Path) -> list[dict]:
    g = Graph()
    g.parse(path, format="turtle", publicID=path.resolve().as_uri())
    out = []
    for manifest in g.subjects(RDF.type, MF.Manifest):
        for entry in rdf_list(g, g.value(manifest, MF.entries)):
            status = g.value(entry, MF.status)
            kind = g.value(entry, RDF.type)
            name = f"{path.parent.name}/{local_name(entry)}"
            if status is not None and status != SHT.approved:
                out.append({"test": name, "outcome": "skipped", "reason": f"status {local_name(status)}"})
                continue
            action = g.value(entry, MF.action)
            data_ref, shapes_ref = g.value(action, SHT.dataGraph), g.value(action, SHT.shapesGraph)
            data = _load(path, g, data_ref)
            shapes = _load(path, g, shapes_ref)
            result = g.value(entry, MF.result)
            try:
                conforms, results = shacl.validate(data, shapes)
            except Exception as exc:  # noqa: BLE001 - a crash is an outcome
                ok = result == SHT.Failure
                out.append({"test": name, "outcome": "pass" if ok else "fail",
                            "reason": f"engine raised {type(exc).__name__}"})
                continue
            if result == SHT.Failure or kind != SHT.Validate:
                out.append({"test": name, "outcome": "fail", "reason": "expected a failure"})
                continue
            exp_conforms, exp_keys = _expected(g, result)
            got = Counter(_key(r.focus, r.path, r.component, r.sh_severity, r.value) for r in results)
            ok = exp_conforms == conforms and exp_keys == got
            rec = {"test": name, "outcome": "pass" if ok else "fail"}
            if not ok:
                rec["reason"] = (f"conforms expected {exp_conforms} got {conforms}; "
                                 f"missing {sorted((exp_keys - got).elements())[:3]}; "
                                 f"extra {sorted((got - exp_keys).elements())[:3]}")
            out.append(rec)
    return out


def _load(path: Path, manifest_graph: Graph, ref) -> Graph:
    if ref is None or str(ref) == path.resolve().as_uri():
        return manifest_graph
    other = Path(str(ref).replace("file:///", "").replace("file://", ""))
    if not other.exists():
        other = path.parent / local_name(ref)
    g = Graph()
    g.parse(other, format="turtle", publicID=other.resolve().as_uri())
    return g


def run(root: str | Path) -> dict:
    root = Path(root)
    if not root.exists():
        return {"part": "shacl-core", "status": "not-run", "reason": f"{root} not found"}
    results = []
    for f in sorted(root.rglob("*.ttl")):
        if f.name == "manifest.ttl":
            continue
        results.extend(run_file(f))
    counts = Counter(r["outcome"] for r in results)
    applicable = counts["pass"] + counts["fail"]
    return {"part": "shacl-core", "status": "ran", "tests": len(results), **counts,
            "pass_rate": round(counts["pass"] / applicable, 4) if applicable else None,
            "failures": [r for r in results if r["outcome"] == "fail"]}
