import json
import time
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Any
import asyncio

from playwright.async_api import BrowserContext, Error as PlaywrightError, Page

from .auth import AuthStatus, get_auth_status
from .artifact_db import ARTIFACT_DB_PATH, connect_db
from .artifact_importer import import_character_details_payload, unwrap_hoyolab_payload
from .account_storage import sync_account_storage_from_local_files, weapon_equipment_from_detail_rows
from .account_equipment import apply_hoyolab_equipment_snapshot
from .abyss_source_refresh import (
    DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH,
    HoYoLABAbyssPeriod,
    context_request_fetch_json,
    resolve_abyss_period_with_fallbacks,
    refresh_cached_abyss_source_data_for_hoyolab_period,
    write_hoyolab_abyss_period,
)
from .artifact_set_catalog import (
    ensure_artifact_set_catalog,
    ensure_artifact_set_bonus_descriptions,
    ensure_artifact_set_names,
    ensure_hoyolab_set_mapping,
    normalize_language,
)
from .character_trait_catalog import load_or_refresh_character_trait_catalog
from .character_trait_catalog import rebuild_character_trait_reference_from_catalog
from .character_region_catalog import load_character_region_catalog
from .character_detail import ROLES_URL, fetch_character_details_batch, real_character_ids
from .collect_account_inventory import (
    build_inventory,
    wait_for_character_list_response,
)
from .crop_manifest import character_asset_key, icon_key
from .asset_layers import capture_card_layer_sources, cleanup_unused_v2_assets, prepare_layered_assets
from .display_stat_effects import (
    read_weapon_wiki_from_account_detail_cache,
    rebuild_artifact_set_display_stat_effects,
    rebuild_weapon_passive_tooltips,
    rebuild_weapon_display_stat_effects,
    weapon_entry_page_id_to_weapon_id_map,
)
from .hoyowiki_catalog_refresh import refresh_weapon_stats_catalog_entries
from .import_static_cache import ImportArtifactSetLists
from .hoyolab_exporter import HOYOLAB_URL, HoyolabExporter, close_export_context
from .paths import (
    HOYOLAB_ASSETS_DIR,
    HOYOLAB_DATA_DIR,
    HOYOLAB_DEBUG_DIR,
    HOYOLAB_PROFILE_DIR,
    PROJECT_ROOT,
    clear_folder_contents,
    ensure_hoyolab_dirs,
)


class HoYoLABImportError(RuntimeError):
    pass


CHARACTER_LIST_URL = "https://sg-act-public-api.hoyolab.com/event/game_record/genshin/api/character/list"
FAST_REQUEST_TIMEOUT_MS = 6_000


async def fast_context_request_fetch_json(page: Page, url: str, **kwargs) -> dict[str, Any]:
    """Bound the API shortcut so a stalled request reaches browser fallback soon."""
    return await asyncio.wait_for(
        context_request_fetch_json(page, url, timeout_ms=FAST_REQUEST_TIMEOUT_MS, **kwargs),
        timeout=(FAST_REQUEST_TIMEOUT_MS + 1_000) / 1_000,
    )


async def fetch_character_list_direct(page: Page) -> tuple[list[dict[str, Any]], dict[str, str]] | None:
    """Use the authenticated API when its Genshin role is unambiguous.

    Multi-role accounts retain the browser's selected-role behavior. Any API
    failure is left to the normal browser path, which reports its own error.
    """
    try:
        roles_result = await fast_context_request_fetch_json(page, ROLES_URL)
        roles_payload = roles_result.get("json") or {}
        if not roles_result.get("ok") or roles_payload.get("retcode") != 0:
            return None
        roles = (roles_payload.get("data") or {}).get("list") or []
        genshin_roles = [role for role in roles if isinstance(role, dict) and role.get("game_biz") == "hk4e_global"]
        if len(genshin_roles) != 1:
            return None
        role = genshin_roles[0]
        role_id = str(role.get("game_uid") or role.get("game_role_id") or role.get("role_id") or "")
        server = str(role.get("region") or role.get("server") or "")
        if not role_id or not server:
            return None
        list_result = await fast_context_request_fetch_json(
            page, CHARACTER_LIST_URL, method="POST", body={"server": server, "role_id": role_id},
        )
        list_payload = list_result.get("json") or {}
        items = (list_payload.get("data") or {}).get("list")
        if not list_result.get("ok") or list_payload.get("retcode") != 0 or not isinstance(items, list) or not items:
            return None
        return items, {"role_id": role_id, "server": server}
    except Exception:
        return None


async def get_export_page(context: BrowserContext) -> Page:
    for page in context.pages:
        if not page.is_closed():
            return page
    return await context.new_page()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
        temporary_path = Path(file.name)
        try:
            json.dump(data, file, ensure_ascii=False, indent=2)
        except BaseException:
            file.close()
            temporary_path.unlink(missing_ok=True)
            raise
    try:
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def read_json_or_none(path: Path) -> Any | None:
    if not path.exists():
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _publish_staged_images(staging_root: Path) -> None:
    for staged_path in staging_root.rglob("*.png"):
        final_path = PROJECT_ROOT / staged_path.relative_to(staging_root)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        staged_path.replace(final_path)


def _sync_image_paths_only(manifest: dict[str, Any]) -> None:
    """Update only existing account image columns after an image-only refresh."""
    with closing(connect_db(ARTIFACT_DB_PATH)) as conn, conn:
        required = {"account_characters", "account_weapon_observed_stacks"}
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not required <= tables:
            raise HoYoLABImportError("Import account data once before refreshing only images.")
        for asset in manifest.get("characterAssets") or []:
            conn.execute(
                "UPDATE account_characters SET portrait_path = ? WHERE character_id = ?",
                (asset["crop"], int(asset["character"]["id"])),
            )
        by_icon = {icon_key(asset["weapon"].get("icon")): asset["crop"] for asset in manifest.get("weaponAssets") or []}
        by_id = {int(asset["weapon"]["id"]): asset["crop"] for asset in manifest.get("weaponAssets") or []}
        for row in conn.execute("SELECT id, weapon_id, icon_url FROM account_weapon_observed_stacks"):
            path = by_icon.get(icon_key(row["icon_url"])) or by_id.get(row["weapon_id"])
            if path:
                conn.execute("UPDATE account_weapon_observed_stacks SET icon_path = ? WHERE id = ?", (path, row["id"]))


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


def sync_static_reference_catalogs_for_import(
    content_language: str | None = None,
    *,
    weapon_wiki: dict[str, Any] | None = None,
    artifact_set_list_fetcher=None,
) -> tuple[dict[str, Any], str | None]:
    """Best-effort HoYoWiki static catalog refresh used by normal import."""

    summary: dict[str, Any] = {}
    errors: list[str] = []

    try:
        summary["artifactSetCatalog"] = ensure_artifact_set_catalog(
            db_path=ARTIFACT_DB_PATH,
            allow_network=True,
            missing_only=True,
            list_fetcher=artifact_set_list_fetcher,
        )
    except Exception as exc:
        errors.append(f"artifact set catalog: {compact_exception_summary(exc)}")

    try:
        trait_catalog = load_or_refresh_character_trait_catalog()
        with closing(connect_db(ARTIFACT_DB_PATH)) as conn, conn:
            trait_reference_rows = rebuild_character_trait_reference_from_catalog(
                conn,
                trait_catalog,
            )
            conn.commit()
        summary["characterTraitCatalog"] = {
            "source": trait_catalog.source,
            "entries": len(trait_catalog.entries),
            "sqlite_reference_rows": trait_reference_rows,
            "fetched_at": trait_catalog.fetched_at,
        }
    except Exception as exc:
        errors.append(f"character trait catalog: {compact_exception_summary(exc)}")

    try:
        if content_language:
            region_entries = load_character_region_catalog(content_language, allow_network=True)
            summary["characterRegionCatalog"] = {
                "language": content_language,
                "entries": len(region_entries),
            }
    except Exception as exc:
        errors.append(f"character region catalog: {compact_exception_summary(exc)}")

    try:
        entry_ids = tuple(weapon_entry_page_id_to_weapon_id_map(weapon_wiki or {}).keys())
        if content_language and entry_ids:
            result = refresh_weapon_stats_catalog_entries(
                entry_ids,
                language=content_language,
            )
            summary["localizedWeaponStatsCatalog"] = result.to_dict()
            with closing(connect_db(ARTIFACT_DB_PATH)) as conn, conn:
                summary["weaponPassiveTooltips"] = {
                    "language": content_language,
                    "rows": rebuild_weapon_passive_tooltips(
                        conn,
                        weapon_wiki=weapon_wiki or {},
                        language=content_language,
                    ),
                }
                conn.commit()
    except Exception as exc:
        errors.append(
            f"localized weapon stats/passive tooltips: {compact_exception_summary(exc)}"
        )

    return summary, "; ".join(errors) if errors else None


def refresh_abyss_source_data_for_import(
    period: HoYoLABAbyssPeriod | None,
    *,
    floor: int = 12,
    status_callback=print_status,
    refresher=refresh_cached_abyss_source_data_for_hoyolab_period,
) -> tuple[dict[str, Any] | None, str | None]:
    """Best-effort Abyss source refresh used by the normal HoYoLAB import."""

    if period is None:
        return None, "official_abyss_period_unavailable"
    if status_callback is not None:
        status_callback("updating_abyss_source_data")
    summary, error = refresher(period, floor=floor)
    if status_callback is not None and isinstance(summary, dict):
        if summary.get("skipped"):
            status_callback("skipping_abyss_source_data_refresh")
        else:
            assets = summary.get("assets")
            if isinstance(assets, dict) and assets.get("enabled"):
                status_callback("caching_abyss_monster_icons")
    return summary, error


async def prepare_artifact_mapping_for_import(
    character_details, export_page, real_ids, artifact_set_lists, static_catalog_summary,
    content_language,
):
    """Keep reference-data failures separate from the account payload import."""
    try:
        summary = await ensure_hoyolab_set_mapping(
            character_details, export_page, real_ids, db_path=ARTIFACT_DB_PATH,
            allow_unmapped=True,
        )
        if summary.get("unmapped") and "fresh_cache" in artifact_set_lists.sources.values():
            fresh_lists = ImportArtifactSetLists(force_network=True)
            ensure_artifact_set_catalog(
                db_path=ARTIFACT_DB_PATH, allow_network=True, missing_only=True,
                list_fetcher=fresh_lists,
            )
            ensure_artifact_set_names(
                content_language, db_path=ARTIFACT_DB_PATH, list_fetcher=fresh_lists,
            )
            ensure_artifact_set_bonus_descriptions(
                content_language, db_path=ARTIFACT_DB_PATH, list_fetcher=fresh_lists,
            )
            static_catalog_summary["artifactSetListSources"].update(fresh_lists.sources)
            static_catalog_summary["artifactSetListRefreshedForUnknownMapping"] = True
            summary = await ensure_hoyolab_set_mapping(
                character_details, export_page, real_ids, db_path=ARTIFACT_DB_PATH,
                allow_unmapped=True,
            )
        return summary
    except Exception as exc:
        # The artifact importer independently resolves each set against SQLite;
        # only unresolved artifacts are skipped, without guessing their identity.
        return {"error": type(exc).__name__}


def _weapon_wiki_from_character_details(character_details: dict[str, Any] | None) -> dict[str, Any]:
    payload = (character_details or {}).get("json")
    if not isinstance(payload, dict):
        payload = character_details or {}
    data = payload.get("data") if isinstance(payload, dict) else {}
    weapon_wiki = data.get("weapon_wiki") if isinstance(data, dict) else {}
    return dict(weapon_wiki) if isinstance(weapon_wiki, dict) else {}


def build_import_log(
    *,
    image_path: Path | None,
    layout_path: Path | None,
    manifest_path: Path,
    character_details_path: Path,
    manifest: dict[str, Any],
    characters: list[dict[str, Any]],
    weapons: list[dict[str, Any]],
    character_details: dict[str, Any] | None,
    artifact_summary: dict[str, Any] | None,
    account_storage_summary: dict[str, Any] | None = None,
    account_storage_error: str | None = None,
    static_catalog_summary: dict[str, Any] | None = None,
    static_catalog_error: str | None = None,
    abyss_period_path: Path | None = None,
    abyss_period: dict[str, Any] | None = None,
    abyss_period_error: str | None = None,
    abyss_source_data_summary: dict[str, Any] | None = None,
    abyss_source_data_error: str | None = None,
    started_at: float,
) -> dict[str, Any]:
    return {
        "startedAt": started_at,
        "finishedAt": time.time(),
        "image": image_path.as_posix() if image_path else None,
        "layout": layout_path.as_posix() if layout_path else None,
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
        "staticCatalogs": static_catalog_summary,
        "staticCatalogError": static_catalog_error,
        "abyssPeriod": abyss_period,
        "abyssPeriodPath": abyss_period_path.as_posix() if abyss_period_path else None,
        "abyssPeriodError": abyss_period_error,
        "abyssSourceData": abyss_source_data_summary,
        "abyssSourceDataError": abyss_source_data_error,
    }


async def run_hoyolab_import(*, change_equipment: bool = False, images_only: bool = False) -> dict[str, Any]:
    """Run full HoYoLAB import into the current MVP folders.

    Outputs:
    - data/hoyolab/account_characters.json
    - data/hoyolab/account_weapons.json
    - data/hoyolab/account_character_details.json
    - data/hoyolab/crop_manifest.json
    - assets/hoyolab/characters/*.png
    - assets/hoyolab/weapons/*.png
    - assets/hoyolab/shared/*.png
    - data/artifacts.db
    - debug/hoyolab/import_log.json
    """
    started_at = time.time()
    current_stage = "preparing"
    browser_events = []
    stage_events = []

    def report_status(status):
        nonlocal current_stage
        current_stage = status
        stage_events.append({"stage": status, "elapsedSeconds": round(time.time() - started_at, 2)})
        print_status(status)

    def record_browser_event(event):
        browser_events.append({"event": event, "stage": current_stage,
                               "elapsedSeconds": round(time.time() - started_at, 2)})

    if get_auth_status(HOYOLAB_PROFILE_DIR) != AuthStatus.LOGGED_IN:
        raise HoYoLABImportError(
            "HoYoLAB profile is not logged in. Authorize in the app first."
        )

    report_status("preparing")
    ensure_hoyolab_dirs()
    clear_folder_contents(HOYOLAB_DEBUG_DIR)

    exporter = HoyolabExporter(
        profile_dir=HOYOLAB_PROFILE_DIR,
        download_dir=HOYOLAB_DEBUG_DIR,
        scale=1,
    )

    context: BrowserContext | None = None
    export_page = None
    character_list_future = None
    character_list_request: dict[str, str] = {}
    staged_assets = None

    manifest_path = HOYOLAB_DATA_DIR / "crop_manifest.json"
    characters_path = HOYOLAB_DATA_DIR / "account_characters.json"
    weapons_path = HOYOLAB_DATA_DIR / "account_weapons.json"
    character_details_path = HOYOLAB_DATA_DIR / "account_character_details.json"
    account_language_path = HOYOLAB_DATA_DIR / "account_language.json"
    abyss_period_path = DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH
    import_log_path = HOYOLAB_DEBUG_DIR / "import_log.json"
    result: dict[str, Any] | None = None
    manifest: dict[str, Any] | None = None
    artifact_summary: dict[str, Any] | None = None
    account_storage_summary: dict[str, Any] | None = None
    account_storage_error: str | None = None
    static_catalog_summary: dict[str, Any] | None = None
    static_catalog_error: str | None = None
    abyss_period: HoYoLABAbyssPeriod | None = None
    abyss_period_error: str | None = None
    abyss_source_data_summary: dict[str, Any] | None = None
    abyss_source_data_error: str | None = None
    import_warnings: list[dict[str, Any]] = []

    try:
        context = await exporter._create_context()
        export_page = await get_export_page(context)
        export_page.on("close", lambda *_: record_browser_event("page_closed"))
        export_page.on("crash", lambda *_: record_browser_event("page_crashed"))
        if context.browser is not None:
            context.browser.on("disconnected", lambda *_: record_browser_event("browser_disconnected"))
        report_status("opening_hoyolab")
        print("[HoYoLAB Import] Opening export page...")

        # Start listening before HoYoLAB loads. The endpoint may respond quickly.
        character_list_future = await wait_for_character_list_response(
            export_page, request_context=character_list_request,
        )
        character_list: list[dict[str, Any]] | None = None

        async def after_character_list_open() -> None:
            nonlocal character_list
            report_status("collecting_inventory")
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

        report_status("opening_character_list")
        direct_list = await fetch_character_list_direct(export_page)
        if direct_list is not None:
            character_list, account_context_from_api = direct_list
            character_list_request.update(account_context_from_api)
            character_list_future.cancel()
            cards = []
            report_status("collecting_inventory")
            print(f"[HoYoLAB Import] Account inventory captured directly: {len(character_list)} characters")
        else:
            await exporter._wait_until_ready_or_login(export_page)
            await exporter._click_with_popup_retry(export_page, ".block-title-right")
            await export_page.locator(".me-share__btn").first.wait_for(state="visible", timeout=30_000)
            await after_character_list_open()
            report_status("collecting_asset_urls")
            cards = await capture_card_layer_sources(export_page)

        report_status("writing_inventory")
        print("[HoYoLAB Import] Building account inventory...")
        if character_list is None:
            raise HoYoLABImportError("HoYoLAB character/list was not captured during export flow.")

        characters, weapons = build_inventory(character_list)

        # Stage every cache miss before mutating the account files.
        staged_assets = tempfile.TemporaryDirectory(prefix="import-assets-", dir=HOYOLAB_DEBUG_DIR)
        staging_root = Path(staged_assets.name)
        report_status("downloading_assets")
        print("[HoYoLAB Import] Caching unique image layers and rendering display variants...")
        manifest = await prepare_layered_assets(
            characters=characters, weapons=weapons, cards=cards,
            staging_root=staging_root, refresh_images=images_only,
        )
        if not manifest.get("cardsCount"):
            raise HoYoLABImportError("HoYoLAB inventory produced no characters; existing account data was preserved.")

        if images_only:
            report_status("closing_browser")
            await close_export_context(context)
            context = None
            report_status("updating_hoyolab_data")
            _publish_staged_images(staging_root)
            _sync_image_paths_only(manifest)
            write_json(manifest_path, manifest)
            cleanup_failures = cleanup_unused_v2_assets(manifest)
            if cleanup_failures:
                print(f"[HoYoLAB Import] Could not retire {len(cleanup_failures)} old images; retry on next import.")
            result = {"manifest": manifest, "manifestPath": manifest_path, "imagesOnly": True}
            return result

        real_ids = real_character_ids(characters)
        report_status("fetching_character_details")
        print(
            "[HoYoLAB Import] Fetching character/detail batch:",
            f"{len(real_ids)} characters",
        )
        account_context = (
            {"role_id": character_list_request["role_id"], "server": character_list_request["server"]}
            if character_list_request.get("role_id") and character_list_request.get("server")
            else {}
        )
        if direct_list is not None:
            try:
                character_details = await fetch_character_details_batch(
                    export_page, real_ids, json_fetcher=fast_context_request_fetch_json, **account_context,
                )
            except Exception:
                # The page request remains the established fallback for
                # transient BrowserContext.request or API differences.
                print("[HoYoLAB Import] Direct detail request failed; retrying through the page.")
                character_details = await fetch_character_details_batch(
                    export_page, real_ids, **account_context,
                )
        else:
            character_details = await fetch_character_details_batch(export_page, real_ids, **account_context)

        content_language = normalize_language(character_details.get("detectedLanguage"))
        print(f"[HoYoLAB Import] HoYoLAB content language: {content_language}")
        try:
            report_status("fetching_abyss_period")
            print("[HoYoLAB Import] Resolving Spiral Abyss period...")
            abyss_period = await resolve_abyss_period_with_fallbacks(
                export_page,
                language=content_language,
                **account_context,
            )
            print(
                "[HoYoLAB Import] Spiral Abyss period:",
                abyss_period.raw_period,
                f"({abyss_period.start_date} -> {abyss_period.end_date})",
                f"source={abyss_period.source}",
            )
        except Exception as exc:
            abyss_period_error = compact_exception_summary(exc)
            print(
                "[HoYoLAB Import] Spiral Abyss period warning:",
                abyss_period_error,
            )
        report_status("updating_artifact_catalog")
        artifact_set_lists = ImportArtifactSetLists()
        static_catalog_summary, static_catalog_error = sync_static_reference_catalogs_for_import(
            content_language,
            weapon_wiki=_weapon_wiki_from_character_details(character_details),
            artifact_set_list_fetcher=artifact_set_lists,
        )
        if static_catalog_error:
            print(
                "[HoYoLAB Import] Static HoYoWiki catalog refresh warning:",
                static_catalog_error,
            )
        try:
            set_names_summary = ensure_artifact_set_names(
                content_language, db_path=ARTIFACT_DB_PATH, list_fetcher=artifact_set_lists,
            )
        except Exception as exc:
            set_names_summary = {"error": type(exc).__name__}
        try:
            set_bonus_summary = ensure_artifact_set_bonus_descriptions(
                content_language, db_path=ARTIFACT_DB_PATH, list_fetcher=artifact_set_lists,
            )
        except Exception as exc:
            set_bonus_summary = {"error": type(exc).__name__}
        static_catalog_summary["artifactSetListSources"] = dict(artifact_set_lists.sources)
        if artifact_set_lists.cleanup_failures:
            static_catalog_summary["artifactSetListCleanupWarnings"] = list(artifact_set_lists.cleanup_failures)

        report_status("mapping_artifact_sets")
        print("[HoYoLAB Import] Preparing artifact set id mapping...")
        set_mapping_summary = await prepare_artifact_mapping_for_import(
            character_details, export_page, real_ids, artifact_set_lists,
            static_catalog_summary, content_language,
        )
        if (static_catalog_error or set_names_summary.get("error")
                or set_bonus_summary.get("error") or set_mapping_summary.get("error")):
            import_warnings.append({"code": "reference_catalog_incomplete"})

        report_status("closing_browser")
        print("[HoYoLAB Import] Closing HoYoLAB browser...")
        await close_export_context(context)
        context = None

        report_status("importing_artifacts")
        print("[HoYoLAB Import] Importing artifacts into SQLite...")
        try:
            artifact_summary = import_character_details_payload(
                character_details, db_path=ARTIFACT_DB_PATH, skip_unmapped_sets=True,
            )
        except Exception as exc:
            artifact_summary = {"error": type(exc).__name__, "equipment_updated": False}
            import_warnings.append({"code": "artifacts_not_imported"})
        if artifact_summary.get("relics_skipped_unmapped"):
            import_warnings.append({
                "code": "artifact_sets_unmapped",
                "count": artifact_summary["relics_skipped_unmapped"],
                "sets": artifact_summary["unmapped_sets"],
            })
        artifact_summary["static_catalogs"] = static_catalog_summary
        artifact_summary["static_catalog_error"] = static_catalog_error
        artifact_summary["set_names"] = set_names_summary
        artifact_summary["set_mapping"] = set_mapping_summary

        report_status("updating_hoyolab_data")
        print("[HoYoLAB Import] Updating local HoYoLAB data/assets...")
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
        write_json(characters_path, merged_characters)
        write_json(weapons_path, merged_weapons)
        write_json(character_details_path, character_details)
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
        if abyss_period is not None:
            write_hoyolab_abyss_period(abyss_period, period_path=abyss_period_path)
        try:
            with closing(connect_db(ARTIFACT_DB_PATH)) as conn, conn:
                static_catalog_summary["staticDisplayEffects"] = {
                    "artifact_set_rows": rebuild_artifact_set_display_stat_effects(conn),
                    "weapon_rows": rebuild_weapon_display_stat_effects(
                        conn,
                        weapon_wiki=read_weapon_wiki_from_account_detail_cache(
                            character_details_path
                        ),
                    ),
                }
        except Exception as exc:
            static_catalog_summary["staticDisplayEffectsError"] = compact_exception_summary(exc)

        _publish_staged_images(staging_root)
        write_json(manifest_path, manifest)
        cleanup_failures = cleanup_unused_v2_assets(manifest)
        if cleanup_failures:
            print(f"[HoYoLAB Import] Could not retire {len(cleanup_failures)} old images; retry on next import.")

        report_status("syncing_account_storage")
        print("[HoYoLAB Import] Syncing account SQLite storage...")
        account_storage_summary, account_storage_error = sync_account_storage_for_import(
            download_side_icons=True,
        )
        if account_storage_error:
            import_warnings.append({"code": "account_storage_sync_failed"})
            report_status("account_storage_sync_warning")
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

        if abyss_period is not None:
            print(
                "[HoYoLAB Import] Updating Abyss Floor 12 source-data cache:",
                abyss_period.raw_period,
            )
            abyss_source_data_summary, abyss_source_data_error = (
                refresh_abyss_source_data_for_import(
                    abyss_period,
                    floor=12,
                )
            )
            if abyss_source_data_error:
                print(
                    "[HoYoLAB Import] Abyss source-data cache warning:",
                    abyss_source_data_error,
                )
            elif abyss_source_data_summary:
                print(
                    "[HoYoLAB Import] Abyss source-data cache:",
                    f"rows={abyss_source_data_summary.get('enemyRows')}",
                    f"matched={abyss_source_data_summary.get('matched')}",
                    f"path={abyss_source_data_summary.get('cachePath')}",
                    f"skipped={abyss_source_data_summary.get('skipped')}",
                )
        elif abyss_period_error:
            abyss_source_data_error = (
                "official_abyss_period_unavailable: " + abyss_period_error
            )

        equipment_summary = None
        if change_equipment:
            if account_storage_error or not artifact_summary.get("equipment_updated", True):
                equipment_summary = {"applied": False, "reason": "incomplete_import"}
            else:
                report_status("applying_equipment")
                try:
                    detail_rows = unwrap_hoyolab_payload(character_details)["data"]["list"]
                    weapons_to_apply = weapon_equipment_from_detail_rows(detail_rows)
                    with closing(connect_db(ARTIFACT_DB_PATH)) as conn, conn:
                        artifacts_to_apply = [
                            (int(row["character_id"]), int(row["artifact_id"]))
                            for row in conn.execute("SELECT character_id, artifact_id FROM artifact_equipment")
                        ]
                        equipment_summary = apply_hoyolab_equipment_snapshot(
                            conn, artifacts=artifacts_to_apply, weapons=weapons_to_apply,
                        )
                    equipment_summary["applied"] = True
                except Exception as exc:
                    equipment_summary = {"applied": False, "error": type(exc).__name__}
            if not equipment_summary["applied"]:
                import_warnings.append({"code": "equipment_not_applied"})
        report_status("writing_import_log")
        log = build_import_log(
            image_path=None,
            layout_path=None,
            manifest_path=manifest_path,
            character_details_path=character_details_path,
            manifest=manifest,
            characters=characters,
            weapons=weapons,
            character_details=character_details,
            artifact_summary=artifact_summary,
            account_storage_summary=account_storage_summary,
            account_storage_error=account_storage_error,
            static_catalog_summary=static_catalog_summary,
            static_catalog_error=static_catalog_error,
            abyss_period_path=abyss_period_path if abyss_period is not None else None,
            abyss_period=abyss_period.to_dict() if abyss_period is not None else None,
            abyss_period_error=abyss_period_error,
            abyss_source_data_summary=abyss_source_data_summary,
            abyss_source_data_error=abyss_source_data_error,
            started_at=started_at,
        )
        log["browserLifecycle"] = browser_events
        log["stageEvents"] = stage_events
        log["equipmentApplied"] = equipment_summary
        log["warnings"] = import_warnings
        write_json(import_log_path, log)

        result = {
            "imagePath": None,
            "layoutPath": None,
            "manifestPath": manifest_path,
            "characterDetailsPath": character_details_path,
            "accountLanguagePath": account_language_path,
            "overlayPath": None,
            "importLogPath": import_log_path,
            "manifest": manifest,
            "artifactSummary": artifact_summary,
            "accountStorageSummary": account_storage_summary,
            "accountStorageError": account_storage_error,
            "abyssPeriodPath": abyss_period_path if abyss_period is not None else None,
            "abyssPeriod": abyss_period.to_dict() if abyss_period is not None else None,
            "abyssPeriodError": abyss_period_error,
            "abyssSourceDataSummary": abyss_source_data_summary,
            "abyssSourceDataError": abyss_source_data_error,
            "equipmentApplied": equipment_summary,
            "warnings": import_warnings,
        }
        return result

    except Exception as exc:
        # Capture BEFORE cleanup so a closed target is distinguishable from our
        # own shutdown. No URLs, headers, cookies, payloads or exception text.
        try:
            process = getattr(context, "_browser_process", None) if context is not None else None
            exit_code = process.poll() if process is not None else None
            failure = {
                "stage": current_stage,
                "errorType": type(exc).__name__,
                "pageClosed": bool(export_page.is_closed()) if export_page is not None else None,
                "browserExitCode": exit_code if isinstance(exit_code, int) else None,
                "browserEvents": browser_events,
            }
            write_json(HOYOLAB_DEBUG_DIR / "import_failure.json", failure)
            print(f"[HoYoLAB Import] Failure stage: {current_stage}; page_closed={failure['pageClosed']}; browser_exit={failure['browserExitCode']}")
        except Exception:
            pass
        raise
    finally:
        if character_list_future is not None:
            if not character_list_future.done():
                character_list_future.cancel()
            elif not character_list_future.cancelled():
                # An early export failure can leave a captured API error unconsumed.
                character_list_future.exception()
        if context is not None:
            await close_export_context(context)
        if staged_assets is not None:
            try:
                staged_assets.cleanup()
            except OSError as exc:
                print(f"[HoYoLAB Import] Staging cleanup warning: {type(exc).__name__}")

        if result is not None and manifest is not None and (artifact_summary is not None or images_only):
            report_status("done")
            print("[HoYoLAB Import] Done.")
            print(f"[HoYoLAB Import] Unique images downloaded: {manifest.get('assetsDownloaded')}; variants rendered: {manifest.get('assetsRendered')}")
            print(f"[HoYoLAB Import] Assets: {HOYOLAB_ASSETS_DIR}")
            print(f"[HoYoLAB Import] Manifest: {manifest_path}")
            if not images_only:
                print(f"[HoYoLAB Import] Character details: {character_details_path}")
            print(f"[HoYoLAB Import] Cards: {manifest.get('cardsCount')}")
            if artifact_summary is not None:
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
            if abyss_source_data_summary:
                print(
                    "[HoYoLAB Import] Abyss source-data cache:",
                    f"period={abyss_source_data_summary.get('period', {}).get('rawPeriod')}",
                    f"rows={abyss_source_data_summary.get('enemyRows')}",
                    f"matched={abyss_source_data_summary.get('matched')}",
                    f"skipped={abyss_source_data_summary.get('skipped')}",
                )
            elif abyss_source_data_error:
                print(
                    "[HoYoLAB Import] Abyss source-data warning:",
                    abyss_source_data_error,
                )
