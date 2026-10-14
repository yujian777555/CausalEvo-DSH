"""LinUCB core (P3.1-S3 B2): disjoint per-action ridge + UCB bonus.

Pure numpy. Deterministic given the update sequence. Serializable to plain
dicts (lists) for auditability."""

from __future__ import annotations

import numpy as np


class LinUCB:
    """Disjoint LinUCB: each action keeps its own (A, b); theta_a = A^-1 b;
    score_a = theta_a . x + alpha * sqrt(x^T A_a^-1 x)."""

    def __init__(self, n_actions: int, dim: int, alpha: float = 1.0,
                 ridge: float = 1.0) -> None:
        if alpha <= 0 or ridge <= 0:
            raise ValueError("alpha and ridge must be positive")
        self.dim = dim
        self.alpha = alpha
        self.ridge = ridge
        self.A = np.stack([np.eye(dim) * ridge for _ in range(n_actions)])
        self.b = np.zeros((n_actions, dim))

    def scores(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=float)
        if x.shape != (self.dim,):
            raise ValueError(f"state dim {x.shape} != {self.dim}")
        out = np.zeros(len(self.A))
        for i in range(len(self.A)):
            a_inv = np.linalg.inv(self.A[i])
            theta = a_inv @ self.b[i]
            bonus = self.alpha * float(np.sqrt(x @ a_inv @ x))
            out[i] = theta @ x + bonus
        return out

    def select(self, x: np.ndarray) -> int:
        return int(np.argmax(self.scores(x)))

    def update(self, action: int, x: np.ndarray, reward: float) -> None:
        x = np.asarray(x, dtype=float)
        self.A[action] += np.outer(x, x)
        self.b[action] += reward * x

    def to_dict(self) -> dict:
        return {"dim": self.dim, "alpha": self.alpha, "ridge": self.ridge,
                "A": self.A.tolist(), "b": self.b.tolist()}

    @classmethod
    def from_dict(cls, d: dict) -> "LinUCB":
        obj = cls(len(d["A"]), d["dim"], d["alpha"], d["ridge"])
        obj.A = np.array(d["A"])
        obj.b = np.array(d["b"])
        return obj
