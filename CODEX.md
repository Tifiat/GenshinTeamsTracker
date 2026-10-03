# CODEX: GenshinTeamsTracker

Read this once per task. Read scoped handoffs only when the task touches that
area. A previously read file need not be loaded again unless it changed; inspect
the diff and affected section. English is preferred for project handoffs; user
conversation is usually Russian.

## Work boundaries

- Use narrow `rg` searches/small file slices. Delegate self-contained checks
  and bounded low-context tasks to inexpensive suitable subagents (for example
  `gpt-6-luna` with `max` reasoning). Give a compact task and explicit files;
  do not fork the main chat's large history or duplicate broad project loading.
  Optimizer experiment runs go to these inexpensive agents; the main agent
  analyzes the compact evidence. Bounded implementation with few local files
  may use an inexpensive coding model such as `gpt-6-sol`; delegate it only when
  the setup does not duplicate the main agent's large architectural context.
  Keep context-heavy architecture/integration with the main agent; delegation
  requiring large repeated context needs explicit user approval. Review agent
  results and serialize expensive optimizer runs/shared managed scratch; no
  unattended matrix batches or overlapping edits.
- Preserve other worktree changes. Never revert user changes. Use
  `apply_patch` for local edits. Do not scan generated/private trees
  (`data/`, `hoyolab_export/profile/`, `assets/hoyolab/`, image folders or
  large JSON) unless the task needs them.
- Treat a request to discuss, plan, review or audit as read-only. An
  acknowledgment is not authorization to implement. Before implementation,
  check current code and the relevant contract for conflicting assumptions.
  Ask only when a choice materially changes behavior; resolve local details
  from existing patterns.
- Do not invent correctness-critical paths, IDs, fields, formats, keys or
  versions. Discover them in current source or ask. Mark intentionally
  provisional fixtures/modules with their source, replacement and tests.
- Use focused validation relevant to the change. Do not launch the app, broad
  tests, imports, DB scans or image processing for a documentation-only task.
  Use `.venv/Scripts/python.exe` when system Python lacks dependencies.
  For one unresolved blocker, allow up to three substantive repair attempts
  by default; preserve evidence and ask before an unsupported fourth attempt.
- Protect credentials, profiles and private dumps. Never commit cookies,
  tokens, request headers, browser profiles or private debug/network output.
  Generated files require an owner, finite retention and connected cleanup:
  see `docs/handoff/DATA_WORK_RULES.md`.
- The user authorized automatic local commits of own verified completed stages.
  Cross-branch transfers, push and other Git mutations require explicit
  confirmation. Follow the Git policy/journal through
  `docs/handoff/COORDINATION.md`; never stage unrelated changes.
- Parallel workers use separate Git worktrees. Resolve imports, databases,
  settings, engines, caches and outputs inside the calling worker's checkout;
  never edit another worker's files or share its live database. Git objects and
  refs are shared, so coordinate merges/branch moves. Dependency environments
  may be reused read-only; dependency changes require a separate environment.
- Shared task coordination is linked by `coordination.json` and
  `docs/handoff/COORDINATION.md`. Read the common queue and your own status at
  task selection, scope changes and closeout. Worker1 owns shared queue files;
  each worker writes only its own status. Keep technical docs/evidence with code.
  No shared docs junction or automatic cross-worker acceptance. A missing hub
  is reported, not replaced by another live queue. Other workers' checkouts
  remain write-protected by policy; migrations are applied by their own chat.
- A scheduled continuation exists only after the automation tool returns a
  persisted active ID. A suggested card is not an active schedule.
- `tools/future/` is for explicitly requested or genuinely reusable manual
  utilities without a product owner; research probes belong in
  `tools/experiments/`.

## Read by task

The short router is `docs/handoff/README.md`. Read only the current status
and the relevant contract section for the selected area. Deep design and dated
evidence are consulted for the specific mechanism or failure. `TODO.md` routes
to the one shared active order; read it when choosing or changing stages.
`docs/handoff/WORK_BACKLOG.md` routes to the shared deferred scopes.

| Task | Scoped guardrails |
| --- | --- |
| GCSIM optimizer, formula/set/energy work | `docs/handoff/OPTIMIZER_WORK_RULES.md` |
| AppShell, visual UI, user-path bugs | `docs/handoff/UI_WORK_RULES.md` |
| Account, persistence, generated output/cleanup | `docs/handoff/DATA_WORK_RULES.md` |

Only load another guardrail when the task actually crosses that boundary.
The complete optional catalog is `docs/handoff/CATALOG.md`; it is not startup
reading. Old checkpoints and audits are dated evidence, not current authority.

## Project map

This is a PySide6 desktop app. `main.py` still starts the legacy
`ui.main_window.App`; the AppShell development/user entry is
`python -m ui.app_shell_smoke`. Reconfirm the actual launcher for a UI check;
do not switch production entrypoints without user approval.

- `ui/app_shell.py` coordinates workspaces; feature UI lives under
  `ui/<area>_browser/` and `ui/right_panel/`.
- `run_workspace/session.py` owns live run state; snapshot builders own
  immutable History saves. Widgets display and command state.
- `hoyolab_export/` owns account import, catalogs, SQLite and equipment.
- `native/gcsim_optimizer/` owns the Go optimizer;
  `run_workspace/gcsim/` owns Python integration and engine lifecycle.

## Documentation closeout

Use `docs/handoff/HANDOFF_MAINTENANCE.md` after implementation, saved decisions,
changed acceptance/evidence or handoff edits. Update document owners only for
durable changes; a routine local fix needs no documentary diary. Reconcile
affected facts, run `.venv/Scripts/python.exe tools/check_handoffs.py`, and
review semantics; the checker alone does not prove product behavior.
