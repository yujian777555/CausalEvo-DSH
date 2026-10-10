"""Command executors.

DockerExecutor: the only path allowed for UNTRUSTED (model-produced) content.
Throwaway container per command: no network, read-only root, capped
memory/cpu/pids, non-root, per-task mount, hard wall-clock kill.

LocalTrustedExecutor: host subprocess for OFFLINE pipeline validation with
in-repo trusted content only (reference fixes, fake policies). It must never
run model-generated code — that boundary is documented in PHASE1_DESIGN.md
and enforced by policy review, not by the OS. Environment is minimized so no
secrets leak into the child process.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ExecResult:
    exit_code: int | None  # None when killed by timeout
    stdout: str
    stderr: str
    duration_ms: int
    executor: str
    timed_out: bool = False


class Executor(Protocol):
    kind: str

    def run(self, workdir: Path, argv: list[str], timeout_s: int) -> ExecResult: ...


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"],
                              capture_output=True, text=True, timeout=15)
        return proc.returncode == 0
    except Exception:
        return False


class DockerExecutor:
    kind = "docker"

    def __init__(self, image: str = "python:3.11-slim") -> None:
        self.image = image

    def run(self, workdir: Path, argv: list[str], timeout_s: int) -> ExecResult:
        name = f"ceval-{uuid.uuid4().hex[:12]}"
        cmd = [
            "docker", "run", "--rm", "--name", name,
            "--network", "none",
            "--read-only",
            "--memory", "256m", "--memory-swap", "256m",
            "--cpus", "1", "--pids-limit", "64",
            "--user", "65534:65534",
            "--workdir", "/work",
            "-v", f"{workdir.resolve()}:/work:ro",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-e", "PYTHONHASHSEED=0",
            self.image, *argv,
        ]
        started = time.monotonic()
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            subprocess.run(["docker", "kill", name], capture_output=True, timeout=15)
            try:
                stdout, stderr = proc.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
        duration = int((time.monotonic() - started) * 1000)
        return ExecResult(
            exit_code=None if timed_out else proc.returncode,
            stdout=stdout[-8000:], stderr=stderr[-8000:],
            duration_ms=duration, executor=self.kind, timed_out=timed_out,
        )


class LocalTrustedExecutor:
    """Host subprocess for TRUSTED offline content only. Minimal environment:
    no inherited credentials, fixed PYTHONHASHSEED, hard timeout."""

    kind = "local-trusted"

    def run(self, workdir: Path, argv: list[str], timeout_s: int) -> ExecResult:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        }
        started = time.monotonic()
        try:
            proc = subprocess.run(
                argv, cwd=workdir, env=env, capture_output=True, text=True,
                timeout=timeout_s,
            )
            return ExecResult(
                exit_code=proc.returncode, stdout=proc.stdout[-8000:],
                stderr=proc.stderr[-8000:],
                duration_ms=int((time.monotonic() - started) * 1000),
                executor=self.kind,
            )
        except subprocess.TimeoutExpired as exc:
            return ExecResult(
                exit_code=None, stdout=(exc.stdout or "")[-8000:] if isinstance(exc.stdout, str) else "",
                stderr=(exc.stderr or "")[-8000:] if isinstance(exc.stderr, str) else "",
                duration_ms=int((time.monotonic() - started) * 1000),
                executor=self.kind, timed_out=True,
            )


def default_executor(prefer_docker: bool = True) -> Executor:
    if prefer_docker and docker_available():
        return DockerExecutor()
    return LocalTrustedExecutor()
