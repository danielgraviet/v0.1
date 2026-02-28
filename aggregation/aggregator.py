"""Hypothesis aggregator.

The Aggregator takes validated AgentResult objects from the JudgeLayer and
produces a single ranked list of hypotheses. It handles two concerns the
judge does not:

1. Deduplication — hypotheses with similar labels from different agents are
   merged into one, with all contributing agents listed.

2. Scoring — hypotheses are ranked by a simple formula:
       final_score = base_confidence + agreement_bonus
   where agreement_bonus = +0.1 per additional agent that produced a
   matching hypothesis. Cross-agent agreement is mathematically rewarded.

Schema note:
    Hypothesis.contributing_agent is typed as str (singular). After merging,
    a hypothesis may have multiple contributing agents. These are stored as a
    comma-separated string (e.g. "metrics_agent, commit_agent") rather than
    changing the schema mid-phase. This is a known tradeoff for the hackathon.
"""

from judge.judge import JudgedResult
from schemas.hypothesis import Hypothesis


class Aggregator:
    """Ranks and deduplicates hypotheses from all valid agent results.

    Matching is based on case-insensitive substring comparison of hypothesis
    labels. If either label contains the other as a substring, the hypotheses
    are considered to describe the same root cause and are merged.

    The top 5 hypotheses by final score are returned. Confidence is capped
    at 1.0 even if the agreement bonus would push it higher.
    """

    def aggregate(self, results: list[JudgedResult]) -> list[Hypothesis]:
        """Aggregate valid hypotheses from all judged results into a ranked list.

        Steps:
            1. Collect all hypotheses from valid results only
            2. Group by similar label (case-insensitive substring match)
            3. For each group: take highest confidence, apply agreement bonus,
               merge contributing agents and supporting signals
            4. Sort by final score descending
            5. Return top 5

        Args:
            results: JudgedResult objects from the JudgeLayer. Invalid results
                are filtered out — only valid results contribute hypotheses.

        Returns:
            List of up to 5 Hypothesis objects sorted by final score
            descending. Returns an empty list if no valid hypotheses exist.
        """
        all_hypotheses = self._collect_valid(results)

        if not all_hypotheses:
            return []

        groups = self._group_by_label(all_hypotheses)
        ranked = [self._merge_group(group) for group in groups]
        ranked.sort(key=lambda h: h.confidence, reverse=True)

        return ranked[:5] # why are we slicing 5? 

    # ── Private helpers ───────────────────────────────────────────────────────

    def _collect_valid(self, results: list[JudgedResult]) -> list[Hypothesis]:
        """Collect all hypotheses from valid JudgedResults.

        Args:
            results: All judged results from the judge layer.

        Returns:
            Flat list of all hypotheses from results where valid=True.
        """
        hypotheses = []
        for judged in results:
            if judged.valid:
                hypotheses.extend(judged.result.hypotheses) # what does extend do?
        return hypotheses

    def _group_by_label(self, hypotheses: list[Hypothesis]) -> list[list[Hypothesis]]:
        """Group hypotheses by similar label using case-insensitive substring match.

        Each hypothesis is placed into the first group whose representative
        label it matches. If no group matches, a new group is started.

        Matching is bidirectional: "DB Pool" matches "DB Connection Pool
        Exhaustion" because one label contains the other as a substring.

        Args:
            hypotheses: Flat list of all collected hypotheses.

        Returns:
            List of groups, where each group is a list of hypotheses that
            describe the same root cause.
        """
        groups: list[list[Hypothesis]] = []

        for hypothesis in hypotheses:
            placed = False
            for group in groups:
                if self._labels_match(hypothesis.label, group[0].label):
                    group.append(hypothesis)
                    placed = True
                    break
            if not placed:
                groups.append([hypothesis])

        return groups

    def _merge_group(self, group: list[Hypothesis]) -> Hypothesis:
        """Merge a group of matching hypotheses into one ranked hypothesis.

        Takes the hypothesis with the highest base confidence, applies the
        agreement bonus, merges contributing agents and supporting signals,
        and returns a single Hypothesis representing the group.

        Agreement bonus: +0.1 per additional agent beyond the first.
        A group of 3 agents gets +0.2. Capped at 1.0.

        Args:
            group: List of hypotheses that describe the same root cause.
                Must contain at least one element.

        Returns:
            A single merged Hypothesis with the final scored confidence.
        """
        best = max(group, key=lambda h: h.confidence)
        agreement_bonus = 0.1 * (len(group) - 1)
        final_score = min(best.confidence + agreement_bonus, 1.0)

        # Merge contributing agents — deduplicate, sort for determinism
        contributing_agents = sorted({h.contributing_agent for h in group})

        # Union of all cited signal IDs — deduplicate, preserve order
        seen = set()
        merged_signals = []
        for h in group:
            for sig_id in h.supporting_signals:
                if sig_id not in seen:
                    seen.add(sig_id)
                    merged_signals.append(sig_id)

        return best.model_copy(update={
            "confidence": round(final_score, 4),
            "supporting_signals": merged_signals,
            "contributing_agent": ", ".join(contributing_agents),
        })

    def _labels_match(self, label_a: str, label_b: str) -> bool:
        """Check if two hypothesis labels describe the same root cause.

        Matching is case-insensitive and bidirectional. Either label
        containing the other as a substring is considered a match.

        Args:
            label_a: First hypothesis label.
            label_b: Second hypothesis label.

        Returns:
            True if the labels are considered to describe the same root cause.
        """
        a = label_a.strip().lower()
        b = label_b.strip().lower()
        return a in b or b in a
