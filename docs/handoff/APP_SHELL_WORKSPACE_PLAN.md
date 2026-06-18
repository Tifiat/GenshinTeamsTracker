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
    |-- PersistentHeader
    |   |-- page-specific tabs / controls
    |   `-- global actions
    `-- ContentStack
        |-- live_run current-run pages
        |-- history snapshot-bound shared Run presentation
        |-- pvp controls/stages
        `-- settings / Account / Data pages
```

Terms:

- Left workspace: information, browsing, selection, and large working views.
- Right operations dock: fixed-width process/control/build area.
- Fixed right panel means a stable operations width based on the Right Panel
  Prototype direction; it is not a user-resizable split-pane in the first pass.
- `RightOperationsDock` owns a persistent header above its content stack.
  Page-specific controls and global actions are separate ownership zones but
  form one visually continuous row of same-style buttons with the ordinary
  inter-button spacing only. Do not add a visual divider, stretch gap, or
  page-specific duplicate of a global action.
- Current normal header controls are Abyss / DPS Dummy plus Account. The live
  RUN panel itself owns the localized bottom Reset and Save commands for the
  active live run mode. Save writes immutable backend snapshot bundles only; it
  does not open History. The PvP AppShell policy replaces RUN header controls
  with `Decks` / `Play` / `Draft` when the `pvp` workspace is active.
  Account opens a compact localized Account / Data page in the same fixed dock
  without changing the left workspace. The page reuses the existing HoYoLAB
  import/update behavior, offline profile save/load/sign-out actions, and
  language selector. AppShell refreshes account asset caches after import and
  clears only its runtime team state when an offline profile is loaded or signed
  out. Only the currently open dock page is visually active. Run-mode routing
  and workspace routing use stable ids, never localized button text.
- `LeftWorkspaceHost` owns left pages and lazy construction. Left-nav buttons
  request stable workspace ids through root `AppShell`; root AppShell performs
  activation and remains the coordination point for future workspace-driven
  right-dock page/control policies. Do not let future workspaces become
  independent UI islands that directly rewrite the right dock.
- Root `AppShell` also routes left-workspace mutations according to the active
  right-dock page. Character/Weapon roster and weapon clicks may mutate run
  state only while the RUN page is active. Account / Data is a global page, not
  a team-building operation page. Opening Account must preserve the current
  operation target. Returning from a non-RUN page must update the requested
  controller mode and right-panel model before exposing RUN content so the
  previous run-mode model cannot paint as a stale intermediate frame.
- The PvP Decks/Play/Draft pages and History snapshot presentation are
  workspace-driven right-dock policies. History uses a separate read-only
  instance of the same mode-specific Run presentation component tree, while the
  live instance and session remain intact. Future empty-database startup should
  auto-open Account / Data setup, and later onboarding may highlight the
  Account action. A compact
  Support/Donate action near Account and a fuller support area inside Account
  remain optional future directions; do not add them until explicitly requested.
- Custom overlay scrollbars remain relevant where native scrollbars would shift
  right-panel content or create asymmetric empty space.

Target right-panel source ownership:

```text
ui/right_panel/
  common/
    # shared right-panel visual primitives:
    # character slot cards, team cards, portrait/weapon/artifact mini-zones,
    # shared metrics/styles/helpers, non-domain-specific card UI

  live_run/
    # normal current-run right panel used by Characters/Weapons,
    # Artifact Browser, and GCSIM Browser
    abyss/
    dps_dummy/
    gcsim/

  history/
    # frozen snapshot adapters/host/read-only policy;
    # reuses the mode-specific Run presentation instead of copying it

  pvp/
    # all PvP right-panel pages and internal match-stage panels
    decks/
    play/
    draft/
      pick_ban/
      assignment/
      weapons/
      artifacts/
      gcsim/
      timers/
      result/

  settings/
    # Account/Data, language, DPS settings, and other global right-dock settings

  dock.py
  header.py
```

Mode terminology:

- `live_run` mode is the normal current-run right-panel mode. Characters/Weapons,
  Artifact Browser, and GCSIM Browser operate on the same live run state; the
  right panel must not become three unrelated panels just because the left
  workspace changes.
- Abyss and DPS Dummy are submodes of `live_run`. Abyss owns two teams, chamber
  rows, timers, factual DPS, and GCSIM summaries where available. DPS Dummy owns
  one team, dummy settings/results, and GCSIM summaries where available.
- Artifact Browser and GCSIM Browser remain left workspaces. They should use the
  selected `live_run` target/state through controllers or adapters, not directly
  own right-panel widgets.
- `settings` mode owns Account/Data, language, DPS settings, and similar global
  right-dock pages. Account/Data can be opened without destroying the current
  live run, PvP, or History state.
- `history` mode is a right-panel mode for read-only frozen snapshots. The left
  History browser remains under `ui/history_browser/`; `ui/right_panel/history/`
  may own the snapshot adapter/host/read-only policy, but selected snapshots use
  a separate instance of the same mode-specific Run presentation classes as
  `live_run`, not a History-specific widget tree.
- `pvp` mode owns PvP right-dock pages and match-stage panels under
  `ui/right_panel/pvp/`. The left/main PvP workspace remains under
  `ui/pvp_browser/`.
- PvP build mode must not be implemented as a separate visual clone of
  `live_run`. After pick/ban, PvP should launch a scoped instance of the normal
  Characters/Weapons + Artifact Browser + GCSIM Browser + `RunRightPanelWidget`
  pipeline. The scope owns its own run state and equipment/artifact data source,
  while reusing the existing widget/controller behavior.
- PvP source data comes from a profile provider: local players may read the
  current app SQLite DB as source data, while imported/remote players read a
  `.gttpvp` package's managed temporary `account_slice.sqlite`. Runtime
  equipment state is not the provider DB: PvP uses separate per-seat scoped
  weapon/artifact equipment state that starts empty and never writes normal
  account equipment tables.

The global source-ownership refactor toward this tree has been applied for the
current right-panel code. Future moves should keep imports and corresponding
tests updated in the same task.

Display scale contract:

- The AppShell design is calibrated against a 1920x1080 reference desktop.
  Calibrated AppShell/Artifact Browser design constants, including minimum
  width/height and panel/grid widths, remain design-pixel layout contracts.
- Screens narrower than the 1920px reference width must use startup-only adaptive
  downscale so the rendered UI keeps the same proportions instead of compressing
  columns. Do not upscale above 1.0 on 1920px+ screens.
- This is a final application requirement. `app_shell_smoke` may be the first
  wired entrypoint, but the production AppShell launcher must run the same
  scaling bootstrap before `QApplication` is created.

This should be a new application shell, not the old main window with the old
right column patched in place.

## Left Workspaces

### Character / Weapon Workspace

- Replacement for the current left grids in `ui/main_window.py`.
- Should be the first/default workspace.
- The old main window's right half is not migrated into this workspace.
- It should update typed TeamBuilder/run state, not legacy image-path slots.
- Character and weapon browser grids use `ui/utils/pixel_icon_grid.py` through
  the narrow `ui/character_browser/` adapter. The grid is one painted surface
  with deterministic integer physical-pixel item/gap layout, cached HiDPI
  pixmaps, custom tooltip support, and stable item-id click signals.
- Current left workspace ids are stable internal ids: `characters_weapons`,
  `artifacts`, `gcsim`, `history`, and `pvp`. They are routing ids, not
  localized display labels.

### Artifact Browser Workspace

- Embedded mode for the existing Artifact Browser is implemented as an
  AppShell left workspace.
- Artifact Browser participates in the current `live_run` right-panel mode
  through a selected target/state adapter. It must not own or instantiate a
  separate right-panel widget for team-building state.
- The workspace is lazy-created on first switch so the default Character/Weapon
  workspace stays fast.
- Standalone Artifact Browser remains available; embedded mode does not show
  standalone close/window controls.
- Embedded mode is currently calibrated for a compact minimum-width landing:
  one `GRID_SIZE.width()` artifact cell, compact Assignment/target rows with
  marquee text, and the fixed preset/current-equipment panel visible. Current
  calibration: Assignment panel width 144px, Assignment minimum hint about
  138px, target row button about 94px, and AppShell minimum about 1408px.
  Divmod/remainder adaptive fit is implemented from this calibrated minimum:
  the artifact viewport gets whole `GRID_SIZE.width()` columns and leftover
  remainder goes to Assignment width as a preferred/current width.
- AppShell minimum height/width must be top-level and state-independent, not
  derived from the currently visible `QStackedWidget` page. Artifact Browser
  target/no-target state hides different widgets and changes `minimumSizeHint()`;
  right-panel target sync can therefore make the window shrink below the fixed
  current-equipment/build-preview area unless AppShell owns a global minimum.
  Keep this as an explicit shell contract when adding new workspaces.
- Artifact/target/preset lists use overlay scrollbars. Artifact grid overlay
  scrollbar right-offset polish remains future work; keep it overlay-style so
  it does not consume layout width.
- New/reworked reusable UI pieces should take colors from `ui/utils/ui_palette.py`
  rather than adding local literal hex colors. Legacy QSS can be migrated later
  when touched; do not do broad style churn during functional fixes.
- `DragScrollArea` is reusable scroll mechanics plus edge chevrons/gradient only; the concrete caller owns the normal area background.
- Shared filter buttons use `ui/utils/filter_button_style.py`. Do not duplicate
  local QSS for filter button size, border, padding, hover, or checked states.
  AppShell character/weapon filters and Artifact Browser target filters should
  stay visually aligned through this helper.
- Qt QSS button sizing rule: `min-width`/`max-width` can act like content-box
  sizing. Border and padding may add to the real outer widget/content width. If
  a filter button must occupy an exact outer size, compute/pass a content size
  such as `outer - 2 * (border + padding)` and keep a test for hidden overflow.
- If a hover/checked ring, border, or icon is clipped on one side inside a
  scroll/layout strip, do not first change neighboring margins, z-order,
  spacing, or unrelated button padding. First measure the actual widget/content
  geometry: scroll `viewport()` size, `widget()` size, horizontal/vertical
  scrollbar maximum, and the button's real outer size. For `DragScrollArea`,
  `scroll.widget().width() <= scroll.viewport().width()` and scrollbar maximum
  zero are the key no-hidden-overflow checks.
- Hidden overflow in a scroll viewport can visually look like an unrelated
  neighbor overlaying the control. Prove overflow is zero before changing target
  rows, Assignment panel width, or AppShell minimum-size calibration.
- Assignment/target geometry changes must be narrow and measured. The artifact
  list minimum includes `GRID_SIZE.width() + ARTIFACT_GRID_FIT_PADDING`, the
  artifact-to-target gap is intentionally zero, and the target-to-build gap is
  the explicit `CONTENT_TARGET_BUILD_SPACING`. Do not reintroduce global content
  spacing that consumes the artifact list's padding/remainder.
- Resize twitch note: an isolated PySide probe reproduced the live-resize twitch
  outside the app, and the effect varies by monitor/system refresh behavior.
  Treat it as system/environment behavior for now; no active AppShell workaround
  is planned.
- Behavior depends on selected build target:
  - selected target exists: equip/apply actions can target that
    character/slot;
  - no selected target: browse-only mode; it must not implicitly equip or apply
    artifacts/builds to anyone.

### GCSIM Workspace

- GCSIM Browser MVP exists as a left workspace in AppShell. It can prepare
  account-backed configs and run selected or three-chamber dev flows through the
  backend GCSIM bridge.
- Browser runtime results may update compact right-panel Sim DPS cells, but they
  are not durable saved history. Treat them as current-session runtime results
  until immutable run snapshots/history are implemented.
- Normal GCSIM Browser belongs to `live_run`: it uses the current live-run teams
  selected in Characters/Weapons or Artifact Browser, and it updates summaries
  on the shared live-run right panel through controller state.

### PvP Workspace

- The first real PvP AppShell integrations are Decks v0, Play/local setup v0,
  and Draft board v0 with stable left workspace id `pvp`.
- When `pvp` is active, root AppShell switches the right operations dock to
  `Decks` / `Play` / `Draft` page controls. Abyss / DPS Dummy controls and normal
  TeamBuilder mutations are hidden while PvP pages are active.
- Account / Data remains the global right-dock action in the same header
  position. Opening Account from PvP preserves the PvP right-dock policy until a
  normal workspace is selected again.
- `ui/pvp_browser/` owns the left/main PvP workspace: deck browser grids, draft
  board, and main PvP scenes. MVP build stages host a restricted
  `CharacterWeaponWorkspace` subclass backed by a seat-scoped
  `AppShellController`; it changes the available assets/provider, not the
  normal quick-pick or weapon-assignment behavior.
- `ui/right_panel/pvp/` owns PvP mode routing and Draft/build commands. For MVP
  build stages it exposes the normal `RunRightPanelWidget` for each scoped PvP
  run context and provides only seat headers, collapse/Ready state, and routing
  chrome. The custom right-panel target-slot imitation has been removed from
  the accepted path.
- `PvpWorkspace` owns separate Decks, Play, and Draft left pages.
  `PvpDecksWorkspace` shows account characters/weapons, supports deck view/edit
  mode, and persists presets through `run_workspace/pvp/deck_preset.py`; Play
  selects two local deck presets and starts an in-memory `FreeDraftController`;
  Draft renders the backend board projection and sends legal pick/ban card
  clicks through the controller.
- In the target PvP flow, `Draft` is the active match container. Internal match
  stages should live inside Draft: Pick/Ban, Assignment, Weapon assignment,
  Artifact equipment, optional PvP GCSIM, Timers/results, and Completed
  result/export. Do not add top-level Team/Timers/Result/Artifacts/GCSIM PvP
  header tabs unless a later product decision changes this.
- PvP Decks character/weapon selection grids also use the shared painted icon
  grid. Preserve edit-mode viewport tint, selected outlines, inactive overlay,
  custom tooltips, overlay scrollbars, and stable test helper handles instead
  of depending on QLabel child widgets.
- Draft v0 wires the first real local pick/ban board, but normal
  TeamBuilder/Run state is still not mutated.
- PvP Assignment/Weapon/Artifact/GCSIM build stages remain PvP-owned in scope
  and must not mutate the normal TeamBuilder/Run state automatically. They
  should use a separate scoped `RunSessionController` / `TeamBuilderState` plus
  scoped equipment database/provider, not a duplicate PvP slot model.
- Detailed PvP UI mode/stage direction lives in `PVP_UI_ROADMAP.md`; this
  AppShell plan owns only the shell/workspace/right-dock coordination boundary.

### History Workspace

- Minimal left workspace exists with stable id `history` and is implemented
  through `ui/history_browser/`.
- `ui/app_shell.py` should only wire/register the History workspace, update its
  nav label, and coordinate the History right-dock policy. History browsing UI
  belongs in the History Browser module; `ui/right_panel/history/` owns only its
  adapter/host/read-only policy. The selected snapshot must be shown by a
  separate instance of the shared mode-specific Run presentation, not by a
  History-owned copy of its team/slot/details/chamber widgets.
- Legacy `runs_history.json` / image-path history UI is obsolete and should not
  become the long-term design.
- The current left page reads immutable snapshot bundles from disk, shows
  grouped saved-run rows, and supports saved-row selection. Selection adapts
  the frozen bundle into an isolated read-only instance of the shared Run
  presentation; the independent details widget and permanent PNG preview have
  been removed from normal browsing.
- The accepted MVP adapts a selected immutable snapshot into the same current
  right-panel view-model and presentation classes as live Abyss or DPS Dummy.
  This snapshot-bound instance is read-only: slot inspection, scrolling, and
  tooltips remain available; mutation, drag/drop, equipment, and commands do
  not. Mode tabs and Reset/Save are hidden, timers and saved state controls are
  disabled, and command-only controls such as GCSIM Run are hidden.
- History-specific metadata stays in the left browser. That browser owns
  internal Abyss/DPS Dummy tabs, defaults to the current live mode, groups
  Abyss runs by period, and orders new records first. Exact period headers and
  compact row content are defined in `docs/handoff/HISTORY_BROWSER.md`.
- Entering History must not reset, clear, or reinitialize live Abyss/DPS/PvP
  session state. Leaving History for a normal workspace restores the live Run
  panel and its previous state.
- Real History browsing belongs on the left as a workspace/tab. The right dock
  may later expose a compact History command, but it should route to the left
  workspace and active run type, not open the old floating history window as
  the final behavior.
- Complete per-slot snapshot/assets, shared read-only presentation, browser-row,
  and future export rules live in `docs/handoff/HISTORY_BROWSER.md`.

## Right Operations Dock

Current default:

- Build/Run Panel based on `ui.right_panel.live_run.panel.RunRightPanelWidget`.
- PvP Decks/Play/Draft right pages are under `ui/right_panel/pvp/`; the left
  workspace remains under `ui/pvp_browser/`.
- Fixed width.
- Always visible in the normal app shell.

Future operation modes:

- Account/Data owns HoYoLAB import/update, offline profile actions, language
  selection, and the DPS settings subzone. Current DPS setting: persistent
  Abyss Fact DPS multi-target HP toggle, default off/solo-target.
- Account/Data and similar global pages belong to `ui/right_panel/settings/`;
  opening them must preserve the current live-run, PvP, or History state.
- Real PvP draft/deck/opponent controls wired to the Free Draft board/read-model
  contract.
- Build panel after PvP draft when a buildable pool/team exists.

The right side is an operations dock, not only a build widget. Future
workspace-specific right pages and controls should be selected through root
AppShell coordination, while global actions such as Account remain present.

## Selection And Artifact Browser Rule

- The right panel/controller owns or displays the current selected build target.
- Clicking an already-selected character/slot again should clear that selection.
- Artifact Browser must check selected build target through shared
  controller/state:
  - if target is `None`, it must not equip/apply anything;
  - if target is set, equip/apply actions can target that character/slot.
- Do not couple Artifact Browser directly to right-panel widgets. Use shared
  state/controller signals or a narrow adapter.
- Detailed Artifact Browser equipment UX lives in
  `docs/handoff/ARTIFACT_BROWSER_EQUIPMENT_UX.md`.

Target/equip-mode contract:

- if the right panel has a selected character, that character is the Artifact
  Browser operation target and is first synced as the browser's single selected
  character so presets appear immediately;
- if the user deselects that character in Artifact Browser, browser selection
  clears for preset browsing, while the right-panel target remains as a
  secondary operation-target marker for free artifact clicks;
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
- current equipment is shown as a top current-equipment zone, not as an
  `artifact_build` preset;
- clicking a preset previews/selects it only, while the apply-preset action is
  the explicit write action.

Future weapon move/swap rule:

- persistent weapon equipment already validates `weapon_fingerprint` assignment
  counts against `known_count`;
- future weapon panel UI should support explicit move/swap from a named current
  owner when all known copies are assigned;
- do not silently steal an exhausted assigned weapon by fingerprint without an
  explicit source owner/copy choice.

## Timer / Run Logic

- Timer remains visually in the right operations dock/build panel.
- Durable timer/run/session logic should move toward typed `RunSessionState`,
  `AbyssRunState`, `DpsDummyRunState`, and a `RunSessionController` or
  equivalent model/controller layer.
- The right panel should display and command timer state, not own persistence or
  durable run/session logic.
- Current AppShell status: Abyss T1/T2 cells in the compact chamber table are
  editable in memory. They use separate minute/second segments inside one
  compact visual `MM:SS` field. Segment input stays raw until commit; Left/Right
  moves between segments, while wheel and Up/Down step the active segment.
  The chamber table keeps fixed compact T1/T2 widths and groups future Fact/Sim
  DPS columns under two-level headers so long labels do not widen the fixed
  right dock. Keep the current Fact DPS left boundary stable: future timer
  polish must fit inside the `Ch + T1 + T2` budget, while Fact/Sim columns keep
  enough width for readable six-digit values. `AbyssTimerState` and
  `calculate_abyss_chamber_result(...)` to derive elapsed seconds and Total.
  T2 follows the same chamber's T1 until T2 is manually edited; if T1 is edited
  below the current T2 value, T2 clamps down to T1 and returns to follow mode.
  Fact DPS reads cached Abyss source-data and uses Account/Data's solo/multi HP
  mode setting. The RUN Reset command resets the active typed live mode only;
  the RUN Save command persists immutable snapshot bundles for the active run
  type. History browsing/opening commands and durable saved-result GCSIM
  integration remain future work.
- Detailed next-stage contract lives in
  `docs/handoff/RUN_WORKSPACE_SNAPSHOT_CONTRACT.md`. Follow it before coding
  History or GCSIM.
- Later implementation should inspect and reuse useful parts of:
  - `ui/widgets/timers.py`
  - `run_workspace/models.py`

Preserve useful behavior such as wheel-friendly timer editing and validation,
but do not preserve the old right panel as the final owner of run state.
Saved runs must be immutable structured snapshots for Abyss and DPS Dummy, not
live references to account/build state and not image-only legacy records.
Factual DPS belongs in pure run/session result code near `run_workspace.models`
or a future `run_workspace.results` module. GCSIM sim DPS remains a separate
result kind: Browser MVP runtime results may update current UI state, while
durable saved results must later attach through explicit session/snapshot data.

## Legacy Plan

- `ui/main_window.py` becomes legacy once `AppShell` is introduced.
- The old right panel should not be preserved except for useful timer/run logic.
- Old history is obsolete and should be replaced later, not migrated as the
  future design.
- Delete/cleanup legacy code only after the new shell is stable and the user has
  approved the cleanup stage.

## PvP Direction

- PvP now has AppShell Decks, Play, and Draft workspace/right-dock policy, not a
  separate first window.
- PvP right-panel code belongs under `ui/right_panel/pvp/`; `ui/pvp_browser/`
  should keep the left/main PvP workspace, deck grids, draft board, and source
  pools.
- Detailed PvP current/target UI direction lives in `PVP_UI_ROADMAP.md`.
- During draft/deck/opponent phases, showing the normal build panel can be
  misleading because builds may not be editable yet.
- Once the match reaches build stages, the right operations dock shows the
  normal `RunRightPanelWidget` for the scoped PvP run context plus compact
  PvP-specific commands. Do not add a second PvP team/slot-card hierarchy.
- Pick/Ban, Assignment, Weapon assignment, Artifact equipment, optional PvP
  GCSIM, Timers/results, and Completed result/export controls should be internal
  Draft-stage controls, not extra top-level right-header pages.
- Once draft/pool/team is ready, the whole normal build pipeline should be
  reused against the PvP scoped roster/database instead of the full account
  roster. Reuse means the same quick-pick markers, selected-target behavior,
  weapon filtering, Artifact Browser operation-target behavior, GCSIM Browser
  behavior, and `RunRightPanelWidget.set_model(...)` path.
- PvP profile import/export is backend-owned by `run_workspace/pvp/`. Decks
  exposes package export; Play exposes import and return-to-local actions per
  seat. Import selects an imported provider and never restores profile data
  into the main app database.
- PvP artifact equipment is target product direction. Local players should read
  shared artifact source data without duplicating the whole local DB, while
  artifact equipment choices and newly created PvP runtime state stay scoped to
  the active match/seat. Imported/remote players read source data from their
  package/provider. None of these paths may mutate the main Artifact Browser,
  normal account artifact state, or live-run builds. Prefer reusing Artifact
  Browser logic through a scoped PvP adapter/session rather than forking a
  second browser.
- PvP can expose GCSIM through a button/action inside Draft/build flow, routing
  to a scoped PvP GCSIM stage/panel using PvP teams/builds. It should not add a
  separate top-level PvP GCSIM Browser tab or use normal live-run teams.
- PvP training runs can later save history scoped to the current deck/PvP mode.

## Current AppShell Status

Current development entrypoint:

```powershell
.\.venv\Scripts\python.exe -m ui.app_shell_smoke
```

`main.py` still launches the legacy app until the production switch is explicitly
approved. When that switch happens, `main.py` must run the same startup adaptive
scaling bootstrap as `ui.app_shell_smoke` before constructing `QApplication`.

Current interaction rules:

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
- The right panel is refreshed through `RunRightPanelWidget.set_model(...)`
  after controller state changes.

Equipment-state note:

- Persistent equipment-state design lives in
  `docs/handoff/ACCOUNT_EQUIPMENT_STATE_DESIGN.md`. Schema/service helpers are
  implemented in `hoyolab_export/account_equipment.py`; AppShell weapon
  persistence, current artifact snapshots, Artifact Browser equip/apply, and
  owner side icons are wired. Equipment is per character, not per right-panel
  mode.
- Future equipment UI work should focus on richer explicit move/swap source
  choice when a weapon fingerprint has no free copies. If character A equips an
  item worn by B, the service layer supports move/swap resolution when the
  source owner is explicit.
- Build presets are definitions, not current equipped state. Equipping a preset
  should be an explicit action for exactly one character, copying that preset's
  artifacts into that character's current equipped state; if the preset has
  missing slots, those target slots are cleared so current equipment matches
  exactly what the preset shows. Later manual equipment changes must not mutate
  the preset itself.
- Artifact Browser remains browse-only when no build target is selected. With a
  selected target, explicit equip/apply actions may modify current equipped
  state through `account_equipment`.
- AppShell embeds Artifact Browser as the `Artifacts` left workspace. The
  browser is created lazily on first switch, reflects the right-panel selected
  operation target through browser target selection/highlight plus the
  current-equipment zone, and falls back to exactly one browser-selected
  character target when the right panel has no target. Artifact clicks can
  equip/unequip the operation target, and preset apply writes the selected
  preset into current equipment without mutating the preset definition.
- Embedded Artifact Browser keeps standalone window-resize behavior disabled
  and is calibrated for a compact one-artifact-cell minimum layout: target rows
  use `MarqueeButton` with a reserved portrait/icon zone and marquee text only
  in the name area, Assignment is narrower than the previous 180/238px
  calibrations, JSON import/clear buttons do not force the artifact viewport
  wider than one `GRID_SIZE.width()` cell, and the fixed preset panel remains
  visible. Divmod/remainder adaptive fit is implemented and must keep Assignment
  expansion as a preferred/current width, not a propagated minimum.
- JSON import/clear controls are compact at one artifact column and expand only
  at 2+ columns. They must not reintroduce an artifact viewport minimum wider
  than one grid cell.
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
  roughly `1-2 ms` building the right-panel view-model. `RunRightPanelWidget`
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

- `CharacterWeaponWorkspace` now keeps character/weapon browser items in one
  painted `PixelIconGrid` per grid instead of QWidget-per-card layouts. Roster
  marker-only updates change item outline state on the grid instead of calling
  `reload_characters()`.
- Full grid reload remains reserved for real data/filter/layout rebuilds. Mode
  switches may sync visible marker item state, but do not reread SQLite or
  recreate child icon widgets.
- Earlier opt-in perf logs showed normal quick-pick marker refresh at about
  `0.0-0.2 ms` for one affected card, and mode-switch full marker sync at about
  `0.7-0.9 ms` for 73 visible cards. `filter_characters` no longer appears in
  the marker-only click path. Re-run perf logs if the painted-grid migration is
  being tuned further.
- Roster clicks update marker state first, request repaint, and schedule a short
  debounced right-panel refresh. Rapid clicks coalesce into one later
  `RunRightPanelWidget.set_model(...)` call.
- Character and weapon asset items are cached for the AppShell session. A future
  import/data refresh can explicitly clear this cache, but ordinary filter
  clicks should not reopen SQLite.
- `PixelIconGrid` prepares pixmaps through `ui/utils/hidpi_pixmap.py` outside
  paint events, with cache keys covering source path, target size, physical
  size, DPR, mtime/size, and visual key parts. Marker-only updates do not reload
  or rescale pixmaps.
- High-DPI PNG rendering is an AppShell/current UI contract, not a layout
  contract. Keep widget sizes in logical/design pixels and render raster assets
  at physical `logical_size * effective_dpr`, then set the pixmap DPR. The
  startup small-monitor `QT_SCALE_FACTOR` downscale remains startup-only and
  must not double-shrink PNGs; effective pixmap DPR is clamped to at least
  `1.0`. New visible raster UI work should go through
  `ui/utils/hidpi_pixmap.py` or helpers built on it, and generated/persistent
  visible pixmap cache keys must include DPR/physical size plus source identity
  and visual parameters. Legacy `main.py` remains outside this first migration
  unless a later task explicitly includes it.
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
- Right-panel bounce root cause and prevention:
  - The visible bounce was not one bug. It was a chain of layout and refresh
    problems that only became obvious under realistic click timing.
  - First cause: right-panel team/slot area used destructive rebuilds in
    `RunRightPanelWidget.set_model(...)`. Clearing `_teams_layout`
    temporarily removed the slot area, so the chamber/timer block could visually
    jump upward. Fix: keep persistent team/slot widgets for same-structure
    updates and update slot contents in place.
  - Second cause: selected-details rebuilt its whole layout and recreated the
    bonus strip when selected character data changed. Set-bonus icon appearance
    made this especially visible. Fix: use a stable selected-details skeleton,
    persistent stats/meta/weapon/CV areas, and a persistent
    `BonusSourceStripWidget` with in-place item updates.
  - Third cause: add-character fast path and deferred persistent-equipment
    hydration could produce two visible right-panel states: minimal selected
    details first, hydrated details later. Fix: do not show the intermediate
    minimal details refresh for newly added characters; let the marker update
    immediately, then refresh the right panel after hydration.
  - Fourth cause: stale pending right-panel refresh timers from earlier actions
    could fire between a new fast state change and hydration. Fix: when scheduling
    persistent equipment hydration for an added character, cancel any pending
    right-panel refresh first so stale timers cannot draw a half-updated model.
  - Fifth cause: removing the selected character switched selected details from
    selected mode to empty mode and changed details size hints. Under narrow
    timing this caused a final small flash around the chamber/slot area. Partial
    fix: after selected details have been shown once, remember the selected
    height and keep that minimum height even in empty mode.
  - Final trace finding: the remaining remove-bounce was a one-frame layout
    settle issue. In the failing trace, right after `set_model(...)` the chamber
    block was at the wrong y-position, then the next event-loop tick (`settled`)
    returned it to the correct geometry. Synchronous layout activation alone did
    not guarantee the first visible frame used the settled geometry.
  - Final fix: keep the stable teams/details geometry guards, call the content
    layout settle helper, and delay repaint re-enable until the next event-loop
    tick. In practice this means disabling updates during right-panel
    `set_model(...)`, then using a zero-delay timer to settle layout again,
    re-enable updates, and repaint only after Qt has reached settled geometry.
  - Future browser/panel rule: do not rely on fast repaint masking. Keep widgets
    owned by stable parent/layouts, update via state/content/visibility, avoid
    intermediate visible placeholder states during deferred hydration/load, and
    keep geometry stable when switching between selected/empty/hydrated modes.
    If diagnostics show different `after` vs `settled` geometry, guard painting
    until the settled tick instead of showing the intermediate frame.
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
- PvP post-draft source panels follow the same rule. Once Assignment/Weapons
  has created the scoped `CharacterWeaponWorkspace` source zones, clicks must
  update titles, markers, filters, and grids in place. Do not detach source
  workspaces, clear the whole scroll layout, or rebuild the post-draft source
  frame on every character/weapon/slot action; that reproduces the old
  live-resize/blank-window twitch failure under a different left-panel path.
- PvP post-draft refresh should also preserve the AppShell signal cadence. A
  source click, weapon click, slot select, or slot drop changes build state, not
  the active draft identity, so it should emit one state refresh. Do not emit
  both `active_draft_changed` and `state_changed` for those actions, and do not
  refresh both player `RunRightPanelWidget` instances when only the active seat
  changed. The fixed path updates the active seat in place and reserves all-seat
  refreshes for initial creation or stage changes.
- Artifact Browser cold-start audit status:
  - Baseline after target-filter optimization was about `356 ms` total, with
    store load around `110 ms`, target item loading around `46-48 ms`, and UI
    construction around `178-180 ms`.
  - Embedded Artifact Browser no longer raises the whole AppShell minimum size on
    first open; setting the embedded browser size policy to ignore vertical
    minimum hints removed the visible `1408x820 -> 1408x850` resize twitch.
  - Target character asset items now reuse the already-loaded Character/Weapon
    workspace session cache when the embedded Artifact Browser is created. This
    removed the second SQLite target asset pass and reduced `targets` to roughly
    `7 ms` in the measured cold open.
  - Remaining cold cost is intentional and loader-ready: SQLite artifact store
    load plus one-time creation of about 74 target buttons (`ensure ~100 ms`).
    Do not add persistent bake/cache before the loader pass just to hide this;
    keep it measurable until the future loader/cache pass.
- Startup loader + persistent cache/bake work is intentionally later and mostly
  pre-release. Until that loader pass, keep remaining cold-start/stutter sources
  visible and measurable so bad synchronous paths are easy to find and fix.
  Do not add persistent caches just to hide current lag while the UI is still
  being actively optimized.
- Recent AppShell click-path profiling with Abyss timers and Fact DPS visible
  found that the immediate roster marker path is still fast (`~2-3 ms` per
  click). The remaining loader/prewarm candidates are deferred work: the first
  selected-character weapon auto-filter can still load weapon assets from SQLite
  (`~140-150 ms` cold sync), later cached weapon-filter grid rebuilds can cost
  `~15-40 ms`, and selected-details/bonus-strip right-panel refreshes for
  equipped characters can spike around `~50-66 ms`. Treat these as future
  loader/cache/prewarm candidates unless they become a visible current bug.
- When the loader pass starts, mark every loader-covered subsystem explicitly
  and bake/cache repeatable work in the same pass. Candidates include Artifact
  Browser cold-start store/init data, target/preset UI preparation,
  preset-edit controls, Character/Weapon workspace weapon asset/filter prep,
  reusable weapon grid card pixmaps/widgets where safe, pixmap/text/marquee
  caches, right-panel selected-details/bonus-strip pixmap prep if needed, and
  bulk persistent equipment/negative-cache prewarm for account characters. After
  that point, second and later openings should reuse baked/cache data where safe.
- Future right-panel slot drag/drop is feasible because `TeamBuilderState`
  already supports whole-slot swap/move across teams. The UI should drag a full
  slot payload, not just a portrait, so weapon/artifact/details move together;
  resonances and team bonuses must be recalculated from the post-drop team
  composition rather than copied as slot data.

Sizing note:

- AppShell uses a fixed `RightOperationsDock` width from the reduced right-panel
  content width (`660px` at the time of writing).
- The dock is not user-resizable and must not expand when the outer window gets
  wider; the left workspace receives extra width.
- The Character/Weapon workspace uses project overlay scroll areas around its
  painted character and weapon grids so native vertical scrollbars do not
  reserve layout width or shift grid content.

## Current Implemented Areas

- `run_workspace/session.py` owns typed live-run session state: active mode,
  per-mode `TeamBuilderState`, selected team/slot, external bonus state, Abyss
  timers/T2 follow flags, compact runtime GCSIM chamber results, and active-mode
  Reset.
- `AppShellController` remains the UI/account/equipment adapter and right-panel
  view-model coordinator until the right-panel source-ownership refactor moves
  widgets into `ui/right_panel/`.
- `LeftWorkspaceHost` uses stable workspace ids through root AppShell. Current
  workspaces are Character/Weapon, lazy-created Artifacts, GCSIM Browser,
  `ui/history_browser/`, and PvP Decks/Play/Draft.
- Artifact Browser embedded/content mode exists as the `Artifacts` left
  workspace. It preserves standalone browser construction, respects selected
  target/no-target browse-only rules, and routes equip/apply through
  `account_equipment`.
- RUN-page Save stores immutable grouped `HistorySnapshotBundle` records through
  `run_workspace/history_snapshot_builder.py`. The History workspace can
  read/list saved bundles and select records through an isolated read-only
  `RunRightPanelWidget`. Snapshot v2 captures display details for every occupied
  slot and production Save materializes declared visible assets inside the
  bundle without changing live team state. The next stage is the contracted
  History tabs, period groups, and compact visual rows.
- GCSIM Browser runtime output may update current-session Sim DPS rows, but it
  is not durable saved history until explicit session/snapshot attachment is
  implemented.

## Implementation Guardrails

- Do not patch the old main-window right column as the future architecture.
- Do not copy `ui/right_panel_prototype_smoke.py` builders into production.
- Do not save future runs from live widgets or image paths.
- Do not make Artifact Browser equip/apply anything without an explicit selected
  build target.
- Keep source-ownership refactors separate from new feature behavior unless the
  user explicitly asks for that broader stage.
