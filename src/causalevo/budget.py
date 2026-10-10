"""Fail-closed budget gate for live API spend.

The gate answers one question before every new live request: "if everything
still planned went as badly as possible, could we exceed the authorized cap?"
If the answer is not provably "no", the run stops. Billing data may lag, so
the gate never claims absolute safety; it refuses new work early instead.
"""

from __future__ import annotations

from dataclasses import dataclass


class BudgetExceeded(RuntimeError):
    """Raised when starting a new call could not be proven within budget."""


@dataclass(slots=True)
class BudgetGate:
    cap_cny: float
    worst_case_per_call_cny: float
    spent_cny: float = 0.0
    completed_calls: int = 0

    def __post_init__(self) -> None:
        if self.cap_cny <= 0:
            raise ValueError("cap_cny must be positive")
        if self.worst_case_per_call_cny <= 0:
            raise ValueError("worst_case_per_call_cny must be positive")

    @property
    def remaining_cny(self) -> float:
        return self.cap_cny - self.spent_cny

    def check_can_start(self, planned_calls_remaining_including_this: int) -> None:
        """Fail-closed check before a new live request.

        Requires actual spend so far plus worst case for every planned call
        (including this one) to stay under the cap.
        """
        if planned_calls_remaining_including_this < 1:
            raise ValueError("planned_calls_remaining_including_this must be >= 1")
        projected = self.spent_cny + planned_calls_remaining_including_this * self.worst_case_per_call_cny
        if projected > self.cap_cny:
            raise BudgetExceeded(
                f"refusing new live call: spent {self.spent_cny:.4f} CNY + "
                f"{planned_calls_remaining_including_this} planned x worst-case "
                f"{self.worst_case_per_call_cny:.4f} CNY = {projected:.4f} CNY "
                f"> cap {self.cap_cny:.4f} CNY"
            )

    def record_spend(self, amount_cny: float, calls_completed: int = 1) -> None:
        if amount_cny < 0:
            raise ValueError("amount_cny must be >= 0")
        self.spent_cny += amount_cny
        self.completed_calls += calls_completed
