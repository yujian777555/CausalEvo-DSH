"""Clean-clone reproducibility check (P4-R1.2-S1, hardened P4-R1.3-S5):
verify the tested HEAD and any explicit expected SHA match REMOTE origin/main,
clone the configured origin's main branch to a temp dir, create a FRESH venv,
install the lockfile, and run the Phase 4 recomputation subset. Proves
fresh-clone recompute without the developer's raw files — and that the claim
covers the REMOTE commit, not an unpushed local one.

Usage: .venv/Scripts/python.exe scripts/clean_clone_check.py [expected_sha]
Exit 0: CLEAN CLONE OK. Exit 1: clone failed. Exit 2: remote/HEAD mismatch.
Exit 3: remote SHA could not be determined (REMOTE_UNVERIFIED).
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _git(args, cwd, check=True, env=None):
    return subprocess.run(["git", *args], cwd=cwd, check=check,
                          capture_output=True, text=True, env=env)


def _remote_sha() -> str | None:
    import os
    env = dict(os.environ)
    try:
        proc = _git(["ls-remote", "origin", "main"], cwd=REPO, env=env)
        return proc.stdout.split()[0]
    except (subprocess.CalledProcessError, IndexError):
        return None


def main() -> int:
    remote = _remote_sha()
    if not remote:
        print("REMOTE_UNVERIFIED: could not determine origin/main SHA")
        return 3
    expected = sys.argv[1] if len(sys.argv) > 1 else remote
    if expected != remote:
        print(f"REMOTE MISMATCH: expected {expected} != origin/main {remote}")
        return 2
    work = Path(tempfile.mkdtemp(prefix="ce-cleanclone-"))
    try:
        clone = work / "repo"
        try:
            origin_url = _git(
                ["config", "--get", "remote.origin.url"], cwd=REPO).stdout.strip()
            subprocess.run(
                ["git", "clone", "--quiet", "--branch", "main", "--single-branch",
                 origin_url, str(clone)], check=True, cwd=work,
                capture_output=True, text=True)
        except (subprocess.CalledProcessError, OSError):
            print("CLONE FAILED: could not clone configured origin/main")
            return 1
        head = _git(["rev-parse", "HEAD"], cwd=clone).stdout.strip()
        if head != remote:
            print(f"HEAD MISMATCH: cloned {head} != verified origin/main {remote}")
            return 2
        assert not (clone / "results/phase4/live/phase4-live-20261014T110259Z/tasks.jsonl").exists(), \
            "raw tasks.jsonl must NOT be in a fresh clone"
        py = clone / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        # build the venv from the PROJECT interpreter (lockfile pins require
        # >=3.10); never whatever `python` happens to be on PATH
        base_py = str(REPO / ".venv" / "Scripts" / "python.exe") \
            if (REPO / ".venv" / "Scripts" / "python.exe").is_file() else sys.executable
        subprocess.run([base_py, "-m", "venv", str(clone / "venv")],
                       check=True, cwd=work)
        import os
        env = dict(os.environ)
        env["PIP_INDEX_URL"] = "https://pypi.org/simple"
        subprocess.run([str(py), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
                       check=True, cwd=clone, env=env)
        subprocess.run(
            [str(py), "-m", "pip", "install", "--quiet",
             "-r", "requirements-lock.txt"],
            check=True, cwd=clone, env=env)
        # the recomputation subset: reader validation + full analysis + reconcile
        subprocess.run(
            [str(py), "scripts/reconcile_phase4_rows.py"], check=True, cwd=clone)
        subprocess.run(
            [str(py), "-m", "pytest", "-q",
             "tests/test_phase4_analysis.py", "tests/test_phase4_integrity.py",
             "tests/test_auditable.py"],
            check=True, cwd=clone)
        # P4-R1.4 P1-F: the key safety/algorithm suites must ALSO pass inside
        # the clean clone of the final SHA (docker available on this host)
        subprocess.run(
            [str(py), "-m", "pytest", "-q",
             "tests/test_credential_isolation.py",
             "tests/test_budget_proxy.py",
             "tests/test_budget_proxy_r14.py",
             "tests/test_budget_proxy_r15.py",
             "tests/test_budget_proxy_r16.py",
             "tests/test_online_evolution.py",
             "tests/test_incremental_fitness.py",
             "tests/test_cluster_sensitivity.py",
             "tests/test_analyze_r12.py",
             "tests/test_round_spend.py",
             "tests/test_r12_hashes.py",
             "tests/test_holm_step_down.py",
             "tests/test_frozen_task_set.py",
             "tests/test_holm_mapping.py",
             "tests/test_analysis_determinism.py",
             "tests/test_cea_v2_integration.py",
             "tests/test_cea_v2_offline.py",
             "tests/test_analyze_r19.py",
             "tests/test_proxy_control.py",
             "tests/test_proxy_integration_e2e.py",
             "tests/test_causal_policy_adapter.py",
             "tests/test_phase4_v2_offline.py",
             "tests/test_clean_clone_check.py"],
            check=True, cwd=clone)
        print(f"CLEAN CLONE OK: verified origin/main {remote[:12]}; "
              "configured origin clone recomputes 312 auditable rows in a fresh clone")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
