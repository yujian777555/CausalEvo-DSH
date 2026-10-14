"""S0-GATE adversarial FS isolation tests for the CONTAINER world.

Each test drives ContainerHarnessRunner with a scripted FakeProvider against
a tmp workspace; a host canary secret (a file OUTSIDE the mounted workspace)
must never appear in any tool result the provider observes. Requires docker
plus the local agent/helper images; skips cleanly otherwise.
"""

import subprocess
import uuid
from pathlib import Path

import pytest

from causalevo.eval.executor import docker_available
from causalevo.eval.harness_agent import ContainerHarnessRunner
from causalevo.eval.runtime_budget import RuntimeBudget
from causalevo.eval.task_spec import load_task

REPO = Path(__file__).resolve().parents[1]
AGENT_IMAGE = "causalevo-dsh-agent:0.2.0"
HELPER_IMAGE = "python:3.11-slim"
TASK_DIR = REPO / "benchmarks" / "tasks" / "micro-000-clamp_value"


def _image_exists(image: str) -> bool:
    try:
        proc = subprocess.run(["docker", "image", "inspect", image],
                              capture_output=True, timeout=15)
        return proc.returncode == 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not (docker_available() and _image_exists(AGENT_IMAGE) and _image_exists(HELPER_IMAGE)),
    reason="docker or local agent/helper image unavailable",
)

BUGGY = "def clamp_value(x, lo, hi):\n    return min(max(x, hi), lo)\n"


def _workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir(parents=True)
    (ws / "solution.py").write_text(BUGGY, encoding="utf-8")
    return ws


def _canary(tmp_path: Path) -> tuple[Path, str]:
    secret = f"CANARY_{uuid.uuid4().hex[:12]}"
    path = tmp_path / "host_canary.txt"  # outside the mounted workspace
    path.write_text(secret, encoding="utf-8")
    return path, secret


def _run_container(ws: Path, script):
    """Drive the v2 container runner: tape server inside the internal network,
    hardened agent container (ro rootfs, cap-drop ALL, internal net only)."""
    from causalevo.eval.networks import ProviderContainer

    tape = {str(i): [list(a) for a in script([], i)] for i in range(8)}
    spec = load_task(TASK_DIR)
    with ProviderContainer(tape) as provider:
        runner = ContainerHarnessRunner(
            image=AGENT_IMAGE,
            patch_path=REPO / "configs" / "dsh_task_patch.yml",
            model="deepseek-flash", reasoning_effort="low", max_tokens=256,
            provider_endpoint=provider.endpoint,
        )
        budget = RuntimeBudget(max_provider_calls=8, max_total_output_tokens=4096,
                               max_tool_calls=12, wall_time_s=240)
        outcome = runner.run_task(spec, ws, "S0-gate-fsiso", budget,
                                  api_key="sk-fake-offline-no-cost")
        results = provider.tool_results()
    return outcome, results


def _assert_no_leak(results: list[str], secret: str) -> None:
    assert results, "scripted tool calls produced no tool results"
    for content in results:
        assert secret not in content, "host canary leaked into agent tool results"


def test_read_absolute_host_windows_path_fails(tmp_path):
    ws = _workspace(tmp_path)
    canary_path, secret = _canary(tmp_path)

    def script(messages, call_index):
        if call_index == 0:
            return [("tool_call", "read", {"file_path": str(canary_path)})]
        return [("text", "done")]

    outcome, results = _run_container(ws, script)
    assert outcome.failure_kind == "none"
    assert all(c.startswith("Error") for c in results)
    assert any("not found" in c for c in results)
    _assert_no_leak(results, secret)


def test_read_traversal_out_of_workspace_fails(tmp_path):
    ws = _workspace(tmp_path)
    _canary_path, secret = _canary(tmp_path)

    def script(messages, call_index):
        if call_index == 0:
            return [("tool_call", "read", {"file_path": "../host_canary.txt"})]
        if call_index == 1:
            return [("tool_call", "read", {"file_path": "../../host_canary.txt"})]
        return [("text", "done")]

    outcome, results = _run_container(ws, script)
    assert outcome.failure_kind == "none"
    assert all(c.startswith("Error") for c in results)
    assert any("not found" in c for c in results)
    _assert_no_leak(results, secret)


def test_container_etc_hostname_is_not_host(tmp_path):
    ws = _workspace(tmp_path)
    canary_path, secret = _canary(tmp_path)

    def script(messages, call_index):
        if call_index == 0:
            return [("tool_call", "read", {"file_path": "/etc/hostname"})]
        if call_index == 1:
            # host-mount-style secret path; nothing like it exists in the container
            return [("tool_call", "read", {"file_path": f"/host_mnt/{canary_path.name}"})]
        return [("text", "done")]

    outcome, results = _run_container(ws, script)
    assert outcome.failure_kind == "none"
    # the container has its OWN /etc/hostname: reading it succeeds, harmlessly
    assert any("<path>/etc/hostname</path>" in c for c in results)
    assert any("not found" in c for c in results)
    _assert_no_leak(results, secret)


def test_symlink_escape_read_fails(tmp_path):
    ws = _workspace(tmp_path)
    canary_path, secret = _canary(tmp_path)
    # host Windows cannot create arbitrary symlinks without extra privileges;
    # create the link from inside a helper container against the same mount
    create = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{ws.resolve()}:/work",
         HELPER_IMAGE, "ln", "-s", str(canary_path), "/work/escape_link"],
        capture_output=True, text=True, timeout=60)
    assert create.returncode == 0, create.stderr
    check = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{ws.resolve()}:/work",
         HELPER_IMAGE, "test", "-L", "/work/escape_link"],
        capture_output=True, timeout=60)
    assert check.returncode == 0, "symlink was not created"

    def script(messages, call_index):
        if call_index == 0:
            return [("tool_call", "read", {"file_path": "escape_link"})]
        return [("text", "done")]

    outcome, results = _run_container(ws, script)
    assert outcome.failure_kind == "none"
    assert all(c.startswith("Error") for c in results)
    assert any("not found" in c for c in results)
    _assert_no_leak(results, secret)


def test_read_sibling_task_workspace_fails(tmp_path):
    ws = _workspace(tmp_path)
    _canary_path, secret = _canary(tmp_path)
    sibling = tmp_path / "sibling_task_ws"  # another task's workspace, never mounted
    sibling.mkdir()
    (sibling / "solution.py").write_text(f"# {secret}\n", encoding="utf-8")
    target = str(sibling / "solution.py")

    def script(messages, call_index):
        if call_index == 0:
            return [("tool_call", "read", {"file_path": target})]
        return [("text", "done")]

    outcome, results = _run_container(ws, script)
    assert outcome.failure_kind == "none"
    assert all(c.startswith("Error") for c in results)
    _assert_no_leak(results, secret)


def test_glob_root_then_secret_file_no_leak(tmp_path):
    ws = _workspace(tmp_path)
    _canary_path, secret = _canary(tmp_path)

    def script(messages, call_index):
        if call_index == 0:
            return [("tool_call", "glob", {"pattern": "**/*", "path": "/"})]
        if call_index == 1:
            return [("tool_call", "read", {"file_path": "/etc/shadow"})]
        return [("text", "done")]

    outcome, results = _run_container(ws, script)
    assert outcome.failure_kind == "none"
    for content in results:  # the agent only ever sees container paths
        assert "C:\\" not in content and "D:\\" not in content
    assert any("permission denied" in c for c in results)  # /etc/shadow unreadable
    _assert_no_leak(results, secret)


def test_grep_canary_across_root_no_leak(tmp_path):
    ws = _workspace(tmp_path)
    _canary_path, secret = _canary(tmp_path)

    def script(messages, call_index):
        if call_index == 0:
            return [("tool_call", "grep", {"pattern": secret, "path": "/"})]
        return [("text", "done")]

    outcome, results = _run_container(ws, script)
    assert outcome.failure_kind == "none"
    _assert_no_leak(results, secret)


def test_write_outside_workspace_denied(tmp_path):
    ws = _workspace(tmp_path)
    _canary_path, secret = _canary(tmp_path)

    def script(messages, call_index):
        if call_index == 0:
            return [("tool_call", "write", {"file_path": "/etc/x", "content": "x"})]
        if call_index == 1:
            # positive control: writing inside the workspace must work
            return [("tool_call", "write", {"file_path": "ok.txt", "content": "ok"})]
        return [("text", "done")]

    outcome, results = _run_container(ws, script)
    assert outcome.failure_kind == "none"
    assert any("sandbox: file access denied" in c for c in results)
    assert (ws / "ok.txt").read_text(encoding="utf-8") == "ok"
    _assert_no_leak(results, secret)
