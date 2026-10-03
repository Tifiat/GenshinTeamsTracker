# Shared worker coordination

<!-- handoff-current: worker-coordination -->
Reviewed 2026-10-04. Worker5 is connected to the sibling `GTT coordination` hub
through `coordination.json`. The hub owns the active queue and area backlog.
Worker1 owns common queue, registry, decisions and migration records; Worker5
writes only its linked status file. Technical contracts and dated evidence remain
in this branch.

The original local TODO and backlog match the main documents preserved in
[migration archive](../../../GTT%20coordination/archive/MIGRATION.md) by SHA256;
no unique Worker5 queue content was lost.
Local TODO and WORK_BACKLOG are routers. Branch work, review readiness and
acceptance on master stay separate. A registry entry or document check does
not prove product or user-path acceptance.

The migration grants no app, account, engine or Git authorization. The current
application launch is separately authorized by the user in the History chat.
No commits, pushes, merges or transfers were requested or performed here.
<!-- /handoff-current -->

## Local routing

Read [hub rules](../../../GTT%20coordination/README.md),
[shared TODO](../../../GTT%20coordination/TODO.md) and
[Worker5 status](../../../GTT%20coordination/workers/worker5.md) at task selection,
scope changes and closeout. Read only the selected
[backlog](../../../GTT%20coordination/BACKLOG.md) area, then this checkout's
technical owner. Existing local TODO/backlog links remain valid routers.

Only Worker1 reconciles shared queue changes. Worker5 records proposals in its
own status and preserves other workers' files. Subagents report to their parent.
Coordination does not authorize unrelated implementation or create a shared
technical docs junction, automatic notification or cross-worker acceptance.

## Validation and portability

Use the local handoff checker when it understands coordination. Until then,
invoke the main checkout's `tools/check_handoffs.py` read-only with `--root`
naming `C:/Users/user/Desktop/worker5 GTT`. This checks local handoffs and the hub,
without launching applications or certifying gameplay or Git ancestry.

If the hub is missing, report it before choosing a new shared task; do not
recreate a private live queue or regenerate the hub from an old checkout.
Relocation requires updating the relative link and registry together and
revalidating paths. The small fixed migration archive preserves original queues;
new numerical or UI evidence stays versioned with its owning branch. The hub
is machine-local, outside Git worktrees, and does not imply GitHub backup.
