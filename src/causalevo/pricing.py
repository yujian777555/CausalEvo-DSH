"""Pricing with explicit provenance. No hardcoded "permanent" prices.

Price table snapshot: DeepSeek official pricing page fetched 2026-10-10
(https://api-docs.deepseek.com/quick_start/pricing), model deepseek-flash
(= DeepSeek-V4.1-Flash; legacy alias deepseek-v4-flash served by V4.1-Flash
and billed at Flash price).

Rates are USD per 1M tokens. Peak windows: 01:00-04:00 and 06:00-10:00 UTC,
Monday-Friday, excluding Chinese public holidays; all other hours off-peak
(weekends and CN public holidays are fully off-peak per the same page).

Cache-write pricing is NOT published separately by DeepSeek; we disclose that
and bill cache_write_tokens at the cache-MISS rate as a documented upper
bound (never silently equated with the cheaper cache-hit rate).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .usage import UsageRecord

PRICE_TABLE_META = {
    "source_url": "https://api-docs.deepseek.com/quick_start/pricing",
    "fetched_date": "2026-10-10",
    "currency": "USD",
    "unit": "per 1M tokens",
    "model": "deepseek-flash",
    "model_version": "DeepSeek-V4.1-Flash",
    "cache_write_pricing": "not published; billed at cache-miss rate as upper bound",
}

# USD per 1M tokens, (peak, off_peak)
RATES_USD_PER_M = {
    "input_cache_hit": (0.006, 0.003),
    "input_cache_miss": (0.30, 0.15),
    "output": (1.20, 0.60),
}

# USD -> CNY rate used for reporting. Source: recorded at run time by the
# benchmark config; this default is an explicit, dated assumption.
DEFAULT_USD_CNY = 7.10
DEFAULT_USD_CNY_META = "assumed rate for estimation, recorded 2026-10-10; reconcile against platform balance delta (CNY) for ground truth"

# Chinese public holidays (UTC dates) relevant to the Phase 0 window. The
# official rule excludes CN public holidays from peak pricing; weekends are
# off-peak regardless. Extend if the run window moves.
CN_PUBLIC_HOLIDAYS_2026 = {
    "2026-01-01", "2026-01-02",
    "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-21", "2026-02-22",
    "2026-04-05", "2026-04-06",
    "2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05",
    "2026-06-19", "2026-06-20", "2026-06-21",
    "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07",
}

_PEAK_WINDOWS = ((1, 4), (6, 10))  # UTC hour ranges [start, end)


def classify_price_tier(moment_utc: datetime) -> str:
    """'peak' | 'off_peak' for a UTC timestamp per the official rule."""
    if moment_utc.tzinfo is None:
        raise ValueError("classify_price_tier requires a timezone-aware UTC datetime")
    moment_utc = moment_utc.astimezone(timezone.utc)
    date_str = moment_utc.date().isoformat()
    if date_str in CN_PUBLIC_HOLIDAYS_2026:
        return "off_peak"
    if moment_utc.weekday() >= 5:  # Saturday/Sunday: fully off-peak
        return "off_peak"
    hour = moment_utc.hour
    for start, end in _PEAK_WINDOWS:
        if start <= hour < end:
            return "peak"
    return "off_peak"


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    tier: str
    cost_usd: float
    cost_cny: float
    usd_cny_rate: float


def cost_for_usage(usage: UsageRecord, tier: str, usd_cny: float = DEFAULT_USD_CNY) -> CostBreakdown:
    """Cost of one settled usage record at a given price tier.

    uncached_input -> miss rate; cache_read -> hit rate;
    cache_write -> miss rate (documented upper bound, see module docstring);
    output -> output rate.
    """
    if tier not in ("peak", "off_peak"):
        raise ValueError(f"unknown price tier {tier!r}")
    idx = 0 if tier == "peak" else 1
    miss = RATES_USD_PER_M["input_cache_miss"][idx]
    hit = RATES_USD_PER_M["input_cache_hit"][idx]
    out = RATES_USD_PER_M["output"][idx]
    usd = (
        (usage.uncached_input_tokens + (usage.cache_write_tokens or 0)) * miss
        + usage.cache_read_tokens * hit
        + usage.output_tokens * out
    ) / 1_000_000.0
    return CostBreakdown(tier=tier, cost_usd=usd, cost_cny=usd * usd_cny, usd_cny_rate=usd_cny)


def worst_case_cost_cny(
    max_prompt_tokens: int,
    max_output_tokens: int,
    usd_cny: float = DEFAULT_USD_CNY,
) -> float:
    """Conservative per-call worst case: everything uncached, at PEAK rates."""
    usage = UsageRecord(
        uncached_input_tokens=max_prompt_tokens,
        cache_read_tokens=0,
        cache_write_tokens=0,
        output_tokens=max_output_tokens,
    )
    return cost_for_usage(usage, "peak", usd_cny).cost_cny
