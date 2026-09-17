# History Browser Contract

Scope: authoritative product and architecture contract for the AppShell
History Browser.

<!-- handoff-current: history-browser -->
Reviewed 2026-09-17: the user likes v6 compact and approved v7's portrait-based
team identity. Splash-art download research was explicitly cancelled: do not
implement or queue it. History now uses side icons for character slots and a
front portrait of the first occupied slot for the team picture. The comparison
setting and its AppShell signal were removed; obsolete saved values are ignored.

V7 expansion replaces the wide team header with a left identity panel, large
bonuses and a team timer aligned beside the three room results. Character/stat
columns are denser; the overall header/total stays dominant. The saved
444-second run is 666px tall at width 1220 (previously 770), 706px at 864;
below 800, two columns preserve readability (1186px at 720). PNG is 1600x888.
Compact geometry remains 120/180/220px at 1220/864/720, with whole-run zebra,
one total column and no DPS. Expanded/export/right-panel DPS remain.
The final header moves the bare total left and centers `Abyss · 12` above a
14px month range (`9.2026–10.2026`), without the save timestamp. It never invents
a missing/invalid period end; the old fixture displays `8.2026`.

Side icons reuse ArtifactCardDelegate's untrimmed calibrated canvas and shared
owner-badge face ratio. A common bottom anchor allows hats above the text/card
edge instead of shrinking faces individually. Bonus variants use alpha >64
bounds to exclude faint Pyro glow from sizing; 30px compact/32px expanded cells
now scale visible content consistently. Source files remain unchanged.

Artwork hover offers upload/reset; an export-bar menu provides keyboard access.
The override belongs only to this saved record/team and survives restart/source
removal. It is stored under `data/history/presentation`, never in immutable
snapshot JSON; export includes it without hover controls. See the stable
presentation-asset boundary below.

All 19 focused automated checks passed (ten cards, four AppShell, five HiDPI).
The subsequent header-only edit passed render and month-range edge checks.
Native verification reached the real History compact list, then was stopped
because the app was being used concurrently. The user explicitly postponed
upload/reset/export/restart checks. They remain unverified through the real UI;
automated tests and rendered PNG are not substitutes. Details and resume steps
are in the [v7 evidence](../design/history/README.md). Next: review the final v7 corrections
in [TODO](../../TODO.md). No full locale/monitor matrix, real DPS Dummy save,
or frontend migration is implied.

One pre-contract 2026-06-13 bundle is v1, rejected by the existing v2 reader;
the top unreadable-snapshot count remains visible and the file was preserved.
Normal browsing has no permanent PNG preview and generates no PNG on selection.
<!-- /handoff-current -->

## Ownership And Boundaries

- History is a left AppShell workspace with stable id `history`.
- History is not a floating legacy window and not a right-dock-only page.
- `ui/app_shell.py` owns workspace routing and right-dock page selection only.
  History browsing belongs under `ui/history_browser/`.
- `ui/right_panel/history/` may own the snapshot adapter, host, empty state, and
  read-only policy. It must not own parallel copies of Run presentation widgets.
- `ui/run_history_window.py` and `runs_history.json` are obsolete and must not
  become the final History model.
- Opening History automatically reloads the configured immutable snapshot root without
  resetting or rebuilding the live Abyss/DPS Dummy/PvP session.
- History never reads current account equipment, Artifact Browser presets,
  account/profile data, DBs or network state to reconstruct saved run facts.
  Character slots use bundle-local side icons, falling back to portraits only
  when absent. Team art uses the first occupied slot's front portrait. There
  is no longer a user-facing Profile/Portrait comparison setting.
- The Abyss period navigator may read production Floor 12 source-data caches
  for its period catalog and enemy preview only. A selected saved-run row and
  its right panel use only frozen snapshot fields and bundle-local assets.

## Shared Right-Panel Presentation

- Selecting an Abyss snapshot creates or updates a separate instance of the
  same Abyss Run presentation class/component tree used by the live pipeline.
- Selecting a DPS Dummy snapshot does the same with the normal DPS Dummy Run
  presentation.
- Separate instance means separate widget state and ownership; it does not mean
  a separate simplified History implementation.
- History must not create parallel team-slot, selected-details, chamber-table,
  timer, build, or result widgets. It adapts frozen snapshot data into the same
  current shared right-panel view-model consumed by the live presentation.
- Snapshot JSON stores domain/display facts, not QWidget instances or a
  serialized copy of a particular UI view-model version. Old saved data is
  displayed by the current shared presentation design.
- History-specific metadata such as save date, period, and bundle identity is
  shown in the left browser row/group, not as a wrapper above the shared right
  panel.
- Before a saved row is selected, the History right-dock page may show a small
  localized empty prompt. After selection, the shared snapshot presentation is
  the right-dock content.

## Read-Only Policy

History presentation allows inspection but no mutation:

- select a frozen character slot to inspect its saved details;
- initialize selection to the first occupied slot;
- allow scrolling and saved-data tooltips;
- disable slot drag/drop and all equipment/build mutation;
- render saved Abyss timers with the same timer widgets and geometry, but keep
  their editors disabled;
- show saved state controls, such as the external-bonuses state, disabled;
- hide command-only controls such as GCSIM Run;
- hide the right-panel mode tabs because the selected snapshot fixes the mode;
- hide the bottom live Run Reset/Save action row;
- never emit commands into the live `RunSessionState`.

Changing selected slots inside History changes only History-local inspection
state. Leaving History restores the live Run presentation and its previous
teams, selection, timers, results, and settings unchanged.

## Left Browser MVP

- The right-dock header exposes History-local `Abyss`, `DPS Dummy`, and `PvP`
  mode buttons plus Account. They use a separate History signal and never
  invoke live Run or live PvP routing.
- Account opened from History keeps those History mode buttons visible; a mode
  button returns to History. PvP currently opens a localized History-only
  placeholder and does not read or mutate live PvP.
- Entering History defaults to the current live Run mode.
- Switching History mode or Abyss period clears the selected row/right snapshot.
- Within each section, newest saved runs are listed first.
- MVP navigation includes type tabs, Abyss period groups, and newest-first
  ordering. Character/DPS/set/warning filters and richer sorting remain later.

### Abyss

- The period catalog is the union of immutable snapshot periods and readable
  cached `floor_12.json` periods. It is newest-first, cache-only periods remain
  selectable with empty run lists, and unknown snapshot periods sort last.
- The initial period is the current cached period when available, otherwise the
  newest catalog period. Selection is History-local and never rewrites the live
  period file or Run Session.
- The top selected-period zone always shows C1/C2/C3 with Side 1/Side 2,
  compact local enemy icons and total HP per side. Enemy tooltips show saved or
  cached name, level, count, wave, and individual HP.
- A full-width period dropdown below that zone shows date range, floor, and run
  count. Invalid/too-short end dates are omitted rather than inferred.
- Cache data is preferred for this period preview; latest snapshot enemy data
  is the fallback. Saved-run rows never borrow cache/account assets.
- Each compact row has two dense team strips, four characters horizontally per team
  at normal panel width (two columns below 680 design pixels),
  weapon/refinement and set/count icons, main-stat shorthand, team bonuses,
  completion seconds and all three chamber result blocks.
- Compact scale is a height budget, not a scaled-down expanded report: at the
  864px reference viewport, target <=180px for an ordinary two-team run. A head
  occupies essentially the full 44px character strip; adjacent equipment is
  slightly smaller and C stays beside the name. At sufficient width, reclaim
  horizontal gaps for right-hand timers (ordinary run <=140px tall
  at 1220px). The narrower fallback uses a separate results strip. Extra height
  is reserved for genuinely narrower content or additional set information.
  Title/date are expanded/export-only; the period navigator already owns them.
- Compact adjacent runs alternate background brightness, not the two teams
  inside one run. A shared total-time column visually binds the whole record.
  Order team name, large bonuses, team time; put chamber times in one line.
  Overall total is the strongest time accent, then team time, then chamber time.
- Compact cards omit all factual/simulated DPS by explicit user decision.
  Expanded chamber blocks and PNG show saved time plus both DPS types when
  present; the frozen data and shared right-panel fields are unchanged.
- Row click (also Enter/Space) expands inline and loads the same snapshot on the
  right; repeating it collapses the card without clearing right selection.
  Opening a different row collapses the previous one. There is no expand arrow.
- Expansion replaces the compact composition inside the same widget; never
  append a second export report or duplicate character headers below it.
  On-screen layout uses readable font floors and maps painted hit regions back
  to widget coordinates when compensating sub-1 DPR. Expanded chamber results
  sit below the character grid; compact results use the width-dependent layout
  above, intentionally omitting DPS.
  Export scaling is separate from screen
  layout; PNG still shares the expanded painter and frozen data.
- The expanded composition stacks two teams. Each has a left identity/art panel
  with large bonuses and a team timer aligned beside room results, plus four character columns
  with level/C, weapon/R, sets, shorthand and overall stats, followed by a
  separate three-chamber band with frozen enemies/counts, seconds and DPS.
  It intentionally omits individual artifact pieces and precise timer editors.
  The report header centers the mode/floor and month-year period, with the
  unlabeled total at top left. It does not mix save date with the Abyss period;
  invalid/short ends are omitted, and no missing date is inferred.
- Side icons preserve the calibrated full canvas like ArtifactCardDelegate:
  the shared owner-badge size ratio defines a common face scale, with one
  bottom anchor and top overhang for hats. Never trim each side silhouette to
  fit independently; that reintroduces unequal heads. Front portraits/art may
  trim transparent margins and use a rounded cover crop. Bonus content uses
  alpha >64 bounds, ignoring faint glow, in both compact and expanded views.
  Loader cache keys include the threshold. These are prepared variants, never
  mutations of bundle files; no decoding or alpha scan occurs during painting.
- Soft team/element gradients, visible section/card borders, alternating stat
  rows and numeric separators distinguish the hierarchy. Overall total, team
  totals and room times lead; name/C sit above the smaller equipment beside
  the taller head. Two-set builds and enemy
  overflow reserve extra height; absent saved stats remain empty.
- Character hover uses a custom, non-activating, screen-clamped popup with
  weapon/character levels, C/R, frozen stats and sets over an element gradient.
  All card popups use the visible hover point through the opt-in shared
  `anchored_tooltip_rect` boundary; never anchor enemies to the whole card.
  Other `CustomTooltipPopup` callers keep their existing default placement.
  Scroll, collapse, hide, resize and export dismiss pending/visible popups.

### DPS Dummy

- Each saved-run row shows one visual team, target/setup summary and duration.
  Factual/simulated DPS appear in expansion/export, not compact mode.

Rows use frozen display data and copied bundle assets. Missing optional result
values use clear unavailable/not-run states, not raw ids, paths, or debug keys.

## Immutable Snapshot Requirements

Each occupied team slot must preserve enough frozen data to rebuild the full
shared read-only panel independently:

- character identity, display name, level, element, rarity, constellation,
  portrait, and side icon;
- weapon identity, display fields, level/refinement, visible stats, passive
  tooltip data, and icon;
- complete selected/current artifact build contents, active sets, set icons,
  visible stats, CV/proc values, warnings, and saved tooltips;
- saved detail rows and bonus-source state for every occupied slot, not only the
  slot selected when Save was pressed;
- scenario, chamber, timer, enemy/HP, factual DPS, and sim DPS data needed by
  the normal mode-specific panel;
- user-facing warnings plus internal provenance kept outside primary UI.

All visible portraits and icons required by History are copied into the bundle
when Save succeeds. Paths are bundle-local conveniences, never identity. A
saved run must remain visually usable after account data and caches are removed.

Existing pre-contract/dev snapshots are disposable. No automatic migration or
live-data repair path is required; implementation work may remove them before
validating the new contract.

## Export

### Per-record presentation assets

`run_workspace/history_artwork.py` owns optional user artwork separately from
immutable domain facts. The key hashes resolved bundle path plus bundle id;
each team has an atomically replaced PNG under
`data/history/presentation/<key>/team-<index>.png`. Moving the bundle changes
the decoration identity; portability/profile export of these overrides is not
implemented. No DB/account/network lookup occurs while browsing History.

`HistoryRunRowWidget` opens the local file dialog, validates PNG/JPEG/WebP
(32 MiB, 24 million pixels), applies EXIF orientation, bounds the long edge to
1600px and persists its own PNG copy. Cancelling or invalid input leaves the
previous image intact. Reset deletes only that team's override. Hover clicks
upload/reset without collapsing or reselecting the card; the keyboard menu
provides the same commands. Only left-card/export decoration changes; the
frozen right Run and live session remain read-only/unaffected.

- A permanent selected-run PNG preview is not part of normal History browsing.
- Expanded cards expose Save PNG with a native destination dialog. Export uses
  the same expanded painter, side icons and per-record team artwork, with no
  interaction chrome. Width is 1600px; height fits saved stats/enemy rows.
- `ui/right_panel/common/history_card.py` owns shared painting and custom hover;
  `run_workspace/history_browser_catalog.py` adapts frozen data/assets;
  `run_workspace/history_presentation.py` owns shared
  saved-build shorthand. Pixmaps are prepared outside paint/hover via the
  shared HiDPI path; selection does not generate an image or rebuild every row.
- The old text-first `history_snapshot_preview.py` remains a transitional
  utility and is not used by this browser/export path.
- Dedicated Preview/Share commands remain later work; inline expansion and
  explicit PNG save are already implemented.
- Structured XLSX/data export remains a later feature.

## Implemented Baseline And Remaining Scope

Snapshot Bundle v2 and production Save capture frozen display details for every
occupied slot and materialize declared visible assets inside the bundle without
retaining temporary hydration in live state. Grouped storage, row selection,
the snapshot-to-shared-right-panel adapter, isolated read-only Run panel, first
occupied slot selection, frozen slot navigation, disabled timers/state changes,
hidden commands, and removal of the permanent PNG area are implemented.

The v7 composition and saved-build formatting repair are implemented. The user
approved compact density and the portrait-based identity direction; final v7
corrections still need review. The rejected first pass,
v2, one-team study and oversized v3 compact report are historical references.
V7 visual review, fuller DPS Dummy
input capture, real PvP History, filters/sorting beyond newest-first and further
Preview/Share/data-export features remain open in TODO. Original concept and
actual app samples are distinct, linked references; neither implies acceptance
of untested data/layouts.
