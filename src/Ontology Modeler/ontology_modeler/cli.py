"""Unified command-line interface for the Ontology Modeler.

    python -m ontology_modeler upload  [--clear] [--workers N] [PATH ...]
    python -m ontology_modeler upload  --async [--concurrency N] [PATH ...]
    python -m ontology_modeler lpg     [--clear] [--embed] [--embedder KIND] [--dry-run]
    python -m ontology_modeler ping

Connection settings come from infra/*/.env (see FusekiSettings/FalkorSettings).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from .config import REPO_ROOT, FusekiSettings, FalkorSettings
from .fuseki import FusekiClient
from .upload import Uploader, AsyncUploader
from .lpg import LpgConverter

log = logging.getLogger("ontology_modeler")


def _client(args) -> FusekiClient:
    return FusekiClient(FusekiSettings.from_env(base_url=getattr(args, "fuseki_base", None),
                                                dataset=getattr(args, "dataset", None)))


def _cmd_ping(args) -> int:
    try:
        print("Fuseki up:", _client(args).ping())
    except Exception as exc:
        print(f"Fuseki DOWN: {exc}", file=sys.stderr)
        return 1
    try:
        from .lpg import FalkorDBExporter
        FalkorDBExporter(FalkorSettings.from_env()).ping()
        print("FalkorDB up")
    except Exception as exc:
        print(f"FalkorDB DOWN: {exc}", file=sys.stderr)
    return 0


def _cmd_upload(args) -> int:
    paths = args.paths or [REPO_ROOT / "Ontology Repository"]
    if args.dry_run:
        from .rdf import iter_rdf_files, graph_uri
        files = iter_rdf_files([Path(p) for p in paths])
        total_mb = sum(f.stat().st_size for f in files) / 1_048_576
        print(f"Found {len(files)} RDF file(s), {total_mb:.1f} MB")
        for f in files:
            print(f"  {graph_uri(f)}")
        return 0

    client = _client(args)
    if not client.is_up():
        print(f"error: Fuseki not answering at {client.settings.base_url}\n"
              f"       start it: cd infra/fuseki && docker compose up -d", file=sys.stderr)
        return 1

    if args.use_async:
        result = asyncio.run(AsyncUploader(client).upload_paths(
            [Path(p) for p in paths], concurrency=args.concurrency, progress=True))
    else:
        result = Uploader(client).upload_paths(
            [Path(p) for p in paths], clear=args.clear, workers=args.workers, progress=True)

    print(f"\n{result}")
    if not args.use_async:
        print(f"dataset now holds {client.count_triples():,} triples")
    return 1 if result.failed else 0


def _cmd_lpg(args) -> int:
    conv = LpgConverter(_client(args),
                        FalkorSettings.from_env(graph_name=getattr(args, "graph_name", None)))
    ir = conv.extract_transform()
    print("IR:", ir)
    embeddings = conv.build_embeddings(args.embedder) if args.embed else None
    if args.dry_run:
        print("dry run: FalkorDB not touched")
        return 0
    print("Loaded:", conv.load(clear=args.clear, embeddings=embeddings))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ontology_modeler",
                                     description="Manage an ontology across Fuseki and FalkorDB.")
    parser.add_argument("--fuseki-base", default=None)
    parser.add_argument("--dataset", default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ping = sub.add_parser("ping", help="check both backends")
    p_ping.set_defaults(func=_cmd_ping)

    p_up = sub.add_parser("upload", help="upload RDF files into Fuseki")
    p_up.add_argument("paths", nargs="*", type=Path)
    p_up.add_argument("--clear", action="store_true", help="CLEAR ALL first (sync only)")
    p_up.add_argument("--workers", type=int, default=1, help="thread-pool size (sync)")
    p_up.add_argument("--async", dest="use_async", action="store_true", help="use the async uploader")
    p_up.add_argument("--concurrency", type=int, default=8, help="async in-flight PUTs")
    p_up.add_argument("--dry-run", action="store_true", help="list graph URIs; don't upload")
    p_up.set_defaults(func=_cmd_upload)

    p_lpg = sub.add_parser("lpg", help="convert the Fuseki TBox into a FalkorDB LPG")
    p_lpg.add_argument("--graph-name", default=None)
    p_lpg.add_argument("--clear", action="store_true", help="drop the FalkorDB graph first")
    p_lpg.add_argument("--embed", action="store_true", help="generate + load embeddings")
    p_lpg.add_argument("--embedder", default="hash", help="'hash' or 'sentence-transformers'")
    p_lpg.add_argument("--dry-run", action="store_true", help="IR only; don't touch FalkorDB")
    p_lpg.set_defaults(func=_cmd_lpg)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")
    logging.getLogger("ontology_modeler").setLevel(logging.INFO)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
