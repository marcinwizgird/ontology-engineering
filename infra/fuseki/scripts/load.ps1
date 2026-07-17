#Requires -Version 5.1
<#
.SYNOPSIS
    Load RDF files from this repository into the local Fuseki 'ontology' dataset.

.DESCRIPTION
    Uploads each file into its own named graph over the SPARQL Graph Store
    Protocol, using HTTP PUT so re-running replaces a graph rather than
    duplicating triples. The dataset has unionDefaultGraph enabled, so an
    unqualified query sees the union of everything loaded.

    Graph URIs are derived from the repo-relative path, e.g.
      urn:graph:src/Ontology%20Enricher/data/hbim_business_assets.ttl

    Requires the stack to be running: docker compose up -d

.PARAMETER Path
    Files or directories to load (directories are searched recursively).
    Defaults to the Ontology Enricher's data, mappings, fibo and output folders.

.PARAMETER Clear
    Drop every graph in the dataset before loading.

.EXAMPLE
    .\load.ps1
    Load the default Ontology Enricher file set.

.EXAMPLE
    .\load.ps1 -Clear
    Wipe the dataset, then reload it from scratch.

.EXAMPLE
    .\load.ps1 -Path "..\..\..\src\Ontology Enricher\output\hbim_enriched.ttl"
    Load a single file.

.EXAMPLE
    .\load.ps1 -Path "..\..\..\Ontology Repository\FIBO\fibo\FND"
    Load one FIBO module. Loading all of FIBO this way takes a long time;
    raise FUSEKI_JVM_ARGS first.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string[]]$Path,

    [string]$BaseUrl,
    [string]$Dataset = "ontology",
    [string]$User = "admin",
    [string]$Password,
    [switch]$Clear
)

$ErrorActionPreference = "Stop"

$repoRoot  = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$composeDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# --- defaults from .env (falling back to the same values docker-compose.yml uses)

$envVars = @{}
$envFile = Join-Path $composeDir ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
            $envVars[$Matches[1]] = $Matches[2].Trim('"').Trim("'")
        }
    }
}

if (-not $BaseUrl) {
    $port = "3030"
    if ($envVars.ContainsKey("FUSEKI_PORT") -and $envVars["FUSEKI_PORT"]) { $port = $envVars["FUSEKI_PORT"] }
    $BaseUrl = "http://localhost:$port"
}
$BaseUrl = $BaseUrl.TrimEnd("/")

if (-not $Password) {
    $Password = "admin"
    if ($envVars.ContainsKey("FUSEKI_ADMIN_PASSWORD") -and $envVars["FUSEKI_ADMIN_PASSWORD"]) {
        $Password = $envVars["FUSEKI_ADMIN_PASSWORD"]
    }
}

$auth    = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("${User}:${Password}"))
$headers = @{ Authorization = "Basic $auth" }

# --- which files

$contentTypes = @{
    ".ttl"    = "text/turtle"
    ".turtle" = "text/turtle"
    ".n3"     = "text/n3"
    ".nt"     = "application/n-triples"
    ".rdf"    = "application/rdf+xml"
    ".owl"    = "application/rdf+xml"
    ".xml"    = "application/rdf+xml"
    ".jsonld" = "application/ld+json"
    ".trig"   = "application/trig"
    ".nq"     = "application/n-quads"
}

if (-not $Path) {
    $Path = @(
        "src\Ontology Enricher\data",
        "src\Ontology Enricher\mappings",
        "src\Ontology Enricher\fibo",
        "src\Ontology Enricher\output"
    ) | ForEach-Object { Join-Path $repoRoot $_ } | Where-Object { Test-Path $_ }
}

$files = @()
foreach ($p in $Path) {
    if (-not (Test-Path $p)) {
        Write-Warning "Skipping missing path: $p"
        continue
    }
    $item = Get-Item -LiteralPath $p
    if ($item.PSIsContainer) {
        $files += Get-ChildItem -LiteralPath $item.FullName -Recurse -File |
                  Where-Object { $contentTypes.ContainsKey($_.Extension.ToLower()) }
    }
    else {
        $files += $item
    }
}
$files = $files | Sort-Object FullName -Unique

if (-not $files) {
    throw "No RDF files found. Looked in: $($Path -join '; ')"
}

# --- check the server is up before doing anything destructive

try {
    Invoke-RestMethod -Uri "$BaseUrl/`$/ping" -Headers $headers -TimeoutSec 10 | Out-Null
}
catch {
    throw "Fuseki is not answering at $BaseUrl ($($_.Exception.Message)). Start it with: docker compose up -d"
}

if ($Clear) {
    Write-Host "Clearing dataset '$Dataset'..." -ForegroundColor Yellow
    Invoke-RestMethod -Method Post -Uri "$BaseUrl/$Dataset/update" -Headers $headers `
        -ContentType "application/sparql-update" -Body "CLEAR ALL" | Out-Null
}

# --- load

Write-Host "Loading $($files.Count) file(s) into $BaseUrl/$Dataset" -ForegroundColor Cyan

$ok = 0
$failed = @()
foreach ($file in $files) {
    $rel = $file.FullName
    if ($rel.StartsWith($repoRoot, [StringComparison]::OrdinalIgnoreCase)) {
        $rel = $rel.Substring($repoRoot.Length).TrimStart("\", "/")
    }
    $rel   = $rel.Replace("\", "/")
    $graph = "urn:graph:" + [uri]::EscapeDataString($rel).Replace("%2F", "/")
    $ct    = $contentTypes[$file.Extension.ToLower()]
    $uri   = "$BaseUrl/$Dataset/data?graph=" + [uri]::EscapeDataString($graph)

    try {
        Invoke-RestMethod -Method Put -Uri $uri -Headers $headers -ContentType $ct `
            -InFile $file.FullName | Out-Null
        Write-Host ("  OK   {0}" -f $rel) -ForegroundColor Green
        $ok++
    }
    catch {
        Write-Host ("  FAIL {0} - {1}" -f $rel, $_.Exception.Message) -ForegroundColor Red
        $failed += $rel
    }
}

# --- report

$summary = "Loaded $ok/$($files.Count) file(s)."
try {
    $queryHeaders = @{ Authorization = "Basic $auth"; Accept = "application/sparql-results+json" }
    $count = Invoke-RestMethod -Uri "$BaseUrl/$Dataset/sparql" -Method Post -Headers $queryHeaders `
        -ContentType "application/sparql-query" `
        -Body "SELECT (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } }"
    $summary += " Dataset now holds $($count.results.bindings[0].n.value) triples."
}
catch {
    Write-Verbose "Could not read triple count: $($_.Exception.Message)"
}

Write-Host $summary -ForegroundColor Cyan
Write-Host "Query it at $BaseUrl/dataset.html?tab=query&ds=/$Dataset"

if ($failed) {
    Write-Host "Failed files:" -ForegroundColor Red
    $failed | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    exit 1
}
