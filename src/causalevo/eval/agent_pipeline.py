"""Agent-task pipeline (R2): real Harness runtime (container world) driving
one task, then the independent judge, then traces/metrics.

Differs from pipeline.run_offline (fake file-editing agent) in that the agent
loop is the genuine DSH runtime over a protocol-level fake (or, later and only
with explicit authorization, live) provider. All token/tool accounting goes
through RuntimeBudget; unknown spend stops the task.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from ..usage import UsageRecord
from .executor import Executor
from .harness_agent import AgentRunOutcome, ContainerHarnessRunner
from .judge import Judge
from .metrics import summarize_traces
from .policy import Policy
from .task_spec import TaskSpec
from .trace import RunManifest, TaskTrace, TraceWriter, config_sha256, new_run_id, provenance_block
from .workspace_factory import WorkspaceFactory


def run_agent_tasks(
    specs: list[TaskSpec],
    policy: Policy,
    judge: Judge,
    judge_executor: Executor,
    out_dir: Path,
    *,
    provider_factory,  # TaskSpec -> FakeProvider (per-task provider instance)
    budget_factory,
    image: str,
    patch_path: Path,
    provider_kind: str = "fake",
    split_seed: int = 0,
    run_id: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run each task: fresh workspace -> agent (container) -> judge -> trace."""
    run_id = run_id or f"{policy.policy_id}-agent-{new_run_id()}"
    run_dir = out_dir / run_id
    factory = WorkspaceFactory()
    writer = TraceWriter(run_dir)
    traces: list[dict[str, Any]] = []
    try:
        for spec in specs:
            ws = factory.create(spec, run_id)
            digest_before = ws.digest()
            budget = budget_factory()
            states = {
                "api_response_observed": provider_kind == "live",
                "tool_executed": False,
                "task_completed": False,
                "visible_tests_passed": False,
                "sealed_tests_passed": False,
                "invalid": False,
                "timeout": False,
                "budget_stop": False,
            }
            with provider_factory(spec) as provider:
                runner = ContainerHarnessRunner(
                    image=image,
                    patch_path=patch_path,
                    model="deepseek-flash", reasoning_effort="low", max_tokens=256,
                    provider_kind=provider_kind,
                    host_base_url=provider.base_url.replace("127.0.0.1", "host.docker.internal"),
                )
                outcome: AgentRunOutcome = runner.run_task(
                    spec, ws.root, policy.policy_id, budget,
                    api_key="sk-fake-offline-no-cost",
                )
            states["tool_executed"] = budget.ledger.tool_attempts > 0
            states["task_completed"] = outcome.finish_reason == "completed"
            states["budget_stop"] = outcome.failure_kind in ("budget_stop", "unknown_cost")
            states["timeout"] = outcome.failure_kind == "timeout"
            if outcome.failure_kind in ("provider_error", "transport", "protocol"):
                states["invalid"] = False  # infra failure is not a task-format failure
            report = judge.grade(spec, ws.root)
            states["visible_tests_passed"] = report.visible_passed
            states["sealed_tests_passed"] = report.sealed_passed
            states["invalid"] = states["invalid"] or bool(report.invalid_reason)
            states["timeout"] = states["timeout"] or report.timed_out
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
                duration_ms=outcome.duration_ms,
                created_utc=new_run_id(),
                provider_kind=provider_kind,
                model_invoked=True,  # the real Harness agent loop ran (fake provider)
                agent={
                    "runner": outcome.runner,
                    "finish_reason": outcome.finish_reason,
                    "failure_kind": outcome.failure_kind,
                    "budget_stop_reason": outcome.budget_stop_reason,
                    "final_response_sha16": outcome.final_response_sha16,
                    "ledger": outcome.ledger,
                    "usage": outcome.usage.as_dict() if outcome.usage else None,
                    "events_slim": outcome.events_slim,
                },
            )
            writer.write_trace(trace)
            traces.append(trace.as_dict())
            if outcome.failure_kind == "unknown_cost":
                # fail-closed across the run: unmetered provider requests mean
                # the spend ledger is unreliable; do not start further tasks.
                break
        summary = summarize_traces(traces)
        manifest = RunManifest(
            run_id=run_id,
            policy_id=policy.policy_id,
            created_utc=new_run_id(),
            split_seed=split_seed,
            task_count=len(specs),
            executor_kind=judge_executor.kind,
            config=config or {},
            config_sha256=config_sha256(config or {}),
            notes=[
                "R2 agent run through real DSH runtime over protocol-level fake provider",
                "judge blinded; sealed tests never in agent workspace",
                "fake provider usage is synthetic; not provider billing evidence",
            ],
            provenance=provenance_block(),
        )
        writer.write_manifest(manifest)
        (run_dir / "report.json").write_text(
            json.dumps({"manifest": manifest.as_dict(), "summary": summary},
                       indent=2, ensure_ascii=False),
            encoding="utf-8")
        return {"run_id": run_id, "summary": summary, "run_dir": str(run_dir)}
    finally:
        writer.close()
        factory.destroy_all()
