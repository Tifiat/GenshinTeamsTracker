# TODO: GenshinTeamsTracker

This file is for future agents. Keep it short, current, English, and mostly ASCII. Do not preserve completed implementation history unless it changes how future work should be done.

## Workflow Rules

- Read `CODEX.md` first.
- Keep tool usage narrow and cheap.
- Do not run tests, app startup, imports, DB scans, or broad validation unless the user asks or the change needs it.
- Use `.venv\Scripts\python.exe` for local checks when the system interpreter lacks project dependencies.
- Avoid scanning generated/private state:
  - `hoyolab_export/profile`
  - `data/`
  - `assets/hoyolab`
  - `assets/artifact_sets`
  - large JSON/image folders
- Expensive repeatable UI work should use both in-memory cache and persistent cache under `data/cache/...`; do not leave image processing/parsing in hot UI paths.
- Update this file only with active tasks and useful follow-ups.

## Current Artifact Browser Implementation Notes

- Compact build preset row metadata is implemented:
  - no active bonus shows `NO / BONUS`;
  - single active 2p shows one set icon with badge `2`;
  - 4p shows one set icon with badge `4`;
  - 2+2 shows one diagonal composite icon with one badge `2`;
  - sands/goblet main stats show as a compact badge.
- Compact preset-row bonus rendering is separate from build preview block set bonus rendering.
- Compact preset-row bonus icons use in-memory cache plus persistent PNG cache at `data/cache/ui/preset_bonus_icons/`.
- Build target preview strip is a baked pixmap strip, not many child widgets; target preview icons are not clickable and no tooltip is planned there.
- Target preview caches:
  - `data/cache/ui/target_preview_icons/`;
  - `data/cache/ui/target_preview_strips/`.
- Build preview block geometry is explicit and should keep this structure: target strip, 5 artifact mini-cards, set bonus preview container, summary stats block.

## Artifact Browser: Current Priority

- [ ] Manually review the new Build Target Selector MVP:
  - layout is `Artifact grid | Build Target Selector | Preset panel`;
  - filter strip stays fixed;
  - Universal is always visible;
  - character list scrolls;
  - selected targets filter presets by intersection.
- [ ] Verify target persistence:
  - creating a preset with Universal and/or characters creates one preset with all selected targets;
  - editing a saved preset reflects its targets in the selector;
  - saving preserves/updates edited preset targets, then restores previous browsing target selection;
  - cancel restores previous browsing target selection without silently losing draft changes.
- [ ] Polish target selector width and item spacing after visual review.
- [ ] Manually verify build preview and target preview after the latest geometry/cache work:
  - target preview strip is a baked pixmap strip;
  - drag-scroll and wheel-scroll work without visible scrollbars;
  - gradient chevrons appear only on scrollable edges;
  - Universal uses `users.svg` through the auto-contrast helper;
  - 5 artifact mini-cards + set-bonus container fit without clipping;
  - stat summary remains 2 columns x 5 rows.
- [ ] Later round/crop normal character preview portraits with transparent alpha corners, a lightweight mask, or another cheap approach. Do not do this before the current deadline.
- [ ] Smoke-test build preset lifecycle:
  - no selected target hides create/list and keeps preview placeholders visible;
  - selecting one target shows only presets containing that target;
  - selecting multiple targets shows only presets containing all selected targets;
  - save/cancel/delete still work for saved and new drafts.
- [ ] Smoke-test custom sets after the build target selector changes:
  - create/edit/delete;
  - dirty-confirm;
  - edit highlight and bottom save/cancel bar;
  - filters/sorting while edit mode is active.
- [ ] Wire the isolated Artifact Browser into the main UI when the prototype is stable.
- [ ] Later unify reset controls in target selector, sort popup, and sets popup:
  - move reset controls near the popup/panel header where possible instead of separate bottom areas;
  - prefer one shared helper/function for clearing selected items in list-like selectors instead of duplicating three separate reset implementations.

## Artifact Browser: Builds / Presets

- [ ] Keep build presets as shared ownership categories, not "one build = one character".
- [ ] Universal is a target at the same level as character targets.
- [ ] A preset can belong to multiple targets.
- [ ] Selected target filters use intersection semantics. Do not auto-include Universal unless Universal is selected.
- [ ] When editing a preset, the selector temporarily switches to that preset's targets and must restore the previous browsing selection on Save/Cancel.
- [ ] Keep preset panel compact and fixed-width. Future character/target expansion belongs in the middle target selector column.
- [ ] Keep build preset row names flexible:
  - MarqueeButton should occupy leftover row space until fixed metadata/actions;
  - long names should marquee/clip, not expand row width;
  - do not reintroduce horizontal scrolling in the preset list.
- [ ] Add color highlighting for build summary Crit Value and Proc Count later; choose thresholds/colors first.
- [ ] Add future character target UX refinements only after the MVP is visually stable.
- [ ] Add future drag/drop of builds into the team window.
- [ ] Keep build data separate from visual skin and delegate rendering.
- [ ] Keep SVG UI icons on `ui/utils/icon_utils.py` auto-contrast helpers; do not reintroduce direct raw SVG loading or hardcoded final icon colors.

## Artifact Browser: Set Bonuses / Tooltips

- [ ] Add custom tooltip support for set bonus icons wherever set bonus icons are shown, except the target preview strip.
- [ ] Tooltip behavior:
  - icon with `2`: show 2-piece bonus description;
  - icon with `4`: show 4-piece bonus description;
  - 2+2: show both 2-piece descriptions.
- [x] Refactor existing custom tooltip logic into `ui/utils/tooltips.py`.
- [x] Extend HoYoWiki artifact set catalog/import pipeline to collect 2p/4p bonus descriptions.
- [x] Store set bonus descriptions with language/content locale.
- [x] Content language should follow HoYoLAB/API content language, not necessarily UI language.
- [x] Add DB/catalog support for set bonus descriptions if missing.
- [ ] Wire stored set bonus descriptions into custom tooltip UI.

## Artifact Browser: Popup Selection UI

- [ ] Make Sort popup and Sets popup selection behavior visually consistent with artifacts/targets/presets.
- [ ] Remove visible checkbox/checkmark UI from those popup rows.
- [ ] Sort popup should display selected order number on the right, not before text.
- [ ] Sets popup should use the same selected-row style where applicable.
- [ ] Sort game/custom sets by number of owned pieces descending.

## Artifact Browser: Target Selector Follow-Ups

- [x] Add region filters through a popup with region icons.
- [x] Use HoYoWiki character gallery region tags as the current data source.
- [ ] Future: replace localized-name region joins with a stable character id mapping if HoYoWiki exposes one.

## Artifact Browser: Sorting / Data

- [ ] Keep default sort stable: rarity desc, level desc, effective crit value desc, set name, artifact name, id.
- [ ] Circlet CV sorting should include CR/CD main stat contribution for sorting.
- [ ] Keep Crit Value as the first sort option and Proc Count as the last sort option.
- [ ] Treat missing proc `times` as `0`; Artiscan/GOOD samples do not include proc counts.

## Artifact Import / JSON

- [ ] Implement artifact import from JSON, initially for Artiscan-compatible data.
- [ ] Use structured GOOD fields only; no image matching.
- [ ] Map GOOD `setKey`, `slotKey`, and stat keys into existing `set_uid`, `pos`, and property types.
- [ ] Imported JSON artifacts do not have proc counts.
- [ ] Prevent duplicates: the same artifact must not be inserted twice.
- [ ] Allow multiple JSON imports.
- [ ] Add a safe "clear imported from JSON" action.
- [ ] Clearing JSON-imported artifacts must not delete pre-existing duplicate artifacts that were kept instead of imported copies.
- [ ] After clearing imported artifacts, clear corresponding preset slots.
- [ ] Then ask in Russian: "После удаления соответствующие слоты в пресетах будут очищены. Удалить эти пресеты?" with confirm/cancel.
- [ ] First-day patch TODO after JSON import: automatic proc counting for imported artifacts.
- [ ] Check other export/import services and compatibility.

## Artifact Browser: Final UI Polish

- [ ] Treat current QWidget rows as prototype UI, not the final visual layer.
- [ ] After functionality is stable, redesign the browser toward a Genshin-like interface.
- [ ] Prefer model/view/delegates/theme/assets for final visuals.
- [ ] Keep `store`, `queries`, and models independent from the final skin.

## Future UI Architecture / Performance

- [ ] After Artifact Browser functionality is stable, run a separate UI/performance refactor.
- [ ] Use model/view for large or frequently updated lists:
  - characters;
  - weapons;
  - artifacts;
  - game sets;
  - custom sets/tags;
  - build presets;
  - future build drag/drop slots.
- [ ] Avoid one QWidget per item in large lists.
- [ ] Route final textures/frames/backgrounds through a separate theme/assets layer.

## Artifact Import / DB Cleanup

- [ ] Do not do final cleanup of old DB physical schema until the new browser path is stable.
- [ ] Later migration: recreate/drop old `artifacts.icon_id` and `artifact_icons` physical leftovers if they still exist in local DBs.
- [ ] Keep `artifact_set_piece_icons` as the browser icon source by `(set_uid, pos)`.
- [ ] Do not reintroduce per-artifact icon cache or `artifact_icons` fallback.

## Offline Profile Export/Import

- [ ] When improving offline profile export/import, include `data/hoyolab/account_language.json` with:
  - `account_character_details.json`
  - `account_characters.json`
  - `account_weapons.json`
  - `crop_manifest.json`
- [ ] Manually smoke-test offline profile export/import from the PySide UI.
- [ ] Manually smoke-test sign-out with both keep/delete history choices.

## Main UI Follow-Ups

- [ ] Main UI character asset loading/filter/sort helpers are shared through `ui/character_assets.py`; keep main window and Artifact Browser selector behavior aligned.
- [ ] Re-check team builder behavior with `assets/hoyolab/*` paths and manifest-backed tooltips.
- [ ] Manually smoke-test character/weapon filter UI.
- [ ] Preserve draggable team composition behavior while integrating Artifact Browser/builds.

## Localization

- [ ] Add localization keys for any new UI screens as they are built.
- [ ] Keep `ru`, `en`, and `pt-br` locale files in sync.
- [ ] Keep dynamic HoYoLAB/API display names in the HoYoLAB content language; do not tie them to app UI language.

## Git / Release Hygiene

- [ ] Commit seeded artifact catalog resources:
  - `data/static/artifact_set_catalog.json`
  - `assets/artifact_sets`
- [ ] Keep local account/generated state ignored:
  - `data/hoyolab`
  - `data/artifacts.db`
  - `assets/hoyolab`
  - browser profile/session/debug/download outputs
- [ ] Keep Artiscan sample files under `samples/artiscan/` unless a future import task needs another layout.
- [ ] Retry normal `git push` for local commit `1ae2de6` after previous GitHub Internal Server Error; do not force-push.

## Future History Features

- [ ] Design a new history schema.
- [ ] Support history categories:
  - Abyss;
  - Stygian Onslaught.
- [ ] Support version/cycle switching inside each category.
- [ ] Store teams and timers per saved run.
- [ ] Add fast visual export of history for a selected mode/version/cycle.
