"""LLMClient abstract base class.

Defines the interface every LLM provider must implement. The runtime and
agents depend only on this interface — never on a concrete provider. Swapping
OpenRouter for Cerebras (or any other provider) means writing a new class
that satisfies this interface, with zero changes to the rest of the system.
"""

from abc import ABC, abstractmethod


class LLMClient(ABC):
    """Abstract base class for all LLM provider clients.

    Agents receive an LLMClient instance at construction time and call
    complete() to get a text response. They never import or instantiate
    a concrete provider directly — that decision belongs to the caller
    that wires the system together.

    To add a new provider, subclass LLMClient and implement complete().
    """

    @abstractmethod
    async def complete(self, system: str, user: str) -> str:
        """Send a prompt to the LLM and return the response as plain text.

        Args:
            system: The system prompt that sets the agent's role and
                instructions (e.g. "You are an SRE analyst...").
            user: The user-turn content — typically the signal list and
                incident context the agent should reason over.

        Returns:
            The model's response as a plain string. Callers never see
            the raw SDK response object.

        Raises:
            NotImplementedError: If a subclass does not implement this method.
        """
        ...
