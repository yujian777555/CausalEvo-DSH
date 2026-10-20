"""Standalone BudgetProxy server for the proxy container (P4-R1.2-S2).

Runs inside a Docker container with the package mounted read-only. Traffic
port 8081 faces ceval-net (agents); control port 8082 is published to host
loopback only. Upstream is the configured provider host, DIRECT (no proxy
env). The upstream API key comes from the proxy container's environment
(trusted injection), never from the agent.

Config via env:
  CE_PROXY_UPSTREAM       e.g. https://api.deepseek.com (or fake provider)
  CE_PROXY_KEY            trusted upstream key (never logged)
  CE_PROXY_MAX_PER_TASK   per-task request cap
  CE_PROXY_CAP_CNY        global cap
  CE_PROXY_AUTHORIZED     "1"/"0"
Ledger: /ledger/ledger.jsonl (host-mounted for durability).
Control: POST /control {"task_id": "..."} sets the current task attribution.
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, "/opt/src")

from causalevo.eval.budget_proxy import BudgetProxy, ProxyConfig  # noqa: E402

PROXY: BudgetProxy | None = None

PROXY: BudgetProxy | None = None
CONTROL_FILE = Path(os.environ.get("CE_PROXY_CONTROL", "/ledger/control.json"))


def _control_loop() -> None:
    """Trusted task attribution via the shared ledger dir: the host writes
    control.json; agents cannot reach it (they never see the mount). The proxy
    acks by writing control_ack.json so the host can synchronize."""
    last = None
    while True:
        try:
            if CONTROL_FILE.is_file():
                data = json.loads(CONTROL_FILE.read_text(encoding="utf-8"))
                if data != last and "task_id" in data and PROXY is not None:
                    PROXY.set_current_task(data["task_id"])
                    last = data
                    CONTROL_FILE.with_name("control_ack.json").write_text(
                        json.dumps({"task_id": data["task_id"]}), encoding="utf-8")
        except Exception:
            pass
        time.sleep(0.05)


def main() -> int:
    global PROXY
    ledger = Path(os.environ.get("CE_PROXY_LEDGER", "/ledger/ledger.jsonl"))
    PROXY = BudgetProxy(ProxyConfig(
        upstream_base_url=os.environ["CE_PROXY_UPSTREAM"],
        max_requests_per_task=int(os.environ.get("CE_PROXY_MAX_PER_TASK", "8")),
        global_cap_cny=float(os.environ.get("CE_PROXY_CAP_CNY", "3.0")),
        authorized=os.environ.get("CE_PROXY_AUTHORIZED", "1") == "1",
        upstream_api_key=os.environ.get("CE_PROXY_KEY") or None,
    ), ledger)
    PROXY.start(bind=("0.0.0.0", 8081))
    threading.Thread(target=_control_loop, daemon=True).start()
    print("proxy up", flush=True)
    # keep the process alive; the traffic server runs in its own thread
    threading.Event().wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
