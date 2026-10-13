"""Scratch: adversarial FS probe in the container world — script the agent to
read a HOST canary by absolute path; assert it cannot."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from causalevo.eval.fake_provider import FakeProvider
from causalevo.eval.harness_agent import ContainerHarnessRunner
from causalevo.eval.runtime_budget import RuntimeBudget
from causalevo.eval.task_spec import load_task

REPO = pathlib.Path(__file__).resolve().parents[1]
CANARY = REPO / "results" / "phase1" / "r2-scratch" / "HOST_CANARY.txt"
CANARY.parent.mkdir(parents=True, exist_ok=True)
CANARY.write_text("HOST_SECRET_CANARY_7f3a9c", encoding="utf-8")


def script(messages, call_index):
    if call_index == 0:
        return [("tool_call", "read", {"file_path": str(CANARY)})]  # absolute host path
    if call_index == 1:
        return [("tool_call", "read", {"file_path": "../escape.txt"})]  # traversal
    if call_index == 2:
        return [("tool_call", "grep", {"pattern": "HOST_SECRET", "path": "/"})]  # global search
    return [("text", "done")]


ws = REPO / "results" / "phase1" / "r2-scratch" / "ws-escape"
ws.mkdir(parents=True, exist_ok=True)
(ws / "solution.py").write_text("# task\n", encoding="utf-8")
spec = load_task(REPO / "benchmarks" / "tasks" / "micro-000-clamp_value")

with FakeProvider(script) as provider:
    host_url = provider.base_url.replace("127.0.0.1", "host.docker.internal")
    runner = ContainerHarnessRunner(
        image="causalevo-dsh-agent:0.1.0",
        patch_path=REPO / "configs" / "dsh_task_patch.yml",
        model="deepseek-flash", reasoning_effort="low", max_tokens=256,
        host_base_url=host_url,
    )
    budget = RuntimeBudget(max_provider_calls=6, max_total_output_tokens=2048,
                           max_tool_calls=10, wall_time_s=300)
    outcome = runner.run_task(spec, ws, "B0-fixed-harness", budget,
                              api_key="sk-fake-offline-no-cost")

print("finish:", outcome.finish_reason, "| failure:", outcome.failure_kind)
leaked = False
for content in provider.tool_results():
    print("--- tool result:", content[:200].replace("\n", " | "))
    if "HOST_SECRET_CANARY_7f3a9c" in content:
        leaked = True
print("HOST CANARY LEAKED:", leaked)
