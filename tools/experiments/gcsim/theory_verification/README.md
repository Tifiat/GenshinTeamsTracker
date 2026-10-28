# Theory point-verification bench

Owner and dated results:
[`2026-10-03-theory-verification`](../../../../docs/optimizer-evidence/2026-10-03-theory-verification/README.md).
This is a research caller, never a production fallback. Retain sources/cases
until an accepted Theory verification stage absorbs their useful guards; then
retire the bench and consolidate its minimal receipts.

`render.py` validates one exact package/main/substat vector and replaces only
artifact rows. It reuses the common artifact investment rules, preserves
declaration/rotation order and requires the runner's active set registry.
Fractional max-roll equivalents are explicitly a relaxation, not real pieces.

`run_case.py` prepares the selected saved virtual team through the real Theory
input builder, then calls the bound active GCSIM directly. It does not execute
`optimize-theory`, discover new candidates, mutate the matrix DB variant or
install another engine. One invocation accepts one case, at most two fixed-seed
captures and one ordinary128/500 simulation. There is no matrix loop or retry.

Run only inside the worker using its read-only dependency environment:

```text
python -B tools/managed_optimizer_experiment.py --timeout 240 -- python -B tools/experiments/gcsim/theory_verification/run_case.py --case tools/experiments/gcsim/theory_verification/cases/lunar_charged_saved_rank1.json --receipt <new-worker-local-receipt.json>
```

Set `PYTHONDONTWRITEBYTECODE=1`; optional `--prepare-only` performs zero GCSIM
calls. Existing receipt paths are refused. The current pilot pins the audited
branch/HEAD, active engine, saved profile/rotation hashes and reference receipt.
Rebinding a future case requires recording its new identities; do not weaken
these gates merely to rerun old input under a changed setup.

The 14 saved matrix teams now have separate case files. A historical
`candidate_source` adds `run_id` to select one successful Theory row/rank in the
hash-pinned September 19 matrix fixture. The current manifest team, ordered
characters and rotation path must agree. That fixture omits original profile
and rotation hashes and uses an older engine; its prediction is a historical
reference, even if fresh damage numerically matches. Receipts retain this
provenance. Only an audited source with matching input and active engine
bindings can receive a same-engine point-response classification; inline
formula values remain unbound references. Matrix rows are released one at a
time after receipt review, never by an unattended loop. The existing October 3
Lunar-Charged point is reused rather than simulated again.

All configs, large members, ordinary outputs and process temp/cache belong to
one managed job. The outer runner deletes the job, including failed calls.
The small receipt retains exact input config/vector, hashes, per-seed damage,
per-actor/channel counts and ordinary mean/standard error. After runner exit,
the caller records measured deleted bytes and checks that the job is absent.
Orphan residue blocks the next allocation. The managed runner's existing
deletion/preservation guards and the renderer/runner tests cover that lifecycle.

When ordinary output provides them, receipts also retain duration mean/SD in
seconds and reaction-event mean/SD per declared actor. Engine array indices are
bound to the exact config declaration order; omitted proto zero fields become
zero. These event counts do not identify a particular attack tag or prove the
cause of a fixed-panel/ordinary discrepancy.

## New user cases

Copy a case description with a new ID and freeze the same team profiles,
weapon/refinement, rotation, target and energy policy. Use either a hash-bound
`candidate_source` receipt/rank or an inline `candidate`, never both. Inline
candidates use the exact existing Theory shape:

- `packages`: one wearer row each, no bonus (`sets: null`), single2p, 4p or
  distinct2+2, with active `set_uid` values;
- `allocations`: the five named `main_stats`, substat `stat_key`, `roll_units`,
  `stat_value`, and consistent `spent_roll_units`/`unspent_roll_units` per wearer;
- optional `formula_dps` only when a bound formula actually scored that point.

Natural-language accents are translated by the assistant into an explicit
case, with a visible distinction between fixed requirements, minimum thresholds
and preferred starts. The runner does not guess gameplay rules or turn a vague
preference into an undisclosed hard constraint. The current bench replays a
frozen vector; independent optimization under each user package belongs to the
separate hypothesis stage and is not implemented by this renderer.

A same-vector set swap isolates an effect response. A fair best-build comparison
requires reoptimization of each package under identical investment rules,
including the optimized no-bonus competitor. Ordinary GCSIM checks a selected
point; it cannot establish that all other builds are weaker. Formula/seed
residuals, observed schedule changes and ordinary sampling noise are reported
separately. Completion of the runner is not a response PASS.
