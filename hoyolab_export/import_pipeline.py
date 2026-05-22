import json
import time
from pathlib import Path
from typing import Any
import asyncio

from PIL import Image
from playwright.async_api import BrowserContext, Error as PlaywrightError, Page

from .auth import AuthStatus, get_auth_status
from .artifact_db import ARTIFACT_DB_PATH
from .artifact_importer import import_character_details_payload
from .account_storage import sync_account_storage_from_local_files
from .artifact_set_catalog import (
    ensure_artifact_set_bonus_descriptions,
    ensure_artifact_set_names,
    ensure_hoyolab_set_mapping,
    normalize_language,
)
from .character_detail import fetch_character_details_batch, real_character_ids
from .collect_account_inventory import (
    build_inventory,
    wait_for_character_list_response,
    write_inventory,
)
from .crop_manifest import build_crop_manifest, character_asset_key, icon_key
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
    clear_folder_contents,
    ensure_hoyolab_dirs,
)


class HoYoLABImportError(RuntimeError):
    pass


async def get_export_page(context: BrowserContext) -> Page:
    for page in context.pages:
        if not page.is_closed():
            return page
    return await context.new_page()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def image_width(path: Path) -> int | None:
    try:
        with Image.open(path) as image:
            return int(image.width)
    except Exception:
        return None


def read_json_or_none(path: Path) -> Any | None:
    if not path.exists():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def character_inventory_key(character: dict[str, Any]) -> str:
    return character_asset_key(character)


def weapon_inventory_key(weapon: dict[str, Any]) -> str:
    parts = [
        weapon.get("id"),
        weapon.get("refinement"),
        weapon.get("level"),
        icon_key(weapon.get("icon")),
    ]

    if any(part is not None and part != "" for part in parts):
        return "|".join(str(part or "") for part in parts)

    return ""


def merge_inventory_records(
    previous: Any,
    current: list[dict[str, Any]],
    key_func,
) -> list[dict[str, Any]]:
    if not isinstance(previous, list):
        previous = []

    merged: list[dict[str, Any]] = []
    indexes: dict[str, int] = {}

    for item in previous:
        if not isinstance(item, dict):
            continue

        key = key_func(item)
        if not key or key in indexes:
            continue

        indexes[key] = len(merged)
        merged.append(item)

    for item in current:
        key = key_func(item)
        if not key:
            merged.append(item)
            continue

        if key in indexes:
            merged[indexes[key]] = item
            continue

        indexes[key] = len(merged)
        merged.append(item)

    return merged


def print_status(status: str) -> None:
    print(f"[STATUS] {status}", flush=True)


def compact_exception_summary(exc: BaseException) -> str:
    text = str(exc).split("Call log:", 1)[0].strip()
    if len(text) > 600:
        text = text[:600] + "..."
    return text or type(exc).__name__


def sync_account_storage_for_import(
    *,
    download_side_icons: bool = True,
) -> tuple[dict[str, Any] | None, str | None]:
    """Best-effort post-import account SQLite sync.

    The HoYoLAB import owns refreshing the raw source/cache files first; account
    SQLite storage is then updated from those local files. Side icons are an
    account asset cache path, so normal import opts into caching missing icons.
    """

    try:
        summary = sync_account_storage_from_local_files(
            download_side_icons=download_side_icons,
        )
    except Exception as exc:
        return None, compact_exception_summary(exc)

    return summary.to_dict(), None


def build_import_log(
    *,
    image_path: Path,
    layout_path: Path,
    manifest_path: Path,
    character_details_path: Path,
    manifest: dict[str, Any],
    characters: list[dict[str, Any]],
    weapons: list[dict[str, Any]],
    character_details: dict[str, Any] | None,
    artifact_summary: dict[str, Any] | None,
    account_storage_summary: dict[str, Any] | None = None,
    account_storage_error: str | None = None,
    started_at: float,
) -> dict[str, Any]:
    return {
        "startedAt": started_at,
        "finishedAt": time.time(),
        "image": image_path.as_posix(),
        "layout": layout_path.as_posix(),
        "manifest": manifest_path.as_posix(),
        "characterDetails": character_details_path.as_posix(),
        "characters": len(characters),
        "weapons": len(weapons),
        "characterDetailsRequested": (
            character_details.get("charactersRequested")
            if isinstance(character_details, dict)
            else None
        ),
        "characterDetailsReturned": (
            character_details.get("charactersReturned")
            if isinstance(character_details, dict)
            else None
        ),
        "artifactImport": artifact_summary,
        "cards": manifest.get("cardsCount"),
        "matchedCharacters": manifest.get("matchedCharacters"),
        "matchedWeapons": manifest.get("matchedWeapons"),
        "okMatches": manifest.get("okMatches"),
        "warningMatches": manifest.get("warningMatches"),
        "accountStorage": account_storage_summary,
        "accountStorageError": account_storage_error,
    }


async def run_hoyolab_import() -> dict[str, Any]:
    """Run full HoYoLAB import into the current MVP folders.

    Outputs:
    - data/hoyolab/account_characters.json
    - data/hoyolab/account_weapons.json
    - data/hoyolab/account_character_details.json
    - data/hoyolab/layout.json
    - data/hoyolab/crop_manifest.json
    - assets/hoyolab/characters/*.png
    - assets/hoyolab/weapons/*.png
    - data/artifacts.db
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
    ensure_hoyolab_dirs()
    clear_folder_contents(HOYOLAB_DEBUG_DIR)

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
    characters_path = HOYOLAB_DATA_DIR / "account_characters.json"
    weapons_path = HOYOLAB_DATA_DIR / "account_weapons.json"
    character_details_path = HOYOLAB_DATA_DIR / "account_character_details.json"
    account_language_path = HOYOLAB_DATA_DIR / "account_language.json"
    overlay_path = HOYOLAB_DEBUG_DIR / "crop_manifest_overlay.png"
    page_screenshot_path = HOYOLAB_DEBUG_DIR / "page_screenshot.png"
    import_log_path = HOYOLAB_DEBUG_DIR / "import_log.json"
    result: dict[str, Any] | None = None
    manifest: dict[str, Any] | None = None
    artifact_summary: dict[str, Any] | None = None
    account_storage_summary: dict[str, Any] | None = None
    account_storage_error: str | None = None

    try:
        context = await exporter._create_context()
        export_page = await get_export_page(context)
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

        try:
            await export_page.goto(HOYOLAB_URL, wait_until="domcontentloaded", timeout=60_000)
        except PlaywrightError as exc:
            message = str(exc)
            if "Target page, context or browser has been closed" in message:
                raise HoYoLABImportError(
                    "HoYoLAB automation browser closed before the page loaded. "
                    "Close any HoYoLAB authorization/automation browser windows and try again."
                ) from exc
            raise

        print_status("exporting_image")
        print("[HoYoLAB Import] Exporting image...")
        download = await exporter._run_export_flow(
            export_page,
            after_character_list_open=after_character_list_open,
            status_callback=print_status,
        )

        image_path.parent.mkdir(parents=True, exist_ok=True)
        print_status("downloading_image")
        await download.save_as(str(image_path))
        print_status("image_downloaded")
        exporter._validate_image(image_path)

        await export_page.wait_for_timeout(500)
        print_status("building_layout")
        print("[HoYoLAB Import] Collecting layout...")
        layout = await collect_layout(export_page, exporter)
        layout["downloadedImage"] = image_path.name
        actual_image_width = image_width(image_path)
        if actual_image_width and exporter.fixed_container_width:
            actual_scale = actual_image_width / exporter.fixed_container_width
            if actual_scale > 0:
                layout.setdefault("exporter", {})["scale"] = actual_scale
                layout["exporter"]["actualImageWidth"] = actual_image_width

        try:
            await export_page.screenshot(path=str(page_screenshot_path), full_page=True)
        except Exception as exc:
            print(f"[HoYoLAB Import] Could not save page screenshot: {exc}")

        print_status("writing_inventory")
        print("[HoYoLAB Import] Building account inventory...")
        if character_list is None:
            raise HoYoLABImportError("HoYoLAB character/list was not captured during export flow.")

        characters, weapons = build_inventory(character_list)

        real_ids = real_character_ids(characters)
        print_status("fetching_character_details")
        print(
            "[HoYoLAB Import] Fetching character/detail batch:",
            f"{len(real_ids)} characters",
        )
        character_details = await fetch_character_details_batch(export_page, real_ids)

        content_language = normalize_language(character_details.get("detectedLanguage"))
        print(f"[HoYoLAB Import] HoYoLAB content language: {content_language}")
        print_status("updating_artifact_catalog")
        set_names_summary = ensure_artifact_set_names(
            content_language,
            db_path=ARTIFACT_DB_PATH,
        )
        set_bonus_summary = ensure_artifact_set_bonus_descriptions(
            content_language,
            db_path=ARTIFACT_DB_PATH,
        )
        write_json(
            account_language_path,
            {
                "contentLanguage": content_language,
                "source": "character/detail.x-rpc-language",
                "capturedAt": int(time.time() * 1000),
                "artifactSetNames": set_names_summary,
                "artifactSetBonusDescriptions": set_bonus_summary,
            },
        )

        print_status("mapping_artifact_sets")
        print("[HoYoLAB Import] Preparing artifact set id mapping...")
        set_mapping_summary = await ensure_hoyolab_set_mapping(
            character_details,
            export_page,
            real_ids,
            db_path=ARTIFACT_DB_PATH,
        )

        print_status("closing_browser")
        print("[HoYoLAB Import] Closing HoYoLAB browser...")
        await close_export_context(context)
        context = None

        print_status("importing_artifacts")
        print("[HoYoLAB Import] Importing artifacts into SQLite...")
        artifact_summary = import_character_details_payload(
            character_details,
            db_path=ARTIFACT_DB_PATH,
        )
        artifact_summary["set_names"] = set_names_summary
        artifact_summary["set_mapping"] = set_mapping_summary

        print_status("updating_hoyolab_data")
        print("[HoYoLAB Import] Updating local HoYoLAB data/assets...")
        previous_manifest = read_json_or_none(manifest_path)
        previous_characters = read_json_or_none(characters_path)
        previous_weapons = read_json_or_none(weapons_path)
        merged_characters = merge_inventory_records(
            previous_characters,
            characters,
            character_inventory_key,
        )
        merged_weapons = merge_inventory_records(
            previous_weapons,
            weapons,
            weapon_inventory_key,
        )
        ensure_hoyolab_dirs()
        write_json(layout_path, layout)
        write_inventory(merged_characters, merged_weapons, HOYOLAB_DATA_DIR)
        write_json(character_details_path, character_details)

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
            previous_manifest=previous_manifest,
            merge_existing_assets=True,
        )

        print_status("syncing_account_storage")
        print("[HoYoLAB Import] Syncing account SQLite storage...")
        account_storage_summary, account_storage_error = sync_account_storage_for_import(
            download_side_icons=True,
        )
        if account_storage_error:
            print_status("account_storage_sync_warning")
            print(
                "[HoYoLAB Import] Account SQLite sync failed after raw import:",
                account_storage_error,
            )
        elif account_storage_summary:
            warnings = account_storage_summary.get("warnings") or []
            print(
                "[HoYoLAB Import] Account SQLite:",
                f"characters={account_storage_summary.get('characters_seen')}",
                f"talents={account_storage_summary.get('talents_seen')}",
                f"weapon_stacks={account_storage_summary.get('weapon_stacks_seen')}",
                f"warnings={len(warnings)}",
            )

        print_status("writing_import_log")
        log = build_import_log(
            image_path=image_path,
            layout_path=layout_path,
            manifest_path=manifest_path,
            character_details_path=character_details_path,
            manifest=manifest,
            characters=characters,
            weapons=weapons,
            character_details=character_details,
            artifact_summary=artifact_summary,
            account_storage_summary=account_storage_summary,
            account_storage_error=account_storage_error,
            started_at=started_at,
        )
        write_json(import_log_path, log)

        result = {
            "imagePath": image_path,
            "layoutPath": layout_path,
            "manifestPath": manifest_path,
            "characterDetailsPath": character_details_path,
            "accountLanguagePath": account_language_path,
            "overlayPath": overlay_path,
            "importLogPath": import_log_path,
            "manifest": manifest,
            "artifactSummary": artifact_summary,
            "accountStorageSummary": account_storage_summary,
            "accountStorageError": account_storage_error,
        }
        return result

    finally:
        if context is not None:
            await close_export_context(context)

        if result is not None and manifest is not None and artifact_summary is not None:
            print_status("done")
            print("[HoYoLAB Import] Done.")
            print(f"[HoYoLAB Import] Image: {image_path}")
            print(f"[HoYoLAB Import] Assets: {HOYOLAB_ASSETS_DIR}")
            print(f"[HoYoLAB Import] Manifest: {manifest_path}")
            print(f"[HoYoLAB Import] Character details: {character_details_path}")
            print(f"[HoYoLAB Import] Cards: {manifest.get('cardsCount')}")
            print(
                "[HoYoLAB Import] Artifacts:",
                f"seen={artifact_summary.get('relics_seen')}",
                f"inserted={artifact_summary.get('artifacts_inserted')}",
                f"existing={artifact_summary.get('artifacts_existing')}",
            )
            print(
                "[HoYoLAB Import] Matches:",
                f"ok={manifest.get('okMatches')}",
                f"warnings={manifest.get('warningMatches')}",
            )
            if account_storage_summary:
                warnings = account_storage_summary.get("warnings") or []
                print(
                    "[HoYoLAB Import] Account SQLite:",
                    f"characters={account_storage_summary.get('characters_seen')}",
                    f"talents={account_storage_summary.get('talents_seen')}",
                    f"weapon_stacks={account_storage_summary.get('weapon_stacks_seen')}",
                    f"warnings={len(warnings)}",
                )
            elif account_storage_error:
                print(
                    "[HoYoLAB Import] Account SQLite warning:",
                    account_storage_error,
                )
