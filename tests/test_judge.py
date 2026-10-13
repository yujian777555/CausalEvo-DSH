"""Judge tests: real microtasks graded via LocalTrustedExecutor (offline).

Trusted in-repo content only: oracle copies the sealed reference fix purely as
engineering validation that the judge can pass correct code; no model involved.
"""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from causalevo.eval.executor import LocalTrustedExecutor
from causalevo.eval.judge import Judge
from causalevo.eval.task_spec import load_task
from causalevo.eval.workspace_factory import WorkspaceFactory

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = REPO_ROOT / "benchmarks" / "tasks"
TASK_ID = "micro-000-clamp_value"


@pytest.fixture
def judge() -> Judge:
    return Judge(LocalTrustedExecutor.for_trusted_content())


def _make_workspace(spec, tmp_path: Path):
    return WorkspaceFactory(base_dir=tmp_path).create(spec, "pytest")


def test_oracle_fix_passes_visible_and_sealed(judge, tmp_path):
    spec = load_task(TASKS_DIR / TASK_ID)
    ws = _make_workspace(spec, tmp_path)
    shutil.copyfile(spec.reference_fixed, ws.root / spec.entry_file)
    report = judge.grade(spec, ws.root)
    assert report.visible_passed is True
    assert report.sealed_passed is True
    assert report.task_succeeded is True
    assert report.invalid_reason is None
    assert report.timed_out is False
    assert report.visible_failures == [] and report.sealed_failures == []
    assert report.executor == "local-trusted"


def test_buggy_workspace_fails_honestly_not_invalid(judge, tmp_path):
    spec = load_task(TASKS_DIR / TASK_ID)
    ws = _make_workspace(spec, tmp_path)  # untouched buggy solution.py
    report = judge.grade(spec, ws.root)
    assert report.visible_passed is False
    assert report.sealed_passed is False
    assert report.task_succeeded is False
    assert report.invalid_reason is None  # honest test failure, not invalid
    assert report.timed_out is False


def test_syntax_broken_workspace_is_invalid(judge, tmp_path):
    spec = load_task(TASKS_DIR / TASK_ID)
    ws = _make_workspace(spec, tmp_path)
    (ws.root / spec.entry_file).write_text("def broken(:\n", encoding="utf-8")
    report = judge.grade(spec, ws.root)
    assert report.invalid_reason is not None
    assert report.visible_passed is False
    assert report.sealed_passed is False
    assert report.task_succeeded is False
    assert report.timed_out is False


def test_sealed_tests_never_enter_agent_workspace(judge, tmp_path):
    spec = load_task(TASKS_DIR / TASK_ID)
    ws = _make_workspace(spec, tmp_path)
    judge.grade(spec, ws.root)
    files = [p for p in ws.root.rglob("*") if p.is_file()]
    assert [p.name for p in files] == [spec.entry_file]
    assert not any("sealed" in p.name for p in ws.root.rglob("*"))


def test_judge_copy_removed_after_grade(judge, tmp_path):
    spec = load_task(TASKS_DIR / TASK_ID)
    ws = _make_workspace(spec, tmp_path)
    judge_dir = ws.root.parent / (ws.root.name + ".judge")
    judge.grade(spec, ws.root)
    assert not judge_dir.exists()
    assert list(tmp_path.glob("*.judge")) == []


def test_failure_names_parsed_for_wrong_edit(judge, tmp_path):
    spec = load_task(TASKS_DIR / TASK_ID)
    ws = _make_workspace(spec, tmp_path)
    (ws.root / spec.entry_file).write_text(
        "def clamp_value(x, lo, hi):\n    return min(max(x, lo), hi) + 1\n",
        encoding="utf-8")
    report = judge.grade(spec, ws.root)
    assert report.visible_passed is False
    assert report.visible_failures == ["inside"]  # the single visible check
    assert report.sealed_passed is False
    assert "below" in report.sealed_failures
    assert report.invalid_reason is None


class _RecordingExecutor:
    """Delegates to LocalTrustedExecutor but keeps each ExecResult."""

    kind = "local-trusted"

    def __init__(self) -> None:
        self._inner = LocalTrustedExecutor.for_trusted_content()
        self.results = []

    def run(self, workdir, argv, timeout_s):
        result = self._inner.run(workdir, argv, timeout_s)
        self.results.append(result)
        return result


def test_hanging_import_times_out(tmp_path):
    task_dir = tmp_path / TASK_ID
    shutil.copytree(TASKS_DIR / TASK_ID, task_dir)
    solution = task_dir / "workspace" / "solution.py"
    solution.write_text(
        "import time\ntime.sleep(60)\n" + solution.read_text(encoding="utf-8"),
        encoding="utf-8")
    meta = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    meta["timeout_s"] = 2  # keep the test fast
    meta["hashes"]["workspace/solution.py"] = hashlib.sha256(
        solution.read_bytes()).hexdigest()  # re-pin so the integrity gate passes
    (task_dir / "task.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    spec = load_task(task_dir)

    executor = _RecordingExecutor()
    report = Judge(executor).grade(spec, spec.workspace_dir)
    assert report.timed_out is True
    assert report.task_succeeded is False
    assert report.invalid_reason is None
    assert executor.results[0].timed_out is True
    assert executor.results[0].exit_code is None
