"""One-off: give the seven sweep-style tasks the checks their exercises never had.

Run once from `oe-course/`:  python _add_missing_task_checks.py

Most converted exercises already asserted their own marking scheme, and
``assignment.task`` lifts those assertions into a checks cell automatically. Seven did
not: they sweep a parameter, print a table and draw a conclusion in prose. That is fine
for a worked example and useless as an assignment, so each gets assertions here.

The assertions are chosen to be *properties*, not recorded outputs. Three kinds:

* **shape** -- the sweep covered the parameters it claims to, and every row reports the
  parameter beside the score, which is the reporting discipline several of these
  exercises are about;
* **monotonicity** -- raising a cost or a penalty cannot raise an optimal value. This is
  guaranteed by the MDP, so it holds regardless of solver or platform;
* **the stated lesson** -- the one claim the exercise's prose makes, turned into an
  assertion, so a student who reproduces the table but breaks the conclusion fails.

Deliberately *not* asserted: exact V* values or scores. Pinning those would make the
marking scheme a snapshot of one machine's arithmetic rather than a statement about the
model.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

CHAPTERS = Path(__file__).resolve().parent / "chapters"

# (chapter, builder filename, task number) -> the checks cell source.
CHECKS: dict[tuple[str, str, str], str] = {
    ("ch01_introduction", "_build_notebooks.py", "5.4"): (
        "assert 'guess_quality' in {t.name for t in tempting}, 'the tempting tool must be offered'\n"
        "assert ctx2.log.names(), 'the agent should have called at least one tool'\n"
        "assert 'guess_quality' not in ctx2.log.names(), (\n"
        "    'the planner took the shortcut: the trajectory should be unchanged by adding it')"
    ),
    ("ch02_first_order_logic", "_build_notebooks.py", "4.1"): (
        "assert len(rows) >= 3, 'sweep at least three budgets'\n"
        "assert [r['budget'] for r in rows] == sorted(r['budget'] for r in rows)\n"
        "assert all({'budget', 'dev_score', 'n_rules'} <= set(r) for r in rows), (\n"
        "    'report the budget beside the score -- a score without its budget is uninterpretable')\n"
        "assert all(0.0 <= r['dev_score'] <= 1.0 and r['n_rules'] >= 0 for r in rows)"
    ),
    ("ch04_web_ontology_languages", "_build_agentic_lab.py", "4.1"): (
        "assert [r['penalty'] for r in rows] == [0.0, 0.25, 0.5, 1.0]\n"
        "assert all(r['n_asserted'] >= 1 for r in rows), 'the requirement must still be met'\n"
        "# The lesson: a legal alternative exists, so the penalty never has to bite.\n"
        "assert not any(r['breaks_EL'] for r in rows)\n"
        "# Raising a penalty cannot raise the optimal value.\n"
        "assert rows[-1]['V*'] <= rows[0]['V*'] + 1e-9"
    ),
    ("ch05_methods_methodologies", "_build_notebooks.py", "4.3"): (
        "assert [r['discount'] for r in rows] == [0.0, 0.2, 0.4, 0.6]\n"
        "# With no discount the search cannot pay for itself; with a large one it must.\n"
        "assert not rows[0]['searches for reuse']\n"
        "assert rows[-1]['searches for reuse']\n"
        "# A discount can only make the plan cheaper.\n"
        "assert rows[-1]['V*'] >= rows[0]['V*'] - 1e-9"
    ),
    ("ch06_topdown_development", "_build_notebooks.py", "4.1"): (
        "assert [r['question_cost'] for r in rows] == [0.0, 0.05, 0.1, 0.2, 0.3, 0.5]\n"
        "assert rows[0]['questions in tree'] > 0, 'free questions should always be asked'\n"
        "# Raising the cost of a question cannot raise the optimal value, nor make the\n"
        "# agent ask more of them.\n"
        "assert rows[-1]['V*'] <= rows[0]['V*'] + 1e-9\n"
        "assert rows[-1]['questions in tree'] <= rows[0]['questions in tree']"
    ),
    ("ch08_linking_data", "_build_notebooks.py", "4.1"): (
        "updates = [r['updates'] for r in rows]\n"
        "assert updates == sorted(updates, reverse=True), (\n"
        "    'sweep from frequent updates down to none')\n"
        "assert updates[0] > 0 and updates[-1] == 0\n"
        "# Every query is served exactly one way.\n"
        "assert all(r['refreshes'] + r['from copy'] + r['rewrites'] == r['workload'].count('q')\n"
        "           for r in rows)\n"
        "# The strategy flips: frequent updates favour rewriting, no updates favour the copy.\n"
        "assert rows[0]['rewrites'] >= rows[-1]['rewrites']\n"
        "assert rows[-1]['from copy'] > 0"
    ),
    ("ch02_first_order_logic", "_build_notebooks.py", "4.3"): (
        "assert [r['penalty'] for r in rows] == [0.0, 1.0, 5.0]\n"
        "assert all({'penalty', 'V*', 'steps', 'verdict'} <= set(r) for r in rows)\n"
        "# Raising the penalty for an unproved verdict cannot raise the optimal value.\n"
        "assert rows[-1]['V*'] <= rows[0]['V*'] + 1e-9\n"
        "# entailed=False, so the correct verdict needs no proof: the agent is right for\n"
        "# free however harshly wrong verdicts are punished. That asymmetry is the lesson.\n"
        "assert all('claim' in r['verdict'] for r in rows)"
    ),
    ("ch04_web_ontology_languages", "_build_agentic_lab.py", "4.2"): (
        "# The requirement is unsatisfiable from the candidate set, so at every penalty --\n"
        "# including zero -- the optimal policy asserts nothing and submits an empty\n"
        "# ontology. Silence is optimal only because the reward cannot express escalation.\n"
        "for penalty in [0.0, 0.5]:\n"
        "    Mx = A.AxiomConstructionMDP(cands, req, profile='EL',\n"
        "                                step_cost=0.05, profile_penalty=penalty)\n"
        "    Vx, pix = mdp.value_iteration(Mx)\n"
        "    plan = mdp.run_episode(Mx, mdp.greedy_policy(pix)).actions\n"
        "    assert [a for a in plan if a != 'submit'] == [], (\n"
        "        f'asserted an axiom at penalty={penalty}; the empty ontology is optimal')\n"
        "    assert plan[-1] == 'submit'"
    ),
    ("ch04_web_ontology_languages", "_build_agentic_lab.py", "4.3"): (
        "from types import SimpleNamespace\n"
        "\n"
        "assert any(r.id == 'simple-property-only' for r in strict_rules)\n"
        "\n"
        "# The rule has to bite: a transitive property inside a universal restriction is\n"
        "# exactly what OWL 2 DL forbids, so the strict scorer must penalise and record it.\n"
        "# Axiom.parse takes a dict, a JSON object or an Axiom -- not the display form.\n"
        "gold = A.build_dataset('all')[0]\n"
        "offender = SimpleNamespace(axiom=A.Axiom('Wheel', 'only', 'Car', 'isPartOf'))\n"
        "assert strict_scorer(gold, offender).score <= A.axiom_scorer(gold, offender).score\n"
        "assert 'simple-property-only' in strict_scorer(gold, offender).violated\n"
        "\n"
        "# A simple property in the same position is not penalised by the new rule.\n"
        "innocent = SimpleNamespace(axiom=A.Axiom('Giraffe', 'only', 'Leaf', 'eats'))\n"
        "assert 'simple-property-only' not in strict_scorer(gold, innocent).violated"
    ),
    ("ch10_rough_temporal_fuzzy", "_build_notebooks.py", "4.1"): (
        "assert [r['cost'] for r in rows] == [0.05, 0.3, 0.5, 0.9, 1.5]\n"
        "assert rows[0]['propagations'] > 0, 'cheap propagation should be used'\n"
        "# Raising the price of propagation cannot raise the optimal value, nor buy more\n"
        "# propagations than the cheapest setting did.\n"
        "assert rows[-1]['V*'] <= rows[0]['V*'] + 1e-9\n"
        "assert rows[-1]['propagations'] <= rows[0]['propagations']"
    ),
}


def as_source(checks: str, indent: str = "        ") -> str:
    """Render the checks as an indented implicitly-concatenated string literal."""
    lines = checks.split("\n")
    body = "\n".join(
        f"{indent}    {parts!r}" for parts in
        [line + "\n" if i < len(lines) - 1 else line for i, line in enumerate(lines)])
    return f"{indent}checks=(\n{body}\n{indent}),\n"


def insert(path: Path, number: str, checks: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "task"):
            continue
        try:
            if ast.literal_eval(node.args[0]) != number:
                continue
        except Exception:
            continue
        if any(kw.arg == "checks" for kw in node.keywords):
            return f"task {number} already has checks"

        close = offsets[node.end_lineno - 1] + node.end_col_offset - 1
        assert source[close] == ")", f"expected a closing paren at {close}"
        before = source[:close].rstrip()
        separator = "" if before.endswith(",") else ","
        patched = (before + separator + "\n" + as_source(checks) + "    "
                   + source[close:])
        ast.parse(patched)          # refuse to write a file we just broke
        path.write_text(patched, encoding="utf-8")
        return f"task {number}: checks added"
    return f"task {number} not found"


def fix_main_blocks() -> list[str]:
    """`save_assignment` returns two paths, not one; teach the `__main__` blocks that.

    Every builder ends by printing what it wrote. The lab builder now writes a pair, so
    the print has to cope with both shapes -- and it should, because the whole point of
    the change is that a lab produces two notebooks and the operator should see both.
    """
    notes = []
    old_loop = '        print("wrote", build().name)'
    new_loop = (
        "        written = build()\n"
        "        for path in (written if isinstance(written, tuple) else (written,)):\n"
        '            print("wrote", path.name)')
    old_single = '    print("wrote", build().name)'
    new_single = (
        "    written = build()\n"
        "    for path in (written if isinstance(written, tuple) else (written,)):\n"
        '        print("wrote", path.name)')

    for path in sorted(CHAPTERS.glob("ch*/_build*.py")):
        source = path.read_text(encoding="utf-8")
        original = source
        if old_loop in source:
            source = source.replace(old_loop, new_loop)
        elif old_single in source:
            source = source.replace(old_single, new_single)
        if source != original:
            ast.parse(source)
            path.write_text(source, encoding="utf-8")
            notes.append(f"  {path.parent.name}/{path.name}: prints both variants")
    return notes


def main() -> int:
    failures = 0
    for (chapter, filename, number), checks in CHECKS.items():
        path = CHAPTERS / chapter / filename
        if not path.exists():
            print(f"! {chapter}: {filename} missing", file=sys.stderr)
            failures += 1
            continue
        result = insert(path, number, checks)
        ok = result.endswith("checks added")
        failures += 0 if ok else 1
        print(f"{'  ' if ok else '! '}{chapter:30} {result}")

    for note in fix_main_blocks():
        print(note)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
