"""Metrics analyzer — deterministic signal extraction from metrics dict.

Detects:
- Latency spike: p99 > 2x baseline
- DB connection pool saturation: used/max >= 90%
- Cache hit rate degradation: hit rate < 50% of baseline

No LLM involved. Same input always produces the same output.
"""

from schemas.signal import Signal


class MetricsAnalyzer:
    """Extract signals from the incident metrics dictionary."""

    LATENCY_SPIKE_MULTIPLIER = 2.0    # p99 must exceed this multiple of baseline
    POOL_SATURATION_THRESHOLD = 0.90  # used/max ratio that counts as saturated
    CACHE_DEGRADATION_THRESHOLD = 0.50  # hit rate must drop below this fraction of baseline

    def analyze(self, metrics: dict) -> list[Signal]:
        """Scan metrics and return a list of detected signals.

        Args:
            metrics: The metrics dict from the incident payload. Expected keys
                are documented in schemas/incident.py. Missing keys are
                silently skipped — the analyzer emits only what it can compute.

        Returns:
            List of Signal objects with placeholder IDs.
        """
        signals: list[Signal] = []

        signals.extend(self._check_latency(metrics))
        signals.extend(self._check_db_pool(metrics))
        signals.extend(self._check_cache(metrics))

        return signals

    # ── Private ───────────────────────────────────────────────────────────────

    def _check_latency(self, m: dict) -> list[Signal]:
        p99      = m.get("latency_p99_ms")
        baseline = m.get("latency_baseline_p99_ms")
        if p99 is None or baseline is None or baseline == 0:
            return []

        ratio = p99 / baseline
        if ratio < self.LATENCY_SPIKE_MULTIPLIER:
            return []

        return [Signal(
            id="placeholder",
            type="metric_spike",
            description=(
                f"p99 latency {p99}ms vs baseline {baseline}ms "
                f"({ratio:.0f}x spike)"
            ),
            value=round(ratio, 1),
            severity="high" if ratio >= 5 else "medium",
            source="metrics_analyzer",
        )]

    def _check_db_pool(self, m: dict) -> list[Signal]:
        used = m.get("db_connection_pool_used")
        total = m.get("db_connection_pool_max")
        if used is None or total is None or total == 0:
            return []

        saturation = used / total
        if saturation < self.POOL_SATURATION_THRESHOLD:
            return []

        return [Signal(
            id="placeholder",
            type="resource_saturation",
            description=(
                f"DB connection pool {saturation:.0%} saturated "
                f"({used}/{total} connections used)"
            ),
            value=round(saturation, 3),
            severity="high",
            source="metrics_analyzer",
        )]

    def _check_cache(self, m: dict) -> list[Signal]:
        hit_rate = m.get("cache_hit_rate")
        baseline = m.get("cache_hit_rate_baseline")
        if hit_rate is None:
            return []

        # Absolute threshold: below 50% is always notable
        absolute_bad = hit_rate < 0.50

        # Relative threshold: dropped more than 50% from baseline
        relative_bad = (
            baseline is not None
            and baseline > 0
            and hit_rate < baseline * self.CACHE_DEGRADATION_THRESHOLD
        )

        if not (absolute_bad or relative_bad):
            return []

        if baseline is not None:
            desc = (
                f"Cache hit rate dropped from {baseline:.0%} to {hit_rate:.0%} "
                f"({(baseline - hit_rate) / baseline:.0%} degradation)"
            )
        else:
            desc = f"Cache hit rate is {hit_rate:.0%} — below healthy threshold"

        return [Signal(
            id="placeholder",
            type="metric_degradation",
            description=desc,
            value=round(hit_rate, 3),
            severity="high" if hit_rate < 0.20 else "medium",
            source="metrics_analyzer",
        )]
