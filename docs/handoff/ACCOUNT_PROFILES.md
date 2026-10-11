# Saved accounts and application defaults

<!-- handoff-current: account-profiles -->
Reviewed 2026-10-04. Local master contains Worker5's account registry,
isolated storage roots, optional in-game profile metadata, an AppShell account
selector, separate Login/Import actions, per-account deletion and full reset.
Profile changes restart the UI process so module defaults and memory caches
cannot retain the previous account. Worker5's combined account/lifecycle/settings/Qt
suite ran 270 tests: 269 passed, one host symlink test skipped; deterministic
link/reparse protection checks passed. Native AppShell checks verified clean
startup, Login hint, separate Import, equipment ON, create/switch drafts,
dropdown red crosses and Clear all. Worker5 data/preferences were reset as
requested; that reset check ended with one empty login draft and zero imports.
The later read-only tooltip closeout sees one registered, active imported
profile; that user import was not observed/repeated by this agent.
Five managed-browser lifetime tests passed; a real login-window launch held
the operation lock as required. The later native browser inspection was stopped
by the tool's URL-verification safeguard. The login overlay now reuses the same
explicit Import instruction as the login dialog. The combined adapted
login/profile/tooltip suite passed 37 controlled tests; visible acceptance of
these last edits is reserved for the user's manual smoke check.
Multiple real-account imports and actual game-avatar rendering remain
unverified. The user-authorized local transfer is saved with controlled target
checks; [integration evidence](integration_receipts/2026-10-04_ready_workers.md)
also records the main legacy migration caused by an old startup test and its
isolation repair. This is not a real multiaccount-import acceptance.
Push remains unauthorized. [Transfer scope](WORKER5_TRANSFER_PACKAGE.md) owns
the package/dependency boundary; the older isolated importer candidate is separate.
2026-10-06: the user-requested startup hotfix prevents recreated legacy GCSIM
outputs from triggering migration
into a populated selected profile. [Target evidence](integration_receipts/startup_legacy_outputs_20261006.json)
records 21 focused controls (20 pass, one host symlink skip), both real launcher
paths and repeated supervised AppShell startup with normal window close/exit0.
Registry, account DB and legacy-run hashes remain identical. No import, optimizer
run or Computer Use; broader multiaccount/button acceptance remains separate.
2026-10-09: native PyCharm traceback reproduced another startup collision:
a recreated legacy SQLite schema had no rows, but a populated target existed.
Startup now preserves this empty schema and its sidecars separately. The
profile suite ran 37 tests (36 passed, one host skip); ordinary supervised AppShell
opened successfully and was observed through Computer Use. Account metadata,
import and editor interactions were not changed/tested in that native check.
<!-- /handoff-current -->

The [7 October integration audit](performance_measurements/2026-10-07_main_startup_and_merge_audit.md)
reproduced an absolute-image-path guard omission in UI asset adapters. The
common resolver enforces/remaps managed profile paths, but these absolute
branches skip it. The issue remains open; no real foreign profile was accessed.

## Ownership and switching

`run_workspace/account_profiles.py` owns `data/profiles/registry.json`, its
atomic writes and `data/profiles/<opaque UUID>/` roots. UID/server identifies a
game account; browser credentials never enter the registry. A newly created
draft holds an isolated browser session but is not an imported account. The
registry has no account-count limit. Duplicate UID/server imports are rejected
before source publication and offer switching to the existing account.

`profile_context.py` selects an immutable `ACCOUNT_ROOT` before domain imports.
The code checkout, engines and public reference caches retain `PROJECT_ROOT`.
Account SQLite (including presets and equipment), source JSON, account images,
History, PvP and account-derived simulation outputs live under ACCOUNT_ROOT.
Portable image paths stay account-relative. Offline ZIP imports restore into a
new root before activation; an error preserves the active account.

Absolute UI image paths also pass through `account_asset_path`, including
browser/weapon adapters and selection normalization: migrated legacy paths remap
to the active profile, another managed profile is rejected, and external package
files remain valid. Image candidates must be files. The 11 October Worker4
[card receipt](CHARACTER_CARD_ASSETS.md#portrait-weapon-and-filter-follow-up--2026-10-11)
owns synthetic regression evidence; real multi-account acceptance stays open.

AppShell is launched through `python -m ui.app_shell_smoke`. Its supervisor
waits for UI process exit before switching/deleting/resetting, then creates a
new process. Profile actions are unavailable during login/import/calculation.
OS locks coordinate supervisor/import/profile mutations. Never hot-swap a DB
constant while widgets or background workers can retain the previous context.

`profile_legacy.py` moves an explicit allowlist of old single-account files on
first upgrade. The move journal permits recovery after interruption. Sources
and targets are preflighted for containment and links/junctions; ambiguous
source+destination collisions fail closed. Migration creates no export/backup.
`startup_legacy_migration_needed` distinguishes derived-only simulation/cache
outputs from primary account payload. With an already populated selected
profile, orphan outputs remain separately preserved and produce a diagnostic
log, not a move/delete or fatal Python warning. A pending journal always retains
recovery, primary legacy data/DB sidecars retain collision/binding checks, and
an empty first upgrade retains migration. The broad legacy predicate and
explicit clear/migrate APIs are unchanged. No account identity is inferred
from orphan run files or account rows.

The startup-only exception also recognizes a schema-only legacy SQLite database
when the selected profile already contains primary data. Immutable read-only
inspection requires integrity and no rows in any table, including internal
tables; database/sidecar identities and modification times must remain stable.
Nonempty WAL, a rollback journal, unsafe paths, malformed databases or any other
primary legacy file retain collision checks. All files remain in place, and
empty first-upgrade migration and explicit reset/migration remain unchanged.

## Metadata and login

HoYoLAB Chronicle's selected role supplies nickname, Adventure Rank and
`game_head_icon`, which is the in-game avatar. The community `AvatarUrl` must
never be substituted. Metadata and avatar fetch failures are optional and must
not roll back a committed equipment import. Missing fields display a dash;
World Level is not inferred from Adventure Rank. Any additional external
source requires an explicit product decision and provenance.

Login only opens authentication. A dismissible explanation tells the user to
close the browser, then press Import data in Settings. Import/Update remains a
separate action. Credentials and the browser profile belong to the selected
account and are excluded from portable archives.
Closing a standalone login never starts an import. Import/image refresh and
profile export are also guarded in their handlers while a managed login is
running. The Worker3 candidate's automatic continuation belonged to its older
combined button and was not adopted into this separate-action contract.
`hoyolab_export.login_session` holds the profile-operation lease for the managed
browser's lifetime, independently of the UI process. Its startup handshake
confirms the lease/browser before the UI begins polling. An unrelated externally
launched browser is outside this managed-lifetime guarantee.

## Defaults and destructive cleanup

`run_workspace/settings_defaults.py` is the **only owner of default values**.
Every future persistent setting, checkbox and “don't show again” flag must be
registered there; UI call-site fallbacks must not define competing defaults.
Dynamic defaults receive the saved settings context explicitly. First-launch
equipment import is enabled, while a saved false value remains false.

PvP color defaults follow the [selection color contract](UI_WORK_RULES.md#selection-color-contract).
Missing keys use the current pair; saved colors remain explicit choices, including
values equal to an older factory pair. The PvP Settings **По умолчанию** action
resets only the two color keys and refreshes both swatches/signals. It preserves
unrelated preferences. No hex-matching migration or second defaults store exists.

Deleting one account removes its entire owned root, including browser login,
DB, History, presets, images and derived outputs. Other accounts and global
preferences remain. Zero imported accounts shows the clean Login/Import flow.
Clear all removes every profile and legacy account data, then atomically resets
`settings.json` to `{}`. This also clears obsolete/unrecognized suppression
keys. A fresh UI process resolves all settings from the central defaults.

Saved profiles are durable user-owned data retained until explicit deletion,
an exception to bounded cache retention. Derived files keep their existing
bounded cleaners inside each root. Account avatar has one replaceable cache
file. Registry lock files are fixed-size OS-owned handles. Supervisor action
files are single-use, deleted after application and on normal exit. Migration
journals are deleted when the move completes. All runtime files stay ignored.
Deletion refuses links/junctions and propagates errors instead of claiming a
successful clean state after partial failure.

For an explicitly requested cleanup of orphan **project-root** `data/gcsim/runs`,
`tools/cleanup_legacy_gcsim_runs.ps1` previews by default; `-Apply` sends only
that fixed directory to the Windows Recycle Bin, with no permanent-delete
fallback or extra backup/log. It never clears profile outputs or other caches.
Apply holds the supervisor, operation and registry leases, rechecks containment
and links, and refuses a missing selected profile DB, root legacy DB/sidecars
or any physical profile's pending migration journal. Temporary-tree tests in
`tests/tools/test_cleanup_legacy_gcsim_runs.py` use a mocked recycle boundary;
they do not delete live output or certify an actual Windows Recycle Bin action.
