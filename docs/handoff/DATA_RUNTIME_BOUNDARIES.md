# Data Runtime Boundaries

Purpose: compact map of where current project data lives, who writes it, who
reads it at runtime, and what each layer is not allowed to mean. This is a
boundary map, not a full architecture document. Detailed table/source notes live
in the linked handoffs.

## Raw HoYoLAB JSON / Source Cache

Paths:

- `data/hoyolab/account_characters.json`
- `data/hoyolab/account_weapons.json`
- `data/hoyolab/account_character_details.json`
- `data/hoyolab/account_language.json`
- `data/hoyolab/crop_manifest.json`

Role:

- source/cache output of the HoYoLAB import pipeline;
- input to account SQLite sync, artifact import, crop/asset generation, and
  explicit debug/source inspection tools;
- test fixture source where a parser/source path is being tested.

Runtime rule:

- new UI/runtime account code should not read these files directly for account
  character, talent, weapon, or icon state;
- if SQLite account runtime tables are expected but empty, report the empty
  storage/import condition instead of silently falling back to stale raw JSON.

## Account SQLite Runtime State

DB:

- `data/artifacts.db`

Note: this is a legacy filename for the unified local SQLite runtime DB. It is
not artifact-only storage; account, equipment, artifact, and selected static
effect tables can live in the same file.

Runtime account tables:

- `account_characters`
- `account_character_talents`
- `account_weapon_observed_stacks`

Writers:

- normal HoYoLAB import (`python -m hoyolab_export.run_import`) after raw JSON,
  artifacts, and crop manifest are written;
- manual/debug resync (`python -m hoyolab_export.account_storage`), optionally
  with `--download-side-icons`.

Readers:

- runtime/UI account loaders through `hoyolab_export/account_storage.py` read
  adapters;
- `ui/character_assets.py` converts adapter records into legacy visual grid
  asset items;
- `run_workspace/pvp/account_deck_export.py` reads the same adapters to build a
  backend-only Free Draft `DraftDeck` from owned characters and observed weapon
  stacks.

Meaning:

- `account_characters`: authoritative account character state from HoYoLAB
  character list plus clean base/reference fields where available and resolved
  GCSIM character key readiness metadata;
- `account_character_talents`: observed account skill/talent levels from local
  HoYoLAB detail `skills[]`;
- `account_weapon_observed_stacks`: reconstructed observed weapon stacks from
  equipped/detail observations, including resolved GCSIM weapon key readiness
  metadata.

Terminology note: "stack" here means a deduped observed weapon fingerprint with
`known_count`, not a UI tooltip/grouping of different weapon variants.

Important limits:

- `account_characters.name` is localized HoYoLAB display text. Identity-sensitive
  adapters should use stable IDs such as `character_id` plus explicit mapping
  data, not English-name searches or localized display-name matching;
- GCSIM config adapters should consume stored resolved `gcsim_character_key` and
  `gcsim_weapon_key` only when their status is `ready`. The
  `catalog_english_name` fields are local HoYoWiki source context and are not
  valid GCSIM keys by themselves;
- observed weapon stacks are not guaranteed full weapon inventory;
- HoYoLAB weapon id is a weapon type id, not a unique account instance id;
- no fake weapon instance ids;
- current-equipped character -> weapon relation is provenance only, not
  canonical weapon identity;
- TeamBuilder/prototype selected weapons should be explicit observed weapon
  options (stack id/fingerprint or deterministic smoke selector), not inferred
  from current-equipped provenance;
- talent/constellation descriptions, effects, parsed buffs, and GCSIM configs do
  not belong in account SQLite.

Detailed contract: `docs/handoff/ACCOUNT_SQLITE_STORAGE.md`.

## PvP Deck Export Output

Default generated/private write path:

- `data/pvp/decks/`

Role:

- optional output for `python -m run_workspace.pvp.account_deck_export_smoke
  --write`;
- contains PvP `DraftDeck` JSON built from current local account SQLite runtime
  data.

Rules:

- default account deck export smoke is dry-run and writes no JSON;
- generated deck JSON may contain stable ids, localized display names, levels,
  constellations, weapon refinements, and stack counts;
- deck JSON must not contain artifacts, artifact stats, HoYoLAB auth/cookies,
  raw account dumps, local paths, SQLite row ids, or generated/private storage
  internals;
- `data/pvp/` is ignored and should not be committed.

## PvP Session Bundle Output

Default generated/private write path:

- `data/pvp/sessions/`

Role:

- optional output for `python -m run_workspace.pvp.session_bundle_smoke --write`;
- contains backend/debug PvP session bundle JSON for replay/validation.

Rules:

- default session bundle smoke is dry-run and writes no JSON;
- `--account` is required before the smoke reads local account data;
- bundles may embed account-derived PvP deck data when account mode is explicit;
- bundles must not contain artifacts, artifact stats, HoYoLAB auth/cookies, raw
  account dumps, local paths, SQLite row ids, or huge raw ruleset payloads;
- session bundles are not PvP History persistence;
- `data/pvp/` is ignored and should not be committed.

## Account Character Visual Assets

Sources/paths:

- `account_characters.portrait_path`
- `account_characters.side_icon_url`
- `account_characters.side_icon_path`
- generated/cached files under `assets/hoyolab/characters/...`

Rules:

- portrait/crop paths are local visual assets;
- side icons are cached from already-known HoYoLAB side-icon URLs and reused;
- `side_icon_path` is used for compact overlays such as occupied
  artifact/preset/weapon owner markers and team-bonus member icons;
- side-icon failure is non-fatal and should preserve `side_icon_url`.

Dummy/mannequin placeholders:

- known dummy/mannequin ids from `hoyolab_export/crop_manifest.py` are not
  account runtime visual entries;
- filter them as entities before portrait/side-icon fallback;
- cached side icons must not make non-account placeholders visible.

## Weapon Visual Assets And Hidden Low-Rarity Weapons

Sources/paths:

- `account_weapon_observed_stacks.icon_url`
- `account_weapon_observed_stacks.icon_path`
- generated/cached files under `assets/hoyolab/weapons/...`
- `data/hoyolab/crop_manifest.json` as source/cache asset metadata

Rules:

- weapon icon mapping must use weapon identity/icon source (`icon` URL key first,
  then `weapon_id`), not display order, source row index, or equipped character;
- same weapon type at different levels/refinements normally shares one icon;
- weapon tooltip stat labels must use UI display mappings/localization, not raw
  `P20` / `P23` property ids.

Low rarity:

- 1-2 star weapons may be stored in `account_weapon_observed_stacks`;
- normal weapon visual grids intentionally hide them via
  `IGNORED_WEAPON_RARITIES = {1, 2}` / crop manifest `weaponIgnored` semantics;
- this is stored-but-hidden behavior, not missing icons and not deletion.

## Artifact SQLite Runtime / Storage

DB:

- `data/artifacts.db`

Artifact tables include artifacts, substats, equipment, tags, build presets,
build slots, build targets, artifact sets, set names, set piece icons, and set
bonus descriptions.

Structured static display-stat effects:

- `artifact_set_display_stat_effects` stores only direct always-on artifact set
  display stat effects detected from set bonus descriptions, keyed by
  `(set_uid, pieces_required, stat_key)`;
- `weapon_display_stat_effects` stores only direct always-on weapon passive
  display stat effects, keyed by `(weapon_id, refinement, stat_key)`;
- `weapon_passive_tooltips` stores localized weapon passive/effect tooltip text
  from HoYoWiki weapon `baseInfo` passive fields, keyed by `(weapon_id, lang)`;
- JSON audit/seed files for these effects are source/seed input only and are
  not runtime databases;
- TeamBuilder display stats may apply rows from these SQLite tables, but formula
  effects, conditional effects, talents, constellations, resonances, reaction
  bonuses, enemy debuffs, and combat-state toggles remain out of scope.
- the Right Panel prototype exposes these rows through bonus source display
  items/chips. The current source kinds are `artifact_set_static` and
  `weapon_passive_static`; future elemental resonance, `Moonsign`, `Hexerei`,
  lunar, and other team-bonus sources should use the same display shape instead
  of inventing another explanation layer.
- the Right Panel external-bonus toggle disables only external bonus source
  rows such as static artifact set effects and static weapon passive effects.
  It must not disable character base stats, weapon base ATK, weapon secondary
  stat, or artifact main/sub stat totals.
- HoYoLAB account weapon `desc` is flavor/lore reference text from the account
  detail payload. It is not a combat passive/effect description and must not be
  rendered as passive tooltip text.

Role:

- observed equipped artifacts from HoYoLAB are imported into artifact SQLite
  storage;
- existing `artifact_equipment` is an imported HoYoLAB observation table, not
  canonical user-managed current equipment state;
- artifact identity uses content fingerprint/dedupe, not account character
  ownership as identity;
- artifact build presets/slots/targets remain their existing model and are
  separate from account character/weapon runtime tables.
- TeamBuilder/right-panel slot main-stat badges should read actual sands/goblet
  main stats from the selected artifact build snapshot slot data, not build
  target recommendations, character element, HoYoLAB current-final stat rows, or
  selected-detail display stat order.

Do not reset artifact inventory/build preset tables during account-only storage
repairs. See `CODEX.md` artifact database section and Artifact Browser notes for
the detailed current model.

## Future Persistent Equipment State

Design handoff:

- `docs/handoff/ACCOUNT_EQUIPMENT_STATE_DESIGN.md`
- `docs/handoff/ARTIFACT_BROWSER_EQUIPMENT_UX.md`

Planned role:

- canonical user-managed current weapon per character;
- canonical user-managed current artifact slots per character;
- side-icon owner read models for artifacts, weapons, and presets;
- explicit Artifact Browser equip/apply writes.

Boundaries:

- Stage A schema/service helpers are implemented in
  `hoyolab_export/account_equipment.py` and initialized by `init_db`;
- AppShell reads/writes current weapons through
  `hoyolab_export/account_equipment.py`, including repeated-click unequip;
- AppShell reads current artifact ids through
  `account_character_equipped_artifacts` and converts them into a runtime-only
  current-equipment artifact snapshot for right-panel stats/set bonuses;
- the current-equipment snapshot is not persisted as `artifact_builds` and does
  not mutate saved preset rows;
- AppShell embeds Artifact Browser as a left workspace and reflects the
  operation target/current-equipment UI state through target selection
  highlight and the current-equipment zone. Artifact Browser manual equip,
  repeated-click unequip, and preset apply write persistent equipment through
  the same service helpers. Right-panel target sync initially becomes real
  browser selection for preset browsing; if deselected in the browser, the
  right-panel target remains only as a secondary operation target;
- separate from build preset definitions;
- separate from HoYoLAB observed current-equipped provenance;
- HoYoLAB observation apply helpers exist but are not wired to live import yet;
- missing HoYoLAB equipment data means "no data", not "clear local equipment";
- normal import must not silently clear/overwrite local equipment without the
  future auto-apply/sync policy.

Artifact Browser / owner-icon boundary:

- the top current-equipment zone is UI presentation over current equipment, not
  an `artifact_build` preset;
- applying a preset copies preset artifacts into current equipment for exactly
  one target character and does not mutate the preset;
- incomplete preset apply clears missing target slots so current equipment
  matches the shown preset;
- artifact owner icons derive from `account_character_equipped_artifacts`;
- preset owner icons derive from the current owners of artifacts in
  `artifact_build_slots`, not from `artifact_build_targets`;
- weapon owner icons derive from `account_character_equipped_weapons` and must
  not create fake weapon instance ids.
- future weapon move/swap UI must select an explicit source owner/copy when a
  `weapon_fingerprint` has no available `known_count`; do not silently steal an
  exhausted assigned weapon by fingerprint.

## Asset / Cache Layer

Generated and cached visual assets live under paths such as:

- `assets/hoyolab/...`
- `assets/artifact_sets/...`
- `data/cache/...`

Rules:

- `crop_manifest.json` is source/cache asset metadata, not the main runtime
  account DB;
- expensive repeatable image work should be cached persistently and not repeated
  in UI hot paths;
- generated local account assets are private/generated state.

Far pre-release note:

- account character portrait/icon crop resolution can later become a selectable
  generation quality (`lowres`, `1k`, `2k`, `4k`) with a regenerate/replace
  action for existing local crops;
- this should mostly change the HoYoLAB export scale / screenshot canvas size;
  the crop grid is expected to adapt automatically to the exported layout;
- keep this as a late asset-quality pass after the final card/right-panel sizes
  are known.

## Static / Reference Catalogs

Examples:

- HoYoWiki character stats catalog;
- HoYoWiki weapon stats catalog;
- character region catalog;
- SQLite `character_identity` enrichment table, built from account characters plus
  static/reference region and trait catalogs;
- stat normalization maps;
- current Right Panel team-bonus display/evaluation helpers for elemental
  resonance, `Moonsign`, and `Hexerei`;
- future recommendation or ruleset catalogs.
- refreshable character trait catalog for resonance systems such as `Moonsign`
  (HoYoWiki entry `8782`) and `Hexerei` (HoYoWiki entry `9347`) in
  `hoyolab_export/character_trait_catalog.py`. Raw/source payloads may be
  cached at `data/cache/hoyowiki/character_trait_catalog.json`; normalized
  runtime/reference data lives in SQLite.

Role:

- static/reference data, not account state;
- useful for ascension bonus/reference/fallback, stat normalization, filters,
  and future recommendation/guide features.
- runtime character filters should consume the enriched SQLite/read-adapter
  fields (`region_key`, `traits`, `is_standard_5_star`) rather than each screen
  joining raw HoYoWiki caches independently.
- account-runtime ascension bonus selection uses static HoYoWiki rows only after
  matching the row/phase by factual HoYoLAB base stat anchors from account
  SQLite sync.

Limits:

- character/weapon stat catalogs are not account character/weapon inventory;
- talent/constellation descriptions/effects are not stored in account SQLite;
- `Moonsign`/`Hexerei` are not HoYoLAB account-source fields; they are
  static/reference character traits joined into `character_identity` for
  filters, history, PvP, and resonance calculation;
- normalized trait reference data lives in SQLite tables:
  `character_trait_definitions`, `character_trait_memberships`, and
  `character_trait_tooltip_sections`. `character_identity.traits_json` remains
  the account/runtime join for owned characters, not the full reference catalog.
- HoYoWiki JSON/cache files for traits are source/debug cache only. UI/runtime
  must read normalized SQLite/reference helpers and must not fetch or parse
  HoYoWiki on hover.
- Hexerei tooltip text uses en-us HoYoWiki entry `9347` as canonical source of
  truth. The current HoYoLAB/HoYoWiki content language is a localized override;
  missing localized sections fall back to en-us. Do not machine-translate.
- the Right Panel prototype currently evaluates direct display-stat elemental
  resonance effects in code and exposes them as `RightPanelBonusSourceDisplayItem`
  chips. Implemented stat contributors are Pyro `ATK +25%`, Hydro `HP +25%`,
  Cryo `CR +15%`, Geo selected-character elemental DMG `+15%`, and simplified
  Dendro `EM +50/+80/+100`. Electro/Anemo and non-display-stat resonance
  effects are not modeled in stat rows.
- `Moonsign` is shown as a Lunar Reaction DMG indicator chip only when the team
  has at least 2 `moonsign` characters. With external bonuses enabled, it is
  calculated after direct external stat bonuses (artifact-set static effects,
  weapon-passive static effects, and elemental resonance). If all team members
  are `moonsign`, the chip remains visible but the Lunar value is 0% because a
  non-`moonsign` trigger character is required. The indicator is capped at 36%
  and does not add back into HP/ATK/DEF/EM or normal elemental/physical damage
  rows.
- `Hexerei` is display/tooltip-only for now and does not affect stats. It is
  shown as a team source only when at least 2 current team members have the
  `hexerei` trait. Hexerei source/member tooltips read cached/reference trait
  tooltip sections from SQLite and otherwise show a clear fallback. Member
  tooltips filter sections by account constellation, for example a C4 Mona
  should not show C6 Hexerei text.
- current trait keys are `moonsign` and `hexerei`. The local HoYoWiki trait
  cache carries source entry ids/URLs (`8782` for `Moonsign`, `9347` for
  `Hexerei`) and per-character HoYoWiki entry ids. Tooltip section text belongs
  in `character_trait_tooltip_sections`, not in `character_identity.traits_json`.
- team bonus icons live under `assets/team_bonus/`, including elemental
  resonance icons plus `Moonsign.png` and `Hexerei.png`. Filter icons also
  exist under `assets/filters`. Bonus strip source icons are rendered through a
  cached alpha-trim/scale helper so transparent PNG padding does not shrink the
  visible icon inside the chip. Bonus source chips follow the compact layout
  `[large source icon] [separate effect badge(s)]`; `Hexerei` uses compact
  member icons instead of numeric effect badges. Compact member side icons in
  bonus chips use a separate cached side-icon renderer: fixed scale, centered
  by width, bottom-aligned, clipped at the top if needed, and no nested square
  background.
- bonus source tooltips should be formatted once by the shared Right Panel
  tooltip formatter: title, one `Effects:` section when numeric effects exist,
  then one source/note/breakdown body. Do not repeat the same effect text in
  both the formatter and the source body.
- the Right Panel smoke supports `--team-preset fake|default|moonsign|hexerei|resonance-sanity`
  plus `--summary` for no-GUI validation. `--real-thoma` remains a shortcut for
  the default real smoke. The Moonsign preset includes an all-Moonsign team
  that should show `Lunar +0%` and a Lauma/Ineffa/Nahida/Yelan team for the
  non-Moonsign trigger case. The Hexerei preset has one team with exactly one
  Hexerei member and one team with 2+ Hexerei members. The resonance sanity
  preset covers Geo selected-character elemental damage and Dendro `EM +100`.
- there is currently no elemental resonance definition table/file and no
  resonance formula storage. Future broader structured resonance/team-bonus
  definitions can move to a normalized SQLite/static-reference table, with
  source/cache JSON used only as refresh input. Suggested source keys are
  `elemental_resonance:<element_or_id>`, `moonsign`, and `hexerei`, linked to
  active characters by element or `character_identity.traits_json`.
- standard 5-star membership is a static character trait/filter using
  `assets/filters/standard.png`; UI behavior is tri-state: show all, only
  standard 5-stars, or exclude standard 5-stars;
- account Traveler is force-marked as `standard_5_star` by Traveler character
  id in the identity join; the future dedicated Traveler model must preserve
  that trait even if account display names or elemental variants change;
- if static talent/constellation effects are needed later, create a separate
  static/reference catalog task;
- do not scrape broad HoYoLAB/HoYoWiki sources from account runtime tasks looking
  for talent effect descriptions.

Related handoffs:

- `docs/handoff/ACCOUNT_CHARACTER_DETAIL_FIELDS.md`
- `docs/handoff/ACCOUNT_SQLITE_STORAGE.md`
- `docs/handoff/STAT_NORMALIZATION.md`

## Not Stored Here / Future Boundaries

Not currently stored in account SQLite:

- GCSIM configs/formulas;
- parsed talent/constellation buffs;
- guaranteed full weapon inventory;
- unique weapon instances;
- current-equipped weapon relation as canonical account weapon storage;
- Run Workspace/saved-run immutable snapshot model.

Future saved runs must snapshot actual selected character/weapon/artifact/build
contents instead of relying only on live account/build references.

## Update Rule

When a task changes a persistent data structure, source/cache format, runtime
source boundary, visual filtering rule, or adapter ownership, update this
boundary map or the more specific handoff it points to. Keep root `TODO.md` and
`CODEX.md` as concise entrypoints, not duplicated architecture dumps.
