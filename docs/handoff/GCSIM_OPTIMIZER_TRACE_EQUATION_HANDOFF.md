# GCSIM Artifact Optimizer - Current Trace-Equation Contract

Status: authoritative, compacted 2026-08-27.

This is the sole active optimizer handoff. It describes the current product
decision and the next implementation stages. It intentionally does not preserve
the chronological V1-V6 development diary.

## Superseded context

The following are forensic history only and must not define new work:

- M1-M8, S0-S7 and Gate 0-4 milestone plans;
- the removed Selected V2 package and its synthetic evidence protocol;
- stat-map-first, response-surface and black-box perturbation search;
- historical Current/New/Archive DPS values from different frozen contexts;
- old detailed per-candidate formula traversal as a production evaluator;
- dated trace-schema checkpoints and old "next blocker" descriptions.

Machine identities and old patch receipts may remain in
`GCSIM_OPTIMIZER_TRACE_EQUATION_CLEANUP_MANIFEST.json`. They are evidence, not a
task queue, candidate source, fallback backend or product default.

There is no legacy optimizer fallback. Reusable database, materialization,
legality, engine transport, cancellation and cache primitives may be adapted
only through the current trace-era contracts.

## Product goal

Build three user-facing optimizer scopes over one frozen team, rotation, target
and account context:

1. **Selected Sets** - search real account artifacts while preserving the
   user-selected concrete set packages.
2. **All Sets** - search real account artifacts and feasible set packages.
3. **Theory** - compare inventory-independent equal-investment builds and set
   packages.

The immediate goal remains a working Selected Sets backend and button. All Sets
and Theory reuse the same evaluator after their candidate domains exist.

The product optimizes average DPS for the supplied fixed action script and
target. The action script may still contain engine-random outcomes: a fixed
sequence of player actions does not guarantee one fixed hit/reaction topology.
The optimizer does not repair a bad rotation or optimize general gameplay.
Final quality is the best simulated candidate among the candidates retained by
the chosen mode; no mode claims a mathematical global optimum.

Cold runtime is product runtime. A warm cache is useful but cannot hide a cold
failure. Selected Sets above 180 seconds and All Sets above 600 seconds are
unusable product failures. Faster is the design target.

## Accepted end-to-end direction

1. Freeze the engine, source/config, team, weapons, talents, rotation, target,
   account database and artifact ownership context.
2. Run low-iteration trace evidence to observe the rotation's actual hits,
   reactions, effective per-hit stats, modifiers, source dependencies and
   schedule. First detect whether hit/reaction topology changes across seeds. A
   single trace is sufficient only for a topology-stable context; otherwise the
   accepted input must represent the expected stochastic outcome distribution.
   Sampled DPS is never the ranking objective; trace evidence supplies equations.
3. Compile the accepted topology-stable or expectation-aggregated evidence into
   STANDARD and FAST formula evaluators.
4. Rebase FAST into an explicit artifact-variable objective. Character,
   weapon, rotation and target state are fixed parameters; raw artifact stats
   and artifact-set choices are controlled variables; known nested mechanics
   remain functions of those variables. The current incumbent-anchored
   `baseline + candidate-minus-baseline` form is a parity control, not the
   search contract.
5. In an isolated strategy, solve a bounded continuous relaxation to estimate
   the best stat balance and marginal value curves. This target guides search
   but cannot by itself delete a physical build.
6. Build legal artifact candidates as absolute stat vectors. Apply CR cap and
   other explicit caps before valuing candidate stats.
7. Remove only proven irrelevant/dominated states, then compose complete legal
   team assignments with one off-set piece where allowed and twenty globally
   unique artifact IDs. Use formula bounds to skip branches that cannot reach
   the finalist region.
8. Rank the retained assignments directly with FAST.
9. Simulate a bounded FAST finalist list with real GCSIM at common fidelity.
10. Publish the best simulated finalist, its artifacts, formula estimate,
   measured DPS, warnings and frozen identities.

FAST does not call STANDARD. STANDARD does not sit between FAST and GCSIM.

## Formula modes

### FAST - working product evaluator

FAST is the intended evaluator for optimizer search, but it is not yet product
accepted. It folds repeated observed hits into a small number of response-
equivalent channels and uses expected damage rather than sampled critical hits.
Current FAST removes crit-roll noise inside one observed trace. It does not yet
average seed-dependent hit elements, reaction occurrences or spawned attacks.

A normal FAST channel is separated by the engine evidence that can change its
response:

- actor;
- scaling kind;
- amplifying-reaction participation;
- raw engine attack tag;
- raw engine damage type;
- the complete observed candidate-response coordinate set, including nested
  source-program coordinates.

This is deliberately data-driven. There is no Chasca, Furina, element-name,
artifact-set or known-attack-type switch. A future unknown damage type remains
separate because its raw engine identity is different.

Only hits with the same response signature may be averaged. Therefore:

- charged, normal, skill, burst and other engine attack tags remain separate
  when the engine distinguishes them;
- the same attack tag dealing two damage types becomes two channels;
- different nested stat dependencies become separate channels;
- repeated hits of one signature collapse to event count / activation rate,
  weighted coefficient and weighted effective state;
- transformative reactions remain separate reaction channels;
- unsupported damage remains an explicit frozen residual.

Candidate arithmetic includes:

- ATK, HP, DEF and EM scaling supported by the captured formula;
- common additive damage bonus and the matching damage-type bonus;
- expected CR/CD with useful CR capped to `[0, 1]`;
- amplifying and transformative EM curves when owner/formula evidence exists;
- bounded nested source-program response slopes;
- observed defense, resistance and other frozen post multipliers.

FAST is approximate by design. The accepted trade-off is that it can reorder a
small number of close candidates and can theoretically omit the true global
best before final simulation. The final GCSIM run proves only which retained
finalist is best. The UI and result must not claim a global optimum.

### STANDARD - development control

STANDARD preserves the safe compact formula groups with substantially less
averaging. It is retained as a bounded development oracle for:

- FAST regression audits;
- new formula/damage-type fixtures;
- targeted parity checks after engine/schema changes;
- diagnosing an unexpected FAST result.

STANDARD is not a product stage, hidden fallback or mandatory FAST confirmation.
Do not run every FAST candidate through STANDARD in production.

### Detailed scorer - narrow parity fixture only

The old detailed per-candidate traversal is too slow for search. It may be used
only on a few deterministic fixtures to prove STANDARD compilation parity. It
must never be reconnected as the normal ranking loop.

## Development evidence and rejected real-context claims

Saved trace context:

- 358 observed hits;
- 198 STANDARD groups: 190 normal, 8 transformative, 0 whole-frozen;
- 23 FAST channels after response-signature separation;
- 12 Chasca channels, preserving observed attack-tag/damage-type families;
- no GCSIM calls during candidate arithmetic.

Selected-shaped single-swap diagnostic corpus:

- 1,223 legal physical/stat-distinct assignments, including the incumbent;
- STANDARD evaluation: about 2.00 seconds;
- FAST evaluation: about 0.18 seconds;
- same FAST/ STANDARD leader;
- Top-8/16/32/64 recall: 100%;
- Spearman rank correlation: about 0.999993;
- one formal sign mismatch is the incumbent's floating-point near-zero delta,
  not a material better/worse reversal.

Broad deterministic FAST/ STANDARD stat stress:

- 1,787 profiles;
- zero material sign reversals;
- mean FAST-vs-STANDARD error: about 9.55 DPS;
- maximum extreme-profile error: about 222.75 DPS / 0.286%;
- same leader;
- Top-16/32/64/128 recall: 100%;
- Top-8 recall: 7/8, with the same rank-1 candidate;
- Spearman rank correlation: about 0.999977;
- 12 direct damage-type bonus swaps: 100% sign agreement, maximum error about
  22.88 DPS.

Explicit artifact-variable v1 evidence:

- `artifact_variable_objective.py` rebases FAST's incumbent channel state into
  fixed non-artifact channel values plus sparse absolute raw artifact stats;
- direct ATK/HP/DEF/EM scaling, CR/CD, common/type damage bonus, amplifying EM
  and known linearized nested source response are rebased;
- the incumbent absolute vector, an empty artifact vector, changed absolute
  vectors and replacement-path independence match incumbent-delta FAST;
- eight dedicated contract/parity tests pass;
- no product/UI/search import and no engine call were added.

Focused trace-equation and isolated search suites pass. The live n=1000
same-context acceptance remains intentionally opt-in. Unit tests prove
contracts and local arithmetic fixtures, not real-context GCSIM truth.

The earlier scripts loaded current SQLite candidate deltas while the saved trace
came from `.codex_tmp/forwarded_attack_v1_run/team.txt`, an abstract dev stat
block. Therefore their physical leader/Top-K/sign claims remain rejected as
account or GCSIM evidence.

### Same-context acceptance attempt - 2026-08-26

The missing identity gate now exists in
`trace_equation/same_context_acceptance.py`, with an opt-in live integration test
in `test_same_context_acceptance.py`. It binds the same physical config file to:

- the exact 20 current SQLite artifact IDs, all globally unique;
- materialized aggregate artifact stats and active set lines for every wearer;
- current equipped weapons, fixed rotation/target/energy policy;
- trusted engine artifact/binding, source config and equipment snapshot hashes;
- both the n=1 trace invocation and ordinary n=1000 GCSIM invocation.

Identity binding passed, but the numerical gate correctly failed:

- FAST: `141306.0424 DPS`;
- GCSIM n=1000: `143738.2939 DPS`, SE `66.0034 DPS`;
- error: `2432.2514 DPS` / `1.6921%`;
- frozen allowance: max of 1% (`1437.3829 DPS`) and 3*SE
  (`198.0101 DPS`), therefore `1437.3829 DPS`;
- result: **FAIL**. The tolerance must not be widened to make this green.

FAST is not broadly arithmetically wrong for the sampled trace. That trace's
actual sampled DPS was `141157.9165`; FAST differed from it by about `148.13 DPS`
or `0.105%`. The failure is that one trace seed is not the mean rotation for this
context. A second n=1 trace with the adjacent seed, same config and same 4017
frames produced:

- 389 hits instead of 365;
- `143997.5538 DPS` instead of `141157.9165 DPS`;
- 90 spawned-reaction attacks instead of 68;
- different Chasca damage-element counts and resulting reaction counts.

Thus the old premise "same hits, only critical-roll noise" is disproved for the
real rotation. Current FAST faithfully approximates one sampled stochastic
schedule, not expected n=1000 DPS. No controlled artifact replacement parity
runs are authorized until this baseline failure is repaired.

## Fixed schedule, snapshots and nested mechanics

The trace records one actual execution of the supplied rotation. Candidate
evaluation may assume its hit/reaction schedule remains fixed only after a
generic cross-seed topology check proves stability. Otherwise event counts and
response-equivalent channels must carry an expected stochastic distribution or
an explicit uncertainty envelope. Choosing a lucky seed is forbidden.

Development decision 2026-08-26: stochastic skill/reaction averaging is deferred
until after the evaluator-independent composition algorithm exists. Until then,
the current single-seed FAST objective may be used only as
`PROVISIONAL_SINGLE_SEED` development input. It may prove search implementation
parity against exhaustive evaluation of that same provisional objective, but it
has no real-quality, safe-prune, finalist-policy, product or UI authority.
Generic stochastic aggregation and the unchanged live n=1000 acceptance test
remain mandatory before the full Selected quality audit.

Per-hit effective snapshots already contain temporary buffs such as the actual
damage bonus active at that moment. This lets candidate arithmetic value an
artifact stat against the correct observed buff state without rerunning GCSIM.

When an artifact stat also changes a buff or another supporting mechanic, the
mechanic must be compiled as a candidate-dependent formula just like direct
damage. The isolated correctness control now executes a real generic path from
an artifact-stat delta through heal/HP arithmetic, queued and ordered state,
the resulting modifier and the exact terminal hits that consumed it. A generic
forward/backward slice and cached FAST correction now make that path usable at
candidate-search speed without replacing the full control. Observed-domain
combined coordinates, multiple providers and relevant opaque boundaries pass
and the isolated complete-assignment boundary now consumes the evaluator.
Cap/overheal behavior outside that observed domain remains fail-closed and has
no product-prune authority.

If recursion reaches an unsupported closure, state object, cycle, ambiguous
owner or depth/node limit, the last observed value becomes `OPAQUE_FROZEN`.
Unknown input never becomes zero, independence or dominance evidence.

Common damage bonuses from goblets, sets, weapons and character buffs are one
additive damage-bonus bucket when the engine formula says so. Missing one of
these contributions can change HP/ATK versus damage-bonus main-stat ordering,
so the captured effective bucket and known candidate-dependent sources must be
preserved.

### Generic mechanism-dependency replay

Damage, buffs, healing, drains, stacks, thresholds and future mechanics use one
generic dependency rule. Start from every observed output that affects the DPS
equation, walk backward through engine provenance/state events, and stop only at
one of these typed terminals:

1. **Candidate stat leaf.** A concrete artifact-controlled stat feeds a scale,
   guard, cap, state update or modifier amount. Preserve it as a variable.
2. **Fixed action leaf.** The supplied rotation performs an activation at a
   fixed time and no allowed artifact stat changes that activation. Preserve it
   as fixed schedule input.
3. **Proven unused branch.** The mechanic is not reached and cannot become
   reachable anywhere in the allowed candidate domain. Only this proof permits
   removal.
4. **Opaque boundary.** Provenance is incomplete, ambiguous, cyclic or exceeds a
   bounded traversal limit. Freeze the observed value, emit diagnostics and
   reduce confidence; never relabel it as unused or fixed.

After the backward walk, replay the ordered state ledger forward for every
candidate: recompute candidate-dependent heal/drain amounts, HP caps and
overheal, state/stack accumulation, guards, queued updates, modifier caps and
the exact modifier active on each affected hit. Only after this replay may
equivalent events be compressed into FAST channels. This is a generic graph and
state-machine operation; production code may not switch on Furina, Bennett,
Fanfare or another known mechanic name.

Multiple supporting actors are not assigned manually. Every observed provider
feeds the same ordered ledger; their joint contribution, overlap, cap and
opportunity cost emerge from the team-DPS equation. Search must not force a
support mechanic to maximum. It may accept a lower buff when the support's
personal damage or another mechanic gives a larger total team result.

The current team is the acceptance fixture, not generic logic. Its intended
dependency path is:

```text
artifact HP/healing variables
  -> observed heal formulas and effective HP changes
  -> ordered HP-change state updates
  -> accumulated/capped burst state
  -> emitted additive team damage-bonus modifier by frame
  -> every affected hit channel
  -> total team DPS
```

The current exact C2 trace confirms why ordered replay is required. Observed
accepted burst-bonus values range from 37.5% to 100%, and 80 hits occur at the
100% cap. A naive average over all 365 hits, including unbuffed hits, is about
37.36%; actual-damage-weighting gives about 54.34%.
Neither number is a mechanic constant or a valid replacement for ordered replay.
The same trace contains 163 Furina drain rows, 28 Furina heal rows and five
Bennett heal rows. The generic graph must consume all observed contributors,
not assume one healer. This paragraph described the original loss: FAST once
froze the observed timeline. The current replay path now lets candidate HP and
healing changes alter the resulting team modifier and exact affected hits
without hard-coded entity names.

#### 2026-08-26 support-chain evidence status

The structural engine losses found by the earlier audit are repaired generically
and persisted. The runtime resolver selects a unique shortest route while equal-
shortest ambiguity remains fail-closed; numeric state/payload instrumentation
accepts only scalar values proven by the Go type structure; nonnumeric or
unresolved values remain opaque. No character, mechanic, set or element name is
used by production logic.

Patch `0017-gtt-support-chain-v1.patch` adds the remaining evidence bridge. A
queued task retains numeric provenance only for its execution scope, mutations
of numeric task arguments become explicit state-transition events, state writes
point to the arithmetic event that produced them, and the common observed form
`effective health change / max HP * 100` is linked to typed health-operation
fields only when the runtime value matches. A mismatch fails open to a literal;
it cannot create a false dependency.

One real exact-context diagnostic trace proves the following path:

```text
health-operation:9
  -> state-event:1092  (1.6 = effective amount / max HP * 100)
  -> state-event:1097  (queued numeric payload)
  -> state-event:1269  (task-local 1.6 -> 5.6 transition)
  -> state-event:1272  (state transition)
  -> state-event:1273  (state write 150 -> 155.6)
  -> observed modifier occurrences
  -> terminal hit occurrences
```

The trace contains 365 hits, 196 health operations and 39,767 state events. The
strict production decoder accepts schema v6. From `health-operation:9`, the
dependency index reaches 166 terminal hits; 170 modifier-evaluation/terminal-hit
pairs are bound for the observed team modifier. These counts prove evidence
reachability, not candidate-quality or expected-DPS accuracy.

Two Python contract defects exposed by the real trace were also repaired:

- an incomplete source-expression event may omit still-unbound template
  parameters, while a complete event must still bind the exact parameter set;
- ordered state validation now uses one incremental prior-event index instead of
  rebuilding the full prior map for every event. Strict decode took about
  18.17 seconds and dependency indexing about 3.49 seconds on this saved trace.

Patch `0018-gtt-replayable-state-arithmetic-v1.patch` removes the next
mechanical replay loss. Supported scalar assignment expressions are now emitted
as explicit `add`, `subtract`, `multiply`, `divide`, `min` and `max` numeric
events instead of the opaque `state_transition` label. The transformation is
structural: unsupported operators or unbound leaves still fail closed, and no
entity or mechanic name is inspected. State reads are emitted only when the
right-hand side actually consumes that prior state, avoiding false dependencies
and invalid generated Go variables.

That 18-patch build receipt is retained only as an earlier checkpoint. The
current active stack contains 21 patches. Patches `0019` and `0020` lower the
supported normalized-health and modifier arithmetic into replayable numeric
events. Patch `0021-gtt-hit-modifier-eval-binding-v1.patch` serializes the exact
modifier-evaluation event ID used by every captured stat and attack modifier
contribution on a terminal hit. All changes are structural; production code
does not inspect entity or mechanic names.

A fresh official v2.42.2 tree applied all 21 patches, compiled, and passed its
runtime probe from an absolute store path. The executable SHA-256 is
`8b212171a164e302511b235ac99d8439abc52e539854a4a42471f60d0c722a99`.
The current real trace is stored at
`.codex_tmp/same_context_trace_diagnostic_20260826_hit_binding_v11/trace.json`;
its evidence SHA-256 is
`d61117770d0932dbf2df0d3b7cc8d5c5a4f34431f62ed25150f5be3ffdbacc30`.
It contains 365 hits and 40,790 state events. All 3,328 serialized bindings
resolve exactly: 2,462 stat-modifier and 866 attack-modifier bindings, with zero
missing or mismatched IDs.

`trace_equation/support_replay.py` now performs a zero-engine forward replay and
projects changed modifier outputs into the exact hit rows. The isolated
`trace_equation/support_objective.py` control keeps STANDARD per-hit formula
granularity and deliberately has no pruning or product authority. On the real
trace, reducing Bennett artifact HP% by 0.20 has no direct-only formula effect,
but the support-aware control propagates through the observed team mechanic,
changes 14 Furina hits, and reduces rotation formula damage by about 1754.97.
This proves the generic cross-actor path; it does not prove GCSIM truth or an
expected stochastic schedule.

The control exposed and fixed an important input-domain defect: runtime modifier
deltas such as generic DMG% must enter the damage formula even when they are not
legal raw artifact coordinates. Artifact inputs and replayed dynamic inputs are
now kept separate until formula evaluation. Nineteen focused formula/replay
tests pass after that fix. The initial 7.2-second candidate cost was mostly an
implementation bug: the immutable 40k-event evidence identity was serialized
and hashed repeatedly. Caching that identity and prevalidating hit bindings
reduced the full control to about 0.28 seconds without changing the result.

The product-speed path remains separate. A compile-time forward/backward slice
keeps only events that both depend on a changed artifact coordinate and can
reach a modifier consumed by a hit. For the Bennett HP% case this reduces
20,821 replayable events to 1,535 and about 0.049 seconds. The full control emits
326 global frozen-runtime warnings for any non-empty delta; the slice emits no
new warnings and omits those unrelated to its candidate-to-hit path. Relevant
opaque boundaries must still remain frozen and reported.

`trace_equation/support_fast_objective.py` combines ordinary direct FAST with an
exact-hit support correction. Modifier projections are cached only by the
support-relevant artifact-coordinate subvector; each candidate's direct stats
still revalue that correction, so reusing a support projection cannot freeze CR,
CD, scaling or other direct interactions. On the real fixture:

- four artifact coordinates can reach DPS through the support graph;
- four single-coordinate checks match the full-control support correction
  within `2.1e-9` rotation damage;
- a cache miss takes about 0.049 seconds and a cache hit about 0.001 seconds;
- the exact-context 1,223-candidate fixed-4p single-swap corpus produced 251
  cache misses and 972 hits and completed in about 16.7 seconds;
- 16 profiles built from the observed physical minimum/maximum deltas of all
  four support-relevant coordinates (single-coordinate extremes, all-min,
  all-max and every pairwise maximum) match the full-control support correction
  with zero mismatches and at most `1.1e-8` rotation-damage error;
- engine calls remain zero.

These are runtime and formula-correction parity results only. The corpus is
single-swap, not complete Selected composition; its leader is not accepted as a
quality result. The observed physical support-coordinate boundary and combined
extremes are accepted for isolated composition work. Deliberate
multiple-provider and candidate-relevant opaque-boundary regressions pass.
Cap/overheal behavior outside the observed domain remains fail-closed rather
than extrapolated, so this still grants no product/prune authority.

The evaluator is now consumed only through
`optimizer_trace_search/selected_composition.py`. This boundary does not invent
or prune candidates: it validates one supplied complete 20-artifact assignment,
enforces global physical-ID uniqueness, slot correctness and every wearer's
selected fixed-4p package, materializes absolute artifact variables and then
calls cached support-aware FAST. A reduced exact-context binary audit varied
eight real slots selected specifically for support reachability. Of 256
combinations, 60 were complete/legal, up to four artifacts changed together,
all 60 support keys were distinct, and scoring took about 4.16 seconds with
zero engine calls. The incumbent was retained and reproduced zero delta. This
is an integration/runtime proof, not a candidate-generation strategy or leader
quality result.

Synthetic regressions also prove two fail-closed boundaries: two candidate
actors may feed one combined modifier before a hit and FAST still matches the
full control; when a candidate-relevant numeric source is opaque, its observed
value freezes, the uncertainty survives into the score, and no false support
gain is invented.

### Baseline anchoring versus artifact variables

The historical 358-hit development trace was produced from an abstract dev stat
block, not the current SQLite assignment. A newer exact-current-equipment trace
exists and passed identity binding, but failed expected-DPS acceptance because
its single seed is stochastic. In every case FAST channel fields contain the
effective observed state of the trace-producing configuration. Replacement
scoring applies the complete aggregate delta

```text
candidate artifact vector - incumbent artifact vector
```

to every supported coordinate. This is valid only when the incumbent vector is
immutably proven to be the vector that produced the trace. For direct stats it is
algebraically equivalent to subtracting the incumbent artifacts from the
observed state and adding the candidate. Algebraic subtract/add tests cannot
replace that identity proof; the attempted DB audits demonstrated this failure.

That incumbent-anchored representation is nevertheless the wrong ownership
boundary for continuous allocation and general composition. Before search,
compile or adapt it into the explicit form

```text
known fixed context + artifact-controlled variables
  + known derived mechanics(artifact-controlled variables)
  + typed frozen residual
```

The categories are:

- **controlled variables:** raw main/sub-stat totals per wearer and the
  artifact-set/package state selected by the candidate;
- **fixed parameters:** character and weapon identity/base data, talents,
  constellation/options, rotation, target, enemy and engine semantics;
- **known derived values:** buffs, healing, reaction or other mechanics whose
  formulas are fixed but whose output can change when artifact variables
  change;
- **frozen residual:** unsupported behavior retained at its observed boundary.

Weapon, ascension and rotation buffs must not be added again during candidate
evaluation. Conversely, incumbent artifact stats must not remain hidden as
unchangeable constants. Selected Sets may freeze the chosen set package as a
discrete lane, but its effect is still artifact-owned input, not part of the
character's permanent base. All Sets will vary that input explicitly.

FAST does not reduce the entire rotation to one global average character stat.
It preserves separate response-equivalent channels. Within each channel it
uses hit-count-weighted effective states and event count; activation rate per
second is derived metadata. Therefore the fixed/non-artifact part may differ
between channels when buffs differ in time.

Required parity invariants before any continuous search:

1. zero artifact delta reproduces the accepted FAST baseline;
2. explicit-variable evaluation of the incumbent artifact vector reproduces
   the same baseline;
3. explicit-variable and incumbent-delta forms agree for every supported
   deterministic test replacement within tolerance;
4. scoring depends only on the final absolute artifact vector, not the order
   or path of replacements;
5. the artifact vector contains no weapon, ascension or temporary-buff rows;
6. known artifact-dependent nested mechanics change through their source
   expression, while unknown ones remain typed frozen rather than silently
   becoming fixed or independent.

The incumbent-delta evaluator remains a bounded regression oracle until these
invariants pass. It must not be the input contract of the continuous optimizer.

## Continuous balance and discrete artifact search

An unconstrained damage formula has no finite artifact optimum: apart from
explicit caps, more positive stats always increase damage. The formula becomes
an optimization problem only after defining a bounded investment/feasibility
domain. The accepted continuous relaxation is now derived from the fixed
five-star artifact rules rather than from fractional mixtures of account
builds. Physical account artifacts remain a later discrete domain and are not
used to invent the mathematical stat budget.

### Confirmed five-star artifact investment contract

The user confirmed the canonical one-roll table on 2026-08-26. Each five-star
substat roll has one of four configured values. Their RV qualities are
70/80/90/100%; conditional on the selected substat, the four value tiers are
equally weighted. Percent values below are internal fractions:

| FAST stat | 70% | 80% | 90% | 100% |
|---|---:|---:|---:|---:|
| `hp` | 209.13 | 239.00 | 268.88 | 298.75 |
| `atk` | 13.62 | 15.56 | 17.51 | 19.45 |
| `def` | 16.20 | 18.52 | 20.83 | 23.15 |
| `hp%` | 0.0408 | 0.0466 | 0.0525 | 0.0583 |
| `atk%` | 0.0408 | 0.0466 | 0.0525 | 0.0583 |
| `def%` | 0.0510 | 0.0583 | 0.0656 | 0.0729 |
| `em` | 16.32 | 18.65 | 20.98 | 23.31 |
| `er` | 0.0453 | 0.0518 | 0.0583 | 0.0648 |
| `cr` | 0.0272 | 0.0311 | 0.0350 | 0.0389 |
| `cd` | 0.0544 | 0.0622 | 0.0699 | 0.0777 |

A four-line +20 artifact contains four initial values and five upgrade values:
nine roll instances. Five artifacts therefore have an absolute ceiling of 45
roll instances per wearer, not 49; a three-line start has eight. Main stats are
separate deterministic slot choices and do not consume this substat budget.

Continuous investment is measured in maximum-roll equivalents. One configured
roll consumes 0.7/0.8/0.9/1.0 units, and each wearer has a hard ceiling of 45
units. A full four-person team therefore has at most 180 units, but investment
is constrained separately per wearer: quality cannot be transferred from one
character's five pieces to another character. The target is a curve across
investment levels, not only the unattainable all-perfect endpoint. Real
physical candidates retain their exact stored values and are always evaluated
directly by FAST.

The relaxation also retains safe game-derived coordinate ceilings. A substat
can occur once per piece and can receive at most five upgrades, so one stat has
at most six roll instances per eligible piece. A piece whose main stat equals
that stat is ineligible for that substat. The v1 relaxation does not yet encode
every four-distinct-substat packing constraint; it is therefore an optimistic
search target with no prune authority.

Flower/plume main stats are fixed. Sands, goblet and circlet are discrete
lanes using the existing legal five-star main-stat catalog. Different elemental
or physical damage types stay separate. Main-stat lanes may be compared by
their optimized FAST objective, but their values must never be converted into
the shared substat-roll budget.

For a simple product, equal-cost stat investment is optimal when marginal DPS
gain per unit of artifact investment is equal across the stats that receive
investment. The same rule extends to FAST's multi-channel objective: calculate
the marginal total-team gain of each artifact-controlled coordinate against
the current fixed context, including channel coverage, caps, reactions and
known nested effects. A two-stat graph becomes a multidimensional continuous
surface, but the principle is unchanged.

The continuous solution is a **search target and heuristic**, not a physical
answer or prune proof. Real artifacts are indivisible multi-stat packages,
main-stat/set choices are discrete, and two wearers can want the same physical
piece. Raw Euclidean distance to the ideal vector is not a valid ranking. A
physical candidate's distance is its objective loss under FAST.

The former fractional-build idea (`a*A + b*B` over complete account builds) is
superseded and must not be implemented as `continuous_target_v1`.

The accepted search design is therefore hybrid:

1. solve a bounded continuous relaxation for each required discrete lane, or
   for the full team when the relaxation owns cross-character constraints;
2. use the resulting target, marginal curves and sensitivity to find strong
   complete incumbents and order branches;
3. combine physical artifacts as vectors, with an optional two-slot/three-slot
   meet-in-the-middle implementation detail;
4. retain globally contested alternatives instead of keeping only each
   character's locally best build;
5. prune only by contextual dominance or a valid optimistic formula ceiling;
   distance from the continuous target alone never authorizes deletion;
6. score surviving complete twenty-artifact assignments with FAST, then send a
   bounded finalist set to real GCSIM.

For an unfinished branch, a safe first ceiling may use an impossible fantasy
completion containing the independently best remaining value of every useful
coordinate. Because the fantasy dominates every legal completion on modeled
monotone coordinates, a branch may be closed when even that ceiling cannot
enter the retained finalist region. Any non-monotone or frozen dependency
disables that proof for the affected coordinate and widens retention.

If the bounded search finishes, it may prove the FAST optimum for that frozen
domain. If a product deadline stops it early, report the best complete result,
the largest remaining optimistic ceiling and the unresolved gap. Never label a
timed result a mathematical global optimum.

## Search-strategy isolation contract

The new search layer is intentionally replaceable. Its package root is
`run_workspace/gcsim/optimizer_trace_search/`; it must not be placed inside the
FAST formula compiler and must not be imported by UI/product composition roots
until an explicit acceptance gate passes.

Boundaries:

- immutable input contract: compiled explicit-variable FAST objective, frozen
  context identities and read-only legal artifact-domain snapshot;
- immutable output contract: strategy identity/version, proposed physical
  assignments, FAST scores/bounds, retained/pruned counts, timing and
  diagnostics;
- explicit strategy selection, initially `continuous_target_v1`; a second
  experimental strategy may coexist behind a different identity without
  becoming a fallback or sharing mutable state;
- no engine runner, GCSIM process, UI import, artifact equip/save, cache
  mutation or product callback inside a strategy;
- experiment harnesses live under `tools/experiments/`, focused tests under
  `tests/run_workspace/gcsim/optimizer_trace_search/`;
- deleting one rejected strategy must leave FAST, STANDARD, artifact
  materialization and other strategies intact.

"Parallel strategies" means isolated code alternatives that can be compared
sequentially. It does not authorize parallel agents or simultaneous expensive
runs.

Initial acceptance uses exhaustive truth only on deliberately reduced artifact
domains small enough to enumerate offline. The experiment must show target
quality, retained-winner recall, safe-prune parity, visited-state count and
runtime. It must make zero GCSIM calls. A failure may revise only the isolated
strategy; after three substantive failed revisions, stop for user review.

## Reactions

Ordinary amplifying and transformative reaction arithmetic must use engine
formula/owner evidence, not black-box DPS fitting. Reaction EM cannot be ignored
when the reaction is a material share of team damage.

Fixed-schedule reaction evaluation may vary owner EM and other transported
inputs. If ownership, aura topology, ICD/suppression, contributor fan-in or the
reaction operator is unknown, keep the affected candidate and mark the response
frozen/degraded rather than inventing a result.

Before claiming broad product compatibility, add controls for:

- Bloom and its converter ownership;
- a reaction-dominant amplifying team;
- a multi-contributor Lunar reaction where changing one character can reorder
  contributor weights;
- a future/unknown reaction operator that freezes cleanly and emits diagnostics.

Low-materiality incidental opaque reactions may remain frozen. Their measured
damage share, not hit count, determines warning severity.

## Energy boundary

Energy/ER optimization is deferred. Technical character wrappers used by the
engine for energy bookkeeping are not damage actors. They may remain ignored or
frozen for the current fixed-rotation DPS objective.

Do not infer an ER threshold from the current evaluator. A future energy mode
must explicitly bind each wrapper to its character and solve the feedback
between damage, enemy energy drops, rotation feasibility and ER. It must be a
separate accepted contract, not an incidental extension of FAST.

## Frozen and unknown mechanics

Unknown mechanics must not stop formula evaluation. The normal rule is:

1. evaluate every known formula;
2. retain the observed unknown contribution as a frozen boundary;
3. report the known/frozen damage shares and candidate reachability;
4. keep additional candidates when a material unknown may affect their order;
5. let final GCSIM include the real mechanic for retained finalists.

If a material portion is unknown, return a degraded best-effort result rather
than crash or silently claim normal confidence. A deterministic sanitized debug
archive should eventually be written to
`data/gcsim_optimizer/diagnostics/<report_sha256>.zip`.

The archive must contain engine/schema/source/config identities and bounded
mechanic evidence, but no tokens, cookies, browser state or other credentials.

## Artifact and set candidate boundary

The accepted 1,223-candidate corpus is diagnostic only. It contains the
incumbent plus legal single-piece changes under currently equipped fixed sets.
It is not a complete Selected optimizer.

Selected Sets still needs complete multi-slot composition. The intended
filtering direction is "remove proven junk, then search the remainder":

- never assign one context-free scalar score to an individual artifact;
- derive continuous stat balance from the explicit artifact-variable formula,
  then use it only to guide physical combination search;
- discard main-stat concepts with no meaningful formula response;
- compare artifacts in the context of useful stats and caps, not context-free
  crit mass;
- count CR only up to the character's remaining useful cap;
- retain materially different CR/CD/scaling/EM distributions;
- remove a piece only when another feasible piece safely dominates its response
  and contention backup value;
- choose the off-set piece as part of the complete build, not greedily per slot;
- preserve account-wide alternatives when two characters may need the same
  artifact;
- rank complete assignments with FAST.

All Sets is not merely Selected with more names. It additionally needs generic
set semantics: wearer eligibility, activation condition, affected attack/damage
types, team recipients, coverage, duplicate/overlap behavior and replacement
opportunity cost. Candidate set effects must add their own response dimensions
to the hit signature; incompatible modifier types must never be averaged.

Theory uses the same formulas but a different candidate domain and equality of
investment. It must not return physical artifact IDs.

## Independent FAST product flow

The accepted product flow is:

```text
explicit artifact-variable FAST objective
  -> bounded continuous target (guidance only)
  -> candidate domain
  -> contextual relevance/dominance and formula-bound filtering
  -> legal complete assignments
  -> FAST ranking
  -> bounded FAST finalists
  -> real GCSIM at common fidelity
  -> best simulated finalist
```

There is no `FAST -> STANDARD -> GCSIM` chain.

The finalist count is not yet frozen. It must be chosen from legal multi-piece
recall/runtime measurements, not from the synthetic broad-stat audit alone. The
incumbent must always survive to final comparison.

## Current performance boundary

Formula arithmetic is no longer the main Selected bottleneck:

- FAST evaluates 1,223 candidates in about 0.18 seconds;
- STANDARD evaluates them in about 2.00 seconds;
- broad FAST+STANDARD evaluation of 1,787 profiles takes about 2.8 seconds.

Older cold trace decoding varied roughly from 38 to 104 seconds while ordered
state validation rebuilt its prior-event index repeatedly. After the incremental
index repair, the current 66.9 MB saved trace decodes strictly in about 18.17
seconds and builds the dependency index in about 3.49 seconds. This is improved
but still a material fixed cost. Before UI acceptance:

- cache the validated decoded/aggregated trace evidence and compiled FAST
  objective by complete engine, source, config, rotation, target and schema
  identity;
- prove cold-cache and warm-cache behavior separately;
- invalidate fail-closed on any bound identity change;
- do not require STANDARD compilation for the FAST product path.

Candidate generation, full-domain composition search and finalist simulations
still need measured cold budgets after they exist.

## Current code map

Working evaluator:

- `run_workspace/gcsim/trace_equation/coarse_rotation_objective.py` - FAST and
  mode boundary;
- `run_workspace/gcsim/trace_equation/artifact_variable_objective.py` - accepted
  explicit absolute raw-artifact-stat view of FAST; the incumbent-delta form is
  its regression oracle;
- `run_workspace/gcsim/trace_equation/rotation_objective.py` - STANDARD compact
  control;
- `run_workspace/gcsim/optimizer_trace_selected_candidates.py` - current
  Selected incumbent/single-swap diagnostic corpus.

Created isolated search boundary:

- `run_workspace/gcsim/optimizer_trace_search/` - isolated continuous-target
  strategy plus a complete-assignment scoring boundary; proposal generation and
  pruning remain separate and no product import is allowed until their gates
  pass;
- `run_workspace/gcsim/optimizer_trace_search/selected_composition.py` -
  validates and scores complete physical Selected assignments with attempt-local
  support caching; it deliberately generates and deletes nothing;
- `run_workspace/gcsim/artifact_investment_rules.py` - one neutral source for
  confirmed five-star roll tiers, main-stat values and optimistic coordinate
  ceilings;
- `tools/experiments/gcsim_trace_continuous_target_v1_audit.py` - saved-trace,
  current-SQLite offline audit harness; its first attempted result is rejected
  because the saved trace stat block was not produced from that SQLite vector.

Evidence and tests:

- `tools/experiments/gcsim_trace_formula_modes_v1_audit.py`;
- `tools/experiments/gcsim_trace_formula_modes_v1_wide_stats_audit.py`;
- `tools/experiments/gcsim_trace_continuous_target_v1_audit.py`;
- `run_workspace/gcsim/trace_equation/state_evidence.py` - strict ordered-state
  decoder and validation;
- `run_workspace/gcsim/trace_equation/candidate_dependencies.py` - typed
  reachability/diagnostic dependency index;
- `run_workspace/gcsim/trace_equation/support_replay.py` - full-ledger
  zero-engine correctness replay and exact per-hit modifier projection;
- `run_workspace/gcsim/trace_equation/support_objective.py` - isolated
  support-aware STANDARD control; never use it as the mass search evaluator;
- `run_workspace/gcsim/trace_equation/support_fast_objective.py` - isolated
  cached FAST plus exact-hit support correction; still has no product/prune
  authority;
- `tools/experiments/gcsim_trace_support_objective_v1_audit.py` - saved real-
  context zero-engine support audit;
- `tools/experiments/gcsim_trace_selected_composition_v1_audit.py` - reduced
  real complete-assignment integration/runtime audit with zero engine calls;
- `tests/run_workspace/gcsim/trace_equation/test_coarse_rotation_objective.py`;
- `tests/run_workspace/gcsim/trace_equation/`;
- `tests/run_workspace/gcsim/optimizer_trace_search/`.

Engine patches currently extend through `0021`, but no future task may hard-code
that range. Before product cutover, audit every patch present at that time,
remove obsolete deltas, consolidate required engine changes into one versioned
patch and prove automatic update plus rollback. The current optimizer UI and
three product buttons do not yet exist.

## Immediate implementation order

Completed analytical prerequisites: explicit artifact-variable v1 and its
synthetic parity fixtures. The exact-current-equipment identity binding is also
implemented and passed. Real-context numerical parity was executed and failed
because one trace seed does not represent the stochastic mean. Selected set
packages remain frozen discrete lanes; generic variable set semantics still
belong to the later All Sets stage.

1. **Support-domain and complete-assignment boundary - completed for isolated
   development.** Single-coordinate and 16 real boundary/combined profiles
   match the full support correction. Candidate-relevant opaque and two-actor
   combined-provider fixtures pass. The cached scorer is exposed only through a
   complete legal assignment boundary. Its reduced real audit scored 60 legal
   multi-piece assignments (up to four simultaneous changes) in about 4.16
   seconds with zero engine calls. This grants no pruning, product or UI
   authority. The boundary now consumes no more than `candidate_limit + 1`
   rows from an input stream, keeps support/assignment caches bounded per
   attempt, uses logarithmic artifact-ID lookup, and exposes frozen baseline
   damage/share in each FAST score.
2. **Continuous-target input and provisional quality gate - current blocker.**
   The isolated v1 core, exact investment rules, main-stat lanes, marginal
   allocation and bounded exchange are
   implemented. Eight focused analytical tests pass, including exhaustive
   equality on a small integer-roll domain. The attempted real-context audit is
   **rejected**: `.codex_tmp/forwarded_attack_v1_run/team.txt` is an abstract dev
   stat configuration, while the audit supplied current SQLite equipment as its
   incumbent artifact vector. The algebraic subtract/add reconstruction passed
   but did not prove identity. It generated negative non-artifact EM and even
   negative Furina reaction damage after replacement. Its target allocation and
   DPS must not be cited as account evidence. Exact identity binding now exists;
   Now validate reaction ownership and compare target retrieval with
   exhaustive complete physical builds on a deliberately reduced domain using
   the same `PROVISIONAL_SINGLE_SEED` evaluator. This proves implementation
   equivalence only, not real GCSIM quality or product pruning.
3. **Contextual frontier and bounded composition prototype.** Add formula ceilings,
   cap-aware dominance, selected-set/off-set legality and global artifact-ID
   contention. Compare every claimed safe prune with exhaustive reduced-domain
   truth under the same provisional evaluator. Keep the incumbent and conflict
   alternatives. Keep this strategy isolated so later expected-channel input
   replaces single-seed input without rewriting composition.
4. **Deferred stochastic-skill expectation gate.** Before any real-quality/full-
   Selected claim, aggregate seed-dependent hit elements, reactions and spawned
   attacks generically. Prefer compact engine-side aggregation of a bounded
   fixed seed panel; repeatedly decoding full 47 MB traces is not acceptable.
   Keep a topology-stable one-trace fast path. Rerun the unchanged exact baseline
   test and then a small controlled replacement set within the frozen 1%/3*SE
   allowance. Do not tune the seed or tolerance.
5. **Full Selected multi-piece audit.** Run the isolated strategy on the frozen
   real account domain with zero GCSIM calls. Measure visited states, reduction,
   unresolved bound gap and runtime before accepting it as the Selected search
   implementation.
6. **FAST finalist policy.** Measure legal recall/runtime and freeze a bounded
   top-K plus uncertainty/incumbent policy.
7. **Final GCSIM verification.** Run retained finalists at common fidelity,
   choose by simulated DPS, support cancel/resume/cache identities and report
   formula-versus-simulation residuals.
8. **Selected UI button.** Expose progress, result artifacts, simulated DPS,
   warnings and debug path. Prove a clean new-user cold run.
9. **All Sets semantics and search.** Add generic set candidates/allocation,
   then reuse FAST and final verification.
10. **Theory domain and button.** Add equal-investment candidates without
   physical artifact IDs.
11. **Engine patch consolidation/update UI.** Audit all then-current patches,
   build one consolidated patch and atomically update/rollback engines.

Do not start a new black-box stat map or reconnect old M/S/Gate orchestration.

## Acceptance and working rules

- Work sequentially. Do not use subagents or parallel agents for this project.
- Do not brute-force parameters or repeatedly run GCSIM to discover known
  formulas. Reuse accepted traces and local deterministic arithmetic.
- After three failed substantive attempts on the same blocker, stop and discuss
  it with the user. A fourth attempt requires a changed failure category or
  explicit approval.
- No character, set, element or reaction name switches in generic evaluator
  logic. Fixtures may name concrete game entities.
- Unknown behavior freezes at a typed boundary and creates diagnostics; it does
  not crash the normal evaluator.
- Preserve unrelated user work in the dirty tree.
- Update this handoff, `CODEX.md` and `TODO.md` whenever the roadmap or accepted
  contract changes. Remove stale active steps instead of appending another
  development diary.
