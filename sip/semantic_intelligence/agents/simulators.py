"""Deterministic offline simulators for every agent task.

They are honest stand-ins, not toys pretending to be a model: each implements a
small, documented heuristic (lexical patterns, token similarity, fixed
glossaries), returns output in the *same JSON schema* the real model must use,
and therefore exercises exactly the same critics and submission path. Where a
heuristic cannot do the task (e.g. translation outside the glossary) it
proposes nothing rather than inventing something.
"""

from __future__ import annotations

import json
import re

from .llm import SimulatedModel

_ART = r"(?:a|an|the)\s+"


def _sing(w: str) -> str:
    w = w.strip()
    if w.lower().endswith("ies"):
        return w[:-3] + "y"
    if w.lower().endswith(("sses", "shes", "ches", "xes")):
        return w[:-2]
    if w.lower().endswith("s") and not w.lower().endswith(("ss", "us", "is")):
        return w[:-1]
    return w


#: a sentence ends at . ! ? followed by whitespace, or at a line end ("schema.org" stays whole)
SENTENCE = re.compile(r"(?m)[^\n]+?(?:[.!?](?=\s|$)|$)")


def _sentences(text: str):
    for m in SENTENCE.finditer(text):
        s = m.group().strip()
        if s:
            yield s


# --------------------------------------------------------------------------- #
# requirements.cqs — the ORSD from a brief: purpose and scope from "needs an
# ontology of …", uses from "we need to know …", non-functional requirements from
# "must/should be available|published|…", reuse from a small registry of well-known
# ontologies, and "Which X …?" questions from "X has/is/..." statements
# --------------------------------------------------------------------------- #

#: name in the brief → (namespace IRI, title, default reuse mode)
KNOWN_ONTOLOGIES = {
    "schema.org": ("https://schema.org/", "Schema.org", "align"),
    "fibo": ("https://spec.edmcouncil.org/fibo/ontology/",
             "Financial Industry Business Ontology", "align"),
    "owl-time": ("http://www.w3.org/2006/time#", "OWL-Time", "import"),
    "dublin core": ("http://purl.org/dc/terms/", "DCMI Metadata Terms", "reference"),
    "qudt": ("http://qudt.org/schema/qudt/", "QUDT", "import"),
    "geonames": ("https://www.geonames.org/ontology#", "GeoNames Ontology", "reference"),
}
_SOFT = re.compile(r"\b(?:should|ideally|nice to have|could|may)\b", re.I)


def _quoted(text: str, quote: str) -> dict:
    return {"text": text, "quote": quote}


def sim_requirements(prompt: str, schema: dict) -> dict:
    data = json.loads(prompt)
    brief = data["brief"]
    terms, cqs, reuse = [], [], []
    spec = {"purpose": _quoted("", ""), "scope": _quoted("", ""), "intended_users": [],
            "intended_uses": [], "non_functional": []}
    for s in _sentences(brief):
        m = re.search(r"^(?:the\s+)?(.+?)\s+(?:needs?|wants?|requires?)\s+an?\s+ontology\s+"
                      r"(?:of|for|about|covering)\s+(.+?)[.!?]?$", s, re.I)
        if m:
            spec["purpose"] = _quoted(s, s)
            spec["scope"] = _quoted(m.group(2), m.group(2))
            spec["intended_users"].append(_quoted(m.group(1), m.group(1)))
            continue
        low = s.lower()
        hits = [k for k in KNOWN_ONTOLOGIES if k in low]
        if hits and re.search(r"\b(?:reuse|reused|align|aligned|import|imported|based on)\b",
                              low):
            for k in hits:
                iri, title, mode = KNOWN_ONTOLOGIES[k]
                mode = ("import" if "import" in low else "align" if "align" in low else mode)
                reuse.append({"iri": iri, "title": title, "mode": mode,
                              "rationale": f"the brief asks for {title}", "quote": s})
            continue
        if re.search(r"\b(?:must|should)\s+be\s+(?:available|published|provided|expressed|"
                     r"compatible|licensed|documented)\b", s, re.I):
            spec["non_functional"].append(_quoted(s, s))
            continue
        priority = "should" if _SOFT.search(s) else "must"
        m = re.search(r"\b(?:every|each|all)\s+(\w+)\s+(?:has|have|must have)\s+(?:" + _ART
                      + r")?(?:one or more\s+|at least one\s+)?(\w+)", s, re.I)
        if m:
            a, b = _sing(m.group(1)), _sing(m.group(2))
            terms += [a, b]
            A, B = a[:1].upper() + a[1:], b[:1].upper() + b[1:]
            # NB: "?x rdfs:subClassOf* :B" would always succeed (the zero-length path
            # binds :B itself); the test must ask for the axiom that encodes the claim.
            cqs.append({"id": f"cq_{A}_{B}", "question": f"Does every {a} have some {b}?",
                        "sparql": (f"ASK {{ :{A} rdfs:subClassOf ?r . ?r owl:onProperty ?p ; "
                                   f"owl:someValuesFrom :{B} }}"),
                        "expectation": "ask:true", "priority": priority, "quote": s})
            continue
        m = re.search(r"\b(?:we need to know|track|record)\s+(?:which|what)\s+(\w+)", s, re.I)
        if m:
            a = _sing(m.group(1))
            A = a[:1].upper() + a[1:]
            terms.append(a)
            spec["intended_uses"].append(_quoted(s, s))
            cqs.append({"id": f"cq_{A}", "question": f"Which {a}s are there?",
                        "sparql": f"SELECT ?x WHERE {{ ?x a/rdfs:subClassOf* :{A} }}",
                        "expectation": "non-empty", "priority": priority, "quote": s})
    return {"specification": spec, "reuse": reuse, "terms": sorted(set(terms)), "cqs": cqs}


# --------------------------------------------------------------------------- #
# extraction.candidates — Hearst-style patterns with verbatim quotes
# --------------------------------------------------------------------------- #

_ISA = re.compile(r"\b(?:" + _ART + r")?([A-Z]?[a-z]+(?: [a-z]+)?)\s+(?:is|are)\s+(?:a|an)\s+"
                  r"(?:kind|type|sort) of\s+([a-z]+(?: [a-z]+)?)", re.I)
_ISA2 = re.compile(r"\b(?:Every|Each|A|An)\s+([a-z]+(?: [a-z]+)?)\s+is\s+(?:a|an)\s+"
                   r"([a-z]+(?: [a-z]+)?)\b", re.I)
_SUCH = re.compile(r"\b([a-z]+)s?,?\s+such as\s+([a-z]+(?:s)?(?:,\s*[a-z]+s?)*(?:,?\s+and\s+"
                   r"[a-z]+s?)?)", re.I)
_HAS = re.compile(r"\b(?:Every|Each|A|An)\s+([a-z]+)\s+(has|contains|owns|is made by|"
                  r"is produced by|belongs to)\s+(?:one or more\s+|several\s+|a\s+|an\s+|"
                  r"many\s+)?([a-z]+)", re.I)
_DATA = re.compile(r"\b(?:Every|Each|A|An)\s+([a-z]+)\s+has\s+(?:a|an)\s+([a-z]+(?: [a-z]+)?)"
                   r"\s+(?:recorded as|given as|expressed as|measured in)\s+(?:an?\s+)?"
                   r"(integer|number|decimal|date|text|string)", re.I)
_XSD = {"integer": "xsd:integer", "number": "xsd:decimal", "decimal": "xsd:decimal",
        "date": "xsd:date", "text": "xsd:string", "string": "xsd:string"}
_VERB = {"has": "has", "contains": "contains", "owns": "owns", "is made by": "madeBy",
         "is produced by": "producedBy", "belongs to": "belongsTo"}


def sim_extraction(prompt: str, schema: dict) -> dict:
    text = json.loads(prompt)["document"]
    classes: dict[str, str] = {}
    subs, props = [], []
    data_spans = set()
    for s in _sentences(text):
        for m in _DATA.finditer(s):
            dom, attr, typ = _sing(m.group(1)), m.group(2), m.group(3).lower()
            classes.setdefault(dom.lower(), m.group(0))
            props.append({"name": attr, "kind": "data", "domain": dom, "range": _XSD[typ],
                          "quote": m.group(0)})
            data_spans.add(m.group(0))
        for rx in (_ISA, _ISA2):
            for m in rx.finditer(s):
                if any(m.group(0) in d for d in data_spans):
                    continue
                sub, sup = _sing(m.group(1)), _sing(m.group(2))
                if sub.lower() in ("kind", "type") or sup.lower() == sub.lower()                         or sup.split()[0].lower() in ("kind", "type", "sort"):
                    continue
                classes.setdefault(sub.lower(), m.group(0))
                classes.setdefault(sup.lower(), m.group(0))
                subs.append({"sub": sub, "sup": sup, "quote": m.group(0)})
        for m in _SUCH.finditer(s):
            sup = _sing(m.group(1))
            classes.setdefault(sup.lower(), m.group(0))
            for sub in re.split(r",\s*|\s+and\s+", m.group(2)):
                sub = _sing(sub.strip())
                if sub:
                    classes.setdefault(sub.lower(), m.group(0))
                    subs.append({"sub": sub, "sup": sup, "quote": m.group(0)})
        for m in _HAS.finditer(s):
            if any(m.group(0) in d or d in s for d in data_spans if m.group(1) in d):
                continue
            dom, verb, rng = _sing(m.group(1)), m.group(2).lower(), _sing(m.group(3))
            classes.setdefault(dom.lower(), m.group(0))
            classes.setdefault(rng.lower(), m.group(0))
            props.append({"name": f"{_VERB[verb]} {rng}" if verb == "has" else _VERB[verb],
                          "kind": "object", "domain": dom, "range": rng, "quote": m.group(0)})
    seen_sub = set()
    uniq_subs = []
    for x in subs:
        k = (x["sub"].lower(), x["sup"].lower())
        if k not in seen_sub:
            seen_sub.add(k)
            uniq_subs.append(x)
    return {"classes": [{"name": n, "quote": q} for n, q in classes.items()],
            "subclasses": uniq_subs, "properties": props}


# --------------------------------------------------------------------------- #
# modeling.axioms — existential restrictions from domain/range evidence
# --------------------------------------------------------------------------- #

def sim_modeling(prompt: str, schema: dict) -> dict:
    data = json.loads(prompt)
    cls = data["class"]
    vocab = data["vocabulary"]
    frame = data["frame"]
    have = " ".join(r["text"] for rows in frame.values() for r in rows)
    out = []
    ev = data.get("evidence", "")
    for item in vocab["objectProperties"]:
        local, _label, dom, rng = (item.split("|") + ["", ""])[:4]
        if dom != cls or not rng or local in have:
            continue
        # "Every <cls> has/is made by ... <range>" in the evidence -> existential restriction
        sent = next((s for s in _sentences(ev)
                     if re.search(rf"\bevery\s+{re.escape(cls)}\b", s, re.I)
                     and re.search(rf"\b{re.escape(rng)}s?\b", s, re.I)), None)
        if sent:
            out.append({"kind": "SubClassOf", "expression": f"{local} some {rng}",
                        "rationale": f"the evidence states that every {cls} has some {rng}",
                        "quote": sent, "confidence": 0.75})
    return {"axioms": out}


# --------------------------------------------------------------------------- #
# vocabulary.labels — glossary-only translation (honest: no glossary, no label)
# --------------------------------------------------------------------------- #

GLOSSARY = {
    ("fr", "vehicle"): "véhicule", ("fr", "car"): "voiture", ("fr", "wheel"): "roue",
    ("fr", "engine"): "moteur", ("fr", "truck"): "camion", ("fr", "manufacturer"): "constructeur",
    ("fr", "has part"): "a pour partie", ("fr", "customer"): "client",
    ("fr", "product"): "produit", ("fr", "organisation"): "organisation",
    ("de", "vehicle"): "Fahrzeug", ("de", "car"): "Auto", ("de", "wheel"): "Rad",
    ("de", "engine"): "Motor", ("de", "truck"): "Lastwagen",
}


def sim_vocabulary(prompt: str, schema: dict) -> dict:
    out = []
    for it in json.loads(prompt)["items"]:
        for lang in it["missing"]:
            t = GLOSSARY.get((lang, it["existing"].lower()))
            if t:
                out.append({"resource": it["resource"], "lang": lang, "label": t,
                            "confidence": 0.9})
    return {"labels": out}


def sim_alignment(prompt: str, schema: dict) -> dict:
    return {"decisions": [{"entity1": c["entity1"], "entity2": c["entity2"],
                           "decision": "accept" if c["measure"] >= 0.85 else "reject",
                           "relation": "=", "reason": f"label similarity {c['measure']}"}
                          for c in json.loads(prompt)["cells"]]}


def sim_quality(prompt: str, schema: dict) -> dict:
    """Pick, per unsatisfiable class, the SubClassOf axiom on the class itself that
    occurs in the fewest justifications (the 'least shared, most specific' rule)."""
    out = []
    for item in json.loads(prompt)["unsatisfiable"]:
        counts: dict[str, int] = {}
        for j in item["justifications"]:
            for ax in j:
                counts[ax] = counts.get(ax, 0) + 1
        own = [ax for ax in counts if ax.startswith(item["cls"] + " SubClassOf ")]
        if not own:
            continue
        ax = sorted(own, key=lambda a: (counts[a], a))[-1]
        out.append({"cls": item["cls"], "remove_kind": "SubClassOf", "subject": item["cls"],
                    "expression": ax.split(" SubClassOf ", 1)[1],
                    "reason": "the class's own assertion that participates in the conflict"})
    return {"repairs": out}


def sim_steward(prompt: str, schema: dict) -> dict:
    out = []
    for r in json.loads(prompt)["pending"]:
        ev = r.get("evidence") or {}
        why = ev.get("rationale") or "no rationale recorded"
        src = f" Source: \"{ev['quote']}\"." if ev.get("quote") else ""
        out.append({"commit": r["commit"],
                    "summary": f"{r['operation']} proposed by {r['principal']}: {why}.{src}"})
    return {"summaries": out}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def sim_kg_mapping(prompt: str, schema: dict) -> dict:
    data = json.loads(prompt)
    header = [h.strip() for h in data["header"].split(",")]
    vocab = data["vocabulary"]
    classes = [c.split("|")[0] for c in vocab["classes"]]
    # class: the vocabulary class whose name best matches the most header columns' context
    first = header[0].lower().replace("_id", "").replace("id", "")
    cls = next((c for c in classes if _norm(c) and _norm(c) in _norm(first)), classes[0]
               if classes else "Thing")
    id_col = next((h for h in header if h.lower() in ("id", f"{cls.lower()}_id")
                   or h.lower().endswith("_id")), header[0])
    label_col = next((h for h in header if h.lower() in ("name", "label", "title")), "")
    cols = []
    for h in header:
        if h in (id_col, label_col):
            continue
        hn = _norm(h)
        for item in vocab["dataProperties"]:
            local = item.split("|")[0]
            if _norm(local) == hn or _norm(local).endswith(hn):
                dt = "xsd:integer" if re.search(r"year|count|number|qty", h, re.I) else "xsd:string"
                cols.append({"column": h, "property": local, "kind": "data", "datatype": dt,
                             "target_class": ""})
                break
        else:
            for item in vocab["objectProperties"]:
                local = item.split("|")[0]
                tgt = next((c for c in classes if _norm(c) == hn), None)
                if tgt and hn in _norm(local):
                    cols.append({"column": h, "property": local, "kind": "object",
                                 "datatype": "", "target_class": tgt})
                    break
    return {"cls": cls, "id_column": id_col, "label_column": label_col, "columns": cols}


def sim_assistant(prompt: str, schema: dict) -> dict:
    data = json.loads(prompt)
    q = data["question"]
    classes = [c.split("|") for c in data["vocabulary"]["classes"]]
    m = re.search(r"\b(?:which|what|list)\s+(\w+)", q, re.I)
    target = None
    if m:
        w = _sing(m.group(1)).lower()
        target = next((loc for loc, lab in classes if lab.lower() == w or loc.lower() == w), None)
    if target is None:
        return {"sparql": "SELECT ?x WHERE { ?x a owl:Class }", "answer_template":
                "I could not map the question; the ontology's classes are: {answer}"}
    return {"sparql": f"SELECT DISTINCT ?x WHERE {{ ?x a/rdfs:subClassOf* :{target} }}",
            "answer_template": f"The {target} instances are: {{answer}}"}


# --------------------------------------------------------------------------- #
# semantic.verify — a domain expert with nothing but the reference text. Facts are
# read from "every X has a Y", "every X is <verb> by a Y", "a X is a (kind of) Y",
# "no X is a Y" and "Ys, such as A and B"; each controlled-English statement is
# then judged against them. Anything the reference does not settle is "unsure":
# the simulator never claims domain knowledge it was not given.
# --------------------------------------------------------------------------- #

_QTY = r"(?:a|an|one or more|several|some|many|at least one|exactly one)\s+"


def _noun(s: str) -> str:
    words = re.sub(r"[^a-z0-9 ]", " ", s.lower()).split()
    return " ".join(words[:-1] + [_sing(words[-1])]) if words else ""


def _reference_facts(text: str) -> dict:
    isa, has, disjoint = set(), set(), set()       # has: (subject, object, verb phrase)
    for sent in _sentences(text):
        s = sent.rstrip(".!?").strip()
        if m := re.fullmatch(r"(?:no)\s+(.+?)\s+is\s+an?\s+(.+)", s, re.I):
            disjoint.add(frozenset((_noun(m.group(1)), _noun(m.group(2)))))
        elif m := re.fullmatch(r"(?:an?|every|each)\s+(.+?)\s+is\s+(?:a\s+kind\s+of|a\s+type\s+of"
                               r"|an?)\s+(.+)", s, re.I):
            isa.add((_noun(m.group(1)), _noun(m.group(2))))
        elif m := re.fullmatch(r"(?:an?|every|each)\s+(.+?)\s+is\s+(\w+\s+by)\s+an?\s+(.+)", s,
                               re.I):
            has.add((_noun(m.group(1)), _noun(m.group(3)), m.group(2).lower()))
        elif m := re.fullmatch(r"(?:an?|every|each)\s+(.+?)\s+(?:has|have)\s+(?:" + _QTY
                               + r")?(.+?)(?:\s+(?:recorded|stored|given|which|that)\b.*)?", s,
                               re.I):
            has.add((_noun(m.group(1)), _noun(m.group(2)), "has"))
        if m := re.search(r"(\w+?)s?,\s+such\s+as\s+(.+?),", s, re.I):
            y = _noun(m.group(1))
            for item in re.split(r",|\band\b", m.group(2)):
                item = _noun(item)
                if item:
                    isa.add((item, y))
                    if item.endswith(" " + y):
                        isa.add((item[: -len(y) - 1], y))
    return {"isa": isa, "has": has, "disjoint": disjoint}


def _above(isa: set, a: str) -> set:
    seen, todo = {a}, [a]
    while todo:
        x = todo.pop()
        for s, o in isa:
            if s == x and o not in seen:
                seen.add(o)
                todo.append(o)
    return seen


def _uses(fact: tuple, prop: str) -> bool:
    """Does the reference fact (s, o, verb) use the property called *prop*?"""
    _, o, verb = fact
    return prop == verb or (verb == "has" and o.split()[-1] in prop.split())


def _judge(st: str, f: dict) -> tuple[str, str]:
    isa, has, dis = f["isa"], f["has"], f["disjoint"]
    st = st.rstrip(".")
    if m := re.fullmatch(r"Every (.+?) is an? (.+)", st):
        a, b = _noun(m.group(1)), _noun(m.group(2))
        if b in _above(isa, a):
            return "holds", f"the reference says every {a} is a {b}"
        if a in _above(isa, b) and a != b:
            return "false", f"the reference says it is the other way round: every {b} is a {a}"
        if frozenset((a, b)) in dis:
            return "false", f"the reference says no {a} is a {b}"
    elif m := re.fullmatch(r"Nothing is both an? (.+?) and an? (.+)", st):
        a, b = _noun(m.group(1)), _noun(m.group(2))
        if frozenset((a, b)) in dis:
            return "holds", f"the reference says no {a} is a {b}"
        if b in _above(isa, a) or a in _above(isa, b):
            return "false", f"the reference says one is a kind of the other"
    elif m := re.fullmatch(r"Every (.+?) is related by '(.+?)' (to at least one|to no|only to) "
                           r"(.+?)(?: things)?", st):
        a, p, q, b = _noun(m.group(1)), m.group(2), m.group(3), _noun(m.group(4))
        mine = [x for x in has if x[0] in _above(isa, a) and _uses(x, p)]
        said = [x for x in mine if b in _above(isa, x[1])]
        other = [x for x in mine if x not in said]
        if q == "to no":
            if said:
                return "false", f"the reference says every {a} has a {b}"
        elif said:
            return "holds", f"the reference says every {a} has a {b}"
        elif other:
            return "false", f"the reference says '{p}' leads to a {other[0][1]}, not a {b}"
    elif m := re.fullmatch(r"Anything related by '(.+?)' to something is an? (.+)", st):
        p, d = m.group(1), _noun(m.group(2))
        uses = [x for x in has if _uses(x, p)]
        if any(x[0] == d for x in uses):
            return "holds", f"the reference uses '{p}' for a {d}"
        if uses:
            return "false", f"the reference uses '{p}' for a {uses[0][0]}, not a {d}"
    elif m := re.fullmatch(r"Anything that something is related to by '(.+?)' is an? (.+)", st):
        p, r = m.group(1), _noun(m.group(2))
        uses = [x for x in has if _uses(x, p)]
        if any(x[1] == r for x in uses):
            return "holds", f"the reference says '{p}' leads to a {r}"
        if uses:
            return "false", f"the reference says '{p}' leads to a {uses[0][1]}, not a {r}"
    return "unsure", "the reference does not settle it"


def sim_semantic(prompt: str, schema: dict) -> dict:
    data = json.loads(prompt)
    facts = _reference_facts(data["reference"])
    out = []
    for s in data["statements"]:
        verdict, reason = _judge(s["statement"], facts)
        out.append({"id": s["id"], "verdict": verdict, "reason": reason})
    return {"verdicts": out}


def simulated_model() -> SimulatedModel:
    m = SimulatedModel()
    for task, fn in {"requirements.cqs": sim_requirements,
                     "extraction.candidates": sim_extraction,
                     "modeling.axioms": sim_modeling, "vocabulary.labels": sim_vocabulary,
                     "alignment.adjudicate": sim_alignment, "quality.repair": sim_quality,
                     "steward.summaries": sim_steward, "kg.mapping": sim_kg_mapping,
                     "assistant.sparql": sim_assistant,
                     "semantic.verify": sim_semantic}.items():
        m.register(task, fn)
    return m
