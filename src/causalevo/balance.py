"""Platform balance queries for cost reconciliation (plan P0.4: 抽样对账).

DeepSeek bills in CNY; GET /user/balance returns the remaining balance. The
delta around a run is ground truth for actual billed cost (subject to
concurrent usage elsewhere, which we do not have). The API key is read from
the environment and never logged. Proxies are bypassed explicitly so a
misconfigured local proxy cannot break a billing measurement.
"""

from __future__ import annotations

import json
import urllib.request

BALANCE_URL = "https://api.deepseek.com/user/balance"


def query_balance_cny(api_key: str, timeout_seconds: float = 15.0) -> float:
    """Total remaining balance in CNY. Raises on any failure (fail-closed)."""
    if not api_key.strip():
        raise ValueError("api_key must be non-empty")
    request = urllib.request.Request(
        BALANCE_URL, headers={"Authorization": f"Bearer {api_key}"}
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    for info in payload.get("balance_infos", []):
        if info.get("currency") == "CNY":
            return float(info["total_balance"])
    raise RuntimeError(f"no CNY balance in response: keys={list(payload.keys())}")
