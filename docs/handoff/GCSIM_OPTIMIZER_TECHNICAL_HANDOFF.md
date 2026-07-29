# GCSIM Optimizer Technical Handoff

Last updated: 2026-07-29.

This is the authoritative backend contract for the GCSIM artifact optimizer.
It describes the current implementation and the remaining calibration/release
work. Historical milestone logs and superseded response experiments belong in
Git history, not in this file.

## 1. Current status

| Product operation | Backend | Status |
| --- | --- | --- |
| Account artifacts, selected set pools | `optimizer_anytime_selected_service.py` | Functional; paired stat-response v2 active; real UI calibration still required |
| Account artifacts, all feasible database sets | `optimizer_all_set_service.py` | Paired set-impact, source-package recall anchor, and bounded per-signature physical refinement active; wider UI calibration remains |
| Theoretical equal-investment 4p | `optimizer_theoretical_anytime_service.py` | Impact-driven package search plus fair full-main-layout witnesses active; focused and real-engine regressions passed |
| Theoretical equal-investment 2p+2p | `optimizer_theoretical_anytime_service.py` | Single-2p-first package search plus fair full-main-layout witnesses active; focused and real-engine regressions passed |

Every result means:

> best build found under the frozen, versioned work plan

It is not a claim of an exhaustive mathematical optimum.

There are no accepted user-facing `Quick`, `Balanced`, or `Deep` speed modes.
`screen_8`, `refine_32`, `validate_200`, and `rerace_1000` are internal
fidelity phases, not product modes.

## 2. Product operations

### 2.1 Account: selected set pools

The user selects one or more concrete packages for each wearer:

- one selected set per wearer is the simple/default case;
- several selected sets form an editable pool;
- the source config's active set is only a default UI suggestion;
- every selected package is mandatory search input and is not screened away by
  broad all-set heuristics;
- all eligible artifacts from the complete database that can form the selected
  package participate;
- every exact candidate keeps its real GCSIM set effect active;
- optional account `2p+2p` adds canonical distinct-set packages.

### 2.2 Account: all database sets

This mode uses the complete read-only artifact database captured at run start.
It considers only trusted modeled packages that are physically formable from
eligible database artifacts.

For a 4p package, physical feasibility requires four distinct usable artifact
slots from that set; a raw count of four same-slot rows is insufficient. A
complete five-slot wearer build must also be possible. Joint team proposals are
rechecked against global artifact-ID no-reuse.

The source/current set receives no score or winner preference. Its resolvable
four-wearer package signature is nevertheless an obligatory recall/control
anchor: artifacts for it are rebuilt from the complete frozen database and it
is simulated alongside other shortlisted signatures. Broad search is
explicitly two-level:

1. measure the set effect for every feasible `(wearer, package)`;
2. retain positive and uncertain packages conservatively;
3. guarantee physical candidate coverage for retained packages;
4. search feasible ordered four-wearer package combinations;
5. regenerate physical candidates inside up to eight shortlisted package
   signatures, source anchor first when resolvable;
6. screen every generated local proposal and run the ordinary exact race.

Artifact substats must not decide which set bonuses are ever tried.

### 2.3 Theoretical equal investment

Theoretical `4p` and `2p+2p` are separate typed operations. They:

- never read account artifacts;
- ignore source/original artifact sets and stats;
- use trusted modeled five-star engine packages;
- compare complete four-character states under the same legal main-stat and
  liquid-substat investment budget;
- keep each exact modeled set effect active in GCSIM;
- preserve concrete package identity even when engine-proved effect-equivalent
  packages share proposal evidence;
- report percent-to-best inside the same operation, with rank 1 at 100%.

The corrective theoretical package-search gate is implemented. Every 4p
package, and every engine-proven 2p effect component/equivalence class, receives
set-impact coverage before bounded joint package proposals are chosen. Hash or
catalog order does not decide which packages reach simulation. For 2p+2p, the
actual prospective concrete-pair mapping remains attached through terminal
packaging; a missing synthetic pair key fails closed instead of being
misrepresented as a 4p set.

All retained packages stay typed/auditable. When that domain is wider than the
64-run quick tier, a deterministic paired-impact shortlist selects at most 30
package anchors per wearer and reports retained-but-unscreened counts instead
of failing the operation or pretending full coverage. Every shortlisted
wearer/package first gets an explicit `balanced` full-main-stat anchor.
Additional complete main-stat triples are distributed round-robin by package,
including generic scaling, EM/reaction, elemental-damage, and crit archetypes
inferred from measured response. A narrow focus profile can no longer
masquerade as coverage for a different complete layout. The final validated
result carries the exact sands/goblet/circlet mains and the complete
fixed/liquid substat-roll vector used by `substatOptim`.

### 2.4 Artifact eligibility

Default eligibility is valid five-star artifacts. Account four-star artifacts
require an explicit set/ID override represented by the typed request.
Theoretical search is five-star only.

Malformed rows, missing mains, and unsupported set mappings remove only the
affected row/package when safe. They do not poison unrelated legal builds.

## 3. Input and mutation boundaries

### Account truth

Account search freezes all relevant `artifacts` and `artifact_substats` rows in
one read-only input at run start. Row provenance is irrelevant to optimization;
equipment, owner, location, lock, and preset state do not filter candidates.

`artifact_database_input_sha256` identifies those frozen DB contents for
request/cache/provenance integrity.

### Prepared config

The source config supplies the already selected team, weapons, talents,
constellations, options, rotation, and explicit target/scenario. For every
candidate the optimizer replaces only optimizer-owned set/stat rows.

Response probes, source-control simulation, candidate races, and final
validation use the exact same target:

- a chamber launch uses that selected chamber/scenario;
- an explicit DPS Dummy launch uses that dummy;
- no explicit target is `NOT_READY`;
- there is no hidden static-target fallback.

Finite-target comparisons keep duration/clear evidence together with DPS and
total damage. Duration/dummy targets use expected DPS as their direct objective.

### Read-only search

Search never equips artifacts, changes current equipment, edits presets, or
writes History. Persistence happens only through an explicit save action after a
saveable result exists.

## 4. Contracts, identities, and source map

Product requests remain schema v4 in `optimizer_product_contracts.py`.
Response/result/progress/work-plan subcontracts and caches have independent
versions. Product result schema v3 includes typed theoretical allocation
evidence; progress schema v3 distinguishes provisional stage leaders from
verified and final leaders and includes their actual iteration count.
Current primary work-plan identities are:

- selected account: `anytime_approx_v2`;
- all-account: `all_database_sets_anytime_approx_v3`;
- theoretical 4p: `theoretical_4p_anytime_approx_v2`;
- theoretical 2p+2p: `theoretical_2p2p_anytime_approx_v2`.

Use the constants in their owning modules as the exact plan-version authority;
never copy cached evidence across a version change.

| Concern | Module |
| --- | --- |
| Product requests/results/progress | `optimizer_product_contracts.py` |
| Trusted engine/catalog binding | `optimizer_engine_context.py` |
| Prepared config shell | `optimizer_config_shell.py` |
| Complete read-only DB input | `optimizer_artifact_database.py` |
| Immutable account run input | `optimizer_run_input.py` |
| Generic stat floors | `optimizer_stat_constraints.py` |
| Exact artifact/set/stat rendering | `optimizer_artifact_materializer.py` |
| Paired stat response | `optimizer_stat_response.py` |
| Response/profile adapter | `optimizer_anytime_response.py` |
| Paired set-impact | `optimizer_set_impact.py` |
| Package feasibility | `optimizer_package_feasibility.py` |
| Selected-account orchestration | `optimizer_anytime_selected_service.py` |
| All-account orchestration | `optimizer_all_set_service.py` |
| Theoretical candidates/race/service | `optimizer_theoretical_anytime_candidates.py`, `optimizer_theoretical_anytime_race.py`, `optimizer_theoretical_anytime_service.py` |
| Readable theoretical allocation evidence | `optimizer_theoretical_allocation.py` |
| Cache | `optimizer_cache.py` |
| Explicit save | `optimizer_save.py` |

A request binds the ordered four wearers, prepared config, explicit
target/scenario, energy mode, engine/catalog, work plan, material budgets,
package policy, stat floors, and account DB identity where applicable.

Cache identity includes every value that can change simulation meaning,
including full ordered package/layout state, intervention and seed panel,
compiled config, execution fidelity, and exact physical IDs for account work.

## 5. Paired stat-response v2

The active response path uses the patched engine capability
`gtt_stat_response_v2`. It:

- parses the frozen config/rotation/target once;
- runs baseline and interventions on the same deterministic seed panel;
- uses expected-damage collection to remove ordinary crit-multiplier luck;
- returns team expected DPS and the ordered four-character DPS vector;
- returns paired deltas and uncertainty inputs;
- preserves partial typed evidence on local timeout/cancellation;
- fails the owning operation on contract or wiring failure.

The response result is evidence for this rotation and context, not a universal
artifact score.

### Anchors and interventions

The implementation uses a sparse diagnostic anchor and a realistic balanced
anchor. Large synthetic additions prove that a dependency can exist; they do
not become artifact weights. Comparative values use attainable marginal changes
and legal whole-main layouts.

Every wearer is probed separately so indirect effects are visible in both team
and per-character deltas. Non-additive all-wearer results may trigger bounded
interaction probes. Failed/noisy evidence is `uncertain`, never fabricated
zero.

Axes are classified as:

- `dominant`;
- `secondary`;
- `negligible`;
- `uncertain`.

Only paired negligible evidence with a safe upper bound can remove a branch.

### Legal main stats

Main-stat probes use actual level-20 five-star values:

| Slot | Legal values |
| --- | --- |
| Sands | HP/ATK 46.6%, DEF 58.3%, EM 186.5, ER 51.8% |
| Goblet | HP/ATK 46.6%, DEF 58.3%, EM 186.5, elemental DMG 46.6%, Physical DMG 58.3% |
| Circlet | HP/ATK 46.6%, DEF 58.3%, EM 186.5, Crit Rate 31.1%, Crit DMG 62.2%, Healing Bonus 35.9% |

Changing a main replaces the old coordinate; it does not stack another main on
top. Complete sands/goblet/circlet layouts retain one equal attainable substat
budget.

### Crit and low-personal-damage supports

Expected damage removes ordinary crit roll noise. A capped Crit Rate probe is an
upper-bound relevance check, not a real CR weight. Set-provided conditional crit
remains active at its engine-modeled uptime.

If crit can only improve a support's tiny personal contribution below the
practical full-team threshold, the result may describe an equivalence family
such as `any HP%` or `any EM + useful HP% substats`. This requires positive
evidence for the named axis and a bounded team-loss proof.

During broad package search, one best legal representative per such equivalence
family/package is enough. Physical replacements are expanded only when the
package changes, becomes a finalist, or no-reuse requires an alternative.

### ER policy

Energy sufficiency is never inferred or automatically balanced. Account ER is
the same generic pre-simulation rule as any other floor:

> final artifact contribution for stat X must be at least Y

Builds below an explicit floor are rejected before GCSIM. Surplus ER receives no
generic energy-availability reward. Direct ER-to-damage conversion modeled by a
character or set remains ordinary damage scaling and may be measured.

Theoretical search has no implicit ER floor and does not optimize ER
availability. Infinite/boosted energy is a separate explicit simulation choice.

## 6. Paired set-impact

Broad set search uses the engine capability `gtt_set_response_v1`. Capability
presence is authoritative; the cumulative `gtt_patch_version` marker is
diagnostic and may advance as newer patches include the same capability.

`optimizer_set_impact.py` strips all character set rows, keeps one synthetic
stat baseline fixed, adds exactly one candidate package to one wearer, and
measures paired personal/team/ordered-character deltas on the exact selected
target and common seeds.

Two panels are mandatory:

1. `balanced` uses the balanced synthetic response anchor;
2. `crit_headroom` repeats the package probe without inherited synthetic CR, so
   crit-granting sets cannot be discarded only because the balanced panel was
   already at or near the crit cap.

Each `(wearer, package)` is classified as:

- `personal_positive`;
- `team_positive`;
- `personal_and_team_positive`;
- `uncertain_retained`;
- `negligible`.

Only `negligible` is removable. Missing, noisy, interrupted, or unresolved
evidence is retained conservatively. A non-negative package surrogate is
derived from the confidence-adjusted personal/team gain and guides proposal
ordering; it is not displayed as simulated DPS and does not replace exact
GCSIM validation.

Selected-set pools are user-mandated and are not removed by this broad screen.
All-account enables it for feasible database packages. The theoretical
corrective package path is integrating the same evidence while preserving equal
investment and inventory independence.

## 7. Account candidate algorithms

### Selected packages

1. Freeze the complete DB input and selected package targets.
2. Exclude invalid/ineligible rows fail-closed.
3. Build one dense slot/set/stat catalog with integer artifact bit masks.
4. Deduplicate content-identical rows for ranking with
   `content_fingerprint`, retaining bounded physical replacements.
5. Build the paired-response profile from the selected representative context;
   preserve every user-selected package through candidate coverage.
6. Preserve Pareto, threshold, crit-shape, reaction, equivalence, and
   conflict-shadow representatives.
7. Build complete five-slot wearer candidates and apply stat floors.
8. combine four wearers with global artifact-ID no-reuse;
9. race exact compiled configs through common fidelity.

### All-account packages

1. Derive trusted physically feasible 4p and requested 2p+2p targets from the
   complete DB.
2. Record inventory-infeasible packages instead of pretending they were tested.
3. Run a neutral-set paired stat response at no fewer than 32 iterations; use
   it only for soft ranking, never hard main-stat deletion.
4. Run paired set-impact for every feasible `(wearer, package)`.
5. Remove only proved-negligible packages; retain uncertain ones and any
   resolvable source-package control anchor.
6. Feed the set-impact surrogate into package/candidate proposal ordering.
7. Guarantee retained package coverage before artifact-level variants consume
   the bounded proposal budget.
   If several strongest-fixed obligations compile to the same exact team config,
   they share one simulation and the proposal retains every obligation label;
   duplicate scheduler identities are never emitted.
8. Search physically feasible ordered team package combinations with global
   no-reuse.
9. Locally regenerate mixed legal main-stat and physical candidates inside up
   to eight package signatures, with up to twelve joint proposals per
   signature, then run the exact multifidelity race.

The untouched source config may be simulated on the same target as control
evidence. It is never an early-stop threshold, package priority, pruning
authority, or substitute for all-set exploration.

Account artifacts always use their stored level, main value, and substats.
Canonical +20 mains are response/theoretical calibration only.

### Content fingerprint limitation

`content_fingerprint` contains normalized slot, set, rarity, level, main, and
substats. Equal-content rows may collapse during ranking while bounded physical
alternatives remain for no-reuse and saving. This accepted limitation is
source-independent and not a blocker.

## 8. Theoretical candidate algorithm

The required corrective contract is:

1. derive all trusted optimizer-ready five-star 4p packages, or canonical
   distinct 2p signature pairs;
2. run paired set-impact coverage before package proposal truncation;
3. for 2p+2p, shortlist components through single-2p impact evidence and retain
   engine-proved equivalent concrete identities;
4. enumerate legal whole-main layouts under one equal investment budget;
5. impact-shortlist an over-wide retained domain to at most 30 quick anchors
   per wearer while recording every retained-but-unscreened package;
6. give every quick anchor a balanced complete-main witness, then allocate
   further complete layouts package-round-robin rather than global-score-first;
7. construct bounded full-team package/layout proposals using set-impact,
   response, interaction, and diversity evidence;
8. retain positive and uncertain package evidence conservatively;
9. run exact ordinary screening, one finalist `substatOptim` allocation, and
   exact validation.

The corrective proposal/search path is covered by focused package-survival,
wide-domain, mixed-layout, and package-signature regressions. Earlier real
DPS-Dummy smokes proved both engine paths execute through `BEST_FOUND`; their
numeric outputs belong to superseded planning identities and must be rerun
before they are used as calibration evidence.

## 9. Multifidelity evaluation

Current internal phases are:

- account: up to 64 at 8 iterations, 16 at 32, 6 at 200, then at most 3
  statistically overlapping leaders at 1000;
- theoretical: 64 at 8, 16 at 32, at most 6 finalists through one
  `substatOptim` pass, validation at 200, and at most 3 close leaders at 1000;
- `substatOptim` is never rerun during the 1000-iteration rerace.

Only 200/1000-iteration exact evidence may enter terminal top-N or save.
Lower-fidelity leaders are provisional progress only. Starting a new fidelity
stage clears the previous stage's leader; UI text reports `n`, labels 8/32 as
provisional, 200+ as verified, completion as final, and displays uncertainty as
standard error (`SE`) rather than an unexplained `+/-` value.

## 10. Package-signature top-N

Top-N is diverse by the full ordered team package signature, not by tiny
physical artifact differences.

For each ordered wearer, the signature contains:

- package kind (`4p` or `2p+2p`);
- canonical GCSIM set key for 4p;
- canonical sorted pair of set keys for 2p+2p.

Validated rows are grouped by this four-wearer signature. Only the best exact
candidate from each group occupies a top-N row. A second artifact allocation
under the identical team package combination is replacement evidence, not
another rank. It may become a separate top row only when at least one wearer's
package changes.

This rule applies to selected-account, all-account, and theoretical results.
The saved candidate remains the exact physical winner for that row where
physical artifacts exist.

## 11. Errors, progress, and resources

Terminal status is fail-closed:

- `BEST_FOUND`: at least one saveable exact candidate;
- `NO_SUCCESS`: no saveable candidate in the frozen domain;
- `NOT_READY`: prerequisite or domain failure;
- `CANCELLED`: explicit cancellation;
- `DEADLINE`: no saveable evidence before the global deadline;
- `FAILED`: contract, wiring, materialization, or unexpected execution error.

Progress stages include:

- preflight;
- layout/index scan;
- stat-response scan;
- set-impact scan;
- candidate generation;
- joint package/no-reuse search;
- screening;
- refinement;
- final validation;
- rerace;
- completion.

The active engine must advertise each required capability. Wave-scenario
preflight treats `gtt_wave_scenario_payload` as authoritative and accepts newer
cumulative patch markers. Set-impact requires `gtt_set_response_v1`.

CPU-aware callers keep total live GCSIM workers within the frozen CPU budget.
Cancellation propagates to the active response, set-impact, race, optimizer, or
rerace owner.

Generated runs are diagnostics:

- successful default ordinary screens remove their run directory after summary
  extraction;
- failed/cancelled runs may remain for diagnosis;
- two-stage runs remove their reproducible private executable copy;
- `python -m run_workspace.gcsim.cleanup` bounds `runs`, `farming-runs`, and
  `optimizer-runs` independently;
- `data/cache/gcsim_optimizer` is reusable content-addressed evidence, not a
  temporary run directory, but it is still retention-bounded automatically to
  20,000 JSON entries and 256 MiB; the full scan is throttled to once per five
  minutes and stale atomic `.tmp` files older than one hour are removed;
- the same cache policy is available through
  `python -m run_workspace.gcsim.cleanup`, including dry-run reporting.

## 12. Result and save boundary

Account results contain absolute exact estimates and exact four-wearer
assignments. Theoretical results additionally contain percent-to-best and a
versioned readable allocation witness: exact package, sands/goblet/circlet
mains, all ten fixed/liquid roll coordinates, and the originating optimized
GCSIM stat rows. Source-control comparison is informational and cannot suppress
the best result inside the requested domain.

Nothing is saved automatically. After a saveable result, the explicit save flow
may:

- save a wearer build as a normal character artifact preset;
- suggest `best_found_<other team members>` as its editable default name;
- reuse an already saved exact preset instead of duplicating it;
- save the four preset references as one GCSIM team optimizer result.

If the user does not save, the result is disposable. Atomic apply-all and a
dedicated linked-presets GCSIM tab remain later UI work.

## 13. Current release gates

Impact-driven package search, package-signature Top-N, real DPS-Dummy smokes,
and focused corrective regressions are complete. The latest correction adds:

- all-account soft neutral response, source-package recall coverage, and local
  physical regeneration instead of support/main-stat hard deletion;
- balanced per-package theoretical anchors, fair mixed-main witnesses, and a
  non-failing wide 2p+2p shortlist with explicit unscreened accounting;
- progress fidelity/leader semantics that cannot display an n=8 spike as the
  final winner;
- readable theoretical main-stat and roll allocations in the typed result and
  Browser panel.

These corrections have automated regression coverage. Previous diagnostic DPS
numbers from superseded work-plan identities are not release evidence for the
new plans and are intentionally not retained here.

Remaining before calling the optimizer release-usable:

1. rerun the reported Chasca/Ororon/Furina/Bennett selected/all-account and
   theoretical comparisons under the new plan identities, then compare more
   user-built teams and selected-chamber targets;
2. calibrate materiality/pruning budgets from those UI comparisons;
3. remeasure cold/warm runtime, cancellation, cache, memory, and long wide-pool
   behavior;
4. finish explicit save/preset UI validation without changing search semantics.

All-account remains an accepted but optional/experimental mode until its
quality and wide-pool runtime are acceptable. Do not add speed modes before the
corrected base algorithm is measured.

Confirmed later ideas remain:

- automatic discovery of public GCSIM rotations matching the selected team;
- a GCSIM tab linking four saved character presets;
- one explicit atomic apply-all action;
- a compact indication of near-equivalent physical replacements.
