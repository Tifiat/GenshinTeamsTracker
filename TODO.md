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
- After large stages, compact source-of-truth handoffs before the next major
  task. If root docs become long, contradictory, or dominated by completed
  history, report: "handoffs should be cleaned before the next major task."
- After each completed pushable task, final responses should include one short
  Russian commit-message suggestion in impersonal passive/resultative wording,
  not first-person past wording. Prefer a style equivalent to "has been
  added/fixed/updated" or "added/fixed/updated as a completed result", not a
  style equivalent to "I added/fixed/updated".
- Test-suite layout/rules live in `docs/handoff/TESTS.md`; keep new tests under
  the matching project area and prefer narrow per-folder `unittest discover`
  runs for the touched subsystem.
- When adding/changing persistent structures, source/cache formats, domain models, raw payload discoveries, UI prototype contracts, or long-lived research, update the relevant handoff map in `docs/handoff/` and keep root docs as concise entrypoint pointers.
- `docs/obsidian/` is a user-owned folder for optional human maps. It is not
  source of truth; ignore it unless the user explicitly asks to work on
  Obsidian maps.

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
  - continue the separate `AppShell` prototype launched by `python -m ui.app_shell_smoke`; `main.py` still launches legacy `ui.main_window.App`. Do not switch the production entrypoint yet: the compact chamber/result area has live in-memory Abyss timer and factual-DPS behavior, active-mode Reset is typed, RUN-page Save writes immutable grouped backend bundles, and History can read grouped saved rows with sanitized read-only selected snapshot details plus a derived user-facing PNG preview v0; polished History export/actions and routing remain future, and the approved future `main.py` switch must run startup adaptive scaling before constructing `QApplication`;
  - keep the reduced fixed-width right operations dock around `ui.right_panel.live_run.panel.RunRightPanelWidget`; it must not be user-resizable or expand with the window;
  - right-panel source ownership has been refactored into `ui/right_panel/{common,live_run,history,pvp,settings}` plus `dock.py`/`header.py`; `ui/right_panel_prototype.py`, `ui/account_data_page.py`, and old PvP right-panel exports remain compatibility shims. PvP page/stage constants are canonical in `ui/right_panel/pvp/_shared.py`; the compact PvP v0 target slot now uses `ui/right_panel/common/compact_slot.py` plus common mini-box/mini-zone visual parts, and the Draft right panel uses visual pick/ban chips. Follow-ups remain full scoped PvP artifact equipment and scoped PvP GCSIM;
  - harden the extracted Character/Weapon workspace as the first left workspace; it already uses overlay scrollbars, a painted pixel-aligned icon grid via `ui/utils/pixel_icon_grid.py`, typed `TeamBuilderState`, weapon type/rarity filters, selected-character weapon type auto-filtering, sequential roster quick-pick, per-mode team selection, roster slot markers, target-based compatible weapon assignment, persistent SQLite-backed current weapon restore/assignment through `account_equipment`, normalized local icon paths for right-panel display, and SQLite-backed weapon passive/effect enrichment for right-panel tooltips/bonus chips;
  - AppShell left workspace navigation exists with Character/Weapon, lazy-created Artifacts, GCSIM Browser, `ui/history_browser/` History saved-bundle list/details/preview v0, and PvP Decks/Play/Draft v0 workspace pages. `LeftWorkspaceHost` owns pages/lazy construction, while nav clicks request stable workspace ids through root `AppShell`; activating History reloads the snapshot root, hides the live Run panel behind an isolated read-only History viewer without clearing live session state, and keeps polished export/cards future under the contract in `docs/handoff/HISTORY_BROWSER.md`;
  - continue the production adapter: first typed live-session ownership now lives in `run_workspace/session.py` for mode/per-mode team state, selected target, external bonus state, Abyss timers/T2 follow flags, compact runtime GCSIM chamber results, and active-mode Reset. Immutable History Snapshot Bundle v1 schema/service now lives in `run_workspace/history_snapshot.py`, `run_workspace/history_snapshot_builder.py` can build backend-only bundles from supplied session/right-panel data, and RUN-page Save persists grouped bundles through an explicit store root; History row selection/viewer v0 is read-only, while right-command routing and durable GCSIM history attachment remain future work;
  - keep roster clicks as quick-pick add/remove and right-panel slot clicks as selected build/details target toggle;
  - AppShell quick-pick marker latency is fixed with incremental visible-card marker updates; roster clicks now update markers immediately and defer/coalesce right-panel refreshes through a short scheduler;
  - AppShell filters now use session-cached character/weapon asset lists plus the reusable painted icon grid. The grid computes integer physical-pixel item/gap rectangles under fractional startup downscale and prepares cached HiDPI pixmaps outside paint events. Right-panel slot selection does not reload portrait/weapon PNGs, fitted right-panel PNG canvases are cached per DPR/source, and remaining performance work is to reduce first bonus-strip chip rebuild cost on high-DPI screens;
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
  - RightOperationsDock now owns a persistent same-style header row with page-specific Abyss / DPS Dummy controls plus an always-visible global Account action; live Reset/Save commands sit in the bottom RUN panel action row, not in the header. Account opens a compact localized Account/Data page in the same dock without changing the left workspace. The page reuses the current HoYoLAB import/update flow, offline profile save/load/sign-out actions, and language selector; AppShell refreshes account asset caches after import and clears only its runtime team state when an offline profile is loaded or signed out. Header routing uses stable ids rather than localized text. Future PvP can replace its page-specific controls while Account stays present;
  - root AppShell now gates Character/Weapon workspace mutation clicks by the active right-dock page: roster and weapon clicks are no-op while Account/Data is open. Returning from a non-RUN page updates the requested controller mode and right-panel model before exposing RUN content, so the previous run mode cannot paint as a stale intermediate frame;
  - future first-run/onboarding flow should handle empty-account startup: when the account database is empty, guide the user by opening/highlighting the Account/Data page as part of the onboarding/tutorial sequence. Do not implement this as an isolated Account/Data auto-open task now; debug it together with the first-opening guidance flow. A compact Support/Donate header action, fuller settings area, and fuller Account-page support area remain optional future directions, not current UI;
  - keep PvP inside the AppShell `pvp` workspace/right-dock policy. Detailed PvP UI mode/stage direction lives in `docs/handoff/PVP_UI_ROADMAP.md`; Decks mode v0, Play/local match setup v0, backend/read-model `unified_pool`, readable unified-pool Draft board v0, and local post-draft Assignment/Weapon/Timers/Completed result v0 are implemented with the corrected two-player visual source/target match layout. Current PvP limitations are not future design prohibitions: the target right panel should support a rich isolated PvP build flow with character, weapon, artifact, and scoped GCSIM stages when those tasks are chosen;
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
- Before extending History selection/routing/details or durable GCSIM history, keep using `run_workspace/history_snapshot_builder.py` to build immutable `HistorySnapshotBundle` records from typed run/session state. The right-panel widget must display/command this state; it must not be the source of truth for timers or saved runs.

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

## 6. History Browser

- History is an AppShell left workspace owned by `ui/history_browser/`. It reads
  immutable snapshot bundles from the configured root, shows grouped minimal
  rows, supports saved-row selection, shows read-only selected snapshot details,
  displays a derived PNG preview v0 for the selected snapshot, and keeps the
  isolated History right-viewer separate from the live Run panel.
- Future richer Akasha-like rows, polished export/share actions, XLSX export,
  and right-dock History command routing are contracted in
  `docs/handoff/HISTORY_BROWSER.md`.
- Backend-only `run_workspace/history_snapshot.py` defines the autonomous
  immutable bundle schema/service and grouped storage:
  `abyss/<period_start>/<bundle_id>/snapshot.json` or
  `dps_dummy/<bundle_id>/snapshot.json`. The reader can list old flat dev
  bundles without migrating them. `run_workspace/history_snapshot_builder.py`
  builds bundles from supplied typed session/right-panel data; RUN-page Save now
  writes grouped bundles.
- Do not develop `ui/run_history_window.py` or `runs_history.json` as the final
  History model.

## 7. Abyss Data Updater and Enemy Model

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
  then stores `cached_icon_path` on rows for future tooltip UI. Persisted JSON
  keeps these icon references cache-file-relative
  (`floor_<floor>_assets/monster_icons/<file>`), not absolute user/profile
  paths; the loader resolves them to local paths for Qt and can recover old
  absolute cache entries by filename when the copied icon file exists under the
  current period/floor asset directory. Icon downloads are bounded-parallel and
  reuse existing URL-hash files even during source-data `--force`; force
  refreshes source data, not identical already-cached icons.
  It does not wire final UI; it supersedes the historical static fixture as the
  runtime source-data path. HP source modes are now
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
  custom tooltip surface. The accepted content is compact HTML/text with
  enemies grouped by wave, monster icons, enemy names/levels/target mode/HP,
  calculation mode, HP/sec, DPS result/reason, and source summary including
  composition/name/count source, HP source, and match method/confidence. Native
  Qt/system tooltips are not acceptable. Account/Data now has a persistent DPS
  subzone toggle for multi-target HP mode, default off/solo-target.
  Manual/debug period switcher exists at
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
- Abyss source research is done; see `docs/handoff/ABYSS_ENEMY_DATA.md` and
  `docs/handoff/ABYSS_MECHANICS_NOTES.md`. `docs/handoff/ABYSS_HP_FIXTURE.md`
  is a historical 2026-05-16 research/debug fixture, not current runtime
  factual-DPS truth. Keep the source join resilient so one unavailable/stale
  source does not break the feature.
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
- Factual Abyss DPS should use confidence states, not a single yes/no gate. Prefer source-like/period-specific HP multipliers; if those are missing but enemy ids/counts/levels/base HP are matched, a Fandom general floor-multiplier estimate can be shown with an explicit `estimated_from_floor_multiplier` warning. If core inputs are missing/ambiguous, show enemy list/warnings and keep HP/time DPS unavailable. The accepted Fact DPS tooltip already exposes source/match confidence details; do not add separate near-cell source UI unless a later product decision asks for it.
- `docs/handoff/ABYSS_HP_FIXTURE.md`, `hoyolab_export/abyss_sources.py`, and
  `hoyolab_export/abyss_fixture_report.py` are historical audit/fixture
  references only. Normal displayed AppShell Fact DPS must use the production
  source-data cache (`run_workspace/abyss/source_data*.py`) and must not fall
  back to the old invalid/static fixture path.
- Abyss mechanics audit exists at `docs/handoff/ABYSS_MECHANICS_NOTES.md`. It
  records Fandom structured fields/prose tags for shields, wards,
  invulnerability, state RES, paralyze/downed windows, true damage HP events,
  summons/adds, elemental/reaction requirements, and mode-specific stat blocks.
- Backend Abyss mechanics parser/report code exists in `hoyolab_export/abyss_mechanics.py`. It parses Fandom enemy-page wikitext snippets into structured fields and warning tags such as `shield_check`, `ward_or_barrier`, `phase_invulnerability`, `state_res_override`, `paralyze_window`, `true_damage_hp_event`, `summons_or_adds`, `elemental_requirement`, `reaction_requirement`, `lunar_requirement`, `high_mobility`, and `mode_specific_stats`. Future Abyss UI work is mechanics-warning integration only, not another broad audit or Fact DPS tooltip/source-summary redesign.

## 8. Stats / Resonance / Static Catalogs

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
- Isolated Right Panel / TeamBuilder Prototype v6 exists: pure view-model in `run_workspace/right_panel_prototype_view_model.py`, display stat helper in `run_workspace/display_stats.py`, and live-run QWidget implementation in `ui/right_panel/live_run/panel.py`; `ui/right_panel_prototype.py` is a compatibility facade. Manual visual smoke launcher: `python -m ui.right_panel_prototype_smoke` with fake data by default, or `python -m ui.right_panel_prototype_smoke --real-thoma` for the no-network Thoma + build id 20 sample plus several local no-preset character slots. The no-preset sandbox loader now uses SQLite account runtime records and observed weapon stacks, not raw account detail JSON. It keeps the v4/v5 layout, enforces a minimum standalone content width, uses square character portraits with aligned weapon/build boxes, keeps chamber factual/sim DPS columns, and shows selected-character virtual build display rows from character base + selected weapon + selected artifact build + ascension/baselines. The build box uses compact Artifact Browser preset-row set semantics: active set icons plus 2p/4p overlay/count, with `Equip`/`ART` placeholders for no-preset slots. The lower slot main-stat badge is derived from the selected artifact build snapshot's actual sands/goblet main stats; do not source it from target recommendations, character element, HoYoLAB current-final stats, or display-stat order. Selected weapon meta includes weapon base ATK and secondary stat from selected SQLite observed weapon stack/account runtime data. The selected-details bottom area is a compact external bonus source strip, not a plain set-name line; it shows modeled artifact-set and weapon-passive static effects with numeric chips and custom tooltips. Real smoke selected weapons are explicit observed weapon options from SQLite, not inferred from current-equipped provenance. It is visual-only and not wired into the legacy right panel.
- Low-priority UI polish: replace the temporary full-strip click behavior for `Apply external bonuses` with the user's custom compact toggle component, then reuse that same toggle for the Artifact Browser on/off switch. Keep selection state shown by field/border styling rather than a checkbox.
- Reusable UI rule: dense vertical card/grid panels should use `ui/utils/overlay_scroll.py::OverlayVerticalScrollArea` when native scrollbars would make content jump or reserve asymmetric empty space. It draws an auto-hidden scrollbar over the right edge, appears on scroll/edge hover/drag, and does not participate in layout width. The Right Panel prototype uses it first; apply the same utility to other suitable project scroll areas after visual verification.
- Display stat rows are virtual TeamBuilder results in this order: HP, ATK, DEF, EM, Crit Rate, Crit DMG, ER, then damage/healing bonuses. HoYoLAB stat-sheet `final` rows are reference/debug only for TeamBuilder slots and must not be shown as selected-build final stats. Raw partial labels such as `Base HP`, `Weapon ATK`, `Asc ...`, `Art CR`, `WATK`, `AER`, etc. must not be shown as final selected-detail stat rows. Direct static artifact set/weapon passive display effects may be applied only from normalized SQLite rows; formula effects, conditional bonuses, resonances, talents, and constellations remain excluded.
- Raw partial contribution labels such as `Base HP`, `Weapon ATK`, `Asc ...`, `Art CR`, `WATK`, `AER`, etc. are internal/debug provenance and should not be shown as final selected-detail stat rows.
- Stat normalization / GCSIM stat-key mapping handoff exists at `docs/handoff/STAT_NORMALIZATION.md`; backend code exists in `hoyolab_export/stat_normalization.py`. It maps project artifact `property_type` values to normalized keys/GCSIM `add stats` keys, converts percent-point values like `46.6` to ratio values like `0.466`, keeps flat stats unchanged, treats Crit Value / Proc Count as virtual metrics, and intentionally does not compute final totals or apply passives/set bonuses/resonances.
- Next Run Workspace/UI step after visual inspection of Prototype v6: inspect real multi-character layout, no-preset states, and build-slot readability; then refine exact proportions if needed before planning/building the first Run Workspace / TeamBuilder shell around the shared TeamBuilder/TeamCard concepts.
- Weapon passive/refinement text is reference data only for now; do not parse free text into stat formulas or auto-apply passive stat bonuses unless a future effect is explicitly modeled/whitelisted.
- Standard 5-star filter exists with `assets/filters/standard.png` and tri-state behavior: show all / only Standard 5-star / exclude Standard 5-star. Membership is stored as static trait `standard_5_star` in `character_identity`; HoYoWiki entry `2952` is the source context, while the current API payload is not a clean structured character list, so the 5-star standard character membership is seeded by explicit HoYoWiki character entry ids. Traveler is intentionally included in this trait and must stay included when the dedicated Traveler model is implemented.
- Future storage audit/refactor: account character/weapon runtime tables are started; next audits should decide which remaining generated JSON/cache files should stay as small rebuildable source caches or seeds and which should be normalized into SQLite/catalog DB tables. Prefer DB storage only for runtime-critical data that is frequently joined, mapped, filtered, queried, reported, or used by stat calculator/UI. Remaining likely candidates include HoYoWiki character stats, weapon stats, character traits, character region catalog, mapping reports / alias override tables, and other large generated account/catalog JSON files after usage audit. A two-layer model is acceptable: raw/source JSON cache for fetched HoYoWiki/HoYoLAB data plus normalized DB tables for lookup, mappings, aliases, reports, UI, and stat calculation.

## 9. Export

- Abyss history and DPS Dummy history have a selected-snapshot PNG preview v0
  that uses saved display labels instead of raw paths/debug text; polished
  export actions and XLSX remain future work.
- Target formats: PNG/image for visual sharing and XLSX for analysis/comparison. CSV/HTML can be optional fallback later.
- PNG export should reuse the same visual components/cards as history where practical.
- XLSX should be data-oriented and include season/period, date, run type, chamber/side, team, characters, weapons, artifact set bonuses, timers, factual DPS if available, sim DPS if available, notes/warnings.
- Do not prioritize import of history as a separate feature. Later full offline profile import/export can include history.

## 10. GCSIM Integration

- GCSIM now has backend/dev infrastructure plus an AppShell Browser backend-MVP product path for selected runtime teams. It is usable for current Browser prepare/run diagnostics and runtime right-panel Sim DPS rows; the Browser has a first compact UI pass with context/rotation tabs/run summary, while production packaging, mapping coverage, saved-result persistence/history policy, no-code rotations, and final polish remain future work.
- Read before GCSIM work:
  - `docs/handoff/GCSIM.md` for upstream research and CLI/result behavior;
  - `docs/handoff/GCSIM_ENGINE_INTEGRATION_PLAN.md` for the current GTT engine lifecycle, patch stack, Browser MVP, cleanup/retention policy, and production-readiness sequence;
  - `docs/handoff/STAT_NORMALIZATION.md` for project stat normalization and GCSIM stat-key mapping rules.
- Implemented enough to rely on:
  - transactional local engine-store/update prototype with source acquisition, ordered patch backends, runtime probe/build-artifact checks, and active/rollback metadata;
  - patch stack and `-gtt-info` capability validation owned by the dedicated GCSIM handoff rather than this root TODO;
  - active-artifact runner plus backend/dev config readiness, key mapping reports, account-prepared config bridge, selected-runtime-team config adapter, and Abyss wave scenario bridge; `account_prepared_config.py` remains a dev/smoke bridge, not the Browser product team source;
  - AppShell GCSIM Browser workspace prepares/runs from the current selected TeamBuilder/AppShell team state, not localized-name `team_names`; missing characters/weapons/artifact sets/artifacts/talents/levels/refinement/rotation errors produce grouped readiness summaries;
  - Abyss Browser selected-chamber and `Run 3 chambers` actions require the current cached Abyss source identity and never fall back to backend smoke defaults; both write runtime-only right-panel Sim DPS rows for matching team/chamber/side when a run result exists;
  - DPS Dummy has a diagnostic backend run path that uses the selected team and manual rotation shell without Abyss identity, history persistence, no-code rotation support, or damage-correctness claims;
  - GCSIM boosted/infinite energy is an explicit Account/GCSIM setting (`gcsim_boosted_energy_enabled`) that injects/replaces `energy every interval=480,720 amount=100;` only when enabled and clears stale runtime Sim DPS results when changed; dev CLI energy override remains in `account_prepared_config.py`;
  - Sim DPS cells have runtime-only tooltips with status, clear time, DPS, average total damage per sim run, source/config paths, target mode, stale reasons, warnings/issues, and explicit no-DPS-correctness/no-history notes; Browser runtime results are not saved history;
  - normal GCSIM Browser blocked-run output is compact/readiness-first with debug issue counts/codes instead of raw issue dict walls; the prepare/preflight path is exposed as `Check readiness`, with raw diagnostics kept behind Advanced/Debug UI;
  - DPS Dummy reports energy mode and dummy target HP/resist/source for diagnostics;
  - generated GCSIM engines are retention-pruned to active + one previous successful + one latest failed; `.go/build-cache` is rebuildable and cleaned after successful probe/build unless explicitly kept; `.go/pkg/mod` remains as the small module cache; manual cleanup dry-run command is `python -m run_workspace.gcsim.cleanup`.
- Real next work:
  - create/curate production project-id-to-GCSIM mappings for characters, weapons, artifact sets, and enemy type overrides where automatic registry matching is insufficient;
  - decide production packaging/shipped fallback artifact policy and release validation for `gtt-gcsim.exe`;
  - connect GCSIM results to typed run/session state and immutable saved snapshots/history instead of treating Browser runs as durable results;
  - finish production mapping coverage, user-facing readiness/error polish, no-code rotation editing policy, run retention/debug keep-artifacts controls, cancellation/progress, and final AppShell/GCSIM UI polish.

## 11. KQM / Standard Builds Research

- Investigate where GCSIM gets default/standard character builds.
- Do not hardcode "KQM standards" until source, license, and data format are verified.
- Research whether this data is actually KQM standards, where it is stored, whether it can be used legally/technically, and what it contains: artifacts, talents, weapons, rotations, assumptions.
- Future uses: simulator fallback, draft bot, account-independent team estimates, comparing user builds to standard baseline.

## 12. Artifact Optimizer

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

## 13. Offline Profile

- Current profile import/export covers account characters, weapons, character
  details, account language, crop manifest, allowed account assets, and artifact
  DB. It should eventually become full offline profile import/export, not only
  the current account/artifact snapshot.
- Future full profile should include, where safe: account characters, weapons, artifacts DB, build presets, run history, settings/local state needed for offline use, and relevant local catalog/cache data if appropriate.
- It must not include cookies, auth tokens, browser profile/session data, or private debug dumps.
- Use versioned profile format and safe restore/backup semantics.

## 14. Far Future / Non-MVP Ideas

- Far-future PvP/tournament, analytics, draft bot, donation/support, monetization, optional AI companion, and similar speculative ideas live in `docs/handoff/FAR_FUTURE_TODO.md`.
- Do not load those ideas into normal MVP task planning unless the user asks about them or wants to add/update a far-future idea.
- Active PvP v0 contract lives in `docs/handoff/PVP_V0_CONTRACT.md`; implementation status lives in `docs/handoff/PVP_BACKEND_STATUS.md`, and PvP UI direction lives in `docs/handoff/PVP_UI_ROADMAP.md`. Backend foundation now exists in `run_workspace/pvp/` with deck JSON, deck validation, Decks UI preset persistence (`run_workspace/pvp/deck_preset.py`), shared observed weapon-stack identity helper (`run_workspace/pvp/weapon_identity.py`), Free Draft schedule/reducer/action log, local Free Draft controller/projection API, UI-facing board/read-model projection with backend-owned `unified_pool` plus validator/sample fixture (`samples/pvp/ui_contract/free_draft_board_projection_sample.json`), post-draft team/weapon assignment validation, timer/result summaries, local-account Free Draft deck export/full-loop smoke from SQLite runtime data, draft-system registry, PvP session bundle snapshot/verifier, report-only ruleset applicability/cost previews/ruleset-balance application reports, and deterministic dev smokes (`python -m run_workspace.pvp.full_loop_smoke`, `python -m run_workspace.pvp.free_draft_controller_smoke`, `python -m run_workspace.pvp.free_draft_controller_smoke --json`, `python -m run_workspace.pvp.free_draft_controller_smoke --step-demo`, `python -m run_workspace.pvp.ui_full_flow_smoke`, `python -m run_workspace.pvp.account_deck_export_smoke`, `python -m run_workspace.pvp.account_full_loop_smoke`, `python -m run_workspace.pvp.session_bundle_smoke`, `python -m run_workspace.pvp.ruleset_applicability_smoke`, `python -m run_workspace.pvp.ruleset_balance_smoke`). AppShell now has PvP Decks, Play/local setup, Draft board, and local post-draft Assignment/Weapon/Timers/Completed result v0 with current UI widgets under `ui/pvp_browser/`: Decks persists root-resolved local presets and validates them through backend `DraftDeck`; Play chooses Player 1/Player 2 deck presets and starts an in-memory local `FreeDraftController`; Draft consumes the backend `unified_pool`, renders one readable character pool, completes local pick/ban, then continues through PvP-owned assignment, weapon assignment, manual timers, and read-only result summary without normal TeamBuilder/Run mutation. Candidate PvP UI follow-ups and target scoped Artifact/GCSIM build-flow direction live in `docs/handoff/PVP_UI_ROADMAP.md`. Online relay, real Gentor/Abyss importer, richer rulesets/cost rendering, Traveler support, scoped PvP GCSIM scoring, PNG/export, and PvP History remain later stages.
- PvP reference-site findings live in `docs/handoff/PVP_REFERENCE_SITE_AUDIT.md`; planning history remains in `docs/handoff/PVP_MODE_PLAN.md`.
- PvP/tournament source audit remains in `docs/handoff/PVP_RULESETS_AUDIT.md`; current public/source mapping status is in `docs/handoff/PVP_RULESET_SOURCE_MATRIX.md`. Gentor-like rulesets can currently feed cost/config research, but executable draft schedule derivation remains blocked until a source-specific adapter or explicit flow exists. Abyss Draft has no confirmed public parseable ruleset payload in this repo.

## Other Future / Maintenance Items

- Add color highlighting for build summary Crit Value and Proc Count later; choose thresholds/colors first.
- Later unify reset controls in target selector, sort popup, and sets popup.
- Future polish: make Sort popup and Sets popup selection behavior visually consistent with artifacts/targets/presets.
- Artifact Browser geometry status: divmod/remainder adaptive fit is implemented
  from the calibrated minimum layout (`GRID_SIZE.width()` artifact cell, compact
  Assignment rows, fixed preset panel). Extra horizontal remainder goes to
  Assignment width as a preferred/current width, not a propagated minimum. Do
  not reintroduce candidate-width search or guessed card/gap constants.
- Future startup preload/cache concept, after real optimization work, is tracked
  in `docs/handoff/PRELOADER_BACKLOG.md`. Do not use that future loader as a
  substitute for fixing duplicate work, avoidable rebuilds, or current layout
  bugs. Keep TODO here as a pointer; detailed loader candidates belong in the
  dedicated handoff with measurement context.
- AppShell/Artifact Browser performance measurement on the weak 1366px HP
  laptop is recorded in
  `docs/handoff/performance_measurements/2026-06-13_appshell_artifact_browser_hp_1366.md`.
  Follow-up optimization should reduce total work first: avoid full
  `PixelIconGrid` pixmap refreshes for outline-only updates, avoid redundant
  show-time pixmap preparation, remove duplicated account SQLite loads between
  Character/Weapon and PvP workspaces, and profile Artifact Browser target
  button creation before moving any work under a future loader.
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
