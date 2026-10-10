"""Adversarial Docker isolation tests for DockerExecutor.

Every container is throwaway (--rm, unique ceval-<hex> name). Skips cleanly
when docker is unavailable.
"""

import json
import subprocess

import pytest

from causalevo.eval.executor import DockerExecutor, docker_available

pytestmark = pytest.mark.skipif(not docker_available(), reason="docker unavailable")

PY = "python"


def _workdir(tmp_path):
    workdir = tmp_path / "ws"
    workdir.mkdir()
    (workdir / "marker.txt").write_text("hello\n")
    return workdir


def test_network_denied(tmp_path):
    res = DockerExecutor().run(
        _workdir(tmp_path),
        [PY, "-c", "import socket; socket.create_connection(('1.1.1.1', 443), timeout=5)"],
        timeout_s=30,
    )
    assert not res.timed_out
    assert res.exit_code != 0
    assert "OSError" in res.stderr


def test_no_host_filesystem(tmp_path):
    workdir = _workdir(tmp_path)
    res = DockerExecutor().run(
        workdir,
        [PY, "-c",
         "import os, json; "
         "print(json.dumps(sorted(os.listdir('/')))); "
         "print(json.dumps(sorted(os.listdir('/work'))))"],
        timeout_s=30,
    )
    assert res.exit_code == 0, res.stderr
    root_entries, work_entries = (json.loads(line) for line in res.stdout.strip().splitlines())
    assert "work" in root_entries
    assert "host" not in root_entries
    assert "Users" not in root_entries  # no C:\Users leak
    assert work_entries == ["marker.txt"]  # /work shows only mounted files


def test_workspace_read_only(tmp_path):
    workdir = _workdir(tmp_path)
    res = DockerExecutor().run(
        workdir,
        [PY, "-c", "open('/work/x.txt', 'w').write('x')"],
        timeout_s=30,
    )
    assert not res.timed_out
    assert res.exit_code != 0
    assert not (workdir / "x.txt").exists()


def test_no_inherited_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-test-key")
    res = DockerExecutor().run(
        _workdir(tmp_path),
        [PY, "-c", "import os; print('DEEPSEEK_API_KEY' in os.environ)"],
        timeout_s=30,
    )
    assert res.exit_code == 0, res.stderr
    assert res.stdout.strip() == "False"


def test_timeout_kill_leaves_no_container(tmp_path):
    res = DockerExecutor().run(
        _workdir(tmp_path),
        [PY, "-c", "import time; time.sleep(30)"],
        timeout_s=2,
    )
    assert res.timed_out
    assert res.exit_code is None
    ps = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=ceval", "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=15,
    )
    assert ps.returncode == 0
    assert ps.stdout.strip() == ""


def test_memory_cap_enforced(tmp_path):
    res = DockerExecutor().run(
        _workdir(tmp_path),
        [PY, "-c", "x = bytearray(400_000_000)"],
        timeout_s=60,
    )
    assert not res.timed_out
    assert res.exit_code is not None and res.exit_code != 0


def test_normal_run_works(tmp_path):
    res = DockerExecutor().run(
        _workdir(tmp_path),
        [PY, "-c", "print(40 + 2)"],
        timeout_s=30,
    )
    assert res.exit_code == 0, res.stderr
    assert res.stdout.strip() == "42"
    assert not res.timed_out
