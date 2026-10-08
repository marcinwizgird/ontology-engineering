"""Chapter 9 problem-set support — multilingual review sheets for a zoo alliance.

Provided code for ``04_assignment.ipynb``. The Rhine–Meuse Zoo Alliance keeps one
shared animal-husbandry ontology and has its keepers review the axioms every
quarter, each in their own language (English, Dutch, German). Keepers do not read
OWL, so every axiom is **verbalised** into a controlled sentence on a review
sheet. This module supplies what that project would already have in its
codebase:

* the **lexicon** — one ontology, three sets of labels, *with morphology*
  (plural, Dutch de/het, German gender and the case a verb governs), and the
  translation agency's first Dutch delivery, defects included;
* the **controlled grammar** — :func:`parse_cnl` reads a sentence back into an
  axiom. It tolerates inflection (``Jeder/Jede/Jedes``, ``a/an``, singular or
  plural) but not paraphrase, and it is **lenient** in one realistic way: an
  unknown word is returned unchanged, so a leaked identifier still "parses";
* the committee's **style checks** (:func:`lint`) — the part of readability a
  regular expression can decide. They are deliberately incomplete: plural after
  *only*, German case after the verb and German noun capitalisation are in the
  style guide but not in the lint, exactly as in a real project;
* the **corpus** — 15 axioms, each verbalised in two languages by the
  committee's translator (30 items), split 5/5/5 **by axiom** (so no language
  version of a test axiom is ever seen in training), every construct in every
  split; and the **readability panel** — 22 sentences the keepers labelled
  acceptable or not;
* the **guidelines** a scorer can report (:data:`CNL_RULEBOOK`), the agent's
  **tools**, and **best-of-n resampling as an MDP** (:class:`RevisionMDP`).

What is *not* here, on purpose: the scorer, the judge, the agreement statistics
and the stopping rule. Those are the assignment.

Run ``python ch09_agentic.py`` to re-validate every gold artefact.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass

from ch09_toolkit import Axiom

__all__ = [
    "Axiom", "LANGUAGES", "LEXICON", "NL_DELIVERY_V0", "lexicon_with", "forms",
    "label", "term_kind", "term_sheet", "STYLE_GUIDE", "parse_axiom_text",
    "parse_cnl", "round_trip", "lint", "TEMPLATE_WORDS", "CORPUS", "AXIOMS",
    "build_dataset", "gold_axiom", "READABILITY_PANEL", "CNL_RULEBOOK",
    "LINT_RULES", "REVIEW_COST_USD", "Ch9Context", "build_toolset", "DraftState",
    "RevisionMDP", "validate",
]

LANGUAGES = ("en", "nl", "de")

#: What one sentence on a review sheet is worth, in USD of keeper time: a
#: sentence a keeper cannot sign off costs about two minutes to rewrite by hand.
#: It converts API spend into the same units as sentence quality (Part D).
REVIEW_COST_USD = 1.50


# --------------------------------------------------------------------------- #
# The lexicon: one ontology, three languages, with morphology
# --------------------------------------------------------------------------- #
def _en(label, plural=None):
    return {"label": label, "plural": plural}


def _nl(label, article, plural):
    return {"label": label, "article": article, "plural": plural}


def _de(label, gender, plural, oblique=None):
    return {"label": label, "gender": gender, "plural": plural, "oblique": oblique}


#: term -> {"kind": class|individual|property, "en": {...}, "nl": {...}, "de": {...}}.
#: Nouns carry their plural; Dutch nouns their article (de/het); German nouns
#: their gender (m/f/n) and, for weak masculines, the oblique singular
#: ("einen Löwen"). Properties carry the case their object takes in German.
LEXICON: dict[str, dict] = {
    # --- classes ------------------------------------------------------------
    "Animal":      {"kind": "class", "en": _en("animal", "animals"),
                    "nl": _nl("dier", "het", "dieren"), "de": _de("Tier", "n", "Tiere")},
    "Plant":       {"kind": "class", "en": _en("plant", "plants"),
                    "nl": _nl("plant", "de", "planten"), "de": _de("Pflanze", "f", "Pflanzen")},
    "Leaf":        {"kind": "class", "en": _en("leaf", "leaves"),
                    "nl": _nl("blad", "het", "bladeren"), "de": _de("Blatt", "n", "Blätter")},
    "Insect":      {"kind": "class", "en": _en("insect", "insects"),
                    "nl": _nl("insect", "het", "insecten"), "de": _de("Insekt", "n", "Insekten")},
    "Herbivore":   {"kind": "class", "en": _en("herbivore", "herbivores"),
                    "nl": _nl("herbivoor", "de", "herbivoren"),
                    "de": _de("Pflanzenfresser", "m", "Pflanzenfresser")},
    "Carnivore":   {"kind": "class", "en": _en("carnivore", "carnivores"),
                    "nl": _nl("carnivoor", "de", "carnivoren"),
                    "de": _de("Fleischfresser", "m", "Fleischfresser")},
    "Insectivore": {"kind": "class", "en": _en("insectivore", "insectivores"),
                    "nl": _nl("insecteneter", "de", "insecteneters"),
                    "de": _de("Insektenfresser", "m", "Insektenfresser")},
    "Elephant":    {"kind": "class", "en": _en("elephant", "elephants"),
                    "nl": _nl("olifant", "de", "olifanten"),
                    "de": _de("Elefant", "m", "Elefanten", "Elefanten")},
    "Lion":        {"kind": "class", "en": _en("lion", "lions"),
                    "nl": _nl("leeuw", "de", "leeuwen"), "de": _de("Löwe", "m", "Löwen", "Löwen")},
    "Giraffe":     {"kind": "class", "en": _en("giraffe", "giraffes"),
                    "nl": _nl("giraf", "de", "giraffen"), "de": _de("Giraffe", "f", "Giraffen")},
    "Okapi":       {"kind": "class", "en": _en("okapi", "okapis"),
                    "nl": _nl("okapi", "de", "okapi's"), "de": _de("Okapi", "n", "Okapis")},
    "Anteater":    {"kind": "class", "en": _en("anteater", "anteaters"),
                    "nl": _nl("miereneter", "de", "miereneters"),
                    "de": _de("Ameisenbär", "m", "Ameisenbären", "Ameisenbären")},
    "Enclosure":   {"kind": "class", "en": _en("enclosure", "enclosures"),
                    "nl": _nl("verblijf", "het", "verblijven"), "de": _de("Gehege", "n", "Gehege")},
    "Paddock":     {"kind": "class", "en": _en("paddock", "paddocks"),
                    "nl": _nl("buitenverblijf", "het", "buitenverblijven"),
                    "de": _de("Außengehege", "n", "Außengehege")},
    "Keeper":      {"kind": "class", "en": _en("keeper", "keepers"),
                    "nl": _nl("verzorger", "de", "verzorgers"),
                    "de": _de("Tierpfleger", "m", "Tierpfleger")},
    "Veterinarian": {"kind": "class", "en": _en("veterinarian", "veterinarians"),
                     "nl": _nl("dierenarts", "de", "dierenartsen"),
                     "de": _de("Tierarzt", "m", "Tierärzte")},
    # --- individuals (names are not translated) -----------------------------
    "Kiara":  {"kind": "individual", "en": {"label": "Kiara"}, "nl": {"label": "Kiara"},
               "de": {"label": "Kiara"}},
    "Tembo":  {"kind": "individual", "en": {"label": "Tembo"}, "nl": {"label": "Tembo"},
               "de": {"label": "Tembo"}},
    "Zawadi": {"kind": "individual", "en": {"label": "Zawadi"}, "nl": {"label": "Zawadi"},
               "de": {"label": "Zawadi"}},
    # --- properties (third person singular; German object case) -------------
    "eats":     {"kind": "property", "en": {"label": "eats"}, "nl": {"label": "eet"},
                 "de": {"label": "frisst", "case": "acc"}},
    "livesIn":  {"kind": "property", "en": {"label": "lives in"}, "nl": {"label": "leeft in"},
                 "de": {"label": "lebt in", "case": "dat"}},
    "caresFor": {"kind": "property", "en": {"label": "cares for"}, "nl": {"label": "verzorgt"},
                 "de": {"label": "betreut", "case": "acc"}},
    "treats":   {"kind": "property", "en": {"label": "treats"}, "nl": {"label": "behandelt"},
                 "de": {"label": "behandelt", "case": "acc"}},
}

#: The translation agency's first Dutch delivery (term -> nl entry), as received.
#: It has four real defects; Problem A2 is to find them mechanically.
NL_DELIVERY_V0: dict[str, dict] = {
    **{term: dict(entry["nl"]) for term, entry in LEXICON.items() if term != "Insectivore"},
    "Paddock": _nl("verblijf", "het", "verblijven"),       # same word as Enclosure
    "caresFor": {"label": "caresFor"},                      # identifier copied, not translated
    "Okapi": _nl("een okapi", "de", "okapi's"),            # article typed into the label
}


def lexicon_with(language: str, entries: dict, base: dict | None = None) -> dict:
    """A copy of ``base`` (default :data:`LEXICON`) whose ``language`` labels are
    replaced by ``entries``. Terms missing from ``entries`` lose that language."""
    base = base if base is not None else LEXICON
    out = {}
    for term, entry in base.items():
        new = {k: (dict(v) if isinstance(v, dict) else v) for k, v in entry.items()
               if k != language}
        if term in entries:
            new[language] = dict(entries[term])
        out[term] = new
    return out


def term_kind(term: str, lexicon: dict | None = None) -> str | None:
    entry = (lexicon or LEXICON).get(term)
    return entry["kind"] if entry else None


def label(term: str, language: str, lexicon: dict | None = None) -> str:
    """The base label of a term, falling back to the identifier (as RDF tools do)."""
    entry = (lexicon or LEXICON).get(term, {}).get(language) or {}
    return entry.get("label") or term


def forms(term: str, language: str, lexicon: dict | None = None) -> list[str]:
    """Every surface form of a term in one language: label, plural, oblique."""
    entry = (lexicon or LEXICON).get(term, {}).get(language) or {}
    out = [entry.get(k) for k in ("label", "plural", "oblique")]
    return list(dict.fromkeys(f for f in out if f))


_GENDER = {"m": "masculine", "f": "feminine", "n": "neuter"}
_CASE = {"acc": "accusative", "dat": "dative"}


def term_sheet(axiom: Axiom, language: str, lexicon: dict | None = None) -> str:
    """What the verbaliser is told about the terms of one axiom, in one language."""
    lexicon = lexicon or LEXICON
    lines = []
    for term in (axiom.subject, axiom.property, axiom.filler):
        if not term:
            continue
        kind = term_kind(term, lexicon)
        entry = lexicon.get(term, {}).get(language) or {}
        base = entry.get("label") or term
        if kind == "individual":
            lines.append(f"{term}: '{base}' (proper name)")
        elif kind == "property":
            extra = f"; object in the {_CASE[entry['case']]}" if entry.get("case") else ""
            lines.append(f"{term}: '{base}' (verb{extra})")
        else:
            bits = ["noun"]
            if entry.get("article"):
                bits.append(f"{entry['article']}-word")
            if entry.get("gender"):
                bits.append(_GENDER[entry["gender"]])
            if entry.get("plural"):
                bits.append(f"plural '{entry['plural']}'")
            if entry.get("oblique"):
                bits.append(f"accusative/dative singular '{entry['oblique']}'")
            lines.append(f"{term}: '{base}' ({'; '.join(bits)})")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# The controlled grammar
# --------------------------------------------------------------------------- #
#: The committee's style guide, one line per construct and language. This is the
#: *specification*; the regular expressions below are its inverse.
STYLE_GUIDE = {
    "en": {
        "subclassof": "Every X is a/an Y.",
        "some": "Every X <verb> at least one Y.",
        "only": "Every X <verb> only Ys.   (Y in the plural)",
        "disjoint": "No X is a/an Y.",
        "type": "Name is a/an Y.",
    },
    "nl": {
        "subclassof": "Elke/Elk X is een Y.   (Elk before a het-word)",
        "some": "Elke/Elk X <verb> ten minste één Y.",
        "only": "Elke/Elk X <verb> alleen Ys.   (Y in the plural)",
        "disjoint": "Geen X is een Y.",
        "type": "Name is een Y.",
    },
    "de": {
        "subclassof": "Jeder/Jede/Jedes X ist ein/eine Y.   (by gender)",
        "some": "Jeder/Jede/Jedes X <verb> mindestens einen/eine/ein/einem/einer Y.   "
                "(by gender, in the verb's case)",
        "only": "Jeder/Jede/Jedes X <verb> nur Ys.   (Y in the plural)",
        "disjoint": "Kein/Keine X ist ein/eine Y.",
        "type": "Name ist ein/eine Y.",
    },
}

_S, _P, _F = r"(?P<subject>.+?)", r"(?P<property>.+?)", r"(?P<filler>.+?)"

_PATTERNS = {
    "en": [
        ("disjoint", rf"No {_S} is an? {_F}"),
        ("some", rf"Every {_S} {_P} at least one {_F}"),
        ("only", rf"Every {_S} {_P} only {_F}"),
        ("subclassof", rf"Every {_S} is an? {_F}"),
        ("type", rf"{_S} is an? {_F}"),
    ],
    "nl": [
        ("disjoint", rf"Geen {_S} is een {_F}"),
        ("some", rf"Elke? {_S} {_P} ten minste (?:een|één) {_F}"),
        ("only", rf"Elke? {_S} {_P} alleen {_F}"),
        ("subclassof", rf"Elke? {_S} is een {_F}"),
        ("type", rf"{_S} is een {_F}"),
    ],
    "de": [
        ("disjoint", rf"Keine? {_S} ist eine? {_F}"),
        ("some", rf"Jede[rs]? {_S} {_P} mindestens (?:einen|einem|einer|eine|ein) {_F}"),
        ("only", rf"Jede[rs]? {_S} {_P} nur {_F}"),
        ("subclassof", rf"Jede[rs]? {_S} ist eine? {_F}"),
        ("type", rf"{_S} ist eine? {_F}"),
    ],
}
_COMPILED = {lang: [(op, re.compile(rf"^{pat}\.$", re.I)) for op, pat in pats]
             for lang, pats in _PATTERNS.items()}

#: Words the grammar itself uses, per language. A label containing one of them
#: can make the parser split a sentence in the wrong place (Problem A2).
TEMPLATE_WORDS = {
    "en": {"every", "no", "is", "a", "an", "at", "least", "one", "only"},
    "nl": {"elke", "elk", "geen", "is", "een", "één", "ten", "minste", "alleen"},
    "de": {"jeder", "jede", "jedes", "kein", "keine", "ist", "ein", "eine", "einen",
           "einem", "einer", "mindestens", "nur"},
}


def _reverse(language: str, lexicon: dict) -> dict[str, str]:
    """surface form (lower-case) -> term. Later terms overwrite earlier ones, so
    a label shared by two terms silently resolves to one of them."""
    out: dict[str, str] = {}
    for term in lexicon:
        for form in forms(term, language, lexicon):
            out[form.lower()] = term
    return out


def parse_cnl(sentence: str, language: str = "en", lexicon: dict | None = None) -> Axiom | None:
    """Read a controlled sentence back into an axiom, or ``None`` if it is not one.

    Patterns are tried most specific first. Words are mapped back to terms through
    every surface form of the language; a word the lexicon does not know is kept
    as it is — which is why a leaked identifier (``livesIn``, ``Herbivore``) still
    round-trips, and why readability needs its own check.
    """
    lexicon = lexicon or LEXICON
    text = re.sub(r"\s+", " ", (sentence or "").strip())
    if language not in _COMPILED or not text:
        return None
    reverse = _reverse(language, lexicon)

    def term(words: str | None) -> str:
        words = (words or "").strip()
        return reverse.get(words.lower(), words)

    for operator, pattern in _COMPILED[language]:
        match = pattern.match(text)
        if not match:
            continue
        groups = match.groupdict()
        subject = term(groups["subject"])
        is_individual = term_kind(subject, lexicon) == "individual"
        if (operator == "type") != is_individual:
            continue          # 'type' is for named individuals, the rest for classes
        return Axiom(subject=subject, operator=operator, filler=term(groups["filler"]),
                     property=term(groups.get("property")) if groups.get("property") else "")
    return None


def round_trip(sentence: str, axiom: Axiom, language: str, lexicon: dict | None = None) -> dict:
    """Parse ``sentence`` and compare with ``axiom``: the free, exact fidelity check."""
    recovered = parse_cnl(sentence, language, lexicon)
    return {"parses": recovered is not None,
            "recovered": str(recovered) if recovered else None,
            "faithful": recovered is not None and recovered.key() == axiom.key()}


_AXIOM_TEXT = [
    ("some", re.compile(r"^(\w+) SubClassOf \((\w+) some (\w+)\)$")),
    ("only", re.compile(r"^(\w+) SubClassOf \((\w+) only (\w+)\)$")),
    ("subclassof", re.compile(r"^(\w+) SubClassOf (\w+)$")),
    ("disjoint", re.compile(r"^(\w+) DisjointWith (\w+)$")),
    ("type", re.compile(r"^(\w+) Type (\w+)$")),
]


def parse_axiom_text(text: str) -> Axiom:
    """Inverse of ``str(Axiom)``: ``'Okapi SubClassOf (livesIn some Enclosure)'``."""
    text = (text or "").strip()
    for operator, pattern in _AXIOM_TEXT:
        m = pattern.match(text)
        if m:
            if operator in ("some", "only"):
                return Axiom(m.group(1), operator, m.group(3), m.group(2))
            return Axiom(m.group(1), operator, m.group(2))
    raise ValueError(f"not an axiom: {text!r}")


# --------------------------------------------------------------------------- #
# The committee's style checks (the decidable part of readability)
# --------------------------------------------------------------------------- #
LINT_RULES = ("use-the-lexicon-label", "correct-article", "agree-in-gender")

_EVERY_DE = {"m": "jeder", "f": "jede", "n": "jedes"}
_NO_DE = {"m": "kein", "f": "keine", "n": "kein"}
_A_DE = {"m": "ein", "f": "eine", "n": "ein"}


def _has_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, re.I) is not None


def lint(sentence: str, axiom: Axiom, language: str, lexicon: dict | None = None) -> list[dict]:
    """Style issues a regular expression can decide, as ``{"rule", "message"}`` dicts.

    Checks: every term appears in one of *this language's* forms and no
    camelCase identifier leaks (``use-the-lexicon-label``); English a/an
    (``correct-article``); Dutch Elk/Elke and German Jeder/Jede/Jedes,
    Kein/Keine, ein/eine (``agree-in-gender``). Not checked — by design, because
    the first version of the style checks did not: plural after *only*, German
    case after the verb, German noun capitalisation.
    """
    lexicon = lexicon or LEXICON
    text = re.sub(r"\s+", " ", (sentence or "").strip())
    issues: list[dict] = []
    for term in (axiom.subject, axiom.property, axiom.filler):
        if term and not any(_has_phrase(text, f) for f in forms(term, language, lexicon)):
            issues.append({"rule": "use-the-lexicon-label",
                           "message": f"'{term}' should appear as "
                                      f"'{label(term, language, lexicon)}' in {language}."})
    for word in re.findall(r"\w+", text):
        if re.search(r"[a-z][A-Z]", word):
            issues.append({"rule": "use-the-lexicon-label",
                           "message": f"Raw identifier '{word}' in the sentence."})
    if language == "en":
        for m in re.finditer(r"\b(a|an) (\w+)", text, re.I):
            article, word = m.group(1).lower(), m.group(2)
            vowel = word[0].lower() in "aeiou"
            if (article == "a") == vowel:
                issues.append({"rule": "correct-article",
                               "message": f"'{m.group(0)}': use '{'an' if vowel else 'a'}'."})
    words = [w.lower() for w in re.findall(r"\w+", text)]
    first = words[0] if words else ""
    if language == "nl" and first in ("elk", "elke"):
        article = (lexicon.get(axiom.subject, {}).get("nl") or {}).get("article")
        want = {"het": "elk", "de": "elke"}.get(article)
        if want and first != want:
            issues.append({"rule": "agree-in-gender",
                           "message": f"'{label(axiom.subject, 'nl', lexicon)}' is a "
                                      f"{article}-word: start with '{want.capitalize()}'."})
    if language == "de":
        subj_gender = (lexicon.get(axiom.subject, {}).get("de") or {}).get("gender")
        fill_gender = (lexicon.get(axiom.filler, {}).get("de") or {}).get("gender")
        table = _EVERY_DE if first.startswith("jede") else _NO_DE if first.startswith("kein") else None
        if table and subj_gender and first != table[subj_gender]:
            issues.append({"rule": "agree-in-gender",
                           "message": f"'{label(axiom.subject, 'de', lexicon)}' is "
                                      f"{_GENDER[subj_gender]}: start with "
                                      f"'{table[subj_gender].capitalize()}'."})
        m = re.search(r"\bist (eine?) ", text, re.I)
        if m and fill_gender and m.group(1).lower() != _A_DE[fill_gender]:
            issues.append({"rule": "agree-in-gender",
                           "message": f"'{label(axiom.filler, 'de', lexicon)}' is "
                                      f"{_GENDER[fill_gender]}: 'ist {_A_DE[fill_gender]}'."})
    return issues


# --------------------------------------------------------------------------- #
# The corpus: 15 axioms x 2 languages, split by axiom
# --------------------------------------------------------------------------- #
#: (axiom id, split, axiom, {language: approved reference sentence}). Each split
#: has every construct exactly once and 4 en / 3 nl / 3 de items. The reference
#: sentences are last quarter's translator-approved wording: one acceptable
#: answer, not the only one — the grader never compares strings.
CORPUS: list[tuple[str, str, Axiom, dict[str, str]]] = [
    # --- train --------------------------------------------------------------
    ("elephant-is-herbivore", "train", Axiom("Elephant", "subclassof", "Herbivore"),
     {"en": "Every elephant is a herbivore.", "de": "Jeder Elefant ist ein Pflanzenfresser."}),
    ("lion-eats-herbivore", "train", Axiom("Lion", "some", "Herbivore", "eats"),
     {"en": "Every lion eats at least one herbivore.",
      "nl": "Elke leeuw eet ten minste één herbivoor."}),
    ("giraffe-eats-only-leaves", "train", Axiom("Giraffe", "only", "Leaf", "eats"),
     {"nl": "Elke giraf eet alleen bladeren.", "de": "Jede Giraffe frisst nur Blätter."}),
    ("plants-not-animals", "train", Axiom("Plant", "disjoint", "Animal"),
     {"en": "No plant is an animal.", "de": "Keine Pflanze ist ein Tier."}),
    ("kiara-is-lion", "train", Axiom("Kiara", "type", "Lion"),
     {"en": "Kiara is a lion.", "nl": "Kiara is een leeuw."}),
    # --- dev ----------------------------------------------------------------
    ("anteater-is-insectivore", "dev", Axiom("Anteater", "subclassof", "Insectivore"),
     {"en": "Every anteater is an insectivore.", "nl": "Elke miereneter is een insecteneter."}),
    ("okapi-lives-in-enclosure", "dev", Axiom("Okapi", "some", "Enclosure", "livesIn"),
     {"en": "Every okapi lives in at least one enclosure.",
      "de": "Jedes Okapi lebt in mindestens einem Gehege."}),
    ("carnivore-eats-only-animals", "dev", Axiom("Carnivore", "only", "Animal", "eats"),
     {"nl": "Elke carnivoor eet alleen dieren.", "de": "Jeder Fleischfresser frisst nur Tiere."}),
    ("herbivore-not-carnivore", "dev", Axiom("Herbivore", "disjoint", "Carnivore"),
     {"en": "No herbivore is a carnivore.", "de": "Kein Pflanzenfresser ist ein Fleischfresser."}),
    ("tembo-is-elephant", "dev", Axiom("Tembo", "type", "Elephant"),
     {"en": "Tembo is an elephant.", "nl": "Tembo is een olifant."}),
    # --- test ---------------------------------------------------------------
    ("insect-is-animal", "test", Axiom("Insect", "subclassof", "Animal"),
     {"nl": "Elk insect is een dier.", "de": "Jedes Insekt ist ein Tier."}),
    ("keeper-cares-for-animal", "test", Axiom("Keeper", "some", "Animal", "caresFor"),
     {"en": "Every keeper cares for at least one animal.",
      "nl": "Elke verzorger verzorgt ten minste één dier."}),
    ("vet-treats-only-animals", "test", Axiom("Veterinarian", "only", "Animal", "treats"),
     {"en": "Every veterinarian treats only animals.", "de": "Jeder Tierarzt behandelt nur Tiere."}),
    ("leaf-not-animal", "test", Axiom("Leaf", "disjoint", "Animal"),
     {"en": "No leaf is an animal.", "nl": "Geen blad is een dier."}),
    ("zawadi-is-giraffe", "test", Axiom("Zawadi", "type", "Giraffe"),
     {"en": "Zawadi is a giraffe.", "de": "Zawadi ist eine Giraffe."}),
]

AXIOMS: dict[str, Axiom] = {axiom_id: axiom for axiom_id, _, axiom, _ in CORPUS}


def build_dataset(split: str = "all"):
    """The corpus as ``dspy.Example`` rows, one per (axiom, language).

    Inputs: ``axiom`` (Manchester-like text), ``language``, ``terms`` (the term
    sheet). Labels: ``subject``/``operator``/``property``/``filler`` and the
    approved ``reference`` sentence. ``id`` is ``<axiom id>-<language>``.
    """
    import dspy

    rows = []
    for axiom_id, item_split, axiom, references in CORPUS:
        for language in LANGUAGES:
            if language not in references:
                continue
            rows.append(dspy.Example(
                id=f"{axiom_id}-{language}", axiom_id=axiom_id, split=item_split,
                axiom=str(axiom), language=language, terms=term_sheet(axiom, language),
                subject=axiom.subject, operator=axiom.operator, property=axiom.property,
                filler=axiom.filler, reference=references[language],
            ).with_inputs("axiom", "language", "terms"))
    return rows if split == "all" else [r for r in rows if r.split == split]


def gold_axiom(example) -> Axiom:
    """The axiom a dataset row asks for."""
    return Axiom(example.subject, example.operator, example.filler, example.property or "")


# --------------------------------------------------------------------------- #
# The keepers' readability panel (human labels for judge validation)
# --------------------------------------------------------------------------- #
#: Every sentence here round-trips exactly. ``acceptable`` is the majority vote
#: of three keepers who review in that language; ``issue`` is their reason.
READABILITY_PANEL: list[dict] = [
    {"id": "P01", "axiom_id": "elephant-is-herbivore", "language": "en",
     "sentence": "Every elephant is a herbivore.", "acceptable": True, "issue": ""},
    {"id": "P02", "axiom_id": "giraffe-eats-only-leaves", "language": "de",
     "sentence": "Jede Giraffe frisst nur Blätter.", "acceptable": True, "issue": ""},
    {"id": "P03", "axiom_id": "insect-is-animal", "language": "nl",
     "sentence": "Elk insect is een dier.", "acceptable": True, "issue": ""},
    {"id": "P04", "axiom_id": "plants-not-animals", "language": "en",
     "sentence": "No plant is an animal.", "acceptable": True, "issue": ""},
    {"id": "P05", "axiom_id": "okapi-lives-in-enclosure", "language": "de",
     "sentence": "Jedes Okapi lebt in mindestens einem Gehege.", "acceptable": True, "issue": ""},
    {"id": "P06", "axiom_id": "kiara-is-lion", "language": "nl",
     "sentence": "Kiara is een leeuw.", "acceptable": True, "issue": ""},
    {"id": "P07", "axiom_id": "vet-treats-only-animals", "language": "en",
     "sentence": "Every veterinarian treats only animals.", "acceptable": True, "issue": ""},
    {"id": "P08", "axiom_id": "zawadi-is-giraffe", "language": "de",
     "sentence": "Zawadi ist eine Giraffe.", "acceptable": True, "issue": ""},
    {"id": "P09", "axiom_id": "carnivore-eats-only-animals", "language": "nl",
     "sentence": "Elke carnivoor eet alleen dieren.", "acceptable": True, "issue": ""},
    {"id": "P10", "axiom_id": "keeper-cares-for-animal", "language": "en",
     "sentence": "Every keeper cares for at least one animal.", "acceptable": True, "issue": ""},
    {"id": "P11", "axiom_id": "lion-eats-herbivore", "language": "en",
     "sentence": "Every lion eats at least one herbivore.", "acceptable": True, "issue": ""},
    {"id": "P12", "axiom_id": "okapi-lives-in-enclosure", "language": "nl",
     "sentence": "Elke okapi leeft in ten minste één verblijf.", "acceptable": True, "issue": ""},
    {"id": "P13", "axiom_id": "plants-not-animals", "language": "en",
     "sentence": "No plant is a animal.", "acceptable": False, "issue": "article: 'an animal'"},
    {"id": "P14", "axiom_id": "giraffe-eats-only-leaves", "language": "de",
     "sentence": "Jeder Giraffe frisst nur Blätter.", "acceptable": False,
     "issue": "gender: 'Giraffe' is feminine, 'Jede'"},
    {"id": "P15", "axiom_id": "elephant-is-herbivore", "language": "nl",
     "sentence": "Elke olifant is een Herbivore.", "acceptable": False,
     "issue": "English word in a Dutch sentence ('herbivoor')"},
    {"id": "P16", "axiom_id": "okapi-lives-in-enclosure", "language": "en",
     "sentence": "Every okapi livesIn at least one enclosure.", "acceptable": False,
     "issue": "identifier 'livesIn'"},
    {"id": "P17", "axiom_id": "insect-is-animal", "language": "nl",
     "sentence": "Elke insect is een dier.", "acceptable": False,
     "issue": "'insect' is a het-word: 'Elk insect'"},
    {"id": "P18", "axiom_id": "giraffe-eats-only-leaves", "language": "en",
     "sentence": "Every giraffe eats only leaf.", "acceptable": False,
     "issue": "number: 'only leaves'"},
    {"id": "P19", "axiom_id": "lion-eats-herbivore", "language": "de",
     "sentence": "Jeder Löwe frisst mindestens ein Pflanzenfresser.", "acceptable": False,
     "issue": "case: accusative 'einen Pflanzenfresser'"},
    {"id": "P20", "axiom_id": "okapi-lives-in-enclosure", "language": "de",
     "sentence": "Jedes Okapi lebt in mindestens ein Gehege.", "acceptable": False,
     "issue": "case: dative 'einem Gehege'"},
    {"id": "P21", "axiom_id": "vet-treats-only-animals", "language": "de",
     "sentence": "Jeder tierarzt behandelt nur tiere.", "acceptable": False,
     "issue": "German nouns are capitalised"},
    {"id": "P22", "axiom_id": "carnivore-eats-only-animals", "language": "en",
     "sentence": "Every carnivore eats only animal.", "acceptable": False,
     "issue": "number: 'only animals'"},
]


# --------------------------------------------------------------------------- #
# Guidelines a scorer (or a judge) can report
# --------------------------------------------------------------------------- #
def _rulebook():
    from oe_course.evaluation import Rule, RuleBook

    return RuleBook([
        Rule("template-for-subclassof",
             "Render 'X SubClassOf Y' as: en 'Every X is a/an Y.'; nl 'Elke/Elk X is een "
             "Y.'; de 'Jeder/Jede/Jedes X ist ein/eine Y.' Nothing before or after it."),
        Rule("template-for-some",
             "Render 'X SubClassOf (p some Y)' as: en 'Every X <p> at least one Y.'; nl "
             "'Elke/Elk X <p> ten minste één Y.'; de 'Jeder/Jede/Jedes X <p> mindestens "
             "einen/eine/ein/einem/einer Y.'"),
        Rule("template-for-only",
             "Render 'X SubClassOf (p only Y)' as: en 'Every X <p> only <Y plural>.'; nl "
             "'Elke/Elk X <p> alleen <Y plural>.'; de 'Jeder/Jede/Jedes X <p> nur <Y plural>.'"),
        Rule("template-for-disjoint",
             "Render 'X DisjointWith Y' as: en 'No X is a/an Y.'; nl 'Geen X is een Y.'; "
             "de 'Kein/Keine X ist ein/eine Y.'"),
        Rule("template-for-type",
             "Render 'n Type Y' (n is a named animal) as: en 'n is a/an Y.'; nl 'n is een "
             "Y.'; de 'n ist ein/eine Y.' -- without 'Every'."),
        Rule("preserve-the-terms",
             "Use the term sheet's word for every term. A synonym ('plant-eater' for "
             "herbivore, 'Stall' for Gehege) cannot be mapped back to the ontology."),
        Rule("use-the-lexicon-label",
             "Use the requested language's word from the term sheet, never the ontology "
             "identifier (livesIn, Herbivore) or another language's word."),
        Rule("correct-article",
             "English: 'an' before a vowel sound, 'a' before a consonant."),
        Rule("agree-in-gender",
             "Dutch: 'Elk' before a het-word, 'Elke' before a de-word. German: "
             "Jeder/Kein/ein (masculine), Jede/Keine/eine (feminine), Jedes/Kein/ein "
             "(neuter), from the term sheet."),
        Rule("plural-after-only",
             "After only / alleen / nur use the plural form from the term sheet."),
        Rule("german-case-after-verb",
             "German: after the verb, the article takes the verb's case from the term "
             "sheet -- accusative einen/eine/ein, dative einem/einer/einem."),
        Rule("capitalise-german-nouns",
             "German: capitalise every noun, as the term sheet does."),
    ])


#: The committee's style guide as named guidelines. Only the first nine can be
#: reported by a deterministic scorer; the last three need a reader.
CNL_RULEBOOK = _rulebook()


# --------------------------------------------------------------------------- #
# Agent tools
# --------------------------------------------------------------------------- #
@dataclass
class Ch9Context:
    """The verbaliser agent's workspace: the lexicon it may consult, and its log."""

    lexicon: dict = None
    log: object = None

    def __post_init__(self):
        from oe_course.tools import ToolCallLog

        self.lexicon = self.lexicon if self.lexicon is not None else LEXICON
        self.log = self.log or ToolCallLog()


def build_toolset(ctx: Ch9Context):
    """The verbaliser agent's tools: style guide, term sheet, round trip, lint."""
    from langchain_core.tools import tool

    from oe_course.tools import instrument

    def style_guide(language: str) -> str:
        """The controlled-language pattern for each construct in one language (en, nl, de).
        Sentences that do not follow these patterns cannot be checked and are rejected."""
        return json.dumps(STYLE_GUIDE.get(language, {}), ensure_ascii=False)

    def lookup_terms(axiom: str, language: str) -> str:
        """The words to use for every term of an axiom (e.g. 'Okapi SubClassOf (livesIn
        some Enclosure)') in one language, with plural, gender/article and case."""
        return term_sheet(parse_axiom_text(axiom), language, ctx.lexicon)

    def check_round_trip(sentence: str, language: str, axiom: str) -> str:
        """Parse a draft sentence back into an axiom and compare it with the intended one.
        faithful=true means the sentence says exactly the axiom; anything else is wrong
        however well it reads."""
        return json.dumps(round_trip(sentence, parse_axiom_text(axiom), language, ctx.lexicon),
                          ensure_ascii=False)

    def lint_sentence(sentence: str, language: str, axiom: str) -> str:
        """The committee's automatic style checks for a draft: wrong-language or
        identifier words, a/an, and gender agreement. An empty list means no issue these
        checks can see -- they do not check plural, case or capitalisation."""
        return json.dumps(lint(sentence, parse_axiom_text(axiom), language, ctx.lexicon),
                          ensure_ascii=False)

    impls = [style_guide, lookup_terms, check_round_trip, lint_sentence]
    return [tool(instrument(fn, fn.__name__, ctx.log)) for fn in impls]


# --------------------------------------------------------------------------- #
# Best-of-n resampling as an optimal-stopping MDP
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DraftState:
    """Attempts spent, and the quality (ladder index) of the draft in hand; -1 = none."""

    attempts: int
    quality: int

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"n={self.attempts},q={'-' if self.quality < 0 else self.quality}"


ACCEPTED = DraftState(-1, -1)


class RevisionMDP:
    """Draw a verbalisation, see its quality, and decide whether to draw again.

    | | |
    |---|---|
    | **S** | attempts spent, and the quality of the draft in hand |
    | **A** | ``accept`` the draft in hand, or ``retry`` (while attempts remain) |
    | **T** | stochastic: a new draft's quality is drawn from ``probabilities`` |
    | **R** | ``-cost`` per draw; on accept, the quality accepted |

    ``recall=True`` keeps the **best** draft so far (you can always go back to
    it — best-of-n with a scorer). ``recall=False`` keeps only the **latest**
    draft (a pipeline that overwrites, or a reviewer who has already discarded
    the old one). The two have differently shaped optimal policies.
    """

    def __init__(self, qualities=(0.4, 0.7, 1.0), probabilities=(0.5, 0.3, 0.2),
                 cost: float = 0.05, max_attempts: int = 4, recall: bool = True,
                 gamma: float = 1.0):
        assert len(qualities) == len(probabilities) and len(qualities) >= 1
        assert abs(sum(probabilities) - 1.0) < 1e-9, "probabilities must sum to 1"
        assert list(qualities) == sorted(qualities), "list qualities from worst to best"
        self.qualities = tuple(float(q) for q in qualities)
        self.probabilities = tuple(float(p) for p in probabilities)
        self.cost = float(cost)
        self.max_attempts = int(max_attempts)
        self.recall = recall
        self.gamma = gamma

    def initial_state(self) -> DraftState:
        return DraftState(0, -1)

    def is_terminal(self, state: DraftState) -> bool:
        return state.attempts < 0

    def states(self) -> list[DraftState]:
        out = [DraftState(0, -1)]
        for attempts in range(1, self.max_attempts + 1):
            out += [DraftState(attempts, q) for q in range(len(self.qualities))]
        return out + [ACCEPTED]

    def actions(self, state: DraftState) -> list[str]:
        if self.is_terminal(state):
            return []
        options = ["accept"] if state.quality >= 0 else []
        if state.attempts < self.max_attempts:
            options.append("retry")
        return options

    def transition(self, state: DraftState, action: str):
        if action == "accept":
            return [(1.0, ACCEPTED, self.qualities[state.quality])]
        outcomes = []
        for index, probability in enumerate(self.probabilities):
            kept = max(index, state.quality) if self.recall else index
            outcomes.append((probability, DraftState(state.attempts + 1, kept), -self.cost))
        return outcomes

    def step(self, state: DraftState, action: str):
        outcomes = self.transition(state, action)
        roll, cumulative = random.random(), 0.0
        for probability, nxt, reward in outcomes:
            cumulative += probability
            if roll <= cumulative:
                return nxt, reward, self.is_terminal(nxt)
        _, nxt, reward = outcomes[-1]
        return nxt, reward, self.is_terminal(nxt)

    def thresholds(self, policy: dict) -> list[dict]:
        """The accept/retry decision at each (attempts spent, quality in hand)."""
        rows = []
        for attempts in range(1, self.max_attempts + 1):
            row = {"attempts spent": attempts}
            for index, quality in enumerate(self.qualities):
                row[f"q={quality:g}"] = policy.get(DraftState(attempts, index), "-")
            rows.append(row)
        return rows


# --------------------------------------------------------------------------- #
# Validation of every gold artefact
# --------------------------------------------------------------------------- #
def validate() -> dict:
    """Re-check the corpus, the panel and the lexicon with the chapter's own engine."""
    rows = build_dataset()
    splits = {s: [r for r in rows if r.split == s] for s in ("train", "dev", "test")}
    for name, items in splits.items():
        assert len(items) == 10, (name, len(items))
        assert {r.operator for r in items} == {"subclassof", "some", "only", "disjoint", "type"}
        langs = [r.language for r in items]
        assert (langs.count("en"), langs.count("nl"), langs.count("de")) == (4, 3, 3), name
    by_split = {s: {r.axiom_id for r in items} for s, items in splits.items()}
    assert not (by_split["train"] & by_split["dev"] or by_split["train"] & by_split["test"]
                or by_split["dev"] & by_split["test"])
    for r in rows:
        axiom = gold_axiom(r)
        assert round_trip(r.reference, axiom, r.language)["faithful"], r.id
        assert lint(r.reference, axiom, r.language) == [], (r.id, lint(r.reference, axiom, r.language))
    lint_catches = {"P13", "P14", "P15", "P16", "P17"}
    for row in READABILITY_PANEL:
        axiom = AXIOMS[row["axiom_id"]]
        assert round_trip(row["sentence"], axiom, row["language"])["faithful"], row["id"]
        flagged = bool(lint(row["sentence"], axiom, row["language"]))
        assert flagged == (row["id"] in lint_catches), row["id"]
        assert not (flagged and row["acceptable"]), row["id"]
    for language in LANGUAGES:
        seen: dict[str, str] = {}
        for term in LEXICON:
            for form in forms(term, language):
                assert seen.setdefault(form.lower(), term) == term, (language, form)
    return {"items": len(rows), "panel": len(READABILITY_PANEL),
            "split": {s: len(v) for s, v in splits.items()}}


if __name__ == "__main__":
    print(validate())
