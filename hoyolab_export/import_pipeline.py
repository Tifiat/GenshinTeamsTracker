import json
import time
import tempfile
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from pathlib import Path
from typing import Any
import asyncio
from urllib.parse import urlsplit

from playwright.async_api import BrowserContext, Page

from .auth import AuthStatus, get_auth_status
from .account_summary import fetch_account_summary
from .artifact_db import ARTIFACT_DB_PATH, connect_db
from .artifact_importer import unwrap_hoyolab_payload
from .account_storage import (
    sync_account_storage_from_local_files,
    cache_account_side_icon, _download_url_to_file,
)
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
from .asset_layers import cleanup_unused_v2_assets, prepare_layered_assets, _image_is_usable, _run_asset_thread
from .display_stat_effects import (
    rebuild_artifact_set_display_stat_effects,
    rebuild_weapon_passive_tooltips,
    rebuild_weapon_display_stat_effects,
    weapon_entry_page_id_to_weapon_id_map,
)
from .hoyowiki_catalog_refresh import refresh_weapon_stats_catalog_entries
from .import_static_cache import ImportArtifactSetLists
from .import_progress import ImportProgress, JOB_PHASES
from .import_store import (
    prepare_import_store, stage_import_attempt, commit_import_snapshot,
    get_import_attempt, get_import_result, latest_committed_import,
    update_import_enrichment, refresh_import_references,
    adopt_legacy_account_binding, ImportStoreError, read_equipment_revision,
    get_active_account_binding, AccountBindingMismatch,
)
from .hoyolab_exporter import HOYOLAB_URL, HoyolabExporter, close_export_context
from .paths import (
    HOYOLAB_ASSETS_DIR,
    HOYOLAB_DATA_DIR,
    HOYOLAB_DEBUG_DIR,
    HOYOLAB_PROFILE_DIR,
    PROJECT_ROOT,
    ensure_hoyolab_dirs,
)
from run_workspace.profile_context import ACCOUNT_ROOT, PROFILE_ID, account_asset_path


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


def _publish_staged_images(staging_root: Path) -> list[dict[str, str]]:
    errors = []
    for staged_path in staging_root.rglob("*.png"):
        try:
            final_path = (ACCOUNT_ROOT / staged_path.relative_to(staging_root)).resolve()
            if not final_path.is_relative_to(ACCOUNT_ROOT.resolve()):
                raise ValueError("asset path escaped account root")
            final_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.replace(final_path)
        except OSError as exc:
            errors.append({"kind": "publication", "key": staged_path.name, "reason": type(exc).__name__})
        except (RuntimeError, ValueError) as exc:
            errors.append({"kind": "publication", "key": staged_path.name, "reason": type(exc).__name__})
    return errors


def _sync_image_paths_only(manifest: dict[str, Any]) -> None:
    """Update only existing account image columns after an image-only refresh."""
    with closing(connect_db(ARTIFACT_DB_PATH)) as conn, conn:
        required = {"account_characters", "account_weapon_observed_stacks"}
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not required <= tables:
            raise HoYoLABImportError("Import account data once before refreshing only images.")
        for asset in manifest.get("characterAssets") or []:
            path = asset.get("crop") or asset.get("portrait")
            if not path:
                continue
            conn.execute(
                "UPDATE account_characters SET portrait_path = ? WHERE character_id = ?",
                (path, int(asset["character"]["id"])),
            )
        by_icon = {icon_key(asset["weapon"].get("icon")): asset.get("crop") or asset.get("icon")
                   for asset in manifest.get("weaponAssets") or []}
        by_id = {int(asset["weapon"]["id"]): asset.get("crop") or asset.get("icon")
                 for asset in manifest.get("weaponAssets") or []}
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
    """Legacy local-file adapter retained for explicit maintenance callers.

    Normal import uses commit_import_snapshot and never calls this adapter;
    its source/receipt transaction must not depend on JSON projections.
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
    progress_callback=None,
) -> tuple[dict[str, Any], str | None]:
    """Best-effort HoYoWiki static catalog refresh used by normal import."""

    summary: dict[str, Any] = {}
    errors: list[str] = []

    def refresh_sets():
        try:
            summary["artifactSetCatalog"] = ensure_artifact_set_catalog(
                db_path=ARTIFACT_DB_PATH,
                allow_network=True,
                missing_only=True,
                list_fetcher=artifact_set_list_fetcher,
            )
        except Exception as exc:
            errors.append(f"artifact set catalog: {compact_exception_summary(exc)}")

    def refresh_traits():
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

    def refresh_regions():
        try:
            if content_language:
                region_entries = load_character_region_catalog(content_language, allow_network=True)
                summary["characterRegionCatalog"] = {
                    "language": content_language,
                    "entries": len(region_entries),
                }
        except Exception as exc:
            errors.append(f"character region catalog: {compact_exception_summary(exc)}")

    def refresh_weapons():
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

    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="import-catalog") as pool:
        futures = [pool.submit(operation) for operation in
                   (refresh_sets, refresh_traits, refresh_regions, refresh_weapons)]
        for completed, future in enumerate(as_completed(futures), 1):
            future.result()
            if progress_callback:
                progress_callback("catalogs", completed, len(futures))
    return summary, "; ".join(errors) if errors else None


def refresh_abyss_source_data_for_import(
    period: HoYoLABAbyssPeriod | None,
    *,
    floor: int = 12,
    status_callback=print_status,
    refresher=refresh_cached_abyss_source_data_for_hoyolab_period,
    progress_callback=None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Best-effort Abyss source refresh used by the normal HoYoLAB import."""

    if period is None:
        return None, "official_abyss_period_unavailable"
    if status_callback is not None:
        status_callback("updating_abyss_source_data")
    progress_args = {"progress_callback": progress_callback} if progress_callback else {}
    summary, error = refresher(period, floor=floor, **progress_args)
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
    content_language, *, english_details=None,
):
    """Keep reference-data failures separate from the account payload import."""
    try:
        summary = await ensure_hoyolab_set_mapping(
            character_details, export_page, real_ids, db_path=ARTIFACT_DB_PATH,
            allow_unmapped=True, english_details=english_details,
        )
        if summary.get("unmapped") and "fresh_cache" in artifact_set_lists.sources.values():
            fresh_lists = ImportArtifactSetLists(force_network=True)
            refreshed = {}
            refreshed["catalog"] = await asyncio.to_thread(ensure_artifact_set_catalog,
                db_path=ARTIFACT_DB_PATH, allow_network=True, missing_only=True,
                list_fetcher=fresh_lists,
            )
            refreshed["names"] = await asyncio.to_thread(ensure_artifact_set_names,
                content_language, db_path=ARTIFACT_DB_PATH, list_fetcher=fresh_lists,
            )
            refreshed["bonuses"] = await asyncio.to_thread(ensure_artifact_set_bonus_descriptions,
                content_language, db_path=ARTIFACT_DB_PATH, list_fetcher=fresh_lists,
            )
            # Successful identity mapping does not imply every reference field
            # was loaded. Keep incomplete forced refreshes eligible for repair.
            refreshed["errors"] = [
                name for name, value in refreshed.items()
                if isinstance(value, dict) and (value.get("error") or value.get("errors") or value.get("failed"))
            ]
            static_catalog_summary["mappingRefresh"] = refreshed
            static_catalog_summary["artifactSetListSources"].update(fresh_lists.sources)
            static_catalog_summary["artifactSetListRefreshedForUnknownMapping"] = True
            summary = await ensure_hoyolab_set_mapping(
                character_details, export_page, real_ids, db_path=ARTIFACT_DB_PATH,
                allow_unmapped=True, english_details=english_details,
            )
        return summary
    except Exception as exc:
        # Source artifacts already exist; this only postpones canonical enrichment.
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


def cleanup_import_staging(*, now: float | None = None) -> list[str]:
    """Retire only abandoned, importer-owned staging after one day."""
    root = HOYOLAB_DEBUG_DIR.resolve()
    if (root != HOYOLAB_DEBUG_DIR.absolute()
            or not root.is_relative_to(PROJECT_ROOT.resolve())):
        return ["unsafe_staging_root"]
    failures = []
    for path in root.glob("import-assets-*"):
        try:
            target = path.resolve()
            if path.is_symlink() or target != path.absolute() or target.parent != root or not target.is_dir():
                continue
            if (now if now is not None else time.time()) - path.stat().st_mtime < 86400:
                continue
            shutil.rmtree(target)
        except OSError:
            failures.append(path.name)
    return failures


def _safe_detail_source(details: dict[str, Any]) -> dict[str, Any]:
    """Persist source data and useful metadata, never HTTP/session diagnostics."""
    payload = unwrap_hoyolab_payload(details)
    return {
        "json": payload,
        **{key: details[key] for key in (
            "detectedLanguage", "charactersRequested", "charactersReturned", "capturedAt",
        ) if key in details},
    }


def _current_attempt(attempt_id: str) -> dict[str, Any]:
    current = latest_committed_import(ARTIFACT_DB_PATH)
    if current is None or current["attempt_id"] != attempt_id:
        raise ImportStoreError("Only the current account snapshot can publish derived data")
    return current


def publish_import_projections(attempt_id: str) -> dict[str, Any]:
    """Legacy JSON is a rebuildable projection of the committed SQLite source."""
    current = _current_attempt(attempt_id)
    source = current["source"]
    for filename, key in (
        ("account_characters.json", "account_characters"),
        ("account_weapons.json", "account_weapons"),
        ("account_character_details.json", "account_character_details"),
    ):
        write_json(HOYOLAB_DATA_DIR / filename, source[key])
    write_json(HOYOLAB_DATA_DIR / "account_language.json", {
        "contentLanguage": source["content_language"],
        "accountUid": current["account_uid"], "server": current["server"],
        "attemptId": attempt_id, "observedAt": current["observed_at"],
        "source": "committed_hoyolab_snapshot",
    })
    return {"files": 4}


def _asset_local_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        path = account_asset_path(value).resolve()
        if not path.is_relative_to(ACCOUNT_ROOT.resolve()):
            return None
        return path
    except (OSError, RuntimeError, ValueError):
        return None


def _usable_asset_path(value: Any) -> bool:
    path = _asset_local_path(value)
    return path is not None and _image_is_usable(path)


def _merge_asset_manifests(previous: dict[str, Any], fresh: dict[str, Any]) -> dict[str, Any]:
    """Keep valid prior images when a single refresh/publication failed."""
    result = dict(fresh)
    checked = {}
    def usable(value):
        if not isinstance(value, str):
            return False
        if value not in checked:
            checked[value] = _usable_asset_path(value)
        return checked[value]
    for group, identity in (("characterAssets", "character"), ("weaponAssets", "weapon")):
        def key(asset):
            entity = asset.get(identity) or {}
            return (entity.get("id"), icon_key(entity.get("icon")) if identity == "weapon" else "")
        old = {key(asset): asset for asset in previous.get(group) or []}
        merged = []
        for asset in fresh.get(group) or []:
            fallback = old.pop(key(asset), {})
            merged.append({
                **asset,
                **{field: (asset.get(field) if usable(asset.get(field))
                           else fallback.get(field) if usable(fallback.get(field)) else "")
                   for field in ("crop", "pvp", "history", "portrait", "icon")
                   if field in asset or field in fallback},
            })
        # HoYoLAB observations are not a complete inventory.
        merged.extend(old.values())
        result[group] = merged
    shared = {}
    old_shared = previous.get("sharedAssets") or {}
    for group in set(old_shared) | set(fresh.get("sharedAssets") or {}):
        values = dict(old_shared.get(group) or {})
        values.update({k: v for k, v in (fresh.get("sharedAssets", {}).get(group) or {}).items()
                       if usable(v)})
        shared[group] = {k: v for k, v in values.items() if usable(v)}
    result["sharedAssets"] = shared
    return result


async def refresh_import_assets(
    characters, weapons, *, cards=(), refresh_images=False, attempt_id=None,
    progress_callback=None,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="import-assets-", dir=HOYOLAB_DEBUG_DIR) as staging:
        manifest = await prepare_layered_assets(
            characters=characters, weapons=weapons, cards=list(cards),
            staging_root=Path(staging), refresh_images=refresh_images,
            **({"progress_callback": progress_callback} if progress_callback else {}),
        )
        if not manifest.get("cardsCount"):
            raise HoYoLABImportError("Image preparation produced no characters")
        # Validation/publication includes PNG decoding and filesystem work.
        # Drain the worker before deleting staging even on cancellation.
        if progress_callback:
            progress_callback("saving", 0, 1)
        result = await _run_asset_thread(_publish_import_assets, manifest, Path(staging), attempt_id)
        if progress_callback:
            progress_callback("saving", 1, 1)
        return result


def _publish_import_assets(manifest, staging, attempt_id):
    started = time.perf_counter()
    errors = _publish_staged_images(staging)
    manifest.setdefault("assetErrors", []).extend(errors)
    manifest["assetsPending"] = int(manifest.get("assetsPending") or 0) + len(errors)
    path = HOYOLAB_DATA_DIR / "crop_manifest.json"
    previous = read_json_or_none(path) or {}
    if attempt_id:
        current = _current_attempt(attempt_id)
        saved = (current["enrichment"].get("assets") or {}).get("result") or {}
        previous = saved.get("manifest") or previous
    manifest = _merge_asset_manifests(previous, manifest)
    manifest.setdefault("assetTimings", {})["validationAndReplaceSeconds"] = round(time.perf_counter() - started, 3)
    # Persist before the replaceable projection, so a crash can be repaired
    # without downloading images again.
    if attempt_id:
        update_import_enrichment(
            ARTIFACT_DB_PATH, attempt_id=attempt_id, kind="assets", status="pending",
            result={"manifest": manifest},
        )
    _sync_image_paths_only(manifest)
    write_json(path, manifest)
    cleanup_failures = cleanup_unused_v2_assets(manifest)
    if cleanup_failures:
        manifest["cleanupPending"] = len(cleanup_failures)
    return {"manifest": manifest, "pending": bool(manifest.get("assetsPending") or cleanup_failures)}


def _profile_registry_entry() -> dict[str, Any] | None:
    if not PROFILE_ID:
        return None
    from run_workspace.account_profiles import list_profiles

    return next((item for item in list_profiles() if item.get("id") == PROFILE_ID), None)


def _profile_identity_metadata(account_context: dict[str, Any]) -> dict[str, Any]:
    return {
        "uid": str(account_context["role_id"]),
        "server": str(account_context["server"]),
    }


def _profile_summary_metadata(
    account_context: dict[str, Any], summary: dict[str, Any] | None,
) -> dict[str, Any]:
    metadata = _profile_identity_metadata(account_context)
    if not isinstance(summary, dict):
        return metadata
    if (str(summary.get("uid") or "") != metadata["uid"]
            or str(summary.get("server") or "") != metadata["server"]):
        return metadata
    for key in ("nickname", "world_level", "adventure_rank", "avatar_url"):
        value = summary.get(key)
        if value is not None:
            metadata[key] = value
    return metadata


def _reserve_profile_identity(account_context: dict[str, Any]) -> None:
    """Bind a managed profile before any account source is staged."""
    if not PROFILE_ID:
        return
    from run_workspace.account_profiles import (
        DuplicateAccountProfile, list_profiles, update_profile_metadata,
    )

    entry = next((item for item in list_profiles() if item.get("id") == PROFILE_ID), None)
    if entry is None:
        raise HoYoLABImportError("The selected local account profile is unavailable.")
    current = entry.get("metadata") or {}
    requested = _profile_identity_metadata(account_context)
    current_uid = str(current.get("uid") or "")
    current_server = str(current.get("server") or "")
    if ((current_uid and current_uid != requested["uid"])
            or (current_server and current_server.casefold() != requested["server"].casefold())):
        raise HoYoLABImportError("The selected HoYoLAB role differs from this profile's reserved identity.")
    options = {} if entry.get("imported") else {"imported": False}
    try:
        update_profile_metadata(PROFILE_ID, requested, **options)
    except DuplicateAccountProfile as exc:
        print("[PROFILE_DUPLICATE] " + json.dumps(
            {"existing_profile_id": exc.existing_profile_id}, ensure_ascii=False,
        ), flush=True)
        raise


def _update_profile_imported_metadata(
    account_context: dict[str, Any], summary: dict[str, Any] | None = None,
    *, avatar_path: str | None = None,
) -> dict[str, Any] | None:
    if not PROFILE_ID:
        return None
    from run_workspace.account_profiles import update_profile_metadata

    metadata = _profile_summary_metadata(account_context, summary)
    if avatar_path:
        metadata["avatar_path"] = avatar_path
    return update_profile_metadata(PROFILE_ID, metadata, imported=True)


def _profile_avatar_url_is_safe(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
    except ValueError:
        return False
    return bool(
        parts.scheme == "https" and host
        and not parts.username and not parts.password
        and any(host == domain or host.endswith(f".{domain}")
                for domain in ("hoyolab.com", "hoyoverse.com", "mihoyo.com"))
    )


def _cache_profile_avatar_sync(avatar_url: str, *, force: bool = False) -> str:
    """Download to a private candidate, decode/validate, then atomically publish."""
    if not _profile_avatar_url_is_safe(avatar_url):
        raise ValueError("profile avatar URL is not an allowed HoYoLAB image")
    destination = ACCOUNT_ROOT / "assets" / "hoyolab" / "account" / "avatar.png"
    account_root = ACCOUNT_ROOT.resolve()
    try:
        if not destination.parent.resolve().is_relative_to(account_root):
            raise ValueError("profile avatar path escaped account root")
        if (destination.exists() or destination.is_symlink()) \
                and not destination.resolve().is_relative_to(account_root):
            raise ValueError("profile avatar path escaped account root")
    except RuntimeError as exc:
        raise ValueError("profile avatar path could not be resolved") from exc
    if not force and _image_is_usable(destination):
        return "assets/hoyolab/account/avatar.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.parent.resolve().is_relative_to(account_root):
        raise ValueError("profile avatar path escaped account root")
    candidate = destination.with_name(f".avatar-{uuid.uuid4().hex}.png")
    temporary = candidate.with_suffix(candidate.suffix + ".tmp")
    try:
        _download_url_to_file(avatar_url, candidate)
        if not _image_is_usable(candidate):
            raise ValueError("profile avatar image failed validation")
        candidate.replace(destination)
        return "assets/hoyolab/account/avatar.png"
    finally:
        candidate.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)


async def _refresh_profile_metadata(
    account_context: dict[str, Any], summary_task: asyncio.Task | None,
    *, previous_avatar_url: str | None = None,
    previous_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not PROFILE_ID:
        return {"pending": False}
    summary = None
    summary_error = None
    if summary_task is not None:
        try:
            summary = await summary_task
        except Exception as exc:
            summary_error = type(exc).__name__
    previous = _profile_registry_entry() or {}
    previous_metadata = previous.get("metadata") or {}
    if previous_avatar_url is None:
        previous_avatar_url = previous_metadata.get("avatar_url")
    if not summary:
        summary = None
    requested_avatar_url = (
        summary.get("avatar_url") if isinstance(summary, dict) else None
    )
    avatar_url = requested_avatar_url or previous_metadata.get("avatar_url")
    try:
        _update_profile_imported_metadata(account_context, summary)
    except Exception as exc:
        return {"pending": True, "error": type(exc).__name__,
                "summaryError": summary_error}

    avatar_path = None
    avatar_cached = False
    avatar_error = None
    if avatar_url:
        try:
            avatar_path = await _run_asset_thread(
                _cache_profile_avatar_sync, avatar_url,
                force=bool(requested_avatar_url and requested_avatar_url != previous_avatar_url),
            )
            avatar_cached = bool(avatar_path)
            _update_profile_imported_metadata(account_context, summary, avatar_path=avatar_path)
        except Exception as exc:
            avatar_error = type(exc).__name__

    # Keep a small, portable projection for offline profile export. Paths are
    # account-relative and are included only while the decoded file is usable.
    entry = _profile_registry_entry() or {}
    metadata = dict(entry.get("metadata") or {})
    avatar_file = ACCOUNT_ROOT / "assets" / "hoyolab" / "account" / "avatar.png"
    if _image_is_usable(avatar_file):
        metadata["avatar_path"] = "assets/hoyolab/account/avatar.png"
    else:
        metadata.pop("avatar_path", None)
    projection = {
        key: metadata.get(key)
        for key in ("uid", "server", "nickname", "world_level", "adventure_rank", "avatar_url")
    }
    if metadata.get("avatar_path"):
        projection["avatar_path"] = metadata["avatar_path"]
    try:
        write_json(HOYOLAB_DATA_DIR / "account_summary.json", projection)
    except Exception as exc:
        return {"pending": True, "error": type(exc).__name__,
                "summaryError": summary_error, "avatarError": avatar_error}
    summary_available = bool(summary)
    pending_reason = None
    if summary_task is not None and summary_error:
        pending_reason = "network_profile_summary_unavailable"
    elif summary_task is None:
        prior_summary = previous_result or {}
        summary_available = bool(
            prior_summary.get("summaryAvailable")
            or any(previous_metadata.get(key) is not None
                   for key in ("nickname", "adventure_rank", "avatar_url"))
        )
        if prior_summary.get("pendingReason") == "network_profile_summary_unavailable":
            pending_reason = "network_profile_summary_unavailable"
        elif not summary_available:
            pending_reason = "profile_summary_unavailable"
    return {
        "pending": bool(avatar_error or pending_reason),
        "summaryAvailable": summary_available,
        "avatarCached": avatar_cached,
        **({"pendingReason": pending_reason} if pending_reason else {}),
        **({"summaryError": summary_error} if summary_error else {}),
        **({"avatarError": avatar_error} if avatar_error else {}),
    }


async def _close_context_after_sources(
    context: Any, *source_tasks: asyncio.Task | None,
) -> str | None:
    """Drain source requests before closing their shared browser context."""
    tasks = [task for task in source_tasks if task is not None]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    if context is None:
        return None
    try:
        await close_export_context(context)
    except Exception as exc:
        return type(exc).__name__
    return None


async def refresh_import_side_icons(
    *, progress_callback=None, extra_work=None,
) -> dict[str, Any]:
    with closing(connect_db(ARTIFACT_DB_PATH)) as conn:
        rows = [dict(row) for row in conn.execute(
            "SELECT character_id, side_icon_url FROM account_characters WHERE side_icon_url != ''"
        )]
    semaphore = asyncio.Semaphore(6)
    completed = 0
    total = len(rows) + (1 if extra_work is not None else 0)
    if progress_callback:
        progress_callback("download", completed, total)

    async def download(row):
        nonlocal completed
        async with semaphore:
            result = await asyncio.to_thread(
                cache_account_side_icon,
                character_id=row["character_id"], side_icon_url=row["side_icon_url"],
                cache_dir=HOYOLAB_ASSETS_DIR / "characters" / "side_icons",
                downloader=_download_url_to_file,
            )
            completed += 1
            if progress_callback:
                progress_callback("download", completed, total)
            return row, result

    async def run_extra_work():
        nonlocal completed
        try:
            result = await extra_work()
        except Exception as exc:
            result = {"pending": True, "error": type(exc).__name__}
        completed += 1
        if progress_callback:
            progress_callback("download", completed, total)
        return result

    tasks = [download(row) for row in rows]
    if extra_work is not None:
        tasks.append(run_extra_work())
    results = await asyncio.gather(*tasks)
    side_icon_results = results[:len(rows)]
    profile_result = results[-1] if extra_work is not None else None
    with closing(connect_db(ARTIFACT_DB_PATH)) as conn, conn:
        for row, result in side_icon_results:
            if result.path:
                conn.execute(
                    "UPDATE account_characters SET side_icon_path = ? "
                    "WHERE character_id = ? AND side_icon_url = ?",
                    (result.path, row["character_id"], row["side_icon_url"]),
                )
    return {
        "downloaded": sum(item.downloaded for _, item in side_icon_results),
        "pending": bool(sum(bool(item.warnings) for _, item in side_icon_results)
                         or (profile_result or {}).get("pending")),
        **({"profileMetadata": profile_result} if profile_result is not None else {}),
    }


async def refresh_import_catalogs(attempt_id, character_details, english_source_task, *, progress_callback=None):
    language = normalize_language(character_details.get("detectedLanguage"))
    lists = ImportArtifactSetLists()
    summary, error = await asyncio.to_thread(
        sync_static_reference_catalogs_for_import, language,
        weapon_wiki=_weapon_wiki_from_character_details(character_details),
        artifact_set_list_fetcher=lists,
        progress_callback=progress_callback,
    )
    summary["artifactSetListSources"] = dict(lists.sources)
    errors = [error] if error else []
    for name, updater in (("names", ensure_artifact_set_names),
                          ("bonuses", ensure_artifact_set_bonus_descriptions)):
        if progress_callback:
            progress_callback(name, 0, 1)
        try:
            summary[name] = await asyncio.to_thread(
                updater, language, db_path=ARTIFACT_DB_PATH, list_fetcher=lists,
            )
        except Exception as exc:
            errors.append(type(exc).__name__)
        if progress_callback:
            progress_callback(name, 1, 1)
    if progress_callback:
        progress_callback("mapping", 0, 1)
    english = await english_source_task
    mapping = await prepare_artifact_mapping_for_import(
        character_details, None, [], lists, summary, language, english_details=english,
    )
    if progress_callback:
        progress_callback("mapping", 1, 1)
    summary["mapping"] = mapping
    if mapping.get("error"):
        errors.append(mapping["error"])
    for name, value in summary.items():
        if isinstance(value, dict) and (value.get("error") or value.get("errors") or value.get("failed")):
            errors.append(name + "_incomplete")
    # Mapping updates the existing artifact IDs in place. No source reimport:
    # it must never restore old equipment or increment observed stack counts.
    if progress_callback:
        progress_callback("saving", 0, 1)
    summary["accountReferences"] = await asyncio.to_thread(
        refresh_import_references, ARTIFACT_DB_PATH, attempt_id=attempt_id,
    )
    with closing(connect_db(ARTIFACT_DB_PATH)) as conn, conn:
        from .artifact_db import backfill_artifact_content_fingerprints
        backfill_artifact_content_fingerprints(conn)
        summary["staticDisplayEffects"] = {
            "artifact_set_rows": rebuild_artifact_set_display_stat_effects(conn),
            "weapon_rows": rebuild_weapon_display_stat_effects(
                conn, weapon_wiki=_weapon_wiki_from_character_details(character_details),
            ),
        }
    summary["pending"] = bool(errors or mapping.get("unmapped"))
    summary["errors"] = errors
    return summary


def _needs_english_mapping(details: dict[str, Any]) -> bool:
    payload = unwrap_hoyolab_payload(details)
    source_ids = {
        int(relic["set"]["id"])
        for row in (payload.get("data") or {}).get("list") or []
        for relic in row.get("relics") or []
        if isinstance(relic.get("set"), dict) and relic["set"].get("id")
    }
    if not source_ids:
        return False
    with closing(connect_db(ARTIFACT_DB_PATH)) as conn:
        known = {int(row[0]) for row in conn.execute(
            "SELECT hoyolab_set_id FROM artifact_sets WHERE hoyolab_set_id IS NOT NULL"
        )}
    return bool(source_ids - known)


async def run_hoyolab_import(
    *, change_equipment: bool = False, images_only: bool = False,
    attempt_id: str | None = None, resume_attempt: str | None = None,
    adopt_legacy: bool = False,
) -> dict[str, Any]:
    """Acquire -> durable source -> one core transaction -> independent jobs."""
    started = time.monotonic()
    current_stage = "preparing"
    stage_events, browser_events = [], []
    context = export_page = character_list_future = profile_summary_task = None
    receipt = None
    result = None
    attempt_id = resume_attempt or attempt_id or str(uuid.uuid4())
    progress = ImportProgress(None if images_only else attempt_id, images_only=images_only)
    cards = []
    jobs = []
    record_errors = []
    profile_metadata_needs_retry = False
    profile_previous_avatar_url = None
    equipment_revision = read_equipment_revision(ARTIFACT_DB_PATH) if change_equipment else None

    def report_status(status):
        nonlocal current_stage
        current_stage = status
        stage_events.append({"stage": status, "elapsedSeconds": round(time.monotonic() - started, 3)})
        print_status(status)

    def browser_event(event):
        browser_events.append({"event": event, "stage": current_stage,
                               "elapsedSeconds": round(time.monotonic() - started, 3)})

    def record(kind, status, data):
        # Disk/SQLite errors after COMMIT must not change the core outcome.
        try:
            update_import_enrichment(
                ARTIFACT_DB_PATH, attempt_id=attempt_id, kind=kind, status=status, result=data,
            )
        except Exception as exc:
            record_errors.append({"kind": kind, "error": type(exc).__name__})

    async def run_job(kind, operation):
        record(kind, "pending", (saved_jobs.get(kind) or {}).get("result") or {})
        progress.update(kind, JOB_PHASES[kind][0])
        job_started = time.monotonic()
        try:
            data = await operation()
            data["durationSeconds"] = round(time.monotonic() - job_started, 3)
            record(kind, "pending" if data.get("pending") else "complete", data)
            progress.finish(kind, pending=bool(data.get("pending")))
            return data
        except Exception as exc:
            data = {"error": type(exc).__name__, "pending": True,
                    "durationSeconds": round(time.monotonic() - job_started, 3)}
            record(kind, "failed", data)
            progress.finish(kind, pending=True)
            return data

    async def open_browser():
        nonlocal context, export_page
        exporter = HoyolabExporter(
            profile_dir=HOYOLAB_PROFILE_DIR, download_dir=HOYOLAB_DEBUG_DIR, scale=1,
        )
        context = await exporter._create_context()
        export_page = await get_export_page(context)
        export_page.on("close", lambda *_: browser_event("page_closed"))
        export_page.on("crash", lambda *_: browser_event("page_crashed"))
        if context.browser is not None:
            context.browser.on("disconnected", lambda *_: browser_event("browser_disconnected"))
        return exporter

    report_status("preparing")
    ensure_hoyolab_dirs()
    cleanup_import_staging()
    try:
        if images_only:
            # Reuse this database's own source; a different logged-in role must
            # never overwrite its image paths.
            try:
                saved = latest_committed_import(ARTIFACT_DB_PATH)
            except Exception:
                saved = None
            source = saved["source"] if saved else {
                "account_characters": read_json_or_none(HOYOLAB_DATA_DIR / "account_characters.json"),
                "account_weapons": read_json_or_none(HOYOLAB_DATA_DIR / "account_weapons.json"),
            }
            if not source["account_characters"]:
                raise HoYoLABImportError("Import account data once before refreshing only images.")
            report_status("downloading_assets")
            data = await refresh_import_assets(
                source["account_characters"], source["account_weapons"] or [], refresh_images=True,
                attempt_id=saved["attempt_id"] if saved else None,
                progress_callback=progress.callback("assets"),
            )
            if saved:
                update_import_enrichment(
                    ARTIFACT_DB_PATH, attempt_id=saved["attempt_id"], kind="assets",
                    status="pending" if data.get("pending") else "complete", result=data,
                )
            result = {"imagesOnly": True, **data,
                      "warnings": [{"code": "images_pending"}] if data.get("pending") else []}
            progress.finish("assets", pending=bool(data.get("pending")))
            return result

        if resume_attempt:
            saved = get_import_attempt(ARTIFACT_DB_PATH, resume_attempt)
            if saved is None:
                raise HoYoLABImportError("Saved import attempt was not found.")
            source = saved["source"]
            characters, weapons = source["account_characters"], source["account_weapons"]
            character_details = source["account_character_details"]
            account_context = {"role_id": saved["account_uid"], "server": saved["server"]}
            _reserve_profile_identity(account_context)
            if adopt_legacy:
                adopt_legacy_account_binding(
                    ARTIFACT_DB_PATH, account_uid=saved["account_uid"], server=saved["server"], verified=True,
                )
            if saved["status"] == "committed":
                _current_attempt(attempt_id)
        else:
            if adopt_legacy:
                raise HoYoLABImportError("Legacy account confirmation requires a saved attempt.")
            if get_auth_status(HOYOLAB_PROFILE_DIR) != AuthStatus.LOGGED_IN:
                raise HoYoLABImportError("HoYoLAB profile is not logged in. Authorize in the app first.")
            exporter = await open_browser()
            character_list_request = {}
            character_list_future = await wait_for_character_list_response(
                export_page, request_context=character_list_request,
            )
            report_status("opening_hoyolab")
            await export_page.goto(HOYOLAB_URL, wait_until="domcontentloaded", timeout=60_000)
            report_status("opening_character_list")
            direct = await fetch_character_list_direct(export_page)
            if direct is not None:
                character_list, account_context = direct
                character_list_future.cancel()
            else:
                await exporter._wait_until_ready_or_login(export_page)
                await exporter._click_with_popup_retry(export_page, ".block-title-right")
                await export_page.locator(".me-share__btn").first.wait_for(state="visible", timeout=30_000)
                character_list = await asyncio.wait_for(character_list_future, timeout=60)
                account_context = dict(character_list_request)
                # DOM image metadata is optional and never blocks source capture.
            if not account_context.get("role_id") or not account_context.get("server"):
                raise HoYoLABImportError("Could not verify the selected account/server. Select it in HoYoLAB and retry.")
            account_context = {key: str(account_context[key]) for key in ("role_id", "server")}
            binding = get_active_account_binding(ARTIFACT_DB_PATH)
            if binding and (binding["account_uid"], binding["server"]) != (
                    account_context["role_id"], account_context["server"]):
                raise AccountBindingMismatch("The selected HoYoLAB role differs from this local account.")
            report_status("collecting_inventory")
            characters, weapons = build_inventory(character_list)
            if not characters:
                raise HoYoLABImportError("HoYoLAB inventory produced no characters.")
            _reserve_profile_identity(account_context)
            if PROFILE_ID:
                profile_summary_task = asyncio.create_task(fetch_account_summary(
                    export_page, dict(account_context), fast_context_request_fetch_json,
                ))
            report_status("fetching_character_details")
            ids = real_character_ids(characters)
            try:
                character_details = await fetch_character_details_batch(
                    export_page, ids, json_fetcher=fast_context_request_fetch_json, **account_context,
                )
            except Exception:
                character_details = await fetch_character_details_batch(export_page, ids, **account_context)
            character_details = _safe_detail_source(character_details)
            # All optional catalogs/network are deliberately outside this transaction.
            prepare_import_store(ARTIFACT_DB_PATH)
            stage_import_attempt(
                ARTIFACT_DB_PATH, account_uid=account_context["role_id"], server=account_context["server"],
                account_characters=characters, account_weapons=weapons,
                account_character_details=character_details,
                content_language=normalize_language(character_details.get("detectedLanguage")),
                change_equipment=change_equipment, attempt_id=attempt_id,
                expected_equipment_revision=equipment_revision,
            )

        report_status("saving_account")
        receipt = await asyncio.to_thread(
            commit_import_snapshot, ARTIFACT_DB_PATH, attempt_id=attempt_id,
            side_icon_cache_dir=HOYOLAB_ASSETS_DIR / "characters" / "side_icons",
        )
        if PROFILE_ID:
            try:
                profile_entry = _profile_registry_entry() or {}
                profile_previous_avatar_url = (profile_entry.get("metadata") or {}).get("avatar_url")
            except Exception:
                profile_previous_avatar_url = None
        finished_summary = None
        if profile_summary_task is not None and profile_summary_task.done():
            try:
                finished_summary = profile_summary_task.result()
            except Exception:
                pass
        if PROFILE_ID:
            try:
                _update_profile_imported_metadata(account_context, finished_summary)
            except Exception as exc:
                # The SQLite receipt is authoritative; the side-icon job retries
                # registry/profile projection work after the receipt is visible.
                profile_metadata_needs_retry = True
        print("[IMPORT_COMMITTED] " + json.dumps({"attempt_id": attempt_id}, ensure_ascii=False), flush=True)
        report_status("enriching_account")
        saved = get_import_attempt(ARTIFACT_DB_PATH, attempt_id)
        saved_jobs = saved["enrichment"]

        async def recovery_browser():
            if (not resume_attempt or (saved_jobs.get("references") or {}).get("status") == "complete"
                    or normalize_language(character_details.get("detectedLanguage")) == "en-us"
                    or (saved_jobs.get("mapping_source") or {}).get("result", {}).get("details")
                    or not _needs_english_mapping(character_details)):
                return
            if get_auth_status(HOYOLAB_PROFILE_DIR) != AuthStatus.LOGGED_IN:
                return
            try:
                await open_browser()
                await export_page.goto(HOYOLAB_URL, wait_until="domcontentloaded", timeout=60_000)
            except Exception as exc:
                record("mapping_source", "failed", {"error": type(exc).__name__})

        recovery_browser_task = asyncio.create_task(recovery_browser())

        async def english_source():
            known = (saved_jobs.get("mapping_source") or {}).get("result", {}).get("details")
            if known:
                return known
            language = character_details.get("detectedLanguage")
            if language and normalize_language(language) == "en-us":
                return character_details
            if not _needs_english_mapping(character_details):
                return None
            await recovery_browser_task
            if export_page is None:
                return None
            try:
                try:
                    response = await fetch_character_details_batch(
                        export_page, real_character_ids(characters), language="en-us",
                        json_fetcher=fast_context_request_fetch_json, **account_context,
                    )
                except Exception:
                    response = await fetch_character_details_batch(
                        export_page, real_character_ids(characters), language="en-us", **account_context,
                    )
                english = _safe_detail_source(response)
                record("mapping_source", "complete", {"details": english})
                return english
            except Exception as exc:
                record("mapping_source", "failed", {"error": type(exc).__name__})
                return None

        async def abyss_period_source():
            data = (saved_jobs.get("abyss_period") or {}).get("result", {}).get("period")
            if data:
                return HoYoLABAbyssPeriod(
                    raw_period=data["rawPeriod"], start_date=data["startDate"], end_date=data["endDate"],
                    source_path=data.get("sourcePath", ""), source=data.get("source", ""),
                )
            try:
                await recovery_browser_task
                period = await resolve_abyss_period_with_fallbacks(
                    export_page, language=normalize_language(character_details.get("detectedLanguage")),
                    **account_context,
                )
                record("abyss_period", "complete", {"period": period.to_dict()})
                return period
            except Exception as exc:
                record("abyss_period", "failed", {"error": type(exc).__name__})
                return None

        english_task = asyncio.create_task(english_source())
        period_task = asyncio.create_task(abyss_period_source())

        async def close_browser_when_sources_ready():
            nonlocal context
            cleanup_error = await _close_context_after_sources(
                context, english_task, period_task, profile_summary_task,
            )
            context = None
            if cleanup_error:
                record_errors.append({"kind": "browser_cleanup", "error": cleanup_error})

        async def projections():
            return await asyncio.to_thread(publish_import_projections, attempt_id)

        async def assets():
            return await refresh_import_assets(
                characters, weapons, cards=cards, attempt_id=attempt_id,
                progress_callback=progress.callback("assets"),
            )

        async def references():
            return await refresh_import_catalogs(
                attempt_id, character_details, english_task,
                progress_callback=progress.callback("references"),
            )

        async def side_icons():
            extra_work = None
            if PROFILE_ID:
                prior_side_icons = saved_jobs.get("side_icons") or {}
                previous_profile_result = (
                    (prior_side_icons.get("result") or {}).get("profileMetadata")
                )
                async def extra_work():
                    return await _refresh_profile_metadata(
                        account_context, profile_summary_task,
                        previous_avatar_url=profile_previous_avatar_url,
                        previous_result=previous_profile_result,
                    )
            return await refresh_import_side_icons(
                progress_callback=progress.callback("side_icons"), extra_work=extra_work,
            )

        async def abyss():
            period = await period_task
            if period is None:
                return {"pending": True, "reason": "period_unavailable"}
            progress.update("abyss", "period", 1, 1)
            write_hoyolab_abyss_period(period, period_path=DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH)
            data, error = await asyncio.to_thread(
                refresh_abyss_source_data_for_import, period, floor=12, status_callback=None,
                progress_callback=progress.callback("abyss"),
            )
            return {"summary": data, "pending": bool(error), "error": error}

        operations = {"projections": projections, "assets": assets, "references": references,
                      "side_icons": side_icons, "abyss": abyss}
        # Resuming a receipt only repairs unfinished jobs. It never reapplies gear.
        for kind, operation in operations.items():
            previous = saved_jobs.get(kind) or {}
            if resume_attempt and previous.get("status") == "complete":
                profile_metadata_saved = bool(
                    (previous.get("result") or {}).get("profileMetadata")
                )
                if (kind != "side_icons" or not PROFILE_ID
                        or (profile_metadata_saved and not profile_metadata_needs_retry)):
                    progress.finish(kind)
                    continue
            jobs.append(asyncio.create_task(run_job(kind, operation)))
        jobs.append(asyncio.create_task(close_browser_when_sources_ready()))
        await asyncio.gather(*jobs)
        current = get_import_attempt(ARTIFACT_DB_PATH, attempt_id)
        enrichment = current["enrichment"]
        pending = [key for key in operations if (enrichment.get(key) or {}).get("status") != "complete"]
        manifest = (enrichment.get("assets") or {}).get("result", {}).get("manifest") or {}
        result = {
            "attemptId": attempt_id, "status": "committed", "receipt": receipt,
            "artifactSummary": receipt["artifacts"], "accountStorageSummary": receipt["account_storage"],
            "equipmentApplied": receipt["equipment"], "enrichment": enrichment, "pendingJobs": pending,
            "manifest": manifest, "manifestPath": HOYOLAB_DATA_DIR / "crop_manifest.json",
            "characterDetailsPath": HOYOLAB_DATA_DIR / "account_character_details.json",
            # An unknown reference is a normal readiness state, never a skipped
            # artifact warning or an account-import failure.
            "warnings": [{"code": "enrichment_pending"}] if record_errors else [],
        }
        if receipt["equipment"].get("reason") in {"stale_equipment_revision", "revision_unavailable"}:
            result["warnings"].append({"code": "equipment_not_applied"})
        try:
            write_json(HOYOLAB_DEBUG_DIR / "import_log.json", {
                "attemptId": attempt_id, "status": "committed",
                "durationSeconds": round(time.monotonic() - started, 3),
                "stageEvents": stage_events, "browserLifecycle": browser_events,
                "pendingJobs": pending, "recordErrors": record_errors,
            })
        except OSError:
            pass
        report_status("done")
        return result
    except Exception as exc:
        # The durable receipt is authoritative even if a process/log/cache fails
        # immediately after COMMIT. A UI also checks this receipt on process exit.
        try:
            receipt = receipt or get_import_result(ARTIFACT_DB_PATH, attempt_id)
        except Exception:
            pass
        if receipt:
            return {"attemptId": attempt_id, "status": "committed", "receipt": receipt,
                    "artifactSummary": receipt["artifacts"], "accountStorageSummary": receipt["account_storage"],
                    "equipmentApplied": receipt["equipment"],
                    "warnings": [{"code": "enrichment_pending"}]}
        try:
            write_json(HOYOLAB_DEBUG_DIR / "import_failure.json", {
                "attemptId": attempt_id, "stage": current_stage, "errorType": type(exc).__name__,
                "pageClosed": bool(export_page.is_closed()) if export_page is not None else None,
                "browserEvents": browser_events,
            })
        except Exception:
            pass
        raise
    finally:
        # Never remove staging while a background thread is still publishing it.
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
        if profile_summary_task is not None:
            if not profile_summary_task.done():
                profile_summary_task.cancel()
            await asyncio.gather(profile_summary_task, return_exceptions=True)
        if character_list_future is not None:
            if not character_list_future.done():
                character_list_future.cancel()
            elif not character_list_future.cancelled():
                character_list_future.exception()
        if context is not None:
            try:
                await close_export_context(context)
            except Exception as exc:
                print(f"[HoYoLAB Import] Browser cleanup pending: {type(exc).__name__}", flush=True)
