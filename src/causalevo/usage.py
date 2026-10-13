"""Mutually-exclusive token-bucket accounting for DeepSeek Harness runs.

Upstream contract (verified by live smoke call 2026-10-10 and recorded in
docs/HARNESS_INTEGRATION.md): the deepseek-official adapter emits usage on
``assistant/message`` events (``data.usage``, duplicated by the final
``chunk:usage`` stream frame) shaped like::

    {"inputTokens": 146, "outputTokens": 32, "totalTokens": 178,
     "cacheReadTokens": 0, "reasoningTokens": 21}

``inputTokens`` counts ONLY uncached input tokens; it is mutually exclusive
with ``cacheReadTokens`` (and ``cacheWriteTokens`` when reported). The smoke
run showed ``cacheWriteTokens`` is NOT always reported, so it is an optional
bucket (plan P0.4: "cache_write_tokens (如上游返回)"). Therefore:

    total_prompt_tokens = uncached_input + cache_read + (cache_write if reported)
    cache_hit_rate      = cache_read / total_prompt_tokens   (None if total == 0)

Never use ``inputTokens`` alone as the prompt denominator, never add
``cache_read`` on top of a total that already includes it, and never sum
streaming shards: within one assistant/message the final usage frame is the
settled cumulative value for that request. Distinct assistant/message events
are DISTINCT provider requests (multi-step turns); their settled usages are
summed, because each request bills separately. Failed/retried attempts are
metered separately and never silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


class UsageUnavailable(RuntimeError):
    """Raised when usage data is missing or inconsistent (fail-closed)."""


_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "uncached_input_tokens": ("inputTokens", "uncached_input_tokens", "input_tokens"),
    "cache_read_tokens": ("cacheReadTokens", "cache_read_tokens", "prompt_cache_hit_tokens"),
    "output_tokens": ("outputTokens", "output_tokens", "completion_tokens"),
}
_OPTIONAL_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "cache_write_tokens": ("cacheWriteTokens", "cache_write_tokens"),
}


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """Settled usage for one provider request. Input buckets are exclusive.

    cache_write_tokens is None when the provider does not report that bucket;
    it then contributes 0 to the totals and ``cache_write_reported`` is False.
    """

    uncached_input_tokens: int
    cache_read_tokens: int
    output_tokens: int
    cache_write_tokens: int | None = None

    @property
    def cache_write_reported(self) -> bool:
        return self.cache_write_tokens is not None

    @property
    def total_prompt_tokens(self) -> int:
        return (
            self.uncached_input_tokens
            + self.cache_read_tokens
            + (self.cache_write_tokens or 0)
        )

    @property
    def cache_hit_rate(self) -> float | None:
        """cache_read / total_prompt; None when denominator is 0."""
        total = self.total_prompt_tokens
        if total <= 0:
            return None
        return self.cache_read_tokens / total

    def as_dict(self) -> dict[str, Any]:
        return {
            "uncached_input_tokens": self.uncached_input_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cache_write_reported": self.cache_write_reported,
            "output_tokens": self.output_tokens,
            "total_prompt_tokens": self.total_prompt_tokens,
            "cache_hit_rate": self.cache_hit_rate,
        }


def _coerce_non_negative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise UsageUnavailable(f"usage field {field_name!r} is not an int: {value!r}")
    if value < 0:
        raise UsageUnavailable(f"usage field {field_name!r} is negative: {value}")
    return value


def parse_usage_mapping(usage: Mapping[str, Any]) -> UsageRecord:
    """Parse one usage mapping into a UsageRecord. Fail-closed on gaps.

    uncached input, cache read and output buckets are mandatory; missing
    mandatory fields raise UsageUnavailable (never assumed zero). The
    cache-write bucket is optional per upstream behaviour (see docstring).
    """
    if not isinstance(usage, Mapping):
        raise UsageUnavailable(f"usage payload is not a mapping: {type(usage).__name__}")
    parsed: dict[str, int] = {}
    for canonical, aliases in _FIELD_ALIASES.items():
        found: Any = None
        found_alias: str | None = None
        for alias in aliases:
            if alias in usage:
                found = usage[alias]
                found_alias = alias
                break
        if found_alias is None:
            raise UsageUnavailable(
                f"usage payload missing required bucket {canonical!r} "
                f"(accepted aliases: {aliases}); got keys {sorted(map(str, usage.keys()))}"
            )
        parsed[canonical] = _coerce_non_negative_int(found, found_alias)
    cache_write: int | None = None
    for alias in _OPTIONAL_FIELD_ALIASES["cache_write_tokens"]:
        if alias in usage:
            cache_write = _coerce_non_negative_int(usage[alias], alias)
            break
    return UsageRecord(cache_write_tokens=cache_write, **parsed)


def _usage_from_message_event(event: Mapping[str, Any]) -> UsageRecord | None:
    """Settled usage of one assistant/message event, or None if it has none.

    Prefers data.usage; falls back to the LAST chunk:usage frame inside
    data.stream (earlier shards are superseded, never summed).
    """
    if event.get("type") != "assistant/message":
        return None
    data = event.get("data")
    if not isinstance(data, Mapping):
        return None
    return _usage_from_data(data)


def _usage_from_data(data: Mapping[str, Any]) -> UsageRecord | None:
    direct = data.get("usage")
    if isinstance(direct, Mapping):
        return parse_usage_mapping(direct)
    stream = data.get("stream")
    if isinstance(stream, list):
        for frame in reversed(stream):
            if not isinstance(frame, Mapping):
                continue
            chunk = frame.get("chunk")
            if isinstance(chunk, Mapping) and chunk.get("type") == "usage":
                payload = chunk.get("usage")
                if isinstance(payload, Mapping):
                    return parse_usage_mapping(payload)
    return None


def _event_identity(event: Mapping[str, Any], source: str) -> tuple[Any, ...]:
    """Provable request identity for dedup (R1.2-F2.2).

    assistant/message identifies its provider request by (turn, step); the
    committed message of a step is the request that produced it.
    assistant/attempt identifies by (turn, step, attempt-id) when the event
    carries one. Missing identity fields make dedup unprovable -> UsageUnavailable.
    """
    data = event.get("data")
    if not isinstance(data, Mapping):
        raise UsageUnavailable(f"{source} event has no data mapping")
    turn = data.get("turn")
    step = data.get("step")
    if turn is None or step is None:
        raise UsageUnavailable(
            f"{source} event lacks turn/step identity; refusing to guess at dedup"
        )
    if source == "attempt":
        attempt_id = data.get("attempt", data.get("attemptId"))
        return ("attempt", turn, step, attempt_id)
    return ("message", turn, step)


def extract_request_usages(events: Iterable[Mapping[str, Any]]) -> list[UsageRecord]:
    """One settled UsageRecord per distinct provider request, following the
    identity doctrine in extract_settled_usage. Raises UsageUnavailable when
    identity is unprovable; returns [] when no usage-bearing events exist."""
    return _collect_request_usages(list(events))


def _collect_request_usages(event_list: list[Mapping[str, Any]]) -> list[UsageRecord]:
    per_request: list[UsageRecord] = []
    counted_messages: dict[tuple[Any, ...], UsageRecord] = {}
    event_list = list(event_list)

    # Pass 1: committed messages are authoritative for their (turn, step).
    for event in event_list:
        if event.get("type") != "assistant/message":
            continue
        usage = _usage_from_message_event(event)
        if usage is None:
            continue
        key = _event_identity(event, "message")
        if key in counted_messages:
            if counted_messages[key] != usage:
                raise UsageUnavailable(
                    f"conflicting usages for the same committed request {key}"
                )
            continue  # duplicate report of the same request
        counted_messages[key] = usage
        per_request.append(usage)

    # Pass 2: attempts (incl. failed ones that never committed a message).
    # Identity doctrine (RISK-1 resolution, R2): usage VALUES can never prove
    # two requests are the same. Distinct event `seq` values are distinct
    # provider requests (observed 1:1 against logged HTTP requests in the
    # offline fake-provider probe, 2026-10-10). The only skip allowed is the
    # exact same event redelivered (same seq). An id-less attempt whose usage
    # equals the committed message at its (turn, step) is AMBIGUOUS — it may
    # be the same request or a different one that coincidentally cost the
    # same — so we fail closed instead of guessing.
    seen_attempt_seqs: dict[Any, UsageRecord] = {}
    for event in event_list:
        if event.get("type") != "assistant/attempt":
            continue
        data = event.get("data")
        if not isinstance(data, Mapping):
            raise UsageUnavailable("assistant/attempt event has no data mapping")
        usage = _usage_from_data(data)
        if usage is None:
            continue  # attempt without usage: handled by caller's fail-closed path
        key = _event_identity(event, "attempt")
        seq = event.get("seq")
        if key[3] is not None:
            dedup_key: Any = key  # explicit attempt id identifies the request
        elif seq is not None:
            dedup_key = ("attempt-seq", seq)
        else:
            raise UsageUnavailable(
                f"assistant/attempt at {key} has neither attempt id nor event seq; "
                "cannot establish request identity"
            )
        if dedup_key in seen_attempt_seqs:
            if seen_attempt_seqs[dedup_key] != usage:
                raise UsageUnavailable(
                    f"conflicting usages for the same attempt event {dedup_key}"
                )
            continue  # same event redelivered
        seen_attempt_seqs[dedup_key] = usage
        message_key = ("message", key[1], key[2])
        message_usage = counted_messages.get(message_key)
        if message_usage is not None and message_usage == usage and key[3] is None:
            raise UsageUnavailable(
                f"ambiguous identity: id-less assistant/attempt at (turn={key[1]}, "
                f"step={key[2]}) has usage equal to the committed message; cannot "
                "prove whether it is the same provider request (fail-closed)"
            )
        per_request.append(usage)

    return per_request


def extract_settled_usage(events: Iterable[Mapping[str, Any]]) -> UsageRecord:
    """Aggregate settled usage for one logical call's session events.

    Rules: one committed provider request per assistant/message (turn, step);
    failed/retried assistant/attempt events with settled usage also bill;
    dedup never uses usage VALUES (RISK-1) — distinct event `seq` values are
    distinct requests, only identical seq redelivery is skipped, and an
    id-less attempt matching the committed message's usage exactly is
    ambiguous -> UsageUnavailable (fail-closed). Streaming shards within one
    event are never summed; only the settled frame counts.
    """
    per_request = _collect_request_usages(list(events))
    if not per_request:
        raise UsageUnavailable("no settled usage found in attempt events")
    if len(per_request) == 1:
        return per_request[0]
    cache_write_values = [u.cache_write_tokens for u in per_request if u.cache_write_reported]
    return UsageRecord(
        uncached_input_tokens=sum(u.uncached_input_tokens for u in per_request),
        cache_read_tokens=sum(u.cache_read_tokens for u in per_request),
        output_tokens=sum(u.output_tokens for u in per_request),
        cache_write_tokens=(
            sum(cache_write_values) if len(cache_write_values) == len(per_request) else None
        ),
    )


@dataclass(slots=True)
class AttemptRecord:
    """One API attempt (including failures and retries)."""

    attempt_index: int
    status: str  # "ok" | "error"
    usage: UsageRecord | None
    finish_reason: str | None = None
    error: str | None = None


@dataclass(slots=True)
class CallRecord:
    """A logical benchmark call, possibly spanning several attempts."""

    attempts: list[AttemptRecord] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return bool(self.attempts) and self.attempts[-1].status == "ok"

    @property
    def final_usage(self) -> UsageRecord | None:
        for attempt in reversed(self.attempts):
            if attempt.usage is not None:
                return attempt.usage
        return None

    @property
    def total_output_tokens_all_attempts(self) -> int:
        """Retries and failed attempts still cost money; never drop them."""
        return sum(a.usage.output_tokens for a in self.attempts if a.usage is not None)

    @property
    def total_prompt_tokens_all_attempts(self) -> int:
        return sum(a.usage.total_prompt_tokens for a in self.attempts if a.usage is not None)
