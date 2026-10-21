# Graph and ontology visualization libraries and tools for SIP (Python backend + browser front end)

Research date: 2026-10-20. Scope: JS rendering/layout libraries, Python-side helpers, ontology-specific tools, and which ones can render Cypher (FalkorDB) or SPARQL CONSTRUCT results directly. Environment constraints: Windows, no Java, no native cairo, and a dependency-light core (stdlib, rdflib, owlrl, networkx). JS loaded from a CDN or vendored files is preferred.

**Method and evidence levels.** Stars, licence SPDX IDs and last-push dates came from the GitHub REST API (`api.github.com/repos/<repo>`), queried live on 2026-10-20. Latest versions, release dates, licences and weekly downloads came from the npm registry and the npm downloads API, and Python versions from the PyPI JSON API. Bundle sizes came from the Bundlephobia API (minified and gzipped), and UMD file sizes from fetching the file on jsDelivr. Pricing and features came from web pages, cited inline.

Claims tagged **[K]** come from my prior knowledge of the project's official docs and were *not* re-fetched in this session. The cited URL is the canonical doc page, and these claims should be spot-checked before they are relied on. Vendor-only performance claims are tagged **[vendor claim]**.

---

## 1. JS libraries: licence, maintenance, rendering, layouts, scale, interaction, editing, bundle, CDN/offline

### Takeaway
Cytoscape.js (MIT, 11.2k stars, v3.34.4 released 2026-10-15, ~11M weekly downloads) is the best all-round fit for an ontology component. It is the only mainstream free library that has true compound (nested) nodes, has a plug-in layout ecosystem (dagre, ELK, fCoSE) and expand-collapse, works from a CDN with no build step, and is easy to feed from Python as JSON. For large instance graphs, sigma.js v4 + graphology (WebGL) or cosmos.gl (GPU) are the scale options. Commercial yFiles, Ogma and GoJS add polish and layouts but cost thousands of dollars (GoJS is from $3,995; yFiles and Ogma are quote-only).

### Comparison table (numbers measured 2026-10-20)

| Library | Licence | Latest release (npm) | GitHub stars / last push | npm weekly DL | Rendering | Hierarchical / layered | Compound / nested | Practical scale | Interaction / editing | Bundle (min / gz) | No-build CDN + offline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Cytoscape.js** | MIT | 3.34.4 (2026-10-15) | 11,246 / 2026-10-15 | 11.1M | Canvas; experimental WebGL since 3.31 | `breadthfirst` built in; dagre/ELK via extensions | **Yes, native compound nodes** | Low thousands of elements on Canvas; WebGL aims higher (no published benchmark) | Selection, styling via CSS-like stylesheet, filtering via selectors, expand-collapse ext, edgehandles ext; editing via API | 425 / 134 KB | Yes (UMD `dist/cytoscape.min.js`, 436 KB); vendor the file for offline |
| cytoscape-elk | MIT | 2.3.0 (2024-11-26) | 56 / 2026-04-10 | 14k | (layout adapter) | ELK layered, mrtree, etc. | ELK respects compounds | Bound by ELK cost | n/a | pulls elkjs (1,417 / 423 KB) | Yes with elkjs UMD |
| cytoscape-dagre | MIT | 4.0.1 (2026-08-28) | 287 / 2026-08-28 | 196k | (layout adapter) | dagre layered DAG | Limited | Hundreds to low thousands | n/a | small + dagre | Yes |
| cytoscape-fcose | MIT | 2.2.0 (2023-01-17) | 186 / 2026-04-17 | 10.3M | (layout adapter) | No (force-directed) | **Yes, compound-aware with constraints** | Thousands | n/a | 119 KB min (Bundlephobia gz figure of 1 KB looks like a measurement artefact) | Yes (needs layout-base + cose-base UMDs) |
| cytoscape-expand-collapse | MIT | 4.1.1 (2024-08-28) | 140 / 2024-11-27 | 12k | (UI ext) | n/a | Collapses compounds and edges | n/a | expand/collapse of compound nodes and edge bundles | n/a | Yes |
| **sigma.js** (+ graphology) | MIT | sigma 4.0.3 (2026-10-15); graphology 0.26.0 (2025-01-26) | 12,196 / 2026-10-16; graphology 1,763 / 2026-09-02 | 272k; graphology 954k | **WebGL** | Not built in (ForceAtlas2, noverlap, circular via graphology-layout-*) | No | Tens of thousands of nodes / 100k+ edges [K: sigma docs] | Hover, click, node reducers for filtering/highlight; no built-in editing | sigma 365 / 94 KB; graphology 65 / 13 KB | Yes (UMD builds on jsDelivr: sigma.min.js 392 KB, graphology.umd.min.js 74 KB) |
| **d3-force / d3-hierarchy** | ISC | d3-force 3.0.0 (2021-06-05); d3-hierarchy 3.1.2 (2022-04-02) | 2,009 / 2023-12-30; 1,276 / 2025-04-08 | 15.3M / 15.9M | Whatever you draw (SVG or Canvas) | d3-hierarchy tree, cluster, partition, pack, treemap (trees only, not DAGs) | Pack/treemap nesting | SVG ~1-2k nodes; Canvas more | Everything hand-built | 15 / 6 KB and 14 / 6 KB | Yes (`d3` UMD); stable but rarely released |
| **elkjs** | EPL-2.0 OR GPL-3.0-or-later | 0.12.0 (2026-07-17) | 2,837 / 2026-10-19 | 7.5M | None (layout only) | **ELK Layered (Sugiyama), the strongest open layered layout**; mrtree, radial, force, stress | **Yes, hierarchical ports and compound graphs** | Hundreds to a few thousand nodes; runs in a Web Worker | n/a | 1,417 / 423 KB (`elk.bundled.js` 1.6 MB) | Yes (bundled UMD) |
| **dagre** (`@dagrejs/dagre`) | MIT | 3.1.1 (2026-08-08); old `dagre` 0.8.5 stuck at 2019 | 5,831 / 2026-08-08 | 3.1M (+1.6M legacy) | None (layout only) | Layered DAG (Sugiyama-style) | Basic clusters | Hundreds to low thousands | n/a | 46 / 15 KB | Yes (`dist/dagre.min.js` 49 KB) |
| dagre-d3 | MIT | 0.6.4 (2019-12-03) | 2,964 / 2024-03-13 | 50k | SVG via d3 | dagre | Clusters | Small | n/a | n/a | Yes, but **effectively unmaintained** |
| **vis-network** | Apache-2.0 OR MIT | 10.1.2 (2026-08-19) | 3,635 / 2026-10-20 | 453k | Canvas | `hierarchical` layout built in (direction, level separation) | "Clustering" (collapse to cluster node), not true nesting | Low thousands (physics slows beyond that) [K] | Built-in manipulation toolbar (add/edit/delete nodes and edges), physics, clustering, events | 404 / 116 KB | **Yes**: standalone UMD (652 KB) includes CSS; used by pyvis and the YASGUI graph plugin |
| **AntV G6 v5** | MIT | 5.1.1 (2026-05-08) | 12,339 / 2026-10-20 | 127k | Canvas (default) / SVG / WebGL renderers via AntV G | dagre, antv-dagre, indented/compact-box trees, ELK-like layered, radial, concentric, force, fruchterman, plus WASM/GPU layouts | **Yes, combos (nested groups) and tree collapse/expand** | Thousands; WebGL renderer for more [K] | Rich behaviours (drag, zoom, collapse-expand, lasso, create-edge), plugins (minimap, legend, toolbar) | 1,368 / 390 KB (UMD 1.38 MB) | Yes (`dist/g6.min.js`); docs mostly Chinese-first |
| **React Flow / xyflow** | MIT | @xyflow/react 12.12.0 (2026-09-24) | 38,727 / 2026-10-20 | 8.3M | **DOM/HTML + SVG edges** | None built in; examples use dagre/ELK | Sub-flows (parent/child nodes) | Hundreds to low thousands (DOM nodes) | Excellent node editing, custom React node components, handles | 183 / 59 KB (+ React) | Needs React + a build in practice; ESM-CDN possible but not idiomatic |
| **cosmos.gl** (formerly Cosmograph "cosmos") | MIT (`@cosmos.gl/graph`); Cosmograph app/lib `@cosmograph/cosmos` and `cosmograph` are **CC-BY-NC-4.0** | @cosmos.gl/graph 3.5.1 (2026-10-08) | cosmosgl/graph 1,300 / 2026-10-16 | 46k | **WebGL GPU** (force simulation on the GPU) | No | No | Hundreds of thousands to ~1M nodes [vendor claim] | Pan/zoom/select; no editing | 447 / 112 KB | Yes (ESM) |
| **ngraph** (ngraph.graph + ngraph.forcelayout, ngraph.pixel) | BSD-3-Clause (ngraph.graph), MIT (repo) | ngraph.graph 20.1.2 (2026-02-14) | 1,512 / 2026-06-23 | 257k | Bring your own; ngraph.pixel/VivaGraph WebGL | No | No | Large force layouts | Minimal | 4 / 2 KB (core) | Yes |
| **Ogma** (Linkurious, now part of Nuix) | Commercial | n/a (private registry) | closed | n/a | WebGL + Canvas | hierarchical, force, radial, concentric, grid [K] | Node grouping [K] | 100k+ elements [vendor claim] | Rich | n/a | Licensed bundle can be vendored |
| **yFiles for HTML** (yWorks) | Commercial, one-time purchase + optional maintenance | v3.x (docs reference 3.0.0.4) | closed | n/a | SVG + Canvas + WebGL | **Best-in-class hierarchic (layered), orthogonal, tree, organic layouts** [K] | **Yes, full group/folding support** [K] | 10k+ with WebGL [vendor claim] | Full editing (GraphEditorInputMode), undo, folding | large | Needs a licence file per domain to run |
| **GoJS** (Northwoods) | Commercial | 4.0.5 (2026-10-02) | 8,490 / 2026-10-02 (source-available) | 157k | Canvas (+ SVG export) | LayeredDigraphLayout, TreeLayout, Force, Circular, Grid | **Yes, Groups (nested, collapsible)** | Thousands with virtualization [K] | Full diagram editing, undo manager, templates | 997 / 271 KB (`go.js` 1.06 MB) | Yes (`release/go.js` on jsDelivr); unlicensed use shows a watermark [K] |

### Cited findings
- Cytoscape.js: MIT, 11,246 stars, pushed 2026-10-15; npm `cytoscape` 3.34.4 published 2026-10-15, 11.1M weekly downloads; 425 KB min / 134 KB gzipped — [GitHub](https://github.com/cytoscape/cytoscape.js), [npm](https://www.npmjs.com/package/cytoscape), [Bundlephobia](https://bundlephobia.com/package/cytoscape)
- Cytoscape.js added an experimental WebGL renderer in 3.31.0 (2025-01-13). It does not yet support every style (e.g. segment edges). The project says Canvas frame rates drop as networks grow, with ~15 FPS jerky, ~5 FPS unresponsive and ~1 FPS frozen — [Cytoscape blog: WebGL preview](https://blog.js.cytoscape.org/2025/01/13/webgl-preview/), [3.31.0 release](https://blog.js.cytoscape.org/2025/01/13/3.31.0-release/)
- Cytoscape.js compound nodes (via the `parent` data field), the `breadthfirst` layout, selector-based filtering and the stylesheet model — [K] [Cytoscape.js docs](https://js.cytoscape.org/)
- cytoscape-elk 2.3.0 (2024-11-26), cytoscape-dagre 4.0.1 (2026-08-28), cytoscape-fcose 2.2.0 (2023-01-17; repo pushed 2026-04-17), cytoscape-expand-collapse 4.1.1 (2024-08-28; repo last pushed 2024-11-27), all MIT — [npm cytoscape-elk](https://www.npmjs.com/package/cytoscape-elk), [npm cytoscape-dagre](https://www.npmjs.com/package/cytoscape-dagre), [npm cytoscape-fcose](https://www.npmjs.com/package/cytoscape-fcose), [npm cytoscape-expand-collapse](https://www.npmjs.com/package/cytoscape-expand-collapse)
- fCoSE supports compound graphs and placement constraints (fixed, alignment, relative) — [K] [cytoscape.js-fcose README](https://github.com/iVis-at-Bilkent/cytoscape.js-fcose)
- sigma 4.0.3 (2026-10-15), MIT, 12,196 stars; graphology 0.26.0 (2025-01-26), 954k weekly downloads; sigma 94 KB gzipped, graphology 13 KB gzipped — [GitHub sigma.js](https://github.com/jacomyal/sigma.js), [npm sigma](https://www.npmjs.com/package/sigma), [npm graphology](https://www.npmjs.com/package/graphology)
- elkjs 0.12.0 released 2026-07-17, dual-licensed EPL-2.0 OR GPL-3.0-or-later; 1.4 MB min / 423 KB gzipped — [GitHub releases](https://github.com/kieler/elkjs/releases), [npm elkjs](https://www.npmjs.com/package/elkjs)
- dagre is now published as `@dagrejs/dagre` 3.1.1 (2026-08-08, 3.1M/week). The legacy `dagre` package is frozen at 0.8.5 (2019), and `dagre-d3` is frozen at 0.6.4 (2019) with its repo last pushed 2024-03-13 — [npm @dagrejs/dagre](https://www.npmjs.com/package/@dagrejs/dagre), [npm dagre-d3](https://www.npmjs.com/package/dagre-d3)
- d3-force 3.0.0 (2021) and d3-hierarchy 3.1.2 (2022), ISC, ~15M weekly downloads each. Both are stable, with essentially no new releases — [npm d3-force](https://www.npmjs.com/package/d3-force), [npm d3-hierarchy](https://www.npmjs.com/package/d3-hierarchy)
- vis-network 10.1.2 (2026-08-19), licensed "Apache-2.0 OR MIT", 3,635 stars, pushed 2026-10-20, 453k/week; the standalone UMD is 652 KB — [npm vis-network](https://www.npmjs.com/package/vis-network), [GitHub](https://github.com/visjs/vis-network)
- AntV G6 5.1.1 (2026-05-08), MIT, 12,339 stars, 1.37 MB min / 390 KB gzipped — [npm @antv/g6](https://www.npmjs.com/package/@antv/g6), [GitHub](https://github.com/antvis/G6)
- G6 v5 combos, multiple renderers (Canvas/SVG/WebGL) and tree layouts — [K] [G6 docs](https://g6.antv.antgroup.com/en)
- React Flow (`@xyflow/react`) 12.12.0 (2026-09-24), MIT, 38,727 stars, 8.3M/week, 59 KB gzipped — [npm](https://www.npmjs.com/package/@xyflow/react), [GitHub](https://github.com/xyflow/xyflow)
- The cosmos GPU graph engine moved to the `cosmosgl/graph` repo (MIT, 1,300 stars), published as `@cosmos.gl/graph` 3.5.1 (2026-10-08). The older `@cosmograph/cosmos` 3.4.1 and the `cosmograph` 2.5.1 package are licensed **CC-BY-NC-4.0** (non-commercial) — [GitHub cosmosgl/graph](https://github.com/cosmosgl/graph), [npm @cosmos.gl/graph](https://www.npmjs.com/package/@cosmos.gl/graph), [npm @cosmograph/cosmos](https://www.npmjs.com/package/@cosmograph/cosmos), [npm cosmograph](https://www.npmjs.com/package/cosmograph)
- ngraph.graph 20.1.2 (2026-02-14), BSD-3-Clause; the ngraph repo was pushed 2026-06-23 — [npm](https://www.npmjs.com/package/ngraph.graph), [GitHub](https://github.com/anvaka/ngraph)
- GoJS 4.0.5 (2026-10-02), "SEE LICENSE IN license.html". Pricing: Individual $3,995, Team (up to 3 developers) $6,990, Group (up to 20) $11,950, Enterprise custom. There are no runtime royalties, and extra options (unlimited domains, up to 5 apps) cost $3,995 each. An older Northwoods page says Group covers up to 50 developers, which conflicts with the current page — [GoJS pricing](https://gojs.net/latest/pricing), [Northwoods sales](https://nwoods.com/sales/index.html)
- yFiles for HTML: one-time purchase with no subscription required, plus optional maintenance. Licence types: Single Developer (1 named developer, 1 domain), Project (1 application, up to 3 developers, 2 domains) and Site. No fixed prices are published (quote via the licence finder). EUR pricing applies in the eurozone and USD elsewhere. A valid licence file is required at runtime — [yFiles license types](https://www.yworks.com/products/yfiles-for-html/license-types), [yFiles pricing](https://yfiles.com/pricing), [yFiles licensing docs](https://docs.yworks.com/yfiles-html/dguide/licensing/)
- Ogma: no public price list. Directory listings show "free trial / contact vendor", and Linkurious is listed as part of Nuix — [Capterra Ogma](https://www.capterra.com/p/10011703/Ogma/)

### Inferences
- For a no-build static HTML page, Cytoscape.js, vis-network, sigma+graphology, dagre, elkjs (bundled) and G6 all ship UMD files on jsDelivr. Vendoring them into the repo (e.g. `sip/.../static/vendor/`) gives offline operation with no Node toolchain.
- elkjs is EPL-2.0/GPL dual-licensed, not MIT. Taking it under EPL-2.0 is weak-copyleft and file-level only, which is fine for an unmodified vendored file, but it should be noted in a licence inventory.
- Ontology class hierarchies are DAGs (multiple inheritance), not trees, so d3-hierarchy alone is inadequate. Layered layouts (dagre/ELK) are the right tool, and ELK Layered with compound support is the strongest open option.
- Avoid the CC-BY-NC Cosmograph packages in a product. Use the MIT `@cosmos.gl/graph` if GPU scale is needed.
- React Flow is excellent for editing small diagrams (e.g. a SHACL shape or class-diagram editor), but it requires a React build, which conflicts with the no-build goal.

### Gaps
- No independent, like-for-like benchmark of Cytoscape Canvas vs WebGL vs sigma vs G6 at fixed sizes was found. The scale figures above are rough or vendor-sourced.
- No public prices for yFiles or Ogma. The exact current Ogma licence terms (per-developer vs per-deployment) were not confirmed.
- Ogma and yFiles feature and scale claims are [K] or vendor claims and were not verified this session.

---

## 2. Python-side options

### Takeaway
None of the Python wrappers is a good long-term base. pyvis (vis.js) is unmaintained since 2023, and ipycytoscape is Jupyter-only with its last PyPI release in 2022. Graphviz needs native binaries (problematic under the Windows/no-native constraint). The cleanest approach for SIP is to emit Cytoscape-JSON (or graphology/vis JSON) from rdflib/networkx with the stdlib `json` module and render in a vendored JS library. pyLODE and Ontospy are useful for HTML documentation, not interactive graphs.

### Comparison table

| Tool | Licence | Latest release | Activity | What it produces | Native deps | Notes for SIP |
|---|---|---|---|---|---|---|
| **pyvis** | BSD-3-Clause | 0.3.2 (2023-02-24) | Repo last pushed 2024-04-24; last commit 2023-02-10; 1,209 stars | Static HTML with vis-network | None | **Stale**. Generates HTML from networkx; easy PoC, but bundles an old vis 9.1.2 |
| **ipycytoscape** | BSD-3-Clause | 1.3.3 (PyPI, 2022-04-04) | Repo pushed 2026-10-05; 291 stars | Jupyter widget (Cytoscape.js) | Jupyter stack | Notebook-only, not a web component; no PyPI release since 2022 |
| networkx drawing | BSD-3-Clause | networkx 3.7 (2026-09-21) | Active | matplotlib static images; `nx.cytoscape_data()` / `node_link_data()` JSON | matplotlib for drawing; JSON export is pure Python | **`nx.cytoscape_data()` emits Cytoscape.js JSON directly** [K] — the key zero-dependency bridge |
| **graphviz** (Python pkg) | MIT | 0.21 (2025-06-15) | 1,814 stars, pushed 2026-07-11 | DOT source; rendering needs the `dot` executable | **Requires Graphviz binaries** | DOT generation is pure Python; rendering needs the native `dot`, or a browser-side WASM build (e.g. viz.js / @hpcc-js/wasm) [K] |
| **pygraphviz** | BSD-3-Clause [K] (GitHub reports NOASSERTION) | 2.0.4 (2026-10-15) | 848 stars, active | C bindings to libgraphviz | **Needs Graphviz C headers/libs to build; painful on Windows** | Excluded by the no-native constraint |
| **Mermaid** generation | MIT (mermaid 12.2.0, 2026-10-13, 90.8k stars, 11M/week) | — | Very active | Text → SVG in the browser | None (JS) | Easy to emit `classDiagram`/`flowchart` text from rdflib; good for small static docs, poor for interactive large graphs; the min bundle is 5.5 MB on jsDelivr |
| **Ontospy** | MIT | 2.7 (2026-10-20) | 253 stars, pushed 2026-10-20 | CLI/library: inspects RDF/OWL and generates HTML docs, including D3-based visualizations [K] | rdflib-based | Useful as reference/documentation output; its visualizations are template-based, not a reusable component |
| **pyLODE** | BSD-3-Clause | 3.6.0 (2026-08-17) | 232 stars, pushed 2026-09-19 | Static HTML ontology documentation (OWL/SKOS profiles) | rdflib | Docs, not graph visualization; complements the publish stage |
| **OWL2VOWL** | MIT | (Java) | Repo pushed 2026-06-04; 154 stars | OWL → VOWL JSON for WebVOWL | **Java (OWL API)** | No Python port found; SIP would have to write an rdflib → VOWL-JSON converter |
| yfiles-jupyter-graphs | yWorks free licence for the widget [K] | 2.0.0 (2026-08-10) | — | Jupyter widget using yFiles | Jupyter | Notebook exploration only |
| ipysigma | MIT | 0.24.6 (2025-11-25) | — | Jupyter widget using sigma.js | Jupyter | Notebook exploration only |

### Cited findings
- pyvis 0.3.2 released 2023-02-24 (PyPI), BSD-3-Clause. Its most recent commits (Feb 2023) moved bindings to vis 9.1.2, and the repo was last pushed 2024-04-24 — [PyPI pyvis](https://pypi.org/project/pyvis/), [GitHub pyvis](https://github.com/WestHealth/pyvis)
- ipycytoscape latest PyPI release 1.3.3 (2022-04-04); the GitHub repo was pushed 2026-10-05 — [PyPI](https://pypi.org/project/ipycytoscape/), [GitHub](https://github.com/cytoscape/ipycytoscape)
- graphviz (Python) 0.21 on 2025-06-15, MIT; pygraphviz 2.0.4 on 2026-10-15 — [PyPI graphviz](https://pypi.org/project/graphviz/), [PyPI pygraphviz](https://pypi.org/project/pygraphviz/)
- networkx 3.7 released 2026-09-21 — [PyPI networkx](https://pypi.org/project/networkx/)
- `networkx.readwrite.json_graph.cytoscape_data` returns Cytoscape.js-format JSON — [K] [networkx docs](https://networkx.org/documentation/stable/reference/readwrite/generated/networkx.readwrite.json_graph.cytoscape_data.html)
- Mermaid 12.2.0 (2026-10-13), MIT, 90,773 stars, 11M weekly downloads — [npm mermaid](https://www.npmjs.com/package/mermaid), [GitHub](https://github.com/mermaid-js/mermaid)
- Ontospy 2.7 (2026-10-20), MIT — [PyPI ontospy](https://pypi.org/project/ontospy/), [GitHub](https://github.com/lambdamusic/Ontospy)
- pyLODE 3.6.0 (2026-08-17), BSD-3-Clause — [PyPI pylode](https://pypi.org/project/pylode/), [GitHub](https://github.com/RDFLib/pyLODE)
- OWL2VOWL is a Maven-built Java jar that writes a JSON file. No Python port producing VOWL JSON from rdflib was found; related Python tools (owllib, owl2else/owl2plot via graphviz, funowl) are not VOWL ports — [OWL2VOWL GitHub](https://github.com/VisualDataWeb/OWL2VOWL), [owl2else PyPI](https://pypi.python.org/project/owl2else/), [owllib PyPI](https://pypi.org/project/owllib/)
- yfiles_jupyter_graphs 2.0.0 (2026-08-10); ipysigma 0.24.6 (2025-11-25, MIT) — [PyPI yfiles_jupyter_graphs](https://pypi.org/project/yfiles_jupyter_graphs/), [PyPI ipysigma](https://pypi.org/project/ipysigma/)

### Inferences
- The SIP backend needs no visualization dependency at all: rdflib → networkx (already a core dependency) → `cytoscape_data()`/custom JSON → static HTML that loads vendored JS. This satisfies the dependency-light rule.
- Graphviz output is only viable if the DOT is rendered in the browser with a WASM Graphviz build (no native libs). That is workable for static class diagrams, but interactivity is limited.
- A VOWL-JSON emitter written in Python over rdflib (mapping owl:Class, rdfs:subClassOf, object/datatype properties, owl:equivalentClass, etc.) would let SIP reuse WebVOWL's front end without Java. This is a modest, self-contained capability.

### Gaps
- The exact JSON shape of Ontospy's current visualizations (and whether they can be embedded) was not verified.
- The yfiles-jupyter-graphs licence terms were not verified this session.

---

## 3. Ontology-specific tools

### Takeaway
Of the ontology-specific tools, the reusable open ones are WebVOWL (MIT, VOWL notation, revived with commits in June 2026 but still dependent on Java OWL2VOWL for conversion) and Reactodia (LGPL-2.1-or-later, the actively maintained TypeScript/React fork of Ontodia, v0.35.2 in Aug 2026). The rest are features of commercial or Java platforms (GraphDB, Stardog, Gruff, TopBraid EDG, VocBench, Protégé), useful mainly as UX references. Neo4j NVL is licensed only for use with Neo4j products, so it is unusable for SIP/FalkorDB. The FalkorDB Browser is SSPL-licensed. The new MIT `@falkordb/canvas` web component is a better reuse candidate.

### Table

| Tool | Licence | Maintenance (2025–26) | Tech | Ontology features | Reuse in SIP |
|---|---|---|---|---|---|
| **WebVOWL** | MIT | Repo pushed 2026-06-04 (Docker local-stack work); 1,014 stars | D3 force, SVG | VOWL notation for OWL (classes, properties, set operators, cardinalities); filters; JSON-VOWL export | Front end reusable if SIP emits VOWL JSON; the converter is Java (OWL2VOWL) |
| **Ontodia** | LGPL-2.1 | **Archived** (last push 2022-12, npm 0.12.2 from 2020) | React/TS | Diagram-based RDF/OWL exploration | Do not use; superseded |
| **Reactodia** (`@reactodia/workspace`) | LGPL-2.1-or-later | 0.35.2 (2026-08-08), ~6k weekly DL | TypeScript/React, SVG + layout in a Web Worker | Load RDF ontology, create a diagram from OWL classes, explore and edit graph data from data providers (e.g. SPARQL) | **Strong candidate** for the production ontology/KG explorer; needs a React build; LGPL means keep it as an unmodified, separately loaded library |
| Gruff (Franz) | Proprietary (free download, password-gated) | Browser version included in AllegroGraph 7 | Desktop/browser | RDF browser, visual query building, works with any SPARQL endpoint | UX reference only |
| GraphDB Visual Graph (Ontotext) | Proprietary (part of the GraphDB Workbench) | Active product | Workbench UI | Visual graph from a resource or a CONSTRUCT query; custom graph configs | Reference: shows the CONSTRUCT → visual graph pattern |
| Stardog Studio / Explorer | Proprietary | Active product | Web | Studio: Text/Visual toggle for CONSTRUCT/DESCRIBE; Explorer: search → expand graph, class legend filtering; older docs cite ~5,000-entity visualization limits | Reference |
| **FalkorDB Browser** | **SSPL v1** (LICENSE.txt) | Very active (pushed 2026-10-20); 135 stars | Next.js app | Cypher query results as a graph, per-label styling, query history, CSV import | Run as a separate admin tool (Docker), not embedded |
| **@falkordb/canvas** | MIT | 0.3.3 (2026-10-12) | Standalone web component, force-directed | Visualizes FalkorDB graphs | **Candidate** for a FalkorDB projection view; young (0.x) |
| Neo4j Bloom / **NVL** | Proprietary; NVL "may only be used with" Neo4j Aura or Neo4j commercial products | NVL 2.0.0 (2026-09-15) | WebGL/Canvas | — | **Not usable** with FalkorDB/Fuseki |
| neovis.js | Apache-2.0 | Last release 2.1.0 (2023-05) | vis-network | Neo4j Cypher → vis | Stale, Neo4j-specific |
| TopBraid EDG diagrams | Proprietary | EDG Diagram panel since 7.1/7.2 | Web | Class boxes listing properties with ranges and cardinality; expandable relationship arrows; resource, class and property-shape nodes; classes and instances on one canvas | **UX reference for SHACL/class diagrams** |
| VocBench 3 graph view | BSD-3-Clause [K] | Graph view stable since v6.0 (2019); class diagram stable since v8.0 (2020) | Angular + D3 [K] | Data-oriented, model-oriented and class-diagram perspectives; language/literal filters; expand from a node; SVG export | Direct functional reference, since SIP ports VocBench |
| Protégé OntoGraf | LGPL [K] (GitHub reports no licence) | **Dormant**: repo last pushed 2018-05-27; 23 stars | Java Swing | Class hierarchy, interactive expand | Java, unusable here; reference only |
| yasgui-graph-plugin (Matdata) | Apache-2.0 | 0.1.0 MVP, 1 star | vis-network | Renders CONSTRUCT/DESCRIBE results; double-click runs DESCRIBE to expand; CDN UMD | Tiny reference for a SPARQL → graph plugin |

### Cited findings
- WebVOWL: MIT, 1,014 stars. The latest commits (2026-06-04) add a Docker local stack that clones OWL2VOWL in the image build. OWL2VOWL: MIT, 154 stars, pushed 2026-06-04 — [WebVOWL GitHub](https://github.com/VisualDataWeb/WebVOWL), [OWL2VOWL GitHub](https://github.com/VisualDataWeb/OWL2VOWL)
- Ontodia's GitHub repo is archived (last push 2022-12-11). The npm `ontodia` package is 0.12.2 (2020-03-25, LGPL-2.1) — [metaphacts/ontodia](https://github.com/metaphacts/ontodia), [npm ontodia](https://www.npmjs.com/package/ontodia)
- `@reactodia/workspace` 0.35.2 (2026-08-08), LGPL-2.1-or-later, ~5,950 weekly downloads. It is an open-source fork of Ontodia, a TypeScript library to explore, visualize and change data as an interactive graph. Its example loads an RDF ontology, builds a diagram from OWL classes and runs layout in a Web Worker. VisGraph is a third-party RDF/ontology editor built on the Reactodia canvas — [npm @reactodia/workspace](https://www.npmjs.com/package/@reactodia/workspace), [VisGraph](https://dataportal.material-digital.de/en/dataset/visgraph-interactive-rdf-ontology-canvas)
- Gruff works with any triple store via the SPARQL endpoint protocol. The browser version is included in AllegroGraph 7. The download page requires a password obtained via Franz's X feed or sales. An undated Franz deck lists free AllegroGraph at 5M triples (this is AllegroGraph's cap, not a Gruff cap) — [Gruff downloads](https://franz.com/agraph/gruff/download/), [Franz slides](https://www.slideshare.net/FranzInc/visualizing-and-exploring-knowledge-graphs-with-the-new-browser-based-gruff)
- GraphDB: a CONSTRUCT query can be shown as a "Visual" graph in the workbench, and filtering to classes is recommended to avoid clutter — [Medium: Exploring an RDF graph database](https://levelup.gitconnected.com/exploring-a-rdf-graph-database-ba2688f9e118), [SPHN guide](https://sphn-semantic-framework.readthedocs.io/en/latest/user_guide/data_exploration.html)
- Stardog Studio renders CONSTRUCT and DESCRIBE results with a Text/Visual toggle. Explorer offers search-to-graph expansion with a class legend filter. The archived 7.9.0 docs state a top-50-entity search limit and ~5,000-entity visualization limit — [Stardog blog](https://www.stardog.com/blog/picture-this-visual-results-in-studio/), [Explorer docs 7.9.0](https://docs.stardog.com/archive/7.9.0/stardog-applications/explorer/)
- FalkorDB Browser: a Next.js visualization/management UI with per-label styling, query history, Cypher diagnostics and CSV import. It ships as `falkordb/falkordb-browser` and inside `falkordb/falkordb`. Its LICENSE.txt is the **Server Side Public License v1** — [GitHub falkordb-browser](https://github.com/FalkorDB/falkordb-browser), [LICENSE.txt](https://github.com/FalkorDB/falkordb-browser/blob/staging/LICENSE.txt)
- `@falkordb/canvas` 0.3.3 (2026-10-12), MIT: "A standalone web component for visualizing FalkorDB graphs using force-directed layouts" — [npm @falkordb/canvas](https://www.npmjs.com/package/@falkordb/canvas)
- NVL licence: "may only be used with (i) the Aura software as a service ... or (ii) the proprietary commercial graph database products developed by Neo4j". `@neo4j-nvl/base` 2.0.0 (2026-09-15) — [unpkg LICENSE.txt](https://unpkg.com/@neo4j-nvl/base@2.0.0/LICENSE.txt), [NVL docs](https://neo4j.com/docs/nvl/current/)
- neovis.js 2.1.0 (2023-05-17), Apache-2.0, repo last pushed 2023-10 — [npm neovis.js](https://www.npmjs.com/package/neovis.js)
- TopBraid EDG Diagram panel: introduced in 7.1 and expanded in 7.2. Class boxes list properties with ranges and cardinalities, literal vs relationship icons and expandable relationships, with resource, class and property-shape node types — [TopQuadrant blog](https://topquadrant.com/blog/visual-exploration-of-ontologies-with-topbraid-edg), [EDG 7.2 Using EDG Diagrams](https://archive.topquadrant.com/doc/7.2/user_guide/working_with_asset_collections/using_edg_diagrams.html)
- VocBench 3 Graph View has data-oriented, model-oriented and class-diagram perspectives. The graph view was finalized in v6.0 and the class diagram became stable in v8.0. It has language and literal filters, node expansion and SVG export — [VocBench Graph View docs](https://vocbench.uniroma2.it/doc/user/graphs.jsf), [VB3 v6.0 announcement](https://lists.w3.org/Archives/Public/semantic-web/2019Jun/0190.html), [Stellato NKOS 2021](https://nkos.dublincore.org/2021NKOSworkshop/Stellato-NKOS2021.pdf)
- Protégé OntoGraf: GitHub repo last pushed 2018-05-27, 23 stars — [GitHub ontograf](https://github.com/protegeproject/ontograf)
- yasgui-graph-plugin: Apache-2.0, vis-network-based, CONSTRUCT/DESCRIBE only, jsDelivr UMD, v0.1.0 MVP with 1 star — [GitHub](https://github.com/Matdata-eu/yasgui-graph-plugin)

### Inferences
- SIP's model-stage "class diagram" view should copy the TopBraid EDG / VocBench class-diagram idiom: UML-ish class boxes listing properties with range and cardinality, plus subclass edges in a layered layout. Cytoscape.js compound/HTML-label nodes or G6 can approximate this, while Reactodia does it natively.
- SSPL on the FalkorDB Browser is a network-copyleft licence. Running it unmodified as a separate admin container is fine, but embedding or modifying it inside SIP is not advisable.
- Because NVL is restricted to Neo4j products, the "Neo4j look" for the FalkorDB projection would have to come from `@falkordb/canvas`, Cytoscape.js or sigma.

### Gaps
- The official Ontotext GraphDB "graph config" documentation page was not retrieved. The CONSTRUCT-based visual graph is confirmed only via secondary sources.
- The current Stardog Explorer limits (post-v9) were not verified.
- Whether Reactodia's official GitHub repository is `reactodia/reactodia-workspace` could not be verified (GitHub API rate limit). Its star count is unknown.
- The FalkorDB Browser's internal rendering library was not identified from the README.
- The licences for VocBench 3 (BSD-3-Clause) and OntoGraf (LGPL) are [K] and unverified.

---

## 4. Which tools render FalkorDB/Cypher results and SPARQL CONSTRUCT results directly?

### Takeaway
Only database-bundled tools render results directly. The FalkorDB Browser and `@falkordb/canvas` handle Cypher on FalkorDB. GraphDB Workbench, Stardog Studio, Gruff, YASGUI + graph plugin and Reactodia (via its SPARQL data provider) handle SPARQL. No general JS library consumes Cypher or CONSTRUCT output natively. For SIP, a ~100-line Python adapter (rdflib Graph from CONSTRUCT → Cytoscape JSON; FalkorDB result set nodes/edges → the same JSON) gives one renderer for both stores.

### Cited findings
- FalkorDB Browser visualizes graph data from Cypher queries, with a query-history panel — [GitHub falkordb-browser](https://github.com/FalkorDB/falkordb-browser)
- `@falkordb/canvas` is a standalone web component for visualizing FalkorDB graphs — [npm](https://www.npmjs.com/package/@falkordb/canvas)
- Stardog Studio renders CONSTRUCT and DESCRIBE results visually — [Stardog blog](https://www.stardog.com/blog/picture-this-visual-results-in-studio/)
- GraphDB Workbench renders CONSTRUCT results via the "Visual" option — [Medium](https://levelup.gitconnected.com/exploring-a-rdf-graph-database-ba2688f9e118)
- Gruff works against any SPARQL endpoint — [Gruff downloads / Franz](https://franz.com/agraph/gruff/download/)
- The YASGUI graph plugin renders CONSTRUCT/DESCRIBE results via vis-network — [GitHub](https://github.com/Matdata-eu/yasgui-graph-plugin)
- Reactodia builds diagrams from RDF/OWL data through data providers — [npm @reactodia/workspace](https://www.npmjs.com/package/@reactodia/workspace)
- NVL can render Cypher results, but it is licensed only for use with Neo4j products — [NVL LICENSE.txt](https://unpkg.com/@neo4j-nvl/base@2.0.0/LICENSE.txt)

### Inferences
- An rdflib CONSTRUCT result is already a `Graph`, so SIP can project it (IRIs → nodes, literals → node attributes or label nodes, rdf:type → class styling, rdfs:subClassOf → hierarchical edges) into Cytoscape JSON server-side. This keeps Fuseki and FalkorDB views on a single front-end component.
- Fuseki's own UI has no graph view, so SIP's component fills a real gap for the canonical store.

### Recommendation shortlist

**(a) No-build PoC (single static HTML, CDN or vendored, offline-capable)**
1. **Cytoscape.js 3.34 + cytoscape-dagre (or cytoscape-elk + elkjs bundled) + cytoscape-fcose + cytoscape-expand-collapse**, fed by `networkx.cytoscape_data()` / a custom rdflib → JSON emitter. This covers layered class hierarchies, compound nodes for namespaces/modules, expand-collapse and selector filtering. The core is 134 KB gzipped, plus 423 KB gzipped if elkjs is used.
2. **vis-network 10** as the quickest fallback: built-in hierarchical layout and an editing toolbar in one 652 KB UMD file (the approach pyvis uses, but with a current vis version).
3. **Mermaid 12** for static documentation snippets (class diagrams in reports), not for interactive exploration.
4. Optionally, keep **WebVOWL** as a static reference viewer if a Python rdflib → VOWL-JSON emitter is written (no Java at runtime).

**(b) Production component**
1. **Cytoscape.js (with ELK layered + fCoSE, WebGL renderer as it matures)** as the default ontology/KG view component. It has an MIT licence, is very actively maintained and keeps the PoC code path.
2. **Reactodia** (LGPL-2.1+) for an ontology-aware explorer/editor (OWL classes, SPARQL data providers). It requires adopting a React/TypeScript build and LGPL compliance (dynamic, unmodified use).
3. **sigma.js v4 + graphology** (or MIT **cosmos.gl**) for large instance-level KG / GraphRAG projection views beyond Cytoscape Canvas limits.
4. Commercial upgrade path if budget allows: **yFiles for HTML** (best hierarchic/orthogonal layouts and folding; quote-only) or **GoJS** (from $3,995 individual / $6,990 for 3 developers; no royalties). **Ogma** is quote-only. All performance claims for these are vendor claims.
5. Avoid: NVL (Neo4j-only licence), Cosmograph CC-BY-NC packages, pyvis/dagre-d3/Ontodia/OntoGraf (stale or archived), pygraphviz (native build), and embedding the SSPL FalkorDB Browser.

### Gaps
- No published side-by-side benchmark for rendering ontology-sized graphs (1k–50k nodes) across these libraries was found. SIP should run its own benchmark using FIBO as the test corpus.
