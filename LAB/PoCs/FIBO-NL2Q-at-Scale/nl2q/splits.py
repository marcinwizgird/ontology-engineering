"""Train / validation / test splits by **gold query** (``uniqueQueryID``), so paraphrases of
one query never cross splits, stratified by query type. Deterministic (seeded).

train 40% — example bank, GEPA training set · val 20% — GEPA Pareto set, numeric tuning ·
test 40% — frozen; scored only for a release candidate.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict

from . import gold, paths

SEED = 20261019
FRACTIONS = (("train", 0.4), ("val", 0.2), ("test", 0.4))


def make() -> dict[str, list[int]]:
    by_type: dict[str, list[int]] = defaultdict(list)
    seen = set()
    for q in gold.questions():
        if q.sql_id not in seen:
            seen.add(q.sql_id)
            by_type[q.query_type].append(q.sql_id)
    rng = random.Random(SEED)
    out = {name: [] for name, _ in FRACTIONS}
    for t in sorted(by_type):
        ids = sorted(by_type[t])
        rng.shuffle(ids)
        n = len(ids)
        a = round(n * FRACTIONS[0][1])
        b = a + round(n * FRACTIONS[1][1])
        out["train"] += ids[:a]
        out["val"] += ids[a:b]
        out["test"] += ids[b:]
    return {k: sorted(v) for k, v in out.items()}


def load() -> dict[str, list[int]]:
    f = paths.GOLD_DIR / "splits.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    s = make()
    f.write_text(json.dumps(s, indent=0), encoding="utf-8")
    return s


def questions(split: str) -> list[gold.Question]:
    ids = set(load()[split]) if split != "all" else None
    return [q for q in gold.questions() if ids is None or q.sql_id in ids]
