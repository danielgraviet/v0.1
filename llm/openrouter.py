"""OpenRouter LLM client.

OpenRouter is a unified proxy that provides access to models from Anthropic,
Google, Cerebras, and others through a single OpenAI-compatible API and one
API key. Switching models is just changing the model string — the rest of
the code is unchanged.

Required environment variable:
    OPENROUTER_API_KEY: Your OpenRouter API key. Add to .env and never commit.
"""

import os

import openai
from dotenv import load_dotenv

from llm.base import LLMClient

load_dotenv()


class OpenRouterClient(LLMClient):
    """LLMClient implementation backed by OpenRouter.

    Uses the openai SDK pointed at the OpenRouter base URL, which makes it
    compatible with any model OpenRouter proxies. Model routing is just a
    string — pass the model ID at construction time and the client handles
    the rest.

    Example usage:
        log_agent = LogAgent(llm=OpenRouterClient("anthropic/claude-sonnet-4-6"))
        metrics_agent = MetricsAgent(llm=OpenRouterClient("google/gemini-2.0-flash"))

    Attributes:
        model: The OpenRouter model identifier string passed to the API
            (e.g. "anthropic/claude-sonnet-4-6", "google/gemini-2.0-flash").
        client: The underlying async OpenAI client configured for OpenRouter.
    """

    def __init__(self, model: str):
        """Initialize the client for a specific model.

        Args:
            model: OpenRouter model ID string. No default — always be explicit
                about which model an agent is using.

        Raises:
            KeyError: If OPENROUTER_API_KEY is not set in the environment
                or .env file. Fails immediately at construction rather than
                at the first API call.
        """
        self.model = model
        self.client = openai.AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
        )

    async def complete(self, system: str, user: str) -> str:
        """Send a prompt to the configured model via OpenRouter.

        Args:
            system: System prompt defining the agent's role and task.
            user: User-turn content — the signals and context to reason over.

        Returns:
            The model's response as a plain string with no SDK wrapper.

        Raises:
            openai.APIError: If the OpenRouter API returns an error response.
        """
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content
