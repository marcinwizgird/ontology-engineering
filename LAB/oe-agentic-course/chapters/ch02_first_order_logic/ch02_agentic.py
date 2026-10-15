"""Chapter 2 problem-set support — formalising an access policy, and checking it.

Provided code for ``04_assignment.ipynb``. The student builds the grader and the
Claude formaliser in the notebook, and optimises it with GEPA; this module supplies
what a real project would already have in its codebase:

* the **policy corpus** — 48 English policy statements, a fixed predicate
  vocabulary, gold formulas, and a train / dev / test split (16 / 16 / 16) by item;
* a **transfer set** — the requirement sentences of SIP's demo, over a fleet
  vocabulary (Part D);
* **semantic comparison** (:func:`equivalent`) and **mistake naming**
  (:func:`diagnose`) on top of Chapter 2's model checker;
* the **guidelines** a formalisation scorer reports (:data:`POLICY_RULEBOOK`);

The original problem set's Part D (a compliance agent that proves its verdicts,
and proof search as an MDP) moves to the chapters that introduce those layers:
tool-calling agents in Chapter 3, MDPs in Chapter 6.

Why the grader is unusual and worth dwelling on: most LLM evaluation is stuck
with string overlap or a judge because the task has no decision procedure.
Formalisation has one — two formulas mean the same thing when they have the same
models — so Chapter 2's own semantics *is* the grader.
"""

from __future__ import annotations

import functools
import itertools
import json
from dataclasses import dataclass, field

import ch02_toolkit as fol

__all__ = [
    "VOCABULARY", "vocabulary_text", "POLICY_ITEMS", "build_dataset",
    "SIP_VOCABULARY", "SIP_REQUIREMENTS", "sip_vocabulary_text", "build_sip_dataset",
    "equivalent", "diagnose", "model_space_bits", "POLICY_RULEBOOK",
]


# --------------------------------------------------------------------------- #
# The vocabulary the formaliser must use
# --------------------------------------------------------------------------- #
#: predicate -> (arity, gloss). The gold formulas use exactly these names.
VOCABULARY: dict[str, tuple[int, str]] = {
    "Clinician": (1, "x is a clinician"),
    "Nurse": (1, "x is a nurse"),
    "Employee": (1, "x is an employee of the hospital"),
    "Contractor": (1, "x is a contractor"),
    "Auditor": (1, "x is an auditor"),
    "External": (1, "x is external to the hospital"),
    "Patient": (1, "x is a patient"),
    "Consented": (1, "x (a patient) has given research consent"),
    "Record": (1, "x is a health record"),
    "Sensitive": (1, "x (a record) is marked sensitive"),
    "Treats": (2, "x treats y"),
    "About": (2, "record x is about patient y"),
    "CanAccess": (2, "x can access record y"),
    "Supervises": (2, "x supervises y"),
    # added with the second batch of statements (research use, minors and guardians)
    "Researcher": (1, "x is a researcher"),
    "Approved": (1, "x (a researcher) is approved by the review board"),
    "Minor": (1, "x (a patient) is a minor"),
    "Guardian": (2, "x is the legal guardian of y"),
}


def vocabulary_text() -> str:
    """The vocabulary as the formaliser sees it: one predicate per line."""
    lines = []
    for name, (arity, gloss) in VOCABULARY.items():
        args = "x" if arity == 1 else "x, y"
        lines.append(f"{name}({args}): {gloss}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# The policy corpus
# --------------------------------------------------------------------------- #
#: (id, split, statement, gold formula). Split is fixed by item and balanced by
#: phenomenon, so no split can be solved by memorising a sibling item.
POLICY_ITEMS: list[tuple[str, str, str, str]] = [
    # --- train ---------------------------------------------------------------
    ("clinicians-are-employees", "train", "Every clinician is an employee.",
     "forall x (Clinician(x) -> Employee(x))"),
    ("some-auditor-external", "train", "Some auditor is external.",
     "exists x (Auditor(x) & External(x))"),
    ("no-contractor-clinician", "train", "No contractor is a clinician.",
     "forall x (Contractor(x) -> ~Clinician(x))"),
    ("records-about-patients", "train", "Every record is about some patient.",
     "forall x (Record(x) -> exists y (Patient(y) & About(x, y)))"),
    ("someone-supervises-all-nurses", "train", "There is someone who supervises every nurse.",
     "exists x forall y (Nurse(y) -> Supervises(x, y))"),
    ("only-clinicians-access", "train", "Only clinicians can access records.",
     "forall x forall y ((Record(y) & CanAccess(x, y)) -> Clinician(x))"),
    ("not-all-employees-clinicians", "train", "Not every employee is a clinician.",
     "~forall x (Employee(x) -> Clinician(x))"),
    ("no-self-treatment", "train", "No clinician treats themselves.",
     "forall x (Clinician(x) -> ~Treats(x, x))"),
    # --- dev -----------------------------------------------------------------
    ("nurses-are-clinicians", "dev", "All nurses are clinicians.",
     "forall x (Nurse(x) -> Clinician(x))"),
    ("some-record-sensitive", "dev", "Some records are sensitive.",
     "exists x (Record(x) & Sensitive(x))"),
    ("contractors-no-access", "dev", "Contractors cannot access any record.",
     "forall x (Contractor(x) -> ~exists y (Record(y) & CanAccess(x, y)))"),
    ("clinicians-treat-someone", "dev", "Every clinician treats some patient.",
     "forall x (Clinician(x) -> exists y (Patient(y) & Treats(x, y)))"),
    ("every-nurse-supervised", "dev", "Every nurse is supervised by someone.",
     "forall y (Nurse(y) -> exists x Supervises(x, y))"),
    ("auditor-external-or-employee", "dev", "Every auditor is either external or an employee.",
     "forall x (Auditor(x) -> (External(x) | Employee(x)))"),
    ("some-nurse-treats-nobody", "dev", "Some nurse treats no patient.",
     "exists x (Nurse(x) & ~exists y (Patient(y) & Treats(x, y)))"),
    ("supervisors-of-nurses-clinicians", "dev", "Anyone who supervises a nurse is a clinician.",
     "forall x forall y ((Supervises(x, y) & Nurse(y)) -> Clinician(x))"),
    # --- test ----------------------------------------------------------------
    ("contractors-not-employees", "test", "No contractor is an employee.",
     "forall x (Contractor(x) -> ~Employee(x))"),
    ("some-patient-consented", "test", "At least one patient has given research consent.",
     "exists x (Patient(x) & Consented(x))"),
    ("external-auditors-no-sensitive", "test",
     "No external auditor can access a sensitive record.",
     "forall x ((Auditor(x) & External(x)) -> ~exists y (Record(y) & Sensitive(y) & CanAccess(x, y)))"),
    ("patients-have-records", "test", "Every patient has at least one record about them.",
     "forall y (Patient(y) -> exists x (Record(x) & About(x, y)))"),
    ("one-clinician-treats-all", "test", "Some clinician treats every patient.",
     "exists x (Clinician(x) & forall y (Patient(y) -> Treats(x, y)))"),
    ("only-consented-sensitive", "test",
     "Sensitive records exist only about patients who have consented.",
     "forall x forall y ((Record(x) & Sensitive(x) & About(x, y)) -> Consented(y))"),
    ("auditor-external-iff-not-employee", "test",
     "An auditor is external exactly when they are not an employee.",
     "forall x (Auditor(x) -> (External(x) <-> ~Employee(x)))"),
    ("every-patient-treated", "test", "Every patient is treated by some clinician.",
     "forall y (Patient(y) -> exists x (Clinician(x) & Treats(x, y)))"),
    # --- second batch: modelled on HIPAA Privacy Rule provisions (research use and
    # authorisation, personal representatives of minors, minimum necessary). Paraphrased
    # for this vocabulary, not quoted; each split gets eight, mixed by phenomenon.
    ("researchers-need-consent", "train",
     "A researcher can access a record only if the patient it is about has consented.",
     "forall x forall y forall z ((Researcher(x) & CanAccess(x, y) & About(y, z)) -> Consented(z))"),
    ("unapproved-researchers-no-access", "train",
     "No researcher who is not approved can access any record.",
     "forall x ((Researcher(x) & ~Approved(x)) -> ~exists y (Record(y) & CanAccess(x, y)))"),
    ("minors-have-guardians", "train", "Every patient who is a minor has a guardian.",
     "forall x ((Patient(x) & Minor(x)) -> exists y Guardian(y, x))"),
    ("some-patient-minor", "train", "Some patients are minors.",
     "exists x (Patient(x) & Minor(x))"),
    ("nobody-supervises-themselves", "train", "Nobody supervises themselves.",
     "forall x ~Supervises(x, x)"),
    ("records-about-minors-sensitive", "train", "Every record about a minor is sensitive.",
     "forall x forall y ((Record(x) & About(x, y) & Minor(y)) -> Sensitive(x))"),
    ("record-nobody-accesses", "train", "There is a record that nobody can access.",
     "exists x (Record(x) & ~exists y CanAccess(y, x))"),
    ("contractors-supervised-by-employees", "train",
     "Every contractor is supervised by some employee.",
     "forall x (Contractor(x) -> exists y (Employee(y) & Supervises(y, x)))"),
    ("guardians-access-records", "dev",
     "A guardian of a patient can access every record about that patient.",
     "forall x forall y forall z ((Guardian(x, y) & Patient(y) & Record(z) & About(z, y)) "
     "-> CanAccess(x, z))"),
    ("external-access-only-auditors", "dev",
     "No external party can access a record unless they are an auditor.",
     "forall x forall y ((External(x) & Record(y) & CanAccess(x, y)) -> Auditor(x))"),
    ("approved-researchers-staff", "dev",
     "Every approved researcher is an employee or a contractor.",
     "forall x ((Researcher(x) & Approved(x)) -> (Employee(x) | Contractor(x)))"),
    ("not-all-records-sensitive", "dev", "Not every record is sensitive.",
     "~forall x (Record(x) -> Sensitive(x))"),
    ("treating-implies-clinician", "dev", "Whoever treats a patient is a clinician.",
     "forall x forall y ((Treats(x, y) & Patient(y)) -> Clinician(x))"),
    ("auditors-treat-nobody", "dev", "No auditor treats any patient.",
     "forall x (Auditor(x) -> ~exists y (Patient(y) & Treats(x, y)))"),
    ("some-approved-researcher-not-employee", "dev",
     "Some approved researcher is not an employee.",
     "exists x (Researcher(x) & Approved(x) & ~Employee(x))"),
    ("patient-treated-by-every-nurse", "dev",
     "There is a patient whom every nurse treats.",
     "exists y (Patient(y) & forall x (Nurse(x) -> Treats(x, y)))"),
    ("nurses-treating-minors-supervised", "test",
     "Every nurse who treats a minor is supervised by a clinician.",
     "forall x ((Nurse(x) & exists y (Minor(y) & Treats(x, y))) "
     "-> exists z (Clinician(z) & Supervises(z, x)))"),
    ("sensitive-records-consented", "test",
     "Every sensitive record is about some patient who has consented.",
     "forall x ((Record(x) & Sensitive(x)) -> exists y (Patient(y) & Consented(y) & About(x, y)))"),
    ("contractor-supervisors-employees", "test",
     "Anyone who supervises a contractor is an employee.",
     "forall x forall y ((Supervises(x, y) & Contractor(y)) -> Employee(x))"),
    ("minors-not-employees", "test", "No minor is an employee.",
     "forall x (Minor(x) -> ~Employee(x))"),
    ("guardians-of-minors-access-something", "test",
     "Every guardian of a minor patient can access some record.",
     "forall x forall y ((Guardian(x, y) & Minor(y) & Patient(y)) "
     "-> exists z (Record(z) & CanAccess(x, z)))"),
    ("sensitive-access-clinician-or-researcher", "test",
     "Whoever can access a sensitive record is a clinician or an approved researcher.",
     "forall x forall y ((Record(y) & Sensitive(y) & CanAccess(x, y)) "
     "-> (Clinician(x) | (Researcher(x) & Approved(x))))"),
    ("clinician-treats-no-minor", "test", "Some clinician treats no minor.",
     "exists x (Clinician(x) & ~exists y (Minor(y) & Treats(x, y)))"),
    ("consenting-minors-have-internal-guardian", "test",
     "Every minor patient who has consented has a guardian who is not external.",
     "forall x ((Patient(x) & Minor(x) & Consented(x)) -> exists y (Guardian(y, x) & ~External(y)))"),
]


def build_dataset(split: str = "all"):
    """The corpus as ``dspy.Example`` rows (inputs: statement, vocabulary)."""
    import dspy

    vocab = vocabulary_text()
    rows = [
        dspy.Example(id=item_id, split=item_split, statement=text, vocabulary=vocab,
                     gold_formula=formula).with_inputs("statement", "vocabulary")
        for item_id, item_split, text, formula in POLICY_ITEMS
    ]
    return rows if split == "all" else [r for r in rows if r.split == split]


# --------------------------------------------------------------------------- #
# A transfer set from the Semantic Intelligence Platform (Part D)
# --------------------------------------------------------------------------- #
#: The requirement sentences of SIP's end-to-end demo (``sip/semantic_intelligence/
#: demo.py``: the project brief and the source document), with gold formulas over a
#: fleet vocabulary. A program tuned on hospital policy has never seen this domain.
SIP_VOCABULARY: dict[str, tuple[int, str]] = {
    "Vehicle": (1, "x is a vehicle"),
    "Car": (1, "x is a car"),
    "Truck": (1, "x is a truck"),
    "Wheel": (1, "x is a wheel"),
    "Engine": (1, "x is an engine"),
    "DieselEngine": (1, "x is a diesel engine"),
    "ElectricMotor": (1, "x is an electric motor"),
    "Manufacturer": (1, "x is a manufacturer"),
    "Country": (1, "x is a country"),
    "HasPart": (2, "x has y as a part"),
    "MadeBy": (2, "x is made by y"),
    "HasCountry": (2, "x has y as its country"),
    "Powers": (2, "x powers y"),
}

SIP_REQUIREMENTS: list[tuple[str, str, str]] = [
    ("vehicle-has-wheels", "Every vehicle has one or more wheels.",
     "forall x (Vehicle(x) -> exists y (Wheel(y) & HasPart(x, y)))"),
    ("manufacturer-has-country", "Every manufacturer has a country.",
     "forall x (Manufacturer(x) -> exists y (Country(y) & HasCountry(x, y)))"),
    ("car-is-vehicle", "A car is a kind of vehicle.", "forall x (Car(x) -> Vehicle(x))"),
    ("truck-is-vehicle", "A truck is a kind of vehicle.", "forall x (Truck(x) -> Vehicle(x))"),
    ("vehicle-has-engine", "Every vehicle has an engine.",
     "forall x (Vehicle(x) -> exists y (Engine(y) & HasPart(x, y)))"),
    ("vehicle-made-by-manufacturer", "Every vehicle is made by a manufacturer.",
     "forall x (Vehicle(x) -> exists y (Manufacturer(y) & MadeBy(x, y)))"),
    ("engine-kinds", "Engines, such as diesel engines and electric motors, power vehicles.",
     "forall x ((DieselEngine(x) | ElectricMotor(x)) -> Engine(x)) & "
     "forall x (Engine(x) -> exists y (Vehicle(y) & Powers(x, y)))"),
]


def sip_vocabulary_text() -> str:
    return "\n".join(f"{name}({'x' if arity == 1 else 'x, y'}): {gloss}"
                     for name, (arity, gloss) in SIP_VOCABULARY.items())


def build_sip_dataset():
    """SIP's requirements as ``dspy.Example`` rows, shaped like the policy rows."""
    import dspy

    vocab = sip_vocabulary_text()
    return [dspy.Example(id=i, split="sip", statement=text, vocabulary=vocab,
                         gold_formula=formula).with_inputs("statement", "vocabulary")
            for i, text, formula in SIP_REQUIREMENTS]


# --------------------------------------------------------------------------- #
# Semantic comparison — the grader's core
# --------------------------------------------------------------------------- #
def model_space_bits(formulas, size: int) -> int:
    """How many ground atoms a model of this size must decide.

    The number of models the checker enumerates is ``2 ** bits`` — which is why
    the grader refuses (rather than hangs on) a formula with too big a signature.
    """
    signature: dict[str, int] = {}
    for f in formulas:
        signature.update(fol.predicates(f))
    return sum(size ** arity for arity in signature.values())


#: What the vocabulary itself implies. "About(x, y): record x is about patient y" makes
#: x a record and y a patient, so an answer that writes ``Patient(y)`` next to
#: ``About(x, y)`` says nothing the gold formula does not. Equivalence is decided
#: *modulo* these axioms (the first live run marked such answers wrong).
TYPING = {
    "About": "forall x forall y (About(x, y) -> (Record(x) & Patient(y)))",
}


def _typing_for(*formulas) -> list:
    used = set()
    for f in formulas:
        used |= set(fol.predicates(f))
    return [fol.parse(TYPING[p]) for p in sorted(used) if p in TYPING]


@functools.lru_cache(maxsize=4096)
def _equivalent_cached(a_text: str, b_text: str, max_size: int) -> bool:
    a, b = fol.parse(a_text), fol.parse(b_text)
    background = _typing_for(a, b)
    return (fol.entails(background + [a], b, max_size)[0]
            and fol.entails(background + [b], a, max_size)[0])


def equivalent(a, b, max_size: int = 2) -> bool:
    """Do two closed formulas have the same models (among those satisfying the
    vocabulary's :data:`TYPING` axioms) on every domain up to ``max_size``?

    Two-way finite entailment. Not full logical equivalence (undecidable), but
    sound in the direction that matters for grading: a *difference* found is a
    real difference, witnessed by an explicit model. Memoised on the normalised
    text, because an optimiser grades the same answer many times.
    """
    return _equivalent_cached(fol.to_string(a), fol.to_string(b), max_size)


def diagnose(predicted, gold) -> str | None:
    """Name the classic mistake, when the shape of the error is recognisable.

    Returning a *named* pitfall rather than "wrong" is what lets a GEPA metric
    tell the optimiser something it can act on.
    """
    match (predicted, gold):
        case (fol.Not(fol.ForAll(_, _)), fol.ForAll(_, fol.Implies(_, fol.Not(_)))):
            return "negation-scope"
        case (fol.ForAll(_, fol.And(_, _)), fol.ForAll(_, fol.Implies(_, _))):
            return "universal-uses-implication"
        case (fol.Exists(_, fol.Implies(_, _)), fol.Exists(_, fol.And(_, _))):
            return "existential-uses-conjunction"
        case (fol.Exists(_, fol.ForAll(_, _)), fol.ForAll(_, fol.Exists(_, _))):
            return "quantifier-order-matters"
        case (fol.ForAll(_, fol.Exists(_, _)), fol.Exists(_, fol.ForAll(_, _))):
            return "quantifier-order-matters"
    return None


def _rulebook():
    from agentlab.evaluation import Rule, RuleBook

    return RuleBook([
        Rule("emit-parseable-formula",
             "Answer with one formula in the ASCII syntax -- forall/exists, ~ & | -> <->, "
             "predicates written Name(arg, ...) -- and nothing else: no prose, no "
             "Unicode symbols, no code fences."),
        Rule("close-every-variable",
             "Bind every variable with a quantifier; a free variable leaves the "
             "statement without a truth value."),
        Rule("use-the-vocabulary",
             "Use only the predicates listed in the vocabulary, with exactly the "
             "listed arity and argument order; do not invent synonyms."),
        Rule("universal-uses-implication",
             "Translate 'every/all X is Y' as forall x (X(x) -> Y(x)); a conjunction "
             "under a universal claims everything in the domain is an X."),
        Rule("existential-uses-conjunction",
             "Translate 'some X is Y' as exists x (X(x) & Y(x)); an implication under "
             "an existential is satisfied by any non-X and asserts almost nothing."),
        Rule("quantifier-order-matters",
             "Keep the quantifier order of the English: 'everyone R something' is "
             "forall x exists y, 'someone R everything' is exists x forall y."),
        Rule("negation-scope",
             "Translate 'no X is Y' as forall x (X(x) -> ~Y(x)), with the negation "
             "inside the universal; 'not every X is Y' negates the whole universal."),
        Rule("match-the-intended-reading",
             "Check the formula against the English: direction of 'only', what is "
             "required versus permitted, and which argument plays which role."),
    ])


#: The guidelines a formalisation scorer reports as violated.
POLICY_RULEBOOK = _rulebook()
