# Character filters and sorting

<!-- handoff-current: character-filters -->
2026-10-11, Worker4 scoped character-browser follow-up. Shared controls and the
same sorting model cover AppShell, scoped PvP equipment, PvP Decks, the Draft
pool, Artifact Browser character targets and the legacy left panel. The user
confirmed descending numeric order and replacement of the previous sort by the
last selected sort. Final original SVGs are shipped application assets.

The contract below owns predicate combinations, sort cycles, missing values,
ties and target-list exceptions. Tooltips describe these rules in EN/RU/PT-BR
and refresh existing controllers without clearing state. Duplicate Decks and
legacy character-filter builders are retired; weapon/artifact predicates retain
their own domain. Automated and native evidence are recorded separately below.
Canonical PvP worker status and the common queue retain their existing owners.
<!-- /handoff-current -->

## Predicates and conflicts

`ui/character_assets.py:character_matches_filters` owns character eligibility.
An empty family imposes no restriction. Multiple elements, weapon types,
rarities, regions or traits are **OR within that family**; selected families
are **AND between families**. Selecting both Moonsign and Hexerei accepts either
trait. The standard-character button cycles all → only standard → exclude
standard → all; this condition intersects the other families. Standard membership
uses the existing nested/top-level `is_standard_5_star` flag or
`standard_5_star` trait through the same helper used for sorting. Traveler's
existing catalog membership is retained; no name-based classification is added.

Contradictory conditions, for example rarity 4★ with only standard 5★, produce
no matching candidates. Filters are never silently cleared or given an implicit
priority. Existing metadata-less legacy assets retain their passthrough behavior;
known rows missing a selected field cannot match that field. PvP seat scope,
requirement tier/role, allowed equipment IDs and deck visibility intersect these
predicates. Their existing rules own when those contextual scopes clear.

Artifact targets retain selected characters and the current equipment-operation
target even when they do not match; Universal remains visible and first. The
filter tooltip explicitly names this exception. Sorting changes their displayed
order, preserving cached row widgets, parents, selected keys and operation state.
The target-filter reset clears predicates and sorting, preserving target selection.

## Sort controls

`ui/character_browser/sorting.py` owns the state machine, standard classification
and comparison keys. `CharacterSortControls` is used inside `CharacterFilterBar`
and the vertical artifact target lane. Click a button to advance its mode:

| Control / mode | Group priority | Numeric order inside each group |
| --- | --- | --- |
| Constellations 1 | All 5★ → 4★ | C6 → C0 |
| Constellations 2 | Nonstandard 5★ → standard 5★ → 4★ | C6 → C0 |
| Level 1 | All 5★ → 4★ | Highest level first |
| Level 2 | Nonstandard 5★ → standard 5★ → 4★ | Highest level first |
| Level 3 | One group across every character | Highest level first |

Constellations cycle **0 → 1 → 2 → 0**; level cycles
**0 → 1 → 2 → 3 → 0**. Mode 0 restores the existing default key: rarity
descending, level descending, canonical/name casefold, filename. Only one
criterion is active. Choosing the other starts its mode 1 and clears the old
criterion; returning to it also starts at 1. Predicates remain selected.
Sorting is browser-session presentation state, never an account/settings write,
deck membership change or draft action. Retranslation does not emit a sort/filter
change. Shared filter reset returns both buttons to mode 0 with one notification.

Group priority precedes the number: a C0 nonstandard 5★ precedes a C6 standard 5★
in constellation mode 2; a level-20 5★ precedes a level-95 4★ in level mode 1,
while level mode 3 reverses that example. Any other/unknown rarity follows 5★/4★
in grouped modes. Standard splitting applies only to rarity 5★.

Active metric values come from `metadata.character.constellation` / `.level`.
Valid values are integer numbers or integer strings: C0–C6, level ≥1 with no
assumed upper cap. Missing, boolean, malformed or out-of-range values follow
valid values within their group; missing constellation is distinct from C0.
Equal numbers use canonical/name casefold, filename, then the full stable
character ID (numeric IDs first, numeric order; other IDs by their string).
No hidden secondary metric is added. Targets without an asset use their known
target name/key and no invented level/Cn.

Normal AppShell first filters and collapses Traveler variants, then sorts the
shown card by the selected variant's own values. Its popup keeps fixed element
order and exposes only matching alternatives. PvP Decks/Draft keep separate
variant IDs; sorting only the pool does not reorder the action timeline, mutate
the board, grant legality or change owner/equipment overlays.

The user confirmed the PvP shared-pool source rule: an explicit Player 1/2 scope
uses that player's `entry.per_seat` Cn/level; All uses
`board.current_requirement.active_seat` (or the entry's active seat). If that
player does not own the character, use its actual owner; without a current turn,
use the entry's existing base owner. Missing values from an owning player's row
stay missing rather than borrowing the opponent's stronger values. Old controlled
entries without per-seat data retain the asset fallback. Mode 0 keeps the former
asset comparison. Only a temporary comparison projection changes; profiles,
board rows and visible ownership/Cn badges are not edited. This rule is included
on both Draft sort tooltips in every locale.

## Icons and tooltips

Final assets are `assets/ui/icons/character-constellation.svg` and
`character-level.svg`: original project vector geometry, 24×24 view boxes,
transparent background and `currentColor`, rendered with the shared SVG tint
helper. No external license/download, account image or generated trial bitmap
is required. Releases must ship these two files with the existing UI icon
directory. Mode numbers are runtime badges; they are not separate asset files.

Both sort tooltips list every numbered mode, the current mode, click/wrap cycle,
descending behavior, exclusive-sort rule, retained filters, missing-value and
tie handling. Predicate hints explain OR/AND and incompatible choices; artifact
hints add pinned targets. EN/RU/PT-BR are required. All hints use the existing
custom tooltip surface and retain one controller per widget. Semantic families
and bindings are registered under [tooltip contracts](TOOLTIP_CONTRACTS.md).

## Verification — 2026-10-11

The final combined synthetic/offscreen run passed **73 tests in 11.191 seconds**:
sort keys/cycles and every mode on normal, Decks, Draft, scoped and legacy routes;
cached artifact row ordering/selection/removal; Traveler's displayed values;
predicate intersections and two-player metric sources; reset/resource rendering;
existing character assets, painted grids, weapon owner geometry/style and draft
projection/performance. The fresh-process import-order regression also passed.
The warmed draft fixture retained one board projection and one incremental pool
update per action, with no full pool resets. This is a controlled fixture, not a
native responsiveness claim.

`tools/check_tooltips.py` passed **74 checks in 4.966 seconds**, including all
EN/RU/PT-BR sort/predicate/pinned/source hints, persistent custom controllers,
binding registration and a read-only EmblemOfSeveredFate 2p/4p witness on both
surfaces. Earlier intermediate/scoped runs overlap; do not sum them.
The structural handoff checker and whitespace check passed before closeout.

The full tooltip entry initially exposed two pre-existing gaps in source
`468c5c0`: the unregistered native first-actor hint and an import-order cycle
through the new draft clock. The hint now uses the custom surface with an
independent semantic regression; constructing the clock imports it after the
panel class is defined, and both fresh-process entry orders are tested. Draft
rules, first-actor choice and clock behavior are unchanged by these repairs.

Fixtures use caller-owned temporary images/paths/settings/DBs and read-only
artifact sources. No live account/settings/History write, network/import, engine
execution or native application restart/control occurred. Icons were inspected
through in-memory offscreen rendering; no preview/trial file is retained.

Native smoke after the user's next development restart: open AppShell's
character browser; cycle both buttons and confirm numeric/group order and mode
badges; choose a Traveler element; keep element/rarity filters while switching
sort; check Decks/Draft and the artifact target selector; confirm selected targets
survive reordering/reset; change UI language and hover the existing buttons.
This stage does not claim native clicks, authenticated import or packaged release
acceptance, and does not change `main.py`'s existing launcher.

## Local Git receipt

Intent 2026-10-11 20:48:32 +03:00: commit this verified scoped filter/sort/resource/
test/handoff stage on `codex/pvp-providers`, from
`468c5c0d8dcea1d3a9a84cc6a849e635e2533dfb`, under standing own-stage authority.
All 28 selected paths belong to this stage. Index is empty; no merge/rebase/
cherry-pick/revert/sequencer state or index lock is present. No branch transfer,
push, account migration or canonical PvP worker-status/queue edit is included.
The source result is reported after the commit; native/release acceptance remains
at the stated boundary.
