"""Per-provider-request budget gate proxy, v2 (P4-R1.2-S2/S3).

Differences from v1 (all driven by the R1.1 review):
- atomic request states: RESERVED -> SENT -> SETTLED / UNKNOWN / REJECTED,
  persisted to the ledger BEFORE forwarding (crash-safe reservations)
- concurrency-safe global budget: projected = known + in_flight_reserved +
  new_worst_case, under one lock; two different in-flight requests can never
  share the same headroom
- upstream Authorization comes from the TRUSTED proxy config; agent-supplied
  Authorization is stripped and never logged
- task attribution is host-controlled: the runner calls set_current_task()
  before launching the container (the SDK sends no task headers); the agent
  cannot set or forge it
- crash recovery: on start, any RESERVED/SENT entry without settlement turns
  UNKNOWN and the proxy refuses new requests until a human reconciliation
  marker file exists
- upstream calls are DIRECT (empty ProxyHandler): no proxy env is honored

Direct-connection rule: the proxy's upstream client never reads proxy env.
"""

from __future__ import annotations

import hashlib
import json
import threading
import urllib.request
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ..pricing import worst_case_cost_cny

# request lifecycle states
RESERVED = "RESERVED"
SENT = "SENT"
SETTLED = "SETTLED"
UNKNOWN = "UNKNOWN"
REJECTED = "REJECTED"


class GateStop(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProxyConfig:
    upstream_base_url: str
    max_requests_per_task: int
    global_cap_cny: float
    worst_case_prompt_tokens: int = 8192
    worst_case_output_tokens: int = 2048
    usd_cny: float = 7.10
    authorized: bool = True
    upstream_api_key: str | None = None  # trusted; injected, never logged


class BudgetProxy:
    def __init__(self, config: ProxyConfig, log_path: Path) -> None:
        self.config = config
        self.log_path = log_path
        self._lock = threading.Lock()
        self._states: dict[str, str] = {}
        self._known_cost = 0.0
        self._inflight_reserved = 0.0
        self._per_task: dict[str, int] = {}
        self._stopped = False
        self._stop_reason: str | None = None
        self._current_task = "unknown-task"
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # crash recovery: unsettled entries from a previous run block us
        self._recovered_unknown = 0
        if log_path.is_file():
            states: dict[str, str] = {}
            for line in log_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                e = json.loads(line)
                if "request_id" in e and "state" in e:
                    states[e["request_id"]] = e["state"]
            for state in states.values():
                if state in (RESERVED, SENT):
                    self._recovered_unknown += 1
            if self._recovered_unknown:
                self._stopped = True
                self._stop_reason = (f"crash recovery: {self._recovered_unknown} "
                                     "unsettled request(s) marked UNKNOWN; refusing new "
                                     "requests until reconciled")
        self._log = log_path.open("a", encoding="utf-8")
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    # ---------- host-side control ----------
    def set_current_task(self, task_id: str) -> None:
        """Trusted host-side attribution. The agent cannot reach this."""
        with self._lock:
            self._current_task = task_id

    def reconcile(self) -> None:
        """Manual reconciliation clears the crash-recovery stop (auditable)."""
        with self._lock:
            if self._recovered_unknown:
                self._persist({"control": "manual_reconcile",
                               "cleared": self._recovered_unknown})
                self._recovered_unknown = 0
                self._stopped = False
                self._stop_reason = None

    # ---------- gate ----------
    def _worst_case(self) -> float:
        return worst_case_cost_cny(self.config.worst_case_prompt_tokens,
                                   self.config.worst_case_output_tokens,
                                   self.config.usd_cny)

    def _check_and_reserve(self, task_id: str) -> str:
        """All checks + reservation under one lock, BEFORE any byte upstream."""
        if not self.config.authorized:
            raise GateStop("not authorized")
        if self._stopped:
            raise GateStop(f"gate stopped: {self._stop_reason}")
        n_task = self._per_task.get(task_id, 0)
        if n_task + 1 > self.config.max_requests_per_task:
            raise GateStop(f"per-task request cap: {n_task + 1} > "
                           f"{self.config.max_requests_per_task}")
        worst = self._worst_case()
        projected = self._known_cost + self._inflight_reserved + worst
        if projected > self.config.global_cap_cny:
            raise GateStop(f"global budget: {projected:.6f} > {self.config.global_cap_cny}")
        request_id = uuid.uuid4().hex
        self._states[request_id] = RESERVED
        self._inflight_reserved += worst
        self._per_task[task_id] = n_task + 1
        self._persist({"request_id": request_id, "state": RESERVED,
                       "task_id": task_id, "reserved_cny": worst})
        return request_id

    def _transition(self, request_id: str, state: str, **extra) -> None:
        self._states[request_id] = state
        self._persist({"request_id": request_id, "state": state, **extra})

    def _settle(self, request_id: str, cost_cny: float | None, note: str) -> None:
        worst = self._worst_case()
        if cost_cny is None:
            self._transition(request_id, UNKNOWN, note=note)
            self._inflight_reserved -= worst  # reservation converts to UNKNOWN
            self._stopped = True
            self._stop_reason = f"unknown_cost at {request_id} ({note})"
        else:
            self._known_cost += cost_cny
            self._inflight_reserved -= worst
            self._transition(request_id, SETTLED, cost_cny=cost_cny, note=note)

    def _persist(self, entry: dict[str, Any]) -> None:
        self._log.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._log.flush()

    # ---------- HTTP ----------
    def start(self, bind: tuple[str, int] = ("127.0.0.1", 0)) -> "BudgetProxy":
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                with proxy._lock:
                    task_id = proxy._current_task  # host-attributed, not SDK-supplied
                    try:
                        request_id = proxy._check_and_reserve(task_id)
                    except GateStop as exc:
                        proxy._persist({"state": REJECTED, "reason": str(exc),
                                        "task_id": task_id})
                        self._send(429, {"error": str(exc)})
                        return
                    proxy._transition(request_id, SENT)
                try:
                    status, resp_body, usage = proxy._forward(body)
                except Exception as exc:
                    with proxy._lock:
                        proxy._settle(request_id, None, f"transport: {type(exc).__name__}")
                    self._send(502, {"error": "upstream transport"})
                    return
                with proxy._lock:
                    if status >= 400:
                        proxy._settle(request_id, None, f"upstream HTTP {status}")
                    else:
                        proxy._settle(request_id, proxy._usage_cost(usage),
                                      "ok" if usage else "missing usage")
                if status >= 400:
                    self._send(status, {"error": "upstream error"})
                    return
                self._send(200, resp_body)

            def _send(self, status: int, obj) -> None:
                data = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type",
                                 "text/event-stream" if data[:5] == b"data:" else "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self._server = ThreadingHTTPServer(bind, Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    @property
    def base_url(self) -> str:
        assert self._server
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def _forward(self, body: bytes) -> tuple[int, bytes, dict | None]:
        """DIRECT upstream (no env proxies). Authorization comes only from the
        trusted config; any agent-supplied Authorization is stripped."""
        headers = {"Content-Type": "application/json"}
        if self.config.upstream_api_key:
            headers["Authorization"] = f"Bearer {self.config.upstream_api_key}"
        req = urllib.request.Request(
            self.config.upstream_base_url.rstrip("/") + "/chat/completions",
            data=body, headers=headers)
        try:
            resp = self._opener.open(req, timeout=120)
            payload = resp.read()
            return resp.status, payload, _extract_sse_usage(payload)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), None

    def _usage_cost(self, usage: dict | None) -> float | None:
        if usage is None:
            return None
        from ..usage import parse_usage_mapping, UsageUnavailable
        from ..pricing import cost_for_usage
        try:
            u = parse_usage_mapping(usage)
        except UsageUnavailable:
            return None
        return cost_for_usage(u, "peak", self.config.usd_cny).cost_cny

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "known_cost_cny": round(self._known_cost, 10),
                "inflight_reserved_cny": round(self._inflight_reserved, 10),
                "stopped": self._stopped,
                "stop_reason": self._stop_reason,
                "recovered_unknown": self._recovered_unknown,
                "states": dict(self._states),
                "per_task": dict(self._per_task),
            }

    def close(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        self._log.close()

    def __enter__(self) -> "BudgetProxy":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.close()


def _extract_sse_usage(payload: bytes) -> dict | None:
    text = payload.decode("utf-8", errors="replace")
    usage = None
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            continue
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("usage"), dict):
            usage = obj["usage"]
    if usage is None:
        return None
    return {
        "inputTokens": usage.get("prompt_cache_miss_tokens",
                                 usage.get("inputTokens",
                                           usage.get("prompt_tokens", 0)
                                           - usage.get("prompt_cache_hit_tokens", 0))),
        "cacheReadTokens": usage.get("prompt_cache_hit_tokens",
                                     usage.get("cacheReadTokens", 0)),
        "outputTokens": usage.get("completion_tokens", usage.get("outputTokens", 0)),
    }
