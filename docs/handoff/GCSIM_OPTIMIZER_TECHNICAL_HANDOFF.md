# GCSIM Optimizer Technical Handoff

Reviewed: 2026-07-28

Theoretical mechanics baseline: `7a390c1`

Superseded product-contract draft baseline: `ef85de3`

Status: the read-only real-account selected-pool and all-database-set services
run end to end for complete `4p` and opt-in concrete `2p+2p` packages. The
theoretical `4p` and engine-derived theoretical `2p+2p` product boundaries
also run end to end. It is not yet a release-ready optimizer.
Milestone 0R is complete and its current request boundary is schema v4: the
accepted modes plus hard per-wearer minimum static-build constraints are typed,
and every operation cache/provenance namespace is versioned at `.v4`. Milestone
1 is also complete: the
prepared-config artifact shell and true read-only all-row artifact database
boundary are implemented. Milestone 2 is complete: immutable run input and the
strict arbitrary-five-ID/full-team materializer are implemented. Milestone 3 is
complete: independent reduced exhaustive account/theoretical `4p` oracles and
their winner-survival audit boundary are implemented. Milestone 4 is complete:
set-aware database-reachable main-layout domains, exact multi-scale response
probes, and the coupled-EM safeguard are implemented. Milestone 5 is complete:
exact lazy per-wearer real `4p` candidate streams,
feature/shape retention, and conflict-repair shadows are implemented. Milestone
6 is complete: the exact bounded all-different proposal
solver, lazy conflict enrichment, and feedback score-adjustment boundary are
implemented. Milestone 7 is complete: exact compiled-config deduplication,
iterative typed enrichment, low-/high-fidelity evaluation, close-leader
reraces, and evidence-bound account finalist ranking are implemented.
Milestone 8 is complete: quality-first reference anchors and the selected-set-
pool account orchestration service compose M4-M7 into typed account results.
Milestone 9 is complete: all-database-set mode derives every mapped modeled
five-star concrete set from the frozen database, preserves per-set coverage,
and orders extra package combinations by attainable real-artifact response
evidence. Milestone 10 is complete: canonical distinct-set account pairs use
the same exact reachability, lazy candidate, global no-reuse, and final GCSIM
pipeline, with reduced exhaustive parity. Milestone 11 is complete: the
five-star theoretical `4p` product preserves joint EM layouts, supports
parameterized-set defaults, validates at common fidelity, reraces close
leaders from every successful finalist attempt independently of display
`top_n`, persists verified finalist evidence, emits live typed progress, and
returns percent-to-best. Milestone 12 is complete: trusted GCSIM source
generates conservative 2p effect signatures, every distinct concrete pair
remains represented, only strictly proved static-equivalent effects share
work, and the theoretical pair product reuses the pair-aware equal-investment
layout/response/reliability loop. Milestone 13 is complete: the dedicated
GCSIM Browser optimizer panel, cancellable worker/adapter, and explicit
wearer/team preset save transaction are wired without a global AppShell
refactor. Milestone 14 reliability/performance evidence is in progress; the
optimizer is not release-ready and no Quick/Balanced/Deep modes are accepted.

This file is the technical source of truth for mechanics, invariants, source
boundaries, and the target search algorithm. Use
`GCSIM_ACCOUNT_ARTIFACT_OPTIMIZER_PIPELINE.md` for implementation order.

## 1. Accepted product model

| User mode | Domain | Result claim |
| --- | --- | --- |
| Account: selected set pools | All eligible real artifacts, but active packages are formed only from each wearer's selected concrete set pool | Best found for the frozen database/team/rotation under those pools |
| Account: all eligible database sets | All eligible real artifacts and every feasible modeled concrete set represented in the database, with rotation-conditioned pruning | Best found in the evaluated all-set account domain |
| Theoretical equal investment | Inventory-independent complete set packages, main stats, and abstract substats under one standard | Best found under equal investment for the frozen team/rotation |

One selected set is the simple case of a per-wearer set pool. The M13 UI
prefills the pool from the ready source config's active set lines.

For account requests, `include_2p2p` adds canonical distinct-set `2p+2p`
packages in either selected-pool or all-database-set scope. It does not replace
`4p` and does not permit `2p+1+1+1` or rainbow. Theoretical package shape is
selected by its explicit `4p` or `2p+2p` operation; theoretical requests do not
carry the account flag. The UI checkbox dispatches the appropriate operation
without merging their request or cache identities.

The backend retains separate schema-v4 operation/cache identities for
theoretical `4p`, theoretical `2p+2p`, and account artifacts. User-facing
`Quick/Balanced/Deep` speed modes are deferred until a correct algorithm is
measured. Internal quality-first work plans remain typed and versioned.

Default eligibility is 5-star only. A selected 4-star-only set or explicit
per-wearer artifact-ID allowlist can opt specific 4-star pieces into a request.

## 2. What GCSIM does and does not optimize

Upstream `gcsim -substatOptim` assumes the team, weapons, rotation, artifact
sets, and main stats are already fixed. It optimizes an abstract substat roll
allocation and emits new `add stats` lines.

GTT theoretical product requests use the patched engine with
`optimize_er=0;fine_tune=0`. The fixed KQM-standard rolls remain part of the
equal-investment envelope, but upstream automatic ER allocation and ER-vs-
damage fine tuning are disabled. The theoretical product boundary also rejects
every ER reference weight and every ER response-profile axis, including a
caller-supplied/manual profile. ER is never an automatic or manual theoretical
optimizer objective.

It does not:

- choose sands/goblet/circlet main stats;
- read GTT's artifact database;
- select real artifact IDs;
- enforce cross-character ownership;
- search set packages;
- return a physical five-piece build.

The legacy `run_workspace/gcsim/farming_layout_scan.py` coordinate scan starts
from a generic `ATK% / ATK% / CR` seed. It remains a compatibility component,
not the product authority: M11 preserves mandatory mixed/joint EM layouts, and
M12 passes the concrete theoretical pair package through the set-aware
layout/response path instead of substituting one 4p carrier as response truth.

Therefore:

- upstream optimization is one non-ER theoretical reference seed;
- GTT ordinary-sim layout/response discovery owns main-stat search;
- the real account optimizer owns artifact generation and no-reuse;
- final account ranking comes from whole-team ordinary GCSIM.

## 3. Current source map

### Current theoretical top-level flow

- `run_workspace/gcsim/farming_optimized_advisor.py`
  - automatic layout/response/set screening plus finalist optimization;
- `run_workspace/gcsim/farming_auto_advisor.py`
  - layout discovery followed by response/set/team screening;
- `run_workspace/gcsim/farming_advisor.py`
  - response/set/team screening for caller-provided layouts;
- `run_workspace/gcsim/farming_controller.py`
  - complete cheap `4p` screen and team composition;
- `run_workspace/gcsim/farming_finalist_optimizer.py`
  - bounded `substatOptim` plus ordinary-sim finalist validation;
- `run_workspace/gcsim/optimizer_runner.py`
  - isolated low-level optimizer process.

### Supporting modules

| Concern | Current module |
| --- | --- |
| Schema-v4 product contracts and `.v4` operation namespaces | `optimizer_product_contracts.py` |
| Trusted engine/source/executable/catalog binding | `optimizer_engine_context.py` |
| Static-target structural validation | `config_structure.py` |
| Theoretical main-stat rendering | `optimizer_config.py` |
| Complete theoretical `4p` rendering | `optimizer_set_config.py` |
| Set capabilities | `artifact_set_catalog.py` |
| Equal-investment profiles | `farming_profile_config.py`, `farming_search.py` |
| Legacy theoretical main-stat discovery | `farming_layout_scan.py` |
| Legacy theoretical stat-response discovery | `farming_response.py`, `farming_response_scan.py` |
| M4 set-aware reachable main/response boundary | `optimizer_main_response.py` |
| Ordinary GCSIM scheduling | `farming_evaluator.py` |
| Team composition | `farming_team_search.py` |
| Persistent ordinary-sim cache | `optimizer_cache.py` |
| Account stat normalization/rendering primitives | `hoyolab_export/artifact_db.py`, `hoyolab_export/stat_normalization.py`, `selected_team_config.py`, `config_blocks.py` |

The strict optimizer-specific arbitrary five-ID materializer is
`optimizer_artifact_materializer.py`. The reduced exhaustive reference solvers
are `optimizer_account_oracle.py` and `optimizer_theoretical_oracle.py`.

## 4. Current theoretical product

Current flow:

1. discover a small main-stat layout set;
2. discover generic non-ER stat-response profiles;
3. screen complete supported `4p` packages cheaply;
4. preserve raw leaders, uncertainty, coverage, and structural novelty;
5. compose bounded full-team states through seeds, beam, one-wearer changes, and
   selected exact two-wearer moves;
6. send a canonical finalist prefix through upstream `substatOptim`;
7. validate each optimized config through ordinary static-target GCSIM.

The product boundary is
`optimizer_theoretical_four_piece_service.py`. It requires five-star default
membership and joint/mixed EM preservation. The layout scan retains the best
measured layout plus `EM/EM/EM` and `EM/EM/CR`; the bounded Cartesian phase
still tests joint combinations of retained coordinate values. The existing
team composer explores rotating seeds and coordinated one- through
four-wearer states, while the reduced theoretical oracle exhausts explicit
adversarial domains.

Every displayed finalist first has one common validation fidelity. Leaders
whose DPS intervals overlap are rerun at a higher frozen iteration count; the
rerace candidate set is derived from every successful finalist attempt, not
the display-limited `outcomes` projection. Public output still obeys the
original `top_n`. Rerace evidence replaces rather than averages the earlier
estimate, and terminal provenance records distinct original-finalist and
rerace request hashes plus elapsed time including rerace. Successful
finalist snapshots are stored in the content-addressed persistent cache and
are revalidated from their exact input, optimized config, result JSON, engine,
catalog, options, and hashes even after the original run directory is gone.
Corrupt cache entries are ignored and recomputed. Product progress is emitted
live as the inner flow enters layout scan, response scan, joint search, final
validation, optional rerace, and completion. `LAYOUT_SCAN`, `RESPONSE_SCAN`,
`JOINT_SEARCH`, and `RERACE` are each delivered before the corresponding
blocking `stage.run()` begins; typed events include current leader/cache-hit
evidence.

Parameterized sets remain eligible only through pinned/default GCSIM behavior.
Arbitrary caller-supplied theoretical set parameters are not an implemented M11
contract; add a separate typed and engine-validated contract later if needed.
Four-star rendering remains supported, but default theoretical product
membership is five-star only.

Every current success means `BEST_FOUND` inside its evaluated heuristic domain,
never a global optimum.

## 5. Schema-v4 product contracts

`run_workspace/gcsim/optimizer_product_contracts.py` now defines:

- operation identities for theoretical `4p`, theoretical `2p+2p`, and account;
- selected-set-pool and all-database-set account scopes;
- typed numeric account character identity plus team slot/GCSIM key;
- engine/catalog-bound concrete set references and canonical package types;
- account `include_2p2p`, explicit 4-star set/ID overrides, and hard per-wearer
  minimum constraints in `stat_space=static_build_contribution`: normalized
  main/sub stats from exactly five artifacts plus only engine-proved
  unconditional static 2p set stats active for the target package;
- same-`ModKey` static set effects mirror GCSIM render-order overwrite instead
  of summing; conditional, parameterized, indirect, and unproved effects do not
  enter the floor;
- a versioned internal work plan with no `Quick/Balanced/Deep`;
- source config/rotation/target/options/engine and database-input identities;
- candidate/request/evaluation binding;
- mandatory account 4x5 assignment witnesses with global ID uniqueness;
- typed issues, replacement witnesses/counts, coverage/cache/timing counters;
- account absolute-DPS output without baseline/percent fields and theoretical
  percent-to-best output;
- strict schema-v4 request plus `.v4` cache/provenance namespaces and versioned
  progress/result parsers with
  deterministic canonical JSON round trips and fail-closed older-schema/
  unknown-field rejection;
- an existing-theoretical-4p compatibility projection that explicitly retains
  the richer in-process evidence object and is not described as lossless.

This remains a contract package, not a common executable runner. It performs no
database read, build materialization, search, save, or UI work.

## 6. Frozen engine and simulation contract

Every production operation starts from a trusted
`GcsimOptimizerEngineContext`, including:

- engine id/version;
- source tree and executable hashes;
- manifest hashes;
- artifact-set catalog fingerprint;
- renderer contract;
- combined binding.

Current renderer binding is `gcsim-v2.42.2`. The verified active local engine is
`gcsim-v2.42.2-20260726210410` with `patch_count=5`, including the explicit ER
optimizer-policy patch. Any source, binary, patch, or catalog drift must fail
closed until rebuilt/resealed.

Optimizer comparison remains static-target-specific:

- exactly one target statement;
- explicit very-high HP target;
- no target type that overwrites the pinned HP;
- no GTT wave directive;
- one options statement;
- structurally canonical optimizer-sensitive rows.

This is not an Abyss wave ranking. A different target model is a separate
product decision.

## 7. Prepared config boundary

The user reaches the optimizer from the existing GCSIM Browser after selecting a
team and rotation, so a ready config exists.

The optimizer freezes that config, removes all four existing artifact stat/set
blocks, and treats the result as a candidate shell. For every assignment it
inserts four newly materialized artifact blocks.

Only the following may be learned from the original artifact blocks:

- the active set key or keys used to prefill each selected set pool;
- set parameters already present in config as diagnostic suggestions. Their
  presence does not make arbitrary theoretical parameters an accepted product
  request.

The original artifact stats are not:

- an account baseline;
- a candidate;
- current-equipment truth;
- a filter over the database;
- a response/scoring reference after the shell is frozen.

The optimizer does not query current-equipment tables. It also does not need a
second artifact-free team builder: it needs a strict parser/replacer over the
already ready config.

Initial tests can use:

- `run_workspace/gcsim/smoke_fixtures/rotation_chasca_ororon_furina_bennett.txt`;
- `run_workspace/gcsim/smoke_fixtures/prepared_team_chasca_ororon_furina_bennett.json`.

## 8. Account database input and eligibility

The optimizer's raw account-artifact input is every `artifacts` row plus all
matching `artifact_substats` rows from `data/artifacts.db`.

Required rules:

- true SQLite read-only connection and one short consistent transaction;
- no importer or JSON call;
- no source/batch/timestamp membership filter;
- no equipment/preset/owner/lock/location lookup;
- no write-capable schema initialization;
- `artifacts.id` as allocation identity;
- exact stored rarity/level/main/sub values;
- deterministic all-row hash;
- no later SQLite query during a run.

Validation and eligibility are separate from loading:

- malformed required calculation fields mark that artifact ineligible with a
  typed issue and `artifact_id`;
- unrelated valid artifacts remain searchable;
- zero substats are valid;
- 5-star is eligible by default;
- 4-star is eligible only through explicit wearer/package/ID authorization;
- lower rarity remains in the frozen input but outside default search.

Run-level `not_ready/no_success` is appropriate only when the database read
itself fails or no complete legal four-wearer assignment remains.

Current local audit (2026-07-26):

- 520 artifact rows;
- 2068 substat rows;
- 513 5-star, 6 4-star, 1 2-star;
- no missing set UID, position, main type, or main value;
- one valid zero-substat 2-star artifact.

`content_fingerprint` may already have collapsed two physical exact twins into
one ID. This accepted pre-optimizer limitation is not a search blocker and must
not be redesigned here.

## 9. Set identity and parameters

Real inventory identity is concrete database `set_uid`. Simulation identity is
the validated GCSIM set key.

Use a typed set reference containing:

- `set_uid`;
- GCSIM key;
- active engine/catalog binding.

The current mapping hypothesis is `set_uid.casefold()`/lowercase matching the
GCSIM key. Always verify the result in the active registry. Never fuzzy-match a
localized display name.

If a set is active at 2p/4p, mapping is required. An unmapped one-piece offpiece
does not produce a set line and does not invalidate the artifact.

Set parameters:

- explicit values are rendered and included in request/config/cache identity;
- omission uses pinned GCSIM default/automatic behavior and is recorded;
- omission alone does not exclude the set;
- two parameter states may share work only if compiled behavior is identical.

GCSIM applies modeled set effects from `add set`. Do not manually add set
formulas to real artifact totals.

## 10. Strict real-build materialization

Canonical real-build identity is exactly:

```text
flower  -> artifact_id
plume   -> artifact_id
sands   -> artifact_id
goblet  -> artifact_id
circlet -> artifact_id
```

The materializer must validate:

- exactly one ID per slot;
- artifact metadata position matches the slot;
- all five IDs are distinct;
- every required stored stat maps exactly;
- set counts and target legality;
- exact values without empty-to-zero coercion;
- active set mapping/defaulted parameters.

It produces:

- exact IDs by slot;
- normalized main/sub totals;
- GCSIM `add stats`;
- GCSIM `add set`;
- active set counts/package;
- issues;
- compiled block/config hashes.

Five same-set pieces are one `4p` assignment. `3A+2B` is one canonical `A+B`
assignment. Free/offpiece position is derived and must not duplicate identity.

The existing `calculate_raw_build_summary(...)` and normalization paths are
useful parity references on valid fixtures, but they are too permissive to be
the optimizer's fail-closed production materializer. Add a strict
optimizer-specific adapter; do not alter old Artifact Browser/equipment behavior
as a side effect.

## 11. Target account search algorithm

The account algorithm is iterative, not a one-way
response -> candidates -> solver -> evaluator pipeline.

### 11.1 Feasible package and main-layout domain

Index eligible rows by slot, set, main stat, and response features.

Before scoring:

- prove set/slot feasibility with a small matching/DP check;
- enumerate sands/goblet/circlet triples actually reachable for a
  wearer/package;
- reject only impossible shapes, invalid mappings, and rarity-policy failures.

Selected-pool mode creates every requested feasible `4p` package. With the flag,
it also creates each distinct unordered pair in the pool.

All-set mode derives concrete sets from the frozen DB and active GCSIM catalog.
No static set tier list is allowed.

### 11.2 Rotation-conditioned reference branches

For each wearer/package/main region:

1. Build inventory-independent equal-investment full-team reference states. Do
   not reuse the source config's original artifact stats.
2. Run upstream substat optimization for fixed package/layout as one seed.
3. Apply one-roll and multi-scale perturbations through the real full-team
   rotation.
4. Preserve multiple piecewise branches for damage, support, threshold, mixed,
   set-only, and uncertain behavior.
5. Relearn around strong real joint assignments later.

This is what the old pipeline called a "stat response." It is not a permanent
character stat table. Its purpose is to avoid sending millions of real artifact
combinations to GCSIM while keeping rotation-relevant directions and thresholds.

Account user-specified minimum stats are legality constraints, never response
axes. Schema v4 names the space `static_build_contribution`: the exact
normalized main/sub contribution of five selected real artifacts plus only the
active package's engine-proved unconditional static 2p set-stat contribution.
For example, Emblem of Severed Fate 2p contributes +20% ER (`er=0.20`). Effects
with the same `ModKey` follow the materializer's set-row render order and later values
overwrite earlier ones; conditional, parameterized, indirect, and unproved set
effects count as zero. Package-specific guaranteed set stats are translated
into effective artifact-only bounds for partial pruning, then the complete
static-build floor is checked again before materialization and GCSIM. ER is
never automatically balanced: it is only another axis for this explicit
account floor. Infinite/boosted energy remains an independent frozen simulation
option and neither creates nor disables a floor.

A later account UI may show familiar final-sheet ER, but it must derive the
required `static_build_contribution` through the same frozen stat calculator:
subtract the complete non-artifact baseline, including base ER and every frozen
static character/weapon contribution, rather than hand-subtracting only one
weapon or character value. The UI must not subtract a package's static 2p bonus;
the backend applies that package-specific proved contribution itself. The
current theoretical operations do not accept this account constraint. A
theoretical floor is a separate future contract and must not be implied by the
account field.

### 11.3 EM/main-stat safeguard

The search must not infer joint main-stat value from isolated changes around
`ATK/ATK/CR`.

- Probe EM at several roll scales.
- If EM is material beyond noise, changes reaction ownership, or becomes
  nonlinear, force EM-heavy/mixed branches to survive.
- Directly test reachable coupled layouts including `EM/EM/EM`, even if each
  isolated slot change loses.
- Repeat the EM test near real account leaders.
- Apply equivalent interaction safeguards to non-ER caps and unusual
  HP/DEF/healing branches. ER enters only through an explicit account floor.

No character-name exception.

### 11.4 Lazy artifact/build generation

Do not make one global "top artifacts" cut.

For each package/layout/response branch, use a lazy best-first
branch-and-bound/DP generator. A partial build carries:

- selected IDs/slots;
- current/remaining set feasibility;
- exact accumulated stat vector;
- cap/threshold region;
- optimistic remaining-slot bound.

Retain explicit diversity:

- score leaders;
- Pareto stat frontier;
- high useful-stat/crit-mass pieces;
- explicit minimum-floor feasibility plus crit/HP/DEF/healing thresholds;
- EM and unusual mains;
- offpiece/set-count shapes;
- uncertain/model-error branches;
- contested-ID alternatives.

Crit Value is a feature, not a universal rule. A weak crit artifact needed to
satisfy an explicit floor, or with material EM/HP/DEF utility, must survive its
relevant branch. ER has no automatic response branch.

If artifact A dominates B locally, B still cannot be destroyed globally:
A may be needed by another wearer. Keep dominated/conflict alternatives in a
lazy shadow index.

### 11.5 Global no-reuse proposals

The joint solver chooses one complete build per wearer and enforces twenty
distinct IDs.

It:

- solves bounded pools exactly where practical;
- uses surrogate values only for proposal order;
- retains package/layout/response/conflict diversity;
- asks lazy generators for more alternatives when an ID is contested;
- explores coordinated two-, three-, and four-wearer repairs;
- remains deterministic and wearer-order-independent.

It proposes states; it does not know final team DPS before GCSIM.

### 11.6 Whole-team feedback

```text
reference branches
  -> lazy wearer builds
  -> disjoint team proposals
  -> low-fidelity whole-team GCSIM
  -> leader/uncertainty/threshold/EM/conflict evidence
  -> branch and pool enrichment
  -> new proposals
  -> common high-fidelity finalists
```

Low fidelity is screening only. Every displayed finalist receives one common
minimum high-fidelity regime; that result replaces its screening estimate.
Close leaders receive higher-fidelity reraces. Do not average incompatible
fidelity/seed regimes without a defined statistical model.

### 11.7 All-set garbage pruning

All-set mode must prevent clearly losing real crit-mass/package combinations
from reaching expensive simulations.

Safe hard filters:

- malformed or disallowed rarity;
- slot/set infeasibility;
- unavailable main layout;
- invalid active set mapping;
- duplicate IDs.

Conservative heuristic filters:

- package/layout's best attainable real-artifact bound loses beyond uncertainty
  plus calibrated model-error margin;
- partial build's optimistic remaining-slot bound cannot reach the current
  frontier;
- candidate is outside the score/confidence frontier and represents no
  EM/threshold/unusual-main/structural/conflict-repair branch.

A set is never pruned because it is unpopular or "bad on this character" in a
static table. A weak theoretical set with exceptional real artifacts can remain.
A strong theoretical set with poor real artifacts can be removed before a full
real-candidate sim.

Every heuristic pruning stage must expose counters and oracle removal traces.

### 11.8 Replacement groups

Different ID assignments can compile to identical GCSIM set/stat text.

- Simulate one compiled config once.
- Keep one canonical assignment witness.
- Keep a bounded conflict-diverse set of alternate witnesses.
- Record the total equivalent count and `has_many_replacements`.

Do not fill result top-N or search beams with many identical stat configs. This
lets the solver continue changing other wearers and testing materially different
main/EM branches.

Near-identical wearer builds may share one bounded proposal-diversity cluster so
they do not consume the whole beam. Keep their IDs in the lazy replacement pool,
preserve conflict/main/EM-distinct representatives, and report the cluster as
having many replacements. They cannot reuse one simulation result unless their
compiled configs are exactly identical. Any numerical near-equivalence threshold
is versioned and must be calibrated against oracle/rerace evidence.

## 12. Theoretical equal-investment search

The theoretical mode compares full four-character set/main/substat states under
one versioned investment envelope. Account artifact quality is irrelevant.

Theoretical runs pin `optimize_er=0;fine_tune=0` on the verified patched engine.
The fixed KQM-standard rolls remain in the equal-investment allocation; only
automatic liquid ER allocation and ER-vs-damage fine tuning are disabled. The
product boundary also fails closed on ER reference weights and on any ER axis in
automatic or caller-supplied/manual response profiles. Account
`static_build_contribution` constraints are not accepted here. If a later
product needs theoretical stat floors, add a separate typed contract and equal-
investment semantics instead of reusing the real-artifact field silently.

Default domain:

- 5-star main-stat standards;
- complete `4p`;
- complete distinct-set `2p+2p` when the flag is enabled;
- no lone `2p` or rainbow;
- parameterized sets use pinned/default behavior; arbitrary explicit
  theoretical parameters remain a future contract.

Required hardening over current code:

- joint main-stat coverage/EM safeguard;
- set-aware response/layout reopening;
- coarse roll exchange around caps/thresholds;
- coordinated one- through four-wearer changes;
- feedback/enrichment rather than one canonical prefix only;
- common-fidelity finalist ranking and close-leader rerace.

Result projection:

- rank;
- absolute sim DPS;
- `candidate_dps / best_dps * 100`;
- uncertainty/tie;
- sets, mains, and optimized abstract stats;
- complete equal-investment/engine/config provenance.

Rank one is always `100%`. Do not call this a baseline delta.

### Engine-derived 2p equivalence

Theoretical `2p+2p` uses engine-bound descriptors generated from trusted GCSIM
implementation/catalog behavior:

- only the narrow proved unconditional static-stat shape may share work;
- the proof includes literal modifier key and whether the pair has distinct or
  colliding modifier keys;
- `UNIQUE_SOURCE`, conditional, parameterized, indirect, and unknown effects
  remain opaque and single-alias;
- same-`ModKey` pairs are also single-alias because application order/collision
  semantics cannot be transferred safely;
- every concrete pair remains available for display;
- if equivalence cannot be proved automatically, use a unique signature.

The verified active engine domain contains 39 modeled five-star 2p descriptors,
741 distinct concrete pairs, 526 conservative proof groups, 25 proved static
descriptors, and 14 opaque `UNIQUE_SOURCE` descriptors.

Do not make a manually maintained per-set equivalence table the primary truth.

Account mode never collapses concrete set UIDs, because their physical inventory
pools differ. When a theoretical alias group is transferred to account search,
transfer its concrete aliases as an editable selected set pool.

## 13. Cache, provenance, and result identity

Keep two identities separate.

Simulation cache identity includes only inputs that can change GCSIM output:

- evaluator schema;
- trusted engine binding;
- exact compiled config hash;
- simulation options;
- fidelity/iterations/seed/execution semantics.

Assignment/result provenance includes:

- operation/schema;
- source request/config/rotation/target identity;
- frozen all-row DB-input hash;
- account scope and selected set pools;
- 4-star eligibility overrides;
- all twenty artifact IDs;
- exact compiled-config witness;
- work-plan/scoring versions;
- evaluated budget and stop reason.

A simulation-cache hit can serve a different physical assignment only when the
compiled config/execution identity matches. It can never transfer the old
assignment witness or request provenance.

Run directories and cache need an explicit retention/eviction policy before
large account runs. Current farming run directories are not covered by the
general GCSIM cleanup path, so unbounded production search would grow disk.

## 14. Result and persistence boundary

Account results currently need:

- typed terminal status and stop reason;
- rank and absolute whole-team sim DPS;
- DPS uncertainty/iterations;
- exact source/engine/config/DB/work-plan identities;
- coverage/cache/timing counters and typed issues;
- four wearer rows;
- five exact artifact IDs by slot per wearer;
- set counts/package and normalized stats;
- bounded replacements/many-replacements marker.

There is no account baseline or required percent-to-best display.

Search performs zero writes. The result is ephemeral in the optimizer view.
Changing relevant input, starting a new search, or closing the view without
saving discards it. It is not History.

Confirmed later explicit UI flow:

- per-wearer `Save preset`;
- default name `best_found_<other three team members>`, editable by user;
- `Save team` reuses already saved wearer presets and creates only missing ones;
- create one GCSIM-only multi-preset referencing those four preset IDs;
- no separate generic multi-preset constructor;
- no auto-equip during save;
- later explicit multi-preset apply may equip all four atomically.

Current storage has character artifact presets but no GCSIM four-preset entity.
That schema/service belongs to the later UI/save milestone, not account search.

## 15. Existing-code intervention boundary

Optimizer-owned modules may be changed or replaced as needed.

Preferred integration changes:

- add new strict optimizer DB/materializer/search modules;
- reuse pure normalization/rendering pieces;
- extract a generic ordinary-GCSIM process/cancel/cache core from
  `farming_evaluator.py` if needed;
- preserve the existing theoretical API through a compatibility adapter and
  focused regression tests;
- add narrow GCSIM Browser wiring only in the later UI milestone.

Do not fix unrelated old subsystems "along the way":

- importer numeric/provenance behavior;
- `content_fingerprint` identity;
- equipment ownership/move behavior;
- Artifact Browser preset semantics;
- History/RunSession persistence;
- global AppShell architecture.

If an optimizer requirement truly needs behavior changed in one of those
existing contracts rather than wrapped, discuss it with the user first.

## 16. CPU, cancellation, progress, and trace

- Work runs outside the UI thread.
- `Auto` initially reserves at least one logical CPU:
  `max(1, logical_cpus - 1)`.
- GCSIM `workers` and `GOMAXPROCS` are explicit.
- Sum of assigned workers across live processes cannot exceed the CPU budget.
- Long processes run below normal priority on Windows.
- Cancellation stops new work and terminates only disposable optimizer
  processes.
- Failed/cancelled partial files are never parsed/cached as success.
- Adaptive work reports counters/current plan or upper bound; it must not invent
  a final exact planned count.

Trace retained in normal production:

- aggregate stage counters;
- bounded leader/enrichment/pruning examples;
- current best and stop reason.

Full state trace is debug-only. Reduced oracles retain the exact winner path and
removal stage.

## 17. Reliability gate

Exactness requirements:

- exact top-1 parity in hand-checkable reduced exhaustive modes;
- exact slot/set legality and global no-reuse;
- deterministic canonical identity.

Production heuristic evidence:

- oracle-winner survival per pruning stage;
- top-N recall;
- best-DPS regret and maximum miss;
- randomized reduced inventories against exhaustive enumeration;
- adversarial EM joint-layout, explicit ER-floor/no-auto-ER policy, crit caps,
  HP/healing, DEF, support-only, duplicate-buff, unusual-main, contested-ID,
  and three/four-wearer fixtures;
- common-fidelity/rerace stability;
- runtime/memory/cache/cancel metrics on the real database.

Do not set a speed-mode SLA before this evidence exists. Quality is the first
gate. Speed buttons, if useful, are a later measured product decision.

## 18. Verification commands

Focused GCSIM backend:

```powershell
.\.venv\Scripts\python.exe -m unittest discover `
  -s tests\run_workspace\gcsim -t . -p "test_*.py"
```

Full repository:

```powershell
.\.venv\Scripts\python.exe -m unittest discover `
  -s tests -t . -p "test_*.py"
```

Every search milestone also needs its reduced oracle tests. Real-engine smokes
prove compatibility only; they do not prove ranking recall.

## 19. Current implementation boundary and immediate next task

Milestone 1 is complete:

- `optimizer_config_shell.py` strictly identifies the four canonical
  character/weapon/artifact blocks, replaces only set/stats rows with four
  inert wearer markers, preserves every other config byte, and exposes active
  `count >= 2` set lines plus engine-valid `+params=[...]` values only as source
  suggestions;
- `optimizer_artifact_database.py` opens the unified SQLite database with URI
  `mode=ro`, enables `query_only`, freezes every `artifacts` and ordered
  `artifact_substats` row in one short read transaction, closes SQLite before
  validation, and emits deterministic raw-input identity;
- malformed calculation rows remain frozen but become ineligible with typed
  artifact issues; unmapped sets remain valid as possible one-piece offpieces;
- 5-star rows are eligible by default, while 4-star admission is explicitly
  scoped to the typed wearer plus selected package/set or artifact ID;
- the implementation does not call importer, equipment, preset, owner, lock,
  location, schema-init, or UI/AppShell code.

The real local database smoke loaded 520 artifacts and 2068 substats, retained
the valid zero-substat row, admitted 513 valid 5-star rows by default, and made
no database write or journal-mode change.

Milestone 2 is complete:

- `optimizer_run_input.py` binds the schema-v4 account request, trusted engine
  catalog, M1 config shell, and frozen all-row database without retaining a
  SQLite connection;
- the M1 raw database hash remains the request/snapshot identity, while a
  separate deterministic M2 hash contains only exact calculation-relevant
  artifact/substat fields;
- `optimizer_artifact_materializer.py` requires one exact ID for every slot,
  validates physical slot/rarity/stat/set/package legality, preserves every
  stored main/substat contribution including `+0`, and uses exact decimal
  percent-point conversion;
- physical set counts render canonical active `add set` rows, including
  engine-validated integer `+params`; omitted known parameters are explicit
  non-blocking default/automatic notices;
- set effects are never added to the artifact main/sub totals themselves;
  minimum-stat evaluation combines them separately with only the frozen engine-
  proved unconditional static 2p contribution;
- the full-team compiler replaces exactly four shell markers and records hashes
  for the physical assignment, compiled config, non-artifact segments,
  replacement proof, execution semantics, and simulator identity;
- simulator-identical compiled configs can share one simulation hash while a
  bounded witness bucket retains distinct physical 4x5 assignments.

A real-engine smoke used twenty IDs from the local database, compiled the
Chasca/Ororon/Furina/Bennett fixture, and completed 10 GCSIM iterations with
return code 0 and mean DPS `4384.571005815334`.

The root `run_workspace.gcsim` facade exports the implemented
`render_gcsim_four_star_set_optimizer_config` name. Its regression test checks
that every `__all__` entry is bound and that wildcard import succeeds.

Milestone 3 is complete:

- `optimizer_oracle.py` owns typed scores, strict reduced-domain limits, and the
  ordered audit that reports the first future pruning stage removing an oracle
  winner;
- `optimizer_account_oracle.py` exhaustively enumerates legal five-slot `4p`
  builds through the M2 materializer, then all four-wearer combinations,
  enforces global no-reuse, compiles every disjoint assignment, evaluates each
  unique simulator identity once, and retains bounded physical witnesses;
- its hand-checkable fixture has wearer domains `8 x 7 x 7 x 7 = 2744`, exactly
  `260` conflicted and `2484` disjoint assignments, `324` simulator-identical
  replacement pairs, and `2160` unique evaluations; all five offpiece positions,
  `5p`, one contested artifact, and one malformed row are explicit;
- `optimizer_theoretical_oracle.py` forms each wearer domain as the explicit
  Cartesian product of typed complete `4p` packages and typed legal
  main-layout/equal-investment stat states. The adversarial fixture covers all
  zero- through four-wearer changes in 96 states with change-count distribution
  `(0:1, 1:10, 2:32, 3:38, 4:15)` and includes crit-cap, fixed-roll/no-auto-ER,
  coupled EM, HP, DEF, healing/team-buff, and duplicate/non-stacking branches;
- `optimizer_reduced_oracle_smoke.py` is an explicit local smoke, not a unit
  dependency. The committed Chasca/Ororon/Furina/Bennett fixture compiled one
  reduced physical assignment across four engine-modeled 4-star-only sets and
  completed one real 10-iteration GCSIM evaluation with finite positive
  DPS/standard-error output; the exact 10-iteration value is stochastic. This
  proves compatibility only, not ranking or balance truth;
- the public oracle entry points require an external typed evaluator and reject
  domains above explicit safety limits. No production beam, pruning model,
  account service, UI, or AppShell work was added.

Milestone 4 is complete:

- `optimizer_main_response.py` proves all legal sands/goblet/circlet layouts
  reachable from the frozen eligible database for one wearer/concrete `4p`
  package. The proof is slot-local matching/DP-style feasibility, not complete
  artifact-build enumeration;
- every reachable layout receives an inventory-independent five-star
  equal-investment reference. Exact one-, four-, and eight-roll exchanges cover
  non-ER response axes and mixed EM interactions while preserving the roll
  budget and investment signature. ER is not probed as an optimization axis;
- response reduction is package-local and retains independent set-only,
  damage, threshold, support, mixed, unusual-main, uncertain, upstream-seed,
  and coupled-EM branches with branch-to-probe trace evidence;
- material EM response, reaction-ownership change, nonlinearity, or unresolved
  EM evidence forces every reachable mixed-EM and joint-EM main layout to
  survive. Direct joint layouts are evaluated even if all isolated EM layouts
  lose. No character-name rule participates;
- upstream `substatOptim` output is represented only as an additional seed and
  cannot delete independently retained main/stat regions;
- `materialize_gcsim_optimizer_response_probe(...)` round-trips each exact
  integer allocation through the existing trusted theoretical renderer and
  freezes the other three wearer states plus the full rotation;
- the adversarial suite covers renamed character identity, isolated-EM losses
  with an `EM/EM/EM` winner, no-auto-ER policy, HP/healing, DEF, unusual mains,
  set-aware response reopening, incomplete evidence, exact allocation
  conservation, and complete branch traces;
- `optimizer_main_response_smoke.py` materializes reference and four-roll EM
  exchange configs for the committed Chasca/Ororon/Furina/Bennett rotation and
  completes both through the active engine at 10 iterations. Exact DPS is
  stochastic and is not ranking evidence.
- `optimizer_lazy_candidates.py` builds its index only from the frozen all-row
  M2 run input. It applies strict row normalization, request-scoped rarity
  eligibility, exact slot/main-layout matching, and concrete 4p feasibility;
  it does not read equipment, presets, import provenance, or SQLite.
- Each M4 response branch is bound to a versioned additive proposal model.
  Models may be explicit or derived from observed M4 roll-exchange slopes.
  They order proposals only; they are not a DPS claim and do not replace the
  later full-team GCSIM evaluation.
- The stateful best-first stream carries physical IDs, exact accumulated stats,
  target-set feasibility, threshold/cap regions, and a set-feasible optimistic
  remaining-slot bound. Only completed candidates requested by the caller are
  passed through the strict M2 materializer; lower bounded states remain lazy.
- Retention can add exact leaders for `5p`, every offpiece slot, response-useful
  stats, and raw crit value. Threshold, EM, unusual-main, and uncertain
  alternatives remain independent M4 branches rather than character-specific
  exceptions. Returned batches expose a Pareto projection and coverage counts.
- Component-dominated or simulator-identical physical rows remain in the
  shadow index. `request_conflict_repair(...)` can exclude contested IDs and
  produce another physical witness; identical simulator text is marked by the
  existing compiled-block `content_fingerprint`, not deleted from the search.
- The reduced M5 suite proves exact ordered top-K parity, all six 4p/5p shapes,
  survival of a low-crit EM-threshold artifact, upper-bound laziness, shadow
  repair, identical-content fingerprints, and database-row-order invariance.
- `optimizer_joint_proposals.py` canonicalizes the four wearer pools by stable
  team slot and solves their current finite Cartesian domain best-first. Every
  emitted proposal is compiled through M2 and proves twenty distinct IDs.
- Candidate proposal scores and typed evidence-bound adjustments affect order
  only. The solver returns proposals, never a DPS claim; M7 remains responsible
  for full-rotation simulation and final ranking.
- A contested local-top state triggers continuation pulls and blocked-ID M5
  shadow requests. The same search naturally explores coordinated two-,
  three-, and four-wearer changes without greedy wearer ordering.
- Cancellation and deadline return only a valid compiled best-so-far when one
  already exists. Pool exhaustion, model-bound pruning, state limit,
  cancellation, deadline, finite-domain exhaustion, and requested completion
  are separate typed stop reasons with aggregate coverage.
- The reduced M6 suite matches the exhaustive four-wearer oracle score, proves
  wearer-order invariance, reassigns a contested artifact after typed feedback,
  finds a three-wearer repair, and exercises every required stop boundary.
- `optimizer_feedback_loop.py` owns a cancellable M7 session over the existing
  ordinary-GCSIM scheduler and cache. Screening, finalist, and rerace fidelity
  have distinct request/cache identities; an overall deadline is carried
  across every adaptive batch.
- Exact simulator-identical compiled configs share each engine run while their
  physical assignment witnesses remain available as bounded replacements.
  Low-fidelity estimates never appear as final evidence.
- Typed enrichment can add proposals or evidence-bound M6 score adjustments.
  EM, threshold, unusual-main, and explicit structural labels protect
  non-leading branches from premature finalist deletion.
- Every feedback-enriched proposal is revalidated fail closed against the full
  package-specific `static_build_contribution` floor before it can enter the
  ordinary-GCSIM scheduler; the same check is repeated at the evaluation gate.
- Every displayed row has common minimum finalist fidelity. Close leaders use
  higher-fidelity rerace evidence, which replaces rather than averages earlier
  estimates, and expose an honest uncertainty label with absolute DPS only.
- Cancellation, deadline, no-success, partial-error, and exhausted-work-plan
  outcomes are typed. Failed or cancelled evaluations are not cached as
  successes, and trace retention is bounded with aggregate coverage counters.
- The M7 suite proves enrichment recovery, EM protection, cache-equivalent
  semantics, cancellation cache safety, close-leader reraces, and preservation
  of physical witnesses.
- `optimizer_reference_anchors.py` exhausts small joint layout/set domains and
  otherwise retains quality-first structural anchors, including coordinated
  EM/support/unusual-main states and explicit stat-floor boundary witnesses,
  before any real-artifact pruning. ER is not an automatic anchor.
- `optimizer_selected_pool_service.py` is the complete read-only account
  backend. It searches every feasible selected concrete `4p` package and,
  when requested, every canonical distinct-set `2p+2p` package and every
  four-wearer package combination, composes M4 response discovery, M5 lazy
  candidates, M6 all-different proposals, and M7 whole-team validation, and
  returns exact twenty-ID account witnesses with absolute DPS.
- Account request minimum-stat constraints are merged into M5 package-specific
  feasibility thresholds. Impossible partial branches and complete below-floor
  builds stop before materialization/GCSIM. The schema-v4
  `static_build_contribution` is exact normalized main/sub stats from five real
  artifacts plus only engine-proved unconditional static 2p stats active for
  that package. It includes Emblem 2p +20% ER (`er=0.20`), mirrors same-`ModKey`
  render-order overwrite, and excludes conditional/parameterized effects. ER can use
  this generic `stat >= X` floor, but is never an automatic balancing objective.
- Infeasible user-selected packages are not silently lost: the result contains
  a typed package issue plus feasible/infeasible/package-combination coverage
  counters. The service performs no database, equipment, preset, UI, or
  AppShell writes.
- The M8 completion suite contained 564 GCSIM backend tests.
- `optimizer_all_set_service.py` derives concrete set references only from
  default-eligible 5-star rows whose frozen engine capability is registered
  and has a complete modeled 4p effect. Unmapped, 4-star-only, and incomplete
  engine packages cannot enter the all-set target domain.
- Every reachable wearer/set target appears in a required rotation of M6 joint
  combinations. The current attainable-bound leader is also required; the
  remaining bounded combinations are enumerated best-first by equal-investment
  reference DPS adjusted with the exact best real candidate under each M4
  additive response model. This is evidence ordering, not a DPS claim.
- Required rotations distribute different sets across wearers to avoid
  inventing an all-same-set inventory conflict. Required package combinations
  and the attainable-bound leader receive M7 validation before optional extra
  proposals fill the feedback budget.
- A typed decision accounts for every derived wearer/set package as retained,
  safely infeasible, or not evaluated after an interruption. Package bounds,
  decision counts, selected combinations, cache/timing, and exact terminal
  provenance remain visible.
- The M9 suite proves all-set derivation, per-set joint coverage, global
  twenty-ID results, randomized reduced-frontier best recall/zero regret, a
  theoretically weak set winning through exceptional real pieces, and an
  unattainable real stat floor reaching no final GCSIM run.
- Milestone 10 extends M4/M5/M6/M7 to canonical distinct-set pairs. `A+B` and
  `B+A` share one identity; `A+A`, lone `2p`, and rainbow are not packages.
  Exact set-count DP admits `2+2+1`, `3+2`, and `2+3`, while concrete set UIDs
  and physical artifact IDs remain distinct.
- Pair response probes render two explicit `count=2` GCSIM rows. The account
  exhaustive oracle records the deterministic free slot and both canonical
  shape families; pair fixtures prove reduced exhaustive winner parity,
  contested-ID resolution, exact twenty-ID output, and all-set pair coverage.
- With pairs enabled, the all-set frontier also requires one deterministic
  distinct-4p low-conflict seed so package coverage cannot consume a small
  work plan without any physically plausible starting team.
- The M10 completion suite contained 578 GCSIM backend tests.
- Milestone 11 adds the native theoretical `4p` product boundary. Product
  requests require five-star defaults, `optimize_er=0;fine_tune=0`, and the
  joint EM safeguard; ER reference weights and ER response profiles fail closed.
  Close leaders are selected from all successful finalist
  attempts independently of display `top_n` and reraced at higher common
  fidelity; percent-to-best is calculated from final evidence. Parameterized
  sets use pinned engine defaults only.
- Finalist cache entries persist the exact byte snapshots and typed runner
  diagnostics behind the existing content identity. Cache hits survive removal
  of transient run directories and are revalidated before use.
- Typed progress transitions are emitted live as preflight, layout, response,
  joint search, final validation, optional rerace, and completion begin. The
  `LAYOUT_SCAN`, `RESPONSE_SCAN`, `JOINT_SEARCH`, and `RERACE` events are each
  delivered before the corresponding blocking `stage.run()` call. The
  theoretical oracle and
  composer tests cover zero- through four-wearer coordinated adversarial
  states.
- Original-finalist and rerace request hashes remain distinct in terminal
  provenance, and elapsed time includes rerace work.
- Milestone 12 derives 2p signatures from the trusted engine source. Only the
  narrow proved unconditional static-stat shape is grouped, and its proof
  includes modifier-key relation. Parameterized, conditional, indirect,
  unknown, and `UNIQUE_SOURCE` implementations keep unique engine-bound
  identities; same-`ModKey` pairs are single-alias.
- The active engine exposes 39 modeled five-star 2p sets, 741 distinct
  concrete pairs, and 526 conservative proof groups: 25 descriptors have the
  narrow static proof and 14 are opaque `UNIQUE_SOURCE`. All concrete aliases
  remain in the result domain while one representative per safely shareable
  group is simulated.
- The theoretical pair product uses two explicit distinct `count=2` set rows,
  canonical `3+2` slot metadata, and the same five-star equal-investment
  reliability loop as theoretical `4p`. Its main-layout and response evidence
  is derived with the actual pair package active, not a substituted 4p carrier.
  Its reduced exhaustive oracle covers coordinated four-wearer changes.
- Milestone 13 adds `optimizer_ui_adapter.py`, `optimizer_worker.py`, and a
  dedicated `optimizer_panel.py`. The adapter freezes the selected team and
  rotation, uses the unified artifact database only for account candidates,
  preserves source set parameters when they prefill a selected pool, converts
  final-sheet ER floors to artifact-only minimums from the artifact-free
  display baseline, and dispatches the typed selected/all/theoretical service.
- Account results remain ephemeral until an explicit save click.
  `optimizer_save.py` creates one normal Artifact Browser build preset for a
  wearer, or atomically creates missing wearer presets plus one four-member
  GCSIM optimizer team preset. Existing build IDs are reused only after exact
  character and five-artifact validation. Search and save never equip,
  overwrite, or create History.
- Milestone 14 adds typed quality and benchmark evidence in
  `optimizer_release_gate.py` and `optimizer_benchmark.py`. The response scan
  measures every reachable main layout but builds the expensive exchange plan
  only after retaining measured leaders plus every structural/stat response
  region. The reference-only builder avoids constructing thousands of probes
  that would immediately be discarded. Independent-context scheduler batches
  share one verified engine snapshot but expose no invalid cross-context
  ranking.
- The selected-pool work-plan version is 2 and includes reference/response
  scheduler budgets, candidate retention, joint-search, enrichment, and
  feedback budgets in its identity. Coverage includes reference layouts,
  deeply probed layouts/probes, branches, combinations, proposals, and final
  simulations.
- Real 2026-07-28 selected-pool `4p` run, local 520-row DB, committed
  Chasca/Ororon/Furina/Bennett rotation, CPU 15: the pre-fix path hit its
  1,944.75 s deadline; the corrected mixed cold/warm path completed
  `best_found` in 802.094 s; the fully warm repeat completed in 327.157 s
  (330.703 s wall), returned 6 rows, and produced a 49,288.7566 DPS leader at
  1000 iterations. Cancellation latency measured 0.057 s. A coordinator-only
  101,249,024-byte sample is not a valid process-tree peak. This is useful
  evidence, not a passed release gate: the full selected/all-set,
  `4p`/`4p+2p+2p`, cold/warm benchmark and randomized oracle corpus remain.
- Current full GCSIM backend suite: 618/618 tests passed in 160.976s on
  2026-07-28.

The legacy `farming_layout_scan.py` remains available to the existing
experimental theoretical advisor, but its `ATK/ATK/CR` coordinate result is not
an account-pruning authority for the new pipeline.

NEXT: continue Milestone 14. Do not claim release readiness until the complete
quality/benchmark matrix is recorded and acceptable. The current fully warm
selected-pool case still spends about 208 s in response discovery and 100 s in
joint search, so all-set/`2p+2p` expansion must not be waved through with a
larger timeout. No speed-mode design precedes this evidence.
