# AppShell Performance Probe Baseline - 2026-06-13

## Context

- Measured at: `2026-06-13T12:54:59+03:00`.
- Measured code revision: `c371ef4`.
- Device profile: weak 1366px HP Notebook, AMD A6-5200 APU with Radeon HD Graphics, 11.5 GB RAM, Windows 11 Pro 10.0.22621.
- Probe command: `.\.venv\Scripts\python.exe tools\experiments\appshell_perf_probe.py --mode all --importtime`.
- Probe environment: `QT_QPA_PLATFORM=offscreen`, `GTT_PERF_LOG=1`.
- This is the baseline before the pre-loader optimization pass. The only uncommitted file at the time was the new diagnostic probe itself.

## Headline Results

- `ui.app_shell` import: `10900.5 ms` cumulative by `python -X importtime`.
- AppShell probe import inside the measured process: `3694.1 ms`.
- `AppShell()` construction: `5901.2 ms`.
- Initial show/events: `4638.6 ms`.
- First Artifact Browser open: `3558.1 ms`.
- Repeat Artifact Browser switch: `525.0 ms`.
- One marker update: `131.6 ms`.
- All-character marker update: `4973.7 ms`.

## Grid / Pixmap Attribution

- Character grid `set_items`: `1592.8 ms` for `73` items.
- Weapon grid `set_items`: `550.3 ms` for `58` items.
- PvP deck grid `set_items`: `1616.3 ms` for `116` total items across two grids.
- Character grid refresh calls: `78`, total `6522.3 ms`.
- Character grid `update_item(outline=...)`: `74` calls, total `4914.6 ms`.
- Character grid pixmap cache hits during marker updates: `5475` calls, `4315.4 ms`.
- Character grid pixmap cold loads: `73` calls, `1581.9 ms`.
- PvP deck grid cold loads: `111` calls, `1595.5 ms`.

## Artifact Target Attribution

- Artifact module import for target instrumentation: `2438.8 ms`.
- Target buttons created: `74`.
- `_make_build_target_button` total: `523.8 ms`.
- `_ensure_build_target_buttons` total: `536.3 ms`.

## Acceptance Targets For This Pass

- Outline-only marker updates should trigger zero pixmap loads.
- All-character marker update should be at least 10x faster than the baseline `4973.7 ms`.
- PvP should not perform its own SQLite account asset loads when AppShell can provide Character/Weapon workspace snapshots.
- First Artifact Browser open must not regress from the baseline.
- Remaining unavoidable cold work should be recorded in `docs/handoff/PRELOADER_BACKLOG.md`, not hidden by lazy loading or persistent cache.
