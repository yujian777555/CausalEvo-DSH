"""Regression tests for the R1.12 artifact-hash manifest and verifier
(P4-R1.12-REVIEW-FIX1 Task A)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PILOT = REPO / "results" / "phase4" / "live2" / "phase4-r12-replication-pilot-20261027T034229Z"
MANIFEST = PILOT / "manifest_reconciled.json"


def _build():
    proc = subprocess.run([sys.executable, str(REPO / "scripts" / "build_r12_manifest.py")],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr


def _verify(path=None):
    args = [sys.executable, str(REPO / "scripts" / "verify_r12_hashes.py")]
    if path is not None:
        args.append(str(path))
    return subprocess.run(args, capture_output=True, text=True, timeout=60)


def test_build_and_verify_pass():
    _build()
    proc = _verify()
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "HASH VERIFIED: 12 artifacts" in proc.stdout


def test_changed_content_rejected(tmp_path):
    _build()
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    doc["artifacts"]["pilot_analysis"]["sha256"] = "0" * 64
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    proc = _verify(bad)
    assert proc.returncode == 1
    assert "hash mismatch" in proc.stdout


def test_missing_file_rejected(tmp_path):
    _build()
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    doc["artifacts"]["pilot_analysis"]["path"] = "results/phase4/live2/phase4-r12-replication-pilot-20261027T034229Z/does-not-exist.json"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    proc = _verify(bad)
    assert proc.returncode == 1
    assert "missing file" in proc.stdout


def test_path_traversal_rejected(tmp_path):
    _build()
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    doc["artifacts"]["evil"] = {"path": "../../etc/passwd", "sha256": "0" * 64}
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    proc = _verify(bad)
    assert proc.returncode == 1
    assert "path traversal" in proc.stdout


def test_manifest_has_required_entries_and_no_self_hash():
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    artifacts = doc["artifacts"]
    for key in ("protocol", "analysis_script", "pilot_tasks", "pilot_events",
                "pilot_ledger", "pilot_controller_state", "pilot_analysis",
                "canary_tasks", "canary_events", "canary_ledger", "canary_manifest",
                "pilot_original_manifest"):
        assert key in artifacts, f"missing {key}"
        assert len(artifacts[key]["sha256"]) == 64
    assert "manifest_reconciled.json" not in artifacts, "no self-referential hash"
