# Shared worker coordination

<!-- handoff-current: worker-coordination -->
Reviewed 2026-10-04. The local sibling hub `GTT coordination` owns active task
order and the area backlog for five registered checkouts. Worker1 owns shared
queue/decisions/registry files; each worker owns its own short status file.
Local `coordination.json` names the hub relative to the checkout. No junction or
shared technical `docs` directory is used.

Versioned contracts, current subsystem checkpoints, engine identities and dated
evidence remain in their branch. Branch work, ready-for-review and accepted-on-
master are distinct. A registry entry or a notification is not user-path or
gameplay acceptance. Existing energy work is deferred to a joint Theory stage.

The migration preserves five original queue/backlog documents with hashes,
including Theory and Worker3/Worker4 deltas. Root TODO and WORK_BACKLOG are
routers, not duplicate editable queues. New task selection and closeout read
the shared queue and own status. Missing hub is reported; never regenerate it
from an old checkout. Checkouts outside the registry require explicit admission.

`tools/check_coordination.py` is read-only and checks routing, ownership, paths,
links and declared status, not Git ancestry or acceptance. Handoff closeout
also checks local structural and live-manifest facts. Workers receive migration
instructions and applied their own routing edits, preserving dirty files. All
five explicit-root handoff checks pass; 36 focused doc checks pass with one
Windows symlink-creation skip (escape tests also run independently). No
app restart, engine or account write is part of this setup.
The user's additional Git-policy/Obsidian request now has separate approved rules
and a factual local-refs journal in the hub. On 2026-10-04 the user authorized
local integration of ready branches. The clean main folder switched to master
and fast-forwarded Worker1's saved stage. Worker3's target merge passes 95 safe
equipment/browser/settings/scaling tests; Worker4 integration remains next.
The [integration receipt](integration_receipts/2026-10-04_ready_workers.md)
owns source pins, conflict handling and remaining acceptance.
Worker2 still owns Theory; its later role change is not applied.
Push still requires separate approval. Worker events are retained until collected
in the common journal; branch integration does not close numerical or visible
user acceptance gates.
The hub itself can be
opened as a separate Obsidian vault; no vault junction, plugin/settings change
or physical render is claimed.
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
