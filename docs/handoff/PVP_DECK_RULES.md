# PvP deck rules editor

<!-- handoff-current: pvp-deck-rules -->
Reviewed 2026-10-09, Worker4 source branch only. The existing Decks editor now
loads the public Abyss catalog on an explicit action, offers the latest live
version per family plus Free Draft, and saves a validated rules snapshot with
the deck. Character cost/tier badges, weapon base prices, budgets, tier bands,
required combinations and scoped issues are displayed without replacing the
existing selection grids. Older saved versions remain viewable; a current
catalog is required to save an Abyss edit, and a known newer version must be
adopted explicitly. Cancel preserves the original deck.

Nine current DEFAULT source families parsed in a fresh in-memory public check;
the tenth, Abyss Ascend Test, requires unsupported FRENCH_COST and produces a
specific message without changing the deck. Known price/count/required-character
checks run; tier allocation/reuse, zero upper bounds and parts of bundle matching
remain explicitly unverified. These are editable deck drafts, not certification
of tournament legality. Abyss match launch is disabled; Free Draft remains the
executable match mode. Current Abyss Cup requires Pyro Traveler, whose selection
is not supported by GTT yet; the UI names the variant and limitation.

Scoped automated and live-source evidence is below. No Computer Use, application
launch, real-account import/write or native visual acceptance. The user reported
an import into Worker4; it was not rerun or inspected by these tests. Next is the
user-owned Decks smoke and feedback, then confirmed rule matching/Traveler and
match schedule work. The [source receipt](PVP_ABYSS_SOURCE_AUDIT.md) retains the
API/document conflicts; organizer prose is not silently merged into live rules.
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
