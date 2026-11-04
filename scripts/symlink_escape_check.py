import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LIVE2 = REPO / "results" / "phase4" / "live2"
MANIFEST = LIVE2 / "phase4-r12-replication-pilot-20261027T034229Z" / "manifest_reconciled.json"


def main():
    link_dir = None
    try:
        link_dir = Path(tempfile.mkdtemp(prefix="symlink-escape-check-", dir=LIVE2))
        link = link_dir / "tasks.jsonl"
        link.symlink_to(REPO / "status.json")
        doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
        doc["artifacts"]["pilot_tasks"]["path"] = str(link.relative_to(REPO)).replace("\\", "/")
        bad = link_dir / "bad.json"
        bad.write_text(json.dumps(doc), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "verify_r12_hashes.py"), str(bad)],
            cwd=REPO, capture_output=True, text=True, timeout=60,
        )
        print("exit_code:", proc.returncode)
        print(proc.stdout.strip() or proc.stderr.strip())
        assert proc.returncode != 0, "symlink escape must be rejected on Linux"
        assert "escapes allowed artifact root" in proc.stdout
    finally:
        if link_dir is not None:
            shutil.rmtree(link_dir)
    print("SYMLINK-ESCAPE-REJECTED-CONFIRMED-LINUX")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
