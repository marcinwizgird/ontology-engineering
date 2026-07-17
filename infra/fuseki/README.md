# Local Apache Jena Fuseki (Docker)

A single-node Fuseki + TDB2 triplestore for local development: somewhere to load
this repo's ontologies and run SPARQL against them without touching a cluster.

The dataset name (`ontology`) and the endpoint names match the GKE assembler in
[`../../architecture/technical architecture/deploy/fuseki/config-tdb2.ttl`](../../architecture/technical%20architecture/deploy/fuseki/config-tdb2.ttl),
so a query URL that works here works there. This stack is **not** a model of that
deployment — see [Differences from the cluster](#differences-from-the-cluster).

## Requirements

Docker Desktop (or any Docker engine with Compose v2). Everything else — Java,
Jena, Fuseki — is in the image.

## Start

```powershell
cd "infra/fuseki"
docker compose up -d
```

First start pulls the image and initialises an empty TDB2 database; give it ~20s.
Check it is healthy:

```powershell
docker compose ps
curl.exe http://localhost:3030/$/ping
```

Then open **<http://localhost:3030/>** — user `admin`, password `admin` (or
whatever you set in `.env`).

Optional configuration lives in `.env`:

```powershell
Copy-Item .env.example .env
```

| Variable | Default | Purpose |
|---|---|---|
| `FUSEKI_PORT` | `3030` | Host port (bound to `127.0.0.1` only) |
| `FUSEKI_ADMIN_PASSWORD` | `admin` | Password for the UI and `/$/*` endpoints |
| `FUSEKI_JVM_ARGS` | `-Xmx2g` | JVM heap; raise to `-Xmx4g`+ before large loads |

## Load the repo's ontologies

With the stack running:

```powershell
.\scripts\load.ps1
```

That loads the Ontology Enricher's `data/`, `mappings/`, `fibo/` and `output/`
files, each into its own named graph such as
`urn:graph:src/Ontology%20Enricher/output/hbim_enriched.ttl`. Uploads use HTTP
`PUT`, so re-running the script refreshes graphs instead of duplicating triples.

That default set currently resolves to 10 files, which includes
`protege_reasoning_ready` in **both** `.ttl` and `.rdf` — the same ontology, so it
lands in two graphs and its triples are counted twice under
`unionDefaultGraph`. Harmless, but pass `-Path` explicitly if that skews a count.

```powershell
.\scripts\load.ps1 -Clear                                  # wipe, then reload
.\scripts\load.ps1 -Path "..\..\src\Ontology Enricher\output\hbim_enriched.ttl"
.\scripts\load.ps1 -Path "..\..\Ontology Repository\FIBO\fibo\FND"   # one FIBO module
```

`Get-Help .\scripts\load.ps1 -Full` documents the rest. The bash equivalent for a
single file:

```bash
curl -u admin:admin -X PUT -H 'Content-Type: text/turtle' \
  --data-binary @path/to/file.ttl \
  'http://localhost:3030/ontology/data?graph=urn:graph:my-file.ttl'
```

Loading **all** of FIBO (thousands of files) over HTTP is slow and wants a bigger
heap. Prefer loading only the modules you need.

## Query

The dataset sets `unionDefaultGraph`, so a query with no `GRAPH` clause sees
every loaded file at once — while `GRAPH ?g { ... }` still tells you which file a
triple came from.

```powershell
curl.exe -u admin:admin http://localhost:3030/ontology/sparql `
  --data-urlencode "query=SELECT ?g (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } } GROUP BY ?g" `
  -H "Accept: text/csv"
```

| Endpoint | URL |
|---|---|
| Query | `http://localhost:3030/ontology/sparql` (alias `/query`) |
| Update | `http://localhost:3030/ontology/update` |
| Graph Store (read/write) | `http://localhost:3030/ontology/data` |
| Graph Store (read-only) | `http://localhost:3030/ontology/get` |

From Python, point `SPARQLWrapper`/`rdflib` at the query endpoint above.

## Stop, reset, upgrade

```powershell
docker compose down          # stop; data survives in the 'fuseki-base' volume
docker compose down -v       # stop and DELETE the database
docker compose logs -f fuseki
```

The database lives in the named volume `ontology-fuseki_fuseki-base`, not in the
repo, so nothing here ends up in git or OneDrive. `down -v` is the reset button
when a load goes wrong.

To change the version, edit the `image:` pin in `docker-compose.yml`. TDB2 data
survives Fuseki upgrades within a major version; across majors, reset the volume
and reload.

## Text search (optional)

`config/optional/ontology-text.ttl` adds the Lucene index that the cluster config
uses. It is off by default to keep the default start path minimal. The file's
header comments explain how to switch to it — the index only covers data written
*after* it is enabled, so reload afterwards.

## Configuration

`config/ontology.ttl` is mounted read-only at
`/fuseki/configuration/ontology.ttl`, where Fuseki reads it at startup. Edit it,
then `docker compose restart fuseki` (or `up -d` after changing the mount).
Because the file is the source of truth in git, the server is not allowed to
rewrite it — so **creating a dataset through the web UI will not persist**. Add
datasets by editing the assembler instead.

## Differences from the cluster

Deliberate, and the reason this is dev-only:

- **No auth split.** Update and Graph Store writes are anonymous; prod restricts
  them by role. Mitigated by binding the port to `127.0.0.1` — do not publish it
  on `0.0.0.0` with these defaults.
- **No query timeout.** Prod bounds queries at 30s/60s; local exploration may run
  as long as it likes.
- **No Lucene index** unless you opt in (above).
- **Different image.** This uses the community `stain/jena-fuseki` image; prod
  builds its own from the Apache distribution. Apache publishes no official
  image, only a Dockerfile toolkit.
- **Sizing.** 2g heap and a Docker volume, versus a 16Gi pod on an SSD PVC.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `port is already allocated` | Something else holds 3030 (another Fuseki?). Set `FUSEKI_PORT` in `.env`. |
| Dataset `/ontology` missing after start | Assembler failed to parse. `docker compose logs fuseki` shows the Riot parse error and line. |
| Container is `unhealthy` | Server still starting, or the JVM died — check `logs`. `-Xmx` above what Docker Desktop grants the VM kills it at boot. |
| `load.ps1` says Fuseki is not answering | Stack not up, or `FUSEKI_PORT` in `.env` disagrees with the running container. |
| A file loads as 0 triples | Content type is guessed from the extension; a `.rdf` file that actually holds Turtle will parse to nothing. |
| Dataset created in the UI vanishes on restart | Expected — see [Configuration](#configuration). |
