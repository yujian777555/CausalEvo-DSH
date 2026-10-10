"""Per-task isolated workspaces.

Every task execution gets a fresh directory copied from the pristine task
workspace. The factory records a snapshot digest before/after so tests can
prove reset actually happened (RISK-3: replay must recreate state, not just
reuse a session). Sealed tests and reference fixes live OUTSIDE the
agent-visible workspace and are only injected by the judge.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .task_spec import TaskSpec


def tree_digest(root: Path) -> str:
    """Deterministic digest over (relative path, content) of every file."""
    h = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            h.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
            h.update(b"\0")
            h.update(path.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


@dataclass(slots=True)
class Workspace:
    root: Path
    digest_at_open: str

    def digest(self) -> str:
        return tree_digest(self.root)

    def reset(self, spec: TaskSpec) -> None:
        """Restore the pristine task workspace (full recreate)."""
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)
        _copy_tree(spec.workspace_dir, self.root)
        self.digest_at_open = self.digest()


class WorkspaceFactory:
    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = base_dir or Path(tempfile.mkdtemp(prefix="ceval-ws-"))
        self._base.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        return self._base

    def create(self, spec: TaskSpec, run_id: str) -> Workspace:
        spec.verify_hashes()  # pristine source integrity before copying
        root = self._base / f"{run_id}--{spec.task_id}"
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True)
        _copy_tree(spec.workspace_dir, root)
        return Workspace(root=root, digest_at_open=tree_digest(root))

    def destroy_all(self) -> None:
        if self._base.exists():
            shutil.rmtree(self._base, ignore_errors=True)


def _copy_tree(src: Path, dst: Path) -> None:
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, target)
