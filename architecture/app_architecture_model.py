"""Logical Application Architecture for EKGF maturity **Level 2 — Extensible
Platform** of the Ontology Repository Capability Model.

This module defines the ArchiMate **Application layer** elements required to
support the 14 Level-2 capabilities (see
``ontology_engineering_capabilities``):

* **Application Components** — deployable software units.
* **Application Services** — externally visible behaviour; each L2 capability is
  served by one (or more) application service.
* **Data Objects** — passive structure accessed by the components.
* **Relations** — ArchiMate ``realization`` (component → service),
  ``serving`` (service → capability, component → component) and ``access``
  (component → data object, with read/write mode).

Elements are grouped into **Application Domains** (logical groupings /
ArchiMate application collaborations) that drive the diagram layout.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

# Make the sibling capability package importable when run as a plain script.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Pull the capability definitions so the architecture stays in sync and we can
# assert that every supported capability really is a Level-2 capability.
from ontology_engineering_capabilities import CAPABILITY_BY_ID, EKGF_LEVELS

TARGET_LEVEL = 2
TARGET_LEVEL_NAME = EKGF_LEVELS[TARGET_LEVEL]  # "Extensible Platform"


# --------------------------------------------------------------------------- #
# Element types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ApplicationDomain:
    """A logical grouping of components (ArchiMate application collaboration)."""

    id: str
    name: str
    description: str


@dataclass(frozen=True)
class DataObject:
    """ArchiMate Data Object (passive structure)."""

    id: str
    name: str
    description: str


@dataclass(frozen=True)
class ApplicationService:
    """ArchiMate Application Service serving one or more L2 capabilities."""

    id: str
    name: str
    description: str
    serves_capabilities: tuple[str, ...]  # capability ids (must be Level 2)


@dataclass(frozen=True)
class ApplicationComponent:
    """ArchiMate Application Component realizing services and accessing data."""

    id: str
    name: str
    domain: str  # ApplicationDomain.id
    description: str
    realizes: tuple[str, ...]  # ApplicationService ids
    reads: tuple[str, ...] = ()  # DataObject ids (access: read)
    writes: tuple[str, ...] = ()  # DataObject ids (access: write/read-write)
    uses: tuple[str, ...] = ()  # other ApplicationComponent ids it is served by
    technology_candidates: tuple[str, ...] = ()  # illustrative COTS/OSS options


# --------------------------------------------------------------------------- #
# Application domains (left-to-right columns in the diagram)
# --------------------------------------------------------------------------- #
DOMAINS: list[ApplicationDomain] = [
    ApplicationDomain("MOD", "Modelling & Authoring",
                      "Author and formalise ontologies and reuse foundational models."),
    ApplicationDomain("VOC", "Vocabulary & Glossary",
                      "Manage controlled vocabularies, thesauri and the business glossary."),
    ApplicationDomain("RVT", "Reasoning, Validation & Testing",
                      "Classify, check consistency, validate constraints and run CQ tests."),
    ApplicationDomain("KGP", "Knowledge Graph Platform",
                      "Store, version, release and query ontologies and their graphs."),
    ApplicationDomain("ACP", "Access & Publishing",
                      "Explore, visualise, document and publish ontologies."),
    ApplicationDomain("ENB", "Enterprise Enablement",
                      "Enterprise services that fund and staff the ontology practice."),
]
DOMAIN_BY_ID = {d.id: d for d in DOMAINS}


# --------------------------------------------------------------------------- #
# Data objects
# --------------------------------------------------------------------------- #
DATA_OBJECTS: list[DataObject] = [
    DataObject("D.ONT", "OWL Ontology", "The formal ontology (OWL/RDFS) under development."),
    DataObject("D.VOC", "SKOS Vocabulary / Thesaurus", "Controlled vocabularies and thesauri."),
    DataObject("D.GLO", "Business Glossary", "Agreed business terms and definitions."),
    DataObject("D.SHP", "SHACL Shapes", "Constraint shapes used to validate data and models."),
    DataObject("D.CQ", "Competency-Question Test Suite", "Executable competency-question tests."),
    DataObject("D.GRAPH", "RDF Graph (Triples)", "Stored RDF triples / named graphs."),
    DataObject("D.INF", "Inference Result", "Entailments and reasoner classification results."),
    DataObject("D.REL", "Ontology Release / Version", "Versioned, tagged ontology releases."),
    DataObject("D.QRY", "SPARQL Query / Result", "Queries and their result sets."),
    DataObject("D.DOC", "Documentation Site", "Generated human-readable ontology documentation."),
    DataObject("D.FUND", "Funding / Portfolio Record", "Budget, investment and portfolio records."),
    DataObject("D.SKILL", "Skills Profile", "Competency and talent records for the practice."),
]
DATA_OBJECT_BY_ID = {d.id: d for d in DATA_OBJECTS}


# --------------------------------------------------------------------------- #
# Application services (each serves >=1 Level-2 capability)
# --------------------------------------------------------------------------- #
SERVICES: list[ApplicationService] = [
    ApplicationService("S.AUTH", "Ontology Authoring Service",
                       "Create, edit and formalise ontology classes, properties and axioms.",
                       ("T.DA.2",)),
    ApplicationService("S.IMPORT", "Foundational Ontology Import Service",
                       "Discover, import and align upper/foundational ontologies and modules.",
                       ("T.DA.3",)),
    ApplicationService("S.VOCAB", "Controlled Vocabulary Management Service",
                       "Curate SKOS vocabularies, thesauri and code lists.",
                       ("T.DA.6",)),
    ApplicationService("S.GLOSS", "Business Glossary Service",
                       "Maintain business terms reconciled with the ontology.",
                       ("B.SE.4",)),
    ApplicationService("S.REASON", "Consistency Reasoning Service",
                       "Classify the ontology and check logical consistency/satisfiability.",
                       ("T.RI.1",)),
    ApplicationService("S.VALIDATE", "Constraint Validation Service",
                       "Validate ontology and data against SHACL shapes/constraints.",
                       ("T.QV.1",)),
    ApplicationService("S.CQTEST", "Competency-Question Testing Service",
                       "Run competency-question test suites on every change.",
                       ("T.QV.2",)),
    ApplicationService("S.STORE", "Graph Storage Service",
                       "Persist ontologies and instance graphs in a managed store.",
                       ("T.OO.1",)),
    ApplicationService("S.SPARQL", "SPARQL Query Service",
                       "Standards-based query access (SPARQL) to the knowledge graph.",
                       ("T.AC.1",)),
    ApplicationService("S.VERSION", "Ontology Versioning & Release Service",
                       "Version, tag, diff and release ontologies under change control.",
                       ("T.OO.2",)),
    ApplicationService("S.VIZ", "Ontology Visualization Service",
                       "Interactive visual exploration of ontology structure and content.",
                       ("T.AC.2",)),
    ApplicationService("S.DOCS", "Documentation Publishing Service",
                       "Generate and publish human-readable ontology documentation.",
                       ("T.AC.3",)),
    ApplicationService("S.FUND", "Funding & Portfolio Service",
                       "Manage budget, investment and portfolio for the ontology roadmap.",
                       ("B.SG.4",)),
    ApplicationService("S.SKILL", "Skills & Competency Service",
                       "Manage ontology-engineering skills, roles and talent.",
                       ("B.CT.1",)),
]
SERVICE_BY_ID = {s.id: s for s in SERVICES}


# --------------------------------------------------------------------------- #
# Application components
# --------------------------------------------------------------------------- #
COMPONENTS: list[ApplicationComponent] = [
    ApplicationComponent(
        "C.AUTH", "Ontology Authoring Workbench", "MOD",
        "Desktop/web ontology editor for formalising the conceptual model.",
        realizes=("S.AUTH", "S.IMPORT"),
        reads=("D.VOC", "D.GLO"), writes=("D.ONT",),
        uses=("C.VOCAB", "C.RVE", "C.KGS"),
        technology_candidates=("Protégé", "TopBraid Composer", "VS Code + ROBOT"),
    ),
    ApplicationComponent(
        "C.VOCAB", "Vocabulary & Thesaurus Manager", "VOC",
        "SKOS editor for controlled vocabularies, thesauri and code lists.",
        realizes=("S.VOCAB",),
        reads=(), writes=("D.VOC",),
        uses=("C.KGS",),
        technology_candidates=("VocBench", "PoolParty", "Skosmos (publish)"),
    ),
    ApplicationComponent(
        "C.GLOSS", "Business Glossary Manager", "VOC",
        "Business-facing glossary tool reconciled with the ontology.",
        realizes=("S.GLOSS",),
        reads=("D.VOC",), writes=("D.GLO",),
        technology_candidates=("Collibra", "egeria", "Atlan"),
    ),
    ApplicationComponent(
        "C.RVE", "Reasoning & Validation Engine", "RVT",
        "Reasoner + SHACL validator + competency-question test runner.",
        realizes=("S.REASON", "S.VALIDATE", "S.CQTEST"),
        reads=("D.ONT", "D.GRAPH"), writes=("D.SHP", "D.CQ", "D.INF"),
        uses=("C.KGS",),
        technology_candidates=("HermiT/ELK/Pellet", "pySHACL/TopBraid SHACL", "Themis/OQuaRE"),
    ),
    ApplicationComponent(
        "C.KGS", "Knowledge Graph Store & Query Engine", "KGP",
        "Triplestore exposing storage and a SPARQL endpoint.",
        realizes=("S.STORE", "S.SPARQL"),
        reads=("D.ONT",), writes=("D.GRAPH", "D.QRY"),
        technology_candidates=("GraphDB", "Stardog", "Apache Jena Fuseki", "Virtuoso"),
    ),
    ApplicationComponent(
        "C.REPO", "Ontology Repository & Version Control", "KGP",
        "Git-based repository for versioning, diffing and releasing ontologies.",
        realizes=("S.VERSION",),
        reads=("D.ONT",), writes=("D.REL",),
        uses=("C.KGS",),
        technology_candidates=("Git/GitHub/GitLab", "ROBOT", "OnToology"),
    ),
    ApplicationComponent(
        "C.VIZ", "Ontology Visualization & Exploration", "ACP",
        "Interactive graph/tree visualisation of the ontology and graph.",
        realizes=("S.VIZ",),
        reads=("D.GRAPH", "D.ONT"), writes=(),
        uses=("C.KGS",),
        technology_candidates=("WebVOWL", "VOWL", "yEd/Graphviz", "Ontodia"),
    ),
    ApplicationComponent(
        "C.DOC", "Documentation Generator & Portal", "ACP",
        "Generates and publishes human-readable ontology documentation.",
        realizes=("S.DOCS",),
        reads=("D.ONT",), writes=("D.DOC",),
        uses=("C.REPO",),
        technology_candidates=("Widoco", "pyLODE", "Ontospy"),
    ),
    ApplicationComponent(
        "C.FUND", "Portfolio & Funding Management", "ENB",
        "Enterprise portfolio/budget application supporting funding decisions.",
        realizes=("S.FUND",),
        reads=(), writes=("D.FUND",),
        technology_candidates=("Jira Align", "ServiceNow SPM", "Planview"),
    ),
    ApplicationComponent(
        "C.SKILL", "Skills & Talent Management", "ENB",
        "Enterprise HR/competency application for the ontology practice.",
        realizes=("S.SKILL",),
        reads=(), writes=("D.SKILL",),
        technology_candidates=("Workday", "SAP SuccessFactors", "Skills matrix"),
    ),
]
COMPONENT_BY_ID = {c.id: c for c in COMPONENTS}


# --------------------------------------------------------------------------- #
# Accessors / validation
# --------------------------------------------------------------------------- #
def services_for_capability(cap_id: str) -> list[ApplicationService]:
    return [s for s in SERVICES if cap_id in s.serves_capabilities]


def components_in(domain_id: str) -> list[ApplicationComponent]:
    return [c for c in COMPONENTS if c.domain == domain_id]


def services_of(component: ApplicationComponent) -> list[ApplicationService]:
    return [SERVICE_BY_ID[sid] for sid in component.realizes]


def supported_capability_ids() -> list[str]:
    ids: list[str] = []
    for s in SERVICES:
        ids.extend(s.serves_capabilities)
    return sorted(set(ids))


def validate_model() -> list[str]:
    """Return integrity problems (empty == consistent)."""
    problems: list[str] = []
    svc_ids = set(SERVICE_BY_ID)
    comp_ids = set(COMPONENT_BY_ID)
    data_ids = set(DATA_OBJECT_BY_ID)

    # every service must serve only Level-2 capabilities
    for s in SERVICES:
        for cid in s.serves_capabilities:
            cap = CAPABILITY_BY_ID.get(cid)
            if cap is None:
                problems.append(f"{s.id}: unknown capability {cid!r}")
            elif cap.maturity_level != TARGET_LEVEL:
                problems.append(f"{s.id}: capability {cid} is L{cap.maturity_level}, not L{TARGET_LEVEL}")

    # every service must be realized by exactly-one+ component
    realized = {sid for c in COMPONENTS for sid in c.realizes}
    for sid in svc_ids - realized:
        problems.append(f"service {sid} is not realized by any component")

    # component references must resolve
    for c in COMPONENTS:
        if c.domain not in DOMAIN_BY_ID:
            problems.append(f"{c.id}: unknown domain {c.domain!r}")
        for sid in c.realizes:
            if sid not in svc_ids:
                problems.append(f"{c.id}: realizes unknown service {sid!r}")
        for did in (*c.reads, *c.writes):
            if did not in data_ids:
                problems.append(f"{c.id}: accesses unknown data object {did!r}")
        for uid in c.uses:
            if uid not in comp_ids:
                problems.append(f"{c.id}: uses unknown component {uid!r}")

    # every Level-2 capability should be supported by >=1 service
    l2 = {cid for cid, cap in CAPABILITY_BY_ID.items() if cap.maturity_level == TARGET_LEVEL}
    for cid in l2 - set(supported_capability_ids()):
        problems.append(f"Level-2 capability {cid} has no supporting application service")

    return problems


if __name__ == "__main__":
    probs = validate_model()
    print(f"domains    : {len(DOMAINS)}")
    print(f"services   : {len(SERVICES)}")
    print(f"components : {len(COMPONENTS)}")
    print(f"data objs  : {len(DATA_OBJECTS)}")
    print(f"L2 caps    : {len(supported_capability_ids())} supported")
    print(f"problems   : {len(probs)}")
    for p in probs:
        print("  -", p)
