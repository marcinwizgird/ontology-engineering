"""Loading strategy: ingest the IR into FalkorDB with parameterised Cypher (spec Section 4).

MERGE throughout for idempotency (4.1-4.3): re-running updates in place instead of
duplicating. UNWIND-batched. Object-property and restriction edges need a dynamic
relationship type, which Cypher cannot parameterise -- so the type token is sanitised at
extraction (rel_type_of) and re-validated here before it is injected into the query
string, while every value stays a bound parameter.

Edges are dispatched on the IR's `kind` attribute (taxonomy / object_property /
restriction / defined_in) rather than on the absence of a key, so a new edge kind added
upstream cannot silently fall into the object-property loader.
"""

from __future__ import annotations

import re
from collections import defaultdict

import networkx as nx

from ..config import FalkorSettings

# A relationship type we interpolate into Cypher must be exactly this shape.
_SAFE_REL = re.compile(r"^[A-Z][A-Z0-9_]*$")

MERGE_CLASSES = """
UNWIND $batch AS row
MERGE (c:Class {iri: row.iri})
SET c.short_name = row.short_name,
    c.name = row.name,
    c.definition = row.definition,
    c.alt_labels = row.alt_labels,
    c.alt_text = row.alt_text,
    c.external = row.external,
    c.module_iri = row.module_iri
"""

MERGE_MODULES = """
UNWIND $batch AS row
MERGE (m:Module {iri: row.iri})
SET m.name = row.name,
    m.path = row.path,
    m.abstract = row.abstract
"""

MERGE_TAXONOMY = """
UNWIND $batch AS row
MATCH (sub:Class {iri: row.sub_iri})
MATCH (sup:Class {iri: row.super_iri})
MERGE (sub)-[:SUBCLASS_OF]->(sup)
"""

MERGE_DEFINED_IN = """
UNWIND $batch AS row
MATCH (c:Class {iri: row.class_iri})
MATCH (m:Module {iri: row.module_iri})
MERGE (c)-[:DEFINED_IN]->(m)
"""

# {rel} is the validated type token; row values are bound parameters.
#
# `via` is part of the MERGE pattern, not something SET afterwards. Without it this
# pattern matches ANY edge of this type between the same two classes -- including the
# restriction edge the same property produced -- and rewrites it as a domain/range edge.
# The restriction loader then finds nothing with via='restriction' and creates a fresh
# one, so every re-projection adds edges instead of updating them. Idempotence is the
# whole point of MERGE, and this is how it was being lost.
MERGE_RELATIONS = """
UNWIND $batch AS row
MATCH (dom:Class {{iri: row.domain_iri}})
MATCH (ran:Class {{iri: row.range_iri}})
MERGE (dom)-[r:{rel} {{via: 'domain_range'}}]->(ran)
SET r.iri = row.prop_iri,
    r.name = row.prop_name,
    r.definition = row.prop_definition
"""

# The quantifier is part of the MERGE pattern: `hasPart some Wheel` and `hasPart only
# Wheel` are different axioms and must not collapse into one edge.
MERGE_RESTRICTIONS = """
UNWIND $batch AS row
MATCH (src:Class {{iri: row.source_iri}})
MATCH (tgt:Class {{iri: row.target_iri}})
MERGE (src)-[r:{rel} {{via: 'restriction', quantifier: row.quantifier}}]->(tgt)
SET r.iri = row.prop_iri,
    r.name = row.prop_name,
    r.cardinality = row.cardinality,
    r.origin = row.origin
"""

# vecf32(): store as FalkorDB's native vector type so the vector index can see it. A plain
# float array is stored but invisible to db.idx.vector.queryNodes.
SET_EMBEDDING = """
UNWIND $batch AS row
MATCH (c:Class {iri: row.iri})
SET c.embedding = vecf32(row.embedding)
"""


class FalkorDBExporter:
    """Writes a MetaGraphBuilder's MultiDiGraph into a FalkorDB graph."""

    def __init__(self, settings: FalkorSettings | None = None):
        from falkordb import FalkorDB
        self.settings = settings or FalkorSettings.from_env()
        self._db = FalkorDB(host=self.settings.host, port=self.settings.port,
                            password=self.settings.password or None)
        self.graph = self._db.select_graph(self.settings.graph_name)

    def ping(self) -> None:
        self._db.connection.ping()

    def clear(self) -> None:
        """Drop the whole graph (a full reload starts clean)."""
        try:
            self.graph.delete()
        except Exception:
            pass   # a graph that does not exist yet cannot be deleted
        self.graph = self._db.select_graph(self.settings.graph_name)

    # -- ingestion ----------------------------------------------------------- #

    def load_classes(self, g: nx.MultiDiGraph, batch_size: int = 1000) -> int:
        rows = [
            {"iri": n, "short_name": d.get("short_name"), "name": d.get("name"),
             "definition": d.get("definition"), "alt_labels": d.get("alt_labels", []),
             # A joined copy, because a full-text index cannot be built over an array.
             "alt_text": " ".join(d.get("alt_labels", [])),
             "external": bool(d.get("external", False)),
             "module_iri": d.get("module_iri")}
            for n, d in g.nodes(data=True) if d.get("label") == "Class"
        ]
        for chunk in _chunks(rows, batch_size):
            self.graph.query(MERGE_CLASSES, {"batch": chunk})
        return len(rows)

    def load_modules(self, g: nx.MultiDiGraph, batch_size: int = 1000) -> int:
        rows = [
            {"iri": n, "name": d.get("name"), "path": d.get("path"),
             "abstract": d.get("abstract") or ""}
            for n, d in g.nodes(data=True) if d.get("label") == "Module"
        ]
        for chunk in _chunks(rows, batch_size):
            self.graph.query(MERGE_MODULES, {"batch": chunk})
        return len(rows)

    def load_taxonomy(self, g: nx.MultiDiGraph, batch_size: int = 1000) -> int:
        rows = [{"sub_iri": u, "super_iri": v}
                for u, v, d in g.edges(data=True) if d.get("kind") == "taxonomy"]
        for chunk in _chunks(rows, batch_size):
            self.graph.query(MERGE_TAXONOMY, {"batch": chunk})
        return len(rows)

    def load_defined_in(self, g: nx.MultiDiGraph, batch_size: int = 1000) -> int:
        rows = [{"class_iri": u, "module_iri": v}
                for u, v, d in g.edges(data=True) if d.get("kind") == "defined_in"]
        for chunk in _chunks(rows, batch_size):
            self.graph.query(MERGE_DEFINED_IN, {"batch": chunk})
        return len(rows)

    def load_object_properties(self, g: nx.MultiDiGraph, batch_size: int = 500) -> int:
        by_type: dict[str, list[dict]] = defaultdict(list)
        for u, v, d in g.edges(data=True):
            if d.get("kind", "object_property") != "object_property":
                continue
            rel = _validated(d.get("type", ""))
            by_type[rel].append({
                "domain_iri": u, "range_iri": v, "prop_iri": d.get("iri"),
                "prop_name": d.get("name"), "prop_definition": d.get("definition"),
            })
        return self._load_by_type(MERGE_RELATIONS, by_type, batch_size)

    def load_restrictions(self, g: nx.MultiDiGraph, batch_size: int = 500) -> int:
        by_type: dict[str, list[dict]] = defaultdict(list)
        for u, v, d in g.edges(data=True):
            if d.get("kind") != "restriction":
                continue
            rel = _validated(d.get("type", ""))
            by_type[rel].append({
                "source_iri": u, "target_iri": v, "prop_iri": d.get("iri"),
                "prop_name": d.get("name"), "quantifier": d.get("quantifier"),
                "cardinality": d.get("cardinality"), "origin": d.get("origin"),
            })
        return self._load_by_type(MERGE_RESTRICTIONS, by_type, batch_size)

    def _load_by_type(self, template: str, by_type: dict[str, list[dict]],
                      batch_size: int) -> int:
        total = 0
        for rel, rows in by_type.items():
            query = template.format(rel=rel)
            for chunk in _chunks(rows, batch_size):
                self.graph.query(query, {"batch": chunk})
            total += len(rows)
        return total

    def load_embeddings(self, embeddings: dict[str, list[float]], batch_size: int = 500) -> int:
        rows = [{"iri": iri, "embedding": vec} for iri, vec in embeddings.items()]
        for chunk in _chunks(rows, batch_size):
            self.graph.query(SET_EMBEDDING, {"batch": chunk})
        return len(rows)

    # -- indexes ------------------------------------------------------------- #

    def create_vector_index(self, dim: int, similarity: str = "cosine") -> bool:
        """Register a vector index on :Class(embedding) (spec 5.3). False if one exists."""
        try:
            self.graph.query(
                f"CREATE VECTOR INDEX FOR (c:Class) ON (c.embedding) "
                f"OPTIONS {{dimension:{int(dim)}, similarityFunction:'{similarity}'}}"
            )
            return True
        except Exception:
            return False   # index already present, or DDL form unsupported

    def create_fulltext_index(self, fields: tuple[str, ...] = ("name", "definition", "alt_text")) -> bool:
        """Full-text index on :Class, for the lexical half of hybrid anchoring.

        Vector search alone misses exact identifiers -- an analyst asking for 'LEI' or
        'ISDA Master Agreement' wants the term, not its nearest neighbour in embedding
        space. The retriever runs both and fuses the rankings.
        """
        try:
            args = ", ".join(f"'{f}'" for f in fields)
            self.graph.query(f"CALL db.idx.fulltext.createNodeIndex('Class', {args})")
            return True
        except Exception:
            return False

    def create_lookup_indexes(self) -> int:
        """Exact indexes on the IRI keys every MERGE and MATCH goes through."""
        created = 0
        for label in ("Class", "Module"):
            try:
                self.graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.iri)")
                created += 1
            except Exception:
                pass
        return created

    # -- query --------------------------------------------------------------- #

    def knn(self, query_vector: list[float], k: int = 5,
            include_external: bool = False) -> list[tuple[str, str, float]]:
        """K nearest :Class nodes to a query vector. Returns (iri, name, score).

        External stubs are excluded by default: they have an IRI and nothing else, so they
        can win on an empty profile and crowd out real answers.
        """
        # Over-fetch, then filter, so the post-filter cannot empty the result set.
        fetch = k * 4 if not include_external else k
        rows = self.graph.query(
            "CALL db.idx.vector.queryNodes('Class','embedding',$k,vecf32($q)) "
            "YIELD node, score RETURN node.iri AS iri, node.name AS name, "
            "node.external AS external, score ORDER BY score",
            {"k": fetch, "q": query_vector},
        )
        out = []
        for iri, name, external, score in rows.result_set:
            if external and not include_external:
                continue
            out.append((iri, name, float(score)))
            if len(out) >= k:
                break
        return out

    def search_text(self, query: str, k: int = 5) -> list[tuple[str, str, float]]:
        """Full-text search over :Class. Returns (iri, name, score), best first."""
        try:
            rows = self.graph.query(
                "CALL db.idx.fulltext.queryNodes('Class', $q) YIELD node, score "
                "WHERE node.external = false "
                "RETURN node.iri AS iri, node.name AS name, score "
                "ORDER BY score DESC LIMIT $k",
                {"q": query, "k": k},
            )
        except Exception:
            return []
        return [(r[0], r[1], float(r[2])) for r in rows.result_set]

    # -- verification -------------------------------------------------------- #

    def count_nodes(self, label: str = "Class") -> int:
        return self.graph.query(f"MATCH (c:{label}) RETURN count(c) AS n").result_set[0][0]

    def count_edges(self, rel_type: str | None = None) -> int:
        # count(r), not count(*): FalkorDB under-counts count(*) on an all-anonymous
        # MATCH ()-[r]->() pattern; count(r) returns the true relationship total.
        pattern = f"[r:{rel_type}]" if rel_type else "[r]"
        return self.graph.query(f"MATCH ()-{pattern}->() RETURN count(r) AS n").result_set[0][0]

    def relationship_types(self) -> list[str]:
        return [r[0] for r in self.graph.query("CALL db.relationshipTypes()").result_set]

    def edge_counts_by_type(self) -> dict[str, int]:
        """Edge count per relationship type, counted one type at a time.

        Not `MATCH ()-[r]->() RETURN type(r), count(r)`: projecting an ontology gives one
        relationship type per object property -- 906 of them for FIBO -- and the
        anonymous pattern makes FalkorDB union every one of those edge sets, which times
        out. A typed MATCH hits the per-type index, and 906 of them finish in ~2 seconds.
        """
        return {rt: self.count_edges(rt) for rt in self.relationship_types()}

    def stats(self) -> dict:
        counts = self.edge_counts_by_type()
        return {
            "classes": self.count_nodes("Class"),
            "modules": self.count_nodes("Module"),
            "edges": sum(counts.values()),
            "relationship_types": len(counts),
            "subclass_of": counts.get("SUBCLASS_OF", 0),
            "defined_in": counts.get("DEFINED_IN", 0),
        }


def _validated(rel: str) -> str:
    if not _SAFE_REL.match(rel):
        raise ValueError(f"unsafe relationship type refused: {rel!r}")
    return rel


def _chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]
