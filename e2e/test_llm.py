"""LLM client tests.

Tests for the LLMClient abstraction and OpenRouterClient implementation.

TestLLMClientAbstract  — no API key needed, runs in CI
TestOpenRouterClient   — the real API call test is skipped if OPENROUTER_API_KEY
                         is not set in the environment or .env file
"""

import os

import pytest

from llm.base import LLMClient
from llm.openrouter import OpenRouterClient


# ── LLMClient (abstract) ──────────────────────────────────────────────────────

class TestLLMClientAbstract:
    def test_cannot_instantiate_directly(self):
        """LLMClient is abstract — instantiating it directly must raise."""
        with pytest.raises(TypeError, match="abstract"):
            LLMClient()

    def test_subclass_without_complete_raises(self):
        """A subclass that skips implementing complete() must also raise."""
        class IncompleteClient(LLMClient):
            pass

        with pytest.raises(TypeError, match="abstract"):
            IncompleteClient()

    def test_subclass_with_complete_is_instantiable(self):
        """A subclass that implements complete() should instantiate fine."""
        class ConcreteClient(LLMClient):
            async def complete(self, system: str, user: str) -> str:
                return "ok"

        client = ConcreteClient()
        assert isinstance(client, LLMClient)


# ── OpenRouterClient ──────────────────────────────────────────────────────────

class TestOpenRouterClient:
    def test_raises_immediately_if_api_key_missing(self, monkeypatch):
        """Missing key must raise KeyError at construction, not at first call."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        with pytest.raises(KeyError):
            OpenRouterClient(model="google/gemini-2.0-flash-001")

    def test_is_subclass_of_llm_client(self):
        """OpenRouterClient must satisfy the LLMClient interface."""
        assert issubclass(OpenRouterClient, LLMClient)

    @pytest.mark.skipif(
        not os.getenv("OPENROUTER_API_KEY"),
        reason="OPENROUTER_API_KEY not set — skipping live API call",
    )
    @pytest.mark.live
    async def test_real_api_call_returns_string(self):
        """Make a real call to OpenRouter and verify we get a non-empty string back."""
        client = OpenRouterClient(model="google/gemini-2.0-flash-001")
        response = await client.complete(
            system="You are a test assistant. Reply with one word only, no punctuation.",
            user="Say the word pong.",
        )
        assert isinstance(response, str)
        assert len(response.strip()) > 0

    @pytest.mark.skipif(
        not os.getenv("OPENROUTER_API_KEY"),
        reason="OPENROUTER_API_KEY not set — skipping live API call",
    )
    @pytest.mark.live
    async def test_different_models_both_respond(self):
        """Verify two different models both return responses through the same client interface."""
        claude = OpenRouterClient(model="anthropic/claude-sonnet-4.5")
        gemini = OpenRouterClient(model="google/gemini-2.0-flash-001")

        system = "Reply with one word only, no punctuation."
        user = "Say the word pong."

        claude_response = await claude.complete(system=system, user=user)
        gemini_response = await gemini.complete(system=system, user=user)

        assert isinstance(claude_response, str) and len(claude_response.strip()) > 0
        assert isinstance(gemini_response, str) and len(gemini_response.strip()) > 0
