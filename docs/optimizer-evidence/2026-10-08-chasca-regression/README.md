# Public Chasca regression — 2026-10-08

On2026-10-08 the human accepted the unchanged synthetic inventory and measured
reference, and authorized publication plus orchestrator-coordinated Worker2
uptake. The installed small button fixture retains its separate baseline.

The reusable gate is [check_chasca_optimizer.py](../../../tools/check_chasca_optimizer.py),
with the [accepted baseline](../../../tests/fixtures/gcsim_optimizer_go_v1/chasca_button_baseline_v1.json).
It exercises the chosen application's actual button/worker/backend path using
disposable public data. The accepted reference is123.265s for All Sets and
25.563s for Selected; over reference+5s requests an idle-machine check and an
isolated `--case` rerun. It never updates a slower or changed baseline itself.
Measured results use their reported sampling errors; the formula score of a
noise-selected winner is recorded but is not required to be bit-identical.
Publication and target uptake remain separate operations until their actual
commit/runtime receipts are recorded by the orchestrator.

## Fixed scope

The isolated [spec](../../../tools/experiments/gcsim/chasca_regression/spec.json)
and factory generate 600 five-star level20 artifacts: 24 engine-backed set keys,
five slots and five variants per slot. No private account, characters, weapons,
artifact rows or rotation are copied. Character/weapon/talent choices are
explicit, not read from live account state:

| Character | C | Talents N/E/Q | Weapon90 | R | Selected4p |
| --- | ---: | --- | --- | ---: | --- |
| Chasca90 |1|1/10/9|Astral Vulture's Crimson Plumage|1|Obsidian Codex|
| Furina90 |2|2/10/10|Wolf-Fang|5|Golden Troupe|
| Bennett90 |6|3/5/10|Sapwood Blade|3|Noblesse Oblige|
| Ororon90 |6|1/1/9|The Stringless|5|Scroll of the Hero of Cinder City|

The public project rotation has four fixed cycles, Furina E/Q and Chasca Q on
even cycles, Ororon Q/E, Bennett E/Q and Chasca E/charged shots every cycle.
Infinite energy, level100 target,10% resistance, ordinary n500 finalist checks.
It is deliberately not the user's private rotation; its timing cannot be
inferred from that run. All requests3bonus groups with one leader plus two
single-item replacements each; Selected has its one fixed-bonus group and two
replacements. Selected runtime APIs, imports, engine and consumer come from the
current main application; only fixture/output ownership is isolated.

The 24-set timing scope excludes obvious extra-hit/healing-linked and attack-
speed examples. It is not universal set-response or global-optimum coverage.

## Preparation and lifecycle evidence

- [Preparation01](preparation-01.json): harness import failure before fixture
  generation;0engine calls, cleanup passed. No product failure established.
- [Preparation02](preparation-02.json): synthetic DB/request generated, but
  cleanup encountered a retained SQLite handle and masked the inner exception.
  No engine run occurred; the lost assertion is not accepted product evidence.
- [Recovery01](preparation-recovery-01.json): exact owned orphan inspected and
  removed after its child process exited. Only1,063,652 synthetic bytes removed;
  original failure receipts retained. Main/account data untouched.
- [Preparation03](preparation-03.json): both actual main input adapters prepared
  600 artifacts/four wearers successfully. Separate child exits before cleanup;
  owned job removed, main source/pointer/binary pins unchanged,0engine calls.

## Measurement boundary

The one reviewed first measurement is limited to the two normal cases, with a
900-second whole-probe watchdog and20engine-attempt cap,16expected calls. These
are experiment protections, not product search time limits. No rebuild,
installed engine/consumer substitution, live settings/DB write, Computer Use,
automatic baseline refresh or repeated performance run is authorized here.
The bounded measurement receipt will own actual timings and call/cleanup facts.

## Accepted regression-gate validation

The new gate's seven offline controls and five source parses pass. The first
[full gate](accepted-gate-01.json) completed both normal button cases on the
unchanged installed engine/consumer, with16 matching attempts/results and
73,382,887 scratch bytes removed. All measured140456.039 DPS and Selected
139140.628 DPS are compatible with the accepted references. All took129.094s
(+5.829s); Selected27.703s (+2.140s). The outer check correctly returned
`TIMING_RECHECK_REQUIRED` for All, not a full PASS. Pre-run CPU was37%; three
post-run samples were16/10/30%. These observations do not prove an idle machine
or a code slowdown. The human then confirmed a concurrent Theory run and
explicitly waived this timing observation and the immediate repeat because
the installed search was unchanged. Preserve the alert as loaded-machine
evidence, not a new performance regression or a timing PASS. The accepted
reference stays unchanged; the next meaningful timing check runs in isolation.
The new package changes test infrastructure and replacement labels, not search
or the installed engine. Keep numerical completion, timing alert, and source
readiness separate.

Git intent2026-10-08: save this accepted baseline, reusable gate, its focused
checks and bounded actual run evidence on detached source71fe770. The human
authorized publication and orchestrator-led Worker2 uptake. Only this stage,
08e502a display changes and71fe770 fixture/evidence are transfer candidates;
the detached13cb safeguard, profile edits and other research remain excluded.

## First completed measurement (subsequently accepted)

The retained [candidate](../../../tools/experiments/gcsim/chasca_regression/measurement_candidate.json)
and [recovered receipt](measurement-recovery-01.json) record the single completed
two-mode run through current main's actual offscreen button/worker/session path:

| Mode | Button to result | Backend session | Formula DPS | GCSIM DPS (SE) |
| --- | ---: | ---: | ---: | ---: |
| All Sets3groups,2swaps each |123.265s|122.797s|139125.979|140462.904 (130.984)|
| Selected1group,2swaps |25.563s|25.047s|137465.054|139086.520 (131.391)|

Both winners contain20 unique owned synthetic IDs. The inventory/spec hashes
match preparation03. All's measured leader exceeds Selected's by1376.384 DPS;
this is an observed fixture result, not a universal dominance certificate.
Both report bounded search and unresolved formula boundaries; All additionally
reports its inventory/search work budgets and Selected top-confidence overlap.
No formula-to-simulator exactness or exhaustive optimum is claimed.

Sixteen distinct request/config attempts have matching results:2All captures,
2Selected compact members and12ordinary n500 finalists. These observations
are mapped to the source's one-launch call sites, not independent OS process-
start telemetry. All generated output was removed (73,366,438 bytes); no job
remains. Selected engine7df37b52 and native consumerdd84139e were used without
rebuild/substitution. The post-run main snapshot matches the proven preparation
source/runtime pins; intervening ceabea4 changed readable-rotation docs only.

The initial supervisor stopped before any child twice: a missing argparse
import and a now-reviewed documentation-only HEAD change. Those were harness
preflights, not extra product attempts. After the successful two cases, the
original detailed receipt exceeded its32KiB export guard. Scratch cleanup had
already completed, so detailed per-stage search counters are unavailable. The
separate recovery receipt retains candidate data, emitted completion/count
observations and explicitly post-run-only checks; it does not invent lost
snapshots or timings. Bounded scalar extraction was corrected and syntax-checked
without another engine run. The candidate stayed byte-for-byte unchanged.

The human subsequently reviewed and accepted this fixed setup and its first
timings. Historical candidate/recovery files retain their original provisional
status and bytes; the separate accepted baseline records the later decision.
This is a reproducible synthetic test, not a replay of the user's account.
Their actual runs used597 different artifacts and a rotation containing
`wait(82);`;157862.913/155552.979 measured DPS and174.532/27.641s are separate
observations. They cannot establish a speedup or regression against this test.

Helper-only closeout: `run_measurement.py --help` exits0; an AST-isolated test
retains five allowed scalars and rejects nested values and a257-character
string. No second measurement or managed allocation was used for that check.

Historical Git intent: save this explicitly experimental public factory/probe, fixed spec,
bounded successful/failed preparation evidence and recovered first measurement
from detached source08e502a, with the checkpoint link and read-only timing audit.
The approved automatic own-local-commit rule does not accept a golden, transfer
source safeguard13cb, modify main, or authorize push. Unrelated profile/policy
changes and historical research remain outside this stage.

The [display and user-run audit](../2026-10-08-replacement-display/README.md)
owns the separate174.532s/27.641s observation, corrected physical-assignment
join and source-only green/amber/red labels. Do not equate either a preparation
PASS or those private-account timings with this public fixture's acceptance.
