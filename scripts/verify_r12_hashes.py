"""Independent verifier for the R1.12 SHA-256 manifest (P4-R1.12-REVIEW-FIX1).

Recomputes every listed SHA-256 from the committed bytes and FAILS on:
- a missing referenced file;
- a hash mismatch (content changed);
- a path escaping the allowed artifact roots (path traversal).
Exit 0 on success, 1 on failure with a specific reason.
"""
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ALLOWED_PREFIXES = ("results/phase4/live2/", "docs/", "scripts/")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


REPO = Path(__file__).resolve().parents[1]
ALLOWED_PREFIXES = ("results/phase4/live2/", "docs/", "scripts/")
EXPECTED_LABELS = frozenset({
    "protocol", "analysis_script", "pilot_tasks", "pilot_events",
    "pilot_ledger", "pilot_controller_state", "pilot_analysis",
    "canary_tasks", "canary_events", "canary_ledger", "canary_manifest",
    "pilot_original_manifest",
})


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contained(resolved: Path, root: Path) -> bool:
    """Path-aware containment (not string-prefix matching): True iff
    `resolved` is a descendant of `root` after canonical resolution."""
    try:
        resolved.relative_to(root)
        return True
    except ValueError:
        return False


def verify(manifest_path: Path) -> list[str]:
    errors = []
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = doc.get("artifacts")
    if not isinstance(artifacts, dict):
        return ["artifacts: not a mapping"]
    labels = set(artifacts)
    if labels != EXPECTED_LABELS:
        missing = sorted(EXPECTED_LABELS - labels)
        unexpected = sorted(labels - EXPECTED_LABELS)
        errors.append(f"artifact inventory mismatch: missing={missing}, unexpected={unexpected}")
    for label, entry in artifacts.items():
        if not isinstance(entry, dict):
            errors.append(f"{label}: malformed entry (not an object)")
            continue
        rel = entry.get("path")
        expected = entry.get("sha256")
        if not isinstance(expected, str) or len(expected) != 64 or \
                any(c not in "0123456789abcdef" for c in expected):
            errors.append(f"{label}: malformed sha256 {expected!r}")
            continue
        if not isinstance(rel, str):
            errors.append(f"{label}: invalid path {rel!r}")
            continue
        rel_posix = rel.replace("\\", "/")
        if rel_posix.startswith("/") or rel_posix.startswith("~"):
            errors.append(f"{label}: absolute path rejected {rel!r}")
            continue
        if ".." in Path(rel_posix).parts:
            errors.append(f"{label}: parent traversal rejected {rel!r}")
            continue
        if not rel_posix.startswith(ALLOWED_PREFIXES):
            errors.append(f"{label}: not-allowed root {rel!r}")
            continue
        path = (REPO / rel_posix).resolve()
        if not _contained(path, REPO):
            errors.append(f"{label}: path escapes repo root {rel!r}")
            continue
        allowed_root = next((REPO / prefix for prefix in ALLOWED_PREFIXES
                             if rel_posix.startswith(prefix)), None)
        if allowed_root is None or not _contained(path, allowed_root):
            errors.append(f"{label}: path escapes allowed artifact root {rel!r}")
            continue
        if not path.is_file():
            errors.append(f"{label}: missing file {rel_posix}")
            continue
        actual = sha(path)
        if actual != expected:
            errors.append(f"{label}: hash mismatch {rel_posix} (expected {expected}, actual {actual})")
    return errors


def main() -> int:
    manifest = REPO / "results" / "phase4" / "live2" / \
        "phase4-r12-replication-pilot-20261027T034229Z" / "manifest_reconciled.json"
    if len(sys.argv) > 1:
        manifest = Path(sys.argv[1])
    errors = verify(manifest)
    if errors:
        for e in errors:
            print("FAIL:", e)
        return 1
    print(f"HASH VERIFIED: {len(json.loads(manifest.read_text(encoding='utf-8'))['artifacts'])} artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
