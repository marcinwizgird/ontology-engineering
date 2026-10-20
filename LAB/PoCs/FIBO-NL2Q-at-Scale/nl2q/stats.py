"""Paired statistics for comparing systems on the same questions."""

from __future__ import annotations

import math
import random
from typing import Sequence


def mcnemar_exact(a: Sequence[bool], b: Sequence[bool]) -> dict:
    """Exact two-sided McNemar test on paired binary outcomes (a vs b, same items)."""
    assert len(a) == len(b)
    n01 = sum(1 for x, y in zip(a, b) if not x and y)   # b right, a wrong
    n10 = sum(1 for x, y in zip(a, b) if x and not y)
    n = n01 + n10
    if n == 0:
        return {"n01": 0, "n10": 0, "p": 1.0}
    k = min(n01, n10)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return {"n01": n01, "n10": n10, "p": min(1.0, 2 * p)}


def bootstrap_ci(values: Sequence[float], iters: int = 10_000, alpha: float = 0.05,
                 seed: int = 7) -> tuple[float, float, float]:
    """Mean and percentile CI."""
    if not values:
        return (float("nan"),) * 3
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))
    lo, hi = means[int(alpha / 2 * iters)], means[int((1 - alpha / 2) * iters) - 1]
    return sum(values) / n, lo, hi


def paired_bootstrap_diff(a: Sequence[float], b: Sequence[float], iters: int = 10_000,
                          seed: int = 7) -> tuple[float, float, float]:
    """Mean of (b - a) with a 95% percentile CI, resampling items jointly."""
    d = [y - x for x, y in zip(a, b)]
    return bootstrap_ci(d, iters, seed=seed)


def cohen_kappa(a: Sequence[bool], b: Sequence[bool]) -> float:
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)
