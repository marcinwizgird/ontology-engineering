"""Environment detection and shared paths for the Ontology Engineering course.

The course runs against the real thing: every LLM call goes to Anthropic, and
SPARQL goes to Apache Jena Fuseki when it is up (``infra/fuseki``). There is no
simulated model. The assignments measure what Claude actually does, so a number
in a notebook is a number about the model — with the cost that implies.

Credentials are resolved the way the Anthropic SDK resolves them
(``ANTHROPIC_API_KEY`` or ``ANTHROPIC_AUTH_TOKEN``). For convenience a ``.env``
file at the course root (``oe-course/.env``, see ``.env.example``) is loaded on
import; values already set in the environment win.
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
ENV_FILE = REPO_ROOT / ".env"


def artifacts_dir() -> Path:
    """Directory for generated files; created on first use."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    return ARTIFACTS_DIR


def _load_env_file(path: Path = ENV_FILE) -> None:
    """Load ``KEY=VALUE`` lines from the course ``.env``; never override the shell."""
    if not path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:  # python-dotenv is optional; parse the simple format by hand
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))
        return
    load_dotenv(path, override=False)


_load_env_file()

# --------------------------------------------------------------------------- #
# Models
#
# Model ids are pinned here so a course-wide upgrade is a one-line change.
# `claude-opus-5` rejects `temperature`/`top_p`/`top_k` at non-default values,
# which is why `dspy_lm()` in oe_course.llm passes temperature=1.0 (the accepted
# default) rather than DSPy's usual 0.0.
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


def has_credentials() -> bool:
    """Is an Anthropic credential visible to the SDK?"""
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


class MissingCredentialsError(RuntimeError):
    """Raised before the first billed call when no Anthropic credential is set."""


def require_credentials() -> None:
    """Fail fast, with instructions, when there is nothing to authenticate with."""
    if not has_credentials():
        raise MissingCredentialsError(
            "No Anthropic credential found. Set ANTHROPIC_API_KEY in your shell, or put "
            f"it in {ENV_FILE} (copy .env.example). The course calls the live API; "
            "there is no offline mode."
        )


def describe_environment() -> dict:
    """A small dict the notebooks print in their setup cell."""
    from oe_course.sparql import fuseki_available  # local import: avoids cycle

    return {
        "credentials": "found" if has_credentials() else "MISSING - set ANTHROPIC_API_KEY",
        "chat_model": CHAT_MODEL,
        "dspy_model": DSPY_MODEL,
        "reflection_model": REFLECTION_MODEL,
        "fuseki": f"{FUSEKI_URL}/{FUSEKI_DATASET}" if fuseki_available() else "in-memory rdflib",
        "artifacts": str(ARTIFACTS_DIR),
    }
