# Shared worker coordination

<!-- handoff-current: worker-coordination -->
Reviewed 2026-10-04. Worker3's checkout on branch `worker3` is connected to the
sibling `GTT coordination` hub through `coordination.json`, schema
`gtt_coordination_link_v1`, hub `../GTT coordination`. Worker1 owns shared
TODO/BACKLOG/registry/decisions; Worker3 updates only its
[own status](../../../GTT%20coordination/workers/worker3.md).
Versioned technical owners and dated evidence remain in this checkout.

Root TODO and WORK_BACKLOG are short routers without independent task lists.
Before replacement, both original files matched their migration archives
byte-for-byte: the main TODO and Worker3 backlog, including first-open and
applied-preset user acceptance gates. Those gates are also in the shared queue.
No additional task delta was discovered. Original documentary evidence remains
in the hub's fixed archive; no new source or data snapshot is created.

The browser implementation and recorded automated gates remain branch work;
physical UI acceptance and integration into master are not declared. The user
approved automatic verified local commits of each worker's own completed stages
on 2026-10-04; [Git policy](../../../GTT%20coordination/GIT_POLICY.md) must be reread
before any Git write. Cross-branch transfers, push and other Git mutations need
separate explicit user confirmation. This documentation scope grants no new
product work, app launch, Computer Use, engine or account write.
The main handoff checker with the explicit Worker3 root passed on 2026-10-04.
Migration checks verify documents/routing only; product tests were not rerun.
<!-- /handoff-current -->

## Reading and ownership

At task selection, scope changes and closeout, read the
[hub rules](../../../GTT%20coordination/README.md),
[shared TODO](../../../GTT%20coordination/TODO.md) and
[own status](../../../GTT%20coordination/workers/worker3.md). Read only the chosen
[backlog](../../../GTT%20coordination/BACKLOG.md) section, then the technical owner
in this checkout. Existing TODO/WORK_BACKLOG links continue through the routers.

Reread the own status immediately before editing it with `apply_patch`. Report
new tasks/decisions as proposals there for Worker1; do not edit common queue,
registry, decisions, another worker's status or another checkout. Subagents
report to their parent. Integration uses `branch_work`, `ready_for_review` or
`accepted_on_master` as appropriate; the last requires accepted commit evidence.
An assignment or a passed structural check is not implementation authorization
or user-path acceptance.

Worker3 records its own Git events in its status: time, branch, full parent/result
hashes, checks and unverified limits. Retain them until Worker1 collects them in
the [shared journal](../../../GTT%20coordination/GIT_JOURNAL.md); only Worker1
edits that journal. A documentation commit is separate from unaccepted product
work. The main-folder master/orchestrator and later Worker2 optimizer roles
remain future plans until explicitly approved and performed.

## Validation and portability

The local older checker does not yet understand external hub links. Use the
main checkout's checker read-only with the explicit worker root:

```powershell
& 'C:/Users/user/Desktop/GenshinTeamsTracker/.venv/Scripts/python.exe' 'C:/Users/user/Desktop/GenshinTeamsTracker/tools/check_handoffs.py' --root 'C:/Users/user/Desktop/worker3 GTT'
```

It checks local handoffs and shared coordination without launching the app or
certifying gameplay/Git ancestry. `--no-route-check` is not full hookup acceptance.
No main-checkout file or dependency environment is modified by this migration.

The hub is local and outside Git worktrees; no shared docs junction, automatic
notification or GitHub synchronization is installed. Report a missing hub and
do not reconstruct it from an old checkout. Deliberate relocation requires a
matching link/registry update by their owners and revalidation. Preserve the
[fixed migration records](../../../GTT%20coordination/archive/MIGRATION.md) with
normal project-document backups; new technical evidence stays with its branch.
