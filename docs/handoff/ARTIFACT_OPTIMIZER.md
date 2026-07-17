# Artifact Optimizer Backend

Status reviewed: 2026-07-17

## Current Status

An isolated real-account Artifact Optimizer v0 exists in
`run_workspace/artifact_optimizer/`. It is backend-only and does not depend on
AppShell, PvP, widgets, or mutable TeamBuilder state.

Implemented:

- read-only loading from the existing `data/artifacts.db` `artifacts`,
  `artifact_substats`, and optional `artifact_equipment` tables;
- five-slot candidate search over real artifact ids;
- additive raw-stat proxy weights in the project's existing units (percentage
  stats remain percentage points, flat stats remain flat values);
- fixed and excluded artifact ids, rarity/level filters, allowed main stats per
  slot, and an equipped-artifact policy that may preserve the target
  character's own artifacts;
- generic minimum set counts, including normal 4p + off-piece and 2p + 2p +
  off-piece templates;
- minimum total-stat constraints;
- deterministic top-K output, unique artifact ids, set/stat totals, and
  conversion of a candidate back to the existing `ArtifactBuildSnapshot`
  contract;
- upper-bound branch pruning, remaining-stat feasibility pruning, remaining-set
  feasibility pruning, optional lossy top-per-slot/top-per-set shortlisting,
  and a hard complete-build consideration cap;
- explicit `exact` versus `best_found` diagnostics. Candidate shortlisting or
  reaching the combination cap always prevents an absolute-optimum claim;
- an optional second-stage `FinalBuildEvaluator` callback. It reranks only the
  retained proxy candidate pool and is the intended seam for a later expensive
  GCSIM/DPS evaluator.

Main modules:

- `models.py` - immutable request, artifact, candidate, diagnostics, and report
  records;
- `repository.py` - read-only SQLite adapter and `ArtifactBuildSnapshot`
  bridge;
- `solver.py` - filtering, shortlisting, feasibility checks, branch-and-bound,
  top-K retention, and optional reranking;
- `__main__.py` - JSON diagnostic CLI.

## CLI

Default CLI scoring uses the project's existing Crit Value proxy
`2 * CRIT Rate + CRIT DMG`:

```powershell
python -m run_workspace.artifact_optimizer --top-k 10
```

Examples:

```powershell
python -m run_workspace.artifact_optimizer `
  --weight 20=2 --weight 22=1 `
  --minimum-stat 23=130 `
  --main-stat 3=6,23 `
  --require-set EmblemOfSeveredFate=4

python -m run_workspace.artifact_optimizer `
  --fixed 1=31 --exclude 92 --exclude-equipped `
  --target-character-id 10000090 --top-k 20
```

`--exact` disables lossy candidate shortlisting, but the combination cap still
applies. `--max-combinations 0` disables that cap and should be used only for a
small, already-filtered search space.

## Search Contract

The proxy objective is additive:

```text
score(build) = sum(raw artifact stat total[property_type] * weight[property_type])
```

The upper bound is therefore safe for this proxy: at each remaining slot the
solver adds the best still-available per-artifact proxy score. Minimum-stat and
set feasibility pruning use the maximum remaining contribution/available slot
count and cannot remove a feasible proxy build.

Shortlisting is intentionally different. It keeps the top global candidates
per slot plus top candidates per set, but it can remove a build that a later
nonlinear evaluator would prefer. Any such run is labelled `best_found`. The
second-stage evaluator also produces only a best result within its retained
proxy pool unless every feasible build was retained and reranked.

Set requirements enforce piece counts only. The additive proxy deliberately
does not inject 2p/4p effects into raw stat totals. A character damage formula
or GCSIM final evaluator must own set effects, weapon/character passives,
reactions, rotations, and enemy assumptions.

Unknown-set artifacts receive per-artifact fallback set keys, so unrelated
unknown rows can never accidentally activate a fake 2p/4p set.

## Real-Data Smoke

The local 2026-07-17 read-only smoke loaded 520 artifacts, grouped as
101/110/106/104/99 candidates across the five positions. The unrestricted raw
Cartesian space was 12,125,187,360 builds. With lossy shortlisting disabled and
a 200,000-build cap, the Crit Value proxy found its requested top five after
considering 10 complete builds and pruning 1,032 branches by the additive upper
bound. It did not hit the cap, retained the complete candidate pools, and
therefore reported an exact top-K for this additive proxy objective.

A real exact-pool 4p Emblem smoke returned only builds with at least four
`EmblemOfSeveredFate` pieces plus a valid off-piece. It considered 8 complete
builds, pruned 34,763 branches by set feasibility and 2,569 by the score upper
bound, and did not hit the 500,000-build cap.

These numbers describe one local account snapshot and are performance evidence,
not durable product thresholds or build recommendations.

Tests live in `tests/run_workspace/artifact_optimizer/` and cover deterministic
top-K ranking, 4p, 2p+2p, minimum stats, fixed/excluded/main-stat/equipment
filters, unique artifact ids, shortlisting diagnostics, combination caps,
second-stage reranking, 20 deterministic random exact-vs-brute-force
inventories, real SQLite loading, and the snapshot bridge.

## Upstream Genshin Optimizer Research

The official Genshin Optimizer repository is MIT-licensed. Its current solver
is a larger browser-worker system: it preprocesses formulas and artifact
ranges, prunes dominated/range-infeasible candidates, partitions set shapes,
uses branch-and-bound upper approximations, and coordinates shared top-N
thresholds across workers.

Primary references:

- repository/license: https://github.com/frzyc/genshin-optimizer
- Genshin solver coordinator:
  https://github.com/frzyc/genshin-optimizer/blob/master/libs/gi/solver/src/GOSolver/GOSolver.ts
- artifact range/order pruning and set-shape generation:
  https://github.com/frzyc/genshin-optimizer/blob/master/libs/gi/solver/src/common.ts
- branch splitting/upper-bound implementation:
  https://github.com/frzyc/genshin-optimizer/tree/master/libs/gi/solver/src/GOSolver/BNBSplitWorker
- GOOD import schema:
  https://github.com/frzyc/genshin-optimizer/blob/master/libs/gi/good/src/schemas/good-format.ts

GTT's implementation is independent Python code over the project's SQLite and
snapshot contracts. It uses the same broad solver ideas, not copied TypeScript
implementation. Importing GOOD directly is unnecessary for v0 because Artiscan
and HoYoLAB data are already normalized into SQLite.

## GCSIM Boundary

GCSIM's `-substatOptim` / `-substatOptimFull` optimize theoretical substat
allocation under config assumptions. They do not select five real account
artifact ids. Do not route the real-account search through those flags.

The intended expensive path is:

1. Build a broad real-artifact proxy pool with this optimizer.
2. Convert each retained candidate through `build_candidate_snapshot`.
3. Generate a character/team GCSIM config through existing normalized snapshot
   adapters.
4. Simulate only bounded top-M candidates with cancellation/progress and a
   persistent config/engine/scenario cache.
5. Rerank by sim DPS and present `best found`, never an unconditional absolute
   optimum.

Do not add this loop to the normal GCSIM Browser hot path yet. It needs an
explicit selected character/team, target/rotation, set-template policy,
bounded CPU budget, cancellation, and cache ownership.

## Next Backend Stages

1. Define a selected-character optimization request from typed TeamBuilder /
   DPS Dummy state: character, weapon, rotation, target, allowed set templates,
   main stats, stat floors, equipped policy, and CPU budget.
2. Add a cheap character-aware damage proxy (or formula adapter) so the first
   stage accounts for base stats and critical balance rather than only linear
   user weights.
3. Implement a bounded GCSIM final-evaluator batch service with progress,
   cancellation, result cache keys, and stale-input identity.
4. Add a backend-owned saved optimization request/result format only after the
   evaluator contract stabilizes.
5. Add UI in its own feature package later. Do not refactor `ui/app_shell.py`
   while the parallel PvP UI pass is active.
6. Multi-character/team allocation is a separate harder solver. Repeated
   single-character search with `excluded_artifact_ids` prevents reuse but is
   greedy and cannot claim a globally optimal team allocation.

## Non-Goals / Known Limits

- no UI, background worker, progress, cancellation, or persistent cache yet;
- no built-in GCSIM execution or damage-correctness claim;
- no automatic set-template recommendations or KQM/default-build data;
- no direct set-bonus, passive, reaction, enemy, or rotation evaluation in the
  additive proxy;
- no global four-character artifact allocation;
- no mutation/equip/save operation against account or build-preset state.
