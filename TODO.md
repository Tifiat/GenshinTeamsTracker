# Shared task queue

<!-- coordination-router -->

Active assignments and priority are in the
[shared TODO](../GTT%20coordination/TODO.md). Read the
[hub rules](../GTT%20coordination/README.md) and
[Worker5 status](../GTT%20coordination/workers/worker5.md) at task selection,
scope changes and closeout. The
[shared backlog](../GTT%20coordination/BACKLOG.md) holds deferred areas.

This is a versioned router, not a second editable queue. Worker1 owns the shared
queue; Worker5 proposes changes in its own status file. Technical contracts and
checkpoints stay in this checkout. Branch implementation does not mean master
acceptance or authorize Git changes.

Connection and failure behavior: [COORDINATION](docs/handoff/COORDINATION.md).
If the local hub is missing, report it; do not reconstruct a private live queue.
The original queue is preserved in the hub's fixed migration archive.
