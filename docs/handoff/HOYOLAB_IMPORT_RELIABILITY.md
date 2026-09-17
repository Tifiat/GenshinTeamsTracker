# HoYoLAB Import Failure Boundaries

Scope: Settings `AccountDataPage.run_hoyolab_export` -> QProcess ->
`hoyolab_export.run_import` -> import pipeline/exporter. This is a bounded
repair/audit of the existing path, not a new importer or a full reliability claim.

## Entry Point And Import Contract

Production import entrypoint: `python -m hoyolab_export.run_import`.
The UI starts it through QProcess and consumes `[STATUS]` progress lines.
Account runtime reads go through SQLite adapters; JSON/crop manifests are source
inputs. Extraction is DOM/layout/coordinate based, not image matching.

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

## Navigation And Export

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
- A downloaded image alone is insufficient: empty root-discovery metadata or
  zero generated cards is a failure before account writes.
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
- Crops are built in a temporary mirror of project-relative asset paths, seeded
  with existing crops. A partial crop failure cannot overwrite old images.
- Account language/period publication happens after artifact import. Account
  JSON is replaced per file; staged image files replace their final paths.
- Artifact import retains content-fingerprint dedupe and SQLite transaction
  rollback, and explicitly closes its connection on success/failure.
- User-managed equipment and saved presets remain separate from HoYoLAB
  observed equipment. Default OFF preserves user equipment; the later explicit
  "Change equipment" switch applies a fresh snapshot only after account sync.
  Saved presets are never changed. See `ACCOUNT_EQUIPMENT_STATE_DESIGN.md`.
- Existing account SQLite sync warnings remain non-fatal after raw publication,
  as documented in `ACCOUNT_SQLITE_STORAGE.md`.

## Verification And Backup

Tests are isolated from the real login profile/runtime DB. Relevant modules:

- `tests/hoyolab_export/account/test_export_navigation.py`
- `tests/hoyolab_export/account/test_export_download.py`
- `tests/hoyolab_export/account/test_import_run_lock.py`
- `tests/hoyolab_export/account/test_import_reliability.py`
- `tests/hoyolab_export/account/test_import_pipeline.py`
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

## Limits

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
