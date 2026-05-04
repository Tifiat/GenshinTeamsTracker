import json
import time
from pathlib import Path
from typing import Any
import asyncio

from playwright.async_api import BrowserContext, Page

from .auth import AuthStatus, get_auth_status
from .collect_account_inventory import (
    build_inventory,
    wait_for_character_list_response,
    write_inventory,
)
from .crop_manifest import build_crop_manifest
from .hoyolab_exporter import HOYOLAB_URL, HoyolabExporter, close_export_context
from .layout_capture import collect_layout
from .paths import (
    HOYOLAB_ASSETS_DIR,
    HOYOLAB_CHARACTER_ASSETS_DIR,
    HOYOLAB_DATA_DIR,
    HOYOLAB_DEBUG_DIR,
    HOYOLAB_PROFILE_DIR,
    HOYOLAB_WEAPON_ASSETS_DIR,
    PROJECT_ROOT,
    clear_hoyolab_current_data,
    ensure_hoyolab_dirs,
)


class HoYoLABImportError(RuntimeError):
    pass


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

def print_status(status: str) -> None:
    print(f"[STATUS] {status}", flush=True)

def build_import_log(
    *,
    image_path: Path,
    layout_path: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    characters: list[dict[str, Any]],
    weapons: list[dict[str, Any]],
    started_at: float,
) -> dict[str, Any]:
    return {
        "startedAt": started_at,
        "finishedAt": time.time(),
        "image": image_path.as_posix(),
        "layout": layout_path.as_posix(),
        "manifest": manifest_path.as_posix(),
        "characters": len(characters),
        "weapons": len(weapons),
        "cards": manifest.get("cardsCount"),
        "matchedCharacters": manifest.get("matchedCharacters"),
        "matchedWeapons": manifest.get("matchedWeapons"),
        "okMatches": manifest.get("okMatches"),
        "warningMatches": manifest.get("warningMatches"),
    }


async def run_hoyolab_import() -> dict[str, Any]:
    """Run full HoYoLAB import into the current MVP folders.

    Outputs:
    - data/hoyolab/account_characters.json
    - data/hoyolab/account_weapons.json
    - data/hoyolab/layout.json
    - data/hoyolab/crop_manifest.json
    - assets/hoyolab/characters/*.png
    - assets/hoyolab/weapons/*.png
    - debug/hoyolab/image.png
    - debug/hoyolab/crop_manifest_overlay.png
    - debug/hoyolab/page_screenshot.png
    - debug/hoyolab/import_log.json
    """
    started_at = time.time()

    if get_auth_status(HOYOLAB_PROFILE_DIR) != AuthStatus.LOGGED_IN:
        raise HoYoLABImportError(
            "HoYoLAB profile is not logged in. Authorize in the app first."
        )

    print_status("preparing")
    clear_hoyolab_current_data()
    ensure_hoyolab_dirs()

    exporter = HoyolabExporter(
        profile_dir=HOYOLAB_PROFILE_DIR,
        download_dir=HOYOLAB_DEBUG_DIR,
        scale=4,
        fixed_container_width=500,
        browser_window_width=1280,
        browser_window_height=900,
        image_format="png",
    )

    context: BrowserContext | None = None

    image_path = HOYOLAB_DEBUG_DIR / "image.png"
    layout_path = HOYOLAB_DATA_DIR / "layout.json"
    manifest_path = HOYOLAB_DATA_DIR / "crop_manifest.json"
    overlay_path = HOYOLAB_DEBUG_DIR / "crop_manifest_overlay.png"
    page_screenshot_path = HOYOLAB_DEBUG_DIR / "page_screenshot.png"
    import_log_path = HOYOLAB_DEBUG_DIR / "import_log.json"

    try:
        context = await exporter._create_context()
        export_page = context.pages[0] if context.pages else await context.new_page()
        print_status("opening_hoyolab")
        print("[HoYoLAB Import] Opening export page...")
        await exporter._prepare_export_page(export_page)

        # Start listening before HoYoLAB loads. The endpoint may respond quickly.
        character_list_future = await wait_for_character_list_response(export_page)
        character_list: list[dict[str, Any]] | None = None

        async def after_character_list_open() -> None:
            nonlocal character_list
            print_status("collecting_inventory")
            print("[HoYoLAB Import] Waiting for account inventory...")
            character_list = await asyncio.wait_for(character_list_future, timeout=60)
            print(f"[HoYoLAB Import] Account inventory captured: {len(character_list)} characters")

        await export_page.goto(HOYOLAB_URL, wait_until="domcontentloaded", timeout=60_000)

        print_status("exporting_image")
        print("[HoYoLAB Import] Exporting image...")
        download = await exporter._run_export_flow(
            export_page,
            after_character_list_open=after_character_list_open,
        )

        image_path.parent.mkdir(parents=True, exist_ok=True)
        await download.save_as(str(image_path))
        exporter._validate_image(image_path)

        await export_page.wait_for_timeout(500)
        print_status("building_layout")
        print("[HoYoLAB Import] Collecting layout...")
        layout = await collect_layout(export_page, exporter)
        layout["downloadedImage"] = image_path.name
        write_json(layout_path, layout)

        try:
            await export_page.screenshot(path=str(page_screenshot_path), full_page=True)
        except Exception as exc:
            print(f"[HoYoLAB Import] Could not save page screenshot: {exc}")

        print_status("writing_inventory")
        print("[HoYoLAB Import] Writing account inventory...")
        if character_list is None:
            raise HoYoLABImportError("HoYoLAB character/list was not captured during export flow.")

        characters, weapons = build_inventory(character_list)
        write_inventory(characters, weapons, HOYOLAB_DATA_DIR)

        print_status("cropping_assets")
        print("[HoYoLAB Import] Building crops and manifest...")
        manifest = build_crop_manifest(
            image_path=image_path,
            layout=layout,
            characters=characters,
            weapons=weapons,
            character_output_dir=HOYOLAB_CHARACTER_ASSETS_DIR,
            weapon_output_dir=HOYOLAB_WEAPON_ASSETS_DIR,
            manifest_path=manifest_path,
            overlay_path=overlay_path,
            relative_to=PROJECT_ROOT,
            source_layout_path=layout_path,
        )

        log = build_import_log(
            image_path=image_path,
            layout_path=layout_path,
            manifest_path=manifest_path,
            manifest=manifest,
            characters=characters,
            weapons=weapons,
            started_at=started_at,
        )
        write_json(import_log_path, log)

        print_status("done")
        print("[HoYoLAB Import] Done.")
        print(f"[HoYoLAB Import] Image: {image_path}")
        print(f"[HoYoLAB Import] Assets: {HOYOLAB_ASSETS_DIR}")
        print(f"[HoYoLAB Import] Manifest: {manifest_path}")
        print(f"[HoYoLAB Import] Cards: {manifest.get('cardsCount')}")
        print(
            "[HoYoLAB Import] Matches:",
            f"ok={manifest.get('okMatches')}",
            f"warnings={manifest.get('warningMatches')}",
        )

        return {
            "imagePath": image_path,
            "layoutPath": layout_path,
            "manifestPath": manifest_path,
            "overlayPath": overlay_path,
            "importLogPath": import_log_path,
            "manifest": manifest,
        }

    finally:
        if context is not None:
            await close_export_context(context)