# History Browser Contract

Scope: product and architecture contract for the AppShell History Browser.
The current implementation is a minimal left-workspace reader/list in
`ui/history_browser/` plus an empty isolated right-panel viewer. RUN-page Save
creates immutable backend bundles and the History workspace can read/list them,
but export, filters, row selection side effects, and snapshot payload rendering
are later tasks.

## Boundary

- History browsing is a left workspace/browser in AppShell.
- History browsing is not a floating legacy window and not a right-dock-only
  page.
- `ui/app_shell.py` owns only stable workspace id/routing/nav wiring for
  `history` and the workspace-driven right-dock selection. History UI belongs
  under `ui/history_browser/`.
- `ui/run_history_window.py` and `runs_history.json` are legacy. Do not develop
  them as the final History model, and do not migrate them as the first real
  History implementation.
- Opening the `history` workspace reloads the current snapshot root and
  immediately switches the fixed right dock to the isolated empty History
  viewer, before any saved run is selected.
- The left workspace lists saved immutable bundles from disk. The right viewer
  remains placeholder-only until frozen snapshot details are implemented.

## Future Rows

History rows should become Akasha-like compact saved-run rows:

- Abyss rows may be paired/double-team rows.
- Abyss rows should eventually show side-character icons, weapon icons,
  artifact bonus icons/labels, chamber time, factual DPS summaries, sim DPS
  where available, and warnings/provenance where needed.
- DPS Dummy rows are one-team rows with team/build summary plus factual DPS and
  sim DPS where available.
- PvP History is later and must wait for the final PvP shape.

## Selecting A Run

Clicking a saved run should eventually:

1. Select an immutable saved snapshot.
2. Expand an export-preview card/image inside the left History workspace.
3. Send a frozen read-only snapshot payload to a History-specific right-panel
   viewer.

History browsing state is separate from the live run mode. Switching filters,
sections, or selected snapshots in History must not mutate current Abyss, DPS
Dummy, or later PvP run state.

## Right-Panel Viewer

The History right-panel viewer is not the live Run panel:

- initial state is an empty localized prompt to select a saved run before
  snapshot details exist;
- no ticking timers;
- no GCSIM execution;
- no equipment/team mutation;
- no save/reset live commands;
- no dependency on the current account, profile, cache, or settings;
- no reset/clear of live Run Session state as a shortcut for entering History;
- current live Abyss, DPS Dummy, and PvP state must remain intact when leaving
  History.

The viewer consumes frozen snapshot display data and can expose read-only
details/tooltips/export actions. It must not query live account equipment or
current build presets to render a saved run.

## Snapshot Bundle

Saved history must be an autonomous immutable snapshot bundle:

- structured JSON is the source of truth;
- local snapshot assets are copied into the bundle;
- frozen display labels, stat rows, tooltips, and result payloads are stored;
- character ids, build ids, artifact ids, and similar live ids may be stored as
  provenance/debug references only;
- those ids are not required live references for display;
- clearing account/profile/artifact/weapon/Abyss/GCSIM caches must not break
  already saved History display.

The snapshot bundle must preserve enough structured data for browsing, details,
export, provenance, and future compatibility. It must not be image-only.

Backend status: `run_workspace/history_snapshot.py` defines
`HistorySnapshotBundle` v1, nested frozen display/provenance/team/scenario/
result/asset/preview records, JSON roundtrip helpers, and
`HistorySnapshotBundleStore(root)` for caller-provided local roots. The grouped
write path stores Abyss bundles at
`<root>/abyss/<period_start>/<bundle_id>/snapshot.json`, using
`unknown_period` when no safe/parseable period start exists, and DPS Dummy
bundles at `<root>/dps_dummy/<bundle_id>/snapshot.json`. The old flat
`<root>/<bundle_id>/snapshot.json` writer/reader remains for tests and
transition; no automatic migration or deletion is performed.
`run_workspace.history_snapshot_builder` can build backend-only bundles from
explicit typed session/right-panel view-model data, and AppShell RUN Save
writes those bundles to the configured snapshot root. These backend pieces and
the Save bridge do not copy real assets, query account/cache/DB data, or render
export surfaces.

## Abyss Period Groups

- Abyss History is organized by saved Abyss period key, normally the immutable
  `scenario.abyss.period_start` ISO date.
- Period groups should eventually show a compact period card with start/end,
  floor/season label, chamber enemy/boss/HP summary, and later stored
  boss/enemy image/icon previews if snapshot assets contain them.
- That period summary must be derived from saved snapshot data, not from the
  live Abyss cache.
- Real image/export rendering remains future work.

## Export Preview/Card

The expanded History card should become a normal image export surface:

- PNG/JPEG or equivalent ordinary image output is expected.
- Visual quality is high priority.
- The renderer may be isolated from the main Qt UI if a better layout/styling
  path is useful, for example HTML/CSS/JS or another dedicated renderer.
- AppShell should consume the generated image/preview without embedding
  generator complexity into shell routing code.
- The first real renderer/export implementation is a separate future task.

## First Real Stages

Recommended sequence after the placeholder/module split:

1. Extract typed `RunSessionState`.
2. Done: define snapshot bundle schema/service v1.
3. Done: build backend-only snapshots from typed session/view-model data.
4. Done: wire RUN-page Save to persist immutable bundles.
5. Done: add a minimal History left reader/list for saved bundles.
6. Add a History-specific right-panel snapshot viewer.
7. Add the export renderer/generator.
