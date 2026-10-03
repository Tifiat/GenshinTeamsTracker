# Isolated filter hypotheses and saved output counts — 2026-10-03

Owner: [GP-3 checkpoint](../../handoff/GCSIM_GOB11_GP3_CHECKPOINT.md).
Research only: no installed optimizer/engine/settings changes, full search,
new ordinary finalist simulation, matrix batch, app restart or Computer Use.
Low-context Sol helpers implemented the kernels; Luna executed serialized
managed pilots. The parent reviewed their evidence and scope.

## Input and comparison boundary

Exact application request: `all_sets-20261003-201232-82e3ec5d`, SHA256
`43db6218200f074fe182eaf66821f9b42e68f9fe39c07799f94e03fd3e65a6bf`.
The current active engine is `gcsim-v2.45.0-20260927011932`, artifact SHA256
`7df37b5224f655d271d9389686bf22445717e02e896df5e3aa22d1d698042f8c`.
The runner checks that the saved binary belongs to the active engine, verifies
its bytes, and checks request, sources, output, real settings and installed
optimizer hashes before/after. Both actual pilots report unchanged protected
state. They use the same canonical no-set capture/binding/reduction entrypoints
as All Sets, but **do not run its complete search coordinator**.

All **13 returned rows** reproduce their saved formula DPS with **zero residual**
in both actual pilots. The original request verified 35 finalists, not 13:
ordinary verification can promote a different leader, and final output retains
only candidates one physical item away from that leader. These counts describe
different stages; thirteen reproduced rows are not thirty-five new simulations.

The recorded request uses infinite energy. This pilot does not certify finite
energy feasibility, changed schedules, global optima or fresh engine response.

## What was tested

Two saved group leaders: Bennett 4p Noblesse / Chasca 4p Obsidian / Ororon 4p
Scroll, with Furina either 4p Tenacity or 4p Golden Troupe. For each wearer,
three other wearers and three slots remain fixed. Plume/circlet are exhaustively
enumerated: tiny 4x4 pools with K=1, then all available 123x115 pools with K=7.
Every candidate uses real inventory IDs, ownership and exact physical bonus
legality. All methods retain the same priority order and deterministic DPS/ID
tie break; no precomputed oracle winner initializes a pruning threshold.

- H1: interval upper bound for the remaining slot; drop a branch only below the
  current Kth result. Independent stat extrema deliberately relax correlations.
- H2: structural monotonicity over the entire rectangular stat range, then
  same-physical-set dominance. Each removed item needs K available dominators
  with lower IDs to preserve capped/tied ordering. This is conditional on the
  fixed other wearers, not global item deletion or removal of UI alternatives.
- H3: skip an event walk only while no subscriptions, tasks, energy tracking or
  hitlag-sensitive mods can consume it. Preserve event/hitlag indices and query
  timing. Compare complete numeric/symbolic replay outputs, not only DPS.
- H4: prepare a set-family compatibility table from real representative IDs;
  skip impossible two-slot combinations before leaf work. The actual validator
  still checks surviving leaves. This does not depend on formula completeness.

The guarded H1/H2 pilot fails open on unresolved response coverage. The separate
model-scope pilot studies only the **existing compiled arithmetic**, with a
read-only clone; the original unresolved flag and scratch stay unchanged. That
weaker scope is explicitly **not a fresh-engine-response bound** and is not
authorized for product pruning. Unknown/singular arithmetic remains unsupported.

## Measurements and disposition

[Guarded pilot](chasca-pilot-retry3.json): 16/16 top-K comparisons match;
all programs have unresolved coverage, zero supported bounds and zero pruning.
Wide-domain bound overhead: 0.190441s versus 0.122590s enumeration. This is a
fail-open check, not evidence of useful bound precision.

[Compiled-model extension](compiled-model.json): 16/16 comparisons match for
each of H1, H2 and H4. Wide-domain sums below include three-repeat mean kernel
times; H2 includes sign/dominance preparation, H4 includes family preparation.
The common gradient ordering and capture are outside these kernel times.

| Method, eight wide domains | Seconds | Eligible candidates scored | Disposition |
| --- | ---: | ---: | --- |
| Exhaustive baseline | 0.122042 | 718 | Oracle |
| H1, model-only upper bound | 0.646634 | 718 | No legal pruning; about 5.3x slower |
| H2, conservative top-7 dominance | 0.176868 | 718 | Removes none; extra setup, not useful here |
| H4, early physical compatibility | 0.047397 | 718 | Same results; about 2.6x faster **on this small kernel** |

H1 has 869 supported bound calls but still prunes nothing in the wide domains.
Its rectangular bounds combine stats from impossible/different items and set
families. The eight tiny domains have nine legal points; 24 raw H1 skips remove
only invalid combinations, not legal candidates. Tiny timings are dominated by
timer granularity/setup and do not establish a speed gain.

H2 does find structural signs (typically 17 nondecreasing coordinates), but
no item satisfies the conservative K=7 witness rule. This does not prove that
every possible dominance scheme, or a full-inventory K=1 study, fails.

H4 replaces enumeration of 113,160 raw pairs with 6,496 family checks and 718
legal leaves (eight legal family pairs). It saves about **0.075 seconds** across
the sampled kernels. These are fixed two-slot domains, not the full production
refinement pools. Production already restricts pools per set/category, so this
2.6x number must not be applied to the 119-second whole search. H4 merits a
same-input complete-coordinator overlay gate before any promotion.

H3: **236/236 complete replay outputs equal**, 1.885439s -> 1.781761s, a sampled
gain of **0.103678s** (5.5%). The 1,322,898 query evaluations are unchanged;
874,458 query advances qualify for skipping only the event walk. It is not a
query-count reduction or a demonstrated button-time improvement. Existing
component reuse may make the production benefit smaller. Do not promote it as
a solution to the main search duration.

Neutral arithmetic is already marked unresolved **before set bonuses**.
The extension retains up to twelve unique reason samples per panel (not a
complete count), including `artifact_stat_read_binding_unresolved`,
`attack_field_operand_dependency_frozen`, `callback_provider_unattributed` and
health/flat-source dependency boundaries. Disabling the guard does not repair
those dependencies. No new lost-build or engine defect is inferred from this
classification alone.

One-time actual capture: 14.493s / 14.625s. These costs, source replay and build
time are not gains or losses in the kernel comparison. No combination speedup
or new end-to-end acceptance has been measured. None of these prototypes has
been installed. Current acceptance and previously rejected player heuristics
remain with their existing owners.

## Why the request was 5x7 rather than the default

Read-only source/settings audit plus **12 settings regression tests PASS**:

- The saved 20:12 request explicitly contains `set_group_limit=5`,
  `builds_per_group=7`, `fast_mode=false`.
- `builds_per_group` includes the leader: that request means **five groups and
  six replacements each**, not seven replacements.
- The later primary `settings.json` snapshot, modified at 20:48:22 MSK on
  October 3, contains fast=false, groups=3, builds=3: **UI default 3/2**.
  Its hash is unchanged by all tests/pilots.
- Fresh normal defaults are 3/2; fresh fast defaults are 5/20. Explicit saved
  counts persist. Mode switching updates only the mode flag; refresh blocks
  count-setting signals. No inspected path converts the normal default into
  the historical 5/7 request by itself.
- AppShell reads the effective persisted counts on click and passes them to
  the backend. There is no historical settings snapshot proving who selected
  those values. A saved explicit/user or earlier setting is compatible with
  the evidence, **not established user attribution**. No settings were reset.

## Reproduction, failed evidence and retention

Sources: `tools/experiments/gcsim/filter_hypotheses/`. Go source/patch overlays
are applied only inside an owned managed job; no second checkout/source tree
or installed executable is created. Example, with a NEW receipt filename:

```powershell
.venv/Scripts/python.exe tools/managed_optimizer_experiment.py --timeout 600 -- .venv/Scripts/python.exe tools/experiments/gcsim/filter_hypotheses/run.py --run data/gcsim/optimizer-go-runs/all_sets-20261003-201232-82e3ec5d --receipt docs/optimizer-evidence/2026-10-03-filter-hypotheses/new-receipt.json --model-bounds
```

The managed runner owns and removes captures, rule caches, Go build caches and
overlay copies on success/failure; cleanup failure blocks allocation. Five
successful cleanup receipts reclaim 520,285,174 bytes total; no job residue
remains (only the runner lock). Permanent evidence is capped at **six immutable
JSON receipts, 256 KiB each**; exhausted budgets stop rather than overwriting
failed evidence. This is a finite dated collection, not an accumulating log.
Receipt path/escape, preservation and budget tests (3) and managed cleanup/
preservation tests (8) PASS. No automatic deletion of historical receipts.
One 11,994-byte research-module import cache remains under this probe's
`__pycache__`: its narrowly validated shell cleanup was denied by the tool
policy, and no alternate deletion route was attempted. Subsequent runner/test
imports disable new research bytecode; this residue is separate from the
successfully cleaned managed jobs and does not block their lifecycle.

- [synthetic.json](synthetic.json): initial arithmetic oracle PASS; initial
  accidental punctuation argument was rejected before running and left no data.
- [chasca-pilot.json](chasca-pilot.json): harness failure, capture parent had not
  been created. Corrected the research harness, not the engine.
- [chasca-pilot-retry2.json](chasca-pilot-retry2.json): harness failure, saved
  formula DPS is a decimal JSON string, not a number. Corrected the decoder.
- [chasca-pilot-retry3.json](chasca-pilot-retry3.json): actual guarded pilot PASS.
- [compiled-model.json](compiled-model.json): distinct model/legality extension
  PASS, including seven top-level arithmetic controls and five subcases.

Receipts retain the executed prototype hashes. Later helper changes do not
retroactively change earlier attempts or extend their scope.
