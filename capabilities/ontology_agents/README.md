# Ontology Agents

The agents of the Knowledge Graph Agentic Platform that act on ontologies. Each agent has
a deterministic engine as its source of truth and a DSPy-optimised agentic layer, and is
specified in SysML v2 before it is implemented.

| agent | status | purpose |
|---|---|---|
| [validation_agent](validation_agent) | S0 (specification) | reasoning, SHACL and 131 custom checks; root causes, verified repairs, policy verdict; staged into DSPy optimisation and gated self-evolution |
