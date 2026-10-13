"""F2.2/R2 fixtures: assistant/attempt settled-usage extraction and identity.

IMPORTANT (docs/HARNESS_INTEGRATION.md records this): these fixtures are
CONSTRUCTED from the upstream event-structure contract plus the 2026-10-10
fake-provider probe (6 attempt events ↔ 6 HTTP requests). They pin accounting
semantics; they are not evidence of provider failure frequencies.
"""

import pytest

from causalevo.usage import UsageUnavailable, extract_settled_usage


def attempt_event(usage: dict, *, turn=1, step=1, attempt=None, seq=None,
                  via_stream=False) -> dict:
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
    event = {"type": "assistant/attempt", "data": data}
    if seq is not None:
        event["seq"] = seq
    return event


def message_event(usage: dict, *, turn=1, step=1, seq=100) -> dict:
    return {"type": "assistant/message", "seq": seq,
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


def test_attempt_with_different_usage_is_a_distinct_billed_request():
    """Retried provider call inside one step: different settled usage ->
    both bill."""
    events = [attempt_event(U1, attempt=1), message_event(U2)]
    u = extract_settled_usage(events)
    assert u.uncached_input_tokens == 1450
    assert u.cache_read_tokens == 128
    assert u.output_tokens == 22


def test_equal_usage_attempt_and_message_is_ambiguous_fail_closed():
    """RISK-1: equal usage can NEVER prove sameness; ambiguous identity stops."""
    with pytest.raises(UsageUnavailable):
        extract_settled_usage([message_event(U2), attempt_event(U2)])
    with pytest.raises(UsageUnavailable):
        extract_settled_usage([attempt_event(U2), message_event(U2)])


def test_same_attempt_event_redelivered_is_counted_once():
    """Exact same event (same seq) redelivered = one request."""
    events = [attempt_event(U1, seq=42), attempt_event(U1, seq=42)]
    u = extract_settled_usage(events)
    assert u.output_tokens == 10


def test_distinct_seqs_are_distinct_requests_even_with_equal_usage():
    """The 2026-10-10 probe case: 6 retries, equal usage, distinct seqs ->
    all 6 bill. Usage values must NOT collapse them."""
    events = [attempt_event(U1, seq=s) for s in range(9, 15)]
    u = extract_settled_usage(events)
    assert u.uncached_input_tokens == 6 * 700
    assert u.output_tokens == 6 * 10


def test_conflicting_usage_same_seq_fails_closed():
    with pytest.raises(UsageUnavailable):
        extract_settled_usage([attempt_event(U1, seq=7), attempt_event(U2, seq=7)])


def test_attempt_without_identity_fails_closed():
    with pytest.raises(UsageUnavailable):
        extract_settled_usage([{"type": "assistant/attempt", "data": {"usage": U1}}])


def test_attempt_without_seq_or_id_fails_closed():
    with pytest.raises(UsageUnavailable):
        extract_settled_usage([attempt_event(U1)])  # turn/step but no seq/id


def test_no_usage_anywhere_raises():
    with pytest.raises(UsageUnavailable):
        extract_settled_usage([{"type": "assistant/attempt", "seq": 1,
                                "data": {"turn": 1, "step": 1, "attempt": 1}}])


def test_failed_attempt_then_committed_message_sequence():
    """Failed attempt (usage A, seq 9) then committed message (usage B):
    both metered; a duplicate redelivery of the message is counted once."""
    events = [
        attempt_event(U1, seq=9),
        message_event(U2, seq=12),
        message_event(U2, seq=12),  # same event redelivered
    ]
    u = extract_settled_usage(events)
    assert u.uncached_input_tokens == 1450 and u.output_tokens == 22
