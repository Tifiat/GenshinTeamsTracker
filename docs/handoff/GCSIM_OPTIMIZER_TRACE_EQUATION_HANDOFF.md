# GCSIM Artifact Optimizer — current authoritative handoff

Current implementation, acceptance limits, active engine and next action:
[GCSIM_GOB11_GP3_CHECKPOINT.md](GCSIM_GOB11_GP3_CHECKPOINT.md).
Use that owner for live state; measurements below retain their dated scope.

This document owns optimizer architecture and gate order. The GP-3 checkpoint
owns current run evidence/resume; the Go design owns implementation detail;
the engine plan owns update/rollback. Read only the needed companion:

- GCSIM_OPTIMIZER_GO_BACKEND_DESIGN.md — active implementation design;
- GCSIM_ENGINE_INTEGRATION_PLAN.md — engine update, patch and rollback boundary;
- GCSIM_GOB11_ROTATION_VALIDATION.md — supplied fixture provenance and dated measurements;
- GCSIM_OPTIMIZER_TRACE_EQUATION_CLEANUP_MANIFEST.json — detailed receipts and deletion disposition;

Old M/S/Gate, Selected V2, CF-BB, Adaptive Oracle Exchange and Contextual Scan plans are not active architecture.

## 1. Product goal

The application needs three optimizer modes:

1. Selected Sets — search real account artifacts inside fixed4p or2+2 set packages.
2. All Sets — choose promising set packages and real artifacts.
3. Theory / farming guidance — explain useful main stats, balance, plateaus and future farming targets.

Selected and the bounded All Sets extension are implemented. Installed backend
evidence and pending real UI acceptance belong to the checkpoint. Both return:

- five artifact IDs for each of four characters;
- twenty globally unique physical IDs;
- measured adaptive n=500/n=1000 GCSIM DPS and standard error;
- formula estimate, residual and uncertainty warnings;
- deterministic debug receipt;
- no automatic equip; every character row can be saved explicitly as a normal
  Artifact Browser preset through the existing preset storage service.

Cold Selected above 190 seconds remains a performance failure criterion. The
historical GOB-10 replay met the backend target; its 62-64s full UI projection
was an estimate. Current copied-fixture Flins backend timings are recorded
separately in GP-3. The temporary 360s UI boundary is only a fail-safe; All Sets
has a separate future 600s boundary. No fresh UI timing is claimed here.

## 2. Accepted production architecture

The production backend is gtt_gcsim_optimizer_go_v1.

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

Python-produced frozen fixtures are parity evidence. The temporary Python
Selected/FGBS implementation was removed at GOB-6; do not resume it as an oracle
or fallback. The following measurements describe that historical experiment.

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
- automatic compatibility of the adapter patch with every future GCSIM release;
- semantic completeness for Lunar Crystallize, Stellar Conduct or another
  materially new mechanic not exercised by the current team;
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
- an `AttackInfo` flat-damage producer remains traceable whether it is written
  in the literal, assigned later, updated with a compound assignment, passed
  through a typed pointer helper, stored in a persistent field or fed from a
  saved stat alias. Snapshot HP/ATK/DEF reads are captured once at their real
  evaluation point; later reconstruction from mutable stats is forbidden;
- opaque behavior freezes at the last known boundary;
- frozen share remains visible and cannot prove dominance or saturation;
- a material unknown widens retained finalists and produces diagnostics;
- no character, set, element or reaction name switch in generic evaluator/search code;
- All Sets changes the observed effect context, not only artifact stats. An
  unchanged hit topology does not authorize formula reuse after a set change.
  Apply a fully proved static-effect replacement or capture the changed team
  context; keep unknown/conditional effects visible rather than assuming zero.
  The isolated `internal/setcontext` boundary keeps replacement bias separate
  from physical item stats and reuses only fully bound contexts. Its proof
  contract does not itself prove engine source semantics; enabled coverage and
  product integration belong to the current checkpoint and Go design.
  Discovery retains alternative amounts and activation/ownership uncertainty.
  Old-context increments can guide proposals but do not remove an old effect.
  Neutral read annotations identify the actual input owner/query/graph node;
  generic arithmetic probes must not invent inheritance for another damage type.
- accepted Selected remains infinite-energy. The shared switch also exposes
  diagnostic finite-energy execution, not ER-aware search. Selected supports
  fixed4p and2+2 packages; current acceptance is owned by the checkpoint.
  Energy-aware search remains separately gated last, after All Sets.

Reaction-dominant and future Lunar/multi-contributor teams remain required later controls. Damage share, not hit count, determines whether an unknown path is material.

## 6. Selected artifact/search rules retained for Go

The Go rewrite keeps the method, not the Python implementation:

1. Precompute each artifact's normalized numeric contribution.
2. Search complete five-slot wearer builds.
3. Enforce selected4p or two distinct2p sets and one legal flexible item.
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

## 7. Completed Implementation And Acceptance

GOB-0 through GOB-10 are complete. Detailed stage evidence remains in
`GCSIM_OPTIMIZER_GO_BACKEND_DESIGN.md`, dated fixtures under
`tests/fixtures/gcsim_optimizer_go_v1/` and the cleanup manifest. Their earlier
failures/next-step instructions are historical, not a second active queue.

| Gates | Accepted boundary |
| --- | --- |
| GOB-0..2 | Architecture, standard-library standalone Go module, strict cross-language v1 contracts, compact adapter feasibility |
| GOB-3..5 | Fixed seed-panel aggregation, signed artifact deltas, indexed evaluator, bounded complete-build Go search |
| GOB-6 | Superseded Python Selected strategies removed; migration fixture retained as evidence only |
| GOB-7..8 | Common-context screen/finalists, actual AppShell Selected result, cancellation/errors, exact IDs and preset saves |
| GOB-8P..10 | Adaptive n500/n1000 policy, final cleanup, dependency-aware evaluation and measured speedup |

The original GOB-8 full UI path narrowly missed 190s; the later GOB-10
saved-account product replay completed in 57.0s after preparation. Its projected
62-64s UI path is an estimate for that fixture, not a measured universal UI
benchmark. Later copied-fixture measurements and their residual/uncertainty
limits belong to the current checkpoint.

### Retained product result contract

- Selected and capability-gated All Sets share this result path; Theory remains unavailable.
- One Go process returns exact IDs, measured DPS, progress/cancellation,
  fail-closed errors, warnings and a debug receipt. No automatic equip.
- Four compact five-piece rows reuse existing artifact/stat/element assets.
  Per-character Save prompts for a name and uses the existing Artifact Browser
  `save_build_preset` service, never a second storage path.
- Result-v1 `candidates` contains measured finalists ordered by measured DPS.
  Paging uses the returned data, not debug files or extra simulations. Older
  payloads without that additive field show one winner page.
- Keep common n128 for Current plus the 24-row formula pool: saved evidence
  disproves truncating directly to formula top-seven.
- Run all retained/mandatory finalists (at most seven) at n500. Extend only a
  two-to-four-row group unresolved within three combined standard errors to
  n1000. An overwide unresolved group returns the bounded n500 panel with
  explicit warnings, not an unbounded extension.
- Each seed member uses its own duration before DPS averaging. Preserve
  deterministic seed order, exact physical IDs, stage-wide engine identity,
  cache/cancellation safety and mandatory Current comparison.

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

## 10. Open Gates And Extension Order

Current evidence and the immediate gate are owned by
[GCSIM_GOB11_GP3_CHECKPOINT.md](GCSIM_GOB11_GP3_CHECKPOINT.md).
User-decided scope order is in [TODO](../../TODO.md); do not maintain a second
mutable queue here. A demonstrated response loss must be repaired and
validated before another acceptance search. Earlier bounded passes do not
certify new candidate deltas. Preserve dated failed receipts and use current
engine identities from the checkpoint, not historical install records.

Selected2+2 retains each chosen pair and the legal remaining slot across
UI/request/legality/search/materialization/tests. Its standalone Go extension
is described in the Go design; acceptance is owned by the checkpoint.
Energy-aware Selected, All Sets and
Theory remain separately scoped work. Engine update limitations are retained
in `GCSIM_ENGINE_UPDATE_COMPATIBILITY_AUDIT.md`.

Use one fixed-rotation fixture per materially different mechanism: direct
ATK/HP/DEF scaling, amplifying reactions, transformative/owned reactions,
off-field/snapshot damage and Lunar/multi-contributor paths where applicable.
Record capture validity, whole-channel freezes versus partially frozen inputs,
controlled-stat response, bounded-finalist behavior, measured winner residual
and unresolved ranks. Overlapping opaque reason shares are not additive unknown
damage. A demonstrated response/ranking-direction loss requires narrow diagnosis;
it is not permission to rewrite search, widen simulations or revive legacy code.

### Energy modes and shared UI state

Product energy mode has one settings-owned value with two synchronized views:

- Account/Settings -> GCSIM;
- an inline control next to the artifact-optimizer action.

Both controls now read and write the same `gcsim_boosted_energy_enabled` setting
and update each other immediately. Selected no longer unconditionally overrides
the config: infinite mode writes/passes `ignore_burst_energy=true`, while the
other position writes/passes `false`. The latter is exposed only as a diagnostic
boundary with an explicit warning that ER-aware artifact search is not built;
it may fail the fixed rotation and must not be described as a working
energy-aware optimizer. A future `EnergyMode` wrapper must preserve this single
source of truth rather than copying the boolean.
The user deferred energy implementation until last on2026-09-16; leave this
diagnostic path unchanged during Selected2+2 and All Sets. The design below is
future work, not a prerequisite for those modes; TODO owns sequencing.

- Infinite energy preserves current Selected behavior: the intended fixed
  rotation is observed with burst costs ignored.
- Energy-aware mode must return only builds for which that same intended
  rotation can pay every burst cost. Invalid user rotation code remains the
  user's responsibility, but an impossible account inventory must return an
  honest infeasible result rather than silently dropping actions.

### Energy evidence and optimized calculation

Do not estimate energy from skill names and do not run a full simulation for
every artifact build. The first compact capture already executes the intended
rotation with costs ignored. Extend that capture with an energy ledger containing:

- every burst cost and its exact time;
- every particle/orb event, element, source and arrival time;
- active/off-field recipient state and the engine-applied party multiplier;
- raw particle energy normalized to ER=100%;
- flat energy changes, which are not multiplied by ER;
- target HP-threshold drops and any source whose count/timing depends on damage,
  crit, probability or another artifact-controlled stat.

For each character, required ER is the maximum cumulative shortage at every
burst deadline, not an average energy-per-second number. Energy that arrives
after a burst cannot pay for it. Deterministic character particles and flat
energy form the cheap base constraint. Candidate damage formulas can predict
when enemy HP thresholds are crossed; stat/probability-dependent energy sources
must remain typed dependencies or uncertainty, never character-name switches.

The standalone Go search then treats ER feasibility as another formula-owned
constraint. It keeps candidates close to an ER boundary, rejects proven
shortages, and continues optimizing damage after the requirement is met. This
must happen in the same contextual build search; ER is not an independent item
score. Only the bounded finalists run ordinary GCSIM with real burst costs and
without infinite-energy injection. Final acceptance checks that the intended
burst/action schedule actually executed.

GCSIM v2.45 already exposes generic `OnEnergyChange`/`OnEnergyBurst` events,
particle distribution and enemy HP-drop data. Its upstream ER optimizer is a
useful control only: it uses 350 iterations and explicit Raiden/Favonius
exceptions, so it is not the production algorithm and must not be copied as-is.

### Energy result explanation

Energy-aware results should report, per character: selected ER, estimated
minimum/range, margin, the largest energy sources, and any unresolved source.
If the constraint consumes a main stat or a large part of the available damage
budget, report the measured trade-off and suggest reviewing rotation, burst
frequency or an energy weapon. Do not automatically declare a burst worthless:
its damage/support contribution and energy cost must both be visible first.

### Overnight execution contract (2026-09-17; bounded N0 recovery verified)

The user explicitly started the autonomous session after discussion, adding N0
disk-growth diagnosis, safe cleanup and enforced retention before other work.
TODO owns N0-N6 order; the checkpoint owns resume state. This is a scoped
exception, not a permanent policy change.
The initial agent cleanup command was denied. Both user-run allowlists are now
confirmed absent; subsequently authorized guarded deep cleanup and lossless
archiving completed. The checkpoint owns results and N1 inputs. Five extra
binary removals were separately denied; do not retry through another API.
Heartbeat remains paused. Future-output lifecycle rules continue to apply.

- All Sets: retain the shared Go search. First measure on saved contexts where
  repeated work and weak-branch spending occur. Reject impossible packages using
  actual slot availability/physical IDs. Rank feasible packages using the team's
  damage/support dependencies, conditions, buff duplication/caps, wearer cost
  and available artifact strength, rather than a universal set tier list.
  A promising bonus alone does not prove a promising complete team. Cheap
  ranking followed by bounded refinement is a hypothesis to test, not a claimed
  implemented speedup. Hard elimination requires a valid feasibility/dominance
  or upper-bound proof; heuristic low scores justify less budget, not claims of
  impossibility. Retain bounded unknown/synergy discovery. Do not enumerate all
  set combinations or weaken effect replacement/source binding to save time.
- Compare incremental work against the saved incumbent and reduced exact
  controls: total time by stage, search coverage, best formula score, ordinary
  measured quality/uncertainty and changed finalist semantics. A faster timeout
  or silently lower-quality winner is not an accepted optimization. Revisit
  mandatory weak representatives separately from discovery. No promise of
  Selected-like runtime or a global optimum before measurements.
- Shared product checks follow AppShell action -> request -> installed Go/engine
  -> worker result -> cards/preset service. For this session the user explicitly
  accepts a temporary handler-path harness instead of Computer Use. Preserve
  the distinction in reports: harness verification is not a physical click.
  Include2+2/4p legality, unique IDs, cancellation, result paging, save service
  and unchanged live equipment. Use copies for persistence tests. Clean only
  proven disposable files under existing gates; keep rollback/UI-pending backups.
- Theory reuses preserved continuous-target mathematics only where helpful;
  do not force it into account search. Read the existing roll/main-stat budget
  contract before modeling reachable theoretical stats and set conditions.
  Keep theoretical estimates/farming advice distinct from owned artifact IDs,
  proven global optima and ordinary measured DPS. Missing product assumptions
  that materially change conclusions remain explicit choices, not magic values.
- Energy starts only after the preceding optimizer stages. Follow the ledger
  contract above, including initial energy, capacity/clipping, burst deadlines,
  flat versus ER-scaled gains and timing/probability-dependent sources. An
  expected particle count alone cannot guarantee burst readiness. Keep uncertain
  constraints visible and validate actual action completion with bounded
  finite-energy finalists. No automatic rotation/weapon rewrite or second toggle.
- Editor: one self-contained worker may research upstream grammar and build
  grouped buttons plus RU/EN readable rendering with punctuation. Maintain a
  structured, round-trippable representation and raw escape path. Unknown valid
  DSL must not be dropped. Agree isolated file ownership before delegation;
  do not load the entire optimizer history or let the worker edit shared handoffs.
- At most one subagent at a time; the main agent handles optimizer work. Do not
  recruit more workers through a child. Reuse project venv/imports, Go tests and
  saved evidence rather than reasoning through large numeric tables manually.
- Fix ordinary defects and select justified recommended local options without
  waiting. After three failed substantive attempts, preserve the first unresolved
  loss and park that task; take the next independent authorized task. Do not
  convert this into unlimited retries, fabricated certainty, permission bypass,
  external publication or destructive live-data changes. History Browser is out
  of scope, including incidental redesign/migrations from other TODO work.
- Checkpoint each meaningful stage and before a safe pause. On the user's return
  and stop request, stop new work, finish/cancel safely and report completed,
  measured, unverified and parked work separately. If every available task is
  done or genuinely blocked, stop rather than inventing work. Scheduled resumption
  is claimed only after a persisted ACTIVE automation exists. The current
  heartbeat is `automation`, created ACTIVE every30 minutes on2026-09-17, then
  confirmed PAUSED at the N0 deletion-policy stop.
  Usage limits/app availability cannot be bypassed.

## 11. Permanent execution rules

- Work sequentially without subagents or parallel agents outside the scoped,
  explicitly started overnight exception above.
- Do not brute-force parameters or repeat expensive runs without a declared gate.
- Stop after three substantive failed approaches to one blocker.
- Ordinary technical errors are fixed without pretending they are conceptual.
- No full-account or n=1000 run before its reduced/parity gate.
- Unknown behavior degrades safely; no legacy fallback.
- Preserve unrelated dirty-tree work.
- Do not commit/push unless requested.
- Update the owning status/contract and affected root pointers/cleanup manifest;
  keep evidence in dated receipts instead of duplicating logs across documents.
