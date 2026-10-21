"""Per-provider-request budget gate proxy, v3 (P4-R1.3 S1-S4).

v2 -> v3 changes (all driven by the R1.2 independent review):
- FULL ledger replay on start: every request_id's final state, all SETTLED
  cost, per-scope request counts and unresolved UNKNOWNs are reconstructed;
  corrupted/truncated/contradictory ledgers fail CLOSED (no budget resets).
- Evaluation-scope attribution (experiment_run_id/task_id/seed/arm) replaces
  bare task_id bucketing; retries share their evaluation row's scope.
- Ingress client authentication: when config.client_token is set, requests
  without the exact bearer token are rejected (401) BEFORE any upstream byte.
  The token is distinct from the upstream API key and never logged.
- Request-bound enforcement: path, method, Content-Length, JSON shape, model
  and max_tokens are validated against the frozen worst-case reservation
  BEFORE reserving or forwarding; violations are audited and rejected.
- Upstream allowlist: only pre-approved hosts (live: api.deepseek.com);
  https required unless the host-trusted config opts into an offline fake.
- _persist flushes AND fsyncs (crash-grade durability for reservations).

Kept from v2: atomic RESERVED -> SENT -> SETTLED/UNKNOWN/REJECTED lifecycle
persisted BEFORE forwarding; concurrency-safe global budget under one lock;
trusted upstream Authorization injection (agent-supplied auth stripped);
DIRECT upstream (empty ProxyHandler, no proxy env honored).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..pricing import worst_case_cost_cny

# request lifecycle states
RESERVED = "RESERVED"
SENT = "SENT"
SETTLED = "SETTLED"
UNKNOWN = "UNKNOWN"
REJECTED = "REJECTED"

# legal forward transitions during replay (None = request_id not seen yet)
_REPLAY_TRANSITIONS: dict[str | None, frozenset[str]] = {
    None: frozenset({RESERVED}),
    RESERVED: frozenset({SENT, UNKNOWN}),
    SENT: frozenset({SETTLED, UNKNOWN}),
}


class GateStop(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProxyConfig:
    upstream_base_url: str
    max_requests_per_task: int  # per evaluation SCOPE (kept name for compat)
    global_cap_cny: float
    worst_case_prompt_tokens: int = 8192
    worst_case_output_tokens: int = 2048
    usd_cny: float = 7.10
    authorized: bool = True
    upstream_api_key: str | None = None  # trusted; injected, never logged
    # P4-R1.3 S4: ingress client credential (distinct from the upstream key).
    # None disables ingress auth (host-side unit tests only); the container
    # deployment ALWAYS sets a per-run token.
    client_token: str | None = None
    # P4-R1.3 S4/S5: request-bound enforcement
    allowed_model: str | None = "deepseek-flash"
    max_body_bytes: int | None = None  # default: worst_case_prompt_tokens
    # P4-R1.3 S4: upstream allowlist (host-trusted; agents cannot influence)
    allowed_upstream_hosts: tuple[str, ...] = ("api.deepseek.com",)
    allow_insecure_upstream: bool = False  # http only for offline fakes

    def __post_init__(self) -> None:
        parsed = urlparse(self.upstream_base_url)
        host = parsed.hostname or ""
        if host not in self.allowed_upstream_hosts:
            raise ValueError(
                f"upstream host {host!r} not in allowed_upstream_hosts "
                f"{self.allowed_upstream_hosts!r}")
        if parsed.scheme != "https" and not self.allow_insecure_upstream:
            raise ValueError(
                "upstream must use https; allow_insecure_upstream=True is only "
                "acceptable for host-trusted offline fake providers")

    @property
    def effective_max_body_bytes(self) -> int:
        # prompt_tokens <= body bytes (every token is at least one byte in the
        # request JSON), so bounding the body bounds the prompt conservatively.
        return self.max_body_bytes or self.worst_case_prompt_tokens


# frozen output-limit protocol (P4-R1.4 P0-A): a request must carry EXACTLY
# ONE effective output token limit. The DeepSeek chat-completions schema
# accepts `max_tokens` (current) and `max_completion_tokens` (alias); both may
# co-occur ONLY when identical (proven-consistent), otherwise the request is
# ambiguous and rejected. The value must be a strict positive int (bool/float/
# str/null/missing/negative/zero are all illegal) and must not exceed the
# proxy's worst-case reservation. All rejections happen before reservation
# and before any upstream byte.
_ABSENT = object()


def _strict_positive_int(v: Any) -> bool:
    """Strict schema integer: real int, never bool (bool is an int subclass),
    positive. Floats/strings/null never pass — even when Python's cross-type
    equality (True == 1, 256.0 == 256) would call them equal to a valid int."""
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def _output_limit_problem(obj: dict) -> str | None:
    """None = valid; otherwise a short audit-safe reason (no prompt content)."""
    mt = obj.get("max_tokens", _ABSENT)
    mct = obj.get("max_completion_tokens", _ABSENT)
    if mt is _ABSENT and mct is _ABSENT:
        return "output_limit_missing"
    # P4-R1.5 P0-A: validate EVERY supplied field independently FIRST; only
    # then may the (now guaranteed strict-int) values be compared.
    for v in (mt, mct):
        if v is _ABSENT:
            continue
        if not _strict_positive_int(v):
            return "output_limit_illegal"
    if mt is not _ABSENT and mct is not _ABSENT and mt != mct:
        return "output_limit_ambiguous"
    return None


def _validate_output_limit(obj: dict) -> int | None:
    """The single effective output limit, or None when the request is illegal."""
    if _output_limit_problem(obj) is not None:
        return None
    mt = obj.get("max_tokens", _ABSENT)
    return mt if mt is not _ABSENT else obj["max_completion_tokens"]


def _valid_amount(v: Any) -> bool:
    """Ledger monetary amounts: JSON number, finite, nonnegative, never bool,
    and representable in the ledger's float accounting representation.

    TOTAL for any json-decoded value (P4-R1.6 P1-A): bool is an int subclass;
    NaN/Inf are non-finite; and math.isfinite(10**400) / float(10**400) raise
    OverflowError, so the float-conversion itself is attempted under a guard —
    any failure or non-finite result rejects the amount WITHOUT leaking
    OverflowError / ValueError / TypeError into proxy construction."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    if v < 0:
        return False
    try:
        f = float(v)
    except (OverflowError, ValueError, TypeError):
        return False
    return math.isfinite(f)


class BudgetProxy:
    def __init__(self, config: ProxyConfig, log_path: Path) -> None:
        self.config = config
        self.log_path = log_path
        self._lock = threading.Lock()
        self._states: dict[str, str] = {}
        self._known_cost = 0.0
        self._inflight_reserved = 0.0
        self._per_scope: dict[str, int] = {}
        self._stopped = False
        self._stop_reason: str | None = None
        self._current_scope = "unknown-scope"
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._ledger_corrupt = False
        self._recovered_unknown = 0
        self._unresolved_unknown: set[str] = set()
        self._request_scope: dict[str, str] = {}  # request_id -> evaluation scope
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if log_path.is_file():
            self._replay(log_path)
        self._log = log_path.open("a", encoding="utf-8")
        if self._recovered_unknown and not self._ledger_corrupt:
            self._persist({"control": "crash_recovery",
                           "unknown_request_ids": sorted(self._unresolved_unknown)})
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    # ---------- ledger replay (P4-R1.3 S2) ----------
    def _replay(self, log_path: Path) -> None:
        """Rebuild full proxy state from the append-only ledger. Any structural
        inconsistency marks the ledger corrupt and stops the gate (fail-closed):
        budgets must NEVER silently reset after a restart."""
        # rid -> [state, scope, reserved_cny, settled_cost]
        states: dict[str, list[Any]] = {}
        corrupt: str | None = None
        reconciled: set[str] = set()
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        for lineno, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                corrupt = f"line {lineno}: invalid JSON (truncated/corrupt ledger)"
                break
            except ValueError as exc:
                # e.g. an integer literal exceeding the runtime's configured
                # int-str digit limit (runtimes that enforce one): a numeric
                # parser failure is ledger corruption, not an escaping exception
                corrupt = (f"line {lineno}: numeric parse failure "
                           f"({type(exc).__name__})")
                break
            if not isinstance(e, dict):
                corrupt = f"line {lineno}: entry is not a JSON object"
                break
            control = e.get("control")
            if control is not None:
                if control != "manual_reconcile":
                    continue  # crash_recovery etc.: audit-only
                # P4-R1.4 P0-B: replay validates every reconcile event. Only
                # explicitly listed request ids may be cleared; each id must
                # exist, be in an unresolved state, and belong to the event's
                # scope (cross-scope events must use scope=None + reason).
                cleared = e.get("cleared")
                escope = e.get("scope")
                if (not isinstance(cleared, list)
                        or not all(isinstance(r, str) for r in cleared)):
                    corrupt = (f"line {lineno}: malformed reconcile (cleared "
                               "must be a list of request ids)")
                    break
                if escope is not None and not isinstance(escope, str):
                    corrupt = f"line {lineno}: malformed reconcile scope"
                    break
                if escope is None and not e.get("reason"):
                    corrupt = (f"line {lineno}: cross-scope reconcile without "
                               "operator reason")
                    break
                bad = None
                for rid in cleared:
                    prev_r = states.get(rid)
                    if prev_r is None:
                        bad = f"reconcile references unknown request id {rid}"
                        break
                    if prev_r[0] not in (RESERVED, SENT, UNKNOWN):
                        bad = f"reconcile of non-pending request {rid}"
                        break
                    if escope is not None and prev_r[1] != escope:
                        bad = (f"reconcile scope {escope!r} overreaches request "
                               f"{rid} (scope {prev_r[1]!r})")
                        break
                if bad:
                    corrupt = f"line {lineno}: {bad}"
                    break
                reconciled |= set(cleared)
                continue
            state = e.get("state")
            rid = e.get("request_id")
            if state == REJECTED and rid is None:
                continue  # ingress/gate rejection audit
            if not isinstance(rid, str) or state not in (
                    RESERVED, SENT, SETTLED, UNKNOWN, REJECTED):
                corrupt = f"line {lineno}: malformed entry (request_id/state)"
                break
            prev = states.get(rid)
            cur = prev[0] if prev else None
            if prev is not None and state == cur:
                # duplicate event: idempotent ONLY when every semantic field
                # is strictly valid AND identical (P4-R1.5 P0-B); NaN/bool/
                # negative/conflicting values corrupt the ledger — never a
                # tolerance comparison on unvalidated numbers
                if state == RESERVED:
                    scope = e.get("scope", e.get("task_id", "unknown-scope"))
                    reserved = e.get("reserved_cny")
                    if (scope != prev[1] or not _valid_amount(reserved)
                            or reserved != prev[2]):
                        corrupt = (f"line {lineno}: conflicting/invalid duplicate "
                                   f"RESERVED for {rid}")
                        break
                elif state == SETTLED:
                    new = e.get("cost_cny")
                    if not _valid_amount(new) or new != prev[3]:
                        corrupt = (f"line {lineno}: conflicting/invalid duplicate "
                                   f"SETTLED for {rid}")
                        break
                continue  # idempotent repeat (SENT/UNKNOWN carry no extra semantics)
            if state not in _REPLAY_TRANSITIONS.get(cur, frozenset()):
                corrupt = f"line {lineno}: illegal transition {cur}->{state} for {rid}"
                break
            if state == RESERVED:
                scope = e.get("scope", e.get("task_id", "unknown-scope"))
                reserved = e.get("reserved_cny")
                if not isinstance(scope, str) or not _valid_amount(reserved):
                    corrupt = f"line {lineno}: malformed RESERVED for {rid}"
                    break
                states[rid] = [RESERVED, scope, float(reserved), None]
            elif state == SETTLED:
                cost = e.get("cost_cny")
                if not _valid_amount(cost):
                    corrupt = f"line {lineno}: SETTLED with invalid cost for {rid}"
                    break
                prev[0] = SETTLED
                prev[3] = float(cost)
            else:
                prev[0] = state
        if corrupt is not None:
            self._ledger_corrupt = True
            self._stopped = True
            self._stop_reason = f"ledger corrupt: {corrupt}; refusing ALL requests"
            return
        for rid, (st, scope, _reserved, cost) in states.items():
            self._states[rid] = st
            self._request_scope[rid] = scope
            self._per_scope[scope] = self._per_scope.get(scope, 0) + 1
            if st == SETTLED:
                self._known_cost += cost
            elif st in (RESERVED, SENT):
                # conservative: an unsettled request MAY have been billed
                if rid not in reconciled:
                    self._recovered_unknown += 1
                    self._unresolved_unknown.add(rid)
            elif st == UNKNOWN and rid not in reconciled:
                self._unresolved_unknown.add(rid)
        if self._unresolved_unknown:
            self._stopped = True
            self._stop_reason = (
                f"ledger replay: {len(self._unresolved_unknown)} unresolved "
                "UNKNOWN/unsettled request(s); refusing new requests until a "
                "scoped manual reconcile")

    # ---------- host-side control ----------
    def set_current_scope(self, scope: str) -> None:
        """Trusted host-side attribution (experiment_run_id/task_id/seed/arm).
        The agent cannot reach this."""
        with self._lock:
            self._current_scope = scope

    def set_current_task(self, task_id: str) -> None:
        """Backward-compatible alias: attributes to a task-only scope."""
        self.set_current_scope(task_id)

    def reconcile(self, scope: str) -> list[str]:
        """Manual reconciliation of UNKNOWN requests belonging to ONE scope
        (P4-R1.4 P0-B). Only unresolved unknowns whose recorded scope equals
        `scope` are cleared; unknowns of every other scope keep the gate
        stopped. Never clears settled cost or per-scope counts. A corrupt
        ledger cannot be reconciled in-process."""
        with self._lock:
            if self._ledger_corrupt:
                raise GateStop("ledger corrupt: reconcile refused; rebuild required")
            if not scope or not isinstance(scope, str):
                raise GateStop("reconcile requires an explicit non-empty scope")
            cleared = sorted(rid for rid in self._unresolved_unknown
                             if self._request_scope.get(rid) == scope)
            self._persist({"control": "manual_reconcile", "scope": scope,
                           "cleared": cleared})
            self._apply_reconcile(cleared)
            return cleared

    def reconcile_requests(self, request_ids: list[str], *, reason: str) -> list[str]:
        """Cross-scope reconciliation: ONLY the explicitly listed request ids,
        with a mandatory operator reason. Refuses unknown/ghost ids."""
        with self._lock:
            if self._ledger_corrupt:
                raise GateStop("ledger corrupt: reconcile refused; rebuild required")
            if not reason or not isinstance(reason, str):
                raise GateStop("cross-scope reconcile requires an operator reason")
            if not request_ids:
                raise GateStop("cross-scope reconcile requires explicit request ids")
            unknown = [rid for rid in request_ids
                       if rid not in self._unresolved_unknown]
            if unknown:
                raise GateStop(f"request ids not pending reconciliation: {unknown}")
            cleared = sorted(request_ids)
            scopes = sorted({self._request_scope.get(rid, "?") for rid in cleared})
            self._persist({"control": "manual_reconcile", "scope": None,
                           "scopes": scopes, "cleared": cleared, "reason": reason})
            self._apply_reconcile(cleared)
            return cleared

    def _apply_reconcile(self, cleared: list[str]) -> None:
        for rid in cleared:
            self._unresolved_unknown.discard(rid)
        if not self._unresolved_unknown:
            self._recovered_unknown = 0
            self._stopped = False
            self._stop_reason = None
        else:
            self._recovered_unknown = len(self._unresolved_unknown)
            remaining = sorted({self._request_scope.get(rid, "?")
                                for rid in self._unresolved_unknown})
            self._stopped = True
            self._stop_reason = (f"{len(self._unresolved_unknown)} unresolved "
                                 f"UNKNOWN request(s) remain in scope(s) {remaining}")

    # ---------- gate ----------
    def _worst_case(self) -> float:
        return worst_case_cost_cny(self.config.worst_case_prompt_tokens,
                                   self.config.worst_case_output_tokens,
                                   self.config.usd_cny)

    def _check_and_reserve(self, scope: str) -> str:
        """All checks + reservation under one lock, BEFORE any byte upstream."""
        if not self.config.authorized:
            raise GateStop("not authorized")
        if self._stopped:
            raise GateStop(f"gate stopped: {self._stop_reason}")
        n_scope = self._per_scope.get(scope, 0)
        if n_scope + 1 > self.config.max_requests_per_task:
            raise GateStop(f"per-scope request cap: {n_scope + 1} > "
                           f"{self.config.max_requests_per_task}")
        worst = self._worst_case()
        projected = self._known_cost + self._inflight_reserved + worst
        if projected > self.config.global_cap_cny:
            raise GateStop(f"global budget: {projected:.6f} > {self.config.global_cap_cny}")
        request_id = uuid.uuid4().hex
        self._states[request_id] = RESERVED
        self._request_scope[request_id] = scope
        self._inflight_reserved += worst
        self._per_scope[scope] = n_scope + 1
        self._persist({"request_id": request_id, "state": RESERVED,
                       "scope": scope, "reserved_cny": worst})
        return request_id

    def _transition(self, request_id: str, state: str, **extra) -> None:
        self._states[request_id] = state
        self._persist({"request_id": request_id, "state": state, **extra})

    def _settle(self, request_id: str, cost_cny: float | None, note: str) -> None:
        worst = self._worst_case()
        if cost_cny is None:
            self._transition(request_id, UNKNOWN, note=note)
            self._inflight_reserved -= worst  # reservation converts to UNKNOWN
            self._unresolved_unknown.add(request_id)
            self._stopped = True
            self._stop_reason = f"unknown_cost at {request_id} ({note})"
        else:
            self._known_cost += cost_cny
            self._inflight_reserved -= worst
            self._transition(request_id, SETTLED, cost_cny=cost_cny, note=note)

    def _persist(self, entry: dict[str, Any]) -> None:
        if self._ledger_corrupt:
            return  # a corrupt ledger is evidence; never append to it
        self._log.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._log.flush()
        os.fsync(self._log.fileno())  # crash-grade durability for reservations

    def _audit_reject(self, reason: str, *, scope: str | None = None,
                      body: bytes | None = None, detail: str | None = None) -> None:
        """Audit an ingress/gate rejection. Never logs keys or prompt bodies."""
        entry: dict[str, Any] = {"state": REJECTED, "reason": reason,
                                 "scope": scope or self._current_scope}
        if body is not None:
            entry["body_sha16"] = hashlib.sha256(body).hexdigest()[:16]
            entry["body_bytes"] = len(body)
        if detail:
            entry["detail"] = detail
        with self._lock:
            self._persist(entry)

    # ---------- HTTP ----------
    def start(self, bind: tuple[str, int] = ("127.0.0.1", 0)) -> "BudgetProxy":
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                # --- ingress checks, all BEFORE any upstream byte (S4/S5) ---
                if self.path != "/chat/completions":
                    proxy._audit_reject("path", detail=self.path[:80])
                    self._send(404, {"error": "unknown path"})
                    return
                if proxy.config.client_token is not None:
                    expected = f"Bearer {proxy.config.client_token}"
                    if self.headers.get("Authorization") != expected:
                        proxy._audit_reject("ingress_auth")
                        self._send(401, {"error": "proxy client authentication failed"})
                        return
                raw_len = self.headers.get("Content-Length")
                try:
                    n = int(raw_len)  # type: ignore[arg-type]
                    if n < 0:
                        raise ValueError
                except (TypeError, ValueError):
                    proxy._audit_reject("content_length")
                    self._send(400, {"error": "missing/invalid Content-Length"})
                    return
                if n > proxy.config.effective_max_body_bytes:
                    proxy._audit_reject("body_size", detail=f"{n} bytes")
                    self._send(413, {"error": "request body exceeds reserved bound"})
                    return
                body = self.rfile.read(n)
                try:
                    obj = json.loads(body)
                except json.JSONDecodeError:
                    proxy._audit_reject("json", body=body)
                    self._send(400, {"error": "invalid JSON body"})
                    return
                if not isinstance(obj, dict) or not isinstance(obj.get("messages"), list):
                    proxy._audit_reject("shape", body=body)
                    self._send(400, {"error": "chat.completions shape required"})
                    return
                if proxy.config.allowed_model and \
                        obj.get("model") != proxy.config.allowed_model:
                    proxy._audit_reject("model", body=body,
                                        detail=str(obj.get("model"))[:60])
                    self._send(403, {"error": "model not allowed by frozen protocol"})
                    return
                max_out = _validate_output_limit(obj)
                if max_out is None:
                    proxy._audit_reject("output_limit", body=body,
                                        detail=_output_limit_problem(obj))
                    self._send(400, {"error": _output_limit_problem(obj)})
                    return
                if max_out > proxy.config.worst_case_output_tokens:
                    proxy._audit_reject("output_limit_exceeds", body=body,
                                        detail=str(max_out))
                    self._send(403, {"error": "output token cap exceeds reservation"})
                    return
                # --- budget gate (reserve BEFORE forwarding) ---
                with proxy._lock:
                    scope = proxy._current_scope  # host-attributed, not SDK-supplied
                    try:
                        request_id = proxy._check_and_reserve(scope)
                    except GateStop as exc:
                        proxy._persist({"state": REJECTED, "reason": str(exc),
                                        "scope": scope})
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

            def _refuse_method(self):
                proxy._audit_reject("method", detail=self.command)
                self._send(405, {"error": "POST /chat/completions only"})

            do_GET = _refuse_method
            do_PUT = _refuse_method
            do_DELETE = _refuse_method
            do_PATCH = _refuse_method

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
        trusted config; any agent-supplied Authorization is stripped. The URL
        is fixed at config time (allowlisted host, frozen path) — agents and
        untrusted env cannot redirect it."""
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
                "unresolved_unknown": sorted(self._unresolved_unknown),
                "ledger_corrupt": self._ledger_corrupt,
                "states": dict(self._states),
                "per_scope": dict(self._per_scope),
                # legacy key kept for older reports
                "per_task": dict(self._per_scope),
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
