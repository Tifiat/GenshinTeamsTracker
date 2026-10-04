# Shared worker coordination

<!-- handoff-current: worker-coordination -->
Reviewed 2026-10-04. The sibling `GTT coordination` hub owns the single active
queue and registry for five checkouts. Worker1's existing main/master checkout
is coordinated by the new orchestrator chat named in the registry; the previous
optimizer chat is a read-only consultant. Each worker applies changes only in
its own checkout and owns its short shared status. No duplicate checkout entry,
shared technical-doc junction or second editable queue is used.

The user authorized reverse local synchronization of completed Workers1/3/4/5
from accepted master `ad0ea8c`; Worker2 and unfinished Theory/energy are excluded.
Owners first preserve dirty work; the user explicitly approved verified archives
for Worker3/4 overlays. They apply agreed local operations sequentially. The hub's
[technical event log](../../../GTT%20coordination/archive/GIT_EVENTS_20261004_REVERSE_SYNC.md)
owns before/after hashes, archive provenance and actual results. A plan or source
commit alone is not completed synchronization or product acceptance.

Master includes Worker1's saved stage, merged browser/display and PvP packages,
and only the scoped Worker5 import/profiles/icons/tooltips transfer. Older History
lineage is excluded. The [integration receipt](integration_receipts/2026-10-04_ready_workers.md)
owns target compatibility, overlapping test scopes, the old startup-fixture
escape/main-account migration and its guarded repair. Retain migrated data;
no before-hash exists. Manual multiaccount/import/hover/display, the old timer
width failure and Chasca numerical acceptance remain open. No app, real import
or numerical engine run belongs to this synchronization. Push requires separate
approval; Worker2's later role change remains unapplied.

The hub is a separate Obsidian vault. Its compact Git journal retains Mermaid
gitGraph and newest-first Worker1–5 lists, with full events linked in archives.
Slick Mermaid was added only to the hub from the user's installed reference;
personal settings were not changed. The user chose file-only setup and will
verify the enlargement button. No live render is claimed.
<!-- /handoff-current -->

## Local routing

Read the [hub rules](../../../GTT%20coordination/README.md),
[shared TODO](../../../GTT%20coordination/TODO.md) and your own status file from
the registry at task selection, scope changes and closeout. Read only the chosen
[backlog](../../../GTT%20coordination/BACKLOG.md) section. Existing `../../TODO.md`
and `WORK_BACKLOG.md` links still lead through local routers.
Read [Git rules](../../../GTT%20coordination/GIT_POLICY.md) before any Git write;
[Git journal](../../../GTT%20coordination/GIT_JOURNAL.md) separates facts/plans.

Each worker updates only its own file. Queue changes are proposals there until
Worker1 reconciles them. Subagents report to their parent. The coordinator does
not write another worker's checkout; workers connect their own instructions.
This protocol deliberately prevents concurrent editing of one shared TODO,
but is not an OS permission system or an automatic notification service.

## Validation and portability

Run the local handoff checker. Until another checkout receives the checker
changes, it may invoke the main checkout's `tools/check_handoffs.py` read-only
with `--root` naming its own root. The standalone coordination checker also
accepts `--root`; `--hub` selects an explicit known hub. Never validate a foreign
worker using the main root. During migration `--no-route-check` validates hub
structure only and is not full worker hookup acceptance.

The shared folder is machine-local and outside all Git worktrees. An external
clone can read versioned contracts but must report missing coordination instead
of inventing a second active queue. To relocate, move the hub deliberately,
update the relative link and registry together, and revalidate all roots.
Keep durable shared documents with regular project backups; this setup does not
create a GitHub repository or run unattended synchronization. Permanent original
queue records remain small and fixed, not an accumulating generated cache.
