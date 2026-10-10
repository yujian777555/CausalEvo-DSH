"""TaskSpec: load/validate microtasks and verify pinned file hashes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

VALID_SPLITS = ("train", "dev", "sealed_test")


class TaskSpecError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TaskSpec:
    task_id: str
    split: str
    function: str
    bug_class: str
    instructions: str
    entry_file: str
    timeout_s: int
    task_dir: Path
    hashes: dict[str, str]

    @property
    def workspace_dir(self) -> Path:
        return self.task_dir / "workspace"

    @property
    def visible_tests(self) -> Path:
        return self.task_dir / "visible_tests.py"

    @property
    def sealed_tests(self) -> Path:
        """Judge-side only. Never mounted into an agent-visible workspace."""
        return self.task_dir / "sealed" / "sealed_tests.py"

    @property
    def reference_fixed(self) -> Path:
        return self.task_dir / "reference" / "solution_fixed.py"

    def verify_hashes(self) -> None:
        """Fail if any pinned file changed (integrity gate)."""
        for rel, expected in self.hashes.items():
            path = self.task_dir / rel
            if not path.is_file():
                raise TaskSpecError(f"{self.task_id}: missing {rel}")
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                raise TaskSpecError(
                    f"{self.task_id}: hash mismatch for {rel}: {actual[:12]} != {expected[:12]}"
                )


def load_task(task_dir: Path, *, verify: bool = True) -> TaskSpec:
    meta = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    if meta.get("split") not in VALID_SPLITS:
        raise TaskSpecError(f"{task_dir}: invalid split {meta.get('split')!r}")
    spec = TaskSpec(
        task_id=meta["task_id"],
        split=meta["split"],
        function=meta["function"],
        bug_class=meta["bug_class"],
        instructions=meta["instructions"],
        entry_file=meta["entry_file"],
        timeout_s=int(meta["timeout_s"]),
        task_dir=task_dir,
        hashes=meta["hashes"],
    )
    if verify:
        spec.verify_hashes()
    return spec


def load_all_tasks(tasks_dir: Path, *, verify: bool = True) -> list[TaskSpec]:
    specs = [load_task(d, verify=verify) for d in sorted(tasks_dir.iterdir()) if d.is_dir()]
    if not specs:
        raise TaskSpecError(f"no tasks found under {tasks_dir}")
    ids = [s.task_id for s in specs]
    if len(set(ids)) != len(ids):
        raise TaskSpecError("duplicate task ids")
    return specs
