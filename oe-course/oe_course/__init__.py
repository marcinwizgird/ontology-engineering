"""Shared framework for the graduate Ontology Engineering course.

Built around Keet, *Ontology Engineering* (2nd ed.), recast as a practice-first
graduate course: every concept in the book becomes something you run, measure,
and can be graded on.

Layers
------
=====================  =====================================================
:mod:`~oe_course.config`       environment, model ids, offline/live detection
:mod:`~oe_course.llm`          Anthropic clients + the offline simulators
:mod:`~oe_course.sparql`       one SPARQL API over Fuseki or in-memory rdflib
:mod:`~oe_course.ontology`     metrics, spectrum classification, defect scanning
:mod:`~oe_course.tools`        LangChain function tools + call logging
:mod:`~oe_course.agents`       single-loop agents and decomposed pipelines
:mod:`~oe_course.mdp`          agentic tasks as MDPs, solved exactly
:mod:`~oe_course.evaluation`   datasets, deterministic metrics, LLM judge, GEPA
:mod:`~oe_course.optimize`     DSPy/GEPA compilation and before/after reporting
:mod:`~oe_course.skills`       versioned capability bundles and skill cards
:mod:`~oe_course.selfimprove`  failure mining with a held-out promotion gate
:mod:`~oe_course.programs`     the worked reference task (ontology triage)
=====================  =====================================================

Everything runs with no API key and no Docker; see :func:`oe_course.config.offline`.
"""

from oe_course import config

__version__ = "0.1.0"
__all__ = ["config", "describe_environment"]


def describe_environment() -> dict:
    """A one-line health check the notebooks print in their setup cell."""
    return config.describe_environment()
