import json
import subprocess
import sys
from pathlib import Path

doc = json.load(open("results/phase4/live2/phase4-r12-replication-pilot-20261027T034229Z/manifest_reconciled.json", encoding="utf-8"))
doc["artifacts"]["pilot_tasks"]["path"] = "results/phase4/live2/symlink-test-tmp/tasks.jsonl"
Path("/tmp/symlink-bad.json").write_text(json.dumps(doc), encoding="utf-8")
proc = subprocess.run([sys.executable, "scripts/verify_r12_hashes.py", "/tmp/symlink-bad.json"], capture_output=True, text=True)
print("exit_code:", proc.returncode)
print(proc.stdout.strip() or proc.stderr.strip())
assert proc.returncode == 1, "symlink escape must be rejected on Linux"
assert "escapes allowed artifact root" in proc.stdout
print("SYMLINK-ESCAPE-REJECTED-CONFIRMED-LINUX")
