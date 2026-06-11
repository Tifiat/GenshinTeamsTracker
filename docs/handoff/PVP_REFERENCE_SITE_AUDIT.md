# PvP Reference Site Audit

Research date: 2026-06-11

Scope: lightweight architecture research for the PvP v0 contract. This pass
used public pages, public API responses, Playwright/Chrome page probes, and
client bundle inspection. No GTT runtime code, app startup, local account data,
HoYoLAB auth, or tests were used.

Sandbox helper:

- `tools/experiments/pvp_site_audit/pvp_site_probe.py`
- Browser profiles and captures are generated under that sandbox and ignored by
  `tools/experiments/pvp_site_audit/.gitignore`.

## Sites Inspected

Abyss Cup / Abyss Draft:

- `https://abyss.darte.gg/`
- `https://abyss.darte.gg/drafts`
- `https://abyss.darte.gg/assets/index-DMdlKM8O.js`
- `https://abyss.darte.gg/assets/draft-flow.component-C8r3eyHd.js`
- `https://abyss.darte.gg/assets/form-create-draft.component-DqDlvusi.js`
- `https://abyss.darte.gg/assets/draft-system-form.component-DV4PFr1o.js`
- `https://abyss.darte.gg/assets/draft-systems-CHs2GPD4.js`
- `https://abyss.darte.gg/assets/draft-systems-api-C4_Bio9e.js`

Gentor:

- `https://gentor.vercel.app/`
- `https://gentor.vercel.app/planilhas`
- `https://gentor.vercel.app/salas`
- `https://gentor.vercel.app/partidas`
- `https://gentor.com.br/planilha`
- `https://gentor.com.br/planilha/3`
- `https://gentor.com.br/planilha/26`
- relevant deployed chunks including `chunk-TSAC52OC.js`,
  `chunk-WK6LPPE3.js`, `chunk-Y6KV3TJ3.js`, `chunk-ZQAACK2I.js`, and shared
  `chunk-BHL4UV4O.js`.

## Findings For GTT

### Domain Separation

Both reference products support the same high-level split GTT should use:

- ruleset / draft system / spreadsheet;
- account or roster/deck;
- room/draft session;
- pick/ban flow;
- team or room assignment after picks;
- result/timer/finish phase;
- online roles and links later.

This supports a GTT model where `Ruleset`, `DraftDeck`, `DraftSession`,
`DraftAction`, `TeamAssignment`, and `MatchResult` are separate contracts.

### Abyss Cup / Abyss Draft

Observed client concepts:

- session phases:
  - `NOT_STARTED`
  - `STAGE`
  - `PREBAN`
  - `PICKS`
  - `TEAMS`
  - `PAUSED`
  - `FINISHED`
- phase/action kinds:
  - `BAN`
  - `PICK`
  - `PREBAN`
  - `IMMUNE`
  - `IMMUNE_BAN`
  - `IMMUNE_PICK`
  - `MIRROR`
  - `UNDO`
  - `CONTINUE`
  - `PAUSE`
- roles:
  - `player0`
  - `player1`
  - `judge`
  - `spectator`
- create-draft links are generated separately for player 0, player 1, judge,
  spectator, and spectator-with-controls.
- draft creation includes selected players, selected draft system, absolute
  immune list, and a count for generated drafts.
- rules/draft-system data includes cost settings, character/weapon counts,
  character/weapon costs, team weapon max cost, preban cost step, pick time,
  reserve time, phases/flow, absolute immune, and teams/match settings.
- visible text includes ready/timer concepts such as "The timer will start once
  all players are ready".

Implications for GTT:

- Hot-seat v0 can hide judge/spectator, but the long-term role model should not
  pretend only two roles will ever exist.
- GTT should model `PREBAN`, `PICKS`, `TEAMS`, and `FINISHED` as separate phases
  even in offline mode.
- Immune/mirror support can be postponed, but the ruleset layer should reserve
  a future place for it.
- The first contract should use a schedule/flow list, not only
  `pick_batch_size`, because real draft systems have mixed pick/ban phases.

### Gentor

Observed public pages/routes:

- `/planilhas`: public spreadsheet/ruleset list.
- `/salas`: room/draft route, mostly empty without auth but client code is
  present.
- `/partidas`: match route, mostly empty without auth but client code is
  present.
- `/planilhas/{id}/decks/novo` and `/planilhas/{id}/decks/simulacao` appear in
  client routing.

Observed public API:

- `GET https://gentor.com.br/planilha`
- `GET https://gentor.com.br/planilha/{id}`

Examples fetched:

- id `3`, `Abyss Fight Club`, 81 characters, 89 weapons, 6 tiers.
- id `26`, `x1 visionario`, 70 characters, 100 weapons, 6 tiers.

Observed ruleset/config fields:

- `regra`, commonly `FRANCESA`;
- `desafio`, commonly `ABISMO`;
- `limitePontosPersonagens`;
- `baseBansIniciais`;
- `linhaCorteBanInicial`;
- `intervaloPontos`;
- `intervaloJoker`;
- `maxJokers`;
- `localBanArma`;
- `quantidadeBansArma`;
- `usaScript`;
- `script`;
- character C0-C6 costs;
- level 95/100 extra costs;
- weapon R1-R5 costs;
- character-specific weapon overrides;
- tiers and tier restrictions.

Observed room/match/deck client concepts:

- room/draft configuration has separate `jogador1` and `jogador2` config;
- per-player draft config includes extra bans, joker bans, initial bans, middle
  bans, weapon ban count, and special-ban totals;
- `localBanArma` controls weapon-ban location;
- room/match code computes current draft order from config with helpers named
  like `montarOrdemPickBanComConfig` and `obterOrdensDraftAtuais`;
- post-pick/finalization code handles selected picks and weapon refinements,
  including local storage for saved refinements;
- deck pages generate/copy a Luna Draft code and show deck points;
- teams/users can be associated with account/deck data.

Implications for GTT:

- Gentor planilha JSON does not provide one simple flat "turn 1, turn 2" list.
  GTT should support either a normalized explicit schedule or a config-to-
  schedule adapter.
- Rulesets define deck constraints and draft order inputs. They are not the PvP
  engine.
- Deck validation and ruleset validation must be different reports.
- Weapon deck data is first-class, not an optional decoration.

## Local Repo Reality Check

Current repository state:

- `hoyolab_export/tournament_ruleset.py` exists and parses normalized/Gentor-like
  ruleset data.
- `hoyolab_export/tournament_ruleset_report.py` reports ruleset validation.
- `tests/hoyolab_export/tournament/test_tournament_ruleset.py` covers parser and
  ruleset validation behavior.
- `samples/rulesets/minimal_ruleset.json` is the only ruleset sample file found.

Important boundary:

- Existing `TournamentRulesetV1` code validates source ruleset data and simple
  catalog-name matching.
- It is not a PvP engine.
- It is not a deck validator.
- It does not yet own draft schedule execution, deck legality under rules,
  player/seat identity, action log, team assignment, timer result, or online
  room state.

## Contract Consequences

The PvP v0 contract should:

- implement a full offline loop, not only pick/ban;
- include characters and weapons in decks from the start;
- treat the active player identity as a seat/role in the session, with nickname
  as display metadata;
- use stable internal character/weapon ids in deck JSON and localize display
  names from the local app catalog, falling back to English;
- postpone Traveler support;
- postpone immune/mirror mode execution while reserving ruleset space for it;
- model weapons as owned stack/copy entries, not fake unique instances;
- define a default explicit draft schedule that picks 8 characters per player;
- split ruleset validation from deck validation;
- keep hot-seat judge/spectator out of v0 UI and session flow, but reserve
  roles for future online mode.
