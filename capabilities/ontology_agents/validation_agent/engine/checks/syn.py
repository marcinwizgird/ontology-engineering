"""SYN: can the document be read, and are its terms and literals lexically valid?"""

from __future__ import annotations

import re

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF

from .. import vocab as V
from ..registry import CheckContext, detector, finding

ILLEGAL_IRI_CHARS = re.compile(r'[\s<>"{}|\\^`]')
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")


@detector("SYN-01")
def document_does_not_parse(ctx: CheckContext):
    load = ctx.load
    if load is None or load.error is None:
        return []
    where = f" (line {load.error_line})" if load.error_line else ""
    return [finding("SYN-01", load.source, f"The document does not parse as {load.format}{where}.",
                    evidence={"parser_error": load.error, "line": load.error_line},
                    fix_hint="Fix the syntax at the reported position; every other check is "
                             "skipped until the document parses.")]


@detector("SYN-02")
def invalid_iri(ctx: CheckContext):
    out = []
    terms = {t for triple in ctx.graph for t in triple if isinstance(t, URIRef)}
    for t in sorted(terms, key=str):
        s = str(t)
        if s.startswith(V.NO_BASE):
            out.append(finding("SYN-02", t, f"Relative IRI <{s[len(V.NO_BASE):]}> in a document "
                               "without a base IRI.",
                               evidence={"iri": s[len(V.NO_BASE):], "problem": "relative"},
                               fix_hint="Declare @base / xml:base, or write the IRI in full."))
        elif ILLEGAL_IRI_CHARS.search(s):
            bad = sorted({repr(c) for c in ILLEGAL_IRI_CHARS.findall(s)})
            out.append(finding("SYN-02", t, f"IRI <{s}> contains illegal characters {', '.join(bad)}.",
                               evidence={"iri": s, "problem": "illegal-characters", "chars": bad},
                               fix_hint="Percent-encode or remove the characters (e.g. use "
                                        "CamelCase instead of spaces)."))
        elif not SCHEME.match(s):
            out.append(finding("SYN-02", t, f"IRI <{s}> has no scheme.",
                               evidence={"iri": s, "problem": "no-scheme"},
                               fix_hint="Use an absolute IRI with a scheme such as https:."))
    return out


@detector("SYN-03")
def ill_typed_literal(ctx: CheckContext):
    out = []
    for s, p, o in sorted(ctx.graph, key=lambda t: (str(t[0]), str(t[1]), str(t[2]))):
        if isinstance(o, Literal) and getattr(o, "ill_typed", False):
            out.append(finding(
                "SYN-03", s, f'Literal "{o}" is not in the lexical space of '
                f"{V.local_name(o.datatype)} (on {V.local_name(p)}).",
                related=[p], evidence={"triples": [f"<{s}> <{p}> \"{o}\"^^<{o.datatype}>"],
                                       "datatype": str(o.datatype)},
                fix_hint="Correct the lexical form, or change the datatype to the one the "
                         "value actually has. In OWL 2 DL this makes the ontology inconsistent."))
    return out


@detector("SYN-06")
def malformed_restriction(ctx: CheckContext):
    g, out = ctx.graph, []
    nodes = set(g.subjects(RDF.type, OWL.Restriction)) | set(g.subjects(OWL.onProperty, None))
    for r in sorted(nodes, key=str):
        problems = []
        on_props = list(g.objects(r, OWL.onProperty))
        if not on_props and (r, OWL.onProperties, None) not in g:
            problems.append("no owl:onProperty")
        elif len(on_props) > 1:
            problems.append(f"{len(on_props)} owl:onProperty values")
        fillers = sorted(V.local_name(p) for p in V.RESTRICTION_FILLERS for _ in g.objects(r, p))
        if not fillers:
            problems.append("no filler or cardinality")
        elif len(fillers) > 1:
            problems.append("several fillers/cardinalities: " + ", ".join(fillers))
        if any((r, q, None) in g for q in V.QUALIFIED) and \
                (r, OWL.onClass, None) not in g and (r, OWL.onDataRange, None) not in g:
            problems.append("qualified cardinality without owl:onClass/owl:onDataRange")
        if problems:
            owners = [str(o) for o in V.named_owners(g, r)]
            focus = owners[0] if owners else str(r)
            out.append(finding(
                "SYN-06", focus, "Malformed restriction" +
                (f" on {V.local_name(owners[0])}" if owners else "") + ": " + "; ".join(problems) + ".",
                related=[str(p) for p in on_props],
                evidence={"problems": problems,
                          "triples": [f"_:r <{p}> {o.n3()}" for p, o in sorted(g.predicate_objects(r))]},
                fix_hint="A restriction needs exactly one owl:onProperty and exactly one filler "
                         "or cardinality; reasoners ignore anything else."))
    return out
