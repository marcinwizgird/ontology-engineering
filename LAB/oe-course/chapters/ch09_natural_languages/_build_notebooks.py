"""Generate the Chapter 9 notebooks.  Run:  python _build_notebooks.py"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from oe_course.nbbuild import code, exercise, header, learning_outcomes, md, save  # noqa: E402

CHAPTER = "Chapter 9 — Ontologies and Natural Languages"

BOOT = """\
import sys, json, logging
from pathlib import Path
here = Path.cwd()
for candidate in [here, *here.parents]:
    if (candidate / "oe_course").is_dir():
        sys.path.insert(0, str(candidate)); break
sys.path.insert(0, str(Path.cwd()))

import ch09_toolkit as ch9
import pandas as pd
logging.getLogger("dspy").setLevel(logging.WARNING)\
"""


# --------------------------------------------------------------------------- #
def nb00():
    cells = header(
        CHAPTER,
        "Notebook 0 · Overview and setup",
        "Keet, *Ontology Engineering* (2nd ed.), Ch. 9",
        "An ontology nobody can read gets reviewed by nobody. Chapter 9 is "
        "about closing that gap in both directions — rendering axioms as "
        "readable sentences, and doing it in more than one language.",
    )
    cells += [
        code(BOOT),
        code("import oe_course; print(json.dumps(oe_course.describe_environment(), indent=1))"),
        md(
            "## Notebooks in this chapter\n\n"
            "| # | Notebook | Book section | What you build |\n|---|---|---|---|\n"
            "| 0 | `00_overview_and_setup` | — | environment check |\n"
            "| 1 | `01_verbalisation` | 9.2 | a verbaliser **and its inverse** |\n"
            "| 2 | `02_multilingual` | 9.1 | lexicons, coverage, and where translation leaks |\n"
            "| 3 | `03_exercises` | 9.3 | autograded answers |\n"
            "| 4 | `04_assignment` / `04_solutions` | — | problem set: a Claude verbaliser for multilingual review sheets, a validated judge, and an **optimal-stopping MDP** |\n"
        ),
        md(
            learning_outcomes(
                [
                    "Verbalise axioms in controlled natural language, and **parse the "
                    "sentences back** to check fidelity exactly.",
                    "Explain why a controlled language is the price of having an inverse.",
                    "Separate an ontology from its lexicons, and measure translation "
                    "coverage per language.",
                    "State precisely what a round-trip check **cannot** see — and build the "
                    "measurement that can.",
                    "Derive the stopping rule for best-of-n sampling.",
                ]
            )
        ),
        md(
            "## Why this chapter matters for evaluation\n\n"
            "Almost everything in this course needs gold labels, a reasoner, or a judge. "
            "Verbalisation needs none of them: it has an **inverse**. Verbalise, parse back, "
            "compare — the grader is a function.\n\n"
            "> That makes it the right place to be honest about the limits of exact metrics. "
            "`\"No plant is a animal.\"` round-trips **perfectly** and is still wrong English. "
            "Notebook 1 shows exactly that, which is the most useful thing in the chapter."
        ),
        md("### Sanity check: verbalise and recover every sample axiom"),
        code(
            "results = [ch9.round_trips(a, 'en') for a in ch9.SAMPLE_AXIOMS]\n"
            "print(f\"{sum(r['ok'] for r in results)}/{len(results)} axioms survive the round trip\")\n"
            "assert all(r['ok'] for r in results)"
        ),
    ]
    return save(cells, HERE / "00_overview_and_setup.ipynb")


# --------------------------------------------------------------------------- #
def nb01():
    cells = header(
        CHAPTER,
        "Notebook 1 · Verbalisation, and the inverse that grades it",
        "Section 9.2",
        "Rendering an axiom as a sentence is easy. Rendering it so that the "
        "sentence can be turned back into the same axiom is what makes the "
        "output trustworthy — and it is why the language has to be "
        "*controlled*.",
    )
    cells += [
        code(BOOT),
        md(
            "## 1. Templates\n\n"
            "One template per construct. This is a **controlled** natural language: a "
            "deliberately small fragment of English, chosen so that parsing it back is "
            "possible at all."
        ),
        code(
            "for operator, template in ch9.TEMPLATES['en'].items():\n"
            "    print(f'  {operator:12s} {template}')"
        ),
        code(
            "for axiom in ch9.SAMPLE_AXIOMS:\n"
            "    print(f'{str(axiom):48s} -> {ch9.verbalise(axiom)}')"
        ),
        md(
            "## 2. The inverse\n\n"
            "`parse_cnl` runs the templates backwards. Note the ordering constraint in the "
            "grammar: `Every X eats only Y` must be tried **before** the bare `Every X is a "
            "Y`, or the general pattern swallows the specific one. Ordering the rules is the "
            "entire difficulty of parsing a CNL."
        ),
        code(
            "sentence = 'Every lion eats at least one herbivore.'\n"
            "print('sentence :', sentence)\n"
            "print('recovered:', ch9.parse_cnl(sentence))\n"
            "print()\n"
            "print('free prose does not parse:', ch9.parse_cnl('Lions tend to eat herbivores.'))"
        ),
        md(
            "## 3. The round trip is the grader\n\n"
            "Verbalise, parse, compare. No gold labels, no annotation, no judge — and the "
            "answer is exact."
        ),
        code(
            "rows = [ch9.round_trips(a) for a in ch9.SAMPLE_AXIOMS]\n"
            "print(pd.DataFrame(rows)[['sentence', 'recovered', 'ok']].to_string(index=False))\n"
            "assert all(r['ok'] for r in rows)"
        ),
        md(
            "## 4. What the round trip cannot see\n\n"
            "Here is the most important cell in the chapter. Look at the disjointness "
            "sentence."
        ),
        code(
            "bad = ch9.verbalise(ch9.Axiom('Plant', 'disjoint', 'Animal'))\n"
            "print('sentence      :', bad)\n"
            "print('round-trips OK:', ch9.round_trips(ch9.Axiom('Plant', 'disjoint', 'Animal'))['ok'])\n"
            "print()\n"
            "print('readability   :', json.dumps(ch9.readability(bad), indent=1))"
        ),
        md(
            "> **`\"No plant is a animal.\"`** The round trip is perfect: parse it back and "
            "you recover exactly `Plant DisjointWith Animal`. And it is still wrong English.\n\n"
            "The round trip tests whether the *inverse function* works. It has nothing to say "
            "about whether a human would accept the output — and verbalisation exists solely "
            "so that humans will read it. **An exact metric that measures the wrong thing is "
            "still measuring the wrong thing.** This is the concrete case for keeping a judge "
            "alongside a decision procedure, and the problem set (`04_assignment`) scores both halves separately."
        ),
        code(
            "print('every sample sentence, scored for readability:\\n')\n"
            "rows = []\n"
            "for a in ch9.SAMPLE_AXIOMS:\n"
            "    s = ch9.verbalise(a)\n"
            "    r = ch9.readability(s)\n"
            "    rows.append({'sentence': s, 'wrong article': r['wrong_article'],\n"
            "                 'identifier leak': r['contains_identifier'],\n"
            "                 'score': r['score']})\n"
            "print(pd.DataFrame(rows).to_string(index=False))\n"
            "print('\\nEvery one of these round-trips perfectly.')"
        ),
    ]
    cells += exercise(
        "1.1",
        "Fix the article without breaking the round trip",
        "Repair `\"No plant is a animal.\"` so it reads correctly, and confirm the corrected "
        "sentence still parses back to the same axiom.",
        "# YOUR CODE HERE\n",
        "import re\n"
        "axiom = ch9.Axiom('Plant', 'disjoint', 'Animal')\n"
        "original = ch9.verbalise(axiom)\n"
        "fixed = re.sub(r'\\ba (?=[aeiou])', 'an ', original, flags=re.I)\n"
        "print('before:', original, '->', ch9.readability(original)['score'])\n"
        "print('after :', fixed, '->', ch9.readability(fixed)['score'])\n\n"
        "recovered = ch9.parse_cnl(fixed)\n"
        "print('\\nstill round-trips:', recovered is not None and recovered.key() == axiom.key())\n"
        "assert recovered.key() == axiom.key()\n"
        "assert ch9.readability(fixed)['score'] > ch9.readability(original)['score']\n"
        "print('\\nThe parser accepts \\'a\\' or \\'an\\' (the pattern is `is an?`), so the fix\\n'\n"
        "      'costs nothing in fidelity. That is the ideal case: a presentation problem\\n'\n"
        "      'that can be fixed without touching meaning. Pluralisation (\\'eats only\\n'\n"
        "      'leaf\\') is the harder cousin -- see Exercise 1.2.')",
        hint="`is an?` in the parser pattern already accepts both forms.",
    )
    cells += exercise(
        "1.2",
        "Find a sentence that is faithful and unacceptable",
        "`Every giraffe eats only leaf.` round-trips. Explain what is wrong with it, and say "
        "what the toolkit would need in order to detect the problem automatically.",
        "# YOUR CODE HERE\n",
        "axiom = ch9.Axiom('Giraffe', 'only', 'Leaf', 'eats')\n"
        "sentence = ch9.verbalise(axiom)\n"
        "print('sentence      :', sentence)\n"
        "print('round-trips   :', ch9.round_trips(axiom)['ok'])\n"
        "print('readability   :', ch9.readability(sentence)['score'])\n"
        "assert ch9.round_trips(axiom)['ok']\n"
        "print('\\nThe universal restriction reads as a bare singular: \"only leaf\" should\\n'\n"
        "      'be \"only leaves\". The readability check scores it 1.0 because it looks\\n'\n"
        "      'for articles and identifiers, not number agreement.\\n\\n'\n"
        "      'Detecting it needs a plural form in the lexicon -- i.e. the lexicon must\\n'\n"
        "      'carry MORPHOLOGY, not just a string per language. That is exactly what\\n'\n"
        "      'lemon models and why §9.1 treats a lexicon as a structured artefact\\n'\n"
        "      'rather than a translation table.')",
    )
    return save(cells, HERE / "01_verbalisation.ipynb")


# --------------------------------------------------------------------------- #
def nb02():
    cells = header(
        CHAPTER,
        "Notebook 2 · Multilingual ontologies",
        "Section 9.1",
        "The axioms are language-independent; the labels are not. That single "
        "separation is what lets one ontology serve many languages — and it is "
        "also where half-translated ontologies hide.",
    )
    cells += [
        code(BOOT),
        md(
            "## 1. One ontology, several lexicons\n\n"
            "Note what does **not** change between languages: the terms. `Giraffe` is the "
            "ontology's identifier in every language; only its surface form differs."
        ),
        code(
            "rows = [{'term': term, **labels} for term, labels in ch9.LEXICON.items()]\n"
            "print(pd.DataFrame(rows).to_string(index=False))"
        ),
        code(
            "axiom = ch9.Axiom('Lion', 'some', 'Herbivore', 'eats')\n"
            "print('axiom:', axiom, '\\n')\n"
            "for language in ch9.LANGUAGES:\n"
            "    print(f'  {language}: {ch9.verbalise(axiom, language)}')"
        ),
        md(
            "## 2. The round trip works in every language\n\n"
            "Each language has its own templates and its own reverse lexicon, so fidelity is "
            "checkable per language."
        ),
        code(
            "rows = []\n"
            "for language in ch9.LANGUAGES:\n"
            "    ok = sum(ch9.round_trips(a, language)['ok'] for a in ch9.SAMPLE_AXIOMS)\n"
            "    rows.append({'language': language, 'round-trips': f'{ok}/{len(ch9.SAMPLE_AXIOMS)}'})\n"
            "print(pd.DataFrame(rows).to_string(index=False))\n"
            "assert all(ch9.round_trips(a, l)['ok']\n"
            "           for a in ch9.SAMPLE_AXIOMS for l in ch9.LANGUAGES)"
        ),
        md(
            "## 3. Coverage: what a language is missing\n\n"
            "Translation is rarely complete. `label_for` falls back to the identifier, so an "
            "unlexicalised term renders as its IRI fragment — quietly."
        ),
        code(
            "for language in ch9.LANGUAGES:\n"
            "    print(' ', ch9.lexicon_coverage(language))"
        ),
        code(
            "partial = {k: dict(v) for k, v in ch9.LEXICON.items()}\n"
            "for term in ['Herbivore', 'Leaf', 'isPartOf']:\n"
            "    partial[term].pop('nl', None)          # simulate an incomplete translation\n"
            "original = ch9.LEXICON\n"
            "ch9.LEXICON = partial\n"
            "try:\n"
            "    print('coverage now:', ch9.lexicon_coverage('nl')['coverage'])\n"
            "    print('missing     :', ch9.lexicon_coverage('nl')['missing'])\n"
            "    print()\n"
            "    for a in ch9.SAMPLE_AXIOMS[:3]:\n"
            "        print('  ', ch9.verbalise(a, 'nl'))\n"
            "finally:\n"
            "    ch9.LEXICON = original"
        ),
        md(
            "> **`Elke giraf is een Herbivore.`** — Dutch grammar, an English noun, and no "
            "error anywhere. This is what a half-translated ontology looks like in "
            "production: mostly right, quietly wrong, and impossible to spot without "
            "measuring coverage per language."
        ),
        md(
            "## 4. Fidelity does not imply translation\n\n"
            "Worse: the sentence above still **round-trips**. The parser falls back to "
            "returning an unknown label unchanged, so the axiom is recovered exactly. An "
            "exact metric reports success on a sentence that is not really Dutch."
        ),
        code(
            "sentence = 'Elke giraf is een Herbivore.'\n"
            "recovered = ch9.parse_cnl(sentence, 'nl')\n"
            "print('sentence :', sentence)\n"
            "print('recovered:', recovered)\n"
            "print('faithful :', recovered.key() == ch9.SAMPLE_AXIOMS[0].key())\n"
            "print()\n"
            "print('but is it Dutch?')\n"
            "print(json.dumps(ch9.uses_lexicon_labels(sentence, ch9.SAMPLE_AXIOMS[0], 'nl'), indent=1))"
        ),
        code(
            "good = ch9.verbalise(ch9.SAMPLE_AXIOMS[0], 'nl')\n"
            "print('properly localised:', good)\n"
            "print(json.dumps(ch9.uses_lexicon_labels(good, ch9.SAMPLE_AXIOMS[0], 'nl'), indent=1))\n"
            "print('\\nTwo different checks, two different questions: \"did the meaning\\n'\n"
            "      'survive?\" and \"is this the requested language?\". Neither implies the\\n'\n"
            "      'other, which is why the Chapter 9 metric scores both.')"
        ),
    ]
    cells += exercise(
        "2.1",
        "Add a fourth language",
        "Add French labels for four terms, verbalise an axiom, and report coverage. State "
        "what would break if you added the labels but not a template set.",
        "# YOUR CODE HERE\n",
        "original = {k: dict(v) for k, v in ch9.LEXICON.items()}\n"
        "try:\n"
        "    ch9.LEXICON['Giraffe']['fr'] = 'girafe'\n"
        "    ch9.LEXICON['Herbivore']['fr'] = 'herbivore'\n"
        "    ch9.LEXICON['Lion']['fr'] = 'lion'\n"
        "    ch9.LEXICON['Animal']['fr'] = 'animal'\n"
        "    print('fr coverage:', ch9.lexicon_coverage('fr')['coverage'])\n"
        "    print('fr missing :', ch9.lexicon_coverage('fr')['missing'][:5], '...')\n"
        "    print('\\nlabels resolve:', ch9.label_for('Giraffe', 'fr'),\n"
        "          '/', ch9.label_for('Herbivore', 'fr'))\n"
        "    try:\n"
        "        ch9.verbalise(ch9.SAMPLE_AXIOMS[0], 'fr')\n"
        "        print('verbalised in French')\n"
        "    except KeyError as exc:\n"
        "        print('\\nverbalisation FAILS:', repr(exc))\n"
        "        print('A lexicon is not enough. Verbalisation needs TEMPLATES too, and\\n'\n"
        "              'templates encode grammar -- article agreement, word order,\\n'\n"
        "              'inflection. Adding a language is a grammar job, not a glossary job,\\n'\n"
        "              'which is the practical reason multilingual ontologies stall.')\n"
        "finally:\n"
        "    ch9.LEXICON.clear(); ch9.LEXICON.update(original)",
        hint="`verbalise` looks up `TEMPLATES[language]`, not just the lexicon.",
    )
    cells += exercise(
        "2.2",
        "Measure how much translation is really done",
        "Report, per language, the fraction of the sample axioms that verbalise using **only** "
        "that language's labels.",
        "# YOUR CODE HERE\n",
        "rows = []\n"
        "for language in ch9.LANGUAGES:\n"
        "    localised = sum(\n"
        "        ch9.uses_lexicon_labels(ch9.verbalise(a, language), a, language)['ok']\n"
        "        for a in ch9.SAMPLE_AXIOMS)\n"
        "    rows.append({'language': language,\n"
        "                 'fully localised': f'{localised}/{len(ch9.SAMPLE_AXIOMS)}',\n"
        "                 'lexicon coverage': ch9.lexicon_coverage(language)['coverage']})\n"
        "print(pd.DataFrame(rows).to_string(index=False))\n"
        "assert all(r['lexicon coverage'] == 1.0 for r in rows)\n"
        "print('\\nWith a complete lexicon every axiom localises fully. The number to watch\\n'\n"
        "      'in a real project is the FIRST column: coverage of the vocabulary is not\\n'\n"
        "      'the same as coverage of the sentences people actually generate, because\\n'\n"
        "      'a single missing term spoils every axiom that mentions it.')",
    )
    return save(cells, HERE / "02_multilingual.ipynb")


# --------------------------------------------------------------------------- #
def nb03():
    cells = header(
        CHAPTER,
        "Notebook 3 · Exercises",
        "Section 9.3",
        "The book's exercises, executable. Assertions are the marking scheme.",
    )
    cells += [code(BOOT)]
    cells += exercise(
        "R1",
        "Verbalise five axioms and verify each",
        "Verbalise five axioms in English and confirm each recovers exactly.",
        "# YOUR CODE HERE\n",
        "axioms = ch9.SAMPLE_AXIOMS[:5]\n"
        "rows = [ch9.round_trips(a) for a in axioms]\n"
        "print(pd.DataFrame(rows)[['axiom', 'sentence', 'ok']].to_string(index=False))\n"
        "assert all(r['ok'] for r in rows)",
    )
    cells += exercise(
        "R2",
        "Show why the language must be controlled",
        "Give three paraphrases of one axiom that a human would accept, and show how many "
        "the parser accepts. Draw the conclusion.",
        "# YOUR CODE HERE\n",
        "paraphrases = [\n"
        "    'Every giraffe is a herbivore.',\n"
        "    'All giraffes are herbivores.',\n"
        "    'Giraffes are herbivores.',\n"
        "    'A giraffe is always a herbivore.',\n"
        "]\n"
        "for text in paraphrases:\n"
        "    print(f'{str(ch9.parse_cnl(text)):46s} <- {text}')\n"
        "accepted = sum(ch9.parse_cnl(t) is not None for t in paraphrases)\n"
        "print(f'\\n{accepted}/{len(paraphrases)} accepted')\n"
        "assert accepted < len(paraphrases)\n"
        "print('\\nEnglish offers many ways to say one thing; a parser with an inverse can\\n'\n"
        "      'afford exactly one. That is the trade a CONTROLLED language makes:\\n'\n"
        "      'expressive range for invertibility. Widen the grammar and you lose the\\n'\n"
        "      'free grader this chapter is built on.')",
    )
    cells += exercise(
        "R3",
        "Report translation status for a release",
        "Produce a per-language table a project manager could act on: coverage, missing "
        "terms, and how many axioms are affected by each missing term.",
        "# YOUR CODE HERE\n",
        "original = {k: dict(v) for k, v in ch9.LEXICON.items()}\n"
        "try:\n"
        "    for term in ['Leaf', 'isPartOf']:\n"
        "        ch9.LEXICON[term].pop('de', None)\n"
        "    status = ch9.lexicon_coverage('de')\n"
        "    print('coverage:', status['coverage'], 'missing:', status['missing'])\n"
        "    rows = []\n"
        "    for term in status['missing']:\n"
        "        affected = [a for a in ch9.SAMPLE_AXIOMS\n"
        "                    if term in (a.subject, a.filler, a.property)]\n"
        "        rows.append({'missing term': term, 'axioms affected': len(affected)})\n"
        "    print(pd.DataFrame(rows).to_string(index=False))\n"
        "    assert sum(r['axioms affected'] for r in rows) >= 2\n"
        "    print('\\nRanking missing terms by axioms affected turns \"finish the\\n'\n"
        "          'translation\" into a prioritised list -- the same move Chapter 5 made\\n'\n"
        "          'with competency-question coverage.')\n"
        "finally:\n"
        "    ch9.LEXICON.clear(); ch9.LEXICON.update(original)",
    )
    cells += [
        md(
            "## Where this leaves you\n\n"
            "You have a generator with an exact inverse, a measurement of what that inverse "
            "cannot see, and a per-language coverage report. The problem set (`04_assignment`) "
            "gives the job to Claude and asks the question every LLM engineer eventually asks: **when should I "
            "stop resampling?**"
        )
    ]
    return save(cells, HERE / "03_exercises.ipynb")


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    for build in (nb00, nb01, nb02, nb03):
        written = build()
        for path in (written if isinstance(written, tuple) else (written,)):
            print("wrote", path.name)
