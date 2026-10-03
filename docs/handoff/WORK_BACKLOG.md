# Deferred work by area

The active optimizer order is in `../../TODO.md`. These are open scopes to read
only when selected by the user or after the active stage is finished. The linked
owner documents contain contracts, current status and detailed acceptance;
this list is not independent implementation authority.

## Run workspace, History and export

Owners: `APP_SHELL_WORKSPACE_PLAN.md`, `RUN_WORKSPACE_SNAPSHOT_CONTRACT.md`,
`HISTORY_BROWSER.md`.

- [ ] Complete DPS Dummy factual inputs/target capture and attach diagnostic
  GCSIM results to typed session/snapshot state and History.
- [ ] Finish the History v10 review and its postponed real click, artwork,
  upload/reset/export/restart path. The exact geometry, presentation decisions,
  automated evidence and unverified UI path are in `HISTORY_BROWSER.md` and
  `../design/history/README.md`.
- [ ] Add a localized current-Abyss-period setting, marking only the dynamically
  authoritative latest period, for example `(current) 9.2026`; leave every
  other option unmarked. Never infer authority from date, selected period or
  newest saved run.
- [ ] Add History filters/sorting, real PvP History, and, if needed, a dedicated
  PNG Preview/Share beyond the existing inline card and Save PNG.
- [ ] Add data-oriented XLSX export with period/date/type/chamber/side, team,
  equipment, timers, factual/sim DPS and warnings; CSV/HTML are later options.
  Standalone History import is not a priority.
- [ ] Review launch blockers through the real user path before an approved
  `main.py` switch; retain adaptive scaling and remove legacy UI only after
  replacement acceptance. Design first-run empty-account onboarding as part
  of Account/Data guidance. Revisit roster-to-slot drag only on request.

## PvP

Read `PVP_PROFILE_PACKAGE.md` for the immediate sequence and
`PVP_UI_ROADMAP.md` / `PVP_BACKEND_STATUS.md` for the rest.

- [ ] Finish independent Player 1/Player 2 providers, including same-ID
  characters with seat-specific constellations/images.
- [ ] Replace development `.gttpvp` with a minimal allowlisted SQLite slice,
  portable assets, hashes/schema/reference validation and managed cleanup;
  decide artifact/preset inclusion during schema design. Then produce the
  isolated second-account archive with 3-4 decks without merging accounts.
- [ ] Add scoped Artifact Browser equipment and then executable scoped GCSIM
  through normal build services; do not mutate normal account equipment.
- [ ] Add authoritative Abyss-period admission, PvP result export and History.
- [ ] Later: local draft-system/ruleset setup, immunes and prebans with explicit
  stages; ruleset import waits for usable real sources. Add cost rendering,
  extended artifact/preset exchange, final styling and online transport later.
  `FAR_FUTURE_TODO.md` remains separate non-MVP research.

## Artifact Browser and equipment

Owners: `ARTIFACT_BROWSER.md`, `ARTIFACT_BROWSER_EQUIPMENT_UX.md`,
`ACCOUNT_EQUIPMENT_STATE_DESIGN.md`.

- [ ] Persist the applied-preset marker per character until equipment changes.
- [ ] Reproduce and fix the missing weapon-owner icon on duplicate/count stacks
  (reported Favonius Sword 90 R2/R5); verify the actual UI path.
- [ ] Design explicit owner/source choice for exhausted weapon fingerprints.
- [ ] Unify reset/selection across target, Sort and Sets popups; choose
  thresholds/colors before CV/Proc Count highlighting.
- [ ] Later: shared compact toggles, Artiscan proc inference, other structured
  import/export compatibility, final portrait crop/rounding, optional export
  resolution and sourced artifact-stat recommendations.

## Abyss data and mechanics

Owners: `ABYSS_ENEMY_DATA.md`, `ABYSS_MECHANICS_NOTES.md`.

- [ ] Surface prepared warnings for shields, wards, invulnerability, state RES,
  summons and elemental/reaction requirements.
- [ ] Extend scenario/season modeling only for concrete missing source fields.
  Label any offline provisional period as a session placeholder; a calendar
  date or static fixture cannot supply factual-DPS authority.

## Normal GCSIM Browser and release

Owner: `GCSIM_ENGINE_INTEGRATION_PLAN.md`.

- [ ] Finish team/target/readiness/result presentation and navigation. Correct
  the misleading `History persistence: disabled` label: Abyss results persist
  with Run Save but are not individually auto-saved.
- [ ] After optimizer priorities, build readable rotation parsing/presets and
  grouped action/condition buttons with live grammar-aware text. Inventory
  installed GCSIM DSL and official docs; preserve raw unsupported constructs.
  Start with RU/EN, then other locales.
- [ ] Later: roster-matched published-rotation discovery, progress/cancel and
  run-artifact retention, measured parallel chamber runs, bundled known-good
  `gtt-gcsim.exe`, advanced dependency/update UX and proved mapping overrides.
- [ ] Research sources, license, format and contents before adopting any
  standard-build label.

## Account, catalogs and offline profile

Owners: `DATA_RUNTIME_BOUNDARIES.md`, `ACCOUNT_SQLITE_STORAGE.md`,
`HOYOLAB_IMPORT_RELIABILITY.md`, `STAT_NORMALIZATION.md`.

- [ ] Model Traveler element selection with shared level and variant-specific
  talents/constellations. Preserve `standard_5_star`; avoid localized aliases.
- [ ] Add conditional combat/ability bonuses only as a separate layer.
- [ ] Audit catalogs for runtime-critical SQLite needs while retaining small
  rebuildable source caches; prepare sanitized release seeds/assets.
- [ ] Consider separate UI and account/reference language choices.
- [ ] Extend safe offline backup/restore to History, settings and needed caches
  while excluding auth/debug; keep PvP exchange separate.
- [ ] If requested, design import crash recovery that preserves concurrent
  equipment/preset edits.
- [ ] Add localized custom-tooltip help for HoYoLAB Change equipment; migrate
  physical legacy `artifacts.icon_id` / `artifact_icons` fields deliberately
  after browser stability.

## Performance, size and packaging

- [ ] After optimizer work, perform a separate full size/lifecycle audit:
  measure source/runtime/package, inventory generators/cleaners, add bounds
  and tests, remove reviewed rebuildable duplicates and verify startup,
  rollback and sizes while preserving user data/evidence/engines/worktrees.
- [ ] Re-measure before performance work; June 2026 weak-laptop measurements
  are dated. Follow `PRELOADER_BACKLOG.md`, reduce duplicate grid/pixmap/SQLite
  work, then profile remaining hot paths.
- [ ] In an approved loader stage, prepare cold stores, targets, presets,
  controls and image/text caches together with complete invalidation keys.
- [ ] Build a distributable without development venv/private state; measure
  installer/unpacked size and place user runtime data outside the bundle.
- [ ] Revisit resize twitch only with fresh evidence.
