"""Signal extractor — orchestrates all analyzers into a single signal list.

This is the only class the runtime calls. It:
1. Runs all four analyzers against the incident payload
2. Collects their raw Signal objects (all with placeholder IDs)
3. Assigns final sequential IDs: sig_001, sig_002, ...
4. Returns the complete, ID-stable signal list

ID assignment happens here — not inside individual analyzers — so each
analyzer can be tested in isolation without needing to know its position
in the global sequence.
"""

import logging

from schemas.incident import IncidentInput
from schemas.signal import Signal
from signals.commit_analyzer import CommitAnalyzer
from signals.config_analyzer import ConfigAnalyzer
from signals.log_analyzer import LogAnalyzer
from signals.metrics_analyzer import MetricsAnalyzer

logger = logging.getLogger(__name__)


class SignalExtractor:
    """Orchestrates all analyzers and returns a stable, ID-assigned signal list."""

    def extract(self, incident: IncidentInput) -> list[Signal]:
        """Run all analyzers against the incident and return labelled signals.

        Each analyzer runs independently. If one raises, the error is logged
        and extraction continues with the remaining analyzers — partial signals
        are better than no signals.

        Args:
            incident: The validated IncidentInput for this execution.

        Returns:
            List of Signal objects with sequential IDs (sig_001, sig_002, ...).
        """
        raw: list[Signal] = []

        raw.extend(self._run(LogAnalyzer().analyze, incident.logs, "LogAnalyzer"))
        raw.extend(self._run(MetricsAnalyzer().analyze, incident.metrics, "MetricsAnalyzer"))
        raw.extend(self._run(CommitAnalyzer().analyze, incident.recent_commits, "CommitAnalyzer"))
        raw.extend(self._run(
            lambda cfg: ConfigAnalyzer().analyze(cfg),
            incident.config_snapshot,
            "ConfigAnalyzer",
        ))

        # Assign sequential IDs now that all analyzers have run
        for i, signal in enumerate(raw, start=1):
            signal.id = f"sig_{i:03d}"

        logger.debug("SignalExtractor produced %d signals.", len(raw))
        return raw

    # ── Private ───────────────────────────────────────────────────────────────

    def _run(self, fn, arg, name: str) -> list[Signal]:
        """Call an analyzer function, catching and logging any exception."""
        try:
            return fn(arg)
        except Exception as exc:
            logger.error("Analyzer %s failed — skipping. Error: %s", name, exc)
            return []
