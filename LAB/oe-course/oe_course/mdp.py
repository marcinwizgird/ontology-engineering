"""Agentic tasks as Markov decision processes.

Why bother formalising an LLM agent as an MDP? Because it converts vague
questions ("is the agent efficient?", "did it gather enough evidence?") into
ones with answers. Once the task is an MDP you can compute the optimal value
:math:`V^*` by value iteration and report the agent's *regret* against it —
a far sharper instrument than eyeballing a transcript.

The formalisation used throughout the course
--------------------------------------------
========  ====================================================================
:math:`S` what the agent has established so far: the set of evidence it holds,
          plus whether it has committed to an answer
:math:`A` one tool call per kind of evidence, plus a ``submit`` action
:math:`T` deterministic for tool calls over a fixed artefact (the tools are pure
          functions of the graph); stochastic once a sampled LLM chooses actions
:math:`R` ``-cost`` for each tool call, and on ``submit`` the task-quality score
          the evaluation metric assigns to the answer that evidence supports
:math:`γ` a discount that expresses impatience; ``1.0`` for finite-horizon tasks
========  ====================================================================

The reward deliberately contains the *evaluation metric* used in
:mod:`oe_course.evaluation`. That is the whole point: the thing GEPA optimises,
the thing the grader measures, and the thing the MDP rewards are one function.

Two views of the same episode
-----------------------------
:class:`FiniteMDP` gives the analytical view (enumerable states, exact solution).
:func:`episode_from_tool_log` gives the empirical view — it replays what a real
LangChain agent did, from :class:`oe_course.tools.ToolCallLog`, into the same
state/action/reward vocabulary. Comparing the two is the core lab exercise.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Hashable, Iterable, Protocol

__all__ = [
    "FiniteMDP",
    "EvidenceMDP",
    "Transition",
    "Episode",
    "run_episode",
    "value_iteration",
    "policy_value",
    "random_policy",
    "greedy_policy",
    "episode_from_tool_log",
    "SUBMIT",
]

SUBMIT = "submit"


# --------------------------------------------------------------------------- #
# Episode records
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Transition:
    state: Hashable
    action: str
    reward: float
    next_state: Hashable
    done: bool

    def to_dict(self) -> dict:
        return {
            "state": str(self.state),
            "action": self.action,
            "reward": round(self.reward, 4),
            "next_state": str(self.next_state),
            "done": self.done,
        }


@dataclass
class Episode:
    transitions: list[Transition] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.transitions)

    @property
    def actions(self) -> list[str]:
        return [t.action for t in self.transitions]

    @property
    def rewards(self) -> list[float]:
        return [t.reward for t in self.transitions]

    def total_reward(self) -> float:
        return sum(self.rewards)

    def discounted_return(self, gamma: float = 1.0) -> float:
        """:math:`G_0 = \\sum_t \\gamma^t r_t` — the quantity a policy maximises."""
        return sum((gamma ** t) * r for t, r in enumerate(self.rewards))

    def to_list(self) -> list[dict]:
        return [t.to_dict() for t in self.transitions]


# --------------------------------------------------------------------------- #
# The MDP interface
# --------------------------------------------------------------------------- #
class FiniteMDP(Protocol):
    """A finite MDP with deterministic-or-stochastic transitions.

    ``transition`` returns ``[(probability, next_state, reward), ...]``, which
    covers both cases and is exactly the form value iteration needs.
    """

    gamma: float

    def states(self) -> Iterable[Hashable]: ...
    def actions(self, state: Hashable) -> list[str]: ...
    def transition(self, state: Hashable, action: str) -> list[tuple[float, Hashable, float]]: ...
    def is_terminal(self, state: Hashable) -> bool: ...
    def initial_state(self) -> Hashable: ...


# --------------------------------------------------------------------------- #
# The concrete family used by the chapter labs
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EvidenceState:
    """Evidence held so far, and whether the agent has committed."""

    evidence: frozenset[str]
    submitted: bool = False

    def __str__(self) -> str:  # pragma: no cover - display only
        held = ",".join(sorted(self.evidence)) or "-"
        return f"[{held}]{'!' if self.submitted else ''}"


class EvidenceMDP:
    """Gather evidence under a budget, then commit to an answer.

    This is the shape of nearly every ontology-engineering agent task in the
    course: assess an artefact, propose an axiom, answer a competency question.
    The agent chooses which evidence to buy before it answers, and the reward
    trades answer quality against the cost of gathering.

    Parameters
    ----------
    evidence_kinds:
        The tool calls available, e.g. ``["metrics", "spectrum", "smells"]``.
    score:
        ``score(evidence) -> float in [0, 1]`` — how good an answer that
        evidence set supports. This is where the evaluation metric plugs in.
    step_cost:
        Cost charged per tool call. Raising it makes the optimal policy
        parsimonious; setting it to 0 makes gathering everything optimal.
    max_steps:
        Horizon. Exceeding it forces termination with no submission bonus.
    """

    def __init__(
        self,
        evidence_kinds: list[str],
        score: Callable[[frozenset[str]], float],
        step_cost: float = 0.05,
        max_steps: int | None = None,
        gamma: float = 1.0,
    ):
        self.evidence_kinds = list(evidence_kinds)
        self.score = score
        self.step_cost = step_cost
        self.max_steps = max_steps if max_steps is not None else len(evidence_kinds) + 1
        self.gamma = gamma

    # -- interface ----------------------------------------------------------
    def initial_state(self) -> EvidenceState:
        return EvidenceState(frozenset())

    def is_terminal(self, state: EvidenceState) -> bool:
        return state.submitted

    def states(self) -> list[EvidenceState]:
        """All :math:`2^{|E|}` evidence sets, submitted and not."""
        out = []
        for mask in range(1 << len(self.evidence_kinds)):
            ev = frozenset(
                k for i, k in enumerate(self.evidence_kinds) if mask & (1 << i)
            )
            out.append(EvidenceState(ev, False))
            out.append(EvidenceState(ev, True))
        return out

    def actions(self, state: EvidenceState) -> list[str]:
        if state.submitted:
            return []
        # Re-running a tool you have already run is available but never useful:
        # it costs and changes nothing. Excluding it keeps the state space
        # acyclic and the exercise about *which* evidence, not how many times.
        remaining = [k for k in self.evidence_kinds if k not in state.evidence]
        if len(state.evidence) >= self.max_steps:
            return [SUBMIT]
        return remaining + [SUBMIT]

    def transition(self, state: EvidenceState, action: str):
        if action == SUBMIT:
            return [(1.0, EvidenceState(state.evidence, True), self.score(state.evidence))]
        nxt = EvidenceState(state.evidence | {action}, False)
        return [(1.0, nxt, -self.step_cost)]

    # -- convenience --------------------------------------------------------
    def step(self, state: EvidenceState, action: str):
        """Sample one transition — the gym-style interface a policy drives."""
        outcomes = self.transition(state, action)
        r = random.random()
        cumulative = 0.0
        for prob, nxt, reward in outcomes:
            cumulative += prob
            if r <= cumulative:
                return nxt, reward, self.is_terminal(nxt)
        prob, nxt, reward = outcomes[-1]
        return nxt, reward, self.is_terminal(nxt)


# --------------------------------------------------------------------------- #
# Solving and evaluating
# --------------------------------------------------------------------------- #
def value_iteration(mdp, tol: float = 1e-9, max_sweeps: int = 1000):
    """Exact :math:`V^*` and a greedy optimal policy for a finite MDP.

    Returns ``(V, policy)``. With this in hand, an agent's episode return can be
    reported as *regret* — how much value the LLM left on the table — which is
    a much more informative number than a raw score.
    """
    V = {s: 0.0 for s in mdp.states()}
    for _ in range(max_sweeps):
        delta = 0.0
        for s in V:
            if mdp.is_terminal(s):
                continue
            acts = mdp.actions(s)
            if not acts:
                continue
            best = max(
                sum(p * (r + mdp.gamma * V[ns]) for p, ns, r in mdp.transition(s, a))
                for a in acts
            )
            delta = max(delta, abs(best - V[s]))
            V[s] = best
        if delta < tol:
            break

    policy = {}
    for s in V:
        if mdp.is_terminal(s) or not mdp.actions(s):
            continue
        policy[s] = max(
            mdp.actions(s),
            key=lambda a: sum(
                p * (r + mdp.gamma * V[ns]) for p, ns, r in mdp.transition(s, a)
            ),
        )
    return V, policy


Policy = Callable[[object, list[str]], str]


def random_policy(rng: random.Random | None = None) -> Policy:
    rng = rng or random.Random(0)
    return lambda state, actions: rng.choice(actions)


def greedy_policy(table: dict) -> Policy:
    """Follow a policy table (e.g. the one :func:`value_iteration` returns)."""
    return lambda state, actions: table.get(state, actions[-1])


def run_episode(mdp, policy: Policy, max_steps: int = 50) -> Episode:
    """Roll the policy out once and record the trajectory."""
    state = mdp.initial_state()
    ep = Episode()
    for _ in range(max_steps):
        if mdp.is_terminal(state):
            break
        actions = mdp.actions(state)
        if not actions:
            break
        action = policy(state, actions)
        nxt, reward, done = mdp.step(state, action)
        ep.transitions.append(Transition(state, action, reward, nxt, done))
        state = nxt
        if done:
            break
    return ep


def policy_value(mdp, policy: Policy, episodes: int = 200) -> float:
    """Monte-Carlo estimate of :math:`V^\\pi(s_0)`."""
    return sum(run_episode(mdp, policy).discounted_return(mdp.gamma) for _ in range(episodes)) / episodes


# --------------------------------------------------------------------------- #
# Bridging a real agent run into the MDP vocabulary
# --------------------------------------------------------------------------- #
def episode_from_tool_log(
    log,
    mdp: EvidenceMDP,
    tool_to_evidence: dict[str, str],
    final_score: float,
) -> Episode:
    """Replay a LangChain agent's tool log as an MDP episode.

    Tool calls that map to no evidence kind (``list_artefacts``, a failed call)
    still cost a step — that is exactly the inefficiency the MDP view exposes
    and the reward penalises.
    """
    state = mdp.initial_state()
    ep = Episode()
    for call in log.calls:
        kind = tool_to_evidence.get(call.name)
        reward = -mdp.step_cost
        nxt = EvidenceState(state.evidence | ({kind} if kind else set()), False)
        ep.transitions.append(Transition(state, call.name, reward, nxt, False))
        state = nxt
    terminal = EvidenceState(state.evidence, True)
    ep.transitions.append(Transition(state, SUBMIT, final_score, terminal, True))
    return ep
