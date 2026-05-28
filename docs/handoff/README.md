# Project Handoff Maps

This folder stores detailed project maps and research handoffs. Root `TODO.md`
and `CODEX.md` remain the main entrypoints; link here for durable details
instead of duplicating long research notes in root docs.

Current maps:

- `DATA_RUNTIME_BOUNDARIES.md` - compact source/cache vs runtime SQLite vs asset/static catalog boundary map.
- `ACCOUNT_CHARACTER_DETAIL_FIELDS.md` - HoYoLAB account character detail payload field reference.
- `ACCOUNT_SQLITE_STORAGE.md` - clean local SQLite account characters, talents, and observed weapon stacks.
- `ACCOUNT_EQUIPMENT_STATE_DESIGN.md` - design and Stage A status for persistent current weapon/artifact equipment state, separate from build presets and HoYoLAB observations.
- `ARTIFACT_BROWSER_EQUIPMENT_UX.md` - future Artifact Browser equip-mode UX, current equipment zone, preset apply behavior, and artifact/preset/weapon owner side-icon model.
- `ABYSS_ENEMY_DATA.md` - Abyss enemy data source research.
- `ABYSS_ENEMY_DATA_AUDIT_TASK.md` - original prompt for the Abyss enemy data audit.
- `ABYSS_HP_FIXTURE.md` - concrete current Floor 12 HP fixture and source-join notes.
- `ABYSS_MECHANICS_NOTES.md` - Abyss enemy mechanics parser tags and source notes.
- `GCSIM.md` - GCSIM research and integration notes.
- `PVP_RULESETS_AUDIT.md` - PvP/tournament ruleset source audit.
- `STAT_NORMALIZATION.md` - stat normalization and GCSIM stat-key mapping handoff.
- `MAIN_UI_RIGHT_PANEL_INTEGRATION_AUDIT.md` - audit and staged plan for replacing the legacy main-window right panel with fixed Right Panel Prototype v6 plus left workspaces.
- `APP_SHELL_WORKSPACE_PLAN.md` - target AppShell architecture: left workspace host plus fixed right operations dock, with staged migration notes.

Rules:

- When adding or changing a persistent structure, source format, data model, or
  long-lived UI/data contract, update the relevant handoff map in this folder
  and keep root docs as concise pointers.
- Obsidian map maintenance: the Obsidian vault is stored in
  `docs/obsidian/GTT/`. `docs/obsidian/GTT/GenshinTeamsTracker.canvas` is the
  human project navigation map, `docs/obsidian/GTT/DataFlow.canvas` is the
  human data-flow map, and `docs/obsidian/GTT/SourceBoundaries.canvas` is the
  human source/runtime boundary map. These maps do not replace `CODEX.md`/`TODO.md` or the
  detailed handoffs. After meaningful structural changes, update the maps
  together with handoff files when the change affects human understanding of the
  project layout: new major subsystem, renamed/moved important folder, changed
  data flow, changed current priority, changed architecture direction, or an
  important feature moving from planned to active/done. Do not update maps for
  tiny bugfixes, one-line styling changes, or internal refactors that do not
  affect the project map.
