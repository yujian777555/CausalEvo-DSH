"""Per-provider-request budget gate proxy (P4-R1.1-S3).

An HTTP proxy between the Harness runtime and the provider endpoint. EVERY
provider request passes: identity assignment + dedup, per-task cap check,
global worst-case reservation, authorization check — BEFORE forwarding. The
response settles actual usage; a request without parseable usage, an upstream
error after send, or a broken stream fails closed and stops all further
forwarding. The ledger is appended to disk after every event so a kill never
loses it.

Direct-connection rule (supplemental requirement): the proxy's upstream
client uses an explicit empty ProxyHandler — no HTTP(S)_PROXY env is honored
for provider traffic, and this is verified by tests.
"""

from __future__ import annotations

import hashlib
import json
import threading
import urllib.request
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ..pricing import worst_case_cost_cny


class GateStop(RuntimeError):
    pass


@dataclass(slots=True)
class ProxyConfig:
    upstream_base_url: str
    max_requests_per_task: int
    global_cap_cny: float
    worst_case_prompt_tokens: int = 8192
    worst_case_output_tokens: int = 2048
    usd_cny: float = 7.10
    authorized: bool = True  # call sites pass the double-gate result


@dataclass(slots=True)
class RequestLedger:
    entries: list[dict[str, Any]] = field(default_factory=list)
    known_cost_cny: float = 0.0
    unknown_spend: int = 0
    stopped: bool = False
    stop_reason: str | None = None


class BudgetProxy:
    """Thread-safe per-request gate. `log_path` is appended after EVERY event."""

    def __init__(self, config: ProxyConfig, log_path: Path) -> None:
        self.config = config
        self.log_path = log_path
        self.ledger = RequestLedger()
        self._lock = threading.Lock()
        self._inflight: set[str] = set()
        self._seen_bodies: set[str] = set()
        self._per_task: dict[str, int] = {}
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = log_path.open("a", encoding="utf-8")
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    # ---------- gate ----------
    def _worst_case(self) -> float:
        return worst_case_cost_cny(self.config.worst_case_prompt_tokens,
                                   self.config.worst_case_output_tokens,
                                   self.config.usd_cny)

    def _check(self, task_id: str, body_hash: str) -> str:
        """All checks BEFORE any byte goes upstream. Returns request_id."""
        if not self.config.authorized:
            raise GateStop("not authorized")
        if self.ledger.stopped:
            raise GateStop(f"gate stopped: {self.ledger.stop_reason}")
        if body_hash in self._inflight:
            raise GateStop("duplicate in-flight request body (identity collision)")
        n_task = self._per_task.get(task_id, 0)
        if n_task + 1 > self.config.max_requests_per_task:
            raise GateStop(f"per-task request cap: {n_task + 1} > "
                           f"{self.config.max_requests_per_task}")
        projected = self.ledger.known_cost_cny + self._worst_case()
        if projected > self.config.global_cap_cny:
            raise GateStop(f"global budget: {projected:.4f} > {self.config.global_cap_cny}")
        return uuid.uuid4().hex

    def _settle(self, request_id: str, cost_cny: float | None, note: str) -> None:
        """Settle a completed/failed request. None = usage unknown -> stop."""
        entry = {"request_id": request_id, "cost_cny": cost_cny, "note": note}
        self.ledger.entries.append(entry)
        if cost_cny is None:
            self.ledger.unknown_spend += 1
            self.ledger.stopped = True
            self.ledger.stop_reason = f"unknown_cost at {request_id} ({note})"
        else:
            self.ledger.known_cost_cny += cost_cny
        self._persist(entry)

    def _persist(self, entry: dict[str, Any]) -> None:
        self._log.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._log.flush()

    # ---------- HTTP ----------
    def start(self) -> "BudgetProxy":
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                task_id = self.headers.get("X-Task-Id", "unknown-task")
                body_hash = hashlib.sha256(body).hexdigest()
                with proxy._lock:
                    try:
                        request_id = proxy._check(task_id, body_hash)
                        proxy._inflight.add(body_hash)
                        proxy._per_task[task_id] = proxy._per_task.get(task_id, 0) + 1
                    except GateStop as exc:
                        proxy._persist({"rejected": body_hash, "reason": str(exc)})
                        self._send(429, {"error": str(exc)})
                        return
                try:
                    status, resp_body, usage = proxy._forward(body)
                except Exception as exc:
                    with proxy._lock:
                        proxy._inflight.discard(body_hash)
                        proxy._settle(request_id, None, f"transport: {exc}")
                    self._send(502, {"error": f"upstream transport: {exc}",
                                     "request_id": request_id})
                    return
                with proxy._lock:
                    proxy._inflight.discard(body_hash)
                    if status >= 400:
                        # request WAS sent and rejected upstream: billing unknown
                        proxy._settle(request_id, None, f"upstream HTTP {status}")
                    else:
                        proxy._settle(request_id, proxy._usage_cost(usage),
                                      "ok" if usage else "missing usage")
                if status >= 400:
                    self._send(status, {"error": "upstream error", "request_id": request_id})
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

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    @property
    def base_url(self) -> str:
        assert self._server
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def _forward(self, body: bytes) -> tuple[int, bytes, dict | None]:
        """Forward to upstream DIRECT (no env proxies). Returns
        (status, body, usage_dict|None)."""
        req = urllib.request.Request(
            self.config.upstream_base_url.rstrip("/") + "/chat/completions",
            data=body, headers={"Content-Type": "application/json"})
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
        return {
            "known_cost_cny": round(self.ledger.known_cost_cny, 10),
            "unknown_spend": self.ledger.unknown_spend,
            "stopped": self.ledger.stopped,
            "stop_reason": self.ledger.stop_reason,
            "requests": len(self.ledger.entries),
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
    """Final SSE chunk's usage; cacheReadTokens shape already matches our
    parser aliases (inputTokens etc. via prompt_cache_*)."""
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
            usage = obj["usage"]  # last usage wins (settled frame)
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
