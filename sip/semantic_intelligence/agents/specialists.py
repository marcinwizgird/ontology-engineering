"""The specialist agents — one or more per lifecycle stage (FR-AG-01).

======================  ========  ===============================================
agent                   stage     writes (always staged)
======================  ========  ===============================================
RequirementsAgent       scope     competency questions (+ SPARQL tests)
ExtractionAgent         acquire   classes, subclass links, properties — grounded
ModelingCopilot         model     Manchester axioms that survive the reasoner
VocabularyAgent         model     missing labels in project languages
AlignmentAgent          model     mapping triples (mappings graph)
QualityAgent            validate  ICV fixes; repairs of unsatisfiable classes
StewardAgent            review    nothing — summaries and recommendations
KnowledgeGraphBuilder   populate  lifted individuals; owl:sameAs proposals
AssistantAgent          consume   nothing — grounded answers with cited rows
======================  ========  ===============================================

Every agent has a ``system_prompt`` (stable, cacheable), a JSON schema for its
model output and a critic. The critics are where the guarantees live; the model
can only make proposals *better*, never make an unsafe one pass.
"""

from __future__ import annotations

import json
import re

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS
from rdflib.plugins.sparql import prepareQuery

from ..owl import manchester
from ..owl.model import Axiom, axiom_triples
from ..owl.rendering import ShortFormProvider, local_name
from ..reasoning.reasoner import ReasonerManager
from .base import Agent, Proposal


def _obj(props: dict, required=None) -> dict:
    return {"type": "object", "properties": props, "required": required or list(props),
            "additionalProperties": False}


_STR = {"type": "string"}
_NUM = {"type": "number"}


def _camel(s: str, upper: bool = True) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", s)
    if not parts:
        return s
    out = "".join(p[:1].upper() + p[1:] for p in parts)
    return out if upper else out[:1].lower() + out[1:]


def _vocabulary(ctx) -> dict:
    """Compact signature of the ontology for prompts (names + labels)."""
    g = ctx.ontology(staged=True)
    sfp = ShortFormProvider(g)

    def items(t, with_signature=False):
        out = set()
        for s in g.subjects(RDF.type, t):
            if not isinstance(s, URIRef):
                continue
            row = f"{local_name(s)}|{sfp.render(s)}"
            if with_signature:
                d, r = g.value(s, RDFS.domain), g.value(s, RDFS.range)
                row += f"|{local_name(d) if isinstance(d, URIRef) else ''}"                        f"|{local_name(r) if isinstance(r, URIRef) else ''}"
            out.add(row)
        return sorted(out)[:300]
    return {"classes": items(OWL.Class),
            "objectProperties": items(OWL.ObjectProperty, True),
            "dataProperties": items(OWL.DatatypeProperty, True)}

# =========================================================================== #
# Scope
# =========================================================================== #


class RequirementsAgent(Agent):
    name, stage, roles = "requirements", "scope", ("agent-ontology-copilot",)
    description = "Turns a project brief into competency questions with SPARQL tests."
    system_prompt = (
        "You are an ontology requirements engineer. From a project brief, write competency "
        "questions (CQs) the ontology must answer. For each CQ give an executable SPARQL 1.1 "
        "SELECT or ASK query over the ontology's namespace (use the prefix ':' for the "
        "project namespace; rdf:, rdfs:, owl:, skos: are predefined) and an expectation: "
        "'non-empty', 'empty', 'count>=N' or 'ask:true'. Also list the key domain terms. "
        "Only use terms the brief supports.")
    SCHEMA = _obj({"terms": {"type": "array", "items": _STR},
                   "cqs": {"type": "array", "items": _obj({
                       "id": _STR, "question": _STR, "sparql": _STR, "expectation": _STR,
                       "quote": _STR})}})

    def run(self, project: str, brief: str) -> "AgentRun":
        run = self.start(project)
        ctx = self.platform.projects[project]
        ns = ctx.config.default_namespace
        out = self.ask(run, "requirements.cqs",
                       json.dumps({"brief": brief, "namespace": ns}), self.SCHEMA)
        if out is None:
            return self.finish(run)
        prefixes = (f"PREFIX : <{ns}>\nPREFIX rdf: <{RDF}>\nPREFIX rdfs: <{RDFS}>\n"
                    f"PREFIX owl: <{OWL}>\nPREFIX skos: <http://www.w3.org/2004/02/skos/core#>\n")
        for cq in out["cqs"]:
            q = cq["sparql"] if cq["sparql"].lstrip().upper().startswith("PREFIX") \
                else prefixes + cq["sparql"]
            critic = []
            try:
                prepareQuery(q)
            except Exception as exc:  # noqa: BLE001
                critic.append(f"SPARQL does not parse: {exc}")
            if not re.fullmatch(r"non-empty|empty|count>=\d+|ask:(true|false)|contains:.+",
                                cq["expectation"]):
                critic.append(f"bad expectation {cq['expectation']!r}")
            if cq.get("quote") and cq["quote"] not in brief:
                critic.append("quote is not verbatim from the brief")
            self.submit(run, Proposal("quality.addCompetencyQuestion",
                                      {"id": re.sub(r"[^A-Za-z0-9_-]", "_", cq["id"]),
                                       "question": cq["question"], "sparql": q,
                                       "expectation": cq["expectation"]},
                                      "derived from the brief",
                                      {"quote": cq.get("quote")}, 0.7, critic))
        return self.finish(run, {"terms": out["terms"]})

# =========================================================================== #
# Acquire
# =========================================================================== #


class ExtractionAgent(Agent):
    name, stage, roles = "extraction", "acquire", ("agent-ontology-copilot",)
    description = "Grounded extraction of classes, taxonomy and relations from documents."
    system_prompt = (
        "You extract ontology candidates from a document. Return classes, subclass relations "
        "and object/data properties. For every candidate give 'quote': an EXACT verbatim "
        "span of the source text (copy it character for character) that states it. Do not "
        "invent candidates the text does not state. Names are singular nouns.")
    SCHEMA = _obj({
        "classes": {"type": "array", "items": _obj({"name": _STR, "quote": _STR})},
        "subclasses": {"type": "array", "items": _obj({"sub": _STR, "sup": _STR,
                                                       "quote": _STR})},
        "properties": {"type": "array", "items": _obj({
            "name": _STR, "kind": {"type": "string", "enum": ["object", "data"]},
            "domain": _STR, "range": _STR, "quote": _STR})}})

    def run(self, project: str, source_id: str) -> "AgentRun":
        run = self.start(project)
        ctx = self.platform.projects[project]
        src = ctx.sources[source_id]
        text = src["content"]
        out = self.ask(run, "extraction.candidates", json.dumps(
            {"document": text, "existing": _vocabulary(ctx)}), self.SCHEMA)
        if out is None:
            return self.finish(run)
        existing = {local_name(s).lower() for s in ctx.ontology(staged=True).subjects(
            RDF.type, OWL.Class)}

        def ground(quote: str) -> tuple[list[str], dict]:
            i = text.find(quote) if quote else -1
            if i < 0:
                return [f"quote not found verbatim in {source_id}"], {}
            return [], {"source": source_id, "sha256": src["sha256"], "quote": quote,
                        "char_start": i, "char_end": i + len(quote)}
        created: set[str] = set()
        for c in out["classes"]:
            name = _camel(c["name"])
            critic, ev = ground(c["quote"])
            if name.lower() in existing or name in created:
                critic.append("class already exists")
            p = self.submit(run, Proposal("owl.createClass", {"name": name,
                                                              "label": c["name"].strip()},
                                          "stated in source", ev, 0.8, critic))
            if p.commit:
                created.add(name)
        known = existing | {n.lower() for n in created}
        for s in out["subclasses"]:
            sub, sup = _camel(s["sub"]), _camel(s["sup"])
            critic, ev = ground(s["quote"])
            for n in (sub, sup):
                if n.lower() not in known:
                    critic.append(f"{n} is not a known or proposed class")
            self.submit(run, Proposal("owl.addAxiom", {"subject": sub, "kind": "SubClassOf",
                                                       "expression": sup},
                                      "taxonomy stated in source", ev, 0.8, critic))
        for pr in out["properties"]:
            name = _camel(pr["name"], upper=False)
            critic, ev = ground(pr["quote"])
            dom = _camel(pr["domain"])
            if dom.lower() not in known:
                critic.append(f"domain {dom} unknown")
            rng = pr["range"] if pr["kind"] == "data" else _camel(pr["range"])
            if pr["kind"] == "object" and rng.lower() not in known:
                critic.append(f"range {rng} unknown")
            if pr["kind"] == "data" and not rng.startswith("xsd:"):
                critic.append("data property range must be an xsd: datatype")
            self.submit(run, Proposal("owl.createProperty", {
                "name": name, "kind": pr["kind"], "domain": dom, "range": rng,
                "label": pr["name"]}, "relation stated in source", ev, 0.7, critic))
        return self.finish(run)

# =========================================================================== #
# Model
# =========================================================================== #


class ModelingCopilot(Agent):
    name, stage, roles = "modeling", "model", ("agent-ontology-copilot",)
    description = "Proposes class axioms in Manchester syntax; keeps only those the reasoner accepts."
    system_prompt = (
        "You are an OWL 2 modelling assistant. Given a class, its current description and "
        "the vocabulary, propose missing necessary conditions (SubClassOf) or a definition "
        "(EquivalentTo) in Manchester OWL syntax, using ONLY the given entity names. Prefer "
        "few, high-value axioms. Give a one-sentence rationale each and, when the axiom "
        "rests on the evidence text, the verbatim sentence it rests on as 'quote' (else '').")
    SCHEMA = _obj({"axioms": {"type": "array", "items": _obj({
        "kind": {"type": "string", "enum": ["SubClassOf", "EquivalentTo", "DisjointWith"]},
        "expression": _STR, "rationale": _STR, "quote": _STR, "confidence": _NUM})}})

    def run(self, project: str, cls: str, evidence_text: str = "") -> "AgentRun":
        run = self.start(project)
        ctx = self.platform.projects[project]
        frame = self.read(run, "browse.classFrame", cls=cls, include_inferred=False)
        out = self.ask(run, "modeling.axioms", json.dumps(
            {"class": cls, "frame": frame, "vocabulary": _vocabulary(ctx),
             "evidence": evidence_text}), self.SCHEMA)
        if out is None:
            return self.finish(run)
        sfp = ctx.sfp(staged=True)
        base = ctx.ontology(staged=True)
        for ax in out["axioms"]:
            critic = []
            err = manchester.check(ax["expression"], sfp)
            if err is not None:
                critic.append(f"Manchester: {err}")
            else:
                critic += self._logical_critic(ctx, base, cls, ax["kind"], ax["expression"], sfp)
            quote = ax.get("quote") or ""
            ev = {}
            if quote:
                i = evidence_text.find(quote)
                if i < 0:
                    critic.append("quote is not verbatim from the evidence")
                else:
                    ev = {"quote": quote, "char_start": i, "char_end": i + len(quote)}
            self.submit(run, Proposal("owl.addAxiom", {"subject": cls, "kind": ax["kind"],
                                                       "expression": ax["expression"]},
                                      ax["rationale"], ev, float(ax.get("confidence", 0.5)),
                                      critic))
        return self.finish(run)

    @staticmethod
    def _logical_critic(ctx, base: Graph, cls: str, kind: str, expr: str, sfp) -> list[str]:
        """Reject an axiom that would make the ontology inconsistent or a class unsatisfiable."""
        from ..platform import _iri
        ce = manchester.parse(expr, sfp)
        s = _iri(ctx, cls)
        ax = Axiom({"SubClassOf": "SubClassOf", "EquivalentTo": "EquivalentClasses",
                    "DisjointWith": "DisjointClasses"}[kind], (s, ce))
        probe = Graph()
        for t in base:
            probe.add(t)
        before = ReasonerManager().classify(base)
        for t in axiom_triples(ax):
            probe.add(t)
        after = ReasonerManager().classify(probe)
        out = []
        if before.consistent and not after.consistent:
            out.append("would make the ontology inconsistent (OWL2-RL)")
        new_unsat = set(after.unsatisfiable) - set(before.unsatisfiable)
        if new_unsat:
            out.append("would make unsatisfiable: " + ", ".join(sfp.render(u) for u in new_unsat))
        return out


class VocabularyAgent(Agent):
    name, stage, roles = "vocabulary", "model", ("agent-thesaurus-copilot",)
    description = "Fills missing labels in the project languages (from the ICV finding)."
    system_prompt = (
        "You are a terminologist. For each resource, propose a label in the requested "
        "language: a faithful translation or rendering of the existing label, in the "
        "conventions of that language (no articles, singular). If unsure, omit it.")
    SCHEMA = _obj({"labels": {"type": "array", "items": _obj({
        "resource": _STR, "lang": _STR, "label": _STR, "confidence": _NUM})}})

    def run(self, project: str, max_items: int = 50) -> "AgentRun":
        run = self.start(project)
        ctx = self.platform.projects[project]
        res = self.read(run, "quality.runChecks", checks=["listResourcesNoLexicalization"])
        todo = [{"resource": f["resource"], "missing": f["details"]["missingLang"],
                 "existing": self.platform.call(self.principal, project, "browse.resourceView",
                                                resource=f["resource"])["show"]}
                for f in res["findings"][:max_items]]
        if not todo:
            return self.finish(run, {"todo": 0})
        out = self.ask(run, "vocabulary.labels", json.dumps({"items": todo}), self.SCHEMA)
        if out is None:
            return self.finish(run)
        allowed = {r["resource"]: set(r["missing"]) for r in todo}
        skos = ctx.config.lexicalization.name in ("SKOS", "SKOSXL")
        for lab in out["labels"]:
            critic = []
            if lab["lang"] not in allowed.get(lab["resource"], set()):
                critic.append("language not missing / not a project language")
            if not lab["label"].strip() or lab["label"] != lab["label"].strip():
                critic.append("empty or untrimmed label")
            op, args = (("skos.setPrefLabel", {"concept": lab["resource"], "label": lab["label"],
                                               "lang": lab["lang"]}) if skos else
                        ("owl.setAnnotation", {"subject": lab["resource"],
                                               "property": "rdfs:label", "value": lab["label"],
                                               "lang": lab["lang"]}))
            src = next((t["existing"] for t in todo if t["resource"] == lab["resource"]), "")
            self.submit(run, Proposal(op, args, "fills listResourcesNoLexicalization",
                                      {"source_label": src, "basis": "rendering of the "
                                       "existing label", "finding": "listResourcesNoLexicalization"},
                                      float(lab.get("confidence", 0.5)), critic))
        return self.finish(run)


class AlignmentAgent(Agent):
    name, stage, roles = "alignment", "model", ("agent-mapper",)
    description = "Lexical matching, model adjudication of borderline cells, mapping proposals."
    system_prompt = (
        "You adjudicate candidate ontology correspondences. For each cell decide 'accept' or "
        "'reject' and the relation ('=', '<', '>'). Accept only when the two entities denote "
        "the same (or the stated sub/super) concept, judging from their labels and context.")
    SCHEMA = _obj({"decisions": {"type": "array", "items": _obj({
        "entity1": _STR, "entity2": _STR, "decision": {"type": "string",
                                                       "enum": ["accept", "reject"]},
        "relation": {"type": "string", "enum": ["=", "<", ">"]}, "reason": _STR})}})

    def run(self, project: str, target_project: str | None = None,
            target_data: str | None = None, auto_accept: float = 0.95,
            floor: float = 0.6) -> "AgentRun":
        run = self.start(project)
        ctx = self.platform.projects[project]
        res = self.read(run, "alignment.generate", target_project=target_project,
                        target_data=target_data, threshold=floor, alignment_id=run.id)
        cells = res["cells"]
        sure = [c for c in cells if c["measure"] >= auto_accept]
        borderline = [c for c in cells if c["measure"] < auto_accept]
        decisions = {(c["entity1"], c["entity2"]): ("accept", "=", "lexical identity")
                     for c in sure}
        if borderline:
            out = self.ask(run, "alignment.adjudicate", json.dumps({"cells": borderline}),
                           self.SCHEMA)
            for d in (out or {"decisions": []})["decisions"]:
                decisions[(d["entity1"], d["entity2"])] = (d["decision"], d["relation"],
                                                           d["reason"])
        al = ctx.alignments[run.id]
        for c in al.cells:
            dec = decisions.get((str(c.entity1), str(c.entity2)))
            if dec is None:
                continue
            c.relation = dec[1]
            self.read(run, "alignment.validateCell", entity1=str(c.entity1),
                      entity2=str(c.entity2), decision=dec[0], alignment_id=run.id)
        accepted = [c for c in al.cells if c.status == "accepted"]
        self.submit(run, Proposal("alignment.apply", {"alignment_id": run.id},
                                  f"{len(accepted)} accepted correspondence(s)",
                                  {"cells": [{"e1": str(c.entity1), "e2": str(c.entity2),
                                              "measure": c.measure, "relation": c.relation,
                                              "reason": decisions[(str(c.entity1),
                                                                   str(c.entity2))][2]}
                                             for c in accepted]},
                                  0.8, [] if accepted else ["nothing accepted"]))
        return self.finish(run, {"cells": len(cells), "accepted": len(accepted)})

# =========================================================================== #
# Validate
# =========================================================================== #


class QualityAgent(Agent):
    name, stage, roles = "quality", "validate", ("agent-ontology-copilot",)
    description = "Runs ICV + reasoner; proposes fixes and repairs of unsatisfiable classes."
    system_prompt = (
        "You repair OWL ontologies. For an unsatisfiable class you get its justifications "
        "(minimal axiom sets causing it). Choose the single axiom whose removal is most "
        "likely the modelling error (prefer the most specific, most recently added, least "
        "shared axiom) and explain why in one sentence.")
    SCHEMA = _obj({"repairs": {"type": "array", "items": _obj({
        "cls": _STR, "remove_kind": {"type": "string",
                                     "enum": ["SubClassOf", "EquivalentTo", "DisjointWith"]},
        "subject": _STR, "expression": _STR, "reason": _STR})}})

    def run(self, project: str, apply_fixes: bool = True) -> "AgentRun":
        run = self.start(project)
        ctx = self.platform.projects[project]
        cls_res = self.read(run, "reasoning.classify", materialise_inferred=False, staged=True)
        checks = self.read(run, "quality.runChecks")
        fixed = set()
        if apply_fixes:
            from ..quality.icv import REGISTRY
            for f in checks["findings"]:
                chk = REGISTRY.get(f["check"])
                if chk and chk.fix and f["check"] not in fixed:
                    fixed.add(f["check"])
                    self.submit(run, Proposal("quality.applyFix", {"check": f["check"]},
                                              f"fix for {chk.name}",
                                              {"finding_count": sum(
                                                  1 for x in checks["findings"]
                                                  if x["check"] == f["check"])}, 0.9))
        unsat = ctx.preview.unsatisfiable if ctx.preview else []
        if unsat:
            sfp = ctx.sfp(staged=True)
            items = []
            for u in unsat[:10]:
                ex = self.read(run, "reasoning.explain", kind="unsatisfiable", sub=str(u),
                               limit=3, staged=True)
                items.append({"cls": sfp.render(u), "iri": str(u),
                              "justifications": ex["justifications"]})
            out = self.ask(run, "quality.repair", json.dumps({"unsatisfiable": items}),
                           self.SCHEMA)
            for r in (out or {"repairs": []})["repairs"]:
                critic = []
                just = next((i for i in items if i["cls"] == r["cls"]), None)
                text = f"{r['subject']} {r['remove_kind'].replace('EquivalentTo', 'EquivalentTo')}"
                if just is None or not any(
                        r["expression"] in ax and r["subject"] in ax
                        for j in just["justifications"] for ax in j):
                    critic.append("proposed removal is not part of a justification")
                self.submit(run, Proposal("owl.removeAxiom", {
                    "subject": r["subject"], "kind": r["remove_kind"],
                    "expression": r["expression"]}, r["reason"],
                    {"justifications": just["justifications"] if just else [], "text": text},
                    0.6, critic))
        return self.finish(run, {"summary": checks["summary"], "consistent":
                                 cls_res["consistent"], "unsatisfiable": cls_res["unsatisfiable"]})

# =========================================================================== #
# Review
# =========================================================================== #


class StewardAgent(Agent):
    name, stage, roles = "steward", "review", ("agent-reader",)
    description = "Summarises each pending commit with risk and a recommendation. Never decides."
    system_prompt = (
        "You assist a human validator. For each pending change write a two-sentence "
        "summary of what it changes and why it was proposed, using the evidence given. "
        "Do not recommend; the recommendation is computed separately.")
    SCHEMA = _obj({"summaries": {"type": "array", "items": _obj({"commit": _STR,
                                                                 "summary": _STR})}})

    def run(self, project: str) -> "AgentRun":
        run = self.start(project)
        pending = self.read(run, "validation.pending")
        reviews = []
        for c in pending:
            ev = c.get("evidence") or {}
            risk, reasons = 0, []
            if c["removed"]:
                risk += 2
                reasons.append(f"removes {c['removed']} triple(s)")
            grounded = any(ev.get(k) for k in ("quote", "justifications", "cells",
                                               "finding_count", "source_label", "mapping",
                                               "signals"))
            if c["machine"] and not grounded:
                risk += 1
                reasons.append("agent proposal without grounding evidence")
            if ev.get("confidence", 1) < 0.6:
                risk += 1
                reasons.append(f"low confidence {ev.get('confidence')}")
            rec = "accept" if risk == 0 else ("review" if risk < 3 else "reject?")
            reviews.append({"commit": c["id"], "operation": c["operation"],
                            "principal": c["principal"], "risk": risk, "reasons": reasons,
                            "recommendation": rec, "evidence": ev})
        if reviews:
            out = self.ask(run, "steward.summaries", json.dumps({"pending": reviews}),
                           self.SCHEMA)
            text = {s["commit"]: s["summary"] for s in (out or {"summaries": []})["summaries"]}
            for r in reviews:
                r["summary"] = text.get(r["commit"], "")
        return self.finish(run, reviews)

# =========================================================================== #
# Populate
# =========================================================================== #


class KnowledgeGraphBuilder(Agent):
    name, stage, roles = "kg-builder", "populate", ("agent-kg-builder",)
    description = "Maps a table to the ontology, lifts it into the KG, proposes owl:sameAs."
    system_prompt = (
        "You map a CSV table to an OWL ontology. Choose the class each row instantiates, the "
        "column that identifies a row (for the IRI), the label column, and for other columns "
        "the property (from the given vocabulary) and kind ('data' with an xsd datatype, or "
        "'object' with the target class). Skip columns with no fitting property.")
    SCHEMA = _obj({"cls": _STR, "id_column": _STR, "label_column": _STR,
                   "columns": {"type": "array", "items": _obj({
                       "column": _STR, "property": _STR,
                       "kind": {"type": "string", "enum": ["data", "object"]},
                       "datatype": _STR, "target_class": _STR})}})

    def run(self, project: str, source_id: str, resolve: bool = True) -> "AgentRun":
        from ..platform import _iri
        run = self.start(project)
        ctx = self.platform.projects[project]
        src = ctx.sources[source_id]
        header = src["content"].splitlines()[0]
        sample = "\n".join(src["content"].splitlines()[:6])
        out = self.ask(run, "kg.mapping", json.dumps({"header": header, "sample": sample,
                                                      "vocabulary": _vocabulary(ctx)}),
                       self.SCHEMA)
        if out is None:
            return self.finish(run)
        kg_ns = ctx.config.default_namespace.rstrip("#/") + "/kg/"
        mapping = {
            "cls": str(_iri(ctx, out["cls"])),
            "iri_template": f"{kg_ns}{_camel(out['cls'], upper=False)}/{{{out['id_column']}}}",
            "label_column": out["label_column"] or None,
            "columns": [{"column": c["column"], "property": str(_iri(ctx, c["property"])),
                         "kind": c["kind"],
                         "datatype": ("http://www.w3.org/2001/XMLSchema#" + c["datatype"][4:]
                                      if c["datatype"].startswith("xsd:") else
                                      (c["datatype"] or None)),
                         "target_class": str(_iri(ctx, c["target_class"]))
                         if c["target_class"] else None} for c in out["columns"]]}
        from ..kg.lifting import ColumnMap, TableMapping
        tm = TableMapping(mapping["cls"], mapping["iri_template"],
                          [ColumnMap(**c) for c in mapping["columns"]], mapping["label_column"])
        critic = tm.validate([h.strip() for h in header.split(",")], ctx.ontology(staged=True))
        self.submit(run, Proposal("kg.liftTable", {"source_id": source_id, "mapping": mapping},
                                  "table mapping proposed from header/sample",
                                  {"source": source_id, "sha256": src["sha256"],
                                   "mapping": mapping}, 0.7, critic))
        if resolve:
            for d in self.read(run, "kg.resolveEntities"):
                self.submit(run, Proposal("kg.assertSameAs", {"a": d["a"], "b": d["b"]},
                                          "duplicate candidates", {"score": d["score"],
                                                                   "signals": d["evidence"]},
                                          d["score"]))
        return self.finish(run, {"mapping": mapping})

# =========================================================================== #
# Consume
# =========================================================================== #


class AssistantAgent(Agent):
    name, stage, roles = "assistant", "consume", ("agent-reader",)
    description = "Answers questions with SPARQL over ontology+KG; cites the rows it used."
    system_prompt = (
        "You answer questions about a knowledge graph by writing ONE SPARQL SELECT query "
        "(prefix ':' is the project namespace; rdf/rdfs/owl/skos predefined). Use only the "
        "vocabulary given. Return the query and the answer template; the answer is filled "
        "from the query results only.")
    SCHEMA = _obj({"sparql": _STR, "answer_template": _STR})

    def run(self, project: str, question: str) -> "AgentRun":
        run = self.start(project)
        ctx = self.platform.projects[project]
        out = self.ask(run, "assistant.sparql", json.dumps(
            {"question": question, "vocabulary": _vocabulary(ctx),
             "namespace": ctx.config.default_namespace}), self.SCHEMA)
        if out is None:
            return self.finish(run, {"answer": None, "reason": "model unavailable"})
        ns = ctx.config.default_namespace
        q = out["sparql"]
        if not q.lstrip().upper().startswith("PREFIX"):
            q = (f"PREFIX : <{ns}>\nPREFIX rdf: <{RDF}>\nPREFIX rdfs: <{RDFS}>\n"
                 f"PREFIX owl: <{OWL}>\n") + q
        try:
            rows = self.read(run, "sparql.query", query=q, include_inferred=True)
        except Exception as exc:  # noqa: BLE001
            return self.finish(run, {"answer": None, "sparql": q, "error": str(exc)})
        values = sorted({str(v) for r in rows for v in r.values() if v})
        sfp = ShortFormProvider(ctx.ontology() + ctx.kg())   # KG labels for instances
        shown = [sfp.render(URIRef(v)) if v.startswith(("http", "urn")) else v for v in values]
        answer = out["answer_template"].replace("{answer}", ", ".join(shown) or "none")
        return self.finish(run, {"answer": answer, "sparql": q, "rows": rows,
                                 "grounded": True, "cited_values": values})


ALL_AGENTS = (RequirementsAgent, ExtractionAgent, ModelingCopilot, VocabularyAgent,
              AlignmentAgent, QualityAgent, StewardAgent, KnowledgeGraphBuilder, AssistantAgent)
