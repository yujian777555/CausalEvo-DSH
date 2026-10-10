"""Workspace isolation guarantees (offline, no key)."""

import shutil
from pathlib import Path

import pytest

from causalevo.eval.task_spec import TaskSpecError, load_all_tasks, load_task
from causalevo.eval.workspace_factory import WorkspaceFactory, tree_digest

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = REPO_ROOT / "benchmarks" / "tasks"
SPECS = load_all_tasks(TASKS_DIR)


def _factory(tmp_path) -> WorkspaceFactory:
    return WorkspaceFactory(base_dir=tmp_path / "ws")


def test_create_copies_pristine_workspace(tmp_path):
    spec = SPECS[0]
    ws = _factory(tmp_path).create(spec, run_id="r1")
    assert ws.root.is_dir()
    assert ws.digest() == tree_digest(spec.workspace_dir)
    assert ws.digest_at_open == ws.digest()
    assert (ws.root / spec.entry_file).read_bytes() == (
        spec.workspace_dir / spec.entry_file
    ).read_bytes()


def test_reset_restores_pristine_digest(tmp_path):
    """RISK-3: reset is a full recreate, not a session reuse."""
    spec = SPECS[0]
    ws = _factory(tmp_path).create(spec, run_id="r1")
    pristine = ws.digest_at_open
    target = ws.root / spec.entry_file
    target.write_text(target.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    (ws.root / "stray.py").write_text("x = 1\n", encoding="utf-8")
    assert ws.digest() != pristine
    ws.reset(spec)
    assert ws.digest() == pristine
    assert ws.digest_at_open == pristine
    assert not (ws.root / "stray.py").exists()


def test_two_workspaces_for_same_task_are_independent(tmp_path):
    spec = SPECS[0]
    factory = _factory(tmp_path)
    ws_a = factory.create(spec, run_id="r1")
    ws_b = factory.create(spec, run_id="r2")
    assert ws_a.root != ws_b.root
    digest_b = ws_b.digest()
    target = ws_a.root / spec.entry_file
    target.write_text("broken\n", encoding="utf-8")
    assert ws_a.digest() != digest_b
    assert ws_b.digest() == digest_b


def test_workspace_excludes_sealed_tests_and_reference(tmp_path):
    for spec in SPECS:
        ws = _factory(tmp_path / spec.task_id).create(spec, run_id="r1")
        for path in ws.root.rglob("*"):
            segments = set(path.relative_to(ws.root).parts)
            assert "sealed" not in segments
            assert "reference" not in segments
            assert path.name not in {"sealed_tests.py", "solution_fixed.py"}


def test_tree_digest_deterministic_and_content_sensitive(tmp_path):
    tree = tmp_path / "tree"
    (tree / "sub").mkdir(parents=True)
    (tree / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tree / "sub" / "b.py").write_text("y = 2\n", encoding="utf-8")
    first = tree_digest(tree)
    assert tree_digest(tree) == first
    (tree / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert tree_digest(tree) != first


def test_create_verifies_source_hashes(tmp_path):
    """Corrupt a COPY of a task dir: create() must refuse the tampered source."""
    src = SPECS[0].task_dir
    tampered = tmp_path / "task"
    shutil.copytree(src, tampered)
    target = tampered / "workspace" / SPECS[0].entry_file
    target.write_text(target.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    with pytest.raises(TaskSpecError):
        load_task(tampered, verify=True)
    spec = load_task(tampered, verify=False)
    with pytest.raises(TaskSpecError):
        _factory(tmp_path).create(spec, run_id="r1")


def test_destroy_all_removes_base_dir(tmp_path):
    factory = _factory(tmp_path)
    factory.create(SPECS[0], run_id="r1")
    assert factory.base_dir.is_dir()
    factory.destroy_all()
    assert not factory.base_dir.exists()
