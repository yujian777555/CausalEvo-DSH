"""Auditable reader tests (P4-R1.2-S1)."""

import json
from pathlib import Path

import pytest

from causalevo.eval.auditable import AuditableReadError, read_auditable_rows

REPO = Path(__file__).resolve().parents[1]
AUDIT = REPO / "results" / "phase4" / "live" / "phase4-live-20261014T110259Z" / "auditable_tasks.jsonl"


def test_reads_312_rows():
    rows = read_auditable_rows(AUDIT)
    assert len(rows) == 312


def test_grid_complete():
    rows = read_auditable_rows(AUDIT)
    assert len({r["task_id"] for r in rows}) == 26
    assert {r["arm"] for r in rows} == {"B0-original", "B1-random", "B2-rule",
                                        "B3-reflexion", "B4-cea-v0", "B5-cea-v1"}
    assert {r["seed"] for r in rows} == {20261014, 20261015}


def test_rejects_missing_rows(tmp_path):
    rows = read_auditable_rows(AUDIT)
    text = AUDIT.read_text(encoding="utf-8").splitlines()
    meta = [l for l in text if l.startswith("#")]
    short = tmp_path / "short.jsonl"
    short.write_text("\n".join(meta + [json.dumps(r, sort_keys=True)
                                       for r in rows[:100]]) + "\n", encoding="utf-8")
    with pytest.raises(AuditableReadError):
        read_auditable_rows(short)


def test_rejects_tampered_row_hash(tmp_path):
    rows = read_auditable_rows(AUDIT)
    bad = dict(rows[0])
    bad["cost_cny"] = bad["cost_cny"] + 1.0  # hash mismatch
    text = AUDIT.read_text(encoding="utf-8").splitlines()
    meta = [l for l in text if l.startswith("#")]
    body = [json.dumps(r, sort_keys=True) for r in [bad] + rows[1:]]
    p = tmp_path / "tampered.jsonl"
    p.write_text("\n".join(meta + body) + "\n", encoding="utf-8")
    with pytest.raises(AuditableReadError):
        read_auditable_rows(p)


def test_rejects_wrong_schema_version(tmp_path):
    text = AUDIT.read_text(encoding="utf-8").splitlines()
    text[1] = text[1].replace("schema_version=1", "schema_version=99")
    p = tmp_path / "bad_schema.jsonl"
    p.write_text("\n".join(text) + "\n", encoding="utf-8")
    with pytest.raises(AuditableReadError):
        read_auditable_rows(p)


def test_rejects_duplicate_keys(tmp_path):
    rows = read_auditable_rows(AUDIT)
    rows[1] = dict(rows[0])  # duplicate (task, arm, seed)
    text = AUDIT.read_text(encoding="utf-8").splitlines()
    meta = [l for l in text if l.startswith("#")]
    p = tmp_path / "dup.jsonl"
    p.write_text("\n".join(meta + [json.dumps(r, sort_keys=True) for r in rows]) + "\n",
                 encoding="utf-8")
    with pytest.raises(AuditableReadError):
        read_auditable_rows(p)
