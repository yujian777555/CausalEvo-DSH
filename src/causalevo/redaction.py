"""Redaction helpers: secrets must never reach logs, CSVs, reports, or git."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

_REDACTED = "[REDACTED]"

# Bearer tokens, DeepSeek-style sk- keys, generic long hex/base64 secrets.
_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{10,}", re.IGNORECASE),
    re.compile(r"(?i)(api[_-]?key|authorization|token|secret)([\"'\s:=]+)([^\s\"',}]{8,})"),
]

_SENSITIVE_KEY_RE = re.compile(r"(?i)(api[_-]?key|authorization|token|secret|password|credential)")


def redact_text(text: str) -> str:
    """Replace credential-looking substrings with [REDACTED]."""
    out = text
    for pattern in _PATTERNS:
        out = pattern.sub(lambda m: (
            m.group(1) + m.group(2) + _REDACTED if m.lastindex and m.lastindex >= 3 else _REDACTED
        ), out)
    return out


def redact_obj(obj: Any) -> Any:
    """Deep-redact mappings/sequences; values of sensitive keys are replaced wholesale."""
    if isinstance(obj, Mapping):
        redacted: dict[str, Any] = {}
        for key, value in obj.items():
            if isinstance(key, str) and _SENSITIVE_KEY_RE.search(key):
                redacted[key] = _REDACTED
            else:
                redacted[key] = redact_obj(value)
        return redacted
    if isinstance(obj, (list, tuple)):
        return [redact_obj(item) for item in obj]
    if isinstance(obj, str):
        return redact_text(obj)
    return obj


def hash_identifier(identifier: str, *, salt: str, length: int = 12) -> str:
    """Deterministic truncated hash for publishing session IDs safely."""
    if not salt:
        raise ValueError("hash_identifier requires a non-empty salt")
    digest = hashlib.sha256(f"{salt}:{identifier}".encode("utf-8")).hexdigest()
    return digest[:length]
