"""G2: live authorization gate tests. Fully offline — no test may dial any
external host; api.deepseek.com must never appear in a dialed URL."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from causalevo.eval.fake_provider import FakeProvider
from causalevo.eval.provider import (
    LiveNotAuthorized,
    fake_endpoint,
    live_endpoint,
)
from causalevo.eval.harness_agent import (
    LIVE_AUTH_ENV,
    LIVE_AUTH_VALUE,
    require_live_authorization,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv(LIVE_AUTH_ENV, raising=False)
    return monkeypatch


def test_no_key_no_flag_refused(clean_env):
    with pytest.raises(LiveNotAuthorized):
        live_endpoint({})


def test_key_without_flag_refused(clean_env):
    with pytest.raises(LiveNotAuthorized):
        live_endpoint({"DEEPSEEK_API_KEY": "sk-fake"})
    with pytest.raises(PermissionError):
        require_live_authorization({"DEEPSEEK_API_KEY": "sk-fake"})


def test_flag_without_key_refused(clean_env):
    with pytest.raises(LiveNotAuthorized):
        live_endpoint({LIVE_AUTH_ENV: LIVE_AUTH_VALUE})


def test_wrong_flag_value_refused(clean_env):
    env = {"DEEPSEEK_API_KEY": "sk-fake", LIVE_AUTH_ENV: "yes-please"}
    with pytest.raises(LiveNotAuthorized):
        live_endpoint(env)


def test_full_authorization_constructs_without_network(clean_env, monkeypatch):
    """Both credentials -> endpoint object, and provably no socket is opened."""
    def _boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr("socket.socket", lambda *a, **k: _boom())
    ep = live_endpoint({"DEEPSEEK_API_KEY": "sk-fake", LIVE_AUTH_ENV: LIVE_AUTH_VALUE})
    assert ep.kind == "live" and ep.live_enabled is True
    assert ep.base_url == "https://api.deepseek.com"


def test_require_live_authorization_matrix(clean_env):
    with pytest.raises(PermissionError):
        require_live_authorization({})
    with pytest.raises(PermissionError):
        require_live_authorization({"DEEPSEEK_API_KEY": "sk-fake"})
    with pytest.raises(PermissionError):
        require_live_authorization({LIVE_AUTH_ENV: LIVE_AUTH_VALUE})
    require_live_authorization(
        {"DEEPSEEK_API_KEY": "sk-fake", LIVE_AUTH_ENV: LIVE_AUTH_VALUE})  # no raise


def test_fake_endpoint_never_live():
    with FakeProvider(lambda m, i: [("text", "ok")]) as provider:
        ep = fake_endpoint(provider)
    assert ep.kind == "fake"
    assert ep.live_enabled is False
    assert ep.base_url.startswith("http://127.0.0.1:")


def test_no_test_file_dials_deepseek_domain():
    """Static guard: the forbidden domain may appear only in comments or in
    refusal strings, never adjacent to a URL scheme."""
    for path in (REPO_ROOT / "tests").glob("test_*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in ("http://api.deepseek.com", "https://api.deepseek.com"):
            # provider.py holds the constant; tests may reference the refusal text
            # but never a URL — except this guard file's own needle literals.
            if path.name == "test_live_guard.py":
                continue
            assert needle not in text, f"{path.name} references {needle}"


def _run_cli(env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop(LIVE_AUTH_ENV, None)
    env.update(env_extra)
    env["NO_PROXY"] = "*"
    return subprocess.run(
        [str(REPO_ROOT / ".venv" / "Scripts" / "python.exe"),
         str(REPO_ROOT / "scripts" / "run_agent_task.py"), "--live", "--tasks", "1"],
        capture_output=True, text=True, env=env, timeout=120)


def test_cli_live_refused_without_flag():
    proc = _run_cli({"DEEPSEEK_API_KEY": "sk-fake"})
    assert proc.returncode == 2
    assert "not scheduled" in (proc.stdout + proc.stderr) or "refus" in (
        proc.stdout + proc.stderr).lower()


def test_cli_live_refused_even_with_flag_this_round():
    proc = _run_cli({"DEEPSEEK_API_KEY": "sk-fake", LIVE_AUTH_ENV: LIVE_AUTH_VALUE})
    assert proc.returncode == 2
    assert "not scheduled" in proc.stdout
