"""Clean-clone reproducibility check (P4-R1.2-S1, hardened P4-R1.3-S5):
verify the tested HEAD matches the REMOTE origin/main (or an explicit target
SHA), clone to a temp dir, create a FRESH venv, install the lockfile, run the
Phase 4 recomputation subset. Proves fresh-clone recompute without the
developer's raw files — and that the claim covers the REMOTE commit, not an
unpushed local one.

Usage: .venv/Scripts/python.exe scripts/clean_clone_check.py [expected_sha]
Exit 0: CLEAN CLONE OK. Exit 2: remote/HEAD mismatch. Exit 3: remote SHA
could not be determined (REMOTE_UNVERIFIED).
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
    expected = sys.argv[1] if len(sys.argv) > 1 else _remote_sha()
    if not expected:
        print("REMOTE_UNVERIFIED: could not determine origin/main SHA")
        return 3
    work = Path(tempfile.mkdtemp(prefix="ce-cleanclone-"))
    try:
        clone = work / "repo"
        subprocess.run(["git", "clone", "--quiet", str(REPO), str(clone)],
                       check=True, cwd=work)
        head = _git(["rev-parse", "HEAD"], cwd=clone).stdout.strip()
        if head != expected:
            print(f"HEAD MISMATCH: cloned {head} != expected {expected} "
                  "(local commits not on origin/main)")
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
             "tests/test_proxy_control.py",
             "tests/test_proxy_integration_e2e.py",
             "tests/test_causal_policy_adapter.py",
             "tests/test_phase4_v2_offline.py"],
            check=True, cwd=clone)
        print(f"CLEAN CLONE OK: HEAD {expected[:12]} == origin/main; "
              "312 auditable rows recompute in a fresh clone")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
