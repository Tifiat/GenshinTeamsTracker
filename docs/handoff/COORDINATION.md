# Shared worker coordination

<!-- handoff-current: worker-coordination -->
Reviewed 2026-10-04. Worker4 (`codex/pvp-providers`) is connected through
`coordination.json` to the sibling `GTT coordination` hub. Worker1 owns shared
TODO/BACKLOG/decisions/registry; Worker4 writes only its own status. Technical
contracts, implementation and evidence remain in this checkout.

The local TODO and WORK_BACKLOG are routers. Their pre-migration content matches
the fixed main TODO and Worker4 backlog migration records, including the shared
neutral-portrait decision. The additional chosen artifact/build inclusion rule
and current PvP progress are recorded in `PVP_PROFILE_PACKAGE.md` and Worker4's
hub status for reconciliation.

Branch work, ready-for-review and accepted-on-master are separate states.
The user approved automatic verified local commits of this worker's own completed
stages on 2026-10-04. Transfers between branches, push and other Git writes need
separate explicit authorization. This grants no new product work. Application
restart, Computer Use and account writes remain outside migration authorization;
the user's smoke checks remain user-owned. Git journal/Obsidian ownership stays
with Worker1; the main-folder master/orchestrator transition remains a plan.
<!-- /handoff-current -->

## Read and update

At task selection, scope changes and closeout, read the
[hub rules](../../../GTT%20coordination/README.md),
[shared TODO](../../../GTT%20coordination/TODO.md) and
[own status](../../../GTT%20coordination/workers/worker4.md). Read only the
selected [backlog](../../../GTT%20coordination/BACKLOG.md) section, then its
technical owner here. Reread your own status immediately before editing with
`apply_patch`. Put queue proposals there; do not edit another worker's status
or common queue. Subagents report to their parent.

Before any Git write, read the [Git policy](../../../GTT%20coordination/GIT_POLICY.md).
Commit only a reviewed, verified completed stage on your own branch, preserving
other index/worktree changes. Record time, operation, branch, full parent/result
hashes, checks and remaining gates in your status. Keep each event until Worker1
collects it into the [shared Git journal](../../../GTT%20coordination/GIT_JOURNAL.md).
Only Worker1 edits that journal. No branch switch/rename/transfer or publication
is implied by local commit authorization.

The hub is local and outside Git worktrees. Missing coordination is reported
when selecting a shared task; do not rebuild a private queue from an old clone.
Relocation requires a deliberate link/registry update by their owners. Preserve
the fixed [migration records](../../../GTT%20coordination/archive/MIGRATION.md)
and back up shared documents with normal project documents.

## Validation

The main checkout has a coordination-aware read-only checker. Until this
checkout receives it, run that checker with this root explicitly:

```powershell
& 'C:/Users/user/Desktop/GenshinTeamsTracker/.venv/Scripts/python.exe' 'C:/Users/user/Desktop/GenshinTeamsTracker/tools/check_handoffs.py' --root 'C:/Users/user/Desktop/worker4 GTT'
```

This checks structure/routing and the shared hub; it does not prove gameplay,
Git ancestry or UI acceptance, and does not modify another checkout. No shared
technical-doc junction or unattended synchronization is used.
