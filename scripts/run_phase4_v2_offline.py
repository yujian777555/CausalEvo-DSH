"""P4-R1.3-S6: versioned offline adapter-integration smoke using the REAL
policy adapters, driven through FOUR distinct fake-provider failure scenarios.

B4-v2: LinUCB controller (CausalPolicyAdapter.cea_v0) selects the intervention.
B5-v2: frozen NSGA-III Pareto front (CausalPolicyAdapter.cea_v1) with the
frozen failure-conditioned genome selection rule; the front is loaded ONLY
after its SHA-256 is verified against the independent frozen manifest
configs/phase3_artifact_manifest.json (no self-certification).

Scenarios (attempt-1 tapes):
  edited_failing     valid-but-wrong edit  -> edited=True,  invalid=False
  invalid_syntax     syntactically broken  -> edited=True,  invalid=True
  no_edit            read only, never writes -> edited=False, invalid=False
  infra_unknown_cost correct edit, usage suppressed on EVERY step, plus one
                     provider error the SDK retries -> the retried attempt is
                     recorded as an assistant/attempt without settled usage
                     -> failure_kind="unknown_cost", run still "completes"

Chain per case: agent container attempt-1 (scenario tape) -> adapter selects
from observable evidence only (edited is COMPUTED from the workspace digest,
never hardcoded) -> attempt-2 (fix tape + selected intervention text) unless
the adapter says no-retry -> independent judge. Zero API spend; fake provider
only; rows are labeled experiment_version=p4-r1.3-v2 with
evidence_class=adapter_integration_smoke and never merge into the 2026-10-14
pilot rows.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from causalevo.eval.executor import DockerExecutor  # noqa: E402
from causalevo.eval.harness_agent import ContainerHarnessRunner  # noqa: E402
from causalevo.eval.judge import Judge  # noqa: E402
from causalevo.eval.live_pilot import INTERVENTION_TEXT  # noqa: E402
from causalevo.eval.networks import ProviderContainer  # noqa: E402
from causalevo.eval.runtime_budget import RuntimeBudget  # noqa: E402
from causalevo.eval.task_spec import load_task  # noqa: E402
from causalevo.eval.workspace_factory import WorkspaceFactory  # noqa: E402
from causalevo.eval.trace import new_run_id, provenance_block  # noqa: E402
from causalevo.evolution.adapter import ADAPTER_VERSION, CausalPolicyAdapter, canonical_sha256  # noqa: E402
from causalevo.evolution.policy import ACTIONS, LinUCBPolicy  # noqa: E402
from causalevo.evolution.reward import compute_reward  # noqa: E402
from causalevo.intervention.generator import INTERVENTION_LIBRARY  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
IMAGE = "causalevo-dsh-agent:0.2.1"
PATCH = REPO / "configs" / "dsh_task_patch.yml"
FRONT = REPO / "results" / "phase3" / "evolution" / "pareto_front.json"
SWEEP = REPO / "results" / "phase3" / "replay_sweep" / "sweep_results.jsonl"
ARTIFACT_MANIFEST = REPO / "configs" / "phase3_artifact_manifest.json"
EXPERIMENT_VERSION = "p4-r1.3-v2"
EVIDENCE_CLASS = "adapter_integration_smoke"
ARMS = ("B4-v2", "B5-v2")
INFRA_KINDS = ("unknown_cost", "budget_stop", "transport", "protocol")

# frozen action->text mapping for B4-v2 (recorded; not tuned on results)
ACTION_TO_TEXT = {
    "lib:tool_failure": INTERVENTION_TEXT["tool_validation"],
    "lib:planning_failure": INTERVENTION_TEXT["planning"],
    "lib:verification_failure": INTERVENTION_TEXT["verification"],
    "lib:knowledge_failure": INTERVENTION_TEXT["read_before_write"],
    "lib:strategy_failure": INTERVENTION_TEXT["planning"],
    "lib:execution_failure": None,   # infra: never retry behaviorally
    "lib:unknown": None,
}

WRONG_FIX = "def clamp_value(x, lo, hi):\n    return min(max(x, lo), lo)\n"
CORRECT_FIX = "def clamp_value(x, lo, hi):\n    return min(max(x, lo), hi)\n"
BROKEN_FIX = "def clamp_value(:\n"

SCENARIO_TAPES = {
    # valid-but-wrong write (always returns lo; differs from the pristine
    # buggy file so the workspace digest really changes) -> judge fails,
    # edited=True, invalid=False
    "edited_failing": {
        "0": [["tool_call", "read", {"file_path": "solution.py"}]],
        "1": [["tool_call", "write", {"file_path": "solution.py",
                                      "content": WRONG_FIX}]],
        "2": [["text", "wrong fix applied"]],
    },
    # syntactically invalid write -> judge invalid_reason, edited=True
    "invalid_syntax": {
        "0": [["tool_call", "read", {"file_path": "solution.py"}]],
        "1": [["tool_call", "write", {"file_path": "solution.py",
                                      "content": BROKEN_FIX}]],
        "2": [["text", "wrote something"]],
    },
    # never writes -> edited=False
    "no_edit": {
        "0": [["tool_call", "read", {"file_path": "solution.py"}]],
        "1": [["text", "done"]],
    },
    # correct fix, usage suppressed on EVERY step. The leading provider error
    # is retried by the SDK and recorded as an assistant/attempt WITHOUT
    # settled usage; the committed no-usage message steps are invisible to the
    # ledger. Net: run "completes" but failure_kind="unknown_cost".
    "infra_unknown_cost": {
        "0": [["error", 500, {"error": {"message": "boom"}}], ["no_usage"]],
        "1": [["tool_call", "read", {"file_path": "solution.py"}], ["no_usage"]],
        "2": [["tool_call", "write", {"file_path": "solution.py",
                                      "content": CORRECT_FIX}], ["no_usage"]],
        "3": [["text", "fixed"], ["no_usage"]],
    },
}
SCENARIOS = tuple(SCENARIO_TAPES)

FIX_TAPE = {
    "0": [["tool_call", "read", {"file_path": "solution.py"}]],
    "1": [["tool_call", "write", {"file_path": "solution.py",
                                   "content": CORRECT_FIX}]],
    "2": [["text", "fixed"]],
}


def _manifest_hash(artifact_rel: str) -> str:
    manifest = json.loads(ARTIFACT_MANIFEST.read_text(encoding="utf-8"))
    return manifest["artifacts"][artifact_rel]["sha256"]


def _verify_against_manifest(path: Path, artifact_rel: str) -> str:
    expected = _manifest_hash(artifact_rel).strip().lower()
    actual = canonical_sha256(path)
    if actual != expected:
        raise ValueError(
            f"{artifact_rel} diverged from the frozen manifest: expected "
            f"{expected}, file has {actual}")
    return expected


def _train_linucb_snapshot() -> tuple[LinUCBPolicy, str]:
    """Deterministic offline training from the sweep matrix (frozen rules).
    The sweep file hash is verified against the frozen manifest FIRST — the
    snapshot must provably come from the pinned artifact."""
    _verify_against_manifest(SWEEP, "results/phase3/replay_sweep/sweep_results.jsonl")
    rows = [json.loads(l) for l in SWEEP.read_text(encoding="utf-8").splitlines()]
    lib = {iv.intervention_id: iv for iv in INTERVENTION_LIBRARY}
    policy = LinUCBPolicy(alpha=0.5)
    for r in rows:  # fixed order = file order
        state = {"failure_type": r["true_failure"], "prompt_chars": 100,
                 "n_visible_checks": 3}
        reward = compute_reward(r["success_delta"], r["cost_delta_cny"])
        policy.update(state, r["intervention_id"], reward)
    snapshot = policy.to_dict()
    sha = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    return policy, sha


def _budget() -> RuntimeBudget:
    return RuntimeBudget(max_provider_calls=8, max_total_output_tokens=4096,
                         max_tool_calls=12, wall_time_s=240)


def _run_attempt(spec, tape, prompt_extra, judge, ws_factory, tag):
    ws = ws_factory.create(spec, tag)
    with ProviderContainer(tape) as provider:
        runner = ContainerHarnessRunner(
            image=IMAGE, patch_path=PATCH, model="deepseek-flash",
            reasoning_effort="low", max_tokens=256, provider_kind="fake",
            provider_endpoint=provider.endpoint)
        outcome = runner.run_task(spec, ws.root, EXPERIMENT_VERSION, _budget(),
                                  api_key="sk-fake-offline-no-cost",
                                  extra_prompt=prompt_extra)
    report = judge.grade(spec, ws.root)
    success = (report.visible_passed and report.sealed_passed
               and not report.invalid_reason and not report.timed_out)
    return ws, outcome, report, success


def _b4_decide(b4, snap_sha, spec, failure_kind, edited, invalid):
    """B4-v2 selection from observable evidence. Infra failure kinds are
    fail-closed: the candidate set is restricted to the execution_failure
    action, whose frozen text mapping is None (never a behavioral retry)."""
    if failure_kind in INFRA_KINDS:
        failure_type = "execution_failure"
        candidates = ["lib:execution_failure"]
    else:
        failure_type = "verification_failure" if invalid else "knowledge_failure"
        candidates = list(ACTIONS)
    state = {"failure_type": failure_type,
             "prompt_chars": len(spec.instructions),
             "n_visible_checks": 3}
    sel = b4.select(state, candidates)
    action = sel["selected_action"]
    text = ACTION_TO_TEXT.get(action)
    if failure_kind in INFRA_KINDS:
        reason = (f"infra failure {failure_kind}: fail-closed, "
                  "lib:execution_failure maps to no retry")
    else:
        reason = f"LinUCB selected {action} for failure_type={failure_type}"
    return text, {
        "b4_failure_type": failure_type,
        "candidates": candidates,
        "policy_snapshot_sha256": snap_sha,
        "policy_version": sel["policy_version"],
        "selected_action": action,
        "confidence": sel["confidence"],
        "reason": reason,
    }


def _b5_decide(b5, failure_kind, edited, invalid):
    pick = b5.select_genome(failure_kind=failure_kind, edited=edited,
                            invalid=invalid)
    if pick["genome"] is None:
        return None, {"selected_genome": None, "reason": pick["reason"],
                      "pareto_front_sha256": b5.provenance["pareto_front_sha256"]}
    interv = b5.intervention_for(failure_kind=failure_kind, edited=edited,
                                 invalid=invalid, genome=pick["genome"])
    return interv["text"], {
        "selected_genome": pick["genome_id"],
        "reason": pick["reason"],
        "genome_train_fitness": pick.get("train_fitness"),
        "pareto_front_sha256": b5.provenance["pareto_front_sha256"],
    }


def main() -> int:
    out = REPO / "results" / "phase4" / "v2-offline" / f"run-{new_run_id()}"
    out.mkdir(parents=True, exist_ok=True)
    judge = Judge(DockerExecutor())
    spec = load_task(REPO / "benchmarks" / "tasks" / "micro-000-clamp_value")
    linucb, snap_sha = _train_linucb_snapshot()
    b4 = CausalPolicyAdapter.cea_v0(linucb.to_dict())
    b5 = CausalPolicyAdapter.cea_v1_from_manifest(FRONT, ARTIFACT_MANIFEST)
    records = []
    for arm in ARMS:
        for scenario in SCENARIOS:
            factory = WorkspaceFactory()
            ws, outcome1, report1, success1 = _run_attempt(
                spec, SCENARIO_TAPES[scenario], None, judge, factory,
                f"{arm}-{scenario}-a1")
            # observable evidence COMPUTED from the workspace before teardown
            edited = ws.digest() != ws.digest_at_open
            factory.destroy_all()
            invalid = bool(report1.invalid_reason)
            failure_kind = outcome1.failure_kind
            if arm == "B4-v2":
                text, rec_extra = _b4_decide(b4, snap_sha, spec, failure_kind,
                                             edited, invalid)
            else:
                text, rec_extra = _b5_decide(b5, failure_kind, edited, invalid)
            record = {
                "scenario": scenario,
                "arm": arm,
                "experiment_version": EXPERIMENT_VERSION,
                "failure_state": {"failure_kind": failure_kind,
                                  "edited": edited, "invalid": invalid},
                "attempt1_success": success1,
                "intervention_text": text,
                "policy_updated": False,
                **rec_extra,
            }
            if text is None:
                record.update({"attempt2": None, "final_success": success1,
                               "note": "no retry (adapter decision)"})
            else:
                factory2 = WorkspaceFactory()
                _ws2, _o2, _r2, success2 = _run_attempt(
                    spec, FIX_TAPE, text, judge, factory2,
                    f"{arm}-{scenario}-a2")
                factory2.destroy_all()
                record.update({"attempt2": "ran", "final_success": success2})
            records.append(record)
            print(arm, scenario, "a1:", success1, "kind:", failure_kind,
                  "edited:", edited, "invalid:", invalid,
                  "final:", record["final_success"])
    with (out / "records.jsonl").open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    (out / "manifest.json").write_text(json.dumps({
        "experiment_version": EXPERIMENT_VERSION,
        "evidence_class": EVIDENCE_CLASS,
        "arms": list(ARMS),
        "scenarios": list(SCENARIOS),
        "adapter_version": ADAPTER_VERSION,
        "artifact_manifest": "configs/phase3_artifact_manifest.json",
        "pareto_front_sha256": b5.provenance["pareto_front_sha256"],
        "sweep_sha256": _manifest_hash(
            "results/phase3/replay_sweep/sweep_results.jsonl"),
        "policy_snapshot_sha256": snap_sha,
        "provider": "fake tape (offline)",
        "provenance": provenance_block(),
        "note": ("synthetic fake-provider evidence only; NOT algorithm "
                 "generalization / real-agent improvement / NSGA-III "
                 "superiority evidence."),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("run_dir:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
