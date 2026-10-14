"""Failure dataset builder (P2.1-S3).

Scans committed offline run artifacts (results/phase1/**/traces.jsonl),
analyzes every trace with the rule-based analyzer, and writes
failure_records.jsonl. Nothing is invented: records exist only for traces that
actually exist; scenario labels (injected faults) are recorded as ground truth
where the run config declares them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..analysis.schema import FailureCategory
from ..analysis.trace_analyzer import analyze_trace

# Scenario -> injected ground-truth failure category (by construction).
SCENARIO_GROUND_TRUTH = {
    "bad_tool_call": FailureCategory.TOOL.value,
    "tool_over_budget": FailureCategory.STRATEGY.value,
    "provider_error": FailureCategory.EXECUTION.value,
    "wrong_fix": FailureCategory.KNOWLEDGE.value,
    "noop": FailureCategory.PLANNING.value,
    "provider_timeout": FailureCategory.EXECUTION.value,
}

REPAIR_HINTS = {
    FailureCategory.PLANNING.value: "强制 定位→修改→验证 步骤结构",
    FailureCategory.TOOL.value: "工具调用前 schema 校验",
    FailureCategory.KNOWLEDGE.value: "提供错误定位上下文",
    FailureCategory.EXECUTION.value: "修复基础设施后重跑；不计入模型失败",
    FailureCategory.VERIFICATION.value: "编辑后自我验证再结束",
    FailureCategory.STRATEGY.value: "停滞检测 + 动作多样性",
    FailureCategory.UNKNOWN.value: "保持 unknown",
}


def iter_traces(results_root: Path):
    """Yield (trace_dict, source_run, provider_kind, scenario_label|None)."""
    for traces_path in sorted(results_root.rglob("traces.jsonl")):
        run_dir = traces_path.parent
        manifest_path = run_dir / "manifest.json"
        scenario = None
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            scenario = (manifest.get("config") or {}).get("scenario")
        for line in traces_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                trace = json.loads(line)
                yield trace, run_dir.name, trace.get("provider_kind", "none"), scenario


def build_records(results_root: Path) -> list[dict[str, Any]]:
    records = []
    for trace, source_run, provider_kind, scenario in iter_traces(results_root):
        report = analyze_trace(trace)
        record = {
            "trace_id": trace.get("trace_id"),
            "task_id": trace.get("task_id"),
            "failure_category": report.failure_type,
            "outcome": report.outcome,
            "evidence": [e.as_dict() for e in report.evidence],
            "confidence": report.confidence,
            "repair_hint": REPAIR_HINTS.get(report.failure_type, ""),
            "source_run": source_run,
            "provider_kind": provider_kind,
            "ground_truth": scenario and SCENARIO_GROUND_TRUTH.get(scenario),
        }
        records.append(record)
    return records


def stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_cat: dict[str, int] = {}
    by_conf: dict[str, int] = {}
    by_truth_match = {"matched": 0, "mismatched": 0, "unlabeled": 0}
    for r in records:
        by_cat[r["failure_category"]] = by_cat.get(r["failure_category"], 0) + 1
        by_conf[r["confidence"]] = by_conf.get(r["confidence"], 0) + 1
        gt = r.get("ground_truth")
        if gt is None:
            by_truth_match["unlabeled"] += 1
        elif gt == r["failure_category"]:
            by_truth_match["matched"] += 1
        else:
            by_truth_match["mismatched"] += 1
    return {
        "total_records": len(records),
        "by_category": by_cat,
        "by_confidence": by_conf,
        "ground_truth_agreement": by_truth_match,
    }
