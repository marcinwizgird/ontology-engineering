"""Semantic enrichment of the mapped terms, without the post-hoc glossary.

Only 48 of the 220 mapped terms carried a definition: alignment imports one only for an
``exact`` FIBO match, the 116 FRO / US GAAP classes have no FIBO counterpart, and the 25
``suggested`` FIBO matches were never reviewed. Three layers close the gap, each with its
provenance recorded per term, and each switchable for the ablation (``nl2q.h1``):

* ``review`` — the 25 suggestions, decided in ``artifacts/knowledge/alignment_review.csv``
  with a SKOS match type. ``exact`` / ``close`` import the FIBO definition and synonyms;
  ``broad`` / ``narrow`` / ``related`` import only the FIBO label as a synonym (the
  definition would describe a different concept); ``reject`` imports nothing.
* ``usgaap`` — the FASB US GAAP taxonomy (``nl2q.usgaap``). A class is linked to taxonomy
  elements by (1) the elements its rows actually carry in FIBEN's data
  (``HASUNIQUEIDENTIFIER``, financial-statement subclasses only), then (2) its name:
  the element itself, its plural, the element with a standard US GAAP qualifier
  (``Current``, ``Net``, ``NetOfTax`` ...) or the disclosure text block. The definition
  is the element's documentation; its labels become synonyms.
* ``derived`` — a structural definition from the schema for whatever is still undefined
  (mostly properties): what the property belongs to, its value type, and for
  low-cardinality code columns their values. Lowest trust, so it is a separate layer.

No layer reads the gold SQL, the gold SPARQL or the questions: unlike the K4 glossary, the
enrichment cannot carry benchmark knowledge.

    python -m nl2q.enrich      # writes enrichment.csv, enrichment.ttl, enrichment_summary.json
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache

from . import paths, schema, vkg_build

LAYERS = ("review", "usgaap", "derived")
REVIEW_CSV = paths.KNOWLEDGE_DIR / "alignment_review.csv"
MATCH_TYPES = {"exact", "close", "broad", "narrow", "related", "reject"}
IMPORTS_DEFINITION = {"exact", "close"}

#: US GAAP qualifiers that turn a concept name into the reported element
#: (Liabilities -> LiabilitiesCurrent, ComprehensiveIncome -> ComprehensiveIncomeNetOfTax)
QUALIFIERS = ["", "Current", "Noncurrent", "CurrentAndNoncurrent", "Net", "Gross", "NetOfTax",
              "NetOfTaxIncludingPortionAttributableToNoncontrollingInterest", "Total"]
TEXT_BLOCKS = ["DisclosureTextBlock", "TextBlock", "PolicyTextBlock", "TableTextBlock"]
_BLOCK_LABEL = re.compile(r"\s*\[(?:Text Block|Policy Text Block|Table Text Block|Abstract)\]\s*$")
#: code columns whose distinct values describe the property (<= this many values)
MAX_CODE_VALUES = 8


@dataclass
class Enrichment:
    local: str
    kind: str
    definition: str = ""
    source: str = ""                       # fibo | fibo-reviewed | us-gaap | derived
    synonyms: list[str] = field(default_factory=list)
    match: str = ""                        # SKOS match type for a reviewed FIBO term
    target: str = ""                       # the reviewed FIBO IRI
    elements: list[str] = field(default_factory=list)   # linked US GAAP elements
    method: str = ""                       # how the definition's source was found


# ----------------------------------------------------------------------------- #
# review
# ----------------------------------------------------------------------------- #
def load_review() -> list[dict]:
    with REVIEW_CSV.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        if r["decision"] not in MATCH_TYPES:
            raise ValueError(f"{r['fiben']}: unknown decision {r['decision']!r}")
        if r["decision"] != "reject" and not r["fibo"]:
            raise ValueError(f"{r['fiben']}: decision {r['decision']} needs a FIBO target")
    return rows


def _review_layer(out: dict[str, Enrichment], align: dict[str, dict]) -> None:
    from . import fibo
    f = fibo.load()
    for r in load_review():
        if r["decision"] == "reject":
            continue
        t = f.terms[r["fibo"]]
        local = align[r["fiben"], r["kind"]]["local"]
        e = out.setdefault(local, Enrichment(local, r["kind"]))
        e.match, e.target, e.method = r["decision"], t.iri, "review"
        if r["decision"] in IMPORTS_DEFINITION and t.definition:
            e.definition, e.source = t.definition, "fibo-reviewed"
            e.synonyms += [t.label, *t.synonyms, *t.abbreviations]
        else:
            e.synonyms.append(t.label)


# ----------------------------------------------------------------------------- #
# US GAAP
# ----------------------------------------------------------------------------- #
def observed_elements() -> dict[str, list[str]]:
    """FIBEN financial-statement subclass table -> the US GAAP elements its rows carry,
    most frequent first (``us-gaap/2015_NetIncomeLoss`` -> ``NetIncomeLoss``)."""
    from .load_fiben import connect
    s = schema.load()
    root = "ELEMENTOFFINANCIALSTATEMENT"
    con = connect()
    out = {}
    for child, parent in s.subclass_edges:
        if parent != root:
            continue
        pk, rpk = s.tables[child].pk[0], s.tables[root].pk[0]
        rows = con.execute(
            f'SELECT e."HASUNIQUEIDENTIFIER", count(*) FROM "{paths.SCHEMA}"."{child}" x '
            f'JOIN "{paths.SCHEMA}"."{root}" e ON x."{pk}" = e."{rpk}" GROUP BY 1').fetchall()
        names = Counter()
        for ident, n in rows:
            if ident:
                names[ident.split("_", 1)[-1]] += n
        out[child] = [n for n, _ in names.most_common()]
    return out


def _forms(stem: str) -> list[str]:
    """The upper-cased name and its plurals (LIABILITY -> LIABILITIES, REVENUE -> REVENUES)."""
    out = [stem, stem + "S", stem + "ES"]
    if stem.endswith("Y"):
        out.append(stem[:-1] + "IES")
    return out


def link_elements(table: str, tx, observed: dict[str, list[str]]) -> tuple[list[str], str]:
    """US GAAP elements for a FIBEN class table, and the method that found them."""
    if observed.get(table):
        found = [n for n in observed[table] if tx.get(n)]
        if found:
            # the element named like the class defines it best (Liability -> Liabilities,
            # not the more frequent LiabilitiesAndStockholdersEquity); then by frequency
            named = [n for n in found if n.upper() in _forms(table)]
            return named + [n for n in found if n not in named], "observed"
    stems = [table] + ([table[:-len("DISCLOSURE")]] if table.endswith("DISCLOSURE") else [])
    for stem in stems:
        for base in _forms(stem):
            for q in QUALIFIERS:
                if (e := tx.get(base + q.upper())):
                    blocks = [b.name for b in (tx.get(base + t.upper()) for t in TEXT_BLOCKS) if b]
                    return [e.name, *blocks[:1]], "name" if not q and base == stem else "name-variant"
    for stem in stems:
        for t in TEXT_BLOCKS:
            if (e := tx.get(stem + t.upper())):
                return [e.name], "text-block"
    return [], ""


def _clean_label(label: str) -> str:
    return _BLOCK_LABEL.sub("", label).strip()


def _usgaap_layer(out: dict[str, Enrichment], align: dict[str, dict]) -> None:
    from . import usgaap
    tx = usgaap.load()
    observed = observed_elements()
    for (token, kind), a in align.items():
        if kind != "class" or a["status"] == "exact":
            continue
        e = out.get(a["local"])
        if e and e.source:                      # a reviewed FIBO definition wins
            continue
        names, method = link_elements(token, tx, observed)
        if not names:
            continue
        els = [tx.get(n) for n in names]
        e = out.setdefault(a["local"], Enrichment(a["local"], kind))
        doc = next((x.documentation for x in els if x.documentation), "")
        if doc:
            e.definition, e.source = doc, "us-gaap"
        e.synonyms += [_clean_label(lab) for x in els for lab in x.labels()]
        e.elements, e.method = names, method


# ----------------------------------------------------------------------------- #
# derived
# ----------------------------------------------------------------------------- #
def _derived_layer(out: dict[str, Enrichment], align: dict[str, dict], defined: set[str]) -> None:
    s = schema.load()
    lab = vkg_build.label
    parent = dict(s.subclass_edges)
    owners: dict[str, list[str]] = defaultdict(list)    # column -> tables that carry it
    ranges: dict[str, set[str]] = defaultdict(set)
    types: dict[str, str] = {}
    for t in s.tables.values():
        for fk in t.relation_fks:
            owners[fk.column].append(t.name)
            ranges[fk.column].add(fk.ref_table)
        for c in t.data_columns:
            owners[c.name].append(t.name)
            types[c.name] = c.xsd
    codes = _code_values(s, owners)
    for (token, kind), a in align.items():
        local = a["local"]
        if local in defined:
            continue
        if kind == "class":
            if token not in parent:
                continue                         # a root class: nothing structural to say
            text = f"{lab(token)}: a kind of {lab(parent[token])}"
        else:
            own = _top_owners(owners[token], parent)
            what = "relation" if kind == "object" else f"{types.get(token, 'value')} attribute"
            text = f"{lab(token)}: {what} of {', '.join(lab(o) for o in own)}"
            if kind == "object":
                text += f", linking to {', '.join(sorted(lab(r) for r in ranges[token]))}"
            if token in codes:
                text += f"; values {', '.join(codes[token])}"
        e = out.setdefault(local, Enrichment(local, kind))
        e.definition, e.source, e.method = text, "derived", "schema"


def _top_owners(tables: list[str], parent: dict[str, str], limit: int = 3) -> list[str]:
    """The most general tables carrying a column: a column every disclosure subclass
    repeats is described once, as an attribute of their common parent."""
    tabs = set(tables)
    tops = sorted({t for t in tabs if parent.get(t) not in tabs})
    if len(tops) > limit:
        roots = Counter(parent.get(t, t) for t in tops)
        tops = [r for r, _ in roots.most_common(limit)]
    return tops


def _code_values(s, owners: dict[str, list[str]]) -> dict[str, list[str]]:
    """Distinct values of low-cardinality string columns (codes such as 10-K / 10-Q),
    over every table that carries the column."""
    from .load_fiben import connect
    con = connect()
    values: dict[str, set[str]] = defaultdict(set)
    too_many: set[str] = set()
    for t in s.tables.values():
        for c in t.data_columns:
            if c.xsd != "string" or c.name in too_many:
                continue
            rows = con.execute(f'SELECT DISTINCT "{c.name}" FROM "{paths.SCHEMA}"."{t.name}" '
                               f'WHERE "{c.name}" IS NOT NULL LIMIT {MAX_CODE_VALUES + 1}').fetchall()
            values[c.name] |= {str(v[0]) for v in rows if str(v[0]) not in ("", "None")}
            if len(values[c.name]) > MAX_CODE_VALUES:
                too_many.add(c.name)
    return {c: sorted(v) for c, v in values.items()
            if c not in too_many and v and all(len(x) <= 20 for x in v)}


# ----------------------------------------------------------------------------- #
def _alignment() -> dict[tuple[str, str], dict]:
    with (paths.KNOWLEDGE_DIR / "alignment.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["local"] = r["iri"].rsplit("#", 1)[-1]
    return {(r["fiben"], r["kind"]): r for r in rows}


def fibo_defined(align: dict[tuple[str, str], dict]) -> set[str]:
    """Terms that already carry a definition: an exact FIBO match whose FIBO term has one."""
    from . import fibo
    f = fibo.load()
    return {a["local"] for a in align.values()
            if a["status"] == "exact" and a["fibo"] in f.terms and f.terms[a["fibo"]].definition}


def build(layers: tuple[str, ...] = LAYERS) -> dict[str, Enrichment]:
    """Enrichment per mapped term (local name), for the requested layers."""
    unknown = set(layers) - set(LAYERS)
    if unknown:
        raise ValueError(f"unknown enrichment layers {sorted(unknown)}")
    align = _alignment()
    out: dict[str, Enrichment] = {}
    if "review" in layers:
        _review_layer(out, align)
    if "usgaap" in layers:
        _usgaap_layer(out, align)
    if "derived" in layers:
        defined = fibo_defined(align) | {k for k, e in out.items() if e.definition}
        _derived_layer(out, align, defined)
    for e in out.values():
        e.synonyms = list(dict.fromkeys(x for x in e.synonyms if x))
    return out


@lru_cache(maxsize=8)
def load(layers: tuple[str, ...] = LAYERS) -> dict[str, Enrichment]:
    return build(layers)


def write() -> dict:
    """Versioned outputs: per-term provenance (CSV), SKOS annotations (Turtle) and a summary."""
    from rdflib import Graph, Literal, Namespace, URIRef
    from rdflib.namespace import DCTERMS, SKOS
    enr = load()
    align = _alignment()
    rows = []
    from_fibo = fibo_defined(align)
    for a in align.values():
        e = enr.get(a["local"])
        source = "fibo" if a["local"] in from_fibo else (e.source if e and e.definition else "")
        defined = bool(source)
        rows.append({"local": a["local"], "kind": a["kind"], "defined": int(defined), "source": source,
                     "match": e.match if e else "", "fibo": e.target if e else "",
                     "us_gaap": " ".join(e.elements) if e else "",
                     "method": e.method if e else "", "synonyms": " | ".join(e.synonyms) if e else "",
                     "definition": e.definition if e else ""})
    with (paths.KNOWLEDGE_DIR / "enrichment.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["kind"], r["local"])))

    g = Graph()
    voc = Namespace(vkg_build.VOC)
    g.bind("fiben", voc)
    g.bind("skos", SKOS)
    g.bind("dct", DCTERMS)
    usg = "http://fasb.org/us-gaap/2015#"
    for e in enr.values():
        s = voc[e.local]
        if e.definition:
            g.add((s, SKOS.definition, Literal(e.definition, lang="en")))
            g.add((s, DCTERMS.source, Literal(e.source)))
        for syn in e.synonyms:
            g.add((s, SKOS.altLabel, Literal(syn, lang="en")))
        if e.match:
            g.add((s, SKOS[f"{e.match}Match"], URIRef(e.target)))
        for n in e.elements:
            g.add((s, SKOS.relatedMatch, URIRef(usg + n)))
    g.serialize(paths.KNOWLEDGE_DIR / "enrichment.ttl", format="turtle")

    c = Counter(r["source"] or "none" for r in rows)
    summary = {
        "mapped_terms": len(rows),
        "defined": sum(r["defined"] for r in rows),
        "by_source": dict(sorted(c.items())),
        "by_kind": {k: f"{sum(r['defined'] for r in rows if r['kind'] == k)}/"
                       f"{sum(r['kind'] == k for r in rows)}" for k in ("class", "object", "datatype")},
        "usgaap_link_methods": dict(Counter(e.method for e in enr.values() if e.source == "us-gaap")),
        "review_decisions": dict(Counter(r["decision"] for r in load_review())),
    }
    (paths.KNOWLEDGE_DIR / "enrichment_summary.json").write_text(json.dumps(summary, indent=1),
                                                                  encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(write(), indent=1))
