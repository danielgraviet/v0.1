"""Tests for the Sentry integration layer.

Covers signature verification and webhook payload parsing. No network calls,
no API keys — these are pure function tests against known inputs.
"""

import hashlib
import hmac

import pytest

from sre.integrations.sentry import parse_webhook_payload, verify_sentry_signature


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_signature(body: bytes, secret: str) -> str:
    """Compute the HMAC-SHA256 signature the way Sentry does."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def make_issue_payload(**overrides) -> dict:
    """Minimal valid Sentry issue-alert webhook payload."""
    base = {
        "action": "created",
        "actor": {"name": "acme-corp"},
        "data": {
            "issue": {
                "id": "4500123456",
                "project": {"slug": "backend-api"},
            }
        },
    }
    base.update(overrides)
    return base


def make_error_payload(project=None) -> dict:
    """Minimal valid Sentry error.created webhook payload."""
    return {
        "action": "created",
        "actor": {"name": "sentry"},
        "data": {
            "error": {
                "issue_id": 7299453182,
                "project": project if project is not None else {"slug": "backend-api"},
            }
        },
    }


# ── verify_sentry_signature ───────────────────────────────────────────────────

class TestVerifySentrySignature:
    def test_valid_signature_passes(self):
        body = b'{"action": "created"}'
        secret = "my_client_secret"
        sig = make_signature(body, secret)
        assert verify_sentry_signature(body, sig, secret) is True

    def test_wrong_secret_fails(self):
        body = b'{"action": "created"}'
        sig = make_signature(body, "correct_secret")
        assert verify_sentry_signature(body, sig, "wrong_secret") is False

    def test_tampered_body_fails(self):
        # Signature was computed on original body — tampered body should not match.
        body = b'{"action": "created"}'
        secret = "my_client_secret"
        sig = make_signature(body, secret)
        tampered = b'{"action": "created", "injected": true}'
        assert verify_sentry_signature(tampered, sig, secret) is False

    def test_empty_body_with_matching_signature_passes(self):
        body = b""
        secret = "my_client_secret"
        sig = make_signature(body, secret)
        assert verify_sentry_signature(body, sig, secret) is True


# ── parse_webhook_payload ─────────────────────────────────────────────────────

class TestParseWebhookPayload:
    def test_parses_issue_format(self):
        payload = parse_webhook_payload(make_issue_payload())
        assert payload.issue_id == "4500123456"
        assert payload.project_slug == "backend-api"
        assert payload.org_slug == "acme-corp"
        assert payload.action == "created"

    def test_parses_error_format_with_dict_project(self):
        payload = parse_webhook_payload(make_error_payload(project={"slug": "backend-api"}))
        assert payload.issue_id == "7299453182"
        assert payload.project_slug == "backend-api"

    def test_parses_error_format_with_integer_project(self):
        # Regression test — Sentry sometimes sends project as a bare integer ID.
        # This was the bug that caused the first 500 error in production.
        payload = parse_webhook_payload(make_error_payload(project=4510961984929792))
        assert payload.issue_id == "7299453182"
        assert payload.project_slug == "4510961984929792"

    def test_issue_id_is_always_a_string(self):
        # issue_id from error payloads arrives as an integer — must be cast to str.
        payload = parse_webhook_payload(make_error_payload())
        assert isinstance(payload.issue_id, str)

    def test_unknown_data_key_raises(self):
        raw = {
            "action": "created",
            "actor": {"name": "sentry"},
            "data": {"unknown_key": {}},
        }
        with pytest.raises(KeyError):
            parse_webhook_payload(raw)

    def test_missing_data_key_raises(self):
        raw = {"action": "created", "actor": {"name": "sentry"}}
        with pytest.raises(KeyError):
            parse_webhook_payload(raw)

    def test_resolved_action_is_preserved(self):
        # Parser must not filter on action — the webhook handler does that.
        raw = make_issue_payload(action="resolved")
        payload = parse_webhook_payload(raw)
        assert payload.action == "resolved"
