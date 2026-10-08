"""ShaclEngine: pyshacl over the submission with a supplied or house-rule shapes graph.

Each ``sh:ValidationResult`` becomes one result record; the detectors map them to
findings. A crashing shapes graph is reported, never read as a pass (the S1b check SHC-09
will turn it into its own finding).
"""

from __future__ import annotations

from dataclasses import dataclass

from rdflib import BNode, Graph, Literal
from rdflib.namespace import RDF

from .vocab import SH, local_name, named_owners

SEVERITY_MAP = {SH.Violation: None, SH.Warning: "minor", SH.Info: "info"}
"""``None`` keeps the catalogue severity of the check (major for SHC-02 and SHC-08)."""


@dataclass
class ShaclResult:
    focus: str
    path: str | None
    value: str | None
    shape: str
    component: str
    sh_severity: str
    message: str


def _render(term, graph: Graph | None = None) -> str | None:
    """Render a term without blank-node ids (they differ between runs, which would break
    the determinism contract): a blank node is named by its owning entity when it has one."""
    if term is None:
        return None
    if isinstance(term, BNode):
        owners = named_owners(graph, term) if graph is not None else []
        return f"{owners[0]} (anonymous part)" if owners else "_:anonymous"
    if isinstance(term, Literal):
        return term.n3()
    return str(term)


def _shape_ref(shapes: Graph, shape) -> str:
    if shape is None:
        return ""
    name = shapes.value(shape, SH.name)
    if name is not None:
        return str(name)
    if not isinstance(shape, BNode):
        return str(shape)
    parent = next(iter(sorted(shapes.subjects(SH.property, shape), key=str)), None)
    path = shapes.value(shape, SH.path)
    prefix = _shape_ref(shapes, parent) if parent is not None else "shape"
    return f"{prefix} / property {local_name(path) if path is not None else '?'}"


def validate(data: Graph, shapes: Graph) -> tuple[bool, list[ShaclResult]]:
    from pyshacl import validate as pyshacl_validate
    conforms, report, _ = pyshacl_validate(
        data, shacl_graph=shapes, inference="none", advanced=True, abort_on_first=False,
        allow_warnings=False, meta_shacl=False)
    results = []
    # only the report's own sh:result nodes: pyshacl also types the nested sh:detail
    # results as sh:ValidationResult, which would double-count a violation
    top = [r for rep in report.subjects(RDF.type, SH.ValidationReport)
           for r in report.objects(rep, SH.result)]
    for r in top:
        sev = report.value(r, SH.resultSeverity)
        msg = report.value(r, SH.resultMessage)
        shape = report.value(r, SH.sourceShape)
        results.append(ShaclResult(
            focus=_render(report.value(r, SH.focusNode), data) or "",
            path=_render(report.value(r, SH.resultPath)),
            value=_render(report.value(r, SH.value), data),
            shape=_shape_ref(shapes, shape),
            component=local_name(report.value(r, SH.sourceConstraintComponent) or ""),
            sh_severity=local_name(sev) if sev is not None else "Violation",
            message=str(msg) if msg is not None else ""))
    results.sort(key=lambda x: (x.focus, x.path or "", x.component, x.value or "", x.message))
    return bool(conforms), results


def severity_for(result: ShaclResult) -> str | None:
    return SEVERITY_MAP.get(SH[result.sh_severity])
