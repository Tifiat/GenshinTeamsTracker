# All Sets speed research: consolidated ledger — 2026-09-28

Owner: GP-3 checkpoint for acceptance; Go design for implementation. This receipt
consolidates the prior waves and the player's remaining hypotheses. Measurements
below concern isolated source-copy research. Subsequent integration and current
installation evidence are in the [matrix and integration gate](matrix/README.md);
do not read a historical prototype pass as production acceptance. The main agent implements/reviews;
bounded Sol helpers write small isolated helpers; Luna runs serialized managed
jobs. No Computer Use, account/equipment writes, or application restart.

## Comparison contract

Same saved Chasca request, inventory, rotation and two seeds:
`all_sets-20260927-212145-2c1cb70d`; request SHA
`8fc91b23f9c96ede6dd08ed88e7313c138119d7c52e34bdf67674095f89c8f8f`.
Active engine `gcsim-v2.45.0-20260927011932`, artifact SHA
`7df37b5224f655d271d9389686bf22445717e02e896df5e3aa22d1d698042f8c`.
Baseline consumer SHA
`585aca6b49bd766a2b41fd5cc4392f6aeffd6463b824660f39736f62f55b1715`.
Each runner verifies active identity and drives the actual CLI All Sets
coordinator with hash/config/seed-bound saved captures. No engine fallback.

Times below are measured search seconds, **not** build/test time or total button
latency. New ordinary GCSIM finalist simulations are not run. Scores refer to
the retained formula model, not independently verified live-simulation DPS.
There are 7 bonus groups, each with a leader and 6 independent single-item swaps:
49 rows. Output validation checks physical inventory membership, twenty unique
items, set groups and single-swap semantics. Search remains bounded by work/
cycle policies; `neutral_cycle_budget` is not a timeout or global optimality.

Two reference identities must not be conflated:

- Installed saved output: fingerprint `b85e013d2680db75f94c5622afc3e7582a5b94984286a0fc569a4869f525f843`.
- Narrow prototype: fingerprint `4b6f3f964c3e6de793f0b76366b18f859c19229522b4b83b501485950fb9a4cd`.
  Six group leaders stay unchanged; the Furina 2p Golden Troupe group improves
  by 48.6938 DPS. Sorted rank deltas split that into +47.8809 and +0.8128 because
  two groups exchange rank. `exact_rows=false` against the installed output
  therefore does not by itself mean a loss.

## Earlier waves: what is already measured

Full measurements and controls remain in their original receipts:
[first wave](../2026-09-27-search-hypotheses/README.md),
[preparation](../2026-09-28-preparation-hypotheses/README.md),
[bonus representation](../2026-09-28-bonus-hypotheses/README.md).
Small single-run differences are not independently established speed gains.

| Hypothesis | Measured search seconds | Disposition |
| --- | ---: | --- |
| Installed-like reference |132.262; confirmation132.780|Reference|
| Shared source accounting |136.189|No benefit|
| Larger bounded reduced-program cache |124.965|Exact reuse; memory tradeoff|
| Memoize already-resolved contexts |127.812|Exact reuse|
| Narrow initial refinement frontier 8→2 |105.277;104.015|Heuristic; final stabilization unchanged|
| Cache + context memo + narrow frontier |84.322|Measured compatible combination|
| Lazy/full unreduced evaluation |181.280|Reject: slower|
| Linear freeze without shared-subexpression reduction |189.242|Reject: slower, large allocation churn|
| Group equal constants only |131.626|No material gain|
| Immutable inventory vectors |83.504 vs85.166|Small exact setup reuse|
| Prepared event-query plans |84.255 vs85.166|Small exact setup reuse|
| Reuse unchanged formula regions |82.602; dense export81.134|Exact setup reuse|
| Combined preparation changes |79.582 vs83.922|Measured compatible combination|
| Dense constants + sparse genuinely variable effects |65.069 vs79.110|Largest new representation gain|
| Reuse equal effect-family compositions |60.970 vs62.698|Small exact gain after interaction checks|
| Cache immutable Amount-function syntax plans |60.600 vs61.302|Small measured gain, not a major lever|
| Fresh n=1 capture per 4p |2.974/2.616/2.613 per changed context|Three contexts already ~8.2s; all249 shared source replays ~7.4–8.1s. Reject blanket recapture|

These times are **not additive**. Every later prototype explicitly inherits its
compatible predecessors; the combined runs measure the actual total.

The new `player_safe_wide` control combines all exact reuse/representation work
but restores the original wide refinement. It takes **91.355s**, still790687
trials, and preserves the complete installed 49-row fingerprint. Thus about31%
of the original wall time can be removed without changing the search policy on
this case. The separate ~60.6s chain includes narrowing; do not attribute that
additional gain solely to caches.

## Player-logic and approximate-search trials

All following variants inherit `amount_plan` (~60.6s), unless explicitly noted.
The actual final scores use the normal formula except the uptime experiment,
whose49 retained builds are independently rescored with approximation disabled
in a fresh process. A short list or local stat weight is never a hard upper bound.

| Hypothesis | Seconds | Quality / decision |
| --- | ---: | --- |
| Keep paired screens, omit single screens |60.687|190838 trials; all49 narrow-reference rows identical; no material time gain|
| Initial refinement width2→1 |54.151|121697 trials; all49 narrow-reference rows identical; promising, still heuristic|
| Tighten sampled-gap rejection 2→0.5 |51.590|Loses a group; sorted rank7 −320.36 DPS vs installed. Do not silently enable|
| Only one coordinate cycle |40.608|Top2 retained; ranks3–7 lose714–2215 DPS. Second cycle is useful|
| Prioritize crit mass alone |63.371|Returns installed49 rows, loses the narrow chain's small improvement; no speed gain|
| Permanently keep top2 weighted items per physical set/slot in a candidate run |62.244|Only top1 preserved; lower ranks lose695–1481 DPS, two original groups absent. Reject|
| Same with top4 items |64.635|Recovers all49 narrow-reference rows but slower. Reject as acceleration|
| Equal normalized amounts of locally useful stats |64.940|Top1 loses740.29 DPS vs installed; slower. Reject|
| Preselect top32 simple2p packages by legal item quality + source-derived bonus |56.583|All49 narrow-reference rows identical;451/524 packages retained per actor, not32 total|
| Same with top96 |58.806|Same49 rows;515/524 retained; little benefit|
| Mean observed constant bonus across matching reads |59.970|Exact rescored top7 unchanged; displayed error up to907.55 DPS. No meaningful gain|
| Peak observed constant bonus across matching reads |58.949|Exact rescored ranks3–7 lose185–5995 DPS vs narrow reference; display error up to12231.50. Reject|
| Direct literal2p port construction, without event replay |62.359|All49 narrow-reference rows identical;36 choices bypass replay,249→213 total replays; no observed whole-search gain|
| Paired screens + refinement width1 together |53.756|112182 trials; all49 narrow-reference rows identical. Actual combined measurement, not added percentages|
| One actual-build point in the shared formula, top32 before detailed preparation |45.230|119180 trials; all49 narrow-reference rows identical; all49 scalar points agree with normal context evaluation|
| Same with top96 |47.093|129528 trials; same49 rows and parity. Wider screen adds work without improving this case|

Receipts: `search-frontier-attempt1.json`, `depth-attempt1.json`,
`item-priority-attempt1.json`, `package-priority-attempt1.json`,
`uptime-attempt2.json`. The retained `uptime-attempt1.json` is a harness failure:
the oracle initially expected numeric JSON DPS, while the product writes a
decimal string. Corrected to `json.Number`; no game/optimizer bug was inferred.
`literal-and-combo-attempt1.json` additionally owns the direct-literal and
normalized-stat-amount trials. Normalization uses the available item vectors,
not hardcoded official substat roll sizes; this is a useful-amount proxy.
`point-screen-attempt1.json` owns the new deferred-preparation experiment.

## Measured combinations, not a sum of projected savings

`final-combination-attempt1.json` repeats the installed-like baseline and then
runs three explicit combinations on the identical frozen input:

| Combination | Search seconds | Candidate trials | Result |
| --- | ---: | ---: | --- |
| Installed-like baseline |134.399|790687|Installed49 rows exactly|
| Exact reuse/representation + narrow frontier + simple2p preselection + width1 refinement |51.611|119168|Improved49 rows exactly|
| Exact reuse/representation + narrow frontier + shared-formula point32 preselection + width1 refinement |42.658|85906|Improved49 rows exactly|
| Same shared-formula point32 preselection, without width1 refinement; repeat |45.699|119180|Improved49 rows exactly; earlier45.230s|

The42.658s combination is about3.15 times faster than the fresh134.399s
baseline (68.3% less search time). It is a real combined run, not a prediction.
Six bonus-group leaders retain their original DPS; one improves48.6938 DPS.
Top1 remains153577.8043 formula DPS. All49 final point evaluations are checked
against normal context resolution in a fresh process; retained-score residuals
are at floating-point rounding scale, not a new ordinary GCSIM comparison.

Final confirmation `adaptive-confirmation-attempt1.json` repeats
`player_point32_refine` at44.833s and tests `player_point32_adaptive` at43.443s.
The latter stops a speculative cheap prepass after16 unsupported packages and
zero successful scalar points, returning the **entire** feasible package list.
It never treats unsupported as weak. The first two actor blocks now spend
0.229/0.286s rather than1.451/1.971s before falling back to all524 packages;
the remaining six retain the normal point32 screen. Both runs retain85906
trials and the identical improved49-row fingerprint. All49 point checks pass;
max retained-score rescore residual is2.91e-11 DPS. Thirteen named hypothesis
controls pass per variant, in addition to the focused existing controls.

Thus the measured combined target is **about43–45s**, not a promised42.658s
on every repeat and not30s. The adaptive variant is the nominated matrix
candidate; original-width exact reuse is the fallback/control. End-snapshot
reserved Go heap is708.5MB for adaptive versus616.3MB in the fresh baseline;
cumulative allocations fall from29.20GB to12.03GB. Neither is peak RSS. Larger
reuse caches still need the cross-team bounded-memory gate.

These measurements exclude fresh engine capture work. The original live sample
has139.913s search and141.542s backend elapsed; the prior complete live session
is154.579s. Replacing its search using the replay speed comparison suggests
roughly one to one-and-a-half minutes for this fast-mode button case, **not** a
measured new UI time or a promise for other teams. Ordinary mode additionally
pays for the configured number of finalist simulations. Research build/control
time is not application startup and must not be added to that prediction.

Simple2p hints are derived from engine source, not hardcoded stat tables or a
named-set allowlist. The strict prototype recognizes18/42 source sets, of which
the available simple inventory combinations produce105 rankable packages.
Unknown2p, all4p, zero-bonus, current search leader and reservation failures
remain mandatory. The source-only hint is not yet a generic all-set descriptor.

The direct-literal variant imposes stricter source checks: permanent literal
modifier key/duration, plain non-Extra owner stat, no receiver rebinding or
side effects outside recognized branches, trivial Init, and no neutral modifier
key collision. It preserves stat modes/masks and modifier/stat write footprints,
including interactions requiring joint replay. Eight eligible owner/set choices
are checked against ordinary replay at **every retained port**, including
footprints and uncertainty. Unknown forms fall back. This confirms that simple
2p effects need not always replay events, but not that bypassing those few
first replays materially accelerates the whole search.

The mean/peak experiment groups matching owner, member, kind, stat, mode,
stat-key mask, attack identity and target. It leaves symbolic components and
resistance curves exact. Grouping is prepared once per captured binding. Mean
is a mean of observed reads, not time-weighted uptime; peak is observed peak,
not an engine-derived theoretical maximum. Both still pay first source replay,
so they cannot eliminate the cost of first discovering activation. Finalist
GCSIM cannot restore candidates already discarded by their distorted ranking.

## Deferred detailed preparation: the substantial new player-logic result

`player_point32` does not replace a conditional bonus with full uptime. For
each feasible package, a source-derived current-formula guide first chooses
an actual legal seed from the account, respecting occupied IDs. The complete
constant effect vector is obtained through the existing event/source model.
That one seed is evaluated directly in the shared parametric formula, without
first constructing a separate reduced search view for this package. Keep the
top32 such proposals, plus no-bonus/current search leader and every symbolic,
unknown, coordinate-incompatible or allocation-failed case. Only this reduced
list receives the normal detailed preparation, actual build screens, refinement,
joint work and final stabilization. The final DPS is the unchanged full model.

This is **exact arithmetic for a proposed seed, heuristic selection over all
possible builds**, not an upper-bound discard. It must be matrix-gated. It does
not use the user's equipped build as a privileged result. The shared evaluator
uses one dedicated model-owned scratch buffer and immutable source graph;
all input identities, latent constant ports and finite values are checked.
Existing source uncertainty is not erased; selected contexts export their usual
warnings. Symbolic effects are not silently frozen or called zero.

In this case the first two actor blocks cannot use the cheap scalar path and
retain all524 packages. The next six blocks score521/522 scalar packages each
and retain34/35 total packages at width32 (98/99 at width96). The eight cheap
prepasses together cost about12.2s. This is why it remains adaptive rather than
a named-set whitelist. Normal context requests fall5774→2377; source replays
remain249. `neutral_model.RuleSeconds` now excludes the new prepass's rule work:
do not misread its1.34s as all rule work becoming1.34s. Actual total search is
45.23s; detailed point-vs-bound-model parity is checked on all49 final builds in
a separate fresh process.

Point32 search retains about696MB of reserved Go heap in the end snapshot,
versus817.6MB for the width1-only sample. These are not process peak RSS and not
memory-limit proofs. Cumulative allocated bytes are churn, not live memory.

## Equivalence and safe-discard questions

- A+B and B+A are already one canonical package. On this inventory31 eligible2p
  sets give465 unordered pairs,31 solo2p,27 modeled4p and one no-bonus package:
  524 total. There is no missing factor-of-two optimization here.
- Equal bonuses can share arithmetic, but must not merge physical item pools.
  The family experiment collapses124 owner/set2p choices to32 observed numeric
  vectors on this team, after checking activation and interactions. These are
  not32 universal gameplay bonus types. It retains249 source replays,17 joint
  replays and144 merges; only224 symbolic compositions remain.
- Crit mass, useful-stat amounts and zero value at the current build cannot
  prove an item/set useless. Synthetic controls demonstrate the crit cap,
  a crit-rate set enabling a new crit-damage allocation despite zero gain on
  current gear, and weak pieces losing despite a larger full set bonus.
- Existing inventory-bound research uses actual item vectors rather than
  fictional maxima in every stat. Its small-domain exhaustive checks passed,
  but preparing bounds cost more than enumeration on the already reduced
  formulas. That machinery exists in the repository; it is **not** the active
  neutral real-candidate screen. A bound per item/context would add more such
  work, not remove it for free. Its float64 guards are not formal real-arithmetic
  interval certification. See `inventory_bound_poc_lineage5_v1.json`.

## Coverage of the player's suggestions and explicit non-results

| Suggestion | What was actually checked | Conclusion |
| --- | --- | --- |
| Do not enumerate A+B and B+A twice | Canonical package constructor and524-package inventory decomposition | Already implemented; no new saving to claim |
| Reuse numerically identical2p bonuses | Exact effect families after activation/dependency merging | Useful small saving; item pools remain separate |
| Simple2p is just a stat, not a complex event analysis | Source-derived scalar hints and strict direct-literal port construction with every-port parity controls | True for recognized forms; bypassing36 first replays is not the major cost |
| Begin with crit mass / useful rolls | Full saved-case CV and normalized useful-amount trials, plus cap/reallocation counterexamples | Does not beat formula priorities; useful-amount ordering loses top1 |
| Remove clearly weak pieces before permutations | Candidate-local top2/top4 per physical set/slot; tiny inventories retained | Top2 loses good results; top4 adds overhead without gain |
| Use an average or full bonus instead of detailed timing | Mean and observed-peak trials, with normal-model rescoring of every finalist | Little speed gain; peak ranking loses several thousand DPS |
| Rank bonus and actual available pieces before expensive preparation | Source-only simple2p preselection and whole-formula single-point preselection, both at32/96 | Whole-formula point screen gives the substantial extra gain |
| Capture one changed-set formula directly with n=1 | Four active-engine captures in prior wave | Blanket per4p capture loses on preparation cost; not a composable symbolic proof |
| Stop deeper permutations early | Narrow refinement, width1, sampled-gap cut, one-cycle cut, omitted single screens | Width1 promising here; stronger gap/cycle cuts damage lower top ranks |
| Cache more / avoid rebuilding already available data | Prior cache, immutable view, sparse effect and region-reuse waves, plus original-width exact control | Exact layers alone remove about31% without changing tested candidate sequence |

The peak trial does **not** implement a universal engine-derived theoretical
maximum for every4p, nor a pre-tracing upper-bound oracle. Conditional scalar
and stat-dependent/team-transfer effects cannot all be turned into an additive
maximum by ignoring branches. The strict source-only trial covers recognized
simple2p forms; unknown forms keep normal work. General arbitrary-rule maxima,
a new per-item-bound pilot, and a symbolic single-point interpreter remain
unimplemented extensions, not measured failures and not silently accepted
shortcuts. This finite experimental list does not prove a physical time optimum.

## Scope still outside this research acceptance

No installation, UI acceptance, new ordinary-finalist validation, Theory or
finite-energy-neutral acceptance. Earlier Navia/Flins/Bloom pairs concern the
older `combined_narrow_reuse` variant only:139.829→96.545s,143.461→88.983s,
90.719→73.004s respectively. The user accepts Bloom's rank7 −5.720792 DPS;
the first six remain unchanged. Those three rows do not accept newer variants
or replace the pending13 non-Gaming paired matrix. Gaming stays deferred.

Every completed managed job in this wave cleaned its owned scratch, including
the retained failed oracle attempt. The final combination job removed169880551
bytes and the adaptive confirmation removed120989652 bytes. The active engine,
installed consumer and native production source identities remained unchanged.
Only research templates/compact receipts and handoff projections were updated
in this wave; the earlier scoped replacement-geometry change remains separate.

Generated source copies, binaries, caches and logs belong to managed scratch;
retain compact receipts and reproducible overlay templates through integration
review, then retire rejected overlays. Keep failed attempts unchanged. No new
per-team gameplay state is shipped in a global cache.
