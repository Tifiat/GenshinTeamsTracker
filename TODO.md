# TODO: GenshinTeamsTracker

This file is for future agents. Keep it short, current, English, and mostly ASCII. Do not preserve completed implementation history unless it changes how future work should be done.

## Workflow Rules

- Read `agent_context.md` first.
- Keep tool usage narrow and cheap.
- Do not run tests, app startup, imports, DB scans, or broad validation unless the user asks or the change needs it.
- Avoid scanning generated/private state:
  - `hoyolab_export/profile`
  - `data/`
  - `assets/hoyolab`
  - `assets/artifact_sets`
  - large JSON/image folders
- Update this file only with active tasks and useful follow-ups.

## Artifact Browser: Current Priority

- [ ] Stabilize draft custom-set editing.
- [ ] Fix custom set delete in the custom tab:
  - delete icon should switch the row to inline confirm;
  - check should delete;
  - x should cancel;
  - popup should not close just because delete was clicked.
- [ ] Add Enter-to-create for custom set name input.
- [ ] Add invalid empty-name state with localized "Enter name" placeholder.
- [ ] After custom set creation, close sets popup and visibly enter edit mode.
- [ ] Add blue edit-mode tint behind the artifact list.
- [ ] Remove delete button from bottom edit bar; keep save/cancel only.
- [ ] When editing a custom set, remove only that tag from selected custom filters.
- [ ] Disable normal QListView blue selection; use custom delegate highlight only.
- [ ] Add dirty-edit confirmation when the user closes/reloads/switches edit target with unsaved custom-set changes.
- [ ] Decide whether custom set rename is needed in this prototype; implement only if needed.
- [ ] Manually smoke-test custom set create/edit/delete with empty and non-empty sets.
- [ ] Manually smoke-test sorting + filtering while custom-set edit mode is active.
- [ ] Review whether edit-mode card click behavior conflicts with normal selection/open-details behavior.
- [ ] Keep custom-set data logic in `queries.py`/`store.py`; do not bury DB writes inside delegate/UI paint code.
- [ ] Remove or replace obsolete sandbox/probe helpers once the Artifact Browser path is stable.
- [ ] Wire the isolated Artifact Browser into the main UI when the prototype is stable.

## Artifact Browser: Sorting / Data

- [ ] Keep default sort stable: rarity desc, level desc, crit value desc, set name, artifact name, id.
- [ ] Keep Crit Value as the first sort option and Proc Count as the last sort option.
- [ ] Treat missing proc `times` as `0`; Artiscan/GOOD samples do not include proc counts.
- [ ] When implementing Artiscan import, use structured GOOD fields only; no image matching.
- [ ] Confirm Artiscan import path maps GOOD `setKey`, `slotKey`, and stat keys into existing `set_uid`, `pos`, and property types.
- [ ] If Artiscan import is added before HoYoLAB import, make sure missing HoYoLAB-only fields do not break browser sorting/filtering.

## Artifact Browser: Builds / Presets

- [ ] Design build preset model and UI after custom sets are stable.
- [ ] Add build preset selection/editing.
- [ ] Add artifact build editor after the browser is smoke-tested.
- [ ] Add future drag/drop of builds into the team window.
- [ ] Keep build data separate from visual skin and delegate rendering.

## Artifact Browser: Final UI Polish

- [ ] Do not polish the current QCheckBox/QWidget rows as final design.
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
- [ ] Decide whether `data/artifacts.db` is local generated state and should stay ignored.
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

- [ ] Re-check team builder behavior with `assets/hoyolab/*` paths and manifest-backed tooltips.
- [ ] Manually smoke-test character/weapon filter UI.
- [ ] Manually smoke-test two consecutive HoYoLAB updates after changing equipped weapons; old weapon icons should remain visible.
- [ ] Decide whether a separate future bundle import UI is still needed.
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
- [ ] Review untracked root/sample files and keep/ignore/remove deliberately:
  - `test_artiscan_few.json`
  - `artifacts_artiscan.json`
- [ ] Retry normal `git push` for local commit `1ae2de6` after previous GitHub Internal Server Error; do not force-push.

## Future History Features

- [ ] Design a new history schema.
- [ ] Support history categories:
  - Abyss;
  - Stygian Onslaught.
- [ ] Support version/cycle switching inside each category.
- [ ] Store teams and timers per saved run.
- [ ] Add fast visual export of history for a selected mode/version/cycle.
