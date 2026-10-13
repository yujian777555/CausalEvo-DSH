"""RuntimeBudget (R2-S2): reserve/settle ledger, hard caps, fail-closed spend."""

import pytest

from causalevo.eval.policy import B0, B1
from causalevo.eval.runtime_budget import BudgetStop, RuntimeBudget
from causalevo.pricing import cost_for_usage
from causalevo.usage import UsageRecord

PRICE_TIER = "off_peak"
USD_CNY = 7.10


def _budget(**overrides) -> RuntimeBudget:
    kwargs = dict(
        max_provider_calls=10,
        max_total_output_tokens=1000,
        max_tool_calls=10,
        wall_time_s=300,
    )
    kwargs.update(overrides)
    return RuntimeBudget(**kwargs)


def test_reserve_then_settle_accumulates_ledger():
    budget = _budget()
    usage = UsageRecord(
        uncached_input_tokens=100,
        cache_read_tokens=64,
        output_tokens=50,
        cache_write_tokens=10,
    )
    budget.before_provider_request(0.01)
    assert budget.ledger.reserved_cost_cny == pytest.approx(0.01)

    budget.after_provider_request(usage, price_tier=PRICE_TIER, usd_cny=USD_CNY)
    expected_cost = cost_for_usage(usage, PRICE_TIER, USD_CNY).cost_cny
    assert budget.ledger.provider_attempts == 1
    assert budget.ledger.known_input_tokens == 100 + 10  # uncached + cache_write
    assert budget.ledger.cache_read_tokens == 64
    assert budget.ledger.output_tokens == 50
    assert budget.ledger.known_cost_cny == pytest.approx(expected_cost)

    budget.before_provider_request(0.01)
    budget.after_provider_request(usage, price_tier=PRICE_TIER, usd_cny=USD_CNY)
    assert budget.ledger.provider_attempts == 2
    assert budget.ledger.known_input_tokens == 2 * 110
    assert budget.ledger.cache_read_tokens == 2 * 64
    assert budget.ledger.output_tokens == 2 * 50
    assert budget.ledger.known_cost_cny == pytest.approx(2 * expected_cost)


def test_provider_call_cap_stops_request_beyond_cap():
    budget = _budget(max_provider_calls=1)
    usage = UsageRecord(uncached_input_tokens=10, cache_read_tokens=0, output_tokens=1)
    budget.before_provider_request(0.0)
    budget.after_provider_request(usage, price_tier=PRICE_TIER, usd_cny=USD_CNY)
    with pytest.raises(BudgetStop, match="provider_calls exhausted"):
        budget.before_provider_request(0.0)


def test_tool_call_cap_stops_call_beyond_cap():
    budget = _budget(max_tool_calls=2)
    budget.before_tool_call("fs_read")
    budget.before_tool_call("fs_write")
    with pytest.raises(BudgetStop, match="tool_calls exhausted"):
        budget.before_tool_call("fs_read")
    assert budget.ledger.tool_attempts == 2


def test_output_token_cap_raises_on_settle():
    budget = _budget(max_total_output_tokens=100)
    usage = UsageRecord(uncached_input_tokens=10, cache_read_tokens=0, output_tokens=101)
    budget.before_provider_request(0.0)
    with pytest.raises(BudgetStop, match="output tokens exceeded"):
        budget.after_provider_request(usage, price_tier=PRICE_TIER, usd_cny=USD_CNY)
    assert budget.ledger.output_tokens == 101  # over-cap usage is still metered


def test_cost_cap_raises_on_settle():
    budget = _budget(max_cost_cny=1e-9)
    usage = UsageRecord(uncached_input_tokens=10, cache_read_tokens=0, output_tokens=1)
    budget.before_provider_request(0.0)
    with pytest.raises(BudgetStop, match="known cost exceeded"):
        budget.after_provider_request(usage, price_tier=PRICE_TIER, usd_cny=USD_CNY)


def test_cost_reservation_that_would_exceed_raises_before_send():
    budget = _budget(max_cost_cny=0.001)
    budget.before_provider_request(0.0005)
    with pytest.raises(BudgetStop, match="cost reservation would exceed"):
        budget.before_provider_request(0.0006)  # 0.0005 reserved + 0.0006 new > 0.001


def test_unknown_usage_fails_closed_and_is_never_free():
    budget = _budget()
    budget.before_provider_request(0.0)
    with pytest.raises(BudgetStop, match="unknown_cost"):
        budget.after_provider_request(None, price_tier=PRICE_TIER, usd_cny=USD_CNY)
    assert budget.ledger.provider_attempts == 1
    assert budget.ledger.unknown_spend_attempts == 1
    assert budget.ledger.known_cost_cny == 0.0  # flagged unknown, not claimed as ¥0


def test_wall_time_zero_raises():
    budget = _budget(wall_time_s=0)
    budget.ledger.started_monotonic -= 1.0  # guarantee positive elapsed at any clock granularity
    with pytest.raises(BudgetStop, match="wall_time exceeded"):
        budget.check_wall_time()


def test_snapshot_contains_all_ledger_fields():
    budget = _budget()
    budget.before_tool_call("fs_read")
    snap = budget.snapshot()
    assert set(snap) == {
        "provider_attempts",
        "tool_attempts",
        "known_input_tokens",
        "cache_read_tokens",
        "output_tokens",
        "known_cost_cny",
        "unknown_spend_attempts",
        "elapsed_s",
    }
    assert snap["tool_attempts"] == 1
    assert snap["elapsed_s"] >= 0.0


def test_b0_b1_budget_parity_identical_behavior():
    def build(policy) -> RuntimeBudget:
        b = policy.budget
        return RuntimeBudget(
            max_provider_calls=b.max_provider_calls,
            max_total_output_tokens=b.max_total_output_tokens,
            max_tool_calls=b.max_tool_calls,
            wall_time_s=b.wall_time_s,
        )

    assert B0.budget == B1.budget  # same envelope constants
    usage = UsageRecord(uncached_input_tokens=36, cache_read_tokens=64, output_tokens=12)
    snapshots = []
    for policy in (B0, B1):
        budget = build(policy)
        budget.before_provider_request(0.01)
        budget.after_provider_request(usage, price_tier=PRICE_TIER, usd_cny=USD_CNY)
        budget.before_tool_call("fs_read")
        snapshots.append({k: v for k, v in budget.snapshot().items() if k != "elapsed_s"})
    assert snapshots[0] == snapshots[1]

    for policy in (B0, B1):
        budget = build(policy)
        for _ in range(policy.budget.max_provider_calls):
            budget.before_provider_request(0.0)
            budget.after_provider_request(usage, price_tier=PRICE_TIER, usd_cny=USD_CNY)
        with pytest.raises(BudgetStop):
            budget.before_provider_request(0.0)
