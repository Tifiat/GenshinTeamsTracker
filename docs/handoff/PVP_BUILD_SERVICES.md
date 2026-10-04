# Scoped PvP build services

This checkpoint owns the current Artifact Browser and GCSIM preparation route.
Product direction stays in `PVP_UI_ROADMAP.md`; source/package ownership stays
in `PVP_PROFILE_PACKAGE.md`.

<!-- handoff-current: pvp-build-services -->
2026-10-04: Worker4's branch embeds the existing Artifact Browser independently
for each seat. It reads the seat inventory without source writes; artifact
ownership, swaps and saved-build application live only in match memory. Normal
account equipment, presets, deck files and the other seat remain separate.

The existing GCSIM Browser is also routed per seat for preparation only. It uses
the current seat controller and selected engine registry, explicit source DB
and disposable per-seat outputs. Preparing an empty scoped equipment selection
cannot borrow normal account gear. Simulation, optimizer, virtual roster and
save actions are unavailable in this route; authoritative Abyss-period admission
and executable scoped runs remain unfinished.

The package advances to v3 to retain the selected weapons' static display
effects/passive references. Old development v1/v2 archives require re-export.
Artifact-set display effects are rebuilt from packaged descriptions only in the
managed runtime DB. No full catalog or normal ownership is transported.

Verification uses temporary synthetic fixtures and headless widgets, documented
below. Physical smoke acceptance belongs to the user; Computer Use is forbidden.
No application launch, real-account capture, engine run or rules import occurred.

Next: user-owned build/profile acceptance, isolated second-account source and
usable rules sources; then authoritative-period admission before run dispatch.
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

## Focused verification receipt

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
   switching players. Execution remains unavailable pending period admission.
4. Change equipment and check that the old preparation report clears. Clear the
   match, keep the selected profile, start another match and verify empty runtime
   equipment. Close normally. Temporary cleanup is additionally covered by
   fixtures; do not delete source account files for this check.

This sequence is pending user execution and is not a passed physical smoke.
