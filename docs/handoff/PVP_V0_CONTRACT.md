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
   - hot-seat confirmation is local;
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

Do not wire picked characters directly into the normal right panel as a normal
full-account team. The post-draft pool should behave like a restricted local
roster: only the 8 picked characters and deck weapons are available.

AppShell/Right Panel reuse can happen after the restricted PvP pool/team model
exists. Avoid mutating the user's normal TeamBuilder state during draft.

## Existing Ruleset Code Boundary

Existing files:

- `hoyolab_export/tournament_ruleset.py`
- `hoyolab_export/tournament_ruleset_report.py`
- `run_workspace/pvp/ruleset_applicability.py`
- `run_workspace/pvp/ruleset_costs.py`
- `tests/hoyolab_export/tournament/test_tournament_ruleset.py`
- `samples/rulesets/minimal_ruleset.json`
- `samples/pvp/rulesets/`

Current role:

- parked parser/report prototype for ruleset source data;
- useful evidence for costs/tiers/Gentor-like fields;
- PvP-side applicability and cost-preview reports for research fixtures;
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

## Current Backend Implementation Status

Implemented through 2026-06-12:

- `run_workspace/pvp/deck.py`: v0 deck dataclasses, strict JSON
  root/schema/kind loading, and stable `to_dict()` roundtrip.
- `run_workspace/pvp/validation.py`: `DeckValidationReport`, stable issue
  codes, Free Draft v0 character-count validation, conservative Traveler
  rejection for known account Traveler ids / English Traveler names, and weapon
  stack/count validation.
- `run_workspace/pvp/schedule.py`: data-driven default Free Draft v0 schedule
  and expected per-seat pick/ban counts.
- `run_workspace/pvp/session.py`: deterministic local reducer, append-only
  accepted action log, replay helper, state hash, and backend-only post-draft
  team/weapon assignment validators.
- `run_workspace/pvp/match_result.py`: room/chamber timer totals, lower-time
  winner calculation, draw state, and technical-loss result state.
- `run_workspace/pvp/full_loop_smoke.py`: deterministic backend-only full-loop
  smoke/dev harness. Command: `python -m run_workspace.pvp.full_loop_smoke`.
  It loads the synthetic sample decks, validates them, applies the default
  schedule with a scripted action log, validates teams/weapons, records fixture
  timers, verifies replay/state hash, and prints a compact report.
- `run_workspace/pvp/ruleset_applicability.py`: report-only bridge from parsed
  `TournamentRulesetV1` source data into current PvP v0 capability flags and
  blockers. It is separate from `RulesetValidationReport` and
  `DeckValidationReport`.
- `run_workspace/pvp/ruleset_costs.py`: deck cost-preview helper for
  `TournamentRulesetV1` character/weapon costs. It uses ids first, reports
  display-name fallback as a mapping gap, supports level 95/100 extras, and
  supports character-specific weapon overrides for assigned weapon previews.
- `run_workspace/pvp/ruleset_applicability_smoke.py`: deterministic
  backend-only ruleset applicability/cost smoke. Command: `python -m
  run_workspace.pvp.ruleset_applicability_smoke`.
- `run_workspace/pvp/account_deck_export.py`: backend-only Free Draft deck
  exporter from current local account SQLite runtime data. The production
  provider reads `account_characters` and `account_weapon_observed_stacks`
  through `hoyolab_export.account_storage` adapters; fake providers are used by
  tests. It exports stable character/weapon ids, display names, element, weapon
  type, rarity, character level/constellation, weapon level/refinement/count,
  Free Draft ruleset metadata, and privacy-safe source metadata. It excludes
  artifacts, auth/cookies, raw account dumps, local paths, SQLite row ids, and
  generated/private storage internals.
- `run_workspace/pvp/account_deck_export_smoke.py`: dry-run local account export
  smoke. Command: `python -m run_workspace.pvp.account_deck_export_smoke`.
  Default mode prints a compact summary and writes no deck JSON. `--write`
  writes under generated/private `data/pvp/decks/` unless `--output` is given.
  Traveler is skipped by the same conservative v0 policy as deck validation.
- `run_workspace/pvp/free_draft_planner.py`: deterministic backend-only
  smoke/autoplay helper. It asks the existing reducer to accept each Free Draft
  v0 ban/pick, then builds simple team and weapon assignments for validation.
  This is not a product draft bot or optimizer.
- `run_workspace/pvp/account_full_loop_smoke.py`: backend-only local-account
  full-loop smoke using the account deck exporter. Command: `python -m
  run_workspace.pvp.account_full_loop_smoke`. It copies the exported account
  deck into an independent player 2 scope, plans a reducer-accepted Free Draft,
  verifies replay/state hash, validates teams/weapons, and records fixture
  timers/results. Default mode writes no files; `--json` prints a compact
  structured report without dumping the full deck.
- `samples/pvp/`: synthetic deck fixtures for tests only; ids are not
  production catalog ids. Current fixtures have 12 distinct characters per
  player and enough per-player weapon stack counts for the scripted full-loop
  smoke.
- `samples/pvp/rulesets/`: tiny synthetic ruleset fixtures only. One fixture
  aligns ids with the PvP sample deck for clean cost previews; one sanitized
  Gentor-like fixture intentionally has source-local ids so name fallback is
  reported.
- `tests/run_workspace/pvp/`: focused backend tests for the above contracts.

Still not implemented: UI, AppShell/right-panel integration, online transport,
deck builder/exporter UI, real Gentor/Abyss importer, richer ruleset execution,
automatic schedule derivation from public rulesets, full localized Traveler
detection/support, GCSIM scoring, and PvP History.

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

Stage F: local hot-seat UI.

- Setup.
- Draft board.
- Pools.
- Team/weapon assignment.
- Timer/result summary.

Stage G: deck builder/exporter UI.

- Build a deck from the existing imported account characters/weapons.
- Validate under Free Draft and later rulesets.
- Export deck JSON.
- Status: backend account export exists; no UI/deck-builder surface is wired.

Stage H: iterate toward offline PvP MVP.

- Improve UX.
- Add richer ruleset adapters.
- Decide when to pull existing `TournamentRulesetV1` forward.

Online relay and History remain later major stages after the offline PvP loop is
usable.
