"""GraphRAG retrieval over the projected ontology.

The retrieval funnel, in the order the agent uses it:

    anchor()        hybrid vector + full-text lookup -> a few candidate classes
    resolve()       one term -> one IRI, for when the agent already knows the name
    concept_card()  everything asserted about one class, as a citable record
    neighbourhood() the class plus its immediate graph context
    path_between()  how two classes connect, if they do
    ancestors()     the subsumption chain up to the root
    run_cypher()    the escape hatch, read-only, for counting and filtering

Why hybrid anchoring. Vector search alone answers "what is a thing like this" and misses
exact identifiers -- an analyst asking about 'LEI' or 'ISDA Master Agreement' wants that
term, not its nearest neighbour in embedding space. Full-text alone answers "what
contains these words" and misses paraphrase. Reciprocal-rank fusion over both costs one
extra query and removes most of the anchor misses that otherwise make the agent
confabulate a plausible-sounding class that does not exist.

Every retrieval result carries the IRI it came from, so an answer can be checked against
the graph rather than taken on trust.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from ..config import FalkorSettings, embedder_path
from ..lpg.embed import load_embedder
from ..lpg.load import FalkorDBExporter

log = logging.getLogger("ontology_modeler.graphrag")

# Reciprocal-rank-fusion constant. 60 is the value from the original RRF paper; it damps
# the top of each list enough that one confident-but-wrong ranker cannot dominate.
RRF_K = 60

# Model-authored Cypher can ask for an unbounded scan; fail fast and explain instead.
CYPHER_TIMEOUT_MS = 15_000

# A read-only Cypher guard. The agent writes these queries, so the check is a whitelist of
# shape rather than a blacklist of words: anything that could mutate or administer the
# graph is refused before it reaches FalkorDB.
_FORBIDDEN = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|FOREACH)\b", re.IGNORECASE)
_FORBIDDEN_CALL = re.compile(r"\bCALL\s+(?!db\.idx\.(vector|fulltext)\.query)", re.IGNORECASE)


@dataclass
class Anchor:
    """A candidate entry point into the graph."""

    iri: str
    name: str
    score: float
    found_by: str                       # 'vector', 'fulltext', or 'both'


@dataclass
class ConceptCard:
    """Everything the graph asserts about one class, in citable form."""

    iri: str
    name: str
    short_name: str
    definition: str
    alt_labels: list[str] = field(default_factory=list)
    module: str | None = None
    superclasses: list[dict] = field(default_factory=list)
    subclasses: list[dict] = field(default_factory=list)
    relations_out: list[dict] = field(default_factory=list)
    relations_in: list[dict] = field(default_factory=list)

    def to_text(self) -> str:
        """The card as compact prose -- what goes into the model's context."""
        lines = [f"{self.name}  <{self.iri}>"]
        if self.definition and self.definition != "No definition available.":
            lines.append(f"Definition: {self.definition}")
        if self.alt_labels:
            lines.append(f"Also known as: {', '.join(self.alt_labels)}")
        if self.module:
            lines.append(f"Defined in module: {self.module}")
        if self.superclasses:
            lines.append("Superclasses: " + ", ".join(s["name"] for s in self.superclasses))
        if self.subclasses:
            shown = ", ".join(s["name"] for s in self.subclasses[:15])
            more = f" (+{len(self.subclasses) - 15} more)" if len(self.subclasses) > 15 else ""
            lines.append(f"Subclasses: {shown}{more}")
        for label, rels in (("Relations", self.relations_out),
                            ("Referenced by", self.relations_in)):
            if rels:
                phrases = [f"{r['property']} {r['quantifier']} {r['target']}" for r in rels[:15]]
                lines.append(f"{label}: " + "; ".join(phrases))
        return "\n".join(lines)


class GraphRagRetriever:
    """Read-only retrieval over a projected ontology in FalkorDB."""

    def __init__(self, settings: FalkorSettings | None = None, embedder=None):
        self.settings = settings or FalkorSettings.from_env()
        self.exporter = FalkorDBExporter(self.settings)
        self.graph = self.exporter.graph
        self._embedder = embedder
        self._embedder_loaded = embedder is not None
        self._schema_cache: dict | None = None

    @property
    def embedder(self):
        """The embedder fitted at projection time; loaded lazily, and optional.

        If it is missing the retriever still works -- anchoring falls back to full-text
        only -- because a broken vector path should degrade retrieval, not break the agent.
        """
        if not self._embedder_loaded:
            self._embedder_loaded = True
            try:
                self._embedder = load_embedder(embedder_path(self.settings.graph_name))
            except Exception as exc:
                log.warning("no fitted embedder for graph '%s' (%s); "
                            "anchoring will use full-text only",
                            self.settings.graph_name, type(exc).__name__)
                self._embedder = None
        return self._embedder

    # -- stage 1: anchoring --------------------------------------------------- #

    def anchor(self, query: str, k: int = 8) -> list[Anchor]:
        """Hybrid vector + full-text lookup, fused by reciprocal rank."""
        vector_hits: list[tuple[str, str, float]] = []
        if self.embedder is not None:
            try:
                vector_hits = self.exporter.knn(self.embedder.encode(query), k=k * 2)
            except Exception as exc:
                log.warning("vector search failed (%s); using full-text only", exc)
        text_hits = self.exporter.search_text(_sanitise_fulltext(query), k=k * 2)

        fused: dict[str, dict] = {}
        for source, hits in (("vector", vector_hits), ("fulltext", text_hits)):
            for rank, (iri, name, _score) in enumerate(hits):
                entry = fused.setdefault(iri, {"name": name, "score": 0.0, "sources": set()})
                entry["score"] += 1.0 / (RRF_K + rank + 1)
                entry["sources"].add(source)

        ordered = sorted(fused.items(), key=lambda kv: kv[1]["score"], reverse=True)
        return [
            Anchor(iri=iri, name=entry["name"], score=round(entry["score"], 6),
                   found_by="both" if len(entry["sources"]) == 2 else next(iter(entry["sources"])))
            for iri, entry in ordered[:k]
        ]

    def resolve(self, term: str) -> str | None:
        """One term -> one IRI. Exact IRI, then exact name, then the best anchor."""
        if term.startswith("http://") or term.startswith("https://"):
            rows = self.graph.query(
                "MATCH (c:Class {iri: $iri}) RETURN c.iri LIMIT 1", {"iri": term})
            if rows.result_set:
                return rows.result_set[0][0]

        rows = self.graph.query(
            "MATCH (c:Class) WHERE toLower(c.name) = toLower($t) OR "
            "toLower(c.short_name) = toLower($t) RETURN c.iri ORDER BY c.external LIMIT 1",
            {"t": term})
        if rows.result_set:
            return rows.result_set[0][0]

        anchors = self.anchor(term, k=1)
        return anchors[0].iri if anchors else None

    # -- stage 2: the citable record ------------------------------------------ #

    def concept_card(self, term: str) -> ConceptCard | None:
        iri = self.resolve(term)
        if iri is None:
            return None

        rows = self.graph.query(
            "MATCH (c:Class {iri: $iri}) "
            "OPTIONAL MATCH (c)-[:DEFINED_IN]->(m:Module) "
            "RETURN c.name, c.short_name, c.definition, c.alt_labels, m.name LIMIT 1",
            {"iri": iri})
        if not rows.result_set:
            return None
        name, short, definition, alts, module = rows.result_set[0]

        card = ConceptCard(
            iri=iri, name=name or short or iri, short_name=short or "",
            definition=definition or "", alt_labels=list(alts or []), module=module,
            superclasses=self._related(iri, "-[:SUBCLASS_OF]->"),
            subclasses=self._related(iri, "<-[:SUBCLASS_OF]-"),
            relations_out=self._property_edges(iri, outgoing=True),
            relations_in=self._property_edges(iri, outgoing=False),
        )
        return card

    def _related(self, iri: str, pattern: str, limit: int = 60) -> list[dict]:
        rows = self.graph.query(
            f"MATCH (c:Class {{iri: $iri}}){pattern}(o:Class) "
            f"RETURN DISTINCT o.iri, o.name ORDER BY o.name LIMIT {int(limit)}",
            {"iri": iri})
        return [{"iri": r[0], "name": r[1]} for r in rows.result_set]

    def _property_edges(self, iri: str, *, outgoing: bool, limit: int = 60) -> list[dict]:
        """Non-taxonomy edges, whichever direction, with the axiom shape that produced them."""
        pattern = ("MATCH (c:Class {iri: $iri})-[r]->(o:Class)" if outgoing
                   else "MATCH (o:Class)-[r]->(c:Class {iri: $iri})")
        rows = self.graph.query(
            f"{pattern} WHERE type(r) <> 'SUBCLASS_OF' AND type(r) <> 'DEFINED_IN' "
            f"RETURN DISTINCT r.name, r.quantifier, r.via, o.name, o.iri "
            f"ORDER BY r.name LIMIT {int(limit)}",
            {"iri": iri})
        return [{"property": r[0], "quantifier": r[1] or "", "via": r[2] or "",
                 "target": r[3], "target_iri": r[4]} for r in rows.result_set]

    # -- stage 3: graph context ----------------------------------------------- #

    def neighbourhood(self, term: str, hops: int = 1, limit: int = 80) -> dict:
        """The class plus everything within `hops`, as triples an answer can cite."""
        iri = self.resolve(term)
        if iri is None:
            return {"error": f"no class matches {term!r}"}
        hops = max(1, min(int(hops), 3))
        rows = self.graph.query(
            f"MATCH p = (c:Class {{iri: $iri}})-[*1..{hops}]-(o:Class) "
            f"WITH relationships(p) AS rels UNWIND rels AS r "
            f"WITH DISTINCT startNode(r) AS s, r, endNode(r) AS e "
            f"RETURN s.name, type(r), r.quantifier, e.name, s.iri, e.iri LIMIT {int(limit)}",
            {"iri": iri})
        triples = [
            {"source": r[0], "predicate": r[1], "quantifier": r[2] or "",
             "target": r[3], "source_iri": r[4], "target_iri": r[5]}
            for r in rows.result_set
        ]
        return {"centre": iri, "hops": hops, "triple_count": len(triples), "triples": triples}

    def ancestors(self, term: str, max_depth: int = 12) -> dict:
        """The subsumption chain from a class upward, nearest ancestor first."""
        iri = self.resolve(term)
        if iri is None:
            return {"error": f"no class matches {term!r}"}
        rows = self.graph.query(
            f"MATCH p = (c:Class {{iri: $iri}})-[:SUBCLASS_OF*1..{int(max_depth)}]->(a:Class) "
            f"RETURN a.name, a.iri, length(p) AS d ORDER BY d",
            {"iri": iri})
        seen, chain = set(), []
        for name, ancestor_iri, depth in rows.result_set:
            if ancestor_iri in seen:
                continue
            seen.add(ancestor_iri)
            chain.append({"name": name, "iri": ancestor_iri, "depth": depth})
        return {"iri": iri, "ancestors": chain}

    def path_between(self, term_a: str, term_b: str, max_hops: int = 5) -> dict:
        """The shortest undirected path between two classes, or an explicit miss."""
        a, b = self.resolve(term_a), self.resolve(term_b)
        if a is None or b is None:
            missing = term_a if a is None else term_b
            return {"error": f"no class matches {missing!r}"}
        rows = self.graph.query(
            f"MATCH p = shortestPath((x:Class {{iri: $a}})-[*1..{int(max_hops)}]-(y:Class {{iri: $b}})) "
            f"RETURN [n IN nodes(p) | n.name], [r IN relationships(p) | type(r)]",
            {"a": a, "b": b})
        if not rows.result_set:
            return {"from": a, "to": b, "connected": False,
                    "note": f"no path within {max_hops} hops"}
        nodes, rels = rows.result_set[0]
        steps = [f"{nodes[i]} -[{rels[i]}]- {nodes[i + 1]}" for i in range(len(rels))]
        return {"from": a, "to": b, "connected": True, "hops": len(rels), "path": steps}

    # -- stage 4: the escape hatch -------------------------------------------- #

    def run_cypher(self, query: str, limit: int = 50) -> dict:
        """Run a read-only Cypher query. Refuses anything that could mutate the graph."""
        if _FORBIDDEN.search(query) or _FORBIDDEN_CALL.search(query):
            return {"error": "refused: this retriever is read-only. Use MATCH/RETURN only."}
        if not re.search(r"\bRETURN\b", query, re.IGNORECASE):
            return {"error": "refused: query has no RETURN clause."}
        if not re.search(r"\bLIMIT\b", query, re.IGNORECASE):
            query = f"{query.rstrip().rstrip(';')} LIMIT {int(limit)}"
        try:
            result = self.graph.query(query, timeout=CYPHER_TIMEOUT_MS)
        except Exception as exc:
            message = str(exc)
            if "timed out" in message.lower():
                return {"error": "query timed out",
                        "hint": ("this graph has one relationship type per ontology "
                                 "property, so an untyped pattern like ()-[r]->() has to "
                                 "union hundreds of edge sets. Name the relationship type, "
                                 "or label both endpoints, e.g. (a:Class)-[:SUBCLASS_OF]->(b:Class).")}
            return {"error": f"cypher failed: {message}"}
        return {"columns": list(result.header and [h[1] for h in result.header] or []),
                "rows": [[_plain(v) for v in row] for row in result.result_set]}

    # -- orientation ---------------------------------------------------------- #

    def schema_summary(self, top_n: int = 25) -> dict:
        """What is in this graph: labels, counts, and the relationship types worth using.

        The agent is told to call this first. Without it an LLM writes Cypher against the
        relationship types it imagines an ontology has, and every such query returns
        zero rows -- which it then reports as 'no such thing exists'.
        """
        if self._schema_cache is not None:
            return self._schema_cache

        counts = self.exporter.edge_counts_by_type()
        properties = sorted(
            ((rt, n) for rt, n in counts.items() if rt not in ("SUBCLASS_OF", "DEFINED_IN")),
            key=lambda kv: kv[1], reverse=True)
        module_rows = self.graph.query(
            "MATCH (c:Class)-[:DEFINED_IN]->(m:Module) "
            "RETURN m.name, count(c) AS n ORDER BY n DESC LIMIT $k", {"k": top_n})

        self._schema_cache = {
            "graph": self.settings.graph_name,
            "node_labels": {"Class": self.exporter.count_nodes("Class"),
                            "Module": self.exporter.count_nodes("Module")},
            "edges_total": sum(counts.values()),
            "SUBCLASS_OF": counts.get("SUBCLASS_OF", 0),
            "DEFINED_IN": counts.get("DEFINED_IN", 0),
            "relationship_type_count": len(properties),
            "class_properties": ["iri", "name", "short_name", "definition",
                                 "alt_labels", "external", "module_iri"],
            "edge_properties": ["name", "quantifier", "via", "iri", "origin", "cardinality"],
            "top_relationship_types": [{"type": rt, "count": n} for rt, n in properties[:top_n]],
            "largest_modules": [{"module": r[0], "classes": r[1]} for r in module_rows.result_set],
            "note": (f"There are {len(properties)} relationship types in total -- one per "
                     f"ontology object property -- and only the most common are listed. "
                     f"Do not assume a type exists because the concept does; confirm with "
                     f"get_concept, which reports the relations a class actually has."),
        }
        return self._schema_cache


def _sanitise_fulltext(query: str) -> str:
    """Strip the RediSearch operators a natural-language question brings with it."""
    cleaned = re.sub(r"[^\w\s]", " ", query)
    return " ".join(cleaned.split()) or query


def _plain(value):
    """Cypher values -> JSON-safe Python."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return str(value)
