# GCSIM Optimizer Go Backend — implementation design and acceptance record

Current implementation, acceptance limits, active engine and next action:
[GCSIM_GOB11_GP3_CHECKPOINT.md](GCSIM_GOB11_GP3_CHECKPOINT.md).
This design's stage measurements remain historical evidence, not new-team
performance or complete dependency-coverage guarantees.

This document owns the Go optimizer implementation, including the user-approved
parametric/common-search overhaul in trace handoff section2. It is not a
line-by-line port of the Python implementation. Python FGBS
and stochastic expectation were temporary executable references and were
removed after the explicit GOB-6 parity/cleanup gate.

## 1. Goal

Build one production-oriented local optimizer which:

- receives one compact immutable account/team/rotation request;
- obtains compact formula evidence from the bound GTT-GCSIM engine;
- searches legal physical artifact assignments in Go;
- sends a bounded finalist set to the same engine at common fidelity; the approved
  All Sets replacement uses one n500 stage, while pre-transfer Selected retains
  its installed staged policy;
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
upstream engine patch. Implemented repository boundary:

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
- Selected legality policy: fixed 4p or fixed two distinct 2p sets, one spare piece per wearer,
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

`source_manifest_sha256` is the hash of the build's canonical JSON body, without
its file newline; use `source_manifest_build.canonical_json`, not a file hash.
The development budget must cover the selected mode's product budget (All Sets
600s does not inherit Selected's shorter development limit).
Calculation-valid5-star pieces from unregistered sets remain raw-stat offpieces:
transport their concrete `set_uid` casefolded when no registered key exists.
Only verified set capabilities can nominate active packages, and singleton
offpieces never emit an engine set bonus. Do not drop an equipped physical ID
just because its inactive set bonus is unmodeled.

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

The pending 2026-09-16 dependency successor adds the neutral `select_lt` node:
exactly four ordered inputs `(left, right, if_true, if_false)`, returning the
third when `left < right` and the fourth otherwise. All inputs remain
dependencies, including the currently unselected arm. Only bounded pure scalar
source shapes are accepted; this is not general branch/task replay. Both arms
are evaluated by the numeric DAG and must be valid numeric expressions, without
gameplay side effects. Reference, dense, constant and one-wearer paths agree.
Older consumers reject the unknown operator; engine and native consumer updates
must be paired, with engine/patch identity in cache bindings. This is an
arithmetic operator, not a character/reaction rule. Current installation and
remaining acceptance gates are owned by the checkpoint linked above.

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

## 7. Historical Implementation And Acceptance Stages

GOB-0 through GOB-10 are complete. The entries below preserve the contracts,
failures, repairs and measurements at each stage; engine IDs, next actions,
performance failures and UI estimates inside them are not current runtime
status. Current resume is `GCSIM_GOB11_GP3_CHECKPOINT.md`, gate order is owned by
`GCSIM_OPTIMIZER_TRACE_EQUATION_HANDOFF.md`. Do not rerun completed stages merely
because an old entry uses imperative wording.


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

- historical ordered engine patch `0022-gtt-compact-equation-v1.patch` first added the opt-in
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

- a separate source tree was built from upstream `v2.42.2` plus the historical
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

The GOB-8 result surface introduced a live elapsed timer with a then-current
3-8 minute estimate; the current localized UI estimate is 1-3 minutes. A successful result is materialized from the returned IDs
and the existing account artifact rows into four compact 5-piece rows. Artifact
and element imagery is reused from existing project assets without generated or
downloaded replacements. Per-character Save prompts for a preset name and
delegates to Artifact Browser's existing `save_build_preset` service; it never
auto-equips the result and owns no second persistence path.

All measured final candidates are returned in measured-DPS order through an
additive result-v1 `candidates` field. Each row contains exact twenty IDs and
its measured result, so UI paging never reads the debug receipt or starts more
simulation. Payloads created before this additive field render as one page.

GOB-8P's bounded replay is complete. Repeated unchanged user runs finished in
3:33 and 3:40; that spread remains ordinary host-load noise. The latest real
winner was formula rank 20 among the 25 n=128 inputs, so replacing n=128 with
formula top-7 is contradicted by saved evidence. Replaying only the exact saved
seven at n=500 preserved the n=1000 winner and top-five set while cutting this
stage from 92.54 to 46.36 seconds. Production therefore retains n=128 and uses
an adaptive final protocol: n=500 for all, n=1000 only for a two-to-four-row
group still within three combined standard errors of the leader, otherwise an
explicit overlap result. The subsequent full Go acceptance retained all 24
formula finalists and the common 25-row n=128 screen, resolved the seven-row
final at n=500 without extension, and completed in 159.06 seconds with the same
known winner. No second replay or parameter sweep is authorized. GOB-9 cleanup
then completed without another full optimizer run.

### GOB-9 — PASS, final workspace cleanup

Selected now has one reachable implementation: AppShell -> narrow Python input
preparation -> one standalone Go optimizer. A clean import proves that the
historical trace/search packages are absent from this path. The unreachable
Python response/oracle/search chains, stale manifests and orphaned tests/tools
were removed; Current/farming and continuous-target reference mathematics were
retained under their explicit future owners.

At GOB-9 the engine integration had exactly one historical patch:
`0001-gtt-engine-adapter-v1.patch`, SHA-256
`01ff5993aaf6c3726db30de0b6876c55401b5a3e66e1df979bee24e7c8245638`.
It reproduces the accepted 4,314-file source tree exactly after a fresh apply.
Transactional update built and activated
`gcsim-v2.42.2-gob9-consolidated-20260831`; rollback to the prior GOB-8 build
and restoration both pass. Ordinary n=1 and one real compact-seed handshake
pass. The updater reuses a valid cached release archive and handles truncated
downloads fail-closed.

This receipt is superseded for current runtime identity by the cleaned v2.45
patch and activation recorded below; it remains only as GOB-9 history.

Regression result: 42 focused patch/update/input tests, 638 GCSIM tests, 189
combined optimizer/AppShell UI tests, all Go tests and `go vet` pass. No full
optimizer or high-iteration verification was repeated for cleanup.

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

The former numbered patch stack is historical evidence only and has been
replaced in the repository by the single consolidated adapter patch.

## 9. Continuous optimum and other retained work

The Python continuous-target implementation is **not** part of Selected runtime
and is not deleted at the first Go cleanup. Mark it
`FUTURE_GO_PORT_FOR_THEORY_ALL_SETS`: it remains reference evidence for farming
guidance, equal-investment stat balance, plateaus and theoretical set packages.
It may be ported only after Selected Go acceptance and must stay isolated from
normal FGBS unless a later measured design explicitly changes that rule.

Energy/ER optimization, broad All Sets semantics, Theory UI and automatic equip
were outside the initial Go rewrite. Selected, Selected2+2, All Sets, Theory and
finite-energy extensions now exist; current acceptance and remaining visible-UI
gates belong to the GP-3 checkpoint and TODO rather than this historical stage.

### Selected 2+2 extension (2026-09-16)

Selection still comes from current equipment through the same AppShell adapter.
There is no second set picker, automatic equipment mutation or new engine patch.
Accept active tiers4 or2+2, including5 and3+2 actual piece counts. Reject a lone
2p,3+1+1, duplicates and ambiguous packages. A spare piece may belong to either
chosen set or any third set; it cannot activate a different four-piece bonus.
Both original2p bonuses stay in compact capture and ordinary finalist configs.

Wire extension: old `selected_set_uid` and `fixed_four_piece=true` are retained
for existing4p requests and their canonical hashes. A pair uses sorted
`selected_sets=[{set_uid,count:2},{set_uid,count:2}]` instead; the request sets
`fixed_set_packages=true` and `fixed_four_piece=false`. Exactly one policy and
one wearer representation is allowed. Old consumers reject the new fields;
deploy the paired Python adapter and Go binary together. The native domain
normalizes both encodings into requirements, not duplicated search engines.
Artifact IDs remain globally unique and wearer/slot-bound. The formula seed
panel and artifact variables are unchanged; set effects are captured context.

For2+2 the same bounded FGBS searches disjoint set-membership slot patterns:
10 for3+2,10 for2+3,30 for2+2+off (at most50, dropping empty pools). This enumerates
only five-slot labels, not artifact pairs or the team Cartesian product. Other
wearers' occupied IDs are removed before constructing pools. Every legal build
belongs to exactly one pattern; the original six4p lanes retain their order.
Pair lanes share the existing20,000 frontier-expansion budget so the first lane
cannot consume it all. Each visited lane retains its legal greedy completion
even when frontier expansion stops. Guide completion evaluations are separately
counted, as in4p; the expansion limit is not a bound on all evaluations. Finalist
and simulation budgets are unchanged. No global optimum claim.

Final rendering replaces each selected set row in place, keeping producer
initialization order, emitting actual2/3 or4/5 counts exactly once. Unexpected
set names, missing/duplicate rows and changed bonus tiers fail closed. Small
exhaustive tests prove the50-pattern partition and controlled-domain search;
real copied-account gates and installed/UI status belong to the checkpoint.

### All Sets development plan (2026-09-16)

The following is the staged design; its bounded implementation now exists. Current
Selected captures concrete set effects as context; changing a package is not
just changing artifact-stat leaves. Never retain the old set buff or assume a
new conditional effect exists because its label is known. The user deferred
manual2+2 acceptance until combined UI checks; TODO owns that reminder.

Scope: existing account pieces, fixed team/weapons/rotation/target, proposed
4p and distinct2+2 packages. Preserve one flexible piece and20 physical IDs.
No inventory-independent ideal builds, automatic equip or energy-aware search.
Keep a separate All Sets orchestration boundary over shared Go formula/domain/
FGBS/finalist modules; do not clone Selected or revive removed Python searches.

1. **Set-effect preflight and replacement contract.** Inspect current catalog,
   compact provenance and generator against representative static, conditional,
   team-buff/resistance and reaction effects. Determine when removal/addition
   can be expressed completely as known formula inputs and when a fresh bound
   capture is mandatory. Preserve producer ownership, effect identity/stacking,
   activation timing, cross-owner dependencies and changed topology. A source
   signature is a discovery clue, not proof of activation or reuse. Existing
   `optimizer_two_piece_signatures.py` is only a narrow static-stat/reference
   implementation, not a universal4p analyzer or active Go catalog. Exit: a
   concrete neutral contract, focused no-ghost/double-buff response controls,
   and measured capture/reuse cost before freezing the search budget.
2. **Feasible package domain.** Build4p/2+2 candidates only where inventory slots
   allow them; final feasibility is joint across wearers. Group proven identical
   effects for arithmetic reuse without collapsing distinct physical items.
   Unknown conditions are not zero effect and cannot justify hard exclusion.
3. **Team-context proposals.** Use known formula response and available artifact
   quality to prioritize package/wearer choices. Compare whole-team gains,
   retain distinct personal/support/reaction routes and reconsider provider
   transfers/duplicates as the team changes. No named character roles or always-
   mandatory resistance set. Proposal scores guide order, not unsafe proof of
   dominance. Freeze exact queue/widths after the first measured pilot; no claim
   that independent best-per-character choices produce the best team.
4. **Bounded shared search.** Reuse indexed artifacts and compiled context only
   under proven identities. Couple package changes to legal complete builds;
   use existing FGBS within each accepted formula context. New conditional/
   schedule context requires evidence, not fabricated modifiers. One global
   search/capture budget, not a full Selected pipeline for every set combination.
   Preserve incumbent/diverse alternatives and enforce global ID conflicts.
   If required capture count defeats600s, report that measured design blocker;
   do not silently prune unknown sets or multiply simulations without a bound.
5. **Acceptance and UI.** Small exhaustive controls for package/item synergy,
   support transfers, non-stacking buffs,2+2 and ID conflicts; then bounded real
   supplied teams. Use one shared ordinary-engine finalist panel and report
   unresolved ranks/coverage. Time domain/discovery/capture/compile/search/
   verification separately against600s. Reuse result cards/save and explicit
   cancellation. Before combined UI acceptance remind the user about deferred
   Selected2+2, then test All Sets. No performance success is assumed in advance.

Step1 preflight, the isolated context/routing code and bound capture/domain
pilot are recorded below; no real-set proof producer is enabled. Source
grouping alone is not a reuse certificate. Broader tracing or weaker product coverage still requires an
explicit tradeoff before scope expansion; no unrestricted search is authorized
by the preflight's positive static controls.

### All Sets effect/context boundary established by preflight

Evidence: `tests/fixtures/gcsim_optimizer_go_v1/all_sets_preflight_receipt_v1.json`
and `all_sets_preflight_samples_v1.json`. Research harness:
`tools/experiments/gcsim/all_sets_preflight/`; current status/resume stays in GP-3.
Seven new same-seed n1 captures on the original copied bloom config, no full
search, DB/UI writes, engine changes or new final simulations. Four static
remove/replace/equivalent/restore controls match all543 hits, including cross-
owner effects. Two deliberately wrong old/double-bonus controls fail as intended.
Conditional4p, team-buff and resistance changes require different formula
context even when hits/topology match; new-damage package changes543 to561 hits.
Those negative shortcuts do not mean fixed-set Selected has regressed.

Source findings in the pinned engine:

- `pkg/gttcompact/attack_fields.go::compileArtifactStatRead` composes observed
  stats plus artifact deltas and represented modifier ancestry. This enables
  the demonstrated static replacement through existing arithmetic.
- `pkg/gttcompact/direct.go` embeds observed DefMod/ResMod as constants.
  Existing Go IR carries arithmetic nodes/coordinates, not removable set-
  provider identities. Never identify a bonus by its numeric value or label
  and edit an arbitrary constant; hit topology does not certify effect context.
- `optimizer_two_piece_signatures.py` recognizes25 of42 five-star2p constructor
  stat shapes on this snapshot. It does not prove full NewSet/Init/helper
  side-effect, modifier-key collision, initialization-order or read-binding
  equivalence. The other17 are unproved, not useless. Existing catalog flags
  are source/issue-backed discovery metadata, not semantic acceptance.
- The old account fixture has27 slot-feasible4p packages and465 distinct2+2
  pairs; these are optimistic single-wearer counts, not legal four-person teams.
  A short capture costs2.43-2.92s here. Exhaustive package/team capture or full
  Selected-per-package is not an acceptable design. Numbers are fixture-only.

Neutral contract (isolated Go boundary implemented; product wiring remains open):

1. A package context identifies each actual wearer, concrete set UID/tier,
   parameters, initialization order, source/catalog/patch/binary identities,
   fixed rotation/target/energy/seed policy and the artifact reference vector.
   Effect entries keep source identity, scope (owner/team/target/new output),
   represented amount/condition/timing dependencies and proof/unknown status.
   Discovery data never pretends a conditional effect is active.
2. Choose **identity reuse**, **proved static replacement**, or **fresh context**.
   Static replacement needs complete changed-effect/lifecycle/read-binding
   coverage and compatible modifier identities. Maintain its separate vector
   `new static effect - captured static effect`; evaluation composes this with
   the candidate's raw-artifact delta exactly once. Never write this vector
   into the physical artifact database or final config stats. Unproved or
   conditional changes route to fresh capture; no implicit zero effect or
   silently accepted unchanged-topology shortcut.
3. Fresh capture replaces set rows in the complete team config, retaining
   character order and real raw artifact stats, then uses the existing compact
   adapter/Go compiler. Old effects disappear by construction. Team buffs,
   non-stacking sources and new hits are observed together, not added as four
   independently measured set gains. No new game coefficients in the consumer.
4. One capture/compiled context serves many item candidates. Bound and memoize
   contexts by full identities within the run; share preparation and inventory
   indexing. Keep current2-seed policy for product search; n1 here was a controlled
   experiment, not authorization to reduce product fidelity. Context scheduling
   and global600s budget must be measured before account-scale search.

New hits are a distinct, uncommon effect class, not a synonym for every set
change. A flat addition to an existing hit does not itself create another hit;
Clam's scheduled attack is the concrete new-output preflight witness. A changed
conditional buff/resistance can require a new formula without changing hit count.
Discover new outputs from engine attack creation, never a set-name switch or
the wording "additional damage". Candidate-dependent healing/other inputs of
new outputs must remain formula dependencies where supported, not fixed damage.

### Isolated All Sets context/routing implementation

`native/gcsim_optimizer/internal/setcontext/` is a reusable boundary, not a
second scorer or an enabled product mode:

- `context.go`: immutable identities bind binary/source/patch/catalog,
  reference stats, ordered seeds and exact full prepared config. Config bytes
  retain weapons, target, rotation, energy, package counts/parameters and actor
  initialization order. Replace a whole contiguous package at its original
  position; reject ambiguous rows, duplicate sets, more than five pieces and
  unknown owners. Preserve other text/raw-stat rows and line endings. The
  renderer is intentionally for normalized prepared declarations, not arbitrary
  rotation parsing. Final physical4p/2+2 legality still belongs to the domain.
- `route.go`: identical-context reuse; otherwise a trusted, scoped static
  certificate or fresh context. The static branch verifies context/graph/evidence
  binding, complete lifecycle/read/modifier/schedule obligations, every changed
  package's active2p/4p tiers, owner coordinates, modifier-key ambiguity and
  candidate bounds. Keep `new effect - old effect` apart from raw artifact
  deltas and compose once. Current proof metadata represents owner-static
  effects only; team/target/new-output/conditional/unknown scope routes fresh.
- `session.go`: sequential run-local cache, explicit maximum seed-member
  capture reservations and outer cancellation/deadline, with no hidden retry.
  Provider envelopes must match exact config/context/engine and the complete
  seed panel. Compile with the existing shared formula compiler and verify
  zero-delta baselines. Return to a cached context without recapture. Reuse
  proofs always start from the actual captured origin, never chain old biases.

Important authority limit: `StaticProof` is a trusted-verifier OUTPUT contract,
not an automatic verifier and not JSON accepted from a UI/request. Its coverage
fields must never be filled from constructor discovery or point tests. No real-
set proof producer is enabled. The positive contract tests use a completely
known synthetic model. Real transitions conservatively obtain their own
captured graphs. `engine_provider.go` now connects the same boundary to actual
engine subprocesses in isolated directories, not the installed product route.

Evidence2026-09-16: all native Go suites PASS; the retained seven-change matrix
uses eight saved members, no new engine calls, and reproduces fresh baselines
within1.46e-11 DPS absolute roundoff. It also tests same-frame refusal, preserved
543/561 hit counts, shared-compiler artifact response, cache/restoration and
budget handling. `all_sets_context_routing_receipt_v1.json` records22.49s replay
including large JSON validation/compilation, NOT All Sets search performance.
The first harness pass found LF original versus CRLF probe files; rendering
tests now use the matching newline frame, while capture identities stay exact.
Both newline variants are covered; no relaxed production identity was added.

### Bound capture/domain/search pilot and scope decision

Implemented (installation and actual UI acceptance are checkpoint-owned):

- `engineclient.RunCompact` preserves exact config bytes, emits the existing
  compact adapter request, runs one explicit seed with cancellation/hidden
  Windows process, verifies output and measures process/decode separately.
  `setcontext.EngineProvider` requires the full ordered two-or-more seed panel,
  exact binding and explicit existing energy flag; verify binary before/after
  the stage. Separate exclusive directories prevent stale output reuse.
- `evaluator.CompileMembers` shares the original Selected arithmetic, baseline,
  response ledger and equal-seed weighting. `Handle.SearchPanel` is available
  only for an exact captured context; substituted-bias handles cannot bypass
  composition. The full native suite protects the existing Selected path.
- `domain.FeasiblePackages` uses slot bitmasks:4p needs four distinct slots;
  each2p needs two and their union four. Exclude occupied IDs for a one-wearer
  step. No physical build Cartesian product. This is not joint team feasibility.
  `PackageSeed` visits at most3^5 category patterns after one inventory scan;
  its optional finite priorities guide order, not proof of optimality.
  `ForPackages` shares immutable inventory and original capture-stat references.
- `search.RefineWearer` is a bounded existing FGBS actor step. It enforces
  coordinate/owner alignment and a legal whole-team anchor; other fifteen IDs
  stay reserved. It is not a second search algorithm or full Selected-per-set.

Evidence: `all_sets_capture_domain_receipt_v1.json`, reproduced by the isolated
`capture_pilot.py` in `tools/experiments/gcsim/all_sets_preflight/`. Original
copied bloom inventory only;492 optimistic packages (27x4p,465x2+2) in18.9ms.
Two hand-selected witnesses, not an automatic queue: Lauma/Gilded4p and
Kuki/Paradise4p. Two seeds each plus independent two-seed candidate controls:
eight actual compact calls, two saved baseline members.1000-expansion research
cap (not production default);20 unique IDs, other fifteen unchanged, cache
reuse checked. Formula/fresh expected DPS match exactly at both candidates;
neither improves the original baseline. Incumbent retention remains mandatory.

Measured before the JSON optimization, milliseconds:

| Step | Lauma/Gilded | Kuki/Paradise |
| --- | ---: | ---: |
| Engine processes, two seeds | 5829 | 5734 |
| Strict result decode/validation | 3791 | 3574 |
| Remaining capture/graph identity/compile | 1941 | 1806 |
| Reduced one-wearer FGBS | 335 | 299 |
| Independent candidate controls, two seeds | 9947 | 9329 |

Full pilot receipt49.39s, Go test50.61s including deferred binary checks.
Initial fixture-hash mismatch was corrected before any new engine calls:
Selected's trace-context hash is not its prepared-config hash. Do not merge
those namespaces. The permanent receipt records this and subsequent no-rerun
harness cleanup. The new canonical JSON helper avoids one redundant generic
marshal/decode; three same-file comparisons produce byte-identical output,
median raw-canonicalization substep910->442ms. This is not a measured halving
of capture or total search. Seven retained contexts also pass after the shared
compiler refactor (19.78s, zero engine calls).

**Capture-pilot decision (now resolved by path1 below):** the safe execution path
works, but a complete cheap general4p guide is not yet available. Static2p descriptors
recognize constructor shapes; they neither describe all conditional effects nor
prove removal of an old set throughout its lifecycle. For example, the pinned
Wanderer4p is installed in `Init`, Gilded prepares a team-dependent vector in
`Init` and subscribes to reactions in `NewSet`, and Paradise uses an attack-tag
filter plus timed stacks. These are source witnesses, not names to special-case.
Current compact resistance/defense multipliers can still be observed constants.
Keeping hit topology cannot authorize replacement; live source review reconfirmed
this in `pkg/gttcompact/direct.go`.

User decision after the pilot: path1 below is approved; path2 is not the chosen
implementation. Continue sequentially until a new substantive decision is needed.
The alternatives are retained only to explain the agreed scope:

1. **Approved: generic effect discovery and formula-informed proposals.**
   Describe source-backed amount, stat/tag applicability, recipient, activation,
   stacking and possible new outputs, without set-name rules. Start with a
   bounded source-shape/lifecycle pilot, not a universal Go interpreter. Keep
   discovery/optimistic guide separate from certified replacement; unproved
   activation is neither zero nor guaranteed. Reuse only certified contexts;
   obtain fresh panels for shortlisted conditional/unknown/new-output changes.
   If common effects need new engine provenance, scope that change and update
   patch/compatibility gates instead of silently widening this consumer task.
2. **Faster initial delivery, weaker coverage:** choose a bounded package queue
   from currently available static/raw-item hints and exploratory alternatives,
   capture each queued context, and disclose unexamined conditional effects.
   This can miss strong support/reaction packages before understanding their
   value. It must not be presented as the requested broad formula-informed
   ranking or silently enabled as complete All Sets.

No exhaustive per-package capture is proposed:492 contexts already precede
wearer/team assignments, and a fresh context costs about11s here. That is not
a measured full-search failure or proof of impossibility; it rules out the naive
schedule under600s. No exact queue width or weakened coverage has been chosen.
Implement the approved guide, freeze a measured global
queue/capture/time budget, test package/item synergy and provider transfers,
then common ordinary finalists/UI. Preserve incumbent/diversity and never
hard-exclude unknown sets as useless.

### Source recipes and neutral input guide (isolated implementation)

`internal/seteffects` is the approved bounded source-discovery layer. It parses
the complete catalog-supplied original Go package and hashes all supplied bytes.
It does not execute Go, fetch imports, identify sets by name or grant certificates.
The explicit seams are engine modifier/attack-creation APIs and their types.
The engine's stat/attack enums supply vocabulary; unfamiliar enum shape rejects
the affected mapping rather than shifting IDs. Renaming labels/locals and changing
source coefficients are covered by tests.

Source graph: assignments/returns, lexical guards, event/task/helper edges,
unique returned Set receiver, immutable constructor fields, typed owner/team
recipients and Amount-callback AttackInfo inputs. Mutable/escaped/shadowed roles,
unresolved calls, loop membership, dynamic stacking and new outputs remain
explicit. Limits:100000 AST nodes, expression depth32, activation depth12/64paths.
These are refusal bounds, not evidence that everything within them is understood.
Guard text collisions become unknown. Unknown expressions never establish zero.

Recipes retain **alternative** amount states: e.g. one vector field written in
different callbacks is not a sum of every write. Pure source constants fold with
Go integer division preserved. Piece-count specialization and typed attack-tag
conditions are separate from actual activation. Empty switch cases reach the
post-switch code; trigger-hit filters are not reused as recipient-hit filters.
Owner/team discovery does not prove runtime eligibility, uptime or stacking keys.

Three proposal features exist, none a changed-set score:

1. Raw-stat/channel proxy: perturb an existing captured artifact coordinate,
   evaluate the SAME FAST program and retain only appropriate observed channels.
   `EvaluateChannelDPS` preserves per-seed duration/weight. Source alternatives
   are separate features. Unrepresented consumer coordinates are missing, not
   a zero contribution. Extra semantics/indirect effects are not certified.
2. Exact read-input increment: an isolated observer annotates an EXISTING
   reaction-bonus sum with its actual reader owner, queried tag and graph node.
   No new evaluation/event or gameplay call is introduced. The annotation is
   separate from the unchanged compact member and requires exact graph hash and
   observed-value checks. It is not a source-set replacement certificate.
   `formula.CompileInterventions` adds offsets AFTER original node computation
   and uses the existing arithmetic implementation; original artifact/foreign
   dependencies and downstream contributor sorting survive. It is isolated from
   the production FAST search hot path. `seteffects.InputProbe` connects source
   terms to matching reader inputs, not to the actor printed on the final hit.
3. Target-resistance increment: a bounded scalar slice reads the curve from
   the bound engine source's actual Resistance/ResMod assignments. It accepts
   pure float arithmetic/if branches with lazy branch evaluation, not calls,
   loops or escaped/mutable inputs. Both current damage paths must agree on
   the normalized source recipe. The isolated adapter annotates exact terminal
   multiplier nodes with hit/target/element and observed resistance; it never
   searches for a numerically equal constant. Dead nodes from failed formulas
   are excluded. Direct numeric-recipe and contributor output paths are included.
   Source/value/graph checks precede every probe. No curve coefficients are
   copied into the consumer. Team modifier hints perturb all recognized
   recipients together, preserving cross-owner nonlinear arithmetic.

Evidence: `all_sets_effect_discovery_receipt_v1.json`, source-only42-package scan
plus four new n1 controls on fixed copied bloom/cloud fixtures. Source discovery:
93 effect sites,138 possible terms,116 source constants; NOT a percentage of
complete mechanic or damage coverage. Parse/evidence0.106s, saved panel load/
compile3.44s,728 features0.254s (280 have raw-stat numeric proxies). The isolated
artificial +0.1 reaction-bonus controls exactly match native predicted DPS for
Kuki and Ineffa;100-repeat offline average0.66-0.68ms per graph evaluation. No
ordinary final panel, account-level package ranking or UI acceptance follows.

Observer prototype: `tools/experiments/gcsim/all_sets_preflight/` with a retained
three-copy delta `effect_inputs_experiment.patch` and added observer/test overlays.
This is NOT a second production patch stack. Installed source/binaries remain
unchanged. Remove the delta after eventual production consolidation, compatibility,
ordinary parity and installation gates. Raw four-capture oracles stay until guide
integration; live cleanup projection is owned by the checkpoint/manifest.

The added resistance controls and source/input join are scoped by
`all_sets_effect_guide_receipt_v1.json`. Installed compact resistance remains
constant. The clean candidate now exports opt-in `gtt_effect_inputs_v1` alongside
the unchanged compact member; its marker is in ORIGINAL engine source and the
normal generator preserves it. No handwritten generated output is retained.
`all_sets_observer_consolidation_receipt_v1.json` records clean patch, source
generation, exact transport/stat-response and standard bundle gates. Candidate
was isolated at that receipt; subsequent installation is checkpoint-owned. Experimental deltas are
not additional production patch stacks. Unknown conditional/new-output cases
retain exploratory/fresh-context routes, not hard exclusion.

The sidecar binds exact member file bytes, original input config, resolved engine
config, source manifest, seed and actor initialization order. Original/resolved
text digests are distinct: upstream normalizes CRLF and adds a newline. Native
canonical member hashes are a third, separate namespace. Missing capability,
sidecar or mismatched provenance fails visibly; no stderr parsing or silent
raw-stat-only downgrade. Selected keeps its old request unchanged. Observed
port values are validated against their exact graph before guide intervention.
An exact-context handle can lend snapshots to guide compilation; substituted
contexts cannot inherit these observations. Guide reanchoring uses current raw
artifact deltas and clears numerical proxy caches, without changing graph origin.

#### Bounded package proposal pilot (not product budget/quality acceptance)

The source-input guide is now a reusable `allsets.BuildGuide`, not only an
experiment test. `optimizer_go_all_sources.py` checks binary, canonical manifest
and complete original source-tree identity once; Go checks source envelopes and
does the AST/math work. Unsupported syntax stays a local unknown; broken binding
fails. Per-seed input responses are equal-weighted without renormalizing away
unknown members. No-port/over-limit input families stay unresolved; other families
continue. `Guide.Propose` requires the same graph/context/raw-stat anchor.
Reanchoring resets cached probes and recomputes BOTH feature gains and raw-stat
slopes at the current artifact combination. Actor-local scratch restores all
other actors to that anchor, not to the original zero-delta equipment.

#### Joint carrier/item proposal lane

A literal shared source-key opportunity can move from one wearer to another
while the old holder takes a different package. This is not a name-based list
of mandatory support sets and does not certify activation/stacking.

- Reserve only the other ten physical items. Enumerate slot-feasible PACKAGES,
  then rank their independent linear item completions plus source opportunities.
- Retain at most two package alternatives per role for each current shared key.
  Combine only these bounded alternatives, not every pair of packages/items.
  Unknown/dynamic keys remain on generic discovery lanes, not global-zero claims.
- `domain.PairPackageSeed` selects the best two items per slot/category/wearer.
  Only their at-most-four combinations are needed to avoid a shared physical ID:
  the other wearer can occupy only one candidate in that slot. A five-step DP
  over two package count vectors joins these slot choices. It is exact for the
  supplied ADDITIVE priorities, not for nonlinear damage. A tiny exhaustive
  synthetic oracle checks4p,2+2,shared IDs,ties and reserved items.
- Rank joint proposals by old-context raw counterfactual relative to an equally
  constructed current-package pair plus changes in source opportunity maxima.
  This is neither replacement DPS nor an upper bound. Dedupe whole team packages.
- `RefineTransfers` replaces both set blocks together, resolves ONE fresh context
  via the existing shared session/deadline, then runs unchanged team FGBS. It
  neither splices two individual set effects nor gets an extra simulation budget.
  Unknown mechanics and new-output sets still require fresh contexts.

These are bounded candidate generators. The two-alternative and queue widths
are pilot settings; global product budget/quality and finalist/UI gates remain.

#### Shared coordinator and ordinary measurement

`allsets.Run` now owns the sequential search lifetime. It optimizes the starting
packages once, preserves that Selected result and the original equipment, then
uses one context session and one wall-clock/expansion allowance for all proposals.
Each proposal retains its originating complete context and stat anchor. A better
completed result can create a refreshed guide; an older pending proposal still
uses its own context, never a mixture of the new and old buffs.

The fair queue cursor survives refreshes: joint changes, wearer breadth,
shared/new-output/unresolved routes, then remaining proposals. Whole contexts
are deduplicated before capture. Unknown features are not proven zero and the
bounded queue cannot promise to visit every route before its deadline. Report
pending/unqueued work; do not claim exhaustive All Sets or global optimality.
Budget expiry preserves completed candidates; source/binary/provenance failures
remain failures. Capture reservations and failed artifact-work reservations are
not secretly refunded. Finalists retain context diversity plus original and
Selected baselines, all with20 unique physical items.

The coarse `optimize-all-sets REQUEST SOURCES RUN_ROOT` command is implemented;
installation/UI acceptance is a separate gate. Current N1 limits: at most6 complete
two-seed contexts,3 guides,16 single and6 joint queued proposals per guide,
1,280,000 artifact expansions and420s search inside the600s outer budget. Reserve
150s for one shared finalist stage. Limits are explicit engineering bounds,
not evidence that all teams/hardware meet the target; dated receipts own timing.

`finalists.CandidateRenderer` reuses the existing n128/n500/bounded-n1000 verifier
for context-specific sets and exact raw artifact stats. All Sets checks one
unchanged non-set run frame and engine/source identities, then renders each
candidate through the same `RenderConfig`; no second simulator or finalist
arithmetic. Result identity is `set_context_panel_sha256` over bound graph/
context/assignment identities, mutually exclusive with Selected's
`compact_ir_sha256`. Hint priorities never become reported damage.

In the pre-overhaul All Sets CLI, the n128 call records measurements but does **not**
select a smaller adaptive panel: the same at-most-seven `scores` are passed to
n500/n1000. Do not describe this as Selected's24-plus-Current n128 selection.

`optimizer_go_all.py` is a narrow specialization of the common account/process
adapter: source text is serialized once, all capture/search/math lives in Go.
AppShell shares the worker lifecycle, cancellation, cards and preset saver.
The All Sets display gate reads the installed capability metadata only; actual
binary/source verification still occurs on every run. Source-tree input hashing
excludes only generated build material and exact root `gtt_engine_manifest.json`
store metadata; other source-side files remain hashed. No independent energy
setting, inventory write or automatic equipment change is introduced.

#### Single-wearer proposal lane

`internal/allsets` is the separate coordinator; it does not change Selected's
entrypoint, formula arithmetic or FGBS. The current prototype operates as follows:

- Specialize source terms for2p/4p. Preserve unknown activation; do not sum
  alternative assignments. A hint keeps the strongest individual numeric
  opportunity, not an estimated total set bonus. Literal shared modifier keys
  group team/target opportunities; dynamic keys remain unresolved.
- Compute raw-stat slopes with the existing team FAST panel. These are only
  weights for one legal seed per slot-mask-feasible package; no item is removed
  for a low weight. Seed construction uses <=3^5 set-slot category patterns,
  not physical artifact tuples. Main/substats and reserved IDs are retained.
- Score raw stats on the unchanged context **only as a counterfactual hint**.
  Compare that seed with a similarly built seed in the wearer's current package,
  so weak original equipment does not dominate every queue position. Reset
  the full-team arithmetic anchor between wearer-local probes.
- Proposal priority is raw-seed difference plus change in the peak local
  source opportunity and in shared-key group peaks across the team. Maxima
  avoid adding alternative writes. This heuristic is not candidate DPS,
  an upper bound, effect removal or a dominance/pruning certificate. An
  existing shared-key opportunity is not counted again for another carrier.
  This does not prove uptime or stacking; carrier transfers still need their
  own joint proposal and fresh context.
- One bounded queue reserves wearer breadth, shared-effect and available
  new-output/unresolved lanes; remaining slots rotate across wearers. The
  isolated16-entry measurement is not an approved/released capture budget.
  Missing/unselected effects stay visible; no claim that every useful package
  is retained. Incumbent is preserved independently, without recapture.
- `Refine` resolves each shortlisted package through the shared context session
  before handing its own panel and legal artifact domain to FGBS. Changed
  contexts first use a one-cycle/4,000-expansion-per-actor scout. After breadth
  discovery, the best scout plus one source/unknown/joint exploratory scout use
  the full two-cycle/20,000-expansion configuration without recapture. The
  Selected anchor is always fully searched first and remains the lower bound.
  It cannot create another capture budget, retry or simulate artifacts itself.
  Single-wearer proposal seeds preserve the other15 physical IDs. The product
  coordinator then invokes full-team `solver.Run` inside that fixed set context;
  the older standalone `Refine` helper only refines one wearer. Product results
  are formula candidates until ordinary-engine measured finalist verification.

The first queue witness exposed duplicate shared-effect optimism and a raw
equipment-strength bias; these were corrected before new package captures.
Current acceptance/timings and immediate continuation belong to GP-3. The source
observer, refreshed guide, joint pilot, shared coordinator and ordinary finalist
adapter exist. Remaining release/installation/UI gates are owned by that current
checkpoint, not this design history. No real-set reuse certificate producer exists.

### Isolated real-vector inventory bound concept (2026-09-19)

User-authorized limited proof, **not** the installed search or a revival of the
retired CF-BB implementation. `tools/experiments/gcsim/inventory_bound_poc/`
contains a Go test overlay and managed runner. Results and limitations belong
to the [dated archetype audit](GCSIM_OPTIMIZER_ARCHETYPE_AUDIT_20260919.md).

For one fixed, freshly captured whole-team set context, the proof keeps each
real item's complete joint stat vector. A region is a pool of possible items
for each of five varying slots; the other fifteen physical IDs are reserved.
For a linear expression, extrema are the sum of per-slot extrema of the dot
product with **each real vector**, equivalent to its convex hull. Independent
stat maxima and averaged items do not replace that domain. The mean vector is
only the numerical centre of an enclosure, never a selectable artifact.

The engine IR is constant-folded for fixed wearers and identical subexpressions
are shared. Each remaining expression carries an affine part plus a conservative
remainder. Addition preserves it; multiplication bounds the nonlinear product;
constant powers use bounded curvature; unresolved min/max/select branches use
an interval hull. Singular/unsupported relaxed powers return an infinite bound,
not a low score. Per-hit roots are aggregated into the same two-seed mean team
DPS as the production evaluator. No gameplay coefficients are copied into GTT.
The float guards are prototype safeguards, not a universal rounding proof.

Linear priorities and two rounds of slot exchanges produce a **real lower
candidate only**. Search splits item pools, visits higher bounds first and
removes a region only when its upper bound is below the feasible incumbent.
Every visited bound and best result is checked against exhaustive production
formula scores on the finite test domains. The exhaustive oracle does not feed
search priorities/incumbents. A toy joint-upgrade trap verifies escape from a
coordinate-local optimum. Crit mass is not used as a hard-prune rule; raw flat
ATK and ATK% remain separate formula coordinates with engine-owned base scaling.

Three fixture-specific domains test a witness4p package, inactive Obsidian4p
pieces and five distinct families with no bonus. Their four-item pool selection
is **test scope, not a proposed production shortlist**. Fresh capture binds each
context; no old bonus is added to a replacement and no reuse proof is inferred
from matching topology. This proof does not schedule all sets, cover arbitrary
zero-bonus inventories, model new hit schedules, solve finite energy, resolve
opaque dependencies or optimize all twenty competing IDs. Those integration
boundaries and numerical certification remain open before production pruning.

Historical performance finding: on these tiny domains, enumerating **all**
points through the reduced graph during parity validation was substantially
faster than the bound search. Its1.14-2.67x gain against the current full-graph
scorer is not a gain against that better comparator. The integration below uses
a cost-based switch to cheap exact enumeration; its account-scale measurements
belong to the retained comparison, not this tiny-domain proof. Do not introduce
a lossy top-K item cutoff to hide cost.

### All Sets real-inventory integration (2026-09-19, installed pre-overhaul)

This supersedes the N1 six-context/top16 policy **for All Sets only**. Selected
still uses its existing FGBS constructor and Theory its separate bounded roll
allocator. Acceptance, installed identity and remaining gates belong to GP-3;
[before/after evidence](../optimizer-evidence/all-sets-inventory-20260919/report.md)
uses the user's original matrix without regenerating its baseline.

1. `domain.FeasiblePackages` checks slot availability for every engine-supported
   4p/2+2 package, plus exact single2p and no-bonus alternatives. Five-slot
   family matching proves those latter shapes without enumerating item products.
   Equipped items are not locked: a failed one-wearer seed tries whole-team
   reassignment in24 wearer orders. Greedy joint-seed failure is explicitly
   `reservation_deferred`, **not** proof of physical impossibility or weakness.
   Physical validation rejects hidden2p/4p bonuses in a no-bonus/single2p context.
   All real item IDs remain eligible; inactive-set pieces are not banned.
2. `BuildDiscoveryGuide` supplies source shape/uncertainty only. Hypothetical
   source maxima no longer count as set damage. All feasible seeded packages
   remain queued; old-context raw-stat scores order work but never certify a
   replacement's strength. Wearer/shape round-robin reserves discovery breadth,
   including shared effects and package permutations. There is no named-set
   allowlist or top16 queue. Uncaptured packages remain unknown, not eliminated.
3. Every changed whole-team package gets a fresh two-seed engine capture,
   including its actual buffs and hit schedule. The old set rows are replaced,
   not stacked with the new ones. The same-topology reuse shortcut is disabled.
   No source-text activation guess supplies DPS; an inactive bonus has no
   extra guide gain. Physical4p can still win on its raw items or active2p.
4. `search.NewInventory` specializes the captured **whole-team** arithmetic to
   one wearer's artifact coordinates with the other three at their actual
   current deltas. Constant folding, common-subexpression sharing and dead-node
   removal produce a cheap scorer; team buffs and foreign-owner effects remain.
   HP/ATK/DEF flat and percent, EM, CR/CD, ER and damage bonuses stay independent
   wherever the engine graph depends on them. Crit caps/balance are inherited
   from that graph; there is no universal CR target, CV hard cutoff or summed
   "effective ATK" approximation replacing the original formula.
5. Real item-vector pools use the affine enclosure described above. Local
   derivatives, a linear legal seed and slot exchanges establish/order actual
   candidates only. Larger regions split by pool size and visit higher bounds
   first; smaller regions enumerate the cheap scorer when their leaf count is
   at most `max(256, 4 * total_pool_items * (coordinate_count + 1))`. This is an
   explicit computational heuristic, not a damage coefficient or quality cutoff.
   Only a numerical upper bound below an ER-feasible incumbent prunes a region;
   unknown/singular bounds are infinite. Every retained point is rechecked
   against the original panel. Work limits preserve an explicit unvisited count.
6. Context scouting/refinement shares one session. Current diagnostic defaults:
   48 fresh contexts,12 guide refreshes,3 deep refinements,900s search within
   a1080s product deadline;12k scout/20k deep work per wearer. These are finite
   exploration budgets, not proofs that pending sets or item regions are weak.
   At most7 pooled finalists, including baseline anchors, use the existing
   ordinary-simulation policy (128 screening,500 finalists,1000 near ties).
   Final displayed ranking is measured team DPS, not bound/guide/formula rank.

Limits: current discovery is not a full Cartesian four-wearer set optimizer;
joint seeds are not an exact20-ID assignment solver. Floating enclosures have
focused exhaustive/property controls, not universal rounding certification.
Fresh set capture observes a schedule at reference stats; artifact-dependent
branch/schedule changes and opaque ancestry remain local model boundaries.
Expanded captures/cache/builds are disposable managed jobs. The compact before,
after, install and report files have bounded retention owned by
DATA_RUNTIME_BOUNDARIES; unit controls and the comparison runner are in TESTS.

### Parametric/common-search foundation (2026-09-19, source-only)

Scope/acceptance owner: [GP-3](GCSIM_GOB11_GP3_CHECKPOINT.md). The trace handoff
section2 retains the entire approved scope, not just this first implementation.
The installed consumer and active engine are unchanged; no new full optimizer
run, ordinary candidate panel, matrix row or physical UI acceptance is claimed.

`formula.PrepareParametric` builds one aggregate two-member DPS program. Explicit
exact-node scalar correction ports are introduced BEFORE hash-consing/constant
folding, so equal observed values, zero corrections and conditional arms do not
erase distinct inputs. Original ordered arithmetic is preserved; this is common
subexpression elimination, not unrestricted algebraic reassociation. Dead nodes
are removed and constants are initialized once. Per-member durations remain
separate. `Panel.ArtifactProgramForActors` retains that preparation and specializes
one/two wearers from the small graph instead of the original hit/member graphs.
`ValueGradient` obtains all local stat slopes in one reverse pass. Nonsmooth
caps/branches are reported; slopes are ordering hints, never dominance proofs.

EffectPort is a bound arithmetic input, NOT an activation proof. The approved
neutral producer below removes the requirement to subtract old sets on All Sets'
new route; non-neutral replacement still needs actual removal. Specializing a
fixed correction cannot stand in for a stat-dependent effect. Complete event/
state and arithmetic binding is required before switching context selection.

The fixed-package All Sets inventory source now uses a global region heap instead
of per-lane DFS/equal allowance slices. It retains complete real item vectors,
has no numeric-vector deduplication that discards IDs, and checks legality before
charging a point. Existing small-region cost heuristics still need profiling.
Any opaque model dependency disables finite pruning bounds conservatively; known
arithmetic still scores candidates. This coarse guard is not precise local
uncertainty attribution and may reduce pruning until the producer is complete.

Joint refinement releases both wearers: a legal linear five-slot pair seed and
occupied-item transfers with any free donor replacement complement old retained
row combinations. Fixed4p/2+2 use the existing exact-additive pair seed; sparse
packages use the transfer lane, not that incompatible pair-seed DP. This remains
bounded joint local search, not an exhaustive nonlinear ten/twenty-slot solver.
Pair evaluations share the existing total expansion reservation. Current best
and retained rows survive a deadline inside a wearer/pair; arithmetic/provenance
errors still fail. All Sets source has ONE ordinary n500 finalist stage, without
n128/adaptive reruns; displayed uncertainty remains. Selected's search/finalist
policy and Theory's allocator have not been transferred.

Focused active-engine compiler gate: `TestParametricActiveEngineWitness` reads the
first retained `inventory_bound_poc_lineage5_v1.json` input without rewriting it,
checks the active pointer/path and executable/source binding, then calls the same
`NewEffectEngineProvider` as All Sets for exactly two captures. Config SHA256:
`75e95725b565a5065316873d4d16c420bd6d4ade9ac6f53407b3838518ba3220`.
There were ZERO ordinary simulator calls. At24 joint artifact/port changes and16
wearer specializations, max residual versus unreduced arithmetic was
`2.91038304567e-11` DPS. Nodes:144726 original,19464 with1058 independent ports,
3312 artifact-only whole-panel. Capture10.549s; preparation39.815ms with ports /
15.771ms artifact-only;24 parametric evaluations13.316ms versus49.244ms reference.
Sixteen specializations took24.094ms with retained preparation versus319.311ms
when rebuilding the NEW shared program each time. These are scoped compiler
measurements, NOT old/new full optimizer timing or proof of set response.

The14-package native suite and22 focused Python Selected/All adapter/managed
lifecycle tests pass. Added controls cover distinct/equal ports,
changing branch conditions after reduction, foreign owners, durations, gradients,
unknown no-prune behavior, region order, real occupied-item transfer and an
inside-wearer deadline. The old one-build budget fixture legitimately finished
without new work; its partial-budget test now has multiple real alternatives.
Generated gate output78,046,554 bytes (including compiler cache) was removed by
the managed runner; no completed job/capture remains. Test commands/lifecycle are
documented in TESTS and DATA_RUNTIME_BOUNDARIES. Original matrix/comparison logs
remain untouched. The approved producer implementation below owns the next layer;
changed-set response still precedes the tiny combined-effects/inventory oracle
and the single Flins product gate.

### Effect-producer preflight and stat-query identity (2026-09-20, source-only)

Current resume/acceptance: [GP-3](GCSIM_GOB11_GP3_CHECKPOINT.md). The user asked
to continue sequentially until implementation is ready for the agreed checks,
or a material user decision is needed. No product/matrix rerun this stage.

Two observer losses were confirmed in the active source, independently of set
ranking. `GTTStat` and `GTTNonExtraStat` called the same untyped
`RecordArtifactStatRead`. `GTTStatsOrigin` retained owner/values/modifier IDs,
but not the original query mode/time; later snapshot uses emitted new read
events at their use frame. This is insufficient for replacing timed/Extra
effects even when unchanged-package numeric response is correct.

The candidate `tools/experiments/gcsim/parametric_effects/stat_query_identity.patch`
adds a runtime-bound immutable `StatQueryContext` with distinct query identity,
original frame/state-sequence position and Extra-filter mode. Ordinary getters,
filtered getters, selected stat containers and saved snapshot total/stat refs
preserve it. Existing event fields carry typed channel/payload metadata; no
getter or modifier is re-evaluated for observation. Same-valued independent
queries remain distinct; later uses retain their shared original query. Existing
external-dependency uncertainty is NOT cleared. This does not expose complete
neutral stat ports or produce set activation/replacement semantics.

Focused command (selected active source only; no installation):

```text
.venv/Scripts/python.exe tools/managed_optimizer_experiment.py --timeout 180 -- .venv/Scripts/python.exe tools/experiments/gcsim/parametric_effects/check_stat_queries.py
```

Six tests across `pkg/gtttrace`, `pkg/core/info` and
`pkg/core/player/character` pass, including existing nested-modifier/NonExtra
controls. Ten Python `test_parametric_effect_gate` +
`test_managed_optimizer_experiment` tests pass. Zero captures/ordinary calls;
no changed-set response, whole search, UI or speed acceptance. The successful
managed job generated and removed140,674,766 bytes, including compiler cache.
Two setup attempts each removed76,411 bytes: the first rejected the installed
overlay's old staging path, then the second rejected an extra blank line in
the generated patch hunk. Both are invocation/patch-format repairs, not failed
semantic hypotheses. The runner relocates ONLY this selected installation's
recorded staging prefix inside its temporary overlay, rejecting other engines;
installed metadata/source/binary remain unchanged. No completed job remains.

The user subsequently approved neutral no-set capture, independent event/state
observation, bounded interpretation of the existing imperative source and an
explicit approximate-coverage fallback. Trace handoff section2 owns that
decision. The earlier declarative-engine rewrite proposal is superseded; do not
ask it again or rewrite ordinary set mechanics. Real output/action/source-RNG
changes still require the separate schedule route, not a named-set exception.

### Neutral events and source-rule implementation (2026-09-20, source-only)

Thirteen candidate patches in `tools/experiments/gcsim/parametric_effects/` now retain
query identity, subscription-independent event emissions with nested order,
zero-valued stat/attack ports before graph reduction, and interned world snapshots
of all character modifier keys/expiries. Snapshot and impact inputs have separate
times; attack-mod input is observed at its actual getter, resistance after
elemental reactions. Selected stat keys/Extra filtering and the query point
BEFORE Amount execution survive saved snapshots. Central hitlag observation
retains already-computed expiry extensions, even with no registered modifiers.
Direct totals of proved immutable selected-stat locals retain their original
query/filter/owner through saved-vector arithmetic; no getter is repeated.
Reflection copies bounded
event data; unknown fields stay explicit. World
observation calls no Amount/stat getter. Status-add logs alone cannot prove that
a modifier is absent. The native optional neutral ABI validates owners, nesting,
zero-node identity and world keys. Historical sidecars remain non-neutral-capable.

`check_stat_queries.py` applies the reviewed patches only to managed copies of
touched original AND already-generated source variants, preserving instrumentation
on overlay collisions. Use the managed wrapper with240s. The latest source gate
passes21 central controls plus five selected-stat generator cases and core
compilation. With no
extra option it makes zero captures/ordinary calls. The prior expanded gate first failed to compile because
the observer used `Moonsign` instead of the actual `GetMoonsignLevel`; corrected
before the passing12-test and then13-test gates. This was an API error, not a
failed gameplay hypothesis. Generated bytes removed by successive jobs:
141,372,114 (events),408,087,254 (compile failure),414,078,559 (ports),
415,877,444 (world). A separate native contract/client gate removed62,116,003.

The native `seteffects/rule_*` producer evaluates a bounded Go-AST subset with
lexical closures, struct versus pointer state, source enums/guards and event
registrations. It has no IO/arbitrary imported-code execution; budgets, unsupported
calls, ambiguous state, stateful Amount writes and untyped numeric division remain
explicit boundaries. The source-envelope producer binds event, modifier,
Nightsoul, weapon-class, reaction/target types and set-enum helpers ONLY with `include_neutral_rules=True`; default output stays
compatible with the installed strict consumer. No partial ABI activation.
Host seams model shared-key replacement/deletion, recipients and Extra/selected
stat filtering. A collision with a neutral weapon/character/target modifier
fails instead of leaving its old contribution additive. Mutating captured event
payloads also fails until its output is explicitly bound. Complete hitlag tapes
now reproduce modifier extensions; missing tapes retain an approximation warning.
Callback-phase coverage is still not a general hard-bound certificate.

`check_rules.py` uses the production active-engine loader/source-envelope producer
under the managed wrapper with180s. Language/lifecycle, thirteen active-source
synthetic-tape, timed/weapon, interface/aura and reduced-program controls pass.
Covered examples: inactive
Obsidian zero, Silken/Night team effects, VV Electro Swirl and Tenacity; duplicate
Silken EM is not doubled and incomplete state cannot certify inactive Obsidian.
These synthetic controls are NOT arbitrary set coverage. Both earlier source
jobs removed65,262,137 and65,315,201 bytes; initial
evaluator-only gate removed64,707,411. No completed job retained.

The explicit360s `check_stat_queries.py --capture-fixture` gate now reuses the
first `inventory_bound_poc_lineage5_v1.json` config and seed742031889. It preserves
all non-set bytes and initialization order. Neutral SHA:
`4196fbc24dd20a0a0a88400f32ae5e91acbc794e976b71a92173023d40896d5e`;
original control SHA:
`75e95725b565a5065316873d4d16c420bd6d4ade9ac6f53407b3838518ba3220`.
This tests a candidate overlay of the SELECTED source through
`RunGTTTraceEquation`, not a substitute installed engine or button acceptance.
The source manifest/binary, original logs and all live account state are unchanged.

First real neutral capture exposed a vocabulary defect: direct physical damage
uses legacy `physical%`, while the engine stat label is `phys%`. The neutral
producer now resolves it through the engine's `StringToEle`/`EleToDmgP`, not a
mechanics table. The failed job removed442,070,240 bytes. The corrected
single-capture gate passed; removed442,443,750 bytes. The synthetic Python adapter
test also needed its bound shortcut-registry fixture and request-owned timeout
assertion updated;13 focused tests pass. Both failed Python jobs retained0 bytes.
A runner-variable collision failed before capture and removed536,733 bytes.

The first independent positive-response diagnostic made TWO captures, not a
candidate loop: neutral2.434s and original sets1.984s. Neutral:6906 events,
567 world states,327 hits,4907 stat/attack ports, zero missing query orders;
sidecar10,827,209 bytes. Including effect/resistance ports:5441 inputs,
36904 prepared nodes,40ms preparation. Per package vector30-77ms, outside item
scoring; source parsing/decoding/build time is NOT included in those timings.
Inactive Obsidian on Flins/Ineffa leaves87708.580863 DPS unchanged. The four
control packages together predict144744.345060 versus independently captured
146403.005115: -1658.660055 DPS (-1.132941%), equal topology and72467ms duration.
This was a response DIAGNOSTIC, not acceptance or the n1000/ordinary144.7k result;
a test-runner PASS did not establish a permitted residual. This job removed450,604,459 bytes.
Earlier metadata/port-only gates removed416,132,402 and65,464,913 bytes.

Per-channel attribution identified two independent losses. VV expiry lacked
hitlag extension: observing and replaying the engine's already-computed extension
reduced the gap to310.460482 DPS (-0.212059%); direct hits then matched. Remaining
reaction loss came from `ineffa/asc.go`'s local `SelectStat(true)`/`TotalATK()`:
the saved-vector rewriter froze that scalar, so Tenacity ATK did not flow into
the EM buff. Generic selected-local total provenance fixes this without changing
gameplay or naming a character in the producer. Mutated/aliased/escaped locals
remain unsupported. The refreshed generated overlay changes only Ineffa's file.
Regeneration checks all source entries/templates and immutable binding against
the installation; the pre-build whole-directory hash naturally differs after
post-build receipts are added and is never rewritten by this source-only gate.

Eighth-patch same-seed result: neutral2.359s/control2.145s;6906 events,567 world states,
327 hits,5033 stat/attack ports (126 non-extra), no missing orders;
sidecar10,867,998 bytes. Total5567 ports/37807 prepared nodes,31ms preparation,
30-122ms per package vector (not source parsing/build/decode/end-to-end time).
Neutral87708.580863, inactive Obsidian unchanged; combined control146403.005115
equals independent146403.005115. Every channel matches to roundoff. The regression
now requires equal topology/duration and absolute aggregate/per-hit residual
<=1e-8 DPS. This is one four-package fixture response, not arbitrary-package,
ordinary simulation, inventory-search or UI acceptance.
Attribution/hitlag jobs removed450,630,275/267,011,521/451,181,385 bytes;
the middle job was a TargetKey-to-int compile error. The generator helper's first
whole-directory identity check failed before any capture (64,746,048 bytes
removed); entry/binding checks explained above then passed. Final job removed
456,657,138 bytes. No expanded job/source/cache remains.

`rule_scalar.go` now preserves stat-dependent arithmetic/caps and explicit
non-set stat leaves with owner, Extra filter, frame and order. Only pure local
numeric branches are merged; callback/lifetime/output-dependent branches fail.
Stateless writes into a proved returned scratch vector are copied/restored;
cached counters, old-cell reads and other captured mutations still fail. No
per-item AST replay. The real Emblem source passes four supplied ER inputs,
including its own2p20% and75% cap; a non-burst query yields zero. Unbound reads
are not zero and the legacy constant-vector route refuses them. The constructor's
parameter map now has its actual integer zero-value type. Source gate removed
67,023,260 bytes; no simulation.

`formula/effect_expression.go` can bind effect DAGs into the ALREADY reduced
program and then specialize wearers. Optional, graph-verified read roots survive
reduction without entering the DPS sum. Unknown inputs and dependency cycles fail;
cross-owner inputs/caps remain variable. Three new math controls and the existing
formula/evaluator/seteffects suites pass;68,924,817 bytes removed. A separate
focused Python helper/source-adapter run passes9 tests and retained0 bytes.

The ninth patch retains already-evaluated neutral stat vectors as disconnected
read roots, without new getters or adding them to damage. Direct set inputs are
excluded from these roots to avoid double counting; nested non-set buff ancestry
keeps its ports. Non-extra projections subtract recorded Extra contributions and
are explicitly approximate. Missing/truncated/foreign/future roots never become
zero. Source expressions bind the latest preceding compatible root; prior-query
and selected-filter projections stay visible. One same-seed gate passes the
strict aggregate/per-hit response assertions above. It retains21909 read roots,
5197 stat/attack ports (290 non-extra),5731 total ports/39274 prepared nodes;
sidecar16,028,151 bytes, neutral3.002s/control2.032s, aggregate preparation50ms.
Emblem-Ineffa on the SAME reduced graph changes87988.816595 ->88201.599990 DPS
with +1 artifact ER (3254 bound nodes). This is arithmetic binding, not an
independent Emblem response or search result. Managed job removed469,804,892
bytes; no capture/source/cache remains.

The tenth patch observes actual weapon class/refinement, Hexerei and
`NOCharIsSpecial` initialization facts without a character-name table. Source
replay now matches replacement/unsubscription and original-slice emission;
constructor party visibility and source enum order match Core.AddChar/Init.
Bounded source-only timers model modifier state, not attacks/RNG/actions; unknown
task phase/character hitlag timing remains approximate. Query-local Amount memo
avoids evaluating the same stat vector once per component. Scratch cell compound
writes require a preceding write in the same call. Read roots are indexed by
owner/stat/filter/order, not rescanned per leaf.

The eleventh patch observes actual target interface membership and aura states.
Concrete-type inequality previously could become a false interface guard;
missing implementation evidence now fails explicitly. No target is guessed to
be Enemy. The twelfth patch disables neutral-only event/world/read/hitlag
observation before character setup whenever the config retains sets. Ordinary
query provenance remains enabled; Selected does not pay for the neutral tape.

The earlier twelve-patch fixture gate (`job-jejri8nf`): neutral3.295s/control1.700s,
572 world states,16,454,954 sidecar bytes;327 hits,21909 roots,5731 ports and
39274 prepared nodes unchanged. Preparation51ms; full four-package vector127ms,
not end-to-end timing. The strict response above still passes. The optional
single-tape audit binds275/336 owner/tier choices (84 approximate),61 unresolved
in12.865s. Coverage is not response proof; this count predates the collection
and whole-schedule checks below.

Managed cleanup since the ninth-patch gate: initial catalog/subscription test
469,879,752 bytes (test used forbidden mutable package globals); timed source
67,491,945 (missing weapon fact/test context) then67,504,843 PASS; tenth-patch
coverage470,076,080 PASS. Eleventh patch had one nil-versus-empty world-interning
test failure (464,183,845 removed; captures completed but overall gate FAILED),
then the twelve-patch gate passed and removed471,143,894. A patch-header invocation
error before execution removed592,368. No completed scratch remains.

`evaluator.ParametricView` and `setcontext.NeutralModel` now bridge the retained
aggregate to the existing inventory solver, without re-reading hit IR. Evidence
ownership transfers once; parameterized sets remain an explicit unsupported
boundary. Bound handles use a distinct route, cannot lend a stale energy ledger
and cannot return the neutral panel's old actor/channel detail. Approximate
arithmetic keeps a finite ordering potential but Upper remains infinite; model
priority is never a hard-pruning proof. Formula/evaluator/search/setcontext suites
pass (71,112,514 disposable bytes removed). The product coordinator is unchanged.

Rule-component composition passes scoped controls: retain run-local constant source
responses only with noninteracting read/write/subscription footprints; shared
keys or stat-dependent reads use joint replay. Sum raw resistance changes before
the source resistance curve. Initial synthetic source test lacked character
element metadata in one chosen package (71,707,519 removed, failed gate); use a
metadata-independent2+2 control. The corrected gate plus the real bridge pass
(`job-r5azwq6a`,475,262,098 disposable bytes removed): transfer is one-way,
parameterized choices stay unknown, changed contexts cannot borrow neutral energy
evidence, and approximate models cannot prune. Resolving the four control packages
takes253.488ms first and23.058ms on retained components, with146403.005115 DPS
preserved. This includes effect binding/reduction, not capture/source preparation,
inventory search or ordinary verification. No product speedup is claimed.

`allsets.RunNeutral` now supplies one capture panel to feasible none/single2p/
2+2/4p models, real-inventory upper potentials, new-model gradient seeds,
wearer refinement, whole-package permutations and physical-ID pair transfers.
The initial fixed-package reference is a cheap seed, not four full searches
before coverage. No old raw-context guide or named-set shortlist selects the
queue. Shared work limits include potential evaluation; per-pass counters retain
unprepared and unprocessed packages on expiry. Unknown rules are reported, not
scored zero. This source coordinator is NOT called by the CLI/button yet.
Finite-energy binding, parameterized sets, unknown initial packages and true
schedule alternatives remain explicit unsupported routes. Greedy multi-wearer
reservation failures are deferred, not declared impossible; coordinate stability
is not a global optimum and partial item regions remain in step reports.

The new combined oracle has five items per slot and four wearers; only actor-A
HP enters the synthetic damage graph, with effects read from actual installed
set sources. Independent5^5 enumeration agrees at25.475; five strong unmatched
items win the no-bonus case. One fake capture panel only,20 distinct legal IDs,
33 modeled queue entries (814 units after union potentials;1048 before); source controls also pin
whole-run limits1/3/24 and incomplete-coverage counts. This is not account DPS.
Initial malformed test data repeated a main stat as a substat, then had an
unsorted commutative IR input; neither failure reached search. Jobs removed
75,207,550 and75,207,434 bytes. Corrected oracle/budget controls pass; a
prior compile/old-suite gate removed71,579,388. Subsequent source-only gates
removed75,207,434,75,264,422,75,439,019,75,473,373 and75,522,032 bytes.

Source collections are admitted narrowly: a map loop can only register distinct
event kinds under read-only captured state, with no early exit; arbitrary map
order is not invented. Typed nested literals, source enum String keys and pure
slices.Contains now work. Cached returned struct-field stat vectors can be
cleared/reassigned in Amount and are restored; aliases/shadowed clear/stateful
writes still fail. Actual Scroll tests distinguish12%,40% and unrelated-element
zero. A symbolic piece-count tier requires every executed comparison to agree
for2/3 or4/5 pieces; count arithmetic or differing branches cannot be frozen.

The thirteenth observer exports the actual final frame (bound to member duration).
Replay inspects events/timers AFTER the last neutral damage port through that
frame, not beyond it: delayed new output cannot become zero. Activated attack
speed vectors also require a schedule route (`internal/frames` reads AtkSpd for
action length); inactive registrations alone do not trigger that boundary.
Tail-output, horizon/identity and active-versus-inactive speed controls pass.

Thirteen-patch gate `job-pqjqcqr0`: neutral3.379s/control1.776s,
16,454,977 sidecar bytes; response146403.005115 and every hit still agree to
roundoff. Single-tape audit at that gate:279/336 bound,88 approximate,57 unresolved in
12.430s (before the subsequent conservative speed classifier control).
Remaining APIs include shields, target/core status, energy and real
output/cooldown/RNG. Bridge binding421ms first/35ms repeated is preparation,
NOT optimizer time. Removed478,991,084 generated bytes; binaries unchanged.

Bounded scalar addresses now preserve live read-only external frame references
and distinct local pointer identity across queued callbacks. Comma-ok maps and
helper-call-local Amount counters work; writes through captured/external pointers
remain forbidden, as do symbolic merges across addressed local bindings.
The opt-in library envelope includes the actual `pkg/core/stacks/refresh.go`.
LongNight source controls cover2p, stack cap, overwrite identity, timed expiry
and unrelated hits. No stack mechanic is copied into the consumer. The first
new fixture supplied AttackInfo instead of AttackEvent; corrected fixture passes
(`job-o0m3j66_`75,685,232 bytes removed; `job-c3nkpaat`75,682,954 removed).
Previous whole-native14-package/CLI tests also pass (`job-ci4me2s0`,84,944,209
bytes removed); Python source/gate checks pass6 then7 after the profile safety
test addition (`job-jm50ekdp`, `job-84u1a_p4`, no generated bytes).

The explicit `--capture-fixture --inventory-profile` diagnostic reuses ONE saved
seed's neutral/control pair and the read-only current inventory, after checking
all20 physical reference vectors and packages. It profiles RunNeutral for60s;
it is not a product acceptance/144.7k recall test and starts at the saved strong
reference. Model rule/binding/view costs, seed work and potential work are split
out (seed/proposal timings include nested model work). Partial preparation time
is retained on expiry. Request/captures stay inside the existing managed job;
the cleaner and path/reference-preservation tests own their lifecycle. No new
persistent inventory copy or old-log overwrite is introduced.

The first60s profile (`job-3gpudygr`) exposed eager preparation, not a quality
pass:587 items,2096 wearer/package proposals; only463 prepared/461 queued,
zero refined. Preparation57.653s included potential43.412s, seed14.334s,
source rules3.116s and binding10.132s. Initial/leader146403.005115 is the GIVEN
strong witness, not a found improvement. Source capture3.170s/control1.751s;
the saved response still passed. Removed479,638,653 disposable bytes.

`PotentialUnion` now traverses the damage graph once over all legal slot
patterns. A support direction selects complete real vectors from interned
slot/family pools and then the best allowed pattern; no independent-stat
fictitious item and no mean-item ranking. Its nonlinear remainder can be
looser than per-pattern bounds, so regional refinement remains necessary.
A run-local64-entry/128000-node FIFO also shares strictly identical FULL
constant effect vectors after source activation/interaction checks. Dynamic
expressions bypass it; each view retains private scratch/proof state. Unit
gates `job-pjl3866y`/`job-6m8iq6n9` pass and removed72,968,963/74,703,749 bytes.

Same60s profile after these changes (`job-cyekk598`): all2096 prepared,
2079 queued,17 source models unavailable; preparation37.466s, potential12.991s,
seed24.514s, rules13.429s, binding5.515s,1913 exact-vector cache hits/173 misses.
Only ONE proposal completed refinement,2078 remained: the next bottleneck is
atomic per-package20k refinement, not missing package preparation. Leader
remained the supplied146403.005115. This is neither a recall nor a whole-pipeline
speed pass. Neutral3.159s/control1.717s, per-hit response still roundoff;
removed479,784,203 bytes. The preparation comparison covers different completed
counts, not equal work.

The neutral coordinator now retains resumable inventory frontiers in ONE
cross-package queue. A bound or at most64 complete attempts yields control;
resumption retains region offsets/seen IDs rather than restarting refinement.
The1/7/64-slice controls match the atomic small-domain result with identical
total work; cancellation retains pending regions and a legal improvement
(`job-ixs1kf81`,62,729,828 bytes removed). Invalid complete points consume work.
Within each coordinate pass, anchors remain fixed. Independent wearer winners
can form a legal JOINT proposal, but the complete new effect vector is scored;
individual DPS gains are never added. Conflicting IDs require a new allocation.
The pair stage directly invokes donor replacement instead of repeating four
atomic wearer searches. Small source oracle remains25.475 with123 work units
(`job-s9cfwvlp`,76,102,588 bytes removed). This is still not global joint proof.

If the queue's highest MODEL potential falls below the incumbent, remaining
packages are model-deferred: no hard-pruning counter or response certificate.
They remain in Pending and explicit ModelDeferred counts, including unstarted
frontiers. A later coordinate pass reconsiders them at its new anchor. Ordinary
finalist fidelity/budget is not enlarged by these model uncertainties. Exact
local hard pruning still requires that frontier's own supported bound.

Same60s profile of that scheduler (`job-tof46ui6`) still did NOT reach joint
exchange:2096 prepared/2079 queued/17 unavailable,0 completed,2079 pending,
14252 work units; preparation37.304s, potential12.909s, seed24.380s, rules13.549s,
binding6.042s. Leader is again the given146403.005115. The most expensive open
frontier was Ineffa/no-bonus:3.272s,1257 work,3036 reduced nodes and a relaxed
pending region count19,530,201,600. Work now interleaves packages but their
coarse potentials still keep refinement active. Inventory canonical SHA256:
`a9600392c812f58d5504f1bd390f86c027e2eb6bb9acb606728027345c5fa283`.
Neutral3.150s/control1.770s; saved per-hit response unchanged. Removed479,997,611
generated bytes. This profile is diagnostic, NOT a pipeline-speed/recall pass.
The next bounded repair intersects affine supports with source-operation
intervals at each node. Joint affine item support remains; interval arithmetic
preserves clamp signs and limits nonlinear remainder. Finite interval fallback
handles sqrt(max(0,x)) at zero despite its singular derivative. Random signed
branches, caps, long products, real-vector oracles and singularity/no-prune
controls pass (`job-1k15dz7l`,72,828,231 disposable bytes removed).

Its SAME60s profile (`job-6vhne0xp`) is a PERFORMANCE REGRESSION: preparation
48.669s (seed24.822s, potential23.831s),4984 work,2096 prepared/2079 queued,
17 unavailable,0 completed/2079 pending, no model deferrals and no joint stage.
Rules13.702s/binding5.824s; inventory hash and given146403.005115 leader unchanged.
Neutral3.186s/control1.788s; strict saved response still passes. Removed480,040,690
generated bytes. Mathematical unit success is not search/pipeline acceptance.
The hybrid currently remains in this SOURCE-ONLY draft, never deployed.

**Historical stop gate (superseded by user approval below):** the baseline plus three bounded performance repairs
(union/cache, resumable scheduling, hybrid enclosure) have not met the60s
whole-offline-stage diagnostic criterion. Per CODEX, do not silently attempt a
fourth repair. Await explicit user approval. The first unresolved cost is now
expensive bounds evaluated eagerly for every package, followed by refinement
that still delays joint proposals. No quality/108k-to144.7k recall claim is made:
these profiles start from the strong witness and contain zero ordinary calls.

Rejected/superseded next hypothesis (never implemented): compute a
cheap conservative source-operation interval for every feasible package first;
only refine the currently most promising queue regions with the expensive
joint-vector/hybrid bound. Keep all unvisited packages and approximation flags;
no name/stat shortlist. Score legal combined-wearer seeds and actual donor
replacement before long regional refinement, so complementary improvements can
raise the incumbent early. Risks: a cheap interval may still be too loose, and
early joint proposals are not global joint optimization. Repeat the same60s
profile only after approval; do not compensate by enlarging its budget.

User subsequently approved a different implementation: direct real-candidate
scoring, priority by found DPS and top-five/gap heuristic deferral. It replaces
the eager bounds on RunNeutral only. `search/candidates.go` uses a full linear
seed and five single/five paired exclusions for the screen; the spread rule
requires five distinct scored probes and a paired probe, with twice the observed
range as a heuristic safety margin. It is NOT a bound/confidence interval.
Refinement refreshes gradients, checks one/two-slot moves over per-category
shortlists, and directly enumerates domains of at most4096 raw combinations.
Five refinement rounds and the existing item/work budgets cap this prototype;
no zero local weight proves a useless stat or permits inventory deletion.
Joint donor replacement runs before deep queue processing. All feasible package
screens remain required; genuine unknowns and ID reservation failures are separate.
Heuristic skips and sampled neighborhoods remain unresolved in coverage. Source
support/full-vector caching is reused, not assumed to make inactive sets illegal.
The old enclosure implementation remains available to old callers, but this
source coordinator makes no bound evaluations. Selected/Theory are unchanged.

Initial focused checks: malformed added test substat ordering stopped the first
test before search (62,931,035 bytes removed); a leftover unused capture timing
variable stopped the next coordinator build (74,763,391 removed). Corrected
source/candidate gates pass (`job-1h76xjzc`,77,697,920 removed): tiny exhaustive
candidate parity, cancellation/incumbent, work limits and heuristic evidence
requirements; source-bound5^5 oracle25.475 in0.250s/710 work, no numerical bounds.
The profile now starts from saved `virtual_top1` physical IDs, preserving the
strong capture's coordinate reference. Restricted witness-union then full
inventory are separate60s searches on the SAME source capture, never an initial
strong incumbent. Restricted model recall must pass before expansion. Diagnostics
now print exact unknown package/reason boundaries, initial IDs and final packages.
### 2026-09-20 real-candidate search: restricted then expanded weak-start gate

Source job `job-edkkym2r` reused the selected source and one saved neutral
seed742031889. Neutral/control SHA values above remain unchanged; source
response146403.005115 still matches every original-set hit. Actual capture costs
5.509/1.870s; all481,585,727 generated bytes were removed. These source checks
use the13 observer overlays, NOT a deployed optimizer replacement.

Both searches START at the same saved `virtual_top1` twenty IDs, model DPS
108999.110558. The strong reference is NOT inserted as an incumbent or candidate.
The28-item domain is the union of weak/strong witness items; after its recall
gate passed the same algorithm searched all587 account items. Neither the
original matrix nor Gaming was rerun.

| Domain | Offline coordinator seconds | Found one-seed model DPS | Ordinary n500 DPS | SE |
| --- | ---: | ---: | ---: | ---: |
| Restricted28 | 10.616612 | 147084.493462 | 145210.906503 | 128.727142 |
| Full587 | 60.002615 | 148934.356170 | 147160.450991 | 136.153943 |
| Saved strong control (not searched) | n/a | 146403.005115 | 144625.550417 | 191.674370 |

The restricted run completed both scheduled passes (112 package proposals each);
74/72 reservation deferrals,38/40 modeled queues,36/33 exact tiny refinements and
2/7 heuristic skips. Reservation failure under fixed other wearers is not global
impossibility.1213 scored work units; joint exchange0.046296s. Queue coverage does
not prove global twenty-item optimality.

Full inventory canonical SHA:
`a9600392c812f58d5504f1bd390f86c027e2eb6bb9acb606728027345c5fa283`.
First pass attempted ALL2096 packages:17 unknown,2079 scored,1786 gap-deferred,
293 sampled refinements, joint exchange reached. Second pass prepared831/2096
(4 repeated unknown requests), then timed out; it did not finish or revalidate
every deferred region under the new anchor. Total208477 scored work units,
40.140713s proposal/screen preparation,0 numerical-potential time,0.098778s joint
work. Model3247 requests,2924 exact-vector hits/302 misses; rules16.966983s,
binding10.252464s. These preparation values cover MORE THAN ONE PASS and cannot
be directly presented as a speed ratio against the old37.3/48.7s one-pass values.
The new result establishes scoped recall, NOT complete pipeline/time acceptance.

Exact assignments below use wearer order Columbina,Flins,Ineffa,Jahoda and slot
order flower,plume,sands,goblet,circlet. Raw vectors remain in account inventory;
the immutable source/profile fixtures identify the comparison and reference.

```json
{
  "initial": [
    [
      1395,
      1598,
      8,
      1563,
      1614
    ],
    [
      120,
      219,
      68,
      1566,
      124
    ],
    [
      80,
      81,
      1576,
      88,
      1578
    ],
    [
      1588,
      57,
      58,
      1545,
      165
    ]
  ],
  "restricted": {
    "inventory_sha": "8d53af2a0eb888ba3ffcbbb24275a5b950bca3280a30ca23175a588a1fcb28c9",
    "ids": [
      [
        1395,
        1598,
        8,
        1563,
        1614
      ],
      [
        1,
        1533,
        63,
        1566,
        1565
      ],
      [
        120,
        219,
        68,
        88,
        124
      ],
      [
        1468,
        1472,
        1474,
        1590,
        165
      ]
    ],
    "packages": [
      [
        {
          "set_uid": "tenacityofthemillelith",
          "count": 4
        }
      ],
      [
        {
          "set_uid": "nightoftheskysunveiling",
          "count": 4
        }
      ],
      [
        {
          "set_uid": "silkenmoonsserenade",
          "count": 4
        }
      ],
      [
        {
          "set_uid": "viridescentvenerer",
          "count": 4
        }
      ]
    ]
  },
  "expanded": {
    "inventory_sha": "a9600392c812f58d5504f1bd390f86c027e2eb6bb9acb606728027345c5fa283",
    "ids": [
      [
        66,
        67,
        8,
        69,
        1580
      ],
      [
        1537,
        1534,
        63,
        64,
        1565
      ],
      [
        71,
        72,
        73,
        1566,
        1567
      ],
      [
        1468,
        1472,
        1474,
        1590,
        165
      ]
    ],
    "packages": [
      [
        {
          "set_uid": "silkenmoonsserenade",
          "count": 4
        }
      ],
      [
        {
          "set_uid": "nightoftheskysunveiling",
          "count": 4
        }
      ],
      [
        {
          "set_uid": "aubadeofmorningstarandmoon",
          "count": 4
        }
      ],
      [
        {
          "set_uid": "viridescentvenerer",
          "count": 4
        }
      ]
    ]
  }
}
```

The first-pass17 unknowns are now actually identified (not inferred from the old
count): Maiden4, Nighttime Whispers4, Shimenawa4 and Song of Days Past4 on each of
the four wearers, plus Archaic Petra4 on Ineffa. Reasons respectively:
`AddHealBonusMod` not interpreted; unobserved event payload; unknown energy value;
core-status `Duration` not interpreted; unobserved shield/event payload.
Full canonical UIDs are `maidenbeloved`, `nighttimewhispersintheechoingwoods`,
`shimenawasreminiscence`, `songofdayspast`, `archaicpetra`.
The expanded total21 unavailable REQUESTS includes the four repeats for Columbina
in pass2; it is not21 distinct sets. No unavailable effect was assigned bonus0.

Independent ordinary job `job-ptuxpyt5` checked the two found leaders and saved
strong control, ONCE EACH at n500 with4 workers, through
`run_active_gcsim_artifact` and the ACTIVE installed `build/gtt-gcsim.exe`.
SHA `9d107ed713a171c64509ce35348c5d8f7bc08d81bea785db0f308b46d8869d50`.
All non-artifact config SHA values:
`2ec05b9f19cf8c04ba9854039924315543b19e7be317963156d4b6d050d55d23`.
Restricted/full/control config SHA values, respectively:
`b860dd43e8002329fc2b439c581f612d4e05d975d393394f4e3d97d6b897fbd9`,
`1b33f4adc67b2a8dd877a1da5ea5e1ee20e00a45a41f0c087f1d3c619dc116af`,
`75e95725b565a5065316873d4d16c420bd6d4ade9ac6f53407b3838518ba3220`.
Case preparation+ordinary times9.088193/8.865889/8.880538s; duration72.466667s
and all four failed-action summaries are identical across cases, with zero
energy/stamina failures.387,678 generated bytes removed. Candidate-minus-control
DPS is+2534.900574 (+1.753%). Original n1000 receipts remain untouched.
The one-seed model versus ordinary mean differs by about1.2%; ordinary results,
not the model's148934 figure, are the measured outcome. There is no per-candidate
capture, extra n128 stage or widened verification loop.

Gate helper tests pass6 cases (`job-tx8tb3vg`,0 generated bytes). The added
paired-valley control initially assumed an absent fixture substat and stopped
before search (`job-w5bvdv22`,71,728,392 removed); its correction changes only
synthetic input construction. A cancellation-only coordinator fix also ensures
a partial screen improvement retains its updated physical index. Normal completed
profile paths are unchanged. Final focused gate `job-1h_d4uyu` passes all three
candidate tests, including a domain above the exhaustive cutoff where both
single changes lose but their paired change wins; allsets also compiles.
71,739,118 generated bytes removed. Handoff structural checks pass after compacting
only the optimizer TODO section; unrelated concurrent work remains preserved.

### 2026-09-20 resource API completion and untimed two-pass diagnostic

Current authority remains GP-3. The user requested implementing the17 missing
wearer/package cases and measuring completion without the shared60s search
deadline. No ordinary set code, active installation or product budget changed.

Implementation: `rule_resources.go`, the additive `neutral_resources.patch`,
source-library binding and strict neutral-input decoding. The14th observation
overlay exports shield type/element/expiry, construct type/position, player
position, core status expiries/custom flags and energy scalars. It does not
execute stat getters, modifier amounts, tasks or RNG to discover those facts.
The consumer still executes the installed set source for amounts and guards;
shield/construct source enums are now included in the bound library envelope.

- Maiden:2p remains outgoing `heal`;4p is a separate per-recipient `heal_bonus`
  input in the existing reduced health formula, not an outgoing-stat alias.
- Whispers/Petra: source rules read actual shield types and lunar construct
  proximity. Ineffa's shield does NOT trigger crystallization bonuses. Pickup
  already reaches the engine's `OnShielded` event; no unconditional pickup/full-
  uptime fallback is needed on this tape. User-approved reaction+skill fallback
  remains a possible explicit approximation if pickup facts are missing later.
- Shimenawa: source energy guards/timers/attack-tag filtering execute. Observed
  pre-cap energy gains and source debits are clamped to the observed capacity.
  Candidate ER can change activation, and new energy callbacks are not reemitted:
  both are disclosed approximations. Finite-energy changes remain a schedule
  boundary; the source neutral coordinator still rejects finite mode.
- Song: global status timers and shared custom counters execute source code.
  Additive `OnEnemyHit` FlatDmg writes go to an explicit hit-ID-bound zero port
  retained in the reduced formula. Non-additive or unbound writes still reject.
  Healing-event amounts remain frozen to the captured build for activation/
  accumulation, with an explicit uncertainty code. This is NOT exact arbitrary
  healer-stat response or a proof of new health-dependent schedules.

Generic source controls check no/expired healing bonus; foreign/crystal shields;
near/far lunar constructs; low/high energy; no-heal/accumulated-heal Song damage.
Source-specific detail: Whispers starts its lunar ticker before adding its first
skill modifier, so the first skill alone does not start that ticker in this
engine implementation. The near/far control uses a second skill during the
active window. Do not replace the source behavior by an assumed100% bonus.

Completion command: managed `check_stat_queries.py --capture-fixture
--inventory-profile --finish-passes`, outer900s watchdog/native600s safety limit.
`SearchTime=0` disables ONLY the coordinator deadline; cancellation,8m work ceiling,
two configured cycles and sampled-neighborhood limits remain. This is a measured
two-pass completion test, not convergence or exhaustive global optimization.

Successful job `job-6j6rwaap`: same seed742031889, neutral/control configs, weak
start, reference and both inventory hashes as above. Neutral/control capture
5.723/2.181s;6906 events,808 interned worlds,327 hits,21909 read roots. The four
original packages still predict146403.005115 and match every independent control
hit to roundoff. Zero ordinary simulations in this task.

| Domain | Search seconds | Model DPS | Unknown requests | Scored work |
| --- | ---: | ---: | ---: | ---: |
| Restricted28 | 10.517871 | 147084.493462 | 0 | 1213 |
| Full587 | 115.352460 | 148934.356170 | 0 | 563633 |

Both leaders are EXACTLY the twenty IDs and package lists in the prior receipt.
Reuse its ordinary n500 results145210.906503/147160.450991 versus144625.550417
control; they were NOT rerun. The extra time did not improve the leader. This
comparison also includes the resource repairs, so it is not a clean isolated
speed benchmark of the same code with two timer settings.

Full inventory pass1:2096/2096 prepared/scored,308 sampled refinements,1788
heuristic skips. Pass2:2096/2096 prepared/scored,471 sampled refinements,1625
heuristic skips. Both have zero not-prepared, not-processed or model-unavailable
rows. All17 old cases now score on this tape, not necessarily exactly. The
reported4192 pending regions are non-exhaustive/heuristic coverage markers,
NOT unfinished queues or timeouts. Stop `neutral_cycle_budget` means both
configured cycles ran; it does not prove stability after a third cycle.

Full preparation58.288273s (seed/screen58.215976s), zero bound/potential time;
joint0.340149s. Model5022 requests,4499 exact-vector hits,523 misses; rules
23.573035s, binding18.980782s, view0.666063s. Nested timing counters overlap:
do not add them to preparation or call115s the full application runtime. Capture,
source/test compilation and ordinary finalist measurement are outside it.
This receipt identified repeated preparation/anchor invalidation as the next
performance target; the following exact-reuse receipt supersedes that next step.
CLI/provider integration and the one Flins product/button gate remain separate,
retaining healing/ER and schedule caveats.

Lifecycle: first source control setup lacked bound shield enums and stopped
before the new cases (`job-j9nxk2o8`,78,019,835 bytes removed). After adding the
source libraries, controls passed; the sparse observation patch application
needed explicit sparse-hunk handling (`job-whfl5qa1`,78,723,462 bytes removed),
with zero captures. The successful complete profile removed484,820,817 bytes.
No expanded sources, raw captures or new output roots were retained. Original
matrix SHA remains00a0cd81711081e867faf06cad9230471ada6c4ecd956104181a69187231a152.

Post-profile hardening adds resource snapshot/export non-aliasing, validation of
resource payloads and bound heal/flat ports, and Point.Distance's source arithmetic
order. These are focused controls, not a second inventory timing sample.
Final managed job `job-qak8_zcx` passed the observation, native source/resource,
neutral-input and candidate controls plus all8 focused Python harness/source-
envelope tests. It made no captures or ordinary simulations and removed
443,020,846 temporary bytes; no managed job directories remain.
Installed consumer/engine, Selected/Theory, account/equipment/settings and
physical UI acceptance remain unchanged; no full top-five ordinary ranking or
two-seed production speed claim is made.

### 2026-09-20 exact preparation reuse

Current authority remains GP-3; this is SOURCE ONLY. No engine patch, installed
consumer, deadline, candidate width, package list or heuristic threshold changed.

- `formula/specialization_cache.go`: a NeutralModel-owned FIFO reuses reduced
  arithmetic only for the identical immutable source program, variable-coordinate
  mask, exact IEEE fixed inputs and proof/uncertainty status. Variable-wearer
  anchor values are irrelevant to that reduced function, but fixed teammate
  values and effect inputs are not. Every result has private evaluation scratch.
  Limits reuse the existing64-entry/128000-node policy; node accounting includes
  pinned source programs as well as reduced programs. Eviction only loses reuse,
  never search work. No persistent cache or generated-output root was added.
- `domain/package_linear_plan.go`: prepare weighted real-item family/slot rows
  once for the eleven screening probes. Exclusions choose the next real item;
  the exact existing4p/2+2 and sparse no-bonus/single2p matchers are unchanged.
  Occupied IDs, negative/equal weights and canonical tie handling remain intact.
  Selected does not opt into either optimization.
- Controls compare the planned matcher against repeated inventory scans on
  synthetic inventories/reservations/exclusions. Cache controls compare values
  and gradients, changed teammate/effect/owner/source identities, private scratch,
  approximate-proof isolation, invalid inputs and bounded eviction.

First complete managed job `job-5nrsxg64` passed source/observer/native controls
and the same restricted28/full587 weak-start Flins profiles. Neutral/control
capture3.482/1.600s retained the prior config identities and evidence dimensions.
Restricted6.545063s/model147084.493462/work1213; full90.138174s/model148934.356170/
work563633. Full preparation41.855089s; specialization reuse4179 hits/810 misses,
20 retained entries/125858 conservatively counted nodes. Both passes retained
the exact prior2096-proposal coverage,308/471 sampled refinements,1788/1625
heuristic deferrals, zero unknown packages and all twenty leader IDs. Original
115.352460s came from a separate run, so its25.214286s difference is NOT an
isolated algorithm-only speed claim. The job removed487,643,650 generated bytes.

`check_stat_queries.py --capture-fixture --inventory-profile --finish-passes
--compare-preparation` adds a controlled paired measurement inside one managed
job. Its narrow consumer overlay disables only these two reuse paths; it does
not restore old engine builds or touch installed/workspace sources. Both modes
use the SAME two captured inputs and serialized inventory, with no internal60s
deadline. Each runs restricted then full; all recorded work rows (without
clocks), coverage, model counts and the complete finalist list must match.
`WorkSHA` hashes the recorded coordinator work, not every transient scored leaf.
The helper refuses unmanaged execution/source-target drift, cleans with the
existing job and makes no additional captures or ordinary finalist simulations.
The full existing domain/formula/search suites run before the paired profiles.

Paired job `job-p4ecgyip` PASS (same configs/inventory hashes and seed as above):

| Domain | Reuse off seconds | Reuse on seconds | Off/on preparation seconds |
| --- | ---: | ---: | ---: |
| Restricted28 | 6.3683213 | 6.2465358 | 2.6448188 / 2.6039715 |
| Full587 | 96.4062333 | 89.3880345 | 48.3165613 / 41.9822064 |

Full search saved7.018199s (7.280%); preparation saved6.334355s (13.110%) in
this ONE paired comparison, not a cross-device or end-to-end guarantee. Rule
evaluation18.817121/18.983191s and binding15.561961/15.647694s were essentially
unchanged; these are separate remaining costs, with overlapping phase counters.
Reuse on recorded4179 specialization hits/810 misses; retained20 entries/125858
nodes. No changes to coverage, work counts, original/leader scores, package choices,
unknowns, complete finalists or recorded-work hashes. Both modes completed their
two configured cycles, not a global optimality proof.

- Restricted work hash: `0f15b24cd5491706196024dbf2b8e60c268b0e2170d7d9be742877da0aef2a16`.
- Full work hash: `2696e0792f50e44124fa2d157455ab6776bde673ee6daea957b1d3820c15da9d`.

The following full587 finalist rows were identical in both modes (model DPS,
not fresh ordinary measurements). Actor/slot order remains the prior receipt's
Columbina/Flins/Ineffa/Jahoda and flower/plume/sands/goblet/circlet:

| Rank | Model DPS | Twenty physical IDs grouped by actor |
| --- | ---: | --- |
| 1 | 148934.35617029207 | `[66,67,8,69,1580]; [1537,1534,63,64,1565]; [71,72,73,1566,1567]; [1468,1472,1474,1590,165]` |
| 2 | 148135.86314672744 | `[1395,1598,8,1563,1614]; [1537,1534,63,64,1565]; [120,219,68,1566,124]; [1468,1472,1474,1590,165]` |
| 3 | 145036.81659232764 | `[1395,1598,173,1563,1436]; [1537,1534,63,64,1565]; [71,72,73,1566,1567]; [1468,1472,1474,1590,165]` |
| 4 | 143876.25818584466 | `[1395,1598,8,1563,1614]; [1537,1534,63,64,1565]; [31,1344,1343,1566,35]; [1468,1472,1474,1590,165]` |
| 5 | 143818.27033495856 | `[1395,1598,8,1563,1614]; [1537,1534,63,64,1565]; [31,1344,1576,1566,104]; [1468,1472,1474,1590,165]` |
| 6 | 143080.87122810967 | `[51,1561,1562,1563,75]; [1537,1534,63,64,1565]; [71,72,73,1566,1567]; [1468,1472,1474,1590,165]` |
| 7 (initial) | 108999.1105581193 | `[1395,1598,8,1563,1614]; [120,219,68,1566,124]; [80,81,1576,88,1578]; [1588,57,58,1545,165]` |

Active-source/observer controls, complete native domain/formula/search suites
and9 Python harness/source-envelope tests passed. Neutral/control capture was
3.946/1.607s; no new ordinary runs. Paired job removed491,066,069 bytes; no job
directories remain. Installed engine/consumer, Selected/Theory, matrix logs,
account/settings/equipment and UI remain unchanged.

This isolated speedup did not establish readiness. Its remaining binding-cost
gate is superseded by the following receipt. Production integration, explicit
schedule/healing/ER approximations and the single bounded ordinary finalist
stage remain. GP-3 owns the next Flins product/top-five/button acceptance and
only subsequent one-at-a-time matrix expansion. No architecture decision was
required for these two exact-reuse optimizations.

### 2026-09-20 constant-effect binding reduction

Current authority remains GP-3. This is SOURCE ONLY, on the same active-lineage5
source and saved Flins fixture; no installed engine/consumer or gameplay changes.
`formula/constant_effects.go` prepares the damage-root traversal once. When EVERY
effect expression is a valid finite constant, binding walks only that traversal,
substitutes the values and uses the existing exact folding/interning operations.
Latent read roots stay available in the prepared graph for nonconstant bindings;
dynamic/read/artifact expressions use the general dependency-aware binder.
No event rule, set eligibility, candidate or artifact variable is discarded.

The model cache now validates the entire constant vector before hashing the exact
IEEE values of its conservative damage-reachable projection. Inactive branches
are included. Unknown/dynamic/invalid inputs bypass the shortcut; matching DPS
is never a cache key. Activation and interaction checks still precede lookup.
The existing run-local64-entry/128000-node limits remain. On this fixture6014
effect inputs project to5850; hit/miss counts did NOT improve. The measured gain
comes primarily from binding, not from claiming extra cache hits.

`--compare-effects` makes the narrow control disable just constant binding and
the projected cache key, while keeping the previous preparation optimizations.
Both variants reuse identical captures/inventory. Managed `job-hf6t089c` passed
source controls, full native domain/formula/search suites and paired profiles:

| Domain | Control seconds | Fast seconds | Control/fast binding seconds |
| --- | ---: | ---: | ---: |
| Restricted28 | 6.3060372 | 5.0692023 | 1.902575 / 0.6732606 |
| Full587 | 89.8653781 | 81.2334707 | 16.2890335 / 8.0081422 |

Full preparation41.9717851->36.2253687s; rule18.5460442->18.5567833s;
view0.5361818->0.550225s. These phase counters overlap and must not be summed.
Full563633 evaluations, both2096-proposal cycles, zero unknown packages,
4499/523 program hits/misses,4179/810 specialization hits/misses, all seven
finalists (including every ID and DPS), and both work hashes match the preceding
receipt. Restricted model147084.49346186587 and full148934.35617029207 remain
model scores, not new ordinary verification. No budget or breadth was reduced.
Neutral/control capture3.965/1.595s; zero ordinary calls;494,927,015 generated
bytes cleaned. This is one paired offline measurement, NOT button runtime.

After that measurement, review hardened traversal to the general binder's
ordered DFS postorder: a different valid topological order can change reverse
gradient accumulation rounding despite equal forward DPS. Random controls now
compare compiled nodes/root as well as scores/gradients; a1e16/1/-1e16 cancellation
fixture pins that ordering. Managed `job-2l1agux8` passed all formula/setcontext/
domain/search/allsets suites and cleaned75,410,409 bytes. The paired timings
above preceded this order hardening; they are not a new timing of its final code.
Dynamic latent-read, branch/proof, missing/invalid input and cache projection
controls pass. Eleven focused Python harness/source-envelope tests pass.

The optional `--two-seeds` completion gate uses BOTH retained witness seeds and
independent original-set control captures. Strict decoding covers both members;
response and restricted recall compare the same panel, never the old single-seed
146403.005115 constant. Profiles report panel seeds/member count separately from
provider calls. It shares the existing managed lifecycle and excludes paired
timing options. No full matrix run is authorized by this gate.

Two-seed managed `job-gp4tzy5_` PASS on the final ordered-traversal code.
Seeds742031889/742031890; unchanged neutral/control config hashes from above.
Neutral captures3.701/3.278s; control1.603/1.571s. Second member has6868 events,
805 worlds,325 hits,5406 stat ports,18,463,461 sidecar bytes; first retains the
prior6906/808/327/5480/18,680,134 dimensions. Strict decoding passed both.
Aggregate neutral-model response145343.519729228 matches the independent
two-member original-set control145343.51972922805 (roundoff only).

| Domain | Search seconds | Evaluations | Initial/model leader DPS |
| --- | ---: | ---: | ---: |
| Restricted28 | 9.5334389 | 1215 | 108324.217492 / 146016.143885 |
| Full587 | 109.9605164 | 561044 | 108324.217492 / 147796.549617 |

Full preparation59.6181125s, rule36.9634862s, bind16.3855013s, view0.5542297s.
11944 effect inputs/11616 damage-reachable;5013 requests,4481/532 program
hits/misses,4161/819 specialization hits/misses,20 entries/125908 nodes.
Both2096-proposal cycles finished:305/465 sampled and1791/1631 heuristic
deferrals; zero unavailable packages. Pending4192 remains non-exhaustive model
deferral, not deadline loss. Stop `neutral_cycle_budget` is not convergence.
All seven finalist assignments/order match the preceding one-seed receipt;
their two-seed DPS are147796.54961734888,147077.0633756139,144024.0668780296,
142877.45913400842,142835.72662282834,142053.47379913752,108324.21749233294.
The different scores/work versus one seed are NOT an optimization regression
comparison: the evaluated stochastic panel changed.

- Restricted work hash: `762de55e9946f0afbcd7d173a51df480e56aa4d79b8ad93ec16b27a3c163b2d2`.
- Full work hash: `26642d34942c866f109c1128dcc865196928b2ea9907f60d7ef0954a86b14ae7`.

This run made four source captures and zero ordinary calls;528,644,306 bytes
cleaned. An earlier same-command `job-3hc90n0w` was explicitly interrupted after
the tool-session handle was lost; no numerical result is accepted from it.
Its managed directory and descendants were verified absent before allocating
the accepted retry; cleanup byte receipt was unavailable. This is a harness
collection interruption, not a failed formula/search result.

The existing ACTIVE-engine n500 checks still apply to the unchanged restricted
and full leader IDs (145210.906503/147160.450991 versus144625.550417 control);
they were NOT rerun. Engine/installed consumer and original matrix hashes remain
unchanged. No UI/Selected/Theory or account writes. Next is production bundle
integration and one Flins whole-pipeline/top-five/button gate, not another matrix
team. The109.96s excludes source capture/build, Python preparation and ordinary
finalists; it cannot be advertised as button runtime or a136s target pass.
The source-bound tiny inventory oracle additionally routes every neutral
finalist through the CLI's existing `FinalistRenderer`, including the no-bonus
winner. It checks immutable non-artifact frame, n500 options, energy policy,
set-row cardinality and rendered digest. Managed `job-yv_322vl` passed all
focused source/consumer gates with zero captures/ordinary calls and cleaned
80,631,000 bytes. This is renderer compatibility, not a dispatched product run.

### 2026-09-26 neutral production integration and first whole-pipeline result

Current owner: GP-3. This supersedes the source-only deployment status above,
not those measurements or their limitations. Infinite-energy All Sets now uses
`RunNeutral` when the ACTUAL selected engine advertises `gtt_neutral_inputs_v1`.
Python includes bound rule libraries only for that route. Missing libraries
fail explicitly; finite-energy All Sets retains its existing ledger-aware
context route, and Selected/Theory are unchanged. This does not finish finite
neutral ledger binding or the schedule-changing fallback. Unknown rules remain
boundaries; healing-amount, ER activation and prior-query/callback approximations
remain explicit, not zero/full-uptime substitutions. No ordinary set rewrites.

Managed `job-p71uqwhy` used the exact active v2.45.0 pristine archive and proved
the old eight-patch source replay equals the ACTIVE lineage5 source before
building. Fourteen observer/generator deltas plus capability metadata were
consolidated as production `0009-gtt-neutral-event-effects.patch`; there is only
one production stack. Normal updater/build/source-generator gates, all14 native
packages, two ordinary compatibility smokes, one compact consumer/two-wave gate,
and four ACTUAL built-binary response captures passed before activation. The
two-seed model and independent original-set control both give145343.519729228;
inactive Obsidian has zero damage/crit increments. The later helper hardening
reads generator-ready/required flags from actual manifest metadata (both were
`true` in this installation), not supplied constants. Forty focused
Python adapter/source/gate/retention/UI-routing tests pass; rollback-injection
tests include failure AFTER pointer activation. These are scoped compatibility
and response gates, not universal set/character acceptance.

| Installed component | Identity |
| --- | --- |
| Active engine | `gcsim-v2.45.0-20260926131728` |
| Pinned rollback | `gcsim-v2.45.0-observed-modifier-lineage5-20260919` |
| Engine SHA256 | `b4bef4632939491cbbd8916906ca0cc11c45559f7ef57f6eceb9a2763bf4ed16` |
| Consumer SHA256 | `5d1b37e2e1afb45263d2985db07200917f7ac83f58cdaea760a2e68afb59b00b` |
| Source manifest | `185ac919a185a3a70272d13d1773ad6b799e5ec0f0ea9a94a70320f0129f4576` |
| Ordered stack | `65f9c4f02f3190241ffc9ee52358a7b4726b8500c2cfcd68d1b916267b094b50` |
| Patch0009 | `b760ebd69713f727750249bda5fb4f2cd9766ae7ab09ea5183ee07adf5285006` |

The ONE product-session retry used the installed consumer/active engine through
the same `GcsimOptimizerGoAllSetsRequest/Session` as the button worker. Command:
`all_sets_inventory_regression/run.py --only lunar_charged_all_sets --retry`.
Managed `job-j7kla4ta`, run `all_sets-20260926-162253-62d1f80e`.
Original matrix was NOT rerun. Attempt3 appends to existing before/after logs in
`docs/optimizer-evidence/all-sets-inventory-20260919/`; report rendering separates
historical failed analysis from this neutral attempt. The immutable baseline SHA
remains `00a0cd81711081e867faf06cad9230471ada6c4ecd956104181a69187231a152`.

Inventory587 and prepared config are identical to attempts1/2; inventory SHA
`e39e6051c2bf80396fd1274f3b254118c3578cf417ce19a56340d7dbf33efe43`,
rotation SHA `8da003c2d2b5c501882e879d9c1d5b9a3d952c491b74b9bf97db364a578d6435`,
request SHA `4e584ce4af646732cffb1b2a7b81c2eff639f59819d4faa30f74dc3bbdca2371`.
Same virtual characters, C0/90, weapons/R1, talents9 and saved rotation. The
original matrix lacks an inventory hash, so exact historical inventory parity
cannot be independently proved. Normalizing only iteration/workers gives the
same non-artifact hash as the144733.525 legal control:
`4ce764f144d1ea0055814cd51ca017e5491d85d8d30cb15ef68a62b8d183b57b`.

| Retained rank | Formula DPS | Ordinary n500 DPS | SE |
| --- | ---: | ---: | ---: |
| 1 | 147352.277359 | 147170.596282 | 130.447133 |
| 2 | 145092.618541 | 144688.236672 | 110.677206 |
| 3 | 143190.077592 | 142977.474840 | 121.552902 |
| 4 | 141563.185683 | 141340.227593 | 106.762953 |
| 5 | 140433.114452 | 140348.019315 | 117.744881 |

All five retained rows have20 unique physical IDs and n500 measurement; full
builds are in after.json. Leader IDs exactly match the prior source-profile
leader: Columbina `[66,67,8,69,1580]` Silken4; Flins
`[1537,1534,63,64,1565]` Night4; Ineffa `[71,72,73,1566,1567]` Aubade4;
Jahoda `[1468,1472,1474,1590,165]` VV4. Ordinary gain versus original matrix
108107.231787 is36.13%; versus legal control144733.524592, +2437.071690
(1.684%). This exceeds that known recall witness, not every legal build.

**Performance FAIL:**417.765s whole session versus original272.953s and previous
revision683.329s. Adapter: input7.391s, source9.922s, preflight0.172s,
native400.219s. Native search350.024s; final phase approximately48.2s from
progress timestamps. Only two neutral captures, one context; no per-package
simulation and no n128 stage. Search stopped `neutral_cycle_budget`, NOT the
900s search or1080s product deadline. Both cycles prepared2096/2096 proposals;
sampled37/546, heuristic skips2059/1550, zero model-unavailable/unprepared/
unprocessed/reservation failures.394702 scored evaluations;4192 pending markers
denote non-exhaustive regions, not unfinished queues. One sampled refinement hit
work/round limit;582 reached sampled-neighborhood stability, not global proof.

Costs: proposal282.830668s; rule256.382097s; binding20.178517s; view0.778737s;
joint0.441252s. These counters overlap. Recorded actor refinement sums31.081873s
excluding the cumulative joint rows. Initial capture/compile21.812008s includes
provider work; each provider process5.581/4.795s and decode3.852/3.587s.
Model4814 requests,4293/521 program hits/misses; specializations3964/829.
The program cache saves binding AFTER rule execution, not the256s above.

Code-level performance lead: `CompilePackages` combines individually cached
constant components only while footprints are independent; any shared key or
stat dependence forces a full-team `compilePackagesJoint`. Initial actual
matrix equipment includes TWO Noblesse4 holders. Both write the same recipient
`nob-4pc` keys, so their footprint conflict is real and must not be summed.
The source-profile initial equipment was DIFFERENT: Tenacity/Silken/Obsidian/
Day, captured around a different reference vector. Its109.961s is therefore
not a paired reproduction of this product run. The share of full joint replays
and their per-group costs still needs instrumentation; do not claim that the
Noblesse conflict alone has been quantitatively isolated.

Next bounded implementation: count joint replays/reasons and cache exact package
effect results before formula binding; then replay only connected interacting
groups with strict dependency/uncertainty preservation. Compare repeated/shared-
key cases against full joint replay before rerunning this SAME initial request.
Do not increase deadlines, skip conflicts or advance matrix teams. Current
comparison retention is now three Flins attempts; preserve them and agree a
bounded successor receipt before another product retry, not an implicit fourth
attempt or log overwrite.

UI boundary: native Computer Use inspected a freshly launched project-venv
`python -m ui.app_shell_smoke` (same AppShell module as recorded PyCharm path,
not `main.py`; the currently open PyCharm was another project). GCSIM -> Artifact
optimizer -> All Sets correctly displayed empty-team rejection. No prepared
team was restored, so this proves entry/guard only, NOT a dispatched optimizer
or visible final-result/paging/Save/cancel gate. Automated routing tests bridge
the worker to the numerically checked session. Own window closed and Computer
Use reset; no equipment, preset, settings or account actions. No other matrix
team, Gaming, Theory or Selected numerical rerun.

Lifecycle: install job removed806,806,349 bytes; product job68,475,500 bytes;
no owned job remains. Active and pinned rollback persist normally; old patch
overlays/install helper stay only through the declared product/button cleanup
gate, not as a second active stack. Their old overlay commands cannot be applied
again to the consolidated active source: a capability guard rejects that
historical gate before source controls/captures, with a focused regression.

### 2026-09-26 user-run feather counterexample (diagnosis, not a fix)

User-triggered All Sets run `all_sets-20260926-165133-9336ff4c` completed through
the visible app and retained its request/captures/finalists under the ordinary
run-retention owner. Engine, patch/source hashes and consumer match the installed
integration receipt above. Inventory587 has the same comparison-format SHA
`e39e6051c2bf80396fd1274f3b254118c3578cf417ce19a56340d7dbf33efe43`.
The prepared config differs from attempt3 ONLY in four talent rows: all10/10/10
instead of9/9/9. Rotation content is identical (raw shell trailing newline differs).
User run request SHA `b5a3a920681430a36263bc204aba5a7f605c056fb9464d5a13f7e8e63c9dba63`;
saved winner config SHA `5352384af1057779c8a7feb8e838b6b6392d2368896c441aecffd0594ca24f4b`.
Same20 winner IDs as attempt3, measured152872.410114 (n500, SE123.223866),
formula152791.384867. Total318.922s, search279.790629s,393797 scores,
two-cycle stop, not deadline; no speed acceptance inferred from different inputs/load.

Screenshot identifies Night plume1534 (ATK9.3%, CR9.3%, CD15.5%, HP239) versus
1535 (ATK5.8%, CR10.1%, CD18.7%, HP478); both mainATK311. Difference is
-3.5 percentage points ATK, +0.8 CR, +3.2 CD, +239HP; +4.8 displayed CV.
The latter is unoccupied in the saved winner; replacement preserves20 unique IDs
and all four packages. The managed probe changes ONLY this artifact stat delta
in the exact saved finalist config, preserving declaration order and rotation.

| Ordinary active-engine check | Iterations | DPS | Standard error |
| --- | ---: | ---: | ---: |
| Exact saved user top1, repeated | 500 | 152571.961584 | 127.300314 |
| Same top1, only four talent rows restored to9 | 500 | 147114.967846 | 116.751899 |
| User top1, plume1534 | 4000 | 152389.751579 | 44.449792 |
| User top1, only plume1534->1535 | 4000 | 152657.950206 | 43.200594 |

Ordinary advantage+268.198627 DPS (+0.175995%); independent-seed difference
SE61.984476, approximate95% interval[146.709054,389.688201]. Ordinary runner
uses new random seeds, not exact per-iteration replay. All four duration means
72.466666667s; identical cooldown-wait summaries, no insufficient-energy events.
Talents9 reproduction agrees with prior147170.596 within simulation uncertainty.
Do not compare a new n4000 swapped result to the original n500 winner to rank items.

Reused BOTH original user neutral captures without another capture or full
search. Same production model reproduces saved formula152791.384867 exactly.
Plume1535 gives153013.147648 (+221.762781): formula and ordinary simulation
agree on the ordering, not identical absolute DPS. All five account Night plumes
were evaluated with the other19 pieces fixed:1534=152791.384867,
1535=153013.147648,2=151840.272277,1533=152680.439355,1536=149379.937417.
Separate full-formula interventions at top1: ATK-3.5% costs845.984477DPS,
CR+0.8% gains397.155974, CD+3.2% gains677.597383, HP+239 changes0.
These separate gains are not additive because the terms multiply. Crit cap is
not the explanation: the extraCR has a positive modeled contribution.

**Confirmed search orchestration defect:** `neutral_coordinator.go` freezes the
cycle anchor for all one-wearer package screens/refinements. Combination and
`RefineJoint` can then change the team after those local checks. Its terminal
`runJoint` does NOT include per-wearer single-slot stabilization;
`inventory_pairs.go` proposes linear pair seeds and occupied-item transfers,
not every free single replacement. All six competitive ordinary finalists kept
plume1534; no1535 variant reached final simulation. The saved work log is not a
per-evaluation trace, so it cannot prove1535 was never scored in another context.

Direct existing `RefineCandidates` on the FINAL top1 finds
Flins`[1537,1535,63,64,1565]`,153013.147648DPS in280 evaluations,
0.024768s, sampled-neighborhood-stable. Direct `RefineJoint` at the SAME top1
does not improve it:716 evaluations, no work-budget exhaustion,0.096485s.
Even the recorded earlier joint anchor prefers1535 by194.203519 formulaDPS;
do not explain the failure as an established earlier preference for ATK.
This counterexample proves a missing terminal local check, not that one check
solves all earlier heuristic deferrals or guarantees a global optimum.

Required correctness gate before accepting the speed work: stabilize surviving
complete finalists on their actual joint team formula, including affordable
legal free single-item substitutions; recheck affected wearers after accepted
joint changes and report bounded non-convergence explicitly. Keep one bounded
ordinary finalist panel AFTER that offline stage. This is a proposed repair,
not implemented/deployed here; no deadline increase or extra matrix run.

Reproducer: managed `parametric_effects/check_saved_feather.py <saved-run>`;
four ordinary checks plus opt-in `TestSavedFeatherDiagnosis` against the saved
capture. Four Python no-engine substitution/guard tests pass. The extended
formula-only diagnostic also passes. Jobs`ahjfcf_w` and`e9vyv_gt` cleaned
71,185,316 and70,706,483bytes respectively. No generated probe output survives;
this compact dated receipt is durable evidence, not a fourth matrix attempt.
The temporary Python/Go probes share the existing Flins research cleanup gate.
No production code, engine, account, equipment or UI actions changed.
User-completed visible result is now reported/saved-log evidence; automated
paging/Save/cancel/full-UI acceptance is still open.

### 2026-09-26 terminal stabilization and conflict-group preparation repair

Scope: user-authorized All Sets repair after the feather counterexample, not a
new matrix sweep or Selected/Theory rollout. This implements variable-neighborhood
descent over **complete legal assignments**, not a critical-value heuristic or
a claim of convex/global optimization. Gradient scores remain proposals only.
See [Hansen/Mladenovic, VNS](https://www.sciencedirect.com/science/article/pii/S0377221700001004)
for neighborhood changes; [SCIP primal heuristics](https://www.scipopt.org/doc/html/HEUR.php)
for cost-aware scheduling; [LLVM SCCP/DCE](https://www.llvm.org/docs/Passes.html)
for the distinction between proved irrelevant computation and a zero observed
derivative. These principles motivate the repair; they do not certify the game
model or these heuristics as globally optimal.

- `search/stabilize.go`: enumerate every free single-slot substitution at each
  final joint assignment using its reduced arithmetic, preserving package and
  physical-ID legality. Revisit ALL owners after any improvement because a
  support artifact can change another owner's response. Then run the existing
  within-owner paired/linear proposals and cross-owner exchanges; any gain
  restarts singles. Strict ascent tolerance is1e-9*(1+abs(DPS)); the finite
  assignment space plus the shared work allowance bounds execution. Record
  `single_stationary`, evaluations, accepted moves and stop separately; this
  certificate excludes occupied-piece exchanges and unvisited set contexts.
- Neutral coordinator polishes every surviving non-baseline finalist, within
  the existing per-finalist20k/shared8M allowance and existing deadline. It
  replaces representatives rather than reintroducing unchecked old rows after
  deduplication. The baseline comparison remains unchanged. The ordinary n500
  budget is not increased. A deep-work log now records the actual refined
  result instead of its entry seed (previously misleading diagnostic evidence).
- `CompileSourceBundleForInventory`: verify every supplied source hash, but
  skip rule parsing when the inventory lacks two distinct slot types of the
  set. On the user's587 items this skips11 of42 source sets. No artifact is
  deleted, no-bonus/off-set pieces stay legal, and2p remains eligible when4p is
  impossible. Existing slot/package feasibility checks still precede replay.
  Theory and finite/legacy source routes are unchanged.
- Reuse isolated constant effect components; replay only conflicting groups.
  Cache group raw vectors/footprints within the captured panel (FIFO128 entries,
  <=2M floats), not damage graphs or persistent gameplay tables. Shared writes,
  reads of another effect's state, or shared subscriptions require joint replay.
  Merge repeatedly: A can enable B, exposing a previously hidden conflict with C.
  Keep a conservative union without mutating cached footprints. Stat-dependent
  or unresolved components still fall back to full joint replay. Apply the
  nonlinear resistance curve AFTER raw composition. Empty bonuses avoid replay.
  Thus speed does not rely on silently interpreting unknown effects as zero.

Do not implement the proposed HP/DEF early exit from a current zero gradient:
a cap, conversion, heal or cross-owner buff can make it useful elsewhere. Such
an exit requires the whole-team dependency/effect graph, not a character-name
allowlist. The present repair removes repeated source work without pruning
additional candidate regions or changing damage/stat formulas.

Source checks: full native suite including active-source controls passes.
Synthetic tests cover cross-owner reconsideration, negative local slope,
independent direct N1 enumeration, monotonicity, cancellation/work limits,
finalist retention, newly exposed three-group conflicts, cache order/aliasing,
early source feasibility and authentication even for skipped rules. Existing
tiny exhaustive, paired-escape, reservation and no-bonus oracles pass. On BOTH
saved user captures the original formula is unchanged exactly; stabilization
recovers1535 at153013.147648 in3609 evaluations/0.338s, then a separate N1 oracle
finds no improvement. Twenty-eight saved-panel package checks (including shared
Noblesse and stat-dependent Emblem) match full joint effects/uncertainty; initial
probe2.696s versus5.330s full replay, not an end-to-end speed claim.

Installed consumer SHA256
`ebe0ccf19c017409708ab45165a408133f2ac1acb1bd7bab7fd1c9127cdde8ec`;
engine`gcsim-v2.45.0-20260926131728`/artifact`b4bef463...`/patch/source unchanged.
The fixed [successor receipt](../optimizer-evidence/all-sets-inventory-20260919/flins-user-stabilization-20260926.json)
retains old/new measurements, configs, assignments, search work and identities.
No fourth matrix row was appended: all three historical attempts remain intact.
Replay copied the exact saved request bytes and regenerated an exactly equal
active-source envelope, then used the installed button session's real preflight,
source and process methods. This intentionally skips account request rebuilding;
it is not a physical button click or whole fresh-UI timing.

| Identical measured boundary | User run before | Repaired replay |
| --- | ---: | ---: |
| Go backend total, seconds | 305.298908 | 144.771283 |
| Neutral capture/model/search, seconds | 279.790629 | 117.371808 |
| Source effect preparation, nested seconds | 200.842100 | 35.297891 |
| Formula binding, nested seconds | 16.197309 | 16.286245 |
| Ordinary seven-finalist n500 stage, seconds | 24.219242 | 26.099552 |
| Formula evaluations | 393797 | 420942 |

Backend2.1088x/52.58% faster; new adapter replay153.296s. Earlier full user
session318.922s includes account preparation and is NOT the same boundary.
Both search configurations are byte-value equal; no time/work/cycle/frontier
increase.4817 model requests/519 program misses/4298 hits are identical;
2096/2096 packages prepared in each of two cycles, zero unavailable models,
586 sampled refinements and3606 heuristic deferrals unchanged. Preparation now
uses251 replays (19 joint),1070 conflict-group hits/10 misses and9 conservative
full fallbacks. Raw retained groups119440 floats. New preparation time includes
22.219s actual source replay plus composition/other preparation; it is NOT pure
Go-source parsing. Deep candidate refinement27.074s, joint0.815s, finalist
stabilization2.281s; counters are nested, not additive phase totals.

All six competitive finalists finish `single_stationary_sampled_pairs_stable`;
18 accepted improvements add27145 evaluations, exactly the before/after work
difference. Top1 swaps only1534->1535 and retains the other19 IDs/packages;
formula153013.147648. Ordinary n500152817.383291/SE123.684233, residual-0.128%.
Old mean152872.410114 differs by-55.027DPS, below combinedSE174.591; this is not
measured regression or proof of gain. The earlier dedicated n4000 feather A/B
owns the statistically resolved ordering. Other context representatives also
improve in formula score; stronger finalist quality is not a global-optimum proof.
Stop remains `neutral_cycle_budget`: final N1 checks completed, broad two-cycle
set exploration is still heuristic and bounded. No opaque/schedule guarantee is
inferred from zero unavailable set models.

Full native suite (14 packages, active-source and saved two-capture probes)
passes, plus47 focused Python probe/adapter/UI-routing tests. No other team,
Gaming, Theory or Selected numerical run; no CU/account/equipment/settings change.
Managed replay/build job`amrmi5lx` removed234,657,530bytes; preceding test jobs
removed80,096,640 and80,212,929bytes. No owned scratch remains; only the fixed
715396-byte successor survives under the comparison's user-replacement gate.

### 2026-09-26 Navia matrix continuation: faster result, uncovered effect boundaries

The user explicitly authorized one `gpt-6-luna`/max subagent to continue All
Sets rows sequentially, reporting each to the parent and stopping on anomalies.
Only `lunar_crystallize_all_sets` attempt2 ran; no next row or Gaming. The normal
matrix harness uses the actual Python product session/default consumer and
active engine, not an alternate simulator. Binary identities are unchanged from
the preceding stabilization receipt: consumer `ebe0ccf19c017409708ab45165a408133f2ac1acb1bd7bab7fd1c9127cdde8ec`,
engine `gcsim-v2.45.0-20260926131728`/`b4bef4632939491cbbd8916906ca0cc11c45559f7ef57f6eceb9a2763bf4ed16`.
No UI click, account/equipment mutation or budget increase occurred.

The bounded existing [comparison](../optimizer-evidence/all-sets-inventory-20260919/report.md)
and `after.json` retain both Navia attempts and every original row; original
source/copy SHA remains `00a0cd81711081e867faf06cad9230471ada6c4ecd956104181a69187231a152`.
Request `e6422c40229d2ce357a10eee28d20b85aa3c79747eb2c3854b9ce362e2212928`,
rotation `8bd154a96c4af8a0669897c2c2b5a1d46c3aad3321a64b92cbea84e2ac0200f0`,
inventory `e39e6051c2bf80396fd1274f3b254118c3578cf417ce19a56340d7dbf33efe43`.
Navia/Xilonen/Ineffa/Columbina profiles and rotation match the manifest, talents9,
infinite energy. The old baseline lacks an inventory hash; prior attempt1 matches
the current inventory hash. Both old rows use lineage5, so the improvement does
not isolate engine changes from search changes.

| Same team, saved row | Ordinary mean DPS | SE | Whole session seconds |
| --- | ---: | ---: | ---: |
| Original supplied matrix, n1000 | 111008.753989 | 55.324160 | 280.000 |
| Prior attempt1, n500 | 122434.876739 | 60.880878 | 639.188 |
| Neutral attempt2, n500 | 126982.713688 | 70.632666 | 184.407 |

New formula126376.212319, residual+606.501369/+0.478%; the top-five residuals
range+0.396..0.478%, not zero response error. Backend169.675405s; adapter
process170.875s; capture/model/search128.209505s. Effect source replay/preparation
counter50.095633s, binding17.223785s. These nested counters cannot be summed as
independent phases. Two captures/cycles,2096/2096 packages prepared per cycle;
738 sampled refinements and3448 heuristic deferrals across both cycles;
606294 evaluations. Stop `neutral_cycle_budget`, not timeout. All six competitive
finalists complete `single_stationary_sampled_pairs_stable`,31121 stabilization
evaluations/12 changes. Seven ordinary n500 checks, including the anchor. The
harness now preserves all seven and the stabilization diagnostics, not only UI
top5. Preparation completion is not exhaustive inventory or set-combination
coverage and does not resolve the following unavailable contexts.

Parent inspection stopped progression: per cycle, MH4 on Navia/Xilonen fails on
`math.Abs`; Song4 on Xilonen fails on observed event mutation. Six unavailable
contexts across two cycles are three repeated owner/set combinations, not six
different sets. Source-only changes in `seteffects` now support exact numeric
`math.Abs` and symbolic `max(x,-x)` without freezing the stat operand, and provide
a specific missing-hit-identity error on an attempted additive flat-damage write.
Other observed mutations/unknown functions remain rejected. The active-source
suite passes, including real-heal/overheal/target/off-field/stacks/expiry MH
controls, signed-zero/symbolic/invalid-call arithmetic controls and Song missing/
zero/unbound-ID rejection. These edits are NOT installed or product accepted.

Song diagnosis is a producer/consumer timing bug, not unsupported game arithmetic.
Active `pkg/enemy/attack.go` calls `gttTraceBeginHit` and emits `OnEnemyHit`;
`pkg/core/info/gtt_combat_event.go` copies `GTTTraceHit.HitID` then. But active
`pkg/optimization/optstats/trace_equation.go` assigns that ID only in the later
`OnEnemyDamage` subscription. Existing synthetic Song control supplies HitID7
up front and therefore missed the actual producer seam. Read-only inspection of
the retained same-active-engine Flins context `de73de5b...`, seed742031889 confirms
327/327 hit-event payloads have ID0, while327 retained formula hits have nonzero
IDs (950 attack-shaped event payloads in6906 events; all950 IDs are zero).
No matching by numeric damage, actor alone or coincident frame is permissible.

Next discussion: a narrowly scoped observer fix must establish an unambiguous
identity before event serialization and preserve that identity into its formula
port. It must not change ordinary set mechanics, callback order or assign the
bonus to a guessed neighboring hit. Validate real multi-hit/multi-target event
identity and a neutral-versus-ordinary Song witness before coherent deployment
and the same Navia retry; then resume one-row-at-a-time checks. Engine, production
patch and installed consumer remain unchanged pending that work. Healing amount
and callback-order response approximations remain disclosed separately from
identity correctness.

Storage: matrix scratch removed89,250,756bytes; active-source focused Go test
scratch removed67,536,250bytes; both jobs absent. No new persistent output class:
the existing bounded matrix receipt/report lifecycle owns the appended row;
historical stop notes remain explicitly dated, while current matrix metadata
now says paused on Navia coverage. No full-suite/search rerun after the source-only
fix; focused report/retention tests and handoff checker own their separate gates.

### 2026-09-26 approved early hit identity repair — gate mechanics

The user approved the narrow observer correction after the Navia diagnosis.
`parametric_effects/repair_hit_identity.py` reconstructs the exact ACTIVE source
from its bound archive and complete production stack before changing anything.
Its reviewed `hit_identity.patch` is consolidated into patch0009 against that
layer's original input; no ordinary artifact/character implementation is changed
and no second production observer stack is retained. A trace-only per-core
counter allocates the enemy hit ID in `gttTraceBeginHit`, before `OnEnemyHit`
serialization. The terminal collector preserves that ID; opaque terminal-only
hits use the same allocator if needed. Number allocation neither calls RNG nor
advances observation ordering. Multiple targets receive independent identities.

Gate controls include trace-off/nil/per-core counter behavior, source package
tests, normal updater compatibility, unchanged artifact/character source trees,
real same-frame/multi-target event-to-formula identity, and independent ordinary
versus neutral-plus-Song response. The controlled healer deliberately saturates
Song's accumulation cap; this isolates attribution from the separately disclosed
frozen healing-amount approximation, NOT universal healing response acceptance.
The final real capture is repeated after installation/overlay relocation inside
the promotion transaction; an error restores pointer, consumer and prior patch
before returning the candidate to managed cleanup. Injected tests cover both
new-patch installation and replacement, including post-relocation failure.

Preserved gate failures before activation (not optimizer-search measurements):

- First helper scenario used an infinite action loop, which the declared
  duration did not terminate; ordinary-control call hit60s before any build or
  activation. Replaced with a finite12-action loop; focused probe passed.
  Scratch removed158,933,106bytes; probe removed26,424bytes.
- The next candidate built and passed updater/application compatibility, but
  the separate cold source-test command exceeded its180s technical command
  watchdog. No response verdict or activation; removed1,571,968,115bytes.
  Test execution remains120s; compilation command now has600s, with two build
  workers and the same owned Go module/cache environment as engine preparation.
  Product search deadlines and candidate counts are unchanged.
- The third gate passed source tests, actual multi-target identity checks and
  ordinary before/after/compact equality2443.453454325 DPS, but its two-character
  synthetic team did not satisfy the consumer's four-character panel contract.
  `TestLiveSongHitIdentityAndResponse` failed before effect scoring, not as a
  damage discrepancy. No activation; removed1,261,033,476bytes. Added two idle
  characters rather than relaxing the contract; a fresh active-engine ordinary/
  neutral/schema probe passed and removed1,609,231bytes. The observer source
  correction itself is unchanged across these test-harness repairs.

- Fourth gate: canonical healer lookup used the config alias `kokomi` rather
  than emitted `sangonomiyakokomi`; identity/ordinary checks passed, response
  test stopped at `healer absent`. Canonical name was confirmed in active
  `pkg/core/keys/character.dm.go`, then fixed and added to cheap preflight.
  Removed1,261,063,536bytes; preflight removed1,609,226bytes. No activation.
- Fifth gate: the source replay and aggregate evaluation executed, but the test
  rejected unequal compact `topology_sha256` before printing/checking numerical
  response. These hashes include `GuardSummary`, not only the hit schedule.
  Raw controls establish identical14 topology events and38 hits, both15750ms.
  Neutral hash `6588f32f863de8a040e48cdae5380e3cf0a268c8e13ffdcf91f9464147fc75f7`;
  Song hash `c70bfe6ed28bb59ae85fb62b67a34ff681ba168b360a8c0521b6c05c4e3ae0b7`.
  Guard unsupported count9->10 and flat provenance true->false account for a
  changed completeness signature; both guards already have incomplete provider/
  reaction provenance. Ordinary/compact baseline equality is NOT general
  formula response proof. The corrected test now compares actual raw topology
  and per-hit identity/frame/actor/target/tag/element/reaction/ICD/aura facts,
  while retaining the strict1e-7 DPS response tolerance and disclosing guards.
  This corrected real gate has NOT been rerun or accepted. Added early numeric
  logging so any further alignment failure cannot hide already computed scores.

The fifth job's bounded120s manual-review window expired before the continuation
marker arrived. Bulk cleanup removed the candidate/captures/cache; the late88-byte
marker caused final directory removal to fail. Inspection proved it was the only
residue; removed the marker and the verified empty owned directory. No other job
or engine was deleted. The manual marker-retry feature has been removed rather
than retaining a cleanup race. Its failed removal did not yield a reliable total
byte count. All failed candidates were staged only; ACTIVE engine, patch0009 and
consumer hashes remain exactly the preceding GP-3 identities. No Navia attempt3
or later matrix row ran. Further full response/deployment retry needs explicit
user approval after this sequence of failed validation attempts.

Final lightweight validation: `go test -p1 ./internal/seteffects -count=1
-timeout=90s` passed; managed scratch removed67,604,893bytes. The opt-in real
capture test was skipped without its environment, so this is compilation/unit
coverage only. Promotion rollback and matrix-runner Python suites pass11tests,
including existing-patch restoration and post-relocation failure injection.

The existing bounded engine store and managed scratch lifecycle own all output.
Current partial acceptance/resume is in GP-3; these are retained failed gates,
not an installed or completed fix. Source inspection supports the narrow repair;
numerical Song acceptance and the same-button-backend Navia retry remain open.

#### Additional authorized gate: response PASS, deployment rolled back

The user authorized one corrected full gate, then installation and Navia only
on success. Managed job `job-1n8pczcs`, candidate
`gcsim-v2.45.0-20260926164554`, ran the exact active-source reconstruction and
normal build/application compatibility. Fourteen native packages passed before
and after real-source binding. Engine tests passed for `pkg/gtttrace`,
`pkg/core/info`, `pkg/enemy`; `pkg/optimization/optstats` compiled with no matching
tests. The full source-bound seteffects suite also passed.

`TestLiveSongHitIdentityAndResponse` PASSED on real exports:38 hits,2 targets,
simultaneous hits, nonzero unique event/terminal identity, identical raw topology
and per-hit scheduling facts. Baseline2047.933454325 DPS; neutral plus Song and
independent ordinary control both2443.453454325 DPS; residual0. Ordinary old/new/
compact equality also passed. Saturated healing deliberately isolates hit
attribution; retained uncertainty codes are
`counterfactual_callback_phase_observed_schedule`,
`counterfactual_flat_callback_order_observed`,
`counterfactual_task_phase_observed_schedule`,
`set_activation_heal_amount_frozen_to_observed_build`. This is not general
healing-amount or stochastic schedule response acceptance.

Promotion reached its post-relocation installed capture, then strict whole-member
comparison failed: `Relocated installed capture differs`. The helper did not log
the differing field. Transactional rollback restored the active pointer,
consumer and patch0009; hashes rechecked against GP-3. The old engine remains
active, candidate was returned to managed cleanup; removed1,273,904,448bytes.
No job directory remains, no Navia attempt3 or later row ran. Therefore this is
a controlled response pass, NOT installed acceptance. The failed export pair was
not retained; do not claim a measured DPS or graph-semantic difference from it.
Source inspection confirms compact member serialization excludes timing audit
and filesystem paths. Harmless numbering/order and semantic differences remain
unresolved alternatives, not a diagnosed cause.

Added a bounded first-eight-path structural diagnostic to the same strict gate,
without ignoring any field or allowing installation on mismatch. The first
unit test exposed Python nested `1 == True` equality; recursive comparison now
preserves scalar types too. All12 promotion/diagnostic/matrix-runner unit tests
pass. No new real capture/build followed the failure. Next proposed step is a
cheap repeatability diagnosis on the existing active binary, without relocation
or compilation, before requesting another full deployment attempt. User approval
is still needed to continue beyond the one additional full gate just consumed.

#### Follow-up: reproducibility diagnosis without rebuilding

The user explicitly authorized automatic technical diagnosis/local repairs and
continuation to player-visible evidence, stopping only for a genuine decision
fork. This supersedes the preceding per-retry approval request for this work.
Two fresh captures from the SAME unchanged active executable, without any move,
reproduced different node numbering:4223 nodes each, both2047.9334543250047 DPS.
The first logged change was node1711 value -1 versus0.25, with later input IDs
swapping correspondingly. `compileModifierEvent`/`dynamicStatDeltas` iterate
independent map entries while allocating graph nodes. This establishes that
byte-identical member layout is not a valid relocation requirement. The first
diagnostic removed3,156,280bytes, with no installed changes.

The deployment-only `capture_equivalence.py` verifies each sidecar's original
member-byte digest first, then computes dependency-ordered expression hashes
including operation, literals, coordinate and ordered input relations. Full
effect annotations (owner/stat/point/event/target, including neutral read roots)
participate in node identities BEFORE dependent expressions are hashed. Equal
zero-valued ports therefore cannot silently exchange owners or activation times.
Every node/multiplicity, channel root, opaque boundary, energy/guard/context and
remaining sidecar field survives comparison; only graph numbering and unordered
neutral annotation discovery order are normalized. No numerical tolerance or
ignored gameplay field was introduced; no additional engine patch is needed.
Tests reject equal-baseline changed responses, swapped zero ports, owner/time/
ledger changes, invalid hashes, missing references and cycles. Four new tests
and five promotion tests pass. A second fresh active capture pair passed this
expression-plus-effect comparison; removed3,156,280bytes. No relocation alone
was claimed to change damage. The historical failed pair was already cleaned,
so the observed repeatability mechanism, rather than a reconstructed exact diff
of that old pair, is the evidence for correcting the gate.

The ensuing managed clean-build/install gate PASSED, including the real Song
witness again, full14 native packages, active-source seteffects, normal updater
compatibility and a fresh capture through the relocated ACTIVE path. Ordinary
old/new/compact control all2443.4534543250047 DPS; no game-mechanics source diff.
Installed identity:

- Engine `gcsim-v2.45.0-20260926170526`, executable
  `93efe0efed194b4fffdee6d5340e2cf633232ded85a20230e5f7020465ccbf00`.
- Consumer `6ea621a7416bf3d98cceea64fa2b07f9ce55e0d071aee2bdad8445346ca6b9d9`;
  source manifest `b359a169d814cecf49fbaad03ee40eb8ed2203bf1f619df586b43e733a37164f`.
- Patch0009 `49593c83a5dfb36095c5d0b696a6d00dc877b45b060e6b043b7fb11053f1f70e`;
  complete stack `ea7845dbf839ad5cf2f89305ded2fe6ef8326594c7755c3e6afb69a45c494de4`.
- Previous/rollback engine `gcsim-v2.45.0-20260926131728`; previous consumer
  `ebe0ccf19c017409708ab45165a408133f2ac1acb1bd7bab7fd1c9127cdde8ec`.
- Control config SHA `372bb5ae5799b7032f29143345bec662e916ae8e28e574518cb32d4d9d085d0b`.

Managed job `job-_8vbddtc` removed1,130,098,041bytes after successful promotion;
only the validated normal engine install and consolidated patch/consumer survive.
Active pointer and all three installed artifact hashes were rechecked. This is
installed-path acceptance of the repair, not a physical UI check or a claim
that Navia/new-team search quality is proved. The next one-row Navia receipt is
retained in the existing matrix store, not in a new output class.

#### Navia attempt3: installed coverage repair and player-facing review

Luna/max ran only `lunar_crystallize_all_sets --retry` through the normal product
session on the installed bundle above. Saved attempt3 preserves attempts1/2 and
the immutable original. Parent independently checked equality of virtual profile
entry,587-item inventory hash, prepared config text, rotation and search config
against attempt2. Whole185.219s versus184.407s; optimizer process172.344s versus
170.875s; internal total171.352s versus169.675s; capture/model/search129.383s versus
128.210s; ordinary verification40.682s versus40.161s. No runtime improvement is
claimed for this observer/coverage correction.

Top1 is the same20-ID assignment:126945.303984 DPS, n500 SE70.638932, versus
126982.713688/SE70.632666. Formula unchanged126376.212319; residual+569.091665
(.448%). All five physical candidate builds and their formula scores are
unchanged; ordinary DPS differences are under1.3 combined SE. Ranks4/5 exchange,
not evidence of a genuine reversal. Unknown effect records6->0; no
`all_sets_unknown_effects_present`. Each cycle prepares2096/2096 packages with
zero unprepared/unavailable, but item search remains heuristic:2074+1378 skipped,
740 sampled package visits across two cycles,606731 evaluations. All6 competitive
finalists finish the full legal free single-item neighborhood and sampled pairs
(31121 checks,12 accepted changes). Stop `neutral_cycle_budget`, not time expiry,
exhaustive coverage or proof of global optimality. Seven ordinary n500 finalists
include the initial-equipment control. Cleanup removed89,285,647bytes; no orphan.

Player-visible interpretation of the retained top1:

- Navia:4 Night of the Sky's Unveiling, ATK%/Geo/crit damage, one Obsidian piece.
  The ACTIVE source gates the4p CR on a Lunar event while wearer is active,
  not a Natlan/Nod-Krai wearer whitelist; it also gives the team Lunar bonus
  while that status exists. A teammate may trigger the event. Source controls
  cover this path; ordinary simulation validates the whole build. The receipt
  does NOT isolate a numerical Night-versus-no-set contribution.
- Xilonen:4 Scroll, DEF%/DEF%/crit damage. Infinite-energy pure team-DPS does
  not optimize ER comfort or healing sufficiency. This is not a universal
  finite-energy/Favonius/healer recommendation; do not change the objective
  silently to make the result look like a conventional guide.
- Columbina:2 Gilded +2 Tenacity, EM/HP%/crit damage. Ineffa:4 Aubade,
  ATK%/ATK%/crit damage. One-piece fragments and2+2 are legal stat choices,
  not an award for an inactive set bonus.

Remaining observable limits: close-rank stochastic swaps; formula underprediction
around .4-.5% on these finalists; opaque/approximate response boundaries; useful
multi-item improvements may remain beyond heuristic visits/sample pairs. No
physical UI check, Theory/Selected rerun, next matrix row or Gaming run occurred.

#### 2026-09-26: isolated player-requested artifact counterfactuals

This is an ordinary-simulator comparison, NOT another optimizer/matrix attempt.
Source is the unchanged Navia attempt3 top1 in the retained `after.json`.
`parametric_effects/compare_navia_user_swaps.py` reconstructs raw owned-artifact
rows through the existing config renderer, preserves character declaration order,
profiles, weapons, talents9, target, rotation and infinite energy. The
non-artifact SHA256 (blank rows excluded, n2000/workers4 normalized) is
`aeafea59e00bf0b4dbf920e6ebc89bef25791e600f79726e863b82ed3170554f`.
The active engine is still `gcsim-v2.45.0-20260926170526`,
artifact `93efe0efed194b4fffdee6d5340e2cf633232ded85a20230e5f7020465ccbf00`,
resolved through the app's ordinary artifact runner; executable path and final
identity checked. No engine, optimizer, equipment, settings or account edits.

Each row starts from the SAME top1, changes one wearer only, and uses twenty
distinct owned IDs. Columbina package changes and Xilonen off-piece relocation
necessarily change several items on that one wearer. Sixteen completed n2000
cases including baseline; no n128 screen or optimizer rerun. Independent random
samples, not paired seeds. Every completed rotation lasts83.166666667s.
Baseline126909.046 agrees with saved n500126945.304 within sampling error.

| Isolated change (IDs flower/plume/sands/goblet/circlet) | Team DPS | SE | Delta vs baseline |
| --- | ---: | ---: | ---: |
| none | 126909.046 | 34.750 | 0.000 |
| Navia plume1533->1535 | 126241.066 | 33.967 | -667.980 |
| Navia plume1533->2 | 126469.887 | 33.003 | -439.159 |
| Navia plume1533->1534 | 126373.275 | 33.763 | -535.771 |
| Navia goblet19->64 | 124943.986 | 36.457 | -1965.060 |
| Navia goblet19->88 | 125347.904 | 33.365 | -1561.142 |
| Navia goblet19->103 | 123137.813 | 33.711 | -3771.233 |
| Columbina1395/1598/33/1563/1614 | 124044.116 | 40.634 | -2864.929 |
| Columbina1395/1598/173/1563/1405 | 124415.112 | 37.790 | -2493.933 |
| Columbina1395/1598/48/1563/1405 | 123374.098 | 37.338 | -3534.947 |
| Columbina1395/1598/173/1563/203 (original matrix Navia rank3) | 124591.062 | 37.162 | -2317.983 |
| Columbina1395/1598/173/1563/1436 (Flins attempt3 rank3) | 124634.587 | 35.558 | -2274.458 |
| Columbina1395/1598/8/1563/1614 (original Flins control) | 123853.108 | 38.400 | -3055.937 |
| Ineffa flower1560->71 | 125624.342 | 31.272 | -1284.704 |
| Xilonen goblet54->34, circlet1617->1547 | 126080.222 | 36.723 | -828.824 |
| Xilonen goblet54->1285, circlet1617->1547 | 126956.637 | 36.682 | 47.591 |

The best tested Tenacity is the saved Flins assignment, not a certified exhaustive
Tenacity optimum. Relative to baseline, its engine-attributed character DPS
changes by Navia+1162.094, Xilonen-301.628, Ineffa+1893.104,
Columbina-5028.028. The ATK buff operates; the inventory/stat tradeoff loses more.
All three Navia feathers and three ATK goblets lose well beyond sampling noise.
Xilonen DEF-circlet/Geo-goblet is inconclusive: +47.591, approximate95% difference
interval +/-99.036 DPS. Do not call that a search defect or a confirmed gain.

Source-backed interpretation: Navia snapshot CR68.664%, with active Night4
+30% =98.664%; plume1535 raises active CR to105.264% while losing47EM,
3.5%ATK and2.3%CD. Ineffa uses Ballad of the Fjords R1: snapshot CR89.764%;
flower71 raises it to104.964%, losing21.8%CD,6.4%ATK and19flatATK.
`pkg/reactable/lunarcrystallize.go` and `pkg/core/combat/reaction.go` compute
the ordinary Lunar-Crystallize contribution from level/EM/crit and reaction
modifiers, not the contributor's ATK/DEF/Geo stat. This is NOT a rule for every
direct Lunar talent or indirect team buff. Navia's engine-attributed LCr line
with goblet64 rises12381.675->12591.670, but its other damage falls
36990.473->34793.137; gains do not cover losses. Reaction damage attribution is
last-trigger ownership, not an isolated personal-contribution decomposition.

No owned DEF-main Scroll circlet or DEF-main Scroll goblet exists. Xilonen's
tested DEF circlet1547 therefore requires Scroll goblet34(EM) or1285(Geo) to keep4p.
This relocates the DEF main from goblet to circlet; total DEF is63 lower, not higher.
She has Favonius R3, not her signature. These are real-build comparisons, not a
clean increased-DEF sensitivity test or a healing/finite-energy recommendation.

The first Tenacity attempt hit240s during a user-confirmed computer freeze;
it is excluded, not an engine/set bug or a DPS result. A later short n10
baseline/Tenacity diagnostic passed; completed n2000 cases take37-44s each.
An interrupted short diagnostic had no recovered numerical receipt and is not
counted. Initial preparation also rejected an extra blank row left by removing
two set declarations; normalization now ignores ONLY blank/artifact rows and
tests still reject changed actions/profiles. Main managed jobs removed977118
and1258498bytes; successful short diagnostic removed278190bytes. No raw output
retained. Fifteen focused probe/lifecycle tests pass. No physical button click,
new formula capture, broader search-optimality claim or next matrix team.

Exact n2000 config SHA256 values (reproducer owns the explicit replacements):

```text
baseline a2a5d709fd8b1034d2391008e72dbc59295cb12fe31746f9c84d603cfe9e9103
navia_plume1535_cv38.9 2839e1f5288950fb50e58efae34dea2939918bddb27811378c287baca93a545c
navia_plume2_cv35.8 8f3a84970980b7bccb75e5385840f3fb6a7564442f45c5cf604bcefadd98b687
navia_plume1534_cv34.1 b9c96c0ead7eb51651b57d0b3e75c2590c9b0845b616d725268c67ecb0a2b501
navia_goblet64_atk_em63 274c37d6bd17b963cba45cee93cc4adfeefbb1cc6388aae1abb3653b85475129
navia_goblet88_atk_cv36.6 de67a7134083c683df9fed23d2e14801387c969f2514a4a049b4cb778cc43dd4
navia_goblet103_atk_cv38.8 bce3fa5a1dfbe2ef1e803ac76d7c5b2dadb2535d334ec178ba22024c77fadce7
columbina_millelith_free_em_sands 885e79389fbbd1af43129984b54e22f480bc4db5a931f21aa647c11086d94319
columbina_millelith_em_sands 7329306c2391766b4ce9bc8fff6cdc4140a2aaea2700dae2f001ca9694cd889e
columbina_millelith_hp_sands ade4c95b1019f9c837b5eb2bfcdb56cd63f0ffd80c9f9e8b3c1184a9db91b803
columbina_millelith_saved_navia 48ed7d1d5b2d1b0f3eba8dab01189a5d507ff357584f1cd34a998b4dd2c005a2
columbina_millelith_saved_flins f4e579144c9769d946b0e22ef20e501f25d4e6452e0a0069ee6e80b5f3a4fede
columbina_millelith_free_hp_sands 6f02b814e88b161c6696a50f67e68e82bede6a3906fbde16b494ee704f102b94
ineffa_flower71_cr17.9 6d1e889076af85de9c06c1d7695baf23fdc09666cc5d926637ccf8879de5ed50
xilonen_def_circlet_scroll_em_goblet c96764743b62de9546d07d5757c0dbb7e26826307e1ab83f9fd658fa6783cb7d
xilonen_def_circlet_scroll_geo_goblet b146236009fe2aade9fe10f567e0120ba41f0622d9ed1b874020c7183d5ad4d1
```

#### 2026-09-26: user Chasca startup failures, read-only diagnosis

Scope: user's actual default-rotation Chasca/Furina/Bennett/Ororon runs, not
the virtual matrix fixture. No new simulator capture, optimizer search, product
code change, engine deployment, UI interaction or account/equipment write.
Active engine remains `gcsim-v2.45.0-20260926170526`, artifact SHA256
`93efe0efed194b4fffdee6d5340e2cf633232ded85a20230e5f7020465ccbf00`;
installed consumer remains `6ea621a7416bf3d98cceea64fa2b07f9ce55e0d071aee2bdad8445346ca6b9d9`.

Three existing product directories under `data/gcsim/optimizer-go-runs/`:

| Local start / directory | Observed outcome |
| --- | --- |
| `all_sets-20260926-221820-b9c37826` | Failed after6.344s: `prepared config artifact IDs differ for chasca`; no serialized request or compared ID arrays survived |
| `selected-20260926-222343-fa20a7d9` | Success,107.562s; winner151342.559481 DPS, n500, SE89.265; request prepared config equals the next All Sets config byte-for-byte |
| `all_sets-20260926-222806-1d2eda4d` | Failed after33.530s: `initial package requires an unsupported rule/schedule route`; request validation passed and two neutral captures survived |

All three rotation files have SHA256
`ae0b1bec1844338f24cc863ef859a0f4dcf4dca1f156b0274b240795be07f8ff`.
The two serialized requests bind the same currently installed engine, with
infinite energy, account profiles C1/C2/C6/C6 and initial4p Obsidian/Golden
Troupe/Noblesse/Scroll. All Sets canonical request identity is
`2047e758f37ac3e0c5893a4c9e2e53d9449e220dbb25a772887a9515acd25d2d`;
request file SHA256 is
`575907b62e763870fc889f9634d2da5ae9f7bd0b577a53d385f5a172c03af539`;
source-envelope file SHA256 is
`ccf507d42c87701d1d17233edbc0b41b6e979872fd2e24e12d9a2718f69ad71c`.
The first failure result file hash is
`98641a84e731e32a73db112f517a38164ea3ccef645b4dfe3b5afc120f94da77`.
These raw user runs retain their existing product-retention owner; no copies
or new output root were created. This compact receipt survives their retention.

**ID boundary.** `selected_team_config._selected_artifact_payload` prefers the
UI slot's `stat_snapshot.artifact.summary` / `artifact_build_snapshot`.
The optimizer independently calls `load_selected_equipped_team_snapshot`
against current database equipment, then `bind_selected_report_config_and_snapshot`
rejects differing physical IDs. Two focused diagnostic tests reproduce source
preference and the exact Chasca exception before materialization. The guard is
correct and must stay. A stale UI snapshot or an intervening equipment change
can cause this failure; the exact old IDs/cause of the22:18 event are NOT proven
because that input was not persisted. This boundary is shared with Selected;
its later success does not disprove a transient inconsistency.

**Neutral rule boundary.** Opt-in `TestSavedInitialPackageDiagnosis` reads the
actual two saved members, verifies member/sidecar and binary hashes, compiles
the original source bundle with the original inventory gate, and compares
cached composition with full source replay. Both return the same boundaries:

| Isolated package on its original wearer | Neutral effect compilation |
| --- | --- |
| No sets | Complete |
| Chasca Obsidian2/4 | Complete |
| Furina Golden Troupe2/4 | Complete |
| Bennett Noblesse2 | Complete |
| Bennett Noblesse4 | `query Extra filter unresolved` |
| Ororon Scroll2 | Complete |
| Ororon Scroll4 | `query Extra filter unresolved` |
| Original joint package | `query Extra filter unresolved` |

Complete here means no missing-rule boundary, NOT exact changed-set response:
existing callback/task/energy approximation flags remain. This is not a DPS
comparison. Seeds742031889/742031890 each contain36 failing query ports:
Bennett HP%4, flatHP4, outgoing healing4, Furina outgoing healing24. First
failures are Bennett HP% at frame718/order11751 and frame774/order12387.
Their exported mode is literally `unresolved`; no time-budget exhaustion,
item ranking or shortlist has occurred yet.

Causal code chain: engine adapter `pkg/gttcompact/support.go` reconstructs
health source-template stat parameters (`parameterNode`) and outgoing healing
(`compileHealthOperation`) through `artifactDelta`, while the current input
point comes from a health event. `neutralEventPoint` only identifies stat-input
channels and MaxHP-read events, leaving those health-origin ports unresolved.
Consumer `rule_replay.go::query` rejects the unknown Extra-filter mode as soon
as an active stat modifier reaches it, BEFORE stat filtering/vector extraction.
Thus unrelated ATK/elemental bonuses can trip HP/healing ports as well; this is
not evidence that Noblesse or Scroll is inapplicable. `RunNeutral` then aborts
because the INITIAL package has no model, hiding specific reasons behind the
generic startup message. Selected captures its chosen set effects in place
and does not run this neutral changed-package binding, explaining the contrast.

Next repair scope, not implemented here: unify optimizer input snapshots without
discarding identity validation; preserve original getter owner/time/Stat versus
NonExtraStat and selected-stat semantics for health-derived inputs; permit
source-PROVEN irrelevant effect exits, not a blanket unresolved-to-stat coercion;
retain useful failure details and handle an unmodelled initial package without
pretending its bonus is zero. Verify changed-input response on this healing team
before replaying its exact product request and checking the user button path.
No named set/character allowlist, gameplay implementation rewrite or budget rise.

Checks: saved-tape diagnostic PASS (10 package cases, two members, cached/full
failure parity),7 Python input tests PASS including two added reproducers.
The diagnostic's PASS confirms reproduction, NOT repaired All Sets. Two managed
Go jobs removed67626234 and67636304bytes respectively; zero jobs retained.
Helper source is opt-in/test-only and retires with parametric research after
the Chasca startup gate; existing managed-runner tests own cleanup/preservation.

#### 2026-09-27: Chasca startup repair, installed replay and physical dispatch

This supersedes the preceding read-only diagnosis's next action, not its failed
evidence. Original user logs remain intact. The repair is shared/generic, not a
Chasca, Noblesse or Scroll allowlist; ordinary character/artifact implementation
files are unchanged. No account/equipment/settings writes or larger budgets.

**Input boundary.** Selected/All Sets first identify actors, freeze inventory
and current equipped IDs, then rebuild only physical artifact summaries in a
copied team payload before the strict config/ID/stat/set binder. Nonempty virtual
overrides and Theory remain distinct. A cheap isolated edge audit found a second
race: unchanged IDs could hide an inventory stat/set edit between two reads.
The equipment read transaction now hashes the same raw artifact/substat rows;
a differing frozen digest fails explicitly rather than combining versions.
Virtual anchor summaries use frozen rows, with no later DB read. Connections
are query-only, rolled back and closed. Tests cover stale UI summaries, 2+2,
TeamBuilder payloads, slot/character identity, empty versus explicit virtual
overrides, no caller mutation, concurrent same-ID edits and frozen virtual data.
Latest four focused input/Selected/All Sets/database modules:35 tests PASS.
Historical22:18 conflicting IDs were not retained, so their precise cause is
still unproven even though the reproducible mechanism is removed.

**Health provenance.** Trace-only source generation follows a unique local RHS
through enclosing lexical scopes into delayed health callbacks. It captures
amount and outgoing-healing Bonus separately once at their original evaluation,
preserving typed receiver, query mode and time; omitted Bonus is literal zero.
No later MaxHP reread and no unconditional caller-healing artifact delta.
Raw Stats reads carry an origin reference through proven private same-file
helpers; every callsite must use the same typed receiver and an unchanged array.
Indexed cells validate origin/value; mutation, aliases, escape, extra consumers
and unsupported scalar aliases fail closed. `source_bonus` has explicit state
shape/value validation. Initial-package errors now expose their actual boundary
reasons. Unknown query modes are never relabeled ordinary Stat by assumption.

Both exact original neutral seeds742031889/742031890 change36 unknown query
ports to0. Original combined package and each original2p/4p component compile;
cached/full replay agree. Existing callback/energy/health schedule approximations
remain, so complete binding is not universal changed-input response acceptance.
Focused sourcegen/coreinfo/compact/optimization tests, full sourcegen/coreinfo/
compact/template-character packages and all14 native Go packages pass. Original
set control capture retains identical duration/damage channel values. Relocated
installed capture passes expression/port/owner/time semantic comparison.

**Deployment.** Production stack remains `run_workspace/gcsim/patch_stack`;
fragments consolidate into0009 through the ordinary updater, not a second stack.

| Identity | Value |
| --- | --- |
| Active / rollback | `gcsim-v2.45.0-20260926211654` / `gcsim-v2.45.0-20260926170526` |
| Engine SHA256 | `5a20524165b1e764f32a868e9dec5432b511380acae92279431604f0bc4f2969` |
| Source manifest SHA256 | `662d1b02f96d5141bc79819087d16dcfdda24363076b2e2e8ff5315596e14c67` |
| Patch stack SHA256 | `8274b6e10b3fc0012d3ed380124ce6ea031b65354be0a23d72734504ddfd038a` |
| Patch0009 SHA256 | `31ada56c4814d949dec8918d60335e7ca33b60806d6b2e8eac9617abe6834305` |
| Consumer SHA256 | `b0298b767879d31457c69aa96bbd62732df6a6afa06d920252ff283f82a703c8` |

Failed gates preserved compactly: a negative fixture replacement referenced the
wrong local variable (fixed); a candidate with unsafe scalar alias inference was
cancelled before activation and narrowed to raw cells; delta export represented
a deleted Go file as empty, corrected using actual git deletion plus real
apply/regression tests; first source-bonus capture was rejected by missing
validator support, repaired with positive and mismatch/missing-source tests.
Previous active engine survived every failed/cancelled gate. Managed jobs removed
400993780,990845177,709473665,418565072,1534914060 and1530237284bytes respectively;
no expanded deployment tree remains. Exporter regression suite6 PASS; bounded
receipt helper suite6 PASS. No failed run is relabeled acceptance.

**Exact request replay.**
[Immutable receipt](../optimizer-evidence/all-sets-inventory-20260919/chasca-user-startup-attempt1-20260926.json)
uses the saved22:28 request:597 items, profiles, rotation, target, constraints,
two seeds and1080000ms product budget unchanged. Only installed engine binding
and explicit trace-context digest change. Original raw request SHA256 remains
`575907b62e763870fc889f9634d2da5ae9f7bd0b577a53d385f5a172c03af539`.
The production All Sets Python preflight/source/process methods use the same
installed executable as the button. Elapsed197.141s is this prepared-request
adapter boundary, NOT a fresh full UI request timing. Go model/search162.678s,
nested proposal79.364s, rules42.112s, binding22.463s; counters overlap.
Two neutral captures and seven ordinary n500 finalist measurements, no n128
ladder. Winner153190.369 DPS, SE99.271; formula151793.049, residual1397.320/.912%.
Historical same-config Selected151342.559/SE89.265 is a separate old-engine run,
not an isolated speed/algorithm comparison. Winner sets: Bennett Noblesse4,
Chasca Obsidian4, Furina Tenacity4, Ororon Scroll4. Six non-baseline finalists
finish full single-item neighborhoods and sampled-pair stabilization. Both
cycles prepare2096/2096, unavailable0;3538 heuristic deferrals remain. Stop
`neutral_cycle_budget` is neither timeout nor exhaustive/global-optimum proof.
The managed replay removed53713096bytes after exporting the1.09MiB receipt.

**Physical button scope.** Confirmed actual PyCharm launcher
`.venv/Scripts/python.exe ui/app_shell_smoke.py`. Selected the four physical
characters, opened GCSIM/Artifact optimizer/All Sets, observed search start,
cancelled at41.436s and closed the window. No child optimizer/simulator remained.
Run `all_sets-20260927-002759-398550e5` binds the new engine/consumer; its items,
wearers, prepared config, rotation, target, constraints and budgets match the
original22:28 request. UI preparation5.453s/source7.719s/preflight.109s are scoped
to this cancelled route check, not a complete search time. Three offscreen Qt
routing tests also pass. CU is stopped. Final visible result/paging/Save remains
open; the receipt's `physical_button_verified:false` correctly describes the
programmatic replay itself, with this separate physical gate recorded here.

**Ownership/next action.** CODEX now permits cheap low-context isolated agents,
without forking main history; parent owns integration and reviews each matrix
row. One heavy job at a time. Resume one saved matrix row, exclude Gaming and
preserve every attempt/baseline. Startup helper output is exclusive-create,
at most three2MiB receipts; expanded captures belong to tested managed scratch
and clean on success/failure/cancel. Health fragments/installer/replay helpers
retire with the existing parametric research cleanup after acceptance evidence
is closed; production0009, regression tests and minimal receipts survive.

#### 2026-09-27: Lunar Bloom matrix regression and controlled recall diagnosis

After the Chasca gate, a fresh low-context Luna/max agent ran exactly
`lunar_bloom_all_sets --retry` (attempt2); parent reviewed it before any next row.
No Gaming or unattended batch. Original fixture/before.json SHA256 remains
`00a0cd81711081e867faf06cad9230471ada6c4ecd956104181a69187231a152`.
Every attempt survives in the [comparison receipt](../optimizer-evidence/all-sets-inventory-20260919/after.json).

| Retained result | Measured DPS / SE (n500) | Whole row seconds |
| --- | ---: | ---: |
| Original matrix | 125679.368 /71.246 | 251.6 |
| Old inventory-search attempt1 | 129788.909 /93.747 | 679.875 |
| Neutral attempt2, consumer `b0298b76` | 120983.445 /66.507 | 189.938 |

This is NOT accepted acceleration: measured quality regresses. Profiles and
rotation are identical across attempts; rotation SHA256
`6965ce026d14632731b4afc8935e69c63d54b26df8f13ffb56144e0c1f71bb0c`.
Recorded search configuration matches, but pipeline/engine and inventory differ.
Inventory SHA256 changed from
`e39e6051c2bf80396fd1274f3b254118c3578cf417ce19a56340d7dbf33efe43` to
`146de0c8d10ee0a813bfc5b501fc81eea879f714fe1a79d5f98bb523914d8101`;
old per-item stat snapshots were not retained. Therefore old/new row differences
alone cannot isolate a search regression. The controlled diagnosis below does.

Attempt2 uses the installed health-repair engine. Search146.498s; nested
proposal90.561s/rules70.817s/bind20.683s. Two cycles prepare2096/2096 each;
3372 heuristic deferrals and6 unavailable package bindings (Scroll's target
interface observation,3 per cycle). Stop `neutral_cycle_budget`, not timeout.
Its winner has Deepwood4 on Columbina/Kuki/Nahida and Serenade4 on Lauma;
formula121666.552, residual−683.107/.565%. Six finalists finish single-item
stabilization, which fixes artifacts only inside their existing packages.
Managed matrix output removed91602229bytes.

**Controlled current-input evidence.** The bounded helper
`parametric_effects/diagnose_bloom_candidates.py` reconstructs the same current
product request and verifies its exact inventory/config hash before work.
`TestMatrixCandidateDiagnosis` uses one current-engine two-seed neutral panel
and the production source model/domain for exactly two retained assignments:

| Candidate, actor order Columbina/Kuki/Lauma/Nahida | Current formula DPS | Current ordinary DPS / SE |
| --- | ---: | ---: |
| Old winner: none /Serenade4 /Gilded4 /Deepwood4 | 130466.058 | 129986.080 /97.729 |
| Attempt2 winner: Deepwood4 /Deepwood4 /Serenade4 /Deepwood4 | 121666.552 | 120983.445 /66.507 (matrix) |

Both assignments pass current physical-ID/package legality and source binding;
new-winner formula exactly reproduces attempt2. Old-winner ordinary n500 uses
the same current virtual profiles/rotation/target/energy mode and current item
rows. Only artifact declarations change; all other nonempty source lines and
their order are identical after normalizing the shared iteration/worker budget.
Config SHA256 `b9a7b8645e52b2b3fef39bf9ef938842916c36cfae5d52279f7413960e634a8d`;
non-artifact SHA256 `fc71e42f05eefc7d4bb5ab4277eacf240985f75d8453a492a3610cf5363b6221`.
This establishes a legal current candidate about9002.6 DPS stronger than the
search output. It is a recall defect, not unknown old inventory or simulator
noise. No new long optimizer search was needed for this diagnosis.

Failed probe setup is retained: first attempt lacked an existing provider output
directory (fixed; no capture); second passed both formula checks but the old
Flins comparison helper's raw non-artifact hash counted blank lines left by
different numbers of set declarations. It correctly stopped before simulation.
The new helper ignores ONLY empty lines after deleting artifact declarations;
two tests retain changes to actor order, levels, actions and options. Ordinary
control then ran alone, without repeating captures. Managed cleanup removed
71322282,159702020 and329759bytes respectively. Combined comparison/retention
tests9 PASS. All expanded graphs/configs/results remain disposable; this dated
receipt and existing winner IDs own durable reproduction. Helpers retire after
this matrix regression gate; no new unbounded output family.

**Code cause and bounded repair.** The old cycle froze one team for all wearers,
scored every replacement relative to it, then combined four independently best
conditional choices. This is invalid as an independence assumption for shared
nonstacking effects: several wearers may each choose the same first team buff.
Full-team scoring checks that combined build, but only two stale-anchor sweeps
can leave the redundant packages in place. The permutation lane only rearranges
packages already present; final item stabilization cannot introduce a new one.
The source model DOES rank the known stronger combination correctly.

Coordinator now uses sequential actor blocks: screen/refine a wearer against
the latest accepted complete team, then proceed to the next wearer. Same
feasible domain, two-cycle/work/time limits and ordinary-finalist cap; no named
set exclusion or hard bound inferred from gradients. This is block-coordinate
improvement, NOT global optimality: joint non-improving transitions and heuristic
deferrals remain limits. Installation and attempt3 acceptance follow below;
source edits alone do not establish that the matrix regression is fixed.

Consumer installation gate passed: all14 native packages and the active-source
tiny inventory exhaustive oracle (best25.475), now asserting every actor block
uses the prior completed team's assignment/DPS, never decreases the incumbent,
and preserves complete/partial budget accounting. The toy shared-bonus fixture
was considered but NOT implemented/executed; do not claim that separate test.
Six installer transaction tests cover preservation, build/oracle failure,
concurrent changes and copy rollback. Consumer SHA256
`c63e35410666c580e2ec18cf76512c4e9b642d7cffb9d23cb8207de1c90e55eb`
replaces `b0298b76`; active engine/patch/source are unchanged. Managed installer
removed166672850bytes. The original matrix install.json was not overwritten.
Actor anchor/complete markers survive in the normal compact search-work receipt;
they are not additional captures or simulations. Attempt3 runs through the
installed product session, not this test's provider.

**Attempt3 outcome: partial recall repair, not acceptance.** Low-context Luna/max
ran only the same matrix row; parent compared its identities and actor markers.
Request SHA256 `f9daec74315f896a96627d14cf93b183a7b8e237c041bdb0729cb98c9a121d4b`,
inventory/rotation/engine identity, full prepared config, virtual profiles and
recorded search settings exactly match attempt2. Only the optimizer changed to
`c63e3541`. Original fixture and before.json remain byte-identical.

| Current-input comparison | Formula DPS | Ordinary DPS / SE (n500) | Whole row s |
| --- | ---: | ---: | ---: |
| Attempt2 | 121666.552 | 120983.445 /66.507 | 189.938 |
| Sequential attempt3 | 129232.655 | 128737.946 /76.687 | 188.406 |
| Retained old winner, controlled current-input recheck | 130466.058 | 129986.080 /97.729 | not an optimizer run |

Gain7754.501 DPS (+6.41%) is not a time-budget increase. Remaining gap1248.134
DPS is about10 combined SE, so it is not explained by ordinary sampling noise.
Formula underprediction494.709 DPS/.384% is smaller than attempt2's residual,
and the formula itself prefers the missed control. Rank2 is128734.046/SE75.419,
a noise tie, not a meaningful ordering difference.

Top1 (flower/plume/sands/goblet/circlet): Columbina Deepwood4
`90/1351/1355/1563/109`; Kuki Serenade4 `66/67/68/213/1626`; Lauma
Night2+Wanderer2 `1/1536/127/34/129`; Nahida Deepwood2+Gilded2
`31/81/112/108/35`. The redundant three-Deepwood4 winner is gone.
Each actor's completion becomes the next actor's exact assignment/DPS anchor.
In cycle2 all four actor blocks retain the129194.593 formula anchor; later
finalist stabilization and measured ranking select the result above.

Search151.575s; preparation/proposals82.696s, rules67.371s, binding20.361s,
joint refinement.142s (nested counters overlap). Python preparation5.125s,
source preparation7.078s, preflight.125s; seven ordinary finalists22.137s.
Stop remains `neutral_cycle_budget`, not timeout. Two cycles prepare2096/2096
each; heuristic skips1111+1539=2650, six unavailable bindings and1080614
expansions. Pending4186 counts non-exhaustive search regions, not unfinished
preparation. Five distinct boundary strings concern Scroll's unobserved target
interface; six is the invocation count. No renewed health-query failure.
Managed output cleanup removed93106032bytes, with no job left running.

**Remaining mechanism and next decision.** Sequential blocks repair stale-team
scoring but follow only the current best team. `permutedPackages` rearranges
already present packages; it cannot replace a package with a new zero-bonus
choice while relocating its team effect to another wearer. `RefineJoint` and
final `Stabilize` operate inside fixed packages. These are verified structural
limitations; the precise contribution of coupled package changes versus
heuristic deferrals to the remaining1248 DPS miss is not yet isolated.
Proposal: a bounded joint package relocation/replacement lane, retaining a few
distinct complete-team alternatives and evaluating replacements through the
same formula/physical-ID legality. First prove a small shared-bonus relocation
fixture against exhaustive enumeration, then a controlled same-input matrix
comparison with unchanged time/simulator budgets. No set-name whitelist or
claim that low gradient proves domination. A pair lane still needs a bounded
diverse-team escape for three-way dependencies; do not promise global recall.
All three original row attempts are used. Preserve them and request permission
for the next joint-package stage/comparison rather than silently raising the
retry limit, disguising a fourth run or advancing the matrix. Combined helper/
installer/retention tests15 PASS; all14 native packages and the tiny active-source
oracle passed before installation. No fourth row attempt or next team ran.

#### 2026-09-27: approved bounded joint package replacement gate

User approved the proposed joint-package stage and one further Lunar Bloom
comparison after reviewing the partial attempt3 repair. This is an explicit
attempt4 authorization, not an unattended matrix restart or higher search budget.

`package_joint.go` adds a bounded complete-team frontier (three distinct package
tuples). Each completed wearer block retains three conditional package proposals;
the joint lane also always considers zero bonus and transferring the other
wearer's current package, even if those single changes scored poorly. For each
wearer pair it proposes replacements of BOTH packages, reserves the other ten
physical IDs, and evaluates both allocation orders. Gradients seed legal items;
the new complete tuple is bound through the existing neutral model and scored
as full team DPS. Screens refresh gradients under the changed bonuses. At most
three distinct complete tuples then receive fixed-package item refinement before
the next already-configured cycle. Incumbent improvements are monotone; lower
frontier alternatives may survive. Unchanged leader alone is no longer a stable
stop if the retained team frontier changed. Current limits, simulator finalist
cap and single neutral capture are unchanged.

This is NOT exhaustive joint search: at most450 pair proposals per lane before
feasibility, three roots and three deeper refinements. One physical assignment
per package tuple is a heuristic root restriction: alternative item layouts stay
in the normal candidate/inventory domain, but fixed-wearer reservations can
still hide another useful layout. Three/four-way package interactions and lost
frontier alternatives remain possible misses. `neutral_package_joint` records
seeded/scored/unavailable/deferred allocations, roots/refinements, elapsed time
and bounded-lane completion separately from global optimality. No set-name
allowlist or proved-pruning claim was added.

Luna/max independent review found a near-tie ordering defect: combining an
epsilon comparison with lexical tie-breaking is non-transitive. Neutral
frontiers and shared All Sets candidate sorting now use strict finite-DPS order
(energy feasibility/shortage first where applicable), then deterministic identity.
The improvement acceptance tolerance remains separate and unchanged.

Validation: all14 native packages PASS, including the new finite synthetic
shared-bonus oracle against all3x3 package tuples (both individual moves lose,
joint move finds the best20 versus initial13), inactive synthetic bonus,
near-tie/deterministic frontier and cap checks, cancellation/partial retention,
and real-ID reservation/exact-none allocation tests. This synthetic objective
does not assert real-game effect semantics. The active-source production
coordinator oracle also PASS: one capture, best25.475 equals exhaustive inventory,
2774 work units, both joint lanes finish within the shared allowance. Python
installer, receipt retention/authorization and candidate diagnosis tests19 PASS.

Installed consumer SHA256
`2fba066e1bd2428132c7305161b33eafa3b6177b7a459e3ef2a349d0635b878b`
replaces `c63e3541`; engine/patch/source remain unchanged. Managed base native
check removed70997003bytes; full test/oracle/build/install removed167257486bytes.
The original install.json and all historical matrix rows remain untouched.
Expanded graphs/build outputs stay disposable. To retain the explicitly approved
row without deleting earlier evidence, the existing runner keeps its8MiB legacy
cap plus at most3MiB for ONLY the authorized fourth Lunar Bloom row (11MiB total).
Guards reject wrong cases, missing retry, reuse/fifth attempts and size overflow
before replacing the old receipt; focused preservation/boundary tests pass.
The actual attempt4 quality/runtime result follows; installation is not acceptance.

**Authorized attempt4: known-control recall PASS, runtime increase disclosed.**
Luna/max ran only `lunar_bloom_all_sets --retry` with the explicit attempt4 flag.
Parent reviewed the retained row independently. The installed2fba066e consumer
produces133667.674601 DPS/SE77.003025 at n500, formula134320.817257,
residual−653.142656/.489%. Whole session218.359s versus188.406s in attempt3:
+4929.729 DPS (+3.83%), but+29.953s (+15.90%). The legal current-input old winner
129986.080/SE97.729 is exceeded by3681.594 DPS (+2.83%), about29.6 combined SE.
This passes this known-control recall gate, not universal optimality or speed.

Inventory SHA256 `146de0c8d10ee0a813bfc5b501fc81eea879f714fe1a79d5f98bb523914d8101`,
input profiles, full prepared config, rotation SHA, engine identity, search
settings, initial20 physical IDs and initial44292.016777 formula score all match
attempt3. Both capture seeds remain742031889/742031890. The raw request SHA
does NOT match: `beaf6cbdb4d5c97e16c3ef33fe6092f2932bcf62d8368889202cddd34507ce4e`
versus `f9daec74315f896a96627d14cf93b183a7b8e237c041bdb0729cb98c9a121d4b`.
Raw requests were disposable and not retained; the exact differing field was
not isolated. The producer hashes full raw DB/snapshot provenance as well as
gameplay fields, but provenance drift is a hypothesis, not a proved explanation.
Therefore this receipt claims explicitly checked gameplay equality, NOT complete
byte-identical requests. Formula topology/coverage summaries agree; parent also
compared all eight first-cycle actor anchor/complete records excluding context
digests/timing: assignments, packages and DPS are exactly identical before the
new joint lane. No new capture or optimizer run was used to investigate hashes.

The first joint lane supplies a direct mechanism witness: Columbina becomes
zero-bonus while Nahida takes Deepwood4, reaching133222.992292 formula DPS.
The subsequent existing cycle improves Columbina to Tenacity2+Wanderer2.
Top1 physical IDs (flower/plume/sands/goblet/circlet):

| Wearer | Package | IDs | Sands / goblet / circlet |
| --- | --- | --- | --- |
| Columbina | Tenacity2 + Wanderer2 | 1395/111/1466/1563/1436 | HP% / HP% / CD |
| Kuki | Serenade4 | 66/67/68/213/1626 | EM / EM / EM |
| Lauma | Night2 + Wanderer2 | 1/1536/127/34/129 | EM / EM / EM |
| Nahida | Deepwood4 | 105/81/112/108/109 | EM / Dendro / CR |

Ranks2–5 ordinary DPS/SE are133127.167/76.487,132866.986/84.180,
132853.548/77.299,132822.978/65.230; nearby lower ranks are noise-scale.
Seven ordinary finalists remain n500 once each, verification26.284s. Search
176.135s; proposals88.042s, source rules75.565s and binding28.532s are nested
measurements, not additive phases. New joint lanes cost7.228+8.284=15.511s,
with272+288=560 proposals,350+410=760 scored legal seeds and six refined tuple
representatives. Both bounded lanes finish, with zero allocation deferrals or
unavailable joint seeds. These15.511s do not explain the whole29.953s wall
increase; changed downstream work and run-to-run overhead also contribute.

Stop remains `neutral_cycle_budget`: two2096/2096 coordinate screens,2619
heuristic skips,4186 non-exhaustive regions, six unavailable Scroll bindings,
1134297 expansions. This is not a timeout or exhaustive search. Active source,
engine and simulator budgets are unchanged; no UI check was repeated. All four
attempts remain in after.json (9126547bytes before the later parent status text
edit), with original baseline untouched. Managed cleanup removed93196284bytes;
no job/process or fifth attempt/next row remains. Next work is preparation-cost
review before another single matrix team, not a larger timer or a full matrix.

#### 2026-09-27: lossless neutral preparation reduction

Preparation after the authorized Lunar attempt4 was the next approved task;
this change does not add a fifth Lunar run, candidates, cycles or simulator calls.
Engine `gcsim-v2.45.0-20260926211654` and artifact SHA
`5a20524165b1e764f32a868e9dec5432b511380acae92279431604f0bc4f2969`
remain unchanged in this preparation-only deployment. The consumer is
`bd9d7758ed3d492d2765bb8437cacdb932f74123bcff5ea37c689d060a714aab`,
replacing `2fba066e1bd2428132c7305161b33eafa3b6177b7a459e3ef2a349d0635b878b`.

Three preparation-only changes:

- `CompilePackagesCompact` returns fully composed constant effects as one dense
  vector. It keeps the existing legality/footprint/conflict checks, summation
  order, post-sum resistance transformation and uncertainty. First single-source
  replays, symbolic amounts and joint fallbacks keep the expression-map route.
- `NeutralModel.bindConstants` validates a full capture-port/formula-key
  bijection once, validates ALL finite values including latent ports before a
  projected cache lookup, and shares the existing exact-bit cache/FIFO/node cap
  with map binding. The same ordered reduction performs constant binding; this
  is neither source-rule skipping nor a new damage formula. New model counters
  distinguish `ConstantVectorBindings` and `ExpressionMapBindings`.
- Replay's single-entry, host-local world cache reuses converted snapshot
  fields only for the same immutable ledger pointer/index. Every call restores
  the baseline after query-local state overrides; backward/task/cross-world and
  invalid lookups retain their old semantics. Modifier replacement/deletion
  lookup uses typed owner/target/key identity instead of formatted strings.

Managed install gate: all14 native packages PASS; active-installed-source
rule/port/shared-bonus/unknown-boundary/symbolic controls PASS; tiny production
coordinator oracle still reaches25.475 with2774 work,42 modeled contexts and64
refinements. Dense/map tests include reordered ports, signed-zero keys,
nonfinite latent values, exact general-binder graph/gradient parity and raw
resistance composition. World sequence tests compare with the original
conversion, including query overrides/deletion. Two capture-only opt-in tests
were SKIPPED: no new capture was supplied to this unit gate. The subsequent
retention/identity/install helper suite passes26 Python tests.

Managed microbenchmark on this machine (not whole-search speed): composing
16012 constant ports takes2.706547ms/map versus0.460810ms/dense (~5.87x),
2031444 versus263467 bytes and16099 versus21 allocations per operation. A
repeated SAME-world-index lookup takes26.27ns/0alloc versus2326ns/6alloc for
the original conversion: a cache-hit best case, not a replay-wide multiplier.
Search domains, candidate ordering, numeric operation order and budgets are
unchanged. No claim that whole All Sets is5.87x faster follows from this.

The matrix successor receipt serializer now removes indentation without removing any
field/attempt or increasing its8MiB/3MiB/11MiB caps. Round-trip of the existing
14 attempts is exact (9126597->4078036bytes before the next row); immutable
`before.json` is untouched. Human-readable presentation remains the
[comparison report](../optimizer-evidence/all-sets-inventory-20260919/report.md).
Retention/overflow/failed-attempt preservation regressions pass. Managed native
gate cleanup removed167818038bytes; its job no longer exists. Ancillary agent
unit checks used the ordinary shared Go cache (not deleted); the managed gate
above is the authoritative validation. No engine/ordinary search was run by
those ancillary checks.

The first Bountiful neutral row (retained attempt2; Nilou/Kaveh/Nahida/Xingqiu)
FAILED in34.8s before item search: `initial package ... unbound neutral query`.
No DPS/search-completion result exists for that attempt. Its managed job removed
83675046bytes. A separate initial-only gate used the same active engine, exact
prepared config and inventory, captured two neutral seeds and compared the old
map and new dense paths. Both accept zero packages and both reject the starting
packages with the identical boundary. This isolates the startup bug from the
preparation representation change; it does not certify a repaired search.
The diagnostic removed155010379bytes; its job no longer exists.

The initial formatting change briefly also affected the shared inventory hash
codec. This was corrected: `json_bytes` retains the historical indented identity
encoding; only `receipt_bytes` is compact. A regression pins both. Attempt2's
original recorded digest is retained, not rewritten:
`2389ece299f2cf3011d16e80258be7fac252f49965c421a44c1bd8cbc8df29ac`.
The exact-input diagnostic verifies the same inventory under the historical
codec as `146de0c8d10ee0a813bfc5b501fc81eea879f714fe1a79d5f98bb523914d8101`.
This is an encoding discrepancy, not evidence of changed artifact contents.

Source diagnosis: Nilou's Tranquility Aura and Xingqiu's orbital call the generic
`QueueAttack` with a negative snapshot delay. These are real Hydro applications
with valid hit/attack order, but no character-stat snapshot. The compact exporter
previously invented both raw artifact dependence and a snapshot StatMod port at
order0. Removing those aura events would lose reactions; accepting every
order0/nil-origin query as zero would hide lost provenance. The candidate repair
therefore records the explicit omission on the queued attack (not on a copyable
Snapshot), keeps independent reaction/source reads variable and retains the
per-hit AttackMod input. Custom supplied snapshots remain un-attested. The
ordinary character/set implementations are not changed. The source fragment and
bounded repair/diagnostic helpers share the existing parametric-probe retirement
gate; generated sources, captures and caches remain owned by managed jobs.

Installed observer gate (same upstream lineage, consolidated production0009):

- engine `gcsim-v2.45.0-20260926234622`, artifact
  `e04b1e7e0dcdd6a9854b0538f5492d191d1f5170ce1923de096208441433725b`;
- source manifest `872f301bb7b9c93592957dabf61ccae9471d454be9a75c0471d00991fd6a7892`;
- patch0009 `71f34aa9df945fb32cb5cc1b14fadb3c2db0d9d18c1b33af9a8377572977ad54`,
  stack `67c4de845730a1c5ff2ed571069fe62685f677cba9712d2eab28b448dabc79ff`;
- consumer remains `bd9d7758`; rollback is the previous active engine
  `gcsim-v2.45.0-20260926211654`.

The first focused overlay gate passes, then review narrows omission handling
from generic `artifactDelta` to explicit `snapshotDelta` call sites. Independent
reaction-EM fallback, event reads and flat-template candidate parameters retain
their dependencies/boundaries. The marker belongs to AttackEvent, so supplying a
copied Snapshot through QueueAttackWithSnap does not inherit that assertion.
The final clean reconstruction/source-generator/compiler/character-template and
compatibility gates PASS; ordinary character/artifact source trees are identical.
All14 consumer packages PASS. Two new neutral seeds compile every initial2p/4p
package and the complete team with zero unknown query ports; map, dense and full
joint boundaries agree. Callback-schedule uncertainty remains disclosed, not
silently exact. Original-set old/new control hit damage is identical. After
transactional promotion, the actual installed executable reproduces the candidate
neutral expression/port/owner/time graph. This is an installed backend gate, not
a new physical UI click or a full item-search result.

Focused-overlay job removed409790572bytes; installation job removed1580207645bytes.
Both scopes are absent. No gameplay database/equipment/settings writes. The
following matrix attempt owns full-product acceptance separately.

**Installed Bountiful attempt3:** Luna/max ran exactly the one product-session
row; parent independently read the saved result. Active engine/consumer match
the identities above. Prepared config, input entry and rotation SHA match
attempt2; inventory digest matches its separately verified historical encoding.
The original matrix is byte-identical. All16 attempts including failure2 remain.

| Measurement | Original matrix | Historical attempt1 | Current attempt3 |
| --- | ---: | ---: | ---: |
| Ordinary DPS (n500) | 55640.014 | 57467.168 | 59811.818 |
| Standard error | 15.314 | 17.645 | 16.969 |
| Whole-session wall seconds | 167.25 | 469.578 | 122.859 |

Old engines and inventory differ (original inventory hash is unavailable), so
the historical rows are not an isolated preparation microbenchmark. Attempt3
has32.736s package preparation,84.775s total search and23.234s final verification;
rule18.874/bind17.408/replay12.251s are nested counters, not additive stages.
Of6286 model requests,6273 bind dense constants and13 retain expression maps;
5501 program-cache hits/785 misses,250 replays/31986 component hits. Both
joint-package lanes finish:572 proposals,787 seeds,6 refinements,10.231s total.
The separate older joint-item lane is0.106s, NOT the whole joint-package cost.

Two cycles prepare2096/2096 each, zero unavailable,2932 heuristic deferrals;
740068 expansions of the unchanged8m budget. Stop `neutral_cycle_budget` means
the configured two cycles finished, not timeout, exhaustive enumeration or a
global optimum. All6 searched finalists pass full final-team single-item
stationarity plus sampled-pair stabilization. Seven candidates including the
initial control receive one n500 verification stage. Winner formula59842.941,
ordinary59811.818, residual−31.122/.052%. Top1/top2 measured gap0.992DPS is much
smaller than their combined SE; do not sell their exact ordering as robust.

Winner (flower/plume/sands/goblet/circlet): Kaveh4Gilded
`31/1344/1576/1618/35`, ATK/Dendro/CR; Nahida4Deepwood
`105/106/112/108/129`, EM/Dendro/EM; Nilou2Tenacity plus individual pieces
`1587/1608/48/1563/225`, HP/HP/HP; Xingqiu4ParadiseLost
`147/1329/1337/34/1339`, EM/EM/EM. The apparent Kaveh/Xingqiu stat-role contrast
is a measured winner here, not a universal build recommendation. The witness
retains169 zero-damage Hydro aura hits with no invented artifact coordinates,
and161 Bloom-reaction hits with variable multi-owner EM/Nilou HP.

One presentation issue remains: `all_sets_unknown_effects_present` is emitted
for any coordinator boundary, including `joint_package_frontier_heuristic`,
despite zero unavailable packages here. This is distinct from the panel's
callback-schedule/formula uncertainty; do not erase real uncertainties merely
to remove that overbroad label. No extra product retry was spent on presentation.
Matrix job removed86561669bytes and is absent; the metadata-only closeout preserves
every row and generated no captures. No physical UI/Save check. Next is one
parent-reviewed matrix row, not Gaming or a fourth Bountiful/fifth Lunar retry.

#### 2026-09-27: sequential remaining matrix and warning classification

User approved remaining rows serialized through a low-context Luna/max runner,
with parent review before each next row; Gaming remains the separate deferred
rotation case. Chiori attempt2 is retained in `after.json`:106109.505 DPS,
SE64.607,n500,659.437s wall,615.196s search,99.979s preparation,28.177s final
measurement. Both2096-package cycles prepare completely;0 unavailable,2069
heuristic deferrals,1586561 evaluations,all6 finalists single-stationary.
Stop `neutral_cycle_budget`, not timeout/global optimum. Winner formula residual
−485.181 DPS(−.455%); original90369.2 differs in engine/inventory. Runtime is still
poor; no third Chiori simulation was run merely to measure speed again.
Cleanup removed89122187 bytes.

After Chiori, warning-only consumer
`bd5d1a02211d88351014657b0dc09eb3fdf7323510af15cf792cc310e84f2210`
replaced `bd9d7758…` through the managed install gate. Native14 packages,
active-source rules and tiny exhaustive oracle pass(25.475,2774 work).
Engine identity is unchanged. Search/allocation/stabilization bounds no longer
raise `all_sets_unknown_effects_present`; true/future unknown boundaries and
positive unavailable counts still do. Opaque formula uncertainty stays visible.
Cleanup removed167919227 bytes; no expanded jobs retained.

Future matrix receipts freeze up to60 distinct top-three physical item rows
from the exact request before cleanup. They retain at most64 detailed
intermediate work examples plus full-population hash/lane totals/extrema;
examples are explicitly not exhaustive evidence. All finalist measurements and
stabilization rows remain complete. Older attempts/baseline are untouched;
existing8MiB(+3MiB authorized Lunar row) cap and managed cleanup remain wired.
Eighteen runner/player-report tests pass. Top1 frozen item tables and only
top2/top3 changed slots are rendered; missing old item rows are never backfilled
from the live DB. Gaming is explicitly historical/deferred; receipt success
and latest-consumer provenance have separate counts, neither certifies acceptance.
This changes evidence extraction, not search or inventory identity encoding.

The serialized continuation then completed Spread attempt2(65612.195 DPS,
SE58.285,117.594s,residual−714.449), Aggravate attempt1(51371.470 DPS,SE38.567,
119.610s,residual+81.591), Vaporize attempt1(82257.399 DPS,SE84.651,272.032s,
residual−506.055). Each has two complete2096-package preparations,zero unavailable,
six single-stationary finalists and `neutral_cycle_budget`; no timeout/global
optimum claim. Unusual Noblesse Keqing and stat-only Deepwood pieces on Xingqiu
are player-review points, not proven regressions. Their final means exceed their
same-run equipped controls. All exact top3 rows survive from Spread onward.

Burgeon attempt1 FAILED before search(16.812s): `unstable hit identity`; no DPS
result. Cleanup removed421718 bytes; no next row was released. Installed source
allocates HitID before hit/react handlers but appends the observation after
damage. Nested zero-delay reactions can complete before their parent. The old
validator incorrectly requires `HitID == slice index + 1`. ID-based expression,
resistance and event joins use actual keys; compact channel ordinal is separate.
The proposed `nested_hit_identity.patch` validates positive unique HitIDs and
positive AttackIDs without sorting/renumbering/altering gameplay. Duplicate/zero
IDs remain errors. Focused active-source overlay tests pass(sourcegen/core-info/
compact/optimization); cleanup409838417 bytes.
`repair_nested_hit_identity.py` owns the bounded current-lineage gate:
exact failed inputs, two neutral seeds/initial packages, concrete reordered-ID
witness and unchanged old/new Song control. Burgeon old capture cannot export,
so this control must not be called same-case Burgeon trace parity. The helper
reuses managed lifecycle and transactional promotion; fragments retire with
other matrix observer probes. No fourth/fifth unrelated retries or budget changes.

The subsequent activation gate passed:594 raw hits,36 out of allocation order,
first mismatch at observation41 with IDs `[40,41,43,44,42,45]`. Both neutral
seeds/initial packages have zero unknowns; old/new Song observed damage matches;
native14(including source-only Selected coordinator units) and engine source
gates pass. Installed-path canonical capture matches. Ordinary character/set
source trees are identical. Cleanup removed1560276334 bytes, job absent.
Full Burgeon product attempt2 is the next gate, not yet accepted by these units.

- New active engine `gcsim-v2.45.0-20260927011932`; rollback
  `gcsim-v2.45.0-20260926234622`.
- Artifact `7df37b5224f655d271d9389686bf22445717e02e896df5e3aa22d1d698042f8c`.
- Source manifest `9a2475aa2eb8b8676d4778de1c1be92d965b8c9cf97c4d0b8b2b648caad21ebe`.
- Patch0009 `b56c87a144a23e3b7956388f5268033e950dab8664b339ca0e6c39075148dd30`.
- Stack `154ba582eb6af53f1a2e96f8eb4e808e268a047308b0198a30cbcd88b6b56198`.
- Exact installed consumer `bd5d1a02211d88351014657b0dc09eb3fdf7323510af15cf792cc310e84f2210`
  reused, not rebuilt. Source-only Selected is not in its product route.
- No physical UI check. Source/installed-provider acceptance is not a completed
  matrix row or ordinary full-account search acceptance.

Burgeon attempt2 then completed the installed product route:57596.552 DPS,
SE19.215,n500,111.984s; initial21448.129, formula residual+17.595/.03%.
Search74.336s, preparation27.887s, final22.596s (nested counters overlap);
4192 prepared,4 unavailable,2754 heuristic deferrals,6 stationary finalists,
`neutral_sampled_coordinate_pass_stable`. Cleanup68595070 bytes, job absent.
The four unavailable Scroll tuples pause the queue: the consumer discards the
event's immutable `Target.Type` and consults world snapshots instead. Dendro
cores are not in that snapshot. The producer already emits target events via
the actual `info.Target` interface; a consumer fix can preserve this attestation
and type without inventing an enemy, aura, activation, or gameplay constant.
Other interfaces must remain unknown unless separately observed. Attempt2 is
retained as partial-coverage evidence, not rewritten after the fix.
The first consumer gate failed a legacy event fixture without an event Type;
no install occurred. A narrow diagnostic preserved the assertion. The repaired
lookup prefers event Type, falls back to an independently observed world Type
for the same key, otherwise stays unknown. Immutable metadata does not change
reference equality. Real-source Scroll tests cover Burgeon/Hyperbloom,
enemy/gadget discrimination and wrong-owner rejection without a world target.
Native suite, active-source suite and tiny oracle pass; consumer
`ea259f348268f2bce520a931adc347d99676308e9cf71e79fb39bf7f50154fb6`
installed with engine unchanged. Cleanup168271676 bytes, job absent. Prior
failed/narrow gate cleanup89423963/68184272 bytes also completed. Installer
source-test output is no longer verbose so failure assertions survive bounded
logging.25 Python installer/evidence/report tests pass. Burgeon3 is the product
coverage gate; no fourth attempt is authorized.
Burgeon3 passes the exact installed product path:57610.333 DPS/SE19.807,n500,
112.343s; formula57578.957, residual+31.376. Search74.437/preparation27.990/
final23.030s,4192 prepared,0 unavailable,2766 heuristic deferrals,6 stationary
finalists. Winner/score formula unchanged from attempt2; ordinary difference
is noise-scale. Stop is sampled-coordinate stability, not exhaustive proof.
Cleanup68577068 bytes, job absent. Queue resumes with Burning.

Burning1 completes:85609.682 DPS/SE171.983,n500,93.766s; initial34513.010,
formula89426.631,residual−3816.949. Search58.409/preparation20.935/final20.363s;
4192 prepared,0 unavailable,3282 heuristic deferrals,6 stationary finalists,
`neutral_cycle_budget`. Top1:Bennett4Noblesse,Dehya4Tenacity,Emilie4Deepwood,
Kinich4Obsidian. Cleanup52417327 bytes, job absent. Queue pauses on residual:
the public rotation branches on Sacrificial Dehya cooldown, so a two-seed
schedule sample can differ from n500, but this is a hypothesis, not acceptance.
`diagnose_burning_seeds.py`/`TestMatrixWinnerSeedResponse` compare the retained
winner's formula and native capture on each original seed (four captures total,
no item search/ordinary repeat/install). Managed scratch owns every expanded
output; retain compact stdout in this dated section and retire with the matrix
response probes. Selected source routing/units are in progress, not installed;
infinite route uses complete-candidate search and one n500 final panel, finite
route preserves existing ER checks and staged verification pending its own gate.
The paired Burning diagnostic passes: native seed742031889=90159.229747 DPS,
71550ms; seed742031890=88709.839077 DPS,73817ms. Each matches the corresponding
neutral duration/topology. Native two-seed mean89434.534412 vs predicted
89426.631327 (exact retained formula), residual−7.903085/.009%; native two-seed
SD1024.873972/SE724.695335. This compares the aggregate prediction on the same
two scenarios, not individual offline seed predictions or n500 schedule proof.
The much larger difference from the n500 mean is predominantly schedule-sample
bias, not a4.5% wrong set bonus. The raw unresolved-boundary list is empty, but
aggregate opacity remains (callback/stat/attack dependencies, provider timelines,
reaction/gadget/saved-stat schedules and shield feedback); the probe does not
certify these globally. Four engine invocations,22.86s native test; cleanup
128320895 bytes, job absent. No Burning rerun; resume Physical/Overload/Taser.

Remaining matrix rows on engine7df37b52/consumer ea259f34:

| Row / attempt | n500 DPS / SE | Wall s | Formula minus measured | Unavailable | Final single-stationary |
| --- | ---: | ---: | ---: | ---: | ---: |
| Physical1 |47487.34 /51.83|114.109|−133.10 /−.281%|0|6/6|
| Overload1 |57410.94 /47.20|108.172|+438.87 /+.759%|0|6/6|
| Taser1 |67429.42 /26.23|151.250|−47.70 /−.071%|4|6/6|

All stop at the configured two-cycle search boundary, not a wall timeout.
Prepared4192 contexts each; heuristic deferrals3042/2139/2869 respectively.
Physical retains6 joint-reservation deferrals; Overload/Taser0. Physical,
Overload and Taser cleanup removed58831571/56316184/99329961 bytes; jobs absent.
Player-review oddities (attacking Mika/Chevreuse, Keqing inactive2p VV) are not
proven bugs: this is infinite-energy team-DPS optimization and inactive-bonus
pieces remain legal for their stats. No independent swap tests certify these
particular choices. Formula uncertainty and sampled search remain explicit.
Taser coverage is partial: four Celestial Gift contexts fail on generic
character `StatusDuration`. Queue pauses for a consumer API repair, then this
row alone may use attempt2. No whole-matrix acceptance is claimed yet.

Selected candidate source integration now passes focused CLI units: fixed
complete-candidate coordinator, total160000 candidate-trial ceiling (prior actor
stage ceiling now shared with final stabilization; guide/preparation work is
separate), at most6 polished proposals plus unchanged control,
single n500 per unique infinite-energy finalist. Stop/work/stabilization fields
and bounded-search warnings are explicit. Finite ER path is unchanged.
`compare_selected_consumer.py` is a managed-only old/new same-request/IR harness,
not installed acceptance. It preserves live DB/equipment, freezes request and
compact input, builds no persistent alternate runtime, records call/iteration
counts and rejects material measured regressions; its3 synthetic receipt tests
pass. Source-built candidate and all raw comparison files belong to managed
scratch. Retire the helper after Selected transfer; keep only compact dated
measurements here. Actual Flins/2+2 comparisons and installation remain pending.

Generic character `StatusDuration` now follows the active engine's strict
`expiry > frame` rule, including permanent status duration0. Replay/touched
deletion/neutral-state precedence, uncertainty and dependency footprint are
preserved. Synthetic lifecycle and actual-source Celestial skill/swap/expiry
controls pass; full native, active-source and tiny inventory gates pass.
This candidate remains uninstalled pending Selected comparison. The first
managed comparison stopped before simulation at valid Selected preflight:
live Jahoda has only2 equipped pieces, Columbina3+1+1, and Lauma now4Deepwood,
not the old2+2 setup. No equipment was changed. Cleanup160582318 bytes, job absent.
The explicit `--matrix-equipment` test option now copies SQLite via read-only
backup and applies retained full-team top1 IDs only inside owned scratch:
Flins matrix attempt3; Bloom attempt4, including Lauma and Columbina2+2.
Today's inventory/account profiles and the mode-manifest rotation are retained;
this is NOT a historical inventory restoration or a replay of matrix profiles.
Both consumers receive identical prepared request/compact bytes. Source-row
hash/IDs and copy setup are part of the compact receipt. Five harness controls
pass, including copy isolation and refusal to equip outside managed scratch.

A further source audit found three common-search sorts still using tolerant
`betterObjective`/`betterScored` plus lexical IDs. For feasible scores0,
.75e-9,1.5e-9 and IDs1,2,3 this forms A<B, B<C, C<A. The partial frontier,
scored-assignment pool and diverse frontier now use exact lexicographic
feasibility/shortage/DPS keys, with IDs only breaking true ties. Improvement
acceptance keeps its existing tolerance. Objective keys are prepared before
sorting and errors still fail the search. Strict-order triple/permutation
regressions and focused search/CLI tests pass. Candidate remains uninstalled;
any earlier comparison binary hash must not be relabeled as this repair.

**Selected Flins paired gate, BEFORE strict-order repair.** Installed
`ea259f348268f2bce520a931adc347d99676308e9cf71e79fb39bf7f50154fb6` versus
candidate `9d999ed4dda590c472bc604758b5cb1e36b5ee3e30c0b91abe3a2ec1c30087d1`;
engine7df37b52 unchanged. The explicit scratch-equipment setup above uses
source-row SHA`45bf745e24c6eb53881190345197a23260b365a1314343b607041ec916185e56`.
Request`a256504939a8df626ce6641dab7bad01e451513cd85f4ef926f041a48709bf8f`,
compact`12d70492953d955f4129a9a0c485255a8f2c1038e4ca22771fde23ecdd9981e6`,
prepared config`555a36be8836eb39db4ba47ec26871324ab2df89fc3f33cc0d5b9ecb64c3ee5a`,
rotation`d315d2c63a8fb5c0ae175eb5ba7b620d577ee420f0246484bf48b6865ac0ab54`,
copy artifact-input digest`2938cc8c5ec021edb59db612a364db9a4b78fc8109c9080a0c75756ef137a43b`.
Live DB, equipment, rotation, binaries and engine unchanged; request/IR identical.

| Selected Flins gate | Installed old | Source candidate |
| --- | ---: | ---: |
| n500 winner DPS / SE |194492.185 /101.356|194468.480 /105.288|
| n500 initial DPS / SE |193301.613 /114.756|193373.939 /107.441|
| Optimizer process s |170.562|25.750|
| Compile / item search s |1.702 /88.518|1.696 /4.786|
| n128 screen / final ordinary s |34.757 /37.027|none /10.907|
| Reported internal total s |162.005|17.388|
| Ordinary calls / iterations |32 /6700|2 /1000|

Shared request preparation5.078s/capture5.532s; preflight.108/.125s.
Candidate decrease23.705 DPS <438.436 threshold (3 combined SE); no material
regression. This is controlled old/new evidence, unlike the changed-inventory
matrix. Six seeds converge to one polished assignment plus the unchanged
control:2 rows, not five guaranteed distinct builds. All6 stabilizations are
single-stationary;31066 total trials,8 screens/86 trials and8 refinements/3782;
stop `fixed_candidates_sampled_coordinate_pass_stable`, not timeout.
Candidate top1 IDs F/P/S/G/C: Columbina66/67/8/69/1580;
Flins1/1533/63/88/1565; Ineffa71/72/73/1566/1567;
Jahoda1468/1472/1474/1590/165. Initial differs only on Flins:
1537/1534/63/64/1565. Installed top1 differs from candidate on Jahoda only:
1468/1472/43/1476/165; candidate top1 is installed rank3 within noise.
Cleanup205867352 bytes, job absent. No install. The final strict-order binary
still requires its separate gate; do not imply byte-identical installed scope.

**Selected Bloom2+2 gate and install.** Strict-order candidate
`7ec65bd8d553a696d9256dd481795e729bcbe9491fcea919b449a5f951430a09` passes
full native, active-source and tiny inventory gates. Same engine7df37b52;
request`9685a5d170a1294b0aa2d84b82f11f60285708ea5afcbbdd5d6b5bf2b7e1fff9`,
compact`b2d19e49f5191e6e2da8d0ef26e3323c9b7ec782dfd546a29b586ee876a86b6d`.
Shared request preparation5.046s/capture4.047s. Matrix Bloom4 top1 is applied
only on the disposable current-account copy, including Lauma Night2+Wanderer2;
Kuki uses the approved Dark Iron90R2 in that copy only.

| Selected Bloom gate | Installed old ea259f34 | Strict-order candidate7ec65bd8 |
| --- | ---: | ---: |
| n500 winner DPS / SE |142406.96 /78.43|142379.70 /81.61|
| n500 initial DPS / SE |134799.71 /71.60|134654.93 /74.79|
| Optimizer process s |95.969|14.625|
| Item search / final ordinary s |44.063 /23.360|1.437 /6.918|
| Ordinary calls / iterations |32 /6700|2 /1000|

Identical top1 physical build: Columbina31/1598/1466/1563/243;
Kuki66/67/68/213/1626; Lauma1/1536/127/34/129;
Nahida105/106/112/108/203 (F/P/S/G/C). Ordinary difference27.26 DPS <339.55
threshold; no material regression. All6 finalist checks single-stationary;
71 screen/4636 refinement trials,160000 shared cap, stop sampled-coordinate-
pass-stable,2 returned rows after deduplication. Old top2 swaps Kuki goblet1428;
old top3 Kuki goblet184 and Nahida goblet1573. Identity/DB/equipment/rotation
guards pass. Cleanup241897950 bytes; job absent.

The managed native/source/oracle install gate then installs exactly7ec65bd8,
replacing ea259f34; engine unchanged. Cleanup168502811 bytes; job absent.
At this install step acceptance still needed Taser2 on the installed All Sets path and the
default-path full Selected session. The helper's `installed_smoke()` owns that
single Selected session and disposable setup under the existing managed
lifecycle; it does not override the executable or change live equipment.

**Installed Taser2 closure.** Consumer7ec65bd8/engine7df37b52 match; same normal
All Sets request/session path. DPS67435.73/SE26.32,n500; formula67381.72,
residual+54.01/.080%. Top1 IDs unchanged from partial attempt1. Unavailable
contexts4->0,4192 prepared across2 cycles,1511 sampled/2681 heuristic deferrals;
all6 finalists finish single-neighborhood/sample-pair stabilization. Stop
`neutral_cycle_budget`, not timeout or exhaustive search. Adapter preparation
5.203s/formula inputs7.156s; Go search109.309s (proposal43.437s nested), final
ordinary30.11s; optimizer process141.796s,whole session154.296s. The runner's
initial verbal label "formula capture101.8s" was incorrect; adapter fields
above are authoritative. Unknown-effects warning disappears; explicit search
and formula-opacity warnings remain. Original before.json SHA unchanged,
all28 attempts retained; cleanup99721617 bytes, job absent. The13 non-Gaming
rows now have successful parent-reviewed latest receipts, on their recorded
versions; earlier rows were not silently rerun on7ec65bd8. Chiori659s and
Vaporize272s remain performance weaknesses. This closes the remaining matrix
queue, not global-optimum, arbitrary-response or new physical-UI acceptance.
Python Selected/adapter/input/harness/report unit suite:48 passes; after report
label clarification, the18 report/retention controls pass again.

**Installed full Selected closure.** The managed helper calls the complete
`GcsimOptimizerGoSelectedSession(request).run()` without an optimizer executable
override: installed consumer7ec65bd8 and active engine7df37b52, not a candidate
binary or a legacy engine. Request
`a256504939a8df626ce6641dab7bad01e451513cd85f4ef926f041a48709bf8f`
matches the earlier Flins comparison. The explicit disposable equipment fixture
uses source-row SHA
`45bf745e24c6eb53881190345197a23260b365a1314343b607041ec916185e56`;
it is not a restoration of historical inventory or a live equipment write.

Whole adapter session36.547s (returned elapsed36.546s): preparation5.047s,
preflight.109s, formula inputs5.500s, optimizer process25.891s. Inside the
process, item search4.771s and final ordinary verification10.944s. Winner
194407.06 DPS/SE102.06,n500; unchanged input control193257.26/SE111.36,n500.
Search uses31066/160000 candidate trials, all6 finalist checks stationary,
stop `sampled_coordinate_pass_stable`;2 ordinary calls/1000 iterations and2
distinct returned rows after deduplication. This is a completed bounded search,
not an exhausted timer or an exhaustive global-optimum certificate.

Top1 physical IDs (F/P/S/G/C): Columbina66/67/8/69/1580;
Flins1/1533/63/88/1565; Ineffa71/72/73/1566/1567;
Jahoda1468/1472/1474/1590/165. The control differs only in Flins's
1537/1534/63/64/1565. The runner's first prose summary incorrectly called
the winner's plume1534; its exact result JSON has1533, while1534 belongs to
the control. DB/input/equipment/engine/binary/rotation guards pass;
cleanup65467618 bytes, managed job absent. This closes the installed default
backend path, not a new physical result-page, paging or Save check.

#### 2026-09-27: grouped finalists, no equipped control, optional fast mode

User approved G bonus combinations and K physical alternatives per combination,
both1..7, default3x2; fast OFF by default. Trace handoff section2 owns the new
contract. The standalone consumer (engine unchanged) is
`1aa0be585cac2a40eb391f2a963f31ea03509e79c7f5e6326c9c8ed70df9c268`,
replacing `7ec65bd8d553a696d9256dd481795e729bcbe9491fcea919b449a5f951430a09`.
Active engine remains `gcsim-v2.45.0-20260927011932`, SHA
`7df37b5224f655d271d9389686bf22445717e02e896df5e3aa22d1d698042f8c`.

**Confirmed loss mechanism.** User runs
`all_sets-20260927-132957-e5a9bcbe` and
`selected-20260927-133717-32aa97a3` have identical inventory, profiles, prepared
config, rotation, engine and stochastic settings (different mode time budgets).
Raw request file SHAs are `dbcadbbd9d7a57f7d207085d5dde827aaeef1f61b9fec0af44c9cdffb75d694f`
and `13ba0c4a46282c74ad8625a020f327e7d5f05e3c3e44f0debf810bc92601332d`.
Old All Sets already scored the exact Selected winner's20 IDs at the identical
formula150008.565604 DPS, but `chooseFinalists` reserved initial/selected rows
before context diversity. The weak original occupied the Golden Troupe context
and displaced its improved candidate from ordinary verification. Old All top1
153167.534/SE101.883 was valid; the missing Golden Troupe row was151267.509/
SE92.063 in Selected, above old All top2 150174.187. This was finalist retention,
not a different engine or absence of the candidate from item search.

Implementation separates output archive from search frontier. Each scored legal
neighbor may enter its group's bounded topK; score observers don't change the
search leader/queue. Retain group identities/scores, not thousands of bound
graphs; rebind final groups from the existing neutral model. No reserved original
candidate in production; All Sets capture/search uses a reproducible physical
inventory-ID reference independent of equipped IDs/stats. Selected keeps its
fixed packages. Normal output is one n500 panel, including finite Selected;
fast returns formula-only fields. CLI diagnostic controls remain test-only.

**Source/default-path gates.** Managed `check_grouped_results.py` replays frozen
requests through the production adapter's preflight/formula-input/process methods;
it does not rebuild the account request or write DB/equipment. All Sets3x2 normal
PASS on candidate1aa:367.422s total,319.470s Go search,32.217s ordinary verification,
6 calls atn500, zero unavailable. Stop `neutral_cycle_budget`, not a time limit
or global optimum. This is a **runtime regression**, not a speedup over old
178.984s/141.461s search/21.662s verification. The independent starting point also
changes the search trajectory; isolate costs before assigning the whole regression
to archive maintenance. Do not hide the two-cycle limit or claim convergence.

Common IDs (flower/plume/sands/goblet/circlet):
Bennett36/1413/1426/140/203; Chasca1571/81/92/88/1615;
Ororon1616/91/241/1586/119. Every second alternative changes only Bennett plume
to1414. Furina IDs identify each distinct group below.

| Group / Furina bonuses and IDs | Formula DPS alt1 / alt2 | n500 DPS ± SE alt1 / alt2 |
| --- | --- | --- |
| 1: Tenacity4;1395/1598/48/1563/1510 |153577.804 /153555.699 |153169.563±108.128 /153096.178±101.012 |
| 2: Golden Troupe4;1302/7/1466/1309/1319 |151461.909 /151439.186 |151134.206±97.617 /150981.949±99.374 |
| 3: Golden Troupe2+Wanderer's2;1454/7/1466/1309/1436 |150341.850 /150319.128 |150198.109±94.837 /150190.783±94.194 |

Byte-identical rebuild/install followed by Selected1x2 **default-button binary**
PASS:23.281s total,7.654s ordinary;151247.378±96.420 and151059.023±96.585,
formula150008.566/149986.593, eachn500. Same group2 IDs above. Both builds are
ordinary search results; no extra measured control. Full native `go test ./...`
passes, including canonical-reference independence, archive retention/reentry,
bonus-tier grouping,49-row and1-row boundaries, and formula-only contracts.
Python adapter/settings/result/UI suite46 passes. No engine rebuild or matrix rerun.

Live PyCharm `.venv` AppShell settings check sees3/2/OFF and the requested warning
on enabling fast; restoredOFF afterwards. Real small-window inspection exposed
description clipping, repaired by a scrollable settings body with pinned title;
its compact-height widget test passes. Final scrolling layout and physical new
result pages/Save/dispatch are not yet accepted. Computer Use was stopped after
settings checks. Reload AppShell for the last layout change. Expanded numerical
outputs and build caches are owned by managed scratch and removed on completion;
this compact receipt owns the durable evidence.

**Installed fast gates PASS.** Default executable1aa and the same active engine:
Selected1x7 completes15.609s, seven distinct alternatives, formula150008.566
through149956.048; All3x2 completes335.656s, six rows with the exact normal-gate
IDs/formula scores above. Both have zero ordinary calls and zero ordinary time;
the actual product JSON omits measurement/residual fields (the compact console
projection prints null for absent keys). Formula-only warning is present. All
search remains321.454s,790687 trials, two cycles sampled615/327, with1481/1769
heuristic package deferrals and zero unavailable. Neither max cycle count nor
formula-only ranking is an optimum certificate. Both managed jobs removed.

**Runtime localization, not a repair.** Old retained normal log has5503 model
requests,12.555s rule evaluation,21.920s binding,255 preparation replays/23 joint,
8 full fallbacks and9.269s replay time. New fast log has5774 requests,154.878s
rules,59.037s binding,1648 replays/1416 joint,1399 full fallbacks and152.032s
replay time. Replay is included in rule time; do not add those overlapping
counters. New complete-candidate work totals59.031s, final stabilization3.176s;
provider processes3.8/4.0s and decoding2.24/2.30s. The primary measured cost
increase is source-effect preparation, not six result widgets or ordinary
verification. `seteffects/neutral_composition.go` safely takes joint fallback
when a component/group is stat-dependent or cannot be composed. Determine which
new start/trajectory components force this path before changing independence
checks; bypassing it for speed would weaken formula correctness. This remains
the next performance investigation, not a proven specific set-rule bug.

#### 2026-09-27: expanded results and cooperative finish (live checks deferred)

User requested optional50x50 output and removal of Selected/All Sets timeouts,
then explicitly deferred button/live checks until the next combined UI change.
The default remains3x2; Selected has one fixed package group. Expansion affects
retained output, not a promise of50 distinct candidates or an exhaustive search.
Normal expansion warns about up to2500 ordinary simulations/CPU/runtime; fast
expansion has no extra cost warning. Disabling expansion clamps saved values
to7. Only visible result-page widgets are constructed. Contract validation uses
linear exact assignment deduplication and validates both grouped ranks <=50.

Production product/development budgets are0 (unlimited wall time). Explicit
positive diagnostic budgets remain valid; Theory's360s request policy stays.
The Selected preflight15s cap and All900s/reserved150s search split are removed.
Existing work/cycle/context bounds remain visible and unchanged.

The session owns a per-run `finish-requested` marker, passed as trailing CLI
`--finish-file PATH`. A thread-safe event queues pre-run/preparation clicks.
Native `searchcontrol.Begin/Ready` waits for mandatory formula preparation and
one scored complete candidate, then cancels only its search child context.
Archives retain evaluated legal builds; final rendering/normal n500 verification
uses the outer context. Fast mode skips ordinary verification. Results carry
`search_finished_by_user` / `user_requested_finish`; finite mode cannot present
an unfeasible partial candidate as verified. Cancel still kills the owned tree.
An independent review found a late-cancel publication gap in fast mode; an outer
context check was added before writing success in both entrypoints.

Completed checks before the user's deferral: full native `go test ./...` PASS;
focused native control/search/coordinator/CLI tests PASS after finite-stop
message clarification. Native tests cover pre-preparation queuing, in-search
candidate retention, parent-vs-child cancellation, no deadline at0, and
synthetic2500-row normal/formula output. Python Selected24, All6, Theory9 pass.
The later final-publication context check and failure-metadata finish flag were
not rerun. UI/settings unittest ran30:28 pass, two assertions targeted the
unrelated regular-run summary; assertions corrected to optimizer text, rerun
deferred. Pytest was unavailable; unittest is the actual test runner.

No new numerical replay, real button click, UI restart, matrix run, equipment
or account write occurred. Source and consumer build are synchronized; exact
installed identity/acceptance is in GP-3. Build/copy identity is not a live
optimizer acceptance claim. Managed build scratch is deleted on exit.

Next combined gate: rerun focused tests, then active-engine saved Chasca
Selected normal early-finish, All normal mid-search finish, expanded Selected
fast50 alternatives, All fast partial output and hard Cancel during final
verification; only then short real settings/Finish/Cancel/paging clicks. The
existing managed grouped-results helper still needs finish-trigger options and
zero budgets; do not accidentally reuse saved legacy time budgets. Preserve the
independent-start preparation slowdown as a separate unfinished All Sets task.

#### 2026-09-27: symbolic preparation reuse and output-independent search

Owner: GP-3 for installed acceptance; this receipt owns the reproducible
single-Chasca performance repair. Frozen user input is
`all_sets-20260927-165615-1689738a` (fast5x7), canonical request SHA
`2537659e3c6a2f3f1cafcb9ba3d64a72bc9bbb56c68fe7cc76f84197f2b5e8f4`.
Its total session337.516s includes request preparation; Go search322.606s,
790687 trials, stop `neutral_cycle_budget`,35 formula-only rows, zero ordinary
calls. Rules154.583s include replay151.802s; binding59.149s. Ordinary3x2 user
run `all_sets-20260927-170313-41ef46c0` has the same inputs except result options:
362.969s total,328.281s search,19.730s ordinary verification of6 rows. These
timings are not CPU-load measurements or a global-optimum certificate.

The saved tape's336 isolated owner/set/tier probes identify Emblem4 as the
only stat-dependent package on this inventory for each of the four owners.
This is diagnosis, NOT a production set-name exception. The old broad
`statDependent` guard forced1399 full-team replays. The repair tracks typed
owner/stat/Stat-vs-NonExtra reads and writes, including every bound symbolic
read leaf. Declared AffectedStat narrows writers; nil/NoStat/unknown writers
remain owner-wide wildcards, Extra does not write NonExtra, and deletion is
conservative. Existing modifier/subscription conflicts and fixed-point joint
replay remain. Interacting components still replay together; independent
components retain symbolic increments plus separate raw constants. Resistance
is transformed only after raw composition; symbolic resistance stays unknown.
Cached single-component expression graphs have a128000-node bound.

Bound-program reuse now admits exact full symbolic expression identities,
including latent roots, owners/read keys, ordered children and float bits;
only constants retain the established damage-live projection. Cycle, size,
depth, nonfinite and missing-root guards cannot authorize an invalid binding.
Successful programs alone enter the existing64-entry/128000-node FIFO; cache
eviction never prunes search. Core stabilization uses a separate per-group-1
archive and fixed internal finalist count, with no original-build reservation.
Output G/K only controls retention/output/verification. Final context hydration
is shared across alternatives, not repeated for each row.

Validation: active-source seteffects suite PASS;60 saved-tape two-package cases
match full joint replay at three read scales (.25/1/4), across all ports.
Fast component composition1.255s versus full joint4.564s in this small gate,
zero full fallbacks; not a whole-search speed claim. Tests include owner/stat/
Extra/wildcard interactions, joint symbolic conflict routing, immutable DAGs,
memory bounds and output-limit invariance. Initial full native suite passed;
the added symbolic-cache fixture then failed because its artifact-delta read
witness was incorrectly100 rather than0. Corrected in the test only; the full
native suite then passed. A non-vacuous12-group selection fixture verifies the
same fixed7 leaders under3x2/5x7/50x50 and detects the old display-derived panel.

First fully compared candidate `eafbce47530bc73796af486f729f3289f8767587429197ba66fe2facf56a47fd`
passes fast5x7 through the product adapter:181.094s total (frozen request, no
account-request rebuild),166.948s search. All35 physical assignments and all35
formula DPS values match the saved output exactly (maximum difference0), best
153577.80433290062. Model requests5774, unavailable0, full fallbacks0, replay
8.181s, rule13.911s, binding49.680s. Four symbolic components use1440 retained
expression nodes;1399 symbolic compositions replace the old full replays.
Program hits4279/misses1495. Item refinement57.155s and stabilization3.115s.
No CPU-load telemetry was collected; do not attribute timing variance to load.

Binding still dominates preparation. The follow-up optimization preserves the
exact fingerprint byte protocol but hashes one contiguous bounded encoding,
avoiding per-field hash-interface calls/tiny allocations. A regression compares
the digest against the prior incremental protocol. Final timing/install below.

Two helper-only failures are retained: optional false `expanded_limits` was
noncanonical (preflight, no capture), then canonical decimal-string DPS was
subtracted without numeric conversion after a167.941s completed candidate run.
Both were fixed in `check_grouped_results.py`; neither was an optimizer result
failure or a quality PASS. Managed jobs were removed after every attempt.
The helper now uses zero product/development timers and may run native tests
inside the same managed build cache. No engine changes or UI restart.

**Final candidate/default installation PASS.** Consumer
`e64bfd7c764f4b352a7ad82fdd76e6c1327460004e8b7de9d83f23d234c2df9b`
replaces `bd49423085db430399dcc3f577f6bf6b5b22470e0aad201efa69018a1b3d7057`.
Engine/path SHA remains7df37b52 as recorded above. Full native tests pass before
the final candidate; the installed normal gate verifies the rebuilt byte identity
and uses `default_button_binary=true` with rollback on failure.

| Frozen-request adapter gate | Total seconds | Go search seconds | Trials | Ordinary |
| --- | ---: | ---: | ---: | --- |
| final fast5x7 |177.125|162.9762939|790687|0 |
| installed normal3x2 |198.375|164.1967749|790687|6 x n500,19.7638551s |

Fast all35 rows match the saved35 by all20 physical IDs, with maximum formula
DPS difference0. Normal returns6 of those same35, maximum formula difference0;
the other29 are not requested by3x2, not lost search results. Both stops are
`neutral_cycle_budget`. Final fast rules13.6742289s, binding46.7783213s, full
fallbacks0, symbolic compositions1399. The buffering follow-up's177.125 versus
181.094s is a single timing comparison, not an independently controlled4s claim.
The robust localization is the source-rule154.583->13.674s reduction with exact
result/work preservation. Remaining binding and item refinement are not free.

Installed normal rows1/2 (Furina Tenacity4) measure153265.739±107.611 and
153063.039±105.711 DPS; row3 (Golden Troupe4)151262.173±96.585, each500 iterations.
Corresponding formula153577.804333/153555.699292/151461.908780 is unchanged.
Other party packages remain Bennett Noblesse4 / Chasca Obsidian4 / Ororon Scroll4.
These are measured comparisons, not a claim that formula equals the stochastic
mean or that every group/alternative is a local/global optimum.

Timing scope: replay calls the same production adapter preflight, formula-input
preparation and optimizer process, starting from the saved request. It excludes
account request assembly (5.375s in the old fast user run). Do not label177.125s
as a newly clicked whole-app time or guarantee every PC/team finishes under3min.
Normal/fast current native work is the same; retaining/formatting more output
still has small costs even without ordinary simulation.

Final fast job cleaned153461326 bytes; checked-install normal cleaned133876950
bytes. No managed jobs or numerical processes remain. Small agent-only Go tests
also used the normal shared Go build cache; that preexisting shared cache was
not deleted or falsely classified as owned disposable output. No native UI or
deferred Finish/Cancel live acceptance was performed in this performance repair.

#### 2026-09-27: source cache and exact work reuse

This receipt owns the subsequent performance/cache gate; GP-3 owns installed
acceptance. Same saved Chasca input `all_sets-20260927-165615-1689738a`:
raw request file SHA `5c809dda4141177378b75a0c9d1f1cb7b854da5a217600518714c6b599d24bd9`,
canonical saved request SHA `2537659e3c6a2f3f1cafcb9ba3d64a72bc9bbb56c68fe7cc76f84197f2b5e8f4`.
The previous receipt's253 hash is canonical, not raw-file identity. Replays
clear obsolete timers and explicitly select output options; their fast request
SHA is `e3e1285d43fedcab71029f4a9884b567f129b7349998fb60d4c99a3d63bfdcb1`.
Active engine remains `gcsim-v2.45.0-20260927011932`, artifact7df37b52/source9a2475aa;
no engine source, rotation, account, equipment or saved-input changes.

**Exact computation reuse.** The reduced formula retains coordinate dependency
masks. Only changed IEEE input bits invalidate downstream nodes; identical
damage-live vectors reuse their score while every physical identity still enters
the archive. Independent scratch and error recovery are tested against full
evaluation, including gradients, signed zero, nonfinite input and branches.
Small ordered CSE keys, dense graph memo tables, contiguous owned operand storage
and read-only node references remove allocation/copy work without reassociation.
A one-wearer trial validates its five items against the other fifteen already
validated reservations; random ordinary/exact0/2/4/2+2 controls match the full
validator. No set/item pruning, lower search allowance or output-dependent core
work was introduced.

**Persistent source cache.** `RuleParseCache` stores immutable syntax under
source/path/schema/Go-version keys, shares common libraries in memory, and never
stores team activation or a universal DPS/bonus. Bundled entries are read-only;
new/changed/corrupt entries use a bounded writable cache and fresh-source repair.
Compiler failures after disk hits get one reparse attempt. VM state is separate.
The product neutral inventory path no longer calls unused legacy `Discover`;
finite/Theory/audits retain it. Legacy-only envelopes do not evict neutral libs.
The distribution producer is `tools/prepare_optimizer_set_cache.py`, independent
of disposable research helpers. The lifecycle owner is DATA_RUNTIME_BOUNDARIES.

The generated distribution seed contains97 entries/301591 bytes for42 sets,
plus one provenance record, generated with consumer
`361fb658a75c2304589963c20a8f64b1f44ee566d09771edfc372b860713ea4f`.
Full-catalog generation took0.755s, zero errors. Actual fast replay reports75
bundled hits,390 memory hits, no misses/writes/errors; source preparation0.261s.
This is NOT a claim that serialized syntax beats the native parser: the first
Gob format was rejected after a synthetic19KiB benchmark measured15.5-15.8ms
warm load against1.35ms parse. The bounded typed syntax format2 reduces warm
load to8.21-8.36ms, but parse remains1.42-1.49ms. A warm catalog is now small work;
the main gains below come from arithmetic/preparation reuse, not an asserted
minute-scale disk-cache benefit. Rotation-dependent rules and graph binding
remain necessary for each team.

**Schedule isolation.** Source metadata flags Desert Pavilion4 attack speed
and Ocean-Hued Clam4 queued attacks in this engine (not a production name list).
Successful neutral evaluation wins even with potential metadata. An activated
or otherwise unavailable classified schedule context gets a bounded fresh
full-context capture, cached separately from the neutral graph; failed attempts
also consume/carry their explicit boundary. The active-engine two-seed probe
passes: Chasca OHC4 inactive stays neutral with zero extra calls; Bennett OHC4
captures its own two seeds,85366.301970684843 versus neutral84897.344904775819 DPS.
Repeat reuses it; returning to neutral restores its graph/score. This is a
controlled bonus/route test, not a legal account-build quality claim. Changed
item timing remains explicitly unverified; the user-facing engine is unpatched.

| Frozen-request gate | Adapter seconds | Go search seconds | Work/result |
| --- | ---: | ---: | --- |
| previous installed fast5x7 |177.125|162.9762939|790687 trials,35 rows |
| new candidate fast5x7 |147.875|138.2695149|same790687 trials, same35 IDs/scores |
| previous installed normal3x2 |198.375|164.1967749|six n500 finalists19.7638551s |
| new installed normal3x2 |166.922|138.0278072|same790687 trials, six n500 finalists19.1129661s |

Maximum formula difference0; best153577.80433290062. Full35-row summary digest
`79b79e1b9096a0d8124a4b122631f3ea38913381663ee1e796e517dae358a3e2`.
Both cycles prepare2096 packages, unavailable0, same615/327 sampled and
1481/1769 heuristic deferrals. Stop remains `neutral_cycle_budget`, not a
wall-clock deadline or global optimum. Rules13.815s, binding41.337s, real-item
refinement41.012s, final stabilization2.314s; full preparation fallbacks0.
The fast path makes its usual two capture calls and zero ordinary finalist calls.
Adapter timing excludes old account-request assembly (about5.4s) and cache asset
generation. Single-case timings are not a universal runtime promise.

Checked installation on the default application consumer path PASS with SHA
`361fb658a75c2304589963c20a8f64b1f44ee566d09771edfc372b860713ea4f`.
The normal replay's six physical assignments all occur in the saved35-row oracle,
maximum formula delta0; measured GCSIM ranking remains authoritative. Request SHA
`2b1ae111b7c1577a35267e5ea41faee1c8d13b99bd208a759b40ef0d6e46e5f9`,
six-row summary SHA `82e41d97b5a5866d85aa5807177fc2cf2726f2144456ff5e5914ae881299646a`.
Normal source preparation0.270s, same75 bundled/390 memory hits, zero cache errors.
Managed install job removed138646845 bytes including its temporary prior-consumer
backup after success; failed installation would restore it automatically.

Selected fast default-path replay uses saved `selected-20260927-133717-32aa97a3`,
raw request SHA `13ba0c4a46282c74ad8625a020f327e7d5f05e3c3e44f0debf810bc92601332d`.
Both short repetitions complete in9.547s with zero ordinary calls. Winner IDs
and formula150008.56560406514 are unchanged. Only one of the two old rows matches:
the old second138352.4183945117 row is exactly the saved equipped control (all20
IDs checked), deliberately removed by the already-approved no-control contract.
The new second149986.59287185734 differs from the winner only by Bennett's plume
1413->1414. This is not full historical two-row equality or a new measured-DPS
claim. Replays cleaned20644600 and20644598 bytes; saved input remains untouched.

Validation: full native suite with active-source controls PASS, including cold/
warm source equivalence, activation isolation, corruption/version repair, bounded
cleanup/preservation, round-trip and malformed syntax payloads. Python adapters
and cache tooling46 tests (45 pass, one Windows symlink-creation skip); managed
scope/research helper/cache controls24 tests (23 pass, same symlink skip).
The managed live schedule test uses four seed executions total, no ordinary n500.

Failed development evidence retained: first gate found integer conversions in
cache IO bounds, an intermediate missing metadata declaration, and occupied-ID
test fixtures; a later cache VM fixture attempted unsupported package-global
assignment. Fixtures/types were corrected without expanding VM gameplay. The
new codec's first compile missed its decoder node-counter method; added before
the successful full gate. No failing consumer was installed. An intermediate
profiled candidate `aec75658` also matched all35 rows (search145.805s); its helper
total174.109s included profile-report rendering and is NOT a timing comparator.
The helper now stops its clock before diagnostics. All managed jobs self-cleaned;
one agent's compile-only attempt used the preexisting shared Windows Go cache,
which was not misclassified/deleted as task-owned scratch.

Legacy disposition: duplicate scratch-scope resolver consolidated into the
managed owner; Gob codec removed before distribution. Full-team legality remains
for team/pair boundaries; wide ordered keys remain for variadic nodes. Legacy
source discovery is retained only for finite/Theory/audits until those consumers
have accepted replacements. No unrelated old engines or user logs were removed.
UI/Finish/Cancel checks remain deferred; no app restart or physical click here.
The running app may retain old Python imports: reload is needed for the new cache
environment wiring; backend evidence uses fresh production adapter instances.

#### 2026-09-27: single-item replacement output and early Finish

Consumer `50866df37e777988bc415324b3105b0778433f3b10eac5dafb29bf6f6d4dab1f`
was tested then installed through the checked default-button adapter path.
Engine remains `gcsim-v2.45.0-20260927011932`, artifact
`7df37b5224f655d271d9389686bf22445717e02e896df5e3aa22d1d698042f8c`.
Trace section2 owns the revised groups/single-swap limits and Finish contract.

Blank UI root cause: `ui/app_shell.py` referenced `Sequence` without importing
it in the finish-warning helper, before writing result text/cards. Both reported
backend runs had succeeded. The import repair plus handler regressions removes
that exception; result cards now group by bonus identity and attach only true
one-item alternatives below their wearer. SingleReplacements uses the existing
reduced program/local validator; it checks all legal one-item substitutions,
preserves five-slot arithmetic order and energy constraints, then retains the
requested bounded output. It changes no core search queue or work allowance.
Independent deltas cannot be added. Measured reranking can reduce visible swaps
when the new leader is two items away from another tested alternative.

Saved All Sets source `all_sets-20260927-165615-1689738a`, raw request SHA
`5c809dda4141177378b75a0c9d1f1cb7b854da5a217600518714c6b599d24bd9`:

| Gate | Adapter seconds | Search seconds | Ordinary checks | Visible rows |
| --- | ---: | ---: | ---: | ---: |
| Candidate fast3 groups /2 swaps |156.859|146.926|0|9|
| Installed normal3 groups /2 swaps |184.797|142.234|9 (32.445s)|7|

Both retain790687 trials, two cycles,2096 prepared package contexts per cycle,
zero unavailable models and unchanged heuristic deferral counts. This is bounded
search (`neutral_cycle_budget`), not a time limit or global optimum. Timings
exclude account assembly; they do not establish a new speedup. Output-only swap
preparation was about0.12s. Normal's seven rows are not nine failed simulations:
all nine were measured; distance-two rows after leader promotion were omitted
from per-item presentation. Candidate-row digests: fast
`0bed3194ed5548262a8a69357ec0e84136aad859c31d59dadc124b044809399f`, normal
`cbd4a685ca434379cbe19ee6e8509223f86107b7cba6f92a9d9d42bbe335308e`.

Full native suite PASS with active-source bundle;73 focused Python/UI/adapter
tests PASS. Additional measured-leader-promotion regression PASS. Development
failures: old total-row/expanded-limit/queued-Finish fixtures required migration;
one progress callback int/int64 compile mismatch was corrected. One helper
invocation incorrectly requested native source tests from a Selected fixture
without set-sources.json; repeated with the All Sets fixture. No failed consumer
was installed. Locale-sensitive assertion was changed to the actual translation
key; no production behavior was relaxed. Managed jobs self-cleaned.

Approved live restart used PyCharm app_shell_smoke configuration, project .venv,
working directory `ui`, same active engine/default optimizer. Recreated transient
Furina/Chasca/Bennett/Ororon team without equipping or saving anything. Selected
`selected-20260927-210926-4ff13edd` completed in27.766s (four n500 rows), winner
151247.566 DPS, formula150008.566. Actual expanded Furina flower showed-157 DPS.
All Sets `all_sets-20260927-211141-42f8e2a7` Finish during initial capture returned
finish_no_result and restart instructions. Its generic failure heading was then
corrected to the specific stopped/no-build label. All Sets
`all_sets-20260927-211232-35620e62` Finish during search retained five groups,
verified20 rows, displayed13 and explicit early-stop notice. Total115.890s;
113291.246 DPS is an intentionally EARLY partial result, not completed recall.
Its stop reason is user_requested_finish, not a timeout.

Second approved reload verified the corrected no-build heading live:
`all_sets-20260927-212011-bc978124` Finish during Python preparation returned
stopped/no-build and restart instructions, without claiming completion.
`selected-20260927-211900-45b74566` fast Finish during search returned a labeled
partial formula result. `all_sets-20260927-212105-c3457d19` hard Cancel produced
no result; process inspection found no remaining optimizer/engine children.

Full live fast run `all_sets-20260927-212145-2c1cb70d`, raw request SHA
`8fc91b23f9c96ede6dd08ed88e7313c138119d7c52e34bdf67674095f89c8f8f`, completed
in154.579s (UI2:35): account preparation4.875s, preflight0.110s, formula inputs
7.000s, optimizer142.594s. Requested7 groups/6 swaps yielded49 rows, zero ordinary
checks,790687 trials and neutral_cycle_budget, not user Finish. Formula leaders:
153577.804,151461.909,150341.850,150194.482,150156.973,150087.851,150087.038 DPS.
Programmatic comparison confirmed every attached row differs by exactly one
physical item from its displayed leader. Real paging1-to2 and Furina's expanded
flower replacement showed approximately-35 DPS; group2 has Golden Troupe4p.
The fast-mode warning and normal heavy-check warning were both observed, with
normal controls clamped to5 groups/3 swaps. Original fast-OFF preference restored;
raw saved7/7 limits preserved. Result left open, CU stopped, no Save/equip writes.
The73 focused tests passed again after final UI/localization cleanup. Removed
obsolete expansion/queued-Finish translation keys; no broad legacy cleanup.

Cache audit (read-only): source preparation0.268s is not the large cost. Current
team-dependent BindSeconds42.116 includes binding/cache identity work. Potential
follow-up: immutable sorted expression-key reuse, fewer repeated DAG walks and
node-accounting/eviction diagnostics before changing cache size or policy. These
are unmeasured opportunities, not implemented speed claims. Complete team effects
cannot be cached solely by set name across different rotations/teams. Source-only
distribution cache remains bounded and repairable as described in the prior receipt.

#### 2026-09-27: revised output recommendations and saved Chasca time breakdown

User clarification supersedes the prior5/3 and10/20 recommendations: normal5
groups/10 swaps; fast10/40. Defaults for fresh/reset settings are normal3/2,
fast5/20; explicit persisted values are not reset. Reintroduced expanded_limits
checkbox lifts these recommendations to a user-approved high technical cap50
groups/100 swaps in either mode, with persistent risk copy in all three locales.
No reset button was requested yet. Trace section2 owns the current contract.

Fixed an allocation hazard: grouped selection reserved requested G*K capacity
even with few observed rows. It now reserves len(observed rows). Reconciled
Selected's former50-row output check, wire rank validation, result row limit and
UI truncation with101 rows/group and5050 total. Fewer available rows are valid;
large requests do not demand new search cycles or invent replacements. This is
bounded memory protection, not a guarantee of cheap maximum-volume simulation.

75 focused Python/UI/adapter tests PASS. Native contracts, search and CLI suites
PASS, including synthetic5050-row validation, observed-row allocation with
1e9 requested counts, and101-row Selected output on a tiny domain. Consumer
`585aca6b49bd766a2b41fd5cc4392f6aeffd6463b824660f39736f62f55b1715` was built,
validated on the saved live request, installed via checked rollback wrapper,
then revalidated at the default button binary path. Prior consumer50866df3;
engine unchanged. Managed job cleaned96320272 bytes. No optimizer search,
GCSIM simulation, app restart or new CU acceptance this turn; fresh checkbox
is widget-tested, physical app reload remains pending. A test expecting the
former shared default was updated to assert the requested fast default21 rows.

Read-only saved timing audit (same live run IDs as the receipt above):

| Phase | All Sets fast212145 | Selected normal210926 |
| --- | ---: | ---: |
| Account preparation + preflight |4.985s|5.062s|
| Initial formula/source preparation |7.000s|2.719s|
| Optimizer process |142.594s|19.969s|
| Total |154.579s|27.766s|

All Sets inner search139.913s splits into disjoint proposal/package preparation
and screening56.609s,942 candidate refinements41.605s, package-joint passes13.801s,
seven stabilization records2.347s, remainder25.551s. The remainder includes
capture/setup, other joint work and coordination; it is not a separately timed
solver. Expansion count790687, two cycles2096 package contexts each. Inner
rule14.127s, binding41.848s and view0.875s are overlapping attribution counters,
NOT additional elapsed time. Source parsing0.216s. There were5774 model requests,
not5774 simulator calls; ordinary verification count zero.

Selected: compile0.601s, search3.606s/37543 evaluations, four n500 checks13.043s
(one wave12.407s). Its optimizer process has approximately2.72s outside those
inner phase counters. The earlier normal All Sets replay184.797s instead adds
nine n500 checks32.445s to142.234s search. Different verification counts and outer
scope are disclosed; none of these saved timings benchmark the new high limits.

#### 2026-09-27: isolated search-speed hypotheses and replacement geometry

The [isolated evidence receipt](../optimizer-evidence/2026-09-27-search-hypotheses/README.md)
owns exact saved inputs, timings, failed attempts and reproduction. Seven
source-copy alternatives were compared against the current Chasca 49-row search
through the actual CLI coordinator with a hash/config/seed-bound saved capture
provider. No new GCSIM simulation, installed consumer change or Computer Use.
The original saved run and matrix remain unchanged.

The experiments separate cache bookkeeping, increased cache capacity, exact
context dispatch reuse, lazy scalar binding, deferred common-subexpression
elimination, equal-port template reuse, and a narrower local item frontier.
Cache changes produce modest/no gains; lazy/no-CSE representations amplify
later work. The narrow frontier is promising but explicitly heuristic, not a
new certified bound; its saved-case comparison and confirmation are in the
receipt. Do not silently promote any experiment or claim a global optimum.
The combined narrow/exact-reuse prototype takes84.322s versus the repeated
baseline132.780s, with all49 rows matching the confirmed narrow variant (six
groups unchanged, one improved). Installed binaries remain unchanged. This is
a saved-capture search timing, not end-to-end or multi-team acceptance; the
larger bounded caches also increase reserved heap. Integration must separate
exact reuse from heuristic frontier changes.

Follow-up matrix authorization uses `search_hypotheses/matrix_pair.py`, one
managed parent-reviewed row at a time. The [paired matrix receipt](../optimizer-evidence/2026-09-27-search-hypotheses/matrix/README.md)
owns the current result, input identities and any gate failures. Installed and
prototype receive one frozen current account request through the button adapter;
the old matrix is historical context, not an identical-inventory baseline. Fresh
captures use the active engine. The existing structural graph/port canonicalizer
compares semantics while retaining raw hashes: repeated engine captures can
renumber constant nodes without changing expressions, owners or event timing.
Fast formula quality is separate from ordinary n500 and UI acceptance. Gaming
stays deferred; no unattended batch, installation or engine switch is authorized
by a successful individual row.

The [2026-09-28 preparation experiments](../optimizer-evidence/2026-09-28-preparation-hypotheses/README.md)
separate immutable inventory-vector reuse, prepared event-query ordering/catalog
lookup, and incremental scalar-effect binding through a bounded immutable node
arena. A dense export variant preserves original graph encounter order and
gradient accumulation without per-export hash maps. General symbolic effects
still use the original binder; no VM activation state is shared across choices.
All remain managed source-copy overlays, not a second production path. The dated
receipt owns timings, reference identities, exact full-result comparisons and
combined confirmation. Trace section2 owns the user's practical acceptance of
the prior tiny Bloom rank7 difference; historical numerical receipts stay intact.

The [equal-bonus/sparse-effect follow-up](../optimizer-evidence/2026-09-28-bonus-hypotheses/README.md)
tests dense constants plus sparse symbolic inputs, bounded exact effect-family
payload reuse AFTER dependency merging, and immutable Amount syntax plans with
per-invocation state checks. Physical set/item domains remain distinct. A
separate bounded n1 active-engine probe measures direct4p capture/compile cost;
it is not a generic composable-effect producer or changed-item response proof.
The receipt owns paired49-row equality, explicit active-source control passes/
skips, memory costs, the retained harness failure and successful cleanup.
The [consolidated player-logic follow-up](../optimizer-evidence/2026-09-28-player-hypotheses/README.md)
adds exact original-width reuse control, narrower refinement, item/package
preselection, CV/useful-amount priorities, mean/observed-peak effects and strict
literal2p construction. Its strongest combined prototype evaluates a legal
candidate in the shared parametric graph before preparing a detailed package
view. Symbolic/unknown cases retain normal work; constant-point selection is
heuristic, not an upper bound. The ledger owns paired combination timings,
all49 normal-model checks, failures and rejected quality/speed tradeoffs.
An observed peak is not a generic theoretical maximum extracted from arbitrary
4p source; that general extension remains unimplemented. These measurements were
isolated; subsequent exact-only integration is recorded below and in GP-3.

`tools/experiments/gcsim/search_hypotheses/` contains historical research and
current deployment-check helpers. Generated source copies, captures and binaries
live in managed jobs and are removed on exit. The source-copy overlays are now
retired from active development: retain them only to reproduce their dated
receipts against the guarded old source. Do not apply them over integrated source
or expose rejected variants as a second product backend. The checked-in native
implementation and its regressions own current behavior. Deployment/comparison
helpers remain available for their explicit gates. Any future deferred-binding
representation needs a consistent fixed-input/view contract; unchanged response
shape is the UI boundary.

Replacement expansion repair is independent: 160px replacement cards caused a
new horizontal scrollbar and a14px viewport-height change in the actual offscreen
workspace. Cards now keep the104px column width, with DPS on its own line.
The realistic regression fails before and passes after; all5 result tests pass.
No delayed scroll-restoration workaround remains. This is programmatic geometry
acceptance, not a new physical button check or application restart.

#### 2026-09-28: original-width exact-reuse integration

The [paired matrix and integration receipt](../optimizer-evidence/2026-09-28-player-hypotheses/matrix/README.md)
owns timings, failures, immutable identities and acceptance evidence; GP-3 owns
installed state. All13 non-Gaming matrix cases retain all637 rows and trial
counts. Point shortlists and narrowed refinement frontiers are rejected. The
production search coordinator/candidate policy is unchanged; the uncalled
experimental narrowing entry point and approximate helpers are not transferred.

The compatible production implementation consists of:

- `domain/vectors.go`: inventory-owned, wearer/ordered-coordinate vector cache,
  at most16 shapes/1,000,000 float words; package views share immutable vectors,
  not item pools or mutable reference values.
- `setcontext/neutral*.go`:256 reduced-program entries/1,024,000 nodes and8192
  context-dispatch entries, scoped to one captured run. Mixed binding validates
  every port, keeps constants dense and transports only real dependent
  expressions sparsely. Timing fields separate these binding routes.
- `formula/region_binding.go`: reuse unchanged constant-bound regions, with
 250,000 arena nodes/1,000,000 operands and ordinary binding fallback. Export
  keeps original first-encounter/reverse-gradient order and independent outputs.
- `seteffects/neutral_binding.go` and `rule_replay.go`: prepare immutable query
  order/source lookup once, retain the normal path for direct/synthetic callers.
- `seteffects/effect_families.go`: reuse equal complete raw IEEE-port vectors
  only after dependency/conflict merging. Symbolic components remain distinct;
  ownership diagnostics are rebuilt for actual choices. Payload retention is
  bounded by128 entries/2,000,000 values/128,000 expression nodes.
- `seteffects/rule_amount_plan.go`:128 immutable syntax plans per VM; actual
  storage, observed state and lexical `clear` binding are rechecked per call.
  The general inspector remains the fallback, not a second search policy.

General expression/map APIs remain for callers and regression oracles; they are
not removed merely because the neutral optimizer uses the compact route.
Selected shares inventory-vector reuse, not neutral package preparation. No
GCSIM engine or wire schema changes. Research captures/source copies/binaries
are still managed disposable output; retain compact receipts and the historical
overlay scripts as non-product reproducers, with their old-source hash guard.

### Implemented neutral Theory extension

**Required comparison semantics (user clarification, 2026-09-19):** compare
set effects at the same explicit artifact-investment budget and roll-quality/
main-stat rules, with team profiles, weapons, rotation and energy policy fixed.
For each candidate set-effect configuration, independently optimize useful main
and substats, including crit balance and team-buff dependencies. Equal investment
does not mean holding the same stat vector for every set: a bonus can change the
best allocation. Compare those optimized objectives, including an independently
optimized zero-bonus alternative, not a standalone bonus score added to one
unchanged build. Owned-item availability/quality belongs to All Sets, not this
Theory comparison. An inactive bonus has no intrinsic advantage under matched
investment. This is the required objective, not a claim that the bounded solver
below reaches its optimum or that a new search implementation is approved.

Theory shares the prepared rotation, source-backed set catalog, formula capture
and set-context provider, but it has a distinct wire boundary. Python sends no
owned artifacts, current assignments or selected set package. Each wearer has
only the canonical five-main `theory_baseline`; `DecodeTheoryRequest` validates
that representation and creates twenty private process-only pieces. Ordinary
Selected/All Sets validation never accepts this Theory-only wire form. All Sets
separately supports a virtual profile with a private neutral baseline while
searching the real account artifact inventory.

The neutral prepared config has no active set rows. `setcontext.Context` can
insert a complete candidate package immediately before each actor's stat row;
the bounded Theory guide considers source-supported 4p and distinct 2p+2p
packages and preserves wearer/shared/new-output/unresolved breadth. The current
coordinator shortlists 32 single-wearer changes, evaluates at most 40 contexts
(16 primary plus 24 marginal/minimization), and labels the result partial if
the 300-second deadline stops it sooner. Its capture budget includes the separate
neutral base panel, so the final candidate cannot exhaust
the session merely because the base was captured first. Each context uses the dedicated
equal-investment main-stat/roll allocator. Its output is farming guidance, not
owned artifact IDs, physical feasibility or proof of a global optimum.

`internal/theory/solver.go` implements45 ideal roll units per wearer, restricting
each stat to six units per piece with a different main stat. It first greedily
adds one unit at the greatest team-formula gain, then makes at most16 improving
within-wearer exchanges of0.25 units. At most two main-stat cycles screen legal
sands/goblet/circlet combinations using projected existing rolls, then rerun
roll allocation for the chosen layout. Only graph-visible axes participate.
This is a bounded local relaxation, not the retained Python continuous-target
solver, a KKT/convergence certificate, or proof that five physical items realize
all allocations. `coordinate_descent_converged` is emitted even when the fixed
iteration ceiling is reached. Theory performs no ordinary n500 verification.
After at most16 primary contexts, the marginal phase takes up to six leaders
and removes wearers' sets with reallocation. A loss no greater than0.05% permits
an undistinguished/removed set; this does not test all omitted alternatives.

The current Theory solver has no burst-deadline/ER constraint. When the shared
energy toggle requests finite energy, its Python product boundary fails with
`theory_finite_energy_unsupported` before formula capture rather than silently
returning an infeasible farming target. Selected and All Sets keep their
separate implemented finite-energy search. An actual ER-aware theoretical
allocation is open in TODO.

`validate-theory-request` is invoked against the exact installed optimizer
executable before formula work. This is a compatibility gate, not a Python
shadow decoder: schema drift or a stale binary fails before expensive captures.
The current behavior and visible-UI validation limit are owned by GP-3.

## 10. Performance and execution rules

- Selected cold190s remains a performance reference, not an automatic timeout;
  configured output size must be recorded when comparing runtimes. Selected/All
  production has no wall-clock ceiling; one n500 stage or explicit fast skip.
- Disposable diagnostic runs retain an explicit managed watchdog. Theory's
  existing limits are unchanged by the cooperative-Finish extension.
- Follow `CODEX.md`: inexpensive agents for bounded low-context checks; no
  large main-history forks. Main-agent review and serial expensive runs remain.
- Work sequentially; no parameter sweeps or brute-force retries.
- Stop after three substantive failed approaches to one blocker; ordinary code
  errors are fixed without pretending they are conceptual failures.
- No full-account/n1000 run before the preceding reduced/parity gate passes.
- Preserve unrelated dirty-tree work; do not commit/push unless requested.

## 11. Current Continuation And Historical GOB-10 Evidence

Read [GCSIM_GOB11_GP3_CHECKPOINT.md](GCSIM_GOB11_GP3_CHECKPOINT.md) for the
current acceptance/repair gate and [TODO](../../TODO.md) for user-decided scope
order. Unknown ancestry/branch/schedule limits remain explicit. Do not reopen
completed Go migration/search stages without a demonstrated defect.

The following GOB-10 measurements describe its saved fixture and older engine;
they are retained evidence, not current cross-team or UI performance promises.

### GOB-10 — measured compute optimization

Baseline user runs were 3:33 and 3:40. The saved stage receipt attributed the
work to about 66.8 s formula search, 48.6 s n=128 screening and 43.2 s adaptive
n=500 final verification, plus compact/preparation/process overhead.

The accepted implementation changes no recall or finalist limits:

- immutable formula nodes are evaluated once; an artifact change recomputes
  every downstream node influenced by that wearer's artifact coordinates,
  including cross-character support chains;
- the engine executable is hashed before and after a complete verification
  stage, never before and after every candidate;
- ordinary simulations bypass trace-only event recording, modifier provenance
  and traced MaxHP arithmetic; trace capture itself retains full behavior;
- the two fixed compact seeds run concurrently and are reassembled in canonical
  seed order.

Proof on the saved real account:

- optimized full search result is `reflect.DeepEqual` to the accepted result;
- old and new compact payloads compile to exactly equal complete search output;
- 25-row n=128 screen and all seven adaptive finalists remain present;
- winner IDs are unchanged;
- compact capture 1.83 s, compile 0.47 s, search 13.27 s, n=128 18.15 s,
  adaptive n=500 19.65 s, complete post-preparation boundary 57.0 s;
- expected UI total is about 62-64 s because unchanged request/config/database
  preparation previously measured about five seconds.

Historical GOB-10/v2.45 checkpoint: `gcsim-v2.45.0-clean-adapter-20260901`; executable SHA-256
`4ce399e8fd0fae48ac8812fbe8e3fcd746b5e74c84554228fa660ef944cfb857`.
Consolidated patch SHA-256:
`d7e0c0ab6b1133b179949396bcb104e68cf51ff07081b49b816f210e9a3b315c`.
The previous `gcsim-v2.42.2-gob10-perf-20260901` remains installed as the
rollback target. The v2.45 compatibility proof is recorded in the engine
integration handoff; it does not alter the accepted GOB-10 search result.

Historical GOB-11A checkpoint (2026-09-07) changed the engine identity to
`gcsim-v2.45.0-gob11a-20260907`; executable SHA-256
`ecbeb14af152c25e67bafb567912aebc1a8ceb3d8fb6e0a6a6cfc1529d4087c1`.
The compact consumer schema stays v1; the engine's flattened formula registry
advances to `gtt_trace_formula_v2` and the source/patch/binary binding changes.
The adapter uses observed producer receipts and actual calculation branches for
reaction classification. Legacy `direct_lunar` evidence remains readable, while
new hits use `direct_reaction`. Direct-reaction candidate formulas were never
correctly supported by the standard talent compiler: those hits now explicitly
freeze, including future unknown terminal categories. GOB-11 owns their actual
dependency coverage. Current-team channel expressions, baseline damage and
coordinates are unchanged on both seeds. Go search/evaluator code is unchanged.
The v2.45 catalog reader accepts `artifact.dm.json` and pipeline `kind: artifact`
with canonical `name`, while retaining older engine layouts for rollback.

The subsequent compatibility repair is now installed as
`gcsim-v2.45.0-compat-20260907`, with GOB-11A explicitly pinned for rollback.
Its flattened formula registry is v3; compact schema remains v1. The compiler
removes unproven reaction owner crit/DMG% inputs and independently checks each
terminal baseline; external reaction-support dependencies can still freeze.
The native consumer rejects absent/null ordinary DPS fields. Current-team
baseline damage stays unchanged; candidate reaction coordinates deliberately
change. Search architecture is unchanged and finalist quality was not re-run.
Official activation now includes actual consumer/catalog/ordinary/wave smokes;
see GCSIM_ENGINE_UPDATE_COMPATIBILITY_AUDIT.md for receipt and remaining limits.

## 12. Implemented energy-aware Go extension

The existing request/formula/search/finalist ownership is retained. The
versioned `gtt_energy_ledger_v1` section is compact evidence rather than a
Python callback or a GCSIM run per candidate. It records burst deadlines,
normalized particle energy, flat energy, active/off-field distribution and
source identity without character-specific rules.

The Go evaluator compiles each character's ledger into cumulative feasibility
constraints. Required ER is the largest prefix shortage before any intended
burst, not an averaged rate. Candidate formula damage may update enemy
HP-threshold particle timing without rerunning the engine. Unknown or stochastic
energy sources widen the margin/retained lane and are verified at the bounded
finalist stage.

Finite-energy finalists are rendered with `ignore_burst_energy=false` and no
boosted-energy injection. Ordinary-result `failed_actions.insufficient_energy`
is the final authority; a miss rejects the finalist and cannot silently fall
back to infinite energy. Infinite energy remains the explicit other mode.

The two UI controls are synchronized projections of the existing settings-owned
`gcsim_boosted_energy_enabled` value; they are not independent booleans. Live
window inspection on 2026-09-17 confirmed synchronization in both directions.
The finite position is a working energy-aware mode: Selected fails before
ordinary simulations when the inventory has no feasible assignment; All Sets
continues across set contexts and verifies only feasible finalists when any
exist. Successful results report artifact ER, required artifact ER and margin
per wearer.

The requirement is deadline-based and precomputed once per fresh formula/set
context. Search then compares candidate artifact ER against four thresholds;
it does not binary-search requirements per candidate. On the saved
Chasca/Furina/Ororon/Bennett control this reduced the search from a 300-second
timeout (the rejected per-candidate calculation) to roughly 10 seconds. That
inventory has no feasible Selected-set assignment: Bennett, Furina and Ororon
remain short, so the correct product result is an explicit no-feasible-build
failure rather than a misleading DPS winner.

Current limit: schedules are observations from the fixed two-seed panel, not a
symbolic proof of every random energy branch. Enemy-drop timing and other
observed stochastic sources therefore retain uncertainty codes, and the final
ordinary real-energy simulation is mandatory.
