# TODO: GenshinTeamsTracker

This file is for future agents. Keep it current, English, and mostly ASCII. Completed history should stay compact unless it changes future architecture or implementation choices.

## Workflow Rules

- Read `CODEX.md` first.
- Keep tool usage narrow and cheap.
- Do not run tests, app startup, imports, DB scans, or broad validation unless the user asks or the change needs it.
- Use `.venv\Scripts\python.exe` for local checks when the system interpreter lacks project dependencies.
- Avoid scanning generated/private state:
  - `hoyolab_export/profile`
  - `data/`
  - `assets/hoyolab`
  - `assets/artifact_sets`
  - large JSON/image folders
- Expensive repeatable UI work should use both in-memory cache and persistent cache under `data/cache/...`; do not leave image processing/parsing in hot UI paths.
- Update this file only with active tasks and useful follow-ups.
- After each completed task, update handoff docs before final response when the task changes roadmap, state, or reusable context: mark completed subitems compactly, add durable new knowledge to `CODEX.md`/`TODO.md` or a dedicated handoff file, and remove stale active-task/development-log leftovers.
- When adding/changing persistent structures, source/cache formats, domain models, raw payload discoveries, UI prototype contracts, or long-lived research, update the relevant project map in `docs/handoff/` and keep root docs as concise entrypoint pointers.
- Do not bring Known Bugs into planning/discussion unless the user explicitly asks about bugs or the affected area.

## Known Bugs

- [ ] Changing app language can change the window size, narrowing the character selector area; the artifact grid is not recalculated afterward.
- [ ] Editing the timer for one room does not adjust overlapping room timers, so impossible totals can appear, for example room 1 ends at 9:50 (10s), room 2 ends at 9:56 (-6s), total 4s.
- [ ] After dragging a character into a team slot, the same character remains available in the character grid; characters already placed in slots cannot be moved to another slot or another team's slot.

## Current Artifact Browser State

- Artifact Browser is stable enough to stop treating it as a pure prototype, but direct main-UI integration should wait for the Run Workspace architecture below.
- Completed manual smoke passes: Build Target Selector, target persistence, build/target preview, JSON import/clear, build preset lifecycle, and custom sets.
- Compact preset rows show set-bonus metadata, sands/goblet main-stat badge, and cached set-bonus icons.
- Build preset inline rename focus is fixed: entering edit mode focuses the name field and selects text so typing/backspace works immediately without an extra click.
- Build target preview strip is a baked pixmap strip with persistent caches; it is not many child widgets and intentionally has no tooltips.
- Build preview set bonus cells and compact preset-row set bonus icons use stored 2p/4p set bonus descriptions and custom tooltips.
- Region filters are implemented through `assets/filters/Statue.png`; character regions come from HoYoWiki character list `menu_id=2`, are cached at `data/cache/hoyowiki/character_region_catalog.json`, and are joined into SQLite `character_identity` for runtime filters.
- Region/trait filters are multi-select: OR inside their own group, AND with element/weapon/rarity. Standard 5-star is tri-state: all / only Standard 5-star / exclude Standard 5-star.
- Non-priority UI polish: add custom in-app tooltips for character/target filter buttons. Do not use system tooltips there; Artifact Browser target filter system tooltips are intentionally disabled until custom tooltips exist.
- Artifact Browser has fixed bottom-row `Import JSON` / `Clear JSON` buttons; JSON clear deletes only `json_imported=1` + `import_source='artiscan'` artifacts and clears affected build preset slots.
- Sort and Sets popups toggle closed on repeated button click and order game/custom sets by owned piece count descending.
- Region/trait joins prefer HoYoWiki entry ids when available and use normalized names only as fallback.

## 1. Pre-Integration Architecture

- Do not keep developing the current main-window right panel as the final structure. It is legacy/prototype UI and should be replaced by a shared Run Workspace.
- Do not blindly discard useful legacy behavior. Extract reusable logic into modules/helpers when it fits the new model, for example timer editing that reacts to mouse wheel and updates values.
- Separate these domains clearly:
  - Account / Inventory: imported characters, weapons, artifacts, build presets, local catalogs.
  - Team Builder: current team composition, selected characters/weapons, selected artifact builds, calculated stats, resonances.
  - Scenario / Run: Abyss run, DPS Dummy run, future PvP match, enemy/room/rules metadata, timers, results.
  - Presentation / Export: shared TeamCard/RunCard components, history UI, PNG/XLSX export, simulator result presentation, PvP result export.
- Saved run history must store immutable snapshots, not live references to current account/build state. If artifacts, levels, weapons, or presets change later, old saved runs must not silently change.
- Snapshots must preserve structured information, not only images: characters, weapons, constellations/refinements when available, artifacts, set bonuses, stats, timers, run metadata, and enough data for useful later tooltips/details.

## 2. Main Run Workspace

- Replace the legacy right panel with a Run Workspace that has at least two modes/tabs: Abyss and DPS Dummy.
- Active mode controls team layout, visible inputs, which history tab opens from "open history", and which run type is saved.
- If the panel is on DPS Dummy, history opens DPS Dummy history. If it is on Abyss, history opens Abyss history.
- Abyss mode:
  - two teams;
  - rooms/chambers;
  - timers per team per chamber;
  - total timer;
  - factual DPS based on enemy HP and clear time when enemy data exists;
  - save run snapshot into the current Abyss season.
- DPS Dummy mode:
  - one team;
  - one DPS result / target setup;
  - same TeamCard logic;
  - saved into DPS Dummy history;
  - later connected to simulator UI.
- Prefer UI wording "DPS" or "factual DPS" for HP/time calculation. Keep simulator output separate as "sim DPS" with explicit GCSIM label/logo where applicable.

## 3. Shared TeamCard / RunCard

- Create reusable TeamCard / RunCard concepts shared by main Run Workspace, Abyss history, DPS Dummy history, export, simulator window, and most PvP post-draft flows.
- PvP may use different visuals where needed, but the underlying team composition logic should remain reusable.
- A team contains four characters. Each character tile/card should eventually show portrait, element, constellation, weapon, refinement when available, compact artifact set bonus info, useful current stats, and tooltip/details with full snapshot information.
- Reuse the compact artifact set bonus rendering/tooltips already implemented in Artifact Browser where possible. Do not create a second incompatible set-bonus representation unless there is a concrete reason.
- Visual design problem: weapon and artifact bonus info must stay readable without covering the portrait too much. Explore small attached badges/strips rather than fully overlaying the portrait.
- Pre-release visual pass: round/crop normal character preview portraits only after all card-like windows and slots are present, so final card treatment is consistent.
- Far pre-release asset quality pass: add a user/dev choice for generated account character portrait/icon resolution, for example `lowres`, `1k`, `2k`, and `4k`, then regenerate/replace the cropped character icons accordingly. This is expected to be a simple HoYoLAB export-scale/canvas-screenshot setting because the crop grid already adapts automatically to the exported layout; do not prioritize before the main Run Workspace/card visuals stabilize.

## 4. Team Selection and Snapshot Model

- New team builder should support drag from available list into slots, drag between slots, drag between teams, swap characters, clear slot, and disabled/hidden used characters in the available list.
- Used weapons should disappear if unique. Weapon duplicates are first-day/future patch unless current data can distinguish instances safely; do not overcomplicate MVP.
- Artifacts are not consumed by PvP deck rules unless a future ruleset explicitly says so. For normal team building, selected builds/artifacts should be shown and snapshotted.
- Snapshot actual selected artifact/build data, active set bonuses, and relevant stats when saving a run. Do not rely only on a live build preset id.

## 5. Artifact Browser Integration Into Main UI

- Do not integrate Artifact Browser as a disconnected button. It should feed artifact builds/build presets into Team Builder and TeamCard.
- The current Artifact Browser can still open as its own window, but main UI needs a clean path to select/use builds in teams.
- Preserve build presets as shared ownership categories, not "one build = one character".
- A preset can belong to Universal and/or multiple character targets; selected target filters use intersection semantics and should not auto-include Universal unless Universal is selected.
- Keep build data separate from visual skin/delegate rendering.
- Future equip-context rule: keep one shared Artifact Browser with `library mode` and `equip mode(character_slot)`, not one browser per TeamBuilder slot. Equip mode may later be docked/attached around the right panel and selected presets should immediately equip the originating character slot.
- Domain rule: a character equips a preset, and a preset assigns artifacts. Artifacts in an assigned preset are reserved by that character. Build id/name alone is not enough for saved history; saved runs must snapshot immutable artifact/build contents.
- If equip mode manually clicks artifacts instead of selecting a preset, create/update a temporary preset for that character. Temporary presets count as equipped and may later be edited like normal presets, while hidden/separated in library mode to avoid clutter.
- Occupied artifacts/presets should use compact side-profile account character icon overlays. Occupied artifacts show reserving character icon(s); conflicting presets show red/conflict outline plus owner icon(s).
- Clicking an occupied artifact in equip mode should require confirmation because it mutates another character's assigned preset. Empty current position moves the artifact and previous owner loses the slot; occupied current position swaps artifacts between the two assigned presets.
- Whole presets containing occupied artifacts should not be silently equipped with one click in MVP/design. Show conflict state and owner overlays; allow opening/editing the preset to replace conflicting pieces. Full multi-artifact preset swap can be considered later.
- Editing a preset currently assigned to a character changes that character's equipment because the character wears the preset.

## 6. Abyss History / Seasons

- Redesign history around shared RunCard/TeamCard components. The old history grid is not final and will not scale once weapons, set bonuses, simulator values, filters, and metadata are added.
- Future visual direction: use Akasha-like compact saved-run rows. Abyss rows can be paired/double team rows with character icons, weapon icons, set/build icons, room times, factual DPS, and sim DPS; hover over a character should show a rich build tooltip, and expanding the row should show full RunCard/export-ready detail.
- Abyss history structure:
  - top-level tab: Abyss;
  - inside: seasons/periods;
  - each season page shows period/timestamp, floors/chambers/enemies when known, total HP when known, saved runs, filters/sorting, and export.
- Previous seasons can be read-only or mostly read-only.
- New saved Abyss runs go into the current season.
- Saved run history must be immutable snapshots, not live references to current account/build state.

## 7. DPS Dummy History

- DPS Dummy history should use the same visual language as Abyss history but simpler.
- One team per result.
- Future visual direction: one compact team row with character icons, weapon icons, set/build icons, factual DPS, sim DPS, hover build tooltips, and expandable export-ready detail.
- Store dummy/target setup if available, factual DPS, sim DPS later, filters/sorting, and export.
- The DPS Dummy history button should open when the Run Workspace is in DPS Dummy mode.

## 8. Abyss Data Updater and Enemy Model

- Need future AbyssSeason / room / chamber / wave / enemy model.
- For each Abyss chamber/side, data should ideally support enemies, waves, enemy HP, total HP, resistances, immunities, special states, invulnerability/phases where available, and icons.
- Do not require this data for the app to function.
- Abyss source research is done; see `docs/handoff/ABYSS_ENEMY_DATA.md`, `docs/handoff/ABYSS_HP_FIXTURE.md`, and `docs/handoff/ABYSS_MECHANICS_NOTES.md`. Keep the source join resilient so one unavailable/stale source does not break the feature.
- Do not download a huge historical database initially. Update current Abyss info at the relevant time and create a new season/page if current Abyss data changed.
- No network / no data fallback:
  - still create/use an Abyss period based on the system date;
  - use the 16th day of month as the split point;
  - use a localized period label such as `16.05 - 16.06.26`;
  - show "no data" / localized equivalent where enemy data/HP is needed;
  - factual DPS from enemy HP is unavailable when HP data is missing.
- Keep in mind HP/time DPS is not exact damage dealt because waves, immunity, phases, shields, invulnerability, movement, and similar mechanics can distort it.
- Abyss enemy data audit exists at `docs/handoff/ABYSS_ENEMY_DATA.md`; the original prompt is `docs/handoff/ABYSS_ENEMY_DATA_AUDIT_TASK.md`.
- Audit result: no single reliable source currently provides current Abyss lineup + monster ids + waves/positions + ready HP totals + resists. MVP should use a resilient source join: current period/lineup/wave notes from Fandom, source-like monster ids/stats/icons/resists from AnimeGameData/GCSIM/Yatta/Ambr where available, and Fandom enemy/level-scaling pages as fallback/cross-check for floor HP multipliers, enemy HP tables, Abyss-specific resist states, and mechanics notes.
- Factual Abyss DPS should use confidence states, not a single yes/no gate. Prefer source-like/period-specific HP multipliers; if those are missing but enemy ids/counts/levels/base HP are matched, a Fandom general floor-multiplier estimate can be shown with an explicit `estimated_from_floor_multiplier` warning. If core inputs are missing/ambiguous, show enemy list/warnings and keep HP/time DPS unavailable.
- Near the end of right-panel development, surface factual Abyss DPS source/confidence near the DPS value, for example `source_like_period_multiplier`, `fandom_period_note`, `fandom_floor_scaling_estimate`, or `unavailable`. Do not present weak/estimated enemy HP DPS as exact; detailed research lives in `docs/handoff/ABYSS_ENEMY_DATA.md`.
- Current concrete HP fixture exists at `docs/handoff/ABYSS_HP_FIXTURE.md` for `2026-05-16` Floor 12. It confirms current lineup parsing, monster id/base HP/curve/resistance mapping for all inspected Floor 12 enemies, generic `2.5x` Floor 12 fallback totals, and likely current `3.75x` Stage12 totals from `LevelEntity_Monster_HpUp_Stage12_New2` / CHS `+275%` source text. It also records variant risks such as `Primo Geovishap (Cryo)` needing id `26050301`, Yatta 404s for newer enemies, Fandom display levels being one higher than AnimeGameData `monsterLevel`, and state-specific RES/mechanics on enemy pages.
- Abyss mechanics audit exists at `docs/handoff/ABYSS_MECHANICS_NOTES.md`. It uses the current Floor 12 fixture as the first-pass enemy list and records Fandom structured fields/prose tags for shields, wards, invulnerability, state RES, paralyze/downed windows, true damage HP events, summons/adds, elemental/reaction requirements, and mode-specific stat blocks.
- Backend Abyss fixture/report code exists in `hoyolab_export/abyss_sources.py` and `hoyolab_export/abyss_fixture_report.py`. Command: `python -m hoyolab_export.abyss_fixture_report --period-url https://genshin-impact.fandom.com/wiki/Spiral_Abyss/Floors/2026-05-16`. It parses Fandom period wikitext, extracts Floor 12 chamber/side/wave/enemy data, joins the confirmed current fixture aliases from `docs/handoff/ABYSS_HP_FIXTURE.md`, and emits HP estimate confidence flags such as `source_like_period_multiplier`, `fandom_floor_scaling_estimate`, and `unavailable`.
- Backend Abyss mechanics parser/report code exists in `hoyolab_export/abyss_mechanics.py`. It parses Fandom enemy-page wikitext snippets into structured fields and warning tags such as `shield_check`, `ward_or_barrier`, `phase_invulnerability`, `state_res_override`, `paralyze_window`, `true_damage_hp_event`, `summons_or_adds`, `elemental_requirement`, `reaction_requirement`, `lunar_requirement`, `high_mobility`, and `mode_specific_stats`. Next Abyss step is UI integration of factual DPS source/confidence and mechanics warnings, not another broad audit.

## 9. Stats / Resonance / Static Catalogs

- Team selection UI should eventually display current stats for each character.
- Stats may need character base stats by level/ascension, weapon base stats/substats, weapon level/refinement, artifact main/sub stats, static artifact set bonuses, and resonances.
- HoYoLAB account detail stat-sheet fields are the preferred source for account base/reference extraction when available. Source-field map: `docs/handoff/ACCOUNT_CHARACTER_DETAIL_FIELDS.md`.
- For TeamBuilder/right-panel selected details, do not use HoYoLAB stat-sheet `final` values as final stats when a virtual selected weapon/build is active; those finals describe current in-game equipment. Derive virtual build display stats from HoYoLAB base/reference values, selected weapon values, selected ArtifactBuildSnapshot totals, HoYoWiki ascension bonus matched by factual HoYoLAB base stat, and safe baselines.
- HoYoLAB stat-sheet groups `base_properties`, `extra_properties`, `element_properties`, and `selected_properties` remain useful as reference/debug. Preserve `property_type` ids as primary keys.
- Display stat order remains HP, ATK, DEF, EM, Crit Rate, Crit DMG, ER, then damage/healing bonuses. Hide zero stats except baselines: ER 100%, Crit Rate 5%, Crit DMG 50%. Raw contribution/provenance rows must not be rendered as final stat rows.
- HoYoWiki character stats catalog remains useful for ascension bonus extraction, Traveler/reference/fallback, and possible guide/recommendation parsing; it is no longer the primary source for account right-panel current stats when HoYoLAB stat sheet is available. GCSIM may still be useful as simulator/reference data later; see `docs/handoff/GCSIM.md`.
- Do not fully parse arbitrary set bonus text into formulas for MVP.
- Reasonable stats MVP:
  - calculate from known structured data;
  - include direct static display-stat bonuses only when explicitly modeled in
    SQLite (`artifact_set_display_stat_effects`, `weapon_display_stat_effects`);
  - explain applied external bonuses in the Right Panel through compact
    source chips. The prototype source item shape currently covers
    `artifact_set_static` and `weapon_passive_static`; future elemental
    resonance, `Moonsign`, `Hexerei`, lunar, and other team bonuses should reuse
    that shape.
  - keep localized weapon passive/effect tooltip text separate from structured
    static effects: `weapon_passive_tooltips` is display/reference text by
    `(weapon_id, lang)`, while `weapon_display_stat_effects` is the applied
    whitelisted stat-effect table. HoYoLAB account weapon `desc` is flavor/lore,
    not a combat passive.
  - add a later separate "combat/ability bonuses" layer for scoped bonuses such
    as Elemental Skill/Burst/Normal/Charged/Plunging DMG or CRIT modifiers.
    These should not be mixed into ordinary visible character display stats.
  - keep the Right Panel `Apply external bonuses` toggle scoped only to
    external bonus rows. It must not disable base stats, selected weapon base
    ATK/secondary stat, or artifact main/sub stat totals.
  - skip conditional bonuses or mark them as condition-required/not automatically included;
  - add manual toggles later if needed.
- Need data-driven resonance model for elemental resonances, `Moonsign`, `Hexerei`, and future resonance-like systems. Use the in-game/source terms `moonsign` and `hexerei` when searching code/docs/sources; do not substitute guessed terms.
- Elemental resonances can usually be inferred from character elements. `Moonsign`/`Hexerei` require character trait/tag data from a confirmed source such as HoYoWiki pages/lists or a local seeded/updatable trait catalog. `hoyolab_export/character_trait_catalog.py` refreshes `data/cache/hoyowiki/character_trait_catalog.json` from HoYoWiki entries `8782` (`Moonsign`) and `9347` (`Hexerei`), names the character groups only, and deliberately does not define resonance bonus formulas. Account sync joins these static tags into SQLite `character_identity` as runtime fields for filters/history/PvP/resonance calculation.
- UI should show active resonances, why each resonance is active/inactive, description tooltip, and involved characters.
- For lunar resonance, first implementation can show total bonus, contribution by character when known, and clear explanation when activation is impossible.
- Refactor future catalog/update code into a common location instead of scattering it in UI modules. Use bundled seed/static data, downloaded cache, schema version, source, timestamp, language, and updater modules.
- App should work offline with last known or bundled data.
- Data categories likely needing common catalog/updater support: artifact set catalog/icons, character base stats, weapon base stats, resonance definitions, current Abyss enemies/HP, monster stats, standard build profiles, tournament rulesets.
- HoYoWiki character/weapon stats are static/generated catalog data, not account import data. Refresh them explicitly with the backend catalog refresh path; do not fetch every character/weapon detail page from UI hot paths or ordinary HoYoLAB account update.
- Current explicit refresh path: `python -m hoyolab_export.hoyowiki_catalog_refresh`. It refreshes `data/cache/hoyowiki/character_stats_catalog.json` and `data/cache/hoyowiki/weapon_stats_catalog.json` from HoYoWiki lists plus detail pages, uses `en-us` by default, skips valid cached entries in missing-only mode, and supports `--force` after parser/source changes. Normal HoYoLAB import additionally best-effort refreshes only missing/new canonical artifact sets plus the small `Moonsign`/`Hexerei` trait catalog, so newly released sets/trait characters can be discovered without a separate manual step or a full icon recheck of every existing set.
- Future release flow can generate full sanitized catalogs once, ship them as seed/static data where appropriate, and refresh only missing/new entries after game updates.
- Future language/UI idea: support both application UI language and HoYoLAB
  content language as separate choices, especially for localized reference
  text such as weapon passive tooltips.
- HoYoWiki entries with empty/no ascension rows are not automatically non-playable junk. Some may be announced/future playable characters whose final stats are not available yet. Classify them as `future_pending_stats` / `stats_unavailable_yet` unless another source proves they are truly non-playable. If a matched account character ever has no stat rows, future `CharacterStatSnapshot` should warn instead of crashing.
- Traveler is special/deferred for account mapping: HoYoWiki list contains elemental Traveler variants as separate entries, but account Traveler / localized Traveler names must not be solved by aliasing to one variant. Future model should select an elemental Traveler variant explicitly while keeping shared account level and variant-specific talents/constellations separate. Account/default Traveler must remain marked with the `standard_5_star` trait for the Standard 5-star tri-state filter.
- Real account-matched readiness is clean enough for the next backend step: current local account maps to 74 ready characters plus 1 Traveler `special_deferred`; 68/68 account weapons are ready. Non-blocking character mapping warnings can remain, but next task can start minimal `CharacterStatSnapshot` foundation without solving full Traveler.
- Minimal `CharacterStatSnapshot` foundation exists for ordinary matched-ready characters/weapons. It is read-only/backend-only and partial: it preserves character base HP/ATK/DEF, ascension bonus separately, weapon base ATK/secondary stat, optional artifact summary, and warnings. Direct always-on display-stat artifact/weapon effects are structured separately in SQLite for TeamBuilder display rows; formulas, conditional bonuses, resonances, talents, and constellations remain excluded. Traveler remains `special_deferred`.
- Account character source shape is documented in `docs/handoff/ACCOUNT_CHARACTER_DETAIL_FIELDS.md`: current account detail data exposes useful stat-sheet rows, weapon `promote_level`, and `skills[]` talent levels. Character ascension/promote phase is not required as a raw HoYoLAB field for the current account storage model; account sync matches the needed HoYoWiki row by factual HoYoLAB base HP, then DEF, then derived character ATK. The old HoYoWiki level-only row policy remains reference/fallback behavior only; do not use it as account runtime ascension bonus selection when HoYoLAB base stat rows are present.
- Clean account character/weapon runtime storage now exists in local SQLite `data/artifacts.db` tables `account_characters`, `account_character_talents`, and `account_weapon_observed_stacks`; see `docs/handoff/ACCOUNT_SQLITE_STORAGE.md`. Normal HoYoLAB import (`python -m hoyolab_export.run_import`) now syncs these tables automatically after raw/source cache files and crop manifest are written. Raw/source cache files remain `data/hoyolab/account_characters.json`, `data/hoyolab/account_weapons.json`, and `data/hoyolab/account_character_details.json`, but normal UI/runtime account loading should use SQLite read adapters, not raw JSON. Adapter/manual debug CLI: `hoyolab_export/account_storage.py`, command `python -m hoyolab_export.account_storage` (`--download-side-icons` optionally caches already-known side icon URLs for manual resync). Read adapter functions: `list_account_characters`, `get_account_character`, `list_account_character_talents`, `list_account_weapon_observed_stacks`, `get_account_weapon_observed_stack`, and `get_account_weapon_observed_stack_by_id`. UI asset helpers in `ui/character_assets.py` convert account SQLite records into legacy grid asset items. Characters upsert by authoritative HoYoLAB `character_id`; side icon paths are deterministic local cache refs when present/downloaded by normal import or explicit manual cache; cached side icon files are reused, failures are non-fatal; talents upsert by `(character_id, skill_id)`; empty/broken character/detail sources do not wipe character/talent rows.
- Weapon storage is reconstructed observed stacks, not full inventory and not current-equipped canonical refs. HoYoLAB weapon id is a type id, not a unique account weapon instance id. Exact observed weapon identity uses normalized `weapon_fingerprint`; identical fingerprints dedupe and update non-decreasing `known_count`, while later smaller/zero observations never delete or decrease stacks. The interrupted `account_weapons` / current-equipped-ref model is replaced from the canonical path. Normal weapon asset grids intentionally hide 1-2 star observed stacks by the same `IGNORED_WEAPON_RARITIES` / `weaponIgnored` rule used by `crop_manifest`; those stacks remain stored but are not expected to have visible `weaponAssets`.
- Runtime account visual rules: dummy/mannequin IDs from `crop_manifest` are explicitly filtered before portrait/side-icon fallback; weapon stack icon paths are resolved by weapon `icon` URL key / `weapon_id`, not equipped-character or source row order; weapon tooltips use display stat names such as `Energy Recharge` / `CRIT Rate`, not raw `P23` / `P20` ids.
- Compact data/runtime boundary map exists at `docs/handoff/DATA_RUNTIME_BOUNDARIES.md`; read it before changing raw HoYoLAB caches, SQLite runtime tables, visual asset caches, static/reference catalogs, or stored-vs-hidden visual rules.
- Pure account stat-sheet helper exists in `hoyolab_export/account_stat_sheet.py`: `parse_account_character_stat_sheet(...)`, `extract_account_character_base_values(...)`, and `extract_account_weapon_property_values(...)`. It is explicit-input only, preserves `property_type`, derives character base ATK as account base ATK minus weapon base ATK, and does not mutate DB/UI/network state.
- Narrow HoYoWiki ascension helpers exist in `hoyolab_export/character_ascension_bonus.py`: `extract_character_ascension_bonus_by_base_stats(...)` is the account-runtime path and stores a bonus only after matching a HoYoWiki row/phase by HoYoLAB base stat; `extract_character_ascension_bonus(...)` remains legacy/reference level-policy behavior.
- Future Traveler model: treat account Traveler as a special/default character with auto-detected HoYoWiki elemental Traveler variants, a default Traveler icon/card, and a popup/dropdown element selector. Keep Traveler marked as `standard_5_star` in the identity/trait layer and include it in planned tri-state filtering alongside special/default character filtering; do not solve this until the Run Workspace needs it.
- Future source note: Russian HoYoWiki character pages may expose recommendation blocks for weapons, artifacts, and teams/allies. This could later feed right-side guide/info content, draft bot heuristics, and recommended stat/build hints. Do not parse it now.
- Real no-network `CharacterStatSnapshot` smoke exists: `python -m hoyolab_export.character_stat_snapshot_smoke --limit 2`. It reads only allowlisted account JSON and local HoYoWiki stats caches, uses `account_character_details.json` wiki links, and builds sanitized examples for ordinary matched-ready characters. Equipped weapon promote phase is available from `account_character_details.json -> json.data.list[].weapon.promote_level`, so weapon before/after selection uses explicit weapon data. Artifact summary is still missing and final totals remain intentionally uncomputed.
- Artifact-only build snapshot foundation exists in `hoyolab_export/artifact_build_snapshot.py`. It is explicit-input only: callers pass already-loaded raw build summaries/presets, and `CharacterStatSnapshot` carries the resulting artifact contribution without querying Artifact Browser DB/UI. Build id/name are provenance only; future saved runs still need actual artifact/build contents. Set bonus formulas, conditional bonuses, resonances, weapon passives, and final totals are still not applied.
- Real Artifact Browser build snapshot smoke exists: `python -m hoyolab_export.artifact_build_snapshot_smoke --build-name test111` or `--build-id <id>`. It opens `data/artifacts.db` read-only, loads one selected build preset, converts the existing raw build summary into `ArtifactBuildSnapshot`, and can pass it into `CharacterStatSnapshot` as explicit artifact input. The `test111` smoke confirmed build id 20, four artifact slots, missing position 5, active 2+2 set metadata, CV 95.6, proc count 12. Build name is only acceptable for explicit smoke/debug selection; final UI/team-builder paths must pass `build_id`.
- TeamCard / CharacterDetails backend data adapter exists in `hoyolab_export/team_card_data.py`. It accepts explicit selected account character + selected account weapon + prepared build snapshot, or an outer read-only build-id loader that converts the selected Artifact Browser preset to `ArtifactBuildSnapshot`. `CharacterStatSnapshot` remains DB/UI-free. `CharacterDetailsData` now carries selected character/weapon/build provenance, the snapshot/provenance layer, parsed HoYoLAB `account_stat_sheet` when raw account detail is supplied, HoYoWiki `ascension_bonus` reference data, warnings, and GCSIM-readiness notes.
- Real no-network `CharacterDetailsData` smoke exists: `python -m hoyolab_export.team_card_data_smoke --character-id 10000050 --weapon-id 13407 --weapon-level 70 --weapon-refinement 5 --weapon-promote-level 4 --build-id 20`. It reads SQLite account runtime storage and `data/artifacts.db` read-only, not raw account JSON. The smoke validates selected character + explicit observed weapon option + build id -> prepared details data with artifact contribution, while still not applying passives/set/resonance formulas.
- Minimal backend TeamBuilder slot-state model exists in `run_workspace/team_builder.py`. It stores typed selections (`SelectedCharacterRef`, `SelectedWeaponRef`, `SelectedArtifactBuildRef`) instead of legacy image paths, supports set/clear/swap/move operations, detects duplicate selected characters, and can optionally carry prepared `CharacterDetailsData`. It does not replace the legacy right panel yet.
- Isolated read-only TeamCard prototype exists: pure view-model in `run_workspace/team_card_view_model.py` plus isolated QWidget prototype in `ui/team_card_prototype.py`. Manual visual smoke launcher: `python -m ui.team_card_prototype_smoke` for real no-network `Тома` + build id 20, or `python -m ui.team_card_prototype_smoke --fake` for fake data. It consumes `TeamBuilderState` / optional `CharacterDetailsData`, displays four slots, empty placeholders, character/weapon/build labels, artifact summary, status, and compact warnings. It is not wired into the legacy right panel and is not the final Run Workspace UI.
- Isolated Right Panel / TeamBuilder Prototype v6 exists: pure view-model in `run_workspace/right_panel_prototype_view_model.py`, display stat helper in `run_workspace/display_stats.py`, and isolated QWidget prototype in `ui/right_panel_prototype.py`. Manual visual smoke launcher: `python -m ui.right_panel_prototype_smoke` with fake data by default, or `python -m ui.right_panel_prototype_smoke --real-thoma` for the no-network `Тома` + build id 20 sample plus several local no-preset character slots. The no-preset sandbox loader now uses SQLite account runtime records and observed weapon stacks, not raw account detail JSON. It keeps the v4/v5 layout, enforces a minimum standalone content width, uses square character portraits with aligned weapon/build boxes, keeps chamber factual/sim DPS columns, and shows selected-character virtual build display rows from character base + selected weapon + selected artifact build + ascension/baselines. The build box uses compact Artifact Browser preset-row set semantics: active set icons plus 2p/4p overlay/count, with `Equip`/`ART` placeholders for no-preset slots. The lower slot main-stat badge is derived from the selected artifact build snapshot's actual sands/goblet main stats; do not source it from target recommendations, character element, HoYoLAB current-final stats, or display-stat order. Selected weapon meta includes weapon base ATK and secondary stat from selected SQLite observed weapon stack/account runtime data. The selected-details bottom area is a compact external bonus source strip, not a plain set-name line; it shows modeled artifact-set and weapon-passive static effects with numeric chips and custom tooltips. Real smoke selected weapons are explicit observed weapon options from SQLite, not inferred from current-equipped provenance. It is visual-only and not wired into the legacy right panel.
- Low-priority UI polish: replace the temporary full-strip click behavior for `Apply external bonuses` with the user's custom compact toggle component, then reuse that same toggle for the Artifact Browser on/off switch. Keep selection state shown by field/border styling rather than a checkbox.
- Reusable UI rule: dense vertical card/grid panels should use `ui/utils/overlay_scroll.py::OverlayVerticalScrollArea` when native scrollbars would make content jump or reserve asymmetric empty space. It draws an auto-hidden scrollbar over the right edge, appears on scroll/edge hover/drag, and does not participate in layout width. The Right Panel prototype uses it first; apply the same utility to other suitable project scroll areas after visual verification.
- Display stat rows are virtual TeamBuilder results in this order: HP, ATK, DEF, EM, Crit Rate, Crit DMG, ER, then damage/healing bonuses. HoYoLAB stat-sheet `final` rows are reference/debug only for TeamBuilder slots and must not be shown as selected-build final stats. Raw partial labels such as `Base HP`, `Weapon ATK`, `Asc ...`, `Art CR`, `WATK`, `AER`, etc. must not be shown as final selected-detail stat rows. Direct static artifact set/weapon passive display effects may be applied only from normalized SQLite rows; formula effects, conditional bonuses, resonances, talents, and constellations remain excluded.
- Raw partial contribution labels such as `Base HP`, `Weapon ATK`, `Asc ...`, `Art CR`, `WATK`, `AER`, etc. are internal/debug provenance and should not be shown as final selected-detail stat rows.
- Stat normalization / GCSIM stat-key mapping handoff exists at `docs/handoff/STAT_NORMALIZATION.md`; backend code exists in `hoyolab_export/stat_normalization.py`. It maps project artifact `property_type` values to normalized keys/GCSIM `add stats` keys, converts percent-point values like `46.6` to ratio values like `0.466`, keeps flat stats unchanged, treats Crit Value / Proc Count as virtual metrics, and intentionally does not compute final totals or apply passives/set bonuses/resonances.
- Next Run Workspace/UI step after visual inspection of Prototype v6: inspect real multi-character layout, no-preset states, and build-slot readability; then refine exact proportions if needed before planning/building the first Run Workspace / TeamBuilder shell around the shared TeamBuilder/TeamCard concepts.
- Weapon passive/refinement text is reference data only for now; do not parse free text into stat formulas or auto-apply passive stat bonuses unless a future effect is explicitly modeled/whitelisted.
- Standard 5-star filter exists with `assets/filters/standard.png` and tri-state behavior: show all / only Standard 5-star / exclude Standard 5-star. Membership is stored as static trait `standard_5_star` in `character_identity`; HoYoWiki entry `2952` is the source context, while the current API payload is not a clean structured character list, so the 5-star standard character membership is seeded by explicit HoYoWiki character entry ids. Traveler is intentionally included in this trait and must stay included when the dedicated Traveler model is implemented.
- Future storage audit/refactor: account character/weapon runtime tables are started; next audits should decide which remaining generated JSON/cache files should stay as small rebuildable source caches or seeds and which should be normalized into SQLite/catalog DB tables. Prefer DB storage only for runtime-critical data that is frequently joined, mapped, filtered, queried, reported, or used by stat calculator/UI. Remaining likely candidates include HoYoWiki character stats, weapon stats, character traits, character region catalog, mapping reports / alias override tables, and other large generated account/catalog JSON files after usage audit. A two-layer model is acceptable: raw/source JSON cache for fetched HoYoWiki/HoYoLAB data plus normalized DB tables for lookup, mappings, aliases, reports, UI, and stat calculation.

## 10. Export

- Abyss history and DPS Dummy history need export.
- Target formats: PNG/image for visual sharing and XLSX for analysis/comparison. CSV/HTML can be optional fallback later.
- PNG export should reuse the same visual components/cards as history where practical.
- XLSX should be data-oriented and include season/period, date, run type, chamber/side, team, characters, weapons, artifact set bonuses, timers, factual DPS if available, sim DPS if available, notes/warnings.
- Do not prioritize import of history as a separate feature. Later full offline profile import/export can include history.

## 11. GCSIM Integration

- GCSIM is a major future feature and should influence architecture now, but implementation comes later.
- Detailed GCSIM research handoff lives in `docs/handoff/GCSIM.md`; read it before implementing any engine download/runner/config work.
- Stat/GCSIM `add stats` key mapping handoff lives in `docs/handoff/STAT_NORMALIZATION.md`; the pure normalization layer exists in `hoyolab_export/stat_normalization.py`. Use it before final stat totals or GCSIM config generation.
- Do not cram detailed GCSIM into the small TeamCard. Right panel should show only compact factual/sim DPS summary and readable GCSIM button/status; detailed GCSIM/rotation editor should open as a larger overlay/drawer around the right panel. If GCSIM lacks a character/reaction implementation, show a clear unavailable status.
- Each team/run card should eventually have simulator action, GCSIM logo/label, and result area for sim DPS.
- Clicking the GCSIM logo should show a dialog like "Open GCSIM website?" before opening the official GCSIM site, for useful attribution and license/credit clarity.
- Before bundling or modifying GCSIM, verify current license/attribution requirements. It is believed to be MIT-compatible, but do not rely on memory.
- Simulator window should receive team data from TeamCard/TeamSnapshot: characters, constellations, weapons, refinements, artifacts, stats, set bonuses, talents if available, rotation, target/enemy setup.
- Implement GCSIM for DPS Dummy first:
  - one team;
  - one target;
  - configurable HP/resistance or supported target setup;
  - rotation editor;
  - sim DPS result;
  - comparison with factual dummy DPS if available.
- GCSIM for Abyss later should start with simplified modes: single target, multi-target, simplified room, manual target. Do not promise perfect full-Abyss simulation.
- For Abyss, compare factual DPS from HP/time with sim DPS from simplified/current selected target.
- Later GCSIM implementation/research follow-ups from `docs/handoff/GCSIM.md`:
  - CLI/binary/library options;
  - config format;
  - enemies/targets;
  - rotation representation;
  - output format;
  - cancellation/timeouts;
  - result parser;
  - optimizer functionality;
  - whether local GCSIM data can provide character/weapon base stats;
  - where standard/KQM-style builds come from.
- Possible architecture names: `GcsimEngineManager`, `GcsimConfigGenerator`, `GcsimRunner`, `GcsimResultParser`, rotation editor, result cache keyed by team/build/rotation/target/gcsim version.

## 12. KQM / Standard Builds Research

- Investigate where GCSIM gets default/standard character builds.
- Do not hardcode "KQM standards" until source, license, and data format are verified.
- Research whether this data is actually KQM standards, where it is stored, whether it can be used legally/technically, and what it contains: artifacts, talents, weapons, rotations, assumptions.
- Future uses: simulator fallback, draft bot, account-independent team estimates, comparing user builds to standard baseline.

## 13. Artifact Optimizer

- Future advanced feature: find the strongest build on the account for a selected team and rotation.
- Target DPS Dummy / simulator workspace first. Do not attempt full Abyss optimization initially.
- Full optimization across four characters, thousands of artifacts, set bonuses, off-pieces, and multiple rooms is combinatorially huge. Use heuristics, not full brute force.
- Potential staged approach:
  - use current or standard build;
  - run simulation;
  - estimate damage share;
  - choose candidate set templates;
  - select top-N artifacts per slot/stat weighting;
  - generate limited candidate builds;
  - simulate top-M candidates;
  - cache results;
  - show "best found", not "absolute optimum".
- Investigate whether current GCSIM already has usable optimizer-like functionality.
- Keep the user's simplified idea for research: use default standards, test set templates quickly, identify promising configurations, apply filters, then search best artifacts matching the configuration.

## 14. Offline Profile

- Current profile import/export should eventually become full offline profile import/export, not partial character/profile data.
- Future full profile should include, where safe: account characters, weapons, artifacts DB, build presets, run history, settings/local state needed for offline use, and relevant local catalog/cache data if appropriate.
- It must not include cookies, auth tokens, browser profile/session data, or private debug dumps.
- Use versioned profile format and safe restore/backup semantics.
- When improving offline profile export/import, include `data/hoyolab/account_language.json` alongside account details, characters, weapons, and crop manifest.

## 15. Tournament / PvP

- PvP is experimental and important long-term, but do not mix it into MVP before normal run/history/simulator features work well.
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
- Future custom tournament system idea: balance not only by character cost/tier but also by account artifact strength. Keep this as design/research, not immediate implementation.
- PvP ruleset audit exists at `docs/handoff/PVP_RULESETS_AUDIT.md`. Gentor exposes structured public JSON via `https://gentor.com.br/planilha` / `/planilha/{id}` with character C0-C6 costs, weapon R1-R5 costs, character-specific weapon overrides, tiers/restrictions, draft config, and optional TypeScript draft script.
- Backend `TournamentRulesetV1` model and validation report exist in `hoyolab_export/tournament_ruleset.py` and `hoyolab_export/tournament_ruleset_report.py`. Command: `python -m hoyolab_export.tournament_ruleset_report --ruleset-json samples/rulesets/minimal_ruleset.json`. MVP accepts normalized JSON and simple CSV files, reports missing/duplicate/unknown/unsupported fields, and does not execute third-party TypeScript scripts.
- XLSX import and Gentor website/API adapter remain future work after the internal schema/report are useful. Next PvP step is UI/import flow or deck validation, not another source search.
- Deck builder should evaluate total cost, tier constraints, invalid choices, and why a deck is invalid.
- Lobby/networking stages should be realistic:
  - local/hotseat lobby;
  - LAN/direct IP or manual connection;
  - import/export lobby state fallback;
  - investigate P2P with connection code;
  - investigate STUN/signaling/relay;
  - optional user-hosted relay or future server only if resources/donations justify it.
- Do not promise fully reliable serverless P2P; NAT, CG-NAT, firewalls, routers, and provider restrictions can break direct connections.
- PvP roles: player 1, player 2, spectator, moderator/judge, host.
- Draft engine must be generic/data-driven and support ban order, pick order, timers, locked picks, unavailable characters after pick/ban, rule validation, and action log.
- PvP result confirmation should bind confirmations to a state hash. Any result change after one player confirms clears that confirmation. Final means both players confirmed the same unchanged state inside the app.
- Do not claim the app guarantees real-world truth of entered timers. It can guarantee only that both players confirmed the same unchanged in-app result state.
- Export result image should include players, rooms, teams, timers per room/run, total timers, winner, confirmation status, statement like "confirmed by both players in GenshinTeamsTracker", and maybe session id/hash.
- PvP multi-run timer logic should support cumulative totals across games.

### PvP / Tournament Analytics

- Future analytics feature, not immediate MVP: collect local/in-app statistics across matches/games for characters and weapons.
- Character analytics can include winrate, banrate, pick/draft frequency, deck inclusion rate, account ownership rate, and constellation-tier breakdown where useful. Different constellations can be treated as separate statistical variants.
- Constellation ownership is cumulative/inclusive upward, not independent buckets. Example: C1 = 50% and C2 = 40% means that among players/accounts with the character, some have C1 only and 40% have C2 or higher. UI can show an overall character row first, then expandable constellation details with exact percentages where useful.
- Weapon analytics can mirror character analytics where applicable: winrate, pickrate/usage rate when the weapon exists on the account, and deck inclusion/selection rate. Initial version can ignore ascension/refinement tiers unless later needed.
- Use cases: draft bot heuristics, tournament balancing, tierlist-like analysis, custom ruleset balancing, and checking whether artifact/account strength changes results.
- Privacy: keep analytics local/in-app first. Any global/shared analytics must be opt-in and needs privacy policy/anonymization decisions. Do not imply online telemetry now.

## 16. Draft Bots

- Future bots should let the user practice drafts when no one is available.
- Start with a rule-based bot, not global self-learning.
- Bot should consider current Abyss, tournament rules, cost/tier limits, enemy features, elements, immunities/counter-picks, team archetypes, synergy/anti-synergy, and rough character strength.
- Possible later stages: local imitation bot trained from user draft history, opt-in global draft data only with privacy policy/infrastructure, anonymization, and explicit consent.
- Bot logic should use metrics/tags, not only memorized character names, so new characters are not ignored.
- Useful tags/metrics: role, element, archetype, pick/ban priority, synergy, anti-synergy, Abyss suitability, historical pick/ban rate when available.
- After draft, bot should assign picked characters into teams/rooms using Abyss enemy features, similar GCSIM team/rotation data, KQM/default standards, assumed fallback talents, reasonable weapon fallback, and other available structured data.

## 17. Donation / Support Page

- Future non-core task: add a support/donation page/dialog.
- It should say users can support development and can potentially donate toward a specific major feature, but specific feature requests should be discussed with the developer first for feasibility.
- Mention that some features may depend on external APIs, licenses, servers, infrastructure, or third-party data, so not every requested feature is guaranteed feasible.
- Do not clutter core UI with donation content.

## 18. Far Future Inspiration / Monetization

- Non-MVP inspiration only: optional custom character icons/profile cosmetics, loosely inspired by Akasha-like profile customization.
- Optional tiny local AI companion could help with UI, comment on builds/runs, and lightly praise/tease the user, but only if it can run on weak PCs and stays optional.
- Investigate whether GitHub distribution can support paid feature unlocks; otherwise research a separate paid executable, overlay, or license mechanism compatible with the free app. This must not shape MVP architecture.

## Other Future / Maintenance Items

- Add color highlighting for build summary Crit Value and Proc Count later; choose thresholds/colors first.
- Later unify reset controls in target selector, sort popup, and sets popup.
- Future polish: make Sort popup and Sets popup selection behavior visually consistent with artifacts/targets/presets.
- First-day/future patch: automatic proc counting for imported Artiscan artifacts.
- Check other export/import services and compatibility.
- Do not do final cleanup of old DB physical schema until the new browser path is stable.
- Later migration: recreate/drop old `artifacts.icon_id` and `artifact_icons` physical leftovers if they still exist in local DBs.
- Keep `artifact_set_piece_icons` as the browser icon source by `(set_uid, pos)`.
- Do not reintroduce per-artifact icon cache or `artifact_icons` fallback.
- Keep `ru`, `en`, and `pt-br` locale files in sync when adding UI strings.
- Commit seeded artifact catalog resources when ready: `data/static/artifact_set_catalog.json` and `assets/artifact_sets`.
- Keep local account/generated state ignored: `data/hoyolab`, `data/artifacts.db`, `assets/hoyolab`, browser profile/session/debug/download outputs.
- Keep Artiscan sample files under `samples/artiscan/` unless a future import task needs another layout.
- Retry normal `git push` for local commit `1ae2de6` after previous GitHub Internal Server Error; do not force-push.
