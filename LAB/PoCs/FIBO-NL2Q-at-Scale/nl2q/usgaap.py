"""The FASB US GAAP 2015 taxonomy as a definition source for FIBEN's FRO classes.

116 FIBEN classes come from the Financial Report Ontology (FRO), which is built from the
US GAAP taxonomy, not from FIBO, so FIBO has no definitions for them. The taxonomy does:
its documentation linkbase defines every element, and its label linkbase gives the
standard and terse labels accountants use ("Revenues", "Net Income (Loss)").

Only the two label linkbases are needed (git-ignored, ~29 MB, free under the FASB
taxonomy terms of use):

    mkdir -p data/raw/us-gaap-2015 && cd data/raw/us-gaap-2015
    curl -O https://xbrl.fasb.org/us-gaap/2015/elts/us-gaap-doc-2015-01-31.xml
    curl -O https://xbrl.fasb.org/us-gaap/2015/elts/us-gaap-lab-2015-01-31.xml

FIBEN's data uses elements from the 2012-2019 taxonomies; element names are stable across
these releases, and 2015 is the year FIBEN's own identifiers cite most
(``us-gaap/2015_LiabilitiesCurrent``).
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from . import paths

DOC_FILE = "us-gaap-doc-2015-01-31.xml"
LAB_FILE = "us-gaap-lab-2015-01-31.xml"
XLINK = "{http://www.w3.org/1999/xlink}"
LINK = "{http://www.xbrl.org/2003/linkbase}"
ROLES = {  # label role -> Element field
    "http://www.xbrl.org/2003/role/label": "label",
    "http://www.xbrl.org/2003/role/terseLabel": "terse",
    "http://www.xbrl.org/2003/role/verboseLabel": "verbose",
    "http://www.xbrl.org/2003/role/documentation": "documentation",
}


@dataclass
class Element:
    name: str                      # local name, e.g. NetIncomeLoss
    label: str = ""
    terse: str = ""
    verbose: str = ""
    documentation: str = ""

    def labels(self) -> list[str]:
        return list(dict.fromkeys(x for x in (self.label, self.terse, self.verbose) if x))


@dataclass
class Taxonomy:
    elements: dict[str, Element] = field(default_factory=dict)
    by_upper: dict[str, str] = field(default_factory=dict)   # NETINCOMELOSS -> NetIncomeLoss

    def get(self, name: str) -> Element | None:
        """Look an element up by its local name, case-insensitively (FIBEN's table
        names are the upper-cased element or disclosure names)."""
        key = self.by_upper.get(name.upper())
        return self.elements.get(key) if key else None


def parse_linkbase(path: Path, into: dict[str, Element]) -> None:
    """Read one label linkbase: locators name the element, arcs connect a locator to
    label resources, and each resource's role says which kind of label it is."""
    loc: dict[str, str] = {}
    res: dict[str, list[tuple[str, str]]] = {}
    arcs: list[tuple[str, str]] = []
    for _, el in ET.iterparse(path):
        tag = el.tag
        if tag == f"{LINK}loc":
            href = el.get(f"{XLINK}href", "")
            loc[el.get(f"{XLINK}label")] = href.split("#", 1)[-1].split("_", 1)[-1]
        elif tag == f"{LINK}label":
            role = ROLES.get(el.get(f"{XLINK}role", ""))
            if role and (el.text or "").strip():
                res.setdefault(el.get(f"{XLINK}label"), []).append((role, " ".join(el.text.split())))
        elif tag == f"{LINK}labelArc":
            arcs.append((el.get(f"{XLINK}from"), el.get(f"{XLINK}to")))
        el.clear()
    for frm, to in arcs:
        name = loc.get(frm)
        if not name:
            continue
        e = into.setdefault(name, Element(name))
        for role, text in res.get(to, []):
            if not getattr(e, role):
                setattr(e, role, text)


def build(directory: Path = paths.USGAAP_DIR) -> Taxonomy:
    elements: dict[str, Element] = {}
    for f in (LAB_FILE, DOC_FILE):
        p = directory / f
        if not p.exists():
            raise FileNotFoundError(f"{p} is missing; see the download steps in nl2q/usgaap.py")
        parse_linkbase(p, elements)
    return Taxonomy(elements, {k.upper(): k for k in elements})


@lru_cache(maxsize=1)
def load() -> Taxonomy:
    cache = paths.CACHE / "usgaap_2015.json"
    if cache.exists():
        raw = json.loads(cache.read_text(encoding="utf-8"))
        elements = {k: Element(**v) for k, v in raw.items()}
        return Taxonomy(elements, {k.upper(): k for k in elements})
    t = build()
    paths.CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({k: asdict(v) for k, v in t.elements.items()}), encoding="utf-8")
    return t


def available() -> bool:
    return all((paths.USGAAP_DIR / f).exists() for f in (DOC_FILE, LAB_FILE)) or \
        (paths.CACHE / "usgaap_2015.json").exists()
