# Preloader / Startup Cache Backlog

This file records expensive work that should eventually move under the explicit
startup loader/prewarm/cache stage. Do not implement that stage during ordinary
performance fixes. Before adding an item here, first check whether the lag is
caused by duplicate work, avoidable rebuilds, bad hot-path code, or an
algorithmic shortcut that should be fixed directly.

## Rules

- Pre-loader optimization means reducing total work, not moving work to a later
  click, timer, background hydration, or hidden lazy path.
- Add a backlog item only when the remaining work is useful/necessary cold work
  or a cache/prewarm candidate that should be handled by the future loader.
- Each item should include:
  - subsystem;
  - measured cost, device, command, and commit;
  - why it lags;
  - why it is not fixed now;
  - what the loader should eventually bake, prewarm, or cache.
- Keep measurement details in `docs/handoff/performance_measurements/`; keep
this file as the curated loader queue.

## Current Artifact Browser Direct Fixes

The 2026-10-03 first-open optimization and pending user smoke gate are owned by
[ARTIFACT_BROWSER.md](ARTIFACT_BROWSER.md#artifact-browser-storage-and-json-import).
The [dated receipt](performance_measurements/2026-10-03_artifact_first_open_worker3.md)
remeasures this worker's current inventory, including preset-target batching,
single construction with known targets, initialized reads and alpha trimming.
It supersedes June estimates for that specific scenario only. Remaining store,
widget and raster preparation are still candidates for measured direct fixes
before an approved loader; no new cache/prewarm stage is installed.
The [2026-10-04 continuation](performance_measurements/2026-10-04_artifact_scaling_actions_worker3.md)
adds scaled inventories and equipment-action measurements. It confirms bounded
inventory query counts and removes avoidable apply-time row rebuilding. Initial
widget/raster work and long target-switch list rebuilding remain measurable;
the continuation makes no claim of an additional first-open speedup.

## Historical Measurement Sources (2026-06-13)

- Weak 1366px HP Notebook baseline:
  `docs/handoff/performance_measurements/2026-06-13_appshell_perf_probe_baseline_c371ef4_hp_1366.md`.
- Weak 1366px HP Notebook after the direct optimization pass:
  `docs/handoff/performance_measurements/2026-06-13_appshell_perf_probe_after_optimization_c371ef4_hp_1366.md`.
- Weak 1366px HP Notebook after the MarqueeButton target-list pass:
  `docs/handoff/performance_measurements/2026-06-13_artifact_browser_marquee_target_pass_30571b7_hp_1366.md`.
- Command:
  `.\.venv\Scripts\python.exe tools\experiments\appshell_perf_probe.py --mode all --importtime`.
- Commit: `c371ef4`.

These measurements describe the recorded commit/device, not the current tree.
Remeasure the selected subsystem before implementing a loader or claiming a
current speedup. Costs below are retained as evidence; no new profiling was
performed during the 2026-09-16 documentation reconciliation.

## Backlog Items

### AppShell Import Graph

- Measured cost: `ui.app_shell` import `10900.5 ms` cumulative on the weak
  1366px HP Notebook at `c371ef4`.
- Current guarded remeasurement: the 6 October 2026 synthetic-profile probe
  recorded `ui.app_shell` import `2758.5 ms`, child readiness `3975.0 ms`, and
  supervisor-to-ready `4734.2 ms` on the current local Windows workstation;
  see [the dated receipt](performance_measurements/2026-10-06_guarded_startup_profile.md).
  It is a one-run diagnostic on a different commit/device, not a comparison or
  a claimed speedup over the HP notebook evidence.
- Populated-profile follow-up: the [7 October audit](performance_measurements/2026-10-07_main_startup_and_merge_audit.md)
  reproduced 10+ second readiness in disposable copies of the main inventory,
  images and History. Construction of hidden History/PvP workspaces and repeated
  filesystem/image work also dominate this case; the empty-profile import-only
  diagnosis must not be treated as a populated-user startup guarantee.
- Why it lags: importing AppShell pulls in large UI/backend dependency chains,
  including PySide modules, AppShell workspaces, PvP, GCSIM, account pages,
  right-panel view-models, and shared grid utilities.
- Why not fixed now: import graph reshaping is broader than the current
  duplicate-work cleanup, and lazy-importing heavy screens would hide cost
  rather than reduce it unless done as a deliberate loader/bootstrap design.
- Loader target: show an explicit startup loader before heavy AppShell imports
  or split a tiny bootstrap from heavy workspace imports, then report named
  import/prewarm stages.

### Initial Character / Weapon Grid Pixmap Preparation

- Measured cost: Character grid `set_items` `1592.8 ms` for `73` items; weapon
  grid `set_items` `550.3 ms` for `58` items on the weak 1366px HP Notebook at
  `c371ef4`.
- Why it lags: first grid construction loads/scales account raster assets into
  HiDPI pixmaps and prepares overlay state.
- Why not fixed now: duplicate refreshes and outline-only refreshes should be
  fixed directly first; the remaining first-use pixmap preparation is useful
  work that belongs under a future loader if still visible.
- Loader target: prewarm account character/weapon grid pixmaps after account
  data is known, with progress labels and cache-key visibility.

### PvP Deck Grid Cold Preparation

- Measured cost: PvP deck grid `set_items` `1616.3 ms` for `116` total items on
  the weak 1366px HP Notebook at `c371ef4`.
- Why it lags: PvP Decks creates painted grids for account character and weapon
  assets during AppShell construction.
- Why not fixed now: duplicate SQLite/account loading should be removed now, but
  moving PvP construction to first click would only hide the lag.
- Loader target: once the loader stage exists, include PvP Deck grid pixmap prep
  in the startup work manifest if Decks remains part of the initial AppShell
  workspace set.

### Artifact Browser Store Load

- Measured cost: Artifact store load around `548.2 ms` in the baseline probe;
  previous runs observed roughly `323.6-568.9 ms`.
- Why it lags: the Artifact Browser builds its in-memory store from SQLite,
  artifacts, custom sets, and set bonus data.
- Why not fixed now: the store load is legitimate cold data construction; hiding
  it behind delayed Artifact Browser creation would obscure the real cost.
- Loader target: prewarm/load the Artifact Browser store under the explicit
  loader and expose timing for artifact rows, custom sets, and set bonuses.

### Artifact Browser Target Buttons

- Measured cost: `74` target buttons, `_make_build_target_button` `523.8 ms`,
  `_ensure_build_target_buttons` `536.3 ms` on the weak 1366px HP Notebook at
  `c371ef4`. After the direct optimization pass, artifact-only repeats still
  measured `586.6-752.6 ms`, with icon assignment at `352.3-484.0 ms`. After
  the MarqueeButton inactive-sync reduction, target creation measured
  `297.6-367.1 ms`, with icon assignment at `229.8-295.8 ms`.
- Why it lags: first creation still constructs many QWidget buttons and assigns
  portrait icons. In-place updates already avoid repeated filter rebuilds.
- Why not fixed now: a safe repaint-suppression/logging pass is acceptable, but
  replacing the target list with a painted surface is a separate UI tradeoff and
  moving creation later would hide cold work.
- Loader target: if target button creation remains visible after direct fixes,
  prewarm/create the target selector under the loader or replace it with a
  measured lower-widget-count UI in a dedicated task.

### Preset/Edit Control And Text/Marquee Prep

- Measured cost: after the MarqueeButton target-list pass, Artifact Browser init
  still reports `ui=1030.5-1037.0 ms`, `presets=35.9-39.5 ms`, and
  `build_panel=25.0-34.2 ms` on the weak 1366px HP Notebook.
- Why it lags: edit controls, preset rows, icon/text/marquee helpers, and build
  preview widgets are created during cold Artifact Browser construction.
- Why not fixed now: only direct duplicate/rebuild bugs should be fixed in the
  current pass.
- Loader target: include any remaining unavoidable widget/pixmap/text
  preparation in the loader manifest after direct UI simplification options are
  exhausted.
