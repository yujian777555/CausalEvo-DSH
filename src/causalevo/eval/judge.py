"""Independent judge: runs AFTER the agent, on an isolated copy, deciding task
success. The judge never sees policy identity (blinding) and sealed tests are
injected only into the judge-side copy, never into the agent workspace.

Outcome states (plan P1.3): api_response_observed / tool_executed /
task_completed / visible_tests_passed / sealed_tests_passed / invalid /
timeout / budget_stop. finish_reason=completed or a model claiming success is
NOT task success.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .executor import Executor
from .task_spec import TaskSpec

ALL_STATES = (
    "api_response_observed", "tool_executed", "task_completed",
    "visible_tests_passed", "sealed_tests_passed", "invalid", "timeout",
    "budget_stop",
)


@dataclass(slots=True)
class JudgeReport:
    task_id: str
    visible_passed: bool
    sealed_passed: bool
    visible_failures: list[str] = field(default_factory=list)
    sealed_failures: list[str] = field(default_factory=list)
    invalid_reason: str | None = None
    timed_out: bool = False
    executor: str = ""
    duration_ms: int = 0

    @property
    def task_succeeded(self) -> bool:
        return self.visible_passed and self.sealed_passed and not self.invalid_reason and not self.timed_out


def _parse_failures(stdout: str) -> list[str]:
    return [line[5:].split(":", 1)[0] for line in stdout.splitlines()
            if line.startswith("FAIL ")]


class Judge:
    def __init__(self, executor: Executor) -> None:
        self.executor = executor

    def grade(self, spec: TaskSpec, candidate_workspace: Path) -> JudgeReport:
        """Grade the candidate workspace. `candidate_workspace` is treated as
        read-only input; tests run on a judge-side copy."""
        spec.verify_hashes()  # pristine source must be intact after the agent ran
        judge_dir = candidate_workspace.parent / (candidate_workspace.name + ".judge")
        if judge_dir.exists():
            shutil.rmtree(judge_dir)
        shutil.copytree(candidate_workspace, judge_dir)
        try:
            solution = judge_dir / spec.entry_file
            if not solution.is_file():
                return JudgeReport(spec.task_id, False, False,
                                   invalid_reason=f"missing {spec.entry_file}",
                                   executor=self.executor.kind)
            # Import sanity: broken syntax -> invalid, not a test failure.
            probe = self.executor.run(
                judge_dir, ["python", "-c", f"import {spec.entry_file[:-3]}"],
                timeout_s=spec.timeout_s)
            if probe.timed_out:
                return JudgeReport(spec.task_id, False, False, timed_out=True,
                                   executor=self.executor.kind, duration_ms=probe.duration_ms)
            if probe.exit_code != 0:
                return JudgeReport(spec.task_id, False, False,
                                   invalid_reason="import failed: " + probe.stderr[-300:],
                                   executor=self.executor.kind)

            visible = self._run_tests(spec, judge_dir, spec.visible_tests, "visible")
            sealed = self._run_tests(spec, judge_dir, spec.sealed_tests, "sealed")
            return JudgeReport(
                task_id=spec.task_id,
                visible_passed=visible[0], sealed_passed=sealed[0],
                visible_failures=visible[1], sealed_failures=sealed[1],
                timed_out=visible[2] or sealed[2],
                executor=self.executor.kind,
                duration_ms=probe.duration_ms + visible[3] + sealed[3],
            )
        finally:
            shutil.rmtree(judge_dir, ignore_errors=True)

    def _run_tests(self, spec: TaskSpec, judge_dir: Path, test_file: Path,
                   label: str) -> tuple[bool, list[str], bool, int]:
        target = judge_dir / f"_{label}_tests.py"
        shutil.copyfile(test_file, target)
        result = self.executor.run(judge_dir, ["python", target.name],
                                   timeout_s=spec.timeout_s)
        target.unlink(missing_ok=True)
        if result.timed_out:
            return False, [], True, result.duration_ms
        passed = result.exit_code == 0
        return passed, ([] if passed else _parse_failures(result.stdout)), False, result.duration_ms
