"""Signal layer tests.

Covers LogAnalyzer, MetricsAnalyzer, CommitAnalyzer, ConfigAnalyzer,
and SignalExtractor. No LLM calls, no API keys — all deterministic.

TestLogAnalyzer     — error rate spike, dominant error type, new signatures
TestMetricsAnalyzer — latency spike, DB saturation, cache degradation
TestCommitAnalyzer  — cache removal, unindexed query, pool reduction
TestConfigAnalyzer  — reduced limits, new feature flags
TestSignalExtractor — orchestration, sequential IDs, analyzer fault isolation
"""

import pytest

from schemas.incident import IncidentInput
from schemas.signal import Signal
from signals.commit_analyzer import CommitAnalyzer
from signals.config_analyzer import ConfigAnalyzer
from signals.log_analyzer import LogAnalyzer
from signals.metrics_analyzer import MetricsAnalyzer
from signals.signal_extractor import SignalExtractor


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ids(signals: list[Signal]) -> list[str]:
    return [s.id for s in signals]

def _types(signals: list[Signal]) -> list[str]:
    return [s.type for s in signals]

def _find(signals: list[Signal], type_: str) -> Signal | None:
    return next((s for s in signals if s.type == type_), None)


# ── LogAnalyzer ───────────────────────────────────────────────────────────────

class TestLogAnalyzer:
    def test_empty_logs_returns_no_signals(self):
        assert LogAnalyzer().analyze([]) == []

    def test_all_info_logs_returns_no_signals(self):
        logs = ["INFO  GET /api/users 200 45ms"] * 20
        assert LogAnalyzer().analyze(logs) == []

    def test_high_error_rate_emits_log_anomaly(self):
        # 15 errors out of 20 = 75% — well above the 10% threshold
        logs = ["ERROR GET /api/users 500 timeout after 5000ms"] * 15
        logs += ["INFO  GET /api/users 200 45ms"] * 5
        signals = LogAnalyzer().analyze(logs)
        types = _types(signals)
        assert "log_anomaly" in types

    def test_low_error_rate_below_threshold_no_spike(self):
        # 1 error out of 20 = 5% — below the 10% threshold
        logs = ["ERROR GET /api/users 500 timeout"] * 1
        logs += ["INFO  GET /api/users 200 45ms"] * 19
        signals = LogAnalyzer().analyze(logs)
        # No error rate signal — though dominant error may still appear if count >= 3
        spike_signals = [s for s in signals if s.value is not None and s.value > 1]
        assert len(spike_signals) == 0

    def test_error_rate_signal_value_is_ratio_over_baseline(self):
        # 20 errors / 20 total = 100% error rate; baseline 1% → ratio = 100
        logs = ["ERROR GET /api/users 500 timeout after 5000ms"] * 20
        signals = LogAnalyzer().analyze(logs)
        spike = next(s for s in signals if s.value is not None and s.value > 1)
        assert spike.value == pytest.approx(100.0, rel=0.05)
        assert spike.severity == "high"

    def test_dominant_error_type_emitted_when_repeated(self):
        # Same error message repeated 10 times
        logs = ["ERROR DB connection pool exhausted"] * 10
        logs += ["INFO  GET /api/users 200 45ms"] * 5
        signals = LogAnalyzer().analyze(logs)
        descs = [s.description for s in signals]
        assert any("DB connection pool exhausted" in d for d in descs)

    def test_new_error_signature_detected_in_later_logs(self):
        # First 20% of logs: no errors
        # Last 80%: a new error pattern that wasn't in the early window
        early = ["INFO  GET /api/users 200 45ms"] * 5
        late  = ["INFO  GET /api/users 200 45ms"] * 5
        late += ["ERROR DB connection pool exhausted"] * 8
        signals = LogAnalyzer().analyze(early + late)
        descs = [s.description for s in signals]
        assert any("New error pattern" in d for d in descs)

    def test_all_signals_have_required_fields(self):
        logs = ["ERROR GET /api/users 500 timeout after 5000ms"] * 15
        logs += ["INFO  GET /api/users 200 45ms"] * 5
        for signal in LogAnalyzer().analyze(logs):
            assert signal.type
            assert signal.description
            assert signal.severity in ("low", "medium", "high")
            assert signal.source == "log_analyzer"


# ── MetricsAnalyzer ───────────────────────────────────────────────────────────

class TestMetricsAnalyzer:
    def test_empty_metrics_returns_no_signals(self):
        assert MetricsAnalyzer().analyze({}) == []

    def test_latency_spike_emitted_when_p99_exceeds_2x_baseline(self):
        metrics = {"latency_p99_ms": 4800, "latency_baseline_p99_ms": 120}
        signals = MetricsAnalyzer().analyze(metrics)
        spike = _find(signals, "metric_spike")
        assert spike is not None
        assert spike.value == pytest.approx(40.0, rel=0.1)
        assert spike.severity == "high"

    def test_latency_spike_not_emitted_below_threshold(self):
        # p99 only 1.5x baseline — below the 2x threshold
        metrics = {"latency_p99_ms": 180, "latency_baseline_p99_ms": 120}
        signals = MetricsAnalyzer().analyze(metrics)
        assert _find(signals, "metric_spike") is None

    def test_latency_spike_skipped_when_baseline_missing(self):
        metrics = {"latency_p99_ms": 4800}
        signals = MetricsAnalyzer().analyze(metrics)
        assert _find(signals, "metric_spike") is None

    def test_db_saturation_emitted_at_100_percent(self):
        metrics = {"db_connection_pool_used": 5, "db_connection_pool_max": 5}
        signals = MetricsAnalyzer().analyze(metrics)
        sat = _find(signals, "resource_saturation")
        assert sat is not None
        assert sat.value == pytest.approx(1.0)
        assert sat.severity == "high"

    def test_db_saturation_emitted_at_90_percent_threshold(self):
        metrics = {"db_connection_pool_used": 9, "db_connection_pool_max": 10}
        signals = MetricsAnalyzer().analyze(metrics)
        assert _find(signals, "resource_saturation") is not None

    def test_db_saturation_not_emitted_below_threshold(self):
        metrics = {"db_connection_pool_used": 4, "db_connection_pool_max": 10}
        signals = MetricsAnalyzer().analyze(metrics)
        assert _find(signals, "resource_saturation") is None

    def test_cache_degradation_emitted_when_hit_rate_drops(self):
        metrics = {"cache_hit_rate": 0.08, "cache_hit_rate_baseline": 0.82}
        signals = MetricsAnalyzer().analyze(metrics)
        deg = _find(signals, "metric_degradation")
        assert deg is not None
        assert deg.severity == "high"   # 0.08 < 0.20 threshold

    def test_cache_degradation_emitted_on_absolute_low_even_without_baseline(self):
        # 20% hit rate with no baseline — still below 50% absolute threshold
        metrics = {"cache_hit_rate": 0.20}
        signals = MetricsAnalyzer().analyze(metrics)
        assert _find(signals, "metric_degradation") is not None

    def test_healthy_cache_not_flagged(self):
        metrics = {"cache_hit_rate": 0.85, "cache_hit_rate_baseline": 0.82}
        signals = MetricsAnalyzer().analyze(metrics)
        assert _find(signals, "metric_degradation") is None

    def test_zero_cache_baseline_does_not_crash_and_uses_absolute_threshold(self):
        metrics = {"cache_hit_rate": 0.20, "cache_hit_rate_baseline": 0.0}
        signals = MetricsAnalyzer().analyze(metrics)
        deg = _find(signals, "metric_degradation")
        assert deg is not None
        assert "below healthy threshold" in deg.description

    def test_all_three_signals_produced_from_full_incident_b_metrics(self):
        metrics = {
            "latency_p99_ms": 4800,
            "latency_baseline_p99_ms": 120,
            "db_connection_pool_used": 5,
            "db_connection_pool_max": 5,
            "cache_hit_rate": 0.08,
            "cache_hit_rate_baseline": 0.82,
        }
        signals = MetricsAnalyzer().analyze(metrics)
        types = _types(signals)
        assert "metric_spike" in types
        assert "resource_saturation" in types
        assert "metric_degradation" in types


# ── CommitAnalyzer ────────────────────────────────────────────────────────────

class TestCommitAnalyzer:
    def test_empty_commits_returns_no_signals(self):
        assert CommitAnalyzer().analyze([]) == []

    def test_cache_removal_detected_from_diff_summary(self):
        commits = [{"sha": "abc123", "message": "perf", "diff_summary": "Removed @cache decorator from get_user_profile()"}]
        signals = CommitAnalyzer().analyze(commits)
        assert any("Cache decorator removed" in s.description for s in signals)

    def test_cache_removal_detected_from_message(self):
        commits = [{"sha": "abc123", "message": "Remove cache from endpoint", "diff_summary": ""}]
        signals = CommitAnalyzer().analyze(commits)
        assert any("Cache decorator removed" in s.description for s in signals)

    def test_unindexed_query_detected(self):
        commits = [{"sha": "abc123", "message": "add query", "diff_summary": "Added SELECT * FROM users JOIN orders WHERE user_id = ?"}]
        signals = CommitAnalyzer().analyze(commits)
        assert any("unindexed query" in s.description for s in signals)

    def test_pool_reduction_detected_with_numeric_values(self):
        commits = [{"sha": "e4f5g6h", "message": "reduce pool", "diff_summary": "Changed MAX_DB_CONNECTIONS from 20 to 5 in config.py"}]
        signals = CommitAnalyzer().analyze(commits)
        pool_sig = next((s for s in signals if "pool reduced" in s.description), None)
        assert pool_sig is not None
        assert pool_sig.severity == "high"
        assert pool_sig.value == 5.0

    def test_pool_increase_not_flagged(self):
        # Pool going up is not a risk signal
        commits = [{"sha": "abc", "message": "scale up", "diff_summary": "Changed MAX_DB_CONNECTIONS from 5 to 20"}]
        signals = CommitAnalyzer().analyze(commits)
        assert not any("pool reduced" in s.description for s in signals)

    def test_sha_included_in_signal_description(self):
        commits = [{"sha": "deadbeef", "message": "Remove cache", "diff_summary": "Removed @cache decorator"}]
        signals = CommitAnalyzer().analyze(commits)
        assert any("deadbeef" in s.description for s in signals)

    def test_multiple_issues_in_one_commit_emit_multiple_signals(self):
        commits = [{
            "sha": "abc123",
            "message": "mixed changes",
            "diff_summary": (
                "Removed @cache decorator. "
                "Added SELECT * FROM users JOIN orders. "
                "Changed MAX_DB_CONNECTIONS from 20 to 5."
            ),
        }]
        signals = CommitAnalyzer().analyze(commits)
        assert len(signals) >= 3

    def test_benign_commit_emits_no_signals(self):
        commits = [{"sha": "abc123", "message": "fix typo in README", "diff_summary": "Updated README.md"}]
        signals = CommitAnalyzer().analyze(commits)
        assert signals == []


# ── ConfigAnalyzer ────────────────────────────────────────────────────────────

class TestConfigAnalyzer:
    def test_empty_config_returns_no_signals(self):
        assert ConfigAnalyzer().analyze({}) == []

    def test_reduced_limit_flagged_when_baseline_provided(self):
        config   = {"MAX_DB_CONNECTIONS": 5}
        baseline = {"MAX_DB_CONNECTIONS": 20}
        signals = ConfigAnalyzer().analyze(config, baseline)
        assert any("MAX_DB_CONNECTIONS" in s.description for s in signals)

    def test_increased_limit_not_flagged(self):
        config   = {"MAX_DB_CONNECTIONS": 20}
        baseline = {"MAX_DB_CONNECTIONS": 5}
        signals = ConfigAnalyzer().analyze(config, baseline)
        assert signals == []

    def test_heuristic_flags_zero_value_without_baseline(self):
        config = {"CACHE_TTL_SECONDS": 0}
        signals = ConfigAnalyzer().analyze(config)
        assert any("CACHE_TTL_SECONDS" in s.description for s in signals)

    def test_new_feature_flag_enabled_emits_signal(self):
        config   = {"FEATURE_FLAGS": {"new_query_engine": True}}
        baseline = {"FEATURE_FLAGS": {"new_query_engine": False}}
        signals = ConfigAnalyzer().analyze(config, baseline)
        assert any("new_query_engine" in s.description for s in signals)

    def test_unchanged_feature_flag_not_flagged(self):
        config   = {"FEATURE_FLAGS": {"new_query_engine": True}}
        baseline = {"FEATURE_FLAGS": {"new_query_engine": True}}
        signals = ConfigAnalyzer().analyze(config, baseline)
        assert signals == []

    def test_severity_high_when_limit_cut_more_than_half(self):
        # 5 is less than 50% of 20 → should be high severity
        config   = {"MAX_DB_CONNECTIONS": 5}
        baseline = {"MAX_DB_CONNECTIONS": 20}
        signals = ConfigAnalyzer().analyze(config, baseline)
        assert signals[0].severity == "high"


# ── SignalExtractor ───────────────────────────────────────────────────────────

class TestSignalExtractor:
    @pytest.fixture
    def incident_b(self):
        return IncidentInput(
            deployment_id="deploy-test",
            logs=(
                ["ERROR GET /api/users 500 timeout after 5000ms"] * 20
                + ["INFO  GET /api/users 200 45ms"] * 10
            ),
            metrics={
                "latency_p99_ms": 4800,
                "latency_baseline_p99_ms": 120,
                "db_connection_pool_used": 5,
                "db_connection_pool_max": 5,
                "cache_hit_rate": 0.08,
                "cache_hit_rate_baseline": 0.82,
            },
            recent_commits=[
                {
                    "sha": "a1b2c3d",
                    "message": "Remove cache",
                    "diff_summary": "Removed @cache decorator. Added SELECT * FROM users JOIN orders.",
                },
                {
                    "sha": "e4f5g6h",
                    "message": "Reduce pool",
                    "diff_summary": "Changed MAX_DB_CONNECTIONS from 20 to 5",
                },
            ],
            config_snapshot={"MAX_DB_CONNECTIONS": 5, "CACHE_TTL_SECONDS": 0},
        )

    def test_produces_at_least_six_signals(self, incident_b):
        signals = SignalExtractor().extract(incident_b)
        assert len(signals) >= 6

    def test_all_signal_ids_are_sequential(self, incident_b):
        signals = SignalExtractor().extract(incident_b)
        for i, signal in enumerate(signals, start=1):
            assert signal.id == f"sig_{i:03d}"

    def test_all_signal_ids_are_unique(self, incident_b):
        signals = SignalExtractor().extract(incident_b)
        ids = _ids(signals)
        assert len(ids) == len(set(ids))

    def test_covers_all_signal_types(self, incident_b):
        signals = SignalExtractor().extract(incident_b)
        types = set(_types(signals))
        assert "log_anomaly" in types
        assert "metric_spike" in types
        assert "resource_saturation" in types
        assert "metric_degradation" in types
        assert "commit_change" in types

    def test_all_signals_have_required_fields(self, incident_b):
        for signal in SignalExtractor().extract(incident_b):
            assert signal.id.startswith("sig_")
            assert signal.type
            assert signal.description
            assert signal.severity in ("low", "medium", "high")
            assert signal.source

    def test_empty_incident_returns_no_signals(self):
        incident = IncidentInput(
            deployment_id="empty",
            logs=[],
            metrics={},
            recent_commits=[],
            config_snapshot={},
        )
        signals = SignalExtractor().extract(incident)
        assert signals == []

    def test_analyzer_failure_does_not_halt_extraction(self, monkeypatch):
        """If one analyzer raises, the others still run."""
        from signals import log_analyzer
        monkeypatch.setattr(
            log_analyzer.LogAnalyzer,
            "analyze",
            lambda self, logs: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        incident = IncidentInput(
            deployment_id="fault-test",
            logs=["ERROR something"] * 5,
            metrics={"latency_p99_ms": 4800, "latency_baseline_p99_ms": 120},
            recent_commits=[],
            config_snapshot={},
        )
        # Should not raise — LogAnalyzer failure is caught, MetricsAnalyzer still runs
        signals = SignalExtractor().extract(incident)
        assert any(s.source == "metrics_analyzer" for s in signals)
