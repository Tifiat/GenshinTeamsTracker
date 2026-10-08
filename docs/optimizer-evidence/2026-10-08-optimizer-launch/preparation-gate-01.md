# Optimizer button preparation gate 01

- Result: PASS; both real request-preparation modes completed.
- Scope: one managed disposable job; public synthetic fixture only. No GCSIM engine invocation, app/database bootstrap, native product build, or native validator invocation.
- Fixture: 20 synthetic artifacts, 4 wearers; finite plain action list with 6 normal attack actions and no conditional/counter loop. Fixture SHA-256: `65fbb27fffe87acb25bed574a74a7547ae66b6bda25d02d99312c15de8966ba7`.
- Active local engine: `gcsim-v2.45.0-20260927011932`; artifact SHA-256: `7df37b5224f655d271d9389686bf22445717e02e896df5e3aa22d1d698042f8c`.
- Main active-pointer SHA-256 before/after: `388e28fe2c88122be8690d46fcb603d4228c0f3307d1f1110c1e39f6293f8efb` (unchanged).

| Mode | Request SHA-256 | Prepared-config SHA-256 | Rotation SHA-256 | Request artifacts | Wearers |
| --- | --- | --- | --- | ---: | ---: |
| Selected | `3e9f29d82cc13d30a80bafb7277c4e002b5bec8aeca1cdd89edb59e32ded664b` | `bd2ebe5cfa54eb3e54fba7468c0372002198cb9e4436d13117fa61d79155580c` | `469f83ae23911a66b23fe2b2d322fac793bfad9a2a7a70552d568c5d1b320b3e` | 20 | 4 |
| All Sets | `23dc11648b748abbbcaec78e540d904b056515330bf4e2b733aa468cf4b5ca96` | `bd2ebe5cfa54eb3e54fba7468c0372002198cb9e4436d13117fa61d79155580c` | `469f83ae23911a66b23fe2b2d322fac793bfad9a2a7a70552d568c5d1b320b3e` | 20 | 4 |

- Scratch cleanup: 416,458 bytes removed by the managed runner; job directory no longer exists. The generated fixture database and prepared requests were confined to that job.
- This gate establishes request preparation only. It does not establish engine execution, positive measured duration, DPS, or UI button behavior.
