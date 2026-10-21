# CE-DSH-P4-R1.7 — GPT Planner Independent Review

- Repository: yujian777555/CausalEvo-DSH
- Reviewed remote HEAD: 8286d38d38d6c1812e26225031a85690852f0068
- Implementation/test commit: 1f6c324af86c2d517358df823d757d426956150e
- Follow-up docs/status commit: 8286d38d38d6c1812e26225031a85690852f0068
- Decision: **R1.7 offline engineering accepted by source review; the R1.7 live-pilot proposal is NOT APPROVED as written.**
- Scope: source and artifact review on GitHub. GPT did not independently run the Windows/Docker test suite or reproduce the local route diagnostic.

## 1. Task A — digit-limit portability: ACCEPTED BY SOURCE REVIEW

The helper now distinguishes a positive interpreter digit limit from an absent/zero limit and emits a 5000-digit overflow fixture for the latter. The focused zero-limit test avoids changing global interpreter settings. Existing end-to-end corrupt-ledger assertions remain present. The executor reports 8/8 for the R1.6 suite and 575/575 overall; these are executor-reported results, not independently rerun by GPT.

## 2. Task B — route diagnostic artifact: ACCEPTED WITH STRICTLY SCOPED CLAIM

The sanitized JSON records the timestamp, proxy mode and TUN status, direct opener configuration, DNS/TCP/TLS details, rotated log hash, 128 logged flows and zero api.deepseek.com entries in the stated interval, and the Sangfor aTrust limitation. The report transparently explains why the earlier count of 109 differs from the later 128 count.

The raw rotated log is not committed, so the log-based route classification cannot be independently reproduced from GitHub alone. Accept the artifact as a faithful, scoped executor record only. It supports at most the claim that the observed direct-opener diagnostic did not traverse mihomo during that interval. It does not establish a universal or future TUN/underlay routing guarantee. No live authorization follows.

## 3. Task C — algorithm fidelity: ACCEPTED

The source audit correctly distinguishes:
- Offline NSGA-III search with measured tape-replay fitness: implemented/tested at small scale.
- Pareto artifact generation and external manifest pinning: implemented/tested, with six front entries but only four unique genomes and one member containing reserved genes.
- Runtime CEA-v1 behavior: static failure-conditioned selection from a frozen artifact.
- Runtime evolutionary feedback/update loop: not implemented.
- L4 recursive self-improvement: not implemented.
- Historical 312-row Phase 4 B4/B5 semantics: proxy heuristic and static bundle, not the later CEA adapter; historical records remain untouched.

The scientific conclusion is appropriately negative/neutral: the prior experiment does not establish algorithmic superiority, and the later adapter integration is fake-provider smoke evidence only.

## 4. Task D — pilot proposal: NOT APPROVED FOR LIVE EXECUTION

The proposal is useful as a draft, but the primary endpoint and actual implementation path need repair before any budget can be authorized.

### D1. Conditional recovery rate is not the proposed McNemar outcome

The existing implementation in scripts/analyze_phase4.py defines recovery_rate as success among rows where that arm's first attempt failed and a retry occurred. The denominator is therefore arm-specific. The proposal names this conditional recovery rate as the primary endpoint but proposes McNemar exact testing as if the outcome were a binary variable observed on a common paired denominator. These are not the same estimand.

Before any preregistration is approved, either:
- use final_success on every paired task-seed as the primary fixed-denominator binary endpoint for McNemar, and report conditional recovery as secondary/descriptive with its denominator and cluster-aware interval; or
- if recovery itself must be primary, construct a common pre-treatment failure set and branch the same frozen attempt-1 state into each intervention arm, then test paired recovery outcomes on that common set.

Do not choose the approach after seeing outcomes.

### D2. The proposed B5-v2 path is not wired into the current live runner

src/causalevo/eval/live_pilot.py still maps the historical B5 arm to the fixed CEAV1_BUNDLE. The CausalPolicyAdapter.cea_v1_from_manifest path is exercised by scripts/run_phase4_v2_offline.py using a fake provider. Thus the proposal describes a path that is not yet the current live runner path. A future experiment must use a separately versioned runner with tested adapter selection and prompt injection; do not alter or relabel the frozen 312 historical rows.

### D3. Power and effect decision rule are incomplete

The proposal has 52 task-seed pairs across 26 task clusters but no sensitivity/power analysis based on plausible discordant-pair rates. H1 states an effect of at least +0.10 while H0 states a difference at most zero, leaving the practical-effect threshold and statistical test as separate criteria without a complete decision rule. Clarify superiority testing, minimum relevant effect, confidence interval, and whether the run is confirmatory or only an exploratory feasibility pilot.

### D4. Task identity and budget envelope need exact freezing

The proposal says the task hash will be recorded in a future manifest but does not publish the actual task IDs and canonical hash. Also, its per-scope cap of 8 provider requests must be reconciled with the actual RuntimeBudget and BudgetProxy configuration in the exact runner; do not assume two attempts times four requests if the effective task budget differs. Freeze and test the exact ceilings before any live request.

## 5. Git and validation evidence

- Current remote HEAD is 8286d38d38d6c1812e26225031a85690852f0068.
- The executor reports the full suite as 575 passed, 0 failed, 0 skipped.
- Clean-clone and the 312-row recomputation were reported at 1f6c324af86c2d517358df823d757d426956150e.
- The subsequent 8286d38 commit changes only status.json and planner/executor_report.md; the executor explicitly states that this follow-up commit did not rerun clean-clone.
- GPT did not independently execute tests. Therefore, test and clean-clone results remain executor-reported.
- status.json at the reviewed HEAD still had stale top-level blockers and R1.6-era fields (including current_remote_head=b35e6d..., the completed digit-limit task as a blocker, and an old TUN wording). The Planner's follow-up status update corrects those metadata inconsistencies; it does not change code or test evidence.

## Final decision

**Accept R1.7 for offline engineering and algorithm-fidelity reporting. Do not approve the R1.7 pilot for live execution.**

Next: CE-DSH-P4-R1.8 — implement and validate a genuine offline runtime evolutionary update loop, repair the experiment estimand/statistical protocol, and test the new controller using deterministic synthetic and fake-provider scenarios. Real API calls remain zero until a later separate Planner approval and explicit user budget authorization.