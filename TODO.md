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
- Before implementing a task specification, briefly inspect the relevant current code and handoff contract. Clarify only ambiguities that materially change architecture, behavior, or visible UI; use engineering judgment for narrow local implementation details after the contract is clear.
- In this repo, handoff context means `CODEX.md`, `TODO.md`, and `docs/handoff/*.md`. When the user asks to update or clean handoffs, include all three entrypoints unless they narrow the scope.
- After each completed task, update handoff docs before final response when the task changes roadmap, state, or reusable context: mark completed subitems compactly, add durable new knowledge to `CODEX.md`/`TODO.md` or a dedicated handoff file, and remove stale active-task/development-log leftovers.
- After each completed pushable task, final responses should include one short
  Russian commit-message suggestion in impersonal passive/resultative wording,
  not first-person past wording. Prefer a style equivalent to "has been
  added/fixed/updated" or "added/fixed/updated as a completed result", not a
  style equivalent to "I added/fixed/updated".
- Future test-suite cleanup: split broad AppShell/right-panel checks into
  narrower runnable groups so feature tasks can run only the tests covering the
  touched subsystem, while preserving a cheap full-smoke option.
- When adding/changing persistent structures, source/cache formats, domain models, raw payload discoveries, UI prototype contracts, or long-lived research, update the relevant project map in `docs/handoff/` and keep root docs as concise entrypoint pointers.
- Obsidian map maintenance: The Obsidian vault is stored in `docs/obsidian/GTT/`. `docs/obsidian/GTT/GenshinTeamsTracker.canvas` is the human project navigation map. `docs/obsidian/GTT/DataFlow.canvas` is the human data-flow map. `docs/obsidian/GTT/SourceBoundaries.canvas` is the human source/runtime boundary map for avoiding data-owner confusion. These maps do not replace `CODEX.md`/`TODO.md` or detailed handoff files. After meaningful structural changes, update the maps together with handoff files when the change affects human understanding of the project layout: new major subsystem, renamed/moved important folder, changed data flow, changed current priority, changed architecture direction, or an important feature moving from planned to active/done. Do not update maps for tiny bugfixes, one-line styling changes, or internal refactors that do not affect the project map.

## Current Artifact Browser State

- Artifact Browser is stable enough to stop treating it as a pure prototype. It is embedded as an AppShell left workspace; current-equipment preview, manual artifact equip/unequip, preset apply, selected-card highlights, and owner side icons are wired through persistent current-equipment state.
- Future equipment UX task: persist the last applied build-preset marker per character so the current-equipment zone can show `{preset}: {character}` after app restart and after switching characters, until that character's artifact equipment actually changes. Current implementation only has an in-memory `ArtifactBrowserWindow.applied_current_equipment_label`.
- AppShell uses the embedded Artifact Browser footprint as a global top-level minimum, not the current page/current target `minimumSizeHint()`. Keep the minimum state-independent so Characters/Weapons and Artifacts cannot shrink below the fixed current-equipment/build-preview area.
- Completed manual smoke passes: Build Target Selector, target persistence, build/target preview, JSON import/clear, build preset lifecycle, and custom sets.
- Compact preset rows show set-bonus metadata, sands/goblet main-stat badge, and cached set-bonus icons.
- Build preset inline rename focus is fixed: entering edit mode focuses the name field and selects text so typing/backspace works immediately without an extra click.
- Build target preview strip is a baked pixmap strip with persistent caches; it is not many child widgets and intentionally has no tooltips.
- Build preview set bonus cells and compact preset-row set bonus icons use stored 2p/4p set bonus descriptions and custom tooltips.
- Region filters are implemented through `assets/filters/Statue.png`; character regions come from HoYoWiki character list `menu_id=2`, are cached at `data/cache/hoyowiki/character_region_catalog.json`, and are joined into SQLite `character_identity` for runtime filters.
- Region/trait filters are multi-select: OR inside their own group, AND with element/weapon/rarity. Standard 5-star is tri-state: all / only Standard 5-star / exclude Standard 5-star.
- Artifact Browser has fixed bottom-row `Import JSON` / `Clear JSON` buttons; JSON clear deletes only `json_imported=1` + `import_source='artiscan'` artifacts and clears affected build preset slots.
- Sort and Sets popups toggle closed on repeated button click and order game/custom sets by owned piece count descending.
- Region/trait joins prefer HoYoWiki entry ids when available and use normalized names only as fallback.

## 1. Pre-Integration Architecture

- New target main app shell is documented in `docs/handoff/APP_SHELL_WORKSPACE_PLAN.md`: `[LeftWorkspaceHost] [RightOperationsDock]`. Treat `ui/main_window.py` as legacy once the new shell begins; do not patch the old right column as the final architecture.
- Future AppShell tasks:
  - continue the separate `AppShell` prototype launched by `python -m ui.app_shell_smoke`; `main.py` still launches legacy `ui.main_window.App`. Do not switch the production entrypoint yet: the new chamber/action area is still display-only, typed run/session save-reset-history behavior is not wired, and the approved future `main.py` switch must run startup adaptive scaling before constructing `QApplication`;
  - keep the reduced fixed-width right operations dock around `RightPanelPrototypeWidget`; it must not be user-resizable or expand with the window;
  - harden the extracted Character/Weapon workspace as the first left workspace; it already uses overlay scrollbars, typed `TeamBuilderState`, weapon type/rarity filters, selected-character weapon type auto-filtering, sequential roster quick-pick, per-mode team selection, roster slot markers, target-based compatible weapon assignment, persistent SQLite-backed current weapon restore/assignment through `account_equipment`, normalized local icon paths for right-panel display, and SQLite-backed weapon passive/effect enrichment for right-panel tooltips/bonus chips;
  - AppShell left workspace navigation exists with Character/Weapon and lazy-created Artifacts workspaces. `LeftWorkspaceHost` owns pages/lazy construction, while nav clicks request stable workspace ids through root `AppShell`; keep future workspace-driven right-dock policies at that root coordination boundary;
  - continue the production adapter: next production-switch work starts with current in-memory run/session behavior for the right dock (reset, elapsed-time and factual-DPS results) without reviving legacy widget ownership. AppShell already has live in-memory Abyss T1/T2 timer editing in the compact chamber table, with elapsed seconds and Total derived from controller timer state; the compact editor uses separate minute/second segments inside one visual `MM:SS` field, with commit-time normalization and segment-aware wheel/arrow stepping; T2 follows T1 until manually edited, and if T1 drops below T2 then T2 clamps to T1 and returns to follow mode. Immutable saved snapshots, snapshot persistence, and History opening come later, after working timer/DPS/GCSIM result data exists. Richer `CharacterDetailsData` preparation can continue incrementally where the selected-details UI still needs it;
  - keep roster clicks as quick-pick add/remove and right-panel slot clicks as selected build/details target toggle;
  - AppShell quick-pick marker latency is fixed with incremental visible-card marker updates; roster clicks now update markers immediately and defer/coalesce right-panel refreshes through a short scheduler;
  - AppShell filters now use session-cached character/weapon asset lists plus shared high-DPI roster/weapon pixmap caching. Right-panel slot selection does not reload portrait/weapon PNGs, fitted right-panel PNG canvases are cached per DPR/source, and `AssetIconLabel` no longer does a duplicate queued pixmap update after construction. Remaining performance work is to avoid recreating visible card widgets on filter changes, likely with hide/show or a virtualized/lazy grid if profiling still warrants it, and to reduce first bonus-strip chip rebuild cost on high-DPI screens;
  - AppShell/current prototype PNG rendering is now high-DPI aware through `ui/utils/hidpi_pixmap.py`: visible raster assets keep logical UI size, render at `logical_size * devicePixelRatio`, clamp startup downscale below 1.0 back to 1.0 for image rendering, and refresh on screen/DPR changes where converted. New AppShell/current UI PNG paths should use that helper; legacy `main.py`/old widgets remain future migration unless explicitly included later;
  - reusable vector toggle switch exists at `ui/utils/toggle_switch.py`, with a
    manual visual probe at `tools/experiments/toggle_switch_probe.py`. It is not
    wired into production yet; future boolean settings such as Abyss
    multi-target HP mode and Artifact Browser ON/OFF controls should use this
    shared widget instead of text-only ON/OFF buttons;
  - right-panel add/select/remove smoothness is now stable enough for manual UX: quick-pick uses fast UI state plus deferred hydration, team/slot widgets update in place, selected details use a stable skeleton/persistent bonus strip and keep selected-height reserve when empty, add-character cancels stale pending right-panel refreshes and no longer performs a visible intermediate minimal-details refresh before hydration, and right-panel repaint is deferred until the next event-loop tick when layout geometry has settled;
  - Artifact Browser target-character filters now use stable in-layout target buttons with in-place visibility/state updates, so standard/all target filtering no longer rebuilds 65-73 buttons on every click. Do not reintroduce QWidget cache approaches that remove/re-add target buttons through layouts; keep buttons parented in one stable layout and update via visibility/state/content;
  - Artifact Browser cold-start is audited/optimized enough for the future loader pass: embedded size policy no longer forces AppShell resize on first open, target character assets reuse the already-loaded Character/Weapon workspace session cache instead of a second SQLite pass, and remaining cold work is mostly SQLite store load plus one-time creation of target buttons;
  - startup loader + persistent cache/bake work is a later pre-release smoothing task. Until that loader pass, keep remaining cold-start/stutter sources visible and measurable instead of hiding them behind persistent caches too early;
  - when the loader pass starts, explicitly list all work hidden under it and bake/cache all repeatable loader-covered data together, for example Artifact Browser cold-start init/store data, target/preset UI prep, preset-edit controls, pixmap/text/marquee caches, and bulk persistent equipment/negative-cache prewarm;
  - add future drag/swap for right-panel character cards within a team and between teams after quick-pick remains stable. The model already has whole-slot swap/move support; UI drag/drop should swap full slot payloads so character, weapon, artifact details, warnings, and current build display move together while team bonuses/resonances are recalculated from the resulting team composition;
  - Artifact Browser is embedded as the `Artifacts` workspace and reflects the right-panel selected operation target through target highlight/current-equipment zone; artifact click equip/unequip, current-equipment preview, selected-card highlights, preset apply, conflict confirmation, and owner side icons are wired through current-equipment tables;
  - persistent account equipment Stage B/B2 is implemented for AppShell: adding a character restores current weapon from SQLite, weapon clicks persist through `equip_weapon(...)`, equipment is per character not per mode, slot removal does not unequip, and current equipped artifact ids are converted into a runtime live snapshot for right-panel artifact stats/set bonuses without creating fake build presets;
  - future import equipment auto-apply setting: HoYoLAB import should optionally apply observed current artifacts/weapons into the new `account_equipment` runtime tables after import. When enabled, apply through account equipment service helpers so artifacts/weapons follow the same move/swap semantics as manual equip; current import/storage paths still need an audit before wiring this behind a user-toggleable setting;
  - Artifact Browser equipment UX is documented in `docs/handoff/ARTIFACT_BROWSER_EQUIPMENT_UX.md`: right-panel selected character can drive the browser operation target, the top current-equipment zone is current equipment rather than a preset, preset apply is explicit, incomplete preset apply clears missing target slots, and owner side icons come from current equipment tables;
  - separate timer/run logic into a model/controller while keeping timer UI visually in the right operations dock;
  - RightOperationsDock now owns a persistent same-style header row with page-specific Abyss / DPS Dummy controls plus an always-visible global Account action. Account opens a compact localized Account/Data page inside the same dock without changing the left workspace. The page reuses the current HoYoLAB import/update flow, offline profile save/load/sign-out actions, and language selector; AppShell refreshes account asset caches after import and clears only its runtime team state when an offline profile is loaded or signed out. Header routing uses stable ids rather than localized text. Future PvP can replace its page-specific controls while Account stays present;
  - root AppShell now gates Character/Weapon workspace mutation clicks by the active right-dock page: roster and weapon clicks are no-op while Account/Data is open. Returning from a non-RUN page updates the requested controller mode and right-panel model before exposing RUN content, so the previous run mode cannot paint as a stale intermediate frame;
  - future first-run/onboarding flow should handle empty-account startup: when the account database is empty, guide the user by opening/highlighting the Account/Data page as part of the onboarding/tutorial sequence. Do not implement this as an isolated Account/Data auto-open task now; debug it together with the first-opening guidance flow. A compact Support/Donate header action, fuller settings area, and fuller Account-page support area remain optional future directions, not current UI;
  - keep PvP as a separate mode/window direction initially, reusing the build panel only after a buildable pool/team exists;
  - clean legacy main-window right panel and legacy history only after the new shell is stable.
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

- Detailed next-stage session/snapshot contract: `docs/handoff/RUN_WORKSPACE_SNAPSHOT_CONTRACT.md`.
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
- Before implementing History or GCSIM, create typed run/session state and immutable snapshot persistence. The right-panel widget must display/command this state; it must not be the source of truth for timers or saved runs.

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
- The current Artifact Browser can still open as its own window. AppShell also embeds it as the `Artifacts` left workspace with target/current-equipment UI.
- Preserve build presets as shared ownership categories, not "one build = one character".
- A preset can belong to Universal and/or multiple character targets; selected target filters use intersection semantics and should not auto-include Universal unless Universal is selected.
- Keep build data separate from visual skin/delegate rendering.
- Equip-context rule: keep one shared Artifact Browser with browse mode and equip mode for exactly one operation target, not one browser per TeamBuilder slot. Selecting a preset only previews it; the explicit apply-preset action performs the equipment write.
- Domain rule: current equipment is separate from build presets. A preset is a reusable definition; the live/free per-character equipment state is stored in persistent equipment tables.
- Artifact Browser target/equip-mode UX is documented in `docs/handoff/ARTIFACT_BROWSER_EQUIPMENT_UX.md`. Equip mode is active only for exactly one operation target. Right-panel selected target wins when present; it initially syncs as the browser's single selected character so presets appear, and if the user deselects it in the browser it remains only as a secondary/background operation target. Without a right-panel target, the browser may use exactly one selected character. With 0 or 2+ browser-selected characters, free artifact clicks do not equip.
- Current equipment flow status: embedded browser target selection/secondary marker, current-equipment preview, artifact equip/unequip, preset preview/deselect, preset apply, incomplete-preset clearing, conflict confirmation, owner markers, and selected-card highlights are wired through `account_equipment`.
- The current-equipment zone is a top zone above presets, not an `artifact_build` preset. Selecting a preset previews it; the explicit apply-preset action copies preset artifacts into the operation target's current equipment.
- Current/preset zone UX: current equipment is rendered as plain text on the existing panel background, with current set bonuses/main-stat badge and no edit/delete controls. When a saved preset is selected, the zone becomes one large apply-preset action. Repeated preset clicks deselect and return the preview to current equipment.
- Applying an incomplete preset clears the missing target slots so current equipment matches exactly what the preset shows. The applied preset name may be temporary UI-buffer text only and resets to the default current-equipment label after manual artifact changes.
- Manual artifact click in equip mode equips that artifact through the equipment service and does not mutate presets. In preset-edit mode, artifact clicks edit the preset only.
- If a preset contains artifacts currently worn by other characters, show a compact confirmation with character side icons only before applying. Accepted apply uses equipment service move/swap semantics.
- Current equipment set icons in the right-panel mini build box and static bonus strip must come from the same persistent artifact/set icon data used by Artifact Browser rows, not guessed paths. Text fallbacks such as `2p`, `4p`, or `2+2` are only for genuinely missing/invalid icon assets.
- Artifact owner icons, preset owner icons, and weapon owner icons come from current equipment tables, not `artifact_build_targets`. Weapon owner icons must respect `weapon_fingerprint` + `known_count` without fake weapon instance ids.
- Known visual bug: the weapon owner overlay/side icon can fail to appear on duplicate/count weapon stacks, for example two Favonius Sword 90 lvl R2/R5 copies. Weapon equips and selected weapon display can still be correct; the remaining issue is only overlay identity/count visual feedback.
- Future weapon-card visual polish: if weapon thumbnails later receive a more noticeable corner radius, keep the occupied-weapon outline radius synchronized with the thumbnail shape. The current occupied outline intentionally uses only a minimal 3px rounding.
- Later/post-release: add recommended artifact stat filters per character. Examples: Varesa should rank Electro DMG goblets higher, Ineffa should rank ATK goblets higher. This likely needs imported guide/recommendation data from external sources; do not implement it in the current equipment-flow work.
- Future weapon panel move/swap UI: when all known copies of a `weapon_fingerprint` are assigned, require an explicit current owner/source choice before moving or swapping. Do not silently steal an exhausted assigned weapon by fingerprint.

## 6. Abyss History / Seasons

- Redesign history around shared RunCard/TeamCard components. The old history grid is not final and will not scale once weapons, set bonuses, simulator values, filters, and metadata are added.
- History should become a left workspace/tab after typed immutable snapshots exist. The right dock may keep a compact History command, but browsing and filtering saved runs belongs on the left.
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

- First production Abyss source-data boundary exists in
  `run_workspace/abyss/source_data.py`. It converts Fandom-shaped composition
  reports plus optional Nanoka-shaped tower reports into typed Floor 12 source
  data with enemy rows, waves, chamber-side HP summaries, source URLs, match
  methods/confidence, and warnings. Live production-safe debug update entrypoint
  exists at `python -m run_workspace.abyss.source_data_update --period-start
  YYYY-MM-DD --floor 12`; it fetches the Fandom period page, resolves Nanoka's
  internal tower id from the Nanoka manifest by period, then fetches Nanoka
  tower detail data. `--tower-id N` remains an explicit debug override only.
  Persistent cache boundary exists in
  `run_workspace/abyss/source_data_cache.py` and stores schema-v1
  `AbyssFloorSourceData` JSON under the project-root-anchored path
  `data/cache/abyss/source_data/<period_start>/floor_<floor>.json`; the update
  CLI writes it only with `--save-cache`. Monster icon asset caching is also
  backend-only there: `--save-cache` downloads icons by default into
  `data/cache/abyss/source_data/<period_start>/floor_<floor>_assets/monster_icons/`
  using Nanoka icon URLs first and Fandom composition icon URLs as fallback,
  then stores `cached_icon_path` on rows for future tooltip UI. Icon downloads
  are bounded-parallel and reuse existing URL-hash files even during source-data
  `--force`; force refreshes source data, not identical already-cached icons.
  It does not wire UI or replace the current fixture. HP source modes are now
  explicit: `--hp-source auto` uses Nanoka as primary and Fandom enemy-page HP
  as fallback only for missing HP, `--hp-source nanoka-only` keeps the old
  no-enemy-page fallback path, and `--hp-source fandom-only` forces Fandom
  enemy-page HP for validation. Source-data refresh uses one bounded network
  worker setting (`--network-workers`, default 10) for Fandom enemy-page HP
  fallback and monster icon downloads; `--fandom-hp-workers` remains a
  compatibility alias. The fallback fetches unique enemy pages without a
  persistent enemy-page HP cache. In normal Nanoka-backed modes, Fandom
  composition and Nanoka source fetch run in parallel before join/build.
  Normal HoYoLAB import now resolves the current Spiral Abyss period with source
  priority HoYoLAB overview -> latest Fandom Spiral Abyss/Floors period page
  -> Nanoka live tower metadata, stores it at
  `data/hoyolab/spiral_abyss_period.json` with source/warning/fallback metadata,
  and best-effort refreshes this period/floor source-data cache after a
  successful import. This refresh is non-fatal; existing caches stay untouched
  on source update failure. Manual backend/debug command:
  `python -m hoyolab_export.abyss_source_refresh --write-period --update-cache`;
  it skips same-period ready cache/assets by default, has `--force` for an
  explicit refresh, has `--period-source auto|hoyolab|nanoka|fandom` for
  period diagnostics, and passes `--hp-source auto|nanoka-only|fandom-only`
  plus `--hp-multiplier` / `--network-workers` into the source-data updater.
  Local system date is not a source-data authority for this refresh
  path. Right panel Fact DPS now reads this local cache via
  `run_workspace/abyss/source_data_runtime.py`, never fetches network data from
  the right panel, and uses `solo_target_hp` as the default displayed HP mode.
  Missing period/cache/HP leaves Fact DPS unavailable instead of falling back to
  the invalid static fixture; missing cache is not permanently memoized in
  AppShell. The source-data update report now includes lightweight timing fields
  for Fandom, Nanoka, join/build, JSON cache save, and icon asset caching. The
  Account/Data HoYoLAB import button already triggers the best-effort Abyss
  source-data refresh after a successful import; same-period ready cache/assets
  are skipped by default and `--force` refreshes explicitly. Fact DPS cells now
  expose a compact cached-source-data tooltip payload and use the project's
  custom tooltip surface. The current content is compact HTML/text with enemies
  first, then calculation and source summary; native Qt/system tooltips are not
  acceptable. Account/Data now has a persistent DPS subzone toggle for
  multi-target HP mode, default off/solo-target. A richer custom tooltip card
  remains future work. Manual/debug period switcher exists at
  `tools/future/abyss_period_switch.py`: it points AppShell at an already
  cached period by rewriting only `data/hoyolab/spiral_abyss_period.json`,
  refuses missing period/floor caches, preserves a `.debug_backup.json` period
  backup by default, and never fetches or mutates source-data caches. Use it for
  temporary historical-period checks such as 2026-02-16 / tower 116; normal
  HoYoLAB import may overwrite the debug period-ref with the official current
  period.
- Useful Abyss debug commands from the project root:
  - update/cache normal Nanoka-backed source data:
    `.\.venv\Scripts\python.exe -m run_workspace.abyss.source_data_update --period-start YYYY-MM-DD --floor 12 --save-cache --hp-source auto --network-workers 10 --format text`
  - force Fandom enemy-page HP fallback for validation:
    `.\.venv\Scripts\python.exe -m run_workspace.abyss.source_data_update --period-start YYYY-MM-DD --floor 12 --save-cache --hp-source fandom-only --network-workers 10 --format text`
  - switch AppShell to an already cached period:
    `.\.venv\Scripts\python.exe tools\future\abyss_period_switch.py --period-start YYYY-MM-DD --floor 12 --format text`
  - restore the previous period ref after a debug switch:
    `.\.venv\Scripts\python.exe tools\future\abyss_period_switch.py --restore-backup --format text`
- Need future AbyssSeason / room / chamber / wave / enemy model on top of this
  source-data boundary.
- For each Abyss chamber/side, data should ideally support enemies, waves, enemy HP, total HP, resistances, immunities, special states, invulnerability/phases where available, and icons.
- Do not require this data for the app to function.
- Abyss source research is done; see `docs/handoff/ABYSS_ENEMY_DATA.md`, `docs/handoff/ABYSS_HP_FIXTURE.md`, and `docs/handoff/ABYSS_MECHANICS_NOTES.md`. Keep the source join resilient so one unavailable/stale source does not break the feature.
- Do not download a huge historical database initially. Update current Abyss info at the relevant time and create a new season/page if current Abyss data changed.
- No network / no data fallback:
  - future UI may create/use a provisional Abyss period based on the system
    date only as an offline session placeholder, not as source-data authority;
  - use the 16th day of month as the split point;
  - use a localized period label such as `16.05 - 16.06.26`;
  - show "no data" / localized equivalent where enemy data/HP is needed;
  - factual DPS from enemy HP is unavailable when HP data is missing.
- Keep in mind HP/time DPS is not exact damage dealt because waves, immunity, phases, shields, invulnerability, movement, and similar mechanics can distort it.
- Abyss enemy data audit exists at `docs/handoff/ABYSS_ENEMY_DATA.md`; the original prompt is `docs/handoff/ABYSS_ENEMY_DATA_AUDIT_TASK.md`.
- Audit result: no single reliable source currently provides current Abyss lineup + monster ids + waves/positions + ready HP totals + resists. MVP should use a resilient source join: current period/lineup/wave notes from Fandom, source-like monster ids/stats/icons/resists from AnimeGameData/GCSIM/Yatta/Ambr where available, and Fandom enemy/level-scaling pages as fallback/cross-check for floor HP multipliers, enemy HP tables, Abyss-specific resist states, and mechanics notes.
- Factual Abyss DPS should use confidence states, not a single yes/no gate. Prefer source-like/period-specific HP multipliers; if those are missing but enemy ids/counts/levels/base HP are matched, a Fandom general floor-multiplier estimate can be shown with an explicit `estimated_from_floor_multiplier` warning. If core inputs are missing/ambiguous, show enemy list/warnings and keep HP/time DPS unavailable.
- Near the end of right-panel development, surface factual Abyss DPS source/confidence near the DPS value, for example `source_like_period_multiplier`, `fandom_period_note`, `fandom_floor_scaling_estimate`, or `unavailable`. Do not present weak/estimated enemy HP DPS as exact; detailed research lives in `docs/handoff/ABYSS_ENEMY_DATA.md`.
- `docs/handoff/ABYSS_HP_FIXTURE.md`, `hoyolab_export/abyss_sources.py`, and
  `hoyolab_export/abyss_fixture_report.py` are historical audit/fixture
  references only. Normal displayed AppShell Fact DPS must use the production
  source-data cache (`run_workspace/abyss/source_data*.py`) and must not fall
  back to the old invalid/static fixture path.
- Abyss mechanics audit exists at `docs/handoff/ABYSS_MECHANICS_NOTES.md`. It
  records Fandom structured fields/prose tags for shields, wards,
  invulnerability, state RES, paralyze/downed windows, true damage HP events,
  summons/adds, elemental/reaction requirements, and mode-specific stat blocks.
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
    source chips. The prototype source item shape now covers
    `elemental_resonance`, `moonsign`, `hexerei`, `artifact_set_static`, and
    `weapon_passive_static`; future team bonuses should reuse that shape.
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
- Right Panel prototype team bonus chips now include direct display-stat elemental resonances, a `Moonsign` Lunar Reaction DMG indicator, and display-only `Hexerei`. Use the in-game/source terms `moonsign` and `hexerei` when searching code/docs/sources; do not substitute guessed terms. Elemental resonances are inferred from character elements. Implemented stat contributors are Pyro `ATK +25%`, Hydro `HP +25%`, Cryo `CR +15%`, Geo selected-character elemental DMG `+15%`, and simplified Dendro `EM +50/+80/+100`; Electro/Anemo and non-display-stat resonance effects are not modeled in stat rows. `Moonsign` uses `character_identity.traits_json`, shows a capped Lunar Reaction DMG indicator only when at least 2 team members have `moonsign`, reads team member stats after direct external stat bonuses when the external-bonus toggle is on, requires a non-`moonsign` trigger teammate for a nonzero value, and does not alter normal display stat rows. Bonus strip source chips use `[large source icon] [separate compact effect badge(s)]`, with cached alpha-trim scaling so transparent PNG padding does not shrink source icons inside chips. Compact Hexerei/member side icons use a separate cached bottom-aligned side-icon renderer rather than alpha-fit cropping. The shared bonus tooltip formatter owns the single `Effects:` section so source bodies should not duplicate effect labels. `Hexerei` appears only with 2+ Hexerei team members and is tooltip/display-only; member tooltips read normalized SQLite Hexerei sections, filter locked sections by account constellation, prefer localized content-language rows, and fall back to en-us. `ui.right_panel_prototype_smoke` supports `--team-preset moonsign|hexerei|resonance-sanity` and `--summary` for no-GUI team bonus sanity checks.
- `hoyolab_export/character_trait_catalog.py` refreshes HoYoWiki trait sources. Raw/source cache remains `data/cache/hoyowiki/character_trait_catalog.json`; normalized trait reference data lives in SQLite tables `character_trait_definitions`, `character_trait_memberships`, and `character_trait_tooltip_sections`. Account sync joins owned-character trait tags into SQLite `character_identity` as runtime fields for filters/history/PvP/resonance calculation. Targeted Hexerei tooltip refresh command: `python -m hoyolab_export.character_trait_catalog --refresh-hexerei-tooltips --language ru-ru`; it always refreshes en-us entry `9347` as canonical, then content-language override, with en-us fallback and no UI web reads.
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
- Account stat-snapshot readiness is separate from GCSIM key readiness. Local
  account counts can change with the imported account/cache; ordinary
  non-Traveler rows should remain usable for `CharacterStatSnapshot` when
  HoYoLAB base/reference data and HoYoWiki stat rows match, while Traveler stays
  special/deferred until the dedicated Traveler model exists.
- Minimal `CharacterStatSnapshot` foundation exists for ordinary matched-ready characters/weapons. It is read-only/backend-only and partial: it preserves character base HP/ATK/DEF, ascension bonus separately, weapon base ATK/secondary stat, optional artifact summary, and warnings. Direct always-on display-stat artifact/weapon effects are structured separately in SQLite for TeamBuilder display rows; formulas, conditional bonuses, resonances, talents, and constellations remain excluded. Traveler remains `special_deferred`.
- Account character source shape is documented in `docs/handoff/ACCOUNT_CHARACTER_DETAIL_FIELDS.md`: current account detail data exposes useful stat-sheet rows, weapon `promote_level`, and `skills[]` talent levels. Character ascension/promote phase is not required as a raw HoYoLAB field for the current account storage model; account sync matches the needed HoYoWiki row by factual HoYoLAB base HP, then DEF, then derived character ATK. The old HoYoWiki level-only row policy remains reference/fallback behavior only; do not use it as account runtime ascension bonus selection when HoYoLAB base stat rows are present.
- Clean account character/weapon runtime storage now exists in local SQLite `data/artifacts.db` tables `account_characters`, `account_character_talents`, and `account_weapon_observed_stacks`; see `docs/handoff/ACCOUNT_SQLITE_STORAGE.md`. The DB filename is legacy and this is a unified runtime DB, not artifact-only storage. Normal HoYoLAB import (`python -m hoyolab_export.run_import`) now syncs these tables automatically after raw/source cache files and crop manifest are written. Raw/source cache files remain `data/hoyolab/account_characters.json`, `data/hoyolab/account_weapons.json`, and `data/hoyolab/account_character_details.json`, but normal UI/runtime account loading should use SQLite read adapters, not raw JSON. Adapter/manual debug CLI: `hoyolab_export/account_storage.py`, command `python -m hoyolab_export.account_storage` (`--download-side-icons` optionally caches already-known side icon URLs for manual resync). Read adapter functions: `list_account_characters`, `get_account_character`, `list_account_character_talents`, `list_account_weapon_observed_stacks`, `get_account_weapon_observed_stack`, and `get_account_weapon_observed_stack_by_id`. UI asset helpers in `ui/character_assets.py` convert account SQLite records into legacy grid asset items. Characters upsert by authoritative HoYoLAB `character_id`; `account_characters.name` and observed weapon `name` are localized HoYoLAB display text and must not be used as English identity keys for GCSIM mapping. Account sync stores `catalog_english_name` plus resolved `gcsim_character_key` / `gcsim_weapon_key` status and method fields by joining already-local HoYoWiki stats caches with the local GCSIM shortcut registry once per sync. Ready rows can feed future `GcsimMappingRef` construction directly; missing/ambiguous/unsupported rows remain controlled not-ready. Side icon paths are deterministic local cache refs when present/downloaded by normal import or explicit manual cache; cached side icon files are reused, failures are non-fatal; talents upsert by `(character_id, skill_id)`; empty/broken character/detail sources do not wipe character/talent rows.
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
- Current-equipment artifact snapshot builder exists in `hoyolab_export/team_card_data.py`: `build_current_equipment_artifact_snapshot(...)` reads `account_character_equipped_artifacts`, reuses `calculate_raw_build_summary(..., slots=...)`, skips missing artifact rows softly with a warning, and returns a runtime-only `ArtifactBuildSnapshot` with `build_id=None`. AppShell uses it for right-panel artifact stats/set bonuses; it must not create or mutate `artifact_builds`, `artifact_build_slots`, or `artifact_build_targets`.
- Real no-network `CharacterDetailsData` smoke exists: `python -m hoyolab_export.team_card_data_smoke --character-id 10000050 --weapon-id 13407 --weapon-level 70 --weapon-refinement 5 --weapon-promote-level 4 --build-id 20`. It reads SQLite account runtime storage and `data/artifacts.db` read-only, not raw account JSON. The smoke validates selected character + explicit observed weapon option + build id -> prepared details data with artifact contribution, while still not applying passives/set/resonance formulas.
- Minimal backend TeamBuilder slot-state model exists in `run_workspace/team_builder.py`. It stores typed selections (`SelectedCharacterRef`, `SelectedWeaponRef`, `SelectedArtifactBuildRef`) instead of legacy image paths, supports set/clear/swap/move operations, detects duplicate selected characters, and can optionally carry prepared `CharacterDetailsData`. It does not replace the legacy right panel yet.
- Isolated read-only TeamCard prototype exists: pure view-model in `run_workspace/team_card_view_model.py` plus isolated QWidget prototype in `ui/team_card_prototype.py`. Manual visual smoke launcher: `python -m ui.team_card_prototype_smoke` for real no-network Thoma + build id 20, or `python -m ui.team_card_prototype_smoke --fake` for fake data. It consumes `TeamBuilderState` / optional `CharacterDetailsData`, displays four slots, empty placeholders, character/weapon/build labels, artifact summary, status, and compact warnings. It is not wired into the legacy right panel and is not the final Run Workspace UI.
- Isolated Right Panel / TeamBuilder Prototype v6 exists: pure view-model in `run_workspace/right_panel_prototype_view_model.py`, display stat helper in `run_workspace/display_stats.py`, and isolated QWidget prototype in `ui/right_panel_prototype.py`. Manual visual smoke launcher: `python -m ui.right_panel_prototype_smoke` with fake data by default, or `python -m ui.right_panel_prototype_smoke --real-thoma` for the no-network Thoma + build id 20 sample plus several local no-preset character slots. The no-preset sandbox loader now uses SQLite account runtime records and observed weapon stacks, not raw account detail JSON. It keeps the v4/v5 layout, enforces a minimum standalone content width, uses square character portraits with aligned weapon/build boxes, keeps chamber factual/sim DPS columns, and shows selected-character virtual build display rows from character base + selected weapon + selected artifact build + ascension/baselines. The build box uses compact Artifact Browser preset-row set semantics: active set icons plus 2p/4p overlay/count, with `Equip`/`ART` placeholders for no-preset slots. The lower slot main-stat badge is derived from the selected artifact build snapshot's actual sands/goblet main stats; do not source it from target recommendations, character element, HoYoLAB current-final stats, or display-stat order. Selected weapon meta includes weapon base ATK and secondary stat from selected SQLite observed weapon stack/account runtime data. The selected-details bottom area is a compact external bonus source strip, not a plain set-name line; it shows modeled artifact-set and weapon-passive static effects with numeric chips and custom tooltips. Real smoke selected weapons are explicit observed weapon options from SQLite, not inferred from current-equipped provenance. It is visual-only and not wired into the legacy right panel.
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
- Initial isolated engine lifecycle prototype exists in
  `run_workspace/gcsim/engine_store.py`; official GitHub source acquisition and
  the backend/dev update command exist in `run_workspace/gcsim/source_acquisition.py`
  and `run_workspace/gcsim/engine_update.py`. Command:
  `python -m run_workspace.gcsim.engine_update --release latest`. It downloads
  official source, applies the selected replaceable patch backend, runs a source
  layout smoke check, writes a manifest, and activates only on success. Use
  `--probe-runtime` to additionally require local Go `windows/amd64` and
  `go run ./cmd/gcsim -version`; this marks `runtime_ready=true` only when the
  probe passes and keeps the old active engine on Go/probe failure. Go cache/bin
  paths are sandboxed under ignored `.go/`; the rebuildable `.go/build-cache`
  is deleted after successful `--probe-runtime`/`--build-artifact` unless
  `--keep-go-build-cache` is passed, while `.go/pkg/mod` is kept as the small
  module cache. Generated engine-store cleanup now keeps the active engine,
  one previous successful rollback engine, and one latest failed engine; older
  generated engines/staging folders are pruned. Manual cleanup/dry-run command:
  `python -m run_workspace.gcsim.cleanup` (`--apply` to delete).
  `--patch-backend git` now applies
  ordered `.patch` stacks with `git apply --check` then `git apply`; it isolates
  patch application from the parent GTT repository so generated `data/gcsim/...`
  engine trees are patched as plain source folders. Overlay remains the
  conservative default/test backend. `--build-artifact` now builds
  `build/gtt-gcsim.exe` inside the prepared engine folder, verifies that
  executable with `-version`, records artifact path/hash/build metadata, and
  marks `runtime_ready=true` only when the built artifact works. The default git
  patch stack contains `run_workspace/gcsim/patch_stack/0001-gtt-engine-marker.patch`,
  `run_workspace/gcsim/patch_stack/0002-gtt-sequential-wave-prototype.patch`,
  and `run_workspace/gcsim/patch_stack/0003-gtt-wave-scenario-payload.patch`.
  The marker adds `-gtt-info`; the prototype patch keeps the legacy opt-in
  comment proof `# gtt_wave_prototype duplicate_first_target=1`; the payload
  patch adds explicit `-gtt-wave-scenario scenario.json` input. Payload
  schema v1 is intentionally tiny: `schema_version=1`,
  `spawn_policy="group_clear"`, and `waves[].targets[]` with required
  `level`, `type`, and explicit `hp`. The patch builds the enemy through
  GCSIM's target type/profile path so `type` owns the monster stats/resists;
  optional `pos`/`radius` are only explicit overrides, and normal Abyss bridge
  output does not write them. The first payload wave replaces parsed config
  targets; remaining waves spawn after the current group clears inside the same
  simulation iteration. Current built GTT
  artifacts should report `gtt_patch_version=gtt-wave-scenario-v1`,
  capabilities including `gtt_engine_marker`,
  `gtt_wave_scheduler_prototype`, and `gtt_wave_scenario_payload`, plus
  `sequential_waves=true`. This is still a prototype explicit-target payload,
  not final Abyss enemy/key mapping or 3+3+3 modeling. When
  `--build-artifact` is used with a non-empty `.patch` stack, `-gtt-info` is
  required; missing, nonzero, invalid, or capability-missing output keeps the
  previous active engine. Minimal active-artifact runner exists in
  `run_workspace/gcsim/artifact_runner.py`; dev smoke command:
  `python -m run_workspace.gcsim.run_smoke --config path --gtt-wave-scenario scenario.json --format text`.
  It runs the active built artifact with caller-provided config text and
  optional scenario payload, then parses only a tolerant result JSON summary.
  A narrow backend Abyss-to-GTT-wave bridge exists in
  `run_workspace/gcsim/abyss_wave_scenario.py`: it audits typed
  `AbyssFloorSourceData` chamber/side waves and can produce schema-v1
  `group_clear` payloads when per-enemy HP/level are present and each enemy can
  resolve to a compatible valid GCSIM target type. GTT writes explicit Abyss HP
  into the payload, so exact GCSIM HP/variant identity is not required at this
  stage; `Grounded Geoshroom -> groundedgeoshroom` is an acceptable success case
  when it avoids an unknown target type and keeps usable GCSIM resists.
  Nanoka monster id is the preferred strong identity when present, but it is not
  the only allowed identity: Fandom enemy page URL/page title/name candidates
  must remain valid fallback identities, and enemy-type fallback must be
  independent from HP source fallback. HP may come from Nanoka while GCSIM type
  resolves through Fandom/name identity, or HP may come from Fandom fallback while
  type resolves through Nanoka/name identity. Managed Snap Monster title cache
  support now exists in `run_workspace/gcsim/snap_monster_titles.py` as a
  last-resort enemy `Name -> Title` fallback after manual overrides, normal
  registry exact/base matching, and small aliases fail. The normal app-style
  contract is cache-first: primary matching runs without Snap; if rows remain
  unresolved, GTT may check the managed cached
  `data/cache/gcsim/snap_metadata/Monster.json`; if cached `Name -> Title`
  matching and cached title-containing-target matching are still insufficient,
  the cache may be refreshed from the official online Snap.Metadata file
  `https://github.com/wangdage12/Snap.Metadata/blob/main/Genshin/EN/Monster.json`
  and then rechecked. No Git install or Snap.Metadata repository checkout is
  required. The refresh step reads the single online `Monster.json` over HTTPS
  and persists only the managed cache file plus a small sidecar metadata file.
  A local file path or direct URL remains supported only as an explicit
  dev/offline/debug input, not as the normal app contract. Only `Name` and
  `Title` are read; Snap metadata must not be used as HP/stat/resist/wave/count
  truth or as source-data replacement. The fallback is intended for too-specific
  source names such as Arkhe suffixes and Tenebrous Mimesis forms, and duplicate
  normalized Snap `Name` records with different `Title` values are reported as
  ambiguous. If even the Snap `Title` does not exact/base-match the registry,
  the final last-resort matcher may resolve a unique GCSIM target whose key
  contains the full normalized Snap title (`snap_title_contains_target`);
  multiple containing targets remain ambiguous. This covers cases such as
  `Tenebrous Papilla: Type II -> Tenebrous Papilla -> tenebrouspapillatypei`
  without turning arbitrary display-name fuzziness into production truth.
  Missing Nanoka id alone is not a blocker; the blocker is missing any safe
  explicit or automatic compatible GCSIM target type. The bridge must not infer
  production-ready GCSIM type keys from arbitrary fuzzy/display-name similarity.
  Dev CLI `python -m run_workspace.gcsim.abyss_wave_scenario_smoke` loads current or
  explicit cached Abyss source data, writes this provisional scenario JSON, and
  can optionally pass it with an existing caller-provided config into the active
  artifact runner. It accepts managed Snap cache flags
  `--use-cached-snap-monster-json`, `--refresh-snap-monster-json-if-needed`, and
  optional `--snap-monster-cache-path`; direct `--snap-monster-json PATH_OR_URL`
  and `--use-default-remote-snap-monster-json` remain dev/debug overrides and
  are mutually exclusive with the managed flow. Remote Snap refresh failures,
  invalid JSON, and invalid shape are controlled input errors. Missing
  cache/source fields or missing enemy type mapping prints audit and exits
  nonzero without writing/running a misleading scenario. Backend reports now
  expose structured progress steps such as `matching_enemy_names_primary`,
  `checking_cached_snap_titles`, `refreshing_snap_metadata`,
  `rechecking_snap_titles_after_refresh`, `building_abyss_wave_scenario`, and
  `running_gcsim_artifact`. Coverage reports also include `timing_seconds`
  diagnostics for primary matching, cached Snap loading/matching, remote
  refresh/indexing when it happens, refreshed matching, and total report time.
  The first forced Snap fallback can be noticeably slower because it refreshes
  the managed runtime cache from the online `Monster.json`; later runs should
  use the cached file and avoid network. Future UI loader messages should
  surface these backend steps so enemy matching, Snap refresh, scenario build,
  and optional artifact run do not look frozen.
  Wave scheduling contract: current implemented `group_clear` behavior is
  sequential groups. The first scenario wave is active at sim start; the next
  wave is spawned only after all enemies in the current wave/group are dead. If
  a wave contains multiple targets, killing one target does not spawn the next
  wave; the whole group must be cleared first, and then the next wave spawns as
  a whole group. Future mode design: single-target DPS should use the selected
  single target and then the next single target; this should later be tied to
  the existing fact-DPS single-target/multi-target setting so fact DPS and GCSIM
  DPS describe the same scenario. Multi-target DPS should eventually have two
  settings-backed modes: `sequential waves` (current group-clear behavior) and
  `stack/rolling replacement` (future, not implemented), where enemies from the
  next wave may be added to replace dead enemies from the current group. Do not
  implement stack mode until the in-game behavior/policy is confirmed.
  Artifact runs that supply `gtt_wave_scenario` now preflight-check the selected
  artifact with `-gtt-info` before sim execution. The selected active or shipped
  fallback artifact must report `gtt_patch_version=gtt-wave-scenario-v1` and
  capability `gtt_wave_scenario_payload`; otherwise the runner returns
  `artifact_wave_scenario_contract_mismatch` with observed/required
  version/capability diagnostics and a rebuild-required message without running
  the sim. Runs without a wave scenario keep the previous behavior and do not
  require this preflight.
  Stable backend/dev smoke case catalog now exists at
  `run_workspace/gcsim/smoke_cases.py`, with committed manual config fixture
  `run_workspace/gcsim/smoke_fixtures/manual_config_minimal.txt`. Named case
  `abyss_2026_04_16_f12_c3_s2_manual_config` proves manual GCSIM config plus
  generated cached Abyss wave scenario, managed cache-first Snap matching, and
  artifact preflight/run parsing without depending on an ad-hoc runtime run
  directory config. Latest manual case run passed through the active artifact:
  scenario generation used managed Snap cache hit (`remote_not_needed`),
  resolved `Tenebrous Papilla: Type II` by `snap_title_contains_target` to
  `tenebrouspapillatypei`, built one wave / one target, and artifact preflight
  observed `gtt-wave-scenario-v1` with `gtt_wave_scenario_payload`. Parsed run
  summary stayed smoke-only: duration_mean `0.03333333333333333`, dps_mean
  `0.0`, total_damage_mean `0.0`; do not treat this as DPS correctness.
  Additional manual/dev fixture
  `run_workspace/gcsim/smoke_fixtures/manual_config_neuv_furina_lauma_xiangling.txt`
  stores a hand-written Neuvillette/Furina/Lauma/Xiangling config for backend
  compatibility diagnostics only. Its manual `target` lines are placeholders;
  when used through `abyss_wave_scenario_smoke`, generated `-gtt-wave-scenario`
  JSON remains the enemy/wave/HP/type source of truth. A real local run on
  2026-06-05 for cached period `2026-05-16` F12 C2 S1 built three exact-name
  scenario waves (`fatuielectrocicinmage`, `ruindrakeearthguard`,
  `primogeovishap`) and passed artifact preflight. This smoke exposed a patched
  GCSIM runtime panic in `pkg/stats/damage/damage.go`: dynamically spawned wave
  enemies can receive sparse target keys after gadgets, while cumulative damage
  buckets were sized by current enemy count and indexed by `targetKey-1`.
  Patch-stack fix `0004-gtt-dynamic-wave-stats.patch` makes damage cumulative
  buckets grow by resolved enemy index and lets aura aggregation grow for
  dynamic `result.Enemies`. After rebuilding the active artifact in-place on
  2026-06-05, the same 3-wave smoke passed with artifact preflight intact.
  The same config also still passes without `-gtt-wave-scenario`. No DPS
  correctness claim.
  Enemy type mapping JSON now supports explicit records with `source_kind`,
  `source_id`, `gcsim_type`, and optional diagnostics; the old
  `enemy_types_by_nanoka_monster_id` shape still loads for dev compatibility.
  Dev coverage checker
  `python -m run_workspace.gcsim.abyss_enemy_type_mapping_report --gcsim-enemy-registry-source path --scan-cache-dir data/cache/abyss/source_data --format text`
  can bulk-scan cached source-data files (`**/floor_*.json`) or accept repeated
  `--cache-file`; optional `--period-start`/`--floor` filters keep checks
  narrow. It reports cache file count, source rows, resolution counts by method
  and identity kind, missing/ambiguous type mappings, HP-present/type-missing
  rows, type-present/HP-missing rows, compact unresolved/ambiguous row lists,
  and JSON resolved-row details without mutating caches, running GCSIM, or
  touching UI. It accepts the same managed Snap cache flags as the smoke CLI.
  Network is not used when primary registry matching resolves all rows, and is
  not used when the cached Snap title fallback resolves the remaining rows.
  The online Snap `Monster.json` refresh is a last step only when explicitly
  enabled and cache results are missing, invalid, or insufficient. The report
  records `snap_cache`, refresh/cache status, source kind, progress `steps`, and
  Snap fallback counts. Direct `--snap-monster-json PATH_OR_URL` and
  `--use-default-remote-snap-monster-json` remain dev/debug overrides. Snap
  fallback resolutions are counted separately as `snap_title_fallback` and final
  containing-target resolutions as `snap_title_contains_target`, so exact/base
  coverage remains visible. Current real-code-path diagnostic over the 8 cached
  source files / 96 rows resolved 88 exact, 7 `snap_title_fallback`, 1
  `snap_title_contains_target`, 0 missing, and 0 ambiguous after Snap title
  fallback. Use it to validate matcher behavior on real cached Abyss rows.
  Missing/ambiguous rows should drive small matcher or alias fixes, not a full
  hand-written enemy mapping table.
  Backend/dev GCSIM enemy type registry matcher exists in
  `run_workspace/gcsim/enemy_type_registry.py`. It can parse known target type
  keys from local prepared GCSIM `pkg/shortcut/enemies_gen.go` and match Abyss
  Nanoka/Fandom name candidates by exact normalized name, compatible/base-name
  rules, and small explicit aliases. Manual mapping JSON records remain the
  first-priority override/exception layer, not a full production enemy database.
  Missing or ambiguous compatible matches are reported instead of guessed, and
  fuzzy/display-name similarity is not production truth. The smoke CLI and
  coverage checker accept `--gcsim-enemy-registry-source path`; existing callers
  without a registry remain strict/manual-only.
  Backend config readiness audit exists in
  `run_workspace/gcsim/config_readiness.py`; it accepts lightweight prepared
  team inputs and reports whether explicit non-display-name GCSIM mappings,
  current/max levels, weapon/refinement, artifact set mappings, normalized
  artifact add-stats, and confirmed talent order are ready. It does not infer
  keys from localized/display names and keeps Traveler unsupported/deferred.
  Backend key-mapping report foundation exists in
  `run_workspace/gcsim/key_mapping.py`; it accepts explicit character, weapon,
  and artifact-set seed records, converts ready records into readiness
  `GcsimMappingRef` values, summarizes missing/ambiguous/display-name-rejected
  statuses by entity type, and warns that production mapping data is still
  missing unless a caller marks a trusted source present. Display-name and
  normalized-name guessed sources are rejected, and Traveler remains
  unsupported/deferred. Tiny committed dev seed lives at
  `run_workspace/gcsim/mapping_seeds/gcsim_key_mapping_seed_v1.json`, with a
  report CLI at `python -m run_workspace.gcsim.key_mapping_report --format text`.
  The seed is not production-complete coverage; it only records a few explicit
  curated/dev keys already pinned by backend fixtures/static catalog evidence.
  Backend/dev entity registry coverage reporting has been added in
  `run_workspace/gcsim/entity_key_readiness_report.py`, with CLI
  `python -m run_workspace.gcsim.entity_key_readiness_report --format text`.
  It parses local prepared GCSIM shortcut sources `pkg/shortcut/characters.go`,
  `weapons.go`, and `artifacts.go`, prefers explicit seed overrides first, then
  exact normalized key candidates, then a conservative contiguous-name-span
  fallback. The span fallback matches whole normalized tokens/spans only, not
  random substrings: `Yumemizuki Mizuki -> mizuki` and
  `Rainbow Serpent's Rain Bow -> rainbowserpent` are accepted as audit
  candidates, while `The Daybreak Chronicles -> ak` is rejected. Exact and span
  candidates are readiness evidence only
  (`auto_exact_candidate_not_curated_mapping` /
  `contiguous_name_span_candidate_not_curated_mapping`), not committed curated
  production mapping. Default local diagnostics read existing HoYoWiki
  character/weapon stats caches and the artifact set static seed;
  character/weapon cache identities are HoYoWiki `entry_page_id` values and are
  explicitly warned as not the missing production game-id mapping owner. Traveler
  and Traveler variants remain unsupported/deferred. Current-registry gaps
  remain controlled missing and should later surface as user-facing warnings to
  replace the entity or update GCSIM source. Full character/weapon/artifact-set
  production mapping coverage remains future work.
  This report is a catalog/registry diagnostic, not an account SQLite mapper:
  default character and weapon names such as Mizuki come from local HoYoWiki
  stats caches, not from localized `account_characters.name` and not from
  network at report runtime.
  GCSIM level text helper has been added in `run_workspace/gcsim/config_level.py`.
  It converts account level/promote data into current/max text for future config
  generation: breakpoint levels such as `80,promote=5 -> 80/80` and
  `80,promote=6 -> 80/90`, missing promote on breakpoint levels is assumed
  after ascension with a warning, and final/special caps use `90/90`, `95/95`,
  and `100/100`. Missing level is a controlled `missing_level` result.
  Backend character config block builder has been added in
  `run_workspace/gcsim/config_blocks.py`. It renders one prepared
  character/equipment block with character level/constellation/talents, weapon
  key/refinement/level, artifact set counts, and artifact-snapshot-only
  normalized `add stats`; missing mappings, unsupported Traveler, unconfirmed
  talent order, missing levels, or unmappable artifact stats return controlled
  not-ready results with no partial config text. It still does not generate a
  full GCSIM config, query UI/account storage, create mapping data, run an
  artifact, or wire UI.
  Backend/dev full-config assembly foundation has been added in
  `run_workspace/gcsim/config_assembly.py`, with a shell-only Chasca/Ororon/
  Furina/Bennett rotation fixture at
  `run_workspace/gcsim/smoke_fixtures/rotation_chasca_ororon_furina_bennett.txt`.
  The shell supplies only options, energy, active character, placeholder target,
  and rotation script; generated character/equipment/artifact blocks must come
  from prepared backend state, and enemy/wave/HP/type truth remains the
  generated `-gtt-wave-scenario` payload. The assembler rejects shells that
  contain manual `char`/`add weapon`/`add set`/`add stats` lines and emits no
  partial full config when any character block is not ready. Explicit prepared
  input adapter boundary lives in `run_workspace/gcsim/prepared_config_adapter.py`;
  it consumes explicit prepared backend/dev JSON/dict input, does not access
  UI/storage/network, and ignores final/right-panel stat fields instead of
  using them as `add stats`. Dev fixture
  `run_workspace/gcsim/smoke_fixtures/prepared_team_chasca_ororon_furina_bennett.json`
  is marked `synthetic_dev_fixture`: it is not account truth, not UI state, and
  not production mapping data, but it can render four ready generated blocks and
  assemble them with the shell through
  `python -m run_workspace.gcsim.prepared_config_adapter --format text|json`.
  The bridge writes a full config only when all prepared characters and the
  shell audit are ready; missing required characters, mappings, weapons,
  talents, or artifact stats skip output instead of writing partial config.
  Account-backed backend/dev prepared config adapter now exists in
  `run_workspace/gcsim/account_prepared_config.py`; CLI:
  `python -m run_workspace.gcsim.account_prepared_config --format text|json`.
  It reads real account SQLite rows for Chasca/Ororon/Furina/Bennett, consumes
  stored ready `gcsim_character_key` and `gcsim_weapon_key` fields, never uses
  localized `name` as GCSIM identity, uses current-equipped weapon rows when
  present, and otherwise chooses deterministic ready observed weapon candidates
  by weapon type with `dev_weapon_candidate_not_account_truth`. Current-equipped
  artifact rows are now consumed when present: the bridge reads
  `account_character_equipped_artifacts`, joins `artifacts` and
  `artifact_substats`, builds `add stats` only from equipped artifact main/sub
  stat totals, and builds `add set` from equipped set counts. It does not inject
  final/account/right-panel stat sheets or manual set bonuses. Missing or
  incomplete current artifacts produce a controlled not-ready report instead of
  a silent synthetic fallback. Artifact set keys are exact registry-checked
  `set_uid` candidates for this backend/dev bridge and are not curated
  production mapping. The adapter writes no partial config when a
  character/weapon/talent/artifact block is not ready.
  Because current GCSIM v2.42.2 parser accepts talent levels only in `1..10`,
  account/HoYoLAB displayed talent levels are normalized through
  `run_workspace/gcsim/config_talents.py` before config output: active C3/C5
  effects are matched by colored talent references against active skill names,
  the +3 bonus is removed when exactly one talent matches, and unresolved or
  still-above-range levels are capped to 10 with explicit warnings such as
  `constellation_talent_bonus_not_resolved` and
  `post_normalization_talent_level_capped_to_gcsim_range`. Local no-network smoke on
  2026-06-06 used real account Chasca/Ororon/Furina/Bennett rows, cached
  `2026-02-16` F12 C1 S1 wave scenario, and the active artifact; it passed as a
  backend compatibility smoke only, with no DPS correctness claim. Right-panel
  persistence/UI and production selected-team/current-build ownership were not
  added.
  The same backend CLI now supports an end-to-end dev smoke with account-prepared
  team blocks, the manual Chasca rotation shell, a temporary dev-only boosted
  energy override (`--dev-energy-override`), generated cached Abyss waves, and
  the existing patched artifact runner. The override writes a temporary shell
  copy in the run dir and does not mutate the committed rotation fixture. This
  remains a backend compatibility smoke only, not DPS correctness. Future GCSIM
  browser work needs direct rotation code input/editing rather than relying only
  on committed shell fixtures.
  Backend shipped fallback artifact resolver exists in
  `run_workspace/gcsim/shipped_artifact.py`; runner support in
  `run_workspace/gcsim/artifact_runner.py` is explicit opt-in and uses a ready
  fallback candidate only when the active built artifact is unavailable. No
  production shipped binary is bundled yet, and shipped fallback marker/capability
  validation is still future release-process work. It still does not generate
  account/team configs, create production project-id-to-GCSIM mapping data,
  model final Abyss wave policies, or wire UI. Next GCSIM tasks should add real
  shipped artifact packaging/validation, real key-mapping source data, stronger
  smoke configs, and then generate payloads/configs from app-owned scenario and
  team data before any UI wiring.
- Stat/GCSIM `add stats` key mapping handoff lives in `docs/handoff/STAT_NORMALIZATION.md`; the pure normalization layer exists in `hoyolab_export/stat_normalization.py`. Use it before final stat totals or GCSIM config generation.
- First GCSIM Browser UI should be a dedicated browser tab/page near the existing character/weapon and artifact browser areas, not an isolated popup and not a small TeamCard-only panel. The right panel remains the compact run summary that shows factual DPS and Sim DPS results.
- UI browser package cleanup plan:
  - GCSIM Browser code should live under `ui/gcsim_browser/`, with the main widget in `window.py`, following the existing `ui/artifact_browser/window.py` pattern.
  - Do not keep browser/page widgets as loose one-off files directly under `ui/` unless they are truly tiny shared pages.
  - Later, move the current character/weapon workspace out of the monolithic `ui/app_shell.py` into a dedicated browser package, likely `ui/character_browser/` or `ui/character_weapon_browser/`.
  - That later refactor should be done only after the GCSIM Browser skeleton is stable, because the current character/weapon workspace is working and tied to selection markers, weapon overlays, filters, and app-shell runtime state.
  - The later refactor must be split into small behavior-preserving moves: first move classes without behavior changes, then update imports, then add tests/smoke checks.
- The first browser MVP should consume the current runtime team composition from Run Workspace/right panel without adding right-panel persistence. Abyss mode has Team 1 / Team 2 tabs; DPS Dummy mode has one team tab.
- GCSIM Browser MVP layout:
  - compact team readiness cards: character, weapon, set summary, ready/issues;
  - GCSIM total-stats tooltip/report for each character, to compare against right-panel/account stats;
  - Abyss target browser: C1/C2/C3, side by team, waves, enemy names, levels, HP, and resolved GCSIM target types;
  - Later visual polish: render Abyss enemies as compact horizontal cards similar to Nanoka enemy cards, with icon, name, level, HP, wave grouping, and compact use of horizontal space instead of long vertical plain-text lists.
  - current solo/multi target toggle controls which targets are sent to GCSIM;
  - current wave policy remains `group_clear`; stack/rolling replacement stays future work;
  - temporary run-defaults block shows iterations and boosted-energy status; later move defaults to GCSIM settings;
  - raw GCSIM rotation-code editor is required in the MVP; visual/button-based rotation building is later/optional;
  - current implemented first run action is `Run selected chamber`: it maps active Team 1/Team 2 tab to Abyss side 1/2, uses the selected C1/C2/C3 button, takes the same current cached Abyss source-data identity used by the Browser/right-panel preview (`period_start`, `floor`) instead of backend smoke defaults, runs asynchronously through `ui/gcsim_browser/run_worker.py`, and writes config/scenario paths, source identity, scenario waves/targets/total HP, observed duration, DPS summary, warnings, failed action buckets, incomplete characters, and controlled error category only into the GCSIM Browser Results panel. It does not write Sim DPS/clear-time back to the right panel yet.
  - current implemented batch action is `Run 3 chambers`: it maps the active Team 1/Team 2 tab to side 1/2, uses the same source identity and rotation editor text, runs C1/C2/C3 sequentially in the same Qt worker (no parallel GCSIM processes), writes a compact batch report into GCSIM Browser Results, and writes runtime-only compact Sim DPS cells (`clear time / DPS`) into the right panel for the active team only. Results live on `AppShellController`, are not persisted to SQLite/history, and are cleared on obvious input changes such as team/equipment/source/target-mode/rotation changes.
  - future GCSIM run scheduler should keep the current sequential `Run 3 chambers` path as the safe MVP, then add bounded parallel chamber runs only when the user's machine can handle them. It needs `max_workers`/auto mode, isolated `run_dir`/config/scenario/stdout/stderr per chamber, ordered C1/C2/C3 result aggregation, and cancellation/progress handling.
  - later run work should add right-panel sim tooltips/details, stale/result history policy, settings-backed run defaults, and production polish around Browser/right-panel result navigation.
- First UI should prioritize readiness reports, generated config visibility, run results, warnings/stderr, and clear error categories over visual polish.
- Each team/run card should eventually have simulator action, GCSIM logo/label, and compact result area for sim DPS/clear time.
- The right-panel GCSIM logo/label/button must not open the GCSIM website. Its likely product behavior is to open/focus the in-app GCSIM Browser workspace tab, duplicating the left workspace GCSIM tab for discoverability from the Sim DPS column. Final exact behavior can be decided later.
- Before bundling or modifying GCSIM, verify current license/attribution requirements. It is believed to be MIT-compatible, but do not rely on memory.
- Simulator window should receive team data from TeamCard/TeamSnapshot: characters, constellations, weapons, refinements, artifacts, stats, set bonuses, talents if available, rotation, target/enemy setup.
- DPS Dummy GCSIM path remains supported as the simpler one-team mode:
  - one team;
  - one target;
  - configurable HP/resistance or supported target setup;
  - raw rotation editor;
  - sim DPS result;
  - comparison with factual dummy DPS if available.
- GCSIM for Abyss should start from the backend path that already exists: account-prepared team, raw rotation code, generated cached Abyss waves, and `group_clear` wave scenario. Do not promise perfect full-Abyss simulation.
- For Abyss, compare factual DPS from HP/time with Sim DPS/clear time from the selected solo/multi target mode.
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

- Current profile import/export covers account characters, weapons, character
  details, account language, crop manifest, allowed account assets, and artifact
  DB. It should eventually become full offline profile import/export, not only
  the current account/artifact snapshot.
- Future full profile should include, where safe: account characters, weapons, artifacts DB, build presets, run history, settings/local state needed for offline use, and relevant local catalog/cache data if appropriate.
- It must not include cookies, auth tokens, browser profile/session data, or private debug dumps.
- Use versioned profile format and safe restore/backup semantics.

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

- Review `docs/obsidian/GTT/GenshinTeamsTracker.canvas`, `docs/obsidian/GTT/DataFlow.canvas`, and `docs/obsidian/GTT/SourceBoundaries.canvas` in Obsidian: check readability, missing descriptions, broken nodes, and whether the data flow/source boundaries are understandable.
- Add color highlighting for build summary Crit Value and Proc Count later; choose thresholds/colors first.
- Later unify reset controls in target selector, sort popup, and sets popup.
- Future polish: make Sort popup and Sets popup selection behavior visually consistent with artifacts/targets/presets.
- Artifact Browser geometry status: divmod/remainder adaptive fit is implemented
  from the calibrated minimum layout (`GRID_SIZE.width()` artifact cell, compact
  Assignment rows, fixed preset panel). Extra horizontal remainder goes to
  Assignment width as a preferred/current width, not a propagated minimum. Do
  not reintroduce candidate-width search or guessed card/gap constants.
- Future startup preload/cache concept, after real optimization work: prewarm
  heavy tabs/widgets under the startup loader or a progress strip, including
  Artifact Browser, Character/Weapon workspace, preset-edit controls, and
  pixmap/text/marquee caches. Persistent caches should reduce loader time on
  later launches. Do not use this loader as a substitute for fixing current
  optimization or layout bugs.
- Loader/prewarm backlog from AppShell click profiling: the visible roster marker
  path is still instant (`~2-3 ms`), but deferred work can still feel heavy.
  Prewarm the Character/Weapon workspace weapon asset list so the first
  selected-character weapon auto-filter cannot reopen SQLite (`~140-150 ms` in
  the measured cold sync), and consider prebuilding/reusing filtered weapon grid
  card pixmaps/widgets where safe (`~15-40 ms` cached sync). Also keep an eye on
  right-panel selected-details/bonus-strip rendering for equipped characters
  (`~50-66 ms` refresh spikes) as a possible loader/cache target if it becomes
  visible again.
- Pre-release packaging/size audit: the current dev `.venv` is about `767 MB`,
  mostly `PySide6` (`~628 MB`) plus `playwright` (`~104 MB`). PySide6 includes
  large unused-looking pieces such as `Qt6WebEngineCore.dll`, `resources`,
  `translations`, `qml`, Designer/tools, and extra plugins. Before public
  release, build a clean distributable instead of shipping the dev environment:
  exclude unused Qt WebEngine/QML/Designer/translations/plugins where safe,
  exclude tests/docs/experiments/debug/raw profile/cache folders, keep user
  runtime data outside the bundled app, and verify the final unpacked and
  installer sizes. Target this as a dedicated packaging pass, not as ordinary
  feature work.
- AppShell resize twitch: isolated probe reproduced the effect outside the app,
  and it is reduced on a 144Hz monitor without desktop holes. Treat it as
  system/environment live-resize behavior for now; no active app-level fix is
  planned.
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
