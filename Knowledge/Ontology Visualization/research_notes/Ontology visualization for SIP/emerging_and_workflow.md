# Emerging and engineering-workflow-oriented directions in ontology and KG visualization (2022-2026)

Scope note: these notes cover capabilities beyond static diagrams that matter to an agent-assisted ontology engineering platform (SIP), where agents stage changes, validators accept them, reasoning and validation produce findings, and competency questions (CQs) act as tests. They are current as of October 2026, based on about 25 searches and fetches. Maturity labels used below: **Maintained product** (vendor-supported, documented), **Maintained OSS** (active repo or releases), **Research prototype** (paper and demo, unclear maintenance), **Marketing claim** (vendor statement not backed by docs I could verify).

## 1. LLM-assisted visual exploration (NL to view or subgraph, LLM explanations, LLM-generated diagrams, OntoChat, copilots)

### Takeaway
In commercial tools, LLMs are mostly used to turn natural language into a query (NL to SPARQL or Cypher) whose answer is shown in a chat, table or dashboard. I found no documented vendor feature that turns natural language into a curated *visual view* of an ontology, such as "show me how Loan relates to Party" rendered as a diagram, and none that has an LLM explain a diagram. LLM-generated Mermaid or PlantUML from ontologies appears only in ad-hoc experiments. OntoChat is the main research system, and it targets requirements and CQs rather than visualization.

### Cited Findings
**Commercial tools**
- **GraphDB "Talk to Your Graph" (TTYG).** It was originally bound to OpenAI's Assistants API and lets you define an agent over a GraphDB repository. It combines vector retrieval (the Similarity plugin) with SPARQL querying. Version 2.0, in GraphDB 10.8, is described as "a no-code showcase" of features exposed as APIs on the Graphwise platform. — [Graphwise blog, TTYG 2.0](https://graphwise.ai/blog/talk-to-your-graph-2-0-a-partners-view/); [Ontotext news, GraphDB 10.8](https://www.ontotext.com/company/news/graphdb-10-8-brings-multi-method-querying-to-graph-rag/)
- Before GraphDB 11.1, all GraphDB AI features depended on the OpenAI Assistant API. Version 11.1 added more providers, including locally hosted models. — [Graphwise](https://graphwise.ai/?p=241711) (search snippet; the official GraphDB docs page was not retrieved)
- A separate Python package, `ttyg`, does NL querying over GraphDB using LangChain agents. It is not the same thing as the in-product feature. — [PyPI ttyg](https://pypi.org/project/ttyg/)
- **metaphactory 5.5 (2 October 2024)** launched a *beta* conversational interface. It holds contextual LLM conversations that "generate, refine, and run structured queries" and answer unstructured questions with RAG. Its NL2SPARQL component uses type-based entity disambiguation. The same release added a visual ontology editor with batch creation of classes, relations and attributes, and diagrams that move between instances along with the ontology. — [metaphactory 5.5 release](https://metaphactory.com/metaphactory-5-5)
- **Stardog Voicebox** is an LLM conversational layer that turns NL questions into graph queries. Stardog also markets it as a "knowledge engineer" that builds classes and relationships from plain-language prompts. VentureBeat reports it runs on an ensemble of fine-tuned open-source-based models. A Databricks case study says Stardog chose an in-house model approach after finding OpenAI output insufficient for complex queries. Stardog's own claim that answers are "free of hallucination" is a **marketing claim**. — [Stardog product](https://stardog.com/product); [VentureBeat](https://venturebeat.com/ai/stardog-launches-voicebox-an-llm-powered-layer-to-query-enterprise-data); [Databricks customer story](https://www.databricks.com/customers/stardog); [Stardog docs, Voicebox](https://cooper.stardog.com/docs/s/development-integration/applications-voicebox)
- **Neo4j Bloom / Explore.** Search uses a "near-natural language" grammar built from labels, relationship types and property keys, plus parameterised Cypher "search phrases". This is a deterministic grammar, not an LLM. — [Bloom search bar docs](https://neo4j.com/docs/bloom-user-guide/current/bloom-visual-tour/search-bar/); [Aura Explore search bar](https://neo4j.com/docs/aura/explore/explore-visual-tour/search-bar/)
- **Neo4j Aura console** got a "GenAI co-pilot" (announced September 2024) as a unifying hub to "administer, manage, ingest, model, and visualize data" in natural language. This comes from a press release, and I did not verify its visualization-specific behaviour in the docs. — [Neo4j press release](https://neo4j.com/press-releases/neo4j-aura-update/)
- **NeoDash Text2Cypher extension.** It started in NeoDash 2.3 (2023, OpenAI only). The commercial version supports OpenAI, Azure OpenAI and AWS Bedrock, and a per-report toggle switches between writing Cypher and writing English. The Labs version is unsupported, and Neo4j now points users to Aura Dashboards. — [NeoDash commercial docs](https://www.neo4j.com/docs/neodash-commercial/current/user-guide/extensions/natural-language-queries); [NeoDash Labs 2.4 docs](https://www.neo4j.com/labs/neodash/2.4/user-guide/extensions/natural-language-queries/); [Neo4j blog, NeoDash 2.3](https://neo4j.com/blog/developer/neodash-graph-dashboards-llm-powered/)
- Neo4j's own Text2Cypher paper notes that LLMs "often struggle to capture complex nuances, resulting in incomplete or incorrect outputs." — [arXiv 2412.10064](https://arxiv.org/html/2412.10064v1)

**Research**
- **OntoChat** (Zhang et al., arXiv 2403.05921, ESWC 2024 LLMs-for-KE track) is a conversational framework for requirement elicitation, analysis and *testing*. It helps users write user stories, extracts CQs, and was evaluated by rebuilding the Music Meta Ontology. The code is on GitHub (King-s-Knowledge-Graph-Lab/OntoChat). — [arXiv 2403.05921](https://arxiv.org/abs/2403.05921v1); [ESWC 2024 special track](https://2024.eswc-conferences.org/special-track-llms-for-ke/)
- The OntoChat follow-up (Zhao et al., arXiv 2408.15256, AAAI Spring Symposium) found that users struggled to write effective prompts. It introduced "participatory prompting" templates (persona, goals, scenarios, sample data, resources) with GPT-4o, then converted the resulting user stories to CQs. — [arXiv 2408.15256](https://arxiv.org/html/2408.15256v3); [AAAI-SS](https://ojs.aaai.org/index.php/AAAI-SS/article/view/31799)
- **LLM-generated Mermaid from ontologies.** Meyer et al. ("LLM-assisted Knowledge Graph Engineering: Experiments with ChatGPT", arXiv 2307.06917) prompted ChatGPT for a Mermaid diagram of DBpedia's main classes. The result was a subClassOf tree that used only two distinct properties as edges, a modest outcome. — [arXiv 2307.06917](https://arxiv.org/pdf/2307.06917)
- A deterministic, non-LLM baseline exists: Shimizu et al. generate schema diagrams programmatically from OWL and report they outperform VOWL and OWLGrEd. — [Wright State CORE Scholar](https://corescholar.libraries.wright.edu/cse/748)

### Inferences
- For SIP, "natural language to view" is best built as NL to SPARQL or Cypher subgraph query, followed by a deterministic layout. This matches what vendors actually ship (query generation, then rendering) and keeps the visual output reproducible. LLM-authored Mermaid is unreliable at ontology scale and is better kept to small explanatory snippets.
- None of the vendor chat features I found treats the result as a *staged change* to be reviewed. Stardog's "build classes from prompts" is the closest, and its governance path is undocumented in what I found.
- OntoChat is the research system most directly aligned with "CQs as tests", but it is a requirements and CQ tool with no visual layer.

### Gaps
- I did not find the official GraphDB documentation page for TTYG, or any confirmation that TTYG renders graph visualizations rather than text and tables.
- I found no peer-reviewed KG-exploration copilot (2023-2026) that produces interactive subgraph views from natural language and comes with a user evaluation. One may exist but did not surface.
- I found no tool that generates natural-language explanations *of a diagram*.

## 2. Visual (diagrammatic) ontology editing and round-trip (Chowlk, OWLGrEd, WebVOWL Editor, Graphol/Eddy, Ontodia/Reactodia, diagrams.net)

### Takeaway
Diagram-first authoring is mature for one-way generation, diagram to OWL (Chowlk, Eddy). True bidirectional sync, where the diagram and the text model stay consistent after edits on either side and layout persists across regenerations, is rare. The most practical patterns are: the diagram as a source artifact converted to OWL (Chowlk); a dedicated diagram format that stores layout and exports OWL (Eddy/Graphol); or a canvas-based editor over a triple store that stores diagrams as separate artifacts (metaphactory, Reactodia).

### Cited Findings
- **Chowlk** (UPM OEG; ESWC 2022, Chávez-Feria, García-Castro, Poveda-Villalón) has three parts: a UML-based notation, diagrams.net templates, and a converter from diagrams.net XML to OWL. It is available as a web app (chowlk.linkeddata.es) and as an API that returns Turtle. Its authors explicitly chose *not* to build a graphical editor, aiming instead for a smoother path from conceptualization to a first implementation. The notation was published at VOILA 2023 and has been adopted by standardisation-body ontologies. It is Apache-2.0 licensed, with about 25 GitHub stars, and its last push was about a year ago, so maintenance is uncertain. Tutorials ran at ECAI 2024 and in CEUR Vol-3882. — [ESWC 2022 paper](https://2022.eswc-conferences.org/wp-content/uploads/2022/05/paper_90_Chavez-Feria_et_al.pdf); [science.ecosyste.ms](https://science.ecosyste.ms/projects/6370); [ECAI 2024 tutorial](https://ecai2024.eu/programme/tutorials/boosting-ontology-conceptualization-with-chowlk); [CEUR Vol-3882 tutorial](https://ceur-ws.org/Vol-3882/tutorial-2.pdf)
- **Graphol/Eddy** (Sapienza DASI-lab; Lembo, Pantaleone, Santarelli, Savo, IJCAI-16). Graphol is a DL visual language inspired by ER diagrams. Eddy draws OWL 2 ontologies as Graphol diagrams, exports standard OWL 2, and runs *design-time syntax validation*, colour-coding invalid expressions as you draw. Grapholscape is a companion web *viewer* (search, filter, per-element OWL 2 translation) that points users to Eddy for editing. An earlier pipeline drew Graphol in yEd and translated it to OWL functional syntax. The Graphol specification is licensed CC BY-NC-ND 4.0, which restricts commercial reuse. — [IJCAI-16 paper](https://cs.unibg.it/savo/papers/LPSS-IJCAI-16.pdf); [Grapholscape npm](https://www.npmjs.org/package/grapholscape); [Sapienza research page](https://research.uniroma1.it/node/48108)
- **OWLGrEd** (University of Latvia) extends UML class diagrams with optional Manchester syntax for class expressions. It offers automatic layout algorithms, graphical refactoring and Protégé interoperability. A VOILA 2016 paper describes manual fine-tuning of the generated layout to produce documentation-ready diagrams, plus an option framework and plug-ins. The W3C wiki entry was last modified in 2012, so check current maintenance. — [OWLED 2010 paper](https://ceur-ws.org/Vol-596/paper-05.pdf); [VOILA 2016 paper](https://ceur-ws.org/Vol-1704/paper13.pdf); [W3C wiki](https://www.w3.org/2001/sw/wiki/OWLGrEd)
- **WebVOWL Editor** (Wiens, Lohmann, Auer, ISWC 2018) is open-source visual ontology editing focused on device independence, visual modelling, and guidance to avoid common modelling mistakes. It supports only a *subset* of OWL constructs chosen with domain experts. VOWL itself uses a force-directed layout (ProtégéVOWL, WebVOWL). — [Fraunhofer publica](https://publica.fraunhofer.de/handle/publica/407769); [VOWL, SWJ](https://journals.sagepub.com/doi/full/10.3233/SW-150200)
- **Ontodia lineage.** metaphactory 3.0 listed beta "visual graph authoring with Sputniq Explorer (former Ontodia)". metaphactory 4.7 added visual *instance* authoring with its graph component, and 5.5 added a visual ontology editor whose diagrams travel with the ontology on import and export. — [metaphactory 3.0](https://metaphacts.com/metaphactory-3-0); [metaphactory 4.7](https://metaphacts.com/metaphactory-4-7); [metaphactory 5.5](https://metaphactory.com/metaphactory-5-5)
- **Reactodia** (`@reactodia/workspace`) is an LGPL-2.1+ TypeScript library forked from Ontodia, for exploring, visualizing and *making changes to* data as an interactive graph over pluggable data sources. — [npm @reactodia/workspace](https://www.npmjs.org/package/@reactodia/workspace)
- **VisGraph** (MaterialDigital data portal) is a third-party RDF and ontology editor built on the Reactodia canvas. It supports node and link editing and OWL-RL reasoning, and visually distinguishes inferred knowledge from asserted. — [MaterialDigital data portal](https://dataportal.material-digital.de/en/dataset/visgraph-interactive-rdf-ontology-canvas)

### Inferences
- **Layout persistence.** Eddy (in its own diagram files), metaphactory (diagrams as artifacts exported with the ontology) and diagrams.net/Chowlk (the XML file is the source) all keep layout *separately* from the OWL. None of the sources describes automatic re-sync of a hand-tuned layout when the OWL changes underneath it. For SIP, layout should be a separate, versioned artifact keyed by IRIs, reconciled against the canonical graph in Fuseki: new IRIs get auto-placed, deleted IRIs are flagged.
- Chowlk's model, diagram to converter to Turtle, maps neatly onto "agent proposes a staged change". A diagram-derived Turtle delta could be submitted as a staged commit and validated before acceptance.
- The Ontodia, Reactodia and VisGraph lineage is the most reusable OSS base for a canvas that both explores and edits, and that marks inferred knowledge, in a web UI.

### Gaps
- I did not verify current maintenance or release activity for Eddy, OWLGrEd or the WebVOWL Editor in 2024-2026.
- I found no source describing *text to diagram* re-sync, meaning edits made in Turtle or Protégé reflected back into an existing hand-laid-out diagram, for any of these tools.
- I found no evidence that metaphacts maintains Reactodia. The fork relationship is confirmed, but organisational ownership is not.

## 3. Visualizing reasoning (inferred vs asserted, unsatisfiable classes, justifications)

### Takeaway
Justification computation is mature (Kalyanpur, Horridge), and Protégé shows inferred hierarchies and explanation panels. Dedicated *visual* explanation tools remain research prototypes, with Evonne (TU Dresden, 2023) the strongest recent one. Showing inferred and asserted knowledge distinctly on a graph canvas is now found in smaller OSS tools such as VisGraph.

### Cited Findings
- **Evonne** (Méndez et al., Computer Graphics Forum 2023) is a visual tool for explaining OWL reasoning consequences and supporting interactive debugging of unwanted consequences. It offers multiple coordinated views and layout modes, colour-coded cross-view highlighting, and "what if" comparison of how removing axioms would change entailments. A qualitative study with 16 logic experts was positive. — [Eurographics digital library](https://diglib.eg.org:443/handle/10.1111/cgf14730); [TU Dresden PDF](https://mt.inf.tu-dresden.de/cnt/uploads/Mendez2023-Evonne.pdf)
- Foundational work: Kalyanpur et al., "Finding all justifications of OWL DL entailments", gives algorithms for computing all justifications, which are essential for debugging unsatisfiable classes. Horridge and colleagues' "justificatory structure" work analyses how multiple justifications relate and identifies *root* unsatisfiable classes in large ontologies. — [Manchester, finding all justifications](https://research.manchester.ac.uk/en/publications/finding-all-justifications-of-owl-dl-entailments/); [Manchester, justificatory structure](https://research.manchester.ac.uk/en/publications/the-justificatory-structure-of-owl-ontologies/)
- Historical precedent: Swoop (2005) marked unsatisfiable classes in red and gave plain-language clash explanations, which made dependencies between unsatisfiable classes visible. — [W3C public-owl-dev, 2005](https://lists.w3.org/Archives/Public/public-owl-dev/2005AprJun/0008.html)
- Research has examined whether *diagrammatic* justifications reduce errors in finding unsatisfiable concepts (Napier). I saw only the abstract-level framing. — [Napier repository](https://napier-repository.worktribe.com/OutputFile/822596)
- VisGraph (Reactodia-based) runs OWL-RL reasoning with visual differentiation of inferred knowledge. — [MaterialDigital data portal](https://dataportal.material-digital.de/en/dataset/visgraph-interactive-rdf-ontology-canvas)

### Inferences
- SIP uses owlrl (OWL 2 RL, with no HermiT or Pellet because there is no Java). It therefore cannot compute DL justifications natively. A practical substitute is to record rule-firing provenance for each inferred triple from owlrl, or to compute minimal axiom subsets by deletion testing (as Evonne's "what if" view does), and then render them as an Evonne-style proof graph.
- An "asserted / inferred / unsatisfiable" tri-state style (for example solid, dashed and red outline) is a well-precedented, low-cost overlay for any SIP diagram.

### Gaps
- I did not verify Evonne's code availability or maintenance status.
- I did not fetch Protégé explanation-view documentation. Its current behaviour (the explanation workbench plugin) comes from background knowledge and should be confirmed.
- I found no 2024-2026 work on LLM-generated natural-language paraphrases of justifications, although the topic is plausible.

## 4. Overlays for quality and validation findings, provenance, and change states (OOPS!, SHACL reports, VocBench validation, ROBOT/Git diffs)

### Takeaway
Quality and validation tools emit *lists* or *RDF reports* (OOPS! pitfalls with severities, SHACL validation graphs, metaphactory's SHACL quality checks), and change workflows emit *diffs* or *accept/reject queues* (VocBench validation, ROBOT diff as Markdown or HTML in GitHub PRs). I found no maintained tool that overlays these findings or change states directly onto an ontology diagram. That integration is an open opportunity.

### Cited Findings
- **OOPS!** (UPM) takes an ontology URI or pasted OWL and returns a list of pitfalls, the elements affected, and a severity (critical, important, minor). It has a web UI and a RESTful service. Its catalogue groups 41 pitfalls into structural, functional and usability-profiling dimensions, with 48 methods detecting 33 of them. — [SWJ OOPS! paper](https://www.semantic-web-journal.net/node/989); [UPM thesis](https://tesis.biblioteca.upm.es/tesis/8205); [DCMI LD4PE](https://ld4pe.dublincore.org/learning_resource/oops-ontology-pitfall-scanner/)
- A SHACL validation engine produces a validation report that is itself an RDF graph. ShapeUML is a UML-style notation for visualizing *shapes*, not reports. Shapes have also been rendered with PlantUML. I found no dedicated SHACL *report* visualizer. — [SHACL, Wikipedia](https://en.wikipedia.org/wiki/SHACL); [ShapeUML spec](https://w3id.org/imec/unshacled/spec/shape-uml/20210118); [W3C semantic-web list, Francart 2020](https://lists.w3.org/Archives/Public/semantic-web/2020Nov/0029.html)
- **metaphactory 5.5** runs data-quality checks as standard SHACL rules with a default best-practice rule set. It monitors the quality of ontologies and vocabularies, including those edited outside the platform, with severity levels, and adds an event bus that emits lifecycle notifications such as review requests. — [metaphactory 5.5](https://metaphactory.com/metaphactory-5-5)
- **VocBench 3** supports proposing terms and *validating* them (accept or reject). Version 6.0 added "term blacklisting": terms proposed in rejected actions go to a blacklist pool. In version 8.0, any user who performed an action can reject it during validation. — [VocBench tips](https://vocbench.uniroma2.it/doc/tipsntricks); [VB3 v6.0 announcement](https://lists.w3.org/Archives/Public/semantic-web/2019Jun/0190.html); [VB3 v8.0 announcement](https://lists.w3.org/Archives/Public/public-lod/2020Jul/0023.html); [VB3 SWJ paper](https://semantic-web-journal.net/content/vocbench-3-collaborative-semantic-web-editor-ontologies-thesauri-and-lexicons-1)
- **ROBOT diff** supports `plain` (OWL functional syntax), `pretty` (labels and CURIEs), and `markdown` and `html` formats based on Manchester syntax. — [ROBOT diff docs](https://robot.obolibrary.org/diff)
- The ODK v1.3.1 release (June 2022) synced an "ontology diff GitHub action" for creating diffs on ontology PRs into ODK setups. — [ODK v1.3.1 release](https://github.com/INCATools/ontology-development-kit/releases/tag/v1.3.1)
- A caveat for diff-based review: OWLAPI and ROBOT serializer upgrades "will likely result in large diffs", so the advice is to save once with the new version first. Kendall (2024) recommends consistent serialization for usable diffs and points to axiomatic diff via ROBOT. — [ROBOT releases](https://github.com/ontodev/robot/releases); [W3C semantic-web list, Kendall 2024](https://lists.w3.org/Archives/Public/semantic-web/2024Sep/0033.html)

### Inferences
- SIP's staged-commit model already has the data needed for an overlay: the staged delta (added and removed axioms), validator findings (SHACL report focus nodes, OOPS!-style pitfall elements, SIP's own check catalogue), and reasoning results. A diagram overlay keyed by IRI, with badges for severity and green/red/amber for added/removed/modified, would bring together what VocBench (queue), ROBOT (textual diff) and metaphactory (SHACL dashboard) each do separately.
- Axiom-level diffs (ROBOT markdown or HTML on Manchester syntax) are more review-friendly than triple or line diffs and are robust to serialization noise. They are a good basis for a "proposed vs stable" review view.

### Gaps
- I found no maintained tool that renders SHACL validation results on a graph, or OOPS! pitfalls on a diagram. This is worth flagging as a gap in the market, not just in this research.
- I did not inspect how the ODK diff action formats PR comments, or whether any GitHub renderer visualizes OWL diffs graphically.
- I found no source on provenance visualization (PROV-O overlays) specific to ontology editors.

## 5. CQ coverage visualization, mapping (R2RML/RML) visualization, ontology-to-database mapping views

### Takeaway
CQ-coverage *measurement* is an active 2024-2026 research area, with LLM-generated CQs, SPARQL tests and coverage metrics. *Visualizing* coverage, for example highlighting which classes and properties CQs exercise, does not appear as a tool feature in any source I found. For mapping visualization, the RMLEditor and MapVOWL work is the principal graph-based approach, while newer tools such as Matey (a YARRRML IDE) and GRAPE are text-centric.

### Cited Findings
- **CQGen-MAS** (AAMAS 2026 extended abstract) defines coverage through semantic relevance (each CQ's SPARQL references only ontology concepts) and conceptual coverage across the CQ set. Uncovered concepts drive a generate-validate-expand loop. It reports recall on simple CQs of about 78-89% across four ontologies, beating the LLM4KE and RETROFIT-CQs baselines. — [AAMAS 2026](https://ifaamas.org/Proceedings/aamas2026/pdfs/RRYE6579.pdf)
- **GrOIL** (arXiv 2608.22135, 2026) generated 300 CQ-answer pairs over 10 contracts, wrote SPARQL for each against the induced ontology, and used an LLM judge (Qwen3-30B), reaching about 91% overall accuracy (0.73-1.00 per contract). — [arXiv 2608.22135](https://arxiv.org/pdf/2608.22135)
- **Bench4KE** (arXiv 2505.24554) benchmarks automated CQ generation and reviews earlier CQ validation tools such as OntologyTest and CQChecker, which measure answer accuracy and coverage. — [arXiv 2505.24554](https://arxiv.org/html/2505.24554v3)
- **ESWC 2024 paper 268** tests whether LLMs can write SPARQL tests from an ontology and a CQ, and finds performance depends on ontology characteristics and LLM settings. — [ESWC 2024 paper 268](https://2024.eswc-conferences.org/wp-content/uploads/2024/04/ESWC_2024_paper_268.pdf)
- Alharbi et al. argue that CQ benchmark comparisons are hampered by differing tasks, datasets and measures. Metrics are therefore not comparable across papers. — [CEUR Vol-3953](https://ceur-ws.org/Vol-3953/369.pdf)
- **RMLEditor** (Heyvaert et al., ESWC 2016) is a graph-based visual UI for defining mappings. **MapVOWL and RMLEditor** (JWS 2018) added a visual notation for mapping rules, handling of large visualizations, and display of raw data fractions. In user studies, the visual notation was preferred over writing the mapping language directly, and graph-based visualization was preferred over the form-based RMLx editor. — [Verborgh, ESWC 2016](https://ruben.verborgh.org/publications/heyvaert_eswc_2016/); [Verborgh, JWS 2018](https://ruben.verborgh.org/publications/heyvaert_jws_2018/)
- **Matey** (2025 paper) is a web IDE for YARRRML with syntax highlighting and panels for sources, mappings and outputs. It is text-focused, not graph-based. **GRAPE** is a newer OSS prototype that combines a textual RML abstraction with RDF metadata. — [CEUR Vol-3999](https://ceur-ws.org/Vol-3999/paper3.pdf); [CEUR Vol-4245](https://ceur-ws.org/Vol-4245/paper5.pdf)

### Inferences
- SIP treats CQs as tests, so a coverage overlay is a natural and apparently novel feature. It would colour classes and properties by how many passing or failing CQ SPARQL tests touch them, computed by parsing each CQ query's IRIs, which mirrors CQGen-MAS's "semantic relevance" check. Uncovered elements become prompts for the scoping or requirements agent.
- For mappings, the evidence (JWS 2018 user studies) favours graph-based views for authoring. The 2024-2026 tooling trend, however, is text IDEs with side panels (Matey). A side-by-side view, mapping text on one side and a graph of source columns to ontology terms on the other, combines both.

### Gaps
- I found no tool that visualizes CQ coverage on an ontology diagram.
- I did not verify whether the RMLEditor is still maintained or publicly available.
- I did not research ontology-to-database mapping views in Ontop or other VKG tools. This overlaps with the NL2Q/Ontop PoC and could be a follow-up.

## 6. Linked views / coordinated multiple views (CMV) in ontology tools

### Takeaway
Coordinated multiple views appear mainly in research prototypes (Evonne's cross-view highlighting) and in established editors' tree, detail and graph panes (Grapholscape's element details with OWL translation, metaphactory's linked components). I found little 2022-2026 literature specifically evaluating coordinated views for ontology engineering.

### Cited Findings
- Evonne combines multiple views with colour-coded cross-view highlighting for reasoning explanations, linking proof and ontology views. — [Eurographics digital library](https://diglib.eg.org:443/handle/10.1111/cgf14730)
- Grapholscape links a diagram to per-element details and the OWL 2 translation of a selected element, with search and filtering. — [Grapholscape npm](https://www.npmjs.org/package/grapholscape)
- The RMLEditor shows raw data fractions alongside the mapping graph, a form of linked data and mapping views. Matey uses linked panels for sources, mappings and outputs. — [Verborgh, JWS 2018](https://ruben.verborgh.org/publications/heyvaert_jws_2018/); [CEUR Vol-3999](https://ceur-ws.org/Vol-3999/paper3.pdf)

### Inferences
- For SIP, the most valuable coordination is across *workflow artifacts* rather than across visual encodings. Selecting a class should highlight it in the staged diff, in validator findings, in the CQ tests that touch it, and in the justification graph. Each source above does one slice of this; none does all of it.

### Gaps
- I did not search VOILA 2022-2025 proceedings systematically for CMV studies, so a targeted pass may find more.
- I did not verify Protégé's or WebProtégé's current multi-view coordination (for example linked class hierarchy and graph views) in 2024-2026 releases.
