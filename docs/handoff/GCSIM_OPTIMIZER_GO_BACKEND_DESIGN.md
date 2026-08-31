# GCSIM Optimizer Go Backend — authoritative redesign

Status: GOB-3 through GOB-8 functional PASS. The real Selected button completed
end to end on 2026-08-31. Repeated user runs of 3:33 and 3:40 confirm that no
performance optimization has happened yet and the product target remains
missed. The clean repository checkpoint is complete; bounded GOB-8P work is
next, then final GOB-9 cleanup.

This document owns the clean rewrite of the active Selected optimizer backend
in Go. It is not a line-by-line port of the Python implementation. Python FGBS
and stochastic expectation were temporary executable references and were
removed after the explicit GOB-6 parity/cleanup gate.

## 1. Goal

Build one production-oriented local optimizer which:

- receives one compact immutable account/team/rotation request;
- obtains compact formula evidence from the bound GTT-GCSIM engine;
- searches legal physical artifact assignments in Go;
- sends a bounded finalist set to the same engine at common n=1000 fidelity;
- returns measured DPS and the exact twenty artifact IDs;
- finishes cold Selected within 190 seconds;
- remains safe to update when upstream GCSIM changes;
- never falls back silently to a legacy optimizer or guesses through an unknown
  mechanic.

The Python work proved the method's useful principles, not a production
implementation to preserve. The Go rewrite may change data layout, traversal,
caching, batching and budgets while retaining the accepted correctness rules.

## 2. Architectural decision: separate Go optimizer + minimal engine adapter

The optimizer is a separate Go module/binary owned by GenshinTeamsTracker. It
must not import `gcsim/internal/...` packages and must not be copied into the
upstream engine patch. Proposed repository boundary:

```text
native/gcsim_optimizer/
  cmd/gtt-optimizer/
  internal/contracts/
  internal/engineclient/
  internal/formula/
  internal/artifacts/
  internal/search/fgbs/
  internal/finalists/
  internal/audit/
```

GCSIM retains a small GTT adapter patch because ordinary GCSIM output does not
expose all executed formula lineage, state/support dependencies and typed
unknown boundaries. The adapter owns only:

1. narrow runtime hooks needed to observe the executed rotation;
2. conversion from GCSIM internals into a versioned engine-neutral compact IR;
3. capability/source/context identities;
4. the existing ordinary simulation entry needed for the common-fidelity
   finalist n=1000 run.

The adapter does **not** own artifact enumeration, FGBS, candidate ranking,
cache policy, finalist selection or UI behavior. Any reference to upstream
GCSIM types is confined to this adapter surface. The standalone optimizer reads
only the stable GTT IR contract.

This split is intentional:

- a fully external parser cannot recover data the engine never emits;
- putting the whole optimizer in the engine patch would couple every search
  change to upstream GCSIM updates;
- the hybrid keeps unavoidable upstream coupling narrow and keeps the evolving
  optimizer independently testable.

## 3. Process boundary and data transfer

There is one request file and one result stream/file per attempt. Python never
calls Go once per artifact or candidate.

### 3.1 Python -> Go request

The UI/application materializes one canonical request containing:

- request/schema identity;
- active engine binary, engine binding and source/patch manifest identities;
- exact prepared config/rotation/target text and hashes;
- four character keys, weapons and fixed Selected set packages;
- current twenty-artifact assignment;
- every eligible account artifact as `artifact_id`, slot, set UID, rarity/level
  and normalized raw main/sub-stat numbers;
- Selected legality policy: fixed 4p, at most one off-set item per wearer,
  twenty globally unique physical IDs and 5-star-only default;
- predeclared stochastic seed policy and product/development time budgets;
- final n=1000 fidelity and bounded finalist policy identity once FGBS-8 freezes
  that policy.

JSON is acceptable for this boundary: a few hundred compact artifact rows are
small compared with the current 69–71 MB trace files. A binary codec is allowed
later only if measurement proves this single transfer material. Go does not read
the application SQLite database in v1; this avoids duplicating DB schema and a
Windows SQLite/CGO dependency. Input canonicalization and hashes prevent silent
translation drift.

### 3.2 Go -> Python progress/result

Go emits bounded newline-delimited progress records and one final result:

- current stage and completed/total work where knowable;
- elapsed time, cancellation status and cache identities;
- FAST finalists with formula estimate and uncertainty;
- for the winner: exact twenty IDs grouped by wearer/slot;
- measured n=1000 DPS, standard error and engine result identity;
- formula residual versus measured DPS;
- degraded/unknown mechanic warnings;
- deterministic debug receipt/archive path.

Python only starts/cancels the process, renders progress and displays/saves the
result. Search and simulation results never cross the boundary as live Python
objects.

## 4. Compact engine-neutral formula IR

The new adapter output is not a raw debug trace. For each frozen seed member it
contains only information consumed by the optimizer:

- duration and seed identity;
- response-equivalent normal-damage channels, kept distinct by generic attack
  tag, raw damage type and response coordinates;
- owned reaction channels and their stat dependencies;
- ordered support/state/heal/drain dependencies that can reach terminal damage;
- base values, coefficients, caps/guards and artifact-controlled leaves;
- typed opaque/frozen boundaries plus their baseline damage share;
- actor attribution and enough identity to reproduce diagnostics;
- no unrelated source occurrences, energy-only wrappers or debug event history.

The adapter may stream one compact seed member at a time. The Go optimizer
validates and compiles it immediately, then releases transport buffers. A fixed
seed panel is aggregated with equal weights; no favorable seed is selected.
Members are allowed to have different engine durations. Every member's total
and actor DPS is calculated using its own duration before equal-weight
aggregation; a shared-duration equality check is invalid for stochastic runs.
One-trace mode is allowed only with an explicit topology-stability certificate.

Unknown mechanics freeze at the last understood boundary. Known formula regions
continue to work. Material unknown share widens finalist retention and creates a
debug receipt; it never becomes zero, a hard prune, or a crash.

## 5. Clean Go mathematical representation

The rewrite is data-oriented rather than object-oriented:

- character and stat names are converted once into small integer indexes;
- artifact stats are dense fixed-width numeric arrays;
- artifact IDs, slots, set membership and occupancy use indexed arrays/bitsets;
- formula channels compile once into immutable numeric operations;
- candidate evaluation reuses preallocated scratch buffers;
- support coordinates use compact dependency slices and bounded caches;
- stochastic members are aggregated inside one evaluator rather than retaining
  multiple Python object trees;
- hashes/provenance remain outside hot arithmetic loops;
- no `Decimal`, dictionary lookup or dataclass creation per search state.

The rewrite must preserve expected critical damage with CR capped at 100%, raw
artifact-variable rebasing, reaction EM curves, support dependencies, fixed
sets, off-set legality and physical-ID conflicts. It must not hard-code a
character, set, element or reaction name in generic evaluation/search logic.

## 6. Go FGBS: principles retained, implementation reconsidered

The active method remains Formula-Guided Build Search, but old Python control
flow and frontier widths are evidence, not source code or immutable constants.

Required principles:

1. evaluate complete five-piece wearer builds, never permanently delete an item
   because it looks weak alone;
2. use the formula response ledger to order/retain materially different direct,
   reaction and support continuations;
3. preserve the incumbent and all typed-unknown lanes;
4. certify saturation only from complete bounds; otherwise report uncertainty;
5. rebuild wearers against the current complete team anchor;
6. iterate dependency cycles to bounded stability;
7. test formula-linked or physically contested simultaneous changes and off-set
   transfer;
8. keep wider unresolved provider components visible rather than calling pair
   refinement complete;
9. send only a bounded retained set to common-fidelity GCSIM;
10. never claim a global optimum from a bounded frontier.

Go-specific opportunities that must be assessed with reduced exact controls:

- precompute every artifact/wearer stat vector once;
- group slot candidates by response signature without deleting physical backups;
- reuse partial sums and occupancy bitsets;
- use bounded heaps/arrays instead of allocating search-state objects;
- compile formula operations and stochastic weights once;
- batch direct guide evaluation over contiguous candidate arrays;
- choose widths from recall/runtime evidence in Go, not copy 32->8 blindly.

Language speed does not authorize larger hidden truncation or weaker quality.

## 7. Implementation and acceptance stages

### GOB-0 — contract/design freeze

- accept this document as the sole Go-backend design;
- freeze Python product development at the current FGBS-7 protocol checkpoint;
- Python may receive only reference tests, diagnostic export fixes and cleanup
  changes needed for Go parity;
- no UI cutover, old-code deletion or normal full-account rerun.

Acceptance: documents agree on ownership, boundaries and cleanup order.

### GOB-1 — isolated Go module and cross-language contract — PASS 2026-08-30

- create the standalone module and command;
- define canonical request, progress, compact-IR and result schemas;
- implement strict validation, hashing, cancellation and deterministic ordering;
- use small synthetic fixtures shared by Python and Go;
- do not import GCSIM internals or implement search yet.

Acceptance: malformed/unknown schema fails closed; valid round-trip is byte/
semantic deterministic; clean build uses the configured bundled Go toolchain.

Accepted receipt:

- standalone standard-library-only module: `native/gcsim_optimizer`;
- GOB-1 accepted a validation-only command boundary; later accepted stages add
  aggregation, indexed audit and FGBS subcommands without changing v1 identity;
- strict v1 request/progress/compact-IR/result structs and validators;
- canonical gameplay decimals are strings, preventing Python/Go float identity
  drift before Go parses them into later numeric arrays;
- canonical object ordering, source/config/context hashes, request/IR/result
  identity links and process-interrupt cancellation are pinned;
- shared fixtures under `tests/fixtures/gcsim_optimizer_go_v1/` cover four
  wearers, twenty unique physical artifact IDs, two seed members, typed opaque
  evidence, progress, measured result and canonical hashes;
- canonical request identity:
  `d2a0c68aa8736d270d9ac72a0fadea050ed20fb4dd9e3fb64579ed142971cfa6`;
- 10 focused Go tests and 4 Python cross-language tests pass;
- `go vet`, local Go 1.26.4 build and dependency/isolation scans pass;
- GCSIM/engine/search/UI calls and behavior: 0.

### GOB-2 — compact adapter feasibility slice — PASS 2026-08-30

- specify the smallest upstream hook surface needed by current executed traces;
- emit compact direct/reaction/support/unknown evidence for one seed;
- prove equivalence to the accepted Python-compiled formula on a synthetic
  trace and one frozen current-context seed trace;
- measure output size, adapter runtime and peak memory before adding a panel.

Acceptance: formula/candidate parity within numerical tolerance, no missing
material path, and a material reduction from 69–71 MB raw trace. If this fails,
stop before implementing FGBS and discuss the missing information.

Accepted receipt:

- ordered engine patch `0022-gtt-compact-equation-v1.patch` adds the opt-in
  `compact_ir_v1` output seam; omitted output mode preserves the raw trace path;
- the engine emits only engine-neutral formula nodes, damage channels and typed
  opaque boundaries. Search, artifact enumeration and UI remain outside GCSIM;
- synthetic coverage includes direct damage, reaction damage, a support HP
  dependency and an unsupported path that stays explicitly opaque;
- frozen seed `742031889` compiled 365 hits through 9,063 relevant ancestor
  events into 42,242 nodes and 365 channels;
- Go baseline damage `9460439.540199643` and Bennett HP% candidate damage
  `9458684.571997381` match the accepted Python values within `1e-6`; the
  candidate delta matches at the same tolerance;
- compact output is 4,548,636 bytes versus 69,085,424 raw bytes: 15.19x smaller
  (about 93.4% removed);
- adapter work measured about 117.5 ms; the complete frozen-seed command took
  1.781 s and peaked at about 145 MB process working set;
- 25 encountered opaque reason classes remain typed and visible rather than
  being silently discarded. Their current full-baseline exposure values are
  conservative overlapping warnings, not 25 additive damage chunks;
- two development engine executions used the same frozen seed: the first proved
  the seam and the second added final audit/opaque accounting. No stochastic
  aggregation, artifact search, finalist simulation, n=1000 or UI was run;
- the permanent patch applies after patches 0001–0021 in a fresh source copy,
  and focused patched-engine, standalone-Go and cross-language receipt tests pass.

### GOB-3 — stochastic expectation in Go — PASS

- compile a predeclared bounded seed panel sequentially/streamingly;
- equal-weight damage, actor contribution and uncertainty;
- de-duplicate opaque reasons per member and never sum overlapping conservative
  full-baseline exposure warnings as if they were separate damage;
- retain explicit sample count/dispersion and stable-one-trace proof boundary;
- never choose a lucky seed or widen the frozen tolerance.

Acceptance: exact parity with the Python two-seed protocol fixture, bounded
memory independent of raw trace size, and a measured preparation budget that
leaves room under 190 seconds.

#### GOB-3A — frozen aggregation contract — PASS 2026-08-30

GOB-3A changes no engine behavior and implements no aggregator. It freezes the
following rules for GOB-3B through GOB-3F.

Panel and identity:

- the aggregator accepts the request's sorted unique seed panel generically and
  must never hard-code character, rotation or seed identities;
- the real development parity request is exactly the adjacent seeds
  `742031889`, `742031890`, each with weight `1/2`; synthetic fixtures may use
  other declared seeds to test the same generic rules;
- this pair is a compatibility/runtime checkpoint, not the accepted future
  product panel size or convergence rule;
- every requested seed must occur exactly once; missing, duplicate, additional
  or reordered members fail closed rather than being selected or reweighted;
- request, engine binding, context, incumbent artifact vector, character domain
  and duration must be identical across members;
- topology hashes may differ and are expected to differ. Different schedules
  are averaged; they are not grounds for choosing the better seed;
- a one-member panel is not authoritative without a separate explicit topology
  stability proof hash. No such proof is claimed by GOB-3A.

Formula meaning and baseline invariant:

- every `artifact_stat` leaf is a signed delta from the incumbent artifact stat
  vector, not an absolute stat value;
- a missing candidate coordinate therefore means zero delta;
- evaluating each member at the all-zero delta vector must reproduce the sum
  of its channel `baseline_damage` values within absolute `1e-6`;
- non-finite arithmetic, unsupported operations, invalid node order or a
  baseline mismatch fail the panel before aggregation;
- an actor absent from one seed contributes zero for that seed rather than
  changing the denominator.

Arithmetic for `N` members:

- evaluate every member independently to `D_s(x)` damage, per-actor damage and
  `DPS_s(x) = D_s(x) / duration_seconds`;
- aggregate damage, DPS, candidate-minus-incumbent delta and each actor's
  contribution by the equal arithmetic mean over all declared seeds;
- compute candidate sample standard deviation with Bessel's correction,
  `sqrt(sum((D_s - mean_D)^2) / (N - 1))` for `N > 1`;
- standard error is `sample_sd / sqrt(N)`; one proven-stable member reports
  zero dispersion without pretending that zero is empirical convergence;
- Go must traverse seeds in canonical order and use deterministic compensated
  summation. It may not widen the accepted `1e-6` absolute parity tolerance;
- damage dispersion is the Python parity quantity. DPS dispersion is derived
  from the same member DPS values and must also remain visible in the receipt.

Opaque and uncertainty rules:

- keep a sorted union of reason codes plus the exact member seeds in which each
  reason occurred;
- absence in another seed does not cancel an uncertainty;
- overlapping full-baseline exposure warnings are presence/coverage metadata,
  never additive damage and never stochastic weights;
- known baseline damage remains in the member formula while an unknown response
  stays frozen at that member's observed boundary;
- GOB-3 aggregation has no hard-prune, global-optimum or product-result
  authority. It only produces a formula guide and an explicit uncertainty
  receipt for later gates.

Frozen parity landmarks:

- member DPS: `141306.04242269805`, `144641.0275931734`;
- equal-weight DPS: `142973.53500793572`;
- DPS sample SD: `2358.190629199696`;
- DPS standard error: `1667.4925852376762`;
- per-member, mean, delta, actor, dispersion and standard-error comparisons use
  absolute tolerance `1e-6` against the frozen Python oracle;
- `143738.2939` n=1000 DPS remains an external comparison only, not an input or
  correction factor for formula aggregation.

#### GOB-3B — synthetic Go aggregator — PASS 2026-08-30

- `internal/stochastic` evaluates every request-owned seed member once and
  combines damage, DPS and actor contribution with equal weight in canonical
  seed order;
- it reports candidate sample SD/SE and reason-to-seed opaque coverage without
  adding overlapping opaque exposure values as damage;
- request, engine, context, seed order/count, duration, actor domain and the
  zero-delta baseline invariant fail closed on mismatch;
- differing topology hashes are accepted and averaged rather than selected;
- reordered, duplicate, missing and incompatible members plus non-finite
  artifact deltas are covered by focused tests;
- all standalone Go tests and `go vet` pass. Engine/search/n=1000/UI calls: 0.

#### GOB-3C — exact isolated staging engine — PASS 2026-08-30

- a separate source tree was built from upstream `v2.42.2` plus the complete
  ordered patch identity 0001-0022; patched tree SHA-256 is
  `b4feb9cc908ac20b00b753fadefffb809951448da2be68f494588fb06b08d2a9`;
- source-manifest identity is
  `b3c8b25eeaee4ca7b80f8f422f66703936bc95fb8a379a993d89a08799559977`,
  patch-stack identity is
  `fd63f04802d97a2ae49a3546a3039736b1794426f4b064d53327da45a24ccf6a`;
- staging executable SHA-256 is
  `4fcfcc4cea8642c10b2610224427ef141356d81ad6a0c958754c5bcf88d0f537`
  and it reports `gtt-compact-equation-v1` plus `gtt_compact_equation_v1`;
- historical patch 0016 required whitespace-tolerant application in the copied
  Windows tree. The resulting tree matched the independently validated
  0001-0022 reference tree exactly; updater normalization remains a later
  update-path acceptance item;
- the active application engine remained
  `gcsim-v2.42.2-20260729070641`.

#### GOB-3D — two real compact members — PASS 2026-08-30

- the same staging executable and config captured seeds `742031889` then
  `742031890`, each at n=1/workers=1 and compact output only;
- seed 742031889: 365 channels, 42,242 nodes, 4,548,636 bytes, 1.576 s,
  baseline DPS `141306.04242269817`;
- seed 742031890: 389 channels, 43,927 nodes, 4,729,609 bytes, 1.569 s,
  baseline DPS `144641.0275931735`;
- topology hashes differ, as expected. Both members pass strict Go decoding and
  reproduce their declared channel baseline at zero artifact delta;
- receipt:
  `tests/fixtures/gcsim_optimizer_go_v1/gob3d_two_seed_capture_receipt_v1.json`;
- engine executions: 2. Search/n=1000/UI: 0. Real-panel aggregation was
  deliberately not performed before GOB-3E.

#### GOB-3E/GOB-3F — real panel parity and runtime — PASS 2026-08-30

- canonical real request contains 483 eligible artifacts and binds both frozen
  compact members without another engine run;
- Go matches Python member/mean/actor/SD/SE and all 25 uncertainty classes
  within absolute `1e-6`; aggregate mean is `142973.53500793583` DPS;
- cold decode/validation of the 9.28 MB panel was about 2.10 s and repeated
  uncompiled evaluation about 857 ms each. This proved that validation and
  string parsing must remain outside candidate arithmetic;
- receipts: `gob3e_real_panel_parity_receipt_v1.json` and
  `gob3f_runtime_receipt_v1.json`; engine/search/n=1000/UI calls: 0.

### GOB-4 — artifact domain and formula evaluator

- ingest the real compact artifact snapshot;
- precompute indexed stat vectors, legality and incumbent identity;
- implement direct/reaction/support FAST candidate evaluation and caches;
- compare incumbent, broad stat profiles and a real single-swap corpus with the
  Python reference.

Acceptance: same legal vectors and numerical scores within frozen tolerance;
twenty IDs remain globally unique; engine calls during candidate arithmetic 0.

Status: PASS. The compiled/indexed Go evaluator owns 483 artifacts, 37
coordinates, exact Selected fixed-4p plus one-offpiece legality and global ID
uniqueness. Incumbent, a broad stat profile and 20 real legal swaps match the
independent Python reduction within `1e-6`. Receipt:
`gob4_indexed_evaluator_receipt_v1.json`.

### GOB-5 — clean Go FGBS through current Python capability

- implement response ledger, bounded complete wearer search, dynamic anchors,
  cyclic recheck and dependency/conflict pair refinement;
- run reduced exhaustive synergy/CR-cap/support/off-set/occupied-ID controls;
- run the current account under the same compact objective;
- report all raw/expanded/retained/discarded/budget counts.

Acceptance: reduced exact leader/recall gates pass; the Python incumbent and
accepted leader are retained, and a different Go leader is allowed only if its
score is no worse under the same objective. Cold search must have meaningful
margin below 190 seconds before proceeding.

Status: PASS. The real search completed in 64.39 s, retained the frozen Python
leader at finalist rank 24, and found `148135.03384471865` formula DPS versus
`148017.35836796626` for that migration leader on the same two-member panel.
It returns 24 bounded finalists, exposes every search/discard/budget count,
preserves the Bennett/Furina cross-actor response edges, and refuses saturation
freeze while 25 opaque reason classes remain. Engine/n=1000/UI calls: 0.
Receipt: `gob5_real_account_acceptance_receipt_v1.json`.

### GOB-6 — mandatory Python optimizer cleanup gate

After GOB-5 passes, stop feature work and perform a fresh import/call-graph/test
scan. Then delete the replaced Python product implementation, including:

- active Python FGBS package and its product-only audits;
- Python stochastic expectation and Selected scoring paths replaced by Go;
- superseded CF-BB, Adaptive Oracle Exchange and Contextual Scan strategies;
- orphaned Python formula/search helpers, fixtures and handoffs with no retained
  patch/update/reference role.

Do not delete the remaining Current comparison backend yet. Preserve only the
smallest cross-language parity fixtures required to validate Go and engine
updates. Cleanup must leave one Selected product backend, not a hidden fallback.

Acceptance: clean-cache tests/build, no imports/references to deleted strategies,
Go backend still reproduces GOB-5 receipts.

Status: PASS. The fresh scan found no product/UI callers. Replaced Python
Selected code, superseded strategies, neutral oracle and orphaned tests/tools/
handoffs were removed. Continuous-target Theory mathematics remains isolated;
the Go backend and GOB-5 receipt remain reproducible.

### GOB-7 — continue FGBS-7/FGBS-8 in Go only

- determine the bounded product seed panel/convergence rule;
- rerun unchanged same-context FAST-vs-n1000 baseline and controlled
  replacements;
- freeze finalist K from recall/runtime evidence;
- simulate all finalists at common n=1000 and select measured best DPS.

Acceptance: no tolerance widening, no seed selection, cold Selected <190 s,
exact returned artifact IDs, measured DPS/SE and residual recorded.

Status: PASS. Formula rank was proven insufficient for early truncation because
the retained migration leader ranked 24th by formula and won common n=1000.
The accepted rule therefore screens the 24 formula rows plus Current at common
n=128, retains the measured top five plus mandatory formula leader and Current
(at most seven unique builds), then runs only that bounded set at common n=1000.
The clean accepted run used 25 n=128 and 6 n=1000 processes, completed in
170.665 s, and returned 148744.2304 DPS (SE 68.3218) versus Current
143721.6620 DPS. Winner formula residual was +726.872 DPS. Exact twenty IDs and
engine/config/result identities are frozen in the GOB-7 receipt.
The top two measured candidates overlap within their combined standard error;
the strict product result therefore carries `measured_top_confidence_overlap`
while still returning the highest observed mean as the winner.

### GOB-8 — UI and clean-new-user acceptance

- connect one Selected button to the Go process boundary;
- progress, cancellation, warnings and debug receipt;
- render IDs/builds and final engine n=1000 DPS;
- prove cold use with no development cache and rollback-safe engine selection.

Implementation and functional acceptance PASS. Dynamic two-wave scheduling
keeps every finalist and uses 4 processes x 4 workers followed by 3 x 5 on a
16-thread machine. The next real attempt exposed and fixed an invalid shared
duration assumption in the compact seed panel: each member now uses its own
duration before mean aggregation. The exact failed UI payload passes the cheap
audit. A restarted real AppShell then completed the actual Selected button with
148910.0985 measured DPS, SE 68.4937 and twenty unique IDs. Progress completed
at about 191.152 seconds; the Go receipt reports 188.407 seconds internally.
Thus functionality is accepted and the 190-second full-UI performance target
is still narrowly missed. The temporary working UI kill is 360 seconds.

The accepted result surface also owns a live elapsed timer and a CPU-dependent
3–8 minute estimate. A successful result is materialized from the returned IDs
and the existing account artifact rows into four compact 5-piece rows. Artifact
and element imagery is reused from existing project assets without generated or
downloaded replacements. Per-character Save prompts for a preset name and
delegates to Artifact Browser's existing `save_build_preset` service; it never
auto-equips the result and owns no second persistence path.

All measured final candidates are returned in measured-DPS order through an
additive result-v1 `candidates` field. Each row contains exact twenty IDs and
its measured result, so UI paging never reads the debug receipt or starts more
simulation. Payloads created before this additive field render as one page.

The next stage is GOB-8P, a bounded performance audit before final GOB-9
completion. Repeated unchanged user runs finished in 3:33 and 3:40; that spread
is treated as ordinary host-load noise, not an optimization result. The latest
real winner was formula rank 20 among the 25 n=128 inputs, so replacing n=128
with formula top-7 is contradicted by saved evidence. The first experiment is
limited to replaying the exact saved seven finalists at n=500 and comparing them
with existing n=1000 evidence; no broad iteration sweep or full optimizer rerun
is part of that experiment.

### GOB-9 — mandatory final workspace cleanup

After Selected UI acceptance, stop feature work and clean the entire optimizer
area, not only the main Python package. Run fresh import/call-graph, test/tool,
documentation and patch reachability scans, then remove every implementation,
adapter and experiment no longer used by the accepted Go product path.

The audit must explicitly cover:

- Python FGBS/stochastic/formula/search leftovers missed by GOB-6;
- CF-BB, Adaptive Oracle Exchange, Contextual Scan, Selected V2/M/S/Gate-era
  orchestration and neutral assignment-oracle code if no accepted caller remains;
- old optimizer UI buttons, factories, progress event types and backend wiring;
- experimental harnesses, saved-report readers and fixtures with no retained
  parity/update role;
- obsolete engine instrumentation and numbered patch deltas replaced by the
  consolidated adapter patch;
- stale handoffs/TODO entries and duplicate contracts;
- generated debug/cache/temp artifacts through the bounded cleanup mechanism.

Continuous target is removed only after its accepted Theory/All Sets Go port,
not merely because Selected is complete. The remaining Current comparison
backend is removed when Selected, All Sets and Theory are accepted and the user
has tried their replacements, as already required by the cutover contract.

Acceptance: one reachable Selected backend, one consolidated active engine
patch, no imports/references to deleted implementations, clean-cache build/tests,
patch-update plus rollback proof, and a fresh new-user Selected smoke. GOB-9 is
part of completion, not an optional maintenance suggestion.

## 8. Engine update and patch safety

"Safe update" means fail-closed update plus rollback, not a promise that every
future upstream refactor applies automatically.

Before cutover, audit **all** patches present then, remove obsolete optimizer
experiments and produce one consolidated versioned GTT adapter patch. The patch
should add most code under GTT-owned packages and touch upstream files only at
named narrow seams. The source/patch/capability manifest binds the exact build.

Transactional update sequence:

1. acquire pristine official source into staging;
2. verify supported upstream identity;
3. run `git apply --check` for the consolidated patch;
4. apply and generate the source manifest;
5. build engine and adapter capabilities;
6. run Go package tests, compact-IR fixture, ordinary simulation smoke and
   optimizer handshake;
7. activate atomically only after every check passes;
8. otherwise preserve the previous known-good engine and the failed staging
   diagnostics.

If GCSIM renames or changes an internal type used by the narrow adapter, patch
application, compilation or semantic smoke must fail before activation. The
standalone Go optimizer remains unaffected unless the versioned compact IR
contract intentionally changes.

During development the current numbered patch stack is forensic reconstruction
input. It is not the desired release shape and must not be copied wholesale
into the Go optimizer.

## 9. Continuous optimum and other retained work

The Python continuous-target implementation is **not** part of Selected runtime
and is not deleted at the first Go cleanup. Mark it
`FUTURE_GO_PORT_FOR_THEORY_ALL_SETS`: it remains reference evidence for farming
guidance, equal-investment stat balance, plateaus and theoretical set packages.
It may be ported only after Selected Go acceptance and must stay isolated from
normal FGBS unless a later measured design explicitly changes that rule.

Energy/ER optimization, broad All Sets semantics, Theory UI and automatic equip
remain outside the initial Go rewrite. The rewrite reaches current Selected
capability first, cleans Python, then advances from that point in Go.

## 10. Performance and execution rules

- Selected cold product failure: >190 s total including compact evidence,
  search, finalist n=1000 and result production.
- Development audit ceiling: 360 s unless the user explicitly changes it.
- No subagents or parallel agents for this project.
- Work sequentially; no parameter sweeps or brute-force retries.
- Stop after three substantive failed approaches to one blocker; ordinary code
  errors are fixed without pretending they are conceptual failures.
- No full-account/n1000 run before the preceding reduced/parity gate passes.
- Preserve unrelated dirty-tree work; do not commit/push unless requested.

## 11. Current next implementation block

GOB-3 through GOB-8 and the pre-performance repository checkpoint are
complete. The active stage is GOB-8P: replay only the exact seven saved
finalists at n=500 against their existing n=1000 evidence, then decide whether
the product may use an adaptive final gate that extends only unresolved leaders.
Do not perform a broad n-sweep or another full optimizer run before that
decision. GOB-9 remains the final deep reachability/patch/update cleanup after
the finalist protocol is frozen, so the same area is not cleaned and recreated
twice.
