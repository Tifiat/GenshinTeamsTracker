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
- Current PvP widgets still live in `ui/pvp_browser/window.py`, but the target
  right-panel ownership is `ui/right_panel/pvp/`. The next global right-panel
  refactor should move PvP right-dock pages/stages there while keeping
  `ui/pvp_browser/` focused on the left/main PvP workspace.
- Decks v0 is implemented in `ui/pvp_browser/window.py` as
  `PvpDecksWorkspace` plus `PvpDecksRightPanel`.
  The corrected UI follows the existing Characters/Weapons browser grid on the
  left and the Artifact Browser preset-row/list/edit pattern on the right. It
  persists local deck presets, supports explicit view/edit/save/cancel, and
  validates through the existing backend deck validator.
- Play/local match setup v0 is implemented in `ui/pvp_browser/window.py` as
  a `PvpWorkspace` page plus `PvpPlayRightPanel`. It selects Player 1 and
  Player 2 local deck presets, validates both through backend `DraftDeck`
  conversion, starts an in-memory `FreeDraftController`, and switches to the
  Draft board page.
- Draft board v0 is implemented in `ui/pvp_browser/window.py` as a local
  hot-seat board over the backend Free Draft board projection. It consumes the
  backend `unified_pool` read model, renders one readable character pool,
  displays shared ownership markers on one card, moves picked/banned entries
  into right-panel result zones, and refreshes from the backend controller after
  accepted/rejected actions.
- PvP browsing, deck editing, draft, and post-draft stages must not mutate the
  normal TeamBuilder / Run state unless a future explicit bridge is designed.
- Post-draft Assignment, Weapon assignment, Timers/results, and read-only
  completed result summary v0 are implemented for local hot-seat matches.
  Online play, ruleset costs, immune picks, export/PNG, and PvP History are
  still not implemented.

## Core Model

PvP is a mini-section inside AppShell, not a single flat screen.

- Left/main PvP area: browser/workspace scene.
- Right PvP control panel: current mode controls, deck preset list, validation,
  selected details, setup actions, timers/result controls.
- Source ownership target:
  - `ui/pvp_browser/` owns deck browser grids, the draft board, source pools,
    and main PvP scenes.
  - `ui/right_panel/pvp/` owns fixed right-dock PvP pages and internal
    match-stage panels.

PvP opens into Decks, not directly into Draft.

Top-level PvP right-header pages:

- Decks;
- Play / local match setup;
- Draft.

`Draft` is the active match container. Future post-start match stages should be
internal Draft stages, not additional top-level tabs:

1. Draft / pick-ban.
2. Assignment.
3. Weapon assignment.
4. Artifact equipment.
5. Optional PvP GCSIM.
6. Timers / results.
7. Completed result / export.

Permanent right-header tabs should be added only when their real mode is
implemented. Do not add top-level Team, Timers, Result, Artifacts, GCSIM, or
Match tabs.

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
schedule. It remains a working intermediate board, not the target readable UX.

Current implemented v0:

- Player 1 board;
- Player 2 board;
- current action banner;
- picks/bans pools;
- timeline/action log;
- immune/extra-ban placeholders later.

Right panel remains compact:

- current phase/action;
- legal target count;
- selected card details;
- reset/auto-step/dev controls;
- later room/invite links.

The right panel must not contain the full draft board.

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
- The board renders cards from `to_board_dict()["unified_pool"]["entries"]`,
  marks legal/available/blocked states, and sends legal clicks through the
  backend action payload exposed on the entry.
- Picked/banned entries are omitted from the main pool and rendered in
  right-panel result zones from `unified_pool.result_zones`.
- After each accepted or rejected action, UI state is rebuilt from the backend
  projection.
- When the schedule completes, pick/ban clicks are disabled and final picks,
  bans, and action-log count remain visible.
- After completion, the Draft page can continue through internal Assignment,
  Weapon assignment, Timers/results, and Completed result stages for local
  hot-seat play.
- Online mode, ruleset cost rendering, immune picks, session files, PvP History
  writes, and export are still out of scope.

## Team Assignment

- Assignment v0 is implemented as an internal Draft stage after pick/ban
  completion.
- It keeps PvP-owned in-memory UI state until validation succeeds, then commits
  through `FreeDraftController.set_team_assignment(...)`.
- Left/main area is now the visual source pool: top Player 1 and bottom
  Player 2, each with that player's weapon pool and 8 picked characters as
  image-backed `PixelIconGrid` cards. There are no filters or full-account
  browsers in post-draft stages.
- The PvP right panel is now the target match panel: top Player 1 and bottom
  Player 2, each with two compact 4-character team halves, compact
  portrait-backed target slots, assigned weapon icons, and compact timer/result
  rows. The previous text-button post-draft prototype is no longer the accepted
  visual layer.
- Interaction is simple click source character, click right-panel target slot.
  Re-selecting an already used character moves it instead of duplicating it;
  slots can be cleared.
- Stage controls are low-priority right-panel footer controls; stage
  validation still enables the next-stage button only when both players have
  valid 4+4 assignments.
- No normal character filters, artifact badges, GCSIM block, or normal
  TeamBuilder mutation are part of v0.

## Weapon Assignment

- Weapon assignment v0 is implemented as the next internal Draft stage.
- It commits through `FreeDraftController.set_weapon_assignment(...)` only after
  backend validation accepts both players.
- Each assigned character can be selected, then assigned a compatible weapon
  stack from that player's own left/main source weapon pool.
- Weapon assignment is visual: click a right-panel team character slot, then
  click a compatible source weapon grid card. The assigned weapon icon is shown
  on/near that right-panel slot.
- The UI enforces player ownership, weapon type compatibility, and stack count
  exhaustion before setting local selection state; backend validation remains
  the final authority before continuing.
- Weaponless continuation is blocked by the existing backend contract.

## Artifact Equipment

Artifact equipment is the new product direction for PvP, not an immediate
implementation requirement for this docs-only task.

- After Draft pick/ban plus team and weapon assignment, PvP should support an
  Artifact equipment stage inside Draft.
- Player 1 gets a temporary isolated copy of the current local Artifact Browser
  data/session.
- Player 2 gets a temporary empty Artifact Browser session with the same
  artifact-browser logic.
- Player 2 can import artifacts from JSON into that temporary PvP session.
- PvP artifact data is scoped to the active PvP match/session.
- Changes made inside PvP must not affect the main Artifact Browser, main
  account artifact state, normal live-run builds, or current account equipment.
- The eventual implementation should reuse the existing Artifact Browser logic
  through a scoped PvP adapter/session rather than forking a second Artifact
  Browser.
- PvP right-panel character slots must be designed for character, weapon, and
  artifact mini-zones plus artifact-equipment actions. Do not build a dead-end
  simplified no-artifact target widget.

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

## PvP GCSIM

- Normal live-run GCSIM Browser remains a left workspace tied to current
  live-run teams.
- PvP does not need a separate top-level PvP GCSIM Browser tab.
- PvP can expose GCSIM through a button/action inside the Draft/build flow.
- That action should open or route to a scoped PvP GCSIM stage/panel using PvP
  teams/builds, not normal live-run teams.

## Timers / Results

- Timers/results v0 is implemented as an internal Draft stage after valid team
  and weapon assignment. In the target flow, it follows artifact equipment and
  optional PvP GCSIM when those stages exist.
- The right-panel target zones keep the teams/weapons visible and show compact
  timer inputs per player. Inputs accept `mm:ss` or raw seconds and require
  valid values for both players before finalization.
- Finalization calls `FreeDraftController.set_match_timers(...)`; lower total
  time wins and equal totals draw through the backend result model.
- Factual DPS, restarts, technical-loss UI, bundle/export actions, and GCSIM
  scoring are still future work.

## Export / Result

- Completed result v0 is implemented as a read-only internal Draft stage.
- It stays in the same two-player visual match layout and shows teams,
  assigned weapons, per-player chamber timers/totals, winner/draw, and time
  difference.
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

Completed Decks v0 task:

> PvP Decks mode v0: persistent deck presets + corrected
> Characters/Weapons-style browser and Artifact Browser-style preset list/edit
> flow.

Implemented in:

- `run_workspace/pvp/deck_preset.py`;
- `run_workspace/pvp/weapon_identity.py`;
- `ui/pvp_browser/window.py` (`PvpDecksWorkspace`, `PvpDecksRightPanel`);
- `ui/app_shell.py` as the shell coordinator that instantiates the PvP
  workspace/right-dock page;
- `tests/run_workspace/pvp/test_deck_preset.py`;
- `tests/run_workspace/pvp/test_weapon_identity.py`;
- `tests/ui/pvp_browser/test_pvp_browser.py`;
- `tests/ui/app_shell/test_app_shell.py` for AppShell routing integration.

Current Decks v0 scope:

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
- Draft board v0 is implemented. It renders the backend `unified_pool`, lets the
  user click legal pick/ban targets through the controller, shows right-panel
  pick/ban zones, and can complete the full Free Draft schedule locally.
- Post-draft local flow v0 is implemented inside Draft with the corrected
  two-player visual match layout: left/main source pools for picked characters
  and weapons, right-panel target teams/weapons/timers/results. It reuses
  controller assignment/timer APIs and remains in-memory/PvP-owned.

Next implementation task:

> Post-draft polish and result/export planning. The core local flow now reaches
> completed result in the intended visual match layout; next code work should
> refine usability/review/back affordances, improve visual density, or begin
> export/history only when their contracts are ready.

Next architecture task before more PvP right-panel growth:

> Global right-panel refactor. Move right-dock ownership toward
> `ui/right_panel/{common,live_run,history,pvp,settings}`; place PvP right-panel
> pages and Draft-stage panels under `ui/right_panel/pvp/`; keep
> `ui/pvp_browser/` as the left/main PvP workspace; update imports and matching
> tests in the same task without weakening behavior coverage.

Still out of scope:

- online;
- History;
- PNG/export result card;
- ruleset cost rendering;
- Gentor/Abyss importer;
- scoped PvP artifact equipment and JSON preset import/export QoL;
- scoped PvP GCSIM scoring;
- final styling.
