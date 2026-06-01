# Account SQLite Storage Handoff

Purpose: document the clean local SQLite account tables used as runtime inputs
for future TeamBuilder/stat recalculation. Raw HoYoLAB JSON files remain
source/cache inputs and are not deleted.

## Storage Location

Use the existing local SQLite DB:

- `data/artifacts.db`

Schema initialization lives in:

- `hoyolab_export/artifact_db.py`
- `hoyolab_export/account_storage.py`
- `hoyolab_export/account_equipment.py`

Normal HoYoLAB import updates these tables automatically after the raw
HoYoLAB JSON/cache files and crop manifest have been written:

```powershell
.\.venv\Scripts\python.exe -m hoyolab_export.run_import
```

During normal import, missing side icons are cached from already-known
HoYoLAB `side_icon` URLs and existing valid local icon files are reused. Account
SQLite sync failures are reported as import warnings after the raw import, but
do not delete the refreshed raw JSON/artifact results.

Manual/debug no-network sync command:

```powershell
.\.venv\Scripts\python.exe -m hoyolab_export.account_storage
```

The sync reads already-local files only:

- `data/hoyolab/account_characters.json`
- `data/hoyolab/account_weapons.json`
- `data/hoyolab/account_character_details.json`
- `data/hoyolab/crop_manifest.json`
- `data/cache/hoyowiki/character_stats_catalog.json` when present

The manual command still does not fetch network data by default. Passing
`--download-side-icons` enables the same narrow side-icon cache path used by
normal import for already-known HoYoLAB `side_icon` URLs; cached files are reused
and not redownloaded.

## Runtime Boundary

Normal runtime/UI account data should read from the SQLite adapter in
`hoyolab_export/account_storage.py`, not directly from HoYoLAB account JSON:

- account character grids/lists use `account_characters`;
- character level/constellation/element/rarity/icon/portrait/side icon/base
  values come from `AccountCharacterRuntimeRecord`;
- talent levels come from `account_character_talents`;
- region, `Moonsign`/`Hexerei`, and standard 5-star membership come from the
  SQLite `character_identity` enrichment table through the same account read
  adapter;
- weapon lists use `account_weapon_observed_stacks`;
- observed weapons are stack rows with `known_count`, not unique instances.
- TeamBuilder/prototype selected weapons should use explicit observed weapon
  options (stack id/fingerprint or an explicit smoke selector). Source metadata
  about current-equipped observations is provenance/debug context, not a
  canonical selector.
- persistent current equipment state uses `account_character_equipped_artifacts`
  and `account_character_equipped_weapons` through
  `hoyolab_export/account_equipment.py`; AppShell Stage B reads/writes current
  weapons through these helpers.

Runtime visual weapon grids should keep the legacy crop/asset visibility rule:
1-2 star observed weapons are stored in `account_weapon_observed_stacks` for
provenance/reconstruction, but hidden from normal weapon asset grids. The crop
manifest marks these rows as `weaponIgnored`, does not create `weaponAssets` for
them, and `ui/character_assets.py` follows the same rule instead of treating the
missing local icon crop as an asset loss.

Known dummy/mannequin IDs from `hoyolab_export/crop_manifest.py` are not runtime
account character display entries. Account sync and visual helpers must filter
them explicitly before portrait/side-icon fallback so a cached side icon cannot
make a non-account placeholder visible.

Weapon stack icon paths must be resolved by stable weapon identity/icon source
(`icon` URL key first, then `weapon_id`), not by source row order or equipped
character. A single character can appear in multiple crop manifest weapon assets
after equipment changes, so character-keyed icon lookup can swap images such as
Slingshot and Skyward Harp.

Raw HoYoLAB JSON remains a source/cache input for import/sync and explicit
debug/source-inspection tools only. Do not add new direct reads of
`account_characters.json`, `account_weapons.json`, or
`account_character_details.json` to UI/runtime code. If runtime SQLite account
tables are empty after import should have run, show/report a clear empty storage
condition instead of silently falling back to stale raw JSON.

## Tables

### `account_characters`

One canonical account-state row per HoYoLAB source/game character id.
`account_characters.json` is the authoritative source for which characters are
on the account.

Fields:

- `character_id INTEGER PRIMARY KEY`
- `name`
- `element`
- `rarity`
- `level`
- `constellation`
- `weapon_type`
- `weapon_type_name`
- `icon_url`
- `side_icon_url`
- `portrait_path`
- `side_icon_path`
- `base_hp`
- `base_atk`
- `base_def`
- `ascension_bonus_stat_type`
- `ascension_bonus_value`
- `source_metadata_json`
- `warnings_json`
- `first_seen_at`
- `last_seen_at`
- `updated_at`

### `character_identity`

One runtime enrichment row per account character. This is not raw account state;
it joins the account character row with static/reference character catalogs so
all UI/runtime code can filter and sort consistently.

Fields:

- `character_id INTEGER PRIMARY KEY`
- `hoyowiki_entry_id`
- `region_key`
- `region_name`
- `traits_json`
- `is_standard_5_star`
- `source_metadata_json`
- `updated_at`

Current trait values include `moonsign`, `hexerei`, and `standard_5_star`.
`Moonsign`/`Hexerei` membership comes from HoYoWiki entries `8782` and `9347`;
standard 5-star membership is seeded from the standard-wish 5-star list plus
Traveler, with HoYoWiki entry `2952` as source context. Traveler must remain
marked `standard_5_star` when the dedicated Traveler model is implemented; the
current identity join force-marks Traveler account character ids as standard so
localized/custom account naming does not hide it from the tri-state filter.
Concrete resonance formulas are not stored here.

Base stat source rules:

- HP: `account_character_details.json -> base_properties[property_type=2000].base`
- DEF: `account_character_details.json -> base_properties[property_type=2002].base`
- ATK: `base_properties[property_type=2001].base - weapon.main_property.final`

`weapon.main_property.final` is allowed here because it is equipped weapon base
ATK, needed to derive clean character base ATK from HoYoLAB's account base ATK.
HoYoLAB final stat-sheet rows remain non-canonical for TeamBuilder selected-build
stats.

Ascension bonus source rules:

- HoYoLAB does not expose a reliable character promote/ascension phase field, but
  `base_properties[*].base` gives actual account base stats.
- Account sync matches the HoYoWiki row/phase by HoYoLAB base stat before storing
  `ascension_bonus_stat_type/value`.
- Match order is HP first, DEF second, then derived character ATK only if HP/DEF
  are unavailable.
- If the base-stat match is missing, ambiguous, or unavailable, keep clean base
  HP/ATK/DEF but leave `ascension_bonus_value` empty and record source warnings.
- Do not use the old level-only assumption (`70 => after ascension`) for account
  runtime ascension bonuses.

Side icon path rules:

- `side_icon_url` comes from HoYoLAB account character data.
- `side_icon_path` is a deterministic local cache path when the icon already
  exists locally or the normal import/manual side-icon cache path is used.
- The path key uses stable `character_id`, not localized character name.
- Side icon cache failure is non-blocking: keep `side_icon_url`, leave
  `side_icon_path` empty, and record a warning/provenance entry.

Sync policy:

- valid non-empty HoYoLAB character list upserts by `character_id`;
- existing rows update in place;
- new characters insert;
- empty/broken character source does not wipe the table;
- destructive character pruning is intentionally not part of this model.

Storage contract:

`account_characters` contains account character state and clean references:

- character id/name/element/rarity/level/constellation;
- icon URL/local paths, including side icon URL/local path for future overlays;
- clean base HP/ATK/DEF where available;
- ascension bonus stat/value as matched reference when available;
- source metadata and warnings.

For display/stat-combiner use, account-runtime ascension bonuses for HP/ATK/DEF
are percent bonuses even when SQLite stores the numeric value without a `%`
suffix. Elemental Mastery remains flat/additive.

`account_characters` does not contain:

- talent descriptions/effects;
- constellation descriptions/effects;
- parsed buffs;
- GCSIM formulas;
- current equipped artifact-influenced final stats as canonical values.

Direct always-on artifact set and weapon passive display-stat effects are not
account state. They live in separate runtime SQLite effect tables documented in
`docs/handoff/DATA_RUNTIME_BOUNDARIES.md`; account tables only provide the
selected character/weapon facts those effect rows are joined against.

Character ascension/promote phase is not stored as a raw account field. Account
storage derives the needed HoYoWiki row/phase by matching actual HoYoLAB base
stats instead of guessing by level.

### `account_character_talents`

Observed account skill/talent levels from local HoYoLAB detail JSON:

- `account_character_details.json -> json.data.list[].skills[]`

Fields:

- `character_id INTEGER NOT NULL`
- `skill_id INTEGER NOT NULL`
- `skill_type`
- `name`
- `level`
- `icon_url`
- `is_unlock`
- `source_metadata_json`
- `warnings_json`
- `first_seen_at`
- `last_seen_at`
- `updated_at`

Primary key:

- `(character_id, skill_id)`

Sync policy:

- upsert by `(character_id, skill_id)`;
- existing skill rows update level/name/type/icon/unlock state;
- new skill rows insert;
- missing/broken detail JSON for one character does not wipe existing talents;
- no pruning/deletion policy is implemented in this step.

Storage contract:

`account_character_talents` contains:

- observed account skill/talent levels;
- skill ids/types/names/icons/unlock state as account state;
- minimal source metadata/warnings.

`account_character_talents` does not contain:

- parsed formulas;
- static talent effect catalog;
- constellation effects;
- GCSIM-specific config.

Future static talent/constellation effect parsing belongs in a separate
catalog/research task. Do not scrape broad HoYoLAB/HoYoWiki sources for static
talent descriptions in this account-storage area.

### `account_weapon_observed_stacks`

Reconstructed observed weapon stacks from HoYoLAB equipped/detail observations.
This is not a proven full weapon inventory.

Terminology note: "stack" here means a deduped observed weapon fingerprint with
`known_count`, not a UI tooltip/grouping of different weapon variants.

HoYoLAB weapon id is a weapon type id, not a unique account weapon instance id.
For example, several Favonius Lances can all share weapon id `13407`; exact
identity comes from the normalized observed weapon fingerprint, not from a fake
instance id.

Fields:

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `weapon_fingerprint TEXT NOT NULL UNIQUE`
- `weapon_id`
- `name`
- `weapon_type`
- `weapon_type_name`
- `rarity`
- `level`
- `refinement`
- `promote_level`
- `base_atk`
- `base_atk_raw`
- `secondary_property_type`
- `secondary_stat_value`
- `secondary_stat_value_raw`
- `description` (HoYoLAB account flavor/lore text only; not weapon passive text)
- `icon_url`
- `icon_path`
- `known_count INTEGER NOT NULL DEFAULT 1`
- `first_seen_at`
- `last_seen_at`
- `source_metadata_json`
- `warnings_json`

Fingerprint identity fields use project canonical values:

- `weapon_id`
- `rarity`
- `level`
- `refinement`
- `promote_level`
- normalized `base_atk`
- `secondary_property_type`
- normalized `secondary_stat_value`

Not part of fingerprint:

- equipped character;
- localized name;
- description/flavor text;
- icon path;
- source row index;
- current-equipped relation.

Sync policy:

- build observations from local `account_weapons.json` and
  `account_character_details.json -> json.data.list[].weapon`;
- dedupe duplicate list/detail observations for the same equipped character;
- group identical fingerprints within one sync;
- upsert by `weapon_fingerprint`;
- if a fingerprint is observed `N` times in one sync,
  `known_count = max(existing_known_count, N)`;
- if a later sync observes fewer copies or zero copies, do not decrease
  `known_count` and do not delete the stack;
- if a different fingerprint appears, insert a separate observed stack;
- do not infer "same weapon upgraded" vs "different copy";
- do not invent canonical weapon instance ids.

Weapon passive/effect tooltip text is stored outside account weapon stacks in
`weapon_passive_tooltips` by `(weapon_id, lang)`. That table is populated from
HoYoWiki weapon `baseInfo` passive fields through the `weapon_wiki` mapping.
Keep it separate from `account_weapon_observed_stacks.description`, which is
only localized flavor/lore text from HoYoLAB account detail.

This follows the artifact identity philosophy: source observations are imported
into local runtime storage and deduped by source-independent content. The weapon
difference is that exact duplicate weapons are common, so the model stores a
non-decreasing known/max count for indistinguishable copies.

Storage contract:

`account_weapon_observed_stacks` contains:

- reconstructed observed weapon stacks from equipped/detail observations;
- normalized fingerprint;
- non-decreasing known/max count;
- stable weapon reference fields such as level/refinement/promote level/base ATK
  and secondary stat where observed.

`account_weapon_observed_stacks` does not contain:

- guaranteed full weapon inventory;
- unique weapon instances;
- current-equipped relation as canonical identity.

Visibility note: 1-2 star starter/common weapons can appear here as observed
stacks, but normal weapon grids hide them by the same `IGNORED_WEAPON_RARITIES`
rule used by `hoyolab_export/crop_manifest.py`. This is a UI/asset visibility
filter, not deletion and not evidence that icons were lost.

Tooltip/display note: weapon secondary stats in runtime UI should use display
labels from the shared property-type mapping, for example `Energy Recharge` or
`CRIT Rate`, not raw `P23` / `P20` ids. SQLite still stores canonical
`secondary_property_type` and numeric values separately from display text.

## Current-Equipped Relation

Current-equipped character -> weapon relation is provenance/source context only,
not canonical account weapon storage.

Do not resurrect the interrupted draft semantics as the main model:

- `account_weapons` as current/default equipped refs;
- `source_key = equipped_character:<character_id>:weapon:<weapon_id>`;
- `account_current_equipped_weapons` as canonical source;
- `get_current_equipped_weapon_for_character(...)` as primary storage API;
- source-row index as weapon identity;
- pruning/deleting/decreasing observed weapon data after a later smaller
  observation window.

If current-equipped provenance is needed later, read it from raw JSON or compact
`source_metadata_json`; do not add an observations table until there is a concrete
runtime query that raw JSON/metadata cannot satisfy.

## Persistent Current Equipment State

Stage A current-equipment storage is implemented in
`hoyolab_export/account_equipment.py` and initialized by `init_db`.

Tables:

- `account_character_equipped_artifacts`
- `account_character_equipped_weapons`

Rules:

- artifacts reference `artifacts.id`;
- one artifact can be worn by at most one character through
  `UNIQUE(artifact_id)`;
- artifact slots use `flower`, `plume`, `sands`, `goblet`, `circlet`;
- weapons reference `account_weapon_observed_stacks.weapon_fingerprint`;
- weapons do not get fake instance/copy ids;
- multiple characters may reference the same weapon fingerprint only up to that
  stack's `known_count`, validated by service helpers;
- build presets are definitions and are not mutated by equip/unequip/swap
  operations;
- HoYoLAB observation helpers use the same service path and set
  `source='hoyolab_import'`;
- missing HoYoLAB equipment data means "no data" and does not clear local
  equipment.

Important boundary: AppShell uses this state for current weapon restore/write
and current weapon unequip. It reads current artifact ids into a runtime current
equipment snapshot for right-panel stats/set display, and embedded Artifact
Browser equip/apply writes through the same account equipment service helpers.

## Read Adapter Boundary

TeamBuilder/prototype code should not read raw SQL rows directly. For account
character/weapon observation rows, use `hoyolab_export/account_storage.py`:

- `list_account_characters(conn)`
- `get_account_character(conn, character_id)`
- `list_account_character_talents(conn, character_id)`
- `list_account_weapon_observed_stacks(conn)`
- `get_account_weapon_observed_stack(conn, weapon_fingerprint)`
- `get_account_weapon_observed_stack_by_id(conn, stack_id)`

The adapter returns `AccountCharacterRuntimeRecord` and
`AccountWeaponObservedStack` dataclasses with `to_dict()` and narrow future
TeamBuilder ref helpers. UI asset helpers in `ui/character_assets.py` convert
these runtime records into the legacy grid asset-item shape without reading
`crop_manifest.json` at runtime.

For current equipment, use `hoyolab_export/account_equipment.py` helpers such as
`equip_artifact`, `equip_weapon`, `list_equipped_artifacts_for_character`,
`get_equipped_weapon_for_character`, and owner read models. AppShell uses these
helpers for weapon restore/write/unequip and current artifact snapshot/display
paths.

## Canonical Vs Non-Canonical

Canonical for TeamBuilder virtual stat calculation:

- clean character base HP/ATK/DEF;
- selected weapon base ATK and secondary stat from an explicit selected weapon;
- HoYoWiki ascension bonus reference/value when available;
- selected `ArtifactBuildSnapshot` stat totals;
- safe baselines for CR/CD/ER/etc.

Non-canonical for TeamBuilder selected-build stats:

- HoYoLAB current-equipped final HP/ATK/DEF;
- HoYoLAB current CR/CD/ER/damage stats from currently equipped artifacts;
- `selected_properties` as final TeamBuilder output;
- current equipped artifact totals;
- weapon passive formulas;
- set bonus formulas;
- resonances;
- conditional effects;
- talents/constellations.

`source_metadata_json` may note that HoYoLAB `final` rows exist as reference, but
those rows must not be treated as canonical selected-build results.

## Value Normalization Layers

Keep these separate:

- raw/source value: exactly what HoYoLAB/source rows provide, optionally stored
  in `*_raw` fields or metadata;
- project canonical value: numeric/internal value used for SQLite storage,
  fingerprinting, dedupe, and future stat calculation inputs;
- display value: localized/formatted UI string;
- GCSIM/export value: a separate adapter layer, often ratios for percent stats.

Do not make GCSIM ratio values the default SQLite canonical representation unless
a dedicated stat-normalization handoff explicitly requires it. See
`docs/handoff/STAT_NORMALIZATION.md`.

## Deferred

- Full weapon inventory remains deferred. HoYoLAB equipped observations alone do
  not prove the complete inventory.
- Manual weapon merge/delete/allocation UI is not implemented.
- Account/profile scope is not added here; account switching continues through
  the existing explicit profile cleanup/export flow.
- No passive/set/resonance/final-total calculator is implemented here.
- No broad TeamBuilder/prototype loader migration is included in this step.
