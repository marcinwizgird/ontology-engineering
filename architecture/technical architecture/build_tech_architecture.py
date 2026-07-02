"""Generate the technical-architecture artifacts into ./artifacts/.

Run:  python "architecture/technical architecture/build_tech_architecture.py"
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_ARCH = os.path.dirname(HERE)
_ROOT = os.path.dirname(_ARCH)
for p in (_ROOT, _ARCH, HERE):           # repo root, architecture/, this dir
    if p not in sys.path:
        sys.path.insert(0, p)

import tech_architecture_model as M       # noqa: E402
import tech_arch_generators as G          # noqa: E402

ART = os.path.join(HERE, "artifacts")


def main() -> None:
    os.makedirs(ART, exist_ok=True)
    probs = M.validate_model()
    if probs:
        raise SystemExit(f"model invalid: {probs}")
    print(f"model OK: {len(M.REQUIREMENTS)} requirements, {len(M.TECH_SERVICES)} services, "
          f"{len(M.TECH_NODES)} nodes")

    def write(name, text):
        p = os.path.join(ART, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"  wrote {os.path.relpath(p, HERE)} ({len(text):,} bytes)")

    os.makedirs(os.path.join(HERE, "mapping"), exist_ok=True)
    write(os.path.join("..", "REQUIREMENTS_CATALOG.md"), G.to_requirements_catalog_md())
    write(os.path.join("..", "TRACEABILITY.md"), G.to_traceability_md())
    write(os.path.join("..", "mapping", "MAPPING_FALKORDB_GCP.md"), G.to_mapping_md(
        [M.PG], M.T_FALKOR, "Mapping — Property-Graph requirements → FalkorDB on GCP",
        "How **FalkorDB**, deployed on **GKE/GCP**, satisfies each technology-agnostic "
        "*Property Graph Platform* requirement. See also the design narrative in `falkordb-gke.md`."))
    write(os.path.join("..", "mapping", "MAPPING_FUSEKI_GCP.md"), G.to_mapping_md(
        [M.SK], M.T_FUSEKI, "Mapping — Semantic-Knowledge-Graph requirements → Fuseki on GCP",
        "How **Apache Jena Fuseki**, deployed on **GKE/GCP**, satisfies each technology-agnostic "
        "*Semantic Knowledge Graph Platform* requirement. See also the design narrative in `fuseki-gke.md`."))
    write(os.path.join("..", "mapping", "MAPPING_PLATFORM_GCP.md"), G.to_mapping_md(
        [M.CN, M.SP], M.T_GCP, "Mapping — Cloud-Native & Platform-Services requirements → GCP",
        "How **GCP/GKE** services satisfy the shared, store-agnostic platform requirements that "
        "**both** FalkorDB and Fuseki depend on. See also `supporting-components.md`."))
    write("technology_architecture.svg", G.to_archimate_svg())
    png = G.draw_archimate_png(os.path.join(ART, "technology_architecture.png"))
    print(f"  wrote {os.path.relpath(png, HERE)}")
    print("done.")


if __name__ == "__main__":
    main()
