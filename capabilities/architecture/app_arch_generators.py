"""Diagram + documentation generators for the Level-2 application architecture.

Produces, from ``app_architecture_model.py``:

* ``compute_layout`` — a single shared layout (nodes + edges) consumed by both
  renderers so the SVG and PNG always match;
* ``to_archimate_svg`` — a hand-rendered ArchiMate Application-Architecture
  diagram (4 layers: Capability ← Service ← Component → Data Object);
* ``draw_archimate_png`` — a matplotlib raster twin (also used for verification);
* ``to_mermaid`` — a Mermaid view of the same model;
* ``to_architecture_markdown`` — the architecture description document.
"""

from __future__ import annotations

import textwrap

from ontology_engineering_capabilities import CAPABILITY_BY_ID

from .app_architecture_model import (
    COMPONENTS,
    DATA_OBJECT_BY_ID,
    DOMAINS,
    SERVICE_BY_ID,
    TARGET_LEVEL,
    TARGET_LEVEL_NAME,
    components_in,
    DATA_OBJECTS,
    SERVICES,
)

# ArchiMate-ish palette
CAP_FILL, CAP_STROKE = "#FBE2B5", "#B5821E"   # strategy / capability (yellow)
SVC_FILL, SVC_STROKE = "#CFE8FB", "#2E6CA4"   # application service (blue)
CMP_FILL, CMP_STROKE = "#BBD7F0", "#1F5C95"   # application component (blue)
DAT_FILL, DAT_STROKE = "#E3F0FB", "#3A6EA5"   # data object (blue, lighter)

# Layout constants
_MARGIN = 24
_LEFT = 132            # left gutter for band labels
_COL_W = 212
_COL_GAP = 22
_TITLE_H = 74
_LEGEND_H = 64
_CAP_H, _SVC_H, _CMP_H, _DAT_H = 46, 54, 70, 44
_VGAP = 12
_BAND_GAP = 46

_BANDS = [
    ("capability", "Capabilities (L2)", _CAP_H),
    ("service", "Application Services", _SVC_H),
    ("component", "Application Components", _CMP_H),
    ("data", "Data Objects", _DAT_H),
]


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #
def _data_domain() -> dict[str, str]:
    """Assign each data object to a domain column (by its writer, else reader)."""
    assign: dict[str, str] = {}
    for comp in COMPONENTS:
        for did in comp.writes:
            assign.setdefault(did, comp.domain)
    for comp in COMPONENTS:
        for did in comp.reads:
            assign.setdefault(did, comp.domain)
    return assign


def compute_layout() -> dict:
    """Return {'nodes': {...}, 'edges': [...], 'width':, 'height':, 'bands': }."""
    domains = DOMAINS
    n_cols = len(domains)

    # per-domain element lists
    dom_services = {d.id: [s for s in SERVICES if s in [SERVICE_BY_ID[x] for x in
                    [sv.id for sv in SERVICES] ] and s.id in
                    [sid for c in components_in(d.id) for sid in c.realizes]] for d in domains}
    # simpler & deterministic: services whose realizing component is in the domain
    dom_services = {d.id: [] for d in domains}
    for comp in COMPONENTS:
        for sid in comp.realizes:
            dom_services[comp.domain].append(SERVICE_BY_ID[sid])
    dom_caps = {d.id: [] for d in domains}
    for d in domains:
        seen = []
        for s in dom_services[d.id]:
            for cid in s.serves_capabilities:
                if cid not in seen:
                    seen.append(cid)
        dom_caps[d.id] = seen
    dom_comps = {d.id: components_in(d.id) for d in domains}
    data_dom = _data_domain()
    dom_data = {d.id: [do for do in DATA_OBJECTS if data_dom.get(do.id) == d.id] for d in domains}

    band_count = {
        "capability": max(len(dom_caps[d.id]) for d in domains),
        "service": max(len(dom_services[d.id]) for d in domains),
        "component": max(len(dom_comps[d.id]) for d in domains),
        "data": max(len(dom_data[d.id]) for d in domains),
    }
    band_h = {
        "capability": band_count["capability"] * (_CAP_H + _VGAP),
        "service": band_count["service"] * (_SVC_H + _VGAP),
        "component": band_count["component"] * (_CMP_H + _VGAP),
        "data": band_count["data"] * (_DAT_H + _VGAP),
    }

    # band y tops
    band_top: dict[str, float] = {}
    y = _TITLE_H + _MARGIN
    for key, _label, _h in _BANDS:
        band_top[key] = y
        y += band_h[key] + _BAND_GAP
    total_h = y - _BAND_GAP + _LEGEND_H + _MARGIN

    width = _MARGIN + _LEFT + n_cols * _COL_W + (n_cols - 1) * _COL_GAP + _MARGIN

    def col_x(i: int) -> float:
        return _MARGIN + _LEFT + i * (_COL_W + _COL_GAP)

    box_w = {"capability": _COL_W - 30, "service": _COL_W - 14,
             "component": _COL_W - 6, "data": _COL_W - 40}
    box_h = {"capability": _CAP_H, "service": _SVC_H, "component": _CMP_H, "data": _DAT_H}

    nodes: dict[str, dict] = {}

    def place(kind: str, items, ci: int, label_fn):
        bw, bh = box_w[kind], box_h[kind]
        cx = col_x(ci) + (_COL_W - bw) / 2
        for slot, item in enumerate(items):
            ny = band_top[kind] + slot * (bh + _VGAP)
            nid = item if isinstance(item, str) else item.id
            label, sub = label_fn(item)
            nodes[nid] = dict(x=cx, y=ny, w=bw, h=bh, kind=kind, label=label, sub=sub)

    for ci, d in enumerate(domains):
        place("capability", dom_caps[d.id], ci,
              lambda cid: (CAPABILITY_BY_ID[cid].name, cid))
        place("service", dom_services[d.id], ci,
              lambda s: (s.name, s.id))
        place("component", dom_comps[d.id], ci,
              lambda c: (c.name, c.id))
        place("data", dom_data[d.id], ci,
              lambda do: (do.name, do.id))

    # edges
    edges: list[tuple[str, str, str]] = []
    for s in SERVICES:                       # serving: service -> capability
        for cid in s.serves_capabilities:
            if cid in nodes:
                edges.append((s.id, cid, "serving"))
    for c in COMPONENTS:
        for sid in c.realizes:               # realization: component -> service
            edges.append((c.id, sid, "realization"))
        for did in c.reads:                  # access read: data -> component
            if did in nodes:
                edges.append((c.id, did, "access_r"))
        for did in c.writes:                 # access write: component -> data
            if did in nodes:
                edges.append((c.id, did, "access_w"))
        for uid in c.uses:                   # serving: used-component -> component
            edges.append((c.id, uid, "uses"))

    return dict(nodes=nodes, edges=edges, width=width, height=total_h,
                band_top=band_top, band_h=band_h, col_x=[col_x(i) for i in range(n_cols)],
                domains=[(d.id, d.name) for d in domains])


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _wrap(text: str, width: int, max_lines: int) -> list[str]:
    lines = textwrap.wrap(text, width=width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max(0, width - 1)] + "…"
    return lines


def _edge_anchor(n: dict, side: str) -> tuple[float, float]:
    if side == "top":
        return (n["x"] + n["w"] / 2, n["y"])
    if side == "bottom":
        return (n["x"] + n["w"] / 2, n["y"] + n["h"])
    if side == "left":
        return (n["x"], n["y"] + n["h"] / 2)
    return (n["x"] + n["w"], n["y"] + n["h"] / 2)  # right


# --------------------------------------------------------------------------- #
# SVG renderer
# --------------------------------------------------------------------------- #
def to_archimate_svg() -> str:
    L = compute_layout()
    nodes, edges = L["nodes"], L["edges"]
    W, H = L["width"], L["height"]

    svg: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
        f'viewBox="0 0 {W:.0f} {H:.0f}" font-family="Segoe UI, Arial">',
        # markers
        '<defs>',
        '<marker id="open" markerWidth="11" markerHeight="11" refX="9" refY="5" orient="auto">'
        '<path d="M1,1 L9,5 L1,9" fill="none" stroke="#37474F" stroke-width="1.4"/></marker>',
        '<marker id="tri" markerWidth="13" markerHeight="13" refX="10" refY="6" orient="auto">'
        '<path d="M1,1 L11,6 L1,11 Z" fill="white" stroke="#37474F" stroke-width="1.2"/></marker>',
        '<marker id="dot" markerWidth="9" markerHeight="9" refX="7" refY="4.5" orient="auto">'
        '<path d="M1,1 L7,4.5 L1,8" fill="none" stroke="#5C7A99" stroke-width="1.2"/></marker>',
        '</defs>',
        f'<rect width="{W:.0f}" height="{H:.0f}" fill="#FFFFFF"/>',
        f'<text x="{_MARGIN}" y="34" font-size="20" font-weight="700" fill="#1A2733">'
        f'Ontology Repository — Application Architecture (ArchiMate)</text>',
        f'<text x="{_MARGIN}" y="56" font-size="12" fill="#546170">'
        f'Logical application services supporting EKGF maturity Level {TARGET_LEVEL} '
        f'“{TARGET_LEVEL_NAME}” capabilities · service ▸ serves capability · '
        f'component ▸ realizes service · component ⋯ accesses data object</text>',
    ]

    # band backgrounds + labels
    band_tint = {"capability": "#FFF8EC", "service": "#EEF6FD",
                 "component": "#E7F1FB", "data": "#F2F8FD"}
    for key, label, _h in _BANDS:
        top = L["band_top"][key]
        bh = L["band_h"][key]
        svg.append(
            f'<rect x="{_MARGIN}" y="{top - 10}" width="{W - 2 * _MARGIN}" height="{bh + 20}" '
            f'rx="8" fill="{band_tint[key]}" stroke="#CFD8DC" stroke-width="1"/>'
        )
        svg.append(
            f'<text x="{_MARGIN + 8}" y="{top - 14}" font-size="11.5" font-weight="700" '
            f'fill="#607D8B">{label}</text>'
        )

    # domain column headers (in the capability band area)
    for ci, (did, dname) in enumerate(L["domains"]):
        x = L["col_x"][ci]
        svg.append(
            f'<text x="{x + _COL_W / 2}" y="{_TITLE_H + _MARGIN - 14}" text-anchor="middle" '
            f'font-size="11" font-weight="700" fill="#37474F">{did} · {_esc(dname)}</text>'
        )

    # edges first (under nodes)
    def line(p1, p2, **kw):
        st = kw.get("stroke", "#37474F"); wdt = kw.get("w", 1.3)
        dash = f' stroke-dasharray="{kw["dash"]}"' if "dash" in kw else ""
        mark = f' marker-end="url(#{kw["marker"]})"' if "marker" in kw else ""
        # simple orthogonal-ish curve via quadratic for non-vertical links
        x1, y1 = p1; x2, y2 = p2
        if abs(x1 - x2) < 1:
            d = f'M{x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f}'
        else:
            mx = (x1 + x2) / 2
            d = f'M{x1:.1f},{y1:.1f} C{mx:.1f},{y1:.1f} {mx:.1f},{y2:.1f} {x2:.1f},{y2:.1f}'
        svg.append(f'<path d="{d}" fill="none" stroke="{st}" stroke-width="{wdt}"{dash}{mark}/>')

    style = {
        "serving":     dict(stroke="#37474F", w=1.3, marker="open"),
        "realization": dict(stroke="#37474F", w=1.2, marker="tri", dash="5 4"),
        "access_r":    dict(stroke="#5C7A99", w=1.0, marker="dot", dash="2 3"),
        "access_w":    dict(stroke="#5C7A99", w=1.0, marker="dot", dash="2 3"),
        "uses":        dict(stroke="#7E9AB5", w=1.0, marker="open"),
    }
    for src, dst, etype in edges:
        if src not in nodes or dst not in nodes:
            continue
        a, b = nodes[src], nodes[dst]
        if etype == "serving":         # service(top) -> capability(bottom)
            line(_edge_anchor(a, "top"), _edge_anchor(b, "bottom"), **style[etype])
        elif etype == "realization":   # component(top) -> service(bottom)
            line(_edge_anchor(a, "top"), _edge_anchor(b, "bottom"), **style[etype])
        elif etype == "access_w":      # component(bottom) -> data(top)
            line(_edge_anchor(a, "bottom"), _edge_anchor(b, "top"), **style[etype])
        elif etype == "access_r":      # data(top) -> component(bottom)
            line(_edge_anchor(b, "top"), _edge_anchor(a, "bottom"), **style[etype])
        elif etype == "uses":          # used(right/left) -> user component
            line(_edge_anchor(b, "left" if b["x"] > a["x"] else "right"),
                 _edge_anchor(a, "right" if b["x"] > a["x"] else "left"), **style[etype])

    # nodes
    for nid, n in nodes.items():
        x, y, w, h, kind = n["x"], n["y"], n["w"], n["h"], n["kind"]
        if kind == "capability":
            fill, stroke = CAP_FILL, CAP_STROKE
            svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>')
            # capability glyph
            svg.append(f'<rect x="{x + w - 22}" y="{y + 6}" width="14" height="10" rx="2" fill="none" stroke="{stroke}" stroke-width="1"/>')
            svg.append(f'<line x1="{x + w - 22}" y1="{y + 11}" x2="{x + w - 8}" y2="{y + 11}" stroke="{stroke}" stroke-width="1"/>')
        elif kind == "service":
            fill, stroke = SVC_FILL, SVC_STROKE
            svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h/2:.0f}" fill="{fill}" stroke="{stroke}" stroke-width="1.3"/>')
        elif kind == "component":
            fill, stroke = CMP_FILL, CMP_STROKE
            svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3" fill="{fill}" stroke="{stroke}" stroke-width="1.3"/>')
            # UML component "ears"
            for dy in (12, 30):
                svg.append(f'<rect x="{x - 6}" y="{y + dy}" width="12" height="9" fill="{fill}" stroke="{stroke}" stroke-width="1.1"/>')
        else:  # data object
            fill, stroke = DAT_FILL, DAT_STROKE
            svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>')
            svg.append(f'<line x1="{x}" y1="{y + 12}" x2="{x + w}" y2="{y + 12}" stroke="{stroke}" stroke-width="1.1"/>')

        # labels
        name_w = 22 if kind in ("capability", "data") else (24 if kind == "service" else 24)
        name_lines = _wrap(n["label"], name_w, 2 if kind != "data" else 2)
        ty = y + (16 if kind != "component" else 26)
        for ln in name_lines:
            svg.append(f'<text x="{x + 9}" y="{ty}" font-size="10.5" font-weight="600" fill="#16242E">{_esc(ln)}</text>')
            ty += 12
        svg.append(f'<text x="{x + 9}" y="{y + h - 6}" font-size="8.5" fill="#4E6473">{n["sub"]}</text>')

    # legend
    ly = H - _LEGEND_H + 18
    items = [
        ("rect", CAP_FILL, CAP_STROKE, "Capability (L2)"),
        ("pill", SVC_FILL, SVC_STROKE, "Application Service"),
        ("comp", CMP_FILL, CMP_STROKE, "Application Component"),
        ("data", DAT_FILL, DAT_STROKE, "Data Object"),
    ]
    lx = _MARGIN
    for shape, fill, stroke, label in items:
        if shape == "pill":
            svg.append(f'<rect x="{lx}" y="{ly - 12}" width="22" height="14" rx="7" fill="{fill}" stroke="{stroke}"/>')
        else:
            svg.append(f'<rect x="{lx}" y="{ly - 12}" width="22" height="14" rx="2" fill="{fill}" stroke="{stroke}"/>')
        svg.append(f'<text x="{lx + 28}" y="{ly}" font-size="10.5" fill="#37474F">{label}</text>')
        lx += 175
    # relation legend
    ly2 = ly + 22
    rels = [("serving ▸ serves", "#37474F", "open", None),
            ("realization ▷", "#37474F", "tri", "5 4"),
            ("access ⋯", "#5C7A99", "dot", "2 3"),
            ("uses ▸", "#7E9AB5", "open", None)]
    lx = _MARGIN
    for label, color, marker, dash in rels:
        d = f' stroke-dasharray="{dash}"' if dash else ""
        svg.append(f'<line x1="{lx}" y1="{ly2 - 5}" x2="{lx + 28}" y2="{ly2 - 5}" stroke="{color}" stroke-width="1.4" marker-end="url(#{marker})"{d}/>')
        svg.append(f'<text x="{lx + 34}" y="{ly2 - 1}" font-size="10.5" fill="#37474F">{label}</text>')
        lx += 175
    svg.append("</svg>")
    return "\n".join(svg) + "\n"


# --------------------------------------------------------------------------- #
# matplotlib raster twin
# --------------------------------------------------------------------------- #
def draw_archimate_png(path: str = "artifacts/app_architecture.png"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, Rectangle, FancyArrowPatch

    L = compute_layout()
    nodes, edges = L["nodes"], L["edges"]
    W, H = L["width"], L["height"]
    fig, ax = plt.subplots(figsize=(W / 72, H / 72))
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.invert_yaxis(); ax.axis("off")

    ax.text(_MARGIN, 30, "Ontology Repository — Application Architecture (ArchiMate)",
            fontsize=16, fontweight="bold", color="#1A2733")
    ax.text(_MARGIN, 52, f"Logical application services supporting EKGF maturity Level "
            f"{TARGET_LEVEL} “{TARGET_LEVEL_NAME}” capabilities",
            fontsize=10, color="#546170")

    band_tint = {"capability": "#FFF8EC", "service": "#EEF6FD",
                 "component": "#E7F1FB", "data": "#F2F8FD"}
    for key, label, _h in _BANDS:
        top = L["band_top"][key]; bh = L["band_h"][key]
        ax.add_patch(Rectangle((_MARGIN, top - 10), W - 2 * _MARGIN, bh + 20,
                     facecolor=band_tint[key], edgecolor="#CFD8DC"))
        ax.text(_MARGIN + 8, top - 14, label, fontsize=10, fontweight="bold", color="#607D8B")
    for ci, (did, dname) in enumerate(L["domains"]):
        x = L["col_x"][ci]
        ax.text(x + _COL_W / 2, _TITLE_H + _MARGIN - 14, f"{did} · {dname}",
                ha="center", fontsize=9, fontweight="bold", color="#37474F")

    def anchor(n, side):
        return _edge_anchor(n, side)

    estyle = {
        "serving": ("#37474F", 1.3, "-", "-|>"),
        "realization": ("#37474F", 1.2, (0, (5, 4)), "-|>"),
        "access_r": ("#5C7A99", 1.0, (0, (2, 3)), "-|>"),
        "access_w": ("#5C7A99", 1.0, (0, (2, 3)), "-|>"),
        "uses": ("#7E9AB5", 1.0, "-", "-|>"),
    }
    for src, dst, etype in edges:
        if src not in nodes or dst not in nodes:
            continue
        a, b = nodes[src], nodes[dst]
        color, lw, ls, arr = estyle[etype]
        if etype in ("serving", "realization"):
            p1, p2 = anchor(a, "top"), anchor(b, "bottom"); rad = 0.0 if abs(a["x"]-b["x"])<1 else 0.15
        elif etype == "access_w":
            p1, p2 = anchor(a, "bottom"), anchor(b, "top"); rad = 0.2
        elif etype == "access_r":
            p1, p2 = anchor(b, "top"), anchor(a, "bottom"); rad = 0.2
        else:
            if b["x"] > a["x"]:
                p1, p2 = anchor(b, "left"), anchor(a, "right")
            else:
                p1, p2 = anchor(b, "right"), anchor(a, "left")
            rad = 0.25
        ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=arr, color=color, lw=lw,
                     linestyle=ls, mutation_scale=11,
                     connectionstyle=f"arc3,rad={rad}", shrinkA=1, shrinkB=2))

    for nid, n in nodes.items():
        x, y, w, h, kind = n["x"], n["y"], n["w"], n["h"], n["kind"]
        if kind == "capability":
            fc, ec = CAP_FILL, CAP_STROKE
            ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=7", facecolor=fc, edgecolor=ec, lw=1.2))
        elif kind == "service":
            fc, ec = SVC_FILL, SVC_STROKE
            ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={h/2:.0f}", facecolor=fc, edgecolor=ec, lw=1.3))
        elif kind == "component":
            fc, ec = CMP_FILL, CMP_STROKE
            ax.add_patch(Rectangle((x, y), w, h, facecolor=fc, edgecolor=ec, lw=1.3))
            for dy in (12, 30):
                ax.add_patch(Rectangle((x - 6, y + dy), 12, 9, facecolor=fc, edgecolor=ec, lw=1.1))
        else:
            fc, ec = DAT_FILL, DAT_STROKE
            ax.add_patch(Rectangle((x, y), w, h, facecolor=fc, edgecolor=ec, lw=1.2))
            ax.plot([x, x + w], [y + 12, y + 12], color=ec, lw=1.1)
        nm_w = 24 if kind in ("service", "component") else 22
        ty = y + (15 if kind != "component" else 25)
        for ln in _wrap(n["label"], nm_w, 2):
            ax.text(x + 9, ty, ln, fontsize=8.2, fontweight="bold", color="#16242E")
            ty += 11.5
        ax.text(x + 9, y + h - 6, n["sub"], fontsize=7, color="#4E6473")

    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return path


# --------------------------------------------------------------------------- #
# Mermaid
# --------------------------------------------------------------------------- #
def to_mermaid() -> str:
    mid = lambda s: s.replace(".", "_")
    lines = [
        "%% Level-2 Application Architecture (ArchiMate application layer)",
        "flowchart BT",
        "  classDef cap fill:#FBE2B5,stroke:#B5821E,color:#000;",
        "  classDef svc fill:#CFE8FB,stroke:#2E6CA4,color:#000;",
        "  classDef cmp fill:#BBD7F0,stroke:#1F5C95,color:#000;",
        "  classDef dat fill:#E3F0FB,stroke:#3A6EA5,color:#000;",
        '  subgraph CAPS["Capabilities (L2 — Extensible Platform)"]',
    ]
    for cid in sorted({c for s in SERVICES for c in s.serves_capabilities}):
        lines.append(f'    {mid(cid)}["{cid} {CAPABILITY_BY_ID[cid].name}"]:::cap')
    lines.append("  end")
    lines.append('  subgraph SVCS["Application Services"]')
    for s in SERVICES:
        lines.append(f'    {mid(s.id)}(["{s.id} {s.name}"]):::svc')
    lines.append("  end")
    lines.append('  subgraph CMPS["Application Components"]')
    for c in COMPONENTS:
        lines.append(f'    {mid(c.id)}["{c.id} {c.name}"]:::cmp')
    lines.append("  end")
    lines.append('  subgraph DATA["Data Objects"]')
    for d in DATA_OBJECTS:
        lines.append(f'    {mid(d.id)}[("{d.id} {d.name}")]:::dat')
    lines.append("  end")
    lines.append("  %% realization (component -> service) and serving (service -> capability)")
    for c in COMPONENTS:
        for sid in c.realizes:
            lines.append(f"  {mid(c.id)} -. realizes .-> {mid(sid)}")
    for s in SERVICES:
        for cid in s.serves_capabilities:
            lines.append(f"  {mid(s.id)} --> |serves| {mid(cid)}")
    for c in COMPONENTS:
        for did in c.writes:
            lines.append(f"  {mid(c.id)} -.->|writes| {mid(did)}")
        for did in c.reads:
            lines.append(f"  {mid(did)} -.->|read by| {mid(c.id)}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Architecture documentation
# --------------------------------------------------------------------------- #
def to_architecture_markdown() -> str:
    from .app_architecture_model import validate_model, services_for_capability
    out: list[str] = []
    w = out.append
    w("# Level-2 Application Architecture — Ontology Repository\n")
    w(f"Logical **application architecture** (ArchiMate application layer) that provides the "
      f"application **services** required to support the **{len(set(c for s in SERVICES for c in s.serves_capabilities))} "
      f"capabilities at EKGF maturity Level {TARGET_LEVEL} — “{TARGET_LEVEL_NAME}”** of the "
      f"Ontology Repository Capability Model.\n")
    w("> *Extensible Platform* (EKG/MM L2): “the organisation has implemented an Enterprise "
      "Knowledge Graph and is starting to build out its capabilities and integrations with "
      "other systems and processes.” The architecture below is the minimum coherent set of "
      "application services/components to operate the ontology practice as a reusable platform.\n")
    probs = validate_model()
    w(f"**Model integrity:** {'consistent (0 problems)' if not probs else probs}\n")

    w("## 1. Overview\n")
    w("The architecture is organised into four ArchiMate layers and six application domains:\n")
    w("- **Capabilities (L2)** — the business/technology capabilities being supported.")
    w("- **Application Services** — externally visible behaviour; one service per L2 capability.")
    w("- **Application Components** — deployable software realising the services.")
    w("- **Data Objects** — passive structure the components access.\n")
    w("| Application domain | Purpose | Components |")
    w("|---|---|---|")
    for d in DOMAINS:
        comps = ", ".join(c.name for c in components_in(d.id))
        w(f"| **{d.id} · {d.name}** | {d.description} | {comps} |")
    w("")

    w("## 2. Capability → Application Service → Component mapping\n")
    w("Each Level-2 capability is served by an application service realised by a component.\n")
    w("| L2 capability | Application service | Realising component | EKGF pillar |")
    w("|---|---|---|---|")
    comp_for_service = {sid: c for c in COMPONENTS for sid in c.realizes}
    for s in SERVICES:
        for cid in s.serves_capabilities:
            cap = CAPABILITY_BY_ID[cid]
            comp = comp_for_service[s.id]
            w(f"| {cid} {cap.name} | {s.id} **{s.name}** | {comp.id} {comp.name} | {cap.ekgf_pillar} |")
    w("")

    w("## 3. Application services (catalogue)\n")
    for s in SERVICES:
        comp = comp_for_service[s.id]
        caps = ", ".join(f"{c} ({CAPABILITY_BY_ID[c].name})" for c in s.serves_capabilities)
        w(f"### {s.id} · {s.name}\n")
        w(f"- **Description:** {s.description}")
        w(f"- **Serves capability:** {caps}")
        w(f"- **Realised by:** {comp.id} {comp.name}\n")

    w("## 4. Application components (catalogue)\n")
    w("| ID | Component | Domain | Realises services | Reads | Writes | Uses | Technology candidates |")
    w("|---|---|---|---|---|---|---|---|")
    for c in COMPONENTS:
        reads = ", ".join(c.reads) or "—"
        writes = ", ".join(c.writes) or "—"
        uses = ", ".join(c.uses) or "—"
        realizes = ", ".join(c.realizes)
        tech = ", ".join(c.technology_candidates) or "—"
        w(f"| {c.id} | **{c.name}** | {c.domain} | {realizes} | {reads} | {writes} | {uses} | {tech} |")
    w("")

    w("## 5. Data objects\n")
    w("| ID | Data object | Description | Written by | Read by |")
    w("|---|---|---|---|---|")
    for d in DATA_OBJECTS:
        writers = ", ".join(c.id for c in COMPONENTS if d.id in c.writes) or "—"
        readers = ", ".join(c.id for c in COMPONENTS if d.id in c.reads) or "—"
        w(f"| {d.id} | **{d.name}** | {d.description} | {writers} | {readers} |")
    w("")

    w("## 6. Component cooperation (key dependencies)\n")
    w("`uses` (serving) relations between components — the platform's internal wiring:\n")
    for c in COMPONENTS:
        if c.uses:
            w(f"- **{c.name}** uses: " + ", ".join(COMPONENT_NAME[u] for u in c.uses))
    w("")

    w("## 7. ArchiMate relations used\n")
    w("- **Serving** (service → capability, component → component): the source provides "
      "behaviour the target consumes.")
    w("- **Realization** (component → service): the component implements the service.")
    w("- **Access** (component ⋯ data object): read/write of passive structure.\n")

    w("## 8. Notes & scope\n")
    w(f"- Scope is deliberately limited to Level {TARGET_LEVEL}. Level-1 prerequisites "
      "(conceptualisation, competency questions) are assumed available; higher-level "
      "capabilities (CI/CD, federation, LLM augmentation, observability) are **out of scope** "
      "and would extend this architecture at L3–L5.")
    w("- Enterprise-enablement services (funding, skills) are typically realised by existing "
      "COTS platforms and are shown for completeness as they support the L2 business capabilities.")
    w("- Technology candidates are illustrative, not prescriptive.\n")

    w("## 9. Artifacts\n")
    w("- `artifacts/app_architecture.svg` — ArchiMate application architecture diagram (SVG).")
    w("- `artifacts/app_architecture.png` — raster twin of the diagram.")
    w("- `artifacts/app_architecture.mmd` — Mermaid view of the same model.\n")
    return "\n".join(out)


# convenience lookup used by the doc generator
COMPONENT_NAME = {c.id: c.name for c in COMPONENTS}
