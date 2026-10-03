# History Browser Contract

Scope: authoritative product and architecture contract for the AppShell
History Browser.

<!-- handoff-current: history-browser -->
Reviewed 2026-09-18: v10 keeps inline team/chamber timing from 960 logical
pixels, so a 1004px History workspace at 150% retains detail in its 976px inner
cards. Normal and 2+2 builds share the threshold. Both wide and narrow team
strips are 41px; an ordinary two-team run is 84 logical pixels high (126
physical pixels at 150%), down from v9's 104. Below 960px, secondary timers are
hidden without increasing row height. Four character columns remain through
560px; smaller cards switch to a bounded 2x2 layout. The independent 86px total
contains only the unlabeled compact overall timer.

The outer rounded card is now the actual team-row background. From 980px, a
centered 14px I/II allocation starts at its left edge, one vertical divider
follows it, and character content begins immediately after the divider. There
is no inset team band, marker rectangle or blank gutter. Markers still yield
before bonus data. Narrow bonus icons remain borderless in a separate 28px
two-high allocation, which disappears below 720px; inline bonuses are 18px.

Expanded identity no longer paints obsolete `01`/`02` badges or individual
bonus frames. Bonuses form an in-bounds grid of up to two rows with a bounded
`+N` overflow cell. The team label and timer are centered in their shared
panel. V8 period/boss controls, one-line header, warning classification,
calibrated assets, tooltip containment, export and snapshot isolation remain
unchanged and are specified below.

Fifteen focused History-card checks and four AppShell History checks pass,
including 520/560/704/960/980px responsive geometry, 4p/2+2 layouts and bounded
expanded bonus overflow. Direct hidden Qt renders cover the 704px workspace,
the 1004px workspace/card at 150%, and the 520px fallback. The real app was not
taken over while the user was using it, so the actual click path and visual
acceptance remain open, along with upload/reset/export/restart. See
[v10 evidence](../design/history/README.md) and [TODO](../../TODO.md).
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

- The period catalog remains the union of immutable snapshot periods and
  readable cached `floor_12.json` periods, newest-first with unknown snapshot
  periods last. The History selector exposes only periods with saved runs;
  cache-only zero-run periods remain catalog metadata and do not create empty
  menu rows.
- The initial visible period is the current cached period only when it has a
  saved run, otherwise the newest run-bearing catalog period. Selection is
  History-local and never rewrites the live period file or Run Session.
- One accent heading is both the full-width period selector and period label,
  using `Abyss 12 · 9.2026–10.2026` month-range formatting. It does not consume
  a second metadata row. Invalid/too-short ends are omitted rather than inferred;
  menu entries add the saved-run count.
- An adjacent localized Show bosses toggle owns C1/C2/C3 enemy details. They
  take no height while collapsed. Expanded details use one horizontal group per
  chamber: a fixed room badge, two half-rows of enlarged local enemies, and a
  styled total-HP pill at the right. Tooltips retain saved/cache name, level,
  count, wave and individual HP.
- Cache data is preferred for this period preview; latest snapshot enemy data
  is the fallback. Saved-run rows never borrow cache/account assets.
- Each compact row has two dense team strips, four characters horizontally per team
  from 560 design pixels (two columns below that boundary),
  weapon/refinement and set/count icons, main-stat shorthand and team bonuses.
- Compact scale is a height budget, not a scaled-down expanded report. At the
  864px/RDP viewport an ordinary two-team run is 84px: one 36px character row
  inside each 41px team strip and no secondary results rows. The shared column
  keeps a clean rectangular overall timer and an independent, borderless
  resonance allocation with up to two vertically stacked icons per team. That
  allocation disappears as a unit below 720 design pixels. From 980px a
  centered 14px `I`/`II` allocation occupies the outer rounded card edge; one
  divider leads directly into the character grid, with no inset band or gap.
  It yields before resonance data. From 960px, both 4p and 2+2 layouts retain
  inline team totals and three chamber times in the same two 41px team strips,
  keeping the full card at 84px.
  Truly two-column widths may reserve extra character height, never an empty
  results band.
  Title/date are expanded/export-only; the period navigator already owns them.
- Compact adjacent runs alternate background brightness, not the two teams
  inside one run. A shared total-time column visually binds the whole record.
  Wide mode orders borderless bonuses and team time after the optional left
  Roman marker, with chamber times on one line. Overall total is the strongest
  time accent. Narrow mode keeps that clean total and its separate borderless
  resonance allocation; Roman markers are omitted first.
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
  sit below the character grid; wide compact results use the inline layout,
  while narrow compact intentionally omits all secondary results and DPS.
  Export scaling is separate from screen
  layout; PNG still shares the expanded painter and frozen data.
- The expanded composition stacks two teams. Each has a left identity/art panel
  with a borderless bonus grid and centered team timer aligned beside room
  results, plus four character columns
  with level/C, weapon/R, sets, shorthand and overall stats, followed by a
  separate three-chamber band with frozen enemies/counts, seconds and DPS.
  It has no numeric team badge, intentionally omits individual artifact pieces
  and precise timer editors, and keeps excess bonuses inside at most two rows
  plus an in-bounds overflow cell.
  The report header uses one row: unlabeled total at top left, mode/floor in the
  center and month-year period at top right. It does not mix save date with the
  Abyss period; invalid/short ends are omitted, and no missing date is inferred.
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
retaining temporary hydration in live state.
New saves may carry a second frozen character image for expanded cards:
background plus portrait, without element or constellation. Compact/team art
keeps its original portrait, and old bundles fall back when the optional
expanded reference is absent. Both files are copied into the immutable bundle.
The History right panel also uses the expanded variant when present.
Grouped storage, row selection, the snapshot-to-shared-right-panel adapter,
isolated read-only Run panel, first
occupied slot selection, frozen slot navigation, disabled timers/state changes,
hidden commands, and removal of the permanent PNG area are implemented.

The v10 responsive composition and saved-build formatting repair are implemented.
The user approved the preceding wide compact density and portrait-based identity
direction; the corrected narrow/RDP mode, one-line headers and collapsible boss section
still need real-app review. The rejected first pass,
v2, one-team study and oversized v3 compact report are historical references.
V10 visual review, fuller DPS Dummy
input capture, real PvP History, filters/sorting beyond newest-first and further
Preview/Share/data-export features remain open in TODO. Original concept and
actual app samples are distinct, linked references; neither implies acceptance
of untested data/layouts.
