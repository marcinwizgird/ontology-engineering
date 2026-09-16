"""Render SysML diagrams from the parsed models in ``models/*.sysml``.

Five SysML diagram kinds, each emitted twice:

* **SVG**, hand-rendered here with a small layered-layout engine. No external renderer,
  no toolchain to install, and it is the artifact that survives being opened years later.
* **Mermaid**, for reviewing a change inline in a pull request or an IDE.

    bdd   Block Definition   part defs, composition, specialisation
    ibd   Internal Block     parts of one block and the connections between them
    req   Requirement        requirements, what satisfies them, what verifies them
    act   Activity           an action def, its sub-actions, and their succession
    stm   State Machine      a state def and its transitions

Both renderers read the same `Model`, so a diagram cannot disagree with its model
without the build failing first.
"""

from __future__ import annotations

import html
import textwrap
from dataclasses import dataclass, field

from sysml_model import Element, Model

# --------------------------------------------------------------------------- #
# Palette. One hue per SysML element kind, light and saturated pair per hue, so a
# reader can tell a requirement from a block without reading either.
# --------------------------------------------------------------------------- #

PALETTE = {
    "block":       ("#eef3fb", "#4a6fa5", "#1d3557"),
    "abstract":    ("#f5f7fa", "#8fa3bf", "#41506b"),
    "external":    ("#f2f2f2", "#9a9a9a", "#555555"),
    "requirement": ("#fdf4ec", "#c07a34", "#7a4a15"),
    "verification":("#fbeef0", "#b5545f", "#78303a"),
    "constraint":  ("#f4f0fa", "#7a5ea8", "#46326b"),
    "action":      ("#eefaf1", "#4f9d69", "#256341"),
    "state":       ("#e8f6f6", "#3f8e8e", "#1f5757"),
    "port":        ("#fffdf0", "#b09a3a", "#6d5e18"),
    "variant":     ("#f7f0fa", "#9a5ea8", "#5d316b"),
}

FONT = ("ui-sans-serif, -apple-system, 'Segoe UI', Roboto, "
        "'Helvetica Neue', Arial, sans-serif")
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

CHAR_W_TITLE = 7.25      # ~12.5px semibold
CHAR_W_BODY = 6.05       # ~10.5px regular


@dataclass
class Node:
    id: str
    title: str
    stereotype: str = ""
    lines: list[str] = field(default_factory=list)
    kind: str = "block"
    note: str = ""
    # filled in by layout
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    layer: int = 0

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


@dataclass
class Edge:
    src: str
    dst: str
    label: str = ""
    style: str = "solid"          # solid | dashed
    head: str = "open"            # open | closed | diamond | none
    hierarchy: bool = True        # counted when assigning layers


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #

H_GAP = 34
V_GAP = 78
PAD_X = 34
PAD_Y = 86
MAX_WIDTH = 1500


def _measure(node: Node) -> None:
    title_w = len(node.title) * CHAR_W_TITLE + 30
    stereo_w = len(node.stereotype) * CHAR_W_BODY + 30
    body_w = max((len(line) * CHAR_W_BODY for line in node.lines), default=0) + 26
    node.w = max(150.0, min(330.0, max(title_w, stereo_w, body_w)))
    header = 26 if node.stereotype else 0
    node.h = 30 + header + (len(node.lines) * 15) + (10 if node.lines else 0)


def _assign_layers(nodes: dict[str, Node], edges: list[Edge]) -> None:
    """Longest-path layering over hierarchy edges; parents sit above children."""
    incoming: dict[str, list[str]] = {nid: [] for nid in nodes}
    for edge in edges:
        if edge.hierarchy and edge.src in nodes and edge.dst in nodes:
            incoming[edge.dst].append(edge.src)

    memo: dict[str, int] = {}

    def depth(nid: str, seen: frozenset) -> int:
        if nid in memo:
            return memo[nid]
        if nid in seen:
            return 0                      # a cycle: stop rather than recurse forever
        parents = incoming.get(nid, [])
        value = 0 if not parents else 1 + max(
            depth(p, seen | {nid}) for p in parents)
        memo[nid] = value
        return value

    for nid in nodes:
        nodes[nid].layer = depth(nid, frozenset())


def _place(nodes: dict[str, Node], edges: list[Edge]) -> tuple[float, float]:
    _assign_layers(nodes, edges)
    for node in nodes.values():
        _measure(node)

    by_layer: dict[int, list[Node]] = {}
    for node in nodes.values():
        by_layer.setdefault(node.layer, []).append(node)

    # Order a layer by the mean position of its parents, so edges cross less often.
    parents: dict[str, list[str]] = {nid: [] for nid in nodes}
    for edge in edges:
        if edge.hierarchy and edge.src in nodes and edge.dst in nodes:
            parents[edge.dst].append(edge.src)

    order: dict[str, float] = {}
    y = PAD_Y
    width = 0.0
    for layer in sorted(by_layer):
        row = by_layer[layer]
        row.sort(key=lambda n: (
            sum(order.get(p, 0.0) for p in parents[n.id]) / len(parents[n.id])
            if parents[n.id] else 0.0,
            n.title.lower()))

        # Wrap a long row so the canvas stays a sensible shape.
        lines: list[list[Node]] = [[]]
        running = PAD_X
        for node in row:
            if running + node.w > MAX_WIDTH and lines[-1]:
                lines.append([])
                running = PAD_X
            lines[-1].append(node)
            running += node.w + H_GAP

        for sub in lines:
            total = sum(n.w for n in sub) + H_GAP * (len(sub) - 1)
            x = max(PAD_X, (MAX_WIDTH - total) / 2)
            tallest = 0.0
            for node in sub:
                node.x, node.y = x, y
                order[node.id] = x + node.w / 2
                x += node.w + H_GAP
                tallest = max(tallest, node.h)
            width = max(width, x)
            y += tallest + V_GAP
    return width + PAD_X, y - V_GAP + PAD_Y / 2


# --------------------------------------------------------------------------- #
# SVG
# --------------------------------------------------------------------------- #

def _defs() -> str:
    markers = []
    for name, colour in (("open", "#5a6b82"), ("closed", "#4a6fa5"),
                         ("dashed", "#9a5ea8"), ("verify", "#b5545f"),
                         ("satisfy", "#c07a34"), ("flow", "#4f9d69")):
        markers.append(
            f'<marker id="arrow-{name}" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{colour}"/></marker>')
    markers.append(
        '<marker id="diamond" viewBox="0 0 12 10" refX="11" refY="5" '
        'markerWidth="11" markerHeight="9" orient="auto-start-reverse">'
        '<path d="M 0 5 L 6 0 L 12 5 L 6 10 z" fill="#4a6fa5"/></marker>')
    markers.append(
        '<marker id="triangle" viewBox="0 0 12 12" refX="11" refY="6" '
        'markerWidth="10" markerHeight="10" orient="auto-start-reverse">'
        '<path d="M 0 0 L 12 6 L 0 12 z" fill="#ffffff" stroke="#4a6fa5" '
        'stroke-width="1.4"/></marker>')
    return "<defs>" + "".join(markers) + "</defs>"


_ARROW = {"open": "arrow-open", "closed": "triangle", "diamond": "diamond",
          "flow": "arrow-flow", "satisfy": "arrow-satisfy", "verify": "arrow-verify",
          "none": None}


def _edge_geometry(a: Node, b: Node) -> tuple[str, tuple[float, float], tuple[float, float]]:
    """A cubic from the edge of `a` to the edge of `b`, plus its two endpoints.

    The endpoints are returned because the label belongs at the curve's midpoint, not at
    the midpoint between the two node *centres*. For an edge spanning more than one layer
    those are different points, and the second one lands inside whatever box sits in
    between -- which is how edge labels end up printed on top of unrelated blocks.
    """
    if abs(a.cy - b.cy) < 4:
        x1, y1 = (a.x + a.w, a.cy) if a.cx < b.cx else (a.x, a.cy)
        x2, y2 = (b.x, b.cy) if a.cx < b.cx else (b.x + b.w, b.cy)
        mid = (x1 + x2) / 2
        path = f"M {x1:.1f} {y1:.1f} C {mid:.1f} {y1:.1f} {mid:.1f} {y2:.1f} {x2:.1f} {y2:.1f}"
        return path, (x1, y1), (x2, y2)
    if a.cy < b.cy:
        x1, y1, x2, y2 = a.cx, a.y + a.h, b.cx, b.y
    else:
        x1, y1, x2, y2 = a.cx, a.y, b.cx, b.y + b.h
    mid = (y1 + y2) / 2
    path = f"M {x1:.1f} {y1:.1f} C {x1:.1f} {mid:.1f} {x2:.1f} {mid:.1f} {x2:.1f} {y2:.1f}"
    return path, (x1, y1), (x2, y2)


def _label_spot(p1: tuple[float, float], p2: tuple[float, float], text_w: float,
                boxes: list[Node]) -> tuple[float, float] | None:
    """Where to put an edge label, or None if there is nowhere clear to put it.

    The curve's midpoint first; then small offsets along the edge; then give up. A label
    that cannot be placed without covering a block is better dropped -- the edge still
    carries its meaning through colour and arrowhead, and a legible diagram with one
    unlabelled edge beats a cluttered one.
    """
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    candidates = [(0, 0), (0, -17), (0, 17), (0, -32), (0, 32),
                  (text_w * 0.6, 0), (-text_w * 0.6, 0),
                  (text_w * 0.6, -17), (-text_w * 0.6, -17),
                  (text_w * 0.6, 17), (-text_w * 0.6, 17)]
    for dx, dy in candidates:
        x, y = mx + dx, my + dy
        rect = (x - text_w / 2, y - 9, text_w, 15)
        if not any(_rects_overlap(rect, (n.x, n.y, n.w, n.h)) for n in boxes):
            return x, y
    return None


def _rects_overlap(a: tuple[float, float, float, float],
                   b: tuple[float, float, float, float]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def render_svg(nodes: list[Node], edges: list[Edge], title: str,
               subtitle: str = "", legend: list[tuple[str, str]] | None = None) -> str:
    index = {n.id: n for n in nodes}
    edges = [e for e in edges if e.src in index and e.dst in index and e.src != e.dst]
    width, height = _place(index, edges)
    width = max(width, 720.0)
    if legend:
        height += 46

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
        f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'font-family="{FONT}">',
        _defs(),
        f'<rect width="{width:.0f}" height="{height:.0f}" fill="#ffffff"/>',
        f'<text x="{PAD_X}" y="38" font-size="19" font-weight="650" fill="#1d2430">'
        f'{html.escape(title)}</text>',
    ]
    if subtitle:
        out.append(f'<text x="{PAD_X}" y="60" font-size="12" fill="#6b7686">'
                   f'{html.escape(subtitle)}</text>')

    for edge in edges:
        a, b = index[edge.src], index[edge.dst]
        colour = {"satisfy": "#c07a34", "verify": "#b5545f", "flow": "#4f9d69"}.get(
            edge.head, "#7d8ba1" if edge.style == "dashed" else "#5a6b82")
        dash = ' stroke-dasharray="5 4"' if edge.style == "dashed" else ""
        marker = _ARROW.get(edge.head)
        marker_attr = f' marker-end="url(#{marker})"' if marker else ""
        path, p1, p2 = _edge_geometry(a, b)
        out.append(f'<path d="{path}" fill="none" stroke="{colour}" '
                   f'stroke-width="1.5"{dash}{marker_attr}/>')
        if edge.label:
            text_w = len(edge.label) * 5.6 + 10
            spot = _label_spot(p1, p2, text_w, nodes)
            if spot:
                mx, my = spot
                out.append(f'<rect x="{mx - text_w / 2:.1f}" y="{my - 9:.1f}" '
                           f'width="{text_w:.1f}" height="15" rx="7" fill="#ffffff" '
                           f'fill-opacity="0.92"/>')
                out.append(f'<text x="{mx:.1f}" y="{my + 2:.1f}" font-size="10" '
                           f'text-anchor="middle" fill="{colour}">'
                           f'{html.escape(edge.label)}</text>')

    for node in nodes:
        fill, stroke, ink = PALETTE.get(node.kind, PALETTE["block"])
        out.append(f'<rect x="{node.x:.1f}" y="{node.y:.1f}" width="{node.w:.1f}" '
                   f'height="{node.h:.1f}" rx="8" fill="{fill}" stroke="{stroke}" '
                   f'stroke-width="1.4"/>')
        text_y = node.y + 20
        if node.stereotype:
            out.append(f'<text x="{node.cx:.1f}" y="{text_y:.1f}" font-size="10" '
                       f'text-anchor="middle" fill="{stroke}" font-style="italic">'
                       f'{html.escape(node.stereotype)}</text>')
            text_y += 17
        weight = "600" if not node.kind == "abstract" else "500"
        style = ' font-style="italic"' if node.kind == "abstract" else ""
        out.append(f'<text x="{node.cx:.1f}" y="{text_y:.1f}" font-size="12.5" '
                   f'font-weight="{weight}" text-anchor="middle" fill="{ink}"{style}>'
                   f'{html.escape(node.title)}</text>')
        if node.lines:
            divider = text_y + 8
            out.append(f'<line x1="{node.x + 8:.1f}" y1="{divider:.1f}" '
                       f'x2="{node.x + node.w - 8:.1f}" y2="{divider:.1f}" '
                       f'stroke="{stroke}" stroke-opacity="0.35"/>')
            line_y = divider + 15
            for line in node.lines:
                out.append(f'<text x="{node.x + 11:.1f}" y="{line_y:.1f}" '
                           f'font-size="10.5" fill="{ink}" fill-opacity="0.85" '
                           f'font-family="{MONO}">{html.escape(line)}</text>')
                line_y += 15

    if legend:
        y = height - 22
        x = PAD_X
        for label, kind in legend:
            fill, stroke, ink = PALETTE.get(kind, PALETTE["block"])
            out.append(f'<rect x="{x}" y="{y - 10}" width="15" height="12" rx="3" '
                       f'fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>')
            out.append(f'<text x="{x + 21}" y="{y}" font-size="11" fill="#4a5566">'
                       f'{html.escape(label)}</text>')
            x += 30 + len(label) * 6.2
    out.append("</svg>")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Diagram builders
# --------------------------------------------------------------------------- #

MAX_ATTR_CHARS = 42


def _attr_lines(element: Element, limit: int = 5) -> list[str]:
    """One compartment line per attribute, elided rather than hard-cut.

    A default that does not fit is dropped entirely instead of being sliced mid-token:
    `fulltextFields: String[1..*] = ("name", "d` reads as a rendering bug, whereas the
    signature without its default reads as a deliberate summary -- which is what a
    diagram compartment is.
    """
    lines = []
    for attr in element.attributes[:limit]:
        mult = f"[{attr['multiplicity']}]" if attr["multiplicity"] else ""
        prefix = f"{attr['direction']} " if attr["direction"] else ""
        signature = f"{prefix}{attr['name']}: {attr['type'] or '?'}{mult}"
        line = signature
        if attr["default"]:
            value = " ".join(attr["default"].replace('"', "").split())
            candidate = f"{signature} = {value}"
            if len(candidate) <= MAX_ATTR_CHARS:
                line = candidate
            elif len(signature) + 6 <= MAX_ATTR_CHARS:
                room = MAX_ATTR_CHARS - len(signature) - 4
                line = f"{signature} = {value[:room].rstrip()}…"
        lines.append(_elide(line, MAX_ATTR_CHARS))
    remaining = len(element.attributes) - limit
    if remaining > 0:
        lines.append(f"… {remaining} more")
    return lines


def _elide(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _kind_of(element: Element) -> str:
    if element.kind == "requirement def":
        return "requirement"
    if element.kind == "verification def":
        return "verification"
    if element.kind == "constraint def":
        return "constraint"
    if element.kind in ("action def", "action"):
        return "action"
    if element.kind in ("state def", "state"):
        return "state"
    if element.kind == "port def":
        return "port"
    if element.kind == "variant part":
        return "variant"
    return "abstract" if element.abstract else "block"


def bdd(model: Model) -> tuple[list[Node], list[Edge]]:
    """Block Definition Diagram: part defs, their attributes, composition and specialisation."""
    defs = [e for e in model.root.descendants() if e.kind == "part def"]
    known = {e.name for e in defs}
    nodes = [
        Node(id=e.name, title=e.name,
             stereotype="«abstract part def»" if e.abstract else "«part def»",
             lines=_attr_lines(e), kind=_kind_of(e))
        for e in defs
    ]
    edges: list[Edge] = []
    for element in defs:
        for super_name in element.supers:
            if super_name in known:
                edges.append(Edge(super_name, element.name, style="solid",
                                  head="closed", label="specialises"))
        for child in element.of_kind("part"):
            target = child.typed_as
            if target in known:
                edges.append(Edge(element.name, target, head="diamond",
                                  label=child.name))
        for child in element.of_kind("variation part", "variant part"):
            if child.typed_as in known:
                edges.append(Edge(element.name, child.typed_as, head="diamond",
                                  label=child.name, style="dashed"))
    return nodes, edges


def ibd(model: Model, block_name: str) -> tuple[list[Node], list[Edge]]:
    """Internal Block Diagram: the parts of one block and the connections between them."""
    block = model.find(block_name)
    if block is None:
        return [], []
    parts = block.of_kind("part")
    nodes = []
    for part in parts:
        definition = model.find(part.typed_as or "") if part.typed_as else None
        nodes.append(Node(
            id=part.name, title=part.name,
            stereotype=f"«{part.typed_as}»" if part.typed_as else "«part»",
            lines=_attr_lines(definition, 4) if definition else [],
            kind=_kind_of(definition) if definition else "block"))
    for port in block.of_kind("port"):
        nodes.append(Node(id=port.name, title=port.name,
                          stereotype=f"«{port.typed_as}»", kind="port"))
    names = {n.id for n in nodes}
    edges = [Edge(r.source, r.target, head="flow", hierarchy=True)
             for r in model.relations
             if r.kind == "connect" and r.source in names and r.target in names]
    return nodes, edges


def req(model: Model) -> tuple[list[Node], list[Edge]]:
    """Requirement Diagram: requirements, what satisfies them, what verifies them."""
    nodes: list[Node] = []
    requirements = model.by_kind("requirement def")
    verifications = model.by_kind("verification def")

    for element in requirements:
        constraint = next((a for a in element.attributes
                           if a["name"] in ("budgetSeconds", "landedEdges")), None)
        lines = [_first_sentence(element.doc, 40)]
        if constraint:
            lines.append(f"constrains {constraint['name']}")
        nodes.append(Node(id=element.ident or element.name,
                          title=f"{element.ident}  {element.name}",
                          stereotype="«requirement»", lines=lines, kind="requirement"))

    for element in verifications:
        nodes.append(Node(id=element.ident or element.name,
                          title=f"{element.ident}  {element.name}",
                          stereotype="«verification»",
                          lines=[_first_sentence(element.doc, 40)],
                          kind="verification"))

    satisfiers = {r.source for r in model.relations if r.kind == "satisfy"}
    for name in sorted(satisfiers):
        element = model.find(name)
        definition = model.find(element.typed_as) if element and element.typed_as else None
        nodes.append(Node(id=name, title=name,
                          stereotype=f"«{element.typed_as}»" if element and element.typed_as
                                     else "«part»",
                          kind=_kind_of(definition) if definition else "block"))

    edges = []
    for relation in model.relations:
        # No per-edge label: every edge here is one of two kinds, both already carried
        # by colour and named in the legend. Repeating the word on 20 edges costs more
        # legibility than it adds -- over half of them could not be placed without
        # covering a block.
        if relation.kind == "satisfy":
            edges.append(Edge(relation.source, relation.target,
                              style="dashed", head="satisfy", hierarchy=False))
        elif relation.kind == "verify":
            edges.append(Edge(relation.source, relation.target,
                              style="dashed", head="verify", hierarchy=False))
    return nodes, edges


def act(model: Model, action_name: str) -> tuple[list[Node], list[Edge]]:
    """Activity Diagram: one action def, its sub-actions, and their succession."""
    action = model.find(action_name)
    if action is None:
        return [], []
    subs = action.of_kind("action")
    nodes = [Node(id=s.name, title=s.name, stereotype="«action»",
                  lines=_wrap(_first_sentence(s.doc, 38), 2), kind="action")
             for s in subs]
    names = {n.id for n in nodes}

    edges: list[Edge] = []
    seen: set[tuple[str, str]] = set()
    for chain in model.succession:
        for a, b in zip(chain, chain[1:]):
            if a in names and b in names and (a, b) not in seen:
                edges.append(Edge(a, b, head="flow"))
                seen.add((a, b))
    for relation in model.relations:
        if relation.kind == "flow" and relation.source in names \
                and relation.target in names and (relation.source, relation.target) not in seen:
            edges.append(Edge(relation.source, relation.target, label="flow",
                              head="flow", style="dashed"))
            seen.add((relation.source, relation.target))
    return nodes, edges


def stm(model: Model, state_name: str) -> tuple[list[Node], list[Edge]]:
    """State Machine Diagram: a state def and its transitions."""
    machine = model.find(state_name)
    if machine is None:
        return [], []
    states = machine.of_kind("state")
    nodes = [Node(id=s.name, title=s.name, stereotype="«state»", kind="state")
             for s in states]
    names = {n.id for n in nodes}
    edges = [Edge(r.source, r.target, label=_short_guard(r.guard), head="flow")
             for r in model.relations
             if r.kind == "transition" and r.source in names and r.target in names]
    return nodes, edges


# --------------------------------------------------------------------------- #
# Mermaid
# --------------------------------------------------------------------------- #

def bdd_mermaid(model: Model) -> str:
    defs = [e for e in model.root.descendants() if e.kind == "part def"]
    known = {e.name for e in defs}
    out = [f"%% Block Definition Diagram — generated from {model.path.name}",
           "%% Regenerate: python architecture/graphrag_agent/build_diagrams.py",
           "classDiagram", "    direction TB"]
    for element in defs:
        body = [f"        {a['name']} : {a['type'] or '?'}" for a in element.attributes[:6]]
        stereo = "        <<abstract>>" if element.abstract else None
        inner = ([stereo] if stereo else []) + body
        if inner:
            out.append(f"    class {element.name} {{")
            out += inner
            out.append("    }")
        else:
            out.append(f"    class {element.name}")
    for element in defs:
        for super_name in element.supers:
            if super_name in known:
                out.append(f"    {super_name} <|-- {element.name}")
        for child in element.of_kind("part"):
            if child.typed_as in known:
                out.append(f"    {element.name} *-- {child.typed_as} : {child.name}")
        for child in element.of_kind("variation part", "variant part"):
            if child.typed_as in known:
                out.append(f"    {element.name} o-- {child.typed_as} : {child.name}")
    return "\n".join(out) + "\n"


def req_mermaid(model: Model) -> str:
    out = [f"%% Requirement Diagram — generated from {model.path.name}",
           "requirementDiagram", ""]
    for element in model.by_kind("requirement def"):
        out.append(f"    requirement {element.name} {{")
        out.append(f"        id: {element.ident}")
        out.append(f'        text: "{_first_sentence(element.doc, 90)}"')
        out.append("        risk: high")
        out.append("        verifymethod: test")
        out.append("    }")
    for element in model.by_kind("verification def"):
        out.append(f"    element {element.name} {{")
        out.append("        type: verification")
        out.append(f'        docref: "{element.ident}"')
        out.append("    }")
    for name in sorted({r.source for r in model.relations if r.kind == "satisfy"}):
        out.append(f"    element {name} {{\n        type: component\n    }}")

    by_id = {e.ident: e.name for e in model.by_kind("requirement def")}
    verif = {e.ident: e.name for e in model.by_kind("verification def")}
    out.append("")
    for relation in model.relations:
        if relation.kind == "satisfy" and relation.target in by_id:
            out.append(f"    {relation.source} - satisfies -> {by_id[relation.target]}")
        elif relation.kind == "verify" and relation.target in by_id:
            out.append(f"    {verif.get(relation.source, relation.source)} - verifies -> "
                       f"{by_id[relation.target]}")
    return "\n".join(out) + "\n"


def act_mermaid(model: Model, action_name: str) -> str:
    nodes, edges = act(model, action_name)
    out = [f"%% Activity Diagram — {action_name}, generated from {model.path.name}",
           "flowchart TB", "    START(( ))"]
    for node in nodes:
        detail = f"<br/><i>{_first_sentence(node.lines and ' '.join(node.lines), 60)}</i>" \
            if node.lines else ""
        out.append(f'    {node.id}["<b>{node.title}</b>{detail}"]')
    ids = [n.id for n in nodes]
    if ids:
        out.append(f"    START --> {ids[0]}")
    for edge in edges:
        arrow = "-.->" if edge.style == "dashed" else "-->"
        label = f"|{edge.label}|" if edge.label else ""
        out.append(f"    {edge.src} {arrow}{label} {edge.dst}")
    if ids:
        out.append(f"    {ids[-1]} --> STOP(((  )))")
    return "\n".join(out) + "\n"


def stm_mermaid(model: Model, state_name: str) -> str:
    nodes, edges = stm(model, state_name)
    out = [f"%% State Machine — {state_name}, generated from {model.path.name}",
           "stateDiagram-v2", "    direction TB"]
    if nodes:
        out.append(f"    [*] --> {nodes[0].id}")
    for edge in edges:
        guard = f" : {edge.label}" if edge.label else ""
        out.append(f"    {edge.src} --> {edge.dst}{guard}")
    terminals = {n.id for n in nodes} - {e.src for e in edges}
    for terminal in sorted(terminals):
        out.append(f"    {terminal} --> [*]")
    return "\n".join(out) + "\n"


def ibd_mermaid(model: Model, block_name: str) -> str:
    nodes, edges = ibd(model, block_name)
    out = [f"%% Internal Block Diagram — {block_name}, generated from {model.path.name}",
           "flowchart LR"]
    for node in nodes:
        shape = f'(["{node.title}<br/><i>{node.stereotype}</i>"])' if node.kind == "port" \
            else f'["<b>{node.title}</b><br/><i>{node.stereotype}</i>"]'
        out.append(f"    {node.id}{shape}")
    for edge in edges:
        out.append(f"    {edge.src} --> {edge.dst}")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- #

def _first_sentence(doc: str | None, limit: int = 60) -> str:
    if not doc:
        return ""
    text = " ".join(doc.split())
    for terminator in (". ", " -- ", "; "):
        if terminator in text:
            text = text.split(terminator)[0]
            break
    text = text.rstrip(".").replace('"', "'")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _wrap(text: str, max_lines: int, width: int = 38) -> list[str]:
    if not text:
        return []
    return textwrap.wrap(text, width)[:max_lines]


def _short_guard(guard: str | None) -> str:
    if not guard:
        return ""
    guard = " ".join(guard.split())
    if guard.startswith("options : "):
        return "start"
    return guard if len(guard) <= 26 else guard[:25] + "…"
