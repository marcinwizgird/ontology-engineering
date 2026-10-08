"""Alignment — Semantic Turkey's ``Alignment`` service (23 ops) over the Alignment
API format, plus a lexical matcher for candidate generation.

Data model (``AlignmentModel``/``Cell``): an alignment between ``onto1`` and
``onto2``; cells ``(entity1, entity2, measure, relation, mappingProperty?,
status ∈ {accepted, rejected, error}, comment?)``. Relations ``=``, ``<``, ``>``,
``%`` (disjoint), ``HasInstance``, ``InstanceOf``.

The relation → property table is ``AlignmentUtils.suggestPropertiesForRelation``
verbatim, keyed by the *role* of ``entity1``; the cells marked "error" would
require asserting a triple with the target as subject and are rejected with the
same message.

``apply_validation`` writes accepted cells into the project's **mappings** graph
(not into the ontology), and with ``delete_rejected`` removes rejected mapping
triples that already exist. Loading reverses an alignment whose ``onto2`` is the
current project (swap entities, ``<``↔``>``, ``HasInstance``↔``InstanceOf``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

from ..core.changes import ChangeSet
from ..core.namespaces import ALIGN

ERROR = "error"
SUGGESTIONS: dict[str, dict[str, tuple]] = {
    "property": {"=": (OWL.equivalentProperty, OWL.sameAs), "<": (RDFS.subPropertyOf,),
                 ">": ERROR, "%": (OWL.propertyDisjointWith,), "InstanceOf": (RDF.type,),
                 "HasInstance": ERROR},
    "concept": {"=": (SKOS.exactMatch, SKOS.closeMatch), "<": (SKOS.broadMatch,),
                ">": (SKOS.narrowMatch,), "%": (), "InstanceOf": (SKOS.broadMatch, RDF.type),
                "HasInstance": (SKOS.narrowMatch,)},
    "cls": {"=": (OWL.equivalentClass, OWL.sameAs), "<": (RDFS.subClassOf,), ">": ERROR,
            "%": (OWL.disjointWith,), "InstanceOf": (RDF.type,), "HasInstance": ERROR},
    "individual": {"=": (OWL.sameAs,), "<": ERROR, ">": ERROR, "%": (OWL.differentFrom,),
                   "InstanceOf": (RDF.type,), "HasInstance": ERROR},
}
REVERSE = {"<": ">", ">": "<", "HasInstance": "InstanceOf", "InstanceOf": "HasInstance",
           "=": "=", "%": "%"}


class InvalidAlignmentRelation(ValueError):
    pass


def suggest_properties(role: str, relation: str) -> tuple[URIRef, ...]:
    key = "property" if role.endswith("roperty") or role == "property" else role
    table = SUGGESTIONS.get(key)
    if table is None:
        table = SUGGESTIONS["individual"]
    s = table.get(relation, ())
    if s == ERROR:
        raise InvalidAlignmentRelation(
            f"relation {relation!r} on a {role} would require asserting a triple with the "
            "target as subject")
    return s


@dataclass
class Cell:
    entity1: URIRef
    entity2: URIRef
    measure: float
    relation: str = "="
    mapping_property: URIRef | None = None
    status: str | None = None
    comment: str | None = None
    creator: str | None = None


@dataclass
class Alignment:
    onto1: str
    onto2: str
    cells: list[Cell] = field(default_factory=list)
    level: str = "0"
    type: str = "**"

    # -- Alignment API RDF ------------------------------------------------- #
    @classmethod
    def parse(cls, data: str, fmt: str = "xml") -> "Alignment":
        g = Graph().parse(data=data, format=fmt)
        a = next(g.subjects(RDF.type, ALIGN.Alignment), None)
        if a is None:
            raise ValueError("no align:Alignment in document")

        def onto(p):
            o = g.value(a, p)
            if o is None:
                return ""
            loc = g.value(o, ALIGN.location) if isinstance(o, BNode) else None
            return str(loc or o)
        al = cls(onto(ALIGN.onto1), onto(ALIGN.onto2),
                 level=str(g.value(a, ALIGN.level) or "0"), type=str(g.value(a, ALIGN.type) or "**"))
        for m in g.objects(a, ALIGN.map):
            for c in ([m] if (m, ALIGN.entity1, None) in g else g.objects(m, None)):
                e1, e2 = g.value(c, ALIGN.entity1), g.value(c, ALIGN.entity2)
                if e1 is None or e2 is None:
                    continue
                meas = g.value(c, ALIGN.measure)
                al.cells.append(Cell(URIRef(e1), URIRef(e2), float(meas) if meas is not None
                                     else 1.0, str(g.value(c, ALIGN.relation) or "=")))
        return al

    def to_graph(self) -> Graph:
        g = Graph()
        g.bind("align", ALIGN)
        a = BNode()
        g.add((a, RDF.type, ALIGN.Alignment))
        g.add((a, ALIGN.xml, Literal("yes")))
        g.add((a, ALIGN.level, Literal(self.level)))
        g.add((a, ALIGN.type, Literal(self.type)))
        g.add((a, ALIGN.onto1, URIRef(self.onto1)))
        g.add((a, ALIGN.onto2, URIRef(self.onto2)))
        for c in self.cells:
            n = BNode()
            g.add((a, ALIGN.map, n))
            g.add((n, RDF.type, ALIGN.Cell))
            g.add((n, ALIGN.entity1, c.entity1))
            g.add((n, ALIGN.entity2, c.entity2))
            g.add((n, ALIGN.measure, Literal(c.measure, datatype=XSD.float)))
            g.add((n, ALIGN.relation, Literal(c.relation)))
        return g

    def reverse(self) -> "Alignment":
        if any(c.relation not in REVERSE for c in self.cells):
            raise ValueError("cannot reverse an alignment with custom relations")
        return Alignment(self.onto2, self.onto1, [
            Cell(c.entity2, c.entity1, c.measure, REVERSE[c.relation]) for c in self.cells],
            self.level, self.type)

    # -- validation -------------------------------------------------------- #
    def accept(self, cell: Cell, role_of, forced: URIRef | None = None) -> Cell:
        try:
            prop = forced or suggest_properties(role_of(cell.entity1), cell.relation)[0]
        except (InvalidAlignmentRelation, IndexError) as exc:
            cell.status, cell.comment = "error", str(exc) or "no property for relation"
            return cell
        cell.mapping_property, cell.status = prop, "accepted"
        return cell

    def accept_all_above(self, threshold: float, role_of) -> int:
        n = 0
        for c in self.cells:
            if c.measure >= threshold:
                self.accept(c, role_of)
                n += c.status == "accepted"
        return n

    def reject_all_under(self, threshold: float) -> int:
        n = 0
        for c in self.cells:
            if c.measure < threshold:
                c.status = "rejected"
                n += 1
        return n

    def apply_validation(self, mappings_graph: URIRef, existing: Graph, role_of,
                         delete_rejected: bool = False) -> tuple[ChangeSet, list[dict]]:
        cs = ChangeSet("alignment.applyValidation", {"onto1": self.onto1, "onto2": self.onto2},
                       mappings_graph)
        report = []
        for c in self.cells:
            if c.status == "accepted" and c.mapping_property is not None:
                cs.add(c.entity1, c.mapping_property, c.entity2)
                report.append({"entity1": str(c.entity1), "entity2": str(c.entity2),
                               "property": str(c.mapping_property), "action": "Added"})
            elif c.status == "rejected" and delete_rejected:
                try:
                    props = suggest_properties(role_of(c.entity1), c.relation)
                except InvalidAlignmentRelation:
                    props = ()
                for p in props:
                    if (c.entity1, p, c.entity2) in existing:
                        cs.remove(c.entity1, p, c.entity2)
                        report.append({"entity1": str(c.entity1), "entity2": str(c.entity2),
                                       "property": str(p), "action": "Deleted"})
        return cs, report


# --------------------------------------------------------------------------- #
# Candidate generation — a lexical matcher (MAPLE-style lexicalization pairing)
# --------------------------------------------------------------------------- #

_TOKEN = re.compile(r"[A-Za-z][a-z]+|[A-Z]+(?![a-z])|\d+")


def _norm(s: str) -> str:
    return " ".join(t.lower() for t in _TOKEN.findall(s))


def lexicalizations(g: Graph, r: URIRef) -> set[str]:
    out = {_norm(str(o)) for p in (RDFS.label, SKOS.prefLabel, SKOS.altLabel)
           for o in g.objects(r, p) if isinstance(o, Literal)}
    frag = re.split(r"[#/]", str(r))[-1]
    if frag:
        out.add(_norm(frag))
    return {x for x in out if x}


def _sim(a: str, b: str) -> float:
    if a == b:
        return 1.0
    ta, tb = set(a.split()), set(b.split())
    jac = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
    # character trigram Dice
    def grams(s):
        s = f"  {s} "
        return {s[i:i + 3] for i in range(len(s) - 2)}
    ga, gb = grams(a), grams(b)
    dice = 2 * len(ga & gb) / (len(ga) + len(gb)) if ga and gb else 0.0
    return max(jac, dice * 0.95)


def lexical_match(left: Graph, right: Graph, left_entities, right_entities,
                  threshold: float = 0.8) -> list[Cell]:
    """Best match per left entity above *threshold* (relation ``=``)."""
    rl = {r: lexicalizations(right, r) for r in right_entities}
    out = []
    for l in left_entities:
        ll = lexicalizations(left, l)
        best, score = None, 0.0
        for r, labels in rl.items():
            s = max((_sim(a, b) for a in ll for b in labels), default=0.0)
            if s > score:
                best, score = r, s
        if best is not None and score >= threshold:
            out.append(Cell(l, best, round(score, 3), "="))
    return sorted(out, key=lambda c: -c.measure)
