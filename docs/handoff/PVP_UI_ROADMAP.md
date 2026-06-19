# PvP UI Roadmap

Purpose: source of truth for the PvP UI direction before implementation. The
backend/product contract remains in `PVP_V0_CONTRACT.md`; implementation status
remains in `PVP_BACKEND_STATUS.md`.

## Current AppShell Baseline

- A `PvP` workspace tab exists beside Characters / Weapons, Artifacts, and
  GCSIM.
- When PvP is active, the right dock shows `Decks`, `Play`, `Draft`, and the
  global Account action instead of Abyss / DPS Dummy.
- Account remains a global shell action in the right header.
- PvP source ownership is split: `ui/pvp_browser/window.py` owns the left/main
  workspace, while `ui/right_panel/pvp/` owns the fixed right-dock pages and
  stage panels. Old right-panel exports from `ui.pvp_browser.window` remain as
  compatibility re-exports.
- Decks v0 is implemented as `ui.pvp_browser.window.PvpDecksWorkspace` on the
  left plus `ui.right_panel.pvp.decks.panel.PvpDecksRightPanel` on the right.
  The corrected UI follows the existing Characters/Weapons browser grid on the
  left and the Artifact Browser preset-row/list/edit pattern on the right. It
  persists local deck presets, supports explicit view/edit/save/cancel, and
  validates through the existing backend deck validator.
- Play/local match setup v0 is implemented as a `PvpWorkspace` page plus
  `ui.right_panel.pvp.play.panel.PvpPlayRightPanel`. It selects Player 1 and
  Player 2 local deck presets, validates both through backend `DraftDeck`
  conversion, starts an in-memory `FreeDraftController`, and switches to the
  Draft board page.
- Draft board v0 is implemented in `ui/pvp_browser/window.py` as a local
  hot-seat board over the backend Free Draft board projection. The right Draft
  panel is `ui.right_panel.pvp.draft.panel.PvpDraftRightPanel`; shared draft UI
  helper/read-model formatting and canonical PvP page/stage/timer constants
  used by both sides live in `ui/right_panel/pvp/_shared.py`.
- The current Draft pick/ban visual pass exists. Post-draft Assignment and
  Weapon assignment now run through seat-scoped `AppShellController` state,
  a `CharacterWeaponWorkspace` subclass that only restricts available assets,
  and the shared Abyss `RunRightPanelWidget`. The old PvP-specific source grids,
  `SEL`/grey assigned overlays, assignment dictionaries, and fake right-panel
  target-slot model assembly are no longer an accepted UI path.
- PvP browsing, deck editing, draft, and post-draft stages must not mutate the
  normal TeamBuilder / Run state unless a future explicit bridge is designed.
- Post-draft Assignment, Weapon assignment, Timers/results, and read-only
  completed result summary v0 are implemented for local hot-seat matches.
  Profile package import/export actions are also available. Artifact Browser
  routing, executable scoped PvP GCSIM, online play, ruleset costs, immune
  picks, result PNG/export, and PvP History are still not implemented.

## Core Model

PvP is a mini-section inside AppShell, not a single flat screen.

- Left/main PvP area: browser/workspace scene.
- Right PvP control panel: current mode controls, deck preset list, validation,
  selected details, setup actions, timers/result controls.
- Target PvP build stages must reuse the normal AppShell build pipeline, not a
  visually similar PvP-specific imitation. The reusable unit is the existing
  Characters/Weapons workspace, embedded Artifact Browser, GCSIM Browser, typed
  `RunSessionController` / `TeamBuilderState`, and `RunRightPanelWidget`
  refresh path. PvP may provide scoped adapters, routing, and data providers,
  but it must not duplicate roster markers, slot assignment visuals,
  right-panel slot hierarchies, artifact-equipment UI, or GCSIM browser UI.
- Source ownership target:
  - `ui/pvp_browser/` owns deck browser grids, the draft board, and main PvP
    scenes before build flow.
  - `ui/right_panel/pvp/` owns fixed right-dock PvP pages and Draft/build
    routing commands.
  - MVP build-flow visuals come from the normal AppShell workspace/right-panel
    classes running against scoped PvP data, not from new PvP source/target
    widgets.

PvP opens into Decks, not directly into Draft.

Top-level PvP right-header pages:

- Decks;
- Play / local match setup;
- Draft.

`Draft` is the active match container. Target post-start match stages should be
internal Draft stages, not additional top-level tabs:

1. Pick/Ban.
2. Assignment.
3. Weapon assignment.
4. Artifact equipment.
5. Optional PvP GCSIM.
6. Timers / results.
7. Completed result / export.

Permanent right-header tabs should be added only when their real mode is
implemented. Do not add top-level Team, Timers, Result, Artifacts, GCSIM, or
Match tabs.

## MVP Build Flow Contract

After pick/ban produces each player's restricted pool, PvP MVP build flow is a
scoped instance of the normal live-run build pipeline:

- The normal pipeline is: Characters/Weapons left workspace, embedded Artifact
  Browser left workspace, GCSIM Browser left workspace, and the shared Abyss
  `RunRightPanelWidget`.
- PvP must be able to launch that pipeline with a scoped PvP run context instead
  of the user's normal live-run state. The scoped context owns its own
  `RunSessionController` / `TeamBuilderState`, selected slot, timers, runtime
  GCSIM summaries, provider source data, and seat-local runtime equipment state.
- PvP provider source data and PvP runtime equipment state are separate. A
  local player can read shared immutable/source account data from the normal app
  SQLite DB without duplicating it, but weapon/artifact equipment decisions made
  inside PvP must live in a per-seat scoped runtime state that starts empty and
  never mutates normal account equipment. Imported/future remote players read
  source data from their `.gttpvp` package while still receiving a fresh PvP
  runtime equipment state for the current match.
- The PvP profile package format is `.gttpvp`, a versioned ZIP containing
  `manifest.json`, `decks.json`, and `account_slice.sqlite`. It is not `.npz`:
  NumPy adds no useful contract here. Import must validate archive entries and
  materialize only the SQLite member to a managed temp path, not unpack an
  arbitrary folder tree.
- Target `.gttpvp` packages contain deck presets, a deduplicated account slice
  for characters/weapons/artifacts/presets used by those decks, and the bitmap
  assets needed for autonomous display on another machine. Current package
  implementation still has an asset-portability gap and must not fall back to
  image paths as identity.
- The left Characters/Weapons view for Assignment/Weapon stages must use the
  same normal quick-pick and marker machinery as AppShell. Selected characters
  show team-colored team-local slot markers `1-4` for team 1 and `1-4` for team
  2; they do not use PvP-only `SEL` badges, grey disabled overlays, or custom
  assigned-card states.
- Right-panel character slots must be the same `RunRightPanelWidget` slots
  driven by the scoped run model. A PvP command/routing layer may choose which
  scoped player is active and where Artifact/GCSIM actions open, but it must not
  create a second team/slot-card hierarchy that merely resembles the normal
  right panel.
- Artifacts and GCSIM are opened from PvP Draft/build controls, not from the
  normal top-level AppShell workspace tabs. Those controls may be placed later
  in the PvP right panel or another agreed Draft/build command location, but
  the target they open is the existing Artifact Browser or GCSIM Browser wired
  to the scoped PvP context.
- Build-stage right-dock layout should keep player build panels collapsible as
  local UI state. In future online mode, collapsing the opponent panel affects
  only the local client and must not become synchronized draft state.
- The previous PvP-specific post-draft source/target widgets were disposable
  scaffolding and have been removed or bypassed. Do not reintroduce them.

## Decks Mode

UI label: EN `Decks`, RU `Kolody`.

Decks is the current real PvP entry point.

Left/main area:

- Base the visual and asset-data approach on the existing Characters / Weapons
  browser.
- Use the same section order and grid feel as the existing browser: weapons
  first, then characters, with the same filter rows, card sizes, spacing, and
  overlay-scroll behavior.
- Show characters and weapons from account browser/runtime data.
- View mode shows only members of the active deck preset.
- Edit mode shows all account characters and weapons.
- In edit mode, selected items are normal/highlighted and unselected items are
  dimmed.
- Clicking in edit mode toggles membership in the deck preset.
- Characters and weapons should be separate sections.
- Costs/ruleset visuals are reserved for later.

Right panel:

- The Decks tab/control replaces the former placeholder `PvP Control`.
- Create deck preset through the same conceptual flow as Artifact Browser build
  presets: plus creates a draft from all current account characters/weapons,
  the left browser enters edit mode, Save commits, and Cancel discards.
- List deck presets as compact Artifact Browser-style rows with inline
  edit/delete icons.
- Expand the selected preset in-place inside its row; the expanded block pushes
  lower rows down and contains compact info/actions instead of a separate form.
- Selected preset info owns:
  - ruleset/cost system selector;
  - initially only `No rules / Free Draft`;
  - character count;
  - weapon count;
  - automatic compact validation/status;
  - future character/weapon cost summary;
  - edit actions;
  - later export actions.
- The ruleset/cost selector belongs inside expanded deck preset info, not as an
  unrelated global control.

## Deck Preset Persistence

Use `data/pvp/decks/` for local PvP deck presets.

Persistence rules:

- The format must be versioned.
- Do not store localized display names, image paths, or local machine paths as
  identity.
- Character identity should be stable `character_id`.
- Weapon identity uses the account observed-stack bridge in
  `run_workspace/pvp/weapon_identity.py`. The UI selects one
  `WeaponObservedStackRef` per observed stack, preferring
  `weapon_fingerprint` and falling back only to stable structured weapon fields.
  `known_count > 1` is a stack count, not fake instance ids.
- Persistence uses a thin UI preset wrapper, `gtt.pvp_deck_preset`, implemented
  in `run_workspace/pvp/deck_preset.py`. It delegates weapon identity extraction
  and `DraftWeaponStack` conversion to `weapon_identity.py`, then converts to
  the existing backend `DraftDeck` contract for validation.
- Avoid creating a second incompatible deck format.

Existing backend deck contract:

- `schema_version = 1`;
- `kind = "gtt.pvp_deck"`;
- `deck_name`;
- `ruleset_ref.ruleset_id = "free_draft_v0"`;
- `characters[].character_id`;
- `weapons[]` as observed weapon stacks;
- no artifacts, auth/cookies, raw account dumps, local paths, or SQLite row ids.

Current UI preset fields:

- `schema_version`;
- `deck_id`;
- `name`;
- `ruleset_id`, initially `free_draft_v0` / no-rules;
- `character_ids`;
- `weapon_refs`;
- `created_at_utc`;
- `updated_at_utc`;

Current identity status:

- The shared `Weapon observed stack identity contract/helper` exists in
  `run_workspace/pvp/weapon_identity.py`; future PvP screens should use it
  instead of reading raw HoYoLAB/browser weapon fields directly.

## Cost / Ruleset Roadmap

- The first Decks implementation does not implement ruleset costs.
- Free Draft / No Rules treats costs as disabled or `0`.
- Future rulesets/cost systems should show character costs, weapon costs,
  tier/cost summaries in the right preset panel, and a cost line on cards.
- Cost display on cards should reserve a separate lower text row/zone.
- Level likely belongs in a lower corner/row rather than competing with the
  existing HoYoLAB constellation overlay.
- Do not design final card styling now.

Card identity and presentation note:

- Draft identity is the stable `character_id`; images/icons are optional
  presentation assets and must never be identity.
- The earlier risk with one shared visual card was ambiguity, not a rule that
  opponent images are forbidden. A shared card is acceptable when it has
  explicit ownership markers and per-seat metadata.
- If a character belongs to both players, preserve the displayed/base
  HoYoLAB constellation badge and add the other player's constellation/ownership
  badge on the opposite corner. Use split/two-color ownership styling or another
  clear dual-owner marker without hardcoding final colors here.
- Future local/export/online paths may provide or resolve images by
  `character_id`, but draft/session logic must work without image paths. Prefer
  local cache, bundled/common fallback icons, or client-side asset resolution;
  do not assume a future server hosts images.

## Play / Local Match Setup

UI label: RU `Играть`, EN `Play`.

- Play v0 is implemented as a real local setup tab, not an empty placeholder.
- In v0, only local hot-seat exists.
- The user may select the local account as both players.
- Player 2 can be a local hot-seat opponent using the same account and one of
  the same deck presets.
- Ghost-copy / self-vs-self is acceptable for v0.
- Online opponent search can later become an additional Player 2 source.

Suggested v0 flow:

1. Choose Player 1 deck preset.
2. Choose Player 2 local/hot-seat deck preset or ghost copy.
3. Start local draft.
4. Show an in-memory active draft summary from the backend board projection.

Current v0 scope:

- Uses saved local deck presets from `data/pvp/decks/`.
- Same-preset/self-vs-self starts with an independent Player 2 backend deck
  copy in memory only.
- Start local draft switches to Draft automatically. The left Play page still
  shows setup/helper text and does not duplicate the full form.
- No session files, PvP history, normal TeamBuilder mutation, or network access
  are performed by Play v0.

## Draft Stage

Draft board v0 is implemented for local manual play through the full Free Draft
schedule as a readable visual prototype. The old duplicated Player 1/Player 2
text-card boards, moving debug/status strip, and right-panel debug summary are
not accepted fallbacks.

Target readable Draft phase:

- Left/main area shows one unified character pool, not two full duplicated
  scrolling player boards.
- Each unique `character_id` should be shown once when possible.
- Player-only characters use that player's display metadata and a clear
  ownership marker.
- Shared characters use one card with per-seat ownership/constellation markers.
- Current legal targets are visually obvious and clickable.
- Illegal/unavailable targets are dimmed and non-clickable.
- Picked and banned characters leave the unified pool and appear in right-panel
  result zones.

Target right Draft panel:

- current player/action prominently;
- compact step/progress and legal target count;
- Player 1 picks;
- Player 1 bans;
- Player 2 picks;
- Player 2 bans;
- picks are more readable/larger, bans can be compact chips/icons;
- timeline/action log stays compact/collapsible/later, not the dominant UI.

Backend/read-model direction:

- The durable source of truth for the unified pool is the backend board
  projection section `unified_pool`.
- Draft UI consumes `unified_pool` instead of reconstructing the readable pool
  from `seats[*].cards`.
- `unified_pool` entries include stable `character_id`,
  `owner_seats`, `base_seat`, per-seat display metadata, legal/action data,
  pool/result zone, picked/banned owner, action index, and optional reason codes.
- Do not put local image paths into the backend identity/read-model contract;
  the validator rejects visual path/icon/image keys in `unified_pool`.

Current v0 scope:

- Draft tab appears only because the real board exists.
- Draft without an active session shows an empty state directing the user back
  to Play.
- Starting from Play creates an in-memory `FreeDraftController` and switches to
  Draft.
- The board renders `unified_pool.entries` through the shared painted
  `PixelIconGrid` path used by character/weapon browsers. The removed
  QWidget-per-card Draft implementation is not an accepted fallback.
- The pool header is a segmented `Unified pool / Player 1 / Player 2` scope.
  The pool reuses the same `CharacterFilterBar` as the normal AppShell
  Characters workspace, so element, weapon type, rarity, trait, and Standard
  filters have one implementation and one behavior contract.
- Pool portraits carry Player 1/Player 2 constellation badges on opposite
  sides. Legal portraits use the active seat accent and accept the backend
  action payload; illegal portraits are dimmed and non-clickable.
- A painted two-row 22-position order strip flattens the backend `timeline`.
  Empty positions use a large turn number plus a translucent semantic action
  fill; completed positions show an uncluttered portrait while retaining the
  action fill. Player identity uses amber/purple accents, while pick/ban/immune
  use neutral/red/gold action colors. Do not reuse normal team green/blue for
  either Draft players or Draft actions.
- Picked/banned entries are omitted from the main pool and rendered through
  the same Draft grid-item adapter in right-panel result zones. Picks use the
  readable character-grid size; bans use compact portraits.
- The right Draft panel keeps current action/progress prominent, does not show
  the old five-line debug summary, and keeps the action log collapsed by
  default.
- After each accepted or rejected action, UI state is rebuilt from the backend
  projection.
- When the schedule completes, pick/ban clicks are disabled, all order
  positions are filled, and final visual pick/ban zones remain visible.
- After pick/ban completion, current v0 continues through internal Assignment,
  Weapon assignment, Timers/results, and Completed result stages for local
  hot-seat play.
- Current v0 skips Artifact equipment and scoped PvP GCSIM, but the target
  architecture must prepare right-panel slots/stages for them.
- Online mode, ruleset cost rendering, immune picks, session files, PvP History
  writes, and export are not implemented in current v0.

## Team Assignment

- Assignment starts after pick/ban completion and must be the first MVP pass
  that moves PvP onto the real build pipeline.
- The allowed source roster is restricted to that player's 8 picked
  `character_id` values, but the view/behavior must be the normal
  Characters/Weapons workspace behavior: sequential quick-pick into Abyss team
  1 slots 1-4, then team 2 slots 1-4; clicking an already picked source
  character removes it from its slot without compacting; clicking a new
  character when all eight slots are full does nothing.
- The selected-source markers must be the normal AppShell roster markers:
  compact team-colored markers with team-local slot numbers. Do not use PvP-only
  `SEL` overlays, grey assigned-card dimming, disabled cards, or separate
  selected/assigned marker logic.
- The right panel is the normal Abyss `RunRightPanelWidget` driven by a scoped
  PvP `RunSessionController` / `TeamBuilderState`. Right-panel slot clicks keep
  their normal behavior: selected build/details target toggle, not character
  assignment.
- When assignment is committed to the PvP draft backend, convert the scoped
  `TeamBuilderState` team slots into the backend `character_id` assignment and
  call `FreeDraftController.set_team_assignment(...)`. Backend validation
  remains final authority, but it must not be the source of UI identity or
  roster marker visuals.
- Player 1 and Player 2 may be built as separate scoped run contexts or as an
  explicit seat switch over one scoped build workspace. In either case, the
  inactive player must not consume half of the right panel as an empty target
  area. Collapsed/inactive seat controls should be compact command rows only.
- The existing PvP-specific post-draft target/source implementation is not an
  MVP foundation. Delete or bypass it during the real build-flow migration; do
  not extend it.

## Weapon Assignment

- Weapon assignment is the normal Characters/Weapons weapon flow running against
  the same scoped PvP context/database used for Assignment.
- Clicking a right-panel slot selects the character/build target. Clicking a
  compatible source weapon assigns it through the normal weapon assignment path,
  filtered by the selected character's weapon type.
- The weapon pool is restricted to the current player's PvP deck/temporary
  database, but the UI must reuse normal weapon grid behavior, owner/exhaustion
  markers where applicable, selected-target weapon-type filtering, and right
  panel weapon mini-box rendering.
- When weapon assignment is committed to the PvP draft backend, convert scoped
  equipment state into the backend weapon-stack identity contract and call
  `FreeDraftController.set_weapon_assignment(...)`. Do not invent localized-name,
  image-path, or display-string weapon identity.
- Weaponless continuation remains blocked by the existing backend contract.

## Artifact Equipment

Artifact equipment is target product direction for PvP. It is not implemented
in current v0, and the immediate source-ownership refactor should preserve the
structure needed for it rather than implementing the full equipment flow.

- After Draft pick/ban plus team and weapon assignment, PvP should support an
  Artifact equipment stage inside Draft.
- Local Player 1 reads normal Artifact Browser source data but uses scoped PvP
  runtime artifact equipment state. It should not require a duplicated copy of
  the whole local artifact DB.
- Imported/remote Player 2 reads artifact source data from the imported package
  and uses the same scoped PvP runtime artifact equipment state boundary.
- Player 2 can import artifacts from JSON into that temporary PvP session.
- PvP artifact data is scoped to the active PvP match/session.
- Changes made inside PvP must not affect the main Artifact Browser, main
  account artifact state, normal live-run builds, or current account equipment.
- The implementation must use the existing Artifact Browser code path through a
  scoped PvP adapter/session rather than forking a second Artifact Browser. PvP
  may decide where the "open artifacts" command appears, but the opened surface
  must be the same embedded Artifact Browser behavior pointed at the scoped PvP
  database/operation target.
- PvP right-panel character slots are the normal live-run slot cards and must
  support the existing character, weapon, and artifact mini-zones plus
  artifact-equipment actions. Do not build a dead-end simplified no-artifact
  target widget.

Future PvP JSON preset QoL:

- Later, GTT export JSON should optionally include Artifact Browser build
  presets.
- Import should support both ordinary artifact JSON / Artiscan-like imports and
  extended GTT JSON that includes artifacts plus preset metadata.
- This is a later PvP Artifact Browser import/export enhancement, not part of
  the immediate right-panel refactor. It matters for PvP MVP polish because
  Player 2 should not have to manually find already prepared artifacts when an
  exported JSON already includes the needed presets.

Hot-seat layout direction:

- In hot-seat PvP, Player 1 and Player 2 halves/zones should be able to
  collapse/expand so the artifact-equipment stage has enough room.
- This is especially relevant once Artifact Browser-like equipment UI opens
  inside PvP.
- Assignment/Weapons source panels must stay stable after they are first
  created. The scoped `CharacterWeaponWorkspace` instances are reused while
  title text, markers, weapon filters, owner badges, and right-panel models are
  updated in place. Rebuilding the post-draft left source frame on every click
  is a regression because it reintroduces the same twitch/flicker class that was
  fixed for the production right panel.
- Right-panel slot drag/drop in PvP must route to the same scoped
  `AppShellController.swap_slots(...)` behavior as normal Abyss. Slot clicks
  select targets; source-card clicks assign characters/weapons; drag/drop swaps
  existing right-panel slots.
- Post-draft performance contract: Assignment/Weapons actions use the normal
  AppShell fast path and must not double-refresh. Build-state actions emit a
  single state refresh and update only the active seat right-panel model unless
  the stage changes or the panel is being created. Collapsed player zones should
  shrink to a compact full-width toggle row, including when both players are
  collapsed.
- Weapon assignment identity must use the scoped backend stack key selected from
  the draft deck. UI display/type names are not authority; numeric Hoyo weapon
  type ids and localized names must resolve to the same canonical stack key the
  backend validates.

## PvP GCSIM

- Normal live-run GCSIM Browser remains a left workspace tied to current
  live-run teams.
- PvP does not need a separate top-level PvP GCSIM Browser tab.
- PvP can expose GCSIM through a button/action inside the Draft/build flow. The
  exact command location is intentionally flexible for later layout work.
- That action must open or route to the existing GCSIM Browser behavior wired to
  the scoped PvP teams/builds, not normal live-run teams and not a second
  PvP-specific GCSIM UI.

## Timers / Results

- Timers/results v0 is implemented as an internal Draft stage after valid team
  and weapon assignment. In the target flow, it follows artifact equipment and
  optional PvP GCSIM when those stages exist.
- Timers/results should reuse scoped PvP team/build data for display rather
  than resurrecting custom target-slot panels. The six timer inputs are
  `CompactTimerInputWidget` instances shared with the normal Abyss timer path:
  mouse wheel, Up/Down, Left/Right, Enter, focus selection, clamping, and
  two-digit segment normalization must not be reimplemented in PvP. Each input
  records the clock remaining when that player's second team finishes the
  chamber, starts at `10:00`, and is clamped to the normal editable Abyss range
  down to `05:00`. All six values are required before finalization. UI converts
  each remaining value to elapsed seconds (`600 - remaining`) before committing
  `ChamberTimer` data; it must never submit the clock value as elapsed time.
- Finalization calls `FreeDraftController.set_match_timers(...)`; lower total
  time wins and equal totals draw through the backend result model.
- The left Draft workspace now owns the playable timer scene: three chamber
  rows, both players' remaining-clock inputs, a readable elapsed-seconds
  total/difference
  scoreboard with winner/loser chevrons, cached current Abyss period, separate
  enemy wave rows, per-half solo/multi-target HP summaries, and the finalization
  command.
  The right dock remains scoped team/build details and does not regain the live
  Abyss chamber table. Missing cached Abyss data is an explicit unavailable
  state, not invented monster data.
- PvP player colors have one UI source of truth in `ui/utils/pvp_colors.py`.
  Picks, ownership badges, result-zone outlines, post-draft seat accents, and
  timer labels must resolve from that source instead of copying literals or the
  normal green/blue team colors. Account settings expose both player colors and
  a reset-to-default action. Seat accents must be painted inside existing frame
  geometry so changing color/collapse state never changes right-dock width or
  content alignment. Draft order overlays remain translucent when inactive:
  picks use the acting player's color, bans use the ban semantic red, and immune
  actions keep their dedicated semantic color.
- Future match admission must validate Abyss period identity before Draft
  starts. Local/hot-seat profiles must resolve to the same period; a mismatch
  must be checked against the current authoritative period and require stale
  data to be updated. Online room create/join must use the server-advertised
  current period as authority and block/ask the client to refresh when its
  profile period differs. This admission gate is not implemented yet.
- Factual DPS, restarts, technical-loss UI, bundle/export actions, and GCSIM
  scoring are still future work.

## Export / Result

- Completed result v0 is implemented as a read-only internal Draft stage.
- The MVP result view should show scoped PvP teams/builds, assigned weapons,
  per-player chamber timers/totals, winner/draw, and time difference without
  bringing back the disposable two-player source/target slot layout.
- PNG/export, history persistence, and polished result-card design remain
  future work.

## Reference-Site Conclusions

Stable conclusions from Gentor/Abyss review:

- Gentor deck/profile screens support the Decks split: main grid for
  characters/weapons, side panel for account/preset/cost summaries.
- Gentor/Abyss draft screens support a large main draft board, compact
  controls/status outside the board, and staged flow: draft creation/setup,
  pick/ban, team assignment, timers/results.
- GTT chooses a unified character pool with explicit ownership markers instead
  of preserving the current duplicated two-board display.
- Some routes require auth or are blocked. Do not depend on live scraping for
  app behavior.

Use reference sites to decide information placement, not to copy styling.

## Current Implementation Status

Current PvP v0 implementation lives in:

- `run_workspace/pvp/deck_preset.py`;
- `run_workspace/pvp/weapon_identity.py`;
- `ui/pvp_browser/window.py` (`PvpDecksWorkspace`, `PvpWorkspace`,
  `PvpDraftWorkspace`, and left/main PvP browser scenes);
- `ui/right_panel/pvp/host.py`, `decks/panel.py`, `play/panel.py`,
  `draft/panel.py`, `draft/pick_ban/result_zone.py`, and
  `draft/assignment/target_slot.py` for the right-dock PvP host/pages/current
  common-backed visual result zones and compatibility target-slot alias;
- `ui/app_shell.py` as the shell coordinator that instantiates the PvP
  workspace/right-dock page;
- `tests/run_workspace/pvp/test_deck_preset.py`;
- `tests/run_workspace/pvp/test_weapon_identity.py`;
- `tests/ui/pvp_browser/test_pvp_browser.py`;
- `tests/ui/app_shell/test_app_shell.py` for AppShell routing integration.

Current v0 scope:

- Decks replaces the former `PvP Control` placeholder in the right header.
- Presets persist under root `data/pvp/decks/` as `gtt.pvp_deck_preset`
  JSON. The path is resolved from the repository root, not current working
  directory; the accidental `ui/data/pvp/decks/` path was removed.
- New deck drafts start from all current account characters/weapons and are not
  saved until Save is pressed.
- View mode shows only selected deck members without extra deck-selection
  outlines on every card.
- Edit mode shows all account characters/weapons, with unselected items dimmed.
- The left browser uses the same weapons-first/characters-second grid order,
  filters, card sizing, and spacing as the normal Characters/Weapons browser.
- The right panel uses compact preset rows, in-row expansion, inline
  edit/delete/save/cancel icons, and compact validation/info modeled on the
  Artifact Browser preset flow.
- Save/cancel are explicit; Enter/Esc are scoped to active create/edit on the
  right panel and left deck editor.
- Validation is automatic compact expanded-row status through the existing
  backend `DraftDeck` validator; there is no manual `Validate` button in v0.
- Edit/create mode uses Artifact Browser-style edit viewport styling: the
  weapon/character card grid viewports get the blue edit background, selected
  deck cards get the gold edit-selection border, unselected cards are dimmed,
  and labels/filter rows outside the card viewports must not be tinted.
- `Start local draft` is not part of Decks; Play/setup owns that action.
- Play/setup v0 is implemented. It owns `Start local draft`, creates an
  in-memory local `FreeDraftController`, and switches to Draft.
- Draft board visual MVP is implemented. It renders the backend `unified_pool`
  as a dense image-backed `PixelIconGrid`, exposes shared pool/player scope tabs
  and the normal AppShell character filters, shows two-sided constellation
  badges, exposes a semantic action-colored 22-position order strip, reuses the
  same item adapter for right-panel picks/bans, and can complete the full Free
  Draft schedule locally. The old yellow text-card/debug-summary path has been
  removed.
- Post-draft local flow now uses one scoped normal AppShell build context per
  seat. Character clicks use normal sequential quick-pick, right-panel slot
  clicks select the build target, weapon clicks use the normal selected-slot
  equipment path, and seat Ready commits converted team/weapon assignments
  through the PvP backend controller. When both seats are Ready, timers and the
  future GCSIM route move to the left Draft workspace.

Right-panel architecture status before more PvP growth:

> The global right-panel ownership refactor is complete for current v0 code.
> Keep new PvP right-panel work under `ui/right_panel/pvp/`; keep
> `ui/pvp_browser/` as the left/main PvP workspace. PvP page/stage constants are
> canonical in `ui/right_panel/pvp/_shared.py`. Assignment/Weapon stages now
> use scoped normal AppShell controller/workspace state and the shared
> `RunRightPanelWidget`; the previous custom source/target implementation must
> not return. Artifact Browser and executable scoped GCSIM remain later steps
> on the same scoped pipeline.

Current v0 limitations / later work:

- online;
- History;
- PNG/export result card;
- ruleset cost rendering;
- Gentor/Abyss importer;
- scoped PvP artifact equipment implementation;
- extended GTT JSON artifact+preset import/export QoL;
- scoped PvP GCSIM scoring;
- final styling.
