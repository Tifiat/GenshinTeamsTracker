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
  hot-seat board over the backend Free Draft board projection. Legal character
  cards are clickable, accepted actions refresh from the backend controller,
  and the completed state shows final picks/bans and action-log summary.
- Current Draft board v0 is playable but intentionally still an intermediate
  technical board: it shows two per-seat grids and is not the final readable
  draft UX.
- PvP browsing, deck editing, draft, and post-draft stages must not mutate the
  normal TeamBuilder / Run state unless a future explicit bridge is designed.
- Team assignment, timers/results, online play, ruleset costs, immune picks,
  and PvP History are still not implemented.

## Core Model

PvP is a mini-section inside AppShell, not a single flat screen.

- Left/main PvP area: browser/workspace scene.
- Right PvP control panel: current mode controls, deck preset list, validation,
  selected details, setup actions, timers/result controls.

PvP opens into Decks, not directly into Draft.

Top-level PvP right-header pages:

- Decks;
- Play / local match setup;
- Draft.

`Draft` is the active match container. Future post-start match stages should be
internal Draft stages, not additional top-level tabs:

1. Draft / pick-ban.
2. Assignment.
3. Timers / results.
4. Export / result.

Permanent right-header tabs should be added only when their real mode is
implemented. Do not add top-level Team, Timers, Result, or Match tabs.

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

- The durable source of truth for the unified pool should be a dedicated
  backend board projection section such as `unified_pool`.
- UI may prototype from existing `seats[*].cards`, but the next code contract
  task should add backend projection fields first.
- Future `unified_pool` entries should include stable `character_id`,
  `owner_seats`, `base_seat`, per-seat display metadata, legal/action data,
  pool/result zone, picked/banned owner, action index, and optional reason codes.
- Do not put local image paths into the backend identity/read-model contract.

Current v0 scope:

- Draft tab appears only because the real board exists.
- Draft without an active session shows an empty state directing the user back
  to Play.
- Starting from Play creates an in-memory `FreeDraftController` and switches to
  Draft.
- The board renders cards from `to_board_dict()`, marks legal/available/picked/
  banned/blocked states, and sends legal clicks through
  `FreeDraftController.apply_current_action(...)`.
- After each accepted or rejected action, UI state is rebuilt from the backend
  projection.
- When the schedule completes, pick/ban clicks are disabled and final picks,
  bans, and action-log count remain visible.
- No team assignment UI, timers/results UI, online mode, ruleset cost rendering,
  immune picks, session files, or PvP History writes are part of Draft board v0.

## Team Assignment

- After Draft, do not mutate normal TeamBuilder automatically.
- Team assignment is PvP-owned state.
- This is an internal Draft stage after pick/ban completion.
- Left/main area should use a split Player 1 / Player 2 layout.
- Each side shows only that player's 8 picked characters plus two team/half
  areas.
- Weapon assignment belongs in this stage and uses that player's deck weapon
  pool.
- No normal character filters, artifact badges, or GCSIM block are needed here.
- Right panel shows validation, selected slot/card details, ready/continue
  controls, and later auto-assign/dev controls.

## Timers / Results

- This is an internal Draft stage after assignment.
- Reference timer/restart UIs are messy; GTT should make this stage cleaner.
- Left/main area shows teams, rooms/chambers, and result overview.
- Right panel shows timers, restarts, manual result controls, and
  bundle/export actions.
- Prefer compact horizontal timer rows such as `T1 [09:01]`, `T2 [08:45]`,
  `T3 [09:12]` for both players, plus total time, factual DPS where available,
  and winner.

## Export / Result

- This is the final internal Draft stage.
- Show a read-only result card/report preview with players, teams, weapons,
  chamber times, totals, and winner.
- Final result should eventually support a clean image/report export.
- PNG/export is later; do not implement it before the core assignment/timer
  state exists.

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
- Draft board v0 is implemented. It renders the backend projection, lets the
  user click legal pick/ban targets through the controller, and can complete the
  full Free Draft schedule locally. It is an intermediate technical board; the
  next readable Draft UX target is unified-pool based.

Next implementation task:

> Backend/read-model `unified_pool` projection contract for Free Draft board:
> add tests and update the committed sample fixture before refactoring
> `PvpDraftWorkspace` to the unified visual pool.

Still out of scope:

- team assignment UI;
- timers/results UI;
- online;
- History;
- ruleset cost rendering;
- Gentor/Abyss importer;
- GCSIM scoring;
- final styling.
