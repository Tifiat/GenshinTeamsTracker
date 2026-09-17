# TODO: GenshinTeamsTracker

Open work only. Optimizer items reconciled 2026-09-17 after All Sets backend installation;
other sections retain their separately scoped review status.
Read `CODEX.md` for execution/verification rules and `docs/handoff/README.md`
for document ownership. Completed evidence stays with its subsystem.
Items below are available scopes, not authorization to implement all of them.

## 1. Active Optimizer Work

Contract: `docs/handoff/GCSIM_OPTIMIZER_TRACE_EQUATION_HANDOFF.md`.
Implementation: `docs/handoff/GCSIM_OPTIMIZER_GO_BACKEND_DESIGN.md`.
Current evidence/resume: `docs/handoff/GCSIM_GOB11_GP3_CHECKPOINT.md`.
Engine safety: `docs/handoff/GCSIM_ENGINE_UPDATE_COMPATIBILITY_AUDIT.md`.
Cleanup ownership: `docs/handoff/GCSIM_OPTIMIZER_TRACE_EQUATION_CLEANUP_MANIFEST.json`.

The checkpoint owns current acceptance and failure evidence; do not duplicate
its changing metrics or infer UI acceptance from backend results.

- [ ] **Next N1:** All Sets efficiency/quality after bounded N0 storage recovery;
  **N2** shared handler-path regressions and gated cleanup; **N3** Theory;
  **N4** energy; **N5** readable rotation editor; **N6** other feasible TODO,
  excluding History Browser. Start from the saved Jahoda review. The optimizer
  handoff's "Overnight execution contract" owns the temporary one-agent,
  blocker-parking and handler-verification exceptions; user start only.
  no subagent started. Cleanup and archive verification are recorded in the
  checkpoint. Preserve the bounded evidence archive, expanded N1 inputs and
  dirty worktree; do not recreate all retired scratch for the next benchmark.
  This replaces UI-first work order, not actual UI acceptance requirements.
- [ ] **Remaining combined UI acceptance:** user-confirmed All Sets completion
  and seven-page navigation do not accept Selected2+2/Save/cancel/preservation.
  After restart check AppShell Selected with equipped2+2, preserved pairs,
  finalist pages/save and unchanged live equipment. Milestone reminder delivered.
  Do not repeat the accepted Jahoda full run as a startup check. Evidence and
  backend/visible-UI limits belong to the checkpoint.
- [ ] After this UI gate, complete mandatory All Sets area cleanup: remove
  consolidated research deltas and disposable capture/overlay copies, retaining
  permanent receipts, active/pinned rollback and the deployment backup until
  rollback is no longer needed. Do not leave a second production patch stack.
- [ ] **N1: bounded All Sets efficiency and quality:**
  Jahoda user run hit the search deadline after five contexts, with55 proposals
  pending. Prioritize feasible, team-promising sets before deep artifact search;
  allocate effort by promise, not equally. Distinguish exploratory representatives
  from global Top-N. Measure speed versus incumbent quality on saved/reduced
  controls. Revisit the n128 screen only with an
  explicit quality/budget comparison; no speculative search-budget expansion.
- [ ] Extend account-level acceptance alongside these stages by mechanism, one
  bounded fixture at a time. Eight public-config archetypes have controlled
  formula coverage, not account-equipment DPS/search acceptance. General alias/
  branch/schedule coverage remains partial; repair demonstrated losses.
- [ ] Separate GCSIM database config import after team gates; source/API
  discovery and parser/cache/attribution remain a separate scope.
- [ ] **N3:** Theory/farming guidance using the future Go port of continuous-
  target math; clearer unknown/frozen mechanic diagnostics.
- [ ] **N4: energy support after All Sets and Theory (updated2026-09-17).** GOB-12 remains a label,
  not an instruction to implement before All Sets. Do not modify the current
  finite-energy diagnostic mode until that stage. Keep the single
  `gcsim_boosted_energy_enabled` setting and its two synchronized UI views.
  Finite-energy execution is currently diagnostic, not accepted ER-aware search.
  Add a generic energy ledger, cumulative burst-deadline constraints in Go,
  typed stat/HP/probability dependencies, bounded ordinary-engine finalist
  checks and per-character ER/margin/source/uncertainty explanations.
  Do not run GCSIM per candidate, average away event timing, or copy upstream
  character-specific ER heuristics. Detailed contract is in the optimizer handoff.
- [ ] Before MVP, re-audit every engine patch/seam then present, remove obsolete
  code and repeat clean apply/build/capability/cross-team semantic/rollback
  gates. Include normal updater relocation of generated absolute overlay paths
  from staging to final source (the current All Sets installation was explicitly
  relocated and checked). Required feature capabilities must activate atomically; optional
  groups are a later packaging decision, not an excuse for partial activation.
- [ ] **Engine-update application-path audit (user requested2026-09-17; later).**
  Check every consumer of active engine/source/catalog identity, not only patch
  application: import mappings, stored character/weapon keys, artifact/enemy
  registry defaults, team snapshots, prepared configs, optimizer and normal-run
  UI, caches, rollback and restart. Test an update/rollback with newly supported
  entities and renamed generated registry files. A stale old-version mapping
  must not silently block a supported entity. Explicitly cover stale mappings
  after update without reimport; today's Jahoda repair is not this whole audit.
  Owner: engine integration plan. Do not implement the broader audit now.
- [ ] **Settings / GCSIM version visibility (later).** Show the active engine
  version actually used, not the newest download. Later add selection among
  retained, locally patched/built compatible installations if the bounded store
  retains them. Reuse the engine store, validation and rollback; no second
  engine preference or activation by directory existence alone. Documentation
  only in the current task; UI implementation waits its stage.
- [ ] Clean superseded isolated stores/captures only under the manifest's gates.
  Preserve permanent receipts, the active/pinned rollback engines, Current
  comparison until all product scopes are accepted/abandoned, and the future
  Theory/All Sets math reference. Accepted GP-3 and dependency-audit deltas are
  removed after consolidation; permanent regressions and audit helpers remain.

Performance boundaries remain: cold Selected target 190s; temporary fail-safe
360s; future All Sets 600s. Retain the common n128 screen and bounded n500/n1000
final policy. Do not repeat accepted full runs as routine documentation checks.

## 2. Run Workspace, History And Export

Owners: `APP_SHELL_WORKSPACE_PLAN.md`, `RUN_WORKSPACE_SNAPSHOT_CONTRACT.md`,
`HISTORY_BROWSER.md` under `docs/handoff/`.

The AppShell session, Reset/Save, snapshot-v2 History, shared read-only Run panel,
Abyss sim-result attachment and right-panel slot swaps already exist.
`main.py` still starts the legacy app; changing that entrypoint requires the
user's approval and the current launch-readiness review.

- [ ] Complete DPS Dummy factual inputs/target capture and attach its existing
  diagnostic GCSIM results to typed session/snapshot state and History.
- [ ] Review final v7 [History corrections](docs/design/history/README.md):
  left team portrait/bonuses and timer beside room results, denser expanded
  data, centered title/month range with total on the left, consistent side-icon
  face scale, per-record custom artwork/upload/reset. Native interaction checks
  are postponed by the user while using the app; resume path is in design notes.
  Compact density and portrait-based team identity are user-approved; splash
  downloads were cancelled and the comparison setting removed. Compact DPS
  stays omitted; expanded/right-panel/export DPS remain. `HISTORY_BROWSER.md`
  owns implementation evidence and remaining validation limits.
- [ ] Add History filters/sorting beyond newest-first.
- [ ] Implement real PvP History through the PvP-owned snapshot boundary.
- [ ] Add dedicated PNG Preview/Share if needed beyond the implemented inline
  expanded card and Save PNG. Do not restore a permanent PNG browser panel.
- [ ] Add data-oriented XLSX export: period/date/type/chamber/side, team,
  characters/weapons/artifact sets, timers, factual/sim DPS and warnings.
  CSV/HTML may be later alternatives; standalone History import is not priority.
- [ ] Review the remaining launch blockers with actual user-path checks before
  an approved `main.py` switch; preserve adaptive scaling before QApplication.
  Remove legacy right-panel/history code only after the replacement is stable.
- [ ] Design first-run empty-account onboarding around Account/Data guidance.
  Do not add an isolated auto-open workaround outside that flow.
- [ ] Revisit roster-to-slot drag only if requested; right-panel slot-to-slot
  and cross-team swaps are already connected. Preserve normal quick-pick markers
  and complete slot data; do not revive old hide-used-card prototype wording.

## 3. PvP

Read `docs/handoff/PVP_PROFILE_PACKAGE.md` for the immediate sequence and
`PVP_UI_ROADMAP.md` / `PVP_BACKEND_STATUS.md` for the rest of the feature.

- [ ] Finish independent Player 1/Player 2 providers, including same-id
  characters with seat-specific constellation/image data.
- [ ] Replace development `.gttpvp` with an allowlisted minimal SQLite slice,
  portable bitmap assets, hashes/schema/reference validation and managed cleanup.
  Decide the explicit artifact/preset inclusion rule during schema design.
- [ ] Only after those gates, produce the isolated second-account archive with
  3-4 decks. Do not merge it into the main account or freeze the prototype format.
- [ ] Add scoped Artifact Browser equipment, then executable scoped GCSIM via
  normal build services. Do not mutate normal account equipment or clone its UI.
- [ ] Add authoritative Abyss-period admission for both local seats/future clients.
- [ ] Add PvP result PNG/export and History; preserve scoped providers in saves.
- [ ] Later local setup: draft-system/ruleset selection, immunes and extra
  prebans with explicit pre-main-draft stages. Ruleset mapping/import is paused
  until usable real sources exist; do not infer executable schedules from costs.
- [ ] Later ruleset-cost rendering, extended GTT artifact+preset JSON exchange,
  final styling and online transport. Far-future product ideas remain in
  `FAR_FUTURE_TODO.md`, not the immediate PvP queue.

## 4. Artifact Browser And Equipment UX

Owners: `docs/handoff/ARTIFACT_BROWSER.md`,
`ARTIFACT_BROWSER_EQUIPMENT_UX.md`, `ACCOUNT_EQUIPMENT_STATE_DESIGN.md`.

- [ ] Persist the last applied preset marker per character so
  `{preset}: {character}` survives restart/target switches until that character's
  artifacts actually change. Current `applied_current_equipment_label` is memory-only.
- [ ] Reproduce/fix the reported missing weapon-owner side icon on duplicate/count
  stacks (example: Favonius Sword level 90 R2/R5); distinguish overlay identity
  from correct equip/display behavior and verify through the actual UI.
- [ ] For exhausted weapon fingerprints, design explicit current-owner/source
  selection before move/swap. Do not silently take an ambiguous assigned copy.
- [ ] Unify reset controls and selection behavior across target/Sort/Sets popups.
- [ ] Choose thresholds/colors before adding CV/Proc Count highlighting.
- [ ] Later apply the shared compact toggle to external-bonus/browser on/off
  controls where still needed. `ToggleSwitch` is already used by Account settings.
- [ ] Later infer proc counts for Artiscan artifacts and review other structured
  import/export compatibility. Keep content-copy identity and saved preset IDs.
- [ ] After all card surfaces stabilize, do one portrait crop/rounding pass;
  keep occupied-weapon outline radius aligned with any future thumbnail change.
- [ ] Late asset-quality option: configurable export/crop resolution, followed
  by regeneration. Verify scaling/crop behavior instead of assuming it is trivial.
- [ ] Post-release recommended artifact-stat filters require sourced guide data;
  do not hardcode character advice during equipment work.

## 5. Abyss Data And Mechanics

Owner: `docs/handoff/ABYSS_ENEMY_DATA.md`; parser research:
`ABYSS_MECHANICS_NOTES.md`. Runtime cache/period refresh, enemy/wave HP,
Fact DPS source-confidence tooltips and solo/multi-target setting already exist.

- [ ] Integrate prepared mechanics warnings into the UI: shields, wards,
  invulnerability, state RES, summons and elemental/reaction requirements.
  This is not another broad source audit or Fact DPS tooltip redesign.
- [ ] Extend scenario/season modeling only for concrete missing fields or flows,
  preserving the existing typed chamber/wave/enemy source boundary.
- [ ] If an offline provisional period UI is needed, label it as a session
  placeholder. A local calendar date must never become source-data authority.
  Missing cache/HP keeps factual DPS unavailable; no static-fixture fallback.

## 6. Normal GCSIM Browser And Release

Owner: `docs/handoff/GCSIM_ENGINE_INTEGRATION_PLAN.md`.
Selected-team Abyss prepare/run/results backend is implemented.

- [ ] Finish Browser team/target/readiness/result presentation and navigation.
  Correct the runtime `History persistence: disabled` wording: Abyss results
  persist with Run Save; simulations are not individually auto-saved.
- [ ] **N5 (after optimizer priorities):** readable rotation parsing/presets and
  grouped action/condition buttons with dynamic text/punctuation on insertion
  and deletion. Independently inventory the installed GCSIM DSL and official
  docs; preserve raw input and unsupported constructs without lossy rewrites.
  Start grammar with RU/EN, then other languages; shared UI keys still follow
  project localization rules. One isolated subagent is authorized only after
  the paused overnight session starts; no additional concurrent subagents.
- [ ] Later discover published rotations by exact stable four-character roster,
  with safe parsing, attribution, freshness and deduplication.
- [ ] Add Browser progress/cancellation and run-artifact/debug retention controls.
  Consider bounded parallel chamber runs only after measurement.
- [ ] Release-validate a bundled known-good `gtt-gcsim.exe`; normal users must
  not need Go/Git. Add dependency-aware advanced update/failure UX afterward.
- [ ] Curate mapping overrides only for proved exceptions; Traveler/upstream
  gaps remain controlled unavailable cases. Coordinate shared AppShell/PvP hooks
  before touching them from the normal Browser track.
- [ ] Research standard-build sources, license, format and actual contents
  before adopting or labeling anything as KQM standards.

## 7. Account, Catalogs And Offline Profile

Owners: `DATA_RUNTIME_BOUNDARIES.md`, `ACCOUNT_SQLITE_STORAGE.md`,
`HOYOLAB_IMPORT_RELIABILITY.md` and `STAT_NORMALIZATION.md`.

- [ ] Model Traveler element selection explicitly: shared account level,
  variant-specific talents/constellations, default icon and element selector.
  Preserve `standard_5_star`; never alias localized Traveler to one variant.
- [ ] Add a separate combat/ability-bonus layer only as its own contract.
  Do not mix conditional/talent/ability effects into ordinary display stats.
- [ ] Audit remaining catalogs for runtime-critical SQLite needs; retain small
  rebuildable source JSON/seed caches. Share updater metadata/schema/language
  conventions and support offline last-known/bundled data.
- [ ] Prepare sanitized seed catalogs/resources for release, including artifact
  catalog/icons; keep personal data and browser state ignored.
- [ ] Consider separate user choices for UI and account/reference content language.
- [ ] Broader offline profile: versioned safe restore/backup including History,
  settings and needed caches where appropriate; continue excluding auth/debug.
  This is separate from PvP profile exchange.
- [ ] If full import crash recovery is requested, design publication recovery
  without overwriting concurrent equipment/preset edits. Current DB + JSON +
  image publication is not one transaction.
- [ ] Add a reusable localized custom-tooltip help icon, including an explanation
  of the already implemented HoYoLAB Change equipment setting.
- [ ] Later remove physical legacy `artifacts.icon_id` / `artifact_icons`
  leftovers through a deliberate migration after the browser path is stable.

## 8. Performance And Packaging

- [ ] **After optimizer work, open a separate full size/lifecycle audit.**
  Measure source/runtime/package; inventory generators/cleaners; add bounds and
  tests, then remove reviewed rebuildable duplicates. Preserve user data,
  evidence, protected engines/worktrees; verify startup, rollback and sizes.
- [ ] Refresh measurements before performance work. Existing weak-laptop
  measurements in `docs/handoff/performance_measurements/` are dated June 2026,
  not current universal costs. Follow `PRELOADER_BACKLOG.md`.
- [ ] Reduce duplicate grid/pixmap/SQLite work first; profile remaining
  bonus-strip hydration, target-button creation and Artifact Browser cold load.
- [ ] In an explicitly selected loader stage, inventory and prepare necessary
  cold work together: stores, targets/presets/edit controls, image/text/marquee
  caches and equipment prewarm with complete invalidation keys.
- [ ] Build a clean distributable instead of shipping the development venv.
  Audit unused Qt/Playwright payloads, exclude development/private state, keep
  user runtime data outside the app bundle and measure installer/unpacked size.
  Historical venv size estimates must be remeasured for the chosen build.
- [ ] Revisit resize twitch only with new evidence; an earlier isolated probe
  reproduced environment-dependent live-resize behavior outside the app.
