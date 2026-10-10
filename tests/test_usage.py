"""Usage parsing: happy path, aliases, settled-vs-shard, fail-closed gaps."""

import pytest

from causalevo.usage import (
    UsageRecord,
    UsageUnavailable,
    extract_settled_usage,
    parse_usage_mapping,
)

# Shape observed in the 2026-10-10 live smoke call (assistant/message data.usage).
SMOKE_USAGE = {
    "inputTokens": 146,
    "outputTokens": 32,
    "totalTokens": 178,
    "cacheReadTokens": 0,
    "reasoningTokens": 21,
}


def test_parse_smoke_shape_without_cache_write():
    u = parse_usage_mapping(SMOKE_USAGE)
    assert u.uncached_input_tokens == 146
    assert u.cache_read_tokens == 0
    assert u.output_tokens == 32
    assert u.cache_write_tokens is None and not u.cache_write_reported
    assert u.total_prompt_tokens == 146
    assert u.cache_hit_rate == 0.0


def test_parse_with_cache_write():
    u = parse_usage_mapping({**SMOKE_USAGE, "cacheWriteTokens": 10, "cacheReadTokens": 100})
    assert u.cache_write_reported and u.cache_write_tokens == 10
    assert u.total_prompt_tokens == 146 + 100 + 10  # uncached + read + write
    assert abs(u.cache_hit_rate - 100 / 256) < 1e-12


def test_missing_mandatory_bucket_fails_closed():
    with pytest.raises(UsageUnavailable):
        parse_usage_mapping({"inputTokens": 5, "outputTokens": 3})  # no cacheReadTokens
    with pytest.raises(UsageUnavailable):
        parse_usage_mapping({"cacheReadTokens": 5, "outputTokens": 3})  # no inputTokens
    with pytest.raises(UsageUnavailable):
        parse_usage_mapping({"inputTokens": 5, "cacheReadTokens": 0})  # no outputTokens


def test_negative_and_non_int_rejected():
    with pytest.raises(UsageUnavailable):
        parse_usage_mapping({**SMOKE_USAGE, "inputTokens": -1})
    with pytest.raises(UsageUnavailable):
        parse_usage_mapping({**SMOKE_USAGE, "outputTokens": "12"})
    with pytest.raises(UsageUnavailable):
        parse_usage_mapping({**SMOKE_USAGE, "cacheReadTokens": True})


def test_hit_rate_unavailable_on_zero_denominator():
    u = UsageRecord(uncached_input_tokens=0, cache_read_tokens=0, output_tokens=5)
    assert u.total_prompt_tokens == 0
    assert u.cache_hit_rate is None


def _message_event(usage: dict, text: str = "x", turn: int = 1, step: int = 1) -> dict:
    return {
        "type": "assistant/message",
        "data": {"turn": turn, "step": step,
                 "message": {"content": [{"text": text}]}, "usage": usage},
    }


def test_extract_settled_single_message():
    events = [
        {"type": "turn/start", "data": {}},
        _message_event(SMOKE_USAGE),
        {"type": "turn/end", "data": {"reason": {"kind": "completed"}}},
    ]
    u = extract_settled_usage(events)
    assert u.uncached_input_tokens == 146 and u.output_tokens == 32


def test_stream_shards_never_summed():
    """Cumulative shard frames inside one message must not add up."""
    shard = {"inputTokens": 100, "cacheReadTokens": 0, "outputTokens": 10}
    settled = {"inputTokens": 100, "cacheReadTokens": 0, "outputTokens": 32}
    event = {
        "type": "assistant/message",
        "data": {
            "turn": 1,
            "step": 1,
            "message": {},
            "stream": [
                {"type": "chunk", "chunk": {"type": "usage", "usage": shard}},
                {"type": "chunk", "chunk": {"type": "usage", "usage": settled}},
            ],
        },
    }
    u = extract_settled_usage([event])
    assert u.output_tokens == 32  # settled frame wins; 10+32 would be wrong


def test_multi_step_turn_sums_distinct_requests():
    events = [
        _message_event({"inputTokens": 100, "cacheReadTokens": 0, "outputTokens": 10}, turn=1, step=1),
        _message_event({"inputTokens": 130, "cacheReadTokens": 80, "outputTokens": 12}, turn=1, step=2),
    ]
    u = extract_settled_usage(events)
    assert u.uncached_input_tokens == 230
    assert u.cache_read_tokens == 80
    assert u.output_tokens == 22
    assert u.total_prompt_tokens == 310


def test_no_usage_fails_closed():
    with pytest.raises(UsageUnavailable):
        extract_settled_usage([{"type": "turn/end", "data": {"reason": {"kind": "completed"}}}])
