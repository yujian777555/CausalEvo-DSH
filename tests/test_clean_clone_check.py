import importlib.util
from pathlib import Path
from unittest.mock import Mock

REPO = Path(__file__).resolve().parents[1]
REMOTE_SHA = "a" * 40
OTHER_SHA = "b" * 40

_spec = importlib.util.spec_from_file_location(
    "clean_clone_check", REPO / "scripts" / "clean_clone_check.py")
clean_clone_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(clean_clone_check)


def _forbid_side_effects(monkeypatch, tmp_path):
    mkdtemp = Mock(return_value=str(tmp_path / "work"))
    run = Mock()
    monkeypatch.setattr(clean_clone_check.tempfile, "mkdtemp", mkdtemp)
    monkeypatch.setattr(clean_clone_check.subprocess, "run", run)
    monkeypatch.setattr(
        clean_clone_check, "_git",
        lambda *args, **kwargs: Mock(stdout=REMOTE_SHA + "\n"))
    return mkdtemp, run


def test_explicit_sha_must_match_remote_before_any_clone_or_install(
        monkeypatch, tmp_path):
    remote_sha = Mock(return_value=REMOTE_SHA)
    monkeypatch.setattr(clean_clone_check, "_remote_sha", remote_sha)
    monkeypatch.setattr(
        clean_clone_check.sys, "argv", ["clean_clone_check.py", OTHER_SHA])
    mkdtemp, run = _forbid_side_effects(monkeypatch, tmp_path)

    result = clean_clone_check.main()

    assert result == 2
    remote_sha.assert_called_once_with()
    mkdtemp.assert_not_called()
    run.assert_not_called()


def test_unknown_remote_sha_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(clean_clone_check, "_remote_sha", lambda: None)
    monkeypatch.setattr(clean_clone_check.sys, "argv", ["clean_clone_check.py"])
    mkdtemp, run = _forbid_side_effects(monkeypatch, tmp_path)

    result = clean_clone_check.main()

    assert result == 3
    mkdtemp.assert_not_called()
    run.assert_not_called()


ORIGIN_URL = "https://user:fake-token@example.invalid/org/repo.git"


def _mock_clone_environment(monkeypatch, tmp_path, run=None, head=REMOTE_SHA):
    work = tmp_path / "work"
    clone = work / "repo"
    monkeypatch.setattr(clean_clone_check, "_remote_sha", lambda: REMOTE_SHA)
    monkeypatch.setattr(clean_clone_check.sys, "argv", ["clean_clone_check.py"])
    monkeypatch.setattr(
        clean_clone_check.tempfile, "mkdtemp", Mock(return_value=str(work)))
    run = Mock() if run is None else run
    monkeypatch.setattr(clean_clone_check.subprocess, "run", run)

    def fake_git(args, cwd, check=True, env=None):
        if args == ["config", "--get", "remote.origin.url"]:
            return Mock(stdout=ORIGIN_URL + "\n")
        if args == ["rev-parse", "HEAD"]:
            return Mock(stdout=head + "\n")
        raise AssertionError(f"unexpected git call: {args}")

    git = Mock(side_effect=fake_git)
    monkeypatch.setattr(clean_clone_check, "_git", git)
    return run, git, clone


def test_clone_uses_configured_origin_main_single_branch(
        monkeypatch, tmp_path):
    run, git, clone = _mock_clone_environment(monkeypatch, tmp_path)

    result = clean_clone_check.main()

    assert result == 0
    git.assert_any_call(
        ["config", "--get", "remote.origin.url"], cwd=clean_clone_check.REPO)
    clone_call = run.call_args_list[0]
    assert clone_call.args[0] == [
        "git", "clone", "--quiet", "--branch", "main", "--single-branch",
        ORIGIN_URL, str(clone)]
    assert clone_call.kwargs.get("capture_output") is True
    assert clone_call.kwargs.get("text") is True
    git.assert_any_call(["rev-parse", "HEAD"], cwd=clone)


def test_success_output_identifies_verified_remote_and_configured_clone(
        monkeypatch, tmp_path, capsys):
    _mock_clone_environment(monkeypatch, tmp_path)

    result = clean_clone_check.main()

    captured = capsys.readouterr()
    assert result == 0
    assert f"verified origin/main {REMOTE_SHA[:12]}" in captured.out
    assert "configured origin clone" in captured.out
    assert ORIGIN_URL not in captured.out + captured.err


def test_clean_clone_critical_suite_includes_this_regression_suite(
        monkeypatch, tmp_path):
    run, _, _ = _mock_clone_environment(monkeypatch, tmp_path)

    result = clean_clone_check.main()

    assert result == 0
    commands = [call.args[0] for call in run.call_args_list]
    critical = next(
        command for command in commands
        if "tests/test_phase4_v2_offline.py" in command)
    assert "tests/test_clean_clone_check.py" in critical


def test_clone_failure_is_controlled_and_does_not_leak_origin_url(
        monkeypatch, tmp_path, capsys):
    def fail_clone(command, *args, **kwargs):
        raise clean_clone_check.subprocess.CalledProcessError(
            128, command, stderr=f"fatal: could not read from {ORIGIN_URL}")

    run, _, _ = _mock_clone_environment(
        monkeypatch, tmp_path, run=Mock(side_effect=fail_clone))

    result = clean_clone_check.main()

    captured = capsys.readouterr()
    assert result != 0
    assert run.call_count == 1
    assert ORIGIN_URL not in captured.out + captured.err
    assert "Traceback" not in captured.out + captured.err


def test_cloned_head_mismatch_stops_before_venv_or_install(
        monkeypatch, tmp_path, capsys):
    run, _, _ = _mock_clone_environment(
        monkeypatch, tmp_path, head=OTHER_SHA)

    result = clean_clone_check.main()

    captured = capsys.readouterr()
    assert result == 2
    assert run.call_count == 1
    assert run.call_args_list[0].args[0][:2] == ["git", "clone"]
    assert ORIGIN_URL not in captured.out + captured.err
