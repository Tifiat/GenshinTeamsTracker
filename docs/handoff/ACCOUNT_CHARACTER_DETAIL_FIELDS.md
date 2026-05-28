# HoYoLAB Account Character Detail Fields

Purpose: record the useful raw fields from `data/hoyolab/account_character_details.json`
so future agents do not rediscover the same payload shape. Do not paste full raw
JSON here; keep this as a compact field map.

Allowed local sources for this reference:

- `data/hoyolab/account_character_details.json`
- `data/hoyolab/account_characters.json`
- `data/hoyolab/account_language.json`

## Wrapper Structure

The saved detail file is an import wrapper:

- `root.capturedAt`
- `root.charactersRequested`
- `root.charactersReturned`
- `root.detectedLanguage`
- `root.requestedLanguage`
- `root.source`
- `root.status` / `root.statusText`
- `root.url`
- `root.json`

The API payload lives at:

- `root.json.retcode`
- `root.json.message`
- `root.json.data`
- `root.json.data.list[]`

Shared API maps under `root.json.data`:

- `property_map`: map of stat/property ids to localized names/icons/filter labels.
- `relic_property_options`: artifact main/sub stat option groups.
- `relic_wiki`: artifact set/piece wiki mapping data.
- `weapon_wiki`: account weapon id -> HoYoWiki entry URL mapping.
- `avatar_wiki`: account character id -> HoYoWiki entry URL mapping.

## Normal Character Example

Known inspected example: `Тома` / Thoma, id `10000050`, from `json.data.list[]`.

Relevant confirmed values:

- `base.id = 10000050`
- `base.name = "Тома"`
- `base.level = 70`
- `base.actived_constellation_num = 6`
- `weapon.id = 13407`
- `weapon.name = "Копьё Фавония"`
- `weapon.level = 70`
- `weapon.affix_level = 5`
- `weapon.promote_level = 4`
- `weapon.main_property.final = "429"`
- `weapon.sub_property.property_type = 23`
- `weapon.sub_property.final = "25.2%"`
- `base_properties` contains HP/ATK/DEF stat-sheet rows.
- `selected_properties`, `extra_properties`, and `element_properties` contain current stat-sheet rows.

## Detail Record Fields

Each `json.data.list[]` record currently has:

- `base`
- `weapon`
- `relics`
- `constellations`
- `costumes`
- `selected_properties`
- `base_properties`
- `extra_properties`
- `element_properties`
- `skills`
- `recommend_relic_property`
- `weapon_skin`

### `base`

Observed fields:

- `id`
- `name`
- `element`
- `fetter`
- `level`
- `rarity`
- `actived_constellation_num`
- `is_chosen`
- `weapon_type`
- `weapon`
- `icon`: str/url (present)
- `side_icon`: str/url (present)
- `image`: str/url (present)

Notes:

- Character promote/ascension phase is not required by the current account
  storage model. Treat absence of that field as historical source context, not
  an active blocker.
- `base.weapon` is a compact equipped weapon summary with id/icon/type/rarity/level/refinement/name.

### `weapon`

Observed fields:

- `id`
- `name`
- `rarity`
- `type`
- `type_name`
- `level`
- `affix_level`
- `promote_level`
- `icon`: str/url (present)
- `desc`
- `main_property`
- `sub_property`

Notes:

- `weapon.promote_level` exists and is reliable for weapon row selection.
- `weapon.affix_level` is refinement.
- `weapon.desc` is available for display/reference only. Do not parse or apply passive formulas unless a future effect is explicitly modeled.
- `weapon.main_property.final` exposes equipped weapon base ATK, e.g. `"429"`.
- `weapon.sub_property.property_type` and `weapon.sub_property.final` expose secondary stat id/value, e.g. property type `23`, `"25.2%"`.

### Stat-Sheet Property Rows

These lists use the same row shape:

- `selected_properties`
- `base_properties`
- `extra_properties`
- `element_properties`
- `weapon.main_property`
- `weapon.sub_property`

Row fields:

- `property_type`
- `base`
- `add`
- `final`

Source direction:

- Use HoYoLAB stat-sheet rows as the primary source for clean account
  base/reference extraction, not as canonical TeamBuilder final stats.
- Preserve `property_type` as the stable key; localized names are display/reference only.
- `final` values describe current in-game equipment from HoYoLAB. They may be
  preserved as debug/reference, but must not become selected-build final stats
  when TeamBuilder has a virtual `build_id`.
- `selected_properties` is useful for HoYoLAB's selected summary ordering/debug,
  not as the only display source.
- For character base ATK, derive `base_properties[property_type=2001].base - weapon.main_property.final`.
- Character base HP and DEF can come from `base_properties[property_type=2000].base` and `base_properties[property_type=2002].base`.
- These HoYoLAB `base` values are factual account base-stat anchors. Use them
  to match the correct HoYoWiki level/ascension row before applying an
  ascension bonus: HP first, DEF second, derived character ATK only as a last
  fallback.

### `relics`

List of equipped artifact records. Observed fields include:

- `id`
- `name`
- `icon`: str/url (present)
- `pos`
- `pos_name`
- `rarity`
- `level`
- `set`
- `main_property`
- `sub_property_list`

Notes:

- `set` includes set id/name and affix/effect descriptions.
- Artifact ownership/equipped state can be cross-referenced later, but preset/build ownership rules live in TeamBuilder/Artifact Browser architecture notes.

### `constellations`

List of constellation records. Observed fields include:

- `id`
- `name`
- `icon`: str/url (present)
- `effect`
- `is_actived`
- `pos`
- `is_enhanced`
- `enhanced_effect`
- `can_enhanced`

### `costumes`

List; can be empty. Treat images/URLs as present references, not as stable local assets.

### `skills`

List of skill records. Observed fields include:

- `skill_id`
- `skill_type`
- `name`
- `level`
- `icon`: str/url (present)
- `desc`
- `is_unlock`
- `is_enhanced`
- `can_enhanced`
- `enhanced_desc`
- `skill_affix_list`
- `before_enhanced_skill_attr_index`
- `after_enhanced_skill_attr_index`

Account storage uses `skills[]` only for observed account talent/skill levels in
`account_character_talents`. Do not store parsed formulas, constellation
effects, or static skill catalogs there.

### `recommend_relic_property`

Dict with:

- `recommend_properties`
- `custom_properties`
- `has_set_recommend_prop`

This may help future build/stat hints, but is not part of current stat display.

### `weapon_skin`

May be `null`; preserve as optional.

## Architecture Notes

- Current TeamBuilder display stats should be computed from clean HoYoLAB
  base/reference values, selected weapon values, selected ArtifactBuildSnapshot
  totals, HoYoWiki ascension bonus/reference data, and safe baselines.
- HoYoLAB current-equipped final rows are non-canonical for virtual
  TeamBuilder builds.
- Normalized runtime account character/weapon rows live in local SQLite
  `data/artifacts.db`; see `ACCOUNT_SQLITE_STORAGE.md`.
- HoYoWiki character stats remain useful for ascension bonus extraction, Traveler/reference/fallback data, and possible future guide/recommendation parsing.
- Character ascension/promote phase is not a raw HoYoLAB field in the current
  account storage contract. For runtime ascension bonus, infer the needed
  HoYoWiki row by matching factual HoYoLAB base stats; do not use level-only
  after-ascension guesses.
- Russian HoYoWiki pages may contain recommendation blocks for weapons, artifacts, and teams/allies; preserve this as a possible future guide/bot source, but do not parse it in MVP code.
