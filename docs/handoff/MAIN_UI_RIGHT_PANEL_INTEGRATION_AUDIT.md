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
- `history/` owns the read-only frozen snapshot viewer. It may reuse common
  visuals but must not tick timers, run GCSIM, mutate teams/equipment, save or
  reset live runs, query live account/cache data for old snapshots, or clear
  live Abyss/DPS/PvP state.
- `pvp/` owns PvP right-dock pages and internal Draft-stage panels. The left/main
  PvP workspace stays under `ui/pvp_browser/`.
- `settings/` owns Account/Data, language, DPS settings, and other global
  right-dock pages. Opening settings must not destroy current live-run, PvP, or
  History state.
- `dock.py` and `header.py` own fixed right-dock shell/header mechanics and
  stable-id routing.

## Refactor Rule

A candidate code task is the global right-panel source-ownership refactor toward
the tree above. When ownership moves, update imports and matching tests in the
same task. Do not weaken behavior coverage because files move.

Do not treat old prototype integration steps as current instructions. The
durable rule is the ownership split above plus AppShell-controlled routing.
