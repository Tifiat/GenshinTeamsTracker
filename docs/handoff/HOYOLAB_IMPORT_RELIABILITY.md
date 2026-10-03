# HoYoLAB Import Failure Boundaries

<!-- handoff-current: hoyolab-import -->
2026-10-04. Independent catalog/partial-import hotfix prepared in Worker5.
Seeded SQLite catalogs close after transaction exit and still perform requested
network refresh. Missing canonical set mappings no longer abort the normal
account import: known artifacts, characters, weapons, raw details and prepared
images continue; unresolved artifacts are skipped without guessing identity.
Raw details retain the skipped records for a later import. An incomplete
artifact observation preserves prior observed and canonical equipment, even
with Change equipment ON; saved presets remain unchanged. Reference refresh,
artifact transaction, account sync and equipment failures produce structured
warnings in the import log/CLI and a localized completed-with-warnings dialog.
Primary inventory/detail validation and pre-publication image failures retain
their existing failure/preservation boundary.

Verification and the user's failed-import measurement are recorded below in
the 2026-10-04 receipt. Automated fixtures use temporary databases and mocked
network; the fixed path still needs the user's manual retry. This portable
fix has no History/timer/policy dependency and is not installed on master.
<!-- /handoff-current -->

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

Production import entrypoint: `python -m hoyolab_export.run_import`.
The UI starts it through QProcess and consumes `[STATUS]` progress lines.
Account runtime reads go through SQLite adapters; JSON/asset manifest are source
inputs. Normal images are composed from direct source files, not browser renders.

- HoYoLAB relic set IDs and HoYoWiki entry IDs are distinct. The EN detail
  service pass is mapping input only; never publish it as localized account data.
- Account content language and application UI language remain separate.
- Catalog detail refresh is explicit; normal account update does not fetch every
  HoYoWiki character/weapon detail. See `DATA_RUNTIME_BOUNDARIES.md`.
- Current Abyss period resolution uses HoYoLAB overview, then Fandom latest,
  then Nanoka live metadata. Local date is not source authority. Refresh failure
  is non-fatal and preserves existing caches.
- Sign-out/offline restore own destructive profile cleanup; ordinary early
  import failure must preserve existing account data/assets.

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
- Failure diagnostics record stage, page-closed state, browser exit code and
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
- Busy/cooldown is checked before authorization. The update/profile controls
  are disabled during import; profile import/export also guard their handlers.
  Completion acts only on its own process; duplicate/stale signals are ignored.
  Failed start, failure and crash close the loader and allow retry after cleanup.
- Follow `CODEX.md` Operating Rules for all bug fixes: visible user launch and
  actual controls on the user's computer are mandatory, with updated code loaded.
  Offscreen widgets/direct handlers do not replace that final verification.

## Responses And Data

- Inventory capture is installed before navigation, validates HTTP/retcode and
  a non-empty list, bounds response-body reading and removes its listener when
  complete/cancelled. Pipeline teardown consumes or cancels an unused future.
- Browser JSON fetch has a 60-second bound and browser-side abort. Roles/detail
  failures and missing requested character ids are rejected before account writes.
- Missing source layers and display variants are built in a temporary mirror
  before account writes. Existing v2 source files are reused on normal import;
  a failed download/render leaves the prior account images untouched.
- Account language/period publication happens after artifact import. Account
  JSON is replaced per file; staged image files replace their final paths.
- Artifact import retains content-fingerprint dedupe and SQLite transaction
  rollback, and explicitly closes its connection on success/failure.
- Strict artifact/mapping helper calls still reject unresolved sets by default.
  Normal import opts into partial mapping/conversion. Only a typed missing
  mapping skips a relic; other conversion errors roll back the artifact phase
  and warn while preserving the remaining account source import.
- User-managed equipment and saved presets remain separate from HoYoLAB
  observed equipment. Default OFF preserves user equipment; the later explicit
  "Change equipment" switch applies a fresh snapshot only after account sync.
  Saved presets are never changed. See `ACCOUNT_EQUIPMENT_STATE_DESIGN.md`.
- Existing account SQLite sync warnings remain non-fatal after raw publication,
  as documented in `ACCOUNT_SQLITE_STORAGE.md`.
- CLI `[IMPORT_WARNING]` JSON records persist in the existing import log. UI
  consumes complete or buffered final lines and shows one localized warning
  after refreshing account data; malformed/unknown records are ignored.

## Verification And Backup

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
retry with this version running. Primary API validation and final file-publication
limits below still apply.

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
failure/crash/success and button recovery after cooldown, stale signals,
profile guards, real OS lock contention/release, download re-click/three-click
limit and a real asyncio wait interrupted by a simulated page crash.

Before real updates, use SQLite's backup API while excluding DB writers,
copy account source/assets and affected static/Abyss caches, and verify file
hashes before/after copying plus snapshot integrity/foreign keys. Never copy
just an active WAL-mode DB file or include login cookies/tokens in diagnostics.
Private backups for this audit are under `exports/hoyolab_before_import_*`.

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

Remaining import-cost audit: the character/detail call is already one batch,
set mapping fetches an English batch only for unknown set IDs, and Abyss
source-data refresh has a same-period cache gate. The two HoYoWiki trait pages
are fetched unconditionally by normal import; this is the first independent
network/cache optimization candidate after stage timings show its cost. The
new `stageEvents` field in `debug/hoyolab/import_log.json` records future
normal-import boundaries without logging private URLs or response bodies.

- The complete DB + JSON + image publication is not a single transaction.
  Disk failure/process termination during final publication can still leave
  partial results; retain the verified backup. No whole-DB automatic rollback
  is added because it could overwrite concurrent user equipment/preset edits.
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
