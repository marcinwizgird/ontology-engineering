"""The *ontology extraction schema*: what LangExtract is asked to find in text.

LangExtract is a span-grounded extractor: for every finding it returns an
``extraction_class``, the **verbatim source text** it came from, a set of
free-form ``attributes``, and — after alignment — the character interval of
that text in the document.  Turning "extract an ontology" into a LangExtract
task therefore means answering one question well:

    *What is the span, and what is the payload?*

The convention used throughout this package is:

* the **span** (``extraction_text``) is always a literal quote from the source.
  It is evidence, not the ontology entity.  Never a paraphrase — LangExtract
  aligns it back to the document, and a paraphrase loses the grounding that
  makes the whole exercise worthwhile.
* the **payload** (``attributes``) carries the normalised ontology commitment:
  the class labels, the property name, the axiom type.  This is what
  ``owl.py`` renders into OWL.

Keeping those apart is what lets every axiom in the generated ontology point
back at the sentence that justifies it (see :mod:`langextract_ontology.owl`).

The six extraction classes below cover the constructs the bottom-up pipeline
of Keet, *Ontology Engineering* (2nd ed.), Ch. 7 asks for — candidate classes,
subsumption, object and data properties, individuals — plus a catch-all for
the constraints ("axiom finding") that Fig. 7.7 marks as an optional step.
"""

from __future__ import annotations

import langextract as lx

# --------------------------------------------------------------------------- #
# Extraction classes
# --------------------------------------------------------------------------- #
CLASS = "class"
SUBSUMPTION = "subsumption"
OBJECT_PROPERTY = "object_property"
DATA_PROPERTY = "data_property"
INDIVIDUAL = "individual"
AXIOM = "axiom"

EXTRACTION_CLASSES: tuple[str, ...] = (
    CLASS,
    SUBSUMPTION,
    OBJECT_PROPERTY,
    DATA_PROPERTY,
    INDIVIDUAL,
    AXIOM,
)

#: Attributes each extraction class is expected to carry.  Used by the prompt,
#: by :mod:`langextract_ontology.owl` when rendering, and by the offline
#: simulator when it fabricates extractions.
ATTRIBUTE_KEYS: dict[str, tuple[str, ...]] = {
    CLASS: ("label", "definition"),
    SUBSUMPTION: ("subclass", "superclass", "pattern"),
    OBJECT_PROPERTY: ("property", "domain", "range"),
    DATA_PROPERTY: ("property", "domain", "datatype"),
    INDIVIDUAL: ("label", "type"),
    AXIOM: ("axiom_type", "subject", "property", "filler", "cardinality", "expression"),
}

#: Values the ``axiom_type`` attribute may take.
AXIOM_TYPES: tuple[str, ...] = (
    "disjointness",
    "cardinality",
    "existential",
    "universal",
    "functional",
    "equivalence",
    "domain_range",
)


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #
PROMPT_DESCRIPTION = """\
You are an ontology engineer performing bottom-up ontology development from
unstructured domain text.  Extract the ontological commitments the text makes,
in order of appearance.

Use these extraction classes:

- class: a candidate OWL class (a universal / type of thing, not a particular).
  attributes: label (singular, lower case, e.g. "centrifugal pump"),
  definition (the defining phrase if the text gives one, else omit).
- subsumption: a statement that one class is a kind of another.
  attributes: subclass, superclass, pattern (the lexico-syntactic pattern that
  licensed it, e.g. "copular definition", "such as", "types of").
- object_property: a relation that holds between two classes.
  attributes: property (lowerCamelCase, e.g. "isTaughtBy"), domain, range.
- data_property: an attribute of a class whose value is a literal.
  attributes: property (lowerCamelCase), domain, datatype (an xsd type such as
  xsd:string, xsd:integer, xsd:decimal, xsd:date, xsd:boolean).
- individual: a named particular (an instance), not a type.
  attributes: label, type (the class it instantiates).
- axiom: a constraint stronger than a plain relation.
  attributes: axiom_type (one of: disjointness, cardinality, existential,
  universal, functional, equivalence, domain_range), subject, property, filler,
  cardinality (a number, when the axiom_type is cardinality),
  expression (the constraint written in OWL Manchester-style syntax).

Rules:

1. extraction_text MUST be an exact, contiguous quote copied from the source
   text. Do not paraphrase, do not normalise, do not re-order words. The quote
   is the evidence for the extraction; the normalised form belongs in the
   attributes.
2. Quote the shortest span that carries the evidence. For a subsumption,
   anchor on the phrase that names the subclass and its parent.
3. Do not invent classes, relations or constraints that the text does not
   state. Grounded recall beats coverage: an ontology you cannot trace back to
   a sentence is worse than a smaller one you can.
4. Do not reuse the same span for two extractions of the same class.
5. Distinguish universals from particulars: "pump" is a class, "P-101" is an
   individual.
"""


# --------------------------------------------------------------------------- #
# Few-shot examples
# --------------------------------------------------------------------------- #
# NOTE: every ``extraction_text`` below is a literal substring of the
# accompanying ``text``.  LangExtract validates this at call time
# (``prompt_validation_level``) and warns when an example cannot be aligned —
# if you edit these, keep the quotes exact.  ``tests.py`` asserts it too.
_EXAMPLE_1_TEXT = (
    "A centrifugal pump is a rotodynamic pump that moves fluid by means of an "
    "impeller. Every pump must have exactly one impeller. Boiler feed pumps "
    "and slurry pumps are types of centrifugal pump. Each pump has a serial "
    "number recorded as text. P-101 is a centrifugal pump."
)

_EXAMPLE_2_TEXT = (
    "A professor is an academic staff member who supervises postgraduate "
    "students. Each course is taught by exactly one lecturer. No student is a "
    "staff member. Every course has a credit value expressed as an integer."
)


def _ex(cls: str, text: str, **attrs: str) -> lx.data.Extraction:
    return lx.data.Extraction(
        extraction_class=cls, extraction_text=text, attributes=dict(attrs)
    )


EXAMPLES: list[lx.data.ExampleData] = [
    lx.data.ExampleData(
        text=_EXAMPLE_1_TEXT,
        extractions=[
            _ex(
                CLASS,
                "centrifugal pump",
                label="centrifugal pump",
                definition="a rotodynamic pump that moves fluid by means of an impeller",
            ),
            _ex(
                SUBSUMPTION,
                "A centrifugal pump is a rotodynamic pump",
                subclass="centrifugal pump",
                superclass="rotodynamic pump",
                pattern="copular definition",
            ),
            _ex(
                OBJECT_PROPERTY,
                "moves fluid by means of an impeller",
                property="movesFluidByMeansOf",
                domain="centrifugal pump",
                range="impeller",
            ),
            _ex(
                AXIOM,
                "Every pump must have exactly one impeller",
                axiom_type="cardinality",
                subject="pump",
                property="hasImpeller",
                filler="impeller",
                cardinality="1",
                expression="pump SubClassOf hasImpeller exactly 1 impeller",
            ),
            _ex(
                SUBSUMPTION,
                "Boiler feed pumps",
                subclass="boiler feed pump",
                superclass="centrifugal pump",
                pattern="types of",
            ),
            _ex(
                SUBSUMPTION,
                "slurry pumps are types of centrifugal pump",
                subclass="slurry pump",
                superclass="centrifugal pump",
                pattern="types of",
            ),
            _ex(
                DATA_PROPERTY,
                "has a serial number recorded as text",
                property="serialNumber",
                domain="pump",
                datatype="xsd:string",
            ),
            _ex(
                INDIVIDUAL,
                "P-101",
                label="P-101",
                type="centrifugal pump",
            ),
        ],
    ),
    lx.data.ExampleData(
        text=_EXAMPLE_2_TEXT,
        extractions=[
            _ex(
                SUBSUMPTION,
                "A professor is an academic staff member",
                subclass="professor",
                superclass="academic staff member",
                pattern="copular definition",
            ),
            _ex(
                OBJECT_PROPERTY,
                "supervises postgraduate students",
                property="supervises",
                domain="professor",
                range="postgraduate student",
            ),
            _ex(
                AXIOM,
                "Each course is taught by exactly one lecturer",
                axiom_type="cardinality",
                subject="course",
                property="isTaughtBy",
                filler="lecturer",
                cardinality="1",
                expression="course SubClassOf isTaughtBy exactly 1 lecturer",
            ),
            _ex(
                AXIOM,
                "No student is a staff member",
                axiom_type="disjointness",
                subject="student",
                filler="staff member",
                expression="student DisjointWith staff member",
            ),
            _ex(
                DATA_PROPERTY,
                "has a credit value expressed as an integer",
                property="creditValue",
                domain="course",
                datatype="xsd:integer",
            ),
        ],
    ),
]
