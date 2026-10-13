from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .classifier import Classifier, OllamaError
from .db import Database, utcnow
from .models import Health, RequestRecord, StatusUpdate, SubmitRequest
from .taxonomy import CATEGORY_LABELS, STATUS_LABELS, URGENCY_LABELS

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "data/opentriage.db"))
if not DATABASE_PATH.is_absolute():
    DATABASE_PATH = ROOT / DATABASE_PATH

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
ORG_EMAIL_DOMAIN = os.getenv("ORG_EMAIL_DOMAIN", "").strip().lower() or None
ORG_TEAMS = [
    team.strip()
    for team in os.getenv(
        "ORG_TEAMS", "Engineering,Product,Operations,Finance,People,Marketing"
    ).split(",")
    if team.strip()
]

db = Database(DATABASE_PATH)
classifier = Classifier(OLLAMA_HOST, OLLAMA_MODEL)

app = FastAPI(title="OpenTriage", version="1.0.0")
static_dir = ROOT / "frontend"
app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")


@app.get("/api/health", response_model=Health)
def health() -> Health:
    probe = classifier.health()
    return Health(
        ok=bool(probe.get("ok")),
        ollama=bool(probe.get("ok") and probe.get("has_model")),
        model=OLLAMA_MODEL,
        available_models=probe.get("models", []),
        org_email_domain=ORG_EMAIL_DOMAIN,
    )


@app.get("/api/meta")
def meta() -> dict:
    return {
        "teams": ORG_TEAMS,
        "org_email_domain": ORG_EMAIL_DOMAIN,
        "model": OLLAMA_MODEL,
        "categories": CATEGORY_LABELS,
        "urgencies": URGENCY_LABELS,
        "statuses": STATUS_LABELS,
    }


@app.get("/api/stats")
def stats() -> dict:
    return db.stats()


@app.get("/api/requests", response_model=list[RequestRecord])
def list_requests(
    status: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    urgency: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
) -> list[dict]:
    return db.list_requests(status=status, category=category, urgency=urgency, q=q)


@app.get("/api/requests/{request_id}", response_model=RequestRecord)
def get_request(request_id: int) -> dict:
    try:
        return db.get_request(request_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc


@app.post("/api/requests", response_model=RequestRecord)
def submit_request(payload: SubmitRequest) -> dict:
    _assert_org_email(str(payload.requester_email))
    record = db.insert_request(payload.model_dump(mode="json"))
    return _classify_and_store(record["id"])


@app.post("/api/requests/{request_id}/reclassify", response_model=RequestRecord)
def reclassify(request_id: int) -> dict:
    try:
        db.get_request(request_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc
    return _classify_and_store(request_id)


@app.patch("/api/requests/{request_id}", response_model=RequestRecord)
def update_status(request_id: int, payload: StatusUpdate) -> dict:
    try:
        db.get_request(request_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc
    fields = {"status": payload.status}
    if payload.note is not None:
        fields["status_note"] = payload.note.strip()
    return db.update_request(request_id, fields)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/inbox")
def inbox() -> FileResponse:
    return FileResponse(static_dir / "index.html")


def _assert_org_email(email: str) -> None:
    if not ORG_EMAIL_DOMAIN:
        return
    domain = email.rsplit("@", 1)[-1].lower()
    if domain != ORG_EMAIL_DOMAIN:
        raise HTTPException(
            status_code=400,
            detail=f"Use your {ORG_EMAIL_DOMAIN} email to submit a request.",
        )


def _classify_and_store(request_id: int) -> dict:
    record = db.get_request(request_id)
    try:
        result = classifier.classify(
            title=record["title"],
            details=record["details"],
            impact=record["impact"],
            team=record["team"],
        )
        return db.update_request(
            request_id,
            {
                **result.model_dump(),
                "classification_error": None,
                "model": classifier.model,
                "classified_at": utcnow(),
            },
        )
    except (OllamaError, ValidationError) as exc:
        return db.update_request(
            request_id,
            {
                "classification_error": str(exc),
                "model": classifier.model,
            },
        )
