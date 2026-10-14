"""Scripted fake-provider scenarios for offline agent-pipeline evidence.

Each scenario is a factory: TaskSpec -> script(messages, call_index) -> actions.
They drive the REAL Harness agent loop (tool dispatch, workspace edits) through
the protocol-level fake provider. Synthetic usage, zero cost, no network.

Coverage required by CE-DSH-P1-R2 S1: noop, correct fix, wrong fix, bad tool
call, provider timeout, provider error, tool-over-budget.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from .task_spec import TaskSpec

Script = Callable[[list[dict[str, Any]], int], list[tuple]]
ScenarioFactory = Callable[[TaskSpec], Script]


def _noop(spec: TaskSpec) -> Script:
    def script(messages, call_index):
        return [("text", "I will not change anything.")]
    return script


def _correct_fix(spec: TaskSpec) -> Script:
    fixed = spec.reference_fixed.read_text(encoding="utf-8")

    def script(messages, call_index):
        if call_index == 0:
            return [("tool_call", "read", {"file_path": spec.entry_file})]
        if call_index == 1:
            return [("tool_call", "write",
                     {"file_path": spec.entry_file, "content": fixed})]
        return [("text", "Fixed.")]
    return script


def _wrong_fix(spec: TaskSpec) -> Script:
    def script(messages, call_index):
        if call_index == 0:
            return [("tool_call", "read", {"file_path": spec.entry_file})]
        if call_index == 1:
            return [("tool_call", "write",
                     {"file_path": spec.entry_file,
                      "content": f"def {spec.function}(*a, **k):\n    return None\n"})]
        return [("text", "Applied a fix.")]
    return script


def _bad_tool_call(spec: TaskSpec) -> Script:
    def script(messages, call_index):
        if call_index == 0:
            return [("tool_call", "definitely_not_a_tool", {"x": 1})]
        return [("text", "Tool call failed; stopping.")]
    return script


def _provider_error(spec: TaskSpec) -> Script:
    def script(messages, call_index):
        return [("error", 500, {"error": {"message": "injected provider failure"}})]
    return script


def _provider_timeout(spec: TaskSpec) -> Script:
    def script(messages, call_index):
        return [("sleep", 30)]
    return script


def _tool_over_budget(spec: TaskSpec) -> Script:
    def script(messages, call_index):
        return [("tool_call", "glob", {"pattern": "**/*.py"})]  # loops forever
    return script


def _bad_tool_blocks_write(spec: TaskSpec) -> Script:
    """Failure depends on the tool error: the write is BLOCKED because the
    bad tool call replaced the mandatory read (write requires prior read)."""
    fixed = spec.reference_fixed.read_text(encoding="utf-8")

    def script(messages, call_index):
        if call_index == 0:
            return [("tool_call", "definitely_not_a_tool", {"x": 1})]
        if call_index == 1:
            return [("tool_call", "write",
                     {"file_path": spec.entry_file, "content": fixed})]
        return [("text", "done")]
    return script


def _broken_write(spec: TaskSpec) -> Script:
    """Reads, then writes syntactically broken code, then stops: a
    verification failure (no read-back/self-check before finishing)."""

    def script(messages, call_index):
        if call_index == 0:
            return [("tool_call", "read", {"file_path": spec.entry_file})]
        if call_index == 1:
            return [("tool_call", "write",
                     {"file_path": spec.entry_file, "content": "def broken(:\n"})]
        return [("text", "done")]
    return script


SCENARIOS: dict[str, ScenarioFactory] = {
    "noop": _noop,
    "correct_fix": _correct_fix,
    "wrong_fix": _wrong_fix,
    "bad_tool_call": _bad_tool_call,
    "provider_error": _provider_error,
    "provider_timeout": _provider_timeout,
    "tool_over_budget": _tool_over_budget,
    "bad_tool_blocks_write": _bad_tool_blocks_write,
    "broken_write": _broken_write,
}


def scenario_tape(spec: TaskSpec, factory: ScenarioFactory, max_calls: int) -> dict[str, Any]:
    """Materialize a scenario into a JSON-serializable tape: {str(i): actions}.

    Constraint: scenario scripts may depend only on call_index (ours do);
    message-dependent branching is out of scope for tapes. Indices
    0..max_calls-1 are materialized; the tape server answers out-of-range
    calls with a plain text completion so the agent loop terminates. The
    caller must size max_calls above the runtime's retry horizon (observed
    5-6 internal retries) or error scenarios would leak into the fallback.
    """
    script = factory(spec)
    tape: dict[str, Any] = {}
    for i in range(max_calls):
        actions = script([], i)
        tape[str(i)] = [list(a) if isinstance(a, tuple) else a for a in actions]
    return tape
