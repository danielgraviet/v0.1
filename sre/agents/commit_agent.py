"""Commit Agent — reasons over commit change signals using Claude."""

import json
import logging
import pathlib

from pydantic import BaseModel

from agents.base import AgentContext, BaseAgent
from llm.base import LLMClient
from schemas.hypothesis import Hypothesis
from schemas.result import AgentResult
from utils.parse import LLMParseError, parse_llm_json

logger = logging.getLogger(__name__)

_PROMPT_FILE = pathlib.Path(__file__).parent.parent / "prompts" / "commit_agent.txt"
_SIGNAL_TYPES = {"commit_change"}


class _HypothesesSchema(BaseModel):
    hypotheses: list[Hypothesis]


class CommitAgent(BaseAgent):
    """Analyses commit change signals and generates deployment risk hypotheses.

    Focuses exclusively on signals of type 'commit_change'. Returns empty
    result if none are present.

    Model: anthropic/claude-sonnet-4-6 via OpenRouter — strongest model
    for code diff analysis and understanding causal chains in code changes.
    """

    name = "commit_agent"

    def __init__(self, llm: LLMClient) -> None:
        super().__init__(llm)
        self._system_prompt = _PROMPT_FILE.read_text()

    async def run(self, context: AgentContext) -> AgentResult:
        signals = [s for s in context.signals if s.type in _SIGNAL_TYPES]

        if not signals:
            logger.debug("commit_agent: no commit_change signals — skipping LLM call.")
            return AgentResult(agent_name=self.name, hypotheses=[], execution_time_ms=0.0)

        user_message = (
            f"Deployment: {context.incident.deployment_id}\n\n"
            f"Commit change signals:\n{json.dumps([s.model_dump() for s in signals], indent=2)}"
        )

        try:
            raw = await self.llm.complete(system=self._system_prompt, user=user_message)
            parsed = parse_llm_json(raw, _HypothesesSchema)
            return AgentResult(agent_name=self.name, hypotheses=parsed.hypotheses, execution_time_ms=0.0)
        except LLMParseError as exc:
            logger.error("commit_agent: failed to parse LLM response: %s\nRaw: %s", exc, exc.raw)
            return AgentResult(agent_name=self.name, hypotheses=[], execution_time_ms=0.0)
