# Main UI / Right Panel Integration Audit

Purpose: compact current audit for right-panel source ownership. This file is
not a development log; detailed AppShell routing rules live in
`APP_SHELL_WORKSPACE_PLAN.md`, and PvP UI direction lives in
`PVP_UI_ROADMAP.md`.

## Legacy Boundary

- `ui/main_window.py` and its old right column are not the final right-panel
  architecture.
- The old main-window right panel mixed team slots, timer widgets, save/history
  actions, and language/profile controls in one layout. Do not preserve that as
  the production structure.
- The legacy history path (`ui/run_history_window.py`, `runs_history.json`, and
  image-path-only team rows) is not the final History model.
- Useful behavior may still be extracted when it fits current architecture,
  especially wheel-friendly timer editing, timer validation/clamping, and
  compact run-result presentation.

## Current Target Ownership

The right panel should be organized by source ownership, not by whichever
workspace happens to be visible on the left:

```text
ui/right_panel/
  common/
  live_run/
    abyss/
    dps_dummy/
    gcsim/
  history/
  pvp/
    decks/
    play/
    draft/
      pick_ban/
      assignment/
      weapons/
      artifacts/
      gcsim/
      timers/
      result/
  settings/
  dock.py
  header.py
```

Ownership rules:

- `common/` owns shared visual primitives only: character slot cards, team
  cards, portrait/weapon/artifact mini-zones, shared metrics/styles/helpers, and
  non-domain-specific card UI.
- `live_run/` owns the normal current-run right panel used by Characters/Weapons,
  Artifact Browser, and GCSIM Browser. Abyss and DPS Dummy are submodes of the
  same live-run state; left workspaces should use the selected live-run target
  through controllers/adapters instead of owning right-panel widgets.
- `history/` owns the frozen snapshot adapter, host/empty state, and read-only
  interaction policy. A selected snapshot must use a separate instance of the
  same mode-specific Run presentation classes as `live_run`, not a parallel
  History team/slot/details/chamber widget tree. The History scope does not
  inherit live commands: it must not tick/edit timers, run GCSIM, mutate
  teams/equipment, save or reset live runs, query live account/cache data for
  old snapshots, or clear live Abyss/DPS/PvP state.
- `pvp/` owns PvP right-dock pages and internal Draft-stage panels. The left/main
  PvP workspace stays under `ui/pvp_browser/`.
- `settings/` owns Account/Data, language, DPS settings, and other global
  right-dock pages. Opening settings must not destroy current live-run, PvP, or
  History state.
- `dock.py` and `header.py` own fixed right-dock shell/header mechanics and
  stable-id routing.

## Current Implementation Snapshot

The global right-panel source-ownership refactor has been applied with no
intended behavior or visual changes:

- `ui/right_panel/common/metrics.py`, `slot_parts.py`, `slot_card.py`, and
  `team_card.py` own shared slot/team card metrics, HiDPI pixmap helpers,
  drag/drop MIME handling, portrait/weapon/artifact mini-zones, and the
  production `RightPanelSlotCardWidget` / `RightPanelTeamCardWidget` names.
- `ui/right_panel/live_run/panel.py` owns the current Run/Abyss/DPS right panel
  as `RunRightPanelWidget`, including run actions, chamber/timer cells, selected
  details, bonus strip/chips, and compact GCSIM/factual-DPS cells. The
  `run_workspace/right_panel_prototype_view_model.py` owner was intentionally
  left unchanged.
- `ui/right_panel/dock.py` and `ui/right_panel/header.py` own
  `RightOperationsDock` and `RightDockHeader`; `ui/app_shell.py` remains the
  routing/coordinator root.
- `ui/right_panel/settings/account_data.py` owns the Account/Data/global
  settings page. `ui/account_data_page.py` is only a compatibility wrapper.
- `ui/right_panel/history/viewer.py` currently owns the provisional independent
  frozen History viewer. The accepted target keeps History adapter/host/read-only
  policy under `ui/right_panel/history/` but replaces that separate viewer with
  a snapshot-bound instance of the shared Run presentation. `ui/history_browser/`
  continues to own the left History browser/list; its permanent PNG preview is
  also provisional.
- `ui/right_panel/pvp/` owns PvP right-dock pages:
  `host.py`, `decks/panel.py`, `play/panel.py`, `draft/panel.py`, and
  `draft/assignment/target_slot.py`. PvP page/stage/timer constants are
  canonical in `ui/right_panel/pvp/_shared.py`; `ui/pvp_browser/window.py`
  imports them instead of redefining them. Current PvP post-draft visual code is
  provisional and should not be treated as the MVP build-flow target. The MVP
  target is scoped reuse of the normal AppShell build pipeline:
  Characters/Weapons workspace, embedded Artifact Browser, GCSIM Browser,
  `RunSessionController` / `TeamBuilderState`, and `RunRightPanelWidget`.
  `ui/pvp_browser/window.py` keeps left/main PvP workspace classes and
  compatibility re-exports for old right-panel names.
- `ui/right_panel_prototype.py` is now a deprecated compatibility facade only.
  Old names such as `RightPanelPrototypeWidget`,
  `RightPanelSlotPrototypeWidget`, `RightPanelTeamPrototypeWidget`,
  `RunModeTabsWidget`, and `RightPanelRunActionsWidget` remain importable while
  new production imports should use `ui.right_panel.*`.
- Tests moved with ownership where practical: live-run right-panel tests now
  live under `tests/ui/right_panel/live_run/`, structural ownership/import
  coverage lives under `tests/ui/right_panel/`, AppShell routing remains under
  `tests/ui/app_shell/`, and left/main PvP behavior remains under
  `tests/ui/pvp_browser/` while importing right panels from their new owners.

Intentional non-goals of this refactor: do not switch `main.py` to AppShell, do
not delete `ui/main_window.py`, do not implement PvP Artifact equipment, and do
not implement scoped PvP GCSIM.

## Refactor Rule

Future right-panel work should keep the tree above as source ownership. When
ownership moves again, update imports and matching tests in the same task. Do
not weaken behavior coverage because files move.

Do not treat old prototype integration steps as current instructions. The
durable rule is the ownership split above plus AppShell-controlled routing.
