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
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

load_dotenv()

from core.runtime import AlphaRuntime
from display.live import LiveDisplay
from llm.cerebras import CerebrasClient
from llm.openrouter import OpenRouterClient
from schemas.incident import IncidentInput
from sre.agents.commit_agent import CommitAgent
from sre.agents.config_agent import ConfigAgent
from sre.agents.log_agent import LogAgent
from sre.agents.metrics_agent import MetricsAgent
from sre.agents.synthesis_agent import SynthesisAgent
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
console = Console()
_cli_display_lock = asyncio.Lock()

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

def _wire_demo_agents() -> None:
    """Register default agents for demo use if provider keys are present.

    Controlled by env:
        ALPHA_AUTO_REGISTER_AGENTS=true|false  (default: true)
        ALPHA_LLM_PROVIDER=openrouter|cerebras (default: openrouter)
    """
    if os.environ.get("ALPHA_AUTO_REGISTER_AGENTS", "true").lower() != "true":
        logger.info("Skipping agent auto-registration (ALPHA_AUTO_REGISTER_AGENTS=false).")
        return

    provider = os.environ.get("ALPHA_LLM_PROVIDER", "openrouter").strip().lower()

    if provider == "cerebras":
        client_cls = CerebrasClient
        default_model = os.environ.get("ALPHA_MODEL_DEFAULT", "llama-3.3-70b")
        model_log = os.environ.get("ALPHA_MODEL_LOG", default_model)
        model_metrics = os.environ.get("ALPHA_MODEL_METRICS", default_model)
        model_commit = os.environ.get("ALPHA_MODEL_COMMIT", default_model)
        model_config = os.environ.get("ALPHA_MODEL_CONFIG", default_model)
        model_synthesis = os.environ.get("ALPHA_MODEL_SYNTHESIS", default_model)
    else:
        client_cls = OpenRouterClient
        model_log = os.environ.get("ALPHA_MODEL_LOG", "anthropic/claude-sonnet-4-6")
        model_metrics = os.environ.get("ALPHA_MODEL_METRICS", "google/gemini-2.0-flash-001")
        model_commit = os.environ.get("ALPHA_MODEL_COMMIT", "anthropic/claude-sonnet-4-6")
        model_config = os.environ.get("ALPHA_MODEL_CONFIG", "google/gemini-2.0-flash-001")
        model_synthesis = os.environ.get("ALPHA_MODEL_SYNTHESIS", "anthropic/claude-sonnet-4-6")

    try:
        runtime.register(LogAgent(llm=client_cls(model_log)))
        runtime.register(MetricsAgent(llm=client_cls(model_metrics)))
        runtime.register(CommitAgent(llm=client_cls(model_commit)))
        runtime.register(ConfigAgent(llm=client_cls(model_config)))
        runtime.set_synthesizer(SynthesisAgent(llm=client_cls(model_synthesis)))
        logger.info(
            "Auto-registered 4 agents + synthesis using provider='%s'.",
            provider,
        )
    except KeyError as exc:
        logger.warning(
            "Agent auto-registration skipped: missing API key env var %s. "
            "Set OPENROUTER_API_KEY or CEREBRAS_API_KEY.",
            exc,
        )


_wire_demo_agents()


def _cli_webhook_mode_enabled() -> bool:
    return os.environ.get("ALPHA_CLI_WEBHOOK_MODE", "false").lower() == "true"


def _print_cli_summary(issue_id: str, result) -> None:
    """Print final execution summary for webhook-driven CLI demo mode."""
    console.rule(f"[bold]Alpha SRE · Issue {issue_id}[/bold]")

    if not result.ranked_hypotheses:
        console.print("[yellow]No hypotheses produced.[/yellow]")
    else:
        table = Table(title="Ranked Hypotheses", show_lines=True, border_style="bright_black")
        table.add_column("#", style="dim", width=3, justify="right")
        table.add_column("Label", style="bold", min_width=28)
        table.add_column("Confidence", width=12, justify="center")
        table.add_column("Severity", width=10, justify="center")
        table.add_column("Agents", style="dim", min_width=20)

        for i, h in enumerate(result.ranked_hypotheses, 1):
            conf_color = "green" if h.confidence >= 0.8 else "yellow" if h.confidence >= 0.6 else "red"
            sev_color = "red" if h.severity == "high" else "yellow" if h.severity == "medium" else "dim"
            table.add_row(
                str(i),
                h.label,
                f"[{conf_color}]{h.confidence:.0%}[/{conf_color}]",
                f"[{sev_color}]{h.severity}[/{sev_color}]",
                h.contributing_agent,
            )

        console.print(table)

    if result.synthesis:
        synthesis = result.synthesis
        synth_text = (
            f"[bold]Key finding:[/bold] {synthesis.key_finding}\n\n"
            f"[bold]Summary:[/bold] {synthesis.summary}\n\n"
            f"[bold]Confidence in ranking:[/bold] {synthesis.confidence_in_ranking:.0%}"
        )
        console.print(Panel(synth_text, title="Synthesis", border_style="cyan"))

    review = (
        "[bold red]Requires human review[/bold red]"
        if result.requires_human_review
        else "[bold green]Confidence sufficient for automated action[/bold green]"
    )
    console.print(review)
    console.print(f"[dim]execution: {result.execution_id}[/dim]\n")

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
    synthesis: dict | None = None
    error: str | None = None
    created_at: str = ""


# In-memory store: execution_id → ExecutionRecord.
# Lost on server restart — swap for SQLite or Redis when persistence matters.
_store: dict[str, ExecutionRecord] = {}
_latest_id: str | None = None
_issue_latest_execution: dict[str, str] = {}
_issue_last_accepted_at: dict[str, datetime] = {}
_webhook_lock = asyncio.Lock()

WEBHOOK_DEDUP_SECONDS = int(os.environ.get("ALPHA_WEBHOOK_DEDUP_SECONDS", "60"))


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

        if _cli_webhook_mode_enabled():
            async with _cli_display_lock:
                agent_names = [a.name for a in runtime._registry.get_all()]
                if agent_names:
                    event_queue: asyncio.Queue = asyncio.Queue()
                    display = LiveDisplay(agent_names)
                    with display.make_live() as live:
                        pipeline = asyncio.create_task(runtime.execute(incident, event_queue=event_queue))
                        consumer = asyncio.create_task(display.consume(event_queue, live))
                        result = await pipeline
                        await event_queue.put(None)
                        await consumer
                else:
                    result = await runtime.execute(incident)

                _print_cli_summary(payload.issue_id, result)
        else:
            result = await runtime.execute(incident)

        _save(_store[execution_id].model_copy(update={
            "status": "complete",
            "deployment_id": result.execution_id,
            "requires_human_review": result.requires_human_review,
            "hypotheses": [h.model_dump() for h in result.ranked_hypotheses],
            "signals": [s.model_dump() for s in result.signals_used],
            "synthesis": result.synthesis.model_dump() if result.synthesis else None,
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

    # Dedupe bursts: avoid re-running the full pipeline repeatedly for the
    # same issue while one execution is in flight or within a short cooldown.
    now = datetime.now(timezone.utc)
    async with _webhook_lock:
        latest_for_issue = _issue_latest_execution.get(payload.issue_id)
        if latest_for_issue and latest_for_issue in _store:
            existing = _store[latest_for_issue]
            if existing.status == "pending":
                logger.info(
                    "Deduped Sentry issue %s: execution %s still pending.",
                    payload.issue_id,
                    latest_for_issue,
                )
                return {
                    "execution_id": latest_for_issue,
                    "status": "deduped",
                    "reason": "pending_execution_exists",
                }

        last_seen = _issue_last_accepted_at.get(payload.issue_id)
        if (
            last_seen is not None
            and (now - last_seen).total_seconds() < WEBHOOK_DEDUP_SECONDS
        ):
            logger.info(
                "Deduped Sentry issue %s: within %ds cooldown window.",
                payload.issue_id,
                WEBHOOK_DEDUP_SECONDS,
            )
            return {
                "execution_id": latest_for_issue,
                "status": "deduped",
                "reason": f"cooldown_{WEBHOOK_DEDUP_SECONDS}s",
            }

        # Create a pending record so the frontend has something to poll immediately
        execution_id = str(uuid.uuid4())
        _save(ExecutionRecord(
            execution_id=execution_id,
            status="pending",
            sentry_issue_id=payload.issue_id,
            created_at=now.isoformat(),
        ))
        _issue_latest_execution[payload.issue_id] = execution_id
        _issue_last_accepted_at[payload.issue_id] = now

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
