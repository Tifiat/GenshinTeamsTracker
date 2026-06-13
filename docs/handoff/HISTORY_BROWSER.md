# History Browser Contract

Scope: product and architecture contract for the AppShell History Browser.
The current implementation is a left-workspace reader/list in
`ui/history_browser/` plus an isolated read-only right-panel snapshot viewer
v0. RUN-page Save creates immutable backend bundles, History can read/list
grouped bundles, saved rows are selectable, and the viewer renders compact
frozen snapshot details. A v0 PNG export-preview renderer exists for selected
saved rows. Filters, polished export/share actions, and richer image rendering
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
- The left workspace lists saved immutable bundles from disk. Selecting a row
  loads that immutable bundle and sends a frozen read-only details payload to
  the History viewer.
- Selecting a row also generates or reuses a derived PNG preview at
  `<bundle_dir>/preview/history_card.png`. The PNG is derived from
  `snapshot.json`; the immutable snapshot JSON is not rewritten for preview
  refs in this stage.

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

Clicking a saved run now:

1. Select an immutable saved snapshot.
2. Visually mark the selected saved row.
3. Send a frozen read-only snapshot payload to a History-specific right-panel
   viewer.
4. Show a v0 generated PNG preview in the left History workspace.

History browsing state is separate from the live run mode. Switching filters,
sections, or selected snapshots in History must not mutate current Abyss, DPS
Dummy, or later PvP run state.

## Right-Panel Viewer

The History right-panel viewer is not the live Run panel:

- initial state is an empty localized prompt to select a saved run;
- selected state shows compact frozen snapshot details: run/date/source,
  Abyss period/floor when present, teams, character/weapon/build labels,
  chamber timing, factual DPS, sim DPS where present, warnings, and provenance;
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
- Period groups now derive a compact text summary from saved snapshots:
  start/end, floor/season label, saved run count, chamber labels, and
  chamber/side enemy/HP lines when the bundle contains them.
- That period summary is derived from saved snapshot data, not from the live
  Abyss cache.
- Richer period card visuals and later stored boss/enemy image/icon previews
  remain future work.
- The selected-run PNG preview is available, but richer period-level images
  remain future work.

## Export Preview/Card

Current v0:

- `run_workspace/history_snapshot_preview.py` renders a text-first PNG card from
  a supplied immutable `HistorySnapshotBundle`.
- The output convention is `<bundle_dir>/preview/history_card.png`.
- The renderer uses saved snapshot fields only. It does not query live account
  data, caches, DBs, image assets, GCSIM, or network state.
- Missing icon/image refs are tolerated and shown as text fallbacks.
- The left History workspace displays the generated PNG for the selected row.

Future:

- Polish the visual card design and reusable RunCard/TeamCard presentation.
- Add deliberate export/share/copy actions.
- Add XLSX/data-oriented export.

## First Real Stages

Recommended sequence after the placeholder/module split:

1. Extract typed `RunSessionState`.
2. Done: define snapshot bundle schema/service v1.
3. Done: build backend-only snapshots from typed session/view-model data.
4. Done: wire RUN-page Save to persist immutable bundles.
5. Done: add a minimal History left reader/list for saved bundles.
6. Done: add saved-row selection and a History-specific read-only right-panel
   snapshot viewer v0.
7. Done: add a v0 selected-snapshot PNG export-preview renderer.
