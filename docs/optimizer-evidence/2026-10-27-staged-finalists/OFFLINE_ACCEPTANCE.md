# R2 offline acceptance — 27 October 2026

ROOT reviewed the six experiment files prefixed `r2_` / `test_r2_transport.py`
in `tools/experiments/gcsim/mvp_polish`. The overlay verifies the exact R1 image
map and changes only the final-verification call plus additive measurement data.
No product installation or numerical engine run has occurred at this checkpoint.

Six Go policy tests passed: clear leader and honest mixed rows, close contenders,
rank reversal, all-close cap (18 calls / 5400 iterations), invalid identity / NaN /
iteration count with retained failure evidence, and energy-rejected leader fallback.
The grouped product test and two Python transport/display tests also passed across
the recorded focused attempts. The n500 winner and n100 alternate retain their
actual iteration counts and standard errors through the existing worker and result
path. Existing grouped presentation remains one page with its replacement row.

Two test-fixture failures remain recorded: the first product fixture omitted its
required compact-context identity; the first Python assertion incorrectly expected
two pages instead of one group page with two builds. Only fixtures/assertions were
corrected. No product grouping change was made to satisfy these tests.

Pre-test review also repaired two draft defects: production stages now use the
existing nil-runner path, preserving per-stage engine identity guards; an
energy-rejected pilot leader falls back to the next eligible candidate instead of
ending the whole staged selection. Focused checks cover the latter. A separate
read-only Luna review found no remaining concrete policy blocker.

Evidence: `focused-core-v1-a1.log`, `focused-product-v1-a2.log`,
`focused-transport-v1-a1.log` and `focused-transport-v1-a2.log`. Original local JSON
receipts retain source maps and elapsed times. `mixed-ui-fixture-v1.json` is synthetic
transport evidence only; it is not a benchmark inventory. The admitted numerical
run must use the full real account under [the contract](CONTRACT.md).

These checks support one consumer build and subsequent admission review, not a
performance/quality conclusion. Historical R1/403 helper and archive dependencies
remain; this overlay is not a claim of standalone clean-checkout source closure.
Shared handoffs contain older unrelated dirty changes and are excluded from the
scoped source commit. No ON/WARM, installation or next experiment is authorized.

## Button runner completion

The thin `r2_button.py` reuses the R1 managed owner and real worker path, allows
only OFF, requires the same full-account identity, and exports staged measurements
plus adaptive-policy events. `whole_chasca_button.measured_rows` now accepts an
explicit allowed-iterations argument; its existing default remains n500 only.
Three focused runner checks passed (owner/input/OFF gate, mixed gear extraction,
partial failure retention), with zero engine calls and zero consumer builds in
those checks. See `focused-runner-v1.json` and its log. Combined scope: 7 Go and
5 Python checks. A new n500 confirmation means a separate complete run, not a
statistical independence claim for streams using the same fixed seed policy.
