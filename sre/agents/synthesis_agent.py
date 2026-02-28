"""Synthesis Agent — explains the ranked hypotheses in plain English."""

import json
import logging
import pathlib

from pydantic import BaseModel

from llm.base import LLMClient
from schemas.hypothesis import Hypothesis
from schemas.result import SynthesisResult
from schemas.signal import Signal
from utils.parse import LLMParseError, parse_llm_json

logger = logging.getLogger(__name__)

_PROMPT_FILE = pathlib.Path(__file__).parent.parent / "prompts" / "synthesis_agent.txt"


class _SynthesisSchema(BaseModel):
    summary: str
    key_finding: str
    confidence_in_ranking: float


class SynthesisAgent:
    """Generates a narrative summary from signals and ranked hypotheses.

    This agent runs after aggregation and does not produce hypotheses.
    It only explains the existing ranking.
    """

    name = "synthesis_agent"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self._system_prompt = _PROMPT_FILE.read_text()

    async def synthesize(
        self,
        signals: list[Signal],
        ranked_hypotheses: list[Hypothesis],
    ) -> SynthesisResult:
        """Return a narrative synthesis of the ranked incident hypotheses."""
        if not ranked_hypotheses:
            return SynthesisResult(
                summary=(
                    "No validated hypotheses were produced from the current signal set. "
                    "A human should review logs, metrics, and recent changes directly."
                ),
                key_finding="Insufficient evidence to identify a likely root cause.",
                confidence_in_ranking=0.0,
            )

        user_message = (
            f"Signals:\n{json.dumps([s.model_dump() for s in signals], indent=2)}\n\n"
            f"Ranked hypotheses:\n"
            f"{json.dumps([h.model_dump() for h in ranked_hypotheses], indent=2)}"
        )

        try:
            raw = await self.llm.complete(system=self._system_prompt, user=user_message)
            parsed = parse_llm_json(raw, _SynthesisSchema)
            return SynthesisResult(
                summary=parsed.summary,
                key_finding=parsed.key_finding,
                confidence_in_ranking=max(0.0, min(1.0, parsed.confidence_in_ranking)),
            )
        except LLMParseError as exc:
            logger.error("synthesis_agent: failed to parse LLM response: %s\nRaw: %s", exc, exc.raw)
            top = ranked_hypotheses[0]
            return SynthesisResult(
                summary=(
                    "The ranking indicates a likely causal chain, but the synthesis response "
                    "could not be parsed. Review the top-ranked hypothesis details directly."
                ),
                key_finding=f"{top.label}: {top.description}",
                confidence_in_ranking=top.confidence,
            )
