# Independent populated startup A/B — 7 October 2026

Owner: independent main verification chat. **Technical PASS within scope; no
new package finding. Not installed in main.** Benchmark phase is complete and
the numerical slot is free. No native UI or PyCharm click acceptance is claimed.

## Exact package

Main baseline: ef60d82905aae05fe6490b8cd57835daaccbc1fd; its product equals
77c26458d3a0beda3f88fc4cda1b129053dad081 (later differences are documentation).
Reviewed source: Worker3 committed 9830a5137971ca72faeb42285a2c912e30e47fe9,
parent 77c2645, from C:/Users/user/Desktop/worker3 GTT. Foreign working files
were not used. The exact commit delta has ten paths:

- Product: hoyolab_export/asset_paths.py and ui/character_assets.py.
- Regression: tests/ui/character_assets/test_asset_loading_batch.py.
- Manual probe: tools/experiments/appshell_weapon_startup_probe.py.
- Documentation: docs/handoff/PRELOADER_BACKLOG.md plus five
  performance_measurements/2026-10-07_asset_startup_* receipts: worker3 Markdown
  and ab/parity/tests/refresh_tests JSON.

The full ten-path patch passed apply-check and application in a disposable main
copy. Product and regression contents match the committed candidate, normalizing
CRLF/LF only. No migration, dependency install, engine synchronization or other
prerequisite product delta is required. Main product, refs, runtime, live
profiles, foreign files and shared statuses were not changed. Only this receipt
and its catalog row are retained; integration belongs to the orchestrator.

## Method and preservation

Exactly three pairs, order before/after, after/before, before/after. Main
.venv/Scripts/python.exe (Python 3.11.5, PySide6 6.11.0) executed each disposable
ui/app_shell_smoke.py file with working directory ui, followed by its normal
supervised child. Qt was offscreen; project root and observer were on PYTHONPATH.
Fresh processes and physical copies, project bytecode disabled, identical
instrumentation and no persisted project cache. OS file cache was warm /
uncontrolled, not flushed. No optimizer, engine build or numerical run occurred.

One selected-profile template supplied all six copies: 604 artifacts,
78 characters, 77 observed weapon stacks, actual images/crop manifest, saved
History/PvP, state/preferences, four allowlisted public catalogs, active engine
manifest and startup catalog sources. The engine subset included catalog Go,
artifact config/source, issue and substat metadata; executables were excluded.
Raw import JSON beyond language/manifest, authentication, cookies, browser and
debug trees were excluded. The copied registry retained only selected metadata.

The source DB had no WAL, SHM, rollback journal or pending migration. It was
opened with SQLite mode=ro&immutable=1, quick-checked and backed up once.
Sidecar absence and all 2,302 staged source-file SHA256 identities were checked
before/after capture and after each run. All remained identical, including
registry, DB, settings, images, catalogs and product. Absolute main-root references
were rewritten only in disposable JSON/DB values, identically on both sides.
Copied DBs passed quick_check. No source application was closed.

The existing startup_profile.disposable_snapshot lifecycle owned the template,
six launch copies and separate test copies, including failure paths. Runtime
inputs: 1,592 files / 129,450,002 bytes. Full template: 2,302 files /
157,239,537 bytes. Largest post-run launch copy: 157,291,930 bytes.
Every owned root was removed; final temp-prefix inspection found no remaining
gtt-startup-* directory. Six launches used 72.478 seconds total launcher wall time.
All six exited zero, with no stderr, timeout or guard event.

The observer rejected source-private access, writes outside the copy, other
desktop-checkout reads, network and unexpected process paths. Qt process starts
and Qt network entrypoints were also blocked. Timing includes guards, named
wrappers, SQL tracing and payload hashing. First-ready is the first queued Qt
tick after AppShell show, not physical usability or a PyCharm click stopwatch.

## Comparable facts

Times are milliseconds; each cell is baseline / candidate.

| Pair | Launcher to first-ready | Character assets | Weapon assets |
| --- | ---: | ---: | ---: |
| 1, before then after | 11,533.269 / 11,403.361 | 1,071.417 / 677.016 | 1,052.505 / 711.682 |
| 2, after then before | 11,750.165 / 10,943.457 | 1,226.972 / 697.434 | 933.357 / 707.771 |
| 3, before then after | 11,352.227 / 10,576.721 | 994.766 / 640.773 | 955.559 / 688.235 |

| Named stage, median | Baseline | Candidate |
| --- | ---: | ---: |
| Launcher to first-ready | 11,533.269 | 10,943.457 |
| UI child to first-ready | 10,710.564 | 10,029.716 |
| Import ui.app_shell | 3,282.657 | 3,571.882 |
| AppShell construction | 6,144.408 | 5,320.920 |
| Character asset list | 1,071.417 | 677.016 |
| Weapon asset list | 955.559 | 707.771 |
| History construction | 1,649.419 | 1,604.113 |
| PvP construction | 2,675.616 | 1,898.478 |
| Included PvP Decks construction | 2,576.767 | 1,803.284 |
| Active artifact-set catalog | 384.482 | 374.171 |

Launcher median decreased **589.812 ms / 5.11%**. Paired reductions:
129.908, 806.708 and 775.506 ms. Readiness ranges: baseline
11,352.227–11,750.165 ms; candidate 10,576.721–11,403.361 ms.
Ranges overlap, n=3 is small and import jitter is material: a bounded local
improvement, not a universal 5% promise. Both asset stages improved in every pair.
Nested stages overlap and must not be added. The earlier
[populated audit](2026-10-07_main_startup_and_merge_audit.md) used different
instrumentation/input staging; its 14-second observations are not an A/B arm.

Owner SELECTs and equipment-schema passes were 77 / 1 in every pair.
All six complete adapter payloads matched after normalizing only disposable
account/project prefixes. Character SHA256:
569b047796a936f11b934b3d1dc14b17fb4213c50fd939069b6a41c462be4d32;
weapon SHA256:
04a41f9b593e19b7b463271c59dda8c1c49ede1e2cff158510850fba7177887a.
All logical DB table contents were unchanged across each copied launch.
Copy DB byte preservation is not asserted; source DB preservation is.

## Review and checks

Read-only independent review found no new regression in batch lifetime, asset
freshness, owner ordering, refresh or profile isolation. Finally releases a batch
after one synchronous list read, including exceptions; nested reads reuse it.
Completed imports atomically publish the manifest before later reads. Positive
and negative file results and resolved paths are rechecked by the next batch.
Both owner queries order by character ID. Equipment is read afresh and the
separate owner-badge refresh retains its path. Real profile switching starts a
new process under the existing contract.

**41 distinct focused checks passed** in the final guarded disposable candidate
process: exit zero, no guard violations, 4.155 seconds unittest time.

- Five candidate batch regressions; 13 existing character-asset checks.
- Two AppShell import-completion refresh/reset signal checks.
- Twenty account equipment/schema/import-observation checks.
- One independent synthetic check of account-relative manifest paths in two
  isolated profile roots, foreign/traversal rejection and deletion visibility
  on the next batch. Resolver and adapter contexts were rebound only inside
  the fixture; no actual profile switch was performed.

Earlier setup stopped before tests on a CRLF-versus-LF byte assertion; normalized
content verification resolved it. One broader 58-test attempt was INCOMPLETE:
the process guard rejected the profile-context test's extra subprocess; network
guards rejected Windows asyncio socketpair setup in 16 asset-layer tests.
Those 17 are not PASS and were excluded from the final bounded selection.
No guard was relaxed. All copies were cleaned; no startup measurement was rerun.

The pre-existing absolute-image-path adapter bypass and shared target-preview
cache lifecycle gap remain open in both versions; see the prior audit. This
review is not a global isolation certificate. Authenticated imports, actual
multiaccount switching, physical image quality/scaling, PyCharm launch and the
reported brief flash remain unverified. No loader, first-click deferral,
persistent cache or image transformation was introduced. Ready integration
source is exactly the commit above; main has not been accelerated by this audit.
