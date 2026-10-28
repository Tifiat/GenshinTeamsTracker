# Theory 429s / historical105s — saved-data and source forensics

28 October2026. Read-only analysis of result81306ce and the historical
`2026-10-25-cache-team-matrix/corpus-main14-v2/chasca_600_fixture-theory/off.json`.
No simulations, tests, builds, profiler, product/harness edits or new timing runs.

## Finding and limits

**A policy leak is proved:** T1 inherits the AllSets R1 frozen-residual opt-in
through a shared neutral-model constructor. Thus this was exact R5 engineering
source, but not the historical ordinary Theory availability policy. A concrete
slow path now admits formerly unsupported package arithmetic as uncertain guides,
rather than stopping that tuple before binding/allocation. This is the leading
source-backed explanation of the regression, not a measured allocation of all
359 extra seconds to one function.

The observed search changes from10534 found +476 unavailable tuples to11010
found +0 unavailable, with447→452 families. Their sum remains11010. This count
identity is consistent with the policy change; complete old/new tuple-key sets
were not retained, so it is not a per-tuple identity join. Different attained
anchors/candidates may also change work within the same fixed search policy.

## Timing boundary — what429.045 actually includes

R5 reconstructed `cmd/gtt-optimizer/main.go:463–464` starts the progress clock
with `time.Now()`. `theory_session.go:313` constructs it and:325 emits
compiling_formula. `theorySnapshot` at:163–178 reports cumulative
`time.Since(emitter.started)` at:170, not a phase duration.

Before the first simulating_finalists event, the source executes:

1. Neutral context/two-seed capture, panel compilation and model construction
   (`theory_session.go:328–371`); source catalog loading at:239 precedes this clock.
2. Independent response-world fork (:378–387), original resolution (:435),
   `session.First` (:439): starts, one catalog pass, publication refinement,
   absorb and pre-deep checkpoint fork (`internal/theorysearch/session.go:108–132`).
3. OfferSearch and OfferResponseProposals BEFORE ordinary finalist verification
   (`theory_session.go:418–424,557–569`). The response producer executes its
   stat-response simulations and proposal work here (:399–416;
   `internal/theoryverify/responses.go:620–677`).
4. `Archive.Verify` sets inProgress and publishes BEFORE launching the finalist
   batch (`internal/theoryverify/archive.go:364–401`). This is the429.045s event.

Therefore429s includes capture/model, first search and forks, candidate offering,
support probes and proposal processing. It is neither pure formula compilation
nor pure search nor ordinary finalist execution. The actual first n500 finalist
batch follows this event. Support probes are distinct from that batch.

| Saved metric | Historical415d | T1 R5 | Difference |
| --- | ---: | ---: | ---: |
| Button→terminal |105.344s|461.797s|+356.453s|
| Adapter optimizer process |94.156s|449.437s|+355.281s|
| First finalist event, UI offset from first progress |70.344s|429.047s|+358.703s|
| Verified searching event, same UI clock |81.844s|442.110s|+360.266s|
| First finalist→verified searching, same UI clock |11.500s|13.063s|+1.563s|
| First verified snapshot from button |97.532s|459.516s|+361.984s|
| Prepare / formula-input adapter |4.531 /5.860s|5.266 /6.454s|+0.735 /0.594s|

The current native429.045s and UI429.047s nearly agree. The old native timestamp
is not retained;70.344s is explicitly an event-arrival offset. Almost all excess
is before finalist verification; actual n500 verification and GUI Finish cannot
account for it. Historical larger terminal/progress overhead partly offsets the
pre-finalist difference. No individual constituent above has a saved timer.

## Exact source identity, not dirty HEAD

Old consumer415d995c20897d13faf70217fedd37831528e6570b249b472d154b36a61f069d
is bound by `2026-10-25-mechanic-compiler/stage22-final-v1-release.json` to403
source files, map a5262483285f03b982553238f531c9823c8a04d1623c5c3d45b72b200672aa81.
Current consumer6f3027201939f0a796db8ba90a76187bdebbee8dfe9056b98ff510677b350e27
uses444 files, map48f643c2e4c7f353806513c8e00f9f5efd31d5bfe615cdb93a038d9f84b9ae09.
Producerf1e, original config/rotation/target/context/seeds and inventory match.
R5 Python is separately frozen; an identical historical Python image is not proved.

R5 bytes were reconstructed in memory using r3_recovery (Git6f1cab8389bc63e53297a91a7b14b743009ebd96
+ checked r2-source-delta-v1) →r3_engineering→r4_redundant→r5_redundant.
The resulting444-file map exactly matches the run. Selected old bytes came from
R2's retained image or hash-matching local files, never trusted merely because
they were live. Reverse removal of the documented R1 additions from binding,
expressions/composition also reproduced their old manifest digests exactly.
Source line numbers below refer to these reconstructed images, not current HEAD.

Theory session hash is unchanged:
`f818ffa4532fc76880abeac1d0e54d317b4c0b73668a960c2b1ba8ba8707750f`.
Search hash unchanged:
`4ea4f236254d4ea37831aac949dec7bc4bd6026aae27c90e180d0533caf6d342`.
Theory allocator, response producer/supportimpact files, verification archive,
full_build.go, main.go and parse-cache source likewise match the old manifest.

## Proven policy chain and reuse consequences

- Harness `t1_theory_button.py:219` exports `GTT_R1_SINGLE_NEUTRAL=1`.
- R1 recipe `r1_single_trace.py:62` adds the global env check to shared
  `internal/setcontext/neutral.go:107`: `binding.EnableR1FrozenResiduals()`.
  Theory constructs this same model at `theory_session.go:363`.
- `neutral_expressions.go:169` now returns `b.r1Freeze(choices,out)` (recipe:53),
  whereas exact415d returned out unchanged. `r1_frozen_neutral.go:42–75` keeps
  complete results and invalid operations intact, but handles incomplete results.
  At:54–71 it can clear boundaries and mark a guide; at:74 it can additionally
  call `EvaluatePackages` for concrete rule replay. At:108–128 unresolved source
  slots become observed-anchor or preserved-reference interventions, with
  uncertainty;:140 clears boundaries and:141 marks r1Frozen.
- `NeutralModel.resolve` (`neutral.go:167–204`) formerly returned unavailable
  when effects were incomplete. Newly completed uncertain guides continue into
  binding and Theory family/allocation (`theorysearch/search.go:325–347`). Old
  unavailable evidence specifically records unobserved Custom resource facts.
- Frozen output is deliberately ineligible for reusable component composition:
  `neutral_composition.go:68` adds `!out.r1Frozen`. At:295–296 or:312–313 an
  unusable component triggers full joint rule replay, before the composed-payload
  lookup at:342. `conflictGroup:97` also refuses unusable entries. Combined with
  r1Freeze's optional concrete replay, this is real repeated rule work for these
  newly admitted cases. **Joint replay interprets retained rules in memory; it
  is not a new gcsim trace/capture.** T1 retained exactly2 capture requests.

This is not proof that a previously complete program lost reuse. Incomplete
components were already unusable in415d, but their tuples could terminate early;
R5 now continues work. General target/program caches remain in place. R3's
reverse index retains pointer/key checks; Theory fork resets the index and
rebuilds it from fork-owned programs. R5's view change uses one owned scratch
copy instead of two while retaining specialization-cache attachment and preflight.
No static evidence of a lost complete-program cache was found in these diffs.

Other activated shared changes: R3 parallel two-seed capture, typed canonical
JSON, reusable adjoint buffers, reverse program index, operation validation;
R4 typed panel/digest and R5 evaluation/view/hash work. Reusable adjoints change
retained-memory behavior, but no old RSS/GC evidence assigns them time here.
R2 staged-finalists alters only the AllSets call; Theory still invokes unchanged
VerifyFullBuildsWithRenderer with n500. It does not run the AllSets n100 policy.
The R1 counters are not started on the Theory entry, so their new detailed phase
timers were not exported. These alternatives cannot be timed from this receipt.

## Existing counters and missing evidence

Current First:1 completed pass,8 catalog sweeps,2 publication refinements,
0 deep bundles,111890 formula evaluations,21460 gradients,1356 allocation
attempts,666 independent/690 transferred starts,8 tuple-alias hits. Old detailed
work counters were dropped by its projection and are unknown, not zero.
Current output lists52 stat-response results +2 n500 finalist results; old probe
count is unknown. Both retain2 completed n500 finalists, lifetime limit7 with
response reserve2, full45 rolls, same package-domain cardinality3595305184641.

Both OFF receipts have identical AST236 misses/3569 memory hits and IR71
semantic analyses/473 fresh binds/473 memory hits; bundled/writable hits0.
The old bundled directory had43 files and the new one0, but cache-OFF disables
both disk paths (`rule_parse_cache.go:748–750`); the receipts corroborate this.
It is not evidence of lost disk-cache reuse. Model rule/bind/view seconds,
component/full-fallback counts, per-response duration, First/fork/OfferSearch
timers and old gradient/allocation counts are absent. Thus no defensible exact
split of429s or all358.703 extra UI seconds exists in saved evidence.

## Minimal proposed correction — discussion only

Separate **no additional captures** from **allow frozen-residual candidates**.
Keep the no-recapture policy and exact2-seed neutral universe. Add an explicit
independent frozen-residual policy at the model boundary; for the next separately
approved Theory comparison set it OFF, while preserving accepted AllSets R1
behavior. Do not simply unset SINGLE_NEUTRAL globally, which could re-enable an
AllSets recapture fallback. Theory's FormulaWorld already has no capture fallback.

Retain R3/R4/R5 engineering changes, cache OFF, normal45-roll domain, response
reserve/budget and first verified→Finish boundary. First review this narrow
configuration separation against the old unavailable policy; restore genuine
unknown status rather than treating unobserved effects as known. Any later
implementation and comparison require a separate human GO. If further attribution
is requested then, export existing rule/bind/view/replay statistics and separate
capture/model, First/fork, offer/probes and verification timestamps; never infer
their seconds from a single cumulative progress event. None added or run here.

STOP. ROOT owns current handoff/queue updates; this file saves bounded forensics.
