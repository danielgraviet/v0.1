"""Base agent definition.

Defines the contract every SRE agent must satisfy. Agents are the reasoning
units of the Alpha runtime — they receive a context of verified signals and
return candidate root-cause hypotheses.

Agents are deliberately "dumb" workers:
- They do not call other agents
- They do not store state between runs
- They do not see raw incident data — only the extracted signal list
- They do not modify signals

All intelligence about scheduling, validation, and ranking lives in the
runtime, executor, judge, and aggregator layers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from llm.base import LLMClient
from schemas.incident import IncidentInput
from schemas.result import AgentResult
from schemas.signal import Signal


@dataclass
class AgentContext:
    """The input context passed to every agent at execution time.

    Built by AlphaRuntime from StructuredMemory just before agents run.
    Agents receive this and nothing else — they never see the raw
    IncidentInput directly.

    This is a dataclass rather than a Pydantic model because it is an
    internal runtime object. It is never serialized, validated from external
    input, or passed across a system boundary.

    Attributes:
        signals: The full list of verified signals extracted from the incident.
            Agents reason over these and cite their IDs in hypotheses.
            Immutable by convention — agents must not modify this list.
        incident: The original incident payload. Included for reference
            (e.g. deployment ID for labeling) but agents should ground
            their reasoning in signals, not raw incident fields.
    """

    signals: list[Signal]
    incident: IncidentInput


class BaseAgent(ABC):
    """Abstract base class for all Alpha SRE agents.

    Every concrete agent (LogAgent, MetricsAgent, etc.) extends this class
    and implements name and run(). The runtime only ever interacts with agents
    through this interface — concrete types are never referenced in core/.

    The LLM client is injected at construction time so that:
    - Different agents can use different models (one string change)
    - Tests can inject a mock client without touching agent logic
    - The runtime stays provider-agnostic

    Example:
        class LogAgent(BaseAgent):
            name = "log_agent"

            async def run(self, context: AgentContext) -> AgentResult:
                response = await self.llm.complete(system=..., user=...)
                ...

    Attributes:
        llm: The LLM client this agent uses to generate hypotheses.
    """

    def __init__(self, llm: LLMClient) -> None:
        """Initialise the agent with an LLM client.

        Args:
            llm: Any concrete LLMClient implementation. The agent calls
                llm.complete() during run() to get model responses.
        """
        self.llm = llm

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this agent.

        Used by the judge to validate agent_name, by the aggregator to track
        contributing agents, and by the display layer to label panels.

        Implement by declaring a class-level attribute on the subclass:

            class LogAgent(BaseAgent):
                name = "log_agent"
        """
        ...

    @abstractmethod
    async def run(self, context: AgentContext) -> AgentResult:
        """Analyse the incident context and return candidate root causes.

        This is the core reasoning step. The implementation should:
        1. Filter signals relevant to this agent's domain
        2. Build a prompt from those signals
        3. Call self.llm.complete() to get the model's analysis
        4. Parse the response into one or more Hypothesis objects
        5. Return an AgentResult with those hypotheses

        Args:
            context: Signals and incident metadata for this execution.
                Provided by AlphaRuntime via StructuredMemory.

        Returns:
            An AgentResult containing zero or more hypotheses. Returning
            zero hypotheses is valid — it means the agent found no signals
            relevant to its domain. The judge will still validate the result.

        Raises:
            Exception: Any unhandled exception is caught by ParallelExecutor,
                which logs it and skips this agent rather than crashing the run.
        """
        ...
