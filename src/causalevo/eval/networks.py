"""Controlled-egress plumbing for the container world (G1).

The agent container and its (fake) provider container share an INTERNAL
Docker network: no NAT to the outside, no metadata service, no host reach.
The only thing the agent can talk to is the provider endpoint on that
network. Live mode would replace the provider container with an egress-
restricted proxy to api.deepseek.com (future work, documented).
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

INTERNAL_NETWORK = "ceval-net"
PROVIDER_IMAGE = "python:3.11-slim"
TAPE_SERVER_PATH = Path(__file__).with_name("tape_server.py")


def _docker(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def ensure_internal_network(name: str = INTERNAL_NETWORK) -> str:
    """Create the internal (no external egress) network if absent; return name."""
    proc = _docker("network", "inspect", name, "--format", "{{.Id}}")
    if proc.returncode == 0 and proc.stdout.strip():
        return name
    created = _docker("network", "create", "--internal", name)
    if created.returncode != 0:
        raise RuntimeError(f"docker network create failed: {created.stderr.strip()}")
    return name


class ProviderContainer:
    """A tape-serving fake provider running INSIDE the internal network."""

    def __init__(self, tape: dict, network: str = INTERNAL_NETWORK,
                 image: str = PROVIDER_IMAGE) -> None:
        self.tape = tape
        self.network = network
        self.image = image
        self.name = f"ceval-provider-{uuid.uuid4().hex[:10]}"
        self._tmp: tempfile.TemporaryDirectory | None = None

    @property
    def endpoint(self) -> str:
        return f"http://{self.name}:8080"

    def __enter__(self) -> "ProviderContainer":
        ensure_internal_network(self.network)
        self._tmp = tempfile.TemporaryDirectory(prefix="ceval-tape-")
        tmp = Path(self._tmp.name)
        (tmp / "tape.json").write_text(json.dumps(self.tape), encoding="utf-8")
        proc = _docker(
            "run", "-d", "--name", self.name,
            "--network", self.network,
            "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--memory", "128m", "--cpus", "0.5", "--pids-limit", "32",
            # rw: the provider appends observed tool results to
            # /tape/observations.jsonl for host-side assertions
            "-v", f"{tmp.resolve()}:/tape",
            "-v", f"{TAPE_SERVER_PATH.resolve()}:/opt/tape_server.py:ro",
            self.image, "python", "/opt/tape_server.py", "/tape/tape.json",
        )
        if proc.returncode != 0:
            raise RuntimeError(f"provider container failed to start: {proc.stderr.strip()}")
        self._wait_ready()
        return self

    def _wait_ready(self, timeout_s: float = 30.0) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            alive = _docker("inspect", self.name, "--format", "{{.State.Running}}")
            if alive.returncode != 0 or alive.stdout.strip() != "true":
                logs = _docker("logs", self.name).stderr
                raise RuntimeError(f"provider container died: {logs[-500:]}")
            logs = _docker("logs", self.name).stderr
            if "Traceback" in logs:
                raise RuntimeError(f"provider container crashed: {logs[-500:]}")
            return  # running with clean logs; the server binds at startup
        raise RuntimeError(f"provider container {self.name} not ready within {timeout_s}s")

    def tool_results(self) -> list[str]:
        """Tool-result contents observed by the provider (readback for tests)."""
        if self._tmp is None:
            return []
        path = Path(self._tmp.name) / "observations.jsonl"
        if not path.is_file():
            return []
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line)["content"])
        return out

    def __exit__(self, *exc) -> None:
        _docker("rm", "-f", self.name, timeout=20)
        if self._tmp is not None:
            self._tmp.cleanup()
