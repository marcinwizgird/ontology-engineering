# Notations and View Types for OWL/RDF/SKOS/SHACL Ontology Visualization (state as of Oct 2026)

Method note: primary sources were read where possible (full text of the VOWL SWJ article and the Chowlk VOILA 2023 paper were extracted and read). Repository activity was checked through the GitHub REST API on 2026-10-20. `pushed_at` records the last push to any branch, which includes bot and dependency pushes, so it is an upper bound on activity and does not prove substantive maintenance. The API rate limit stopped the checks before Graffoo, shacl2plantuml, Protégé core, Bubastis and OWLDiff were covered.

## 1. VOWL: spec version, OWL coverage and omissions, WebVOWL / OWL2VOWL implementation

### Takeaway
VOWL 2 is the current and final spec version. It is a force-directed node-link notation that is TBox-only by design. It covers classes, object and datatype properties, domain/range, subclass, equivalence, disjointness, anonymous set operators, cardinalities and property characteristics. It explicitly lacks notation for named classes defined by set operators, the nesting order of set operators, custom data ranges, and enumerations such as oneOf. Its authors concede that large ontologies are "not yet sufficiently addressed". WebVOWL/OWL2VOWL (MIT) still receive pushes in 2026, but the canonical domain is lost.

### Cited Findings
- Two VOWL versions exist, both specified at purl.org/vowl/spec/. VOWL 1 integrated classes and individuals. VOWL 2 "focuses on the visual representation of classes, properties, and datatypes" (the TBox), and ABox information is optional, with individuals recommended for a linked sidebar — [Lohmann, Negru, Haag, Ertl, "Visualizing Ontologies with VOWL", Semantic Web Journal](https://www.semantic-web-journal.net/content/visualizing-ontologies-vowl-0)
- Graphical primitives: classes are circles, properties are lines carrying domain/range, property labels and datatypes are rectangles, and text carries labels and cardinalities. Circle size may encode the number of individuals (log or sqrt scaling is recommended). owl:Thing is drawn small and fixed-size. External classes (base IRI differs) get a dark-blue "external" style. Deprecated elements are grey, and the deprecated colour overrides the external colour by priority rules. Equivalent classes are merged into one node. Multi-edges between the same pair of classes are curved — [VOWL SWJ article](https://www.semantic-web-journal.net/content/visualizing-ontologies-vowl-0)
- Set operators (union, intersection, complement) are drawn as dashed nodes with Venn-diagram glyphs plus the symbols ∪ ∩ ¬. Disjointness also uses a Venn-like glyph. Cardinality and subclass notation was borrowed from UML. Global cardinalities and characteristics (functional, inverse functional, symmetric, etc.) appear as text annotations on properties — [VOWL SWJ article](https://www.semantic-web-journal.net/content/visualizing-ontologies-vowl-0)
- Omissions found with the OntoViBe benchmark:
  - No support for custom data ranges.
  - Set operators are specified only for anonymous classes ("no notation for named classes that are defined by these set operations exists").
  - Nesting direction is not shown: "a union including an intersection and an intersection including a union look the same".
  - An expert participant asked for restrictions such as enumerated individuals (oneOf), "currently not supported by VOWL".
  - Source: [VOWL SWJ article](https://www.semantic-web-journal.net/content/visualizing-ontologies-vowl-0)
- Scalability: "The visualization of large-scale ontologies with VOWL is an issue that has not yet been sufficiently addressed". The evaluation ontologies were "of relatively moderate size". The force-directed layout places nodes randomly on every render, which "prevents users from creating a 'mental map'" across sessions — [VOWL SWJ article](https://www.semantic-web-journal.net/content/visualizing-ontologies-vowl-0)
- WebVOWL filters for reducing graph size:
  - Disjointness is hidden by default and listed only in the sidebar.
  - Separate filters hide datatype properties, set operators and "solitary subclasses".
  - A degree-based collapsing slider removes low-degree classes first.
  - Output can be exported to SVG.
  - Source: [VOWL SWJ article](https://www.semantic-web-journal.net/content/visualizing-ontologies-vowl-0)
- Implementation: WebVOWL is a client-side JS/SVG app driven by a custom VOWL-JSON schema (classes, properties, datatypes, characteristics, annotations, metrics). A Java OWL2VOWL converter built on the OWL API produces the JSON. WebVOWL 0.4.0 is described as "a complete implementation of VOWL 2". ProtégéVOWL (a Protégé 4/5 plugin) "does not implement all visual elements" — [VOWL SWJ article](https://www.semantic-web-journal.net/content/visualizing-ontologies-vowl-0); the Protégé wiki also notes the plugin is incomplete and recommends WebVOWL — [Protégé wiki, Visualization](https://protegewiki.stanford.edu/wiki/Visualization)
- Evidence quality: three qualitative, counterbalanced within-subject comparative studies with lay or casual users, plus an interview with only five experienced ontology users (four had used Protégé). Experts found the set-operator notation (dashed border + Venn + symbol) a "visual overload". Three of the five said the displayed information was "almost too much". Some wanted colours to encode hierarchy depth — [VOWL SWJ article](https://www.semantic-web-journal.net/content/visualizing-ontologies-vowl-0). **Flag:** the evidence is qualitative, small-N, on moderate-size ontologies, and collected by the notation's own authors. It does not cover large ontologies such as FIBO.
- Maintenance: VisualDataWeb/WebVOWL is MIT-licensed, has about 1,014 stars and was last pushed 2026-06-04. OWL2VOWL is MIT, last pushed 2026-06-04. ProtegeVOWL is MIT, last pushed 2026-07-04. None is archived — [GitHub API, WebVOWL](https://api.github.com/repos/VisualDataWeb/WebVOWL), [OWL2VOWL](https://api.github.com/repos/VisualDataWeb/OWL2VOWL), [ProtegeVOWL](https://api.github.com/repos/VisualDataWeb/ProtegeVOWL). The README says the visualdataweb.org domain is no longer owned by the project and points to service.tib.eu/webvowl/. It also says the legacy Docker setup is broken (issue #212) and that no GitHub releases are published — [WebVOWL GitHub](https://github.com/VisualDataWeb/WebVOWL). Verified: vowl.visualdataweb.org/v2/ now 301-redirects to an unrelated domain (quickui.org), so spec links in older papers are dead — [vowl.visualdataweb.org/v2/](http://vowl.visualdataweb.org/v2/)
- A WebVOWL Editor exists for device-independent visual modelling (Wiens, Lohmann, Auer, ISWC 2018). It is cited in [Poveda-Villalón et al., VOILA 2023 (Chowlk)](https://ceur-ws.org/Vol-3508/paper2.pdf)

### Inferences
- For SIP, VOWL is a reasonable "overview / explain to domain experts" notation for small modules. It is unsuitable as the primary view for FIBO-scale TBoxes or for faithful display of complex class expressions (nested restrictions, named defined classes, oneOf, data ranges). SIP would need a textual (Manchester) fallback for those.
- Its VOWL-JSON schema is a practical, reusable interchange target. SIP could emit VOWL-JSON from rdflib without Java and so avoid an OWL2VOWL/OWL API dependency. The lack of Java in this environment makes that the realistic route.
- The random force layout should be replaced with deterministic or persisted layouts to preserve mental maps, a point the authors themselves raise.

### Gaps
- The VOWL 2 spec page itself could not be fetched (the domain was hijacked or redirects), so the construct-by-construct table, for example whether someValuesFrom/allValuesFrom get a dedicated glyph, was not verified from the spec. The TIB-hosted copy or the Wayback Machine should be checked.
- No commit messages were checked, so it is not known whether the 2026 WebVOWL/OWL2VOWL pushes are substantive or dependency bumps.

## 2. UML-style notations: OWLGrEd, ODM/UML profiles, Graffoo, Chowlk, Mermaid/ArchiMate style; how restrictions and class expressions are shown

### Takeaway
The UML-style notations differ mainly in how they render class expressions:
- OWLGrEd embeds Manchester-syntax text in class boxes. It is compact and complete, but less visual.
- Chowlk puts restriction tags on property arrows: (some), (all), (N1..N2), (eq). It uses circles for ∩/∪/≡/⊥ axioms and hexagons for oneOf.
- Graffoo draws restrictions as extra boxes.
- VOWL uses anonymous set-operator nodes and omits most restrictions.
None of them has published controlled user studies of a strength comparable to Fu et al. (see §4).

### Cited Findings
- **OWLGrEd** (Bārzdiņš, Bārzdiņš, Čerāns, Liepiņš, Sproģis, BIR 2010) is a UML-style graphical notation and editor for OWL 2 — [LU research portal](https://research.lu.lv/en/publications/owlgred-a-uml-style-graphical-notation-and-editor-for-owl-2/). It extends UML class diagrams rather than defining a UML profile. Optional Manchester-syntax encoding of class expressions inside class boxes avoids drawing many anonymous classes. Text conventions: "<" for subclass/subproperty, "=" for equivalence, "<>" for disjointness — [CEUR Vol-596 paper 05](https://ceur-ws.org/Vol-596/paper-05.pdf); [Čerāns et al., contextual verbalization, arXiv 1607.01490](https://arxiv.org/pdf/1607.01490). The Protégé wiki records that the OWL2UML plugin "has grown into the OWLGrEd project" — [Protégé wiki](https://protegewiki.stanford.edu/wiki/Visualization). The current site offers a free desktop editor with selectable entity types, auto-layout and image export. The copyright footer reads 2013–2026, and no version or licence is stated — [owlgred.lumii.lv](https://owlgred.lumii.lv/). The Chowlk authors criticise that, from its notation description, "it is not clear which OWL features are supported, e.g. imports, class equivalence, property equivalences, cardinality constraints" — [Chowlk VOILA 2023](https://ceur-ws.org/Vol-3508/paper2.pdf)
- **Graffoo** (Peroni et al.) has spec v1.0, dated 28 Oct 2013:
  - Classes are yellow rectangles with solid black borders.
  - Object properties are blue lines, with a solid circle at the domain and an arrow at the range.
  - Individuals are pink circles.
  - It covers datatypes, properties, individuals, ontologies and restrictions.
  - It is built on the yEd editor's standard library.
  - DiTTO converts Graffoo diagrams into OWL.
  - The paper is "Modelling OWL ontologies with Graffoo" (Falco, Gangemi, Peroni, Shotton, Vitali, 2014).
  - Sources: [Graffoo spec](https://essepuntato.it/graffoo/specification/); [Graffoo home](https://essepuntato.it/graffoo/); [DiTTO](https://essepuntato.it/ditto/)
  - No spec update after 1.0 was found.
- **Chowlk** (Poveda-Villalón, Chávez-Feria, Carulli-Pérez, García-Castro; first at ESWC 2022, notation paper at VOILA 2023):
  - Basis: the notation is based on the UML_Ont profile (NeOn), but binds its stereotypes to OWL, RDF(S) and some OWL 2 constructs, with more compact tags for property characteristics and axioms.
  - Blocks: dedicated blocks for namespace/prefix declarations and for ontology metadata, including owl:imports.
  - Classes and individuals: rectangles are classes, and an underlined URI marks an individual. Subclass is an empty-head arrow or an «rdfs:subClassOf» dashed arrow.
  - Axioms: anonymous classes are empty rectangles. Circles with logic operators represent ∩, ∪, ≡ and ⊥ axioms. A hexagon represents oneOf linked to individuals.
  - Restrictions: written as tags on the object-property arrow, or before the datatype property: (some), (all) and (N1..N2) with "N" meaning unbounded. They default to rdfs:subClassOf semantics, and the "(eq)" prefix makes them equivalence.
  - Source: [Chowlk VOILA 2023, CEUR Vol-3508](https://ceur-ws.org/Vol-3508/paper2.pdf). Note that the paper's text swaps the words ("(all) and (some) indicate existential and universal restrictions, respectively"), an apparent typo.
  - Tooling: drawn in diagrams.net with constrained template libraries (complete and lightweight). The XML export is converted to OWL by a web converter. The converter cannot be linked from online diagrams.net because of security constraints — [ESWC 2022 paper](https://2022.eswc-conferences.org/wp-content/uploads/2022/05/paper_90_Chavez-Feria_et_al.pdf); [public-lod mailing list, 2022](https://lists.w3.org/Archives/Public/public-lod/2022Feb/0023.html)
  - Adoption: ETSI SAREF extensions, W3C RML ontologies and WoT discovery, and EU projects (BIMERR, COGITO, BIM4EEB, etc.) — [Chowlk VOILA 2023](https://ceur-ws.org/Vol-3508/paper2.pdf)
  - Maintenance: oeg-upm/Chowlk is Apache-2.0, about 47 stars, last pushed 2025-04-11 — [GitHub API](https://api.github.com/repos/oeg-upm/Chowlk). It has slowed, and an unofficial PyPI fork exists — [PyPI chowlk-unofficial-fork](https://pypi.org/project/chowlk-unofficial-fork)
- Chowlk authors' critique of the others:
  - In WebVOWL it is hard to show many object properties between two classes, diagrams are less compact because datatype properties become separate nodes, and hierarchies cannot be tree-laid-out.
  - Graffoo also turns datatype properties into nodes and draws restrictions as extra boxes.
  - Both WebVOWL and Graffoo encode meaning in colour, which is lost in black-and-white printing or for colour-blind users. In Chowlk colour is non-semantic, but per-namespace colouring is advised.
  - Source: [Chowlk VOILA 2023](https://ceur-ws.org/Vol-3508/paper2.pdf). **Flag:** this is an author-interested comparison with no user evaluation, and the paper itself lists "detailed comparison ... in terms of capabilities, clarity" as future work.
- A systematic review of UML ↔ ontology formalisms analysed 66 works (Mkhinini, Labbani-Narsis, Nicolle, Computer Science Review 2020) — cited in [Chowlk VOILA 2023](https://ceur-ws.org/Vol-3508/paper2.pdf)

### Inferences
- For SIP's "model" stage, a Chowlk-like convention suits round-tripping a conceptual diagram to OWL: restriction tags on edges and operator circles. Since Mermaid classDiagram and PlantUML support edge labels and stereotypes, a Chowlk-flavoured Mermaid/PlantUML renderer generated from rdflib is plausible and dependency-light. This is my inference. I found no published Mermaid-for-OWL notation spec, and an ArchiMate-for-OWL convention was not found either.
- The OWLGrEd approach (Manchester text in boxes) is the most faithful way to show arbitrary nested class expressions, which FIBO uses heavily, without graph explosion.

### Gaps
- No primary source was found on a formal ODM (OMG Ontology Definition Metamodel) UML profile diagram in active tool use in 2026.
- No user-study comparisons between Chowlk, Graffoo and OWLGrEd were found.
- Graffoo's and OWLGrEd's repository activity and licences were not verified (rate limit, and the site states nothing).

## 3. Protégé visualization plugins (OWLViz, OntoGraf, Jambalaya, NavigOWL): 2026 status

### Takeaway
OWLViz (Graphviz-based asserted and inferred class hierarchy) is the only one with recent repository activity. OntoGraf's repository was last pushed in 2018. Jambalaya (Shrimp) and NavigOWL are Protégé 3.x-era plugins with no evidence of maintenance. All of them are effectively legacy for a Python/web platform.

### Cited Findings
- Protégé wiki visualization list: OWLViz "views and navigates asserted and inferred class hierarchies". OntoGraf offers interactive navigation of OWL relationships with multiple layouts and filters. Jambalaya visualizes Protégé-Frames and OWL ontologies using Shrimp. NavigOWL offers graph layouts supporting RDF/OWL. Other listed plugins include OWLPropViz, OntoViz (Graphviz), SOVA (full ontology including anonymous classes), TGViz (TouchGraph), Cloud Views, Matrix, PromptViz and LogDiffViz (version diffs), and OWL2UML → OWLGrEd. The page carries no compatibility or status information, and its last edit dates from 2007 — [Protégé wiki, Visualization](https://protegewiki.stanford.edu/wiki/Visualization)
- OntoGraf supports subclass, individual, domain/range object-property and equivalence relationships. The wiki lists releases only up to 1.0.1, around 2010 — [Protégé wiki OntoGraf](https://protegewiki.stanford.edu/wiki/Pr4_UG_rv_Cl_OntoGraf)
- GitHub: protegeproject/ontograf was last pushed 2018-05-27, has no licence metadata and about 23 stars. protegeproject/owlviz was last pushed 2026-09-29, has no licence metadata and about 48 stars — [GitHub API ontograf](https://api.github.com/repos/protegeproject/ontograf), [GitHub API owlviz](https://api.github.com/repos/protegeproject/owlviz)

### Inferences
- OWLViz requires a native Graphviz install. Neither OWLViz nor OntoGraf is reusable outside the Java Protégé desktop, so for SIP they are design references only: an asserted-vs-inferred hierarchy toggle (OWLViz) and filterable relationship types (OntoGraf).

### Gaps
- No source confirmed Jambalaya or NavigOWL compatibility with Protégé 5.6.x. Their repositories were not located, so they are presumed abandoned on the basis of absence of evidence.
- Whether the 2026 OWLViz push is substantive is unknown.

## 4. Generic view types and the ontology tasks they suit

### Takeaway
2D node-link diagrams dominate tools, but there is controlled evidence that indented lists are better for search and graphs better for information processing. Space-filling (treemap, sunburst, icicle, nested circles) and matrix views are used for hierarchy overview and dense mappings. Hyperbolic, Euler and Venn views remain niche. Most claims about view suitability beyond Fu et al. rest on surveys and tool papers rather than experiments.

### Cited Findings
- Survey (Dudáš, Lohmann, Svátek, Pavlov, Knowledge Engineering Review 33, e10, 2018): most tools use 2D node-link diagrams concentrating on class hierarchies. Visual variety and OWL 2 support are low, and supported tasks are often unclear. Key challenges are tool maturity, usability, and overview plus detail for large ontologies — [Cambridge KER](https://cambridge.org/core/journals/knowledge-engineering-review/article/ontology-visualization-methods-and-tools-a-survey-of-the-state-of-the-art/5EA8C64D7DF60A84F6D2B7B9A09B6E6A). An earlier EKAW 2014 "roadmapping" paper classified tools by use case and built a rule-based visualizer recommender — [Dudáš, Zamazal, Svátek EKAW 2014](https://kizi.vse.cz/wp-content/uploads/old/dudas_ekaw14.pdf). A 2024 paper summarises four high-level use cases: editing, learning, inspecting and sharing — [SciTePress 2024](https://scitepress.org/publishedPapers/2024/128559/pdf/index.html)
- Controlled evidence: Fu, Noy and Storey ran an eye-tracking study (Semantic Web 8(1), 2017) comparing indented lists and node-link graphs. Indented lists were more efficient for information search, and graphs for information processing — [IOS Press SW](https://content.iospress.com:443/articles/semantic-web/sw163); [SWJ PDF](https://www.semantic-web-journal.net/system/files/swj672.pdf). The earlier ISWC 2013 study "Indented tree or graph?" covered class-mapping evaluation, and a follow-up looked at indented lists on desktop and tablet — [SciTePress 2016](https://www.scitepress.org/Papers/2016/60531/)
- VOWL authors' related-work review: nested graph visualizations split hierarchies, and some tools show the class hierarchy as nested circles "similar to treemaps". CropCircles and Cluster Maps visualize individuals grouped by class. Graph visualization "has been confirmed in a comparative evaluation" as intuitive for structure, though the authors cite only that evaluation — [VOWL SWJ article](https://www.semantic-web-journal.net/content/visualizing-ontologies-vowl-0)
- Adjacency-matrix and cube views are used for dense alignment comparison (Alignment Cubes extends Matrix Cubes; see §6) — [ISWC 2017 paper 304](https://iswc2017.ai.wu.ac.at/paper-304/). The Protégé "Matrix" plugin gives spreadsheet views of existential fillers and relationships — [Protégé wiki](https://protegewiki.stanford.edu/wiki/Visualization)
- Euler/Venn: VOWL uses Venn glyphs only as icons for set operators and disjointness, not as extension diagrams. Experts found the combination overloaded — [VOWL SWJ article](https://www.semantic-web-journal.net/content/visualizing-ontologies-vowl-0)

### Inferences (task-to-view mapping; synthesis, not directly evidenced except where noted)
- Find or locate a class in a large hierarchy: indented tree with search (Fu et al. evidence). This should be SIP's default navigator for FIBO.
- Understand local relations of a class (domain/range, restrictions): an ego-centric node-link view, 1–2 hops, with Manchester text for complex expressions (Fu et al. favour graphs for processing).
- Size and shape overview of a module (where depth and breadth sit, individual counts): sunburst, icicle or treemap (used by SKOS Play and in the hierarchy literature; no controlled ontology study found).
- Dense many-to-many relationships (alignments, property usage across classes, diff matrices): adjacency matrix.
- Hyperbolic trees (e.g. older TGViz/OntoRama-style focus+context): no 2024–2026 tool evidence found, so they are a low priority.
- Euler/Venn extension diagrams: suit teaching and small expressions only.

### Gaps
- No controlled user study found comparing treemap, sunburst or icicle against indented trees specifically for OWL ontologies.
- No 2024–2026 survey updating Dudáš et al. 2018 was retrieved in full.

## 5. SKOS-specific views (VocBench, Skosmos, SKOS Play!)

### Takeaway
SKOS views are dominated by hierarchy browsers (Skosmos, VocBench) plus SKOS Play's printable indexes and D3 tree, icicle and sunburst-style visualizations. All three tools are actively maintained in 2026.

### Cited Findings
- SKOS Play outputs:
  - alphabetical indexes, hierarchical trees (static or unfoldable), translation tables, permuted/KWIC indexes and alignment tables;
  - clickable PDFs;
  - D3.js tree, "square" (icicle/partition-like) and "circle" (sunburst-like) visualizations, plus an autocomplete field.
  - No size limits are documented.
  - Source: [sparna-git/skos-play README](https://github.com/sparna-git/skos-play). Note that the square/circle chart identification is inferred from image filenames.
  - Repository: LGPL-3.0, last pushed 2026-07-24 — [GitHub API](https://api.github.com/repos/sparna-git/skos-play). The live service returned HTTP 503 on 2026-10-20 — [skos-play.sparna.fr](https://skos-play.sparna.fr/play/)
- Skosmos (NatLibFi): repository last pushed 2026-10-19 and actively maintained (licence reported as NOASSERTION by the API) — [GitHub API](https://api.github.com/repos/NatLibFi/Skosmos)

### Inferences
- For SIP's SKOS concept schemes: a concept hierarchy tree with broader/narrower and related as secondary links, an alphabetical/KWIC index, and an optional sunburst for overview. This mirrors Skosmos and SKOS Play.

### Gaps
- Skosmos 3 and VocBench 3 hierarchy/graph view details were not fetched in this session. The VocBench GitHub path guessed (VocBench/vocbench3) returned 404.

## 6. Visualizing alignments/mappings, diffs/versions and SHACL shapes

### Takeaway
- Alignments: matrix/cube and indented-tree side-by-side approaches, mainly research prototypes such as Alignment Cubes (ISWC 2017).
- Diffs: mostly textual or tabular (ROBOT diff in plain, pretty, Markdown and HTML Manchester; Bubastis; Widoco changelog). Graph-based diff visualizations are rare.
- SHACL: UML class-diagram style via PlantUML (SHACL Play Draw, shacl2plantuml).

### Cited Findings
- Alignment Cubes (Ivanova, Bach, Pietriga, Lambrix, ISWC 2017) extends Matrix Cubes to explore and compare multiple alignments interactively, including without a reference alignment. It goes beyond aggregate precision, recall and F-measure — [ISWC 2017 paper 304](https://iswc2017.ai.wu.ac.at/paper-304/); [LiU postprint](https://www.ida.liu.se/~patla00/publications/ISWC2017/ISWC17-postprint.pdf); [HAL](https://hal-universite-paris-saclay.archives-ouvertes.fr/LISN/hal-01827794v1)
- Fu et al. 2013 studied indented tree vs graph specifically for class-mapping evaluation — [SciTePress 2016 (follow-up citing it)](https://www.scitepress.org/Papers/2016/60531/)
- SKOS Play generates alignment tables for SKOS mappings — [skos-play README](https://github.com/sparna-git/skos-play)
- ROBOT diff formats:
  - plain: OWL Functional syntax with IRIs, with optional labels;
  - pretty: labels and CURIEs, with language priority;
  - html and markdown: Manchester-based.
  - It compares logical content and ignores serialisation differences. It has no graphical output.
  - Source: [ROBOT diff docs](https://robot.obolibrary.org/diff). ontodev/robot is BSD-3, last pushed 2026-10-07 — [GitHub API](https://api.github.com/repos/ontodev/robot)
- Bubastis (EBI) analyses two ontology versions to highlight logical changes at adjustable detail — [EBI Bubastis](https://www.ebi.ac.uk/efo/bubastis/). Widoco extends Bubastis to produce a changelog section in documentation — [Widoco README](https://github.com/dgarijo/Widoco)
- The Protégé-era diff visualizers PromptViz and LogDiffViz are listed on the Protégé wiki, and OWLDiff is listed as a plugin — [Protégé wiki](https://protegewiki.stanford.edu/wiki/Visualization)
- SHACL Play Draw (Sparna):
  - It generates PlantUML UML-style diagrams as SVG, PNG, TXT or HTML.
  - NodeShapes are boxes. Property shapes become attributes or arrows.
  - sh:node and sh:class link to shapes; sh:class links to the shape whose sh:targetClass matches, or creates a box for the class.
  - sh:or is resolved through its members. rdfs:subClassOf is drawn as bold grey links.
  - sh:order sorts properties, and owl:inverseOf merges opposing arrows.
  - A "hide data properties" option exists. Diagrams embed in the generated application-profile documentation.
  - Source: [SHACL Play Draw](https://shacl-play.sparna.fr/play/draw). Repository: LGPL-3.0, last pushed 2026-10-20 — [GitHub API](https://api.github.com/repos/sparna-git/shacl-play)
  - A 2020 list post questioned why subclass relations were omitted (since then added, per the page above) — [public-rdf-shapes 2020](https://lists.w3.org/Archives/Public/public-rdf-shapes/2020Nov/0001.html)
- shacl2plantuml (rosecky) is a CLI that generates PlantUML (.wsd) class diagrams from SHACL shapes plus an OWL ontology — [GitHub rosecky/shacl2plantuml](https://github.com/rosecky/shacl2plantuml)
- pyLODE 3.x has a `valpub` profile for SHACL shapes graphs, `vocpub` for SKOS and `ontpub` for OWL. It produces static HTML without diagrams — [pyLODE README](https://github.com/RDFLib/pyLODE)

### Inferences
- SIP could provide a semantic diff view that groups ROBOT/Bubastis-style axiom changes per entity and colours added and removed nodes in the ego graph. No mature open tool doing graph-overlay diffs was found, so this is a gap SIP could fill.
- For SHACL, a PlantUML or Mermaid class-diagram renderer is the de facto convention. It can be produced from rdflib without Java only if Mermaid (JS) is used. PlantUML needs Java, which is unavailable here.

### Gaps
- AlignmentVis was not located, so no sourced findings on it.
- OWLDiff and Bubastis repositories, licences and status were not verified.
- No evidence was found of user studies on diff visualizations.

## 7. Documentation generators that embed diagrams (LODE, Widoco, pyLODE, Ontospy)

### Takeaway
Widoco is the only mainstream generator that embeds an interactive diagram (WebVOWL, via `-webVowl`). It also uses LODE for the class and property sections and Bubastis for changelogs. pyLODE is deliberately diagram-free static HTML. LODE is XSLT-based HTML without diagrams. Ontospy generates HTML docs and is in maintenance mode. All four are active in 2026.

### Cited Findings
- Widoco:
  - It uses WebVOWL for visualization via the `-webVowl` flag and LODE for the documentation of classes and properties.
  - LODE visualization is unavailable with `-uniteSections`.
  - It extends Bubastis for changelogs. No Mermaid is mentioned.
  - The README references v1.4.24.
  - Source: [Widoco README](https://github.com/dgarijo/Widoco). Repository: Apache-2.0, last pushed 2026-10-19 — [GitHub API](https://api.github.com/repos/dgarijo/Widoco)
- pyLODE 3.1.0: profiles ontpub, vocpub, valpub and supermodel. It produces static HTML with "no JavaScript" and no diagrams. BSD-3, last pushed 2026-09-19 — [pyLODE README](https://github.com/RDFLib/pyLODE); [GitHub API](https://api.github.com/repos/RDFLib/pyLODE)
- LODE (Peroni): ISC licence, last pushed 2026-08-04 — [GitHub API](https://api.github.com/repos/essepuntato/LODE)
- Ontospy: generates HTML documentation out of the box. The maintainer has "little time", so work focuses on bug fixes. MIT, last pushed 2026-10-20 — [Ontospy README](https://github.com/lambdamusic/Ontospy); [GitHub API](https://api.github.com/repos/lambdamusic/Ontospy)

### Inferences
- pyLODE (Python, BSD, rdflib-based) fits SIP's dependency-light rule best for the publish stage. SIP would add its own diagrams (VOWL-JSON or Mermaid) because pyLODE ships none. Widoco brings WebVOWL but requires Java.

### Gaps
- Ontospy's D3 visualization types (tree, bubble, partition, etc.) were not confirmed from the current README. From memory, Ontospy has had a `viz` command with several D3 views, but this is unverified and should not be cited.
- The exact date of the latest Widoco release is unverified.
