"""Build a deterministic cross-run SHA-256 manifest for the R1.12 replication
(P4-R1.12-REVIEW-FIX1 Task A).

Computes hashes for the frozen protocol, analysis script, pilot artifacts and
canary artifacts, writing results/phase4/live2/<pilot>/manifest_reconciled.json.
The reconciled manifest itself is never hashed inside itself (no self-reference).
"""
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PILOT = REPO / "results" / "phase4" / "live2" / "phase4-r12-replication-pilot-20261027T034229Z"
CANARY = REPO / "results" / "phase4" / "live2" / "phase4-r12-replication-canary-20261027T034020Z"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    entries = {}
    for label, path in [
        ("protocol", REPO / "docs" / "PHASE4_R1_12_REPLICATION_PROTOCOL.md"),
        ("analysis_script", REPO / "scripts" / "analyze_r12_replication.py"),
        ("pilot_tasks", PILOT / "tasks.jsonl"),
        ("pilot_events", PILOT / "events.jsonl"),
        ("pilot_ledger", PILOT / "proxy-ledger" / "ledger.jsonl"),
        ("pilot_controller_state", PILOT / "controller_state.json"),
        ("pilot_analysis", PILOT / "analysis.json"),
        ("canary_tasks", CANARY / "tasks.jsonl"),
        ("canary_events", CANARY / "events.jsonl"),
        ("canary_ledger", CANARY / "proxy-ledger" / "ledger.jsonl"),
        ("canary_manifest", CANARY / "manifest.json"),
        ("pilot_original_manifest", PILOT / "manifest.json"),
    ]:
        if not path.is_file():
            raise FileNotFoundError(f"required artifact missing: {path}")
        entries[label] = {"path": str(path.relative_to(REPO)).replace("\\", "/"),
                          "sha256": sha(path)}
    out = {
        "reconciled_by": "scripts/build_r12_manifest.py",
        "note": "cross-run SHA-256 manifest for R1.12; this file itself is not hashed inside itself (no self-reference)",
        "artifacts": entries,
    }
    (PILOT / "manifest_reconciled.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("reconciled manifest written:", PILOT / "manifest_reconciled.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
