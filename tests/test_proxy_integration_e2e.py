"""Docker E2E: agent container -> ProxyContainer -> fake provider -> judge
(P4-R1.2-S2). Full chain on the internal network; no external calls."""

import json
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from causalevo.eval.executor import docker_available
from causalevo.eval.harness_agent import ContainerHarnessRunner
from causalevo.eval.judge import Judge
from causalevo.eval.executor import DockerExecutor
from causalevo.eval.networks import ProviderContainer, ProxyContainer
from causalevo.eval.runtime_budget import RuntimeBudget
from causalevo.eval.task_spec import load_task

REPO = Path(__file__).resolve().parents[1]
AGENT_IMAGE = "causalevo-dsh-agent:0.2.1"


def _img(name: str) -> bool:
    return subprocess.run(["docker", "image", "inspect", name],
                          capture_output=True, timeout=15).returncode == 0


pytestmark = pytest.mark.skipif(
    not (docker_available() and _img(AGENT_IMAGE) and _img("python:3.11-slim")),
    reason="docker/images unavailable")


@pytest.fixture
def spec():
    return load_task(REPO / "benchmarks" / "tasks" / "micro-000-clamp_value")


def _budget():
    return RuntimeBudget(max_provider_calls=8, max_total_output_tokens=4096,
                         max_tool_calls=12, wall_time_s=240)


def test_agent_through_proxy_full_chain(tmp_path, spec):
    tape = {"0": [["tool_call", "read", {"file_path": "solution.py"}]],
            "1": [["tool_call", "write", {"file_path": "solution.py",
                                          "content": "def clamp_value(x, lo, hi):\n    return min(max(x, lo), hi)\n"}]],
            "2": [["text", "done"]]}
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "solution.py").write_text("def clamp_value(x, lo, hi):\n    return min(max(x, hi), lo)\n",
                                    encoding="utf-8")
    with ProviderContainer(tape) as upstream, \
            ProxyContainer(upstream=upstream.endpoint, ledger_dir=tmp_path / "ledger") as proxy:
        proxy.set_current_task(spec.task_id)
        runner = ContainerHarnessRunner(
            image=AGENT_IMAGE, patch_path=REPO / "configs" / "dsh_task_patch.yml",
            model="deepseek-flash", reasoning_effort="low", max_tokens=256,
            provider_kind="live",  # proxy path is the same shape as live
            provider_endpoint=proxy.endpoint)
        outcome = runner.run_task(spec, ws, "proxy-e2e", _budget(),
                                  api_key="sk-proxied")
        assert outcome.finish_reason == "completed"
        judge = Judge(DockerExecutor())
        report = judge.grade(spec, ws)
        assert report.visible_passed and report.sealed_passed
        entries = proxy.snapshot()["entries"]
        states = [e.get("state") for e in entries]
        assert "RESERVED" in states and "SETTLED" in states
        assert all(e.get("task_id") == spec.task_id for e in entries if "task_id" in e)


def test_proxy_cap_stops_agent_midrun(tmp_path, spec):
    """cap=1: the runtime's second provider request must be rejected by the
    proxy BEFORE forwarding (upstream call_count proves it)."""
    tape = {"0": [["tool_call", "read", {"file_path": "solution.py"}]],
            "1": [["tool_call", "write", {"file_path": "solution.py",
                                          "content": "def clamp_value(x, lo, hi):\n    return min(max(x, lo), hi)\n"}]],
            "2": [["text", "done"]]}
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "solution.py").write_text("def clamp_value(x, lo, hi):\n    return min(max(x, hi), lo)\n",
                                    encoding="utf-8")
    with ProviderContainer(tape) as upstream, \
            ProxyContainer(upstream=upstream.endpoint, ledger_dir=tmp_path / "ledger",
                           max_requests_per_task=1) as proxy:
        proxy.set_current_task(spec.task_id)
        runner = ContainerHarnessRunner(
            image=AGENT_IMAGE, patch_path=REPO / "configs" / "dsh_task_patch.yml",
            model="deepseek-flash", reasoning_effort="low", max_tokens=256,
            provider_kind="live", provider_endpoint=proxy.endpoint)
        outcome = runner.run_task(spec, ws, "proxy-e2e-cap", _budget(),
                                  api_key="sk-proxied")
        states = [e.get("state") for e in proxy.snapshot()["entries"]]
        assert "REJECTED" in states, "the 2nd request must be rejected pre-send"
        # the upstream saw at most one forwarded request: prove via its ledger
        # (the provider container logs observations)
        obs = [json.loads(l) for l in
               (tmp_path / "ledger" / "ledger.jsonl").read_text().splitlines() if l.strip()]
        assert sum(1 for e in obs if e.get("state") == "SENT") == 1


def test_agent_cannot_bypass_proxy_when_endpoint_absent(tmp_path, spec):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "solution.py").write_text("x = 1\n", encoding="utf-8")
    runner = ContainerHarnessRunner(
        image=AGENT_IMAGE, patch_path=REPO / "configs" / "dsh_task_patch.yml",
        model="deepseek-flash", reasoning_effort="low", max_tokens=256,
        provider_kind="live", provider_endpoint=None)
    with pytest.raises(PermissionError):
        runner.run_task(spec, ws, "no-proxy", _budget(), api_key="sk-x")
