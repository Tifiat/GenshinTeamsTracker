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
- [ ] Verify exporter still downloads image correctly.
- [ ] Verify inventory collector creates:
  - `account_characters.json`
  - `account_weapons.json`
- [x] Verify transferred exporter/inventory modules import successfully.

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

- [ ] Define export bundle folder structure.
- [ ] Save exported HoYoLAB image as part of bundle.
- [ ] Save clean character inventory JSON.
- [ ] Save clean weapon inventory JSON.
- [ ] Add layout/DOM metadata capture for character and weapon elements.
- [x] Add `tests/probe_layout.py` for live HoYoLAB layout probing.
- [x] Hook html2canvas root capture into exporter JS patch via `window.__genshin_export_root_probe__`.
- [x] Add `html2canvasPatchStatus`, `fallbackRootProbe`, `rootSource`, and `rootDiscovery` diagnostics to layout probe output.
- [x] Ensure exporter/probe terminates its browser process after cleanup.
- [x] Remove fixed-port debug-login flow; first login now uses normal browser setup.
- [x] Replace `asyncio.run()` in layout probe with explicit Windows-friendly loop cleanup.
- [x] Keep normal outputs free of cookie/header/token dumps.
- [ ] Audit future bundle outputs so cookies/headers/raw sensitive network dumps never enter normal mode.
- [ ] Add one command that performs image export + clean inventory collection into one timestamped bundle.

## Phase 4: Coordinate-Based Crop Pipeline

- [ ] Determine reliable DOM selectors or layout rules for character cards.
- [ ] Determine reliable DOM selectors or layout rules for weapon mini-cards.
- [ ] Save DOM element rectangles before html2canvas export.
- [x] Run live `tests/probe_layout.py` and inspect `layout_probe.json` / `page_screenshot.png`.
- [ ] If `rootSource` is `fallback_candidate`, compare fallback root against exported PNG and harden html2canvas root patch.
- [ ] Investigate why `html2canvasPatchStatus.matched == true` but runtime `calls` is empty and `html2canvasRootProbe` is null.
- [x] If Google login is needed, use `python -m hoyolab_export.run_login_setup` before running automation.
- [ ] Authorize through the UI HoYoLAB prompt or `python -m hoyolab_export.run_login_setup`, close browser, then rerun `tests/probe_layout.py`.
- [ ] Confirm whether `html2canvasRootProbe.rootRect` maps to final PNG by `scale`.
- [ ] Convert DOM coordinates to final PNG coordinates using export scale/container width.
- [x] Add first coordinate-cropper scaffold that crops from `layout.json` rectangles.
- [x] Smoke-test coordinate cropper on a synthetic image/layout pair.
- [ ] Crop character images from final PNG by coordinates.
- [ ] Crop weapon images from final PNG by coordinates.
- [ ] Produce `crop_manifest.json` linking crops to API character/weapon records.
- [ ] Keep old binary-mask parser only as optional fallback, not primary path.
- [ ] Replace temporary layout schema with real HoYoLAB DOM selectors and API id linkage.

## Phase 5: UI Integration

- [x] Add UI action for HoYoLAB export.
- [ ] Add UI action for future HoYoLAB bundle import after the real bundle pipeline exists.
- [ ] Re-add export bundle import UI after the real `crop_manifest.json` pipeline exists.
- [ ] Display generated character crops with API metadata.
- [ ] Display generated weapon crops with API metadata.
- [ ] Ensure team builder works from new crop manifest.
- [ ] Preserve draggable team composition behavior.

## Phase 6: History Model

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
