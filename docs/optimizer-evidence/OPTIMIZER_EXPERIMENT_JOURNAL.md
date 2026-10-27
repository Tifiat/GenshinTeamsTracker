# Optimizer experiment journal

Consolidated on 27 October 2026. This is the single observation index; dated
receipts retain their original measurements. Current execution authority belongs
to the shared queue and [checkpoint](../handoff/GCSIM_GOB11_GP3_CHECKPOINT.md).
Human resumed after the quota pause on27October. Historical investigation below
is complete enough to select the next configuration without repeating it. This
investigation ran no optimizer, build, installation or product-source edit.

## Comparison rules and unresolved reference

The user remembers Chasca at approximately97 seconds through the button with
157–158k measured DPS. That joint observation has NOT yet been located in the
inspected receipts. It remains an unresolved reference, not disproved or replaced
with another team's timing. If its exact version cannot be recovered, use the
fastest evidenced useful configuration and identify reusable parts.

Keep input/inventory, rotation, engine/consumer/source, mode, result count, cache,
timing boundary, formula versus ordinary DPS, uncertainty and stop reason together.
An internal search time is not button latency. A public600 fixture is not the
user's full account. A fast failed/partial run is not a successful baseline.
Do not add nested timers or compare versions as an isolated patch experiment.
Preserve old rows; each useful completed stage needs a scoped local commit under
[the milestone rule](../handoff/HANDOFF_MAINTENANCE.md#commit-useful-milestones--human-order-27-october-2026).

## Located versions and measurements

| Evidence | Input / configuration | Measured boundary and result | Interpretation |
| --- | --- | --- | --- |
| [8October user audit](2026-10-08-replacement-display/README.md), [Chasca receipt](2026-10-08-chasca-regression/README.md) | Chasca/Furina/Bennett/Ororon, real597 artifacts; engine7df37b52; main consumer separately verified dd84139e; All3 groups×3 rows,9 n500 | Full session174.532s; search117.104s; ordinary38.834s; preparation15.657s; remaining2.937s. Best ordinary157862.913DPS. Two captures; parser465hits/0misses;996240 expansions;2-cycle work stop | Strong historical real-account reference. Request itself does not attest consumer. This is not the still-missing97-second sample |
| Same user audit | Selected1 group×3 rows,3 n500 | Full27.641s; search3.586s; ordinary11.556s; preparation8.844s; remaining3.655s; best155552.979DPS | Different mode, not All Sets acceleration |
| [8October public gate](2026-10-08-chasca-regression/README.md) | Synthetic public600, dd841/7df | All button123.265s,140462.904±130.984SE; Selected25.563s,139086.520±131.391SE | Separate public fixture |
| [25October installed comparison](2026-10-25-chasca-current-button/closeout-report-ru.md) | Same public600,77b2a653/3913a877 | All button110.157s,139969.822±133.949SE; Selected36.703s,139110.315±129.055SE | Fastest located completed installed All button sample on this fixed public fixture. Selected timing regressed; one run each, no general speed acceptance |
| [Installed full-account ON/OFF pair](2026-10-25-cache-team-matrix/corpus-main14-v2/chasca_600_fixture-all_sets/pair.json) | Actual604 account/597 request despite historical `chasca_600_fixture` label;415d995c/f1e076b7;All3×3,n500 | ON button455.719s,158230.985±107.223SE; OFF455.844s,158472.516±107.301SE. Search392.355/391.838s,307575 expansions,cycle-budget stop.98 reserved capture slots/provider timing rows;9 ordinary completions | Installed slow behavior exists independently of the later410s experiment. Reserved slots are not a proven process-launch count. Warm saved0.125s in this pair; no material total benefit established |
| [September exact reuse](2026-09-28-player-hypotheses/README.md) | Saved real Chasca request `all_sets-20260927-212145-2c1cb70d`,7df;fast7×7; ordinary0 | Original search132.262/132.780s; exact-reuse `player_safe_wide`91.355s, all49 rows unchanged | Search only; formula top153577.8043, not ordinary157–158k/button97 |
| Same September experiments | Shared scalar point32 screen + narrower refinement | Search42.658/44.833s; adaptive43.443s; all49 Chasca formula rows retained/improved | Fastest located Chasca search family, not installed full-button acceptance. Cross-team failures below prevent blanket adoption |
| [September matrix](2026-09-28-player-hypotheses/matrix/README.md) | Original-width exact reuse,13 non-Gaming teams | All637 rows/IDs/formula scores retained; examples Taser150.432→79.936s, Overload87.910→50.895s, Aggravate110.334→60.132s, Chiori603.798→440.839s | Search-only evidence; Gaming deferred. Clear reusable exact optimizations, not universal sub100s |
| Same matrix, installed promotion | Navia,e0bf5d64/7df | Search94.866s;adapter97.531s | Located97.531 is Navia, not proof for or against the user's separate Chasca observation |
| [October H4](2026-10-03-filter-hypotheses/whole-search/README.md) | Same frozen legal inventory,35 builds,physical legality prefilter | Search135.891→127.672s and144.566→138.572s; all35 scores/order exact. Physical visits6205182→1776685;1187017 scores unchanged | Useful exact early filtering;158822.6228 is formula DPS, not ordinary DPS |
| [18October width experiment](2026-10-15-mvp-polish/chasca-width-20261018.md) | Public600,current25576 engine,width8→4 | Search81.697→59.383s;9 ordered finalists exact,formula139142.428;ordinary0 | Uninstalled heuristic; separate failed V1 export retained |
| [Candidate preservation Chasca](2026-10-15-mvp-polish/candidate-preservation-chasca-v2-result.json), [interpretation](2026-10-15-mvp-polish/tighnari20-general-scalar.md) | Public600,4f2066c0/3913; research verification allocation | Search42.232→41.471s; extended quality protocol122.001→83.000s; ordinary selection10→7 calls; independent139993.507±126.259→140242.867±134.001SE | Useful verification-policy candidate. Preparation excluded; control adds a separate heldout adapter33.141s, so83s is not a button measurement or isolated algorithm gain |
| [V3 control](2026-10-26-response-pilot/whole-search-chasca-v3-control-review.json) | Experimental C4 disabled, NOT historical fast optimizer | Soft-finished410.063s;search371.614s;158259.586±109.952SE;92 captures=2base+90fallback |90 fallback boundaries from unsupported healing,0 schedule-change boundaries. Fallback process197.780s+decode83.518s=281.298s |
| [V3 C4](2026-10-26-response-pilot/whole-search-chasca-v3-candidate-review.json) | Experimental candidate,soft-finished |288.422s;search253.535s;77458.281±134SE;2captures;56 package projections207.469s | Failed configuration, not quality acceptance.54 Bennett packages prepared/0processed;2042unprepared. Do not infer the entire gap is formula ranking |

## Why earlier configurations helped, and where they failed

1. Exact reuse reduced repeated context resolution, unchanged formula-region
   construction, binding and source-program work. Dense constants plus sparse
   variable effects retained arithmetic. September `player_safe_wide` kept the
   original search policy and all49 Chasca outputs; matrix retained637 rows.
   Inspect these existing layers before adding duplicate caches.
2. Shortlisting/narrowing changed recall: point32 lost a Flins group; point96
   lost Bloom's best; all-package width1 lost Navia top1 by128.780 formula DPS;
   width2 restored those cases but lost Chiori ranks5–7 by about46DPS while top4
   remained exact. Old acceptance demanded exact secondary ranks. Current user
   prioritizes best usable builds/time and permits measured small losses, so
   some former rejections merit reassessment, not automatic promotion. Candidate
   ordinary quality and full time still need paired evidence.
3. Mean/peak buff approximations did not remove discovery cost. Mean saved
   little; peak lost lower leaders by up to5995DPS. Final simulation cannot
   recover a candidate already eliminated by a distorted model.
4. Source review at `d965932` versus current `neutral_coordinator.go` identifies
   a changed fallback condition: old schedule potential/observed schedule change
   versus typed schedule-change, unknown-operation, unsupported-source and
   analysis-budget boundaries. Missing neutral model also now requests capture.
   This is a generic policy change, not proof that Chasca requires a new rotation.
   V3 receipts directly attribute90 extra captures to healing uncertainty. The
   installed corpus has49 unavailable contexts and98 provider timing rows; do
   not transfer V3's exact breakdown to that separate run without attribution.
5. [Mechanic compiler stage](2026-10-25-mechanic-compiler/FULL_STAGE_REPORT_RU.md)
   fixed dependency dispatch/read-only tables and preserved runnable unknown
   cases, but its recovery policy added cost: Overload102.797→125.797s, with
   six extra contexts costing24.001s. Earlier bad52778DPS/337.844s was rejected;
   unavailable models1712→6 and captures98→14 after repair. Theory's separate
   quality loss was a missing final local refinement, not a worse formula.

## Useful recent experiment findings to retain

Receipts below are in [response-pilot](2026-10-26-response-pilot/). They are
local or partial evidence unless explicitly stated, not whole-search acceptance.

| Finding / receipt | Evidence and decision |
| --- | --- |
| `c2-v1-diagnosis.json` | Whole-modifier validity contaminated a requested HP dependency with an unrelated unknown ATK modifier. Field-sensitive provenance is needed; zero observed response is not independence proof |
| `c3-v5.json`, `c4-local-health-v8.json` | Fixed replacement double counting; shared known arithmetic, frozen residuals,30 health roots/108 linked ports and3-anchor parity. Synthetic/saved-chain scope |
| `stat-read-repair-v1-decision.json` | Missing caller SourceID froze known own EM, making reaction contribution constant across builds. Generic stat primitive restored six-build ranking; unknown external modifiers remain residuals |
| `projection-v1-diagnosis.json` | Arithmetic0.18–0.22s versus repeated integrity30–31s: optimize data lifetime/validation before simplifying more math |
| `integrity-v2-chain.json` | Exact local parity; OFF preparation26.61→16.54s, WARM25.86→17.94s |
| `cache-order-v1.json` | Four fresh-process comparisons: OFF16.098s/WARM16.126s means. No demonstrated total preparation benefit; persistent cache OFF selected, within-run reuse retained |
| `calibration-reuse-v1-root-review.json` | Private immutable validated snapshot:7 visits/5 builds28.437→5.579s; scores/80gradients exact; hashes84→4. Memo arm5.150s single-order marginal benefit unproved; memoOFF selected |
| `whole-search-chasca-v4-failure-review.json`, `whole-search-harness-repair-v1.json` | V4 failed before native launch on explicit reused-engine path.5top/16subcase harness checks passed; next packet source remains PARTIAL/unchecked/unrunnable. No V4 quality/time result |

## Recovery map, checked read-only by existing MAIN on27October

No executable, benchmark or build was run in this investigation. Hash/source-map
reconstruction used reads and in-memory overlays only; live files were unchanged.

| Version | Recovery route / limits |
| --- | --- |
| dd84139e /7df37b52 | [Launch receipt](../handoff/integration_receipts/2026-10-08_optimizer_launch_hotfix.md) binds native build to Git `d965932afe769bd5adeb10c71673cdfaa627c499`; commit/tree exist. Exact7df engine exists under `data/gcsim/engines/engines/gcsim-v2.45.0-20260927011932/build/gtt-gcsim.exe`. dd841 absent from25 inspected named consumer binaries/archives; not proof of global absence. Source recoverable, bit-identical binary rebuild/toolchain not proved |
|77b2a653 /3913a877 | Exact consumer `2026-10-25-mechanic-compiler/runtime-rollback/previous-gtt-optimizer.exe`; binding in `rollback-binding.json`. Exact engine under `gcsim-v2.45.0-unified-health-20261023/build/gtt-gcsim.exe`. `model_preparation.py::product_images()` reconstructs364 source images, map363f0286e10a231ea62de3f40438a4c6c51a49ae0a12ff7c8b1c3e408c3a1a37 |
|fd2c2cb3 /3913a877 | Exact consumer `2026-10-15-mvp-polish/model-preparation-install-v2-rollback/previous-gtt-optimizer.exe`; accepted361+4node-lookup overlays give362 images/map22e28d3ef48bffda6cbe0ab8a06e57b1068d77636f600842b4e3302a208b57c6 |
|a2c59f73 /3913a877 | Exact consumer `2026-10-15-mvp-polish/dense-node-install-v1-rollback/previous-gtt-optimizer.exe`; archived351+40product-port files deduplicate to361/mapb747d1d9d497d87d19e338cb1afde26e1a50e6a7c6c62aed8be70c823ed7c57a |
|4f2066c0 /3913a877 research | Exact `candidate-preservation-tighnari-v1-consumer.exe.gz`;10 reviewed deltas over361 produce366/mapfbf9d98d9d3995faff00a1ad4d782956ff8784ba70b00e9019599dfb1db24543. Uninstalled policy, not ordinary installed baseline |
|415d995c /f1e076b7 installed | Exact live binaries preserved. Accepted403 map a5262483285f03b982553238f531c9823c8a04d1623c5c3d45b72b200672aa81 reconstructs only after reversing THREE later OnHeal research sections in memory: `neutral_expressions.go`, `rule_program.go`, `rule_resources.go`, from `2026-10-25-formula-preparation/dispatch-v3-product.patch`. Other2patch sections already have base bytes; do not reverse twice. Physical dirty source is not installed415d |

The latest product merge on master before this investigation was `cfa93e5`
(11October); later installed families above primarily used archives/receipts,
not committed source. This is a preservation/process gap, not evidence all code
was lost. Rule commit `2236ad2` now requires useful source/evidence milestones.
Do not repair the gap by committing the entire mixed dirty tree.

## Next decision after historical investigation

Start from recovered fast behavior and isolate changes, not another total rewrite.
Use dd841/7df's real-account result as the located historical quality reference;
77b2/3913 is the ready-binary installed comparison; September exact reuse and
4f2066's bounded verification allocation supply separately evidenced ideas.
No single row above is a proved best whole pipeline on today's full inventory.

First compare source policies for neutral reuse, unknown residuals versus genuine
schedule changes, per-package projection lifetime, candidate admission and final
verification. Preserve legal inventory/ownership/finite-value/unknown diagnostics
and measured final DPS. Avoid generic recapture merely because analysis is unknown;
do not silently call unknown response zero or use approximation as an exact bound.
Choose one concrete modular configuration from that comparison, commit its source
and run one complete same-input Chasca comparison through the button path, with
cache ON/OFF and per-stage timings. Material anomaly stops the routine series;
only a specifically justified diagnostic may follow. Navia/corpus expansion comes
after review. Do not run the partial V5 harness; installation remains outside
the current experiment scope.

No new benchmark results were produced by this historical investigation. Observer
remains disabled. Existing checks and failed receipts remain unchanged.

## 27October: R1 configuration selected, implementation authorized

The human authorized one complete Chasca experiment and a full report under the
[R1 contract](2026-10-27-single-trace/CONTRACT.md). ROOT selected the normal
neutral/parametric path from accepted403/a5262483 plus current f1e producer,
without C4 per-package three-anchor projection or any additional context capture.
Known arithmetic stays; unresolved ports use typed concrete-anchor freezing or
explicit reference-only uncertainty. Existing solvers and9n500 checks are retained
initially. MAIN integrates/checks the complete chain; Luna runs first OFF then
admitted warm ON on identical full-account inputs. No measurement yet; no install.
Residual learning and later teams are not part of this one-configuration scope.

[R1 core checkpoint](2026-10-27-single-trace/CORE_CHECKPOINT.md): six focused Go
tests passed with zero engine calls; core source/delta frozen for a separate
research commit. Actual3×3 wrapper check also passed; full managed integration
and numerical measurements remain pending. The historical403 helper/archive
dependency is explicitly disclosed, not falsely called a standalone source tree.
