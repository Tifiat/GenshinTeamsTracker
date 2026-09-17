# GCSIM Optimizer Go Backend — implementation design and acceptance record

Current implementation, acceptance limits, active engine and next action:
[GCSIM_GOB11_GP3_CHECKPOINT.md](GCSIM_GOB11_GP3_CHECKPOINT.md).
This design's stage measurements remain historical evidence, not new-team
performance or complete dependency-coverage guarantees.

This document owns the clean rewrite of the active Selected optimizer backend
in Go. It is not a line-by-line port of the Python implementation. Python FGBS
and stochastic expectation were temporary executable references and were
removed after the explicit GOB-6 parity/cleanup gate.

## 1. Goal

Build one production-oriented local optimizer which:

- receives one compact immutable account/team/rotation request;
- obtains compact formula evidence from the bound GTT-GCSIM engine;
- searches legal physical artifact assignments in Go;
- sends a bounded finalist set to the same engine at common n=500 fidelity and
  extends only a small unresolved group to n=1000;
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
were outside the initial Go rewrite. The initial Go Selected path and cleanup
are complete; current core acceptance continues through the GP-3 checkpoint.
The Selected2+2 extension below is implemented; installed/UI acceptance belongs
to the checkpoint. All Sets is now a separate bounded extension; Theory remains later;
TODO owns their order and explicitly leaves energy until last.

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
installation/UI acceptance is a separate gate. Initial limits: at most8 complete
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
  before handing its own panel and legal artifact domain to `RefineWearer`.
  It cannot create another capture budget, retry or simulate artifacts itself.
  Single-wearer results preserve the other15 physical IDs. They are formula
  candidates, not ordinary-engine measured finalists.

The first queue witness exposed duplicate shared-effect optimism and a raw
equipment-strength bias; these were corrected before new package captures.
Current acceptance/timings and immediate continuation belong to GP-3. The source
observer, refreshed guide, joint pilot, shared coordinator and ordinary finalist
adapter exist. Remaining release/installation/UI gates are owned by that current
checkpoint, not this design history. No real-set reuse certificate producer exists.

## 10. Performance and execution rules

- Selected cold product failure: >190 s total including compact evidence,
  search, adaptive finalist n500/n1000 and result production.
- Development audit ceiling: 360 s unless the user explicitly changes it.
- No subagents or parallel agents for this project.
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

## 12. Planned energy-aware Go extension

Keep the existing request/formula/search/finalist ownership. Add a versioned
energy-ledger section to compact evidence rather than a Python callback or a
GCSIM run per candidate. The ledger records burst deadlines, normalized
particle energy, flat energy, active/off-field distribution and typed
target/stat/probability dependencies.

The Go evaluator compiles each character's ledger into cumulative feasibility
constraints. Required ER is the largest prefix shortage before any intended
burst, not an averaged rate. Candidate formula damage may update enemy
HP-threshold particle timing without rerunning the engine. Unknown or stochastic
energy sources widen the margin/retained lane and are verified at the bounded
finalist stage.

Finalists are rendered with `ignore_burst_energy=false` and no boosted-energy
injection. Besides DPS, verification compares the intended versus executed
burst/action schedule. A failure cannot silently fall back to infinite energy.
The current infinite-energy path remains an explicit user-selectable mode.

The two UI controls are synchronized projections of the existing settings-owned
`gcsim_boosted_energy_enabled` value; they are not independent booleans. The
inline control is already visible at the user's request. Its finite-energy
position passes `ignore_burst_energy=false` but is labelled diagnostic and may
fail because ER-aware search is not implemented. Promote that position to a
working energy-aware mode only after the ledger, constrained search and
real-energy finalist acceptance all pass.
