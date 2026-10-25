"""CE-DSH-P4-R1.8 Task C — deterministic synthetic validation of the CEA-v2
online evolutionary controller (offline, zero API calls, no docker).

A prequential mechanism test: every arm SELECTS first, then observes only that
episode's settled synthetic outcome, then updates for later episodes. No arm
ever sees a future row. All randomness is seeded or hash-derived, so the whole
run is byte-for-byte reproducible (episodes.jsonl / summary.json /
ablations.json are identical across reruns; manifest.json additionally carries
the run id and wall-clock provenance).

Synthetic reward environment (PREDECLARED, frozen in this file — the regime
spec below is hashed into the manifest):

  stationary_contextual   — each failure_type has a distinct best effective
                            phenotype; stationary for the whole stream.
  abrupt_shift            — at shift_at, the tool-context reward table flips
                            (best effective phenotype changes mid-stream) and
                            the context mix becomes tool-heavy.
  success_cost_tradeoff   — in the verification context the success-argmax
                            phenotype is expensive while a cheaper phenotype
                            wins the lambda-scalarized score; the tool context
                            is unambiguous. Tests multi-objective selection.
  iid_noise               — every phenotype in every context is Bernoulli(0.45)
                            with identical cost/calls: there is NO signal, so
                            any "learning" is overfitting and adaptation should
                            NOT win. Negative control regime.

Outcomes are deterministic given (regime, episode_index, failure_type,
phenotype): success = uhash(...) < p. Every arm faces the SAME context stream
per regime and the SAME outcome envelope per (episode, phenotype).

Arms: random, rule (fixed frozen mapping), static_pareto (frozen Pareto front
via CausalPolicyAdapter.cea_v1_from_manifest + select_genome), linucb_frozen
(frozen snapshot trained from the manifest-pinned sweep — training code reused
verbatim from scripts/run_phase4_v2_offline.py, read-only), cea_v2 (the
OnlineEvolutionController under its frozen default config).

Ablations of cea_v2: no_update (never observes), no_variation
(mutation_p=0, n_offspring=0), no_context (failure_type scrubbed to
"unknown"), single_objective (lambda_cost=lambda_calls=0).

KNOWN CONTROLLER DEFECT DISCOVERED BY THIS VALIDATION (disclosed, not hidden):
under the frozen defaults the controller livelocks inside _evolve() once the
population holds > 16 - n_offspring of the 16 possible effective phenotypes:
the offspring loop requires n_offspring NOVEL phenotypes, unmeasured offspring
are never evicted, and once per-context incumbents outscore the exploration
bonus offspring stop being measured, so free phenotype slots drain to zero.
Empirically the 4th evolve (behavioral observation 16) cannot terminate in
EVERY regime here. The driver therefore installs a structural guard: it knows
the exact termination precondition (unique phenotypes in the population
> 16 - n_offspring at the moment an evolve would trigger) and TRUNCATES the
arm before the hanging observe, recording terminated=
"controller_livelock_phenotype_exhaustion" with the guard state. Truncated
prefixes are reported as-is; full-horizon arms run the whole stream. This is
the honest output of a mechanism test: the frozen controller, as shipped,
cannot run more than ~15 behavioral episodes in a convergent environment.

evidence_class = "synthetic_mechanism_test": these regimes exercise the
mechanism; they are NOT evidence of real-agent improvement.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from causalevo.eval.trace import new_run_id, provenance_block  # noqa: E402
from causalevo.eval.live_pilot import INTERVENTION_TEXT  # noqa: E402
from causalevo.evolution.adapter import (  # noqa: E402
    CausalPolicyAdapter, _GENE_TO_TEXT_KEY, canonical_sha256)
from causalevo.evolution.genome import InterventionGenome  # noqa: E402
from causalevo.evolution.online_evolution import (  # noqa: E402
    OnlineEvolutionController, effective_phenotype)
from causalevo.evolution.policy import ACTIONS, LinUCBPolicy  # noqa: E402
from causalevo.evolution.reward import compute_reward  # noqa: E402
from causalevo.intervention.generator import INTERVENTION_LIBRARY  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
FRONT = REPO / "results" / "phase3" / "evolution" / "pareto_front.json"
MANIFEST = REPO / "configs" / "phase3_artifact_manifest.json"
SWEEP = REPO / "results" / "phase3" / "replay_sweep" / "sweep_results.jsonl"
DEFAULT_OUT_ROOT = REPO / "results" / "phase4" / "cea_v2_offline"

EXPERIMENT_VERSION = "p4-r1.8-cea-v2-offline"
EVIDENCE_CLASS = "synthetic_mechanism_test"
DISCLAIMER = ("Synthetic regimes are mechanism tests ONLY: they exercise "
              "selection/observation/update/evolution wiring under controlled "
              "reward tables. They are NOT evidence of real-agent improvement, "
              "algorithm generalization, or NSGA-III superiority on real "
              "tasks. No real model was invoked anywhere in this run.")
SEED = 20261024
LAMBDA_COST = 50.0
LAMBDA_CALLS = 0.02
INFRA_EVERY = 37  # episode indices i % 37 == 36 are infrastructure failures

T = "replace_unknown_tool_with_read"
R = "prepend_read_step"
B = "break_repeat_with_read"
V = "append_readback_and_fix"
TRANSFORMS = [T, R, B, V]
IDENTITY = ("identity",)

# cost/calls envelope (equivalent for every arm; the controller's lambda
# values scalarize with exactly these weights)
COST = {"base": 0.0002, T: 0.0003, R: 0.0001, B: 0.0002, V: 0.0004}
CALLS = {"base": 1, T: 1, R: 1, B: 1, V: 2}
OTHER_COST = 0.0001   # identity / non-phenotype transforms (e.g. inject_fix_after_write)
OTHER_CALLS = 1

_REG1_EFFECTS = {
    "tool":         {T: +0.30, R: +0.10, B: +0.10, V: -0.25},
    "verification": {T: +0.15, R: -0.25, B: +0.10, V: +0.30},
    "planning":     {T: -0.10, R: +0.35, B: -0.10, V: -0.20},
    "knowledge":    {T: -0.20, R: -0.10, B: +0.30, V: +0.15},
}
_SHIFT_TOOL_B = {T: -0.20, R: -0.10, B: -0.30, V: +0.45}

REGIMES: dict[str, dict] = {
    "stationary_contextual": {
        "n_episodes": 160, "base_p": 0.30,
        "context_mix": {"tool": .25, "verification": .25,
                        "planning": .25, "knowledge": .25},
        "effects": _REG1_EFFECTS,
        "description": ("stationary context-conditioned rewards; each "
                        "failure_type has a distinct best effective phenotype"),
    },
    "abrupt_shift": {
        "n_episodes": 240, "base_p": 0.30, "shift_at": 8,
        "context_mix": {"tool": .25, "verification": .25,
                        "planning": .25, "knowledge": .25},
        "context_mix_after": {"tool": .70, "verification": .10,
                              "planning": .10, "knowledge": .10},
        "effects": _REG1_EFFECTS,
        "effects_after": {**_REG1_EFFECTS, "tool": _SHIFT_TOOL_B},
        "description": ("abrupt reward+context shift at episode 8: the tool "
                        "context's best effective phenotype flips from the "
                        "tool bundle (T,R,B) to the verification phenotype "
                        "(T,V) among frozen-front members — the unconstrained "
                        "post-shift oracle is the singleton (V,) — and the "
                        "context mix becomes tool-heavy. The shift is placed "
                        "early on purpose: under frozen defaults the CEA-v2 "
                        "controller livelocks at behavioral observation 16 "
                        "(see known_defects), so only an early shift leaves a "
                        "post-shift window inside the controller's maximum "
                        "viable horizon; frozen arms demonstrate the full "
                        "232-episode post-shift regret."),
    },
    "success_cost_tradeoff": {
        "n_episodes": 160, "base_p": 0.30,
        "context_mix": {"tool": .50, "verification": .50},
        "effects": {
            "tool":         {T: +0.40, R: +0.35, B: -0.05, V: -0.20},
            "verification": {T: +0.15, R: +0.52, B: -0.05, V: +0.50},
        },
        "cost_multiplier": {"verification": {V: 4.0}},
        "calls_extra": {"verification": {V: 1}},
        "description": ("context-dependent success/cost trade-off: in the "
                        "verification context the success-argmax phenotype "
                        "(tool+verification genes) is expensive (verification "
                        "transform cost x4, +1 call) while the lambda-"
                        "scalarized argmax is the cheaper tool bundle; the "
                        "tool context is unambiguous."),
    },
    "iid_noise": {
        "n_episodes": 160,
        "flat": {"p": 0.45, "cost_cny": 0.0005, "calls": 3},
        "context_mix": {"tool": .25, "verification": .25,
                        "planning": .25, "knowledge": .25},
        "description": ("negative control: i.i.d. Bernoulli(0.45) rewards "
                        "with identical cost/calls for every phenotype in "
                        "every context. There is no signal; any adaptation "
                        "is overfitting and should NOT win."),
    },
}

KNOWN_DEFECTS = [{
    "id": "CEA-V2-D1",
    "severity": "blocking for long-horizon online operation",
    "summary": ("OnlineEvolutionController._evolve() livelocks once the "
                "population holds more than 16 - n_offspring of the 16 "
                "possible effective phenotypes."),
    "mechanism": ("offspring generation loops until n_offspring NOVEL "
                  "phenotypes are found; unmeasured offspring are protected "
                  "from eviction forever; once per-context incumbents score "
                  "above the exploration bonus (0.55) offspring stop being "
                  "measured, so free phenotype slots drain monotonically. "
                  "Under the frozen defaults (update_every=4, n_offspring=4, "
                  "max_population=16) the 4th evolve — behavioral observation "
                  "16 — cannot terminate."),
    "reproduction": ("run scripts/run_cea_v2_offline.py: every evolving arm "
                     "is truncated by the structural guard at episode 15 in "
                     "every regime (guard precondition: unique phenotypes "
                     "> 16 - n_offspring at evolve time)."),
    "consequence": ("cea_v2, cea_v2_no_context and cea_v2_single_objective "
                    "are truncated to a 15-episode prefix in all regimes; "
                    "their cumulative metrics cover only that prefix and are "
                    "NOT comparable to full-horizon arms — compare "
                    "regret_per_behavioral_episode and success_rate only, "
                    "and treat the livelock itself as the validation's "
                    "primary finding."),
}]

# fixed rule policy (frozen at build time; mirrors the B1 taxonomy rule at the
# genome level, mapped onto the front's effective phenotypes)
RULE_MAP = {
    "tool": (T, R, B),
    "verification": (T, V),
    "planning": (R,),
    "knowledge": (B, V),
}

# LinUCB action -> context failure_type used by the frozen snapshot arm
FT_TO_LT = {"tool": "tool_failure", "verification": "verification_failure",
            "planning": "planning_failure", "knowledge": "knowledge_failure"}

# frozen action -> intervention text (same frozen table as
# scripts/run_phase4_v2_offline.py; recorded for logging only)
ACTION_TO_TEXT = {
    "lib:tool_failure": INTERVENTION_TEXT["tool_validation"],
    "lib:planning_failure": INTERVENTION_TEXT["planning"],
    "lib:verification_failure": INTERVENTION_TEXT["verification"],
    "lib:knowledge_failure": INTERVENTION_TEXT["read_before_write"],
    "lib:strategy_failure": INTERVENTION_TEXT["planning"],
    "lib:execution_failure": None,
    "lib:unknown": None,
}


# ---------------------------------------------------------------- environment
def uhash(*parts: object) -> float:
    """Deterministic uniform in [0, 1) from a SHA-256 draw."""
    h = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def env_params(regime: str, episode_index: int, failure_type: str,
               phenotype: tuple[str, ...]) -> tuple[float, float, int]:
    """(success_prob, cost_cny, calls) — the exact, deterministic envelope."""
    spec = REGIMES[regime]
    if "flat" in spec:
        f = spec["flat"]
        return f["p"], f["cost_cny"], f["calls"]
    effects = spec["effects"]
    shift = spec.get("shift_at")
    if shift is not None and episode_index >= shift:
        effects = spec["effects_after"]
    vm = spec.get("cost_multiplier", {}).get(failure_type, {})
    ve = spec.get("calls_extra", {}).get(failure_type, {})
    p = spec["base_p"] + sum(effects.get(failure_type, {}).get(t, 0.0)
                             for t in phenotype)
    p = min(0.98, max(0.02, p))
    cost = COST["base"] + sum(COST.get(t, OTHER_COST) * vm.get(t, 1.0)
                              for t in phenotype)
    calls = CALLS["base"] + sum(CALLS.get(t, OTHER_CALLS) + ve.get(t, 0)
                                for t in phenotype)
    return p, cost, calls


def env_outcome(regime: str, episode_index: int, failure_type: str,
                phenotype: tuple[str, ...]) -> dict:
    """One settled synthetic episode outcome (deterministic)."""
    p, cost, calls = env_params(regime, episode_index, failure_type, phenotype)
    success = uhash(SEED, regime, episode_index, failure_type,
                    ",".join(phenotype)) < p
    return {"success": bool(success), "cost_cny": float(cost),
            "calls": int(calls), "failure_kind": "none"}


def expected_score(regime: str, episode_index: int, failure_type: str,
                   phenotype: tuple[str, ...]) -> float:
    p, cost, calls = env_params(regime, episode_index, failure_type, phenotype)
    return p - LAMBDA_COST * cost - LAMBDA_CALLS * calls


_ALL_PHENOTYPES = [tuple(sorted(c)) or None for r in range(5)
                   for c in itertools.combinations(TRANSFORMS, r)]
ALL_PHENOTYPES = [ph if ph else IDENTITY for ph in _ALL_PHENOTYPES]


def oracle_score(regime: str, episode_index: int, failure_type: str) -> float:
    """Best achievable expected scalar score over ALL 16 effective phenotypes
    (the controller may discover non-front phenotypes via mutation; the oracle
    must cover them so regret stays >= 0)."""
    return max(expected_score(regime, episode_index, failure_type, ph)
               for ph in ALL_PHENOTYPES)


def context_stream(regime: str) -> list[dict]:
    """The episode stream for a regime — generated ONCE and shared by all arms."""
    spec = REGIMES[regime]
    rng = np.random.default_rng(SEED + {
        "stationary_contextual": 11, "abrupt_shift": 22,
        "success_cost_tradeoff": 33, "iid_noise": 44}[regime])
    stream = []
    for i in range(spec["n_episodes"]):
        mix = spec["context_mix"]
        if spec.get("shift_at") is not None and i >= spec["shift_at"]:
            mix = spec["context_mix_after"]
        fts = sorted(mix)
        ps = np.array([mix[k] for k in fts], dtype=float)
        ps /= ps.sum()
        ft = fts[int(rng.choice(len(fts), p=ps))]
        stream.append(context_for(ft, infra=(i % INFRA_EVERY == INFRA_EVERY - 1)))
    return stream


def context_for(failure_type: str, infra: bool) -> dict:
    """Observable-evidence context; flags follow the frozen derivation rules
    of docs/PHASE4_R1_8_ONLINE_EVOLUTION_DESIGN.md §7."""
    if infra:
        return {"failure_type": "infra", "edited": True, "invalid": False,
                "failure_kind": "budget_stop"}
    return {
        "tool": {"failure_type": "tool", "edited": True, "invalid": False,
                 "failure_kind": "provider_error"},
        "verification": {"failure_type": "verification", "edited": True,
                         "invalid": True, "failure_kind": "none"},
        "planning": {"failure_type": "planning", "edited": False,
                     "invalid": False, "failure_kind": "none"},
        "knowledge": {"failure_type": "knowledge", "edited": True,
                      "invalid": False, "failure_kind": "none"},
    }[failure_type]


# ------------------------------------------------------------------- helpers
def front_candidates() -> list[InterventionGenome]:
    """Effective-phenotype-deduplicated front members, in front order."""
    front = json.loads(FRONT.read_text(encoding="utf-8"))
    out, seen = [], set()
    for member in front:
        g = InterventionGenome.from_dict(member["genome"])
        ph = effective_phenotype(g)
        if ph in seen:
            continue
        seen.add(ph)
        out.append(g)
    return out


def genome_text(genome: InterventionGenome | None) -> str | None:
    """Genome -> intervention text via the frozen gene->text mapping
    (adapter._GENE_TO_TEXT_KEY + live_pilot.INTERVENTION_TEXT)."""
    if genome is None:
        return None
    texts = []
    for gene, val in genome.as_dict().items():
        if val > 0:
            key = _GENE_TO_TEXT_KEY.get(gene)
            if key and key in INTERVENTION_TEXT:
                texts.append(INTERVENTION_TEXT[key])
    return " ".join(texts) if texts else None


def train_linucb_snapshot() -> tuple[LinUCBPolicy, str]:
    """Frozen LinUCB snapshot from the manifest-pinned sweep. Training code
    reused verbatim (read-only) from scripts/run_phase4_v2_offline.py
    (_train_linucb_snapshot): fixed order = file order."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = manifest["artifacts"][
        "results/phase3/replay_sweep/sweep_results.jsonl"]["sha256"].strip().lower()
    actual = canonical_sha256(SWEEP)
    if actual != expected:
        raise ValueError(f"sweep hash mismatch: expected {expected}, file has {actual}")
    rows = [json.loads(l) for l in SWEEP.read_text(encoding="utf-8").splitlines()]
    policy = LinUCBPolicy(alpha=0.5)
    for r in rows:
        state = {"failure_type": r["true_failure"], "prompt_chars": 100,
                 "n_visible_checks": 3}
        reward = compute_reward(r["success_delta"], r["cost_delta_cny"])
        policy.update(state, r["intervention_id"], reward)
    snapshot = policy.to_dict()
    sha = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
    return policy, sha


# ---------------------------------------------------------------------- arms
class ArmResult:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.truncated: dict | None = None


def _armspecs() -> dict[str, dict]:
    return {
        "random": {"kind": "random", "group": "arm",
                   "description": "uniform random over the deduplicated front "
                                  "phenotypes (seeded); never updates"},
        "rule": {"kind": "rule", "group": "arm",
                 "description": "fixed frozen failure_type -> front-phenotype "
                                "rule; never updates"},
        "static_pareto": {"kind": "static_pareto", "group": "arm",
                          "description": "frozen Pareto front via "
                                         "CausalPolicyAdapter.cea_v1_from_manifest "
                                         "+ frozen select_genome rule; never updates"},
        "linucb_frozen": {"kind": "linucb_frozen", "group": "arm",
                          "description": "frozen LinUCB snapshot trained from the "
                                         "manifest-pinned replay sweep (cea_v0); "
                                         "never updates"},
        "cea_v2": {"kind": "controller", "group": "arm", "config": {},
                   "description": "OnlineEvolutionController under its frozen "
                                  "default config (cea-v2-r1.8)"},
        "cea_v2_no_update": {"kind": "controller", "group": "ablation",
                             "config": {}, "no_observe": True,
                             "description": "ablation: never calls observe() — "
                                            "no online update; population_version "
                                            "must stay 0"},
        "cea_v2_no_variation": {"kind": "controller", "group": "ablation",
                                "config": {"mutation_p": 0.0, "n_offspring": 0},
                                "description": "ablation: no mutation/crossover — "
                                               "context-conditioned statistics only"},
        "cea_v2_no_context": {"kind": "controller", "group": "ablation",
                              "config": {}, "scrub_context": True,
                              "description": "ablation: failure_type scrubbed to "
                                             "'unknown' — no context features"},
        "cea_v2_single_objective": {"kind": "controller", "group": "ablation",
                                    "config": {"lambda_cost": 0.0, "lambda_calls": 0.0},
                                    "description": "ablation: success-only selection "
                                                   "(single-objective)"},
    }


ARMS = [n for n, s in _armspecs().items() if s["group"] == "arm"]
ABLATIONS = [n for n, s in _armspecs().items() if s["group"] == "ablation"]


def run_arm(regime: str, arm: str, *, _cache: dict | None = None) -> dict:
    """One prequential pass: select -> settled outcome -> update. Returns rows
    plus the arm-level summary. Deterministic."""
    spec = _armspecs()[arm]
    stream = context_stream(regime)
    cache = _cache if _cache is not None else {}
    ctl = None
    b5 = None
    b4 = None
    candidates = None
    rng = np.random.default_rng(SEED + 99)  # random arm only
    if spec["kind"] == "controller":
        ctl = OnlineEvolutionController(pareto_front_path=FRONT,
                                        manifest_path=MANIFEST,
                                        config=spec["config"])
    elif spec["kind"] == "static_pareto":
        b5 = cache.get("b5")
        if b5 is None:
            b5 = CausalPolicyAdapter.cea_v1_from_manifest(FRONT, MANIFEST)
            cache["b5"] = b5
    elif spec["kind"] == "linucb_frozen":
        b4 = cache.get("b4")
        if b4 is None:
            policy, _sha = train_linucb_snapshot()
            b4 = CausalPolicyAdapter.cea_v0(policy.to_dict())
            cache["b4"] = b4
    elif spec["kind"] in ("random", "rule"):
        candidates = cache.get("candidates")
        if candidates is None:
            candidates = front_candidates()
            cache["candidates"] = candidates
        if spec["kind"] == "rule":
            geno_by_ph = {effective_phenotype(g): g for g in candidates}

    result = ArmResult()
    pending = 0
    cumulative_regret = 0.0
    successes = 0
    behavioral = 0
    total_cost = 0.0
    total_calls = 0
    total_scalar = 0.0
    phenotypes_seen: set[tuple[str, ...]] = set()
    post_shift_tool: list[tuple[str, ...]] = []
    pre_shift_tool_last: tuple[str, ...] | None = None
    shift_at = REGIMES[regime].get("shift_at")

    for i, ctx in enumerate(stream):
        episode_id = f"{regime}-{i:04d}"
        infra = ctx["failure_kind"] == "budget_stop"
        # --- structural livelock guard (see KNOWN_DEFECTS CEA-V2-D1) ---
        if ctl is not None and not spec.get("no_observe"):
            unique_ph = len({c.phenotype for c in ctl.population})
            if (pending + 1 >= ctl.config["update_every"]
                    and unique_ph > 16 - ctl.config["n_offspring"]):
                result.truncated = {
                    "terminated": "controller_livelock_phenotype_exhaustion",
                    "at_episode_index": i,
                    "unique_phenotypes": unique_ph,
                    "population_size": len(ctl.population),
                    "population_version": ctl.population_version,
                    "evolution_updates": ctl.evolution_updates,
                    "pending_observations": pending,
                    "update_every": ctl.config["update_every"],
                    "n_offspring": ctl.config["n_offspring"],
                    "defect_id": "CEA-V2-D1",
                }
                break
        sel_ctx = dict(ctx)
        if spec.get("scrub_context"):
            sel_ctx["failure_type"] = "unknown"

        # ---------------- select FIRST (prequential) ----------------
        action = None
        policy_version = None
        population_version = None
        lineage = None
        reason = ""
        if spec["kind"] == "controller":
            sel = ctl.select(sel_ctx, episode_id)
            genome = sel["genome"]
            phenotype = tuple(sel["phenotype"])
            genome_id = sel["genome_id"]
            policy_version = sel["policy_version"]
            population_version = sel["population_version"]
            reason = sel["reason"]
            cand = next((c for c in ctl.population if c.genome_id == genome_id), None)
            if cand is not None:
                lineage = {"parent_ids": list(cand.parent_ids),
                           "born_generation": cand.born_generation}
            text = genome_text(genome)
        elif spec["kind"] == "random":
            genome = None if infra else candidates[int(rng.integers(len(candidates)))]
            genome_id = genome.genome_id if genome else None
            phenotype = tuple(effective_phenotype(genome)) if genome else None
            policy_version = "synthetic-random@seed20261024"
            reason = "seeded uniform choice over deduplicated front phenotypes"
            text = genome_text(genome)
        elif spec["kind"] == "rule":
            genome = None if infra else geno_by_ph[RULE_MAP[ctx["failure_type"]]]
            genome_id = genome.genome_id if genome else None
            phenotype = tuple(effective_phenotype(genome)) if genome else None
            policy_version = "synthetic-rule@frozen"
            reason = ("frozen failure_type->phenotype rule"
                      if genome else "infra: fail-closed, no retry")
            text = genome_text(genome)
        elif spec["kind"] == "static_pareto":
            pick = b5.select_genome(failure_kind=ctx["failure_kind"],
                                    edited=ctx["edited"], invalid=ctx["invalid"])
            genome = pick["genome"]
            genome_id = pick.get("genome_id") if genome else None
            phenotype = tuple(effective_phenotype(genome)) if genome else None
            policy_version = "cea-v1-static@" + b5.provenance["pareto_front_sha256"][:12]
            reason = pick["reason"]
            text = genome_text(genome)
        else:  # linucb_frozen
            if infra:
                state = {"failure_type": "execution_failure", "prompt_chars": 100,
                         "n_visible_checks": 3}
                cands = ["lib:execution_failure"]
            else:
                state = {"failure_type": FT_TO_LT[ctx["failure_type"]],
                         "prompt_chars": 100, "n_visible_checks": 3}
                cands = list(ACTIONS)
            sel = b4.select(state, cands)
            action = sel["selected_action"]
            transform = {iv.intervention_id: iv.tape_transform
                         for iv in INTERVENTION_LIBRARY}[action]
            phenotype = (transform,) if transform != "identity" else IDENTITY
            genome = None
            genome_id = None
            policy_version = sel["policy_version"]
            reason = f"frozen LinUCB snapshot selected {action}"
            text = ACTION_TO_TEXT.get(action)

        # ---------------- settled outcome for THIS episode only ----------------
        if infra:
            outcome = {"success": False, "cost_cny": 0.0, "calls": 0,
                       "failure_kind": "budget_stop"}
            regret = 0.0
            exp_score = 0.0
        else:
            outcome = env_outcome(regime, i, ctx["failure_type"], phenotype)
            exp_score = expected_score(regime, i, ctx["failure_type"], phenotype)
            regret = oracle_score(regime, i, ctx["failure_type"]) - exp_score
            behavioral += 1
            successes += int(outcome["success"])
            total_cost += outcome["cost_cny"]
            total_calls += outcome["calls"]
            phenotypes_seen.add(phenotype)
            if shift_at is not None and ctx["failure_type"] == "tool":
                if i >= shift_at:
                    post_shift_tool.append(phenotype)
                else:
                    pre_shift_tool_last = phenotype
        scalar = (float(outcome["success"]) - LAMBDA_COST * outcome["cost_cny"]
                  - LAMBDA_CALLS * outcome["calls"])
        total_scalar += scalar
        cumulative_regret += regret

        # ---------------- update for LATER episodes only ----------------
        update_event = None
        if ctl is not None and not spec.get("no_observe"):
            events_before = len(ctl.events)
            ret = ctl.observe(episode_id, sel_ctx, genome_id, outcome)
            update_event = dict(ret)
            if ret.get("evolved"):
                for e in ctl.events[events_before:]:
                    if e.get("kind") == "evolve":
                        update_event.update({"generation": e["generation"],
                                             "offspring": e["offspring"],
                                             "parents": e["parents"]})
            pending = 0 if ret.get("evolved") else pending + (1 if ret.get("updated") else 0)
        elif spec.get("no_observe"):
            update_event = {"updated": False, "reason": "no-update ablation: observe() never called"}

        result.rows.append({
            "experiment_version": EXPERIMENT_VERSION,
            "regime": regime, "arm": arm,
            "episode_id": episode_id, "episode_index": i,
            "context": ctx,
            "selected": {"genome_id": genome_id, "phenotype": list(phenotype) if phenotype else None,
                         "action": action, "intervention_text": text,
                         "reason": reason},
            "reward": {"success": outcome["success"], "cost_cny": outcome["cost_cny"],
                       "calls": outcome["calls"], "scalar_reward": scalar,
                       "expected_score": exp_score, "regret": regret},
            "policy_version": policy_version,
            "population_version_at_select": population_version,
            "lineage": lineage,
            "update_event": update_event,
            "cumulative_regret": cumulative_regret,
        })

    # ---------------- arm summary ----------------
    terminated = "completed"
    detail = None
    if result.truncated is not None:
        terminated = result.truncated["terminated"]
        detail = result.truncated
    summary = {
        "episodes_total": len(stream),
        "episodes_completed": len(result.rows),
        "terminated": terminated,
        "termination_detail": detail,
        "behavioral_episodes": behavioral,
        "infra_episodes": len(result.rows) - behavioral,
        "successes": successes,
        "success_rate": successes / behavioral if behavioral else None,
        "mean_cost_cny": total_cost / behavioral if behavioral else None,
        "mean_calls": total_calls / behavioral if behavioral else None,
        "total_scalar_reward": total_scalar,
        "cumulative_regret": cumulative_regret,
        "regret_per_behavioral_episode": (cumulative_regret / behavioral
                                          if behavioral else None),
        "phenotype_diversity": len(phenotypes_seen),
        "distinct_phenotypes": sorted("|".join(p) for p in phenotypes_seen),
        "evolution_updates": ctl.evolution_updates if ctl is not None else 0,
        "final_population_version": ctl.population_version if ctl is not None else 0,
    }
    if shift_at is not None:
        # post-shift adaptation target: best FROZEN-FRONT phenotype for the
        # tool context after the shift (arm-agnostic reference; the
        # unconstrained oracle is recorded separately in the regime spec).
        target = max(
            (tuple(effective_phenotype(g)) for g in front_candidates()),
            key=lambda ph: expected_score(regime, shift_at, "tool", ph))
        oracle_ph = max(ALL_PHENOTYPES,
                        key=lambda ph: expected_score(regime, shift_at, "tool", ph))
        hits = [ph == target for ph in post_shift_tool]
        first_hit = next((j for j, h in enumerate(hits) if h), None)
        stable = None
        for L in range(len(hits)):
            window = hits[L:L + 10]
            if window and sum(window) / len(window) >= 0.8:
                stable = L
                break
        if ctl is not None and result.truncated is not None and len(hits) < 10:
            lag_reason = ("controller livelocked before a measurable post-shift "
                          "window (tool-context episodes observed post-shift: "
                          f"{len(hits)}); adaptation lag not measurable — see "
                          "known_defects CEA-V2-D1")
        elif pre_shift_tool_last == target:
            lag_reason = ("arm already selected the post-shift target before the "
                          "shift (frozen/chance pick — NOT an adaptation event); "
                          "lag fields are formally recorded but vacuous")
        elif stable is None:
            lag_reason = ("target phenotype never reached an 80% trailing-window "
                          "share post-shift" + ("" if first_hit is None else
                                                f"; first hit at post-shift tool episode {first_hit}"))
        else:
            lag_reason = "adapted"
        summary["adaptation_lag"] = {
            "shift_episode": shift_at,
            "target_phenotype": list(target),
            "post_shift_oracle_phenotype": list(oracle_ph),
            "pre_shift_tool_last_phenotype": (list(pre_shift_tool_last)
                                              if pre_shift_tool_last else None),
            "post_shift_tool_episodes": len(hits),
            "first_hit_lag": first_hit,
            "stable_lag_80pct_window10": stable,
            "reason": lag_reason,
        }
    return {"rows": result.rows, "summary": summary}


# --------------------------------------------------------------------- main
def _config_payload() -> dict:
    return {
        "experiment_version": EXPERIMENT_VERSION,
        "seed": SEED,
        "lambda_cost": LAMBDA_COST,
        "lambda_calls": LAMBDA_CALLS,
        "infra_every": INFRA_EVERY,
        "cost_envelope": {k: v for k, v in COST.items()},
        "calls_envelope": {k: v for k, v in CALLS.items()},
        "other_cost": OTHER_COST, "other_calls": OTHER_CALLS,
        "arms": ARMS, "ablations": ABLATIONS,
        "regimes": {name: {k: v for k, v in spec.items() if k != "description"}
                    for name, spec in REGIMES.items()},
    }


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    run_id = args.run_id or new_run_id()
    out = args.out_root / f"run-{run_id}"
    suffix = 2
    while out.exists():
        out = args.out_root / f"run-{run_id}-{suffix}"
        suffix += 1
    out.mkdir(parents=True, exist_ok=False)

    config = _config_payload()
    config_sha = _sha(config)
    env_sha = _sha({name: {k: v for k, v in spec.items()}
                    for name, spec in REGIMES.items()})
    manifest_data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    front_sha = manifest_data["artifacts"][
        "results/phase3/evolution/pareto_front.json"]["sha256"]
    sweep_sha = manifest_data["artifacts"][
        "results/phase3/replay_sweep/sweep_results.jsonl"]["sha256"]

    cache: dict = {}
    summaries: dict[str, dict[str, dict]] = {}
    all_rows: list[dict] = []
    for regime in REGIMES:
        summaries[regime] = {}
        for arm in ARMS + ABLATIONS:
            res = run_arm(regime, arm, _cache=cache)
            summaries[regime][arm] = res["summary"]
            all_rows.extend(res["rows"])
            if not args.quiet:
                s = res["summary"]
                print(f"{regime:22s} {arm:24s} n={s['episodes_completed']:3d} "
                      f"succ={s['success_rate'] if s['success_rate'] is not None else float('nan'):.3f} "
                      f"regret={s['cumulative_regret']:8.3f} "
                      f"term={s['terminated']}", flush=True)

    with (out / "episodes.jsonl").open("w", encoding="utf-8") as fh:
        for row in all_rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    arms_summary = {regime: {arm: summaries[regime][arm] for arm in ARMS}
                    for regime in REGIMES}
    summary_doc = {
        "experiment_version": EXPERIMENT_VERSION,
        "evidence_class": EVIDENCE_CLASS,
        "real_agent_improvement_evidence": False,
        "note": DISCLAIMER,
        "known_defects": KNOWN_DEFECTS,
        "config_sha256": config_sha,
        "environment_sha256": env_sha,
        "seeds": {"master": SEED,
                  "context_stream": {"stationary_contextual": SEED + 11,
                                     "abrupt_shift": SEED + 22,
                                     "success_cost_tradeoff": SEED + 33,
                                     "iid_noise": SEED + 44},
                  "random_arm": SEED + 99,
                  "controller": 20261021},
        "artifact_hashes": {"pareto_front_sha256": front_sha,
                            "sweep_sha256": sweep_sha},
        "regimes": {name: {"description": spec["description"],
                           "n_episodes": spec["n_episodes"],
                           "shift_at": spec.get("shift_at")}
                    for name, spec in REGIMES.items()},
        "arms": {arm: _armspecs()[arm]["description"] for arm in ARMS},
        "results": arms_summary,
    }
    (out / "summary.json").write_text(
        json.dumps(summary_doc, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8")

    ablation_doc = {
        "experiment_version": EXPERIMENT_VERSION,
        "evidence_class": EVIDENCE_CLASS,
        "real_agent_improvement_evidence": False,
        "note": DISCLAIMER,
        "ablations": {arm: {"description": _armspecs()[arm]["description"],
                            "config_delta": _armspecs()[arm]["config"],
                            "no_observe": bool(_armspecs()[arm].get("no_observe")),
                            "scrub_context": bool(_armspecs()[arm].get("scrub_context"))}
                      for arm in ABLATIONS},
        "results": {regime: {arm: summaries[regime][arm] for arm in ABLATIONS}
                    for regime in REGIMES},
    }
    (out / "ablations.json").write_text(
        json.dumps(ablation_doc, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8")

    manifest_doc = {
        "run_id": out.name,
        "experiment_version": EXPERIMENT_VERSION,
        "evidence_class": EVIDENCE_CLASS,
        "real_agent_improvement_evidence": False,
        "note": DISCLAIMER,
        "task": "CE-DSH-P4-R1.8 Task C — deterministic synthetic validation",
        "known_defects": KNOWN_DEFECTS,
        "config": config,
        "config_sha256": config_sha,
        "environment_sha256": env_sha,
        "seeds": summary_doc["seeds"],
        "artifact_manifest": "configs/phase3_artifact_manifest.json",
        "artifact_manifest_sha256": canonical_sha256(MANIFEST),
        "pareto_front_sha256": front_sha,
        "sweep_sha256": sweep_sha,
        "controller_config_frozen": True,
        "provider": "none (pure synthetic arithmetic; zero API calls; no docker)",
        "episodes_recorded": len(all_rows),
        "outputs": ["manifest.json", "episodes.jsonl", "summary.json",
                    "ablations.json"],
        "provenance": provenance_block(),
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest_doc, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8")
    print(f"run_dir: {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
