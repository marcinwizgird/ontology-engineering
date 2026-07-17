"""Uploading RDF files into Fuseki over the Graph Store Protocol.

Two strategies over the same operation (PUT one file per named graph, so re-runs replace
rather than duplicate):

* Uploader       -- sequential, or a thread pool. Uses the shared FusekiClient.
* AsyncUploader  -- asyncio + aiohttp, bounded concurrency. Reuses the client's settings
                    and RDF helpers but manages its own aiohttp session, because aiohttp
                    cannot share requests' Session.

Why bounded concurrency: TDB2 serialises writers, so the server-side write is never
parallel; what overlaps is disk reads, TCP, and parsing. A handful of connections
captures that; a flood just contends on the write lock.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import aiohttp

from .fuseki import FusekiClient, FusekiError
from .rdf import content_type_for, graph_uri, iter_rdf_files, repo_relative


@dataclass
class UploadResult:
    """Outcome of an upload batch."""

    total: int
    succeeded: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)
    elapsed: float = 0.0

    @property
    def ok(self) -> int:
        return len(self.succeeded)

    def __str__(self) -> str:
        s = f"uploaded {self.ok}/{self.total} in {self.elapsed:.1f}s"
        if self.failed:
            s += f"; {len(self.failed)} failed"
        return s


class Uploader:
    """Sequential / thread-pool uploader built on the shared FusekiClient."""

    def __init__(self, client: FusekiClient | None = None):
        self.client = client or FusekiClient()

    def upload_file(self, path: Path, timeout: int = 300) -> tuple[Path, str | None]:
        """PUT one file into its named graph. Returns (path, error|None)."""
        try:
            self.client.put_file(path, timeout=timeout)
            return path, None
        except (FusekiError, OSError, ValueError) as exc:
            return path, str(exc)[:200]

    def upload_paths(self, paths: list[Path], *, clear: bool = False,
                     workers: int = 1, timeout: int = 300,
                     progress: bool = False) -> UploadResult:
        """Upload every RDF file under `paths`. `workers > 1` uses a thread pool."""
        files = iter_rdf_files([Path(p) for p in paths])
        result = UploadResult(total=len(files))
        if not files:
            return result

        if clear:
            self.client.clear_all()

        started = time.monotonic()
        done = 0

        def record(path: Path, error: str | None) -> None:
            nonlocal done
            done += 1
            if error:
                result.failed.append((path, error))
            else:
                result.succeeded.append(path)
            if progress:
                tag = "FAIL" if error else "ok"
                line = f"  [{done}/{len(files)}] {tag:4s} {repo_relative(path)}"
                print(line + (f"\n        {error}" if error else ""))

        if workers > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(self.upload_file, f, timeout) for f in files]
                for fut in concurrent.futures.as_completed(futures):
                    record(*fut.result())
        else:
            for f in files:
                record(*self.upload_file(f, timeout))

        result.elapsed = time.monotonic() - started
        return result


class AsyncUploader:
    """Concurrent uploader using asyncio + aiohttp, bounded by a semaphore."""

    def __init__(self, client: FusekiClient | None = None):
        self.client = client or FusekiClient()

    async def _put_one(self, session: aiohttp.ClientSession, sem: asyncio.Semaphore,
                       path: Path, timeout: aiohttp.ClientTimeout) -> tuple[Path, str | None]:
        ctype = content_type_for(path)
        if ctype is None:
            return path, f"not an RDF file: {path.name}"
        uri = f"{self.client.settings.gsp_endpoint}?graph={quote(graph_uri(path), safe='')}"
        async with sem:                                   # the semaphore caps in-flight PUTs
            try:
                data = path.read_bytes()
                async with session.put(uri, data=data,
                                       headers={"Content-Type": ctype}, timeout=timeout) as resp:
                    if resp.status >= 400:
                        body = (await resp.text()).strip().splitlines()
                        return path, f"HTTP {resp.status}: {(body[0] if body else '')[:160]}"
                    return path, None
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
                return path, f"{type(exc).__name__}: {exc}"[:160]

    async def upload_paths(self, paths: list[Path], *, concurrency: int = 8,
                           timeout_seconds: int = 300, progress: bool = False) -> UploadResult:
        files = iter_rdf_files([Path(p) for p in paths])
        result = UploadResult(total=len(files))
        if not files:
            return result

        sem = asyncio.Semaphore(concurrency)
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        s = self.client.settings
        auth = aiohttp.BasicAuth(s.user, s.password)
        connector = aiohttp.TCPConnector(limit=concurrency)
        started = time.monotonic()
        done = 0

        async with aiohttp.ClientSession(auth=auth, connector=connector) as session:
            tasks = [asyncio.create_task(self._put_one(session, sem, f, timeout)) for f in files]
            for coro in asyncio.as_completed(tasks):
                path, error = await coro
                done += 1
                if error:
                    result.failed.append((path, error))
                else:
                    result.succeeded.append(path)
                if progress:
                    tag = "FAIL" if error else "ok"
                    print(f"  [{done}/{len(files)}] {tag:4s} {path.name}"
                          + (f"\n        {error}" if error else ""))

        result.elapsed = time.monotonic() - started
        return result
