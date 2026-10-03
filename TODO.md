# Shared task queue

<!-- coordination-router -->

Active assignments and priority are in the
[shared TODO](../GTT%20coordination/TODO.md). Read the
[hub rules](../GTT%20coordination/README.md) and your own worker status before
choosing work, after scope changes and at closeout. The
[shared backlog](../GTT%20coordination/BACKLOG.md) holds deferred areas.

This is a versioned router, not a second editable queue. Worker1 owns the shared
queue; other workers propose changes in their own status file. Technical
contracts and checkpoints stay in their corresponding checkout. Implementation
in one branch is not acceptance on master or authorization for Git changes.

Connection and failure behavior: `docs/handoff/COORDINATION.md`.
If the local hub is missing, report it; do not reconstruct a private live queue.
The original queue is preserved in the hub's fixed migration archive.
