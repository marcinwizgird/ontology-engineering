"""Check the generated SVGs for the defects a layout engine actually produces.

Run:  python architecture/graphrag_agent/verify_diagrams.py

A diagram build that writes bytes is not a diagram build that produced a readable
picture. These are the failures a hand-rolled layered layout makes, each of which turns
a diagram into something a reader quietly stops trusting:

    xml        malformed output
    bounds     a box outside the canvas, so it is cropped in a viewer
    overlap    two boxes on top of each other
    clipped    compartment text running past its box
    collision  an edge label sitting on top of an unrelated box
    dangling   an edge drawn to a node that is not there
    density    a canvas so crowded the layout has effectively given up

It does not verify that a diagram is *well composed* -- that still needs eyes.
"""

from __future__ import annotations

import html
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

DIAGRAMS = Path(__file__).resolve().parent / "artifacts" / "diagrams"

CHAR_W_BODY = 6.05          # must match sysml_diagrams.CHAR_W_BODY
NODE_RECT = re.compile(
    r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)" rx="8"')
BODY_TEXT = re.compile(
    r'<text x="([\d.]+)" y="([\d.]+)" font-size="10\.5"[^>]*>([^<]*)</text>')
LABEL_RECT = re.compile(
    r'<rect x="(-?[\d.]+)" y="(-?[\d.]+)" width="([\d.]+)" height="15" rx="7"')
PATH_ENDS = re.compile(r'<path d="M ([\d.]+) ([\d.]+) C .* ([\d.]+) ([\d.]+)"')


def _overlap(a, b, margin: float = 0.0) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return (ax < bx + bw + margin and bx < ax + aw + margin
            and ay < by + bh + margin and by < ay + ah + margin)


def check(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    problems: list[str] = []

    try:
        ET.fromstring(text)
    except ET.ParseError as exc:
        return [f"xml: not well-formed ({exc})"]

    width = float(re.search(r'width="(\d+)"', text).group(1))
    height = float(re.search(r'height="(\d+)"', text).group(1))
    boxes = [tuple(float(v) for v in m.groups()) for m in NODE_RECT.finditer(text)]

    for i, box in enumerate(boxes):
        x, y, w, h = box
        if x < 0 or y < 0 or x + w > width + 1 or y + h > height + 1:
            problems.append(f"bounds: box {i} at ({x:.0f},{y:.0f},{w:.0f}x{h:.0f}) "
                            f"leaves the {width:.0f}x{height:.0f} canvas")

    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if _overlap(boxes[i], boxes[j]):
                problems.append(f"overlap: boxes {i} and {j} intersect")

    for m in BODY_TEXT.finditer(text):
        tx, ty, raw = float(m.group(1)), float(m.group(2)), m.group(3)
        rendered = html.unescape(raw)          # measure what a viewer draws, not the markup
        owner = next((b for b in boxes
                      if b[0] <= tx <= b[0] + b[2] and b[1] <= ty <= b[1] + b[3] + 2), None)
        if owner and tx + len(rendered) * CHAR_W_BODY > owner[0] + owner[2] - 3:
            overflow = tx + len(rendered) * CHAR_W_BODY - (owner[0] + owner[2])
            problems.append(f"clipped: {rendered[:34]!r} overflows its box by "
                            f"{overflow:.0f}px")

    for m in LABEL_RECT.finditer(text):
        lx, ly, lw = float(m.group(1)), float(m.group(2)), float(m.group(3))
        label_box = (lx, ly, lw, 15.0)
        for i, box in enumerate(boxes):
            if _overlap(label_box, box):
                problems.append(f"collision: an edge label overlaps box {i}")
                break

    centres = {(round(b[0] + b[2] / 2), round(b[1])) for b in boxes}
    centres |= {(round(b[0] + b[2] / 2), round(b[1] + b[3])) for b in boxes}
    centres |= {(round(b[0]), round(b[1] + b[3] / 2)) for b in boxes}
    centres |= {(round(b[0] + b[2]), round(b[1] + b[3] / 2)) for b in boxes}
    for m in PATH_ENDS.finditer(text):
        start = (round(float(m.group(1))), round(float(m.group(2))))
        end = (round(float(m.group(3))), round(float(m.group(4))))
        for point, which in ((start, "start"), (end, "end")):
            if not any(abs(point[0] - cx) <= 2 and abs(point[1] - cy) <= 2
                       for cx, cy in centres):
                problems.append(f"dangling: an edge {which} at {point} touches no box")
                break

    area = sum(b[2] * b[3] for b in boxes)
    if area > 0.55 * width * height:
        problems.append(f"density: boxes cover {area / (width * height):.0%} of the "
                        f"canvas; the layout is too crowded to read")

    return problems


def main() -> int:
    files = sorted(DIAGRAMS.glob("*.svg"))
    if not files:
        print(f"no SVGs in {DIAGRAMS}; run build_diagrams.py first", file=sys.stderr)
        return 1

    total = 0
    for path in files:
        problems = check(path)
        total += len(problems)
        status = "ok" if not problems else f"{len(problems)} problem(s)"
        print(f"{path.name:52} {status}")
        for problem in problems[:6]:
            print(f"      {problem}")
        if len(problems) > 6:
            print(f"      … {len(problems) - 6} more")

    print(f"\n{len(files)} diagram(s) checked, {total} problem(s)")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
