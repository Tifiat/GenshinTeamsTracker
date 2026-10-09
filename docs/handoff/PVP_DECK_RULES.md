# PvP deck rules editor

<!-- handoff-current: pvp-deck-rules -->
Reviewed 2026-10-09, Worker4 source branch only. The existing Decks editor now
loads the public Abyss catalog on an explicit action, offers the latest live
version per family plus Free Draft, and saves a validated rules snapshot with
the deck. Character cost/tier badges, weapon base prices, budgets, tier bands,
required combinations and scoped issues are displayed without replacing the
existing selection grids. Older versions remain viewable; saving requires a
current catalog and explicit adoption of a known newer version. Cancel preserves
the original deck.

Nine DEFAULT source families are supported; FRENCH_COST remains unsupported.
Known price/count/required-character checks run. A requirement table shows
live values, per-target/role coverage
and a shared non-reusing allocation, including alternative T0 groups. Exact site
allocation parity, zero upper bounds and parts of bundle matching remain
unverified. These are editable deck drafts, not certification
of tournament legality. Abyss match launch is disabled; Free Draft remains the
executable match mode. Current Abyss Cup requires Pyro Traveler, whose selection
is not supported by GTT yet; the UI names the variant and limitation.

The user's clipping failure is repaired with one scroll area and wrapped tables.
A later screenshot exposed zero-price characters outside the declared tier bands
aborting every combination check. These known non-tier members now stay outside
the allocation pool without cancelling known T1/T0 coverage. Missing/ambiguous
tiers remain unknown; the table separately counts out-of-band members.
Allocation runs off the UI thread with one active and one latest pending request;
stale results cannot replace a newer composition. Unknown/bounded-out checks use
`?`, not a failure marker. Tier bands describe character cost, not quantity caps.
Physical character roles use the selected preset's DD-ID list, correcting the
earlier price-field mapping. Role-condition Show/Clear actions filter this deck's
grid by tier and role; filters reset on deck/rules changes and never alter selection.

Selection now updates one retained card and the open details in place. Inventory
projection/prices and unchanged allocation inputs are reused until their source
changes. The [performance receipt](performance_measurements/2026-10-09_pvp_selection_pipeline.md)
owns synthetic timings, regression tests and the downstream pipeline check.
No Computer Use, application launch or real-account import/write. Next is the
user's create/edit recheck, then source parity and match schedule work. Traveler
remains the first independent task for another chat. The
[source receipt](PVP_ABYSS_SOURCE_AUDIT.md) retains API/document conflicts;
organizer prose is not silently merged into live rules.
<!-- /handoff-current -->

## Boundaries and implementation

- `run_workspace/pvp/abyss_client.py`: bounded unauthenticated public GETs,
  pagination, latest non-archived family selection and exact returned version.
  Catalog/source data is session-memory only. No source JavaScript execution,
  cookies, persistent catalog cache or automatic background network request.
- `run_workspace/pvp/abyss_rules.py`: allowlisted, bounded immutable JSON
  projection with source lineage/date, display names, cost slots, tier bands,
  bundles and declarations. It keeps source variants and stable game IDs.
  `content_hash` identifies the normalized snapshot; UI fetches do not currently
  persist hashes of the original response bytes. Fetched/updated timestamps are
  distinct; a missing original hash is not invented.
- `ui/pvp_browser/deck_rules.py`: asynchronous explicit catalog/version reads,
  freshness state and localized presentation. A failed refresh leaves saved
  data visible, marks freshness unknown and offers only Free Draft until a new
  successful catalog check. Pending loads cannot apply after cancelling or
  beginning another edit. Errors preserve membership and the previous rules.
- `PvpDecksWorkspace` retains view/edit/save/cancel and normal neutral portraits.
  Costs are calculated outside paint calls, including unselected account cards.
  C/rarity/element layers remain; lower badges show character price/tier or base
  weapon price. Final weapon prices can depend on post-draft assignment and are
  shown as unresolved where that context is absent.
- Free Draft is the initial selection and has no price badges. There is no menu
  for creating from old versions. Saved old titles remain visible separately
  until the user enters edit mode and adopts the current version.

## Persistence and exchange

`gtt.pvp_deck_preset` v1 gains optional `rules_snapshot`; old Free Draft JSON
remains valid and omits it. Abyss references are `abyss:<exact system id>`.
Snapshot/reference mismatches and unsupported extra snapshot fields are rejected.
The snapshot is user-created deck content, retained until that deck is deleted;
the existing deck deletion owns cleanup. No separate cache or database migration.

The development `.gttpvp` v3 deck collection accepts optional `rules_snapshots`
indexed by normalized content hash and per-deck `rules_snapshot_ref`. Export
deduplicates snapshots and uses compact deck JSON; import checks hashes, all
references, no unused snapshots and the existing 1 MiB JSON bound before exposing
any provider. Inline `rules_snapshot` is also validated for local compatibility.
Free Draft archives retain their prior shape. Older consumers without this
extension reject Abyss archives; they must receive the reviewed source package.
Nested snapshot text has the existing portable no-local-path/no-NUL gate.
The inventory, auth exclusion, neutral image and managed-provider cleanup contract
remains owned by [profile exchange](PVP_PROFILE_PACKAGE.md).

## Verification receipt — 2026-10-09

Seventy-four unique focused checks passed: 55 combined model/preset/persistence,
profile schema/package and integrated Decks cases; six public client cases;
four isolated right-panel cases; nine existing Decks UI cases. The 55-case run
emitted one Python shutdown `ResourceWarning` about an uncollectable object;
it reported no failing assertion. Offscreen controls are not physical UI evidence.
The first new cost-badge fixture expected C0 while its shared asset default was
C6; the fixture now explicitly selects C0 and the expected cost passes.

Covered: C/level rounding, variant mapping, missing prices, bundle declarations,
known bounds, snapshot corruption, latest-only selection, stale/failed catalog,
explicit update without losing selection, asynchronous cancellation, save/reopen,
snapshot removal with deck deletion, deduplicated snapshot exchange, source
privacy, and Free Draft compatibility. Live public retrieval normalized all nine
DEFAULT families; FRENCH_COST rejected explicitly. No public payload files were
created. The prior research temp retention remains as recorded in the source
receipt; this stage did not retry its blocked deletion.

User smoke in the Worker4 AppShell:

1. PvP → Decks → create a deck → Load Abyss rules → choose Abyss Cup.
2. Toggle characters/weapons; check cost/tier badges, sums and wrapped conditions.
3. Save, reopen, edit and cancel; check that membership/rules remain stable.
4. Check updates; only newest family options should be selectable. Free Draft
   should remove cost badges and preserve the existing deck workflow.

Native readability, widths, clicks and real imported account behavior remain
for the user. These checks do not close the existing PvP timer/engine/second-seat
or online acceptance gates.

## Readability repair receipt — 2026-10-09

The user's screenshot showed overlapping controls and vertically sliced text.
An isolated unsaved-deck fixture at 650×480 reproduced labels allocated 4–5px
when text required 14–28px; its scroll range was zero. The original 74 checks
covered controls/semantics but did not cover this constrained layout.

New-deck details had been added directly to the fixed header. They now share
the saved-deck scroll boundary through stable parents, with separate cost,
requirement and issue sections. Wrapped text retains its height for the current
width, including counts. Same-deck refresh preserves scroll position; a different
deck resets it, and switching to short Free Draft content reduces the scroll
range. Weapon issues use available weapon names; an unknown issue code has a
localized fallback rather than exposing a translation key.

Twenty-three focused tests passed: seven right-panel controls/layout tests, six
integrated rules/presentation tests and ten existing Decks tests. The constrained
layout test covers 18 combinations: three languages, new/with-existing/saved-edit
states, and 354×480 or 650×590 hosts. Assertions check required label heights,
sibling non-overlap, content width and scroll extent, alongside bottom reachability
and update/short-content transitions. An initial English saved-deck case exposed
unwrapped counts widening the content by 10px; wrapping fixed that case.

Three offscreen PNG previews (narrow top/bottom, wide middle) were inspected with
Segoe UI fixture fonts and the inherited right-panel stylesheet. Text, spacing and
section boundaries were readable; viewport clipping at scroll edges is expected.
Windows' offscreen plugin has no system fonts, so the test loads the fixture fonts
in memory and removes them afterward. The three owned PNGs totaled 97,266 bytes
and were removed by the temporary-directory context immediately after review.
No screenshot output or persistent cache is included in the package.

Native user recheck remains: restart the Worker4 AppShell from the user's existing
launcher, open PvP → Decks → new/edit → Abyss rules at the reported window size;
scroll through all requirements, toggle a character while scrolled, then choose
Free Draft. Verify readable rows, accessible lower conditions and stable scrolling.
Computer Use remains prohibited; no real app window, imported account or data was
opened by this repair. Native acceptance is still pending this user-owned path.

## Requirement status and allocation receipt — 2026-10-09

The Requirements section now has description, current value and status columns.
The same presenter handles all loadable DEFAULT families; Free Draft displays its
configured minimum character count and absence of cost/tier constraints. Tier
rows show selected counts beside price bands without treating band endpoints as
count limits. Requires rows show covered/selected targets and assigned/required
role slots. Mandatory characters have individual presence rows; limits show the
current value. Optional equals recipes remain neutral when unused; consumed
groups list their physical members and total cost. Green check/red cross use
existing tinted SVG icons; status is also named for accessibility. Uncertain
budgets, unknown data and incomplete allocation use `?`.

`run_workspace/pvp/tier_allocation.py` searches one shared pool of physical
characters, maximizing completed target instances then filled partial slots.
Direct bipartite matching is tried first; equals groups use canonical physical
combinations, exact decimal threshold comparisons and backtracking. No character
can support two slots, including across direct/equals alternatives. Full coverage
has a witness; a negative result requires exhaustive search. State/option budgets,
missing relevant data, duplicate identities and unsupported nested requirements
or recursive equivalents produce unknown. Synthetic targets from equals do not
create new requirements. This evaluates the explicitly requested local non-reuse
policy, not an unavailable website/server evaluator. The original report's source
uncertainty remains; persisted snapshots/archive formats are unchanged.

Fresh public catalog retrieval confirmed the nine DEFAULT families' patterns:
T4/T3 require T1 roles, 322CUP also uses T2→T0, and equals uses 2/3/4 T0→T1.
The [current API](https://abyss.darte.gg/api/abyss/draft_systems/6ac54cc57032007b0dd5e4f9)
specifies no role on the resulting T1. The
[older public guide](https://docs.google.com/document/d/1PfNi7XsWEdcrpyc31_1F75KTnRK9a1Lmd5t2tRkbF3o/export?format=txt)
explicitly permits an equivalent DD or support with older recipes. Flexible role
is the stated default inference for this implementation; an optional user choice
was asked and no answer was recorded before closeout. Older numeric thresholds
were not imported. API zero-bound semantics and website reuse remain unproven.

The controller retains only the last allocation in memory. One worker job runs
at a time, with at most the newest pending composition; generation checks discard
stale replies and switching to Free Draft invalidates the pending result. A
completed allocation refreshes panel state without refreshing card grids. This
prevents the new solver from synchronously blocking clicks; it does not claim to
fix the user's earlier selection-lag report. Bounded synthetic 80-row measurements
were roughly 1–60ms for direct/scarce/two-member cases and 395ms for one four-member
case, motivating background execution. No persistent cache or generated data.

Fifty-seven focused tests PASS: 20 allocation, seven existing Abyss model, twelve
integrated rules/presentation/async, eight right-panel and ten existing Decks tests.
Coverage includes shared T1 scarcity, alternative group packing, threshold edges,
order independence, partial roles, duplicate/missing data, bounded search,
coalesced updates, stale-result discard, Free Draft invalidation and live counts.
An independent in-memory oracle matched 250 small nonrecursive cases; review found
an unsupported nested-requires false PASS, now unknown with a regression test.

The first integrated offscreen render exposed missing check/cross font glyphs;
the shared SVG correction passed re-render. Final narrow/wide views showed a
two-T4 composition with one covered target, distinct DD/support counts and
disjoint three-/four-T0 groups. Six owned PNGs across two temporary contexts
(112,027 and 113,240 bytes) were removed immediately after review. Real AppShell
interaction remains user-owned: create/edit an Abyss deck, add/remove T1/T0 while
checking shared T4/T3 coverage, scroll the table, then switch to Free Draft.
No Computer Use, real account access or application launch occurred.

## Character role correction and contextual filters — 2026-10-09

The public client's [character display](https://abyss.darte.gg/assets/agent-list.component-DCkqRtrj.js)
and [preset editor](https://abyss.darte.gg/assets/draft-system-form.component-D22FFMIo.js)
classify eligible characters by `preset.ddAgents` membership of `enkaId`: DD=0,
support=1. The inspected current Abyss Cup has 50 DD IDs and 131 price rows whose
`specification` values are all zero. Price-editor defaults are not role evidence.
The evaluator now derives roles from snapshot `dd_character_ids`, including the
bundle input projection; unknown/unpriced/ambiguous variants retain unknown role.
Raw price fields remain unchanged for snapshot/hash/archive compatibility. Existing
saved snapshots already contain the DD list; no migration/refetch is required.
This corrects physical roles; the separate T0-equivalent role inference above
remains unchanged and does not establish full site allocation parity.

User narrowed scope to condition checking and contextual PvP filters, with no
universal character-role DB or filters in other browsers. Show beside a role
requirement such as T1 DD filters the current Decks grid by both tier and role.
Show becomes Clear while active, and the grid shows an active-filter/count banner
with its own Clear action. Existing element/weapon/rarity filters still intersect.
At most one requirement filter is active; a deck or snapshot change clears it.
Filtering never changes selected membership, counts, allocation or saved data.
Free Draft has no role actions. UI text is localized in RU/EN/PT-BR.

Focused validation covers all-zero prices, derived support allocation, unresolved
variants, rule-specific role changes, tier filtering, filter intersections,
Show/Clear callbacks, hidden membership on save, reset on deck/version/Free Draft,
immediate banner retranslation and constrained layouts in three languages.
Sixty-four focused tests PASS (8 model, 20 allocation, 17 integrated/presentation,
9 panel, 10 existing Decks). The final combined run initially retained one stale
indent assertion; it now checks left-only margins and its focused rerun passes.
Independent review found a stale banner translation, corrected with a regression.
Offscreen review exposed QLabel's top indentation on role rows; left-only margins
keep labels aligned with their actions. Native verification remains user-owned:
Decks → create/edit Abyss → Show beside T1 DD/support → Clear → change rules;
confirm visible cards, unchanged selected counts and readable controls.
No AppShell/CUA or real account access; owned synthetic preview directories use
TemporaryDirectory cleanup and no persistent outputs are kept.

## Zero-price allocation repair — 2026-10-09

The user's post-fix screenshot disproved coverage on a full account-shaped roster:
78 selected characters, tier counts 19/17/1/3/2 and 36 zero-price cards without a
tier, with T4/T3 and role coverage all zero/unknown despite working Show filters.
The allocator rejected the first `tier=None` before examining any requirements;
the formatter then manufactured zero counts for absent allocation results.

`evaluate_deck` now distinguishes one matching band, known cost outside all bands,
overlapping bands and missing data. The allocator excludes only validated explicit
outside rows after identity/duplicate checks. They still count toward roster and
budget limits, but cannot supply T0 or create tier targets. Empty band definitions
remain unknown, as do missing prices/levels/constellations and ambiguous variants.
Unknown tiers may hide extra targets, so known coverage alone does not certify
the whole allocation. No snapshot/archive migration or rule-range change.

The table shows an outside-band count and explanation, em dashes for unavailable
allocation instead of false zeros, and unknown denominators when unresolved tiers
could add targets. Optional T0 recipes say Not needed after full coverage without
that recipe; when used, their counters still name the actual disjoint groups.

59 focused tests PASS: 10 model, 22 allocation, 18 integrated/presentation/async,
9 right-panel. The synthetic source reproduces all screenshot tier counts and
total 887 with invented IDs, not copied account data. It reaches T4=2/2,
DD/support=2/2 each and T3=3/3; deleting 15 T1 through card callbacks uses five
disjoint real T0 triples while 36 zero-price extras remain. Boundary checks cover
zero inside/outside T0, unknown/overlapping/empty bands and duplicate identity.
Independent review caught the empty-band edge; the focused repair checks pass.
Two 354/650-wide offscreen previews (94,343 bytes) were inspected and removed by
TemporaryDirectory cleanup. Native acceptance remains user-owned: reopen the
reported deck, check T4/T3 coverage, remove/re-add T1 and observe T0 groups.
No CUA/AppShell launch or real account reads/writes; no new source parity claim.
