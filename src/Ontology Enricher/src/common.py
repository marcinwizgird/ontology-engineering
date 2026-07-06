"""Shared paths and RDF namespaces for the Ontology Enricher."""
import sys
from pathlib import Path
from rdflib import Namespace
from rdflib.namespace import SKOS, RDF, RDFS, OWL, XSD, DCTERMS

# Windows consoles often default to cp1252; force UTF-8 so RDF/OWL output prints.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# ---- Project paths --------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "hbim_business_assets.ttl"
FIBO = ROOT / "fibo" / "fibo_enrichment_excerpt.ttl"
MAPPINGS = ROOT / "mappings" / "hbim_to_fibo_mappings.ttl"
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)

HBIM_ENRICHED = OUTPUT / "hbim_enriched.ttl"
PROTEGE_TTL = OUTPUT / "protege_reasoning_ready.ttl"
PROTEGE_RDF = OUTPUT / "protege_reasoning_ready.rdf"
INFERRED_TTL = OUTPUT / "inferred_closure.ttl"
REPORT_JSON = OUTPUT / "enrichment_report.json"

# ---- Namespaces -----------------------------------------------------------
HBIM = Namespace("https://example.org/hbim/")
CAA = Namespace("https://spec.edmcouncil.org/fibo/ontology/FBC/ProductsAndServices/ClientsAndAccounts/")
FPAS = Namespace("https://spec.edmcouncil.org/fibo/ontology/FBC/ProductsAndServices/FinancialProductsAndServices/")
FSE = Namespace("https://spec.edmcouncil.org/fibo/ontology/FBC/FunctionalEntities/FinancialServicesEntities/")
REL = Namespace("https://spec.edmcouncil.org/fibo/ontology/FND/Relations/Relations/")
CMNS_ID = Namespace("https://www.omg.org/spec/Commons/Identifiers/")
CMNS_ORG = Namespace("https://www.omg.org/spec/Commons/Organizations/")

# FIBO namespaces (for "is this node from FIBO?" checks)
FIBO_NS = (CAA, FPAS, FSE, REL, CMNS_ID, CMNS_ORG)

PREFIXES = {
    "hbim": HBIM, "caa": CAA, "fpas": FPAS, "fse": FSE, "rel": REL,
    "cmns-id": CMNS_ID, "cmns-org": CMNS_ORG,
    "skos": SKOS, "owl": OWL, "rdfs": RDFS, "dct": DCTERMS,
}


def bind_all(graph):
    for prefix, ns in PREFIXES.items():
        graph.bind(prefix, ns)
    return graph


def is_fibo(node) -> bool:
    return any(str(node).startswith(str(ns)) for ns in FIBO_NS)


def is_hbim(node) -> bool:
    return str(node).startswith(str(HBIM))
