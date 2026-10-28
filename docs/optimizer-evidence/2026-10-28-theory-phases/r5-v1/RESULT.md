# One timed R5 Theory result — success, 28 October 2026

Sidebar Luna executed the one admitted instrumented R5 run. Button462.079s,
first verified459.594s, first_light→normal Finish→finished_early/join. Formula
196428.786 matches slow uninstrumented T1. Ordinary leader198293.89DPS, n500;
the precise measurement/SE/allocations remain in native.json. No new witness.
2capture/52stat-response/2ordinary counts match old415d control114.734s.

| Non-overlapping top scope | Seconds |
| --- | ---: |
| Context setup |0.683312|
| Capture |8.354755|
| Model |0.100326|
| Config/world |0.064542|
| Response world fork |0 at recorded clock resolution|
| Initial resolve/binding check |0.773798|
| First |396.606653|
| OfferSearch |11.706204|
| OfferResponseProposals |10.225756|
| Verify |13.999735|

Nested within First: checkpoint fork0.069976s. Nested within OfferResponse:
support probes9.930071s. These must NOT be added again. Clock elapsed444.547637s
excludes the earlier catalog/request preamble; gaps/finalization are not invented
phase time. Full start/duration nanoseconds are preserved in phases.json.

Main-model cumulative after original resolution + First: RuleSeconds374.185143,
Preparation.ReplaySeconds372.929676, BindSeconds11.231044, ViewSeconds0.963583.
ReplaySeconds is a subset of RuleSeconds, itself inside this pre-offer work.
Main initial counters were zero. The separate response fork replay is0.155932s;
it is not another372s copy. The dominant time is rule replay/preparation, not
model construction, simulator count, checkpoint copying or ordinary verification.

Observed main preparation:3516Replays,3111JointReplays,3102FullFallbacks;
R1FallbackReplays3140, AnchorPorts26076661, ReferencePorts4677622,
OmittedRecords30754155. Model Requests22020/DispatchHits11010; program
hits10557/misses453. The source-level cause and counter semantics are investigated
separately; do not equate any one count with distinct tuples or simulator calls.

Evidence is available, schema valid, dropped0, all required spans present;
off.json records phase path/hash. Worker joined; registry success, job_removed,
main_protected_after_match and package_retained all true. Managed job-* residue0.
The owned instrumented baseline remains available; no DB/binary/raw scratch is
committed. No repeat/new numeric run was performed for result closeout.
