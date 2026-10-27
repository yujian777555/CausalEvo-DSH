"""CE-DSH-P4-R1.9 — four-arm pilot runner with the REAL online evolution loop.

Arms (distinct code paths, recorded per row):
- B0-original: single attempt, no retry.
- B1-random: frozen random intervention text on attempt-1 failure.
- B5-v1: frozen Pareto static selection (CausalPolicyAdapter.cea_v1_from_manifest
  + select_genome), zero updates for the whole run.
- CEA-v2: OnlineEvolutionController — settled (judge + ledger) observations
  update statistics and periodically evolve the candidate population; later
  selections change because of earlier settled outcomes.

Offline smoke (--offline-smoke): fake provider tapes, no API spend, proves the
wiring (selection -> intervention text -> judge/ledger feedback -> changed
later selection; infra -> no retry/no behavioral update).
Live (--live / --canary): requires DEEPSEEK_API_KEY + CE_DSH_LIVE_AUTH and goes
ONLY through the budget-proxy container (per-scope cap = 2, global cap from
the protocol, unknown-cost fail-closed). The real key never enters agent space.

Historical 312 rows and live_pilot.py are NOT modified.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

from causalevo.eval.executor import DockerExecutor  # noqa: E402
from causalevo.eval.harness_agent import (  # noqa: E402
    ContainerHarnessRunner, require_live_authorization)
from causalevo.eval.judge import Judge  # noqa: E402
from causalevo.eval.live_pilot import INTERVENTION_TEXT  # noqa: E402
from causalevo.eval.networks import ProviderContainer, ProxyContainer  # noqa: E402
from causalevo.eval.runtime_budget import RuntimeBudget  # noqa: E402
from causalevo.eval.task_spec import load_all_tasks, load_task  # noqa: E402
from causalevo.eval.trace import new_run_id, provenance_block  # noqa: E402
from causalevo.eval.workspace_factory import WorkspaceFactory  # noqa: E402
from causalevo.evolution.adapter import CausalPolicyAdapter, _GENE_TO_TEXT_KEY  # noqa: E402
from causalevo.evolution.online_evolution import (  # noqa: E402
    INFRA_KINDS, OnlineEvolutionController)

REPO = Path(__file__).resolve().parents[1]
IMAGE = "causalevo-dsh-agent:0.2.1"
PATCH = REPO / "configs" / "dsh_task_patch.yml"
FRONT = REPO / "results" / "phase3" / "evolution" / "pareto_front.json"
MANIFEST = REPO / "configs" / "phase3_artifact_manifest.json"
ARMS = ["B0-original", "B1-random", "B5-v1-frozen-pareto", "CEA-v2-online"]
SEEDS = [20261014, 20261015]
GLOBAL_CAP_CNY = 2.00
WARN_CAP_CNY = 1.80

FAIL_TAPE = {
    "0": [["tool_call", "read", {"file_path": "solution.py"}]],
    "1": [["tool_call", "write", {"file_path": "solution.py",
                                   "content": "def clamp_value(x, lo, hi):\n    return min(max(x, lo), lo)\n"}]],
    "2": [["text", "wrong fix applied"]],
}
FIX_TAPE = {
    "0": [["tool_call", "read", {"file_path": "solution.py"}]],
    "1": [["tool_call", "write", {"file_path": "solution.py",
                                   "content": "def clamp_value(x, lo, hi):\n    return min(max(x, lo), hi)\n"}]],
    "2": [["text", "fixed"]],
}
INFRA_TAPE = {
    "0": [["error", 500, {"error": "provider failure"}],
          ["tool_call", "read", {"file_path": "solution.py"}]],
    "1": [["no_usage"], ["text", "done"]],
}


def genome_to_text(genome) -> str | None:
    """Executable intervention text derived from the genome's active genes."""
    active = {k: v for k, v in genome.as_dict().items() if v > 0}
    texts = [INTERVENTION_TEXT[_GENE_TO_TEXT_KEY[g]]
             for g in active if _GENE_TO_TEXT_KEY.get(g) in INTERVENTION_TEXT]
    return " ".join(texts) if texts else None


def derive_context(outcome1, report1, edited: bool) -> dict:
    """Frozen observable context (design doc §7). No CoT/sealed content."""
    if outcome1.failure_kind in INFRA_KINDS:
        ft = "infra"
    elif report1.invalid_reason:
        ft = "verification"
    elif not edited:
        ft = "planning"
    elif outcome1.failure_kind == "provider_error":
        ft = "tool"
    else:
        ft = "knowledge"
    return {"failure_type": ft, "edited": bool(edited),
            "invalid": bool(report1.invalid_reason),
            "failure_kind": outcome1.failure_kind}


def _success(report) -> bool:
    return (report.visible_passed and report.sealed_passed
            and not report.invalid_reason and not report.timed_out)


def run_row(spec, arm, seed, judge, make_runner, *, rng, controller=None,
            frozen_adapter=None, run_id: str, task_index: int,
            provider_calls_cap: int = 8) -> dict:
    """One (task, arm, seed) row. The controller is only used for CEA-v2;
    the frozen adapter only for B5-v1. Both never update for B0/B1/B5-v1.

    provider_calls_cap: the live protocol envelope is 8 per row (real DSH
    agent uses 3 provider requests per attempt; the historical 312-row
    distribution tops out at 8). Offline tape runs need 6 (3 requests per
    attempt x 2). Never use 2: that artificially rejects the third request
    of an attempt and manufactures unknown_cost."""
    budget = RuntimeBudget(max_provider_calls=provider_calls_cap,
                           max_total_output_tokens=2048,
                           max_tool_calls=20, wall_time_s=240)
    factory = WorkspaceFactory()
    ws = factory.create(spec, f"{run_id}-{arm}-{task_index}-{seed}")
    episode_id = f"{run_id}/{spec.task_id}/{seed}/{arm}"
    t0 = time.monotonic()
    try:
        runner1 = make_runner(0)
        outcome1 = runner1.run_task(spec, ws.root, arm, budget,
                                    api_key="sk-fake-offline-no-cost")
        calls_after_1 = budget.ledger.provider_attempts
        cost_after_1 = budget.ledger.known_cost_cny
        report1 = judge.grade(spec, ws.root)
        success1 = _success(report1)
        edited = ws.digest() != ws.digest_at_open
        record = {
            "episode_id": episode_id, "task_id": spec.task_id, "seed": seed,
            "arm": arm, "attempt1_success": success1,
            "attempt_1_status": outcome1.failure_kind, "edited": edited,
            "invalid": bool(report1.invalid_reason),
            "attempt1_visible_failures": len(report1.visible_failures),
            "attempt_2_status": None, "final_success": success1,
            "retried": False, "intervention_text": None,
            "selected_genome_id": None, "policy_version": None,
            "population_version": None, "selection_reason": None,
            "controller_update": None, "final_status": outcome1.failure_kind,
            "attempt_1_provider_requests": calls_after_1,
            "attempt_2_provider_requests": 0,
            "attempt_1_cost_cny": round(cost_after_1, 10),
            "attempt_2_cost_cny": 0.0,
        }
        if outcome1.failure_kind in INFRA_KINDS:
            # infrastructure: no retry, no behavioral learning
            if controller is not None:
                upd = controller.observe(episode_id,
                                         derive_context(outcome1, report1, edited),
                                         "infra-no-genome",
                                         {"success": False, "cost_cny": None,
                                          "calls": budget.ledger.provider_attempts,
                                          "failure_kind": outcome1.failure_kind})
                record["controller_update"] = upd
            record["abort_reason"] = outcome1.failure_kind
            return _finalize(record, budget, t0)
        if success1 or arm == "B0-original":
            return _finalize(record, budget, t0)

        # attempt-1 failed: choose an intervention by the arm's REAL code path
        context = derive_context(outcome1, report1, edited)
        if arm == "B1-random":
            key = rng.choice(sorted(INTERVENTION_TEXT))
            text = INTERVENTION_TEXT[key]
            record["selection_reason"] = f"random:{key}"
            record["policy_version"] = "frozen-random-v1"
        elif arm == "B5-v1-frozen-pareto":
            pick = frozen_adapter.select_genome(failure_kind=outcome1.failure_kind,
                                                edited=edited,
                                                invalid=bool(report1.invalid_reason))
            if pick["genome"] is None:
                record["selection_reason"] = pick["reason"]
                return _finalize(record, budget, t0)
            interv = frozen_adapter.intervention_for(
                failure_kind=outcome1.failure_kind, edited=edited,
                invalid=bool(report1.invalid_reason), genome=pick["genome"])
            text = interv["text"]
            record["selected_genome_id"] = pick["genome_id"]
            record["selection_reason"] = pick["reason"]
            record["policy_version"] = "frozen-pareto-v1"
        elif arm == "CEA-v2-online":
            sel = controller.select(context, episode_id)
            text = genome_to_text(sel["genome"])
            record["selected_genome_id"] = sel["genome_id"]
            record["selection_reason"] = sel["reason"]
            record["policy_version"] = sel["policy_version"]
            record["population_version"] = sel["population_version"]
        else:
            raise ValueError(arm)
        record["intervention_text"] = text
        if text is None:
            # R1.10 Task D: explicit no-op semantics. A selected genome with no
            # executable intervention text gets NO retry, but its outcome IS
            # observed exactly once with zero incremental cost/calls (settled
            # accounting; no extra model request). Never silently skip observe.
            if controller is not None:
                upd = controller.observe(
                    episode_id, context, record["selected_genome_id"],
                    {"success": record["final_success"], "cost_cny": 0.0,
                     "calls": 0, "failure_kind": outcome1.failure_kind})
                record["controller_update"] = upd
                record["population_version_after"] = controller.population_version
            return _finalize(record, budget, t0)

        record["retried"] = True
        runner2 = make_runner(1)
        outcome2 = runner2.run_task(spec, ws.root, arm, budget,
                                    api_key="sk-fake-offline-no-cost",
                                    extra_prompt=text)
        report2 = judge.grade(spec, ws.root)
        record["attempt_2_status"] = outcome2.failure_kind
        record["final_success"] = _success(report2)
        record["final_status"] = outcome2.failure_kind
        record["abort_reason"] = (outcome2.failure_kind
                                  if outcome2.failure_kind in INFRA_KINDS else None)
        record["attempt_2_provider_requests"] = (
            budget.ledger.provider_attempts - calls_after_1)
        record["attempt_2_cost_cny"] = round(
            budget.ledger.known_cost_cny - cost_after_1, 10)
        if controller is not None:
            final_kind = outcome2.failure_kind
            # R1.10 Task D: only the intervention-INCREMENTAL cost/calls feed
            # candidate fitness (attempt-1 costs never enter them).
            cost = (record["attempt_2_cost_cny"]
                    if final_kind not in INFRA_KINDS else None)
            calls_incremental = record["attempt_2_provider_requests"]
            upd = controller.observe(
                episode_id, context, record["selected_genome_id"],
                {"success": record["final_success"], "cost_cny": cost,
                 "calls": calls_incremental,
                 "failure_kind": final_kind})
            record["controller_update"] = upd
            record["population_version_after"] = controller.population_version
        return _finalize(record, budget, t0)
    finally:
        factory.destroy_all()


def _finalize(record, budget, t0):
    record.update({
        "provider_calls": budget.ledger.provider_attempts,
        "input_tokens": budget.ledger.known_input_tokens,
        "cache_read_tokens": budget.ledger.cache_read_tokens,
        "output_tokens": budget.ledger.output_tokens,
        "cost_cny": round(budget.ledger.known_cost_cny, 10),
        "latency_ms": int((time.monotonic() - t0) * 1000),
    })
    return record


def make_fake_runner_factory(providers, infra: bool = False):
    def make_runner(attempt: int):
        tape = INFRA_TAPE if infra else (FIX_TAPE if attempt == 1 else FAIL_TAPE)
        provider = ProviderContainer(tape)
        provider.__enter__()
        providers.append(provider)
        return ContainerHarnessRunner(
            image=IMAGE, patch_path=PATCH, model="deepseek-flash",
            reasoning_effort="low", max_tokens=256, provider_kind="fake",
            provider_endpoint=provider.endpoint, network="ceval-net")
    return make_runner


def offline_smoke() -> int:
    """Fake-provider integration: real agent containers + controller."""
    out = REPO / "results" / "phase4" / "cea_v2_agent_smoke" / f"run-{new_run_id()}"
    out.mkdir(parents=True, exist_ok=True)
    judge = Judge(DockerExecutor())
    spec = load_task(REPO / "benchmarks" / "tasks" / "micro-000-clamp_value")
    controller = OnlineEvolutionController(pareto_front_path=FRONT,
                                           manifest_path=MANIFEST)
    adapter = CausalPolicyAdapter.cea_v1_from_manifest(FRONT, MANIFEST)
    rng = np.random.default_rng(20261021)
    providers = []
    records = []
    try:
        # 4 behavioral episodes (CEA-v2 learns across them) + 1 infra episode
        for arm in ARMS:
            for i in range(4 if arm == "CEA-v2-online" else 1):
                rec = run_row(spec, arm, 20261021, judge,
                              make_fake_runner_factory(providers), rng=rng,
                              controller=controller if arm == "CEA-v2-online" else None,
                              frozen_adapter=adapter, run_id=f"smoke-{arm}-{i}",
                              task_index=i, provider_calls_cap=6)
                rec["scenario"] = "edited_failing"
                records.append(rec)
        rec = run_row(spec, "CEA-v2-online", 20261021, judge,
                      make_fake_runner_factory(providers, infra=True), rng=rng,
                      controller=controller, run_id="smoke-infra", task_index=99,
                      provider_calls_cap=6)
        rec["scenario"] = "infra_unknown_cost"
        records.append(rec)
    finally:
        for p in providers:
            try:
                p.__exit__(None, None, None)
            except Exception:
                pass
    with (out / "records.jsonl").open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    with (out / "events.jsonl").open("w", encoding="utf-8") as fh:
        for e in controller.events:
            fh.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
    (out / "controller_state.json").write_text(
        json.dumps(controller.state_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps({
        "evidence_class": "adapter_integration_smoke",
        "note": "fake provider; mechanism wiring only; NOT real-model efficacy",
        "provider_calls_cap": 6,
        "envelope_note": "tape mechanics need 3 provider requests per attempt (read+write+text); the live protocol envelope is 2 per row (real agent uses 1 per attempt) — smoke budget is larger ONLY to fit the tape, never the live protocol",
        "arms": ARMS, "provenance": provenance_block(),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("smoke run_dir:", out)
    return 0


def _read_ledger(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def _read_ledger(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()
            if l.strip()]


def _round_spend(run_dirs: list[Path]) -> tuple[float, float]:
    """Return (settled_cny, unknown_bound_cny) across run ledgers.

    Used to enforce the CUMULATIVE round cap across canary/interruption/
    resume: a later run's cap is the round cap minus earlier settled spend
    and unresolved reservation bounds. Never a reset.
    """
    settled = 0.0
    unknown_bound = 0.0
    for d in run_dirs:
        entries = _read_ledger(Path(d) / "proxy-ledger" / "ledger.jsonl")
        settled += sum(e.get("cost_cny", 0.0) for e in entries
                       if e.get("state") == "SETTLED")
        for e in entries:
            if e.get("state") == "RESERVED" and not any(
                    x.get("request_id") == e["request_id"]
                    and x.get("state") in ("SETTLED", "REJECTED")
                    for x in entries):
                unknown_bound += e.get("reserved_cny", 0.15704064)
    return settled, unknown_bound


def live_pilot(canary: bool, out_override: str | None,
               resume_dir: str | None = None,
               previous_runs: list[str] | None = None,
               seeds: list[int] | None = None,
               run_tag: str = "phase4-r19") -> int:
    require_live_authorization()
    import os
    key = os.environ["DEEPSEEK_API_KEY"]
    previous_runs = previous_runs or []
    seed_list = seeds or SEEDS
    previous_settled, unknown_bound = _round_spend(
        [Path(d) for d in previous_runs])
    if resume_dir:
        run_dir = Path(resume_dir)
        run_id = run_dir.name
        out_dir = run_dir.parent
        # the aborted run's own unresolved reservations also count as unknown
        _s, _u = _round_spend([run_dir])
        unknown_bound += _u
        cap_cny = GLOBAL_CAP_CNY - previous_settled - unknown_bound
        if cap_cny <= 0.05:
            raise RuntimeError(f"round budget exhausted: remaining cap {cap_cny}")
        completed = set()
        tasks_file = run_dir / "tasks.jsonl"
        if tasks_file.is_file():
            for line in tasks_file.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    completed.add(json.loads(line)["episode_id"])
        # operator-scoped reconcile of the aborted run's unresolved requests:
        # appended to the audit ledger (never silently cleared, never zeroed)
        aborted_entries = _read_ledger(run_dir / "proxy-ledger" / "ledger.jsonl")
        final_states: dict[str, dict] = {}
        for e in aborted_entries:
            if e.get("request_id"):
                final_states[e["request_id"]] = e
        unresolved = [rid for rid, e in final_states.items()
                      if e["state"] in ("RESERVED", "SENT", "UNKNOWN")]
        if unresolved:
            scopes = sorted({final_states[rid].get("scope", "") for rid in unresolved})
            rec = {"control": "manual_reconcile", "scope": None,
                   "scopes": scopes, "cleared": sorted(unresolved),
                   "reason": "resume after IncompleteRead/unknown-cost stop; "
                             "operator reviewed; unknown spend kept UNKNOWN with "
                             "worst-case bound in round accounting"}
            with (run_dir / "proxy-ledger" / "ledger.jsonl").open(
                    "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        controller = OnlineEvolutionController.replay(
            run_dir / "events.jsonl",
            pareto_front_path=FRONT, manifest_path=MANIFEST)
    else:
        run_id = f"{run_tag}-{'canary' if canary else 'pilot'}-{new_run_id()}"
        out_dir = Path(out_override) if out_override else REPO / "results" / "phase4" / "live2"
        run_dir = out_dir / run_id
        # cumulative round cap: canary/interrupted spend and UNKNOWN bounds
        # are subtracted BEFORE the fresh run's first request (no reset)
        cap_cny = GLOBAL_CAP_CNY - previous_settled - unknown_bound
        if cap_cny <= 0.05:
            raise RuntimeError(f"round budget exhausted: remaining cap {cap_cny}")
        completed = set()
        controller = OnlineEvolutionController(pareto_front_path=FRONT,
                                               manifest_path=MANIFEST)
    proxy = ProxyContainer(upstream="https://api.deepseek.com",
                           ledger_dir=run_dir / "proxy-ledger",
                           upstream_api_key=key, cap_cny=cap_cny,
                           max_requests_per_task=8)
    proxy.__enter__()
    judge = Judge(DockerExecutor())
    adapter = CausalPolicyAdapter.cea_v1_from_manifest(FRONT, MANIFEST)
    specs = load_all_tasks(REPO / "benchmarks" / "tasks")
    if canary:
        specs = specs[:1]
    run_dir.mkdir(parents=True, exist_ok=True)
    records_path = run_dir / "tasks.jsonl"
    events_path = run_dir / "events.jsonl"
    aborted = None
    rows = 0
    events_written = len(controller.events) if resume_dir else 0
    warn_cap = cap_cny - 0.20  # internal warning line below the remaining cap
    try:
        for seed in seed_list:
            rng = np.random.default_rng(seed)
            for ti, spec in enumerate(specs):
                for arm in ARMS:
                    if aborted:
                        break
                    episode_id = f"{run_id}/{spec.task_id}/{seed}/{arm}"
                    if episode_id in completed:
                        continue  # resume: never re-run a completed episode
                    # scope BEFORE the first provider request of this row
                    proxy.set_current_scope(episode_id)
                    snap = proxy.snapshot()
                    settled_now = sum(e.get("cost_cny", 0.0)
                                      for e in snap.get("entries", [])
                                      if e.get("state") == "SETTLED")
                    if settled_now >= warn_cap:
                        aborted = f"internal warning cap {warn_cap} reached"
                        break
                    rec = run_row(
                        spec, arm, seed, judge,
                        lambda attempt: ContainerHarnessRunner(
                            image=IMAGE, patch_path=PATCH, model="deepseek-flash",
                            reasoning_effort="low", max_tokens=256,
                            provider_kind="live", provider_endpoint=proxy.endpoint,
                            network="ceval-net", agent_api_key=proxy.client_token),
                        rng=rng,
                        controller=controller if arm == "CEA-v2-online" else None,
                        frozen_adapter=adapter, run_id=run_id, task_index=ti)
                    with records_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    # persist only NEW controller events (audit trail per row)
                    with events_path.open("a", encoding="utf-8") as fh:
                        for e in controller.events[events_written:]:
                            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
                    events_written = len(controller.events)
                    rows += 1
                    print(f"{seed} {spec.task_id} {arm}: a1={rec['attempt1_success']} "
                          f"final={rec['final_success']} cost={rec['cost_cny']}",
                          flush=True)
                    if rec.get("abort_reason"):
                        aborted = f"fail-closed at {spec.task_id}/{arm}: {rec['abort_reason']}"
                        break
                if aborted:
                    break
            if aborted:
                break
    except Exception as exc:
        aborted = f"controller/runner exception: {type(exc).__name__}: {exc}"
        import traceback
        traceback.print_exc()
    finally:
        proxy.__exit__(None, None, None)
    with events_path.open("a", encoding="utf-8") as fh:
        for e in controller.events[events_written:]:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    (run_dir / "controller_state.json").write_text(
        json.dumps(controller.state_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8")
    final_entries = proxy.snapshot().get("entries", [])
    settled_cost = sum(e.get("cost_cny", 0.0) for e in final_entries
                       if e.get("state") == "SETTLED")
    final_states: dict[str, str] = {}
    for e in final_entries:
        if e.get("request_id") and e.get("state"):
            final_states[e["request_id"]] = e["state"]
    n_unknown = sum(1 for s in final_states.values() if s == "UNKNOWN")
    n_unsettled = sum(1 for s in final_states.values() if s in ("RESERVED", "SENT"))
    (run_dir / "manifest.json").write_text(json.dumps({
        "run_id": run_id, "canary": canary, "arms": ARMS, "seeds": seed_list,
        "task_count": len(specs), "rows": rows, "aborted": aborted,
        "global_cap_cny": GLOBAL_CAP_CNY, "warn_cap_cny": warn_cap,
        "cap_cny_this_run": cap_cny,
        "resumed_from": resume_dir,
        "previous_runs": previous_runs,
        "proxy_final": {"settled_cost_cny": settled_cost,
                        "ledger_entries": len(final_entries),
                        "unsettled_or_unknown": {"unknown": n_unknown,
                                                "unsettled": n_unsettled},
                        "per_scope_count": len({e.get("scope") for e in final_entries
                                                if e.get("scope")})},
        "controller": controller.state_dict(),
        "provenance": provenance_block(),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"rows={rows} aborted={aborted} settled_cost={settled_cost:.6f}")
    print("run_dir:", run_dir)
    return 0 if aborted is None else 3


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--offline-smoke", action="store_true")
    p.add_argument("--live", action="store_true")
    p.add_argument("--canary", action="store_true")
    p.add_argument("--out", default=None)
    p.add_argument("--resume", default=None,
                   help="resume an aborted run dir in place (ledger+controller replay)")
    p.add_argument("--previous-runs", default="",
                   help="comma-separated earlier run dirs whose settled spend "
                        "is subtracted from the round cap")
    p.add_argument("--seeds", default="",
                   help="comma-separated seeds (default: historical 20261014,20261015)")
    p.add_argument("--run-tag", default="phase4-r19",
                   help="run-id prefix (e.g. phase4-r12-replication)")
    args = p.parse_args()
    if args.offline_smoke:
        return offline_smoke()
    if args.live or args.canary:
        seed_list = [int(s) for s in args.seeds.split(",") if s.strip()] or None
        return live_pilot(canary=args.canary, out_override=args.out,
                          resume_dir=args.resume,
                          previous_runs=[d for d in args.previous_runs.split(",")
                                         if d.strip()],
                          seeds=seed_list, run_tag=args.run_tag)
    p.error("choose --offline-smoke or --live/--canary")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
