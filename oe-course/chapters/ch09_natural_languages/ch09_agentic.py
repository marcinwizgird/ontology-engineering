"""Chapter 9 agentic lab — verbalisation, and knowing when to stop resampling.

The task has a property almost nothing else in this course does: **a free, exact
correctness signal**. Verbalise an axiom, parse the sentence back, and compare.
No gold labels, no annotation, no judge — the inverse function is the grader.

That makes Chapter 9 the right place to show what a deterministic metric
*cannot* do. ``"No plant is a animal."`` round-trips perfectly and is still bad
English. The score is split accordingly: half exact round-trip fidelity, half
readability. An agent can max the first half and still produce text no domain
expert will read, which is the honest case for keeping a judge in the loop.

The MDP is **optimal stopping** — new for the course, and the one shape every
LLM engineer meets in practice. The agent samples a candidate verbalisation,
sees its quality, and decides whether to accept it or pay to try again. That is
best-of-n sampling, and value iteration gives the exact stopping rule.
"""

from __future__ import annotations

from dataclasses import dataclass

import ch09_toolkit as ch9

__all__ = [
    "build_dataset", "verbalisation_scorer", "CNL_RULEBOOK", "cnl_responder",
    "VerbalisationProgram", "BASELINE_INSTRUCTION", "build_toolset", "Ch9Context",
    "RevisionMDP",
]


# --------------------------------------------------------------------------- #
# Dataset
# --------------------------------------------------------------------------- #
def build_dataset(split: str = "all"):
    """Every sample axiom in every language — the gold answer is a function."""
    import dspy

    examples = []
    for axiom in ch9.SAMPLE_AXIOMS:
        for language in ch9.LANGUAGES:
            examples.append(
                dspy.Example(
                    axiom=str(axiom),
                    subject=axiom.subject,
                    operator=axiom.operator,
                    property=axiom.property,
                    filler=axiom.filler,
                    language=language,
                    id=f"{axiom.subject}-{axiom.operator}-{language}",
                ).with_inputs("axiom", "subject", "operator", "property", "filler",
                              "language")
            )

    if split == "all":
        return examples

    # Stratify on (operator, language): both halves must see every construct in
    # every language, or a rule becomes unlearnable for reasons invisible in the
    # report -- the failure Chapter 5 Exercise 4.1 isolates.
    groups: dict = {}
    for example in examples:
        groups.setdefault((example.operator, example.language), []).append(example)
    train, dev = [], []
    for key in sorted(groups):
        for index, example in enumerate(groups[key]):
            (train if index % 2 == 0 else dev).append(example)
    return train if split == "train" else dev


def _axiom_of(example) -> ch9.Axiom:
    return ch9.Axiom(example.subject, example.operator, example.filler, example.property)


# --------------------------------------------------------------------------- #
# Scoring: half exact, half judged
# --------------------------------------------------------------------------- #
def verbalisation_scorer(gold, pred):
    """Half round-trip fidelity (exact), half readability (proxy for a judge).

    The split is the chapter's argument in one function. The first half is a
    decision procedure; the second is a matter of taste that still has to be
    measured, because a perfectly faithful verbalisation nobody can read has
    failed at the only job verbalisation has.
    """
    from oe_course.evaluation import ScoreReport

    sentence = str(getattr(pred, "sentence", "") or "").strip()
    axiom = _axiom_of(gold)
    language = gold.language

    notes, violated = [], []

    if not sentence:
        return ScoreReport(0.0, ["No sentence produced."],
                           [f"template-for-{axiom.operator}"])

    recovered = ch9.parse_cnl(sentence, language)
    faithful = bool(recovered) and recovered.key() == axiom.key()
    if not faithful:
        if recovered is None:
            notes.append(
                f"The sentence does not parse as controlled {language}: {sentence!r}. "
                f"Use the template for the '{axiom.operator}' construct."
            )
            violated.append(f"template-for-{axiom.operator}")
        else:
            notes.append(
                f"Round trip changed the axiom: started from {axiom}, recovered "
                f"{recovered}."
            )
            violated.append(f"template-for-{axiom.operator}")

    report = ch9.readability(sentence)
    labels = ch9.uses_lexicon_labels(sentence, axiom, language)
    if not labels["ok"]:
        expected = ", ".join(f"{m['term']} -> {m['expected']!r}" for m in labels["missing"])
        notes.append(
            f"The sentence does not use the {language} labels ({expected}). Note the "
            f"round trip did NOT catch this: the parser falls back to returning an "
            f"unknown label unchanged, so fidelity looked fine."
        )
        violated.append("use-the-lexicon-label")
    if report["contains_identifier"]:
        notes.append(
            "The sentence contains a raw identifier rather than a surface form."
        )
        violated.append("use-the-lexicon-label")
    if report["wrong_article"]:
        notes.append("Wrong article: 'a' before a vowel should be 'an'.")
        violated.append("correct-article")

    presentation = 0.5 * report["score"] + 0.5 * float(labels["ok"])
    score = 0.5 * float(faithful) + 0.5 * presentation
    notes.append(f"round_trip={int(faithful)} readability={report['score']} "
                 f"lexicon_ok={int(labels['ok'])}")
    return ScoreReport(round(score, 4), notes, list(dict.fromkeys(violated)))


# --------------------------------------------------------------------------- #
# Rulebook + offline simulator
# --------------------------------------------------------------------------- #
def _rulebook():
    from oe_course.llm import Rule, RuleBook

    return RuleBook(
        [
            Rule("template-for-subclassof",
                 "Render a subclass axiom as 'Every X is a Y.' (and the equivalent in the "
                 "requested language)."),
            Rule("template-for-some",
                 "Render an existential restriction as 'Every X <property> at least one Y.'"),
            Rule("template-for-only",
                 "Render a universal restriction as 'Every X <property> only Y.'"),
            Rule("template-for-disjoint",
                 "Render disjointness as 'No X is a Y.'"),
            Rule("template-for-type",
                 "Render a class assertion about an individual as 'Simba is a lion.'"),
            Rule("use-the-lexicon-label",
                 "Use the lexicon label for the requested language, never the raw ontology "
                 "identifier."),
            Rule("correct-article",
                 "Use 'an' rather than 'a' before a vowel sound."),
        ]
    )


CNL_RULEBOOK = _rulebook()

BASELINE_INSTRUCTION = "Express the axiom as a sentence."


def _fix_article(sentence: str) -> str:
    import re

    return re.sub(r"\ba (?=[aeiou])", "an ", sentence, flags=re.I)


def cnl_responder(inputs: dict, active: set[str]) -> dict:
    """A weak verbaliser: identifiers glued together, improving rule by rule."""
    axiom = ch9.Axiom(
        subject=inputs.get("subject", "") or "",
        operator=(inputs.get("operator", "") or "").strip(),
        filler=inputs.get("filler", "") or "",
        property=inputs.get("property", "") or "",
    )
    language = (inputs.get("language", "en") or "en").strip()

    # Each construct is enabled by its OWN rule. A meta-rule gated on top of the
    # per-construct rules would make improvement invisible until two rules were
    # discovered together, which is a credit-assignment trap for any optimiser.
    uses_template = f"template-for-{axiom.operator}" in active

    if not uses_template:
        # The naive output: identifiers in a row. Reads badly and never parses.
        parts = [axiom.subject, axiom.operator, axiom.property, axiom.filler]
        sentence = " ".join(p for p in parts if p)
        return {"sentence": sentence, "note": "literal rendering of the axiom"}

    if "use-the-lexicon-label" in active:
        sentence = ch9.verbalise(axiom, language)
    else:
        # Right template, wrong vocabulary: identifiers survive into the text.
        template = ch9.TEMPLATES[language][axiom.operator]
        sentence = template.format(subject=axiom.subject, filler=axiom.filler,
                                   property=axiom.property)

    if "correct-article" in active:
        sentence = _fix_article(sentence)
    return {"sentence": sentence, "note": f"template for {axiom.operator}"}


# --------------------------------------------------------------------------- #
# DSPy program
# --------------------------------------------------------------------------- #
_SIG = None


def VerbalisationSignature():
    global _SIG
    if _SIG is None:
        import dspy

        class _VerbalisationSignature(dspy.Signature):
            """Verbalise an axiom in controlled natural language."""

            axiom: str = dspy.InputField(desc="the axiom in Manchester-like syntax")
            subject: str = dspy.InputField()
            operator: str = dspy.InputField(desc="subclassof, some, only, disjoint or type")
            property: str = dspy.InputField(desc="the property, when the axiom has one")
            filler: str = dspy.InputField()
            language: str = dspy.InputField(desc="en, nl or de")
            sentence: str = dspy.OutputField(desc="one controlled-language sentence")
            note: str = dspy.OutputField(desc="the construct used")

        _SIG = _VerbalisationSignature
    return _SIG


def VerbalisationProgram(instruction: str | None = BASELINE_INSTRUCTION):
    import dspy

    class _Program(dspy.Module):
        def __init__(self):
            super().__init__()
            self.write = dspy.Predict(VerbalisationSignature())
            if instruction:
                self.write.signature = self.write.signature.with_instructions(instruction)

        def forward(self, axiom, subject, operator, property, filler, language):
            return self.write(axiom=axiom, subject=subject, operator=operator,
                              property=property, filler=filler, language=language)

    return _Program()


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@dataclass
class Ch9Context:
    log: object = None

    def __post_init__(self):
        from oe_course.tools import ToolCallLog

        self.log = self.log or ToolCallLog()


def build_toolset(ctx: Ch9Context):
    import json

    from langchain_core.tools import tool

    from oe_course.tools import instrument

    def list_templates(language: str = "en") -> str:
        """The controlled-language template for each construct, in one language.

        Call this before writing a sentence: free prose will not parse back.
        """
        return json.dumps(ch9.TEMPLATES.get(language, ch9.TEMPLATES["en"]))

    def lookup_label(term: str, language: str = "en") -> str:
        """The lexicon label for an ontology term in one language.

        Call this for every term you put in a sentence; the raw identifier is
        almost never the right surface form.
        """
        return json.dumps({"term": term, "language": language,
                           "label": ch9.label_for(term, language),
                           "lexicalised": language in ch9.LEXICON.get(term, {})})

    def check_round_trip(sentence: str, language: str = "en") -> str:
        """Parse a sentence back into an axiom and report what was recovered.

        This is the cheapest correctness check available: if the sentence does
        not parse back to the axiom you started from, it is wrong regardless of
        how good it reads.
        """
        recovered = ch9.parse_cnl(sentence, language)
        return json.dumps({"parses": recovered is not None,
                           "recovered": str(recovered) if recovered else None})

    def check_readability(sentence: str) -> str:
        """Report readability problems the round trip cannot see."""
        return json.dumps(ch9.readability(sentence))

    def lexicon_status(language: str) -> str:
        """How much of the vocabulary a language covers, and what is missing."""
        return json.dumps(ch9.lexicon_coverage(language))

    impls = [list_templates, lookup_label, check_round_trip,
             check_readability, lexicon_status]
    return [tool(instrument(fn, fn.__name__, ctx.log)) for fn in impls]


# --------------------------------------------------------------------------- #
# Optimal stopping: when to stop resampling
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DraftState:
    """How many attempts are spent, and the quality of the best draft in hand."""

    attempts: int
    quality: int          # index into the quality ladder; -1 means nothing yet

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"n={self.attempts},q={'-' if self.quality < 0 else self.quality}"


class RevisionMDP:
    """Sample a verbalisation, judge it, and decide whether to try again.

    This is **best-of-n sampling** as a decision problem, and it is the shape
    every LLM engineer meets without naming it. Each attempt costs; each draws a
    quality from a known distribution; accepting ends the episode with that
    quality as the reward.

    | | |
    |---|---|
    | **S** | attempts spent, and the best quality in hand |
    | **A** | ``accept`` the current draft, or ``retry`` |
    | **T** | **stochastic** — a fresh draft's quality is drawn, not chosen |
    | **R** | ``-cost`` per attempt; on accept, the quality accepted |

    The optimal policy is a **threshold rule that falls as the budget runs out**:
    early on, hold out for a good draft; with one attempt left, take what you
    have. Value iteration derives the thresholds exactly.
    """

    def __init__(self, qualities=(0.4, 0.7, 1.0), probabilities=(0.5, 0.3, 0.2),
                 cost: float = 0.05, max_attempts: int = 4, gamma: float = 1.0):
        assert abs(sum(probabilities) - 1.0) < 1e-9, "probabilities must sum to 1"
        self.qualities = tuple(qualities)
        self.probabilities = tuple(probabilities)
        self.cost = cost
        self.max_attempts = max_attempts
        self.gamma = gamma

    def initial_state(self) -> DraftState:
        return DraftState(0, -1)

    def is_terminal(self, state: DraftState) -> bool:
        return state.attempts < 0

    def states(self):
        out = [DraftState(0, -1)]
        for attempts in range(1, self.max_attempts + 1):
            out += [DraftState(attempts, q) for q in range(len(self.qualities))]
        out.append(DraftState(-1, -1))          # the absorbing accepted state
        return out

    def actions(self, state: DraftState):
        if self.is_terminal(state):
            return []
        options = []
        if state.quality >= 0:
            options.append("accept")
        if state.attempts < self.max_attempts:
            options.append("retry")
        return options or ["accept"]

    def transition(self, state: DraftState, action: str):
        if action == "accept":
            reward = self.qualities[state.quality] if state.quality >= 0 else 0.0
            return [(1.0, DraftState(-1, -1), reward)]
        # retry: pay the cost, keep the better of the old and new draft
        outcomes = []
        for index, probability in enumerate(self.probabilities):
            best = max(index, state.quality)
            outcomes.append(
                (probability, DraftState(state.attempts + 1, best), -self.cost))
        return outcomes

    def step(self, state: DraftState, action: str):
        import random

        outcomes = self.transition(state, action)
        roll, cumulative = random.random(), 0.0
        for probability, nxt, reward in outcomes:
            cumulative += probability
            if roll <= cumulative:
                return nxt, reward, self.is_terminal(nxt)
        probability, nxt, reward = outcomes[-1]
        return nxt, reward, self.is_terminal(nxt)

    def thresholds(self, policy: dict) -> list[dict]:
        """The accept/retry decision at each (attempts, quality) — the stopping rule."""
        rows = []
        for attempts in range(1, self.max_attempts + 1):
            row = {"attempts spent": attempts}
            for index, quality in enumerate(self.qualities):
                state = DraftState(attempts, index)
                row[f"q={quality}"] = policy.get(state, "-")
            rows.append(row)
        return rows
