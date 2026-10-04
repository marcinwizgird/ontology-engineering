"""The Ontology Validation Agent's check catalogue -- the single source of truth.

Every check the deterministic engine will run is declared here *before* it is
implemented. The catalogue is read by three later stages, which is why it is code and
not prose:

* **S1 (deterministic tool)** -- each entry becomes one detector registered under its
  ``id``; ``method`` names the engine that runs it, ``stage`` says when it ships.
* **S2 (evaluation datasets)** -- ``mutation`` names the fault-injection operator that
  must provably trigger the check on a clean seed ontology. The mutated graph is the
  input, the check id is the gold label, so gold labels exist *by construction*.
* **S3/S4 (DSPy, self-evolution)** -- ``id`` is the vocabulary of the scorer's named
  violations and of the experience buffer, and ``adjudication`` says whether an LLM may
  ever touch the finding.

Two rules are encoded in the fields and enforced by ``build_docs.py``:

1. **Candidates are always deterministic.** A check with ``adjudication="llm"`` still
   has a deterministic candidate generator (``method``); the model only labels the
   candidates true/false positive. It never invents a finding outside the candidate set.
2. **Every check that can fail a submission has a mutation operator.** Otherwise its
   recall cannot be measured, and an unmeasured check is an opinion.

Run ``python build_docs.py`` to regenerate CHECK_CATALOGUE.md and validate the catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Vocabularies
# --------------------------------------------------------------------------- #

SEVERITIES = ("blocker", "major", "minor", "info")
"""Ordered most to least severe. ``blocker`` -> reject, ``major``/``minor`` -> revise
(subject to waivers), ``info`` never changes the verdict. See SPECIFICATION.md s.6."""

METHODS = {
    "parse":    "rdflib parser / lexical-space validation of terms and literals",
    "sparql":   "SPARQL SELECT/ASK over the asserted (or closure) graph",
    "graph":    "networkx algorithm over an extracted graph (hierarchy, RBox, imports)",
    "reasoner": "owlrl OWL 2 RL closure; optional DL reasoner (HermiT/Pellet via owlready2, Java-gated)",
    "shacl":    "pyshacl over a data graph and a shapes graph",
    "lexical":  "deterministic string/NLP rules over labels, IRIs and definitions",
    "diff":     "comparison against a baseline version (asserted or entailed)",
}

ADJUDICATION = {
    "none":  "fully decidable; the critic may override any LLM claim about it",
    "llm":   "deterministic candidates, LLM labels each true/false positive (severity capped at major)",
    "human": "reported for a human decision; never auto-resolved",
}

PROFILES = {
    "all":  "every submission",
    "rdfs": "RDFS vocabularies and taxonomies",
    "owl":  "OWL 2 ontologies",
    "dl":   "OWL 2 DL specifically (global restrictions apply)",
    "skos": "SKOS thesauri and concept schemes",
    "abox": "submissions with individuals / instance data",
    "shacl": "submissions shipped with a shapes graph",
    "versioned": "a baseline version is available",
    "cq":   "competency questions are supplied",
}

STAGES = {
    "S1a": "deterministic MVP -- passes the reference conformance suite",
    "S1b": "deterministic full catalogue",
    "S1c": "needs the DL reasoner or the justification engine",
}


@dataclass(frozen=True)
class Family:
    code: str
    title: str
    purpose: str
    oracles: tuple[str, ...] = ()   # reference tools for differential testing (S1 acceptance)


@dataclass(frozen=True)
class Check:
    id: str
    family: str
    title: str
    detects: str
    rationale: str
    method: str
    severity: str
    adjudication: str = "none"
    applies: tuple[str, ...] = ("owl",)
    refs: tuple[str, ...] = ()
    params: dict = field(default_factory=dict)
    mutation: str | None = None         # S2 fault-injection operator that triggers it
    stage: str = "S1b"

    @property
    def deterministic(self) -> bool:
        return self.adjudication == "none"


FAMILIES = [
    Family("SYN", "Syntax & well-formedness",
           "Can the document be read at all, and are its terms and literals lexically valid?",
           oracles=("rdflib", "Apache Jena riot")),
    Family("DECL", "Declarations & namespaces",
           "Is every term declared, owned by the right namespace, and resolvable?",
           oracles=("ROBOT report",)),
    Family("DL", "OWL 2 DL structure & profiles",
           "Does the ontology respect the OWL 2 DL global restrictions, and which profile is it in?",
           oracles=("OWL API profile checker",)),
    Family("RSN", "Reasoning",
           "What does a reasoner say: consistency, satisfiability, unintended entailments.",
           oracles=("HermiT", "ELK", "W3C OWL 2 test cases")),
    Family("SHC", "SHACL",
           "Closed-world conformance of data and of the ontology itself against shapes.",
           oracles=("W3C SHACL test suite", "Apache Jena SHACL")),
    Family("HIER", "Class hierarchy (inheritance)",
           "Is the subsumption hierarchy acyclic, non-redundant, well-shaped and ontologically sound?",
           oracles=("ROBOT report", "OOPS!")),
    Family("PHIER", "Property hierarchy",
           "Is the RBox (sub-property, inverse, chain) coherent with domains and ranges?",
           oracles=("OOPS!",)),
    Family("PROP", "Property semantics",
           "Domains, ranges and characteristics: do they commit to what the author meant?",
           oracles=("OOPS!", "ROBOT report")),
    Family("LEX", "Lexical & annotation",
           "Can a domain expert read and review it: labels, definitions, naming.",
           oracles=("ROBOT report", "OOPS!")),
    Family("SKOS", "SKOS integrity",
           "The SKOS reference integrity conditions plus common thesaurus defects.",
           oracles=("qSKOS", "Skosify")),
    Family("META", "Metadata & governance",
           "Ontology-level metadata, licensing, deprecation discipline.",
           oracles=("ROBOT report", "FOOPS!")),
    Family("ABOX", "Individuals & instance data",
           "Instance-level errors that make the knowledge base inconsistent or meaningless.",
           oracles=("HermiT",)),
    Family("EVO", "Change & versioning",
           "Is this version a safe successor of the previous one?",
           oracles=("ROBOT diff", "OWL API diff")),
    Family("CQ", "Competency questions",
           "Does the ontology answer the questions it was built for?"),
    Family("MOD", "Modelling pitfalls",
           "Design anti-patterns that need judgement to confirm."),
    Family("METRIC", "Profile & metrics",
           "Measurements that plan the run and feed the policy (spectrum, size, expressivity)."),
]

C = Check
CHECKS: list[Check] = [
    # ------------------------------------------------------------------ SYN
    C("SYN-01", "SYN", "Document does not parse",
      "The submission fails to parse in its declared or sniffed serialisation.",
      "Nothing downstream is meaningful; report the parser position and stop the run.",
      "parse", "blocker", applies=("all",), mutation="truncate-statement", stage="S1a"),
    C("SYN-02", "SYN", "Invalid IRI",
      "IRIs containing spaces, illegal characters, or relative IRIs without a base.",
      "Invalid IRIs are silently rewritten or rejected by different tools, so two stores "
      "disagree on what the ontology says.",
      "parse", "major", applies=("all",), mutation="inject-space-in-iri", stage="S1a"),
    C("SYN-03", "SYN", "Ill-typed literal",
      "A typed literal whose lexical form is outside its datatype's lexical space "
      "(e.g. \"abc\"^^xsd:integer).",
      "In OWL 2 DL an ill-typed literal makes the ontology inconsistent; most authors do "
      "not know that.",
      "parse", "blocker", applies=("all",), mutation="corrupt-typed-literal", stage="S1a"),
    C("SYN-04", "SYN", "Malformed language tag",
      "Language tags that are not well-formed BCP 47.",
      "Label lookup by language silently misses them.",
      "parse", "minor", applies=("all",), mutation="corrupt-language-tag"),
    C("SYN-05", "SYN", "Malformed RDF list",
      "rdf:List structures used by owl:unionOf/intersectionOf/oneOf/members/propertyChainAxiom "
      "that are unterminated, branching or cyclic.",
      "The OWL mapping to triples fails; the axiom is dropped or misread without warning.",
      "sparql", "blocker", mutation="break-rdf-list"),
    C("SYN-06", "SYN", "Malformed restriction",
      "owl:Restriction without owl:onProperty, or with zero or several fillers/cardinalities.",
      "The restriction cannot be mapped to an OWL axiom and is ignored by reasoners.",
      "sparql", "blocker", mutation="drop-onProperty", stage="S1a"),
    C("SYN-07", "SYN", "IRI contains file extension",
      "Ontology or term IRIs ending in .owl/.ttl/.rdf.",
      "Ties identity to a serialisation; breaks when the file format changes.",
      "lexical", "minor", applies=("all",), refs=("OOPS P36",), mutation="add-file-extension"),
    C("SYN-08", "SYN", "Empty or padded literal",
      "Labels, definitions or comments that are empty, whitespace-only or padded.",
      "Produces blank UI entries and duplicate-label false negatives.",
      "lexical", "minor", applies=("all",), mutation="blank-label"),

    # ------------------------------------------------------------------ DECL
    C("DECL-01", "DECL", "Undeclared class",
      "An IRI used as a class (subject/object of rdfs:subClassOf, rdf:type object, "
      "restriction filler) that is never declared owl:Class / rdfs:Class.",
      "Its type stays implicit; tools that enumerate the vocabulary cannot see it.",
      "sparql", "blocker", applies=("all",), refs=("OOPS P34",), mutation="drop-class-declaration", stage="S1a"),
    C("DECL-02", "DECL", "Undeclared property",
      "A predicate or restriction property used but never declared as an object, "
      "datatype or annotation property.",
      "A DL parser must guess the property kind, and different parsers guess differently.",
      "sparql", "major", refs=("OOPS P35",), mutation="drop-property-declaration", stage="S1a"),
    C("DECL-03", "DECL", "Missing ontology header",
      "No owl:Ontology node, or more than one in a single document.",
      "Without a header there is nothing to version, import or attach metadata to.",
      "sparql", "minor", refs=("OOPS P38",), mutation="drop-ontology-header", stage="S1a"),
    C("DECL-04", "DECL", "Reserved-vocabulary typo",
      "Terms in the rdf:/rdfs:/owl:/xsd: namespaces that those vocabularies do not define "
      "(owl:class, rdfs:subclassOf, owl:ObjectProperties).",
      "The single most common silent error: the triple parses, means nothing, and the "
      "intended axiom is simply absent.",
      "sparql", "blocker", applies=("all",), mutation="typo-reserved-term", stage="S1a"),
    C("DECL-05", "DECL", "Namespace hijacking",
      "Axioms (not annotations) asserted about terms in namespaces the ontology does not own: "
      "reserved vocabularies, or imported ontologies.",
      "Changes the meaning of somebody else's term for every consumer that imports this "
      "ontology.",
      "sparql", "major", refs=("OOPS P40",), params={"owned_namespaces": "from config"},
      mutation="assert-axiom-on-foreign-term"),
    C("DECL-06", "DECL", "Ambiguous namespace",
      "Own terms minted under several base namespaces, or no stable base at all.",
      "Consumers cannot tell which terms the ontology is authoritative for.",
      "lexical", "minor", refs=("OOPS P39",), mutation="mint-under-second-namespace"),
    C("DECL-07", "DECL", "Unresolvable import",
      "owl:imports targets that cannot be fetched or resolved via the catalogue.",
      "The imports closure, and therefore every reasoning result, is incomplete.",
      "parse", "major", mutation="point-import-to-missing"),
    C("DECL-08", "DECL", "Reference to unimported external term",
      "IRIs from a foreign namespace used in axioms when that ontology is not imported.",
      "The reasoner treats them as fresh, unconstrained symbols.",
      "sparql", "info", mutation="reference-unimported-term"),
    C("DECL-09", "DECL", "Entity declared with conflicting kinds",
      "One IRI typed as two of owl:Class, owl:ObjectProperty, owl:DatatypeProperty, "
      "owl:AnnotationProperty, owl:NamedIndividual without a declared punning intent.",
      "Kind conflicts are either illegal (property kinds) or accidental punning.",
      "sparql", "major", mutation="add-conflicting-type"),

    # ------------------------------------------------------------------ DL
    C("DL-01", "DL", "Illegal property punning",
      "An IRI used both as object and datatype property (or object/annotation).",
      "Forbidden in OWL 2 DL; DL reasoners refuse the ontology.",
      "sparql", "blocker", applies=("dl",), mutation="pun-object-datatype-property"),
    C("DL-02", "DL", "Class used as individual",
      "A class IRI used in an individual position (rdf:type subject, ABox assertion) "
      "without a declared punning intent.",
      "Conflates class and instance levels -- 'is Lion a kind or a thing?'",
      "sparql", "blocker", applies=("all",),
      mutation="type-class-as-individual", stage="S1a"),
    C("DL-03", "DL", "Non-simple property in restricted position",
      "A transitive property (or one with a transitive sub-property or chain) used in a "
      "cardinality restriction, owl:hasSelf, functional/irreflexive/asymmetric/disjoint axioms.",
      "Violates the OWL 2 DL global restrictions; decidability is lost and reasoners reject it.",
      "graph", "blocker", applies=("dl",), mutation="cardinality-on-transitive"),
    C("DL-04", "DL", "Irregular role hierarchy",
      "Property chains and sub-property axioms that violate the RBox regularity condition.",
      "Same as DL-03: the ontology leaves OWL 2 DL.",
      "graph", "blocker", applies=("dl",), mutation="cyclic-property-chain"),
    C("DL-05", "DL", "Annotation property in logical axiom",
      "An annotation property used in a restriction, domain/range axiom or sub-property of "
      "an object property.",
      "Annotations carry no semantics; the author believes a constraint exists that does not.",
      "sparql", "major", mutation="annotation-property-in-restriction"),
    C("DL-06", "DL", "Datatype outside the OWL 2 datatype map",
      "Use of datatypes not in the OWL 2 datatype map (e.g. xsd:date, xsd:duration) in "
      "logical axioms.",
      "Conformant DL reasoners reject or ignore them; xsd:date is the classic surprise.",
      "sparql", "major", applies=("dl",), mutation="use-xsd-date-range"),
    C("DL-07", "DL", "Inverse-functional datatype property",
      "owl:InverseFunctionalProperty on a datatype property.",
      "Not expressible in OWL 2 DL (use a key, owl:hasKey).",
      "sparql", "major", applies=("dl",), mutation="ifp-on-datatype-property"),
    C("DL-08", "DL", "OWL 2 profile report",
      "Which of OWL 2 EL / QL / RL the ontology falls in, and the first construct that "
      "excludes it from each.",
      "Decides which reasoner is complete for it, and therefore how much RSN results mean.",
      "graph", "info", stage="S1a"),

    # ------------------------------------------------------------------ RSN
    C("RSN-01", "RSN", "Ontology inconsistent",
      "The ontology (with imports closure) has no model: owl:Nothing has an instance, or a "
      "clash is derived.",
      "Everything is entailed; no other result can be trusted until this is fixed.",
      "reasoner", "blocker", mutation="assert-individual-in-disjoint-classes", stage="S1a"),
    C("RSN-02", "RSN", "Unsatisfiable class",
      "A named class entailed to be equivalent to owl:Nothing; reported as root or derived "
      "(derived = unsatisfiable only because it uses a root one).",
      "An unsatisfiable class can never have instances -- a modelling error with certainty. "
      "Root/derived separation usually turns 40 findings into 2 causes.",
      "reasoner", "blocker", mutation="disjoint-child-parent", stage="S1a"),
    C("RSN-03", "RSN", "Inferred equivalence collapse",
      "Two named classes entailed equivalent though no equivalence is asserted (includes "
      "collapse caused by subsumption cycles).",
      "Almost never intended; silently merges two categories for every query.",
      "reasoner", "major", refs=("OOPS P31",), mutation="mutual-subclass"),
    C("RSN-04", "RSN", "Unintended domain/range typing",
      "An entity whose inferred type comes only from a property's domain/range and is not "
      "subsumed by any asserted type.",
      "rdfs:domain is an inference rule, not a constraint. This is how 'Locomotive' becomes "
      "a 'Person' because someone used hasDriver on it.",
      "reasoner", "major", adjudication="llm", mutation="use-property-outside-domain"),
    C("RSN-05", "RSN", "Cross-branch inferred subsumption",
      "Subsumptions entailed but not asserted, flagged when they connect different "
      "top-level branches.",
      "Inferred hierarchy changes inside a branch are often the point of defined classes; "
      "across branches they are usually an error.",
      "reasoner", "major", adjudication="llm", mutation="overbroad-equivalent-definition"),
    C("RSN-06", "RSN", "Identity clash",
      "Functional / inverse-functional properties or owl:hasKey entail owl:sameAs between "
      "individuals asserted owl:differentFrom (or under the UNA policy).",
      "A precise diagnosis for one of the most common sources of RSN-01.",
      "reasoner", "blocker", applies=("abox",), mutation="two-values-for-functional-object-property"),
    C("RSN-07", "RSN", "Redundant logical axiom",
      "An asserted axiom that is entailed by the remaining axioms.",
      "Redundancy is not wrong, but it hides intent and breaks when the other axioms change.",
      "reasoner", "minor", mutation="duplicate-entailed-axiom", stage="S1c"),
    C("RSN-08", "RSN", "Reasoning incomplete",
      "The reasoner timed out, or only OWL 2 RL reasoning ran on an ontology outside RL.",
      "A clean RSN result from an incomplete reasoner is not evidence of absence; the report "
      "must say so.",
      "reasoner", "info", stage="S1a"),
    C("RSN-09", "RSN", "Justification for an entailment",
      "Minimal axiom sets (justifications) for each RSN-01/02/03 finding, computed by "
      "black-box expand-shrink inside the STAR locality module of the entailment's signature.",
      "A finding without its justification costs a reviewer an afternoon; with it, a minute.",
      "reasoner", "info", stage="S1c"),

    # ------------------------------------------------------------------ SHC
    C("SHC-01", "SHC", "Ill-formed shapes graph",
      "The supplied shapes graph does not conform to the SHACL-for-SHACL meta-shapes.",
      "A malformed shape validates nothing and reports success.",
      "shacl", "blocker", applies=("shacl",), mutation="corrupt-shape-path"),
    C("SHC-02", "SHC", "Data graph non-conformant",
      "sh:ValidationResult entries from the supplied shapes; severity mapped from sh:severity.",
      "The contract the publishers declared for their own data.",
      "shacl", "major", applies=("shacl",), mutation="violate-sh-minCount", stage="S1a"),
    C("SHC-03", "SHC", "Closed-world reading of OWL axioms violated",
      "Instance data violating shapes auto-derived from the TBox (domain/range -> sh:class, "
      "functional -> sh:maxCount 1, cardinality and someValuesFrom -> sh:minCount/qualified).",
      "OWL infers what SHACL would reject; this check shows both readings side by side.",
      "shacl", "major", applies=("abox",), mutation="omit-required-value"),
    C("SHC-04", "SHC", "Dead shape",
      "A shape whose target class has no declaration or no instances, or whose target is empty.",
      "Coverage that exists on paper only.",
      "shacl", "minor", applies=("shacl",), mutation="retarget-shape-to-missing-class"),
    C("SHC-05", "SHC", "Shape references undeclared term",
      "sh:path / sh:class / sh:datatype pointing to IRIs not in the ontology.",
      "Usually a stale shape after a rename.",
      "sparql", "major", applies=("shacl",), mutation="rename-property-not-shape"),
    C("SHC-06", "SHC", "Shape contradicts ontology",
      "A shape constraint incompatible with the ontology (sh:datatype vs rdfs:range, "
      "sh:maxCount below an OWL min cardinality, sh:class disjoint with the range).",
      "No conforming data can also be a model of the ontology.",
      "sparql", "major", applies=("shacl",), mutation="shape-maxcount-below-owl-min"),
    C("SHC-07", "SHC", "Shape coverage gap",
      "Classes with instances but no shape targeting them, where policy requires coverage.",
      "Reports which part of the data contract is unwritten.",
      "sparql", "info", applies=("shacl",)),
    C("SHC-08", "SHC", "House-rule shape pack violation",
      "TBox-level shapes encoding the organisation's modelling policy (e.g. every class has "
      "an English label and a definition; every object property has domain and range).",
      "Lets governance add rules as data, without code -- the extension point S4 uses.",
      "shacl", "major", applies=("all",), params={"pack": "policy/house_rules.ttl"},
      mutation="violate-house-rule", stage="S1a"),
    C("SHC-09", "SHC", "SHACL-SPARQL constraint error",
      "A sh:sparql constraint that fails to execute.",
      "A crashing constraint must not be read as a passing one.",
      "shacl", "major", applies=("shacl",), mutation="break-sparql-constraint"),

    # ------------------------------------------------------------------ HIER
    C("HIER-01", "HIER", "Subsumption cycle",
      "A strongly connected component of size > 1 in the asserted rdfs:subClassOf graph.",
      "A cycle forces every member equivalent and collapses the taxonomy under a reasoner.",
      "graph", "blocker", applies=("rdfs", "owl"), refs=("OOPS P06",), mutation="add-back-edge", stage="S1a"),
    C("HIER-02", "HIER", "Individual in subsumption axiom",
      "rdfs:subClassOf with a named individual on either side.",
      "A category error: the author meant rdf:type.",
      "sparql", "blocker", applies=("rdfs", "owl"),
      mutation="subclass-of-individual", stage="S1a"),
    C("HIER-03", "HIER", "Subclass of a non-class",
      "rdfs:subClassOf whose object is typed as a property, datatype, ontology, "
      "skos:Concept or skos:ConceptScheme.",
      "The axiom is meaningless or punned; either way not what was meant.",
      "sparql", "blocker", applies=("rdfs", "owl"), mutation="subclass-of-property"),
    C("HIER-04", "HIER", "Redundant asserted subsumption",
      "A ⊑ C asserted when A ⊑ B ⊑ C is also asserted (not in the transitive reduction).",
      "Redundant edges survive refactoring of the middle class and then encode a stale claim.",
      "graph", "minor", applies=("rdfs", "owl"), mutation="add-transitive-shortcut"),
    C("HIER-05", "HIER", "Disjoint with an ancestor",
      "A owl:disjointWith B (or AllDisjointClasses) where A is a descendant of B.",
      "A becomes unsatisfiable; cheap structural diagnosis that names the cause directly.",
      "graph", "blocker", mutation="disjoint-child-parent", stage="S1a"),
    C("HIER-06", "HIER", "Subclass of two disjoint classes",
      "A class with two ancestors that are asserted disjoint.",
      "Unsatisfiable by construction; the structural explanation of an RSN-02 finding.",
      "graph", "blocker", mutation="subclass-of-disjoint-pair"),
    C("HIER-07", "HIER", "Inherited restriction conflict",
      "A subclass restriction incompatible with an inherited one (max n vs min m > n on the "
      "same property; someValuesFrom D under allValuesFrom E with D disjoint E).",
      "Explains unsatisfiability in terms the author wrote, without a DL reasoner.",
      "sparql", "blocker", mutation="tighten-inherited-cardinality"),
    C("HIER-08", "HIER", "Missing sibling disjointness",
      "Sibling classes under a common parent with no disjointness axiom among them.",
      "Without disjointness most modelling errors stay satisfiable and invisible to the "
      "reasoner. Waivable for vocabularies and thesauri (policy W1).",
      "sparql", "minor", refs=("OOPS P10",),
      mutation="drop-disjointness", stage="S1a"),
    C("HIER-09", "HIER", "Asserted polyhierarchy",
      "A primitive class with two or more asserted named superclasses.",
      "Normalisation keeps the asserted hierarchy a tree and lets the reasoner build the "
      "polyhierarchy; asserted multiple inheritance is a maintenance trap. Intentional "
      "multi-axis classification is legitimate, hence adjudication.",
      "graph", "minor", adjudication="llm",
      refs=("Rector 2003 normalisation", "Arp/Smith/Spear 2015 single inheritance"),
      mutation="add-second-parent"),
    C("HIER-10", "HIER", "Orphan class",
      "A class with no asserted superclass other than owl:Thing that is not a declared "
      "top-level class, in an ontology that has a root.",
      "Usually a forgotten placement; unconnected elements are invisible to browsing.",
      "graph", "minor", refs=("OOPS P04",), params={"top_level": "from config or inferred"},
      mutation="detach-subtree"),
    C("HIER-11", "HIER", "Single-child class",
      "A class with exactly one direct subclass.",
      "Either the siblings are missing or the level adds nothing.",
      "graph", "info", mutation="collapse-siblings"),
    C("HIER-12", "HIER", "Excessive depth",
      "Branches deeper than a threshold, or depth far above the ontology's median.",
      "Over-specialisation; a sign of encoding attributes as classes.",
      "graph", "info", refs=("OOPS P17",), params={"max_depth": 12}, mutation="insert-chain"),
    C("HIER-13", "HIER", "Excessive fan-out",
      "A class with more direct subclasses than a threshold.",
      "Missing intermediate categories; also unreviewable.",
      "graph", "info", params={"max_children": 25}, mutation="flatten-subtree"),
    C("HIER-14", "HIER", "Too many roots",
      "More top-level classes than a threshold.",
      "A fragmented taxonomy: the ontology is several ontologies, or lacks an upper level.",
      "graph", "info", params={"max_roots": 10}, mutation="detach-subtree"),
    C("HIER-15", "HIER", "Upper-ontology alignment missing",
      "A top-level class that does not descend from an approved upper-ontology class "
      "(BFO, gist, DOLCE, or the house upper model) when policy requires alignment.",
      "Alignment is what makes two domain ontologies composable.",
      "graph", "major", params={"upper": "from policy"}, mutation="detach-from-upper"),
    C("HIER-16", "HIER", "Is-a overload",
      "Subsumptions whose labels suggest part-of, role, constitution or membership "
      "(Wheel ⊑ Car, Driver ⊑ Locomotive).",
      "Using subClassOf for every relation is the most common taxonomic error by novices.",
      "lexical", "major", adjudication="llm", refs=("OOPS P03",), mutation="partof-as-subclass"),
    C("HIER-17", "HIER", "Instance modelled as class",
      "Leaf classes whose labels are proper names or unique artefacts (Germany, ISO 8601, "
      "the Class 66 locomotive #66001).",
      "Instances modelled as classes cannot carry facts as individuals.",
      "lexical", "minor", adjudication="llm", mutation="individual-as-leaf-class"),
    C("HIER-18", "HIER", "Rigidity violation (OntoClean)",
      "An anti-rigid class (role, phase) subsuming a rigid one, and other OntoClean "
      "meta-property violations, where meta-properties are annotated (or proposed by the "
      "LLM and confirmed by a human).",
      "Student ⊑ Person is fine; Person ⊑ Student is not -- OntoClean makes the difference "
      "checkable.",
      "sparql", "major", adjudication="human", refs=("OntoClean, Guarino & Welty",),
      mutation="rigid-under-antirigid"),
    C("HIER-19", "HIER", "SKOS/OWL hierarchy mixing",
      "skos:broader between owl:Classes, or rdfs:subClassOf between skos:Concepts.",
      "Mixes an associative navigation relation with logical subsumption.",
      "sparql", "major", applies=("rdfs", "owl", "skos"), mutation="broader-between-classes"),
    C("HIER-20", "HIER", "Equivalence plus subsumption",
      "A ≡ B together with A ⊑ B (or B ⊑ A) asserted.",
      "The subsumption is redundant and suggests the author doubted the equivalence.",
      "sparql", "minor", mutation="add-subclass-to-equivalent"),
    C("HIER-21", "HIER", "Indistinguishable siblings",
      "Sibling classes with identical superclass sets and no distinguishing restriction, "
      "definition or annotation (no differentia).",
      "Aristotelian definition: genus plus differentia. Siblings without differentia are "
      "duplicates or undefined.",
      "sparql", "minor", adjudication="llm", refs=("Arp/Smith/Spear 2015",),
      mutation="clone-sibling"),
    C("HIER-22", "HIER", "Child label does not specialise parent",
      "A child whose label's head noun is unrelated to the parent's (Locomotive ⊑ Signal).",
      "Cheap lexical signal of a misplaced class; noisy, hence adjudication.",
      "lexical", "info", adjudication="llm", mutation="move-class-to-wrong-parent"),
    C("HIER-23", "HIER", "Subclass of deprecated class",
      "A non-deprecated class whose asserted parent is owl:deprecated.",
      "Children of a deprecated class inherit its retirement without anyone deciding so.",
      "sparql", "major", mutation="deprecate-parent"),

    # ------------------------------------------------------------------ PHIER
    C("PHIER-01", "PHIER", "Sub-property cycle",
      "Cycle in rdfs:subPropertyOf.",
      "Collapses the properties into equivalents.",
      "graph", "major", applies=("rdfs", "owl"), mutation="property-back-edge"),
    C("PHIER-02", "PHIER", "Sub-property widens domain or range",
      "A sub-property whose domain/range is not subsumed by its super-property's.",
      "Every use of the sub-property infers the super-property's domain anyway; the "
      "declared narrower intent is contradicted or the wider one leaks.",
      "reasoner", "major", applies=("rdfs", "owl"), mutation="widen-subproperty-domain"),
    C("PHIER-03", "PHIER", "Inverse with mismatched domain/range",
      "p owl:inverseOf q where domain(p) is not range(q) or range(p) is not domain(q).",
      "Wrong inverses produce silent type inferences on every use.",
      "sparql", "major", refs=("OOPS P05",), mutation="swap-inverse-range"),
    C("PHIER-04", "PHIER", "Property inverse of itself",
      "p owl:inverseOf p.",
      "Means symmetric; say owl:SymmetricProperty.",
      "sparql", "minor", refs=("OOPS P25",), mutation="self-inverse"),
    C("PHIER-05", "PHIER", "Inverse declared for symmetric property",
      "An inverse declared for a property that is symmetric.",
      "Redundant and usually a sign of confusion about the property's meaning.",
      "sparql", "minor", refs=("OOPS P26",), mutation="inverse-of-symmetric"),
    C("PHIER-06", "PHIER", "Object/datatype property hierarchy mixing",
      "An object property sub-property of a datatype property or vice versa.",
      "Illegal in OWL 2 DL.",
      "sparql", "blocker", applies=("dl",), mutation="object-under-datatype-property"),
    C("PHIER-07", "PHIER", "Missing inverse",
      "Object properties without a declared inverse where policy requires one.",
      "Queries in the reverse direction cannot be written in the vocabulary.",
      "sparql", "info", refs=("OOPS P13",)),
    C("PHIER-08", "PHIER", "Single-property chain",
      "owl:propertyChainAxiom with one element.",
      "That is a sub-property axiom written the hard way.",
      "sparql", "minor", refs=("OOPS P33",), mutation="truncate-chain"),

    # ------------------------------------------------------------------ PROP
    C("PROP-01", "PROP", "Property without domain or range",
      "Object (and datatype) properties lacking rdfs:domain or rdfs:range.",
      "Without them the property carries no commitment and a reasoner infers nothing.",
      "sparql", "minor", applies=("rdfs", "owl"), refs=("OOPS P11",), mutation="drop-domain", stage="S1a"),
    C("PROP-02", "PROP", "Multiple domains or ranges",
      "More than one rdfs:domain (or range) asserted for a property.",
      "Multiple domains mean the intersection; the author almost always meant the union.",
      "sparql", "major", applies=("rdfs", "owl"), refs=("OOPS P19",), mutation="add-second-domain"),
    C("PROP-03", "PROP", "Range kind mismatch",
      "Object property with a datatype range, or datatype property with a class range.",
      "Illegal in OWL 2 DL; meaningless in RDFS.",
      "sparql", "blocker", mutation="datatype-range-on-object-property"),
    C("PROP-04", "PROP", "Conflicting characteristics",
      "Symmetric + asymmetric, reflexive + irreflexive, asymmetric with a reflexive "
      "super-property; functional + transitive flagged as suspicious.",
      "Either unsatisfiable usage or a misunderstanding of the characteristic.",
      "sparql", "major", mutation="symmetric-and-asymmetric"),
    C("PROP-05", "PROP", "Symmetric property with distinct domain and range",
      "A symmetric property whose domain and range differ.",
      "Symmetry forces every subject into the range and vice versa.",
      "sparql", "major", refs=("OOPS P28",), mutation="symmetric-with-distinct-range"),
    C("PROP-06", "PROP", "Suspicious transitivity",
      "Transitive properties whose names denote non-transitive relations (hasParent, "
      "isAdjacentTo, hasDirectPart).",
      "A wrong transitivity floods the closure with false facts.",
      "lexical", "minor", adjudication="llm", refs=("OOPS P29",), mutation="make-parent-transitive"),
    C("PROP-07", "PROP", "Unused property",
      "A declared property never used in an axiom, restriction or assertion.",
      "Dead vocabulary, or a missing restriction.",
      "sparql", "info", mutation="declare-unused-property"),
    C("PROP-08", "PROP", "Wrong equivalent properties",
      "owl:equivalentProperty between properties with incompatible domains/ranges.",
      "The equivalence silently retypes every use of either property.",
      "sparql", "major", refs=("OOPS P27",), mutation="equate-incompatible-properties"),
    C("PROP-09", "PROP", "Literal-valued object property in use",
      "An object property asserted with a literal object, or a datatype property with an IRI.",
      "Data and vocabulary disagree on what the property is.",
      "sparql", "major", applies=("abox",), mutation="literal-on-object-property"),

    # ------------------------------------------------------------------ LEX
    C("LEX-01", "LEX", "Missing label",
      "Classes and properties without rdfs:label or skos:prefLabel.",
      "A domain expert cannot review an IRI.",
      "sparql", "minor", applies=("all",), refs=("OOPS P08",), mutation="drop-label", stage="S1a"),
    C("LEX-02", "LEX", "Missing definition",
      "Classes without skos:definition / IAO:0000115 / rdfs:comment.",
      "The label names the class; only a definition fixes what it means.",
      "sparql", "minor", applies=("all",), refs=("OOPS P08",), mutation="drop-definition", stage="S1a"),
    C("LEX-03", "LEX", "Duplicate label",
      "Two different entities with the same normalised label in the same language.",
      "Ambiguous for every human and every label-based lookup or mapping.",
      "lexical", "major", applies=("all",), refs=("OOPS P32",), mutation="copy-label"),
    C("LEX-04", "LEX", "Missing language tag",
      "Labels/definitions without a language tag where policy requires one.",
      "Multilingual lookup and SKOS S14 checks become undefined.",
      "sparql", "minor", applies=("all",), mutation="strip-language-tag"),
    C("LEX-05", "LEX", "Inconsistent naming convention",
      "Mixed CamelCase / snake_case / kebab-case within one entity kind, or classes not "
      "UpperCamel and properties not lowerCamel.",
      "Naming noise makes the vocabulary look unreviewed and breaks code generation.",
      "lexical", "minor", applies=("all",), refs=("OOPS P22",), mutation="rename-snake-case"),
    C("LEX-06", "LEX", "Label disagrees with IRI",
      "For non-opaque IRIs, a label that shares no tokens with the IRI local name.",
      "Usually a copy-paste error or a renamed concept with a stale IRI.",
      "lexical", "info", applies=("all",), mutation="swap-labels"),
    C("LEX-07", "LEX", "Circular definition",
      "A definition that contains the defined term's own label.",
      "Defines nothing.",
      "lexical", "minor", applies=("all",), adjudication="llm", refs=("OOPS P24",),
      mutation="circularise-definition"),
    C("LEX-08", "LEX", "Plural class name",
      "Class labels in the plural (Trains, Signals).",
      "A class names the kind each instance is: an instance is a Train, not a Trains.",
      "lexical", "minor", adjudication="llm", mutation="pluralise-label"),
    C("LEX-09", "LEX", "Annotation misuse",
      "Definition-length text in labels, labels in comments, IRIs where literals are "
      "expected in annotation values.",
      "Each annotation property has a job; misuse breaks every tool that relies on it.",
      "lexical", "minor", applies=("all",), refs=("OOPS P20",), params={"max_label_chars": 80},
      mutation="definition-in-label"),
    C("LEX-10", "LEX", "Definition not in genus-differentia form",
      "A definition whose genus does not name (a synonym of) one of the class's parents.",
      "A definition and a hierarchy that disagree mean one of them is wrong.",
      "lexical", "info", adjudication="llm", refs=("Arp/Smith/Spear 2015",),
      mutation="replace-genus-in-definition"),
    C("LEX-11", "LEX", "Language coverage gap",
      "Entities without labels in every required language.",
      "The ontology is unusable for part of its audience.",
      "sparql", "info", applies=("all",), params={"languages": ["en"]}, mutation="drop-translation"),
    C("LEX-12", "LEX", "Unexpanded acronym",
      "All-caps labels without an expanded synonym or definition.",
      "Acronyms are ambiguous across departments (ETCS, ATO, PIS).",
      "lexical", "info", applies=("all",), mutation="acronymise-label"),

    # ------------------------------------------------------------------ SKOS
    C("SKOS-01", "SKOS", "Concept and ConceptScheme overlap (S9)",
      "A resource typed both skos:Concept and skos:ConceptScheme.",
      "Violates SKOS integrity condition S9.",
      "sparql", "blocker", applies=("skos",), refs=("SKOS S9",), mutation="type-concept-as-scheme"),
    C("SKOS-02", "SKOS", "Label kind clash (S13)",
      "The same literal as prefLabel and altLabel/hiddenLabel of one concept.",
      "Violates SKOS integrity condition S13.",
      "sparql", "minor", applies=("skos",), refs=("SKOS S13",), mutation="pref-as-alt"),
    C("SKOS-03", "SKOS", "Several prefLabels per language (S14)",
      "More than one skos:prefLabel per language tag on one concept.",
      "Violates SKOS integrity condition S14.",
      "sparql", "major", applies=("skos",), refs=("SKOS S14",), mutation="add-second-preflabel"),
    C("SKOS-04", "SKOS", "Related and broader clash (S27)",
      "skos:related between concepts also linked by skos:broaderTransitive.",
      "Violates SKOS integrity condition S27.",
      "sparql", "major", applies=("skos",), refs=("SKOS S27",), mutation="relate-ancestor"),
    C("SKOS-05", "SKOS", "Broader cycle",
      "Cycle in skos:broader.",
      "Legal in SKOS, nonsensical for navigation, and a taxonomy-level cycle under any "
      "conversion to OWL.",
      "graph", "major", applies=("skos",), mutation="broader-back-edge", stage="S1a"),
    C("SKOS-06", "SKOS", "Orphan concept",
      "A concept in no scheme, or with neither broader nor topConceptOf.",
      "Unreachable when browsing the scheme.",
      "sparql", "minor", applies=("skos",), mutation="detach-concept"),
    C("SKOS-07", "SKOS", "Top concept with broader",
      "skos:topConceptOf a scheme while having a broader concept in the same scheme.",
      "Contradicts the scheme's declared entry points.",
      "sparql", "minor", applies=("skos",), mutation="broader-on-top-concept"),
    C("SKOS-08", "SKOS", "Mapping relation clash (S46)",
      "skos:exactMatch together with broadMatch or relatedMatch between the same pair.",
      "Violates SKOS integrity condition S46.",
      "sparql", "major", applies=("skos",), refs=("SKOS S46",), mutation="exact-and-broad-match"),
    C("SKOS-09", "SKOS", "Exact match within scheme",
      "skos:exactMatch between two concepts of the same scheme.",
      "Mapping relations are for links across schemes; inside one it is a duplicate concept.",
      "sparql", "minor", applies=("skos",), mutation="exact-match-same-scheme"),
    C("SKOS-10", "SKOS", "Duplicate notation",
      "Two concepts with the same skos:notation and datatype in one scheme.",
      "Notations are codes; duplicated codes break every system that keys on them.",
      "sparql", "major", applies=("skos",), mutation="copy-notation"),

    # ------------------------------------------------------------------ META
    C("META-01", "META", "Missing ontology metadata",
      "No title, description, creator, version info/versionIRI or license on the ontology header.",
      "A registry cannot catalogue, cite or legally reuse an ontology without them.",
      "sparql", "minor", applies=("all",), refs=("OOPS P41",),
      params={"required": ["dcterms:title", "dcterms:license", "owl:versionIRI"]},
      mutation="drop-license", stage="S1a"),
    C("META-02", "META", "Deprecated without replacement",
      "owl:deprecated true without dcterms:isReplacedBy / IAO 'term replaced by'.",
      "Consumers cannot migrate.",
      "sparql", "minor", applies=("all",), mutation="deprecate-without-replacement"),
    C("META-03", "META", "Deprecated entity in use",
      "A deprecated entity referenced by non-deprecated axioms or data.",
      "Deprecation that nothing respects is documentation, not governance.",
      "sparql", "major", applies=("all",), mutation="use-deprecated-term"),
    C("META-04", "META", "Version IRI not advanced",
      "owl:versionIRI identical to the baseline's, or not matching the version pattern.",
      "Two different documents under one version identifier.",
      "diff", "minor", applies=("versioned",), mutation="keep-version-iri"),

    # ------------------------------------------------------------------ ABOX
    C("ABOX-01", "ABOX", "Untyped individual",
      "A named individual with no rdf:type other than owl:NamedIndividual.",
      "Carries no meaning a reasoner or query can use.",
      "sparql", "minor", applies=("abox",), mutation="drop-individual-type"),
    C("ABOX-02", "ABOX", "Individual typed with undeclared class",
      "rdf:type to an IRI not declared as a class.",
      "Usually a typo in a class name.",
      "sparql", "major", applies=("abox",), mutation="typo-type"),
    C("ABOX-03", "ABOX", "Individual in disjoint classes",
      "An individual asserted or inferred to be in two disjoint classes.",
      "Inconsistency; the precise diagnosis of an RSN-01.",
      "reasoner", "blocker", applies=("abox",), mutation="assert-individual-in-disjoint-classes"),
    C("ABOX-04", "ABOX", "Value outside property range",
      "A literal whose datatype or facet violates the data property's range.",
      "Inconsistent in OWL 2 DL; rejected by any downstream schema.",
      "sparql", "major", applies=("abox",), mutation="wrong-datatype-value"),
    C("ABOX-05", "ABOX", "Several values for a functional property",
      "Two distinct literals for a functional datatype property (inconsistent), or two "
      "individuals for a functional object property (forces sameAs, see RSN-06).",
      "Functional means 'at most one'; data that disagrees is wrong or the axiom is.",
      "sparql", "major", applies=("abox",), mutation="two-values-for-functional-property"),

    # ------------------------------------------------------------------ EVO
    C("EVO-01", "EVO", "Entity removed without deprecation",
      "An entity in the baseline that is absent now and was not deprecated first.",
      "A breaking change for every consumer that references it.",
      "diff", "major", applies=("versioned",), mutation="delete-class"),
    C("EVO-02", "EVO", "Entailment lost",
      "Subsumptions entailed by the baseline that are no longer entailed.",
      "Queries that used to return results stop returning them, silently.",
      "diff", "major", applies=("versioned",), mutation="drop-subclass-axiom", stage="S1c"),
    C("EVO-03", "EVO", "New cross-branch entailment",
      "Subsumptions entailed now but not by the baseline, across top-level branches.",
      "A semantic change nobody asserted directly.",
      "diff", "info", applies=("versioned",), mutation="overbroad-equivalent-definition", stage="S1c"),
    C("EVO-04", "EVO", "Rename without redirect",
      "A label that moved to a new IRI with the old IRI gone and no equivalence/replacement.",
      "Identity broken for a cosmetic change.",
      "diff", "major", applies=("versioned",), mutation="rename-iri"),
    C("EVO-05", "EVO", "Semantic diff summary",
      "Added/removed axioms and entailments by kind.",
      "The reviewer's starting point for a version bump.",
      "diff", "info", applies=("versioned",)),

    # ------------------------------------------------------------------ CQ
    C("CQ-01", "CQ", "Competency question test failure",
      "A CQ formalised as SPARQL ASK/SELECT (Themis-style) with an expected result that fails.",
      "The ontology does not do what its requirements say.",
      "sparql", "major", applies=("cq",), mutation="drop-cq-required-axiom"),
    C("CQ-02", "CQ", "Competency question vocabulary gap",
      "CQ terms with no matching label or synonym in the ontology.",
      "The question cannot even be formalised against the vocabulary.",
      "lexical", "major", applies=("cq",), adjudication="llm", mutation="drop-cq-term"),
    C("CQ-03", "CQ", "Answerable only under reasoning",
      "CQs that fail on the asserted graph and pass on the closure.",
      "Consumers without a reasoner get a different answer -- worth stating.",
      "reasoner", "info", applies=("cq",)),

    # ------------------------------------------------------------------ MOD
    C("MOD-01", "MOD", "Synonyms as separate classes",
      "Classes whose labels/altLabels are synonyms or near-duplicates and that are not "
      "declared equivalent.",
      "Two IRIs for one concept split the data between them.",
      "lexical", "major", adjudication="llm", refs=("OOPS P02", "OOPS P30"),
      mutation="duplicate-class-with-synonym"),
    C("MOD-02", "MOD", "Merged concepts",
      "Class labels joining two concepts with and/or (CarsAndTrucks, TrainOrBus).",
      "One class, two meanings; the 'and' is usually a union that should be a parent.",
      "lexical", "minor", adjudication="llm", refs=("OOPS P07",), mutation="merge-two-classes"),
    C("MOD-03", "MOD", "Miscellaneous class",
      "Classes named Other / Misc / General / Unknown among siblings.",
      "A bucket for what the author did not classify; it has no definition.",
      "lexical", "minor", adjudication="llm", refs=("OOPS P21",), mutation="add-other-class"),
    C("MOD-04", "MOD", "Attribute encoded in names",
      "Values or n-ary context baked into class or property names (hasSalary2024, "
      "RedLocomotive vs BlueLocomotive).",
      "Needs a property, a value partition or an n-ary relation pattern instead.",
      "lexical", "info", adjudication="llm", mutation="encode-value-in-name"),
    C("MOD-05", "MOD", "Polysemous element",
      "One class used with two incompatible senses across its axioms and annotations.",
      "Every query over it returns a mixture.",
      "lexical", "minor", adjudication="human", refs=("OOPS P01",)),

    # ------------------------------------------------------------------ METRIC
    C("METRIC-01", "METRIC", "Spectrum position and declared-level mismatch",
      "Measured position on the vocabulary -> taxonomy -> thesaurus -> formal-ontology "
      "spectrum below the level declared by the publisher.",
      "A submission that over-promises its formality is sent back for revision.",
      "sparql", "major", applies=("all",), mutation="strip-formal-axioms", stage="S1a"),
    C("METRIC-02", "METRIC", "Size and expressivity profile",
      "Counts (classes, properties, axioms by type, individuals) and DL expressivity "
      "(e.g. ALCHIQ(D)).",
      "Feeds the planner's cost model: which reasoner, which budget.",
      "graph", "info", applies=("all",), stage="S1a"),
    C("METRIC-03", "METRIC", "Disconnected components",
      "More than one weakly connected component in the class/property graph.",
      "Unconnected islands are either separate ontologies or forgotten links.",
      "graph", "minor", applies=("all",), refs=("OOPS P04",), mutation="detach-subtree"),
    C("METRIC-04", "METRIC", "Annotation and axiom richness",
      "Ratios: labelled, defined, restricted, disjoint-covered classes (OQuaRE-style).",
      "Trends across versions are more telling than any single threshold.",
      "sparql", "info", applies=("all",)),
]
del C

CHECK_BY_ID = {c.id: c for c in CHECKS}
