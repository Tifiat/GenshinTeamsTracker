# Tests

Purpose: keep the unit/integration test suite cheap to navigate and cheap to
run by feature area. Root `CODEX.md` and `TODO.md` stay as entrypoints; this
file owns the detailed test-layout rules.

## Layout

Mirror the primary project owner under `tests/`:

- `tests/hoyolab_export/account/` - account storage, equipment, import pipeline,
  offline profile, account stat sheet.
- `tests/hoyolab_export/artifacts/` - artifact DB/catalog integration, build
  snapshots, stat normalization, display stat effects.
- `tests/hoyolab_export/catalog/` - HoYoWiki/static catalogs, mapping reports,
  character/weapon stat snapshots, trait catalogs.
- `tests/hoyolab_export/abyss/` - HoYoLAB/export-side Abyss helpers and refresh
  orchestration.
- `tests/hoyolab_export/tournament/` - tournament ruleset validation.
- `tests/run_workspace/abyss/` - Run Workspace Abyss source data, factual DPS,
  runtime fixture/cache behavior.
- `tests/run_workspace/gcsim/` - backend GCSIM lifecycle, config generation,
  mapping, wave scenarios, cleanup, artifact runner.
- `tests/run_workspace/pvp/` - backend PvP deck validation, Decks UI preset
  persistence/conversion and root-resolved default path coverage
  (`test_deck_preset.py`), observed weapon-stack identity helper coverage
  (`test_weapon_identity.py`), current development PvP `.gttpvp` envelope/temp
  provider coverage (`test_profile_package.py`), Free Draft
  schedule/reducer/action log, team/weapon assignment validation, and
  timer/result behavior, local-account deck export provider/report behavior,
  draft-system registry behavior, deterministic Free Draft planner/account
  full-loop smoke behavior, Free Draft controller/projection behavior, Free
  Draft board/read-model projection behavior, backend-owned `unified_pool`
  projection/result-zone behavior, board projection validator and committed
  UI-contract sample behavior, PvP session bundle roundtrip/replay
  verification, plus report-only ruleset applicability, cost-preview, and
  ruleset/balance application tests. Manual backend smoke
  commands: `python -m
  run_workspace.pvp.full_loop_smoke`, `python -m
  run_workspace.pvp.free_draft_controller_smoke`, `python -m
  run_workspace.pvp.free_draft_controller_smoke --json`, `python -m
  run_workspace.pvp.free_draft_controller_smoke --step-demo`, `python -m
  run_workspace.pvp.ui_full_flow_smoke`, `python -m
  run_workspace.pvp.ui_full_flow_smoke --account`, `python -m
  run_workspace.pvp.ruleset_applicability_smoke`, `python -m
  run_workspace.pvp.account_deck_export_smoke`, `python -m
  run_workspace.pvp.account_full_loop_smoke`, `python -m
  run_workspace.pvp.session_bundle_smoke`, and `python -m
  run_workspace.pvp.ruleset_balance_smoke`.
- `tests/run_workspace/team/` - team-builder state and team-card data/view
  models.
- `tests/run_workspace/right_panel/` - right-panel view-model behavior owned by
  `run_workspace`.
- `tests/run_workspace/history/` - immutable History Snapshot Bundle schema,
  caller-rooted local read/write service behavior, complete frozen data for
  every occupied slot, bundle-local asset capture, and snapshot-to-shared
  right-panel view-model adapters. Future fixtures must prove that rendering a
  saved run needs no live account, DB, cache, or Run Session data. Catalog
  tests also cover cache-only/snapshot-only period union, deduplication,
  newest-first ordering, current-period preference, and no period-file writes.
- `tests/run_workspace/session/` - typed live Run Session ownership for
  AppShell mode/team/selection/timer/GCSIM runtime state.
- `tests/ui/app_shell/` - AppShell and legacy-main-window adapter tests,
  including cross-boundary routing tests for right-dock page selection,
  workspace/right-dock routing integration for History and PvP. History
  coverage should verify a separate snapshot-bound presentation state and an
  unchanged live session after entering/leaving History. PvP coverage includes
  `Decks`/`Play`/`Draft` header routing, preservation of normal Run state while
  switching PvP pages, root deck path coverage that prevents `ui/data`
  recreation, and active in-memory Draft board preservation after leaving and
  returning to PvP.
- `tests/ui/right_panel/common/` - shared right-panel visual primitives such as
  reusable slot/team/card primitives, `slot_parts.py` portrait/weapon/artifact
  mini-zones, shared metrics/styles/helpers, and non-domain-specific card UI.
- `tests/ui/right_panel/live_run/` - live Run/Abyss/DPS right-panel widgets,
  including current-run team slots, chamber/timer/result widgets, selected
  target behavior, and compact GCSIM summary/status cells. The former
  right-panel prototype bonus/smoke tests now live here and import production
  widgets from `ui.right_panel.*`.
- `tests/ui/right_panel/history/` - frozen snapshot adapters, host, and read-only
  policy around the shared mode-specific Run presentation. Coverage should
  verify reuse of common Run components, first-occupied-slot selection, frozen
  slot navigation/tooltips, disabled timers/state controls, hidden
  mode/Reset/Save/command controls, blocked mutation and drag/drop, and
  bundle-local assets. Do not pin the provisional separate details QLabel or
  permanent PNG preview as target behavior.
- `tests/ui/right_panel/pvp/` - PvP right-panel host/pages/stage panels,
  including Decks, Play, Draft pick/ban zones, future scoped build-flow routing,
  Timers/results, and Completed result/export panels. Tests must not bless a
  PvP-specific clone of the normal build right panel as MVP behavior.
- `tests/ui/right_panel/test_right_panel_ownership_imports.py` - structural
  right-panel ownership guardrails: new production imports, compatibility
  facades, canonical PvP constants/imports, and guardrails that MVP PvP build
  flow routes to the normal `RunRightPanelWidget` path instead of a custom PvP
  target-slot hierarchy.
- `tests/ui/pvp_browser/` - left/main PvP browser/workspace tests, including
  deck browser grids, left workspace create/edit/save/cancel coordination,
  card-grid viewport edit tint, selected-card edit markers, Play deck selectors,
  disabled/no-op invalid start, same-deck self-vs-self start, active Free Draft
  controller summary fields, Draft empty state, start-to-Draft routing,
  unified-pool current action/legal target rendering, one card per shared
  `character_id`, per-seat ownership/constellation markers, legal click mapping,
  illegal no-op behavior, same-deck seat-state independence, and a deterministic
  full Free Draft completion through UI card clicks, plus post-draft transition
  guards. Draft visual regression coverage requires one painted
  `PixelIconGrid` pool rather than QWidget/text cards, image paths for pool and
  result items, opposite-side P1/P2 constellation badges, legal-only click
  routing, removal of accepted targets from the pool, the full 22-position
  order strip, owner-colored frames independent of active turn, split Player 1
  left / Player 2 right frames for shared cards, owner badges retained on
  disabled cards, fixed 72x72 draft-order slots that reflow vertically without
  overlapping the central turn board at narrow/medium/wide widths, no tiny
  action labels inside order slots, right-panel pick/ban grids built through
  the same item adapter, uncluttered result portraits without pool ownership overlays, and a
  collapsed-by-default secondary action log. The Draft suite also pins the
  shared `CharacterFilterBar`, unified/player scope controls, semantic
  action-slot state, and empty-filter cleanup so hidden stale items cannot stay
  legal. MVP build-flow tests assert
  that scoped PvP assignment uses the
  normal AppShell quick-pick marker contract: team-colored `1-4` markers for
  team 1 and team 2, no PvP-only `SEL` badges, no grey disabled
  assigned-character overlays, and no custom PvP target-slot hierarchy in place
  of `RunRightPanelWidget`. They also cover normal slot-target selection,
  stable width-neutral seat highlighting driven by configurable global PvP
  player colors, action-colored translucent Draft-slot overlays, shared
  Abyss-style `10:00..05:00` remaining-clock wheel/keyboard timer inputs through
  the left Draft scene, remaining-to-elapsed backend conversion, separate enemy
  wave and solo/multi-target HP rendering in fixed table columns, equal-width
  timer columns across all chambers, table-style Solo/Multi DPS summary,
  six-value readiness, backend result finalization, and the completed
  elapsed-seconds total/chevron/difference scoreboard state. Account-settings
  tests pin both PvP color swatches and the
  reset-to-default behavior.
  Abyss-period admission tests remain a
  required future suite when that backend gate is implemented. They also cover
  selected-slot weapon assignment, Ready backend commits, both-Ready timer
  transition, imported-profile provider routing, per-seat scoped PvP runtime
  weapon state, no mutation of normal account equipment tables, no initial
  leakage of normal/imported owner badges into PvP source grids, stable
  post-draft source/right-panel widget identity across clicks, runtime weapon
  hydration after character remove/re-add, right-panel slot drag/drop swapping,
  and PvP Ready commits using scoped stack identity instead of display/type-name
  recomputation. Performance-regression coverage should include one-refresh
  source clicks, active-seat-only right-panel updates where possible, compact
  collapsed post-draft seat rows, and numeric/localized weapon type resolution
  to backend stack keys. Tests in this folder may instantiate the moved
  right-panel widgets when asserting cross-page behavior, but those imports
  should come from `ui.right_panel.pvp.*`, not from the old compatibility
  exports in `ui.pvp_browser.window`.
  PvP offscreen smoke has two modes: default synthetic fixtures for a stable
  temp-data full loop, and `--account` for real local PvP deck presets/account
  assets. The account mode should catch post-draft Ready regressions caused by
  numeric/localized weapon type or observed stack identity mismatches. It reads
  local data but must not write session/history files. PvP offscreen smoke
  should also verify the default deck path, first/second activation timing, that
  edit tint is scoped to the card grid viewports when this area changes, and
  that collapsed/inactive PvP seats do not reserve large empty right-panel
  geometry. Post-draft UI regressions should additionally pin the vertical
  right-panel accordion hierarchy, absence of a right painted side accent,
  collapse/expand without model/grid refresh, safe non-window source
  reparenting, and normal AppShell-compatible occupied-weapon swap behavior in
  scoped runtime state. Geometry regression tests must show both seat sections
  expanded at usable shell sizes for the 1408x640 minimum, 1600x900, and
  1920x1080 monitor profiles and pin equal left/right visual Y coordinates,
  equal seat heights, one physical character row, and the fixed character
  viewport. A dedicated content-sizing regression must show the weapon viewport
  matching the full natural multi-row grid when space exists and shrinking with
  vertical scroll only when the containing player section/window is too short.
  The assignment
  transition test installs an application event filter and rejects every newly
  shown top-level QWidget; this covers parentless `setVisible(true)` regressions
  that a `setParent(None)`-only assertion misses.
  Future finalized profile-package coverage must additionally prove two
  providers can expose the same character id with different constellation/image
  data, deterministic player-scope/shared Pick/shared Ban image selection,
  allowlisted SQLite/privacy contents, asset portability after source deletion,
  deck/DB/asset/hash validation, managed cleanup, and zero mutation of the main
  DB/local deck directory. See `PVP_PROFILE_PACKAGE.md`.
- `tests/ui/artifact_browser/` - Artifact Browser UI-side models/actions/stat
  localization.
- `tests/ui/gcsim_browser/` - GCSIM Browser UI worker behavior.
- `tests/ui/history_browser/` - History left-browser behavior: separate
  right-header Abyss/DPS Dummy/PvP routing, default mode from live Run,
  six-side enemy preview/tooltips, History-local period dropdown, cache-only
  empty states, compact frozen visual rows, and newest-first ordering.
- `tests/ui/utils/` - shared UI utility tests.
- `tests/ui/character_assets/` - `ui/character_assets.py` behavior.
- `tests/tools/future/` - reusable future/admin tools.

Root `tests/` should contain only package markers and top-level helpers. Do not
add new feature tests directly in the root.

## Running

Prefer the narrowest suite that covers the touched ownership area:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests\ui\artifact_browser -t . -p "test_*.py"
.\.venv\Scripts\python.exe -m unittest discover -s tests\ui\pvp_browser -t .
.\.venv\Scripts\python.exe -m unittest discover -s tests\ui\right_panel -t . -p "test_*.py"
.\.venv\Scripts\python.exe -m unittest discover -s tests\run_workspace\gcsim -t . -p "test_*.py"
.\.venv\Scripts\python.exe -m unittest discover -s tests\run_workspace\history -t . -p "test_*.py"
.\.venv\Scripts\python.exe -m unittest discover -s tests\run_workspace\session -t . -p "test_*.py"
.\.venv\Scripts\python.exe -m unittest discover -s tests\run_workspace\pvp -t .
.\.venv\Scripts\python.exe -m unittest tests.hoyolab_export.account.test_offline_profile
.\.venv\Scripts\python.exe -m run_workspace.pvp.free_draft_controller_smoke
.\.venv\Scripts\python.exe -m run_workspace.pvp.free_draft_controller_smoke --json
.\.venv\Scripts\python.exe -m run_workspace.pvp.free_draft_controller_smoke --step-demo
.\.venv\Scripts\python.exe -m run_workspace.pvp.ui_full_flow_smoke
.\.venv\Scripts\python.exe -m run_workspace.pvp.ui_full_flow_smoke --account
.\.venv\Scripts\python.exe -m run_workspace.pvp.ruleset_applicability_smoke
.\.venv\Scripts\python.exe -m run_workspace.pvp.account_deck_export_smoke
.\.venv\Scripts\python.exe -m run_workspace.pvp.account_full_loop_smoke
.\.venv\Scripts\python.exe -m run_workspace.pvp.session_bundle_smoke
.\.venv\Scripts\python.exe -m run_workspace.pvp.ruleset_balance_smoke
```

Full-suite command:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -p "test_*.py"
```

Run the full suite only for broad shared changes, test-infrastructure changes,
or when explicitly requested.

## Rules

- Place each test next to the primary source owner. For cross-boundary behavior,
  put the test under the coordinator that owns the contract being asserted.
- Keep tests deterministic and local. Do not use network, browser profile,
  real account data, generated assets, or ignored runtime folders unless the
  test is an explicit smoke/integration test with temp paths or mocks.
- Use temporary directories/databases and patch module-level paths instead of
  reading or mutating real `data/`, `assets/hoyolab/`, `hoyolab_export/profile`,
  or `data/gcsim/`.
- Prefer focused unit tests for domain logic. UI tests should isolate view-models
  when possible; Qt widget tests must construct only the widgets they verify and
  avoid app-wide startup.
- Name files by behavior or source area: `test_<feature>.py`. Use `_smoke` only
  for deliberately wider checks.
- Keep arrange/act/assert easy to edit. Add short comments around the part of a
  scenario that future tasks are expected to change; avoid comments that merely
  restate an assertion.
- Temporary fixtures, hardcoded research data, provisional adapters, or
  intentionally incomplete behavior need a short comment/docstring explaining
  the source, what future implementation should replace, and what contract the
  test pins.
- If fixtures are reused across folders, prefer a small colocated helper module
  such as `_fixtures.py` over importing helpers from another `test_*.py`. Some
  older tests still import from peer test modules; do not extend that pattern.
- Assert stable ids, typed fields, and data contracts instead of localized
  display text unless localization behavior itself is under test.
- When source files move or ownership changes, move the corresponding tests in
  the same task and update handoff references.
