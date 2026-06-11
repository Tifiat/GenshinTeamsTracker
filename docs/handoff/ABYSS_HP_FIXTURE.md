# Historical Abyss HP Fixture: 2026-05-16 Floor 12

Research date: 2026-05-18

Scope: research/parsing notes only. No app code, HoYoLAB import, app startup, local
account data, artifact DB, or generated/private project data were used.

This file is historical research/debug context for the `2026-05-16` Floor 12
fixture. It is not the current/runtime source of AppShell factual DPS. Normal
runtime factual DPS should use the production source-data cache and helpers
under `run_workspace/abyss/source_data*.py`; this fixture remains useful for
parser confidence notes and reproducing the original HP-source investigation.

Labels:

- `confirmed`: directly observed from public API/source/wikitext.
- `estimate`: calculated from confirmed pieces but still needs source confidence in
  product UI.
- `risk`: can make factual DPS inaccurate if ignored.
- `next parser task`: concrete implementation/research step.

## Summary

Confirmed:

- Historical Floor 12 lineup for `2026-05-16` is parseable from Fandom MediaWiki
  wikitext.
- All inspected `2026-05-16` Floor 12 enemy names can be mapped to monster ids and
  base HP/curve/resistance data through GCSIM and/or AnimeGameData.
- Fandom's `Enemy/Level_Scaling` page confirms the general enemy HP formula and
  default Spiral Abyss HP bonuses:
  - Floor 3-7: `+50%` -> `1.5x`.
  - Floor 8-11: `+100%` -> `2.0x`.
  - Floor 12: `+150% nominal bonus` -> `2.5x`.
- The inspected AnimeGameData Floor 12 `floorLevelConfigId=2156` maps to
  `LevelEntity_Monster_HpUp_Stage12_New2`; its CHS text hash says
  `(test) monster HP increased by 275%`, which likely means `3.75x` total HP.
- Fandom enemy pages can contain Abyss-specific RES/mechanics. Example:
  Super-Heavy Landrover has Base (Spiral Abyss) RES `150%`, Overheating
  (Spiral Abyss) RES `50%`, and Paralyzed (Spiral Abyss) RES `-20%`.

MVP recommendation:

- This research path can produce useful factual DPS estimates for the inspected
  Floor 12 if the UI
  carries confidence/source flags.
- Use a confidence ladder:
  - `source_like_period_multiplier`: source-like floor/chamber multiplier parsed
    from game data or current structured API.
  - `fandom_period_note`: current period page note says a specific HP change.
  - `fandom_floor_scaling_estimate`: general Fandom floor multiplier only.
  - `unavailable`: missing or contradictory inputs.
- For this historical Floor 12 fixture, reports can show both the general
  `2.5x` fallback and the likely `3.75x` Stage12 value until `Stage12_New2`
  runtime semantics are fully verified.

## Sources Inspected

Fandom:

- Current period page:
  - https://genshin-impact.fandom.com/wiki/Spiral_Abyss/Floors/2026-05-16
- Current/history index:
  - https://genshin-impact.fandom.com/wiki/Spiral_Abyss/Floors#Past
- MediaWiki API pattern:
  - `https://genshin-impact.fandom.com/api.php?action=query&prop=revisions&rvprop=content&format=json&titles=Spiral%20Abyss/Floors/2026-05-16`
- Enemy level scaling:
  - https://genshin-impact.fandom.com/wiki/Enemy/Level_Scaling
- Super-Heavy Landrover enemy page:
  - https://genshin-impact.fandom.com/wiki/Super-Heavy_Landrover%3A_Mechanized_Fortress
- Lord of the Hidden Depths enemy page:
  - https://genshin-impact.fandom.com/wiki/Lord_of_the_Hidden_Depths%3A_Whisperer_of_Nightmares
- Historical example with explicit HP amendment:
  - https://genshin-impact.fandom.com/wiki/Spiral_Abyss/Floors/2025-04-16

Source-like / generated data:

- GCSIM enemy shortcuts:
  - https://raw.githubusercontent.com/genshinsim/gcsim/main/pkg/shortcut/enemies_gen.go
- GCSIM enemy generated data:
  - https://raw.githubusercontent.com/genshinsim/gcsim/main/pkg/model/enemy_gen.go
- GCSIM enemy curve table:
  - https://raw.githubusercontent.com/genshinsim/gcsim/main/pkg/model/curves.go
- AnimeGameData monster stats:
  - https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/master/ExcelBinOutput/MonsterExcelConfigData.json
- AnimeGameData floor/chamber shell:
  - https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/master/ExcelBinOutput/TowerFloorExcelConfigData.json
  - https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/master/ExcelBinOutput/TowerLevelExcelConfigData.json
- AnimeGameData HP-up entity/text:
  - https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/master/ExcelBinOutput/DungeonLevelEntityConfigData.json
  - https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/master/TextMap/TextMap_MediumCHS.json

Yatta/Ambr:

- Monster detail endpoint, useful but not fresh enough for every current enemy:
  - `https://gi.yatta.moe/api/v2/en/monster/<monster_id>`

## Historical 2026-05-16 Floor 12 Lineup

Confirmed from Fandom `Spiral_Abyss/Floors/2026-05-16` wikitext:

| Chamber/side | Display level | Enemy sequence |
| --- | ---: | --- |
| 12-1 first | 95 | Super-Heavy Landrover: Mechanized Fortress |
| 12-1 second | 95 | Hydro Hilichurl Rogue -> Lord of the Hidden Depths: Whisperer of Nightmares |
| 12-2 first | 98 | Fatui Electro Cicin Mage -> Ruin Drake: Earthguard -> Primo Geovishap (Cryo) |
| 12-2 second | 98 | Battle-Hardened Grounded Geoshroom |
| 12-3 first | 100 | Hexadecatonic Battle-Hardened Mandragora |
| 12-3 second | 100 | Ruin Guard -> Battle-Scarred Rock Crab |

Notes:

- `//` in Fandom enemy fields is treated as sequential/wave separator.
- Missing `*N` count is treated as count `1` for this fixture.
- AnimeGameData current `TowerLevelExcelConfigData.monsterLevel` reports
  `94/97/99` for Floor 12 while Fandom displays `95/98/100`. The floor row also
  has `overrideMonsterLevel=95`. For now, use Fandom display levels for fixture
  HP calculation and store AnimeGameData level as a cross-check until semantics
  are verified.

## HP Multiplier Findings

Confirmed:

- Fandom level scaling formula:
  - `Normal Max HP = Base HP * Level Multiplier`.
  - `Real Max HP = Normal Max HP * (1 + sum HP bonuses) * co-op * special event`.
- Fandom general Spiral Abyss HP bonus:
  - Floor 12 `+150%` nominal -> `2.5x`.
- Inspected AnimeGameData Floor 12 row:
  - `floorId=1129`, `floorIndex=12`, `levelGroupId=129`,
    `floorLevelConfigId=2156`.
  - `DungeonLevelEntityConfigData.id=2156`,
    `levelConfigName=LevelEntity_Monster_HpUp_Stage12_New2`,
    `descTextMapHash=48688570`.
  - `TextMap_MediumCHS[48688570] = "(test) monster HP increased by 275%."`
  - If interpreted like Fandom's bonus text, this is `1 + 2.75 = 3.75x`.

Risk:

- `Stage12_New2` text contains `(test)` and English text was not found during the
  streaming check. It is still source-like and tied to current floor config, but
  runtime semantics should be verified before treating it as fully confirmed.
- Do not stack Fandom `2.5x` with `Stage12_New2`. Treat `Stage12_New2` as a
  replacement multiplier candidate for this inspected period.

## Monster Mapping And HP Fixture

Formula used:

```text
normal_hp = base_hp * GCSIM/AnimeGameData level_curve(display_level)
abyss_hp_2_5 = normal_hp * 2.5
abyss_hp_3_75 = normal_hp * 3.75
```

The `2.5x` column is the generic Floor 12 fallback. The `3.75x` column is the
likely inspected Floor 12 source-like estimate from `Stage12_New2`.

| Chamber/side | Enemy | ID | Level | HP curve | Normal HP | 2.5x HP | 3.75x HP | Key caveat |
| --- | --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| 12-1 first | Super-Heavy Landrover: Mechanized Fortress | 23090101 / maybe 23090102 | 95 | HP_2 | 999,431 | 2,498,576 | 3,747,864 | Abyss entry/state matters for RES/mechanics; Fandom page has Abyss RES states. |
| 12-1 second | Hydro Hilichurl Rogue | 21040201 | 95 | HP_2 | 227,143 | 567,858 | 851,787 | Hydro RES 50%. |
| 12-1 second | Lord of the Hidden Depths: Whisperer of Nightmares | 22150101 | 95 | HP_2 | 1,226,574 | 3,066,435 | 4,599,652 | Normal page stats use hp_ratio 27; Stygian Onslaught variant has higher HP and should not be used for Abyss by default. |
| 12-2 first | Fatui Electro Cicin Mage | 23030101 | 98 | HP | 153,291 | 383,228 | 574,842 | Electro RES 50%; physical RES in AnimeGameData is -20%. |
| 12-2 first | Ruin Drake: Earthguard | 24030201 | 98 | HP_2 | 360,504 | 901,260 | 1,351,891 | Physical RES 50%. |
| 12-2 first | Primo Geovishap (Cryo) | 26050301 | 98 | HP | 919,747 | 2,299,367 | 3,449,051 | Cryo variant maps to `Drake_Primo_Rock_01_Ice`; shortcut `primogeovishap` alone is too coarse. |
| 12-2 second | Battle-Hardened Grounded Geoshroom | 26120501 | 98 | HP_2 | 4,542,352 | 11,355,881 | 17,033,821 | Yatta detail 404; GCSIM/AnimeGameData current data has stats. |
| 12-3 first | Hexadecatonic Battle-Hardened Mandragora | 20081201 | 100 | HP_2 | 3,549,441 | 8,873,603 | 13,310,405 | Dendro RES 135%; Yatta detail 404; GCSIM/AnimeGameData has stats. |
| 12-3 second | Ruin Guard | 24010101 | 100 | HP | 257,356 | 643,390 | 965,084 | Physical RES 70%. |
| 12-3 second | Battle-Scarred Rock Crab | 26162601 | 100 | HP_2 | 5,834,394 | 14,585,984 | 21,878,976 | Yatta detail 404; GCSIM/AnimeGameData current data has stats. |

Side totals from the same fixture:

| Chamber/side | Normal HP | 2.5x HP | 3.75x HP |
| --- | ---: | ---: | ---: |
| 12-1 first | 999,431 | 2,498,576 | 3,747,864 |
| 12-1 second | 1,453,717 | 3,634,293 | 5,451,439 |
| 12-2 first | 1,433,542 | 3,583,856 | 5,375,784 |
| 12-2 second | 4,542,352 | 11,355,881 | 17,033,821 |
| 12-3 first | 3,549,441 | 8,873,603 | 13,310,405 |
| 12-3 second | 6,091,750 | 15,229,374 | 22,844,061 |

## Resistance / Mechanics Notes

Confirmed:

- Base resistance maps are available from AnimeGameData/GCSIM for every mapped
  enemy.
- Fandom individual enemy pages can include state-specific overrides that are not
  obvious from base monster stat rows.
- Super-Heavy Landrover:
  - source-like base row has 10% all-element RES;
  - Fandom page has Base RES 70%, Base (Spiral Abyss) RES 150%,
    Overheating (Spiral Abyss) 50%, Paralyzed (Spiral Abyss) -20%;
  - it can create a Cryo Ward and enter invulnerable/cooling behavior.
- Lord of the Hidden Depths:
  - Fandom page has Normal and Stygian Onslaught stat blocks;
  - Normal hp_ratio 27 matches base HP 366.768;
  - Stygian Onslaught hp_ratio 31.79534 is a different mode and should not be
    used for ordinary Abyss unless the period explicitly says so;
  - shield mechanics can deal true physical damage based on boss max HP and
    cause paralyze/RES reduction.

Risk:

- Factual HP/time DPS does not account for shields, invulnerability, forced
  downtime, spawn travel, or true-damage mechanics. Store these as notes/warnings,
  not as part of the initial HP divisor.
- RES is not needed for HP/time DPS but is important for UI warnings, bots, and
  future simulation target setup.

## Source Freshness Notes

Confirmed:

- Yatta monster detail worked for older/known ids such as Landrover,
  Hilichurl Rogue, Lord, Fatui Electro Cicin Mage, Ruin Drake, Primo Geovishap,
  and Ruin Guard.
- Yatta returned 404 for newer inspected Floor 12 ids:
  - `26120501` Battle-Hardened Grounded Geoshroom;
  - `20081201` Hexadecatonic Battle-Hardened Mandragora;
  - `26162601` Battle-Scarred Rock Crab.
- GCSIM and AnimeGameData both contain those newer ids and stat rows.

MVP recommendation:

- Prefer AnimeGameData/GCSIM for monster stats until a fresher structured
  API is confirmed.
- Treat Yatta/Ambr as a schema reference and optional fallback, not the primary
  current source.

## Parser Implementation Notes

Next parser task:

1. Fandom period parser:
   - Fetch current period from `Spiral_Abyss/Floors#Past` by date interval.
   - Fetch period wikitext through MediaWiki API.
   - Parse `Domain Enemies` blocks, `levelN`, `enemiesN_1`, `enemiesN_2`, and
     `noteN`.
   - Split `//` as sequential/wave groups.
   - Parse `*N` counts; default missing count to 1 with warning.
   - Preserve raw enemy display text and source URL/revision id.

2. Enemy alias/id resolver:
   - Normalize Fandom names to GCSIM keys first.
   - Use exact GCSIM shortcut match when available.
   - Use AnimeGameData variants for explicit suffixes such as `(Cryo)`.
   - Keep manual alias overrides for special names and variants.
   - Return `matched`, `ambiguous`, or `unmatched`; do not silently choose when
     variants differ in HP or mechanics.

3. Monster stat provider:
   - Load AnimeGameData/GCSIM monster base HP, HP curve, resist map, and freeze
     resist.
   - Load GCSIM `EnemyStatGrowthMult` or AnimeGameData
     `MonsterCurveExcelConfigData`.
   - Calculate normal HP by display level.

4. HP multiplier provider:
   - Prefer current source-like `floorLevelConfigId` /
     `DungeonLevelEntityConfigData`.
   - Resolve `descTextMapHash` to text and parse `+N%`.
   - If source-like multiplier is missing, fallback to Fandom
     `Enemy/Level_Scaling`.
   - Store confidence and source text.

5. Mechanics/resistance enrichers:
   - Add optional Fandom enemy-page parser for state-specific RES/mechanics.
   - Store notes as structured warnings first; do not block factual HP/time DPS.

## Open Risks

- The inspected Floor 12 HP multiplier likely uses `3.75x`, but product code
  should keep both source text and confidence until verified.
- Fandom display levels and AnimeGameData `monsterLevel` differ by 1 in the
  inspected Floor 12 shell data; this needs a source-semantics note in code/docs.
- Enemy variants matter. Example: `Primo Geovishap (Cryo)` should map to
  `26050301`, not the generic shortcut id alone.
- Some enemy page stats are mode-specific. Example: Lord's Stygian Onslaught HP
  is not the same as ordinary Abyss.
- The "Boss Chamber" HP bonus row on Fandom level-scaling should not be blindly
  stacked with Spiral Abyss Floor 12 unless a source proves it applies.

## Recommended Next Step

Implement a backend-only `AbyssEnemyFixture` / report parser for the current
period:

- no UI;
- no account data;
- no artifact DB;
- no app startup;
- explicit public-source fetch/cache only;
- output one sanitized JSON/MD report with enemy mappings, HP estimates,
  confidence flags, and source notes.

This should come before wiring factual Abyss DPS into Run Workspace UI.
