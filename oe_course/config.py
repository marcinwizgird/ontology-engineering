"""Environment detection and shared paths for the Ontology Engineering course.

Everything in `oe_course` runs in one of two modes:

* **live**   — a real LLM (Anthropic) and, if it is up, a real Fuseki triplestore;
* **offline** — a deterministic *simulator* stands in for the LLM and an
  in-memory rdflib dataset stands in for Fuseki.

Offline mode exists so that every notebook in the course executes end-to-end
with no API key, no Docker, and no cost. It is **not** a pretend LLM that
returns canned strings: the simulator reacts to the instruction it is given
(see :mod:`oe_course.llm`), which is what makes the DSPy/GEPA optimisation labs
meaningful without spend. Students flip one environment variable to run the
same code against the real thing.
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PKG_DIR = Path(__file__).resolve().parent
DATA_DIR = PKG_DIR / "data"
REPO_ROOT = PKG_DIR.parent
ARTIFACTS_DIR = REPO_ROOT / "course" / "artifacts"


def artifacts_dir() -> Path:
    """Directory for generated files; created on first use."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    return ARTIFACTS_DIR


# --------------------------------------------------------------------------- #
# Models
#
# Model ids are pinned here so a course-wide upgrade is a one-line change.
# `claude-opus-5` is the current flagship; it rejects `temperature`/`top_p`/
# `top_k` at non-default values, which is why `dspy_lm()` in oe_course.llm
# passes temperature=1.0 (the accepted default) rather than DSPy's usual 0.0.
# --------------------------------------------------------------------------- #
CHAT_MODEL = os.environ.get("OE_COURSE_MODEL", "claude-opus-5")
#: DSPy routes through LiteLLM, which wants a `provider/model` string.
DSPY_MODEL = os.environ.get("OE_COURSE_DSPY_MODEL", f"anthropic/{CHAT_MODEL}")
#: GEPA's reflection LM proposes new instructions; it should be a strong model.
REFLECTION_MODEL = os.environ.get("OE_COURSE_REFLECTION_MODEL", DSPY_MODEL)

#: Adaptive thinking is on by default on claude-opus-5; `max_tokens` caps
#: thinking *plus* answer, so leave real headroom.
MAX_TOKENS = int(os.environ.get("OE_COURSE_MAX_TOKENS", "16000"))

# --------------------------------------------------------------------------- #
# Fuseki
# --------------------------------------------------------------------------- #
FUSEKI_URL = os.environ.get("OE_COURSE_FUSEKI_URL", "http://localhost:3030")
FUSEKI_DATASET = os.environ.get("OE_COURSE_FUSEKI_DATASET", "ontology")
FUSEKI_TIMEOUT = float(os.environ.get("OE_COURSE_FUSEKI_TIMEOUT", "2.0"))


def offline() -> bool:
    """True when the course should use simulators instead of a live LLM.

    Forced on with ``OE_COURSE_OFFLINE=1``; otherwise offline iff no Anthropic
    credential is visible in the environment.
    """
    forced = os.environ.get("OE_COURSE_OFFLINE", "").strip().lower()
    if forced in {"1", "true", "yes"}:
        return True
    if forced in {"0", "false", "no"}:
        return False
    return not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def describe_environment() -> dict:
    """A small dict the notebooks print in their setup cell."""
    from oe_course.sparql import fuseki_available  # local import: avoids cycle

    return {
        "mode": "offline (simulated LLM)" if offline() else "live",
        "chat_model": CHAT_MODEL,
        "dspy_model": DSPY_MODEL,
        "fuseki": f"{FUSEKI_URL}/{FUSEKI_DATASET}" if fuseki_available() else "in-memory rdflib",
        "artifacts": str(ARTIFACTS_DIR),
    }
