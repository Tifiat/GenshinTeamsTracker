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
files retain their existing lifetime.

Equipped weapon frames use the exact shared PvP recipe; owner portraits retain the main
checkout's accepted geometry. Balanced green/blue team accents accompany the
same rarity/element/Cn recipe in live and PvP Run
slots. New History saves freeze these layers inside each bundle; old bundles
retain their existing display. Absolute browser/selection paths now pass through
the managed-profile resolver. Filter tooltips have semantic locale checks and
refresh in place when UI language changes.

The dated follow-up below owns automated evidence and the native boundary:
the existing window was inspected before the fix; user Escape stopped further
Computer Use. Native after-fix acceptance, authenticated import and release
packaging remain open. Before MVP, run the resource/smoke checklist below.
`main.py` still starts the legacy image-only UI; this does not migrate that launcher.
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

`character_card_pixmap` prepares the same recipe in memory for the shared Run
slot widget, including PvP postdraft. Slot metadata comes from that character's
row, independently of selection. Cn/element changes invalidate the prepared
visual; selection-only changes reuse it. Explicit layer paths override live
lookups, and explicit empty paths suppress them for old History. No composed
portrait file/cache is introduced.

PvP preserves an already resolved neutral side/source portrait or glyph when a
separate manifest variant is absent. Known baked cards still cannot supply that
fallback. Asset adapters and selection normalization accept files only; a missing
portrait cannot resolve to the project directory. Absolute legacy paths remap to
the active profile, foreign managed-profile paths are rejected and external
package paths remain valid. Shared shipped resources stay outside account ownership.

Normal weapon cells retain PvP's 48px size and 6px gaps. Equipped cards and PvP
Decks selection call `inventory_selection_outline` from the same utility; the
[selection color contract](UI_WORK_RULES.md#selection-color-contract) owns its
exact gold frame and the approved palette/defaults. The owner canvas keeps
the main checkout's accepted 45×45 size at (+17, −22) relative to the 48×48 weapon
box. Its ratios are 45/48 for size, 14/45 right overhang and 22/45 top overhang;
rounding uses the actual weapon rectangle at each scale. Frame thickness/overhang
cannot move or resize the owner portrait. Full and incremental refreshes use the
same recipe. Owner overlays exist in the normal browser and PvP scoped equipment
selection, while Decks selection has no owner portrait layer. PvP prices remain
PvP-owned. Accepted character colors and transparency are retained.

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
6. Add ordinary/Traveler characters through normal and PvP routes; each occupied
   Run slot shows its rarity background, element and own Cn. Save a new History
   entry, remove its original source images in an isolated fixture, and verify
   compact/expanded/right-panel/PNG rendering from bundle-local layers. Old
   entries retain their existing display. Check filter hints and language changes.

Native clicks and authenticated requests are separate acceptance evidence from
offscreen Qt fixtures. No engine/GCSIM calculation boundary changes here.

## Portrait, weapon and filter follow-up — 2026-10-11

The requested right-panel loss came from the raw-image-only shared mini-box.
The repaired view-model/widget route is used by normal Run, PvP postdraft and
the frozen History adapter. New snapshots declare `rarity_background_ref` and
`element_icon_ref`; production materialization copies/reuses these declared
assets within the bundle. History prepares styled compact/expanded portraits
and default team art only when frozen layer references exist. Custom artwork
retains its existing cover crop; styled default art uses containment to preserve
badges. Snapshot schema v2 remains compatible through optional empty defaults.

Regressions also exposed PvP clearing a known neutral fallback without a manifest,
then treating `Path("")` as the project directory. The fallback now survives and
directory inputs fail file validation. Literal question marks in RU trait/standard
and PT-BR standard filter hints were corrected; EN/RU/PT-BR standard hints explain
the all/only/exclude cycle. Retranslation reuses existing custom-tooltip controllers
and preserves filter state in normal and PvP workspaces.

Final combined verification: **175 tests passed in 21.128 seconds** across slot
pixels/DPR/invalidation, all 16 actual PvP assignment slots, immutable History
roundtrip/materialization and legacy behavior, character/profile asset routing,
weapons, Traveler selector, painted grid, PvP profile integration, tooltip semantics
and eight existing AppShell geometry/marker checks. `tools/check_tooltips.py`
passed **69 checks in 4.244 seconds**, including a read-only EmblemOfSeveredFate
2p/4p witness on both hover surfaces. These suites overlap; do not sum the counts.

Computer Use restored and inspected the existing PyCharm-launched AppShell window
before the repair. User physical Escape stopped the next operation; no subsequent
native control, restart or after-fix visual acceptance occurred. Offscreen pixel
checks do not replace that acceptance. No authenticated import, account database
write, old History rewrite, engine execution or network request occurred in this
follow-up. No persistent preview outputs were created. By the user's explicit
queue instruction, completed Traveler, absolute asset routing and the earlier
PvP selection source work are crossed out in the shared queue; runtime/native/
integration gates remain separate. Canonical PvP worker status is preserved.

Structural closeout: `tools/check_handoffs.py` found no issues in changed local
contracts or shared queue edits, but its full result is FAIL for one unrelated
`coordination-oversize-file` in `GTT coordination/workers/worker2.md` (over 8000
bytes). That foreign owner's status was not edited; this boundary is retained.

## Owner overlay and palette correction — 2026-10-11

User-provided screenshots accepted character layering and slight transparency,
requested a lighter green/calmer blue pair and rejected the 22px inset owner
portrait. The rejected compact-overlay assertions are removed; no retained
acceptance claim treats that redesign as the desired layout.

The reference was read from the main checkout's `ui/app_shell.py` at
`c14e366c539d265f52e8bc512d57f65cac1aa271` (that file was clean): a 45px owner
canvas at (+17, −22) on a 48px weapon box. Restored source ratios use the weapon
rectangle, independently of its border. Weapon outline increased 2→4px and uses
alpha 230; team accents changed to the balanced colors specified above while
character alpha/neutral fills stayed intact.

`test_weapon_owner_geometry.py` measures independently colored painted pixels
against the fixed main reference, including downscale/fractional DPR and changes
to border width/overhang. Its fixtures are synthetic, caller-owned temporary
PNGs removed by connected test cleanup, with no account/bootstrap dependency.
The older workspace test still covers equip/unequip, incremental ownership,
payloads and retained grid spacing. Native after-correction acceptance remains
with the user's next restart; this correction does not launch/control the app.

Final combined verification: **39 tests passed in 13.940 seconds**, covering the
two painted-owner regressions, weapon refresh/spacing, pixel grid, Traveler
selector, PvP profile integration and eight existing AppShell geometry/marker
checks. An in-memory mutation to the rejected 22/48, −2/22, −2/22 geometry made
both new rendered tests fail in all seven subcases, with no test errors or source
file edits. The reference case measures 45×45 at (+17, −22); fractional/downscaled
cases preserve box-relative proportions. These are synthetic Qt render checks,
not native hover/click acceptance. The structural closeout retains only the
previously recorded foreign Worker2 status-size issue.

## Shared inventory frame and player defaults — 2026-10-11

The user retained the accepted character colors/transparency and requested the
exact PvP weapon frame. `ui/utils/selection_outline.py` now owns that recipe for
normal equipped weapons and both full/incremental PvP Decks selection. The former
private PvP recipe and unused equipped-green palette alias are removed. The
module creates only the outline; owner canvases keep the main-calibrated geometry.
The workspace regression compares actual normal/PvP grid items, retains the normal
overlay and prohibits Decks owner overlays, including deselect/reselect. The scoped
PvP equipment regression verifies both seats' owner overlays and gold frames.

The [shared selection contract](UI_WORK_RULES.md#selection-color-contract) owns
the tone recipe, accepted HSL bounds, palette roles and alpha. PvP defaults use
the existing central registry, with no hex-matching migration of saved choices.
The Settings **По умолчанию** action applies the new pair to saved preferences.

Combined verification: **59 tests passed in 15.477 seconds** across central
defaults/settings/cache/reset, guarded Settings swatches, normal/PvP frame parity,
owner pixel geometry/DPR, painted grid, Traveler selector, PvP profile integration
and existing AppShell checks. The strengthened scoped PvP owner/frame case then
passed separately in 1.542 seconds; it overlaps the 59-case run. An in-memory
substitution of the old bright green/blue caused the source-backed palette guard
to reject both colors without test errors or source edits.

Checks use caller-owned temporary settings/DBs/images with connected cleanup;
the Settings fixture suppresses HoYoLAB directory/auth initialization. No live
settings/account/history write, import, network, native restart/control or
persistent preview output occurred. Native AppShell acceptance remains the user's
restart/smoke path: compare equipped weapon frames with Decks, retain owner heads
in normal/scoped equipment selection, and inspect/reset both player swatches.
Early structural checks reported the existing foreign Worker2 size issue; the
final full checker passed with no foreign-file edits by this executor.
Canonical PvP status and the common queue remain untouched by this follow-up.

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

Follow-up intent 2026-10-11 15:48:26 +03:00: Worker4 scoped Traveler executor will
commit the reviewed portrait/History/weapon/filter/path package (36 own source,
test and contract paths), from `e58c508d3257f9c2731009cab69b633b12532c0f` on
`codex/pvp-providers`, under standing verified-own-stage authority. The task began
with a clean tree/index; current index is empty. No merge/rebase/cherry-pick/
revert/sequencer state, index lock or active hook was found. Shared queue edits
were explicitly requested by the user and remain outside this Git worktree.
Product checks pass; the structural checker has only the foreign Worker2 issue
recorded above. No transfer, push, profile/runtime change or further native input.

Result 2026-10-11 15:50:02 +03:00: source commit
`e6f8c2069a382a1cdcbf706d2f0d7241fa84c2ad`, parent
`e58c508d3257f9c2731009cab69b633b12532c0f`, on `codex/pvp-providers`.
All 36 selected paths committed; tree/index clean afterward. The 175-case product
suite and 69-case tooltip suite pass within the boundaries above; the full handoff
checker retains only the foreign Worker2 size issue. No transfer, push, engine/
profile mutation, old History rewrite or additional native input occurred.

Receipt-only intent 2026-10-11 15:50:02 +03:00: the same scoped executor will commit
only this recorded Git result, from `e6f8c2069a382a1cdcbf706d2f0d7241fa84c2ad`
under standing own-stage authority. Final receipt hash/clean state will be in the
chat closeout; canonical PvP worker status remains untouched.

Owner/palette correction intent 2026-10-11 16:09:51 +03:00: Worker4 scoped executor will
commit six reviewed own source/test/contract paths from
`a02d4e3127913209038fb51b1344cb17fcf11134` on `codex/pvp-providers`, under standing
verified-own-stage authority. Initial tree/index were clean; current index is
empty. No Git operation/index lock/active hook was found. The 39-case product
check and negative mutation witness pass within the boundaries above. Canonical
PvP status, shared queue, other checkouts, runtime/profile data and native UI are
outside this write; no transfer or push.

Correction result 2026-10-11 16:10:23 +03:00: source commit
`0c21fb51198212ebe41933ac6b28d0d97c4f7be5`, parent
`a02d4e3127913209038fb51b1344cb17fcf11134`, on `codex/pvp-providers`.
All six selected paths committed; tree/index clean afterward. The 39-case product
suite and rejected-geometry mutation witness pass; the full structural checker
still reports only the foreign Worker2 status-size issue. No transfer, push,
profile/runtime mutation, native control or persistent preview output occurred.

Correction receipt-only intent 2026-10-11 16:10:23 +03:00: commit only this actual
result from `0c21fb51198212ebe41933ac6b28d0d97c4f7be5`, same executor/branch and
standing authority. The final chat snapshot supplies receipt hash/clean state.

Shared-frame/defaults intent 2026-10-11 16:39:26 +03:00: Worker4 scoped executor
will commit 15 reviewed own source/test/contract paths from
`6b2c0d2d02e578340b25f749bac31d56af0da824` on `codex/pvp-providers`, under standing
verified-own-stage authority. Initial tree/index were clean; current index is
empty. No Git operation/index lock/active hook was found. The product, mutation
and final structural checks above apply. No transfer, push, profile/runtime/
settings mutation or native control; canonical PvP status and shared queue unchanged.

Shared-frame/defaults result 2026-10-11 16:44:02 +03:00: source commit
`4d87a8b91b32dcfe1373dfc6d6d42bd999929bc2`, parent
`6b2c0d2d02e578340b25f749bac31d56af0da824`, on `codex/pvp-providers`.
All 15 selected paths committed; tree/index clean afterward. Product/mutation
evidence above applies; final structural checker PASS. No external transfer,
push, account/settings/runtime mutation or native control occurred.

Shared-frame receipt-only intent 2026-10-11 16:44:02 +03:00: commit only this
actual result from `4d87a8b91b32dcfe1373dfc6d6d42bd999929bc2`, same scoped executor,
branch and standing authority. Final receipt hash/clean state is in chat closeout.
