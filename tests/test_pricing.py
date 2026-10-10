"""Pricing: peak classification, bucket->rate mapping, cache-write upper bound."""

from datetime import datetime, timezone

import pytest

from causalevo.pricing import (
    RATES_USD_PER_M,
    classify_price_tier,
    cost_for_usage,
    worst_case_cost_cny,
)
from causalevo.usage import UsageRecord


def test_weekend_is_off_peak():
    # 2026-10-10 is a Saturday.
    assert classify_price_tier(datetime(2026, 10, 10, 2, 0, tzinfo=timezone.utc)) == "off_peak"


def test_weekday_peak_windows():
    assert classify_price_tier(datetime(2026, 10, 12, 2, 0, tzinfo=timezone.utc)) == "peak"  # Mon 02:00
    assert classify_price_tier(datetime(2026, 10, 12, 7, 0, tzinfo=timezone.utc)) == "peak"  # Mon 07:00
    assert classify_price_tier(datetime(2026, 10, 12, 5, 0, tzinfo=timezone.utc)) == "off_peak"
    assert classify_price_tier(datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)) == "off_peak"


def test_cn_holiday_is_off_peak_even_in_window():
    assert classify_price_tier(datetime(2026, 10, 5, 2, 0, tzinfo=timezone.utc)) == "off_peak"  # Mon, holiday


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        classify_price_tier(datetime(2026, 10, 12, 2, 0))


def test_cost_buckets_map_to_rates():
    u = UsageRecord(uncached_input_tokens=1_000_000, cache_read_tokens=2_000_000,
                    cache_write_tokens=500_000, output_tokens=1_000_000)
    peak = cost_for_usage(u, "peak", usd_cny=7.0)
    expected_usd = (
        1.5 * RATES_USD_PER_M["input_cache_miss"][0]   # uncached + cache_write at MISS rate
        + 2.0 * RATES_USD_PER_M["input_cache_hit"][0]
        + 1.0 * RATES_USD_PER_M["output"][0]
    )
    assert abs(peak.cost_usd - expected_usd) < 1e-12
    assert abs(peak.cost_cny - expected_usd * 7.0) < 1e-9


def test_cache_write_billed_at_miss_not_hit():
    u = UsageRecord(uncached_input_tokens=0, cache_read_tokens=0,
                    cache_write_tokens=1_000_000, output_tokens=0)
    cost = cost_for_usage(u, "off_peak")
    assert abs(cost.cost_usd - RATES_USD_PER_M["input_cache_miss"][1]) < 1e-12


def test_unreported_cache_write_bills_as_zero():
    """Live adapter omitted cacheWriteTokens (2026-10-10 smoke): None, not 0."""
    u = UsageRecord(uncached_input_tokens=146, cache_read_tokens=0,
                    output_tokens=32, cache_write_tokens=None)
    cost = cost_for_usage(u, "peak")
    expected = (146 * 0.30 + 32 * 1.20) / 1e6
    assert abs(cost.cost_usd - expected) < 1e-12


def test_worst_case_uses_peak_miss_rates():
    cost = worst_case_cost_cny(1000, 64, usd_cny=7.1)
    expected = (1000 * 0.30 + 64 * 1.20) / 1e6 * 7.1
    assert abs(cost - expected) < 1e-12
