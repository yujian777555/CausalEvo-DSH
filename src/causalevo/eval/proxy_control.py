"""Generation-based proxy control channel protocol (P4-R1.3 S3).

The host publishes attribution scopes to the proxy through the shared ledger
directory (agents never see the mount). R1.2 review findings fixed here:

- the stale ACK is removed BEFORE the new control message is published
  (previously: publish-then-delete, which could delete a fresh ACK)
- every control message carries a monotonically increasing generation; the
  proxy ACKs by echoing the SAME generation, so repeated identical scopes,
  fast A->B->A switches and delayed ACKs can never deadlock or be confused
  for freshness
- control.json / control_ack.json are written atomically (tmp + os.replace)
- a missing shared mount, a mismatched/late ACK, or a generation jump raise
  so the runner REFUSES to start the agent when attribution is unconfirmed

The channel supports one active scope at a time; the runner enforces serial
evaluations with a lock (documented in networks.ProxyContainer).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

CONTROL_NAME = "control.json"
ACK_NAME = "control_ack.json"


class ControlChannelError(RuntimeError):
    pass


def publish_control(ledger_dir: Path, generation: int, scope: str) -> None:
    """Host side: clear the stale ACK first, then atomically publish."""
    if not ledger_dir.is_dir():
        raise ControlChannelError(f"ledger dir unavailable: {ledger_dir}")
    ack = ledger_dir / ACK_NAME
    try:
        ack.unlink()
    except FileNotFoundError:
        pass
    tmp = ledger_dir / f".{CONTROL_NAME}.{os.getpid()}.tmp"
    tmp.write_text(json.dumps({"generation": generation, "scope": scope}),
                   encoding="utf-8")
    os.replace(tmp, ledger_dir / CONTROL_NAME)


def await_ack(ledger_dir: Path, generation: int, timeout_s: float = 10.0) -> dict[str, Any]:
    """Host side: wait for the proxy to echo THIS generation."""
    deadline = time.monotonic() + timeout_s
    ack = ledger_dir / ACK_NAME
    while time.monotonic() < deadline:
        try:
            data = json.loads(ack.read_text(encoding="utf-8"))
        except FileNotFoundError:
            time.sleep(0.05)
            continue
        except json.JSONDecodeError:
            time.sleep(0.05)  # ack mid-replace; retry
            continue
        gen = data.get("generation")
        if gen == generation:
            return data
        if isinstance(gen, int) and gen > generation:
            raise ControlChannelError(
                f"ack generation {gen} is newer than published {generation}: "
                "concurrent control publishers detected")
        time.sleep(0.05)
    raise ControlChannelError(
        f"control channel: no ack for generation {generation} within {timeout_s}s")


def apply_control(proxy: Any, data: Any, last_generation: int,
                  ack_path: Path) -> int:
    """Proxy side: apply a control message if (and only if) its generation is
    newer than the last applied one; ACK echoes the applied generation.

    Returns the new last_generation. Stale/duplicate/malformed messages are
    ignored (no ACK), so the host times out loudly instead of proceeding with
    wrong attribution."""
    if not isinstance(data, dict):
        return last_generation
    gen = data.get("generation")
    scope = data.get("scope")
    if not isinstance(gen, int) or isinstance(gen, bool) or \
            not isinstance(scope, str) or not scope:
        return last_generation
    if gen <= last_generation:
        return last_generation
    proxy.set_current_scope(scope)
    tmp = ack_path.with_name(f".{ACK_NAME}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"generation": gen, "scope": scope}), encoding="utf-8")
    os.replace(tmp, ack_path)
    return gen
