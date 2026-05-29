# App Shell / Workspace Plan

Purpose: target architecture for replacing the legacy `ui/main_window.py` with
a new app shell. This is a design handoff only; it records the intended layout,
ownership boundaries, and staged migration path before implementation.

## Target Shape

```text
AppShell
|-- LeftWorkspaceHost
|   |-- WorkspaceNav
|   `-- QStackedWidget / workspace content
`-- RightOperationsDock
    `-- current operation widget
```

Terms:

- Left workspace: information, browsing, selection, and large working views.
- Right operations dock: fixed-width process/control/build area.
- Fixed right panel means a stable operations width based on the Right Panel
  Prototype direction; it is not a user-resizable split-pane in the first pass.
- Custom overlay scrollbars remain relevant where native scrollbars would shift
  right-panel content or create asymmetric empty space.

This should be a new application shell, not the old main window with the old
right column patched in place.

## Left Workspaces

### Character / Weapon Workspace

- Replacement for the current left grids in `ui/main_window.py`.
- Should be the first/default workspace.
- The old main window's right half is not migrated into this workspace.
- It should update typed TeamBuilder/run state, not legacy image-path slots.

### Artifact Browser Workspace

- C1 embedded mode for the existing Artifact Browser is implemented as an
  AppShell left workspace.
- The workspace is lazy-created on first switch so the default Character/Weapon
  workspace stays fast.
- Standalone Artifact Browser remains available; embedded mode does not show
  standalone close/window controls.
- Embedded mode is currently calibrated for a compact minimum-width landing:
  one `GRID_SIZE.width()` artifact cell, compact Assignment/target rows with
  marquee text, and the fixed preset/current-equipment panel visible. Current
  calibration: Assignment panel width 144px, Assignment minimum hint about
  138px, target row button about 94px, and AppShell minimum about 1408px. The
  future divmod/remainder fit should build on this calibrated minimum, not on
  the old wider one-column viewport.
- Artifact/target/preset lists use overlay scrollbars. Artifact grid overlay
  scrollbar right-offset polish remains future work; keep it overlay-style so
  it does not consume layout width.
- Known geometry follow-up: horizontal resize can still show top-level
  AppShell window movement/crawl from propagated minimum-size constraints. This
  is not Assignment-panel jitter. Future fix should inspect top-level geometry,
  minimumSizeHint propagation, `QStackedWidget`/`LeftWorkspaceHost` constraints,
  and resize-settle behavior.
- Behavior depends on selected build target:
  - selected target exists: later equip/apply actions can target that
    character/slot;
  - no selected target: browse-only mode; it must not implicitly equip or apply
    artifacts/builds to anyone.

### GCSIM Workspace

- Future simulation/generation/results workspace.
- Do not implement until the app shell and typed team/run state are in place.

### History Workspace

- Future replacement for legacy history.
- Legacy `runs_history.json` / image-path history UI is obsolete and should not
  become the long-term design.

## Right Operations Dock

Near-term default:

- Build/Run Panel based on `ui.right_panel_prototype.RightPanelPrototypeWidget`.
- Fixed width.
- Always visible in the normal app shell.

Future operation modes:

- Import/settings/language controls.
- PvP draft/deck/opponent controls.
- Build panel after PvP draft when a buildable pool/team exists.

The right side is an operations dock, not only a build widget. Do not implement
mode switching in the first shell patch unless the task explicitly asks for it.

## Selection And Artifact Browser Rule

- The right panel/controller owns or displays the current selected build target.
- Clicking an already-selected character/slot again should clear that selection.
- Artifact Browser must check selected build target through shared
  controller/state:
  - if target is `None`, it must not equip/apply anything;
  - if target is set, later equip/apply actions can target that character/slot.
- Do not couple Artifact Browser directly to right-panel widgets. Use shared
  state/controller signals or a narrow adapter.
- Detailed future Artifact Browser equipment UX lives in
  `docs/handoff/ARTIFACT_BROWSER_EQUIPMENT_UX.md`.

Future target/equip-mode contract:

- if the right panel has a selected character, that character is the Artifact
  Browser operation target and is first synced as the browser's single selected
  character so presets appear immediately;
- if the user deselects that character in Artifact Browser, browser selection
  clears for preset browsing, while the right-panel target remains as a
  secondary operation-target marker for future free artifact clicks;
- if the user selects another browser character while the right-panel target
  still exists, presets follow the browser selection and equipment writes still
  target the right-panel character until it is cleared;
- if the right panel has no selected target, the browser may use exactly one of
  its own selected character targets;
- 0 or 2+ browser-selected characters means equip mode is off;
- free artifact clicks equip only in equip mode;
- preset-edit mode artifact clicks edit the preset only;
- the operation target should be shown as a visual selected/highlighted
  character target in the browser, not as a long "target from right panel" text
  banner;
- current equipment is shown as a `Текущая сборка` top zone, not as an
  `artifact_build` preset;
- clicking a preset previews/selects it only, while `Надеть пресет` is the
  explicit write action.

Future weapon move/swap rule:

- persistent weapon equipment already validates `weapon_fingerprint` assignment
  counts against `known_count`;
- future weapon panel UI should support explicit move/swap from a named current
  owner when all known copies are assigned;
- do not silently steal an exhausted assigned weapon by fingerprint without an
  explicit source owner/copy choice.

## Timer / Run Logic

- Timer remains visually in the right operations dock/build panel.
- Durable timer/run/session logic should move toward a `RunTimerModel`,
  `RunSessionController`, or equivalent model/controller layer.
- The right panel should display and command timer state, not own persistence or
  durable run/session logic.
- Later implementation should inspect and reuse useful parts of:
  - `ui/widgets/timers.py`
  - `run_workspace/models.py`

Preserve useful behavior such as wheel-friendly timer editing and validation,
but do not preserve the old right panel as the final owner of run state.

## Legacy Plan

- `ui/main_window.py` becomes legacy once `AppShell` is introduced.
- The old right panel should not be preserved except for useful timer/run logic.
- Old history is obsolete and should be replaced later, not migrated as the
  future design.
- Delete/cleanup legacy code only after the new shell is stable and the user has
  approved the cleanup stage.

## PvP Direction

- PvP likely remains a separate window/mode at first.
- During draft/deck/opponent phases, showing the normal build panel can be
  misleading because builds may not be editable yet.
- The right operations dock can later show PvP-specific controls for those
  phases.
- Once draft/pool/team is ready, the build panel can be reused against the PvP
  pool/team instead of the full account roster.
- PvP training runs can later save history scoped to the current deck/PvP mode.

## Staged Implementation Plan

### Stage 1: New AppShell

- Introduce a new `AppShell` / `MainShell` file/class.
- Left side contains a Character/Weapon workspace extracted from old
  `ui/main_window.py`.
- Right side contains fixed-width `RightPanelPrototypeWidget`.
- Keep old `ui/main_window.py` as legacy/fallback.
- Do not embed Artifact Browser yet.

Current prototype entrypoint:

```powershell
.\.venv\Scripts\python.exe -m ui.app_shell_smoke
```

This command launches the separate `ui.app_shell.AppShell` prototype only.
`main.py` still launches the legacy app. The prototype uses a real empty
`TeamBuilderState` and does not copy `ui/right_panel_prototype_smoke.py` fake
team builders into the production shell path.

Stage 2 interaction status:

- Character/Weapon workspace icon clicks flow through `AppShellController` into
  typed `TeamBuilderState`.
- Roster character clicks are a sequential quick-pick, independent from the
  right-panel build target. Abyss fills team 1 slots 1-4 first, then team 2
  slots 1-4. Single-team modes such as DPS Dummy use only that mode's slots.
- Clicking a character already picked in the current mode removes it from its
  slot without compacting the remaining slots; the next new character fills the
  first empty gap in slot order. Clicking a new character while all slots are
  full does nothing.
- Abyss and DPS Dummy keep independent in-memory `TeamBuilderState` selections
  inside `AppShellController`; switching tabs preserves each mode's picks until
  that mode is reset or changed.
- Selected roster portraits show compact team-colored markers and a team-local
  slot number in the bottom-left corner, leaving the top-right constellation
  area clear.
- Clicking the selected right-panel slot again clears the selected build target.
- Clicking a weapon assigns it only when a selected slot has a compatible
  character. It uses observed weapon stack metadata from SQLite-backed asset
  helpers and does not create fake weapon instances or revive current-equipped
  weapon identity.
- The selected right-panel character/build target auto-filters the weapon grid
  by that character's weapon type. Clearing or switching the selected target
  clears/switches the auto type filter; rarity filters remain independent.
- AppShell normalizes local visible asset paths before handing character/weapon
  details to the right panel. Slot portraits, selected weapon icons, and
  Moonsign/Hexerei member icons should use the same existing local files that
  the left roster/weapon cards already displayed, rather than relying on
  relative SQLite/manifest paths.
- Weapon assignment enriches the selected details with local SQLite
  `weapon_passive_tooltips` and `weapon_display_stat_effects`. Right-panel
  weapon tooltips should show passive text, not HoYoLAB `weapon.desc` lore, and
  direct always-on static passive rows should appear as `weapon_passive_static`
  bonus source chips when present.
- Weapon assignment is persisted through `hoyolab_export/account_equipment.py`.
  `AppShellController` reads `account_character_equipped_weapons` when a
  character is added to a slot and writes only through `equip_weapon(...)` when
  a weapon card is clicked. Removing a character from a team slot does not
  unequip that character.
- Current equipped artifact ids are read into `character_details_data` as
  read-only `current_equipped_artifact_ids_by_slot` metadata, then converted
  into a runtime-only current-equipment `ArtifactBuildSnapshot` for right-panel
  artifact stat and set-bonus display. Right-panel artifact set icons should be
  resolved from the same persistent artifact/set icon data used by Artifact
  Browser rows; guessed set-icon paths are only a last fallback, and text labels
  such as `2p`/`2+2` should appear only when icon assets are genuinely missing
  or invalid. This does not create or mutate
  `artifact_builds`, `artifact_build_slots`, or `artifact_build_targets`.
- The right panel is refreshed through `RightPanelPrototypeWidget.set_model(...)`
  after controller state changes.

Future equipment-state note:

- Persistent equipment-state design lives in
  `docs/handoff/ACCOUNT_EQUIPMENT_STATE_DESIGN.md`. Stage A schema/service
  helpers are implemented in `hoyolab_export/account_equipment.py`, and Stage B
  AppShell weapon persistence is wired. Equipment is per character, not per
  right-panel mode.
- Future persistent account equipment work should add side icons showing who
  currently wears each artifact/weapon and in-game-like explicit move/swap UI.
  Live current-equipment artifact snapshot support is implemented for the
  right panel; if character A equips an item worn by B, the service layer
  supports move/swap resolution when the source owner is explicit.
- Build presets are definitions, not current equipped state. Equipping a preset
  should be an explicit action for exactly one character, copying that preset's
  artifacts into that character's current equipped state; if the preset has
  missing slots, those target slots are cleared so current equipment matches
  exactly what the preset shows. Later manual equipment changes must not mutate
  the preset itself.
- Artifact Browser remains browse-only when no build target is selected. With a
  selected target, future explicit equip/apply actions may modify current
  equipped state.
- AppShell C1 embeds Artifact Browser as the `Artifacts` left workspace. The
  browser is created lazily on first switch, reflects the right-panel selected
  operation target through browser target selection/highlight plus the
  current-equipment zone, and falls back to exactly one browser-selected
  character target when the right panel has no target. Artifact clicks and
  preset apply are still no-op/not wired for equipment writes.
- Embedded Artifact Browser keeps standalone window-resize behavior disabled
  and is calibrated for a compact one-artifact-cell minimum layout: target rows
  use `MarqueeButton` with a reserved portrait/icon zone and marquee text only
  in the name area, Assignment is narrower than the previous 180/238px
  calibrations, JSON import/clear buttons do not force the artifact viewport
  wider than one `GRID_SIZE.width()` cell, and the fixed preset panel remains
  visible. Divmod/remainder adaptive fit is still future work.
- JSON import/clear controls need a later clean placement/scaling pass; they
  must not reintroduce an artifact viewport minimum wider than one grid cell.
- Artifact grid overlay scrollbar needs later visual right-offset tuning
  (roughly one scrollbar width plus a small 1-5px margin), without consuming
  layout width.
- AppShell resize twitch was reproduced with an isolated PySide probe outside
  the app and is reduced on a 144Hz monitor without desktop holes. Treat it as
  system/environment live-resize behavior for now; no active app-level
  workaround is planned.
- Artifact/preset/weapon side icons should come from persistent current
  equipment tables. `artifact_build_targets` remains intended/available target
  metadata, not current ownership.
- HoYoLAB observation apply helpers exist for explicit artifact/weapon
  observations, but live import does not call them yet. Missing HoYoLAB
  equipment data must not clear local equipment.
- Future drag/swap of right-panel character cards should swap characters within
  one team and between teams, but quick-pick does not depend on drag/drop.

Performance audit note, 2026-05-26:

- Opt-in timing is available with `GTT_PERF_LOG=1` or
  `python -m ui.app_shell_smoke --perf-log`.
- Programmatic offscreen audit with local SQLite-backed asset helpers measured
  73 character cards and 58 visible weapon cards. A quick-pick character click
  spent only about `0.1-0.4 ms` in `AppShellController` state mutation and
  roughly `1-2 ms` building the right-panel view-model. `RightPanelPrototypeWidget`
  rebuilds were usually `25-60 ms`, with an occasional `~150 ms` layout/details
  spike.
- The dominant click bottleneck is selected roster marker refresh:
  `set_character_selection_markers(...)` calls `reload_characters()`, which
  rereads SQLite (`~50-80 ms`), filters/sorts cheaply, clears the whole grid,
  recreates all 73 `AssetIconLabel` widgets, reloads/scales their `QPixmap`s,
  and costs about `470-680 ms` per click before event-loop paint work.
- Filter latency has the same root. Clearing character filters rebuilt 73 cards
  in about `560 ms` synchronous filter time; standard-only and element filters
  were faster only because they reduced the visible card count to 7-8. Weapon
  filters spent `~60-80 ms` in SQLite reload and `~20-210 ms` rebuilding pixmap
  cards depending on result count.
- Display stat, elemental resonance, Moonsign, and Hexerei calculation were not
  the bottleneck in this audit; selected details/stat rows were generally below
  `1 ms` in the measured scenarios.
- Completed optimization direction: marker-only selection updates no longer
  rebuild the character grid; right-panel refresh is now deferred/coalesced; and
  normal filter clicks now operate on session-cached AppShell asset records plus
  shared scaled roster/weapon pixmaps instead of rereading SQLite and rescaling
  every icon from scratch.

Performance fix status:

- `CharacterWeaponWorkspace` now keeps a stable visible character-card registry
  keyed by character id. Roster marker-only updates call
  `AssetIconLabel.set_selection_marker(...)` on affected visible cards instead
  of calling `reload_characters()`.
- Full character grid reload remains reserved for real data/filter/layout
  rebuilds. Mode switches may sync all visible markers, but still iterate
  existing widgets instead of rereading SQLite or recreating pixmaps.
- After this change, opt-in perf logs showed normal quick-pick marker refresh at
  about `0.0-0.2 ms` for one affected card, and mode-switch full marker sync at
  about `0.7-0.9 ms` for 73 visible cards. `filter_characters` no longer appears
  in the marker-only click path.
- Roster clicks now update marker widgets first, request repaint, and schedule a
  short debounced right-panel refresh. Rapid clicks coalesce into one later
  `RightPanelPrototypeWidget.set_model(...)` call.
- Character and weapon asset items are cached for the AppShell session. A future
  import/data refresh can explicitly clear this cache, but ordinary filter
  clicks should not reopen SQLite.
- `AssetIconLabel` uses a shared scaled pixmap cache keyed by icon path, target
  size, device pixel ratio, mtime, and file size. Marker-only updates do not
  reload or rescale pixmaps.
- After this pass, local programmatic smoke measured character add handler
  `~0.7 ms` plus deferred right-panel flush `~56 ms`; remove/fill-gap handlers
  `~0.3-0.4 ms` plus deferred flush `~49 ms`; 8 rapid character clicks
  `~2.6 ms` before a single deferred flush; mode switches `~0.4-0.7 ms` before
  deferred flush; standard-character filter `~14 ms`; character filter clear
  `~111 ms`; weapon type filter `~18 ms`; weapon type/rarity clear `~95-96 ms`.
- Right-panel add/select smoothness pass is completed enough for manual UX:
  quick-pick places/removes characters through a fast UI path, persistent
  equipment hydration is deferred/stale-guarded, team/slot widgets update in
  place, selected details use a stable skeleton with a persistent bonus strip,
  and adding a character no longer performs a visible intermediate
  minimal-details refresh before hydrated details are available.
- Artifact Browser target-character filters were separately profiled from
  artifact item filters. Artifact item filters were already cheap
  (`artifact_filter_apply` roughly `0.3-5 ms`). The target-character filter lag
  came from destructive target button rebuilds: standard filter all/exclude
  recreated about 65-73 `MarqueeButton` target buttons and measured about
  `50-58 ms` in the build step after universal icon caching.
- Artifact Browser target-character filters now keep target buttons in one
  stable layout and refresh by ensuring missing buttons once, calculating
  visible keys, then updating `setVisible(...)`, checked state, operation-target
  property, and icon/text only when needed. Normal target filter refresh logs
  should use `artifact_target_filter_refresh ... mode=in_place`.
- Do not repeat the failed intermediate approach that cached target button
  widgets while removing/re-adding them through layouts. That caused blank
  transient windows and multi-second first init. Stable Qt widget ownership is
  required: keep widgets parented in a single layout and update
  visibility/state/content in place.
- Startup loader + persistent cache/bake work is intentionally later and mostly
  pre-release. Until that loader pass, keep remaining cold-start/stutter sources
  visible and measurable so bad synchronous paths are easy to find and fix.
  Do not add persistent caches just to hide current lag while the UI is still
  being actively optimized.
- When the loader pass starts, mark every loader-covered subsystem explicitly
  and bake/cache repeatable work in the same pass. Candidates include Artifact
  Browser cold-start store/init data, target/preset UI preparation,
  preset-edit controls, pixmap/text/marquee caches, and bulk persistent
  equipment/negative-cache prewarm for account characters. After that point,
  second and later openings should reuse baked/cache data where safe.
- Future right-panel slot drag/drop is feasible because `TeamBuilderState`
  already supports whole-slot swap/move across teams. The UI should drag a full
  slot payload, not just a portrait, so weapon/artifact/details move together;
  resonances and team bonuses must be recalculated from the post-drop team
  composition rather than copied as slot data.

Sizing note:

- The first AppShell prototype uses a fixed `RightOperationsDock` width from
  the reduced Right Panel Prototype minimum (`660px` at the time of writing).
- The dock is not user-resizable and must not expand when the outer window gets
  wider; the left workspace receives extra width.
- The Character/Weapon workspace uses project overlay scroll areas for its
  character and weapon grids so native vertical scrollbars do not reserve layout
  width or shift grid content.

### Stage 2: Real Controller / Adapter

- Add a real controller/adapter between left character/weapon selection and the
  right panel view-model.
- Maintain typed `TeamBuilderState` / selected team / selected slot.
- Remove smoke-only dependencies from production path.
- Keep smoke presets as debug harness only.
- Initial click wiring exists in `ui/app_shell.py`; remaining work is richer
  `CharacterDetailsData` preparation, artifact build selection, and later
  Artifact Browser equip/browse integration.

### Stage 3: LeftWorkspaceHost

- Add `LeftWorkspaceHost` using a `QStackedWidget` and small workspace nav.
- First workspace: Character/Weapon.
- Add disabled/TODO entries for Artifact Browser, GCSIM, and History only if
  useful for navigation planning.

### Stage 4: Embedded Artifact Browser

- C1 implemented: add Artifact Browser embedded/content mode as an `Artifacts`
  left workspace while preserving standalone browser construction.
- Preserve grid resize recalculation.
- Respect selected target / no-target browse-only rule through visible
  target-selection/current-equipment UI scaffolding.
- Later C2+: wire artifact click equip, preset apply, conflict confirmation,
  owner side icons, and selected build/preset handoff into typed TeamBuilder
  state/equipment service.

### Stage 5: GCSIM And History

- Add GCSIM workspace after the shell and state model are stable.
- Add new History workspace based on immutable saved run snapshots.
- Do not migrate legacy history UI as the final design.

### Stage 6: Legacy Cleanup

- Remove legacy main-window right panel after replacement is stable.
- Retire old history window/data path after a migration/export decision.

## Implementation Guardrails

- Do not patch the old main-window right column as the future architecture.
- Do not copy `ui/right_panel_prototype_smoke.py` builders into production.
- Do not save future runs from live widgets or image paths.
- Do not make Artifact Browser equip/apply anything without an explicit selected
  build target.
- Do not implement PvP, GCSIM, Artifact Browser embedding, or legacy cleanup in
  the first AppShell patch unless the user explicitly asks for that stage.
