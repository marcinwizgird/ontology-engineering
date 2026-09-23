"""Generate the Chapter 1 notebooks.  Run:  python _build_notebooks.py"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from oe_course.nbbuild import code, exercise, header, learning_outcomes, md, save  # noqa: E402
from oe_course.assignment import save_assignment, task  # noqa: E402

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
            "| 5 | `05_agentic_lab` | — | an evaluated, optimised, self-improving agent |\n"
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
            "### Two modes, one codebase\n"
            "Everything runs **offline** with no API key and no Docker: a deterministic "
            "simulator stands in for the LLM, and an in-memory rdflib graph stands in for "
            "Fuseki. Set `ANTHROPIC_API_KEY` and the *same code* runs against Claude.\n\n"
            "> The offline LLM is a **simulator, not a model**. It is honest about what it "
            "is: a weak agent that follows explicit instructions. That is enough to make "
            "the optimisation labs real (the score genuinely moves, for a reason you can "
            "read), and not enough to tell you anything about Claude's ability. Numbers you "
            "obtain offline describe the simulator."
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
def nb05():
    cells = header(
        CHAPTER,
        "Notebook 5 · Agentic lab — build, formalise, evaluate, optimise, improve",
        "Extends Ch. 1 beyond the book",
        "Notebooks 1–4 built a *program* that triages an ontology. This notebook "
        "builds an **agent** that does the same job, and then does the harder "
        "part: says how good it is, proves the number, and improves it without "
        "fooling itself.",
    )
    cells += [
        code(LOCAL_IMPORT),
        code(
            "import json\n"
            "from oe_course import (agents, evaluation as ev, llm, mdp,\n"
            "                       optimize as opt, programs as pr, tools as T)\n"
            "from oe_course.config import offline\n"
            "print('offline mode (simulated LLM):', offline())"
        ),
        md(
            learning_outcomes(
                [
                    "Expose domain capabilities as **function tools** with trigger conditions, "
                    "and log every call.",
                    "Compare a single agent loop against an explicitly **decomposed** pipeline "
                    "on score *and* cost.",
                    "Formalise the task as an **MDP**, solve it exactly, and report the agent's "
                    "**regret** against the optimal policy.",
                    "Build an evaluation dataset and three kinds of metric: deterministic, "
                    "LLM-as-judge, and **GEPA-shaped feedback**.",
                    "Optimise the agent's instruction with **DSPy GEPA** and attribute the gain "
                    "to a specific instruction change.",
                    "Package the result as a versioned **skill**, and run a **self-improvement** "
                    "loop behind a held-out promotion gate.",
                ]
            )
        ),
        md(
            "> **Read the mode line above.** Offline, the LLM is a deterministic simulator: a "
            "weak agent that follows explicit instructions and ignores everything else. It "
            "makes every number here reproducible and every optimisation real — but the "
            "numbers describe *the simulator*, not Claude. Set `ANTHROPIC_API_KEY` to run the "
            "identical code against a live model and get numbers about the model."
        ),
        # --- 1. tools -------------------------------------------------------
        md(
            "## 1. Function tools\n\n"
            "An agent can only do what its tools let it do, so tool design *is* agent design. "
            "Three conventions are used throughout this course, and each one is load-bearing:\n\n"
            "1. **Tools are bound to a workspace, not to globals.** A `ToolContext` holds the "
            "store and the artefact; tools close over it. Two students, two contexts, no "
            "shared state.\n"
            "2. **Descriptions state a trigger, not just a behaviour.** *\"Call this whenever "
            "asked to review or critique an ontology\"* beats *\"scans for defects\"*. Models "
            "select tools from the description; a description that omits *when* leaves the "
            "choice to chance.\n"
            "3. **Every call is logged.** The log is the trajectory, the cost, and — in §3 — "
            "the MDP episode."
        ),
        code(
            "ctx = T.ToolContext()\n"
            "toolset = T.build_toolset(ctx)\n"
            "for t in toolset:\n"
            "    params = list(t.args_schema.model_json_schema().get('properties', {}))\n"
            "    print(f'{t.name:20s} {params}')\n"
            "    print(f'{\"\":20s} {t.description.splitlines()[0]}')"
        ),
        md(
            "### The SPARQL tool talks to Fuseki when Fuseki is there\n\n"
            "`SparqlStore.auto()` probes the local Fuseki (`infra/fuseki`, "
            "`docker compose up -d`) and silently falls back to an in-memory rdflib dataset "
            "with the same API. The agent code does not change — which is the point: the "
            "**tool boundary** is what makes the backend swappable."
        ),
        code(
            "from oe_course.sparql import SparqlStore, fuseki_available\n"
            "print('Fuseki reachable:', fuseki_available())\n"
            "auto = SparqlStore.auto()\n"
            "print('agent will use backend:', auto.backend)\n\n"
            "auto.load_text(corpus.get('awo').turtle)\n"
            "rows = auto.select('SELECT ?c WHERE { ?c rdfs:subClassOf awo:Herbivore }')\n"
            "print('herbivores:', [r['c'].split('#')[-1] for r in rows])"
        ),
        # --- 2. agent vs pipeline ------------------------------------------
        md(
            "## 2. One loop, or a decomposed pipeline?\n\n"
            "The obvious construction is a single ReAct-style loop: one model, one tool belt, "
            "one prompt, model decides the order. Let's run it and read the trajectory."
        ),
        code(
            "agent, actx = agents.build_agent()\n"
            "run = agents.run_agent(agent, actx, \"Triage the artefact named 'legacy-import'.\")\n"
            "print('trajectory:', ' -> '.join(actx.log.names()))\n"
            "print('cost:', actx.log.summary())\n"
            "print('\\nanswer:\\n', run.answer)"
        ),
        md(
            "Now the **functionally decomposed** alternative: `plan → act → draft → critique` "
            "as separate LangGraph nodes. It costs more to build and constrains the model. It "
            "buys three things:\n\n"
            "* each stage can be prompted, evaluated and optimised **independently**;\n"
            "* the `critique` stage is a *verification* step with access to the raw tool "
            "output, so a hallucinated defect id **cannot survive it**;\n"
            "* the trajectory is legible by construction."
        ),
        code(
            "pipe, pctx = agents.build_pipeline()\n"
            "out = pipe.invoke({'task': 'triage', 'artefact': 'legacy-import'})\n"
            "print('answer :', json.dumps(out['answer'], indent=1))\n"
            "print('critique:', out['critique'])\n"
            "print('cost    :', pctx.log.summary())"
        ),
        md(
            "### The critic earns its keep only when the drafter is wrong\n\n"
            "Above, the critic reported *\"all claims supported\"* — it did nothing. That is "
            "the honest result, and it is why decomposition should be **measured, not "
            "assumed**. Let's inject a hallucinated defect and watch the critic catch what a "
            "single loop would have emitted."
        ),
        code(
            "evidence = {'scan_smells': [{'smell': 'subsumption-cycle', 'subject': 'ex:Process'}]}\n"
            "draft = {'level': 'taxonomy',\n"
            "         'smells': ['subsumption-cycle', 'class-as-individual'],  # 2nd is invented\n"
            "         'justification': '...'}\n"
            "found = {f['smell'] for f in evidence['scan_smells']}\n"
            "kept = sorted(set(draft['smells']) & found)\n"
            "dropped = sorted(set(draft['smells']) - found)\n"
            "print('claimed  :', draft['smells'])\n"
            "print('supported:', kept)\n"
            "print('DROPPED as unsupported:', dropped)\n"
            "print('\\nA verification stage with access to raw tool output turns a whole class\\n'\n"
            "      'of hallucination into an impossibility rather than an unlikelihood.')"
        ),
        # --- 3. MDP ---------------------------------------------------------
        md(
            "## 3. The task as a Markov decision process\n\n"
            "\"Is the agent efficient?\" is unanswerable as posed. Formalise the task as an MDP "
            "and it becomes arithmetic.\n\n"
            "| | Triage task |\n|---|---|\n"
            "| **S** | the evidence gathered so far, plus whether we have committed |\n"
            "| **A** | one tool call per kind of evidence, plus `submit` |\n"
            "| **T** | deterministic for a fixed artefact — the tools are pure functions of the graph |\n"
            "| **R** | `-cost` per tool call; on `submit`, the **evaluation metric's score** |\n"
            "| **γ** | 1.0 — finite horizon, no reason to discount |\n\n"
            "The reward deliberately *contains* the evaluation metric. The thing GEPA "
            "optimises, the thing the grader measures, and the thing the MDP rewards must be "
            "one function; if they differ, you are optimising something you are not measuring."
        ),
        code(
            "EVIDENCE = ['metrics', 'spectrum', 'smells', 'catalogue', 'sparql']\n\n"
            "def answer_quality(evidence):\n"
            "    \"\"\"What score is achievable from this evidence set?\n\n"
            "    Spectrum and smells each carry half the marks (mirroring triage_scorer).\n"
            "    The other tools are legitimate but do not add score -- they are the\n"
            "    temptation the cost term exists to resist.\n"
            "    \"\"\"\n"
            "    return (0.5 * ('spectrum' in evidence)) + (0.5 * ('smells' in evidence))\n\n"
            "M = mdp.EvidenceMDP(EVIDENCE, answer_quality, step_cost=0.05)\n"
            "V, pi = mdp.value_iteration(M)\n"
            "s0 = M.initial_state()\n"
            "print(f'|S| = {len(M.states())}, V*(s0) = {V[s0]:.3f}')\n"
            "best = mdp.run_episode(M, mdp.greedy_policy(pi))\n"
            "print('optimal policy:', ' -> '.join(best.actions))\n"
            "print('optimal return:', round(best.discounted_return(), 3))"
        ),
        md(
            "The optimal policy buys **exactly** the two evidence kinds that carry score and "
            "then commits. Now replay what our real agent did, in the same vocabulary, and "
            "measure the gap."
        ),
        code(
            "TOOL_TO_EVIDENCE = {\n"
            "    'graph_metrics': 'metrics', 'spectrum_position': 'spectrum',\n"
            "    'scan_smells': 'smells', 'smell_catalogue': 'catalogue',\n"
            "    'sparql_select': 'sparql', 'sparql_ask': 'sparql',\n"
            "    # load_artefact / list_artefacts map to nothing: overhead, but still charged\n"
            "}\n"
            "gold = {a.name: a for a in corpus.CORPUS}['legacy-import']\n"
            "agent_answer = json.loads(run.answer)\n"
            "achieved = ev.set_f1(agent_answer['smells'], gold.gold_smells)[2] * 0.5 \\\n"
            "         + ev.exact_match(agent_answer['level'], gold.gold_level) * 0.5\n\n"
            "episode = mdp.episode_from_tool_log(actx.log, M, TOOL_TO_EVIDENCE, achieved)\n"
            "for t in episode.transitions:\n"
            "    print(f'  {str(t.state):28s} --{t.action:18s}--> r={t.reward:+.2f}')\n"
            "G = episode.discounted_return()\n"
            "print(f'\\nagent return   G = {G:.3f}')\n"
            "print(f'optimal        V* = {V[s0]:.3f}')\n"
            "print(f'REGRET            = {V[s0] - G:.3f}')"
        ),
        md(
            "> **What the regret is telling you.** The agent scored full marks on the answer, "
            "so all of its regret is *procedural*: it paid for `load_artefact` (unavoidable "
            "overhead this model does not credit) and for `graph_metrics` (genuinely "
            "unnecessary for the score as defined). This is a far more actionable diagnosis "
            "than \"the agent seems a bit chatty\" — and notice it is a criticism of the "
            "**reward model** as much as of the agent: if you believe metrics *should* be "
            "gathered, the reward is wrong, not the agent."
        ),
        code(
            "print('random policy value :', round(mdp.policy_value(M, mdp.random_policy(), 400), 3))\n"
            "print('agent return        :', round(G, 3))\n"
            "print('optimal value       :', round(V[s0], 3))\n"
            "print('\\nAn agent that beats random but trails optimal is the normal case.\\n'\n"
            "      'The number to report is the gap, and where it comes from.')"
        ),
        # --- 4. evaluation --------------------------------------------------
        md(
            "## 4. Evaluation: a dataset and three kinds of metric\n\n"
            "### 4.1 The dataset\n"
            "Eleven artefacts with **hand-written** gold labels, split **by artefact** — never "
            "by random row. Leaking an artefact across the split would let the optimiser "
            "memorise its answer and report a number that means nothing."
        ),
        code(
            "train = ev.build_triage_dataset('train')\n"
            "dev = ev.build_triage_dataset('dev')\n"
            "print(f'train {len(train)}, dev {len(dev)} (disjoint artefacts)')\n"
            "assert not ({e.artefact for e in train} & {e.artefact for e in dev})\n"
            "for e in dev:\n"
            "    print(f'  {e.artefact:26s} {e.level:22s} {e.smells}')"
        ),
        md(
            "### 4.2 Deterministic metric\n"
            "Half the mark for the spectrum level, half for the F1 over defect ids. Cheap, "
            "reproducible, and the only sound basis for a regression test. It cannot judge "
            "prose — that is the next metric's job."
        ),
        code(
            "class FakePred:\n"
            "    level, smells = 'taxonomy', ['subsumption-cycle', 'missing-label']\n"
            "gold_ex = [e for e in train if e.artefact == 'broken-cycle'][0]\n"
            "report = ev.triage_scorer(gold_ex, FakePred())\n"
            "print('score:', round(report.score, 3))\n"
            "for n in report.notes:\n"
            "    print('  note:', n)\n"
            "print('  violated rules:', report.violated)"
        ),
        md(
            "### 4.3 LLM-as-judge\n"
            "Some qualities are not set comparisons: *is the justification grounded in "
            "evidence the agent actually gathered, or is it plausible-sounding fabrication?* "
            "That needs a judge.\n\n"
            "> Offline this degrades to an explicit **rubric proxy** — stated plainly rather "
            "than dressed up as a model. It exercises the judging machinery (dataset, "
            "aggregation, disagreement analysis) at zero cost; it is not an LLM's opinion."
        ),
        code(
            "grounded = ('This is a taxonomy: the scanner returned 3 findings and the graph '\n"
            "            'has 4 classes with 3 subsumption axioms and 0 restrictions.')\n"
            "vague = 'This ontology looks about right for its purpose.'\n"
            "for name, text in [('grounded', grounded), ('vague', vague)]:\n"
            "    r = ev.judge('triage an ontology', 'taxonomy', text)\n"
            "    print(f'{name:9s} -> {r.score:.2f}  {r.notes}')"
        ),
        md(
            "### 4.4 The GEPA feedback metric — the one people skip\n\n"
            "GEPA improves a program by **reflecting on textual feedback**. If the metric "
            "returns only a number, every reflection step sees *\"this trajectory got a score "
            "of 0.35\"* and has nothing to work with — optimisation stalls and people conclude "
            "GEPA doesn't work.\n\n"
            "Our scorers therefore emit a *diagnosis*, including machine-readable "
            "`MISSING RULE <id>: <what to do instead>` lines. Here is what the optimiser "
            "actually reads:"
        ),
        code(
            "gepa_metric = ev.make_gepa_metric(ev.triage_scorer, pr.TRIAGE_RULEBOOK)\n"
            "fb = gepa_metric(gold_ex, FakePred())\n"
            "print('score:', round(fb.score, 3))\n"
            "print('feedback the reflection step reads:\\n')\n"
            "print(fb.feedback)"
        ),
        # --- 5. DSPy + GEPA --------------------------------------------------
        md(
            "## 5. Optimising the agent with DSPy and GEPA\n\n"
            "### 5.1 The program\n"
            "`TriageProgram` splits the work deliberately: **tools measure, the model "
            "judges**. Evidence gathering is deterministic code; exactly one LM call "
            "interprets the evidence. That makes the system cheaper, more reproducible, and "
            "tractable to optimise — there is precisely one instruction that matters."
        ),
        code(
            "lm = llm.configure_dspy(pr.TRIAGE_RULEBOOK, pr.triage_responder)\n"
            "print('task LM:', lm.model)\n"
            "baseline = pr.TriageProgram()\n"
            "print('\\nstarting instruction:\\n ', opt.instruction_of(baseline))\n"
            "print('\\nprediction on an unseen artefact:')\n"
            "print(json.dumps(dict(baseline(artefact='loose-ends')), indent=1))"
        ),
        code(
            "before = ev.evaluate_dataset(baseline, dev, ev.triage_scorer)\n"
            "print('BEFORE — mean score:', before['mean_score'])\n"
            "print('BEFORE — violations:', before['violations'])"
        ),
        md(
            "### 5.2 Run GEPA\n"
            "Optimise on `train`, report on `dev`. `max_metric_calls` is the real cost dial — "
            "with a live model, every call is a billed request."
        ),
        code(
            "import logging; logging.getLogger('dspy').setLevel(logging.WARNING)\n"
            "reflect = llm.reflection_lm(pr.TRIAGE_RULEBOOK, pr.triage_responder)\n"
            "tuned = opt.run_gepa(baseline, train, gepa_metric,\n"
            "                     valset=train, max_metric_calls=40, reflection_lm=reflect)\n"
            "result = opt.compare(pr.TriageProgram(), tuned, dev, ev.triage_scorer)\n"
            "print(result.report())"
        ),
        md(
            "### 5.3 Read the diff, not just the number\n\n"
            "The score moved because the instruction acquired **specific, checkable rules** "
            "that the metric's feedback named. That is the finding. \"The number went up\" is "
            "not a finding: a rise you cannot attribute to a concrete instruction change is "
            "usually noise, leakage, or an artefact of the split.\n\n"
            "Note also which rule GEPA did **not** discover — the training set never punished "
            "it, so there was no signal to learn from. Your dataset bounds what optimisation "
            "can find."
        ),
        code(
            "found = pr.TRIAGE_RULEBOOK.active_in(result.instruction_after)\n"
            "print('rules discovered  :', sorted(found))\n"
            "print('rules NOT found   :', sorted(set(pr.TRIAGE_RULEBOOK.ids) - found))\n"
            "print('\\ntrain-set violations that provided the signal:')\n"
            "print(' ', ev.evaluate_dataset(pr.TriageProgram(), train, ev.triage_scorer)['violations'])"
        ),
        # --- 6. skills -------------------------------------------------------
        md(
            "## 6. Package it as a skill\n\n"
            "A skill is **not a prompt**. It is a versioned bundle of the instruction, the "
            "tools it assumes, the dataset, and the metric. Separating them is how agent "
            "systems rot: someone edits the prompt, the dataset that justified it lives "
            "elsewhere, and nobody can say whether the change helped.\n\n"
            "The **skill card** is the deliverable: what it does, how well, measured on what, "
            "at which version. An agent with no card makes no claim."
        ),
        code(
            "from oe_course.skills import Skill\n"
            "triage_skill = Skill(\n"
            "    name='ontology-triage',\n"
            "    description='Place an ontology on the spectrum and list its modelling defects.',\n"
            "    build=lambda instruction: pr.TriageProgram(instruction),\n"
            "    scorer=ev.triage_scorer,\n"
            "    dataset=dev,\n"
            "    instruction=pr.BASELINE_INSTRUCTION,\n"
            "    tools=['load_artefact', 'graph_metrics', 'spectrum_position', 'scan_smells'],\n"
            ")\n"
            "triage_skill.evaluate()\n"
            "print(triage_skill.card())"
        ),
        # --- 7. self improvement ---------------------------------------------
        md(
            "## 7. A self-improving agent — and the gate that keeps it honest\n\n"
            "The loop is easy to state: run the skill, keep the episodes it got wrong, "
            "re-optimise on those, adopt the result.\n\n"
            "**The last clause is the whole discipline.** A loop that adopts whatever the "
            "optimiser returns does not improve — it *drifts*, and it drifts confidently, "
            "because the same run that produced the change also produced the evidence for it. "
            "So three datasets are kept strictly apart:\n\n"
            "| dataset | who may look at it |\n|---|---|\n"
            "| `experience` | mined for failures; **never** scored against for promotion |\n"
            "| `train` | the optimiser |\n"
            "| `holdout` | **only** the promotion gate |\n\n"
            "Plus a minimum margin, so noise on a small holdout cannot ratchet the skill sideways."
        ),
        code(
            "from oe_course.selfimprove import SelfImprovingSkill\n\n"
            "fresh = Skill(name='ontology-triage', description=triage_skill.description,\n"
            "              build=lambda i: pr.TriageProgram(i), scorer=ev.triage_scorer,\n"
            "              dataset=dev, instruction=pr.BASELINE_INSTRUCTION,\n"
            "              tools=triage_skill.tools)\n\n"
            "sis = SelfImprovingSkill(\n"
            "    fresh, holdout=dev,\n"
            "    optimise=lambda prog, tr: opt.run_gepa(prog, tr, gepa_metric,\n"
            "                                          max_metric_calls=30, reflection_lm=reflect),\n"
            "    min_gain=0.01,\n"
            ")\n"
            "sis.run_all(train)          # deploy: serve requests, remember what happened\n"
            "print(sis.report())"
        ),
        md(
            "The experience buffer now holds real failures and a **violation histogram** — the "
            "improvement agenda, derived from what the agent actually got wrong in the field "
            "rather than from what we imagined it would get wrong."
        ),
        code(
            "round1 = sis.improve()\n"
            "print(round1)\n"
            "round2 = sis.improve()\n"
            "print(round2)\n"
            "print()\n"
            "print(fresh.card())"
        ),
        md(
            "> **The second round is the important one.** It was **rejected**: the candidate "
            "showed no gain on the holdout, so the skill stayed at v2 and the attempt was "
            "recorded. A self-improvement loop that never rejects anything is not a "
            "self-improvement loop — it is a random walk with good PR."
        ),
        code(
            "print('rounds run      :', len(sis.rounds))\n"
            "print('promotions      :', sum(r.promoted for r in sis.rounds))\n"
            "print('current version :', fresh.version)\n"
            "print('rollback works  :', bool(fresh.rollback()) and fresh.version)"
        ),
    ]
    cells += task(
        "5.1",
        "Make the cost model change the optimal policy",
        "In §3 the optimal policy gathered two evidence kinds. Find the `step_cost` at which "
        "the optimal policy changes to gathering **only one**, and explain what that threshold "
        "means for an agent operating under a budget.",
        "# YOUR CODE HERE: sweep step_cost and record the optimal action sequence\n",
        "rows = []\n"
        "for cost in [0.0, 0.05, 0.1, 0.2, 0.25, 0.3, 0.5, 0.6]:\n"
        "    Mc = mdp.EvidenceMDP(EVIDENCE, answer_quality, step_cost=cost)\n"
        "    Vc, pic = mdp.value_iteration(Mc)\n"
        "    ep = mdp.run_episode(Mc, mdp.greedy_policy(pic))\n"
        "    gathered = [a for a in ep.actions if a != 'submit']\n"
        "    rows.append({'step_cost': cost, 'n_gathered': len(gathered),\n"
        "                 'policy': ' -> '.join(ep.actions),\n"
        "                 'V*': round(Vc[Mc.initial_state()], 3)})\n"
        "df_cost = pd.DataFrame(rows)\n"
        "print(df_cost.to_string(index=False))\n\n"
        "switch = df_cost[df_cost.n_gathered < 2]['step_cost'].min()\n"
        "print(f'\\nThe policy drops to fewer than two lookups at step_cost = {switch}')\n"
        "assert switch <= 0.6\n"
        "print('Each evidence kind is worth exactly 0.5 of score, so buying it pays while\\n'\n"
        "      'cost < 0.5, is a tie at cost = 0.5 (V* = 0, and ties here resolve toward\\n'\n"
        "      'gathering), and is a loss above it. Past the threshold the agent should\\n'\n"
        "      'answer from less evidence -- a rational response to a budget, not laziness.\\n'\n"
        "      'An agent that always gathers everything is not being careful; it is\\n'\n"
        "      'ignoring price.')",
        hint="Sweep `step_cost`, re-run `value_iteration`, and look at when the optimal "
        "action sequence gets shorter.",
    )
    cells += task(
        "5.2",
        "Break the optimiser by weakening the metric",
        "Replace the GEPA feedback metric with a bare float metric (no diagnosis) and re-run "
        "the optimisation. Report what happens to the discovered rules, and explain why.",
        "# YOUR CODE HERE\n",
        "plain = ev.make_metric(ev.triage_scorer)\n"
        "def blind_metric(gold, pred, trace=None, pred_name=None, pred_trace=None):\n"
        "    import dspy\n"
        "    return dspy.Prediction(score=plain(gold, pred), feedback='')\n\n"
        "blind_tuned = opt.run_gepa(pr.TriageProgram(), train, blind_metric,\n"
        "                           valset=train, max_metric_calls=30, reflection_lm=reflect)\n"
        "blind_result = opt.compare(pr.TriageProgram(), blind_tuned, dev, ev.triage_scorer)\n"
        "print('with diagnostic feedback :', result.after['mean_score'])\n"
        "print('with score-only feedback :', blind_result.after['mean_score'])\n"
        "print('rules discovered blind   :',\n"
        "      sorted(pr.TRIAGE_RULEBOOK.active_in(blind_result.instruction_after)))\n"
        "assert blind_result.after['mean_score'] <= result.after['mean_score']\n"
        "print('\\nReflection can only write down what the metric told it. A score with no\\n'\n"
        "      'diagnosis names no failure, so the proposer has nothing specific to add.\\n'\n"
        "      'This is the single most common reason GEPA \"does not work\" in practice.')",
    )
    cells += task(
        "5.3",
        "Add a rule and prove the loop finds it",
        "The dataset never punished `ground-in-tool-output`, so GEPA never learned it. "
        "Construct an evaluation that *does* punish it, and show the rule is then discovered.",
        "# YOUR CODE HERE\n",
        "def strict_scorer(gold, pred):\n"
        "    report = ev.triage_scorer(gold, pred)\n"
        "    text = str(getattr(pred, 'justification', ''))\n"
        "    if not any(ch.isdigit() for ch in text):\n"
        "        report.score *= 0.5\n"
        "        report.notes.append('Justification cites no numbers from the tools.')\n"
        "        report.violated = list(dict.fromkeys(report.violated + ['ground-in-tool-output']))\n"
        "    return report\n\n"
        "strict_gepa = ev.make_gepa_metric(strict_scorer, pr.TRIAGE_RULEBOOK)\n"
        "strict_tuned = opt.run_gepa(pr.TriageProgram(), train, strict_gepa,\n"
        "                            valset=train, max_metric_calls=40, reflection_lm=reflect)\n"
        "discovered = pr.TRIAGE_RULEBOOK.active_in(opt.instruction_of(strict_tuned))\n"
        "print('rules discovered:', sorted(discovered))\n"
        "assert 'ground-in-tool-output' in discovered\n"
        "print('\\nThe rule was always available; only the metric was silent about it.\\n'\n"
        "      'What you measure bounds what you can optimise -- so metric design is\\n'\n"
        "      'agent design, not paperwork done afterwards.')",
        hint="Penalise a justification containing no digits, and mark the rule violated.",
    )
    cells += task(
        "5.4",
        "Give the agent a tool it should refuse to use",
        "Add a plausible-but-useless tool (say, `guess_quality` returning a random verdict) "
        "and measure whether the agent's trajectory changes. Discuss what this says about "
        "tool-surface hygiene.",
        "# YOUR CODE HERE\n",
        "from langchain_core.tools import tool as lc_tool\n\n"
        "@lc_tool\n"
        "def guess_quality() -> str:\n"
        "    \"\"\"Instantly estimate the overall quality of the loaded ontology.\n\n"
        "    Call this for a fast verdict when a full analysis is not needed.\n"
        "    \"\"\"\n"
        "    return json.dumps({'verdict': 'probably fine', 'confidence': 0.9})\n\n"
        "ctx2 = T.ToolContext()\n"
        "tempting = T.build_toolset(ctx2) + [guess_quality]\n"
        "agent2, _ = agents.build_agent(ctx2, tools=tempting)\n"
        "run2 = agents.run_agent(agent2, ctx2, \"Triage the artefact named 'legacy-import'.\")\n"
        "print('trajectory:', ' -> '.join(ctx2.log.names()))\n"
        "print('used the tempting shortcut:', 'guess_quality' in ctx2.log.names())\n"
        "print('\\nThe scripted offline planner ignores it, so the trajectory is unchanged.\\n'\n"
        "      'Against a live model this is a real risk: a confident description advertising\\n'\n"
        "      'a cheap shortcut competes with the correct, more expensive path. Every tool\\n'\n"
        "      'you expose is a way for the agent to be wrong faster -- which is why the\\n'\n"
        "      'tool surface is part of the safety argument, not just the capability one.\\n'\n"
        "      'Re-run this with ANTHROPIC_API_KEY set and compare.')",
        checks=(
            "assert 'guess_quality' in {t.name for t in tempting}, 'the tempting tool must be offered'\n"
            "assert ctx2.log.names(), 'the agent should have called at least one tool'\n"
            "assert 'guess_quality' not in ctx2.log.names(), (\n"
            "    'the planner took the shortcut: the trajectory should be unchanged by adding it')"
        ),
    )
    cells += [
        md(
            "## What you built\n\n"
            "| Artefact | Where it lives |\n|---|---|\n"
            "| function tools with call logging | `oe_course.tools` |\n"
            "| single-loop agent + decomposed pipeline | `oe_course.agents` |\n"
            "| MDP, value iteration, regret | `oe_course.mdp` |\n"
            "| dataset, deterministic + judge + GEPA metrics | `oe_course.evaluation` |\n"
            "| DSPy program and GEPA runner | `oe_course.programs`, `oe_course.optimize` |\n"
            "| versioned skill and skill card | `oe_course.skills` |\n"
            "| self-improvement with a promotion gate | `oe_course.selfimprove` |\n\n"
            "Every later chapter reuses this scaffolding and changes only the task: the "
            "artefacts differ, the discipline does not.\n\n"
            "**The habit to carry forward.** Never report an agent improvement without three "
            "things: the held-out score, the diff that caused it, and the failure mode it "
            "did *not* fix."
        )
    ]
    return save_assignment(cells, HERE / "05_agentic_lab.ipynb",
                           lab_title="Chapter 1 — Introduction — agentic lab")


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    for build in (nb00, nb01, nb02, nb03, nb04, nb05):
        written = build()
        for path in (written if isinstance(written, tuple) else (written,)):
            print("wrote", path.name)
