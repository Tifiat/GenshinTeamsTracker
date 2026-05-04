# Agent Context: GenshinTeamsTracker

## Project Identity

`GenshinTeamsTracker` is a new clean project replacing the legacy `AbyssTracker` pipeline.

Legacy source project:

- `C:\Users\user\Desktop\AbyssTracker`

Target project:

- `C:\Users\user\Desktop\GenshinTeamsTracker`

`AbyssTracker` should be treated as legacy. It contains useful UI behavior and HoYoLAB exporter experiments, but also a lot of old parsing/matching code that should not become the main architecture of the new project.

## Product Goal

Build a desktop PySide6 app for tracking Genshin Impact team history using HoYoLAB as the primary source.

Core idea:

1. HoYoLAB generates the visual image/card/screenshot.
2. HoYoLAB API provides structured account data.
3. DOM/layout coordinates provide precise crop regions.
4. The app stores clean character/weapon/team/history records.

The new pipeline should avoid relying on binary-mask icon detection as the primary method.

## Current Strategic Decisions

- UI stack: PySide6.
- Existing windows and behavior from legacy should be ported as a starting point.
- HoYoLAB exporter should be ported fully and developed further.
- Current mask-based parser and DINO/ORB matching should be legacy/fallback only, not the main path.
- New crop pipeline should use DOM/API/layout coordinates from HoYoLAB export.
- Do not store cookies, auth headers, or raw sensitive network dumps in normal output files.
- New project startup path must stay free of legacy `parser`, `weapon_matcher`, ORB, DINO, OpenCV, and mask-based calls.

## Current Project Structure

Implemented scaffold:

- `main.py` starts the PySide6 app.
- `ui/` contains the ported legacy window/widgets, with startup parser/matcher calls removed.
- `hoyolab_export/` contains the ported exporter sandbox as importable modules:
  - `hoyolab_exporter.py`
  - `run_manual_export.py`
  - `collect_account_inventory.py`
  - `debug_extract_data.py`
  - `coordinate_cropper.py`
- `requirements.txt` intentionally contains only current runtime dependencies:
  - `PySide6`
  - `playwright`
  - `pillow`
- `.gitignore` ignores browser profiles, downloads, debug data, export bundles, caches, generated crops/assets, virtualenvs, and local state/history JSON.

Verification done in the new project:

- `python -m compileall -q main.py ui hoyolab_export`
- `python -m compileall -q main.py ui hoyolab_export tests`
- Import check for `ui.main_window`, `hoyolab_export.hoyolab_exporter`, and `hoyolab_export.coordinate_cropper`
- Search confirmed no startup imports of legacy `parser`, `weapon_matcher`, `icon_enricher`, `cv2`, `HoyolabParser`, `match_weapons`, or ORB in new Python files.
- `tests/probe_layout.py` imports and compiles.
- Search confirmed no mojibake markers in `ui` / `hoyolab_export` excluding `hoyolab_export/profile/**`.

Not yet verified:

- Live HoYoLAB image download after the latest popup-dismiss retry changes.
- Live inventory collection output files.

Latest layout and role-card probe verification:

- `python tests/probe_layout.py` succeeded and latest inspected bundle is:
  - `tests/probe_layout_output/20260504_012954/image.png`
  - `tests/probe_layout_output/20260504_012954/layout_probe.json`
  - `tests/probe_layout_output/20260504_012954/page_screenshot.png`
  - `tests/probe_layout_output/20260504_012954/role_cards_preview.json`
  - `tests/probe_layout_output/20260504_012954/role_cards_overlay.png`
- `layout_probe.json` contains required top-level keys:
  - `html2canvasPatchStatus`
  - `html2canvasRootProbe`
  - `fallbackRootProbe`
  - `rootSource`
  - `rootDiscovery`
- Latest result:
  - `html2canvasPatchStatus.matched == true`
  - `rootSource == "html2canvas_clone"`
  - `html2canvasCloneProbe != null`
  - `rootDiscovery.imageLike` contains 535 image-like elements
- `tests/extract_role_cards_from_probe.py` successfully reads the latest probe bundle and writes:
  - `role_cards_preview.json`
  - `role_cards_overlay.png`
- Latest `role_cards_preview.json` result:
  - `cardsCount == 76`
  - 76/76 cards have `portraitRect`
  - 76/76 cards have `weaponRect`
- The sandbox role-card extractor identifies:
  - character cards by `DIV` with class containing `role-share`;
  - portraits by `IMG` with class containing `role-img`;
  - weapon icons by `IMG` whose parent chain contains `role-weapon-info`;
  - card order by root-relative `cardRect` top/left.
- Interpretation: the project now has a working DOM/layout-based source for visible character and weapon crop rectangles. The next step is to promote this sandbox logic into the production HoYoLAB import pipeline and link crops to clean API records.

## Important Legacy Files To Inspect / Port

HoYoLAB exporter sandbox:

- `C:\Users\user\Desktop\AbyssTracker\test\hoyolab_export\hoyolab_exporter.py`
- `C:\Users\user\Desktop\AbyssTracker\test\hoyolab_export\run_manual_export.py`
- `C:\Users\user\Desktop\AbyssTracker\test\hoyolab_export\debug_extract_data.py`
- `C:\Users\user\Desktop\AbyssTracker\test\hoyolab_export\collect_account_inventory.py`

Useful UI legacy files:

- `C:\Users\user\Desktop\AbyssTracker\main.py`
- `C:\Users\user\Desktop\AbyssTracker\ui\main_window.py`
- `C:\Users\user\Desktop\AbyssTracker\ui\run_history_window.py`
- `C:\Users\user\Desktop\AbyssTracker\ui\widgets\*.py`

Legacy parser/matcher files are reference only:

- `parser/hoyolab_parser.py`
- `services/icon_enricher_orb.py`
- `services/weapon_matcher.py`
- `services/weapon_*`

Do not port old parser/matcher code as the main path unless explicitly requested.

## HoYoLAB Exporter Facts

Working exporter behavior:

- Opens Chrome/Edge through a persistent browser profile.
- Requires the persistent profile to be logged in before automated export.
- First login must happen through a normal browser process, not a CDP/remote-debugging automation browser.
- Opens HoYoLAB Genshin record page.
- Clicks the character/list/share controls automatically.
- Downloads the HoYoLAB-generated image.
- Uses CDP with browser-assigned remote debugging port, not fixed `9222`.
- Supports `scale` and `fixed_container_width`.
- Final image width is approximately:

```text
fixed_container_width * scale
```

Current working example:

```python
scale = 4
fixed_container_width = 500
# output width ~= 2000 px
```

The exporter currently patches HoYoLAB JS/html2canvas rather than relying on viewport size.

Current html2canvas probe hook:

- `hoyolab_export/hoyolab_exporter.py` injects `window.__genshin_export_root_probe__` immediately before the patched `html2canvas(t, r)` call.
- `hoyolab_export/hoyolab_exporter.py` also tracks route-level patch diagnostics in `HoyolabExporter.html2canvas_patch_status` and merges that into `window.__genshin_html2canvas_patch_status__` before `tests/probe_layout.py` collects layout data.
- `hoyolab_export.close_export_context(...)` closes pages, stops Playwright, and terminates the browser process created by `_create_context`; this avoids leaving the persistent profile locked or paused after a failed/manual login attempt.
- `hoyolab_export.auth` is the shared profile-status layer for UI, setup scripts, reset, and exporter preflight.
- `hoyolab_export.run_login_setup` opens HoYoLAB in a normal Chrome/Edge process with the same app profile. The user authorizes and closes that browser window.
- `run_manual_export.py` is the manual test flow. If profile auth is not detected, it opens a normal Chrome/Edge login browser, waits for the user to close it, rechecks auth status, then exports only if auth is detected.
- Product/UI export flow should not ask the user to log in inside the automation browser. The UI should require auth first, then start `python -m hoyolab_export.run_manual_export` as a subprocess.
- The PySide UI checks HoYoLAB profile status on startup. It shows an authorization prompt only when needed and includes a "Сменить аккаунт" action that resets the app profile and opens the normal authorization browser.
- Auth detection is intentionally stricter than "Cookies file exists": `hoyolab_export.auth.get_auth_status(...)` opens the cookie DB read-only and checks only safe cookie names/hosts, never values. A non-empty browser cookie file after visiting HoYoLAB is not enough to count as logged in.
- Current UI auth behavior:
  - `not_logged_in`: visible auth block with `Авторизоваться`; `HoYoLAB export` disabled.
  - login browser open/profile busy: visible instruction to close the browser; export disabled.
  - `logged_in`: visible `Сменить аккаунт`; `HoYoLAB export` enabled unless an export subprocess is running.
- `HoYoLAB export` is no longer a placeholder popup. It starts the manual exporter subprocess when auth is detected and shows a simple finish/failure message.
- The auth block has explicit button styling because default PySide/Windows styling previously made the auth button look like an empty beige area.
- If exporter, inventory collector, or debug extractor sees the HoYoLAB login iframe, it raises an instruction to authorize through the normal browser flow instead of asking the user to log in inside the automation browser.
- Exporter now retries important clicks after attempting to dismiss known HoYoLAB popups/modals/update notices. If share export still fails, it prints `Visible blockers debug` with visible overlay candidates to help identify the blocker.
- The stored root probe includes:
  - `rootRect`
  - `scale`
  - `fixedContainerWidth`
  - `devicePixelRatio`
  - `scrollX` / `scrollY`
  - viewport size
- This is intended to make the html2canvas root DOM node the coordinate source of truth.

## Account Data Facts

HoYoLAB endpoint:

```text
/event/game_record/genshin/api/character/list
```

contains account character and equipped weapon data.

Known character fields:

- `id`
- `name`
- `element`
- `level`
- `rarity`
- `actived_constellation_num`
- `weapon_type`
- `icon`
- `side_icon`
- `weapon`

Known weapon fields inside `weapon`:

- `id`
- `name`
- `type`
- `rarity`
- `level`
- `affix_level`
- `icon`

Weapon type mapping discovered:

```python
{
    1: "sword",
    10: "catalyst",
    11: "claymore",
    12: "bow",
    13: "polearm",
}
```

Existing debug collector can create:

- `account_characters.json`
- `account_weapons.json`

These are clean normalized files and should be preferred over raw network dumps.

## Desired New Pipeline

Target pipeline:

```text
HoYoLAB browser session
  -> export image.png
  -> collect character/list API
  -> collect DOM/layout metadata
  -> save export bundle
  -> crop character/weapon regions by coordinates
  -> link crops to exact API ids
  -> show/store in PySide6 UI
```

Export bundle should eventually contain:

```text
image.png
account_characters.json
account_weapons.json
layout.json
crop_manifest.json
```

`layout.json` should describe visible DOM elements and coordinate scale needed to crop from the final image.

`crop_manifest.json` should link each generated crop to structured data:

```json
{
  "character": {
    "id": 10000089,
    "name": "...",
    "rarity": 5,
    "element": "Hydro",
    "level": 90,
    "constellation": 2
  },
  "weapon": {
    "id": 11426,
    "name": "...",
    "rarity": 4,
    "type": 1,
    "type_name": "sword",
    "level": 90,
    "refinement": 5
  },
  "crops": {
    "character": "crops/characters/char_001.png",
    "weapon": "crops/weapons/weapon_001.png"
  }
}
```

Current temporary coordinate cropper contract:

```json
{
  "items": [
    {
      "id": "api-or-dom-id",
      "kind": "character",
      "rect": {
        "left": 0,
        "top": 0,
        "right": 100,
        "bottom": 100
      }
    }
  ]
}
```

`hoyolab_export.coordinate_cropper.crop_from_layout(...)` scales these DOM rectangles into final PNG coordinates and writes `crop_manifest.json`. This is only a scaffold; the next step is to replace the temporary layout schema with real HoYoLAB DOM selectors and API id linkage.

Current handoff for the next implementation task:

- Turn the UI `HoYoLAB export` button into a real HoYoLAB import flow.
- The flow should:
  - run the existing export/probe flow;
  - use the role-card extraction logic proven in `tests/extract_role_cards_from_probe.py`;
  - collect clean account inventory from the HoYoLAB character/list API;
  - match visible role cards to API records by the same display order;
  - crop character portraits and weapon icons from the exported PNG using `portraitRect` and `weaponRect`;
  - save generated images to `assets/hd/characters` and `assets/hd/weapons`;
  - save a manifest JSON that links each generated image to structured fields for future sorting;
  - refresh the PySide grids after successful import.
- Manifest records should include at minimum:
  - character `id`, `name`, `rarity`, `element`, `level`, `constellation`, `weapon_type`, `weapon_type_name`;
  - weapon `id`, `name`, `rarity`, `type`, `type_name`, `level`, `refinement`, `equipped_by`;
  - local crop paths;
  - source root-relative rectangles;
  - simple sort fields derived from the API data.
- Keep this path HoYoLAB API + DOM/layout + coordinate crops first. Do not add legacy OpenCV/mask matching as the primary import path.

Layout probe script:

- `tests/probe_layout.py`
- Defaults to the normal app profile `hoyolab_export/profile` and browser-assigned CDP port.
- `--debug-port <port>` can be used only for explicit technical debugging.
- Run with:

```bash
python tests/probe_layout.py
```

First-login launcher:

```bash
python -m hoyolab_export.run_login_setup
```

Use this first on a fresh install/profile. It opens a normal browser, so Google/HoYoLAB login is not attempted inside the automation browser. Log in, close that browser, then run `python -m hoyolab_export.run_manual_export` or `python tests/probe_layout.py`.

Manual export command:

```bash
python -m hoyolab_export.run_manual_export
```

This command may open the normal auth browser first if the app profile is not logged in. After the browser is closed, it rechecks auth status and only then starts automation/export.

Windows cleanup note:

- `tests/probe_layout.py` intentionally uses a custom `run_async(...)` instead of `asyncio.run(...)`.
- This gives Playwright subprocess transports a short cleanup window before the event loop closes and avoids the common ignored `RuntimeError: Event loop is closed` traceback on Windows.

- Output goes to `tests/probe_layout_output/YYYYMMDD_HHMMSS/`.
- Expected files:
  - exported HoYoLAB image
  - `layout_probe.json`
  - `page_screenshot.png`
- `layout_probe.json` contains `html2canvasRootProbe`, page metrics, candidate card rectangles, image rectangles, and root-relative rectangles where the root probe is available.
- The output folder is ignored by git because it may contain private account visuals.

## UI Direction

Port legacy UI behavior first, then reshape it.

Useful existing behavior:

- Main window with left asset panel and right team panel.
- Draggable icons.
- Team slots.
- Timers.
- Run/history window.
- Zoomable history cards.

New history direction:

- History window should eventually have tabs:
  - Abyss
  - Stygian Onslaught / "Мрачный натиск"
- Inside each tab, user should be able to switch versions/cycles.
- Future export/history records should include visual team composition and timer data.

Do not redesign everything in the first pass. First preserve working window behavior, then replace data source/pipeline.

Current UI state:

- Main window, draggable icons, team slots, timers, save/reset run, and history window are ported.
- User-facing strings touched during the port were changed away from mojibake.
- `HoYoLAB export` now runs the manual exporter subprocess when auth status is `logged_in`; it is disabled when auth is missing or profile is busy.
- The auth block currently uses Russian button text: `Авторизоваться`, `Ожидаю закрытия браузера`, `Сменить аккаунт`.
- The old `Import export bundle` UI placeholder was removed. Re-add bundle import only after the real `crop_manifest.json` pipeline exists.

## Future Data Needs

Eventually the app must know:

- current Spiral Abyss version/cycle;
- current Stygian Onslaught version/cycle;
- historical versions/cycles for both modes.

This is future work. Do not block the first HoYoLAB export/crop pipeline on it.

## Security / Privacy Rules

Do not save or commit:

- cookies;
- auth tokens;
- raw request headers;
- full raw network dumps unless explicitly in debug-only ignored folders.

Clean normal outputs may include:

- character ids/names;
- weapon ids/names;
- levels;
- constellations/refinements;
- icons;
- local crop files.

Debug files should live in ignored folders and should be treated as private.

## Working Rules For Future Chats

Before coding:

1. Read `agent_context.md`.
2. Read `TODO.md`.
3. Inspect current files instead of assuming.
4. Keep changes scoped.
5. After completing a task:
   - mark TODO item as done;
   - add discovered follow-up tasks;
   - update `agent_context.md` if architecture changed.

## Legacy Warning

Avoid carrying over legacy complexity by inertia.

Legacy mask-based code currently detects extra false positives:

- weapon detector catches 3 extra elements near screenshot start;
- character detector catches 2 extra elements near footer/QR/logo.

The preferred fix is not "more CV heuristics"; it is coordinate/layout-based cropping from HoYoLAB's own rendered DOM.
