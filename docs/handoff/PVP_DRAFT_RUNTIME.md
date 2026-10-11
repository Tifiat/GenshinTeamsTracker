# PvP draft setup and clocks

<!-- handoff-current: pvp-draft-runtime -->
Reviewed 2026-10-11, Worker4 source only. DEFAULT and FRENCH_COST drafts prepend
cost-compensation prebans to the supported 26/22-action source flows. Play displays both
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

Extra prebans globally exclude their targets and contribute to ban totals/history.
Admission and accepted/candidate actions now check future completion for flows
without remaining MIRROR. Matching reserves distinct normal targets and separate
per-seat protected/absolute copies; a complete witness is replayed. Preparation
branches use equivalent target classes. Only proven impossibility blocks an
action; exhausted budgets and remaining MIRROR are unknown. Automatic timed
modes admit future ban skips; manual/untimed modes reserve real ban targets.

113 focused fake-clock and synthetic setup→28-action→result compatibility checks
pass. Native acceptance is user-owned; no AppShell/CUA or live profile access.
Ascend MIRROR, Reverse and French flows now execute locally. Their actor-scoped
selection and signed capped-cost semantics are described below. Next: remaining
legality and future-pick feasibility for overlapping rosters.
No persisted rules cache or durable match snapshot was introduced. The user
chose a new draft before each game of a series; series implementation follows.
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
is static client evidence, not a server calculation-parity claim.

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

## Other source families — 11 October

The public [Ascend](https://abyss.darte.gg/api/abyss/draft_systems/6a8b487d875af1e871de37b8),
[Ascend Test](https://abyss.darte.gg/api/abyss/draft_systems/6a3812fb09e09ea6bc4f5bd6)
and [Reverse Cup](https://abyss.darte.gg/api/abyss/draft_systems/695948c967a24684c3d3118f)
flows were re-read anonymously. Each has 22 actions and three bans per seat:
Ascend selects seven PICK plus one MIRROR, Test eight PICK, Reverse six PICK
plus two IMMUNE. They have no shared preparation stage. Unsupported action/count
shapes and enabled Stage still fail explicitly.

The current draft selector uses each actor's own roster. MIRROR can select any
otherwise available own card, including an opponent PICK/ordinary IMMUNE
counterpart; no equal-price or opponent-copy prerequisite was found. It adds one
card to the actor, with no automatic counterpart assignment. A prior MIRROR stays
unavailable globally, except explicit absolute immunity. Preparation-protected
cards remain reserved. Reverse absolute immunity prevents bans and permits each
seat to use its own copy once; its ordinary IMMUNE is an own-roster selection.
These are local rules based on static client selectors/team projection, not a
server validation claim.

French snapshots retain the optional source method without changing old DEFAULT
snapshot hashes. `french_cost.py` groups by source variant, treating an absent
seat as zero; each left-minus-right price delta is clamped to ±costLimit unless
disableCostLimit exempts it. It sums signed deltas before taking the absolute
value. The sign chooses the cheaper seat. Cap zero is literal, including in the
inspected Test source, whose rows have no exemptions. Bundle adjustments do not
enter this comparison. Play displays an explanatory cap note.

118 focused test executions (111 distinct checks) passed across parsing, cap zero/exemptions/cancellation,
MIRROR sharing and uniqueness, source-shaped 22-action replay, disjoint-roster
admission, Reverse absolute immunity, real Play/clock/assignment dispatch and
the existing Free/Cup board and retained-grid regressions. Narrow French setup
and MIRROR order images were inspected; the disposable owner was cleaned.
An anonymous current-catalog check normalized and built all ten latest families:
seven 26-action DEFAULT, two 22-action DEFAULT and one 22-action FRENCH_COST.
This checks source projection/schedule compatibility, not real-roster legality.

## Future completion guard — 11 October

`draft_completion.py` is a bounded pure oracle. After preparation, exact matching
assigns remaining ordinary bans and PICK/IMMUNE slots to resources. Normal IDs
have global capacity one; protected/absolute IDs have one copy per eligible seat,
with protected cards restricted to IMMUNE. Before preparation, reducer-equivalent
classes reduce the choice search. Complete results carry a reducer-replayed
witness; failures prove no completion under that ban policy; unsupported future
MIRROR and the 2,000-state budget return unknown. Only impossible results reject
setup/actions. Controller memoizes candidate status within one immutable state;
accepting an action drops the prior state's memo. No files/caches are persisted.

59 distinct focused checks pass, including the former 16/24-overlap first-legal
stall, non-greedy witness, shared immunity, skipped-ban policy, setup rejection,
Play dispatch and existing Cup/Reverse/French/Free timing guards. Synthetic source
handler medians were 21.60ms for bans and 12.73ms for picks (not native/full-panel
acceptance); pure candidate checks peaked at 30.03ms across all 26 actions.

Zero upper draft bounds remain unknown: no public source validation was found;
the tier maxCost sentinel is a different field. Joker role/refinement exceptions
are prose-only; structured Joker identifiers/selection data remain unverified.
Bundle helper observations are scoped to team displays. Its separate creation/
preban caller was not reverified after a CDN 403; earlier scoped evidence is
preserved. These unresolved items keep the shared legality task open. No guessed
Joker marker or universal unlimited-bound interpretation was enabled.
