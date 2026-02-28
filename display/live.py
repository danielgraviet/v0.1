"""Rich live display — one panel per agent, updating in real time.

The display layer is fully decoupled from the runtime. It subscribes to an
asyncio.Queue of AgentEvents and renders them into a live terminal layout.
The runtime runs whether or not a display is attached — it just puts events
into the queue and never checks if anyone is reading.

Usage:
    event_queue = asyncio.Queue()
    display = LiveDisplay(agent_names)

    with display.make_live() as live:
        pipeline = asyncio.create_task(runtime.execute(payload, event_queue))
        consumer = asyncio.create_task(display.consume(event_queue, live))
        result = await pipeline
        await event_queue.put(None)  # sentinel — tells consume() to stop
        await consumer
"""

import asyncio
from dataclasses import dataclass, field

from rich.columns import Columns
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from schemas.events import AgentEvent, EventType


# ── Per-agent state ───────────────────────────────────────────────────────────

@dataclass
class _AgentState:
    """Mutable state for one agent's panel.

    Updated by _apply() each time an event arrives. The display reads this
    to re-render the panel on every refresh tick.
    """
    name: str
    status: str = "waiting"    # waiting | running | complete | error
    elapsed_ms: float = 0.0
    messages: list[str] = field(default_factory=list)


# ── Display ───────────────────────────────────────────────────────────────────

class LiveDisplay:
    """Manages the Rich live layout and subscribes to the event queue.

    Attributes:
        _states: Dict of agent name → _AgentState, updated as events arrive.
        _order:  Agent names in registration order — preserves panel layout.
    """

    def __init__(self, agent_names: list[str]) -> None:
        self._states = {name: _AgentState(name=name) for name in agent_names}
        self._order = list(agent_names)

    def make_live(self) -> Live:
        """Return a Rich Live context manager ready to use with `with`."""
        return Live(self._render(), refresh_per_second=12, transient=False)

    async def consume(self, queue: asyncio.Queue, live: Live) -> None:
        """Read events from the queue and update the display until sentinel.

        Runs concurrently with the pipeline. Stops when it receives None
        (the sentinel the CLI puts into the queue after the pipeline finishes).

        Args:
            queue: The asyncio.Queue the executor writes AgentEvents into.
            live:  The active Rich Live context to update on each event.
        """
        while True:
            event = await queue.get()
            if event is None:
                break
            self._apply(event)
            live.update(self._render())

    # ── Private ───────────────────────────────────────────────────────────────

    def _apply(self, event: AgentEvent) -> None:
        """Update the agent state from an incoming event."""
        state = self._states.get(event.agent_name)
        if state is None:
            return

        state.elapsed_ms = event.timestamp_ms

        if event.event_type == EventType.STARTED:
            state.status = "running"
            state.messages.append("analyzing...")

        elif event.event_type == EventType.COMPLETE:
            state.status = "complete"
            state.messages.append(f"✓ {event.message}")

        elif event.event_type == EventType.ERROR:
            state.status = "error"
            state.messages.append(f"✗ {event.message}")

        elif event.event_type == EventType.SIGNAL_DETECTED:
            state.messages.append(f"→ {event.message}")

        # Keep only the last 4 lines so panels don't grow unbounded
        state.messages = state.messages[-4:]

    def _render_panel(self, state: _AgentState) -> Panel:
        """Build a Rich Panel for one agent from its current state."""
        icons = {
            "waiting":  "[dim]○[/dim]",
            "running":  "[bold yellow]●[/bold yellow]",
            "complete": "[bold green]✓[/bold green]",
            "error":    "[bold red]✗[/bold red]",
        }
        border_styles = {
            "waiting":  "dim",
            "running":  "yellow",
            "complete": "green",
            "error":    "red",
        }

        icon = icons.get(state.status, "○")
        elapsed = f"[dim][{state.elapsed_ms / 1000:.2f}s][/dim]"
        header = Text.from_markup(f"{elapsed}  {icon}")

        lines: list[Text] = [header]
        for msg in state.messages:
            lines.append(Text.from_markup(f"  [dim]{msg}[/dim]"))

        return Panel(
            Group(*lines),
            title=f"[bold]{state.name}[/bold]",
            border_style=border_styles.get(state.status, "dim"),
            width=42,
        )

    def _render(self) -> Group:
        """Build the full layout: panels arranged in rows of two."""
        panels = [self._render_panel(self._states[name]) for name in self._order]
        rows = []
        for i in range(0, len(panels), 2):
            rows.append(Columns(panels[i : i + 2], equal=True))
        return Group(*rows)
