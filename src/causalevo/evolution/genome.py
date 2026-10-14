"""Intervention genome (P3.2-S1). A genome encodes an agent adaptation policy
as a fixed gene vector; its phenotype is the ordered tape-transform pipeline
it induces (see phenotype_transforms). Deterministic, serializable,
mutable, crossoverable, with a Hamming-style distance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

# (name, max_value) — inclusive ranges; 0 means "off".
GENES: tuple[tuple[str, int], ...] = (
    ("tool_validation", 1),     # replace unknown tool with mandatory read
    ("read_before_write", 1),   # prepend read step
    ("verification_level", 2),  # 0 none, 1 read-back+fix, 2 same (reserved strength)
    ("stagnation_break", 1),    # break same-tool spam loops
    ("reflection_step", 1),     # reserved semantic gene (no tape effect v1)
    ("retry_strategy", 2),      # 0 none, 1 single retry, 2 double (reserved)
)
GENE_NAMES = [g[0] for g in GENES]


@dataclass(frozen=True, slots=True)
class InterventionGenome:
    genes: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.genes) != len(GENES):
            raise ValueError(f"genome must have {len(GENES)} genes")
        for (name, hi), v in zip(GENES, self.genes):
            if not isinstance(v, int) or not 0 <= v <= hi:
                raise ValueError(f"gene {name}={v} out of range [0,{hi}]")

    @property
    def genome_id(self) -> str:
        return hashlib.sha256(json.dumps(self.genes).encode()).hexdigest()[:12]

    def as_dict(self) -> dict[str, int]:
        return dict(zip(GENE_NAMES, self.genes))

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "InterventionGenome":
        return cls(tuple(int(d[name]) for name in GENE_NAMES))

    @classmethod
    def from_json(cls, text: str) -> "InterventionGenome":
        return cls.from_dict(json.loads(text))

    @classmethod
    def random(cls, rng: np.random.Generator) -> "InterventionGenome":
        return cls(tuple(int(rng.integers(hi + 1)) for _name, hi in GENES))

    def mutate(self, rng: np.random.Generator, p: float = 0.2) -> "InterventionGenome":
        """Per-gene: with prob p, resample uniformly within range."""
        genes = list(self.genes)
        for i, (_name, hi) in enumerate(GENES):
            if rng.random() < p:
                genes[i] = int(rng.integers(hi + 1))
        return InterventionGenome(tuple(genes))

    def crossover(self, other: "InterventionGenome", rng: np.random.Generator) -> "InterventionGenome":
        """Uniform per-gene crossover."""
        genes = tuple(
            g if rng.random() < 0.5 else o for g, o in zip(self.genes, other.genes))
        return InterventionGenome(genes)

    def distance(self, other: "InterventionGenome") -> float:
        """Normalized per-gene mismatch (Hamming / range)."""
        return float(sum(
            abs(g - o) / max(1, hi)
            for (g, o, (_n, hi)) in zip(self.genes, other.genes, GENES)
        ) / len(GENES))

    def phenotype_transforms(self) -> list[str]:
        """Ordered tape transforms this genome induces (deterministic mapping)."""
        out: list[str] = []
        if self.as_dict()["tool_validation"]:
            out.append("replace_unknown_tool_with_read")
        if self.as_dict()["read_before_write"]:
            out.append("prepend_read_step")
        if self.as_dict()["stagnation_break"]:
            out.append("break_repeat_with_read")
        if self.as_dict()["verification_level"] >= 1:
            out.append("append_readback_and_fix")
        return out or ["identity"]
