"""Regression tests for the hardened R1.12 hash verifier
(P4-R1.12-REVIEW-FIX2 Task B: containment + exact inventory)."""

import errno
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


def _symlink_unavailable(exc):
    if isinstance(exc, NotImplementedError):
        return True
    if not isinstance(exc, OSError):
        return False
    if getattr(exc, "winerror", None) in (5, 1314):
        return True
    errno_values = {errno.EPERM, errno.EACCES}
    for name in ("ENOTSUP", "EOPNOTSUPP", "ENOSYS"):
        value = getattr(errno, name, None)
        if value is not None:
            errno_values.add(value)
    return exc.errno in errno_values


def _os_error(errno_value=None, winerror=None):
    exc = OSError(errno_value, "injected") if errno_value is not None else OSError("injected")
    if winerror is not None:
        exc.winerror = winerror
    return exc


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        pytest.param(NotImplementedError(), True, id="not-implemented"),
        pytest.param(_os_error(winerror=1314), True, id="winerror-privilege"),
        pytest.param(_os_error(winerror=5), True, id="winerror-access-denied"),
        pytest.param(_os_error(errno_value=errno.EPERM), True, id="eperm"),
        pytest.param(_os_error(errno_value=errno.EACCES), True, id="eacces"),
        pytest.param(_os_error(errno_value=errno.ENOTSUP), True, id="enotsup"),
        pytest.param(_os_error(errno_value=errno.EOPNOTSUPP), True, id="eopnotsupp"),
        pytest.param(_os_error(errno_value=errno.ENOSYS), True, id="enosys"),
        pytest.param(_os_error(errno_value=errno.EIO), False, id="eio"),
        pytest.param(_os_error(errno_value=errno.ENOSPC), False, id="enospc"),
        pytest.param(_os_error(errno_value=errno.ENOENT), False, id="enoent"),
        pytest.param(_os_error(), False, id="other-os-error"),
        pytest.param(ValueError("not an OS error"), False, id="non-os-error"),
    ],
)
def test_symlink_unavailable_classifier(exc, expected):
    assert _symlink_unavailable(exc) is expected


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
    import tempfile
    link_dir = None
    link = None
    try:
        link_dir = Path(tempfile.mkdtemp(
            prefix="symlink-test-", dir=REPO / "results" / "phase4" / "live2"))
        link = link_dir / "tasks.jsonl"
        try:
            link.symlink_to(REPO / "status.json")
        except (OSError, NotImplementedError) as exc:
            if _symlink_unavailable(exc):
                pytest.skip(f"symlink creation not permitted on this platform: {exc}")
            raise
        doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
        doc["artifacts"]["pilot_tasks"]["path"] = link.relative_to(REPO).as_posix()
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps(doc), encoding="utf-8")
        proc = _verify(bad)
        assert proc.returncode == 1, "symlink escape must be rejected"
        assert "escapes allowed artifact root" in proc.stdout
    finally:
        if link is not None and (link.is_symlink() or link.exists()):
            link.unlink()
        if link_dir is not None and link_dir.exists():
            link_dir.rmdir()


def test_symlink_escape_io_error_propagates_and_cleans_up(tmp_path, monkeypatch):
    link_dirs = []

    def raise_eio(link, target):
        link_dirs.append(link.parent)
        raise OSError(errno.EIO, "injected I/O failure")

    monkeypatch.setattr(Path, "symlink_to", raise_eio)
    try:
        test_symlink_escape_rejected_if_supported(tmp_path)
    except OSError as exc:
        assert exc.errno == errno.EIO
    except BaseException as exc:
        pytest.fail(f"EIO was not propagated: {type(exc).__name__}: {exc}")
    else:
        pytest.fail("EIO was not raised")
    assert len(link_dirs) == 1
    assert not link_dirs[0].exists()


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
