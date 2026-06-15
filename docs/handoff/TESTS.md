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
  (`test_weapon_identity.py`), Free Draft
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
  run_workspace.pvp.ruleset_applicability_smoke`, `python -m
  run_workspace.pvp.account_deck_export_smoke`, `python -m
  run_workspace.pvp.account_full_loop_smoke`, `python -m
  run_workspace.pvp.session_bundle_smoke`, and `python -m
  run_workspace.pvp.ruleset_balance_smoke`.
- `tests/run_workspace/team/` - team-builder state and team-card data/view
  models.
- `tests/run_workspace/right_panel/` - right-panel view-model behavior owned by
  `run_workspace`.
- `tests/run_workspace/history/` - immutable History Snapshot Bundle schema and
  caller-rooted local read/write service behavior.
- `tests/run_workspace/session/` - typed live Run Session ownership for
  AppShell mode/team/selection/timer/GCSIM runtime state.
- `tests/ui/app_shell/` - AppShell and legacy-main-window adapter tests,
  including cross-boundary routing tests for right-dock page selection,
  workspace/right-dock routing integration for History and PvP, PvP
  `Decks`/`Play`/`Draft` header routing, preservation of normal Run state while
  switching PvP pages, root deck path coverage that prevents `ui/data`
  recreation, and active in-memory Draft board preservation after leaving and
  returning to PvP.
- `tests/ui/right_panel/common/` - shared right-panel visual primitives such as
  reusable slot/team/card primitives, portrait/weapon/artifact mini-zones,
  shared metrics/styles/helpers, and non-domain-specific card UI.
- `tests/ui/right_panel/live_run/` - live Run/Abyss/DPS right-panel widgets,
  including current-run team slots, chamber/timer/result widgets, selected
  target behavior, and compact GCSIM summary/status cells.
- `tests/ui/right_panel/history/` - frozen read-only snapshot viewer widgets.
  Coverage should assert no live timer/GCSIM/equipment/save/reset behavior is
  exposed by the History viewer.
- `tests/ui/right_panel/pvp/` - PvP right-panel host/pages/stage panels,
  including Decks, Play, Draft pick/ban zones, Assignment, Weapon assignment,
  future Artifact equipment, optional scoped PvP GCSIM, Timers/results, and
  Completed result/export panels.
- `tests/ui/pvp_browser/` - left/main PvP browser/workspace tests, including
  deck browser grids, left workspace create/edit/save/cancel coordination,
  card-grid viewport edit tint, selected-card edit markers, Play deck selectors,
  disabled/no-op invalid start, same-deck self-vs-self start, active Free Draft
  controller summary fields, Draft empty state, start-to-Draft routing,
  unified-pool current action/legal target rendering, one card per shared
  `character_id`, per-seat ownership/constellation markers, legal click mapping,
  illegal no-op behavior, same-deck seat-state independence, and a deterministic
  full Free Draft completion through UI card clicks, plus post-draft left/main
  source-zone layout guards for image-backed picked-character and weapon
  `PixelIconGrid` cards.
  PvP offscreen smoke should also verify the default
  deck path, first/second activation
  timing, and that edit tint is scoped to the card grid viewports when this area
  changes.
- `tests/ui/artifact_browser/` - Artifact Browser UI-side models/actions/stat
  localization.
- `tests/ui/gcsim_browser/` - GCSIM Browser UI worker behavior.
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
