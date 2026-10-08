"""FastAPI application for the guided ontology review.

    python -m validation_agent ui [--host 127.0.0.1] [--port 8765]

Sessions live in memory (one ``ValidationWorkspace`` + ``ReviewRecord`` + assistant per
session). That is enough for a single reviewer on a workstation; the multi-tenant run
store is part of the R1 productisation track.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import ENGINE_VERSION
from ..agent.assistant import ReviewAssistant
from ..agent.gateway import LlmGateway
from ..engine import pipeline, report
from ..engine.policy import available_policies, load_policy
from ..engine.profile import DECLARABLE_LEVELS
from ..review import (CHECKLIST_ANSWERS, EXPERT_CHECKLIST, FINAL_DECISIONS, MARKS, STEP_BY_ID,
                      STEPS, ReviewRecord, assess, now, overview)
from ..tools.belt import ToolBelt
from ..workspace import ValidationWorkspace

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
SAMPLES_DIR = HERE.parent / "samples"
SAMPLES = {
    "rail": {"file": "rail.ttl", "shapes": "rail_shapes.ttl", "declared": "formal-ontology",
             "title": "Rail rolling stock (defects planted in every layer)"},
    "clean_rail": {"file": "clean_rail.ttl", "shapes": None, "declared": "formal-ontology",
                   "title": "Rail rolling stock, defects fixed"},
    "thesaurus": {"file": "transport_thesaurus.ttl", "shapes": None, "declared": "thesaurus",
                  "title": "Transport thesaurus (SKOS, broader cycle)"},
}
MAX_SESSIONS = 50


@dataclass
class ReviewSession:
    id: str
    ws: ValidationWorkspace
    record: ReviewRecord
    assistant: ReviewAssistant
    created: float = field(default_factory=time.time)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def summary(self) -> dict:
        ws = self.ws
        return {"session_id": self.id, "run_id": ws.run_id, "source": ws.load.source,
                "verdict": ws.decision.verdict, "policy": ws.policy.id,
                "declared_level": ws.declared_level,
                "measured_level": ws.profile.spectrum_level if ws.profile else None,
                "findings": len(ws.findings), "millis": ws.millis, "versions": ws.versions,
                "steps": overview(ws, self.record), "assistant": self.assistant.status(),
                "final": self.record.final}


class MarkIn(BaseModel):
    finding_id: str
    mark: str | None = None
    comment: str = Field("", max_length=2000)


class ChecklistIn(BaseModel):
    id: str
    answer: str
    comment: str = Field("", max_length=2000)


class SignoffIn(BaseModel):
    step: str
    status: str = "done"
    note: str = Field("", max_length=2000)


class FinalIn(BaseModel):
    reviewer: str = Field(..., min_length=1, max_length=200)
    decision: str
    note: str = Field("", max_length=4000)


class ChatIn(BaseModel):
    step: str
    message: str = Field(..., min_length=1, max_length=4000)
    finding_id: str | None = None


def create_app() -> FastAPI:
    app = FastAPI(title="OVA review", version=ENGINE_VERSION)
    sessions: dict[str, ReviewSession] = {}
    app.state.sessions = sessions

    def get(sid: str) -> ReviewSession:
        s = sessions.get(sid)
        if s is None:
            raise HTTPException(404, "unknown review session (the server may have restarted)")
        return s

    def start(ws: ValidationWorkspace) -> ReviewSession:
        pipeline.run(ws)
        record = ReviewRecord()
        s = ReviewSession(uuid.uuid4().hex[:12], ws, record,
                          ReviewAssistant(ws, record, LlmGateway.from_env()))
        if len(sessions) >= MAX_SESSIONS:
            oldest = min(sessions.values(), key=lambda x: x.created)
            sessions.pop(oldest.id, None)
        sessions[s.id] = s
        return s

    # ------------------------------------------------------------------ meta
    @app.get("/api/meta")
    def meta():
        gw = LlmGateway.from_env()
        return {"engine": ENGINE_VERSION, "steps": STEPS, "policies": available_policies(),
                "levels": list(DECLARABLE_LEVELS),
                "samples": [{"id": k, **v} for k, v in SAMPLES.items()],
                "checklist": EXPERT_CHECKLIST, "marks": MARKS, "answers": CHECKLIST_ANSWERS,
                "final_decisions": FINAL_DECISIONS, "assistant": gw.status()}

    # ------------------------------------------------------------------ sessions
    @app.post("/api/sessions")
    async def create_session(file: UploadFile | None = File(None),
                             shapes: UploadFile | None = File(None),
                             sample: str | None = Form(None),
                             declared_level: str | None = Form(None),
                             policy: str = Form("registry-default-v1")):
        if policy not in available_policies():
            raise HTTPException(400, f"unknown policy {policy}")
        level = declared_level or None
        if level is not None and level not in DECLARABLE_LEVELS:
            raise HTTPException(400, f"unknown level {level}")
        if sample:
            spec = SAMPLES.get(sample)
            if spec is None:
                raise HTTPException(400, f"unknown sample {sample}")
            ws = ValidationWorkspace.from_path(
                SAMPLES_DIR / spec["file"], declared_level=level or spec["declared"], policy=policy,
                shapes_path=SAMPLES_DIR / spec["shapes"] if spec["shapes"] else None)
        elif file is not None:
            data = await file.read()
            if not data:
                raise HTTPException(400, "the uploaded file is empty")
            shapes_data = await shapes.read() if shapes is not None else None
            ws = ValidationWorkspace.from_bytes(
                data, file.filename or "submission", declared_level=level, policy=policy,
                shapes=shapes_data or None, shapes_name=(shapes.filename if shapes else "shapes.ttl"))
        else:
            raise HTTPException(400, "upload an ontology file or choose a sample")
        return start(ws).summary()

    @app.get("/api/sessions/{sid}")
    def session(sid: str):
        return get(sid).summary()

    @app.post("/api/sessions/{sid}/rerun")
    def rerun(sid: str, policy: str = Form(...)):
        s = get(sid)
        if policy not in available_policies():
            raise HTTPException(400, f"unknown policy {policy}")
        ws = ValidationWorkspace(load=s.ws.load, policy=load_policy(policy),
                                 declared_level=s.ws.declared_level,
                                 shapes_load=s.ws.shapes_load, tenant=s.ws.tenant)
        return start(ws).summary()

    @app.get("/api/sessions/{sid}/steps/{step}")
    def step(sid: str, step: str):
        s = get(sid)
        if step not in STEP_BY_ID:
            raise HTTPException(404, f"unknown step {step}")
        with s.lock:
            return assess(s.ws, step, s.record)

    # ------------------------------------------------------------------ review input
    @app.post("/api/sessions/{sid}/marks")
    def mark(sid: str, body: MarkIn):
        s = get(sid)
        if s.ws.finding(body.finding_id) is None:
            raise HTTPException(404, f"no finding {body.finding_id}")
        if body.mark is None:
            s.record.marks.pop(body.finding_id, None)
        elif body.mark not in MARKS:
            raise HTTPException(400, f"mark must be one of {MARKS}")
        else:
            s.record.marks[body.finding_id] = {"mark": body.mark, "comment": body.comment, "at": now()}
        return {"ok": True, "steps": overview(s.ws, s.record)}

    @app.post("/api/sessions/{sid}/checklist")
    def checklist(sid: str, body: ChecklistIn):
        s = get(sid)
        if body.id not in {q["id"] for q in EXPERT_CHECKLIST}:
            raise HTTPException(404, f"no checklist item {body.id}")
        if body.answer not in CHECKLIST_ANSWERS:
            raise HTTPException(400, f"answer must be one of {CHECKLIST_ANSWERS}")
        s.record.checklist[body.id] = {"answer": body.answer, "comment": body.comment, "at": now()}
        return {"ok": True, "steps": overview(s.ws, s.record)}

    @app.post("/api/sessions/{sid}/signoff")
    def signoff(sid: str, body: SignoffIn):
        s = get(sid)
        if body.step not in STEP_BY_ID:
            raise HTTPException(404, f"unknown step {body.step}")
        if body.status not in ("done", "needs-work"):
            raise HTTPException(400, "status must be done or needs-work")
        s.record.signoffs[body.step] = {"status": body.status, "note": body.note, "at": now()}
        return {"ok": True, "steps": overview(s.ws, s.record)}

    @app.post("/api/sessions/{sid}/final")
    def final(sid: str, body: FinalIn):
        s = get(sid)
        if body.decision not in FINAL_DECISIONS:
            raise HTTPException(400, f"decision must be one of {FINAL_DECISIONS}")
        s.record.final = {"reviewer": body.reviewer, "decision": body.decision,
                          "note": body.note, "verdict": s.ws.decision.verdict, "at": now()}
        return {"ok": True, "final": s.record.final}

    # ------------------------------------------------------------------ assistant
    @app.post("/api/sessions/{sid}/chat")
    def chat(sid: str, body: ChatIn):
        s = get(sid)
        if body.step not in STEP_BY_ID:
            raise HTTPException(404, f"unknown step {body.step}")
        with s.lock:
            reply = s.assistant.ask(body.step, body.message, body.finding_id)
        return {**reply.to_dict(), "assistant": s.assistant.status()}

    @app.get("/api/sessions/{sid}/chat/{step}")
    def transcript(sid: str, step: str):
        s = get(sid)
        return {"messages": s.assistant.transcripts.get(step, []),
                "assistant": s.assistant.status()}

    @app.get("/api/sessions/{sid}/entity")
    def entity(sid: str, iri: str):
        s = get(sid)
        with s.lock:
            result = ToolBelt(s.ws, actor="ui").call("describe_entity", {"iri": iri})
        if isinstance(result, str):
            raise HTTPException(404, result)
        return result

    # ------------------------------------------------------------------ reports
    @app.get("/api/sessions/{sid}/report.json")
    def report_json(sid: str):
        s = get(sid)
        body = report.to_json(s.ws, review=s.record.to_dict())
        return JSONResponse(body, headers={
            "Content-Disposition": f'attachment; filename="{s.ws.run_id}.json"'})

    @app.get("/api/sessions/{sid}/report.md")
    def report_md(sid: str):
        s = get(sid)
        return PlainTextResponse(report.to_markdown(s.ws, review=s.record.to_dict()),
                                 media_type="text/markdown; charset=utf-8", headers={
                                     "Content-Disposition": f'attachment; filename="{s.ws.run_id}.md"'})

    # ------------------------------------------------------------------ front end
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    return app


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn
    uvicorn.run(create_app(), host=host, port=port, log_level="info")
