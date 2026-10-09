# PvP selection and downstream response — 2026-10-09

Worker4 source checkout, `codex/pvp-providers`. User requested immediate repair
of character/weapon select/deselect lag and automated regressions, followed by
the downstream PvP pipeline. Computer Use and real-account smoke remain forbidden;
all measurements below use temporary synthetic inventories and offscreen Qt.
No account DB, imported user profile, engine execution or network source was used.

## Deck editor diagnosis and measurement

Same machine/interpreter, 78 invented characters (19/17/1/3/2 tier counts plus 36
known out-of-band zero-price entries), 70 invented weapons, temporary 16×16 PNGs,
saved synthetic Abyss snapshot and the real Decks details panel. Each sample is
one synchronous handler call; allocation/event settlement occurs between samples.
Twenty warmed alternating selections per item type; these are handler timings,
not native input-to-paint measurements or production-inventory guarantees.

| Action | Before median / maximum | After median / maximum |
| --- | --- | --- |
| Deck character select/deselect | 113.759 / 146.005 ms | 3.893 / 4.935 ms |
| Deck weapon select/deselect | 110.463 / 116.770 ms | 3.605 / 5.217 ms |

The same character browser's marker-only path measured 0.067 ms median and
0.232 ms maximum after warmup (40 samples). That path has no rules panel and is
not the full AppShell assignment action. Both synchronous paths fit a 16.7 ms
budget on this fixture; native frame pacing and equality with the complete browser
are not claimed.
The automated timing guard compares on one host and permits one response frame
for live rules. Structural regressions also prohibit grid/image/account reloads
on warmed Decks membership changes, avoiding reliance on timing alone.

The original four-click profile showed eight full right-panel rebuilds, eight
grid reloads and 1,528 filesystem stat calls. Membership changes now update the
one card's outline/fill and the retained detail widgets. Allocation completion
updates details without repricing the same deck or rebuilding either grid.
Inventory-to-deck projection and badge prices are session-memory only; account
refresh replaces inventory inputs, and rule changes invalidate prices/reports.
Saved weapon count fallbacks and missing selected assets retain uncached semantics.
Full structural grid refreshes dispose old QObject card handles.

## Downstream changes

Draft UI readers share one projection for the current immutable controller state.
Hidden Play validation and period reads are excluded from pick/ban work. Explicit
Play refresh and Decks/profile changes still revalidate readiness immediately.
Portrait fallback resolution is reused until account/provider inputs change. Timer edits
keep their local score/validation refresh without refreshing unrelated build UI.

Scoped weapon assignment updates payloads and changed owner overlays in place.
The shared painted grid's incremental API retains prepared images and stored
signatures for unchanged inputs, including retained members after removal/reorder.
Explicit full refresh remains the boundary for same-path file changes. DPR/metrics
and changed image inputs still invalidate appropriately; new members prepare only
their own images. Automatic filter changes rebuild once and cancel
an already pending duplicate filter update. On eight synthetic characters and
70 weapons, 24 warmed alternating equipment changes measured 13.573 ms median,
16.131 ms maximum for `PvpSeatBuildContext.assign_weapon_to_selected_slot`.
This includes its normal scoped assignment logic, but not a live AppShell frame.

A larger 78-card Draft check initially still took about 380–390 ms after the first
projection/fanout repair. Profiling exposed hundreds of Windows path resolutions
for cached player colors on each action. Warm color lookup now bypasses filesystem
resolution; color writes invalidate path aliases. Static rarity/element paths are
resolved once per distinct value in a pool build, with a new short-lived memo for
each refresh. The pool uses retained portrait paths and keeps prepared images
when picked/banned members leave. These are separate measured bottlenecks, not a
backend legality shortcut: accepted actions still use the canonical reducer.

Final standalone 78-card warmed medians, including event processing in the visible
offscreen workspace/right-panel host, were 94.63 ms ban and 95.81 ms pick. The
combined-suite run measured 101.14/107.41 ms; the regression ceiling is 150 ms.
Each action projects once, performs one incremental pool update, and does zero
full pool resets, hidden Play validations/period reads or portrait resolutions.
This improves the large Draft case roughly fourfold; it is still a heavier action
than toggling Decks membership. Remaining work is card/board construction and Qt
painting, not a claim of browser-equivalent Draft frame time.

## Verification and lifecycle

Final combined verification: 147 focused tests PASS in 53.646 seconds, including
23 new regressions. The scope includes Abyss model/allocation, Decks UI, the full
Free Draft-to-results path, equipment, shared grid/colors and synthetic imported
profiles/period gates. The initial 20-test integration batch caught one stale Play
Start-button regression after profile import on Decks. The hidden signal guard
was narrowed to Draft; explicit refresh/profile changes remain immediate, and the
period checks plus the final combined run pass. Fixture tests cover latest-result allocation, roles/tier counts,
inventory invalidation, stable panel/grid objects, owners/stack counts, fresh click
payloads, image invalidation and downstream event fanout. Ordinary browser grid
regressions are included because the incremental image helper is shared.

All generated PNG/SQLite/preset fixtures belong to test/measurement temporary
directories with connected cleanup. No new retained cache or probe output.
Prior source-research retention is unchanged. Rules legality, Traveler support,
online play, imported real-account performance and real engine execution are
outside this repair's acceptance.

User-owned smoke: restart Worker4's usual AppShell, open Decks create/edit with
Abyss rules, quickly select/deselect characters and weapons, and check that marks,
counts and requirements stay current. In a Free Draft match, perform pick/ban,
assign characters/weapons including swaps, then edit all six timers and finish.
Compare visible response with Characters/Weapons and check for jumps or stale
owner badges. This native sequence has not been performed by the agent.
