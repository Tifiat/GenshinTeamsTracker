# History Browser Contract

Scope: authoritative product and architecture contract for the AppShell
History Browser.

The visual MVP is implemented: History has local Abyss/DPS Dummy/PvP modes in
the right header, a compact period navigator/enemy preview, visual saved-run
rows, and an isolated shared read-only Run presentation for selected snapshots.
Normal browsing has no Refresh command or always-visible PNG preview.

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
  account/profile data, DBs, settings, or network state to render a saved run.
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

## Current State And Next Stage

Snapshot Bundle v2 and production Save capture frozen display details for every
occupied slot and materialize declared visible assets inside the bundle without
retaining temporary hydration in live state. Grouped storage, row selection,
the snapshot-to-shared-right-panel adapter, isolated read-only Run panel, first
occupied slot selection, frozen slot navigation, disabled timers/state changes,
hidden commands, and removal of the permanent PNG area are implemented.

The compact left-browser MVP is implemented with reusable summary components.
Future work is visual polish from manual smoke, fuller DPS Dummy input capture,
real PvP History, filters/sorting beyond newest-first, and an explicit shared
presentation-based export flow.
