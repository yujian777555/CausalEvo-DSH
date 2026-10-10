"""Redaction: credentials must not survive into logs/CSVs/reports."""

from causalevo.redaction import hash_identifier, redact_obj, redact_text

FAKE_KEY = "sk-" + "a1b2c3d4" * 4  # 35 chars, DeepSeek-shaped


def test_redacts_sk_keys():
    assert FAKE_KEY not in redact_text(f"Authorization: Bearer {FAKE_KEY}")
    assert FAKE_KEY not in redact_text(f"key={FAKE_KEY} end")


def test_redacts_bearer_tokens():
    out = redact_text("Bearer abcdef1234567890XYZ")
    assert "abcdef1234567890XYZ" not in out


def test_redacts_nested_sensitive_keys():
    payload = {
        "config": {"api_key": FAKE_KEY, "nested": {"authorization": "Bearer " + FAKE_KEY}},
        "note": "model=deepseek-flash",
        "list": [{"token": "abc123456789"}],
    }
    redacted = redact_obj(payload)
    text = str(redacted)
    assert FAKE_KEY not in text
    assert "abc123456789" not in text
    assert redacted["config"]["api_key"] == "[REDACTED]"
    assert redacted["note"] == "model=deepseek-flash"  # non-sensitive text untouched


def test_hash_identifier_is_deterministic_and_salted():
    h1 = hash_identifier("session-1", salt="cfg")
    h2 = hash_identifier("session-1", salt="cfg")
    h3 = hash_identifier("session-1", salt="other")
    assert h1 == h2 and h1 != h3 and len(h1) == 12
