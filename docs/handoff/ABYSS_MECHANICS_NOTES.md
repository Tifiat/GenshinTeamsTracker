# Abyss Mechanics Notes

Research date: 2026-05-19

Scope: docs-only research notes. No app code, app startup, HoYoLAB import,
local account data, artifact DB, generated/private files, or tests were used.

Primary seed enemy list: `ABYSS_HP_FIXTURE.md` for current Floor 12
`2026-05-16`.

## Summary

Confirmed:

- Fandom current Abyss period pages provide lineup/wave text, but not ready HP
  totals.
- Fandom enemy pages often expose useful structured fields in wikitext:
  `hp_ratio`, `hp_type`, `weakpoint`, `abilityN`, `res_title`,
  `resglobalN`, element-specific `*_resN`, and templates such as
  `Elemental Shield Data`.
- Important mechanics are usually prose-only even when a structured stat block
  exists. Parser output should therefore combine structured fields with
  heuristic tags and UI warnings.
- GCSIM and AnimeGameData are better for monster ids/base stat rows/resistance
  cross-checks than for current Abyss lineup/mechanics prose.

MVP recommendation:

- Build a lightweight mechanics parser/report after the HP fixture parser.
- Keep HP/time factual DPS available when HP confidence is good, but show
  mechanics warnings for shields, wards, invulnerability, phases, state RES,
  summons, elemental requirements, and forced downtime.
- Do not try to perfectly model these mechanics in the first DPS calculation.
  Treat them as warnings/tags for UI, filters, bots, and later simulator target
  setup.

## Parser Tags

| Tag | Meaning | MVP UI use |
| --- | --- | --- |
| `shield_check` | Enemy or summoned unit has an elemental shield/gauge. | Warn that clear time can depend on shield-breaking elements. |
| `ward_or_barrier` | Boss creates a ward/barrier/deepdark shield-like mechanic. | Warn that HP/time DPS ignores ward HP or damage gates. |
| `phase_invulnerability` | Enemy can become immune/untargetable or damage-gated. | Warn that factual DPS includes forced downtime. |
| `state_res_override` | RES changes by state, mode, paralyze, shield, or phase. | Show RES is not a single static value. |
| `paralyze_window` | Enemy can be stunned/downed/paralyzed after mechanic success. | Useful for bots/simulator and UI warning. |
| `true_damage_hp_event` | Mechanic deals true/fixed damage based on enemy HP. | Warn HP/time DPS is not equal to player damage dealt. |
| `summons_or_adds` | Enemy summons minions, slimes, fishers, seeds, etc. | Warn about extra targets/waves not captured by boss HP alone. |
| `elemental_requirement` | Mechanic requires specific element/reaction/damage type. | Show counter-element hint. |
| `reaction_requirement` | Mechanic specifically requires reactions such as Bloom variants. | Show reaction-check hint. |
| `lunar_requirement` | Mechanic has Lunar Reaction-specific behavior. | Show lunar-specific hint without assuming team has it. |
| `high_mobility` | Enemy flies, burrows, spins, dashes, or has travel-heavy states. | Warn HP/time DPS includes movement/downtime. |
| `mode_specific_stats` | Page mixes Normal, Spiral Abyss, Local Legend, Stygian, etc. | Require selecting the correct mode/variant. |
| `weakpoint_paralyze` | Weakpoint hits can stun/paralyze. | Useful for warnings and bot/team heuristics. |
| `burrow_or_downtime` | Enemy can burrow/leave normal hitbox. | Warn about downtime. |
| `phase_threshold` | Behavior changes at HP thresholds. | Show phase warning. |

## Current Floor 12 Mechanics Table

| Enemy | Structured fields found | Mechanic tags | Prose-only notes | Parser confidence | UI warning recommendation |
| --- | --- | --- | --- | --- | --- |
| Super-Heavy Landrover: Mechanized Fortress | Fandom fields include `ability1=Fury`, `ability2=Ward`, `hp_ratio=22`, `hp_type=2`, state RES rows, and `Elemental Shield Data|Cryo|28`. Spiral Abyss RES rows include Base all RES `150%`, Overheating `50%`, Paralyzed `-20%`. | `state_res_override`, `ward_or_barrier`, `phase_invulnerability`, `elemental_requirement`, `paralyze_window`, `true_damage_hp_event`, `high_mobility` | Fury gauge, Pyro-driven overheating, Cryo Ward, immunity/cooling during ward, paralyze after ward break, true physical HP event. | High for tags/RES states; medium for exact timing. | Show "Abyss RES changes by state; ward can cause immunity; Pyro/ward-break/paralyze affects practical DPS." |
| Hydro Hilichurl Rogue | Fandom fields include `weakpoint=yes`, `hydro_res=50%`, `hp_ratio=5`, `hp_type=2`, and Hydro Slime shield data. | `summons_or_adds`, `elemental_requirement`, `shield_check`, `paralyze_window` | Summons Hydro Slime; interacting with/defeating slime can apply Hydro and knock down the rogue. | Medium; page gives enough for warning, not full AI timing. | Show "Summoned Hydro Slime/knockdown mechanic; Hydro RES 50%." |
| Lord of the Hidden Depths: Whisperer of Nightmares | Fandom fields include `ability1=Ward`, normal/paralyzed RES rows (`resglobal2=-60%`), `hp_ratio=27`, `hp_type=2`; page also has Stygian Onslaught stats. | `ward_or_barrier`, `summons_or_adds`, `elemental_requirement`, `lunar_requirement`, `paralyze_window`, `true_damage_hp_event`, `mode_specific_stats` | Deepdark Shield is 45% Max HP; four Fisher summons reduce shield by 25% each when defeated; Elemental DMG damages shield; Lunar Reaction DMG has large shield multiplier; shield break can cause true physical HP event, RES reduction, paralyze. | High for mode-specific warning and tags; medium for exact values until parser validates block selection. | Show "Ward/summons/Lunar shield mechanic; do not use Stygian stat block for ordinary Abyss unless period says so." |
| Fatui Electro Cicin Mage | Fandom fields include `weakpoint=yes`, `ability1=Shield`, `ability2=Interruption Resistance`, `ability3=Summoning`, `phys_res=-20%`, `electro_res=50%`, `hp_ratio=5`, `hp_type=1`, Electro shield data. | `summons_or_adds`, `shield_check`, `phase_invulnerability`, `high_mobility`, `elemental_requirement` | Summons Electro Cicins; Thundering Shield absorbs Cicins, gives damage immunity, speed, and stagger resistance; shield decays over time and via reactions. | High for shield/summon tags; medium for timing. | Show "Summons Cicins and can become shielded/immune; Electro RES 50%, Physical RES -20%." |
| Ruin Drake: Earthguard | Fandom fields include `weakpoint=yes`, `phys_res=50%`, `hp_ratio=7`, `hp_type=2`; page also contains Local Legend data. | `weakpoint_paralyze`, `state_res_override`, `mode_specific_stats`, `high_mobility` | Exposes weak point while charging; weakpoint hit can paralyze. Can absorb the most-damaged element and gain RES to it. | Medium; ordinary vs Local Legend behavior must be separated. | Show "Weakpoint/paralyze and absorbed-element RES risk; avoid Local Legend stats unless explicitly needed." |
| Primo Geovishap (Cryo) | Fandom fields include `weakpoint=yes`, `phys_res=30%`, `geo_res=50%`, Countered RES rows, Beginning of Fight high RES rows, `hp_ratio=30`, `hp_type=1`. | `state_res_override`, `elemental_variant`, `burrow_or_downtime`, `shield_check`, `true_damage_hp_event`, `phase_threshold`, `elemental_requirement` | Variant can be Pyro/Hydro/Cryo/Electro; current fixture needs Cryo variant id. Primordial Shower can be countered by shields, causing boss HP loss/stagger and RES reduction. Can burrow if player is far. | High for state/variant warning; medium for exact counter timing. | Show "Cryo variant matters; shield counter can remove HP and alter RES; shortcut `primogeovishap` is too coarse." |
| Battle-Hardened Grounded Geoshroom | Fandom generic `Grounded Geoshroom` page includes normal and Local Legend-like sections; current fixture maps Battle-Hardened id through GCSIM/AnimeGameData. Normal page has Dendro/Geo RES 30%; Local Legend block has much higher stats/states. | `state_res_override`, `elemental_requirement`, `paralyze_window`, `mode_specific_stats` | Local Legend prose has Scorched/Activated/Fury/stun loop, but this may not exactly describe Battle-Hardened Abyss row. | Low-medium for mechanics until variant block is confirmed; high for "mode-specific hazard". | Show "Battle-Hardened variant may not equal generic/Local Legend page block; trust fixture ids/stats and keep mechanics warning conservative." |
| Hexadecatonic Battle-Hardened Mandragora | Fandom page `Hexadecatonic Mandragora` contains Local Legend, Battle-Hardened, Stygian, and Mini Mandragora data. Battle-Hardened block has `hp_ratio=17.28`, base global RES `80%`, Dendro RES `205%`, Diminished Dendro RES `135%`. | `summons_or_adds`, `burrow_or_downtime`, `phase_invulnerability`, `paralyze_window`, `state_res_override`, `mode_specific_stats`, `elemental_requirement` | Fury/countdown and Sporebloom mechanics; burrows, spawns Mini Mandragoras, shares damage with boss while boss cannot be killed in that phase, then stun/diminished state. | High for mode-specific fields/tags; medium for exact state timeline. | Show "Dendro RES/state shift, summon/burrow/unkillable phase risk; factual DPS includes downtime." |
| Ruin Guard | Fandom fields include `weakpoint=yes`, `phys_res=70%`, `hp_ratio=7`, `hp_type=1`. | `weakpoint_paralyze`, `high_mobility` | Two weakpoint hits can stun/paralyze; spin/missile behavior can add movement pressure. | High for basic warning. | Show "Physical RES 70%; weakpoint stun can affect practical clear time." |
| Battle-Scarred Rock Crab | Fandom page `Crab Tsar` contains Local Legend, Battle-Scarred, and Stygian sections. Battle-Scarred block has shielded/global RES states and `hp_ratio=21.2`. | `ward_or_barrier`, `reaction_requirement`, `summons_or_adds`, `paralyze_window`, `state_res_override`, `mode_specific_stats` | Stoneborne Seeds and Ward mechanics; Bloom/Burgeon/Hyperbloom/Lunar-Bloom reactions interact with seeds/ward; ward depletion can stun, failure can increase RES. Stygian instant-kill text should not be used for ordinary Abyss unless mode says so. | High for reaction/ward warning; medium for exact Battle-Scarred state timing. | Show "Bloom-family reaction check and ward/stun/RES state; exclude Stygian-only instant-kill warning from ordinary Abyss by default." |

## Parser Feasibility

Structured fields that look feasible:

- `hp_ratio`, `hp_type`: useful for source cross-check, but HP fixture should
  still prefer current source-like monster ids/curves/multipliers.
- `weakpoint`: direct tag source for `weakpoint_paralyze` candidates.
- `abilityN`: direct hints such as Shield, Ward, Fury, Summoning, and
  Interruption Resistance.
- `res_title`, `resglobalN`, and element-specific `*_resN`: can produce
  `state_res_override` and mode/state rows.
- `Elemental Shield Data`: direct source for `shield_check` and shield element.

Heuristic/prose-only detection likely needed:

- ward/barrier/deepdark shield/immunity/cooling;
- paralyzed, stunned, downed, diminished, countered states;
- true/fixed damage based on current/max HP;
- summons/adds and shared damage;
- specific element/reaction requirements;
- burrowed/flying/mobile/downtime states;
- mode-only text such as Stygian Onslaught or Local Legend mechanics.

Important risk:

- Fandom enemy pages can mix Normal, Spiral Abyss, Battle-Hardened, Local
  Legend, and Stygian Onslaught data in one page. A parser must preserve the
  named block/mode and should not merge all state rows into one monster model.

## Source Pointers

Fandom:

- Current Floor 12 fixture source:
  https://genshin-impact.fandom.com/wiki/Spiral_Abyss/Floors/2026-05-16
- MediaWiki API pattern:
  `https://genshin-impact.fandom.com/api.php?action=parse&page=<page>&prop=wikitext&format=json`
- Enemy pages inspected:
  - https://genshin-impact.fandom.com/wiki/Super-Heavy_Landrover%3A_Mechanized_Fortress
  - https://genshin-impact.fandom.com/wiki/Hydro_Hilichurl_Rogue
  - https://genshin-impact.fandom.com/wiki/Lord_of_the_Hidden_Depths%3A_Whisperer_of_Nightmares
  - https://genshin-impact.fandom.com/wiki/Fatui_Electro_Cicin_Mage
  - https://genshin-impact.fandom.com/wiki/Ruin_Drake%3A_Earthguard
  - https://genshin-impact.fandom.com/wiki/Primo_Geovishap
  - https://genshin-impact.fandom.com/wiki/Grounded_Geoshroom
  - https://genshin-impact.fandom.com/wiki/Hexadecatonic_Mandragora
  - https://genshin-impact.fandom.com/wiki/Ruin_Guard
  - https://genshin-impact.fandom.com/wiki/Crab_Tsar

Source-like cross-checks:

- GCSIM enemy shortcuts:
  https://raw.githubusercontent.com/genshinsim/gcsim/main/pkg/shortcut/enemies_gen.go
- GCSIM enemy data:
  https://raw.githubusercontent.com/genshinsim/gcsim/main/pkg/model/enemy_gen.go
- AnimeGameData monster stats:
  https://raw.githubusercontent.com/DimbreathBot/AnimeGameData/master/ExcelBinOutput/MonsterExcelConfigData.json

## Recommended Next Step

Add a backend-only Abyss mechanics parser/report after the current-period HP
fixture parser:

1. Read current period enemy display names from the Fandom period parser.
2. Resolve page names and monster ids through the HP fixture resolver.
3. Fetch Fandom enemy wikitext through MediaWiki API.
4. Extract structured stat blocks and mode names without merging modes.
5. Add heuristic tags from prose with confidence levels.
6. Emit sanitized JSON/MD with enemy id, page, tags, warnings, structured fields,
   and parser confidence.

Do not block the first factual DPS UI on full mechanics modeling. Surface these
as warnings and data for future filters, draft bots, and simulator targets.
