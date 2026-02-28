"""Sentry integration client.

Responsible for two things:
1. Validating the HMAC signature on incoming Sentry webhooks
2. Fetching enrichment data from the Sentry API to build an IncidentInput

Live mode:   set SENTRY_AUTH_TOKEN in your .env — fetch_enrichment() calls the real API.
Fixture mode: leave SENTRY_AUTH_TOKEN unset — fetch_enrichment() loads incident_b.json.

The fixture path lets the full pipeline run for the demo without a live
Sentry project. The live path is what clients actually trigger in production.

Sentry API reference: https://docs.sentry.io/api/
"""

import hashlib
import hmac
import json
import logging
import os
import pathlib
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

SENTRY_API_BASE = "https://sentry.io/api/0"


# ---------------------------------------------------------------------------
# Webhook payload schema
# ---------------------------------------------------------------------------

@dataclass
class SentryWebhookPayload:
    """The fields Alpha SRE needs from a Sentry issue-alert webhook.

    Sentry sends a larger payload — this captures only what's needed to
    kick off enrichment. Full webhook schema:
    https://docs.sentry.io/product/integrations/integration-platform/webhooks/issue-alerts/

    Attributes:
        issue_id:     Sentry issue ID (e.g. "4500123456"). Used to fetch
                      full issue details and events via the Sentry API.
        project_slug: Sentry project slug (e.g. "backend-api").
        org_slug:     Sentry organization slug (e.g. "acme-corp"). Needed
                      for organization-scoped API endpoints.
        action:       What triggered the webhook: "created", "resolved",
                      "assigned". Alpha only processes "created".
    """
    issue_id: str
    project_slug: str
    org_slug: str
    action: str


# ---------------------------------------------------------------------------
# Signature validation
# ---------------------------------------------------------------------------

def verify_sentry_signature(body: bytes, header_signature: str, secret: str) -> bool:
    """Verify the HMAC-SHA256 signature Sentry attaches to every webhook.

    Sentry signs each request using the client secret configured in your
    internal integration settings. This prevents arbitrary POST requests
    from triggering analysis runs.

    The webhook handler should call this before any other processing and
    return HTTP 401 immediately if it returns False.

    Args:
        body:             Raw request body bytes — must be read before any
                          JSON parsing, since HMAC is computed over raw bytes.
        header_signature: Value of the 'sentry-hook-signature' header.
        secret:           Your integration's client secret, from
                          SENTRY_CLIENT_SECRET in .env.

    Returns:
        True if the signature is valid, False otherwise.
    """
    expected = hmac.new(
        key=secret.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, header_signature)


# ---------------------------------------------------------------------------
# Webhook payload parser
# ---------------------------------------------------------------------------

def parse_webhook_payload(raw: dict) -> SentryWebhookPayload:
    """Extract the fields Alpha SRE needs from the raw Sentry webhook body.

    Sentry sends two different payload shapes depending on the event type:

    Issue alert (issue.created / action="created"):
    {
        "action": "created",
        "actor": {"name": "acme-corp", ...},
        "data": {
            "issue": {"id": "4500123456", "project": {"slug": "backend-api"}, ...}
        }
    }

    Error event (error.created):
    {
        "action": "created",
        "actor": {"name": "sentry", ...},
        "data": {
            "error": {
                "issue_id": "4500123456",
                "project": {"slug": "backend-api", "id": "123"},
                ...
            }
        }
    }

    This function handles both shapes by checking which key is present
    in data before extracting fields.

    Args:
        raw: Parsed JSON body from the incoming POST.

    Returns:
        SentryWebhookPayload with the fields needed to drive enrichment.

    Raises:
        KeyError: If expected fields are missing. The webhook handler
            catches this and returns HTTP 400.
    """
    logger.debug("Raw Sentry payload keys: %s", list(raw.get("data", {}).keys()))

    data = raw["data"]

    if "issue" in data:
        # Issue alert format
        issue = data["issue"]
        issue_id = issue["id"]
        project_slug = issue["project"]["slug"]
    elif "error" in data:
        # Error event format — issue_id is a field on the error object.
        # project may be a dict {"slug": "..."} or a bare integer project ID
        # depending on the Sentry version and integration type.
        error = data["error"]
        issue_id = str(error["issue_id"])
        project_raw = error["project"]
        project_slug = project_raw["slug"] if isinstance(project_raw, dict) else str(project_raw)
    else:
        raise KeyError(
            f"Unrecognised Sentry payload — expected 'issue' or 'error' in data. "
            f"Got keys: {list(data.keys())}"
        )

    return SentryWebhookPayload(
        issue_id=issue_id,
        project_slug=project_slug,
        org_slug=raw["actor"]["name"],
        action=raw["action"],
    )


# ---------------------------------------------------------------------------
# Enrichment fetcher — live or fixture depending on env
# ---------------------------------------------------------------------------

async def fetch_enrichment(payload: SentryWebhookPayload) -> dict:
    """Fetch logs, metrics, and deployment ID for the given Sentry issue.

    Switches automatically between live and fixture mode based on whether
    SENTRY_AUTH_TOKEN is set in the environment:

    - Live mode: makes three Sentry API calls (issue metadata, events, stats)
      and maps the responses to the IncidentInput shape.
    - Fixture mode: loads incident_b.json so the demo runs without a live
      Sentry project.

    Returns a dict with keys: "deployment_id", "logs", "metrics".
    GitHub data (commits, config_snapshot) is fetched separately in main.py.

    Args:
        payload: Parsed webhook payload identifying the issue and org.

    Returns:
        Dict with "deployment_id" (str), "logs" (list[str]),
        "metrics" (dict).

    Raises:
        httpx.HTTPStatusError: If a Sentry API call returns a non-2xx
            response. The webhook handler logs this and returns 200 to
            prevent Sentry retries.
    """
    token = os.environ.get("SENTRY_AUTH_TOKEN")

    if not token:
        logger.info("SENTRY_AUTH_TOKEN not set — using fixture data.")
        return _load_fixture()

    logger.info("Fetching Sentry enrichment for issue %s.", payload.issue_id)
    return await _fetch_from_api(payload, token)


# ---------------------------------------------------------------------------
# Live Sentry API calls
# ---------------------------------------------------------------------------

async def _fetch_from_api(payload: SentryWebhookPayload, token: str) -> dict:
    """Make three Sentry API calls and map the results to IncidentInput fields.

    Calls:
        1. GET /issues/{id}/        — issue metadata (deployment_id, event count)
        2. GET /issues/{id}/events/ — individual error events (log lines)
        3. GET /issues/{id}/stats/  — event count over time (error rate)

    Args:
        payload: Parsed webhook payload.
        token:   Sentry auth token from SENTRY_AUTH_TOKEN.

    Returns:
        Dict with "deployment_id", "logs", "metrics".
    """
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(base_url=SENTRY_API_BASE, headers=headers, timeout=15) as client:

        # 1. Issue metadata — gives us the release version (deployment_id)
        #    and total event count for computing error rate.
        issue_resp = await client.get(f"/issues/{payload.issue_id}/")
        issue_resp.raise_for_status()
        issue = issue_resp.json()

        # 2. Most recent error events — each event is one occurrence of the
        #    error with its stack trace, breadcrumbs, and culprit location.
        #    We convert these into log lines for the signal extractor.
        events_resp = await client.get(
            f"/issues/{payload.issue_id}/events/",
            params={"limit": 100, "full": "true"},
        )
        events_resp.raise_for_status()
        events = events_resp.json()

        # 3. Event count over time — used to compute error rate relative to
        #    a baseline. Sentry returns [[timestamp_ms, count], ...] pairs.
        stats_resp = await client.get(
            f"/issues/{payload.issue_id}/stats/",
            params={"stat": "event_count"},
        )
        stats_resp.raise_for_status()
        stats = stats_resp.json()

    deployment_id = (
        issue.get("lastRelease", {}).get("version")
        or payload.issue_id
    )

    logs = _events_to_log_lines(events)
    metrics = _build_metrics(issue, stats)

    logger.info(
        "Sentry enrichment complete: %d log lines, deployment '%s'.",
        len(logs),
        deployment_id,
    )

    return {
        "deployment_id": deployment_id,
        "logs": logs,
        "metrics": metrics,
    }


def _events_to_log_lines(events: list[dict]) -> list[str]:
    """Convert Sentry error events into plain log lines.

    Each event becomes one or more log lines:
    - The top-level error line: "ERROR {culprit} — {title}"
    - Up to 3 breadcrumb lines showing what happened before the error

    Breadcrumbs are the console/navigation/http events Sentry records in
    the seconds before an exception fires. They give the signal extractor
    context about what the app was doing when it crashed.

    Args:
        events: List of Sentry event objects from the /events/ endpoint.

    Returns:
        Flat list of log line strings, oldest events first.
    """
    lines = []

    for event in events:
        culprit = event.get("culprit") or "unknown"
        title = event.get("title") or event.get("message") or "error"
        lines.append(f"ERROR {culprit} — {title}")

        # Pull breadcrumbs if present — they show the request path,
        # DB queries, or console messages that preceded the crash.
        for entry in event.get("entries", []):
            if entry.get("type") == "breadcrumbs":
                crumbs = entry.get("data", {}).get("values", [])
                for crumb in crumbs[-3:]:  # last 3 breadcrumbs per event
                    msg = crumb.get("message") or crumb.get("data", {}).get("url", "")
                    if msg:
                        category = crumb.get("category", "breadcrumb")
                        lines.append(f"INFO  [{category}] {msg}")

    return lines


def _build_metrics(issue: dict, stats: list) -> dict:
    """Build the metrics dict from Sentry issue data and event stats.

    Sentry provides error frequency (events over time) but not application
    performance metrics like latency or connection pool usage. Those come
    from the fixture for the demo — this function populates only what
    Sentry can actually tell us.

    Fields populated from live data:
    - error_rate: recent events per stat bucket, normalised to 0.0–1.0
    - event_count_1h: total events in the stats window

    Fields with hardcoded baselines (Sentry has no baseline concept):
    - error_rate_baseline: 0.01 (1% — typical healthy error rate)
    - latency_* fields: zeroed — not available from basic Sentry

    Args:
        issue:  Full issue object from GET /issues/{id}/.
        stats:  List of [timestamp_ms, count] pairs from /issues/{id}/stats/.

    Returns:
        Metrics dict matching the keys expected by MetricsAnalyzer.
    """
    event_counts = [point[1] for point in stats if len(point) == 2]
    total_events = sum(event_counts)
    buckets = max(len(event_counts), 1)

    # Normalise: average events per bucket as a rough error rate proxy.
    # Real error rate would need total request volume, which Sentry only
    # provides with Performance monitoring enabled.
    avg_events_per_bucket = total_events / buckets
    error_rate = min(round(avg_events_per_bucket / 100, 4), 1.0)

    return {
        "error_rate": error_rate,
        "error_rate_baseline": 0.01,
        "event_count_1h": total_events,
        # Latency and DB metrics are not available from basic Sentry —
        # the fixture fills these in for the demo.
        "latency_p99_ms": 0,
        "latency_baseline_p99_ms": 0,
        "db_connection_pool_used": 0,
        "db_connection_pool_max": 0,
        "cache_hit_rate": 0,
        "cache_hit_rate_baseline": 0,
    }


# ---------------------------------------------------------------------------
# Fixture fallback
# ---------------------------------------------------------------------------

def _load_fixture() -> dict:
    """Load the incident_b.json fixture for demo runs.

    Used when SENTRY_AUTH_TOKEN is not set — lets the full pipeline run
    and produce meaningful output without a live Sentry account.
    """
    fixture_path = pathlib.Path(__file__).parents[2] / "fixtures" / "incident_b.json"

    if fixture_path.exists():
        with open(fixture_path) as f:
            data = json.load(f)
        return {
            "deployment_id": data["deployment_id"],
            "logs": data["logs"],
            "metrics": data["metrics"],
        }

    # Hard fallback if fixture hasn't been created yet (Phase 3 task)
    logger.warning("fixtures/incident_b.json not found — using minimal inline fallback.")
    return {
        "deployment_id": "deploy-fixture-001",
        "logs": [
            "INFO  GET /api/users 200 45ms",
            "ERROR GET /api/users 500 timeout after 5000ms",
            "ERROR DB connection pool exhausted",
        ],
        "metrics": {
            "latency_p99_ms": 4800,
            "latency_baseline_p99_ms": 120,
            "error_rate": 0.31,
            "error_rate_baseline": 0.01,
            "db_connection_pool_used": 5,
            "db_connection_pool_max": 5,
            "cache_hit_rate": 0.08,
            "cache_hit_rate_baseline": 0.82,
        },
    }
