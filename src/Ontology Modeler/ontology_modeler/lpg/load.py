"""Loading strategy: ingest the IR into FalkorDB with parameterised Cypher (spec Section 4).

MERGE throughout for idempotency (4.1-4.3): re-running updates in place instead of
duplicating. UNWIND-batched. Object-property edges need a dynamic relationship type,
which Cypher cannot parameterise -- so the type token is sanitised at extraction
(rel_type_of) and re-validated here before it is injected into the query string, while
every value stays a bound parameter.
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
    c.alt_labels = row.alt_labels
"""

MERGE_TAXONOMY = """
UNWIND $batch AS row
MATCH (sub:Class {iri: row.sub_iri})
MATCH (sup:Class {iri: row.super_iri})
MERGE (sub)-[:SUBCLASS_OF]->(sup)
"""

# {rel} is the validated type token; row values are bound parameters.
MERGE_RELATIONS = """
UNWIND $batch AS row
MATCH (dom:Class {{iri: row.domain_iri}})
MATCH (ran:Class {{iri: row.range_iri}})
MERGE (dom)-[r:{rel}]->(ran)
SET r.iri = row.prop_iri,
    r.name = row.prop_name,
    r.definition = row.prop_definition
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
             "definition": d.get("definition"), "alt_labels": d.get("alt_labels", [])}
            for n, d in g.nodes(data=True) if d.get("label") == "Class"
        ]
        for chunk in _chunks(rows, batch_size):
            self.graph.query(MERGE_CLASSES, {"batch": chunk})
        return len(rows)

    def load_taxonomy(self, g: nx.MultiDiGraph, batch_size: int = 1000) -> int:
        rows = [{"sub_iri": u, "super_iri": v}
                for u, v, k in g.edges(keys=True) if k == "SUBCLASS_OF"]
        for chunk in _chunks(rows, batch_size):
            self.graph.query(MERGE_TAXONOMY, {"batch": chunk})
        return len(rows)

    def load_object_properties(self, g: nx.MultiDiGraph, batch_size: int = 500) -> int:
        by_type: dict[str, list[dict]] = defaultdict(list)
        for u, v, k, d in g.edges(keys=True, data=True):
            if k == "SUBCLASS_OF":
                continue
            rel = d.get("type", "")
            if not _SAFE_REL.match(rel):
                raise ValueError(f"unsafe relationship type refused: {rel!r}")
            by_type[rel].append({
                "domain_iri": u, "range_iri": v, "prop_iri": d.get("iri"),
                "prop_name": d.get("name"), "prop_definition": d.get("definition"),
            })
        total = 0
        for rel, rows in by_type.items():
            query = MERGE_RELATIONS.format(rel=rel)
            for chunk in _chunks(rows, batch_size):
                self.graph.query(query, {"batch": chunk})
            total += len(rows)
        return total

    def load_embeddings(self, embeddings: dict[str, list[float]], batch_size: int = 500) -> int:
        rows = [{"iri": iri, "embedding": vec} for iri, vec in embeddings.items()]
        for chunk in _chunks(rows, batch_size):
            self.graph.query(SET_EMBEDDING, {"batch": chunk})
        return len(rows)

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

    def knn(self, query_vector: list[float], k: int = 5) -> list[tuple[str, float]]:
        """K nearest :Class nodes to a query vector, via the vector index. (name, score)."""
        rows = self.graph.query(
            "CALL db.idx.vector.queryNodes('Class','embedding',$k,vecf32($q)) "
            "YIELD node, score RETURN node.name AS name, score",
            {"k": k, "q": query_vector},
        )
        return [(r[0], r[1]) for r in rows.result_set]

    # -- verification -------------------------------------------------------- #

    def count_nodes(self) -> int:
        return self.graph.query("MATCH (c:Class) RETURN count(c) AS n").result_set[0][0]

    def count_edges(self, rel_type: str | None = None) -> int:
        # count(r), not count(*): FalkorDB under-counts count(*) on an all-anonymous
        # MATCH ()-[r]->() pattern; count(r) returns the true relationship total.
        pattern = f"[r:{rel_type}]" if rel_type else "[r]"
        return self.graph.query(f"MATCH ()-{pattern}->() RETURN count(r) AS n").result_set[0][0]


def _chunks(seq: list, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]
