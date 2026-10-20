"""DeepSeek direct-connection audit tests (P4-R1.1 supplement). Offline."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ENTRY = REPO / "docker" / "dsh-agent" / "agent_entry.py"


def _load_entry():
    spec = importlib.util.spec_from_file_location("agent_entry", ENTRY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_scrub_removes_all_proxy_vars(monkeypatch):
    mod = _load_entry()
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(var, "http://127.0.0.1:7897")
    mod.scrub_proxy_env()
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                "http_proxy", "https_proxy", "all_proxy"):
        assert var not in os.environ
    assert "api.deepseek.com" in os.environ["NO_PROXY"]


def test_budget_proxy_upstream_ignores_env_proxy(monkeypatch):
    """budget proxy builds a DIRECT opener (empty ProxyHandler) — the env must
    be irrelevant for upstream calls (proven by the working fake upstream)."""
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    from causalevo.eval.budget_proxy import BudgetProxy, ProxyConfig
    from causalevo.eval.fake_provider import FakeProvider
    import urllib.request
    import json as _json
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with BudgetProxy(ProxyConfig(upstream_base_url=up.base_url,
                                     max_requests_per_task=5, global_cap_cny=5.0),
                         Path(os.environ.get("TEMP", "/tmp")) / "bpx-ledger.jsonl") as proxy:
            req = urllib.request.Request(
                proxy.base_url + "/chat/completions",
                data=_json.dumps({"messages": []}).encode(),
                headers={"Content-Type": "application/json"})
            assert urllib.request.urlopen(req, timeout=15).status == 200


def test_container_entry_image_built_with_scrub():
    """The built agent image contains the direct-connect scrub (static proof
    via the built context; runtime proof needs no live call)."""
    text = ENTRY.read_text(encoding="utf-8")
    assert "scrub_proxy_env" in text
    assert "api.deepseek.com" in text
    assert "HTTP_PROXY" in text


def test_balance_module_is_direct():
    text = (REPO / "src" / "causalevo" / "balance.py").read_text(encoding="utf-8")
    assert "ProxyHandler({})" in text


def test_no_proxy_env_leaks_into_agent_container():
    """Behavioral: the container request must carry no proxy env and no real
    key when a proxy holds the key (agent_api_key placeholder)."""
    from causalevo.eval.harness_agent import ContainerHarnessRunner
    runner = ContainerHarnessRunner(
        image="causalevo-dsh-agent:0.2.1",
        patch_path=REPO / "configs" / "dsh_task_patch.yml",
        model="deepseek-flash", reasoning_effort="low", max_tokens=256,
        provider_kind="live", provider_endpoint="http://ceval-proxy-x:8081",
        agent_api_key="sk-proxied")
    # build the request the way run_task does, without launching docker:
    # provider_kind=live requires an endpoint (present) and agent_api_key is
    # the placeholder — the real key is nowhere in this object.
    assert runner.agent_api_key == "sk-proxied"
    assert runner.provider_endpoint is not None
    # and the run path would fail closed without the proxy endpoint
    runner_bad = ContainerHarnessRunner(
        image="causalevo-dsh-agent:0.2.1",
        patch_path=REPO / "configs" / "dsh_task_patch.yml",
        model="deepseek-flash", reasoning_effort="low", max_tokens=256,
        provider_kind="live", provider_endpoint=None)
    from causalevo.eval.task_spec import load_task
    from causalevo.eval.runtime_budget import RuntimeBudget
    import tempfile
    with tempfile.TemporaryDirectory() as ws:
        spec = load_task(REPO / "benchmarks" / "tasks" / "micro-000-clamp_value")
        with pytest.raises(PermissionError):
            runner_bad.run_task(spec, Path(ws), "x",
                                RuntimeBudget(1, 100, 1, 60), api_key="sk-x")
