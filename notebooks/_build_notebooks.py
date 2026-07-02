"""Generator for the bottom-up ontology workflow demo notebooks.

Run:  python notebooks/_build_notebooks.py
Produces the four .ipynb files in this folder.  Kept in-repo so the notebooks
can be regenerated/diffed easily.
"""
from __future__ import annotations

import os
import nbformat as nbf
from nbformat.v4 import new_notebook, new_code_cell, new_markdown_cell

HERE = os.path.dirname(os.path.abspath(__file__))

# Shared bootstrap so a notebook works whether launched from repo root or here.
BOOT = (
    "import sys, os\n"
    "sys.path.insert(0, os.path.abspath('..'))  # make the package importable\n"
    "import matplotlib\n"
    "matplotlib.use('Agg')  # headless-safe; remove for interactive plots\n"
    "import bottomup_ontology as bo\n"
    "print('bottomup_ontology', bo.__version__)"
)

CORPUS = (
    "corpus = [\n"
    "    'A rugby player plays in a position. Siya Kolisi is a rugby player. '\n"
    "    'A team has many players.',\n"
    "    'A club has a coach. The coach trains the team. A player belongs to a club.',\n"
    "    'Mammals such as lions and impalas live in the savanna. A lion eats impala.',\n"
    "    'A blog post has a title and comments. A blog post has a category.',\n"
    "]\n"
    "gold_classes = {'rugby player','player','team','club','coach','lion',\n"
    "                'impala','position','blog post','category','mammal'}\n"
    "len(corpus)"
)


def write(nb, name):
    path = os.path.join(HERE, name)
    nbf.write(nb, path)
    print("wrote", path)


# --------------------------------------------------------------------------- #
# 01 — Build & visualize the workflow graph
# --------------------------------------------------------------------------- #
def nb01():
    c = []
    c.append(new_markdown_cell(
        "# 01 · Build & visualize the bottom-up ontology workflow\n\n"
        "This notebook builds the **text-to-ontology pipeline** of Keet, "
        "*Ontology Repository* (2nd ed.), **Chapter 7, Figure 7.7** as a "
        "`networkx` directed graph.\n\n"
        "* Each **node is a `WorkflowStep` class instance**.\n"
        "* Each step is the invocation of **one function** (reusable as an "
        "agentic tool).\n"
        "* Edges encode execution order / data-flow.\n\n"
        "Pipeline: *Unstructured text → Text cleaning → Pre-processing → "
        "Term extraction → Relation extraction → Axiom finding (opt) → "
        "Human-in-the-loop (opt) → Evaluation → Ontology*."
    ))
    c.append(new_code_cell(BOOT))
    c.append(new_markdown_cell("## Build the default (full) workflow"))
    c.append(new_code_cell(
        "g = bo.build_default_workflow()\n"
        "print('graph name :', g.graph['name'])\n"
        "print('is DAG     :', __import__('networkx').is_directed_acyclic_graph(g))\n"
        "print('execution plan:', bo.execution_plan(g))"
    ))
    c.append(new_markdown_cell("## Inspect the nodes (the step classes)"))
    c.append(new_code_cell(
        "from bottomup_ontology.steps import WorkflowStep\n"
        "for n in g.nodes:\n"
        "    if isinstance(n, WorkflowStep):\n"
        "        kind = 'mandatory' if n.mandatory else 'optional'\n"
        "        print(f'{n.step_id:20s} {kind:9s} -> fn {n.tool_name():24s} | {n.label}')\n"
        "    else:\n"
        "        print(f'{str(n):20s} (io marker)')"
    ))
    c.append(new_markdown_cell("## Inspect the edges (execution order)"))
    c.append(new_code_cell(
        "for u, v, d in g.edges(data=True):\n"
        "    su = getattr(u, 'step_id', u)\n"
        "    sv = getattr(v, 'step_id', v)\n"
        "    print(f'{su:20s} --{d.get(\"relation\",\"\"):9s}--> {sv}')"
    ))
    c.append(new_markdown_cell(
        "## Mandatory vs optional steps\n"
        "The configuration functions toggle the *optional* steps; the "
        "mandatory ones are always present."
    ))
    c.append(new_code_cell(
        "print('mandatory:', bo.mandatory_step_ids())\n"
        "print('optional :', bo.optional_step_ids())"
    ))
    c.append(new_markdown_cell("## Draw the workflow graph"))
    c.append(new_code_cell(
        "import networkx as nx\n"
        "import matplotlib.pyplot as plt\n"
        "from bottomup_ontology.steps import WorkflowStep, PIPELINE_ORDER\n"
        "\n"
        "# assign a layer index for a clean left-to-right layout\n"
        "order = {sid: i + 1 for i, sid in enumerate(PIPELINE_ORDER)}\n"
        "for n in g.nodes:\n"
        "    if n == bo.SOURCE:\n"
        "        g.nodes[n]['layer'] = 0\n"
        "    elif n == bo.SINK:\n"
        "        g.nodes[n]['layer'] = len(PIPELINE_ORDER) + 1\n"
        "    else:\n"
        "        g.nodes[n]['layer'] = order[n.step_id]\n"
        "\n"
        "# align='horizontal' => layers stacked top-to-bottom (readable for a chain)\n"
        "pos = nx.multipartite_layout(g, subset_key='layer', align='horizontal')\n"
        "pos = {n: (x, -y) for n, (x, y) in pos.items()}  # flow downward\n"
        "\n"
        "def node_color(n):\n"
        "    if not isinstance(n, WorkflowStep):\n"
        "        return '#b0bec5'           # io markers (grey)\n"
        "    return '#90caf9' if n.mandatory else '#ffcc80'  # blue / orange\n"
        "\n"
        "labels = {n: (n.label if isinstance(n, WorkflowStep) else str(n)) for n in g.nodes}\n"
        "colors = [node_color(n) for n in g.nodes]\n"
        "\n"
        "fig, ax = plt.subplots(figsize=(9, 13))\n"
        "nx.draw(g, pos, ax=ax, labels=labels, node_color=colors, node_size=3200,\n"
        "        font_size=9, edgecolors='black', width=1.4, arrowsize=20)\n"
        "edge_lbls = {(u, v): d.get('relation', '') for u, v, d in g.edges(data=True)}\n"
        "nx.draw_networkx_edge_labels(g, pos, edge_labels=edge_lbls, font_size=8,\n"
        "                             label_pos=0.5, ax=ax)\n"
        "ax.margins(0.12)\n"
        "ax.set_title('Bottom-up ontology development (Keet 2nd ed., Fig. 7.7)\\n'\n"
        "             'blue = mandatory, orange = optional, grey = input/output')\n"
        "fig.tight_layout()\n"
        "fig.savefig('workflow_graph.png', dpi=120)\n"
        "print('saved workflow_graph.png')\n"
        "plt.show()"
    ))
    c.append(new_markdown_cell(
        "## Each step carries its Figure-7.7 techniques + tunable parameters"
    ))
    c.append(new_code_cell(
        "from bottomup_ontology.steps import STEP_CLASSES\n"
        "for sid, cls in STEP_CLASSES.items():\n"
        "    print(f'## {cls.label}  ({\"mandatory\" if cls.mandatory else \"optional\"})')\n"
        "    print('   category  :', cls.category)\n"
        "    print('   techniques:', ', '.join(cls.techniques))\n"
        "    if cls.parameters:\n"
        "        print('   parameters:', list(cls.parameters))\n"
        "    print()"
    ))
    nb = new_notebook(cells=c)
    nb.metadata.kernelspec = {"name": "python3", "display_name": "Python 3", "language": "python"}
    write(nb, "01_build_and_visualize_workflow.ipynb")


# --------------------------------------------------------------------------- #
# 02 — Run the pipeline end-to-end
# --------------------------------------------------------------------------- #
def nb02():
    c = []
    c.append(new_markdown_cell(
        "# 02 · Run the pipeline end-to-end\n\n"
        "Take a small unstructured-text corpus and run the **full** workflow to "
        "produce an ontology (classes, subclass axioms, object properties), then "
        "evaluate it."
    ))
    c.append(new_code_cell(BOOT))
    c.append(new_markdown_cell("## The input corpus (the *unstructured text*)"))
    c.append(new_code_cell(CORPUS))
    c.append(new_markdown_cell(
        "## Build the workflow and the shared state, then run it\n"
        "`run_workflow` topologically sorts the graph and invokes each node's "
        "single function on the shared `WorkflowState`."
    ))
    c.append(new_code_cell(
        "state = bo.WorkflowState(documents=corpus, gold_classes=gold_classes)\n"
        "g = bo.build_default_workflow()\n"
        "state = bo.run_workflow(g, state, verbose=True)"
    ))
    c.append(new_markdown_cell("## The resulting ontology"))
    c.append(new_code_cell(
        "onto = state.ontology\n"
        "print('summary :', onto.summary())\n"
        "print()\n"
        "print('classes :')\n"
        "for cls in sorted(onto.classes):\n"
        "    print('   -', cls)"
    ))
    c.append(new_code_cell(
        "print('subclass axioms (X subClassOf Y):')\n"
        "for sub, sup in sorted(onto.subclass_of):\n"
        "    print(f'   {sub}  ⊑  {sup}')\n"
        "print()\n"
        "print('object properties (domain --predicate--> range):')\n"
        "for r in onto.object_properties:\n"
        "    print(f'   {r.subject} --{r.predicate}--> {r.object}  (support={r.support})')\n"
        "print()\n"
        "print('axioms found by lexico-syntactic patterns:')\n"
        "for ax in onto.axioms:\n"
        "    print('   -', ax)"
    ))
    c.append(new_markdown_cell("## OWL/Turtle serialisation"))
    c.append(new_code_cell("print(onto.to_turtle())"))
    c.append(new_markdown_cell(
        "## Evaluation (Fig. 7.7 *Evaluation* stage)\n"
        "Gold-standard precision/recall/F1 plus a data-driven vocabulary-"
        "coverage assessment."
    ))
    c.append(new_code_cell(
        "import json\n"
        "print(json.dumps(state.evaluation, indent=2))"
    ))
    c.append(new_markdown_cell(
        "## Full execution trace\n"
        "Every step appends a human-readable line to `state.log`."
    ))
    c.append(new_code_cell("for line in state.log:\n    print('-', line)"))
    nb = new_notebook(cells=c)
    nb.metadata.kernelspec = {"name": "python3", "display_name": "Python 3", "language": "python"}
    write(nb, "02_run_pipeline_end_to_end.ipynb")


# --------------------------------------------------------------------------- #
# 03 — Configure mandatory / optional steps
# --------------------------------------------------------------------------- #
def nb03():
    c = []
    c.append(new_markdown_cell(
        "# 03 · Configure mandatory & optional steps\n\n"
        "The workflow has five **mandatory** steps and two **optional** ones "
        "(*axiom finding* and *human-in-the-loop evaluation*). This notebook "
        "shows the configuration helpers and the human-in-the-loop gate."
    ))
    c.append(new_code_cell(BOOT))
    c.append(new_code_cell(CORPUS))
    c.append(new_markdown_cell(
        "## Minimal vs. full pipeline\n"
        "`build_minimal_workflow` keeps only mandatory steps; "
        "`build_default_workflow` enables everything."
    ))
    c.append(new_code_cell(
        "print('minimal:', bo.execution_plan(bo.build_minimal_workflow()))\n"
        "print('default:', bo.execution_plan(bo.build_default_workflow()))"
    ))
    c.append(new_markdown_cell(
        "## Toggle optional steps declaratively with `configure_workflow`"
    ))
    c.append(new_code_cell(
        "g = bo.configure_workflow(include_axiom_finding=True,\n"
        "                          include_human_in_the_loop=False)\n"
        "print('axiom only :', bo.execution_plan(g))\n"
        "g = bo.configure_workflow(include_axiom_finding=False,\n"
        "                          include_human_in_the_loop=True)\n"
        "print('HITL only  :', bo.execution_plan(g))"
    ))
    c.append(new_markdown_cell(
        "## Add / remove optional steps on an existing graph\n"
        "These return a **new** graph re-wired around the change (mandatory "
        "steps cannot be removed)."
    ))
    c.append(new_code_cell(
        "g = bo.build_minimal_workflow()\n"
        "print('start          :', bo.execution_plan(g))\n"
        "g = bo.add_optional_step(g, 'axiom_finding')\n"
        "print('+axiom_finding :', bo.execution_plan(g))\n"
        "g = bo.add_optional_step(g, 'human_in_the_loop')\n"
        "print('+HITL          :', bo.execution_plan(g))\n"
        "g = bo.remove_optional_step(g, 'axiom_finding')\n"
        "print('-axiom_finding :', bo.execution_plan(g))\n"
        "try:\n"
        "    bo.remove_optional_step(g, 'term_extraction')\n"
        "except ValueError as e:\n"
        "    print('cannot remove mandatory:', e)"
    ))
    c.append(new_markdown_cell(
        "## Per-step parameters\n"
        "`term_extraction` exposes `min_frequency` and `top_k`. Pass defaults at "
        "build time via `step_params`, or per-run via `run_workflow(..., "
        "step_params=...)`."
    ))
    c.append(new_code_cell(
        "g = bo.configure_workflow(step_params={'term_extraction': {'top_k': 6}})\n"
        "st = bo.run_workflow(g, bo.WorkflowState(documents=corpus))\n"
        "print('top_k=6 -> classes:', sorted(st.ontology.classes))"
    ))
    c.append(new_markdown_cell(
        "## The human-in-the-loop gate\n\n"
        "Naive extraction produces some noise — e.g. the Hearst pattern over "
        "*\"Mammals such as lions and impalas live in the savanna\"* yields a "
        "spurious class `live savanna`. The optional **human-in-the-loop** step "
        "uses an approver callback `(kind, label) -> bool` to prune candidates "
        "before final evaluation."
    ))
    c.append(new_code_cell(
        "# Baseline: run WITHOUT the human-in-the-loop step\n"
        "g_no = bo.configure_workflow(include_human_in_the_loop=False)\n"
        "st_no = bo.run_workflow(g_no, bo.WorkflowState(documents=corpus,\n"
        "                                               gold_classes=gold_classes))\n"
        "print('without HITL -> classes:', len(st_no.ontology.classes))\n"
        "print('  ', sorted(st_no.ontology.classes))\n"
        "print('  class P/R/F1:', st_no.evaluation['class_prf'])"
    ))
    c.append(new_code_cell(
        "# A domain expert standing in as a callback. Here we reject obvious\n"
        "# noise: multi-word 'classes' whose head is a verb-like token, and any\n"
        "# class not anchored in the domain vocabulary.\n"
        "NOISE = {'live savanna', 'kolisi'}\n"
        "\n"
        "def approver(kind, label):\n"
        "    label = label.lower()\n"
        "    if kind == 'class':\n"
        "        return label not in NOISE\n"
        "    return True  # accept all object properties\n"
        "\n"
        "g_yes = bo.configure_workflow(include_human_in_the_loop=True)\n"
        "st_yes = bo.run_workflow(\n"
        "    g_yes,\n"
        "    bo.WorkflowState(documents=corpus, gold_classes=gold_classes,\n"
        "                     human_approver=approver),\n"
        ")\n"
        "print('with HITL -> classes:', len(st_yes.ontology.classes))\n"
        "print('  ', sorted(st_yes.ontology.classes))\n"
        "print('  class P/R/F1:', st_yes.evaluation['class_prf'])\n"
        "print()\n"
        "removed = set(st_no.ontology.classes) - set(st_yes.ontology.classes)\n"
        "print('pruned by the expert:', sorted(removed))"
    ))
    nb = new_notebook(cells=c)
    nb.metadata.kernelspec = {"name": "python3", "display_name": "Python 3", "language": "python"}
    write(nb, "03_configure_optional_steps.ipynb")


# --------------------------------------------------------------------------- #
# 04 — Steps as agentic function tools
# --------------------------------------------------------------------------- #
def nb04():
    c = []
    c.append(new_markdown_cell(
        "# 04 · Workflow steps as agentic function tools\n\n"
        "Because every step is a single `state -> state` function, the same "
        "functions can be handed to an LLM agent as **function tools**. The "
        "agent then *drives* the bottom-up pipeline by choosing which tool to "
        "call next, while a `ToolRegistry` keeps the evolving ontology in one "
        "shared state."
    ))
    c.append(new_code_cell(BOOT))
    c.append(new_code_cell(CORPUS))
    c.append(new_markdown_cell(
        "## Tool specifications (OpenAI / Anthropic style JSON)\n"
        "Generated automatically from the step metadata."
    ))
    c.append(new_code_cell(
        "import json\n"
        "specs = bo.tool_specs()\n"
        "print(f'{len(specs)} tools available\\n')\n"
        "# show one full spec + the names of the rest\n"
        "print(json.dumps(bo.tool_specs(['term_extraction'])[0], indent=2))\n"
        "print()\n"
        "for s in specs:\n"
        "    fn = s['function']\n"
        "    print(f\"  {fn['name']:26s} mandatory={fn['x-mandatory']}\")"
    ))
    c.append(new_markdown_cell(
        "## A `ToolRegistry` holds shared state and dispatches calls by name"
    ))
    c.append(new_code_cell(
        "from bottomup_ontology import ToolRegistry\n"
        "reg = ToolRegistry(bo.WorkflowState(documents=corpus, gold_classes=gold_classes))\n"
        "print('tools:', reg.tool_names())"
    ))
    c.append(new_markdown_cell(
        "## Simulate an agent loop\n"
        "A real agent would pick tools from the specs above. Here a tiny "
        "rule-based policy walks the pipeline order; each `invoke` returns a "
        "compact JSON result (the shape an agent gets back)."
    ))
    c.append(new_code_cell(
        "from bottomup_ontology.steps import PIPELINE_ORDER\n"
        "from bottomup_ontology.tools import TOOL_NAME_TO_STEP_ID\n"
        "\n"
        "# tool name keyed by step id, in pipeline order\n"
        "step_to_tool = {sid: name for name, sid in TOOL_NAME_TO_STEP_ID.items()}\n"
        "plan = [step_to_tool[sid] for sid in PIPELINE_ORDER]\n"
        "\n"
        "for tool_name in plan:\n"
        "    args = {'top_k': 8} if tool_name == 'step_term_extraction' else {}\n"
        "    result = reg.invoke(tool_name, args)\n"
        "    print(f\"called {result['tool']:26s} -> {result['ontology']}\")"
    ))
    c.append(new_code_cell(
        "print('Final ontology built by the agent:')\n"
        "print(reg.state.ontology.to_turtle())\n"
        "print('Evaluation:', reg.state.evaluation.get('class_prf'))"
    ))
    c.append(new_markdown_cell(
        "## Direct callables\n"
        "`reg.callables()` gives plain `**params -> WorkflowState` callables, "
        "handy for frameworks that bind Python functions directly."
    ))
    c.append(new_code_cell(
        "calls = reg.callables()\n"
        "print(list(calls)[:3], '...')"
    ))
    c.append(new_markdown_cell(
        "## Wiring into the Anthropic SDK (sketch)\n\n"
        "The `tool_specs()` are already in the right shape. In an Anthropic "
        "tool-use loop you would:\n\n"
        "```python\n"
        "import anthropic\n"
        "client = anthropic.Anthropic()\n"
        "registry = ToolRegistry(WorkflowState(documents=corpus))\n"
        "tools = [{'name': s['function']['name'],\n"
        "          'description': s['function']['description'],\n"
        "          'input_schema': s['function']['parameters']} for s in bo.tool_specs()]\n"
        "\n"
        "# then, on each tool_use block returned by the model:\n"
        "#   result = registry.invoke(block.name, block.input)\n"
        "#   -> feed `result` back as a tool_result content block\n"
        "```\n\n"
        "The model decides the order; the registry guarantees the steps mutate "
        "one consistent ontology state."
    ))
    nb = new_notebook(cells=c)
    nb.metadata.kernelspec = {"name": "python3", "display_name": "Python 3", "language": "python"}
    write(nb, "04_steps_as_agentic_tools.ipynb")


if __name__ == "__main__":
    nb01()
    nb02()
    nb03()
    nb04()
    print("done")
