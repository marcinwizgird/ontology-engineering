"""Ontology Repository Capability Model.

A comprehensive set of *requirements* for an ontology-engineering practice,
expressed as **business** and **technology** capabilities.  The capabilities
are arranged simultaneously as:

* a **taxonomy** — a strict broader/narrower (is-a / part-of) tree
  (Domain → Category → Capability), and
* an **ontology** — a richer typed graph adding ``dependsOn``, ``enables``,
  ``supports`` and ``governedBy`` relations between capabilities.

Every capability is mapped to a pillar and a target maturity **level** of the
**EKGF Enterprise Knowledge Graph Maturity Model (EKG/MM v1.0)**:

EKGF pillars (https://maturity.ekgf.org/intro/structure/):
    Business · Organization · Data · Technology
EKGF maturity levels (1..5):
    1 EKG Initiation · 2 Extensible Platform · 3 Enterprise Ready
    · 4 Strategic Asset · 5 Operational Ecosystem

This module only defines the data + lightweight accessors; diagram/RDF
generation lives in ``generators.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# EKGF reference vocabulary
# --------------------------------------------------------------------------- #
EKGF_LEVELS: dict[int, str] = {
    1: "EKG Initiation",
    2: "Extensible Platform",
    3: "Enterprise Ready",
    4: "Strategic Asset",
    5: "Operational Ecosystem",
}

EKGF_PILLARS: tuple[str, ...] = ("Business", "Organization", "Data", "Technology")

# The two top-level capability *domains* requested (business vs technology).
DOMAINS: tuple[str, ...] = ("Business", "Technology")


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Category:
    """A capability category — the middle tier of the taxonomy."""

    id: str
    name: str
    domain: str  # "Business" | "Technology"
    description: str


@dataclass(frozen=True)
class Capability:
    """A single capability (leaf of the taxonomy / node of the ontology)."""

    id: str
    name: str
    domain: str  # "Business" | "Technology"
    category: str  # Category.id  (taxonomy parent)
    description: str
    ekgf_pillar: str  # one of EKGF_PILLARS
    maturity_level: int  # 1..5 target EKGF level at which it is expected
    requirement: str  # the requirement statement (shall ...)
    depends_on: tuple[str, ...] = ()  # capability ids this one needs
    supports: tuple[str, ...] = ()  # business capability ids a tech cap supports
    governed_by: tuple[str, ...] = ()  # governance capability ids

    @property
    def level_name(self) -> str:
        return EKGF_LEVELS[self.maturity_level]


# --------------------------------------------------------------------------- #
# Categories
# --------------------------------------------------------------------------- #
CATEGORIES: list[Category] = [
    # -- Business domain --
    Category("BSG", "Ontology Strategy & Governance", "Business",
             "Direction-setting, policy, funding and oversight of the ontology practice."),
    Category("BSE", "Stakeholder & Domain Engagement", "Business",
             "Capturing intent and knowledge from domain experts and consumers."),
    Category("BVP", "Value & Performance Management", "Business",
             "Justifying, measuring and driving adoption of the ontology."),
    Category("BCT", "Capability & Talent Development", "Business",
             "People, skills and ecosystem collaboration that sustain the practice."),
    # -- Technology domain --
    Category("TDA", "Ontology Development & Authoring", "Technology",
             "Conceptualising and formalising ontologies and vocabularies."),
    Category("TIA", "Ontology Integration & Alignment", "Technology",
             "Connecting ontologies and data into a coherent semantic layer."),
    Category("TRI", "Reasoning & Inference", "Technology",
             "Deriving and explaining new knowledge from the ontology."),
    Category("TQV", "Quality, Validation & Verification", "Technology",
             "Ensuring the ontology is correct, consistent and fit for purpose."),
    Category("TOO", "Ontology Operations (OntoOps)", "Technology",
             "Storing, versioning, releasing and operating ontologies at scale."),
    Category("TAC", "Access, Consumption & Visualization", "Technology",
             "Publishing, querying, exploring and exploiting the ontology."),
]

CATEGORY_BY_ID = {c.id: c for c in CATEGORIES}


# --------------------------------------------------------------------------- #
# Capabilities (the requirements)
# --------------------------------------------------------------------------- #
CAPABILITIES: list[Capability] = [
    # ===================== BUSINESS · Strategy & Governance ================= #
    Capability(
        "B.SG.1", "Ontology Vision & Strategy", "Business", "BSG",
        "Define the vision, scope, objectives and roadmap for the ontology programme.",
        "Business", 1,
        "The practice shall maintain an explicit ontology vision and strategy aligned to business goals.",
    ),
    Capability(
        "B.SG.2", "Ontology Governance & Stewardship", "Business", "BSG",
        "Roles, decision rights and stewardship over ontological assets.",
        "Data", 3,
        "The practice shall establish governance bodies and assign stewards for every ontology asset.",
        depends_on=("B.SG.1",),
    ),
    Capability(
        "B.SG.3", "Policy, Standards & Conventions Management", "Business", "BSG",
        "Modelling guidelines, naming conventions, reuse and licensing policies.",
        "Data", 3,
        "The practice shall publish and enforce ontology modelling standards and naming conventions.",
        depends_on=("B.SG.2",),
    ),
    Capability(
        "B.SG.4", "Funding & Investment Management", "Business", "BSG",
        "Securing and allocating budget for ontology work.",
        "Organization", 2,
        "The practice shall secure sustained funding tied to the ontology roadmap and value case.",
        depends_on=("B.SG.1",),
    ),
    Capability(
        "B.SG.5", "Ontology Risk & Compliance Management", "Business", "BSG",
        "Managing semantic, legal, privacy and regulatory risk of ontologies.",
        "Data", 4,
        "The practice shall identify and mitigate risks arising from ontology content and its use.",
        depends_on=("B.SG.2", "B.SG.3"),
    ),

    # ===================== BUSINESS · Stakeholder Engagement ================ #
    Capability(
        "B.SE.1", "Domain Knowledge Elicitation", "Business", "BSE",
        "Structured capture of expert knowledge (interviews, workshops).",
        "Business", 1,
        "The practice shall systematically elicit and record domain knowledge from subject-matter experts.",
        depends_on=("B.SG.1",),
    ),
    Capability(
        "B.SE.2", "Competency Question Management", "Business", "BSE",
        "Capturing the questions the ontology must answer.",
        "Business", 1,
        "The practice shall define and maintain competency questions that scope and validate the ontology.",
        depends_on=("B.SE.1",),
    ),
    Capability(
        "B.SE.3", "Use-Case & Requirements Management", "Business", "BSE",
        "Eliciting, prioritising and tracing ontology requirements.",
        "Organization", 1,
        "The practice shall manage prioritised, traceable ontology requirements linked to use cases.",
        depends_on=("B.SE.2",),
    ),
    Capability(
        "B.SE.4", "Business Glossary & Terminology Management", "Business", "BSE",
        "Agreed business terms and definitions feeding the ontology.",
        "Data", 2,
        "The practice shall maintain an authoritative business glossary reconciled with the ontology.",
        depends_on=("B.SE.1",),
    ),

    # ===================== BUSINESS · Value & Performance =================== #
    Capability(
        "B.VP.1", "Value Case & Benefits Realization", "Business", "BVP",
        "Articulating and tracking the business value of the ontology.",
        "Business", 4,
        "The practice shall quantify and track the realised business value of ontology investments.",
        depends_on=("B.SG.4", "B.SE.3"),
    ),
    Capability(
        "B.VP.2", "Performance Measurement (KPIs)", "Business", "BVP",
        "Metrics for ontology quality, coverage, reuse and usage.",
        "Business", 4,
        "The practice shall measure ontology performance against defined KPIs and report them.",
        depends_on=("B.VP.1",),
    ),
    Capability(
        "B.VP.3", "Adoption & Change Management", "Business", "BVP",
        "Driving uptake of the ontology across the organization.",
        "Organization", 3,
        "The practice shall actively manage adoption and change for ontology-based ways of working.",
        depends_on=("B.SE.3",),
    ),

    # ===================== BUSINESS · Capability & Talent =================== #
    Capability(
        "B.CT.1", "Skills & Talent Management", "Business", "BCT",
        "Recruiting and developing ontology-engineering competencies.",
        "Organization", 2,
        "The practice shall build and retain the ontology-engineering skills needed by the roadmap.",
        depends_on=("B.SG.1",),
    ),
    Capability(
        "B.CT.2", "Knowledge Sharing & Community of Practice", "Business", "BCT",
        "Internal reuse of patterns, lessons and assets.",
        "Organization", 3,
        "The practice shall operate a community of practice that shares ontology assets and lessons.",
        depends_on=("B.CT.1",),
    ),
    Capability(
        "B.CT.3", "Ecosystem & Standards Collaboration", "Business", "BCT",
        "Engaging external standards bodies and reusing public vocabularies.",
        "Organization", 5,
        "The practice shall collaborate with external standards ecosystems and adopt shared vocabularies.",
        depends_on=("B.CT.2",),
    ),

    # ===================== TECHNOLOGY · Development & Authoring ============= #
    Capability(
        "T.DA.1", "Ontology Conceptualization & Modelling", "Technology", "TDA",
        "Building the conceptual model (classes, relations, attributes).",
        "Data", 1,
        "The capability shall produce a conceptual model satisfying the competency questions.",
        depends_on=("B.SE.2",), supports=("B.SE.2",),
        governed_by=("B.SG.3",),
    ),
    Capability(
        "T.DA.2", "Ontology Formalization (OWL/RDFS/SKOS)", "Technology", "TDA",
        "Encoding the conceptual model in a formal logic / W3C language.",
        "Data", 2,
        "The capability shall formalise the conceptual model in a standard ontology language.",
        depends_on=("T.DA.1",), governed_by=("B.SG.3",),
    ),
    Capability(
        "T.DA.3", "Foundational / Top-down Ontology Reuse", "Technology", "TDA",
        "Reusing upper/foundational ontologies (e.g. DOLCE, BFO).",
        "Data", 2,
        "The capability shall reuse foundational ontologies where they improve interoperability.",
        depends_on=("T.DA.1",), governed_by=("B.SG.3",),
    ),
    Capability(
        "T.DA.4", "Bottom-up Ontology Learning", "Technology", "TDA",
        "Deriving ontologies from data, databases, text and other legacy resources.",
        "Data", 3,
        "The capability shall extract candidate ontology content from existing data and text sources.",
        depends_on=("T.DA.1", "T.IA.3"), supports=("B.SE.1",), governed_by=("B.SG.3",),
    ),
    Capability(
        "T.DA.5", "Ontology Design Pattern (ODP) Management", "Technology", "TDA",
        "Cataloguing and applying reusable modelling patterns.",
        "Data", 3,
        "The capability shall maintain and apply a catalogue of ontology design patterns.",
        depends_on=("T.DA.2",), governed_by=("B.SG.3",),
    ),
    Capability(
        "T.DA.6", "Vocabulary & Controlled-Term Management", "Technology", "TDA",
        "Managing controlled vocabularies, thesauri and code lists (SKOS).",
        "Data", 2,
        "The capability shall manage controlled vocabularies and thesauri reconciled with the ontology.",
        depends_on=("B.SE.4",), supports=("B.SE.4",), governed_by=("B.SG.3",),
    ),

    # ===================== TECHNOLOGY · Integration & Alignment ============= #
    Capability(
        "T.IA.1", "Ontology Mapping & Alignment", "Technology", "TIA",
        "Aligning concepts across ontologies and schemas.",
        "Data", 3,
        "The capability shall create and maintain mappings that align internal and external ontologies.",
        depends_on=("T.DA.2",), governed_by=("B.SG.2",),
    ),
    Capability(
        "T.IA.2", "Modularization & Import Management", "Technology", "TIA",
        "Decomposing ontologies into modules with managed imports.",
        "Data", 3,
        "The capability shall organise ontologies into versioned, importable modules.",
        depends_on=("T.DA.2",),
    ),
    Capability(
        "T.IA.3", "Semantic Data Integration", "Technology", "TIA",
        "Lifting and linking source data to the ontology (R2RML/RML, OBDA).",
        "Technology", 3,
        "The capability shall integrate heterogeneous source data through the ontology.",
        depends_on=("T.DA.2", "T.IA.1"), supports=("B.VP.1",),
    ),
    Capability(
        "T.IA.4", "Identity Resolution & Entity Reconciliation", "Technology", "TIA",
        "Resolving co-referent entities across sources.",
        "Technology", 3,
        "The capability shall reconcile co-referent entities to stable identifiers.",
        depends_on=("T.IA.3",),
    ),

    # ===================== TECHNOLOGY · Reasoning & Inference =============== #
    Capability(
        "T.RI.1", "Logical Consistency & Reasoning", "Technology", "TRI",
        "Classification and satisfiability checking with a reasoner.",
        "Technology", 2,
        "The capability shall verify logical consistency and classify the ontology with a reasoner.",
        depends_on=("T.DA.2",),
    ),
    Capability(
        "T.RI.2", "Inferencing & Materialization", "Technology", "TRI",
        "Computing and (optionally) materialising entailed facts.",
        "Technology", 3,
        "The capability shall compute entailments and make inferred knowledge available to consumers.",
        depends_on=("T.RI.1", "T.IA.3"), supports=("B.VP.1",),
    ),
    Capability(
        "T.RI.3", "Rule & Constraint Management (SHACL/SWRL)", "Technology", "TRI",
        "Authoring and executing business rules over the graph.",
        "Technology", 3,
        "The capability shall manage and execute rules that augment the ontology with domain logic.",
        depends_on=("T.DA.2",),
    ),
    Capability(
        "T.RI.4", "Inference Explainability", "Technology", "TRI",
        "Explaining and justifying derived results.",
        "Technology", 4,
        "The capability shall provide human-readable justifications for inferred results.",
        depends_on=("T.RI.2",), supports=("B.SG.5",),
    ),

    # ===================== TECHNOLOGY · Quality & Validation ================ #
    Capability(
        "T.QV.1", "Ontology Validation (SHACL/constraints)", "Technology", "TQV",
        "Validating data and models against shapes/constraints.",
        "Data", 2,
        "The capability shall validate ontology and data against declared constraints.",
        depends_on=("T.DA.2", "T.RI.3"), governed_by=("B.SG.3",),
    ),
    Capability(
        "T.QV.2", "Ontology Testing (Competency-Question tests)", "Technology", "TQV",
        "Executable tests that the ontology answers its competency questions.",
        "Data", 2,
        "The capability shall test the ontology against its competency questions on every change.",
        depends_on=("B.SE.2", "T.DA.2"), supports=("B.SE.2",),
    ),
    Capability(
        "T.QV.3", "Quality Assurance & Metrics", "Technology", "TQV",
        "Measuring structural and semantic quality of the ontology.",
        "Data", 3,
        "The capability shall measure ontology quality (coverage, cohesion, conciseness) continuously.",
        depends_on=("T.QV.1",), supports=("B.VP.2",),
    ),
    Capability(
        "T.QV.4", "Verification & Evaluation (gold standard)", "Technology", "TQV",
        "Comparing the ontology to a gold standard / use case.",
        "Data", 3,
        "The capability shall evaluate the ontology against gold standards and application use cases.",
        depends_on=("T.QV.2", "T.QV.3"), supports=("B.VP.2",),
    ),

    # ===================== TECHNOLOGY · Ontology Operations ================= #
    Capability(
        "T.OO.1", "Triplestore & Ontology Storage", "Technology", "TOO",
        "Persisting ontologies and graphs in a managed store.",
        "Technology", 2,
        "The capability shall store ontologies and instance data in a managed, backed-up triplestore.",
        depends_on=("T.DA.2",),
    ),
    Capability(
        "T.OO.2", "Versioning & Release Management", "Technology", "TOO",
        "Semantic versioning, change logs and deprecation of ontologies.",
        "Data", 2,
        "The capability shall version, release and deprecate ontologies under change control.",
        depends_on=("T.OO.1",), governed_by=("B.SG.2",),
    ),
    Capability(
        "T.OO.3", "Ontology CI/CD (OntoOps / DataOps)", "Technology", "TOO",
        "Automated build, test and deployment pipelines for ontologies.",
        "Technology", 4,
        "The capability shall automate build, test and deployment of ontology releases.",
        depends_on=("T.OO.2", "T.QV.2", "T.QV.1"),
    ),
    Capability(
        "T.OO.4", "Federation & Virtualization", "Technology", "TOO",
        "Querying across distributed graphs / virtual integration.",
        "Technology", 5,
        "The capability shall enable federated, virtualised access across distributed knowledge graphs.",
        depends_on=("T.IA.3", "T.OO.1"),
    ),
    Capability(
        "T.OO.5", "Observability & Monitoring", "Technology", "TOO",
        "Monitoring availability, performance and drift of the ontology service.",
        "Technology", 4,
        "The capability shall monitor the health, performance and drift of ontology services.",
        depends_on=("T.OO.1",), supports=("B.VP.2",),
    ),

    # ===================== TECHNOLOGY · Access & Visualization ============== #
    Capability(
        "T.AC.1", "Search & Query (SPARQL)", "Technology", "TAC",
        "Query interfaces over the ontology and graph.",
        "Technology", 2,
        "The capability shall provide standards-based query access (SPARQL) to the knowledge graph.",
        depends_on=("T.OO.1",), supports=("B.SE.2",),
    ),
    Capability(
        "T.AC.2", "Visualization & Exploration", "Technology", "TAC",
        "Interactive visual exploration of the ontology.",
        "Technology", 2,
        "The capability shall offer visual exploration of ontology structure and content.",
        depends_on=("T.AC.1",), supports=("B.SE.1",),
    ),
    Capability(
        "T.AC.3", "Documentation & Publishing", "Technology", "TAC",
        "Generating and publishing human-readable ontology documentation.",
        "Technology", 2,
        "The capability shall publish up-to-date, human-readable documentation for every ontology.",
        depends_on=("T.DA.2",), supports=("B.VP.3",),
    ),
    Capability(
        "T.AC.4", "Ontology-based Access, APIs & Entitlements", "Technology", "TAC",
        "Governed API/data access driven by the ontology.",
        "Technology", 3,
        "The capability shall expose governed, entitlement-aware access to ontology-based data services.",
        depends_on=("T.AC.1", "T.IA.3"), governed_by=("B.SG.5",),
    ),
    Capability(
        "T.AC.5", "Multilingual & Localization Support", "Technology", "TAC",
        "Multilingual labels and locale-aware presentation.",
        "Technology", 4,
        "The capability shall support multilingual labels and locale-aware consumption of the ontology.",
        depends_on=("T.DA.6",),
    ),
    Capability(
        "T.AC.6", "LLM / AI Augmentation", "Technology", "TAC",
        "LLM-assisted authoring, querying and grounding (RAG over the KG).",
        "Technology", 5,
        "The capability shall use the ontology to ground AI/LLM services and accelerate authoring.",
        depends_on=("T.RI.2", "T.AC.1"), supports=("B.VP.1",),
    ),
]

CAPABILITY_BY_ID = {c.id: c for c in CAPABILITIES}


# --------------------------------------------------------------------------- #
# Accessors / validation
# --------------------------------------------------------------------------- #
def capabilities_in(category_id: str) -> list[Capability]:
    return [c for c in CAPABILITIES if c.category == category_id]


def categories_in(domain: str) -> list[Category]:
    return [c for c in CATEGORIES if c.domain == domain]


def validate_model() -> list[str]:
    """Return a list of integrity problems (empty == model is consistent)."""
    problems: list[str] = []
    ids = set(CAPABILITY_BY_ID)
    for c in CAPABILITIES:
        if c.category not in CATEGORY_BY_ID:
            problems.append(f"{c.id}: unknown category {c.category!r}")
        if CATEGORY_BY_ID[c.category].domain != c.domain:
            problems.append(f"{c.id}: domain != category domain")
        if c.maturity_level not in EKGF_LEVELS:
            problems.append(f"{c.id}: bad maturity level {c.maturity_level}")
        if c.ekgf_pillar not in EKGF_PILLARS:
            problems.append(f"{c.id}: bad pillar {c.ekgf_pillar!r}")
        for rel, targets in (("depends_on", c.depends_on),
                             ("supports", c.supports),
                             ("governed_by", c.governed_by)):
            for t in targets:
                if t not in ids:
                    problems.append(f"{c.id}.{rel} -> unknown {t!r}")
    return problems


if __name__ == "__main__":
    problems = validate_model()
    print(f"capabilities : {len(CAPABILITIES)}")
    print(f"categories   : {len(CATEGORIES)}")
    print(f"problems     : {len(problems)}")
    for p in problems:
        print("  -", p)
