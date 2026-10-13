"""Fail-closed guard tests for LocalTrustedExecutor and default_executor.

LocalTrustedExecutor is host execution for trusted offline content only:
direct construction is refused, the child environment is minimized, and
untrusted content never falls back to the host when Docker is unavailable.
"""

import os
import sys

import pytest

import causalevo.eval.executor as executor_mod
from causalevo.eval.executor import (
    DockerExecutor,
    ExecutorUnavailable,
    LocalTrustedExecutor,
    default_executor,
    docker_available,
)

PY = sys.executable


def _workdir(tmp_path):
    workdir = tmp_path / "ws"
    workdir.mkdir()
    return workdir


def test_direct_construction_raises():
    with pytest.raises(RuntimeError, match="for_trusted_content"):
        LocalTrustedExecutor()


def test_for_trusted_content_runs_trivial_command(tmp_path):
    workdir = _workdir(tmp_path)
    ex = LocalTrustedExecutor.for_trusted_content()
    res = ex.run(workdir, [PY, "-c", "import os; print('ok'); print(os.getcwd())"],
                 timeout_s=15)
    assert res.exit_code == 0, res.stderr
    assert not res.timed_out
    lines = res.stdout.strip().splitlines()
    assert lines[0] == "ok"
    # cwd is sandboxed to the given workdir
    got = os.path.normcase(os.path.realpath(lines[1].strip()))
    want = os.path.normcase(os.path.realpath(workdir))
    assert got == want
    assert res.executor == "local-trusted"


@pytest.mark.skipif(not docker_available(), reason="docker unavailable")
def test_default_executor_untrusted_uses_docker_when_available():
    ex = default_executor(for_untrusted=True)
    assert isinstance(ex, DockerExecutor)


def test_default_executor_untrusted_fails_closed_without_docker(monkeypatch):
    monkeypatch.setattr(executor_mod, "docker_available", lambda: False)
    with pytest.raises(ExecutorUnavailable):
        default_executor(for_untrusted=True)


def test_default_executor_trusted_falls_back_to_local_without_docker(monkeypatch):
    monkeypatch.setattr(executor_mod, "docker_available", lambda: False)
    ex = default_executor(for_untrusted=False)
    assert isinstance(ex, LocalTrustedExecutor)


def test_child_env_does_not_leak_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-test-key")
    ex = LocalTrustedExecutor.for_trusted_content()
    res = ex.run(_workdir(tmp_path),
                 [PY, "-c", "import os; print('DEEPSEEK_API_KEY' in os.environ)"],
                 timeout_s=15)
    assert res.exit_code == 0, res.stderr
    assert res.stdout.strip() == "False"


def test_timeout_marks_timed_out(tmp_path):
    ex = LocalTrustedExecutor.for_trusted_content()
    res = ex.run(_workdir(tmp_path),
                 [PY, "-c", "import time; time.sleep(30)"],
                 timeout_s=1)
    assert res.timed_out
    assert res.exit_code is None
