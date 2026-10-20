"""Harness agent bridge: real DeepSeek-Harness runtime driving one task.

Two execution worlds:
- HostHarnessRunner: runtime on the host. FOR PROBES/DEBUG ONLY — the agent's
  file READS are not confined (proved 2026-10-10: fs-sandbox limits writes,
  reads pass through; a scripted read returned a host canary verbatim).
- ContainerHarnessRunner: the whole runtime runs inside a throwaway Docker
  container with ONLY the per-task workspace mounted — the agent's file
  reads/writes/searches are confined by the container boundary, which is
  objectively testable. This is the only runner allowed for task execution.

Provider selection: `fake` (local FakeProvider; offline, zero cost) or `live`
(real DeepSeek API). Live requires BOTH DEEPSEEK_API_KEY and the explicit
one-off authorization env CE_DSH_LIVE_AUTH=phase1-pilot (a Planner-issued
flag), otherwise the runner refuses before any socket is opened.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..usage import UsageRecord, UsageUnavailable, extract_request_usages, extract_settled_usage
from .runtime_budget import BudgetStop, RuntimeBudget
from .task_spec import TaskSpec


def _count_unmetered_attempts(events: list[dict[str, Any]]) -> int:
    """assistant/attempt events with NO settled usage = requests the runtime
    sent but we cannot meter (e.g. HTTP 500 before any token was processed).
    Billing is unknown — each one is an unknown_spend_attempt."""
    n = 0
    for e in events:
        if e.get("type") != "assistant/attempt":
            continue
        data = e.get("data")
        if not isinstance(data, dict):
            n += 1
            continue
        try:
            from ..usage import _usage_from_data
            if _usage_from_data(data) is None:
                n += 1
        except UsageUnavailable:
            n += 1
    return n


def _settle_budget(budget: RuntimeBudget, events: list[dict[str, Any]],
                   price_tier: str, usd_cny: float) -> int:
    """Settle every distinct provider request's settled usage into the ledger.
    Returns the number of unmetered attempts recorded as unknown spend.
    May raise BudgetStop (output/cost cap) which the caller converts to a
    budget_stop outcome."""
    usages = extract_request_usages(events)
    for usage in usages:
        budget.after_provider_request(usage, price_tier=price_tier, usd_cny=usd_cny)
    unmetered = _count_unmetered_attempts(events)
    for _ in range(unmetered):
        budget.record_unknown_attempt()
    return unmetered

LIVE_AUTH_ENV = "CE_DSH_LIVE_AUTH"
LIVE_AUTH_VALUE = "phase1-pilot"


class _WallClockExpired(RuntimeError):
    pass


@dataclass(slots=True)
class AgentRunOutcome:
    task_id: str
    policy_id: str
    finish_reason: str | None
    final_response_sha16: str | None
    failure_kind: str  # none|provider_error|timeout|budget_stop|transport|protocol|invalid|unknown_cost
    budget_stop_reason: str | None
    usage: UsageRecord | None
    ledger: dict[str, Any]
    events_slim: list[dict[str, Any]]
    duration_ms: int
    runner: str
    provider_kind: str  # fake | live
    model_invoked: bool = True


def slim_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Redacted event graph: structure + per-event hashes, never text bodies."""
    slim = []
    for e in events:
        data = e.get("data") or {}
        entry: dict[str, Any] = {"seq": e.get("seq"), "type": e.get("type")}
        if isinstance(data, dict):
            for k in ("turn", "step"):
                if k in data:
                    entry[k] = data[k]
            usage = data.get("usage")
            if isinstance(usage, dict):
                entry["usage"] = {k: v for k, v in usage.items() if isinstance(v, int)}
            tool = data.get("tool") or data.get("name")
            if isinstance(tool, str):
                entry["tool"] = tool
        entry["sha16"] = hashlib.sha256(
            json.dumps(e, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]
        slim.append(entry)
    return slim


def _response_hash(text: str) -> str | None:
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class _BudgetWatcher:
    """Reacts to session notifications mid-run; raises BudgetStop to abort."""

    def __init__(self, budget: RuntimeBudget) -> None:
        self.budget = budget

    def __call__(self, notification) -> None:
        self.budget.check_wall_time()
        if notification.method != "session.event":
            return
        event = notification.payload.get("event")
        if not isinstance(event, dict):
            return
        etype = event.get("type")
        if etype == "tool/call":
            self.budget.before_tool_call(str((event.get("data") or {}).get("tool", "?")))


class HostHarnessRunner:
    """DSH runtime on the host. Probe/debug only — NOT an isolation boundary."""

    kind = "host"

    def __init__(self, *, base_url: str, api_key: str, patch_path: Path,
                 model: str, reasoning_effort: str | None, max_tokens: int,
                 provider_kind: str = "fake") -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.patch_path = patch_path
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.max_tokens = max_tokens
        self.provider_kind = provider_kind

    def run_task(
        self,
        spec: TaskSpec,
        workspace: Path,
        policy_id: str,
        budget: RuntimeBudget,
        dsh_home: Path,
    ) -> AgentRunOutcome:
        from deepseek_harness import DeepSeekHarness, DeepSeekHarnessConfig

        dsh_home.mkdir(parents=True, exist_ok=True)
        watcher = _BudgetWatcher(budget)
        started = time.monotonic()
        finish_reason: str | None = None
        failure_kind = "none"
        final_text = ""
        events: list[dict[str, Any]] = []
        try:
            with DeepSeekHarness(DeepSeekHarnessConfig(
                provider="deepseek-official", model=self.model,
                reasoning_effort=self.reasoning_effort, max_tokens=self.max_tokens,
                cwd=str(workspace), dsh_home=str(dsh_home),
                patches=(str(self.patch_path),),
                initialize_timeout_seconds=60.0, request_timeout_seconds=180.0,
                base_url=self.base_url, api_key=self.api_key,
            )) as harness:
                budget.before_provider_request(reserved_cost_cny=0.0)
                session = harness.start_session(f"task-{spec.task_id}-{uuid.uuid4().hex[:6]}")
                result = session.run(spec.instructions, on_notification=watcher)
                finish_reason = result.finish_reason
                final_text = result.final_response
                events = [dict(e) for e in result.events]
        except BudgetStop as exc:
            failure_kind = "budget_stop"
            budget_stop_reason = exc.reason
            duration = int((time.monotonic() - started) * 1000)
            return self._outcome(spec, policy_id, finish_reason, final_text, failure_kind,
                                 budget_stop_reason, events, budget, duration)
        except Exception as exc:
            failure_kind = "transport" if "Transport" in type(exc).__name__ else "provider_error"
            duration = int((time.monotonic() - started) * 1000)
            return self._outcome(spec, policy_id, finish_reason, final_text, failure_kind,
                                 f"{type(exc).__name__}: {exc}", events, budget, duration)
        duration = int((time.monotonic() - started) * 1000)
        return self._outcome(spec, policy_id, finish_reason, final_text, failure_kind,
                             None, events, budget, duration)

    def _outcome(self, spec, policy_id, finish_reason, final_text, failure_kind,
                 budget_stop_reason, events, budget, duration) -> AgentRunOutcome:
        usage: UsageRecord | None = None
        unmetered = 0
        try:
            if events:
                usage = extract_settled_usage(events)
                unmetered = _settle_budget(budget, events, price_tier="off_peak", usd_cny=7.10)
        except UsageUnavailable:
            usage = None
            unmetered = _count_unmetered_attempts(events)
            for _ in range(unmetered):
                budget.record_unknown_attempt()
        except BudgetStop as exc:
            failure_kind = "budget_stop"
            budget_stop_reason = budget_stop_reason or exc.reason
        if unmetered and failure_kind == "none":
            failure_kind = "unknown_cost"
            budget_stop_reason = budget_stop_reason or (
                f"{unmetered} provider attempt(s) without settled usage")
        return AgentRunOutcome(
            task_id=spec.task_id, policy_id=policy_id, finish_reason=finish_reason,
            final_response_sha16=_response_hash(final_text),
            failure_kind=failure_kind, budget_stop_reason=budget_stop_reason,
            usage=usage, ledger=budget.snapshot(), events_slim=slim_events(events),
            duration_ms=duration, runner=self.kind, provider_kind=self.provider_kind,
        )


def require_live_authorization(env: dict[str, str] | None = None) -> None:
    """Live calls need BOTH the API key AND the explicit one-off flag."""
    env = os.environ if env is None else env
    if not env.get("DEEPSEEK_API_KEY", "").strip():
        raise PermissionError("live mode requires DEEPSEEK_API_KEY")
    if env.get(LIVE_AUTH_ENV) != LIVE_AUTH_VALUE:
        raise PermissionError(
            f"live mode requires {LIVE_AUTH_ENV}={LIVE_AUTH_VALUE} (one-off Planner "
            "authorization); refusing before any network access"
        )


class ContainerHarnessRunner:
    """Runs the whole DSH runtime inside a throwaway container.

    Only the per-task workspace is mounted (/work, rw). Session events stream
    out as JSONL on stdout; the budget watcher applies mid-run, and on
    BudgetStop the container is hard-killed (docker kill), so overspend stops
    at the boundary instead of being discovered afterwards.
    """

    kind = "container"

    def __init__(self, *, image: str, patch_path: Path, model: str,
                 reasoning_effort: str | None, max_tokens: int,
                 provider_kind: str = "fake",
                 provider_endpoint: str | None = None,
                 network: str = "ceval-net",
                 agent_api_key: str | None = None) -> None:
        """Container Security Profile v2: read-only rootfs, tmpfs /tmp,
        cap-drop ALL, no-new-privileges, internal network only. The sole
        reachable endpoint is `provider_endpoint` on the internal network.

        agent_api_key: the key handed to the agent container. When a budget
        proxy fronts the provider, this is a placeholder (the proxy injects
        the trusted key upstream); the real key never enters agent space."""
        self.image = image
        self.patch_path = patch_path
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.max_tokens = max_tokens
        self.provider_kind = provider_kind
        self.provider_endpoint = provider_endpoint
        self.network = network
        self.agent_api_key = agent_api_key

    def run_task(
        self,
        spec: TaskSpec,
        workspace: Path,
        policy_id: str,
        budget: RuntimeBudget,
        api_key: str,
        extra_prompt: str | None = None,
    ) -> AgentRunOutcome:
        if self.provider_kind == "live" and not self.provider_endpoint:
            raise PermissionError(
                "live runs must go through the budget proxy: provider_endpoint is "
                "required (no direct-to-API fallback exists)")
        name = f"ceval-agent-{uuid.uuid4().hex[:12]}"
        prompt = spec.instructions
        if extra_prompt:
            prompt = f"{spec.instructions}\n\nADDITIONAL INSTRUCTION (retry policy): {extra_prompt}"
        request = {
            "session_id": f"task-{spec.task_id}-{uuid.uuid4().hex[:6]}",
            "prompt": prompt,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "max_tokens": self.max_tokens,
            "patch_yml": self.patch_path.read_text(encoding="utf-8"),
            "base_url": self.provider_endpoint,
            "api_key": self.agent_api_key or api_key,
            "request_timeout_s": max(60, budget.wall_time_s),
        }
        cmd = [
            "docker", "run", "--rm", "-i", "--name", name,
            # Container Security Profile v2 (G1)
            "--network", self.network,
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            # the runtime's plugin loader unpacks and mmaps native sidecars
            # (koffi/ripgrep) from its package cache; it needs exec. Scope is
            # limited to this private tmpfs; the model has no shell to abuse it.
            "--tmpfs", "/home/agent/.cache:rw,exec,nosuid,size=64m",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--memory", "768m", "--memory-swap", "768m",
            "--cpus", "1", "--pids-limit", "128",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-v", f"{workspace.resolve()}:/work",
            self.image,
        ]
        started = time.monotonic()
        events: list[dict[str, Any]] = []
        finish_reason: str | None = None
        final_text = ""
        failure_kind = "none"
        stop_reason: str | None = None
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        assert proc.stdin and proc.stdout
        proc.stdin.write(json.dumps(request))
        proc.stdin.close()

        # Reader thread -> queue, so the budget wall-clock is enforced even
        # when the provider hangs and no output is streaming.
        import queue as _queue
        import threading as _threading

        lines: _queue.Queue[str | None] = _queue.Queue()

        def _reader() -> None:
            for ln in proc.stdout:
                lines.put(ln)
            lines.put(None)

        _threading.Thread(target=_reader, daemon=True).start()
        final: dict[str, Any] | None = None
        deadline = started + budget.wall_time_s
        try:
            budget.before_provider_request(reserved_cost_cny=0.0)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise _WallClockExpired("wall_time exceeded while waiting for output")
                try:
                    line = lines.get(timeout=min(remaining, 0.5))
                except _queue.Empty:
                    continue
                if line is None:
                    break  # EOF
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "event":
                    event = msg.get("event")
                    if isinstance(event, dict):
                        events.append(event)
                        if event.get("type") == "tool/call":
                            budget.before_tool_call("?")
                elif msg.get("type") == "final":
                    final = msg
                    break
        except _WallClockExpired as exc:
            failure_kind = "timeout"
            stop_reason = str(exc)
            subprocess.run(["docker", "kill", name], capture_output=True, timeout=15)
        except BudgetStop as exc:
            failure_kind = "budget_stop"
            stop_reason = exc.reason
            subprocess.run(["docker", "kill", name], capture_output=True, timeout=15)
        finally:
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        duration = int((time.monotonic() - started) * 1000)
        if final is None and failure_kind == "none":
            # abnormal termination: no final message at all
            rc = proc.returncode
            if rc not in (0, None):
                failure_kind = "transport"
                stop_reason = f"container exited rc={rc} without final message"
            else:
                failure_kind = "protocol"
                stop_reason = "clean exit but no final message (protocol violation)"
        elif final is not None:
            if not final.get("ok"):
                failure_kind = "provider_error" if failure_kind == "none" else failure_kind
                stop_reason = stop_reason or final.get("error")
            else:
                finish_reason = final.get("finish_reason")
                final_text = final.get("final_response") or ""
                final_events = final.get("events")
                if isinstance(final_events, list) and final_events:
                    events = [e for e in final_events if isinstance(e, dict)]
        usage: UsageRecord | None = None
        unmetered = 0
        try:
            if events:
                usage = extract_settled_usage(events)
                unmetered = _settle_budget(budget, events, price_tier="off_peak", usd_cny=7.10)
        except UsageUnavailable:
            usage = None
            unmetered = _count_unmetered_attempts(events)
            for _ in range(unmetered):
                budget.record_unknown_attempt()
        except BudgetStop as exc:
            if failure_kind == "none":
                failure_kind = "budget_stop"
            stop_reason = stop_reason or exc.reason
        if unmetered and failure_kind == "none":
            failure_kind = "unknown_cost"
            stop_reason = stop_reason or (
                f"{unmetered} provider attempt(s) without settled usage")
        return AgentRunOutcome(
            task_id=spec.task_id, policy_id=policy_id, finish_reason=finish_reason,
            final_response_sha16=_response_hash(final_text),
            failure_kind=failure_kind, budget_stop_reason=stop_reason,
            usage=usage, ledger=budget.snapshot(), events_slim=slim_events(events),
            duration_ms=duration, runner=self.kind, provider_kind=self.provider_kind,
        )
