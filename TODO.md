# TODO: GenshinTeamsTracker

This file is for future agents. Keep it short, current, English, and mostly ASCII. Do not preserve completed implementation history unless it changes how future work should be done.

## Workflow Rules

- Read `agent_context.md` first.
- Keep tool usage narrow and cheap.
- Do not run tests, app startup, imports, DB scans, or broad validation unless the user asks or the change needs it.
- Use `.venv\Scripts\python.exe` for local checks when the system interpreter lacks project dependencies.
- Avoid scanning generated/private state:
  - `hoyolab_export/profile`
  - `data/`
  - `assets/hoyolab`
  - `assets/artifact_sets`
  - large JSON/image folders
- Update this file only with active tasks and useful follow-ups.

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
  - saving preserves/updates selected targets;
  - cancel restores target filter state without silently losing draft changes.
- [ ] Polish target selector width, item spacing, and preview target icon row after visual review.
- [ ] Re-check fixed preset preview geometry:
  - 5 artifact mini-slots + 2 set-bonus slots fit without clipping;
  - left/right padding is visually balanced;
  - stat summary remains 2 columns x 5 rows.
- [ ] Later round/crop normal character preview icons with transparent alpha corners or another lightweight approach.
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
  - move reset controls near the popup/panel header where possible instead of bottom bars;
  - prefer one shared helper/function for clearing selected items in list-like selectors instead of duplicating three separate reset implementations.

## Artifact Browser: Builds / Presets

- [ ] Keep build presets as shared ownership categories, not "one build = one character".
- [ ] Universal is a target at the same level as character targets.
- [ ] Selected target filters use intersection semantics. Do not auto-include Universal unless Universal is selected.
- [ ] Keep preset panel compact and fixed-width. Future character/target expansion belongs in the middle target selector column.
- [ ] Add color highlighting for build summary Crit Value and Proc Count later; thresholds are not decided yet.
- [ ] Add future character target UX refinements only after the MVP is visually stable.
- [ ] Add future drag/drop of builds into the team window.
- [ ] Keep build data separate from visual skin and delegate rendering.

## Artifact Browser: Sorting / Data

- [ ] Keep default sort stable: rarity desc, level desc, effective crit value desc, set name, artifact name, id.
- [ ] Circlet CV sorting should include CR/CD main stat contribution for sorting.
- [ ] Keep Crit Value as the first sort option and Proc Count as the last sort option.
- [ ] Treat missing proc `times` as `0`; Artiscan/GOOD samples do not include proc counts.
- [ ] When implementing Artiscan import, use structured GOOD fields only; no image matching.
- [ ] Confirm Artiscan import path maps GOOD `setKey`, `slotKey`, and stat keys into existing `set_uid`, `pos`, and property types.

## Artifact Browser: Final UI Polish

- [ ] Do not polish current QWidget rows as final design.
- [ ] After functionality is stable, redesign the browser toward a Genshin-like interface.
- [ ] Prefer model/view/delegates/theme/assets for final visuals.
- [ ] Replace set-list checkbox rows with large clickable rows:
  - icon left;
  - name;
  - count right;
  - selected frame/background.
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
