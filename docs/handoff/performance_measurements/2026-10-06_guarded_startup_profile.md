# Guarded startup profile — 6 October 2026

Scope: one cold, disposable measurement of the real legacy `main.py` and
supervised `python -m ui.app_shell_smoke` launchers after the accepted common
code/runtime point `071c62a`. The profiler copied only tracked product files
to a physical temporary root, created a fresh synthetic imported profile and
SQLite database, and ran Qt offscreen. It blocked source-private paths,
network/DNS and unexpected processes. No user account, saved profile, engine,
import or Computer Use path was used. `main.py` and `ui/app_shell_smoke.py`
were fingerprinted as `ae503607…` and `09d9a22e…` respectively.

The final one-repeat run passed all four observations. The legacy launcher
reached its first ready tick in 1391.8 ms (baseline) and 1393.8 ms (detailed);
AppShell's child reached readiness in 4040.9 ms (baseline) and 3975.0 ms
(detailed), or 4797.6/4734.2 ms from its supervising process. No source
profile was opened. Every fixture registry and both legacy fixture databases
were unchanged; the synthetic AppShell database did change during startup.
That is reported as fixture behavior only and did not touch source data.

Detailed timings identify the current cold-path concentration:

- legacy: `ui.main_window` import 735.5 ms; `offline_profile` 535.5 ms;
  `artifact_db` 440.3 ms; `account_storage` 391.8 ms; `App.__init__` 127.9 ms;
- AppShell child: `ui.app_shell` import 2758.5 ms; `AppShell.__init__`
  829.8 ms, including `LeftWorkspaceHost.__init__` 373.8 ms. The supervisor
  spawned the child at 225.7 ms; profile bootstrap and lock acquisition were
  below 36 ms and 2 ms respectively.

This is a diagnostic sample from the current local Windows workstation, not a
physical UI acceptance result or a cross-device performance guarantee. It
confirms that the reported slow path is AppShell's broad cold import graph and
initial shell construction, not profile locking/bootstrap. The curated future
work item remains [AppShell Import Graph](../PRELOADER_BACKLOG.md#appshell-import-graph);
do not introduce a loader or lazy UI path from this receipt alone.

The first probe attempts exposed a Windows cleanup failure in the synthetic
fixture: `init_artifact_db()` committed through SQLite's context manager but
did not close its owned connection. It now closes that connection explicitly.
The probe retains a bounded retry only for a true Windows sharing violation and
propagates every other cleanup failure. Focused lifecycle and probe controls
passed before the final run.
