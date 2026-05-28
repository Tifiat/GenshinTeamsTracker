# PvP Rulesets Audit

Research date: 2026-05-19

Scope: docs-only research notes. No app code, app startup, HoYoLAB import,
local account data, artifact DB, generated/private files, or tests were used.

## Summary

Confirmed:

- `https://gentor.vercel.app/planilhas` is an Angular app route for Gentor
  "planilhas" (rulesheets), not a static spreadsheet-download page.
- The deployed client points to a public JSON API at `https://gentor.com.br`.
- Public API endpoints observed:
  - `GET https://gentor.com.br/planilha`
  - `GET https://gentor.com.br/planilha/{id}`
  - `GET https://gentor.com.br/torneio`
  - `GET https://gentor.com.br/torneio/{id}`
- Gentor rulesheets are structured enough to study and maybe import later:
  character costs C0-C6, level 95/100 extra costs, weapon costs R1-R5,
  character-specific weapon costs, tiers, tier restrictions, deck point config,
  weapon-ban config, challenge type, and optional custom TypeScript draft
  script.

MVP recommendation:

- Start with manual XLSX/CSV/JSON ruleset import in GenshinTeamsTracker.
- Treat website/API scraping/import as a later source adapter after one stable
  source and permission/format expectations are confirmed.
- Use Gentor's JSON shape as strong evidence for what the internal ruleset model
  needs, not as the only source.

## Sources Inspected

Gentor:

- Public route:
  https://gentor.vercel.app/planilhas
- Client chunks:
  - `main-QYLNGZJX.js`
  - `chunk-Y6KV3TJ3.js` (planilhas module)
  - `chunk-ZQAACK2I.js` (decks module)
  - `chunk-WLU7OHFS.js` (torneios/partidas related)
  - `chunk-BHL4UV4O.js` (shared services and API config)
- API base found in client:
  - `API_URL = https://gentor.com.br`
  - `WS_URL = wss://websocket.gentor.com.br`
- Public JSON endpoints tested:
  - https://gentor.com.br/planilha
  - https://gentor.com.br/planilha/3
  - https://gentor.com.br/planilha/26
  - https://gentor.com.br/torneio
  - https://gentor.com.br/torneio/47

Search attempts:

- Public web searches for Genshin tournament character cost spreadsheets did not
  reveal a more stable, generic, importable public XLSX/CSV source during this
  pass. Discord-hosted tournament sheets may still exist but were not accessible
  without user-provided links/samples.

## Gentor Findings

### Public API

`GET /planilha` returns paginated JSON with rulesheet summaries. Example public
records included:

- `Abyss Fight Club`, id `3`, start `2024-10-21`;
- `x1 visionario`, id `26`, start `2025-12-08`;
- active tournament records from `GET /torneio`.

`GET /planilha/{id}` returns a detailed rulesheet with:

- `id`, `nome`, `criador`, `dataInicio`, `dataFinal`;
- `configuracao`;
- `personagens`;
- `armas`;
- `tiers`;
- `cartasAbismo`;
- `editores`.

The Angular service also has create/update/delete paths, but our app should not
depend on those for MVP import.

### Character cost fields

Observed under `planilha.personagens[]`:

- rulesheet row id;
- nested `personagem`:
  - `id`;
  - `nome`;
  - `raridade`;
  - `arma`;
  - `elemento`;
  - icon/splash URLs;
- `valorC0` through `valorC6`;
- `contarParaDeck`;
- `custoAdicionalNivel95`;
- `custoAdicionalNivel100`.

This directly supports constellation-cost variants and level-cap extras.

### Weapon cost fields

Observed under `planilha.armas[]`:

- nested `arma`:
  - `id`;
  - `nome`;
  - `raridade`;
  - `tipo`;
  - icon URL;
- base `valorR1` through `valorR5`;
- optional `personagens[]` overrides, each with nested character data and
  `valorR1` through `valorR5`.

This supports base weapon costs plus character-specific weapon cost overrides.

### Tier fields

Observed under `planilha.tiers[]`:

- `id`;
- `nome`;
- `pontuacaoInicio`;
- `pontuacaoFim`;
- `cor`;
- `restricoes[]`.

Observed restriction fields:

- `tipo`, for example `SOMA_EQUIVALENTE`, `QUANTIDADE_MINIMA`,
  `QUANTIDADE_TIER`;
- `tierComparacao`;
- `valorComparacao`;
- `valorBase`.

This is enough to justify an internal model with tier ranges plus named
constraint objects, rather than hardcoding one tournament's rule style.

### Rulesheet config fields

Observed `configuracao` keys include:

- `regraComparacao`;
- `intervaloPontos`;
- `intervaloJoker`;
- `limitePontosPersonagens`;
- `maxJokers`;
- `linhaCorteBanInicial`;
- `baseBansIniciais`;
- `zerarBansJogadorComMaisPontuacao`;
- `localBanArma`;
- `quantidadeBansArma`;
- `regra`;
- `desafio`;
- `tipoCustoAdicionalPersonagemStellaFortuna`;
- `usaScript`;
- `script`;
- `agrupadoresPersonagem`.

Client defaults observed for a new rulesheet:

- `regraComparacao = PONTUACAO_PERSONAGEM`;
- `intervaloPontos = 100`;
- `intervaloJoker = 3`;
- `localBanArma = SEM_BAN`;
- `regra = FRANCESA`;
- `desafio = ABISMO`;
- `baseBansIniciais = 3`;
- `usaScript = false`.

### Draft script

Gentor supports optional TypeScript draft configuration. The default script in
the client defines `getDraftConfiguration(matchInformation)` and returns:

- `picks`;
- `weaponBanLocation`;
- side-specific:
  - `initialBans`;
  - `middleBans`;
  - `extraBans`;
  - `jokerBans`;
  - `weaponBans`;
- `permaBans`.

The default logic derives:

- picks: 8 for Abyss or no boss count; 12 for some boss challenge cases;
- weapon bans from `spreadsheet.configurations.weaponBansDefault`;
- joker bans from `jokerInterval` and `jokersLimit`;
- extra bans from point difference divided by `pointsInterval`;
- initial bans from `initialBanDefault`, reduced below an initial-ban cutoff.

This is a strong signal that our draft engine should be data-driven and should
support both fixed declarative rules and future script-like/custom rules, even
if the MVP avoids executing user scripts.

### Tournaments

Observed `GET /torneio` and `GET /torneio/{id}` fields include:

- `id`;
- `nome`;
- `dataInicio`, `dataFim`;
- organizer/moderator data;
- `configuracao` with:
  - `tipo`;
  - `usuarioContaUnica`;
  - `configuracaoMd3`;
  - `tipoTime`;
  - permission levels;
  - `desafio`;
  - `gerarTop3`;
  - `utilizaElo`;
  - `timesPreDefinidos`;
- linked `planilha` when present.

This confirms that tournament metadata and rulesheet data are separate enough
to model separately.

## Likely Ruleset Model Needs

Minimum internal ruleset model should support:

- metadata: name, source, source URL, language, version/date, notes;
- character catalog references and display names;
- character cost by constellation C0-C6;
- optional level 95/100 extra costs;
- character inclusion/exclusion or "count toward deck" flag;
- weapon cost by refinement R1-R5;
- character-specific weapon cost overrides;
- tier ranges by point interval;
- tier restrictions by type and comparison tier;
- deck point limit;
- deck size / selected character count;
- initial bans;
- extra bans from point differences;
- joker bans and caps;
- weapon ban location and count;
- permanent/special bans;
- challenge type: Abyss, boss, custom;
- room/team/timer/scoring rules;
- artifact rules, likely unrestricted by default for our app;
- tournament-specific patches and organizer notes.

## Import MVP

Recommended MVP:

1. Manual import first:
   - XLSX;
   - CSV;
   - JSON.
2. Define a normalized internal JSON schema and map manual files into it.
3. Generate a validation report:
   - matched/unmatched character names;
   - matched/unmatched weapon names;
   - duplicate rows;
   - ambiguous aliases;
   - missing constellation/refinement columns;
   - unknown tier restrictions;
   - unsupported custom/script rules.
4. Let users fix aliases/columns rather than silently guessing.
5. Add a Gentor API importer later only if the source remains stable and the
   user wants it.

Why not scrape first:

- Gentor is one public source, but not necessarily the user's tournament source.
- Some tournament data may live in Discord or organizer spreadsheets.
- Tournament sheets can vary heavily by language, columns, and patch-specific
  rules.
- Manual import gives us the internal schema and validation before relying on a
  website adapter.

## Proposed CSV/XLSX Sections

A flexible import should accept these logical tables:

- `metadata`: ruleset name, source, patch/period, author, notes.
- `characters`: name, optional id, element, rarity, weapon type, C0-C6 costs,
  include flag, level extras, notes.
- `weapons`: name, optional id, type, rarity, R1-R5 costs, include flag, notes.
- `weapon_overrides`: weapon name/id, character name/id, R1-R5 override costs.
- `tiers`: tier name, point start/end, color/label.
- `tier_restrictions`: tier, restriction type, comparison tier, value, base.
- `draft`: initial bans, middle bans, extra ban formula, joker interval/cap,
  weapon ban count/location, pick count/order.
- `scoring`: room count, timer rules, reset rules, multi-run cumulative rules.
- `bans`: permanent/special/tournament patch bans.
- `notes`: free-form organizer notes and unsupported rules.

## Parser / Import Risks

- Character/weapon names may be localized or use aliases.
- Traveler variants and future characters need explicit handling.
- Cost fields can be numeric, blank, textual, or formula-driven in spreadsheets.
- Some rules are procedural/scripted rather than declarative.
- Weapon duplicates and account ownership are separate from ruleset catalog
  costs.
- Artifact restrictions may be absent or organizer-specific.
- Public APIs can change or disappear.
- Discord-only rulesheets may require user-provided samples.
- Do not run third-party TypeScript/script rules inside the app in MVP.

## Recommended Next Step

Add a docs/schema-only `TournamentRulesetV1` design or a pure backend parser
prototype for a tiny local CSV/JSON sample:

- no UI;
- no networking;
- no tournament lobby;
- no draft engine execution;
- validation-first report with matched/unmatched characters and weapons.

Website importers, Gentor API import, and Google Sheet scraping should come only
after the internal schema and validation report are useful.
