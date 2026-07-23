# GCSIM Engine Integration Plan

Planning date: 2026-06-04

Status reviewed: 2026-07-23

Scope: implementation-direction handoff for GTT-modified GCSIM engine integration. This is not a final Codex implementation task and not a rigid architecture freeze. It records the current product/engineering vector, open questions, and contracts that future Codex tasks must respect unless a later handoff explicitly supersedes them.

Related references:

- `docs/handoff/GCSIM.md` - original GCSIM research notes and upstream source pointers.
- `docs/handoff/GCSIM_OPTIMIZER_TECHNICAL_HANDOFF.md` - optimizer-specific
  current architecture, invariants, performance controls, and extension seams.
- `docs/handoff/GCSIM_ACCOUNT_ARTIFACT_OPTIMIZER_PIPELINE.md` - ordered,
  independently specifiable milestones to the theoretical set actions and
  real-account artifact optimizer.
- `docs/handoff/STAT_NORMALIZATION.md` - project stat normalization and GCSIM stat-key mapping notes.
- `docs/handoff/RUN_WORKSPACE_SNAPSHOT_CONTRACT.md` - Run Workspace boundary, factual DPS vs sim DPS split, and snapshot/session state rules.
- `docs/handoff/ABYSS_ENEMY_DATA.md` - Abyss source-data pipeline and enemy rows.

## Current Authoritative Status

The functional backend for the current selected-team Abyss Browser path is
implemented. Do not start another broad "finish the GCSIM backend" task without
a concrete failing scenario. The working path already covers:

- transactional engine acquisition/update, ordered GTT patches, build/runtime
  validation, active/rollback metadata, and bounded generated-engine cleanup;
- a patched `gtt-gcsim.exe` contract with `-gtt-info`, structured
  `gtt-wave-scenario-v1` payloads, sequential `group_clear` waves, artifact
  preflight, execution, and result parsing;
- selected runtime TeamBuilder state -> stable account/equipment ids -> full
  generated GCSIM config, with controlled readiness failures and no localized
  display-name identity guesses;
- current cached Abyss chamber/side data -> enemy type resolution -> explicit
  wave/HP payload, selected-chamber and sequential C1-C3 Browser runs;
- runtime Sim DPS results in typed `RunSessionState`, compact right-panel rows,
  stale-input clearing, and immutable Abyss History Snapshot serialization when
  the user saves the run;
- a diagnostic DPS Dummy execution path, boosted-energy settings, retention,
  and backend/dev coverage reports.

The remaining GCSIM work is primarily product UI, orchestration, and release
engineering, not missing config/run backend fundamentals:

- finish the Browser presentation, readable/no-code rotation UX, result detail
  navigation, readiness wording, and settings polish;
- replace the stale `History persistence: disabled` runtime wording. Abyss
  Browser results are not auto-saved per simulation, but current session results
  are included when the user invokes normal Run Save;
- add progress/cancellation and, only after measurement, optional bounded
  parallel batch scheduling; the safe current C1-C3 worker is sequential;
- attach DPS Dummy simulation results to typed DPS Dummy session/snapshot state;
- produce and release-validate the known-good bundled executable and build the
  dependency-aware advanced update UI;
- keep Traveler and entities genuinely absent from the active upstream GCSIM
  registry as controlled unavailable cases rather than app mapping bugs.

The tiny committed `gcsim_key_mapping_seed_v1.json` remains a dev/audit fixture,
not the production Browser mapping owner. Normal Browser runs use account SQLite
character/weapon keys resolved during import, active-registry artifact-set
resolution, and the enemy registry/Snap fallback pipeline. Coverage reports
should find real exceptions and upstream gaps; they are not a requirement to
hand-curate every automatically resolvable entity into one global mapping file.

Status-review verification on 2026-07-17:

- all 233 `tests/run_workspace/gcsim/` tests passed;
- all 18 `tests/ui/gcsim_browser/` worker/report tests passed;
- the focused History builder test confirmed typed GCSIM runtime results become
  immutable `sim_dps` summaries separate from factual DPS;
- the local entity coverage report inspected 414 catalog entities: characters
  102 ready / 15 missing / 7 deferred Traveler, weapons 225 ready / 6 missing,
  artifact sets 58 ready / 1 missing, with no ambiguous rows. Missing rows are
  current active-registry/upstream gaps unless a concrete identity bug proves
  otherwise.

Concurrent work boundary: PvP UI work is active in parallel. Do not refactor
`ui/app_shell.py` or introduce scoped PvP GCSIM as part of the normal GCSIM UI
pass. Until the later AppShell refactor, keep GCSIM work inside the existing
hooks and prefer `ui/gcsim_browser/`, `ui/right_panel/live_run/gcsim/`, and
`run_workspace/gcsim/`. PvP-scoped simulation remains owned by the PvP handoff.

## Set Targets and Selected-Set Artifact Optimization Direction

Detailed optimizer mechanics now live in
`GCSIM_OPTIMIZER_TECHNICAL_HANDOFF.md`; the implementation sequence and final
multi-action UI contract live in
`GCSIM_ACCOUNT_ARTIFACT_OPTIMIZER_PIPELINE.md`. Keep this section as the concise
engine-integration boundary rather than growing a second optimizer roadmap.

Pipeline Milestone 0 is complete in
`run_workspace/gcsim/optimizer_product_contracts.py`: the three operation
identities, target packages, account depths, cache/provenance namespaces,
terminal/progress/top-N semantics, and current theoretical `4p` adapter are
schema-v1 contracts. No later optimizer algorithm, concrete depth registry, or
UI was added in that milestone; Milestone 1 inventory readiness is next.

Accepted product split on 2026-07-19:

1. The inventory-independent equal-investment/farming advisor has two separate
   commands: `Find best 4p` and `Find best 2p+2p`. Each returns its own top-N
   full-team set combinations with re-optimized abstract stats and tells the
   user what may be worth farming. A `2p+2p` package always contains two
   different set keys.
2. `Find artifacts for target sets` searches real account artifacts only for
   four explicit target set packages and exposes separate `Quick`, `Balanced`,
   and `Deep` depth controls. The targets may come from one farming result or be
   edited manually. It returns twenty canonical stored artifact ids, five per
   character, with no cross-character reuse.

The two operations may be used sequentially, but the second one is deliberately
not an automatic all-set account search. A user who knows an off-meta set is
exceptionally strong on the account can select it directly. The product does
not spend its default search budget proving or disproving every unexpected set.

Implementation status on 2026-07-23: the theoretical `4p only` path executes end
to end through a real optimized-finalist race, but it is still a heuristic under
validation and the real-account operation is not implemented. Do not confuse its
screened-domain `BEST_FOUND` with a global optimum or release-ready ranking.
Existing components reused are:

- selected runtime team/rotation/readiness and full-config generation through
  `selected_team_config.py`, `config_blocks.py`, and `config_assembly.py`;
- active-engine resolution, ordinary artifact execution, JSON result parsing,
  engine update/rollback, patch capability preflight, and isolated run dirs;
- stat normalization, artifact SQLite inventory/current-equipment snapshots,
  artifact build summaries, and existing build-preset persistence services;
- current GCSIM Browser worker/context plus typed RunSession/right-panel/History
  boundaries. The optimizer UI must not create a second team or rotation owner.

Implemented in `run_workspace/gcsim/`:

- `optimizer_config.py`, `optimizer_set_config.py`, and
  `optimizer_candidate.py`: exact theoretical main rows, legal layouts, complete
  4p overrides, and all five mixed 4-star-set/5-star-offpiece shapes;
- `artifact_set_catalog.py`: comment/test-excluding source audit, complete 2p+4p
  domain, rarity and required-param discovery. Pinned results are 47 complete
  modeled packages and 46 Phase-1 optimizer-ready packages: Defender's Will has
  no 4p, Lavawalker/Thundersoother have no modeled 2p, and Husk is held out until
  an explicit `stacks` parameter policy exists;
- `optimizer_engine_context.py` and `optimizer_backend.py`: one strict
  manifest/tree/executable/catalog identity, pinned v2.42.2 renderer contract,
  artifact hash assertion, Auto `logical_cpus - 1`, explicit config `workers`,
  and matching `GOMAXPROCS`;
- `optimizer_runner.py`: isolated cancellable two-stage `Popen` execution,
  a private verified executable snapshot per run, frozen sanitized environment,
  shared optimize+simulate deadline, timeout/stage diagnostics, below-normal
  Windows priority, and fail-closed final-result semantics;
- `artifact_runner.py` uncertainty fields, atomic content-addressed cache
  primitives, and `farming_search.py` equal-roll profile, complete coverage
  identity (layout + 4-star offpiece), and recall-first survivor selection;
- `farming_evaluator.py`, `farming_pipeline.py`: proof-carrying ordinary-sim
  materialization, immutable executable/environment/config identities, bounded
  CPU scheduling, cancellation, deadlines, uncertainty and persistent cache;
- `farming_response.py`, `farming_response_scan.py`: complete generic response
  probes on one frozen physical baseline and bounded auditable profile selection;
- `farming_team_search.py`, `farming_controller.py`, `farming_advisor.py`:
  complete supported 4p screening, recall-first survivor pools, full-team
  coordinate/beam/exact-pair composition, and a top-level response-to-set/team
  heuristic session with typed budgeted `best_found` output;
- `farming_layout_scan.py`: experimental two-phase generic main-stat discovery;
  22 one-slot coordinate layouts per wearer reduce the legal 420-layout domain
  before a bounded Cartesian finalist pass. `farming_auto_advisor.py` connects
  layout -> response -> set/team screening under one wall-clock deadline. These
  stages are contract-tested but remain baseline-set-sensitive heuristics;
- `farming_finalist_optimizer.py`: canonical bounded full-team finalists through
  real upstream `substatOptim` plus ordinary static-target validation at frozen
  workers and fixed iterations, with cancellation/deadlines, exact runner-owned
  input/optimized/result byte snapshots and hashes, strict optimizer-owned config
  diffs, pinned roll-budget/rarity validation, deterministic request/state/cache
  rebinding, set/layout/allocation evidence and canonical optimized top-N;
- `farming_optimized_advisor.py`: one cancellable outer deadline over automatic
  layout/response/set-team screening and the optimized-finalist race.

Still missing are set-aware response/main-layout refinement, cheap roll
redistribution around set bonuses/caps, adaptive higher-iteration reracing of
close leaders, persistent cache/progress for finalist runs, user-facing percent/
delta/uncertainty/tie semantics, oracle/adversarial validation, real inventory/
no-reuse search, set-parameter variants, 2p+2p, preset adapters and optimizer UI.
These are application work, not evidence that another Go patch is required. The
current active v2.42.2 engine passes the strict manifest/tree/executable/catalog
trust check; future drift must remain fail closed.

Verified upstream behavior on 2026-07-17:

- the source comment in `pkg/optimization/substats.go` says the user first sets
  the team, weapons, artifact sets/main stats, and rotation;
- `-substatOptim` / `-substatOptimFull` then search ER and other fixed/liquid
  substat counts for the characters and rewrite optimized `add stats` lines;
  the Full variant additionally overwrites its input config and runs it;
- it has no artifact-inventory input, artifact ids, equip ownership, set/main
  template search, or global real-item assignment output;
- GCSIM itself does apply modeled set effects from `add set` lines. GTT already
  emits those lines from selected real set counts in `config_blocks.py` and
  `selected_team_config.py`.

Therefore the first implementation does not need a new Go patch. Add an
application-side orchestration/search layer under `run_workspace/gcsim/`:

Items 1-3 are implemented. Item 4 now executes through automatic cheap screening,
a bounded canonical finalist prefix, real upstream optimization, and one fixed-
iteration final rerank. It remains heuristic until set-aware refinement, adaptive
close-leader reracing and the oracle gate exist. Items 5-8 remain the real-account/
product plan.

1. Copy/freeze the prepared config and account inventory snapshot. Prefer the
   two-stage `-substatOptim -out optimized.txt` contract followed by an ordinary
   simulation of `optimized.txt`; it cleanly separates profile generation from
   final evaluation. If `-substatOptimFull` is retained for a smoke, point it
   only at a disposable copy because it overwrites its config input.
2. Add a dedicated optimizer invocation wrapper, or safely extend the current
   artifact runner's hardcoded command, to support `-substatOptim`, optional
   Full smokes, `-options`, optimized-config capture, timeout/cancellation, and
   diagnostics.
3. Run substat optimization against the dedicated static single-target benchmark
   only: one target row with exactly one explicit `hp=999999999`, no `type=`
   profile that could overwrite HP, and no GTT wave directive. Do not
   pass `gtt-wave-scenario` through the optimizer's seeded path and do not add
   an engine patch merely to support that combination. Regular Abyss/wave runs
   remain separate, and optimizer results are explicitly target-specific. A
   static-target compatibility smoke is sufficient. For ordinary candidate
   evaluation, the existing `-c ... -out ...` runner contract is already
   sufficient.
4. For farming search, treat a full four-character set/main-stat state as the
   comparison unit. Use a cheap ordinary-sim screening stage with a deliberately
   wide survivor set, then rerun the substat optimizer for retained states so
   rolls are redistributed before final ranking. Screening must be recall-first:
   do not compare raw unchanged stats when a set grants crit/ER/ATK/etc.; apply a
   cheap proxy redistribution around caps/thresholds or automatically retain
   such affected branches. Use coordinate/beam/multi-start exploration plus
   selected two-character moves. A
   `4 x implemented 4p sets` scan is one neighborhood pass, not four independent
   final rankings and not a promise to fully optimize every screened state.
5. For selected-set account search, accept target packages explicitly, use the
   theoretical output as stat guidance, generate bounded real full-build
   candidates under those packages, and solve one joint four-character
   assignment with global artifact-id uniqueness. Never optimize four
   characters greedily in sequence.
6. Render retained joint assignments through the existing selected-team config
   adapters so real main/sub totals become normalized `add stats` and active
   set counts become `add set`. Evaluate the entire team/rotation in GCSIM.
7. Use staged/bounded search and whole-team GCSIM validation. Record evaluated
   budgets and report `best_found`. The real-build result means best found under
   the selected target sets, not best across every set in the account.
8. Add progress, cancellation, persistent cache, stale-input identity, and a
   typed result containing rank/DPS/baseline delta plus five artifact ids and
   snapshot-ready totals for each character. The optimizer never mutates
   equipment or presets.

Off-piece handling is part of candidate optimization, not post-processing. A
4p build has five possible free-slot shapes, and a 2p+2p build must jointly
assign slots to set A, set B, and the free piece. Main-stat availability and a
strong off-set sands/goblet/circlet can make the best free slot different from
the weakest-looking set piece. Generate top-K complete builds under set-count
constraints; never select five set artifacts and then discard one.

The theoretical substat output is not itself a real-artifact answer or a
universal stat-weight table. Use its final allocation plus controlled stat-range
sweeps to discover the response shape for this exact team/config. Approximate
classes may be `flat/set-only`, `threshold`, `damage`, and `mixed`. This lets a
Bennett-like support focus on set/ER/healing constraints and low artifact
opportunity cost while a Furina-like mixed contributor retains several broad
branches. Treat this as budget allocation; one zero local derivative is not a
safe proof because ER, HP, crit/Fav, and other effects have thresholds/caps.

The farming advisor should expose separate `Find best 4p` and `Find best
2p+2p` commands rather than silently multiplying the pair domain into the fast
`4p` action. For equal-investment `2p+2p` search, concrete set names with the
same exact modeled 2p effect may share one simulator signature; retain their
equivalent names for display. This avoids multiplying identical ATK/EM/ER/etc.
2p effects while preserving distinct conditional effects. The accepted search
domain contains only complete `4p` or `2p+2p` packages. It excludes one active
2p bonus plus three unmatched pieces and zero-active-bonus/rainbow packages.

The current backend result contains absolute sim DPS, uncertainty fields and
abstract main/substat allocations. The future product adapter must add percent of
the best validated found candidate, delta and explicit uncertainty/tie status.
Nearly equal candidates must be shown as tied/within noise rather than implying
that `99%` is a stable strict order. `Use as target sets` will copy a row into the
selected-set artifact search without equipping anything.

Performance gate measured on 2026-07-19 on the current 8-core/16-thread machine:
representative four-character static-target optimizer states took about 16-26
seconds each depending on the fixture/options even with aggressive worker use.
Sequentially full-optimizing 100 states is therefore roughly 26-43 minutes and
200 states roughly 52-85 minutes before broader beam rounds. This is a
feasibility range, not a stable performance promise. Before fixing UX budgets,
benchmark a 10-50-state screen/retain run and compare candidate-level
parallelism. The theoretical actions need explicit versioned total-time/
evaluation budgets. The selected-target account operation separately exposes
Quick/Balanced/Deep presets that can always return cached best-so-far; neither
track waits for the complete combinatorial domain.

The concrete fast-search contract is rotation-conditioned multi-fidelity
racing, not a static role/set heuristic. Expensive optimization is pruned only
after broad cheap coverage:

1. Build a universal diverse profile bank from the supported stat schema and
   legal sands/goblet/circlet layouts. Probe every stat direction at more than
   one scale while preserving the equal roll budget; retain HP/ATK/DEF, EM,
   ER-safe, crit, threshold/extreme, and mixed branches without consulting a
   character name or popularity table.
2. Cheap-sim every optimizer-ready complete 4p package on every wearer and
   carried main-layout/4-star-offpiece variant against the frozen real
   team/rotation. Carry a small response-selected and diversity-
   preserving subset of the profile bank per wearer, including every large,
   nonlinear, or uncertain stat direction; do not form the full Cartesian
   `sets x every generic profile` product. Retain the union of top overall, top
   per carried profile, uncertain, and empirically response-diverse branches.
   Thus a set is not rejected because it looks wrong for a known character.
3. Apply a few coarse stat-roll exchanges to promising/uncertain branches before
   comparing them, so a set that grants CR/ER/ATK/etc. can shed stale rolls. This
   is only a cheap local adaptation; the final allocation still belongs to the
   upstream optimizer.
4. Compose four-set states with multi-start coordinate/beam exploration and
   selected exact pair moves. Use simulator results to learn/check one- and
   two-wearer interactions such as duplicate non-stacking buffs. Retain novelty
   as well as raw DPS so one intermediate ranking cannot collapse the beam.
5. Allocate the remaining time budget dynamically to full `substatOptim` runs
   for the best and behaviorally distinct finalists, then rerun close leaders at
   higher iterations. Stop at the hard deadline and return reproducible
   `best_found` state rather than overrunning it.

Current implementation is intentionally narrower than step 5's target policy:
it takes `physical_finalists[:max_finalists]` in canonical screening order, runs
them sequentially at one frozen `validation_iterations` value, and stops at the
shared deadline. Dynamic latency-derived finalist allocation and adaptive
higher-iteration reracing of close leaders are still pending.

This specifically protects counterintuitive scaling without a Furina-like
hardcode. Upstream damage optimization already perturbs HPP/HP/DEFP/DEF/ATKP/
ATK/CR/CD/EM per character and measures the resulting whole-team ExpectedDPS for
the supplied rotation. If EM owns reactions and wins, its response is visible.
The external profile/layout search must still include EM main stats because
upstream optimizes substats only and will never turn an HP/Hydro/Crit input into
EM/EM/EM by itself.

Additional benchmark detail from the original representative four-cycle fixture:
ordinary 10, 25, and 100-iteration CLI evaluations took about 0.17, 0.25, and
0.65 seconds; full optimizer runs took about 14.6-16.7 seconds there. Forty
10-iteration candidates took about 8.5 seconds sequentially versus 5.0-6.2
seconds under bounded candidate parallelism. A fresh 2026-07-22 fixture measured
about 0.79/1.24 seconds for ordinary 10/25-iteration requests and about 2.91
seconds for twenty 10-iteration candidates under an eight-CPU budget. The exact
base physical domain is 312 states at one layout/profile per wearer:
`4 * (38 five-star packages + 8 four-star packages * 5 offpiece slots)`. This
invalidates the old ~200-state and 25-60-second screen assumption. Keep 300
seconds only as a prototype hard cap; benchmark the integrated advisor and derive
the finalist count from measured median latency and remaining time.

The first real-engine automatic-advisor smoke on 2026-07-22 used one Bennett
wearer, the static `hp=999999999` target, no wave scenario, 10 iterations, CPU
budget 8, cache disabled, `max_values_per_slot=2`, and
`max_layouts_per_wearer=2`. It completed in 12.688 s inside a 90 s outer cap:
22 coordinate + 8 Cartesian layout requests (1.985 s), 11 response requests
(0.734 s), then 156 physical set/layout states / 312 profile candidates with all
312 successful and zero issues (9.969 s). The one-wearer composer exhausted its
8-survivor domain in 8 evaluations and returned heuristic `BEST_FOUND` at
2115.05 DPS. This validates the real executable, orchestration and wall-clock
budget on a reduced domain; do not extrapolate it into a four-wearer runtime or
recall guarantee.

A separate real-engine finalist smoke on 2026-07-22 passed one exact Bennett /
Unfinished Reverie / ATK%-Pyro%-ATK% state through the actual new finalist
boundary with four workers and 25 fixed validation iterations. The trusted engine
returned typed `BEST_FOUND` in 1.469 s on the static `hp=999999999` target with no
wave, persisted optimized allocation evidence, 2632.86 DPS mean and 67.76 SE.
This is a tiny runner/provenance proof, not a four-wearer latency or recall claim.

A post-hardening real-engine finalist smoke on 2026-07-23 repeated the same one-
wearer set/main-stat shape with four workers and 10 fixed iterations. It returned
typed `BEST_FOUND`, 32322.13 DPS mean and 4233.22 SE while passing exact byte-
snapshot, roll-budget, pinned-dummy and frozen-provenance validation. This is
compatibility evidence only, not a stable performance or ranking benchmark.

Separate ordinary CLI invocations do not share seeds; the fresh 10-iteration
sample showed roughly 2.9-4.5% relative SE. They are suitable for recall-first
racing and large profile differences, not one-roll finite-difference elimination. Keep candidates
whose confidence band overlaps the cutoff and every meaningful response outlier.
A stronger companion/batch evaluator may import the pinned engine packages,
reuse one parsed config/worker pool and common seed cohorts, and call upstream's
ExpectedDPS collector. That is an orchestration/performance adapter rather than
a combat-formula patch. Until it exists, the ordinary-CLI prototype must use
wide survivor margins. Full-optimizer/final validation provides stronger
evidence, but its fixed-iteration order remains heuristic until close-leader
reracing and the oracle gate exist.

There is no mathematical global-optimum guarantee under five minutes for an
arbitrary black-box `sets^4 x mains x rolls` domain. Reliability is an empirical
release gate: compare Fast against offline Deep/exhaustive oracles on reduced
domains and adversarial fixtures for off-field EM ownership, HP/healing team
conversion, DEF scaling, ER cliffs, Fav/crit, unusual mains, and duplicate team
buffs. Log the exact stage that would remove an oracle winner. Initial targets
are oracle-winner top-five recall of at least 95-99%, best-DPS regret at most 1%,
no miss above 2%, all adversarial cases passing, and p95 runtime inside the chosen
budget. A failed gate expands generic profile/beam/pair coverage; it never adds
`if character == ...` exceptions.

Optimizer-specific correctness checklist and remaining blockers:

- DONE for theoretical candidates: the dedicated renderer writes exactly five
  legal main-stat rows separately, including the exact flower marker expected by
  upstream. The current real-build renderer still combines main and substat
  totals, so a future inventory optimizer must use the dedicated theoretical
  boundary rather than passing that combined account line to `substatOptim`;
- DONE for the cheap 4p path: equal-investment profiles, environment, engine,
  config, candidates, outcomes and budgets are frozen in provenance. Defaults
  follow upstream `total_liquid_substats=20`, `indiv_liquid_cap=10`, and
  `fixed_substats_count=2`, with 5-star main values except where a 4-star-only
  set forces 4-star pieces. The experimental main-layout scan covers every legal
  sands/goblet/circlet axis before bounding finalists; integration and set-aware
  refinement remain;
- DONE for 4p screening: the engine-version-scoped capability catalog
  distinguishes parser shortcuts from sets whose requested 2p/4p behavior is
  actually modeled. For example, the pinned source explicitly marks Defender's
  Will 4p unimplemented;
- DONE: result parsing carries iterations and DPS SD/SE. REMAINING: re-run close
  finalists at a higher budget before assigning a strict order;
- DONE: actual executable/source/catalog identity is hashed and the active engine
  is currently trusted. Any later patch or binary change must be rebuilt/resealed
  instead of bypassing the context;
- DONE for optimized finalists: the runner snapshots exact input, optimized
  config and result bytes, verifies the simulated input/config did not change,
  and the finalist boundary checks the optimizer changed only one canonical
  substat row per wearer. Roll units, fixed/liquid totals, main-stat-aware caps,
  4-star rarity modifiers and deterministic request/state/cache identity fail
  closed. Lexer-compatible structural validation treats semicolons as statement
  boundaries and rejects hidden/multiline optimizer-sensitive rows before the
  line-oriented renderers. The exported ordinary evaluator applies that same
  guard and scheduler batches bind an invariant config-shell hash in addition
  to the caller context. The static target is pinned to `hp=999999999`;
- KNOWN ACCEPTED ISSUE (explicit user decision): cross-source
  `content_fingerprint` deduplication may collapse two genuinely distinct,
  completely identical artifacts into one canonical id. This prevents the same
  artifact observed through account data and Artiscan from becoming two copies;
  the exact-twin case is considered negligibly rare. It is not an optimizer
  blocker or a multiplicity migration task. Keep the current policy unless the
  product decision is explicitly reopened.

Entity readiness remains a controlled product limitation, not an optimizer bug.
The pinned v2.42.2 engine lacks Iansan and the owned `A Day Carved From Rising
Winds` set. The official v2.43.4 shortcut registry checked on 2026-07-19 still
lacks Iansan, although the newer release line adds the missing set. Thus the
example Kinich/Bennett/Iansan/Emilie team cannot be used as the first end-to-end
optimizer fixture; use a supported team while separately tracking upstream or
an explicit character implementation patch.

The future Artifact Optimizer is a dedicated subwindow/overlay inside the GCSIM
workspace with separate `Set combinations / farming` and `Artifacts for target
sets` views. The latter supports quick target-set edits, top real assignments,
sim DPS, artifact cards, `Save preset`, and validated `Save all presets`.
Detailed naming/collision ideas are in TODO section 12. Keep this UI out of the
current PvP/AppShell refactor window.

CPU and cancellation are product requirements, not later polish. GCSIM configs
must explicitly set `workers` because the current parser defaults to 20. Expose
`Auto` plus a logical-CPU budget; the initial Auto default is
`max(1, logical_cpus - 1)` and long GCSIM work should use below-normal process
priority on Windows. Also set `GOMAXPROCS` to the assigned count. Start with one
GCSIM process using that budget; if later running independent candidates in
parallel, enforce that the sum of `workers` across all live processes does not
exceed the budget. Benchmark candidate-level versus in-process parallelism.
DONE for the current runner: long optimizer work uses cancellable `Popen`, a
thread-safe direct session cancel call, below-normal Windows priority, per-stage
timeouts and shared outer deadlines. It stops new work, terminates the disposable
active GCSIM process, never uses `QThread.terminate()`, and rejects partial output.
A freshly computed outer timer is armed immediately before each finalist child
run, so time already consumed by session construction cannot extend the deadline.
A Windows Job Object is optional future hardening if GCSIM later starts child
processes. Persistent finalist-cache wiring plus progress/current-best reporting
remain product work. Synchronous candidate materialization and injected custom
session-factory construction themselves are small test/orchestration seams that
cannot be hard-preempted while arbitrary Python is blocked; add checkpoints or
offloading if either becomes materially expensive.

Keep cache and provenance identities separate. Simulation-cache identity
contains the engine hash/version, exact compiled config, and execution/fidelity
options; it intentionally excludes real artifact ids when they do not change
the compiled config. Assignment/result provenance separately contains optimizer
mode, source request, target packages, account inventory snapshot, complete
twenty-artifact assignment, search preset, and the compiled-config witness hash.

## 1. Product Direction

The application should expose GCSIM-backed calculations inside the GenshinTeamsTracker UI, especially in the Run Workspace/right dock where Factual DPS and prepared Sim DPS result cells live.

The UI-level contract is:

- User selects/equips teams, weapons, artifact builds, and an Abyss chamber/side scenario.
- The app sends a structured scenario to a local GTT-modified GCSIM engine boundary.
- The engine returns sim DPS, simulated clear time/timer data, warnings, and engine/scenario metadata.
- Right-panel Sim DPS cells show compact results; deeper config/result/debug UI can live in a separate workspace/window/overlay.
- If team/build/enemy scenario/target mode/engine version changes after a sim result was produced, keep the result visible but mark it stale instead of silently treating it as current.

Factual DPS remains app-owned HP/time math. GCSIM results are `sim DPS` and must not be mixed into factual DPS calculations.

## 2. Engine Update / Patch Model

The intended update model is official GCSIM source plus GTT patches embedded in the application:

```text
official genshinsim/gcsim source release or commit
+ local GTT patch stack shipped with the app
= local GTT-GCSIM engine folder
```

The app-level `Update GCSIM` action should be transactional:

1. Download/select official GCSIM source for a chosen release/commit/PR source.
2. Create a new local engine folder.
3. Apply the GTT patch stack shipped with the app.
4. Build/prepare the engine runtime.
5. Run compatibility smoke checks.
6. Activate the new engine only if patch/build/smoke all pass.
7. If anything fails, keep the previous active engine and report incompatibility.

Guarantee target:

- If upstream GCSIM areas touched by GTT patches remain compatible, patches should apply and the new local GTT engine should become usable automatically.
- If upstream changes conflict with GTT patches or break smoke checks, the app must not activate the new engine.
- Older working engine folders must remain selectable/rollback-capable through the bounded local engine-store retention policy.

A small retained local engine stack is acceptable, for example active plus one previous known-good engine and one latest failed/debug engine. Generated engine folders should stay bounded by retention; unbounded accumulated full source/engine copies are a size problem, not a desired cache.

### Shipped engine and dependency UX contract

The app should ship with a known-good, prebuilt GTT-GCSIM engine artifact that was produced and validated by the project release process. This bundled engine is the out-of-box calculation engine and must work for normal users without requiring Go, Git, Python, or any build tool on their PC.

The shipped engine must not be deleted by ordinary user-triggered GCSIM updates. It should remain available as the trusted fallback even if the local update stack keeps only a small number of downloaded/generated engines. Rationale: a locally rebuilt engine may appear to work at first but later reveal a subtle issue; the release-shipped engine should remain recoverable as the last project-validated baseline.

The `Update GCSIM` UI must not assume the user's Windows installation has build dependencies. The update flow should explicitly detect dependency readiness and present choices before trying a source rebuild:

- automatic dependency install path, preferably using `winget` when available;
- manual dependency path, with links/instructions for official Go and Git downloads;
- already-installed dependency path, where Go/Git are detected and the update proceeds;
- cancel/keep-current-engine path.

The app may later help install dependencies automatically, but it must not silently install Go/Git. Any dependency installation must be explicit, user-confirmed, and recoverable. `winget` must be treated as optional, not guaranteed. If `winget` is unavailable or dependency installation fails, the built-in shipped engine remains active and calculations remain usable.

The final UX should communicate that GCSIM source updates are an advanced/local rebuild path. Normal calculations should continue through the shipped engine even when local update dependencies are missing.

## 3. Patch Stack Direction

GTT features should be implemented as a minimal patch stack over GCSIM, not as broad rewrites scattered across the engine.

Preferred shape:

- Keep most GTT logic isolated in GTT-specific packages/modules inside the patched source tree, such as scenario, wave scheduler, engine API, and result metadata modules.
- Touch upstream GCSIM core/parser/setup/combat code only at narrow integration points.
- Keep patches small enough that upstream updates adding characters, weapons, artifacts, or ordinary mechanics usually merge cleanly.
- Treat conflict with target/combat/event/setup internals as an expected compatibility failure requiring a newer app/patch-stack version.

Planned/possible patches include:

- GTT engine API/capabilities.
- GTT scenario metadata.
- Sequential Abyss wave scheduler.
- GTT result metadata and scenario hash reporting.
- Future GTT-specific target models or debug hooks.

## 4. Sequential Waves / Abyss Target Modeling

Vanilla GCSIM supports simultaneous multi-target scenarios. GTT needs additional sequential wave behavior for Abyss-like scenarios.

Required conceptual feature:

```text
enemy/group dies -> spawn next enemy/group
next dies -> spawn next enemy/group
all scheduled enemies/groups are exhausted -> simulation ends
```

This must happen inside one simulation iteration/run so that buffs, cooldowns, energy, auras, summons, snapshots, active character, and other combat state are preserved across waves.

Important clarification:

- GCSIM `iterations` should be used as repeated Monte Carlo runs of the whole scenario.
- One iteration should represent one simulated Abyss pass/side/chamber scenario.
- Inside each iteration, GTT wave logic handles the sequence of enemies/groups.
- After one full wave scenario ends, the next GCSIM iteration repeats the same full scenario with a different seed as usual.

Open target model options to research/compare:

- `simultaneous_multitarget`: all targets exist at once; vanilla-like multi-target behavior.
- `single_big_target`: one combined HP target; simple but loses AoE/multi-target behavior.
- `representative_multiplier`: simulate representative target(s) and scale by count/HP; useful approximation for some multi-target rooms.
- `sequential_group_clear`: spawn the next group only after the whole current group is dead.
- `sequential_rolling_replacement`: when one target dies, spawn the next queued target into its slot while other current targets remain alive.
- Hybrid Abyss policy: identical enemy stacks may use rolling replacement, while transition to a different enemy/boss may require clearing the remaining current group first.

The exact model for rooms like `3 + 3 + 3` must be researched against actual Abyss behavior and GCSIM mechanics before being treated as product-correct. The handoff intentionally records this as a design area, not as a locked algorithm.

## 5. Abyss Sim Timer

GCSIM Abyss results should eventually produce a simulated clear time and corresponding simulated Abyss timer/remaining time.

Possible sources:

- If the GTT/GCSIM scenario is kill-mode with finite target HP, prefer the simulation result duration statistics, for example mean duration.
- If using fixed-duration sim DPS mode, derive clear time with the same HP/time relationship used by factual DPS: `sim_clear_time = abyss_side_hp / sim_dps`.

The UI should label this separately from factual timer values and carry engine/scenario metadata.

## 6. Key Mapping

Key mapping is a separate required task before reliable config/scenario generation.

Contracts:

- Do not feed localized display names to GCSIM.
- Map project/account character, weapon, artifact set, and enemy identifiers to GCSIM keys using stable IDs or generated mapping data. For account characters and observed weapon stacks, `name` is localized display text; future config adapters should use stored resolved `gcsim_character_key` / `gcsim_weapon_key` fields only when their status is `ready`, rather than searching localized names.
- Traveler is explicitly deferred for initial GCSIM integration; do not silently guess a Traveler element/variant.
- Missing or ambiguous mappings should make a slot/scenario not ready for GCSIM rather than producing a misleading config.
- A backend/dev entity registry report has been added in `run_workspace/gcsim/entity_key_readiness_report.py`. It parses local prepared GCSIM shortcut sources for accepted character, weapon, and artifact set config keys, prefers explicit seed overrides, then reports exact normalized project-name candidates, and then applies a conservative contiguous-name-span fallback. The span fallback matches whole normalized tokens/spans only, not random substrings: `Yumemizuki Mizuki -> mizuki` and `Rainbow Serpent's Rain Bow -> rainbowserpent` are accepted as audit candidates, while `The Daybreak Chronicles -> ak` is rejected. Exact/span candidates are readiness evidence only and are reported with `auto_exact_candidate_not_curated_mapping` or `contiguous_name_span_candidate_not_curated_mapping`; they must not be silently promoted into committed curated production mappings.
- The default report CLI is `python -m run_workspace.gcsim.entity_key_readiness_report --format text|json`. Without an explicit entity fixture, it reads only existing local HoYoWiki character/weapon stats caches plus `data/static/artifact_set_catalog.json`; character/weapon cache identities are HoYoWiki `entry_page_id` values and are warned as diagnostic identities, not the missing production game-id mapping owner. Names such as Mizuki in this report come from the local HoYoWiki cache/catalog and the local prepared GCSIM registry, not from account SQLite localized names and not from network at report runtime. Full production project-id-to-GCSIM-key coverage is still future work.
- Account SQLite sync now materializes a narrower account-owned result for
  current account characters and observed weapon stacks: `catalog_english_name`,
  resolved `gcsim_character_key` / `gcsim_weapon_key`, status, and method. This
  uses the same local registry matching logic once per sync and stores only
  ready keys as config-ready values. It does not solve artifact-set mapping,
  Traveler variant selection, selected-team/current-build ownership, or global
  production mapping coverage.

## 7. Character Level Helper

GCSIM character config needs current/max level style values such as `80/90` or `90/90`.

Current account/runtime data may not always expose character ascension/max level directly. A pure helper has been added before full config generation:

```text
run_workspace.gcsim.config_level.resolve_gcsim_level_text(level, promote_level) -> current/max level + warnings
```

The helper mirrors the project breakpoint assumption: `80,5 -> 80/80`, `80,6 -> 80/90`, `70,4 -> 70/70`, and `70,5 -> 70/80`. If `promote_level` is missing on breakpoint levels 20/40/50/60/70/80, the character is assumed after ascension and the result carries `promote_level_missing_assumed_after_ascension`. Level 90 is `90/90`, and special/final caps 95 and 100 are accepted as `95/95` and `100/100`. Missing level returns controlled `missing_level`. This helper is still formatting/readiness support only; it does not generate config text.

A backend character config block builder has been added in `run_workspace/gcsim/config_blocks.py`. It accepts already-prepared mapping refs, level/promote data or ready level helper results, constellation, confirmed normal/skill/burst talents, weapon mapping/refinement/level, artifact set counts, and artifact build snapshot stat totals. Ready input renders only the character/equipment block lines (`char`, `add weapon`, `add set`, `add stats`). Missing mappings, unsupported Traveler, unconfirmed talent order, missing levels/refinement, ambiguous set mappings, or no mappable artifact snapshot stats return a controlled not-ready result with no partial config text. `add stats` is restricted to artifact snapshot totals normalized through `hoyolab_export/stat_normalization.py`; character base stats, weapon base stats/passives, final/right-panel totals, and artifact set bonuses must not be injected here. This is still not full GCSIM config generation, account/team adapter wiring, artifact execution, or UI integration.

A backend/dev full-config assembly boundary has been added in `run_workspace/gcsim/config_assembly.py`. It combines ready generated character blocks with a rotation/options shell and refuses to emit partial full config if any block is not ready. The Chasca/Ororon/Furina/Bennett shell fixture lives at `run_workspace/gcsim/smoke_fixtures/rotation_chasca_ororon_furina_bennett.txt` and contains only options, energy, a placeholder target line, active character, and rotation script. That shell is not account truth: it must not contain manual `char`, `add weapon`, `add set`, or `add stats` lines, and the assembler rejects shells that do. The target line remains parser/website-style placeholder text; enemy waves, HP, and target types remain the generated schema-v1 `-gtt-wave-scenario` payload. A narrow prepared-input adapter boundary exists in `run_workspace/gcsim/prepared_config_adapter.py`; it accepts explicit backend/dev dict/JSON input and converts it to `GcsimCharacterConfigInput` without UI access, storage queries, network, or final/right-panel stat totals.

Prepared full-config bridge support has been added to the same adapter module. CLI: `python -m run_workspace.gcsim.prepared_config_adapter --fixture path --rotation-shell path --format text|json`. Default dev fixture `run_workspace/gcsim/smoke_fixtures/prepared_team_chasca_ororon_furina_bennett.json` is marked `synthetic_dev_fixture`: it is not account truth, not UI state, and not production mapping data. It uses registry-checked GCSIM keys for Chasca, Ororon, Furina, Bennett, their synthetic weapons/sets, confirmed talent order, and artifact-snapshot-only synthetic stat totals. The bridge writes a generated full config only when all prepared characters and the shell audit are ready; missing required characters, missing/ambiguous mappings, unsupported Traveler, missing weapons, missing talents, or missing artifact stats produce a not-ready report with no config output.

Account-backed backend/dev prepared config bridge now exists in `run_workspace/gcsim/account_prepared_config.py`. CLI: `python -m run_workspace.gcsim.account_prepared_config --format text|json`; optional cached-Abyss smoke: add `--run-abyss-smoke`. It reads real `data/artifacts.db` account rows for Chasca/Ororon/Furina/Bennett, consumes stored ready `account_characters.gcsim_character_key` and `account_weapon_observed_stacks.gcsim_weapon_key`, and never uses localized `name` fields as GCSIM identity. Current-equipped weapon rows are used when present; otherwise a deterministic ready observed weapon stack of the matching weapon type is selected and reported with `dev_weapon_candidate_not_account_truth`. Current-equipped artifact rows are consumed when available: `account_character_equipped_artifacts` joins `artifacts` and `artifact_substats`, `add stats` is built only from equipped artifact main/sub stat totals, and `add set` is built from equipped set counts. Final account/right-panel stat sheets and manual set bonuses are not injected. Missing or incomplete current artifacts produce a controlled not-ready report instead of a silent synthetic fallback. Artifact set keys are exact registry-checked `set_uid` candidates in this backend/dev bridge and are reported as not curated production mapping. The adapter writes no partial config when any character block is not ready. It does not query UI, persist right-panel state, run network refreshes, rebuild GCSIM, or change the patch stack. It uses account SQLite constellation rows only for the narrow talent-level normalization described below. Local no-network diagnostic on 2026-06-06 generated an account-backed Chasca/Ororon/Furina/Bennett full config from current-equipped artifacts and passed cached `2026-02-16` F12 C1 S1 through the active artifact as a backend compatibility smoke only; do not treat the smoke summary as DPS correctness. This bridge remains useful as a dev CLI/smoke path, not the Browser production team source.

The account-backed CLI also supports a backend end-to-end compatibility smoke: `python -m run_workspace.gcsim.account_prepared_config --run-abyss-smoke --dev-energy-override --format text`. It assembles account-prepared team blocks with the manual Chasca rotation shell, writes a temporary dev-only boosted-energy shell copy in the run dir, generates cached Abyss waves for the configured chamber/side, and runs the existing patched artifact runner with `-gtt-wave-scenario`. The boosted energy line is dev-only and must not be treated as product rotation truth. Future GCSIM browser/editor work needs direct rotation code input/editing, not only committed shell fixtures.

Production Browser config wiring now uses `run_workspace/gcsim/selected_team_config.py`. It consumes the current selected `TeamBuilderTeamState`/AppShell slot state and resolves account-owned data by stable ids such as `character_id` and selected/current weapon fingerprint. It must not infer GCSIM identity from localized names, and unlike the dev CLI bridge it must not choose deterministic fallback weapon candidates. Missing selected/current weapon, character/weapon/artifact-set GCSIM key, current artifact data/stats, talent/level/refinement data, unsupported Traveler, or rotation-shell issues produce structured not-ready reports. `run_workspace/gcsim/readiness_summary.py` turns those reports into grouped UI-independent text for Browser prepare/run failures. Normal Browser output is readiness-first and compact; the first compact UI pass shows a context bar, reserved rotation tabs, a run summary, and hidden-by-default Advanced/Debug raw details instead of a dominant issue/log wall. Browser `Check readiness` exposes the prepare/preflight path, while actual run attempts remain the product path for readiness blockers. `run_workspace/gcsim/settings.py` owns product energy mode: boosted energy is disabled by default and only injects/replaces `energy every interval=480,720 amount=100;` when `gcsim_boosted_energy_enabled` is true. The setting is exposed in the Account page under a compact GCSIM block and clears runtime Sim DPS results when changed. The dev CLI `--dev-energy-override` remains separate in `account_prepared_config.py`.

### First GCSIM Browser MVP UI contract

The first GCSIM UI should be a browser tab/page near the existing character/weapon and artifact browser areas, not an isolated popup and not a small TeamCard-only panel. The right panel remains the compact Run Workspace summary that receives Sim DPS / clear-time results.

Contracts:

- Consume the current runtime team composition from Run Workspace/right panel through `selected_team_config.py`; do not use localized display names or the old dev `team_names` bridge as Browser identity. Runtime results belong to typed Run Session state; widgets only display/command that state.
- Abyss mode has Team 1 / Team 2 tabs. Team 1 maps to first-half Abyss enemies, Team 2 maps to second-half Abyss enemies. DPS Dummy mode has one team tab.
- Show compact team readiness cards with character, weapon, artifact set summary, and ready/issues. Full build editing stays in the existing account/artifact UI.
- Provide GCSIM total-stats tooltip/report per character so users can compare GCSIM-computed totals with the app/right-panel totals.
- Show an Abyss target browser below the team: C1/C2/C3, side by active team, waves, enemy names, levels, HP, and resolved GCSIM target types.
- The existing solo/multi target toggle must control which targets are sent to GCSIM. Current generated wave policy remains `group_clear`; stack/rolling replacement is future work.
- Show temporary run defaults in the browser, for example iterations and boosted-energy status. Boosted energy is settings-controlled from Account -> GCSIM and disabled unless explicitly enabled; later these defaults can move to a fuller GCSIM settings section/control.
- Raw GCSIM rotation-code input is required in the MVP. A visual/button-based rotation builder can be added later, but must not replace direct code input.
- Current implemented Abyss run action is `Run selected chamber`: the active Team 1/Team 2 tab maps to Abyss side 1/2, the selected C1/C2/C3 button maps to `abyss_chamber`, the rotation editor text is used as the shell, and a Qt worker under `ui/gcsim_browser/run_worker.py` runs selected-runtime-team config generation plus generated wave backend path asynchronously. AppShell passes the current cached Abyss source-data identity already used by the Browser/right-panel preview (`period_start`, `floor`); the run worker must not fall back to backend smoke defaults such as `2026-02-16` when current UI source-data exists. Results include config/scenario paths, source identity, scenario waves/targets/total HP, observed duration, DPS summary, average total damage per sim run, warnings, failed action buckets, incomplete characters, grouped readiness summaries, and controlled error category in the GCSIM Browser Results panel. A selected-chamber result is converted into `RightPanelGcsimChamberResult`, stored in typed Run Session state, and replaces only the matching team/chamber/side row; compatible existing rows for other chambers on the same team/side are retained, and unrelated team/side rows are not overwritten. Diagnostic warning `abyss_preview_scenario_source_mismatch` is reserved for preview/run source identity drift.
- Current implemented DPS Dummy action reuses the selected Team 1 state and manual rotation shell, assembles config through the same selected-runtime-team adapter, and runs the active artifact without Abyss source identity or generated wave scenario. The report includes diagnostic energy mode, dummy target HP/resist/source when parseable from the shell/config, and average total damage per sim run wording. It deliberately does not create history, no-code rotation, right-panel persistence, or enemy/source defaults, and damage correctness remains unclaimed.
- Current implemented batch action is `Run 3 chambers`: it maps the active Team 1/Team 2 tab to side 1/2, uses the same current cached Abyss source identity and rotation editor text, then runs C1/C2/C3 sequentially in the same Qt worker. Do not parallelize those three GCSIM processes yet. The browser shows a compact batch report with per-chamber status, observed duration, DPS summary, average total damage per sim run, scenario total HP/waves/targets, warnings, and error category. The same batch result is converted into typed-session `RightPanelGcsimChamberResult` rows; the active team's right-panel Sim DPS cells show compact `clear time / DPS` text, the other team remains `not run`, and results are cleared on obvious input changes such as team/equipment/source/target-mode/rotation/energy-mode changes. Normal Run Save serializes these current Abyss session results into immutable History Snapshot `sim_dps` summaries. There is no separate auto-save after every simulation and no SQLite GCSIM archive. The current tooltip/report text that says `History persistence: disabled` is stale and should be replaced during the UI pass with wording that explains save-with-run-snapshot behavior.
- Future GCSIM run scheduler should treat the current sequential `Run 3 chambers` behavior as the safe MVP, then support bounded parallel chamber runs when the user's machine can handle them. It needs `max_workers`/auto mode, isolated `run_dir`/config/scenario/stdout/stderr per chamber, ordered C1/C2/C3 result aggregation, and cancellation/progress handling.
- Later GCSIM Browser/right-panel work should polish sim result tooltip visuals/details, expose the existing save-with-run-snapshot policy clearly, move temporary defaults into fuller settings when needed, and improve navigation between right-panel Sim DPS cells and Browser result details.
- First UI work should prioritize readiness/report/config/result visibility over visual polish.

Manual smoke checklist for the current backend-MVP:

- Ready selected team -> `Check readiness` produces a ready config/preflight report.
- Not-ready selected team -> run attempt shows readable readiness blockers.
- `Run selected chamber` -> the matching right-panel Sim DPS cell updates.
- `Run 3 chambers` -> all three matching right-panel Sim DPS cells update.
- Hover Sim DPS -> tooltip shows status, config/scenario paths, target identity, no-correctness wording, and correct save-with-run-snapshot behavior.
- Toggle Account/Data -> GCSIM boosted energy -> previous Sim DPS clears and the next run reports the new energy mode.
- DPS Dummy -> runs without Abyss source-data and shows energy/dummy target diagnostics.

## 8. Talent Levels

Current GCSIM v2.42.2 validates config talent levels as parser/base values in the inclusive range `1..10` (`pkg/core/player/character/character.go`). Account/HoYoLAB observed talent rows may include constellation-boosted displayed levels above 10, so displayed levels are not GCSIM-ready.

Pure helper `run_workspace/gcsim/config_talents.py` now prepares parser-safe levels before config output. It consumes the three active `skill_type=1` talents plus active constellation rows, considers only active C3/C5 (`pos in 3,5` and `is_actived=true`), extracts text inside HoYoLAB `<color=...>...</color>` markup, normalizes both colored references and talent names, and subtracts the +3 bonus only when a colored reference matches exactly one active talent. Unresolved active C3/C5 rows warn with `constellation_talent_bonus_not_resolved`; any level that remains above 10 after normalization is capped with `post_normalization_talent_level_capped_to_gcsim_range`. GCSIM output must never receive a talent level above 10, and unresolved/special cases are not silently treated as exact.

The account storage layer now persists minimal constellation source rows in `account_character_constellations` (`character_id`, `pos`, `name`, `effect`, `is_actived`) only so the talent helper can remove C3/C5 display bonuses. This is not a buff engine and not a static constellation-effect catalog. Production selected-team generation already uses deterministic `skill_id` ordering with a controlled warning; richer semantic talent-slot validation remains correctness polish, not a missing production wiring prerequisite.

## 9. Artifact / Weapon / Set Double-Counting Boundary

Artifact `add stats` for GCSIM should contain artifact main/sub stats only, normalized to GCSIM units.

Do not manually inject weapon passive effects, artifact set effects, resonance, or other conditional bonuses into `add stats` when GCSIM is expected to model those through its own character/weapon/set systems.

Project display effects/tooltips are UI/reference data and must not be used as GCSIM stat injection unless a later explicit design says otherwise.

## 10. Resource Budget / Multiple Simulations

The app may need to run up to six simulations for Abyss-related calculations. This can be CPU-heavy.

Before launching a batch, the app should estimate a safe resource budget:

- CPU logical/core count.
- Current CPU load if available.
- Reserved threads for system/UI responsiveness.
- Number of requested concurrent sims.
- Workers per sim.

The app should avoid launching multiple GCSIM jobs each with an aggressive default worker count. If resources are limited, queue simulations or reduce per-sim worker count.

Normal Auto mode must remain interactive through its reserved logical processor,
below-normal process priority, progress, and cancellation. Show an explicit
heavy-load warning only when the user selects an aggressive/max CPU budget that
removes the normal responsiveness reserve.

## 11. Result Handling / JSON Boundary

The implemented result boundary uses GCSIM JSON result files/objects as the
interchange format. `artifact_runner.py` tolerates omitted protobuf-default
fields and converts the output into a compact backend summary. Browser workers
add selection/scenario/readiness/error metadata, and successful Abyss rows are
converted into typed Run Session results. Normal Run Save then maps those rows
to immutable History Snapshot `sim_dps` summaries.

Current parsing/reporting extracts:

- sim DPS statistics;
- duration / clear-time statistics;
- total damage;
- warnings and failed actions;
- scenario identity, target mode, generated paths, and compact readiness/error
  diagnostics;
- rotation hash and enough team/chamber/side identity to invalidate or replace
  the correct runtime result.

Deeper target/character/element breakdowns, complete release engine hashes in
saved snapshots, and a dedicated result-details UI remain optional product
extensions rather than backend-MVP blockers.

The parser must tolerate missing default/zero fields because GCSIM results are protobuf JSON where default values may be omitted.

If a later Go API/shared-library/native result object is designed, it should still preserve a JSON/history-friendly result representation.

## 12. Suggested Implementation Phases

Historical phases 1-10 are complete for the current Abyss Browser MVP: engine
store/update, build artifact, GTT capability marker, config generation, selected
runtime-team adapter, `group_clear` waves, current Abyss scenarios, JSON result
parsing, typed session writeback, right-panel summaries, and save-with-run-
snapshot History attachment all exist.

Current implementation sequence:

1. GCSIM Browser UI pass inside `ui/gcsim_browser/`: replace placeholders,
   improve team/target/readiness/result presentation, and correct stale History
   wording without refactoring AppShell ownership.
2. Rotation product pass: retain raw code, add readable parsing/presets, then
   decide whether a constrained no-code builder is worth maintaining.
3. Run orchestration pass: progress, cancellation, run-artifact/debug retention
   controls, and measured optional bounded parallelism.
4. DPS Dummy state pass: attach successful results to typed DPS Dummy session
   and immutable snapshot data, separate from factual DPS.
5. Release pass: build and validate the bundled known-good executable, package
   it outside user-writable engine retention, and add dependency-aware advanced
   update UI.
6. Correctness/coverage pass: maintain real rotation smokes, audit current
   registry gaps, and add explicit mapping overrides only for proven exceptions.

Independent backend-only optimizer track while PvP/AppShell work continues:

1. DONE: optimizer-specific main-stat/4p renderer, two-stage `-substatOptim`
   wrapper, static-target real smoke, actual executable identity, representative
   benchmarks, cancellation, uncertainty fields, worker budget, cache primitive,
   and strict frozen engine/candidate boundary.
2. DONE: proof-carrying ordinary evaluator/scheduler, persistent cache, generic
   response scan, complete 312-state base 4p physical coverage, recall-first
   survivors, full-team coordinate/beam/exact-pair composition, hard deadline/
   cancellation, and top-level heuristic advisor.
3. DONE/EXPERIMENTAL: contract-tested generic bounded main-layout coordinate/
   Cartesian scan and automatic layout -> response -> set/team wrapper.
4. DONE/EXPERIMENTAL: canonical bounded finalists -> real `substatOptim` ->
   fixed-iteration ordinary-sim top-N, plus a cancellable combined one-call
   wrapper. Result semantics are `BEST_FOUND` inside the screened domain only.
5. NEXT: set-aware response/layout refinement, cheap roll adaptation, adaptive
   higher-iteration close-leader reracing, finalist persistent cache/progress,
   user-facing percent/delta/tie adapter, integrated benchmarks and the offline
   oracle/adversarial recall gate.
6. Selected-set real inventory candidate generation plus joint no-reuse solver
   and ordinary GCSIM validation.
7. Add the separate required `2p+2p` tracks: selected-target account support
   and the independent theoretical `Find best 2p+2p` command. Do not fold either
   into the normal theoretical `4p` action.
8. Only then draw the optimizer subwindow using the existing Browser team,
   rotation, settings, runner status, and Artifact Browser preset services.

## 13. Historical Backend Implementation Record

The original first-task direction was completed. The detailed record below is
kept for engine/patch debugging and release validation; it is not the current
task queue. Use the authoritative status and current implementation sequence at
the top of this file for new work.

Current implementation state:

- Initial isolated backend prototype exists in `run_workspace/gcsim/engine_store.py`.
- It models a local engine store with `engines/`, `staging/`, `failed/`, an `active_engine.json` pointer, and per-engine `gtt_engine_manifest.json`.
- `GcsimEngineStore.prepare_engine_update(...)` copies a source-like tree into staging, applies a replaceable `PatchBackend`, runs an optional smoke-check callable, writes the manifest, then activates the new engine only after all steps pass.
- The default `OverlayPatchBackend` is test-only/prototype-friendly: it copies files from a patch-stack directory over the staged source. It proves transaction boundaries without requiring real GCSIM source, network, Go, or `git apply`.
- Production-oriented patch backend exists in `run_workspace/gcsim/patch_backends.py` as `GitApplyPatchBackend`. It discovers ordered `.patch` files from the patch stack, runs `git apply --check`, then runs `git apply`. Git subprocesses set `GIT_CEILING_DIRECTORIES` so prepared engine trees under generated `data/gcsim/...` paths are patched as isolated source folders instead of being interpreted through the parent GTT repository. Missing git, check failure, and apply failure are controlled patch failures; the engine store preserves the failed staging folder and keeps the previous active engine.
- Backend/dev update command supports explicit patch backend selection:
  `python -m run_workspace.gcsim.engine_update --release latest --patch-backend git`.
  Overlay remains the conservative default. If the default `run_workspace/gcsim/patch_stack/` directory is absent or a selected patch stack has no `.patch` files, the git backend reports a no-patch success and does not invoke git.
- Optional build artifact flag exists:
  `python -m run_workspace.gcsim.engine_update --release latest --patch-backend git --build-artifact`.
  It runs `go version`, requires `windows/amd64`, runs `go build -o build/gtt-gcsim.exe ./cmd/gcsim` inside the staged engine source, then verifies the built executable with `build/gtt-gcsim.exe -version`. The new engine activates only when build and artifact runtime check pass.
- First real GTT patch content exists at `run_workspace/gcsim/patch_stack/0001-gtt-engine-marker.patch`. It adds a minimal `pkg/gtt` package and a `-gtt-info` CLI flag to `cmd/gcsim/main.go`.
- Sequential-wave prototype patch exists at `run_workspace/gcsim/patch_stack/0002-gtt-sequential-wave-prototype.patch`. It is opt-in through a vanilla-ignored config comment directive:
  `# gtt_wave_prototype duplicate_first_target=1`.
  The prototype reads that directive before simulation run, duplicates/reuses the first configured finite-HP target as the next wave, hooks damage-mode `stopCheck()` so a pending GTT wave can spawn before vanilla all-dead termination, and keeps the new target visible to the dynamic status/damage result paths needed by this smoke. This proves a next target can be spawned inside one simulation iteration after the current finite-HP target/group dies, preserving the run rather than ending immediately. It does not model real Abyss waves, groups, spawn positions, enemy identities, target key mapping, or final 3+3+3 policy.
- Structured wave scenario payload patch exists at `run_workspace/gcsim/patch_stack/0003-gtt-wave-scenario-payload.patch`. It adds a `-gtt-wave-scenario scenario.json` CLI flag and `simulator.Options.GTTWaveScenarioPath`. Empty path is a no-op so vanilla runs remain unchanged. Explicit payload errors are fatal and must not silently fall back to vanilla.
- Payload schema v1 is intentionally minimal and app-owned: `schema_version=1`, `spawn_policy="group_clear"`, and `waves[].targets[]` with required `level`, `type`, and explicit `hp`. The patch builds each enemy through GCSIM's target type/profile path (`enemy.ConfigureTarget`), so `type` owns monster stats/resists and the payload HP is applied as an explicit override after the profile is configured. Optional `pos`/`radius` remain explicit overrides only; normal Abyss bridge output does not write them. The first payload wave replaces parsed config targets; remaining waves are stored on `ActionList` and deep-copied per simulation iteration. Current implemented `group_clear` behavior is sequential groups: when all enemies in the current group are dead, the scheduler spawns the next payload group inside the same iteration. If a wave contains multiple targets, killing one target does not spawn the next wave; the whole current group must be cleared first, and then the next wave spawns as a whole group. This still does not implement key mapping, real Abyss 3+3+3 policy, rolling replacement, stack replacement, or UI integration.
- Future DPS mode contract: single-target DPS should use the selected single target and then the next single target. This should later be tied to the existing fact-DPS single-target/multi-target setting so fact DPS and GCSIM DPS describe the same target model. Multi-target DPS should eventually expose settings-backed modes: `sequential waves` (current implemented group-clear behavior) and `stack/rolling replacement` (future, not implemented), where enemies from the next wave may be added to replace dead enemies from the current group. Do not implement stack mode until the in-game behavior/policy is confirmed.
- Current `-gtt-info` for a built patched artifact should report `gtt_engine=true`, `gtt_patch_version=gtt-wave-scenario-v1`, `capabilities=["gtt_engine_marker","gtt_wave_scheduler_prototype","gtt_wave_scenario_payload"]`, `sequential_waves=true`, `wave_scheduler_stage="scenario_payload_prototype"`, and the upstream version when available. This is a prototype capability signal, not a final Abyss-correctness claim.
- Built artifact metadata is recorded in the manifest/report: artifact path, filename, sha256, build status, artifact runtime check status, Go version/OS/arch, build command/stdout/stderr, artifact version command/stdout/stderr, GTT marker status/version/capabilities/stdout/stderr, `artifact_kind=local_build`, and `shipped_fallback_status=resolver_available_not_bundled`. `runtime_ready=true` means either the legacy no-build `--probe-runtime` passed or, when `--build-artifact` is requested, the built executable passed the artifact checks. If `--build-artifact` is used with a non-empty `.patch` stack, the built executable must also pass `build/gtt-gcsim.exe -gtt-info`; missing, nonzero, invalid JSON, missing patch version, or missing `gtt_engine_marker` capability keeps the previous active engine.
- Minimal artifact runner exists in `run_workspace/gcsim/artifact_runner.py`, with a dev CLI at:
  `python -m run_workspace.gcsim.run_smoke --config path --gtt-wave-scenario scenario.json --format text`.
  It resolves the active engine from `GcsimEngineStore`, locates the built artifact recorded in the manifest, writes caller-provided config text to a run directory, executes `gtt-gcsim.exe -gtt-wave-scenario scenario.json -c config.txt -out result.json` when a scenario is supplied, captures stdout/stderr/return code, enforces a timeout, and parses only a tolerant summary from uncompressed JSON results: schema version, sim version, `statistics.dps.mean`, `statistics.duration.mean`, `statistics.total_damage.mean`, warnings, failed actions, and incomplete characters. It intentionally does not generate account/team configs, map keys, final Abyss wave policies, or integrate with UI.
- Shipped fallback artifact resolver exists in `run_workspace/gcsim/shipped_artifact.py`. The default candidate path is `run_workspace/gcsim/shipped/gtt-gcsim.exe`, but no production binary is bundled yet. The resolver reports explicit statuses (`disabled`, `candidate_missing`, `candidate_ready`, `candidate_not_file`, `candidate_invalid_path`) and requires an actual file for `candidate_ready`. `run_active_gcsim_artifact(...)` has explicit opt-in fallback support: the active built artifact remains first priority, and a ready shipped fallback is used only when the active artifact is unavailable. Run results now include `artifact_source`, `active_artifact_status`, and `shipped_fallback_status` diagnostics. Shipped binary marker/capability validation is not implemented yet and remains release-process work.
- A narrow backend Abyss-to-GTT-wave bridge now exists in `run_workspace/gcsim/abyss_wave_scenario.py`. It consumes typed `AbyssFloorSourceData`, selects one chamber/side, audits rows grouped by source waves, expands `enemy_count` into individual schema-v1 targets, and can produce a `group_clear` payload dict plus a separate audit/result object. Payload generation is ready only when required source HP/level fields are present and each enemy resolves to a compatible valid GCSIM target type. GTT writes explicit Abyss HP into the payload, so exact GCSIM HP/variant identity is not required at this stage; for example, `Grounded Geoshroom -> groundedgeoshroom` is acceptable when it avoids `unknown target type` and preserves usable GCSIM enemy stats/resists. Nanoka monster id is the preferred strong identity for manual overrides when present, but it is not the only allowed identity: Fandom enemy page URL/page title/name candidates must remain valid fallback identities, and enemy-type fallback must be independent from HP source fallback. HP may come from Nanoka while GCSIM type resolves through Fandom/name identity, or HP may come from Fandom fallback while type resolves through Nanoka/name identity. Managed Snap Monster title cache support exists in `run_workspace/gcsim/snap_monster_titles.py` as a last-resort enemy `Name -> Title` fallback after manual overrides, normal registry exact/base matching, and small aliases fail. The normal app-style contract is cache-first: primary matching runs without Snap; if rows remain unresolved, GTT may check the managed cached `data/cache/gcsim/snap_metadata/Monster.json`; if cached `Name -> Title` matching and cached title-containing-target matching are still insufficient, the cache may be refreshed from the official online Snap.Metadata file `https://github.com/wangdage12/Snap.Metadata/blob/main/Genshin/EN/Monster.json` and then rechecked. No Git install or Snap.Metadata repository checkout is required. The refresh step reads the single online `Monster.json` over HTTPS and persists only the managed cache file plus a small sidecar metadata file. A local file path or direct URL remains supported only as an explicit dev/offline/debug input, not as the normal app contract. Only `Name` and `Title` are read; Snap metadata must not be used as HP/stat/resist/wave/count truth or source-data replacement. Duplicate normalized Snap `Name` records with different `Title` values are ambiguous instead of silently chosen. If the Snap `Title` still does not exact/base-match the registry, the final last-resort matcher may resolve a unique GCSIM target whose key contains the full normalized Snap title (`snap_title_contains_target`); multiple containing targets remain ambiguous. This covers cases such as `Tenebrous Papilla: Type II -> Tenebrous Papilla -> tenebrouspapillatypei` without turning arbitrary display-name fuzziness into production truth. Missing Nanoka id alone is not a blocker; the blocker is missing any safe explicit or automatic compatible GCSIM target type. The bridge must not infer production-ready GCSIM type keys from arbitrary fuzzy/display-name similarity.
- Dev CLI `python -m run_workspace.gcsim.abyss_wave_scenario_smoke` loads either the current cached Abyss period or an explicit cached period/floor, builds the provisional schema-v1 scenario JSON for a selected chamber/side, and can optionally pass that scenario to the existing active artifact runner with a caller-provided config. It accepts explicit override mapping JSON, `--gcsim-enemy-registry-source path` for automatic known-target matching, managed Snap cache flags `--use-cached-snap-monster-json`, `--refresh-snap-monster-json-if-needed`, and optional `--snap-monster-cache-path`. Direct `--snap-monster-json PATH_OR_URL` and `--use-default-remote-snap-monster-json` remain dev/debug overrides and are mutually exclusive with the managed flow. Remote Snap refresh failures, invalid JSON, and invalid shape are controlled input errors. Missing cache/source fields or missing/ambiguous enemy type resolution prints the audit and exits nonzero without writing/running a misleading scenario. Backend reports expose progress steps such as `matching_enemy_names_primary`, `checking_cached_snap_titles`, `refreshing_snap_metadata`, `rechecking_snap_titles_after_refresh`, `building_abyss_wave_scenario`, and `running_gcsim_artifact`. Coverage reports also include `timing_seconds` diagnostics for primary matching, cached Snap loading/matching, remote refresh/indexing when it happens, refreshed matching, and total report time. The first forced Snap fallback can be noticeably slower because it refreshes the managed runtime cache from the online `Monster.json`; later runs should use the cached file and avoid network. Artifact runs that supply `gtt_wave_scenario` now preflight-check the selected artifact with `-gtt-info` before sim execution. The selected active or shipped fallback artifact must report `gtt_patch_version=gtt-wave-scenario-v1` and capability `gtt_wave_scenario_payload`; stale artifacts fail with `artifact_wave_scenario_contract_mismatch`, observed/required version/capability diagnostics, and a rebuild-required message before sim execution. Runs without a wave scenario keep the previous behavior. Stable backend/dev smoke case catalog exists at `run_workspace/gcsim/smoke_cases.py`, with committed manual config fixture `run_workspace/gcsim/smoke_fixtures/manual_config_minimal.txt`. Named case `abyss_2026_04_16_f12_c3_s2_manual_config` proves manual GCSIM config plus generated cached Abyss wave scenario, managed cache-first Snap matching, and artifact preflight/run parsing without depending on an ad-hoc runtime run directory config. Latest manual case run passed through the active artifact: scenario generation used managed Snap cache hit (`remote_not_needed`), resolved `Tenebrous Papilla: Type II` by `snap_title_contains_target` to `tenebrouspapillatypei`, built one wave / one target, and artifact preflight observed `gtt-wave-scenario-v1` with `gtt_wave_scenario_payload`. Parsed run summary stayed smoke-only: duration_mean `0.03333333333333333`, dps_mean `0.0`, total_damage_mean `0.0`; do not treat this as DPS correctness. Future UI loader messages should surface these backend steps so enemy matching, Snap refresh, scenario build, and optional artifact run do not look frozen. This remains backend/dev-only and still does not generate account/team configs, broad key mappings, final Abyss wave policy, or UI state.
- Additional manual/dev fixture `run_workspace/gcsim/smoke_fixtures/manual_config_neuv_furina_lauma_xiangling.txt` stores a hand-written Neuvillette/Furina/Lauma/Xiangling config for backend compatibility diagnostics only. It is not generated account config and not benchmark truth. Its manual `target` lines are placeholders; when used through `abyss_wave_scenario_smoke`, generated `-gtt-wave-scenario` JSON remains the enemy/wave/HP/type source of truth. A real local run on 2026-06-05 for cached period `2026-05-16` F12 C2 S1 built three exact-name scenario waves (`fatuielectrocicinmage`, `ruindrakeearthguard`, `primogeovishap`) and passed artifact preflight. This smoke exposed a patched GCSIM runtime panic in `pkg/stats/damage/damage.go`: dynamically spawned wave enemies can receive sparse target keys after gadgets, while cumulative damage buckets were sized by current enemy count and indexed by `targetKey-1`. Patch-stack fix `0004-gtt-dynamic-wave-stats.patch` makes damage cumulative buckets grow by resolved enemy index and lets aura aggregation grow for dynamic `result.Enemies`. After rebuilding the active artifact in-place on 2026-06-05, the same 3-wave smoke passed with artifact preflight intact. The same config also still passes without `-gtt-wave-scenario`. No DPS correctness claim.
- Enemy type mapping JSON supports explicit records with `source_kind`, `source_id`, `gcsim_type`, diagnostic `source_name`, and optional notes/warnings. The previous `enemy_types_by_nanoka_monster_id` shape still loads for dev compatibility, but explicit records are now the first-priority override/exception layer, not a full production enemy database. Duplicate records for the same identity are reported as ambiguous and are not silently chosen.
- Backend/dev GCSIM enemy type registry matcher exists in `run_workspace/gcsim/enemy_type_registry.py`. It parses known target type keys from local prepared GCSIM `pkg/shortcut/enemies_gen.go` and can resolve Abyss Nanoka/Fandom name candidates by exact normalized name, compatible/base-name rules that strip controlled variant tokens, and small explicit aliases for known exceptions. Automatic matching runs only after manual overrides fail. Missing or ambiguous compatible matches are reported instead of guessed, and fuzzy/display-name similarity is not production truth. Full production validation still depends on using a current prepared GCSIM source registry and later real-engine checks.
- Dev coverage checker `python -m run_workspace.gcsim.abyss_enemy_type_mapping_report --gcsim-enemy-registry-source path --scan-cache-dir data/cache/abyss/source_data --format text` verifies cached Abyss source-data against optional overrides plus the GCSIM enemy type registry without Abyss network refresh, GCSIM runs, or UI imports. It accepts repeated `--cache-file`, single `--cache-dir --period-start --floor`, or bulk `--scan-cache-dir` over `**/floor_*.json`; `--period-start` and `--floor` filter bulk scans. It accepts the same managed Snap cache flags as the smoke CLI. Network is not used when primary registry matching resolves all rows, and is not used when cached Snap title fallback resolves the remaining rows. The online Snap `Monster.json` refresh is a last step only when explicitly enabled and cache results are missing, invalid, or insufficient. The report records `snap_cache`, refresh/cache status, source kind, progress `steps`, and Snap fallback counts. Direct `--snap-monster-json PATH_OR_URL` and `--use-default-remote-snap-monster-json` remain dev/debug overrides. Snap fallback resolutions are counted separately as `snap_title_fallback`, and final containing-target resolutions as `snap_title_contains_target`, so exact/base/alias coverage remains visible. It reports cache file count, total rows, resolution counts by method (`manual_mapping`, `exact_normalized_name`, `compatible_base_name`, `manual_alias`, optional `snap_title_fallback`/`snap_title_contains_target`), counts by identity/name source, missing/ambiguous mappings, HP-present/type-missing rows, type-present/HP-missing rows, compact unresolved/ambiguous text rows, JSON resolved rows with selected type/method, and unresolved rows with all available identities. Current real-code-path diagnostic over the 8 cached source files / 96 rows resolved 88 exact, 7 `snap_title_fallback`, 1 `snap_title_contains_target`, 0 missing, and 0 ambiguous after Snap title fallback. Use it to validate matcher behavior on existing caches for both normal Nanoka-backed data and forced Fandom fallback/Fandom-only caches. Missing/ambiguous rows should drive small matcher or alias fixes, not a full hand-written enemy mapping table. Full production enemy type coverage remains future work.
- Backend config readiness audit now exists in `run_workspace/gcsim/config_readiness.py`. It is adapter-free and accepts lightweight prepared team inputs instead of UI widgets or SQLite rows directly. It audits explicit GCSIM mapping refs for characters, weapons, and artifact sets; current/max character level; equipped weapon level/refinement; artifact completeness and normalized artifact add-stats via the existing stat-normalization layer; and account-observed talent levels only when normal/skill/burst order is confirmed. Missing or display-name-only mappings report `missing_mapping`, ambiguous mappings report `ambiguous_mapping`, Traveler remains `unsupported_traveler`, and missing source fields such as level/weapon/artifacts/talents report controlled readiness statuses. This still does not generate config text, create real project-id-to-GCSIM mapping data/reports, query account/equipment storage, run artifacts, or wire UI.
- Backend GCSIM key-mapping report foundation now exists in `run_workspace/gcsim/key_mapping.py`. It defines explicit character, weapon, and artifact-set mapping records with project id/set uid, diagnostic canonical name, `gcsim_key`, source kind/name, readiness status, warnings, and optional ambiguous candidates. It converts ready records into `config_readiness.GcsimMappingRef` values and reports counts/missing/ambiguous entries by entity type. The current boundary is seed/fixture-oriented (`curated`, `curated_test_fixture`, `dev_fixture`, `test_fixture`) because no reliable committed production `project id -> GCSIM key` source has been identified. Display-name, localized-name, and normalized-name-guess sources are rejected as not ready; Traveler remains explicitly unsupported/deferred. This still does not create production mapping data, generate config text, query account/equipment storage, run artifacts, or wire UI.
- Tiny committed GCSIM key-mapping dev seed now exists at `run_workspace/gcsim/mapping_seeds/gcsim_key_mapping_seed_v1.json`, with a report CLI at `python -m run_workspace.gcsim.key_mapping_report --format text|json`. The default report keeps `production_mapping_data_missing` because the seed is intentionally tiny and not production-complete. Current records cover only explicit dev/fixture-backed Mona, Favonius Codex, and Noblesse Oblige keys; do not extrapolate from these names or slugs, and do not treat this as full character/weapon/artifact-set mapping coverage. Full mapping source generation/curation remains future work.
- Backend/dev entity registry coverage report has been added in `run_workspace/gcsim/entity_key_readiness_report.py`, with CLI `python -m run_workspace.gcsim.entity_key_readiness_report --format text|json`. It parses local prepared GCSIM shortcut sources for accepted character, weapon, and artifact set keys, prefers explicit seed overrides, then reports exact normalized candidates, conservative contiguous-name-span candidates, missing rows, ambiguous rows, and unsupported Traveler/Traveler variants. Default local diagnostics read existing HoYoWiki character/weapon stats caches plus the artifact set static seed; HoYoWiki `entry_page_id` identities are flagged as diagnostic and are not treated as the missing production game-id mapping owner. This report is not an account SQLite mapper: its character names are local HoYoWiki cache/catalog names, not localized `account_characters.name` values. Exact and contiguous-span candidates are not committed curated production mappings. Local diagnostic on 2026-06-05 over available caches after span fallback reported 414 entities total: characters 102 ready / 15 missing / 7 unsupported Traveler / 0 ambiguous, weapons 225 ready / 6 missing / 0 ambiguous, artifact sets 58 ready / 1 missing / 0 ambiguous. Match methods were 382 `exact_normalized_name`, 2 `contiguous_name_span`, 1 `explicit_seed`, 22 missing, and 7 unsupported Traveler. Current-registry gaps remain controlled missing and should later surface as user-facing warnings such as "GCSIM implementation is missing for this character/weapon/set; replace it or update GCSIM source." This still does not generate config text, query account/equipment storage, run artifacts, or wire UI.
- Account SQLite sync stores account-owned GCSIM key enrichment for
  `account_characters` and `account_weapon_observed_stacks`: English HoYoWiki
  `catalog_english_name`, resolved key, status, and method. The resolver loads
  local GCSIM character/weapon shortcut keys once per sync and then does
  in-memory matching. Local backfill on 2026-06-05 updated `data/artifacts.db` in
  about 1.1s: 65 account characters and 64 observed weapon stacks were `ready`,
  7 characters and 2 weapon stacks were current-registry `missing`, and account
  Traveler stayed `unsupported_traveler`. Known current-GCSIM-registry missing
  account rows are expected gaps, not account mapper failures: characters
  `10000100` Kachina, `10000110` Iansan, `10000113` Ifa, `10000123` Durin,
  `10000124` Jahoda, `10000127` Illuga, and `10000130` Linnea; weapon stacks
  `12432` Flame-Forged Insight and `15516` Golden Frostbound Oath. Account
  Traveler `10000007` remains `unsupported_traveler` because variant selection is
  still deferred. These counts are local-account diagnostics, not global
  coverage. This still does not generate configs or solve artifact-set
  mapping/current-build selection.
- GCSIM level text helper has been added in `run_workspace/gcsim/config_level.py`. It formats future config levels from account `level` plus optional `promote_level`: `80,5 -> 80/80`, `80,6 -> 80/90`, `70,4 -> 70/70`, `70,5 -> 70/80`, missing promote on breakpoint levels assumes after ascension with a warning, and final/special caps use `90/90`, `95/95`, and `100/100`. Missing level returns controlled `missing_level`.
- Backend character config block builder has been added in `run_workspace/gcsim/config_blocks.py`. It renders a single prepared character/equipment block from explicit mapping refs, level helper data, constellation/talents, weapon data, artifact set counts, and artifact-snapshot-only normalized `add stats`. Not-ready inputs return issues and no partial config text. This still does not generate full configs, create mappings, query account/UI storage, run artifacts, or wire UI.
- Backend/dev full-config assembler has been added in `run_workspace/gcsim/config_assembly.py`, with shell-only rotation fixture `run_workspace/gcsim/smoke_fixtures/rotation_chasca_ororon_furina_bennett.txt`. The fixture preserves Chasca/Ororon/Furina/Bennett options/energy/active/script plus a placeholder target, while generated character blocks and generated `-gtt-wave-scenario` remain the account/team and enemy truth sources. Explicit prepared-input adapter and CLI bridge have been added in `run_workspace/gcsim/prepared_config_adapter.py`; default synthetic fixture `run_workspace/gcsim/smoke_fixtures/prepared_team_chasca_ororon_furina_bennett.json` can generate four ready blocks and assemble a full config only when all prepared data is ready. Account SQLite backend/dev bridge has been added in `run_workspace/gcsim/account_prepared_config.py`; it reads real account character rows and ready stored character/weapon GCSIM keys, uses current-equipped weapons when available, reports deterministic dev weapon candidates when not, normalizes displayed talent levels through `run_workspace/gcsim/config_talents.py`, uses current-equipped artifact owner rows plus artifact main/sub stat totals when available, and can run an end-to-end account-prepared + manual shell + generated Abyss wave compatibility smoke with dev-only boosted energy. Missing/incomplete current artifacts stay controlled not-ready, not silent synthetic fallback. Browser production wiring now uses `run_workspace/gcsim/selected_team_config.py`: it consumes selected TeamBuilder/AppShell state, resolves account data by stable ids, never chooses dev fallback weapons, uses Account/GCSIM settings-controlled boosted energy, feeds grouped readiness summaries through `run_workspace/gcsim/readiness_summary.py`, writes typed-session right-panel Sim DPS rows for Abyss selected-chamber and 3-chamber Browser runs, includes current Abyss results in normal Run Save snapshots, and reports DPS Dummy target/energy diagnostics without claiming damage correctness. `account_prepared_config.py` remains a dev CLI/smoke bridge.
- Tests in `tests/run_workspace/gcsim/test_gcsim_engine_store.py` pin success activation, patch failure rollback, smoke failure rollback, manifest metadata, and old-active availability.
- Official GitHub source acquisition exists in `run_workspace/gcsim/source_acquisition.py`. It resolves official `genshinsim/gcsim` releases through the GitHub API, downloads the release source zip, extracts the single top-level source tree into `data/gcsim/sources/`, and rejects unsafe/corrupt archives.
- Backend/dev update command exists at `python -m run_workspace.gcsim.engine_update --release latest`. It downloads official source, calls `GcsimEngineStore.prepare_engine_update(...)`, applies the selected replaceable patch backend, runs a source-layout smoke check for `go.mod`, `cmd/gcsim/main.go`, `pkg/simulator`, and `pkg/model`, writes source/patch/check metadata into the manifest, and activates only on success.
- Optional runtime probe flag exists: `python -m run_workspace.gcsim.engine_update --release latest --probe-runtime`. It first checks `go version`, requires `windows/amd64`, then runs `go run ./cmd/gcsim -version` from the prepared source tree with a timeout. If Go is missing, wrong-arch, times out, or exits nonzero, the staged engine is not activated and the previous active engine remains active.
- Go subprocesses launched by this backend use project-local cache/bin directories under `.go/` via `GOMODCACHE`, `GOCACHE`, and `GOBIN`; `.go/` is ignored. Investigation on 2026-06-11 found `.go/build-cache` can grow to about `4.94 GB` after repeated GCSIM builds/probes, while `.go/pkg/mod` was only about `53 MB`. `engine_update` now deletes rebuildable `.go/build-cache` after a successful `--probe-runtime` or `--build-artifact` unless `--keep-go-build-cache` is passed; module cache stays.
- Engine/source runtime data is local/generated and ignored under `data/gcsim/`. Investigation on 2026-06-11 found repeated successful/failed full engine copies were the main `data/gcsim` growth source: `data/gcsim/engines` was about `1.71 GB`, while `data/gcsim/runs` was only about `6.6 MB`. Generated engine-store retention now keeps active + one previous successful engine plus one latest failed engine and prunes older generated/staging folders. Manual cleanup/dry-run command: `python -m run_workspace.gcsim.cleanup`; pass `--apply` to delete. The same command also bounds old run dirs, currently keeping 50 recent run dirs and up to 256 MB by default.
- Default check status remains source-layout only and records `runtime_ready=false` / `runtime_check_status=not_requested`. With `--probe-runtime`, a successful no-build probe records `runtime_ready=true`, `runtime_check_status=runtime_probe_passed`, `go_version`, `go_os`, `go_arch`, and truncated probe stdout/stderr metadata. With `--build-artifact`, the preferred runtime check is the built executable, not `go run`.
- Tests in `tests/run_workspace/gcsim/test_gcsim_patch_backends.py` pin git backend ordered patch success, parent-repo discovery isolation, missing git, patch check failure, patch apply failure, empty patch stack success, and previous-active preservation. Tests in `tests/run_workspace/gcsim/test_gcsim_engine_update.py` pin fake official-source acquisition, download failure, corrupt archive failure, layout-smoke failure, manifest metadata, old-active preservation, Go-missing, wrong-arch, nonzero probe, timeout, default no-probe behavior, successful fake runtime-ready activation, git patch backend plus runtime probe together, successful fake build artifact activation, Go missing/wrong arch/build failure/artifact version failure rollback, artifact sha256 metadata, GTT marker success activation, and GTT marker failure rollback.
- A real local validation command succeeded on 2026-06-04:
  `python -m run_workspace.gcsim.engine_update --release latest --patch-backend git --probe-runtime --build-artifact --format text`.
  After the structured payload patch, it built official upstream `v2.42.2`, activated engine `gcsim-v2.42.2-20260604175430`, produced `build/gtt-gcsim.exe` with sha256 `c06aa07af8924b3bafb7ad9097bc3e5e39f9570e99958dd43cd20c3a760b6921`, and `-gtt-info` returned `gtt_patch_version=gtt-wave-scenario-v1` plus `gtt_wave_scheduler_prototype` and `gtt_wave_scenario_payload` with `sequential_waves=true`.
- A real local sequential-wave prototype smoke also succeeded on 2026-06-04 through `run_smoke`. The smoke used `iteration=1`, `duration=10`, a single finite-HP target, Bennett, and `kill_target(...)` sysfunc calls so the observable is duration rather than damage. Without the GTT directive, the sim ended after the first killed target with `duration_mean=0.0333333`. With `# gtt_wave_prototype duplicate_first_target=1`, the patched engine spawned one more copy of the first target and continued to `duration_mean=1.03333`. This proves continuation/spawn inside one iteration, but not real Abyss wave modeling.
- A real local structured payload smoke also succeeded on 2026-06-04 through `run_smoke --gtt-wave-scenario scenario.json`. With the same simple config and a two-wave `group_clear` payload, no-payload duration remained `0.0333333`, while payload duration was `1.03333`. A bad payload with `spawn_policy="rolling"` failed clearly with `unsupported spawn_policy "rolling"; expected "group_clear"` instead of silently falling back to vanilla.
- Engine/config/scenario/result backend preparation is complete for the current
  Abyss Browser MVP. Remaining engine-side work is release packaging/validation
  of the shipped binary plus targeted patch maintenance when a real regression
  or new wave policy requires it. Do not reopen completed config generation or
  app-side scenario generation as generic tasks.
