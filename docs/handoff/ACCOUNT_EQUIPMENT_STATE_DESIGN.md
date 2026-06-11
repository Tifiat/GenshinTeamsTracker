# Account Equipment State Design

Purpose: document the persistent account equipment state for AppShell,
Artifact Browser equip/apply, right-panel selected details, and owner side-icon
display.

Implementation status: Stage A is implemented in
`hoyolab_export/account_equipment.py` and initialized through
`hoyolab_export/artifact_db.py::init_db`. The schema and focused service helpers
exist, with tests in
`tests/hoyolab_export/account/test_account_equipment.py`. Stage B wires AppShell
weapon restore/assignment to this persistent state. Stage B2 builds a
runtime-only current-equipment artifact snapshot for right-panel stats/set
bonuses without creating saved build rows. Stage C embeds Artifact Browser in
AppShell and wires target/current-equipment preview, artifact equip/unequip,
preset apply, conflict confirmation, and owner side-icon read models through
the same service path. Artifact Browser equipment UX and ownership side-icon
rules are documented in `docs/handoff/ARTIFACT_BROWSER_EQUIPMENT_UX.md`.

## Scope

The model persists:

- current equipped weapon per account character;
- current equipped artifact per account character and artifact slot;
- in-game-like move/swap semantics;
- owner side-icon read models for artifacts, weapons, and presets;
- a clean boundary between saved build presets and current equipped state.

The model must not:

- mutate artifact build presets when the user equips or swaps items;
- treat HoYoLAB current-equipped observations as canonical user equipment;
- invent fake unique weapon instance ids;
- overwrite user-managed equipment during normal import without an explicit
  policy.

## Current Identity Audit

### Artifact Identity

Current artifact storage lives in `data/artifacts.db`.

Relevant tables:

- `artifacts`
- `artifact_substats`
- `artifact_builds`
- `artifact_build_slots`
- `artifact_build_targets`
- `artifact_equipment`

`artifacts.id` is the stable local primary key used by the existing Artifact
Browser and build preset slots. `artifacts.fingerprint` is unique and
source/import identity oriented. `artifacts.content_fingerprint` is the
source-independent structured fingerprint built from set, slot, rarity, level,
main stat, and substats.

Current import dedupes artifacts by `content_fingerprint` first when available,
then by `fingerprint`. In the inspected local DB there were no duplicate
`fingerprint` or `content_fingerprint` groups. Exact duplicate artifacts are
theoretically possible in the game, but the current storage cannot represent two
indistinguishable artifacts with identical structured content because they
dedupe to one row. Do not solve that inside equipment state; if duplicate exact
artifact copies become important, artifact import identity must be extended
first.

Recommended equipment reference:

- reference `artifacts.id`;
- keep artifact fingerprint/content fingerprint as recovery/provenance fields
  only if a future helper needs diagnostics;
- join side-icon owner display against the new canonical equipment table, not
  `artifact_equipment`.

Existing `artifact_equipment`:

- columns: `artifact_id`, `character_id`, `character_name`, `pos`,
  `imported_at`;
- primary key: `(character_id, pos)`;
- writer: `replace_current_equipment(...)`, which deletes all rows and rewrites
  observed current equipment from import;
- meaning: HoYoLAB import observation/provenance only.

`artifact_equipment` should not become canonical persistent equipment state
because normal import can replace it wholesale.

### Weapon Identity

Current account weapon storage lives in `account_weapon_observed_stacks`.

Relevant fields:

- `id` local row id;
- `weapon_fingerprint` unique stable stack key;
- `weapon_id` HoYoLAB weapon type id, not an account instance id;
- `rarity`, `level`, `refinement`, `promote_level`, `base_atk`,
  `secondary_property_type`, `secondary_stat_value`;
- `icon_path`;
- `known_count`.

`weapon_fingerprint` is built from weapon id, rarity, level, refinement,
promote level, base ATK, secondary stat type, and secondary stat value. It
explicitly excludes equipped character, localized name, description, icon path,
and source row order.

The inspected local DB had 66 observed weapon stack rows with total
`known_count = 73`; four stacks had `known_count > 1`. Therefore equipment
state must allow multiple characters to reference one stack only up to
`known_count`.

Recommended equipment reference:

- reference `account_weapon_observed_stacks.weapon_fingerprint`;
- keep `account_weapon_observed_stacks.id` as a local convenience only if
  helpers need it;
- do not invent weapon copy ids.

Identical weapon copies inside one stack are indistinguishable. Equipment state
can know "N characters are using N copies from this stack"; it cannot know which
physical copy each character owns.

### Character Identity

Use `account_characters.character_id` as the equipment key.

Reasons:

- it is the authoritative HoYoLAB/game account character id;
- AppShell persistent equipment wiring keys by character id;
- `artifact_build_targets.character_id` already uses this identity;
- HoYoWiki entry ids are catalog/reference ids and should not own account
  equipment.

### HoYoLAB Current-Equipped Observations

Existing observations:

- `artifact_equipment` records observed artifact wearer by character/slot at
  import time;
- `account_weapon_observed_stacks.source_metadata_json` may include
  `observed_character_ids` and source equipped character ids from
  `account_weapons.json` / detail rows.

These observations are useful for provenance, first seed, or an explicit sync
action. They are not canonical current equipment state and should not overwrite
user-managed equipment during normal import.

## Proposed SQLite Schema

Stage A implementation creates these tables through the normal artifact DB
initialization path.

### `account_character_equipped_artifacts`

Canonical current artifact state.

```sql
CREATE TABLE account_character_equipped_artifacts (
    character_id INTEGER NOT NULL,
    slot_key TEXT NOT NULL,
    artifact_id INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    source_import_batch_id TEXT,
    observed_at TEXT,
    updated_at TEXT NOT NULL,

    PRIMARY KEY (character_id, slot_key),
    UNIQUE (artifact_id),
    FOREIGN KEY (character_id) REFERENCES account_characters(character_id),
    FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE,
    CHECK (slot_key IN ('flower', 'plume', 'sands', 'goblet', 'circlet'))
);
```

Implementation helper must validate that `slot_key` matches `artifacts.pos`:

- `1 -> flower`
- `2 -> plume`
- `3 -> sands`
- `4 -> goblet`
- `5 -> circlet`

The `UNIQUE (artifact_id)` invariant means one artifact can be currently worn
by at most one character.

### `account_character_equipped_weapons`

Canonical current weapon state.

```sql
CREATE TABLE account_character_equipped_weapons (
    character_id INTEGER PRIMARY KEY,
    weapon_fingerprint TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    source_import_batch_id TEXT,
    observed_at TEXT,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (character_id) REFERENCES account_characters(character_id),
    FOREIGN KEY (weapon_fingerprint)
        REFERENCES account_weapon_observed_stacks(weapon_fingerprint)
);
```

Do not add a uniqueness constraint on `weapon_fingerprint`, because one stack can
represent multiple indistinguishable copies. Enforce this invariant in write
helpers:

```sql
COUNT(account_character_equipped_weapons.weapon_fingerprint)
<= account_weapon_observed_stacks.known_count
```

If strict DB-level enforcement is later desired, use triggers. Start with helper
validation and tests because it is easier to reason about swaps.

### `account_character_equipment_state`

An umbrella state table is not necessary for the first implementation. The
weapon and artifact tables are sufficient and easier to query. Add a small
metadata table later only if the app needs account/profile scope, state version,
or global import/sync status.

## Equipment Semantics

All operations below update current equipment state only. They never mutate
`artifact_builds`, `artifact_build_slots`, or `artifact_build_targets`.

### Equip Artifact

Input:

- target `character_id`;
- `artifact_id`;
- slot inferred from `artifacts.pos`.

Rules:

1. If the artifact is unequipped:
   - target receives the artifact in that slot;
   - target's previous artifact in that slot becomes unequipped.
2. If the artifact is equipped by another character:
   - target receives the artifact;
   - previous owner receives target's old artifact in the same slot if target
     had one;
   - if target had no old artifact in that slot, previous owner's slot becomes
     empty.
3. If target already wears that artifact, operation is a no-op.
4. Presets are not changed.

### Unequip Artifact

Input:

- target `character_id`;
- slot key or artifact id.

Rules:

- target slot becomes empty;
- artifact becomes ownerless;
- presets are not changed.

### Equip Weapon

Input:

- target `character_id`;
- `weapon_fingerprint`;
- optional `source_character_id` when the UI is moving a copy from a specific
  current wearer.

Rules:

1. Validate weapon type compatibility against `account_characters.weapon_type`
   and `account_weapon_observed_stacks.weapon_type`.
2. If target already has this stack, operation is a no-op.
3. If assigned count for that `weapon_fingerprint` is lower than `known_count`:
   - target receives one available copy from the stack;
   - target's old weapon becomes available.
4. If assigned count is at `known_count`:
   - plain `equip_weapon(...)` fails with a controlled no-available-copy error
     unless the target already uses that stack;
   - do not implicitly steal a copy by fingerprint alone.
5. If the UI is moving an already equipped copy, use an explicit source-owner
   helper such as `move_weapon_between_characters(...)`.
6. If target had an old weapon and source is moved from another character:
   - source receives target's old weapon if compatible;
   - if incompatible or target had no old weapon, source becomes empty.
7. Do not fabricate instance ids.

### Unequip Weapon

Input:

- target `character_id`.

Rules:

- target weapon row is deleted;
- the stack count becomes available for another character.

### Equip Artifact Preset

Input:

- target `character_id`;
- `build_id`.

Rules:

- target exactly one character;
- read `artifact_build_slots` for that preset;
- for each present slot, apply normal Equip Artifact semantics;
- do not mutate the preset.

Missing-slot behavior:

- applying a preset makes the target wear exactly what the preset shows;
- if the preset has only 3 of 5 artifact slots, applying it clears the target's
  missing slots.

Reason: the Artifact Browser action is "equip this preset", so hidden old
artifacts should not silently remain on the target after the user accepted the
operation. See `ARTIFACT_BROWSER_EQUIPMENT_UX.md` for the UI copy and conflict
confirmation model.

## Preset vs Equipped State

Artifact build preset:

- reusable definition;
- can target Universal and/or many characters;
- can be previewed or selected by multiple characters;
- does not imply current ownership.

Equipped state:

- current wearer mapping;
- one artifact can be worn by at most one character;
- weapon stack assignments must respect `known_count`;
- changes only through explicit equip/unequip/apply actions.

"Free preset" model:

- each character's persistent equipment state is their live/free build;
- equipping a saved preset copies preset artifacts into that character's live
  equipment state;
- later manual equip changes alter the live/free state, not the saved preset.

## Side-Icon Ownership Display

### Artifact Icon Owner

Read model:

- join artifact card/list rows to `account_character_equipped_artifacts`;
- join owner to `account_characters.side_icon_path`;
- if no equipment row exists, show no owner side icon.

### Weapon Icon Owners

Read model:

- join weapon stack rows to `account_character_equipped_weapons`;
- show owner side icons for all characters currently consuming copies from the
  stack;
- if one wearer, show one icon;
- if multiple wearers, show multiple small icons or a compact overflow count.

If multiple owners exist and the user wants to move an already consumed copy,
the UI should let them choose a specific owner icon. That owner becomes
`source_character_id` for swap/move semantics.

### Preset Side Icons

Preset row owner icons should be derived from current equipment state, not from
`artifact_build_targets`.

Read model:

```sql
SELECT DISTINCT equipped.character_id
FROM artifact_build_slots AS slots
JOIN account_character_equipped_artifacts AS equipped
    ON equipped.artifact_id = slots.artifact_id
WHERE slots.build_id = ?
```

If five different characters each wear one artifact from the preset, the preset
row can show those five characters, with an overflow display if needed. Opening
the preset should still show per-artifact owner icons.

### Build Target Metadata Remains Separate

`artifact_build_targets` means "this preset is intended/available for these
characters." It does not say who currently wears the pieces.

Equipment state means "who actually wears these pieces now." It does not change
which targets the preset is intended for.

## AppShell And Artifact Browser Integration Plan

### AppShell Startup

AppShell now loads persistent weapon state from SQLite into the controller/view
model. The old session weapon map is no longer the source of truth.

### AppShell Character Added To Slot

When a character is quick-picked into a slot:

- read current equipped weapon from `account_character_equipped_weapons`;
- read current equipped artifact ids from
  `account_character_equipped_artifacts`;
- attach current weapon to the slot and selected-details model;
- attach current artifact ids as read-only `current_equipped_artifact_ids_by_slot`
  metadata;
- convert those ids into a runtime-only current-equipment `ArtifactBuildSnapshot`
  for right-panel artifact stat and set-bonus display.

This runtime snapshot is built from persistent current equipment rows and
existing artifact ids. It is not saved as an `artifact_build` row and does not
mutate saved preset definitions.

### AppShell Character Removed From Slot

Removing a character from the current team slot should not delete persistent
equipment. It only clears the team slot.

### Re-Adding Same Character

Equipment should reappear from persistent state, not from an in-memory session
map.

### Artifact Browser

If selected build target is `None`:

- browse-only;
- no equip/apply writes.

If selected build target exists:

- explicit equip/apply actions can update persistent equipment state;
- selecting a preset is only preview/selection;
- "equip preset" must be an explicit action targeting exactly one character.

Detailed UX contract:

- the right-panel-selected character is the operation target when present;
- if there is no right-panel target, the browser may use exactly one selected
  browser character target;
- 0 or 2+ browser-selected characters means equip mode is off;
- the top current-equipment zone is UI presentation over current equipment, not
  an `artifact_build` preset;
- selecting a preset changes the top zone to the apply-preset preview/action
  state;
- applied preset name is temporary UI-buffer text only and should reset to the
  default current-equipment label after manual artifact equip;
- artifact/preset/weapon owner side icons must be derived from current
  equipment tables, not from preset target metadata.

See `docs/handoff/ARTIFACT_BROWSER_EQUIPMENT_UX.md`.

## Import / Sync Relationship

HoYoLAB can observe currently equipped artifacts/weapons, but the project should
prefer non-destructive behavior.

Current Stage A policy:

1. Isolated helpers exist:
   - `apply_hoyolab_artifact_equipment_observation(...)`
   - `apply_hoyolab_weapon_equipment_observation(...)`
2. These helpers call the same service as manual equip actions and set
   `source='hoyolab_import'`.
3. They are not wired into live import yet.
4. Missing HoYoLAB character/slot/equipment data means "no data" and must not
   clear local equipment.
5. A future setting should be able to disable automatic application of HoYoLAB
   equipment observations during import.

Tradeoffs:

- applying explicit observations gives the local state a useful starting point;
- the missing-data rule avoids accidental destructive clears from partial
  payloads;
- a future disable-auto-apply setting protects user-managed planning/equip
  changes when the user does not want HoYoLAB observations applied.

## Migration Path

Stage A: storage foundation - implemented 2026-05-26

- SQLite tables are created by `init_db`;
- read/write helpers live in `hoyolab_export/account_equipment.py`;
- tests cover artifact equip/unequip/swap, weapon equip/count validation,
  explicit weapon move/swap, import observation helpers, missing-data
  non-clearing behavior, and preset wearer read models.

Stage B: AppShell equipment persistence

- implemented 2026-05-26;
- transitional AppShell session weapon memory is replaced by persistent helpers;
- weapon assignment uses `equip_weapon(...)` and respects type/`known_count`;
- character add restores persistent current weapon;
- character remove does not delete equipment;
- current artifact ids are restored read-only into details metadata;
- artifact-derived stats/display are deferred.

Stage B2: current artifact live snapshot - implemented 2026-05-26

- `hoyolab_export.team_card_data.build_current_equipment_artifact_snapshot(...)`
  reads `account_character_equipped_artifacts`, reuses
  `calculate_raw_build_summary(..., slots=...)`, and returns a runtime-only
  `ArtifactBuildSnapshot` with `build_id=None`;
- AppShell attaches that snapshot to selected details so current artifact
  main/sub stats and direct static set effects can appear in the right panel;
- missing artifact rows are skipped softly with a warning instead of crashing
  the shell;
- saved build/preset tables are not created or mutated;
- Artifact Browser equip/apply is wired separately through the same service
  helpers and must keep preset definitions immutable.

Stage C: Artifact Browser embedded target UI and equipment writes - implemented

- AppShell has an `Artifacts` left workspace that lazy-creates embedded
  `ArtifactBrowserWindow(embedded=True)`;
- the embedded browser reflects the right-panel selected character as the
  operation target;
- when the right panel has no target, exactly one browser-selected character
  can become the scaffolded operation target;
- the current equipment top zone previews live current equipment;
- explicit preset preview and equip-preset action are wired;
- incomplete presets apply as exact contents, clearing missing target slots;
- compact conflict confirmation appears when preset artifacts are worn by other
  characters;
- artifact card owner icons, weapon stack owner icons, preset row owner icons,
  and preset-preview owner icons are derived from current equipment;
- browse-only/no-target mode does not write equipment;
- manual artifact click equips in equip mode and repeated current-target click
  unequips.

Stage F: HoYoLAB seed/sync

- optional application of explicit observed equipment through the Stage A
  helpers;
- future auto-apply setting;
- never clear local equipment from missing HoYoLAB payload data.

## Risks And Open Questions

- Weapon stack ambiguity: when all copies are consumed and multiple characters
  wear the same stack, the UI must identify which owner is being moved.
- Duplicate indistinguishable weapons: the model can track count usage, not
  physical copies.
- Duplicate indistinguishable artifacts: current artifact import dedupes exact
  structured duplicates, so true duplicate artifact copies are not represented.
- Incomplete preset behavior: the current UX decision is exact apply, so missing
  preset slots clear target slots. The UI should make the selected preset
  preview obvious before confirmation.
- Missing/deleted artifacts: if an artifact row is removed, cascading deletes
  should clear equipment references; UI should show a clear missing item warning
  if helpers preserve tombstones later.
- Missing/deleted weapon stacks: if an observed stack disappears from storage,
  equipment helpers should either block deletion or surface an invalid reference
  repair state.
- Import refresh: normal import should not overwrite canonical equipment;
  explicit sync policy is still needed.
- Account/profile scope: if multi-account/profile support appears later, these
  tables need an account/profile key before they can safely support more than
  one account.

## Documentation Status

Stage A schema/service foundation is implemented. This document remains the
source for Stage B+ wiring decisions. Artifact Browser UX details live in
`docs/handoff/ARTIFACT_BROWSER_EQUIPMENT_UX.md`.
