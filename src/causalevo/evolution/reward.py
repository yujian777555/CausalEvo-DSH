"""Reward shaping (P3.1-S1). reward = success_delta - lambda * cost_delta.

The reward comes from counterfactual outcome DIFFERENCES measured by replay,
never from model self-report. cost_delta uses the synthetic metering of the
tape world; lambda converts it to a success-comparable penalty.
"""

from __future__ import annotations

DEFAULT_LAMBDA = 100.0  # 0.001 CNY extra synthetic cost = 0.1 reward penalty


def compute_reward(success_delta: int, cost_delta_cny: float,
                   lambda_cny: float = DEFAULT_LAMBDA) -> float:
    return float(success_delta) - lambda_cny * max(0.0, cost_delta_cny)
