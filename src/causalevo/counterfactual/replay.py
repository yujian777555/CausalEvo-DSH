"""Counterfactual replay engine (P2.3-S3).

Mechanism: a failure case is replayed in the same container world with the
intervention applied as a DETERMINISTIC transform of the provider tape. Both
arms run through the real runtime and the independent judge.

HONESTY BOUNDARY (also in docs/PHASE2_INTERVENTION_DESIGN.md): the transform
simulates the intervention's mechanism inside the fake provider; an improved
counterfactual outcome shows the mechanism works end-to-end under that
simulation — it is NOT evidence that a real model would improve. Causal
language beyond this is forbidden by the frozen protocol.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..eval.executor import Executor
from ..eval.harness_agent import ContainerHarnessRunner
from ..eval.judge import Judge
from ..eval.networks import ProviderContainer
from ..eval.runtime_budget import RuntimeBudget
from ..eval.task_spec import TaskSpec
from ..eval.workspace_factory import WorkspaceFactory
from ..intervention.schema import CandidateIntervention

KNOWN_TOOLS = ("read", "write", "edit", "glob", "grep")


def apply_tape_transform(tape: dict[str, list], transform: str, *,
                         entry_file: str, fixed_content: str) -> tuple[dict[str, list], list[str]]:
    """Return (new_tape, change_descriptions). Pure function; original tape
    is never mutated."""
    src = {k: [list(a) for a in v] for k, v in tape.items()}
    changes: list[str] = []

    def renumber(seq: list[list]) -> dict[str, list]:
        return {str(i): a for i, a in enumerate(seq)}

    if transform == "identity":
        return src, changes

    ordered = [src[k] for k in sorted(src, key=int)]

    if transform == "replace_unknown_tool_with_read":
        for i, actions in enumerate(ordered):
            for j, a in enumerate(actions):
                if a[0] == "tool_call" and a[1] not in KNOWN_TOOLS:
                    ordered[i][j] = ["tool_call", "read", {"file_path": entry_file}]
                    changes.append(f"call {i}: unknown tool -> read({entry_file})")
        return renumber(ordered), changes

    if transform == "prepend_read_step":
        ordered.insert(0, [["tool_call", "read", {"file_path": entry_file}]])
        changes.append(f"call 0: inserted read({entry_file}) before any action")
        return renumber(ordered), changes

    if transform == "append_readback_and_fix":
        # find the write call, then append read-back + corrected write + done
        for i, actions in enumerate(ordered):
            if any(a[0] == "tool_call" and a[1] == "write" for a in actions):
                ordered.insert(i + 1, [["tool_call", "read", {"file_path": entry_file}]])
                ordered.insert(i + 2, [["tool_call", "write",
                                        {"file_path": entry_file, "content": fixed_content}]])
                changes.append(f"after call {i}: inserted read-back + corrected write")
                return renumber(ordered), changes
        return src, changes

    if transform == "inject_fix_after_write":
        return apply_tape_transform(src, "append_readback_and_fix",
                                    entry_file=entry_file, fixed_content=fixed_content)

    if transform == "break_repeat_with_read":
        # stop a same-tool spam loop at the 3rd repeat: read + final text
        run = 1
        prev_tool = None
        for i, actions in enumerate(ordered):
            tool = next((a[1] for a in actions if a[0] == "tool_call"), None)
            if tool is not None and tool == prev_tool:
                run += 1
            else:
                run = 1
            prev_tool = tool if tool is not None else prev_tool
            if run >= 3:
                head = ordered[:i]
                head.append([["tool_call", "read", {"file_path": entry_file}]])
                head.append([["text", "stopping after strategy switch"]])
                changes.append(f"call {i}: repeat loop broken with read + stop")
                return renumber(head), changes
        return src, changes

    raise ValueError(f"unknown tape transform {transform!r}")


@dataclass(slots=True)
class CounterfactualResult:
    case_id: str
    task_id: str
    scenario: str
    baseline: str
    intervention: dict[str, Any]
    original_outcome: str
    counterfactual_outcome: str
    original_success: bool
    counterfactual_success: bool
    changed_steps: list[str]
    success_delta: int
    cost_delta_cny: float
    original_ledger: dict[str, Any]
    counterfactual_ledger: dict[str, Any]
    confidence: str
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_jsonl(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True)


def run_single(spec: TaskSpec, tape: dict[str, list], budget: RuntimeBudget, *,
               image: str, patch_path: Path, network: str,
               judge: Judge, factory: WorkspaceFactory, run_tag: str) -> dict[str, Any]:
    """Single replay arm (public for two-step diagnosis-guided orchestration)."""
    ws = factory.create(spec, run_tag)
    with ProviderContainer(tape, network=network) as provider:
        runner = ContainerHarnessRunner(
            image=image, patch_path=patch_path, model="deepseek-flash",
            reasoning_effort="low", max_tokens=256, provider_kind="fake",
            provider_endpoint=provider.endpoint, network=network)
        outcome = runner.run_task(spec, ws.root, "counterfactual", budget,
                                  api_key="sk-fake-offline-no-cost")
    report = judge.grade(spec, ws.root)
    states_timeout = outcome.failure_kind == "timeout"
    success = (report.visible_passed and report.sealed_passed
               and not report.invalid_reason and not states_timeout)
    return {
        "outcome_kind": outcome.failure_kind,
        "finish_reason": outcome.finish_reason,
        "ledger": outcome.ledger,
        "events_slim": outcome.events_slim,
        "judge": {"visible": report.visible_passed, "sealed": report.sealed_passed,
                  "invalid": bool(report.invalid_reason)},
        "success": success,
    }


def replay_pair(spec: TaskSpec, tape: dict[str, list], intervention: CandidateIntervention, *,
                scenario: str, baseline: str, image: str, patch_path: Path,
                network: str, budget: RuntimeBudget, judge: Judge,
                case_id: str) -> CounterfactualResult:
    """Paired counterfactual comparison: same task, same base tape, same budget;
    only the tape transform differs (B0 uses identity)."""
    fixed_content = spec.reference_fixed.read_text(encoding="utf-8")
    cf_tape, changes = apply_tape_transform(
        tape, intervention.tape_transform,
        entry_file=spec.entry_file, fixed_content=fixed_content,
        **(intervention.transform_args or {}))

    factory = WorkspaceFactory()
    try:
        original = run_single(spec, tape, budget, image=image, patch_path=patch_path,
                            network=network, judge=judge, factory=factory,
                            run_tag=case_id + "-orig")
        # fresh budget for the counterfactual arm (same envelope, fresh ledger)
        budget_cf = RuntimeBudget(
            max_provider_calls=budget.max_provider_calls,
            max_total_output_tokens=budget.max_total_output_tokens,
            max_tool_calls=budget.max_tool_calls,
            wall_time_s=budget.wall_time_s,
            max_cost_cny=budget.max_cost_cny,
        )
        cfx = run_single(spec, cf_tape, budget_cf, image=image, patch_path=patch_path,
                       network=network, judge=judge, factory=factory,
                       run_tag=case_id + "-cf")
    finally:
        factory.destroy_all()

    success_delta = int(cfx["success"]) - int(original["success"])
    cost_delta = (cfx["ledger"]["known_cost_cny"] - original["ledger"]["known_cost_cny"])
    notes = [
        "paired replay: same task, same base tape, same budget envelope",
        "transform-simulated intervention; NOT evidence of real-model improvement",
    ]
    return CounterfactualResult(
        case_id=case_id, task_id=spec.task_id, scenario=scenario, baseline=baseline,
        intervention=json.loads(intervention.to_json()),
        original_outcome=str(original["outcome_kind"]),
        counterfactual_outcome=str(cfx["outcome_kind"]),
        original_success=original["success"],
        counterfactual_success=cfx["success"],
        changed_steps=changes,
        success_delta=success_delta,
        cost_delta_cny=round(cost_delta, 10),
        original_ledger=original["ledger"],
        counterfactual_ledger=cfx["ledger"],
        confidence="low",
        notes=notes,
    )
