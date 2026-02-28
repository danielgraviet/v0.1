"""LLM response parser utility.

Every agent uses this to turn a raw LLM string into a validated Pydantic
model. Handles the common failure modes:
- JSON wrapped in markdown code blocks (```json ... ```)
- Commentary before or after the JSON object
- Invalid field values (e.g. confidence outside [0.0, 1.0])
"""

import json
import re

from pydantic import BaseModel


class LLMParseError(Exception):
    """Raised when an LLM response cannot be parsed into the expected schema.

    Includes the raw response so callers can log it for debugging without
    having to catch and re-wrap the original exception themselves.
    """

    def __init__(self, message: str, raw: str):
        super().__init__(message)
        self.raw = raw


def parse_llm_json(response: str, schema: type[BaseModel]) -> BaseModel:
    """Parse an LLM response string into a validated Pydantic model.

    Tries three extraction strategies in order, stopping at the first that
    produces valid JSON:
        1. Strip markdown code fences and parse the remainder directly.
        2. Extract the first {...} block via regex (handles leading commentary).
        3. Fail with LLMParseError including the raw response.

    Confidence values on any nested Hypothesis objects are clamped to
    [0.0, 1.0] before validation so LLM rounding errors don't crash the run.

    Args:
        response: Raw string returned by LLMClient.complete().
        schema:   Pydantic model class to validate against.

    Returns:
        A validated instance of schema.

    Raises:
        LLMParseError: If the response cannot be parsed or does not match
            the schema. The .raw attribute contains the original response.
    """
    cleaned = _strip_code_fences(response)

    data = _try_parse(cleaned)
    if data is None:
        data = _extract_json_object(cleaned)
    if data is None:
        raise LLMParseError(
            f"No valid JSON found in LLM response for schema {schema.__name__}",
            raw=response,
        )

    _clamp_confidences(data)

    try:
        return schema.model_validate(data)
    except Exception as exc:
        raise LLMParseError(
            f"LLM response does not match schema {schema.__name__}: {exc}",
            raw=response,
        ) from exc


# ── Private helpers ────────────────────────────────────────────────────────────

def _strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers."""
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text)
    return text.strip()


def _try_parse(text: str) -> dict | None:
    """Attempt a direct json.loads(); return None on failure."""
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None


def _extract_json_object(text: str) -> dict | None:
    """Find the first {...} block in text and parse it."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    return _try_parse(match.group(0))


def _clamp_confidences(data: dict) -> None:
    """Clamp confidence values to [0.0, 1.0] in any hypotheses list."""
    for hyp in data.get("hypotheses", []):
        if isinstance(hyp, dict) and "confidence" in hyp:
            hyp["confidence"] = max(0.0, min(1.0, float(hyp["confidence"])))
