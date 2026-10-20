"""P4-R1.4 P0-C/P1-D: real API key must NEVER enter agent-visible space, and
must never ride the host docker CLI argv either.

History: this file replaces tests/test_secret_isolation.py, which was silently
swallowed by the .gitignore `*secret*` protection rule in R1.3 and therefore
never reached the remote — the R1.3 report path was wrong; this is the
corrected, committed, and extended version.

Canary tests drive the ACTUAL request-building/run path (ContainerHarness-
Runner.run_task with a captured subprocess) and the ACTUAL ProxyContainer
docker-run construction (captured _docker call): a canary "real" key must
appear 0 times in the agent container request JSON (stdin), the agent docker
argv/env, the proxy docker argv, serialized outcomes (trace/ledger), stdout/
stderr, and exception text. The agent only holds the per-run proxy token; the
real key reaches the proxy container exclusively through the subprocess
environment (bare `-e NAME` passthrough).
"""

import io
import json
from pathlib import Path

import pytest

from causalevo.eval import harness_agent, networks
from causalevo.eval.harness_agent import ContainerHarnessRunner
from causalevo.eval.runtime_budget import RuntimeBudget
from causalevo.eval.task_spec import load_task

REPO = Path(__file__).resolve().parents[1]
CANARY = "sk-CANARYrealsecret-0123456789abcdef0123456789abcdef"
TOKEN = "ce-proxy-testtoken-0123456789abcdef"


@pytest.fixture
def spec():
    return load_task(REPO / "benchmarks" / "tasks" / "micro-000-clamp_value")


def _budget():
    return RuntimeBudget(max_provider_calls=2, max_total_output_tokens=1024,
                         max_tool_calls=5, wall_time_s=60)


class _RecordingStdin(io.StringIO):
    """StringIO that mirrors every write (run_task closes stdin, so the
    content must be captured at write time)."""

    def __init__(self, sink: list):
        super().__init__()
        self._sink = sink

    def write(self, s):
        self._sink.append(s)
        return super().write(s)


class _FakeProc:
    """Captures stdin (the container request JSON) and replays a clean final
    message on stdout so run_task completes without docker."""

    def __init__(self, cmd, sink: list):
        self.cmd = cmd
        self.stdin = _RecordingStdin(sink)
        final = {"type": "final", "ok": True, "finish_reason": "completed",
                 "final_response": "done", "events": []}
        self.stdout = io.StringIO(json.dumps(final) + "\n")
        self.stderr = io.StringIO("")
        self.returncode = 0

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def kill(self):
        pass


def _run_with_capture(monkeypatch, spec, runner, api_key):
    captured = {"stdin_writes": []}

    def fake_popen(cmd, **kw):
        proc = _FakeProc(cmd, captured["stdin_writes"])
        captured["cmd"] = cmd
        captured["proc"] = proc
        return proc

    monkeypatch.setattr(harness_agent.subprocess, "Popen", fake_popen)
    outcome = runner.run_task(spec, Path("/tmp/ws"), "arm", _budget(),
                              api_key=api_key)
    captured["outcome"] = outcome
    return captured


def test_canary_key_absent_from_container_request_and_env(monkeypatch, spec):
    runner = ContainerHarnessRunner(
        image="img", patch_path=REPO / "configs" / "dsh_task_patch.yml",
        model="deepseek-flash", reasoning_effort="low", max_tokens=64,
        provider_kind="live", provider_endpoint="http://ceval-proxy-x:8081",
        agent_api_key=TOKEN)
    cap = _run_with_capture(monkeypatch, spec, runner, api_key=CANARY)

    stdin_blob = "".join(cap["stdin_writes"])
    request = json.loads(stdin_blob)
    assert request["api_key"] == TOKEN, "agent gets the proxy token only"
    assert CANARY not in stdin_blob, "real key leaked into request JSON"
    for element in cap["cmd"]:
        assert CANARY not in element, "real key leaked into agent docker argv/env"
    blob = json.dumps(cap["outcome"].ledger) + json.dumps(cap["outcome"].events_slim)
    assert CANARY not in blob, "real key leaked into trace/ledger"
    stderr_text = cap["proc"].stderr.getvalue()
    assert CANARY not in stderr_text


def test_canary_absent_even_on_provider_error_path(monkeypatch, spec):
    """Exceptions/abnormal finals must not smuggle the real key either."""
    runner = ContainerHarnessRunner(
        image="img", patch_path=REPO / "configs" / "dsh_task_patch.yml",
        model="deepseek-flash", reasoning_effort="low", max_tokens=64,
        provider_kind="live", provider_endpoint="http://ceval-proxy-x:8081",
        agent_api_key=TOKEN)

    class _ErrProc(_FakeProc):
        def __init__(self, cmd):
            super().__init__(cmd, [])
            self.stdout = io.StringIO(json.dumps(
                {"type": "final", "ok": False,
                 "error": f"upstream rejected placeholder {TOKEN}"}) + "\n")

    monkeypatch.setattr(harness_agent.subprocess, "Popen",
                        lambda cmd, **kw: _ErrProc(cmd))
    outcome = runner.run_task(spec, Path("/tmp/ws"), "arm", _budget(),
                              api_key=CANARY)
    blob = json.dumps(outcome.ledger) + json.dumps(outcome.events_slim) + \
        str(outcome.budget_stop_reason)
    assert CANARY not in blob


def test_canary_absent_when_container_launch_fails(monkeypatch, spec):
    """Docker start failure: the raised exception (which may embed the command
    line) must not contain the real key."""
    runner = ContainerHarnessRunner(
        image="img", patch_path=REPO / "configs" / "dsh_task_patch.yml",
        model="deepseek-flash", reasoning_effort="low", max_tokens=64,
        provider_kind="live", provider_endpoint="http://ceval-proxy-x:8081",
        agent_api_key=TOKEN)

    def boom(cmd, **kw):
        raise OSError(f"docker launch failed: {cmd}")

    monkeypatch.setattr(harness_agent.subprocess, "Popen", boom)
    with pytest.raises(OSError) as excinfo:
        runner.run_task(spec, Path("/tmp/ws"), "arm", _budget(), api_key=CANARY)
    assert CANARY not in str(excinfo.value)


def test_live_construction_requires_proxy_and_placeholder():
    with pytest.raises(ValueError):
        ContainerHarnessRunner(
            image="img", patch_path=REPO / "configs" / "dsh_task_patch.yml",
            model="deepseek-flash", reasoning_effort="low", max_tokens=64,
            provider_kind="live", provider_endpoint=None,
            agent_api_key=TOKEN)
    with pytest.raises(ValueError):
        ContainerHarnessRunner(
            image="img", patch_path=REPO / "configs" / "dsh_task_patch.yml",
            model="deepseek-flash", reasoning_effort="low", max_tokens=64,
            provider_kind="live", provider_endpoint="http://ceval-proxy-x:8081",
            agent_api_key=None)


def test_live_driver_factory_uses_proxy_token():
    """run_phase4_pilot.make_live_runner wires the per-run proxy token as the
    agent credential (never the real key)."""
    import importlib.util
    import types
    script = REPO / "scripts" / "run_phase4_pilot.py"
    spec_mod = importlib.util.spec_from_file_location("run_phase4_pilot", script)
    mod = importlib.util.module_from_spec(spec_mod)
    spec_mod.loader.exec_module(mod)
    proxy = types.SimpleNamespace(endpoint="http://ceval-proxy-x:8081",
                                  client_token=TOKEN)
    runner = mod.make_live_runner(proxy)
    assert runner.agent_api_key == TOKEN
    assert runner.provider_endpoint == proxy.endpoint
    assert runner.provider_kind == "live"


def test_live_driver_source_never_moves_real_key_to_agent_holder():
    """Source guard: the live branch must not call set_api_key(<env key>);
    the real key may only reach the balance query and ProxyContainer env."""
    src = (REPO / "scripts" / "run_phase4_pilot.py").read_text(encoding="utf-8")
    assert "set_api_key(key)" not in src
    assert "agent_api_key=proxy.client_token" in src
    # the placeholder/fake key is still set for dry-run symmetry
    assert 'set_api_key("sk-fake-offline-no-cost")' in src


def test_out_dir_resolved_before_live_setup(tmp_path, monkeypatch):
    """P1 regression: --live --out must fail at the authorization gate with a
    SPECIFIC error, never a NameError about out_dir."""
    import os
    import subprocess
    import sys
    env = dict(os.environ)
    env.pop("DEEPSEEK_API_KEY", None)
    env.pop("CE_DSH_LIVE_AUTH", None)
    env["NO_PROXY"] = "*"
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "run_phase4_pilot.py"),
         "--live", "--tasks", "1", "--out", str(tmp_path)],
        capture_output=True, text=True, env=env, timeout=120)
    blob = (proc.stdout + proc.stderr).lower()
    assert proc.returncode != 0
    assert "nameerror" not in blob and "out_dir" not in blob
    assert "live mode requires" in blob or "permissionerror" in blob


# ---------------------------------------------------------------------------
# P1-D: the real upstream key never rides the docker CLI argv
# ---------------------------------------------------------------------------

def test_proxy_container_key_not_in_docker_argv(monkeypatch, tmp_path):
    """Capture the ACTUAL ProxyContainer docker-run construction: the canary
    key must appear ONLY in the subprocess environment (bare -e passthrough),
    never in any argv element. The proxy still receives the credential."""
    calls = []

    class _CP:
        def __init__(self, returncode=0, stdout=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    def fake_docker(*args, timeout=60, extra_env=None):
        calls.append({"args": args, "extra_env": extra_env or {}})
        if args[0] == "run":
            return _CP(0)
        if args[0] == "network":
            return _CP(0)
        if args[0] == "inspect":
            return _CP(0, "true")
        if args[0] == "logs":
            return _CP(0, "proxy up")
        return _CP(0)

    monkeypatch.setattr(networks, "_docker", fake_docker)
    monkeypatch.setattr(networks, "ensure_internal_network", lambda name: name)
    monkeypatch.setattr(networks.ProxyContainer, "set_current_scope",
                        lambda self, scope: None)  # skip the bootstrap handshake

    with networks.ProxyContainer(
            upstream="http://ceval-provider-x:8080",
            ledger_dir=tmp_path / "ledger",
            upstream_api_key=CANARY):
        pass

    run_calls = [c for c in calls if c["args"][0] == "run"]
    assert run_calls, "docker run was issued"
    argv = run_calls[0]["args"]
    blob = " ".join(str(a) for a in argv)
    assert CANARY not in blob, "real key present in docker CLI argv"
    assert "CE_PROXY_KEY" in argv, "bare -e passthrough must be present"
    # the value must be present, but only in the subprocess environment
    assert "-e" in argv
    key_idx = list(argv).index("CE_PROXY_KEY")
    assert argv[key_idx - 1] == "-e" and "=" not in argv[key_idx]
    envs = run_calls[0]["extra_env"]
    assert envs.get("CE_PROXY_KEY") == CANARY, "proxy still gets the credential"
    # and the exception path of a FAILED run must not contain it either
    def failing_docker(*args, timeout=60, extra_env=None):
        if args[0] == "run":
            return _CP(125, "")
        return _CP(0)
    monkeypatch.setattr(networks, "_docker", failing_docker)
    with pytest.raises(RuntimeError) as excinfo:
        with networks.ProxyContainer(
                upstream="http://ceval-provider-x:8080",
                ledger_dir=tmp_path / "ledger2",
                upstream_api_key=CANARY):
            pass
    assert CANARY not in str(excinfo.value)


def test_agent_token_and_upstream_key_are_distinct():
    """The proxy client token (agent-visible) and the upstream key (proxy-only)
    must be different credentials by construction."""
    p = networks.ProxyContainer(upstream="http://ceval-provider-x:8080",
                                ledger_dir=Path("/tmp/x"),
                                upstream_api_key=CANARY)
    assert p.client_token != CANARY
    assert p.client_token.startswith("ce-proxy-")
