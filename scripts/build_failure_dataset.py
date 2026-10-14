"""Build the Phase 2.1 failure dataset from committed offline run artifacts.

Offline; reads results/phase1/**/traces.jsonl (committed fake/replay runs),
writes results/phase2/failure_analysis/. No API calls; no fabricated failures
— every record corresponds to a real committed trace.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from causalevo.analysis.evaluate import evaluate  # noqa: E402
from causalevo.failure_dataset.builder import build_records, stats  # noqa: E402
from causalevo.eval.trace import provenance_block  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "results" / "phase2" / "failure_analysis"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    records = build_records(REPO / "results" / "phase1")
    with (OUT / "failure_records.jsonl").open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    s = stats(records)
    ev = evaluate(records)
    (OUT / "failure_stats.json").write_text(
        json.dumps({"stats": s, "evaluation": ev}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    # sample reports: 2 per category max, content-free
    samples: dict[str, list] = {}
    for r in records:
        samples.setdefault(r["failure_category"], []).append(r)
    (OUT / "sample_reports.json").write_text(
        json.dumps({k: v[:2] for k, v in sorted(samples.items())}, indent=2,
                   ensure_ascii=False),
        encoding="utf-8")
    (OUT / "manifest.json").write_text(json.dumps({
        "created_by": "scripts/build_failure_dataset.py",
        "source": "results/phase1/**/traces.jsonl (committed offline runs)",
        "record_count": len(records),
        "provenance": provenance_block(),
        "notes": [
            "records derive only from committed offline traces; nothing fabricated",
            "evidence refs point at trace fields; no CoT, no sealed content",
        ],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("records:", len(records))
    print(json.dumps(s["by_category"], indent=1))
    print("accuracy(labeled):", ev["accuracy_labeled"], "| unknown_rate:", ev["unknown_rate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
