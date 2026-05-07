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
  - `paths.py`
  - `layout_capture.py`
  - `crop_manifest.py`
  - `character_detail.py`
  - `artifact_db.py`
  - `artifact_importer.py`
  - `offline_profile.py`
  - `import_pipeline.py`
  - `run_import.py`
- Current production HoYoLAB folders:
  - `data/hoyolab`
  - `assets/hoyolab`
  - `assets/hoyolab/artifacts`
  - `debug/hoyolab`
- Artifact SQLite DB:
  - `data/artifacts.db`
- Legacy/currently unused asset folders:
  - `assets/hd/characters`
  - `assets/hd/weapons`
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
- Earlier search confirmed no mojibake markers in touched `ui` / `hoyolab_export` files, but current inspection found mojibake Russian text/comments in `ui/widgets/loader.py`, `ui/widgets/drag.py`, and some legacy UI strings.

Latest production import verification from local generated files:

- `data/hoyolab/crop_manifest.json` exists.
- `data/hoyolab/account_characters.json` exists.
- `data/hoyolab/account_weapons.json` exists.
- `data/hoyolab/layout.json` exists.
- Current manifest summary:
  - `cardsCount == 75`
  - `matchedCharacters == 75`
  - `matchedWeapons == 75`
  - `okMatches == 75`
  - `warningMatches == 0`
  - `characterAssets == 73`
  - `weaponAssets == 49`
- `layout.json` uses `rootSource == "html2canvas_clone"` and has 535 image-like elements.
- Local commit `1ae2de6` ("собран пайплайн импорта из хоелаб") was created. Push previously failed with GitHub remote `Internal Server Error`; retry a normal push, do not force-push.

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
- Interpretation: the sandbox proved the DOM/layout-based crop source. Production now uses the same idea in `hoyolab_export/crop_manifest.py`.
- Production note: the old 76-card sandbox result included `role-share-container`. Production excludes container-like cards and currently produces 75 real cards.

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
- `hoyolab_export.close_export_context(...)` terminates the browser process created by `_create_context`, then stops Playwright with short cleanup timeouts; this avoids leaving the persistent profile locked or paused after a failed/manual login attempt.
- `hoyolab_export.auth` is the shared profile-status layer for UI, setup scripts, reset, and exporter preflight.
- `hoyolab_export.run_login_setup` opens HoYoLAB in a normal Chrome/Edge process with the same app profile. The user authorizes and closes that browser window.
- `run_manual_export.py` remains a manual test/export flow. If profile auth is not detected, it opens a normal Chrome/Edge login browser, waits for the user to close it, rechecks auth status, then exports only if auth is detected.
- Product/UI import flow should not ask the user to log in inside the automation browser. The main HoYoLAB UI button opens the normal authorization browser when auth is missing, or starts `python -m hoyolab_export.run_import` through `QProcess` when auth is present.
- The PySide UI checks HoYoLAB profile status on startup. The separate visible login/switch buttons and the old auth-status block were removed; the left panel now keeps at most two visible HoYoLAB actions under the character list: the dynamic main HoYoLAB button and `Профиль...`.
- Auth detection is intentionally stricter than "Cookies file exists": `hoyolab_export.auth.get_auth_status(...)` opens the cookie DB read-only and checks only safe cookie names/hosts, never values. A non-empty browser cookie file after visiting HoYoLAB is not enough to count as logged in.
- Current UI auth behavior:
  - `not_logged_in`: main HoYoLAB button text is `Авторизоваться / выбрать профиль`; clicking it shows instructions and can open the normal authorization browser.
  - login browser open/profile busy: visible instruction to close the browser; main HoYoLAB action is disabled.
  - `logged_in` without local data: main HoYoLAB button text is `Импортировать из HoYoLAB`.
  - `logged_in` with local data: main HoYoLAB button text is `Обновить данные HoYoLAB`.
- The main HoYoLAB button is no longer a placeholder popup. It starts the full import/update pipeline when auth is detected and uses a loader dialog for progress/failure handling.
- The auth block has explicit button styling because default PySide/Windows styling previously made the auth button look like an empty beige area.
- If exporter, inventory collector, or debug extractor sees the HoYoLAB login iframe, it raises an instruction to authorize through the normal browser flow instead of asking the user to log in inside the automation browser.
- Exporter now retries important clicks after attempting to dismiss known HoYoLAB popups/modals/update notices. If share export still fails, it prints `Visible blockers debug` with visible overlay candidates to help identify the blocker.
- Share/download clicks use Playwright trusted clicks with the transparent input blocker temporarily disabled. This is important because JS `el.click()` can run html2canvas without producing a browser `download` event on current HoYoLAB/Chromium.
- The old page-injected DOM input blocker (`__abyss_tracker_blocker__`) is no longer used in export flow because it can cover HoYoLAB's own share/download controls and cause `expect_download` timeouts. If `Visible blockers debug` shows a fixed `DIV` with `zIndex: 2147483647`, suspect a stale/internal blocker first, not the Qt loader window.
- If Chromium/Playwright does not emit a `download` event after HoYoLAB runs html2canvas, the exporter first falls back to the captured html2canvas PNG data URL. If that data URL is also missing, it falls back to a screenshot of the exported DOM root and returns an in-memory download object.
- HoYoLAB JS route patching sanitizes Playwright errors before printing them. Do not print `Route.fetch` call logs because they can include request headers and cookies.
- If `route.fetch()` fails with transient network errors such as `ECONNRESET`, exporter retries and then falls back to a plain public Python fetch of the JS bundle without browser cookies.
- Patched JS routes are fulfilled with fixed safe JavaScript headers/status after patching. Do not reuse a `route.fetch()` response object in that path because the JS body may have come from the public no-cookie fallback instead.
- Automation browser startup ignores stale `DevToolsActivePort` markers by requiring the marker mtime to be newer than the current Chrome launch. This avoids connecting to a closed/old CDP target and failing on `Page.goto: Target page, context or browser has been closed`.
- Import reuses the startup `about:blank` tab instead of opening a second tab for HoYoLAB.
- `[STATUS] done` is emitted only after browser cleanup, so the UI loader should not sit on `Готово` while the subprocess is still waiting for Chrome to close.
- `close_export_context(...)` terminates the owned automation browser before stopping Playwright and wraps page/playwright cleanup in short timeouts, so the UI is not blocked until the user manually closes the browser.
- HoYoLAB loader window is non-modal and uses `Qt.WindowTransparentForInput` plus `WA_TransparentForMouseEvents`, so if it physically overlaps the browser it should not intercept user/mouse input.
- The import UI now shows the captured subprocess error tail instead of only the generic authorization warning.
- Ordinary import/update no longer clears current HoYoLAB data/assets at `[STATUS] preparing`; early browser failures should leave the previously loaded offline/local profile intact.
- Ordinary import/update is additive for character and weapon collection data. It updates/merges `account_characters.json`, `account_weapons.json`, `crop_manifest.characterAssets`, `crop_manifest.weaponAssets`, and existing character/weapon PNGs instead of deleting the previous local collection. Destructive cleanup belongs to `Выйти из профиля` or offline profile restore.
- Character collection keys are based on character id + element, so a Traveler element change can be preserved as a separate local character asset. Weapon collection keys are based on weapon id/refinement/level/icon for inventory JSON and icon key for manifest assets; moving the same weapon to another character updates the latest equipped info instead of creating a new local weapon.
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

Current inventory collector facts:

- `collect_account_inventory.py` is reusable and still has a CLI.
- `build_inventory(...)` no longer sorts API results. It preserves the HoYoLAB API order.
- The production manifest matching does not rely on API/card index matching anymore because `/character/list` order can vary.
- `wait_for_character_list_response(...)`, `build_inventory(...)`, and `write_inventory(...)` are reusable entry points.
- Clean inventory files are written to `data/hoyolab` by the production import pipeline:
  - `account_characters.json`
  - `account_weapons.json`
- The older debug CLI can still write to `hoyolab_export/debug_data`.

## Artifact Data Facts

HoYoLAB full character/artifact detail endpoint discovered:

```text
POST https://sg-public-api.hoyolab.com/event/game_record/genshin/api/character/detail
```

Request body shape:

```json
{
  "server": "...",
  "role_id": "...",
  "character_ids": [10000034]
}
```

Endpoint behavior:

- Batch requests work. Verified requesting all 73 real characters in one POST.
- `role_id` and `server` can be detected from the HoYoLAB game roles endpoint used by the sandbox tools.
- Manual/browser fetch must pass language from the current page/session:
  - `x-rpc-language`
  - `accept-language`
- Without those language headers, `character/detail` may return Chinese data even when the visible page is not Chinese.
- `index?avatar_list_type=1` includes relics, but not full artifact stats:
  - `main_property: null`
  - `sub_property_list: []`
- Full artifact stats are in `character/detail`:
  - `main_property.property_type`
  - `main_property.value`
  - `sub_property_list[].property_type`
  - `sub_property_list[].value`
  - `sub_property_list[].times`
  - `property_map`

Artifact persistence layer:

- `hoyolab_export/artifact_db.py` defines SQLite DB `data/artifacts.db`.
- Tables:
  - `artifact_icons`
  - `artifacts`
  - `artifact_substats`
  - `artifact_equipment`
  - `artifact_tags`
  - `artifact_tag_links`
  - `artifact_builds`
  - `artifact_build_slots`
- `hoyolab_export/artifact_importer.py` normalizes `character/detail` relics, calculates stable fingerprints, and upserts:
  - artifact icons;
  - artifacts;
  - substats;
  - current equipment.
- Artifact fingerprint intentionally excludes character id, so moving an artifact to another character keeps it as the same artifact.
- Current equipment is replaced on import; artifact records, user tags, and user artifact builds are preserved during ordinary HoYoLAB updates.

Artifact tools:

- `tools/capture_hoyolab_artifacts.py`: sandbox endpoint capture / active fetch helper.
- `tools/probe_hoyolab_character_detail_batch.py`: fetches role info, detects language from page/session, and POSTs a batch `character/detail` request.
- `tools/import_artifacts_from_detail_json.py`: imports `character_detail_batch_result.json` into SQLite.
- `tools/test_artifact_tag_persistence.py`: verifies user tags survive re-import.

Verified local artifact import:

- First import from `character_detail_batch_result.json`:
  - `characters: 73`
  - `relics_seen: 254`
  - `artifacts_inserted: 254`
  - `artifact_icons: 104`
  - `artifact_substats: 1004`
- Re-importing the same file:
  - `artifacts_inserted: 0`
  - `artifacts_existing: 254`
- Current `data/artifacts.db` row counts:
  - `artifact_icons: 104`
  - `artifacts: 254`
  - `artifact_substats: 1004`
  - `artifact_equipment: 254`
  - `artifact_tags: 1`
  - `artifact_tag_links: 1`
- Test tag `test_keep_after_import` survived re-import.

Current artifact UI MVP:

- `hoyolab_export/artifact_queries.py` is the read/write query layer for the artifact browser. It lists artifacts with substats, equipment, and tags from `data/artifacts.db`; it also adds/removes artifact tags through the existing `artifact_tags` and `artifact_tag_links` tables.
- `ui/artifact_browser_window.py` adds the first PySide6 artifact browser window. It supports search, slot/rarity/equipment/tag filters, artifact cards, a detail panel, and adding/removing tags.
- `ui/main_window.py` opens the browser through the new `Открыть артефакты` button on the right panel.
- The artifact browser is intentionally an MVP: no build editor yet. It has a close button and uses cached local artifact icons when available; if icon files are missing locally, cards show a placeholder.
- Artifact icon caching is bounded and cosmetic. Public icon download failures or slow CDN responses must not fail or hang the HoYoLAB import.

Current artifact import pipeline:

- `hoyolab_export/character_detail.py` is the reusable production helper for `character/detail`.
- `python -m hoyolab_export.run_import` now fetches one batch `character/detail` request after `/character/list` inventory is known.
- The compact current detail snapshot is written to `data/hoyolab/account_character_details.json`.
- The same import run imports/updates artifacts into `data/artifacts.db`.
- Ordinary HoYoLAB import/update clears debug at startup, then replaces current HoYoLAB JSON/assets only after browser export, inventory, and detail fetch have succeeded. It does not delete `data/artifacts.db`, so user artifact tags/builds survive repeated updates.
- Account/profile switching is the explicit boundary that clears `data/artifacts.db`, because artifacts and user artifact tags/builds must not be mixed between accounts.

## Desired New Pipeline

Current production HoYoLAB import pipeline:

```text
HoYoLAB browser session
  -> verify existing app auth status
  -> clear debug/hoyolab only
  -> open HoYoLAB once in automation browser
  -> install /character/list response listener before page load
  -> open character list during export flow
  -> export image.png
  -> collect html2canvas clone layout/rootDiscovery
  -> build clean inventory in memory
  -> fetch character/detail for all real characters
  -> import/update artifacts in SQLite
  -> merge current character/weapon inventory into the local collection
  -> write/update clean inventory JSON and current character details snapshot
  -> crop character/weapon regions by DOM/root-relative coordinates
  -> link current crops to exact API ids by icon URL
  -> merge current character/weapon crops into existing local assets/manifest
  -> write manifest/debug overlay
  -> refresh PySide6 grids
```

Current outputs:

```text
data/hoyolab/account_characters.json
data/hoyolab/account_weapons.json
data/hoyolab/account_character_details.json
data/hoyolab/layout.json
data/hoyolab/crop_manifest.json
assets/hoyolab/characters/*.png
assets/hoyolab/weapons/*.png
data/artifacts.db
debug/hoyolab/image.png
debug/hoyolab/crop_manifest_overlay.png
debug/hoyolab/page_screenshot.png
debug/hoyolab/import_log.json
```

## Offline Profile Export/Import

Offline profiles are local backup/restore bundles for already collected account data. They do not contain HoYoLAB browser auth/session data and do not require HoYoLAB authorization to import back into the app.

Production helper:

- `hoyolab_export/offline_profile.py`

Offline profile export is ZIP-based and includes only the allowlisted current local data:

- `data/hoyolab/account_characters.json`
- `data/hoyolab/account_weapons.json`
- `data/hoyolab/crop_manifest.json`
- `data/hoyolab/account_character_details.json` if present
- `assets/hoyolab/characters/`
- `assets/hoyolab/weapons/`
- `assets/hoyolab/artifacts/` if present
- `data/artifacts.db`

Offline profile export explicitly excludes:

- `hoyolab_export/profile/`
- HoYoLAB cookies/session/browser data
- `debug/`
- `downloads/`

`offline_profile.py` uses an SQLite backup snapshot when exporting `data/artifacts.db`, rather than copying browser profile or sensitive state. It writes `data/hoyolab/offline_export_state.json` as a local marker/signature so the sign-out flow can tell whether the current local profile has probably been saved. If the marker is missing or the signature does not match, UI warns before clearing data.

Offline profile import restores the allowlisted JSON/assets/db, refreshes UI grids, and marks the imported state as exported. It does not require HoYoLAB auth.

Sign-out behavior:

- Warn if the current local profile has not been exported or cannot be verified.
- Offer `Сохранить профиль` or `Не сохранять`.
- Ask whether to keep `runs_history.json`.
- Clear HoYoLAB browser profile, current HoYoLAB JSON/assets/debug, artifact assets, and `data/artifacts.db`.
- Preserve run history only if the user chose to keep it.
- Reset the current run UI after clearing, because team slots may point to account-specific assets.

`layout.json` describes visible DOM elements and coordinate scale needed to crop from the final image. Production layout capture lives in `hoyolab_export/layout_capture.py` and no longer depends on `tests/probe_layout.py`.

`crop_manifest.json` links generated crops and visible cards to structured data. Top-level fields include:

```json
{
  "version": 1,
  "source": {"image": "debug/hoyolab/image.png", "layout": "data/hoyolab/layout.json", "scale": 4.0},
  "cardsCount": 75,
  "matchedCharacters": 75,
  "matchedWeapons": 75,
  "okMatches": 75,
  "warningMatches": 0,
  "characterAssets": [],
  "weaponAssets": [],
  "cards": []
}
```

Matching/cropping facts:

- Production role-card extraction is in `hoyolab_export/crop_manifest.py`.
- Character cards are `DIV` nodes with `role-share`, excluding `role-share-container`, and requiring `role-rarity-`.
- Portraits are `IMG` nodes with `role-img`.
- Weapon icons are `IMG` nodes whose parent chain includes `role-weapon-info`.
- Crop rectangles come from DOM/root-relative rects and export scale. Current crop inset is one setting: `CROP_INSET = 1`.
- Card/API matching is icon-based:
  - `portraitSrc` -> `character.icon` / `character.side_icon`
  - `weaponSrc` -> `weapon.icon`
  - weapon validation also checks `equipped_by.id == character.id`
- Dummy characters `10000118` and `10000117` remain in manifest/cards but are not saved to character assets.
- Weapon rarity 1 and 2 are ignored for weapon assets.
- Duplicate weapon icons are not duplicated in `assets/hoyolab/weapons`; `weaponAssets` aggregates variants.
- Duplicate weapon variants are aggregated by `refinement + level` into tooltip lines such as `R5 lvl 90 x2`.
- Across ordinary HoYoLAB updates, `weaponAssets` keeps previously discovered weapons that are no longer equipped. Variant counts are merged with `max(previous_count, current_count)`, not summed every run, so repeated updates do not inflate counts.
- Across ordinary HoYoLAB updates, current character/weapon crops reuse existing manifest crop paths when their collection key already exists. New discoveries receive new stable filenames; old PNGs are not deleted.
- Character tooltip format is `Name lvl X`. Weapon tooltip format is weapon name followed by variant lines.
- `tests/build_crop_manifest_from_probe.py` is a sandbox/proof wrapper. Production should rely on `hoyolab_export.crop_manifest`, not test scripts.

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

Production import command:

```bash
python -m hoyolab_export.run_import
```

`run_import.py` wraps stdout/stderr with UTF-8 replacement and emits `[STATUS] ...` lines used by the UI loader.

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
- Static UI strings now go through the JSON localization layer where touched by the localization pass.
- Legacy note: this section originally described the old `HoYoLAB export` button; current behavior is documented below in "Current UI import details".
- The auth block uses localization keys for login, waiting, and account-switch labels.
- The old `Import export bundle` UI placeholder was removed. A separate bundle-import UI is no longer required for the current-state MVP unless future archived bundles are introduced.

Current UI import details:

- The old `HoYoLAB export` button is now the dynamic main HoYoLAB button.
- Button text/action state:
  - no auth: `Авторизоваться / выбрать профиль`, shows instructions and can open the normal auth browser;
  - auth + no local data: `Импортировать из HoYoLAB`, starts import;
  - auth + local data: `Обновить данные HoYoLAB`, starts the same import/update pipeline.
- The main button runs `python -m hoyolab_export.run_import` through `QProcess`, not the old manual export subprocess.
- During import, UI shows `HoYoLABLoadingDialog` from `ui/widgets/loader.py`.
- The loader reads `[STATUS] ...` lines and maps them to smooth progress targets.
- The loader uses `assets/loader/grey_ldr.png` and `assets/loader/color_ldr.png`.
- After successful import, UI calls `safe_update_grids()` without a success popup.
- After completion/error, the import button has a short cooldown before it can be used again.
- The cooldown is tracked with `_hoyolab_import_cooldown_active`, so `refresh_hoyolab_auth_status()` cannot accidentally re-enable the dynamic HoYoLAB button immediately after a successful import while Chrome/profile cleanup is still settling.
- UI grids now read from:
  - `assets/hoyolab/characters`
  - `assets/hoyolab/weapons`
- `main_window.py` reads `data/hoyolab/crop_manifest.json` and uses manifest `characterAssets` / `weaponAssets` for tooltips and filters.
- The left panel has icon-only filter buttons backed by generated local PNGs in `assets/filters`:
  - character filters: element, weapon type, rarity 5/4;
  - weapon filters: weapon type, rarity 5/4/3.
- Filter behavior is multi-select: OR inside one group, AND between groups. If a manifest is missing, the grids fall back to showing PNG files from the asset folder.
- The visible manual `Очистить персонажей и оружие` button was removed.
- `Профиль...` opens a menu with `Сохранить профиль`, `Загрузить профиль`, and `Выйти из профиля`.
- `change_hoyolab_account()` is now the sign-out flow behind `Выйти из профиля`: optional offline save warning, run-history keep/delete question, browser profile reset, current HoYoLAB data/assets/debug cleanup, artifact DB cleanup, and UI reset.
- Closing the run-history question dialog cancels sign-out instead of choosing `Нет`.
- `DraggableIcon.setToolTip()` now stores custom tooltip text, disables the native Qt tooltip, and shows a custom `FloatingTooltip`.
- `drag.py` allows right-click deletion from both legacy asset folders and current `assets/hoyolab/characters` / `assets/hoyolab/weapons`.
- Visible loader/drag/main-window strings touched by the localization pass no longer keep hard-coded mojibake text.

## Localization

- UI localization uses a small JSON-backed layer, not Qt `.ts/.qm` yet.
- Localization module:
  - `localization/i18n.py`
  - `localization/locales/ru.json`
  - `localization/locales/en.json`
  - `localization/locales/pt-br.json`
- UI code should call `tr("key")` instead of embedding display strings directly.
- Default UI language is `ru`.
- Supported UI languages:
  - `ru` / Russian
  - `en` / English
  - `pt-br` / Brazilian Portuguese
- The main window has a bottom-right language selector with country flags.
- Selected UI language is saved to local `settings.json`; this file is ignored by git.
- `GTT_LANGUAGE` or `GTT_LANG` can override the UI language for a process, for example:

```powershell
$env:GTT_LANGUAGE = "en"
python main.py
```

- Current scope is static UI text: buttons, labels, loader statuses, warning/info dialogs, filter tooltips, and small static tooltips.
- Character and weapon names/tooltips come from HoYoLAB/API data and should keep using the language returned by HoYoLAB.
- HoYoLAB/API language and UI language are separate concerns. Do not force API language just because the UI language changes.
- Future localization work:
  - keep adding keys to `ru.json` / `en.json` as new UI text appears;
  - keep `pt-br.json` in sync with `ru.json` / `en.json`;
  - consider Qt Translation System only if the app grows enough to justify `.ts/.qm` tooling.

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
