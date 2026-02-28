"""Alpha SRE — CLI demo runner.

Runs the full pipeline against a fixture incident and renders live agent
panels in the terminal using Rich. Shows the ranked hypothesis table when
all agents complete.

Usage:
    uv run python cli.py

Phase 4: swap the demo stub agents below for real SRE agents (LogAgent,
MetricsAgent, CommitAgent) to run against live Sentry data.
"""

import asyncio

from rich.console import Console
from rich.table import Table

from agents.base import AgentContext, BaseAgent
from core.memory import StructuredMemory
from core.runtime import AlphaRuntime
from display.live import LiveDisplay
from schemas.hypothesis import Hypothesis
from schemas.incident import IncidentInput
from schemas.result import AgentResult
from schemas.signal import Signal

console = Console()


# ── Demo stub agents ──────────────────────────────────────────────────────────
# Simulate the Phase 4 SRE agents with asyncio.sleep() so the live panels
# are visually interesting. Each agent takes a different amount of time so
# you can see them completing independently — proving parallel execution.
#
# Phase 4: replace these classes with the real agents from sre/agents/.

class LogAgent(BaseAgent):
    name = "log_agent"

    def __init__(self):
        self.llm = None

    async def run(self, context: AgentContext) -> AgentResult:
        await asyncio.sleep(1.2)
        return AgentResult(
            agent_name=self.name,
            hypotheses=[
                Hypothesis(
                    label="Error Rate Spike",
                    description="Error rate 3.1x above baseline — consistent with DB connection exhaustion causing request failures",
                    confidence=0.85,
                    severity="high",
                    supporting_signals=["sig_001"],
                    contributing_agent=self.name,
                )
            ],
            execution_time_ms=1200.0,
        )


class MetricsAgent(BaseAgent):
    name = "metrics_agent"

    def __init__(self):
        self.llm = None

    async def run(self, context: AgentContext) -> AgentResult:
        await asyncio.sleep(0.9)
        return AgentResult(
            agent_name=self.name,
            hypotheses=[
                Hypothesis(
                    label="DB Connection Pool Exhaustion",
                    description="Pool at 100% capacity (5/5). Requests are queuing and timing out. Reduced pool size is the likely cause.",
                    confidence=0.91,
                    severity="high",
                    supporting_signals=["sig_002"],
                    contributing_agent=self.name,
                )
            ],
            execution_time_ms=900.0,
        )


class CommitAgent(BaseAgent):
    name = "commit_agent"

    def __init__(self):
        self.llm = None

    async def run(self, context: AgentContext) -> AgentResult:
        await asyncio.sleep(1.5)
        return AgentResult(
            agent_name=self.name,
            hypotheses=[
                Hypothesis(
                    label="DB Connection Pool Exhaustion",
                    description="Commit e4f5g6h reduced MAX_DB_CONNECTIONS from 20 to 5. Combined with cache removal in a1b2c3d, this saturated the pool.",
                    confidence=0.88,
                    severity="high",
                    supporting_signals=["sig_001", "sig_002"],
                    contributing_agent=self.name,
                )
            ],
            execution_time_ms=1500.0,
        )


# ── Demo runtime ──────────────────────────────────────────────────────────────

class _DemoRuntime(AlphaRuntime):
    """Seeds StructuredMemory with fixture signals so the judge passes.

    Overrides the Phase 3 placeholder. Phase 3 will replace this with a
    real SignalExtractor — at that point this class can be removed and
    the plain AlphaRuntime used directly.
    """

    def _extract_signals(self, payload: IncidentInput, memory: StructuredMemory) -> list:
        memory.add_signals([
            Signal(
                id="sig_001",
                type="log_anomaly",
                description="Error rate 3.1x above baseline",
                value=3.1,
                severity="high",
                source="log_analyzer",
            ),
            Signal(
                id="sig_002",
                type="resource_saturation",
                description="DB connection pool 100% saturated (5/5)",
                value=1.0,
                severity="high",
                source="metrics_analyzer",
            ),
        ])
        return memory.get_signals()


# ── Results table ─────────────────────────────────────────────────────────────

def _print_results(result) -> None:
    """Render the final ranked hypothesis table and human review flag."""
    if not result.ranked_hypotheses:
        console.print("\n[yellow]No hypotheses produced.[/yellow]")
        return

    table = Table(title="Ranked Hypotheses", show_lines=True, border_style="bright_black")
    table.add_column("#",          style="dim",   width=3,  justify="right")
    table.add_column("Label",      style="bold",  min_width=28)
    table.add_column("Confidence", width=12,      justify="center")
    table.add_column("Severity",   width=10,      justify="center")
    table.add_column("Agents",     style="dim",   min_width=20)

    for i, h in enumerate(result.ranked_hypotheses, 1):
        conf_color = "green" if h.confidence >= 0.8 else "yellow" if h.confidence >= 0.6 else "red"
        sev_color  = "red"   if h.severity == "high" else "yellow" if h.severity == "medium" else "dim"

        table.add_row(
            str(i),
            h.label,
            f"[{conf_color}]{h.confidence:.0%}[/{conf_color}]",
            f"[{sev_color}]{h.severity}[/{sev_color}]",
            h.contributing_agent,
        )

    console.print()
    console.print(table)

    review = (
        "[bold red]⚠  Requires human review[/bold red]"
        if result.requires_human_review
        else "[bold green]✓  Confidence sufficient for automated action[/bold green]"
    )
    console.print(f"\n{review}")
    console.print(f"[dim]execution: {result.execution_id}[/dim]\n")


# ── Entry point ───────────────────────────────────────────────────────────────

async def _run() -> None:
    incident = IncidentInput(
        deployment_id="deploy-v2.3.1-demo",
        logs=[
            "ERROR GET /api/users 500 timeout after 5000ms",
            "ERROR DB connection pool exhausted",
            "INFO  GET /api/users 200 45ms",
        ],
        metrics={
            "latency_p99_ms": 4800,
            "latency_baseline_p99_ms": 120,
            "error_rate": 0.31,
            "error_rate_baseline": 0.01,
            "db_connection_pool_used": 5,
            "db_connection_pool_max": 5,
        },
        recent_commits=[
            {
                "sha": "a1b2c3d",
                "message": "Remove cache from user profile endpoint",
                "diff_summary": "Removed @cache decorator from get_user_profile()",
            },
            {
                "sha": "e4f5g6h",
                "message": "Reduce DB pool for cost optimization",
                "diff_summary": "Changed MAX_DB_CONNECTIONS from 20 to 5",
            },
        ],
        config_snapshot={"MAX_DB_CONNECTIONS": 5, "CACHE_TTL_SECONDS": 0},
    )

    runtime = _DemoRuntime()
    runtime.register(LogAgent())
    runtime.register(MetricsAgent())
    runtime.register(CommitAgent())

    agent_names = [a.name for a in runtime._registry.get_all()]
    display = LiveDisplay(agent_names)
    event_queue: asyncio.Queue = asyncio.Queue()

    console.rule("[bold]Alpha SRE[/bold]")
    console.print(f"  deployment  [cyan]{incident.deployment_id}[/cyan]")
    console.print(f"  agents      [cyan]{len(agent_names)} registered[/cyan]")
    console.print()

    with display.make_live() as live:
        pipeline = asyncio.create_task(
            runtime.execute(incident, event_queue=event_queue)
        )
        consumer = asyncio.create_task(
            display.consume(event_queue, live)
        )

        result = await pipeline
        await event_queue.put(None)   # sentinel: tell consumer to stop
        await consumer

    _print_results(result)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
