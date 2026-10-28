"""Regression tests for the hardened R1.12 hash verifier
(P4-R1.12-REVIEW-FIX2 Task B: containment + exact inventory)."""

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


def test_parent_traversal_to_status_rejected(tmp_path):
    _build()
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    doc["artifacts"]["evil"] = {"path": "results/phase4/live2/../../../status.json",
                                "sha256": "0" * 64}
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    proc = _verify(bad)
    assert proc.returncode == 1
    assert "parent traversal" in proc.stdout


def test_absolute_path_rejected(tmp_path):
    _build()
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    doc["artifacts"]["evil"] = {"path": "/etc/passwd", "sha256": "0" * 64}
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    proc = _verify(bad)
    assert proc.returncode == 1
    assert "absolute path" in proc.stdout


def test_symlink_escape_rejected_if_supported(tmp_path):
    _build()
    # create a symlink under an allowed root that resolves OUTSIDE it
    link_dir = tmp_path / "allowed"
    link_dir.mkdir()
    target = REPO / "status.json"
    link = link_dir / "tasks.jsonl"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not supported on this platform")
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    doc["artifacts"]["pilot_tasks"]["path"] = str(link.relative_to(REPO))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    proc = _verify(bad)
    # must reject because the resolved path leaves the allowed artifact root
    assert proc.returncode == 1
    assert "escapes allowed artifact root" in proc.stdout


def test_missing_required_label_rejected(tmp_path):
    _build()
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    del doc["artifacts"]["pilot_ledger"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    proc = _verify(bad)
    assert proc.returncode == 1
    assert "inventory mismatch" in proc.stdout


def test_unexpected_label_rejected(tmp_path):
    _build()
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    doc["artifacts"]["unexpected"] = {"path": "docs/x", "sha256": "0" * 64}
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    proc = _verify(bad)
    assert proc.returncode == 1
    assert "inventory mismatch" in proc.stdout


def test_malformed_sha256_rejected(tmp_path):
    _build()
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    doc["artifacts"]["pilot_analysis"]["sha256"] = "not-a-hash"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    proc = _verify(bad)
    assert proc.returncode == 1
    assert "malformed sha256" in proc.stdout


def test_malformed_entry_rejected(tmp_path):
    _build()
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    doc["artifacts"]["pilot_analysis"] = "not-an-object"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    proc = _verify(bad)
    assert proc.returncode == 1
    assert "malformed entry" in proc.stdout


def test_missing_file_rejected(tmp_path):
    _build()
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    doc["artifacts"]["pilot_analysis"]["path"] = "results/phase4/live2/phase4-r12-replication-pilot-20261027T034229Z/does-not-exist.json"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    proc = _verify(bad)
    assert proc.returncode == 1
    assert "missing file" in proc.stdout


def test_hash_mismatch_rejected(tmp_path):
    _build()
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    doc["artifacts"]["pilot_analysis"]["sha256"] = "0" * 64
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    proc = _verify(bad)
    assert proc.returncode == 1
    assert "hash mismatch" in proc.stdout
