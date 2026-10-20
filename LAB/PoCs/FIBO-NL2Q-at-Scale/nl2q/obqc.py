"""Ontology-based query checks (OBQC), extended to restriction-derived allowed edges.

Two entry points:

* :func:`check_plan` — for the IR: every class/property exists in the mapped ontology,
  every link and attribute is allowed for its subject class (inheritance-aware, from the
  query graph), ids resolve, aggregation targets are numeric where required, values parse
  for their datatype, grouping is complete.
* :func:`check_sparql` — for free SPARQL (arms A/B): the rules of Allemang & Sequeda
  (2024) — unknown property, domain, range, double-domain, double-range, domain-range —
  evaluated against the *allowed edges* instead of rdfs:domain/range only.

Each finding is a short message written for the repair prompt and for GEPA's reflection.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime

from . import ir
from .querygraph import load as load_graph

NUMERIC = {"integer", "double", "decimal"}


def prop_range(prop: str) -> str | None:
    g = load_graph()
    for d, p, r in g.pack.edges:
        if p == prop:
            return r
    return None


def _value_ok(xsd: str | None, v: str | None) -> bool:
    if v is None or xsd is None:
        return True
    try:
        if xsd in NUMERIC:
            float(v)
        elif xsd == "date":
            date.fromisoformat(v[:10])
        elif xsd == "dateTime":
            datetime.fromisoformat(v.replace("Z", "")[:19] if "T" in v else v[:10])
    except ValueError:
        return False
    return True


def _check_pattern(p: ir.Pattern, where: str, outer_ids: dict[str, str] | None = None) -> tuple[list[str], dict[str, str], dict[str, str]]:
    g = load_graph()
    problems: list[str] = []
    nodes: dict[str, str] = {}
    attrs: dict[str, str] = {}
    for n in p.nodes:
        if n.cls not in g.classes:
            problems.append(f"{where}: unknown class {n.cls!r} (node {n.id})")
        nodes[n.id] = n.cls
    allnodes = {**(outer_ids or {}), **nodes}
    for l in p.links:
        s, o = allnodes.get(l.subj), allnodes.get(l.obj)
        if s is None or o is None:
            problems.append(f"{where}: link {l.subj} {l.prop} {l.obj} uses an unknown node id")
            continue
        if g.prop_kind.get(l.prop) != "object":
            problems.append(f"{where}: {l.prop!r} is not an object property")
            continue
        if not g.allowed(s, l.prop, o):
            rev = g.allowed(o, l.prop, s)
            hint = f" (the reverse direction {o} {l.prop} {s} is allowed)" if rev else ""
            doms = sorted(g.domains_of(l.prop))[:5]
            problems.append(f"{where}: {s} {l.prop} {o} is not allowed by the ontology{hint}; "
                            f"{l.prop} applies to {doms}")
    for a in p.attrs:
        cls = allnodes.get(a.node)
        if cls is None:
            problems.append(f"{where}: attribute {a.id} on unknown node {a.node}")
            continue
        if g.prop_kind.get(a.prop) != "datatype":
            problems.append(f"{where}: {a.prop!r} is not a datatype property")
            continue
        if a.prop not in g.attributes(cls):
            opts = sorted(g.domains_of(a.prop))[:5]
            problems.append(f"{where}: class {cls} has no {a.prop}; {a.prop} is on {opts}")
        attrs[a.id] = a.prop
    for f in p.filters:
        if f.target not in attrs and f.target not in allnodes and f.target not in (outer_ids or {}):
            problems.append(f"{where}: filter on unknown id {f.target}")
            continue
        xsd = prop_range(attrs[f.target]) if f.target in attrs else None
        for v in [f.value, f.value2, *f.values]:
            if not _value_ok(xsd, v):
                problems.append(f"{where}: value {v!r} is not a valid {xsd} for {attrs.get(f.target)}")
        if f.op == "between" and f.value2 is None:
            problems.append(f"{where}: between needs value2")
        if f.op in ("contains", "starts_with") and xsd and xsd != "string":
            problems.append(f"{where}: {f.op} applies to text, {attrs.get(f.target)} is {xsd}")
    return problems, nodes, attrs


def check_plan(plan: ir.Plan) -> list[str]:
    if not plan.answerable:
        return []
    probs, nodes, attrs = _check_pattern(ir.Pattern(nodes=plan.nodes, links=plan.links,
                                                    attrs=plan.attrs, filters=plan.filters), "main")
    if not plan.nodes:
        probs.append("main: the plan has no nodes")
    # every node must be linked to the others: an unlinked node is a cross product
    if len(plan.nodes) > 1:
        import networkx as nx
        h = nx.Graph()
        h.add_nodes_from(n.id for n in plan.nodes)
        h.add_edges_from((l.subj, l.obj) for l in plan.links if l.subj in h and l.obj in h)
        comps = list(nx.connected_components(h))
        if len(comps) > 1:
            names = [sorted(nodes.get(i, i) for i in c) for c in comps]
            probs.append(f"main: the nodes are not all linked (separate groups {names}); "
                         "link them with object properties or drop the extra node")
    if not plan.projections:
        probs.append("main: the plan projects nothing")
    ids = set(nodes) | set(attrs)
    for i, pr in enumerate(plan.projections):
        if pr.target == "*" and pr.agg == "COUNT":
            continue
        if pr.target not in ids:
            probs.append(f"projection {i}: unknown id {pr.target}")
        elif pr.agg in ("SUM", "AVG") and (pr.target not in attrs or prop_range(attrs[pr.target]) not in NUMERIC):
            probs.append(f"projection {i}: {pr.agg} needs a numeric attribute, got {pr.target}")
    for gb in plan.group_by:
        if gb not in ids:
            probs.append(f"group_by: unknown id {gb}")
    for h in plan.having:
        if h.target not in ids and h.target != "*":
            probs.append(f"having: unknown id {h.target}")
    for o in plan.order_by:
        if not 0 <= o.projection < len(plan.projections):
            probs.append(f"order_by: projection index {o.projection} out of range")
    outer = {**nodes, **{k: v for k, v in attrs.items()}}
    for j, neg in enumerate(plan.negations):
        p2, n2, a2 = _check_pattern(neg.pattern, f"negation {j}", outer_ids=nodes)
        probs += p2
        for jn in neg.joins:
            if jn.outer not in outer or (jn.inner not in n2 and jn.inner not in a2):
                probs.append(f"negation {j}: join {jn.outer}={jn.inner} uses unknown ids")
    for j, c in enumerate(plan.comparisons):
        p2, n2, a2 = _check_pattern(c.sub_pattern, f"comparison {j}")
        probs += p2
        if c.left_target not in ids:
            probs.append(f"comparison {j}: unknown left id {c.left_target}")
        if c.sub_target not in n2 and c.sub_target not in a2:
            probs.append(f"comparison {j}: unknown sub id {c.sub_target}")
        for jn in c.correlate:
            if jn.outer not in outer or (jn.inner not in n2 and jn.inner not in a2):
                probs.append(f"comparison {j}: correlation {jn.outer}={jn.inner} uses unknown ids")
    return probs


# ----------------------------------------------------------------------------- #
FIBEN_NS = "https://example.org/fiben/voc#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


def _bgp_triples(sparql: str):
    """All triple patterns of the query (including inside OPTIONAL/EXISTS/sub-selects),
    with variables as ``?name`` and FIBEN terms as ``fiben:local``."""
    from rdflib.plugins.sparql import prepareQuery
    from rdflib.term import URIRef, Variable

    def fmt(t) -> str:
        if isinstance(t, Variable):
            return "?" + str(t)
        if isinstance(t, URIRef):
            s = str(t)
            if s == RDF_TYPE:
                return "a"
            return "fiben:" + s[len(FIBEN_NS):] if s.startswith(FIBEN_NS) else s
        return str(t)

    out = []

    def walk(node):
        if hasattr(node, "name") and node.name == "BGP":
            out.extend((fmt(s), fmt(p), fmt(o)) for s, p, o in node.triples)
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)
    walk(prepareQuery(sparql).algebra)
    return out


def check_sparql(sparql: str) -> list[str]:
    """Allemang & Sequeda's OBQC rules over the allowed-edge view, for free SPARQL."""
    g = load_graph()
    types: dict[str, set[str]] = defaultdict(set)
    triples = []
    probs: list[str] = []
    try:
        for s, p, o in _bgp_triples(sparql):
            if p == "a":
                types[s].add(o.removeprefix("fiben:"))
            else:
                triples.append((s, p.removeprefix("fiben:"), o))
    except Exception as exc:  # noqa: BLE001
        return [f"SPARQL does not parse: {str(exc)[:200]}"]
    for v, cs in types.items():
        for c in cs:
            if c not in g.classes:
                probs.append(f"unknown class fiben:{c}")
    subj_props: dict[str, list[str]] = defaultdict(list)
    for s, p, o in triples:
        kind = g.prop_kind.get(p)
        if kind is None:
            probs.append(f"unknown property fiben:{p} (incorrect property)")
            continue
        subj_props[s].append(p)
        st = [c for c in types.get(s, ()) if c in g.classes]
        # an individual belongs to all its types: the property must fit *some* type
        if st and not any(g.allowed(c, p, None) for c in st):        # domain rule
            probs.append(f"domain: {s} is a {'/'.join(sorted(st))}, which has no {p}")
        if kind == "object" and o.startswith("?") and st:
            ot = [c for c in types.get(o, ()) if c in g.classes]     # range rule
            if ot and not any(g.allowed(a, p, b) for a in st for b in ot):
                probs.append(f"range: {'/'.join(sorted(st))} {p} {'/'.join(sorted(ot))} is not allowed")
    # connectivity of the main pattern's variables (a cross product is almost never meant)
    import networkx as nx
    h = nx.Graph()
    for s in types:
        h.add_node(s)
    for s, p, o in triples:
        h.add_node(s)
        if o.startswith("?"):
            h.add_edge(s, o)
    ent = [v for v in h.nodes if v in types]
    up = sparql.upper()
    flat = up.count("SELECT") == 1 and "UNION" not in up and "EXISTS" not in up and "MINUS" not in up
    if flat and len(ent) > 1 and not nx.is_connected(h.subgraph(nx.node_connected_component(h, ent[0]) | set(ent))):
        comps = [c for c in nx.connected_components(h) if c & set(ent)]
        if len(comps) > 1:
            probs.append(f"cross product: typed variables in unlinked groups {[sorted(c & set(ent)) for c in comps]}")
    for s, props in subj_props.items():                               # double domain
        if types.get(s):
            continue
        doms = [g.domains_of(p) for p in props]
        if doms and not set.intersection(*doms):
            probs.append(f"double domain: no class has all of {sorted(set(props))} for {s}")
    return sorted(set(probs))
