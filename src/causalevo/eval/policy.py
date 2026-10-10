"""Baseline policies B0/B1 (offline definitions) and budget parity (P1.4).

Both policies share the SAME budget envelope; the difference is decision
policy only:
- B0 (fixed harness): one attempt, no reflection, no persistent updates.
- B1 (self-reflection): may spend part of the SAME budget on one structured
  reflection + one re-attempt; never modifies agent components across tasks.

Fairness rule: B1's reflection consumes from the identical pool. The
parity check is enforced by tests, not convention.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Budget:
    max_provider_calls: int = 2
    max_total_output_tokens: int = 2048
    max_tool_calls: int = 20
    wall_time_s: int = 300


@dataclass(frozen=True, slots=True)
class Policy:
    policy_id: str
    description: str
    budget: Budget
    allow_reflection: bool
    max_attempts_per_task: int
    persistent_updates: bool  # must stay False for both baselines


B0 = Policy(
    policy_id="B0-fixed-harness",
    description="Fixed prompt/tools/budget; no reflection; no persistent updates.",
    budget=Budget(),
    allow_reflection=False,
    max_attempts_per_task=1,
    persistent_updates=False,
)

B1 = Policy(
    policy_id="B1-self-reflection-fixed-budget",
    description="One structured reflection + one re-attempt inside the SAME budget envelope; no cross-task component updates.",
    budget=Budget(),
    allow_reflection=True,
    max_attempts_per_task=2,
    persistent_updates=False,
)

POLICIES = {B0.policy_id: B0, B1.policy_id: B1}


def check_budget_parity(a: Policy, b: Policy) -> None:
    """B0/B1 must share identical budget envelopes (fair-comparison gate)."""
    if a.budget != b.budget:
        raise ValueError(f"budget mismatch: {a.policy_id} {a.budget} != {b.policy_id} {b.budget}")
    if a.persistent_updates or b.persistent_updates:
        raise ValueError("baselines must not persist updates across tasks")


def get_policy(policy_id: str) -> Policy:
    return POLICIES[policy_id]
