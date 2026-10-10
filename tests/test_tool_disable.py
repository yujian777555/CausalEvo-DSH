"""Tool-disable regression guard: the bench patch must keep every known
dangerous plugin disabled. Structural evidence that the composed runtime
actually boots without tools is produced by the live smoke run (see
docs/PHASE0_RESULTS.md); this test guards the patch file itself."""

import re
from pathlib import Path

PATCH = Path(__file__).resolve().parents[1] / "configs" / "dsh_bench_patch.yml"

# Plugin ids observed enabled in the stock `sdk` profile (dump 2026-10-10,
# runtime 0.1.5-rc.1) that must stay disabled for the benchmark.
DANGEROUS_IDS = [
    "tool-pwsh", "tool-bash", "tool-jobs", "pwsh-sandbox", "bash-sandbox",
    "sandbox", "sandbox-policy", "subprocess",
    "tool-fs", "tool-fs-search", "fs-sandbox", "fs-observation-policy",
    "attachment-local", "agent-instructions",
    "tool-web", "web", "web-search-deepseek", "web-fetch-http",
    "skill", "skill-filesystem", "tool-skill",
    "commands", "command-feedback", "command-compact",
    "goal", "goal-round-driver", "command-goal", "tool-goal",
    "plan-mode", "tool-todo", "tool-ralph",
    "subagent", "subagent-spawn-in-process", "subagent-fork-in-process",
    "tool-subagent-control", "tool-subagent-list-agents", "tool-subagent",
    "tool-subagent-fork", "workflow-worker-thread", "tool-workflow",
    "spill-local", "spill-policy", "tool-result-pruner", "repeat-tool-reminder",
    "user-questions", "compaction-basic", "session-checkpoint-policy",
    "session-title", "session-title-llm", "permission",
    "session-telemetry-otel", "session-log-deepseek",
]


def _disabled_ids() -> set[str]:
    text = PATCH.read_text(encoding="utf-8")
    return set(re.findall(r"^- id: (\S+)\n  disabled: true", text, re.M))


def test_all_dangerous_plugins_disabled():
    disabled = _disabled_ids()
    missing = [pid for pid in DANGEROUS_IDS if pid not in disabled]
    assert not missing, f"patch no longer disables: {missing}"


def test_no_tool_like_id_left_enabled():
    text = PATCH.read_text(encoding="utf-8")
    enabled = set(re.findall(r"^# - id: (\S+)", text, re.M))  # commented-out = kept
    assert enabled <= {"approval", "shell-env", "timeout-policy"}
