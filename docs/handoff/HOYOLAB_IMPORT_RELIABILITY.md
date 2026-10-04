# HoYoLAB Import Failure Boundaries

<!-- handoff-current: hoyolab-import -->
2026-10-04. Worker5 is replacing the earlier partial-import hotfix with
source-first, account-bound publication. A validated source snapshot is durable
before one SQLite transaction publishes artifacts, account observations,
optional equipment and its receipt. Valid unknown sets retain source IDs and
stats with nullable canonical identity; no relic is skipped because references
are absent. Later canonical enrichment preserves artifact/preset IDs.

Independent assets, catalog/reference, side-icon, Abyss and JSON-projection
jobs run after core commit with bounded concurrency. Receipts and job states
allow recovery without repeating observations or overwriting user gear.
A failed optional job cannot turn a committed account into a failed import.
New references are an ordinary readiness state. Active unresolved set bonuses
make affected calculations incomplete instead of silently contributing zero.

The independent patch is checked on an isolated `master` baseline; dated test
receipts below distinguish controlled fixtures from the user's successful core
import. A later timing audit found eight optional Abyss icon HTTP-403 failures
that the old receipt had incorrectly marked complete; partial icon failures now
remain recoverable. The first-run equipment default is ON with saved choices
preserved. The loader counts actual parallel work, and HP/icon requests overlap
within the existing request bound. The [icon-recovery checkpoint](ABYSS_ENEMY_DATA.md)
records the later Nanoka and ordinary-browser repair of all eight cached icons,
including its initial partial failure and bounded retry behavior. A native UI check showed the enabled default;
that window was subsequently closed. Real loader review, a repeated live import
and main-branch integration remain pending. The later user instruction to finish
synchronization authorizes the local source commit and orchestrator-owned
transfer while physical acceptance remains open; push remains unauthorized.
Existing History/optimizer and policy edits are outside this package; required
import-identity/defaults/path seams are listed in the
[transfer inventory](WORKER5_TRANSFER_PACKAGE.md).
The follow-up [saved-account scope](ACCOUNT_PROFILES.md) adds isolated account
roots, game metadata and complete reset; its acceptance is tracked separately.
<!-- /handoff-current -->

### Worker3 UI handoff adaptation (2026-10-04)

The frozen packet in
`C:/Users/user/Documents/Codex/2026-10-03/worker3-gtt/outputs/worker5-import-ui-handoff/`
was reviewed against the current saved-account contract. The mini-set tooltip
freshness/read-only lookup and Fact DPS local-file URI fixes are adapted; their
owners are [artifact descriptions](ARTIFACT_BROWSER.md) and
[Abyss images](ABYSS_ENEMY_DATA.md). The earlier combined-button automatic-login
continuation was not installed. Login remains separate, its overlay now shares
the explicit import instruction, and action handlers reject overlap with an
open login. [Profile acceptance](ACCOUNT_PROFILES.md) records the combined check.

Manual smoke after restarting Worker5: close Login and verify no import starts;
press Import explicitly; hover the right character panel's set icon after its
catalog is ready; hover Fact DPS and inspect the available cached enemy icons.
These visible steps remain user-owned. No Computer Use, app restart or real
import was run for this adaptation; it does not resolve remote Cloudflare checks.

### Historical optimization checkpoint (2026-09-27; low-rarity followup 2026-10-03)

Normal import gets one unambiguous Genshin role and its character
list through the authenticated request context, then reads detail and Abyss
period for that role without repeating role lookup. Multi-role/API failures
retain the browser-selected list path. Direct list uses the observed public
element/rarity URLs; a live comparison found the same 78 portraits and shared
layers as the browser card path. Missing portrait/weapon/layer files are
downloaded once; browser, PvP and expanded-History variants render locally.
`--images-only` remains the forced refresh of image columns and manifest.
2026-10-03 focused fix: numeric and string rarities 1/2 are both excluded before
weapon download jobs are built. A mocked-downloader regression verifies that
their URLs are never requested; no new live import is claimed.
HoYoWiki artifact lists are reused per language and for six hours on disk;
an unknown set mapping forces one network refresh and retry. Trait membership
also uses its recent cache. The same Abyss period reuses source composition
and retries only missing icons; the Fandom icon request now supplies its site
referer, clearing prior 403 failures on successful retry.

Live full CLI import: 75.42s before this optimization with broken Abyss icon
cache; 34.43s after catalog/source repair with cold list caches and icon retry;
9.85s on a hot cache (8.19s inside Python). A later request stalled for the
old 30s API timeout and fell back successfully at 42.21s total; the fast path
now has a 6s request bound and a repeat completed in 10.71s. Last run: 78
cards, 57 unique weapons, zero image downloads/renders, 250 existing artifacts,
zero inserted. SQLite integrity/foreign keys passed; saved builds, targets,
slots and artifact equipment matched the verified pre-change backup. Weapon
equipment also matched at the 9.85s checkpoint; one row later changed from
`hoyolab_import` to `manual` while parallel work was active, so final weapon
equipment is not byte-identical to that backup. These timings include different
network/cache states. Focused backend tests and direct authenticated API
probes passed. The earlier
visible Settings image-only run and PvP display check covered the image layer
change; this optimization was verified through the production CLI, not a new
visible UI run.

Scope: Settings `AccountDataPage.run_hoyolab_export` -> QProcess ->
`hoyolab_export.run_import` -> import pipeline/exporter.

## Entry Point And Import Contract

Production entrypoint: `python -m hoyolab_export.run_import`. The UI supplies a
stable attempt UUID and consumes progress plus a committed receipt marker.
`--resume-attempt` repairs a saved attempt; it never reapplies an already
committed equipment snapshot. `--images-only` refreshes this database's saved
image sources without acquiring another account.

1. Capture UID/server and requested character IDs once. Ambiguous roles use
   the browser's selected request; missing identity is rejected. An already
   bound database rejects another role before source staging.
2. Validate complete inventory/detail structure, keeping localized account
   content separate from the EN mapping source. Prepare schemas before any
   account transaction.
3. Stage the exact safe source in `hoyolab_import_attempts`. Legacy unbound
   account data needs explicit one-time identity confirmation; it is not
   silently assigned to the first returned role.
4. Publish artifacts, character/talent/weapon observations, optional equipment,
   binding, immutable receipt and pending jobs in one SQLite transaction.
   Initialization, network, JSON and image writes do not run inside it.
5. Refresh independent projections, images, references and Abyss data.
   Completed source/receipt is authoritative; files are replaceable projections.
   Reference enrichment updates existing IDs and derived fields, never source
   observations, inventory counts or user equipment.

HoYoLAB set IDs and HoYoWiki entry IDs remain distinct. Unmapped artifacts
retain their source set ID, name and properties, with a source-content
fingerprint independent of canonical names. Identical copies require distinct
simultaneous source wearers; ordering, translation and later mapping do not
create new IDs. Unknown active set bonuses make selected calculations partial
and block affected GCSIM preparation; a single unknown piece still has raw stats.
Canonical collisions between source-less/scanner records and HoYoLAB records
retain all IDs and presets. Without distinct simultaneous source observations,
the optimizer excludes that ambiguous group and team preparation rejects
allocating two aliases together. Manual equipment is not copy-count evidence.

The first-run equipment switch defaults ON; saved OFF/ON choices are preserved.
CLI/backend calls still require explicit equipment opt-in. Enabled imports compare the assignment revision
captured before acquisition; concurrent edits are preserved. Missing
observations never clear canonical equipment or presets. A core write failure
rolls back the unit and leaves staged source available for retry. Older pending
sources cannot overwrite a newer committed snapshot.

Public catalogs reuse valid local caches and fetch missing entries with bounded
worker pools. Incomplete catalog entries remain queued for targeted retry.
An EN detail batch is requested only when source mappings need it. Images use
bounded asynchronous downloads/renders, transient retries, validated cache
reuse and per-file atomic replacement. Numeric/string 1/2-star weapons are
filtered before download jobs. Missing shared layers do not hide usable raw
portraits/icons. Abyss period still comes from authoritative remote sources,
with the existing fallback chain and same-period cache reuse.

The loader reads structured, attempt-bound progress for each concurrent job:
actual download/render counts, catalog phases and Abyss source/HP/icon work.
The bar aggregates completed work, not a prediction of remaining seconds;
wall-clock time is displayed separately and never advances the work bar.
Independent Abyss phases retain both counters when they overlap. Pending
recovery is a distinct terminal job state. Core acquisition uses only the first
20% of the bar, leaving the remaining range for enrichment and process exit.
PNG validation and image publication run in cancellation-drained workers,
so they do not block the asynchronous request loop or outlive staging cleanup.
Asset receipts include download/render/cache counters and phase durations.

`import_store.py` owns at most ten committed receipts and ten pending attempts;
pending TTL is 30 days, with the newest retained within the row cap. Staging and
commit invoke pruning. Sign-out/profile reset deletes the containing DB.
Import asset staging is cleaned on exit; the next import removes only owned
abandoned directories older than 24 hours, without following linked roots.
Logs use two replaceable debug JSON files, exclude credentials/private HTTP
diagnostics, and cannot determine success. Catalog retry rows are bounded by
the validated current catalog list.

Offline profile export derives account JSON from the exact SQLite backup it
archives, so failed projection writes cannot export mismatched account state.
Runtime account reads continue through SQLite adapters.

## Navigation And Legacy Manual Export

The points below preserve the failure contract for the separate manual exporter.
Normal account import stops after `character/list` and does not invoke the share
popover, canvas capture, layout collection or screenshot cropper.

- `DOMContentLoaded` may describe an intermediate redirect document. Startup
  popup JavaScript previously ran outside the readiness guard and could fail
  with `Page.evaluate: Execution context was destroyed`.
- Readiness checks visible login before popup dismissal and the character
  button afterwards. Only document-loss errors during preparation are retried,
  with at most three failed attempts inside the existing overall deadline.
- Obsolete input-blocker cleanup no longer evaluates JavaScript after clicks or
  export. It could replace the original failure with a navigation exception.
  Popup/browser cleanup failures retain the original operation error; failed
  browser acquisition owns cleanup of the process and Playwright driver.
- Character/share navigation waits for visible destination controls instead
  of the former fixed 2.5-second pauses. Existing image/download fallbacks remain
  bounded and are not whole-import retries.
- Live inspection on 2026-09-08 found the current image call `p()(e,r)` in
  `r_m_ys_all_*.js`. The old `f()(t,r)` match in a tarot/shared chunk still existed
  but was not called by account export. Both narrowly observed sites now reuse
  the same root/clone/canvas capture helper; do not patch arbitrary vendor JS.
- In the legacy manual exporter, a downloaded image alone is insufficient:
  empty root-discovery metadata or zero generated cards is a failure.
- Follow-up regression: a stray `break` after reopening the share popover
  skipped the second/third export click. A failing deterministic fixture
  reproduced this; the bounded retry now really performs up to three clicks.
- A page close/crash or browser disconnect wakes the download wait immediately.
  Canvas fallback must not swallow closure and turn it into a later
  `Page.wait_for_timeout: Target ... has been closed` failure. Event listeners
  and futures are removed on exit. Debug popup inspection is opt-in.
- Failure diagnostics record stage, page-closed state, error type and
  lifecycle events BEFORE intentional cleanup in `debug/hoyolab/import_failure.json`.
  They omit exception text, URLs, cookies/tokens, headers and response bodies;
  diagnostic failures cannot replace the original error.

## Process And Visible UI

- Actual user launcher: PyCharm Run Current File `ui/app_shell_smoke.py`, with
  project `.venv/Scripts/python.exe`. Its Account button starts a fresh
  `-m hoyolab_export.run_import` process with project-root working directory.
  UI module edits require restarting AppShell; exporter code is loaded afresh
  by the subprocess. Do not attribute browser closure to Codex limits without
  evidence. The historical screenshot alone does not identify who closed it.
- The entrypoint holds an OS file lock outside the cleared debug directory,
  rejecting concurrent imports before browser/data work. Process exit releases
  the lock; the persistent lock file is not a stale-lock indicator.
- Busy state is checked before authorization. The update/profile controls
  are disabled during import; profile import/export also guard their handlers.
  Completion acts only on its own process; duplicate/stale signals are ignored.
  Failed start, failure and crash close the loader and allow retry after cleanup.
- Follow `CODEX.md` Operating Rules for all bug fixes: visible user launch and
  actual controls on the user's computer are mandatory, with updated code loaded.
  Offscreen widgets/direct handlers do not replace that final verification.

## Responses And Data

Inventory capture is installed before navigation, validates HTTP/retcode and a
non-empty list, bounds response-body reading and removes its listener on every
exit. Browser JSON fetch has a 60-second bound and browser-side abort; the direct
request shortcut has a six-second bound before its page fallback.

`[IMPORT_COMMITTED]` is emitted only after the atomic receipt is stored. The
UI refreshes account data then and after optional jobs finish, and also reads
the receipt on process exit. A subprocess crash after commit therefore cannot
report that the whole account was lost. Incremental UTF-8 decoding preserves
split progress/receipt records; stale/duplicate process signals are ignored.
Optional missing references do not show a skipped-set warning.

The OS-owned import lock covers acquisition, publication and derived jobs.
No arbitrary cooldown remains after process exit. Background threads finish
before their staging directories are removed. A saved-source recovery does
not require authorization unless an optional authenticated mapping request is
still needed; cached/public enrichment can proceed offline from the session.

## Verification

### Full pipeline repair (2026-10-04, Worker5; acceptance pending)

The final backend/CLI/Qt regression suite ran 264 tests successfully on an
isolated checkout based on `master` (`bde62f9`), with one fixture-declared skip.
This independent patch includes the earlier hotfix and pre-download rarity
gate, excludes History/optimizer UI and policy changes, and remains uncommitted.
The account-page palette import was adapted to the master baseline. Coverage
includes cold import without catalogs,
unmapped source retention, transactional faults, saved-source recovery, account
binding, concurrent equipment edits, immutable receipt replay, per-file image
failure, bounded downloads/catalog workers, profile projection consistency,
mixed scanner/source copy ambiguity and process-crash UI recovery. All test
accounts, network responses and SQLite databases were isolated fixtures.
Late audit regressions cover repeated cancellation with active/queued writers,
incomplete forced catalog refresh, numeric zero properties and recovery options
after another role was staged before first binding. Handoff structure,
Python compilation, locale JSON and diff checks pass.

The initial native window activation failed while the game was foreground;
Account input reported `coordinate input geometry is unavailable`. A later
user-requested AppShell launch and manual import succeeded, as recorded below.
No new repair commit, master integration or push exists. No live profile export,
backup, cookie inspection or automatic import was run.

### First full live import after repair (2026-10-04, Worker5)

The user launched import through the updated visible Worker5 AppShell. Its
production import process started at 02:47:04 Moscow time. Pipeline elapsed
time was 53.656s; core publication finished at 10.172s. Post-commit jobs overlap:
assets 40.172s, references 21.750s, side icons 21.172s, Abyss 42.250s and JSON
projections 1.063s. These are pipeline/job durations, not click-to-exit timing or
a controlled cold/hot comparison with older runs.

The receipt has 73 characters, 467 talent rows, 51 observed weapon stacks and
233 newly inserted artifacts. Change Equipment was OFF. All five enrichment
jobs were recorded complete, with no pending jobs or record errors. A subsequent
audit found eight failed Fandom enemy icons (HTTP 403) inside the Abyss result:
the old completion status did not represent full icon readiness. The updated
wrapper preserves this as pending recovery and retries icons from same-period
cached source without repeating composition/HP requests. After enrichment no
HoYoLAB artifact set remained unmapped. The two core observation warnings only
record the established limits of weapon source identity/full-inventory coverage.

Read-only verification: SQLite integrity `ok`, zero foreign-key violations,
374 manifest image files decoded successfully, all 114 raw character/weapon
sources had transparency, no asset errors and no 1/2-star weapon manifest
entries. The importer exited, the loading dialog closed, and the actual
AppShell screenshot showed the user browsing History with imported icons.
The application remains open for their visual review. A repeated live import
and explicit final review remain pending; no preset/equipment preservation
against a private backup is claimed.

### Loader/default/throughput review (2026-10-04, Worker5)

The user requested first-run equipment ON, truthful loader stages and further
speed investigation. Missing settings now default ON; explicit saved False/True
and CLI opt-in behavior are unchanged. Structured progress includes each job's
phase/counters, concurrent HP/icon steps and elapsed time. No timer invents work.
All loader labels, including the previously missing save/enrichment headings,
are present in RU/EN/PT-BR. PNG validation and final asset publication execute in
bounded, cancellation-drained workers; repeated cancellation cannot remove live
staging. Download receipts now separate byte/request-read totals from
download/render wall time and cache hits. Request-read totals overlap and must
not be added to elapsed import time.

Existing-run attribution: Abyss source reports took 16.764s (Nanoka index,
manifest and detail were dependent requests: 5.934s, 5.547s and 5.255s); HP
fallback took 16.461s for eight page requests; icon work took 5.882s and failed
with HTTP 403. HP and icons now share one existing bounded network executor and
run concurrently after source joining. These changes have no measured live
speedup yet; 53.656s is a prior observation, not a proven lower bound. A cached
repeat must be reported separately from a first import.

Worker5 AppShell was launched using the shared read-only interpreter and
`python -m ui.app_shell_smoke`, then the real Account tab was clicked. Native
capture confirms the switch is ON and Update is available. No import was
automatically started. Loader animation during a real repeated import and the
new end-to-end timing remain pending. No commit or push was made.

The isolated portable candidate on `master` baseline `bde62f9` ran 337 tests:
336 passed, one declared Windows symlink skip, no failures/errors. The suite
covers default/saved equipment choices, all locale keys, malformed/foreign
progress, overlapping phase counters, no time-driven bar advancement,
cancellation-drained publication, bounded HP/icon overlap and icon-only retry.
One bounded public-image diagnostic reproduced HTTP 403 with the downloader's
current headers; no supported alternate URL was present in cached source
metadata. No URL guessing, account import or account/auth writes were performed
by that diagnostic. The external icon availability remains unresolved.

### Hotfix receipt (2026-10-04, Worker5)

The user's Settings import failed on `2150451 / Celestial Gift`: a seeded
catalog closed its connection inside the transaction context; seeding also
returned before the requested network refresh. Strict unresolved-set mapping
then aborted the entire import. The measured click-to-process completion was
100.7s (pipeline 98.9s), including 31.4s for image download/render and 54.6s for
static catalog refresh. The subsequent five-second UI cooldown is excluded.
Temporary measurement instrumentation was restored to checkpoint `4ee99d27`
before this fix; no measurement timers, exports or profile cleanup are part of it.

Fix verification: 100 backend/CLI checks across catalog, import reliability,
pipeline, storage and equipment passed; nine isolated Qt lifecycle checks passed.
Fixtures cover seed closure plus network continuation, strict versus tolerant
mapping, known artifacts alongside an unresolved set, raw-source retention,
artifact/equipment rollback, preserved presets and both equipment-switch modes,
reference/refresh failure recovery, structured CLI warnings and buffered Qt
completion. Network is mocked and SQLite writes use temporary fixture databases.
The independent patch applies cleanly to local `master`; no transfer to master
or new fixed live import is claimed. Next evidence is the user's manual Settings
retry with that version running. This receipt describes the earlier hotfix;
the current atomic publication/recovery contract supersedes its partial-write
behavior and unresolved-set warning path.

Tests are isolated from the real login profile/runtime DB. Relevant modules:

- `tests/hoyolab_export/account/test_export_navigation.py`
- `tests/hoyolab_export/account/test_export_download.py`
- `tests/hoyolab_export/account/test_import_run_lock.py`
- `tests/hoyolab_export/account/test_import_reliability.py`
- `tests/hoyolab_export/account/test_import_pipeline.py`
- `tests/hoyolab_export/account/test_asset_layers.py`
- account storage/equipment tests in the same directory
- `tests/ui/right_panel/test_hoyolab_import_lifecycle.py`

Coverage includes document loss, retry limits, visible login precedence,
cleanup masking, timeout/invalid/partial responses, early failure, partial
crop failure, artifact transaction failure, restart, repeated import dedupe,
stable preset/equipment references, JSON serialization failure, Qt start
failure/crash/success and button recovery, stale signals,
profile guards, real OS lock contention/release, download re-click/three-click
limit and a real asyncio wait interrupted by a simulated page crash.

The historical September audit used SQLite's backup API while excluding DB
writers, plus copied account assets and static/Abyss caches verified by hashes
and integrity checks. Its private backups are under
`exports/hoyolab_before_import_*`. The current user explicitly excluded profile
export/backup from this repair workflow. Never copy just an active WAL-mode DB
file or include login cookies/tokens in diagnostics.

Validated on 2026-09-08 through the project `.venv`:

- 85 focused tests passed (the eight modules listed above); `git diff --check`
  passed. A real headless browser with controlled local responses reproduced
  document destruction during evaluation and recovered on preparation attempt 2.
- Live HoYoLAB uses the existing authorization profile. The first full run
  exposed the old false-success behavior: image width 752px and zero cards.
  It preserved old crops/presets/equipment, but was not a complete export.
- After fixing the observed current bundle, the real Settings button handler
  and QProcess path (in an offscreen Qt widget) completed with 79 cards, 79 OK
  matches, zero match warnings, and a 2000 x 15940 image. All 138 manifest crop
  references exist and none contain staging paths; six sample portraits were
  visually inspected. This was not a visual smoke of the already-running app.
- The repeated import saw 251 artifacts, inserted zero, and reused all 251.
  Runtime SQLite contains 588 artifact rows with zero duplicate fingerprint
  groups, integrity `ok`, and no foreign-key violations. All original artifact
  ids survived. Against the original snapshot, 28 presets, 140 slots, 98 targets,
  52 equipped-artifact rows and 23 equipped-weapon rows are unchanged.
- QProcess returned normal exit 0, the loader closed, the process reference
  cleared, one account refresh signal fired, and the update button was enabled
  after the normal cooldown. Authorization remained `logged_in`.
- The page still warned about 55 loading placeholders before capture; final
  matching passed. Seven account-storage warning categories remain (ascension
  catalog matching plus the known observed-weapon inventory/identity limits).
- Verified backups: `exports/hoyolab_before_import_20260908_010257` (original,
  707 copied files plus SQLite snapshot) and
  `exports/hoyolab_before_import_20260908_010932` (before corrected repeat,
  738 files plus SQLite snapshot). Their `backup_manifest.json` files contain
  hashes/check results. The live refresh also downloaded ten missing artifact
  set icons; these generated additions were retained.

Follow-up visible verification (same date; supersedes offscreen-only UI evidence):

- Created `exports/hoyolab_before_import_20260908_114925`: SQLite backup under
  writer exclusion plus 748 files, verified hashes, integrity and foreign keys.
- Used Computer Use to click PyCharm's Run Current File for `app_shell_smoke.py`,
  then the visible AppShell Account / Update HoYoLAB controls. Confirmed the
  actual process command used the project `.venv` and the production subprocess.
- Two full imports in the same AppShell process completed in 71.5s and 83.0s:
  79 cards/79 OK matches/zero match warnings each, 251 existing artifacts and
  zero inserted. Browser and loader closed; update/profile controls recovered.
- Held the OS import lock with a bounded local validation process, then clicked
  the visible update button. The real subprocess rejected it before browser or
  account work; the dialog displayed `Another HoYoLAB import is already running`.
  Closed that dialog, released the validation lock, and retried in the same app.
- That post-refusal import completed in 77.2s, again with 79 OK cards,
  251 existing/zero inserted artifacts and no account-storage sync error.
  All three full imports used the same visible AppShell process; no restart
  or direct handler call was needed between attempts. The final browser and
  import subprocess exited, loader/dialog closed, and update/profile recovered.
- Final export is 2000 x 15940; all 138 referenced crop files exist, decode as
  images and contain no staging paths. Visible character/weapon icons remain
  intact. Authorization remained logged in. Existing seven account-storage
  warning categories persist; they are not import execution failures.
- After the full runs and controlled refusal, SQLite integrity remained `ok`,
  with zero foreign-key errors/duplicate groups. All 588 old artifact ids,
  28 presets, 140 slots, 98 targets, 52 equipped-artifact rows and 23 equipped-
  weapon rows were preserved against the new backup.

Repeatable UI checklist: restart the actual PyCharm AppShell after UI edits;
Account -> Update; observe loader progress and closure, closed automation
browser, enabled update/profile controls and intact character/weapon images;
repeat in the same app and compare preset/equipment ids plus DB integrity.
For refusal/retry validation use a temporary import lock, never remove the
authorization profile or terminate an unrelated browser.

Single-card asset feasibility probe, 2026-09-26 (research evidence, not import
acceptance): `python -m tools.experiments.hoyolab_asset_probe` opened the saved
HoYoLAB session, captured the live character/list response, and downloaded one
character's portrait and weapon directly. Element and rarity-background URLs
were taken from the last local export layout; no whole-page image export,
account sync, or runtime asset write occurred. For Noelle, portrait and weapon
were separate transparent 256x256 PNGs, element 64x64, and both character and
weapon backgrounds used the same 188x188 rarity-4 PNG. The assembled preview
restored the visible portrait missing from the existing bad crop; its layout is
approximate, not pixel-exact. The final live run took 17.52s to have all five
assets ready, including 2.563s for sequential download/decode; the complete
script process took 19.46s. This does not isolate or predict the duration of a
full account import. The probe owns one fixed output of at most 11 files under
`debug/hoyolab/single_asset_probe` (1,113,828 bytes in this run), replacing
only its marked output on rerun; normal import clears that debug root. Source
downloads are bounded to 5MiB/4M pixels each, generated PNGs to 16MiB, and
the complete output to 100MiB.

## Limits

New stage timings distinguish durable account publication from optional jobs.
Each job records duration/status; the replaceable debug log records stage and
browser lifecycle boundaries without private URLs or response bodies. The
historical import timings above do not measure this new pipeline. The first
new live run is recorded above; a controlled cold/hot comparison is still
required. Character details are one batch; known
set mappings, fresh trait/list caches and same-period Abyss sources avoid
unnecessary requests.

- SQLite account publication is atomic. JSON/image publication remains
  individually replaceable; disk failure can leave those projections pending.
  Repair uses the committed source and does not revert user edits or repeat
  observations. The production CLI holds the import lock through acquisition,
  all jobs and thread shutdown; direct concurrent pipeline calls bypass that
  supported serialization contract.
- Source selectors and minified export call sites can change again. Empty
  exports now fail visibly instead of being reported as successful zero cards.
- The historical browser-closed screenshot was not independently reproduced
  during the three visible full imports. Who/what closed that browser remains
  unknown; the retry defect and masking behavior are covered by fault fixtures.
  These runs do not establish reliability under every network/browser failure.
- Image readiness warnings, account mapping warnings, and image quality need
  separate interpretation; a completed process is not proof of their absence.
- Identical artifacts normally reuse existing content matches. The later
  accepted exception creates another local copy only when the same snapshot
  proves simultaneous wearers; repeated imports reuse those copies.
