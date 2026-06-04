# CODEX: GenshinTeamsTracker

This file is written for future coding agents. Keep it compact, English, and mostly ASCII so it is cheap to read and unlikely to cause encoding friction.

## Operating Rules

- The user usually writes in Russian, but project handoff files should stay in English.
- Be frugal with context and tool output.
- Prefer narrow `rg` queries and small file slices.
- When the user is asking to discuss, clarify, reason about, decide on rules, or validate an approach, treat the turn as discussion-only. Do not edit files or apply changes until the user explicitly asks to implement, apply, save, or write them. This rule applies by intent in any language, not by exact words.
- Do not treat an acknowledgement of understanding as permission to implement. Phrases in any language that mean "I understand", "got it", "yes, that is the idea", or similar are not approval to edit files.
- Before implementing a task specification, do a brief preflight against the relevant current code and handoff contract. Look for incorrect assumptions, contradictions, missing ownership boundaries, and wording that can reasonably lead to materially different architecture, behavior, or visible UI. Ask focused questions and wait for answers before editing when those issues affect the solution. Do not turn this into a questionnaire for incidental details that can be resolved safely from existing project patterns.
- The user leaves room for engineering judgment on local technical decisions that are not fixed by the task. After the preflight contract is clear, discover and fix narrow implementation defects needed for a correct result, even if the task author could not know about them. Example: replace display-text-based control routing with stable ids when localization makes the existing shortcut unsafe. If a discovered issue requires a broader redesign or a separate product decision, report it as a follow-up instead of silently expanding scope.
- If a user term can reasonably refer to multiple UI, data, or architecture entities, do not silently choose one when the interpretations would materially change the implementation or the answer. State the plausible meanings briefly, ask which one is intended, and wait for clarification before proceeding. Apply the same rule to technical questions, not only file edits. Do not ask unnecessary questions when the ambiguity does not affect the result.
- If the user asks to make UI "like" an existing project surface, inspect and reuse that working implementation pattern before inventing a new one. First identify the working class/function, coordinate system, parent or viewport used for painting, constants controlling size/offsets, and whether layout size is affected.
- For visual placement bugs, do not repeatedly tweak offsets after failed screenshots. After one failed visual attempt, stop and inspect coordinate systems and actual rects. After two failed attempts, ask for confirmation or more data before further changes.
- Before changing Qt overlay or painting coordinates, identify the source and target coordinate spaces. Do not use `mapTo(other_widget, ...)` for sibling overlays unless the widget relationship is verified; use a known common ancestor or global mapping when needed.
- Do not anchor normalized icon assets by alpha bounds unless the user explicitly asks for content-aware placement. If assets share a calibrated canvas, position the full canvas with one formula and treat silhouette differences as intentional content inside that canvas.
- Do not claim understanding and start implementing if the requested visual or coordinate model is not concrete. Restate what stays unchanged, what layer changes, what coordinate anchor is used, and what existing implementation is being copied; ask a question if any of those are unclear.
- Final AppShell startup must support adaptive downscale on screens narrower
  than the 1920px reference width. Keep the calibrated design/layout constants;
  scale the rendered UI down instead of compressing layouts or lowering minimums.
- Do not recursively list or read generated/private state unless explicitly needed:
  - `hoyolab_export/profile`
  - `data/`
  - `assets/hoyolab`
  - `assets/artifact_sets`
  - image folders and large JSON dumps
- Do not run tests, imports, app startup, DB scans, image parsing, or broad validation unless the user asks or the current code change genuinely needs it.
- Use `.venv\Scripts\python.exe` for local checks when the system interpreter lacks project dependencies.
- If the user says "look only", "do not run", "just understand", or asks for handoff/context updates, inspect only lightweight text metadata and update notes.
- Never revert user changes. The worktree is often dirty.
- Use `apply_patch` for file edits.
- In this repo, handoff context means `CODEX.md`, `TODO.md`, and `docs/handoff/*.md`. When the user asks to update or clean handoffs, include all three entrypoints unless they narrow the scope.
- `tools/future/` is reserved for narrow debug/manual utilities that are useful now
  and may become product/admin features later. Do not put ordinary experiments
  there. Use it only when the user explicitly asks, after clarification, or when
  a tool is genuinely reusable and no planned product surface owns it yet.
  Research probes still belong under `tools/experiments/`.
- After every completed task that changes roadmap, architecture state, or reusable context, update the relevant handoff docs before final response. Mark completed subitems compactly, add durable new knowledge to `CODEX.md`/`TODO.md` or a dedicated handoff file, and remove stale active-task/development-log leftovers instead of letting old "next steps" linger.
- After every completed pushable task, include one short Russian past-tense commit message in the final response.
- When adding or changing any persistent project structure, source/cache format, domain model, or long-lived UI/data contract, update the relevant project map under `docs/handoff/` and keep root docs as concise pointers. Examples: backend data model -> architecture/data map; raw payload discovery -> source-field reference; UI prototype contract -> UI architecture notes; GCSIM/Abyss research -> dedicated handoff file.
- Obsidian map maintenance: The Obsidian vault is stored in `docs/obsidian/GTT/`. `docs/obsidian/GTT/GenshinTeamsTracker.canvas` is the human project navigation map. `docs/obsidian/GTT/DataFlow.canvas` is the human data-flow map. `docs/obsidian/GTT/SourceBoundaries.canvas` is the human source/runtime boundary map for avoiding data-owner confusion. These maps do not replace `CODEX.md`/`TODO.md` or detailed handoff files. After meaningful structural changes, update the maps together with handoff files when the change affects human understanding of the project layout: new major subsystem, renamed/moved important folder, changed data flow, changed current priority, changed architecture direction, or an important feature moving from planned to active/done. Do not update maps for tiny bugfixes, one-line styling changes, or internal refactors that do not affect the project map.
- Project SVG UI icons should go through `ui/utils/icon_utils.py` auto-contrast helpers instead of direct raw SVG loading or hardcoded final icon colors. This is needed for future theme support.
- Any new user-facing UI text must be added through `localization/locales/*.json` and read with the localization helpers (`tr` / `tr_for_language`) instead of being hardcoded in widgets, view-models, or tooltip formatters. Debug/provenance strings can stay internal, but anything visible in the app needs ru/en/pt-br entries when the feature is added.
- New user-facing tooltips must be custom in-app tooltips, not native Qt/system
  tooltips. Do not use `QToolTip` or `QWidget.setToolTip(...)` for new UI
  features except to explicitly clear/suppress a native tooltip while a custom
  tooltip controller is installed. If a task says "HTML/text tooltip" or "first
  pass text tooltip", interpret that as the content rendered inside the custom
  tooltip surface, not permission to use the native Qt tooltip. If the existing
  custom tooltip helper cannot support required content such as images, keep a
  typed tooltip payload in the view-model and implement the narrow custom text
  popup first; do not fall back to a native tooltip silently.
- If a feature performs expensive repeatable work, do not keep it only in UI hot paths and do not rely only on in-memory cache. Use in-memory cache for repeated work inside one session and persistent local cache under `data/cache/...` for results reusable between window/app openings. Examples include trim/mask/composite pixmaps, scaled/tinted asset preparation, external/catalog parsing, expensive derived data, and any repeated operation causing visible delay when reopening a window/app or switching views. Create cache directories automatically. Cache keys must include all inputs affecting output: source file path or stable id, source file mtime/size or content hash where applicable, target dimensions, algorithm/cache version, and visual parameters such as padding, alpha threshold, feather, badge text, theme/colors if relevant. Recompute only when the cache key/version/input changes. Do not do expensive image processing/parsing directly in `paintEvent` or frequent UI hot paths. If a new feature introduces visible delay, identify the expensive step first, then design cache/invalidation explicitly.
- When profiling finds a repeatable but non-urgent prewarm/cache candidate, record it in the loader/prewarm backlog in `TODO.md` and the relevant handoff file. Do not silently drop these findings, and do not immediately hide current bugs behind a loader unless that is the approved task.
- Future storage direction: do not migrate every generated JSON/cache file into SQLite. Keep JSON when it is a small rebuildable source cache or seed-like file. Account character/weapon runtime tables now exist in local SQLite; for remaining catalog/cache data, audit usage and move only runtime-critical, frequently joined, mapped, filtered, queried, reported, or stat-calculator data into normalized SQLite/catalog DB tables. A two-layer model is acceptable: raw/source JSON cache for fetched HoYoWiki/HoYoLAB data plus normalized DB tables for lookup, mappings, aliases, reports, UI, and stat calculation. Likely remaining candidates after usage audit include HoYoWiki character stats, weapon stats, character traits, character regions, mapping reports / alias overrides, and any large generated account/catalog JSON that becomes runtime-critical.
- For hot UI panels/lists, especially Artifact Browser and right-panel widgets, avoid destructive widget rebuilds when structure did not actually change. Keep QWidget instances parented in one stable layout and update state/content/visibility in place.
- Do not cache QWidget instances by removing them from layouts and re-adding them later. That pattern caused blank transient windows and multi-second first-init regressions. If widgets are cached, they must stay owned by a stable parent/layout; filtering should usually be `setVisible(...)`, checked-state sync, property sync, and content/icon updates only when source data changes.
- Avoid intermediate visible placeholder states during deferred load/hydration. If fast UI state is followed by async/deferred hydration, cancel stale pending refresh timers and show only the final hydrated panel state unless the placeholder is an intentional loading design.
- Keep panel geometry stable across selected/empty/hydrated modes. Do not let details/side panels collapse or expand in ways that move unrelated content; use stable skeletons, persistent child widgets, and reserved/minimum height where needed.
- AppShell top-level minimum size is a global state-independent contract. Do not rely on the current `QStackedWidget` page or Artifact Browser selected-target/no-target state to define the window minimum; those visibility changes alter `minimumSizeHint()` and can clip the fixed current-equipment/build-preview area.
- AppShell adaptive downscale is a final-app requirement, not only an
  `app_shell_smoke` convenience. When AppShell becomes the production entrypoint,
  run the same startup scaling bootstrap before `QApplication` is created.
- If a layout trace shows different `after` and `settled` geometry, do not trust synchronous `layout.activate()` alone. Prevent the intermediate frame from painting by disabling updates during the model/layout mutation and re-enabling updates on the next event-loop tick after a final layout settle.
- Avoid many child widgets for non-interactive repeated visual strips. Use baked pixmaps when appropriate, while preserving drag, wheel, and edge-hint behavior for scroll strips.
- For dense card/grid panels with vertical overflow, prefer `ui/utils/overlay_scroll.py::OverlayVerticalScrollArea` over native vertical scrollbars when scrollbar appearance would change content width. The overlay scrollbar should not reserve layout width, should appear on scroll/edge hover/drag, and should auto-hide when idle.
- Build preset row names must use flexible leftover space, not fixed magic widths. Fixed metadata/actions define the right side; long text should clip/marquee instead of expanding rows or reintroducing horizontal scrolling.
- Reusable pixmap operations belong in `ui/utils`, not inside large window classes. Window classes should resolve data/paths, choose modes, and call helpers rather than owning generic trim/mask/composite/cache logic.
- New PNG/raster UI assets must use the shared high-DPI pixmap path in
  `ui/utils/hidpi_pixmap.py` or an existing helper built on it. Do not add raw
  `QPixmap.scaled(...)` in UI code unless that local code also handles logical
  size, effective DPR, cache keys including DPR/source identity, and
  `DevicePixelRatioChange` / screen-change refresh. Startup `QT_SCALE_FACTOR`
  downscale for small monitors is separate from image DPR; raster assets must
  clamp effective pixmap DPR to at least `1.0` so they are not double-shrunk.
- New or refactored reusable UI code must use shared colors from `ui/utils/ui_palette.py` instead of introducing new literal hex colors. Do not mass-migrate old QSS blocks just for cleanup; migrate legacy colors only when that UI area is being actively changed.
- Reusable filter buttons must use `ui/utils/filter_button_style.py`; do not
  create local filter-button QSS copies.
- For Qt/PySide visual clipping bugs, diagnose geometry before layout tweaks:
  measure widget size, scroll viewport/content size, scrollbar maximum, and QSS
  box-model effects. In QSS, button `min-width`/`max-width` may behave like
  content-box sizing, with border and padding increasing the real outer size.
- If an English technical task contains inconsistencies, suspicious requirements, obvious mistakes, or unclear contradictions, point them out before starting implementation.
- Do not invent concrete correctness-critical values in final code, patches, or task text. Filenames, paths, asset names, localization keys, IDs, function/class names, DB fields/tables, data formats, commands, and API/library versions must be explicitly provided by the user, discovered in current project files, or confirmed by the user first. If such a value is missing, stop and ask; do not insert guessed defaults/placeholders with notes like "change this later".
- When adding new modules or tests that contain temporary fixtures, hardcoded
  research data, provisional adapters, sample-only values, or intentionally
  incomplete behavior, add a short module docstring/comment explaining what is
  temporary, what source/handoff it came from, what future implementation should
  replace it, and which tests are pinning the temporary contract. Do not leave
  placeholders implicit.

## Project Goal

GenshinTeamsTracker is a local PySide6 desktop tool for:

- importing a Genshin Impact account state from HoYoLAB;
- cropping and showing local character/weapon icons;
- dragging characters/weapons into team slots;
- timing and saving runs;
- importing artifact data into SQLite;
- building an Artifact Browser with sets, custom tags/sets, sorting, build presets, target ownership, and future drag/drop build integration.

## Main Areas

- `main.py`: PySide6 app entrypoint.
- `ui/main_window.py`: main app window, team builder, HoYoLAB import button, character/weapon filters.
- `ui/character_assets.py`: shared HoYoLAB asset item helpers, character filter constants, character filter/sort logic.
- `ui/utils/icon_utils.py`: cached, HiDPI-safe SVG UI icon tinting and auto-contrast helpers.
- `ui/widgets/`: shared PySide widgets such as loader, draggable icons, history.
- `hoyolab_export/`: HoYoLAB auth/export/import pipeline, artifact DB helpers, HoYoWiki catalog/cache helpers.
- `localization/`: JSON-backed app localization.
- `ui/artifact_browser/`: isolated Artifact Browser module.
- `run_workspace/gcsim/`: isolated backend foundation for future local GCSIM engine lifecycle, including the transactional engine-store/update prototype and dev command `python -m run_workspace.gcsim.engine_update --release latest`; optional `--probe-runtime` runs Go through project-local `.go/` cache/bin paths.
- `docs/handoff/`: detailed project maps and research handoffs. Root `TODO.md` and `CODEX.md` remain the entrypoints.
- `docs/handoff/DATA_RUNTIME_BOUNDARIES.md`: compact map of raw/source caches, runtime SQLite tables, visual asset caches, static/reference catalogs, and stored-vs-hidden UI rules.
- `docs/obsidian/GTT/GenshinTeamsTracker.canvas`: human project navigation map for major areas, subsystem status, priorities, and important paths. It is not detailed agent context.
- `docs/obsidian/GTT/DataFlow.canvas`: human data-flow map from HoYoLAB export through caches/databases to selected-details UI and future Run Workspace.
- `docs/obsidian/GTT/SourceBoundaries.canvas`: human source/runtime boundary map for account JSON, SQLite runtime data, static/reference catalogs, artifact/build storage, and UI display ownership.
- `data/`: local generated profile/account state. Treat as private/generated.
- `assets/hoyolab/`: generated local account icons. Treat as private/generated.
- `assets/artifact_sets/`: generated or seeded artifact set piece icons.

Important generated/seed files:

- `data/hoyolab/account_characters.json`
- `data/hoyolab/account_weapons.json`
- `data/hoyolab/account_character_details.json`
- `data/hoyolab/account_language.json`
- `data/hoyolab/crop_manifest.json`
- `data/artifacts.db`
- `data/static/artifact_set_catalog.json`

## HoYoLAB Import Pipeline

Current production command:

```powershell
python -m hoyolab_export.run_import
```

Pipeline summary:

1. Open HoYoLAB with the app browser profile.
2. Export the HoYoLAB image and capture layout/root metadata.
3. Collect `character/list` and clean inventory JSON.
4. Fetch batch `character/detail` for real character ids.
5. Detect HoYoLAB content language from the real detail request.
6. Resolve the current Spiral Abyss period for source-data cache refresh:
   HoYoLAB overview first, then Fandom latest, then Nanoka live metadata.
7. Save `account_language.json` and `account_character_details.json`.
8. Ensure artifact set catalog and localized set names.
9. Ensure HoYoLAB `relic.set.id -> set_uid` mapping via a service EN-pass when needed.
10. Import/update artifacts into `data/artifacts.db`.
11. Crop characters/weapons and merge current assets/manifest.

Critical rules:

- Do not use image matching, cv2, perceptual hashes, or external artifact databases.
- Do not assume HoYoLAB `set_id` equals HoYoWiki `entry_page_id`.
- Do not import EN `character/detail` as user data. It is only for set id/name mapping.
- Do not overwrite localized character, weapon, stat, or artifact display data with the EN service payload.
- HoYoLAB/API content language and UI language are separate.
- Ordinary HoYoLAB update must preserve existing local HoYoLAB data/assets if it fails early.
- Ordinary HoYoLAB update must not fetch all HoYoWiki character/weapon detail pages. Character/weapon stats catalogs are refreshed only through the explicit static catalog refresh path.
- Abyss source-data period refresh uses source priority HoYoLAB -> Fandom latest -> Nanoka live, records fallback metadata in `data/hoyolab/spiral_abyss_period.json`, and must not use local system date as source-data authority.
- Destructive profile cleanup belongs to explicit profile sign-out or offline profile restore.
- The export image stage drives HoYoLAB's share/save-image UI. It waits briefly for visible
  `gt-image--loading` placeholders, retries the save-image click if no browser download event
  arrives, then falls back to the captured html2canvas PNG or a DOM-root screenshot.
- Far pre-release asset-quality idea: allow choosing generated account character
  portrait/icon resolution such as `lowres`, `1k`, `2k`, or `4k`, then
  regenerate/replace the cropped character icons. This should be mostly a
  HoYoLAB export scale / screenshot canvas setting because the crop grid is
  expected to adapt to the exported layout automatically. Keep it late, after
  Run Workspace/card visuals stabilize.

## HoYoWiki Static Catalogs

Character and weapon stat catalogs are static/generated catalog data, not account import data.

- Explicit refresh command: `python -m hoyolab_export.hoyowiki_catalog_refresh`.
- Default language is `en-us`; display localization can be added later.
- Cache outputs:
  - `data/cache/hoyowiki/character_stats_catalog.json`
  - `data/cache/hoyowiki/weapon_stats_catalog.json`
- Refresh flow:
  - fetch character list from HoYoWiki `menu_id=2`;
  - fetch weapon list from HoYoWiki `menu_id=4`;
  - fetch detail pages only inside the explicit refresh command;
  - parse character/weapon `component_id == "ascension"`;
  - missing-only/default mode keeps valid cached entries and fetches missing/invalid ones;
  - `--force` refetches all entries after parser/source changes;
  - one failed entry is reported without discarding safe existing cache entries.
- Mapping report list fetching is separate from catalog refresh detail fetching. Do not make mapping/report utilities fetch every detail page.
- Normal HoYoLAB import best-effort refreshes only missing/new canonical artifact sets and the small `Moonsign`/`Hexerei` trait catalog because those catalogs directly affect newly imported account/artifact data. It must not full-recheck every existing artifact set icon during ordinary import. Character/weapon stats detail catalogs still use the explicit refresh command.
- Future release can ship sanitized seed/static catalogs and then refresh only missing/new entries after game updates.
- HoYoWiki entries with empty/no ascension rows are not automatically non-playable junk. Some may be announced/future playable characters whose final stats are unavailable. Classify them as `future_pending_stats` / `stats_unavailable_yet` unless another source proves they are truly non-playable. If a matched account character has no stat rows, future `CharacterStatSnapshot` should warn instead of crashing.
- Traveler is special/deferred for account mapping. HoYoWiki Traveler elemental variants are normal catalog entries, but account Traveler / localized Traveler names must not be aliased to one variant. A future model should treat account Traveler as a special/default character, auto-detect HoYoWiki elemental Traveler variants, use a default Traveler icon/card with popup/dropdown element selection, separate shared account level from variant-specific talents/constellations, keep Traveler marked as `standard_5_star`, and include Traveler in planned tri-state filtering alongside special/default character filtering.
- Current real account-matched readiness is clean enough for `CharacterStatSnapshot` foundation: 74 account characters are ready, account Traveler is `special_deferred`, and 68/68 account weapons are ready. Do not block the first snapshot foundation on full Traveler modeling.
- Minimal `CharacterStatSnapshot` foundation exists in `hoyolab_export/character_stat_snapshot.py`. It is read-only/backend-only and partial: it preserves character base HP/ATK/DEF, ascension bonus separately, weapon base ATK/secondary stat, optional artifact summary, and warnings. Direct always-on display-stat artifact/weapon effects are structured separately in SQLite for TeamBuilder display rows; formula effects, conditional bonuses, talents, constellations, and resonances remain excluded.
- HoYoLAB account detail stat sheet is the preferred source for account base/reference extraction when available, not the final TeamBuilder virtual-build result. Source-field map: `docs/handoff/ACCOUNT_CHARACTER_DETAIL_FIELDS.md`; normalized SQLite storage map: `docs/handoff/ACCOUNT_SQLITE_STORAGE.md`. Useful fields live at `account_character_details.json -> json.data.list[]`: `base_properties`, `extra_properties`, `element_properties`, `selected_properties`, `weapon.main_property`, `weapon.sub_property`, `weapon.desc`, `weapon.promote_level`, and `skills[]`. Property rows use `property_type/base/add/final`; preserve `property_type` as the stable key. Character ascension/promote phase is not required as a raw HoYoLAB field because account sync matches the correct HoYoWiki row by factual HoYoLAB base HP, then DEF, then derived character ATK. Weapon `promote_level` exists. HoYoLAB `final` rows describe current in-game equipment and must not be rendered as selected-build final stats when TeamBuilder has a virtual build selected.
- HoYoWiki character stats catalog remains useful for ascension bonus extraction, Traveler/reference/fallback data, and possible future guide/recommendation parsing. It should not be the primary right-panel current stat source when the HoYoLAB stat sheet exists. For account runtime ascension bonuses, use `extract_character_ascension_bonus_by_base_stats(...)` and store a bonus only when the HoYoWiki row/phase is matched by HoYoLAB base stat; do not use level-only `after ascension` guesses for account SQLite runtime data.
- Resonance trait source terms are `Moonsign` and `Hexerei`. Search and model those exact terms; do not replace them with guessed labels. Current HoYoLAB account-source fields do not contain these traits, so `Moonsign`/`Hexerei` come from the static/reference trait catalog in `hoyolab_export/character_trait_catalog.py`. Raw HoYoWiki/source payloads may be cached in `data/cache/hoyowiki/character_trait_catalog.json`, but normalized trait definitions, memberships, and Hexerei tooltip sections live in SQLite (`character_trait_definitions`, `character_trait_memberships`, `character_trait_tooltip_sections`). Account sync joins owned-character tags into SQLite `character_identity` as runtime fields for filters/history/PvP/resonance calculation. Hexerei tooltip text uses en-us entry `9347` as canonical source and the content language as localized override with en-us fallback; UI/runtime reads SQLite helpers, never web/raw JSON on hover. Normal HoYoLAB import best-effort refreshes membership; targeted tooltip refresh command: `python -m hoyolab_export.character_trait_catalog --refresh-hexerei-tooltips --language ru-ru`.
- Pure account stat-sheet helper exists in `hoyolab_export/account_stat_sheet.py`: `parse_account_character_stat_sheet(...)`, `extract_account_character_base_values(...)`, and `extract_account_weapon_property_values(...)`. It is explicit-input only, preserves `property_type`, derives character base ATK as account base ATK minus weapon base ATK, and does not mutate DB/UI/network state.
- Narrow HoYoWiki ascension helpers exist in `hoyolab_export/character_ascension_bonus.py`: `extract_character_ascension_bonus_by_base_stats(...)` is the account-runtime path and selects a bonus by matching HoYoLAB base HP/DEF/derived ATK to the HoYoWiki level row; `extract_character_ascension_bonus(...)` remains legacy/reference level-policy behavior.
- Account character/weapon runtime storage now has clean local SQLite tables in the existing `data/artifacts.db`: `account_characters`, `account_character_talents`, and `account_weapon_observed_stacks`; see `docs/handoff/ACCOUNT_SQLITE_STORAGE.md`. Normal HoYoLAB import (`python -m hoyolab_export.run_import`) syncs these tables automatically after raw/source cache files and crop manifest are written. Raw/source cache files remain `data/hoyolab/account_characters.json`, `data/hoyolab/account_weapons.json`, and `data/hoyolab/account_character_details.json`, but normal UI/runtime account loading should use SQLite read adapters, not raw JSON. Adapter/manual debug CLI: `hoyolab_export/account_storage.py`, command `python -m hoyolab_export.account_storage` (`--download-side-icons` optionally caches already-known side icon URLs for manual resync). Read adapter functions: `list_account_characters`, `get_account_character`, `list_account_character_talents`, `list_account_weapon_observed_stacks`, `get_account_weapon_observed_stack`, and `get_account_weapon_observed_stack_by_id`. UI asset helpers in `ui/character_assets.py` convert account SQLite records into legacy grid asset items. Character rows upsert by authoritative HoYoLAB `character_id`, side icon paths are deterministic local cache refs when present/downloaded by normal import or explicit manual cache, cached side icon files are reused, side icon failures are non-fatal, talents upsert by `(character_id, skill_id)`, and empty/broken character/detail sources do not wipe character/talent rows.
- Weapon storage is reconstructed observed stacks, not full inventory and not current-equipped canonical refs. HoYoLAB weapon id is a type id, not a unique account weapon instance id; exact observed weapon identity uses normalized `weapon_fingerprint` over weapon id, rarity, level, refinement, promote level, base ATK, secondary stat type/value. Identical fingerprints dedupe and update non-decreasing `known_count`; later smaller/zero observations never delete or decrease stacks. Normal weapon asset grids intentionally hide 1-2 star observed stacks by the same `IGNORED_WEAPON_RARITIES` / `weaponIgnored` rule used by `crop_manifest`; those stacks remain stored but are not expected to have visible `weaponAssets`. Do not revive the interrupted `account_weapons` / `account_current_equipped_weapons` / `get_current_equipped_weapon_for_character(...)` current-ref model as canonical storage.
- Runtime account visual rules: dummy/mannequin IDs from `crop_manifest` are explicitly filtered before portrait/side-icon fallback; weapon stack icon paths are resolved by weapon `icon` URL key / `weapon_id`, not equipped-character or source row order; weapon tooltips use display stat names such as `Energy Recharge` / `CRIT Rate`, not raw `P23` / `P20` ids.
- For future data-boundary questions, first read `docs/handoff/DATA_RUNTIME_BOUNDARIES.md`; it summarizes raw HoYoLAB source/cache, SQLite account runtime state, artifact SQLite storage, visual asset/cache layers, static/reference catalogs, and explicit non-stored areas.
- Before main UI, right-panel integration, left workspace, Artifact Browser embedding, history, or PvP layout work, read `docs/handoff/APP_SHELL_WORKSPACE_PLAN.md`. The target is a new AppShell with a left workspace host and reduced fixed-width right operations dock, not the legacy `ui/main_window.py` right column patched in place. Separate prototype launch command: `python -m ui.app_shell_smoke`; `main.py` still launches the legacy app until the user approves switching it. The AppShell Character/Weapon workspace uses overlay scrollbars for its icon grids and has typed `TeamBuilderState` wiring: roster character clicks are a sequential quick-pick per right-panel mode, selected roster portraits get team-colored slot markers, selected-character weapon type auto-filters the weapon grid until selection is cleared/switched, repeated selected right-panel slot click clears target selection, and weapon clicks assign only to a selected compatible character slot. The `Artifacts` left workspace lazy-embeds `ArtifactBrowserWindow(embedded=True)` and reflects the right-panel selected character as the browser operation target through target-selector selection plus current-equipment preview. Manual artifact equip/unequip, preset preview/deselect, preset apply, conflict confirmation, owner side icons, current-equipment highlights, and right-panel refresh are wired through `hoyolab_export.account_equipment`. AppShell passes normalized local visible asset paths into right-panel details so slot portraits, weapon icons, and team-bonus member icons do not fall back to text when SQLite/manifest paths are relative. Weapon assignment persists through `hoyolab_export.account_equipment.equip_weapon(...)`, repeated current weapon clicks unequip through `unequip_weapon(...)`, restores through `get_equipped_weapon_for_character(...)`, respects weapon type and `known_count`, clears old weapon passive tooltip/static-effect rows before applying the new weapon context, and enriches right-panel details only from the current weapon's SQLite `weapon_passive_tooltips` / `weapon_display_stat_effects`. Current equipped artifacts are read from `account_character_equipped_artifacts`, converted into a runtime-only current-equipment artifact snapshot, and shown in right-panel artifact stats/set bonuses without creating `artifact_builds` rows. `AppShellController` keeps independent in-memory team selections for Abyss and DPS Dummy, but equipment is per character and SQLite-backed, not per-mode session memory. Removing a character from a team slot does not unequip persistent equipment. Do not migrate smoke-only right-panel builders into production, and do not revive legacy history/right-panel layout as the target design.
- AppShell `RightOperationsDock` owns a persistent header above its content stack. The header is one visually continuous row of same-style tab buttons with ordinary spacing only: page-specific controls such as Abyss / DPS Dummy, followed by global actions such as Account. The zones are architectural, not visually separated. Global actions remain present when future right-dock modes replace their page-specific controls. Account opens the compact localized Account/Data page inside the same dock and does not switch the left workspace. `LeftWorkspaceHost` owns left pages and lazy construction, but left-nav clicks request stable workspace ids through root `AppShell`; AppShell is the coordination point for future workspace-driven right-dock policies. Run-mode and workspace routing use stable ids, never localized display text. Character/Weapon workspace mutation clicks are routed by root AppShell and are allowed only while the dock RUN page is active; Account/Data is not a team-building operation page. When switching from a non-RUN page to a run mode, update controller state and the right-panel model before exposing the RUN page so a stale previous-mode frame cannot paint. Future empty-database startup should auto-open Account/Data setup; future Support/Donate may add a compact nearby action but is not implemented yet.
- Future startup preload/cache smoothing is documented in `docs/handoff/APP_SHELL_WORKSPACE_PLAN.md` and `TODO.md`. It may prewarm heavy workspaces/widgets and pixmap/text/marquee caches behind a startup loader later, but it must not replace fixing current layout or synchronous rebuild bugs.
- AppShell resize twitch is considered system/environment live-resize behavior for now: an isolated PySide probe reproduced it outside the app, and it is reduced on a 144Hz monitor without desktop holes. No active app-level workaround is planned.
- Persistent equipment Stage A/B/C is implemented in `hoyolab_export/account_equipment.py` and initialized through `hoyolab_export.artifact_db.init_db`: canonical `account_character_equipped_artifacts` references `artifacts.id` with one artifact owner max, canonical `account_character_equipped_weapons` references `account_weapon_observed_stacks.weapon_fingerprint` and validates assignments against `known_count`. No fake weapon instance ids are created. Existing `artifact_equipment` and weapon observed `equipped_character_id` metadata remain HoYoLAB provenance/seed inputs, not a second canonical state. AppShell uses this state for weapon restore/assignment/unequip, current artifact snapshots, and Artifact Browser artifact equip/apply.
- Persistent account equipment design and implemented behavior are documented in `docs/handoff/ACCOUNT_EQUIPMENT_STATE_DESIGN.md` and `docs/handoff/ARTIFACT_BROWSER_EQUIPMENT_UX.md`. Build presets remain reusable definitions; the explicit apply-preset action copies a preset into exactly one character's current equipped state, incomplete presets clear missing target slots, and later manual equipment edits do not mutate the preset. HoYoLAB observation helpers exist but are not wired to live import; missing HoYoLAB equipment data means "no data", not "clear local equipment". AppShell restores current weapons and current artifacts from SQLite; artifact ids are converted into a runtime current-equipment snapshot for selected-details stats/set bonuses, not persisted as a fake saved build.
- AppShell performance status: use `GTT_PERF_LOG=1` or `python -m ui.app_shell_smoke --perf-log` for timing logs. The quick-pick marker bottleneck is fixed with a visible `character_id -> AssetIconLabel` registry and marker-only `set_selection_marker(...)` updates. Roster clicks update markers immediately and schedule debounced/coalesced hydration, weapon-filter sync, and right-panel refresh. AppShell filters use session-cached character/weapon asset lists; roster/weapon card pixmaps use shared high-DPI scaled pixmap caches. Right-panel team/slot widgets and selected details update in place. Follow-up high-DPI click polish keeps slot selected-state changes from reloading portrait/weapon PNGs, caches the final composited `_fit_pixmap(...)` canvas per DPR/source, and avoids the old duplicate `AssetIconLabel` startup pixmap update. Remaining work: filter grid reloads still recreate visible card widgets, and bonus-strip chip rebuilds can still cost a visible first hydrated switch on high-DPI screens.
- Real no-network smoke runner: `python -m hoyolab_export.character_stat_snapshot_smoke --limit 2`. It reads only allowlisted account JSON and local stats caches, then builds sanitized examples from `account_character_details.json` wiki links. Real smoke succeeded for ordinary matched-ready characters; current level-70 examples select character `after` values with `character_ascension_phase_assumed`, Traveler remains skipped/special_deferred, artifact summary is still missing, and final totals are still not computed.
- Artifact-only build snapshot foundation exists in `hoyolab_export/artifact_build_snapshot.py`. It converts explicit already-loaded build summary/preset data into `ArtifactBuildSnapshot` and can be passed into `CharacterStatSnapshot`; neither layer queries Artifact Browser DB/UI. Existing raw build summary shape comes from `hoyolab_export.artifact_db.calculate_raw_build_summary(...)`: `artifact_ids_by_pos`, `missing_positions`, `set_counts`, `total_stats`, `crit_value`, and `proc_count`; build preset rows add provenance/slot details such as `id`, `name`, `slots[].artifact_id`, `set_uid`, main stat fields, rarity, and level. Build id/name are provenance only, not immutable history by themselves. Direct static artifact set/weapon passive display effects may be loaded from SQLite effect tables by the TeamCard adapter; conditional bonuses, derived formulas, resonances, talents, constellations, and final combat totals are still not applied.
- Real Artifact Browser build snapshot smoke exists: `python -m hoyolab_export.artifact_build_snapshot_smoke --build-name test111` or `--build-id <id>`. The smoke opens `data/artifacts.db` read-only, selects one build, calls existing raw build summary helpers, converts to `ArtifactBuildSnapshot`, and optionally passes it as explicit artifact input into the character snapshot smoke. `--build-name` is only for explicit smoke/debug convenience; final app/team-builder flows must pass `build_id` internally because names are display/provenance, not stable identity. Current `test111` smoke confirmed build id 20, four slots, missing position 5, active 2+2 set metadata, CV 95.6, proc count 12, and no DB/UI access inside `CharacterStatSnapshot`.
- TeamCard / CharacterDetails backend data adapter exists in `hoyolab_export/team_card_data.py`. `build_character_details_data(...)` accepts explicit selected account character/weapon data plus prepared `ArtifactBuildSnapshot` input. `build_character_details_data_with_build_id(...)` is the outer read-only Artifact Browser DB adapter for selected `build_id`; it loads the preset, calculates the raw build summary, converts it to `ArtifactBuildSnapshot`, and then passes only the prepared snapshot into `CharacterStatSnapshot`. `build_current_equipment_artifact_snapshot(...)` builds the same snapshot shape from persistent current equipment rows and existing artifact ids without writing preset/build tables. Build names remain display/provenance only, final UI/team-builder flows must pass build ids/records internally, final totals are not computed, and set bonus formulas, conditional bonuses, resonances, and weapon passives are not applied.
- `CharacterDetailsData` in `hoyolab_export/team_card_data.py` now carries both the existing `CharacterStatSnapshot` provenance layer and a parsed HoYoLAB `account_stat_sheet` when the raw account detail record is supplied. It also carries `ascension_bonus` from `hoyolab_export/character_ascension_bonus.py` as reference/fallback. `CharacterStatSnapshot` remains explicit-input only and does not query raw files/DB/UI.
- Real no-network `CharacterDetailsData` smoke exists: `python -m hoyolab_export.team_card_data_smoke --character-id 10000050 --weapon-id 13407 --weapon-level 70 --weapon-refinement 5 --weapon-promote-level 4 --build-id 20`. It reads SQLite account runtime storage and `data/artifacts.db` read-only, not raw account JSON. Current smoke selects Thoma, an explicit Favonius Lance observed weapon option, and build id 20 / `test111`; artifact contribution is present, GCSIM readiness stays false, and formula/passive/resonance application stays disabled.
- Minimal backend TeamBuilder slot-state model exists in `run_workspace/team_builder.py`. It stores typed selections (`SelectedCharacterRef`, `SelectedWeaponRef`, `SelectedArtifactBuildRef`) instead of legacy image paths, supports empty four-slot teams, set/clear/swap/move operations, duplicate character detection, and optional prepared `CharacterDetailsData` attachment. It is backend-only and does not replace the legacy right panel yet. Weapon allocation remains deferred; selected weapons carry a variant key and allocation warning, but no unique weapon instance ids are invented.
- Isolated read-only TeamCard prototype exists as a pure view-model in `run_workspace/team_card_view_model.py` and a small QWidget in `ui/team_card_prototype.py`. Manual visual smoke launcher: `python -m ui.team_card_prototype_smoke` for real no-network Thoma + build id 20, or `python -m ui.team_card_prototype_smoke --fake` for fake data. It consumes `TeamBuilderState` plus optional `CharacterDetailsData`, shows empty/filled four-slot teams, character/weapon/build labels, artifact summaries, statuses, and compact warnings. It is not wired into the legacy right panel and is not the final Run Workspace.
- Isolated Right Panel / TeamBuilder Prototype v6 exists as a pure view-model in `run_workspace/right_panel_prototype_view_model.py`, display stat helper in `run_workspace/display_stats.py`, and a QWidget prototype in `ui/right_panel_prototype.py`. Manual smoke launcher: `python -m ui.right_panel_prototype_smoke` with fake data by default, or `python -m ui.right_panel_prototype_smoke --real-thoma` for the existing no-network Thoma + build id 20 sample plus deterministic Hexerei/Moonsign validation teams when local account data is available; `--team-preset moonsign|hexerei|resonance-sanity` and `--summary` provide no-GUI team bonus sanity checks. The no-preset sandbox loader now uses SQLite account runtime records and observed weapon stacks, not raw account detail JSON. It keeps the v4/v5 layout direction, enforces a minimum standalone content width, uses square character portraits with aligned weapon/build boxes, labels chamber factual/sim columns as DPS, and shows selected-character virtual build display rows from character base + selected weapon + selected artifact build + ascension/baselines. The build box uses compact Artifact Browser preset-row set semantics: active set icons plus 2p/4p overlay/count, with `Equip`/`ART` placeholders for no-preset slots. The slot main-stat badge is derived from the selected `ArtifactBuildSnapshot` slot data, specifically actual sands/goblet main stats, and must not come from target recommendations, character element, HoYoLAB current-final stats, or display-stat row order. Selected weapon meta includes weapon base ATK and secondary stat from selected SQLite observed weapon stack/account runtime data. The selected-details bottom area is now a bonus source strip for modeled external bonuses, with source chips/tooltips for direct static artifact set effects, direct static weapon passive effects, elemental resonance, `Moonsign`, and `Hexerei`; the `Apply external bonuses` toggle excludes external stat rows such as artifact/weapon static effects and elemental resonance, not base stats, selected weapon base/secondary, or artifact main/sub totals. Bonus source chips use `[large source icon] [separate compact effect badge(s)]`, and tooltips are formatted once with title, one `Effects:` section, and one source/note/breakdown body. `Moonsign` is a capped Lunar Reaction DMG indicator shown for teams with at least 2 `moonsign` characters; it reads team member stats after direct external stat bonuses when the toggle is on, requires a non-`moonsign` trigger teammate for a nonzero value, and does not add back into normal stat rows. Bonus strip source icons use cached alpha-trim scaling; compact Hexerei/member side icons use a separate cached bottom-aligned side-icon renderer so hats/hair can clip upward instead of shrinking the whole character. `Hexerei` is shown only with 2+ Hexerei members, remains display/tooltip-only, and member tooltips resolve unlocked SQLite Hexerei sections by account constellation with localized override/en-us fallback. Real smoke selected weapons are explicit observed weapon options from SQLite, not inferred from current-equipped provenance. It is visual-only, not wired into the legacy right panel, and implements no drag/drop, equip conflict logic, history export, or GCSIM execution.
- Display stat rows are virtual TeamBuilder results in this order: HP, ATK, DEF, EM, Crit Rate, Crit DMG, ER, then damage/healing bonuses. HoYoLAB stat-sheet `final` rows are reference/debug only for TeamBuilder slots and must not be shown as selected-build final stats. HoYoWiki contribution rows are fallback/provenance only. Raw partial labels such as `Base HP`, `Weapon ATK`, `Asc ...`, `Art CR`, `WATK`, and `AER` are internal/debug provenance and should not be rendered as selected-detail final stats. Direct static artifact set and weapon passive effects come only from normalized SQLite rows (`artifact_set_display_stat_effects`, `weapon_display_stat_effects`); JSON seed/audit files are not runtime storage, and derived/conditional/talent/constellation effects are not applied.
- Next Run Workspace/UI step after visual inspection of Prototype v6: inspect real multi-character layout, no-preset states, and build-slot readability; then refine exact proportions if needed before planning the first Run Workspace / TeamBuilder shell before replacing the legacy right panel.
- Stat normalization / GCSIM stat-key mapping handoff exists at `docs/handoff/STAT_NORMALIZATION.md`; backend code exists in `hoyolab_export/stat_normalization.py`. It maps artifact `property_type` values to normalized keys/GCSIM `add stats` keys, converts percent-point values like `46.6%` to ratio values like `0.466`, keeps flat stats unchanged, treats Crit Value / Proc Count as virtual metrics, and intentionally does not compute final totals or apply passives/set bonuses/resonances.
- Weapon passive/refinement text is reference data only. Do not parse free text into formulas or auto-apply passive bonuses unless a future effect is explicitly modeled/whitelisted.
- Future source note: Russian HoYoWiki character pages may expose recommendation blocks for weapons, artifacts, and teams/allies. This may later feed right-side guide/info content, draft bot heuristics, and recommended stat/build hints; do not parse it now.
- Standard 5-star filter uses `assets/filters/standard.png` and tri-state behavior: all / only Standard 5-star / exclude Standard 5-star. Membership is stored as static trait `standard_5_star` in SQLite `character_identity`; HoYoWiki entry `2952` is source context, while the current API payload is not a clean structured character list, so membership is seeded by explicit HoYoWiki character entry ids. Traveler is intentionally included and must remain included when the dedicated Traveler model is implemented.

## Artifact Database

SQLite DB: `data/artifacts.db`.

Key tables:

- `artifact_sets`
- `artifact_set_piece_icons`
- `artifact_set_names`
- `artifact_set_bonus_descriptions`
- `artifact_set_display_stat_effects`
- `weapon_display_stat_effects`
- `weapon_passive_tooltips`
- `artifacts`
- `artifact_substats`
- `artifact_equipment`
- `artifact_tags`
- `artifact_tag_links`
- `artifact_builds`
- `artifact_build_slots`
- `artifact_build_targets`
- `artifact_import_batches`

Current artifact identity model:

- canonical artifact set identity is `set_uid`;
- canonical set catalog comes from HoYoWiki `en-us`;
- localized set names live in `artifact_set_names`;
- localized artifact set 2p/4p bonus descriptions live in `artifact_set_bonus_descriptions`;
- localized weapon passive/effect tooltip text lives in `weapon_passive_tooltips`
  by `(weapon_id, lang)`; HoYoLAB account weapon `desc` is only flavor/lore
  text and is not a combat passive;
- HoYoLAB account/API mapping lives in `artifact_sets.hoyolab_set_id`;
- Artiscan/GOOD set-key mapping lives in `artifact_sets.artiscan_set_key`;
- browser icons come from `artifact_set_piece_icons.local_path` by `(set_uid, pos)`;
- custom sets are `artifact_tags` + `artifact_tag_links`;
- build presets use `artifact_builds`, `artifact_build_slots`, and `artifact_build_targets`.
- `artifacts.fingerprint` is kept for legacy/current HoYoLAB identity behavior.
- `artifacts.content_fingerprint` is source-independent and is based on normalized artifact content:
  set_uid, position, rarity, level, main stat type/value, and sorted substat type/value pairs.
- JSON imports mark only newly inserted artifacts with `json_imported=1`, `import_source`,
  `import_format`, and `import_batch_id`; pre-existing duplicate artifacts are not relabeled.

Build preset target model:

- one preset can target Universal and/or multiple characters;
- targets are ownership/category filters, not equipment/apply state;
- selecting multiple targets in the UI means intersection: show presets whose target set contains all selected targets;
- Universal is only included when Universal itself is selected.

Artifact Browser equip-context design:

- There should be one shared Artifact Browser, not separate browser instances per slot.
- It supports account-wide browse mode and equip mode for exactly one operation target. If the right panel has a selected character, that character is the Artifact Browser operation target and initially syncs as the browser's single selected character so presets appear. If the user deselects it inside the browser, browser selection clears for preset browsing while the right-panel target remains as a secondary/background operation target for free artifact clicks. If the right panel has no target, the browser may use exactly one selected character target. With 0 or 2+ browser-selected characters, equip mode is off and free artifact clicks do not equip.
- Current equipment is separate from presets. The browser shows a top current-equipment zone over persistent current equipment, not a fake/temporary preset.
- Current/preset zone: plain current-equipment text with no dark label slab, current set bonuses and main-stat badge, no edit/delete controls, and one large apply-preset action only when a saved preset is selected. Repeated click on the selected preset deselects it and returns to current equipment.
- Clicking a preset previews/selects it only. The explicit apply-preset action copies the preset artifacts into exactly one character's current equipment through `account_equipment`. If the preset has missing slots, those target slots are cleared so the live equipment matches what the preset shows.
- Manual artifact clicks in equip mode equip the clicked artifact to the operation target through the equipment service. In preset-edit mode, artifact clicks edit/construct the preset only.
- If a preset contains artifacts currently worn by other characters, show a compact confirmation with owner side icons before applying. Accepted apply uses equipment service move/swap semantics and does not mutate the preset definition.
- Artifact owner icons, preset owner icons, and weapon owner icons are derived from persistent current equipment tables. `artifact_build_targets` remains intended/available target metadata, not current wearer metadata. Weapon owner display must use `weapon_fingerprint` + `known_count` without fake weapon instance ids. Future weapon move/swap UI must require an explicit current owner/source choice when all known copies of a fingerprint are assigned; do not silently steal exhausted assigned weapons by fingerprint.
- Embedded Artifact Browser geometry is calibrated around a compact minimum-width landing: one `GRID_SIZE.width()` artifact cell, compact Assignment minimum, target rows using `MarqueeButton` with a reserved portrait/icon zone and marquee text only in the name area, fixed preset/current-equipment panel, and JSON import/clear controls that must not force the artifact viewport wider than one grid cell. Divmod/remainder adaptive fit is implemented from these source values: extra width that is not enough for another artifact column goes to Assignment as preferred/current width, not as a propagated minimum. Do not reintroduce candidate-width search or guessed card/gap constants. Remaining polish: shift artifact grid overlay scrollbar visually right without consuming layout width.

Old per-artifact icon cache path has been removed from current code. Do not reintroduce:

- `artifact_icons`
- `icon_id`
- `artifact_icon_cache`
- `upsert_icon`
- `cache_icons`

Old DBs may still physically contain old columns/tables until a later DB cleanup.

## Artifact Browser

Current module: `ui/artifact_browser/`.

Important files:

- `window.py`: `ArtifactBrowserWindow`, layout, edit modes, custom sets, build presets, build target selector.
- `store.py`: in-memory store, grouping, sorting, custom set options.
- `queries.py`: SQLite read/write wrappers for artifacts, custom sets, build presets.
- `models.py`: `ArtifactItem`, substats, tags, computed `cv` and `proc_count`.
- `list_model.py`: Qt model for artifact ids.
- `card_delegate.py`: card renderer and shared edit-selection highlight.
- `filter_popup.py`: game/custom set popup.
- `sort_popup.py`: stat sorting popup.
- `region_popup.py`: multi-select region popup for the build target selector.
- `stat_types.py`: property ids, badges, localizable sort options.
- `json_import_actions.py`: Artiscan/GOOD JSON import and clear actions for the browser UI.

Current functional state:

- Uses `QListView + ArtifactListModel + ArtifactCardDelegate`.
- Normal QListView blue selection is disabled; cards use delegate state/highlight.
- Filters by artifact position.
- Filters by game sets and custom sets.
- Game set icons come from set-piece icon catalog.
- Artifact set 2p/4p bonus descriptions are imported from HoYoWiki list payload
  `display_field.two_set_effect` / `display_field.four_set_effect` and stored per
  `(set_uid, lang, piece_count)`.
- Shared edit-selection mode is used for custom-set and build-preset editing.
- Bottom edit bar has save/cancel only.
- Static UI strings touched so far are localized in `ru`, `en`, and `pt-br`.
- Current UI is prototype quality; do not polish QWidget rows as final design.

Custom sets:

- `queries.py` supports list/create/delete/get/replace for custom sets.
- `store.py` loads custom set options from DB, including empty custom sets.
- `filter_popup.py` custom tab has create/edit/delete with inline delete confirmation.
- Empty custom set names are rejected with localized invalid input state.
- After creating a custom set, the browser enters edit mode for it.
- Dirty custom-set edits ask before close/reload/switching.

Build presets:

- Build data layer supports create/update/delete/list/get, slot replacement, target replacement, and raw summary calculation.
- Preset panel is compact and fixed-width.
- Preset list scrolls independently; preview block stays fixed at the bottom.
- Build preview has an explicit fixed geometry: target strip, 5 artifact mini-cards, set bonus preview container, and compact stat summary. Do not confuse this preview set-bonus rendering with compact preset-row metadata rendering.
- Build preset rows show compact metadata near the name:
  - no active bonus: `NO / BONUS`;
  - single active 2p: one set icon with badge `2`;
  - 4p: one set icon with badge `4`;
  - 2+2: one diagonal composite icon with one badge `2`;
  - row icons use a trim/scale/mask/composite pipeline through `ui/utils/pixmap_utils.py`.
- Compact preset-row bonus icons use in-memory cache plus persistent PNG cache under `data/cache/ui/preset_bonus_icons/`.
- Compact preset-row set bonus icons have custom tooltips backed by stored
  `artifact_set_bonus_descriptions`; 4p shows 2p+4p rows, single 2p shows one row,
  and 2+2 diagonal composite shows two 2p rows.
- Build target preview row is a baked-pixmap horizontal scroll strip, not many child widgets:
  - target icons are not clickable and no tooltip is planned there;
  - drag-scrolls horizontally;
  - wheel-scrolls horizontally;
  - uses gradient edge hints with chevrons;
  - Universal target uses `users.svg` inside a rounded card.
- Target preview icons and final strips use in-memory cache plus persistent PNG caches under:
  - `data/cache/ui/target_preview_icons/`;
  - `data/cache/ui/target_preview_strips/`.
- Build edit mode uses the same tint/highlight/bottom save-cancel infrastructure as custom sets.
- Build preset inline rename focus is fixed: entering preset edit mode focuses the name input and selects its text, so typing/backspace works immediately without an extra click.
- Clicking an artifact while editing assigns/replaces the slot for that artifact position.
- Saved preset selection highlights selected artifacts and may move them to the front of the current artifact list.
- Build target selector is a middle column: fixed vertical filters on the left, scrollable Universal/character target list on the right.
- Build target selector region filtering is implemented as a popup opened by
  `assets/filters/Statue.png`.
- Character region data comes from HoYoWiki character list `menu_id=2` and is cached in
  `data/cache/hoyowiki/character_region_catalog.json`.
- Region/trait identity is joined into SQLite `character_identity`; read adapters expose
  `region_key`, `region_name`, `traits`, and `is_standard_5_star` for every account character when matched.
- Region and `Moonsign`/`Hexerei` filters are OR inside their own group, then AND
  with selected element/weapon/rarity filters. Standard 5-star is a tri-state
  filter using `assets/filters/standard.png`.
- Non-priority UI polish: add custom in-app tooltips for character/target filter
  buttons. Do not use system tooltips there; Artifact Browser target filter
  system tooltips are intentionally disabled until custom tooltips exist.
- Region/trait joins prefer HoYoWiki entry ids and use normalized localized names only as fallback.
- `assets/filters/Icon_Back.png` is used as the build target selector reset-all filter button.
- Editing a saved build preset temporarily switches selected targets to that preset's targets; after save/cancel, the previous target browsing selection is restored.
- Enter/Return saves and Esc cancels when a custom-set or build-preset edit mode is active.
- Main UI and Artifact Browser share character asset/filter/sort helpers via `ui/character_assets.py`.
- Artifact Browser SVG UI icons should use `ui/utils/icon_utils.py` auto-contrast helpers. Current direct `QIcon(...)` uses in the browser are for non-SVG assets such as PNG filters, portraits, and artifact set icons.
- Artifact Browser has fixed bottom-row JSON actions under the artifact list:
  - Import JSON supports multiple Artiscan/GOOD files and uses backend content-fingerprint dedupe.
  - Clear JSON deletes only `json_imported=1` artifacts from `import_source='artiscan'`,
    clears affected build preset slots, then optionally deletes affected presets.

Sorting:

- Default sort: rarity desc, level desc, effective crit value desc, set name, artifact name, id.
- Explicit Crit Value sort also uses effective crit value for circlets, including CR/CD main stat contribution.
- User sort popup supports Crit Value first, regular stat options, and Proc Count last.
- Sort and Sets popups order game/custom sets by owned piece count descending.
- Proc Count is virtual: sum of `ArtifactSubstat.times`.
- Artiscan/GOOD sample data may have no `times`; proc count is then `0`.
- If selected sort includes normal stat types, main-stat priority is applied before selected stat values.
- For circlets, when Crit Value is the first sort key, neither CR nor CD is explicitly selected,
  and another normal stat follows, CR/CD main-stat circlets are sorted by total effective CV
  before the later normal-stat tie-break.

Known near-term Artifact Browser work:

- Do not wire Artifact Browser into the current legacy right panel as a disconnected button.
- Before main integration, design/implement the shared Run Workspace and team snapshot path.
- Pre-release visual pass: round/crop normal character preview portraits only after all
  card-like windows and slots are present, so the final card treatment is consistent.

## Main UI Architecture Direction

The current main-window right panel is legacy/prototype UI. Do not keep polishing it as the final structure. Replace it with a shared Run Workspace concept.

Important direction:

- Useful legacy behavior may be extracted into helpers/modules when it still fits the new model, for example wheel-based timer editing.
- Separate Account/Inventory, Team Builder, Scenario/Run, and Presentation/Export concerns.
- Run Workspace should have at least Abyss and DPS Dummy modes. The active mode controls team layout, visible inputs, history target, and saved run type.
- TeamCard and RunCard concepts should be shared by main Run Workspace, Abyss history, DPS Dummy history, export, simulator UI, and most PvP post-draft flows.
- History / saved runs should use Akasha-like compact rows later: DPS Dummy can be one team row; Abyss can be a paired/double team row. Rows can show character icons, weapon icons, set/build icons, room times, factual DPS, and sim DPS. Character hover should show a rich build tooltip; row expansion should show full RunCard/export-ready detail.
- Saved runs must be immutable structured snapshots, not live references to current account/build state and not image-only records.
- Run snapshots should preserve characters, weapons, constellations/refinements when available, artifacts, active set bonuses, relevant stats, timers, and run metadata.
- Artifact Browser integration should feed artifact builds/build presets into Team Builder and TeamCard. When saving a run, snapshot actual selected build data, not only a live preset id.
- Use "DPS" or "factual DPS" for HP/time results and reserve "sim DPS" for simulator output.
- GCSIM and PvP are architecture drivers, not immediate code tasks. Keep interfaces flexible enough for simulator results, tournament rulesets, draft flows, and PvP result export later. Detailed GCSIM research is in `docs/handoff/GCSIM.md`; read it before implementing engine download, runner, config generation, or result parsing.
- Before coding new History or GCSIM, read `docs/handoff/RUN_WORKSPACE_SNAPSHOT_CONTRACT.md`. The next Run Workspace stage is typed run/session state plus immutable Abyss/DPS Dummy snapshots; right-panel widgets display/command that state but must not own timer persistence or saved-run data. Factual DPS is app-owned HP/time math in run/session result code, while GCSIM output is separate `sim DPS`.
- GCSIM should not be crammed into the small TeamCard. The right panel should show only compact factual/sim DPS summary and a readable GCSIM button/status; detailed GCSIM/rotation editing should open as a larger overlay/drawer around the right panel area. If GCSIM lacks a character/reaction implementation, show a clear unavailable status.
- Abyss enemy data audit exists at `docs/handoff/ABYSS_ENEMY_DATA.md`; the original prompt is `docs/handoff/ABYSS_ENEMY_DATA_AUDIT_TASK.md`.
- Audit result: no single reliable source currently provides current Abyss lineup + monster ids + waves/positions + ready HP totals + resists. MVP should use a resilient source join: current period/lineup/wave notes from Fandom, source-like monster ids/stats/icons/resists from AnimeGameData/GCSIM/Yatta/Ambr where available, and Fandom enemy/level-scaling pages as fallback/cross-check for floor HP multipliers, enemy HP tables, Abyss-specific resist states, and mechanics notes.
- Factual Abyss DPS should use confidence states. Prefer source-like/period-specific HP multipliers; if those are missing but enemy ids/counts/levels/base HP are matched, a Fandom general floor-multiplier estimate may be shown with an explicit `estimated_from_floor_multiplier` warning. If core inputs are missing/ambiguous, produce no-data/warning states instead of guessed DPS.
- Near the end of right-panel development, surface factual Abyss DPS source/confidence near the DPS value, for example `source_like_period_multiplier`, `fandom_period_note`, `fandom_floor_scaling_estimate`, or `unavailable`. Do not present weak/estimated enemy HP DPS as exact; detailed source research lives in `docs/handoff/ABYSS_ENEMY_DATA.md`.
- Concrete current Floor 12 HP fixture exists at `docs/handoff/ABYSS_HP_FIXTURE.md`. It maps the `2026-05-16` Fandom lineup to monster ids/base HP/curves/resists, includes generic `2.5x` and likely current `3.75x` Stage12 totals, and records parser risks such as variant ids, Yatta freshness gaps, Fandom-vs-AnimeGameData level offsets, and state-specific enemy RES/mechanics.
- Abyss mechanics audit exists at `docs/handoff/ABYSS_MECHANICS_NOTES.md`. It uses the current Floor 12 fixture enemy list and records parser tags/warnings for shields, wards, invulnerability, state-specific RES, paralyze/downed windows, true damage HP events, summons/adds, elemental/reaction requirements, and mode-specific stat blocks.
- Backend Abyss fixture/report code exists in `hoyolab_export/abyss_sources.py` and `hoyolab_export/abyss_fixture_report.py`. Command: `python -m hoyolab_export.abyss_fixture_report --period-url https://genshin-impact.fandom.com/wiki/Spiral_Abyss/Floors/2026-05-16`. It parses Fandom period wikitext, joins confirmed current Floor 12 aliases from `docs/handoff/ABYSS_HP_FIXTURE.md`, and emits HP confidence flags such as `source_like_period_multiplier`, `fandom_floor_scaling_estimate`, and `unavailable`.
- Backend Abyss mechanics parser/report code exists in `hoyolab_export/abyss_mechanics.py`. It parses Fandom enemy-page wikitext snippets into structured fields and UI-warning/bot tags without mixing Normal/Abyss/Local Legend/Stygian stat blocks into one "true" block. Next Abyss work should integrate factual DPS confidence and mechanics warnings into the Run Workspace UI.

PvP / tournament analytics is a future local-first feature, not immediate MVP. It should collect in-app match/game statistics for characters and weapons: winrate, banrate, pick/draft frequency, deck inclusion, account ownership, and useful constellation-tier breakdowns. Treat constellation ownership as cumulative/inclusive upward, with an overall character row and expandable constellation details. Weapon analytics can track winrate, usage/pickrate when owned, and deck inclusion; ignore ascension/refinement tiers initially unless later needed. Use this for draft bots, tournament balancing, tierlist-like analysis, custom rulesets, and artifact/account-strength analysis. Any global/shared analytics must be opt-in later with privacy/anonymization work; do not imply telemetry now.

PvP ruleset audit exists at `docs/handoff/PVP_RULESETS_AUDIT.md`. Gentor is a structured public JSON source (`https://gentor.com.br/planilha` and `/planilha/{id}`) with character C0-C6 costs, weapon R1-R5 costs, character-specific weapon overrides, tiers/restrictions, draft config, and optional TypeScript draft script. Backend `TournamentRulesetV1` and validation report code exist in `hoyolab_export/tournament_ruleset.py` and `hoyolab_export/tournament_ruleset_report.py`; command: `python -m hoyolab_export.tournament_ruleset_report --ruleset-json samples/rulesets/minimal_ruleset.json`. MVP supports normalized JSON/simple CSV and reports duplicate/missing/unknown/unsupported rules. Do not execute third-party TypeScript scripts. XLSX import and Gentor API/site adapter are future work.

## Artiscan Notes

Sample files live under `samples/artiscan/`.

Observed GOOD shape:

- format: GOOD
- source: Artiscan
- artifacts list includes `rarity`, `level`, `mainStatKey`, `slotKey`, `setKey`, `substats`, `location`, `lock`
- substats include `key` and `value`
- no roll/proc `times` data observed

Do not build Artiscan assumptions from image matching. Use structured GOOD fields.

Current Artiscan state:

- Backend parser/import helper exists for Artiscan/GOOD JSON.
- Artiscan main stat numeric values use deterministic max main-stat values by rarity/stat key.
- `location` and `lock` are ignored in the MVP.
- Exact content twins may collapse into one artifact through `content_fingerprint`.
- First-day/future improvement: automatic proc counting for imported artifacts.

## Main UI State

Main window current behavior:

- Dynamic HoYoLAB button:
  - no auth: authorize / choose profile;
  - auth + no local data: import from HoYoLAB;
  - auth + local data: update HoYoLAB data.
- Button runs `python -m hoyolab_export.run_import` through `QProcess`.
- `HoYoLABLoadingDialog` consumes `[STATUS] ...` lines.
- On success, UI refreshes grids without a success popup.
- Import button has cooldown so Chrome/profile cleanup can settle.
- Character/weapon grids read account runtime records from SQLite via `ui/character_assets.py`.
- Grids use `account_characters` / `account_weapon_observed_stacks` for tooltips, filters, sort fields, image paths, and observed weapon stack counts; `crop_manifest.json` remains import/sync source-cache input.
- Character grid sort is rarity desc, level desc, name, filename.
- Filters are compact icon rows, multi-select OR inside a group and AND between groups.
- Filtered grids remain left-aligned with fixed icon spacing.
- `Profile...` menu has save profile, load profile, sign out.
- Sign-out is the destructive account boundary and can also clear artifact DB.

## Offline Profile

Offline profile export/import:

- ZIP based.
- Includes allowlisted current JSON/assets/artifact DB only.
- Excludes HoYoLAB browser profile, cookies, sessions, debug, downloads.
- Uses SQLite backup snapshot for `data/artifacts.db`.
- Writes local export-state marker so sign-out can warn if current data may not be saved.

Known TODO:

- When improving offline profile export/import, include `data/hoyolab/account_language.json` alongside:
  - `account_character_details.json`
  - `account_characters.json`
  - `account_weapons.json`
  - `crop_manifest.json`

## Localization

Localization is JSON-backed, not Qt `.ts/.qm`.

Files:

- `localization/i18n.py`
- `localization/locales/ru.json`
- `localization/locales/en.json`
- `localization/locales/pt-br.json`

Rules:

- UI code should use `tr("key")`.
- Default UI language is `ru`.
- Supported UI languages: `ru`, `en`, `pt-br`.
- Selected language and small UI preferences are stored in local ignored
  `settings.json`. Current extra preference: Abyss Fact DPS multi-target HP mode
  (`abyss_fact_dps_multi_target_enabled`), default false/solo-target.
- `GTT_LANGUAGE` or `GTT_LANG` can override UI language for a process.
- Character/weapon/artifact dynamic names from HoYoLAB should keep the HoYoLAB content language.
- Keep `pt-br.json` in sync when adding keys.

## Security / Privacy

Never save or commit:

- cookies;
- auth tokens;
- raw request headers;
- raw network dumps outside explicit ignored debug folders;
- browser profile data.

Normal clean outputs may contain:

- ids and display names;
- levels, rarity, refinements, constellations;
- icons and local crop files;
- artifact DB rows.

Debug files are private and ignored.

## Future Direction

History:

- Current history window exists.
- Future history should support Abyss and Stygian Onslaught tabs.
- Future records should include team composition and timer data by version/cycle.

Artifact Browser final UI:

- Final visual style should be Genshin-like.
- Use delegates/theme/assets rather than QWidget rows when polishing.
- Keep `store`, `queries`, and models independent from visual skin.
- Do final UI/performance refactor only after functionality is stable.

Legacy note:

- Do not revive legacy mask-based image detection unless explicitly asked.
- Preferred HoYoLAB extraction path is DOM/layout/coordinate based.

Far-future inspiration / non-MVP:

- Optional custom character icons/profile-like cosmetics could be explored later, with Akasha-like profile customization as broad inspiration.
- An optional tiny local AI companion could help with UI, comment on builds/runs, and lightly praise/tease the user, but only if it can run on weak PCs and stays optional.
- Investigate whether GitHub distribution can support paid feature unlocks; otherwise research a separate paid executable, overlay, or license mechanism compatible with the free app. This must not affect MVP architecture.
