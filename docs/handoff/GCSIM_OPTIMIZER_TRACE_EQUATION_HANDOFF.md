# GCSIM Artifact Optimizer — current authoritative handoff

Status: GOB-3 through GOB-10 PASS. The bounded adaptive final gate preserves
n=128 recall, starts all retained finalists at n=500 and reruns only a small
statistically unresolved leader group at n=1000. The single full Go product
performance replay completed in 57.0 seconds after preparation and resolved at
n=500 with the same known winner. Final reachability, patch consolidation,
update, rollback and compute optimization are complete. Updated 2026-09-01.

This is the sole current optimizer handoff. Read it together with:

- GCSIM_OPTIMIZER_GO_BACKEND_DESIGN.md — active implementation design;
- GCSIM_ENGINE_INTEGRATION_PLAN.md — engine update, patch and rollback boundary;
- GCSIM_OPTIMIZER_TRACE_EQUATION_CLEANUP_MANIFEST.json — detailed receipts and deletion disposition;

Old M/S/Gate, Selected V2, CF-BB, Adaptive Oracle Exchange and Contextual Scan plans are not active architecture.

## 1. Product goal

The application needs three optimizer modes:

1. Selected Sets — search real account artifacts inside fixed 4p set packages.
2. All Sets — choose promising set packages and real artifacts.
3. Theory / farming guidance — explain useful main stats, balance, plateaus and future farming targets.

Current implementation work is only Selected Sets. A successful Selected run returns:

- five artifact IDs for each of four characters;
- twenty globally unique physical IDs;
- measured adaptive n=500/n=1000 GCSIM DPS and standard error;
- formula estimate, residual and uncertainty warnings;
- deterministic debug receipt;
- no automatic equip; every character row can be saved explicitly as a normal
  Artifact Browser preset through the existing preset storage service.

Cold Selected above 190 seconds remains a performance failure criterion. GOB-10
now passes it with a predicted 62-64 second full UI path. The temporary 360
second UI boundary remains only a fail-safe. All Sets has a separate future
600-second boundary.

## 2. Accepted production architecture

The future product backend is gtt_gcsim_optimizer_go_v1.

It has two parts:

### Standalone Go optimizer

Path: native/gcsim_optimizer.

It owns:

- compact request/result/progress contracts;
- artifact stat arrays and physical legality;
- formula compilation and stochastic expectation;
- Formula-Guided Build Search;
- finalist policy and adaptive ordinary n=500/n=1000 verification;
- cache, cancellation, timings and debug receipt.

It must not import gcsim/internal packages.

### Minimal GCSIM adapter patch

The engine patch owns only unavoidable runtime observation:

- executed hit/reaction formula evidence;
- support/state/heal/drain dependencies reaching damage;
- typed opaque boundaries;
- engine/source/config/seed identities;
- ordinary simulation entrypoints.

It converts GCSIM internals into stable compact GTT IR. Artifact search, FGBS and finalist selection do not live in the engine patch.

Python/UI sends one compact request and receives progress plus the final IDs/DPS. There is no Python-Go call per candidate.

## 3. What the Python work actually proved

Python is now a temporary parity oracle, not the future product backend.

Proven:

- raw artifact stats can be separated as variables from the observed non-artifact context;
- FAST groups only response-equivalent hits and keeps attack type/damage type distinctions;
- expected crit with CR capped at 100% is supported;
- ordinary and owned-reaction formula channels work for the current rotation;
- generic support replay can connect one character's artifact stat through healing/state/modifiers into another character's damage;
- Bennett artifact HP% changes the traced team formula through the support chain without a Bennett/Furina name switch;
- unknown mechanics can freeze at a typed boundary while known formula regions continue;
- fixed 4p, maximum one off-set item per wearer and globally unique physical IDs are enforced;
- FGBS evaluates complete five-piece wearer builds, cycles team anchors and checks linked/conflicting pairs;
- the bounded Python search returned one stable current-account leader across its declared control;
- the two-seed equal-weight protocol combines different hit/reaction schedules without choosing a favorable seed.

Key receipts:

- accepted Python cold path: 181.43 seconds under the user-approved 190-second boundary;
- adjacent seeds: 365/389 hits and 68/90 reaction hits;
- member FAST: 141306.04/144641.03 DPS;
- two-seed mean: 142973.54 DPS, 0.532% below the frozen same-context n=1000 value 143738.29;
- two raw traces: 69.1/70.9 MB;
- two-seed preparation: 50.47 seconds;
- focused stochastic tests: 14 PASS;
- focused FGBS tests: 45 PASS.

The naive Python multi-trace representation is a product runtime failure. Merely adding the second engine plus decode cost to 181.43 seconds exceeds 190 seconds before extra candidate scoring.

## 4. What is not proved

Do not claim any of the following:

- global mathematical optimum;
- support saturation for every actor;
- complete handling of every future reaction/mechanic;
- automatic compatibility of the v2.42.2 adapter patch with GCSIM v2.45.0;
- a fresh GOB-10 measurement initiated by an actual UI click rather than the
  same product boundary replayed from the saved real request.

Selected is accepted as a bounded practical search, not a proof of optimum.

## 5. Formula and unknown-mechanic rules

The optimizer predicts expected damage for a fixed team, rotation, target and engine context. It does not need to reproduce every random hit exactly.

Required rules:

- artifact-controlled stats are explicit variables;
- weapon, ascension, rotation buffs and other known context remain fixed or become typed derived mechanics;
- damage types or attack categories with different modifiers remain separate;
- reaction ownership and EM dependencies come from engine evidence;
- support dependencies are followed recursively to artifact stat leaves when representable;
- opaque behavior freezes at the last known boundary;
- frozen share remains visible and cannot prove dominance or saturation;
- a material unknown widens retained finalists and produces diagnostics;
- no character, set, element or reaction name switch in generic evaluator/search code;
- energy/ER optimization remains deferred.

Reaction-dominant and future Lunar/multi-contributor teams remain required later controls. Damage share, not hit count, determines whether an unknown path is material.

## 6. Selected artifact/search rules retained for Go

The Go rewrite keeps the method, not the Python implementation:

1. Precompute each artifact's normalized numeric contribution.
2. Search complete five-slot wearer builds.
3. Enforce selected 4p package and at most one off-set item.
4. Enforce twenty globally unique IDs across the team.
5. Preserve the incumbent and materially different direct/reaction/support lanes.
6. Never permanently delete an item only because it is weak alone.
7. Use CR cap and other proven caps in evaluation.
8. Freeze a low-value actor only with a complete revocable certificate.
9. Rebuild wearers against the current complete team anchor.
10. Recheck dependency cycles.
11. Check linked/conflicting simultaneous changes and off-set transfer.
12. Keep unresolved wider provider components explicit.
13. Send a bounded retained set to common-fidelity GCSIM.
14. Call the result bounded/provisional unless its exact acceptance proves more.

Python widths 32->8 are benchmark evidence, not mandatory Go constants. Go may use arrays, indexes, bitsets, pooled states, compiled operations and batch evaluation, but quality cannot be weakened silently.

## 7. Current Go implementation sequence

### GOB-0 — PASS

Architecture and migration contract accepted:

- standalone Go optimizer;
- minimal compact GCSIM adapter;
- Python frozen as parity reference;
- continuous optimum reserved for later Theory/All Sets Go port.

### GOB-1 — PASS

Create only:

- isolated native/gcsim_optimizer module and command;
- canonical request, progress, compact-IR and result schemas;
- deterministic identity/hashing and strict validation;
- cancellation contract;
- shared synthetic round-trip fixtures/tests.

No engine patch, search, full account run, n=1000 or UI. Stop for review after the focused gate.

Accepted implementation:

- isolated `native/gcsim_optimizer` standard-library-only Go module;
- strict request/progress/compact-IR/result v1 contracts;
- deterministic Python/Go canonical JSON and linked SHA-256 identities;
- canonical decimal-string transport for gameplay numbers;
- process-interrupt cancellation boundary;
- shared four-wearer/twenty-artifact/two-seed fixtures;
- 10 Go tests, 4 Python tests, `go vet`, clean local build and isolation scan PASS;
- engine/search/UI calls: 0.

### GOB-2 — PASS

Implement the smallest compact adapter feasibility slice for one seed. Compare compact Go formulas with accepted Python reference fixtures. Measure output size, runtime and memory. Stop if material evidence cannot be represented.

Accepted historical result: patch `0022-gtt-compact-equation-v1.patch` first
provided an opt-in
engine-neutral seed-member output without moving search into GCSIM. On frozen
seed `742031889`, its baseline and Bennett HP% candidate formula values match
the accepted Python reference within `1e-6`, including the cross-character
support chain. The payload fell from 69,085,424 to 4,548,636 bytes (15.19x),
adapter work was about 117.5 ms, and the complete command was 1.781 s. Unknown
paths remain typed; their current full-baseline exposure warnings overlap and
must not be summed as damage. This proves one-seed adapter feasibility only.

### GOB-3 — PASS

Implement bounded equal-weight stochastic expectation in Go. Stream/compile members without retaining full raw traces. Preserve sample count, dispersion and explicit stable-one-trace proof.
Opaque reason exposure is conservative and overlapping: aggregate presence and
uncertainty by member/reason, never add those exposure values as damage.

GOB-3A contract is frozen and contains no aggregator or engine run:

- seed lists come from the canonical request and are never hard-coded; the real
  development parity request uses `742031889`, `742031890`, weight `1/2` each;
- differing topology is averaged, never selected;
- `artifact_stat` means signed incumbent delta and zero delta must reproduce
  channel baseline within absolute `1e-6`;
- mean damage/DPS/actor contribution is equal-weight; sample SD uses `N-1` and
  standard error is `SD/sqrt(N)`;
- uncertainty is a sorted reason-to-member coverage map, not additive damage;
- the panel has no hard-prune, product-size, convergence or search authority;
- machine-readable contract:
  `tests/fixtures/gcsim_optimizer_go_v1/gob3a_stochastic_contract_v1.json`.

GOB-3B through GOB-3D are complete:

- the standalone Go module now owns deterministic equal-weight aggregation,
  actor means, SD/SE, baseline validation and opaque reason/member coverage;
- an isolated, non-active v2.42.2 engine was built from the historical exact 0001-0022
  patch identity and reports the compact capability;
- the two real compact members were captured sequentially in 1.576 s and
  1.569 s, have distinct topologies, and both pass strict Go plus zero-delta
  baseline validation;
- receipt:
  `tests/fixtures/gcsim_optimizer_go_v1/gob3d_two_seed_capture_receipt_v1.json`;
- two engine calls, zero search/n=1000/UI calls. The active engine was not
  changed.

GOB-3E and GOB-3F are also complete. The bound real panel matches Python within
`1e-6`: mean `142973.53500793583` DPS, both members, all actor totals, SD/SE and
all 25 uncertainty classes. Cold decode/validation confirmed that the 9.28 MB
payload must be compiled once rather than reparsed per candidate. No additional
engine execution was used.

### GOB-4

PASS. Go indexes 483 real artifacts and 37 coordinates, reconstructs Current,
enforces slot/fixed-4p/one-offpiece/global-ID legality, and matches independent
Python formula arithmetic for the incumbent, a broad profile and 20 real swaps.
Candidate arithmetic uses zero engine calls.

### GOB-5

PASS. Clean Go FGBS implements the response ledger, bounded complete wearer
frontiers, dynamic anchors, a narrow second-cycle recheck, and bounded
dependency/conflict pair refinement. On the real account it completed in 64.39
seconds, retained the Python migration leader at rank 24, and found a leader
117.68 formula DPS higher under the same two-member objective. It reports all
raw/expanded/evaluated/discarded/budget counts and keeps saturation unfrozen
while opaque dependencies remain. Formula search is accepted; gameplay quality
is not yet accepted because common n=1000 belongs to GOB-7.

Authoritative receipts:

- `tests/fixtures/gcsim_optimizer_go_v1/gob3e_real_panel_parity_receipt_v1.json`;
- `tests/fixtures/gcsim_optimizer_go_v1/gob3f_runtime_receipt_v1.json`;
- `tests/fixtures/gcsim_optimizer_go_v1/gob4_indexed_evaluator_receipt_v1.json`;
- `tests/fixtures/gcsim_optimizer_go_v1/gob5_real_account_acceptance_receipt_v1.json`.

### GOB-6 — mandatory migration cleanup

PASS. A fresh production/UI/import/test/tool scan found no accepted callers of
the replaced Python Selected stack. Python FGBS, stochastic expectation,
Selected composition, CF-BB, Adaptive Oracle, Contextual Scan, the neutral
assignment oracle and their orphaned tests/audits/handoffs were removed.

Retained deliberately: the Go implementation and receipts, the small frozen
Python migration-leader JSON, engine adapter/update primitives, Current
comparison, and the independent continuous-target mathematics plus its focused
tests for future Theory/All Sets. No n=1000 or UI work occurred during cleanup.

### GOB-7

PASS. Formula rank cannot safely choose a small K: the retained migration
leader was formula rank 24 and won measured n=1000. The accepted Go-only rule
is therefore:

1. keep all 24 bounded formula candidates and add Current;
2. screen all unique rows at common n=128;
3. retain the measured top five plus mandatory formula leader and Current,
   deduplicated to at most seven builds;
4. run every retained build at common n=1000 and select measured DPS.

The accepted clean run screened 25 builds, sent 6 to n=1000 and completed in
170.665 seconds under the 190-second product limit. Winner: 148744.2304 DPS,
SE 68.3218, exact artifact IDs `36,81,1426,1451,1437 | 80,77,87,88,203 |
1301,7,1466,1309,1319 | 76,91,241,1477,119`. Same-context Current measured
143721.6620 DPS, so the accepted gain is 5022.5683 DPS (3.4946%). Formula
residual for the winner is +726.8720 DPS. Receipt:
`tests/fixtures/gcsim_optimizer_go_v1/gob7_common_n1000_acceptance_receipt_v1.json`.
The winner exceeds the runner-up by only 73.24 DPS while their combined SE is
98.47 DPS, so the product result must show a confidence-overlap warning rather
than claim that the ordering of those two builds is statistically certain.

### GOB-8

Functional PASS; 190-second performance target still FAIL.

- The Artifact optimizer panel exposes all three product modes; only Selected
  is enabled. Selected is bound to one standalone Go process and returns exact
  IDs plus measured final DPS without auto-equipping anything.
- Typed progress, cancellation, fail-closed engine errors, warnings and debug
  receipt display are connected. Progress consumes mappings, not any legacy
  `M8ProductProgress` object.
- A fresh transactional engine build with all 22 then-current development
  patches and compact-IR capability was activated as
  `gcsim-v2.42.2-gob8-20260830b`. GOB-9 subsequently replaced that numbered
  reconstruction stack with one equivalent adapter patch and a new active
  engine while retaining this build as rollback evidence.
- 33 focused Python/UI checks, all Go package tests and `go vet` pass.
- Two no-development-cache product attempts used 483 real artifacts and the
  current four fixed set packages; neither is accepted. The first ran under
  concurrent game load and timed out. On the one permitted idle-CPU repeat,
  search normalized to 67.22 s and n=128 to 42.53 s, but the run produced the
  legal maximum of seven n=1000 finalists. Fixed 3x5 scheduling completed six
  in two ~30 s waves, then Current alone started a third wave and the unchanged
  boundary stopped it at 190.108 s. The six completed finalists already include
  a 148772.66 DPS leader; Current was last at n=128 with 143881.31 DPS, but the
  accepted contract correctly did not skip it. Current first loss is therefore
  `fixed_3x5_requires_three_n1000_waves_for_seven_finalists`, not formula search,
  UI, engine binding or CPU contention.
- Accepted scheduler correction is now implemented: the complete immutable
  finalist list is partitioned dynamically by the 16-thread CPU budget. Seven
  rows become 4 processes x 4 workers followed by 3 x 5; no candidate, n=1000
  iteration or candidate count changes.
- The next real UI attempt first exposed a compact-panel contract bug: seed
  members can differ by one engine tick (`67017` versus `66950` ms). Requiring
  one shared duration was incorrect. Go now calculates every member and actor
  DPS with that member's own duration and only then averages; the exact failed
  request/compact pair passes the indexed-panel audit.
- After rebuilding and restarting the application, the actual AppShell
  `Selected Sets` button completed. It returned `148910.0985153193` DPS,
  standard error `68.49373581920122`, formula estimate
  `149192.89468716306`, residual `-282.79617184377275` and twenty unique IDs.
  Debug run:
  `data/gcsim/optimizer-go-runs/selected-20260831-045553-7307ce20`.
- The process progress completed at about `191.152` seconds and the Go receipt
  reports `188.407` seconds internally. Therefore the button is functionally
  accepted, but the full UI path is not falsely labelled below 190 seconds.
  The working kill boundary is temporarily 360 seconds; 190 remains the
  optimization target rather than a reason to show another false failure.
- Pure duration/scheduler regressions, all Go tests, `go vet`, focused
  Python/UI checks and AppShell checks pass. No further full product run is
  required before the isolated GOB-8P n=500 replay.
- Post-acceptance result UX now shows a live `Running for` timer with an honest
  3–8 minute CPU-dependent estimate, retains the elapsed time after completion,
  and renders the returned twenty IDs as four compact character rows in
  Flower/Plume/Sands/Goblet/Circlet order. Cards reuse the account artifact
  icons, existing stat badges and bundled element icons only. Each row's Save
  action asks for a name and calls the same `save_build_preset` service used by
  Artifact Browser; it does not equip artifacts or introduce separate storage.
- The product result now carries the already-measured finalists in measured-DPS
  order as an additive v1 field. Fixed left/right arrow positions page Top-1,
  Top-2 and later builds; old v1 results without this field remain readable as
  a one-page winner result. Paging adds no engine work and reads no debug file.

### GOB-8C — clean repository checkpoint before performance work

PASS 2026-08-31. The startup empty-window fix was integrated and its regression
proved that AppShell is the only visible top-level widget during startup. New Go
sources, fixtures, UI and retained experiment tools were classified as project
files; the optimizer executable and generated run directories remain ignored.
The already-approved legacy deletions are retained. No user-specific absolute
paths, credentials or heavyweight run outputs are versioned. Focused optimizer
checks, all Go tests/`go vet`, and the full 182-test AppShell module pass without
another GCSIM run. This is a repository checkpoint, not the final GOB-9 engine
patch/update cleanup.

### GOB-8P — bounded performance rationalization

Do not begin with another search rewrite or parameter sweep. First account for
the repeated 3:33 and 3:40 product runs by formula search, n=128 screening,
n=1000 final verification and fixed process overhead. The n=128 stage cannot simply be
deleted: it receives 25 rows (Current plus 24 formula finalists), and in the
latest real run the final winner was formula rank 20 before n=128 promoted it.
Calling those seven rows "already selected" before n=128 is therefore wrong.

The one permitted real experiment replayed the exact seven saved finalists at
n=500 without compact capture, formula search or n=128. It preserved the same
winner as saved n=1000 and all five useful top rows. The winner gap was 836.86
DPS against 130.24 combined standard error (6.43 sigma). Close runner-up order
did move, so n=500 is a winner-selection gate and not proof of exact total
ordering. Final verification fell from 92.54 to 46.36 seconds; substituting
that measured stage into the latest run projects the Go boundary from 207.70
to 161.52 seconds, before UI/process overhead.

Production now keeps the recall-critical common n=128 screen, then runs all at
most seven finalists at n=500. If the leader is more than three combined
standard errors above every contender, it finishes. If two to four candidates
remain unresolved, only that group is rerun at n=1000 and replaces its n=500
evidence. If more than four remain unresolved, the bounded path does not launch
an expensive broad extension; it returns the n=500 panel with explicit overlap
warnings and lets the UI expose the alternatives. The isolated receipt is
`tests/fixtures/gcsim_optimizer_go_v1/gob8p_exact_seven_n500_receipt_v1.json`.
The subsequent single full Go product acceptance kept 24 formula finalists,
screened Current plus those 24 at common n=128, then resolved all seven final
candidates at n=500 without extension. It returned the same known winner at
148907.66 DPS (SE 92.03), improved the same-context Current by 3.56%, and took
159.06 seconds inside the Go boundary: search 66.77 s, screen 48.63 s, final
43.18 s. Its compact receipt is
`tests/fixtures/gcsim_optimizer_go_v1/gob8p_adaptive_acceptance_receipt_v1.json`.
The UI binding was not changed and already has its own accepted end-to-end path;
a user smoke click is useful but is not another development simulation gate.
The one-off replay command was removed after the compact receipt was frozen, so
it does not remain as a second product path. Do not repeat either GOB-8P run or
start a parameter sweep.

### GOB-9 — PASS, final area cleanup

The accepted product boundary is now unambiguous:

- AppShell calls `optimizer_go_selected.py`; narrow request/materialization
  preparation lives in `optimizer_go_selected_inputs.py`; one standalone Go
  optimizer owns formula evaluation, search and staged verification;
- a clean import of Selected loads no `trace_equation` or deleted legacy
  response/search module;
- the second reachability slice removed 13 obsolete Python optimizer/trace
  modules, 12 orphaned tests, 12 obsolete audit tools and eight stale manifests;
- Current/farming remain deliberately retained. Continuous target and the
  smallest supporting trace math remain isolated reference material for a
  future All Sets/Theory Go port and are not Selected runtime;
- all 22 numbered engine patch fragments were replaced by the single
  `0001-gtt-engine-adapter-v1.patch` (SHA-256
  `01ff5993aaf6c3726db30de0b6876c55401b5a3e66e1df979bee24e7c8245638`).
  Fresh `git apply --check`, application and normalized 4,314-file tree
  comparison prove equivalence to the accepted source tree;
- transactional update built and activated
  `gcsim-v2.42.2-gob9-consolidated-20260831`. The source-manifest body SHA-256
  is `f898a307beb59f9fe556fa7acdfa976d2e1c293979a3013dde4e0412353c7e7f`;
  the executable SHA-256 is
  `bce061db71f2ebc7171ba19d192a6c0522358edb68e821b25a7649406f86fe03`;
- switching back to `gcsim-v2.42.2-gob8-20260830b` and restoring the new engine
  both passed. Ordinary n=1 simulation and one real compact seed handshake
  passed; no full optimizer, n=500 or n=1000 acceptance run was repeated;
- valid cached upstream archives are now reused, and truncated downloads fail
  cleanly instead of leaving a misleading update state;
- 42 focused update/patch/input tests, 638 GCSIM tests, 189 combined optimizer/
  AppShell UI tests, all Go tests and `go vet` pass.

### GOB-10 — PASS, compute optimization without search weakening

The complete candidate set, common n=128 screen and adaptive finalist policy
are unchanged. Formula evaluation now precomputes constant nodes and evaluates
the full dependency closure for only the wearer whose artifact vector changed;
cross-character support dependencies remain included. A production-sized
regression returned a result exactly equal to the accepted saved search.

Ordinary finalist stages verify the engine executable once before and once
after the stage. The consolidated engine patch skips trace-only bookkeeping
when trace is disabled, while trace capture preserves the same compiled search
result. The two fixed compact seeds are captured concurrently and restored to
canonical order; cancellation owns both processes.

One authorized full saved-account replay returned the same accepted twenty IDs.
Measured timings: compact capture 1.83 s; compile 0.47 s; formula search 13.27 s;
25-row n=128 screen 18.15 s; seven-row adaptive n=500 final 19.65 s; complete
post-preparation boundary 57.0 s. The winner measured 148874.50 DPS with SE
92.61; ordinary stochastic variation explains the DPS difference from earlier
runs. No n=1000 extension was needed. Adding the separately measured unchanged
UI preparation predicts about 62-64 seconds end to end.

The active build is `gcsim-v2.42.2-gob10-perf-20260901`, artifact SHA-256
`00834023d64f3853723ee2ca28af6b9bd5fbaacb1cbda4cf7e11dd44a45ff99a`.
The optimized consolidated patch SHA-256 is
`dc4d99a243d957afb4c7dee64e7fef6ba22b7a030cbcf36f9f0242960fe09aef`.
Transactional update against upstream v2.45.0 currently fails closed during
patch check and leaves the working engine untouched. Adapting and semantically
validating the single patch against v2.45.0 is the next engine-maintenance task;
it must not be mixed with another search redesign.

Generated GOB-9 staging/handshake copies and the ordinary smoke output are
rebuildable ignored local residue and have no product owner; the current host
blocked their final recursive deletion after their exact paths were verified.
Continuous target is removed only after
an accepted Theory/All Sets Go port. Current comparison is removed only after
Selected, All Sets and Theory are accepted or explicitly abandoned.

## 8. Engine update safety

Before cutover, inspect every patch present at that time. Remove obsolete experiments and consolidate required engine changes into one versioned adapter patch. Never hard-code a historical patch-number range.

Update sequence:

1. acquire pristine upstream source in staging;
2. verify upstream identity;
3. check and apply the consolidated patch;
4. generate source/patch manifest;
5. build;
6. run capability, compact-IR, ordinary simulation and optimizer handshake smokes;
7. activate atomically only on full PASS;
8. otherwise keep the previous working engine and failed diagnostics.

Safe update means fail closed plus rollback. It does not mean upstream can never require an adapter update.

## 9. Retain / delete disposition

Retain now:

- engine store/update/rollback and source-manifest primitives;
- artifact DB read/materialization contracts needed to produce the Go request;
- the frozen Python migration-leader JSON as a small permanent parity receipt;
- smallest parity fixtures;
- Current comparison backend;
- continuous target as FUTURE_GO_PORT_FOR_THEORY_ALL_SETS.

Deleted at GOB-6 after proof: Python FGBS/stochastic/Selected composition,
CF-BB, Adaptive Oracle Exchange, Contextual Scan, neutral assignment oracle and
their orphaned strategy tests/tools/handoffs.

Deleted at GOB-9 after product cutover:

- every remaining old Selected response/oracle/search approach with no accepted caller;
- redundant numbered patch fragments and their orphaned development orchestration;
- stale manifests, tests, audit tools and generated development residue.

Whenever implementation work reveals another unused component, add it immediately to the cleanup manifest with a deletion gate. Do not preserve code merely because it once produced evidence.

## 10. Permanent execution rules

- Work sequentially without subagents or parallel agents.
- Do not brute-force parameters or repeat expensive runs without a declared gate.
- Stop after three substantive failed approaches to one blocker.
- Ordinary technical errors are fixed without pretending they are conceptual.
- No full-account or n=1000 run before its reduced/parity gate.
- Unknown behavior degrades safely; no legacy fallback.
- Preserve unrelated dirty-tree work.
- Do not commit/push unless requested.
- Update this handoff, Go design, TODO, CODEX and cleanup manifest when ownership or roadmap changes.
