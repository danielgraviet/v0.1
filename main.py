"""Alpha SRE — webhook entry point.

This is the intake layer. It sits in front of the runtime and is responsible
for three things:
1. Receiving the Sentry webhook and validating its signature
2. Fetching enrichment data (Sentry events, GitHub commits + config)
3. Building an IncidentInput and handing it to AlphaRuntime.execute()

The runtime knows nothing about Sentry, GitHub, or HTTP. This file is the
only place that touches external APIs and request/response objects.

Run locally:
    uv run uvicorn main:app --reload

Sentry setup (one-time per client):
    Sentry → Settings → Integrations → Internal Integration → Webhooks
    → Add webhook URL: https://your-domain.com/webhooks/sentry
    → Check: Issue alerts
"""

import logging
import logging.handlers
import os
import pathlib

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request

load_dotenv()

from core.runtime import AlphaRuntime
from schemas.incident import IncidentInput
from sre.integrations.sentry import (
    fetch_enrichment,
    parse_webhook_payload,
    verify_sentry_signature,
)

# ---------------------------------------------------------------------------
# Logging — writes to console and alpha_sre.log at the project root
# ---------------------------------------------------------------------------

LOG_FILE = pathlib.Path(__file__).parent / "alpha_sre.log"
LOG_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Rotating file handler — caps the log at 1 MB, keeps 3 old files.
# So you'll have alpha_sre.log, alpha_sre.log.1, alpha_sre.log.2 at most.
_file_handler = logging.handlers.RotatingFileHandler(
    LOG_FILE,
    maxBytes=1_000_000,
    backupCount=3,
    encoding="utf-8",
)
_file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))

# Add directly to the root logger — basicConfig() is a no-op if uvicorn
# has already attached its own handlers, so we bypass it entirely.
_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)
_root_logger.addHandler(_file_handler)

logger = logging.getLogger(__name__)

app = FastAPI(title="Alpha SRE")

# ---------------------------------------------------------------------------
# Runtime setup
# ---------------------------------------------------------------------------
# The runtime is created once at startup and reused for every request.
# Agents are registered here. Each agent gets its own LLM client so
# different models can be used per agent (one string swap to change model).
#
# Phase 3/4: swap StubAgent for real SRE agents (LogAgent, MetricsAgent, etc.)

runtime = AlphaRuntime()

# TODO Phase 4: replace with real agents
# from sre.agents.log_agent import LogAgent
# from sre.agents.metrics_agent import MetricsAgent
# from sre.agents.commit_agent import CommitAgent
#
# runtime.register(LogAgent(llm=OpenRouterClient("anthropic/claude-sonnet-4-5")))
# runtime.register(MetricsAgent(llm=OpenRouterClient("google/gemini-2.0-flash-001")))
# runtime.register(CommitAgent(llm=OpenRouterClient("anthropic/claude-sonnet-4-5")))


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    """Simple liveness check. Used by deployment platforms to verify the
    server is running before routing traffic to it."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Sentry webhook handler
# ---------------------------------------------------------------------------

@app.post("/webhooks/sentry")
async def sentry_webhook(
    request: Request,
    sentry_hook_signature: str = Header(default=None),
):
    """Receive a Sentry issue-alert webhook and run the Alpha SRE pipeline.

    Flow:
        1. Read raw body (needed for HMAC verification before parsing)
        2. Verify Sentry signature — reject with 401 if invalid
        3. Parse the webhook payload to extract issue_id, project, org
        4. Fetch Sentry enrichment (logs, metrics) via Sentry API
        5. Fetch GitHub enrichment (commits, config snapshot) — stub for now
        6. Build IncidentInput and call AlphaRuntime.execute()
        7. Return ranked hypotheses as JSON

    Sentry retries webhooks on non-2xx responses, so always return 200
    once the signature is validated — even if analysis fails. Log failures
    internally rather than surfacing them as HTTP errors (which would cause
    Sentry to retry and flood the queue).

    Args:
        request:                 FastAPI request object.
        sentry_hook_signature:   Value of the 'sentry-hook-signature' header
                                 that Sentry attaches to every webhook POST.
    """

    # Step 1 — read raw body before any parsing.
    # FastAPI reads the body stream once. We need raw bytes for HMAC
    # verification, so we read it here before calling request.json().
    body = await request.body()

    # Step 2 — verify the Sentry HMAC signature.
    # This ensures the request actually came from Sentry and not an
    # arbitrary caller. Without this, anyone could POST to this endpoint
    # and trigger an analysis run.
    client_secret = os.environ.get("SENTRY_CLIENT_SECRET", "")

    if client_secret and sentry_hook_signature:
        if not verify_sentry_signature(body, sentry_hook_signature, client_secret):
            logger.warning("Rejected webhook: invalid Sentry signature.")
            raise HTTPException(status_code=401, detail="Invalid signature.")
    else:
        # No secret configured — skip verification in local development.
        # Never deploy without SENTRY_CLIENT_SECRET set.
        logger.warning("SENTRY_CLIENT_SECRET not set — skipping signature check.")

    # Step 3 — parse the webhook payload.
    import json
    try:
        raw = json.loads(body)
        payload = parse_webhook_payload(raw)
    except (KeyError, ValueError) as exc:
        logger.error("Failed to parse Sentry webhook payload: %s", exc)
        raise HTTPException(status_code=400, detail=f"Malformed payload: {exc}")

    # Only process new issues, not re-opens or assignments.
    if payload.action != "created":
        logger.info("Ignoring webhook action '%s' — only 'created' triggers analysis.", payload.action)
        return {"status": "ignored", "reason": f"action={payload.action}"}

    logger.info(
        "Processing Sentry issue %s from project '%s'.",
        payload.issue_id,
        payload.project_slug,
    )

    # Step 4 — fetch Sentry enrichment (logs, metrics, deployment_id).
    # Live if SENTRY_AUTH_TOKEN is set, fixture otherwise. See sre/integrations/sentry.py.
    sentry_data = await fetch_enrichment(payload)

    # Step 5 — fetch GitHub enrichment (recent commits, config snapshot).
    # TODO Phase 4: replace stub with real GitHubClient calls.
    # from sre.integrations.github import GitHubClient
    # github = GitHubClient(token=os.environ["GITHUB_TOKEN"])
    # github_data = github.fetch_enrichment(
    #     repo=os.environ["GITHUB_REPO"],          # e.g. "acme-corp/backend"
    #     since_sha=sentry_data["deployment_id"],
    # )
    github_data = _stub_github_enrichment()

    # Step 6 — build IncidentInput and run the pipeline.
    # IncidentInput is the contract between the intake layer and the runtime.
    # Everything above this line is intake; everything below is runtime.
    incident = IncidentInput(
        deployment_id=sentry_data["deployment_id"],
        logs=sentry_data["logs"],
        metrics=sentry_data["metrics"],
        recent_commits=github_data["recent_commits"],
        config_snapshot=github_data["config_snapshot"],
    )

    result = await runtime.execute(incident)

    logger.info(
        "Analysis complete for issue %s. %d hypotheses. Human review: %s.",
        payload.issue_id,
        len(result.ranked_hypotheses),
        result.requires_human_review,
    )

    # Step 7 — return the result.
    # For the hackathon, return JSON directly.
    # TODO Phase 4: also post to Slack or comment on the Sentry issue.
    # await post_to_slack(result)
    return {
        "execution_id": result.execution_id,
        "requires_human_review": result.requires_human_review,
        "hypotheses": [h.model_dump() for h in result.ranked_hypotheses],
    }


# ---------------------------------------------------------------------------
# GitHub enrichment stub
# ---------------------------------------------------------------------------

def _stub_github_enrichment() -> dict:
    """Return fixture commit and config data for Incident B.

    Phase 4 replaces this with a real GitHubClient that:
    - Calls GET /repos/{owner}/{repo}/commits?since={deploy_sha}
    - Calls GET /repos/{owner}/{repo}/contents/config.py?ref={sha}
    and returns the same shape as this stub.
    """
    import json
    import pathlib

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
                "diff_summary": "Removed @cache decorator from get_user_profile(). Added SELECT * FROM users JOIN orders query without index.",
            },
        ],
        "config_snapshot": {
            "MAX_DB_CONNECTIONS": 5,
            "CACHE_TTL_SECONDS": 0,
        },
    }
