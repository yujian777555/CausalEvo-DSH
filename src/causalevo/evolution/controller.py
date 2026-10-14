"""CausalEvolutionController (P3.1-S2).

select_intervention(failure_state, candidates) -> {selected_action,
confidence, policy_version}. Confidence for LinUCB = normalized top-2 score
margin; for rule/random it is a fixed documented value. The controller owns
the episode memory and enforces time discipline through it."""

from __future__ import annotations

from typing import Any

from .memory import Episode, EpisodeMemory
from .policy import ACTIONS, LinUCBPolicy, Policy


class CausalEvolutionController:
    def __init__(self, policy: Policy, memory: EpisodeMemory | None = None) -> None:
        self.policy = policy
        self.memory = memory or EpisodeMemory()

    def _history_rates(self) -> list[float]:
        """Per-action empirical reward rate from PAST episodes only."""
        rates = []
        for action in ACTIONS:
            past = [e for e in self.memory.episodes if e.selected_action == action]
            rates.append(sum(e.reward for e in past) / len(past) if past else 0.0)
        return rates

    def select_intervention(self, failure_state: dict[str, Any],
                            candidates: list[str]) -> dict[str, Any]:
        selected = self.policy.select(failure_state, candidates, self._history_rates())
        if isinstance(self.policy, LinUCBPolicy):
            from .policy import state_vector
            x = state_vector(failure_state,
                             self._history_rates() if self.policy.use_history else None)
            scores = sorted(self.policy.bandit.scores(x), reverse=True)
            margin = (scores[0] - scores[1]) if len(scores) > 1 else 1.0
            confidence = "high" if margin > 0.5 else "medium" if margin > 0.1 else "low"
        else:
            confidence = "medium" if self.policy.policy_id == "B1-rule" else "low"
        return {
            "selected_action": selected,
            "confidence": confidence,
            "policy_version": f"{self.policy.policy_id}@{self.policy.state_hash()}",
        }

    def record_and_update(self, episode_id: int, failure_state: dict[str, Any],
                          candidates: list[str], selected_action: str,
                          reward: float, update_note: str = "") -> None:
        """Append the episode FIRST (temporal truth), then update the policy
        using only history strictly before this episode."""
        self.memory.append(Episode(episode_id, failure_state, list(candidates),
                                   selected_action, reward, update_note))
        history_rates = self._rates_before(episode_id)
        self.policy.update(failure_state, selected_action, reward, history_rates)

    def _rates_before(self, episode_id: int) -> list[float]:
        past = self.memory.history_up_to(episode_id)
        rates = []
        for action in ACTIONS:
            sel = [e for e in past if e.selected_action == action]
            rates.append(sum(e.reward for e in sel) / len(sel) if sel else 0.0)
        return rates
