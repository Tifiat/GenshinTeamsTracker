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
- If the user says "look only", "do not run", "just understand", or asks for handoff/context updates, inspect only lightweight text metadata and update notes.
- If a task can be answered by reading a small file or by the user visually checking something faster, stop after minimal inspection and report what to look at.
- Never revert user changes. The worktree is often dirty.
- Use `apply_patch` for file edits.

## Project Goal

GenshinTeamsTracker is a local PySide6 desktop tool for:

- importing a Genshin Impact account state from HoYoLAB;
- cropping and showing local character/weapon icons;
- dragging characters/weapons into team slots;
- timing and saving runs;
- importing artifact data into SQLite;
- building a new Artifact Browser with sets, custom tags/sets, sorting, presets, and future drag/drop build integration.

## Current Architecture

Main areas:

- `main.py`: PySide6 app entrypoint.
- `ui/main_window.py`: main app window, team builder, HoYoLAB import button, filters.
- `ui/widgets/`: shared PySide widgets such as loader, draggable icons, history.
- `hoyolab_export/`: HoYoLAB auth/export/import pipeline.
- `localization/`: JSON-backed app localization.
- `ui/artifact_browser/`: new isolated Artifact Browser module.
- `data/`: local generated profile/account state. Treat as private/generated.
- `assets/hoyolab/`: generated local account icons. Treat as private/generated.
- `assets/artifact_sets/`: generated or seeded artifact set piece icons.

Important generated files:

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

Current artifact identity model:

- canonical artifact set identity is `set_uid`;
- canonical set catalog comes from HoYoWiki `en-us`;
- localized set names live in `artifact_set_names`;
- HoYoLAB account/API mapping lives in `artifact_sets.hoyolab_set_id`;
- browser icons come from `artifact_set_piece_icons.local_path` by `(set_uid, pos)`.

Old per-artifact icon cache path has been removed from current code:

- `artifact_icon_cache.py` deleted;
- `upsert_icon()` removed;
- `cache_icons` no-op API removed;
- `upsert_artifact()` no longer takes `icon_id`;
- browser query no longer joins/falls back to `artifact_icons`;
- old DBs may still physically contain old columns/tables until a later DB cleanup.

## Artifact Browser State

The old QWidget-card Artifact Browser MVP was removed. The new module is under `ui/artifact_browser/`.

Current files:

- `window.py`: `ArtifactBrowserWindow`, top/bottom bars, filters, sorting, custom-set edit draft.
- `store.py`: in-memory store, grouping, sorting, custom set options.
- `queries.py`: SQLite read/write helpers for artifacts and custom sets.
- `models.py`: `ArtifactItem`, substats, tags, computed `cv` and `proc_count`.
- `list_model.py`: Qt model for artifact ids.
- `card_delegate.py`: current card renderer and edit-selection highlight.
- `filter_popup.py`: game/custom set popup.
- `sort_popup.py`: stat sorting popup.
- `stat_types.py`: property ids, badges, localizable sort options.

Current functional prototype:

- Uses `QListView + ArtifactListModel + ArtifactCardDelegate`.
- Filters by artifact position.
- Filters by game sets and custom sets.
- Game set icons come from set-piece icon catalog.
- Static UI strings touched so far are localized in `ru`, `en`, and `pt-br`.
- Current UI is prototype quality; do not polish QCheckBox/QWidget rows as final design.

Sorting:

- Default sort: rarity desc, level desc, crit value desc, set name, artifact name, id.
- User sort popup supports:
  - Crit Value first;
  - regular stat options;
  - Proc Count last.
- Proc Count is virtual: sum of `ArtifactSubstat.times`.
- Artiscan/GOOD test data currently has `rarity` and `level`, but no `times`; proc count is therefore `0` until roll data exists.
- If selected sort includes normal stat types, main-stat priority is applied before selected stat values.

Draft custom-set editing:

- `queries.py` supports:
  - `list_custom_sets`
  - `create_custom_set`
  - `delete_custom_set`
  - `get_custom_set_artifact_ids`
  - `replace_custom_set_artifacts`
- `store.py` loads custom set options from DB, including empty custom sets.
- `filter_popup.py` custom tab has draft create/edit/delete controls.
- Custom set creation works.
- Custom set deletion from the custom tab is not stable yet and needs UX cleanup:
  - delete should switch the row to inline confirm in-place;
  - check should delete the tag;
  - x should cancel pending delete;
  - popup should not close just because delete was clicked.
- `window.py` tracks an edit draft:
  - `editing_custom_set_id`
  - `editing_custom_set_name`
  - `editing_custom_artifact_ids`
  - `editing_custom_dirty`
- While editing, clicking cards toggles membership.
- Bottom edit bar currently has save/cancel/delete in the rough draft.
- Intended UX: bottom edit bar should keep save/cancel only.
- Custom set deletion belongs to the custom sets popup row, not to edit mode.
- `card_delegate.py` highlights draft-selected artifacts.
- This is a rough functional draft and needs manual review and UX cleanup.

Known Artifact Browser cleanup/future work:

- Stabilize custom-set editing.
- Add dirty-edit confirmation when closing/reloading/switching edit targets.
- Decide whether custom set rename belongs in the prototype.
- Smoke-test create/edit/delete for empty and non-empty sets.
- Smoke-test sorting/filtering while edit mode is active.
- Wire browser into main UI when stable.
- Later add build presets and drag/drop builds into team UI.

## Artiscan Notes

Root sample files:

- `test_artiscan_few.json`
- `artifacts_artiscan.json`

Observed `test_artiscan_few.json` shape:

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
- Character/weapon asset grids sort by rarity and level desc.
- Filters are compact icon rows, multi-select OR inside a group and AND between groups.
- Filter tooltips were removed.
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
