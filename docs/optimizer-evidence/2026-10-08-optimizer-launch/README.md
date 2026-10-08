# Optimizer child-process directory check — 2026-10-08

## Scope and current evidence

This is an independent Windows launch hotfix, not the uninstalled rotation
safeguard/engine package `13cb3f7`. The human authorized transferring only this
fix to main after its real-button gate passes, with an optimizer-consumer
rebuild; the selected GCSIM engine and its patch stack must not change.

The user's saved All Sets run stopped before formula capture: its existing seed
directory was 261 characters long. The selected engine executable existed and
matched the request's artifact hash. Windows limits a child process's current
directory separately from long-path file access; see Microsoft's
[SetCurrentDirectory documentation](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setcurrentdirectory).
The correction selects the nearest existing short ancestor for process `cwd`
only. Absolute input/output paths remain in the original run directory. No
global directory change, output relocation, account migration or gameplay
change is involved. Missing requested directories still fail explicitly.

Evidence, in order:

- Initial harness failure below: wrong Go module working directory, no tests.
- [Corrected native proof](attempt-02.md): raw long-directory launch fails;
  the chosen ancestor launches successfully and reads/writes deep files.
- [Adapter/wiring checks](python-gates-01.md): 29 focused checks pass.
- [Public fixture preparation](preparation-gate-01.md): both modes use their
  real input-preparation paths with 20 synthetic items and four legal actors.
- [Native/Python follow-up](gate-02.md): 10 checks pass, including missing-cwd
  rejection and the actual AppShell button-unlocking callback.
- [First real-button attempt](button-gate-01.json): Selected fast succeeded,
  then the test harness's abbreviated cleanup left buttons disabled. The failed
  receipt is retained unchanged. Its zero-call counter missed Python compact
  captures and must not be interpreted as an actual zero-GCSIM claim.
- [Corrected real-button gate](button-gate-02.json): all four modes pass,
  10/10 actual engine calls (eight compact captures and two ordinary n=500
  simulations); the temporary native build contains only main's code plus the
  cwd fix. Installed main sources, consumer, engine and caches are unchanged;
  the managed job is removed. These observations were reviewed for the public
  golden, not silently accepted from a changed live account.
- [Strict numerical regression](button-gate-03.json): all four modes match
  the reviewed golden, 10/10 engine calls; main/runtime unchanged and scratch
  cleaned. Eight baseline and two supervisor tests pass.
- [Timing calibration](button-gate-04.json): numerical golden remains strict;
  all four modes pass, 10/10 engine calls, 13 offline checks. Click-to-ready
  times are 5.875s Selected fast, 16.391s All Sets fast, 7.672s Selected verified
  and 18.797s All Sets verified. These were manually added as runtime references;
  this run did not yet enforce a timing golden. Installation must repeat the
  gate with both numerical and timing assertions enabled.

The reusable real-button test clicks actual offscreen QPushButtons and uses
the AppShell launch/finish handlers, QThread worker, production preparation,
native consumer and selected installed engine, without process/result mocks.
It checks Selected/All Sets in fast and verified modes, legal physical IDs,
deep paths and build cards. Candidate observations are reviewed before a golden
fixture is saved. Formula DPS must match that reviewed baseline; ordinary DPS
is compared using both runs' sampling error, not against formula DPS. Increases
also require review rather than automatic replacement. Physical app-window
interaction and the user's account-wide search remain distinct acceptance gates.

The human's added performance rule is per-case reference plus 5 seconds. A
larger observed time is a recheck request, not proof of a code regression:
confirm that the computer is idle and repeat only that case. Do not silently
refresh the reference or rerun the whole matrix. Numerical checks happen first
so a slower run cannot hide a DPS failure. These tiny public-fixture references
are not a Chasca full-account performance promise. The historical ~90s Chasca
measurement used fast 7x7 research search, not a verified 3x2 app session; see
[the existing research receipt](../2026-09-27-search-hypotheses/README.md).

## Repeating the regression gate

After building/installing the reviewed native consumer in the calling checkout,
run that checkout's Python environment with:

```text
python -B tools/check_optimizer_buttons.py
```

The runner uses the same configured native consumer and selected engine store
as AppShell. Explicit read-only `--optimizer-binary` and `--engine-store` paths
are available for disposable pre-install verification. It owns temporary
profiles/settings/cache/DB/runs and cleans on exit. It enforces the baseline;
an inherited candidate-recording flag cannot bypass verification. Regular cheap
test discovery deliberately skips real GCSIM calls; a skipped gate is not
launch acceptance. Numerical baseline changes need reviewed evidence and an
explicit fixture edit. The dated experiment runner pins the original clean
main sources and records each attempt immutably; it is not the normal installed
regression command.

After an idle confirmation, an isolated performance recheck is, for example:

```text
python -B tools/check_optimizer_buttons.py --case all_sets_fast
```

## Source-stage closeout and authorized transfer

The isolated source stage preserves main's source/runtime identities through
all gates above. Handoff checks have only the same 11 inherited missing external
hub/router errors in this detached checkout; the real shared hub was read
explicitly, not recreated. Main's coordinator owns target hookup acceptance.

Git intent: save only this verified launch fix, its public regression fixture,
timing policy, tests and evidence as one independent local commit whose parent
is `13cb3f71484c0c379b8b9e50f8854caac1ef0e4a`. Local commit permission is the
standing Git policy. The human separately authorized the coordinator to
cherry-pick this commit onto clean main `1d5e86945c573da22a3a261bb2d8ae7d8081220e`
and rebuild the optimizer consumer. Parent `13cb3f7`, engine0010, profile/startup
drafts, other branches and push are excluded. Integration is not yet claimed.
The target must repeat `check_optimizer_buttons.py` with the installed consumer,
both DPS and timing checks enabled, and update its own receipt/current owner.

## Original failed harness receipt (unchanged)

One managed offline attempt exited 1 before Go package compilation. The exact
requested test command was issued:

```text
go test ./internal/engineclient -run 'TestWindowsCurrentDirectoryUnits|TestChildProcessDirectory' -count=1
```

Go reported:

```text
go: go.mod file not found in current directory or any parent directory; see 'go help modules'
```

Result: 0 tests executed; no test binary was built or child process launched.
The managed runner starts commands from the repository root, while the Go
module is `native/gcsim_optimizer/go.mod`. The raw long-current-directory failure
and corrected-ancestor success were not exercised. No retry was made.

## Scope and cleanup

`GOPROXY=off`, `GOSUMDB=off`, `GOWORK=off`, and `GOTOOLCHAIN=local` were set;
Go build, module, and temporary paths were scoped to the managed job. No GCSIM
calls or builds, app launch, database access, or network access occurred.

The detached checkout had no active-engine pointer before or after the attempt.
Managed job `.codex_tmp/managed-optimizer/job-y66l4ovn` was removed; cleanup
reported 0 generated bytes, the path is absent, and no `job-*` directories
remain. The managed root retains only its pre-existing 1-byte lease file.
