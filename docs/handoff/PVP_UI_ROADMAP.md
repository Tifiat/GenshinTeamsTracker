# PvP UI Roadmap

Purpose: source of truth for the PvP UI direction before implementation. The
backend/product contract remains in `PVP_V0_CONTRACT.md`; implementation status
remains in `PVP_BACKEND_STATUS.md`.

## Current AppShell Baseline

- A `PvP` workspace tab exists beside Characters / Weapons, Artifacts, and
  GCSIM.
- When PvP is active, the right dock shows `Decks`, `Play`, and the global
  Account action instead of Abyss / DPS Dummy.
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
  conversion, starts an in-memory `FreeDraftController`, and shows only a
  compact placeholder/summary.
- PvP browsing, deck editing, draft, and post-draft stages must not mutate the
  normal TeamBuilder / Run state unless a future explicit bridge is designed.
- The real draft board and pick/ban clicks are still not implemented.

## Core Model

PvP is a mini-section inside AppShell, not a single flat screen.

- Left/main PvP area: browser/workspace scene.
- Right PvP control panel: current mode controls, deck preset list, validation,
  selected details, setup actions, timers/result controls.

PvP opens into Decks, not directly into Draft.

Internal PvP stages:

- Decks;
- Play / local match setup;
- Draft;
- Team assignment;
- Timers / result.

Permanent right-header tabs should be added only when their real mode is
implemented. Do not add empty Draft, Result, or Match tabs.

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

Card identity note:

- Do not rely on one shared character card to represent both players'
  constellation/cost state during Draft.
- Prefer separate Player 1 and Player 2 boards because opponent portraits and
  constellation data may come from the opponent account, and HoYoLAB images may
  already include constellation overlays.

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
- The left Play page shows setup/active-draft placeholder text and does not
  duplicate the full form.
- No session files, PvP history, normal TeamBuilder mutation, or network access
  are performed by Play v0.

## Draft Stage

Draft board v0 is the next implementation target.

Future Draft belongs mostly in the left/main area:

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

## Team Assignment

- After Draft, do not mutate normal TeamBuilder automatically.
- Team assignment is PvP-owned state.
- Left/main area shows picked roster and half/team slots.
- Right panel shows validation, selected slot/card details, ready/continue
  controls, and later auto-assign/dev controls.

## Timers / Results

- Reference timer/restart UIs are messy; GTT should make this stage cleaner.
- Left/main area shows teams, rooms, and result overview.
- Right panel shows timers, restarts, manual result controls, and
  bundle/export actions.
- Final result should eventually support a clean image/report export.

## Reference-Site Conclusions

Stable conclusions from Gentor/Abyss review:

- Gentor deck/profile screens support the Decks split: main grid for
  characters/weapons, side panel for account/preset/cost summaries.
- Gentor/Abyss draft screens support a large main board for both players, compact
  controls/status outside the board, and staged flow: draft creation/setup,
  pick/ban, team assignment, timers/results.
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
  in-memory local `FreeDraftController`, and shows a compact active-draft
  summary/placeholder instead of the real board.

Next implementation task:

> PvP Draft board v0: render the backend Free Draft board/read-model projection
> and add the first real pick/ban interaction path.

Still out of scope:

- draft board;
- pick/ban clicks;
- live `FreeDraftController` UI action wiring;
- online;
- History;
- ruleset cost rendering;
- Gentor/Abyss importer;
- GCSIM scoring;
- final styling.
