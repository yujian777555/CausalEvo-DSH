"""F2.2 fixtures: assistant/attempt settled-usage extraction and dedup.

IMPORTANT (docs/HARNESS_INTEGRATION.md records this): these fixtures are
CONSTRUCTED from the upstream event-structure contract (data.usage /
data.stream chunk:usage / turn / step / attempt fields), NOT captured from
real API failures. They pin the accounting semantics; they are not evidence
of how often the provider emits which shape.
"""

import pytest

from causalevo.usage import UsageUnavailable, extract_settled_usage


def attempt_event(usage: dict, *, turn=1, step=1, attempt=None, via_stream=False) -> dict:
    data: dict = {"turn": turn, "step": step, "message": {}}
    if attempt is not None:
        data["attempt"] = attempt
    if via_stream:
        shard = {**usage, "outputTokens": max(0, usage["outputTokens"] - 5)}
        data["stream"] = [
            {"type": "chunk", "chunk": {"type": "usage", "usage": shard}},
            {"type": "chunk", "chunk": {"type": "usage", "usage": usage}},
        ]
    else:
        data["usage"] = usage
    return {"type": "assistant/attempt", "data": data}


def message_event(usage: dict, *, turn=1, step=1) -> dict:
    return {"type": "assistant/message",
            "data": {"turn": turn, "step": step, "message": {}, "usage": usage}}


U1 = {"inputTokens": 700, "cacheReadTokens": 0, "outputTokens": 10}
U2 = {"inputTokens": 750, "cacheReadTokens": 128, "outputTokens": 12}


def test_attempt_only_failure_is_metered():
    """A failed attempt with settled usage bills even without any message."""
    u = extract_settled_usage([attempt_event(U1, attempt=1)])
    assert u.uncached_input_tokens == 700 and u.output_tokens == 10


def test_attempt_usage_from_final_stream_frame_only():
    u = extract_settled_usage([attempt_event(U1, attempt=1, via_stream=True)])
    assert u.output_tokens == 10  # settled frame, not shard+settled


def test_attempt_equal_to_committed_message_is_deduplicated():
    """Same (turn, step), no attempt id, equal usage -> same request twice
    reported; count once."""
    events = [message_event(U2), attempt_event(U2)]  # attempt lacks id
    u = extract_settled_usage(events)
    assert u.uncached_input_tokens == 750 and u.output_tokens == 12


def test_attempt_with_different_usage_is_a_distinct_billed_request():
    """Retried provider call inside one step: different settled usage ->
    both bill."""
    events = [attempt_event(U1, attempt=1), message_event(U2)]
    u = extract_settled_usage(events)
    assert u.uncached_input_tokens == 1450
    assert u.cache_read_tokens == 128
    assert u.output_tokens == 22


def test_duplicate_attempt_event_counted_once():
    events = [attempt_event(U1, attempt=3), attempt_event(U1, attempt=3)]
    u = extract_settled_usage(events)
    assert u.output_tokens == 10


def test_conflicting_duplicate_attempt_fails_closed():
    with pytest.raises(UsageUnavailable):
        extract_settled_usage([attempt_event(U1, attempt=3), attempt_event(U2, attempt=3)])


def test_conflicting_duplicate_message_fails_closed():
    with pytest.raises(UsageUnavailable):
        extract_settled_usage([message_event(U1), message_event(U2)])


def test_attempt_without_identity_fails_closed():
    event = {"type": "assistant/attempt", "data": {"usage": U1}}  # no turn/step
    with pytest.raises(UsageUnavailable):
        extract_settled_usage([event])


def test_no_usage_anywhere_raises():
    with pytest.raises(UsageUnavailable):
        extract_settled_usage([{"type": "assistant/attempt",
                                "data": {"turn": 1, "step": 1, "attempt": 1}}])


def test_failed_attempt_then_committed_message_sequence():
    """Realistic retry shape: failed attempt (usage A), then committed
    message (usage B) -> both metered, message counted once."""
    events = [
        attempt_event(U1, attempt=1),
        message_event(U2),
        message_event(U2),  # duplicate report of the same committed message
    ]
    u = extract_settled_usage(events)
    assert u.uncached_input_tokens == 1450 and u.output_tokens == 22


def test_dedup_is_order_independent():
    """attempt-before-message with equal usage must dedup exactly as
    message-before-attempt does."""
    forward = extract_settled_usage([attempt_event(U2), message_event(U2)])
    backward = extract_settled_usage([message_event(U2), attempt_event(U2)])
    assert forward == backward
    assert forward.uncached_input_tokens == 750 and forward.output_tokens == 12
