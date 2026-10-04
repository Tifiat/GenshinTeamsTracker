# UI work rules

Read this for AppShell, right-panel, History, browser layout, assets, visual
feedback or a user-reported UI bug. The area contract and current status are
linked from `README.md`; this file contains implementation and verification
guardrails, not another product roadmap.

## Real user path

- A user-reported bug needs final verification through the user's actual
  interaction path. Reconfirm launcher, interpreter, working directory, visible
  window and controls. Restart/rebuild after editing when needed, click the same
  controls, and inspect output plus adjacent persistent state. Backend tests,
  handler calls and offscreen widgets supplement this check but do not replace
  it. If computer interaction is unavailable, state the exact unverified path.
- The recorded AppShell development path is `ui.app_shell_smoke` with the project
  `.venv/Scripts/python.exe` through PyCharm Run Current File; `main.py` still
  launches the legacy app. Reconfirm the actual path before acceptance and do
  not switch `main.py` without the user's approval. On this Windows setup the
  trusted native route has used `mcp__node_repl__js` with `@oai/sky`; a
  browser-oriented CUA failure has not proved native access unavailable. Search
  callable tools and select the unique real window before reporting a blocker.
- Final reports distinguish automated checks from real UI clicks and name the
  path exercised. For UX changes, record a short repeatable smoke sequence and
  its visible result.

## Layout and rendering

- When matching an existing surface, inspect its working class/function,
  painting parent/viewport, coordinate system and size constants first. Before
  changing overlays, identify source/target coordinates; do not map sibling
  widgets to each other without a verified relationship. After a failed visual
  offset attempt, inspect actual rects rather than repeatedly nudging offsets.
  After two failed visual attempts, ask for confirmation or more data.
- Position calibrated icon canvases as whole canvases; do not anchor them by
  alpha bounds unless explicitly requested. Diagnose Qt clipping with widget,
  viewport/content and scrollbar sizes plus QSS border/padding effects. If
  `after` and settled layouts differ, prevent the intermediate frame from
  painting until the event-loop settle.
- AppShell adaptive downscale is required below the 1920px reference width,
  including its eventual production entrypoint before `QApplication`. Keep a
  state-independent top-level minimum size. Dense fractional-scale grids use
  `ui/utils/pixel_icon_grid.py`; vertical overflow can use
  `ui/utils/overlay_scroll.py`. Preserve interaction behavior when replacing
  repeated noninteractive child widgets with a painted strip.
- Keep hot-panel widgets parented in one stable layout. Update content,
  visibility and state in place; do not remove/re-add cached QWidgets or show
  temporary hydration placeholders that later jump. Reserve stable detail-panel
  geometry. Flexible build-preset names use leftover width and clip/marquee.
- Reusable pixmap work belongs in `ui/utils`. Raster assets use
  `ui/utils/hidpi_pixmap.py` or an equivalent complete DPR-aware path; clamp
  effective DPR to at least 1 during startup downscale. Use shared icon
  auto-contrast (`ui/utils/icon_utils.py`), palette (`ui/utils/ui_palette.py`)
  and filter-button (`ui/utils/filter_button_style.py`) helpers rather than
  local copies.

## Text and performance

- New user-visible text goes through `localization/locales/{ru,en,pt-br}.json`
  and `tr`/`tr_for_language`. New tooltips use the in-app custom surface, not
  native Qt tooltips; preserve typed content when richer payloads are planned.
- Every user-reported tooltip defect must add or update its semantic regression
  in the same fix. Check the actual attached/rendered content against independent
  expected facts, including stale/empty transitions; a nonempty string is not
  acceptance. Register new tooltip families/bindings and run the focused suite
  described in [tooltip contracts](TOOLTIP_CONTRACTS.md). Missing optional
  inventory witnesses warn; present witnesses with incorrect text fail.
- Before the approved loader/prewarm stage, improve lag by reducing total work,
  not merely delaying it to a click or timer. Measure expensive repeatable work.
  Persistent caches are introduced only with an approved cache/loader task;
  keys must include source identity/freshness, output dimensions, algorithm
  version and visual parameters. Do not do expensive parsing or image work in
  paint paths. Deferred candidates go to `PRELOADER_BACKLOG.md` with measured
  cost and device/commit context, not an immediate hidden prewarm.
