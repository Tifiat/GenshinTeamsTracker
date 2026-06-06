# Stat Normalization / GCSIM Key Mapping Handoff

Research date: 2026-05-18

Scope: handoff only. No app code, generated account/cache data, HoYoLAB import, UI behavior, or history/state schemas were changed for this note.

Label meanings:

- Confirmed: verified from current project source or GCSIM source/docs.
- Unconfirmed: plausible, but not safe enough to implement against yet.
- Needs follow-up: concrete next step before implementation.
- Risk: correctness or maintenance risk.
- MVP recommendation: safest first direction for the next implementation step.

## 1. Why This Exists

Confirmed:

- `CharacterDetailsData` and `CharacterStatSnapshot` can now carry character, weapon, and artifact-build contributions.
- They intentionally do not compute final totals yet.
- The next risky backend step is normalizing stat identifiers and numeric units before TeamCard, Character Details, and GCSIM config generation use the data.
- Current artifact summaries use HoYoLAB/Artiscan `property_type` integers and `raw_value` numbers in display percent points. Example: `46.6%` becomes `46.6`.
- GCSIM config `add stats` expects percent-like stats as decimal ratios. Example: `46.6%` should become `0.466`.

MVP recommendation:

- Add a small pure stat-normalization layer before final totals or GCSIM config generation.
- Keep display localization separate from technical stat keys.
- Keep raw source values/provenance next to normalized values for debugging.

## 2. Project Stat Sources Inspected

Confirmed source files:

- `ui/artifact_browser/stat_types.py`
  - UI/display constants for Artifact Browser stat property types.
  - Virtual sort keys: `CRIT_VALUE = -1`, `PROC_COUNT = -2`.
  - Localized label lookup via `STAT_LABEL_KEYS`.
- `hoyolab_export/artifact_stats.py`
  - Backend artifact property constants.
  - Artiscan key -> HoYoLAB-like `property_type` mapping.
  - Artiscan max main stat values for 5-star MVP import.
- `hoyolab_export/artifact_db.py`
  - `calculate_raw_build_summary(...)`.
  - Sums artifact main/sub stats by `property_type`.
  - `_parse_raw_stat_value(...)` strips `%` and returns a float in display percent points.
- `hoyolab_export/artifact_build_snapshot.py`
  - `ArtifactBuildSnapshot`.
  - `ArtifactStatTotalSnapshot` stores `property_type`, `property_name`, `raw_value`, or optional `stat_key`.
  - Set bonuses are metadata only; formulas are not applied.
- `hoyolab_export/character_stats_catalog.py`
  - HoYoWiki character HP/ATK/DEF rows and ascension bonus.
  - Default assumptions: CR 5%, CD 50%, ER 100%, other special stats 0.
- `hoyolab_export/weapon_stats_catalog.py`
  - HoYoWiki weapon base ATK and secondary stat rows.
  - Passive/refinement text is reference-only and must not be auto-applied.
- `hoyolab_export/character_stat_snapshot.py`
  - Combines prepared character/weapon/artifact contributions.
  - Emits warnings for uncomputed final totals, missing artifact summary, unsupported Traveler, omitted passives/formulas.
- `hoyolab_export/team_card_data.py`
  - `CharacterDetailsData` wraps `CharacterStatSnapshot`.
  - GCSIM config generation and key mapping are explicitly not implemented.
- `docs/handoff/GCSIM.md`
  - Dedicated GCSIM integration research handoff.

## 3. Existing Project Artifact Stat IDs

Confirmed:

| Project concept | property_type | Artiscan key | Current display/name | Current raw summary unit |
| --- | ---: | --- | --- | --- |
| HP flat | 2 | `hp` | `HP` | flat number |
| HP percent | 3 | `hp_` | `HP%` | percent points |
| ATK flat | 5 | `atk` | `ATK` | flat number |
| ATK percent | 6 | `atk_` | `ATK%` | percent points |
| DEF flat | 8 | `def` | `DEF` | flat number |
| DEF percent | 9 | `def_` | `DEF%` | percent points |
| Crit Rate | 20 | `critRate_` | `CRIT Rate` / `CR` | percent points |
| Crit Damage | 22 | `critDMG_` | `CRIT DMG` / `CD` | percent points |
| Energy Recharge | 23 | `enerRech_` | `Energy Recharge` / `ER` | percent points |
| Healing Bonus | 26 | `heal_` | `Healing Bonus` | percent points |
| Elemental Mastery | 28 | `eleMas` | `Elemental Mastery` / `EM` | flat number |
| Physical DMG Bonus | 30 | `physical_dmg_` | `Physical DMG Bonus` | percent points |
| Pyro DMG Bonus | 40 | `pyro_dmg_` | `Pyro DMG Bonus` | percent points |
| Electro DMG Bonus | 41 | `electro_dmg_` | `Electro DMG Bonus` | percent points |
| Hydro DMG Bonus | 42 | `hydro_dmg_` | `Hydro DMG Bonus` | percent points |
| Dendro DMG Bonus | 43 | `dendro_dmg_` | `Dendro DMG Bonus` | percent points |
| Anemo DMG Bonus | 44 | `anemo_dmg_` | `Anemo DMG Bonus` | percent points |
| Geo DMG Bonus | 45 | `geo_dmg_` | `Geo DMG Bonus` | percent points |
| Cryo DMG Bonus | 46 | `cryo_dmg_` | `Cryo DMG Bonus` | percent points |

Confirmed:

- `CRIT_VALUE` and `PROC_COUNT` are virtual UI/sort metrics, not HoYoLAB stat IDs and not GCSIM stats.
- Current `crit_value` is `crit_rate * 2 + crit_damage` using artifact summary `raw_value`, where CR/CD are percent points.
- Current `proc_count` comes from artifact substat roll/proc metadata when present.

Risk:

- Do not feed current artifact `raw_value` directly to GCSIM for percent stats. It would be 100x too large.

## 4. GCSIM Stat Keys

Confirmed from GCSIM local source clone:

- Local clone path inspected: `%LOCALAPPDATA%/Temp/gcsim-src`.
- Commit inspected: `b613b8a8e8374107362e1d4804563676f9548381` (`2026-05-11`, subject `added hexerei to NewChar in sucrose (#2613)`).
- Primary source files:
  - `pkg/gcs/ast/keys.go`
  - `pkg/core/attributes/stats.go`
  - `pkg/gcs/parser/parseCharacter.go`
  - `pkg/core/info/convert.go`
- Official source links:
  - https://github.com/genshinsim/gcsim/blob/main/pkg/gcs/ast/keys.go
  - https://github.com/genshinsim/gcsim/blob/main/pkg/core/attributes/stats.go
  - https://github.com/genshinsim/gcsim/blob/main/pkg/gcs/parser/parseCharacter.go
  - https://github.com/genshinsim/gcsim/blob/main/pkg/core/info/convert.go
- Official docs:
  - https://docs.gcsim.app/guides/understanding_config_files/
  - https://docs.gcsim.app/reference/config/

Confirmed GCSIM `add stats` keys:

| GCSIM key | GCSIM attribute |
| --- | --- |
| `def%` | `attributes.DEFP` |
| `def` | `attributes.DEF` |
| `hp` | `attributes.HP` |
| `hp%` | `attributes.HPP` |
| `atk` | `attributes.ATK` |
| `atk%` | `attributes.ATKP` |
| `er` | `attributes.ER` |
| `em` | `attributes.EM` |
| `cr` | `attributes.CR` |
| `cd` | `attributes.CD` |
| `heal` | `attributes.Heal` |
| `pyro%` | `attributes.PyroP` |
| `hydro%` | `attributes.HydroP` |
| `cryo%` | `attributes.CryoP` |
| `electro%` | `attributes.ElectroP` |
| `anemo%` | `attributes.AnemoP` |
| `geo%` | `attributes.GeoP` |
| `dendro%` | `attributes.DendroP` |
| `phys%` | `attributes.PhyP` |
| `atkspd%` | `attributes.AtkSpd` |
| `dmg%` | `attributes.DmgP` |

Confirmed GCSIM base stat keys exist internally:

- `base_hp`
- `base_atk`
- `base_def`

MVP recommendation:

- For GCSIM config generation, use `add stats` for artifact stats only.
- Do not add character/weapon base stats to `add stats`; define characters/weapons with GCSIM character/weapon config lines and let GCSIM compute base stats/effects.
- Our app can still compute/display its own final stat view later, but that is separate from GCSIM config generation.

## 5. Project -> GCSIM Mapping Table

Confirmed MVP mapping:

| property_type | Project normalized key | GCSIM key | Unit conversion for GCSIM |
| ---: | --- | --- | --- |
| 2 | `hp_flat` | `hp` | keep flat value |
| 3 | `hp_percent` | `hp%` | percent points / 100 |
| 5 | `atk_flat` | `atk` | keep flat value |
| 6 | `atk_percent` | `atk%` | percent points / 100 |
| 8 | `def_flat` | `def` | keep flat value |
| 9 | `def_percent` | `def%` | percent points / 100 |
| 20 | `crit_rate` | `cr` | percent points / 100 |
| 22 | `crit_damage` | `cd` | percent points / 100 |
| 23 | `energy_recharge` | `er` | percent points / 100 |
| 26 | `healing_bonus` | `heal` | percent points / 100 |
| 28 | `elemental_mastery` | `em` | keep flat value |
| 30 | `physical_dmg_bonus` | `phys%` | percent points / 100 |
| 40 | `pyro_dmg_bonus` | `pyro%` | percent points / 100 |
| 41 | `electro_dmg_bonus` | `electro%` | percent points / 100 |
| 42 | `hydro_dmg_bonus` | `hydro%` | percent points / 100 |
| 43 | `dendro_dmg_bonus` | `dendro%` | percent points / 100 |
| 44 | `anemo_dmg_bonus` | `anemo%` | percent points / 100 |
| 45 | `geo_dmg_bonus` | `geo%` | percent points / 100 |
| 46 | `cryo_dmg_bonus` | `cryo%` | percent points / 100 |

Needs follow-up:

- Decide whether `atkspd%` and generic `dmg%` should enter the project normalized stat enum now or only when a source actually produces them.
- Decide how to represent source stats that GCSIM ignores or does not model as stats, such as incoming healing or shield-strength style properties.

## 6. Proposed Internal Normalized Model

MVP recommendation:

Add a pure module, likely under `hoyolab_export/`, for reusable stat normalization. Candidate names:

- `stat_normalization.py`
- `normalized_stats.py`

Candidate serializable-friendly objects:

```python
NormalizedStatValue(
    key="crit_rate",
    value=0.311,
    unit="ratio",
    source_value="31.1%",
    source_numeric=31.1,
    source_unit="percent_points",
    property_type=20,
    gcsim_key="cr",
    warnings=(),
)

NormalizedStatBlock(
    values=(...),
    source="artifact_build_snapshot",
    warnings=(),
)
```

Recommended value units:

- `flat`: regular number, e.g. `311`, `4780`, `187`.
- `ratio`: percent-like number normalized to decimal ratio, e.g. `46.6% -> 0.466`.
- `virtual`: CV/proc-count style metrics, not used for final stat totals or GCSIM config.
- `unknown`: parsed but not safely classified.

Confirmed conversion rule for current artifact summary:

- If `property_type` is in a percent-like set, convert `raw_value / 100`.
- Otherwise keep `raw_value`.

Percent-like property types:

- `3, 6, 9, 20, 22, 23, 26, 30, 40, 41, 42, 43, 44, 45, 46`.

Flat property types:

- `2, 5, 8, 28`.

Risk:

- HoYoWiki character/weapon stat catalog values are strings and may include `%`; they need their own parser. Do not assume they use artifact summary `raw_value` semantics.

## 7. Final Stat Calculator Boundary

Confirmed current boundary:

- `CharacterStatSnapshot` is a contribution/snapshot container, not a final calculator.
- Character base contribution includes base HP/ATK/DEF and ascension bonus separately.
- Weapon contribution includes base ATK and secondary stat separately.
- Artifact contribution includes artifact-only stats and set metadata.
- Weapon passives are not applied.
- Artifact set bonus formulas are not applied.
- Conditional bonuses are not applied.
- Resonance formulas are not applied.

MVP recommendation:

- First normalize numeric values and keys.
- Then build a conservative partial-total calculator that can report exactly what was included/excluded.
- Only calculate final-looking HP/ATK/DEF/CR/CD/ER/EM when inputs are unambiguous and included sources are clearly labeled.

## 8. GCSIM Config Generator Boundary

Confirmed:

- `CharacterDetailsData.gcsim_readiness` currently reports:
  - `gcsim_config_generation_not_implemented`
  - stored account character/weapon GCSIM key fields may be available, but
    config generation is not wired yet
  - `final_totals_not_computed`
- GCSIM character, weapon, and set keys are separate from stat keys.

Current character/weapon key boundary:

- `hoyolab_export/account_storage.py` stores `catalog_english_name` plus
  resolved `gcsim_character_key` / `gcsim_weapon_key` status and method for
  account characters and observed weapon stacks.
- The resolver uses local HoYoWiki stats caches for English names and local
  prepared GCSIM shortcut sources for accepted keys. It does not use localized
  display names, does not fetch network data, and does not run a GCSIM artifact.
- Ready stored keys can become `GcsimMappingRef` inputs for future config
  generation; missing/ambiguous/unsupported rows remain not-ready.

Needs follow-up:

- Build mapping from artifact `set_uid`/names to GCSIM set keys.
- Decide Traveler handling for GCSIM separately; account Traveler cannot be blindly mapped to one elemental Traveler variant.
- Wire selected team/current build adapters to consume stored ready
  character/weapon keys.

MVP recommendation:

- Do not generate GCSIM configs from localized display names.
- Keep explicit key-mapping reports for global/catalog coverage and diagnostics;
  account SQLite key fields are a runtime cache of resolved local-account rows,
  not a complete production mapping table.
- Keep unknown/unmapped characters, weapons, and sets as readiness warnings, not silent fallbacks.

## 9. Source Pointers

Project:

- `ui/artifact_browser/stat_types.py`: UI stat constants, badges, labels.
- `hoyolab_export/artifact_stats.py`: backend artifact stat constants and Artiscan mapping.
- `hoyolab_export/artifact_db.py`: raw artifact build summary and current percent-point parsing.
- `hoyolab_export/artifact_build_snapshot.py`: artifact build snapshot shape.
- `hoyolab_export/character_stats_catalog.py`: character base rows and default base stat assumptions.
- `hoyolab_export/weapon_stats_catalog.py`: weapon base rows and passive-reference policy.
- `hoyolab_export/character_stat_snapshot.py`: contribution snapshot boundary.
- `hoyolab_export/team_card_data.py`: TeamCard/CharacterDetails data boundary and GCSIM readiness warning.

GCSIM:

- `pkg/gcs/ast/keys.go`: DSL stat key map.
- `pkg/core/attributes/stats.go`: internal stat enum and stat string names.
- `pkg/gcs/parser/parseCharacter.go`: `add stats` parser.
- `pkg/core/info/convert.go`: proto stat -> GCSIM stat conversion, including ignored unsupported stat types.
- `docs/handoff/GCSIM.md`: local app integration handoff.

## 10. Recommended Next Small Code Step

MVP recommendation:

Add a pure `stat_normalization` module and tests:

- Map project `property_type` to normalized key and optional GCSIM key.
- Convert artifact percent-point `raw_value` to decimal ratio for normalized/GCSIM usage.
- Preserve raw source value and source unit.
- Convert `ArtifactBuildSnapshot.stat_totals` into a `NormalizedStatBlock`.
- Leave final totals, set bonus formulas, resonances, weapon passives, and GCSIM config generation unimplemented.

Suggested tests:

- `46.6` HP% -> normalized `0.466` and GCSIM key `hp%`.
- `31.1` CR -> normalized `0.311` and GCSIM key `cr`.
- `187` EM -> normalized `187` and GCSIM key `em`.
- CV/proc count remain virtual and are not emitted as GCSIM stats.
- Unknown property type returns warning and is not silently mapped.
- ArtifactBuildSnapshot -> NormalizedStatBlock preserves source/provenance.
