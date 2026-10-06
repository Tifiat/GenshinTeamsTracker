# Shared worker coordination

<!-- handoff-current: worker-coordination -->
Reviewed 2026-10-06. The sibling `GTT coordination` hub owns the single active
queue and registry for five checkouts. Worker1's existing main/master checkout
is coordinated by the new orchestrator chat named in the registry; the previous
optimizer chat is a read-only consultant. Each worker applies changes only in
its own checkout and owns its short shared status. No duplicate checkout entry,
shared technical-doc junction or second editable queue is used.

The user authorized reviewed local integration and one accepted product/runtime
version in main and completed Workers3/4/5. Worker2 and detached schedule-repair
overlays are excluded. Owners preserve changes and apply agreed branch/runtime
operations sequentially. The hub's
[current event log](../../../GTT%20coordination/archive/GIT_EVENTS_20261006_INTEGRATION.md)
owns source/target hashes, exact transfer scope and actual results; the
[4 October archive](../../../GTT%20coordination/archive/GIT_EVENTS_20261004_REVERSE_SYNC.md)
retains original preservation and reverse-sync evidence. Git ancestry alone
does not establish equal working product code or ignored runtime binaries.

Master includes Worker1's saved stage, merged browser/display and PvP packages,
and scoped Worker5 import/profiles/icons/tooltips and reviewed transparent History
follow-up. Worker-specific routing and unfinished optimizer/Theory remain
excluded from target transfers. The [prior integration receipt](integration_receipts/2026-10-04_ready_workers.md)
owns target compatibility, overlapping test scopes, the old startup-fixture
escape/main-account migration and its guarded repair. Retain migrated data;
no before-hash exists. Manual multiaccount/import/hover/display, the old timer
width failure and Chasca numerical acceptance remain open. Startup orphan-output
correction and the future website-backed PvP direction are saved separately.
Runtime synchronization uses accepted fingerprinted bundles, existing store
transactions, compatibility checks and retained consumer rollback; no account
data is copied. The 6 October guarded startup probe measured legacy readiness
at about 1.39 seconds and AppShell at about 4 seconds in disposable synthetic
profiles; `ui.app_shell` import dominated the AppShell path. The
[dated measurement](performance_measurements/2026-10-06_guarded_startup_profile.md)
is diagnosis, not physical UI acceptance or a cross-device promise. Computer
Use, live cleanup and push are outside this task; Worker2's later adoption
needs its own preservation/compatibility gate.

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
