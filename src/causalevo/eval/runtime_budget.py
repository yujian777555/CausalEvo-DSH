"""Runtime budget gate for agent task runs (R2-S2).

Not a static dataclass: a live ledger that
- reserves a conservative upper bound BEFORE each provider request,
- settles with the actual metered usage AFTER the response,
- counts every provider attempt (multi-step tool loops included) and every
  tool call against the SAME envelope for B0 and B1,
- hard-stops the run on breach (budget_stop) or unknown spend,
- never treats a failed attempt as free.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..pricing import cost_for_usage
from ..usage import UsageRecord


class BudgetStop(RuntimeError):
    """Raised when the runtime budget envelope is exhausted."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(slots=True)
class AttemptLedger:
    provider_attempts: int = 0
    tool_attempts: int = 0
    known_input_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    known_cost_cny: float = 0.0
    unknown_spend_attempts: int = 0
    reserved_cost_cny: float = 0.0
    started_monotonic: float = field(default_factory=time.monotonic)


@dataclass(slots=True)
class RuntimeBudget:
    """One task's runtime envelope. Shared shape for B0/B1 (parity)."""

    max_provider_calls: int
    max_total_output_tokens: int
    max_tool_calls: int
    wall_time_s: int
    max_cost_cny: float | None = None
    ledger: AttemptLedger = field(default_factory=AttemptLedger)

    def check_wall_time(self) -> None:
        elapsed = time.monotonic() - self.ledger.started_monotonic
        if elapsed > self.wall_time_s:
            raise BudgetStop(f"wall_time exceeded: {elapsed:.1f}s > {self.wall_time_s}s")

    def before_provider_request(self, reserved_cost_cny: float) -> None:
        """Reserve a conservative upper bound before sending; fail early."""
        self.check_wall_time()
        if self.ledger.provider_attempts + 1 > self.max_provider_calls:
            raise BudgetStop(
                f"provider_calls exhausted: {self.ledger.provider_attempts + 1} > "
                f"{self.max_provider_calls}"
            )
        if self.max_cost_cny is not None and (
            self.ledger.known_cost_cny + self.ledger.reserved_cost_cny + reserved_cost_cny
            > self.max_cost_cny
        ):
            raise BudgetStop("cost reservation would exceed max_cost_cny")
        self.ledger.reserved_cost_cny += reserved_cost_cny

    def after_provider_request(
        self, usage: UsageRecord | None, *, price_tier: str, usd_cny: float
    ) -> None:
        """Settle one provider attempt. usage=None means the request may have
        left the machine unmeasured -> unknown spend, fail-closed stop."""
        self.ledger.provider_attempts += 1
        if usage is None:
            self.ledger.unknown_spend_attempts += 1
            raise BudgetStop("unknown_cost: provider attempt without settled usage")
        self.ledger.known_input_tokens += (
            usage.uncached_input_tokens + (usage.cache_write_tokens or 0)
        )
        self.ledger.cache_read_tokens += usage.cache_read_tokens
        self.ledger.output_tokens += usage.output_tokens
        cost = cost_for_usage(usage, price_tier, usd_cny).cost_cny
        self.ledger.known_cost_cny += cost
        if self.ledger.output_tokens > self.max_total_output_tokens:
            raise BudgetStop(
                f"output tokens exceeded: {self.ledger.output_tokens} > "
                f"{self.max_total_output_tokens}"
            )
        if self.max_cost_cny is not None and self.ledger.known_cost_cny > self.max_cost_cny:
            raise BudgetStop(
                f"known cost exceeded: {self.ledger.known_cost_cny:.6f} > {self.max_cost_cny}"
            )

    def record_unknown_attempt(self) -> None:
        """A provider request that was sent (or cannot be proven unsent) but
        returned no settled usage: count it as unknown spend. Never raises;
        the caller decides to stop (fail-closed) — recorded, never silently 0."""
        self.ledger.provider_attempts += 1
        self.ledger.unknown_spend_attempts += 1

    def before_tool_call(self, tool_name: str) -> None:
        self.check_wall_time()
        if self.ledger.tool_attempts + 1 > self.max_tool_calls:
            raise BudgetStop(
                f"tool_calls exhausted: {self.ledger.tool_attempts + 1} > {self.max_tool_calls}"
            )
        self.ledger.tool_attempts += 1

    def snapshot(self) -> dict:
        return {
            "provider_attempts": self.ledger.provider_attempts,
            "tool_attempts": self.ledger.tool_attempts,
            "known_input_tokens": self.ledger.known_input_tokens,
            "cache_read_tokens": self.ledger.cache_read_tokens,
            "output_tokens": self.ledger.output_tokens,
            "known_cost_cny": round(self.ledger.known_cost_cny, 10),
            "unknown_spend_attempts": self.ledger.unknown_spend_attempts,
            "elapsed_s": round(time.monotonic() - self.ledger.started_monotonic, 3),
        }
