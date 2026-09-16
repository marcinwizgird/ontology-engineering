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
            "| 4 | `04_agentic_lab` | — | a verbaliser agent + an **optimal-stopping MDP** |\n"
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
            "alongside a decision procedure, and Notebook 4 scores both halves separately."
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
            "cannot see, and a per-language coverage report. Notebook 4 gives the job to an "
            "agent and asks the question every LLM engineer eventually asks: **when should I "
            "stop resampling?**"
        )
    ]
    return save(cells, HERE / "03_exercises.ipynb")


# --------------------------------------------------------------------------- #
def nb04():
    cells = header(
        CHAPTER,
        "Notebook 4 · Agentic lab — verbalising, and when to stop resampling",
        "Extends §9.1–9.2",
        "A task with a free exact grader, a second half that the exact grader "
        "cannot judge, and the course's first **optimal-stopping** MDP — which "
        "is best-of-n sampling with the arithmetic done.",
    )
    cells += [
        code(BOOT),
        code(
            "import ch09_agentic as AG\n"
            "from oe_course import evaluation as ev, llm, mdp, optimize as opt\n"
            "import oe_course\n"
            "print(json.dumps(oe_course.describe_environment(), indent=1))"
        ),
        md(
            learning_outcomes(
                [
                    "Build an agent graded by a **function**, with no gold labels anywhere.",
                    "Score fidelity and presentation separately, and see an agent max one "
                    "while failing the other.",
                    "Derive the **stopping rule** for best-of-n sampling by value iteration.",
                    "Explain why the threshold falls as the budget runs out.",
                ]
            )
        ),
        md("> **Prerequisite:** the Chapter 1 agentic lab."),
        md(
            "## 1. Tools\n\n"
            "`check_round_trip` is the unusual one: it is a **grader the agent can call on "
            "itself**. Most tasks in this course require a gold answer to know whether the "
            "output is right; here the agent can find out unaided, before submitting."
        ),
        code(
            "ctx = AG.Ch9Context()\n"
            "tools = {t.name: t for t in AG.build_toolset(ctx)}\n"
            "for name, t in tools.items():\n"
            "    print(f'{name:20s} {list(t.args_schema.model_json_schema().get(\"properties\", {}))}')\n"
            "    print(f'{\"\":20s} {t.description.splitlines()[0]}')"
        ),
        code(
            "print(tools['lookup_label'].invoke({'term': 'Herbivore', 'language': 'de'}))\n"
            "print(tools['check_round_trip'].invoke(\n"
            "    {'sentence': 'Every lion eats at least one herbivore.', 'language': 'en'}))\n"
            "print(tools['check_round_trip'].invoke(\n"
            "    {'sentence': 'Lions tend to eat herbivores.', 'language': 'en'}))\n"
            "print(tools['check_readability'].invoke({'sentence': 'No plant is a animal.'}))\n"
            "print('\\ntrajectory:', ctx.log.names())"
        ),
        md(
            "## 2. The dataset and the two-part metric\n\n"
            "Every sample axiom in every language — 24 examples, stratified on "
            "`(construct, language)` so both halves see every construct in every language.\n\n"
            "The score is **half fidelity, half presentation**:\n\n"
            "| half | measured by | kind |\n|---|---|---|\n"
            "| does it mean the right thing? | round trip | exact decision procedure |\n"
            "| would anyone read it? | readability + lexicon check | proxy for a judge |"
        ),
        code(
            "train, dev = AG.build_dataset('train'), AG.build_dataset('dev')\n"
            "print(f'train {len(train)}, dev {len(dev)}')\n"
            "print('train constructs:', sorted({e.operator for e in train}))\n"
            "print('dev   constructs:', sorted({e.operator for e in dev}))\n"
            "print('train languages :', sorted({e.language for e in train}))\n"
            "print('dev   languages :', sorted({e.language for e in dev}))"
        ),
        code(
            "lm = llm.configure_dspy(AG.CNL_RULEBOOK, AG.cnl_responder)\n"
            "baseline = AG.VerbalisationProgram()\n"
            "example = dev[0]\n"
            "pred = baseline(**example.inputs())\n"
            "print('axiom    :', example.axiom, f'({example.language})')\n"
            "print('produced :', repr(pred.sentence))\n"
            "report = AG.verbalisation_scorer(example, pred)\n"
            "print('score    :', report.score)\n"
            "for n in report.notes:\n"
            "    print('   ', n)"
        ),
        code(
            "before = ev.evaluate_dataset(baseline, dev, AG.verbalisation_scorer)\n"
            "print('BEFORE:', before['mean_score'])\n"
            "print('violations:', before['violations'])"
        ),
        md(
            "## 3. GEPA\n\n"
            "Each construct has its **own** rule, so each discovery pays off immediately. "
            "That is a deliberate design choice: an earlier draft gated the templates behind "
            "a single meta-rule, and improvement stayed invisible until *two* rules were "
            "found together — a credit-assignment trap that stalled the optimiser completely."
        ),
        code(
            "gepa_metric = ev.make_gepa_metric(AG.verbalisation_scorer, AG.CNL_RULEBOOK)\n"
            "reflect = llm.reflection_lm(AG.CNL_RULEBOOK, AG.cnl_responder)\n"
            "tuned = opt.run_gepa(baseline, train, gepa_metric, valset=train,\n"
            "                     max_metric_calls=180, reflection_lm=reflect)\n"
            "result = opt.compare(AG.VerbalisationProgram(), tuned, dev, AG.verbalisation_scorer)\n"
            "print(result.report()[:1500])"
        ),
        code(
            "found = AG.CNL_RULEBOOK.active_in(result.instruction_after)\n"
            "print(f'rules discovered: {len(found)}/{len(AG.CNL_RULEBOOK.ids)}')\n"
            "print('missed:', sorted(set(AG.CNL_RULEBOOK.ids) - found) or 'none')"
        ),
        md(
            "### The rule the exact metric could not have taught\n\n"
            "`use-the-lexicon-label` is worth dwelling on. An agent that uses English "
            "identifiers in a Dutch sentence still **round-trips perfectly** — the parser "
            "falls back to returning an unknown label unchanged, so fidelity looks flawless.\n\n"
            "Only the presentation half notices. Had the metric been fidelity alone, this "
            "agent would have scored full marks while emitting sentences that are not in the "
            "requested language."
        ),
        code(
            "faithful_but_english = 'Elke giraf is een Herbivore.'\n"
            "axiom = ch9.SAMPLE_AXIOMS[0]\n"
            "recovered = ch9.parse_cnl(faithful_but_english, 'nl')\n"
            "print('sentence  :', faithful_but_english)\n"
            "print('round-trip:', recovered.key() == axiom.key())\n"
            "print('is Dutch  :', ch9.uses_lexicon_labels(faithful_but_english, axiom, 'nl')['ok'])\n"
            "print('\\nA metric made only of the exact half would have called this perfect.')"
        ),
        md(
            "## 4. Optimal stopping: when to stop resampling\n\n"
            "The agent drafts a verbalisation, sees its quality, and decides: accept, or pay "
            "to draw again? This is **best-of-n sampling**, and it is a decision problem with "
            "an exact answer.\n\n"
            "| | |\n|---|---|\n"
            "| **S** | attempts spent, and the best quality in hand |\n"
            "| **A** | `accept` the current draft, or `retry` |\n"
            "| **T** | **stochastic** — a fresh draft's quality is drawn, not chosen |\n"
            "| **R** | `-cost` per attempt; on accept, the quality accepted |"
        ),
        code(
            "M = AG.RevisionMDP(qualities=(0.4, 0.7, 1.0), probabilities=(0.5, 0.3, 0.2),\n"
            "                   cost=0.05, max_attempts=4)\n"
            "print('quality ladder :', M.qualities)\n"
            "print('draw probability:', M.probabilities)\n"
            "print('cost per attempt:', M.cost, ' budget:', M.max_attempts)\n"
            "V, pi = mdp.value_iteration(M)\n"
            "print(f'\\nV*(s0) = {V[M.initial_state()]:.4f}')\n"
            "print(f'expected quality of a single draw = '\n"
            "      f'{sum(q * p for q, p in zip(M.qualities, M.probabilities)):.3f}')"
        ),
        md("### The stopping rule, derived:"),
        code("print(pd.DataFrame(M.thresholds(pi)).to_string(index=False))"),
        md(
            "> **Read the table by row.** With attempts to spare, the agent rejects anything "
            "below the top quality and draws again. On the **last** attempt it accepts "
            "whatever it holds, because there is nothing left to trade.\n\n"
            "That is the classic optimal-stopping shape: a **threshold that falls as the "
            "budget runs out**. Nobody encoded it — value iteration derived it from the cost "
            "and the distribution. If you have ever run best-of-n sampling and guessed at "
            "`n`, this is the arithmetic you were guessing at."
        ),
        code(
            "import random\n"
            "random.seed(0)\n"
            "rows = []\n"
            "for cost in [0.0, 0.05, 0.15, 0.3, 0.5]:\n"
            "    Mc = AG.RevisionMDP(cost=cost)\n"
            "    Vc, pic = mdp.value_iteration(Mc)\n"
            "    lengths = [len(mdp.run_episode(Mc, mdp.greedy_policy(pic))) - 1\n"
            "               for _ in range(300)]\n"
            "    rows.append({'cost per attempt': cost,\n"
            "                 'V*': round(Vc[Mc.initial_state()], 4),\n"
            "                 'mean attempts': round(sum(lengths) / len(lengths), 2)})\n"
            "print(pd.DataFrame(rows).to_string(index=False))\n"
            "print('\\nFree attempts -> sample until you hit the best draft. Expensive\\n'\n"
            "      'attempts -> take the first thing you get. Everything in between is the\\n'\n"
            "      'interesting case, and it is where real systems live.')"
        ),
    ]
    cells += exercise(
        "4.1",
        "Find the budget beyond which more sampling does not pay",
        "Sweep `max_attempts` and report where `V*` stops improving materially. Explain the "
        "shape of the curve.",
        "# YOUR CODE HERE\n",
        "rows = []\n"
        "previous = None\n"
        "for budget in range(1, 9):\n"
        "    Mb = AG.RevisionMDP(max_attempts=budget)\n"
        "    Vb, _ = mdp.value_iteration(Mb)\n"
        "    value = Vb[Mb.initial_state()]\n"
        "    rows.append({'max attempts': budget, 'V*': round(value, 4),\n"
        "                 'gain': '-' if previous is None else round(value - previous, 4)})\n"
        "    previous = value\n"
        "print(pd.DataFrame(rows).to_string(index=False))\n"
        "gains = [r['gain'] for r in rows if r['gain'] != '-']\n"
        "assert gains[-1] < gains[0]\n"
        "print('\\nDiminishing returns, and quickly: each extra attempt only helps in the\\n'\n"
        "      'worlds where every earlier draw was poor, and those get rarer\\n'\n"
        "      'geometrically. Past a handful of attempts you are paying full price for\\n'\n"
        "      'an increasingly unlikely improvement -- which is why best-of-64 is almost\\n'\n"
        "      'never worth 64 times best-of-1.')",
    )
    cells += exercise(
        "4.2",
        "Score fidelity only, and watch the language break",
        "Build a metric that scores **only** the round trip, optimise against it, and show "
        "the resulting agent scoring well while producing sentences that are not in the "
        "requested language.",
        "# YOUR CODE HERE\n",
        "from oe_course.evaluation import ScoreReport\n\n"
        "def fidelity_only(gold, pred):\n"
        "    sentence = str(getattr(pred, 'sentence', '') or '').strip()\n"
        "    axiom = ch9.Axiom(gold.subject, gold.operator, gold.filler, gold.property)\n"
        "    recovered = ch9.parse_cnl(sentence, gold.language)\n"
        "    ok = bool(recovered) and recovered.key() == axiom.key()\n"
        "    notes = [] if ok else [f'Does not recover {axiom}.']\n"
        "    violated = [] if ok else [f'template-for-{axiom.operator}']\n"
        "    return ScoreReport(float(ok), notes, violated)\n\n"
        "blind_metric = ev.make_gepa_metric(fidelity_only, AG.CNL_RULEBOOK)\n"
        "blind = opt.run_gepa(AG.VerbalisationProgram(), train, blind_metric, valset=train,\n"
        "                     max_metric_calls=140, reflection_lm=reflect)\n"
        "blind_rules = AG.CNL_RULEBOOK.active_in(opt.instruction_of(blind))\n"
        "print('rules discovered:', sorted(blind_rules))\n"
        "print('lexicon rule learned?', 'use-the-lexicon-label' in blind_rules)\n\n"
        "fidelity = ev.evaluate_dataset(blind, dev, fidelity_only)['mean_score']\n"
        "full = ev.evaluate_dataset(blind, dev, AG.verbalisation_scorer)['mean_score']\n"
        "print(f'\\nscored on fidelity only : {fidelity}')\n"
        "print(f'scored on the full metric: {full}')\n"
        "assert 'use-the-lexicon-label' not in blind_rules\n"
        "assert full < fidelity\n"
        "print('\\nNear-perfect on the metric it was optimised against, and worse on the\\n'\n"
        "      'one that reflects the job. The exact half was never wrong -- it was\\n'\n"
        "      'INCOMPLETE, and an optimiser will find whatever your metric forgot to\\n'\n"
        "      'measure. That is the argument for pairing a decision procedure with a\\n'\n"
        "      'judge rather than choosing between them.')",
    )
    cells += exercise(
        "4.3",
        "Let the agent grade itself before answering",
        "Show that an agent calling `check_round_trip` can reject its own bad draft without "
        "any gold answer, and argue what that changes about deployment.",
        "# YOUR CODE HERE\n",
        "ctx2 = AG.Ch9Context()\n"
        "t2 = {t.name: t for t in AG.build_toolset(ctx2)}\n"
        "drafts = ['Giraffe subclassof Herbivore',\n"
        "          'Giraffes are herbivores.',\n"
        "          'Every giraffe is a herbivore.']\n"
        "for draft in drafts:\n"
        "    verdict = json.loads(t2['check_round_trip'].invoke(\n"
        "        {'sentence': draft, 'language': 'en'}))\n"
        "    print(f\"{str(verdict['parses']):5s} {draft!r:44s} -> {verdict['recovered']}\")\n"
        "accepted = [d for d in drafts\n"
        "            if json.loads(t2['check_round_trip'].invoke(\n"
        "                {'sentence': d, 'language': 'en'}))['parses']]\n"
        "assert accepted == ['Every giraffe is a herbivore.']\n"
        "print('\\ntool calls:', len(ctx2.log.names()))\n"
        "print('\\nThe agent discarded two of three drafts using only a function it can\\n'\n"
        "      'call. That is worth more than it looks: a self-checkable task can be\\n'\n"
        "      'deployed with a guarantee rather than a hope, and the optimal-stopping\\n'\n"
        "      'MDP above is exactly the policy for using such a check under a budget.')",
    )
    cells += [
        md(
            "## Chapter 9 in the course arc\n\n"
            "| | Ch. 8 | Ch. 9 |\n|---|---|---|\n"
            "| MDP | serve under staleness | **optimal stopping** |\n"
            "| grader | two paths must agree | **a function and its inverse** |\n"
            "| what it teaches about metrics | agreement needs no oracle | an exact metric can still be incomplete |\n\n"
            "Chapters 8 and 9 make the same point from opposite directions. Chapter 8: the "
            "best checks need no gold answer. Chapter 9: even a *perfect* check only measures "
            "what it measures. Both are arguments for building the evaluation deliberately "
            "rather than reaching for whichever metric is easiest to compute."
        )
    ]
    return save(cells, HERE / "04_agentic_lab.ipynb")


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    for build in (nb00, nb01, nb02, nb03, nb04):
        print("wrote", build().name)
