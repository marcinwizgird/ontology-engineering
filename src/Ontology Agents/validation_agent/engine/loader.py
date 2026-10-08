"""Load a submission into an rdflib graph without touching the network.

* The serialisation comes from the declared format, the file suffix, or a content sniff.
* Parsing uses :data:`~.vocab.NO_BASE` as the base, so relative IRIs in a document
  without ``@base`` stay recognisable for SYN-02.
* ``owl:imports`` are recorded, never fetched (import fetching is off by default,
  OVA-P03). An import is reported as missing unless a local mirror maps it.
* A parse failure is returned, not raised: SYN-01 turns it into a finding and the
  pipeline short-circuits.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from rdflib import Graph
from rdflib.namespace import OWL

from .vocab import NO_BASE

MAX_BYTES = 50 * 1024 * 1024
"""Upload size limit (OVA-P03). Larger submissions belong to store pushdown (R1+)."""

SUFFIX_FORMATS = {
    ".ttl": "turtle", ".turtle": "turtle", ".n3": "n3", ".nt": "nt", ".ntriples": "nt",
    ".rdf": "xml", ".owl": "xml", ".xml": "xml", ".jsonld": "json-ld", ".json": "json-ld",
    ".trig": "trig", ".nq": "nquads",
}


@dataclass
class LoadResult:
    graph: Graph | None
    source: str
    format: str
    hash: str
    size: int
    error: str | None = None
    error_line: int | None = None
    imports: dict[str, list[str]] = field(default_factory=lambda: {"resolved": [], "missing": []})

    @property
    def loaded(self) -> bool:
        return self.graph is not None

    def summary(self) -> dict:
        return {"loaded": self.loaded, "source": self.source, "format": self.format,
                "triples": len(self.graph) if self.graph is not None else 0,
                "hash": self.hash, "bytes": self.size, "error": self.error,
                "error_line": self.error_line, "imports": self.imports}


def sniff_format(data: bytes, name: str = "") -> str:
    suffix = Path(name).suffix.lower()
    if suffix in SUFFIX_FORMATS and suffix not in (".owl", ".xml", ".json"):
        return SUFFIX_FORMATS[suffix]
    head = data[:2048].lstrip()
    if head.startswith(b"<?xml") or head.startswith(b"<rdf:RDF") or head.startswith(b"<Ontology"):
        return "xml"
    if head.startswith(b"{") or head.startswith(b"["):
        return "json-ld"
    return SUFFIX_FORMATS.get(suffix, "turtle")


def _xml_is_safe(data: bytes) -> bool:
    """Reject DOCTYPE/ENTITY declarations: the XXE guard for RDF/XML (OVA-P03)."""
    return not re.search(rb"<!(DOCTYPE|ENTITY)", data[:65536], re.IGNORECASE)


def load_bytes(data: bytes, name: str = "submission", fmt: str | None = None) -> LoadResult:
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    fmt = fmt or sniff_format(data, name)
    result = LoadResult(None, name, fmt, digest, len(data))
    if len(data) > MAX_BYTES:
        result.error = f"submission is {len(data)} bytes; the limit is {MAX_BYTES}"
        return result
    if fmt == "xml" and not _xml_is_safe(data):
        result.error = "RDF/XML with a DOCTYPE or ENTITY declaration is refused (XXE guard)"
        return result
    g = Graph()
    term_log = logging.getLogger("rdflib.term")
    level = term_log.level
    term_log.setLevel(logging.CRITICAL)   # ill-typed literals are reported by SYN-03
    try:
        g.parse(data=data, format=fmt, publicID=NO_BASE)
    except Exception as exc:  # every parser raises its own type
        msg = " ".join(str(exc).split())
        result.error = f"{type(exc).__name__}: {msg[:400]}"
        m = re.search(r"line (\d+)", str(exc))
        result.error_line = int(m.group(1)) if m else None
        return result
    finally:
        term_log.setLevel(level)
    result.graph = g
    result.imports["missing"] = sorted(str(o) for o in g.objects(None, OWL.imports))
    return result


def load_path(path: str | Path, fmt: str | None = None) -> LoadResult:
    p = Path(path)
    return load_bytes(p.read_bytes(), p.name, fmt)


def load_text(text: str, name: str = "submission.ttl", fmt: str | None = None) -> LoadResult:
    return load_bytes(text.encode("utf-8"), name, fmt)
