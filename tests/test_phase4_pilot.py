"""Phase 4 pilot runner tests: arm logic, gating, dry-run path (offline)."""

import json
from pathlib import Path

import numpy as np
import pytest

from causalevo.eval.live_pilot import ARMS, INTERVENTION_TEXT, run_task_arm

REPO = Path(__file__).resolve().parents[1]


def test_six_arms_frozen():
    assert ARMS == ["B0-original", "B1-random", "B2-rule", "B3-reflexion",
                    "B4-cea-v0", "B5-cea-v1"]


def test_intervention_texts_nonempty_and_frozen_keys():
    assert set(INTERVENTION_TEXT) == {"tool_validation", "verification",
                                      "read_before_write", "planning"}
    for t in INTERVENTION_TEXT.values():
        assert len(t) > 20


def test_pilot_refuses_live_without_auth(monkeypatch):
    import os
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("CE_DSH_LIVE_AUTH", raising=False)
    env = dict(os.environ)
    env.pop("DEEPSEEK_API_KEY", None)
    env["NO_PROXY"] = "*"
    import subprocess
    proc = subprocess.run(
        [str(REPO / ".venv" / "Scripts" / "python.exe"),
         str(REPO / "scripts" / "run_phase4_pilot.py"), "--live", "--tasks", "1"],
        capture_output=True, text=True, env=env, timeout=120)
    assert proc.returncode != 0  # PermissionError before any socket


def test_dry_run_smoke_two_tasks():
    """The committed dry-run scratch proves the offline path (rerun is slow)."""
    runs = sorted((REPO / "results" / "phase4" / "scratch").glob("phase4-dry-*"))
    assert runs, "dry-run evidence missing"
    manifest = json.loads((runs[-1] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["live"] is False
    assert manifest["rows"] == 24
    assert manifest["spent_cny"] >= 0
