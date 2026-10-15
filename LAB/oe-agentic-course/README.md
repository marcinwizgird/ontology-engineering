# Ontology Engineering: the agentic track

The Ontology Engineering course (Keet, *An Introduction to Ontology Engineering*, 2nd
ed.), rebuilt so that **the code grows with the course**. The book content is the
original course's: every chapter notebook, exercise and problem set is ported from
`../oe-course`. What changes is how the code reaches you.

In the original, the first cell of Chapter 1 imports a complete framework
(`oe_course`), and every problem set uses all of it: tools, agents, DSPy, GEPA, an LLM
judge, MDPs, skills. Here each chapter introduces only the code it needs, opens by
reading it, and each problem set uses only the agent-engineering layers introduced so
far.

## How the course is built

| rule | how it is kept |
|---|---|
| **One package, grown per chapter.** Reusable code lives in `agentlab/`. Each module declares `INTRODUCED_IN = N` and says in its docstring why chapter N needs it. The modules are the original course's, split by first use, with the same function names. | `tests/test_incremental.py` |
| **Nothing ahead of time.** Chapter N, and every `agentlab` module, imports only what chapters ≤ N introduced. Chapters do not import from each other, with one narrow exception: a *revisit* (`chNN_revisit.py`, or a problem set marked `# revisits:`) may import an **earlier** chapter's support modules, to bring a new layer back to that chapter's task. Nothing imports `oe_course`. | `tests/test_incremental.py` |
| **Each chapter's `00_overview_and_setup` reads the new code** ("The code this chapter adds"). `agentlab.catalogue(up_to_chapter=N)` lists what exists; `agentlab.show(f)` prints any function's source. | the notebooks |
| **The chapter's subject stays in the chapter.** Its engine and data (`ch02_toolkit.py`, `corpus.py`, `ch01_agentic.py` …) live in its folder. | folder layout |
| **Notebooks are readable as plain Python.** Every notebook's source is a `.py` file in "percent" format. A problem set is one source (`NN_problem_set.py`) whose cells tagged `assignment` / `solution` build the two notebooks, so they cannot drift apart. | `tools/build_notebooks.py` |
| **Exercises test your code, not the reference.** In the book notebooks every exercise has a starter, a check that tests the names *your* code defines, and its worked solution in a separate `NN_name_solutions.ipynb`. A failing check is recorded, not raised, so a notebook always runs to the end. | `tests/test_incremental.py` |
| **Live Claude, with the bill shown.** Book notebooks never call a model. Problem sets call the Anthropic API and price every block with `llm.meter`; DSPy's disk cache makes unchanged re-runs free. | `agentlab/llm.py` |

## Agent-engineering layers, chapter by chapter

| ch | subject (Keet) | layer the chapter adds | adds to `agentlab` | problem set | status |
|---|---|---|---|---|---|
| 1 | Introduction: what an ontology is, why it pays off, good and bad ontologies | **a Claude program** (DSPy signature, predictor, module); diagnostic scorers, including one for the written report; held-out evaluation with cost and noise | `ontology`, `sparql`, `llm`, `evaluation`, `grading` | Triaging submissions to an ontology registry: A1, B1, B2 as in the original; B3 grades the report by code; C writes the policy into the prompt and measures the noise; **D runs on 40 real FIBO modules, where the policy itself breaks, and fixes it (imports)**; **E triages the ontology SIP builds** | ✅ |
| 2 | First-order logic and reasoning | **optimisation**: feedback metrics and GEPA | `optimize` | Formalising a hospital access policy (48 statements, half modelled on HIPAA Privacy Rule provisions): A–B as in the original; **C optimises the formaliser a team ships first (no syntax hints: Claude writes correct logic in Unicode that does not parse), because the described one is already at the ceiling**; the grader works modulo the vocabulary's typing; **D tests whether the tuned formaliser transfers to SIP's requirements** | ✅ |
| 3 | Description logics | **tools and agents**: function tools, call logs, a tool-calling agent vs a pipeline in which the reasoner disposes | `tools`, `agents` | Reviewing rail-ontology change requests: A–C as in the original (heuristic, blind spot, scorer, reviewer, GEPA, noise); D1 the review agent; **D2 the model proposes, the reasoner disposes, and escalates where it cannot certify**; **E1 reasoning or remembering: the Pizza ontology famous / renamed / counterfactual**; **E2 SIP's fleet ontology**. A second problem set (`06`) brings the layer back to earlier tasks: Ch 1's registry tools and agent vs program+critic (orig. Ch 1 A2, D1) and Ch 2's compliance agent (orig. Ch 2 D1) | ✅ |
| 4 | OWL 2 and its profiles | multi-step programs, per-step feedback | | | planned |
| 5 | Methods and methodologies | **LLM-as-judge**, validated against labels | `judge` | + Ch 1's judge validation (orig. Ch 1 B3) | planned |
| 6 | Top-down development | **MDPs**: pricing evidence and proof | `mdp` | + Ch 1's evidence MDP (orig. Ch 1 D2), Ch 2's proof-search MDP (orig. Ch 2 D2), Ch 3's reasoner budget (orig. Ch 3 D2) | planned |
| 7 | Bottom-up development | grounded extraction | | | planned |
| 8 | Linking ontologies to data | SPARQL over a live store (Fuseki) | `sparql` gains a Fuseki backend | | planned |
| 9 | Natural language | round-trip metrics | | | planned |
| 10 | Rough, temporal, fuzzy | **skills and gated self-improvement** | `skills`, `selfimprove` | + Ch 1's skill and promotion gate (orig. Ch 1 D3), Ch 3's self-labelling with a certified oracle (orig. Ch 3 C3) | planned |

Every part removed from the original Chapter 1–3 problem sets is listed in the
"returns in" column above, so nothing is lost; it moves to where its layer is taught.

## Layout

```
oe-agentic-course/
├── agentlab/                       the package, grown chapter by chapter
│   ├── __init__.py                 catalogue(), show(), artifacts_dir(), describe_environment()
│   ├── ontology.py · sparql.py · llm.py · evaluation.py · grading.py      (ch 1)
│   ├── optimize.py                                                        (ch 2)
│   └── tools.py · agents.py                                               (ch 3)
├── chapters/
│   ├── ch01_introduction/
│   │   ├── 00_overview_and_setup.py … 04_exercises.py   → .ipynb  (book notebooks, free)
│   │   ├── 05_problem_set.py        → 05_assignment.ipynb + 05_solutions.ipynb (live)
│   │   ├── corpus.py · awo.ttl · ch01_toolkit.py · ch01_agentic.py
│   │   └── fibo/ · fibo_index.json · _vendor_fibo.py   40 real FIBO modules (MIT) + import index
│   ├── ch02_first_order_logic/
│   │   ├── 00_overview_and_setup.py … 03_exercises.py   → .ipynb  (book notebooks, free)
│   │   ├── 04_problem_set.py        → 04_assignment.ipynb + 04_solutions.ipynb (live, GEPA)
│   │   └── ch02_toolkit.py · ch02_agentic.py · _answers.py (exercise check references)
│   └── ch03_description_logics/
│       ├── 00_overview_and_setup.py … 04_exercises.py   → .ipynb  (book notebooks, free)
│       ├── 05_problem_set.py        → 05_assignment.ipynb + 05_solutions.ipynb (live, agents)
│       ├── 06_problem_set.py        → 06_assignment.ipynb + 06_solutions.ipynb (live; revisits ch 1–2)
│       └── ch03_toolkit.py (the ALC tableau) · ch03_agentic.py (corpus, certificates,
│           review tools, Pizza contamination twins, SIP's fleet modules)
├── tools/build_notebooks.py        .py sources → .ipynb
└── tests/                          the build rule + each chapter's deterministic code
```

## Running it

```bash
cd LAB/oe-agentic-course
pip install -r requirements.txt
cp .env.example .env              # add ANTHROPIC_API_KEY (only the problem sets need it)

python -m pytest tests -q         # free: no model is called
python tools/build_notebooks.py   # regenerate every .ipynb from its .py source
jupyter lab chapters/
```

**Cost.** Book notebooks (`00`–`04`, `00`–`03`) never call a model. Problem sets state
their budget in the header and print an `llm.meter` line for every block of work. A
measured triage call costs about $0.01 with the default task model (`claude-sonnet-5-5`;
GEPA's reflection uses `claude-opus-5-5`; change them in `.env`).

**What has been verified.** The tests never call the API; one of them runs the real
`dspy.GEPA` loop through `agentlab.optimize` with DSPy's `DummyLM` and a scripted
reflector. Both variants of every book notebook execute (your version records failing
checks; the solutions version passes them all). The Chapter 1 and 2 problem-set solution
notebooks are committed **executed against Claude**, so their outputs are real results and
their model answers were checked against them. The Chapter 3 solutions have been
dry-run end to end with fakes (a DSPy `DummyLM`, a scripted reflector and a scripted
tool-calling chat model through LangChain's real agent loop: 53/53 checks pass); their
live record run, and the measured budget, are still to do, so the Chapter 3 model
answers describe what to look for rather than recorded numbers.

## Reading order for a chapter

1. `00_overview_and_setup`: the chapter plan, and the code the chapter adds.
2. The book notebooks, in number order, with their exercises.
3. The problem set: the assignment, then the solutions (executed, with real outputs).
