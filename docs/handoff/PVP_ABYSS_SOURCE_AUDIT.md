# Abyss public rules source — 9 October 2026

Owner: Worker4. This dated research receipt precedes the product adapter in
[Deck rules](PVP_DECK_RULES.md), which owns current implementation/acceptance.
This receipt supersedes the June finding that no usable public
Abyss rules payload had been confirmed. Research only: no product importer,
rule enforcement, application launch, Computer Use or account access.

## Follow-up: weapon limits and executable client semantics — 9 October

10 October follow-up: unauthenticated current Cup reads still expose
`draft.minMaxCosts.engines=[0,0]` and separate `phaseTeams=500/500`; the inspected
costs/draft/preset fields contain no structured 155/130/25 split. The user now
explicitly requires interpreting the quoted weapon statement as executable
requirements. The selected-entry counter and narrowly parsed version-bound prose
fallback are owned by [the current requirement receipt](PVP_DECK_RULES.md#weapon-roster-requirements--2026-10-10).
The shipped client sums one assigned `team.engine.cost` per team entry; its engine
catalog has no inventory quantity field. GTT inventory counts therefore remain
availability metadata rather than multipliers for selected-card roster cost.
The public Google Docs text export was also read in memory on 10 October:
its original weapon paragraph still states 155 total, 130 general, 25 reserved,
cheap ≤14, expensive ≥15, and cheap weapons may use the general pool. The parser
fixture retains that bounded paragraph; the document edition timestamp remains unknown.
No arbitrary-document importer, refreshed document edition or server parity is
claimed by this fallback.

Public GET/client-text inspection was repeated in memory without credentials,
script execution, account access or new payload files. Current exact Cup is
`6ac54cc57032007b0dd5e4f9`, root `6953c08267a24684c387795c`, updated
`2026-10-06T19:34:41.433Z`. All nine DEFAULT families still normalize; Ascend's
MIRROR and Reverse Cup's 22-step shape remain unsupported for local execution.

The currently linked [event regulation](https://docs.google.com/document/d/1sBlA2ybrqqp35J66XbwejBx8S1z-Ehk-fwfd8asKhJI/edit?tab=t.0)
describes roster weapons at most 155: 130 general points plus 25 reserved for
weapons priced at most 14; weapons priced at least 15 cannot use the reserve.
Cheap weapons may also use the general pool. This is organizer prose: current
machine `draft.minMaxCosts.engines` is `[0,0]`. `phaseTeams` is separately
500/500, summed over each player's two teams, with a threshold increased in
500-point steps from the lower-cost side. Do not enforce 155 as every version's
machine cap. Joker restrictions include role/refinement and team-buff exceptions;
they remain manual linked rules. The older walkthrough's 65-point budget is
historical, not current fallback.

Public [character](https://abyss.darte.gg/api/abyss/agents) and
[weapon](https://abyss.darte.gg/api/abyss/engines) catalogs supply integer
`specialty` 1..5 (bow, catalyst, claymore, polearm, sword). The
[price helper](https://abyss.darte.gg/assets/agent-list.component-BELlgTBD.js)
uses a matching character override first, otherwise off-specialty slot when
specialties differ, otherwise the selected refinement slot.

The [shipped match client](https://abyss.darte.gg/assets/index-DAHBbc_N.js)
and [phase display](https://abyss.darte.gg/assets/half-flow.component-B2IrI_Od.js)
confirm 26 Cup actions. IMMUNE_BAN/IMMUNE_PICK are preparatory: four distinct
shared equal-price targets are needed across both players' two actions.
Preparatory bans affect immunity only; they do not remove later draft picks.
Normal BAN excludes protected/absolute-immune targets. IMMUNE_PICK reserves
a target for IMMUNE; regular IMMUNE counts as a final pick and can share that
protected target across seats. Each seat gets six PICK plus two IMMUNE and
three ordinary bans. No public server validator was found; this is inspected
client behavior, not backend parity evidence.

The source [result helper](https://abyss.darte.gg/assets/results-icon-DmnGoN_-.js)
adds restart penalties to elapsed clear time; lower adjusted time wins.
Current API `phaseMatch` is three free restarts, then `[5,5,10]`. The linked
document instead says two paid restarts at five seconds, failed rooms add 300
seconds, and ties compare restart count then room times across two games.
No document modification timestamp was verified, so authority is unresolved.
The local adapter follows pinned API/client single-game scoring, explicitly
distinguishes this from organizer legality, and does not implement a series,
failed-room penalties or document tie-breaks.

## Verified retrieval

The current public entry script is `/assets/index-uf6B5LvO.js`. Its
`draft-systems-api-u_0O2znN.js` and `use-api-D4EXiud1.js` identify these GETs:

| Resource | URL / behavior |
| --- | --- |
| Systems | <https://abyss.darte.gg/api/abyss/draft_systems?withDetails=true> |
| Pagination | `skip` and `limit`; default response returned 5 of 10 systems. Both pages were read. |
| Exact system | <https://abyss.darte.gg/api/abyss/draft_systems/6ac54cc57032007b0dd5e4f9> |
| Character catalog | <https://abyss.darte.gg/api/abyss/agents> |
| Weapon catalog | <https://abyss.darte.gg/api/abyss/engines> |
| Tournament/source linkage | <https://abyss.darte.gg/api/abyss/tournaments> |

All returned HTTP 200 without authentication or cookies, using a normal
`Mozilla/5.0` User-Agent. Default Python User-Agent received 403/1010; this was
not evidence that sign-in was required. No challenge automation was used.

The latest inspected tournament list entry, **Abyss Fast Soup 23**, was created
`2026-10-01T09:55:21.098Z`, marked unfinished, and referenced the exact system
above. That system is titled **Abyss Cup**, marked official and non-archived,
updated `2026-10-06T19:34:41.433Z`; root `6953c08267a24684c387795c`.
The catalog's internal mode string is `shiyu`, although its game IDs/names/assets
are Genshin. Do not infer game identity from that mode string alone.

Historical tournament reference `6aa0682c875af1e871a76385` also returned HTTP
200, the same exact requested ID, the same root, `archived=true` and update
`2026-09-08T19:55:24.347Z`. Preserve selected `_id`, `root`, `ref`, `updatedAt`,
fetch time and content hash. Updating the source list must not silently replace
a saved deck/match's version. The observed lineage is not a documented API SLA.

## Actual mapping, not a synthetic source

The current selected system contains 131 character-price rows, 233 weapon-price
rows, 135 character-specific weapon overrides, 10 character bundles, five tiers,
six preset constraints and 26 pick/ban/immune actions. Catalogs contain 140
character rows and 233 weapons. Every price reference resolves via `_id` to
`enkaId`; there are 125 unique character game IDs, because Traveler has seven
element variants. Preserve source attribute/variant references, including in
mandatory-character rules; GTT currently excludes Traveler.

| Source field | Resolved meaning / GTT mapping boundary |
| --- | --- |
| `costs.agents[].costs[0:7]` | Character C0–C6 prices. |
| Slots 7, 8 | Percentage and flat level adjustment. At level >=95: `ceil(base * (1 + percent/100) + flat)`; at level 100 double percent and flat. Confirmed by client function `Et`; cannot map to V1's fixed level extras without losing meaning. |
| `costs.engines[].costs[0:5]` | R1–R5 prices; `bis` contains character-specific arrays. |
| Weapon slot 5 | Off-specialty price, checked after BIS in client `sl`; not an extra refinement. |
| `costs.agentsBundles` | Conditional character combinations and cost adjustments, with minimum/optional maximum C bounds; preserve bounds rather than flattening prices. |
| `costs.tiers` | Inclusive min/max cost bands, T0–T4. Current bands: 1–14, 15–44, 45–49, 50–64, 65–1000. Zero cost has no matching tier in this table. |
| `costs.costLimit` | French per-character difference cap (`rl`), **not total deck budget**. `disableCostLimit` exempts a character. |
| `draft.minMaxCosts`, `minMaxCount` | Separate roster cost/count bounds. Current character cost pair `[520,0]`; zero-bound enforcement is unverified, so preserve zero explicitly. |
| `preset.rules` | Declarative `requires`, `equals`, `required_agents`, `max_count`; see below. |
| `preset.ddAgents` | Game IDs classified as DD in the selected system; other eligible priced IDs are support. Price-row `specification` is not a role source. Confirmed by later same-day client display/form inspection; [correction and implementation](PVP_DECK_RULES.md#character-role-correction-and-contextual-filters--2026-10-09). |
| `phasePicks` | Ordered action list, player0/player1, 60,000 ms pick time, 300,000 ms reserve, preban step 60. |
| `phaseStage`, `phaseTeams`, `phaseMatch` | Stage settings, team weapon costs, restarts; separate from draft deck validation. |

The live declaration requires one T1 DD plus one T1 support for T4, one T1 of
unspecified role for T3, allows three T0 with aggregate threshold 19 or four T0
with threshold 20 as T1 equivalents, names six mandatory character variants,
and declares maximum count 50. These are parsed declarations, not proof of the
server's matching/reuse algorithm. DD/Sup values 0/1 are confirmed by the client.
The inspected form/calculator/profile/live-draft bundles did not expose the
constraint evaluator. Allocation overlap, repeated use and zero-bound semantics
remain unverified; do not claim parity from a field transcription.

## Public documents and conflicting editions

The tournament's `regulations` link points to
[Abyss Fast Soup regulations](https://docs.google.com/document/d/1sBlA2ybrqqp35J66XbwejBx8S1z-Ehk-fwfd8asKhJI/edit?tab=t.0).
Its public text export works. It specifies 520–540 roster points, max three T4,
weapon total 155 split into 130 plus a 25-point cheap-weapon allowance, and three
free/two paid restarts. The API currently gives `[520,0]`, total count 50 and
three paid penalties `[5,5,10]`. These are materially different declarations.

The regulation links [character prices](https://docs.google.com/spreadsheets/d/1cyibKv0-YBH1zwlyOcZzLJLWQtnyo331zV0nikw9Rjw/edit?gid=1039938840#gid=1039938840),
[weapon prices](https://docs.google.com/spreadsheets/d/17UZX06crdMd0nvmIEjhdq9u3cK7uvibyoAV3FP4aH94/edit?gid=0#gid=0)
and a [system walkthrough](https://docs.google.com/document/d/1PfNi7XsWEdcrpyc31_1F75KTnRK9a1Lmd5t2tRkbF3o/edit?tab=t.0).
Public CSV exports work; sheets include old-price columns and date-like titles
without enough version provenance to assume they match today's API. The guide
states 510–530 points and older tier combinations (T4: two T1 DD plus one support;
T3: one of each; T2: one T1). Do not merge these into the current API silently.
Summer 2026 regulations are a separate historical event, not the current source.

For reproducing website behavior, select an exact API system as the machine
source and report document differences. A tournament-specific organizer rulebook
requires a separately reviewed override layer. No user source upload is needed
to start the adapter; discovering and checking sources is Worker4's task.

## Reproducible research projection and evidence

`tools/experiments/pvp_site_audit/abyss_rules_source.py --list` retrieves the
paginated public catalog; `--system-id 6ac54cc57032007b0dd5e4f9` emits annotated
JSON with mapped IDs/price slots, preserved constraints, provenance and explicit
`execution_ready=false`. It does not write files/cache, import GTT accounts,
execute source JS or pretend to emit `TournamentRulesetV1`. Callers own any
explicit output redirection; no raw data is retained by default.

Fresh probe retrieval at `2026-10-09T04:42:54Z` returned the same system/catalog
hashes below and completed normalization without source files or credentials.
Five focused tests PASS: ID/slot mapping, distinct cap/budget fields, privacy
projection, unknown/schema failures, pinned-version checks and element variants.
The real payload projection PASS covered all counts above. The first attempt
correctly rejected duplicate game IDs; the bounded fix preserves Traveler
variants and mandatory references instead of merging them. Render/product tests
are not applicable to this source-only research change.

SHA256 of fetched payload bytes: system
`5940a7557ada323950628744c61cba6fcba4f26b2412e3f5302e6960025c5e13`,
agents `733eab9ee81fca0215089498af8d7c237a4396483a5fe7e30e12896f6f484262`,
engines `feff0496ab635995fed03ce1ee47d97800d5cf0cc4b9b3d8d43ac5c012cbe6e9`.
Sorted ASCII research projection: 153,418 bytes,
`ef6efebe1f630e463a586f2036db3f5191659ba8c81b2e02bef67b3dfa59f1f5`.
Temporary public JS/JSON copies remain at
`C:/Users/user/AppData/Local/Temp/worker4-abyss-source-kdilhnng` with `OWNER.txt`.
Closeout attempted a path/ownership-checked deletion; automatic approval review
rejected the command as `blocked by policy`. No retry or alternate deletion was
attempted. These public research copies are outside Git and contain no account
credentials. Intended retained project evidence is this receipt, synthetic tests
and the read-only probe; deferred temp cleanup is not a rules-adapter blocker.
