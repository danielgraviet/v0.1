"""Config analyzer — deterministic signal extraction from config snapshots.

Detects:
- Numeric limits that were reduced vs a known-safe baseline
- Feature flags newly enabled (new code paths activated)

When no baseline is provided the analyzer uses heuristics: any numeric
config key whose name contains a capacity/limit keyword and whose value
looks low is flagged.

No LLM involved. Same input always produces the same output.
"""

import re

from schemas.signal import Signal

# Config key name fragments that suggest a capacity or rate limit.
_LIMIT_KEYWORDS = re.compile(
    r"(max|limit|pool|size|connections|workers|threads|concurren|rate|ttl|timeout)",
    re.IGNORECASE,
)


class ConfigAnalyzer:
    """Extract signals from the incident config snapshot."""

    def analyze(
        self,
        config: dict,
        baseline_config: dict | None = None,
    ) -> list[Signal]:
        """Scan config and return detected signals.

        Args:
            config: Current config snapshot from the incident payload.
            baseline_config: Optional known-good config to compare against.
                When provided, the analyzer emits a signal for every numeric
                key whose value decreased. When absent, heuristics are used.

        Returns:
            List of Signal objects with placeholder IDs.
        """
        signals: list[Signal] = []

        signals.extend(self._check_numeric_limits(config, baseline_config))
        signals.extend(self._check_feature_flags(config, baseline_config))

        return signals

    # ── Private ───────────────────────────────────────────────────────────────

    def _check_numeric_limits(
        self, config: dict, baseline: dict | None
    ) -> list[Signal]:
        signals = []

        for key, value in config.items():
            if not isinstance(value, (int, float)):
                continue
            if not _LIMIT_KEYWORDS.search(key):
                continue

            if baseline is not None:
                baseline_value = baseline.get(key)
                if isinstance(baseline_value, (int, float)) and value < baseline_value:
                    signals.append(Signal(
                        id="placeholder",
                        type="config_change",
                        description=(
                            f"Config '{key}' reduced from {baseline_value} to {value}"
                        ),
                        value=float(value),
                        severity="high" if value / baseline_value < 0.5 else "medium",
                        source="config_analyzer",
                    ))
            else:
                # Heuristic: flag suspiciously low values for known limit keys
                if value == 0 or (isinstance(value, int) and value <= 5
                                  and "connection" in key.lower()):
                    signals.append(Signal(
                        id="placeholder",
                        type="config_change",
                        description=(
                            f"Config '{key}' is set to {value} — "
                            f"unusually low for a limit/capacity setting"
                        ),
                        value=float(value),
                        severity="medium",
                        source="config_analyzer",
                    ))

        return signals

    def _check_feature_flags(
        self, config: dict, baseline: dict | None
    ) -> list[Signal]:
        signals = []

        flags = config.get("FEATURE_FLAGS", {})
        baseline_flags = (baseline or {}).get("FEATURE_FLAGS", {})

        for flag, enabled in flags.items():
            if enabled is True:
                was_enabled = baseline_flags.get(flag, False)
                if not was_enabled:
                    signals.append(Signal(
                        id="placeholder",
                        type="config_change",
                        description=f"Feature flag '{flag}' newly enabled",
                        value=None,
                        severity="medium",
                        source="config_analyzer",
                    ))

        return signals
