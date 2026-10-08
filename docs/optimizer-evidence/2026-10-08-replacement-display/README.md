# Chasca replacement display and timing audit — 2026-10-08

Source-only presentation change. Main's installed search, engine and scoring
are unchanged. The original optimizer owner works in the isolated repair
checkout; target transfer requires a separate reviewed Git authorization.

## Display policy and checks

The human requested three visual levels rather than red labels for tiny losses.
Losses up to250 DPS use green “Практически равно” without a number; losses
over250 through600 use amber “Малая разница: … DPS”; larger losses retain red
numeric DPS. Gains stay green. Formula estimates retain “≈”. The existing
custom tooltip explains that250/600 is a presentation heuristic, not a sampled
confidence interval. No score, rank, candidate, raw difference or search changes.

Focused offscreen result tests pass6/6, covering both bases, threshold edges,
gains, single-item independence and the170x171px minimum card. Tooltip/binding
tests pass68/68 against an owned empty synthetic catalog, with the expected
missing-owned-set warning. No physical UI, app launch, GCSIM or account writes.
All managed jobs were removed. Initial harness attempts are not hidden: first
SQLite setup used tuple rather thanRow results and stopped before tests; the
next tooltip assertion expected a non-contiguous English phrase and failed.
The final assertion checks the actual reviewed confidence/error-bar meaning.

## Read-only user-run audit

The completed Oct8 Chasca/Furina/Bennett/Ororon runs have the same597-item
inventory, prepared input, rotation, target and engine artifact. Their actual
settings are normal mode, All3groups with3total rows each, Selected1group with
3rows: the user's “3+2” means base plus two swaps, hence9 versus3 n500 checks.
No product timeout was active. Main's consumer identity is not attested by the
saved requests themselves; engine artifact is7df37b52 and the installed main
consumer was separately verified asdd84139e.

| Stage | All Sets | Selected |
| --- | ---: | ---: |
| Python preparation/preflight/formula-input boundary |15.657s|8.844s|
| Native search pipeline |117.104s|3.586s|
| Ordinary verification |38.834s (9x500)|11.556s (3x500)|
| Remaining compile/process/serialization |2.937s|3.655s|
| Full session |174.532s|27.641s|

All ran two neutral cycles,996240 expansions and stopped at its configured
cycle work budget, not a time limit. Parser465hits/zero misses and two captures
do not support a repeated engine/source-parsing explanation. Nested rule,
binding, replay and proposal counters must not be added to total wall time.
The bounded search is not an exhaustive/global-optimum certificate.

Current-main source review selects `RunNeutral` in `cmd/gtt-optimizer/all_sets.go`,
not the legacy `allsets/coordinator.go` capture/refine route. One neutral model
and one two-seed capture panel serve the broad package/item search; result
group counts do not multiply searches. Model resolve dispatch/program caches
and schedule-context caching are connected. The source and recorded counters
show no per-group capture/compile or old128/500/1000 verification ladder.
Selected recorded39,258 evaluations within its160,000 work limit and stopped
at stable coordinates. All's two-cycle stop is explicitly bounded/incomplete.

One narrow output-side redundancy remains: the archive retains several rows per
bonus group, whereas `allSetReplacements` keeps one anchor and rescans single-
item neighbors. Possible overlap with already scored search points is not
measured. This is outside the117.104s core search and cannot explain that cost;
only about1.649s of native product wall time remains after search/verification.
It is not evidence that the selected anchor or physical assignment is wrong.

## Cube order and attribution

The same physical builds occur in All's bonus group2 and Selected's group1.
Match by the ordered physical20-item assignment, never product display rank:
verification rank is the original input order. An initial diagnostic joined
those ranks incorrectly; its hash/table mismatch was retracted before any
code change. Corrected finalist configs differ only in the workers option;
artifact stats, actors, weapons, rotation and target match.

| Ororon goblet | All measured DPS (SE) | Selected measured DPS (SE) |
| --- | ---: | ---: |
| ATK46.6% |155512.916 (93.987)|155489.248 (94.474)|
| Electro46.6%, candidateB |155353.358 (97.747)|155501.651 (93.180)|
| Electro46.6%, candidateC |155344.089 (94.302)|155552.979 (96.415)|

The ordering follows each run's measured mean; cross-run differences are
compatible with independent sampling variation (below1.6 combined standard
errors), not a proven noise cause. All-vs-Selected formula differences132–138
DPS remain a disclosed reference/effect-model difference, not equal-formula
acceptance or a demonstrated lost stronger build. No claim of all bugs absent.

The next representative public fixture is prepared separately under
`tools/experiments/gcsim/chasca_regression/`. Its first measurement must be
shown to the human before adding an automatic golden or performance assertion;
no full-account Chasca timing baseline is installed by this UI change.

Git intent: save only these independently verified display/localization/tests
and this scoped receipt as a local commit from source7770b52. Unrelated profile,
policy, source safeguard, research, benchmark prototypes and runtime changes
are excluded. No transfer, engine update or push is implied.
