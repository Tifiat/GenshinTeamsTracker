# AppShell / Artifact Browser Performance Measurement - 2026-06-13

## Context

- Measured at: `2026-06-13T11:56:03+03:00` recording time.
- Measured code revision: `4a63856`.
- Recorded in repo at revision: `742d4da`.
- Worktree after recording: clean relative to `master...origin/master`.
- User noted the newer merge commit does not affect these measurements.
- Device profile: weak 1366px laptop, HP Notebook, AMD A6-5200 APU with Radeon HD Graphics, 11.5 GB RAM, Windows 11 Pro 10.0.22621.
- User context: RDP and browser may be running in parallel; this device is intentionally useful because performance improvements are easier to notice.
- Startup scaling: app detected monitor width `1366`, reference width `1920`, computed `QT_SCALE_FACTOR=0.711458`.

## Measurement Method

- No production code was changed for measurement.
- Used isolated PySide6 offscreen probes with:
  - `QT_QPA_PLATFORM=offscreen`
  - `GTT_PERF_LOG=1`
- Used existing `[PERF]` logs plus temporary runtime monkeypatch probes in the measurement process for:
  - `PixelIconGrid._refresh_prepared_pixmaps`
  - `PixelIconGrid.set_items`
  - `PixelIconGrid.update_item`
  - `ui.utils.pixel_icon_grid.load_hidpi_pixmap`
  - selected constructors / Artifact Browser build methods
- Offscreen measurements are good for CPU/construction/load attribution, but not a final visible-FPS benchmark.

## Baseline Timings

Startup/import layer:

- `ui.app_shell` import with `python -X importtime`: `3278.5 ms` cumulative.
- Qt import: about `718.0 ms` in the startup breakdown probe.
- `QApplication` creation: about `50.1 ms`.

AppShell startup:

- `AppShell()` constructor: about `3916.0 ms` baseline, with observed run range about `3834-5087 ms`.
- Initial `show()` plus event processing: about `3194.4 ms`.
- Character grid initial reload: `1274.8 ms` total, including `1089.8 ms` grid/icon work for `73` characters.
- Weapon grid initial reload: `878.1 ms` total, including `428.2 ms` grid/icon work for `58` weapons.

Left workspace constructor attribution:

- `LeftWorkspaceHost.__init__`: about `3016.3 ms`.
- `CharacterWeaponWorkspace.__init__`: about `268.0 ms`.
- `PvpDecksWorkspace.__init__`: about `2574.0 ms`.
- `PvpDecksWorkspace.refresh_account_data`: about `2399.1 ms`.
- `PvpDecksWorkspace._load_character_assets`: about `181.3 ms`.
- `PvpDecksWorkspace._load_weapon_assets`: about `658.9 ms`.
- `PvpDecksWorkspace.refresh_view`: about `1539.4 ms`.
- PvP `_reload_deck_grid` calls: about `396.4 ms` and `1131.7 ms`.

Artifact Browser first open:

- `artifact_workspace_lazy_create`: about `2167.5-2621.7 ms`.
- First visible open probe: about `2939.1-3373.9 ms`.
- Repeat workspace switch after creation: about `438.4-551.7 ms`.
- `artifact_browser_init`: about `1909.1-2412.1 ms`.
- `ArtifactBrowserStore.load_from_db`: about `323.6-568.9 ms`.
- Artifact target list refresh: about `675.2-698.6 ms`.
- `_ensure_build_target_buttons`: about `683.3 ms`.
- `_build_build_target_selector`: about `998.6 ms`.
- `_make_build_target_button`: `74` buttons, about `667.7 ms` total.
- `apply_current_filters`: about `5.2-10.9 ms`.

Paint cost comparison for current `SmoothPixmapTransform`:

- Character grid repaint: about `28.942 ms/frame` with smoothing vs `18.044 ms/frame` without.
- Weapon grid repaint: about `56.042 ms/frame` with smoothing vs `37.626 ms/frame` without.
- Disabling smoothing did not materially improve cold Artifact Browser creation in a separate baseline run; it mostly affects repaint/resize smoothness cost.

Marker/update hot path:

- Updating one character outline via `PixelIconGrid.update_item`: about `38.1 ms`.
- Updating all `73` character outlines: about `4266.4 ms` in `marker_incremental`.
- Root cause observed in code: `update_item` refreshes prepared pixmaps for the whole grid even when only `outline` changes.

## Findings

1. The latest stair-step fix is not the main cause of multi-second Artifact Browser first-open time.
   It adds `SmoothPixmapTransform`, which makes grid repaint cost higher, but Artifact Browser cold creation is dominated by store load and target button/widget creation.

2. App startup now pays for PvP Decks workspace immediately.
   `PvpDecksWorkspace` loads account character/weapon data and builds painted grids during `LeftWorkspaceHost.__init__`, even though the PvP workspace is not the first visible workspace.

3. `PixelIconGrid.update_item` does too much repeat work.
   Marker/outline-only updates should not rebuild all prepared pixmaps. This is a real optimization target because it reduces total work, not just perceived lag.

4. `PixelIconGrid` also refreshes prepared pixmaps on `Show`.
   This can be redundant if DPR, metrics, and item pixmap inputs have not changed.

5. Artifact Browser target creation is still widget-heavy.
   The in-place target button approach fixed repeated filter rebuilds, but first creation still builds 74 `MarqueeButton`/`QIcon` target rows and costs about `0.6-0.7 s` on this laptop.

## Optimization Rules For Follow-Up

- Optimize by reducing total computation and repeated work first.
- Do not hide cold work by moving it to a later click, background timer, lazy path, or prewarm pass unless the task explicitly starts the loader/prewarm/cache stage.
- Until the loader/cache stage starts, keep cold-start and interaction lag visible and measurable so the eventual loader can cover a known list of work.
- Cache/prewarm candidates from this measurement should be recorded, not silently implemented as lag-hiding.

## Suggested Follow-Up Targets

1. Make `PixelIconGrid.update_item` distinguish pixmap-affecting changes from paint-only changes. `outline`, `overlay_fill`, and non-pixmap properties should update state and repaint without calling `_refresh_prepared_pixmaps`.
2. Guard `PixelIconGrid` show/DPR refreshes with an input signature so unchanged pixmap inputs are not reprocessed.
3. Remove duplicated SQLite/account asset loading between Character/Weapon and PvP workspaces without deferring PvP work merely to hide startup cost.
4. Profile Artifact Browser target button creation separately before choosing whether the final fix should be fewer widgets, cheaper icon preparation, or a future loader-covered prewarm.
5. When the startup loader/cache stage begins, include AppShell import cost, Character/Weapon grids, PvP Deck grids, Artifact Browser store load, target buttons, preset/edit controls, and pixmap/text/marquee preparation in one explicit loader manifest.
