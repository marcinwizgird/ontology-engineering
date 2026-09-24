"""Generate the Chapter 1 notebooks.  Run:  python _build_notebooks.py"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from oe_course.nbbuild import code, exercise, header, learning_outcomes, md, save  # noqa: E402

CHAPTER = "Chapter 1 — Introduction"
LOCAL_IMPORT = """\
sys.path.insert(0, str(Path.cwd()))          # so ch01_toolkit imports
import ch01_toolkit as ch1
from oe_course import ontology as ont
from oe_course.data import corpus
import pandas as pd
pd.set_option("display.width", 120)\
"""


# --------------------------------------------------------------------------- #
def nb00():
    cells = header(
        CHAPTER,
        "Notebook 0 · Overview, setup and the course contract",
        "Keet, *Ontology Engineering* (2nd ed.), Ch. 1",
        "This course rebuilds Keet's textbook as a **practice-first graduate "
        "course**. Every claim the book makes in prose, you will make in code: "
        "measure it, test it, and defend it against a grader.",
    )
    cells += [
        md(
            "## How this chapter is organised\n\n"
            "| # | Notebook | Book section | What you produce |\n"
            "|---|---|---|---|\n"
            "| 0 | `00_overview_and_setup` | — | a working environment |\n"
            "| 1 | `01_what_an_ontology_looks_like` | 1.1 | a spectrum classifier and its evidence |\n"
            "| 2 | `02_why_ontologies_pay_off` | 1.2 | a measured integration result (recall 0 → 1) |\n"
            "| 3 | `03_what_is_an_ontology` | 1.3 | a defect scanner and a definition scorecard |\n"
            "| 4 | `04_exercises` | 1.5 | autograded answers to the book's exercises |\n"
            "| 5 | `05_assignment` / `05_solutions` | — | problem set: a Claude triage agent for an ontology registry — graded, judge-validated, optimised, gated |\n"
        ),
        md(
            learning_outcomes(
                [
                    "Distinguish an ontology from a vocabulary, a taxonomy and a thesaurus "
                    "**by measurement**, not by assertion.",
                    "Demonstrate the value of an ontology by showing a query whose answer "
                    "is wrong without one.",
                    "Argue about competing definitions of *ontology* by applying them to real "
                    "artefacts and finding where they disagree.",
                    "Detect and explain common modelling defects automatically.",
                    "Build, evaluate and optimise an agent that performs this triage, and say "
                    "honestly how good it is.",
                ]
            )
        ),
        md(
            "## Tooling\n\n"
            "| Tool | Role |\n|---|---|\n"
            "| **rdflib** | RDF graphs, Turtle, SPARQL |\n"
            "| **owlrl** | pure-Python OWL 2 RL reasoner — entailment with no Java |\n"
            "| **LangChain / LangGraph** | agent loops and decomposed pipelines |\n"
            "| **DSPy (incl. GEPA)** | programmatic prompt optimisation |\n"
            "| **Apache Jena Fuseki** | *optional* triplestore (`infra/fuseki`) |\n\n"
            "### Running against Claude\n"
            "The chapter notebooks run locally with no key. Each chapter's **problem set** "
            "calls the live Anthropic API (`claude-opus-5`): put `ANTHROPIC_API_KEY` in "
            "your shell or in `oe-course/.env` (copy `.env.example`). Every model call is "
            "billed, and every problem set states its estimated budget and asks you to "
            "report a cost next to every score. Fuseki is optional: without it the course "
            "uses an in-memory rdflib store."
        ),
        code(
            "import sys, os, json\n"
            "from pathlib import Path\n"
            "here = Path.cwd()\n"
            "for candidate in [here, *here.parents]:\n"
            "    if (candidate / 'oe_course').is_dir():\n"
            "        sys.path.insert(0, str(candidate)); break\n"
            "import oe_course\n"
            "print(json.dumps(oe_course.describe_environment(), indent=1))"
        ),
        code(LOCAL_IMPORT),
        md(
            "### Self-test: does the labelled corpus still agree with the detectors?\n\n"
            "The course ships eleven small ontologies with **hand-written** gold labels. "
            "`verify_corpus()` checks the detectors against those labels. It must print "
            "nothing — if it complains, either a detector or a label is wrong, and the "
            "exercises downstream are measuring the wrong thing."
        ),
        code(
            "problems = corpus.verify_corpus()\n"
            "print(problems or 'corpus OK: detectors agree with all hand-written labels')\n"
            "print(f'{len(corpus.CORPUS)} artefacts:', ', '.join(sorted(corpus.BY_NAME)))"
        ),
        md("### Sanity check: load the African Wildlife Ontology and measure it"),
        code(
            "awo = ont.load_graph(corpus.get('awo').turtle)\n"
            "m = ont.graph_metrics(awo)\n"
            "print(f\"{m['triples']} triples, {m['classes']} classes, \"\n"
            "      f\"{m['logical_axioms']} logical axioms, richness {m['axiom_richness']}\")\n"
            "assert m['classes'] > 10 and m['restrictions'] > 0"
        ),
    ]
    return save(cells, HERE / "00_overview_and_setup.ipynb")


# --------------------------------------------------------------------------- #
def nb01():
    cells = header(
        CHAPTER,
        "Notebook 1 · What does an ontology look like?",
        "Section 1.1",
        "The book answers this question with a picture. We answer it with a "
        "measurement — and then discover that the measurement forces us to be "
        "precise about a word the field uses loosely.",
    )
    cells += [
        code(LOCAL_IMPORT),
        md(
            "## 1. Vocabulary versus axioms\n\n"
            "An ontology has two separable parts, and conflating them is the single most "
            "common confusion in this field:\n\n"
            "* the **vocabulary** — the named terms (classes, properties, individuals);\n"
            "* the **axioms** — the logical statements that constrain what those terms can mean.\n\n"
            "A file with 500 classes and no axioms is a *word list with URIs*. Let's look at "
            "both parts of the African Wildlife Ontology separately."
        ),
        code(
            "from oe_course.sparql import SparqlStore\n"
            "store = SparqlStore.in_memory(corpus.get('awo').turtle)\n"
            "awo = ont.load_graph(corpus.get('awo').turtle)\n\n"
            "vocab = store.select('''\n"
            "  SELECT ?term ?label WHERE { ?term a owl:Class ; rdfs:label ?label }\n"
            "  ORDER BY ?label''')\n"
            "print(f'{len(vocab)} named classes')\n"
            "for row in vocab[:8]:\n"
            "    print('  ', row['label'], '  <-', row['term'].split('#')[-1])"
        ),
        md(
            "Now an **axiom**. `Giraffe` is not merely a term under `Herbivore`; the ontology "
            "commits to what giraffes eat. In OWL that commitment is a restriction, which in "
            "RDF is a blank node — the reason ontologies are painful to read as raw triples "
            "and are normally viewed through a tool."
        ),
        code(
            "q = '''SELECT ?prop ?filler WHERE {\n"
            "  awo:Giraffe rdfs:subClassOf ?r .\n"
            "  ?r a owl:Restriction ; owl:onProperty ?prop ; ?kind ?filler .\n"
            "  FILTER(?kind != rdf:type && ?kind != owl:onProperty)\n"
            "}'''\n"
            "for row in store.select(q):\n"
            "    print('Giraffe SubClassOf', row['prop'].split('#')[-1],\n"
            "          'only/some', row['filler'].split('#')[-1])\n\n"
            "print('\\nIn DL notation:  Giraffe ⊑ Herbivore ⊓ ∀eats.Leaf')"
        ),
        md(
            "## 2. The ontology spectrum, as a classifier\n\n"
            "The book places artefacts on a spectrum: **controlled vocabulary → taxonomy → "
            "thesaurus → formal ontology**. That is usually taught as a diagram to memorise. "
            "It is more useful as a *decision procedure*, because writing one forces you to "
            "state what actually separates the levels:\n\n"
            "| Level | Requires |\n|---|---|\n"
            "| controlled-vocabulary | named terms with labels |\n"
            "| taxonomy | + a subsumption hierarchy |\n"
            "| thesaurus | + associative / lexical relations (SKOS) |\n"
            "| formal-ontology | + axioms a reasoner can act on beyond subsumption |\n\n"
            "`classify_spectrum` implements exactly that, and — importantly — returns the "
            "**evidence** it used. A classifier that will not show its work cannot be argued with."
        ),
        code(
            "rows = []\n"
            "for art in corpus.CORPUS:\n"
            "    g = ont.load_graph(art.turtle)\n"
            "    m = ont.graph_metrics(g)\n"
            "    rows.append({\n"
            "        'artefact': art.name,\n"
            "        'level': ont.classify_spectrum(g)['level'],\n"
            "        'classes': m['classes'],\n"
            "        'subclass': m['subclass_axioms'],\n"
            "        'skos': m['skos_relations'],\n"
            "        'restrictions': m['restrictions'],\n"
            "        'disjoint': m['disjointness_axioms'],\n"
            "        'richness': m['axiom_richness'],\n"
            "    })\n"
            "df = pd.DataFrame(rows).sort_values('richness', ascending=False)\n"
            "df"
        ),
        code(
            "res = ont.classify_spectrum(ont.load_graph(corpus.get('food-thesaurus').turtle))\n"
            "print('food-thesaurus ->', res['level'])\n"
            "for e in res['evidence']:\n"
            "    print('   because:', e)"
        ),
        md(
            "## 3. Why `axiom_richness` is the number worth watching\n\n"
            "`axiom_richness` = logical axioms per class. It is deliberately crude, and it "
            "separates the artefacts that *say something* from the ones that merely *name "
            "things*. Watch how it tracks the spectrum level — and note where it doesn't, "
            "which is the interesting part."
        ),
        code(
            "print(df[['artefact', 'level', 'richness']].to_string(index=False))\n"
            "print('\\nMean richness by level:')\n"
            "print(df.groupby('level')['richness'].mean().sort_values().to_string())"
        ),
        md(
            "> **Discussion.** `bare-properties` and `animals-taxonomy` are both taxonomies, "
            "but their richness differs — domain/range axioms count as logical commitments "
            "even when the properties are otherwise unconstrained. Is that the right call? "
            "Defend an answer; this is the kind of judgement an ontology engineer is paid for."
        ),
    ]
    cells += exercise(
        "1.1",
        "Order the corpus by formality",
        "Without using `classify_spectrum`, rank every artefact in the corpus by how "
        "*formal* it is, using only `graph_metrics`. Then compare your ranking with the "
        "spectrum labels and identify one artefact where a pure metric ranking disagrees "
        "with the categorical label.",
        "# YOUR CODE HERE\n"
        "# ranking = ...  # list of artefact names, most formal first\n",
        "ranking = [r['artefact'] for r in sorted(\n"
        "    ({'artefact': a.name, **ont.graph_metrics(ont.load_graph(a.turtle))}\n"
        "     for a in corpus.CORPUS),\n"
        "    key=lambda r: (r['restrictions'] + r['disjointness_axioms']\n"
        "                   + r['property_characteristics'], r['axiom_richness']),\n"
        "    reverse=True)]\n"
        "print('most formal first:', ranking)\n\n"
        "levels = {a.name: a.gold_level for a in corpus.CORPUS}\n"
        "assert ranking[0] == 'awo', 'the AWO carries the most reasoner-relevant axioms'\n"
        "# The disagreement: a thesaurus outranks some taxonomies on SKOS relations,\n"
        "# but SKOS relations are *not* reasoner-relevant, so richness ranks it lower.\n"
        "print('food-thesaurus is labelled', levels['food-thesaurus'],\n"
        "      'but ranks at position', ranking.index('food-thesaurus') + 1, 'of', len(ranking))",
        hint="Reasoner-relevant axioms are restrictions, disjointness and property "
        "characteristics — subsumption alone only buys you a taxonomy.",
    )
    cells += exercise(
        "1.2",
        "Promote a taxonomy to a formal ontology",
        "`animals-taxonomy` is classified as a taxonomy. Add the **smallest** set of axioms "
        "that makes `classify_spectrum` return `formal-ontology`, and explain what real-world "
        "claim you just committed to.",
        "animals = ont.load_graph(corpus.get('animals-taxonomy').turtle)\n"
        "print('before:', ont.classify_spectrum(animals)['level'])\n"
        "# YOUR CODE HERE: add axioms to `animals`\n",
        "from rdflib import OWL, URIRef\n"
        "EX = 'http://example.org/oe/'\n"
        "animals = ont.load_graph(corpus.get('animals-taxonomy').turtle)\n"
        "print('before:', ont.classify_spectrum(animals)['level'])\n\n"
        "# One disjointness axiom is enough: it is the cheapest reasoner-relevant commitment.\n"
        "animals.add((URIRef(EX + 'Mammal'), OWL.disjointWith, URIRef(EX + 'Bird')))\n\n"
        "after = ont.classify_spectrum(animals)\n"
        "print('after: ', after['level'])\n"
        "assert after['level'] == 'formal-ontology'\n"
        "print('\\nThe commitment: nothing can be both a mammal and a bird. That is a claim\\n'\n"
        "      'about the world which a reasoner will now enforce -- and which will make\\n'\n"
        "      'certain future data *inconsistent* rather than merely odd.')",
    )
    return save(cells, HERE / "01_what_an_ontology_looks_like.ipynb")


# --------------------------------------------------------------------------- #
def nb02():
    cells = header(
        CHAPTER,
        "Notebook 2 · What is an ontology actually good for?",
        "Section 1.2 (data and information system integration)",
        "The textbook argues that ontologies help with integration. Arguments are "
        "cheap. Here we build two hospitals that genuinely cannot answer a question, "
        "add an ontology, and watch recall go from **0.0 to 1.0**.",
    )
    cells += [
        code(LOCAL_IMPORT),
        md(
            "## 1. The scenario\n\n"
            "Two hospitals record the same clinical reality with no vocabulary in common:\n\n"
            "| | Hospital A | Hospital B |\n|---|---|---|\n"
            "| patient class | `a:Patient` | `b:Client` |\n"
            "| link to disorder | `a:hasDiagnosis` | `b:condition` |\n"
            "| a heart attack is | `a:dx_I21` (ICD code) | `b:cond_heartattack` (free text) |\n\n"
            "The question we must answer across both: **which patients have a cardiac "
            "disorder?** Note that no source system has the concept 'cardiac disorder' at all."
        ),
        code("print(ch1.HOSPITAL_A.split('#')[0] and ch1.HOSPITAL_A[ch1.HOSPITAL_A.index('a:pat001'):][:400])"),
        code("print(ch1.HOSPITAL_B[ch1.HOSPITAL_B.index('b:person77'):][:400])"),
        md(
            "## 2. Attempt one: put it all in one graph\n\n"
            "The reflex solution — dump both sources into one store and query it. This is the "
            "'data lake' answer, and it is the control condition for our experiment."
        ),
        code(
            "lake = ch1.naive_union()\n"
            "print(f'{len(lake)} triples from both hospitals')\n"
            "print('cardiac patients found:', ch1.cardiac_patients(lake))\n"
            "print('\\nZero. The query asks about med:CardiacDisorder, a concept that exists\\n'\n"
            "      'in neither source. Co-location is not integration.')"
        ),
        md(
            "## 3. Attempt two: add the shared ontology and an alignment\n\n"
            "Now we introduce the missing piece — a small shared ontology, plus an "
            "**alignment** saying how each source's vocabulary maps into it. Note how small "
            "the alignment is relative to the payoff."
        ),
        code("print(ch1.ALIGNMENT[ch1.ALIGNMENT.index('a:Patient'):])"),
        code(
            "aligned = ch1.integrated(reason=False)\n"
            "print(f'{len(aligned)} triples (sources + ontology + alignment)')\n"
            "print('cardiac patients found:', ch1.cardiac_patients(aligned))\n"
            "print('\\nStill zero -- and this is the step everyone gets wrong.')"
        ),
        md(
            "> **The key insight of this notebook.** Writing the axioms down changes the "
            "*graph*; it does not change the *answers*. The alignment says `a:Patient ⊑ "
            "med:Patient`, but nothing has yet concluded that `a:pat001` **is** a "
            "`med:Patient`. Integration = alignment **+** entailment. Miss the second half and "
            "you have an expensive documentation exercise."
        ),
        md("## 4. Attempt three: run the reasoner"),
        code(
            "full = ch1.integrated(reason=True)\n"
            "print(f'{len(full)} triples after OWL 2 RL materialisation')\n"
            "for patient, disorder in ch1.cardiac_patients(full):\n"
            "    print('  ', patient.split('#')[-1], '->', disorder.split('#')[-1])"
        ),
        code(
            "report = ch1.integration_report()\n"
            "pd.DataFrame(report['rows'])"
        ),
        md(
            "Two things to notice, both of which matter in practice:\n\n"
            "1. **Recall goes 0.0 → 0.0 → 1.0.** The value is entirely in the final step.\n"
            "2. **Triples go 33 → 69 → 314.** Materialisation is not free. It trades storage "
            "and write-time for query-time simplicity — the classic choice you will meet "
            "again in Chapter 8 as *materialisation vs. query rewriting*.\n\n"
            "Also note the answer spans **both** hospitals and includes a patient whose "
            "record says only 'cardiomyopathy' — a term that never appears in the question."
        ),
    ]
    cells += exercise(
        "2.1",
        "Onboard a third hospital",
        "Hospital C arrives with yet another schema: `c:Subject` linked by `c:ails` to "
        "`c:ail_mi`, labelled 'MI'. Write the alignment triples that bring it into the "
        "integrated view, and show that the cardiac query now returns **five** patients.",
        "HOSPITAL_C = ch1._PREFIXES + '''\n"
        "@prefix c: <http://example.org/hospitalC#> .\n"
        "c:subj01 a c:Subject ; c:ails c:ail_mi .\n"
        "c:ail_mi a c:Ailment ; rdfs:label \"MI\"@en .\n"
        "'''\n"
        "# YOUR CODE HERE: write ALIGNMENT_C and rebuild the integrated graph\n",
        "HOSPITAL_C = ch1._PREFIXES + '''\n"
        "@prefix c: <http://example.org/hospitalC#> .\n"
        "c:subj01 a c:Subject ; c:ails c:ail_mi .\n"
        "c:ail_mi a c:Ailment ; rdfs:label \"MI\"@en .\n"
        "'''\n"
        "ALIGNMENT_C = ch1._PREFIXES + '''\n"
        "@prefix c: <http://example.org/hospitalC#> .\n"
        "c:Subject rdfs:subClassOf med:Patient .\n"
        "c:ails rdfs:subPropertyOf med:hasDisorder .\n"
        "c:ail_mi a med:MyocardialInfarction .\n"
        "'''\n\n"
        "import owlrl\n"
        "g = ch1.integrated(reason=False)\n"
        "g.parse(data=HOSPITAL_C, format='turtle')\n"
        "g.parse(data=ALIGNMENT_C, format='turtle')\n"
        "owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(g)\n\n"
        "found = ch1.cardiac_patients(g)\n"
        "patients = {p for p, _ in found}\n"
        "print(f'{len(patients)} cardiac patients across three hospitals:')\n"
        "for p in sorted(patients):\n"
        "    print('  ', p.split('#')[-1])\n"
        "assert len(patients) == 5\n"
        "print('\\nThree alignment triples were enough. The shared ontology did not change:\\n'\n"
        "      'that is the property that makes this approach scale to the nth source.')",
        hint="Three triples: one for the class, one for the property, one typing the ailment.",
    )
    cells += exercise(
        "2.2",
        "Use an ontology to *find an error*",
        "Section 1.2.2 claims ontologies help with more than integration. Demonstrate error "
        "detection: declare `med:CardiacDisorder` and `med:Asthma` disjoint, assert that "
        "`a:dx_J45` (asthma) is also a cardiac disorder, and write a SPARQL query that finds "
        "the individual violating disjointness.",
        "# YOUR CODE HERE\n",
        "from rdflib import Graph\n"
        "bad = ch1.integrated(reason=False)\n"
        "bad.parse(data=ch1._PREFIXES + '''\n"
        "med:CardiacDisorder owl:disjointWith med:Asthma .\n"
        "a:dx_J45 a med:CardiacDisorder .\n"
        "''', format='turtle')\n\n"
        "conflict_query = '''\n"
        "PREFIX owl: <http://www.w3.org/2002/07/owl#>\n"
        "SELECT DISTINCT ?individual ?c1 ?c2 WHERE {\n"
        "  ?c1 owl:disjointWith ?c2 .\n"
        "  ?individual a ?c1 ; a ?c2 .\n"
        "}'''\n"
        "violations = list(bad.query(conflict_query))\n"
        "for row in violations:\n"
        "    print('VIOLATION:', str(row[0]).split('#')[-1],\n"
        "          'is both', str(row[1]).split('#')[-1], 'and', str(row[2]).split('#')[-1])\n"
        "assert violations, 'the disjointness violation should be detectable'\n"
        "print('\\nWithout the disjointness axiom this data is merely wrong.\\n'\n"
        "      'With it, the error is *detectable by machine* -- which is the entire\\n'\n"
        "      'argument for paying the cost of writing axioms down.')",
    )
    return save(cells, HERE / "02_why_ontologies_pay_off.ipynb")


# --------------------------------------------------------------------------- #
def nb03():
    cells = header(
        CHAPTER,
        "Notebook 3 · What *is* an ontology, and what makes one bad?",
        "Sections 1.3.1–1.3.3",
        "The book plays 'the definition game' and then sorts ontologies into good, "
        "not-so-good and bad. We make both operational — and find that the "
        "definitions genuinely disagree about real files.",
    )
    cells += [
        code(LOCAL_IMPORT),
        md(
            "## 1. The definition game, played with a scorecard\n\n"
            "Section 1.3.1 lists competing definitions of *ontology*. Rather than choosing a "
            "favourite, encode each as a **testable predicate** over an artefact's metrics and "
            "apply all of them to the whole corpus. Where they disagree is where the field's "
            "arguments actually live."
        ),
        code(
            "for d in ch1.DEFINITIONS:\n"
            "    print(f\"{d['id']:22s} {d['gloss']}\")\n"
            "    print(f\"{'':22s} operationalised as: {d['reads_as']}\\n\")"
        ),
        code(
            "graphs = {a.name: ont.load_graph(a.turtle) for a in corpus.CORPUS}\n"
            "scorecard = pd.DataFrame(ch1.definition_scorecard(graphs)).set_index('artefact')\n"
            "scorecard"
        ),
        code(
            "disputed = scorecard[scorecard.nunique(axis=1) > 1]\n"
            "print('Artefacts the definitions DISAGREE about:\\n')\n"
            "print(disputed.to_string())\n"
            "print('\\nEach disputed row is a real argument: under Gruber it is an ontology,\\n'\n"
            "      'under Guarino it is not. Neither side is being careless.')"
        ),
        md(
            "> **Exam-style question.** `colours-vocab` counts as an ontology under "
            "Gruber-1993 and under no other definition. Is Gruber's definition too weak, or "
            "are the others too strong? Your answer should say what *work* you need the "
            "definition to do — which is the only basis on which the question can be settled."
        ),
        md(
            "## 2. Good, not-so-good and bad ontologies (§1.3.3)\n\n"
            "The book's quality discussion becomes a **defect scanner**. Each detector is "
            "syntactic and explainable: it names the term that triggered it, so a finding can "
            "always be checked by hand. That is a hard requirement — a quality tool nobody can "
            "audit will be ignored the first time it is wrong."
        ),
        code(
            "for s in ont.SMELLS:\n"
            "    print(f'{s.id}\\n    {s.title}\\n    why it matters: {s.why}\\n')"
        ),
        code(
            "rows = []\n"
            "for art in corpus.CORPUS:\n"
            "    counts = ont.smell_summary(ont.load_graph(art.turtle))\n"
            "    rows.append({'artefact': art.name, 'defects': sum(counts.values()), **counts})\n"
            "pd.DataFrame(rows).fillna(0).set_index('artefact').astype(int)"
        ),
        md("### Reading a finding\n\nEvery finding carries the evidence that produced it."),
        code(
            "for f in ont.scan_smells(ont.load_graph(corpus.get('legacy-import').turtle)):\n"
            "    print(f'[{f.smell}]')\n"
            "    print(f'  subject: {f.subject}')\n"
            "    print(f'  detail : {f.detail}\\n')"
        ),
        md(
            "### Where the scanner is deliberately conservative\n\n"
            "`staff-instance-confusion` has no sibling classes, so `no-disjointness` does "
            "**not** fire — there is nothing yet to be disjoint from. A detector that fired "
            "anyway would be technically defensible and practically useless, because engineers "
            "switch off tools that cry wolf. Precision is a design goal, not an accident."
        ),
        code(
            "g = ont.load_graph(corpus.get('staff-instance-confusion').turtle)\n"
            "print('findings:', [f.smell for f in ont.scan_smells(g)])\n"
            "print('gold labels:', sorted(corpus.get('staff-instance-confusion').gold_smells))"
        ),
    ]
    cells += exercise(
        "3.1",
        "Write a new detector",
        "Add a detector for the **lonely child** defect: a class with exactly one direct "
        "subclass. It is a taxonomy smell — a partition into one part usually means either a "
        "missing sibling or a redundant level. Register it and run it over the corpus.",
        "from oe_course.ontology import Finding, Smell\n"
        "def detect_lonely_child(g):\n"
        "    # YOUR CODE HERE: return a list of Finding objects\n"
        "    return []\n",
        "from collections import defaultdict\n"
        "from rdflib import RDFS, URIRef\n"
        "from oe_course.ontology import Finding, Smell\n\n"
        "def detect_lonely_child(g):\n"
        "    children = defaultdict(list)\n"
        "    for s, _, o in g.triples((None, RDFS.subClassOf, None)):\n"
        "        if isinstance(s, URIRef) and isinstance(o, URIRef):\n"
        "            children[o].append(s)\n"
        "    return [\n"
        "        Finding('lonely-child', str(parent),\n"
        "                f'exactly one direct subclass ({str(kids[0]).split(chr(35))[-1]}); '\n"
        "                'a one-part partition is usually a missing sibling or a redundant level')\n"
        "        for parent, kids in sorted(children.items(), key=lambda kv: str(kv[0]))\n"
        "        if len(kids) == 1\n"
        "    ]\n\n"
        "lonely = Smell('lonely-child', 'Class with a single subclass',\n"
        "               'A partition into one part carries no information and often marks an '\n"
        "               'unfinished model.', detect_lonely_child)\n\n"
        "hits = {a.name: len(detect_lonely_child(ont.load_graph(a.turtle))) for a in corpus.CORPUS}\n"
        "print({k: v for k, v in hits.items() if v})\n"
        "assert hits['animals-taxonomy'] == 1, 'Bird has exactly one subclass (Penguin)'\n"
        "print('\\nRegistering it would change the gold labels, so verify_corpus() would now\\n'\n"
        "      'fail -- correctly. Adding a detector is a breaking change to a graded rubric.')",
        hint="Count direct `rdfs:subClassOf` children per parent; report parents with exactly one.",
    )
    cells += exercise(
        "3.2",
        "Repair a broken ontology",
        "Take `broken-cycle` and repair it so the scanner reports **no** defects, without "
        "deleting classes. State which real-world claim each repair encodes.",
        "g = ont.load_graph(corpus.get('broken-cycle').turtle)\n"
        "print('before:', ont.smell_summary(g))\n"
        "# YOUR CODE HERE\n",
        "from rdflib import OWL, RDFS, URIRef\n"
        "EX = 'http://example.org/oe/'\n"
        "g = ont.load_graph(corpus.get('broken-cycle').turtle)\n"
        "print('before:', ont.smell_summary(g))\n\n"
        "# Repair 1: break the cycle. Vehicle is the general concept, Car the specific one,\n"
        "# so the axiom 'Vehicle SubClassOf Car' is the wrong one and must go.\n"
        "g.remove((URIRef(EX + 'Vehicle'), RDFS.subClassOf, URIRef(EX + 'Car')))\n\n"
        "# Repair 2: commit to Car and Lorry being different kinds of thing.\n"
        "g.add((URIRef(EX + 'Car'), OWL.disjointWith, URIRef(EX + 'Lorry')))\n\n"
        "print('after: ', ont.smell_summary(g))\n"
        "assert ont.smell_summary(g) == {}\n"
        "print('level now:', ont.classify_spectrum(g)['level'])\n"
        "print('\\nRepair 1 asserts a direction of generality; repair 2 asserts that no\\n'\n"
        "      'single vehicle is both a car and a lorry. Both are claims about the world\\n'\n"
        "      'that a domain expert must sign off -- the tool can find the defect, but it\\n'\n"
        "      'cannot decide which axiom was the wrong one.')",
    )
    return save(cells, HERE / "03_what_is_an_ontology.ipynb")


# --------------------------------------------------------------------------- #
def nb04():
    cells = header(
        CHAPTER,
        "Notebook 4 · Exercises",
        "Section 1.5",
        "The book's review questions and exercises, recast as executable tasks. "
        "Every solution asserts — the assertions *are* the marking scheme.",
    )
    cells += [code(LOCAL_IMPORT)]
    cells += [
        md(
            "## Review questions (§1.5)\n\n"
            "The book asks these in prose. Answer each by producing evidence from the corpus, "
            "not by recalling a definition."
        )
    ]
    cells += exercise(
        "R1",
        "What distinguishes a taxonomy from an ontology?",
        "Produce two artefacts from the corpus that differ *only* in this respect, and the "
        "single metric that separates them.",
        "# YOUR CODE HERE\n",
        "tax = ont.load_graph(corpus.get('animals-taxonomy').turtle)\n"
        "onto = ont.load_graph(corpus.get('awo').turtle)\n"
        "mt, mo = ont.graph_metrics(tax), ont.graph_metrics(onto)\n\n"
        "print(f\"{'metric':28s}{'taxonomy':>10s}{'ontology':>10s}\")\n"
        "for k in ['classes', 'subclass_axioms', 'restrictions',\n"
        "          'disjointness_axioms', 'property_characteristics']:\n"
        "    print(f'{k:28s}{mt[k]:>10d}{mo[k]:>10d}')\n\n"
        "assert mt['subclass_axioms'] > 0 and mo['subclass_axioms'] > 0\n"
        "assert mt['restrictions'] == 0 and mo['restrictions'] > 0\n"
        "print('\\nBoth have a hierarchy. Only one constrains what its terms may mean.\\n'\n"
        "      'The separating metric is restrictions (axioms beyond subsumption).')",
    )
    cells += exercise(
        "R2",
        "Give an example where an ontology changes a query answer",
        "Show a query returning nothing on raw data and something correct after entailment. "
        "Report the recall difference numerically.",
        "# YOUR CODE HERE\n",
        "before = len({p for p, _ in ch1.cardiac_patients(ch1.naive_union())})\n"
        "after = len({p for p, _ in ch1.cardiac_patients(ch1.integrated(reason=True))})\n"
        "print(f'cardiac patients found -- raw union: {before}, integrated+reasoned: {after}')\n"
        "assert before == 0 and after == 4\n"
        "print(f'recall {before/4:.2f} -> {after/4:.2f}')",
    )
    cells += exercise(
        "R3",
        "Name three properties of a 'good' ontology and test them",
        "Choose three properties that are checkable, and evaluate the AWO against them.",
        "# YOUR CODE HERE\n",
        "awo = ont.load_graph(corpus.get('awo').turtle)\n"
        "m = ont.graph_metrics(awo)\n"
        "checks = {\n"
        "    'every class is documented (labelled)':\n"
        "        not any(f.smell == 'missing-label' for f in ont.scan_smells(awo)),\n"
        "    'properties carry domain and range':\n"
        "        not any(f.smell == 'property-without-domain-or-range'\n"
        "                for f in ont.scan_smells(awo)),\n"
        "    'the hierarchy is acyclic':\n"
        "        not any(f.smell == 'subsumption-cycle' for f in ont.scan_smells(awo)),\n"
        "}\n"
        "for name, ok in checks.items():\n"
        "    print(f\"  [{'PASS' if ok else 'FAIL'}] {name}\")\n"
        "assert all(checks.values())\n"
        "print('\\nNote what is NOT checkable this way: whether the ontology is *true*,\\n'\n"
        "      'or useful for its purpose. Those need a domain expert and a use case.')",
    )
    cells += [md("## Exercises (§1.5)")]
    cells += exercise(
        "E1",
        "Classify an unseen artefact",
        "Write Turtle for a small artefact of your own that lands on **thesaurus** — not "
        "taxonomy, not formal ontology — and prove it.",
        "my_ttl = '''\n"
        "@prefix owl:  <http://www.w3.org/2002/07/owl#> .\n"
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .\n"
        "@prefix ex:   <http://example.org/mine#> .\n"
        "# YOUR CODE HERE\n"
        "'''\n",
        "my_ttl = '''\n"
        "@prefix owl:  <http://www.w3.org/2002/07/owl#> .\n"
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .\n"
        "@prefix ex:   <http://example.org/mine#> .\n\n"
        "ex:Instrument a owl:Class ; rdfs:label \"instrument\"@en .\n"
        "ex:Strings    a owl:Class ; rdfs:label \"strings\"@en ;\n"
        "              rdfs:subClassOf ex:Instrument ; skos:broader ex:Instrument .\n"
        "ex:Violin     a owl:Class ; rdfs:label \"violin\"@en ;\n"
        "              rdfs:subClassOf ex:Strings ; skos:related ex:Viola .\n"
        "ex:Viola      a owl:Class ; rdfs:label \"viola\"@en ;\n"
        "              rdfs:subClassOf ex:Strings ; skos:related ex:Violin .\n"
        "'''\n"
        "g = ont.load_graph(my_ttl)\n"
        "result = ont.classify_spectrum(g)\n"
        "print(result['level'])\n"
        "for e in result['evidence']:\n"
        "    print('  -', e)\n"
        "assert result['level'] == 'thesaurus'\n"
        "print('\\nTo stay a thesaurus it must have SKOS relations and NO restrictions,\\n'\n"
        "      'disjointness or property characteristics. Adding one owl:disjointWith\\n'\n"
        "      'would reclassify it immediately.')",
    )
    cells += exercise(
        "E2",
        "Build a defect that no current detector catches",
        "Construct a small ontology that is clearly badly modelled but that `scan_smells` "
        "reports as clean. This is an exercise in the **limits** of automated quality checks.",
        "# YOUR CODE HERE\n",
        "sneaky = '''\n"
        "@prefix owl:  <http://www.w3.org/2002/07/owl#> .\n"
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "@prefix ex:   <http://example.org/sneaky#> .\n\n"
        "# Modelling a part-whole relation as subsumption: a wheel is NOT a kind of car.\n"
        "ex:Car   a owl:Class ; rdfs:label \"car\"@en .\n"
        "ex:Wheel a owl:Class ; rdfs:label \"wheel\"@en ; rdfs:subClassOf ex:Car .\n"
        "ex:Door  a owl:Class ; rdfs:label \"door\"@en ; rdfs:subClassOf ex:Car .\n"
        "ex:Car owl:disjointWith ex:Person .\n"
        "ex:Person a owl:Class ; rdfs:label \"person\"@en .\n"
        "'''\n"
        "g = ont.load_graph(sneaky)\n"
        "print('scanner says:', ont.smell_summary(g) or 'clean')\n"
        "assert ont.smell_summary(g) == {}\n"
        "print('\\nYet Wheel SubClassOf Car asserts that every wheel IS a car -- the classic\\n'\n"
        "      'is-a / part-of confusion (Keet Ch. 6.2). No syntactic detector catches it,\\n'\n"
        "      'because syntactically it is a perfectly ordinary subsumption axiom.\\n'\n"
        "      'Catching it needs either a foundational ontology or a human. That is the\\n'\n"
        "      'honest boundary of the tooling in this chapter.')",
        hint="Think about a relation that is *not* subsumption being modelled as subsumption.",
    )
    cells += [
        md(
            "## Where this chapter leaves you\n\n"
            "You can now measure what an artefact is, show what it is worth, and detect a "
            "class of defects automatically — *and* you have seen exactly where automation "
            "stops (Exercise E2). Notebook 5 asks the next question: can an **agent** do this "
            "triage, and how would you know whether it does it well?"
        )
    ]
    return save(cells, HERE / "04_exercises.ipynb")


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    for build in (nb00, nb01, nb02, nb03, nb04):
        written = build()
        for path in (written if isinstance(written, tuple) else (written,)):
            print("wrote", path.name)
