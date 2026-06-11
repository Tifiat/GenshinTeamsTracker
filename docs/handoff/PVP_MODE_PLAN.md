# PvP Mode Plan Draft

Planning date: 2026-06-11

Status: planning history. The active PvP v0 implementation contract is now
`docs/handoff/PVP_V0_CONTRACT.md`. Reference-site findings live in
`docs/handoff/PVP_REFERENCE_SITE_AUDIT.md`.

This file captures the earlier PvP direction, known contradictions, risks, and
decisions that led into the final v0 contract.

No runtime code, tests, UI, parser/importer, or network/server implementation
should be started from this file alone.

## Sources Read For This Pass

Required handoff entrypoints:

- `CODEX.md`
- `TODO.md`
- `docs/handoff/README.md`
- `docs/handoff/PVP_RULESETS_AUDIT.md`
- `docs/handoff/FAR_FUTURE_TODO.md`

Relevant deeper context discovered by search:

- `docs/handoff/APP_SHELL_WORKSPACE_PLAN.md`
- `docs/handoff/RUN_WORKSPACE_SNAPSHOT_CONTRACT.md`
- `docs/handoff/ACCOUNT_SQLITE_STORAGE.md`
- `docs/handoff/TESTS.md`
- `hoyolab_export/tournament_ruleset.py`
- `hoyolab_export/tournament_ruleset_report.py`
- `tests/hoyolab_export/tournament/test_tournament_ruleset.py`
- `samples/rulesets/minimal_ruleset.json`

Search terms included PvP, tournament, draft, deck, lobby, ruleset, Gentor,
Abyss Draft, multiplayer, hot-seat, P2P, and relay.

## Scope And Non-Scope

PvP in GenshinTeamsTracker should mean tournament-style deck/draft/ruleset play.
It is not "GCSIM team vs team benchmark" and should not be driven by simulator
DPS as the primary product model.

First development direction:

- local/offline Hot-seat / Ghost Deck Free Draft;
- Player 1 deck generated/exported from the current local account;
- Player 2 deck either copied from Player 1 for self-test/debug or imported
  from another player's deck JSON;
- the same draft action/session contract should later support online mode;
- hot-seat is a real offline training/beta slice, not throwaway scaffolding.

Explicit non-scope for the first PvP work:

- no runtime code in this planning task;
- no UI in this planning task;
- no network/server code in this planning task;
- no Gentor API importer as the first product step;
- no custom TypeScript/script execution;
- no GCSIM-vs-GCSIM benchmark model;
- no ruleset compiler that automatically builds a legal deck from the whole
  account;
- no full TournamentRuleset execution as the first draft prototype;
- no P2P/player-host architecture as the primary online path;
- no chat, global online player list, private invites, spectators, moderators,
  or judges in the first online prototype.

Important distinction:

- A ruleset defines constraints, costs, tiers, bans/picks, schedules, scoring,
  and validation rules.
- A player manually builds a tournament deck under those constraints.
- A Deck Validator reports whether the deck is legal and why not.
- A future AI/bot deck optimizer is far-future only.
- Free Draft v0 is the exception: it may use all available deck/account
  characters and weapons because costs and tournament restrictions are disabled.

## Proposed PvP v0 Architecture

This section names contracts, not final class/module names.

### DraftDeck

Represents one player's exported/imported draft pool.

Likely fields:

- schema version and deck id/name;
- optional ruleset compatibility metadata;
- source metadata;
- character entries;
- weapon entries;
- validation summary produced by import/export or a later validator;
- privacy-safe display metadata only.

DraftDeck should not contain artifacts, raw HoYoLAB dumps, auth data, local
private paths, or UI storage internals.

### DraftCharacter

Represents one selectable character in a deck.

Likely fields:

- stable character id when available;
- display name;
- element;
- weapon type;
- rarity;
- level, if exported under the privacy policy;
- constellation, if exported under the privacy policy;
- optional local match status after import.

### DraftWeapon

Represents one selectable weapon in a deck.

Likely fields:

- stable weapon id when available;
- display name;
- weapon type;
- rarity;
- level, if exported under the privacy policy;
- refinement, if exported under the privacy policy;
- optional local match status after import.

Weapon stack/instance identity is unresolved. The existing account model has
observed weapon stacks, not guaranteed unique weapon instances. PvP deck
contracts must avoid depending on fake local weapon instance ids.

### DraftRuleset / FreeDraftRuleset

`FreeDraftRuleset` should be a small built-in configuration for the first
prototype:

- ban count;
- first player;
- pick batch size;
- total pick count / team size;
- optional immune character list;
- no costs;
- no tiers;
- no weapon bans;
- no score/match format.

Future `TournamentRulesetV1` can layer on top once the draft/session/action
contracts are stable.

### DraftAction

Append-only user intent accepted by the reducer.

Possible shape:

```json
{
  "schema_version": 1,
  "action_id": "local-unique-id",
  "sequence": 12,
  "seat": "player_1",
  "type": "ban_character",
  "target": {
    "kind": "character",
    "id": "10000021",
    "display_name": "Amber"
  },
  "payload": {},
  "client_time_utc": "optional-debug-only",
  "state_hash_before": "optional-for-online",
  "state_hash_after": "filled-after-acceptance"
}
```

First action types probably include:

- `ban_character`;
- `pick_character`;
- `undo` only if explicitly approved later;
- `assign_weapon` only if weapon assignment is included in v0;
- `finish_draft` or equivalent only after the contract needs it.

### DraftSessionState

Deterministic reducer state built from initial decks, ruleset config, and
accepted actions.

Likely fields:

- schema version;
- session id;
- seats and deck refs;
- ruleset config;
- phase: setup, banning, picking, weapon_assignment, complete, aborted;
- active seat;
- remaining bans/picks per seat;
- global character bans;
- picked characters per seat;
- availability cache or derived availability report;
- validation errors/warnings;
- current state hash;
- last accepted sequence.

### ActionLog

Append-only accepted action log.

Required properties:

- replaying the same initial state plus action log produces the same session
  state and state hash;
- invalid/out-of-turn/duplicate actions are rejected before append;
- local hot-seat, fake transport tests, and future relay transport all use the
  same accepted action format;
- action logs can later support reconnect and result confirmation.

### SeatController

A small abstraction for where the next action comes from:

- local human seat;
- hot-seat second local seat;
- ghost/imported deck seat, initially still human-driven unless a future bot is
  approved;
- future remote network seat.

SeatController should not own reducer rules. It should only propose actions and
receive accepted state updates.

### Transport Boundary

Transport should be separate from the reducer:

- none/local transport for hot-seat;
- fake/in-memory transport for tests;
- future relay/server transport for online rooms.

This keeps the local prototype useful and makes remote play a later source of
actions, not a different game engine.

## Draft Deck JSON Contract Draft

This is provisional and privacy-safe by default. Names are placeholders for
discussion, not final schema names.

```json
{
  "schema_version": 1,
  "kind": "gtt.draft_deck",
  "deck_name": "My Free Draft Deck",
  "ruleset": {
    "ruleset_id": "free_draft_v0",
    "compatibility": "free_draft"
  },
  "source": {
    "source_type": "local_account_export",
    "app": "GenshinTeamsTracker",
    "exported_at_utc": "2026-06-11T00:00:00Z",
    "game_version": "",
    "language": "ru-ru",
    "notes": ""
  },
  "characters": [
    {
      "character_id": "10000021",
      "display_name": "Amber",
      "element": "PYRO",
      "weapon_type": "BOW",
      "rarity": 4,
      "level": 90,
      "constellation": 6
    }
  ],
  "weapons": [
    {
      "weapon_id": "15401",
      "display_name": "Favonius Warbow",
      "weapon_type": "BOW",
      "rarity": 4,
      "level": 90,
      "refinement": 5
    }
  ]
}
```

Include at most:

- stable character/weapon ids when available;
- display names;
- element, weapon type, rarity;
- character level and constellation, if approved as default export fields;
- weapon level and refinement, if approved as default export fields;
- source metadata needed for compatibility/debug.

Explicitly exclude:

- artifacts;
- artifact stats;
- artifact DB rows;
- raw HoYoLAB account dumps;
- HoYoLAB cookies, auth, browser profiles, request headers, or tokens;
- local absolute paths;
- local storage row ids unless a local-only matching layer later requires them;
- unrelated settings or account profile state.

Open design note: existing project security notes say clean outputs may contain
ids, names, levels, rarity, refinements, and constellations. A public deck export
is more sensitive than a local debug output, so the final PvP contract should
decide whether levels/constellations/refinements are default, optional, or
redactable.

## Free Draft v0 Contract Draft

Free Draft v0 should be configurable but intentionally simple.

Candidate config fields:

```json
{
  "schema_version": 1,
  "ruleset_id": "free_draft_v0",
  "ban_count": 0,
  "first_player": "player_1",
  "pick_batch_size": 1,
  "total_pick_count": 8,
  "team_size": 4,
  "immune_character_ids": []
}
```

The values above are examples only. The final defaults need user approval.

Expected draft phases:

1. Setup: load/validate Player 1 and Player 2 decks, choose config.
2. Ban phase: players alternate character bans for configured ban count.
3. Pick phase: players alternate character picks by configured batch size.
4. Weapon assignment / team assembly: optional for v0; likely later unless
   approved.
5. Draft result: action log plus picked pools/teams, possibly exportable.

Availability semantics:

- A character ban always bans that character for all players.
- Player decks are separate.
- Global bans affect availability across both decks.
- A picked non-immune character becomes unavailable to the opponent.
- A picked immune character remains available to the opponent.
- Immune characters exist because some tournament formats treat specific
  characters as sufficiently equal across accounts/constellations, so mirror
  picks are allowed.
- A player cannot pick a character missing from that player's deck.
- A player cannot ban or pick a globally banned character.
- A player cannot pick a non-immune character already picked by the opponent.
- A player cannot repeat the same pick in their own picked list unless a future
  ruleset explicitly supports duplicates, which is not expected for v0.

Action validation should check:

- session phase;
- active seat / turn owner;
- action sequence or duplicate action id;
- target exists in the relevant deck or global catalog;
- target has not been banned/picked illegally;
- ban/pick quotas;
- pick batch completion and next-seat transition;
- deterministic state hash after each accepted action.

## Future Ruleset Layering

Future `TournamentRulesetV1` should layer on top of the Free Draft action/session
model rather than replacing it.

Ruleset features to support later:

- character costs by constellation C0-C6;
- optional level 95/100 extra costs;
- weapon costs by refinement R1-R5;
- character-specific weapon cost overrides;
- tiers and tier restrictions;
- deck point config;
- manual deck validation report;
- exact pick/ban schedules;
- cost-dependent ban counts;
- immune characters;
- joker/extra bans;
- weapon bans;
- permanent/special bans;
- challenge/scoring metadata;
- multi-game match format;
- timer/result aggregation rules;
- unsupported/custom procedural/script rules as metadata or warnings, not
  executed in MVP.

The MVP direction should be manual deck building plus validator:

- The app can help export/import a deck.
- The app can validate that deck against a ruleset.
- The app should not auto-compile a legal deck from the whole account in v0.
- A future bot/optimizer is research only and belongs outside the MVP contract.

Existing code note: `hoyolab_export/tournament_ruleset.py` and related tests
already contain an early backend ruleset parser/report. Treat that as parked
ruleset research/prototype code. It should not drive the first PvP Free Draft
stage unless the user explicitly approves pulling it forward.

## Online / Network Future Contract Draft

Online mode should be a later transport over the same action protocol.

Preferred product direction:

- cloud/free relay room server as the primary path;
- public lobby list;
- create lobby / join lobby;
- optional PIN/password;
- open public lobbies are valid;
- exactly two seats in v0: Player 1 and Player 2;
- no chat;
- no global online player list;
- no private invites in the first online prototype;
- no spectators, judges, or moderators in the first online prototype.

P2P/player-host direction:

- do not make P2P the primary path;
- P2P is mainly useful if server cost becomes a problem;
- P2P adds NAT, firewall, security, reliability, support, and UX complexity;
- LAN/direct IP, Tailscale, or user-hosted relay can remain future optional/dev
  fallbacks, not the initial product route.

Future relay/server responsibilities:

- create lobbies;
- list public lobbies;
- join lobbies;
- expire stale lobbies/rooms;
- enforce max two players in v0;
- store temporary room state and append-only action log;
- validate action sequence and current turn owner;
- reject invalid, duplicate, stale, or out-of-turn actions;
- broadcast accepted actions/state updates;
- support reconnect from action log and/or snapshots;
- avoid any private account storage.

Server/privacy rules:

- do not store HoYoLAB auth, cookies, browser profiles, request headers, or
  tokens;
- do not store local file paths;
- do not store artifact DB rows or raw artifact stats;
- do not store raw private account dumps;
- only temporary deck/draft/session/action data required for the room should be
  present, and retention should be short.

Provider choices such as Cloudflare, Firebase, Supabase, a custom server, or a
temporary hosted relay should remain unspecified until the network stage unless
the user wants an architecture decision earlier.

## PvP Match And Result Direction

Long-term PvP is not just draft. It should eventually support:

- multiple draft/game rounds;
- players running Abyss or challenge attempts after draft;
- timer/result entry;
- match winner by configured scoring rule;
- likely combined timers over games for some formats;
- both-player confirmation against an unchanged state hash;
- saved PvP run history in a future History/PvP subtab;
- exportable result images.

For the first implementation stage, do not include match/timer/scoring unless
the user explicitly wants a data placeholder. A safer first finish line is:

- deck import/export;
- Free Draft session;
- action log replay;
- draft result summary.

Relationship to existing Run Workspace:

- PvP match/timer/history can later attach to the Run Workspace snapshot model
  as a PvP scenario/result type.
- TeamBuilder/Right Panel should be reused only after PvP has a buildable
  picked pool/team.
- PvP should not mutate full-account team state silently while the draft is
  still in deck/opponent phases.
- GCSIM output can be shown later as context, but it is not the PvP win condition
  or first product model.

## Testing Strategy For Eventual Implementation

No tests are added in this planning task. Future implementation should add
targeted tests for:

- deck export validation;
- deck import validation;
- privacy exclusions in deck export;
- unknown character matching;
- ambiguous character matching;
- unknown weapon matching;
- ambiguous weapon matching;
- duplicate deck entries;
- Free Draft action reducer;
- turn order;
- phase transitions;
- duplicate bans;
- duplicate picks;
- global ban behavior;
- non-immune pick blocks opponent;
- immune pick allows mirror pick;
- pick batch size behavior;
- total pick/team-size quota behavior;
- action log replay;
- deterministic state hash;
- hot-seat two-seat session;
- copied Player 1 deck self-test flow;
- imported Player 2 deck flow;
- future remote-seat simulation with fake/in-memory transport;
- reconnect/replay behavior once relay transport exists.

Likely test locations:

- `tests/run_workspace/pvp/` or a future PvP backend owner for reducer/session
  tests;
- `tests/hoyolab_export/tournament/` only for ruleset import/validation tests;
- UI tests only after an approved UI surface exists.

## Provisional Roadmap To MVP

This roadmap is not final. It should be revised after the open questions below
are answered.

Stage A: planning contract finalized.

- Review this draft with the user.
- Decide the open questions.
- Write the final PvP v0 development contract and roadmap.

Stage B: deck JSON export/import backend and validation report.

- Define final deck JSON schema.
- Export a local account draft deck.
- Import another player's deck JSON.
- Report unknown/ambiguous matches and privacy-safe field usage.

Stage C: Free Draft reducer/action log backend.

- Implement the Free Draft config.
- Implement deterministic reducer, validation, action log, and replay.
- Keep transport local/fake only.

Stage D: hot-seat draft prototype.

- Build a minimal local UX after backend contract is stable.
- Support Player 2 as copied Player 1 deck and/or imported JSON, depending on
  approved defaults.
- End at draft result/action log unless match/timer placeholder is approved.

Stage E: basic deck builder/validator for tournament rules.

- Manual deck building under ruleset constraints.
- Validation report: costs, tiers, bans, weapon rules, unsupported features.
- Use existing parser/report research only where it matches the approved
  contract.

Stage F: relay lobby/network transport.

- Public lobby list.
- Create/join lobby.
- Optional PIN.
- Two-player room.
- Relay accepted actions over the same protocol.

Stage G: PvP match/timer/history integration.

- Multiple games/rounds.
- Challenge/Abyss attempt timing.
- Scoring/winner rules.
- Confirmation by state hash.
- PvP history/export surfaces.

## Inconsistencies, Gaps, And Questions

This section is intentionally direct. These answers should be settled before the
final PvP v0 implementation contract is written.

### 1. First PvP step conflicts with old ruleset-import recommendation

Gap: `PVP_RULESETS_AUDIT.md` recommends starting with manual XLSX/CSV/JSON
ruleset import or a parser prototype. The current direction says first practical
PvP should be local Hot-seat / Ghost Deck Free Draft, with no Gentor import or
full ruleset execution first.

Why it matters: starting with ruleset import optimizes for tournament source
coverage, while starting with Free Draft optimizes for playable draft/session
contracts. The implementation order and module boundaries differ.

Question: Should the final PvP v0 contract explicitly park ruleset import until
after Free Draft reducer/hot-seat works?

### 2. Existing TournamentRulesetV1 code is ahead of the requested first stage

Gap: `hoyolab_export/tournament_ruleset.py`, its report CLI, tests, and sample
JSON already exist. The current task says not to start TournamentRuleset parser
implementation yet.

Why it matters: future agents could incorrectly treat this code as the active
PvP v0 foundation, even though the requested direction is to start with Free
Draft/deck/session contracts.

Question: Should existing ruleset parser/report code remain parked as research,
or should Stage E later adapt it into the approved PvP contract?

### 3. Network direction changed from P2P-heavy exploration to relay-first

Gap: `FAR_FUTURE_TODO.md` lists LAN/direct IP, P2P, STUN/signaling/relay, and
optional server if resources justify it. The current direction prefers a
cloud/free relay room server as the primary product path, with P2P only as a
future optional/dev fallback.

Why it matters: the online contract, security model, user flow, and testing
strategy differ significantly.

Question: Should the final contract replace the old P2P-first exploration with
relay-first online planning?

### 4. Lobby privacy/access wording needs a precise stance

Gap: old notes are cautious about connectivity, while the current direction says
open public lobbies are valid and PIN is optional, not mandatory.

Why it matters: mandatory PIN/private rooms produce a different first network UX
than public lobby discovery.

Question: Should online v0 default to public visible lobbies with optional PIN?

### 5. Online roles need to be cut down for v0

Gap: old notes mention player 1, player 2, spectator, moderator/judge, and host.
The current direction says first online prototype has only two seats and no
spectators/judges/moderators.

Why it matters: action permissions, room state, UI, and server capacity are much
simpler with only two seats.

Question: Should spectators/judges/moderators be explicitly excluded until a
post-v0 tournament-admin stage?

### 6. Free Draft defaults are not decided

Gap: the current direction lists configurable ban count, first player, pick
batch size, total pick count/team size, and optional immune list, but does not
finalize defaults.

Why it matters: tests, UI labels, saved settings, and example decks need stable
defaults.

Questions:

- What should the default Free Draft ban count be?
- Who should pick/ban first by default: Player 1 or Player 2?
- Should default pick batch size be 1 or 2?
- What should the default total pick count/team size be?

### 7. Weapon drafting/assignment timing is unclear

Gap: older PvP notes say select weapons only from deck weapons after draft. The
current direction says players assign weapons / assemble teams later.

Why it matters: including weapons in v0 expands deck JSON, UI, validation,
availability, and TeamBuilder integration. Characters-only v0 is much smaller.

Question: Should Free Draft v0 be characters-only and stop at picked character
pools, or should it include weapon assignment immediately?

### 8. Immune character semantics are clear, but v0 inclusion is not

Gap: the requested semantics are clear: bans are global, non-immune picks block
the opponent, immune picks allow mirror picks. It is not decided whether Free
Draft v0 should expose immune character settings or keep them future-only.

Why it matters: immune support affects reducer rules, validation tests, and
configuration UI even if the default list is empty.

Question: Should Free Draft v0 include an immune character list from day one,
or should immune handling wait for imported tournament rulesets?

### 9. Player 2 ghost deck behavior needs a default

Gap: Player 2 can be a copy of Player 1 for self-test/debug or an imported deck
JSON from another player.

Why it matters: export/import can be delayed if copy-P1 is the only first debug
path, but a beta-testable ghost mode likely needs import.

Question: Should Player 2 default support copy Player 1 deck, imported JSON, or
both in the first hot-seat prototype?

### 10. Deck JSON privacy policy is not final

Gap: project security notes allow clean outputs to contain ids, names, levels,
rarity, refinements, and constellations. A PvP deck JSON may be shared publicly,
so these fields need explicit user approval.

Why it matters: level, constellation, and refinement reveal account strength and
may be required for tournament legality.

Questions:

- What exact account data is safe to expose in exported deck JSON?
- Should levels/constellations/refinements be included by default?
- Should those fields be optional/redactable for Free Draft?

### 11. Character and weapon identity matching is unresolved

Gap: potential ids come from HoYoLAB, HoYoWiki/static catalogs, Gentor, GCSIM,
or local app mappings. Display names may be localized or aliased.

Why it matters: draft availability must match the same character across two
separate decks. False matches or missed matches can break bans/picks.

Question: What should be the primary stable identity for character and weapon
matching in deck JSON, and what fallback alias behavior is acceptable?

### 12. Weapon instance semantics are risky

Gap: existing account storage observes weapon stacks and current equipment, but
does not guarantee unique weapon instances. PvP deck JSON wants weapon level and
refinement, but assignment could require copy counts or instance-like choices.

Why it matters: duplicate weapons and multiple refinements can be represented
incorrectly if the deck contract pretends stable local weapon instances exist.

Question: Should PvP v0 model weapons as owned stack entries by
weapon-id/refinement/level/count, or avoid weapon assignment until account
weapon identity is stronger?

### 13. Relationship to TeamBuilder and Right Panel is not concrete

Gap: AppShell notes say PvP likely remains separate at first and can reuse the
build panel after a PvP pool/team exists. The current plan does not decide the
first PvP surface.

Why it matters: wiring draft results into TeamBuilder early can create coupling
to full-account team state, while a separate draft result keeps v0 smaller.

Question: Should the first hot-seat prototype stop at draft result/action log,
or should it immediately feed selected characters into TeamBuilder/right panel?

### 14. PvP match/timer/scoring should probably be postponed, but confirm

Gap: long-term PvP includes Abyss/challenge attempts, timers/results, scoring,
winner, and history. The first draft prototype likely does not need that.

Why it matters: match scoring pulls in Run Workspace snapshots, History, Abyss
timer concepts, and result confirmation before draft basics are proven.

Question: Should PvP match/timer scoring be postponed until after draft works?

### 15. History integration is only a future placeholder

Gap: `RUN_WORKSPACE_SNAPSHOT_CONTRACT.md` mentions future PvP history
dimensions, but no PvP snapshot schema exists.

Why it matters: adding too much history shape now can freeze the wrong model;
adding no placeholder may make later integration harder.

Question: Should Stage B-D include only an action-log/draft-result export, with
PvP History postponed to Stage G?

### 16. GCSIM relationship must stay narrow

Gap: current architecture keeps GCSIM active for simulator results, while PvP
needs tournament/deck/draft/ruleset behavior. Some users may expect PvP to mean
sim-vs-sim.

Why it matters: a GCSIM-first PvP design would optimize for configs and DPS,
not human tournament flows and draft legality.

Question: Should the final contract explicitly state that GCSIM may be
informational later but is not part of PvP v0 win/scoring logic?

### 17. Ruleset validation and deck validation boundaries need naming

Gap: existing parser/report validates ruleset source data. The new direction
needs deck validation under a ruleset.

Why it matters: "ruleset validation" and "deck validation" are different
operations and should not share confusing UI/report names.

Question: Should the final contract define separate reports for
RulesetValidationReport and DeckValidationReport?

### 18. Account artifacts are excluded now, but future PvP result exports may
need builds

Gap: deck JSON should exclude artifacts and artifact stats. Long-term PvP
results may need team/build snapshots for exported results and history.

Why it matters: sharing a draft deck is privacy-light; sharing a match result
may intentionally include build/run information. These should be separate
contracts.

Question: Should deck JSON permanently exclude artifacts, while future PvP
match result snapshots use a separate opt-in build/run export contract?

### 19. Online provider choice is intentionally unresolved

Gap: relay-first planning does not choose Cloudflare, Firebase, Supabase, custom
server, or another provider.

Why it matters: provider choice affects auth, persistence, deployment, costs,
rate limits, and app packaging.

Question: Should the final PvP v0 contract leave provider unspecified until
Stage F, or should provider research be included before backend work begins?

### 20. Source-of-truth handoff placement changed

Gap: older PvP material lived in `FAR_FUTURE_TODO.md` and
`PVP_RULESETS_AUDIT.md`. This file is now the current PvP planning draft.

Why it matters: future agents need a clear starting point and should not treat
older far-future notes as the active PvP implementation order.

Question: Should `PVP_MODE_PLAN.md` be treated as the current PvP planning
source of truth until the final PvP v0 contract replaces it?
