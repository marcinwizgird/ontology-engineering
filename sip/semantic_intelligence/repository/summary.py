"""Structural summary of an ontology (FR-REPO-04): deterministic, no language model.

Everything here is computed from the graphs, so the same revision always gives the same
summary. The narrative (LLM) summary of the design's §7.3 is a later release and takes
this output as its only input.
"""

from __future__ import annotations

from collections import Counter

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS

from ..owl.hierarchy import ClassHierarchy
from ..owl.rendering import ShortFormProvider
from ..quality import metrics as metricsmod

_BUILTIN = (str(OWL), str(RDF), str(RDFS), str(SKOS), "http://www.w3.org/2001/XMLSchema#")
_LABELS = (RDFS.label, SKOS.prefLabel)
_DEFS = (SKOS.definition, RDFS.comment, DCTERMS.description)
_KINDS = {"class": OWL.Class, "objectProperty": OWL.ObjectProperty,
          "dataProperty": OWL.DatatypeProperty, "annotationProperty": OWL.AnnotationProperty,
          "individual": OWL.NamedIndividual, "concept": SKOS.Concept}
TOP = 10


def _own(x) -> bool:
    return isinstance(x, URIRef) and not str(x).startswith(_BUILTIN)


def _definition_preds(g: Graph) -> set[URIRef]:
    """skos:definition, rdfs:comment, dcterms:description, and any annotation property
    whose local name says "definition" (FIBO and many corporate ontologies define their
    own)."""
    preds = set(_DEFS)
    for p in set(g.predicates()):
        local = str(p).rsplit("#", 1)[-1].rsplit("/", 1)[-1].lower()
        if "definition" in local:
            preds.add(p)
    return preds


def _first(g: Graph, s, preds) -> str | None:
    for p in preds:
        for o in g.objects(s, p):
            if isinstance(o, Literal):
                return str(o)
    return None


def _snippet(text: str | None, n: int = 160) -> str | None:
    if not text:
        return None
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def header(main: Graph) -> dict:
    """The ``owl:Ontology`` header of the main graph."""
    onto = next((s for s in main.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)), None)
    if onto is None:
        return {k: None for k in ("ontology_iri", "version_iri", "version_info", "title",
                                  "description", "licence")} | {"creators": [], "imports": []}

    def vals(*preds):
        return sorted({str(o) for p in preds for o in main.objects(onto, p)})
    title = vals(DCTERMS.title, RDFS.label)
    desc = vals(DCTERMS.description, RDFS.comment, SKOS.definition)
    return {"ontology_iri": str(onto),
            "version_iri": next(iter(vals(OWL.versionIRI)), None),
            "version_info": next(iter(vals(OWL.versionInfo)), None),
            "title": title[0] if title else None,
            "description": desc[0] if desc else None,
            "licence": next(iter(vals(DCTERMS.license, DCTERMS.rights)), None),
            "creators": vals(DCTERMS.creator, DCTERMS.contributor),
            "imports": vals(OWL.imports)}


def modules(main: Graph, imports: dict[str, Graph]) -> list[dict]:
    """One row per ontology document: the main graph and each materialised import."""
    rows = []
    for gid, g in [("main", main)] + sorted(imports.items()):
        onto = sorted(str(s) for s in g.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef))
        rows.append({"graph": gid, "ontology_iri": onto[0] if onto else None,
                     "triples": len(g),
                     "classes": len({s for s in g.subjects(RDF.type, OWL.Class) if _own(s)}),
                     "imports": sorted(str(o) for o in g.objects(None, OWL.imports))})
    return rows


def entity_counts(g: Graph) -> dict[str, int]:
    return {k: len({s for s in g.subjects(RDF.type, t) if _own(s)}) for k, t in _KINDS.items()}


def structural_summary(g: Graph, main: Graph, imports: dict[str, Graph],
                       languages: tuple[str, ...] = ("en",)) -> dict:
    """The deterministic summary: identity, size, main concepts, key relationships,
    modules, annotation coverage, label languages and gaps. ``g`` is main ∪ imports."""
    sfp = ShortFormProvider(g, languages=tuple(languages) + ("",))
    defs = _definition_preds(g)
    h = ClassHierarchy(g)
    classes = sorted(c for c in h.classes if _own(c))

    top = sorted(((len(h.descendants(c)), str(c), c) for c in classes), reverse=True)[:TOP]
    main_concepts = [{"iri": str(c), "label": sfp.render(c), "descendants": n,
                      "definition": _snippet(_first(g, c, defs))} for n, _, c in top if n > 0]

    usage: Counter = Counter()
    props = {p for p in g.subjects(RDF.type, OWL.ObjectProperty) if _own(p)}
    for p in props:
        usage[p] += sum(1 for _ in g.subject_objects(p))
        usage[p] += sum(1 for _ in g.subjects(OWL.onProperty, p))
        usage[p] += sum(1 for _ in g.subjects(RDFS.subPropertyOf, p))
    key_props = []
    for p, n in sorted(usage.items(), key=lambda kv: (-kv[1], str(kv[0])))[:TOP]:
        dom = [sfp.render(d) for d in g.objects(p, RDFS.domain) if isinstance(d, URIRef)]
        rng = [sfp.render(r) for r in g.objects(p, RDFS.range) if isinstance(r, URIRef)]
        key_props.append({"iri": str(p), "label": sfp.render(p), "usage": n,
                          "domain": sorted(dom), "range": sorted(rng)})

    entities = sorted({s for t in _KINDS.values() for s in g.subjects(RDF.type, t) if _own(s)})
    labelled = [e for e in entities if any(True for p in _LABELS for _ in g.objects(e, p))]
    defined = [e for e in entities if _first(g, e, defs)]
    langs: Counter = Counter()
    for e in entities:
        for p in _LABELS:
            for o in g.objects(e, p):
                if isinstance(o, Literal):
                    langs[o.language or ""] += 1
    deprecated = sorted(str(s) for s, o in g.subject_objects(OWL.deprecated)
                        if str(o).lower() == "true")
    has_label = set(labelled)
    unlabelled = [str(e) for e in entities if e not in has_label]
    loaded = {str(o) for m in [main] + list(imports.values())
              for o in m.subjects(RDF.type, OWL.Ontology)}
    unresolved = sorted({str(o) for o in g.objects(None, OWL.imports)} - loaded)
    m = metricsmod.metrics(g)
    gcis = sum(1 for s in g.subjects(RDFS.subClassOf, None) if isinstance(s, BNode))

    return {
        "header": header(main),
        "size": {"triples": len(g), "modules": 1 + len(imports), **entity_counts(g),
                 "axioms": m["Metrics"].get("Axiom"),
                 "logical_axioms": m["Metrics"].get("Logical axiom count"),
                 "anonymous_superclass_axioms": gcis},
        "expressivity": m["Metrics"].get("DL expressivity (hint)"),
        "main_concepts": main_concepts,
        "key_relationships": key_props,
        "modules": modules(main, imports),
        "annotations": {
            "entities": len(entities),
            "label_coverage": round(len(labelled) / len(entities), 3) if entities else None,
            "definition_coverage": round(len(defined) / len(entities), 3) if entities else None,
            "label_languages": dict(sorted(langs.items())),
        },
        "gaps": {"unlabelled": unlabelled[:TOP], "unlabelled_count": len(unlabelled),
                 "deprecated_count": len(deprecated), "unresolved_imports": unresolved},
    }
