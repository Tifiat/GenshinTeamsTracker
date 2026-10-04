# Artifact Browser inventory scaling and equipment actions

Measured 2026-10-04 in Worker3, branch `worker3`. The reference is the previously
verified, uncommitted preset/first-open stage described by the
[2026-10-03 receipt](2026-10-03_artifact_first_open_worker3.md); checkout HEAD
before this stage is the documentation commit
`26483a39fa0e0e1b213ae8de05a4ccc06a0f72f5`. The code and this receipt accompany
the local browser-stage commit; its full hash is recorded in the worker status.
This is controlled offscreen evidence, not physical UI or import acceptance.

## Method and lifecycle

Windows AMD64, Intel Xeon E5-2690 2.90 GHz, Python 3.11.5, PySide6 6.11.0,
SQLite 3.42.0. The probe is `tools/experiments/artifact_browser_perf_probe.py`.
Use the available project interpreter with `PYTHONDONTWRITEBYTECODE=1`:

```powershell
python tools/experiments/artifact_browser_perf_probe.py --actions
python tools/experiments/artifact_browser_perf_probe.py --artifact-factor 4 --preset-factor 4 --actions
python tools/experiments/artifact_browser_perf_probe.py --artifact-factor 8 --preset-factor 8 --actions
```

Each fresh process reads the calling checkout's database through a read-only
SQLite backup into `managed_scratch`. Factor 4/8 repeats artifact rows and their
substats/tag links with distinct fixture IDs/fingerprints, and preset rows with
their existing slot/target relationships. It does not duplicate equipment,
weapons or characters, and is not an import/deduplication test. Foreign-key
integrity is checked before measurement. Character and weapon grids are already
constructed; the timed host is 1250x800, offscreen. First opening includes
synchronous construction and one event-loop rendering pass. Actions then switch
targets and back, preview/deselect a preset, apply a full preset, and equip a
free artifact. Conflict consent applies only to this disposable fixture.

All traced connections after backup must use the owned snapshot or memory.
History and the existing browser PNG caches are redirected to the same owned
job. Every run removes the job on success/failure; the three fixture sizes
reported 2,988,071 / 4,454,439 / 6,408,231 bytes removed and no remaining job
directory. The managed root has no remaining job directories after the runs.
No source account writes, visible application, Computer Use, new product cache,
background hydration, raw database copy or profiler dump is retained. Only
aggregate timing/count evidence is saved here. This fixture does not model the
user's monitor at 150% system scaling; that separate setting is in shared TODO.

## Work removed

The initialized browser passes explicit skip-setup flags to equipment services
and preset readers. Standalone defaults still initialize missing tables. Live
owner reads, artifact validation, exact applied-slot validation and the single
equipment/marker transaction remain. Conflict preflight is one batch, with
mutation-time owner checks retained after the confirmation boundary.

A panel's freshly read slots feed its highlights and set-bonus icons, rather
than reopening the database for each view component. Applying a preset changes
checked/outline state without rebuilding the unchanged preset list; pending
delete controls are still rebuilt when canceled. A completed preset row shows
its children through Qt parent visibility, avoiding explicit descendant shows.
Full inventory substat/tag reads use their indexed artifact parent relationships
and result-ID guards, without a bind parameter for every artifact.

| Per operation | Connections before -> after | SELECT before -> after | CREATE IF NOT EXISTS before -> after |
| --- | ---: | ---: | ---: |
| First opening | 7 -> 6 | 17 -> 16 | 60 -> 60 |
| Target switch/back | 4 -> 3 | 5 -> 4 | 0 -> 0 |
| Preset preview | 3 -> 3 | 9 -> 8 | 60 -> 0 |
| Preset deselection | 6 -> 3 | 7 -> 4 | 0 -> 0 |
| Full preset apply | 8 -> 6 | 38 -> 32 | 88 -> 0 |
| Single artifact equip | 8 -> 5 | 13 -> 10 | 16 -> 0 |

Counts are stable at all three fixture sizes. First opening still constructs
79 target buttons once and 6 / 24 / 48 matching preset rows. Apply constructs
zero replacement rows instead of 6 / 24 / 48. Initial schema work is retained
for normal compatibility/migration; no hidden readiness cache replaces it.

## Unprofiled timings and limits

Two fresh unprofiled processes per size before and after; numbers below are
medians in milliseconds. These small sequential samples share the user's
machine with other work and are not randomized or a hardware-isolated benchmark.

| Artifacts / presets / characters | First open before -> after | Apply synchronous before -> after | Apply including render before -> after |
| --- | ---: | ---: | ---: |
| 604 / 29 / 78 | 693.119 -> 727.675 | 119.455 -> 58.743 | 199.177 -> 127.151 |
| 2416 / 116 / 78 | 940.415 -> 963.675 | 226.943 -> 70.074 | 322.043 -> 186.801 |
| 4832 / 232 / 78 | 1279.526 -> 1400.014 | 417.142 -> 71.627 | 528.560 -> 171.745 |

The largest fixture's apply is 5.82x faster synchronously and 3.08x faster with
rendering in these samples. The work counts explain the gain: no repeated schema
setup, conflict query per slot or full preset-list recreation. The continuation
does **not** demonstrate a further first-open speedup. Its measured first-open
times are slightly higher; remaining widget/raster work and host variability
prevent claiming every path became faster. The original cold-icon/duplicate
startup fixes keep their separate dated evidence and protocol.

Other synchronous medians, before -> after:

| Action | 604 artifacts | 2416 artifacts | 4832 artifacts |
| --- | ---: | ---: | ---: |
| Switch to alternate target | 84.255 -> 86.353 | 132.639 -> 136.810 | 199.911 -> 233.937 |
| Switch back to target with most presets | 78.259 -> 77.032 | 188.351 -> 214.499 | 370.419 -> 537.009 |
| Preview | 43.800 -> 35.932 | 46.900 -> 48.647 | 85.471 -> 106.428 |
| Deselect | 48.936 -> 32.726 | 58.141 -> 41.458 | 66.218 -> 93.274 |
| Single artifact equip | 73.473 -> 55.495 | 71.220 -> 58.975 | 70.920 -> 61.439 |

Long target-switch rebuilding remains a separate performance limit, not a
closed speedup claim. A diagnostic profile of 48-row refresh attributed ~373 ms
to the list refresh, ~185 ms to row construction, ~133 ms to 384 explicit
row/descendant `show` calls and ~57 ms to source-icon file identity. Profile
costs overlap and must not be summed. The final code uses one explicit show per
completed row. A bounded adjacent memory-only reference run restoring the old
descendant loop (`--reference-child-show`) measured switch-back 597.007 ms versus
546.969 ms without it; with rendering 820.169 versus 745.872 ms. That single
diagnostic pair supports removing duplicate shows, not a general target-switch
speedup. The reference is compiled from this one current method, lives only in
memory during the probe and is never installed in product code or stored as
a second patch stack. Row/raster work still grows with visible preset count.

## Verification and remaining acceptance

92 distinct focused checks PASS: 50 account/import/preset/snapshot/pixmap checks
and 42 Artifact Browser/AppShell checks. Coverage includes a 1217-artifact read
with SQLite's bind limit lowered to 64, stable substat/tag ordering and parent-ID
membership, empty inventory, default schema recreation by standalone services,
initialized-reader parity, single conflict preflight, row identity after apply,
pending-delete cancellation, one preview-slot read on deselect, bonus-cell slot
reuse, visible preset descendants after open/rebuild, manual toggling, exact
marker invalidation, reopen/rename, import preservation and failed-apply rollback.
AppShell gates cover operation-target ownership, equipment propagation, swap,
editing, widget reuse and adjacent layout behavior. The initial selection of a
nonexistent import-test module was corrected to `test_import_equipment`; this
was a test-selector error, not a product failure. The completed cohorts pass.

User smoke remains pending until the import fix is ready: start AppShell from
this checkout, open Artifacts with/without a selected character, apply a preset,
switch away/back, preview/deselect, reopen, change one artifact and enter/cancel
editing. Check retained name and green outline until equipment changes, current
owner icons, unchanged layout and practical latency. The user performs these
visible checks; offscreen tests do not replace them. Main/master integration
and push are separate, unperformed Git gates.
