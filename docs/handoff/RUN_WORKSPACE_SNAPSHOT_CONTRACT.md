# Run Workspace Session And Snapshot Contract

Date: 2026-06-02

Scope: planning and data contract for the next Run Workspace stages around
typed session ownership, immutable history snapshots, and durable GCSIM result
attachment. This is not a UI implementation plan for legacy cleanup, and it
does not switch `main.py`.

## Current State

- `AppShell` is the future root coordinator. The first typed live-session
  extraction now lives in `run_workspace/session.py`: `RunSessionState`,
  `AbyssRunState`, `DpsDummyRunState`, and `RunSessionController` own active
  mode, per-mode `TeamBuilderState`, selected slot target, external-bonus
  toggle state, Abyss timers/T2 follow flags, and compact runtime GCSIM chamber
  results.
- `ui.app_shell.AppShellController` is still the UI/account/equipment adapter:
  it keeps equipment DB/cache/hydration, Abyss source-data cache loading,
  Account/Data settings, GCSIM worker/payload parsing, and shell routing.
- `RightOperationsDock` is the fixed right operation area. Its current
  `RightPanelPrototypeWidget` has live in-memory Abyss timer editing, factual
  DPS rows, and compact GCSIM status/result cells. The old inert bottom
  `Reset` / `Save Run` / `History` action placeholder has been removed. A real
  localized RUN-page Reset command now routes through `RunSessionController`
  and resets only the active live mode; durable save/history commands are still
  future typed session-controller work.
- `run_workspace.team_builder` is the typed team composition layer.
- `run_workspace.models` contains an early legacy Abyss snapshot adapter:
  `AbyssTimerState`, `calculate_abyss_chamber_result(...)`, `RunSnapshotV1`,
  and `build_legacy_abyss_run_snapshot(...)`.
- `run_workspace.history_snapshot` now contains the immutable History Snapshot
  Bundle v1 schema and a caller-rooted local read/write service for supplied
  bundles. It does not build snapshots from live session/AppShell state and
  does not wire Save, History rows, asset copying, preview rendering, or UI.
- AppShell now uses live in-memory Abyss timer state for the compact right-dock
  chamber table. T1/T2 timer edits update controller state and the right-panel
  view model immediately. T2 follows T1 until manually edited; if T1 is edited
  below current T2, T2 clamps to T1 and returns to follow mode. The RUN Reset
  command restores the active mode's teams/selection/timers/GCSIM runtime rows
  to defaults without touching the inactive mode. Save/history persistence is
  still future.
- The current compact editor uses separate minute/second segments inside one
  visual `MM:SS` field per T1/T2 cell. Raw segment input normalizes only on
  commit. Left/Right changes the active segment; mouse wheel and Up/Down step
  the active minute or second segment.
- Current in-memory Abyss timer/session behavior is owned by the typed session
  boundary and exposed through AppShellController compatibility properties.
  Reset is wired through that boundary for the active live run mode. Save/history
  commands and immutable snapshots are still future work.
- `ui/widgets/timers.py` contains useful timer editing behavior but must not
  remain the durable owner of run/session state.
- `ui/run_history_window.py` and `runs_history.json` are legacy image/path
  history. They are not the future history model.
- `docs/handoff/GCSIM.md` and
  `docs/handoff/GCSIM_ENGINE_INTEGRATION_PLAN.md` document simulator
  integration. Backend/dev GCSIM and Browser MVP paths exist, but durable saved
  GCSIM results must attach to typed run/session state or snapshots, not UI
  widgets.

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
  - own save commands; Reset is already owned by typed live session state;
  - build immutable run snapshots;
  - expose a right-panel view model without reading widgets;
  - route history opening to the correct left workspace state.
- Right dock action wiring:
  - Reset now resets the active live run mode through typed session state, not
    legacy widgets.
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

The first concrete backend data contract is
`run_workspace/history_snapshot.py`: `HistorySnapshotBundle` plus nested
display/provenance/team/scenario/result/asset/preview dataclasses, JSON
roundtrip helpers, and `HistorySnapshotBundleStore(root)`. The store writes
supplied bundles as `<root>/<bundle_id>/snapshot.json` through a temp file in
the same directory and reads them back without using production `data/`,
account/profile/cache/DB paths, or real assets. Future work must add the
builder that converts typed live session/view-model data into this bundle.

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
- do not wire Save snapshot builders before the current timer/DPS/GCSIM result
  data is explicit enough to map into `HistorySnapshotBundle`.

## History Workspace Timing

History should become a left workspace/tab after typed snapshots exist.
Detailed History Browser browsing, export-preview, autonomous snapshot-bundle,
and History-specific right-panel viewer rules live in
`docs/handoff/HISTORY_BROWSER.md`.

History owns its own browsing/viewing state. Current run mode and history
browsing mode are separate states:

- the right-dock run mode may provide the default history section when History is
  opened from a run context;
- activating the `history` left workspace switches the right dock to the
  isolated empty History viewer before any snapshot is selected;
- entering History must not reset, clear, or reinitialize the live Run Session;
- Reset must not be used as a History routing shortcut;
- opening History from Abyss should default to Abyss history;
- opening History from DPS Dummy should default to DPS Dummy history;
- once inside History, the user can switch between Abyss, DPS Dummy, and later
  PvP history through explicit controls inside the History workspace;
- switching History's internal type/filter must not mutate the current right-dock
  run mode, team selection, or active run/session state.

Recommended order:

1. Done: define History Snapshot Bundle v1 schema, local write/read service,
   and tests.
2. Build snapshots from typed live session/right-panel view-model data.
3. Wire right-dock Save to snapshot creation for the active run type.
4. Add a minimal History left workspace that reads immutable snapshots.
5. Route the right-dock History action to activate/select that left workspace
   and the relevant default run type section.
6. Retire the floating legacy `RunHistoryWindow` only after the new workspace
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

Backend/dev GCSIM and the AppShell Browser MVP already exist. Their current
runtime outputs are session/UI results, not saved history. Durable GCSIM results
must plug into typed run/session state and immutable snapshots before they are
treated as saved records.

Integration rules:

- GCSIM config generation consumes explicit team/build/target data from typed
  session/snapshot boundaries, not UI widgets.
- GCSIM runner executes outside the UI thread and stores/parses sim results.
- GCSIM result metadata attaches to run/session state or saved snapshots as
  `sim DPS`, not `factual DPS`.
- Current Browser MVP targets Abyss chamber flows first; DPS Dummy remains a
  later consumer.
- Detailed GCSIM controls use a larger drawer/workspace/overlay; the right dock
  shows only compact status/action and summary values.
- Read `docs/handoff/GCSIM.md`,
  `docs/handoff/GCSIM_ENGINE_INTEGRATION_PLAN.md`, and
  `docs/handoff/STAT_NORMALIZATION.md` before implementing config generation or
  result parsing.

## Next Narrow Implementation Sequence

1. Done for the first live slice: typed session ownership exists for mode,
   per-mode team state, selected target, external bonus flag, Abyss timers/T2
   follow flags, and runtime compact GCSIM chamber results. Factual DPS rows
   still use the existing right-panel view-model builder with AppShell-provided
   Abyss source data.
2. Add/keep pure tests for timer/session calculations, reset/default behavior,
   factual DPS math, and GCSIM result stale/current metadata.
3. Done: Reset is wired through the session controller so it resets the active
   live run mode, not widgets, and does not wipe the inactive Abyss/DPS mode.
4. Done: immutable History Snapshot Bundle v1 dataclasses/services exist under
   `run_workspace.history_snapshot` with local temp-root tests.
5. Build a snapshot builder from typed session/right-panel view-model data.
6. Wire Save to snapshot creation for the active run type.
7. Add a minimal History left workspace that reads immutable snapshots, and route
   right-dock History to that workspace with the active run type as default.
8. Attach Browser/GCSIM results to session/snapshot metadata as `sim DPS` and
   keep them separate from factual DPS.
9. Add DPS Dummy current factual-DPS inputs/results and GCSIM DPS Dummy
   integration as separate follow-up work.

## Non-Goals For The Next Stage

- Do not delete `ui/main_window.py`.
- Do not migrate the old `runs_history.json` UI as final design.
- Do not wire Save/History UI before a real builder maps live session data into
  immutable History Snapshot Bundles.
- Do not mix factual DPS and sim DPS.
- Do not make right-panel widgets the source of truth for timers or saved runs.
