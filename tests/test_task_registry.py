"""Microtask registry audits: count, splits, hashes, leak/containment checks (offline)."""

import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from causalevo.eval.task_spec import TaskSpecError, load_all_tasks, load_task

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = REPO_ROOT / "benchmarks" / "tasks"
REGISTRY_PATH = REPO_ROOT / "benchmarks" / "registry.json"

SPLIT_QUOTA = {"train": 13, "dev": 7, "sealed_test": 6}
SPLIT_SEED = 20261010


@pytest.fixture(scope="module")
def registry():
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def specs():
    return load_all_tasks(TASKS_DIR, verify=True)


def test_exactly_26_tasks_on_disk_and_each_loadable(registry):
    task_dirs = sorted(d for d in TASKS_DIR.iterdir() if d.is_dir())
    assert len(task_dirs) == 26
    assert registry["microtasks"]["count"] == 26
    assert len(registry["microtasks"]["tasks"]) == 26
    for d in task_dirs:
        spec = load_task(d, verify=True)  # raises on any hash mismatch
        assert spec.task_id == d.name


def test_split_quotas_and_registry_splits_match_per_task_fields(specs, registry):
    assert Counter(s.split for s in specs) == SPLIT_QUOTA
    actual = {s.task_id: s.split for s in specs}
    recorded = registry["microtasks"]["splits"]
    assert set(recorded) == set(SPLIT_QUOTA)
    for split, quota in SPLIT_QUOTA.items():
        ids = sorted(recorded[split])
        assert len(ids) == quota
        assert ids == sorted(tid for tid, s in actual.items() if s == split)


def test_split_seed_recorded(registry):
    assert registry["microtasks"]["split_seed"] == SPLIT_SEED


def test_registry_task_entries_match_specs(specs, registry):
    by_id = {s.task_id: s for s in specs}
    for entry in registry["microtasks"]["tasks"]:
        spec = by_id[entry["task_id"]]
        assert entry["split"] == spec.split
        assert entry["function"] == spec.function
        assert entry["bug_class"] == spec.bug_class
        assert entry["hashes"] == spec.hashes


def test_function_and_bug_class_all_unique(specs):
    """Template-leak dedup audit: no two tasks share a function or bug class."""
    functions = [s.function for s in specs]
    bug_classes = [s.bug_class for s in specs]
    assert len(set(functions)) == len(functions) == 26
    assert len(set(bug_classes)) == len(bug_classes) == 26


def test_hash_pin_detects_single_byte_flip(tmp_path):
    src = sorted(d for d in TASKS_DIR.iterdir() if d.is_dir())[0]
    copied = tmp_path / src.name
    shutil.copytree(src, copied)
    load_task(copied, verify=True)  # control: untouched copy verifies
    target = copied / "workspace" / "solution.py"
    data = target.read_bytes()
    target.write_bytes(bytes([data[0] ^ 0xFF]) + data[1:])
    with pytest.raises(TaskSpecError, match="hash mismatch"):
        load_task(copied, verify=True)
    load_task(copied, verify=False)  # metadata still parses without verification


def test_sealed_checks_do_not_leak_into_agent_visible_text(specs):
    for spec in specs:
        sealed_lines = [
            line.strip()
            for line in spec.sealed_tests.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("check(")
        ]
        assert sealed_lines, f"{spec.task_id}: no sealed check expressions found"
        visible_text = spec.visible_tests.read_text(encoding="utf-8")
        for line in sealed_lines:
            assert line not in spec.instructions, f"{spec.task_id}: leak in instructions"
            assert line not in visible_text, f"{spec.task_id}: leak in visible_tests.py"


def test_workspace_contains_only_entry_file(specs):
    """sealed/ and reference/ must stay outside the agent-visible workspace."""
    for spec in specs:
        assert sorted(p.name for p in spec.workspace_dir.iterdir()) == ["solution.py"]
        assert not (spec.workspace_dir / "sealed").exists()
        assert not (spec.workspace_dir / "reference").exists()
        assert spec.workspace_dir not in spec.sealed_tests.parents
        assert spec.workspace_dir not in spec.reference_fixed.parents


def test_timeout_positive_and_entry_file_is_solution_py(specs):
    for spec in specs:
        assert spec.timeout_s > 0
        assert spec.entry_file == "solution.py"
