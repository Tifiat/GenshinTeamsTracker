# CODEX: GenshinTeamsTracker

This file is written for future coding agents. Keep it compact, English, and mostly ASCII so it is cheap to read and unlikely to cause encoding friction.

## Operating Rules

- The user usually writes in Russian, but project handoff files should stay in English.
- Be frugal with context and tool output.
- Prefer narrow `rg` queries and small file slices.
- The user explicitly forbids subagents/parallel agents for this repository
  because they multiply model usage. Work sequentially in the current
  user-visible task. If a separate persistent context would materially help,
  stop and ask the user to create or assign a visible worker task; never spawn
  a subagent or delegate automatically. A direct user request for a concrete
  subagent task temporarily authorizes only that delegation; it does not enable
  unsolicited or continuing parallel work.
- The dated 2026-09-17 overnight exception was not a permanent repeal. Its N0
  cleanup is complete and its heartbeat was deleted; do not recreate either
  workflow. Continue only the explicitly selected stage. The optimizer handoff
  and TODO own remaining scope; History Browser stays excluded.
- Any new persistent generated/temp output needs an owner, finite retention
  policy, actually wired cleaner and focused deletion/preservation tests in the
  same change. An ignored folder or a cleanup TODO is not a lifecycle. Research
  copies must name a deletion gate and keep only minimal reproducible evidence
  after it; no accumulating cloned source trees/build caches. Measure generated
  bytes before/after heavy experiments. See DATA_RUNTIME_BOUNDARIES.md.
- New disposable optimizer experiments must use
  `tools/managed_optimizer_experiment.py` (one whole capture/export sequence)
  or an equivalent tested lifecycle, with all generated paths in its owned
  scratch scope. It cleans on exit; failed cleanup/orphan residue blocks another
  allocation. Never bypass that block by inventing a new scratch/cache folder.
  Export minimal evidence first. Legacy scripts are not exempt when rerun;
  adapt their outputs or scope them before running, not after disk growth.
- Treat model/context usage as a scarce project resource. Work sequentially,
  reuse accepted traces/fixtures, prefer one narrow diagnostic over broad
  exploration, and do not brute-force architecture, patches, parameters or
  candidate simulations. For one blocker, allow at most three substantive
  repair attempts by default. A substantive attempt is a changed hypothesis or
  implementation followed by its focused validation; invocation/reporting
  mistakes do not consume the repair budget. After three failed substantive
  attempts, stop, preserve evidence, explain the first unresolved loss and ask
  the user to decide. A fourth attempt requires explicit user approval or new
  evidence that changes the failure category; never silently expand the budget.
- Keep engine calls separately budgeted. Do not replace an incomplete offline
  model with per-candidate GCSIM brute force. If uncertainty exceeds the frozen
  exact-finalist budget, stop widening exact verification and return a visibly
  degraded best-effort result; do not stop the offline equation scorer and do
  not launch an unbounded verification loop.
- GCSIM energy mode has one persisted source,
  `gcsim_boosted_energy_enabled`, shown in Account/Settings and the optimizer.
  Infinite Selected maps to `ignore_burst_energy=true`; finite mode uses engine
  `gtt_energy_ledger_v1`, Go artifact-ER deadline constraints and ordinary
  real-energy finalist verification for Selected/All Sets. Theory currently
  fails closed in finite mode pending an ER-aware farming solver. Formula
  capture ignores burst costs to observe the full schedule; only final
  verification executes real costs. Never
  add a second setting or infer particles from action/character names. Fail
  explicitly when no feasible inventory assignment exists. TODO owns stage order.
- GCSIM owns gameplay formulas. GTT observes source arithmetic, runtime paths
  and input ownership; never duplicate Lunar/Stellar coefficients or hardcode
  character/region rules in the consumer. Unknown operands, ancestry and
  branch/task/schedule changes remain diagnosed local boundaries. Zero wholly
  frozen hits does not prove complete dependency coverage. Read the optimizer
  contract and its linked current checkpoint before changing this area.
- A set-package change cannot reuse a captured formula merely because hit
  topology is unchanged. Require a scoped effect-replacement proof or fresh
  context capture; a recognized2p stat assignment alone is not that proof.
  Keep set-effect changes separate from raw artifact contributions and never
  leave an old buff in place while adding the replacement.
  Static replacement attestations are trusted verifier output, never UI flags
  or inferred from a passing point witness. The isolated context pilot has no
  enabled real-set proof producer; its synthetic certificates are test-only.
  Source-discovered amount alternatives and old-context increment probes are
  proposal features, not an additive set total or changed-set DPS. Neutral input
  annotations must bind exact graph nodes and actual input owners, not displayed
  damage actors or matching numeric values; see the Go design.
- NonExtraStat must preserve Extra exclusion; never substitute ordinary Stat.
  Validate original-flat recipes against their original producer before later
  additions, and preserve observed evaluation count/order and cross-owner inputs.
  A trace provider identifies executing code, not necessarily the stat owner;
  bind artifact coordinates to the typed receiver/owner, including foreign HP.
  Capture eligible health-input expressions at their original evaluation point,
  once; do not reconstruct a saved input by re-reading later mutable stats.
- Controlled stat-response probes must preserve the original character
  declaration/initialization order, seed and settings. Append stat changes;
  prepending a character statement can reorder the party and change RNG.
  Diagnose alignment separately from formula error; test-runner success is not
  a response-acceptance pass. Generated build overlays must resolve to the
  actual installed source, not obsolete updater staging paths.
- When the user is asking to discuss, clarify, reason about, decide on rules, or validate an approach, treat the turn as discussion-only. Do not edit files or apply changes until the user explicitly asks to implement, apply, save, or write them. This rule applies by intent in any language, not by exact words.
- Do not treat an acknowledgement of understanding as permission to implement. Phrases in any language that mean "I understand", "got it", "yes, that is the idea", or similar are not approval to edit files.
- Before implementing a task specification, do a brief preflight against the relevant current code and handoff contract. Look for incorrect assumptions, contradictions, missing ownership boundaries, and wording that can reasonably lead to materially different architecture, behavior, or visible UI. Ask focused questions and wait for answers before editing when those issues affect the solution. Do not turn this into a questionnaire for incidental details that can be resolved safely from existing project patterns.
- The user leaves room for engineering judgment on local technical decisions that are not fixed by the task. After the preflight contract is clear, discover and fix narrow implementation defects needed for a correct result, even if the task author could not know about them. Example: replace display-text-based control routing with stable ids when localization makes the existing shortcut unsafe. If a discovered issue requires a broader redesign or a separate product decision, report it as a follow-up instead of silently expanding scope.
- If a user term can reasonably refer to multiple UI, data, or architecture entities, do not silently choose one when the interpretations would materially change the implementation or the answer. State the plausible meanings briefly, ask which one is intended, and wait for clarification before proceeding. Apply the same rule to technical questions, not only file edits. Do not ask unnecessary questions when the ambiguity does not affect the result.
- If the user asks to make UI "like" an existing project surface, inspect and reuse that working implementation pattern before inventing a new one. First identify the working class/function, coordinate system, parent or viewport used for painting, constants controlling size/offsets, and whether layout size is affected.
- For visual placement bugs, do not repeatedly tweak offsets after failed screenshots. After one failed visual attempt, stop and inspect coordinate systems and actual rects. After two failed attempts, ask for confirmation or more data before further changes.
- Before changing Qt overlay or painting coordinates, identify the source and target coordinate spaces. Do not use `mapTo(other_widget, ...)` for sibling overlays unless the widget relationship is verified; use a known common ancestor or global mapping when needed.
- Do not anchor normalized icon assets by alpha bounds unless the user explicitly asks for content-aware placement. If assets share a calibrated canvas, position the full canvas with one formula and treat silhouette differences as intentional content inside that canvas.
- Do not claim understanding and start implementing if the requested visual or coordinate model is not concrete. Restate what stays unchanged, what layer changes, what coordinate anchor is used, and what existing implementation is being copied; ask a question if any of those are unclear.
- Final AppShell startup must support adaptive downscale on screens narrower
  than the 1920px reference width. Keep the calibrated design/layout constants;
  scale the rendered UI down instead of compressing layouts or lowering minimums.
- Do not recursively list or read generated/private state unless explicitly needed:
  - `hoyolab_export/profile`
  - `data/`
  - `assets/hoyolab`
  - `assets/artifact_sets`
  - image folders and large JSON dumps
- Do not run tests, imports, app startup, DB scans, image parsing, or broad validation unless the user asks or the current code change genuinely needs it.
- Use `.venv\Scripts\python.exe` for local checks when the system interpreter lacks project dependencies.
- If the user says "look only", "do not run", "just understand", or asks for handoff/context updates, inspect only lightweight text metadata and update notes.
- Never revert user changes. The worktree is often dirty.
- Use `apply_patch` for file edits.
- In this repo, handoff context means `CODEX.md`, `TODO.md`, and `docs/handoff/*.md`. When the user asks to update or clean handoffs, include all three entrypoints unless they narrow the scope.
- `tools/future/` is reserved for narrow debug/manual utilities that are useful now
  and may become product/admin features later. Do not put ordinary experiments
  there. Use it only when the user explicitly asks, after clarification, or when
  a tool is genuinely reusable and no planned product surface owns it yet.
  Research probes still belong under `tools/experiments/`.
- Complete [handoff maintenance](docs/handoff/HANDOFF_MAINTENANCE.md) before
  the final reply whenever implementation, saved decisions or evidence change,
  including failed/partial results. Reconcile affected owners, TODO and live
  manifests; compact stale/duplicate content in the same task. Run the lightweight
  handoff checker and the required semantic review; a warning to clean later
  does not satisfy closeout.
- User-reported bug fixes require final verification through the user's actual
  interaction path on their computer. Identify the real launcher/run configuration,
  entrypoint, interpreter, working directory and visible app window; reproduce
  the reported controls/sequence there. After editing, ensure that process uses
  the updated code (restart/rebuild when needed), then perform the same visible
  interactions using Computer Use and inspect the final result and adjacent
  persistent state. Include restart/retry when relevant to the reported failure.
- Unit tests, direct backend calls, isolated widgets, offscreen Qt, smoke runners
  and calling a button handler from Python supplement this check; none replace
  a real click through the user's running UI. Do not call a fix complete based
  only on those substitutes or leave the final reproduction to the user when
  agent-side computer interaction is available and authorized. If access,
  authentication or another real blocker prevents this, state the exact blocker
  and unverified path; do not label the user-facing bug fixed.
- Final reports must distinguish automated tests from actual user-path checks,
  identify the launch/control path exercised and state remaining limitations.
  For UX changes also include a short repeatable smoke checklist: concrete
  controls, expected visible result and preservation checks. The checklist is
  a record of the check, not a substitute for performing it.
- After every completed pushable task, include one short Russian commit-message
  suggestion in impersonal passive/resultative wording, not first-person past
  wording. Prefer a style equivalent to "has been added/fixed/updated" or
  "added/fixed/updated as a completed result", not a style equivalent to "I
  added/fixed/updated".
- When adding or changing any persistent project structure, source/cache format, domain model, or long-lived UI/data contract, update the relevant handoff map under `docs/handoff/` and keep root docs as concise pointers. Examples: backend data model -> architecture/data map; raw payload discovery -> source-field reference; UI prototype contract -> UI architecture notes; GCSIM/Abyss research -> dedicated handoff file.
- `docs/obsidian/` is a user-owned folder for optional human maps. It is not
  source of truth; ignore it unless the user explicitly asks to work on
  Obsidian maps.
- Project SVG UI icons should go through `ui/utils/icon_utils.py` auto-contrast helpers instead of direct raw SVG loading or hardcoded final icon colors. This is needed for future theme support.
- Any new user-facing UI text must be added through `localization/locales/*.json` and read with the localization helpers (`tr` / `tr_for_language`) instead of being hardcoded in widgets, view-models, or tooltip formatters. Debug/provenance strings can stay internal, but anything visible in the app needs ru/en/pt-br entries when the feature is added.
- New user-facing tooltips must be custom in-app tooltips, not native Qt/system
  tooltips. Do not use `QToolTip` or `QWidget.setToolTip(...)` for new UI
  features except to explicitly clear/suppress a native tooltip while a custom
  tooltip controller is installed. If a task says "HTML/text tooltip" or "first
  pass text tooltip", interpret that as the content rendered inside the custom
  tooltip surface, not permission to use the native Qt tooltip. If the existing
  custom tooltip helper cannot support required content such as images, keep a
  typed tooltip payload in the view-model and implement the narrow custom text
  popup first; do not fall back to a native tooltip silently.
- Performance optimization policy before the dedicated startup loader/prewarm
  stage: optimize by reducing total computation, duplicate work, algorithmic
  cost, or needless widget/pixmap rebuilds. Do not improve perceived latency by
  merely moving cold work to a later click, timer, background hydration,
  lazy-created tab, or hidden prewarm unless the user explicitly asks for the
  loader/cache/prewarm stage. Until that stage starts, keep lag sources visible
  and measurable so they can be covered by one explicit loader plan.
- If a feature performs expensive repeatable work, do not keep it only in UI hot paths and do not rely only on in-memory cache. Use in-memory cache for repeated work inside one session and persistent local cache under `data/cache/...` for results reusable between window/app openings only when that cache/prewarm work is the approved task or part of the explicit loader plan. Examples include trim/mask/composite pixmaps, scaled/tinted asset preparation, external/catalog parsing, expensive derived data, and any repeated operation causing visible delay when reopening a window/app or switching views. Create cache directories automatically. Cache keys must include all inputs affecting output: source file path or stable id, source file mtime/size or content hash where applicable, target dimensions, algorithm/cache version, and visual parameters such as padding, alpha threshold, feather, badge text, theme/colors if relevant. Recompute only when the cache key/version/input changes. Do not do expensive image processing/parsing directly in `paintEvent` or frequent UI hot paths. If a new feature introduces visible delay, identify the expensive step first, then design cache/invalidation explicitly.
- When profiling finds a repeatable but non-urgent prewarm/cache candidate, record it in `docs/handoff/PRELOADER_BACKLOG.md` and keep only a compact pointer in `TODO.md`. Do not silently drop these findings, and do not immediately hide current bugs behind a loader unless that is the approved task. New lag sources sent to the future loader/prewarm stage must include measured cost, device/commit context, why the work remains necessary, and what the loader should eventually bake/prewarm/cache.
- Future storage direction: do not migrate every generated JSON/cache file into SQLite. Keep JSON when it is a small rebuildable source cache or seed-like file. Account character/weapon runtime tables now exist in local SQLite; for remaining catalog/cache data, audit usage and move only runtime-critical, frequently joined, mapped, filtered, queried, reported, or stat-calculator data into normalized SQLite/catalog DB tables. A two-layer model is acceptable: raw/source JSON cache for fetched HoYoWiki/HoYoLAB data plus normalized DB tables for lookup, mappings, aliases, reports, UI, and stat calculation. Likely remaining candidates after usage audit include HoYoWiki character stats, weapon stats, character traits, character regions, mapping reports / alias overrides, and any large generated account/catalog JSON that becomes runtime-critical.
- For hot UI panels/lists, especially Artifact Browser and right-panel widgets, avoid destructive widget rebuilds when structure did not actually change. Keep QWidget instances parented in one stable layout and update state/content/visibility in place.
- Do not cache QWidget instances by removing them from layouts and re-adding them later. That pattern caused blank transient windows and multi-second first-init regressions. If widgets are cached, they must stay owned by a stable parent/layout; filtering should usually be `setVisible(...)`, checked-state sync, property sync, and content/icon updates only when source data changes.
- Avoid intermediate visible placeholder states during deferred load/hydration. If fast UI state is followed by async/deferred hydration, cancel stale pending refresh timers and show only the final hydrated panel state unless the placeholder is an intentional loading design.
- Keep panel geometry stable across selected/empty/hydrated modes. Do not let details/side panels collapse or expand in ways that move unrelated content; use stable skeletons, persistent child widgets, and reserved/minimum height where needed.
- AppShell top-level minimum size is a global state-independent contract. Do not rely on the current `QStackedWidget` page or Artifact Browser selected-target/no-target state to define the window minimum; those visibility changes alter `minimumSizeHint()` and can clip the fixed current-equipment/build-preview area.
- AppShell adaptive downscale is a final-app requirement, not only an
  `app_shell_smoke` convenience. When AppShell becomes the production entrypoint,
  run the same startup scaling bootstrap before `QApplication` is created.
- If a layout trace shows different `after` and `settled` geometry, do not trust synchronous `layout.activate()` alone. Prevent the intermediate frame from painting by disabling updates during the model/layout mutation and re-enabling updates on the next event-loop tick after a final layout settle.
- Avoid many child widgets for non-interactive repeated visual strips. Use baked pixmaps when appropriate, while preserving drag, wheel, and edge-hint behavior for scroll strips.
- Dense icon grids that must survive fractional startup downscale should use
  `ui/utils/pixel_icon_grid.py`: one painted surface, integer physical-pixel
  layout math, cached HiDPI pixmaps, item-id signals, and adapter-owned domain
  payload routing. Do not reintroduce QWidget-per-card grids for AppShell or
  PvP icon browsers to hide 1px drift.
- For dense card/grid panels with vertical overflow, prefer `ui/utils/overlay_scroll.py::OverlayVerticalScrollArea` over native vertical scrollbars when scrollbar appearance would change content width. The overlay scrollbar should not reserve layout width, should appear on scroll/edge hover/drag, and should auto-hide when idle.
- Build preset row names must use flexible leftover space, not fixed magic widths. Fixed metadata/actions define the right side; long text should clip/marquee instead of expanding rows or reintroducing horizontal scrolling.
- Reusable pixmap operations belong in `ui/utils`, not inside large window classes. Window classes should resolve data/paths, choose modes, and call helpers rather than owning generic trim/mask/composite/cache logic.
- New PNG/raster UI assets must use the shared high-DPI pixmap path in
  `ui/utils/hidpi_pixmap.py` or an existing helper built on it. Do not add raw
  `QPixmap.scaled(...)` in UI code unless that local code also handles logical
  size, effective DPR, cache keys including DPR/source identity, and
  `DevicePixelRatioChange` / screen-change refresh. Startup `QT_SCALE_FACTOR`
  downscale for small monitors is separate from image DPR; raster assets must
  clamp effective pixmap DPR to at least `1.0` so they are not double-shrunk.
- New or refactored reusable UI code must use shared colors from `ui/utils/ui_palette.py` instead of introducing new literal hex colors. Do not mass-migrate old QSS blocks just for cleanup; migrate legacy colors only when that UI area is being actively changed.
- Reusable filter buttons must use `ui/utils/filter_button_style.py`; do not
  create local filter-button QSS copies.
- For Qt/PySide visual clipping bugs, diagnose geometry before layout tweaks:
  measure widget size, scroll viewport/content size, scrollbar maximum, and QSS
  box-model effects. In QSS, button `min-width`/`max-width` may behave like
  content-box sizing, with border and padding increasing the real outer size.
- If an English technical task contains inconsistencies, suspicious requirements, obvious mistakes, or unclear contradictions, point them out before starting implementation.
- Do not invent concrete correctness-critical values in final code, patches, or task text. Filenames, paths, asset names, localization keys, IDs, function/class names, DB fields/tables, data formats, commands, and API/library versions must be explicitly provided by the user, discovered in current project files, or confirmed by the user first. If such a value is missing, stop and ask; do not insert guessed defaults/placeholders with notes like "change this later".
- When adding new modules or tests that contain temporary fixtures, hardcoded
  research data, provisional adapters, sample-only values, or intentionally
  incomplete behavior, add a short module docstring/comment explaining what is
  temporary, what source/handoff it came from, what future implementation should
  replace it, and which tests are pinning the temporary contract. Do not leave
  placeholders implicit.

## Project And Launch Paths

GenshinTeamsTracker is a local PySide6 desktop application for account import,
team/equipment building, Abyss/DPS runs, immutable History, and offline PvP.

- `main.py` still launches legacy `ui.main_window.App`.
- Current AppShell development/user path: `python -m ui.app_shell_smoke`;
  the recorded user launcher is PyCharm Run Current File on that file with
  the project `.venv/Scripts/python.exe`. Reconfirm the actual running path
  for a user-path check. Do not switch `main.py` without the user's approval.
- Native Windows Computer Use must use trusted `mcp__node_repl__js` with
  `@oai/sky`. Browser-oriented `cua_repl` can report `Trusted RPC service is not
  configured: sky` while the direct route works. If hidden, search deferred
  tools for `node_repl` before declaring it unavailable; then use unique-window
  selection and the real visible path. A shell launch is not a UI click.
- `ui/app_shell.py` coordinates workspaces; feature UI belongs in
  `ui/<area>_browser/`. Right-dock ownership is
  `ui/right_panel/{common,live_run,history,pvp,settings}`.
- `run_workspace/session.py` owns live mode/team/timer/result state;
  `history_snapshot.py` and `history_snapshot_builder.py` own immutable saves.
  Widgets display and command state, not persistence.
- `hoyolab_export/` owns account import, SQLite adapters, catalogs and equipment.
  `native/gcsim_optimizer/` owns the active Go optimizer;
  `run_workspace/gcsim/` owns Python integration and engine lifecycle.

## Read Only The Relevant Handoff

The full index and document authority rules are in `docs/handoff/README.md`.
`TODO.md` contains open work, not the implementation history.

| Work area | Read first under `docs/handoff/` |
| --- | --- |
| Data/source/cache ownership | `DATA_RUNTIME_BOUNDARIES.md` |
| Account tables and source fields | `ACCOUNT_SQLITE_STORAGE.md`, `ACCOUNT_CHARACTER_DETAIL_FIELDS.md` |
| Import failures, lifecycle and verification | `HOYOLAB_IMPORT_RELIABILITY.md` |
| Current equipment | `ACCOUNT_EQUIPMENT_STATE_DESIGN.md` |
| Artifact storage/import/browser | `ARTIFACT_BROWSER.md`, `ARTIFACT_BROWSER_EQUIPMENT_UX.md` |
| UI ownership and launch migration | `APP_SHELL_WORKSPACE_PLAN.md`, `MAIN_UI_RIGHT_PANEL_INTEGRATION_AUDIT.md` |
| Run/History/DPS Dummy | `RUN_WORKSPACE_SNAPSHOT_CONTRACT.md`, `HISTORY_BROWSER.md` |
| Abyss runtime data and mechanics | `ABYSS_ENEMY_DATA.md`, `ABYSS_MECHANICS_NOTES.md` |
| Normal GCSIM and engine updates | `GCSIM_ENGINE_INTEGRATION_PLAN.md`, `GCSIM_ENGINE_UPDATE_COMPATIBILITY_AUDIT.md` |
| Optimizer architecture and next gates | `GCSIM_OPTIMIZER_TRACE_EQUATION_HANDOFF.md`, then its current checkpoint |
| PvP product/backend/UI | `PVP_V0_CONTRACT.md`, `PVP_BACKEND_STATUS.md`, `PVP_UI_ROADMAP.md` |
| Two-player profile exchange | `PVP_PROFILE_PACKAGE.md` |
| Stat units and display boundaries | `STAT_NORMALIZATION.md` |
| Tests and performance follow-up | `TESTS.md`, `PRELOADER_BACKLOG.md` |

Do not load `FAR_FUTURE_TODO.md` for ordinary MVP work unless requested.
`GCSIM.md`, old checkpoints, source audits and measurement reports are dated
evidence; their old next-step labels do not override the current owner document.

## Stable Domain Boundaries

- `data/artifacts.db` is the unified local runtime SQLite DB, despite its name.
  Normal UI reads SQLite adapters; raw HoYoLAB JSON is import/source cache.
  Keep small rebuildable JSON caches where appropriate, not blanket DB migration.
- Character/weapon/artifact identity uses stable IDs and stored resolved keys,
  not localized display names or local image paths. Observed weapons are
  fingerprinted stacks with non-decreasing `known_count`, not unique instances.
- Current equipment, HoYoLAB observations and reusable build presets are
  separate. Removing a team member does not unequip them. Equipment is per
  character, while normal team selection is per mode and PvP equipment is scoped.
- HoYoLAB `Change equipment` is implemented, default OFF. Enabled imports
  apply fresh observations in one validated equipment batch after account sync.
  Missing observations do not mean clear equipment; saved presets are preserved.
- Artifact content twins normally dedupe. Simultaneous distinct HoYoLAB wearers
  can prove extra copies; reuse their IDs on reimport. Never infer copies from
  repeated rows alone. Full import publication across DB/JSON/images is not atomic.
- Account/API content language is separate from UI language. EN service detail
  payloads are mapping input only. Catalog detail refresh is explicit; ordinary
  import must not fetch every HoYoWiki character/weapon detail page.
- Selected-build display stats use base/reference data plus selected equipment,
  not HoYoLAB in-game `final` rows. Apply only explicitly modeled static effects;
  passive text is reference, not a formula. Traveler element modeling is deferred.
- History freezes every occupied slot's display data and visible assets.
  It reuses an isolated read-only Run panel, never live account lookups or a
  permanent PNG preview. Abyss sim results are included by normal Run Save;
  DPS Dummy result attachment and real PvP History remain open.
  [History visual references/notes](docs/design/history/README.md) preserve the
  approved starting concept, rejected first-pass samples and current variants.
  Implementation, verification and visual-review status belong to
  `HISTORY_BROWSER.md`; expansion must transform the existing card in place.
- Fact DPS is HP/time from the production Abyss cache; sim DPS is GCSIM output.
  Missing authoritative period/cache/HP yields unavailable, not the old fixture.
- PvP reuses the normal build UI with independent source providers and scoped
  runtime state. Its development `.gttpvp` is not yet a portable public format.
- The Go optimizer is the sole Selected/All Sets backend. Selected preserves
  currently equipped4p or2+2 packages with one flexible piece; All Sets has a
  separate source-aware bounded package coordinator over the same search,
  capture and final measurement modules. Accepted N1 scouts six contexts, then
  deepens the best and one exploratory context; keep fair discovery lanes.
  Removed Python strategies must not return as fallbacks. Current is
  comparison-only; continuous-target
  Python math is retained only for a future Go port for Theory/All Sets.
  Current acceptance, active engine and user-approved fixture substitutions
  live in `GCSIM_GOB11_GP3_CHECKPOINT.md`; do not duplicate their logs here.

## Localization, Private Data And Scheduling

- Localization is JSON-backed through `localization/i18n.py`; use `tr` /
  `tr_for_language` with synchronized `ru`, `en`, `pt-br` keys.
  Default UI language is `ru`; `GTT_LANGUAGE` / `GTT_LANG` override a process.
  Small preferences live in ignored `settings.json`.
- Never commit cookies, tokens, request headers, browser profiles or private
  debug/network dumps. `data/`, `assets/hoyolab/` and import profiles are local
  generated/private state; sanitized static seeds are a separate explicit scope.
- Normal offline profile export is an allowlisted ZIP with a SQLite backup,
  account JSON/assets and language metadata; it excludes auth/debug/downloads.
  It is separate from PvP exchange. Sign-out/restore are destructive boundaries.
- Scheduled continuation exists only after the automation tool returns a
  persisted active automation ID. A suggested card is not an active schedule.

## Handoff Maintenance

Lifecycle owner: [HANDOFF_MAINTENANCE.md](docs/handoff/HANDOFF_MAINTENANCE.md).
Root rules/pointers, open TODO work, current checkpoints and dated evidence have
separate owners. Update current facts in place and reconcile their dependents.
Ordinary handoff maintenance is included in the authorized task; preserve
concurrent edits and historical evidence. The protocol's structural check is
necessary but does not replace semantic review or product/UI verification.
