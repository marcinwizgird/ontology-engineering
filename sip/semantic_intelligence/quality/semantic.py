"""Semantic verification of axioms: is what the ontology says *true in the domain*?

The ICV checks and the reasoner find structural and logical defects; neither can see
an axiom that is consistent but wrong — ``Vehicle SubClassOf hasEngine only Engine``
where the domain says "some", a filler swapped for a sibling, a domain and range the
wrong way round. Tsaneva, Vasic & Sabou (ESWC 2024) showed the workable set-up: read
each restriction as a controlled-English sentence and ask a domain expert (or an LLM
acting as one) whether it holds.

This module is the deterministic half of that set-up:

* :func:`statements` verbalises the verifiable axioms of a graph (subclass, some,
  only, cardinality, has-value, domain, range, disjointness over *named* classes);
* :func:`mutants` seeds wrong axioms from the right ones (an existential negated,
  a filler replaced by an unrelated class, domain and range swapped, a subclass link
  reversed, disjointness with a superclass) — the calibration set;
* :func:`calibration` scores a verifier's verdicts on originals and mutants together,
  so its findings carry a *measured* precision instead of a claimed one.

A verifier's verdicts are advisory: they never block the release gate. The
reason is in the numbers — a verifier that catches 80 % of seeded mutants still
mislabels some correct axioms, and only a human can tell which.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDFS, XSD

from ..owl.frames import render_axiom
from ..owl.model import Axiom, Card, HasValue, Only, Some, axioms
from ..owl.rendering import ShortFormProvider

MUTATIONS = ("negation", "filler", "swap", "reverse", "disjoint")


@dataclass
class Statement:
    """One axiom (or seeded mutant) as a sentence a domain expert can judge."""
    id: str
    kind: str
    subject: str
    manchester: str
    english: str
    mutation: str | None = None          # None = an axiom of the ontology

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def _words(s: str) -> str:
    """'hasEngine' / 'has engine' / 'DieselEngine' → 'has engine' / 'diesel engine'."""
    s = s.strip("'\"")
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s).replace("_", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def _a(noun: str) -> str:
    return ("an " if noun[:1] in "aeiou" else "a ") + noun


def _sid(prefix: str, text: str) -> str:
    return f"{prefix}-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:8]}"


def _named(x) -> bool:
    return isinstance(x, URIRef)


def _restriction(r, n) -> str | None:
    """'is related by 'has engine' to at least one engine' — or None if not verbalisable."""
    if getattr(r, "data", False) or not _named(getattr(r, "prop", None)):
        return None
    p = f"'{_words(n(r.prop))}'"
    if isinstance(r, Some) and _named(r.filler):
        return f"is related by {p} to at least one {_words(n(r.filler))}"
    if isinstance(r, Only) and _named(r.filler):
        return f"is related by {p} only to {_words(n(r.filler))} things"
    if isinstance(r, HasValue) and _named(r.value):
        return f"is related by {p} to {n(r.value)}"
    if isinstance(r, Card) and (r.filler is None or _named(r.filler)):
        what = _words(n(r.filler)) if r.filler is not None else "thing"
        if r.kind == "max" and r.n == 0:
            return f"is related by {p} to no {what}"
        word = {"min": "at least", "max": "at most", "exactly": "exactly"}[r.kind]
        return f"is related by {p} to {word} {r.n} {what}"
    return None


def verbalise(ax: Axiom, sfp: ShortFormProvider) -> str | None:
    """Controlled English for *ax*, or ``None`` when it is not a verifiable restriction."""
    n = sfp.rendering
    k, a = ax.kind, ax.args
    if k == "SubClassOf" and _named(a[0]):
        sub = _words(n(a[0]))
        if _named(a[1]):
            return f"Every {sub} is {_a(_words(n(a[1])))}."
        r = _restriction(a[1], n)
        return f"Every {sub} {r}." if r else None
    if k == "DisjointClasses" and len(a) == 2 and all(_named(x) for x in a):
        x, y = (_words(n(c)) for c in a)
        return f"Nothing is both {_a(x)} and {_a(y)}."
    if k == "PropertyDomain" and _named(a[0]) and _named(a[1]):
        return f"Anything related by '{_words(n(a[0]))}' to something is {_a(_words(n(a[1])))}."
    if k == "PropertyRange" and _named(a[0]) and _named(a[1]) \
            and not str(a[1]).startswith((str(XSD), str(RDFS.Literal))):
        return (f"Anything that something is related to by '{_words(n(a[0]))}' "
                f"is {_a(_words(n(a[1])))}.")
    return None


def statements(g: Graph, sfp: ShortFormProvider | None = None,
               limit: int | None = None) -> list[Statement]:
    """The verifiable axioms of *g* as sentences, in a stable order."""
    sfp = sfp or ShortFormProvider(g)
    out: dict[str, Statement] = {}
    for ax in axioms(g, include_annotations=False):
        en = verbalise(ax, sfp)
        if en is None:
            continue
        man = render_axiom(ax, sfp)
        sub = sfp.rendering(ax.args[0])
        out.setdefault(man, Statement(_sid("ax", man), ax.kind, sub, man, en))
    items = sorted(out.values(), key=lambda s: s.manchester)
    return items[:limit] if limit else items


# --------------------------------------------------------------------------- #
# Seeded mutants — the calibration set
# --------------------------------------------------------------------------- #


def _supers(g: Graph) -> dict[URIRef, set[URIRef]]:
    """Named class → its named superclasses (reflexive, transitive)."""
    direct: dict[URIRef, set[URIRef]] = {}
    for s, o in g.subject_objects(RDFS.subClassOf):
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            direct.setdefault(s, set()).add(o)
    out = {}
    for c in set(direct) | {o for v in direct.values() for o in v}:
        seen, todo = {c}, [c]
        while todo:
            for o in direct.get(todo.pop(), ()):
                if o not in seen:
                    seen.add(o)
                    todo.append(o)
        out[c] = seen
    return out


def _classes(g: Graph) -> list[URIRef]:
    cs = {c for c in g.subjects(None, OWL.Class) if isinstance(c, URIRef)}
    cs |= {c for pair in g.subject_objects(RDFS.subClassOf) for c in pair
           if isinstance(c, URIRef) and c != OWL.Thing}
    return sorted(cs)


def _unrelated(c: URIRef, avoid: set[URIRef], classes: list[URIRef],
               sup: dict[URIRef, set[URIRef]]) -> URIRef | None:
    """The first class that is neither *c*, nor above or below it, nor in *avoid*."""
    for d in classes:
        if d in avoid or d == c:
            continue
        if d in sup.get(c, {c}) or c in sup.get(d, {d}):
            continue
        return d
    return None


def mutants(g: Graph, sfp: ShortFormProvider | None = None,
            limit: int | None = None) -> list[Statement]:
    """Wrong axioms seeded from the right ones, one family per :data:`MUTATIONS` entry.

    A mutant of a *wrong* original can be right, so calibration is honest only on an
    ontology whose axioms were reviewed; the score is a property of the verifier on
    *this* domain, which is the point of computing it here rather than on Pizza.
    """
    sfp = sfp or ShortFormProvider(g)
    sup, classes = _supers(g), _classes(g)
    axs = list(axioms(g, include_annotations=False))
    domains = {a.args[0]: a.args[1] for a in axs if a.kind == "PropertyDomain"
               and _named(a.args[1])}
    ranges = {a.args[0]: a.args[1] for a in axs if a.kind == "PropertyRange"
              and _named(a.args[1])}
    out: dict[str, Statement] = {}

    def add(kind_: str, mutation: str, ax: Axiom) -> None:
        en = verbalise(ax, sfp)
        if en is None:
            return
        man = render_axiom(ax, sfp)
        sub = sfp.rendering(ax.args[0])
        out.setdefault(man, Statement(_sid("mu", mutation + man), kind_, sub, man, en,
                                      mutation))

    for ax in axs:
        k, a = ax.kind, ax.args
        if k == "SubClassOf" and _named(a[0]):
            sub, sup_ = a
            # NB: some -> only is *not* a safe mutant: "every vehicle has wheels only of
            # kind wheel" is usually true. Negating the existential always is false.
            if isinstance(sup_, Some) and _named(sup_.filler):
                add(k, "negation", Axiom(k, (sub, Card("max", 0, sup_.prop, sup_.filler))))
            if isinstance(sup_, (Some, Only)) and _named(sup_.filler):
                d = _unrelated(sup_.filler, {sub}, classes, sup)
                if d is not None:
                    add(k, "filler", Axiom(k, (sub, type(sup_)(sup_.prop, d))))
            if _named(sup_) and sup_ != OWL.Thing:
                add(k, "reverse", Axiom(k, (sup_, sub)))
                add("DisjointClasses", "disjoint",
                    Axiom("DisjointClasses", (sub, sup_)))
    for p in sorted(set(domains) & set(ranges)):
        if domains[p] != ranges[p]:
            add("PropertyDomain", "swap", Axiom("PropertyDomain", (p, ranges[p])))
            add("PropertyRange", "swap", Axiom("PropertyRange", (p, domains[p])))
    have = {s.manchester for s in statements(g, sfp)}
    items = sorted((s for s in out.values() if s.manchester not in have),
                   key=lambda s: (s.mutation or "", s.manchester))
    return items[:limit] if limit else items


# --------------------------------------------------------------------------- #
# Calibration
# --------------------------------------------------------------------------- #


def calibration(verdicts: dict[str, str], originals: list[Statement],
                seeded: list[Statement]) -> dict:
    """Score a verifier: did it call the mutants false and leave the originals alone?

    ``precision`` = mutants called false / everything called false; ``recall`` =
    mutants called false / mutants; ``coverage`` = share of statements given a
    verdict other than ``unsure``. ``None`` where the denominator is zero.
    """
    caught = sum(1 for s in seeded if verdicts.get(s.id) == "false")
    alarms = sum(1 for s in originals if verdicts.get(s.id) == "false")
    judged = sum(1 for s in originals + seeded if verdicts.get(s.id) in ("holds", "false"))
    total = len(originals) + len(seeded)
    by = {}
    for m in MUTATIONS:
        ms = [s for s in seeded if s.mutation == m]
        if ms:
            by[m] = {"seeded": len(ms),
                     "caught": sum(1 for s in ms if verdicts.get(s.id) == "false")}
    return {"originals": len(originals), "mutants": len(seeded), "caught": caught,
            "false_alarms": alarms,
            "precision": round(caught / (caught + alarms), 3) if caught + alarms else None,
            "recall": round(caught / len(seeded), 3) if seeded else None,
            "coverage": round(judged / total, 3) if total else None,
            "by_mutation": by}
