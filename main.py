"""Alpha SRE — webhook entry point and execution API.

This file handles two concerns:

1. Intake — receives Sentry webhooks, validates them, and kicks off analysis
   as a background task so Sentry gets its 200 immediately.

2. Results API — exposes read endpoints the frontend polls to get results.

Flow after a webhook arrives:
    POST /webhooks/sentry
        → validate signature
        → parse payload
        → create pending ExecutionRecord in store
        → start background task
        → return 200 + execution_id to Sentry immediately

    background task:
        → fetch Sentry enrichment
        → fetch GitHub enrichment (stub)
        → run AlphaRuntime.execute()
        → update record to status="complete" (or "failed")

    frontend polls:
        GET /executions/latest  or  GET /executions/{id}
        → returns ExecutionRecord with status + hypotheses + signals

Run locally:
    uv run uvicorn main:app --reload
"""

import asyncio
import json
import logging
import logging.handlers
import os
import pathlib
import uuid
from datetime import datetime, timezone
from typing import Literal

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from core.runtime import AlphaRuntime
from llm.openrouter import OpenRouterClient
from schemas.incident import IncidentInput
from sre.agents.commit_agent import CommitAgent
from sre.agents.config_agent import ConfigAgent
from sre.agents.log_agent import LogAgent
from sre.agents.metrics_agent import MetricsAgent
from sre.integrations.sentry import (
    SentryWebhookPayload,
    fetch_enrichment,
    parse_webhook_payload,
    verify_sentry_signature,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_FILE = pathlib.Path(__file__).parent / "alpha_sre.log"
LOG_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_file_handler = logging.handlers.RotatingFileHandler(
    LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))

_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)
_root_logger.addHandler(_file_handler)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------

app = FastAPI(title="Alpha SRE")

# Allow the frontend to call these endpoints from a different origin.
# ALLOWED_ORIGINS env var overrides the default for production deployments.
_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Runtime setup
# ---------------------------------------------------------------------------

runtime = AlphaRuntime()
runtime.register(LogAgent(llm=OpenRouterClient("anthropic/claude-sonnet-4-6")))
runtime.register(MetricsAgent(llm=OpenRouterClient("google/gemini-2.0-flash-001")))
runtime.register(CommitAgent(llm=OpenRouterClient("anthropic/claude-sonnet-4-6")))
runtime.register(ConfigAgent(llm=OpenRouterClient("google/gemini-2.0-flash-001")))

# ---------------------------------------------------------------------------
# Execution store
# ---------------------------------------------------------------------------

class ExecutionRecord(BaseModel):
    """A single analysis run — what the frontend polls for.

    status lifecycle:
        "pending"  → created when webhook arrives, before analysis starts
        "complete" → analysis finished, hypotheses and signals populated
        "failed"   → analysis raised an unhandled exception, error is set
    """
    execution_id: str
    status: Literal["pending", "complete", "failed"]
    sentry_issue_id: str | None = None
    deployment_id: str | None = None
    requires_human_review: bool | None = None
    hypotheses: list[dict] = []
    signals: list[dict] = []
    error: str | None = None
    created_at: str = ""


# In-memory store: execution_id → ExecutionRecord.
# Lost on server restart — swap for SQLite or Redis when persistence matters.
_store: dict[str, ExecutionRecord] = {}
_latest_id: str | None = None


def _save(record: ExecutionRecord) -> None:
    """Write a record to the store and update the latest pointer."""
    global _latest_id
    _store[record.execution_id] = record
    _latest_id = record.execution_id


# ---------------------------------------------------------------------------
# Background analysis task
# ---------------------------------------------------------------------------

async def _run_analysis(execution_id: str, payload: SentryWebhookPayload) -> None:
    """Fetch enrichment, run the pipeline, and update the store.

    Runs after the webhook handler has already returned 200 to Sentry.
    All failures are caught and recorded as status="failed" so the frontend
    always gets a terminal state rather than an entry stuck on "pending".

    Args:
        execution_id: Pre-generated ID that was returned to Sentry and the
            frontend. Used as the store key throughout.
        payload: Parsed Sentry webhook payload with issue_id and project info.
    """
    try:
        sentry_data = await fetch_enrichment(payload)
        github_data = _stub_github_enrichment()

        incident = IncidentInput(
            deployment_id=sentry_data["deployment_id"],
            logs=sentry_data["logs"],
            metrics=sentry_data["metrics"],
            recent_commits=github_data["recent_commits"],
            config_snapshot=github_data["config_snapshot"],
        )

        result = await runtime.execute(incident)

        _save(_store[execution_id].model_copy(update={
            "status": "complete",
            "deployment_id": result.execution_id,
            "requires_human_review": result.requires_human_review,
            "hypotheses": [h.model_dump() for h in result.ranked_hypotheses],
            "signals": [s.model_dump() for s in result.signals_used],
        }))

        logger.info(
            "Analysis complete for issue %s. %d hypotheses. Human review: %s.",
            payload.issue_id,
            len(result.ranked_hypotheses),
            result.requires_human_review,
        )

    except Exception as exc:
        logger.error("Analysis failed for execution %s: %s", execution_id, exc)
        _save(_store[execution_id].model_copy(update={
            "status": "failed",
            "error": str(exc),
        }))


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def dashboard():
    return FileResponse("frontend/index.html")


@app.post("/api/analyze")
async def analyze_incident(request: Request):
    """Run the pipeline and stream agent events as NDJSON."""
    body = await request.json()
    try:
        incident = IncidentInput(**body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    eid = str(uuid.uuid4())

    async def stream():
        eq: asyncio.Queue = asyncio.Queue()
        _save(ExecutionRecord(
            execution_id=eid, status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
        ))

        async def run():
            try:
                result = await runtime.execute(incident, event_queue=eq)
                _save(_store[eid].model_copy(update={
                    "status": "complete",
                    "hypotheses": [h.model_dump() for h in result.ranked_hypotheses],
                    "signals": [s.model_dump() for s in result.signals_used],
                    "requires_human_review": result.requires_human_review,
                }))
            except Exception as exc:
                _save(_store[eid].model_copy(update={"status": "failed", "error": str(exc)}))
            finally:
                await eq.put(None)

        task = asyncio.create_task(run())
        while True:
            event = await eq.get()
            if event is None:
                break
            yield json.dumps({"type": "agent_event", **event.model_dump()}) + "\n"
        await task
        yield json.dumps({"type": "result", **_store[eid].model_dump()}) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# Sentry webhook handler
# ---------------------------------------------------------------------------

@app.post("/webhooks/sentry")
async def sentry_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    sentry_hook_signature: str = Header(default=None),
):
    """Receive a Sentry webhook, create a pending execution, return immediately.

    The webhook handler no longer runs the analysis pipeline directly.
    Instead it validates the request, creates a pending record in the store,
    and hands the actual work off to a background task. This means Sentry
    gets its 200 in milliseconds rather than waiting for LLM calls to finish.

    The execution_id returned here is what the frontend uses to poll
    GET /executions/{id} for results.
    """
    body = await request.body()

    # Signature verification
    client_secret = os.environ.get("SENTRY_CLIENT_SECRET", "")
    if client_secret and sentry_hook_signature:
        if not verify_sentry_signature(body, sentry_hook_signature, client_secret):
            logger.warning("Rejected webhook: invalid Sentry signature.")
            raise HTTPException(status_code=401, detail="Invalid signature.")
    else:
        logger.warning("SENTRY_CLIENT_SECRET not set — skipping signature check.")

    # Parse payload
    try:
        raw = json.loads(body)
        payload = parse_webhook_payload(raw)
    except (KeyError, ValueError) as exc:
        logger.error("Failed to parse Sentry webhook payload: %s", exc)
        raise HTTPException(status_code=400, detail=f"Malformed payload: {exc}")

    if payload.action != "created":
        logger.info("Ignoring webhook action '%s'.", payload.action)
        return {"status": "ignored", "reason": f"action={payload.action}"}

    # Create a pending record so the frontend has something to poll immediately
    execution_id = str(uuid.uuid4())
    _save(ExecutionRecord(
        execution_id=execution_id,
        status="pending",
        sentry_issue_id=payload.issue_id,
        created_at=datetime.now(timezone.utc).isoformat(),
    ))

    logger.info(
        "Accepted Sentry issue %s → execution %s (pending).",
        payload.issue_id,
        execution_id,
    )

    # Hand off to background task — this runs after the 200 is sent to Sentry
    background_tasks.add_task(_run_analysis, execution_id, payload)

    return {"execution_id": execution_id, "status": "pending"}


# ---------------------------------------------------------------------------
# Results API — frontend polling endpoints
# ---------------------------------------------------------------------------

@app.get("/executions/latest", response_model=ExecutionRecord)
def get_latest_execution():
    """Return the most recent execution record.

    The frontend polls this endpoint after a Sentry alert fires. The status
    field tells the frontend what to render:
        "pending"  → show a loading state
        "complete" → render hypotheses and signals
        "failed"   → show an error message

    Returns 404 if no executions have run yet.
    """
    if _latest_id is None or _latest_id not in _store:
        raise HTTPException(status_code=404, detail="No executions yet.")
    return _store[_latest_id]


@app.get("/executions/{execution_id}", response_model=ExecutionRecord)
def get_execution(execution_id: str):
    """Return a specific execution record by ID.

    Use this when the frontend received an execution_id from the webhook
    response (via your own notification layer) and wants to fetch that
    specific result rather than the latest.

    Returns 404 if the execution_id is not found.
    """
    if execution_id not in _store:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found.")
    return _store[execution_id]


# ---------------------------------------------------------------------------
# GitHub enrichment stub
# ---------------------------------------------------------------------------

def _stub_github_enrichment() -> dict:
    """Return fixture commit and config data.

    Phase 4 replaces this with a real GitHubClient.
    """
    fixture_path = pathlib.Path(__file__).parent / "fixtures" / "incident_b.json"

    if fixture_path.exists():
        with open(fixture_path) as f:
            data = json.load(f)
        return {
            "recent_commits": data["recent_commits"],
            "config_snapshot": data["config_snapshot"],
        }

    return {
        "recent_commits": [
            {
                "sha": "a1b2c3d",
                "message": "Remove cache from user profile endpoint",
                "diff_summary": "Removed @cache decorator. Added unindexed JOIN query.",
            },
        ],
        "config_snapshot": {"MAX_DB_CONNECTIONS": 5, "CACHE_TTL_SECONDS": 0},
    }


# ---------------------------------------------------------------------------
# Static file serving — must be AFTER all route definitions
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
app.mount("/fixtures", StaticFiles(directory="fixtures"), name="fixtures")
