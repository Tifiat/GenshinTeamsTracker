# Shared backlog routing

<!-- coordination-router -->

Deferred scopes are in the
[shared backlog](../../../GTT%20coordination/BACKLOG.md); active assignments are
in the [shared TODO](../../../GTT%20coordination/TODO.md). Read only the selected
area, then its contract and current checkpoint in this checkout.

This file is a versioned router, not a duplicate queue. Worker1 owns the shared
backlog; Worker5 records proposed changes in
[its own status](../../../GTT%20coordination/workers/worker5.md). Migration
preserved original lists and worker-specific deltas. Missing hub is reported,
not replaced by a private list. See [COORDINATION](COORDINATION.md) for ownership,
validation and relocation rules. No unrelated implementation is authorized by
this backlog.
