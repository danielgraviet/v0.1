"""Tests for SynthesisAgent."""

import pytest

from llm.base import LLMClient
from schemas.hypothesis import Hypothesis
from schemas.signal import Signal
from sre.agents.synthesis_agent import SynthesisAgent


class StubLLM(LLMClient):
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    async def complete(self, system: str, user: str) -> str:
        self.calls += 1
        return self.response


def make_signal() -> Signal:
    return Signal(
        id="sig_001",
        type="metric_spike",
        description="p99 latency spiked",
        severity="high",
        source="metrics_analyzer",
    )


def make_hypothesis() -> Hypothesis:
    return Hypothesis(
        label="DB Pool Exhaustion",
        description="Connection pool saturated after deploy",
        confidence=0.84,
        severity="high",
        supporting_signals=["sig_001"],
        contributing_agent="metrics_agent",
    )


class TestSynthesisAgent:
    async def test_returns_fallback_when_no_hypotheses(self):
        llm = StubLLM(response='{"summary":"x","key_finding":"y","confidence_in_ranking":0.5}')
        agent = SynthesisAgent(llm=llm)

        result = await agent.synthesize(signals=[make_signal()], ranked_hypotheses=[])

        assert result.confidence_in_ranking == 0.0
        assert "Insufficient evidence" in result.key_finding
        assert llm.calls == 0

    async def test_parses_valid_llm_json(self):
        llm = StubLLM(
            response=(
                '{"summary":"Signals and rankings align.","key_finding":"DB pool saturation is the root cause.",'
                '"confidence_in_ranking":0.91}'
            )
        )
        agent = SynthesisAgent(llm=llm)

        result = await agent.synthesize(
            signals=[make_signal()],
            ranked_hypotheses=[make_hypothesis()],
        )

        assert result.key_finding == "DB pool saturation is the root cause."
        assert result.confidence_in_ranking == pytest.approx(0.91)
        assert llm.calls == 1

    async def test_parse_failure_falls_back_to_top_hypothesis(self):
        llm = StubLLM(response="not json")
        agent = SynthesisAgent(llm=llm)

        result = await agent.synthesize(
            signals=[make_signal()],
            ranked_hypotheses=[make_hypothesis()],
        )

        assert "DB Pool Exhaustion" in result.key_finding
        assert result.confidence_in_ranking == pytest.approx(0.84)
