"""Offline pipeline: schedule tasks x policy, run a fake agent, judge, trace.

The fake agent is deliberately dumb (noop / scripted wrong edit / oracle copy
for engineering validation). Its outcomes are pipeline evidence, never model
performance claims. Live provider calls are hard-blocked here: this module has
no code path that touches the network or an API key.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from .executor import Executor
from .judge import Judge
from .metrics import summarize_traces
from .policy import Policy
from .task_spec import TaskSpec
from .trace import (
    RunManifest,
    TaskTrace,
    TraceWriter,
    config_sha256,
    new_run_id,
    provenance_block,
)
from .workspace_factory import WorkspaceFactory


class FakeAgent:
    """Deterministic offline stand-in for a real model-driven agent.

    mode:
    - "noop": never edits (buggy code stays; judge must FAIL the task)
    - "break": writes syntactically broken code (judge must mark invalid)
    - "oracle": copies the sealed reference fix (engineering validation ONLY;
      proves the judge can pass correct code — not a model result)
    """

    def __init__(self, mode: str = "noop") -> None:
        if mode not in ("noop", "break", "oracle"):
            raise ValueError(f"unknown fake agent mode {mode!r}")
        self.mode = mode
        self.tool_calls = 0

    def act(self, spec: TaskSpec, workspace: Path, policy: Policy) -> dict[str, Any]:
        """One task attempt. Returns state flags for the trace.

        R2-S3: a fake agent never produces a real API response, so
        api_response_observed stays False; provider_kind/model_invoked are
        recorded at the trace level by run_offline.
        """
        states = {"api_response_observed": False, "tool_executed": False}
        attempts = policy.max_attempts_per_task if policy.allow_reflection else 1
        for _ in range(attempts):  # B1 consumes its second-budget attempt here
            if self.mode == "oracle":
                shutil.copyfile(spec.reference_fixed, workspace / spec.entry_file)
                states["tool_executed"] = True
            elif self.mode == "break":
                (workspace / spec.entry_file).write_text("def broken(:\n", encoding="utf-8")
                states["tool_executed"] = True
            self.tool_calls += 1 if states["tool_executed"] else 0
        return states


def run_offline(
    specs: list[TaskSpec],
    policy: Policy,
    judge: Judge,
    executor: Executor,
    out_dir: Path,
    fake_mode: str = "noop",
    split_seed: int = 0,
    run_id: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute every task under the given policy, judge independently, trace."""
    run_id = run_id or f"{policy.policy_id}-{new_run_id()}"
    run_dir = out_dir / run_id
    factory = WorkspaceFactory()
    writer = TraceWriter(run_dir)
    agent = FakeAgent(fake_mode)
    traces: list[dict[str, Any]] = []
    try:
        for spec in specs:
            ws = factory.create(spec, run_id)
            digest_before = ws.digest()
            states = {
                "api_response_observed": False,
                "tool_executed": False,
                "task_completed": False,
                "visible_tests_passed": False,
                "sealed_tests_passed": False,
                "invalid": False,
                "timeout": False,
                "budget_stop": False,
            }
            try:
                agent_states = agent.act(spec, ws.root, policy)
                states.update(agent_states)
                states["task_completed"] = True
            except Exception:
                states["invalid"] = True
            # Judge is independent: it receives only the workspace, never the policy.
            report = judge.grade(spec, ws.root)
            states["visible_tests_passed"] = report.visible_passed
            states["sealed_tests_passed"] = report.sealed_passed
            states["invalid"] = states["invalid"] or bool(report.invalid_reason)
            states["timeout"] = report.timed_out
            trace = TaskTrace(
                trace_id=uuid.uuid4().hex[:16],
                task_id=spec.task_id,
                split=spec.split,
                policy_id=policy.policy_id,
                run_id=run_id,
                states=states,
                judge={
                    "visible_passed": report.visible_passed,
                    "sealed_passed": report.sealed_passed,
                    "visible_failures": report.visible_failures,
                    "invalid_reason": report.invalid_reason,
                    "executor": report.executor,
                },
                workspace_digest_before=digest_before,
                workspace_digest_after=ws.digest(),
                executor=report.executor,
                duration_ms=report.duration_ms,
                created_utc=new_run_id(),
                provider_kind="none",
                model_invoked=False,
            )
            writer.write_trace(trace)
            traces.append(trace.as_dict())
        summary = summarize_traces(traces)
        manifest = RunManifest(
            run_id=run_id,
            policy_id=policy.policy_id,
            created_utc=new_run_id(),
            split_seed=split_seed,
            task_count=len(specs),
            executor_kind=executor.kind,
            config=config or {},
            config_sha256=config_sha256(config or {}),
            notes=[
                "OFFLINE pipeline validation with fake agent; outcomes are not model performance",
                "judge receives no policy identity (blinded)",
                "sealed tests never enter the agent-visible workspace",
            ],
            provenance=provenance_block(),
        )
        writer.write_manifest(manifest)
        (run_dir / "report.json").write_text(
            __import__("json").dumps(
                {"manifest": manifest.as_dict(), "summary": summary},
                indent=2, ensure_ascii=False),
            encoding="utf-8")
        return {"run_id": run_id, "summary": summary, "run_dir": str(run_dir)}
    finally:
        writer.close()
        factory.destroy_all()
