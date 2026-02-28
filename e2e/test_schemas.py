"""Schema validation tests.

These tests verify that all Pydantic models accept valid data, reject invalid
data, and enforce field constraints. No API key or external services required.
"""

import uuid

import pytest
from pydantic import ValidationError

from schemas.events import AgentEvent, EventType
from schemas.hypothesis import Hypothesis
from schemas.incident import IncidentInput
from schemas.result import AgentResult, ExecutionResult, SynthesisResult
from schemas.signal import Signal


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_signal(**overrides) -> Signal:
    defaults = dict(
        id="sig_001",
        type="log_anomaly",
        description="Error rate 3x above baseline",
        severity="high",
        source="log_analyzer",
    )
    return Signal(**{**defaults, **overrides})


def make_hypothesis(**overrides) -> Hypothesis:
    defaults = dict(
        label="DB Connection Pool Exhaustion",
        description="Pool saturated under load",
        confidence=0.85,
        severity="high",
        supporting_signals=["sig_001"],
        contributing_agent="metrics_agent",
    )
    return Hypothesis(**{**defaults, **overrides})


# ── Signal ────────────────────────────────────────────────────────────────────

class TestSignal:
    def test_valid_signal_no_value(self):
        s = make_signal()
        assert s.id == "sig_001"
        assert s.value is None

    def test_valid_signal_with_numeric_value(self):
        s = make_signal(id="sig_002", type="metric_spike", value=4800.0)
        assert s.value == 4800.0

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            Signal(id="sig_001", type="log_anomaly", description="test")  # missing severity, source

    def test_all_fields_stored_correctly(self):
        s = make_signal(id="sig_003", type="resource_saturation", value=1.0, severity="high", source="metrics_analyzer")
        assert s.id == "sig_003"
        assert s.type == "resource_saturation"
        assert s.value == 1.0
        assert s.source == "metrics_analyzer"


# ── Hypothesis ────────────────────────────────────────────────────────────────

class TestHypothesis:
    def test_valid_hypothesis(self):
        h = make_hypothesis()
        assert h.label == "DB Connection Pool Exhaustion"
        assert h.confidence == 0.85

    def test_confidence_at_zero(self):
        h = make_hypothesis(confidence=0.0)
        assert h.confidence == 0.0

    def test_confidence_at_one(self):
        h = make_hypothesis(confidence=1.0)
        assert h.confidence == 1.0

    def test_confidence_above_one_raises(self):
        with pytest.raises(ValidationError):
            make_hypothesis(confidence=1.1)

    def test_confidence_below_zero_raises(self):
        with pytest.raises(ValidationError):
            make_hypothesis(confidence=-0.1)

    def test_multiple_supporting_signals(self):
        h = make_hypothesis(supporting_signals=["sig_001", "sig_002", "sig_003"])
        assert len(h.supporting_signals) == 3

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            Hypothesis(label="test", confidence=0.5)  # missing most fields


# ── IncidentInput ─────────────────────────────────────────────────────────────

class TestIncidentInput:
    def test_valid_incident(self):
        incident = IncidentInput(
            deployment_id="deploy-2024-11-15-v2.3.1",
            logs=["ERROR timeout", "ERROR DB pool exhausted"],
            metrics={"latency_p99_ms": 4800, "error_rate": 0.31},
            recent_commits=[{"sha": "a1b2c3d", "message": "Refactor user profile endpoint"}],
            config_snapshot={"MAX_DB_CONNECTIONS": 5},
        )
        assert incident.deployment_id == "deploy-2024-11-15-v2.3.1"
        assert len(incident.logs) == 2

    def test_empty_collections_are_valid(self):
        incident = IncidentInput(
            deployment_id="deploy-001",
            logs=[],
            metrics={},
            recent_commits=[],
            config_snapshot={},
        )
        assert incident.logs == []

    def test_missing_deployment_id_raises(self):
        with pytest.raises(ValidationError):
            IncidentInput(logs=[], metrics={}, recent_commits=[], config_snapshot={})


# ── AgentResult ───────────────────────────────────────────────────────────────

class TestAgentResult:
    def test_valid_result_with_hypotheses(self):
        result = AgentResult(
            agent_name="log_agent",
            hypotheses=[make_hypothesis()],
            execution_time_ms=142.7,
        )
        assert result.agent_name == "log_agent"
        assert len(result.hypotheses) == 1

    def test_valid_result_with_no_hypotheses(self):
        result = AgentResult(agent_name="config_agent", hypotheses=[], execution_time_ms=98.0)
        assert result.hypotheses == []

    def test_missing_agent_name_raises(self):
        with pytest.raises(ValidationError):
            AgentResult(hypotheses=[], execution_time_ms=0.0)


# ── ExecutionResult ───────────────────────────────────────────────────────────

class TestExecutionResult:
    def test_execution_id_auto_generated(self):
        result = ExecutionResult(ranked_hypotheses=[], signals_used=[], requires_human_review=False)
        assert result.execution_id is not None
        assert len(result.execution_id) > 0

    def test_each_instance_gets_unique_execution_id(self):
        r1 = ExecutionResult(ranked_hypotheses=[], signals_used=[], requires_human_review=False)
        r2 = ExecutionResult(ranked_hypotheses=[], signals_used=[], requires_human_review=False)
        assert r1.execution_id != r2.execution_id

    def test_execution_id_is_valid_uuid(self):
        result = ExecutionResult(ranked_hypotheses=[], signals_used=[], requires_human_review=False)
        parsed = uuid.UUID(result.execution_id)  # raises ValueError if invalid
        assert str(parsed) == result.execution_id

    def test_requires_human_review_flag(self):
        result = ExecutionResult(ranked_hypotheses=[], signals_used=[], requires_human_review=True)
        assert result.requires_human_review is True

    def test_synthesis_field_accepts_schema(self):
        result = ExecutionResult(
            ranked_hypotheses=[],
            signals_used=[],
            synthesis=SynthesisResult(
                summary="Investigation summary.",
                key_finding="Top finding.",
                confidence_in_ranking=0.75,
            ),
            requires_human_review=False,
        )
        assert result.synthesis is not None
        assert result.synthesis.confidence_in_ranking == 0.75


class TestSynthesisResult:
    def test_valid_synthesis_result(self):
        synthesis = SynthesisResult(
            summary="Two-sentence summary.",
            key_finding="Most likely root cause.",
            confidence_in_ranking=0.91,
        )
        assert synthesis.key_finding == "Most likely root cause."

    def test_confidence_above_one_raises(self):
        with pytest.raises(ValidationError):
            SynthesisResult(
                summary="Summary.",
                key_finding="Finding.",
                confidence_in_ranking=1.1,
            )


# ── AgentEvent ────────────────────────────────────────────────────────────────

class TestAgentEvent:
    def test_valid_event(self):
        event = AgentEvent(
            agent_name="log_agent",
            event_type=EventType.STARTED,
            message="analyzing error patterns...",
            timestamp_ms=0.0,
        )
        assert event.agent_name == "log_agent"
        assert event.event_type == EventType.STARTED

    def test_event_type_values_are_strings(self):
        assert EventType.STARTED == "started"
        assert EventType.SIGNAL_DETECTED == "signal_detected"
        assert EventType.COMPLETE == "complete"
        assert EventType.ERROR == "error"

    def test_all_event_types_accepted(self):
        for event_type in EventType:
            event = AgentEvent(
                agent_name="test_agent",
                event_type=event_type,
                message="test",
                timestamp_ms=1.0,
            )
            assert event.event_type == event_type

    def test_invalid_event_type_raises(self):
        with pytest.raises(ValidationError):
            AgentEvent(agent_name="test", event_type="unknown", message="test", timestamp_ms=0.0)
