# Tests

Purpose: keep the unit/integration test suite cheap to navigate and cheap to
run by feature area. Root `CODEX.md` and `TODO.md` stay as entrypoints; this
file owns the detailed test-layout rules. Coverage descriptions are navigation,
not proof that the suite passed on the current tree. Historical test counts
remain in dated receipts; documentation maintenance does not rerun product tests.

## Layout

Mirror the primary project owner under `tests/`:

- `tests/hoyolab_export/account/` - account storage, equipment, import pipeline,
  offline profile, account stat sheet.
- `tests/hoyolab_export/artifacts/` - artifact DB/catalog integration, build
  snapshots, stat normalization, display stat effects, and virtual GCSIM build
  target persistence/merge-by-stable-key coverage.
- `tests/hoyolab_export/catalog/` - HoYoWiki/static catalogs, mapping reports,
  character/weapon stat snapshots, trait catalogs.
- `tests/hoyolab_export/abyss/` - HoYoLAB/export-side Abyss helpers and refresh
  orchestration.
- `tests/hoyolab_export/tournament/` - tournament ruleset validation.
- `tests/run_workspace/abyss/` - Run Workspace Abyss source data, factual DPS,
  runtime fixture/cache behavior.
- `tests/run_workspace/gcsim/` - engine lifecycle, compatibility, config/key
  mapping, wave scenarios, cleanup, artifact runners and Python/Go integration.
  `test_gcsim_virtual_roster.py` covers installed-catalog parsing, weapon-class
  compatibility, C/R ranges, complete-profile moves and character
  level-to-max-legal-ascension boundaries (`80` -> `80/90`).
  `test_gcsim_selected_team_config.py` covers strict owned-build input plus the
  separate mixed account/virtual Theory baseline with no saved build, initial
  set package or owned ids. Native contract tests prove the raw Theory request
  keeps that non-owned identity and expands private artifacts only in process.
  Active Selected coverage is in `test_optimizer_go_*.py`; native contract,
  formula, search and stochastic tests are under `native/gcsim_optimizer/`.
  `set_packages_test.go` suites cover4p/2+2 request legality, disjoint slot
  patterns, small exhaustive search controls and bounded frontier fairness;
  finalist render tests preserve both set rows and initialization order.
  `set_effect_preflight_test.go` retains real static set-replacement witnesses
  and negative old/double-bonus/same-topology-resistance shortcuts. These are
  bounded arithmetic controls, not universal effect-replacement proofs.
  Native `internal/setcontext` tests cover isolated context/render/routing/cache
  identities, synthetic scoped proofs, separate set bias and capture budgets.
  The `all_sets_preflight/replay_context.py` overlay reuses seven retained real
  transitions without new engine calls; its dated receipt is separate from
  product integration. `capture_pilot.py` connects the real two-seed provider,
  shared inventory views and bounded one-wearer FGBS for two fixture packages;
  eight new compact calls are an explicit research budget, not a routine suite.
  Its receipt separates formula response from product/search-quality acceptance.
  `inventory_bound_poc/run.py` is a managed, isolated Go overlay: three finite
  real-item domains compare an affine upper-bound search with exhaustive shared
  production-formula scoring. `--synthetic-only` runs seven cheap arithmetic
  controls without engine calls. `tests/tools/test_inventory_bound_poc.py` pins
  its compact receipt, full vectors and restricted physical legality; this is
  not installed search, schedule-response or UI acceptance.
  The integrated All Sets path adds `artifact_bound_test.go` (joint crit/caps,
  flat ATK, nonlinear branches, singularity, randomized finite enclosures),
  `inventory_test.go` (small exhaustive optimum, foreign-anchor parity,
  budget/cancellation), sparse-package legality and cross-wearer reservation
  regressions. These are scoped numerical/physical controls, not global proofs.
  The approved overhaul adds `parametric_program_test.go` for retained variable
  ports, identity/cross-owner/branch/duration parity and reverse gradients;
  inventory tests cover global region order, opaque no-prune behavior, genuine
  occupied-item transfer, shared pair budgets and within-wearer deadline recovery.
  `TestAllSetsEntrypointHasOneCommonFidelityMeasurement` pins the single n500
  orchestration call without simulations; Selected's old screen is separate.
  `internal/evaluator/parametric_live_test.go` is opt-in ONLY: set
  `GTT_PARAMETRIC_LIVE=1` and run `go -C native/gcsim_optimizer test
  ./internal/evaluator -run ^TestParametricActiveEngineWitness$ -count=1 -v`
  through `tools/managed_optimizer_experiment.py --timeout 180 -- ...`.
  It checks the active engine against the retained first small Flins input,
  makes exactly two production-provider captures and compares24 joint input
  changes/16 specializations against unreduced arithmetic. It skips normally,
  refuses unmanaged/live-path drift and is NOT set-lifecycle or product acceptance.
  The historical2026-09-20 source-only query gate is
  `tools/experiments/gcsim/parametric_effects/check_stat_queries.py`, run under
  the same managed wrapper with240s. It tests fourteen reviewed observer/generator
  patches over the then-selected source (21 central controls and five selected-stat
  generator cases, no installation).
  Explicit `--capture-fixture` uses360s and makes two captures of ONE retained
  Flins seed: neutral and unchanged original sets. Strict native decoding,
  aggregate input binding and per-channel response checks follow. The saved
  four-package response now matches to roundoff; this is not arbitrary-set or
  product acceptance. The Go design records scope and earlier failed diagnostics.
  `parametric_effects/check_rules.py` uses180s and the production
  engine-bound source envelope: lexical state, source timers, subscription
  replacement, constructor visibility, scratch-vector purity, typed target
  interfaces and thirteen original synthetic-tape source controls, plus Scroll
  partial/full/zero, independent map registration, enum-key identity, returned
  field scratch,2/3-versus4/5 piece tiers and tail/speed schedule boundaries.
  Scalar addresses retain queued-callback identity and a live read-only frame;
  actual LongNight stack refresh/expiry and Amount helper-local ownership pass.
  Resource controls cover outgoing/received healing separation, expiry, crystal
  versus foreign shields, nearby/far lunar constructs, low/high energy and
  healing-to-flat-hit accumulation. Unknown resource evidence remains unknown;
  event-healing and candidate-ER activation have explicit approximation codes.
  `allsets/neutral_coordinator_test.go` adds a source-bound5^5 inventory oracle,
  no-bonus winner, one-capture ownership and shared-budget coverage controls.
  Its neutral finalists also traverse the production `FinalistRenderer`, pinning
  non-artifact frame, n500 options, energy policy, set rows and rendered identity.
  The opt-in `neutral_profile_test.go` consumes the same saved capture and
  verified reference for restricted then full60s source searches starting from
  the saved WEAK physical build, not the supplied strong incumbent. Restricted
  model recall gates expansion; all generated inputs are managed and removed.
  User-authorized `--finish-passes` removes only the60s search deadline (900s
  managed watchdog,600s native safety ceiling). Both configured passes completed
  on587 items in115.352s, zero unknown packages, unchanged best20 IDs. This is
  not all-combination enumeration, convergence or production/button timing.
  Optional `--compare-preparation` runs reuse-off/on consumer variants against
  the SAME captures and inventory, with no additional engine calls. Full587
  paired96.406->89.388s/preparation48.317->41.982s preserved all seven finalists,
  work hashes and coverage. Cache controls pin exact fixed-input/source/mask/
  proof identity, private scratch and bounded eviction; linear-plan controls
  compare repeated scans with negative/tied weights, reservations and exclusions.
  Complete domain/formula/search suites run before the paired profiles.
  Optional `--compare-effects` isolates constant binding/reachable-key reuse;
  paired full58789.865->81.233s (binding16.289->8.008s) preserved work and all
  seven finalists. Final order hardening additionally matches the general
  binder's compiled-node order and cancellation-sensitive reverse gradients.
  Dynamic latent reads, malformed/nonfinite inputs and proof state remain covered.
  `--two-seeds` completion profiles use both saved seeds: decode each member,
  compare neutral response with the independent SAME-panel control, then gate
  full inventory by restricted recall. This is source-only, not button timing.
  `candidates_test.go` pins tiny exhaustive parity, budgets/cancel and explicit
  top-five/spread heuristic conditions. New search scores complete real builds;
  local weights do not certify permanent item or set elimination.
  Union potentials pin legal pattern support and joint crit/cap enclosures;
  constant caching validates the full vector before exact damage-reachable key
  projection; dynamic expressions bypass it. Controls pin finite FIFO size,
  private scratch and proof state. Resumable frontier controls compare1/7/64-unit slices with the atomic
  small-domain solver, without repeated work or unknown-dependent pruning, and
  retain pending regions/real improvements across cancellation.
  Hybrid affine/interval controls additionally pin finite clamped roots at
  zero, long products and randomized signed/fractional branches. They pass
  arithmetic tests but historically regressed the fixed60s profile. The approved
  real-candidate coordinator no longer invokes those bounds. Its dated weak-start
  results and n500 ordinary checks are in the Go design; not UI acceptance.
  Those source profiles are not installed full-inventory searches. Other gates cover prepared-port,
  timed/weapon and actual-source Emblem controls. Formula tests pin read roots,
  post-reduction expression binding, caps, cycles and cross-owner specialization.
  The managed capture now validates latent stat exports/binding. Optional
  `--audit-rules` measures package coverage on that ONE tape without per-set
  simulations; coverage is not response acceptance. Default native
  suites skip the active-source control unless that managed gate supplies its
  envelope. `tests/tools/test_parametric_effect_gate.py` pins unmanaged
  refusal, patch paths and same-installation overlay relocation; the existing
  managed suite owns cleanup/preservation. The Go design records its scope.
  The2026-09-26 managed `install_neutral.py --activate` gate consolidates those
  observers plus additive `gtt_neutral_inputs_v1` into production patch0009.
  It checks exact active-source replay, full native suite, normal clean updater
  build, application compatibility and four ACTUAL built-binary captures before
  activation. Their two-seed response matches the independent same-panel control.
  `test_neutral_install` covers generated-diff preservation, overlay path escape,
  actual generator evidence and rollback after a failed active-pointer change.
  The source-only overlay command must not be reapplied to the new engine.
  Adapter/CLI controls route only new-capable infinite All Sets to neutral search;
  finite energy/older engines and Theory retain their existing paths. Missing
  neutral rules on an advertised new route fail explicitly. Detailed deployed
  product performance and any real button acceptance remain GP-3 evidence.
  `tools/experiments/gcsim/all_sets_inventory_regression/run.py` runs only the
  14 post-change All Sets rows through production request/session classes and
  the active engine; it never regenerates the supplied baseline. Managed jobs
  remove captures/build caches after each row. Its retention tests guard
  immutable before.json, failed-attempt preservation and size/attempt limits;
  report.py compares measured DPS, twenty IDs, mains, physical sets and limits.
  Native domain tests exhaust small slot masks and preserve raw-stat reference;
  provider/search tests guard seed, energy, ownership, legality and cancellation.
  `measure_decode.py` checks the canonical-read optimization on saved bytes
  without engine calls. No real-set static proof producer is enabled yet.
  Native `internal/seteffects` tests cover source aliases/shadowing, mutable
  count/recipient refusal, callback reachability, typed tag filters, empty
  switch cases, source enum drift and exact-graph input binding. Channel and
  intervention tests reuse existing arithmetic, retain cross-owner dependency
  and reset offsets. `all_sets_effect_discovery_receipt_v1.json` scopes the
  full-catalog scan and four isolated reaction-input control simulations.
  `all_sets_effect_guide_receipt_v1.json` adds four resistance controls using
  source-extracted curves, bound recipe/input features and an automatic queue
  pilot (eight fresh members plus two winner-response members). No comparison
  against optimized Selected or ordinary-DPS/UI claim follows. `internal/allsets`
  tests preserve global queue limits, wearer breadth, physical reservations,
  cancellation, deterministic hints and the correct raw formula anchor.
  Observer consolidation receipt adds clean-source/typed-sidecar and standard
  bundle gates. `test_optimizer_go_all_sources` uses project-venv unittest, not
  pytest: byte-preserving source transport and binary/manifest/tree drift.
  Guide regressions reject stale source/context/stat anchors and preserve unknown
  lanes. Pair-seed DP is checked against a tiny synthetic exhaustive oracle;
  joint proposal tests preserve20 IDs, deterministic ordering and shared budgets.
  Coordinator regressions cover global context/expansion bounds, queue fairness,
  cancellation/partial deadlines, baseline retention and deterministic output.
  Finalist renderer tests enforce own-package output, common non-set frame and
  engine identity. All Sets adapter tests prohibit Python compact-capture loops;
  UI tests exercise the capability gate, signal and shared busy state, not real
  AppShell acceptance. The joint/coordinator receipts separately record copied-
  account comparison against optimized Selected and ordinary finalist panels.
  The observer delta is now consolidated in the production patch; dated research
  commands remain experimental and ordinary test suites do not run GCSIM.
  `all_sets_product_receipt_v1.json` scopes the dated cold CLI, ordinary panels
  and installed source/engine controls separately from later UI evidence.
  Contract tests require exactly one Selected-IR or All-Sets-panel identity;
  Python source tests accept post-build store metadata but reject arbitrary
  added source files. Native finite-energy coverage includes deadline
  feasibility, formula-invisible ER, ordinary-result insufficient-energy
  decoding and rejection of only the failing finalist while preserving later
  valid finalists. Request regressions reject empty inventories, incomplete
  builds and missing equipped IDs. Full Go tests pass at this installation;
  this is not universal mechanic coverage.
  Trace/source-dependency tests under `trace_equation/` cover the retained
  compiler/engine boundary, not a second Python Selected backend.
  Older farming/Current/continuous-target coverage is reference or comparison
  coverage. Released All Sets, Theory and energy-aware Selected acceptance and
  current limits live in the checkpoint. New Selected2+2 backend evidence has its own acceptance receipt,
  separate from actual AppShell/UI acceptance.
  `optimizer_mode_matrix_account_v1.json` adds bounded account evidence for
  Selected, All Sets and Theory on Chasca, Lunar-Charged and Bloom teams plus
  two Flins/Sucrose rotations. Its runner uses the production request/session
  classes and managed scratch; Qt tests click the actual mode buttons, verify
  their emitted team/rotation and map each request type to its production
  session. The dated `GCSIM_OPTIMIZER_ARCHETYPE_AUDIT_20260919.md` additionally
  records real AppShell clicks of all three account buttons and virtual Theory,
  plus 14 virtual All Sets/Theory session pairs. Selected2+2/Save/cancel and a
  virtual All Sets physical click remain distinct UI gates.
  Current real-engine acceptance and limitations live in
  `GCSIM_GOB11_GP3_CHECKPOINT.md`; old migration/stage receipts remain dated
  evidence in the Go design and fixture directory.
- `tests/run_workspace/pvp/` - backend PvP deck validation, Decks UI preset
  persistence/conversion and root-resolved default path coverage
  (`test_deck_preset.py`), observed weapon-stack identity helper coverage
  (`test_weapon_identity.py`), portable PvP v2 schema/privacy/inventory/reference
  coverage (`test_profile_schema.py`) and ZIP/hash/bitmap/cleanup gates
  (`test_profile_package.py`, `test_profile_package_validation.py`), Free Draft
  schedule/reducer/action log, team/weapon assignment validation, and
  timer/result behavior, local-account deck export provider/report behavior,
  draft-system registry behavior, deterministic Free Draft planner/account
  full-loop smoke behavior, Free Draft controller/projection behavior, Free
  Draft board/read-model projection behavior, backend-owned `unified_pool`
  projection/result-zone behavior, board projection validator and committed
  UI-contract sample behavior, PvP session bundle roundtrip/replay
  verification, plus report-only ruleset applicability, cost-preview, and
  ruleset/balance application tests. Manual backend smoke
  commands: `python -m
  run_workspace.pvp.full_loop_smoke`, `python -m
  run_workspace.pvp.free_draft_controller_smoke`, `python -m
  run_workspace.pvp.free_draft_controller_smoke --json`, `python -m
  run_workspace.pvp.free_draft_controller_smoke --step-demo`, `python -m
  run_workspace.pvp.ui_full_flow_smoke`, `python -m
  run_workspace.pvp.ui_full_flow_smoke --account`, `python -m
  run_workspace.pvp.ruleset_applicability_smoke`, `python -m
  run_workspace.pvp.account_deck_export_smoke`, `python -m
  run_workspace.pvp.account_full_loop_smoke`, `python -m
  run_workspace.pvp.session_bundle_smoke`, and `python -m
  run_workspace.pvp.ruleset_balance_smoke`.
- `tests/run_workspace/team/` - team-builder state and team-card data/view
  models.
- `tests/run_workspace/right_panel/` - right-panel view-model behavior owned by
  `run_workspace`.
- `tests/run_workspace/history/` - immutable History Snapshot Bundle schema,
  caller-rooted local read/write service behavior, complete frozen data for
  every occupied slot, bundle-local asset capture, and snapshot-to-shared
  right-panel view-model adapters. Future fixtures must prove that rendering a
  saved run needs no live account, DB, cache, or Run Session data. Catalog
  tests also cover cache-only/snapshot-only period union, deduplication,
  newest-first ordering, current-period preference, and no period-file writes.
- `tests/run_workspace/session/` - typed live Run Session ownership for
  AppShell mode/team/selection/timer/GCSIM runtime state.
- `tests/ui/app_shell/` - AppShell and legacy-main-window adapter tests,
  including cross-boundary routing tests for right-dock page selection,
  workspace/right-dock routing integration for History and PvP. History
  coverage should verify a separate snapshot-bound presentation state and an
  unchanged live session after entering/leaving History. PvP coverage includes
  `Decks`/`Play`/`Draft` header routing, preservation of normal Run state while
  switching PvP pages, root deck path coverage that prevents `ui/data`
  recreation, and active in-memory Draft board preservation after leaving and
  returning to PvP. `test_virtual_gcsim_slots.py` covers account-state
  isolation, selected-team override transport, compact searchable compatible
  weapon/profile/build controls, legal 4p/2p+2p selection, C/R signals, account
  replacement confirmation, blocked account weapon mutation, full-profile
  account/empty/virtual swaps and right-panel drag/drop forwarding.
- `tests/ui/right_panel/common/` - shared right-panel visual primitives such as
  reusable slot/team/card primitives, `slot_parts.py` portrait/weapon/artifact
  mini-zones, shared metrics/styles/helpers, and non-domain-specific card UI.
- `tests/ui/right_panel/live_run/` - live Run/Abyss/DPS right-panel widgets,
  including current-run team slots, chamber/timer/result widgets, selected
  target behavior, and compact GCSIM summary/status cells. The former
  right-panel prototype bonus/smoke tests now live here and import production
  widgets from `ui.right_panel.*`.
- `tests/ui/right_panel/history/` - frozen snapshot adapters, host, and read-only
  policy around the shared mode-specific Run presentation. Coverage should
  verify reuse of common Run components, first-occupied-slot selection, frozen
  slot navigation/tooltips, disabled timers/state controls, hidden
  mode/Reset/Save/command controls, blocked mutation and drag/drop, and
  bundle-local assets. Do not pin the provisional separate details QLabel or
  permanent PNG preview as target behavior.
  `test_history_cards.py` covers coupled expansion/selection, collapse without
  clearing selection, preserved row identity on preference/reload, persistent
  icon choice, frozen PNG rendering, live-format badges/legacy-warning filtering,
  missing-stat alignment and dismissal of popups/pending hover during scroll.
  A scrolled-card regression places enemy and character popups near a visible
  lower-edge hover while the card origin is offscreen; both must stay inside
  the selected screen, and the enemy popup must remain near that hover point.
  Expansion must retain exactly one character hit region per slot at narrow
  and wide viewport widths, including sub-1 DPR startup downscale; hover
  coordinates must match widget pixels. Two-set builds and wrapped enemy rows
  must reserve enough height and keep their hit regions inside the card.
  Compact density has a <=110px height guard for an ordinary two-team run at
  864px rendered width and <=140px at 1220px for the wide results layout. The
  narrow assertion also requires eight character hits without a secondary
  results strip; a separate check covers extra two-set build height. The compact
  hierarchy check pins the clean 86px total, separate 28px two-high resonance
  column, Roman-before-resonance hiding priority, suffix without whitespace and
  silent clipping of bonus overflow. Period UI checks keep the
  heading to one row, omit zero-run menu actions, retain a large popup target,
  and verify horizontal chamber labels, 50px boss icons and styled HP values
  only after the boss preview is toggled open.
  Sub-1 DPR cases still settle hidden-widget resize and convert hit geometry
  through content scale, not a forced DPR=1 assumption.
- `tests/ui/right_panel/pvp/` - PvP right-panel host/pages/stage panels,
  including Decks, Play, Draft pick/ban zones, future scoped build-flow routing,
  Timers/results, and Completed result/export panels. Tests must not bless a
  PvP-specific clone of the normal build right panel as MVP behavior.
- `tests/ui/right_panel/test_right_panel_ownership_imports.py` - structural
  right-panel ownership guardrails: new production imports, compatibility
  facades, canonical PvP constants/imports, and guardrails that MVP PvP build
  flow routes to the normal `RunRightPanelWidget` path instead of a custom PvP
  target-slot hierarchy.
- `tests/ui/pvp_browser/` - left/main PvP browser/workspace tests, including
  deck browser grids, left workspace create/edit/save/cancel coordination,
  card-grid viewport edit tint, selected-card edit markers, Play deck selectors,
  disabled/no-op invalid start, same-deck self-vs-self start, active Free Draft
  controller summary fields, Draft empty state, start-to-Draft routing,
  unified-pool current action/legal target rendering, one card per shared
  `character_id`, per-seat ownership/constellation markers, legal click mapping,
  illegal no-op behavior, same-deck seat-state independence, and a deterministic
  full Free Draft completion through UI card clicks, plus post-draft transition
  guards. Draft visual regression coverage requires one painted
  `PixelIconGrid` pool rather than QWidget/text cards, image paths for pool and
  result items, opposite-side P1/P2 constellation badges, legal-only click
  routing, removal of accepted targets from the pool, the full 22-position
  order strip, owner-colored frames independent of active turn, split Player 1
  left / Player 2 right frames for shared cards, owner badges retained on
  disabled cards, fixed 72x72 draft-order slots that reflow vertically without
  overlapping the central turn board at narrow/medium/wide widths, no tiny
  action labels inside order slots, right-panel pick/ban grids built through
  the same item adapter, uncluttered result portraits without pool ownership overlays, and a
  collapsed-by-default secondary action log. The Draft suite also pins the
  shared `CharacterFilterBar`, unified/player scope controls, semantic
  action-slot state, and empty-filter cleanup so hidden stale items cannot stay
  legal. MVP build-flow tests assert
  that scoped PvP assignment uses the
  normal AppShell quick-pick marker contract: team-colored `1-4` markers for
  team 1 and team 2, no PvP-only `SEL` badges, no grey disabled
  assigned-character overlays, and no custom PvP target-slot hierarchy in place
  of `RunRightPanelWidget`. They also cover normal slot-target selection,
  stable width-neutral seat highlighting driven by configurable global PvP
  player colors, action-colored translucent Draft-slot overlays, shared
  Abyss-style `10:00..05:00` remaining-clock wheel/keyboard timer inputs through
  the left Draft scene, remaining-to-elapsed backend conversion, separate enemy
  wave and solo/multi-target HP rendering in fixed table columns, equal-width
  timer columns across all chambers, table-style Solo/Multi DPS summary,
  six-value readiness, backend result finalization, and the completed
  elapsed-seconds total/chevron/difference scoreboard state. Account-settings
  tests pin both PvP color swatches and the
  reset-to-default behavior.
  Abyss-period admission tests remain a
  required future suite when that backend gate is implemented. They also cover
  selected-slot weapon assignment, Ready backend commits, both-Ready timer
  transition, imported-profile provider routing, per-seat scoped PvP runtime
  weapon state, no mutation of normal account equipment tables, no initial
  leakage of normal/imported owner badges into PvP source grids, stable
  post-draft source/right-panel widget identity across clicks, runtime weapon
  hydration after character remove/re-add, right-panel slot drag/drop swapping,
  and PvP Ready commits using scoped stack identity instead of display/type-name
  recomputation. Performance-regression coverage should include one-refresh
  source clicks, active-seat-only right-panel updates where possible, compact
  collapsed post-draft seat rows, and numeric/localized weapon type resolution
  to backend stack keys. Tests in this folder may instantiate the moved
  right-panel widgets when asserting cross-page behavior, but those imports
  should come from `ui.right_panel.pvp.*`, not from the old compatibility
  exports in `ui.pvp_browser.window`.
  PvP offscreen smoke has two modes: default synthetic fixtures for a stable
  temp-data full loop, and `--account` for real local PvP deck presets/account
  assets. The account mode should catch post-draft Ready regressions caused by
  numeric/localized weapon type or observed stack identity mismatches. It reads
  local data but must not write session/history files. PvP offscreen smoke
  should also verify the default deck path, first/second activation timing, that
  edit tint is scoped to the card grid viewports when this area changes, and
  that collapsed/inactive PvP seats do not reserve large empty right-panel
  geometry. Post-draft UI regressions should additionally pin the vertical
  right-panel accordion hierarchy, absence of a right painted side accent,
  collapse/expand without model/grid refresh, safe non-window source
  reparenting, and normal AppShell-compatible occupied-weapon swap behavior in
  scoped runtime state. Geometry regression tests must show both seat sections
  expanded at usable shell sizes for the 1408x640 minimum, 1600x900, and
  1920x1080 monitor profiles and pin equal left/right visual Y coordinates,
  equal seat heights, one physical character row, and the fixed character
  viewport. A dedicated content-sizing regression must show the weapon viewport
  matching the full natural multi-row grid when space exists and shrinking with
  vertical scroll only when the containing player section/window is too short.
  The assignment
  transition test installs an application event filter and rejects every newly
  shown top-level QWidget; this covers parentless `setVisible(true)` regressions
  that a `setParent(None)`-only assertion misses.
  `test_pvp_profile_integration.py` uses temporary synthetic sources to check
  same-ID per-seat stats and inventories, a shared neutral portrait across pool
  scopes/Pick/Ban/results, all-shared local priority, missing-id/file archive
  fallback, preserved portrait alpha, isolated controllers/equipment,
  failed replacement preservation and managed cleanup without changing the
  fixture's main DB/decks. `tests/ui/character_assets/test_character_assets.py`
  also checks that a foreign profile may reuse a neutral common variant by game
  id while preserving its constellation and account-specific History boundary,
  without falling back to baked browser/side icons when the source layer is absent.
  These headless checks are not real-user smoke acceptance. That pending gate
  and the user's no-Computer-Use restriction are in `PVP_PROFILE_PACKAGE.md`.
- `tests/ui/artifact_browser/` - Artifact Browser UI-side models/actions/stat
  localization.
- `tests/ui/gcsim_browser/` - GCSIM Browser UI worker behavior.
- History left-browser integration currently lives in
  `tests/ui/app_shell/test_app_shell.py`, with catalog tests under
  `tests/run_workspace/history/` and card tests under
  `tests/ui/right_panel/history/`. A separate `tests/ui/history_browser/`
  package has not been created; do not use that path as a runnable suite.
  Geometry tests that assert a named logical width must patch
  `HistoryCardWidget.content_scale` to the intended reference scale; otherwise
  an earlier process-wide Qt scale test can change layout breakpoints. Tooltip
  windows/timers are lazy and should be created only by hover tests.
- `tests/ui/utils/` - shared UI utility tests. HiDPI coverage includes opt-in
  alpha trimming, preservation of alpha=1 silhouette edges and source bytes,
  and distinct cached results for trimmed versus full-canvas images.
- `tests/ui/character_assets/` - `ui/character_assets.py` behavior.
- `tests/tools/future/` - reusable future/admin tools.

Root `tests/` should contain only package markers and top-level helpers. Do not
add new feature tests directly in the root.

## Running

Prefer the narrowest suite that covers the touched ownership area:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests\ui\artifact_browser -t . -p "test_*.py"
.\.venv\Scripts\python.exe -m unittest discover -s tests\ui\pvp_browser -t .
.\.venv\Scripts\python.exe -m unittest discover -s tests\ui\right_panel -t . -p "test_*.py"
.\.venv\Scripts\python.exe -m unittest discover -s tests\run_workspace\gcsim -t . -p "test_*.py"
.\.venv\Scripts\python.exe -m unittest discover -s tests\run_workspace\history -t . -p "test_*.py"
.\.venv\Scripts\python.exe -m unittest discover -s tests\run_workspace\session -t . -p "test_*.py"
.\.venv\Scripts\python.exe -m unittest discover -s tests\run_workspace\pvp -t .
.\.venv\Scripts\python.exe -m unittest tests.hoyolab_export.account.test_offline_profile
.\.venv\Scripts\python.exe -m run_workspace.pvp.free_draft_controller_smoke
.\.venv\Scripts\python.exe -m run_workspace.pvp.free_draft_controller_smoke --json
.\.venv\Scripts\python.exe -m run_workspace.pvp.free_draft_controller_smoke --step-demo
.\.venv\Scripts\python.exe -m run_workspace.pvp.ui_full_flow_smoke
.\.venv\Scripts\python.exe -m run_workspace.pvp.ui_full_flow_smoke --account
.\.venv\Scripts\python.exe -m run_workspace.pvp.ruleset_applicability_smoke
.\.venv\Scripts\python.exe -m run_workspace.pvp.account_deck_export_smoke
.\.venv\Scripts\python.exe -m run_workspace.pvp.account_full_loop_smoke
.\.venv\Scripts\python.exe -m run_workspace.pvp.session_bundle_smoke
.\.venv\Scripts\python.exe -m run_workspace.pvp.ruleset_balance_smoke
```

Full-suite command:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -p "test_*.py"
```

Run the full suite only for broad shared changes, test-infrastructure changes,
or when explicitly requested.

## Handoff maintenance tooling

`tools/check_handoffs.py` is a read-only stdlib documentation check.
Run it after affected handoff changes, together with the semantic closeout in
[HANDOFF_MAINTENANCE.md](HANDOFF_MAINTENANCE.md).

When changing the checker, run its isolated synthetic-file regressions:
`.venv\Scripts\python.exe -m unittest tests.tools.test_check_handoffs`.
These cover orphan/duplicate index entries, broken pointers, current projection
drift, historical exclusions, budgets, current markers and read-only behavior.
They do not import the app or inspect real account data; no product/UI acceptance
can be inferred from their result.

## Rules

- Place each test next to the primary source owner. For cross-boundary behavior,
  put the test under the coordinator that owns the contract being asserted.
- Keep tests deterministic and local. Do not use network, browser profile,
  real account data, generated assets, or ignored runtime folders unless the
  test is an explicit smoke/integration test with temp paths or mocks.
- Use temporary directories/databases and patch module-level paths instead of
  reading or mutating real `data/`, `assets/hoyolab/`, `hoyolab_export/profile`,
  or `data/gcsim/`.
- Prefer focused unit tests for domain logic. UI tests should isolate view-models
  when possible; Qt widget tests must construct only the widgets they verify and
  avoid app-wide startup.
- Name files by behavior or source area: `test_<feature>.py`. Use `_smoke` only
  for deliberately wider checks.
- Keep arrange/act/assert easy to edit. Add short comments around the part of a
  scenario that future tasks are expected to change; avoid comments that merely
  restate an assertion.
- Temporary fixtures, hardcoded research data, provisional adapters, or
  intentionally incomplete behavior need a short comment/docstring explaining
  the source, what future implementation should replace, and what contract the
  test pins.
- If fixtures are reused across folders, prefer a small colocated helper module
  such as `_fixtures.py` over importing helpers from another `test_*.py`. Some
  older tests still import from peer test modules; do not extend that pattern.
- Assert stable ids, typed fields, and data contracts instead of localized
  display text unless localization behavior itself is under test.
- When source files move or ownership changes, move the corresponding tests in
  the same task and update handoff references.
