# Handoff router

Start with `../../CODEX.md` once per task. For an explicit user task, do not
load the whole TODO or catalog. Choose the affected row below, find its current
status by heading or current marker, then read the relevant contract section.
Open a dated receipt, large design or test file only for the mechanism under
investigation. Within one chat, reread only changed sections or diffs.

| Area | Start here | Conditional guardrails |
| --- | --- | --- |
| Optimizer | [current checkpoint](GCSIM_GOB11_GP3_CHECKPOINT.md), then [trace contract](GCSIM_OPTIMIZER_TRACE_EQUATION_HANDOFF.md) section needed | [optimizer rules](OPTIMIZER_WORK_RULES.md) |
| Normal GCSIM / engine updates | [engine integration](GCSIM_ENGINE_INTEGRATION_PLAN.md) current section | [optimizer rules](OPTIMIZER_WORK_RULES.md) only if optimizer is touched |
| AppShell / History / live run | [workspace](APP_SHELL_WORKSPACE_PLAN.md), [History](HISTORY_BROWSER.md), or [snapshot contract](RUN_WORKSPACE_SNAPSHOT_CONTRACT.md) as appropriate | [UI rules](UI_WORK_RULES.md) |
| Account / catalogs / imports | [profiles/defaults](ACCOUNT_PROFILES.md), [storage](ACCOUNT_SQLITE_STORAGE.md), [import](HOYOLAB_IMPORT_RELIABILITY.md), or [data lifecycle](DATA_RUNTIME_BOUNDARIES.md) | [data rules](DATA_WORK_RULES.md) |
| Artifacts / equipment | [artifact browser](ARTIFACT_BROWSER.md) or [equipment](ACCOUNT_EQUIPMENT_STATE_DESIGN.md) | [data rules](DATA_WORK_RULES.md); [UI rules](UI_WORK_RULES.md) for visual work |
| Abyss data / mechanics | [enemy data](ABYSS_ENEMY_DATA.md) or [mechanics](ABYSS_MECHANICS_NOTES.md) | [data rules](DATA_WORK_RULES.md) when storing outputs |
| PvP | [backend status](PVP_BACKEND_STATUS.md), [UI roadmap](PVP_UI_ROADMAP.md), or [profile](PVP_PROFILE_PACKAGE.md) | relevant UI/data rules |
| Testing / tooltips / performance | [tests](TESTS.md), [tooltip contracts](TOOLTIP_CONTRACTS.md), or [preloader backlog](PRELOADER_BACKLOG.md) | relevant UI/data rules |

The [full catalog](CATALOG.md) is for finding a document not shown here; it is
not mandatory reading. [Coordination](COORDINATION.md) routes to the shared
queue and Worker5 status at task selection, scope changes and closeout.
For Worker5 import/icon/tooltip transfer, use the [source inventory](WORKER5_TRANSFER_PACKAGE.md).
`../../TODO.md` and [deferred work](WORK_BACKLOG.md) are local routers; read only
the selected shared backlog area. A contract owns behavior, a current
checkpoint owns acceptance/next action, and dated evidence owns one observation.
Historical instructions never override the current owner.

When a durable fact or handoff changes, use the [closeout protocol](HANDOFF_MAINTENANCE.md).
