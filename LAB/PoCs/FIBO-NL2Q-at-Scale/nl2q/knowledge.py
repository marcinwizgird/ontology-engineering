"""The knowledge pack: everything grounding may read, built deterministically.

* **terms** — the two-tier concept index:
  - tier ``mapped``: the FIBEN ontology's classes and properties (answerable), with
    their segmented label, the aligned FIBO term's label/definition/synonyms when the
    alignment is ``exact``;
  - tier ``fibo``: every other FIBO term — known to the domain but not mapped to this
    data; a match here explains a refusal ("FIBO defines X, this data does not map it").
* **glossary** — curated local knowledge (``nl2q.glossary``).
* **values** — the value index: distinct values of name-like and code columns, keyed by
  (class, property), read *through the mapping* from the database at build time.
  Personal names are included only when ``include_personal=True`` (FIBEN's people are
  synthetic; in a bank this is a policy switch).

Knowledge levels used by the ablation (cumulative):
  K0 bare local names · K1 + labels/definitions · K2 + synonyms/abbreviations/values ·
  K3 + allowed paths (query graph) · K4 + glossary · K5 + example bank.

Semantic enrichment (``nl2q.enrich``) is orthogonal to the levels: it adds definitions
(read at K1+) and synonyms (K2+) to mapped terms FIBO leaves undefined, from the reviewed
FIBO suggestions, the US GAAP taxonomy and the schema. ``NL2Q_ENRICH`` selects its layers
(comma-separated, e.g. ``review,usgaap,derived``). The default is ``none``: on the FIBEN
train split enrichment adds under one point of candidate recall and costs 2.7 points at
K4 (RESULTS.md §5.1), so the arms keep the pack their published results used.
"""

from __future__ import annotations

import csv
import json
import os
import pickle
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from functools import lru_cache

from . import fibo, paths, schema, vkg_build

VOC = str(vkg_build.VOC)


def _layers(spec: str) -> tuple[str, ...]:
    from .enrich import LAYERS
    return () if spec.strip() in ("", "none") else tuple(x for x in LAYERS if x in spec.split(","))


#: the enrichment layers used when a caller does not choose (``nl2q.h1`` sets this per config)
ENRICH: tuple[str, ...] = _layers(os.environ.get("NL2Q_ENRICH", "none"))


@dataclass
class TermDoc:
    iri: str
    local: str
    kind: str                       # class | object | datatype
    tier: str                       # mapped | fibo
    label: str = ""
    definition: str = ""
    synonyms: list[str] = field(default_factory=list)
    notation: str = ""              # FIBEN table / column
    fibo_iri: str = ""
    source: str = ""                # where the definition comes from: fibo | fibo-reviewed | us-gaap | derived

    def text(self, level: int = 4) -> str:
        parts = [self.local if level == 0 else self.label or self.local]
        if level >= 1 and self.definition:
            parts.append(self.definition)
        if level >= 2 and self.synonyms:
            parts.append(" ".join(self.synonyms))
        return " . ".join(parts)


def build_terms(enrich: tuple[str, ...] = ()) -> list[TermDoc]:
    f = fibo.load()
    from . import enrich as _enrich
    enr = _enrich.load(enrich) if enrich else {}
    docs: list[TermDoc] = []
    aligned: set[str] = set()
    with (paths.KNOWLEDGE_DIR / "alignment.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            local = row["iri"].rsplit("#", 1)[-1]
            d = TermDoc(row["iri"], local, row["kind"], "mapped", vkg_build.label(row["fiben"]),
                        notation=row["fiben"])
            if row["status"] == "exact" and row["fibo"] in f.terms:
                t = f.terms[row["fibo"]]
                d.definition = t.definition
                d.synonyms = sorted(set(t.synonyms) | set(t.abbreviations))
                d.fibo_iri = t.iri
                d.source = "fibo" if t.definition else ""
                aligned.add(t.iri)
            if (e := enr.get(local)) is not None:
                if not d.definition and e.definition:
                    d.definition, d.source = e.definition, e.source
                d.synonyms = sorted(set(d.synonyms) | set(e.synonyms) - {d.label})
            docs.append(d)
    for t in f.terms.values():
        if t.iri in aligned or not t.label:
            continue
        docs.append(TermDoc(t.iri, t.local, t.kind, "fibo", t.label, t.definition,
                            sorted(set(t.synonyms) | set(t.abbreviations)), fibo_iri=t.iri))
    return docs


# ----------------------------------------------------------------------------- #
# value index
# ----------------------------------------------------------------------------- #
#: (table, column) -> include. Name-like and code columns; free text and ids excluded.
VALUE_COLUMNS = [
    ("CORPORATION", "HASLEGALNAME", False), ("CORPORATION", "HASTICKERSYMBOL", False),
    ("LISTEDSECURITY", "HASLEGALNAME", False), ("LISTEDSECURITY", "HASTICKERSYMBOL", False),
    ("FINANCIALMARKET", "HASNAME", False), ("COUNTRY", "HASNAME", False),
    ("INDUSTRYSECTORCLASSIFIER", "HASFORMALNAME", False),
    ("INDUSTRYSECTORCLASSIFIER", "HASDESCRIPTION", False),
    ("CONTRACT", "HASTITLE", False), ("CONTRACT", "HASPOSITION", False),
    ("POSTALADDRESS", "HASSTATE", False), ("POSTALADDRESS", "HASCITY", False),
    ("ELEMENTOFFINANCIALSTATEMENT", "APPLICABLEPERIOD", False),
    ("ELEMENTOFFINANCIALSTATEMENT", "HASDOCUMENTTYPE", False),
    ("ELEMENTOFFINANCIALSTATEMENT", "HASMETRICENDQUARTER", False),
    ("PERSON", "HASGENDER", False),
    ("PERSON", "HASPERSONNAME", True), ("PERSON", "HASFIRSTNAME", True),
    ("PERSON", "HASLASTNAME", True),
]


@dataclass
class ValueEntry:
    value: str
    cls: str                        # fiben class local name
    prop: str                       # fiben property local name
    count: int


def build_values(include_personal: bool = True) -> list[ValueEntry]:
    from .load_fiben import connect
    con = connect()
    out = []
    for table, col, personal in VALUE_COLUMNS:
        if personal and not include_personal:
            continue
        rows = con.execute(f'SELECT "{col}", count(*) FROM "{paths.SCHEMA}"."{table}" '
                           f'WHERE "{col}" IS NOT NULL AND "{col}" <> \'None\' GROUP BY 1').fetchall()
        cls, prop = vkg_build.class_name(table), vkg_build.prop_name(col)
        out += [ValueEntry(str(v), cls, prop, n) for v, n in rows]
    return out


# ----------------------------------------------------------------------------- #
@dataclass
class Pack:
    terms: list[TermDoc]
    values: list[ValueEntry]
    glossary: list[dict]
    edges: list[tuple[str, str, str]]
    subclass: dict[str, str]                 # class local -> parent local (FIBEN)

    def mapped(self) -> list[TermDoc]:
        return [t for t in self.terms if t.tier == "mapped"]

    def term(self, local: str) -> TermDoc | None:
        return self._by_local().get(local)

    @lru_cache(maxsize=1)  # noqa: B019 - one pack per process
    def _by_local(self) -> dict[str, TermDoc]:
        return {t.local: t for t in self.terms if t.tier == "mapped"}

    def __hash__(self) -> int:
        return id(self)


def _local(iri: str) -> str:
    return re.split(r"[#/]", iri)[-1]


def build(include_personal: bool = True, enrich: tuple[str, ...] = ()) -> Pack:
    s = schema.load()
    edges = [tuple(_local(x) for x in e) for e in
             json.loads((paths.KNOWLEDGE_DIR / "edges.json").read_text(encoding="utf-8"))]
    from .glossary import GLOSSARY
    sub = {vkg_build.class_name(a): vkg_build.class_name(b) for a, b in s.subclass_edges}
    return Pack(build_terms(enrich), build_values(include_personal), GLOSSARY, edges, sub)


def load(include_personal: bool = True, enrich: tuple[str, ...] | None = None) -> Pack:
    return _load(include_personal, ENRICH if enrich is None else tuple(enrich))


@lru_cache(maxsize=8)
def _load(include_personal: bool, enrich: tuple[str, ...]) -> Pack:
    tag = "-".join(enrich) or "none"
    cache = paths.CACHE / f"pack_{int(include_personal)}_{tag}.pkl"
    if cache.exists():
        with cache.open("rb") as fh:
            return pickle.load(fh)
    p = build(include_personal, enrich)
    paths.CACHE.mkdir(parents=True, exist_ok=True)
    with cache.open("wb") as fh:
        pickle.dump(p, fh)
    return p


def write_summary() -> dict:
    p = load()
    summary = {
        "mapped_terms": len(p.mapped()),
        "mapped_with_fibo_definition": sum(t.source == "fibo" for t in p.mapped()),
        "mapped_with_definition": sum(bool(t.definition) for t in p.mapped()),
        "definition_sources": dict(sorted(Counter(t.source or "none" for t in p.mapped()).items())),
        "enrichment_layers": list(ENRICH),
        "fibo_tier_terms": sum(t.tier == "fibo" for t in p.terms),
        "values": len(p.values),
        "glossary_entries": len(p.glossary),
        "allowed_edges": len(p.edges),
        "subclass_links": len(p.subclass),
    }
    (paths.KNOWLEDGE_DIR / "pack_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


if __name__ == "__main__":
    from nl2q import knowledge as _k  # pickle under the module path, not __main__
    print(_k.write_summary())
