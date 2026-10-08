"""
Ontology -> Labeled Property Graph (LPG) converter
==================================================
A modular ETL pipeline that converts general RDF foundational ontologies into a
schema-level Meta-Graph in FalkorDB.

Pipeline (Strategy Pattern -- Extract / Transform / Load):

    RecursiveOntologyLoader   (E)  parse an ontology + recursively its owl:imports
                                   into one rdflib.Graph; register (:Ontology)
                                   nodes and [:IMPORTS] edges in a NetworkX IR.
    UniversalOntologyConverter (T) walk the unified rdflib.Graph and populate the
                                   same networkx.MultiDiGraph with schema nodes
                                   (:OWLClass/:ObjectProperty/...) and edges
                                   (:SUBCLASS_OF/:HAS_DOMAIN/:DEFINED_IN/...).
    FalkorDBExporter          (L)  idempotently MERGE the IR into FalkorDB using
                                   parameterised, UNWIND-batched Cypher.

MVP scope (per spec): schema only -- no business-data instances, and OWL
restrictions (blank nodes) are ignored entirely.

Requires: rdflib, networkx  (falkordb only needed for live loading; the exporter
falls back to a dry-run that logs the Cypher when it is unavailable).
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional

import networkx as nx
import rdflib
from rdflib import BNode, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

log = logging.getLogger("ontology_to_lpg")

# ---------------------------------------------------------------------------
# Shared vocabulary: how RDF types/predicates map onto LPG labels/edge types.
# ---------------------------------------------------------------------------
TYPE_TO_LABEL = {
    OWL.Class: "OWLClass",
    RDFS.Class: "OWLClass",          # lenient: many ontologies use rdfs:Class
    OWL.ObjectProperty: "ObjectProperty",
    OWL.DatatypeProperty: "DatatypeProperty",
    OWL.AnnotationProperty: "AnnotationProperty",
}

# predicate -> (edge type, reverse?)  ; all are (subject)->(object)
EDGE_RULES = {
    RDFS.subClassOf: "SUBCLASS_OF",
    RDFS.subPropertyOf: "SUBPROPERTY_OF",
    RDFS.domain: "HAS_DOMAIN",       # (Property)->(Class)
    RDFS.range: "HAS_RANGE",         # (Property)->(Class)
}

RESERVED_NODE_KEYS = {"labels"}      # NetworkX attrs that are not Cypher props
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def cypher_safe_key(key: str) -> str:
    """Make a property key safe for Cypher (e.g. 'skos:definition' -> 'skos_definition')."""
    safe = re.sub(r"[^0-9A-Za-z_]", "_", key)
    if safe and safe[0].isdigit():
        safe = "_" + safe
    return safe or "_"


def assert_ident(value: str) -> str:
    """Guard label / relationship-type names (which cannot be parameterised in Cypher)."""
    if not _IDENT_RE.fullmatch(value):
        raise ValueError(f"Unsafe Cypher identifier: {value!r}")
    return value


def build_local_catalog(root_dir: str,
                        exts: Iterable[str] = (".rdf", ".owl", ".ttl")) -> dict[str, str]:
    """Scan a local ontology tree and map each ontology IRI -> local file path.

    Pass the result as ``RecursiveOntologyLoader(uri_to_location=...)`` to resolve
    ``owl:imports`` against local files (offline loading of e.g. a FIBO clone).
    Parsing every file can be slow for large trees, so build this once and reuse it.
    """
    catalog: dict[str, str] = {}
    exts = {e.lower() for e in exts}
    for path in Path(root_dir).rglob("*"):
        if path.suffix.lower() not in exts:
            continue
        g = rdflib.Graph()
        try:
            g.parse(location=str(path))
        except Exception:  # noqa: BLE001 - skip anything that won't parse
            continue
        for ont in g.subjects(RDF.type, OWL.Ontology):
            catalog[str(ont)] = str(path)
    return catalog


# ===========================================================================
# 1. EXTRACTION
# ===========================================================================
class RecursiveOntologyLoader:
    """Recursively load an ontology and its ``owl:imports`` closure.

    Maintains a single shared ``rdflib.Graph`` (all triples merged) and a
    ``networkx.MultiDiGraph`` IR seeded with (:Ontology) nodes + [:IMPORTS] edges.
    """

    def __init__(self, uri_to_location: Optional[dict[str, str]] = None,
                 follow_imports: bool = True):
        self.rdf = rdflib.Graph()
        self.ir = nx.MultiDiGraph()
        self._parsed_locations: set[str] = set()
        self._registered_onts: set[str] = set()
        # Redirect import URIs to local files (offline use / caching).
        self.uri_to_location = dict(uri_to_location or {})
        # When False, load only the given document(s) -- do not fetch owl:imports.
        # Useful for visualising a single ontology module's own schema.
        self.follow_imports = follow_imports

    # -- public ------------------------------------------------------------
    def load(self, source: str) -> tuple[rdflib.Graph, nx.MultiDiGraph]:
        """Load ``source`` (local path or URI) and its import closure."""
        self._load_recursive(source, parent_ontology=None)
        log.info("Extraction complete: %d triples across %d ontology module(s).",
                 len(self.rdf), len(self._registered_onts))
        return self.rdf, self.ir

    # -- internals ---------------------------------------------------------
    def _resolve(self, ref: str) -> str:
        return self.uri_to_location.get(str(ref), str(ref))

    def _parse(self, location: str) -> Optional[rdflib.Graph]:
        """Parse a single document into a fresh graph, trying common formats."""
        sub = rdflib.Graph()
        last_err: Optional[Exception] = None
        # Let rdflib guess first, then fall back to explicit serialisations.
        for fmt in (None, "xml", "turtle", "n3", "nt", "json-ld"):
            try:
                if Path(location).exists():
                    sub.parse(location=location, format=fmt)
                else:
                    sub.parse(location, format=fmt)   # remote fetch
                return sub
            except Exception as exc:                  # noqa: BLE001 - try next fmt
                last_err = exc
        log.warning("Could not parse %s (%s); skipping.", location, last_err)
        return None

    def _register_ontology(self, ont_uri: str, label: Optional[str]) -> None:
        if ont_uri not in self.ir:
            self.ir.add_node(ont_uri, labels={"Ontology"}, uri=ont_uri,
                             qname=self._qname(URIRef(ont_uri)))
        else:
            self.ir.nodes[ont_uri].setdefault("labels", set()).add("Ontology")
        if label:
            self.ir.nodes[ont_uri]["rdfs_label"] = label
        self._registered_onts.add(ont_uri)

    def _qname(self, uri: URIRef) -> str:
        try:
            return self.rdf.namespace_manager.normalizeUri(uri).strip("<>")
        except Exception:  # noqa: BLE001
            return str(uri)

    def _load_recursive(self, ref: str, parent_ontology: Optional[str]) -> None:
        location = self._resolve(ref)

        if location in self._parsed_locations:
            # Already parsed; still make sure the IMPORTS edge exists.
            if parent_ontology and str(ref) in self.ir:
                self.ir.add_edge(parent_ontology, str(ref), key="IMPORTS", type="IMPORTS")
            return
        self._parsed_locations.add(location)

        sub = self._parse(location)
        if sub is None:
            return
        log.info("Recursively fetched: %s", ref)

        # Merge triples into the shared graph, and carry over the document's
        # namespace bindings (``+=`` copies triples only) so the converter can
        # render readable QNames such as ``fibo-fnd:Organization``.
        self.rdf += sub
        for prefix, namespace in sub.namespaces():
            self.rdf.namespace_manager.bind(prefix, namespace, override=False)

        # Determine the ontology's declared IRI (fall back to the ref).
        ont_iri = next(sub.subjects(RDF.type, OWL.Ontology), None)
        ont_uri = str(ont_iri) if ont_iri is not None else str(ref)
        label = None
        if ont_iri is not None:
            lbl = sub.value(ont_iri, RDFS.label)
            label = str(lbl) if lbl is not None else None

        self._register_ontology(ont_uri, label)
        if parent_ontology:
            self.ir.add_edge(parent_ontology, ont_uri, key="IMPORTS", type="IMPORTS")

        # Recurse into imports declared by this document (unless disabled).
        if not self.follow_imports:
            return
        imports = list(sub.objects(ont_iri, OWL.imports)) if ont_iri is not None else []
        for imp in imports:
            self._load_recursive(str(imp), parent_ontology=ont_uri)


# ===========================================================================
# 2. TRANSFORMATION
# ===========================================================================
class UniversalOntologyConverter:
    """Populate the NetworkX IR with schema nodes and edges from the RDF graph."""

    def __init__(self, rdf_graph: rdflib.Graph, ir: nx.MultiDiGraph):
        self.rdf = rdf_graph
        self.ir = ir
        self.nsm = rdf_graph.namespace_manager

    # -- helpers -----------------------------------------------------------
    def _qname(self, uri: URIRef) -> str:
        try:
            return self.nsm.normalizeUri(uri).strip("<>")
        except Exception:  # noqa: BLE001
            return str(uri)

    def _ensure_node(self, uri: URIRef, label: Optional[str] = None) -> str:
        key = str(uri)
        if key not in self.ir:
            self.ir.add_node(key, labels=set(), uri=key, qname=self._qname(uri))
        node = self.ir.nodes[key]
        node.setdefault("labels", set())
        node.setdefault("uri", key)
        node.setdefault("qname", self._qname(uri))
        if label:
            node["labels"].add(label)
        return key

    # -- pipeline steps ----------------------------------------------------
    def convert(self) -> nx.MultiDiGraph:
        self._map_typed_nodes()
        self._attach_literal_properties()
        self._map_topology_edges()
        self._map_lineage_edges()
        n_schema = sum(1 for _, d in self.ir.nodes(data=True)
                       if d.get("labels") and d["labels"] != {"Ontology"})
        log.info("Transformation complete: parsed %d schema node(s), %d IR edge(s).",
                 n_schema, self.ir.number_of_edges())
        return self.ir

    def _map_typed_nodes(self) -> None:
        """A. Core node mapping: rdf:type -> LPG label. BNodes ignored."""
        count = 0
        for rdf_type, label in TYPE_TO_LABEL.items():
            for subj in self.rdf.subjects(RDF.type, rdf_type):
                if isinstance(subj, BNode):
                    continue
                self._ensure_node(subj, label)
                count += 1
        log.info("Mapped %d typed schema node(s).", count)

    def _attach_literal_properties(self) -> None:
        """B. Attach all Literal values on schema nodes as Cypher-safe string props."""
        accumulated: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for node_key in list(self.ir.nodes):
            subj = URIRef(node_key)
            for pred, obj in self.rdf.predicate_objects(subj):
                if isinstance(obj, Literal):
                    key = cypher_safe_key(self._qname(pred))
                    accumulated[node_key][key].add(str(obj))
        for node_key, props in accumulated.items():
            for key, values in props.items():
                # Store as a single string; join multiples deterministically.
                self.ir.nodes[node_key][key] = " | ".join(sorted(values))

    def _map_topology_edges(self) -> None:
        """C. Schema topology edges (subClassOf/subPropertyOf/domain/range)."""
        for pred, edge_type in EDGE_RULES.items():
            for subj, obj in self.rdf.subject_objects(pred):
                if isinstance(subj, BNode) or isinstance(obj, BNode):
                    continue   # ignore complex OWL restrictions
                s = self._ensure_node(subj)
                t = self._ensure_node(obj)
                self._add_edge(s, t, edge_type)

    def _map_lineage_edges(self) -> None:
        """D. Lineage: rdfs:isDefinedBy -> (:SchemaNode)-[:DEFINED_IN]->(:Ontology)."""
        for subj, obj in self.rdf.subject_objects(RDFS.isDefinedBy):
            if isinstance(subj, BNode) or isinstance(obj, BNode):
                continue
            s = self._ensure_node(subj)
            t = str(obj)
            if t not in self.ir:                      # ensure the ontology node exists
                self.ir.add_node(t, labels={"Ontology"}, uri=t, qname=self._qname(obj))
            else:
                self.ir.nodes[t].setdefault("labels", set()).add("Ontology")
            self._add_edge(s, t, "DEFINED_IN")

    def _add_edge(self, src: str, tgt: str, edge_type: str) -> None:
        # MultiDiGraph keyed by edge type -> idempotent within the IR.
        if not self.ir.has_edge(src, tgt, key=edge_type):
            self.ir.add_edge(src, tgt, key=edge_type, type=edge_type)


# ===========================================================================
# 3. LOADING
# ===========================================================================
class FalkorDBExporter:
    """Idempotently ingest the NetworkX IR into FalkorDB via batched Cypher."""

    def __init__(self, ir: nx.MultiDiGraph, graph_name: str = "ontology_meta",
                 host: str = "localhost", port: int = 6379,
                 batch_size: int = 500, dry_run: bool = False):
        self.ir = ir
        self.graph_name = graph_name
        self.batch_size = batch_size
        self.dry_run = dry_run
        self.graph = None
        if not self.dry_run:
            self._connect(host, port)

    def _connect(self, host: str, port: int) -> None:
        try:
            from falkordb import FalkorDB
        except ImportError:
            log.warning("falkordb client not installed -> switching to DRY-RUN "
                        "(Cypher will be logged, not executed).")
            self.dry_run = True
            return
        try:
            db = FalkorDB(host=host, port=port)
            self.graph = db.select_graph(self.graph_name)
            self.graph.query("RETURN 1")   # connectivity probe
            log.info("Connected to FalkorDB graph '%s' at %s:%s.",
                     self.graph_name, host, port)
        except Exception as exc:  # noqa: BLE001
            log.warning("Cannot reach FalkorDB (%s) -> switching to DRY-RUN.", exc)
            self.dry_run = True

    # -- execution ---------------------------------------------------------
    def _run(self, cypher: str, params: dict) -> None:
        if self.dry_run:
            log.info("[DRY-RUN] %s  |  rows=%d", cypher, len(params.get("rows", [])))
            return
        self.graph.query(cypher, params)

    def _run_batched(self, cypher: str, rows: list[dict]) -> None:
        for i in range(0, len(rows), self.batch_size):
            self._run(cypher, {"rows": rows[i:i + self.batch_size]})

    def export(self) -> None:
        log.info("Loading IR into FalkorDB%s...", " (DRY-RUN)" if self.dry_run else "")
        self.export_nodes()
        self.export_edges()
        log.info("Load complete: %d node(s), %d edge(s).",
                 self.ir.number_of_nodes(), self.ir.number_of_edges())

    def export_nodes(self) -> None:
        # Group by label-set so each UNWIND batch shares a MERGE signature.
        groups: dict[tuple[str, ...], list[dict]] = defaultdict(list)
        for uri, data in self.ir.nodes(data=True):
            labels = tuple(sorted(data.get("labels") or {"Resource"}))
            props = {k: v for k, v in data.items() if k not in RESERVED_NODE_KEYS}
            props.setdefault("uri", uri)
            groups[labels].append({"uri": uri, "props": props})

        for labels, rows in groups.items():
            label_str = ":".join(assert_ident(l) for l in labels)
            cypher = (f"UNWIND $rows AS row "
                      f"MERGE (n:{label_str} {{uri: row.uri}}) "
                      f"SET n += row.props")
            log.info("Ingesting %d (:%s) node(s).", len(rows), label_str)
            self._run_batched(cypher, rows)

    def export_edges(self) -> None:
        groups: dict[str, list[dict]] = defaultdict(list)
        for src, tgt, key, data in self.ir.edges(keys=True, data=True):
            groups[data.get("type", key)].append({"src": src, "tgt": tgt})

        for edge_type, rows in groups.items():
            rel = assert_ident(edge_type)
            cypher = (f"UNWIND $rows AS row "
                      f"MATCH (src {{uri: row.src}}), (tgt {{uri: row.tgt}}) "
                      f"MERGE (src)-[:{rel}]->(tgt)")
            log.info("Ingesting %d [:%s] edge(s).", len(rows), rel)
            self._run_batched(cypher, rows)


# ===========================================================================
# Execution block: wire Loader -> Converter -> Exporter
# ===========================================================================
def build_pipeline(root_source: str,
                   uri_to_location: Optional[dict[str, str]] = None,
                   graph_name: str = "ontology_meta",
                   dry_run: bool = False) -> nx.MultiDiGraph:
    loader = RecursiveOntologyLoader(uri_to_location=uri_to_location)
    rdf_graph, ir = loader.load(root_source)

    converter = UniversalOntologyConverter(rdf_graph, ir)
    ir = converter.convert()

    exporter = FalkorDBExporter(ir, graph_name=graph_name, dry_run=dry_run)
    exporter.export()
    return ir


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    here = Path(__file__).resolve().parent
    root_ontology = here / "sample" / "root_ontology.rdf"

    # Redirect the import IRI to the bundled local file so the demo runs offline.
    # For real ontologies (e.g. FIBO) drop this map and let rdflib fetch imports.
    resolver = {
        "http://example.org/foundational": str(here / "sample" / "imported_ontology.rdf"),
    }

    log.info("=== Ontology -> LPG Meta-Graph conversion ===")
    ir = build_pipeline(
        root_source=str(root_ontology),
        uri_to_location=resolver,
        graph_name="ontology_meta",
        dry_run=False,   # auto-falls back to dry-run if FalkorDB is unavailable
    )

    # Compact IR summary for quick inspection.
    label_counts: dict[str, int] = defaultdict(int)
    for _, data in ir.nodes(data=True):
        for lbl in (data.get("labels") or {"Resource"}):
            label_counts[lbl] += 1
    edge_counts: dict[str, int] = defaultdict(int)
    for _, _, data in ir.edges(data=True):
        edge_counts[data.get("type", "?")] += 1

    log.info("IR node labels: %s", dict(sorted(label_counts.items())))
    log.info("IR edge types : %s", dict(sorted(edge_counts.items())))
