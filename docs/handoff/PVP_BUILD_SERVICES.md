# Scoped PvP build services

This checkpoint owns scoped Artifact/GCSIM services and local period admission.
Product direction stays in `PVP_UI_ROADMAP.md`; source/package ownership stays
in `PVP_PROFILE_PACKAGE.md`.

<!-- handoff-current: pvp-build-services -->
2026-10-04: Worker4's branch embeds the existing Artifact Browser independently
for each seat. It reads the seat inventory without source writes; artifact
ownership, swaps and saved-build application live only in match memory. Normal
account equipment, presets, deck files and the other seat remain separate.

The existing GCSIM Browser prepares and dispatches selected/three-chamber runs
for each seat through the canonical browser workers. Requests capture the seat
DB/team/equipment, team half, selected engine and admitted period. Account gear
fallback is disabled. Optimizer, virtual roster and save actions remain hidden.
Cancellation, late-result rejection, bounded output ownership and deferred
imported-source cleanup are connected; verification uses fake executors only.

Play requires both profiles to match a current direct HoYoLAB period before
Draft. Decks export records its canonical start/end identity. Missing, fallback,
expired or mismatched provenance blocks admission with a refresh/re-export
message. Runs recheck admission and matching floor-12 source data; completion
rechecks the captured period and engine. Date-only precision is limited below.

The package advances to v3 to retain the selected weapons' static display
effects/passive references. Old development v1/v2 archives require re-export.
Artifact-set display effects are rebuilt from packaged descriptions only in the
managed runtime DB. No full catalog or normal ownership is transported.

Verification uses temporary synthetic fixtures and headless widgets, documented
below. Physical smoke acceptance belongs to the user; Computer Use is forbidden.
No application launch, real-account capture, engine run or rules import occurred.

Next: user-owned build/profile/engine acceptance, isolated second-account source
and usable rules sources. Online server authority, scoring/History/result export
remain later work. The existing timer header width failure is retained below.
<!-- /handoff-current -->

## Equipment contract

- Each match creates empty per-seat artifact and weapon ownership, even for
  identical game/artifact IDs. Source inventories stay read-only.
- Single-artifact clicks use the normal move/swap/unequip behavior. Preset
  application validates all references before changing ownership and clears
  unlisted slots. Equipment changes invalidate Ready, affected slot hydration
  and that seat's GCSIM preparation display.
- The ordinary Artifact Browser supplies inventory, filters, target selection,
  preset selection, conflict confirmation and stat previews. Source-edit,
  preset-save/delete, tag and JSON-import controls are unavailable in this
  read-only route. Separate JSON imports remain future work.
- Draft/build controls select the seat and open its retained browser inside the
  left Draft workspace. The shared normal Run panel still owns target slots;
  no top-level tab or replacement slot hierarchy is added.

## Preparation and output lifecycle

`PvpGcsimPreparation` wraps the canonical selected-team config builder. Team
indexes remain the seat's two teams, never a Player 1/2 discriminator. The UI
captures a fresh serialized team from that seat, passes current run settings
and resolves the selected engine registry on each request. Normal builder
callers retain account-equipment fallback; PvP explicitly disables it.

Each preparation adapter lazily owns an OS temporary directory, containing at
most two team directories with replaceable rotation/config outputs. Outputs
belong to the active match and are never written to normal GCSIM run folders.
Clear/restart, workspace close and app close release the browser and call the
adapter's idempotent cleaner. Profile replacement is allowed only after clearing
the active match. Profile source lifetime is
separate: clearing a match retains the selected imported provider, while provider
replacement/close removes only its managed files.

The UI retains separate rotation editors/reports for the two seats. Team,
weapon, artifact and rotation changes invalidate the affected preparation text.
Prepared configs are development diagnostics, not PvP scores, verified engine
results, authoritative-period evidence or History entries.

## Period admission and scoped execution

`period_admission.py` accepts only the captured direct
`hoyolab_spiral_abyss_overview` source, `fallback=False`, nonempty official source
path, no warnings, valid ISO dates and `start <= UTC today < end`. The period ID
is exactly `start/end`; no calendar-derived schedule, newest-cache selection,
Nanoka/Fandom fallback or client manifest is an authority. The producer has no
schedule ID or precise boundary timestamps/timezone. Date-only checks cannot
certify the exact reset hour; precise sub-day admission remains a producer gap.
Standalone package APIs still allow empty metadata, but Play rejects it. Existing
v3 archives without a matching period must be re-exported; no schema bump occurs.

An active draft freezes the admitted ID. Run admission and result delivery both
compare it, both providers and current authority; floor-12 cache start must match.
Team index 0/1 selects first/second half within either player's own teams.
Normal result converters store results only in that seat's in-memory controller.
They do not determine PvP scores or write normal Run/History/account state.

`PvpGcsimRunSession` owns one replaceable latest job tree per seat under an OS
temporary root. A single job contains at most three chamber subdirectories;
global PvP capacity is two active jobs, including cancelled jobs of cleared
matches. A new run replaces that seat's old output; invalidation cancels and
discards it. The cancellable runner polls every 100ms and kills/reaps its owned
direct process before cleanup. Clear/close stops polling and cancels; a reader
lease delays imported-profile deletion until the worker exits. The app-exit
weak registry also cancels old matches and shares a five-second join budget.
Cleanup failure preserves the owned reference for retry; normal source and unowned
paths are never cleanup targets. Closed/changed build generations cannot adopt
late payloads. Gear or rotation changes clear only that seat's saved results.

## Authority/dispatch verification receipt

2026-10-04, temporary synthetic sources and offscreen Qt; main-checkout dependency
interpreter reused read-only. Final scope:

| Scope | Cases | Result |
| --- | --- | --- |
| Period provenance/admission, canonical worker hooks, scoped runner/lifetime, preparation/config, package/schema regressions | 95 | 94 PASS; 1 host-limited symlink test SKIP (Windows privilege 1314) |
| Local/profile/build/period routing, scoped execution and normal GCSIM controls | 87 | 86 PASS; existing timer header-width assertion FAIL |
| Final cleanup-error fixes: scoped artifact/GCSIM/profile integration | 17 repeated | PASS |

The unchanged timer layout and width assertion reproduce independently:
`test_pvp_timers_table_fits_readable_width_or_scrolls_when_narrow` reports a
96px multi-target HP title against a 208px size hint. This remains a UI defect,
not a passed acceptance; the source timer widget was not changed in this stage.
Symlink creation is unavailable on this host; unowned-output preservation,
partial cleanup retry, process kill/reap and imported-reader lifetime pass.

Early fixture failures treated a deliberately deleted imported runtime as a
source to preserve and assumed imported metadata access for a local provider;
both assertions were corrected. A cleanup-error test also caught a misplaced
error accumulator in UI disposal; its initialization was moved to the actual
cleanup method, both adapters/seats are attempted, and the final focused rerun
passes. All actual engines/processes are substituted in these checks. No real
engine, application smoke, account capture/import or rules import occurred.

## Preparation/v3 verification receipt

2026-10-04, Worker4-owned temporary sources; dependency interpreter reused
read-only from the main checkout. Final focused checks passed:

| Scope | Cases | Result |
| --- | --- | --- |
| v3 schema/package/privacy, selected weapon effects and passive references | 29 | PASS |
| Scoped artifact ownership, read-only queries and shared snapshot construction | 20 | PASS |
| PvP preparation adapter and normal selected-team/account config regressions | 27 | PASS |
| Embedded PvP artifact and GCSIM routing, isolation, invalidation and cleanup | 7 | PASS |
| Profile/portrait integration and existing local flow, layout, drag/drop, clear | 13 | PASS |
| Normal AppShell artifact equipment and GCSIM/virtual-editor controls | 18 | PASS |

The first panel fixture exposed a misplaced `collapsed` visibility reference
(NameError); moving visibility to the existing collapse-aware path fixed it.
Fixture setup also needed valid set rows and explicit SQLite connection closes
on Windows. A later query-blocking assertion used an incorrect mocked function
name and was corrected; these fixture failures did not modify source accounts.
The weapon audit found and fixed missing imported display effects. An exploratory
nullable-refinement fixture was rejected by the existing Free Draft validator;
supported selected-stack fixtures pass. These checks do not establish real UI
acceptance, a real engine run, performance or accepted master integration.

## User-owned manual acceptance

1. Export a fresh v3 archive, import Player 2, complete Pick/Ban and assign teams
   and weapons. Select a character slot, open that player's Artifacts, equip
   items and apply a saved build. Verify the slot preview and source inventory.
2. Return to Characters/Weapons, repeat for the other player, and verify the
   first player's equipment, normal account equipment and saved builds remain
   unchanged. Compare imported set and weapon static bonuses where available.
3. Open each player's GCSIM, edit distinct rotations and prepare each team.
   Check the displayed team/gear and retain separate editors/reports when
   switching players. With matching current HoYoLAB/profile/cache data, run a
   chamber and all three for each team's half; verify separate player results.
4. Change equipment and check that the old preparation report clears. Clear the
   match, keep the selected profile, start another match and verify empty runtime
   equipment. Close normally. Temporary cleanup is additionally covered by
   fixtures; do not delete source account files for this check.

This sequence is pending user execution and is not a passed physical smoke.
