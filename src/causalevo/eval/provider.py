"""Provider interface: one shape for fake (offline) and live (DeepSeek) paths.

The live path exists so Phase 2 wiring needs no redesign — but it is CLOSED
by default: constructing a live adapter without BOTH DEEPSEEK_API_KEY and the
one-off Planner authorization (CE_DSH_LIVE_AUTH=phase1-pilot) raises before
any socket, URL, or endpoint object is produced. `live_enabled` defaults to
False and is only ever True after that check passes.

Tests must never contact api.deepseek.com; the guard is exercised only to the
refusal point.
"""

from __future__ import annotations

from dataclasses import dataclass

from .fake_provider import FakeProvider
from .harness_agent import LIVE_AUTH_ENV, LIVE_AUTH_VALUE

DEEPSEEK_BASE_URL = "https://api.deepseek.com"  # constant only; never dialed here


class LiveNotAuthorized(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderEndpoint:
    """Where the runtime should send chat completions."""

    kind: str  # "fake" | "live"
    base_url: str
    api_key: str
    live_enabled: bool = False


def fake_endpoint(provider: FakeProvider) -> ProviderEndpoint:
    """Offline endpoint on the internal network's provider container or host."""
    return ProviderEndpoint(kind="fake", base_url=provider.base_url,
                            api_key="sk-fake-offline-no-cost", live_enabled=False)


def live_endpoint(env: dict[str, str] | None = None) -> ProviderEndpoint:
    """The real DeepSeek endpoint. Refuses unless explicitly authorized."""
    import os

    env = os.environ if env is None else env
    key = env.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise LiveNotAuthorized("live endpoint requires DEEPSEEK_API_KEY")
    if env.get(LIVE_AUTH_ENV) != LIVE_AUTH_VALUE:
        raise LiveNotAuthorized(
            f"live endpoint requires {LIVE_AUTH_ENV}={LIVE_AUTH_VALUE} "
            "(one-off Planner authorization); live_enabled stays False"
        )
    return ProviderEndpoint(kind="live", base_url=DEEPSEEK_BASE_URL,
                            api_key=key, live_enabled=True)
