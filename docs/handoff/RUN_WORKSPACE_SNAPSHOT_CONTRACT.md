# Run Workspace Session And Snapshot Contract

Updated: 2026-06-18

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
  Account/Data settings, GCSIM worker/payload parsing, shell routing, and the
  first RUN-page Save bridge into immutable snapshot storage.
- `RightOperationsDock` is the fixed right operation area. Its current
  `RightPanelPrototypeWidget` has live in-memory Abyss timer editing, factual
  DPS rows, and compact GCSIM status/result cells. The old inert bottom
  `Reset` / `Save Run` / `History` action placeholder has been removed. A real
  localized RUN-page Reset command now routes through `RunSessionController`
  and resets only the active live mode. A real localized bottom RUN-page Save
  command now builds and writes immutable `HistorySnapshotBundle` records for
  the active run type, using grouped History storage. A minimal History
  left-workspace reader/list exists; saved rows can select immutable bundles
  and update an isolated read-only instance of the same mode-specific Run
  presentation used by the live pipeline. Normal selection no longer creates a
  derived PNG preview.
- `run_workspace.team_builder` is the typed team composition layer.
- `run_workspace.models` contains an early legacy Abyss snapshot adapter:
  `AbyssTimerState`, `calculate_abyss_chamber_result(...)`, `RunSnapshotV1`,
  and `build_legacy_abyss_run_snapshot(...)`.
- `run_workspace.history_snapshot` contains the immutable History Snapshot
  Bundle v2 schema and a caller-rooted local read/write service for supplied
  bundles. It writes grouped Abyss snapshots under
  `abyss/<period_start>/<bundle_id>/snapshot.json`, DPS Dummy snapshots under
  `dps_dummy/<bundle_id>/snapshot.json`, and can list old flat dev bundles for
  current development compatibility. Pre-contract/dev snapshots are disposable;
  no migration contract is required. `run_workspace.history_snapshot_builder`
  builds backend-only bundles from explicit `RunSessionState`/right-panel
  view-model inputs. It now derives frozen display details for every occupied
  slot. Production AppShell Save materializes every declared visible asset into
  the grouped bundle and restores the original live team state after temporary
  save-time hydration.
- `run_workspace.history_snapshot_preview` renders a derived v0 PNG card from a
  supplied immutable bundle to `<bundle_dir>/preview/history_card.png`. It does
  not mutate `snapshot.json` and does not query live assets/caches. This
  text-first renderer is transitional and must not define normal History
  browsing or the final export design.
- AppShell now uses live in-memory Abyss timer state for the compact right-dock
  chamber table. T1/T2 timer edits update controller state and the right-panel
  view model immediately. T2 follows T1 until manually edited; if T1 is edited
  below current T2, T2 clamps to T1 and returns to follow mode. The RUN Reset
  command restores the active mode's teams/selection/timers/GCSIM runtime rows
  to defaults without touching the inactive mode. The RUN Save command writes
  immutable bundles under the caller-provided snapshot root without resetting
  or opening History. Abyss Save passes already-loaded current Abyss source
  metadata into the builder so saved bundles carry `period_start`/floor when
  available.
- The current compact editor uses separate minute/second segments inside one
  visual `MM:SS` field per T1/T2 cell. Raw segment input normalizes only on
  commit. Left/Right changes the active segment; mouse wheel and Up/Down step
  the active minute or second segment.
- Current in-memory Abyss timer/session behavior is owned by the typed session
  boundary and exposed through AppShellController compatibility properties.
  Reset is wired through that boundary for the active live run mode. Save is
  wired to build/persist immutable bundles from typed session/view-model data;
  the minimal History left workspace can read saved rows, select saved bundles,
  and show provisional selected-snapshot details. The next History UI must use
  a separate read-only instance of the shared Run presentation. History command
  routing is still future work.
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
  - Save now builds and persists an immutable snapshot for the current run type.
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
roundtrip helpers, and `HistorySnapshotBundleStore(root)`. The grouped writer
stores supplied Abyss bundles as
`<root>/abyss/<period_start>/<bundle_id>/snapshot.json` and DPS Dummy bundles
as `<root>/dps_dummy/<bundle_id>/snapshot.json`, through a temp file in the
same directory. Missing Abyss period start uses `unknown_period`. The current
store can also list/read old `<root>/<bundle_id>/snapshot.json` dev bundles,
but those pre-contract snapshots may be deleted and require no migration. The
store does not use production `data/`, account/profile/cache/DB paths, or real
assets. The AppShell RUN Save command uses the project-root convention
`data/history/snapshots` by default, while tests and future callers can pass a
temp/custom root.

Every snapshot must include:

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

Every occupied team slot snapshot must store all data needed to reconstruct its
saved details without a live lookup:

- character id, name, level, element, rarity, constellation;
- bundle-local portrait and side-icon asset references;
- weapon id, name, level, promote level, rarity, refinement,
  `weapon_fingerprint`, bundle-local icon, visible stats, passive/static effect
  data, warnings, and user-facing tooltip content from save time;
- artifact/current-build snapshot:
  - actual artifact ids by slot;
  - complete artifact slot records and saved tooltip content;
  - active set bonuses and set icons;
  - total stats, CV, proc count, missing positions, warnings;
  - selected preset/build id/name only as provenance, not as the source of
    truth;
- calculated/visible stat rows, bonus rows, warnings, and user-facing tooltips;
- source notes such as current-equipment vs saved preset.

The snapshot must capture those fields for every occupied slot, not only the
slot selected when Save was pressed. Every portrait, weapon icon, artifact/set
icon, enemy image, and other visible asset required by History must be copied
inside the immutable bundle during Save. Bundle-local paths are conveniences,
not identity. History must remain complete after account data, DBs, caches, and
original asset paths are removed.

## Snapshot Presentation Adapter

- Snapshot JSON remains frozen domain/display truth. Do not serialize QWidget
  instances or persist a ready-made UI view-model as the source of truth.
- A mode-specific adapter maps an Abyss or DPS Dummy snapshot into the current
  shared right-panel view-model used by the live Run presentation.
- The adapter and shared widget tree must use only snapshot fields and
  bundle-local assets. They must not read current account data, DBs, caches,
  Artifact Browser state, or the live `RunSessionState`.
- This keeps old run facts frozen while allowing the common Run presentation to
  follow the current application design.

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
- Save wiring must call the backend builder from explicit typed
  session/view-model data and then write immutable `HistorySnapshotBundle`
  records through a store boundary.

## History Workspace Timing

History is a left workspace/tab built on typed snapshots. Detailed browsing,
autonomous snapshot-bundle, shared presentation, and export rules live in
`docs/handoff/HISTORY_BROWSER.md`.

History owns its own browsing/viewing state. Current run mode and history
browsing mode are separate states:

- the right-dock run mode may provide the default history section when History is
  opened from a run context;
- activating the `history` left workspace switches the right dock to a separate
  snapshot-bound instance of the same mode-specific Run presentation; it may
  show a small empty prompt before selection and is read-only after selection;
- entering History must not reset, clear, or reinitialize the live Run Session;
- Reset must not be used as a History routing shortcut;
- opening History from Abyss should default to Abyss history;
- opening History from DPS Dummy should default to DPS Dummy history;
- once inside History, the user can switch between Abyss and DPS Dummy through
  explicit tabs inside the History workspace; PvP may be added only under its
  own later contract;
- selecting snapshots or switching History's internal type/filter must not
  mutate the current right-dock run mode, team selection, or active run/session
  state.

The selected snapshot presentation starts on its first occupied slot. Slot
selection, scrolling, and saved-data tooltips remain available. Mode tabs and
the Reset/Save row are hidden; timers and saved state controls are visible but
disabled; mutation, drag/drop, equipment commands, and command-only controls
such as GCSIM Run are unavailable. Snapshot metadata is shown only on the left.

Recommended order:

1. Done: define History Snapshot Bundle v2 schema, local write/read service,
   and tests.
2. Done: build backend-only snapshots from explicit typed live
   session/right-panel view-model data.
3. Done: wire RUN-page Save to snapshot creation for the active run type.
4. Done as a foundation: the History left workspace reads grouped immutable
   snapshots and supports row selection. Its details/PNG views are provisional.
5. Done: capture frozen display data for every occupied slot and materialize
   declared visible assets inside the bundle during production Save.
6. Add Abyss/DPS Dummy snapshot adapters into the shared right-panel view-model
   and enforce the read-only presentation policy.
7. Replace the provisional details/PNG browsing area with the contracted tabs,
   period groups, compact visual rows, and newest-first ordering.
8. Route a future History command to activate/select that left workspace and
   the relevant default run type section.

History is not a global right-dock page. The right dock may contain a command
button, but the browsing surface belongs on the left.

The MVP includes internal mode tabs, Abyss period groups, and newest-first
ordering. More complex future History filters/sorts belong inside the History
workspace, not in the right-dock run-mode tabs. Expected dimensions include:

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
4. Done: immutable History Snapshot Bundle v2 dataclasses/services exist under
   `run_workspace.history_snapshot` with local temp-root tests.
5. Done: backend-only builder maps supplied typed session/right-panel
   view-model data into `HistorySnapshotBundle` records for Abyss and DPS
   Dummy shapes.
6. Done: RUN-page Save builds and persists immutable grouped bundles for the
   active run type through `HistorySnapshotBundleStore`.
7. Done as a foundation: the minimal History left workspace reads grouped
   snapshots and supports row selection.
8. Done: capture frozen display data for every occupied slot and copy declared
   visible assets into each production bundle without retaining save-time
   hydration in live state.
9. Done: snapshot-to-shared-right-panel adapters and the contracted
   read-only/hidden control policy drive an isolated shared Run panel; normal
   row selection does not generate a permanent PNG preview.
10. Replace provisional browsing content with Abyss/DPS Dummy tabs, expandable
   Abyss period groups, compact visual rows, and newest-first ordering.
11. Attach Browser/GCSIM results to session/snapshot metadata as `sim DPS` and
   keep them separate from factual DPS.
12. Add DPS Dummy current factual-DPS inputs/results and GCSIM DPS Dummy
   integration as separate follow-up work.

## Non-Goals For The Next Stage

- Do not delete `ui/main_window.py`.
- Do not migrate the old `runs_history.json` UI as final design.
- Do not add further Save/History UI behavior without calling the backend
  builder from typed session state and writing immutable History Snapshot
  Bundles through an explicit store boundary.
- Do not mix factual DPS and sim DPS.
- Do not make right-panel widgets the source of truth for timers or saved runs.
