# Character card assets and browser presentation

<!-- handoff-current: character-card-assets -->
2026-10-11, Worker4 scoped Traveler executor. AppShell's character browser now
shows one card per source Traveler with a bottom-left chevron opening a small
bordered horizontal row of the other matching variants. Selection changes the
displayed card; clicking that card uses its actual account ID. PvP retains
separate variant cards. Stored character/equipment identities are unchanged.

All character-browser Cn labels use the existing runtime Traveler badge. Seven
element icons and rarity-3/4/5 backgrounds were copied byte-for-byte from the
validated imported cache into tracked application assets. Characters and weapons
share the same rarity-4/5 images. Shared art no longer enters import downloads or
uses per-account overrides. Only unique portrait/weapon sources enter the card
art download jobs; duplicate side-icon URLs share one job/cache entry.

The element/constellation bitmap renderer, shared URL/DOM extraction and
import-dependent filter-icon refresh code are removed. Historical account image
files remain protected by their existing lifetime; no live cache deletion or
account migration is required. Automated checks and visual review are recorded
below. Native AppShell clicks, a real authenticated import and release-package
acceptance remain open. Before MVP, the packaged application must pass the
resource/smoke checklist below. `main.py` still starts the legacy image-only UI;
this change does not migrate that launcher.
<!-- /handoff-current -->

## Application resource contract

The authoritative lookup is `hoyolab_export/bundled_assets.py`. The package must
include exactly these shared card resources at their project-relative paths:

- `assets/filters/element_{anemo,geo,electro,dendro,hydro,pyro,cryo}.png`.
- `assets/card_backgrounds/rarity_{3,4,5}.png`; characters use 4/5, weapons use
  3/4/5. The imported source had identical character/weapon 4/5 artwork, so there
  is one file per rarity, not separate duplicate directories.

[Public-source provenance and hashes](../../assets/card_backgrounds/SOURCES.md)
own the frozen pixels. The former element files are replaced at the same tracked
paths, so filters and cards share the HoYoLAB artwork. Account switches, old
manifests and downloaded caches cannot override this bundle. Shared manifest
references remain project-relative; unique inventory images remain confined to
the selected account. Only the exact resource allowlist may resolve outside an
account root. Missing/bad bundle files cause explicit optional-asset errors,
never a network fallback to shared URLs; the core account transaction remains
committed under [import failure boundaries](HOYOLAB_IMPORT_RELIABILITY.md).

These resources are versioned application source, with application/release
lifetime. Account cleanup, profile deletion and reset do not own them. Old
account `assets/hoyolab/shared` images can remain in old profiles/exports for
compatibility; no new shared image is downloaded or created there. Existing
account icon/composite cleanup and cancellation/drain contracts remain in force.
This checkout has no installer/build asset specification; any external release
packager must include both resource directories.

## Runtime rendering and retired code

`account_character_asset_item` resolves the raw portrait for every character,
with a side-icon or shipped element-glyph fallback if the neutral image is
missing. Known old `char_v2_` / `char_pvp_v2_` / `char_history_v2_` composites
cannot be reused as neutral portraits. `with_character_card_layers` supplies
the fixed rarity/element art and the Cn badge from the selected row: top-right,
24×18 logical pixels, 2-pixel margin, 8-point bold white text on `UI_BG_PANEL`.
No Cn pixels are downloaded or written to an account bitmap. Artifact Browser's
compact text badge remains its own existing style.

The former import-time Cn stamp was locally generated with PIL, not downloaded
as a constellation icon. Its ImageDraw/ImageFont/Arial branch is deleted, along
with baked element compositing, shared CDN constants, unused share-card layer
capture, and profile-dependent filter refresh/property plumbing. Neutral v3
composites retain `crop`/`pvp`/`history` compatibility aliases; their filename and
pixels do not depend on element or constellation. The modern UI reads raw
portraits and paints the labels. Unique raw icon naming stays v2 to reuse valid
existing downloads. Compatibility lookup and retention of historical files are
not an alternate active renderer.

## Traveler selector contract

The database still holds seven variants under
[Traveler identity and migration](TRAVELER_VARIANTS.md). Grouping is confined to
`CharacterWeaponWorkspace` after the full element/weapon/rarity/trait/standard
predicate. The first display chooses the retained positive source ID when it
matches; otherwise the first matching element in canonical element order.
An explicit choice is remembered per source/gender in the workspace session,
with no new persisted setting. Filters can temporarily show another matching
variant without overwriting that choice. A single matching variant has no
chevron; zero matches hide the group. Unknown-element rows are not grouped.

The popup shows only other variants passing the current filters, with their
own element and Cn. Choosing one replaces the card and closes the popup without
editing a team. The next main-card click emits that exact variant through the
ordinary selection/removal route. Team markers also update hidden popup cards.
On the main Traveler card, the slot-number badge occupies the lower-right corner
so the lower-left chevron cannot cover it. Ordinary and PvP badges retain their
default placement. A painted-pixel regression covers this overlap repair.
Escape, outside dismissal, parent hiding, grid refresh and scrolling dismiss
the popup. Placement uses the card's global rectangle and screen bounds; grid
sizing uses physical pitch so startup downscale/fractional DPR keeps one row.
The shared grid adapter and PvP grouping/selection policy are unchanged.

## Acceptance and pre-MVP checklist

Automated acceptance covers
filter-aware grouping, exact selected identity, no team edit on popup selection,
ordinary click/removal, hidden markers, Cn refresh without bitmap changes,
fractional one-row layout, Escape/scroll dismissal, unique icon deduplication,
no shared URLs on fresh/forced imports, old-cache override rejection, confined
manifest paths, optional-image recovery and profile exchange.

Final focused receipts: 176 tests passed in 83.745 seconds across the selector,
character assets, pixel grid, tooltip presentation/inventory, import pipeline,
import reliability, layered/bundled paths, Traveler storage, PvP profile UI and
profile-package exchange/validation. Eight existing AppShell workspace/marker/
filter checks then passed in 0.733 seconds. After the overlap repair, 30 affected
tests passed in 13.299 seconds, including one new painted-badge regression and
the existing grid/PvP checks; these rerun previously covered cases, not 30 new
independent tests. The full `tools/check_tooltips.py` suite passed 69 checks,
including its read-only imported-set witness. The handoff checker passed.
The combined fixture run emitted its existing asynchronous timing diagnostics
and one shutdown ResourceWarning; they did not fail acceptance.

An offscreen visual probe reused the saved neutral Traveler portrait with C4
fixture metadata. The framed six-option row, element/Cn layers, lower-left
chevron and lower-right green slot badge were inspected. The offscreen platform
had no font database, so the probe loaded the existing Windows Segoe UI font
for this inspection only. Both temporary preview PNGs were deleted at closeout.
This is rendered-widget evidence, not native interaction or an authenticated
import. The saved account database was not edited by this follow-up.

Before MVP, check the actual packaged `ui.app_shell_smoke` path on an empty
profile and an existing imported profile:

1. All ten fixed PNGs are present, decode correctly and match the recorded
   source hashes. Filters/cards use these same files before the first import.
2. Open the Traveler chevron; verify a horizontal framed row, selected element
   and its Cn, Escape/outside-click dismissal, screen-edge placement and scrolled
   placement at the supported display scales. A single element filter leaves
   one card; standard exclude removes the Traveler.
3. Every ordinary character has the same runtime Cn label; importing a changed
   constellation refreshes its text without producing a new character bitmap.
4. A cold import downloads unique character/weapon art and source side icons,
   with no shared element/background or constellation-stamp request. A repeated
   import reuses those files; missing/corrupt unique art is recoverable.
5. PvP still displays seven separately selectable Traveler variants with its
   existing seat/price/badge behavior. Offline profile restore on another
   installation resolves shared art from that installation's bundle.

Native clicks and authenticated requests are separate acceptance evidence from
offscreen Qt fixtures. No engine/GCSIM calculation boundary changes here.

## Local Git receipt

Intent 2026-10-11 14:31:05 +03:00: Worker4 scoped Traveler executor will commit this
reviewed UI/import/resource/test/handoff package on `codex/pvp-providers`, from
`5c9494a1203ef3a7b6354072991526d99d1657e5`. Standing own-stage authority applies.
The task began with a clean tree/index; only this package's paths are selected.
Preflight found no merge/rebase/cherry-pick/revert state or index lock.
The canonical PvP worker status and shared queue are owned by their existing
chats; this scoped report proposes source readiness while retaining the native
UI, authenticated import and pre-MVP packaging checks. The final chat snapshot
provides the actual commit result to the queue owner.

Result 2026-10-11 14:32:51 +03:00: source commit
`b98fee2ffe3cd445e5bf51bfb28b23084f8f3275`, parent
`5c9494a1203ef3a7b6354072991526d99d1657e5`, on `codex/pvp-providers`.
All 43 selected paths committed; tree and index were clean afterward. The
focused/tooltip/handoff receipts above apply within their stated boundaries.
No transfer, push, engine/native consumer or canonical worker-status write.

Receipt-only follow-up intent 2026-10-11 14:33:25 +03:00: the same scoped executor will
commit only this actual Git result, from `b98fee2ffe3cd445e5bf51bfb28b23084f8f3275`
on the same branch under the same own-stage authority. Its resulting hash and
final clean-tree result are reported in the final chat snapshot.
