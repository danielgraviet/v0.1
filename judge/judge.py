"""Judge layer.

The JudgeLayer validates AgentResult objects before they reach the aggregator.
All checks are deterministic — same inputs always produce the same pass/fail
result. No LLM is involved, ever.

The judge reports verdicts. It does not decide what to do with them — that
is the runtime's responsibility. A rejected result is logged and excluded
from aggregation, but does not stop the pipeline.

Why deterministic-only?
    If the judge used an LLM to evaluate results, you would have
    non-determinism validating non-determinism. Debugging a failed
    validation would require reasoning about two probabilistic systems
    at once. Deterministic checks are fast, reproducible, and testable.
"""

from dataclasses import dataclass

from core.memory import StructuredMemory
from schemas.result import AgentResult


@dataclass
class JudgedResult:
    """The verdict produced by the JudgeLayer for a single AgentResult.

    A dataclass rather than a Pydantic model because it is an internal
    pipeline object — it is never serialized or passed across a system
    boundary. It flows from judge to aggregator within one execute() call.

    Attributes:
        valid: True if the result passed all checks and its hypotheses
            are safe to aggregate. False if any check failed.
        result: The original AgentResult being judged. Always present
            regardless of validity, so the caller can log context.
        rejection_reason: Human-readable description of the first check
            that failed. None if valid is True.
    """

    valid: bool
    result: AgentResult
    rejection_reason: str | None = None


class JudgeLayer:
    """Validates AgentResult objects before aggregation.

    Runs four deterministic checks on each result. Fails fast — the first
    failing check produces a rejection immediately without running the rest.

    All checks are self-contained and stateless. The only external dependency
    is StructuredMemory, which is needed to cross-reference signal IDs.
    """

    def validate(self, result: AgentResult, memory: StructuredMemory) -> JudgedResult:
        """Validate a single AgentResult against the judge's four checks.

        Checks run in order. The first failure short-circuits and returns
        a rejected JudgedResult immediately. A result with zero hypotheses
        is considered valid — the agent may have found no relevant signals.

        Args:
            result: The AgentResult produced by an agent after execution.
            memory: The StructuredMemory for this execution. Used to
                cross-reference cited signal IDs against real signals.

        Returns:
            A JudgedResult with valid=True if all checks passed, or
            valid=False with a rejection_reason describing the first
            check that failed.
        """

        # Check 1 — agent_name must be a non-empty string.
        # An empty name means the result cannot be attributed to any agent,
        # making it useless for the aggregator and display layer.
        if not result.agent_name or not result.agent_name.strip():
            return JudgedResult(
                valid=False,
                result=result,
                rejection_reason="agent_name is empty or whitespace.",
            )

        # Check 2 — every hypothesis must cite at least one signal.
        # A hypothesis with no supporting signals is pure invention —
        # it is not grounded in any verified fact from the incident.
        for hypothesis in result.hypotheses:
            if not hypothesis.supporting_signals:
                return JudgedResult(
                    valid=False,
                    result=result,
                    rejection_reason=(
                        f"Hypothesis '{hypothesis.label}' from agent "
                        f"'{result.agent_name}' has no supporting signals."
                    ),
                )

        # Check 3 — every cited signal ID must exist in memory.
        # An agent might hallucinate a signal ID that was never extracted.
        # This check catches that before the aggregator treats a ghost
        # signal as real evidence.
        valid_signal_ids = memory.signal_ids()
        for hypothesis in result.hypotheses:
            for signal_id in hypothesis.supporting_signals:
                if signal_id not in valid_signal_ids:
                    return JudgedResult(
                        valid=False,
                        result=result,
                        rejection_reason=(
                            f"Hypothesis '{hypothesis.label}' from agent "
                            f"'{result.agent_name}' cites unknown signal "
                            f"ID '{signal_id}'. Valid IDs: {sorted(valid_signal_ids)}"
                        ),
                    )

        # Check 4 — confidence must be between 0.0 and 1.0.
        # Pydantic already enforces this at Hypothesis creation time, so
        # this check should never fail in practice. It is included as
        # defense-in-depth in case a result is constructed in an unusual
        # way that bypasses normal instantiation.
        for hypothesis in result.hypotheses:
            if not 0.0 <= hypothesis.confidence <= 1.0:
                return JudgedResult(
                    valid=False,
                    result=result,
                    rejection_reason=(
                        f"Hypothesis '{hypothesis.label}' from agent "
                        f"'{result.agent_name}' has invalid confidence "
                        f"{hypothesis.confidence} (must be 0.0–1.0)."
                    ),
                )

        return JudgedResult(valid=True, result=result)
