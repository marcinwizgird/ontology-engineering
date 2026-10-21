"""Benchmarks (algorithm level of Munzner's nested model).

``extract``  server side, offline: FIBO load into a SIP project, index build, and
             ``viz.neighbourhood`` through ``Platform.call`` at stepped caps over
             deterministic seeds (median / p95 ms, payload size).
``browser``  client side: serves the app on a free port, drives ``web/bench.html`` in
             headless Chrome or Edge, collects the posted results (first paint, dagre
             layout, fps during scripted pan/zoom, selection latency, heap).

Thresholds are declared in PLAN.md *before* the runs; results go to ``artifacts/``.

    python -m ontoviz.bench extract
    python -m ontoviz.bench browser
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import socket
import statistics
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from . import _paths
from . import demo
from semantic_intelligence.platform import Platform

CAPS = (50, 100, 300, 1000)
BROWSERS = (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


def _p(xs, q):
    s = sorted(xs)
    return s[min(len(s) - 1, int(q * len(s)))]


def fibo_platform() -> tuple[Platform, dict]:
    p = demo._platform()
    t = time.perf_counter()
    nt = demo.fibo_ntriples()
    parse = time.perf_counter() - t
    load = demo.add_fibo(p)
    t = time.perf_counter()
    stats = p.call("val", "fibo", "viz.stats")
    index = time.perf_counter() - t
    return p, {"ntriples_read_s": round(parse, 2), "load_s": round(load, 2),
               "index_build_s": round(index, 2), "index": stats}


def extract(seeds: int = 30) -> dict:
    p, setup = fibo_platform()
    ix = __import__("ontoviz.sip_ops", fromlist=["bundle"]).bundle(p.projects["fibo"])["index"]
    pool = sorted(n for n in ix.nodes if ix.adj.get(n))
    sample = random.Random(7).sample(pool, seeds)
    t = time.perf_counter()
    p.call("val", "fibo", "viz.neighbourhood", seed=sample[0], overlays=["findings"])
    setup["warmup_first_call_s"] = round(time.perf_counter() - t, 2)   # ICV checks, once
    rows = []
    configs = [("default (hops 2, hub 25)", dict(hops=2, hub_limit=25), (40, 100))] + \
              [("reach (hops 8, no hub guard)", dict(hops=8, hub_limit=10 ** 6), CAPS)]
    for label, kw, caps in configs:
        for cap in caps:
            ms, nodes, edges, size = [], [], [], []
            for s in sample:
                t = time.perf_counter()
                v = p.call("val", "fibo", "viz.neighbourhood", seed=s, cap=cap,
                           overlays=["findings"], **kw)
                ms.append((time.perf_counter() - t) * 1000)
                nodes.append(v["sip"]["stats"]["nodes"])
                edges.append(v["sip"]["stats"]["edges"])
                size.append(len(json.dumps(v)))
            rows.append({"config": label, "cap": cap, "seeds": len(sample),
                         "ms_median": round(statistics.median(ms), 1),
                         "ms_p95": round(_p(ms, 0.95), 1),
                         "nodes_median": statistics.median(nodes), "nodes_max": max(nodes),
                         "edges_median": statistics.median(edges),
                         "payload_kb_median": round(statistics.median(size) / 1024, 1)})
    out = {"setup": setup, "rows": rows,
           "note": "the first viz call per revision runs the ICV checks once (cached); it is "
                   "timed separately as warmup_first_call_s and excluded from the rows"}
    return out


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def browser(seed: str | None = None, caps=CAPS, synth=(2000, 5000, 10000),
            timeout: float = 600) -> dict:
    exe = next((b for b in BROWSERS if Path(b).exists()), None) or shutil.which("chrome")
    if not exe:
        raise RuntimeError("no Chrome or Edge found for the headless browser benchmark")
    import uvicorn
    from .server import make_app
    p, _ = fibo_platform()
    app = make_app(platform=p)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    while not server.started:
        time.sleep(0.1)
    ix = __import__("ontoviz.sip_ops", fromlist=["bundle"]).bundle(p.projects["fibo"])["index"]
    seed = seed or max(ix.nodes, key=lambda n: len(ix.adj.get(n, ())))   # the biggest hub
    url = (f"http://127.0.0.1:{port}/viz/bench?project=fibo&seed={seed}"
           f"&caps={','.join(map(str, caps))}&synth={','.join(map(str, synth))}")
    profile = tempfile.mkdtemp(prefix="ontoviz-bench-")
    proc = subprocess.Popen([exe, "--headless=new", f"--user-data-dir={profile}",
                             "--window-size=1440,900", "--enable-precise-memory-info",
                             "--disable-background-timer-throttling",
                             "--disable-renderer-backgrounding", url],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not app.state.bench_event.wait(timeout):
            raise TimeoutError("browser benchmark did not finish")
    finally:
        proc.kill()
        server.should_exit = True
        th.join(5)
        shutil.rmtree(profile, ignore_errors=True)
    rows = [r for r in app.state.bench if "scene" in r]
    meta = next((r for r in app.state.bench if r.get("done")), {})
    errors = [r for r in app.state.bench if "error" in r]
    return {"browser": Path(exe).name, "userAgent": meta.get("userAgent"), "seed": seed,
            "rows": rows, "errors": errors,
            "note": "headless, software rendering (no GPU flag), one machine; "
                    "fps is capped by the display refresh (60)"}


def browser_repeated(n: int = 3) -> dict:
    """Run the browser benchmark n times (fresh browser each); median per scene and field."""
    runs = [browser() for _ in range(n)]
    scenes = [r["scene"] for r in runs[0]["rows"]]
    rows = []
    for sc in scenes:
        rs = [r for run in runs for r in run["rows"] if r["scene"] == sc]
        row = {"scene": sc, "runs": len(rs)}
        for k, v in rs[0].items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                vals = [r[k] for r in rs if r.get(k) is not None]
                row[k] = round(statistics.median(vals), 1) if vals else None
                if k in ("fpsMean", "firstPaintMs"):
                    row[k + "Range"] = [min(vals), max(vals)] if vals else None
            elif k not in row:
                row[k] = v
        rows.append(row)
    return {**{k: runs[0][k] for k in ("browser", "userAgent", "seed", "note")},
            "repeats": n, "rows": rows, "errors": [e for r in runs for e in r["errors"]],
            "raw": [r["rows"] for r in runs]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("extract", "browser"))
    ap.add_argument("--repeat", type=int, default=3, help="browser runs (median reported)")
    a = ap.parse_args()
    _paths.ARTIFACTS.mkdir(exist_ok=True)
    res = extract() if a.what == "extract" else browser_repeated(a.repeat)
    path = _paths.ARTIFACTS / f"bench_{a.what}.json"
    path.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
