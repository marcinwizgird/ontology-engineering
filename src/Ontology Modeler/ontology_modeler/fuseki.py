"""FusekiClient -- the single HTTP client every Fuseki-facing component shares.

Before this, the uploader, the differ, and the structure queries each built their own
requests.Session, auth, and endpoint strings. They now all take one FusekiClient, so
connection handling, the UTF-8 fetch fix, and error reporting live in exactly one place.

Surface:
    ping()                          liveness
    select(sparql) -> list[dict]    SELECT, values unwrapped to strings
    select_df(sparql) -> DataFrame  same, as a pandas DataFrame
    ask(sparql) -> bool             ASK
    update(sparql)                  SPARQL Update (one transaction per call)
    get_graph(uri) -> rdflib.Graph  GSP GET (UTF-8 correct; absent graph -> empty)
    put_graph(uri, data, ctype)     GSP PUT (replace)
    put_file(path)                  PUT a file with graph URI + content type derived
    delete_graph(uri)               GSP DELETE
    count_triples() -> int          triples across all named graphs
"""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

import requests
from rdflib import Graph

from .config import FusekiSettings
from .rdf import content_type_for, graph_uri

# Prepended to SELECT/ASK queries so callers can use these prefixes without repeating
# them. Update/GSP bodies are passed through untouched.
PREFIXES = """
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
"""


class FusekiError(RuntimeError):
    """An HTTP error from Fuseki, carrying the status and the server's message."""

    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"HTTP {status}: {message}")


class FusekiClient:
    """A thin, shared wrapper over one Fuseki dataset's HTTP endpoints."""

    def __init__(self, settings: FusekiSettings | None = None, prefixes: str = PREFIXES):
        self.settings = settings or FusekiSettings.from_env()
        self.prefixes = prefixes
        self.session = requests.Session()
        self.session.auth = (self.settings.user, self.settings.password)

    # -- liveness ------------------------------------------------------------ #

    def ping(self) -> str:
        """Return the server time, or raise if Fuseki is not answering."""
        resp = self.session.get(self.settings.ping_endpoint, timeout=10)
        resp.raise_for_status()
        return resp.text.strip()

    def is_up(self) -> bool:
        try:
            self.ping()
            return True
        except requests.RequestException:
            return False

    # -- reads --------------------------------------------------------------- #

    def select(self, sparql: str, timeout: int = 300) -> list[dict[str, str]]:
        """Run a SELECT; return one dict per row with values unwrapped to strings."""
        resp = self.session.post(
            self.settings.sparql_endpoint,
            data=(self.prefixes + sparql).encode("utf-8"),
            headers={"Content-Type": "application/sparql-query",
                     "Accept": "application/sparql-results+json"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        cols = data["head"]["vars"]
        return [{c: b[c]["value"] if c in b else None for c in cols}
                for b in data["results"]["bindings"]]

    def select_df(self, sparql: str, timeout: int = 300):
        """SELECT as a pandas DataFrame (columns preserved even when empty)."""
        import pandas as pd
        resp = self.session.post(
            self.settings.sparql_endpoint,
            data=(self.prefixes + sparql).encode("utf-8"),
            headers={"Content-Type": "application/sparql-query",
                     "Accept": "application/sparql-results+json"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        cols = data["head"]["vars"]
        rows = [{c: b[c]["value"] if c in b else None for c in cols}
                for b in data["results"]["bindings"]]
        return pd.DataFrame(rows, columns=cols)

    def ask(self, sparql: str, timeout: int = 60) -> bool:
        resp = self.session.post(
            self.settings.sparql_endpoint,
            data=(self.prefixes + sparql).encode("utf-8"),
            headers={"Content-Type": "application/sparql-query",
                     "Accept": "application/sparql-results+json"},
            timeout=timeout,
        )
        resp.raise_for_status()
        return bool(resp.json()["boolean"])

    def count_triples(self) -> int:
        rows = self.select("SELECT (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } }")
        return int(rows[0]["n"])

    # -- writes -------------------------------------------------------------- #

    def update(self, sparql: str, timeout: int = 300) -> None:
        """Run a SPARQL Update; the whole string is one Fuseki transaction."""
        resp = self.session.post(
            self.settings.update_endpoint,
            data=sparql.encode("utf-8"),
            headers={"Content-Type": "application/sparql-update"},
            timeout=timeout,
        )
        if resp.status_code >= 400:
            raise FusekiError(resp.status_code, _first_line(resp.text))

    def clear_all(self) -> None:
        self.update("CLEAR ALL")

    # -- graph store protocol ------------------------------------------------ #

    def get_graph(self, uri: str, timeout: int = 120) -> Graph:
        """GET one named graph as an rdflib.Graph. Absent graph (404) -> empty graph."""
        endpoint = f"{self.settings.gsp_endpoint}?graph={quote(uri, safe='')}"
        resp = self.session.get(endpoint, headers={"Accept": "text/turtle"}, timeout=timeout)
        g = Graph()
        if resp.status_code == 404:
            return g
        resp.raise_for_status()
        # Parse from raw bytes, not resp.text: for text/turtle with no charset in the
        # response header, requests falls back to ISO-8859-1 and mangles every multibyte
        # UTF-8 character. Turtle is UTF-8 by spec.
        g.parse(data=resp.content, format="turtle")
        return g

    def put_graph(self, uri: str, data: bytes | BinaryIO | Graph,
                  content_type: str = "text/turtle", timeout: int = 300) -> None:
        """PUT (replace) a named graph. `data` may be bytes, a file handle, or a Graph."""
        if isinstance(data, Graph):
            body: bytes | BinaryIO = data.serialize(format="turtle").encode("utf-8")
        else:
            body = data
        endpoint = f"{self.settings.gsp_endpoint}?graph={quote(uri, safe='')}"
        resp = self.session.put(endpoint, data=body,
                                headers={"Content-Type": content_type}, timeout=timeout)
        if resp.status_code >= 400:
            raise FusekiError(resp.status_code, _first_line(resp.text))

    def put_file(self, path: Path, timeout: int = 300) -> str:
        """PUT a file into its derived named graph. Returns the graph URI. Raises on error."""
        ctype = content_type_for(path)
        if ctype is None:
            raise ValueError(f"not an RDF file (unknown extension): {path}")
        uri = graph_uri(path)
        with path.open("rb") as fh:
            self.put_graph(uri, fh, content_type=ctype, timeout=timeout)
        return uri

    def delete_graph(self, uri: str) -> None:
        self.update(f"DROP GRAPH <{uri}>")


def _first_line(text: str) -> str:
    lines = text.strip().splitlines()
    return lines[0][:200] if lines else ""
