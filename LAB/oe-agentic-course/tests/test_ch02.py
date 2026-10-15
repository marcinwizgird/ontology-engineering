"""Chapter 2: the FOL engine, the policy task's grader support, and the GEPA wiring.

The GEPA test runs the real ``dspy.GEPA`` loop through ``agentlab.optimize`` with
DSPy's ``DummyLM`` as the task model and a scripted reflector, so it checks the
wiring without calling the API.
"""

import dspy
import pytest

from agentlab import evaluation as ev, optimize as opt
from conftest import chapter_path

chapter_path("ch02")
import ch02_agentic as A  # noqa: E402
import ch02_toolkit as fol  # noqa: E402


@pytest.mark.parametrize("item", A.POLICY_ITEMS, ids=[i[0] for i in A.POLICY_ITEMS])
def test_gold_formulas_round_trip(item):
    tree = fol.parse(item[3])
    assert fol.parse(fol.to_string(tree)) == tree and not fol.free_vars(tree)


def test_entailment_countermodel_and_resolution():
    p = [fol.parse("forall x (Human(x) -> Mortal(x))"), fol.parse("Human(Socrates)")]
    assert fol.entails(p, fol.parse("Mortal(Socrates)"), max_size=3) == (True, None)
    holds, m = fol.entails([fol.parse("exists x (Record(x) -> Sensitive(x))")],
                           fol.parse("exists x (Record(x) & Sensitive(x))"))
    assert not holds and m is not None


def test_semantic_equivalence_and_diagnosis():
    gold = fol.parse("forall x (Nurse(x) -> Clinician(x))")
    assert A.equivalent(fol.parse("forall y (~Clinician(y) -> ~Nurse(y))"), gold)
    wrong = fol.parse("forall x (Nurse(x) & Clinician(x))")
    assert not A.equivalent(wrong, gold)
    assert A.diagnose(wrong, gold) == "universal-uses-implication"


def test_dataset_split_by_item():
    parts = {s: A.build_dataset(s) for s in ("train", "dev", "test")}
    assert {k: len(v) for k, v in parts.items()} == {"train": 16, "dev": 16, "test": 16}
    ids = [r.id for v in parts.values() for r in v]
    assert len(ids) == len(set(ids))


def test_gepa_metric_carries_named_feedback():
    def scorer(gold, pred):
        return ev.ScoreReport(0.3, ["wrong shape"], ["negation-scope"])
    out = opt.make_gepa_metric(scorer, A.POLICY_RULEBOOK)(A.build_dataset("dev")[0], None)
    assert out.score == 0.3
    assert "VIOLATED GUIDELINE negation-scope:" in out.feedback and "wrong shape" in out.feedback


class ScriptedReflector:
    """Stands in for the reflection LM: always proposes the same instruction."""

    def __init__(self, text):
        self.text, self.history, self.calls = text, [], 0

    def __call__(self, prompt=None, messages=None, **kwargs):
        self.calls += 1
        self.history.append({"usage": {}, "cost": 0.0})
        return [f"```\n{self.text}\n```"]


def test_run_gepa_end_to_end_without_the_api():
    train, dev, test = (A.build_dataset(s) for s in ("train", "dev", "test"))
    gold = {r.statement: r.gold_formula for r in train + dev + test}

    class InstructionSensitiveLM(dspy.utils.DummyLM):
        """Writes the gold formula only when the instruction mentions 'implication'."""

        def __init__(self):
            super().__init__([{"formula": "nonsense"}])

        def __call__(self, prompt=None, messages=None, **kwargs):
            text = str(messages)
            statement = next((s for s in gold if s in text), None)
            good = statement and "implication" in text
            self.answers = iter([{"formula": gold[statement] if good else "nonsense"}])
            return super().__call__(prompt=prompt, messages=messages, **kwargs)

    class Formalise(dspy.Signature):
        """Translate the policy statement into first-order logic."""
        statement: str = dspy.InputField()
        vocabulary: str = dspy.InputField()
        formula: str = dspy.OutputField()

    def scorer(g, pred):
        try:
            ok = A.equivalent(fol.parse(pred.formula), fol.parse(g.gold_formula))
        except ValueError:
            ok = False
        return ev.ScoreReport(float(ok), [], [] if ok else ["universal-uses-implication"])

    reflector = ScriptedReflector(A.POLICY_RULEBOOK.as_guidelines("Translate the statement."))
    with dspy.context(lm=InstructionSensitiveLM()):
        program = dspy.Predict(Formalise)
        tuned = opt.run_gepa(program, train, opt.make_gepa_metric(scorer, A.POLICY_RULEBOOK),
                             valset=dev, max_metric_calls=40, reflection_lm=reflector)
        result = opt.compare(program, tuned, test, scorer)
    assert reflector.calls >= 1
    assert result.before["mean_score"] == 0.0 and result.after["mean_score"] == 1.0
    assert "implication" in opt.instruction_of(tuned) and "+" in result.instruction_diff()


# ------------------------------------------------------------------ the larger corpus and SIP
def test_new_items_fit_the_vocabulary_and_the_grader():
    for item_id, _, _, gold in A.POLICY_ITEMS:
        f = fol.parse(gold)
        assert all(A.VOCABULARY[p][0] == a for p, a in fol.predicates(f).items()), item_id
        assert A.model_space_bits([f], 2) <= 16, item_id      # the B1 scorer's limit


def test_sip_transfer_set_is_verbatim_from_sip():
    from pathlib import Path
    demo = Path(__file__).resolve().parents[3] / "sip" / "semantic_intelligence" / "demo.py"
    if not demo.exists():
        pytest.skip("sip/ not in this checkout")
    text = demo.read_text(encoding="utf-8")
    for item_id, sentence, gold in A.SIP_REQUIREMENTS:
        assert sentence in text, item_id
        f = fol.parse(gold)
        assert all(A.SIP_VOCABULARY[p][0] == a for p, a in fol.predicates(f).items())
    assert len(A.build_sip_dataset()) == len(A.SIP_REQUIREMENTS)


def test_exercise_reference_answers_are_what_the_engine_says():
    import _answers
    f = fol.parse("exists x (P(x) & ~Q(x))")
    models = list(fol.models_of_size([f], 2))
    assert _answers.CH2_1_2 == (len(models), sum(fol.evaluate(f, m) for m in models))
    prem, conc = fol.parse("forall x exists y R(x, y)"), fol.parse("exists y forall x R(x, y)")
    assert _answers.CH2_2_2 == next(n for n in (1, 2, 3) if not fol.entails([prem], conc, n)[0])
    for english, ref in _answers.CH2_R1.items():
        assert not fol.free_vars(fol.parse(ref)), english
