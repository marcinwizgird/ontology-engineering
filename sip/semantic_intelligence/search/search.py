"""Search — Semantic Turkey's ``Search.searchResource`` (regex strategy) and
Protégé's ``OWLEntityFinder``.

Modes (``SearchMode``): ``startsWith``, ``contains``, ``endsWith``, ``exact``
(all case-insensitive) and ``fuzzy`` — the *one-edit neighbourhood* of the
needle: one substituted character, or one extra leading/trailing character
(ST's regex builder produces exactly these; deletions are not included).
Sources: lexicalizations (by the project's lexicalization model), local name,
full IRI, notes. Language filter: exact tag, or tag prefix with
``include_locales`` (``en`` matches ``en-GB``). Results are de-duplicated per
(resource, matchMode) as in ST.

In production the Fuseki ``text:query`` (jena-text/Lucene) index plays the role
ST gives its GraphDB strategy: a pre-filter before the same match logic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from ..core.namespaces import SKOSXL
from ..owl.rendering import entity_role, local_name

MODES = ("startsWith", "contains", "endsWith", "exact", "fuzzy")
ROLES = ("cls", "concept", "conceptScheme", "individual", "property", "skosCollection",
         "dataRange")


def _matcher(needle: str, mode: str):
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    q = re.escape(needle)
    if mode == "startsWith":
        rx = f"^{q}"
    elif mode == "endsWith":
        rx = f"{q}$"
    elif mode == "contains":
        rx = q
    elif mode == "exact":
        rx = f"^{q}$"
    else:
        variants = [f".{q}", f"{q}."] + [re.escape(needle[:i]) + "." + re.escape(needle[i + 1:])
                                       for i in range(len(needle))]
        rx = "|".join(f"(^{v}$)" for v in variants)
    return re.compile(rx, re.I)


@dataclass(frozen=True)
class Hit:
    resource: str
    role: str
    match_mode: str
    matched: str
    source: str        # label | localName | uri | note


def _role_ok(role: str, roles) -> bool:
    if not roles:
        return True
    if role in roles:
        return True
    if "property" in roles and role in ("objectProperty", "datatypeProperty",
                                        "annotationProperty", "ontologyProperty"):
        return True
    return "skosCollection" in roles and role == "skosOrderedCollection"


def search_resource(g: Graph, text: str, *, roles=(), mode: str = "contains",
                    use_lexicalizations: bool = True, use_local_name: bool = False,
                    use_uri: bool = False, use_notes: bool = False, langs=(),
                    include_locales: bool = False, lexicalization: str = "rdfs",
                    schemes=(), limit: int = 200) -> list[Hit]:
    """Validation as in ``ServiceForSearches.checksPreQuery``."""
    if not text:
        raise ValueError("empty search string")
    if not (use_lexicalizations or use_local_name or use_uri or use_notes):
        raise ValueError("enable at least one of lexicalizations/localName/URI/notes")
    if use_notes and not use_lexicalizations:
        raise ValueError("useNotes requires useLexicalizations")
    bad = set(roles) - set(ROLES)
    if bad:
        raise ValueError(f"unsupported roles {sorted(bad)}")
    rx = _matcher(text, mode)
    langs = [l.lower() for l in langs]

    def lang_ok(l: Literal) -> bool:
        if not langs:
            return True
        tag = (l.language or "").lower()
        return any(tag == x or (include_locales and tag.startswith(x + "-")) for x in langs)

    label_props = {"rdfs": [RDFS.label], "skos": [SKOS.prefLabel, SKOS.altLabel,
                                                  SKOS.hiddenLabel],
                   "skosxl": []}.get(lexicalization, [RDFS.label])
    note_props = [SKOS.note, SKOS.definition, SKOS.scopeNote, SKOS.example, SKOS.editorialNote,
                  SKOS.historyNote, SKOS.changeNote, RDFS.comment]
    candidates = {s for s in g.subjects(RDF.type, None) if isinstance(s, URIRef)}
    hits: dict[tuple, Hit] = {}
    for r in sorted(candidates):
        role = entity_role(g, r)
        if not _role_ok(role, roles):
            continue
        if schemes and role == "concept":
            mine = set(g.objects(r, SKOS.inScheme)) | set(g.objects(r, SKOS.topConceptOf))
            if not (mine & set(schemes)):
                continue

        def hit(val: str, source: str):
            if rx.search(val) and (r, mode) not in hits:
                hits[(r, mode)] = Hit(str(r), role, mode, val, source)
        if use_lexicalizations:
            for p in label_props:
                for o in g.objects(r, p):
                    if isinstance(o, Literal) and lang_ok(o):
                        hit(str(o), "label")
            if lexicalization == "skosxl":
                for p in (SKOSXL.prefLabel, SKOSXL.altLabel, SKOSXL.hiddenLabel):
                    for xl in g.objects(r, p):
                        for lf in g.objects(xl, SKOSXL.literalForm):
                            if lang_ok(lf):
                                hit(str(lf), "label")
        if use_local_name:
            hit(local_name(r), "localName")
        if use_uri:
            hit(str(r), "uri")
        if use_notes:
            for p in note_props:
                for o in g.objects(r, p):
                    if isinstance(o, Literal) and lang_ok(o):
                        hit(str(o), "note")
        if len(hits) >= limit:
            break
    return list(hits.values())


def path_from_root_class(g: Graph, c: URIRef, root: URIRef = OWL.Thing) -> list[list[URIRef]]:
    """``getPathFromRoot`` for classes (``rdfs:subClassOf*`` up to *root*)."""
    out = []

    def walk(n, path):
        ps = [p for p in g.objects(n, RDFS.subClassOf) if isinstance(p, URIRef)]
        if n == root or not ps:
            out.append(list(reversed(path + [n])) if n == root else [root] + list(
                reversed(path + [n])))
            return
        for p in ps:
            if p not in path:
                walk(p, path + [n])
    walk(c, [])
    return out
