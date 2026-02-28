"""Component tests for the runtime layer.

Covers StructuredMemory, AgentRegistry, JudgeLayer, Aggregator,
ParallelExecutor, and AlphaRuntime. No API keys or monkeypatching required —
all tests use stub agents and in-memory data only.
"""

import asyncio

import pytest

from agents.base import AgentContext, BaseAgent
from aggregation.aggregator import Aggregator
from core.executor import ParallelExecutor
from core.memory import StructuredMemory
from core.registry import AgentRegistry
from core.runtime import AlphaRuntime
from judge.judge import JudgeLayer, JudgedResult
from llm.base import LLMClient
from schemas.hypothesis import Hypothesis
from schemas.incident import IncidentInput
from schemas.result import AgentResult, ExecutionResult
from schemas.signal import Signal


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def memory():
    mem = StructuredMemory()
    mem.add_signals([
        Signal(id="sig_001", type="log_anomaly", description="Error rate spike", severity="high", source="log_analyzer"),
        Signal(id="sig_002", type="metric_spike", description="Latency spike", severity="high", source="metrics_analyzer"),
    ])
    return mem


@pytest.fixture
def context(memory):
    return AgentContext(
        signals=memory.get_signals(),
        incident=IncidentInput(
            deployment_id="test-001",
            logs=[],
            metrics={},
            recent_commits=[],
            config_snapshot={},
        ),
    )


def make_hypothesis(label="DB Exhaustion", confidence=0.8, signals=None, agent="test_agent"):
    return Hypothesis(
        label=label,
        description="Test hypothesis",
        confidence=confidence,
        severity="high",
        supporting_signals=signals if signals is not None else ["sig_001"],
        contributing_agent=agent,
    )


def make_result(agent_name="test_agent", hypotheses=None):
    return AgentResult(
        agent_name=agent_name,
        hypotheses=hypotheses if hypotheses is not None else [make_hypothesis()],
        execution_time_ms=0.0,
    )


def make_judged(agent_name="test_agent", label="DB Exhaustion", confidence=0.8,
                signals=None, valid=True):
    h = make_hypothesis(label=label, confidence=confidence,
                        signals=signals or ["sig_001"], agent=agent_name)
    result = make_result(agent_name=agent_name, hypotheses=[h])
    return JudgedResult(valid=valid, result=result)


class StubLLM(LLMClient):
    async def complete(self, system: str, user: str) -> str:
        return "ok"


# ── StructuredMemory ──────────────────────────────────────────────────────────

class TestStructuredMemory:
    def test_get_signals_returns_copy(self, memory):
        copy = memory.get_signals()
        copy.clear()
        assert len(memory.get_signals()) == 2

    def test_signal_ids_returns_set_of_ids(self, memory):
        assert memory.signal_ids() == {"sig_001", "sig_002"}

    def test_add_signal_appends(self, memory):
        memory.add_signal(Signal(id="sig_003", type="config_change",
                                 description="Config changed", severity="low", source="config_analyzer"))
        assert "sig_003" in memory.signal_ids()

    def test_starts_empty(self):
        mem = StructuredMemory()
        assert mem.get_signals() == []
        assert mem.get_hypotheses() == []


# ── AgentRegistry ─────────────────────────────────────────────────────────────

class TestAgentRegistry:
    def _make_agent(self, name):
        agent_name = name

        class _Agent(BaseAgent):
            name = agent_name

            async def run(self, context: AgentContext) -> AgentResult:
                return AgentResult(agent_name=self.name, hypotheses=[], execution_time_ms=0.0)

        return _Agent(llm=StubLLM())

    def test_register_and_get_all(self):
        registry = AgentRegistry()
        registry.register(self._make_agent("log_agent"))
        assert len(registry) == 1
        assert registry.get_all()[0].name == "log_agent"

    def test_duplicate_name_raises(self):
        registry = AgentRegistry()
        registry.register(self._make_agent("log_agent"))
        with pytest.raises(ValueError, match="already registered"):
            registry.register(self._make_agent("log_agent"))

    def test_get_by_name_returns_none_when_missing(self):
        registry = AgentRegistry()
        assert registry.get_by_name("nonexistent") is None

    def test_get_all_returns_copy(self):
        registry = AgentRegistry()
        registry.register(self._make_agent("log_agent"))
        copy = registry.get_all()
        copy.clear()
        assert len(registry) == 1


# ── JudgeLayer ────────────────────────────────────────────────────────────────

class TestJudgeLayer:
    def test_valid_result_passes(self, memory):
        judge = JudgeLayer()
        result = judge.validate(make_result(), memory)
        assert result.valid is True
        assert result.rejection_reason is None

    def test_empty_agent_name_fails(self, memory):
        judge = JudgeLayer()
        result = judge.validate(make_result(agent_name="  "), memory)
        assert result.valid is False
        assert "agent_name" in result.rejection_reason

    def test_hypothesis_with_no_signals_fails(self, memory):
        judge = JudgeLayer()
        h = make_hypothesis(signals=[])
        result = judge.validate(make_result(hypotheses=[h]), memory)
        assert result.valid is False
        assert "no supporting signals" in result.rejection_reason

    def test_unknown_signal_id_fails(self, memory):
        judge = JudgeLayer()
        h = make_hypothesis(signals=["sig_999"])
        result = judge.validate(make_result(hypotheses=[h]), memory)
        assert result.valid is False
        assert "sig_999" in result.rejection_reason

    def test_zero_hypotheses_is_valid(self, memory):
        judge = JudgeLayer()
        result = judge.validate(make_result(hypotheses=[]), memory)
        assert result.valid is True


# ── Aggregator ────────────────────────────────────────────────────────────────

class TestAggregator:
    def test_agreement_bonus_applied(self):
        aggregator = Aggregator()
        results = [
            make_judged("metrics_agent", "DB Exhaustion", 0.80, ["sig_001"]),
            make_judged("commit_agent",  "DB Exhaustion", 0.70, ["sig_001"]),
        ]
        ranked = aggregator.aggregate(results)
        assert len(ranked) == 1
        assert ranked[0].confidence == pytest.approx(0.90)

    def test_invalid_results_excluded(self):
        aggregator = Aggregator()
        results = [
            make_judged("metrics_agent", "DB Exhaustion", 0.80, ["sig_001"], valid=True),
            make_judged("crash_agent",   "DB Exhaustion", 0.90, ["sig_001"], valid=False),
        ]
        ranked = aggregator.aggregate(results)
        assert len(ranked) == 1
        assert "crash_agent" not in ranked[0].contributing_agent

    def test_sorted_by_confidence_descending(self):
        aggregator = Aggregator()
        results = [
            make_judged("agent_a", "Low Confidence Issue",  0.40, ["sig_001"]),
            make_judged("agent_b", "High Confidence Issue", 0.90, ["sig_001"]),
            make_judged("agent_c", "Mid Confidence Issue",  0.65, ["sig_001"]),
        ]
        ranked = aggregator.aggregate(results)
        confidences = [h.confidence for h in ranked]
        assert confidences == sorted(confidences, reverse=True)

    def test_no_valid_hypotheses_returns_empty(self):
        aggregator = Aggregator()
        results = [make_judged("agent", "Issue", 0.8, ["sig_001"], valid=False)]
        assert aggregator.aggregate(results) == []

    def test_signals_merged_across_agents(self):
        aggregator = Aggregator()
        results = [
            make_judged("agent_a", "DB Exhaustion", 0.80, ["sig_001"]),
            make_judged("agent_b", "DB Exhaustion", 0.70, ["sig_002"]),
        ]
        ranked = aggregator.aggregate(results)
        assert "sig_001" in ranked[0].supporting_signals
        assert "sig_002" in ranked[0].supporting_signals

    def test_returns_at_most_five(self):
        aggregator = Aggregator()
        results = [
            make_judged(f"agent_{i}", f"Unique Issue {i}", 0.5, ["sig_001"])
            for i in range(8)
        ]
        assert len(aggregator.aggregate(results)) <= 5


# ── ParallelExecutor ──────────────────────────────────────────────────────────

class StubAgent(BaseAgent):
    name = "stub_agent"

    async def run(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            hypotheses=[make_hypothesis()],
            execution_time_ms=0.0,
        )


class CrashAgent(BaseAgent):
    name = "crash_agent"

    async def run(self, context: AgentContext) -> AgentResult:
        raise RuntimeError("agent failed")


class SlowAgent(BaseAgent):
    name = "slow_agent"

    async def run(self, context: AgentContext) -> AgentResult:
        await asyncio.sleep(999)
        return AgentResult(agent_name=self.name, hypotheses=[], execution_time_ms=0.0)


class TestParallelExecutor:
    async def test_successful_agent_returns_result(self, context):
        executor = ParallelExecutor()
        results = await executor.execute([StubAgent(StubLLM())], context)
        assert len(results) == 1
        assert results[0].agent_name == "stub_agent"

    async def test_crashing_agent_is_skipped(self, context):
        executor = ParallelExecutor()
        results = await executor.execute(
            [StubAgent(StubLLM()), CrashAgent(StubLLM())], context
        )
        assert len(results) == 1
        assert results[0].agent_name == "stub_agent"

    async def test_timed_out_agent_is_skipped(self, context):
        executor = ParallelExecutor(timeout_seconds=1)
        results = await executor.execute(
            [StubAgent(StubLLM()), SlowAgent(StubLLM())], context
        )
        assert len(results) == 1
        assert results[0].agent_name == "stub_agent"

    async def test_execution_time_is_recorded(self, context):
        executor = ParallelExecutor()
        results = await executor.execute([StubAgent(StubLLM())], context)
        assert results[0].execution_time_ms > 0

    async def test_empty_agent_list_returns_empty(self, context):
        executor = ParallelExecutor()
        results = await executor.execute([], context)
        assert results == []


# ── AlphaRuntime ──────────────────────────────────────────────────────────────

def make_incident(**overrides):
    defaults = dict(
        deployment_id="test-001",
        logs=[],
        metrics={},
        recent_commits=[],
        config_snapshot={},
    )
    return IncidentInput(**{**defaults, **overrides})


class SeededRuntime(AlphaRuntime):
    """AlphaRuntime subclass that pre-seeds memory with two known signals.

    The default _extract_signals() is a Phase 3 placeholder that returns
    an empty list. This subclass overrides it so agents can cite real signal
    IDs and pass the judge's cross-reference check.
    """
    def _extract_signals(self, payload, memory):
        memory.add_signals([
            Signal(id="sig_001", type="log_anomaly", description="Error spike",
                   severity="high", source="log_analyzer"),
            Signal(id="sig_002", type="metric_spike", description="Latency spike",
                   severity="high", source="metrics_analyzer"),
        ])
        return memory.get_signals()


class TestAlphaRuntime:
    async def test_execute_returns_execution_result(self):
        runtime = AlphaRuntime()
        result = await runtime.execute(make_incident())
        assert isinstance(result, ExecutionResult)

    async def test_no_agents_returns_empty_hypotheses(self):
        runtime = AlphaRuntime()
        result = await runtime.execute(make_incident())
        assert result.ranked_hypotheses == []

    async def test_requires_human_review_when_no_hypotheses(self):
        runtime = AlphaRuntime()
        result = await runtime.execute(make_incident())
        assert result.requires_human_review is True

    async def test_each_execution_gets_unique_id(self):
        runtime = AlphaRuntime()
        r1 = await runtime.execute(make_incident())
        r2 = await runtime.execute(make_incident())
        assert r1.execution_id != r2.execution_id

    def test_register_raises_on_duplicate_name(self):
        runtime = AlphaRuntime()
        runtime.register(StubAgent(StubLLM()))
        with pytest.raises(ValueError, match="already registered"):
            runtime.register(StubAgent(StubLLM()))

    async def test_crashing_agent_does_not_crash_runtime(self):
        # CrashAgent raises RuntimeError on every run — the runtime should
        # swallow it and still return a valid ExecutionResult.
        runtime = AlphaRuntime()
        runtime.register(CrashAgent(StubLLM()))
        result = await runtime.execute(make_incident())
        assert isinstance(result, ExecutionResult)

    async def test_judge_rejects_hallucinated_signal_id(self):
        # Agent cites sig_999 which was never extracted into memory.
        # The judge should reject it, leaving zero ranked hypotheses.
        class HallucinatingAgent(BaseAgent):
            name = "hallucinating_agent"

            async def run(self, context: AgentContext) -> AgentResult:
                return AgentResult(
                    agent_name=self.name,
                    hypotheses=[Hypothesis(
                        label="Ghost hypothesis",
                        description="Cites a signal that does not exist",
                        confidence=0.9,
                        severity="high",
                        supporting_signals=["sig_999"],
                        contributing_agent=self.name,
                    )],
                    execution_time_ms=0.0,
                )

        runtime = AlphaRuntime()
        runtime.register(HallucinatingAgent(StubLLM()))
        result = await runtime.execute(make_incident())
        assert result.ranked_hypotheses == []

    async def test_two_agents_both_appear_in_output(self):
        # Both agents must appear as contributing_agent in the results,
        # proving the executor ran them in parallel.
        class AgentA(BaseAgent):
            name = "agent_a"

            async def run(self, context: AgentContext) -> AgentResult:
                return AgentResult(
                    agent_name=self.name,
                    hypotheses=[Hypothesis(
                        label="Cache Issue", description="Cache miss cascade",
                        confidence=0.7, severity="medium",
                        supporting_signals=["sig_001"], contributing_agent=self.name,
                    )],
                    execution_time_ms=0.0,
                )

        class AgentB(BaseAgent):
            name = "agent_b"

            async def run(self, context: AgentContext) -> AgentResult:
                return AgentResult(
                    agent_name=self.name,
                    hypotheses=[Hypothesis(
                        label="DB Saturation", description="Pool exhausted",
                        confidence=0.8, severity="high",
                        supporting_signals=["sig_002"], contributing_agent=self.name,
                    )],
                    execution_time_ms=0.0,
                )

        runtime = SeededRuntime()
        runtime.register(AgentA(StubLLM()))
        runtime.register(AgentB(StubLLM()))
        result = await runtime.execute(make_incident())

        all_agents = ", ".join(h.contributing_agent for h in result.ranked_hypotheses)
        assert "agent_a" in all_agents
        assert "agent_b" in all_agents

    async def test_does_not_require_review_when_high_confidence(self):
        class HighConfAgent(BaseAgent):
            name = "high_conf_agent"

            async def run(self, context: AgentContext) -> AgentResult:
                return AgentResult(
                    agent_name=self.name,
                    hypotheses=[Hypothesis(
                        label="Clear Root Cause", description="High confidence finding",
                        confidence=0.9, severity="high",
                        supporting_signals=["sig_001"], contributing_agent=self.name,
                    )],
                    execution_time_ms=0.0,
                )

        runtime = SeededRuntime()
        runtime.register(HighConfAgent(StubLLM()))
        result = await runtime.execute(make_incident())
        assert result.requires_human_review is False

    async def test_signals_used_reflects_memory(self):
        # signals_used in ExecutionResult should contain whatever
        # _extract_signals wrote into memory during the run.
        runtime = SeededRuntime()
        result = await runtime.execute(make_incident())
        assert len(result.signals_used) == 2
        signal_ids = {s.id for s in result.signals_used}
        assert signal_ids == {"sig_001", "sig_002"}
