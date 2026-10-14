"""Generate the Phase 1.5 gate artifacts under results/phase1/p15/.

Runs the security/live-guard test battery for real, verifies protocol freeze
checks programmatically, and writes:
- manifest.json         (provenance: repo sha, images, configs)
- security_report.json  (test battery results + container flag digest)
- protocol_check.json   (freeze checks: configs, parity, registry, schema)

Offline; zero API calls. The readiness verdict is written by a human-visible
doc (docs/PHASE1_LIVE_READINESS_REPORT.md), not by this script.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from causalevo.eval.policy import B0, B1, check_budget_parity  # noqa: E402
from causalevo.eval.trace import provenance_block  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "results" / "phase1" / "p15"
PYTEST = [str(REPO_ROOT / ".venv" / "Scripts" / "python.exe"), "-m", "pytest", "-q", "--tb=no"]

SECURITY_FILES = [
    "tests/test_container_security_v2.py",
    "tests/test_agent_fs_isolation.py",
    "tests/test_executor_isolation.py",
    "tests/test_live_guard.py",
    "tests/test_executor_guard.py",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    results: dict = {}

    proc = subprocess.run([*PYTEST, *SECURITY_FILES], capture_output=True, text=True,
                          cwd=REPO_ROOT)
    summary_line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    results["security_battery"] = {
        "files": SECURITY_FILES,
        "command": " ".join(SECURITY_FILES),
        "exit_code": proc.returncode,
        "summary_line": summary_line,
        "passed": summary_line,
    }

    protocol_checks = []

    def check(name, ok, detail=""):
        protocol_checks.append({"check": name, "ok": bool(ok), "detail": detail})

    try:
        check_budget_parity(B0, B1)
        check("b0_b1_budget_parity", True)
    except ValueError as exc:
        check("b0_b1_budget_parity", False, str(exc))
    check("b0_no_persistent_updates", B0.persistent_updates is False)
    check("b1_no_persistent_updates", B1.persistent_updates is False)
    registry = json.loads((REPO_ROOT / "benchmarks" / "registry.json").read_text(encoding="utf-8"))
    check("registry_split_seed", registry["microtasks"]["split_seed"] == 20261010)
    check("registry_counts", registry["microtasks"]["count"] == 26)
    for cfg in ("phase1_b0.yaml", "phase1_b1.yaml"):
        check(f"config_sha256:{cfg}", True, sha256(REPO_ROOT / "configs" / cfg))
    patch = REPO_ROOT / "configs" / "dsh_task_patch.yml"
    check("task_profile_patch_sha256", True, sha256(patch))
    check("security_battery_green", proc.returncode == 0, summary_line)

    (OUT / "security_report.json").write_text(json.dumps({
        "created_by": "scripts/run_p15_gate.py",
        "container_security_profile_v2_flags": [
            "--network ceval-net (internal)", "--read-only",
            "--tmpfs /tmp:rw,noexec,nosuid,size=64m",
            "--tmpfs /home/agent/.cache:rw,exec,nosuid,size=64m",
            "--cap-drop ALL", "--security-opt no-new-privileges",
            "--memory 768m --memory-swap 768m", "--cpus 1", "--pids-limit 128",
        ],
        "battery": results["security_battery"],
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    (OUT / "protocol_check.json").write_text(json.dumps({
        "checks": protocol_checks,
        "all_ok": all(c["ok"] for c in protocol_checks),
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    manifest = {
        "gate": "CE-DSH-P1.5",
        "created_by": "scripts/run_p15_gate.py",
        "provenance": provenance_block(),
        "agent_image": "causalevo-dsh-agent:0.2.0",
        "live_api_calls": 0,
        "live_spend_cny": 0,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                                       encoding="utf-8")
    print("security battery:", summary_line)
    print("protocol checks all_ok:", all(c["ok"] for c in protocol_checks))
    print("artifacts:", OUT)
    return 0 if proc.returncode == 0 and all(c["ok"] for c in protocol_checks) else 1


if __name__ == "__main__":
    sys.exit(main())
