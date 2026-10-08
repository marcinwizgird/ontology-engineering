"""A small reader for the SysML v2 textual subset used in ``models/*.sysml``.

Diagrams are generated *from the model files* rather than drawn beside them. The reason
is the usual one: a hand-drawn diagram is correct on the day it is drawn and slowly stops
being correct afterwards, and nothing tells you when. Parsing means the pictures either
regenerate or fail loudly.

This is not a general SysML parser. It reads the declaration forms these three models
actually use and ignores the rest:

    package N { ... }                      part def N :> Super { ... }
    abstract part def N;                   part n : T { ... }
    variation part n : T { variant part ... }
    port def N { ... }                     port n : T;
    interface def N { end a : T; }         attribute def N { ... }
    attribute n : T[0..*] default X;       enum def N { a; b; }
    requirement def <'R1'> N { ... }       verification def <'V1'> N { ... }
    constraint def N { ... }               assert constraint n : T;
    action def N { in/out p : T; action sub { ... } }
    flow a to b;                           first a then b then c;
    state def N { state X; transition A then B ...; }
    allocate X to "Y";                     connect a.b to c.d;
    satisfy requirement <'R1'> N by a, b;  verify requirement <'R1'> by <'V1'>;
    doc /* ... */

Comments are removed before any brace counting, because several ``doc`` bodies contain
braces of their own and would otherwise close their owner early.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Declaration keywords that open a named element. Order matters: the longest match wins,
# so "part def" is tried before "part".
_DEF_KEYWORDS = (
    "requirement def", "verification def", "constraint def", "attribute def",
    "interface def", "action def", "state def", "part def", "port def", "enum def",
    "variation part", "variant part", "package", "part", "port", "state", "action",
)

_ID_RE = re.compile(r"<'([^']+)'>")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass
class Element:
    """One declaration, with whatever the parser could recover about it."""

    kind: str
    name: str
    ident: str | None = None            # the <'R1'> short id, when present
    typed_as: str | None = None         # after ':'
    supers: list[str] = field(default_factory=list)   # after ':>'
    abstract: bool = False
    doc: str | None = None
    attributes: list[dict] = field(default_factory=list)
    children: list["Element"] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"«{self.ident}» {self.name}" if self.ident else self.name

    def of_kind(self, *kinds: str) -> list["Element"]:
        return [c for c in self.children if c.kind in kinds]

    def descendants(self):
        for child in self.children:
            yield child
            yield from child.descendants()


@dataclass
class Relation:
    """A cross-element link: allocate / satisfy / verify / connect / flow / transition."""

    kind: str
    source: str
    target: str
    label: str | None = None
    guard: str | None = None


@dataclass
class Model:
    path: Path
    package: str
    root: Element
    relations: list[Relation] = field(default_factory=list)
    succession: list[list[str]] = field(default_factory=list)   # first a then b then c

    def find(self, name: str) -> Element | None:
        for element in self.root.descendants():
            if element.name == name or element.ident == name:
                return element
        return None

    def by_kind(self, *kinds: str) -> list[Element]:
        return [e for e in self.root.descendants() if e.kind in kinds]


# --------------------------------------------------------------------------- #
# Lexing: strip comments, remembering doc bodies
# --------------------------------------------------------------------------- #

def _strip_comments(text: str) -> tuple[str, dict[int, str]]:
    """Remove block and line comments; return the text plus recovered doc bodies.

    Block comments are replaced by a marker so a `doc` can still be tied to the
    declaration that follows it. String literals are respected so a `//` or `/*` inside
    an allocation target is not mistaken for a comment.
    """
    out: list[str] = []
    docs: dict[int, str] = {}
    i, n, in_string = 0, len(text), False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end == -1 else end
            body = text[i + 2:end]
            key = len(docs)
            docs[key] = _clean_doc(body)
            out.append(f"\x00DOC{key}\x00")
            i = end + 2
            continue
        if text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end == -1 else end
            continue
        out.append(ch)
        i += 1
    return "".join(out), docs


def _clean_doc(body: str) -> str:
    """Turn a block-comment body into flowing prose."""
    lines = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("*"):
            line = line[1:].strip()
        lines.append(line)
    # Blank lines separate paragraphs; everything else joins into one line.
    paragraphs, current = [], []
    for line in lines:
        if line:
            current.append(line)
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs).strip()


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

def parse_file(path: Path) -> Model:
    text, docs = _strip_comments(Path(path).read_text(encoding="utf-8"))
    package_name, body = _first_package(text)
    root = Element(kind="package", name=package_name)
    relations: list[Relation] = []
    succession: list[list[str]] = []
    _parse_body(body, root, docs, relations, succession)
    return Model(path=Path(path), package=package_name, root=root,
                 relations=relations, succession=succession)


def _first_package(text: str) -> tuple[str, str]:
    match = re.search(r"\bpackage\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{", text)
    if not match:
        return "(anonymous)", text
    start = match.end() - 1
    return match.group(1), _balanced(text, start)


def _balanced(text: str, open_index: int) -> str:
    """The contents of the brace block starting at `open_index`."""
    depth, i, n = 0, open_index, len(text)
    while i < n:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_index + 1:i]
        i += 1
    return text[open_index + 1:]


def _split_statements(body: str) -> list[tuple[str, str | None]]:
    """Split a block into (header, nested-body|None) pairs."""
    statements: list[tuple[str, str | None]] = []
    i, n, start, depth = 0, len(body), 0, 0
    while i < n:
        ch = body[i]
        if ch == "{" and depth == 0:
            header = body[start:i]
            inner = _balanced(body, i)
            statements.append((header.strip(), inner))
            i += len(inner) + 2
            start = i
            continue
        if ch == ";" and depth == 0:
            statements.append((body[start:i].strip(), None))
            i += 1
            start = i
            continue
        i += 1
    tail = body[start:].strip()
    if tail:
        statements.append((tail, None))
    return [(h, b) for h, b in statements if h or b]


def _parse_body(body: str, parent: Element, docs: dict[int, str],
                relations: list[Relation], succession: list[list[str]]) -> None:
    pending_doc: str | None = None

    for header, inner in _split_statements(body):
        header, doc_here = _take_doc(header, docs)
        if doc_here is not None:
            pending_doc = doc_here

        stripped = header.strip()
        if not stripped:
            continue

        # A bare `doc` statement carries the docs already extracted above.
        if stripped == "doc" or stripped.startswith("doc "):
            continue

        if _relation(stripped, inner, parent, relations, succession):
            pending_doc = None
            continue

        element = _declaration(stripped, docs)
        if element is None:
            pending_doc = None
            continue

        if element.doc is None and pending_doc:
            element.doc = pending_doc
        pending_doc = None

        if inner is not None:
            _parse_body(inner, element, docs, relations, succession)
            # `doc` written as the first thing inside a block belongs to the block.
            if element.doc is None:
                _, first_doc = _take_doc(inner, docs)
                element.doc = first_doc
        parent.children.append(element)


def _take_doc(fragment: str, docs: dict[int, str]) -> tuple[str, str | None]:
    """Pull the first doc marker out of a fragment."""
    match = re.search(r"\x00DOC(\d+)\x00", fragment)
    if not match:
        return fragment, None
    return (fragment[:match.start()] + fragment[match.end():],
            docs.get(int(match.group(1))))


def _relation(stripped: str, inner: str | None, parent: Element,
              relations: list[Relation], succession: list[list[str]]) -> bool:
    """Recognise the non-declaration statements. Returns True if consumed."""

    if stripped.startswith("import "):
        return True

    if stripped.startswith("allocate "):
        match = re.match(r'allocate\s+(.+?)\s+to\s+"?(.+?)"?$', stripped)
        if match:
            relations.append(Relation("allocate", match.group(1).strip(),
                                      match.group(2).strip()))
        return True

    if stripped.startswith("satisfy requirement"):
        ident = _ID_RE.search(stripped)
        rest = _ID_RE.sub("", stripped).replace("satisfy requirement", "", 1)
        name, _, by = rest.partition(" by ")
        for target in _names(by):
            relations.append(Relation("satisfy", target,
                                      ident.group(1) if ident else name.strip(),
                                      label=name.strip()))
        return True

    if stripped.startswith("verify requirement"):
        ids = _ID_RE.findall(stripped)
        if ids:
            requirement, cases = ids[0], ids[1:]
            for case in cases:
                relations.append(Relation("verify", case, requirement))
        return True

    if stripped.startswith("connect "):
        match = re.match(r"connect\s+(\S+)\s+to\s+(\S+)", stripped)
        if match:
            relations.append(Relation("connect", _head(match.group(1)),
                                      _head(match.group(2))))
        return True

    if stripped.startswith("flow "):
        match = re.match(r"flow\s+(\S+)\s+to\s+(\S+)", stripped)
        if match:
            relations.append(Relation("flow", _head(match.group(1)),
                                      _head(match.group(2))))
        return True

    if stripped.startswith("first ") or " then " in stripped and stripped.startswith("first"):
        chain = [p.strip() for p in re.split(r"\bthen\b|\bfirst\b", stripped) if p.strip()]
        if len(chain) > 1:
            succession.append(chain)
        return True

    if stripped.startswith("transition "):
        match = re.match(r"transition\s+(\w+)\s+then\s+(\w+)(.*)$", stripped)
        if match:
            tail = match.group(3).strip()
            guard = None
            if tail.startswith("if "):
                guard = tail[3:].strip()
            elif tail.startswith("accept "):
                guard = tail[7:].strip()
            relations.append(Relation("transition", match.group(1), match.group(2),
                                      guard=guard))
        return True

    if stripped.startswith("entry") or stripped.startswith("require constraint") \
            or stripped.startswith("assert constraint {"):
        return True

    if stripped.startswith("assert constraint"):
        match = re.match(r"assert constraint\s+(\w+)\s*:\s*([\w:]+)", stripped)
        if match:
            relations.append(Relation("assert", parent.name,
                                      match.group(2).split("::")[-1],
                                      label=match.group(1)))
        return True

    if stripped.startswith("end ") or stripped.startswith("subject ") \
            or re.match(r"^(in|out)\s+\w+\s*:", stripped):
        # Ports/parameters of a block: recorded as attributes rather than elements.
        parent.attributes.append(_attribute(stripped))
        return True

    return False


def _declaration(stripped: str, docs: dict[int, str]) -> Element | None:
    abstract = stripped.startswith("abstract ")
    if abstract:
        stripped = stripped[len("abstract "):].strip()

    if stripped.startswith("attribute "):
        return None          # handled by the caller's attribute sweep

    for keyword in _DEF_KEYWORDS:
        if stripped == keyword or stripped.startswith(keyword + " "):
            rest = stripped[len(keyword):].strip()
            ident_match = _ID_RE.search(rest)
            ident = ident_match.group(1) if ident_match else None
            rest = _ID_RE.sub("", rest).strip()

            supers: list[str] = []
            if ":>" in rest:
                rest, _, super_part = rest.partition(":>")
                supers = _names(super_part)

            typed_as = None
            if ":" in rest:
                rest, _, type_part = rest.partition(":")
                typed_as = (_names(type_part) or [None])[0]

            name_match = _NAME_RE.search(rest)
            name = name_match.group(0) if name_match else (ident or typed_as or keyword)
            return Element(kind=keyword, name=name, ident=ident, typed_as=typed_as,
                           supers=supers, abstract=abstract)
    return None


def _attribute(stripped: str) -> dict:
    default = None
    if " default " in stripped:
        stripped, _, default = stripped.partition(" default ")
        default = default.strip()
    name_part, _, type_part = stripped.partition(":")
    multiplicity = None
    mult_match = re.search(r"\[([^\]]+)\]", type_part)
    if mult_match:
        multiplicity = mult_match.group(1)
        type_part = type_part[:mult_match.start()]
    tokens = _names(name_part)
    return {
        "direction": tokens[0] if tokens and tokens[0] in ("in", "out", "end", "subject") else None,
        "name": tokens[-1] if tokens else "?",
        "type": (_names(type_part) or [None])[0],
        "multiplicity": multiplicity,
        "default": default,
    }


def _collect_attributes(element: Element, body: str) -> None:
    for line in body.splitlines():
        line = line.strip().rstrip(";")
        if line.startswith("attribute ") and ":" in line:
            element.attributes.append(_attribute(line[len("attribute "):]))


def _names(text: str) -> list[str]:
    return _NAME_RE.findall(text or "")


def _head(path: str) -> str:
    return path.split(".")[0].strip().rstrip(";")


def parse_all(models_dir: Path) -> list[Model]:
    """Parse every .sysml file in a directory, in a stable order."""
    return [parse_file(p) for p in sorted(Path(models_dir).glob("*.sysml"))]


def attach_attributes(model: Model) -> None:
    """Second pass: fill in `attribute` lines, which the structural pass skips."""
    text, _ = _strip_comments(model.path.read_text(encoding="utf-8"))
    for element in model.root.descendants():
        pattern = re.compile(
            rf"\b{re.escape(element.kind)}\s+(?:<'[^']+'>\s*)?"
            rf"(?:abstract\s+)?{re.escape(element.name)}\b[^{{;]*\{{")
        match = pattern.search(text)
        if not match:
            continue
        _collect_attributes(element, _balanced(text, match.end() - 1))
