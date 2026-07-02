"""Generators for the Ontology Repository Capability Model.

Produces, from ``capability_model.py``:

* ``build_taxonomy_graph`` / ``build_ontology_graph`` — ``networkx`` graphs;
* ``to_mermaid_taxonomy`` / ``to_mermaid_ontology`` — Mermaid diagram sources;
* ``to_archimate_svg`` — a hand-rendered ArchiMate-style capability map (SVG);
* ``to_turtle`` — an RDF/OWL/SKOS serialisation (via ``rdflib``);
* ``draw_ontology_networkx`` — a matplotlib rendering of the capability ontology.
"""

from __future__ import annotations

import math
import textwrap

import networkx as nx

from .capability_model import (
    CAPABILITIES,
    CAPABILITY_BY_ID,
    CATEGORIES,
    CATEGORY_BY_ID,
    DOMAINS,
    EKGF_LEVELS,
    categories_in,
    capabilities_in,
)

# Warm 5-step maturity ramp (light enough for black labels).
LEVEL_COLOR: dict[int, str] = {
    1: "#FFF6C8",  # pale yellow
    2: "#FFE08A",
    3: "#FFB860",
    4: "#FF8A5C",
    5: "#E0667A",  # warm red
}
DOMAIN_COLOR = {"Business": "#FFE0B2", "Technology": "#BBDEFB"}


# --------------------------------------------------------------------------- #
# networkx graphs
# --------------------------------------------------------------------------- #
def build_taxonomy_graph() -> nx.DiGraph:
    """Strict broader→narrower tree: ROOT → Domain → Category → Capability."""
    g = nx.DiGraph(name="capability-taxonomy")
    root = "ROOT::Ontology Repository Capabilities"
    g.add_node(root, kind="root", label="Ontology Repository\nCapabilities")
    for domain in DOMAINS:
        dnode = f"DOMAIN::{domain}"
        g.add_node(dnode, kind="domain", label=f"{domain} Capabilities", domain=domain)
        g.add_edge(root, dnode, rel="narrower")
        for cat in categories_in(domain):
            cnode = f"CAT::{cat.id}"
            g.add_node(cnode, kind="category", label=cat.name, domain=domain, cat_id=cat.id)
            g.add_edge(dnode, cnode, rel="narrower")
            for cap in capabilities_in(cat.id):
                g.add_node(
                    cap.id, kind="capability", label=cap.name, domain=domain,
                    level=cap.maturity_level, pillar=cap.ekgf_pillar,
                )
                g.add_edge(cnode, cap.id, rel="narrower")
    return g


def build_ontology_graph() -> nx.MultiDiGraph:
    """Typed capability ontology: capabilities + dependsOn/supports/governedBy."""
    g = nx.MultiDiGraph(name="capability-ontology")
    for cap in CAPABILITIES:
        g.add_node(
            cap.id, label=cap.name, domain=cap.domain, category=cap.category,
            level=cap.maturity_level, pillar=cap.ekgf_pillar,
            requirement=cap.requirement,
        )
    for cap in CAPABILITIES:
        for t in cap.depends_on:
            g.add_edge(cap.id, t, rel="dependsOn")
            g.add_edge(t, cap.id, rel="enables")  # inverse
        for t in cap.supports:
            g.add_edge(cap.id, t, rel="supports")
        for t in cap.governed_by:
            g.add_edge(cap.id, t, rel="governedBy")
    return g


# --------------------------------------------------------------------------- #
# Mermaid
# --------------------------------------------------------------------------- #
def _mm_id(cap_id: str) -> str:
    return cap_id.replace(".", "_")


def to_mermaid_taxonomy() -> str:
    """Flowchart of the capability taxonomy, grouped, annotated with EKGF level."""
    lines = [
        "%% Ontology Repository Capability Model - Taxonomy + EKGF maturity level",
        "flowchart TB",
        "  classDef biz fill:#FFE0B2,stroke:#E65100,color:#000;",
        "  classDef tech fill:#BBDEFB,stroke:#0D47A1,color:#000;",
        "  classDef cat fill:#ECEFF1,stroke:#455A64,color:#000,font-weight:bold;",
        "  ROOT([\"Ontology Repository Capabilities\"]):::cat",
    ]
    for domain in DOMAINS:
        dcls = "biz" if domain == "Business" else "tech"
        lines.append(f"  subgraph DOM_{domain}[\"{domain} Capabilities\"]")
        lines.append("    direction TB")
        for cat in categories_in(domain):
            lines.append(f"    subgraph CAT_{cat.id}[\"{cat.id} · {cat.name}\"]")
            lines.append("      direction TB")
            for cap in capabilities_in(cat.id):
                nid = _mm_id(cap.id)
                lvl = cap.maturity_level
                label = f"{cap.id} {cap.name}<br/><i>L{lvl} · {cap.ekgf_pillar}</i>"
                lines.append(f'      {nid}["{label}"]:::{dcls}')
            lines.append("    end")
        lines.append("  end")
        lines.append(f"  ROOT --> DOM_{domain}")
    return "\n".join(lines) + "\n"


def to_mermaid_ontology() -> str:
    """Flowchart of the capability ontology relations (dependsOn / supports)."""
    lines = [
        "%% Ontology Repository Capability Model - Ontology relations",
        "flowchart LR",
        "  classDef biz fill:#FFE0B2,stroke:#E65100,color:#000;",
        "  classDef tech fill:#BBDEFB,stroke:#0D47A1,color:#000;",
    ]
    for cap in CAPABILITIES:
        nid = _mm_id(cap.id)
        dcls = "biz" if cap.domain == "Business" else "tech"
        lines.append(f'  {nid}["{cap.id}<br/>{cap.name}<br/><i>L{cap.maturity_level}</i>"]:::{dcls}')
    lines.append("  %% dependsOn (solid), supports (dotted), governedBy (thick)")
    for cap in CAPABILITIES:
        for t in cap.depends_on:
            lines.append(f"  {_mm_id(cap.id)} -->|dependsOn| {_mm_id(t)}")
        for t in cap.supports:
            lines.append(f"  {_mm_id(cap.id)} -.->|supports| {_mm_id(t)}")
        for t in cap.governed_by:
            lines.append(f"  {_mm_id(cap.id)} ==>|governedBy| {_mm_id(t)}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# ArchiMate-style SVG capability map
# --------------------------------------------------------------------------- #
# Layout constants
_CAP_W, _CAP_H = 210, 56
_GAP = 12
_PER_ROW = 2
_CAT_PAD = 12
_CAT_HEADER = 26
_DOM_PAD = 14
_DOM_HEADER = 34
_COL_GAP = 30
_MARGIN = 24
_TITLE_H = 64


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _wrap(text: str, width: int = 26, max_lines: int = 2) -> list[str]:
    lines = textwrap.wrap(text, width=width)
    if len(lines) > max_lines:
        lines = lines[: max_lines]
        lines[-1] = lines[-1][: width - 1] + "…"
    return lines


def _cap_svg(cap, x: float, y: float) -> str:
    """Render one ArchiMate capability element at (x, y)."""
    fill = LEVEL_COLOR[cap.maturity_level]
    parts = [
        f'<g>',
        f'<rect x="{x}" y="{y}" width="{_CAP_W}" height="{_CAP_H}" rx="7" ry="7" '
        f'fill="{fill}" stroke="#6D4C41" stroke-width="1.2"/>',
        # ArchiMate capability glyph (rounded rect with a bar) top-right
        f'<rect x="{x + _CAP_W - 24}" y="{y + 6}" width="16" height="12" rx="2" '
        f'fill="none" stroke="#6D4C41" stroke-width="1.1"/>',
        f'<line x1="{x + _CAP_W - 24}" y1="{y + 11}" x2="{x + _CAP_W - 8}" y2="{y + 11}" '
        f'stroke="#6D4C41" stroke-width="1.1"/>',
    ]
    name_lines = _wrap(cap.name, width=24, max_lines=2)
    ty = y + 18
    for ln in name_lines:
        parts.append(
            f'<text x="{x + 10}" y="{ty}" font-family="Segoe UI, Arial" '
            f'font-size="11.5" font-weight="600" fill="#212121">{_esc(ln)}</text>'
        )
        ty += 13
    parts.append(
        f'<text x="{x + 10}" y="{y + _CAP_H - 8}" font-family="Segoe UI, Arial" '
        f'font-size="9.5" fill="#5D4037">{cap.id} · L{cap.maturity_level} {EKGF_LEVELS[cap.maturity_level]} · {cap.ekgf_pillar}</text>'
    )
    parts.append("</g>")
    return "\n".join(parts)


def _category_height(n_caps: int) -> float:
    rows = max(1, math.ceil(n_caps / _PER_ROW))
    return _CAT_HEADER + _CAT_PAD + rows * (_CAP_H + _GAP)


def _domain_inner_width() -> float:
    return _PER_ROW * _CAP_W + (_PER_ROW - 1) * _GAP + 2 * _CAT_PAD


def to_archimate_svg() -> str:
    """Build an ArchiMate-style capability map as a standalone SVG string."""
    dom_inner = _domain_inner_width()
    col_w = dom_inner + 2 * _DOM_PAD
    width = 2 * col_w + _COL_GAP + 2 * _MARGIN

    # compute per-domain content height
    dom_heights = {}
    for domain in DOMAINS:
        h = _DOM_HEADER + _DOM_PAD
        for cat in categories_in(domain):
            h += _category_height(len(capabilities_in(cat.id))) + _GAP
        dom_heights[domain] = h + _DOM_PAD
    content_h = max(dom_heights.values())
    legend_h = 56
    height = _TITLE_H + content_h + legend_h + 2 * _MARGIN

    svg: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="Segoe UI, Arial">',
        f'<rect x="0" y="0" width="{width:.0f}" height="{height:.0f}" fill="#FFFFFF"/>',
        # title
        f'<text x="{_MARGIN}" y="32" font-size="20" font-weight="700" fill="#212121">'
        f'Ontology Repository — Capability Map (ArchiMate)</text>',
        f'<text x="{_MARGIN}" y="52" font-size="12" fill="#616161">'
        f'Capability elements grouped by domain &amp; category · fill colour = target EKGF EKG/MM maturity level</text>',
    ]

    col_x = {DOMAINS[0]: _MARGIN, DOMAINS[1]: _MARGIN + col_w + _COL_GAP}
    top = _TITLE_H + _MARGIN
    for domain in DOMAINS:
        x0 = col_x[domain]
        dh = dom_heights[domain]
        # domain swimlane
        svg.append(
            f'<rect x="{x0}" y="{top}" width="{col_w}" height="{dh}" rx="10" '
            f'fill="{DOMAIN_COLOR[domain]}" fill-opacity="0.35" stroke="#9E9E9E" stroke-width="1"/>'
        )
        svg.append(
            f'<text x="{x0 + 12}" y="{top + 23}" font-size="15" font-weight="700" '
            f'fill="#263238">{domain} Capabilities</text>'
        )
        cy = top + _DOM_HEADER + _DOM_PAD
        for cat in categories_in(domain):
            caps = capabilities_in(cat.id)
            ch = _category_height(len(caps))
            cx = x0 + _DOM_PAD
            # category group box
            svg.append(
                f'<rect x="{cx}" y="{cy}" width="{dom_inner}" height="{ch}" rx="6" '
                f'fill="#FFFFFF" fill-opacity="0.55" stroke="#78909C" stroke-width="1" stroke-dasharray="4 3"/>'
            )
            svg.append(
                f'<text x="{cx + 10}" y="{cy + 17}" font-size="12" font-weight="700" '
                f'fill="#37474F">{cat.id} · {_esc(cat.name)}</text>'
            )
            # capability grid
            gx0 = cx + _CAT_PAD
            gy0 = cy + _CAT_HEADER
            for i, cap in enumerate(caps):
                r, c = divmod(i, _PER_ROW)
                px = gx0 + c * (_CAP_W + _GAP)
                py = gy0 + r * (_CAP_H + _GAP)
                svg.append(_cap_svg(cap, px, py))
            cy += ch + _GAP

    # legend
    ly = _TITLE_H + _MARGIN + content_h + 18
    svg.append(f'<text x="{_MARGIN}" y="{ly}" font-size="12" font-weight="700" fill="#212121">'
               f'EKGF maturity level:</text>')
    lx = _MARGIN + 150
    for lvl in range(1, 6):
        svg.append(
            f'<rect x="{lx}" y="{ly - 12}" width="16" height="16" rx="3" '
            f'fill="{LEVEL_COLOR[lvl]}" stroke="#6D4C41"/>'
        )
        svg.append(
            f'<text x="{lx + 22}" y="{ly}" font-size="11" fill="#424242">'
            f'L{lvl} {EKGF_LEVELS[lvl]}</text>'
        )
        lx += 150
    svg.append("</svg>")
    return "\n".join(svg) + "\n"


def to_requirements_markdown() -> str:
    """Generate the comprehensive requirements document from the model."""
    from .capability_model import EKGF_LEVELS

    out: list[str] = []
    w = out.append
    w("# Ontology Repository Requirements — Capability Model\n")
    w("Comprehensive requirements for an **ontology-engineering practice**, expressed as "
      "**business** and **technology capabilities**, arranged as a **taxonomy** and an "
      "**ontology**, and mapped to the **EKGF Enterprise Knowledge Graph Maturity Model "
      "(EKG/MM v1.0)**.\n")
    w("> Note: the referenced Gemini conversation could not be retrieved automatically "
      "(the share link resolves to a Google sign-in shell, not public content). This model "
      "is therefore grounded in the public EKGF maturity model and ontology-engineering "
      "practice; paste the conversation text to fold in its specifics.\n")
    w(f"**Totals:** {len(CAPABILITIES)} capabilities across {len(CATEGORIES)} categories "
      f"and {len(DOMAINS)} domains.\n")

    w("## EKGF maturity levels\n")
    w("| Level | Name | Meaning (EKG/MM) |")
    w("|---|---|---|")
    meanings = {
        1: "Just starting / piloting an Enterprise Knowledge Graph.",
        2: "EKG implemented; building out capabilities and integrations.",
        3: "EKG fully implemented with org-wide processes and infrastructure.",
        4: "EKG used as a key strategic asset driving innovation and decisions.",
        5: "EKG fully integrated into operations as part of the wider ecosystem.",
    }
    for n, name in EKGF_LEVELS.items():
        w(f"| L{n} | {name} | {meanings[n]} |")
    w("")

    w("## Requirements by domain → category\n")
    for domain in DOMAINS:
        w(f"### {domain} capabilities\n")
        for cat in categories_in(domain):
            w(f"#### {cat.id} · {cat.name}\n")
            w(f"*{cat.description}*\n")
            w("| ID | Capability | Requirement | EKGF pillar | Target level | Depends on |")
            w("|----|------------|-------------|-------------|--------------|------------|")
            for cap in capabilities_in(cat.id):
                deps = ", ".join(cap.depends_on) or "—"
                w(f"| {cap.id} | **{cap.name}** | {cap.requirement} | {cap.ekgf_pillar} "
                  f"| L{cap.maturity_level} {cap.level_name} | {deps} |")
            w("")

    w("## Maturity roadmap (capabilities grouped by target EKGF level)\n")
    for n, name in EKGF_LEVELS.items():
        caps = [c for c in CAPABILITIES if c.maturity_level == n]
        ids = ", ".join(f"{c.id} {c.name}" for c in caps)
        w(f"- **L{n} {name}** ({len(caps)}): {ids}")
    w("")

    w("## Ontology relations\n")
    w("Beyond the broader/narrower taxonomy, capabilities are linked by typed relations:\n")
    w("- `dependsOn` — a capability requires another to be effective (transitive).")
    w("- `enables` — inverse of `dependsOn`.")
    w("- `supports` — a technology capability supports a business capability/outcome.")
    w("- `governedBy` — a capability is governed by a governance capability.\n")
    w("| Capability | dependsOn | supports | governedBy |")
    w("|---|---|---|---|")
    for cap in CAPABILITIES:
        if cap.depends_on or cap.supports or cap.governed_by:
            w(f"| {cap.id} {cap.name} | {', '.join(cap.depends_on) or '—'} "
              f"| {', '.join(cap.supports) or '—'} | {', '.join(cap.governed_by) or '—'} |")
    w("")

    w("## Artifacts\n")
    w("- `artifacts/capability_taxonomy.mmd` — Mermaid taxonomy (domain→category→capability, with EKGF level).")
    w("- `artifacts/capability_ontology.mmd` — Mermaid ontology-relations diagram.")
    w("- `artifacts/capability_archimate.svg` — ArchiMate capability map (SVG, maturity heat-map).")
    w("- `artifacts/capability_archimate.png` — raster twin of the ArchiMate map.")
    w("- `artifacts/capability_ontology.ttl` — RDF/OWL/SKOS serialisation (rdflib).")
    w("- `artifacts/capability_ontology.png` — networkx visualisation of the capability ontology.")
    w("")
    return "\n".join(out)


def draw_archimate_png(path: str = "artifacts/capability_archimate.png"):
    """Raster (matplotlib) twin of :func:`to_archimate_svg` — same layout/colours.

    Useful as a quick-view image and to verify the SVG layout.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.patches as mpatches
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    dom_inner = _domain_inner_width()
    col_w = dom_inner + 2 * _DOM_PAD
    width = 2 * col_w + _COL_GAP + 2 * _MARGIN
    dom_heights = {}
    for domain in DOMAINS:
        h = _DOM_HEADER + _DOM_PAD
        for cat in categories_in(domain):
            h += _category_height(len(capabilities_in(cat.id))) + _GAP
        dom_heights[domain] = h + _DOM_PAD
    content_h = max(dom_heights.values())
    height = _TITLE_H + content_h + 56 + 2 * _MARGIN

    fig, ax = plt.subplots(figsize=(width / 72, height / 72))
    ax.set_xlim(0, width); ax.set_ylim(0, height); ax.invert_yaxis(); ax.axis("off")

    def box(x, y, w, h, **kw):
        ax.add_patch(FancyBboxPatch((x, y), w, h,
                     boxstyle=f"round,pad=0,rounding_size={kw.pop('r', 6)}", **kw))

    ax.text(_MARGIN, 30, "Ontology Repository — Capability Map (ArchiMate)",
            fontsize=16, fontweight="bold", va="center")
    ax.text(_MARGIN, 50, "Capability elements grouped by domain & category · "
            "fill colour = target EKGF EKG/MM maturity level", fontsize=9, color="#616161")

    col_x = {DOMAINS[0]: _MARGIN, DOMAINS[1]: _MARGIN + col_w + _COL_GAP}
    top = _TITLE_H + _MARGIN
    for domain in DOMAINS:
        x0 = col_x[domain]
        box(x0, top, col_w, dom_heights[domain], r=10, facecolor=DOMAIN_COLOR[domain],
            alpha=0.35, edgecolor="#9E9E9E", lw=1)
        ax.text(x0 + 12, top + 20, f"{domain} Capabilities", fontsize=13, fontweight="bold",
                color="#263238")
        cy = top + _DOM_HEADER + _DOM_PAD
        for cat in categories_in(domain):
            caps = capabilities_in(cat.id)
            ch = _category_height(len(caps))
            cx = x0 + _DOM_PAD
            box(cx, cy, dom_inner, ch, r=6, facecolor="white", alpha=0.55,
                edgecolor="#78909C", lw=1, linestyle="--")
            ax.text(cx + 10, cy + 15, f"{cat.id} · {cat.name}", fontsize=10,
                    fontweight="bold", color="#37474F")
            gx0 = cx + _CAT_PAD; gy0 = cy + _CAT_HEADER
            for i, cap in enumerate(caps):
                r, c = divmod(i, _PER_ROW)
                px = gx0 + c * (_CAP_W + _GAP); py = gy0 + r * (_CAP_H + _GAP)
                box(px, py, _CAP_W, _CAP_H, r=7, facecolor=LEVEL_COLOR[cap.maturity_level],
                    edgecolor="#6D4C41", lw=1.1)
                # capability glyph
                box(px + _CAP_W - 24, py + 6, 16, 12, r=2, facecolor="none",
                    edgecolor="#6D4C41", lw=1)
                ax.plot([px + _CAP_W - 24, px + _CAP_W - 8], [py + 11, py + 11],
                        color="#6D4C41", lw=1)
                for j, ln in enumerate(_wrap(cap.name, 24, 2)):
                    ax.text(px + 10, py + 16 + j * 13, ln, fontsize=8.5, fontweight="bold",
                            color="#212121")
                ax.text(px + 10, py + _CAP_H - 8,
                        f"{cap.id} · L{cap.maturity_level} · {cap.ekgf_pillar}",
                        fontsize=7, color="#5D4037")
            cy += ch + _GAP

    ly = top + content_h + 26
    ax.text(_MARGIN, ly, "EKGF maturity level:", fontsize=10, fontweight="bold")
    lx = _MARGIN + 140
    for lvl in range(1, 6):
        box(lx, ly - 11, 16, 16, r=3, facecolor=LEVEL_COLOR[lvl], edgecolor="#6D4C41")
        ax.text(lx + 22, ly, f"L{lvl} {EKGF_LEVELS[lvl]}", fontsize=8.5, color="#424242")
        lx += 150
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return path


# --------------------------------------------------------------------------- #
# RDF / OWL / SKOS  (rdflib)
# --------------------------------------------------------------------------- #
def to_turtle() -> str:
    """Serialise the capability model as RDF (OWL ontology + SKOS taxonomy)."""
    from rdflib import Graph, Literal, Namespace, BNode, URIRef
    from rdflib.namespace import OWL, RDF, RDFS, SKOS, DCTERMS, XSD

    OEC = Namespace("https://example.org/oec#")              # vocabulary
    CAP = Namespace("https://example.org/oec/cap/")          # capability individuals
    EKGF = Namespace("https://maturity.ekgf.org/def#")

    g = Graph()
    g.bind("oec", OEC); g.bind("cap", CAP); g.bind("ekgf", EKGF)
    g.bind("owl", OWL); g.bind("skos", SKOS); g.bind("dct", DCTERMS)

    # ---- ontology header ----
    onto = URIRef("https://example.org/oec")
    g.add((onto, RDF.type, OWL.Ontology))
    g.add((onto, DCTERMS.title, Literal("Ontology Repository Capability Ontology")))
    g.add((onto, RDFS.comment, Literal(
        "Business and technology capabilities for an ontology-engineering practice, "
        "mapped to the EKGF EKG Maturity Model.")))

    # ---- classes ----
    for cls, label in [
        (OEC.Capability, "Capability"),
        (OEC.CapabilityCategory, "Capability Category"),
        (OEC.CapabilityDomain, "Capability Domain"),
    ]:
        g.add((cls, RDF.type, OWL.Class)); g.add((cls, RDFS.label, Literal(label)))
    g.add((OEC.BusinessCapability, RDFS.subClassOf, OEC.Capability))
    g.add((OEC.TechnologyCapability, RDFS.subClassOf, OEC.Capability))
    g.add((OEC.BusinessCapability, RDF.type, OWL.Class))
    g.add((OEC.TechnologyCapability, RDF.type, OWL.Class))

    # ---- object/data properties ----
    for prop, label, inv in [
        (OEC.dependsOn, "depends on", OEC.enables),
        (OEC.enables, "enables", OEC.dependsOn),
        (OEC.supports, "supports", None),
        (OEC.governedBy, "governed by", None),
        (OEC.inCategory, "in category", None),
        (OEC.inDomain, "in domain", None),
        (OEC.targetMaturityLevel, "target maturity level", None),
        (EKGF.pillar, "EKGF pillar", None),
    ]:
        g.add((prop, RDF.type, OWL.ObjectProperty)); g.add((prop, RDFS.label, Literal(label)))
        if inv is not None:
            g.add((prop, OWL.inverseOf, inv))
    g.add((OEC.dependsOn, RDF.type, OWL.TransitiveProperty))
    g.add((OEC.requirementText, RDF.type, OWL.DatatypeProperty))

    # ---- EKGF maturity levels + pillars ----
    g.add((EKGF.MaturityLevel, RDF.type, OWL.Class))
    level_uri = {}
    for n, name in EKGF_LEVELS.items():
        u = EKGF[f"Level{n}"]
        level_uri[n] = u
        g.add((u, RDF.type, EKGF.MaturityLevel))
        g.add((u, RDFS.label, Literal(f"L{n} {name}")))
        g.add((u, OEC.levelNumber, Literal(n, datatype=XSD.integer)))
    g.add((EKGF.Pillar, RDF.type, OWL.Class))
    pillar_uri = {}
    for p in ("Business", "Organization", "Data", "Technology"):
        u = EKGF[f"Pillar_{p}"]; pillar_uri[p] = u
        g.add((u, RDF.type, EKGF.Pillar)); g.add((u, RDFS.label, Literal(f"{p} pillar")))

    # ---- SKOS taxonomy scheme ----
    scheme = OEC.CapabilityScheme
    g.add((scheme, RDF.type, SKOS.ConceptScheme))
    g.add((scheme, RDFS.label, Literal("Ontology Repository Capability Taxonomy")))

    domain_concept = {}
    for domain in DOMAINS:
        dc = CAP[f"domain-{domain.lower()}"]
        domain_concept[domain] = dc
        g.add((dc, RDF.type, SKOS.Concept)); g.add((dc, RDF.type, OEC.CapabilityDomain))
        g.add((dc, SKOS.prefLabel, Literal(f"{domain} Capabilities")))
        g.add((dc, SKOS.topConceptOf, scheme)); g.add((scheme, SKOS.hasTopConcept, dc))

    for cat in CATEGORIES:
        cu = CAP[f"cat-{cat.id}"]
        g.add((cu, RDF.type, SKOS.Concept)); g.add((cu, RDF.type, OEC.CapabilityCategory))
        g.add((cu, SKOS.prefLabel, Literal(cat.name)))
        g.add((cu, DCTERMS.description, Literal(cat.description)))
        g.add((cu, SKOS.inScheme, scheme))
        g.add((cu, SKOS.broader, domain_concept[cat.domain]))

    # ---- capabilities ----
    def cu(cap_id: str) -> URIRef:
        return CAP[cap_id.replace(".", "-")]

    for cap in CAPABILITIES:
        u = cu(cap.id)
        cls = OEC.BusinessCapability if cap.domain == "Business" else OEC.TechnologyCapability
        g.add((u, RDF.type, cls)); g.add((u, RDF.type, SKOS.Concept))
        g.add((u, SKOS.prefLabel, Literal(cap.name)))
        g.add((u, SKOS.notation, Literal(cap.id)))
        g.add((u, DCTERMS.description, Literal(cap.description)))
        g.add((u, OEC.requirementText, Literal(cap.requirement)))
        g.add((u, OEC.inCategory, CAP[f"cat-{cap.category}"]))
        g.add((u, OEC.inDomain, domain_concept[cap.domain]))
        g.add((u, SKOS.broader, CAP[f"cat-{cap.category}"]))
        g.add((u, SKOS.inScheme, scheme))
        g.add((u, OEC.targetMaturityLevel, level_uri[cap.maturity_level]))
        g.add((u, EKGF.pillar, pillar_uri[cap.ekgf_pillar]))
        for t in cap.depends_on:
            g.add((u, OEC.dependsOn, cu(t)))
        for t in cap.supports:
            g.add((u, OEC.supports, cu(t)))
        for t in cap.governed_by:
            g.add((u, OEC.governedBy, cu(t)))

    return g.serialize(format="turtle")


# --------------------------------------------------------------------------- #
# networkx visualisation of the capability ontology
# --------------------------------------------------------------------------- #
def draw_ontology_networkx(path: str = "artifacts/capability_ontology.png"):
    """Draw the capability ontology: x = EKGF maturity level, split by domain.

    dependsOn edges are grey solid; supports edges blue dashed; governedBy red.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.patches as mpatches
    import matplotlib.pyplot as plt

    g = build_ontology_graph()

    # layered layout: x by maturity level, y stacked within (domain band)
    pos: dict[str, tuple[float, float]] = {}
    for domain, y_base, y_dir in (("Business", 0.0, +1.0), ("Technology", -0.6, -1.0)):
        for lvl in range(1, 6):
            caps = [c for c in CAPABILITIES if c.domain == domain and c.maturity_level == lvl]
            for i, cap in enumerate(caps):
                # spread vertically within the level column, away from the centre line
                offset = (i + 1) * 0.9 * y_dir
                pos[cap.id] = (lvl * 3.0, y_base + offset)

    node_colors = ["#FB8C00" if CAPABILITY_BY_ID[n].domain == "Business" else "#1E88E5"
                   for n in g.nodes]

    fig, ax = plt.subplots(figsize=(18, 12))

    # level background bands
    for lvl in range(1, 6):
        ax.axvspan(lvl * 3.0 - 1.4, lvl * 3.0 + 1.4, color="#ECEFF1" if lvl % 2 else "#F5F5F5",
                   zorder=0)
        ax.text(lvl * 3.0, max(p[1] for p in pos.values()) + 1.4,
                f"L{lvl}\n{EKGF_LEVELS[lvl]}", ha="center", va="bottom",
                fontsize=11, fontweight="bold", color="#37474F")
    ax.axhline(-0.3, color="#B0BEC5", lw=1, ls=":")
    ax.text(1.0, 0.2, "BUSINESS", fontsize=12, fontweight="bold", color="#E65100", alpha=0.5)
    ax.text(1.0, -0.9, "TECHNOLOGY", fontsize=12, fontweight="bold", color="#0D47A1", alpha=0.5)

    # edges by type
    def edges(rel):
        return [(u, v) for u, v, d in g.edges(data=True) if d["rel"] == rel]

    nx.draw_networkx_edges(g, pos, edgelist=edges("dependsOn"), ax=ax,
                           edge_color="#90A4AE", arrows=True, arrowsize=12,
                           width=1.1, connectionstyle="arc3,rad=0.08", alpha=0.7)
    nx.draw_networkx_edges(g, pos, edgelist=edges("supports"), ax=ax,
                           edge_color="#1E88E5", style="dashed", arrows=True,
                           arrowsize=12, width=1.2, connectionstyle="arc3,rad=0.12")
    nx.draw_networkx_edges(g, pos, edgelist=edges("governedBy"), ax=ax,
                           edge_color="#C62828", style="dotted", arrows=True,
                           arrowsize=12, width=1.2, connectionstyle="arc3,rad=0.12")

    nx.draw_networkx_nodes(g, pos, node_color=node_colors, node_size=950,
                           edgecolors="black", linewidths=0.8, ax=ax, alpha=0.95)
    labels = {n: n for n in g.nodes}  # short ids keep it readable
    nx.draw_networkx_labels(g, pos, labels=labels, font_size=7.5,
                            font_color="white", font_weight="bold", ax=ax)

    legend = [
        mpatches.Patch(color="#FB8C00", label="Business capability"),
        mpatches.Patch(color="#1E88E5", label="Technology capability"),
        plt.Line2D([0], [0], color="#90A4AE", lw=1.4, label="dependsOn"),
        plt.Line2D([0], [0], color="#1E88E5", lw=1.4, ls="--", label="supports"),
        plt.Line2D([0], [0], color="#C62828", lw=1.4, ls=":", label="governedBy"),
    ]
    ax.legend(handles=legend, loc="lower right", fontsize=10, framealpha=0.95)
    ax.set_title("Ontology Repository Capability Ontology\n"
                 "(node id = capability · x-axis = target EKGF maturity level)",
                 fontsize=15, fontweight="bold")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return path
