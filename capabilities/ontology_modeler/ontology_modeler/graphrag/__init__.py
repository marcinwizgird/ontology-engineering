"""GraphRAG over a projected ontology: retrieval funnel, LangChain tools, and the agent.

    python -m ontology_modeler.graphrag --graph-name fibo selftest
    python -m ontology_modeler.graphrag --graph-name fibo ask "what is a demand deposit account?"

The retriever is usable on its own -- it is a plain read-only client over the FalkorDB
projection -- and the agent is a thin loop on top of it.
"""

from .retriever import Anchor, ConceptCard, GraphRagRetriever
from .tools import build_tools
from .agent import SYSTEM_PROMPT, ask, build_agent, selftest, trace

__all__ = [
    "GraphRagRetriever", "Anchor", "ConceptCard",
    "build_tools", "build_agent", "ask", "trace", "selftest", "SYSTEM_PROMPT",
]
