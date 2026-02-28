"""Commit analyzer — deterministic signal extraction from recent commits.

Scans commit diff summaries for high-risk patterns:
- Cache decorator removed
- Potentially unindexed query added
- DB connection pool size reduced

No LLM involved. Pattern matching only — same input, same output.
"""

import re

from schemas.signal import Signal


class CommitAnalyzer:
    """Extract signals from a list of commit dicts."""

    # Patterns that suggest a cache was removed
    _CACHE_REMOVAL_PATTERNS = [
        r"removed?\s+@?cache",
        r"cache\s+decorator\s+removed",
        r"cache\s*=\s*False",
        r"no.?cache",
        r"disable[d]?\s+cach",
        r"CACHE_TTL\s*=\s*0",
    ]

    # Patterns that suggest a potentially unindexed query was added
    _UNINDEXED_QUERY_PATTERNS = [
        r"SELECT\s+\*\s+FROM\s+\w+\s+JOIN",
        r"JOIN\b(?!.*\bINDEX\b)",
        r"without\s+index",
        r"no\s+index\s+hint",
        r"full\s+table\s+scan",
    ]

    # Patterns that suggest the DB pool size was reduced
    _POOL_REDUCTION_PATTERNS = [
        r"MAX_DB_CONNECTIONS\s+from\s+(\d+)\s+to\s+(\d+)",
        r"pool_size\s+from\s+(\d+)\s+to\s+(\d+)",
        r"MAX_CONNECTIONS\s+from\s+(\d+)\s+to\s+(\d+)",
        r"DB_POOL_SIZE\s+from\s+(\d+)\s+to\s+(\d+)",
    ]

    def analyze(self, commits: list[dict]) -> list[Signal]:
        """Scan commit diffs and return detected signals.

        Args:
            commits: List of commit dicts. Each dict should have at least
                'sha', 'message', and 'diff_summary' keys.

        Returns:
            List of Signal objects with placeholder IDs.
        """
        signals: list[Signal] = []

        for commit in commits:
            sha = commit.get("sha", "unknown")
            diff = commit.get("diff_summary", "") + " " + commit.get("message", "")

            signals.extend(self._check_cache_removal(diff, sha))
            signals.extend(self._check_unindexed_query(diff, sha))
            signals.extend(self._check_pool_reduction(diff, sha))

        return signals

    # ── Private ───────────────────────────────────────────────────────────────

    def _check_cache_removal(self, diff: str, sha: str) -> list[Signal]:
        for pattern in self._CACHE_REMOVAL_PATTERNS:
            if re.search(pattern, diff, re.IGNORECASE):
                return [Signal(
                    id="placeholder",
                    type="commit_change",
                    description=f"Cache decorator removed in commit {sha}",
                    value=None,
                    severity="medium",
                    source="commit_analyzer",
                )]
        return []

    def _check_unindexed_query(self, diff: str, sha: str) -> list[Signal]:
        for pattern in self._UNINDEXED_QUERY_PATTERNS:
            if re.search(pattern, diff, re.IGNORECASE):
                return [Signal(
                    id="placeholder",
                    type="commit_change",
                    description=f"Potentially unindexed query added in commit {sha}",
                    value=None,
                    severity="medium",
                    source="commit_analyzer",
                )]
        return []

    def _check_pool_reduction(self, diff: str, sha: str) -> list[Signal]:
        for pattern in self._POOL_REDUCTION_PATTERNS:
            match = re.search(pattern, diff, re.IGNORECASE)
            if match:
                try:
                    before, after = int(match.group(1)), int(match.group(2))
                    if after < before:
                        return [Signal(
                            id="placeholder",
                            type="commit_change",
                            description=(
                                f"DB connection pool reduced from {before} to {after} "
                                f"in commit {sha}"
                            ),
                            value=float(after),
                            severity="high",
                            source="commit_analyzer",
                        )]
                except (IndexError, ValueError):
                    pass
                # Pattern matched but couldn't extract numbers — still a signal
                return [Signal(
                    id="placeholder",
                    type="commit_change",
                    description=f"DB connection pool size changed in commit {sha}",
                    value=None,
                    severity="medium",
                    source="commit_analyzer",
                )]
        return []
