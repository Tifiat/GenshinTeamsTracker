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
<!-- /handoff-current -->

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

AppShell is launched through `python -m ui.app_shell_smoke`. Its supervisor
waits for UI process exit before switching/deleting/resetting, then creates a
new process. Profile actions are unavailable during login/import/calculation.
OS locks coordinate supervisor/import/profile mutations. Never hot-swap a DB
constant while widgets or background workers can retain the previous context.

`profile_legacy.py` moves an explicit allowlist of old single-account files on
first upgrade. The move journal permits recovery after interruption. Sources
and targets are preflighted for containment and links/junctions; ambiguous
source+destination collisions fail closed. Migration creates no export/backup.

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
