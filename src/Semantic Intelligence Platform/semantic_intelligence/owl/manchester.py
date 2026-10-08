"""Manchester OWL Syntax for class expressions — parse, render, complete.

Protégé's expression editors (``ExpressionEditor<OWLClassExpression>`` with an
``OWLClassExpressionChecker``) parse with the OWL API ``ManchesterOWLSyntaxParser``
and drive auto-completion from its ``ParserException``: the exception carries
the offending token, its offset, the *expected keywords* and flags such as
``isClassNameExpected()`` / ``isObjectPropertyNameExpected()``. The
``AutoCompleter`` then offers entities of the expected kinds whose rendering starts
with the word under the caret, plus the expected keywords.

This module reproduces that contract in pure Python:

* :func:`parse` — recursive descent over the class-expression grammar of the
  Manchester OWL Syntax W3C Note (§2.4 *Descriptions*) incl. data ranges with
  facets, ``inverse``, ``Self``, qualified cardinalities and ``that``;
* :class:`ManchesterError` — offset, token, ``expected`` (keywords and entity
  kinds) at the *furthest* failure point;
* :func:`render` — precedence-aware rendering with Manchester quoting;
* :func:`complete` — Protégé-style completion proposals at a caret position.

Names are resolved through :class:`~.rendering.ShortFormProvider`, so an
expression may be typed with labels (``'has part' some Wheel``), prefixed names
or full IRIs (``<http://…>``) exactly as in Protégé.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDFS, XSD

from .model import (CE, And, Card, DataComplementOf, DataNary, DataOneOf, DataRange,
                    DatatypeRestriction, HasSelf, HasValue, Inverse, Not, OneOf, Only,
                    Or, Some)
from .rendering import BUILTIN_DATATYPES, ShortFormProvider, quote

__all__ = ["parse", "render", "complete", "ManchesterError", "Completion"]

_TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<iri><[^>\s]*>)
  | (?P<qname>'(?:[^'\\]|\\.)*')
  | (?P<string>"(?:[^"\\]|\\.)*"(?:@[A-Za-z\-]+|\^\^[^\s,)\]}]+)?)
  | (?P<number>[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?[fF]?)
  | (?P<facet><=|>=|<|>)
  | (?P<punct>[(){}\[\],])
  | (?P<word>[^\s(){}\[\],'"<>]+)
""", re.X)

KEYWORDS_RESTRICTION = ("some", "only", "value", "min", "max", "exactly", "Self")
FACETS = {"length": XSD.length, "minLength": XSD.minLength, "maxLength": XSD.maxLength,
          "pattern": XSD.pattern, "langRange": URIRef(str(RDFS) + "langRange"),
          "<=": XSD.maxInclusive, ">=": XSD.minInclusive, "<": XSD.maxExclusive,
          ">": XSD.minExclusive}


@dataclass(frozen=True)
class Tok:
    kind: str
    text: str
    start: int


def tokenize(text: str) -> list[Tok]:
    out, pos = [], 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise ManchesterError(f"unexpected character {text[pos]!r}", pos, text[pos],
                                  set())
        if m.lastgroup != "ws":
            out.append(Tok(m.lastgroup, m.group(), pos))
        pos = m.end()
    out.append(Tok("eof", "", len(text)))
    return out


class ManchesterError(ValueError):
    def __init__(self, message: str, offset: int, token: str, expected: set[str]):
        self.offset, self.token, self.expected = offset, token, set(expected)
        exp = ", ".join(sorted(expected)) if expected else "?"
        super().__init__(f"{message} at offset {offset} (token {token!r}); expected: {exp}")

    @property
    def class_name_expected(self) -> bool:
        return "<class>" in self.expected

    @property
    def object_property_name_expected(self) -> bool:
        return "<objectProperty>" in self.expected

    @property
    def data_property_name_expected(self) -> bool:
        return "<dataProperty>" in self.expected

    @property
    def individual_name_expected(self) -> bool:
        return "<individual>" in self.expected

    @property
    def datatype_name_expected(self) -> bool:
        return "<datatype>" in self.expected


@dataclass
class _Parser:
    toks: list[Tok]
    sfp: ShortFormProvider
    i: int = 0
    far: int = -1
    far_expected: set[str] = field(default_factory=set)

    # -- token plumbing ----------------------------------------------------- #
    @property
    def tok(self) -> Tok:
        return self.toks[self.i]

    def expect(self, *items: str) -> None:
        """Record that *items* would have been acceptable at the current token."""
        if self.i > self.far:
            self.far, self.far_expected = self.i, set()
        if self.i == self.far:
            self.far_expected.update(items)

    def fail(self, msg: str):
        t = self.toks[max(self.far, self.i)]
        raise ManchesterError(msg, t.start, t.text, self.far_expected)

    def at(self, *words: str) -> bool:
        self.expect(*words)
        return self.tok.text in words

    def eat(self, word: str) -> None:
        if not self.at(word):
            self.fail(f"expected {word!r}")
        self.i += 1

    def _name_token(self) -> bool:
        return self.tok.kind in ("word", "qname", "iri") and self.tok.text not in (
            "and", "or", "not", "that", "inverse") + KEYWORDS_RESTRICTION

    def entity(self, *kinds: str) -> URIRef | None:
        """Resolve the current token as an entity of one of *kinds* (no consume on miss)."""
        self.expect(*(f"<{k}>" for k in kinds))
        if not self._name_token():
            return None
        hits = self.sfp.resolve(self.tok.text, kinds)
        if not hits and self.tok.kind == "iri":
            hits = [URIRef(self.tok.text[1:-1])]
        if not hits and "class" in kinds and self.tok.text in ("owl:Thing", "Thing"):
            hits = [OWL.Thing]
        if len(hits) > 1:
            raise ManchesterError(f"ambiguous name {self.tok.text!r}: "
                                  f"{', '.join(map(str, hits))}", self.tok.start,
                                  self.tok.text, {f"<{k}>" for k in kinds})
        if hits:
            self.i += 1
            return hits[0]
        return None

    # -- grammar ------------------------------------------------------------ #
    def description(self) -> CE:
        ops = [self.conjunction()]
        while self.at("or"):
            self.i += 1
            ops.append(self.conjunction())
        return ops[0] if len(ops) == 1 else Or(tuple(ops))

    def conjunction(self) -> CE:
        ops = [self.primary()]
        while self.at("and", "that"):
            self.i += 1
            ops.append(self.primary())
        return ops[0] if len(ops) == 1 else And(tuple(ops))

    def primary(self) -> CE:
        if self.at("not"):
            self.i += 1
            return Not(self.primary())
        return self.restriction_or_atomic()

    def restriction_or_atomic(self) -> CE:
        start = self.i
        prop, is_data = self.property_expression()
        if prop is not None:
            if self.tok.text in KEYWORDS_RESTRICTION or not isinstance(prop, URIRef):
                return self.restriction(prop, is_data)
            # A punned name (class *and* property): no restriction keyword follows,
            # so read it as a class. The keywords stay recorded for completion.
            self.expect(*KEYWORDS_RESTRICTION)
            self.i = start
            if not self.sfp.resolve(self.toks[start].text, ["class"]):
                self.i = start + 1
                self.fail("expected a restriction keyword")
        self.i = start
        return self.atomic()

    def property_expression(self) -> tuple[object | None, bool]:
        if self.at("inverse"):
            self.i += 1
            paren = self.tok.text == "("
            if paren:
                self.i += 1
            p = self.entity("objectProperty")
            if p is None:
                self.fail("expected an object property after 'inverse'")
            if paren:
                self.eat(")")
            return Inverse(p), False
        p = self.entity("objectProperty")
        if p is not None:
            return p, False
        p = self.entity("dataProperty")
        if p is not None:
            return p, True
        return None, False

    def restriction(self, prop, data: bool) -> CE:
        if self.at("some", "only"):
            kw = self.tok.text
            self.i += 1
            filler = self.data_primary() if data else self.primary()
            return (Some if kw == "some" else Only)(prop, filler, data)
        if self.at("value"):
            self.i += 1
            if data:
                return HasValue(prop, self.literal(), True)
            ind = self.entity("individual")
            if ind is None:
                self.fail("expected an individual after 'value'")
            return HasValue(prop, ind, False)
        if not data and self.at("Self"):
            self.i += 1
            return HasSelf(prop)
        if self.at("min", "max", "exactly"):
            kind = self.tok.text
            self.i += 1
            self.expect("<nonNegativeInteger>")
            if self.tok.kind != "number" or not self.tok.text.isdigit():
                self.fail("expected a non-negative integer")
            n = int(self.tok.text)
            self.i += 1
            filler = None
            if self._starts_filler(data):
                filler = self.data_primary() if data else self.primary()
            return Card(kind, n, prop, filler, data)
        self.fail("expected a restriction keyword")

    def _starts_filler(self, data: bool) -> bool:
        t = self.tok
        if t.kind == "eof" or t.text in (")", "}", "]", ",", "and", "or", "that"):
            # record what *could* have followed so completion offers it
            self.expect("<datatype>" if data else "<class>", "and", "or")
            return False
        return True

    def atomic(self) -> CE:
        if self.at("("):
            self.i += 1
            ce = self.description()
            self.eat(")")
            return ce
        if self.at("{"):
            self.i += 1
            inds = []
            while True:
                ind = self.entity("individual")
                if ind is None:
                    self.fail("expected an individual")
                inds.append(ind)
                if self.at(","):
                    self.i += 1
                    continue
                break
            self.eat("}")
            return OneOf(tuple(inds))
        c = self.entity("class")
        if c is None:
            self.fail("expected a class expression")
        return c

    # -- data ranges -------------------------------------------------------- #
    def data_range(self) -> DataRange:
        ops = [self.data_conjunction()]
        while self.at("or"):
            self.i += 1
            ops.append(self.data_conjunction())
        return ops[0] if len(ops) == 1 else DataNary("or", tuple(ops))

    def data_conjunction(self) -> DataRange:
        ops = [self.data_primary()]
        while self.at("and"):
            self.i += 1
            ops.append(self.data_primary())
        return ops[0] if len(ops) == 1 else DataNary("and", tuple(ops))

    def data_primary(self) -> DataRange:
        if self.at("not"):
            self.i += 1
            return DataComplementOf(self.data_primary())
        if self.at("("):
            self.i += 1
            dr = self.data_range()
            self.eat(")")
            return dr
        if self.at("{"):
            self.i += 1
            vals = [self.literal()]
            while self.at(","):
                self.i += 1
                vals.append(self.literal())
            self.eat("}")
            return DataOneOf(tuple(vals))
        dt = self.datatype()
        if self.at("["):
            self.i += 1
            facets = []
            while True:
                self.expect(*FACETS)
                f = FACETS.get(self.tok.text)
                if f is None:
                    self.fail("expected a facet")
                self.i += 1
                facets.append((f, self.literal()))
                if self.at(","):
                    self.i += 1
                    continue
                break
            self.eat("]")
            return DatatypeRestriction(dt, tuple(facets))
        return dt

    def datatype(self) -> URIRef:
        self.expect("<datatype>")
        t = self.tok.text
        if t in BUILTIN_DATATYPES:
            self.i += 1
            return BUILTIN_DATATYPES[t]
        dt = self.entity("datatype")
        if dt is None and self.tok.kind == "word" and t.startswith("xsd:"):
            self.i += 1
            return XSD[t[4:]]
        if dt is None:
            self.fail("expected a datatype")
        return dt

    def literal(self) -> Literal:
        self.expect("<literal>")
        t = self.tok
        if t.kind == "string":
            self.i += 1
            m = re.match(r'^"((?:[^"\\]|\\.)*)"(?:@([A-Za-z\-]+)|\^\^(.+))?$', t.text)
            body = m.group(1).replace('\\"', '"')
            if m.group(2):
                return Literal(body, lang=m.group(2))
            if m.group(3):
                dt = m.group(3)
                iri = BUILTIN_DATATYPES.get(dt) or (URIRef(dt[1:-1]) if dt.startswith("<")
                                                    else (self.sfp.resolve(dt) or [XSD.string])[0])
                return Literal(body, datatype=iri)
            return Literal(body)
        if t.kind == "number":
            self.i += 1
            txt = t.text
            if txt.lower().endswith("f"):
                return Literal(float(txt[:-1]), datatype=XSD.float)
            if re.fullmatch(r"[+-]?\d+", txt):
                return Literal(int(txt), datatype=XSD.integer)
            return Literal(txt, datatype=XSD.decimal)
        if t.text in ("true", "false"):
            self.i += 1
            return Literal(t.text == "true", datatype=XSD.boolean)
        self.fail("expected a literal")


def parse(text: str, sfp: ShortFormProvider) -> CE:
    """Parse a Manchester class expression; raise :class:`ManchesterError`."""
    p = _Parser(tokenize(text), sfp)
    ce = p.description()
    if p.tok.kind != "eof":
        p.expect("and", "or", "that")
        p.fail("unexpected trailing input")
    return ce


def check(text: str, sfp: ShortFormProvider) -> ManchesterError | None:
    """Protégé's ``OWLExpressionChecker.check`` — ``None`` when well-formed."""
    try:
        parse(text, sfp)
        return None
    except ManchesterError as e:
        return e

# --------------------------------------------------------------------------- #
# Rendering (ManchesterOWLSyntaxObjectRenderer)
# --------------------------------------------------------------------------- #

_PREC = {Or: 1, And: 2, Not: 3}


def _prec(ce) -> int:
    return _PREC.get(type(ce), 4 if isinstance(ce, (Some, Only, HasValue, HasSelf, Card)) else 5)


def render_literal(v: Literal, sfp: ShortFormProvider | None = None) -> str:
    if v.datatype in (XSD.integer, XSD.decimal, XSD.float, XSD.double) and v.language is None:
        return str(v) + ("f" if v.datatype == XSD.float and "f" not in str(v) else "")
    if v.datatype == XSD.boolean:
        return str(v).lower()
    body = '"' + str(v).replace('"', '\\"') + '"'
    if v.language:
        return body + "@" + v.language
    if v.datatype and v.datatype != XSD.string:
        return body + "^^" + (sfp.prefixed(v.datatype) if sfp else f"<{v.datatype}>")
    return body


def render(ce, sfp: ShortFormProvider) -> str:
    def name(iri) -> str:
        return sfp.rendering(iri)

    def prop(p) -> str:
        return f"inverse ({name(p.prop)})" if isinstance(p, Inverse) else name(p)

    def dr(d) -> str:
        if isinstance(d, URIRef):
            builtin = next((k for k, v in BUILTIN_DATATYPES.items() if v == d and ":" in k), None)
            return builtin or name(d)
        if isinstance(d, DatatypeRestriction):
            inv = {v: k for k, v in FACETS.items()}
            fs = ", ".join(f"{inv.get(f, sfp.prefixed(f))} {render_literal(v, sfp)}"
                           for f, v in d.facets)
            return f"{dr(d.datatype)}[{fs}]"
        if isinstance(d, DataOneOf):
            return "{" + ", ".join(render_literal(v, sfp) for v in d.values) + "}"
        if isinstance(d, DataNary):
            return f" {d.op} ".join(dr(x) if not isinstance(x, DataNary) else f"({dr(x)})"
                                    for x in d.operands)
        if isinstance(d, DataComplementOf):
            return f"not {dr(d.operand)}"
        return str(d)

    def sub(child, parent_prec: int) -> str:
        s = r(child)
        return f"({s})" if _prec(child) <= parent_prec and not isinstance(child, URIRef) else s

    def r(x) -> str:
        if isinstance(x, URIRef):
            return name(x)
        if isinstance(x, Or):
            return " or ".join(sub(o, 1) for o in x.operands)
        if isinstance(x, And):
            return " and ".join(sub(o, 2) for o in x.operands)
        if isinstance(x, Not):
            return "not " + sub(x.operand, 3)
        if isinstance(x, OneOf):
            return "{" + ", ".join(name(i) for i in x.individuals) + "}"
        if isinstance(x, (Some, Only)):
            kw = "some" if isinstance(x, Some) else "only"
            return f"{prop(x.prop)} {kw} " + (dr(x.filler) if x.data else sub(x.filler, 3))
        if isinstance(x, HasValue):
            v = render_literal(x.value, sfp) if isinstance(x.value, Literal) else name(x.value)
            return f"{prop(x.prop)} value {v}"
        if isinstance(x, HasSelf):
            return f"{prop(x.prop)} Self"
        if isinstance(x, Card):
            tail = ""
            if x.filler is not None and x.filler != OWL.Thing:
                tail = " " + (dr(x.filler) if x.data else sub(x.filler, 3))
            return f"{prop(x.prop)} {x.kind} {x.n}{tail}"
        if isinstance(x, (DatatypeRestriction, DataOneOf, DataNary, DataComplementOf)):
            return dr(x)
        raise TypeError(f"cannot render {x!r}")

    return r(ce)

# --------------------------------------------------------------------------- #
# Completion (Protégé AutoCompleter)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Completion:
    text: str          # what to insert (quoted if needed)
    kind: str          # "keyword" | entity kind
    iri: str | None = None


_KIND_OF = {"<class>": "class", "<objectProperty>": "objectProperty",
            "<dataProperty>": "dataProperty", "<individual>": "individual",
            "<datatype>": "datatype"}


def complete(text: str, caret: int, sfp: ShortFormProvider, limit: int = 30
             ) -> tuple[str, list[Completion]]:
    """Proposals at *caret*. Returns ``(word_being_completed, proposals)``.

    Algorithm (``AutoCompleter.performAutoCompletion``): take the text up to the
    caret, split off the partial word, parse the prefix and catch the error at
    its end; the error's expected set says *what kind* of thing can come next;
    offer keywords and entity renderings of those kinds that start with the
    partial word.
    """
    head = text[:caret]
    m = re.search(r"('[^']*|[^\s(){}\[\],]*)$", head)
    word = m.group(1) if m else ""
    prefix = head[: len(head) - len(word)]
    expected: set[str] = set()
    try:
        parse(prefix, sfp)
        expected = {"and", "or", "that"}
    except ManchesterError as e:
        expected = e.expected
    needle = word.lstrip("'").lower()
    out: list[Completion] = []
    for kw in sorted(x for x in expected if not x.startswith("<")):
        if kw.lower().startswith(needle):
            out.append(Completion(kw, "keyword"))
    kinds = [_KIND_OF[x] for x in expected if x in _KIND_OF]
    if kinds:
        for iri in sfp.find(needle + "*" if needle else "*", kinds, limit=limit):
            out.append(Completion(sfp.rendering(iri), next(
                k for k in kinds if k in sfp.types_of(iri)), str(iri)))
        if "datatype" in kinds:
            for name, iri in BUILTIN_DATATYPES.items():
                if name.lower().startswith(needle) and ":" in name:
                    out.append(Completion(name, "datatype", str(iri)))
    return word, out[:limit]
