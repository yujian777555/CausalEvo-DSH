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
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from .proxy_control import await_ack, publish_control

INTERNAL_NETWORK = "ceval-net"
PROVIDER_IMAGE = "python:3.11-slim"
TAPE_SERVER_PATH = Path(__file__).with_name("tape_server.py")


def _docker(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    import os
    env = dict(os.environ)
    env["MSYS_NO_PATHCONV"] = "1"  # never let MSYS rewrite /opt, /work etc.
    return subprocess.run(["docker", *args], capture_output=True, text=True,
                          timeout=timeout, env=env)


class ProxyContainer:
    """The budget-gate proxy as a container (P4-R1.2-S2, hardened in R1.3).

    Topology: agent containers live on the INTERNAL ceval-net and can reach
    only the proxy by name; the proxy is additionally attached to the default
    bridge for DIRECT upstream egress. Because the bridge makes port 8081
    reachable to sibling containers, ingress is protected by a per-run client
    token (CE_PROXY_CLIENT_TOKEN): only request builders that received the
    token from the host (the runner -> agent request JSON) can authenticate.
    The upstream API key is injected into the proxy's env only — never into
    agent containers. The control channel (scope attribution) is a generation-
    based handshake through the host-mounted ledger dir; agents never see it.
    """

    def __init__(self, *, upstream: str, ledger_dir: Path,
                 upstream_api_key: str | None = None,
                 max_requests_per_task: int = 8, cap_cny: float = 3.0,
                 worst_case_prompt_tokens: int = 65536,
                 worst_case_output_tokens: int = 2048,
                 allowed_model: str = "deepseek-flash",
                 network: str = INTERNAL_NETWORK) -> None:
        self.upstream = upstream
        self.ledger_dir = ledger_dir
        self.upstream_api_key = upstream_api_key
        self.max_requests_per_task = max_requests_per_task
        self.cap_cny = cap_cny
        self.worst_case_prompt_tokens = worst_case_prompt_tokens
        self.worst_case_output_tokens = worst_case_output_tokens
        self.allowed_model = allowed_model
        self.network = network
        self.name = f"ceval-proxy-{uuid.uuid4().hex[:10]}"
        # per-run ingress credential (distinct from the upstream API key)
        self.client_token = f"ce-proxy-{uuid.uuid4().hex}"
        self._generation = 0
        self._control_lock = threading.Lock()  # serial-scope enforcement

    @property
    def endpoint(self) -> str:
        return f"http://{self.name}:8081"

    def __enter__(self) -> "ProxyContainer":
        ensure_internal_network(self.network)
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        repo = Path(__file__).resolve().parents[3]
        parsed = urlparse(self.upstream)
        upstream_host = parsed.hostname or ""
        env = [
            "-e", f"CE_PROXY_UPSTREAM={self.upstream}",
            "-e", f"CE_PROXY_MAX_PER_TASK={self.max_requests_per_task}",
            "-e", f"CE_PROXY_CAP_CNY={self.cap_cny}",
            "-e", f"CE_PROXY_WC_PROMPT_TOKENS={self.worst_case_prompt_tokens}",
            "-e", f"CE_PROXY_WC_OUTPUT_TOKENS={self.worst_case_output_tokens}",
            "-e", f"CE_PROXY_ALLOWED_MODEL={self.allowed_model}",
            "-e", "CE_PROXY_AUTHORIZED=1",
            "-e", f"CE_PROXY_CLIENT_TOKEN={self.client_token}",
            # host-trusted upstream allowlist: exactly the configured host
            "-e", f"CE_PROXY_ALLOWED_HOSTS={upstream_host}",
        ]
        if parsed.scheme != "https":
            # offline fake providers only; live requires https
            env += ["-e", "CE_PROXY_ALLOW_INSECURE=1"]
        if self.upstream_api_key:
            env += ["-e", f"CE_PROXY_KEY={self.upstream_api_key}"]
        proc = _docker(
            "run", "-d", "--name", self.name,
            "--network", self.network,
            "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--memory", "256m", "--cpus", "0.5", "--pids-limit", "64",
            *env,
            "-v", f"{repo / 'src'}:/opt/src:ro",
            "-v", f"{repo / 'scripts' / 'proxy_server.py'}:/opt/proxy_server.py:ro",
            "-v", f"{self.ledger_dir.resolve()}:/ledger",
            PROVIDER_IMAGE, "python", "/opt/proxy_server.py",
        )
        if proc.returncode != 0:
            raise RuntimeError(f"proxy container failed: {proc.stderr.strip()}")
        # second NIC: default bridge for DIRECT upstream egress (agent net stays internal)
        proc2 = _docker("network", "connect", "bridge", self.name)
        if proc2.returncode != 0:
            _docker("rm", "-f", self.name)
            raise RuntimeError(f"proxy bridge connect failed: {proc2.stderr.strip()}")
        try:
            self._wait_ready()
            # bootstrap handshake: proves the shared ledger mount and the
            # control channel work BEFORE any agent is allowed to start
            self.set_current_scope("bootstrap/proxy-self-check")
        except Exception:
            _docker("rm", "-f", self.name, timeout=20)
            raise
        return self

    def _wait_ready(self, timeout_s: float = 45.0) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            alive = _docker("inspect", self.name, "--format", "{{.State.Running}}")
            if alive.returncode == 0 and alive.stdout.strip() == "true":
                logs = _docker("logs", self.name).stdout
                if "proxy up" in logs:
                    return
                if "Traceback" in logs or "Error" in logs:
                    raise RuntimeError(f"proxy crashed: {logs[-500:]}")
            time.sleep(0.4)
        raise RuntimeError(f"proxy {self.name} not ready in {timeout_s}s")

    def set_current_scope(self, scope: str) -> None:
        """Trusted attribution via the shared ledger dir (host-only channel;
        the agent network has no route to it). Generation-based handshake:
        clear stale ACK -> atomically publish -> wait for the proxy to echo
        the same generation. Any timeout/mismatch raises, so the runner must
        refuse to start the agent. Serial enforcement: one scope at a time;
        concurrent evaluations through one proxy are not supported."""
        with self._control_lock:
            self._generation += 1
            gen = self._generation
            publish_control(self.ledger_dir, gen, scope)
            await_ack(self.ledger_dir, gen, timeout_s=10.0)

    def set_current_task(self, task_id: str) -> None:
        """Backward-compatible alias (task-only scope)."""
        self.set_current_scope(task_id)

    def snapshot(self) -> dict:
        # ledger on the host mount is the durable source
        ledger = self.ledger_dir / "ledger.jsonl"
        entries = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines()
                   if l.strip()] if ledger.is_file() else []
        return {"ledger_entries": len(entries), "entries": entries}

    def __exit__(self, *exc) -> None:
        _docker("rm", "-f", self.name, timeout=20)


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

    def request_count(self) -> int:
        """Number of POSTs the provider actually received (upstream-side
        counter, recorded in /tape/requests.jsonl by tape_server)."""
        if self._tmp is None:
            return 0
        path = Path(self._tmp.name) / "requests.jsonl"
        if not path.is_file():
            return 0
        return sum(1 for l in path.read_text(encoding="utf-8").splitlines()
                   if l.strip())

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
