"""Maintenance script: vendor a sample of real FIBO modules for the Chapter 1 problem set.

Not used by the notebooks; it produced ``fibo/`` and ``fibo_index.json`` from the
repository's FIBO checkout (``Ontology Repository/FIBO/fibo``) and can be re-run.

* ``fibo/*.rdf``: 40 modules under 60 KB, drawn with a fixed seed from the whole of
  FIBO (excluding the ``About*``, ``All*`` and ``Metadata*`` files, which only list
  imports, and ``etc``), copied unchanged and named after their FIBO path.
* ``fibo_index.json``: what the registry knows about every FIBO module those 40
  import, transitively: its IRI, its file, its ``owl:imports`` and the classes it
  declares. Imports outside FIBO (e.g. OMG Commons) are listed but not available,
  exactly as a registry that holds only FIBO would see them.

FIBO is published by the EDM Council under the MIT License (see ``fibo/LICENSE``).

    python _vendor_fibo.py
"""

from __future__ import annotations

import json
import logging
import random
import shutil
from pathlib import Path

import rdflib
from rdflib import OWL, RDF

HERE = Path(__file__).resolve().parent
FIBO = HERE.parents[3] / "Ontology Repository" / "FIBO" / "fibo"
BASE = "https://spec.edmcouncil.org/fibo/ontology/"
SAMPLE_SIZE, SEED = 40, 0


def file_of(iri: str) -> Path | None:
    """FIBO's file layout mirrors its IRIs: .../FND/Agreements/Contracts/ -> FND/Agreements/Contracts.rdf"""
    if not iri.startswith(BASE):
        return None
    path = FIBO / (iri[len(BASE):].rstrip("/") + ".rdf")
    return path if path.is_file() else None


def local_name(fibo_file: str) -> str:
    """FND/Agreements/Contracts.rdf -> FND-Agreements-Contracts.rdf"""
    return fibo_file.replace("/", "-")


def describe(path: Path) -> dict:
    g = rdflib.Graph().parse(path, format="xml")
    onto = next(iter(g.subjects(RDF.type, OWL.Ontology)))
    return {"iri": str(onto), "file": str(path.relative_to(FIBO)).replace("\\", "/"),
            "imports": sorted(str(o) for o in g.objects(onto, OWL.imports)),
            "classes": sorted(str(c) for c in g.subjects(RDF.type, OWL.Class)
                              if isinstance(c, rdflib.URIRef))}


def main() -> None:
    logging.getLogger("rdflib").setLevel(logging.ERROR)   # FIBO has a few malformed dates
    candidates = sorted(p for p in FIBO.rglob("*.rdf")
                        if p.stat().st_size < 60_000
                        and not p.name.startswith(("About", "All", "Metadata"))
                        and "etc" not in p.relative_to(FIBO).parts)
    sample = random.Random(SEED).sample(candidates, SAMPLE_SIZE)

    index: dict[str, dict] = {}
    queue = [describe(p) for p in sample]
    sampled = [m["iri"] for m in queue]
    while queue:
        m = queue.pop()
        if m["iri"] in index:
            continue
        index[m["iri"]] = m
        for imp in m["imports"]:
            if imp not in index and (f := file_of(imp)) is not None:
                queue.append(describe(f))

    out = HERE / "fibo"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    shutil.copy(FIBO / "LICENSE", out / "LICENSE")
    for iri in sampled:
        shutil.copy(FIBO / index[iri]["file"], out / local_name(index[iri]["file"]))
    (HERE / "fibo_index.json").write_text(json.dumps(
        {"source": "EDM Council FIBO (MIT License), sampled by _vendor_fibo.py",
         "sampled": sampled, "modules": index}, indent=1), encoding="utf-8")
    print(f"{len(sampled)} modules vendored; index covers {len(index)} FIBO modules")


if __name__ == "__main__":
    main()
