# Run Workspace Session And Snapshot Contract

Date: 2026-06-02

Scope: planning and data contract for the next Run Workspace stages before
history and GCSIM implementation. This is not a UI implementation plan for
legacy cleanup, and it does not switch `main.py`.

## Current State

- `AppShell` is the future root coordinator and already owns independent
  in-memory `TeamBuilderState` selections for Abyss and DPS Dummy.
- `RightOperationsDock` is the fixed right operation area. Its current
  `RightPanelPrototypeWidget` still has display-only chamber rows and action
  labels.
- `run_workspace.team_builder` is the typed team composition layer.
- `run_workspace.models` contains an early legacy Abyss snapshot adapter:
  `AbyssTimerState`, `calculate_abyss_chamber_result(...)`, `RunSnapshotV1`,
  and `build_legacy_abyss_run_snapshot(...)`.
- AppShell now uses live in-memory Abyss timer state for the compact right-dock
  chamber table. T1/T2 timer edits update controller state and the right-panel
  view model immediately. T2 follows T1 until manually edited; if T1 is edited
  below current T2, T2 clamps to T1 and returns to follow mode. Reset/save/history
  persistence is still future.
- The next implementation step is current in-memory run/session state and result
  calculation. Saved snapshot models are intentionally later.
- `ui/widgets/timers.py` contains useful timer editing behavior but must not
  remain the durable owner of run/session state.
- `ui/run_history_window.py` and `runs_history.json` are legacy image/path
  history. They are not the future history model.
- `docs/handoff/GCSIM.md` documents future simulator integration. GCSIM must
  consume snapshots/config data, not UI widgets.

## Production Switch Blockers

Before `main.py` can safely switch to `AppShell`, the new path needs a typed
run/session layer that replaces the legacy right-panel ownership of timers,
save/reset, and history entrypoints.

Required before switch:

- `RunSessionState` or equivalent per-mode session model:
  - active run type: `abyss` or `dps_dummy`;
  - per-mode `TeamBuilderState`;
  - selected team/slot target;
  - timer/result state for the active mode;
  - factual result rows derived from scenario data;
  - dirty/reset state;
  - external-bonus toggle state if it remains run-scoped.
- `RunSessionController` or equivalent coordinator:
  - set/switch mode without losing per-mode team state;
  - accept team mutations from `AppShellController` or replace that layer;
  - own reset/save commands;
  - build immutable run snapshots;
  - expose a right-panel view model without reading widgets;
  - route history opening to the correct left workspace state.
- Right dock action wiring:
  - Reset must reset the current run session, not legacy widgets.
  - Save must build and persist an immutable snapshot for the current run type.
  - History must open/select a left History workspace, not a floating legacy
    history window or right-dock-only button.
- Startup scaling and Account/Data behavior from `AppShell` remain required.

Not required before the first `main.py` switch:

- full GCSIM runner;
- full new History browser UI, if save can be disabled until history exists;
- PvP;
- legacy history migration;
- exact full-Abyss enemy wave simulation.

## Session State Shape

The run/session model should keep three domains separate:

- Team Builder:
  - selected characters, selected current weapons, selected/current artifact
    builds, hydrated details, warnings;
  - no timers or history persistence.
- Scenario / Run:
  - Abyss chamber/timer/enemy context;
  - DPS Dummy target/setup/factual result context;
  - future PvP match/rules context.
- Presentation / Export:
  - right-panel view model;
  - history row/card view model;
  - PNG/XLSX/export surfaces.

Recommended first dataclasses or equivalents:

- `RunSessionState`
  - `schema_version`;
  - `run_type`;
  - `team_state`;
  - `scenario_state`;
  - `selected_team_index`;
  - `selected_slot_index`;
  - `external_bonuses_enabled`;
  - `last_sim_result_id` or compact sim status only.
- `AbyssRunState`
  - season/period identity when available;
  - chamber rows, each with team 1/team 2 timer left seconds;
  - optional chamber enemy/HP context;
  - calculated factual result rows.
- `DpsDummyRunState`
  - target label/id;
  - target HP or dummy setup;
  - elapsed/duration seconds;
  - factual damage/DPS entry if manually entered or measured;
  - optional GCSIM result reference later.

The existing `AppShellController` may remain as an adapter during the next
stage, but durable run/session state should not be split across hidden UI
widgets and controller fields.

## Immutable Snapshot Contract

Saved runs must be immutable structured snapshots. They must not depend on
later changes to account characters, current equipment, build presets, icon
crops, or localized display names.

Every snapshot should include:

- `schema_version`;
- `run_type`;
- `created_at`;
- `source` (`app_shell`, `legacy_right_panel`, debug smoke, import, etc.);
- optional account/profile identity metadata;
- game/version metadata if known;
- content language used for display labels at save time;
- teams with ordered slots;
- scenario/run result data;
- warnings and provenance notes.

Each team slot snapshot should store, when available:

- character id, name, level, element, rarity, constellation;
- stable local portrait/side-icon path or asset key for display fallback;
- weapon id, name, level, promote level, rarity, refinement,
  `weapon_fingerprint`, icon path, passive/static effect references that were
  visible at save time;
- artifact/current-build snapshot:
  - actual artifact ids by slot;
  - artifact slot records needed for tooltips;
  - active set bonuses and set icons;
  - total stats, CV, proc count, missing positions, warnings;
  - selected preset/build id/name only as provenance, not as the source of
    truth;
- calculated/visible detail rows needed by history/export;
- source notes such as current-equipment vs saved preset.

Snapshots may include local icon paths for convenience, but image paths are not
identity. If a path goes missing later, history should still show meaningful
text and structured details.

## Abyss Snapshot

Abyss snapshots should contain:

- run type `abyss`;
- season/period/floor metadata when known;
- two teams;
- chamber records in order;
- for each chamber:
  - chamber index/label;
  - team 1 left seconds;
  - team 2 left seconds;
  - start seconds, normally 600;
  - normalized timer state;
  - team 1 elapsed seconds;
  - team 2 elapsed seconds;
  - total elapsed seconds;
  - optional enemy/HP context by side;
  - factual DPS per side only when HP is known;
  - optional simplified sim DPS result references later;
  - warnings, for example clamped timers or missing HP data.
- total elapsed seconds across chambers.

Factual Abyss DPS belongs in `run_workspace` scenario/result code, not in the
right-panel widget. It is HP/time math over explicit Abyss enemy/HP context and
the calculated elapsed seconds from `calculate_abyss_chamber_result(...)`.

## DPS Dummy Snapshot

DPS Dummy snapshots should contain:

- run type `dps_dummy`;
- one team;
- target setup:
  - dummy/target label;
  - target HP if factual DPS is measured by HP/time;
  - resist/level/options if known;
  - duration or elapsed seconds;
  - notes/warnings about manual values;
- factual DPS data:
  - damage amount or target HP basis;
  - elapsed seconds;
  - DPS result;
  - source/provenance;
- optional GCSIM result reference later:
  - sim DPS;
  - iterations;
  - duration;
  - GCSIM version/hash;
  - config hash;
  - warnings/failed actions/incomplete characters.

DPS Dummy factual DPS and GCSIM sim DPS are separate result kinds. Do not store
or display one as the other.

## Timer Behavior To Reuse

Reuse behavior, not widget ownership, from `ui/widgets/timers.py` and legacy
`ui/main_window.py`:

- start time defaults to 10:00 / 600 seconds for Abyss chambers;
- minute spin range effectively stays 5..10 for current Abyss UI;
- seconds wheel editing wraps between minutes where appropriate;
- values clamp to supported timer bounds;
- timer edits recalculate elapsed/team totals immediately;
- reset restores timers and displayed results to zero/initial values;
- timer labels must localize through `localization.tr`.

Implementation direction:

- move current timer values and calculations into model/controller objects;
- let timer widgets edit model values and emit commands;
- never build save snapshots by reading `QSpinBox` or `QLabel` values directly;
- keep `calculate_abyss_chamber_result(...)` or a compatible pure helper as the
  factual elapsed-time source.
- do not design saved snapshot models before the current timer/DPS/GCSIM result
  data is working enough to know what must be preserved.

## History Workspace Timing

History should become a left workspace/tab after typed snapshots exist.

History owns its own browsing state. Current run mode and history browsing mode
are separate states:

- the right-dock run mode may provide the default history section when History is
  opened from a run context;
- opening History from Abyss should default to Abyss history;
- opening History from DPS Dummy should default to DPS Dummy history;
- once inside History, the user can switch between Abyss, DPS Dummy, and later
  PvP history through explicit controls inside the History workspace;
- switching History's internal type/filter must not mutate the current right-dock
  run mode, team selection, or active run/session state.

Recommended order:

1. Define snapshot write/read service and tests.
2. Wire right-dock Save to snapshot creation for the active run type.
3. Add a minimal History left workspace that reads immutable snapshots.
4. Route the right-dock History action to activate/select that left workspace
   and the relevant default run type section.
5. Retire the floating legacy `RunHistoryWindow` only after the new workspace
   can show saved runs.

History is not a global right-dock page. The right dock may contain a command
button, but the browsing surface belongs on the left.

Future History filters/sorts belong inside the History workspace, not in the
right-dock run-mode tabs. Expected filter/sort dimensions include:

- Abyss season/period, floor, chamber, side, enemy/wave/target metadata, clear
  time, factual DPS, team, characters, elements, resonances, artifact sets, and
  warnings;
- DPS Dummy target/setup, duration, factual DPS, optional sim DPS metadata when
  GCSIM exists, team, characters, elements, resonances, artifact sets, and
  warnings;
- later PvP mode/deck/opponent/rules/result dimensions using the same internal
  History navigation model.

## Factual DPS Boundary

Factual DPS is app-owned HP/time math:

- Abyss: enemy/chamber HP divided by calculated clear time per side/chamber.
- DPS Dummy: explicit HP/damage divided by elapsed/duration seconds.

Factual DPS should live in run/session scenario-result modules, near
`run_workspace.models` or a future `run_workspace.results` module. It should be
available to both the right panel and history/export view models.

Do not compute factual DPS inside `ui/right_panel_prototype.py`, History
widgets, or GCSIM adapters.

## GCSIM Boundary

GCSIM plugs in after typed team/run snapshots exist.

Integration rules:

- GCSIM config generation consumes explicit team/build/target snapshots.
- GCSIM runner executes outside the UI thread and stores/parses sim results.
- GCSIM result metadata attaches to run/session state or saved snapshots as
  `sim DPS`, not `factual DPS`.
- DPS Dummy is the first GCSIM consumer.
- Abyss GCSIM starts later with simplified/manual target assumptions.
- Detailed GCSIM controls use a larger drawer/workspace/overlay; the right dock
  shows only compact status/action and summary values.
- Read `docs/handoff/GCSIM.md` and `docs/handoff/STAT_NORMALIZATION.md` before
  implementing config generation or result parsing.

## Next Narrow Implementation Sequence

1. Extend `run_workspace.models` or a sibling module with typed
   current-run/session state: `RunSessionState`, `AbyssRunState`, and
   `DpsDummyRunState`. Do not add saved snapshot dataclasses in this step.
2. Add pure tests for current timer/session calculations, reset/default
   behavior, and factual DPS math.
3. Add an AppShell-side session controller adapter while keeping current
   `AppShellController` team mutations working.
4. Replace display-only chamber rows in
   `run_workspace.right_panel_prototype_view_model` with rows derived from the
   session model.
5. Wire Reset and current timer/result commands through `AppShell`/session
   controller.
6. Add DPS Dummy current factual-DPS inputs/results and then GCSIM DPS Dummy
   integration as separate steps.
7. Only after working timer/DPS/GCSIM result data exists, design immutable saved
   snapshots and snapshot persistence.

## Non-Goals For The Next Stage

- Do not delete `ui/main_window.py`.
- Do not migrate the old `runs_history.json` UI as final design.
- Do not implement saved snapshots before working timer/DPS/GCSIM result data exists.
- Do not mix factual DPS and sim DPS.
- Do not make right-panel widgets the source of truth for timers or saved runs.
