# PvP draft setup and clocks

<!-- handoff-current: pvp-draft-runtime -->
Reviewed 2026-10-11, Worker4 source only. DEFAULT Abyss drafts now prepend
cost-compensation prebans to the supported source flow. Play displays both
character-price totals, difference, cost step, receiving seat and count. The
source step defaults to 60 for inspected Cup; zero disables compensation.
Play provides editable per-match step/turn/reserve and restart settings, an
explicit timer switch and optional auto expiry. Source/API scoring defaults
are authoritative per the user's decision; the regulation fills absent fields.
Overrides never rewrite deck snapshots and are labelled as custom settings.

Draft has a monotonic per-action clock and separate per-seat reserve. Accepted
actions reset turn time; only active-seat overtime consumes reserve. Pausing
freezes time and blocks card actions. Reserve exhaustion defaults to automatic
submission: an unselected ban is skipped; a pick uses a legal prepared immune
candidate or a random legal card. Manual expiry can be selected before Start.
The inspected client dispatches expiry actions; server enforcement is unknown.
Untimed, paused, expired, finished and disposed clocks stop their Qt timer.
Ticks update a retained clock surface without projecting/rebuilding the board.

Extra prebans are distinct actions, globally exclude their targets from later
picks and immunity, and contribute to ban totals/history. Admission checks
opponent roster capacity; a local viability guard preserves four distinct
shared preparation choices. Small overlapping rosters can still lose all legal
late picks through choices, including with compensation disabled; full future
pick feasibility belongs to the ordered legality task in the shared TODO.

113 focused fake-clock and synthetic setup→28-action→result compatibility checks
pass. Native acceptance is user-owned; no AppShell/CUA or live profile access.
The next source scope is other rule families/flows, then remaining legality.
No persisted rules cache or durable match snapshot was introduced.
<!-- /handoff-current -->

## Source evidence

11 October bounded anonymous GETs inspected the current
[creation form](https://abyss.darte.gg/assets/form-create-draft.component-Pf5DSGcS.js),
[price helper](https://abyss.darte.gg/assets/agent-list.component-BELlgTBD.js) and
[draft client](https://abyss.darte.gg/assets/index-DAHBbc_N.js). No JavaScript was
executed, authenticated rooms mutated, payloads saved or browser controlled.

DEFAULT compensation is floor(abs(character total difference)/prebanCostStep),
assigned to the cheaper seat and inserted before the source flow. The form's
normal-array price helper returns the character sum through a nullish expression;
its calculated bundle subtotal is not added. Compensation follows that inspected
sum, while existing deck budget/bundle reports retain their own behavior. This
is static client evidence, not a server calculation-parity claim. French uses a
different comparison and remains unsupported in this stage.

The client starts clocks after ready, resets pick time per action and retains
seat reserves. Its expiry callback calls the normal action dispatcher; bans
without a selected ID submit an empty target. Local replay represents this as
an explicit ban-only skip, spending the turn without banning a card. No client
forfeit callback was found. Stage expiry remains unsupported. Local
hot-seat Start supplies the readiness boundary; online ready/clock authority,
Undo and durable restart recovery remain later scopes.

## Runtime and verification

`draft_options.py` owns bounded immutable overrides; `abyss_match_rules.py`
owns price/extra-action/pair calculations. Controller state retains resolved
options/report. `draft_clock.py` is independent of Qt and accepts a fake monotonic
provider. `PvpWorkspace` owns its lifecycle and a lightweight clock signal;
`DraftClockWidget` owns presentation and retranslation. Clock/report objects
live until clearing/replacing/closing the match; no output or cache file is made.

Tests cover 0/59/60/119/120 boundaries, swapped/equal rosters, disabled/custom
settings, decimal/missing prices, bundle exclusion, insufficient targets,
duplicate/stale bans, all 28 accepted actions, preserved snapshots, per-seat
reserve/expiry/pause, rejected clicks, retranslation, no projections on ticks,
clear/quit cleanup, ban-skip replay, automatic expiry exactly once, exact source
milliseconds under auto-only overrides, custom restarts reaching final scoring
and retained-grid timing guards. Offscreen synthetic previews
use TemporaryDirectory ownership and immediate connected cleanup. Real user smoke:
Play → different-cost Abyss decks → inspect count → change/reset settings → Start
→ prebans → pause/resume → consume reserve → inspect skipped ban/automatic pick;
repeat with auto disabled and a manual action after expiry. Setup/clock previews
were inspected at 354px width in RU/EN/PT-BR and their temporary owner cleaned.
