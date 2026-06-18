# History Browser Contract

Scope: authoritative product and architecture contract for the AppShell
History Browser.

The current code lists grouped immutable bundles and selects saved rows. A
selected bundle is adapted into an isolated read-only instance of the normal
mode-specific Run presentation, and normal browsing no longer generates an
always-visible PNG preview. The remaining MVP gap is the contracted left-side
browser presentation.

## Ownership And Boundaries

- History is a left AppShell workspace with stable id `history`.
- History is not a floating legacy window and not a right-dock-only page.
- `ui/app_shell.py` owns workspace routing and right-dock page selection only.
  History browsing belongs under `ui/history_browser/`.
- `ui/right_panel/history/` may own the snapshot adapter, host, empty state, and
  read-only policy. It must not own parallel copies of Run presentation widgets.
- `ui/run_history_window.py` and `runs_history.json` are obsolete and must not
  become the final History model.
- Opening History reloads the configured immutable snapshot root without
  resetting or rebuilding the live Abyss/DPS Dummy/PvP session.
- History never reads current account equipment, Artifact Browser presets,
  account/profile data, DBs, caches, settings, or network state to render a
  saved run.

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

- History has internal `Abyss` and `DPS Dummy` tabs. PvP may become a third tab
  only after the PvP History contract exists.
- Entering History defaults to the current live Run mode.
- Within each section, newest saved runs are listed first.
- MVP navigation includes type tabs, Abyss period groups, and newest-first
  ordering. Character/DPS/set/warning filters and richer sorting remain later.

### Abyss

- Group snapshots by immutable `scenario.abyss.period_start`, using the period
  start as the stable group key.
- A compact period header shows date range, floor/season, and saved-run count.
- Expanding the period header shows C1/C2/C3, Side 1/Side 2, saved enemy/boss
  images, display names, and total HP for each side.
- Each saved-run row is a compact visual double-team row with character
  portraits, weapon icons, artifact set/build indicators, and all three chamber
  result blocks.
- Each chamber block shows saved time plus factual DPS and sim DPS when present.

### DPS Dummy

- Each saved-run row shows one visual team, target/setup summary, duration/time,
  factual DPS, and sim DPS when present.

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

- A permanent selected-run PNG preview is not part of normal History browsing.
- The current text-first `history_snapshot_preview.py` renderer is transitional
  and must not define the final History/export visual language.
- A future explicit Preview/Export/Share flow should render PNG from the same
  shared RunCard/TeamCard presentation used by Run and History.
- Structured XLSX/data export remains a later feature.

## Current Gap And Next Stage

Snapshot Bundle v2 and production Save capture frozen display details for every
occupied slot and materialize declared visible assets inside the bundle without
retaining temporary hydration in live state. Grouped storage, row selection,
the snapshot-to-shared-right-panel adapter, isolated read-only Run panel, first
occupied slot selection, frozen slot navigation, disabled timers/state changes,
hidden commands, and removal of the permanent PNG area are implemented.

The next implementation stage is:

1. add internal Abyss/DPS Dummy tabs with live-mode entry selection;
2. replace text-first groups and rows with the contracted expandable period
   headers and compact visual rows;
3. preserve newest-first ordering and add the remaining left-browser tests.
