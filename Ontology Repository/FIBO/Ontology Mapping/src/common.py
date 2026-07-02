"""Shared paths and RDF namespaces for the Ontology Mapping demo."""
import sys
from pathlib import Path
from rdflib import Namespace

# Windows consoles often default to cp1252; force UTF-8 so RDF output prints.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# ---- Project paths -------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
FIBO_EXCERPT = ROOT / "fibo_excerpt" / "fibo_account_product_excerpt.ttl"
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

COLLIBRA_EXPORT = DATA_DIR / "collibra_account_export.json"
EXTRACTED_FILE = OUTPUT_DIR / "account_terms_extracted.json"
MAPPING_FILE = OUTPUT_DIR / "collibra_to_fibo_mapping.json"
HBIM_TTL = OUTPUT_DIR / "hbim_account.ttl"
HBIM_INFERRED_TTL = OUTPUT_DIR / "hbim_account_inferred.ttl"

# ---- Namespaces ----------------------------------------------------------
# FIBO (real canonical IRIs)
CAA = Namespace("https://spec.edmcouncil.org/fibo/ontology/FBC/ProductsAndServices/ClientsAndAccounts/")
FPAS = Namespace("https://spec.edmcouncil.org/fibo/ontology/FBC/ProductsAndServices/FinancialProductsAndServices/")
FSE = Namespace("https://spec.edmcouncil.org/fibo/ontology/FBC/FunctionalEntities/FinancialServicesEntities/")
REL = Namespace("https://spec.edmcouncil.org/fibo/ontology/FND/Relations/Relations/")
CMNS_ID = Namespace("https://www.omg.org/spec/Commons/Identifiers/")
CMNS_ORG = Namespace("https://www.omg.org/spec/Commons/Organizations/")

# HBIM = "Harmonised Business Information Model" - the bank's internal model
# that we are aligning to FIBO.  This is the namespace we are building.
HBIM = Namespace("https://example.org/hbim/account/")

PREFIXES = {
    "caa": CAA, "fpas": FPAS, "fse": FSE, "rel": REL,
    "cmns-id": CMNS_ID, "cmns-org": CMNS_ORG, "hbim": HBIM,
}


def bind_all(graph):
    """Bind the standard prefixes onto an rdflib Graph for readable output."""
    for prefix, ns in PREFIXES.items():
        graph.bind(prefix, ns)
    return graph
