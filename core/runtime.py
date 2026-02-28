"""Alpha runtime — the top-level pipeline orchestrator.

AlphaRuntime is the single entry point for the whole system. Callers
register agents once, then call execute() with an IncidentInput as many
times as needed. Each call is fully independent: fresh memory, fresh
context, fresh results.

Pipeline order inside execute():
    1. Initialize StructuredMemory for this run
    2. Run signal extraction (Phase 3 placeholder — empty for now)
    3. Build AgentContext from memory
    4. Execute all agents in parallel via ParallelExecutor
    5. Validate each result via JudgeLayer
    6. Aggregate valid results via Aggregator
    7. Return ExecutionResult

The runtime never imports from sre/. It depends only on core/, agents/,
judge/, aggregation/, and schemas/. The SRE vertical imports from the
runtime — never the reverse.
"""

import asyncio
import logging

from agents.base import AgentContext, BaseAgent
from aggregation.aggregator import Aggregator
from core.executor import ParallelExecutor
from core.memory import StructuredMemory
from core.registry import AgentRegistry
from judge.judge import JudgeLayer
from schemas.incident import IncidentInput
from schemas.result import ExecutionResult

logger = logging.getLogger(__name__)

HUMAN_REVIEW_CONFIDENCE_THRESHOLD = 0.5


class AlphaRuntime:
    """Orchestrates the full agent pipeline for one incident input.

    Holds a registry of agents and a fixed set of pipeline components
    (executor, judge, aggregator). These are created once at construction
    time and reused across all execute() calls.

    Each call to execute() creates its own StructuredMemory, so runs are
    fully isolated — one run cannot pollute the next.

    Attributes:
        _registry: Tracks all registered agents.
        _executor: Runs agents concurrently via asyncio.TaskGroup.
        _judge: Validates each AgentResult before aggregation.
        _aggregator: Ranks and deduplicates hypotheses into a final list.
    """

    def __init__(self) -> None:
        """Initialise the runtime with an empty agent registry."""
        self._registry = AgentRegistry()
        self._executor = ParallelExecutor()
        self._judge = JudgeLayer()
        self._aggregator = Aggregator()

    def register(self, agent: BaseAgent) -> None:
        """Register an agent to participate in every execute() call.

        Delegates directly to AgentRegistry. Raises ValueError if an agent
        with the same name is already registered — this is always a
        programming error, not a recoverable condition.

        Args:
            agent: The agent to register. Its name property is used as
                the unique key.

        Raises:
            ValueError: If an agent with the same name is already registered.
        """
        self._registry.register(agent)
        logger.debug("Registered agent '%s'. Total agents: %d.", agent.name, len(self._registry))

    async def execute(
        self,
        payload: IncidentInput,
        event_queue: asyncio.Queue | None = None,
    ) -> ExecutionResult:
        """Run the full pipeline for one incident and return ranked hypotheses.

        This method is the only way to trigger the pipeline. It is async
        because agent execution involves I/O (LLM API calls), and the
        executor uses asyncio.TaskGroup to run agents concurrently.

        Steps:
            1. Initialize fresh StructuredMemory for this run
            2. Signal extraction placeholder (Phase 3 will fill this in)
            3. Build AgentContext from memory signals + incident
            4. Dispatch all agents in parallel via ParallelExecutor
            5. Validate each result through JudgeLayer
            6. Aggregate valid results via Aggregator
            7. Decide requires_human_review and return ExecutionResult

        Args:
            payload: The validated IncidentInput for this execution.
                Pydantic enforces the schema at construction time, so by
                the time this method receives it, the input is already valid.

        Returns:
            An ExecutionResult containing ranked hypotheses, signals used,
            a unique execution ID, and a human review flag.
        """
        logger.info(
            "Starting execution for deployment '%s' with %d registered agents.",
            payload.deployment_id,
            len(self._registry),
        )

        # Step 1 — fresh memory for this run.
        # Memory is never shared across calls. Creating it here ensures that
        # two concurrent execute() calls cannot interfere with each other.
        memory = StructuredMemory()

        # Step 2 — signal extraction.
        # Phase 3 will replace this with a real SignalExtractor. For now the
        # memory stays empty and agents receive no pre-extracted signals.
        # The judge's signal ID cross-reference check will pass vacuously
        # if agents cite no signals, and will catch hallucinated IDs once
        # real signals are present.
        signals = self._extract_signals(payload, memory)
        logger.debug("Signal extraction complete. %d signals in memory.", len(signals))

        # Step 3 — build context from memory.
        # Agents receive a snapshot of the signals at this moment. Because
        # signal extraction is complete before any agent runs, all agents
        # see the same consistent signal list.
        context = AgentContext(
            signals=memory.get_signals(),
            incident=payload,
        )

        # Step 4 — parallel agent execution.
        # The executor returns only results from agents that completed
        # successfully. Timed-out or errored agents are logged and excluded.
        agents = self._registry.get_all()
        raw_results = await self._executor.execute(agents, context, event_queue)
        logger.info(
            "%d/%d agents returned results.",
            len(raw_results),
            len(agents),
        )

        # Step 5 — judge validation.
        # Every result is validated before it can contribute to the final
        # ranking. Rejected results are logged here so the caller does not
        # need to inspect internals to understand what was thrown out.
        judged_results = [self._judge.validate(result, memory) for result in raw_results]

        for judged in judged_results:
            if not judged.valid:
                logger.warning(
                    "Agent '%s' result rejected: %s",
                    judged.result.agent_name,
                    judged.rejection_reason,
                )

        valid_count = sum(1 for j in judged_results if j.valid)
        logger.info("%d/%d results passed judge validation.", valid_count, len(judged_results))

        # Step 6 — aggregate into ranked hypothesis list.
        ranked_hypotheses = self._aggregator.aggregate(judged_results)
        logger.info("Aggregation complete. %d ranked hypotheses.", len(ranked_hypotheses))

        # Step 7 — decide requires_human_review.
        # Flag the result for human review if:
        # - No hypotheses were produced at all, or
        # - The top hypothesis confidence is below the threshold (0.5).
        # This tells the caller not to act on the result automatically.
        requires_human_review = (
            len(ranked_hypotheses) == 0
            or ranked_hypotheses[0].confidence < HUMAN_REVIEW_CONFIDENCE_THRESHOLD
        )

        return ExecutionResult(
            ranked_hypotheses=ranked_hypotheses,
            signals_used=memory.get_signals(),
            requires_human_review=requires_human_review,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _extract_signals(self, payload: IncidentInput, memory: StructuredMemory) -> list:
        """Placeholder for Phase 3 signal extraction.

        Phase 3 will replace this method with a real SignalExtractor that
        parses logs, metrics, commits, and config snapshots into typed
        Signal objects and writes them into memory.

        For now this is a no-op. The empty signal list is a valid starting
        state — agents that generate hypotheses citing real signal IDs will
        be rejected by the judge (which is correct behaviour: no signals
        means no grounded evidence). Stub agents used in smoke tests should
        add signals to memory manually before calling execute(), or bypass
        this by constructing a runtime with pre-seeded memory.

        Args:
            payload: The raw incident data (unused until Phase 3).
            memory: The StructuredMemory for this run. Phase 3 will call
                memory.add_signals() here.

        Returns:
            The current signal list from memory (empty until Phase 3).
        """
        return memory.get_signals()
