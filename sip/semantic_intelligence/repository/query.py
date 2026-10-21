"""Guarded, read-only SPARQL (FR-REPO-07): guard, dataset, row cap, deadline.

The guard runs before evaluation, in this order, and names the rule that failed:

1. query forms only (SELECT, ASK, CONSTRUCT, DESCRIBE); updates use ``sparql.update``;
2. no ``FROM`` / ``FROM NAMED``: the dataset comes only from graphs the PDP allowed;
3. no ``SERVICE``: no federated calls, so the server cannot be used to reach other hosts
   (rdflib would otherwise execute SERVICE over HTTP);
4. a row cap (results beyond it are cut and reported as truncated);
5. a deadline. rdflib cannot cancel a running query, but it is pure Python, so the
   deadline raises an asynchronous exception in the evaluating thread, which stops at
   the next bytecode boundary. No process, no copy of the dataset.
"""

from __future__ import annotations

import ctypes
import threading
import time
from dataclasses import dataclass

from rdflib import BNode, Dataset, Graph, Literal, URIRef
from rdflib.plugins.sparql.algebra import translateQuery
from rdflib.plugins.sparql.parser import parseQuery
from rdflib.plugins.sparql.parserutils import CompValue

FORMS = {"SelectQuery": "SELECT", "AskQuery": "ASK", "ConstructQuery": "CONSTRUCT",
         "DescribeQuery": "DESCRIBE"}
DEFAULT_LIMIT, MAX_LIMIT = 1000, 10000
DEFAULT_TIMEOUT_MS, MAX_TIMEOUT_MS = 10_000, 60_000


class QueryRejected(ValueError):
    """The guard refused the query; ``rule`` names the rule (1-3)."""

    def __init__(self, rule: str, message: str) -> None:
        super().__init__(f"{rule}: {message}")
        self.rule = rule


class QueryTimeout(Exception):
    """The query ran past its deadline and was stopped."""


@dataclass
class Guarded:
    form: str
    query: object          # rdflib Query (algebra), ready to evaluate


def _walk(node):
    if isinstance(node, CompValue):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, (list, tuple)):
        for v in node:
            yield from _walk(v)


def guard(text: str, init_ns: dict | None = None) -> Guarded:
    try:
        parsed = parseQuery(text)
    except Exception as e:  # noqa: BLE001 — pyparsing raises several types
        msg = str(e).split("\n")[0]
        if any(k in text.upper() for k in ("INSERT", "DELETE", "LOAD", "CLEAR", "DROP",
                                           "CREATE", "COPY", "MOVE", "ADD ")):
            raise QueryRejected("G1", "only queries are allowed here; updates use "
                                      "sparql.update") from None
        raise QueryRejected("G0", f"not a valid SPARQL query: {msg}") from None
    body = parsed[1]
    if body.name not in FORMS:
        raise QueryRejected("G1", f"{body.name} is not a query form")
    if body.get("datasetClause"):
        raise QueryRejected("G2", "FROM / FROM NAMED are not allowed; choose graphs with "
                                  "the dataset selector")
    q = translateQuery(parsed, initNs=init_ns or {})
    if any(n.name == "ServiceGraphPattern" for n in _walk(q.algebra)):
        raise QueryRejected("G3", "SERVICE (federated query) is not allowed")
    return Guarded(FORMS[body.name], q)


def clamp(limit: int | None, timeout_ms: int | None) -> tuple[int, int]:
    lim = DEFAULT_LIMIT if limit is None else int(limit)
    tmo = DEFAULT_TIMEOUT_MS if timeout_ms is None else int(timeout_ms)
    if lim < 1 or tmo < 1:
        raise ValueError("limit and timeout_ms must be positive")
    return min(lim, MAX_LIMIT), min(tmo, MAX_TIMEOUT_MS)


def build_dataset(graphs: dict[str, Graph], namespaces: dict[str, str]) -> Dataset:
    """A dataset whose default graph is the union of ``graphs`` and in which each graph is
    also available by name for ``GRAPH`` patterns."""
    ds = Dataset(default_union=True)
    for name, g in graphs.items():
        target = ds.graph(URIRef(name))
        for t in g:
            target.add(t)
    for p, ns in namespaces.items():
        ds.bind(p, ns, override=True, replace=True)
    return ds


def run_with_deadline(fn, seconds: float):
    """Run ``fn`` in the current thread; raise :class:`QueryTimeout` after ``seconds``."""
    tid = threading.get_ident()
    lock = threading.Lock()
    state = {"done": False, "fired": False}

    def fire():
        with lock:
            if state["done"]:
                return
            state["fired"] = True
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(tid),
                                                       ctypes.py_object(QueryTimeout))

    timer = threading.Timer(seconds, fire)
    timer.daemon = True
    timer.start()
    try:
        try:
            return fn()
        finally:
            with lock:
                state["done"] = True
            timer.cancel()
            if state["fired"]:  # clear an exception that may still be pending
                ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(tid), None)
    except QueryTimeout:
        raise QueryTimeout(f"query stopped after {seconds:g} s") from None


def _term(t) -> dict | None:
    if t is None:
        return None
    if isinstance(t, URIRef):
        return {"type": "uri", "value": str(t)}
    if isinstance(t, BNode):
        return {"type": "bnode", "value": str(t)}
    d = {"type": "literal", "value": str(t)}
    if isinstance(t, Literal):
        if t.language:
            d["lang"] = t.language
        elif t.datatype:
            d["datatype"] = str(t.datatype)
    return d


def evaluate(ds: Dataset, g: Guarded, limit: int, timeout_ms: int) -> dict:
    """Evaluate under the cap and the deadline; SPARQL-JSON-like terms."""
    t0 = time.perf_counter()

    def go():
        res = ds.query(g.query)
        if g.form == "ASK":
            return {"boolean": bool(res.askAnswer)}
        if g.form in ("CONSTRUCT", "DESCRIBE"):
            triples = []
            for i, (s, p, o) in enumerate(res.graph):
                if i == limit:
                    return {"triples": triples, "truncated": True}
                triples.append([_term(s), _term(p), _term(o)])
            return {"triples": triples, "truncated": False}
        cols = [str(v) for v in res.vars or []]
        rows = []
        for i, row in enumerate(res):
            if i == limit:
                return {"columns": cols, "rows": rows, "truncated": True}
            rows.append({c: _term(row[c]) for c in cols if row[c] is not None})
        return {"columns": cols, "rows": rows, "truncated": False}

    out = run_with_deadline(go, timeout_ms / 1000)
    out.setdefault("truncated", False)
    out["form"] = g.form
    out["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return out


def flat(result: dict) -> list[dict]:
    """The pre-repository ``sparql.query`` shape: plain strings."""
    if result["form"] == "ASK":
        return [{"ask": result["boolean"]}]
    if result["form"] in ("CONSTRUCT", "DESCRIBE"):
        return [{"s": s["value"], "p": p["value"], "o": o["value"]}
                for s, p, o in result["triples"]]
    return [{c: r[c]["value"] for c in result["columns"] if c in r} for r in result["rows"]]
