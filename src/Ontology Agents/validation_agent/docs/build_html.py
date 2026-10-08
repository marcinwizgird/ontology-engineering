"""Render ONTOLOGY_REVIEW_AND_VALIDATION.md as a standalone HTML page.

    python build_html.py

The output is a single self-contained file (styles inline, diagram embedded as a data
URI), so it can be opened locally, attached to an e-mail or dropped on an intranet page.
Re-run after editing the Markdown; the Markdown file is the source.
"""

from __future__ import annotations

import base64
import html
import re
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "ONTOLOGY_REVIEW_AND_VALIDATION.md"
TARGET = HERE / "ONTOLOGY_REVIEW_AND_VALIDATION.html"

CSS = """
:root {
  --bg: #fbfbf9; --surface: #ffffff; --text: #1d1d1b; --muted: #5f5f5a;
  --rule: #e4e3de; --accent: #2f6fbd; --accent-soft: #e8f0fa;
  --strong: #1f7a4d; --strong-bg: #e6f4ec; --partial: #8a6a10; --partial-bg: #faf2dc;
  --weak: #a3402f; --weak-bg: #fbe9e5; --none: #9a9a93;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #171716; --surface: #1f1f1d; --text: #ecebe6; --muted: #a8a7a0;
    --rule: #34332f; --accent: #7fb0ee; --accent-soft: #1e2c3d;
    --strong: #7fd3a6; --strong-bg: #173326; --partial: #e2c46e; --partial-bg: #3a3118;
    --weak: #f0a094; --weak-bg: #3d211c; --none: #6f6e68;
  }
}
:root[data-theme="dark"] {
  --bg: #171716; --surface: #1f1f1d; --text: #ecebe6; --muted: #a8a7a0;
  --rule: #34332f; --accent: #7fb0ee; --accent-soft: #1e2c3d;
  --strong: #7fd3a6; --strong-bg: #173326; --partial: #e2c46e; --partial-bg: #3a3118;
  --weak: #f0a094; --weak-bg: #3d211c; --none: #6f6e68;
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, Helvetica, Arial, sans-serif;
}
main { max-width: 860px; margin: 0 auto; padding: 48px 16px 96px; }
h1 { font-size: 2rem; line-height: 1.2; margin: 0 0 8px; letter-spacing: -0.01em; }
h2 { font-size: 1.35rem; margin: 48px 0 12px; padding-top: 16px; border-top: 1px solid var(--rule); }
p, li { max-width: 72ch; }
.byline { color: var(--muted); margin: 0 0 24px; }
blockquote {
  margin: 0 0 32px; padding: 10px 16px; border-left: 3px solid var(--accent);
  background: var(--accent-soft); color: var(--muted); font-size: 0.9rem; border-radius: 0 6px 6px 0;
}
blockquote p { margin: 0; }
a { color: var(--accent); }
strong { font-weight: 600; }
.table-wrap { overflow-x: auto; margin: 16px 0 24px; border: 1px solid var(--rule); border-radius: 8px; background: var(--surface); }
table { border-collapse: collapse; width: 100%; font-size: 0.92rem; }
th, td { text-align: left; vertical-align: top; padding: 10px 12px; border-bottom: 1px solid var(--rule); }
th { font-weight: 600; background: var(--bg); position: sticky; top: 0; }
tr:last-child td { border-bottom: none; }
td.lvl { white-space: nowrap; font-weight: 600; font-size: 0.85rem; }
td.lvl-strong { color: var(--strong); background: var(--strong-bg); }
td.lvl-partial { color: var(--partial); background: var(--partial-bg); }
td.lvl-weak { color: var(--weak); background: var(--weak-bg); }
td.lvl-none { color: var(--none); text-align: center; }
figure { margin: 24px 0; }
figure img { width: 100%; height: auto; display: block; border-radius: 8px; background: #fff; padding: 8px; border: 1px solid var(--rule); }
figcaption { color: var(--muted); font-size: 0.85rem; margin-top: 8px; }
ul.tasks { list-style: none; padding-left: 0; }
ul.tasks li { display: flex; gap: 10px; align-items: flex-start; margin: 8px 0; }
ul.tasks input { margin-top: 6px; accent-color: var(--accent); flex: none; }
footer { margin-top: 64px; color: var(--muted); font-size: 0.85rem; }
@media print {
  body { background: #fff; color: #000; }
  main { padding: 0; max-width: none; }
  h2 { break-after: avoid; }
  .table-wrap, figure { break-inside: avoid; }
}
"""

LEVELS = {"Strong": "strong", "Partial": "partial", "Weak": "weak", "—": "none"}


def _embed_images(body: str) -> str:
    """Inline local images as data URIs and wrap them in a captioned figure."""

    def repl(m: re.Match) -> str:
        src, alt = m.group("src"), m.group("alt")
        path = HERE / src
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return (f'<figure><img src="data:image/png;base64,{data}" alt="{alt}">'
                f"<figcaption>{alt}</figcaption></figure>")

    body = re.sub(r'<p><img alt="(?P<alt>[^"]*)" src="(?P<src>[^"]+)" ?/?></p>', repl, body)
    return body


def _tasks(body: str) -> str:
    """GitHub-style task lists -> checkboxes (python-markdown has no built-in for them)."""
    body = re.sub(r"<li>\[ \] ", '<li><input type="checkbox" aria-label="decision"> <span>', body)
    body = re.sub(r'(<li><input[^>]*> <span>.*?)</li>', r"\1</span></li>", body, flags=re.S)
    return body.replace("<ul>\n<li><input", '<ul class="tasks">\n<li><input')


def _levels(body: str) -> str:
    """Colour the coverage matrix cells (Strong / Partial / Weak / none)."""

    def repl(m: re.Match) -> str:
        text = m.group(1)
        word = text.split(" ")[0]
        if word in LEVELS:
            return f'<td class="lvl lvl-{LEVELS[word]}">{text}</td>'
        return m.group(0)

    return re.sub(r"<td>([^<]*)</td>", repl, body)


def build() -> Path:
    md_text = SOURCE.read_text(encoding="utf-8")
    title_match = re.match(r"# (.+)\n", md_text)
    title = title_match.group(1).strip() if title_match else "Ontology Review & Validation"
    md_text = md_text[title_match.end():] if title_match else md_text

    # The first paragraph after the title is the byline.
    byline, _, rest = md_text.strip().partition("\n\n")

    body = markdown.markdown(rest, extensions=["tables", "sane_lists"], output_format="html")
    body = _embed_images(body)
    body = _tasks(body)
    body = _levels(body)
    body = body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ontology Review and Validation</title>
<meta name="description" content="Approaches to ontology review and validation: reasoning, SHACL, custom checks and more, with their benefits, shortcomings and how they complement each other.">
<style>{CSS}</style>
</head>
<body>
<main>
<h1>{html.escape(title)}</h1>
<p class="byline">{html.escape(byline)}</p>
{body}
<footer>Generated from ONTOLOGY_REVIEW_AND_VALIDATION.md by build_html.py.</footer>
</main>
</body>
</html>
"""
    TARGET.write_text(page, encoding="utf-8")
    return TARGET


if __name__ == "__main__":
    out = build()
    print(f"wrote {out.name} ({out.stat().st_size // 1024} KB)")
