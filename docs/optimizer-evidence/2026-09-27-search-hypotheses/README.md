# Isolated Chasca search hypotheses — 2026-09-27

Owner: [Go optimizer design](../../handoff/GCSIM_OPTIMIZER_GO_BACKEND_DESIGN.md).
This is a saved-input research gate, **not installed-backend or live UI acceptance**.
Temporary sources/binaries are made only by `managed_optimizer_experiment.py` and
removed after each job. Keep these compact receipts and the reproducer through
the integration gate; then retire rejected overlays. Never replace the original
saved run or the old matrix with these measurements.

## Controlled comparison

- Saved run: `all_sets-20260927-212145-2c1cb70d` (Chasca/Furina/Bennett/Ororon).
- Request SHA256: `8fc91b23f9c96ede6dd08ed88e7313c138119d7c52e34bdf67674095f89c8f8f`.
- Installed consumer remains `585aca6b49bd766a2b41fd5cc4392f6aeffd6463b824660f39736f62f55b1715`.
- Active engine: `gcsim-v2.45.0-20260927011932`, artifact SHA256
  `7df37b5224f655d271d9389686bf22445717e02e896df5e3aa22d1d698042f8c`.
- Exact saved config/seed/member-hash/source binding; two seeds 742031889/742031890.
  An unavailable capture fails closed, without calling GCSIM or using another engine.
- Actual CLI All Sets function, canonical inventory reference, full saved inventory,
  same rotation, infinite energy, fast mode, 7 groups × 7 rows (leader + 6 swaps).
  Only the capture provider is replaced by saved data in an isolated source copy.
- Compare all 49 formula scores/physical assignments for exact-reuse variants;
  for search-policy variants additionally inspect each retained bonus group,
  ordered leader quality and exported legal single-item replacements. Improvement
  is not a parity failure. One case cannot establish global-optimum/whole-matrix recall.
- Times below are **search replay**, excluding fresh engine capture, account
  assembly, normal-mode finalist simulations and compile time. They are not new
  button-to-result timings. All runs are serialized, not repeated n128/n500 stages.

## First isolated batch

| Variant | Search seconds | Trials | Outcome |
| --- | ---: | ---: | --- |
| Baseline | 132.262 | 790,687 | Exact 49-row match to saved run |
| Count shared source memory once | 136.189 | 790,687 | Exact match; no useful gain |
| 256-entry / 1,024,000-node caches | 124.965 | 790,687 | Exact match; modest gain, larger memory allowance |
| Lazy constant binding of full common DAG | 181.280 | 790,687 | Exact match; rejected for performance |
| Two-item refinement frontier per category | 105.277 | 217,013 | Same seven groups; six leaders unchanged, seventh +48.694 DPS |

Receipts: [baseline](baseline.json), [isolated variants](isolated.json).
The first baseline helper incorrectly reported zero lane subcounters; those
zeros are **not measurements**. Its top-level timing, work count, model counters
and exact 49-row fingerprint are valid. The helper was corrected before the
first variant batch; no saved-run timing was substituted for missing subcounters.

Lazy binding saved about 9 s inside BindSeconds, but enlarged the graphs handled
later. Specialization hits/misses changed from 3932/2514 to 2423/4023, and only
two entries fit at the end instead of twelve. This rejects the simple lazy
wrapper, not the general idea of binding and specializing in one operation.
The wrapper also has an intentionally private research-only invariant: fixed
effects disappear from its public input list while remaining in internal graph
coordinates. It must not be promoted as a general rebinding API unchanged.

The narrow frontier keeps all package screens, two cycles, joint package search
and final stabilization; it changes which item pairs are explored inside a local
refinement (2 instead of 8 items per category). It is **not guaranteed pruning or an exhaustive search**. The gain
is fewer candidate trials, not a larger time limit. A stronger local path can
also explain its +48.694 DPS: different greedy paths need not be nested as width
increases. Do not claim a universal speed/quality guarantee from this case.

## Further isolated preparation variants

| Variant | Search seconds | Trials | Outcome |
| --- | ---: | ---: | --- |
| Memoize exact target → resident program dispatch | 127.812 | 790,687 | Exact 49-row match; 1,272 repeated dispatches avoided |
| Freeze constants without intermediate CSE | 189.242 | 790,687 | Exact match; rejected for performance |
| Group equal constant ports into reusable variable templates | 131.626 | 790,687 | Exact match; no material speedup |

Receipt: [second isolated batch](second-isolated.json). The no-CSE variant raised
total allocations to 83.94 GB (cumulative churn, not simultaneous RAM), compared
with 28.06 GB for exact dispatch memoization. Its larger retained graphs fit only
two specialization entries and increased subsequent work. Removing reduction
work was therefore counterproductive, despite preserving numerical results.

The grouped-template attempt in that same process failed at compilation, before
any search: an already imported overlay module lacked the newly instrumented
`hypothesisStats` field while the later copied template contained its references.
This was experiment-version drift, **not a numerical or product failure**. Both
completed variants remain valid; the managed job was cleaned. The grouped
variant is rerun in a fresh process with the frozen, matching helper version.

That [fresh grouped-template run](grouped-constants-retry.json) passed arithmetic
controls and exact 49-row parity. It had at most 10 variable groups but only
147 template hits against 986 misses and 965 evictions (21 entries at the end).
Template-key work cost 0.659 s, template builds 8.167 s; overall binding remained
41.562 s. This bounded implementation did not deliver the hoped-for large gain.
Increasing its memory allowance would be another untested combination, not a
result demonstrated here. Neither this wrapper nor the simple lazy wrapper is
ready for generic public formula APIs without an explicit fixed-input contract.

Lane work records are diagnostic: `neutral_joint` contains cumulative snapshots,
so summing that lane's seconds does not give an additional disjoint search cost.

## Repeated control and quality confirmation

The [confirmation job](confirmation.json) repeated baseline and narrow frontier
in the same serialized job, including complete replacement-score comparisons:
132.780 s / 790,687 trials versus 104.015 s / 217,013 trials (**21.7% faster**).
Both stop at the same two-cycle work policy, not a timer. The narrow fingerprint
matches its first run. All 49 export rows pass inventory membership, slot/wearer
identity, unique physical IDs, distinct normalized bonus-group signatures and
single-replacement checks. Six groups retain their exact seven rows. In the
seventh, the leader gains 48.694 formula DPS and all six replacement scores also
improve (+34.469 to +48.694). Ordered top-seven leader deltas are
`[0, 0, 0, 0, 0, +47.880944, +0.812837]`; no retained group/row regresses.

This is a repeatable **formula-search** result for this saved request, not a new
ordinary-simulator DPS improvement claim. No new GCSIM runs or matrix validation
are implied. Cumulative allocations are still 29.13 GB baseline / 28.58 GB narrow,
so fewer trials do not automatically mean proportionally lower preparation or
allocation cost. Final reserved heap is not an observed peak-memory guarantee.

## Combined isolated gate

The [combined run](combined.json) joins the narrow frontier, larger bounded
program/specialization caches and exact resident-program dispatch memoization.
Search took **84.322 s**, versus 132.780 s for the repeated baseline (**36.5%
less time, 1.57x throughput**) and 104.015 s for narrow refinement alone.
It performs the same 217,013 trials as narrow refinement. Its fingerprint,
all seven leader assignments and all 49 formula scores match that confirmed
variant exactly. Six baseline groups remain unchanged; the seventh improves.
Both 2,096-context cycles are prepared, with zero unavailable models. The stop
is still the two-cycle policy, not a timeout or exhaustive-search proof.

There are 2,081 dispatch hits; binding costs 27.711 s and proposal/screen work
50.088 s. These are overlapping counters, not costs to add together. Cumulative
allocations fall to 21.51 GB, but final reserved heap rises to 712.7 MB decimal,
versus 532.3 MB in the repeated baseline. This is a memory tradeoff, not a free
cache win or a peak-RSS measurement. Build plus replay takes 105.922 s; it is
not a new live application timing. The installed consumer/engine are unchanged.

### Disposition and next gate

- Retain exact dispatch reuse and bounded cache-capacity tuning as integration
  candidates; preserve full input/source identity and private evaluation scratch.
- Keep the narrow frontier experimental: one repeatable case satisfies the
  observed no-regression comparison, not arbitrary-team recall. Before promotion,
  compare one additional saved case at a time and cover cross-item interactions.
  A wider fallback based only on a small local gradient is not a certified bound.
- Reject lazy full-graph binding and deferred CSE for performance. Shared-source
  accounting and bounded equal-port templates give no useful standalone speedup
  here. Do not carry their private view-contract shortcuts into production.
- The 30-second aspiration is **not achieved**. A further architectural candidate
  is to combine per-wearer specialization with effect binding, avoiding a full
  team program for each provisional package. It remains unimplemented/unmeasured
  and must retain cross-wearer dependencies, changing anchors, shared-item
  legality and full-team finalist evaluation. It is not the rejected naive lazy
  full-graph wrapper.

## Replacement expansion

The offscreen actual `GcsimBrowserWorkspace` reproduced a horizontal scrollbar
appearing when five replacement columns used 160px cards. The viewport changed
from 886×596 to 886×582. The old test failed on that scrollbar assertion.
Replacement cards now share the main cards' 104px width; the DPS delta has its
own line, and nested-grid spacing matches the parent. All five focused result
tests pass, including unchanged viewport/header/wearer positions after expansion
and collapse. No deferred scroll-restoration timer was retained. Physical user
interaction remains unverified; Computer Use and app restart were not performed.

## Remaining architecture audit and matrix follow-up

The user subsequently authorized a paired matrix gate before promotion; see
[current matrix evidence](matrix/README.md). The old inventory is not a valid
same-input baseline. Freeze one current request for both algorithms, preserve
the old receipt as context, and keep Gaming's separate rotation exception.

Read-only code inspection finds no evidence that 84 s is an optimal runtime:

1. `setcontext.NeutralModel.Resolve` binds a full-team program on a program-cache
   miss; `search.candidateRun` then requests `Panel.ArtifactProgram`, which
   specializes that program for the variable wearer on a second cache miss.
   Simply deferring constants and folding them together with the anchor was
   ALREADY tried by `lazy_constants`, and lost:181s. Its full-size scratch,
   baseline evaluation and per-specialization traversal remain downstream.
   A genuinely different hypothesis needs a direct candidate-specific prepared
   plan: reuse fixed/dependency-disjoint branches and avoid constructing/evaluating
   a full-team view when only a local reduced program is consumed. Retain the
   entire team objective and cross-owner edges; symbolic effects can initially
   use the existing route. This new plan is **not implemented or timed**; merely
   renaming lazy binding as a fused pass is not a new optimization.
   More precisely, immutable regions must be partitioned by propagated artifact
   AND effect dependencies, with exact keys over each region's true inputs and
   shared cross-owner regions. Reuse must cross different package vectors:
   `ArtifactProgram.Evaluate` already recomputes affected nodes for supported
   dependency-mask widths, and exact specialization hits already reuse nodes.
   Measure nodes rebuilt, allocation/copy volume, region hit rate and paired
   time; hashing/linking can erase the expected benefit. This is a high-risk
   representation experiment, not a safe removal of a supposedly redundant pass.
2. `domain.ArtifactVectors` reconstructs item arrays for each local search even
   when inventory, wearer and coordinate layout repeat. An immutable run-owned
   numeric inventory view could be reused. Weights and occupied physical IDs
   remain anchor-dependent and must not be reused merely because sets match.
   `ForPackages` already shares the inventory; it rebuilds coordinates and
   validates twenty assigned IDs, not the whole database.
3. `NeutralBinding` can prebuild fixed port query lists, chronological query
   indices and catalog lookups currently assembled inside rule replays.
   Components, interacting groups, world snapshots, bound programs and exact
   specializations already have caches: do not present these as missing features.
   Combined Chasca rule replay costs8.046s inside12.381s rule work, whereas
   binding costs27.711s. Removing source interpretation alone cannot reach30s.
4. Source ASTs could be compiled into immutable execution instructions rather
   than dispatched as AST nodes by `ruleVM` on every callback. This is distinct
   from parsing-cache work, but is a higher-risk interpreter rewrite with an
   observed limited time ceiling on Chasca. Fresh per-replay state, declaration
   order, closures, task timing and shared modifier interactions remain required.
5. Per-package screens in one wearer block share a fixed anchor and run
   sequentially. Bounded parallel screens with deterministic result merging
   are an untested wall-time hypothesis, not less computational work; current
   mutable caches/scratch cannot simply be shared between workers. Memory and
   unchanged work-budget/Finish behavior need explicit controls.

The active engine's `pkg/optimization/opt_damage.go` and `details.go` were also
inspected. Its existing KQM substat optimizer obtains finite-difference weights
by rerunning simulations (25 iterations in its non-ER phase), not by exposing
an already-solved account-item/set allocation. It is not an overlooked direct
replacement for this inventory search. Set arithmetic/guards live in source
constructors/callbacks (e.g. Tenacity); the inspected `config.yml` contains
registry metadata, not a ready rotation-conditioned bonus table.

Rotation determines initial hit/event evidence and actual schedule-changing
exceptions, but ordinary package and item searches already reuse that evidence
inside a run. Most remaining repeated preparation is therefore not an unavoidable
cost of changing rotations. None of these additional hypotheses is accepted as
a measured speedup or quality-preserving implementation yet.

## Reproduction

Use `tools/experiments/gcsim/search_hypotheses/run.py` only under the managed
runner, with `--saved-run`, `--variants` and a compact `--receipt` path.
There is no install option. Arithmetic controls precede each replay. Source
overlays are guarded by exact expected snippets; source drift fails rather than
quietly running a different experiment. The binary and engine hashes are checked
after every completed replay. Final heap counters, where present, are **not peak
resident-memory measurements**.
