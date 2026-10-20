"""Standalone BudgetProxy server for the proxy container (P4-R1.3 S2-S4).

Runs inside a Docker container with the package mounted read-only. Port 8081
serves agent traffic on ceval-net; the same port is ALSO reachable on the
default bridge (dual-NIC for DIRECT upstream egress), so ingress client
authentication is MANDATORY: every POST must carry the per-run bearer token
from CE_PROXY_CLIENT_TOKEN (generated per run by the host, injected into the
agent's request by the runner, never published to other containers).

Upstream is pinned by config: host allowlist + https (live: api.deepseek.com);
the offline fake provider requires CE_PROXY_ALLOW_INSECURE=1 and its container
name in CE_PROXY_ALLOWED_HOSTS. The upstream API key comes only from the
trusted env CE_PROXY_KEY — agent-supplied Authorization is stripped.

Config via env:
  CE_PROXY_UPSTREAM        e.g. https://api.deepseek.com (or fake provider)
  CE_PROXY_KEY             trusted upstream key (never logged)
  CE_PROXY_CLIENT_TOKEN    REQUIRED per-run ingress token (401 without it)
  CE_PROXY_MAX_PER_TASK    per-scope request cap
  CE_PROXY_CAP_CNY         global cap
  CE_PROXY_AUTHORIZED      "1"/"0"
  CE_PROXY_WC_PROMPT_TOKENS / CE_PROXY_WC_OUTPUT_TOKENS  worst-case reservation
  CE_PROXY_ALLOWED_HOSTS   comma-separated upstream host allowlist
  CE_PROXY_ALLOW_INSECURE  "1" permits http upstream (offline fake only)
  CE_PROXY_ALLOWED_MODEL   fixed model (default deepseek-flash)
Ledger: /ledger/ledger.jsonl (host-mounted for durability).
Control: /ledger/control.json {"generation": n, "scope": "..."} -> ACK echoes n.
"""
import json
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, "/opt/src")

from causalevo.eval.budget_proxy import BudgetProxy, ProxyConfig  # noqa: E402
from causalevo.eval.proxy_control import ACK_NAME, apply_control  # noqa: E402

PROXY: BudgetProxy | None = None
CONTROL_FILE = Path(os.environ.get("CE_PROXY_CONTROL", "/ledger/control.json"))


def _control_loop() -> None:
    """Trusted scope attribution via the shared ledger dir. Generation-based:
    only strictly newer generations are applied and ACKed (echoing the same
    generation), so repeated scopes and delayed ACKs cannot deadlock."""
    last_generation = -1
    ack_path = CONTROL_FILE.with_name(ACK_NAME)
    while True:
        try:
            if CONTROL_FILE.is_file() and PROXY is not None:
                data = json.loads(CONTROL_FILE.read_text(encoding="utf-8"))
                last_generation = apply_control(PROXY, data, last_generation, ack_path)
        except Exception:
            pass
        time.sleep(0.05)


def main() -> int:
    global PROXY
    ledger = Path(os.environ.get("CE_PROXY_LEDGER", "/ledger/ledger.jsonl"))
    token = os.environ.get("CE_PROXY_CLIENT_TOKEN")
    if not token:
        print("FATAL: CE_PROXY_CLIENT_TOKEN required (ingress auth)", flush=True)
        return 2
    allowed_hosts = tuple(h.strip() for h in
                          os.environ.get("CE_PROXY_ALLOWED_HOSTS",
                                         "api.deepseek.com").split(",") if h.strip())
    try:
        PROXY = BudgetProxy(ProxyConfig(
            upstream_base_url=os.environ["CE_PROXY_UPSTREAM"],
            max_requests_per_task=int(os.environ.get("CE_PROXY_MAX_PER_TASK", "8")),
            global_cap_cny=float(os.environ.get("CE_PROXY_CAP_CNY", "3.0")),
            worst_case_prompt_tokens=int(os.environ.get("CE_PROXY_WC_PROMPT_TOKENS",
                                                        "65536")),
            worst_case_output_tokens=int(os.environ.get("CE_PROXY_WC_OUTPUT_TOKENS",
                                                        "2048")),
            authorized=os.environ.get("CE_PROXY_AUTHORIZED", "1") == "1",
            upstream_api_key=os.environ.get("CE_PROXY_KEY") or None,
            client_token=token,
            allowed_model=os.environ.get("CE_PROXY_ALLOWED_MODEL", "deepseek-flash"),
            allowed_upstream_hosts=allowed_hosts,
            allow_insecure_upstream=os.environ.get("CE_PROXY_ALLOW_INSECURE") == "1",
        ), ledger)
    except (ValueError, KeyError) as exc:
        print(f"FATAL: proxy config rejected: {exc}", flush=True)
        return 2
    if not ledger.parent.is_dir():
        print(f"FATAL: ledger dir unavailable: {ledger.parent}", flush=True)
        return 2
    PROXY.start(bind=("0.0.0.0", 8081))
    threading.Thread(target=_control_loop, daemon=True).start()
    print("proxy up", flush=True)
    # keep the process alive; the traffic server runs in its own thread
    threading.Event().wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
