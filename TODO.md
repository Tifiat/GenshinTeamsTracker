# TODO: GenshinTeamsTracker

## Workflow

- [x] Keep this TODO updated after every task.
- [x] Mark completed work with `[x]`.
- [x] Add sub-tasks when new facts are discovered.
- [x] Update `agent_context.md` when architecture or important project facts change.

## Phase 0: Project Bootstrap

- [x] Create clean project folder `GenshinTeamsTracker`.
- [x] Add `agent_context.md` and `TODO.md`.
- [x] Add basic Python project structure.
- [x] Add `requirements.txt` based on required runtime only.
- [x] Add `.gitignore` for:
  - virtualenvs;
  - browser profiles;
  - downloaded images;
  - debug dumps;
  - caches;
  - generated crops.

## Phase 1: Port Known Working Pieces

- [x] Port HoYoLAB exporter from legacy sandbox.
- [x] Port manual export runner.
- [x] Port clean account inventory collector.
- [x] Keep debug extractor as debug-only/private tooling.
- [x] Add shared HoYoLAB profile auth status helper.
- [x] Add UI auth onboarding for first login and account switching.
- [x] Keep `HoyolabExporter` export-only; UI/manual runner handle the normal-browser login flow before automation.
- [x] Tighten HoYoLAB auth detection so a non-empty browser cookie DB alone is not treated as logged in.
- [x] Make auth UI buttons visible and explicit (`Авторизоваться`, `Сменить аккаунт`).
- [x] Wire `HoYoLAB export` button to exporter subprocess and disable it while auth is missing.
- [x] Add popup/update-notice dismissal retries around HoYoLAB export clicks.
- [x] Verify exporter/import pipeline downloads image correctly.
- [x] Verify inventory collector/import pipeline creates:
  - `account_characters.json`
  - `account_weapons.json`
- [x] Verify transferred exporter/inventory modules import successfully.
- [x] Add `hoyolab_export/paths.py` for production HoYoLAB folders and cleanup.
- [x] Add `hoyolab_export/layout_capture.py` for production html2canvas clone layout capture.
- [x] Add `hoyolab_export/crop_manifest.py` for production role-card extraction, crops, manifest, validation, and overlay.
- [x] Add `hoyolab_export/import_pipeline.py` and `hoyolab_export/run_import.py` for full import.

## Phase 2: Port UI Foundation

- [x] Port PySide6 app entrypoint.
- [x] Port main window behavior from legacy.
- [x] Port run/history window behavior from legacy.
- [x] Port necessary widgets:
  - draggable icons;
  - team slots;
  - timers;
  - run cards;
  - flow layout/history container.
- [x] Remove or isolate legacy parser/matcher calls from startup path.
- [x] Replace mojibake user-facing strings where touched.
- [x] Verify PySide6/UI module imports after dependency install.

## Phase 3: New HoYoLAB Export Bundle

- [x] Define current import folder structure.
- [x] Save exported HoYoLAB image as part of current import/debug output.
- [x] Save clean character inventory JSON.
- [x] Save clean weapon inventory JSON.
- [x] Add layout/DOM metadata capture for character and weapon elements.
- [x] Add `tests/probe_layout.py` for live HoYoLAB layout probing.
- [x] Hook html2canvas root capture into exporter JS patch via `window.__genshin_export_root_probe__`.
- [x] Add `html2canvasPatchStatus`, `fallbackRootProbe`, `rootSource`, and `rootDiscovery` diagnostics to layout probe output.
- [x] Ensure exporter/probe terminates its browser process after cleanup.
- [x] Remove fixed-port debug-login flow; first login now uses normal browser setup.
- [x] Replace `asyncio.run()` in layout probe with explicit Windows-friendly loop cleanup.
- [x] Keep normal outputs free of cookie/header/token dumps.
- [x] Confirm latest probe can use `html2canvas_clone` root discovery.
- [x] Define current HoYoLAB MVP folder structure:
  - `data/hoyolab`
  - `assets/hoyolab`
  - `debug/hoyolab`
- [x] Save exported HoYoLAB image to `debug/hoyolab/image.png`.
- [x] Save clean character inventory JSON to `data/hoyolab/account_characters.json`.
- [x] Save clean weapon inventory JSON to `data/hoyolab/account_weapons.json`.
- [x] Save production layout metadata to `data/hoyolab/layout.json`.
- [x] Add one command that performs image export + clean inventory collection + layout + crops into current HoYoLAB folders.
- [ ] Audit future bundle outputs so cookies/headers/raw sensitive network dumps never enter normal mode.
- [ ] Decide later whether timestamped import archives are needed; current MVP intentionally keeps only current account state.

## Phase 4: Coordinate-Based Crop Pipeline

- [x] Determine initial reliable DOM selectors/layout rules for character cards from sandbox probe:
  - `DIV` class contains `role-share`.
- [x] Determine initial reliable DOM selectors/layout rules for weapon mini-cards from sandbox probe:
  - `IMG` whose parent chain contains `role-weapon-info`.
- [x] Save DOM element rectangles from html2canvas clone/rootDiscovery for production import.
- [x] Run live `tests/probe_layout.py` and inspect `layout_probe.json` / `page_screenshot.png`.
- [x] Confirm working sandbox extraction of HoYoLAB role cards from probe layout.
- [x] Confirm sandbox finds 76/76 character cards with portrait and weapon rects in latest inspected bundle.
- [x] Confirm production extraction excludes `role-share-container` and produces 75 real cards.
- [x] Confirm production `layout.json` uses `rootSource == "html2canvas_clone"`.
- [x] If Google login is needed, use `python -m hoyolab_export.run_login_setup` before running automation.
- [x] Convert DOM/root-relative coordinates to final PNG coordinates using export scale.
- [x] Add first coordinate-cropper scaffold that crops from `layout.json` rectangles.
- [x] Smoke-test coordinate cropper on a synthetic image/layout pair.
- [x] Crop character images from final PNG by coordinates.
- [x] Crop weapon images from final PNG by coordinates.
- [x] Produce `crop_manifest.json` linking crops to API character/weapon records.
- [x] Promote sandbox role-card extraction logic into production import pipeline.
- [x] Switch manifest matching from index-based to icon-based:
  - `portraitSrc` -> `character.icon` / `character.side_icon`;
  - `weaponSrc` -> `weapon.icon`;
  - validate `weapon.equipped_by.id == character.id`.
- [x] Ignore dummy character assets for IDs `10000118` and `10000117` while keeping them in manifest/cards.
- [x] Ignore 1-star and 2-star weapons for weapon assets.
- [x] Deduplicate weapon assets by icon and aggregate variants by refinement + level.
- [ ] Keep old binary-mask parser only as optional fallback, not primary path.
- [x] Replace temporary layout schema with real HoYoLAB DOM selectors and API id linkage.

## Phase 5: UI Integration

- [x] Add UI action for HoYoLAB export.
- [x] Convert `HoYoLAB export` button into full HoYoLAB import:
  - run export/probe;
  - collect clean inventory JSON;
  - extract role cards from `rootDiscovery`;
  - crop character and weapon images;
  - save images into `assets/hoyolab/characters` and `assets/hoyolab/weapons`;
  - write manifest linking images to API records and sort fields;
  - refresh UI grids after success.
- [x] Switch UI grids from `assets/hd/*` to `assets/hoyolab/*`.
- [x] Add loader dialog for HoYoLAB import with `[STATUS]` progress updates.
- [x] Add import button cooldown after success/error.
- [x] Display generated character crops with manifest tooltips.
- [x] Display generated weapon crops with manifest tooltips.
- [x] Add custom stable tooltip widget for draggable icons.
- [x] Clear current HoYoLAB data/assets/debug from clear button and account switch.
- [x] Fix visible mojibake UI strings in loader/drag/main UI by routing static text through localization keys.
- [ ] Re-check team builder behavior with new `assets/hoyolab/*` paths and manifest-backed tooltips.
- [ ] Decide whether a separate future bundle import UI is still needed after current-state import MVP.
- [ ] Preserve draggable team composition behavior.

## Phase 6: Artifact Import Pipeline

- [x] Discover full HoYoLAB character/artifact detail endpoint:
  - `POST https://sg-public-api.hoyolab.com/event/game_record/genshin/api/character/detail`.
- [x] Verify `character/detail` accepts batch requests for all real characters in one POST.
- [x] Confirm `index?avatar_list_type=1` relic data lacks full stat fields.
- [x] Confirm full artifact stats are available in `character/detail`:
  - main property;
  - substat list;
  - roll counts;
  - property map.
- [x] Detect HoYoLAB language from page/session and pass it to manual fetch headers:
  - `x-rpc-language`;
  - `accept-language`.
- [x] Add SQLite artifact DB module `hoyolab_export/artifact_db.py`.
- [x] Add artifact importer module `hoyolab_export/artifact_importer.py`.
- [x] Add artifact import tool `tools/import_artifacts_from_detail_json.py`.
- [x] Add artifact tag persistence test tool `tools/test_artifact_tag_persistence.py`.
- [x] Verify first artifact import:
  - 73 characters;
  - 254 relics;
  - 254 inserted artifacts;
  - 104 artifact icons;
  - 1004 artifact substats.
- [x] Verify re-import does not duplicate artifacts.
- [x] Verify user tag `test_keep_after_import` survives re-import.
- [ ] Integrate batch `character/detail` fetch into main `python -m hoyolab_export.run_import` flow.
- [ ] Import artifacts into `data/artifacts.db` as part of main HoYoLAB import.
- [ ] Keep artifact tags persistent during repeated imports.
- [ ] Decide whether HoYoLAB account switch should preserve or clear `data/artifacts.db`.
- [ ] Decide whether `data/artifacts.db` is local generated state and should stay ignored.
- [ ] Add UI surface for artifact browsing/filtering/tagging after import is integrated.

## Localization

- [x] Add JSON-backed localization layer:
  - `localization/i18n.py`
  - `localization/locales/ru.json`
  - `localization/locales/en.json`
  - `localization/locales/pt-br.json`
- [x] Use `tr("key")` for static PySide UI text in main window, loader, timers, run history, and drag/delete dialogs.
- [x] Keep dynamic character/weapon tooltips sourced from HoYoLAB manifest/API data.
- [x] Keep UI language separate from HoYoLAB/API language.
- [x] Add bottom-right UI language selector with country flags.
- [x] Persist selected UI language in ignored local `settings.json`.
- [ ] Add localization keys for any new UI screens as they are built.
- [ ] Keep Brazilian Portuguese localization in sync when adding new keys.

## Git / Release Hygiene

- [ ] Retry normal `git push` for local commit `1ae2de6` after previous GitHub `Internal Server Error`; do not force-push.
- [ ] Decide whether `data/hoyolab`, `data/artifacts.db`, `assets/hoyolab`, and `assets/loader` should be committed or ignored as local/generated state.
- [ ] Review untracked `IMPORT_TODO.md`, `ToDO_importMVP.txt`, and `tests/probe_layout_baseline.log`; keep, ignore, or remove deliberately.

## Phase 7: History Model

- [ ] Design new history schema.
- [ ] Support history categories:
  - Abyss;
  - Stygian Onslaught / Мрачный натиск.
- [ ] Support version/cycle switching inside each category.
- [ ] Store teams and timers per saved run.
- [ ] Plan future fast export of visual history by selected mode/version.

## Deferred / Future

- [ ] Find reliable source for current Abyss cycle/version.
- [ ] Find reliable source for current Stygian Onslaught cycle/version.
- [ ] Add fast visual export of history for a selected Abyss/Onslaught cycle.
- [ ] Add migration/import from legacy `runs_history.json` if needed.
