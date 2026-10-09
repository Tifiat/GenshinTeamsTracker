# Rotation import and editor corrections — 2026-10-09

Owner: [Readable rotation editor](../handoff/READABLE_ROTATION_EDITOR.md).
This receipt distinguishes backend, public native UI and remaining product work.

## Implemented and checked

- KQM HTTPS adapter, exact four-character membership, pagination and ranking:
  C+weapon; same C with other weapons; changed C. Missing metadata stays unknown.
  The API omits C0 in real summaries; an explicit zero in a unique parsed
  top-level character declaration is accepted as evidence. Refinement and sets
  display but do not rank. No account builds or credentials are sent; only four
  engine keys and query pagination. No persistent response cache is created.
- The current endpoint is `https://db.kqm.gg/api/db?q=<JSON>`, using `$and`
  equality filters for `summary.char_names`, `limit`, `skip` and `_id` sorting.
  A live probe rejected `$all`; the official client/site and actual response
  were checked rather than relying on the retired database contract.
  [Official integration](https://github.com/genshinsim/gcsim/blob/main/ui/packages/ui/src/features/dashboard/SharedByOthers.tsx).
- AST-based extraction preserves the program, including preceding functions,
  comments, branches and repeated actions. Source builds and combat setup are
  not applied. Current Browser setup is retained, with the existing bounded
  duration policy for the exact infinite/high-HP dummy case. The picker warns
  before loading. Unsupported syntax, special initial character params, no
  explicit active character and oversized composed source fail visibly.
- A modal picker loads in a background thread, previews alternatives and author
  prose separately, and replaces only the draft. Late results cannot overwrite
  changed Code/team/equipment/engine/draft. Same-engine draft replacement keeps
  undo. A failed draft creation leaves the picker and original code intact.
- Command categories remain visible above the command scroll. Character
  selection opens its actions in Commands with Back; Properties holds selected
  block options. Removing a condition keeps both branches in order. Simple
  loops and recognized independent counted loops unwrap; counter/control/scope
  dependencies reject without deleting contents. Character-window deletion
  still deletes its owned actions.

Focused validation: 58 tests across rotation database, import extraction,
editing, importer UI and editor UI passed; the 8 team-boundary tests also passed.
These cover ranking independent of order/R/stats, pagination/partial/errors,
C0 evidence versus comments/strings/params/duplicates, extraction and combined
size, draft undo, failed creation, source edit/revert and team A→B→A staleness,
tabs, action properties, unwrapping and character-owned deletion.

Live KQM lookup for Furina/Ororon/Bennett/Chasca returned three complete matches:
`RqbmgMp7HHjR`, `hcNnMTLjNjPW`, `p6g7qjMcLCwL`. All three extracted successfully
with the installed audited dialect and default Browser environment. A separate
Chiori/Layla/Ningguang/Rosaria one-row capped request returned `669KbbLdRCRz`
and correctly reported incomplete rather than an exhaustive result.

Native Computer Use opened a public Browser harness with the real installed
engine and public team context: clicked Find rotation, observed all three live
records and author description, opened readable preview, loaded the first
record into the editor, applied it and inspected the updated main Code and
Readable (six rotations, Ororon start, Furina every other rotation, Chasca
burst-ready branch). Persistent group selectors were visible in the editor.
The harness was closed and exited without errors. No source build/account
equipment was applied and no simulation was run. This is not a full AppShell
account acceptance; the earlier global empty-team report remains unresolved
outside the previously confirmed single-Varesa AppShell path.

The native probe exposed omitted C0; the final AST-based recovery was then
verified by focused tests and a bounded live backend response, not by a second
native screenshot. The public harness had no icon/equipment catalogue, so its
weapon/set labels used stable keys. Production uses existing Browser catalogues;
complete localized labels/icons and final row styling remain acceptance work.

## Input recording feasibility and Varesa

Windows supports keyboard/mouse observation through
[Raw Input](https://learn.microsoft.com/en-us/windows/win32/inputdev/about-raw-input),
message queue timestamps through
[GetMessageTime](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getmessagetime),
[global hotkeys](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey)
and a [topmost window](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowpos).
The inference from this boundary is limited: it captures input, not whether the
game accepted it, the active combat state or an executed attack. Repeated clicks
cannot be mapped one-for-one to successful attacks. gcsim itself waits for action
availability, so wall-clock key timing is not an execution trace.

Installed source `gcsim-v2.45.0-20260927011932`, upstream manifest v2.45.0,
`internal/characters/varesa/{skill,attack,charge,plunge,burst}.go`:
skill adds a five-second follow-up status; Attack delegates to ChargeAttack
while it is present. A subsequent aerial attack uses the distinct `high_plunge`
command. Burst chooses Volcano Kablam (30 energy) only with the required Apex
state; otherwise it takes the regular burst path. An illustrative program is
`varesa skill; varesa attack; varesa high_plunge; varesa burst;`, with the final
variant dependent on actual simulated state. This source review does not add
Varesa to the editor's admitted special-mechanics registry.
[Official Varesa reference](https://docs.gcsim.app/reference/characters/varesa/).

Feasible scope: assisted draft from timestamps, chosen team/starting character
and timeline bounds, with ambiguous clicks/state transitions confirmed by the
user. A reliable unattended game-to-gcsim converter was not established. No
capture implementation, global hook, game input injection or process-memory
access was added. No new recording dependency was installed.

## Remaining boundaries

Drag/drop, colored nested character mini-windows matching the user's sketch,
full personal-state explanations, simulation-derived waits and whole-database
language acceptance remain open. Import source timing/setup assumptions are
shown through the original-config tab and generic setup notice; dependency
analysis for different sets/weapons/targets is not claimed. Original author
descriptions are displayed; translation needs supported provider/settings and
credentials. MVP prioritizes imported rotations plus a fallback editor.

Local closeout intent: Readable execution owner will save only this verified
import/editor stage on local master under the standing user authorization in
CODEX.md and the shared Git policy. No push, branch transfer, engine change or
account mutation is included. The orchestrator-owned hub status is not edited
by this personally used execution chat.

## Follow-up: immediate main-window result

The user's follow-up supersedes the draft-only import path above. Find now
searches in the background and loads the first ranked supported candidate into
the main Code/Readable area as one undoable edit, selecting Readable. If the
first candidate cannot be extracted, the current source stays intact and the
reason is shown. Other rotations opens the retained alternatives separately;
explicit selection updates the same main area. A separate editor draft is
preserved, with its stale Apply blocked. Team/equipment/engine and main source
revision guards remain; explicit alternative selection prepares against current
combat settings. Empty/unresolved team, missing engine, network and extraction
failures are displayed beside Find, not in the offscreen run report.

Native investigation used the actual AppShell launched by PyCharm from this
checkout with `.venv/Scripts/python.exe ui/app_shell_smoke.py`. Its selected
team had four empty slots; the account panel reported an unimported profile.
Clicking Find had already written the team-required error below the viewport,
so it appeared to do nothing. This observation does not prove other reported
empty-team cases had the same cause. No team was inferred from the example code.

After a normal close, AppShell was restarted from the same checkout/interpreter
with `-m ui.app_shell_smoke`, through its normal profile supervisor. Native
clicks verified the empty-team message directly beneath Find. Four public
runtime test characters were then selected through the standard Browser cards:
Furina/Ororon/Bennett/Chasca, C0, without selecting equipment. Find returned the
three live KQM records named above and immediately displayed the first program
in main Readable (six rotations), without opening a draft or picker. Other
rotations showed all three rows and original author descriptions. Selecting
the second row and Choose this rotation closed the picker and changed main
Readable to four rotations; Code showed the same imported program and the
retained Browser combat options. The window was left on Readable with this
public test team. No account import, equipment save or battle simulation ran.
The pre-existing wide virtual-card layout still requires horizontal scrolling
on this compact window; layout redesign remains separate.

Review also found the embedded PvP Browser missing its team provider. It now
uses the owning seat controller and selected team; four scoped PvP tests cover
the connection, team switching, seat separation and unchanged source profiles.
This path was tested with controlled fixtures, not native PvP interaction.
Nine importer UI and 24 editor UI checks passed, covering immediate main import,
alternatives, undo, draft preservation, source/team staleness and visible errors.
The earlier backend/live engine checks above remain scoped historical evidence.
