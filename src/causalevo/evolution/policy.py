"""Policies (P3.1-S3): B0 random, B1 rule, B2 LinUCB (CEA-v0).

State vector layout (fixed; changes would break replay comparability):
  [one-hot failure_type (7)] + [prompt_chars/2000, n_visible_checks/10]
  + optional history block (A2 ablation): per-action empirical success rate.
"""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

import numpy as np

from ..intervention.generator import INTERVENTION_LIBRARY
from .bandit import LinUCB

FAILURE_TYPES = [
    "planning_failure", "tool_failure", "knowledge_failure", "execution_failure",
    "verification_failure", "strategy_failure", "unknown",
]
ACTIONS = [iv.intervention_id for iv in INTERVENTION_LIBRARY]
N_BASE = len(FAILURE_TYPES) + 2


def state_vector(failure_state: dict[str, Any], history_rates: list[float] | None = None) -> np.ndarray:
    vec = [0.0] * N_BASE
    ftype = failure_state.get("failure_type", "unknown")
    if ftype in FAILURE_TYPES:
        vec[FAILURE_TYPES.index(ftype)] = 1.0
    vec[len(FAILURE_TYPES)] = min(1.0, failure_state.get("prompt_chars", 0) / 2000.0)
    vec[len(FAILURE_TYPES) + 1] = min(1.0, failure_state.get("n_visible_checks", 0) / 10.0)
    if history_rates is not None:
        vec = vec + list(history_rates)
    return np.array(vec, dtype=float)


class Policy(Protocol):
    policy_id: str

    def select(self, failure_state: dict[str, Any], candidates: list[str],
               history_rates: list[float] | None = None) -> str: ...
    def update(self, failure_state: dict[str, Any], action: str, reward: float,
               history_rates: list[float] | None = None) -> None: ...
    def state_hash(self) -> str: ...


class RandomPolicy:
    policy_id = "B0-random"

    def __init__(self, seed: int) -> None:
        self._rng = np.random.default_rng(seed)
        self._n = 0

    def select(self, failure_state, candidates, history_rates=None) -> str:
        self._n += 1
        return candidates[int(self._rng.integers(len(candidates)))]

    def update(self, *a, **k) -> None:
        return None

    def state_hash(self) -> str:
        return hashlib.sha256(f"{self.policy_id}:{self._n}".encode()).hexdigest()[:12]


class RulePolicy:
    """Taxonomy rule mapping (same table as the P2.3 generator)."""
    policy_id = "B1-rule"

    def __init__(self) -> None:
        self._map = {iv.target_failure: iv.intervention_id for iv in INTERVENTION_LIBRARY}

    def select(self, failure_state, candidates, history_rates=None) -> str:
        choice = self._map.get(failure_state.get("failure_type", "unknown"))
        if choice in candidates:
            return choice
        return candidates[0]

    def update(self, *a, **k) -> None:
        return None

    def state_hash(self) -> str:
        return hashlib.sha256(self.policy_id.encode()).hexdigest()[:12]


class LinUCBPolicy:
    """CEA-v0: LinUCB over the fixed state layout."""
    policy_id = "B2-cea-v0-linucb"

    def __init__(self, alpha: float = 0.5, use_history: bool = False) -> None:
        self.use_history = use_history
        dim = N_BASE + (len(ACTIONS) if use_history else 0)
        self.bandit = LinUCB(n_actions=len(ACTIONS), dim=dim, alpha=alpha)
        self.updates = 0

    def select(self, failure_state, candidates, history_rates=None) -> str:
        rates = history_rates if self.use_history else None
        x = state_vector(failure_state, rates)
        # candidates may be a subset; restrict scores to them
        scores = self.bandit.scores(x)
        idx = max((ACTIONS.index(c) for c in candidates), key=lambda i: scores[i])
        return ACTIONS[idx]

    def update(self, failure_state, action, reward, history_rates=None) -> None:
        rates = history_rates if self.use_history else None
        x = state_vector(failure_state, rates)
        self.bandit.update(ACTIONS.index(action), x, reward)
        self.updates += 1

    def state_hash(self) -> str:
        return hashlib.sha256(self.bandit.to_dict()["b"].__repr__().encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {"policy_id": self.policy_id, "alpha": self.bandit.alpha,
                "use_history": self.use_history, "updates": self.updates,
                "bandit": self.bandit.to_dict()}

    @classmethod
    def from_dict(cls, d: dict) -> "LinUCBPolicy":
        obj = cls(alpha=d["alpha"], use_history=d["use_history"])
        obj.bandit = LinUCB.from_dict(d["bandit"])
        obj.updates = d["updates"]
        return obj
