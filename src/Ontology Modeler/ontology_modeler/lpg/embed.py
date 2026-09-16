"""Embedding strategy: turn a concept profile into a vector (spec Section 5.2).

Two interchangeable implementations behind one Protocol:

* HashingEmbedder (default) -- deterministic, dependency-free character-n-gram hashing,
  L2-normalised. NOT semantic, but stable, fast, needs no model download, and is enough
  to exercise the vector-index plumbing end to end. Same text -> same vector.

* SentenceTransformerEmbedder (optional) -- wraps sentence-transformers (all-MiniLM-L6-v2,
  384-d) for real semantic embeddings, exactly the spec's 5.2 snippet. Import-guarded so
  the heavy torch dependency stays opt-in.

* TfidfSvdEmbedder -- latent semantic indexing fitted on the projected ontology itself.
  Needs a `fit(corpus)` pass before `encode`, costs one SVD, and pulls in nothing beyond
  scikit-learn. It is the sensible default for retrieval over a single closed ontology:
  the vocabulary *is* the corpus, so "deposit account" and "demand deposit" end up near
  each other because FIBO uses them in the same profiles -- something the hashing
  embedder cannot do and a general-purpose sentence encoder does not know about FIBO.

get_embedder(kind) returns one by name; the converter defaults to "tfidf".
"""

from __future__ import annotations

import hashlib
import math
import pickle
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    """Anything that maps text to a fixed-length list of floats.

    An embedder that needs to see the corpus first exposes `fit(corpus)`; the converter
    calls it when present. Stateless embedders simply do not define it.
    """

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


class TfidfSvdEmbedder:
    """TF-IDF + truncated SVD (latent semantic indexing) fitted on the concept profiles.

    Deterministic, CPU-only, and tuned to the ontology at hand rather than to general
    English. `fit` must run before `encode`; `encode` on an unfitted embedder raises
    rather than silently returning zeros, because a zero vector would be indexed happily
    and quietly break retrieval.
    """

    def __init__(self, dim: int = 256, min_df: int = 1, ngram_range: tuple = (1, 2)):
        self.dim = dim
        self._min_df = min_df
        self._ngram_range = ngram_range
        self._vectorizer = None
        self._svd = None

    def fit(self, corpus: list[str]) -> "TfidfSvdEmbedder":
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        texts = [t for t in corpus if t and t.strip()]
        if not texts:
            raise ValueError("TfidfSvdEmbedder.fit got an empty corpus")
        self._vectorizer = TfidfVectorizer(
            lowercase=True, stop_words="english", min_df=self._min_df,
            ngram_range=self._ngram_range, sublinear_tf=True,
        )
        matrix = self._vectorizer.fit_transform(texts)
        # SVD cannot produce more components than the smaller matrix dimension.
        self.dim = max(2, min(self.dim, min(matrix.shape) - 1))
        self._svd = TruncatedSVD(n_components=self.dim, random_state=0)
        self._svd.fit(matrix)
        return self

    def encode(self, text: str) -> list[float]:
        if self._vectorizer is None or self._svd is None:
            raise RuntimeError("TfidfSvdEmbedder.encode called before fit()")
        vec = self._svd.transform(self._vectorizer.transform([text or ""]))[0]
        norm = math.sqrt(float((vec * vec).sum()))
        return (vec / norm).tolist() if norm > 0 else vec.tolist()

    @property
    def explained_variance(self) -> float:
        """How much of the corpus variance the retained components carry."""
        return float(self._svd.explained_variance_ratio_.sum()) if self._svd else 0.0


def get_embedder(kind: str = "tfidf", **kwargs) -> Embedder:
    """Factory: 'tfidf' (default), 'hash', or 'sentence-transformers'."""
    kind = (kind or "tfidf").lower()
    if kind in ("hash", "hashing"):
        return HashingEmbedder(**kwargs)
    if kind in ("tfidf", "lsi", "svd", "default"):
        return TfidfSvdEmbedder(**kwargs)
    if kind in ("st", "sentence-transformers", "sbert", "minilm"):
        return SentenceTransformerEmbedder(**kwargs)
    raise ValueError(f"unknown embedder kind: {kind!r}")


# -- persistence -------------------------------------------------------------- #

def save_embedder(embedder: Embedder, path) -> "Path":
    """Persist a fitted embedder beside its graph. Pickle, because a fitted TF-IDF
    vocabulary plus an SVD basis is exactly a Python object graph and nothing lighter
    round-trips it faithfully."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        pickle.dump(embedder, fh, protocol=pickle.HIGHEST_PROTOCOL)
    return path


def load_embedder(path) -> Embedder:
    """Load an embedder saved by `save_embedder`."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"no fitted embedder at {path}. Re-run the projection with --embed, "
            f"which writes it."
        )
    with path.open("rb") as fh:
        return pickle.load(fh)
