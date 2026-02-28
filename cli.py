"""Alpha SRE — CLI demo runner.

Runs the full pipeline against the incident_b.json fixture and renders
live agent panels in the terminal using Rich. Shows the ranked hypothesis
table when all agents complete.

Usage:
    uv run python cli.py
"""

import asyncio
import json
import pathlib

from rich.console import Console
from rich.table import Table

from core.runtime import AlphaRuntime
from display.live import LiveDisplay
from llm.openrouter import OpenRouterClient
from schemas.incident import IncidentInput
from sre.agents.commit_agent import CommitAgent
from sre.agents.config_agent import ConfigAgent
from sre.agents.log_agent import LogAgent
from sre.agents.metrics_agent import MetricsAgent

console = Console()

_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "incident_b.json"


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
    with open(_FIXTURE) as f:
        incident = IncidentInput(**json.load(f))

    runtime = AlphaRuntime()
    runtime.register(LogAgent(llm=OpenRouterClient("anthropic/claude-sonnet-4-6")))
    runtime.register(MetricsAgent(llm=OpenRouterClient("google/gemini-2.0-flash-001")))
    runtime.register(CommitAgent(llm=OpenRouterClient("anthropic/claude-sonnet-4-6")))
    runtime.register(ConfigAgent(llm=OpenRouterClient("google/gemini-2.0-flash-001")))

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
        await event_queue.put(None)
        await consumer

    _print_results(result)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
