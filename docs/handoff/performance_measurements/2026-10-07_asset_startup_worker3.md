# AppShell asset-read startup reduction — Worker3, 7 October 2026

Owner: Worker3 startup execution chat. Base product:
`77c26458d3a0beda3f88fc4cda1b129053dad081`, branch `worker3`.
This is synthetic offscreen evidence, not populated-main or PyCharm click acceptance.

## Change and scope

`ui/character_assets.py` now reads equipped weapons once per inventory load and
groups their owners, preserving the service's character-ID ordering. Previously,
every stack repeated the owner query and equipment schema checks. The targeted
first A/B removed 76 of 77 repetitions but saved only about 10 ms (425.3 to
415.4 ms); total readiness did not improve in that pair. This justified checking
the remaining asset/path work rather than claiming a startup fix from query counts.

`hoyolab_export/asset_paths.py` now offers a synchronous lookup batch used by the
two account asset-list adapters. Within one call it reuses the manifest stat,
resolved paths and already checked existing/missing manifest assets. `finally`
releases the batch, including on exceptions; nested calls reuse it and another
thread gets its own context. The next refresh rechecks files and the manifest.
Containment still uses resolved paths. This assumes the existing contract that
account import/profile changes complete before the synchronous UI asset read.

No loader, delayed first-click work, disk cache, image transform/quality change,
workspace construction change, startup scaling change, migration, optimizer,
runtime binary or launcher change. Profile switching still starts a new process.
The separately reported absolute-path adapter bypass is not fixed by this patch.
Worker5's History icon work is untouched. A bounded catalog review confirmed
that ordinary startup does not duplicate its heavy catalog parse; that subsystem
was left unchanged.

## Comparable measurement

Manual runner: `tools/experiments/appshell_weapon_startup_probe.py --pairs 3`,
using this checkout's `.venv/Scripts/python.exe` (Python 3.11.5, PySide6 6.11.0).
Every run physically stages the same tracked product/static inputs and creates
78 synthetic characters, 77 weapon stacks and 77 equipment assignments, with
155 generated 200x200 RGBA PNGs and their manifest. Only the two product modules
are swapped between the baseline Git content and the candidate. No account data
is copied or opened from main or from Worker3's live profile.

Entry is file execution of `ui/app_shell_smoke.py`, cwd `ui`, project root in
PYTHONPATH, followed by its normal supervised child. Qt is offscreen. Each run
uses a fresh process and physical snapshot, with project bytecode disabled;
the OS file cache is uncontrolled/warm, not flushed. The same detailed observer
and SQL trace operate on both sides. First ready means the initial queued Qt
tick after AppShell show, as in the earlier guarded probe, not a physical click
stopwatch. Guard overhead is included. Order: before/after, after/before,
before/after. Do not compare these values to an empty-profile probe or the
main populated-profile 14.2–14.4 s audit.

| Pair | Launch to ready before / after | Weapon assets before / after |
| --- | ---: | ---: |
| 1 | 9,816.9 / 8,329.1 ms | 1,094.5 / 626.6 ms |
| 2 (reverse order) | 8,448.0 / 9,123.2 ms | 1,056.0 / 585.5 ms |
| 3 | 8,963.5 / 7,420.9 ms | 1,086.0 / 567.0 ms |

Observed medians:

- Launcher to ready: **8,963.5 -> 8,329.1 ms**, 634.4 ms / 7.1% lower.
- Child to ready: **7,950.6 -> 7,346.9 ms**, 603.7 ms lower.
- AppShell construction: **3,433.4 -> 2,495.6 ms**, 937.8 ms lower.
- Weapon asset loading: **1,086.0 -> 585.5 ms**, 500.5 ms lower.
- Owner SELECTs and equipment schema passes: **77 -> 1** each.

Nested durations must not be added. Import noise remains substantial; ranges
overlap and the reverse pair's total launch was slower after the patch. The
targeted asset-stage reduction is consistent; the exact overall speedup is not
a promise. Raw primary evidence: [three pairs](2026-10-07_asset_startup_ab.json).

## Correctness and verification

A separate additional pair added asset-payload hashing and logical fixture DB
comparison to resolve the byte-fingerprint change reported during startup.
All table rows were unchanged before/after each launch. The byte-level DB/WAL
fingerprint changed, so byte preservation is not claimed. Normalized complete
character and weapon adapter payload hashes match between baseline and candidate:

- characters: `ecc95d2f284f0c69cb499791c1d5769049ec7320242a7feeba46a63e707cd0c2`;
- weapons: `93dc46e3a0ca617d03d7ae77997860637b28a42a1d1acc964c17ce2d12b86ea7`.

That pair measured character loading at 1,228.4 -> 510.6 ms and weapon loading
at 1,235.1 -> 736.3 ms. It uses extra instrumentation and is separate from the
primary three-pair summary: [parity evidence](2026-10-07_asset_startup_parity.json).

**32 distinct focused tests passed**, in two guarded disposable test processes
(20 + 16 executions, four repeated). Coverage: existing character/PvP/History
asset metadata, owner icons and swap refresh; five new batch regressions for
manifest stat reuse, exception/nesting/thread isolation, fresh files/manifest
and account containment, sorted/missing owners and filters; account-import
refresh signal semantics; nine startup-scaling checks. Receipts:
[asset tests](2026-10-07_asset_startup_tests.json),
[refresh/scaling tests](2026-10-07_asset_startup_refresh_tests.json).
The additional nested-snapshot guard check and observer compilation passed.
Read-only peer review found no product regression; its probe counter and test
coverage notes were addressed. Handoff checker and final diff checks are part
of closeout, not evidence of UI behavior.

## Cost, cleanup and remaining gate

The bounded investigation used 12 successful synthetic startups: two unchanged
controls, one pair for owner queries, three pairs for the full patch and one
extra parity pair. Total startup process wall time was 118.3 s; two focused test
processes took 17.1 s. One initial setup attempt stopped before the app because
the original guard rejected its nested disposable directory; the exact temporary
subtree exemption fixed it. No fourth attempt at an unresolved blocker occurred.
The largest measured launch snapshot was 28,344,981 bytes. Each was deleted by
the existing checked lifecycle; no `gtt-startup-*` directory remained. Only the
small permanent evidence receipts and reproducible manual runner are retained.

The fixture has **no active engine, artifacts, saved History or saved PvP decks**,
and uses synthetic art. The orchestrator should arrange a separate guarded
baseline/candidate comparison in main using an authorized disposable populated
profile copy. Physical PyCharm launch, actual profile restart/import and the
user's monitors remain unverified. No Computer Use, live DB read, account copy,
engine execution, peer write, cross-branch transfer or push occurred.

Transfer the two product modules, new regression file, manual runner, this
receipt and its four JSON evidence files, plus the performance-owner link.
No migration or runtime synchronization is required.
