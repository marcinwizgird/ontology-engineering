"""The Claude provider for LangExtract.

LangExtract ships providers for Gemini, OpenAI and Ollama but not for Claude,
so :class:`AnthropicLanguageModel` implements the ``BaseLanguageModel``
contract — ``infer(batch_prompts) -> Iterator[Sequence[ScoredOutput]]`` — and
registers itself for ``claude-*`` / ``anthropic-*`` model ids.

Every extraction here is a real model call. There is no offline stand-in: a
missing credential is an error, not a fallback.
"""

from __future__ import annotations

import concurrent.futures
import os
import pathlib
from collections.abc import Iterator, Sequence
from typing import Any

import langextract as lx
from langextract.core import base_model, types as lx_types

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"

_ANTHROPIC_SYSTEM = (
    "You are a careful information-extraction engine. Answer only with the "
    "JSON object the prompt's examples demonstrate, wrapped in a ```json "
    "fence. Emit no commentary before or after the fence."
)


# --------------------------------------------------------------------------- #
# Credentials
# --------------------------------------------------------------------------- #
def _load_dotenv() -> None:
    """Read ``ANTHROPIC_*`` keys from a repo-root ``.env`` if not already set.

    A convenience for the case where the key lives in the project rather than
    the shell that launched the interpreter. Only fills in variables that are
    absent, so the real environment always wins.
    """
    for parent in [pathlib.Path(__file__).resolve().parent, *pathlib.Path(__file__).resolve().parents]:
        candidate = parent / ".env"
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith("ANTHROPIC_") and key not in os.environ:
                os.environ[key] = value.strip().strip("'\"")
        return


def anthropic_available() -> bool:
    """True when the Anthropic SDK and some credential are both present.

    An unset ``ANTHROPIC_API_KEY`` is not proof of no credentials: the SDK also
    honours ``ANTHROPIC_AUTH_TOKEN`` and profiles written by ``ant auth login``.
    """
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    _load_dotenv()
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    config = pathlib.Path.home() / ".config" / "anthropic"
    return config.is_dir() and any(config.iterdir())


class MissingCredentialError(RuntimeError):
    """Raised when an extraction is requested with no way to reach a model."""


_CREDENTIAL_HELP = """\
No Anthropic credential found, and this package does not simulate one.

Expose the key in any of these ways, then re-run:

  * put ANTHROPIC_API_KEY=sk-ant-... in a `.env` file at the repository root
    (read automatically; add `.env` to .gitignore), or
  * set it in the environment of the process that launches Python
    (`setx ANTHROPIC_API_KEY "sk-ant-..."` on Windows, then restart the shell), or
  * run `ant auth login` and let the SDK pick up the stored profile, or
  * pass it explicitly: extract_ontology(..., model_kwargs={"api_key": "..."}).
"""


# --------------------------------------------------------------------------- #
# The provider
# --------------------------------------------------------------------------- #
@lx.providers.registry.register(r"^claude", r"^anthropic", priority=20)
class AnthropicLanguageModel(base_model.BaseLanguageModel):
    """LangExtract provider backed by the Anthropic Messages API.

    LangExtract's resolver strips a ```json fence before parsing, and the
    format handler already teaches the envelope through the few-shot examples,
    so this provider asks for fenced JSON rather than declaring a schema —
    that keeps it working across every Claude model without pinning a
    structured-output shape.
    """

    def __init__(
        self,
        model_id: str = DEFAULT_ANTHROPIC_MODEL,
        api_key: str | None = None,
        max_tokens: int = 8000,
        effort: str = "medium",
        thinking: bool = True,
        max_workers: int = 4,
        format_type: lx_types.FormatType = lx_types.FormatType.JSON,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise ImportError(
                "The Anthropic provider needs the `anthropic` package: "
                "pip install anthropic"
            ) from exc

        if api_key is None:
            _load_dotenv()
            if not anthropic_available():
                raise MissingCredentialError(_CREDENTIAL_HELP)

        self.model_id = model_id
        self.max_tokens = max_tokens
        self.effort = effort
        self.thinking = thinking
        self.max_workers = max_workers
        self.format_type = format_type
        self._client = (
            anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        )
        #: Token usage accumulated across every call this instance made.
        self.usage: dict[str, int] = {
            "requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
        }

    @property
    def name(self) -> str:
        return self.model_id

    # -- BaseLanguageModel contract ----------------------------------------- #
    def infer(
        self, batch_prompts: Sequence[str], **kwargs: Any
    ) -> Iterator[Sequence[lx_types.ScoredOutput]]:
        """Answer a batch of prompts, one Messages request per prompt."""
        merged = self.merge_kwargs(kwargs)
        if len(batch_prompts) == 1:
            yield [lx_types.ScoredOutput(score=1.0, output=self._call(batch_prompts[0], merged))]
            return

        workers = min(self.max_workers, len(batch_prompts))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for text in pool.map(lambda p: self._call(p, merged), batch_prompts):
                yield [lx_types.ScoredOutput(score=1.0, output=text)]

    def _call(self, prompt: str, options: dict[str, Any]) -> str:
        request: dict[str, Any] = {
            "model": self.model_id,
            "max_tokens": options.get("max_tokens", self.max_tokens),
            # The instructions and few-shot examples are identical for every
            # chunk, so cache that prefix; only the trailing question varies.
            "system": [
                {
                    "type": "text",
                    "text": _ANTHROPIC_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {"effort": options.get("effort", self.effort)},
        }
        if self.thinking:
            request["thinking"] = {"type": "adaptive"}

        response = self._client.messages.create(**request)
        self._record(response)
        if response.stop_reason == "refusal":  # stop_details is only set here
            detail = getattr(response.stop_details, "explanation", "") or ""
            raise RuntimeError(f"Claude declined the extraction request. {detail}")
        return "".join(b.text for b in response.content if b.type == "text")

    def _record(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        self.usage["requests"] += 1
        for key in ("input_tokens", "output_tokens", "cache_read_input_tokens"):
            self.usage[key] += getattr(usage, key, 0) or 0


# --------------------------------------------------------------------------- #
# Model selection
# --------------------------------------------------------------------------- #
def resolve_model(
    model_id: str | None = None, **model_kwargs: Any
) -> base_model.BaseLanguageModel | None:
    """Pick the language model to run the extraction with.

    Returns an :class:`AnthropicLanguageModel` for ``None``/``"auto"`` and for
    any ``claude-*`` id, or ``None`` when ``model_id`` names a provider
    LangExtract already ships (``gemini-*``, ``gpt-*``, an Ollama tag) — in that
    case :func:`~langextract_ontology.extract.extract_ontology` hands the id to
    LangExtract's own factory.

    Raises :class:`MissingCredentialError` rather than degrading to anything
    that is not a real model.
    """
    if model_id in (None, "auto"):
        model_id = DEFAULT_ANTHROPIC_MODEL

    if model_id.startswith(("claude", "anthropic")):
        return AnthropicLanguageModel(model_id=model_id, **model_kwargs)
    return None  # a provider LangExtract resolves itself
