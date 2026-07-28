# GCSIM Optimizer Technical Handoff

Last updated: 2026-07-28.

This document is the authoritative technical description of the current
optimizer backend. Historical M0-M14 implementation logs and superseded
runtime measurements were removed. Git history remains the source for that
history.

## 1. Current status

The current release targets are:

| Product operation | Current backend | Status |
| --- | --- | --- |
| Account artifacts, selected set pools | `optimizer_anytime_selected_service.py` | Current production path |
| Theoretical equal-investment 4p | `optimizer_theoretical_anytime_service.py` | Current production path |
| Theoretical equal-investment 2p+2p | `optimizer_theoretical_anytime_service.py` | Current production path |
| Account artifacts, every database set | `optimizer_all_set_service.py` | Bounded anytime v2; experimental until real-engine benchmark |

Every current production result means:

> best build found under the frozen, versioned work plan

It does not claim a mathematically exhaustive global optimum.

The superseded broad-response selected/theoretical services have been removed
after reduced-oracle, adversarial, randomized, runtime, and regression gates
passed. Current requests must not recreate or route through those old paths.

There are no accepted user-facing `Quick`, `Balanced`, or `Deep` speed modes.
The names of internal fidelity phases are `screen_8`, `refine_32`,
`validate_200`, and `rerace_1000`; they are not selectable product modes.

## 2. Product boundaries

### 2.1 Account: selected set pools

The optimizer reads the complete current artifact database. For each wearer,
the user selects one or more concrete set keys:

- one selected set is the simple/default case;
- several selected sets form one editable pool for that wearer;
- the source config's currently active set is only the default UI suggestion;
- the search still uses all eligible database artifacts that can form the
  selected package;
- the optional account `2p+2p` flag adds canonical distinct-set packages to
  the same account search.

No equipment, preset, Artiscan JSON, import generation, or “currently worn”
state participates in candidate truth. The database snapshot frozen into the
request is the artifact truth.

### 2.2 Account: all database sets

The all-database backend derives every trusted modeled five-star set represented
by eligible database artifacts, then uses the same bounded candidate,
four-wearer no-reuse, and multifidelity kernel as selected-set search. Its plan
identity is `all_database_sets_anytime_approx_v1`, version 2. It reports only
best-found bounded evidence and makes no exhaustive package-coverage or numeric
optimality claim. It remains experimental until a real-engine cold/warm
benchmark is recorded; this does not block the mandatory selected/theoretical
release paths.

### 2.3 Theoretical equal investment

Theoretical `4p` and theoretical `2p+2p` are separate typed operations. They:

- do not read the account artifact database;
- compare complete four-character states under the same GCSIM investment
  contract;
- use only trusted, modeled, five-star engine packages;
- return percent-to-best inside that theoretical operation, where rank 1 is
  exactly 100%;
- preserve concrete package identity in every candidate and cache key.

The UI checkbox may dispatch both operations, but their requests, caches,
evidence, and terminal results remain separate.

### 2.4 Four-star artifacts

Default eligibility is five-star only.

For account search, a four-star artifact is eligible only through an explicit
user-selected set/ID override already represented by the typed request.
The theoretical anytime domain is five-star only and currently has no explicit
four-star override contract.

## 3. Source map

### Shared contracts and frozen inputs

| Concern | Module |
| --- | --- |
| Versioned operation/request/result/progress contracts | `optimizer_product_contracts.py` |
| Trusted GCSIM engine/catalog binding | `optimizer_engine_context.py` |
| Prepared source-config shell | `optimizer_config_shell.py` |
| Read-only artifact database snapshot | `optimizer_artifact_database.py` |
| Immutable account run input | `optimizer_run_input.py` |
| Generic minimum-stat legality constraints | `optimizer_stat_constraints.py` |
| Exact five-artifact/full-team materialization | `optimizer_artifact_materializer.py` |
| Evaluation cache | `optimizer_cache.py` |
| Explicit result persistence | `optimizer_save.py` |

### Current selected-account path

| Stage | Module |
| --- | --- |
| Shared rotation response | `optimizer_anytime_response.py` |
| Dense artifact index, Pareto/shadow pools, bitmask joint search | `optimizer_anytime_candidates.py` |
| 8/32/200/1000 multifidelity race | `optimizer_anytime_race.py` |
| Product orchestration | `optimizer_anytime_selected_service.py` |

### Current theoretical path

| Stage | Module |
| --- | --- |
| Inventory-independent shared response | `optimizer_anytime_response.py` |
| Bounded 4p/2p+2p candidate domain | `optimizer_theoretical_anytime_candidates.py` |
| Ordinary GCSIM 8/32 race | `optimizer_theoretical_anytime_race.py` |
| One optimizer pass plus 200/1000 validation | `optimizer_theoretical_anytime_validation.py` |
| Typed 4p/2p+2p orchestration | `optimizer_theoretical_anytime_service.py` |
| Engine-derived 2p signatures/pair domain | `optimizer_two_piece_signatures.py` |

### UI boundary

`optimizer_ui_adapter.py` freezes the selected team, rotation, CPU budget,
database snapshot, set pools, and constraints, then dispatches the current
services. `optimizer_worker.py` owns cancellation and progress delivery.
`ui/gcsim_browser/optimizer_panel.py` is the dedicated panel.

The optimizer package does not modify AppShell or general Artifact Browser
state.

### Supporting/reference modules

`optimizer_main_response.py`, `optimizer_lazy_candidates.py`,
`optimizer_joint_proposals.py`, `optimizer_feedback_loop.py`, and the farming
advisors remain as focused helpers, diagnostics, or research surfaces. They are
not alternate product orchestrators. The obsolete
`optimizer_selected_pool_service.py`,
`optimizer_theoretical_four_piece_service.py`, and
`optimizer_theoretical_two_plus_two_service.py` orchestrators were deleted.

## 4. Frozen request and identity

All operations use schema-v4 typed product contracts in
`optimizer_product_contracts.py`.

Current work-plan identities are:

- selected account: `anytime_approx_v1`, version 1;
- all-database account: `all_database_sets_anytime_approx_v1`, version 2;
- theoretical 4p: `theoretical_4p_anytime_approx`, version 1;
- theoretical 2p+2p: `theoretical_2p2p_anytime_approx`, version 1.

The old `optimized_theoretical_4p` and `optimized_theoretical_2p2p` IDs are
compatibility/reference identities only.

A request binds:

- operation and account scope, if applicable;
- four ordered wearer identities;
- prepared-config SHA-256;
- trusted engine binding and catalog fingerprint;
- versioned work plan and all material budgets;
- selected set pools and account `2p+2p` policy, if applicable;
- artifact database snapshot hash for account operations only;
- minimum-stat legality constraints for account operations;
- explicit four-star overrides, if any.

Theoretical requests never invent a fake account database hash or account
`RunInput`.

## 5. Prepared config boundary

The source config supplies the already selected team and rotation. The
optimizer does not search rotations.

For each candidate:

1. keep team, weapons, talents, constellations, options, targets, rotation, and
   unrelated config text frozen;
2. replace only optimizer-owned artifact/set/add-stat rows;
3. render the candidate into a valid GCSIM config;
4. retain the exact candidate/config/evidence identity so the same combination
   is not unknowingly re-evaluated.

The source artifact lines are not the account artifact source. They may seed
default selected-set controls and provide the static simulation shell only.

## 6. Rotation-response model

The current services run one shared, compact response scan for the frozen
rotation instead of repeating broad response discovery for every package.

The default response contract:

- uses ordinary GCSIM at 8 iterations;
- currently builds 125 full-team probes;
- measures non-ER stat/layout perturbations for all four wearers;
- emits several conservative profiles rather than one scalar “artifact
  score”;
- preserves crit-rate, crit-damage, EM, HP, DEF, ATK, and elemental/main-stat
  branches needed for threshold or reaction-sensitive characters;
- treats missing/failed probes as uncertainty, not proof that the axis is
  useless.

ER is deliberately excluded from automatic response scoring and theoretical
substat optimization. It is a legality floor, not a damage weight.

Unexpected response wiring/code errors fail the product request. They are not
silently converted into a successful conservative result. Ordinary failed or
timed-out probe rows remain typed evidence and can coexist with completed
probes.

## 7. Selected-account candidate algorithm

The current `anytime_approx_v1` path is:

1. Freeze the current database and typed selected package targets.
2. Filter invalid rows fail-closed:
   - unsupported slot/rarity;
   - missing or invalid main stat;
   - unmapped set;
   - explicit four-star policy violations.
3. Build one dense in-memory catalog with slot/set/stat indexes and integer
   artifact bit masks.
4. Deduplicate content-identical rows per target using
   `content_fingerprint`, while retaining bounded physical alternatives.
5. Score each artifact under multiple rotation-conditioned profiles.
6. Keep Pareto/frontier and shadow representatives per slot/profile:
   - crit-rate-heavy and crit-damage-heavy alternatives remain distinct;
   - reaction/EM and non-crit useful branches are not removed merely for low
     crit value;
   - obvious dominated garbage is removed before five-piece enumeration.
7. Build bounded complete wearer candidates with legal main stats and package
   shape.
8. Combine the four wearer pools with bit masks so no artifact ID can be used
   twice.
9. Preserve package/layout/profile/conflict diversity in at most 64 joint
   proposals.
10. Run the exact compiled configs through the multifidelity race.

The default candidate caps include:

- 24 Pareto rows per frontier group;
- 48 retained rows per slot pool;
- 64 complete builds per target;
- 240 complete builds per wearer;
- 64 joint proposals.

These are frozen work-plan limits, not claims about the unsearched domain.

### Content fingerprint limitation

`content_fingerprint` describes artifact content relevant to optimization:
slot, set, rarity, level, main stat, and normalized substats. Equal-content
physical artifacts may be collapsed during ranking while a bounded replacement
witness is retained.

This is an accepted deduplication limitation. It is not an import-generation
model and not a blocker. Physical IDs still matter for no-reuse and saving.

## 8. Theoretical candidate algorithm

The theoretical path is inventory-independent:

1. derive all trusted optimizer-ready five-star 4p packages, or all canonical
   distinct 2p signature pairs;
2. combine each package with bounded legal sands/goblet/circlet layouts;
3. attach required diverse response profiles for each wearer;
4. retain up to 96 alternatives per wearer;
5. construct at most 64 diverse full-team proposals;
6. run ordinary GCSIM screening before expensive substat optimization.

The cheap deterministic candidate order is only a proposal heuristic. It is
never displayed as DPS and never treated as a winner.

The current engine-derived pair domain canonicalizes `A+B` and `B+A`, binds
concrete set identities, and may group equal 2p effects only when the trusted
engine-derived signature proves equivalence.

## 9. Multifidelity evaluation

### 9.1 Selected-account race

The current fixed phases are:

1. `screen_8`: at most 64 candidates, 8 iterations;
2. `refine_32`: at most 16 candidates, 32 iterations;
3. `validate_200`: at most 6 candidates, 200 iterations;
4. `rerace_1000`: only statistically overlapping leaders, at most 3
   candidates, 1000 iterations.

Confidence intervals, a small relative margin, and diversity retention decide
survival. Only results with at least 200 iterations may enter the terminal
top-N or save flow.

### 9.2 Theoretical race and validation

The theoretical path separates ordinary screening from expensive optimization:

1. at most 64 proposals at 8 ordinary iterations;
2. at most 16 survivors at 32 ordinary iterations;
3. at most 6 physically distinct finalists;
4. run GCSIM `substatOptim` exactly once for each finalist, with ER optimization
   and fine-tuning disabled;
5. validate each optimized config at exactly 200 iterations;
6. select at most 3 statistically overlapping leaders;
7. rerun those exact already-optimized configs at 1000 ordinary iterations;
8. never invoke `substatOptim` a second time during rerace.

A local 32-iteration race deadline may still yield partial physical finalists.
If the global service budget remains, those finalists continue to the
saveable 200-iteration stage. Cancellation remains immediately terminal.

## 10. Minimum-stat constraints and ER

Account requests support generic per-wearer lower bounds:

> normalized final artifact contribution for stat X must be at least Y

The legality check happens after selecting all five artifacts and before
GCSIM, so invalid combinations consume no simulation time.

ER uses the same generic constraint:

- the UI may calculate an artifact ER floor from “final ER at least X” minus
  the non-artifact baseline;
- builds below the floor are rejected;
- builds above the floor are compared without rewarding surplus ER through the
  response model.

The infinite/boosted-energy simulation option is independent of this optimizer
constraint.

Theoretical stat floors are not currently accepted. If required later, they
need a separate typed equal-investment contract; they must not be smuggled in
through account constraints.

## 11. Set identity and rendering

Database `set_uid` is mapped to the trusted GCSIM set key through the frozen
engine catalog. Current data usually matches after canonical case folding, but
that observation is not the contract.

Unknown, ambiguous, unsupported, or unmodeled mappings fail closed or remove
only the affected package. A single malformed artifact row does not block the
entire account run when it can be safely excluded.

Theoretical 4p renders one exact `count=4` modeled set row per wearer.
Theoretical 2p+2p renders two exact distinct `count=2` rows per wearer.

## 12. CPU, cancellation, deadlines, and progress

The public plan objects default to one worker for deterministic, safe direct
use. The UI adapter builds a CPU-aware plan:

- cheap candidates run in parallel with one GCSIM worker each;
- the number of concurrent cheap candidates is capped by the selected CPU
  budget;
- theoretical finalist `substatOptim` runs sequentially, using the selected CPU
  budget inside that one optimizer process;
- 1000-iteration ordinary reraces may again run in parallel within the same
  total budget.

The total concurrent GCSIM worker count must never exceed the frozen CPU
budget.

Cancellation propagates to the currently active response simulator, race
simulator/scheduler, finalist optimizer, or rerace scheduler. Completion
callbacks are observer-only and cannot change correctness.

Progress is typed and monotonic within each stage:

- preflight;
- account database/layout indexing;
- response scan;
- candidate generation;
- account joint no-reuse search;
- screening;
- refinement;
- final validation;
- rerace;
- completed.

Each simulation completion updates completed/planned work, stage-local cache
hits, and the current leader when a leader exists. The UI must label
8/32-iteration leaders as provisional. A saveable leader appears only at
200+ iterations.

## 13. Partial work and terminal semantics

The full-team batch adapter preserves every already-completed typed result when
a batch reaches cancellation or deadline. It does not replace successful rows
with blanket timeout rows.

Terminal statuses are fail-closed:

- `BEST_FOUND`: at least one saveable candidate exists;
- `NO_SUCCESS`: the frozen domain produced no saveable success;
- `NOT_READY`: preflight/domain prerequisites were not met;
- `CANCELLED`: explicit cancellation;
- `DEADLINE`: the global budget ended before saveable evidence;
- `FAILED`: contract, wiring, materialization, or unexpected execution failure.

A failure must not be reported as `BEST_FOUND` through an implicit fallback.

## 14. Cache and provenance

Cache identity includes every factor that can change simulation meaning:

- prepared config and optimized config;
- operation and work-plan identity;
- engine binding/catalog fingerprint;
- exact package/layout/profile state;
- exact account artifact IDs/content where applicable;
- simulation iterations/workers/options/environment;
- theoretical pair-domain identity;
- minimum-stat/account-scope input where applicable.

Account provenance includes the frozen artifact database snapshot. Theoretical
provenance does not.

Progress cache counters are cumulative within a stage and include cached
non-leaders. Terminal counters are derived from complete typed evidence.

## 15. Result and persistence boundary

Account results contain absolute DPS estimates and exact four-wearer artifact
assignments. Theoretical results additionally contain percent-to-best inside
the same operation.

The terminal top-N contains only saveable 200/1000-iteration evidence.
Provisional 8/32-iteration rows may be shown during progress but never saved.

Nothing is persisted automatically.

The explicit save service may:

- save a found wearer build as a normal character artifact preset;
- suggest `best_found_<other team members>` as the default name;
- reuse a preset already explicitly saved instead of duplicating it;
- save the four linked wearer presets as one GCSIM team optimizer result.

If the user does not save, the result may disappear when the optimizer view is
replaced. Applying all four presets atomically and a dedicated GCSIM presets
tab remain later UI work.

### Generated-file lifecycle

Optimizer execution files are local diagnostics, not product persistence:

- a successful default-owned ordinary screening run extracts the typed DPS
  summary and then removes its `data/gcsim/farming-runs/run-*` directory;
- a failed or cancelled screening run may retain its directory for diagnosis;
- a two-stage `substatOptim` run retains its input, optimized config, result,
  and byte snapshots, but removes the reproducible private
  `gcsim-verified.exe` copy after both processes stop;
- `python -m run_workspace.gcsim.cleanup` (dry-run by default, `--apply` to
  delete) covers `runs`, `farming-runs`, and `optimizer-runs` separately. Each
  generated-run root defaults to at most 50 newest directories and 256 MiB;
- `data/cache/gcsim_optimizer` is reusable content-addressed simulation
  evidence, not a temporary run directory. Do not delete it during normal
  per-run cleanup.

This lifecycle was added after a 2026-07-28 audit found 16,940 accumulated
ordinary screening directories (about 6.30 GiB) and 20 two-stage directories
(about 909 MiB, almost entirely duplicated executables). The existing data was
reduced to 50 screening directories / 33.31 MiB and five two-stage diagnostic
directories / 1.64 MiB. The local PyCharm module also excludes `data/gcsim`
from indexing; `.idea` is ignored and that IDE setting is not a portable
repository contract.

## 16. Verified evidence

Focused unit/integration coverage exists for:

- typed requests/plans/results and facade exports;
- dense indexing, fingerprint deduplication, Pareto/shadow retention, and
  bitmask no-reuse;
- ER hard-floor behavior and rejection of ER response authority;
- exact 8/32/200/1000 fidelity boundaries;
- one-pass theoretical `substatOptim`;
- ordinary exact-config 1000 rerace;
- cancellation during response/race/validation;
- per-completion progress and cumulative cache counts;
- partial deadline result preservation;
- theoretical 4p and 2p+2p inventory independence;
- explicit save boundaries.

Real-engine theoretical 4p smoke on 2026-07-28:

- response: 125/125 completed;
- proposals: 64 at 8 iterations;
- refinement: 16 at 32 iterations;
- physical finalists: 6;
- smoke validation cap: 2 finalists at 200 iterations;
- terminal status: `BEST_FOUND`;
- elapsed: 106.36 seconds;
- best smoke DPS: 6894.0846.

This smoke proves real config rendering, GCSIM execution, optimizer output
parsing, and terminal assembly. It is not a broad quality/release proof.

Real selected-set account smoke on the local 520-artifact database on
2026-07-28:

- team/config: Chasca, Ororon, Furina, Bennett on the prepared rotation;
- selected sets: Obsidian Codex, Scroll of the Hero of Cinder City, Golden
  Troupe, and Noblesse Oblige respectively;
- cold response/generation/search: 125 probes, then 64@8, adaptive 8@32,
  6@200, and 2@1000;
- first six saveable exact builds available after 117.64 seconds;
- terminal status: `BEST_FOUND` after 177.27 service seconds (180.97 seconds
  for the whole diagnostic);
- best DPS: 13199.8883 at 1000 iterations, versus 13153.6 for the source
  standard config on the same rotation (`+0.3519%`);
- the winning physical identity contains exactly 20 distinct artifact IDs;
- cold cache result: 0 hits and 205 misses.

Real-engine theoretical 2p+2p smoke on 2026-07-28:

- the trusted five-star domain contained 39 modeled 2p sets, 741 concrete
  pairs, and 526 engine-proved representative groups;
- response: 125/125 completed with no failures;
- race: 64@8, 16@32, and 6 physical finalists;
- smoke validation cap: 2 finalists at 200 iterations;
- terminal status: `BEST_FOUND` in 124.00 seconds;
- no account database or inventory identity entered the operation.

Cold/warm cache benchmarks on the same frozen request:

- theoretical 4p: a missing default cache store was found when caching was
  enabled without an injected store. Before the fix, repeat runs still missed
  2/207 expensive finalists and took about 26-27 seconds with unstable winners.
  The validation session now creates its default store; after one population
  pass, repeat runs hit 207/207 entries in 6.234 and 6.063 seconds and returned
  the identical winner;
- theoretical 2p+2p: 104.625 seconds with 0/207 hits, then 11.594 seconds
  with 207/207 hits (about 9.0x faster), with identical cached winner/DPS;
- selected account: 236.859 seconds with 0/214 hits, then 20.000 seconds
  with 214/214 hits (about 11.8x faster), with the same 20-ID winner and
  14360.0657 DPS at 1000 iterations;
- selected warm time still includes dense-pool generation and joint no-reuse
  search; only exact simulation/optimizer evidence is cached.

No-cache process-tree memory samples on Windows used the same prepared team,
an 8-CPU budget, and a 20 ms sampling interval. The sampler summed every live
descendant's current working set/private bytes, so these are observed aggregate
peaks rather than the invalid coordinator-only number recorded by the old path:

- selected account: `BEST_FOUND` in 131.266 seconds, 335,290,368-byte
  aggregate working-set peak, 554,262,528-byte aggregate private-byte peak,
  and at most 9 live processes;
- theoretical 2p+2p with the two-finalist smoke validation cap: `BEST_FOUND`
  in 93.125 seconds, 351,248,384-byte aggregate working-set peak,
  564,678,656-byte aggregate private-byte peak, and at most 9 live processes.

Real-engine all-database v2 benchmark on 2026-07-28 used the same prepared team,
the local 520-artifact database, 8 CPUs, 4p packages, and an isolated temporary
cache:

- 31 modeled database sets produced 124 wearer/package decisions;
- cold: `BEST_FOUND` in 233.531 service / 233.578 wall seconds, with 0/208
  cache hits;
- warm: `BEST_FOUND` in 89.406 service / 89.453 wall seconds, with 208/208
  cache hits;
- both runs returned the identical 7795.1378-DPS winner at 1000 iterations
  with exactly 20 distinct artifact IDs;
- the warm cost shows that dense-pool construction and joint no-reuse search,
  not simulation alone, still need work before this optional mode is promoted.

The current anytime kernels now have direct reduced quality gates:

- selected account matches the exhaustive physical top-1 on the reduced
  contested-artifact oracle and preserves 20 distinct IDs;
- theoretical exhaustive Cartesian fixtures preserve the coordinated winner
  for low/high crit, triple-EM, EM+crit, HP/heal, and DEF safeguards;
- existing threshold, unusual-main, content-deduplication, and physical-shadow
  tests cover stat floors and contested replacement paths.
- deterministic randomized exhaustive corpora cover 100 account cases and 100
  theoretical cases. Both production kernels pass the provisional aggregate
  requirements: at least 95% exact top-1, at most 0.5% mean best-DPS regret,
  and at most 2% maximum best-DPS regret.

The full GCSIM backend discovery suite passed 621/621 tests in 233.513 seconds.
The optimizer-panel UI suite passed 5/5 tests in 0.205 seconds. The lower test
count reflects deliberate deletion of tests for removed broad orchestrators,
while the new release-policy and randomized-corpus tests are included.

## 17. Release gate and next work

The user accepted a provisional versioned release policy on 2026-07-28:

- selected cold first saveable result: at most 150 seconds;
- selected cold terminal result: at most 300 seconds;
- selected warm terminal result: at most 30 seconds;
- theoretical 4p and 2p+2p cold terminal result: at most 180 seconds each;
- theoretical 4p and 2p+2p warm terminal result: at most 20 seconds each;
- mandatory adversarial/exhaustive fixtures: strict exact top-1;
- randomized exhaustive corpora: at least 95% exact top-1, at most 0.5% mean
  best-DPS regret, and at most 2% maximum best-DPS regret.

`optimizer_release_gate.py` stores these values in a typed provisional policy
and fails closed on missing/duplicate/over-limit runtime evidence. The recorded
mandatory runtime matrix passes: 117.64, 236.859, 20.000, 106.36, 6.234,
124.00, and 11.594 seconds for the seven policy cells respectively. Mandatory
quality fixtures and both 100-case randomized corpora pass their accepted
thresholds. Superseded broad orchestrators have therefore been removed.

The thresholds are intentionally provisional. Recalibrate them only after the
user can compare optimizer usability and result quality with hand-built teams
in the UI. Do not silently change the typed policy from anecdotal timing.

The bounded all-database v2 real-engine benchmark is recorded, but its 89.453
second warm wall time keeps that optional mode experimental. Remaining product
work is UI-driven usability/quality comparison and deliberate recalibration of
the provisional policy; all-database pool/joint-search optimization may be
revisited independently and does not block mandatory selected/theoretical
paths.

Do not add user-facing speed modes until measured tradeoffs justify separate
algorithms.

## 18. Confirmed later ideas

Keep these in product planning; they are not part of the current backend
package:

- automatic discovery of public GCSIM rotations matching the selected team;
- a GCSIM presets tab that links four saved character presets;
- one explicit action to save/apply the four-preset team result atomically;
- optional UI indication that a result has many near-equivalent physical
  replacements.

No Artiscan import/generation work belongs to this optimizer pipeline.
