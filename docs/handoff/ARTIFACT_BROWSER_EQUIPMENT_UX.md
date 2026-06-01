# Artifact Browser Equipment UX

Purpose: durable UX contract for Artifact Browser equip/apply behavior and
ownership side-icon display. AppShell embeds the browser as a left workspace;
operation target sync, current-equipment preview, manual artifact equip/unequip,
preset apply, conflict confirmation, selected-card highlights, and owner
side-icons are wired through persistent current-equipment state.

Related handoffs:

- `docs/handoff/ACCOUNT_EQUIPMENT_STATE_DESIGN.md`
- `docs/handoff/APP_SHELL_WORKSPACE_PLAN.md`
- `docs/handoff/DATA_RUNTIME_BOUNDARIES.md`

## Core Rule

Current equipment is not an `artifact_build` preset.

Current equipment is the canonical live per-character state stored through
`hoyolab_export/account_equipment.py`. Build presets are reusable definitions.
Applying a preset copies its artifacts into exactly one character's current
equipment state and does not mutate the preset itself.

## Target And Equip Mode

Artifact Browser has one operation target for equipment writes.

Equip mode is active only when exactly one character is the operation target:

- if a character is selected in the right panel, that character is the operation
  target for Artifact Browser and is initially synced as the browser's single
  selected character so its presets are visible immediately;
- if the user deselects that same character inside Artifact Browser, browser
  selection becomes empty for preset browsing, but the right-panel character
  remains as a secondary/background operation target for free artifact
  clicks;
- if the user selects another character in Artifact Browser while the
  right-panel target still exists, the browser shows the other character's
  presets while the right-panel target remains the operation target until that
  right-panel target is cleared;
- if no right-panel target exists, Artifact Browser may use its own character
  selection as the operation target;
- if Artifact Browser has zero selected characters or two or more selected
  characters, equip mode is off.

Behavior by mode:

- equip mode: clicking a free artifact equips it to the operation target;
- no equip mode: clicking a free artifact does not equip anything;
- preset-edit mode: clicking artifacts edits/constructs the selected preset and
  never changes current equipment.

Important UX warning: if the right-panel-selected character remains the
operation target while the browser is showing presets or filters for other
characters, artifact clicks still equip to the right-panel target. The UI must
make the operation target visually distinct with a clear target marker/highlight,
not with a long explanatory text banner.

## Current Equipment Zone

Artifact Browser should have a top zone above saved presets for the current
operation target.

Suggested visible label:

- the default current-equipment label

Rules:

- this zone is not an `artifact_build` preset;
- it represents the current live equipment of the operation target;
- it should reuse the same preview/presentation style as build preview where
  practical;
- if there is no single operation target, show a disabled/empty state and no
  equip actions.

When a saved preset is selected:

- the top zone switches to an apply-preset action state;
- the preview area shows the selected preset;
- clicking the preset only previews/selects it, it does not equip immediately.

When the selected preset is deselected:

- if a single target exists, the preview returns to current equipment;
- otherwise it returns to an empty/placeholder state.

Implementation status:

- `ArtifactBrowserWindow(embedded=True)` runs inside AppShell's left workspace
  without standalone close/window controls;
- AppShell passes the right-panel selected character as the browser operation
  target through a narrow adapter;
- the right-panel target is shown by the browser target selector's visual
  selected/highlight state, not by text like "target from right panel";
- right-panel target sync now auto-selects the matching browser character
  first; if the user deselects it in the browser, it remains visible only as a
  secondary operation-target marker and presets are hidden until browser
  selection is restored;
- when no right-panel target exists, the browser derives fallback equip mode
  from exactly one selected character target;
- the current-equipment zone shows live current equipment when a target exists;
- selecting a preset previews it and turns the zone into one large apply action;
- manual artifact equip/unequip and preset apply write through
  `hoyolab_export.account_equipment`;
- the embedded browser is calibrated for a compact minimum-width layout: one
  artifact `GRID_SIZE.width()` cell, narrower Assignment/target rows with
  a reserved portrait/icon zone plus marquee overflow text only in the name
  area, fixed preset/current-equipment panel, and JSON import/clear controls
  that do not force the artifact viewport wider than one grid cell. Current
  calibration is Assignment 144px, target row about 94px, and AppShell minimum
  about 1408px;
- divmod/remainder adaptive fit is implemented from the calibrated minimum
  layout. It consumes existing horizontal remainder into Assignment width as a
  preferred/current width and must not resize the top-level AppShell window;
- remaining geometry polish: artifact grid overlay scrollbar needs a small
  rightward visual offset while staying overlay-style. Horizontal resize twitch
  is considered system/environment live-resize behavior after the isolated probe.

Current/preset zone presentation:

- the current-equipment zone visually behaves like a compact preset row,
  not like a two-label form;
- when no preset is selected, show plain current-equipment text without a dark
  button background, followed by current set
  bonuses and the main-stat badge;
- there are no edit/delete buttons for the current-equipment zone because live
  equipment is always the edit target, not a saved preset definition;
- when a saved preset is selected, replace the non-clickable current label with
  an actionable equip-preset control;
- repeated click on the selected preset deselects it and returns the zone
  to current equipment;
- after manual artifact changes, the zone returns to current equipment/current
  preset text.
- Current implementation note: the applied preset label is only
  `ArtifactBrowserWindow.applied_current_equipment_label`, an in-memory browser
  field. It is not persisted per character and is cleared by target changes or
  manual artifact equipment changes.
- Future durable behavior: store the last applied preset marker per character
  (`character_id`, preset id/name, and enough slot snapshot/fingerprint data to
  validate it). Show `{preset}: {character}` across app restarts and character
  switches only while that character's live artifact equipment still matches the
  applied preset; clear the marker on any manual/current-equipment slot change.

## Applying A Preset

Preset apply is explicit.

Action:

- button/action label: use the localized apply-preset action text;
- target: exactly one operation target;
- implementation: call account equipment service operations for the preset's
  artifact slots;
- preset mutation: never mutate `artifact_builds`, `artifact_build_slots`, or
  `artifact_build_targets`.

Incomplete preset rule:

- applying a preset makes the target wear exactly what the preset shows;
- if the preset has only 3 of 5 artifact slots, applying it clears the target's
  missing slots.

Rationale: the user clicked "equip this preset", so the live equipment should
match the visible preset instead of silently preserving hidden old artifacts.

After applying:

- current equipment may temporarily show the applied preset name;
- that name is UI-buffer text only and is not persisted;
- do not add `last_applied_build_id` now;
- if the user manually changes any artifact after applying, reset the label back
  to the default current-equipment label.

## Manual Artifact Equip

In equip mode:

- single click on an artifact equips that artifact to the operation target;
- repeated click on an artifact already equipped by the operation target
  unequips it;
- this mirrors the in-game equipment page behavior;
- the artifact card already contains enough information, so click is not needed
  for a separate "view details" action.

Outside equip mode:

- artifact click does nothing;
- exception: preset-edit mode, where artifact clicks only edit the selected
  preset.

Manual artifact equip:

- uses `hoyolab_export.account_equipment.equip_artifact(...)`;
- uses `hoyolab_export.account_equipment.unequip_artifact(...)` for the repeated
  current-target click toggle;
- does not mutate presets;
- updates current equipment;
- clears the temporary applied-preset label back to the default
  current-equipment label.

## Conflict Confirmation

If a preset contains artifacts currently equipped by other characters, do not
block automatically. Show a compact confirmation.

Suggested text:

A concise localized confirmation should say that the apply action will change
the equipment of the following characters, then show owner side icons and
yes/no actions.

Rules:

- show icons only, no verbose character-name list;
- avoid repeated explanatory text;
- use the same compact side-icon style used elsewhere;
- if accepted, apply through the equipment service;
- if declined, leave current equipment unchanged.

## Artifact And Preset Owner Icons

Ownership display is derived from current equipment state.

Artifacts:

- an artifact card shows the side icon of its current equipped owner, if any;
- no owner means no side icon;
- source of truth: `account_character_equipped_artifacts`.

Presets:

- a preset card shows side icons for all characters currently wearing at least
  one artifact contained in that preset;
- source helper: `list_preset_current_wearers(...)`;
- source table: `account_character_equipped_artifacts`;
- do not derive these icons from `artifact_build_targets`.

Preset preview:

- each artifact inside the preset preview shows its current owner side icon;
- if several characters wear pieces from the preset, show all relevant owner
  icons on the preset card.

`artifact_build_targets` remains separate. It means "this preset is
intended/available for these characters", not "these characters currently wear
these artifacts."

## Weapon Owner Icons

The AppShell weapon panel shows equivalent owner side icons for weapons.

Rules:

- weapon cards/list entries show side icon(s) for characters currently equipped
  with that weapon;
- repeated click on the selected character's currently equipped weapon unequips
  it through `hoyolab_export.account_equipment.unequip_weapon(...)`;
- source of truth: `account_character_equipped_weapons`;
- use read helpers from `hoyolab_export.account_equipment`;
- owner side icons are UI/read-model presentation only.

For a `weapon_fingerprint` with `known_count > 1`:

- storage still has one fingerprint and multiple character assignments;
- UI may later render multiple identical visual weapon entries;
- each visual entry should show at most one owner side icon;
- avoid collapsing several equipped copies into one cluttered card with many
  icons when separate visual entries are practical;
- do not create fake weapon instance ids.

## Right Panel Relationship

The right panel selected character can drive Artifact Browser's operation target.

Rules:

- clicking an already-selected right-panel slot again clears that target;
- clearing the right-panel target disables Artifact Browser equip mode unless
  the browser itself has exactly one selected character target;
- the right panel can keep displaying current equipment/build stats;
- Artifact Browser should not call right-panel widgets directly;
- use shared controller/state plus `account_equipment` service helpers.

## Stage B2 Implication

Stage B2 is implemented:

- build a runtime "current equipment artifact snapshot" from
  `account_character_equipped_artifacts`;
- feed it to right-panel stats and set-bonus calculation;
- do not create fake build presets for current equipment.

The implementation lives in `hoyolab_export.team_card_data` and AppShell uses it
as selected-details runtime data for both right-panel display and embedded
Artifact Browser current-equipment preview/refresh.

## AppShell Embedding And Equipment Flow

Implemented behavior:

- AppShell has an `Artifacts` left workspace next to `Characters / Weapons`;
- the browser is created lazily on first workspace switch, so AppShell startup
  stays on the fast character/weapon path;
- right-panel target selection updates the embedded browser's target-selector
  highlight/current-equipment preview;
- clearing the right-panel target returns the browser to no-target or
  browser-selected-target state;
- artifact clicks in equip mode call `equip_artifact(...)` or
  `unequip_artifact(...)` for a repeated current-target click;
- preset apply writes through account equipment helpers, clears missing preset
  slots, and does not mutate preset tables;
- current equipment preview, selected-card highlights, owner markers, and the
  right panel refresh immediately after equipment changes;
- no fake `artifact_builds` rows are created.

Remaining/future stages:

- future weapon panel move/swap UI: if a weapon fingerprint has no available
  copy under `known_count`, the UI must require an explicit source owner/copy
  choice before moving or swapping; do not silently steal an exhausted assigned
  weapon by fingerprint.

## Non-Goals

This handoff does not implement:

- equipment SQLite schema changes;
- build preset schema changes;
- live HoYoLAB import auto-apply behavior;
- `last_applied_build_id` persistence.
