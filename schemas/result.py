"""Result schemas.

Defines the output types for individual agent runs (AgentResult) and the
full pipeline execution (ExecutionResult). These are the types that flow
through the judge and aggregator layers before reaching the caller.
"""

import uuid

from pydantic import BaseModel, Field

from schemas.hypothesis import Hypothesis
from schemas.signal import Signal


class AgentResult(BaseModel):
    """Output produced by a single agent after one execution.

    The ParallelExecutor collects one AgentResult per agent. Each result
    is passed to the JudgeLayer for validation before the hypotheses are
    forwarded to the Aggregator.

    Attributes:
        agent_name: Identifier of the agent that produced this result.
            Must be a non-empty string — the judge rejects results that
            fail this check.
        hypotheses: List of candidate root causes the agent identified.
            May be empty if the agent found no relevant signals. Each
            hypothesis must cite at least one signal ID or the judge
            will reject it.
        execution_time_ms: Wall-clock time the agent took to run, in
            milliseconds. Recorded by the ParallelExecutor and surfaced
            in the display layer.
    """

    agent_name: str
    hypotheses: list[Hypothesis]
    execution_time_ms: float


class SynthesisResult(BaseModel):
    """Narrative summary generated after hypothesis aggregation.

    Attributes:
        summary: Plain-English 2-3 sentence explanation of the incident.
        key_finding: Single most likely root cause identified from the ranking.
        confidence_in_ranking: Confidence that the ranked order is correct
            on a 0.0-1.0 scale.
    """

    summary: str
    key_finding: str
    confidence_in_ranking: float = Field(ge=0.0, le=1.0)


class ExecutionResult(BaseModel):
    """Final output of a complete AlphaRuntime.execute() pipeline run.

    This is what the caller receives after all agents have run, results
    have been validated by the judge, and hypotheses have been ranked by
    the aggregator. This is the only object that crosses the runtime
    boundary to the outside world.

    Attributes:
        ranked_hypotheses: Hypotheses sorted by final score descending
            (base_confidence + agreement_bonus). Top 5 returned.
        signals_used: All signals that were in StructuredMemory during
            the run. Included for auditability — callers can trace which
            facts drove the ranking.
        execution_id: Auto-generated UUID for this run. Useful for
            logging, replay, and correlating results with incidents.
        requires_human_review: True if the top hypothesis confidence is
            below a threshold or no hypotheses were produced. Signals to
            the caller that the result should not be acted on automatically.
        synthesis: Narrative explanation of the ranking produced after
            aggregation. Optional so older callers remain compatible.
    """

    ranked_hypotheses: list[Hypothesis]
    signals_used: list[Signal]
    synthesis: SynthesisResult | None = None
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    requires_human_review: bool
