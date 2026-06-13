# AppShell Perf Probe - After Optimization Pass

- Timestamp: `2026-06-13T13:09:52+03:00`
- Measured commit: `c371ef4`
- Working tree: optimization changes applied, not committed yet
- Device: weak 1366px HP Notebook, Windows 11 Pro, AMD A6-5200 class CPU, ~11.5 GB RAM
- Probe: `tools/experiments/appshell_perf_probe.py`
- Environment: `QT_QPA_PLATFORM=offscreen`, `GTT_PERF_LOG=1`

## Main After Run

Command:

```powershell
.\.venv\Scripts\python.exe tools\experiments\appshell_perf_probe.py --mode all
```

Filtered result:

```text
[PERF] filter_characters total=1035.3ms load=0.0ms load_source=cache predicate=0.6ms sort=0.4ms rebuild_cards=1033.2ms count=73 standard=all
[PERF] filter_weapons total=531.8ms load=0.0ms load_source=cache predicate=1.3ms sort=0.3ms rebuild_cards=529.3ms count=58
[PERF] artifact_target_button_ensure total=768.0ms initial=True created=74 icon_assign=434.5ms total_buttons=74
[PERF] artifact_target_filter_refresh total=783.5ms sync=12.3ms ensure=768.3ms filter=0.7ms update=1.8ms mode=in_place created_buttons=74 shown=0 hidden=0 visible=73 total_targets=73 standard=all selected_filters=0
[PERF] artifact_browser_init embedded=True total=2191.9ms store=507.2ms model=0.6ms targets=7.1ms ui=1540.1ms presets=22.1ms filter=20.4ms build_panel=70.1ms artifacts=101 resize_events=0
[PERF] artifact_workspace_lazy_create total=2379.3ms artifacts=101 adaptive_runs=0 resize_events=0
[PERF] marker_incremental total=0.3ms affected=1 updated=1 visible_cards=73
[PERF] marker_incremental total=10.2ms affected=73 updated=73 visible_cards=73
[PROBE] scale=1.0ms app_shell_import=1499.3ms construct=3070.1ms show_initial=2720.2ms artifact_first=3055.1ms artifact_repeat=253.0ms marker_one=50.7ms marker_all=60.4ms characters=73 weapons=58 artifacts=101
[PROBE_GRID] key=refresh:app_shell_character_grid count=4 total=1055.6ms
[PROBE_GRID] key=refresh:app_shell_weapon_grid count=4 total=516.2ms
[PROBE_GRID] key=refresh:pvp_deck_icon_grid count=4 total=913.8ms
[PROBE_GRID] key=refresh_items:app_shell_character_grid count=146 total=0.0ms
[PROBE_GRID] key=refresh_items:app_shell_weapon_grid count=116 total=0.0ms
[PROBE_GRID] key=refresh_items:pvp_deck_icon_grid count=116 total=0.0ms
[PROBE_GRID] key=set_items:app_shell_character_grid count=1 total=1020.3ms
[PROBE_GRID] key=set_items:app_shell_weapon_grid count=1 total=503.4ms
[PROBE_GRID] key=set_items:pvp_deck_icon_grid count=2 total=915.5ms
[PROBE_GRID] key=set_items_count:app_shell_character_grid count=73 total=0.0ms
[PROBE_GRID] key=set_items_count:app_shell_weapon_grid count=58 total=0.0ms
[PROBE_GRID] key=set_items_count:pvp_deck_icon_grid count=116 total=0.0ms
[PROBE_GRID] key=update_item:app_shell_character_grid count=74 total=7.2ms
[PROBE_GRID] key=update_item_changes:app_shell_character_grid:outline count=74 total=0.0ms
[PROBE_PIXMAP] key=app_shell_character_grid:hit=0 count=73 total=980.2ms
[PROBE_PIXMAP] key=app_shell_weapon_grid:hit=0 count=53 total=302.9ms
[PROBE_PIXMAP] key=app_shell_weapon_grid:hit=1 count=5 total=8.0ms
[PROBE_PIXMAP] key=app_shell_weapon_grid_overlay:hit=0 count=20 total=101.2ms
[PROBE_PIXMAP] key=pvp_deck_icon_grid:hit=0 count=111 total=871.2ms
[PROBE_PIXMAP] key=pvp_deck_icon_grid:hit=1 count=5 total=2.1ms
[PROBE_ARTIFACT_TARGET] module_import=1097.6ms buttons=74 button_total=757.0ms ensure_calls=1 ensure_total=768.3ms
```

## Startup Import Check

Command:

```powershell
.\.venv\Scripts\python.exe tools\experiments\appshell_perf_probe.py --mode startup --importtime
```

Filtered result:

```text
[PROBE_IMPORT] cumulative=4447.4ms self=274.0ms module=ui.app_shell
[PROBE_IMPORT] cumulative=788.5ms self=98.2ms module=hoyolab_export.account_storage
[PROBE_IMPORT] cumulative=719.2ms self=0.2ms module=ui.pvp_browser.placeholders
[PROBE_IMPORT] cumulative=719.0ms self=6.1ms module=ui.pvp_browser
[PROBE_IMPORT] cumulative=709.8ms self=24.0ms module=ui.pvp_browser.window
[PROBE_IMPORT] returncode=0
[PERF] filter_characters total=1507.2ms load=0.0ms load_source=cache predicate=0.6ms sort=0.8ms rebuild_cards=1504.9ms count=73 standard=all
[PERF] filter_weapons total=613.3ms load=0.0ms load_source=cache predicate=2.5ms sort=0.4ms rebuild_cards=609.5ms count=58
[PROBE] scale=9.4ms app_shell_import=3098.8ms construct=4005.0ms show_initial=2833.6ms artifact_first=0.0ms artifact_repeat=0.0ms marker_one=0.0ms marker_all=0.0ms characters=73 weapons=58 artifacts=0
```

## Artifact Button Variance Recheck

Command:

```powershell
.\.venv\Scripts\python.exe tools\experiments\appshell_perf_probe.py --mode artifact
```

Two filtered artifact-only runs:

```text
[PERF] artifact_target_button_ensure total=586.6ms initial=True created=74 icon_assign=352.3ms total_buttons=74
[PERF] artifact_browser_init embedded=True total=1928.6ms store=558.2ms ui=1204.2ms artifacts=101
[PROBE] app_shell_import=1596.2ms construct=3297.5ms show_initial=2184.6ms artifact_first=3125.3ms artifact_repeat=286.9ms artifacts=101

[PERF] artifact_target_button_ensure total=752.6ms initial=True created=74 icon_assign=484.0ms total_buttons=74
[PERF] artifact_browser_init embedded=True total=2338.1ms store=452.1ms ui=1640.6ms artifacts=101
[PROBE] app_shell_import=2638.0ms construct=4985.1ms show_initial=2690.8ms artifact_first=3789.4ms artifact_repeat=388.5ms artifacts=101
```

Conclusion: target button creation remains noisy and still belongs in
`docs/handoff/PRELOADER_BACKLOG.md`; the current pass only adds logging and
bulk repaint suppression.

## Baseline Comparison

Baseline file:
`docs/handoff/performance_measurements/2026-06-13_appshell_perf_probe_baseline_c371ef4_hp_1366.md`

| Metric | Baseline | After | Change |
| --- | ---: | ---: | ---: |
| AppShell construct | `5901.2 ms` | `3070.1 ms` | `48.0%` faster |
| Initial show | `4638.6 ms` | `2720.2 ms` | `41.4%` faster |
| First Artifact Browser open | `3558.1 ms` | `3055.1 ms` | `14.1%` faster in the main run |
| Repeat Artifact Browser switch | `525.0 ms` | `253.0 ms` | `51.8%` faster |
| Marker one | `131.6 ms` | `50.7 ms` | `61.5%` faster |
| Marker all | `4973.7 ms` | `60.4 ms` | `82.3x` faster |
| Character grid `update_item` marker path | `4914.6 ms` | `7.2 ms` | pixmap reload removed |
| Character reload source | SQLite pass before cache warm | `load_source=cache` | duplicate PvP/account pass removed |
| Weapon reload source | SQLite pass before cache warm | `load_source=cache` | duplicate PvP/account pass removed |

## Acceptance Notes

- Outline-only marker update triggers zero pixmap loads after the initial grid
  setup. The probe reports only initial `hit=0` pixmap loads and no marker-path
  pixmap reloads.
- All-character marker update is more than `10x` faster than the recorded
  baseline (`4973.7 ms` to `60.4 ms` in the main run; `marker_incremental`
  itself reports `10.2 ms`).
- Character/Weapon reload after PvP construction uses shared cache source.
- First Artifact Browser open is faster in the main before/after probe, but
  artifact-only repeats show high system variance on this laptop. Remaining
  target button cold work is recorded in the preloader backlog.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest tests.ui.utils.test_pixel_icon_grid tests.ui.pvp_browser.test_pvp_browser
.\.venv\Scripts\python.exe -m unittest tests.ui.app_shell.test_app_shell.AppShellTest.test_app_shell_reuses_character_weapon_asset_cache_for_pvp_workspace tests.ui.app_shell.test_app_shell.AppShellTest.test_app_shell_constructs_with_character_weapon_workspace tests.ui.app_shell.test_app_shell.AppShellTest.test_pvp_workspace_switches_left_area_and_right_dock_policy
.\.venv\Scripts\python.exe -m py_compile tools\experiments\appshell_perf_probe.py ui\utils\pixel_icon_grid.py ui\app_shell.py ui\pvp_browser\window.py ui\artifact_browser\window.py
```

- `unittest` PixelIconGrid/PvP suite: `19` tests passed.
- Targeted AppShell tests: `3` tests passed.
- Compile check: passed.
- `pytest` command was not available in this virtualenv: `No module named pytest`.
- Full `tests.ui.app_shell.test_app_shell` via `unittest` timed out earlier on
  this laptop, so only the new and directly related AppShell tests were run.
