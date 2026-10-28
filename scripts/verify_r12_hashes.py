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


def verify(manifest_path: Path) -> list[str]:
    errors = []
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    for label, entry in doc.get("artifacts", {}).items():
        rel = entry.get("path")
        expected = entry.get("sha256")
        if not isinstance(rel, str):
            errors.append(f"{label}: invalid path {rel!r}")
            continue
        rel_posix = rel.replace("\\", "/")
        if not rel_posix.startswith(ALLOWED_PREFIXES):
            errors.append(f"{label}: path traversal / not-allowed path {rel!r}")
            continue
        path = (REPO / rel_posix).resolve()
        if not str(path).startswith(str(REPO)):
            errors.append(f"{label}: path escapes repo root {rel!r}")
            continue
        if not path.is_file():
            errors.append(f"{label}: missing file {rel}")
            continue
        actual = sha(path)
        if actual != expected:
            errors.append(f"{label}: hash mismatch {rel} (expected {expected}, actual {actual})")
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
