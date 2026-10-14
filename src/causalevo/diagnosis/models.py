"""Diagnosis models (P2.2-S3/S4/S5).

B0: rule chain (Phase 2.1, frozen) — wrapped for a uniform interface.
B1: LogisticRegression over FailureFeature (numeric + categorical, DictVectorizer).
B2: hashing-embedding over a text rendering of the slim event graph +
    LogisticRegression. Fully offline (no pretrained download needed or used).

All models support abstention: max class probability below the threshold ->
"unknown". Evidence for ML models = top-|coef| input features mapped back to
trace refs; evidence for B0 = its rule evidence.
"""

from __future__ import annotations

import json
import pickle
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction import DictVectorizer, FeatureHasher
from sklearn.linear_model import LogisticRegression

from ..analysis.trace_analyzer import analyze_trace
from .features import CATEGORICAL_COLUMNS, FEATURE_COLUMNS

UNKNOWN = "unknown"

_FEATURE_REF = {
    "tool_calls": "agent.ledger.tool_attempts",
    "provider_calls": "agent.ledger.provider_attempts",
    "repeat_max_run": "agent.events_slim.tool_call_seq",
    "failed_action_ratio": "agent.events_slim.tool_call",
    "budget_stop": "states.budget_stop",
    "judge_invalid": "judge.invalid_reason",
    "visible_passed": "states.visible_tests_passed",
    "sealed_passed": "states.sealed_tests_passed",
    "n_unknown_spend": "agent.ledger.unknown_spend_attempts",
    "failure_kind": "agent.failure_kind",
    "edited_workspace": "workspace_digest_before!=after",
    "events_count": "agent.events_slim",
    "task_prompt_chars": "task.instructions",
    "n_visible_checks": "task.visible_checks",
    "action_diversity": "agent.events_slim.tool_call",
}


@dataclass(slots=True)
class DiagnosisResult:
    trace_id: str
    failure_type: str
    evidence: list[str]          # trace refs, not content
    confidence: float            # model probability or rule-confidence mapping
    abstained: bool
    model: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CandidateIntervention:
    """P2.2-S7: interface only. No intervention is executed or validated."""
    failure_type: str
    intervention_kind: str
    description: str
    target_component: str        # prompt | tool_policy | workflow | budget

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "CandidateIntervention":
        return cls(**json.loads(text))


def to_candidate_intervention(result: DiagnosisResult) -> CandidateIntervention:
    table = {
        "tool_failure": ("add_tool_validation", "校验工具名与参数后再调用", "tool_policy"),
        "planning_failure": ("enforce_plan_steps", "强制 定位→修改→验证 步骤", "workflow"),
        "knowledge_failure": ("add_error_context", "向 agent 提供失败测试定位", "prompt"),
        "execution_failure": ("fix_infra_retry", "修基础设施后重跑", "budget"),
        "verification_failure": ("require_self_test", "编辑后自测再结束", "workflow"),
        "strategy_failure": ("stagnation_detection", "停滞检测并强制换策略", "workflow"),
        "unknown": ("collect_more_evidence", "收集更多证据", "budget"),
    }
    kind, desc, target = table[result.failure_type]
    return CandidateIntervention(result.failure_type, kind, desc, target)


class RuleDiagnoser:
    name = "B0-rules"

    def diagnose(self, trace: dict[str, Any]) -> DiagnosisResult:
        rep = analyze_trace(trace)
        conf = {"high": 0.9, "medium": 0.6, "low": 0.3}[rep.confidence]
        return DiagnosisResult(
            trace_id=trace.get("trace_id", "?"),
            failure_type=rep.failure_type,
            evidence=[e.ref for e in rep.evidence],
            confidence=conf,
            abstained=rep.failure_type == UNKNOWN,
            model=self.name,
        )


def _rows_to_dicts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        f = r["features"]
        d: dict[str, Any] = {k: f[k] for k in FEATURE_COLUMNS}
        for k in CATEGORICAL_COLUMNS:
            d[f"{k}={f[k]}"] = 1
        out.append(d)
    return out


def _ref_resolves(trace: dict[str, Any], ref: str) -> bool:
    """True only if the dotted ref resolves to a non-null value in the trace."""
    node: Any = trace
    for part in ref.replace("[", ".").rstrip("]").split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return node is not None


class FeatureLRDiagnoser:
    """B1: DictVectorizer + LogisticRegression over FailureFeature."""

    name = "B1-feature-lr"

    def __init__(self, abstain_threshold: float = 0.5) -> None:
        self.abstain_threshold = abstain_threshold
        self.vectorizer = DictVectorizer(sparse=False)
        self.model = LogisticRegression(max_iter=2000)
        self.classes_: list[str] = []
        self._fitted = False

    def fit(self, rows: list[dict[str, Any]]) -> None:
        labeled = [r for r in rows if r["label"]]
        if not labeled:
            raise ValueError("no labeled rows to fit")
        X = self.vectorizer.fit_transform(_rows_to_dicts(labeled))
        y = [r["label"] for r in labeled]
        self.model.fit(X, y)
        self.classes_ = list(self.model.classes_)
        self._fitted = True

    def _predict_proba(self, row: dict[str, Any]) -> np.ndarray:
        X = self.vectorizer.transform(_rows_to_dicts([row]))
        return self.model.predict_proba(X)[0]

    def diagnose_row(self, row: dict[str, Any], trace: dict[str, Any] | None = None) -> DiagnosisResult:
        if not self._fitted:
            raise RuntimeError("not fitted")
        proba = self._predict_proba(row)
        best = int(np.argmax(proba))
        conf = float(proba[best])
        abstained = conf < self.abstain_threshold
        ftype = UNKNOWN if abstained else self.classes_[best]
        # evidence: top-|coef| features. Each entry is a "feature:<name>=<value>"
        # pair (verifiable against row['features']); when the source trace is
        # supplied, entries whose trace ref does not resolve are dropped, so
        # emitted evidence only ever points at data that actually exists.
        coef = self.model.coef_[best]
        names = self.vectorizer.get_feature_names_out()
        top = np.argsort(-np.abs(coef))[:5]
        evidence: list[str] = []
        for i in top:
            feat_name = names[i].split("=")[0]
            value = row["features"].get(feat_name)
            entry = f"feature:{feat_name}={value}"
            ref = _FEATURE_REF.get(feat_name)
            # keep the verifiable feature entry; drop only an unresolvable @ref
            if ref is not None and trace is not None and not _ref_resolves(trace, ref):
                ref = None
            evidence.append(entry + (f" @{ref}" if ref else ""))
        return DiagnosisResult(
            trace_id=row["trace_id"], failure_type=ftype, evidence=evidence,
            confidence=conf, abstained=abstained, model=self.name,
        )

    def save(self, path: Path) -> None:
        path.write_bytes(pickle.dumps({
            "vectorizer": self.vectorizer, "model": self.model,
            "classes": self.classes_, "threshold": self.abstain_threshold,
        }))

    @classmethod
    def load(cls, path: Path) -> "FeatureLRDiagnoser":
        blob = pickle.loads(path.read_bytes())
        obj = cls(abstain_threshold=blob["threshold"])
        obj.vectorizer = blob["vectorizer"]
        obj.model = blob["model"]
        obj.classes_ = blob["classes"]
        obj._fitted = True
        return obj


def trace_to_text(trace: dict[str, Any]) -> str:
    """Text rendering of the slim event graph (structure only, no bodies)."""
    agent = trace.get("agent", {}) or {}
    judge = trace.get("judge", {}) or {}
    parts = [f"failure_kind:{agent.get('failure_kind', 'none')}",
             f"finish:{agent.get('finish_reason')}",
             f"visible:{judge.get('visible_passed')}", f"sealed:{judge.get('sealed_passed')}"]
    for e in agent.get("events_slim", []) or []:
        parts.append(str(e.get("type")))
        if e.get("tool"):
            parts.append(f"tool:{e['tool']}")
    return " ".join(parts)


class EmbeddingDiagnoser:
    """B2: hashing-embedding of the slim trace text + LogisticRegression.
    Offline by construction (HashingVectorizer needs no download)."""

    name = "B2-embedding-lr"

    def __init__(self, abstain_threshold: float = 0.5, n_features: int = 1024) -> None:
        self.abstain_threshold = abstain_threshold
        self.hasher = FeatureHasher(n_features=n_features, input_type="string")
        self.model = LogisticRegression(max_iter=2000)
        self.classes_: list[str] = []
        self._fitted = False
        self._traces: dict[str, dict[str, Any]] = {}

    def _tokens(self, trace: dict[str, Any]) -> list[str]:
        return trace_to_text(trace).split()

    def fit(self, rows: list[dict[str, Any]], traces_by_id: dict[str, dict[str, Any]]) -> None:
        labeled = [r for r in rows if r["label"] and r["trace_id"] in traces_by_id]
        if not labeled:
            raise ValueError("no labeled rows to fit")
        self._traces = traces_by_id
        X = self.hasher.transform([self._tokens(traces_by_id[r["trace_id"]]) for r in labeled])
        self.model.fit(X, [r["label"] for r in labeled])
        self.classes_ = list(self.model.classes_)
        self._fitted = True

    def diagnose(self, trace: dict[str, Any]) -> DiagnosisResult:
        if not self._fitted:
            raise RuntimeError("not fitted")
        X = self.hasher.transform([self._tokens(trace)])
        proba = self.model.predict_proba(X)[0]
        best = int(np.argmax(proba))
        conf = float(proba[best])
        abstained = conf < self.abstain_threshold
        ftype = UNKNOWN if abstained else self.classes_[best]
        evidence = ["agent.events_slim(text-hash)", "agent.failure_kind"]
        return DiagnosisResult(
            trace_id=trace.get("trace_id", "?"), failure_type=ftype,
            evidence=evidence, confidence=conf, abstained=abstained, model=self.name,
        )
