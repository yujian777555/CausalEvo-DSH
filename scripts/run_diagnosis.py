"""Run Phase 2.2 diagnosis baselines offline and write results/phase2/diagnosis/.

Pipeline: build dataset (from committed Phase 1 traces) -> group split by
task_id (seed fixed) -> train B1/B2 on train -> evaluate B0/B1/B2 on val+test
-> write dataset_manifest / baseline_results / confusion_matrix /
sample_diagnosis / models. Zero network, zero cost.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
from sklearn.metrics import confusion_matrix  # noqa: E402

from causalevo.diagnosis.dataset import SPLIT_SEED, build_dataset, dataset_manifest, split_dataset  # noqa: E402
from causalevo.diagnosis.models import (  # noqa: E402
    EmbeddingDiagnoser,
    FeatureLRDiagnoser,
    RuleDiagnoser,
)
from causalevo.eval.trace import provenance_block  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "results" / "phase2" / "diagnosis"
EVAL_LABEL_SOURCES = {"scenario_injected", "judge_outcome"}  # silver excluded from scoring
CATEGORIES = ["planning_failure", "tool_failure", "knowledge_failure",
              "execution_failure", "verification_failure", "strategy_failure",
              "unknown", "success"]


def _ece(confs: list[float], correct: list[bool], bins: int = 10) -> float:
    if not confs:
        return 0.0
    ece = 0.0
    for lo in np.linspace(0, 1, bins, endpoint=False):
        hi = lo + 1 / bins
        idx = [i for i, c in enumerate(confs) if lo <= c < hi]
        if idx:
            ece += len(idx) / len(confs) * abs(
                np.mean([confs[i] for i in idx]) - np.mean([correct[i] for i in idx]))
    return float(ece)


def _risk_coverage(confs, corrects):
    points = []
    for thr in np.arange(0.0, 1.0, 0.05):
        covered = [i for i, c in enumerate(confs) if c >= thr]
        if not covered:
            continue
        acc = np.mean([corrects[i] for i in covered])
        points.append({"threshold": round(float(thr), 2),
                       "coverage": round(len(covered) / len(confs), 4),
                       "accuracy_covered": round(float(acc), 4)})
    return points


def _evidence_precision(results, traces_by_id, rows_by_id=None):
    hits = total = 0
    for res in results:
        trace = traces_by_id.get(res.trace_id, {})
        row = (rows_by_id or {}).get(res.trace_id, {})
        for ref in res.evidence:
            total += 1
            if ref.startswith("feature:"):
                # feature:name=value [@trace.ref] — verifiable against the row
                body, _, tref = ref[len("feature:"):].partition(" @")
                name, _, value = body.partition("=")
                ok = name in row.get("features", {}) and str(row["features"][name]) == value
                if ok and tref:
                    node = trace
                    for part in tref.split("."):
                        if not isinstance(node, dict) or part not in node:
                            ok = False
                            break
                        node = node[part]
                    ok = ok and node is not None
                hits += 1 if ok else 0
                continue
            root = ref.split(".")[0].split("[")[0]
            if root in trace or root in (trace.get("agent") or {}) or root in (trace.get("judge") or {}) \
                    or root in (trace.get("states") or {}):
                hits += 1
    return (hits / total) if total else None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = build_dataset(REPO / "results" / "phase1", REPO / "benchmarks" / "tasks")
    splits = split_dataset(rows, seed=SPLIT_SEED)

    with (OUT / "diagnosis_dataset.jsonl").open("w", encoding="utf-8") as fh:
        for split in ("train", "val", "test"):
            for r in splits[split]:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    manifest = dataset_manifest(splits, SPLIT_SEED)
    manifest["eval_label_sources"] = sorted(EVAL_LABEL_SOURCES)
    manifest["note"] = ("train may include rule_chain_silver labels (distant supervision); "
                        "evaluation metrics use only scenario_injected + judge_outcome labels")
    manifest["provenance"] = provenance_block()
    (OUT / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                                               encoding="utf-8")

    eval_rows = [r for split in ("val", "test") for r in splits[split]
                 if r.get("label_source") in EVAL_LABEL_SOURCES and r.get("label")]
    traces_by_id = {}
    from causalevo.failure_dataset.builder import iter_traces
    for trace, _run, _pk, _sc in iter_traces(REPO / "results" / "phase1"):
        traces_by_id[trace["trace_id"]] = trace

    # B0 rules (no training)
    b0 = RuleDiagnoser()
    # B1 feature LR
    b1 = FeatureLRDiagnoser(abstain_threshold=0.5)
    b1.fit(splits["train"])
    # B2 embedding LR
    b2 = EmbeddingDiagnoser(abstain_threshold=0.5)
    b2.fit(splits["train"], traces_by_id)

    (OUT / "models").mkdir(exist_ok=True)
    b1.save(OUT / "models" / "b1_feature_lr.pkl")

    def eval_model(name, diagnose_fn):
        y_true, y_pred, confs, results = [], [], [], []
        for r in eval_rows:
            res = diagnose_fn(r)
            results.append(res)
            y_true.append(r["label"])
            y_pred.append(res.failure_type)
            confs.append(res.confidence)
        labels = [c for c in CATEGORIES if c in set(y_true) | set(y_pred)]
        cm = confusion_matrix(y_true, y_pred, labels=labels).tolist()
        correct = [t == p for t, p in zip(y_true, y_pred)]
        n = len(y_true)
        acc = float(np.mean(correct)) if n else None
        # macro F1
        f1s = []
        for i, cat in enumerate(labels):
            tp = sum(1 for t, p in zip(y_true, y_pred) if t == cat and p == cat)
            fp = sum(1 for t, p in zip(y_true, y_pred) if t != cat and p == cat)
            fn = sum(1 for t, p in zip(y_true, y_pred) if t == cat and p != cat)
            prec = tp / (tp + fp) if tp + fp else 0.0
            rec = tp / (tp + fn) if tp + fn else 0.0
            f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
        unknown_rate = sum(1 for p in y_pred if p == "unknown") / n if n else None
        return {
            "model": name,
            "n_eval": n,
            "accuracy": acc,
            "macro_f1": (sum(f1s) / len(f1s)) if f1s else None,
            "labels": labels,
            "confusion_matrix": cm,
            "ece": _ece(confs, correct),
            "unknown_rate": unknown_rate,
            "risk_coverage": _risk_coverage(confs, correct),
            "evidence_precision": _evidence_precision(results, traces_by_id,
                                                      {r["trace_id"]: r for r in eval_rows}),
            "evidence_coverage": 1.0 if all(res.evidence for res in results) else None,
            "_results": results,
        }, y_true, y_pred

    out = {}
    out["B0-rules"], t0, p0 = eval_model("B0-rules", lambda r: b0.diagnose(traces_by_id[r["trace_id"]]))
    rows_by_id = {r["trace_id"]: r for r in eval_rows}
    out["B1-feature-lr"], t1, p1 = eval_model(
        "B1-feature-lr", lambda r: b1.diagnose_row(r, trace=traces_by_id[r["trace_id"]]))
    out["B2-embedding-lr"], t2, p2 = eval_model(
        "B2-embedding-lr", lambda r: b2.diagnose(traces_by_id[r["trace_id"]]))

    cm_payload = {}
    for name, (res, yt, yp) in {"B0-rules": (out["B0-rules"], t0, p0),
                                "B1-feature-lr": (out["B1-feature-lr"], t1, p1),
                                "B2-embedding-lr": (out["B2-embedding-lr"], t2, p2)}.items():
        cm_payload[name] = {"labels": res["labels"], "matrix": res["confusion_matrix"]}
    (OUT / "confusion_matrix.json").write_text(json.dumps(cm_payload, indent=2), encoding="utf-8")

    samples = {}
    for name, res in out.items():
        samples[name] = [r.as_dict() for r in res.pop("_results")[:3]]
    (OUT / "sample_diagnosis.json").write_text(json.dumps(samples, indent=2, ensure_ascii=False),
                                               encoding="utf-8")
    (OUT / "baseline_results.json").write_text(json.dumps({
        "eval_rows": len(eval_rows),
        "eval_label_sources": sorted(EVAL_LABEL_SOURCES),
        "results": out,
        "provenance": provenance_block(),
        "note": "offline traces only; NOT model capability evidence",
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"eval rows: {len(eval_rows)}")
    for name, res in out.items():
        print(f"{name}: acc={res['accuracy']:.3f} macroF1={res['macro_f1']:.3f} "
              f"unknown_rate={res['unknown_rate']:.3f} ece={res['ece']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
