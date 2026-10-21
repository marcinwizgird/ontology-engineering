"""The catalog record: what a person decides about an ontology, as DCAT in ``metadata``.

One node per project, ``urn:sip:p:{p}:record``, typed ``dcat:Dataset`` and
``sip:CatalogRecord``. Computed values (counts, quality, last change) are never stored
here; they belong to the derived catalog entry (``catalog.py``), so the record holds only
human decisions and has history and undo like any other content.
"""

from __future__ import annotations

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, RDF

from ..core.namespaces import DCAT, SIP

#: field -> (predicate, many, kind). kind: "text" (language-tagged literal),
#: "plain" (plain literal), "iri" (an IRI if it looks like one, else a plain literal).
FIELDS: dict[str, tuple[URIRef, bool, str]] = {
    "title": (DCTERMS.title, False, "text"),
    "description": (DCTERMS.description, False, "text"),
    "keywords": (DCAT.keyword, True, "text"),
    "domain": (DCAT.theme, False, "plain"),
    "licence": (DCTERMS.license, False, "iri"),
    "contact": (DCAT.contactPoint, False, "plain"),
    "homepage": (DCAT.landingPage, False, "iri"),
}


def record_node(project: str) -> URIRef:
    return URIRef(f"urn:sip:p:{project}:record")


def _term(value: str, kind: str, lang: str | None):
    if kind == "iri" and value.startswith(("http://", "https://", "urn:")):
        return URIRef(value)
    if kind == "text" and lang:
        return Literal(value, lang=lang)
    return Literal(value)


def record_delta(current: Graph, project: str, fields: dict,
                 lang: str | None) -> tuple[list[tuple], list[tuple]]:
    """Additions and removals that make the record carry ``fields``.

    A field given as ``None``, ``""`` or ``[]`` is cleared; a field not given is kept.
    """
    unknown = sorted(set(fields) - set(FIELDS))
    if unknown:
        raise ValueError(f"unknown record fields {unknown}; known: {sorted(FIELDS)}")
    node = record_node(project)
    add: list[tuple] = []
    rem: list[tuple] = []
    if (node, RDF.type, SIP.CatalogRecord) not in current:
        add += [(node, RDF.type, DCAT.Dataset), (node, RDF.type, SIP.CatalogRecord)]
    for name, value in fields.items():
        pred, many, kind = FIELDS[name]
        rem += [(node, pred, o) for o in current.objects(node, pred)]
        values = value if many else [value]
        if many and isinstance(value, str):
            raise ValueError(f"{name} is a list")
        for v in values or []:
            if v is None or str(v).strip() == "":
                continue
            add.append((node, pred, _term(str(v).strip(), kind, lang)))
    keep = set(add) & set(rem)
    return [t for t in add if t not in keep], [t for t in rem if t not in keep]


def read_record(g: Graph, project: str) -> dict:
    node = record_node(project)
    out: dict = {}
    for name, (pred, many, _) in FIELDS.items():
        vals = sorted(str(o) for o in g.objects(node, pred))
        out[name] = vals if many else (vals[0] if vals else None)
    return out
