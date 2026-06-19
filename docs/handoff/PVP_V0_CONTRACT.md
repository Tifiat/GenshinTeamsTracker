# PvP v0 Development Contract

Contract date: 2026-06-11

Status: approved direction for the first PvP implementation stage, based on
`PVP_MODE_PLAN.md`, user decisions on 2026-06-11, and the reference site audit
in `PVP_REFERENCE_SITE_AUDIT.md`.

This contract is for a full offline/hot-seat PvP loop. It is still a prototype
foundation, not the final polished MVP UI.

## Product Definition

PvP in GenshinTeamsTracker is tournament-style deck/draft/ruleset play.

It is not:

- GCSIM team-vs-team benchmark;
- an automatic deck optimizer;
- a Gentor clone tied to Gentor ids;
- online-first networking;
- a full tournament-admin system in v0.

The first implementation target is local Hot-seat / Ghost Deck PvP:

1. Select or define a ruleset/free-draft config.
2. Load two player decks as JSON.
3. Run pick/ban draft locally.
4. Produce each player's picked 8-character pool.
5. Assign picked characters into two teams of four.
6. Assign weapons from the player's deck weapon pool.
7. Record room/chamber timers for both players.
8. Compute winner by lower total timer and show seconds difference.

The match room also needs a stable Abyss period identity. In local/hot-seat
mode both seat profiles must agree on that identity before play; if they do
not, the application resolves the current period and requires stale source
data to be refreshed. In future online mode the room server advertises the
authoritative current period during create/join, and a client with mismatched
Abyss data cannot enter the playable Draft until it updates. This is a future
admission/validation mechanism, not part of the currently implemented local
backend reducer.

Hot-seat is both a development path and a real offline/training mode. It should
not be throwaway code.

## Non-Scope For v0

Do not implement in v0:

- online relay/lobby/server;
- P2P/direct player-host mode;
- account system for GTT PvP;
- chat;
- global player list;
- private invites;
- spectator/judge UI;
- immune/mirror draft mode;
- Traveler support;
- custom TypeScript/script execution;
- Gentor API importer as a required first path;
- GCSIM execution as PvP scoring;
- saved PvP history/browser integration.

Online mode, spectators, judges, invitations, richer rulesets, history, exports,
and GCSIM-assisted analysis are later stages.

## Reference Sites

GTT should borrow the product structure, not the exact implementation.

Reference findings:

- Abyss Draft has phases such as `PREBAN`, `PICKS`, `TEAMS`, `FINISHED`, roles
  such as `player0`, `player1`, `judge`, `spectator`, and action kinds such as
  `BAN`, `PICK`, `IMMUNE`, `IMMUNE_BAN`, `IMMUNE_PICK`, `MIRROR`, and `UNDO`.
- Gentor separates rulesheets (`planilhas`), decks, rooms (`salas`), and matches
  (`partidas`).
- Gentor rulesheets provide constraints and config inputs, not one universal
  flat turn list.
- Both sites treat characters and weapons as first-class PvP data.

Detailed research lives in `docs/handoff/PVP_REFERENCE_SITE_AUDIT.md`.
The current source/applicability matrix lives in
`docs/handoff/PVP_RULESET_SOURCE_MATRIX.md`.

## Core Boundaries

### Ruleset

A ruleset is a rule source. It defines:

- deck constraints;
- character costs;
- weapon costs;
- cost limits;
- tier restrictions;
- draft schedule or config inputs used to derive a schedule;
- weapon-ban policy;
- future immune/mirror/joker/extra-ban behavior;
- future match/scoring metadata.

A ruleset is not the PvP engine and must not auto-build a deck from the account.

### DraftDeck

A deck is a manually chosen preset of allowed characters and weapons.

The player builds a deck under the ruleset constraints. The app validates the
deck and reports why it is legal or illegal.

For Free Draft prototype mode, the deck may include all imported account
characters and observed weapon stacks because costs/constraints are disabled.

### DraftEngine

The engine applies actions:

- ban;
- pick;
- assign team;
- assign weapon;
- ready/confirm;
- record timer/result.

The engine should be deterministic and should validate the current phase, seat,
target availability, and action sequence. It does not know Gentor ids, UI
widgets, or HoYoLAB language names.

### DraftSession

A session binds:

- two seats;
- two deck JSON payloads;
- one ruleset/free config;
- current phase;
- action log;
- current state.

In hot-seat v0, the active identity is the seat: `player_1` or `player_2`.
Nicknames are display metadata. Future online mode may use user-entered unique
nicknames in settings, but session authority still comes from assigned room
seat/role.

### MatchResult

A match result is separate from draft. It contains:

- assigned teams;
- assigned weapons;
- room/chamber timers;
- total timers;
- winner;
- seconds difference;
- validation/technical-loss state when a player cannot form legal teams or
  assign required weapons.

History persistence is later.

## Seat And Role Identity

Primary session identity is the seat/role, not a global user account:

- `player_1`
- `player_2`

Future online roles may add:

- `spectator_n`
- `judge`

Hot-seat v0 has no spectators or judges. Reserve the role vocabulary for future
online mode, but do not implement those flows yet.

Nicknames:

- optional for hot-seat;
- likely required in future online settings;
- used for display, lobby rows, and result summaries;
- not the primary key inside a session.

It must be valid to run `tifiat` vs `tifiat` with two separate deck scopes.

## Character Identity

Deck JSON should store stable character ids, not localized display names as the
primary key.

Display names:

- should be resolved locally from the user's app/account/catalog language;
- should fall back to English when local match/localization is missing;
- should not force a Chinese/Russian/Portuguese name from the exporting player
  onto the importing player.

Traveler is not supported in v0. Treat Traveler as absent from the PvP deck
builder/exporter until a dedicated Traveler identity model is designed.

Gentor ids:

- are source-adapter ids only;
- must not be primary deck/session ids;
- may be stored only in source metadata if needed later for import/debug.

## Weapon Identity

Weapons are part of PvP v0.

Do not model fake unique weapon instances. The current account model has
observed weapon stacks, not guaranteed unique weapon instance ids.

Use stack/copy entries:

```json
{
  "weapon_id": "15401",
  "display_name": "Favonius Warbow",
  "weapon_type": "BOW",
  "rarity": 4,
  "level": 90,
  "refinement": 5,
  "count": 2
}
```

Semantics:

- `count` is how many copies of that exact observed stack can be assigned;
- if the user did not import/observe/export all weapons, that is a deck-building
  problem for the player;
- free-cost weapons may be used up to the available count if included in the
  deck;
- if a player cannot assign legal weapons to required characters, the session
  should report invalid/technical-loss state rather than silently inventing
  copies.

## Deck JSON Contract

Provisional shape:

```json
{
  "schema_version": 1,
  "kind": "gtt.pvp_deck",
  "deck_name": "Example deck",
  "ruleset_ref": {
    "ruleset_id": "free_draft_v0",
    "ruleset_name": "Free Draft v0"
  },
  "player": {
    "nickname": "tifiat"
  },
  "source": {
    "app": "GenshinTeamsTracker",
    "language": "ru-ru",
    "exported_at_utc": "2026-06-11T00:00:00Z"
  },
  "characters": [
    {
      "character_id": "10000099",
      "display_name": "Mavuika",
      "element": "PYRO",
      "weapon_type": "CLAYMORE",
      "rarity": 5,
      "level": 90,
      "constellation": 1,
      "cost": null
    }
  ],
  "weapons": [
    {
      "weapon_id": "12513",
      "display_name": "Example Claymore",
      "weapon_type": "CLAYMORE",
      "rarity": 5,
      "level": 90,
      "refinement": 1,
      "count": 1,
      "cost": null
    }
  ]
}
```

Rules:

- character and weapon ids are primary matching fields;
- display names are metadata/fallback only;
- local app language should control display;
- fallback display language is English;
- include level/constellation/refinement because they affect pick/ban and deck
  legality;
- exclude artifacts, artifact stats, HoYoLAB auth/cookies, raw account dumps,
  local file paths, and local storage row ids.

## Visual Asset Policy

Character and weapon identity is data-first:

- character identity is the stable `character_id` / game id;
- weapon identity uses the observed stack identity contract;
- images, portraits, icons, and badges are optional presentation assets;
- draft/session logic and validation must work without image paths.

Allowed future presentation paths:

- local v0 can resolve images from the host account/catalog assets;
- export bundles may later include visual assets or an asset manifest;
- future online opponent decks may provide optional visual refs/assets;
- a bundled/common PvP icon pack keyed by `character_id` is allowed.

Do not assume a future server hosts images. Prefer local cache, bundled/common
fallback assets, or client-side asset resolution unless a later online design
proves server-hosted media is needed.

The main shared-card risk is visual ambiguity: a HoYoLAB constellation badge on
one corner can be confused with the other player's constellation. A unified
draft card is acceptable when it exposes explicit owner markers and places the
second player's constellation/ownership badge separately.

## Deck Validation

Define `DeckValidationReport` separately from existing
`RulesetValidationReport`.

Ruleset validation checks whether a ruleset source is structurally usable.

Deck validation checks whether one player's deck is legal under one ruleset:

- character ids known;
- weapon ids known;
- character count/min/max;
- weapon count/min/max;
- character cost total;
- weapon cost total;
- constellation/level cost rules;
- refinement/level cost rules;
- duplicate/stack rules;
- unsupported Traveler entries;
- unsupported ruleset features;
- missing required weapon coverage where relevant.

Free Draft v0 may have very light validation, but the report type should exist
from the beginning.

## Default Free Draft v0

Free Draft v0 is the first offline mode, but it should still model the real
shape of PvP.

Defaults:

- no cost limits;
- no tiers;
- no immunes;
- no Traveler;
- two players;
- two teams per player;
- four characters per team;
- eight picked characters per player;
- characters and weapons included in decks;
- total bans per player default: 3;
- middle-draft bans per player default: 1;
- prebans per player default: total bans minus middle-draft bans = 2.

Default schedule:

```json
[
  {"phase": "preban", "seat": "player_1", "actions": [{"type": "ban_character"}]},
  {"phase": "preban", "seat": "player_2", "actions": [{"type": "ban_character"}]},
  {"phase": "preban", "seat": "player_1", "actions": [{"type": "ban_character"}]},
  {"phase": "preban", "seat": "player_2", "actions": [{"type": "ban_character"}]},

  {"phase": "pick", "seat": "player_1", "actions": [{"type": "pick_character"}]},
  {"phase": "pick", "seat": "player_2", "actions": [{"type": "pick_character"}, {"type": "pick_character"}]},
  {"phase": "pick", "seat": "player_1", "actions": [{"type": "pick_character"}, {"type": "pick_character"}]},
  {"phase": "pick", "seat": "player_2", "actions": [{"type": "pick_character"}, {"type": "pick_character"}]},

  {"phase": "pick", "seat": "player_1", "actions": [{"type": "pick_character"}, {"type": "ban_character"}]},
  {"phase": "pick", "seat": "player_2", "actions": [{"type": "pick_character"}, {"type": "ban_character"}]},

  {"phase": "pick", "seat": "player_1", "actions": [{"type": "pick_character"}, {"type": "pick_character"}]},
  {"phase": "pick", "seat": "player_2", "actions": [{"type": "pick_character"}, {"type": "pick_character"}]},
  {"phase": "pick", "seat": "player_1", "actions": [{"type": "pick_character"}, {"type": "pick_character"}]},
  {"phase": "pick", "seat": "player_2", "actions": [{"type": "pick_character"}]}
]
```

Result:

- Player 1 bans 3 characters and picks 8 characters.
- Player 2 bans 3 characters and picks 8 characters.
- Player 2 receives compensation through the sequence: Player 1 opens with one
  pick, then most turns are two actions.

This schedule should be data, not hardcoded UI flow, so later rulesets can
replace it.

## Availability Semantics

Character availability:

- a character ban always bans that character globally for both players;
- a picked non-immune character becomes unavailable to the opponent;
- immune/mirror rules are not active in v0;
- a player can only pick characters in that player's deck;
- the same character id in two different player decks represents separate
  ownership but one shared draft identity for ban/non-immune pick blocking.
- UI read-models should expose that shared draft identity directly instead of
  forcing every UI to infer it from two duplicated per-seat grids.

Weapon availability:

- weapons are not globally banned in Free Draft v0;
- each player assigns weapons only from that player's deck weapon pool;
- assignment consumes available stack count;
- weapon type compatibility must be enforced;
- future rulesets may add weapon bans or weapon cost restrictions.

## v0 Phases

1. Setup
   - choose Free Draft v0 or a simple ruleset config;
   - load Player 1 deck JSON;
   - load Player 2 deck JSON;
   - set optional nicknames;
   - validate decks;
   - act as the offline/local lobby before draft start.

2. Preban
   - run schedule preban actions.

3. Picks
   - run schedule pick and middle-ban actions.

4. Team assignment
   - each player splits 8 picked characters into two teams of four;
   - no full-account roster characters are available here.

5. Weapon assignment
   - each player assigns weapons from that player's deck weapon pool;
   - weapon type and stack counts are enforced.

6. Ready/confirm
   - each seat becomes ready only after all 8 character slots have compatible
     assigned weapons;
   - Ready converts the seat-scoped normal build state to backend
     `PlayerTeamAssignment` and `PlayerWeaponAssignment`, then validates through
     the existing Free Draft controller;
   - hot-seat confirmation and panel collapse state are local UI state;
   - both seats ready transitions the left Draft workspace to timers/GCSIM
     routing while the right side remains the build/details panel;
   - online ready/confirm is future transport behavior.

7. Timers/results
   - record room/chamber timers for both players;
   - compute total timer;
   - lower total timer wins;
   - show seconds difference.

8. Result summary
   - show players, teams, weapons, timers, winner, and validation state;
   - no durable History write in v0.

## Action Log

Keep an action log from the first backend implementation.

Reasons:

- undo/debug;
- deterministic replay;
- future online transport;
- future judge/spectator controls;
- future result confirmation by state hash.

v0 action types should cover at least:

- `ban_character`;
- `pick_character`;
- `assign_team_slot`;
- `assign_weapon`;
- `set_timer`;
- `set_ready`;
- `finish_match`.

`undo` can be implemented later, but the data model should not prevent it.

## UI Direction

First UI should be local/offline and may be simple.

Required surfaces:

- local lobby/setup/load decks;
- deck validation report;
- draft board with ban/pick schedule;
- picked/banned pools;
- team assignment for each player;
- weapon assignment for each player;
- timer/result entry;
- result summary.

Draft read-model direction:

- The playable Draft board v0 may keep its current per-seat board projection as
  an intermediate contract.
- The target readable Draft UX should use one unified pool of unique
  `character_id` values plus right-panel result zones for picks and bans.
- The durable board/read-model projection has a dedicated `unified_pool`
  section so UIs do not reconstruct it ad hoc.
- `unified_pool` entries include stable `character_id`, `owner_seats`,
  `base_seat`, per-seat display metadata such as constellation/level/rarity/
  display name/status, current legal/action data, result zone/status, picked or
  banned owner, action/schedule index where applicable, and optional reason
  codes.
- The backend read model should not include local image paths as identity.
  Presentation layers can resolve optional icons separately; the board
  projection validator rejects visual path/icon/image identity keys in
  `unified_pool`.

Draft result zones:

- Player 1 picks;
- Player 1 bans;
- Player 2 picks;
- Player 2 bans.

Picked and banned characters should be represented in those zones and should
not remain in the active pool as ordinary available cards.

Do not wire picked characters into the user's normal live-run team state. The
post-draft pool should behave like a restricted local roster: only the 8 picked
characters and that player's deck/scoped weapons are available.

The MVP build-flow target is not a new PvP imitation of the normal roster/right
panel. It is the existing AppShell Characters/Weapons, Artifact Browser, GCSIM
Browser, and Abyss right-panel pipeline running against a scoped PvP
run/equipment context. Local players read source account data from the normal
app database without duplicating it, while equipment choices inside PvP live in
per-seat runtime state that starts empty. Imported/remote players read source
data from their package/provider and also get per-seat runtime equipment state.
PvP must not mutate the user's normal `TeamBuilderState`, normal
current-equipment tables, normal Artifact Browser state, or normal GCSIM
summaries.

PvP profile/provider model:

- local hot-seat players may use the current app SQLite database directly only
  as source data;
- local hot-seat weapon/artifact equipment state is scoped per seat and must not
  write to the normal account equipment tables;
- imported or future remote players use a scoped provider backed by a managed
  temporary SQLite database for source data plus a fresh scoped runtime
  equipment state for the match;
- `.gttpvp` is the PvP profile package format. It is a versioned ZIP with
  `manifest.json`, `decks.json`, and `account_slice.sqlite`;
- package export deduplicates characters/weapons across selected deck presets
  and keeps identity data-first;
- package import validates archive entries and materializes only the SQLite DB
  member to a temp path. It must not restore into the main app database.

The restricted PvP roster must still use stable backend identity:
`character_id` for characters and the observed weapon-stack identity contract
for weapons. Localized names, image paths, and display strings are presentation
data only.

## Existing Ruleset Code Boundary

Existing files:

- `hoyolab_export/tournament_ruleset.py`
- `hoyolab_export/tournament_ruleset_report.py`
- `run_workspace/pvp/ruleset_applicability.py`
- `run_workspace/pvp/ruleset_costs.py`
- `run_workspace/pvp/ruleset_balance.py`
- `tests/hoyolab_export/tournament/test_tournament_ruleset.py`
- `samples/rulesets/minimal_ruleset.json`
- `samples/pvp/rulesets/`

Current role:

- parked parser/report prototype for ruleset source data;
- useful evidence for costs/tiers/Gentor-like fields;
- PvP-side applicability, cost-preview, and report-only deck/session-bundle
  ruleset/balance application reports for research fixtures;
- not the PvP engine;
- not deck validation;
- not draft schedule execution.

Future work may adapt this code, but do not force PvP v0 to inherit its current
shape if a cleaner `run_workspace/pvp` backend boundary is better.

## Online Future Boundary

Online mode comes after the local UI/UX is working.

Preferred path:

- relay room server;
- public lobby list;
- create/join lobby;
- optional PIN;
- open lobbies are valid;
- two player seats first;
- no chat/player-list/invites first.

Future online can add:

- spectators;
- judges;
- invite links;
- moderation controls;
- reconnect from action log;
- server-side action validation.

Hot-seat v0 must not implement online roles, but should not use names that make
future roles impossible.

## History Boundary

Do not implement PvP History in v0.

PvP History belongs in the future shared History browser, as a dedicated PvP tab
alongside Abyss/DPS Dummy history. It should not be a standalone PvP-only
history window.

v0 can produce an in-memory/session result summary only.

## Backend Status

Current implementation details, module inventory, smoke commands,
generated/private paths, test commands, and known backend gaps live in
`docs/handoff/PVP_BACKEND_STATUS.md`.

This contract remains the stable product/backend boundary. Do not keep a
file-by-file implementation log here.

## Testing Strategy

When implementation starts, add tests before or alongside UI:

- deck JSON load/validation;
- character id matching and English fallback metadata;
- weapon stack/count validation;
- unsupported Traveler rejection;
- ruleset validation vs deck validation separation;
- default schedule expansion;
- action reducer turn order;
- global character bans;
- non-immune pick blocks opponent;
- per-player weapon assignment consumes only that player's stack counts;
- team assignment requires two teams of four;
- timer total and winner calculation;
- action log replay.
- local-account full-loop smoke uses fake providers in tests and real account
  data only in the manual smoke command.
- session bundle JSON roundtrip and verifier replay checks for tampered actions,
  hashes, missing decks, and unknown draft systems.
- ruleset/balance application reports for id/fallback/unmatched mapping,
  character and weapon costs, unsupported/report-only ruleset features, and
  compact session-bundle summaries.

Likely test owner:

- `tests/run_workspace/pvp/` for PvP engine/session/deck/match behavior.
- Keep `tests/hoyolab_export/tournament/` for ruleset source parser/report
  behavior only.

## Provisional Implementation Stages

Stage A: contracts and reference audit.

- `PVP_REFERENCE_SITE_AUDIT.md`
- this `PVP_V0_CONTRACT.md`

Stage B: backend data contracts.

- `DraftDeck`
- `DraftCharacter`
- `DraftWeaponStack`
- `DeckValidationReport`
- `DraftSchedule`
- `DraftSessionState`
- `DraftAction`
- `MatchResult`
- Status: implemented as backend-only foundation in `run_workspace/pvp/`.

Stage C: deck JSON import and sample deck fixtures.

- Load two deck JSON files.
- Allow development flow where Player 2 receives a copied/manually edited deck
  JSON.
- Do not require deck builder UI before reducer work.
- Status: JSON loading, synthetic sample fixtures, and backend local-account
  Free Draft export are implemented; deck builder/exporter UI remains future
  work.

Stage D: Free Draft v0 reducer/action log.

- Default schedule above.
- Ban/pick validation.
- Picked pool output.
- Status: implemented for local deterministic reducer/replay/action log.

Stage E: team and weapon assignment backend.

- Two teams of four per player.
- Weapon type and stack-count validation.
- Status: implemented as backend validators without mutating normal TeamBuilder
  or AppShell state.

Stage F: Free Draft controller/projection backend.

- Stable backend API for future local UI.
- Create hot-seat/ghost sessions from decks, explicit account export, or bundle.
- Project current requirement, progress, legal targets, draft state,
  assignments, timers/result, and issue codes as JSON-friendly data.
- Status: implemented as backend-only controller plus board/read-model bridge.
  The UI-facing board projection lives at `run_workspace/pvp/free_draft_board.py`
  and is exposed by controller methods `to_board_projection(debug=False)` and
  `to_board_dict(debug=False)`. It includes draft-system/status/current
  requirement, progress, per-seat deck summaries and card statuses, global
  pools, backend-owned `unified_pool` entries/result zones, action-log rows,
  timeline rows, and compact assignment/result summary. Stable card statuses
  are `available`, `legal_target`, `globally_banned`, `picked_by_self`,
  `picked_by_opponent`, `blocked_by_opponent_pick`, `unavailable`, `invalid`,
  and `unsupported_traveler`; unified-pool statuses/zones are documented in
  `PVP_BACKEND_STATUS.md`. A committed UI-contract sample lives at
  `samples/pvp/ui_contract/free_draft_board_projection_sample.json`, with
  initial, after-two-actions, and final/result board states. Board projection
  dictionaries can be checked with
  `validate_free_draft_board_projection_dict(...)`.
- Next UI step: refactor the Draft workspace to consume `unified_pool` for the
  readable visual pool and right-panel pick/ban zones.

Stage G: local hot-seat UI.

- Setup.
- Draft board, currently playable through the full schedule as an intermediate
  per-seat technical board.
- Future readable Draft UI: unified character pool plus right-panel picks/bans.
- Team/weapon assignment.
- Timer/result summary.

Stage H: deck builder/exporter UI.

- Build a deck from the existing imported account characters/weapons.
- Validate under Free Draft and later rulesets.
- Export deck JSON.
- Status: backend account export exists; no UI/deck-builder surface is wired.

Stage I: iterate toward offline PvP MVP.

- Improve UX.
- Add richer ruleset adapters only after real usable tournament source files
  exist.
- Decide when to pull existing `TournamentRulesetV1` forward.

Online relay and History remain later major stages after the offline PvP loop is
usable.
