"""Runner abstraction: the same orchestration drives a live Harness or a fake.

Dry-run uses FakeRunner — deterministic synthetic usage, no network, no key.
Live uses HarnessRunner — deepseek-harness-sdk over JSON-RPC stdio with the
no-tools patch profile. Both return a RunnerOutcome with raw session events;
usage extraction happens once, in benchmark.py, via usage.extract_settled_usage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .usage import UsageRecord


@dataclass(slots=True)
class RunnerOutcome:
    ok: bool
    final_response: str = ""
    finish_reason: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    # error_kind distinguishes failures that provably never sent a request
    # ("local_rejected": validation/refusal before any byte left) from
    # "transport"/"provider" failures where spend is possible but unmeasured.
    error_kind: str | None = None  # None | "local_rejected" | "transport" | "provider"
    wire_model: str | None = None
    registered_tools: list[str] | None = None


class Runner(Protocol):
    def run(self, session_id: str, prompt: str) -> RunnerOutcome: ...
    def close(self) -> None: ...


def estimate_tokens(text: str) -> int:
    """Conservative chars->tokens estimate for dry-run and preflight only.
    Never used for billing: billing uses settled provider usage only."""
    return max(1, (len(text) + 1) // 2)


class FakeRunner:
    """Offline deterministic provider. Simulates plausible cache behaviour so
    the orchestration, accounting and budget gate can be exercised end-to-end
    without any API spend. NOT evidence of real cache behaviour."""

    def __init__(self, prompt_token_estimator=estimate_tokens):
        self._estimator = prompt_token_estimator
        self._history_tokens: dict[str, int] = {}
        self.calls: list[tuple[str, str]] = []

    def run(self, session_id: str, prompt: str) -> RunnerOutcome:
        self.calls.append((session_id, prompt))
        prompt_tokens = self._estimator(prompt)
        history = self._history_tokens.get(session_id, 0)
        # Simulated provider: repeated session history reads as cache hits;
        # the fresh part of the prompt is a miss. New sessions start at 0.
        cache_read = history
        uncached = prompt_tokens
        output = 12
        self._history_tokens[session_id] = history + prompt_tokens + output
        usage = UsageRecord(
            uncached_input_tokens=uncached,
            cache_read_tokens=cache_read,
            cache_write_tokens=0,
            output_tokens=output,
        )
        events = [
            {
                "type": "assistant/message",
                "data": {
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": '{"task":"T000","status":"ok"}'}],
                        "source": {"kind": "model", "model": "fake-offline-model"},
                    },
                    "usage": {
                        "inputTokens": usage.uncached_input_tokens,
                        "cacheReadTokens": usage.cache_read_tokens,
                        "cacheWriteTokens": usage.cache_write_tokens,
                        "outputTokens": usage.output_tokens,
                    },
                },
            },
            {"type": "turn/end", "data": {"reason": {"kind": "completed"}}},
        ]
        return RunnerOutcome(
            ok=True,
            final_response='{"task":"T000","status":"ok"}',
            finish_reason="completed",
            events=events,
            wire_model="fake-offline-model",
            registered_tools=[],
        )

    def close(self) -> None:
        return None


class HarnessRunner:
    """Live runner over deepseek-harness-sdk. Tools are disabled via the
    benchmark patch profile; DSH_HOME and the workspace are isolated dirs."""

    def __init__(
        self,
        *,
        dsh_home: str,
        workspace: str,
        patch_path: str,
        model: str,
        reasoning_effort: str | None,
        max_tokens: int,
        initialize_timeout_seconds: float = 60.0,
        request_timeout_seconds: float | None = 180.0,
    ) -> None:
        from deepseek_harness import DeepSeekHarness, DeepSeekHarnessConfig

        self._harness = DeepSeekHarness(
            DeepSeekHarnessConfig(
                provider="deepseek-official",
                model=model,
                reasoning_effort=reasoning_effort,
                max_tokens=max_tokens,
                cwd=workspace,
                runtime_cwd=workspace,
                dsh_home=dsh_home,
                patches=(patch_path,),
                initialize_timeout_seconds=initialize_timeout_seconds,
                request_timeout_seconds=request_timeout_seconds,
                env={"DSH_PERMISSION_MODE": "read-only"},
            )
        )
        self._harness.start()
        self._tools_cache: list[str] | None = None

    def run(self, session_id: str, prompt: str) -> RunnerOutcome:
        try:
            result = self._harness.run(prompt, session_id=session_id)
        except Exception as exc:  # transport/protocol/API errors -> failed attempt
            # The request may or may not have left the machine: spend unknown.
            return RunnerOutcome(ok=False, error=f"{type(exc).__name__}: {exc}", error_kind="transport")
        return RunnerOutcome(
            ok=result.finish_reason is not None,
            final_response=result.final_response,
            finish_reason=result.finish_reason,
            events=[dict(e) for e in result.events],
            wire_model=_extract_wire_model(result.events),
            registered_tools=self._tools_cache,
        )

    def close(self) -> None:
        self._harness.close()


def _extract_wire_model(events: list[dict[str, Any]]) -> str | None:
    """Best-effort extraction of the provider-side model id from events."""
    for event in reversed(events):
        stack: list[Any] = [event]
        while stack:
            obj = stack.pop()
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key in ("model", "modelId", "wireModel") and isinstance(value, str):
                        return value
                    stack.append(value)
            elif isinstance(obj, list):
                stack.extend(obj)
    return None
