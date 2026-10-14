"""Failure representation schema (P2.1-S1). The single source of truth shared
by docs/PHASE2_FAILURE_SCHEMA.md. No chain-of-thought is ever evidence:
evidence items point at observable trace facts only."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class FailureCategory(str, Enum):
    PLANNING = "planning_failure"        # decomposition/order/missing verification step
    TOOL = "tool_failure"                # wrong tool / bad args / bad path / API misuse
    KNOWLEDGE = "knowledge_failure"      # missing info / wrong assumption
    EXECUTION = "execution_failure"      # environment / timeout / resource limit / provider
    VERIFICATION = "verification_failure"  # changed code without testing / wrong test choice
    STRATEGY = "strategy_failure"        # repeated identical failing approach / no search
    UNKNOWN = "unknown"                  # abstention is a first-class answer


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


TAXONOMY: dict[FailureCategory, dict[str, Any]] = {
    FailureCategory.PLANNING: {
        "examples": ["任务分解错误", "顺序错误", "缺少验证步骤", "未执行任何修改即声称完成"],
        "observable_evidence": "轨迹中零工具调用但宣称完成；动作顺序与任务需求矛盾",
        "hidden_cause_hypothesis": "规划器对任务结构的内部建模错误（不可直接观测，仅作假设）",
    },
    FailureCategory.TOOL: {
        "examples": ["错误工具调用", "参数错误", "文件路径错误", "API 使用错误"],
        "observable_evidence": "tool/result 以 Error 开头（unknown tool / not found / access denied）",
        "hidden_cause_hypothesis": "对工具 schema 或环境布局的错误内部模型",
    },
    FailureCategory.KNOWLEDGE: {
        "examples": ["缺少必要信息", "错误假设"],
        "observable_evidence": "编辑已发生且工具无错误，但 judge 测试失败指向错误逻辑",
        "hidden_cause_hypothesis": "对正确修复内容的知识缺口",
    },
    FailureCategory.EXECUTION: {
        "examples": ["环境问题", "超时", "资源限制", "provider 故障"],
        "observable_evidence": "timeout 状态、provider_error、unknown_cost、预算墙钟耗尽",
        "hidden_cause_hypothesis": "基础设施而非模型决策问题（须与模型失败区分）",
    },
    FailureCategory.VERIFICATION: {
        "examples": ["修改完成但没有测试", "测试选择错误"],
        "observable_evidence": "编辑发生 + judge invalid（语法错误），或编辑后无任何验证型动作",
        "hidden_cause_hypothesis": "缺少自我验证习惯（在本 profile 无 shell 时部分为结构性）",
    },
    FailureCategory.STRATEGY: {
        "examples": ["反复尝试同一种失败方案", "无有效搜索"],
        "observable_evidence": "同一工具同一形态调用反复出现直至预算耗尽",
        "hidden_cause_hypothesis": "探索策略坍塌为单一动作",
    },
    FailureCategory.UNKNOWN: {
        "examples": ["证据不足"],
        "observable_evidence": "现有轨迹无法区分多个候选类别",
        "hidden_cause_hypothesis": "未知；不允许强行分类",
    },
}


@dataclass(slots=True)
class EvidenceItem:
    """One observable fact supporting an attribution. `ref` points at a trace
    location (event seq / ledger field / judge field), never at CoT text."""
    kind: str          # tool_error | timeout | budget | no_tool_use | judge_invalid | judge_fail | repeat_pattern | provider_error | state
    ref: str           # e.g. "events_slim#seq=12" or "ledger.tool_attempts"
    detail: str        # short, redacted (no content bodies)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FailureReport:
    """Analyzer output (S2): one trace -> one attribution with abstention."""
    task_id: str
    run_id: str
    outcome: str                  # success | failed | invalid | timeout | budget_stop
    failure_type: str             # FailureCategory value
    evidence: list[EvidenceItem]
    confidence: str               # Confidence value
    causal_scope: str             # what the attribution can and cannot claim
    repair_direction: str         # hypothesis-level direction, not an applied fix

    def validate(self) -> None:
        if self.failure_type not in {c.value for c in FailureCategory}:
            raise ValueError(f"unknown failure_type {self.failure_type!r}")
        if self.confidence not in {c.value for c in Confidence}:
            raise ValueError(f"unknown confidence {self.confidence!r}")
        if self.outcome == "success" and self.failure_type != FailureCategory.UNKNOWN.value:
            raise ValueError("successful tasks carry no failure_type")
        if self.outcome != "success" and self.failure_type == FailureCategory.UNKNOWN.value \
                and not self.evidence:
            raise ValueError("abstention still requires evidence of insufficiency")

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FailureReport":
        rep = cls(
            task_id=d["task_id"], run_id=d["run_id"], outcome=d["outcome"],
            failure_type=d["failure_type"],
            evidence=[EvidenceItem(**e) for e in d["evidence"]],
            confidence=d["confidence"], causal_scope=d["causal_scope"],
            repair_direction=d["repair_direction"],
        )
        rep.validate()
        return rep


@dataclass(slots=True)
class CounterfactualCase:
    """P2.1-S6: structure only. No replay is executed in this phase."""
    original_trace: dict[str, Any]
    failure_label: str
    candidate_intervention: dict[str, Any]
    replay_config: dict[str, Any]

    def validate(self) -> None:
        if self.failure_label not in {c.value for c in FailureCategory}:
            raise ValueError(f"unknown failure_label {self.failure_label!r}")
        for k in ("kind", "description"):
            if k not in self.candidate_intervention:
                raise ValueError(f"candidate_intervention missing {k!r}")
        for k in ("seed", "budget_policy"):
            if k not in self.replay_config:
                raise ValueError(f"replay_config missing {k!r}")

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "CounterfactualCase":
        case = cls(**json.loads(text))
        case.validate()
        return case
