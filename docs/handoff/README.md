# Project Handoff Maps

This folder stores detailed project maps and research handoffs. Root `TODO.md`
and `CODEX.md` remain the main entrypoints; link here for durable details
instead of duplicating long research notes in root docs.

Current maps:

- `DATA_RUNTIME_BOUNDARIES.md` - compact source/cache vs runtime SQLite vs asset/static catalog boundary map.
- `ACCOUNT_CHARACTER_DETAIL_FIELDS.md` - HoYoLAB account character detail payload field reference.
- `ACCOUNT_SQLITE_STORAGE.md` - clean local SQLite account characters, talents, and observed weapon stacks.
- `ACCOUNT_EQUIPMENT_STATE_DESIGN.md` - design and implemented service/UI status for persistent current weapon/artifact equipment state, separate from build presets and HoYoLAB observations.
- `ARTIFACT_BROWSER_EQUIPMENT_UX.md` - Artifact Browser equip-mode UX, current equipment zone, preset apply behavior, and artifact/preset/weapon owner side-icon model.
- `ARTIFACT_OPTIMIZER.md` - real-account Artifact Optimizer backend, search/diagnostic contract, official Genshin Optimizer research, GCSIM boundary, and next evaluator stages.
- `ABYSS_ENEMY_DATA.md` - Abyss enemy data source research.
- `ABYSS_ENEMY_DATA_AUDIT_TASK.md` - original prompt for the Abyss enemy data audit.
- `ABYSS_HP_FIXTURE.md` - historical `2026-05-16` Floor 12 HP research/debug fixture and source-join notes; not current runtime factual-DPS truth.
- `ABYSS_MECHANICS_NOTES.md` - Abyss enemy mechanics parser tags and source notes.
- `GCSIM.md` - GCSIM research and integration notes.
- `GCSIM_ENGINE_INTEGRATION_PLAN.md` - authoritative current GCSIM status plus the historical implementation record for engine updates, patches, selected-team configs, sequential Abyss waves, typed results/history, and remaining UI/release work.
- `FAR_FUTURE_TODO.md` - non-MVP PvP, analytics, draft bot, support/donation, monetization, and optional AI companion ideas.
- `PVP_V0_CONTRACT.md` - stable PvP v0 product/backend contract for the full offline hot-seat loop: deck JSON, pick/ban, teams, weapons, timers, and winner summary.
- `PVP_BACKEND_STATUS.md` - implementation-oriented PvP backend status:
  modules, smoke commands, generated/private paths, tests, and known gaps.
- `PVP_UI_ROADMAP.md` - PvP AppShell/UI roadmap: Decks-first direction,
  left/main vs right-panel split, local Play setup, unified-pool Draft target,
  current v0 stages, and target scoped PvP build flow.
- `PVP_REFERENCE_SITE_AUDIT.md` - Abyss Draft and Gentor reference-site findings used by the PvP v0 contract.
- `PVP_MODE_PLAN.md` - PvP planning history for local hot-seat Free Draft, deck JSON, future relay lobby, roadmap, risks, and resolved/open questions.
- `PVP_RULESETS_AUDIT.md` - PvP/tournament ruleset source audit.
- `PVP_RULESET_SOURCE_MATRIX.md` - current public/source matrix for mapping
  Gentor/Abyss/manual rulesets onto the PvP backend. Ruleset mapping is paused
  until real usable tournament files exist.
- `STAT_NORMALIZATION.md` - stat normalization and GCSIM stat-key mapping handoff.
- `MAIN_UI_RIGHT_PANEL_INTEGRATION_AUDIT.md` - compact audit of legacy
  main-window right-panel boundaries and current `ui/right_panel/` target
  ownership.
- `APP_SHELL_WORKSPACE_PLAN.md` - target AppShell architecture: left workspace host plus fixed right operations dock, with staged migration notes.
- `RUN_WORKSPACE_SNAPSHOT_CONTRACT.md` - Run Workspace session/snapshot contract
  for durable history, GCSIM result attachment, and the future `main.py` switch.

Durable backend modules:

- `run_workspace/artifact_optimizer/` - read-only real-account artifact search
  with fixed/excluded/equipped/main-stat filters, set/stat constraints,
  branch-and-bound pruning, explicit exact/best-found diagnostics, snapshot
  conversion, and an optional expensive final-evaluator seam. Tests live in
  `tests/run_workspace/artifact_optimizer/`; details and CLI examples are in
  `ARTIFACT_OPTIMIZER.md`.
- `run_workspace/pvp/` - backend-only PvP v0 foundation for deck JSON,
  `DeckValidationReport`, Free Draft v0 schedule/reducer/action log,
  post-draft team and weapon assignment validation, match timer/result
  summaries, and local-account Free Draft deck export from SQLite runtime
  account data. It also contains the deterministic Free Draft smoke planner,
  draft-system registry, local Free Draft controller/projection API, the
  UI-facing board/read-model projection bridge with `unified_pool`, committed
  board contract sample at
  `samples/pvp/ui_contract/free_draft_board_projection_sample.json`, session
  bundle snapshot/verifier, local-account full-loop smoke, and report-only
  ruleset applicability/deck cost-preview/ruleset-balance application research
  helpers. Deterministic dev smoke commands: `python -m
  run_workspace.pvp.full_loop_smoke`, `python -m
  run_workspace.pvp.free_draft_controller_smoke`, `python -m
  run_workspace.pvp.ruleset_applicability_smoke`, `python -m
  run_workspace.pvp.account_deck_export_smoke`, `python -m
  run_workspace.pvp.account_full_loop_smoke`, `python -m
  run_workspace.pvp.session_bundle_smoke`, and `python -m
  run_workspace.pvp.ruleset_balance_smoke`. Backend fixtures/tests live in
  `samples/pvp/` and `tests/run_workspace/pvp/`; PvP Browser UI tests live in
  `tests/ui/pvp_browser/`.

Rules:

- When adding or changing a persistent structure, source format, data model, or
  long-lived UI/data contract, update the relevant handoff map in this folder
  and keep root docs as concise pointers.
- `docs/obsidian/` is a user-owned folder for optional human maps. It is not
  source of truth; ignore it unless the user explicitly asks to work on
  Obsidian maps.
