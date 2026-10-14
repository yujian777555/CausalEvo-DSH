"""Private holdout store tests (P1.6). Offline; no containers needed for most."""

import json
import subprocess
from pathlib import Path

import pytest

from causalevo.eval import holdout
from causalevo.eval.holdout import (
    load_holdout_tasks,
    manifest,
    verify_holdout,
    write_holdout_task,
    write_manifest,
)

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "holdout-store"
    write_holdout_task(
        root, task_id="holdout-t1", split="holdout", function="double_it",
        instructions="fix double_it",
        buggy="def double_it(x):\n    return x\n",
        fixed="def double_it(x):\n    return 2 * x\n",
        visible="from solution import double_it\nassert double_it(2) == 2 or True\nprint('ok')\n",
        sealed="from solution import double_it\nassert double_it(3) == 6\nprint('ok')\n",
    )
    return root


def test_manifest_hashes_only_no_content(store):
    m = manifest(store)
    assert m["count"] == 1
    text = json.dumps(m)
    assert "def double_it" not in text, "manifest must not leak task content"
    assert "hashes" in m["tasks"][0]
    assert all(len(h) == 64 for h in m["tasks"][0]["hashes"].values())


def test_verify_passes_and_tamper_fails(store):
    assert verify_holdout(store) is True
    target = store / "holdout-t1" / "workspace" / "solution.py"
    target.write_text(target.read_text() + " ", encoding="utf-8")
    with pytest.raises(Exception):
        verify_holdout(store)


def test_load_and_splits(store):
    specs = load_holdout_tasks(store)
    assert specs[0].split == "holdout"
    assert specs[0].workspace_dir.is_dir()
    assert specs[0].sealed_tests.is_file()


def test_store_lives_outside_repo_and_untracked():
    root = holdout.DEFAULT_STORE
    assert REPO not in root.parents and root.parent != REPO, \
        f"default store {root} must be outside the repo"
    proc = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True)
    tracked = proc.stdout
    assert "CausalEvo-DSH-holdout" not in tracked
    assert "holdout-001" not in tracked or "holdout_manifest" in tracked


def test_real_store_created_and_verified():
    """The actual holdout store (created by scripts/create_holdout.py) verifies."""
    root = holdout.store_root()
    if not root.is_dir():
        pytest.skip("holdout store not created on this machine")
    assert verify_holdout(root) is True
    specs = load_holdout_tasks(root)
    assert len(specs) == 3


def test_agent_workspace_never_contains_holdout(store, tmp_path):
    """WorkspaceFactory copies only workspace/ — sealed/reference stay out."""
    from causalevo.eval.workspace_factory import WorkspaceFactory

    spec = load_holdout_tasks(store)[0]
    with pytest.MonkeyPatch.context() as mp:
        factory = WorkspaceFactory(tmp_path / "wsbase")
        ws = factory.create(spec, "t")
        names = [p.name for p in ws.root.rglob("*")]
        assert "sealed_tests.py" not in names
        assert "solution_fixed.py" not in names


def test_judge_can_grade_holdout_task(store, tmp_path):
    """Judge-side access works: oracle fix passes; bug fails."""
    from causalevo.eval.executor import LocalTrustedExecutor
    from causalevo.eval.judge import Judge
    from causalevo.eval.workspace_factory import WorkspaceFactory

    spec = load_holdout_tasks(store)[0]
    factory = WorkspaceFactory(tmp_path / "wsbase")
    judge = Judge(LocalTrustedExecutor.for_trusted_content())
    ws = factory.create(spec, "t1")
    report = judge.grade(spec, ws.root)
    assert not report.sealed_passed  # bug present -> sealed fails
    import shutil
    shutil.copyfile(spec.reference_fixed, ws.root / "solution.py")
    report2 = judge.grade(spec, ws.root)
    assert report2.task_succeeded
