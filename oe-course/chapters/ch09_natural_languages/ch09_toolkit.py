"""Chapter 9 toolkit — verbalisation, parsing, and multilingual lexicons.

Chapter 9 has two halves that look unrelated and are not.

**§9.2 verbalisation** turns axioms into controlled natural language so a domain
expert who will never read Manchester syntax can still review them. The
interesting property is that verbalisation has an **inverse**: parse the English
back and you should recover the axiom you started with. That round trip is an
*exact, free* correctness signal — rare enough in generative work to be worth
building a chapter around.

**§9.1 multilingual ontologies** is the same idea seen from the side. The axioms
are language-independent; only the *labels* are not. So one ontology carries many
lexicons, and a verbalisation is a function of both.

The chapter's sharpest lesson is the gap between the two things you can measure
here: a verbalisation can round-trip perfectly and still be unreadable English.
Deterministic metrics and judges measure different things, and Chapter 9 is where
that stops being an abstraction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "Axiom", "AXIOM_OPERATORS", "verbalise", "parse_cnl", "round_trips",
    "LEXICON", "LANGUAGES", "label_for", "lexicon_coverage",
    "SAMPLE_AXIOMS", "TEMPLATES", "readability", "uses_lexicon_labels",
]


# --------------------------------------------------------------------------- #
# Axioms
# --------------------------------------------------------------------------- #
AXIOM_OPERATORS = ("subclassof", "some", "only", "disjoint", "type")


@dataclass(frozen=True)
class Axiom:
    """A small axiom language, shared with Chapter 4's shape.

    ``subclassof``  Subject is a kind of Filler
    ``some``        Subject property at least one Filler
    ``only``        Subject property only Fillers
    ``disjoint``    no Subject is a Filler
    ``type``        the individual Subject is a Filler
    """

    subject: str
    operator: str
    filler: str
    property: str = ""

    def key(self) -> tuple:
        return (self.subject, self.operator, self.property, self.filler)

    def __str__(self) -> str:
        if self.operator == "subclassof":
            return f"{self.subject} SubClassOf {self.filler}"
        if self.operator == "disjoint":
            return f"{self.subject} DisjointWith {self.filler}"
        if self.operator == "type":
            return f"{self.subject} Type {self.filler}"
        return f"{self.subject} SubClassOf ({self.property} {self.operator} {self.filler})"


SAMPLE_AXIOMS = [
    Axiom("Giraffe", "subclassof", "Herbivore"),
    Axiom("Lion", "some", "Herbivore", "eats"),
    Axiom("Giraffe", "only", "Leaf", "eats"),
    Axiom("Plant", "disjoint", "Animal"),
    Axiom("Simba", "type", "Lion"),
    Axiom("Branch", "some", "Tree", "isPartOf"),
    Axiom("Impala", "subclassof", "Herbivore"),
    Axiom("Carnivore", "only", "Animal", "eats"),
]


# --------------------------------------------------------------------------- #
# Multilingual lexicon (a lemon-flavoured subset)
# --------------------------------------------------------------------------- #
LANGUAGES = ("en", "nl", "de")

#: One ontology, three lexicons. Note the *ontology terms* never change — only
#: how each language renders them. That separation is the whole point of §9.1:
#: translating an ontology does not mean translating its axioms.
LEXICON = {
    "Giraffe":   {"en": "giraffe", "nl": "giraf", "de": "Giraffe"},
    "Herbivore": {"en": "herbivore", "nl": "herbivoor", "de": "Pflanzenfresser"},
    "Lion":      {"en": "lion", "nl": "leeuw", "de": "Löwe"},
    "Leaf":      {"en": "leaf", "nl": "blad", "de": "Blatt"},
    "Plant":     {"en": "plant", "nl": "plant", "de": "Pflanze"},
    "Animal":    {"en": "animal", "nl": "dier", "de": "Tier"},
    "Simba":     {"en": "Simba", "nl": "Simba", "de": "Simba"},
    "Tree":      {"en": "tree", "nl": "boom", "de": "Baum"},
    "Branch":    {"en": "branch", "nl": "tak", "de": "Ast"},
    "Impala":    {"en": "impala", "nl": "impala", "de": "Impala"},
    "Carnivore": {"en": "carnivore", "nl": "carnivoor", "de": "Fleischfresser"},
    "eats":      {"en": "eats", "nl": "eet", "de": "frisst"},
    "isPartOf":  {"en": "is part of", "nl": "is deel van", "de": "ist Teil von"},
}


def label_for(term: str, language: str = "en") -> str:
    """The label for a term in one language, falling back to the term itself.

    The fallback matters: an unlexicalised term silently renders as its IRI
    fragment, which is how half-translated ontologies ship without anyone
    noticing.
    """
    entry = LEXICON.get(term)
    if entry is None:
        return term
    return entry.get(language, term)


def lexicon_coverage(language: str, terms=None) -> dict:
    """What fraction of the vocabulary this language actually covers."""
    terms = list(terms) if terms is not None else list(LEXICON)
    covered = [t for t in terms if language in LEXICON.get(t, {})]
    return {
        "language": language,
        "covered": len(covered),
        "total": len(terms),
        "coverage": round(len(covered) / len(terms), 3) if terms else 0.0,
        "missing": sorted(set(terms) - set(covered)),
    }


# --------------------------------------------------------------------------- #
# §9.2  Verbalisation
# --------------------------------------------------------------------------- #
#: The controlled fragment. One template per operator, per language. Keeping it
#: a *controlled* language is what makes the inverse (parsing) possible at all.
TEMPLATES = {
    "en": {
        "subclassof": "Every {subject} is a {filler}.",
        "some": "Every {subject} {property} at least one {filler}.",
        "only": "Every {subject} {property} only {filler}.",
        "disjoint": "No {subject} is a {filler}.",
        "type": "{subject} is a {filler}.",
    },
    "nl": {
        "subclassof": "Elke {subject} is een {filler}.",
        "some": "Elke {subject} {property} ten minste een {filler}.",
        "only": "Elke {subject} {property} alleen {filler}.",
        "disjoint": "Geen {subject} is een {filler}.",
        "type": "{subject} is een {filler}.",
    },
    "de": {
        "subclassof": "Jeder {subject} ist ein {filler}.",
        "some": "Jeder {subject} {property} mindestens ein {filler}.",
        "only": "Jeder {subject} {property} nur {filler}.",
        "disjoint": "Kein {subject} ist ein {filler}.",
        "type": "{subject} ist ein {filler}.",
    },
}


def verbalise(axiom: Axiom, language: str = "en") -> str:
    """Render an axiom as controlled natural language."""
    template = TEMPLATES[language][axiom.operator]
    return template.format(
        subject=label_for(axiom.subject, language),
        filler=label_for(axiom.filler, language),
        property=label_for(axiom.property, language) if axiom.property else "",
    )


# --------------------------------------------------------------------------- #
# Parsing the controlled language back
# --------------------------------------------------------------------------- #
def _reverse_lexicon(language: str) -> dict:
    """label -> ontology term, for one language."""
    out = {}
    for term, labels in LEXICON.items():
        label = labels.get(language)
        if label:
            out[label.lower()] = term
    return out


_PATTERNS = {
    "en": [
        ("disjoint", re.compile(r"^No (?P<subject>.+?) is an? (?P<filler>.+?)\.$", re.I)),
        ("some", re.compile(
            r"^Every (?P<subject>.+?) (?P<property>.+?) at least one (?P<filler>.+?)\.$", re.I)),
        ("only", re.compile(
            r"^Every (?P<subject>.+?) (?P<property>.+?) only (?P<filler>.+?)\.$", re.I)),
        ("subclassof", re.compile(r"^Every (?P<subject>.+?) is an? (?P<filler>.+?)\.$", re.I)),
        ("type", re.compile(r"^(?P<subject>.+?) is an? (?P<filler>.+?)\.$", re.I)),
    ],
    "nl": [
        ("disjoint", re.compile(r"^Geen (?P<subject>.+?) is een (?P<filler>.+?)\.$", re.I)),
        ("some", re.compile(
            r"^Elke (?P<subject>.+?) (?P<property>.+?) ten minste een (?P<filler>.+?)\.$", re.I)),
        ("only", re.compile(
            r"^Elke (?P<subject>.+?) (?P<property>.+?) alleen (?P<filler>.+?)\.$", re.I)),
        ("subclassof", re.compile(r"^Elke (?P<subject>.+?) is een (?P<filler>.+?)\.$", re.I)),
        ("type", re.compile(r"^(?P<subject>.+?) is een (?P<filler>.+?)\.$", re.I)),
    ],
    "de": [
        ("disjoint", re.compile(r"^Kein (?P<subject>.+?) ist ein (?P<filler>.+?)\.$", re.I)),
        ("some", re.compile(
            r"^Jeder (?P<subject>.+?) (?P<property>.+?) mindestens ein (?P<filler>.+?)\.$", re.I)),
        ("only", re.compile(
            r"^Jeder (?P<subject>.+?) (?P<property>.+?) nur (?P<filler>.+?)\.$", re.I)),
        ("subclassof", re.compile(r"^Jeder (?P<subject>.+?) ist ein (?P<filler>.+?)\.$", re.I)),
        ("type", re.compile(r"^(?P<subject>.+?) ist ein (?P<filler>.+?)\.$", re.I)),
    ],
}


def parse_cnl(sentence: str, language: str = "en") -> Axiom | None:
    """Parse controlled natural language back into an axiom.

    Patterns are tried most-specific first: ``Every X eats only Y`` must be
    recognised before the bare ``Every X is a Y``, or the more general pattern
    would swallow it. Ordering the grammar is the whole difficulty of parsing a
    CNL, and it is why the language must stay *controlled*.
    """
    sentence = (sentence or "").strip()
    reverse = _reverse_lexicon(language)

    def term(label: str) -> str:
        return reverse.get(label.strip().lower(), label.strip())

    for operator, pattern in _PATTERNS[language]:
        match = pattern.match(sentence)
        if not match:
            continue
        groups = match.groupdict()
        subject_label = groups["subject"].strip()
        # 'type' is for individuals: distinguish it from 'subclassof' by whether
        # the subject is a known individual rather than by grammar alone.
        if operator == "type" and subject_label.lower() in reverse:
            candidate = reverse[subject_label.lower()]
            if candidate not in ("Simba",):
                continue
        return Axiom(
            subject=term(groups["subject"]),
            operator=operator,
            filler=term(groups["filler"]),
            property=term(groups.get("property") or "") if groups.get("property") else "",
        )
    return None


def round_trips(axiom: Axiom, language: str = "en") -> dict:
    """Verbalise, parse back, and report whether the axiom survived.

    This is the free exact reward signal the chapter is built on: no gold
    labels, no judge, no annotation — just a function and its inverse.
    """
    sentence = verbalise(axiom, language)
    recovered = parse_cnl(sentence, language)
    return {
        "axiom": str(axiom),
        "sentence": sentence,
        "recovered": str(recovered) if recovered else None,
        "ok": bool(recovered) and recovered.key() == axiom.key(),
    }


# --------------------------------------------------------------------------- #
# Readability — the thing the round trip cannot see
# --------------------------------------------------------------------------- #
_BAD_ARTICLE = re.compile(r"\ba (?=[aeiou])", re.I)


def readability(sentence: str) -> dict:
    """A crude readability proxy, deliberately **not** a correctness measure.

    It exists to make one point precisely. ``"No plant is a animal."`` round-trips
    perfectly — parse it back and you recover exactly the axiom you started with —
    and it is still wrong English. The round trip cannot see that, because the
    round trip only tests whether the *inverse function* works.

    Two things a reviewer notices immediately and the round trip does not:
    the article agreement above, and bare identifiers leaking through
    (``isPartOf`` instead of ``is part of``). This function scores those; a real
    judge would score much more.
    """
    text = (sentence or "").strip()
    words = text.split()
    has_camel = any(re.search(r"[a-z][A-Z]", w) for w in words)
    bad_article = bool(_BAD_ARTICLE.search(text))
    return {
        "words": len(words),
        "contains_identifier": has_camel,
        "wrong_article": bad_article,
        "ends_with_period": text.endswith("."),
        "starts_capitalised": bool(text) and text[0].isupper(),
        "score": round(
            0.35 * (not has_camel)
            + 0.35 * (not bad_article)
            + 0.15 * text.endswith(".")
            + 0.15 * (bool(text) and text[0].isupper()), 3),
    }


def uses_lexicon_labels(sentence: str, axiom: "Axiom", language: str = "en") -> dict:
    """Does the sentence actually use *this language's* labels for its terms?

    Worth having as a separate check because the round trip does **not** catch
    this. Writing "Elke Giraffe is een Herbivore." leaves the English
    identifiers in a Dutch sentence; the parser still recovers the right axiom
    (its fallback returns unknown labels unchanged), so fidelity looks perfect
    while the output is not really Dutch at all.
    """
    text = (sentence or "").lower()
    terms = [t for t in (axiom.subject, axiom.property, axiom.filler) if t]
    missing = []
    for term in terms:
        label = label_for(term, language)
        if label.lower() not in text:
            missing.append({"term": term, "expected": label})
    return {
        "language": language,
        "checked": len(terms),
        "missing": missing,
        "ok": not missing,
    }
