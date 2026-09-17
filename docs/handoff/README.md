# Project Handoff Map

Reconciled 2026-09-16 through document/source inspection. This maintenance pass
does not rerun product checks, public research or performance measurements.
The documentation checker is validated separately with synthetic fixtures.

## Reading And Authority

1. Read `CODEX.md` for stable operating rules and architecture entrypoints.
2. Read `TODO.md` for open work and the latest user-decided ordering.
3. Read only the owner document for the selected subsystem below.

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
| [HANDOFF_MAINTENANCE.md](HANDOFF_MAINTENANCE.md) | Mandatory closeout, compaction, consistency checks and history policy |

## Account, Data And Artifacts

| Document | Role |
| --- | --- |
| [DATA_RUNTIME_BOUNDARIES.md](DATA_RUNTIME_BOUNDARIES.md) | Current source/cache, SQLite, assets/catalogs and normal offline-profile boundaries |
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
| [MAIN_UI_RIGHT_PANEL_INTEGRATION_AUDIT.md](MAIN_UI_RIGHT_PANEL_INTEGRATION_AUDIT.md) | Right-panel package ownership and legacy boundary |
| [RUN_WORKSPACE_SNAPSHOT_CONTRACT.md](RUN_WORKSPACE_SNAPSHOT_CONTRACT.md) | Live typed session, immutable saves and launch-readiness review |
| [HISTORY_BROWSER.md](HISTORY_BROWSER.md) | Shared read-only snapshot contract, implemented cards/export and scoped UI verification |
| [History visual workspace](../design/history/README.md) | Original Akasha references, approved starting concept, user wording and real app/PNG samples for refinement |
| [PRELOADER_BACKLOG.md](PRELOADER_BACKLOG.md) | Deferred loader work; remeasure dated costs before implementation |
| [performance_measurements/](performance_measurements/) | Historical device/commit-specific measurements, not current guarantees |
| [TESTS.md](TESTS.md) | Test ownership, focused commands and validation rules |

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
| [GCSIM_OPTIMIZER_DEPENDENCY_AUDIT_20260916.md](GCSIM_OPTIMIZER_DEPENDENCY_AUDIT_20260916.md) | Active dependency repair/archetype audit plan and work notes; release acceptance remains in GP-3 |
| [GCSIM_GOB11_GP3_CHECKPOINT.md](GCSIM_GOB11_GP3_CHECKPOINT.md) | Current GP-3 installation, bounded formula/search evidence, limits and resume |
| [GCSIM_OPTIMIZER_TRACE_EQUATION_CLEANUP_MANIFEST.json](GCSIM_OPTIMIZER_TRACE_EQUATION_CLEANUP_MANIFEST.json) | Current disposition and explicitly historical migration/pilot records |
| [GCSIM_GOB11_ROTATION_VALIDATION.md](GCSIM_GOB11_ROTATION_VALIDATION.md) | Supplied-fixture provenance and validation chronology; resume through GP-3 |
| [GCSIM_GOB11_GENERIC_FORMULA_PATH_AUDIT.md](GCSIM_GOB11_GENERIC_FORMULA_PATH_AUDIT.md) | Source/compiler design audit and dated implementation checkpoints |
| [GCSIM_GOB11_GP1C_CHECKPOINT.md](GCSIM_GOB11_GP1C_CHECKPOINT.md) | Historical GP-1c acceptance; its engine is GP-3 rollback, not active production |
| [GCSIM_ENGINE_UPDATE_COMPATIBILITY_AUDIT.md](GCSIM_ENGINE_UPDATE_COMPATIBILITY_AUDIT.md) | Historical compatibility repairs and retained limits; not current engine IDs |
| [GCSIM.md](GCSIM.md) | Original upstream research; not the active implementation queue |

## PvP And Deferred Research

| Document | Role |
| --- | --- |
| [PVP_V0_CONTRACT.md](PVP_V0_CONTRACT.md) | Stable offline hot-seat product/backend contract |
| [PVP_BACKEND_STATUS.md](PVP_BACKEND_STATUS.md) | Implemented modules, smoke paths and backend gaps |
| [PVP_UI_ROADMAP.md](PVP_UI_ROADMAP.md) | Current Decks/Play/Draft/build/timer UI and later stages |
| [PVP_PROFILE_PACKAGE.md](PVP_PROFILE_PACKAGE.md) | Immediate independent-provider then portable-profile sequence |
| [PVP_REFERENCE_SITE_AUDIT.md](PVP_REFERENCE_SITE_AUDIT.md) | Dated Abyss Draft/Gentor product-reference research |
| [PVP_RULESETS_AUDIT.md](PVP_RULESETS_AUDIT.md) | Historical tournament source research |
| [PVP_RULESET_SOURCE_MATRIX.md](PVP_RULESET_SOURCE_MATRIX.md) | Source/applicability map; import work paused pending usable sources |
| [FAR_FUTURE_TODO.md](FAR_FUTURE_TODO.md) | Non-MVP ideas; read only when requested |

## Maintenance Entry

Follow the documentation lifecycle linked above on every relevant task,
including failed/partial outcomes. Update one current owner, reconcile affected
pointers/tasks/projections, preserve historical evidence and concurrent edits,
then complete structural and semantic checks before the final reply.
`docs/obsidian/` remains user-owned optional material, outside this lifecycle.
