# Far Future TODO

Purpose: park non-MVP ideas that should not load into normal task planning.
Read this file only when the user asks about far-future ideas, PvP/tournament
expansion, monetization/support, draft bots, or wants to add a new speculative
idea.

## Tournament / PvP

- PvP is experimental and important long-term, but do not mix it into MVP before
  normal run/history/simulator features work well.
- General PvP flow:
  - select/import tournament ruleset;
  - build deck according to rules;
  - enter lobby;
  - picks/bans draft;
  - after draft, move to team composition;
  - compose teams only from picked characters;
  - select weapons only from deck weapons;
  - account artifacts are unrestricted by default;
  - enter timers/results;
  - confirm results;
  - export verified result image.
- Future custom tournament system idea: balance not only by character cost/tier
  but also by account artifact strength. Keep this as design/research, not
  immediate implementation.
- PvP ruleset audit exists at `docs/handoff/PVP_RULESETS_AUDIT.md`. Gentor
  exposes structured public JSON via `https://gentor.com.br/planilha` /
  `/planilha/{id}` with character C0-C6 costs, weapon R1-R5 costs,
  character-specific weapon overrides, tiers/restrictions, draft config, and
  optional TypeScript draft script.
- Backend `TournamentRulesetV1` model and validation report exist in
  `hoyolab_export/tournament_ruleset.py` and
  `hoyolab_export/tournament_ruleset_report.py`. Command:
  `python -m hoyolab_export.tournament_ruleset_report --ruleset-json samples/rulesets/minimal_ruleset.json`.
  MVP accepts normalized JSON and simple CSV files, reports
  missing/duplicate/unknown/unsupported fields, and does not execute
  third-party TypeScript scripts.
- XLSX import and Gentor website/API adapter remain future work after the
  internal schema/report are useful. Next PvP step is UI/import flow or deck
  validation, not another source search.
- Deck builder should evaluate total cost, tier constraints, invalid choices,
  and why a deck is invalid.
- Lobby/networking stages should be realistic:
  - local/hotseat lobby;
  - LAN/direct IP or manual connection;
  - import/export lobby state fallback;
  - investigate P2P with connection code;
  - investigate STUN/signaling/relay;
  - optional user-hosted relay or future server only if resources/donations
    justify it.
- Do not promise fully reliable serverless P2P; NAT, CG-NAT, firewalls,
  routers, and provider restrictions can break direct connections.
- PvP roles: player 1, player 2, spectator, moderator/judge, host.
- Draft engine must be generic/data-driven and support ban order, pick order,
  timers, locked picks, unavailable characters after pick/ban, rule validation,
  and action log.
- PvP result confirmation should bind confirmations to a state hash. Any result
  change after one player confirms clears that confirmation. Final means both
  players confirmed the same unchanged state inside the app.
- Do not claim the app guarantees real-world truth of entered timers. It can
  guarantee only that both players confirmed the same unchanged in-app result
  state.
- Export result image should include players, rooms, teams, timers per room/run,
  total timers, winner, confirmation status, statement like "confirmed by both
  players in GenshinTeamsTracker", and maybe session id/hash.
- PvP multi-run timer logic should support cumulative totals across games.

## PvP / Tournament Analytics

- Future analytics feature, not immediate MVP: collect local/in-app statistics
  across matches/games for characters and weapons.
- Character analytics can include winrate, banrate, pick/draft frequency, deck
  inclusion rate, account ownership rate, and constellation-tier breakdown where
  useful. Different constellations can be treated as separate statistical
  variants.
- Constellation ownership is cumulative/inclusive upward, not independent
  buckets. Example: C1 = 50% and C2 = 40% means that among players/accounts with
  the character, some have C1 only and 40% have C2 or higher. UI can show an
  overall character row first, then expandable constellation details with exact
  percentages where useful.
- Weapon analytics can mirror character analytics where applicable: winrate,
  pickrate/usage rate when the weapon exists on the account, and deck
  inclusion/selection rate. Initial version can ignore ascension/refinement
  tiers unless later needed.
- Use cases: draft bot heuristics, tournament balancing, tierlist-like analysis,
  custom ruleset balancing, and checking whether artifact/account strength
  changes results.
- Privacy: keep analytics local/in-app first. Any global/shared analytics must
  be opt-in and needs privacy policy/anonymization decisions. Do not imply
  online telemetry now.

## Draft Bots

- Future bots should let the user practice drafts when no one is available.
- Start with a rule-based bot, not global self-learning.
- Bot should consider current Abyss, tournament rules, cost/tier limits, enemy
  features, elements, immunities/counter-picks, team archetypes,
  synergy/anti-synergy, and rough character strength.
- Possible later stages: local imitation bot trained from user draft history,
  opt-in global draft data only with privacy policy/infrastructure,
  anonymization, and explicit consent.
- Bot logic should use metrics/tags, not only memorized character names, so new
  characters are not ignored.
- Useful tags/metrics: role, element, archetype, pick/ban priority, synergy,
  anti-synergy, Abyss suitability, historical pick/ban rate when available.
- After draft, bot should assign picked characters into teams/rooms using Abyss
  enemy features, similar GCSIM team/rotation data, KQM/default standards,
  assumed fallback talents, reasonable weapon fallback, and other available
  structured data.

## Donation / Support Page

- Future non-core task: add a support/donation page/dialog.
- It should say users can support development and can potentially donate toward
  a specific major feature, but specific feature requests should be discussed
  with the developer first for feasibility.
- Mention that some features may depend on external APIs, licenses, servers,
  infrastructure, or third-party data, so not every requested feature is
  guaranteed feasible.
- Do not clutter core UI with donation content.

## Inspiration / Monetization

- Non-MVP inspiration only: optional custom character icons/profile cosmetics,
  loosely inspired by Akasha-like profile customization.
- Optional tiny local AI companion could help with UI, comment on builds/runs,
  and lightly praise/tease the user, but only if it can run on weak PCs and
  stays optional.
- Investigate whether GitHub distribution can support paid feature unlocks;
  otherwise research a separate paid executable, overlay, or license mechanism
  compatible with the free app. This must not shape MVP architecture.
