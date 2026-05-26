# Artifact Browser Equipment UX

Purpose: durable UX contract for future Artifact Browser equip/apply behavior
and ownership side-icon display. This is a design handoff only. No Artifact
Browser wiring or side-icon UI is implemented by this document.

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
  target for Artifact Browser;
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
make the operation target visually distinct with a clear target marker/highlight.

## Current Equipment Zone

Artifact Browser should have a top zone above saved presets for the current
operation target.

Suggested visible label:

- `Текущая сборка`

Rules:

- this zone is not an `artifact_build` preset;
- it represents the current live equipment of the operation target;
- it should reuse the same preview/presentation style as build preview where
  practical;
- if there is no single operation target, show a disabled/empty state and no
  equip actions.

When a saved preset is selected:

- the top zone switches to an action state, for example `Надеть пресет`;
- the preview area shows the selected preset;
- clicking the preset only previews/selects it, it does not equip immediately.

When the selected preset is deselected:

- if a single target exists, the preview returns to current equipment;
- otherwise it returns to an empty/placeholder state.

## Applying A Preset

Preset apply is explicit.

Action:

- button/action label: `Надеть пресет`;
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
  to `Текущая сборка`.

## Manual Artifact Equip

In equip mode:

- single click on an artifact equips that artifact to the operation target;
- this mirrors the in-game equipment page behavior;
- the artifact card already contains enough information, so click is not needed
  for a separate "view details" action.

Outside equip mode:

- artifact click does nothing;
- exception: preset-edit mode, where artifact clicks only edit the selected
  preset.

Manual artifact equip:

- uses `hoyolab_export.account_equipment.equip_artifact(...)`;
- does not mutate presets;
- updates current equipment;
- clears the temporary applied-preset label back to `Текущая сборка`.

## Conflict Confirmation

If a preset contains artifacts currently equipped by other characters, do not
block automatically. Show a compact confirmation.

Suggested text:

```text
Это изменит экипировку следующих персонажей:
[character icon] [character icon] [character icon]

Да / Нет
```

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

The AppShell weapon panel should later show equivalent owner side icons for
weapons.

Rules:

- weapon cards/list entries show side icon(s) for characters currently equipped
  with that weapon;
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

The next implementation stage can be:

Stage B2:

- build a runtime "current equipment artifact snapshot" from
  `account_character_equipped_artifacts`;
- feed it to right-panel stats and set-bonus calculation;
- do not create fake build presets for current equipment.

Later stages:

- Artifact Browser target-mode UI;
- current equipment top zone;
- preset apply button;
- artifact click equip;
- conflict confirmation;
- artifact owner side icons;
- preset owner side icons;
- weapon owner side icons.

## Non-Goals

This handoff does not implement:

- Artifact Browser equip/apply wiring;
- side icons in UI;
- equipment SQLite schema changes;
- build preset schema changes;
- AppShell behavior changes;
- live HoYoLAB import auto-apply behavior;
- `last_applied_build_id` persistence.
