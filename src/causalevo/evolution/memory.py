"""Episode memory with strict temporal discipline (P3.1-S4).

Append-only log; history_up_to(t) never returns episodes at or after t —
future leakage is structurally impossible without bypassing the API."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class Episode:
    episode_id: int
    failure_state: dict[str, Any]
    candidate_actions: list[str]
    selected_action: str
    reward: float
    update_note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EpisodeMemory:
    episodes: list[Episode] = field(default_factory=list)

    def append(self, ep: Episode) -> None:
        if self.episodes and ep.episode_id <= self.episodes[-1].episode_id:
            raise ValueError("episode ids must be strictly increasing (time order)")
        self.episodes.append(ep)

    def history_up_to(self, episode_id: int) -> list[Episode]:
        """Only episodes strictly before episode_id. Never the future."""
        return [e for e in self.episodes if e.episode_id < episode_id]

    def __len__(self) -> int:
        return len(self.episodes)
