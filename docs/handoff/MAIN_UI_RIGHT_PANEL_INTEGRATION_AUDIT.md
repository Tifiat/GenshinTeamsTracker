# Main UI / Fixed Right Panel Integration Audit

Purpose: pre-implementation audit for replacing the legacy main-window right
panel with the isolated Right Panel Prototype v6 and moving the left side toward
switchable workspaces. This is an audit only; it records integration boundaries
and a staged migration path.

## Current Main Layout

Entry point:

- `ui/main_window.py::App`

Current structure:

- `App` is a `QWidget`, not a `QMainWindow`.
- Top-level layout is `self.main = QHBoxLayout(self)`.
- `build_left_panel()` adds a plain left `QVBoxLayout` with stretch `2`.
- `build_right_panel()` adds a plain right `QVBoxLayout` with stretch `1`.
- There is no `QSplitter`, no `QStackedWidget`, and no workspace/router layer.

Left side today:

- HoYoLAB/profile actions at the bottom.
- Weapon filter row + weapon `QScrollArea`/`QGridLayout`.
- Character filter row + character `QScrollArea`/`QGridLayout`.
- `resizeEvent()` calls `update_grids_delayed()`, which reloads both character
  and weapon grids after a short timer.

Right side today:

- two legacy team rows of `ui.widgets.team.TeamSlot`;
- three `AbyssFloorRow` timer rows;
- total label;
- reset/save/history buttons;
- language switcher.

Fixed-width right panel implication:

- Replace the right `QVBoxLayout` column with a real widget container, likely a
  `RightPanelPrototypeWidget` or wrapper, and set fixed/min/max width there.
- Keep the left side flexible with stretch `1`.
- Avoid reusing the old right panel layout as a base; it mixes team slots,
  timers, save/history buttons, and language controls directly in one column.

## Right Panel Prototype Integration

Reusable directly:

- `run_workspace/right_panel_prototype_view_model.py`
  - `build_right_panel_prototype_view_model(...)`
  - `RightPanelPrototypeViewModel` and nested view-model dataclasses
  - selected character details, display stats, bonus source items, elemental
    resonance, Moonsign, Hexerei, weapon tooltip data, build mini-set data
- `ui/right_panel_prototype.py`
  - `RightPanelPrototypeWidget`
  - card widgets, selected details widget, bonus strip, custom tooltip wiring
- `run_workspace/team_builder.py`
  - typed `TeamBuilderState`, `TeamBuilderTeamState`, `TeamBuilderSlotState`
  - selected character/weapon/build refs
- `run_workspace/display_stats.py`
  - current virtual display-stat calculation

Smoke-only / do not migrate directly:

- `ui/right_panel_prototype_smoke.py`
  - fake state builders;
  - `--real-thoma` convenience;
  - deterministic Moonsign/Hexerei/resonance presets;
  - fallback character/weapon selection helpers for visual smoke only.

Production-suitable runtime path:

- account characters/weapons come from SQLite account adapters;
- selected build details can come through existing artifact build snapshot/team
  card data path;
- Right Panel view-model already consumes `TeamBuilderState`, so the missing
  production piece is a main-window/controller adapter that updates
  `TeamBuilderState` when the user selects characters, weapons, builds, mode,
  and timers.

Minimal adapter needed:

- maintain one app-level `TeamBuilderState`;
- expose selected team/slot/mode;
- on character/weapon/build selection, update the state and rebuild the right
  panel view-model;
- keep smoke preset builders out of this path.

## Timer / Run Logic

Existing UI:

- `ui.widgets.timers.AbyssTimerCell`
- `ui.widgets.timers.AbyssFloorRow`
- `ui/main_window.py::calculate_abyss`

Existing backend model:

- `run_workspace.models.AbyssTimerState`
- `calculate_abyss_chamber_result(...)`
- `RunSnapshotV1`
- `build_legacy_abyss_run_snapshot(...)`

What to preserve:

- wheel-friendly timer spinbox behavior;
- clamping/normalization rules in `calculate_abyss_chamber_result(...)`;
- warning semantics for impossible/invalid timer states;
- the idea that timer state belongs to run state, not to raw widget labels.

What is obsolete:

- saving only legacy image paths from `TeamSlot`;
- using `runs_history.json` as the long-term history model;
- old right-panel timer rows as the final visual design.

Recommended future home:

- timer state should live in a Run Workspace/controller model, separate from the
  right panel widget;
- the right panel may display/edit timer rows through view-model data, but
  should not own persistence or saved-run history by itself;
- saved runs should later snapshot typed team/build/weapon data, not live UI
  widgets or image paths.

## Left Workspace Model

Recommended primitive:

- Use a left-side `QStackedWidget` (or a thin workspace controller wrapping one)
  for future modes.

Why:

- character/weapon selection, Artifact Browser, GCSIM, and history are mutually
  exclusive left-side workspaces;
- fixed right panel can remain visible while the left workspace changes;
- avoids coupling Artifact Browser/GCSIM/history layout to right-panel internals.

Initial left workspace stages:

- first workspace: existing character/weapon selection grid, moved into a
  widget wrapper with minimal behavior changes;
- later workspaces: Artifact Browser, GCSIM, history.

Keep current character/weapon grid:

- initially embed the current left panel content as the first stacked page;
- then replace its data flow with typed `TeamBuilderState` selection updates
  rather than legacy drag image-path slots.

## Artifact Browser Embedding Audit

Current class:

- `ui.artifact_browser.window.ArtifactBrowserWindow(QWidget)`

Standalone assumptions:

- sets `self.setWindowFlag(Qt.Window, True)`;
- calls `setWindowTitle(...)`;
- calls `resize(1180, 760)`;
- owns popups and modal unsaved-change message boxes;
- loads its own `ArtifactBrowserStore` from DB on init/refresh.

Useful resize/grid behavior:

- artifact grid is `QListView` in icon mode with fixed `GRID_SIZE`;
- `resizeEvent()` schedules `update_adaptive_target_panel_width()`;
- adaptive logic adjusts build-target panel width so artifact viewport lands on
  clean grid columns when possible;
- native Windows size-move throttling avoids recalculating during live drag.

Paint-order rule:

- visuals that intentionally extend outside `QListView` item cells, such as
  Artifact Browser owner side-icons, must be painted in a viewport overlay-pass
  after normal delegate painting. Painting them inside the item delegate lets
  neighboring item hover/repaint updates erase the overlapping portion.

Embedding risks:

- `Qt.Window` flag must be optional or avoided in embedded mode;
- initial standalone `resize(...)` should not drive embedded size;
- adaptive width logic currently assumes three internal columns: artifact list,
  target panel, build panel. It can still work embedded if the containing
  workspace provides stable width, but needs visual verification;
- popups should anchor to the embedded widget/screen correctly;
- unsaved edit prompts are still valid but should be tested when the browser is
  not a top-level window.

Recommended later extraction:

- make a reusable browser content widget or add an explicit embedded mode to
  `ArtifactBrowserWindow`;
- keep store/model/delegate/grid/adaptive logic;
- parameterize top-level window behavior, title/resize, and close handling.

## History Audit

Current history:

- `ui.run_history_window.RunHistoryWindow`;
- reads/writes `runs_history.json`;
- uses `RunCard`, `TeamRow`, `FlowLayout`;
- supports Ctrl+wheel scale;
- cards display legacy image-path teams and timer totals.

Worth preserving:

- some card/row scaling ideas;
- deletion/reload flow as reference only;
- timer total display concept.

Obsolete:

- long-term data shape in `runs_history.json`;
- legacy image-path-only team rows;
- separate old history window as the final history UI.

Recommendation:

- do not migrate this UI directly into the left workspace;
- future history workspace should use immutable saved-run snapshots based on
  typed TeamBuilder/Run Workspace data.

## Proposed Migration Plan

Stage 1: Fixed Right-Panel Shell

- Wrap current main layout into explicit left/right container widgets.
- Add fixed-width right container.
- Embed `RightPanelPrototypeWidget` on the right.
- Keep old left character/weapon area mostly intact.

Stage 2: Real Team/Run State Adapter

- Introduce app-level `TeamBuilderState` and selected team/slot.
- Convert legacy character/weapon grid actions to update typed state.
- Feed `build_right_panel_prototype_view_model(...)` from real state.
- Keep smoke builders out of production.

Stage 3: Left Workspace Container

- Add `QStackedWidget` for the left side.
- First page is current character/weapon selection.
- Add lightweight workspace switching controls without changing right panel.

Stage 4: Artifact Browser Workspace

- Add embedded mode/content widget for Artifact Browser.
- Preserve adaptive grid behavior and build preset logic.
- Wire selected build/preset into `TeamBuilderState`.

Stage 5: GCSIM / History Modes

- Add GCSIM left workspace after reading `docs/handoff/GCSIM.md`.
- Add new history workspace using immutable snapshots, not legacy
  `runs_history.json` card UI.

Stage 6: Cleanup

- Remove legacy right-panel team slots/timer column after replacement is stable.
- Retire legacy history window/data path after a migration/export decision.

## What Not To Do In The First Migration Patch

- Do not migrate Artifact Browser and right panel in the same patch.
- Do not build GCSIM/history workspaces immediately.
- Do not preserve old right panel as a parallel final UI.
- Do not save future runs from live widget/image-path state.
- Do not infer current-equipped weapon identity as canonical account weapon
  storage.
