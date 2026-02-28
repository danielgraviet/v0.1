"""Signal schema.

Signals are deterministic facts extracted from an incident payload before
any agent runs. They represent verified observations, not interpretations.
Agents reason over signals — they never create or modify them.
"""

from pydantic import BaseModel


class Signal(BaseModel):
    """A single verified fact extracted from an incident.

    Signals are produced by the signal extraction layer (Phase 3) and stored
    in StructuredMemory. Agents receive the signal list as their input context.
    The judge cross-references hypothesis citations against this list.

    Attributes:
        id: Unique identifier assigned sequentially by SignalExtractor
            (e.g. "sig_001", "sig_002"). Used by hypotheses to cite evidence.
        type: Category of signal. Known types: "log_anomaly", "metric_spike",
            "resource_saturation", "metric_degradation", "commit_change",
            "config_change".
        description: Human-readable description of what was observed
            (e.g. "DB connection pool 100% saturated (5/5 used)").
        value: Optional numeric measurement. None for qualitative signals
            such as code or config changes that have no meaningful scalar.
        severity: Impact level — "low", "medium", or "high".
        source: Name of the extractor that produced this signal
            (e.g. "metrics_analyzer", "log_analyzer").
    """

    id: str
    type: str
    description: str
    value: float | None = None
    severity: str
    source: str
