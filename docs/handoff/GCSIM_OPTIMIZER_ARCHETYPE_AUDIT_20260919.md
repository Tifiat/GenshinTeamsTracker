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
used for the visible-button checks. All matrix rows request infinite energy;
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
ordinary measured n=500 DPS, not its formula score; `Theory` is *formula-only*
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
  poor *set-bonus explanations*, not proof that the final n=500 search
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
