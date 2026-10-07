# Accepted-copy audit and populated AppShell startup — 7 October 2026

Owner: Worker1. This is a read-only product audit of the user's PyCharm
`ui/app_shell_smoke.py` file entrypoint in the main checkout. Product code and
worker refs were not changed by the audit. The later documentation closeout is
separate from the application version verified here.

## Version and integration result

At measurement, main, Worker3 and Worker4 were clean at
`77c26458d3a0beda3f88fc4cda1b129053dad081`. Worker5 was clean at
`9f7e04bdc1c2c52d4588822def75ca525a092a22`, parents `bb68d1f` and `77c2645`.
There were no unmerged index entries, ongoing Git operations or conflict
markers in tracked Python/Go/JSON/QSS. The full committed Worker5 difference
from master was exactly its four documentation files: `AGENTS.md`, `CODEX.md`,
`HOYOLAB_IMPORT_RELIABILITY.md` and its 2026-10-04 reverse-sync receipt.

Physical source/config/asset checks covered 1,570 tracked candidates per accepted
copy, plus three large tracked optimizer fixture JSONs hashed without parsing.
Worker3/4/5 had 49/57/151 raw text byte differences respectively; all were
CRLF/LF differences, with no remaining normalized-content differences. The
three large JSONs and binary assets compared identically. No untracked or
ignored Python module was found under the accepted runtime package roots.

All four pointers selected active `gcsim-v2.45.0-20260927011932` and rollback
`gcsim-v2.45.0-20260926234622`. Their binary SHA256 identities were:

- active: `7df37b5224f655d271d9389686bf22445717e02e896df5e3aa22d1d698042f8c`;
- rollback: `e04b1e7e0dcdd6a9854b0538f5492d191d1f5170ce1923de096208441433725b`;
- current consumer: `76f8a52ca75146e320090775d02b61903e59dedaa74dc8f2cb006d662afa943c`.

Main and Worker3 installed dependency metadata agrees: Python 3.11.5,
PySide6/shiboken6 6.11.0, Pillow 12.2.0 and Playwright 1.59.0. Worker4/5 have
neither their own `.venv/pyvenv.cfg` nor `.idea` SDK configuration; their selected
launch interpreter and installed dependencies are unverified. The main
PyCharm SDK resolves `$USER_HOME$/Desktop/GenshinTeamsTracker/.venv/Scripts/python.exe`.

Worker2 remains the deliberately excluded Theory branch at `918b072`, three
commits ahead and twenty behind the audited master. Its committed tree differs
at 355 paths; its own working tree contains 25 tracked modifications and 24
nonprivate untracked entries. The audit did not move or clean that checkout.

## Populated startup method and result

The prior [6 October measurement](2026-10-06_guarded_startup_profile.md) used an
empty synthetic profile. It does not establish populated-account launch time.

This audit used three finite physical snapshots, the same main `.venv`, file
execution of `ui/app_shell_smoke.py`, working directory `ui`, and a PYTHONPATH
containing the snapshot's project root, matching the saved PyCharm route.
Qt was offscreen. The guard rejected source-private access, network and
unexpected Python/Qt processes. The source DB had no WAL at staging; it was
opened read-only/immutable and backed up into each disposable profile. Only
local display data was staged: DB, image/crop manifest, saved History/PvP and
state/preferences. Browser authentication, cookies and debug trees were not
copied. Absolute main-root references were rewritten only inside the copies.

The active engine's manifest and startup catalog inputs were copied, without
its executable or a numerical run. The populated copy contained 1,394 allowed
files totaling 124,438,924 bytes. The source inventory had 604 artifacts,
78 characters and 77 observed weapon stacks. DB quick_check was `ok`.
The source registry, DB and settings hashes were identical before/after.
All disposable roots were removed by the checked snapshot lifecycle.

| Observation | Child first-ready | Launcher to first-ready |
| --- | ---: | ---: |
| Empty profile plus engine catalogs, detailed | 7,964.9 ms | 8,789.5 ms |
| Populated profile copy, baseline observer | 13,531.9 ms | 14,375.4 ms |
| Populated profile copy, detailed observer | 13,381.5 ms | 14,161.5 ms |

All three runs exited normally with zero guard violations and no stderr
warnings. The detailed observer added function profiling; these numbers are
not interchangeable with the earlier lighter synthetic probe or an exact
PyCharm click stopwatch. Fresh copied source also had no project bytecode cache.

The populated detailed run measured `ui.app_shell` import at 3,584.6 ms and
`AppShell.__init__` at 8,261.2 ms. Included construction costs were:

- History construction/reload: 1,777.8/1,771.1 ms;
- PvP construction: 3,075.3 ms, including Decks at 2,902.0 ms;
- active artifact-set catalog: 853.1 ms;
- right dock construction: 408.7 ms;
- initial visible character/weapon grid update: 699.9 ms.

Image loading accumulated 1,241.9 ms across 362 calls. Function profiling
recorded 3,290 `Path.resolve` calls and 9,253 Windows stat calls; their nested
timings overlap and must not be added to the workspace durations. Profile
bootstrap was 59.6 ms and operation-lock acquisition 2.9 ms. A separate
read-only check against the actual main root found the legacy-migration decision
false in 6.2 ms, without a legacy-tree traversal.

The reported 10+ seconds is consistent with synchronous populated workspace,
catalog and image work before usable display. The main constructor builds
History and PvP even while the Character/Weapon workspace is selected. This
is a performance finding, not evidence of an unresolved merge conflict.
No before/after integration benchmark was performed, so causation by a specific
commit is not established. No loader, lazy workspace or persistent cache was
introduced. See the existing [performance owner](../PRELOADER_BACKLOG.md).

## Flashing window boundary

The Qt observer recorded one top-level AppShell show, followed by the probe's
normal close. It did not record a second startup Qt window. The existing actual
main process tree was read only and matched one supervisor plus one UI child,
each behind Windows virtualenv interpreter forwarding; only the UI child had a
main window. A minimal hidden-parent console probe did not reproduce a visible
console. This does not identify the user's brief flash: no native PyCharm
interaction, video or physical rendering observation was performed. Keep that
symptom open; do not label it fixed or claim a console cause as confirmed.

## Bounded regressions and findings

Thirty-four existing tests passed in a disposable code/test snapshot with zero
network/process/source-private violations: transparent History pipeline (4),
character asset adapters (13), PvP profile integration (5), profile supervisor
and bootstrap (11), and SQLite handle lifecycle (1). These are seam checks,
not full authenticated multi-account, physical UI or numerical acceptance.

Two integration gaps remain at the audited product pin:

1. `ui/character_assets.py:156` only normalizes relative asset paths. Existing
   absolute paths bypass `account_asset_path`, which rejects another managed
   profile and remaps migrated legacy account paths. The same conditional
   normalization appears in the Artifact Browser resolver and weapon-layer
   matching. A synthetic foreign-profile file confirmed that the common
   resolver rejects it while the adapter still accepts the existing file.
   The old absolute branch predates profiles; the profile integration did not
   route that branch through the new guard. No actual foreign account was read.
2. Artifact target-preview icons/strips use shared project
   `data/cache/ui/target_preview_*` directories. Cache writes contain
   account-derived images; profile deletion/reset removes profile roots but
   has no corresponding shared-preview cleaner or finite cache retention.
   Cache keys include image identity, so a cross-profile key collision was not
   demonstrated. This is a lifecycle gap, not a demonstrated account data loss.

The audit implemented neither fix and changed no product behavior. It also did
not claim that the 34 passing existing tests cover the newly reproduced
absolute-path omission. Focused synthetic remap/foreign-root/external-package
regressions should accompany a future authorized fix.
