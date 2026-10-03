# Chasca user-run timing and result-card review — 2026-10-03

Read-only analysis of the completed application run
`all_sets-20261003-201232-82e3ec5d`, followed by a result-widget layout fix.
No new optimizer/capture/simulator run, application restart or physical UI click.

## Actual wall-time breakdown

| Work | Seconds | Evidence |
| --- | ---: | --- |
| Python input preparation, preflight and source inputs | 13.219 | `adapter-timings.json` |
| Neutral formula/search pipeline | 119.226 | `optimizer-output.json:search_seconds` |
| Ordinary finalist verification | 100.040 | `verification.total_elapsed_ms`; 35 candidates, n500, 9 waves |
| Other process/serialization work | 2.625 | Difference from adapter total |
| Complete application session | **235.110** | `adapter-timings.json:total_elapsed_ms` |

The search counter includes neutral capture, proposals, arithmetic preparation,
item search and finalist stabilization. Its proposal/rule/bind/replay counters
are nested work, not extra wall time to add again. Capture was about 14.310s
inside that search pipeline; source parsing was about 0.224s. Parsed-source cache
had 465 hits and zero misses/repairs/errors.

The actual request is ordinary, `fast_mode=false`, five groups and seven total
rows per group (leader included). This is 35 simulator checks, not five.
At this initial review the primary settings file also stored fast=false and
reported a September 27 write. The later
[settings audit](../2026-10-03-filter-hypotheses/README.md#why-the-request-was-5x7-rather-than-the-default)
retains the October 3 snapshot and distinguishes current counts from this saved
request. Neither analysis changed settings; historical choice provenance is
not reconstructed from a later file timestamp.

## Input and historical comparison boundaries

Against the retained, **cancelled** September 28 request
`all_sets-20260928-122321-984021c2`, the complete 597-item inventory, equipped-ID
lists, rotation, target, seeds and result options match. These weapon keys
change in the prepared team:

| Wearer | September 28 | October 3 |
| --- | --- | --- |
| Furina | `favoniussword` | `wolffang`, R5/90 |
| Ororon | `rainbowserpentsrainbow` | `thestringless`, R5/90 |

Chasca's Astral Vulture R1/90 and Bennett's Sapwood Blade R3/90 remain.
The prepared character declaration order also changes: Chasca/Furina/Bennett/
Ororon becomes Furina/Ororon/Chasca/Bennett. The Python slot builder preserves
the supplied team list, and the native context/reference renderer preserves
declaration positions. Request wearers themselves remain alphabetically sorted.
Party declaration order may affect GCSIM initialization/RNG/event ordering, so
this is not a controlled weapon-only comparison. No unordered-slot assembly bug
was found in the inspected preparation path.
The cancelled run stopped after 12.234s before formula/search timing existed;
it is not a successful fast baseline.

The [accepted historical Chasca exact-reuse experiment](../2026-09-28-player-hypotheses/search-frontier-attempt1.json)
records 91.355s search and 790,687 expansions. The current run records 119.226s
and 1,192,638 expansions: 30.5% more search time for 50.8% more trials.
This historical request hash differs from the current request, and its receipt
omits ordinary finalist simulations. It cannot establish a same-input speed
regression or a complete button-time comparison. Approximate elapsed time per
trial is lower in the new run, but capture/setup are included, so this is not a
clean per-evaluation benchmark. Future regression comparisons must preserve
the full prepared input, including party declaration order and output mode/
counts, then compare search and simulator time separately.

The current search prepares two 2,096 wearer/package cycles, reports zero
unavailable neutral models and stops at `neutral_cycle_budget`. This is bounded
search, not an exhaustive optimum and not a product wall-clock timeout.
Changed weapons can change both damage/stat dependence and which complete
builds receive further search. No new lost-build or arithmetic defect is proved
by this timing comparison.

## Engine and second-worker checks

The request binds the unchanged active engine
`gcsim-v2.45.0-20260927011932`, artifact prefix `7df37b52`, patch `154ba582`
and source manifest `9a2475aa`, under the primary checkout. The current installed
optimizer hash is
`e0bf5d64d6d6341fc434bf81f095e67e3e6a3d3ac43abf4fd7475a293bad6cf4`,
matching the accepted installation. This is a current binary check; the saved
run does not attest its own optimizer executable hash.

The Theory chat and its test subagent were inspected read-only. Their available
history contained source/document preparation, with no launched optimizer,
simulator or expensive test job at review time. No managed Theory run was yet
allocated. Settings paths are independent ordinary files in each checkout.
There is no evidence of second-worker compute contention causing this run;
historical machine load was not sampled and cannot be reconstructed generally.

## Result-card implementation and checks

`ui/gcsim_browser/optimizer_result.py` now gives the five artifact slots equal
expanding width instead of fixed 104px cards beside an unbounded action column.
The action column is 116 logical pixels; cards have a 170px minimum, 146px
leader height and 171px replacement height. Values/character names use 15px,
badges/headers/deltas 14px, with larger artifact and character icons.
Replacement columns stay aligned below the corresponding wearer and primary
slot. Existing save, page and independent-DPS-delta behavior is unchanged.

The five focused result tests pass at normal and forced 0.6 scaling. A temporary
four-character/four-substat render at 0.6 scale was inspected by both agents:
no clipped stats, aligned primary/replacement columns and bounded action width.
The render and its owning temporary process were cleaned.
Another 27 optimizer-UI/settings integration tests pass. This is 37 test
executions, not 37 distinct tests. New live appearance remains unverified and
requires reloading the already running application. No source/binary search
algorithm change or new numerical acceptance is claimed.
