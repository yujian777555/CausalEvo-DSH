"""Phase 4 live/dry-run pilot runner.

Per (task, arm, seed): fresh workspace -> attempt 1 -> (arm-specific
intervention retry on failure) -> independent judge. Per-task RuntimeBudget +
global BudgetGate (fail-closed). Live requires the double authorization gate;
dry-run uses the tape-provider container world (zero cost).

Interventions at live time are instruction messages appended to the retry
turn (frozen texts in docs/PHASE4_EXPERIMENT_PROTOCOL.md §3).
"""

from __future__ import annotations


import time

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..budget import BudgetGate
from .harness_agent import ContainerHarnessRunner
from .judge import Judge
from .runtime_budget import RuntimeBudget
from .task_spec import TaskSpec
from .workspace_factory import WorkspaceFactory

INTERVENTION_TEXT = {
    "tool_validation": ("Use ONLY these tools with valid arguments: read, write, edit, "
                        "glob, grep. Read the target file before writing."),
    "verification": ("Before finishing: re-read every file you wrote and check it "
                     "parses/imports; if not, fix and re-check."),
    "read_before_write": "First read solution.py, then write the fix.",
    "planning": "Plan explicitly: locate, modify, verify. Then act.",
}
CEAV1_BUNDLE = (INTERVENTION_TEXT["tool_validation"] + " " +
                INTERVENTION_TEXT["verification"])

ARMS = ["B0-original", "B1-random", "B2-rule", "B3-reflexion", "B4-cea-v0", "B5-cea-v1"]


@dataclass(slots=True)
class ArmResult:
    task_id: str
    arm: str
    seed: int
    attempt1_success: bool
    retried: bool
    final_success: bool
    invalid: bool
    timeout: bool
    failure_kind: str
    intervention: str | None
    provider_calls: int
    tool_calls: int
    input_tokens: int
    cache_read_tokens: int
    output_tokens: int
    cost_cny: float
    latency_ms: int
    run_id: str

    def as_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in self.__dataclass_fields__.values()}


def _judge_success(report) -> bool:
    return (report.visible_passed and report.sealed_passed
            and not report.invalid_reason and not report.timed_out)


def run_task_arm(
    spec: TaskSpec,
    arm: str,
    seed: int,
    judge: Judge,
    run_id: str,
    *,
    rng,
    gate: BudgetGate | None,
    make_runner: Callable[[int], ContainerHarnessRunner],
) -> ArmResult:
    """One (task, arm, seed) execution. make_runner(attempt_index) must return a
    ready ContainerHarnessRunner for that attempt (dry-run: fresh tape provider
    per attempt; live: real endpoint). Budget-gated; never fabricates."""
    budget = RuntimeBudget(max_provider_calls=2, max_total_output_tokens=2048,
                           max_tool_calls=20, wall_time_s=240)
    factory = WorkspaceFactory()
    ws = factory.create(spec, run_id)
    t0 = time.monotonic()
    try:
        runner1 = make_runner(0)
        outcome1 = runner1.run_task(spec, ws.root, arm, budget,
                                    api_key=_current_key())
        report1 = judge.grade(spec, ws.root)
        success1 = _judge_success(report1)

        retried = False
        intervention_used: str | None = None
        final_report = report1

        if not success1 and arm != "B0-original":
            if arm == "B1-random":
                key = rng.choice(sorted(INTERVENTION_TEXT))
            elif arm == "B3-reflexion":
                key = "reflection"
            elif arm == "B5-cea-v1":
                key = "ceav1_bundle"
            else:  # B2-rule / B4-cea-v0: observable-evidence mapping
                edited = ws.digest() != ws.digest_at_open
                if report1.invalid_reason:
                    key = "verification"
                elif not edited:
                    key = "planning"
                elif outcome1.failure_kind != "none":
                    key = "tool_validation"
                else:
                    key = "verification" if arm == "B4-cea-v0" else "read_before_write"
            intervention_used = key
            if key == "reflection":
                fails = ", ".join(report1.visible_failures) or "unknown"
                prompt2 = (f"Your previous attempt failed these visible checks: {fails}. "
                           "Briefly diagnose why, then apply the corrected fix.")
            elif key == "ceav1_bundle":
                prompt2 = CEAV1_BUNDLE
            else:
                prompt2 = INTERVENTION_TEXT[key]
            retried = True
            runner2 = make_runner(1)
            outcome2 = runner2.run_task(spec, ws.root, arm, budget,
                                        api_key=_current_key(), extra_prompt=prompt2)
            final_report = judge.grade(spec, ws.root)

        final_success = _judge_success(final_report)
        latency = int((time.monotonic() - t0) * 1000)
        if gate is not None:
            gate.record_spend(budget.ledger.known_cost_cny)
        return ArmResult(
            task_id=spec.task_id, arm=arm, seed=seed,
            attempt1_success=success1, retried=retried, final_success=final_success,
            invalid=bool(final_report.invalid_reason), timeout=final_report.timed_out,
            failure_kind=outcome1.failure_kind, intervention=intervention_used,
            provider_calls=budget.ledger.provider_attempts,
            tool_calls=budget.ledger.tool_attempts,
            input_tokens=budget.ledger.known_input_tokens,
            cache_read_tokens=budget.ledger.cache_read_tokens,
            output_tokens=budget.ledger.output_tokens,
            cost_cny=round(budget.ledger.known_cost_cny, 10),
            latency_ms=latency, run_id=run_id,
        )
    finally:
        factory.destroy_all()


_API_KEY_HOLDER: list[str] = []


def set_api_key(key: str) -> None:
    _API_KEY_HOLDER.clear()
    _API_KEY_HOLDER.append(key)


def _current_key() -> str:
    return _API_KEY_HOLDER[0] if _API_KEY_HOLDER else "sk-fake-offline-no-cost"
