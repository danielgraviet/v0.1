"""Log analyzer — deterministic signal extraction from log lines.

Scans raw log lines and emits Signal objects for:
- Error rate spikes (ERROR count vs total)
- Dominant error type (most frequent error message prefix)
- New error signatures (patterns in the last 80% of logs absent from first 20%)

No LLM involved. Same input always produces the same output.
"""

import re
from collections import Counter

from schemas.signal import Signal


class LogAnalyzer:
    """Extract signals from a list of raw log lines."""

    ERROR_RATE_THRESHOLD = 0.10       # emit if > 10% of lines are errors
    ERROR_RATE_BASELINE = 0.01        # assumed baseline when not in metrics

    def analyze(self, logs: list[str]) -> list[Signal]:
        """Scan logs and return a list of detected signals.

        Args:
            logs: Raw log lines from the incident payload.

        Returns:
            List of Signal objects (IDs are placeholders — SignalExtractor
            assigns final sequential IDs before returning to the runtime).
        """
        if not logs:
            return []

        signals: list[Signal] = []

        error_lines = [l for l in logs if l.startswith("ERROR")]
        total = len(logs)
        error_rate = len(error_lines) / total

        # ── Error rate spike ──────────────────────────────────────────────────
        if error_rate > self.ERROR_RATE_THRESHOLD:
            ratio = round(error_rate / self.ERROR_RATE_BASELINE, 1)
            signals.append(Signal(
                id="placeholder",
                type="log_anomaly",
                description=(
                    f"Error rate is {error_rate:.0%} — "
                    f"{ratio}x above baseline of {self.ERROR_RATE_BASELINE:.0%}"
                ),
                value=ratio,
                severity="high" if ratio >= 2 else "medium",
                source="log_analyzer",
            ))

        # ── Dominant error type ───────────────────────────────────────────────
        if error_lines:
            prefixes = [self._error_prefix(l) for l in error_lines]
            most_common, count = Counter(prefixes).most_common(1)[0]
            if count >= 3:
                signals.append(Signal(
                    id="placeholder",
                    type="log_anomaly",
                    description=(
                        f"Dominant error: '{most_common}' "
                        f"({count} occurrences, {count / total:.0%} of all logs)"
                    ),
                    value=float(count),
                    severity="high" if count / total > 0.15 else "medium",
                    source="log_analyzer",
                ))

        # ── New error signatures ──────────────────────────────────────────────
        split = max(1, total // 5)           # first 20% vs last 80%
        early_errors = {self._error_prefix(l) for l in logs[:split] if l.startswith("ERROR")}
        late_errors  = {self._error_prefix(l) for l in logs[split:] if l.startswith("ERROR")}
        new_sigs = late_errors - early_errors

        for sig in sorted(new_sigs):
            signals.append(Signal(
                id="placeholder",
                type="log_anomaly",
                description=f"New error pattern appeared after deploy: '{sig}'",
                value=None,
                severity="medium",
                source="log_analyzer",
            ))

        return signals

    # ── Private ───────────────────────────────────────────────────────────────

    def _error_prefix(self, line: str) -> str:
        """Return a short prefix that identifies the error type.

        Strips timestamps, request IDs, and numeric values so that
        'ERROR DB connection pool exhausted — waited 5000ms' and
        'ERROR DB connection pool exhausted — waited 3000ms' hash to the
        same bucket.
        """
        # Remove leading level tag
        line = re.sub(r"^(ERROR|WARN|INFO)\s+", "", line)
        # Remove numeric values (ms durations, status codes, counts)
        line = re.sub(r"\b\d+\b", "N", line)
        # Truncate to first ~60 chars for a stable prefix
        return line[:60].strip()
