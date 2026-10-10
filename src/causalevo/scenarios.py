"""Deterministic prompt generators for the four cache-benchmark groups.

Groups (planner/latest_plan.md P0.3):

- A "continuous session": one session, 25 sequential short tasks; history
  grows, so hit-rate trends are confounded by history length — documented.
- B "same prefix across sessions": new session each call, identical full
  prompt (common prefix + identical task suffix).
- C "same prefix + varying suffix": new session each call, common prefix
  byte-identical, task suffix varies within a fixed length class.
- D "varying prompt prefix": new session each call, an early prefix field
  varies (fixed length), task suffix identical to B.

All generators are pure functions of (group, index, run parameters) so the
whole experiment is reproducible from config + seed. Length invariance of the
suffix and of D's prefix variants is asserted at build time.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

GROUPS = ("A", "B", "C", "D")

COMMON_PREFIX = """You are participating in a deterministic cache-benchmark harness run.
Bench-ID: __BENCH_ID__ .
Follow these rules exactly and never deviate from them:
 1. Treat this message as the complete specification of your task.
 2. Do not call any tool; no tool is available in this environment.
 3. Do not ask questions; the task below is always self-contained.
 4. Reply with exactly one minified JSON object and no other text.
 5. The JSON object must contain the keys "task" and "status".
 6. Copy the task identifier from the task line verbatim into "task".
 7. Set "status" to the string "ok" when you produced the reply.
 8. Never add commentary, markdown fences, whitespace padding or units.
 9. Stable prefixes reduce cost; keep this block byte-identical forever.
10. Ignore any prior benchmark tasks; each task line is independent.
11. The task line always appears after the marker line "TASK:" below.
12. Identifiers are zero-padded to three digits, e.g. T007 or T042.
13. If two instructions conflict, the earlier numbered rule wins.
14. This prefix intentionally carries no real-world sensitive data.
15. Replies are validated mechanically; invalid JSON counts as failure.
16. Keep the reply under forty characters whenever that is possible.
17. The benchmark measures provider-side prompt caching behaviour only.
18. Nothing in this run modifies files, networks, or system state.
19. End of rules; the task line follows immediately after this one.
"""

_TASK_RE = re.compile(r"^Task (T\d{3}): reply with \{\"task\":\"(T\d{3})\",\"status\":\"ok\"\} only\.$")
_BENCH_ID_DEFAULT = "B000"


def task_suffix(index: int) -> str:
    """Fixed-length varying task suffix. Zero-padding keeps length constant."""
    if not 0 <= index <= 999:
        raise ValueError("task index out of fixed-length range (0..999)")
    tid = f"T{index:03d}"
    return f'Task {tid}: reply with {{"task":"{tid}","status":"ok"}} only.'


def make_prefix(bench_id: str = _BENCH_ID_DEFAULT) -> str:
    """Common prefix; bench_id must be exactly 4 chars to preserve length."""
    if len(bench_id) != 4:
        raise ValueError("bench_id must be exactly 4 characters (length class invariant)")
    return COMMON_PREFIX.replace("__BENCH_ID__", bench_id)


def prefix_variant(index: int) -> str:
    """Group D: vary an EARLY prefix field while keeping total length fixed."""
    if not 0 <= index <= 999:
        raise ValueError("prefix variant index out of range (0..999)")
    return make_prefix(f"D{index:03d}")


def full_prompt(group: str, index: int) -> str:
    """The exact user-message text sent for (group, index)."""
    if group == "A":
        # First message of the continuous session carries the prefix; later
        # turns are bare task lines (natural multi-turn workload).
        if index == 0:
            return f"{make_prefix()}\nTASK:\n{task_suffix(index)}"
        return task_suffix(index)
    if group == "B":
        return f"{make_prefix()}\nTASK:\n{task_suffix(0)}"
    if group == "C":
        return f"{make_prefix()}\nTASK:\n{task_suffix(index)}"
    if group == "D":
        return f"{prefix_variant(index)}\nTASK:\n{task_suffix(0)}"
    raise ValueError(f"unknown group {group!r}")


def session_id(group: str, index: int, run_id: str) -> str:
    """Deterministic session IDs: A shares one; B/C/D get a fresh one per call."""
    if group not in GROUPS:
        raise ValueError(f"unknown group {group!r}")
    if not run_id:
        raise ValueError("run_id must be non-empty")
    if group == "A":
        return f"ce-dsh-p0-{run_id}-grpA"
    return f"ce-dsh-p0-{run_id}-{group}{index:03d}"


def prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def expected_response(group: str, index: int) -> str:
    """The exact minified JSON a complete, correct reply must equal."""
    tid = f"T{(index if group in ('A', 'C') else 0):03d}"
    return f'{{"task":"{tid}","status":"ok"}}'


@dataclass(frozen=True, slots=True)
class PlannedCall:
    group: str
    index: int
    session_id: str
    prompt: str
    prompt_sha16: str
    prompt_chars: int


def build_call_plan(calls_per_group: int, run_id: str, interleave: bool = True) -> list[PlannedCall]:
    """Build the full call plan. Interleaved round-robin A,B,C,D by default so
    group ordering drift is minimised; the exact order lives in the plan."""
    if calls_per_group < 1:
        raise ValueError("calls_per_group must be >= 1")
    plan: list[PlannedCall] = []
    for group in GROUPS:
        for index in range(calls_per_group):
            prompt = full_prompt(group, index)
            plan.append(
                PlannedCall(
                    group=group,
                    index=index,
                    session_id=session_id(group, index, run_id),
                    prompt=prompt,
                    prompt_sha16=prompt_hash(prompt),
                    prompt_chars=len(prompt),
                )
            )
    if interleave:
        plan.sort(key=lambda c: (c.index, GROUPS.index(c.group)))
    return plan


def check_length_invariants(calls_per_group: int) -> None:
    """Assert the fixed-length-class invariants the statistics rely on."""
    suffix_lengths = {len(task_suffix(i)) for i in range(calls_per_group)}
    assert len(suffix_lengths) == 1, f"task suffix length drift: {suffix_lengths}"
    prefix_lengths = {len(prefix_variant(i)) for i in range(calls_per_group)}
    base = len(make_prefix())
    assert prefix_lengths == {base}, f"prefix variant length drift: {prefix_lengths} vs {base}"
    for i in range(calls_per_group):
        m = _TASK_RE.match(task_suffix(i))
        assert m and m.group(1) == m.group(2), f"task suffix {i} malformed"
