"""Failure feature extractor (P2.2-S1).

TaskTrace -> FailureFeature. Only agent-observable trajectory + judge outcome
+ task metadata. Never: chain-of-thought, sealed/hidden test content, holdout.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class FailureFeature:
    trace_id: str
    # task features
    task_split: str
    task_prompt_chars: int
    n_visible_checks: int
    # agent behavior features
    tool_calls: int
    provider_calls: int
    action_diversity: float       # distinct tools / max(1, tool calls)
    failed_action_ratio: float    # tool events with error-ish evidence / tool calls (observable via events_slim tool results absence is not available; uses known bad tool names + ledger)
    repeat_max_run: int           # longest run of identical tool name
    events_count: int
    # error features
    failure_kind: str             # none/provider_error/timeout/budget_stop/unknown_cost/...
    n_unknown_spend: int
    budget_stop: bool
    # verification features
    edited_workspace: bool
    judge_invalid: bool
    visible_passed: bool
    sealed_passed: bool
    # meta
    provider_kind: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _repeat_max_run(names: list[str]) -> int:
    best = run = 1
    for i in range(1, len(names)):
        run = run + 1 if names[i] == names[i - 1] else 1
        best = max(best, run)
    return best if names else 0


def extract_features(trace: dict[str, Any], *, task_prompt_chars: int = 0,
                     n_visible_checks: int = 0) -> FailureFeature:
    agent = trace.get("agent", {}) or {}
    judge = trace.get("judge", {}) or {}
    states = trace.get("states", {}) or {}
    ledger = agent.get("ledger", {}) or {}
    events = agent.get("events_slim", []) or []

    names = [e.get("tool") for e in events if e.get("type") == "tool/call" and e.get("tool")]
    tool_calls = int(ledger.get("tool_attempts") or len(names))
    diversity = (len(set(names)) / len(names)) if names else 0.0
    bad = sum(1 for n in names if n not in ("read", "write", "edit", "glob", "grep"))

    edited = trace.get("workspace_digest_before") != trace.get("workspace_digest_after")
    return FailureFeature(
        trace_id=trace.get("trace_id", "?"),
        task_split=trace.get("split", "?"),
        task_prompt_chars=task_prompt_chars,
        n_visible_checks=n_visible_checks,
        tool_calls=tool_calls,
        provider_calls=int(ledger.get("provider_attempts") or 0),
        action_diversity=round(diversity, 6),
        failed_action_ratio=round(bad / tool_calls, 6) if tool_calls else 0.0,
        repeat_max_run=_repeat_max_run(names),
        events_count=len(events),
        failure_kind=str(agent.get("failure_kind") or "none"),
        n_unknown_spend=int(ledger.get("unknown_spend_attempts") or 0),
        budget_stop=bool(states.get("budget_stop")),
        edited_workspace=bool(edited),
        judge_invalid=bool(judge.get("invalid_reason")),
        visible_passed=bool(states.get("visible_tests_passed")),
        sealed_passed=bool(states.get("sealed_tests_passed")),
        provider_kind=str(trace.get("provider_kind", "none")),
    )


FEATURE_COLUMNS = [
    "task_prompt_chars", "n_visible_checks", "tool_calls", "provider_calls",
    "action_diversity", "failed_action_ratio", "repeat_max_run", "events_count",
    "n_unknown_spend", "budget_stop", "edited_workspace", "judge_invalid",
    "visible_passed", "sealed_passed",
]
CATEGORICAL_COLUMNS = ["task_split", "failure_kind", "provider_kind"]
