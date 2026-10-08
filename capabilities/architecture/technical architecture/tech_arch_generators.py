"""Generators for the technical (technology-layer) architecture.

* ``to_archimate_svg`` / ``draw_archimate_png`` — an ArchiMate **technology
  architecture** view (application consumers ← technology services ← nodes /
  system software), with the SVG and a matplotlib PNG twin sharing one layout.
* ``to_requirements_catalog_md`` — the normative technical-requirements catalogue.
* ``to_traceability_md`` — capability ↔ application-component ↔ technology
  service ↔ requirement traceability.
"""

from __future__ import annotations

import textwrap

try:                       # works whether imported as a module or run via the build script
    from . import tech_architecture_model as M
except ImportError:
    import tech_architecture_model as M
from architecture import app_architecture_model as app

try:
    from ontology_engineering_capabilities import CAPABILITY_BY_ID
except Exception:  # pragma: no cover
    CAPABILITY_BY_ID = {}

# ArchiMate technology layer = green; application = blue; we mix for the view.
APP_FILL, APP_STROKE = "#CFE8FB", "#2E6CA4"
SVC_FILL, SVC_STROKE = "#CDE9C6", "#3F7E3A"   # technology service (green)
NODE_FILL, NODE_STROKE = "#BFE0B6", "#2F6B2A"  # node / system software (green)
INFRA_FILL, INFRA_STROKE = "#E6F3E1", "#5A8A53"

# layout
_MARGIN = 24
_LEFT = 120
_COL_W = 168
_COL_GAP = 12
_TITLE_H = 76
_LEGEND_H = 56
_APP_H, _SVC_H, _NODE_H, _INF_H = 50, 56, 64, 56
_BAND_GAP = 50

# Order the 10 services (each realised 1:1 by a node) into related clusters.
_SVC_ORDER = ["TS.RDF", "TS.PG", "TS.SYNC", "TS.OBJ", "TS.SCM", "TS.CICD",
              "TS.IAM", "TS.GW", "TS.SEC", "TS.OBS"]
_SVC_TO_NODE = {n.realizes[0]: n.id for n in M.TECH_NODES if n.realizes}
_APP_ORDER = ["C.KGS", "C.RVE", "C.AUTH", "C.VOCAB", "C.VIZ", "C.DOC", "C.REPO"]
_INFRA_NODES = ["N.GKE", "N.POOL.MEM", "N.POOL.GP", "N.FALKOR.PV",
                "N.FUSEKI.PV", "N.SENTINEL", "N.AR"]
_APP_NAME = {c.id: c.name for c in app.COMPONENTS}


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _wrap(t, w, ml):
    ls = textwrap.wrap(t, width=w)
    if len(ls) > ml:
        ls = ls[:ml]; ls[-1] = ls[-1][:max(0, w - 1)] + "…"
    return ls


def compute_layout():
    n_cols = len(_SVC_ORDER)
    width = _MARGIN + _LEFT + n_cols * _COL_W + (n_cols - 1) * _COL_GAP + _MARGIN

    band_top = {}
    y = _TITLE_H + _MARGIN
    band_top["app"] = y; y += _APP_H + _BAND_GAP
    band_top["svc"] = y; y += _SVC_H + _BAND_GAP
    band_top["node"] = y; y += _NODE_H + _BAND_GAP
    band_top["infra"] = y; y += _INF_H + 30
    height = y + _LEGEND_H + _MARGIN

    def colx(i):
        return _MARGIN + _LEFT + i * (_COL_W + _COL_GAP)

    nodes = {}
    # app components row (spread across full width)
    app_w = _COL_W - 8
    app_span = width - _MARGIN - _LEFT - _MARGIN
    step = app_span / len(_APP_ORDER)
    for i, cid in enumerate(_APP_ORDER):
        x = _MARGIN + _LEFT + i * step + (step - app_w) / 2
        nodes[cid] = dict(x=x, y=band_top["app"], w=app_w, h=_APP_H,
                          kind="app", label=_APP_NAME[cid], sub=cid)
    # services + realizing nodes (aligned columns)
    for i, sid in enumerate(_SVC_ORDER):
        s = M.TECH_SERVICE_BY_ID[sid]
        x = colx(i)
        nodes[sid] = dict(x=x, y=band_top["svc"], w=_COL_W - 8, h=_SVC_H,
                          kind="svc", label=s.name, sub=sid)
        nid = _SVC_TO_NODE[sid]
        nn = M.TECH_NODE_BY_ID[nid]
        nodes[nid] = dict(x=x, y=band_top["node"], w=_COL_W - 8, h=_NODE_H,
                          kind="node", label=nn.name, sub=nid, nkind=nn.kind)
    # infra band (row inside an envelope)
    inf_w = _COL_W - 8
    inf_span = width - _MARGIN - _LEFT - _MARGIN
    istep = inf_span / len(_INFRA_NODES)
    for i, nid in enumerate(_INFRA_NODES):
        nn = M.TECH_NODE_BY_ID[nid]
        x = _MARGIN + _LEFT + i * istep + (istep - inf_w) / 2
        nodes[nid] = dict(x=x, y=band_top["infra"], w=inf_w, h=_INF_H,
                          kind="infra", label=nn.name, sub=nid, nkind=nn.kind)

    edges = []
    # serving: service -> app component
    for sid in _SVC_ORDER:
        for cid in M.TECH_SERVICE_BY_ID[sid].serves_components:
            if cid in nodes:
                edges.append((sid, cid, "serving"))
    # realization: node -> service
    for sid in _SVC_ORDER:
        edges.append((_SVC_TO_NODE[sid], sid, "realization"))
    # hosting (dashed): key platform nodes -> their pool
    for nid, host in [("N.FALKOR", "N.POOL.MEM"), ("N.FUSEKI", "N.POOL.GP"),
                      ("N.RDFDELTA", "N.POOL.GP")]:
        if nid in nodes and host in nodes:
            edges.append((nid, host, "hosting"))

    return dict(nodes=nodes, edges=edges, width=width, height=height,
                band_top=band_top)


# --------------------------------------------------------------------------- #
# SVG
# --------------------------------------------------------------------------- #
def to_archimate_svg():
    L = compute_layout(); nodes = L["nodes"]; W = L["width"]; H = L["height"]
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
        f'viewBox="0 0 {W:.0f} {H:.0f}" font-family="Segoe UI, Arial">',
        '<defs>',
        '<marker id="open" markerWidth="11" markerHeight="11" refX="9" refY="5" orient="auto">'
        '<path d="M1,1 L9,5 L1,9" fill="none" stroke="#37474F" stroke-width="1.3"/></marker>',
        '<marker id="tri" markerWidth="13" markerHeight="13" refX="10" refY="6" orient="auto">'
        '<path d="M1,1 L11,6 L1,11 Z" fill="white" stroke="#37474F" stroke-width="1.1"/></marker>',
        '</defs>',
        f'<rect width="{W:.0f}" height="{H:.0f}" fill="#FFFFFF"/>',
        f'<text x="{_MARGIN}" y="32" font-size="20" font-weight="700" fill="#15301a">'
        f'Ontology Repository — Technology Architecture (ArchiMate)</text>',
        f'<text x="{_MARGIN}" y="54" font-size="12" fill="#4d6b50">'
        f'Technology services &amp; nodes realising the Level-{M.TARGET_LEVEL} application '
        f'components · FalkorDB (property graph) + Fuseki (RDF/SPARQL) on GKE</text>',
    ]
    band_lbl = {"app": "Application (consumers)", "svc": "Technology Services",
                "node": "System Software / Platforms", "infra": "GKE / GCP Infrastructure"}
    band_h = {"app": _APP_H, "svc": _SVC_H, "node": _NODE_H, "infra": _INF_H}
    tint = {"app": "#EEF6FD", "svc": "#EFF7EC", "node": "#EAF4E6", "infra": "#F1F8EE"}
    for key in ("app", "svc", "node", "infra"):
        t = L["band_top"][key]
        svg.append(f'<rect x="{_MARGIN}" y="{t-10}" width="{W-2*_MARGIN}" height="{band_h[key]+20}" '
                   f'rx="8" fill="{tint[key]}" stroke="#CFD8DC"/>')
        svg.append(f'<text x="{_MARGIN+6}" y="{t-14}" font-size="11" font-weight="700" '
                   f'fill="#5a7a5e">{band_lbl[key]}</text>')

    def anchor(n, side):
        if side == "top": return (n["x"]+n["w"]/2, n["y"])
        if side == "bottom": return (n["x"]+n["w"]/2, n["y"]+n["h"])
        return (n["x"]+n["w"]/2, n["y"]+n["h"]/2)

    def link(p1, p2, stroke, w, marker, dash=None):
        x1, y1 = p1; x2, y2 = p2
        d = (f'M{x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f}' if abs(x1-x2) < 1 else
             f'M{x1:.1f},{y1:.1f} C{(x1+x2)/2:.1f},{y1:.1f} {(x1+x2)/2:.1f},{y2:.1f} {x2:.1f},{y2:.1f}')
        da = f' stroke-dasharray="{dash}"' if dash else ''
        svg.append(f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{w}"{da} '
                   f'marker-end="url(#{marker})" opacity="0.75"/>')

    for src, dst, et in L["edges"]:
        a, b = nodes[src], nodes[dst]
        if et == "serving":
            link(anchor(a, "top"), anchor(b, "bottom"), "#5a8a53", 1.0, "open")
        elif et == "realization":
            link(anchor(a, "top"), anchor(b, "bottom"), "#37474F", 1.1, "tri", "5 4")
        elif et == "hosting":
            link(anchor(a, "bottom"), anchor(b, "top"), "#8aa", 1.0, "open", "2 3")

    for nid, n in nodes.items():
        x, y, w, h, kind = n["x"], n["y"], n["w"], n["h"], n["kind"]
        if kind == "app":
            fill, stroke = APP_FILL, APP_STROKE
            svg.append(f'<rect x="{x:.1f}" y="{y}" width="{w}" height="{h}" rx="3" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>')
            for dy in (10, 26):
                svg.append(f'<rect x="{x-5:.1f}" y="{y+dy}" width="10" height="7" fill="{fill}" stroke="{stroke}" stroke-width="1"/>')
        elif kind == "svc":
            fill, stroke = SVC_FILL, SVC_STROKE
            svg.append(f'<rect x="{x:.1f}" y="{y}" width="{w}" height="{h}" rx="{h/2:.0f}" fill="{fill}" stroke="{stroke}" stroke-width="1.3"/>')
        else:
            fill, stroke = (NODE_FILL, NODE_STROKE) if kind == "node" else (INFRA_FILL, INFRA_STROKE)
            svg.append(f'<rect x="{x:.1f}" y="{y}" width="{w}" height="{h}" rx="3" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>')
            # node glyph (box-in-corner)
            svg.append(f'<rect x="{x+w-16:.1f}" y="{y+5}" width="10" height="8" fill="none" stroke="{stroke}" stroke-width="1"/>')
        ty = y + (15 if kind != "node" else 16)
        for ln in _wrap(n["label"], 22, 2):
            svg.append(f'<text x="{x+8:.1f}" y="{ty}" font-size="10" font-weight="600" fill="#16251a">{_esc(ln)}</text>')
            ty += 12
        svg.append(f'<text x="{x+8:.1f}" y="{y+h-6}" font-size="8.5" fill="#4d6b50">{n["sub"]}</text>')

    # legend
    ly = H - _LEGEND_H + 20; lx = _MARGIN
    items = [("app", APP_FILL, APP_STROKE, "Application component"),
             ("svc", SVC_FILL, SVC_STROKE, "Technology service"),
             ("node", NODE_FILL, NODE_STROKE, "System software / node")]
    for shape, fill, stroke, lab in items:
        rx = 7 if shape == "svc" else 3
        svg.append(f'<rect x="{lx}" y="{ly-12}" width="20" height="14" rx="{rx}" fill="{fill}" stroke="{stroke}"/>')
        svg.append(f'<text x="{lx+26}" y="{ly}" font-size="10.5" fill="#37474F">{lab}</text>')
        lx += 200
    for lab, marker, dash in [("serving ▸", "open", None), ("realization ▷", "tri", "5 4")]:
        d = f' stroke-dasharray="{dash}"' if dash else ''
        svg.append(f'<line x1="{lx}" y1="{ly-5}" x2="{lx+26}" y2="{ly-5}" stroke="#37474F" stroke-width="1.3" marker-end="url(#{marker})"{d}/>')
        svg.append(f'<text x="{lx+32}" y="{ly-1}" font-size="10.5" fill="#37474F">{lab}</text>')
        lx += 160
    svg.append("</svg>")
    return "\n".join(svg) + "\n"


def draw_archimate_png(path="artifacts/technology_architecture.png"):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, Rectangle, FancyArrowPatch
    L = compute_layout(); nodes = L["nodes"]; W = L["width"]; H = L["height"]
    fig, ax = plt.subplots(figsize=(W/72, H/72))
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.invert_yaxis(); ax.axis("off")
    ax.text(_MARGIN, 30, "Ontology Repository — Technology Architecture (ArchiMate)",
            fontsize=15, fontweight="bold", color="#15301a")
    ax.text(_MARGIN, 52, f"Technology services & nodes realising the Level-{M.TARGET_LEVEL} "
            "application components · FalkorDB + Fuseki on GKE", fontsize=9, color="#4d6b50")
    band_lbl = {"app": "Application (consumers)", "svc": "Technology Services",
                "node": "System Software / Platforms", "infra": "GKE / GCP Infrastructure"}
    band_h = {"app": _APP_H, "svc": _SVC_H, "node": _NODE_H, "infra": _INF_H}
    tint = {"app": "#EEF6FD", "svc": "#EFF7EC", "node": "#EAF4E6", "infra": "#F1F8EE"}
    for key in ("app", "svc", "node", "infra"):
        t = L["band_top"][key]
        ax.add_patch(Rectangle((_MARGIN, t-10), W-2*_MARGIN, band_h[key]+20, facecolor=tint[key], edgecolor="#CFD8DC"))
        ax.text(_MARGIN+6, t-13, band_lbl[key], fontsize=9, fontweight="bold", color="#5a7a5e")

    def anchor(n, side):
        if side == "top": return (n["x"]+n["w"]/2, n["y"])
        if side == "bottom": return (n["x"]+n["w"]/2, n["y"]+n["h"])
        return (n["x"]+n["w"]/2, n["y"]+n["h"]/2)
    for src, dst, et in L["edges"]:
        a, b = nodes[src], nodes[dst]
        if et == "serving":
            p1, p2, col, ls = anchor(a, "top"), anchor(b, "bottom"), "#5a8a53", "-"
        elif et == "realization":
            p1, p2, col, ls = anchor(a, "top"), anchor(b, "bottom"), "#37474F", (0, (5, 4))
        else:
            p1, p2, col, ls = anchor(a, "bottom"), anchor(b, "top"), "#88aa88", (0, (2, 3))
        rad = 0.0 if abs(a["x"]-b["x"]) < 1 else 0.12
        ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", color=col, lw=1.0,
                     linestyle=ls, mutation_scale=10, alpha=0.75,
                     connectionstyle=f"arc3,rad={rad}", shrinkA=1, shrinkB=2))
    for nid, n in nodes.items():
        x, y, w, h, kind = n["x"], n["y"], n["w"], n["h"], n["kind"]
        if kind == "app":
            fc, ec = APP_FILL, APP_STROKE
            ax.add_patch(Rectangle((x, y), w, h, facecolor=fc, edgecolor=ec, lw=1.2))
            for dy in (10, 26):
                ax.add_patch(Rectangle((x-5, y+dy), 10, 7, facecolor=fc, edgecolor=ec, lw=1))
        elif kind == "svc":
            fc, ec = SVC_FILL, SVC_STROKE
            ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={h/2:.0f}", facecolor=fc, edgecolor=ec, lw=1.3))
        else:
            fc, ec = (NODE_FILL, NODE_STROKE) if kind == "node" else (INFRA_FILL, INFRA_STROKE)
            ax.add_patch(Rectangle((x, y), w, h, facecolor=fc, edgecolor=ec, lw=1.2))
            ax.add_patch(Rectangle((x+w-16, y+5), 10, 8, facecolor="none", edgecolor=ec, lw=1))
        ty = y + (14 if kind != "node" else 15)
        for ln in _wrap(n["label"], 22, 2):
            ax.text(x+8, ty, ln, fontsize=8, fontweight="bold", color="#16251a"); ty += 11
        ax.text(x+8, y+h-6, n["sub"], fontsize=7, color="#4d6b50")
    fig.savefig(path, dpi=110, bbox_inches="tight"); plt.close(fig)
    return path


# --------------------------------------------------------------------------- #
# Requirements catalogue (Markdown)
# --------------------------------------------------------------------------- #
def to_requirements_catalog_md():
    from collections import Counter
    out = []; w = out.append
    by_plat = Counter(r.platform for r in M.REQUIREMENTS)
    by_prio = Counter(r.priority for r in M.REQUIREMENTS)
    w("# Technical Requirements Catalogue (technology-agnostic)\n")
    w(f"**Vendor- and cloud-product-neutral** technical requirements for the Ontology Repository "
      f"technology platform at **EKGF maturity Level {M.TARGET_LEVEL} — “{M.TARGET_LEVEL_NAME}”**. "
      f"They state *what* any conforming product must provide; the concrete realisation for "
      f"**FalkorDB** and **Apache Jena Fuseki** on **GCP** is given separately in the "
      f"`mapping/` documents.\n")
    w(f"**Totals:** {len(M.REQUIREMENTS)} requirements — "
      + ", ".join(f"{k}: {v}" for k, v in by_plat.items())
      + f"  ·  priorities — MUST: {by_prio['MUST']}, SHOULD: {by_prio['SHOULD']}, MAY: {by_prio['MAY']}.\n")
    w("Priority follows RFC-2119 (**MUST** = mandatory, **SHOULD** = strongly recommended, "
      "**MAY** = optional/forward-looking). ID prefixes: `TR.PG` property graph · `TR.SK` semantic "
      "knowledge graph · `TR.CN` cloud-native platform · `TR.SP` platform services.\n")
    w("| Agnostic category | Mapped to (GCP context) |\n|---|---|\n"
      "| Property Graph Platform (`TR.PG.*`) | **FalkorDB** — `mapping/MAPPING_FALKORDB_GCP.md` |\n"
      "| Semantic Knowledge Graph Platform (`TR.SK.*`) | **Fuseki** — `mapping/MAPPING_FUSEKI_GCP.md` |\n"
      "| Cloud-Native Platform + Platform Services (`TR.CN.*`, `TR.SP.*`) | **GCP** — `mapping/MAPPING_PLATFORM_GCP.md` |\n")
    for plat in M.PLATFORMS:
        reqs = M.requirements_for(plat)
        w(f"## {plat} ({len(reqs)} requirements)\n")
        for r in reqs:
            comps = ", ".join(r.components) or "—"
            caps = ", ".join(r.capabilities) or "—"
            w(f"### {r.id} · {r.title}  `[{r.priority}]`\n")
            w(f"**Area:** {r.area}  ·  **Supports components:** {comps}  ·  **Capabilities:** {caps}\n")
            w(f"**Requirement.** {r.statement}\n")
            w(f"**Rationale.** {r.rationale}\n")
            w(f"**Verification.** {r.verification}\n")
    return "\n".join(out)


def to_mapping_md(platforms, tech, title, intro):
    """Generate a technology-mapping document: each agnostic requirement in the
    given platform categories → its realisation for ``tech`` in the GCP context."""
    out = []; w = out.append
    reqs = [r for r in M.REQUIREMENTS if r.platform in platforms]
    w(f"# {title}\n")
    w(intro + "\n")
    w(f"Maps **{len(reqs)}** technology-agnostic requirements (see `../REQUIREMENTS_CATALOG.md`) to "
      f"their concrete realisation. **`[priority]`** is carried from the agnostic requirement.\n")
    last_platform = None
    for r in reqs:
        if r.platform != last_platform:
            w(f"## {r.platform}\n")
            last_platform = r.platform
        ms = [m for m in M.MAPPINGS_BY_REQ.get(r.id, []) if m.technology == tech]
        m = ms[0] if ms else None
        w(f"### {r.id} · {r.title}  `[{r.priority}]`\n")
        w(f"**Agnostic requirement.** {r.statement}\n")
        if m:
            w(f"**{tech} realisation.** {m.realization}\n")
            w(f"**GCP-context specifics.** {m.specifics}\n")
        else:
            w(f"_No {tech}-specific mapping; see the platform mapping._\n")
    return "\n".join(out)


def to_traceability_md():
    out = []; w = out.append
    w("# Traceability — Capability → Application → Technology → Requirement\n")
    w("## Technology service → application components served\n")
    w("| Technology service | Serves application components |\n|---|---|")
    for s in M.TECH_SERVICES:
        w(f"| {s.id} {s.name} | {', '.join(s.serves_components)} |")
    w("\n## Requirement → application components → capabilities\n")
    w("| Req | Platform | Area | Prio | Components | Capabilities |\n|---|---|---|---|---|---|")
    for r in M.REQUIREMENTS:
        caps = ", ".join(f"{c} {CAPABILITY_BY_ID[c].name}" if c in CAPABILITY_BY_ID else c
                         for c in r.capabilities) or "—"
        w(f"| {r.id} | {r.platform} | {r.area} | {r.priority} | {', '.join(r.components) or '—'} | {caps} |")
    w("\n## Application component → realising technology nodes\n")
    w("| Application component | Technology service(s) | Realising node(s) |\n|---|---|---|")
    for c in app.COMPONENTS:
        svcs = [s for s in M.TECH_SERVICES if c.id in s.serves_components]
        node_ids = sorted({n.name
                           for s in svcs for n in M.TECH_NODES
                           if n.realizes and n.realizes[0] == s.id})
        if svcs:
            w(f"| {c.id} {c.name} | {', '.join(s.id for s in svcs)} | {', '.join(node_ids)} |")
    return "\n".join(out)
