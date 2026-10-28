"""Virtual knowledge graph: R2RML mappings between the ontology and relational data.

The Ontop / R2RML role in the platform, kept dependency-light:

* ``source``      relational sources (sqlite3 by default, DuckDB when installed),
                  schema introspection, read-only SELECTs with row limits;
* ``r2rml``       the W3C R2RML model, parsed from / serialised to the project's
                  ``mappings`` named graph;
* ``suggest``     scored mapping proposals from schema + ontology (never applied);
* ``patterns``    the IRI policy (EntityDefs) and mapping patterns P01-P08: compile
                  parameters to triples maps, lift maps back (exactly, or "custom");
* ``spec``        the YAML mapping spec (the SPARQL-2-SQL PoC's format), import/export;
* ``validate``    static mapping checks, coverage, impact of ontology refactorings;
* ``materialise`` an R2RML processor with per-triple provenance;
* ``query``       SPARQL over mapped data + the (staged) ontology with RDFS-style
                  entailment, or an optional external Ontop endpoint.

Writes to the mappings graph are built as change sets by ``platform.py``; nothing in
this package writes to the store.
"""
