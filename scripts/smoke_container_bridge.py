"""Scratch: container bridge smoke — fake provider scripts read->write->final;
assert the mounted workspace gets edited and usage/events flow back."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from causalevo.eval.fake_provider import FakeProvider
from causalevo.eval.harness_agent import ContainerHarnessRunner
from causalevo.eval.runtime_budget import RuntimeBudget
from causalevo.eval.task_spec import load_task

REPO = pathlib.Path(__file__).resolve().parents[1]
FIXED = "def clamp_value(x, lo, hi):\n    return min(max(x, lo), hi)\n"


def script(messages, call_index):
    if call_index == 0:
        return [("tool_call", "read", {"file_path": "solution.py"})]
    if call_index == 1:
        return [("tool_call", "write", {"file_path": "solution.py", "content": FIXED})]
    return [("text", "fixed it")]


ws = REPO / "results" / "phase1" / "r2-scratch" / "ws-container"
ws.mkdir(parents=True, exist_ok=True)
(ws / "solution.py").write_text("def clamp_value(x, lo, hi):\n    return min(max(x, hi), lo)\n",
                                encoding="utf-8")

spec = load_task(REPO / "benchmarks" / "tasks" / "micro-000-clamp_value")

with FakeProvider(script) as provider:
    # container reaches the host server via host.docker.internal
    host_url = provider.base_url.replace("127.0.0.1", "host.docker.internal")
    runner = ContainerHarnessRunner(
        image="causalevo-dsh-agent:0.1.0",
        patch_path=REPO / "configs" / "dsh_task_patch.yml",
        model="deepseek-flash", reasoning_effort="low", max_tokens=256,
        host_base_url=host_url,
    )
    budget = RuntimeBudget(max_provider_calls=4, max_total_output_tokens=2048,
                           max_tool_calls=10, wall_time_s=300)
    outcome = runner.run_task(spec, ws, "B0-fixed-harness", budget,
                              api_key="sk-fake-offline-no-cost")

print("finish_reason:", outcome.finish_reason)
print("failure_kind:", outcome.failure_kind, outcome.budget_stop_reason)
print("usage:", outcome.usage.as_dict() if outcome.usage else None)
print("ledger:", outcome.ledger)
print("provider requests:", provider.call_count)
print("workspace after:", (ws / "solution.py").read_text(encoding="utf-8")[:70].replace("\n", " | "))
print("edit applied:", (ws / "solution.py").read_text(encoding="utf-8") == FIXED)
print("event types:", sorted({e["type"] for e in outcome.events_slim}))
