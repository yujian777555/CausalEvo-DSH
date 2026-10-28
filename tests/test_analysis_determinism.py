"""Deterministic regeneration test for normalized R1.12 analysis output
(P4-R1.12-REVIEW-FIX2 Task D): two isolated output locations must produce
byte-identical analysis.json after run_dir normalization."""

import json
import runpy
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

PILOT = REPO / "results" / "phase4" / "live2" / "phase4-r12-replication-pilot-20261027T034229Z"


def _run(d):
    sys.argv = ["analyze_r12_replication.py", str(d)]
    try:
        runpy.run_path(str(REPO / "scripts" / "analyze_r12_replication.py"),
                       run_name="__main__")
    except SystemExit as exc:
        if exc.code not in (0, None):
            raise


def test_two_isolated_locations_byte_identical(tmp_path):
    a = tmp_path / "loc-a"
    b = tmp_path / "loc-b"
    for loc in (a, b):
        loc.mkdir()
        shutil.copytree(PILOT, loc / "phase4-r12-replication-pilot-20261027T034229Z")
    _run(a / "phase4-r12-replication-pilot-20261027T034229Z")
    _run(b / "phase4-r12-replication-pilot-20261027T034229Z")
    fa = (a / "phase4-r12-replication-pilot-20261027T034229Z" / "analysis.json").read_bytes()
    fb = (b / "phase4-r12-replication-pilot-20261027T034229Z" / "analysis.json").read_bytes()
    assert fa == fb, "analysis.json must be byte-identical across isolated output locations"


def test_run_dir_is_relative_posix_not_machine_specific(tmp_path):
    _run(PILOT)
    doc = json.loads((PILOT / "analysis.json").read_text(encoding="utf-8"))
    run_dir = doc["run_dir"]
    assert "\\" not in run_dir, "run_dir must be POSIX, not a Windows absolute path"
    assert run_dir.startswith("results/phase4/live2/"), run_dir
