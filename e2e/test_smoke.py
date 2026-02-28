from schemas.signal import Signal


def test_signal_schema_smoke() -> None:
    signal = Signal(
        id="sig_001",
        type="metric_spike",
        description="p99 latency increased from baseline",
        value=4.0,
        severity="high",
        source="metrics_analyzer",
    )
    assert signal.id == "sig_001"
    assert signal.value == 4.0
