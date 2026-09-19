# Artifact Browser, Storage And JSON Import

Current contract map, consolidated 2026-09-16 from the former root notes.
This document owns storage identity, browser editing/filter/sort behavior and
Artiscan import conventions. Equipment write semantics and operation-target
priority are owned by [ARTIFACT_BROWSER_EQUIPMENT_UX.md](ARTIFACT_BROWSER_EQUIPMENT_UX.md).
Open work belongs in `TODO.md`; consolidation is not a new UI/test acceptance.

## Storage And Identity

SQLite DB: `data/artifacts.db`.

Key tables:

- `artifact_sets`
- `artifact_set_piece_icons`
- `artifact_set_names`
- `artifact_set_bonus_descriptions`
- `artifact_set_display_stat_effects`
- `weapon_display_stat_effects`
- `weapon_passive_tooltips`
- `artifacts`
- `artifact_substats`
- `artifact_equipment`
- `artifact_tags`
- `artifact_tag_links`
- `artifact_builds`
- `artifact_build_slots`
- `artifact_build_targets`
- `artifact_build_gcsim_targets`
- `artifact_import_batches`

Current artifact identity model:

- canonical artifact set identity is `set_uid`;
- canonical set catalog comes from HoYoWiki `en-us`;
- localized set names live in `artifact_set_names`;
- localized artifact set 2p/4p bonus descriptions live in `artifact_set_bonus_descriptions`;
- localized weapon passive/effect tooltip text lives in `weapon_passive_tooltips`
  by `(weapon_id, lang)`; HoYoLAB account weapon `desc` is only flavor/lore
  text and is not a combat passive;
- HoYoLAB account/API mapping lives in `artifact_sets.hoyolab_set_id`;
- Artiscan/GOOD set-key mapping lives in `artifact_sets.artiscan_set_key`;
- browser icons come from `artifact_set_piece_icons.local_path` by `(set_uid, pos)`;
- custom sets are `artifact_tags` + `artifact_tag_links`;
- account-backed build targets use `artifact_build_targets`; virtual catalog
  targets use `artifact_build_gcsim_targets` keyed by stable GCSIM character
  key. Reads project a virtual target as the single ordinary account target as
  soon as a ready `account_characters.gcsim_character_key` match exists.
- `artifacts.fingerprint` is kept for legacy/current HoYoLAB identity behavior.
- `artifacts.content_fingerprint` is source-independent and is based on normalized artifact content:
  set_uid, position, rarity, level, main stat type/value, and sorted substat type/value pairs.
- JSON imports mark only newly inserted artifacts with `json_imported=1`, `import_source`,
  `import_format`, and `import_batch_id`; pre-existing duplicate artifacts are not relabeled.

Build preset target model:

- one preset can target Universal and/or multiple characters;
- targets are ownership/category filters, not equipment/apply state;
- selecting multiple targets in the UI means intersection: show presets whose target set contains all selected targets;
- Universal is only included when Universal itself is selected.
- a virtual GCSIM character may own a browse/preset target but is never an
  equipment operation target; no artifact click can equip an absent account
  character;
- target identity is the stable GCSIM key, never the localized/display name.
  When the matching account character later exists, the browser suppresses the
  virtual row and exposes one account-backed target/tab rather than duplicates.
  Dedicated lookup/validation by stable GCSIM key accepts either the original
  virtual target row or an ordinary account-character target saved after this
  logical merge, so the virtual run-profile picker does not lose the build.


Old per-artifact icon cache code is removed. Do not restore `artifact_icons`,
`icon_id`, `artifact_icon_cache`, `upsert_icon` or `cache_icons` fallbacks.
Physical old DB columns/tables may remain until a separately planned migration.

## Browser Modules And Behavior

Current module: `ui/artifact_browser/`.

Important files:

- `window.py`: `ArtifactBrowserWindow`, layout, edit modes, custom sets, build presets, build target selector.
- `store.py`: in-memory store, grouping, sorting, custom set options.
- `queries.py`: SQLite read/write wrappers for artifacts, custom sets, build presets.
- `models.py`: `ArtifactItem`, substats, tags, computed `cv` and `proc_count`.
- `list_model.py`: Qt model for artifact ids.
- `card_delegate.py`: card renderer and shared edit-selection highlight.
- `filter_popup.py`: game/custom set popup.
- `sort_popup.py`: stat sorting popup.
- `region_popup.py`: multi-select region popup for the build target selector.
- `stat_types.py`: property ids, badges, localizable sort options.
- `json_import_actions.py`: Artiscan/GOOD JSON import and clear actions for the browser UI.

Current functional state:

- Uses `QListView + ArtifactListModel + ArtifactCardDelegate`.
- Normal QListView blue selection is disabled; cards use delegate state/highlight.
- Filters by artifact position.
- Filters by game sets and custom sets.
- Game set icons come from set-piece icon catalog.
- Artifact set 2p/4p bonus descriptions are imported from HoYoWiki list payload
  `display_field.two_set_effect` / `display_field.four_set_effect` and stored per
  `(set_uid, lang, piece_count)`.
- Shared edit-selection mode is used for custom-set and build-preset editing.
- Bottom edit bar has save/cancel only.
- Static UI strings touched so far are localized in `ru`, `en`, and `pt-br`.
- The embedded browser/equipment flow is implemented; preserve its calibrated
  geometry and data/view separation when polishing.

Custom sets:

- `queries.py` supports list/create/delete/get/replace for custom sets.
- `store.py` loads custom set options from DB, including empty custom sets.
- `filter_popup.py` custom tab has create/edit/delete with inline delete confirmation.
- Empty custom set names are rejected with localized invalid input state.
- After creating a custom set, the browser enters edit mode for it.
- Dirty custom-set edits ask before close/reload/switching.

Build presets:

- Build data layer supports create/update/delete/list/get, slot replacement, target replacement, and raw summary calculation.
- Preset panel is compact and fixed-width.
- Preset list scrolls independently; preview block stays fixed at the bottom.
- Build preview has an explicit fixed geometry: target strip, 5 artifact mini-cards, set bonus preview container, and compact stat summary. Do not confuse this preview set-bonus rendering with compact preset-row metadata rendering.
- Build preset rows show compact metadata near the name:
  - no active bonus: `NO / BONUS`;
  - single active 2p: one set icon with badge `2`;
  - 4p: one set icon with badge `4`;
  - 2+2: one diagonal composite icon with one badge `2`;
  - row icons use a trim/scale/mask/composite pipeline through `ui/utils/pixmap_utils.py`.
- Compact preset-row bonus icons use in-memory cache plus persistent PNG cache under `data/cache/ui/preset_bonus_icons/`.
- Compact preset-row set bonus icons have custom tooltips backed by stored
  `artifact_set_bonus_descriptions`; 4p shows 2p+4p rows, single 2p shows one row,
  and 2+2 diagonal composite shows two 2p rows.
- Build target preview row is a baked-pixmap horizontal scroll strip, not many child widgets:
  - target icons are not clickable and no tooltip is planned there;
  - drag-scrolls horizontally;
  - wheel-scrolls horizontally;
  - uses gradient edge hints with chevrons;
  - Universal target uses `users.svg` inside a rounded card.
- Target preview icons and final strips use in-memory cache plus persistent PNG caches under:
  - `data/cache/ui/target_preview_icons/`;
  - `data/cache/ui/target_preview_strips/`.
- Build edit mode uses the same tint/highlight/bottom save-cancel infrastructure as custom sets.
- Build preset inline rename focus is fixed: entering preset edit mode focuses the name input and selects its text, so typing/backspace works immediately without an extra click.
- Clicking an artifact while editing assigns/replaces the slot for that artifact position.
- Saved preset selection highlights selected artifacts and may move them to the front of the current artifact list.
- Build target selector is a middle column: fixed vertical filters on the left, scrollable Universal/character target list on the right.
- Build target selector region filtering is implemented as a popup opened by
  `assets/filters/Statue.png`.
- Character region data comes from HoYoWiki character list `menu_id=2` and is cached in
  `data/cache/hoyowiki/character_region_catalog.json`.
- Region/trait identity is joined into SQLite `character_identity`; read adapters expose
  `region_key`, `region_name`, `traits`, and `is_standard_5_star` for every account character when matched.
- Region and `Moonsign`/`Hexerei` filters are OR inside their own group, then AND
  with selected element/weapon/rarity filters. Standard 5-star is a tri-state
  filter using `assets/filters/standard.png`.
- Region/trait joins prefer HoYoWiki entry ids and use normalized localized names only as fallback.
- `assets/filters/Icon_Back.png` is used as the build target selector reset-all filter button.
- Editing a saved build preset temporarily switches selected targets to that preset's targets; after save/cancel, the previous target browsing selection is restored.
- Enter/Return saves and Esc cancels when a custom-set or build-preset edit mode is active.
- Main UI and Artifact Browser share character asset/filter/sort helpers via `ui/character_assets.py`.
- Artifact Browser SVG UI icons should use `ui/utils/icon_utils.py` auto-contrast helpers. Current direct `QIcon(...)` uses in the browser are for non-SVG assets such as PNG filters, portraits, and artifact set icons.
- Artifact Browser has fixed bottom-row JSON actions under the artifact list:
  - Import JSON supports multiple Artiscan/GOOD files and uses backend content-fingerprint dedupe.
  - Clear JSON deletes only `json_imported=1` artifacts from `import_source='artiscan'`,
    clears affected build preset slots, then optionally deletes affected presets.

Sorting:

- Default sort: rarity desc, level desc, effective crit value desc, set name, artifact name, id.
- Explicit Crit Value sort also uses effective crit value for circlets, including CR/CD main stat contribution.
- User sort popup supports Crit Value first, regular stat options, and Proc Count last.
- Sort and Sets popups order game/custom sets by owned piece count descending.
- Proc Count is virtual: sum of `ArtifactSubstat.times`.
- Artiscan/GOOD sample data may have no `times`; proc count is then `0`.
- If selected sort includes normal stat types, main-stat priority is applied before selected stat values.
- For circlets, when Crit Value is the first sort key, neither CR nor CD is explicitly selected,
  and another normal stat follows, CR/CD main-stat circlets are sorted by total effective CV
  before the later normal-stat tie-break.


## Artiscan / GOOD

Sample files live under `samples/artiscan/`.

Observed GOOD shape:

- format: GOOD
- source: Artiscan
- artifacts list includes `rarity`, `level`, `mainStatKey`, `slotKey`, `setKey`, `substats`, `location`, `lock`
- substats include `key` and `value`
- no roll/proc `times` data observed

Do not build Artiscan assumptions from image matching. Use structured GOOD fields.

Current Artiscan state:

- Backend parser/import helper exists for Artiscan/GOOD JSON.
- Artiscan main stat numeric values use deterministic max main-stat values by rarity/stat key.
- `location` and `lock` are ignored in the MVP.
- These importer facts are not the optimizer input contract. The optimizer reads
  the already-populated shared `artifacts`/`artifact_substats` tables and does
  not call or filter by Artiscan.
- Exact content twins normally reuse an existing artifact through
  `content_fingerprint`, including cross-source Artiscan/HoYoLAB observations.
  User-approved exception (2026-09-08): the same HoYoLAB snapshot showing
  identical artifacts on distinct characters proves additional copies. Reuse
  existing copy ids first; create only the missing simultaneously seen copies.
  Reimports/reordered rows must not multiply them or alter saved preset refs.
- First-day/future improvement: automatic proc counting for imported artifacts.
