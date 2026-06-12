# PvP UI Roadmap

Purpose: source of truth for the PvP UI direction before implementation. The
backend/product contract remains in `PVP_V0_CONTRACT.md`; implementation status
remains in `PVP_BACKEND_STATUS.md`.

## Current AppShell Baseline

- A `PvP` workspace tab exists beside Characters / Weapons, Artifacts, and
  GCSIM.
- When PvP is active, the right dock uses PvP-specific controls instead of
  Abyss / DPS Dummy.
- Account remains a global shell action in the right header.
- The current PvP workspace and right panel are placeholders only.
- PvP browsing, deck editing, draft, and post-draft stages must not mutate the
  normal TeamBuilder / Run state unless a future explicit bridge is designed.

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

UI label: RU `Колоды`, EN `Decks`.

Decks is the next real PvP UI task after the placeholder and is the entry point
into PvP.

Left/main area:

- Base the visual and asset-data approach on the existing Characters / Weapons
  browser.
- Show characters and weapons from account browser/runtime data.
- View mode shows only members of the active deck preset.
- Edit mode shows all account characters and weapons.
- In edit mode, selected items are normal/highlighted and unselected items are
  dimmed.
- Clicking in edit mode toggles membership in the deck preset.
- Characters and weapons should be separate sections.
- Costs/ruleset visuals are reserved for later.

Right panel:

- The Decks tab/control replaces the placeholder `PvP Control` when implemented.
- Create deck preset.
- List deck presets.
- Expand the selected preset into info, similar in spirit to Artifact Browser
  preset/sidebar behavior.
- Selected preset info owns:
  - name;
  - ruleset/cost system selector;
  - initially only `No rules / Free Draft`;
  - character count;
  - weapon count;
  - validation/status;
  - future character/weapon cost summary;
  - later edit, validate, start local draft, and export actions.
- The ruleset/cost selector belongs inside expanded deck preset info, not as an
  unrelated global control.

## Deck Preset Persistence

Use `data/pvp/decks/` for local PvP deck presets. The first Decks UI task may
implement this persistence.

Persistence rules:

- The format must be versioned.
- Do not store localized display names, image paths, or local machine paths as
  identity.
- Character identity should be stable `character_id`.
- Weapon identity should use the account/runtime weapon identity already used by
  the backend, likely `weapon_fingerprint` plus any needed stable weapon id
  metadata. Existing `DraftDeck` v1 serializes observed stack fields rather than
  fake instance ids, so UI persistence must convert without inventing a second
  weapon identity model.
- Persistence must either reuse/convert to the existing `DraftDeck` backend
  contract or clearly define a thin UI preset wrapper that converts to
  `DraftDeck`.
- Avoid creating a second incompatible deck format.

Existing backend deck contract:

- `schema_version = 1`;
- `kind = "gtt.pvp_deck"`;
- `deck_name`;
- `ruleset_ref.ruleset_id = "free_draft_v0"`;
- `characters[].character_id`;
- `weapons[]` as observed weapon stacks;
- no artifacts, auth/cookies, raw account dumps, local paths, or SQLite row ids.

Suggested UI preset fields to verify before implementation:

- `schema_version`;
- `deck_id`;
- `name`;
- `ruleset_id`, initially `free_draft_v0` / no-rules;
- `characters`;
- `weapons`;
- `created_at`;
- `updated_at`;
- optional `notes` / `dev_source`.

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

- Do not add Play as an empty tab until it is implemented.
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

## Draft Stage

Draft board is not the next implementation target.

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

## Next Implementation Task

Next implementation task:

> PvP Decks mode v0: persistent deck presets + main browser view/edit skeleton.

Scope:

- replace `PvP Control` placeholder with Decks right panel;
- add deck preset persistence in `data/pvp/decks/`;
- show account characters/weapons in the PvP Decks workspace;
- implement view/edit mode;
- show selected/unselected visual state;
- validate through existing backend where possible.

Out of scope:

- draft board;
- pick/ban clicks;
- live `FreeDraftController` wiring;
- online;
- History;
- ruleset cost rendering;
- Gentor/Abyss importer;
- GCSIM scoring;
- final styling.
