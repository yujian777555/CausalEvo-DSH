"""Intervention schema (P2.3-S1). Richer than the P2.2 interface skeleton:
serializable, explainable, replayable. The schema is the only contract the
replay engine accepts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from ..analysis.schema import FailureCategory


class InterventionType(str, Enum):
    TOOL = "tool_intervention"
    PLANNING = "planning_intervention"
    VERIFICATION = "verification_intervention"
    STRATEGY = "strategy_intervention"
    KNOWLEDGE = "knowledge_intervention"
    NONE = "no_intervention"


@dataclass(frozen=True, slots=True)
class CandidateIntervention:
    intervention_id: str
    target_failure: str          # FailureCategory value
    intervention_type: str       # InterventionType value
    description: str
    required_change: str         # what changes in the agent loop (mechanism)
    expected_effect: str
    confidence: str              # high|medium|low
    # Replay binding: name of the deterministic tape transform the counterfactual
    # engine applies (see counterfactual/replay.py). "identity" = no change.
    tape_transform: str = "identity"
    transform_args: dict[str, Any] | None = None

    def validate(self) -> None:
        if self.target_failure not in {c.value for c in FailureCategory}:
            raise ValueError(f"unknown target_failure {self.target_failure!r}")
        if self.intervention_type not in {t.value for t in InterventionType}:
            raise ValueError(f"unknown intervention_type {self.intervention_type!r}")
        if self.confidence not in ("high", "medium", "low"):
            raise ValueError(f"unknown confidence {self.confidence!r}")
        if not self.intervention_id or not self.required_change:
            raise ValueError("intervention_id and required_change are required")

    def stable_id(self) -> str:
        payload = json.dumps(
            {k: v for k, v in asdict(self).items() if k != "intervention_id"},
            sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()[:12]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "CandidateIntervention":
        obj = cls(**json.loads(text))
        obj.validate()
        return obj
