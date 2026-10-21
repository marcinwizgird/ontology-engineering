"""Serve the viewer on SIP's own API.

The app *is* ``semantic_intelligence.api.app.create_app`` (the workbench's server), with
the ``viz.*`` operations registered and the static viewer mounted under ``/viz``. The
page talks to ``POST /projects/{p}/ops/{op}`` with the ``X-SIP-Principal`` header,
exactly as ``workbench.html`` does, so Phase 1 is a move, not a rewrite.

Run (from this PoC's folder)::

    python -m ontoviz.server              # fleet demo on http://127.0.0.1:8765/viz
    python -m ontoviz.server --fibo       # plus the FIBO project (~20 s to load)
"""

from __future__ import annotations

import argparse
import json
import threading
import time

from fastapi import Body
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import _paths
from . import demo
from semantic_intelligence.api.app import create_app


def make_app(fibo: bool = False, platform=None):
    p = platform or demo.build(fibo=fibo)
    app = create_app(p)
    app.state.bench = []
    app.state.bench_event = threading.Event()

    @app.get("/viz", include_in_schema=False)
    def viewer():
        return FileResponse(_paths.WEB / "index.html")

    @app.get("/viz/bench", include_in_schema=False)
    def bench_page():
        return FileResponse(_paths.WEB / "bench.html")

    @app.post("/viz/bench-result", include_in_schema=False)
    def bench_result(body: dict = Body(...)):
        app.state.bench.append(body)
        if body.get("done"):
            app.state.bench_event.set()
        return {"ok": True}

    app.mount("/viz/static", StaticFiles(directory=_paths.WEB), name="viz-static")

    # The viewer is the PoC's landing page; the workbench stays at /ui.
    app.routes[:] = [r for r in app.routes if getattr(r, "path", None) != "/"]

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/viz")

    return app


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--fibo", action="store_true", help="also load the FIBO project")
    a = ap.parse_args()
    import uvicorn
    t = time.perf_counter()
    app = make_app(fibo=a.fibo)
    print(json.dumps({"ready_s": round(time.perf_counter() - t, 1),
                      "projects": sorted(app.state.platform.projects),
                      "url": f"http://{a.host}:{a.port}/viz"}))
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
