# Shared backlog routing

<!-- coordination-router -->

Deferred scopes are in the
[shared backlog](../../../GTT%20coordination/BACKLOG.md); active assignments are
in the [shared TODO](../../../GTT%20coordination/TODO.md). Read only the selected
area, then its contract and current checkpoint in your own checkout.

This file is a versioned router, not a duplicate queue. Worker1 owns the shared
backlog; workers record proposed changes in their own status file. Migration
preserved original lists and worker-specific deltas. Missing hub is reported,
not silently replaced with a private list. See `COORDINATION.md` for ownership,
validation and relocation rules. No unrelated implementation is authorized by
this backlog.
