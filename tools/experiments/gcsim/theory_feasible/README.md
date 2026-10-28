# Feasible Theory search prototype

Owner and numerical evidence:
[8–9 October experiments](../../../../docs/optimizer-evidence/2026-10-08-theory-feasible/README.md).
This is an isolated research harness, not an installed optimizer or a second
gameplay engine. Retire the harness after its reviewed production replacement;
retain the compact dated evidence and focused mathematical tests.

From Worker2, use an available project interpreter (the main checkout's virtual
environment can be reused read-only):

```powershell
& '..\GenshinTeamsTracker\.venv\Scripts\python.exe' -B tools/experiments/gcsim/theory_feasible/run.py --mode unit --receipt docs/optimizer-evidence/2026-10-08-theory-feasible/unit-NN.json
& '..\GenshinTeamsTracker\.venv\Scripts\python.exe' -B tools/experiments/gcsim/theory_feasible/run.py --mode search --receipt docs/optimizer-evidence/2026-10-08-theory-feasible/search-NN.json
```

The historical first-stage cached comparison adds `--phase combined --reuse-numeric --reference
docs/optimizer-evidence/2026-10-08-theory-feasible/search-01.json`. It makes only
two new preparation engine calls and reuses prior finalist checks only after
matching source/fixture/engine binding and exact sets/allocations/witnesses.
Use the default command without `--reference` to request a fresh finalist check.

Use a fresh receipt filename; receipts are never overwritten. The runner owns
one `managed_scratch` scope, copies the current native tree and this kernel into
it, records source/toolchain/selected-engine identities, and removes temporary
source, module/build caches, captures and binaries on success or failure.
Existing orphan jobs block allocation. No engine or consumer is installed.

The search command first runs kernel tests, compiles a disposable Go test binary,
then runs separate ablation and combined-search processes. Each process captures
the same saved Chasca/Furina/Ororon/Bennett team on two fixed seeds, using the
currently selected verified engine. Combined search runs twice in one process
to distinguish a fresh model from warmed caches. At most three distinct formula
families (leader, competitor, independently solved none) receive two fresh engine
samples each. This is at most ten engine calls; none occur inside the allocation
or package loops. Compilation, source preparation, capture, model preparation,
search, and verification are recorded separately.

`kernel/` is copied as `internal/theoryprototype`. It contains feasibility,
projection, numerical steps, starter-row changes and focused synthetic tests.
`family_probe.go` is a scratch-only accessor to the existing exact program key;
each actual package still passes source activation/interaction validation.
`experiment_test.go` owns formula adaptation, package/main neighborhoods and
measurements. Source formulas remain in the existing native evaluator.

The prototype is deliberately bounded research: no new production option,
finite-energy mode, UI control, account item enumeration, or global-optimum
claim. Four-star-only sets need their own mixed-rarity budget/main-stat model;
they are explicitly excluded from this five-star domain.

## Independent second-stage controls

Run one command at a time, after announcing its finite engine series. Use new
receipt filenames and review a finished run before starting another. These
phases reject `--reference`; previously completed outputs cannot seed a cold
quality comparison. Every `r2World` gets its own model and empty search caches
from the same immutable neutral capture. This avoids extra captures while
keeping numerical starts independent.

```powershell
& '..\GenshinTeamsTracker\.venv\Scripts\python.exe' -B tools/experiments/gcsim/theory_feasible/run.py --mode search --phase r2_bench --verify-limit 3 --receipt docs/optimizer-evidence/2026-10-08-theory-feasible/r2-bench-NN.json
& '..\GenshinTeamsTracker\.venv\Scripts\python.exe' -B tools/experiments/gcsim/theory_feasible/run.py --mode search --phase r2_fast --verify-limit 0 --receipt docs/optimizer-evidence/2026-10-08-theory-feasible/r2-fast-NN.json
& '..\GenshinTeamsTracker\.venv\Scripts\python.exe' -B tools/experiments/gcsim/theory_feasible/run.py --mode search --phase r2_search --verify-limit 2 --receipt docs/optimizer-evidence/2026-10-08-theory-feasible/r2-search-NN.json
& '..\GenshinTeamsTracker\.venv\Scripts\python.exe' -B tools/experiments/gcsim/theory_feasible/run.py --mode search --phase r2_pairs --verify-limit 1 --receipt docs/optimizer-evidence/2026-10-08-theory-feasible/r2-pairs-NN.json
```

The respective maximum engine counts are8/2/6/4: each phase captures two neutral
members; pairs verifies only a new improvement if found (none was found in01).
Bench and search verify their explicit finalist lists. No engine
call is made per package, main, line or numeric proposal. The research watchdog
is20 minutes for the combined Go phase, not a product timeout or partial-success
criterion. Receipt packing failures remain failures even if a separately bound
audit establishes that the completed numerical phase is usable.

`round_two_test.go` owns A–H controls, cold ON/OFF route/state comparisons and
changed-bonus transfer. `aggregate.go` decomposes only a fixed line-incidence
domain; `joint.go`, `fast.go` and `slot_lines.go` compare reoptimized feasible
main/line alternatives. `marginal.go` and `window.go` retain measured rejected
alternatives rather than silently entering the main route. The affine probe
requires structural proof, positive scale, identical domains/origins and no
unresolved graph dependencies. The source-based Hunter probe is explicitly
restricted to an observed health-event schedule and six allowlisted sets;
it is a diagnostic approximation, never a generic production resolver.

The final outer route scores every admitted objective family with changed
wearer singles and all same-wearer goblet/circlet pairs, then refines three
retained families per block with a cheap complete main sweep. A finite pool
combines two replacements against the current leader; search01's members had
all been selected earlier. The separate `r2_pairs` probe deliberately combines
two corrected nonwinning singletons from a fresh strong anchor. Finally, three
retained distinct families plus Tenacity/Troupe/none where distinct receive
independent cold full-build correction and a warm alternating main/line solve.
Returned rows are leader, strongest retained distinct-family competitor and
none. Screening limits, local starts and unavailable effects prevent global
or full-catalog ranking claims. No named control imports an earlier solution.
