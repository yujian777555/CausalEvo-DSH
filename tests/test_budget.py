"""Budget gate: fail-closed refusal, conservative metering, spend tracking."""

import pytest

from causalevo.budget import BudgetExceeded, BudgetGate


def test_allows_when_worst_case_fits():
    gate = BudgetGate(cap_cny=10.0, worst_case_per_call_cny=0.05)
    gate.check_can_start(100)  # 100 * 0.05 = 5.0 < 10


def test_refuses_when_projection_exceeds_cap():
    gate = BudgetGate(cap_cny=1.0, worst_case_per_call_cny=0.05)
    with pytest.raises(BudgetExceeded):
        gate.check_can_start(25)  # 25 * 0.05 = 1.25 > 1.0


def test_refuses_after_spend_accumulates():
    gate = BudgetGate(cap_cny=1.0, worst_case_per_call_cny=0.05)
    gate.record_spend(0.9, calls_completed=18)
    with pytest.raises(BudgetExceeded):
        gate.check_can_start(3)  # 0.9 + 0.15 > 1.0
    gate.check_can_start(1)  # 0.9 + 0.05 <= 1.0 still fine


def test_invalid_params_rejected():
    with pytest.raises(ValueError):
        BudgetGate(cap_cny=0, worst_case_per_call_cny=0.1)
    with pytest.raises(ValueError):
        BudgetGate(cap_cny=1, worst_case_per_call_cny=0)
    gate = BudgetGate(cap_cny=1.0, worst_case_per_call_cny=0.05)
    with pytest.raises(ValueError):
        gate.check_can_start(0)
    with pytest.raises(ValueError):
        gate.record_spend(-0.1)
