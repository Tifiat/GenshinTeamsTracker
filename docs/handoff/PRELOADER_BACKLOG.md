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

## Current Measurement Source

- Weak 1366px HP Notebook baseline:
  `docs/handoff/performance_measurements/2026-06-13_appshell_perf_probe_baseline_c371ef4_hp_1366.md`.
- Weak 1366px HP Notebook after the direct optimization pass:
  `docs/handoff/performance_measurements/2026-06-13_appshell_perf_probe_after_optimization_c371ef4_hp_1366.md`.
- Command:
  `.\.venv\Scripts\python.exe tools\experiments\appshell_perf_probe.py --mode all --importtime`.
- Commit: `c371ef4`.

## Backlog Items

### AppShell Import Graph

- Measured cost: `ui.app_shell` import `10900.5 ms` cumulative on the weak
  1366px HP Notebook at `c371ef4`.
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
  measured `586.6-752.6 ms`, with icon assignment at `352.3-484.0 ms`.
- Why it lags: first creation still constructs many QWidget buttons and assigns
  portrait icons. In-place updates already avoid repeated filter rebuilds.
- Why not fixed now: a safe repaint-suppression/logging pass is acceptable, but
  replacing the target list with a painted surface is a separate UI tradeoff and
  moving creation later would hide cold work.
- Loader target: if target button creation remains visible after direct fixes,
  prewarm/create the target selector under the loader or replace it with a
  measured lower-widget-count UI in a dedicated task.

### Preset/Edit Control And Text/Marquee Prep

- Measured cost: after the direct optimization pass, Artifact Browser init
  still reports `ui=1204.2-1640.6 ms`, `presets=22.1-59.4 ms`, and
  `build_panel=49.3-70.1 ms` on the weak 1366px HP Notebook.
- Why it lags: edit controls, preset rows, icon/text/marquee helpers, and build
  preview widgets are created during cold Artifact Browser construction.
- Why not fixed now: only direct duplicate/rebuild bugs should be fixed in the
  current pass.
- Loader target: include any remaining unavoidable widget/pixmap/text
  preparation in the loader manifest after direct UI simplification options are
  exhausted.
