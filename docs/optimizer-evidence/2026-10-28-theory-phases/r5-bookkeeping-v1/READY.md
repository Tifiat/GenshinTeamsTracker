# R5 diagnostic bookkeeping variant — READY for ROOT review

28 October 2026. Preparation only: no numerical optimizer/engine run. Original
timed R5 source, binary, control manifest and r5-v1 result remain preserved.
This is a causal experiment, not accepted product behavior or a measured gain.

The timed result localized 372.929676 seconds to inclusive joint replay inside
374.185143 RuleSeconds. The collector does not split the replay internals.
R1 reported 26,076,661 anchor + 4,677,622 reference port events; 30,754,155
records were omitted, leaving 128 retained. These are repeated port events,
not distinct tuples, simulation launches or independent replay-timer entries.
Source constructed the entire record and sorted/built its package key before
checking that cap. Removing that discarded bookkeeping is the sole hypothesis
tested here; its share of the measured time is not yet known.

The production delta changes only `r1FreezeConcrete`: defer record construction
until retention is known; derive the record package key lazily once per call.
The boolean sentinel also handles an empty package key correctly. Effects,
constants, sparse effects, uncertainty, admission, frozen flags, concrete
evaluation, search, budgets, package guides and all counters remain unchanged.
`native-bookkeeping.patch` is the complete delta over timed R5, not dirty source.

Two focused Go tests PASS. The old function is reconstructed unchanged as a
test oracle. Sixteen fixtures (prefix lengths 0/126/127/128, known/reference
ports, empty/nonempty choices) compare full outputs and entire R1 stats after
296 calls, including record order and values before/through/after the cap.
A Go-test-only source overlay counts the record key call: once when records
are retained, zero when all are discarded. The actual binary has no spy.
The second test isolates the frozen component admission predicate, confirms
direct concrete calls do not increment the joint replay timer, and confirms
ForkTheory preserves component/group entries and counters. It does not change
that policy or attribute every full fallback solely to the frozen predicate.

Identity is in source.json: timed source map b0b5d32d…, variant map 8848afb8…;
consumer 4d6586bbad6fa01f20ce7831f11317e696c17a3b7e65a42495250165938df304.
Production base has 449 files. Only internal/seteffects/r1_frozen_neutral.go
differs. Test-only additions and their identities are separately listed.
The Go target matches the pinned Windows amd64/Go1.26.4/CGO0 snapshot.
Build/test scratch (171,718,545 bytes) was removed. Original 506cd4b7… binary
and exact control.json bytes are backed up in the same owned app.

The adapter reuses the existing immutable Python/harness/producer/inventory
copy and original phase collector, flags and cleanup. No repack or new button
harness. A thin activation wrapper pins the variant binary/manifest, exports
to this separate directory, and restores the original timed binary/manifest
in finally. activation.json proves restoration; bootstrap-check.json records
the full zero-engine bootstrap with actual flags. Original r5-v1 outputs are
untouched. There is no automatic retry or numerical dispatch.

After ROOT review, one sidebar Luna run uses this exact command from the app:

```powershell
& 'C:/Users/user/Desktop/GenshinTeamsTracker/.venv/Scripts/python.exe' -B 'C:/Users/user/Desktop/worker3 GTT/.codex_tmp/t1-control-v1/app/tools/experiments/gcsim/t1_r5_bookkeeping.py' --action run
```

Output: this directory. Common adapter enforces prepared → one attempt.
Then compare formula/artifacts/work counts, all R1 counters, phase timings and
cleanup against r5-v1; any difference is evidence to investigate, not acceptance.
The old numeric result is not replaced by the new run. FrozenOFF is not built.

Owner: MAIN01a1824a under ROOT01a16b30. Retain this additive variant for seven
days per registry expiry; explicit `--action release` removes only its private
variant directory and preserves the original timed app and durable evidence.
The original timed runner's release remains the whole-app cleanup route after
ROOT releases that separately retained baseline. No MAIN/worker2 state changed.
