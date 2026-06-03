# Abyss Enemy Data Source Audit

Research date: 2026-05-18

Scope: research/audit only. No app code, HoYoLAB import, app startup, account data,
or generated/private project folders were touched. Temporary external clones/cache
were used under the OS temp directory to inspect public data schemas.

Follow-up fixture:

- `ABYSS_HP_FIXTURE.md` contains a concrete current Floor 12
  `2026-05-16` HP/mapping fixture, including Fandom lineup parsing, monster id
  mapping, base HP/curve/resistance rows, `2.5x` fallback totals, likely current
  `3.75x` Stage12 totals, and parser implementation notes.

Label meanings:

- Confirmed: directly observed from a public page, API response, source file, or repo.
- Unconfirmed: plausible but not verified enough to design against.
- Needs follow-up: concrete next research item.
- Risk: implementation, data quality, freshness, or legal/terms risk.
- MVP recommendation: preferred first implementation direction.

## 1. Overview

Confirmed:

- No single inspected source currently gives a clean, ready-to-use package of
  current Spiral Abyss lineups, monster ids, waves, positions, HP totals,
  resistances, mechanics, icons, localization, and license clarity.
- A practical MVP must use a split-source join:
  - current period from HoYoLAB;
  - chamber/side/wave/count composition from Fandom/Genshin Wiki period pages;
  - resolved factual HP from Nanoka;
  - ids/icons/resists/simulation keys from source-like data where safe.
- Source-like game data from `DimbreathBot/AnimeGameData` exposes current schedule
  and monster stat tables, but recent Spiral Abyss chamber monster lists are no
  longer fully present in simple `TowerLevelExcelConfigData` rows.
- GCSIM exposes a clean monster stat model and enemy key/id/resistance data, which
  is useful for Sim DPS target setup. It must not be trusted as the Fact DPS HP
  source: its base-HP/curve path is known to disagree with direct current tower HP
  for some current Abyss enemies.
- The Genshin Impact Wiki/Fandom MediaWiki API exposes current and historical
  Abyss pages as parseable wikitext. It is useful for current human-readable
  lineups and sometimes wave notes, but it is community-edited and name-based.
- Fandom is also useful as a fallback source for coefficients and enemy metadata,
  not only lineups: the `Past` table includes the current period, the enemy level
  scaling page documents general Abyss HP multipliers by floor range, and some
  enemy pages expose level HP tables plus Abyss-specific resist/state data.
- Direct current tower-period sources such as Nanoka can expose already-resolved
  Abyss enemy names, monster ids, levels, icons, and HP in one place. Nanoka is the
  primary source for factual HP, but it does not expose reliable wave grouping,
  enemy counts, or spawn sequence. Do not use Nanoka as the source of chamber
  composition.
- `gi.nanoka.cc/tower/119/` was manually inspected for the 2026-05-16 live period
  and its HP values match an independent HoYoLAB guide sanity-check with the
  current `3.75x` multiplier. The experiment found stable SvelteKit/static JSON
  routes under `static.nanoka.cc`.
- Experiment probes now live under `tools/experiments/abyss/`. The Nanoka probe
  discovers static tower JSON for active/explicit/history ids. The Fandom
  composition probe parses MediaWiki-rendered HTML card containers and validates
  the 2026-02-16 Floor 12 Chamber 1 First Half regression as five sequential
  `Fisher of Hidden Depths` waves with count `3` each. The join probe combines
  Fandom composition rows with Nanoka HP rows by floor/chamber/side/normalized
  name and reports unmatched aliases/variants instead of guessing.
- The old 2026-05-16 HP fixture proved that the UI can consume HP and calculate
  `HP / elapsed_seconds`, but its GCSIM/AnimeGameData-derived HP values are known
  invalid for at least some enemies. Do not use that fixture as factual HP.
- Yatta/Ambr API exposes an excellent JSON shape for Abyss schedules and monster
  ids, but the inspected `tower` endpoint was stale compared with current 2026
  Abyss data.

MVP recommendation:

- Product source-authority decision:
  - Trust HoYoLAB Spiral Abyss Overview as the primary authority for the current
    Abyss period when it is available. The account/update page exposes the period
    range, for example `2026/05/16-2026/06/16`, and this should override local
    clock guesses, Fandom discovery links, and source-like schedule guesses.
  - Use Fandom/Genshin Wiki primarily for observable period lineups and
    human-visible enemy/wave notes after matching the page to the HoYoLAB period:
    current enemies, chamber sides, display levels, and notes that can be seen or
    verified in game or period pages. For MVP composition, Fandom is the primary
    source of chamber/side/wave order and enemy count.
  - Fandom current/history index can be used to discover the likely period page,
    especially because the newest link is usually the active Abyss page, but it is
    not the primary current-period authority. The selected Fandom page must match
    the HoYoLAB period date before its lineup is treated as current.
  - Regression case for any composition parser: the 2026-02-16 period must parse
    Floor 12 Chamber 1 First Half as five sequential waves of `Fisher of Hidden
    Depths`, with three enemies per wave. Do not collapse it into one enemy row or
    one aggregate count.
  - Use Nanoka/static tower JSON as the primary factual HP source after matching
    the same period/tower to HoYoLAB/Fandom. Nanoka HP rows can provide monster id,
    icon, level, and resolved HP, but Nanoka wave values are inferred and must not
    override Fandom composition.
  - Trust AnimeGameData/source-like data for non-obfuscated, current
    schedule/floor/chamber metadata, floor config links, HP-up entities, and
    monster stat catalogs. If the period/floor config matches the HoYoLAB period,
    non-obfuscated multiplier/config fields should be treated as stronger
    evidence than generic wiki floor-scaling fallback.
    Do not treat AnimeGameData/GCSIM base HP plus curve as final factual Abyss HP
    until it matches a direct tower-period HP source.
  - AnimeGameData can be used for HP-up multiplier/config evidence, especially
    when Nanoka is unavailable and Fandom enemy-page HP fallback needs a multiplier.
  - Treat obfuscated AnimeGameData fields as parser/research targets, not runtime
    contracts until decoded.
  - AnimeGameData currently provides a global monster catalog with ids, base HP,
    curves, and resistance data, but it does not provide a ready decoded current
    Abyss lineup in the simple `TowerLevelExcelConfigData` monster-list fields.
    Current lineups still need a Fandom/page-based source or a future decoded
    source-like parser.
  - Map Fandom lineup names to stable `monster_id` and `gcsim_key` values through
    GCSIM/AnimeGameData/manual aliases. Use `monster_id` as the canonical
    stat/cache key after the match; do not use display names as durable identity.
  - Fandom enemy pages are the first HP fallback when Nanoka is unavailable. If an
    enemy page contains multiple stat/level tables, choose the table/section whose
    heading best matches the Abyss lineup enemy name, for example `Battle-Scarred`
    for `Battle-Scarred Rock Crab` or `Battle-Hardened` for Battle-Hardened boss
    variants. If no confident table match exists, expose unavailable/low-confidence
    HP rather than silently using the first table.
  - For Sim DPS, GCSIM enemy keys/ids/resists remain useful. Fact DPS HP source
    and Sim DPS target source are separate concerns; comparing the two only makes
    sense when the simulated enemy/resistance/state setup matches the real Abyss
    enemy setup.
  - User guide pages or HoYoLAB guide cards may be used as manual sanity-checks
    when their HP cards match derived totals, but they are not runtime sources.
- Offline/current-period product rule:
  - The app assumes the normal account/profile workflow; designing a separate
    anonymous/no-account Abyss mode is out of scope.
  - The app must remain usable when Abyss source refresh is unavailable because of
    no network, blocked site access, or HoYoLAB/game maintenance.
  - Local system date is only a provisional fallback signal, not an authoritative
    period source. If the system date no longer falls inside the last known
    HoYoLAB period, the release app should ask the user what to do instead of
    silently creating a new period.
  - The prompt should explain that the system date does not match the last known
    Abyss period and offer an update path through Account/Data settings plus an
    explicit option to create a temporary offline Abyss tab.
  - If the user cancels, do nothing. If the same mismatch is still present on the
    next startup, ask again. This also covers narrow regional/server-boundary
    cases around the monthly Abyss transition.
  - Temporary offline periods use the simple monthly rule: from the 16th day of
    the current month to the 16th day of the next month, based on the local
    system date. They are provisional UI/runtime periods only.
  - Until source data is refreshed, enemy HP and factual DPS for a provisional or
    newly detected period should show unavailable/fallback text such as "update
    Abyss data" rather than block team building or timer usage.
  - When HoYoLAB becomes available, its period overrides local-date placeholders.
    If an offline tab has the same period, fill/update that tab with source-backed
    lineup/multiplier data. If no matching tab exists, create/select the official
    HoYoLAB period.
  - Do not automatically backfill every older offline/history period during a
    normal current-period update. Only update the period that matches the current
    HoYoLAB period.
  - Never silently delete user-created run data tied to a provisional period.
    Future history may offer explicit reassignment/recalculation, but that is not
    part of the current MVP.
  - Historical Abyss backfill and bulk recalculation of old runs are future
    low-priority tasks. The current Fact DPS flow should be designed around the
    current Abyss period first.
- Do not block the first Abyss season page on perfect source-like spawn/position
  data.
- Start with a resilient source-join pipeline:
  - HoYoLAB period as the current-period authority.
  - Fandom MediaWiki/API or parsed period pages as the primary source for current
    chamber composition: floor, chamber, side, wave order, enemy display name,
    enemy count per wave, and display level.
  - Nanoka/static tower-period data as the primary source for resolved factual HP,
    monster id, icon, level, and detail URL. Use Nanoka only after matching the
    same period/tower; do not trust Nanoka as a wave/count/sequence source.
  - Dimbreath/AnimeGameData or GCSIM/Yatta monster data for ids, icons, names, and
    resistances, but not as unverified final factual HP.
  - Fandom enemy/level-scaling pages as a practical fallback/cross-check for
    floor HP multipliers, enemy level HP tables, Abyss-specific resist states, and
    mechanics notes when source-like data is incomplete.
  - A small manual/derived alias table to join display names to `monster_id`.
  - Snap.Metadata may be used only as debug/reference for period/floor/group ids.
    Do not use it as the normal composition source: for the 2026-02-16 regression
    case it aggregates Floor 12 Chamber 1 First Half into one wave/count block
    instead of the five sequential Fandom waves.
- GCSIM follow-up:
  - Investigate whether vanilla GCSIM can simulate sequential enemies/waves with
    real HP. If it cannot, consider a local extension that runs enemies in
    sequence.
  - Keep any custom GCSIM extension isolated from the vanilla engine so engine
    updates or unmerged upstream pull requests do not overwrite it.
- Next parser/debug join step should stay experiment-only first, not production
  UI. It should harden alias/variant matching, for example Fandom `"Statue of
  Marble and Brass"` vs Nanoka `Legatus Golem` and Fandom `Primo Geovishap
  (Cryo)` vs Nanoka `Primo Geovishap`, while keeping both source paths and
  preserving warnings when name/count/wave or HP matching is ambiguous.
- Future Fact DPS UI/settings may expose a toggle such as `count multi-target
  HP`. Default should be solo-target mode: for each wave, count only the
  highest-HP matched target once, because that is usually the more comparable
  baseline for GCSIM-style DPS. Multi-target mode should remain available for
  teams whose real value depends on simultaneous enemies, but it should not be
  the default.
- Mark HP totals with explicit source/confidence: `nanoka_resolved_hp`,
  `fandom_enemy_page_fallback`, `source_estimate`, or `unavailable`.
- Prefer Nanoka resolved HP when available. If not, allow a lower-confidence
- Preserve source metadata and uncertainty flags per enemy so the model can be
  upgraded later without rewriting saved runs.

## 2. Candidate Sources Summary

### DimbreathBot / AnimeGameData

Source:

- Repo: https://github.com/DimbreathBot/AnimeGameData
- Raw examples:
  - `ExcelBinOutput/TowerScheduleExcelConfigData.json`
  - `ExcelBinOutput/TowerFloorExcelConfigData.json`
  - `ExcelBinOutput/TowerLevelExcelConfigData.json`
  - `ExcelBinOutput/DungeonExcelConfigData.json`
  - `ExcelBinOutput/DungeonLevelEntityConfigData.json`
  - `ExcelBinOutput/MonsterExcelConfigData.json`
  - `ExcelBinOutput/MonsterDescribeExcelConfigData.json`
  - `ExcelBinOutput/MonsterCurveExcelConfigData.json`
  - `TextMap/TextMap_MediumEN.json`
  - `TextMap/TextMap_MediumCHS.json`
  - `BinOutput/LevelDesign/Meta/LevelMetaData.json`
  - `BinOutput/LevelDesign/Monsters/*.json`
  - `BinOutput/LevelDesign/Routes/*.json`
  - `BinOutput/LevelEntity/ConfigLevelEntity_LevelBuff.json`

Confirmed:

- Current schedule rows are present in `TowerScheduleExcelConfigData.json`.
- Current row observed:
  - `closeTime`: `2026-06-16 03:59:59`
  - `KIGEHEHPIJC[0].MENHKEKCHDG`: `2026-05-16 04:00:00`
  - `KIGEHEHPIJC[0].KIPELJAMCJE`: `[1110, 1111, 1128, 1129]`
- Current floor ids map through `TowerFloorExcelConfigData.json`:
  - floor `1128`: `floorIndex=11`, `levelGroupId=128`,
    `overrideMonsterLevel=88`, `floorLevelConfigId=2153`.
  - floor `1129`: `floorIndex=12`, `levelGroupId=129`,
    `overrideMonsterLevel=95`, `floorLevelConfigId=2156`,
    `HFFJMMIIOGB=2154`, `CNEPHKKECBD=2155`.
- Current chamber rows exist in `TowerLevelExcelConfigData.json`:
  - `levelGroupId=128`: dungeon ids `3284`, `3285`, `3286`, monster levels
    `87`, `89`, `91`.
  - `levelGroupId=129`: dungeon ids `3287`, `3288`, `3289`, monster levels
    `94`, `97`, `99`.
- For these current rows, `firstMonsterList` and `secondMonsterList` were empty.
  The actual monster lineups appear to have moved out of the simple TowerLevel
  rows into level/scene data or another generated path.
- `DungeonExcelConfigData.json` maps current dungeon ids to scene ids:
  - `3284..3286` -> `sceneId=33863..33865`, `scriptData=Level_Tower_Moon_01`.
  - `3287..3289` -> `sceneId=33866..33868`,
    `scriptData=Level_Tower_Universe_01`.
- Monster stat data is clear in `MonsterExcelConfigData.json`:
  - fields include `id`, `describeId`, `monsterName`, `typ`, `hpBase`,
    `fireSubHurt`, `grassSubHurt`, `waterSubHurt`, `elecSubHurt`,
    `windSubHurt`, `iceSubHurt`, `rockSubHurt`, `physicalSubHurt`,
    and `propGrowCurves`.
- Monster names/icons are clear in `MonsterDescribeExcelConfigData.json`:
  - fields include `id`, `icon`, `nameTextMapHash`, `specialNameLabID`,
    `titleID`.
- Text maps can resolve `nameTextMapHash` in multiple languages.
- Current Floor 12 HP multiplier hint is exposed through level entities:
  - `DungeonLevelEntityConfigData.json` id `2156` has
    `levelConfigName=LevelEntity_Monster_HpUp_Stage12_New2`.
  - `TextMap_MediumCHS.json` `descTextMapHash=48688570` contains a test
    description indicating monster HP increase `275%`.
  - English text for that hash was not found in `TextMap_MediumEN.json` during
    this pass.

Risk:

- The repo README says that after game version 5.5.0, field order shuffling harmed
  deobfuscation and fields may stay obfuscated. This is visible in current data:
  schedule fields such as `KIGEHEHPIJC` and level-design fields are not semantic.
- No explicit license file was found in the repo root. The README asks for credit
  if the data is used.
- Reading `BinOutput/LevelDesign` directly likely needs a dedicated parser and
  reverse-engineering of obfuscated fields/path hashes.

MVP recommendation:

- Use AnimeGameData as the best source-like source for:
  - schedule dates;
  - floor/chamber ids;
  - monster levels;
  - monster base HP/growth/resist;
  - names/icons/localization hashes;
  - floor HP multiplier hints.
- Do not rely on AnimeGameData alone for current lineups until a parser can
  extract current chamber monsters from level/scene data.

### GCSIM

Source:

- Repo: https://github.com/genshinsim/gcsim
- Relevant paths:
  - `pipeline/pkg/data/enemy/enemy.go`
  - `pipeline/pkg/data/enemy/load.go`
  - `pkg/enemy/types.go`
  - `pkg/model/enemy_gen.go`
  - `pkg/model/curves.go`
  - `pkg/shortcut/enemies_gen.go`
  - `protos/model/data.proto`
  - `ui/packages/docs/docs/reference/config.md`
  - `ui/packages/docs/docs/reference/enemies/*.md`

Confirmed:

- License is MIT.
- Enemy source loader reads:
  - `MonsterExcelConfigData.json`
  - `MonsterDescribeExcelConfigData.json`
  - `MonsterCurveExcelConfigData.json`
  - `TextMap/TextMap_MediumEN.json`
- `pipeline/pkg/data/enemy/enemy.go` maps:
  - `MonsterExcel.id` -> `MonsterData.id`
  - text map name -> normalized `MonsterData.key`
  - `hpBase` -> `base_stats.base_hp`
  - `FIGHT_PROP_BASE_HP` grow curve -> `base_stats.hp_curve`
  - `FireSubHurt` etc. -> resist fields.
- `protos/model/data.proto` schema:
  - `MonsterData.id`
  - `MonsterData.key`
  - `MonsterData.base_stats.base_hp`
  - `MonsterData.base_stats.hp_curve`
  - `MonsterData.base_stats.resist.fire_resist`
  - `grass_resist`, `water_resist`, `electric_resist`, `wind_resist`,
    `ice_resist`, `rock_resist`, `physical_resist`
  - `freeze_resist`
  - `hp_drop`
- `pkg/shortcut/enemies_gen.go` maps GCSIM enemy keys to monster ids.
- Current Fandom enemy names from 2026-05-16 Floor 12 were present in GCSIM
  generated data, for example:
  - `superheavylandrovermechanizedfortress` -> `23090101`
  - `lordofthehiddendepthswhispererofnightmares` -> `22150101`
  - `hexadecatonicbattlehardenedmandragora` -> `20081201`
  - `battlescarredrockcrab` -> `26162601`
- `pkg/enemy/types.go` calculates named enemy HP as:
  - `HpBase * EnemyStatGrowthMult[level-1][HpGrowCurve]`
  - then applies `hp_mult` if supplied, otherwise `2.5`.
- GCSIM config target syntax supports:
  - `lvl`
  - all-element `resist`
  - per-element `pyro`, `hydro`, `anemo`, `electro`, `dendro`, `cryo`,
    `geo`, `physical`
  - `pos`
  - `radius`
  - `freeze_resist`
  - `hp`
  - `type=<monster_key>`
  - `type=<monster_key>[hp_mult=...]`

Risk:

- GCSIM is not an Abyss lineup source. It has enemy stats and target modeling,
  not current floor/chamber wave schedules.
- GCSIM's default `2.5` HP multiplier reflects old Floor 12 behavior. Current
  source-like data shows newer floor-specific HP-up entities, so factual HP
  totals should not blindly use GCSIM's default multiplier.
- GCSIM key space is normalized English and not localized; localized names must
  not be fed directly into future config generation.

MVP recommendation:

- Use GCSIM as a strong reference for enemy id/key mapping, HP formula, and
  resist schema.
- Keep it as a cross-check against AnimeGameData/Yatta monster stat data.
- Do not use it as the primary Abyss lineup source.

### Yatta / Ambr API

Sources:

- API endpoint inspected: https://gi.yatta.moe/api/v2/en/tower
- Monster endpoint inspected: https://gi.yatta.moe/api/v2/en/monster/23090101
- API/model docs: https://seria.is-a.dev/ambr/reference/models/abyss/

Confirmed:

- `https://gi.yatta.moe/api/v2/en/tower` returned JSON with:
  - `data.monsterList`
  - `data.items`
- `data.monsterList.<monster_id>` contains:
  - `id`
  - `name`
  - `prop[]`
  - `icon`
  - `link`
- `data.items.<cycle>.schedule.floorList[]` contains:
  - `id`
  - `teamNum`
  - `overrideMonsterLevel`
  - `leyLineDisorder[]`
  - `chamberList[]`
- `chamberList[]` contains:
  - `id`
  - `challengeTarget.type`
  - `challengeTarget.values`
  - `monsterLevel`
  - `firstMonsterList`
  - `secondMonsterList`
- The monster detail endpoint contains:
  - `data.id`
  - `data.name`
  - `data.type`
  - `data.icon`
  - `data.route`
  - `data.entries.<monster_id>.prop[]`
  - `data.entries.<monster_id>.hpDrops[]`
  - `data.entries.<monster_id>.resistance.fireSubHurt`
  - `grassSubHurt`, `waterSubHurt`, `elecSubHurt`, `windSubHurt`,
    `iceSubHurt`, `rockSubHurt`, `physicalSubHurt`.

Confirmed freshness issue:

- The inspected `tower` endpoint was stale: only schedule items `104` and `105`
  were returned, with latest observed `closeTime=2025-04-16 00:59:59Z`.
- Current 2026 floors `1128` and `1129` were not present in the inspected API
  response.

Risk:

- Terms/license for direct API use were not confirmed.
- Endpoint freshness must be checked before any runtime dependency.
- The API shape is very useful, but current data coverage was not sufficient.

MVP recommendation:

- Treat Yatta/Ambr as a best-case schema reference and optional source if it
  becomes current again.
- Do not make MVP depend on it for current Abyss periods.

### Genshin Impact Wiki / Fandom

Sources:

- Floor history/current period index:
  - https://genshin-impact.fandom.com/wiki/Spiral_Abyss/Floors#Past
- Current page inspected: https://genshin-impact.fandom.com/wiki/Spiral_Abyss/Floors/2026-05-16
- Enemy level scaling:
  - https://genshin-impact.fandom.com/wiki/Enemy/Level_Scaling
- Example enemy page with Abyss-specific resistance states:
  - https://genshin-impact.fandom.com/wiki/Super-Heavy_Landrover%3A_Mechanized_Fortress
- MediaWiki API pattern:
  - `https://genshin-impact.fandom.com/api.php?action=query&prop=revisions&rvprop=content&format=json&titles=Spiral%20Abyss/Floors/2026-05-16`

Confirmed:

- The `Past` table can include the current active Abyss period even though the
  section name is historical. Newer periods may use `Luna I`, `Luna VI`, etc.
  instead of simple game-version labels; use the date interval/page link, not the
  version text, as the reliable period selector.
- The current page returned parseable wikitext with:
  - `{{Abyssal Moon Spire}}`
  - `startVersion`
  - `start`
  - `end`
  - `prev`
  - `next`
  - `floor11Changed`
  - `floor12Changed`
  - `{{Domain Enemies}}`
  - `level1`, `level2`, `level3`
  - `target1`, `target2`, `target3`
  - `enemies1_1`, `enemies1_2`, etc.
  - `note1`, etc. when wave details are manually described.
- Current Floor 12 example from the 2026-05-16 page:
  - Floor 12 chamber 1 level `95`
    - first half: `Super-Heavy Landrover: Mechanized Fortress`
    - second half: `Hydro Hilichurl Rogue` and
      `Lord of the Hidden Depths: Whisperer of Nightmares`
  - chamber 2 level `98`
    - first half: `Fatui Electro Cicin Mage`,
      `Ruin Drake: Earthguard`, `Primo Geovishap (Cryo)`
    - second half: `Battle-Hardened Grounded Geoshroom`
  - chamber 3 level `100`
    - first half: `Hexadecatonic Battle-Hardened Mandragora`
    - second half: `Ruin Guard`, `Battle-Scarred Rock Crab`
- Fandom lineups use simple markup:
  - `*N` for counts where known.
  - `//` often separates waves or sequential groups.
  - `*?` indicates unknown/uncertain count.
- Some notes describe initial spawns and follow-up spawns in prose.
- The Fandom enemy level-scaling page documents general Spiral Abyss HP
  multipliers by floor range. This is useful as a fallback coefficient when a
  period-specific/source-like `LevelEntity_Monster_HpUp_*` multiplier is not yet
  parsed.
- Individual enemy pages can expose level HP tables and special Abyss state data.
  Example: Super-Heavy Landrover pages include high normal/Abyss resistance
  values and state-specific resistance changes. Treat these as cross-checks or
  fallback metadata; do not assume every enemy page is equally structured.
- Period pages can sometimes contain special notes about HP changes or special
  enemy mechanics. These should be captured as source notes when present, but not
  treated as guaranteed structured data.

Risk:

- Community-edited content is not primary/source-like game data.
- License is Fandom/CC-style content reuse; app bundling or redistribution needs
  attribution/compliance if wiki text is copied.
- Name-only data needs mapping to monster ids. Names can differ from API keys,
  localized text, or internal special names.
- Counts and wave structure can be approximate or absent.
- Period lineup pages generally do not expose ready total HP, spawn coordinates,
  or full resistance tables. Some of that exists on separate Fandom scaling/enemy
  pages and must be joined by name/page, with confidence flags.

MVP recommendation:

- Use Fandom as the most practical current fallback while source-like current
  lineup extraction is unresolved:
  - `Spiral_Abyss/Floors#Past` to locate the current period page by date.
  - Period page wikitext for chamber/side enemy names, counts, levels, and wave
    notes.
  - Enemy level-scaling page for a general floor HP multiplier fallback.
  - Individual enemy pages for HP tables, Abyss-specific resistance/state notes,
    and mechanics notes where available.
- Store Fandom source URL, page title, revision id if fetched, and uncertainty
  flags.
- Keep derived data minimal and attribution-friendly; do not embed long copied
  wiki prose into exports.

### Honey Hunter World

Source:

- Page inspected: https://gensh.honeyhunterworld.com/d_1001/?lang=EN

Confirmed:

- The page renders many Spiral Abyss floor variants and can expose:
  - variant ids such as `1128`, `1129`;
  - monster level;
  - teams;
  - challenge conditions;
  - disorders;
  - older monster lists.
- Current variant `1129` was present, but its monster list rendered empty in the
  inspected HTML, matching the empty current `TowerLevelExcelConfigData`
  `firstMonsterList` / `secondMonsterList` issue.
- The current floor 12 variant showed a test Chinese HP-up line indicating
  monster HP increase `275%`.

Risk:

- HTML scraping is brittle and includes ads/site UI.
- License/terms for scraping or reuse were not confirmed.
- It did not provide current monsters for the inspected current Floor 12 variant.

MVP recommendation:

- Use only as a human cross-check for schedule/floor variants and HP-up labels,
  not as a runtime source.

### HomDGCat / hakush.in / ambr.top

Confirmed:

- The task asked to investigate HomDGCat/hakush/ambr style sources.
- Direct local shell access to `homdgcat.wiki`, `api.hakush.in`, `gi.hakush.in`,
  and `api.ambr.top` failed during this pass due DNS/TLS/HTTP issues.
- `gi.yatta.moe` was reachable and appears to expose a Project-Amber/Yatta style
  API.
- `hakushin-py` public docs were found, but no usable Spiral Abyss lineup endpoint
  was confirmed from docs in this pass.

Needs follow-up:

- Treat HomDGCat as historical context unless a working released-data mirror is
  found. The original site may be unavailable after takedown, so do not design
  runtime logic around it without a current reachable source.
- Search for documented static JSON paths, public mirrors, or archives that expose
  released-period coefficients/overrides without relying on leak-only data.
- Re-check `api.ambr.top` and compare with `gi.yatta.moe`; they may be mirrors or
  related deployments with different freshness.

Risk:

- These sites may have useful current data, but availability, freshness, and
  terms must be verified before runtime use.

## 3. Spiral Abyss Lineup Data

Confirmed:

- Fandom current page is the most immediately usable current lineup source.
- Yatta/Ambr has the best JSON lineup schema but was stale.
- Dimbreath/AnimeGameData has current schedule/floor/chamber shell data, but
  current simple monster lists were empty.

Source comparison:

- Fandom:
  - Current lineups: yes.
  - Historical lineups: yes, page-per-period pattern.
  - Monster ids: no.
  - Counts/waves: partial, name markup/prose.
  - Format: MediaWiki wikitext through API.
- Yatta/Ambr:
  - Current lineups: no in inspected endpoint.
  - Historical/recent lineups: yes for returned 2025 items.
  - Monster ids: yes.
  - Counts/waves: side lists only in inspected shape; no spawn coordinates.
  - Format: JSON.
- AnimeGameData:
  - Current schedule/floors/chambers: yes.
  - Current monster ids in simple TowerLevel rows: no; lists empty.
  - Potential source for current scene-level spawns: likely yes, but parser needed.
  - Format: JSON with many obfuscated fields.

MVP recommendation:

- Use Fandom for current names and notes, then join to monster id data.
- Prefer a future source-like parser from AnimeGameData `BinOutput/LevelDesign`
  or a current Yatta/Ambr/released-data mirror endpoint when confirmed.

## 4. Enemy HP / Level / Scaling Data

Confirmed:

- AnimeGameData, GCSIM, and Yatta/Ambr all expose base HP and HP growth curve
  data.
- AnimeGameData field names:
  - `MonsterExcelConfigData.id`
  - `hpBase`
  - `propGrowCurves[].type=FIGHT_PROP_BASE_HP`
  - `propGrowCurves[].growCurve`
  - `MonsterCurveExcelConfigData`
- GCSIM generated fields:
  - `MonsterData.BaseStats.BaseHp`
  - `MonsterData.BaseStats.HpCurve`
  - `EnemyStatGrowthMult[level-1][curve]`
- Yatta/Ambr fields:
  - `entries.<id>.prop[].propType=FIGHT_PROP_BASE_HP`
  - `initValue`
  - `type`
- Fandom fallback sources:
  - `Enemy/Level_Scaling` for general Abyss floor HP multipliers.
  - individual enemy pages for level HP tables when available.
  - period page notes for occasional cycle-specific HP changes.
- Chamber enemy level comes from:
  - Fandom `level1`, `level2`, `level3`;
  - AnimeGameData `TowerLevelExcelConfigData.monsterLevel`;
  - Yatta/Ambr `chamberList[].monsterLevel`.
- Abyss HP multipliers are floor/level-entity dependent:
  - classic Floor 12 examples use `LevelEntity_Monster_HpUp_Lv4` with text
    `Opponents' HP increased by 150%`, equivalent to `2.5x` if interpreted as
    base plus increase.
  - current Floor 12 `LevelEntity_Monster_HpUp_Stage12_New2` showed a test CHS
    text with `275%`, likely `3.75x` if interpreted the same way.

Unconfirmed:

- The exact runtime interpretation of the newer `Stage12_New2` entity should be
  validated from game behavior or a deobfuscated config, even though the text is
  clear enough for a likely multiplier.
- It is not confirmed whether current Floor 11/12 HP multipliers always map cleanly
  to one `DungeonLevelEntityConfigData` id per floor.
- Fandom's general floor multiplier is a useful fallback, but it may miss
  period-specific/boss-specific overrides. When a period-specific source says the
  multiplier differs, prefer that source and keep the Fandom value as a
  cross-check only.

MVP recommendation:

- Store both:
  - `hp_multiplier_text`: source text/hash/entity name.
  - `hp_multiplier_value`: derived numeric value with `derived_from_text` flag.
- Track multiplier confidence, for example:
  - `source_like_period_multiplier`: parsed from game/source-like level entity or
    a current structured API.
  - `fandom_period_note`: parsed from a period page note.
  - `fandom_floor_scaling_estimate`: derived from the general Fandom level-scaling
    table.
  - `unavailable`: no safe multiplier source.
- If all enemy ids/counts/levels/base HP are matched and only the multiplier is a
  general Fandom fallback, factual DPS may be shown as an estimate with a visible
  confidence/warning marker. If multiplier is missing or internally contradictory,
  show enemy list but leave factual DPS unavailable.

## 5. Enemy Resistances / Immunities

Confirmed:

- AnimeGameData monster resistance fields:
  - `fireSubHurt`
  - `grassSubHurt`
  - `waterSubHurt`
  - `elecSubHurt`
  - `windSubHurt`
  - `iceSubHurt`
  - `rockSubHurt`
  - `physicalSubHurt`
- GCSIM maps these to:
  - Pyro, Dendro, Hydro, Electro, Anemo, Cryo, Geo, Physical.
- Yatta/Ambr detail endpoint exposes:
  - `resistance.fireSubHurt`
  - `grassSubHurt`
  - `waterSubHurt`
  - `elecSubHurt`
  - `windSubHurt`
  - `iceSubHurt`
  - `rockSubHurt`
  - `physicalSubHurt`.
- GCSIM also exposes `freeze_resist`; it sets freeze immunity to `1.0` for
  monsters where `typ == MONSTER_BOSS`.
- Fandom individual enemy pages can expose normal and Abyss-specific resistance
  states/mechanics for some enemies. Example: Super-Heavy Landrover has special
  Abyss resistance/state entries. Use this as fallback/cross-check metadata when
  source-like resist data or state-specific overrides are missing.

Risk:

- Some immunities/shields are mechanics, not simple resist values.
- Elemental shields, armor, gauges, and invulnerability phases are not fully
  captured by base resistance fields.

MVP recommendation:

- For factual HP/time DPS, resistances are optional metadata, not required for the
  numeric HP/time calculation.
- Store resist maps for UI warnings and later bot/simulator use.
- Treat immunities/shields/phases as separate warning tags, not as resist values.

## 6. Waves / Spawn Positions / Room Geometry

Confirmed:

- Fandom sometimes exposes wave/sequential information:
  - `//` in enemy lists often separates sequential groups.
  - `noteN` fields can describe initial spawn and follow-up spawns.
  - counts may use `*N` or `*?`.
- Yatta/Ambr inspected API exposes side lists (`firstMonsterList`,
  `secondMonsterList`) but not detailed wave groups or positions in the returned
  data.
- AnimeGameData `BinOutput/LevelDesign/Meta/LevelMetaData.json` contains scene
  metadata with fields like:
  - `sceneMetaDic`
  - `blockInfo`
  - `blockLevelMonsterDataPathHash`
  - `blockLevelRouteDataPathHash`
  - `blockCenterX`
  - `blockCenterZ`
- AnimeGameData `BinOutput/LevelDesign/Monsters/*.json` contains monster placement
  blocks, but fields are heavily obfuscated. Observed examples include likely
  monster ids/config ids and nested position-like objects, but semantic field
  names were not confirmed.

Risk:

- Spawn positions and exact wave timing are the hardest source area.
- Current data after version 5.5 has obfuscated fields and may require reverse
  engineering of path hashes and monster/group schemas.

MVP recommendation:

- Do not require wave positions for the first factual DPS feature.
- Keep optional fields in the model:
  - `wave_index`
  - `spawn_group`
  - `position`
  - `route_id`
  - `timing_note`
- Populate only when a source is confident; otherwise keep null and show no
  positioning claims.

## 7. Mechanics / Phases / Invulnerability

Confirmed:

- Base data sources expose stats and lineups better than behavior explanations.
- Fandom/wiki pages and guide sites can mention phases, shields, flying/burrowed
  states, and special mechanics in prose, but this is not structured enough for
  automatic factual DPS correction.
- GCSIM has code-level implementations for some enemies/targets and game mechanics,
  but it is not a ready structured encyclopedia of Abyss downtime/phases.

Risk:

- Factual HP/time DPS is not exact damage dealt. Waves, invulnerability, shields,
  forced downtime, phase transitions, mobility, and spawn delays can distort it.

MVP recommendation:

- Add manual/derived warning tags only:
  - `boss_heavy`
  - `aoe_needed`
  - `single_target`
  - `multi_wave`
  - `grouping_useful`
  - `shield_check`
  - `elemental_immunity`
  - `high_mobility`
  - `phase_invulnerability_warning`
- Do not attempt automatic DPS correction for downtime in MVP.

## 8. Icons / Localized Names / Asset Keys

Confirmed:

- AnimeGameData:
  - `MonsterDescribeExcelConfigData.icon` gives icon keys such as
    `UI_MonsterIcon_Fatuimecha_AMP`.
  - `nameTextMapHash` joins to text maps.
  - `specialNameLabID` and `titleID` may help distinguish named/boss variants.
- Yatta/Ambr:
  - `data.monsterList.<id>.name`
  - `icon`
  - `route`
  - detail `title`, `specialName`, `description`.
- GCSIM:
  - `MonsterData.key` gives normalized English keys useful for simulator config.
  - `NameTextHashMap` is preserved.

MVP recommendation:

- Store monster display name snapshots per source/language.
- Canonical identity should be `monster_id`, not display name.
- Store:
  - `icon_key`
  - optional remote/source icon path
  - localized names by language when available
  - `gcsim_key` when matched.

## 9. Mapping Strategy

MVP recommendation:

1. Use `monster_id` as the canonical enemy key whenever available.
2. Maintain a local alias table for name-only lineup sources:
   - source name
   - normalized name
   - language
   - matched `monster_id`
   - `gcsim_key`
   - confidence
   - notes.
3. Normalize Fandom names by:
   - stripping wiki markup/templates;
   - splitting counts (`*N`, `*?`);
   - splitting sequential groups (`//`);
   - preserving variant text such as `(Cryo)`.
4. Join normalized English names against:
   - AnimeGameData `MonsterDescribe.nameTextMapHash` resolved through
     `TextMap_MediumEN.json`;
   - GCSIM `pkg/shortcut/enemies_gen.go`;
   - Yatta/Ambr `monster` list/detail names.
5. If multiple matches exist, do not guess silently:
   - store `needs_manual_alias`;
   - show enemy name but keep HP total unavailable for that enemy.
6. Keep source evidence per enemy:
   - lineup source URL/page/revision;
   - stat source path/API URL;
   - matched id source;
   - multiplier source.

Suggested initial alias record:

```json
{
  "source": "fandom",
  "source_name": "Super-Heavy Landrover: Mechanized Fortress",
  "normalized_name": "superheavylandrovermechanizedfortress",
  "monster_id": 23090101,
  "gcsim_key": "superheavylandrovermechanizedfortress",
  "confidence": "confirmed_by_name_and_id_sources",
  "notes": []
}
```

## 10. MVP Data Model Proposal

MVP recommendation:

- Start with a versioned JSON cache under a future path such as
  `data/cache/abyss/periods/<period_id>.json`.
- Keep raw source snapshots separately, for example:
  - `data/cache/abyss/raw/fandom/<page_title>.<revision_id>.json`
  - `data/cache/abyss/raw/animegamedata/<commit_or_fetch_date>/...`
  - `data/cache/abyss/raw/yatta/<fetch_date>/tower.json`
- Do not store cookies/tokens or browser data.
- Move to SQLite only after usage requires frequent joins, filters, reports, or
  history analysis.

Minimal derived period shape:

```json
{
  "schema_version": 1,
  "period_id": "2026-05-16",
  "start_time": "2026-05-16T04:00:00",
  "close_time": "2026-06-16T03:59:59",
  "game_version": "Luna VI",
  "sources": [
    {
      "type": "lineup",
      "name": "genshin-impact.fandom.com",
      "url": "https://genshin-impact.fandom.com/wiki/Spiral_Abyss/Floors/2026-05-16",
      "revision_id": null,
      "confidence": "community_current"
    },
    {
      "type": "stats",
      "name": "AnimeGameData",
      "url": "https://github.com/DimbreathBot/AnimeGameData",
      "revision": null,
      "confidence": "source_like_public_dump"
    }
  ],
  "floors": [
    {
      "floor_index": 12,
      "floor_id": 1129,
      "team_num": 2,
      "override_monster_level": 95,
      "hp_multiplier": {
        "value": 3.75,
        "source_text": "monster HP increased by 275%",
        "source_entity": "LevelEntity_Monster_HpUp_Stage12_New2",
        "confidence": "derived_from_text"
      },
      "ley_line_disorders": [],
      "chambers": [
        {
          "chamber_index": 1,
          "monster_level": 95,
          "challenge": {
            "type": "remaining_time_more_than_seconds",
            "values": [180, 300, 420]
          },
          "sides": [
            {
              "side": 1,
              "total_hp": null,
              "total_hp_confidence": "unavailable_until_all_enemy_ids_counts_multipliers_confirmed",
              "enemies": [
                {
                  "monster_id": 23090101,
                  "source_name": "Super-Heavy Landrover: Mechanized Fortress",
                  "count": 1,
                  "wave_index": null,
                  "level": 95,
                  "hp": null,
                  "resist": null,
                  "icon_key": "UI_MonsterIcon_Fatuimecha_AMP",
                  "uncertainty": []
                }
              ],
              "tags": []
            }
          ]
        }
      ]
    }
  ]
}
```

Notes:

- `hp_multiplier.value=3.75` above is a model example based on current observed
  text; final code should set it only after multiplier parsing is implemented and
  verified.
- Use `null` HP until all inputs are matched confidently.

## 11. Fallback Behavior When Data Is Missing

MVP recommendation:

- Always create a period shell from local date if source data is unavailable:
  - period split day: 16th day of month;
  - label example: `16.05 - 16.06.26`;
  - run type: Abyss;
  - enemy data: unavailable.
- UI should show localized no-data text where needed:
  - English: `no data`
  - Russian: `нет данных`
- Factual DPS from enemy HP should be unavailable when:
  - chamber enemy list is missing;
  - any enemy id/count/level is uncertain;
  - HP multiplier is missing/ambiguous and no accepted fallback multiplier exists;
  - monster base HP/growth data is missing.
- If enemy ids/counts/levels/base HP are matched and the only weak piece is the
  multiplier source, allow a lower-confidence `estimated_from_floor_multiplier`
  DPS instead of blocking all output. The UI/export must display the estimate
  marker and source notes.
- Still allow saving run snapshots without enemy HP.
- Store warnings in saved snapshots so later source updates do not silently change
  old factual DPS unless a deliberate recompute flow exists.

## 12. License / Terms Risks

Confirmed:

- GCSIM is MIT licensed.
- AnimeGameData had no explicit license file found in the repo root during this
  pass. Its README requests credit for use.
- Fandom content reuse has attribution/license obligations and should not be
  copied wholesale into app exports without care.

Risk:

- Game data dumps and third-party APIs may have unclear legal status or terms.
- Direct scraping of HTML sites is brittle and may violate terms.
- Bundling source-derived enemy data should be reviewed before release.

MVP recommendation:

- Prefer fetching/caching small current-source snapshots locally for personal use
  during early development.
- Add a third-party data/credits note before release if any public source is used
  for distributed seed data.
- Do not redistribute large raw source dumps in the repo until license/terms are
  checked.

## 13. Open Questions

Needs follow-up:

- Find or confirm a current structured API that exposes Spiral Abyss lineups by
  `monster_id`, chamber, side, counts, and ideally wave groups.
- Re-check HomDGCat only as historical context/mirror research; the original site
  may be unavailable after takedown. Also check whether any public mirror/archive
  exposes only released-period coefficient data without relying on leaks.
- Re-check `api.ambr.top` and compare it with `gi.yatta.moe`; they may be mirrors
  or related deployments with different freshness.
- Search specifically for released-Abyss coefficient sources, not only "enemy HP":
  `LevelEntity_Monster_HpUp_*`, HP multiplier/bonus, boss HP override, Abyss
  resistance override, and period-specific monster stat modifiers.
- Determine whether current AnimeGameData `BinOutput/LevelDesign` can be parsed
  into chamber wave/spawn data:
  - map `DungeonExcelConfigData.sceneId` and `scriptData` to scene/group files;
  - map `LevelMetaData.blockLevelMonsterDataPathHash` to
    `LevelDesign/Monsters/*.json`;
  - identify obfuscated fields for monster id, group id, config id, position,
    route, and trigger/wave conditions.
- Verify numeric HP multipliers for current `LevelEntity_Monster_HpUp_*` configs,
  especially `Stage12_New2`.
- Build a small fixture for one known current Floor 12 chamber:
  - Fandom names -> monster ids;
  - monster base HP/curve/resists;
  - level;
  - HP multiplier from source-like entity if available, else Fandom floor-scaling
    fallback with confidence flag;
  - calculated per-enemy HP and total side HP;
  - source notes for any boss-specific HP/resistance/mechanics override.
- Decide source attribution wording before shipping built-in seed data.
- Decide how often to refresh current Abyss data:
  - on app start;
  - daily near period boundary;
  - manual update button;
  - all with offline fallback.

## 14. Useful Source Pointers

Primary/source-like:

- AnimeGameData repo:
  - https://github.com/DimbreathBot/AnimeGameData
- AnimeGameData README:
  - https://github.com/DimbreathBot/AnimeGameData/blob/master/README.md
- Current schedule raw path:
  - https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/master/ExcelBinOutput/TowerScheduleExcelConfigData.json
- Floor config raw path:
  - https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/master/ExcelBinOutput/TowerFloorExcelConfigData.json
- Chamber shell raw path:
  - https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/master/ExcelBinOutput/TowerLevelExcelConfigData.json
- Dungeon config raw path:
  - https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/master/ExcelBinOutput/DungeonExcelConfigData.json
- Level entity config raw path:
  - https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/master/ExcelBinOutput/DungeonLevelEntityConfigData.json
- Monster stats raw path:
  - https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/master/ExcelBinOutput/MonsterExcelConfigData.json
- Monster describe raw path:
  - https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/master/ExcelBinOutput/MonsterDescribeExcelConfigData.json
- Monster curves raw path:
  - https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/master/ExcelBinOutput/MonsterCurveExcelConfigData.json

GCSIM:

- Repo:
  - https://github.com/genshinsim/gcsim
- License:
  - https://github.com/genshinsim/gcsim/blob/main/LICENSE
- Enemy data loader:
  - https://github.com/genshinsim/gcsim/blob/main/pipeline/pkg/data/enemy/enemy.go
- Target HP/multiplier logic:
  - https://github.com/genshinsim/gcsim/blob/main/pkg/enemy/types.go
- Monster schema:
  - https://github.com/genshinsim/gcsim/blob/main/protos/model/data.proto
- Config target docs:
  - https://github.com/genshinsim/gcsim/blob/main/ui/packages/docs/docs/reference/config.md

Structured API / docs:

- Yatta tower endpoint:
  - https://gi.yatta.moe/api/v2/en/tower
- Yatta monster detail example:
  - https://gi.yatta.moe/api/v2/en/monster/23090101
- Ambr Python model docs for Abyss:
  - https://seria.is-a.dev/ambr/reference/models/abyss/
- Ambr wrapper repo:
  - https://github.com/seriaati/ambr

Current/historical lineup fallback:

- Fandom floors index / Past table:
  - https://genshin-impact.fandom.com/wiki/Spiral_Abyss/Floors#Past
- Fandom current period page:
  - https://genshin-impact.fandom.com/wiki/Spiral_Abyss/Floors/2026-05-16
- Fandom MediaWiki API example:
  - https://genshin-impact.fandom.com/api.php?action=query&prop=revisions&rvprop=content&format=json&titles=Spiral%20Abyss/Floors/2026-05-16
- Fandom enemy level scaling / general Abyss floor multipliers:
  - https://genshin-impact.fandom.com/wiki/Enemy/Level_Scaling
- Fandom enemy page example with Abyss-specific resistance states:
  - https://genshin-impact.fandom.com/wiki/Super-Heavy_Landrover%3A_Mechanized_Fortress

Human cross-check:

- Honey Hunter Spiral Abyss floor variants:
  - https://gensh.honeyhunterworld.com/d_1001/?lang=EN
