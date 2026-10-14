"""Trajectory analyzer (P2.1-S2): TaskTrace -> FailureReport.

Uses ONLY agent-observable trajectory data (slim event graph, ledger) plus the
judge outcome. Never reads sealed test content, never uses chain-of-thought.
Rule order matters: infrastructure/execution problems are checked first so a
provider outage is never mislabeled as a model failure.
"""

from __future__ import annotations

from typing import Any

from .schema import Confidence, EvidenceItem, FailureCategory, FailureReport

# Tool names the task profile exposes; anything else the model calls is an
# unknown-tool error (Tool Failure evidence).
KNOWN_TOOLS = {"read", "write", "edit", "glob", "grep"}


def _outcome(states: dict[str, bool]) -> str:
    if states.get("timeout"):
        return "timeout"
    if states.get("budget_stop"):
        return "budget_stop"
    if states.get("invalid"):
        return "invalid"
    if states.get("visible_tests_passed") and states.get("sealed_tests_passed"):
        return "success"
    return "failed"


def _tool_call_names(events: list[dict[str, Any]]) -> list[str]:
    return [e.get("tool") for e in events if e.get("type") == "tool/call" and e.get("tool")]


def _repeated_identical_calls(names: list[str]) -> bool:
    """Same tool called 3+ times in a row (the observable part of 'strategy
    collapse' available in the slim event graph)."""
    run = 1
    for i in range(1, len(names)):
        if names[i] == names[i - 1]:
            run += 1
            if run >= 3:
                return True
        else:
            run = 1
    return False


def analyze_trace(trace: dict[str, Any]) -> FailureReport:
    states = trace.get("states", {})
    agent = trace.get("agent", {}) or {}
    judge = trace.get("judge", {}) or {}
    ledger = agent.get("ledger", {}) or {}
    events = agent.get("events_slim", []) or []
    outcome = _outcome(states)
    task_id = trace.get("task_id", "?")
    run_id = trace.get("run_id", "?")

    evidence: list[EvidenceItem] = []
    failure = FailureCategory.UNKNOWN
    confidence = Confidence.LOW
    causal_scope = "agent-observable trajectory + judge outcome only; no CoT, no sealed content"
    repair = "insufficient evidence"

    if outcome == "success":
        return FailureReport(task_id=task_id, run_id=run_id, outcome="success",
                             failure_type=FailureCategory.UNKNOWN.value, evidence=[],
                             confidence=Confidence.HIGH.value, causal_scope=causal_scope,
                             repair_direction="none (task succeeded)")

    # 1. Infrastructure first: provider/transport/unknown-cost are NOT model failures.
    failure_kind = agent.get("failure_kind")
    if failure_kind in ("provider_error", "transport", "unknown_cost", "protocol"):
        evidence.append(EvidenceItem("provider_error", "agent.failure_kind", failure_kind))
        if ledger.get("unknown_spend_attempts"):
            evidence.append(EvidenceItem("state", "agent.ledger.unknown_spend_attempts",
                                         str(ledger["unknown_spend_attempts"])))
        failure = FailureCategory.EXECUTION
        confidence = Confidence.HIGH
        repair = "修复基础设施/计费路径后重跑；不计入模型失败"

    elif states.get("timeout"):
        evidence.append(EvidenceItem("timeout", "states.timeout", "true"))
        failure = FailureCategory.EXECUTION
        confidence = Confidence.HIGH
        repair = "提高 wall-clock 预算或减小任务范围（两臂同步）"

    # 2. Budget stop from tool-call spam -> strategy collapse evidence.
    elif outcome == "budget_stop":
        reason = agent.get("budget_stop_reason") or ""
        evidence.append(EvidenceItem("budget", "agent.budget_stop_reason", reason[:80]))
        names = _tool_call_names(events)
        if "tool_calls" in reason and _repeated_identical_calls(names):
            evidence.append(EvidenceItem("repeat_pattern", "agent.events_slim.tool_call_seq",
                                         f"same tool repeated: {names[:6]}"))
            failure = FailureCategory.STRATEGY
            confidence = Confidence.MEDIUM
            repair = "引入动作多样性/停滞检测"
        else:
            failure = FailureCategory.EXECUTION
            confidence = Confidence.MEDIUM
            repair = "预算包络复查（两臂同步）"

    # 3. Tool-layer errors (unknown tool / bad path / sandbox denial).
    elif judge.get("invalid_reason"):
        evidence.append(EvidenceItem("judge_invalid", "judge.invalid_reason",
                                     str(judge["invalid_reason"])[:80]))
        if agent.get("tool_executed") or ledger.get("tool_attempts"):
            failure = FailureCategory.VERIFICATION
            confidence = Confidence.MEDIUM
            repair = "编辑后自我验证（import/语法）再结束"
        else:
            failure = FailureCategory.EXECUTION
            confidence = Confidence.LOW
            repair = "证据不足：invalid 但无编辑记录"
    else:
        names = _tool_call_names(events)
        # slim events carry no tool-result text (redacted by construction);
        # unknown-tool calls are visible via tool/call names outside KNOWN_TOOLS
        bad_name = [n for n in names if n not in KNOWN_TOOLS]
        if bad_name:
            evidence.append(EvidenceItem("tool_error", "agent.events_slim.tool_call",
                                         f"unknown tool name(s): {sorted(set(bad_name))}"))
            failure = FailureCategory.TOOL
            confidence = Confidence.HIGH
            repair = "工具名/参数 schema 校验前置"
        elif not names and not ledger.get("tool_attempts") and not states.get("tool_executed"):
            # Agent finished without any tool use: no edit attempted.
            evidence.append(EvidenceItem("no_tool_use", "agent.ledger.tool_attempts", "0"))
            evidence.append(EvidenceItem("state", "judge.sealed_passed", "false"))
            failure = FailureCategory.PLANNING
            confidence = Confidence.MEDIUM
            repair = "任务分解应包含定位-修改-验证步骤"
        elif judge.get("visible_passed") is False and (names or ledger.get("tool_attempts")):
            evidence.append(EvidenceItem("judge_fail", "judge.visible_passed", "false"))
            evidence.append(EvidenceItem("state", "agent.ledger.tool_attempts",
                                         str(ledger.get("tool_attempts"))))
            failure = FailureCategory.KNOWLEDGE
            confidence = Confidence.LOW
            repair = "修复内容知识缺口；需要更强的错误定位信息"
        else:
            evidence.append(EvidenceItem("state", "judge", "no decisive observable signal"))
            failure = FailureCategory.UNKNOWN
            confidence = Confidence.LOW
            repair = "保持 unknown；不得强行分类"

    report = FailureReport(
        task_id=task_id, run_id=run_id, outcome=outcome,
        failure_type=failure.value, evidence=evidence, confidence=confidence.value,
        causal_scope=causal_scope, repair_direction=repair,
    )
    report.validate()
    return report
