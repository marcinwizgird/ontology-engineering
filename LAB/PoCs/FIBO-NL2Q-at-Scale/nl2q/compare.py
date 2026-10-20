"""Execution-result equivalence for NL2Query evaluation.

Two results are equivalent when their **row multisets** are equal after value
normalisation, up to a **column permutation** (a correct query may list the same columns
in another order). Comparison works on signatures, so gold results of any size need not
be stored:

* ``count`` — number of rows;
* ``col_digests`` — per column, an order-independent digest of its value multiset
  (used to find the permutation);
* ``row_digest`` — order-independent digest of the row multiset, in the signature's own
  column order.

Value normalisation: IRIs minted by the FIBEN mapping are reduced to their key (the gold
SQL returns raw ids where the SPARQL returns IRIs); numbers are compared at 6
significant digits (aggregates differ in the last bits across engines); temporal values by
their ISO form; strings stripped.

Lenient mode accepts a prediction whose columns are a superset of the gold columns (the
gold columns found by digest, the rest ignored) — reported separately from strict EX.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import itertools
import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Sequence

_MASK = (1 << 64) - 1
DATA_PREFIX = "https://example.org/fiben/data/"


def norm(v) -> str:
    if v is None:
        return "\x00null"
    if isinstance(v, bool):
        return "b:" + str(v).lower()
    if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
        f = float(v)
        if math.isnan(f):
            return "n:nan"
        if f == int(f) and abs(f) < 1e15:
            return f"n:{int(f)}"
        return "n:" + f"{f:.6g}"
    if isinstance(v, (dt.datetime, dt.date)):
        s = v.isoformat()
        return "t:" + (s[:-6] if s.endswith("+00:00") else s).replace("T00:00:00", "")
    s = str(v).strip()
    if s.startswith(DATA_PREFIX):
        s = s.rsplit("/", 1)[-1]
    # numeric strings (Ontop renders some numbers as text) compare as numbers
    try:
        f = float(s)
        if s.lower() not in ("nan", "inf", "-inf", "infinity"):
            return norm(f)
    except ValueError:
        pass
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return norm(dt.datetime.fromisoformat(s.replace("Z", "")))
        except ValueError:
            pass
    return "s:" + s


def _h(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "big")


@dataclass
class Signature:
    ncols: int
    count: int
    col_digests: list[int]
    row_digest: int
    sample: list[list[str]] = field(default_factory=list)   # first rows, normalised

    def to_json(self) -> dict:
        return {"ncols": self.ncols, "count": self.count,
                "col_digests": [str(d) for d in self.col_digests],
                "row_digest": str(self.row_digest), "sample": self.sample}

    @staticmethod
    def from_json(d: dict) -> "Signature":
        return Signature(d["ncols"], d["count"], [int(x) for x in d["col_digests"]],
                         int(d["row_digest"]), d.get("sample", []))


def _row_digest(rows: Iterable[Sequence[str]]) -> int:
    acc = 0
    for r in rows:
        acc = (acc + _h("\x1f".join(r))) & _MASK
    return acc


def signature(rows: Iterable[Sequence], ncols: int | None = None, sample: int = 20) -> Signature:
    normed = [[norm(v) for v in r] for r in rows]
    n = ncols if ncols is not None else (len(normed[0]) if normed else 0)
    cols = [0] * n
    for r in normed:
        for i, v in enumerate(r):
            cols[i] = (cols[i] + _h(v)) & _MASK
    return Signature(n, len(normed), cols, _row_digest(normed), normed[:sample])


@dataclass
class Match:
    strict: bool
    lenient: bool
    reason: str = ""
    relaxed: bool = False      # prediction columns = a subset of the gold columns, same rows count


def relaxed_match(gold: Signature, pred_rows: Sequence[Sequence], pred_ncols: int) -> bool:
    """Relaxed: the answer omits some of the gold query's context columns. Same row count and
    every predicted column has the value multiset of a distinct gold column. (Benchmarks like
    FIBEN project extra context columns — names, tickers — that a direct answer leaves out.)"""
    normed = [[norm(v) for v in r] for r in pred_rows]
    if len(normed) != gold.count or pred_ncols == 0 or pred_ncols > gold.ncols:
        return False
    if gold.count == 0:
        return True
    pcols = [0] * pred_ncols
    for r in normed:
        for i, v in enumerate(r):
            pcols[i] = (pcols[i] + _h(v)) & _MASK
    free = list(gold.col_digests)
    for d in pcols:
        if d not in free:
            return False
        free.remove(d)
    return True


def compare(gold: Signature, pred_rows: Sequence[Sequence], pred_ncols: int) -> Match:
    """Strict: same count, same number of columns, rows equal under a column
    permutation. Lenient: gold columns found inside wider prediction rows."""
    normed = [[norm(v) for v in r] for r in pred_rows]
    if len(normed) != gold.count:
        return Match(False, False, f"row count {len(normed)} != {gold.count}")
    if gold.count == 0:
        return Match(pred_ncols == gold.ncols or gold.ncols == 0, True, "both empty", relaxed=True)
    pcols = [0] * pred_ncols
    for r in normed:
        for i, v in enumerate(r):
            pcols[i] = (pcols[i] + _h(v)) & _MASK
    # candidate prediction columns for every gold column (equal value multisets)
    cands = [[j for j in range(pred_ncols) if pcols[j] == g] for g in gold.col_digests]
    if any(not c for c in cands):
        return Match(False, False, "a gold column has no equal prediction column")
    for perm in itertools.islice(itertools.product(*cands), 5000):
        if len(set(perm)) != len(perm):
            continue
        if _row_digest([[r[j] for j in perm] for r in normed]) == gold.row_digest:
            strict = pred_ncols == gold.ncols
            return Match(strict, True, "" if strict else "extra prediction columns", relaxed=strict)
    return Match(False, False, "columns match but rows differ")


def compare_all(gold: Signature, pred_rows, pred_ncols: int) -> Match:
    """strict / lenient (superset of gold columns) / relaxed (subset of gold columns)."""
    m = compare(gold, pred_rows, pred_ncols)
    if not m.relaxed:
        m.relaxed = m.strict or relaxed_match(gold, pred_rows, pred_ncols)
    return m
