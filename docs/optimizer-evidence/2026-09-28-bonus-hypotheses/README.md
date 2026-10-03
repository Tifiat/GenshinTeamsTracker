# Equal-bonus and sparse-effect experiments — 2026-09-28

Owner: Go design's isolated search-speed section; GP-3 owns current acceptance.
User authorized isolated safe-to-risky hypotheses, inexpensive agents as test
runners, and no Computer Use or promotion before comparison. Main implements
and reviews; a bounded Sol helper implements the direct-capture and Amount-plan
probes. Preserve this evidence through integration review; managed scratch is
removed after each job. Original saved runs and earlier receipts are unchanged.

## Reference and scope

Saved Chasca: `all_sets-20260927-212145-2c1cb70d`, same request, inventory,
rotation, seeds742031889/742031890,49 rows/7 groups. Reference is the
[previous `combined_preparation` prototype](../2026-09-28-preparation-hypotheses/README.md),
not a new search-depth change. Active engine remains `gcsim-v2.45.0-20260927011932`,
artifact SHA `7df37b5224f655d271d9389686bf22445717e02e896df5e3aa22d1d698042f8c`;
installed consumer remains `585aca6b49bd766a2b41fd5cc4392f6aeffd6463b824660f39736f62f55b1715`.
Every search replay uses the actual CLI coordinator and hash/config/seed-bound
saved capture provider, with no engine fallback. The separate direct-capture
probe below is the only source of new engine calls in this wave.

All six search records preserve217013 expansions, two-cycle work policy,
`neutral_cycle_budget` stop and the complete reference fingerprint
`4b6f3f964c3e6de793f0b76366b18f859c19229522b4b83b501485950fb9a4cd`.
This is neither exhaustive search nor a wall-clock timeout. Physical inventory
IDs, unique team ownership, bonus groups and independent single-item swaps pass
the output validator. Historical `exact_rows=false` compares against the older
installed saved result: the known Furina2p-Troupe group is+48.6938 DPS under the
already-approved narrow-frontier experiment. It is not a loss/change introduced
here. Later receipts add explicit paired-reference equality and control names.

`active-source-controls-attempt1.json` additionally passes134 controls for
`amount_plan` and132 for `effect_families` against the saved active-source
envelope. Nine opt-in/live-capture/platform-link tests remain explicitly skipped
in each; their names are retained, not counted as passes. Both rerun the family
interaction/diagnostic regression. Its outer generic scope label predates the
harness wording fix; `controls_only=true` means NO search or simulation occurred.

## Unordered pairs versus equal effects

`domain/packages.go:FeasiblePackages` already uses each unordered pair once;
`Package.Validate` requires canonical set order. On this saved inventory,31
two-piece-capable sets yield465 unordered pairs,31 single2p packages,27 modeled4p
packages and one zero-bonus package:524, not separate A+B/B+A entries.

Different set names can nevertheless have the same effect. The existing final
program cache recognizes equal complete numeric/expression inputs, but only
AFTER composition/serialization. The new family prototype moves part of that
reuse earlier without joining inventories or weakening item/set legality.
124 observed owner/set2p components collapse to32 distinct full raw effect
vectors on THIS retained team model (including zero effects). These are not32
universal catalog bonus types, nor a proof of all rotations' activation.

## Isolated variants and paired timings

Search seconds exclude test/build startup and do not claim full button latency.
Each row is one sequential paired measurement, not a statistical benchmark.

| Receipt | Candidate | Candidate, s | Fresh reference, s | All49 rows |
| --- | --- | ---: | ---: | --- |
| `mixed-attempt1.json` | `mixed_sparse` |65.069|79.110 (`combined_preparation`)|Exact|
| `families-attempt1.json` | `effect_families` |60.970|62.698 (`mixed_sparse`)|Exact|
| `amount-plan-attempt1.json` | `amount_plan` |60.600|61.302 (`effect_families`)|Exact|

`mixed_sparse` is the substantial new improvement (~17.75% paired). A package
with ANY symbolic effect previously converted all11205 ports, including plain
constants, into expression objects/string-map entries. It now carries a dense
numeric vector plus only the actual symbolic expressions. The same dependency-
aware general binder handles reads, artifact coordinates, inter-effect links,
ordered arithmetic and cycles. Numeric leaves bypass object wrappers, not
formula operations. Capture/formula port order is translated through the
existing validated bijection. All constants, including latent/overridden ones,
are checked before lookup; sparse indices and expression graphs stay validated.
Public map/compact producer APIs retain their contracts; one private consumer
opts into the mixed representation. Graph/gradient parity and invalid-input
controls precede search. Symbolic binding including identity work falls from
about18.7s to3.64s; the search policy does not change.

`effect_families` inherits the mixed representation. Exact-bit raw vectors give
constant components run-local identities; symbolic components deliberately keep
distinct identities. Legality, activation and fixed-point interaction merging
ALWAYS happen first. Only then can an ordered component sequence reuse a
composed numeric/sparse payload. Preserve addition order; no floating-point
reassociation or claim that equal point DPS means equal effects. Current source
footprints/uncertainty are rebuilt on hits, not copied from another set name.
Resistance transformation remains after raw addition. Cache bound:128 entries,
two million raw/numeric float words,128000 expression nodes. On this case3012
of4164 compositions hit;1052 actual symbolic compositions become224.249 source
replays,17 joint replays and144 interaction merges remain: this is NOT source-
activation skipping. Gain is smaller (~2.76% paired), requiring broader timing
and memory review before inclusion. Synthetic tests pin source diagnostics,
interaction-before-reuse, port identity, exact bits and bounds.

`amount_plan` additionally caches the syntactic shape of Amount functions,
which the interpreter otherwise scans twice on every call. Each VM keeps at
most128 immutable body plans. Every invocation still resolves current captured
storage, observed-state status and native `clear` binding; no amount, array or
activation state is cached across queries. Unknown/alias shapes use the complete
old implementation. Existing scratch restore/write checks stay intact. Focused
controls cover changed arrays, shadowed clear, aliases and eviction. Measured
gain0.701s (~1.14%) is small; do not call this a major speedup or a proven
cross-team benefit.

Cumulative allocations decrease17.79→15.07→14.55GB through the first two
pairs. These are allocation churn, NOT live memory. Reserved Go heap snapshots
are roughly0.77–0.83GB; family cache increased the first pair's reserved heap
by~59MB, but later snapshots vary with GC. No peak-RSS claim. Bounded fallback
and multi-team memory gates remain required.

## Direct n=1 capture alternative

`direct-capture-attempt1.json` preserves a harness failure: all four captures
finished, then the source-copy helper tried to copy nonexistent `go.sum` from
this dependency-free module. Optional-file handling was fixed; attempt2 passes.
No optimizer/engine fix or quality conclusion comes from that failure.

Attempt2 runs the ACTIVE engine once for neutral and once each for Furina4p
Golden Troupe, Emblem and Marechaussee Hunter, seed742031889. Saved raw stats
remain fixed to isolate bonus changes; inventory IDs only witness that four
distinct free slots exist, not that these are rendered physical builds. Fresh
neutral is semantically identical to saved neutral. No2p captures were needed
to verify simple Emblem ER/Tenacity HP% source fragments; that small observation
is not a generic classifier for every2p set.

| Capture | Engine/export, s | Go load+decode, s | Formula compile, s | Sum, s |
| --- | ---: | ---: | ---: | ---: |
| Neutral |4.264|2.041|0.265|6.571|
| Golden Troupe |1.989|0.804|0.180|2.974|
| Emblem |1.846|0.649|0.121|2.616|
| Marechaussee |1.873|0.629|0.112|2.613|

The extra Python audit decode and helper build time are NOT added to the
estimated native capture path. Neutral exports25.34MB; changed contexts about
3.81–3.88MB. All have383 ordered damage channels, equal duration/channel shape/
topology hash and resistance-port identity. Effect-port identities differ.
This is not changed-item response proof or full event-tape equivalence. A
changed-set formula can be used as a separate context, but is not automatically
a detachable additive bonus or a safely composable2p fragment.

Blanket direct capture is not justified by these costs: three changed contexts
already need about8.2s, while ALL249 source component/joint replays take about
7.4–8.1s on the two-seed shared neutral model. Larger per-owner4p panels would
multiply the direct cost. A few selected difficult/schedule-changing contexts
remain a valid research/fallback scope; this experiment does not eliminate them.

## Remaining hypotheses and acceptance boundary

No new approximate uptime, full-bonus hard pruning, critical-value item cutoff
or dropped low-gain bonus was implemented in this wave. Those ideas need their
own quality experiment. Full effect at one fixed build is not a safe upper
bound over reoptimized items (e.g. a crit-rate set can enable crit-damage gear);
ordinary finalist simulation cannot recover a candidate removed beforehand.
Use any such estimate as ordering/explicit approximate-search policy until its
recall has been measured. Fast output without finalist GCSIM is a different
setting from approximate search quality.

Next decision is which named safe variants and riskier pilots to combine,
then the paired current-inventory matrix one parent-reviewed non-Gaming team
at a time. None of these overlays is installed; no UI/button acceptance,
ordinary n500 validation, Theory or finite-energy acceptance is implied.

## Reproduction and lifecycle

`tools/experiments/gcsim/search_hypotheses/run.py` with `--saved-run` above,
`--variants` from the table and a NEW `--receipt`, always wrapped by
`tools/managed_optimizer_experiment.py --timeout 1200 -- ...`.
`direct_capture_probe.py` has a hard four-fresh-capture scope and the same wrapper.
Default seteffects controls include synthetic tests; active-source controls
require their explicit source-envelope environment. The new `--controls-only`
mode supplies that envelope and records passed/skipped names without another
search or engine call. The saved CLI replay itself always reads the bound source.
Keep failed attempts; at most three substantive retries for one blocker.
Expanded copies, binaries, caches and raw probe captures are disposable managed
outputs; compact receipts and source templates remain through integration.
Six managed jobs cleaned117496240 +117744942 +37766168 +99125456 +118024246
+88192483 bytes. The failed direct attempt is included; no job remains running.
