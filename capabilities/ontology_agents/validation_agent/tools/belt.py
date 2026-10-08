"""The tool belt (SPECIFICATION.md s.8): narrow, read-only, logged tools bound to one
:class:`~validation_agent.workspace.ValidationWorkspace`.

JSON in, JSON out; errors come back as ``"ERROR: ..."`` text. Each description says
*when* to call the tool. The same objects serve the Ontology Review Assistant
(Anthropic tool use), LangChain (:func:`as_langchain_tools`) and, from S1b, MCP.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from ..engine import vocab as V
from ..engine.policy import apply_policy
from ..engine.registry import CHECKS, FAMILIES, describe

MAX_ROWS = 100
FORBIDDEN_SPARQL = re.compile(
    r"\b(INSERT|DELETE|LOAD|CLEAR|CREATE|DROP|COPY|MOVE|ADD|SERVICE|WITH)\b", re.IGNORECASE)

TOOL_TO_EVIDENCE = {
    "profile": "profile", "check_catalogue": "catalogue", "get_finding": "finding",
    "run_check": "finding", "run_family": "finding", "reason": "entailment",
    "shacl_validate": "shacl", "describe_entity": "entity-card",
    "hierarchy_neighbourhood": "hierarchy", "search_entities": "entity-card",
    "sparql_select": "query", "sparql_ask": "query", "apply_policy": "verdict",
}
"""Which kind of evidence each tool buys, so a trajectory says what a decision used."""

TOOL_PROFILES = {
    "readonlyInspect": ["profile", "check_catalogue", "get_finding", "describe_entity",
                        "hierarchy_neighbourhood", "search_entities", "sparql_select", "sparql_ask"],
    "validate": ["run_check", "run_family", "reason", "shacl_validate", "apply_policy"],
}

_IRI = {"type": "string", "description": "Full IRI of the entity, e.g. https://ex.org/rail#Locomotive"}
TOOL_SPECS: list[dict[str, Any]] = [
    {"name": "profile", "cost": "cheap",
     "description": "Measured profile of the submission: spectrum level, declared level, OWL 2 "
                    "profiles, expressivity and counts. Call first when a question is about what "
                    "the ontology is or why a check did not run.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "check_catalogue", "cost": "cheap",
     "description": "Catalogue entries (what a check detects, why it matters, severity, method). "
                    "Call to explain a check id such as HIER-05, or list a family's checks.",
     "input_schema": {"type": "object", "properties": {
         "check_id": {"type": "string"}, "family": {"type": "string"}}}},
    {"name": "get_finding", "cost": "cheap",
     "description": "One finding by id (f-0007) with its evidence, fix hint and catalogue entry. "
                    "Call before explaining or proposing a fix for a specific finding.",
     "input_schema": {"type": "object", "properties": {"finding_id": {"type": "string"}},
                      "required": ["finding_id"]}},
    {"name": "run_check", "cost": "cheap",
     "description": "Run status and findings of one check in this run.",
     "input_schema": {"type": "object", "properties": {"check_id": {"type": "string"}},
                      "required": ["check_id"]}},
    {"name": "run_family", "cost": "cheap",
     "description": "Run status and findings of every check in a family (SYN, DECL, DL, RSN, "
                    "SHC, HIER, PROP, LEX, SKOS, META, METRIC).",
     "input_schema": {"type": "object", "properties": {"family": {"type": "string"}},
                      "required": ["family"]}},
    {"name": "reason", "cost": "moderate",
     "description": "OWL 2 RL reasoning result: consistency, clashes, unsatisfiable classes "
                    "(root/derived), inferred equivalences, completeness. Call for questions about "
                    "contradictions or empty classes.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "shacl_validate", "cost": "moderate",
     "description": "SHACL results against the supplied shapes ('supplied') or the house-rule "
                    "pack ('house').",
     "input_schema": {"type": "object", "properties": {
         "which": {"type": "string", "enum": ["supplied", "house"]}}, "required": ["which"]}},
    {"name": "describe_entity", "cost": "cheap",
     "description": "Entity card: types, labels, definitions, parents, children, restrictions, "
                    "domain/range and the findings that mention it. Call before saying anything "
                    "about a specific class or property.",
     "input_schema": {"type": "object", "properties": {"iri": _IRI}, "required": ["iri"]}},
    {"name": "hierarchy_neighbourhood", "cost": "cheap",
     "description": "Ancestors (up to `up` levels), siblings, children (down to `down` levels) and "
                    "disjointness of a class.",
     "input_schema": {"type": "object", "properties": {
         "iri": _IRI, "up": {"type": "integer"}, "down": {"type": "integer"}}, "required": ["iri"]}},
    {"name": "search_entities", "cost": "cheap",
     "description": "Find entities whose label or local name contains the text. Call to resolve a "
                    "name the user typed into an IRI.",
     "input_schema": {"type": "object", "properties": {"text": {"type": "string"}},
                      "required": ["text"]}},
    {"name": "sparql_select", "cost": "cheap",
     "description": f"Read-only SPARQL SELECT over the asserted graph; at most {MAX_ROWS} rows. "
                    "No updates, no SERVICE.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}},
                      "required": ["query"]}},
    {"name": "sparql_ask", "cost": "cheap",
     "description": "Read-only SPARQL ASK over the asserted graph.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}},
                      "required": ["query"]}},
    {"name": "apply_policy", "cost": "cheap",
     "description": "The policy decision: verdict, reasons, counts, waived findings. Optionally "
                    "under another policy pack (e.g. ci-lenient-v1) for a what-if; the run's "
                    "verdict itself never changes.",
     "input_schema": {"type": "object", "properties": {"policy": {"type": "string"}}}},
]
SPEC_BY_NAME = {t["name"]: t for t in TOOL_SPECS}


class ToolBelt:
    def __init__(self, ws, actor: str = "assistant") -> None:
        self.ws = ws
        self.actor = actor

    # ------------------------------------------------------------------ dispatch
    def call(self, name: str, args: dict | None = None) -> Any:
        args = args or {}
        t0 = time.perf_counter()
        fn: Callable | None = getattr(self, f"t_{name}", None) if name in SPEC_BY_NAME else None
        try:
            result = fn(**args) if fn else f"ERROR: unknown tool {name!r}"
        except TypeError as exc:
            result = f"ERROR: bad arguments for {name}: {exc}"
        except Exception as exc:  # tools never raise into the caller
            result = f"ERROR: {type(exc).__name__}: {exc}"
        self.ws.tool_log.append({
            "tool": name, "args": args, "actor": self.actor,
            "evidence": TOOL_TO_EVIDENCE.get(name), "ok": not (isinstance(result, str)
                                                               and result.startswith("ERROR")),
            "millis": int((time.perf_counter() - t0) * 1000)})
        return result

    def call_json(self, name: str, args: dict | None = None) -> str:
        r = self.call(name, args)
        return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False, default=str)

    # ------------------------------------------------------------------ helpers
    def _graph(self):
        if self.ws.graph is None:
            raise ValueError("the document did not parse (SYN-01); nothing to inspect")
        return self.ws.graph

    def _iri(self, iri: str) -> URIRef:
        g = self._graph()
        ref = URIRef(iri.strip("<> "))
        if (ref, None, None) not in g and (None, None, ref) not in g:
            raise ValueError(f"<{iri}> does not occur in the ontology; try search_entities")
        return ref

    def _findings_for(self, check_ids=None, iri: str | None = None) -> list[dict]:
        out = []
        for f in self.ws.findings:
            if check_ids is not None and f.check_id not in check_ids:
                continue
            if iri is not None and iri != f.focus and iri not in f.related:
                continue
            out.append({"finding_id": f.finding_id, "check_id": f.check_id,
                        "severity": f.severity, "status": f.status, "focus": f.focus,
                        "message": f.message, "fix_hint": f.fix_hint})
        return out

    # ------------------------------------------------------------------ tools
    def t_profile(self):
        p = self.ws.profile
        if p is None:
            raise ValueError("no profile: the document did not parse")
        return p.to_dict()

    def t_check_catalogue(self, check_id: str | None = None, family: str | None = None):
        if check_id:
            if check_id not in CHECKS:
                raise ValueError(f"{check_id} is not in the catalogue")
            return describe(check_id)
        if family:
            if family not in FAMILIES:
                raise ValueError(f"unknown family {family}; known: {', '.join(FAMILIES)}")
            return [{"id": c.id, "title": c.title, "severity": c.severity, "stage": c.stage,
                     "applies": list(c.applies)} for c in CHECKS.values() if c.family == family]
        return [{"family": f.code, "title": f.title, "purpose": f.purpose} for f in FAMILIES.values()]

    def t_get_finding(self, finding_id: str):
        f = self.ws.finding(finding_id)
        if f is None:
            raise ValueError(f"no finding {finding_id}")
        return {**f.to_dict(), "check": describe(f.check_id)}

    def t_run_check(self, check_id: str):
        run = self.ws.runs.get(check_id)
        if run is None:
            raise ValueError(f"{check_id} did not run in this stage ({self.ws.stage})")
        return {"run": run.to_dict(), "findings": self._findings_for({check_id})}

    def t_run_family(self, family: str):
        ids = [cid for cid in self.ws.runs if CHECKS[cid].family == family]
        if not ids:
            raise ValueError(f"no check of family {family} ran in this stage")
        return {"runs": [self.ws.runs[c].to_dict() for c in ids],
                "findings": self._findings_for(set(ids))}

    def t_reason(self):
        ctx = self.ws.ctx
        if ctx is None:
            raise ValueError("no graph to reason over")
        from ..engine.checks.rsn import reasoning
        return reasoning(ctx).to_dict()

    def t_shacl_validate(self, which: str):
        ctx = self.ws.ctx
        if ctx is None:
            raise ValueError("no graph to validate")
        from ..engine import shacl
        shapes = ctx.shapes if which == "supplied" else ctx.house_rules
        if shapes is None:
            raise ValueError(f"no {which} shapes graph for this run")
        conforms, results = ctx.memo(f"shacl:{which}", lambda: shacl.validate(ctx.graph, shapes))
        return {"conforms": conforms, "results": [r.__dict__ for r in results[:MAX_ROWS]],
                "total": len(results)}

    def t_describe_entity(self, iri: str):
        g = self._graph()
        e = self._iri(iri)
        lit = lambda p: sorted({f"{o}" + (f"@{o.language}" if o.language else "")  # noqa: E731
                                for o in g.objects(e, p) if isinstance(o, Literal)})
        card: dict[str, Any] = {
            "iri": str(e), "label": V.label(g, e),
            "types": sorted(str(t) for t in g.objects(e, RDF.type)),
            "labels": lit(RDFS.label) + lit(V.SKOS.prefLabel),
            "definitions": lit(V.SKOS.definition) + lit(V.IAO_DEFINITION) + lit(RDFS.comment),
            "parents": sorted(str(o) for o in g.objects(e, RDFS.subClassOf) if isinstance(o, URIRef)),
            "children": sorted(str(s) for s in g.subjects(RDFS.subClassOf, e) if isinstance(s, URIRef)),
            "equivalent": sorted(str(o) for o in g.objects(e, OWL.equivalentClass) if isinstance(o, URIRef)),
            "disjoint_with": sorted({str(o) for o in g.objects(e, OWL.disjointWith)}
                                    | {str(s) for s in g.subjects(OWL.disjointWith, e)}),
            "restrictions": self._restrictions(e),
            "domain": sorted(str(o) for o in g.objects(e, RDFS.domain)),
            "range": sorted(str(o) for o in g.objects(e, RDFS.range)),
            "used_as_domain_of": sorted(str(s) for s in g.subjects(RDFS.domain, e)),
            "findings": self._findings_for(iri=str(e)),
        }
        return {k: v for k, v in card.items() if v not in ([], None)}

    def _restrictions(self, e) -> list[str]:
        g, out = self.ws.graph, []
        for sup in g.objects(e, RDFS.subClassOf):
            if isinstance(sup, URIRef):
                continue
            prop = g.value(sup, OWL.onProperty)
            for p in V.RESTRICTION_FILLERS:
                for o in g.objects(sup, p):
                    out.append(f"{V.local_name(prop) if prop else '?'} {V.local_name(p)} {V.local_name(o)}")
        return sorted(out)

    def t_hierarchy_neighbourhood(self, iri: str, up: int = 2, down: int = 1):
        g = self._graph()
        e = self._iri(iri)
        parents = lambda c: sorted((o for o in g.objects(c, RDFS.subClassOf) if isinstance(o, URIRef)), key=str)  # noqa: E731
        children = lambda c: sorted((s for s in g.subjects(RDFS.subClassOf, c) if isinstance(s, URIRef)), key=str)  # noqa: E731
        ancestors, level, frontier = [], 0, [e]
        while frontier and level < max(0, min(up, 6)):
            frontier = sorted({p for c in frontier for p in parents(c)}, key=str)
            ancestors.append([str(p) for p in frontier])
            level += 1
        siblings = sorted({str(s) for p in parents(e) for s in children(p) if s != e})
        descendants, frontier = [], [e]
        for _ in range(max(0, min(down, 4))):
            frontier = sorted({c for p in frontier for c in children(p)}, key=str)
            if not frontier:
                break
            descendants.append([str(c) for c in frontier])
        return {"iri": str(e), "label": V.label(g, e), "ancestors_by_level": ancestors,
                "siblings": siblings, "children_by_level": descendants,
                "disjoint_with": sorted({str(o) for o in g.objects(e, OWL.disjointWith)}
                                        | {str(s) for s in g.subjects(OWL.disjointWith, e)})}

    def t_search_entities(self, text: str):
        g = self._graph()
        needle = text.lower().strip()
        hits = []
        for t in sorted({s for s in g.subjects() if isinstance(s, URIRef)}, key=str):
            names = [V.local_name(t)] + [str(o) for p in V.LABEL_PROPERTIES for o in g.objects(t, p)]
            if any(needle in n.lower() for n in names):
                hits.append({"iri": str(t), "label": V.label(g, t)})
            if len(hits) >= 25:
                break
        return hits

    def _guard(self, query: str, kind: str) -> str:
        q = re.sub(r"#[^\n]*", "", query)
        if FORBIDDEN_SPARQL.search(q):
            raise ValueError("only read-only queries are allowed (no update, no SERVICE)")
        if not re.search(rf"\b{kind}\b", q, re.IGNORECASE):
            raise ValueError(f"expected a SPARQL {kind} query")
        return query

    def t_sparql_select(self, query: str):
        g = self._graph()
        q = self._guard(query, "SELECT")
        if not re.search(r"\bLIMIT\s+\d+", q, re.IGNORECASE):
            q = q.rstrip().rstrip(";") + f"\nLIMIT {MAX_ROWS}"
        res = g.query(q, initNs={"owl": OWL, "rdfs": RDFS, "rdf": RDF, "skos": V.SKOS,
                                 "xsd": V.XSD, "dcterms": V.DCTERMS})
        rows = [{str(k): (str(v) if v is not None else None) for k, v in r.asdict().items()}
                for r in list(res)[:MAX_ROWS]]
        return {"rows": rows, "truncated": len(rows) >= MAX_ROWS}

    def t_sparql_ask(self, query: str):
        g = self._graph()
        q = self._guard(query, "ASK")
        return {"answer": bool(g.query(q, initNs={"owl": OWL, "rdfs": RDFS, "rdf": RDF,
                                                   "skos": V.SKOS}).askAnswer)}

    def t_apply_policy(self, policy: str | None = None):
        if policy is None or policy == self.ws.policy.id:
            return {**self.ws.decision.to_dict(), "what_if": False}
        from ..engine.policy import load_policy
        pol = load_policy(policy)
        p = self.ws.profile
        _, d = apply_policy(self.ws.findings, p.spectrum_level if p else "controlled-vocabulary",
                            self.ws.declared_level, p.applies if p else [], pol)
        return {**d.to_dict(), "what_if": True,
                "note": "what-if only: checks the other policy disables or parametrises "
                        "differently were not re-run; the run's verdict is unchanged"}


def anthropic_tools(names: list[str] | None = None) -> list[dict]:
    """Tool definitions in Messages API shape, in a fixed order (prompt-cache friendly)."""
    names = names or [t["name"] for t in TOOL_SPECS]
    return [{"name": t["name"], "description": t["description"],
             "input_schema": t["input_schema"]} for t in TOOL_SPECS if t["name"] in names]


def as_langchain_tools(belt: ToolBelt) -> list:
    """The belt as LangChain ``StructuredTool``s (lazy import: LangChain is optional)."""
    from langchain_core.tools import StructuredTool
    tools = []
    for spec in TOOL_SPECS:
        name = spec["name"]
        tools.append(StructuredTool.from_function(
            func=lambda _n=name, **kw: belt.call_json(_n, kw), name=name,
            description=spec["description"], args_schema=spec["input_schema"]))
    return tools
