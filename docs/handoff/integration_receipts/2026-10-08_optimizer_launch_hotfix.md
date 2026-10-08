# Windows optimizer launch hotfix on main — 2026-10-08

The human authorized the independent launch fix only. Clean `master`
`1d5e86945c573da22a3a261bb2d8ae7d8081220e` cherry-picked source
`a7f70c1bdae98136d1b7ac6b0aa2974231e0eea4` as
`d965932afe769bd5adeb10c71673cdfaa627c499` (`-x`). The source parent
`13cb3f71484c0c379b8b9e50f8854caac1ef0e4a` was not transferred. The
28-path delta changes child-process working directories for two Go and three
Python launches, provides public path/button regression checks, and adds only
a runtime-path test seam to AppShell. Git auto-merged the checkpoint by adding
the source receipt link above its preserved current status.

The native consumer was rebuilt from this target's Go source in one managed
scratch job. Its new installed path is
`native/gcsim_optimizer/gtt-optimizer.exe`, SHA-256
`dd84139e21ea24af5a08c0e0ba4eb4ce8410459f31dfdb8513bd77045fed4f13`.
The prior SHA-256
`76f8a52ca75146e320090775d02b61903e59dedaa74dc8f2cb006d662afa943c`
is retained as `gtt-optimizer.exe.runtime-sync.rollback` beside it, with
the existing runtime-bundle rollback receipt. Candidate compatibility passed
for both selected and rollback engines before promotion. Build scratch removed
77,389,464 bytes; no managed job remains.

The active engine remains `gcsim-v2.45.0-20260927011932`, rollback remains
`gcsim-v2.45.0-20260926234622`. The active pointer SHA-256 before and after is
`388e28fe2c88122be8690d46fcb603d4228c0f3307d1f1110c1e39f6293f8efb`;
active artifact SHA-256 is
`7df37b5224f655d271d9389686bf22445717e02e896df5e3aa22d1d698042f8c`.
No engine or patch-stack installation occurred.

The installed default-path `.venv/Scripts/python.exe -B tools/check_optimizer_buttons.py`
passed one serial real-backend gate: offscreen AppShell buttons, production
preparation and QThread, selected native consumer and active GCSIM engine. Its
20-item/four-actor public fixture preserved reviewed formula DPS and verified
simulator DPS within the prescribed sampling error. Actual click-to-ready
times versus reference and reference+5s limit were:

| Case | Actual | Reference | Limit |
| --- | ---: | ---: | ---: |
| Selected fast | 5.953s | 5.875s | 10.875s |
| All Sets fast | 16.985s | 16.391s | 21.391s |
| Selected verified | 8.125s | 7.672s | 12.672s |
| All Sets verified | 18.469s | 18.797s | 23.797s |

The installed gate output retained these actual DPS values. The reviewed
references are from the fixed public baseline; formula values matched exactly,
and verified simulations passed the baseline's sampling-error comparison:

| Case | Actual formula / reference | Actual simulated / reference DPS |
| --- | ---: | ---: |
| Selected fast | 1644.8658064907572 / 1644.8658064907572 | not run |
| All Sets fast | 1644.865806490757 / 1644.865806490757 | not run |
| Selected verified | 1644.8658064907572 / 1644.8658064907572 | 1633.4338284571852 / 1639.999482048844 |
| All Sets verified | 1644.865806490757 / 1644.865806490757 | 1640.9431042767897 / 1641.3616219238577 |

The gate made eight compact and two ordinary real-engine calls; both harness
tests passed. Its isolated DB, settings, cache and run job was removed
(3,560,572 bytes). The user's profiles were outside the runner's owned paths.
Focused checks also passed: five native launch tests and 18 Python path,
harness, supervisor and baseline tests. Prior source failures and source gates
01–04 remain unchanged in the [source record](../../optimizer-evidence/2026-10-08-optimizer-launch/README.md).

This is launch and small-fixture regression acceptance only. Physical window
clicks, full-account Chasca timing, general model response, Theory and the
untransferred safeguard remain open. The old 91.355-second Chasca research run
used a different 7×7 search and does not compare to this 1-group × 1-build
public button fixture. A Chasca 3×2 application/full-account benchmark remains
unrecorded.
