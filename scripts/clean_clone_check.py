"""Clean-clone reproducibility check (P4-R1.2-S1): clone the repo to a temp
dir, create a FRESH venv, install the lockfile, run the Phase 4 recomputation
subset. Proves fresh-clone recompute without the developer's raw files.

Usage: .venv/Scripts/python.exe scripts/clean_clone_check.py
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="ce-cleanclone-"))
    try:
        clone = work / "repo"
        subprocess.run(["git", "clone", "--quiet", str(REPO), str(clone)],
                       check=True, cwd=work)
        assert not (clone / "results/phase4/live/phase4-live-20261014T110259Z/tasks.jsonl").exists(), \
            "raw tasks.jsonl must NOT be in a fresh clone"
        py = clone / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run([sys.executable, "-m", "venv", str(clone / "venv")],
                       check=True, cwd=work)
        subprocess.run(
            [str(py), "-m", "pip", "install", "--quiet",
             "-r", "requirements-lock.txt"],
            check=True, cwd=clone)
        # the recomputation subset: reader validation + full analysis + reconcile
        subprocess.run(
            [str(py), "scripts/reconcile_phase4_rows.py"], check=True, cwd=clone)
        subprocess.run(
            [str(py), "-m", "pytest", "-q",
             "tests/test_phase4_analysis.py", "tests/test_phase4_integrity.py",
             "tests/test_auditable.py"],
            check=True, cwd=clone)
        print("CLEAN CLONE OK: 312 auditable rows recompute in a fresh clone")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
