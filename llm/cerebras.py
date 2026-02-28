"""Cerebras LLM client.

Required environment variable:
    CEREBRAS_API_KEY: Your Cerebras API key. Add to .env and never commit.
"""

import os

import openai
from dotenv import load_dotenv

from llm.base import LLMClient

load_dotenv()


class CerebrasClient(LLMClient):
    """LLMClient implementation backed by Cerebras Inference API."""

    def __init__(self, model: str):
        """Initialize the client for a specific Cerebras-hosted model.

        Args:
            model: Cerebras model ID string.

        Raises:
            KeyError: If CEREBRAS_API_KEY is not set in the environment.
        """
        self.model = model
        self.client = openai.AsyncOpenAI(
            base_url="https://api.cerebras.ai/v1",
            api_key=os.environ["CEREBRAS_API_KEY"],
        )

    async def complete(self, system: str, user: str) -> str:
        """Send a prompt to the configured model via Cerebras."""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content
