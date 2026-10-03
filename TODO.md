# Shared task queue

<!-- coordination-router -->

Active assignments and priority are in the
[shared TODO](../GTT%20coordination/TODO.md). Read the
[hub rules](../GTT%20coordination/README.md) and
[Worker3 status](../GTT%20coordination/workers/worker3.md) before choosing work,
after scope changes and at closeout. The
[shared backlog](../GTT%20coordination/BACKLOG.md) holds deferred areas.

This is a versioned router, not a second editable queue. Worker1 owns the shared
queue; Worker3 proposes changes in its own status file. Technical contracts,
checkpoints and evidence stay in this checkout. Branch implementation is not
acceptance on master or authorization for Git changes.

Connection and failure behavior: [COORDINATION](docs/handoff/COORDINATION.md).
If the local hub is missing, report it; do not recreate a private live queue.
The original TODO and Worker3 backlog are preserved in the hub's
[fixed migration archive](../GTT%20coordination/archive/MIGRATION.md).
