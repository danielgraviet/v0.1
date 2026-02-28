"""Incident input schema.

Defines the structured payload that enters the Alpha runtime. This is the
contract between the data ingestion layer (Sentry, GitHub) and the runtime.
Signal extraction reads this payload and converts it into typed Signal objects
before any agent sees the data.
"""

from pydantic import BaseModel


class IncidentInput(BaseModel):
    """Raw incident payload received at the start of a runtime execution.

    This is the only external input to the system. Everything downstream
    (signals, hypotheses, ranked output) is derived from this object.
    Fields map directly to the four data sources: Sentry (logs + metrics)
    and GitHub (commits + config).

    Attributes:
        deployment_id: Unique identifier for the deployment that triggered
            the incident (e.g. "deploy-2024-11-15-v2.3.1"). Used for
            traceability across the execution result.
        logs: Raw log lines from Sentry error events. Signal extraction
            scans these for anomalies such as elevated error rates or
            repeated stack traces.
        metrics: Performance and resource metrics from Sentry, including
            current values and baselines. Common keys: "latency_p99_ms",
            "error_rate", "db_connection_pool_used", "cache_hit_rate".
        recent_commits: List of commits from GitHub in the deployment window.
            Each dict contains "sha", "message", and "diff_summary". For
            the hackathon, this is returned by a deterministic stub that
            mirrors the real GitHub API response format.
        config_snapshot: Key-value config state at the deploy SHA from GitHub.
            For the hackathon, returned by the same deterministic stub.
            Example: {"MAX_DB_CONNECTIONS": 5, "CACHE_TTL_SECONDS": 0}.
    """

    deployment_id: str
    logs: list[str]
    metrics: dict
    recent_commits: list[dict]
    config_snapshot: dict
