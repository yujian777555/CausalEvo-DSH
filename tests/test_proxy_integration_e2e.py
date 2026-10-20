"""Docker E2E: agent container -> ProxyContainer -> fake provider -> judge
(P4-R1.2-S2, hardened P4-R1.3 S2-S4). Full chain on the internal network;
no external calls. Ingress auth uses the per-run proxy client token."""

import json
import subprocess
import time
import urllib.error
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


def _runner(proxy):
    return ContainerHarnessRunner(
        image=AGENT_IMAGE, patch_path=REPO / "configs" / "dsh_task_patch.yml",
        model="deepseek-flash", reasoning_effort="low", max_tokens=256,
        provider_kind="live",  # proxy path is the same shape as live
        provider_endpoint=proxy.endpoint, agent_api_key=proxy.client_token)


GOOD_TAPE = {"0": [["tool_call", "read", {"file_path": "solution.py"}]],
             "1": [["tool_call", "write", {"file_path": "solution.py",
                                           "content": "def clamp_value(x, lo, hi):\n    return min(max(x, lo), hi)\n"}]],
             "2": [["text", "done"]]}


def _ws(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "solution.py").write_text(
        "def clamp_value(x, lo, hi):\n    return min(max(x, hi), lo)\n",
        encoding="utf-8")
    return ws


def test_agent_through_proxy_full_chain(tmp_path, spec):
    ws = _ws(tmp_path)
    with ProviderContainer(GOOD_TAPE) as upstream, \
            ProxyContainer(upstream=upstream.endpoint,
                           ledger_dir=tmp_path / "ledger") as proxy:
        proxy.set_current_scope(f"e2e/{spec.task_id}/s1/B0")
        outcome = _runner(proxy).run_task(spec, ws, "proxy-e2e", _budget(),
                                          api_key="sk-ignored-by-proxied-mode")
        assert outcome.finish_reason == "completed"
        judge = Judge(DockerExecutor())
        report = judge.grade(spec, ws)
        assert report.visible_passed and report.sealed_passed
        entries = proxy.snapshot()["entries"]
        states = [e.get("state") for e in entries]
        assert "RESERVED" in states and "SETTLED" in states
        assert all(e.get("scope") == f"e2e/{spec.task_id}/s1/B0"
                   for e in entries if "scope" in e)
        assert upstream.request_count() >= 1


def test_proxy_cap_stops_agent_midrun(tmp_path, spec):
    """cap=1: the runtime's second provider request must be rejected by the
    proxy BEFORE forwarding; the PROVIDER-SIDE counter proves it (not the
    proxy's own SENT ledger rows)."""
    ws = _ws(tmp_path)
    with ProviderContainer(GOOD_TAPE) as upstream, \
            ProxyContainer(upstream=upstream.endpoint,
                           ledger_dir=tmp_path / "ledger",
                           max_requests_per_task=1) as proxy:
        proxy.set_current_scope(f"e2e/{spec.task_id}/s1/B0")
        _runner(proxy).run_task(spec, ws, "proxy-e2e-cap", _budget(),
                                api_key="sk-ignored")
        states = [e.get("state") for e in proxy.snapshot()["entries"]]
        assert "REJECTED" in states, "the 2nd request must be rejected pre-send"
        assert upstream.request_count() == 1, \
            "provider observed exactly one forwarded request (cap-before-send)"


def test_repeated_same_scope_does_not_deadlock(tmp_path, spec):
    """R1.2 ACK bug: two consecutive identical attributions must both succeed."""
    ws = _ws(tmp_path)
    with ProviderContainer(GOOD_TAPE) as upstream, \
            ProxyContainer(upstream=upstream.endpoint,
                           ledger_dir=tmp_path / "ledger") as proxy:
        scope = f"e2e/{spec.task_id}/s1/B0"
        proxy.set_current_scope(scope)
        proxy.set_current_scope(scope)  # identical repeat: must ack again
        proxy.set_current_scope(scope)
        outcome = _runner(proxy).run_task(spec, ws, "proxy-e2e-repeat",
                                          _budget(), api_key="sk-ignored")
        assert outcome.finish_reason == "completed"


def test_scopes_are_independent_per_arm(tmp_path, spec):
    """Same task, different arm scopes: cap=1 each, both rows run (R1.3-S3)."""
    ws = _ws(tmp_path)
    with ProviderContainer(GOOD_TAPE) as upstream, \
            ProxyContainer(upstream=upstream.endpoint,
                           ledger_dir=tmp_path / "ledger",
                           max_requests_per_task=1) as proxy:
        proxy.set_current_scope(f"e2e/{spec.task_id}/s1/B0")
        proxy.set_current_scope(f"e2e/{spec.task_id}/s1/B1")
        snap = proxy.snapshot()["entries"]
        scopes = [e.get("scope") for e in snap if e.get("state") == "RESERVED"]
        assert scopes == [], "no agent run yet: zero reservations"


def test_bridge_sibling_cannot_use_proxy(tmp_path):
    """P0-E: a container on the DEFAULT BRIDGE (no client token) must not be
    able to spend through the proxy, even though the proxy is dual-NIC."""
    with ProviderContainer(GOOD_TAPE) as upstream, \
            ProxyContainer(upstream=upstream.endpoint,
                           ledger_dir=tmp_path / "ledger") as proxy:
        # proxy's address on the default bridge
        inspect = subprocess.run(
            ["docker", "inspect", proxy.name, "--format",
             "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}"],
            capture_output=True, text=True, timeout=15)
        ip = inspect.stdout.split()[0]
        script = (
            "import urllib.request,urllib.error,json\n"
            f"req=urllib.request.Request('http://{ip}:8081/chat/completions',"
            "data=json.dumps({'model':'deepseek-flash','messages':[]}).encode(),"
            "headers={'Content-Type':'application/json'})\n"
            "try:\n urllib.request.urlopen(req,timeout=10); print('LEAK:200')\n"
            "except urllib.error.HTTPError as e: print('STATUS:%d'%e.code)\n"
            "except Exception as e: print('ERR:%s'%type(e).__name__)\n")
        out = subprocess.run(
            ["docker", "run", "--rm", "--network", "bridge",
             "python:3.11-slim", "python", "-c", script],
            capture_output=True, text=True, timeout=120)
        assert "STATUS:401" in out.stdout, \
            f"unauthenticated sibling must be rejected: {out.stdout} {out.stderr}"
        assert upstream.request_count() == 0, "nothing reached the upstream"
        audits = [json.loads(l) for l in
                  (tmp_path / "ledger" / "ledger.jsonl").read_text().splitlines()
                  if l.strip()]
        assert any(e.get("state") == "REJECTED"
                   and e.get("reason") == "ingress_auth" for e in audits), \
            "the 401 must be audited in the ledger"


def test_agent_cannot_bypass_proxy_when_endpoint_absent(tmp_path, spec):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "solution.py").write_text("x = 1\n", encoding="utf-8")
    # construction itself must now fail without proxy endpoint/token (R1.3-S1)
    with pytest.raises(ValueError):
        ContainerHarnessRunner(
            image=AGENT_IMAGE, patch_path=REPO / "configs" / "dsh_task_patch.yml",
            model="deepseek-flash", reasoning_effort="low", max_tokens=256,
            provider_kind="live", provider_endpoint=None)
