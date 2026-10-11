# Full handoff catalog

- [Character card assets and browser presentation](CHARACTER_CARD_ASSETS.md)
- [Character filters and sorting](CHARACTER_FILTERS.md)

This file lists the available handoff documents for discovery and structural
coverage. It is not startup reading. Use `README.md` to choose one area and
read only that area's current status and relevant contract section. Read
`TODO.md` as the shared-queue router when selecting the current stage and
`WORK_BACKLOG.md` as the shared-backlog router when a deferred area is selected.

## Authority

A contract defines allowed behavior; a current checkpoint records implementation
and acceptance; a dated receipt records what happened in that run. Preserve old
failed receipts as evidence. Their engine IDs, task instructions and missing
features do not override the current owner. Source audits are dated research,
not a claim that an external site/API was checked again today.

For the optimizer specifically: the trace-equation handoff owns architecture/
gate order; the Go design owns implementation and historical stage detail;
GP-3 owns current validation/resume; the engine plan owns update/rollback and
normal Browser behavior. The cleanup manifest tracks disposition and distinguishes
current state from historical records. Do not maintain independent status logs
in every file.

## Documentation Lifecycle

| Document | Role |
| --- | --- |
| [README.md](README.md) | Short area router and reading policy |
| [HANDOFF_MAINTENANCE.md](HANDOFF_MAINTENANCE.md) | Durable-fact closeout, compaction and consistency checks |
| [COORDINATION.md](COORDINATION.md) | Shared queue, per-worker ownership and checkout-local technical evidence |
| [ORCHESTRATOR_RULES.md](ORCHESTRATOR_RULES.md) | User-authorized task dispatch, bounded execution reports, monitoring and loop-stop/clarification |
| [integration_receipts/2026-10-04_ready_workers.md](integration_receipts/2026-10-04_ready_workers.md) | Local ready-branch integration sources, combined checks and acceptance limits |
| [integration_receipts/2026-10-06_worker5_history_regression.md](integration_receipts/2026-10-06_worker5_history_regression.md) | Scoped History payload and guarded transparent asset-to-team-data-to-snapshot regression |
| [integration_receipts/2026-10-08_optimizer_launch_hotfix.md](integration_receipts/2026-10-08_optimizer_launch_hotfix.md) | Main launch-only transfer, native consumer install and public real-button gate |
| [integration_receipts/2026-10-08_minimal_optimizer_publication.md](integration_receipts/2026-10-08_minimal_optimizer_publication.md) | Isolated main-based optimizer transfer, focused target checks and publication boundary |
| [OPTIMIZER_WORK_RULES.md](OPTIMIZER_WORK_RULES.md) | Optimizer-only execution and response invariants |
| [UI_WORK_RULES.md](UI_WORK_RULES.md) | UI-only implementation and real-path verification rules |
| [DATA_WORK_RULES.md](DATA_WORK_RULES.md) | Data, generated-output and cleanup rules |
| [WORK_BACKLOG.md](WORK_BACKLOG.md) | Router to shared deferred scopes; active priority routes through TODO |
| [WORKER5_TRANSFER_PACKAGE.md](WORKER5_TRANSFER_PACKAGE.md) | Worker5 source inventories, transfer dependencies, byte fingerprints and acceptance boundaries |

## Account, Data And Artifacts

| Document | Role |
| --- | --- |
| [DATA_RUNTIME_BOUNDARIES.md](DATA_RUNTIME_BOUNDARIES.md) | Current source/cache, SQLite, assets/catalogs and normal offline-profile boundaries |
| [ACCOUNT_PROFILES.md](ACCOUNT_PROFILES.md) | Isolated saved accounts, profile switching/deletion, login and central settings/reset contract |
| [TRAVELER_VARIANTS.md](TRAVELER_VARIANTS.md) | Seven account Traveler variants, source identity, imports, assets and scoped acceptance |
| [ACCOUNT_CHARACTER_DETAIL_FIELDS.md](ACCOUNT_CHARACTER_DETAIL_FIELDS.md) | Observed HoYoLAB character-detail source fields |
| [ACCOUNT_SQLITE_STORAGE.md](ACCOUNT_SQLITE_STORAGE.md) | Runtime characters, talents, identities and observed weapon stacks |
| [ACCOUNT_EQUIPMENT_STATE_DESIGN.md](ACCOUNT_EQUIPMENT_STATE_DESIGN.md) | Implemented persistent equipment service and import-apply contract |
| [HOYOLAB_IMPORT_RELIABILITY.md](HOYOLAB_IMPORT_RELIABILITY.md) | Import lifecycle/failure boundaries, dated checks and remaining limits |
| [ARTIFACT_BROWSER.md](ARTIFACT_BROWSER.md) | Artifact identity/storage, JSON import, browser edit/filter/sort contracts |
| [ARTIFACT_BROWSER_EQUIPMENT_UX.md](ARTIFACT_BROWSER_EQUIPMENT_UX.md) | Operation target, current equipment, preset apply and owner icons |
| [STAT_NORMALIZATION.md](STAT_NORMALIZATION.md) | Implemented stat/unit normalization and display/config boundaries |

## AppShell, History And Performance

| Document | Role |
| --- | --- |
| [APP_SHELL_WORKSPACE_PLAN.md](APP_SHELL_WORKSPACE_PLAN.md) | Current workspace/dock ownership and remaining launch migration |
| [READABLE_ROTATION_EDITOR.md](READABLE_ROTATION_EDITOR.md) | Shared tree, selected-team/action constraints, compact live Readable, command pages, retained draft context and audited variants; full UI acceptance pending |
| [DISPLAY_SCALING.md](DISPLAY_SCALING.md) | Windows system-scaling Settings switch, startup/font/adaptive contract and pre-MVP user acceptance |
| [MAIN_UI_RIGHT_PANEL_INTEGRATION_AUDIT.md](MAIN_UI_RIGHT_PANEL_INTEGRATION_AUDIT.md) | Right-panel package ownership and legacy boundary |
| [RUN_WORKSPACE_SNAPSHOT_CONTRACT.md](RUN_WORKSPACE_SNAPSHOT_CONTRACT.md) | Live typed session, immutable saves and launch-readiness review |
| [HISTORY_BROWSER.md](HISTORY_BROWSER.md) | Shared read-only snapshot contract, implemented cards/export and scoped UI verification |
| [History visual workspace](../design/history/README.md) | Original Akasha references, approved starting concept, user wording and real app/PNG samples for refinement |
| [PRELOADER_BACKLOG.md](PRELOADER_BACKLOG.md) | Deferred loader work; remeasure dated costs before implementation |
| [performance_measurements/](performance_measurements/) | Historical device/commit-specific measurements, not current guarantees |
| [performance_measurements/2026-10-06_guarded_startup_profile.md](performance_measurements/2026-10-06_guarded_startup_profile.md) | Guarded synthetic-profile timing of the actual legacy and AppShell launchers |
| [performance_measurements/2026-10-07_main_startup_and_merge_audit.md](performance_measurements/2026-10-07_main_startup_and_merge_audit.md) | Accepted-copy code/runtime parity, populated startup timings and remaining profile-path/cache gaps |
| [performance_measurements/2026-10-07_populated_startup_package_review.md](performance_measurements/2026-10-07_populated_startup_package_review.md) | Independent Worker3 package review, guarded populated three-pair A/B and preservation boundary; not installed |
| [TESTS.md](TESTS.md) | Test ownership, focused commands and validation rules |
| [TOOLTIP_CONTRACTS.md](TOOLTIP_CONTRACTS.md) | Tooltip semantic families, first-available catalog witness and required regression workflow |

## Abyss

| Document | Role |
| --- | --- |
| [ABYSS_ENEMY_DATA.md](ABYSS_ENEMY_DATA.md) | Production source/cache notes plus historical source audit |
| [ABYSS_MECHANICS_NOTES.md](ABYSS_MECHANICS_NOTES.md) | Dated mechanics/parser research for later UI warnings |
| [ABYSS_HP_FIXTURE.md](ABYSS_HP_FIXTURE.md) | Historical 2026-05-16 HP fixture; never current runtime factual-DPS truth |

## GCSIM And Optimizer

| Document | Role |
| --- | --- |
| [GCSIM_ENGINE_INTEGRATION_PLAN.md](GCSIM_ENGINE_INTEGRATION_PLAN.md) | Current engine/Browser contracts, update/rollback and remaining release work |
| [GCSIM_OPTIMIZER_TRACE_EQUATION_HANDOFF.md](GCSIM_OPTIMIZER_TRACE_EQUATION_HANDOFF.md) | Optimizer architecture, product/search boundaries and gate order |
| [GCSIM_OPTIMIZER_GO_BACKEND_DESIGN.md](GCSIM_OPTIMIZER_GO_BACKEND_DESIGN.md) | Go implementation design and completed stage evidence |
| [GCSIM_BLOOM_WINNER_DIAGNOSTIC_20260916.md](GCSIM_BLOOM_WINNER_DIAGNOSTIC_20260916.md) | Dated failed winner-response diagnosis; proposed repairs, not accepted implementation |
| [GCSIM_OPTIMIZER_DEPENDENCY_AUDIT_20260916.md](GCSIM_OPTIMIZER_DEPENDENCY_AUDIT_20260916.md) | Dated dependency repair/archetype audit evidence; release acceptance remains in GP-3 |
| [GCSIM_GOB11_GP3_CHECKPOINT.md](GCSIM_GOB11_GP3_CHECKPOINT.md) | Current GP-3 installation, bounded formula/search evidence, limits and resume |
| [GCSIM_OPTIMIZER_REFACTOR_AUDIT_20261003.md](GCSIM_OPTIMIZER_REFACTOR_AUDIT_20261003.md) | Dated source/legacy/Git-baseline findings, repaired verification and proposed structural cleanup |
| [GCSIM_OPTIMIZER_ARCHETYPE_AUDIT_20260919.md](GCSIM_OPTIMIZER_ARCHETYPE_AUDIT_20260919.md) | Dated visible-button checks, 14-archetype mode matrix and candidate-quality observations; acceptance remains in GP-3 |
| [GCSIM_OPTIMIZER_TRACE_EQUATION_CLEANUP_MANIFEST.json](GCSIM_OPTIMIZER_TRACE_EQUATION_CLEANUP_MANIFEST.json) | Current disposition and explicitly historical migration/pilot records |
| [GCSIM_GOB11_ROTATION_VALIDATION.md](GCSIM_GOB11_ROTATION_VALIDATION.md) | Supplied-fixture provenance and validation chronology; resume through GP-3 |
| [GCSIM_GOB11_GENERIC_FORMULA_PATH_AUDIT.md](GCSIM_GOB11_GENERIC_FORMULA_PATH_AUDIT.md) | Source/compiler design audit and dated implementation checkpoints |
| [GCSIM_GOB11_GP1C_CHECKPOINT.md](GCSIM_GOB11_GP1C_CHECKPOINT.md) | Historical GP-1c acceptance; current engine/rollback identity belongs to GP-3 |
| [GCSIM_ENGINE_UPDATE_COMPATIBILITY_AUDIT.md](GCSIM_ENGINE_UPDATE_COMPATIBILITY_AUDIT.md) | Historical compatibility repairs and retained limits; not current engine IDs |
| [GCSIM.md](GCSIM.md) | Original upstream research; not the active implementation queue |

## PvP And Deferred Research

| Document | Role |
| --- | --- |
| [PVP_V0_CONTRACT.md](PVP_V0_CONTRACT.md) | Stable offline hot-seat product/backend contract |
| [PVP_BACKEND_STATUS.md](PVP_BACKEND_STATUS.md) | Implemented modules, smoke paths and backend gaps |
| [PVP_UI_ROADMAP.md](PVP_UI_ROADMAP.md) | Current Decks/Play/Draft/build/timer UI and later stages |
| [PVP_PROFILE_PACKAGE.md](PVP_PROFILE_PACKAGE.md) | Immediate independent-provider then portable-profile sequence |
| [PVP_BUILD_SERVICES.md](PVP_BUILD_SERVICES.md) | Scoped artifact/GCSIM services, local period admission, lifecycle and acceptance |
| [PVP_REFERENCE_SITE_AUDIT.md](PVP_REFERENCE_SITE_AUDIT.md) | Dated Abyss Draft/Gentor product-reference research |
| [PVP_RULESETS_AUDIT.md](PVP_RULESETS_AUDIT.md) | Historical tournament source research |
| [PVP_RULESET_SOURCE_MATRIX.md](PVP_RULESET_SOURCE_MATRIX.md) | Source/applicability map; confirmed public Abyss source and remaining adapters |
| [PVP_ABYSS_SOURCE_AUDIT.md](PVP_ABYSS_SOURCE_AUDIT.md) | Current public API, ID/price/constraint mapping, document conflicts and research probe |
| [PVP_DECK_RULES.md](PVP_DECK_RULES.md) | Latest Abyss deck rules, saved versions, costs/UI, portable snapshots and acceptance limits |
| [PVP_DRAFT_RUNTIME.md](PVP_DRAFT_RUNTIME.md) | Cost-difference prebans, per-match controls, draft clocks, source semantics and acceptance |
| [PvP response measurement](performance_measurements/2026-10-09_pvp_selection_pipeline.md) | Synthetic selection timings, downstream hot-path repair and verification boundary |
| [FAR_FUTURE_TODO.md](FAR_FUTURE_TODO.md) | Non-MVP ideas; read only when requested |

## Maintenance Entry

Follow the lifecycle when a durable fact changes. This catalog is checked for
coverage; do not read it wholesale for an ordinary scoped task.
