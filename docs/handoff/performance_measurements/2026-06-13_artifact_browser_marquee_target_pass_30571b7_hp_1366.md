# Artifact Browser Marquee / Target Button Pass

- Timestamp: `2026-06-13T13:50:54+03:00`
- Measured commit: `30571b7`
- Working tree: MarqueeButton optimization applied, not committed yet
- Device: weak 1366px HP Notebook, Windows 11 Pro, AMD A6-5200 class CPU, ~11.5 GB RAM
- Probe: `tools/experiments/appshell_perf_probe.py`
- Environment: `QT_QPA_PLATFORM=offscreen`, `GTT_PERF_LOG=1`

## Change Under Test

`MarqueeButton` no longer creates a `QTimer` during construction and no longer
does marquee width/style synchronization while the button is inactive. The timer
is created only when the text is active and overflowing, for example checked,
focused, or hovered.

This reduces total cold widget work for the Artifact Browser target list without
moving target button creation to a later click and without adding persistent
cache.

## Artifact-Only Probe

Command:

```powershell
for ($i = 1; $i -le 2; $i++) {
  .\.venv\Scripts\python.exe tools\experiments\appshell_perf_probe.py --mode artifact |
    Select-String -Pattern '^\[PROBE\]|^\[PERF\] (artifact_browser_init|artifact_workspace_lazy_create|artifact_target_button_ensure|artifact_target_filter_refresh)'
}
```

Filtered result:

```text
[PERF] artifact_target_button_ensure total=297.6ms initial=True created=74 icon_assign=229.8ms total_buttons=74
[PERF] artifact_target_filter_refresh total=353.7ms sync=8.0ms ensure=343.1ms filter=0.7ms update=1.8ms mode=in_place created_buttons=74 shown=0 hidden=0 visible=73 total_targets=73 standard=all selected_filters=0
[PERF] artifact_browser_init embedded=True total=1597.2ms store=379.9ms model=0.6ms targets=6.4ms ui=1030.5ms presets=35.9ms filter=18.0ms build_panel=34.2ms artifacts=101 resize_events=0
[PERF] artifact_workspace_lazy_create total=1725.3ms artifacts=101 adaptive_runs=0 resize_events=0
[PROBE] scale=1.2ms app_shell_import=2920.8ms construct=4948.3ms show_initial=1972.9ms artifact_first=2484.1ms artifact_repeat=285.3ms marker_one=0.0ms marker_all=0.0ms characters=73 weapons=58 artifacts=101

[PERF] artifact_target_button_ensure total=367.1ms initial=True created=74 icon_assign=295.8ms total_buttons=74
[PERF] artifact_target_filter_refresh total=379.9ms sync=9.8ms ensure=367.3ms filter=0.8ms update=1.9ms mode=in_place created_buttons=74 shown=0 hidden=0 visible=73 total_targets=73 standard=all selected_filters=0
[PERF] artifact_browser_init embedded=True total=1483.9ms store=326.8ms model=0.8ms targets=9.5ms ui=1037.0ms presets=39.5ms filter=6.4ms build_panel=25.0ms artifacts=101 resize_events=0
[PERF] artifact_workspace_lazy_create total=1568.7ms artifacts=101 adaptive_runs=0 resize_events=0
[PROBE] scale=1.7ms app_shell_import=2383.0ms construct=4245.1ms show_initial=2238.0ms artifact_first=2006.1ms artifact_repeat=208.9ms marker_one=0.0ms marker_all=0.0ms characters=73 weapons=58 artifacts=101
```

## Previous Comparison Point

Previous after-optimization artifact-only repeats from
`docs/handoff/performance_measurements/2026-06-13_appshell_perf_probe_after_optimization_c371ef4_hp_1366.md`:

```text
artifact_target_button_ensure total=586.6-752.6ms
artifact_browser_init total=1928.6-2338.1ms
artifact_workspace_lazy_create total=2183.3-2589.0ms
```

## Result

- Target button creation improved from `586.6-752.6 ms` to `297.6-367.1 ms`.
- Artifact Browser init improved from `1928.6-2338.1 ms` to `1483.9-1597.2 ms`.
- Artifact workspace creation improved from `2183.3-2589.0 ms` to
  `1568.7-1725.3 ms`.

Remaining cold work still includes QWidget target button construction, target
portrait icon assignment, Artifact store load, and the broader Artifact Browser
UI tree. These remain valid candidates for direct simplification first, then
future loader/prewarm if no lower-work implementation is chosen.
