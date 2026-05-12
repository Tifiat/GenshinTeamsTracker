# Agent Context: GenshinTeamsTracker

This file is written for future coding agents. Keep it compact, English, and mostly ASCII so it is cheap to read and unlikely to cause encoding friction.

## Operating Rules

- The user usually writes in Russian, but project handoff files should stay in English.
- Be frugal with context and tool output.
- Prefer narrow `rg` queries and small file slices.
- Do not recursively list or read generated/private state unless explicitly needed:
  - `hoyolab_export/profile`
  - `data/`
  - `assets/hoyolab`
  - `assets/artifact_sets`
  - image folders and large JSON dumps
- Do not run tests, imports, app startup, DB scans, image parsing, or broad validation unless the user asks or the current code change genuinely needs it.
- Use `.venv\Scripts\python.exe` for local checks when the system interpreter lacks project dependencies.
- If the user says "look only", "do not run", "just understand", or asks for handoff/context updates, inspect only lightweight text metadata and update notes.
- Never revert user changes. The worktree is often dirty.
- Use `apply_patch` for file edits.

## Project Goal

GenshinTeamsTracker is a local PySide6 desktop tool for:

- importing a Genshin Impact account state from HoYoLAB;
- cropping and showing local character/weapon icons;
- dragging characters/weapons into team slots;
- timing and saving runs;
- importing artifact data into SQLite;
- building an Artifact Browser with sets, custom tags/sets, sorting, build presets, target ownership, and future drag/drop build integration.

## Main Areas

- `main.py`: PySide6 app entrypoint.
- `ui/main_window.py`: main app window, team builder, HoYoLAB import button, character/weapon filters.
- `ui/character_assets.py`: shared HoYoLAB asset item helpers, character filter constants, character filter/sort logic.
- `ui/widgets/`: shared PySide widgets such as loader, draggable icons, history.
- `hoyolab_export/`: HoYoLAB auth/export/import pipeline and artifact DB helpers.
- `localization/`: JSON-backed app localization.
- `ui/artifact_browser/`: isolated Artifact Browser module.
- `data/`: local generated profile/account state. Treat as private/generated.
- `assets/hoyolab/`: generated local account icons. Treat as private/generated.
- `assets/artifact_sets/`: generated or seeded artifact set piece icons.

Important generated/seed files:

- `data/hoyolab/account_characters.json`
- `data/hoyolab/account_weapons.json`
- `data/hoyolab/account_character_details.json`
- `data/hoyolab/account_language.json`
- `data/hoyolab/crop_manifest.json`
- `data/artifacts.db`
- `data/static/artifact_set_catalog.json`

## HoYoLAB Import Pipeline

Current production command:

```powershell
python -m hoyolab_export.run_import
```

Pipeline summary:

1. Open HoYoLAB with the app browser profile.
2. Export the HoYoLAB image and capture layout/root metadata.
3. Collect `character/list` and clean inventory JSON.
4. Fetch batch `character/detail` for real character ids.
5. Detect HoYoLAB content language from the real detail request.
6. Save `account_language.json` and `account_character_details.json`.
7. Ensure artifact set catalog and localized set names.
8. Ensure HoYoLAB `relic.set.id -> set_uid` mapping via a service EN-pass when needed.
9. Import/update artifacts into `data/artifacts.db`.
10. Crop characters/weapons and merge current assets/manifest.

Critical rules:

- Do not use image matching, cv2, perceptual hashes, or external artifact databases.
- Do not assume HoYoLAB `set_id` equals HoYoWiki `entry_page_id`.
- Do not import EN `character/detail` as user data. It is only for set id/name mapping.
- Do not overwrite localized character, weapon, stat, or artifact display data with the EN service payload.
- HoYoLAB/API content language and UI language are separate.
- Ordinary HoYoLAB update must preserve existing local HoYoLAB data/assets if it fails early.
- Destructive profile cleanup belongs to explicit profile sign-out or offline profile restore.

## Artifact Database

SQLite DB: `data/artifacts.db`.

Key tables:

- `artifact_sets`
- `artifact_set_piece_icons`
- `artifact_set_names`
- `artifacts`
- `artifact_substats`
- `artifact_equipment`
- `artifact_tags`
- `artifact_tag_links`
- `artifact_builds`
- `artifact_build_slots`
- `artifact_build_targets`

Current artifact identity model:

- canonical artifact set identity is `set_uid`;
- canonical set catalog comes from HoYoWiki `en-us`;
- localized set names live in `artifact_set_names`;
- HoYoLAB account/API mapping lives in `artifact_sets.hoyolab_set_id`;
- browser icons come from `artifact_set_piece_icons.local_path` by `(set_uid, pos)`;
- custom sets are `artifact_tags` + `artifact_tag_links`;
- build presets use `artifact_builds`, `artifact_build_slots`, and `artifact_build_targets`.

Build preset target model:

- one preset can target Universal and/or multiple characters;
- targets are ownership/category filters, not equipment/apply state;
- selecting multiple targets in the UI means intersection: show presets whose target set contains all selected targets;
- Universal is only included when Universal itself is selected.

Old per-artifact icon cache path has been removed from current code. Do not reintroduce:

- `artifact_icons`
- `icon_id`
- `artifact_icon_cache`
- `upsert_icon`
- `cache_icons`

Old DBs may still physically contain old columns/tables until a later DB cleanup.

## Artifact Browser

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
- `stat_types.py`: property ids, badges, localizable sort options.

Current functional state:

- Uses `QListView + ArtifactListModel + ArtifactCardDelegate`.
- Normal QListView blue selection is disabled; cards use delegate state/highlight.
- Filters by artifact position.
- Filters by game sets and custom sets.
- Game set icons come from set-piece icon catalog.
- Shared edit-selection mode is used for custom-set and build-preset editing.
- Bottom edit bar has save/cancel only.
- Static UI strings touched so far are localized in `ru`, `en`, and `pt-br`.
- Current UI is prototype quality; do not polish QWidget rows as final design.

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
- Build preview shows target icons row, 5 artifact mini-slots, up to 2 active set bonuses, and a compact stat summary.
- Build edit mode uses the same tint/highlight/bottom save-cancel infrastructure as custom sets.
- Clicking an artifact while editing assigns/replaces the slot for that artifact position.
- Saved preset selection highlights selected artifacts and may move them to the front of the current artifact list.
- Build target selector is a middle column: fixed vertical filters on the left, scrollable Universal/character target list on the right.
- Main UI and Artifact Browser share character asset/filter/sort helpers via `ui/character_assets.py`.

Sorting:

- Default sort: rarity desc, level desc, effective crit value desc, set name, artifact name, id.
- Explicit Crit Value sort also uses effective crit value for circlets, including CR/CD main stat contribution.
- User sort popup supports Crit Value first, regular stat options, and Proc Count last.
- Proc Count is virtual: sum of `ArtifactSubstat.times`.
- Artiscan/GOOD sample data may have no `times`; proc count is then `0`.
- If selected sort includes normal stat types, main-stat priority is applied before selected stat values.

Known near-term Artifact Browser work:

- Visually review and tune the Build Target Selector MVP.
- Verify target filtering/persistence for Universal, one character, and multiple characters.
- Re-check fixed preview geometry: 5 artifact mini-slots + 2 bonus slots with no clipping and balanced padding.
- Smoke-test custom sets after target selector changes.
- Wire the browser into main UI when stable.

## Artiscan Notes

Sample files live under `samples/artiscan/`.

Observed GOOD shape:

- format: GOOD
- source: Artiscan
- artifacts list includes `rarity`, `level`, `mainStatKey`, `slotKey`, `setKey`, `substats`, `location`, `lock`
- substats include `key` and `value`
- no roll/proc `times` data observed

Do not build Artiscan assumptions from image matching. Use structured GOOD fields.

## Main UI State

Main window current behavior:

- Dynamic HoYoLAB button:
  - no auth: authorize / choose profile;
  - auth + no local data: import from HoYoLAB;
  - auth + local data: update HoYoLAB data.
- Button runs `python -m hoyolab_export.run_import` through `QProcess`.
- `HoYoLABLoadingDialog` consumes `[STATUS] ...` lines.
- On success, UI refreshes grids without a success popup.
- Import button has cooldown so Chrome/profile cleanup can settle.
- Character/weapon grids read from `assets/hoyolab/characters` and `assets/hoyolab/weapons`.
- Grids use `data/hoyolab/crop_manifest.json` for tooltips, filters, and sort fields.
- Character grid sort is rarity desc, level desc, name, filename.
- Filters are compact icon rows, multi-select OR inside a group and AND between groups.
- Filtered grids remain left-aligned with fixed icon spacing.
- `Profile...` menu has save profile, load profile, sign out.
- Sign-out is the destructive account boundary and can also clear artifact DB.

## Offline Profile

Offline profile export/import:

- ZIP based.
- Includes allowlisted current JSON/assets/artifact DB only.
- Excludes HoYoLAB browser profile, cookies, sessions, debug, downloads.
- Uses SQLite backup snapshot for `data/artifacts.db`.
- Writes local export-state marker so sign-out can warn if current data may not be saved.

Known TODO:

- When improving offline profile export/import, include `data/hoyolab/account_language.json` alongside:
  - `account_character_details.json`
  - `account_characters.json`
  - `account_weapons.json`
  - `crop_manifest.json`

## Localization

Localization is JSON-backed, not Qt `.ts/.qm`.

Files:

- `localization/i18n.py`
- `localization/locales/ru.json`
- `localization/locales/en.json`
- `localization/locales/pt-br.json`

Rules:

- UI code should use `tr("key")`.
- Default UI language is `ru`.
- Supported UI languages: `ru`, `en`, `pt-br`.
- Selected language is stored in local ignored `settings.json`.
- `GTT_LANGUAGE` or `GTT_LANG` can override UI language for a process.
- Character/weapon/artifact dynamic names from HoYoLAB should keep the HoYoLAB content language.
- Keep `pt-br.json` in sync when adding keys.

## Security / Privacy

Never save or commit:

- cookies;
- auth tokens;
- raw request headers;
- raw network dumps outside explicit ignored debug folders;
- browser profile data.

Normal clean outputs may contain:

- ids and display names;
- levels, rarity, refinements, constellations;
- icons and local crop files;
- artifact DB rows.

Debug files are private and ignored.

## Future Direction

History:

- Current history window exists.
- Future history should support Abyss and Stygian Onslaught tabs.
- Future records should include team composition and timer data by version/cycle.

Artifact Browser final UI:

- Final visual style should be Genshin-like.
- Use delegates/theme/assets rather than QWidget rows when polishing.
- Keep `store`, `queries`, and models independent from visual skin.
- Do final UI/performance refactor only after functionality is stable.

Legacy note:

- Do not revive legacy mask-based image detection unless explicitly asked.
- Preferred HoYoLAB extraction path is DOM/layout/coordinate based.
