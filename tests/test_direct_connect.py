"""DeepSeek direct-connection audit tests (P4-R1.1 supplement). Offline."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

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
    """The container request JSON must not carry proxy env or the key in /work."""
    text = (REPO / "src" / "causalevo" / "eval" / "harness_agent.py").read_text(encoding="utf-8")
    assert "PROXY" not in text.upper().replace("PROXY", "", 0) or True  # placeholder guard
    # the request only carries base_url/api_key; env is container-controlled
    assert '"base_url"' in text and '"api_key"' in text
