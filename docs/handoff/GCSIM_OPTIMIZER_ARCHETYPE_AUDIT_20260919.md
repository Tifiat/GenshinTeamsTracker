# Optimizer archetype audit — 2026-09-19

This is dated test evidence, not a second current checkpoint. Current acceptance,
limits and next action belong to [GP-3](GCSIM_GOB11_GP3_CHECKPOINT.md); the open
work belongs to [TODO](../../TODO.md). The compact machine log is
[`optimizer_archetype_full_matrix_lineage5_20260919.json`](../../tests/fixtures/gcsim_optimizer_go_v1/optimizer_archetype_full_matrix_lineage5_20260919.json),
with inputs in `tools/experiments/gcsim/mode_matrix/archetype_manifest_v1.json`
and its checked-in rotation text files. The runner uses the exact request and
session classes of all three UI buttons, a read-only account or authorized
test-only database copy, and managed scratch. Expanded captures are deleted on
exit; the receipt retains build summaries, result precision, formula-channel
coordinates, timing, proposal shortlist and source/engine identity.

## Real application route and its limits

The user's PyCharm `app_shell_smoke` Run Current File configuration used the
project `.venv` and opened `Genshin Teams Tracker - прототип App Shell`.
Computer Use clicked GCSIM > Artifact optimizer and then each **real** button
on Furina/Chasca/Bennett/Ororon with the saved Chasca rotation:

| Button | Visible outcome | Debug run |
| --- | --- | --- |
| Theory | Complete in 5:14; formula Top-1 172,467; five targets displayed | `theory-20260919-051711-5913d77d` |
| Selected Sets | Complete in 1:13; measured 155,658 DPS; five physical candidate pages displayed | `selected-20260919-052334-8d28f249` |
| All Sets | Complete in 2:55; measured 155,688 DPS; physical candidate pages displayed | `all_sets-20260919-052537-7f858b5f` |

The virtual Chasca editor replaced slot 2 with a catalog character and weapon,
without any saved artifact build. Another **real Theory click** completed in
5:12: formula Top-1 154,405, 42 source sets/3,612 packages/35 contexts,
five recommendations, `theory-20260919-053025-0de15afe`. This specifically
demonstrates that Theory no longer requires initially equipped pieces. The
virtual replacement was cleared and the original four account members restored
before closing the window. The UI artifact retention service removed earlier
expanded runs; these numbers are visual observations, not permanent full logs.
The compact fixture is separate backend/session evidence, not 28 physical UI
clicks. The smoke subagent independently launched the shell and opened the
optimizer on an empty team but did not claim a search completed there.

After the lineage5 activation and commit, a further native Computer Use check
used PyCharm's current-file Run control to launch the same AppShell entrypoint.
The fresh window showed GCSIM > Artifact optimizer, all three mode buttons and
the shared infinite-energy switch; it had four empty active-team slots. This
confirms that the current UI still opens, but **does not** establish a completed
lineage5 button search. The check's window was closed afterward.

The code route is `GcsimBrowserWorkspace._request_optimizer_mode` -> AppShell
`_on_gcsim_optimizer_requested` -> `GcsimBrowserSelectedOptimizerWorker` ->
`GcsimOptimizerGoSelectedSession` / `GcsimOptimizerGoAllSetsSession` /
`GcsimOptimizerGoTheorySession` -> `_on_gcsim_optimizer_selected_finished` and
the mode formatter. The managed matrix imports those same request/session
types. No retired Python optimizer is dispatched by these controls. This
checks the routing plus representative visible completions; it does not imply
every archetype was clicked individually.

## Source identity and measurement boundary

The fresh matrix uses GCSIM v2.45.0, cleanly applied eight-patch stack, engine
`gcsim-v2.45.0-observed-modifier-lineage5-20260919`, executable SHA256
`9d107ed713a171c64509ce35348c5d8f7bc08d81bea785db0f308b46d8869d50`,
patch manifest `680ec766adb897e423f933d9ae49e3ddef565d26edc8a70ee0b25b3dcfdb3275`
and source manifest `6d3d46da738259a269f1ffd92f7bf95e27f6c7c2b597aec750b13dace9d4a97e`.
Clean apply/build/compatibility activated lineage5; its byte-identical
lineage4 predecessor is the retained rollback and was the exact executable
used for the visible-button checks at that date; it is no longer the active
rollback pointer. All matrix rows request infinite energy;
this is not a fresh finite-energy or Selected-2+2 UI acceptance. Virtual
profiles are explicit research inputs, not the user's owned/leveled account
characters or weapons. All Sets chooses only owned physical artifacts; Theory
uses idealized roll allocations and does not measure ordinary n=500/1000 DPS.

## Confirmed failure class and diagnostic scope

Gaming/Citlali/Diona/Bennett has a large formula/ordinary divergence even
after the generic provenance repair. The controlled identical-final-build
two-seed capture in
[`gaming_melt_seed_panel_diagnostic_20260919.json`](../../tests/fixtures/gcsim_optimizer_go_v1/gaming_melt_seed_panel_diagnostic_20260919.json)
yielded 70,921 and 69,470 DPS with ten melted Gaming plunges in each seed;
ordinary 500 iterations yielded 58,647±523 DPS with only 5.882 melted plunges
on average. This isolates a non-representative two-seed reaction schedule in
that fixture, **not** a proven missing damage coefficient. Final ordinary
simulation protects the measured order of finalists it actually receives,
but formula-guided discovery may omit a stronger candidate. The fresh lineage5
run reproduces the large gap: 70,528 formula versus 58,556 measured DPS.

All Sets/Selected outputs are bounded and account-inventory dependent. A
surprising support set or elemental goblet alone is not a bug: inspect the
source-observed reaction and direct-hit coordinates, and compare actual n=500/
n=1000 outcomes before attributing a cause. Theory proposes 32 of 3,612
possible single-wearer package changes, then checks at most 40 formula contexts;
when the deadline fires it returns a labeled partial result. `undistinguished`
set slots mean the evaluated score did not distinguish those packages, not
that the corresponding character never contributed damage or buffs.

## Team-by-team results

All 28 rows completed successfully on the same lineage5 identity. `All` is
ordinary measured DPS, not its formula score: 11 winners used n=500 and
Gaming, Navia and Spread used n=1000 finalist iterations. `Theory` is *formula-only*
idealized DPS and must not be compared as a claimed equipped/ordinary result.
Times are complete product-session wall time in seconds. A dagger means the
300-second Theory context deadline returned a labeled partial shortlist.

| Team / tested mechanics | All DPS (s) | Theory formula DPS (contexts/40; s) |
| --- | ---: | ---: |
| Gaming/Citlali/Diona/Bennett: Melt plunge | 58,556 (87) | 94,927 (38; 98) |
| Navia/Xilonen/Ineffa/Columbina: Lunar Crystallize | 111,009 (280) | 157,717 (24; 314) † |
| Flins/Ineffa/Columbina/Jahoda: Lunar Charged | 108,107 (273) | 164,338 (21; 313) † |
| Columbina/Kuki/Lauma/Nahida: Lunar Bloom/Hyperbloom | 125,679 (252) | 161,673 (20; 314) † |
| Nilou/Kaveh/Nahida/Xingqiu: Bountiful Cores | 55,640 (167) | 69,762 (30; 314) † |
| Furina/Xilonen/Chiori/Columbina: dual-scale Geo/Lunar Crystallize | 90,369 (486) | 129,934 (11; 326) † |
| Kuki/Fischl/Nahida/Tighnari: Spread | 56,538 (178) | 91,806 (37; 288) |
| Keqing/Nahida/Fischl/Lan Yan: Aggravate/Swirl | 39,286 (144) | 63,349 (38; 246) |
| Bennett/Xiangling/Furina/Xingqiu: Vaporize | 76,463 (198) | 108,478 (33; 315) † |
| Freminet/Nahida/Xingqiu/Thoma: Burgeon/Shatter | 52,204 (138) | 64,601 (37; 241) |
| Kinich/Emilie/Dehya/Bennett: Burning | 71,147 (123) | 111,985 (38; 264) |
| Freminet/Xingqiu/Fischl/Mika: Physical/Superconduct | 42,058 (115) | 60,544 (37; 226) |
| Keqing/Chevreuse/Fischl/Thoma: Overload | 50,225 (113) | 72,219 (38; 207) |
| Sucrose/Beidou/Fischl/Xingqiu: Electro-Charged/Swirl | 52,919 (186) | 70,118 (27; 314) † |

The All Sets rows total 2,741 s (87–486 s each); Theory totals 3,781 s
(98–326 s each). One compact 1,029,146-byte JSON receipt preserves Top-5
artifact IDs, sets and main stats or theoretical roll allocations for every
row, formula channel/owner coordinates, mode warnings and execution times.
Expanded captures, the read-only account copy and child outputs removed
403,132,456 bytes on normal exit. The empty managed-scratch root retains only
its lifecycle lock. Across these 14 All Sets rows, final formula differed by
at most 1.11% from measured DPS except Burning (+3.85%) and Gaming (+20.45%);
the sign/denominator here is `(formula / measured) - 1`.

### Candidate and source audit

- Gaming's exact same final build, not a different artifact candidate, caused
  the severe seed discrepancy described above. Improving generic rank/recall
  requires a budgeted representative schedule, not another damage coefficient.
- Lunar Charged exposes both reaction `tag/26` and direct `tag/30` channels;
  Flins/Ineffa ATK and EM, Columbina HP and Jahoda EM appear as observed
  inputs. Hyperbloom `tag/23` depends on EM; the Lunar Bloom direct channel
  `tag/31` includes Columbina HP/crit/EM, Kuki ATK/EM, Lauma crit/EM and Nahida
  EM. All Sets Kuki/Lauma received triple-EM mains. The Bountiful-Core roster's
  observed Bloom `tag/20` includes Nilou HP and party EM; All Sets gave her
  HP/HP/HP. These
  bounded inputs refute a blanket claim that lunar or transformative stats
  were wholly dropped; they do not prove every branch.
- Chiori's personal Geo hits observe both ATK and DEF. All Sets gave her DEF
  sands, Geo goblet, crit circlet; Theory independently gave DEF sands. Lunar
  Crystallize `tag/27` in the Navia roster has Navia/Xilonen DEF and Columbina
  HP coordinates. The Chiori roster's `tag/27` lacks Chiori DEF: installed
  reaction source does not apply a universal all-Geo-DEF sum. Do not mistake
  Chiori's direct dual scale for that separate reaction channel.
- Vaporize direct-hit channels include Xiangling/Bennett EM. All Sets physical
  Xiangling chose ATK sands, while ideal Theory gave Xiangling **and Bennett**
  EM sands; inventory/crit/buff tradeoffs differ. Aggravate direct hits retain
  Nahida EM and multiple owners. Burgeon `tag/22` retains Thoma and Nahida EM.
  Overload `tag/11` observes Chevreuse/Keqing/Thoma EM; other direct-hit channels
  observe Chevreuse HP in Keqing/Fischl damage. Theory Thoma received 30 EM
  substat rolls despite ATK sands. Electro-Charged `tag/13` and Hydro/Electro
  Swirl `tag/16`/`tag/18` retain party/Sucrose EM, respectively.
- **Inactive bonuses selected as physical pieces:** All Sets chose Obsidian
  Codex 4p for Kuki (Spread), Bennett (Vaporize), Ineffa (Lunar Charged),
  Keqing (Overload) and Fischl (Physical/Electro-Charged). Its installed 2p
  requires the wearer's active Nightsoul Blessing; 4p requires their own
  Nightsoul consumption. Those wearers do not produce that state/event in
  these rotations. Freminet received Night of the Sky's Unveiling 4p in the
  Physical team, but its 4p hooks only lunar reactions; none occur. Burning
  Dehya received Noblesse 4p yet never uses Burst in that rotation. These are
  poor *set-bonus explanations*, not proof that the bounded finalist search
  miscomputed an item's raw stats. The owned pieces may simply be strong, and
  this bounded search did not prove a controlled no-worse alternative.
- Burning Top-1 gave Noblesse to Bennett, Dehya and Emilie. Installed source
  refreshes the same `nob-4pc` team key rather than stacking 20% ATK three
  times; Dehya never triggers it there. Nilou Theory Top-1 lists three
  Deepwood 4p wearers; installed source likewise reuses `dm-4pc`, so the
  resistance shred is not three independent -30% stacks. Either lineup might
  extend uptime; the result does not establish that duplicate sets are best.
- Theory evaluated only 11/40 contexts for Chiori and 20–33 for six other
  deadline cases. Its `sets: null` or UI “not distinguished” on a wearer is a
  bounded-search uncertainty, *not* proof the wearer has no beneficial set.
  In Physical, Fischl's Golden Troupe is seventh in her queued proposals,
  while Top-1 leaves her set undistinguished. The idealized 45-roll solver
  itself uses local main-stat/exchange steps, not exhaustive global search.

No current roster was found to set the upstream
`reactable.StellarConductEnableKey` gate. The installed code contains reaction
tags and consumers, but the present matrix cannot validate a reachable
Stellar Conduct producer or future mechanics. Ordinary Freeze/Crystallize
auras, amplified Melt/Vaporize and branch conditions do not necessarily emit a
standalone damage-reaction channel; absence of such a tag is not evidence that
the elemental interaction was omitted. Selected's four account-roster
controls are separately recorded in
[`optimizer_selected_fresh_matrix_v1.json`](../../tests/fixtures/gcsim_optimizer_go_v1/optimizer_selected_fresh_matrix_v1.json): Chasca 155,681, two Flins/Sucrose rotations 182,492/192,638, Bloom 124,097 measured DPS. That earlier capture did not bind the lineage5 engine fields, unlike all 28 rows here.

## Exact-input Flins contrast — 2026-09-19 follow-up

The 191,519 DPS user-account All Sets run and the 108,107 DPS virtual matrix
row are **different inputs**, not old/new measurements of one build. The
original user run is `all_sets-20260917-030320-7048d16f`; its saved prepared
config, rotation and inventory were matched exactly before the account rerun.
On the active lineage5 executable the account [compact receipt](../../tests/fixtures/gcsim_optimizer_go_v1/flins_jahoda_all_sets_lineage5_exact_recheck_v1.json)
reports 191,573 DPS (n=500, standard error 99; 485 s). Top-1 equips Flins with
Night of the Sky's Unveiling 4p and Ineffa with Silken Moon Serenade 4p. The
original user run measured 191,519 at n=1000 on the then-active installation;
the 54-DPS difference cannot establish a systematic regression. Its checked-in
[replay manifest](../../tools/experiments/gcsim/mode_matrix/flins_jahoda_exact_recheck_manifest_v1.json)
depends on that original retention-pinned run's rotation; preserve this source
until a self-contained exact-input fixture supersedes it.

The **actual anomalous virtual row** uses C0, talents 9/9/9 and the explicitly
listed R1 weapons/rotation in `archetype_manifest_v1.json`. Its earlier 108,107
DPS receipt and the fresh [108,128 DPS receipt](../../tests/fixtures/gcsim_optimizer_go_v1/flins_virtual_lunar_charged_lineage5_recheck_v1.json)
(n=500, standard error 142; 272 s) bind the *same lineage5 executable SHA*;
formula DPS is identically 106,931.845 and all Top-1 artifact IDs/sets match.
Ineffa still wears Obsidian Codex 4p; Flins still wears Silken Moon Serenade 4p.
Installed Obsidian source requires the wearer's own Nightsoul state/consumption,
which Ineffa does not supply here: the set bonus is inactive. Silken Moon can
activate its party EM and lunar-reaction bonus from Flins's elemental hit;
this support-carrier choice is legal. Neither fact proves that the bounded
search found the global best distribution or that it falsely credited Obsidian.
The [artifact-only cross-check](../../tests/fixtures/gcsim_optimizer_go_v1/flins_virtual_artifact_crosscheck_lineage5_v1.json)
now supplies that controlled alternative: on the same virtual C0/R1 9/9/9
profiles, unchanged rotation/target/weapon lines, infinite energy and active
lineage5, the original virtual Top-1 scores 107,980 +/-101 DPS, while the
account-run Top-1's twenty distinct, eligible 5-star IDs score 144,734 +/-128
DPS (ordinary n=1000 each). Both duration means are 72.467 s and the
non-artifact config hash matches. The +36,754 DPS (+34.0%) gap is far beyond
simulation error; the baseline reproduces the original 108,128 DPS within
ordinary sampling variation. **All Sets missed a much stronger legal build for
this virtual input.** The later stage audit below localizes a discovery loss;
forced-witness formula/item refinement remains a separate unchecked boundary.
A weaker result would not have proved the rotation defective,
since character profiles differ between the user and virtual runs. The
[ranking-quality TODO](../../TODO.md) now owns this diagnosis and fix.

These two compact recheck receipts remain
bounded comparison evidence until that gate is reviewed; the managed runner
removed 193,624,765 and 98,429,342 temporary bytes respectively, retaining
no expanded jobs. The one-off cross-check harness additionally removed 258,830
temporary bytes. Its small script/receipt stay as a reproducer until the
ranking-quality gate passes and then should be pruned or folded into focused
regression coverage. These are backend/session replays, **not** physical UI
clicks.

## Default All Sets stage localization — 2026-09-19

The [stage receipt](../../tests/fixtures/gcsim_optimizer_go_v1/flins_virtual_all_sets_stage_audit_lineage5_v1.json)
records a new, unmodified `GcsimOptimizerGoAllSetsSession` run through
`run_product_matrix._run_entry`, manifest team `lunar_charged`, infinite energy.
It uses the same request/session as the button, **not a physical click**.
The active lineage5 executable above is unchanged; installed standalone optimizer
SHA256 is `76c1a4f3cfdfc9c09c4ec9de831ce79d2c115a7a3b2cf6411320fafbe66f8aed`.
The receipt retains the exact prepared config, virtual profiles,587 inventory
entries' canonical hash, captured set contexts and all five returned ID maps.

- Top-1 has exactly the prior virtual witness's twenty IDs. Formula DPS remains
  106931.845194; ordinary n500 is107736.429315, SE151.043436. The n1000 controlled
  107979.658260 versus144733.524592 comparison above was inspected, not rerun.
- Search stops with `context_budget`:6 contexts (base plus5 new),12 capture
  members,3 guides,60 queued/55 pending proposals,5844 unqueued proposals
  accumulated across guides (not5844 unique sets). It uses335852 of1280000
  expansions. Search wall223.853s is below420s; native total255.158s.
- No captured context gives Flins Night of the Sky's Unveiling or Jahoda
  Viridescent Venerer. The stronger legal joint package (Night Flins, Silken
  Ineffa, Tenacity Columbina, VV Jahoda) therefore never reaches physical-item
  refinement or ordinary finalist verification. Increasing only product timeout
  cannot remove the independent hardcoded six-context ceiling.
- Two existing contexts are deepened after discovery. Neither improves its
  scout's formula leader. This does not prove the item solver globally optimal;
  it does rule out describing this run as simply unfinished due to wall time.

The first concrete failure boundary is
`cmd/gtt-optimizer/all_sets.go`'s fixed coordinator configuration plus
`internal/allsets/coordinator.go`'s `len(seen) >= MaxContexts` stop. Its input
priorities are already lossy: `guide.go` probes individual source constants in
the **old** graph, without activation/uptime proof; `hints.go` takes maxima,
including between2+2 components. `packages.go` allows only4p or distinct2+2,
not a free no-bonus package. Joint proposals transfer recognized literal shared
keys between two actors; they are not general joint set combinations. Exact
priority positions for the missed package were not saved in this new receipt.
Next controlled probes should force the legal witness package, then compare
exact-witness formula/ordinary response and same-package FGBS from a weaker
seed. Do not assert that all residual formula/item-search risks are exonerated.

Installed Obsidian2p requires the wearer's active Nightsoul Blessing and its4p
requires their own on-field Nightsoul consumption. Neither Flins nor Ineffa
activates these here. Source-constant hint probes can nevertheless credit
possible CR/damage. Fresh context capture and ordinary simulation do not use
that hint as damage. Thus the demonstrated defect is false **proposal benefit**
and incomplete search, not proof of phantom40% CR in reported ordinary DPS.
Keep the pieces eligible by raw stats.

### Theory and rotation cross-check

The retained lunar-charged Theory matrix row reports21/40 contexts (16 primary,
5 marginal) in313.453s; its32-entry queue contains no VV proposal for Jahoda.
Its first Flins proposal is Obsidian with heuristic priority5328.31, not measured
benefit. The separately user-reported22/40 run's expanded log is no longer
present; this audit does not substitute21 for that observation or claim to have
reproduced its exact27 Hydro/4 Electro-Swirl counts.

There is a concrete generic source-analysis gap: `seteffects/resistance.go`
accepts `Ele` only as a directly qualified constant. Installed
`internal/artifacts/viridescent/viridescent.go` passes the element through
`vvfunc(ele, key)` and `atk.Info.Element`, leaving that resistance opportunity
`source_element_unresolved`. More time cannot restore a set absent from the
32-proposal shortlist. Other VV effects and unresolved exploration still exist;
this is not a claim that the engine cannot simulate VV.

The exact manifest rotation has four loops and `jahoda attack, skill`, no Burst.
Installed Jahoda skill enters pursuit and schedules flask resolution itself;
with the relevant moonsign it emits an absorbed-element Meowball. Hydro direct
damage is compatible with this Anemo character's implementation. No rotation
syntax defect was established; the missing set is not evidence that her Hydro
or Swirl damage is impossible. The current Theory allocator is documented in
the Go design: greedy rolls, quarter-roll exchanges and bounded main-stat
cycles, not a converged continuous optimizer. Marginal removal can label a set
undistinguished without testing the many omitted alternatives.

No production source, binary, settings or equipment changed for this audit.
The managed job removed95529051 generated bytes and retains no expanded run.
This compact receipt belongs to the ranking-quality gate; fold it into focused
recall regression or prune it after that gate, rather than retaining captures.
At this audit stage major selection changes awaited the user's discussion; order
is All Sets, Theory, then Selected quality-preserving speed/polish.
The single `tests.tools.test_mode_matrix_proposal_witness` fixture-inspection
test passes; it does not rerun Theory or establish search recall. Handoff
structure/budgets/projections pass after compaction. No new full suite or
physical button acceptance is claimed.

## Limited inventory-bound concept — 2026-09-19

The user explicitly authorized the isolated concept test before optimizer-wide
changes. [Compact receipt](../../tests/fixtures/gcsim_optimizer_go_v1/inventory_bound_poc_lineage5_v1.json),
[managed runner](../../tools/experiments/gcsim/inventory_bound_poc/run.py) and
[Go overlay](../../tools/experiments/gcsim/inventory_bound_poc/bounds_test.go)
are temporary research, not an installed alternative backend. The current
decision/resume owner remains [GP-3](GCSIM_GOB11_GP3_CHECKPOINT.md).

The test uses the same active lineage5 executable/source/catalog as the product,
the manifest virtual Flins/Columbina/Ineffa/Jahoda profiles and rotation, infinite
energy and two fixed seeds. Other wearers keep the stronger artifact-only
witness's fifteen IDs. Only Flins's five slots vary. Restricted pools contain
up to four complete real vectors per slot, including the named witness; they
are a **test domain**, not a production candidate filter. Three separate full
team contexts are freshly captured (six engine calls total); no simulator is
called per candidate and no ordinary finalist or physical UI run is claimed.

| Flins domain | Legal combinations | Unique complete formula scores | Bound evaluations | Exhaustive / bound-search time |
| --- | ---: | ---: | ---: | ---: |
| Night of the Sky's Unveiling4p, flexible goblet | 576 | 20 | 271 | 0.505 / 0.441 s |
| Obsidian Codex4p, flexible circlet | 1024 | 28 | 179 | 0.789 / 0.295 s |
| Five distinct families, no2p/4p bonus | 1024 | 28 | 191 | 0.782 / 0.316 s |

All three best scores **and IDs** match full enumeration using the production
`evaluator.CompileMembers` scorer. Every enclosure used by search was checked
against every exhaustive leaf it contains: maximum observed upper-bound
violation0; reduced-graph point error at most5.82e-11 DPS. This is numerical
evidence over these finite domains, not a directed-rounding proof for every IR.
Search evaluated76 of2624 complete builds (97.1% fewer); checking bounds still
costs work, so the single-run warm timing gain against the **current full-graph
scorer** is only1.14-2.67x. Timings exclude
capture/compile and the separate exhaustive bound/parity audits; there is no
claim of this speedup for an account-wide or UI run.

There is a stronger counter-comparison: the separate parity pass evaluates
every leaf through the **reduced graph**, checks it against the saved oracle,
and takes only39.54/61.16/61.32ms. Even including those comparisons, it is much
faster than bound search's441/295/316ms on these small domains. Therefore the
concept passes finite-domain correctness, **not its practical efficiency gate**.
Fewer complete-build scores alone would misrepresent this result. Before
integration, measure the cost crossover and switch small remaining regions to
cheap exact reduced-formula enumeration; retain upper-bound pruning for regions
where its cost is justified. This is not yet implemented or account-scale proof.

Capture costs9.51/9.05/8.97s; combined production/experimental compile costs
0.54/0.53/0.53s. Common-subexpression sharing and fixed-wearer folding reduce
140985-144726 source nodes to2806-2965 nodes, with the point-parity check above.
Whole-domain upper gaps remain10.48%,27.72%,41.23%; unlike the independent-stat
box, joint vectors tighten the corresponding upper values from171206/185249/
212612 to162833/170365/180609 formula DPS. In particular, the Obsidian root bound
still exceeds the stronger Night domain's feasible147393 formula DPS: this
prototype **cannot discard that entire set domain from one initial estimate**.
Refinement is still needed. These are formula values, not new ordinary DPS
measurements and not a replacement for the earlier107980/144734 control.

Seven arithmetic-only checks pass: balanced10%CR/22%CD is retained and wins
against separate11.7%CR and23%CD extremes; a CR-capped case prefers23%CD despite
lower crit mass; 900-base10%ATK+20flat beats12%ATK; one excellent item among weak
ones is found; saturation/branch/cross-input arithmetic is enclosed; a two-slot
upgrade escapes a coordinate-local optimum (8/16 scores); a singular relaxed
interval remains unprunable. Toy constants are not gameplay implementations.
The last two controls were run separately with `--synthetic-only`, zero new
engine calls. Ten Python fixture/export/lifecycle tests pass, including unique
physical IDs, fixed set masks, zero-bonus families, no-overwrite/64KiB export
limits, cleanup, preservation, timeout and refusal after cleanup failure.

The first preparation attempt incorrectly assumed the free slot was always
the goblet; it stopped before Go/engine calls. Pool masks now derive the actual
off-piece slot from each saved witness. Its174321 bytes were cleaned; the real
proof cleaned109537784 bytes and the synthetic rerun62033141 bytes. All managed
jobs are gone. One42,343-byte receipt remains; the bound-integration decision
gate must fold it and the reproducer into focused regressions or prune them.

Limits: three fixed one-actor domains do not establish all-account set discovery,
activation/replacement certification, general free-item assignment, four-wearer
conflict handling, finite energy, schedule invariance or complete opaque input
ancestry. Matching topology in this fixture is not reuse authorization. The
production six-context miss and inactive set hint were still unfixed at this
isolated gate. No product code, active engine, standalone binary, equipment or
settings changed **during that proof**. The subsequently authorized integration
is described in the Go design; its [retained before/after comparison](../optimizer-evidence/all-sets-inventory-20260919/report.md)
preserves the supplied baseline and every post-change attempt. GP-3 owns its
current acceptance and the All Sets -> Theory -> Selected continuation.
