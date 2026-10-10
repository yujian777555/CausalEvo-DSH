"""Regenerate results/phase0/live/summary.json from the immutable calls.csv.

Usage: .venv/Scripts/python.exe scripts/reconcile_live.py
Offline, no API spend. Writes reconciliation.json + backfilled summary.json.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from causalevo.reconcile import backfill_summary  # noqa: E402

if __name__ == "__main__":
    out = Path("results/phase0/live")
    summary = backfill_summary(out)
    overall = summary["overall"]
    print("backfilled summary.json + reconciliation.json")
    print("rows:", overall["logical_calls"], "ok:", overall["completed_calls"])
    print("uncached:", overall["uncached_input_tokens"],
          "cache_read:", overall["cache_read_tokens"],
          "total_prompt:", overall["total_prompt_tokens"],
          "output:", overall["output_tokens_all_attempts"])
    print("weighted hit rate:", overall["weighted_cache_hit_rate"])
    print("finish:", overall["finish_reason_distribution"])
    print("cost tiered:", overall["cost_cny_tiered"], "peak:", overall["cost_cny_peak"])
