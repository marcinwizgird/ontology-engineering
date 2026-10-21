# Scalability techniques for visualizing large ontologies and knowledge graphs (SIP)

Scope: TBox graphs with 10^3 to 10^4 classes (FIBO) and ABox graphs with 10^5+ nodes, rendered in a web-based ontology engineering tool. Research date: 2026-10-20.

Local measurement of the target corpus: the FIBO snapshot in this repo (`Ontology Repository/FIBO/fibo`) has **297 `.rdf` files and about 3,004 distinct `owl:Class rdf:about` declarations**. The count comes from a grep over the files. It covers production and development modules together and excludes anonymous class expressions. That puts FIBO above the "2,000+" figure in the brief. A patent document likewise describes FIBO as having "over a hundred Ontology modules or files" ([USPTO 12038939](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12038939)). The FIBO Viewer describes a hierarchy of domains, then sub-domains, then modules, with ontologies at the bottom ([FIBO Viewer](https://spec.edmcouncil.org/fibo/ontology/SEC/Debt/Bonds/Bond)). That containment hierarchy is a ready-made clustering structure.

## 1. Focus+context, DOI, expand-on-demand, progressive disclosure, semantic zoom, LOD

### Takeaway
The best-established technique for large graphs whose users have "semi-specific information needs" is van Ham & Perer's model: search, show the context subgraph ranked by a degree-of-interest (DOI) function, and expand on demand. It skips the global overview. It was demonstrated on a citation graph with more than 300k nodes and 3.3M edges through a thin web client, and it maps directly onto ontology work: start from a class, show the classes around it.

### Cited Findings
- Van Ham & Perer (IEEE InfoVis 2009, TVCG 15(6)) argue that a global overview is often "not relevant or practical" for users with semi-specific information needs. They add that remote and low-powered clients "simply do not have the resources needed to compute these overviews". Instead they "advocate an interaction model that allows users to remotely browse the immediate context graph around a specific node of interest." — [van Ham & Perer 2009 PDF](https://perer.org/papers/adamPerer-DOIGraphs-InfoVis2009.pdf)
- The demonstration dataset was about 15 GB of US federal and Supreme Court cases, forming a citation graph of more than 300,000 nodes and 3.3 million edges. Multiple analysts explored it at the same time through an interactive web client. — [van Ham & Perer 2009](https://perer.org/papers/adamPerer-DOIGraphs-InfoVis2009.pdf)
- Furnas's DOI for trees is `DOI(x|y) = α·API(x) + β·D(x,y)`: a priori interest plus distance from the focus. For trees, API can be defined as distance to the root. Van Ham & Perer extend it to graphs: `DOI(x|y,z) = α·API_diff(x) + β·UI_diff(x,z) + γ·D(x,y)`. Here UI is user interest derived from search terms z, and the diffusion term is `API_diff(x) = max(API(x), δ·max_{n∈N(x)} 1/EI(e,x,n)·API_diff(n))`, with 0 ≤ δ < 1. — [van Ham & Perer 2009](https://perer.org/papers/adamPerer-DOIGraphs-InfoVis2009.pdf)
- Diffusion is needed because on graphs, unlike trees, DOI is not strictly nested. A plain threshold yields "a potentially large number of disconnected subgraphs", and a local search from the focus cannot reach interesting nodes that sit behind uninteresting ones. API is computed once. UI is recomputed when the search terms change, and D when the focus changes. — [van Ham & Perer 2009](https://perer.org/papers/adamPerer-DOIGraphs-InfoVis2009.pdf)
- The paper lists the alternatives it rejects. Aggressive clustering abstractions can produce clusters whose meaning is lost. Screen-space distortion compresses the graphics but not the information. Attribute roll-up into metanodes works poorly with very high-degree nodes. It also introduces edge-interest functions to tame high-degree nodes. — [van Ham & Perer 2009](https://perer.org/papers/adamPerer-DOIGraphs-InfoVis2009.pdf)
- RDF Digest+ (ISWC 2018) adds "zoom" and "extend" operators so users can move from a static schema summary to more detailed views. This is progressive disclosure over summaries. The authors show that computing these operators is NP-hard, so heuristics are needed. — [Troullinou et al. ISWC 2018](https://homepages.tuni.fi/konstantinos.stefanidis/docs/iswc18.pdf)
- Paged Graph Visualization (PGV) "starts with a small graph and provides tools to incrementally explore very large RDF ontologies". It fetches subgraphs in response to user-directed exploration and lays them out without disturbing the nodes already placed (layout stability). — [PGV, Knoesis](https://corescholar.libraries.wright.edu/knoesis/225)
- In the Siren Graph Browser, the vendor's expansion guard rails include a configurable "graph expansion limit" (100 to 10,000 nodes per import) and a "big nodes threshold". Past that threshold the user is asked to proceed or to take a sample. — [Siren docs](https://docs.siren.io/siren-platform-user-guide/14.8/graph-browser/t_config-graph-browser.html)

### Inferences
- For SIP, a DOI over the TBox could use API = a key-concept score (section 2), UI = text or facet search match, D = hop distance over `rdfs:subClassOf`, property domain/range, and `owl:imports`, and EI = edge-type weights (subClassOf above restriction edges above annotation edges). All three terms can be precomputed or computed incrementally on the server, which matters for FIBO.
- A "big node" confirm-or-sample guard is cheap and directly useful for ABox hubs such as `fibo-fnd-org-fm:FormalOrganization` instances, or any class with tens of thousands of instances.
- Semantic zoom / LOD (labels and glyphs only above a zoom threshold, aggregate glyphs below it) appears in the renderer documentation as standard practice. I found no ontology-specific study that quantifies its effect.

### Gaps
- I found no controlled user study comparing overview-first and search-first designs specifically for ontologies.
- I did not retrieve Furnas 1986 or a primary semantic-zoom paper. The Furnas formula above is as restated by van Ham & Perer.

## 2. Aggregation and abstraction: summarization, modularization, communities, compound graphs, edge bundling

### Takeaway
Ontology-specific summarization (KCE, RDF Digest) gives a principled "first screen" of 10 to 50 key concepts. FIBO's own module and domain hierarchy, plus imports, gives natural compound-node clusters. Hierarchical edge bundling (Holten) is the canonical way to show non-taxonomic links over a taxonomy without hairballs. Community detection is a fallback when the ontology lacks good modular structure.

### Cited Findings
- KCE (Peroni, Motta, d'Aquin, ASWC 2008) identifies the concepts that best summarize an ontology. It combines cognitive-science criteria (natural categories, basic level), network topology (density, coverage) and lexical statistics (popularity). Its later version agreed strongly with human experts. It powered KC-Viz in the NeOn Toolkit, which navigates large ontologies starting from the key concepts. — [ORO record](https://oro.open.ac.uk/23484); [KMi KCE page](https://kmi.open.ac.uk/technologies/name/kce); [DOI 10.1007/978-3-540-89704-0_17](https://doi.org/10.1007/978-3-540-89704-0_17)
- Li, Motta & d'Aquin noted that ontology summarization lacked consensus on its definition and on evaluation. — [Ontology summarization: an analysis and an evaluation](https://oro.open.ac.uk/24693)
- RDF Digest (Troullinou, Kondylakis, Plexousakis et al., ESWC 2015 and SWJ 2017) builds a summary that is itself a valid RDFS graph. It ranks nodes by relevance, using schema semantics and structure plus the instance distribution, then selects connecting edges by maximizing importance locally or globally. The authors report that it beat two other systems. — [VOILA/CEUR 2015](https://www.ceur-ws.org/Vol-1486/paper_79.pdf); [SWJ article](https://content.iospress.com/articles/semantic-web/sw264)
- A VLDB Journal 2019 survey (Čebirić et al., including the same group) provides a taxonomy of RDF graph summarization methods and notes that there is no single notion of an RDF summary. — [Summarizing semantic graphs: a survey](https://researchportal.ip-paris.fr/fr/publications/summarizing-semantic-graphs-a-survey/)
- A graph-based ontology summarization survey frames the field as mostly centrality-based (degree, betweenness, PageRank-like measures). — [Graph-based Ontology Summarization: A Survey](https://physics.paperswithcode.com/paper/graph-based-ontology-summarization-a-survey)
- OntoPlot (Yang, Wybrow, Li, Czauderna, He; IEEE TVCG 2019) combines an icicle-plot hierarchy, visual compression of "uninteresting" subtrees and interactive association display. Compression is found in a single depth-first traversal, "linear in the number of classes". Labels are shown greedily for parents and diagonally for classes with associations, to avoid occlusion. In a user study with domain experts it beat Protégé on accuracy and task completion. — [OntoPlot arXiv 1908.00688](https://arxiv.org/pdf/1908.00688)
- OntoPlot also cites glyph-based compression for node-link diagrams: Dunne & Shneiderman's motif simplification, which replaces common patterns with glyphs, and structural-equivalence grouping. — [OntoPlot](https://arxiv.org/pdf/1908.00688)
- Holten's Hierarchical Edge Bundles (IEEE TVCG 12(5):741-748, 2006; doi:10.1109/TVCG.2006.147) targets data with inclusion (parent-child) relations plus adjacency relations. Each adjacency edge becomes a B-spline routed along the hierarchy path between its endpoints. This reduces clutter and also shows implicit adjacencies between parent nodes. — [TU/e record](https://research.tue.nl/nl/publications/hierarchical-edge-bundles-visualization-of-adjacency-relations-in/); [paper PDF](https://www.cg.tuwien.ac.at/courses/InfoVis/HallOfFame/2007/Grasberger/InfoVis2006%20Hierarchical%20Edge%20Bundles%20%20%20Visualization%20of%20Adjacency%20Relations%20in%20Hierarchical%20Data%20%5BDanny%20Holten%5D.pdf); [ggraph geom_conn_bundle](https://ggraph.data-imaginist.com/reference/geom_conn_bundle.html)

### Inferences
- FIBO has an explicit inclusion hierarchy (domain → sub-domain → module → ontology file → class) and many non-taxonomic object-property restrictions. That is exactly the "compound graph" input HEB expects. A radial or icicle layout of the module hierarchy with bundled restriction and usage edges is a strong FIBO-wide overview. In SIP it would be a precomputed, static artifact.
- Imports-as-clusters (one compound node per ontology IRI, collapsed by default) is lower-risk than Louvain/Leiden for curated ontologies, because the clusters carry meaning the authors chose. Communities fit ABox projections better (for example in FalkorDB), where no curated grouping exists.
- Locality-based modules (Cuenca Grau et al.; OWL API syntactic locality ⊥/⊤/STAR) are a natural "extract the signature-closed module around my focus" operation. They feed the ego view a logically complete neighbourhood. This was not verified in this session's sources. It needs a source citation from the module-extraction literature.

### Gaps
- I did not fetch primary sources for Louvain (Blondel 2008) or Leiden (Traag, Waltman & van Eck 2019). Their runtimes on 10^5 to 10^6-node graphs, commonly reported as seconds, could not be confirmed here.
- I found no study that evaluates KCE or RDF Digest on FIBO specifically.
- I did not retrieve Pires et al. (cited in the brief).

## 3. Layout algorithms for ontologies and their cost

### Takeaway
Taxonomies with multiple inheritance are DAGs, so a layered (Sugiyama) layout is the natural fit. But crossing minimization is NP-hard even for two layers, so the heuristics get slow and the drawings unreadable at thousands of nodes. Use layered layout for bounded subgraphs (ego views, a single module). Use precomputed, server-side or GPU force/stress layouts for large overviews, and run any client layout in a Web Worker.

### Cited Findings
- Several subproblems of layered drawing are NP-hard, crossing minimization among them, so systems use heuristics. — [Wikipedia: Layered graph drawing](https://en.wikipedia.org/wiki/Layered_graph_drawing)
- Ordering within layers is NP-hard even for two layers. It is usually done by layer-by-layer sweeps (barycenter or median heuristics). — [KIT graph visualization lecture](https://algo.iti.kit.edu/_media/teaching/winter2019/graphvis/graphvis-ws19-v11.pdf)
- One-sided and two-sided crossing minimization are both NP-hard. Eades & Wormald's median heuristic is a 3-approximation for the one-sided case. — [arXiv 2502.20896](https://www.arxiv.org/pdf/2502.20896)
- Counting crossings across the whole graph is itself costly, and it is repeated across many candidate orderings. — [USPTO 8994730](https://patents.google.com/patent/US8994730)
- Reactodia (an Ontodia fork) recommends computing graph layout in a background Web Worker to keep the UI responsive. — [Reactodia GitHub](https://github.com/Reactodia/reactodia-workspace)
- Cosmograph's documentation says CPU force layouts tend to struggle at about 50k nodes in one doc and "around 100,000 nodes" in another. Cosmograph runs the entire force simulation on the GPU, and the many-body term needed a GPU-specific design because random memory access is slow on GPUs. **Vendor claim.** — [Cosmograph concept docs](https://cosmograph.app/docs-general/concept/); [Cosmograph intro](https://cosmograph.app/docs/cosmograph/Introduction)
- Cosmos (the open-source engine under Cosmograph) runs computation and drawing in shaders. It claims real-time simulation of "hundreds of thousands of points and links" on modern hardware. v3 runs on WebGL 2 via luma.gl and adds a GPU collision force using a spatial-hash grid. It fails on Android devices without `OES_texture_float`, and the Many-Body force broke on iOS ≥15.4 when `EXT_float_blend` was removed (reportedly fixed in later iOS). **Vendor claim, no published benchmark.** — [cosmograph-org/cosmos](https://github.com/cosmograph-org/cosmos)
- In the 2025 benchmark (section 4), the default force-directed layouts ran 200 iterations. D3 (Canvas or WebGL) was the only library to finish within 15 minutes at 200k nodes with edge/node ratio 10. ECharts topped out at 20k to 25k nodes. Time here is the whole pipeline, layout included. — [Graph visualization efficiency of popular web-based libraries, Visual Computing for Industry, Biomedicine, and Art 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12061801/)

### Inferences
- Precompute the FIBO-wide layout on the server (Python: networkx/graphviz `dot` for the layered module view, or a stress/force layout) and ship coordinates. The client does only incremental, stable placement of newly expanded nodes, as PGV does. This keeps the dependency-light core rule, since the layout runs offline as a build step.
- For the class DAG, a "spanning tree plus extra edges" approach avoids running a full Sugiyama on 3k nodes: pick one primary parent per class (for example by module or KCE score), lay the tree out radially or as an icicle, and draw the other parents as bundled edges. This is Holten's model.
- Stress majorization (Gansner, Koren & North 2004) gives better distance preservation than force-directed layout but needs all-pairs shortest paths, O(N^2) memory. That is fine for ego views of a few hundred nodes and not for 10^5 ABox nodes without sparse or landmark approximations. This is unverified in this session and should be confirmed with a primary source.

### Gaps
- I found no published runtime benchmarks for ELK Layered or dagre at 1k/5k/10k nodes. Practitioner reports suggest dagre degrades in the low thousands, but no source was retrieved, so treat that as unverified.
- I found no reproducible benchmark of GPU layout (Cosmos) against CPU layout. A 2016 GPU-layout paper claims interactive layout of millions of nodes ([Informatics 2016 via DOAJ](https://doaj.org/article/04bd530593244a46807e8f4c539b6487)), but I did not read the full text.

## 4. Rendering technology: SVG vs Canvas vs WebGL limits

### Takeaway
The only rigorous, reproducible benchmark found is a 2025 peer-reviewed study: 481 graphs, 100 to 200k nodes, one RTX 3060 machine. At edge/node ratio 1, the largest graphs it kept above 30 fps were about 2k nodes (SVG), about 5k (Canvas) and about 7k (WebGL via NetV). Above 10 fps the limits were about 7k / 15k / 20k. Practical rule: SVG for ego views of up to about 1-2k elements with rich styling, Canvas up to about 5k, WebGL for 10^4 to 10^5. Claims of 10^5 to 10^6 at interactive rates (sigma.js, Cosmograph) are vendor-reported or unverified.

### Cited Findings
- **Benchmark setup** (Visual Computing for Industry, Biomedicine, and Art 2025): 481 graphs (156 real, 325 synthetic via NetworkX), 100 to 200k nodes, edge/node ratio 1 to 10. Libraries: D3 5.16 (SVG, Canvas, and WebGL via NetV.js 1.1.11), ECharts 5.4.2 (SVG/Canvas) and G6 4.8.7 (SVG/Canvas). Defaults: force layout, 200 iterations, 1 px nodes and edges, 3k×3k canvas. Hardware: i7-12700, 32 GB RAM, RTX 3060, Chrome 106. 3 runs per dataset with a 15-minute cutoff, giving 10,101 time and 10,101 fps measurements. — [PMC12061801](https://pmc.ncbi.nlm.nih.gov/articles/PMC12061801/)
- **Largest node count still above 30 fps** at ratio 1: G6-SVG 600, G6-Canvas 1k, ECharts-SVG 2k, D3-SVG 2k, ECharts-Canvas 3k, D3-Canvas 5k, D3-WebGL 7k. At ratio 10: G6-SVG 100, G6-Canvas 200, D3-SVG 600, ECharts-SVG 700, ECharts-Canvas 2k, D3-Canvas 2k, D3-WebGL 5k. — [PMC12061801](https://pmc.ncbi.nlm.nih.gov/articles/PMC12061801/)
- **Largest node count still above 10 fps** at ratio 1: D3-WebGL 20k, D3-Canvas 15k, D3-SVG 7k, ECharts-Canvas 5k, ECharts-SVG 4k, G6-Canvas 3k, G6-SVG 2k. At ratio 10: D3-WebGL 15k, D3-Canvas 9k, ECharts-Canvas 4k, D3-SVG 2k, ECharts-SVG 2k, G6-Canvas 600, G6-SVG 300. — [PMC12061801](https://pmc.ncbi.nlm.nih.gov/articles/PMC12061801/)
- **Largest node count within the 15-minute budget** (ratio 1 / ratio 10): D3-SVG 200k/70k, D3-Canvas 200k/200k, D3-WebGL 200k/200k, G6-Canvas 150k/25k, G6-SVG 65k/10k, ECharts 25k/20-25k. On a 100-node graph D3-WebGL started at about 50 fps, below the roughly 60 fps of the other libraries, because of WebGL initialization overhead. — [PMC12061801](https://pmc.ncbi.nlm.nih.gov/articles/PMC12061801/)
- Stated limitations: default parameters only, static graphs only, one hardware configuration, memory not measured, time covers the whole pipeline. Sigma.js, Cytoscape.js and Cosmograph were not tested. 1 px marks with no labels flatter the results compared with real ontology views. — [PMC12061801](https://pmc.ncbi.nlm.nih.gov/articles/PMC12061801/)
- The sigma.js v4 docs say WebGL gives smooth performance with "tens of thousands of nodes and edges". **Vendor claim, not a benchmark.** — [sigma v4 rendering docs](https://v4.sigmajs.org/concepts/rendering/)
- A third-party page claims sigma.js v3 renders 100k-node graphs at 30-60 fps on mid-range hardware. **No methodology; treat as unverified.** — [Knogin](https://knogin.com/en/developers/sigma-large-graph-rendering)
- A practitioner write-up (2015-era test) put Canvas at its limit around 5k nodes and 5k edges, with WebGL usable up to about 10k nodes and 11k edges. These figures are old and anecdotal, but roughly consistent with the 2025 study. — [Stephen Weber, Medium](https://weber-stephen.medium.com/the-best-libraries-and-methods-to-render-large-network-graphs-on-the-web-d122ece2f4dc)
- Memgraph's blog compared D3-on-canvas with sigma.js on WebGL. It is not peer-reviewed. — [Memgraph blog](https://memgraph.com/blog/you-want-a-fast-easy-to-use-and-popular-graph-visualization-tool)
- The Cytoscape.js paper (Bioinformatics 2016) says thousands of elements are manageable on ordinary hardware, with speed depending on styling. Simpler edge styles speed up rendering. — [PMC4708103](https://pmc.ncbi.nlm.nih.gov/articles/PMC4708103)
- Cytoscape.js 2.7.0 release notes claim caching optimizations let it handle "roughly ten times more elements" than 2.6, without WebGL. — [Cytoscape.js blog 2.7.0](https://blog.js.cytoscape.org/2016/05/31/2.7.0-release/)
- A WebGPU study reports rendering up to 100k nodes and 2M edges at interactive frame rates. I could not retrieve the full text to verify. — [NSF PAR 10384648](https://par.nsf.gov//servlets/purl/10384648)
- A competitor (Linkurious Ogma) claims Cytoscape.js may fall short on enterprise-scale scalability. **Competitor claim.** — [Ogma vs Cytoscape](https://doc.linkurious.com/ogma/latest/compare/cytoscape.html)

### Inferences
- Labels dominate cost in ontology views, since class names are long. Every renderer needs label LOD (show labels only above a zoom or degree threshold, or for focus and DOI-top-k nodes), as OntoPlot does.
- A hybrid works well: an SVG/HTML node-template diagram (Reactodia/Ontodia style) for ego and edit views of up to a few hundred nodes, where rich OWL notation and editing matter, plus a WebGL canvas (sigma.js + graphology, or Cosmos) for the 10^4 to 10^5 ABox / FalkorDB projection view with no per-node DOM.

### Gaps
- I found no independent, reproducible benchmark of sigma.js, Cosmograph/Cosmos, deck.gl or regl graph layers. The numbers for those are vendor claims.
- I could not fetch the Cytoscape.js WebGL renderer announcement (Jan 2025; the connection reset). Its claimed speedups are unverified here.
- No benchmark measured memory or label rendering.

## 5. How existing tools handle FIBO-scale ontologies

### Takeaway
Tools that render the whole ontology as a node-link graph (WebVOWL) degrade at hundreds to thousands of classes. Tools that hold up at scale are exploration-first: Ontodia/Reactodia (start empty, add via search, expand neighbours), Neo4j Bloom (search-phrase or pattern-driven, with a hard per-query cap), and the FIBO Viewer and Protégé (indented trees). No tool found tries a full-FIBO node-link overview.

### Cited Findings
- The OntoPlot authors "encountered scalability issues with WebVOWL when visualising medium to large ontologies (hundreds or thousands of classes and their associations)". — [OntoPlot, arXiv 1908.00688](https://arxiv.org/pdf/1908.00688)
- The OntoPlot related-work survey says Protégé's indented tree duplicates concepts under multiple inheritance and lists non-hierarchical associations textually. OWLViz shows only the inheritance hierarchy as a layered node-link diagram. WebVOWL does not visually separate hierarchical from non-hierarchical relations. Jambalaya and Knoocks are unmaintained and no longer run. Surveys conclude that the "maturity, usability, and scalability" of ontology visualization tools "are still limited". — [OntoPlot](https://arxiv.org/pdf/1908.00688)
- The OntView project's comparison page reports that WebVOWL loaded the DBpedia 3.8 ontology (about 450 classes, about 10k axioms). That was an anecdotal comparison. — [OntView additional material](https://sid.cps.unizar.es/projects/OntView/Additional/)
- Ontodia is an LGPL-2.1 JS library for interactive graph views over RDF, with "visual navigation over large graphs" through a data-provider interface. ontodia.org lets users point it at a SPARQL endpoint. Graph Explorer, a fork, is incorporated into metaphactory. — [metaphacts/ontodia README](https://github.com/metaphacts/ontodia/blob/e7543e248a211ab834ab107836db8c766cc4813c/README.md); [graph-explorer](https://github.com/cui-ke/graph-explorer)
- Reactodia's canonical example starts with an empty diagram, uses `dataProvider.lookup` to find `owl:Class` entities, adds selected ones and then calls `model.requestData()`. That is selective, incremental construction, with layout in a Web Worker. It uses React and an `RdfDataProvider` (SPARQL supported per topic tags). — [Reactodia](https://github.com/Reactodia/reactodia-workspace)
- metaphactory 4.0 introduced a visual ontology editor whose language maps to OWL and SHACL, aimed at domain experts. I found no published scale limits. — [metaphactory 4.0](https://metaphacts.com/metaphactory-4-0); [metaphacts blog](https://blog.metaphacts.com/visual-ontology-modeling-for-domain-experts-and-business-users-with-metaphactory)
- Neo4j Bloom shows between 100 and 10,000 unique nodes per scene query, and Cypher responses are capped at 10,000 rows. Because rows contain duplicate nodes, about 26,000 rows were needed to reach 10,000 unique nodes in Neo4j's example. You cannot know the right `LIMIT` in advance, so Bloom uses the reactive driver to stream and deduplicate. — [Neo4j developer blog](https://neo4j.com/blog/developer/fetching-large-amount-data-neo4j-reactive-driver-the-bloom-case/)
- Community moderators describe the 10k cap as per query. Larger graphs are built by repeated expansion or paged search phrases. One AuraDB Free user saw a 1,000-node cap. — [Neo4j community thread](https://community.neo4j.com/t/bypass-10000-node-limit-in-bloom-neo4j-desktop/45670); [AuraDB thread](https://community.neo4j.com/t/neo4j-bloom-auradb/58516)
- FIBO publishes Production and Development releases. Every ontology is marked release, provisional or informative. — [FIBO Primer](https://spec.edmcouncil.org/fibo/doc/FIBO_Primer.pdf)
- Up to a third of FIBO changed at class level each quarter (2021 analysis). Precomputed layouts therefore need regenerating each release, and layout stability across versions matters. — [arXiv 2108.05401](https://arxiv.org/pdf/2108.05401)

### Inferences
- The release/provisional/informative maturity flag and the Production/Development split are cheap filters that shrink the default view of FIBO. For example, show only Production plus `release` by default.
- Bloom's 10k cap and the 100 to 10,000 expansion limit in Siren's Graph Browser suggest industry practice: about 10^4 nodes is the ceiling for a single interactive scene, even with WebGL.

### Gaps
- I could not retrieve the GraphDB Visual Graph documentation (the URL returned 404). Its expansion limits and its SPARQL-configurable "graph config" (starting point, expand, node-info queries) are unconfirmed in this session.
- I did not find WebVOWL's own published limits or a GitHub issue that quantifies them.

## 6. Incremental and query-driven views ("start from search, not from overview")

### Takeaway
Every scalable system found follows the same pipeline: (1) a search or pattern query picks a seed, (2) the server extracts a bounded context subgraph (a SPARQL CONSTRUCT or Cypher pattern with LIMIT, or DOI-ranked top-k), (3) the client renders it and expands on demand under a per-expansion cap, with stable incremental layout.

### Cited Findings
- Van Ham & Perer's client-server design keeps the full 3.3M-edge graph on the server. Clients receive only DOI-thresholded context subgraphs around a search-selected focus. — [van Ham & Perer 2009](https://perer.org/papers/adamPerer-DOIGraphs-InfoVis2009.pdf)
- Ontodia and Reactodia data providers query SPARQL endpoints lazily. Diagrams are built from lookup results and neighbour requests, not from a whole-graph load. — [Ontodia README](https://github.com/metaphacts/ontodia/blob/e7543e248a211ab834ab107836db8c766cc4813c/README.md); [Reactodia](https://github.com/Reactodia/reactodia-workspace)
- Bloom's search phrases are parameterized Cypher patterns, and results are streamed and capped. — [Neo4j developer blog](https://neo4j.com/blog/developer/fetching-large-amount-data-neo4j-reactive-driver-the-bloom-case/)
- PGV fetches subgraphs on demand from very large RDF ontologies and keeps the layout of the nodes already shown. — [PGV](https://corescholar.libraries.wright.edu/knoesis/225)
- RDF Digest+ moves from a summary to details with zoom and extend operators. — [ISWC 2018](https://homepages.tuni.fi/konstantinos.stefanidis/docs/iswc18.pdf)

### Inferences (combination guidance for SIP)
1. **Landing view (no rendering limit problem):** a searchable indented tree or icicle of FIBO domain → module → class (Protégé / FIBO Viewer pattern, OntoPlot compression), plus a KCE or RDF Digest "top-k key concepts" card. Compute the key-concept scores at release build time.
2. **Overview (static, precomputed):** a radial or icicle view of the module hierarchy with Holten-bundled cross-module restriction and usage edges. Layout and bundling are computed on the server per release and served as coordinates.
3. **Working view (ego network):** search → seed class → server-side SPARQL CONSTRUCT over Fuseki for the k-hop / DOI-top-N neighbourhood (N ≈ 50 to 300). Render as rich SVG/HTML node templates (Reactodia-style) with a layered layout for subClassOf, run in a Web Worker. Expand on demand, with a big-node confirm-or-sample guard and stable placement.
4. **ABox / FalkorDB projection (10^4 to 10^5):** a WebGL renderer (sigma.js + graphology, or Cosmos for GPU layout) fed with precomputed or GPU layout, label LOD, Leiden or community compound nodes, and a hard scene cap of about 10^4 nodes, in line with Bloom.
5. Budget against the measured 2025 figures: at about 30 fps, SVG is limited to about 2k sparse elements and fewer with labels. Pick the renderer by view, not one for the whole tool.

### Gaps
- I found no published SPARQL latency figures for k-hop CONSTRUCT extraction on FIBO-scale stores (Fuseki/TDB2). This needs a local measurement.
- I found no study of layout stability (mental-map preservation) across FIBO quarterly releases.
