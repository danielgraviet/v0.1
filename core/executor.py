"""Parallel agent executor.

ParallelExecutor is responsible for running all registered agents concurrently
and collecting their results. It handles timeouts and fault isolation so the
runtime does not have to.

The key guarantee: one agent failing never causes other agents to be skipped.
Each agent runs in its own task with its own exception boundary.
"""

import asyncio
import logging
import time

from agents.base import AgentContext, BaseAgent
from schemas.events import AgentEvent, EventType
from schemas.result import AgentResult

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30


class ParallelExecutor:
    """Runs a list of agents concurrently and returns their results.

    Uses asyncio.TaskGroup to schedule all agents at once. Each agent runs
    in an isolated task — if one raises an exception or times out, the others
    continue unaffected.

    The executor also owns execution timing. It measures wall-clock time for
    each agent and writes it into the AgentResult, so agents do not need to
    track their own timing.

    Attributes:
        timeout_seconds: Maximum time in seconds to wait for a single agent
            before cancelling it and moving on. Defaults to 30.
    """

    def __init__(self, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> None:
        """Initialise the executor.

        Args:
            timeout_seconds: Per-agent timeout. Agents that exceed this are
                cancelled and logged as errors. The remaining agents continue.
        """
        self.timeout_seconds = timeout_seconds

    async def execute(
        self,
        agents: list[BaseAgent],
        context: AgentContext,
        event_queue: asyncio.Queue | None = None,
    ) -> list[AgentResult]:
        """Run all agents concurrently and return their results.

        Agents are dispatched simultaneously using asyncio.TaskGroup. The
        method waits until all agents have either completed, timed out, or
        raised an exception before returning.

        Failed agents are logged and excluded from the returned list. The
        caller (AlphaRuntime) receives only successful results.

        Args:
            agents: The list of agents to run. Typically sourced from
                AgentRegistry.get_all().
            context: The shared context passed to every agent — signals and
                incident metadata from StructuredMemory.
            event_queue: Optional asyncio.Queue to emit AgentEvents into.
                The display layer reads from this queue to update live panels.
                If None, events are silently skipped — the runtime is
                unaffected by whether anything is listening.

        Returns:
            List of AgentResult objects from agents that completed
            successfully. Agents that timed out or raised are excluded.
            May be empty if all agents failed.
        """
        if not agents:
            return []

        exec_start = time.perf_counter()

        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(
                    self._run_agent_safely(agent, context, event_queue, exec_start),
                    name=agent.name,
                )
                for agent in agents
            ]

        return [result for t in tasks if (result := t.result()) is not None]

    async def _run_agent_safely(
        self,
        agent: BaseAgent,
        context: AgentContext,
        event_queue: asyncio.Queue | None,
        exec_start: float,
    ) -> AgentResult | None:
        """Run a single agent with timeout and exception handling.

        This method never raises. All failures are caught, logged, and
        returned as None — which the caller filters out. This is what
        keeps a single failing agent from propagating into the TaskGroup
        and cancelling the other agents.

        The executor measures wall-clock time and writes it into the
        returned AgentResult, overriding whatever the agent reported.
        It also emits STARTED, COMPLETE, and ERROR events to the queue
        if one was provided.

        Args:
            agent: The agent to run.
            context: Shared execution context.
            event_queue: Queue to emit events into. None means no events.
            exec_start: perf_counter() value from when execute() was called.
                Used to compute relative timestamps for events.

        Returns:
            The agent's AgentResult with execution_time_ms filled in by
            the executor, or None if the agent timed out or raised.
        """
        agent_start = time.perf_counter()

        async def emit(event_type: EventType, message: str) -> None:
            if event_queue is not None:
                ts_ms = (time.perf_counter() - exec_start) * 1000
                await event_queue.put(AgentEvent(
                    agent_name=agent.name,
                    event_type=event_type,
                    message=message,
                    timestamp_ms=ts_ms,
                ))

        await emit(EventType.STARTED, "analyzing...")

        try:
            result = await asyncio.wait_for(
                agent.run(context),
                timeout=self.timeout_seconds,
            )
            elapsed_ms = (time.perf_counter() - agent_start) * 1000
            hypothesis_count = len(result.hypotheses)
            noun = "hypothesis" if hypothesis_count == 1 else "hypotheses"
            await emit(EventType.COMPLETE, f"{hypothesis_count} {noun} generated")
            return result.model_copy(update={"execution_time_ms": elapsed_ms})

        except asyncio.TimeoutError:
            elapsed_ms = (time.perf_counter() - agent_start) * 1000
            await emit(EventType.ERROR, f"timed out after {elapsed_ms / 1000:.1f}s")
            logger.error(
                "Agent '%s' timed out after %.1fs (limit: %ds) — skipping.",
                agent.name,
                elapsed_ms / 1000,
                self.timeout_seconds,
            )
            return None

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - agent_start) * 1000
            await emit(EventType.ERROR, str(exc))
            logger.error(
                "Agent '%s' raised after %.0fms — skipping. Error: %s",
                agent.name,
                elapsed_ms,
                exc,
            )
            return None
