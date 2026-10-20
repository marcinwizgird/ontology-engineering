"""Live spike (billed, a few cents): does DSPy + LiteLLM work with the configured Claude
model under the current API rules (no sampling parameters, thinking always on)? Checks a
plain predictor, the typed plan output, and cost accounting.

    NL2Q_MODEL=anthropic/claude-sonnet-5-5 python -m nl2q.spike
"""

from __future__ import annotations

import json
import time

import dspy

from . import evaluate
from .program import NL2SPARQL, make_lm


def main() -> None:
    lm = make_lm()
    if lm is None:
        raise SystemExit("set NL2Q_MODEL")
    dspy.configure(lm=lm)
    out = {"model": lm.model}
    t0 = time.time()
    r = dspy.Predict("question -> answer")(question="Reply with the single word: ready")
    out["plain"] = {"answer": r.answer, "s": round(time.time() - t0, 1)}
    t0 = time.time()
    p = NL2SPARQL()(question="Tell me the last traded value of Alphabet")
    out["program"] = {"refused": p.refused, "reason": p.reason[:200], "problems": p.problems,
                      "sparql_tail": (p.sparql or "")[-300:], "s": round(time.time() - t0, 1)}
    out["calls"] = len(lm.history)
    out["usage"] = [h.get("usage") for h in lm.history]
    out["litellm_cost"] = [h.get("cost") for h in lm.history]
    out["cost_usd"] = round(evaluate._cost_since(lm, 0), 4)
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
