"""Embedding strategy: turn a concept profile into a vector (spec Section 5.2).

Two interchangeable implementations behind one Protocol:

* HashingEmbedder (default) -- deterministic, dependency-free character-n-gram hashing,
  L2-normalised. NOT semantic, but stable, fast, needs no model download, and is enough
  to exercise the vector-index plumbing end to end. Same text -> same vector.

* SentenceTransformerEmbedder (optional) -- wraps sentence-transformers (all-MiniLM-L6-v2,
  384-d) for real semantic embeddings, exactly the spec's 5.2 snippet. Import-guarded so
  the heavy torch dependency stays opt-in.

get_embedder(kind) returns one by name; the converter defaults to "hash".
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """Anything that maps text to a fixed-length list of floats."""

    dim: int

    def encode(self, text: str) -> list[float]:
        ...


class HashingEmbedder:
    """Deterministic character-n-gram hashing embedder. No external model."""

    def __init__(self, dim: int = 384, ngram: int = 3):
        self.dim = dim
        self.ngram = ngram

    def encode(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        s = (text or "").lower()
        if not s:
            return vec
        # Signed-hash trick keeps the bag roughly zero-mean so unrelated texts don't all
        # point the same way.
        padded = f"  {s}  "
        for i in range(len(padded) - self.ngram + 1):
            gram = padded[i:i + self.ngram]
            h = int.from_bytes(hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest(), "big")
            vec[h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in vec))
        return [x / norm for x in vec] if norm > 0 else vec


class SentenceTransformerEmbedder:
    """Real semantic embeddings via sentence-transformers (spec 5.2). Optional dependency."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - only when opted in
            raise ImportError(
                "sentence-transformers is not installed. Install it "
                "(`pip install sentence-transformers`, pulls torch), or use HashingEmbedder."
            ) from exc
        self._model = SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def encode(self, text: str) -> list[float]:
        return self._model.encode(text or "", normalize_embeddings=True).tolist()


def get_embedder(kind: str = "hash", **kwargs) -> Embedder:
    """Factory: 'hash' -> HashingEmbedder (default), 'sentence-transformers' -> real model."""
    kind = (kind or "hash").lower()
    if kind in ("hash", "hashing", "default"):
        return HashingEmbedder(**kwargs)
    if kind in ("st", "sentence-transformers", "sbert", "minilm"):
        return SentenceTransformerEmbedder(**kwargs)
    raise ValueError(f"unknown embedder kind: {kind!r}")
