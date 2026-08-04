# GCSIM Optimizer Technical Handoff

Last updated: 2026-08-02.

This is the authoritative backend contract for the GCSIM artifact optimizer.
It describes the current implementation and the remaining calibration/release
work. Historical milestone logs and superseded response experiments belong in
Git history, not in this file.

## 1. Current status

| Product operation | Backend | Status |
| --- | --- | --- |
| Account artifacts, selected set pools | `optimizer_anytime_selected_service.py` | Current UI baseline is selected plan 11; artifact-first replacement is shadow work |
| Account artifacts, all feasible database sets | `optimizer_account_superset.py` -> `optimizer_all_set_service.py` | Package-first fallback only; not release-ready and frozen against further expansion |
| Theoretical equal-investment 4p | `optimizer_theoretical_anytime_service.py` | Canonical equal-budget run and Chasca controls passed; wider-team calibration required |
| Theoretical equal-investment 2p+2p | `optimizer_theoretical_anytime_service.py` | Canonical equal-budget run passed; keep independent 2p+2p regression coverage |

Every result means:

> best build found under the frozen, versioned work plan

It is not a claim of an exhaustive mathematical optimum.

There are no accepted user-facing `Quick`, `Balanced`, or `Deep` speed modes.
Account `screen_8`; theoretical `package_screen_8`, `main_coordinate_8`, and
`main_combine_8`; shared `refine_32`, `validate_200`, and `rerace_1000` are
internal fidelity phases, not product modes.

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

The currently wired implementation is the package-first
`GcsimOptimizerAccountSupersetSession`. It runs selected-account first, requires
one confirmed physical winner, then injects that proposal into
`optimizer_all_set_service.py`. Both phases bind the same frozen source
simulation, prepared config, target, database, engine/catalog, package policy,
four-star overrides, and stat constraints. The UI audit proved this path is
really behind the existing all button; it did not prove its recall quality.

This implementation is now a frozen fallback/diagnostic, not the release
architecture. Do not add further package screens, signature-local repairs,
surrogate lanes, or post-race expansion to it. The replacement is the shared
artifact-first kernel in section 2.5.

For a 4p package, physical feasibility requires four distinct usable artifact
slots from that set; a raw count of four same-slot rows is insufficient. A
complete five-slot wearer build must also be possible. Joint team proposals are
rechecked against global artifact-ID no-reuse.

For reproducibility, the fallback's broad search is package-first after the
selected prepass:

1. measure the set effect for every feasible `(wearer, package)`;
2. retain positive and uncertain packages conservatively;
3. guarantee physical candidate coverage for retained packages;
4. search feasible ordered four-wearer package combinations;
5. run the ordinary exact race and take its confirmed package signatures in
   measured DPS order, never surrogate order;
6. regenerate structural-stat plus legal-main physical candidates inside up to
   eight confirmed signatures, with bounded CR/CD and other axis coverage;
7. run a second exact race containing the local proposals, every first-race
   confirmed proposal, the first-race winner, and the injected selected
   anchor. The winner and injected anchor are required through every tier.

These steps document the retained comparison path; they are not the design for
new account-search work. Artifact substats still must not decide which set bonus
is ever legal, but the new kernel derives the package only after completing a
physical assignment.

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

Crit Rate and Crit DMG circlets are a coupled theoretical direction: if either
crit direction is materially supported, both remain in the layout domain.
Mixed scaling/elemental/CR and scaling/elemental/CD witnesses are reserved
before score fill, so an all-EM surrogate cannot consume the layout cap. After
the first package screen, up to six leading ordered team-package signatures are
refined without changing any of their four package keys: every retained layout
is measured one wearer at a time, then a bounded beam combines the strongest
single-wearer changes. Only then is the best measured layout per package
signature promoted to 32 iterations and finalist `substatOptim`.

### 2.4 Artifact eligibility

Default eligibility is valid five-star artifacts. Account four-star artifacts
require an explicit set/ID override represented by the typed request.
Theoretical search is five-star only.

Malformed rows, missing mains, and unsupported set mappings remove only the
affected row/package when safe. They do not poison unrelated legal builds.

### 2.5 Account architecture transition: artifact-first target kernel

New account-search work targets one shared physical kernel. Its first primitives
currently run only in offline tests; parallel shadow execution is still pending,
and the selected plan-11 path remains the UI baseline. The stages are fixed in
this order:

1. **Response-aware inventory frontier.** Start from every eligible physical
   row. Keep slot/main/set identity, raw stats, response dimensions, stat-floor
   contribution, and physical conflict alternatives. Roll-normalized axes may
   make unlike stat units comparable inside a vector, but CV/RV or another
   scalar is soft ordering only.
2. **Per-slot injective team matching.** Construct four-wearer matchings for a
   single slot with no repeated `artifact_id`. Score and bound the team matching,
   not four independent wearer choices, so a piece that is second-best locally
   can survive when it unlocks the best injective allocation.
3. **Cross-slot beam with set counts.** Join those matchings across the five
   slots while carrying the global physical-ID mask, per-wearer set counters,
   main/stat totals, floor feasibility, and admissible response bounds. Retain
   conflict and set-completion alternatives explicitly.
4. **Derive package after assignment.** Only a complete legal physical
   assignment determines each wearer's 4p package (with zero or one off-piece)
   or 2p+2p package. Set effects and non-stacking team effects are then
   materialized from that actual state; package identity never partitions the
   first inventory layer. Rainbow and single-2p builds are outside the current
   product contract rather than being silently mislabeled as an off-piece mode.
5. **Exact evaluation and refinement.** Compile the exact physical assignment,
   run the common multifidelity GCSIM race, and perform bounded refinement while
   retaining the last confirmed witness through every later tier.

Selected/all differ only by domain constraints supplied to this kernel.
Selected limits allowed derived package identities; all permits every trusted
modeled physically feasible package. Candidate generation, injective matching,
beam state, materialization, race, and refinement are shared.

#### Advisory skyline measurement and hard-prune boundary

A raw first-layer skyline measurement on the current 520-piece database placed
519 pieces in the first layer when set identity was part of the comparison class
and 512 when set identity was ignored only for an off-piece-equivalent diagnostic.
This does **not** prove that the remaining rows are safe to remove from exact
GCSIM: a larger raw stat can change conditional rotation/weapon behaviour (ER
and `energy < max` is one concrete class). Inventory-frontier plan 2 therefore
retains every eligible row, records componentwise depth only as advisory
evidence, and shadows only rows that are ineligible for every wearer.

A future hard dominance proof must certify monotonicity for the frozen GCSIM
context, be no worse on every relevant response/stat/floor dimension, and
preserve slot legality, set-count futures, and injective/no-reuse
substitutability. Set-aware and off-piece-equivalent relations remain separate.
Anything weaker is a heuristic lane and cannot delete the only copy of a
physical witness.

#### Cutover gates

1. byte-identical frozen DB/config/target/energy/constraint identities between
   baseline and shadow runs;
2. pinned no-hard-prune behavior, advisory 520 -> 519/512 measurement, and
   randomized exhaustive skyline/matching counterexample tests;
3. end-to-end exact slot legality, globally injective physical IDs, set-count/package
   derivation, materialization, and stat-floor tests;
4. selected plan-11 physical witnesses remain reachable and shadow exact results
   are compared on the same compiled configs and confidence intervals;
5. every selected-domain witness remains in the all-domain search under the same
   downstream fidelity policy;
6. common race plan-6 deadline/cancellation tests preserve already confirmed
   saveable evidence;
7. unrelated team/rotation/target quality corpus plus cold/warm/cache/memory and
   wide-inventory runtime limits;
8. UI audit proves both account routes loaded the shared kernel and retained the frozen
   identities. Only then delete the package-first and old selected account paths.

#### Primary design references

These are design constraints and comparison points, not imported code:

- Genshin Optimizer uses multidimensional dominance/range pruning before exact
  formula evaluation rather than a single roll-score cutoff:
  [solver pruning](https://github.com/frzyc/genshin-optimizer/blob/master/libs/gi/solver/src/common.ts),
  [branch-and-bound worker](https://github.com/frzyc/genshin-optimizer/blob/master/libs/gi/solver/src/GOSolver/BNBSplitWorker/index.ts),
  [exact compute](https://github.com/frzyc/genshin-optimizer/blob/master/libs/gi/solver/src/GOSolver/ComputeWorker.ts).
- KQM defines RV as roll quality and explicitly treats useful-stat choice as
  character-dependent; CV/RV is not a team-DPS oracle:
  [KQM Artifact Guide](https://keqingmains.com/misc/artifacts/#roll-value-rv).
  Average roll units for controlled theory comparisons are documented by the
  [KQM Standard](https://compendium.keqingmains.com/).
- gcsim's substat optimizer fixes team/weapons/sets/main stats and describes its
  local method as not fully optimal, so it is an exact rotation-aware evaluator
  or refinement aid, not the physical assignment solver:
  [official guide](https://docs.gcsim.app/guides/substat_optimizer/),
  [source](https://github.com/genshinsim/gcsim/blob/main/pkg/optimization/substats.go).

### 2.6 Future accelerator: nonlinear response surfaces, not fixed weights

If the first artifact-first beam still spends too much budget on broad package
exploration, use the following as the next attempt. For one frozen team,
rotation, target, energy policy, engine, and plan, a legal physical assignment
`A` produces a feature state `phi(A)` containing all four wearers' total stats,
exact set counts/keys/parameters, and team-level set interactions. Exact GCSIM
is the context-specific function `F_context(phi(A))`.

Do **not** assign one permanent score to a stat or artifact. The useful value of
piece `a` is contextual:

`delta_a(A) = F_hat(phi(A + a)) - F_hat(phi(A))`

It changes near Crit Rate caps, ER/action thresholds, base-stat breakpoints,
reaction regions, and 2p/4p set-count jumps. The universal component is the
measurement/fit/search procedure; every frozen simulation learns its own
response surface.

`phi(A)` must not be reduced to four independent character stat vectors. It
also needs cross-wearer and temporal state: reaction ownership and elemental
application, HP-change/healing and Fanfare timelines, buff source and recipient,
the recipient's damage exposure while the buff is active, and target state.
Examples which must be represented or discovered by probes:

- EM on the character who actually owns Bloom/Hyperbloom/Burgeon depends on
  the application/trigger pattern created by the rest of the team;
- HP/healing changes on one or several characters can change Furina's Fanfare
  state and therefore every recipient's damage, rather than only the HP owner's
  personal curve;
- a numerically large team buff has little value when its eligible recipients
  contribute little affected damage, while the same buff can be dominant for a
  different damage distribution;
- elemental bonus or RES shred is valuable only against the matching
  recipient-element-target exposure during its actual uptime.

Therefore a per-stat "weight" is at most a local contextual marginal derivative
of the full multivariate surface. It is not an intrinsic property of the stat,
piece, set, or character, and independent per-character curves cannot simply be
summed without cross terms.

Critical anti-circularity boundary: most temporal features above are visible
only after running GCSIM. If every unseen assignment needs a simulation merely
to construct `phi(A)`, the surrogate provides no search acceleration. Keep two
explicit feature layers:

1. `x(A)`, cheap pre-simulation features computable for every physical
   assignment: wearer stats, set counts/keys, static typed effects and proved
   envelopes, frozen rotation/team/target descriptors, plus source-baseline
   exposure summaries;
2. `z(A)`, expensive runtime observations: reaction ownership, energy/action
   feasibility, HP/Fanfare and buff timelines, stack uptime, snapshot stats,
   target states, and affected damage exposure.

Train either a direct `F_hat(x)` with runtime observations as auxiliary labels,
or a state model `z_hat(x)` followed by `F_hat(x, z_hat(x))`. Never substitute
the source build's `z` as fact for a mechanically different candidate. Any
candidate predicted to change rotation feasibility, reaction ownership,
snapshot timing, or conditional-set activation enters a high-uncertainty exact
probe lane. This boundary is a release gate, not an implementation detail.

Recommended structured surrogate:

1. one-dimensional piecewise splines per wearer/stat to learn slopes, plateaus,
   and change points from several feasible working anchors;
2. sparse pair interactions for Crit Rate x Crit DMG, scaling stat x damage
   bonus/crit, EM x reaction contribution, ER x action/weapon state, and any
   other interaction detected by paired probes rather than character names;
3. categorical 2p/4p set features, set x stat surfaces, cross-wearer set factors,
   and explicit non-stacking team-effect features;
4. an uncertainty model so high-uncertainty, novel, package-diverse, and
   incumbent-neighborhood candidates receive exact probes.

Set effects need a typed semantic catalog:

- a proved unconditional static `AddStatMod` can enter the matching stat axis;
- a conditional numeric maximum (for example maximum stacks of Crit Rate or
  elemental damage bonus) may be an optimistic feature/upper envelope only;
- damage bonus, RES/DEF modification, reaction changes, team buffs, and
  non-stacking effects remain distinct feature axes rather than fake ATK/CR;
- procs, event subscriptions, action changes, parameterized effects, or any
  source pattern without a proof stay opaque and are learned through paired
  set-on/set-off GCSIM probes.

The surrogate set input must be a runtime effect tensor, not one scalar "set
weight". At minimum index every observed effect by source set, wearer,
recipient, stat/effect axis, element, attack tag or reaction where relevant,
and time/uptime. This matters for multi-element damage: a Scroll proc affecting
Hydro and Electro does not grant one generic damage bonus to every Chasca hit.
Its value is coupled to the rotation's per-character, per-element damage
exposure. The team objective may still sum character expected damage, but the
per-character response equations are coupled through these shared effects.

Combine effects by an engine-proved stack-group operator. Supported operators
should include additive, maximum, replacement/refresh, and independent. Scroll
uses same-name per-element modifiers, so duplicate Scroll sources replace or
refresh the same group rather than add another 12%; the 12% and conditional
28% components are separately timed. Do not assume `max` for every unknown
effect: record an unknown operator as opaque and send the combination to an
exact pair/full-team probe. A source-proved `max`/replacement envelope is safe
for proposal scoring; an invented one is not safe for hard pruning.

The current source-backed `artifact_set_catalog.py` proves registration,
rarity, 2p/4p implementation, parameters, and source identity; it does not
expose effect semantics. `optimizer_two_piece_signatures.py` intentionally
extracts only a narrow unconditional static 2p `AddStatMod` shape. Extend this
as an engine-versioned manifest with `effect_kind`, axis/element/attack/reaction,
magnitude or symbolic formula, recipient scope, trigger, duration/ICD/stacks,
and modifier/stack group. AST-proved cases may be generated; unknown cases stay
opaque and retained. Resolve concrete DB set UIDs through the engine's canonical
alias map rather than case-folded string equality.

The active `gtt_set_response_v1` intervention already accepts several set
changes in one request. Use pair/full-team probes for shared buffs, replacement
keys, RES shred, reaction effects, and set x set interactions. The current
`optimizer_set_impact.py` measures one wearer/package at a time against a team
with every set removed; that is insufficient as a future beam score. In
particular, Scroll on Furina can look positive in isolation while adding zero
same-key team bonus beside Scroll on Ororon. Pin a multi-Scroll non-stacking
interaction test before any set-feature shortlist becomes authoritative.

Current observability is not yet sufficient to decide conditional-set uptime
directly. `gtt_stat_response_v2` currently returns paired team and per-character
expected damage/DPS only. The active engine does already carry the relevant
data internally: every enemy-damage event has `AttackEvent.Snapshot.Stats`, the
normal damage aggregator groups DPS by character and element, and debug damage
calculation events expose effective CR/CD/EM, elemental/general damage bonus,
reaction terms, and resistance multiplier. Do not scrape free-form debug logs
as the production contract. Add a proposed engine-versioned
`gtt_effect_observation_v1` collector which aggregates, for the same aligned
seed panel:

- damage-event counts and expected damage by character, element, attack tag,
  source, reaction, and time bucket;
- damage-weighted snapshot-stat histograms/deltas, not only averages, so an
  Obsidian `+0.40 CR` state or Marechaussee `0/.12/.24/.36 CR` stacks are visible;
- effective target RES/DEF/reaction multipliers at damage time;
- set activation, stack, refresh, replacement, and active-frame evidence keyed
  by the canonical modifier/stack group.

For a conditional set, compare set-off and set-on observations. A positive
snapshot delta with non-zero damage exposure proves that the bonus affected the
rotation; an activation event with no later affected hit has zero direct value
for that interval. Classify the result as `active_static`,
`active_conditional`, `interaction_only`, `inactive_proved`, or `uncertain`.
Only an engine/source proof that the trigger is unreachable in the frozen
context may hard-remove a set. Merely observing no proc in a small noisy panel
may demote it, but must not delete it.

Ignoring an activation condition is safe only when the resulting value is a
proved admissible upper bound used to retain candidates. It is not a final
score and cannot justify hard deletion. Existing source parsing proves only a
narrow subset of static 2p modifiers; the general fallback is the engine-bound
paired set-response API.

Sampling should use deterministic feasible maximin/D-optimal panels followed by
active batches over predicted mean, uncertainty, novelty, package diversity,
and incumbent neighborhoods. Keep common random seeds and the existing
`n=8 -> 32 -> 200 -> 1000` exact race. Fit only on legal materialized states;
the confirmed incumbent always comes from exact GCSIM.

For theory, allocate discrete legal roll units with DP/CP-SAT/MIQP over this
surface, then exact-check finalists. For account artifacts, the same surface
makes scoring cheap, but injective slot matching, physical-ID no-reuse, 4-star
conditional admission, set thresholds, and stat floors remain a discrete
solver problem. Encoding set-count jumps in one solver means 2p+2p need not
have a separate search algorithm, but it still must be an allowed domain and
must receive exact validation.

The theoretical equal-investment constraint is a budget over discrete legal
roll units (and separately fixed main-stat/set structure), not a sum of raw
percentage points across unlike stats. For account search each physical piece
contributes its fixed feature vector and cost is implicit in selecting exactly
one legal piece per slot. There is no need to fit a new equation for every
five-piece combination: one frozen-context response surface evaluates all
reachable feature vectors, while the constrained solver supplies the physical
combinations nearest its optima.

A cheap GPT running for a day is not the numeric optimizer: it has no calibrated
uncertainty, deterministic replay, or trustworthy mechanics model. It may help
inspect traces and propose adversarial tests. Spend the simulation budget on
seeded GCSIM design-of-experiments plus a structured active/Bayesian optimizer.
Claims remain `best found under the frozen plan`; global optimality still needs
exhaustive search or a genuinely admissible bound.

Known limits and failure modes of this approach:

- this is a noisy mixed-integer nonlinear black-box optimization problem, not a
  closed-form linear equation system; physical assignment/set thresholds are
  discrete while DPS response is nonlinear and sometimes discontinuous;
- exact global account optimization is combinatorial and can still require
  exponential work. The surrogate/beam/solver reduces the exact-search domain;
  it does not mathematically remove brute force or prove the unseen optimum;
- cross-wearer, timing, reaction-ownership, and high-order interactions create
  a curse of dimensionality. Sparse pair terms can miss a rare three-or-more-
  factor interaction;
- equal aggregate stats need not be equivalent when buff uptime, snapshotting,
  reaction ownership, target phases, or action availability differ. Runtime
  features and exact finalists are required to avoid this feature aliasing;
- adaptive simulation is noisy. A low-iteration winner, an unobserved rare
  proc, or a falsely confident extrapolation can hide the true basin;
- synthetic stat probes can be physically unreachable, and a model trained in
  one team/rotation/target/engine context is invalid after that context changes;
- attribution is ambiguous when several buffs change together. Use controlled
  set-on/off, pair/full-team interventions and aligned seeds, while retaining an
  `uncertain` lane rather than inventing causal credit;
- no candidate may be hard-pruned from surrogate score alone. Preserve diverse
  package basins, exact anchors, uncertainty exploration, and a reduced-domain
  exhaustive oracle measuring recall/regret before UI cutover.

The authoritative objective is mean expected team DPS for the exact frozen
input and exact written rotation. The optimizer never edits, repairs, or
re-optimizes that action list. Rotation conditions and set triggers execute as
modeled by GCSIM; effect observation records which advertised stats/effects were
actually present on affected events, while exact DPS remains the final score.
Clear time, variance/consistency, healing, shielding, survivability, and
multi-scenario robustness are outside this optimizer stage.

The default search policy is `ignore_burst_energy=true`. Normal-energy demand is
not estimated by the optimizer. The only optional energy constraint is an
explicit user-provided per-character minimum on the relevant stat (currently a
generic `stat >= X` floor, including ER when selected). A user may omit those
floors and search without energy constraints. Do not reopen automatic ER
balancing or a second implicit normal-energy objective.

Acceptance/release gates are product-specific:

1. For a selected-set account request, the returned physical artifact IDs must
   match the accepted human/control assignment or produce no lower paired mean
   DPS under the same frozen input. Matching IDs count as artifact-search
   success even when an independently sampled mean is slightly lower from
   simulation noise.
2. The all-set domain contains the selected domain. The exact selected winner is
   a mandatory control candidate under identical downstream fidelity/seeds, so
   all-set top 1 cannot be lower than selected-set top 1 except a reported
   statistical tie/failure. Every displayed all-set row must be the best exact
   candidate found for its displayed ordered package signature, with signature
   diversity rather than several unlabelled random variants.
3. Proposal quality must be attributable to the original nonlinear stat/set
   model and fixed search plan. Persist the pre-simulation feature score/rank,
   proposal lane, package signature, and exact-evaluation/refinement budget.
   Apply the same bounded refinement policy prospectively; do not discover a
   displayed signature, then secretly launch an exceptional long signature-only
   search to manufacture its artifacts. Signature-only exhaustive/local search
   may be an offline diagnostic oracle, but its result must not be relabelled as
   the original production proposal.
4. The theoretical equal-investment operation uses the same learned response
   surface and set semantics; only the feasible domain changes from physical
   account pieces to a fixed legal roll/main-stat budget. Validate it against
   reduced exhaustive theoretical oracles and the same interaction traps.
5. Also require recall@K/regret on reduced exhaustive inventories, uncertainty
   coverage/calibration, monotonic preservation of the exact incumbent,
   deterministic replay, and a pinned maximum simulations/runtime budget.

The mandatory selected control is a product safety net, not evidence that the
nonlinear proposal model works. Add a separate anchor-ablation quality gate:
remove source/selected artifact-ID and package-score anchors from proposal
generation, keep only the requested domain and frozen context, and require the
model-driven search to rediscover a statistically/operationally equivalent
basin. For every retained top package signature, compare its all-set physical
assignment against a deep signature-restricted diagnostic reference and report

`regret = (reference_mean_dps - proposed_mean_dps) / reference_mean_dps`.

The materiality epsilon is not known before the first implementation evidence.
Use an explicitly labelled calibration corpus first to measure paired simulation
noise, the DPS spread among physically/statistically equivalent assignments,
and the quality/runtime frontier. Derive and document the candidate epsilon from
that evidence. Then freeze it before running a separate held-out validation
corpus and do not tune it on validation failures. Pass when paired exact held-out
evidence places regret below that frozen epsilon after accounting for simulation
SE. Exact IDs need not match when several pieces produce equivalent total
features/DPS. This diagnostic reference must remain outside production proposal
generation; otherwise it would conceal poor global ranking rather than validate
it. Record both anchored safety quality and anchorless model quality in the
audit.

Candidate generation should mirror the intended human reasoning without
collapsing it to one scalar piece list: measure local/contextual stat utility,
branch on plausible main-stat/set basins and uncertain tradeoffs, retain several
complementary high-score physical choices needed for set completion and global
no-reuse, then score complete team assignments. A piece that is individually
top-ranked is not automatically part of the best team assignment; complement,
threshold, and contention effects belong in the branch state.

There is one unavoidable claim boundary: without exhaustive enumeration or a
genuinely admissible upper bound, nonlinear weights/surrogates cannot prove that
an unseen physical assignment is not better, either globally or within one
package signature. They can satisfy the gates empirically and make misses
auditable, but the honest production claim remains `best found`. The all >=
selected guarantee is stronger because it is enforced constructively by domain
inclusion and the mandatory exact selected control, not inferred from the
surrogate.

The practical target is therefore not formal global proof. It is anchorless
near-oracle adequacy: across the selected-set controls, reduced exhaustive
inventories, and signature-restricted diagnostics, the model-driven branches
consistently land within the declared materiality epsilon while using far less
than full enumeration. Failure because the proposal began with plainly inferior
base pieces or an irrelevant package is a release-blocking model/search failure,
not acceptable approximation noise.

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
| Current fallback selected-to-all workflow | `optimizer_account_superset.py` |
| Current fallback broad all-account primitive | `optimizer_all_set_service.py` |
| Theoretical candidates/race/exact layout screen/service | `optimizer_theoretical_anytime_candidates.py`, `optimizer_theoretical_anytime_race.py`, `optimizer_theoretical_layout_screen.py`, `optimizer_theoretical_anytime_service.py` |
| Readable theoretical allocation evidence | `optimizer_theoretical_allocation.py` |
| Full account/theoretical benchmark traces | `optimizer_benchmark.py`, `tools/experiments/gcsim_optimizer_*benchmark.py`, `tools/experiments/gcsim_optimizer_chasca_controlled_ab.py` |
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

The crit-headroom panel preserves the same abstract roll budget. CR removed
from the synthetic baseline is redistributed across the other measured legal
roll axes; it is not deleted. This makes the two package panels equal-investment
controls rather than comparisons between a full baseline and a weaker one.

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
All-account enables it for feasible database packages. The theoretical package
path uses the same evidence while preserving equal investment and inventory
independence.

## 7. Account candidate algorithms

This section records the currently wired plan-11/package-first implementation
for reproducibility. It is not the target for new account-search work; the
artifact-first shadow contract and deletion gates are in section 2.5.

### Selected packages

1. Freeze the complete DB input and selected package targets.
2. Exclude invalid/ineligible rows fail-closed.
3. Build one dense slot/set/stat catalog with integer artifact bit masks.
4. Deduplicate content-identical rows for ranking with
   `content_fingerprint`, retaining bounded physical replacements.
5. Build paired-response profiles from the selected representative context and
   preserve every user-selected package through candidate coverage. Keep that
   response-ranked family as the exploitation head, but always add bounded
   structural directions for every supported raw substat axis and every legal
   main axis. Uncertainty profiles remain supplemental evidence; their noisy
   low-iteration classifications no longer decide whether a physical direction
   exists at all.
6. Preserve Pareto, threshold, crit-shape, reaction, equivalence, and
   conflict-shadow piece representatives. Partial and complete wearer beams use
   a hybrid cap: a strong score head plus bounded profile-normalized,
   variable-main, off-piece, and conflict-shape witnesses. A pure global score
   cap loses valid lower-surrogate layouts; a rigid one-row-per-profile quota
   loses stronger builds. Neither is the selected-path policy.
7. Build complete five-slot wearer candidates and apply stat floors.
8. combine four wearers with global artifact-ID no-reuse;
9. race exact compiled configs through common fidelity;
10. merge the response head and structural exploration lanes fairly instead of
    letting the first profile consume the cap, then run bounded exact GCSIM
    coordinate refinement around the confirmed seed. Its screen keeps both a
    surrogate head and fair depth by wearer slot/structural feature. Preserve
    the prior winner as a required proposal in every subsequent 8/32/200/1000
    tier, so local search cannot regress the already proved result.

### All-account packages

1. Run selected-account first on the same frozen request conditions and require
   one confirmed exact physical winner. Rebind it into all-account as an exact
   mandatory proposal; a product caller cannot skip this phase.
2. Derive trusted physically feasible 4p and requested 2p+2p targets from the
   complete DB.
3. Record inventory-infeasible packages instead of pretending they were tested.
4. Run a neutral-set paired stat response at no fewer than 32 iterations; use
   it only for soft ranking, never hard main-stat deletion.
5. Run paired set-impact for every feasible `(wearer, package)`.
6. Remove only proved-negligible packages; retain uncertain ones, any resolvable
   source-package control anchor, and every explicitly injected account winner.
7. Feed the set-impact surrogate into package/candidate proposal ordering.
8. Guarantee retained package coverage before artifact-level variants consume
   the bounded proposal budget.
   If several strongest-fixed obligations compile to the same exact team config,
   they share one simulation and the proposal retains every obligation label;
   duplicate scheduler identities are never emitted.
9. Search physically feasible ordered team package combinations with global
   no-reuse.
10. Run the first exact multifidelity race. From its confirmed evaluations in
    DPS order, locally regenerate mixed structural-stat, legal-main, and
    physical candidates inside up to eight package signatures, with up to
    twelve joint proposals per signature.
11. Run a second exact race over those local proposals plus every first-race
    confirmed proposal. The first-race winner and all injected anchors are
    mandatory at 8/32/200/1000. The all-account terminal winner therefore
    cannot regress below the strict-subset witness, and CR/CD branches compete
    only after their package signature has exact GCSIM evidence.

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
   response, interaction, and diversity evidence. Before broad catalog audit
   rows can fill the 64-slot screen, reserve the measured base, up to six
   single-wearer package swaps per wearer, and eight promising multi-wearer
   package combinations;
8. package-screen 64 proposals at 8 iterations and select up to six leading
   ordered package signatures;
9. inside each selected signature, freeze all four package keys, compare every
   retained main layout one wearer at a time under the same cheap investment,
   then combine the strongest per-wearer changes in a bounded beam;
10. run the cheap 32-iteration race screen, but do not treat its synthetic
substat profile as final main-stat evidence;
11. for at most six package signatures, retain at most six physically distinct
    main layouts each (race winner, coordinate winner, single-wearer changes,
    then bounded combinations), run real `substatOptim` at 32 iterations for
    each, and keep exactly one optimized layout per signature;
12. validate those at 200 iterations and rerace only statistically overlapping
    leaders at 1000.

Response gradients used for theoretical liquid-roll allocation are normalized
by the legal roll value of their axis before they become roll shares. Equal DPS
gain from one CR roll and one CD roll therefore receives equal budget weight;
the smaller numeric CR roll is not accidentally awarded roughly twice as many
rolls. The inner optimizer still enforces its own legal integer budget and crit
cap.

The corrective proposal/search path is covered by focused package-survival,
wide-domain, mixed-layout, and package-signature regressions. Earlier real
DPS-Dummy smokes proved both engine paths execute through `BEST_FOUND`; their
numeric outputs belong to superseded planning identities and must be rerun
before they are used as calibration evidence.

## 9. Multifidelity evaluation

Current wired/fallback internal phases are:

- account races use nominal caps of 64 at 8 iterations, 16 at 32, 8 at 200,
  and at most 3 statistically overlapping leaders at 1000. Required marginal
  package coverage, selected-account coordinate refinement, and all-account
  confirmed-signature structural/main refinement may expand their own
  8-iteration screen to their bounded proposal batch; every later tier remains
  capped at 16/8/3;
- all-account first shortlists exact package signatures, then runs one second
  race over confirmed-signature structural/main proposals plus every preserved
  first-race witness and required anchor;
- theoretical: 64 package proposals at 8; then up to 384 same-signature
  one-wearer main/profile probes and up to 384 bounded combination probes at 8;
  at most 16 cheap race rows at 32; then at most 6 package signatures by at most
  6 physical layouts through optimizer-backed 32-iteration layout screening;
  exactly one winner per signature proceeds to the at-most-6 validation pass at
  200, and at most 3 close leaders rerace at 1000;
- `substatOptim` is never rerun during the 1000-iteration rerace.

Only 200/1000-iteration exact evidence may enter terminal top-N or save.
Lower-fidelity leaders are provisional progress only. Starting a new fidelity
stage clears the previous stage's leader; UI text reports `n`, labels 8/32 as
provisional, 200+ as verified, completion as final, and displays uncertainty as
standard error (`SE`) rather than an unexplained `+/-` value.

The shared account race identity is plan 6. If a scheduler batch ends by
deadline/cancellation, terminal status is processed before required-row checks;
successful evidence already obtained at 200/1000 remains the last confirmed top
instead of being erased because another required row was terminally skipped.

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
- `DEADLINE`: the global deadline ended the current tier. Under common race
  plan 6, any successful evidence already validated at the minimum saveable
  fidelity remains available as the last confirmed top; without such evidence
  the result has no saveable top;
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
- after every completed UI optimizer operation, a best-effort narrow hook
  applies those same run/cache retention limits. It does not touch the engine
  store or Go build cache, and cleanup failure cannot replace the optimizer
  result or error;
- every completed account UI operation writes one bounded immutable audit and
  updates `debug/gcsim_optimizer_ui_runs/latest.json`. The audit binds the typed
  launch request, prepared/source/config/target/database/run-input identities,
  loaded module paths and hashes, selected/all phase order and plan versions,
  confirmed race rows, compiled configs, and exact artifact IDs. Use this file,
  not cache modification time alone, to compare a desktop click with a
  benchmark run;
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

## 13. Current evidence and release gate

The current selected comparator is one frozen UI-entrypoint request under
selected plan 11 and pre-deadline-fix race plan 5. It produced
`139577.8505 ± 292.4415` DPS at `n=1000` in `628.297 s`. The request used the
398-byte two-wave `group_clear` target with SHA-256
`d62cacc31240b756a33595cd38303817e9fb7aaf8bc601bba2255c54b616170c`
and effective `ignore_burst_energy=true`. It is not normal-energy evidence.

Authoritative files for that comparator are:

- UI audit:
  `debug/gcsim_optimizer_ui_runs/20260802T091044477190Z-16092-0c9db722f11c.json`;
- mirrored audit:
  `debug/gcsim_optimizer_benchmarks/ui-production-v11-selected/canonical-ui-selected-audit.json`;
- typed result and full trace:
  `debug/gcsim_optimizer_benchmarks/ui-production-v11-selected/canonical-ui-selected-result.json`.

The common account race is now plan 6. Its deadline/cancellation semantics are a
correctness fix: terminal batch status is resolved before required-proposal
success is enforced, and successful saveable validation already obtained in the
tier remains the confirmed top. The comparator above may seed shadow regression
tests, but a result claimed under the current race identity requires a plan-6
run/cache identity.

Release state:

| Path | State | Release meaning |
| --- | --- | --- |
| Selected plan 11 + race plan 6 | Current UI path | Temporary baseline while the artifact-first kernel is built; remeasure when current-plan evidence is needed |
| Package-first selected-to-all | Frozen fallback | Diagnostic comparison only; not release-ready and receives no more architecture work |
| Artifact-first shared selected/all kernel | Offline primitives; shadow execution pending | Must pass every cutover gate in section 2.5 before either account route switches |
| Theoretical 4p / 2p+2p | Separate implemented operations | Not part of the physical account-kernel migration |

Do not publish an all-account quality claim from the package-first fallback.
Do not delete or bypass the existing UI paths early: first run byte-identical
shadow comparisons, retain exact configs/physical IDs/confidence intervals, and
prove through the immutable UI audit that both account routes loaded the shared kernel.
After the cutover gates pass, delete the old selected and package-first account
paths rather than maintaining two algorithms indefinitely.

Every counterexample must retain its frozen input and identify the first
frontier/matching/beam/materialization/race stage that lost the witness. The
canonical team is a regression input, not a gameplay golden; never encode its
character names, sets, mains, or preferred stats into the kernel. Calibrate
budgets and explicit save/preset UI only after correctness, cancellation/
deadline behavior, and wide-inventory runtime are accepted. Do not add speed
modes before the shared base algorithm is trusted.
