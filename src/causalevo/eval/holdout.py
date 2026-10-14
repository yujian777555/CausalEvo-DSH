"""Private holdout store (R1.6-G3).

Holdout tasks live OUTSIDE the git repository (default: sibling directory
`../CausalEvo-DSH-holdout`, overridable via CE_DSH_HOLDOUT_DIR). They are:
- never committed (only hashes enter git, in benchmarks/holdout_manifest.json)
- never mounted into the agent container (the agent gets a workspace COPY only)
- readable by the judge via load path
- hash-pinned and split-fixed at creation time
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .task_spec import TaskSpec, load_task

DEFAULT_STORE = Path(__file__).resolve().parents[3].parent / "CausalEvo-DSH-holdout"
MANIFEST_PATH = Path(__file__).resolve().parents[3] / "benchmarks" / "holdout_manifest.json"


def store_root(env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    override = env.get("CE_DSH_HOLDOUT_DIR", "").strip()
    return Path(override).resolve() if override else DEFAULT_STORE.resolve()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_holdout_task(root: Path, *, task_id: str, split: str, function: str,
                       instructions: str, buggy: str, fixed: str,
                       visible: str, sealed: str) -> Path:
    """Create one holdout task directory (content never enters git)."""
    tdir = root / task_id
    (tdir / "workspace").mkdir(parents=True, exist_ok=True)
    (tdir / "sealed").mkdir(exist_ok=True)
    (tdir / "reference").mkdir(exist_ok=True)
    (tdir / "workspace" / "solution.py").write_text(buggy, encoding="utf-8", newline="\n")
    (tdir / "visible_tests.py").write_text(visible, encoding="utf-8", newline="\n")
    (tdir / "sealed" / "sealed_tests.py").write_text(sealed, encoding="utf-8", newline="\n")
    (tdir / "reference" / "solution_fixed.py").write_text(fixed, encoding="utf-8", newline="\n")
    hashes = {
        "workspace/solution.py": _sha256(tdir / "workspace" / "solution.py"),
        "visible_tests.py": _sha256(tdir / "visible_tests.py"),
        "sealed/sealed_tests.py": _sha256(tdir / "sealed" / "sealed_tests.py"),
        "reference/solution_fixed.py": _sha256(tdir / "reference" / "solution_fixed.py"),
    }
    meta = {
        "task_id": task_id, "split": split, "function": function,
        "bug_class": "holdout-unspecified",
        "instructions": instructions, "entry_file": "solution.py",
        "timeout_s": 30, "hashes": hashes, "holdout": True,
    }
    (tdir / "task.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return tdir


def manifest(root: Path) -> dict:
    """Hashes-only manifest: proves content integrity without revealing it."""
    tasks = []
    for tdir in sorted(root.iterdir()):
        if not tdir.is_dir():
            continue
        meta = json.loads((tdir / "task.json").read_text(encoding="utf-8"))
        tasks.append({
            "task_id": meta["task_id"],
            "split": meta["split"],
            "function": meta["function"],
            "hashes": meta["hashes"],
        })
    return {
        "kind": "private-holdout",
        "content_policy": "hashes only; task content lives outside git and is never mounted into the agent container",
        "store_hint": "CE_DSH_HOLDOUT_DIR or sibling ../CausalEvo-DSH-holdout",
        "count": len(tasks),
        "tasks": tasks,
    }


def write_manifest(root: Path, path: Path = MANIFEST_PATH) -> dict:
    m = manifest(root)
    path.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return m


def load_holdout_tasks(root: Path | None = None) -> list[TaskSpec]:
    root = root or store_root()
    specs = [load_task(d) for d in sorted(root.iterdir()) if d.is_dir()]
    if not specs:
        raise FileNotFoundError(f"no holdout tasks under {root}")
    return specs


def verify_holdout(root: Path | None = None) -> bool:
    """Every task's files match their pinned hashes."""
    for spec in load_holdout_tasks(root):
        spec.verify_hashes()
    return True
