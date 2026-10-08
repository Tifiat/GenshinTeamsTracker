# Optimizer launch path gates — gate 02

## Result

PASS. One managed disposable job ran the targeted Go and Python checks
sequentially. Native: 5 passed, 0 failed, 0 skipped. Python: 5 passed,
0 failed, 0 skipped. Both commands exited 0.

Native command from `native/gcsim_optimizer`:

```text
go test -v ./internal/engineclient -run 'TestWindowsCurrentDirectoryUnits|TestChildProcessDirectory' -count=1
```

Passed tests: `TestWindowsCurrentDirectoryUnits`,
`TestChildProcessDirectoryKeepsShortDirectory`,
`TestChildProcessDirectoryLongWindowsPath`,
`TestChildProcessDirectoryRejectsUnavailableWindowsDirectory`, and
`TestChildProcessDirectoryHelper`.

Python command from the checkout root:

```text
python -m unittest -v tests.run_workspace.gcsim.test_optimizer_process_paths tests.ui.gcsim_browser.test_optimizer_button_backend.OptimizerButtonHarnessTests
```

Passed tests: all four `OptimizerProcessPathTests` and
`OptimizerButtonHarnessTests.test_completion_uses_application_unlocking_callback`.
The explicitly engine-gated `OptimizerButtonBackendTests` class was not
selected; its opt-in flag was set to `0`.

## Scope and environment

- Go cache, Go temporary files, Python temporary files, and harmless test-child
  outputs were inside the managed job. `GOPROXY=off`, `GOSUMDB=off`,
  `GOWORK=off`, `GOTOOLCHAIN=local`, `GOENV=off`, and
  `PYTHONDONTWRITEBYTECODE=1` were set; Python used the main checkout's `.venv`
  read-only, with Qt offscreen.
- The long-cwd Python child exercised the production process launcher. No
  GCSIM executable, optimizer engine, native product build, app shell,
  account/profile database, or network was used.
- Main checkout active pointer SHA-256 before/after:
  `388e28fe2c88122be8690d46fcb603d4228c0f3307d1f1110c1e39f6293f8efb`.
- Main active engine binary SHA-256 before/after:
  `7df37b5224f655d271d9389686bf22445717e02e896df5e3aa22d1d698042f8c`.
  Active engine ID remained `gcsim-v2.45.0-20260927011932`.
- Managed cleanup removed `63,226,339` bytes; the job directory no longer
  exists. The managed root has zero `job-*` directories and retains its
  pre-existing 1-byte lease file.

This verifies the targeted path helper and harness behavior only. It is not a
real optimizer, GCSIM, or four-button smoke result.
