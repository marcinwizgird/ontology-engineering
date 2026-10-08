"""Knowledge-graph construction: tabular lifting, entity resolution, LPG projection.

**Tabular lifting** takes the role of Semantic Turkey's Sheet2RDF/CODA: a
:class:`TableMapping` says which ontology class a row instantiates, how its IRI is
built (a ``{column}`` template — the CODA ``randIdGen``/template idea without
PEARL), and which column feeds which property (data or object, with optional
datatype, language or a lookup of the target by label). The output is a list of
triples for the project's **kg** graph; the caller commits it as one change set,
so a lift is one reviewable, undoable commit.

**Entity resolution** proposes ``owl:sameAs`` between individuals of the same
class whose normalised labels and key properties agree (blocking by class and
first token, then a similarity score) — proposals only; an agent stages them.

**LPG projection** maps the instance graph to nodes/edges for FalkorDB (the
platform's derived store): typed individuals become labelled nodes, object
property assertions edges, data property values node properties. The full
production projector already exists in ``capabilities/ontology_converter`` and
``ontology_modeler.lpg``; this is the minimal, dependency-free contract.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD


@dataclass
class ColumnMap:
    column: str
    property: str
    kind: str = "data"                 # data | object | label
    datatype: str | None = None
    lang: str | None = None
    target_class: str | None = None    # object: resolve target by label within this class
    target_template: str | None = None # object: or build the target IRI


@dataclass
class TableMapping:
    cls: str
    iri_template: str                  # e.g. "https://ex.org/kg/customer/{id}"
    columns: list[ColumnMap] = field(default_factory=list)
    label_column: str | None = None

    def validate(self, header: Iterable[str], ontology: Graph) -> list[str]:
        """Static checks before anything is lifted (the KG builder agent's critic)."""
        problems = []
        cols = set(header)
        for ph in re.findall(r"\{([^}]+)\}", self.iri_template):
            if ph not in cols:
                problems.append(f"IRI template uses unknown column {ph!r}")
        if (URIRef(self.cls), RDF.type, OWL.Class) not in ontology:
            problems.append(f"class {self.cls} is not declared in the ontology")
        for c in self.columns:
            if c.column not in cols:
                problems.append(f"unknown column {c.column!r}")
            p = URIRef(c.property)
            want = {"data": OWL.DatatypeProperty, "object": OWL.ObjectProperty,
                    "label": None}[c.kind]
            if want is not None and (p, RDF.type, want) not in ontology:
                problems.append(f"{c.property} is not declared as {want.split('#')[-1]}")
        return problems


_LEXICAL = {XSD.integer: re.compile(r"[+-]?\d+"),
            XSD.decimal: re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)"),
            XSD.double: re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?|INF|-INF|NaN"),
            XSD.date: re.compile(r"-?\d{4,}-\d{2}-\d{2}(Z|[+-]\d{2}:\d{2})?"),
            XSD.boolean: re.compile(r"true|false|0|1")}


def _slug(v: str) -> str:
    v = unicodedata.normalize("NFKD", v).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", v.strip()).strip("_")


def lift_table(csv_text: str, mapping: TableMapping, ontology: Graph,
               existing: Graph | None = None) -> tuple[list[tuple], list[str]]:
    """Rows → triples. Returns ``(triples, warnings)``. Raises on mapping errors."""
    reader = csv.DictReader(io.StringIO(csv_text))
    problems = mapping.validate(reader.fieldnames or [], ontology)
    if problems:
        raise ValueError("; ".join(problems))
    existing = existing or Graph()
    by_label: dict[tuple[str, str], URIRef] = {}
    for g in (existing,):
        for s, o in g.subject_objects(RDFS.label):
            for t in g.objects(s, RDF.type):
                by_label[(str(t), str(o).casefold())] = s
    triples, warnings = [], []
    rows = list(reader)
    # first pass: subjects (so object columns can refer to rows of the same table)
    subjects = []
    for row in rows:
        iri = URIRef(mapping.iri_template.format(**{k: _slug(v or "") for k, v in row.items()}))
        subjects.append(iri)
        if mapping.label_column and row.get(mapping.label_column):
            by_label[(mapping.cls, row[mapping.label_column].casefold())] = iri
    for n, (row, s) in enumerate(zip(rows, subjects), start=2):
        triples.append((s, RDF.type, URIRef(mapping.cls)))
        triples.append((s, RDF.type, OWL.NamedIndividual))
        if mapping.label_column and row.get(mapping.label_column):
            triples.append((s, RDFS.label, Literal(row[mapping.label_column].strip(), lang="en")))
        for c in mapping.columns:
            raw = (row.get(c.column) or "").strip()
            if not raw:
                continue
            p = URIRef(c.property)
            if c.kind == "label":
                triples.append((s, p, Literal(raw, lang=c.lang)))
            elif c.kind == "data":
                dt = URIRef(c.datatype) if c.datatype else None
                rx = _LEXICAL.get(dt)
                if rx is not None and not rx.fullmatch(raw):
                    warnings.append(f"row {n}: {c.column}={raw!r} is not a valid "
                                    f"{dt.split('#')[-1]}; skipped")
                    continue
                lit = Literal(raw, datatype=dt) if dt else Literal(raw, lang=c.lang)
                triples.append((s, p, lit))
            else:
                if c.target_template:
                    o = URIRef(c.target_template.format(value=_slug(raw)))
                else:
                    o = by_label.get((c.target_class or "", raw.casefold()))
                    if o is None:
                        warnings.append(f"row {n}: no {c.target_class} labelled {raw!r}; "
                                        f"{c.column} skipped")
                        continue
                triples.append((s, p, o))
    return triples, warnings


# ----------------------------- entity resolution ---------------------------- #

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(inc|ltd|llc|plc|gmbh|sa|ag|co|corp|corporation|company)\b\.?", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    # light stemming so that "Volvo Cars" ~ "Volvo Car (Corporation)"
    return " ".join(t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith("ss") else t
                    for t in s.split())


def _sim(a: str, b: str) -> float:
    if a == b:
        return 1.0
    ta, tb = set(a.split()), set(b.split())
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


@dataclass
class Duplicate:
    a: URIRef
    b: URIRef
    score: float
    evidence: list[str]


def resolve_entities(g: Graph, threshold: float = 0.85,
                     key_properties: Iterable[URIRef] = ()) -> list[Duplicate]:
    keys = list(key_properties)
    blocks: dict[tuple, list[URIRef]] = {}
    labels: dict[URIRef, str] = {}
    for s, o in g.subject_objects(RDFS.label):
        if isinstance(s, URIRef):
            n = _norm(str(o))
            if not n:
                continue
            labels[s] = n
            for t in g.objects(s, RDF.type):
                if t != OWL.NamedIndividual:
                    blocks.setdefault((t, n.split()[0]), []).append(s)
    out: dict[tuple, Duplicate] = {}
    for (_, _), members in blocks.items():
        ms = sorted(set(members))
        for i, a in enumerate(ms):
            for b in ms[i + 1:]:
                if (a, OWL.sameAs, b) in g or (b, OWL.sameAs, a) in g:
                    continue
                score = _sim(labels[a], labels[b])
                ev = [f"labels {labels[a]!r} ~ {labels[b]!r} ({score:.2f})"]
                for k in keys:
                    va, vb = set(g.objects(a, k)), set(g.objects(b, k))
                    if va and vb:
                        if va & vb:
                            score = min(1.0, score + 0.15)
                            ev.append(f"shared {k.split('#')[-1].split('/')[-1]}")
                        else:
                            score -= 0.3
                            ev.append(f"conflicting {k.split('#')[-1].split('/')[-1]}")
                if score >= threshold:
                    out[(a, b)] = Duplicate(a, b, round(score, 3), ev)
    return sorted(out.values(), key=lambda d: -d.score)


# ------------------------------- LPG projection ----------------------------- #

def project_lpg(kg: Graph, ontology: Graph) -> dict[str, list[dict]]:
    """Instance graph → ``{"nodes": [...], "edges": [...]}`` for a property graph."""
    obj = set(ontology.subjects(RDF.type, OWL.ObjectProperty))
    data = set(ontology.subjects(RDF.type, OWL.DatatypeProperty))
    nodes: dict[URIRef, dict] = {}

    def local(i):
        return re.split(r"[#/]", str(i))[-1]
    for s, t in kg.subject_objects(RDF.type):
        if isinstance(s, URIRef) and t != OWL.NamedIndividual and isinstance(t, URIRef):
            n = nodes.setdefault(s, {"id": str(s), "labels": [], "properties": {}})
            n["labels"].append(local(t))
    edges = []
    for s, p, o in kg:
        if s not in nodes:
            continue
        if p in obj and isinstance(o, URIRef):
            edges.append({"source": str(s), "type": local(p), "target": str(o)})
        elif p in data or p == RDFS.label:
            nodes[s]["properties"].setdefault(local(p), []).append(o.toPython()
                                                                    if isinstance(o, Literal)
                                                                    else str(o))
    for n in nodes.values():
        n["labels"].sort()
        n["properties"] = {k: v[0] if len(v) == 1 else v for k, v in n["properties"].items()}
    return {"nodes": sorted(nodes.values(), key=lambda n: n["id"]),
            "edges": sorted(edges, key=lambda e: (e["source"], e["type"], e["target"]))}
