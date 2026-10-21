# Ontology visualization: empirical evidence and evaluation methodology (for a SIP proof-of-concept visualization component)

Research date: 2026-10-20. Evidence-strength flags: **[STRONG]** = controlled experiment, n >= 30, quantitative; **[MODERATE]** = controlled, n of about 20 to 30, or a single study; **[WEAK]** = qualitative, n < 15, author-run, or only reported second-hand.

## Q1. What do the surveys (Katifori 2007, Dudas et al. 2018, Po/Bikakis et al. 2020, 2020-2026 work) establish?

### Takeaway
The surveys are taxonomies of tools and methods, not syntheses of effectiveness. They agree that 2D node-link views of class hierarchies dominate, and that the open problem is giving an overview of a large ontology while still offering details on demand. None reports pooled effect sizes. The only quantitative pooling found is an unpublished course meta-analysis (four studies), which found no reliable advantage for alternative visualizations over the Protege indented list.

### Cited Findings
- Katifori et al. (ACM CSUR 2007) review 34 ontology visualization tools in six categories: indented list; node-link and tree; zoomable; space-filling; focus+context or distortion; 3D information landscapes. 24 of the surveyed techniques use indented lists or graphs. — [Fu, Noy & Storey, SWJ (Related Work, summarising Katifori)](https://www.semantic-web-journal.net/system/files/swj861_0.pdf)
- Dudas, Lohmann, Svatek & Pavlov (KER vol. 33, e10, 2018) update the classification of methods and survey the available tools for visualization method, interaction technique and supported OWL constructs. Findings: most tools use 2D node-link visualizations focused on class hierarchies; colour and shape are used with little variation; OWL 2 support is limited; tasks and use cases are often vague. The main challenges are limited maturity and usability, and overview plus details-on-demand for large ontologies. The paper surveys tools; it is not a user study. — [Cambridge KER](https://cambridge.org/core/journals/knowledge-engineering-review/article/ontology-visualization-methods-and-tools-a-survey-of-the-state-of-the-art/5EA8C64D7DF60A84F6D2B7B9A09B6E6A); [MaxAPress mirror](https://www.maxapress.com/article/doi/10.1017/S0269888918000073)
- Po, Bikakis, Desimoni & Papastefanatos, *Linked Data Visualization: Techniques, Tools, and Big Data* (Morgan & Claypool, 2020, about 157 pp.). It covers LD visualization principles, tools, use cases and an empirical tool evaluation chapter that assesses usability under different scenarios. — [Springer](https://link.springer.com/978-3-031-79491-9); [W3C announcement](https://lists.w3.org/Archives/Public/public-semweb-ui/2020Apr/0000.html)
- A companion VOILA 2020 paper (Desimoni, Bikakis, Po, Papastefanatos) evaluates use cases over 10 LD visualization tools on DBpedia. It checks whether each tool has the functionality a task needs and whether the task can be completed. This is a feature or task walkthrough by the authors, not a study with participants. — [UNIMORE record](https://unimore.unifind.cineca.it/resource/item/260189) (details from the search snippet only; full text not read)
- An SLR on ontology *change* visualisation (SWJ) identifies 28 tools and methods, of which only 12 are still available. It notes a shift from showing individual changes to helping users understand overall evolution. — [SWJ 3622](https://www.semantic-web-journal.net/system/files/swj3622.pdf)
- A 2024 arXiv essay reviews KG visualization frameworks (2014 to September 2024) and KG-embedding visualization. The embedding approaches all project vectors with PCA, t-SNE or UMAP. — [arXiv 2412.05289](https://arxiv.org/html/2412.05289)
- Saghafi's UBC CPSC 547 course survey (2014, supervised in Munzner's course; **unpublished, not peer-reviewed**) found 21 ontology-visualization papers from 2003 to 2014. 11 of them had some empirical user evaluation. It meta-analysed four studies that compare an alternative visualization against Protege's baseline:
  - Katifori et al. 2006: TGViz vs Protege, accuracy, n=23, d=-0.49.
  - Motta et al. 2011: KC-Viz vs Protege, completion time, n=21, d=1.01; usability, d=0.26.
  - Garcia-Penalvo et al. 2012: OWL-VisMod vs Protege, accuracy, n=21, d=-0.14; usability, d=0.79.
  - Fu et al. 2014: node-link vs indented list, time, n=36, d=-1.32; accuracy, d=0.
  - Mean unbiased Cohen's d = 0.014, 95% CI -1.21 to 1.22. — [Saghafi 2014, UBC](https://www.cs.ubc.ca/~tmm/courses/547-14/projects/arash/report.pdf) **[WEAK as synthesis: student report, k=4, heterogeneous outcomes]**
- Generic graph-visualization evaluation surveys:
  - Burch et al. (IEEE Access 2021) classify empirical graph-vis studies into interpretation, memorability and creation. — [DOAJ](https://doaj.org/article/18cae1d0499b4e609a5bffba55723cd7)
  - Yoghourdjian et al. (Visual Informatics 2018) survey human-centred experiments on how node-link features affect visual complexity. They note that "large" depends on data complexity, visual complexity and technology. — [arXiv 1809.00270](https://arxiv.org/abs/1809.00270v1)

### Inferences
- No survey published 2018 to 2026 that I could find pools ontology-specific user studies. In practice the evidence base is a handful of primary studies (Q2).
- The Saghafi CI spans roughly -1.2 to +1.2 SD. Read it as "no evidence of a general advantage". It is not evidence of no effect. The signs suggest a consistent trade-off: node-link views tend to cost time or accuracy on lookup tasks and gain on satisfaction or usability ratings.

### Gaps
- The full texts of Katifori 2007 and Dudas 2018 were not re-read in this pass. The category counts and conclusions above come from abstracts and secondary citations.
- I found no peer-reviewed 2020 to 2026 survey dedicated to visual ontology *editing*, nor a KG-visualization survey with an evaluation meta-analysis. The arXiv/Scopus search was not exhaustive; a database search (Scopus: "ontology visualization" AND "user study", 2019 to 2026) is still needed.

## Q2. What do the primary user studies show (VOWL, Fu/Noy/Storey, Katifori, Chowlk, OWLGrEd, experts vs novices, eye tracking)?

### Takeaway
The best evidence is task-dependent. **Indented lists are faster for search and lookup. Graphs help local information processing and multiple inheritance. Accuracy differences are usually not significant** (Fu et al., n=36, students). Most other studies are qualitative, have 5 to 23 participants, or are author-run (VOWL). Chowlk and OWLGrEd have no published user study that I could find.

### Cited Findings
**Fu, Noy & Storey: indented list vs graph, ontology mapping evaluation, eye tracking (ISWC 2013 + SWJ vol. 8 no. 1)** **[STRONG-ish: n=36, but novices only]**
- Design: 36 participants, all undergraduate or graduate students (CS, biomedical, biochemistry, mechanical, electrical and software engineering). All were novices to ontologies and mapping. One-on-one sessions of about 2 hours with a tutorial. Each participant did 2 tasks, each with one ontology pair and one visualization, and order was varied. — [SWJ 861 PDF](https://www.semantic-web-journal.net/system/files/swj861_0.pdf)
- Task: judge the correctness of existing exact class mappings and add missing ones, using OAEI 2012 Conference ontologies (74 and 110 entities, depth up to 3 or 6, no multiple inheritance) and reduced BioMed ontologies (89 and 181 entities, depth up to 11 or 12, up to 4 multiple-inheritance cases). — [SWJ 861 PDF](https://www.semantic-web-journal.net/system/files/swj861_0.pdf)
- Results:
  - Indented lists: fewer fixations and saccades, smaller convex-hull area, shorter scanpaths, so more efficient search.
  - Graphs: shorter average fixation duration, so more efficient processing of the information found.
  - Task speed: faster with indented lists.
  - **Task accuracy: inconclusive.** Pupil dilation (workload): inconclusive.
  - All participants spent more time searching than processing, which the authors read as motivation for search support in any ontology visualization.
  - Correlations: saccade length vs fixation duration r=-0.291, p<.03; convex hull vs fixation count r=0.343, p<.01.
  - About 500 MB of Tobii gaze data. — [SWJ 861 PDF](https://www.semantic-web-journal.net/system/files/swj861_0.pdf); [SWJ abstract page](https://semantic-web-journal.net/node/861)
- Qualitative (from the ISWC 2013 paper, as summarised in SWJ): indented lists were seen as familiar, fast and easy, but confusing when multiple inheritance creates redundant nodes. Graphs were seen as connected, controllable and better for multiple inheritance, but "time-consuming, distracting and frustrating". — [SWJ 861 PDF](https://www.semantic-web-journal.net/system/files/swj861_0.pdf)
- Follow-up: Huynh & Fu (2016) compared indented lists on desktop vs tablet for class search. — [SciTePress](https://www.scitepress.org/Papers/2016/60531/) (details not read)

**VOWL (Lohmann, Negru, Haag, Ertl; SWJ 2016 "Visualizing Ontologies with VOWL")** **[WEAK]**
- Three *qualitative*, counterbalanced within-subject studies with lay or casual users. None of them was against Protege's class tree:
  1. Early VOWL vs UML class-diagram notation (ODM).
  2. ProtegeVOWL vs SOVA.
  3. WebVOWL vs SOVA and GrOWL.
  - Tasks were structure questions (e.g., "approximate number of visible classes?") and element questions (e.g., "which property is the inverse of X?"), plus comments.
  - Outcome: "lay users ... could solve most tasks well with VOWL", and preference "leaned toward VOWL for the majority".
  - Users asked for neighbour highlighting and search. Node duplication (owl:Thing, datatypes) and merging of equivalent classes drew mixed reactions. — [SWJ 1114 PDF](https://www.semantic-web-journal.net/system/files/swj1114.pdf)
- Sample sizes: an SWJ reviewer notes 6 and 5 participants in the first two studies and calls them qualitative and insufficiently described. — [SWJ review page](https://semantic-web-journal.net/node/892). A secondary source reports one VOWL study with six users in which "participants could solve most of the tasks correctly (84%)" (Lohmann et al. 2014). — [Saghafi 2014](https://www.cs.ubc.ca/~tmm/courses/547-14/projects/arash/report.pdf)
- Expert arm: think-aloud interviews with **5** experienced ontology users (4 had used Protege), 1 alone and 4 in pairs, with free exploration of WebVOWL 0.2.11 and ProtegeVOWL on FOAF, SIOC, MUTO and PersonasOnto. It was used to contrast lay and expert needs. — [SWJ 1114 PDF](https://www.semantic-web-journal.net/system/files/swj1114.pdf)
- The ODM-UML vs VOWL comparative user study (ACM, DOI 10.1145/2506182.2506192) reports "benefits and limitations raised by participants". I could not retrieve its sample size. — [Unpaywall record](https://unpaywall.org/10.1145%2F2506182.2506192)
- A Fraunhofer study compares Protege and the WebVOWL Editor on modelling tasks, recording completion time, errors and conceptual understanding. I could not retrieve its authors or n (access blocked). — [Fraunhofer Publica](https://publica.fraunhofer.de/handle/publica/403767)

**Katifori et al. 2006 (four Protege plugins: two indented-list, two node-link)** **[MODERATE/WEAK: "preliminary results"]**
- The task was retrieving information about entity *evolution* over time. The Protege class browser (indented list) gave higher accuracy. — [Saghafi 2014](https://www.cs.ubc.ca/~tmm/courses/547-14/projects/arash/report.pdf)
- Meta-analysis entry: TGViz vs Protege, n=23, accuracy d=-0.49 (favouring Protege). — [Saghafi 2014](https://www.cs.ubc.ca/~tmm/courses/547-14/projects/arash/report.pdf)
- Primary source: Katifori, Torou, Halatsis, Lepouras, Vassilakis, IEEE IV 2006, pp. 417-423. — citation only, [BibSonomy](https://www.bibsonomy.org/bibtex/e2f8918f01bcce75cfed41639d472cb1)

**Other Protege-baseline studies** (as reported by Saghafi 2014)
- Motta et al. 2011, KC-Viz vs OWLViz/Protege: 21 subjects; faster completion (d=1.01) and higher satisfaction (d=0.26). — [Saghafi 2014](https://www.cs.ubc.ca/~tmm/courses/547-14/projects/arash/report.pdf) **[MODERATE]**
- Garcia-Penalvo et al. 2012, OWL-VisMod vs Protege: n=21; accuracy d=-0.14, usability d=0.79. — [Saghafi 2014](https://www.cs.ubc.ca/~tmm/courses/547-14/projects/arash/report.pdf). A related JUCS 2011 paper evaluates OWL-VisMod with a user-centred, questionnaire approach (n not visible in the abstract). — [JUCS](https://www.jucs.org/jucs_17_9/usability_evaluation_of_a.html)
- Small usability studies: Ma et al. 2012, radial layout, n=19, scores between "useful" and "very useful"; Memoria-Mea wheel graph, n=6. — [Saghafi 2014](https://www.cs.ubc.ca/~tmm/courses/547-14/projects/arash/report.pdf) **[WEAK]**

**Chowlk (Chavez-Feria, Garcia-Castro, Poveda-Villalon, ESWC 2022)**
- **No user evaluation.** The authors write: "Because of the simplicity of the tool, we do not include user experience evaluation in this first version." The validation is a correctness test over 49 diagrams, all of which converted to valid ontologies, plus adoption evidence (H2020 projects BIMERR and COGITO, GitHub forks). — [ESWC 2022 paper](https://2022.eswc-conferences.org/wp-content/uploads/2022/05/paper_90_Chavez-Feria_et_al.pdf)

**OWLGrEd**
- I found no comprehension user study. It appears in criteria-based notation comparisons, not participant studies. — [SWJ review comment](https://semantic-web-journal.net/node/2515)

**Related comprehension studies (textual and visual notations)**
- Kuhn: 64 participants, Attempto Controlled English vs simplified Manchester OWL syntax. Diagrams were used as the evaluation instrument. — [SWJ](https://semantic-web-journal.net/node/167)
- ROWLTab (Protege plugin) evaluation: 12 graduate students modelling natural-language sentences in OWL. — [K-State PDF](https://www.cs.ksu.edu/~hitzler/pub2/2016-ROWL-Eval.pdf)

**Practitioner and expert evidence (KG, not OWL)**
- Li et al. (IEEE TVCG, VIS 2023): interviews with **19** KG practitioners, who fall into three personas: builders (need schema enforcers), analysts (need query builders with interim results) and consumers. For consumers they found a "lack of efficacy" of node-link diagrams; consumers need domain-specific views. — [arXiv 2304.01311](https://arxiv.org/abs/2304.01311v3)

### Inferences
- Defensible design claims for SIP:
  1. Default to an indented hierarchy with search for lookup tasks (find a class, find a superclass).
  2. Offer a local node-link view, an ego-network of 1 to 2 hops, for relationship comprehension and multiple inheritance.
  3. Always provide search and highlighting. Fu's finding that search dominated time, and VOWL participants' requests, both point to this.
  4. Do not assume node-link helps domain-expert consumers (Li et al.).
- No study shows a whole-ontology force-directed graph beating a tree on accuracy.

### Gaps
- No study found that directly compares domain experts with ontology engineers on the same tasks and ontology with adequate n. VOWL's 5-person expert interview is the closest.
- n for the ODM/VOWL and Fraunhofer Protege/WebVOWL-Editor studies could not be retrieved.
- I found no eye-tracking ontology study other than Fu et al. and its follow-up.
- Katifori 2006 primary numbers (accuracy rates, test statistics) were not read; the d=-0.49 is second-hand.

## Q3. Which tasks and metrics are used?

### Takeaway
Tasks fall into **search and lookup** (find class X, count classes, find inverse property), **structure and relationship comprehension** (superclass, domain/range, path), **mapping validation**, and **evolution or retrieval**. Metrics are almost always completion time and accuracy plus a satisfaction questionnaire. Eye tracking appears once; workload measures appear rarely and inconclusively.

### Cited Findings
- Fu et al.:
  - Tasks: mapping correctness and completeness.
  - Indirect metrics: speed, accuracy.
  - Eye-tracking metrics: fixation and saccade count, convex hull, scanpath length and duration, average fixation duration, search-to-process ratio, pupil dilation (workload), saccade angles (confidence).
  - Their research questions were framed as search efficiency, processing efficiency, cognitive workload, and speed and success. — [SWJ 861 PDF](https://www.semantic-web-journal.net/system/files/swj861_0.pdf)
- VOWL: general-structure questions ("approximate number of visible classes?") and element questions ("which property is the inverse of property X?"), plus subjective comments on overview, shapes and colours, comprehensibility or confusion, and perceived completeness. Expert arm: think-aloud. — [SWJ 1114 PDF](https://www.semantic-web-journal.net/system/files/swj1114.pdf)
- Katifori 2006: information retrieval about entity evolution; accuracy. — [Saghafi 2014](https://www.cs.ubc.ca/~tmm/courses/547-14/projects/arash/report.pdf)
- KC-Viz / OWL-VisMod: completion time, accuracy, usability or satisfaction score. — [Saghafi 2014](https://www.cs.ubc.ca/~tmm/courses/547-14/projects/arash/report.pdf)
- Fraunhofer Protege vs WebVOWL Editor: modelling tasks; completion time, errors, understanding of conceptual spaces, reflective questions. — [Fraunhofer Publica](https://publica.fraunhofer.de/handle/publica/403767)
- Generic graph task taxonomy (Lee, Plaisant, Parr, Fekete, Henry, BELIV 2006): complex tasks decompose into low-level tasks on graph objects in four groups (topology-based, attribute-based, browsing, overview). It adds graph-specific tasks such as "find adjacent nodes" to Amar et al.'s analytic tasks. — [Microsoft Research](https://www.microsoft.com/en-us/research/publication/task-taxonomy-graph-visualization/)
- Lam, Bertini, Isenberg, Plaisant & Carpendale, "Seven Guiding Scenarios for Information Visualization Evaluation" (2011), used as a methodological basis by Fu et al. — [cited in SWJ 861 references](https://www.semantic-web-journal.net/system/files/swj861_0.pdf)

### Inferences
- An ontology task battery can be grounded in Lee et al.'s taxonomy:
  - Topology: superclass or ancestors; path between classes; domain/range of a property.
  - Attribute: find classes with annotation X.
  - Browsing: follow a property.
  - Overview: estimate size, identify the main branches.
  - Ontology-specific additions: detect a modelling error (e.g., a cycle, a misplaced subclass, a domain/range clash); validate a mapping.
- SUS and NASA-TLX are not visible in the ontology studies I could read, which mostly use custom questionnaires. Using standard instruments would be an improvement and would allow comparison across studies.

### Gaps
- I found no ontology visualization study that reports SUS or NASA-TLX scores. The studies I read used custom questionnaires; some unread studies may use SUS.
- I found no study that uses error detection (finding modelling defects) as a visualization task with measured accuracy. It is a gap relevant to SIP's validate stage.

## Q4. What are the known weaknesses of this literature?

### Takeaway
The evidence is thin and biased. Samples are small (5 to 36, typically about 20). Participants are mostly students or novices. Ontologies are toy-sized (about 70 to 180 entities in the best study). Many evaluations are qualitative and run by the tool's authors, and outcome measures are heterogeneous. Effect-size reporting is rare.

### Cited Findings
- Largest controlled ontology-vis study found: n=36, all students and novices, ontologies of 74 to 181 entities, BioMed ontologies *reduced* from originals. — [SWJ 861 PDF](https://www.semantic-web-journal.net/system/files/swj861_0.pdf)
- VOWL: 6 and 5 participants, qualitative and "insufficiently described" per a reviewer. The expert arm had n=5. — [SWJ review](https://semantic-web-journal.net/node/892); [SWJ 1114 PDF](https://www.semantic-web-journal.net/system/files/swj1114.pdf)
- Of 21 ontology-vis papers from 2003 to 2014, only 11 had any user evaluation, "some ... qualitative user studies with limited number of participants". Only 4 were comparable enough to meta-analyse. — [Saghafi 2014](https://www.cs.ubc.ca/~tmm/courses/547-14/projects/arash/report.pdf)
- Chowlk shipped with no UX evaluation. — [ESWC 2022](https://2022.eswc-conferences.org/wp-content/uploads/2022/05/paper_90_Chavez-Feria_et_al.pdf)
- Dudas et al. flag vague task definitions and limited usability or maturity across tools. — [KER](https://cambridge.org/core/journals/knowledge-engineering-review/article/ontology-visualization-methods-and-tools-a-survey-of-the-state-of-the-art/5EA8C64D7DF60A84F6D2B7B9A09B6E6A)
- A 2017 requirements review (Proknow-C, 20 refs, 2007 to 2016) explicitly recommends user studies as future work. — [UFMG](https://repositorio.ufmg.br/handle/1843/62375)
- Fu et al. note limits of eye tracking: it misses peripheral vision and does not reveal liking or difficulty, so it must be combined with performance and verbal data. — [SWJ 861 PDF](https://www.semantic-web-journal.net/system/files/swj861_0.pdf)

### Inferences
- With d around 0.5 and a within-subjects design, a paired t-test needs about 34 participants for 80% power at alpha=.05 (standard power arithmetic, not from these sources). Most ontology studies are therefore underpowered for medium effects, and between-subject designs even more so.
- Results from toy ontologies with about 100 entities do not transfer to FIBO-scale ontologies (thousands of classes), which are SIP's test data. Scale must be an explicit factor.

### Gaps
- I found no study of visualization at 1,000 or more classes with human participants for OWL ontologies.

## Q5. How should rendering performance be benchmarked?

### Takeaway
There is no standard benchmark for web graph or ontology rendering. Published numbers are vendor- or author-run, on one machine, with differing graphs. A defensible PoC benchmark must define its own protocol: time-to-first-render, layout convergence time, sustained FPS during pan/zoom at stepped N, and peak memory, on fixed hardware with real ontology graphs. Munzner's algorithm-level validation (measure system time and memory, analyse complexity) supplies the rationale.

### Cited Findings
- Munzner's nested model (IEEE TVCG 2009) has four levels: domain characterisation, data/operation abstraction, encoding/interaction idiom, algorithm. Each has its own threat ("wrong problem", "wrong abstraction", "wrong idiom", "too slow") and validation methods. Algorithm level: measure system time and memory, analyse complexity. Idiom level: justify against alternatives, lab study measuring human time and errors. Domain level: observe target users. Deployment: measure adoption, qualitative result analysis. Upstream errors cascade downstream. — [Munzner 2009 paper page](https://www.cs.ubc.ca/labs/imager/tr/2009/NestedModel/); [Munzner IV09 slides](https://www.cs.ubc.ca/~tmm/talks/iv09/nestedmodel.pdf)
- The Nested Blocks and Guidelines model (Meyer, Sedlmair, Quinan, Munzner) refines the levels into blocks and guidelines. — [NBGM PDF](https://www.cs.ubc.ca/labs/imager/tr/2013/NBGM/nbgm.pdf)
- Cytoscape.js WebGL preview (2025, vendor numbers, M1 MacBook Pro / Chrome):
  - About 1,200 nodes and 16,000 edges: about 20 FPS with canvas, over 100 FPS with WebGL.
  - About 3,200 nodes and 68,000 edges: about 3 FPS with canvas. — [Cytoscape blog](https://blog.js.cytoscape.org/2025/01/13/webgl-preview/)
- Cytoscape's library comparison uses the same 104-node / 2,000-edge network for each library. Sigma.js shows a first frame quickly, but its force layout does not halt on its own and is stopped after 3 s. This illustrates that "time to first render" and "time to stable layout" are distinct metrics. — [GitHub js-graph-lib-comparison](https://github.com/cytoscape/js-graph-lib-comparison/blob/master/README.md)
- NetV.js (Visual Informatics 2021) claims interactive frame rates at up to 50k nodes and 1M edges, outperforming Sigma.js, D3, Cytoscape.js and Stardust.js. The comparison is self-reported. — [DOAJ](https://doaj.org/article/a199b80883cc47a1b6b53ac02ad185a2) **[WEAK: author benchmark]**
- A Leiden bachelor thesis (2019) measured initialisation time and FPS for D3, Ogma and Cytoscape. — [LIACS thesis](https://theses.liacs.nl/pdf/2018-2019-BlindeRJ.pdf)

### Inferences
- Proposed PoC performance protocol:
  - **Graphs:** real SIP data (FIBO modules, FIBO full) plus synthetic graphs at N = 100, 500, 1k, 5k, 10k, 50k nodes, with edge density matched to the ontology (subClassOf, plus object properties, plus annotations if shown).
  - **Metrics:**
    - Data-to-first-paint (ms).
    - Layout time to convergence: stopping criterion is mean node displacement below a threshold, or a fixed iteration cap; report both.
    - Median FPS and p5 FPS (1% low) during a scripted 10 s pan/zoom and during layout.
    - Interaction latency for expand-node and search-highlight (ms, p50 and p95).
    - Peak JS heap and GPU memory.
    - Server-side SPARQL or projection time, reported separately from client rendering.
  - **Procedure:** fixed hardware tiers (laptop iGPU, desktop dGPU), browser version pinned, 1 warm-up plus at least 5 measured runs, median and IQR reported, automated (e.g., Playwright plus `performance.now()` and requestAnimationFrame counters).
  - **Thresholds to state up front:** for example, at least 30 FPS interactive and under 100 ms interaction latency. These are conventional HCI targets, not taken from the sources above.

### Gaps
- I found no independent, peer-reviewed benchmark covering Sigma.js, Cytoscape.js (WebGL), G6, vis-network or WebVOWL under a common protocol. I found no WebVOWL-specific performance data.

## Q6. How can assisted or LLM-driven ontology exploration be evaluated?

### Takeaway
The evidence is very early and qualitative, and comes from KGs, not OWL ontologies. The key empirical signal is **over-trust**: helpful-looking visualizations made users, including experts, trust wrong LLM outputs. No controlled study of LLM-assisted *ontology* visualization was found. An evaluation must measure correctness *and* calibrated trust, not just preference.

### Cited Findings
- LinkQ (Li, Appleby, Alperin, Gomez, Suh; arXiv May 2025): an LLM turns natural-language questions into KG queries, with five visual mechanisms (LLM-KG state diagram, query editor with explanation, entity-relation ID table, query structure graph, interactive result graph). It was evaluated qualitatively with **14 practitioners**. Users, including KG experts, over-trusted outputs because of the "helpful" visualizations even when the LLM was wrong, and workflows varied with prior KG and LLM familiarity. No comparison condition. — [arXiv 2505.21512](https://arxiv.org/abs/2505.21512) **[WEAK: n=14, qualitative, preprint]**
- Li, Appleby & Suh (arXiv 2024): survey plus interviews with **20** KG and LLM experts. Concerns were keeping semantic intent in NL-to-query translation, hallucinated data, and the difficulty of a "perfect prompt". The result is a preliminary design roadmap. — [arXiv 2404.01425](https://www.arxiv.org/abs/2404.01425)
- Informal ChatGPT experiment generating Mermaid diagrams of DBpedia ontology classes (2023); not a controlled study. — [arXiv 2307.06917](https://arxiv.org/pdf/2307.06917)

### Inferences
- For SIP's agent-assisted exploration, use a within-subject design with three conditions: (a) visualization only, (b) visualization plus agent, (c) agent with deliberately seeded errors on some trials. Measure:
  - task accuracy and time;
  - **trust calibration**: the rate of accepting wrong agent answers, and the rate of rejecting correct ones;
  - whether users verified agent claims in the view (interaction logs);
  - NASA-TLX workload.
- Agent answers should be checked automatically against SPARQL ground truth over the Fuseki canonical graph. This gives an objective accuracy score independent of the user.

### Gaps
- No ontology-specific (OWL/SKOS) study of LLM-assisted visualization was found as of October 2026. No study reports SUS or TLX for LLM-assisted KG exploration.

## Q7. What evaluation protocol is defensible for the SIP proof-of-concept visualization component?

### Takeaway
Structure the evaluation by Munzner's nested model. Validate the algorithm level with the automated benchmark (Q5). Validate the idiom level with a small within-subject comparison against an indented-tree baseline on a standardized task battery, using real ontologies at two scales. Validate the domain level with think-aloud sessions with both ontology engineers and domain experts. State effect sizes with CIs, and say plainly that a PoC-scale study is formative, not confirmatory.

### Cited Findings
- Each nested level needs its own validation, and upstream errors invalidate downstream ones. — [Munzner 2009](https://www.cs.ubc.ca/labs/imager/tr/2009/NestedModel/)
- Baseline choice: Protege's indented list is the de facto baseline in prior work (4 of 4 meta-analysed studies). — [Saghafi 2014](https://www.cs.ubc.ca/~tmm/courses/547-14/projects/arash/report.pdf)
- Task-type dependence (search vs processing) means tasks must be stratified by type. — [Fu et al.](https://www.semantic-web-journal.net/system/files/swj861_0.pdf)
- Lay and expert users differ in needs (VOWL interviews), and KG consumers find node-link ineffective (Li et al.). — [SWJ 1114](https://www.semantic-web-journal.net/system/files/swj1114.pdf); [arXiv 2304.01311](https://arxiv.org/abs/2304.01311v3)

### Inferences
Proposed protocol (synthesis; not drawn from a single source):
1. **Algorithm level (automated, CI-run):** the benchmark in Q5 on FIBO and synthetic graphs, with pass/fail thresholds declared in advance.
2. **Idiom level (formative lab study):**
   - Within-subject design with 2 to 3 conditions: indented tree with search (baseline), SIP local node-link, SIP hybrid. Counterbalance with a Latin square, and use isomorphic task sets on 2 ontologies:
     - small: about 100 to 200 classes, e.g., an OAEI Conference ontology, which is comparable to Fu et al.;
     - large: a FIBO module of 1,000 or more classes.
   - Task battery of 12 to 16 tasks, stratified:
     - lookup (find class, find superclass);
     - relationship (domain/range, path between two classes, all subclasses incl. multiple inheritance);
     - overview (main branches, approximate size);
     - error detection (seeded defects);
     - mapping validation (accept or reject candidate alignments).
   - Metrics: accuracy (primary), time on correct trials, SUS per condition, NASA-TLX (raw) per condition, final preference ranking, interaction logs.
   - Sample: aim for at least 24 (power for d of about 0.6 within-subjects). If only 8 to 12 are feasible, pre-declare the study as formative and report descriptives, CIs and qualitative themes, not p-values.
   - Analysis: mixed-effects models (participant and task as random effects), effect sizes with 95% CIs.
3. **Domain level (think-aloud):** 5 to 8 ontology engineers and 5 to 8 domain experts (e.g., finance SMEs for FIBO) doing realistic review-gate tasks, analysed with thematic coding. This addresses the expert-vs-novice gap.
4. **Assisted exploration (if the agent is in scope):** the seeded-error trust-calibration design in Q6.
5. **Reporting:** pre-register tasks and hypotheses; publish the task set, ontologies and logs; flag participant profile (student or practitioner) and ontology size explicitly, since these are the literature's main validity threats.

### Gaps
- SUS and NASA-TLX norms specific to ontology tools do not exist in the sources reviewed, so comparison will be against generic SUS benchmarks only. Those norms were not sourced in this pass.
- I found no validated, reusable task battery for ontology visualization. The battery above would be a novel artefact and should be piloted (2 to 3 pilot participants) before use.
