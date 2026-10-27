"""Statistical analysis plan (specification §5.5).

FIBEN's questions are paraphrases of gold queries, and paraphrases succeed or fail
together, so every confidence interval resamples **gold queries** (clusters) and carries
all their paraphrases. Repeated runs are nested inside questions: the bootstrap resamples
runs within each resampled question, and McNemar uses the per-question majority outcome.
Runs are never pooled as if they were independent questions.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Hashable, Mapping, Sequence
from statistics import NormalDist

import numpy as np

from .. import stats as _stats

ITERS = 10_000


def majority(values: Sequence[bool]) -> bool:
    """True when more than half of the runs are True (ties count as False: not reliably right)."""
    return sum(bool(v) for v in values) * 2 > len(values)


def _cluster_index(clusters: Sequence[Hashable]) -> list[np.ndarray]:
    groups: dict[Hashable, list[int]] = defaultdict(list)
    for i, c in enumerate(clusters):
        groups[c].append(i)
    return [np.array(v) for v in groups.values()]


def _runs_matrix(values: Sequence[Sequence[float]]) -> tuple[np.ndarray, np.ndarray]:
    """Questions x runs, padded with NaN where a question has fewer runs."""
    width = max(len(v) for v in values)
    m = np.full((len(values), width), np.nan)
    for i, v in enumerate(values):
        m[i, :len(v)] = v
    return m, np.array([len(v) for v in values])


def _resample_mean(m: np.ndarray, counts: np.ndarray, idx: np.ndarray, rng) -> float:
    """Mean over the chosen questions of the mean over runs resampled within each question."""
    sub, k = m[idx], counts[idx]
    if sub.shape[1] == 1:
        return float(np.nanmean(sub[:, 0]))
    picks = (rng.random(sub.shape) * k[:, None]).astype(int)
    vals = np.take_along_axis(sub, picks, axis=1)
    return float(np.nanmean(vals.mean(axis=1)))


def cluster_bootstrap_ci(values: Sequence[float] | Sequence[Sequence[float]],
                         clusters: Sequence[Hashable], iters: int = ITERS,
                         alpha: float = 0.05, seed: int = 0) -> tuple[float, float, float]:
    """(mean, lo, hi). ``values[i]`` is one number or the list of run values of question i;
    ``clusters[i]`` is its gold query."""
    vals = [v if isinstance(v, (list, tuple)) else [v] for v in values]
    m, counts = _runs_matrix(vals)
    groups = _cluster_index(clusters)
    rng = np.random.default_rng(seed)
    point = float(np.mean([np.mean(v) for v in vals]))
    boots = np.empty(iters)
    for b in range(iters):
        idx = np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))])
        boots[b] = _resample_mean(m, counts, idx, rng)
    lo, hi = np.quantile(boots, [alpha / 2, 1 - alpha / 2])
    return point, float(lo), float(hi)


def paired_cluster_bootstrap_diff(a: Sequence[float] | Sequence[Sequence[float]],
                                  b: Sequence[float] | Sequence[Sequence[float]],
                                  clusters: Sequence[Hashable], iters: int = ITERS,
                                  alpha: float = 0.05, seed: int = 0) -> tuple[float, float, float]:
    """(mean(a) - mean(b), lo, hi), resampling the same gold queries for both arms."""
    va = [v if isinstance(v, (list, tuple)) else [v] for v in a]
    vb = [v if isinstance(v, (list, tuple)) else [v] for v in b]
    ma, ca = _runs_matrix(va)
    mb, cb = _runs_matrix(vb)
    groups = _cluster_index(clusters)
    rng = np.random.default_rng(seed)
    point = float(np.mean([np.mean(x) for x in va]) - np.mean([np.mean(x) for x in vb]))
    boots = np.empty(iters)
    for i in range(iters):
        idx = np.concatenate([groups[j] for j in rng.integers(0, len(groups), len(groups))])
        boots[i] = _resample_mean(ma, ca, idx, rng) - _resample_mean(mb, cb, idx, rng)
    lo, hi = np.quantile(boots, [alpha / 2, 1 - alpha / 2])
    return point, float(lo), float(hi)


def mcnemar_majority(a: Sequence[Sequence[bool]], b: Sequence[Sequence[bool]]) -> dict:
    """Exact McNemar on the per-question majority outcome of each arm's runs."""
    return _stats.mcnemar_exact([majority(x) for x in a], [majority(x) for x in b])


def mde_paired(n: int, discordant_rate: float, alpha: float = 0.05, power: float = 0.8) -> float:
    """Smallest difference in proportions a paired (McNemar) test detects with the given
    power, for ``n`` pairs and the observed share of discordant pairs (normal approximation)."""
    if n <= 0 or discordant_rate <= 0:
        return float("nan")
    z = NormalDist().inv_cdf(1 - alpha / 2) + NormalDist().inv_cdf(power)
    return z * (discordant_rate / n) ** 0.5


def n_for_mde(mde: float, discordant_rate: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Pairs needed to detect ``mde``."""
    z = NormalDist().inv_cdf(1 - alpha / 2) + NormalDist().inv_cdf(power)
    return int(np.ceil(discordant_rate * (z / mde) ** 2))


def holm(pvalues: Mapping[str, float]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values (monotone, capped at 1)."""
    items = sorted(pvalues.items(), key=lambda kv: kv[1])
    m, out, running = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = running
    return out
