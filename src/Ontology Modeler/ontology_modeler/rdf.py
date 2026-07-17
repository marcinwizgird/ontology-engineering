"""RDF file discovery, named-graph naming, and IRI helpers.

Pure functions with no I/O beyond walking the filesystem: what to upload, what graph
URI a file maps to, and how to abbreviate IRIs. Shared by the uploader (file -> graph)
and the LPG converter (IRI -> short name / edge type).
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

from .config import REPO_ROOT

# Fuseki picks its parser from the Content-Type, so this map is the only thing that
# decides how a file is read.
CONTENT_TYPES = {
    ".ttl": "text/turtle",
    ".turtle": "text/turtle",
    ".n3": "text/n3",
    ".nt": "application/n-triples",
    ".rdf": "application/rdf+xml",
    ".owl": "application/rdf+xml",
    ".xml": "application/rdf+xml",
    ".jsonld": "application/ld+json",
    ".json": "application/ld+json",
    ".trig": "application/trig",
    ".nq": "application/n-quads",
}

# Directories that hold no ontologies but plenty of files. FIBO vendors its own .git
# (hundreds of MB), which would otherwise dominate the scan.
SKIP_DIRS = {".git", ".github", "node_modules", "__pycache__", ".ipynb_checkpoints"}

# OASIS XML catalogs map ontology IRIs to local files for tools like Protege. They
# share the .xml extension with RDF/XML but are not RDF, so a parser that trusts the
# extension fails on them.
SKIP_FILES = {"catalog-v001.xml"}


def content_type_for(path: Path) -> str | None:
    """The Content-Type to send for a file, or None if the extension is not RDF."""
    return CONTENT_TYPES.get(path.suffix.lower())


def iter_rdf_files(paths: list[Path]) -> list[Path]:
    """Expand files/directories into a sorted, de-duplicated list of RDF files.

    Directories recurse; SKIP_DIRS and SKIP_FILES (vendored .git, OASIS catalogs) are
    excluded; only extensions in CONTENT_TYPES are kept.
    """
    found: set[Path] = set()
    for path in paths:
        if not path.exists():
            print(f"warning: skipping missing path: {path}", file=sys.stderr)
            continue
        if path.is_file():
            found.add(path.resolve())
            continue
        for child in path.rglob("*"):
            if not child.is_file():
                continue
            if SKIP_DIRS.intersection(child.parts):
                continue
            if child.name in SKIP_FILES:
                continue
            if child.suffix.lower() in CONTENT_TYPES:
                found.add(child.resolve())
    return sorted(found)


def graph_uri(file: Path) -> str:
    """The named-graph URI for a file, derived from its repo-relative path.

    e.g. urn:graph:Ontology%20Repository/FIBO/fibo/FND/AllFND.rdf -- stable, so PUT
    idempotency is meaningful, and readable, because '/' is left unescaped.
    """
    try:
        rel = file.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel = file.as_posix()
    return "urn:graph:" + quote(rel, safe="/")


def repo_relative(file: Path) -> str:
    """A file's repo-relative POSIX path, or its name if it lives outside the repo."""
    try:
        return file.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return file.name


# --- IRI naming ------------------------------------------------------------- #

def local_name(iri: str) -> str:
    """The local name of an IRI (after the last # or /)."""
    for sep in ("#", "/"):
        if sep in iri:
            tail = iri.rsplit(sep, 1)[-1]
            if tail:
                return tail
    return iri


def short_name(iri: str) -> str:
    """A readable prefixed local name, e.g. ClientsAndAccounts:DepositAccount.

    Derived from the last path segment before the local name. Not the exact FIBO curie
    (`fibo-fbc-fct-fse:`), which would need FIBO's full prefix registry; this is a
    stable, human-legible approximation that needs no external mapping.
    """
    local = local_name(iri)
    stem = iri[: len(iri) - len(local)].rstrip("/#")
    module = stem.rsplit("/", 1)[-1] if "/" in stem else stem
    return f"{module}:{local}" if module else local


def rel_type_of(prop_iri: str) -> str:
    """A sanitised uppercase Cypher relationship type for an object property.

    The local name, uppercased, non-alphanumerics to underscore; a leading digit gets a
    'P_' prefix so the token is a legal (and safely interpolatable) relationship type.
    """
    token = "".join(ch if ch.isalnum() else "_" for ch in local_name(prop_iri)).upper().strip("_")
    if not token:
        token = "REL"
    if token[0].isdigit():
        token = "P_" + token
    return token
