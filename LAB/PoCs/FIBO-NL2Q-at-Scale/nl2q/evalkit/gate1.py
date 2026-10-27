"""Gate 1: build-time ontology, mapping and metric health (specification §5, Gate 1).

Must-pass checks gate the LLM runs; reported checks never block them.

* ``key_integrity`` (part of 1.3, must-pass): every declared foreign key resolves on every
  instance. Ontop trusts declared keys for join elimination, so a dangling key makes an
  instance invalid: SPARQL and the gold SQL can then disagree because of the data,
  not the query. This check found the v1 witness instance (V5) invalid.
* ``run_cqs`` (1.3, must-pass): competency questions (``artifacts/eval/cq/*.rq``) as SPARQL
  ASK tests, the offline stand-in for Themis. The FIBEN ontology declares no domains or
  ranges (its relations live in the mapping), so the CQs run over the TBox plus the allowed
  edges rendered as ``rdfs:domain`` / ``rdfs:range``. Caveat: a property used by several
  edges gets several domains and ranges, so a CQ pairing one edge's domain with another's
  range would pass; each CQ names its property, which keeps this to shared properties.
* ``ova_scan`` (1.1 / 1.2, reported): SIP's Ontology Validation Agent, the offline stand-in
  for OOPS! and FOOPS!, per enrichment level, with the OOPS! pitfalls and FOOPS!-backed
  checks its catalogue covers.
* ``annotation_coverage`` (1.2, reported): definitions per enrichment level.

    python -m nl2q.evalkit.gate1            # writes artifacts/eval/gate1/gate1.json
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path

import duckdb
from rdflib import Graph, Namespace, RDFS, URIRef

from .. import paths, schema

INSTANCES = ("", "_V1", "_V2", "_V3", "_V4", "_V5", "_V6")
OUT = paths.ARTIFACTS / "eval" / "gate1"
CQ_DIR = paths.ARTIFACTS / "eval" / "cq"
OVA_HOME = paths.REPO / "capabilities" / "ontology_agents"


def present_instances(con) -> list[str]:
    have = {r[0] for r in con.execute("SELECT schema_name FROM information_schema.schemata").fetchall()}
    return [f"{paths.SCHEMA}{s}" for s in INSTANCES if f"{paths.SCHEMA}{s}" in have]


def key_integrity(schema_name: str, con=None) -> list[dict]:
    """Violated foreign keys of one instance: table.column -> target, dangling rows, kind."""
    s = schema.load()
    own = con is None
    con = con or duckdb.connect(str(paths.DB), read_only=True)
    out = []
    for t in s.tables.values():
        for f in t.fks:
            n = con.execute(
                f'SELECT count(*) FROM "{schema_name}"."{f.table}" x WHERE x."{f.column}" IS NOT NULL '
                f'AND NOT EXISTS (SELECT 1 FROM "{schema_name}"."{f.ref_table}" y '
                f'WHERE y."{f.ref_column}" = x."{f.column}")').fetchone()[0]
            if n:
                out.append({"fk": f"{f.table}.{f.column}", "target": f.ref_table, "dangling": n,
                            "kind": "subclass" if [f.column] == t.pk else "relation"})
    if own:
        con.close()
    return out


def integrity_report() -> dict:
    con = duckdb.connect(str(paths.DB), read_only=True)
    rep = {sch: key_integrity(sch, con) for sch in present_instances(con)}
    con.close()
    return rep


# ----------------------------------------------------------------------------- CQs
def schema_graph() -> Graph:
    """The TBox plus the allowed edges as rdfs:domain / rdfs:range."""
    g = Graph().parse(paths.ONTOLOGY_TTL)
    for d, p, r in json.loads((paths.KNOWLEDGE_DIR / "edges.json").read_text(encoding="utf-8")):
        g.add((URIRef(p), RDFS.domain, URIRef(d)))
        g.add((URIRef(p), RDFS.range, URIRef(r)))
    return g


def run_cqs(g: Graph | None = None) -> dict:
    g = g or schema_graph()
    results = {}
    for f in sorted(CQ_DIR.glob("*.rq")):
        text = f.read_text(encoding="utf-8")
        q = re.search(r"#\s*CQ:\s*(.*)", text)
        results[f.stem] = {"question": q.group(1) if q else "", "pass": bool(g.query(text).askAnswer)}
    passed = sum(r["pass"] for r in results.values())
    return {"passed": passed, "total": len(results), "rate": round(passed / len(results), 4) if results else None,
            "results": results}


# ----------------------------------------------------------------------------- OVA (OOPS! / FOOPS! stand-in)
def _catalogue_coverage() -> dict:
    sys.path.insert(0, str(OVA_HOME))
    from validation_agent.spec import check_catalogue as cat   # noqa: PLC0415 - optional capability
    src = Path(cat.__file__).read_text(encoding="utf-8")
    return {"checks": len(cat.CHECKS),
            "oops_pitfalls_referenced": sorted({f"P{int(n):02d}" for n in re.findall(r"OOPS!? ?P(\d+)", src)}),
            "families_with_oops_oracle": src.count('"OOPS!"'),
            "families_with_foops_oracle": src.count('"FOOPS!"')}


def ova_scan(enriched: bool) -> dict:
    """Run the validation agent on the ontology (E0) or the ontology plus the enrichment
    annotations (E1); counts by severity and by check."""
    OUT.mkdir(parents=True, exist_ok=True)
    tag = "e1" if enriched else "e0"
    onto = paths.ONTOLOGY_TTL
    if enriched:
        g = Graph().parse(paths.ONTOLOGY_TTL).parse(paths.KNOWLEDGE_DIR / "enrichment.ttl")
        onto = paths.CACHE / "fiben-ontology-e1.ttl"
        g.serialize(onto, format="turtle")
    js, md = OUT / f"ova_{tag}.json", OUT / f"ova_{tag}.md"
    subprocess.run([sys.executable, "-m", "validation_agent", "validate", str(onto), "--declared",
                    "formal-ontology", "--json", str(js), "--md", str(md)],
                   cwd=OVA_HOME, check=True, capture_output=True, env={**__import__("os").environ,
                                                                         "PYTHONIOENCODING": "utf-8"})
    rep = json.loads(js.read_text(encoding="utf-8"))
    v = rep["verdict"]
    reportable = set(v["reportable"])
    by_check: dict[str, dict[str, int]] = {}
    for f in rep["findings"]:
        if f["finding_id"] in reportable:
            c = by_check.setdefault(f["check_id"], {})
            c[f["severity"]] = c.get(f["severity"], 0) + 1
    return {"verdict": v["verdict"], "by_severity": v["counts"], "waived": len(v["waived"]),
            "by_check": dict(sorted(by_check.items())), "level": rep["profile"]["spectrum_level"],
            "report": md.name}


# ----------------------------------------------------------------------------- coverage
def annotation_coverage() -> dict:
    with (paths.KNOWLEDGE_DIR / "enrichment.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    e0 = sum(r["source"] == "fibo" for r in rows)
    e1 = sum(r["defined"] == "1" for r in rows)
    return {"terms": len(rows), "E0": e0, "E1": e1,
            "E1_missing": sorted(r["local"] for r in rows if r["defined"] != "1")}


def run(integrity: bool = True) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    rep = {"annotation_coverage": annotation_coverage(), "cq": run_cqs(),
           "ova": {"E0": ova_scan(False), "E1": ova_scan(True), "catalogue": _catalogue_coverage()}}
    if integrity:
        rep["key_integrity"] = integrity_report()
    prev = OUT / "gate1.json"
    if prev.exists():                       # keep sections written by other steps (ceiling, mutation, SHACL)
        old = json.loads(prev.read_text(encoding="utf-8"))
        rep = {**old, **rep}
    prev.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    return rep


if __name__ == "__main__":
    out = run(integrity="--no-integrity" not in sys.argv)
    print(json.dumps({k: v for k, v in out.items() if k != "cq"} | {"cq": {k: out["cq"][k] for k in ("passed", "total")}},
                     indent=1)[:4000])
