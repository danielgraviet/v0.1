"""Config Agent — reasons over configuration change signals using Gemini Flash."""

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

_PROMPT_FILE = pathlib.Path(__file__).parent.parent / "prompts" / "config_agent.txt"
_SIGNAL_TYPES = {"config_change"}


class _HypothesesSchema(BaseModel):
    hypotheses: list[Hypothesis]


class ConfigAgent(BaseAgent):
    """Analyses configuration change signals and generates infrastructure hypotheses.

    Focuses exclusively on signals of type 'config_change'. Returns empty
    result if none are present.

    Model: google/gemini-2.0-flash via OpenRouter — lightweight and fast
    for key-value comparison reasoning.
    """

    name = "config_agent"

    def __init__(self, llm: LLMClient) -> None:
        super().__init__(llm)
        self._system_prompt = _PROMPT_FILE.read_text()

    async def run(self, context: AgentContext) -> AgentResult:
        signals = [s for s in context.signals if s.type in _SIGNAL_TYPES]

        if not signals:
            logger.debug("config_agent: no config_change signals — skipping LLM call.")
            return AgentResult(agent_name=self.name, hypotheses=[], execution_time_ms=0.0)

        user_message = (
            f"Deployment: {context.incident.deployment_id}\n\n"
            f"Configuration change signals:\n{json.dumps([s.model_dump() for s in signals], indent=2)}"
        )

        try:
            raw = await self.llm.complete(system=self._system_prompt, user=user_message)
            parsed = parse_llm_json(raw, _HypothesesSchema)
            return AgentResult(agent_name=self.name, hypotheses=parsed.hypotheses, execution_time_ms=0.0)
        except LLMParseError as exc:
            logger.error("config_agent: failed to parse LLM response: %s\nRaw: %s", exc, exc.raw)
            return AgentResult(agent_name=self.name, hypotheses=[], execution_time_ms=0.0)
