"""Auditable dataset reader (P4-R1.2-S1): the committed projection is the
default source of truth for recomputation — the raw tasks.jsonl is NOT needed.

Format: two leading `#` metadata lines, then one JSON object per row with a
per-row `row_sha16` over the projected fields. The reader validates schema,
hashes, types, counts, and (task_id, arm, seed) uniqueness.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
EXPECTED_FIELDS: dict[str, type] = {
    "task_id": str, "arm": str, "seed": int,
    "attempt1_success": bool, "retried": bool, "final_success": bool,
    "invalid": bool, "timeout": bool, "failure_kind": str,
    "intervention": (str, type(None)),  # type: ignore[dict-item]
    "provider_calls": int, "tool_calls": int, "input_tokens": int,
    "cache_read_tokens": int, "output_tokens": int,
    "cost_cny": (int, float), "latency_ms": int, "run_id": str,
    "row_sha16": str,
}
HASH_EXCLUDE = {"row_sha16"}


class AuditableReadError(ValueError):
    pass


def read_auditable_rows(path: Path, *, expected_rows: int | None = 312) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    meta = [l for l in lines if l.startswith("#")]
    body = [l for l in lines if l.strip() and not l.startswith("#")]
    if len(meta) != 2:
        raise AuditableReadError(f"expected 2 metadata lines, got {len(meta)}")
    if f"schema_version={SCHEMA_VERSION}" not in meta[1]:
        raise AuditableReadError(f"schema mismatch in metadata: {meta[1]!r}")
    rows = []
    for i, line in enumerate(body):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AuditableReadError(f"row {i}: invalid JSON: {exc}") from exc
        missing = set(EXPECTED_FIELDS) - set(row)
        if missing:
            raise AuditableReadError(f"row {i}: missing fields {sorted(missing)}")
        for field, types in EXPECTED_FIELDS.items():
            if not isinstance(row[field], types if isinstance(types, tuple) else (types,)):
                raise AuditableReadError(
                    f"row {i}: field {field} has wrong type {type(row[field]).__name__}")
        expected_hash = hashlib.sha256(json.dumps(
            {k: v for k, v in row.items() if k not in HASH_EXCLUDE},
            sort_keys=True).encode()).hexdigest()[:16]
        if row["row_sha16"] != expected_hash:
            raise AuditableReadError(f"row {i}: row_sha16 mismatch")
        rows.append(row)
    if expected_rows is not None and len(rows) != expected_rows:
        raise AuditableReadError(f"expected {expected_rows} rows, got {len(rows)}")
    keys = [(r["task_id"], r["arm"], r["seed"]) for r in rows]
    if len(set(keys)) != len(keys):
        raise AuditableReadError("duplicate (task_id, arm, seed)")
    return rows


def row_sha16(row: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        {k: v for k, v in row.items() if k not in HASH_EXCLUDE},
        sort_keys=True).encode()).hexdigest()[:16]
