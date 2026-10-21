"""Deterministic layered SVG of a view (static artifacts: PR comments, RESULTS.md).

Input is the contract JSON (``contract.to_playground``), so the picture shows exactly
what the API returned. Layout: longest-path layering over ``subClassOf``/``broader``
(parents above children), then four barycentre sweeps to reduce crossings, ties broken
by label. No cairo or Graphviz: plain SVG text, verified structurally.

Overlay encoding never relies on colour alone: staged additions carry "+", deletions
"−", modified nodes "~", inferred edges the word "inferred", findings a severity letter.
"""

from __future__ import annotations

import html

HIER = ("subClassOf", "broader")
STATE = {"staged_add": ("#2e7d32", "+ "), "staged_del": ("#c62828", "− "),
         "modified": ("#b26a00", "~ "), "asserted": ("#5c6b80", "")}
SEV = {"blocker": ("#b71c1c", "B"), "major": ("#c62828", "M"), "minor": ("#8d6e00", "m"),
       "info": ("#546e7a", "i")}
GAP_X, GAP_Y, PAD, NODE_H = 26, 92, 28, 36


def _w(label: str) -> float:
    return max(96.0, min(230.0, len(label) * 6.9 + 26))


def layout(entities: list[dict], rels: list[dict]) -> dict[str, tuple[float, float, float]]:
    ids = {e["id"] for e in entities}
    label = {e["id"]: e["name"] for e in entities}
    parents = {i: [] for i in ids}
    children = {i: [] for i in ids}
    refs = {i: [] for i in ids}            # n is referenced by (restriction / range) ...
    for r in rels:
        a, b = r["from"], r["to"]
        if a not in ids or b not in ids or a == b:
            continue
        if r["kind"] in HIER:
            parents[a].append(b)
            children[b].append(a)
        elif not r.get("sip", {}).get("inferred"):
            refs[b].append(a)
    memo: dict[str, int] = {}

    def depth(n: str, seen: frozenset) -> int:
        """Superclasses above; a node with no superclass in view sits one row below a
        class that refers to it (the viewer's rule: generalisation up, references down)."""
        if n in memo:
            return memo[n]
        if n in seen:
            return 0
        if parents[n]:
            v = 1 + max(depth(p, seen | {n}) for p in parents[n])
        elif refs[n]:
            v = 1 + min(depth(p, seen | {n}) for p in refs[n])
        else:
            v = 0
        memo[n] = v
        return v

    layers: dict[int, list[str]] = {}
    for n in sorted(ids, key=lambda i: (label[i].lower(), i)):
        layers.setdefault(depth(n, frozenset()), []).append(n)
    order = {n: k for L in layers.values() for k, n in enumerate(L)}

    def sweep(ls, nbrs):
        for L in ls:
            row = layers[L]
            bc = {n: (sum(order[m] for m in nbrs[n]) / len(nbrs[n]) if nbrs[n] else order[n])
                  for n in row}
            row.sort(key=lambda n: (bc[n], label[n].lower(), n))
            for k, n in enumerate(row):
                order[n] = k

    keys = sorted(layers)
    for _ in range(4):
        sweep(keys[1:], parents)
        sweep(list(reversed(keys[:-1])), children)

    widths = {L: sum(_w(label[n]) for n in row) + GAP_X * (len(row) - 1)
              for L, row in layers.items()}
    full = max(widths.values(), default=0)
    pos = {}
    for L, row in layers.items():
        x = PAD + (full - widths[L]) / 2
        for n in row:
            w = _w(label[n])
            pos[n] = (x, PAD + 56 + L * GAP_Y, w)
            x += w + GAP_X
    return pos


def _clip(x1, y1, x2, y2, w, h):
    """Point where the segment centre(x1,y1) -> (x2,y2) leaves a w×h box at (x1,y1)."""
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return x1, y1
    tx = (w / 2) / abs(dx) if dx else float("inf")
    ty = (h / 2) / abs(dy) if dy else float("inf")
    t = min(tx, ty)
    return x1 + dx * t, y1 + dy * t


def render_svg(view: dict, title: str | None = None) -> str:
    ents, rels = view["entityTypes"], view["relationships"]
    pos = layout(ents, rels)
    width = max((x + w for x, _, w in pos.values()), default=300) + PAD
    height = max((y for _, y, _ in pos.values()), default=0) + NODE_H + PAD + 70
    width = max(width, 640)
    esc = html.escape
    title = title or view.get("name", "Ontology view")
    stats = view.get("sip", {}).get("stats", {})
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
           f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="Segoe UI, Arial, sans-serif" '
           f'role="img" aria-label="{esc(title)}">',
           f'<title>{esc(title)}</title>',
           '<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
           'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
           'fill="context-stroke"/></marker></defs>',
           f'<rect width="{width:.0f}" height="{height:.0f}" fill="#ffffff"/>',
           f'<text x="{PAD}" y="30" font-size="17" font-weight="600" fill="#1d2430">'
           f'{esc(title)}</text>',
           f'<text x="{PAD}" y="50" font-size="11" fill="#5c6b80">'
           f'{stats.get("nodes", len(ents))} nodes, {stats.get("edges", len(rels))} edges, '
           f'{stats.get("truncated", 0)} held back by the cap</text>']
    centre = {n: (x + w / 2, y + NODE_H / 2, w) for n, (x, y, w) in pos.items()}
    for r in sorted(rels, key=lambda r: r["id"]):
        if r["from"] not in centre or r["to"] not in centre or r["from"] == r["to"]:
            continue
        s = r.get("sip", {})
        (x1, y1, w1), (x2, y2, w2) = centre[r["from"]], centre[r["to"]]
        ax, ay = _clip(x1, y1, x2, y2, w1, NODE_H)
        bx, by = _clip(x2, y2, x1, y1, w2, NODE_H)
        colour, prefix = STATE.get(s.get("state", "asserted"), STATE["asserted"])
        dash = ""
        if r["kind"] == "restriction":
            dash = ' stroke-dasharray="6 3"'
        elif r["kind"] == "disjointWith":
            dash = ' stroke-dasharray="1 3"'
        if s.get("inferred"):
            colour, dash, prefix = "#1565c0", ' stroke-dasharray="3 3"', "inferred "
        if s.get("state") == "staged_del":
            dash = ' stroke-dasharray="4 4"'
        width_attr = "3" if r["kind"] == "equivalentClass" else "1.4"
        out.append(f'<line x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" '
                   f'stroke="{colour}" stroke-width="{width_attr}"{dash} marker-end="url(#arr)">'
                   f'<title>{esc(prefix + r["name"])}</title></line>')
        text = prefix + (r["name"] if r["kind"] not in HIER else "")
        if text.strip():
            mx, my = (ax + bx) / 2, (ay + by) / 2
            tw = len(text) * 5.6 + 8
            out.append(f'<rect x="{mx - tw / 2:.1f}" y="{my - 8:.1f}" width="{tw:.1f}" '
                       f'height="14" rx="6" fill="#ffffff" fill-opacity="0.9"/>')
            out.append(f'<text x="{mx:.1f}" y="{my + 3:.1f}" font-size="9.5" '
                       f'text-anchor="middle" fill="{colour}">{esc(text)}</text>')
    for e in sorted(ents, key=lambda e: e["id"]):
        x, y, w = pos[e["id"]]
        s = e.get("sip", {})
        colour, prefix = STATE.get(s.get("state", "asserted"), STATE["asserted"])
        stroke_w = "2.6" if s.get("seed") else "1.3"
        dash = ' stroke-dasharray="4 3"' if s.get("state") == "staged_del" else ""
        fill = "#ffebee" if s.get("unsatisfiable") else e.get("color", "#eeeeee")
        tip = e["name"] + (" (" + s.get("moduleLabel", "") + ")" if s.get("moduleLabel") else "")
        out.append(f'<g><title>{esc(tip)}</title><rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" '
                   f'height="{NODE_H}" rx="7" fill="{fill}" stroke="{colour}" '
                   f'stroke-width="{stroke_w}"{dash}/>')
        out.append(f'<text x="{x + w / 2:.1f}" y="{y + 15:.1f}" font-size="11.5" '
                   f'font-weight="{600 if s.get("seed") else 500}" text-anchor="middle" '
                   f'fill="#1d2430">{esc(prefix + e["name"])}</text>')
        sub = []
        if s.get("complexCount"):
            sub.append(f'{s["complexCount"]} axiom badge')
        if s.get("hidden"):
            sub.append(f'+{s["hidden"]} more')
        if s.get("unsatisfiable"):
            sub.append("unsatisfiable")
        if sub:
            out.append(f'<text x="{x + w / 2:.1f}" y="{y + 29:.1f}" font-size="9" '
                       f'text-anchor="middle" fill="#5c6b80">{esc(" · ".join(sub))}</text>')
        if s.get("worstSeverity") in SEV:
            c, letter = SEV[s["worstSeverity"]]
            out.append(f'<circle cx="{x + w - 4:.1f}" cy="{y + 4:.1f}" r="7" fill="{c}"/>'
                       f'<text x="{x + w - 4:.1f}" y="{y + 7.5:.1f}" font-size="9" '
                       f'text-anchor="middle" fill="#ffffff">{letter}</text>')
        out.append("</g>")
    ly = height - 26
    legend = [("#5c6b80", "asserted"), ("#2e7d32", "+ staged add"),
              ("#c62828", "− staged delete"), ("#b26a00", "~ modified"),
              ("#1565c0", "inferred (dashed)")]
    x = PAD
    for c, t in legend:
        out.append(f'<rect x="{x}" y="{ly - 9}" width="14" height="10" fill="none" '
                   f'stroke="{c}" stroke-width="2"/><text x="{x + 19}" y="{ly}" font-size="10" '
                   f'fill="#1d2430">{esc(t)}</text>')
        x += 30 + len(t) * 6
    out.append(f'<text x="{x + 10}" y="{ly}" font-size="10" fill="#5c6b80">'
               'dashed arrow = restriction (tag in label)</text>')
    out.append("</svg>")
    return "\n".join(out)
