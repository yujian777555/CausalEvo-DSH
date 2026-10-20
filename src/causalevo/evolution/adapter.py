"""CausalPolicyAdapter (P4-R1.1-S2): deploy frozen evolved policies honestly.

B4-live: wraps the REAL LinUCB controller from Phase 3.1 with a frozen
snapshot — select_intervention is genuinely called; the policy is never
updated during evaluation (frozen deployment, no test-set leakage).

B5-live: loads the ACTUAL NSGA-III Pareto front artifact from
results/phase3/evolution/pareto_front.json, verifies the genome id and the
source-file hash, and derives the executable intervention text FROM the
genome's active genes (never a hardcoded bundle).

This module adds a new interface; it does not modify frozen Phase 3 code and
its results must never be backfilled into the 2026-10-14 pilot rows.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .controller import CausalEvolutionController
from .genome import InterventionGenome
from .memory import EpisodeMemory
from .policy import ACTIONS, LinUCBPolicy

ADAPTER_VERSION = "r1.1"

# Observable-failure -> intervention-text key, used when the deployed genome
# bundles multiple genes: the failure evidence picks the gene whose
# intervention addresses it; otherwise all active genes' texts are bundled.
_GENE_TO_TEXT_KEY = {
    "tool_validation": "tool_validation",
    "read_before_write": "read_before_write",
    "verification_level": "verification",
    "stagnation_break": "planning",
}


class CausalPolicyAdapter:
    def __init__(self, mode: str, *, controller: CausalEvolutionController | None = None,
                 genome: InterventionGenome | None = None,
                 provenance: dict[str, Any] | None = None) -> None:
        if mode not in ("cea-v0", "cea-v1"):
            raise ValueError(mode)
        self.mode = mode
        self.controller = controller
        self.genome = genome
        self.provenance = provenance or {}

    # ---------- B4-live: real LinUCB controller with a frozen snapshot ----------
    @classmethod
    def cea_v0(cls, policy_snapshot: dict[str, Any]) -> "CausalPolicyAdapter":
        policy = LinUCBPolicy.from_dict(policy_snapshot)
        controller = CausalEvolutionController(policy, EpisodeMemory())
        return cls("cea-v0", controller=controller,
                   provenance={"policy_id": policy.policy_id,
                               "updates_at_load": policy.updates})

    def select(self, failure_state: dict[str, Any],
             candidates: list[str] | None = None) -> dict[str, Any]:
        """cea-v0: REAL controller call, frozen policy (no update here)."""
        if self.mode != "cea-v0" or self.controller is None:
            raise RuntimeError("select() is only valid for cea-v0 mode")
        candidates = candidates or list(ACTIONS)
        out = self.controller.select_intervention(failure_state, candidates)
        out["adapter_version"] = ADAPTER_VERSION
        out["deployment"] = "frozen-no-update"
        return out

    # ---------- B5-live: frozen Pareto genome from the NSGA-III artifact ----------
    @classmethod
    def cea_v1(cls, pareto_front_path: Path,
               genome_id: str | None = None) -> "CausalPolicyAdapter":
        front = json.loads(pareto_front_path.read_text(encoding="utf-8"))
        source_sha = hashlib.sha256(pareto_front_path.read_bytes()).hexdigest()
        if not front:
            raise ValueError("empty pareto front")
        if genome_id is None:
            member = max(front, key=lambda m: (m["train_fitness"][0],
                                               m["train_fitness"][3]))
        else:
            member = next((m for m in front
                           if InterventionGenome.from_dict(m["genome"]).genome_id == genome_id),
                          None)
            if member is None:
                raise ValueError(f"genome_id {genome_id} not on the frozen front")
        genome = InterventionGenome.from_dict(member["genome"])
        return cls("cea-v1", genome=genome,
                   provenance={"pareto_front_path": str(pareto_front_path),
                               "pareto_front_sha256": source_sha,
                               "genome_id": genome.genome_id,
                               "train_fitness": member["train_fitness"],
                               "front_size": len(front)})

    # frozen selection rule (P4-R1.2-S4): failure-conditioned genome choice.
    # Recorded at build time; never tuned on evaluation results.
    def select_genome(self, *, failure_kind: str, edited: bool,
                      invalid: bool) -> dict[str, Any]:
        """Failure-conditioned deployment: pick the front member whose active
        genes match the observable failure evidence. Frozen rule — changing it
        requires a new adapter version."""
        if self.mode != "cea-v1":
            raise RuntimeError("select_genome is only valid for cea-v1 mode")
        front = self._front_members()
        infra = failure_kind in ("unknown_cost", "budget_stop", "transport", "protocol")
        if infra:
            return {"genome": None, "reason": f"infra failure {failure_kind}: no retry",
                    "adapter_version": ADAPTER_VERSION}
        def _has(gene):
            out = []
            for m in front:
                g = InterventionGenome.from_dict(m["genome"])
                if g.as_dict().get(gene, 0) > 0:
                    out.append((g, m))
            return out
        if invalid and _has("verification_level"):
            g, m = _has("verification_level")[0]
            return {"genome": g, "reason": "invalid -> verification-heavy genome",
                    "genome_id": g.genome_id, "train_fitness": m["train_fitness"],
                    "adapter_version": ADAPTER_VERSION}
        if not edited and _has("read_before_write"):
            g, m = _has("read_before_write")[0]
            return {"genome": g, "reason": "no-edit -> read-first genome",
                    "genome_id": g.genome_id, "train_fitness": m["train_fitness"],
                    "adapter_version": ADAPTER_VERSION}
        if _has("tool_validation"):
            g, m = _has("tool_validation")[0]
            return {"genome": g, "reason": "default -> tool-validation genome",
                    "genome_id": g.genome_id, "train_fitness": m["train_fitness"],
                    "adapter_version": ADAPTER_VERSION}
        return {"genome": self.genome, "reason": "fallback: deployed default genome",
                "genome_id": self.genome.genome_id, "adapter_version": ADAPTER_VERSION}

    def _front_members(self) -> list[dict[str, Any]]:
        path = Path(self.provenance["pareto_front_path"])
        front = json.loads(path.read_text(encoding="utf-8"))
        # re-verify the source hash on every read (frozen artifact integrity)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != self.provenance["pareto_front_sha256"]:
            raise ValueError("pareto_front.json hash changed since adapter load")
        return front

    def intervention_for(self, *, failure_kind: str, edited: bool,
                         invalid: bool,
                         genome: InterventionGenome | None = None) -> dict[str, Any]:
        """cea-v1: map observable failure evidence through a frozen genome
        (explicit override from select_genome, else the deployed default).

        Infra failures (unknown_cost/budget_stop/transport/protocol) never get
        a behavioral intervention — they escalate, per the fail-closed rules.
        """
        if self.mode != "cea-v1" or self.genome is None:
            raise RuntimeError("intervention_for() is only valid for cea-v1 mode")
        from ..eval.live_pilot import INTERVENTION_TEXT

        if failure_kind in ("unknown_cost", "budget_stop", "transport", "protocol"):
            return {"text": None, "reason": f"infra failure {failure_kind}: escalate, no retry",
                    "genome_id": None, "adapter_version": ADAPTER_VERSION}
        g = genome or self.genome
        active = {k: v for k, v in g.as_dict().items() if v > 0}
        texts = []
        for gene in active:
            key = _GENE_TO_TEXT_KEY.get(gene)
            if key and key in INTERVENTION_TEXT:
                texts.append(INTERVENTION_TEXT[key])
        return {
            "text": " ".join(texts) if texts else None,
            "reason": (f"genome {g.genome_id} active genes {sorted(active)}"
                       if texts else "genome has no executable genes (no-op)"),
            "genome_id": g.genome_id,
            "adapter_version": ADAPTER_VERSION,
            "provenance": self.provenance,
        }
