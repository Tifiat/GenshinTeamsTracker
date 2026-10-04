# H4 physical compatibility — complete-search gates, 2026-10-03

Owner: [GP-3](../../../handoff/GCSIM_GOB11_GP3_CHECKPOINT.md).
This extends the [isolated filter pilots](../README.md); their other hypotheses
and earlier failed receipts retain their original scope.

## Controlled search pairs

Saved application request: `all_sets-20261003-201232-82e3ec5d`, SHA256
`43db6218200f074fe182eaf66821f9b42e68f9fe39c07799f94e03fd3e65a6bf`.
Active engine: `gcsim-v2.45.0-20260927011932`, artifact SHA256
`7df37b5224f655d271d9389686bf22445717e02e896df5e3aa22d1d698042f8c`.

Both variants use ONE executable, the actual `optimize-all-sets` coordinator,
strictly bound saved active-engine captures, and the same request. Only
`result_options.fast_mode` changes from the original false to true, equally for
both. Five groups/seven total builds, weapons, inventory, rotation, seeds and declaration
order stay fixed. This is complete offline search, not fresh ordinary n500
verification, a matrix rerun, account reconstruction or physical button timing.

| Run order | Baseline search | H4 search | Saved |
| --- | ---: | ---: | ---: |
| [Baseline first](pair1.json) | 135.891s | 127.672s | 8.219s / 6.05% |
| [H4 first](pair2-reverse.json) | 144.566s | 138.572s | 5.994s / 4.15% |

All four runs return the same **35 physical builds and exact formula DPS**.
Every legally scored candidate is hashed in its original evaluation order;
all four traces match, not just the final top. Each has 1,187,017 traced scores,
1,192,638 search expansions and stop `neutral_cycle_budget`. That stop is a
bounded two-cycle search, NOT exhaustive inventory completion or a global
optimum. Source-cache and package-queue counters match; no work budget widens.

H4 removes known physically impossible visits before `point`: 6,205,182 calls
become 1,776,685. It prepares 2,388 tables, checks 382,631 family representatives,
skips 102,962 single visits and 4,325,535 pair visits, and uses no fallback on this
case. Preparation takes 0.411–0.464s. Cumulative allocated bytes fall by roughly
1GB; these Go counters are NOT peak RAM/RSS measurements. The improvement is
**4–6% of this search**, not2.6x whole-search or an under-three-minute promise.

## Why this cannot discard a stronger legal build

For a fixed wearer/team/package, physical legality depends on item slot,
ownership and physical set families, not stat strength. Check pool metadata once
and one representative for each family combination; keep every permissible ID
in its original order, including duplicate visits. Single failure must NOT
remove its pairs: another slot can restore the required bonus.

Only a 4p or distinct 2+2 requirement may fold outsider families together: a
legal five-piece build then has at most one outsider, which cannot create an
extra 2p bonus. Single 2p and no-bonus packages retain every physical family so
accidental extra bonuses remain forbidden. Strong off-set pieces are not deleted.
Surviving builds still pass the existing validator and unchanged damage formula.
No stat weights, crit-mass rule, unknown-effect assumption or response bound
participates in this filter.

Cancellation is checked during metadata, representative and row preparation.
Cancel/Finish returns no partial table and enters the existing result-retention
path. Malformed/unknown pool metadata instead falls back to original enumeration.
Fourteen synthetic controls cover legality, pair repairs, duplicate/order
preservation, incompatible pools, cancellation and fallback. They test physical
search rules, not gameplay response.

## Source transfer and product gate

The reviewed kernel was transferred to `internal/domain/neighborhood.go` and
the common `search.RefineCandidates` route. A focused Python test checks exact
equivalence of the transferred kernel to the tested research implementation
apart from names/comments; 50 Python research/adapter checks pass.

Fresh-capture real-adapter validation is owned by `promotion.py` and its
separate immutable [product-gate1 receipt](product-gate1.json). It compares
both installed/source-built modes before optional atomic publication, then
checks the default button path. It never opens an account DB or runs ordinary
finalists. Vet and all native package tests/build pass; the receipt does not
retain skip counts and does not certify previously disabled engine-response
controls.

**Passed and installed:** Selected returns seven exact rows; All Sets returns
35 exact rows, also identical to both controlled search pairs. Warnings match.
Fresh All Sets search is 144.530s installed baseline versus 139.338s candidate
(5.192s / 3.59% saved); each variant freshly captures the active engine rather
than replaying saved evidence. This is a third scope, not another same-capture
performance pair or an ordinary DPS validation. All Sets' formula winner remains
158,822.6228197032 DPS; the prior ordinary result is not relabeled as this estimate.

The tested/default-path installed optimizer SHA256 is
`76f8a52ca75146e320090775d02b61903e59dedaa74dc8f2cb006d662afa943c`;
previous installed consumer was `e0bf5d64d6d6341fc434bf81f095e67e3e6a3d3ac43abf4fd7475a293bad6cf4`.
The 2026-10-03 tested native build aggregate SHA256 is
`10c3f490eab2f778528d49ea18f8e4f86529b988f4c97428d85eb640c890ab97`
(sorted POSIX relative paths + NUL + bytes of all Go/mod/sum files, including
tests). GP-3 owns current installed acceptance. No new matrix, finite-energy,
changed-item response, ordinary finalist or physical UI acceptance is claimed.

The Selected gate retains the Sept28 Chasca request SHA256
`11532ecbe8925315e3f675c5b5680c72a7d32c2e1083a95d45af6e00927ab2ef`.
Fresh-capture installed/candidate comparison has 7 exact rows. Both do 37,543
evaluations, 8,546 candidate expansions and 28,997 stabilization evaluations;
six final single-stationary records and stop
`fixed_candidates_sampled_coordinate_pass_stable` match. Search 4.173s versus
4.562s does NOT establish a Selected speed gain or a changed work budget.
Work counters were read from the completed raw outputs while the managed job
was alive; their compact supplement is retained here, not in the JSON receipt.

Naming correction, 2026-10-04: the frozen Selected request above contains
Bennett, Chasca, Furina and Ororon, not Navia. The earlier checkpoint/manifest
label was wrong; input SHA256, receipts and measured results are unchanged.
The separate 2026-09-28 All Sets Navia gate retains its original identity.

## Reproduction and lifecycle

`whole_search.py` now pins only the pre-promotion candidate-loop source from Git
revision `bde62f972ac77c50bffcf6f54cd08beeb0558457` into a managed overlay.
It never rewinds the checkout or substitutes an engine. Its other current
source inputs and immutable saved capture provider remain hash-bound. Earlier
receipts record the executed prototype hashes and must not be rewritten.

Run `whole_search.py --run data/gcsim/optimizer-go-runs/all_sets-20261003-201232-82e3ec5d
--receipt <new-path-in-this-directory> [--reverse]` through
`tools/managed_optimizer_experiment.py --timeout 600 -- .venv/Scripts/python.exe -B`.
All overlays, build caches, captures, binaries, raw output and rollback bytes
belong to that managed job and are removed on success/failure; cleanup failure
blocks another job. The two pair jobs removed 89,980,665 and 90,102,163 bytes;
the product job removed 322,704,525 bytes. No job residue remains. This distinct
coordinator/promotion phase permits at most
**six immutable JSON receipts of 256KiB each** in this exact directory, with
no overwrite/escape. The parent pilot collection's separate finite budget and
small denied bytecode-cleanup residue are unchanged. Research copies are owned
by this phase, never product imports. Retire the physical-filter overlay and
one-shot mutation-capable promotion helper with compatibility-gated research
cleanup, preserving these receipts and the production regression tests.
