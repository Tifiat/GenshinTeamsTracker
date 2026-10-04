# Artifact Browser First Open: Direct Work Reduction

Date: 2026-10-03. Owner/current acceptance: [Artifact Browser](../ARTIFACT_BROWSER.md).
Checkout: worker3; base HEAD `bde62f9`, uncommitted working tree. Existing applied
preset persistence/outline implementation is present in both comparison stages.
Device: Windows AMD64, Intel Xeon E5-2690 at 2.90 GHz; Python 3.11.5,
PySide6 6.11.0. Background load and OS filesystem caches are uncontrolled.

## Method and boundaries

Probe: `tools/experiments/artifact_browser_perf_probe.py`.

```powershell
.\.venv\Scripts\python.exe tools/experiments/artifact_browser_perf_probe.py --profile
1..3 | ForEach-Object { .\.venv\Scripts\python.exe tools/experiments/artifact_browser_perf_probe.py }
```

Fresh processes, serial runs, `QT_QPA_PLATFORM=offscreen`, 1250x800 host. The
character/weapon workspace is constructed before the measured interval. A
right-panel character with saved presets is pending when the Artifact Browser
is first opened. Inventory: 604 artifacts, 29 presets, 78 account characters;
79 target buttons and six visible preset rows after selection.

Construction is the synchronous workspace activation call; first-open adds one
event-loop pass for initial rendering. This excludes whole-AppShell startup,
human click latency and physical display acceptance. The browser's existing
persistent preview/bonus icon cache directories are redirected to fresh scratch
for each process; OS caches are not purged. No product cache is added by this
change. Profiled timings are diagnostic and excluded from medians.

The source DB is opened read-only for SQLite backup. The owned snapshot,
History root and render-cache files use `managed_scratch` and are removed on
exit, including failures. Final probe connections are restricted to its owned
snapshot (or memory). Initial baseline exposed a pre-existing JSON-action count
helper that also initialized/read the checkout's default DB; this repeated
work is included in baseline counts and removed from the browser path. No
equipment/import operation is invoked. Each run reported cleanup of 2,976,905
bytes and no remaining job directory. Only these aggregate findings are retained;
no account rows, SQL literals, raw DB copies or profiler dumps are retained.

## Unprofiled comparison

| Metric, ms | Before: run 1 / 2 / 3 | After: run 1 / 2 / 3 |
| --- | --- | --- |
| Construction | 1760.014 / 1540.608 / 1845.180 | 690.571 / 646.001 / 652.867 |
| First open with initial rendering | 2036.014 / 1824.589 / 2116.189 | 930.792 / 881.709 / 869.614 |
| Transparent trimming, three calls | 777.682 / 634.950 / 731.718 | 2.896 / 2.609 / 2.712 |

Median construction: 1760.014 -> 652.867 ms (62.9% less; 2.70x faster).
Median first open: 2036.014 -> 881.709 ms (56.7% less; 2.31x faster).
This is a controlled local result, not a guarantee for every machine or account.

## Work counts and causes

| Per first opening | Before | After |
| --- | ---: | ---: |
| SQLite connections | 15 | 7 |
| SELECT statements | 88 | 17 |
| CREATE statements from idempotent setup | 476 | 60 |
| PRAGMA statements | 72 | 20 |
| Schema setup legacy-target INSERT/COMMIT cycles | 7 | 1 |
| Ordinary / virtual preset-target SELECTs | 29 / 29 | 1 / 1 |
| Target item loads | 2 | 1 |
| Target-list / preset-list / preview updates | 3 / 3 / 3 | 1 / 1 / 1 |
| Preset row constructions | 12 | 6 |
| Target button constructions | 79 | 79 |

Baseline cProfile: 199,464 `pixelColor` calls during thresholded alpha trimming,
three trims taking 1525.853 ms under profiling. Final profile trims take 6.016
ms with unchanged pixel bounds/threshold semantics. Profiled first open drops
from 3020.392 to 971.597 ms; use the unprofiled medians for the headline.

Main artifact/substat/tag loading was already batched; no per-artifact DB fetch
was found there. Preset targets had N+1 reads. Browser construction applied
pending targets afterward, repeating list/preview work. JSON action repaints
and preset/summary/equipment reads repeated schema setup. The icon resolver
also performed both `exists` and `is_file` for the same path; one check suffices.

Final diagnostic costs still include store construction (~212 ms), target
selector UI (~183 ms), preset loading/rows (~112 ms) and initial rendering
(~238 ms). These overlap within the call tree and must not be summed as
independent costs. Remaining Qt widgets, raster decoding and filesystem checks
have not been moved to timers/background hydration or a new loader.

## Verification and next gate

83 focused tests pass across three final batches (30 + 52 + 1). They cover batched
query counts for 1/30/120 presets, ordering and per-build virtual-account merge,
threshold/DPR/pixel parity, initialized-reader result parity, missing-equipment
schema initialization, JSON flag reload,
initial pending target/equipment priority/highlight, applied preset persistence,
rollback/import/equipment semantics, sorting/localization and relevant AppShell
switching/edit/layout paths. These are automated gates, not physical UI acceptance.

User smoke: restart and first-open Artifacts with/without a right-panel target;
check equipped cards/preview/name/green preset outline; switch targets, preview
and deselect a preset, open edit/cancel and inspect icons/layout at normal scale.
Computer Use is prohibited for this scope. Do not equate this measurement with
whole application startup or clear the user's existing caches/data for a test.
