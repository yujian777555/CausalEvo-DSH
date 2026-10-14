"""Rule-based intervention generator (P2.3-S2). DiagnosisResult -> CandidateIntervention.

Pure rules, no LLM, no API. Every mapping is explicit and auditable."""

from __future__ import annotations

from ..analysis.schema import FailureCategory
from ..diagnosis.models import DiagnosisResult
from .schema import CandidateIntervention, InterventionType

NO_INTERVENTION = CandidateIntervention(
    intervention_id="no-op",
    target_failure=FailureCategory.UNKNOWN.value,
    intervention_type=InterventionType.NONE.value,
    description="不改任何东西（原始轨迹重放）",
    required_change="none",
    expected_effect="none",
    confidence="high",
    tape_transform="identity",
)

_RULES: dict[str, dict] = {
    "tool_failure": dict(
        intervention_type=InterventionType.TOOL.value,
        description="工具调用前增加名称/参数校验（add_path_validation）",
        required_change="tool-call dispatch 前校验工具名在注册表内且参数通过 schema",
        expected_effect="unknown-tool 类失败被拦截并转为合法 read/write",
        tape_transform="replace_unknown_tool_with_read",
    ),
    "planning_failure": dict(
        intervention_type=InterventionType.PLANNING.value,
        description="任务分解前置步骤（add_task_decomposition_step）",
        required_change="首轮前先输出 定位→修改→验证 计划再动作",
        expected_effect="零行动即结束被消除",
        tape_transform="prepend_read_step",
    ),
    "verification_failure": dict(
        intervention_type=InterventionType.VERIFICATION.value,
        description="完成前强制自测（force_test_before_finish）",
        required_change="写入后必须 read-back 并继续修正循环直至结束条件",
        expected_effect="语法错误/明显错误修改在结束前被捕获",
        tape_transform="append_readback_and_fix",
    ),
    "strategy_failure": dict(
        intervention_type=InterventionType.STRATEGY.value,
        description="停滞检测后切换搜索策略（change_search_strategy）",
        required_change="同一工具重复 N 次后强制切换动作类型",
        expected_effect="重复循环在阈值处被打断",
        tape_transform="break_repeat_with_read",
    ),
    "knowledge_failure": dict(
        intervention_type=InterventionType.KNOWLEDGE.value,
        description="补充错误定位上下文（add_error_context）",
        required_change="向 agent 追加失败测试定位信息",
        expected_effect="错误修复内容被替换为正确内容",
        tape_transform="inject_fix_after_write",
    ),
    "execution_failure": dict(
        intervention_type=InterventionType.TOOL.value,
        description="基础设施修复后重跑（fix_infra_retry）",
        required_change="provider/预算/超时修复后重放",
        expected_effect="环境故障消除；非模型失败",
        tape_transform="identity",
        confidence_default="low",
    ),
    "unknown": dict(
        intervention_type=InterventionType.NONE.value,
        description="证据不足：先收集更多证据",
        required_change="none",
        expected_effect="unknown",
        tape_transform="identity",
        confidence_default="low",
    ),
}


def generate_intervention(result: DiagnosisResult) -> CandidateIntervention:
    """Rule table mapping; abstaining diagnoses get the no-op intervention."""
    spec = _RULES.get(result.failure_type, _RULES["unknown"])
    confidence = spec.get("confidence_default", "medium")
    return CandidateIntervention(
        intervention_id=f"rule:{result.failure_type}",
        target_failure=result.failure_type,
        intervention_type=spec["intervention_type"],
        description=spec["description"],
        required_change=spec["required_change"],
        expected_effect=spec["expected_effect"],
        confidence=confidence,
        tape_transform=spec["tape_transform"],
    )


# Full intervention library (for the random baseline; seeded choice).
INTERVENTION_LIBRARY: list[CandidateIntervention] = [
    CandidateIntervention(
        intervention_id=f"lib:{key}",
        target_failure=key,
        intervention_type=spec["intervention_type"],
        description=spec["description"],
        required_change=spec["required_change"],
        expected_effect=spec["expected_effect"],
        confidence=spec.get("confidence_default", "medium"),
        tape_transform=spec["tape_transform"],
    )
    for key, spec in _RULES.items()
]
