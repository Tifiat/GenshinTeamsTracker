# Isolated preparation hypotheses — 2026-09-28

Owner: the optimizer Go design's isolated search-speed section; current stage is
owned by GP-3. User requested testing the new preparation hypotheses before any
production change, with inexpensive low-context agents doing the experiments.
`CODEX.md` owns that delegation policy. No Computer Use or installation.

## Inputs and quality policy

Reference is the previously measured `combined_narrow_reuse` research overlay,
not a fresh reduction in search depth. All new variants retain its search work,
queue/cycle policy and output limits. The user explicitly accepts the prior
Bloom rank7 difference of5.720792 DPS as player-negligible; it is not a blocker
or a blanket tolerance for larger future losses. Exact setup/arithmetic reuse
still compares complete results against THIS reference, not merely its winner.
The strict numerical Bloom receipt remains unchanged in the prior matrix folder.
Prior [hypotheses](../2026-09-27-search-hypotheses/README.md) and
[paired matrix](../2026-09-27-search-hypotheses/matrix/README.md) retain their
original variant scopes; their passes do not automatically accept this new one.

Saved Chasca request/captures: `all_sets-20260927-212145-2c1cb70d`.
The same hash/config/seed-bound provider drives the actual CLI coordinator;
unmatched schedule requests fail instead of silently launching another engine.
The saved engine must equal the active selected engine, artifact SHA is verified,
and the installed consumer/engine are checked unchanged after every replay.
No new GCSIM simulations; results are formula-only search evidence, not UI or
ordinary-finalist acceptance. Each JSON retains exact source/input identities.

## Hypotheses

- `inventory_views`: Build-owned immutable artifact vectors, shared by exact
  actor/ordered-coordinate keys across package views. References remain fresh;
  max16 entries/one million float words. Legality, weights and reservations are
  still computed for the current assignment. Synthetic sharing/identity/budget
  checks and existing domain tests run before replay.
- `prepared_replay`: constructor-owned query arrays and stable chronological
  indices, plus an immutable catalog set lookup. Arbitrary-query APIs retain
  their sorting fallback; VM/activation/task state is NOT reused. Source/rule
  tests and public-vs-prepared order controls run before replay.
- `region_binding`: bounded immutable arithmetic arena across different scalar
  effect vectors. Only changed descendants are re-reduced; canonical output is
  exported in the original binder's encounter order, preserving gradients and
  cross-owner dependence. General symbolic effects retain the existing binder.
  Bound250000 arena nodes/one million operand entries, with original-path fallback.
  This is not the rejected lazy whole-graph evaluation. Counters measure actual
  rebuild/reuse, and arithmetic/gradient/private-output/invalid-input/budget tests
  precede replay. The later `region_dense` variant removes export hash maps using
  bounded reusable generation-stamp arrays; branch/error-recovery tests also run.

## Initial measurements

Times are search only, excluding build and test startup. Small one-run changes
are not established improvements until combined/repeated; allocation counters
are not peak resident memory.

| Variant | Search, s | Exact reference output | Total allocation, GB |
| --- | ---: | --- | ---: |
| Reference | 85.166 | Reference49 rows/7 groups | 21.55 |
| Inventory views | 83.504 | Yes | 20.53 |
| Prepared replay | 84.255 | Yes | 20.80 |
| Region binding | 82.602 | Yes | 19.64 |
| Region binding with dense export | 81.134 | Yes | 19.48 |
| All three, dense export (`combined_preparation`) | 79.582 | Yes | 17.82 |
| Fresh reference after combination | 83.922 | Yes | 21.55 |

All initial variants retain217013 expansions and the same work-policy stop.
Region binding reuses32406229 of35792172 visited nodes, rebuilding3385943;
no reset, peak95414 arena nodes. Its binding time falls28.025→25.695s, but most
end-to-end cost remains. This does not justify a30s or multi-fold speed claim.
Prepared rule replay falls8.394→7.612s; other overlapping timing fields must
not be added together. Whole-job build+test time is not search time.

## Combined confirmation and interpretation

`combined-confirmation-attempt1.json` runs the combination then a fresh reference
sequentially in one managed job. Search79.582 vs83.922s is4.340s/5.17% less time.
The initial reference85.166s shows that small isolated gains should not be
overinterpreted: this is one saved Chasca case, not a statistical performance
study or a universal bound. All seven variant records across the five JSON
receipts share the full49-row fingerprint
`4b6f3f964c3e6de793f0b76366b18f859c19229522b4b83b501485950fb9a4cd`,
all alternative scores,217013 expansions and `neutral_cycle_budget` stop.
The runner's older `exact_rows` field compares against the installed historical
output; it is false for ALL these rows because the reference already includes
the prior narrower frontier. It must not be misread as a new preparation loss.

Exclusive binding instrumentation attributes the paired difference:

| Substage | Fresh reference, s | Combined, s |
| --- | ---: | ---: |
| Scalar effect binding, including cache lookup | 8.990 | 4.996 |
| Symbolic effect binding, including cache lookup | 18.634 | 18.707 |
| Total binding | 27.627 | 23.704 |
| Rule replay (inside rule preparation) | 8.073 | 7.686 |

No new pruning, approximate set uptime, changed formula or GCSIM calls explain
this gain. The scalar arena skips re-reduction for90.5% of visited original
nodes, but export and the general symbolic path still cost work. The symbolic
path must preserve artifact-dependent buffs/read roots and cannot be replaced
by one fixed number. Improving its cross-choice expression identity/binding is
a remaining untested opportunity, not a promise of proportional speedup; the
previously rejected lazy whole-graph representation is not a new hypothesis.
The present experiments do not establish the physical optimum or a30s search.

Cumulative allocation falls21.55→17.82GB (~17.3%); this is lifetime churn, NOT
simultaneous RAM. End-of-run reserved Go heap rises712.70→779.81MB (~67MB), so
memory is a tradeoff, not an unconditional reduction. HeapAlloc snapshots vary
with GC timing; no peak-RSS claim. Cache/node caps and original-path fallbacks
remain required for any integration. Accept the combined overlay as a named
candidate for paired-team gates, not as installed or whole-matrix acceptance.

Four new focused controls pass: shared bounded artifact-vector identity and
fresh references; prepared-vs-public event replay; scalar graph/gradient/private
output parity across120 vectors; ordered branches and failed-update recovery.
Existing formula controls run in every variant; preparation variants also run
the full copied domain and seteffects packages. All new exact setup variants
preserve physical IDs, set-group signatures and single-substitution output.

## Lifecycle

All copies, generated Go tests, binaries and runtime caches live in one
`managed_optimizer_experiment.py` scope and are cleaned before the next job.
The account, installed optimizer and active-engine pointer are not written.
Retain these compact JSON receipts and templates through integration review;
failed controls retain bounded log tails, never overwrite previous attempts.
Each new attempt uses a distinct receipt, at most three substantive attempts
per unresolved failure. No abandoned expanded source trees or capture copies
are retained. Rejected research templates can be retired after acceptance.
Managed cleanup removed81,364,533 +81,501,766 +116,841,967 +81,530,826
+109,373,601 disposable bytes across these five jobs. No experiment is still
running; compact receipts and reusable test templates remain.
