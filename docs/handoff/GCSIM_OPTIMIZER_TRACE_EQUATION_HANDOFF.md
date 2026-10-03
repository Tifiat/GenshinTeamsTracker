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

Selected, bounded All Sets and neutral formula-only Theory are implemented.
Installed backend evidence and pending real UI acceptance belong to the
checkpoint. Selected/All Sets return:

- five artifact IDs for each of four characters;
- twenty globally unique physical IDs;
- ordinary mode: measured GCSIM DPS, sample count, standard error and formula residual;
- fast mode: formula estimate and explicit unverified warning, no fabricated measurement;
- deterministic debug receipt;
- no automatic equip; every character row can be saved explicitly as a normal
  Artifact Browser preset through the existing preset storage service.

Cold Selected above 190 seconds remains a performance failure criterion. The
historical GOB-10 replay met the backend target; its 62-64s full UI projection
was an estimate. Current copied-fixture Flins backend timings are recorded
separately in GP-3. Selected/All Sets wall-clock boundaries were removed by
the2026-09-27 cooperative-Finish extension; Theory keeps its existing limit. GP-3 owns
its quality/performance acceptance. No fresh UI timing is claimed here.

## 2. Production architecture and approved replacement

### Approved parametric/search overhaul (2026-09-19)

The user approved implementation after the whole-pipeline audit. This replaces
the requirement to preserve the old search method/contract, not the engine
ownership and response-correctness guarantees. Implementation and acceptance are
separate; the checkpoint identifies which parts actually run in the product.

The target is one prepared aggregate team-DPS function per observed schedule
member, with artifact inputs and effect expressions still variable AFTER
reduction. The2026-09-20 user-approved refinement starts All Sets from a neutral
capture with NO set rows (already supported by GCSIM and Theory preparation),
not a dummy set or mandatory removal of old buffs. Observe event emissions
independently of registered set callbacks, together with required state/query
identity. Use current source rules plus these facts to evaluate bonus inputs;
ordinary package changes do not recapture or rebuild the damage function.

The user also approved a crystallization-plus-skill activation fallback when
pickup evidence is genuinely unavailable. Prefer observed shield identity and
nearby construct facts where present; a foreign shield is not crystallization,
and absent evidence must not silently become full uptime. Incoming healing is
a recipient input, distinct from the wearer's outgoing healing stat. Diagnostic
completion runs use the managed job's emergency watchdog. Production
Selected/All Sets have no wall-clock deadline; neither policy proves convergence.

Do not rewrite ordinary GCSIM set implementations into a new declarative engine.
Extend only observation/export and the consumer's bounded source interpretation.
Exact supported effects are preferred. Approximate effective coverage is an
approved fallback when amount, applicability and recipients are known; distinguish
it from exact response and from a conservative bound. Unknown activation/amount/
recipient is not zero or a full bonus. Keep caps, stat-dependent expressions,
shared-key interactions and per-damage-kind ownership. Neutral capture eliminates
old set contributions, not these obligations. Effect rules may use the event
schedule without rerunning it; stat-independent work is prepared outside item
scoring. Real output, action, branch or source-RNG changes take an explicit
schedule/uncertainty route, not an energy-mode or named-set exception list.

The approved scope, in dependency order:

1. Revise the parametric input/coverage contract and prove changed-input response,
   including cross-owner support. Baseline agreement alone is insufficient.
2. Produce effect semantics from the active GCSIM implementation and neutral
   event/state evidence, with the exact/approximate distinction above and without
   named set/character allowlists. Keep effect inputs distinct before deduplication;
   equal observed values do not imply interchangeable sources or windows.
3. Reduce earlier: common expressions, constant-only regions, unreachable nodes
   and valid algebraic grouping. Specialize the prepared program for one/two
   variable wearers or fixed packages without re-reading the original hit list.
4. Replace the inherited partial-build beam with real-build candidate search.
   The2026-09-20 user-approved revision supersedes eager upper enclosures:
   formula gradients propose complete legal packages; their actual model DPS
   orders refinement. Inspect different complete starts and joint two-slot
   changes; directly enumerate small domains. A top-five team-DPS gap versus
   observed variation may HEURISTICALLY defer a branch, never certify a bound.
   Reconsider changed team anchors; retain unvisited/deferred accounting.
   Package sweeps update one wearer block at a time against the latest accepted
   complete team. Do not treat four stale-anchor conditional winners as
   independent contributions; shared bonuses couple their utility. The bounded
   block-coordinate schedule still does not prove a global package optimum.
   The2026-09-27 approved extension keeps a bounded frontier of distinct complete
   package teams and scores joint two-wearer replacement/relocation, including
   removing a bonus from its old owner. Conditional package ranks only propose
   alternatives; changed team effects require a fresh score through the SAME
   neutral formula. Preserve the incumbent, actual item ownership, current
   global work bounds and configured final simulator count. Production wall-clock
   limits are removed by the cooperative-Finish extension. A changed nonleading frontier
   may use the next configured cycle; sampled-pair/frontier completion is not
   exhaustive package search or proof of global optimality.
   Zero local gradient is not global irrelevance, and weak pieces can complete
   bonuses or serve another wearer. Unknown effects are not inactive effects.
   Before ordinary verification, stabilize the surviving complete finalists:
   all legal free single-item substitutions first, broader sampled pairs and
   cross-wearer exchanges next; any accepted change restarts the cheap checks.
   Report a complete single-neighborhood check separately from sampled-pair
   stability, work exhaustion and global optimality. Do not refill final slots
   with old unchecked rows after improved representatives deduplicate.
5. Search actual joint wearer exchanges, not only combinations of already
   retained rows. Keep physical-ID alternatives when numeric vectors coincide,
   twenty-ID legality, energy constraints and partial-incumbent checkpoints.
6. All Sets combines feasible inventory and operative effects, including4p,
   2+2, single2p and no-bonus cases. Inactive-set pieces remain eligible. Replace
   raw-old-context/short-list selection, not merely its time/context budget.
7. Remove the separate n128 screen and mandatory repeated128/500/1000 ladder.
   One bounded common-fidelity ordinary finalist stage follows corrected offline
   selection. Selected's previous screen selected rows, so deleting it alone
   was not a quality-preserving replacement. Measure total preparation, transport,
   compilation, search and final verification; do not advertise node counts as
   end-to-end speedups. Avoid illegal-point work and preserve progress on expiry.
8. Theory follows with equal investment, independent stat optimization per
   effect choice/main-stat layout and an optimized no-bonus baseline. Repair
   Jahoda/Columbina coverage, deadline handling and false convergence labels.
   Then apply proven common-core/search improvements to fixed-package Selected,
   preserving4p/2+2 and result paging/Save/cancel. The later grouped-output
   decision below removes the production current-equipment comparison.

The shared arithmetic AND basic inventory search are part of the All Sets work;
they are not deferred to Selected. The Selected replacement requires its own
evidence before installation. First validate response, then tiny exhaustive inventory
oracles, then the saved Flins team/rotation through the production All Sets path.
The legal144.7k control, meaningful coverage and whole-pipeline runtime are the
acceptance comparison (roughly half the original273s is a target, not a promise).
Add teams one at a time afterwards; no14-team matrix restart or Gaming test.
Preserve original/new receipts. Computer Use is limited to short actual button/
route checks; substantive numerical validation is programmatic on that same path.

**2026-09-27 execution/order update:** the user now authorizes continuing all
remaining matrix teams sequentially without requesting permission between rows.
A low-context Luna runner executes each row; the parent reviews its compact
result before releasing the next. Pause the queue on an obvious bug, diagnose
and repair within the existing technical/attempt boundaries, and ask only for
a genuine user decision. Preserve accepted rows and every failed attempt; this
does not require regenerating the baseline or spending extra retries on passed
teams. The earlier Gaming rotation/status exception remains separate. After the
matrix, prepare a player-readable comparison and transfer proved common-core
improvements to Selected Sets before returning to Theory. This supersedes the
old Theory-before-Selected delivery order, not the math/physical-ID/energy gates.

**2026-09-28 practical quality clarification:** the user explicitly accepts the
observed5.720792 DPS loss at Bloom rank7 (~0.0043%, first six ranks unchanged)
as negligible for player-facing quality; it must not block further research or
reject the narrow prototype by itself. Keep its deterministic formula difference
in the receipt, without relabeling it as measured stochastic noise. Review new
heuristic differences by magnitude, affected ranks and gameplay relevance; this
is not blanket permission for materially weaker results or lost valid groups.
Exact arithmetic/setup reuse still requires controlled response and same-input
parity; illegal assignments, stale capture/owner bindings or unsupported effects
remain blockers regardless of small point-DPS differences. New hypotheses are
tested separately before combination/installation. Cheap low-context agents run
the tests and may implement bounded local hypotheses; the parent retains broad
architecture and evidence review, following `CODEX.md`'s delegation policy.

**Selected transfer (2026-09-27):** infinite-energy Selected now shares the
complete-build screen/refine and final single/pair/exchange stabilization APIs
proved in All Sets. Its capture still fixes the selected4p/2+2 packages; it does
not run All Sets' package discovery. One160000 candidate-trial cap covers
proposal work and final stabilization (guide/preparation is separately timed).
Search still stabilizes a bounded shortlist; the independent output archive
retains the best already-scored legal alternatives, including checked neighbors
which need not themselves be local optima. No unchanged input/control row is
reserved or added for measurement. Stops distinguish sampled stability, exhaustion and
cancellation; none claims a global optimum. Common sort keys are exact, while
the improvement-acceptance tolerance remains separate. Finite energy retains
the existing constrained coordinator, not an ER-blind transfer. Ordinary
verification is one n500 stage; there is no production n128/adaptive ladder.
The checkpoint owns installed-path and UI acceptance scopes.

### Source preparation cache and exact arithmetic work reuse

Reusable source structure belongs to a team-independent cache, keyed by original
source bytes/path, cache schema and Go AST version. Verified engine/source/catalog
binding is still checked before use. Immutable parsed trees may be shared; VM
environments, activation state, event tapes and bound formula programs must not
cross team/run boundaries. A changed/new source misses automatically; corrupt or
incompatible entries reparse from verified source. A cached compile failure gets
one source retry, not an endless retry of unsupported gameplay. Distribution seeds
are read-only; runtime repairs use the bounded cache lifecycle documented in
`DATA_RUNTIME_BOUNDARIES.md`. Parsing and event-dependent rule evaluation are
separate costs; a warm syntax cache does not eliminate rotation evaluation.
The neutral inventory path no longer builds the unused legacy `Discover`/recipe
representation. Finite-energy/Theory/audit consumers still require it; remove
that implementation only after their replacements are accepted. Current Selected
consumes a captured panel, not these source rules. Current Theory inherits cache
configuration but supplies no neutral-rule libraries, so receives no AST-cache
benefit and must not clean another mode's entries. Shared arithmetic reuse applies
independently of this source-cache boundary.

Schedule metadata describes potential source hazards, not activation. Successful
neutral evaluation does not request a capture merely because source contains an
attack/speed API. An activated schedule boundary (or unavailable neutral model
with a classified potential schedule effect) uses a separately bounded run-local
capture session. Its key is the full engine/source/config/team/package/seed
context, never a set name. Captured bonuses are not added a second time, and its
schedule never replaces another context's neutral graph. Failed attempts remain
cached diagnostics and spend their reservation. Capture at reference item stats
is not proof of unchanged timing under all candidate stats; preserve that warning.

Incremental arithmetic skips a node only when none of its input coordinates
changed, comparing IEEE bits including signed zero. Scratch/error state remains
private; full evaluation is the oracle. Dense graph memo tables, ordered CSE keys
and contiguous operand storage must preserve arithmetic and gradient accumulation
order. Prepared single-wearer legality may reuse the other fifteen validated IDs;
the changed five still satisfy physical uniqueness, slots and exact bonus tiers.
These are computation reuse, not new item pruning or a global search guarantee.
The checkpoint owns installed acceptance; implementation alone does not accept UI.

The2026-09-28 exact-reuse combination keeps the original proposal/refinement
width and candidate order. Run-local preparation reuses immutable inventory
vectors by wearer and ordered coordinates, preordered neutral queries and source
lookup, context-to-program dispatch, and unchanged reduced formula regions.
Dense constant effect inputs coexist with sparse dependent expressions; all
ports, including latent ones, are validated before projection. Equal full-port
IEEE vectors may share composed arithmetic only AFTER dependency/interaction
checks; symbolic components retain distinct identities. Actual item pools,
ownership, diagnostics and uncertainty remain specific to their set choices.
Bounded amount-function plans cache syntax, never current storage or lexical
values. All caches are finite and fall back to ordinary computation on overflow.
These in-memory caches do not cross runs or replace the persistent parsed-source
cache. Selected shares inventory-vector reuse; it does not acquire All Sets'
neutral package discovery. Rejected point shortlists and narrowed frontiers are
research evidence only, not selectable production paths.

### Grouped output and fast mode (2026-09-27)

Persistent settings are `gcsim_optimizer_set_group_limit` and
`gcsim_optimizer_builds_per_group`. The UI exposes groups and SINGLE-ITEM swaps
per group: recommended normal1..5 groups /0..10 swaps; fast1..10 groups /0..40
swaps. Internal builds_per_group counts the leader too (normal1..11, fast1..41).
Fresh/reset UI defaults are normal3 groups/2 swaps and fast5 groups/20 swaps;
existing explicit saved counts are preserved, not reset by a mode change.
Omitted legacy wire options retain3x2 total rows.
Stored oversized values clamp to the effective mode; native requests exceeding
limits fail validation. `gcsim_optimizer_expanded_limits` / wire expanded_limits
opts into the checkbox "Remove recommended limit": both modes allow50 groups
and100 swaps (101 rows/group,5050 total) as a high technical bound. A persistent
note warns about very long runs, freezes/errors and normal GCSIM verification.
Only found rows consume result allocation; never allocate requested G*K slots
before discovery. Disabling the checkbox persists counts clamped to recommendations.
Fast mode defaults OFF. Theory is unchanged; Selected fixes one bonus group.

A group is the complete wearer-owned combination of active bonus tiers: 2/3
pieces canonicalize to2p, 4/5 to4p; singletons have no bonus. Item swaps that
preserve all wearers' tiers are alternatives, while2+2 and either4p are different
groups. No equipped/input control receives a reserved result slot. All Sets
uses an inventory-ID-canonical physical reference for capture and search,
independent of equipped item IDs/stats; this reference is not a quality control.

An independent per-group archive retains K best scored assignments, including
groups temporarily outside the top G. It does not widen the search frontier.
The final search stabilization panel also stays independent of G/K: a separate
one-leader-per-group core archive supplies the fixed internal finalist count.
Only output retention/construction and ordinary verification scale with the
requested display limits; larger limits do not request extra search cycles or
more stabilized groups. Hydration reuses one model per retained context.
Select G groups by their best formula score. After normal search completion,
enumerate legal single-item neighbours of each group leader through its reduced
formula, preserving bonus tiers, physical IDs and energy constraints. Retain up
to K-1 best swaps; no extra search cycles/stabilization are requested. Send these
leaders and swaps to one ordinary n500 stage (fast skips it). Rank groups by
their best measured DPS. If verification promotes another leader, expose only
measured rows exactly one item away from that actual displayed leader; discard
distance-two rows, do not attribute their joint delta to one item or refill with
extra simulations. Thus fewer swaps may appear than requested.
Pages show distinct bonus groups; swaps expand below their wearer with team-DPS
delta against the displayed group leader. Deltas are independent, not additive.
Limits are maxima, not a promise of G*K legal rows or a global optimum.

Fast mode skips the ordinary finalist stage and uses formula ordering. Initial
engine captures needed to obtain the formula still occur. `ranking_basis=formula`
and `formula_only_unverified` are mandatory; omit measured DPS, SE, engine result
hash and residual. Every user OFF->ON transition warns; restored preferences
do not reopen the modal, while each result remains visibly labeled. Finite
mode also reports `energy_not_simulator_verified`: modeled deadline feasibility
is not ordinary energy verification. Recommended normal output caps at55 ordinary
checks; fast at410 formula rows. Expanded output caps at5050 rows/checks in either
mode. Crossing12 requested ordinary checks, or
returning from fast with that workload, warns about CPU/time cost. Fast has no
extra modal volume warning; the expansion risk note and accuracy warning remain
independent. Fewer available
items is a valid smaller result. No time estimates are displayed: elapsed time
and a monotonic stage/work bar with short animated transitions replace them.

Selected/All Sets production requests use zero product/development time budgets:
no wall-clock deadline for preparation, search or ordinary finalists. Explicit
positive deadlines remain available for bounded diagnostic harnesses. Existing
cycle, work, source-coverage and candidate-queue bounds are unchanged; removing
a timer does not certify exhaustive search or convergence. Theory keeps its
existing limits and is not changed by this feature.

`Finish and show results` is cooperative, separate from emergency Cancel.
A per-run `finish-requested` marker cancels search even during preparation.
If no complete feasible candidate exists, return explicit `finish_no_result`
with instructions to restart and allow preparation/search to produce a build.
Otherwise retain already scored legal candidates, skip output-only swap
enumeration, stop new search and use the outer context for retained-context
hydration and normal n500 verification or fast output. Hard cancellation of
that outer context still stops all work. Report `search_finished_by_user` and stop reason
`user_requested_finish`, never a completed exhaustive search. Finite energy
still requires a feasible candidate; no valid candidate is an explicit failure,
not an invented result. Once finalizing, Finish is disabled and Cancel remains
available to terminate the owned process tree. Arithmetic/provenance failures
must not be converted into partial success. Markers share the session run-root
retention/cleanup lifecycle and cannot leak to a later run.

### Installed architecture before this replacement

The production backend is gtt_gcsim_optimizer_go_v1.

It has two parts:

### Standalone Go optimizer

Path: native/gcsim_optimizer.

It owns:

- compact request/result/progress contracts;
- artifact stat arrays and physical legality;
- formula compilation and stochastic expectation;
- Formula-Guided Build Search;
- bounded ordinary finalist verification (the checkpoint distinguishes installed
  staged policy from the approved single-stage replacement);
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

Shared Python requests, explicit mode input preparation and the process/Finish/
Cancel lifecycle belong to `optimizer_go_requests`, `optimizer_go_inputs` and
`optimizer_go_session`; canonical writers belong to `optimizer_go_contracts`.
Mode adapters own their respective capture/source hooks and CLI command. All
Sets does not inherit Selected's compact capture. Strict source-manifest codecs
belong to `source_manifest_codec` without loading the legacy trace closure;
historical trace readers re-export the same objects/error identity.

Schema-v1 `finalists`, `budgets.development_timeout_ms` and
`cancellation.mode` are deprecated but validated compatibility inputs. They do
not select current product measurement, introduce a second runtime deadline or
change Cancel semantics. Retained requests keep their identities; retirement
requires an explicit versioned migration. Inventory output uses `result_options`
and ordinary finalists use a single n500 stage, not the old sampling ladder.

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
- All Sets changes effects, not only artifact stats. The approved replacement
  uses the neutral parametric/event path in section2. Existing non-neutral
  captures still need complete effect removal/replacement or fresh capture;
  unchanged topology or an approximate guide is not a replacement certificate.
  The isolated `internal/setcontext` boundary keeps replacement bias separate
  from physical item stats and reuses only fully bound contexts. Its proof
  contract does not itself prove engine source semantics; enabled coverage and
  product integration belong to the current checkpoint and Go design.
  Discovery retains alternative amounts and activation/ownership uncertainty.
  Old-context increments can guide proposals but do not remove an old effect.
  Neutral read annotations identify the actual input owner/query/graph node;
  generic arithmetic probes must not invent inheritance for another damage type.
- Selected supports fixed4p and2+2 packages. Its finite-energy route compiles
  observed burst-deadline constraints and ordinary verification checks actual
  energy failures; both energy routes remain live. This is not a proof of every
  stochastic energy schedule. Theory finite energy still fails closed; current
  acceptance and limits belong to the checkpoint.

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

- Selected and capability-gated All Sets share the grouped normal/fast result path;
  Theory has a separate formula-only guidance result, not measured artifact IDs.
- One Go process returns exact IDs, explicit ranking basis, progress/cancellation,
  fail-closed errors, warnings and a debug receipt. No automatic equip.
- Four compact five-piece rows reuse existing artifact/stat/element assets.
  Per-character Save prompts for a name and uses the existing Artifact Browser
  `save_build_preset` service, never a second storage path.
- Result-v1 `candidates` contains up to2500 grouped rows (expanded opt-in), with combinations and
  alternatives ordered by their chosen ranking basis (normal measured DPS,
  fast formula DPS), as defined in section2. Grouped paging is not a flat
  global-DPS rank. Normal results contain measurements; fast results omit them.
  Paging uses the returned data, not debug files or extra simulations. Older
  payloads without that additive field show one winner page.
- The pre-overhaul Selected keeps common n128 for Current plus the24-row formula pool: saved
  evidence disproves truncating directly to formula top-seven. All Sets instead
  preselects at most seven context-diverse rows and sends that unchanged panel
  to both n128 and adaptive verification; this is a distinct recall limitation.
- The pre-overhaul policy runs all retained/mandatory finalists (at most seven) at n500. Extend only a
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
Energy-aware Selected/All Sets are implemented with observed constraints and
ordinary finalist verification; Theory's finite-energy solver remains separate.
Engine update limitations are retained
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
