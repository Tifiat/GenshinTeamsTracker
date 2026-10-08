# Optimizer launch-path Python gate — 2026-10-08

One managed offline job used the main checkout's `.venv` Python read-only.
`PYTHONDONTWRITEBYTECODE=1` and `QT_QPA_PLATFORM=offscreen` were set. The exact
selected files were:

- `tests/run_workspace/gcsim/test_optimizer_process_paths.py`
- `tests/ui/gcsim_browser/test_gcsim_optimizer_ui.py`
- `tests/run_workspace/gcsim/test_optimizer_go_common_boundary.py`

Result: **29 passed, 0 failed, 0 errors, 0 skipped** in 3.037 seconds.
The process-path test launched only its harmless Python child through the
production `Popen` site. UI coverage ran offscreen with mocks; the full AppShell
was not launched. The backend button test remained out of scope while its
fixture is unfinished.

No GCSIM calls/builds, app startup, bootstrap, database access, or network access
occurred. Managed temporary paths stayed inside the job; the test temporary
directories self-cleaned. The runner removed the job (0 leftover file bytes),
its path is absent, no `job-*` directories remain, and the managed root retains
only its pre-existing 1-byte lease file. No source files changed during the
gate.

The main checkout's active-engine pointer was read-only and unchanged. Its
SHA-256 was
`388e28fe2c88122be8690d46fcb603d4228c0f3307d1f1110c1e39f6293f8efb` before and
after.
