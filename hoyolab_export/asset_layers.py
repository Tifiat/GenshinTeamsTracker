"""Download unique HoYoLAB card layers and render local display variants.

The inventory API owns portrait/weapon URLs. The live card DOM only supplies
the small shared element and rarity layer URLs; no browser-rendered bitmap is
used as an image source. Versioned output names avoid stale Qt pixmap caches.
"""

from __future__ import annotations

import asyncio
import hashlib
import http.client
import io
import socket
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont

from .crop_manifest import IGNORED_CHARACTER_IDS, IGNORED_WEAPON_RARITIES, character_asset_key, icon_key
from .paths import HOYOLAB_CHARACTER_ASSETS_DIR, HOYOLAB_WEAPON_ASSETS_DIR, HOYOLAB_SHARED_ASSETS_DIR, PROJECT_ROOT
from .paths import ACCOUNT_ROOT


SHARED_ASSETS_DIR = HOYOLAB_SHARED_ASSETS_DIR
RENDER_VERSION = "v2"
ELEMENTS = {"pyro", "hydro", "electro", "cryo", "anemo", "geo", "dendro"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 4_000_000
MAX_ASSET_WORKERS = 8
MAX_DOWNLOAD_ATTEMPTS = 3


async def _drain_thread_task(task: asyncio.Task) -> None:
    """Wait for a started to_thread call despite repeated caller cancellation."""
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            # The outer import can be cancelled more than once while an OS
            # worker is writing into its staging directory.
            if task.done():
                break
        except BaseException:
            break
    if not task.cancelled():
        try:
            task.result()
        except BaseException:
            pass


async def _gather_asset_tasks(awaitables):
    """Drain other writers before propagating cancellation or a job failure."""
    tasks = [asyncio.create_task(awaitable) for awaitable in awaitables]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        drain = asyncio.gather(*tasks, return_exceptions=True)
        while not drain.done():
            try:
                await asyncio.shield(drain)
            except asyncio.CancelledError:
                # Keep draining even if shutdown requests cancellation again.
                for task in tasks:
                    if not task.done():
                        task.cancel()
        drain.result()
        raise


async def _run_asset_thread(function: Callable[..., object], *args, **kwargs):
    """Run blocking asset work, draining started threads before cancellation.

    Cancelling an asyncio task awaiting ``to_thread`` does not stop its OS
    thread. The gate distinguishes an active writer from executor-queued work:
    active work is awaited to completion, while queued work is cancelled. A
    thread that races with queue cancellation observes the gate and skips the
    writer entirely.
    """
    gate = threading.Lock()
    started = False
    cancelled_before_start = False

    def invoke():
        nonlocal started
        with gate:
            if cancelled_before_start:
                return None
            started = True
        return function(*args, **kwargs)

    worker_task = asyncio.create_task(asyncio.to_thread(invoke))
    try:
        return await asyncio.shield(worker_task)
    except asyncio.CancelledError:
        with gate:
            worker_started = started
            if not worker_started:
                cancelled_before_start = True
        if worker_started:
            await _drain_thread_task(worker_task)
        else:
            worker_task.cancel()
        raise

# Public frontend assets observed in HoYoLAB's saved export layout on
# 2026-09-26. The character/list API does not include these shared layers and
# the share-card DOM is absent until the expensive full-image export starts.
# Live card URLs, when available, supersede these defaults below.
_STATIC_BASE = "https://act.hoyolab.com/app/community-game-records-sea/images/"
STATIC_ELEMENTS = {
    "pyro": _STATIC_BASE + "UI_Buff_Element_Fire.065c510d.png",
    "hydro": _STATIC_BASE + "UI_Buff_Element_Water.5b620394.png",
    "electro": _STATIC_BASE + "UI_Buff_Element_Elect.4c08c57a.png",
    "cryo": _STATIC_BASE + "UI_Buff_Element_Frost.95c777ac.png",
    "anemo": _STATIC_BASE + "UI_Buff_Element_Wind.bf653cfd.png",
    "geo": _STATIC_BASE + "UI_Buff_Element_Roach.bb164efa.png",
    "dendro": _STATIC_BASE + "UI_Buff_Element_Grass.dd061cc0.png",
}
STATIC_RARITY_BACKGROUNDS = {
    1: _STATIC_BASE + "roleStarBg1.8c3ec3b6.png",
    2: _STATIC_BASE + "roleStarBg2.5da2d605.png",
    3: _STATIC_BASE + "roleStarBg3.251efcc0.png",
    4: _STATIC_BASE + "roleStarBg4.0b20569c.png",
    5: _STATIC_BASE + "roleStarBg5.30180c91.png",
}


async def capture_card_layer_sources(page) -> list[dict[str, str]]:
    """Read only image URLs and rarity classes from the live share cards."""
    cards = await page.evaluate(
        """() => [...document.querySelectorAll('.role-share')].map(card => {
          const cssUrl = el => {
            if (!el) return '';
            const value = getComputedStyle(el).backgroundImage;
            const match = value && value.match(/url\\([\"']?(https:\\/\\/[^\"')]+)/);
            return match ? match[1] : '';
          };
          const src = el => el ? (el.currentSrc || el.src || '') : '';
          const avatar = card.querySelector('.role-avatar');
          const weapon = card.querySelector('.role-weapon-info');
          const weaponImg = weapon && weapon.querySelector('img');
          return {
            portrait: src(card.querySelector('img.role-img')),
            element: src(card.querySelector('img.role-element')),
            characterBackground: cssUrl(avatar),
            weaponBackground: cssUrl(weaponImg),
            weapon: src(weaponImg),
            characterRarity: (String(card.className).match(/role-rarity-(\\d+)/) || [])[1] || '',
            weaponRarity: (String(weapon?.className || '').match(/weapon-rarity-(\\d+)/) || [])[1] || ''
          };
        })"""
    )
    return [dict(card) for card in cards if isinstance(card, dict)]


def _fingerprint(*parts: object) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:16]


def _relative(path: Path) -> str:
    return path.relative_to(ACCOUNT_ROOT).as_posix()


def _save_png_atomic(image: Image.Image, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".part")
    try:
        image.save(temporary, format="PNG")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _remove_staged(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # The caller will record the failed asset; staging cleanup is a final
        # safeguard for transient files that cannot be removed immediately.
        pass


def _image_is_usable(path: Path, *, require_transparency: bool = False) -> bool:
    try:
        if not path.is_file():
            return False
        if path.stat().st_size <= 0 or path.stat().st_size > MAX_IMAGE_BYTES:
            return False
        with Image.open(path) as image:
            if image.format != "PNG" or image.width <= 0 or image.height <= 0:
                return False
            if image.width * image.height > MAX_IMAGE_PIXELS:
                return False
            image.verify()
        with Image.open(path) as image:
            image.load()
            if require_transparency:
                low, high = image.convert("RGBA").getchannel("A").getextrema()
                if low == 255 or high == 0:
                    return False
        return True
    except (OSError, ValueError, Image.DecompressionBombError):
        return False


def _optional_int(value: object) -> int | None:
    try:
        return int(str(value).strip()) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _retryable_download_error(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in {408, 425, 429} or 500 <= exc.code < 600
    return isinstance(
        exc,
        (urllib.error.URLError, TimeoutError, ConnectionError, socket.timeout, http.client.IncompleteRead),
    )


def _safe_asset_error(kind: str, key: str, reason: str) -> dict[str, str]:
    """Keep URLs, credentials, and remote exception text out of manifests."""
    return {"kind": kind, "key": key, "reason": reason}


def _safe_icon_key(url: object) -> str:
    if not isinstance(url, str) or not url:
        return ""
    try:
        return icon_key(url)
    except (TypeError, ValueError):
        return ""


def _download_image(
    url: str, destination: Path, *, require_transparency: bool = False,
) -> dict[str, float | int]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host.endswith(".hoyolab.com") or host.endswith(".hoyoverse.com")):
        raise ValueError("Unexpected HoYoLAB image host")
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://act.hoyolab.com/"})
    request_started = time.perf_counter()
    request_read_seconds = 0.0
    try:
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read(MAX_IMAGE_BYTES + 1)
        finally:
            # This interval is limited to opening the HTTP response, reading
            # its body, and closing it. Image decode/validation and disk writes
            # below are excluded from the request/read duration.
            request_read_seconds = time.perf_counter() - request_started
        if not data or len(data) > MAX_IMAGE_BYTES:
            raise ValueError("HoYoLAB image is empty or too large")
        with Image.open(io.BytesIO(data)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError("HoYoLAB image exceeds pixel limit")
            image.load()
            rgba = image.convert("RGBA")
            if require_transparency:
                low, high = rgba.getchannel("A").getextrema()
                if low == 255 or high == 0:
                    raise ValueError("HoYoLAB portrait/weapon source has no usable transparent image")
            _save_png_atomic(rgba, destination)
    except Exception as exc:
        # Preserve timing on network and validation failures without wrapping
        # the original exception, so the existing retry classification stays
        # unchanged. The attribute is private runtime metadata only.
        try:
            setattr(exc, "_asset_request_read_seconds", request_read_seconds)
        except (AttributeError, TypeError):
            pass
        raise
    return {"responseBytes": len(data), "requestReadSeconds": request_read_seconds}


def _layer_file(staging_root: Path, final: Path) -> Path:
    staged = staging_root / final.relative_to(ACCOUNT_ROOT)
    return staged if staged.is_file() else final


def _render_character(
    staging_root: Path, destination: Path, *, portrait: Path, background: Path,
    element: Path | None = None, constellation: int | None = None,
) -> None:
    with Image.open(_layer_file(staging_root, background)) as source:
        canvas = source.convert("RGBA").resize((296, 296), Image.Resampling.LANCZOS)
    with Image.open(_layer_file(staging_root, portrait)) as source:
        canvas.alpha_composite(source.convert("RGBA").resize((296, 296), Image.Resampling.LANCZOS))
    if element is not None:
        with Image.open(_layer_file(staging_root, element)) as source:
            canvas.alpha_composite(source.convert("RGBA").resize((72, 72), Image.Resampling.LANCZOS), (8, 8))
    if constellation is not None:
        badge = Image.new("RGBA", (58, 50), (0, 0, 0, 0))
        draw = ImageDraw.Draw(badge)
        draw.rounded_rectangle((0, 0, 57, 49), radius=10, fill=(35, 32, 48, 190))
        try:
            font = ImageFont.truetype("arial.ttf", 32)
        except OSError:
            font = ImageFont.load_default()
        draw.text((17, 7), str(constellation), font=font, fill="white")
        canvas.alpha_composite(badge, (238, 0))
    _save_png_atomic(canvas, destination)


def _render_weapon(staging_root: Path, destination: Path, *, icon: Path, background: Path) -> None:
    with Image.open(_layer_file(staging_root, background)) as source:
        canvas = source.convert("RGBA").resize((128, 128), Image.Resampling.LANCZOS)
    with Image.open(_layer_file(staging_root, icon)) as source:
        canvas.alpha_composite(source.convert("RGBA").resize((128, 128), Image.Resampling.LANCZOS))
    _save_png_atomic(canvas, destination)


async def prepare_layered_assets(
    *, characters: list[dict], weapons: list[dict], cards: list[dict], staging_root: Path,
    refresh_images: bool = False,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> dict:
    """Prepare independent image assets and localize failures in the manifest.

    Returned paths refer only to a validated staged image or a validated cache
    image. The caller may publish staged images after this function returns.
    ``progress_callback`` runs on the asyncio event-loop thread, first with
    zero progress and then once per completed unique download/render job. A
    callback exception is recorded in the manifest and does not fail import.
    """
    total_started = time.perf_counter()
    clean_characters = [item for item in characters if isinstance(item, dict)]
    clean_weapons = [item for item in weapons if isinstance(item, dict)]
    clean_cards = [item for item in cards if isinstance(item, dict)]
    cards_by_icon = {
        _safe_icon_key(card.get("portrait")): card
        for card in clean_cards
        if _safe_icon_key(card.get("portrait"))
    }

    errors: list[dict[str, str]] = []
    error_keys: set[tuple[str, str, str]] = set()
    progress_callback_errors = 0

    def emit_progress(phase: str, completed: int, total: int) -> None:
        nonlocal progress_callback_errors
        if progress_callback is None:
            return
        try:
            progress_callback(phase, completed, total)
        except Exception:
            # A loader/UI observer must not turn optional asset work into an
            # import failure. Keep only an aggregate count, never exception
            # details that might contain paths or remote data.
            progress_callback_errors += 1

    def add_error(kind: str, key: object, reason: str) -> None:
        safe_key = str(key)
        marker = (kind, safe_key, reason)
        if marker not in error_keys:
            error_keys.add(marker)
            errors.append(_safe_asset_error(kind, safe_key, reason))

    def card_for(item: Mapping[str, object]) -> dict | None:
        return cards_by_icon.get(_safe_icon_key(item.get("icon")))

    # Learn card-provided layers when present; static public sources remain a
    # fallback, and a failure for one layer never blocks unrelated assets.
    element_urls: dict[str, str] = dict(STATIC_ELEMENTS)
    character_background_urls: dict[int, str] = dict(STATIC_RARITY_BACKGROUNDS)
    weapon_background_urls: dict[int, str] = dict(STATIC_RARITY_BACKGROUNDS)
    for character in clean_characters:
        card = card_for(character)
        if card is None:
            continue
        element = str(character.get("element") or "").strip().lower()
        rarity = _optional_int(character.get("rarity"))
        card_rarity = _optional_int(card.get("characterRarity"))
        rarity = rarity if rarity is not None else card_rarity
        if element in ELEMENTS and card.get("element"):
            element_urls[element] = str(card["element"])
        if rarity is not None and card.get("characterBackground"):
            character_background_urls[rarity] = str(card["characterBackground"])
        weapon_rarity = _optional_int(card.get("weaponRarity"))
        if weapon_rarity is not None and card.get("weaponBackground"):
            weapon_background_urls[weapon_rarity] = str(card["weaponBackground"])

    wanted_chars: list[tuple[dict, int]] = []
    for character in clean_characters:
        character_id = _optional_int(character.get("id"))
        if character_id is None:
            continue
        if character_id not in IGNORED_CHARACTER_IDS:
            wanted_chars.append((character, character_id))

    # Normalize rarity before creating any weapon image source/job. Both API
    # number values and string values "1"/"2" are excluded here.
    wanted_weapons: list[tuple[dict, int, int | None]] = []
    for weapon in clean_weapons:
        weapon_id = _optional_int(weapon.get("id"))
        if weapon_id is None:
            continue
        rarity = _optional_int(weapon.get("rarity"))
        if rarity in IGNORED_WEAPON_RARITIES:
            continue
        wanted_weapons.append((weapon, weapon_id, rarity))

    source_jobs: dict[Path, dict[str, object]] = {}

    def source_path(
        folder: Path,
        role: str,
        key: object,
        url: object,
        *,
        kind: str,
        require_transparency: bool = False,
    ) -> Path | None:
        normalized_url = str(url).strip() if isinstance(url, str) else ""
        if not normalized_url:
            add_error(kind, key, "missing_metadata")
            return None
        final = folder / f"{role}_{RENDER_VERSION}_{key}_{_fingerprint(normalized_url)}.png"
        source_jobs.setdefault(final, {
            "url": normalized_url,
            "kind": kind,
            "key": str(key),
            "require_transparency": require_transparency,
        })
        return final

    needed_elements = {
        str(character.get("element") or "").strip().lower()
        for character, _ in wanted_chars
        if str(character.get("element") or "").strip().lower() in ELEMENTS
    }
    element_paths: dict[str, Path | None] = {}
    for element in sorted(needed_elements):
        element_paths[element] = source_path(
            SHARED_ASSETS_DIR, "element", element, element_urls.get(element),
            kind="shared_element",
        )

    character_background_paths: dict[int, Path | None] = {}
    weapon_background_paths: dict[int, Path | None] = {}
    prepared_characters: list[dict[str, object]] = []
    for character, character_id in wanted_chars:
        key = str(character_id)
        card = card_for(character)
        element = str(character.get("element") or "").strip().lower()
        rarity = _optional_int(character.get("rarity"))
        if rarity is None and card is not None:
            rarity = _optional_int(card.get("characterRarity"))
        portrait = source_path(
            HOYOLAB_CHARACTER_ASSETS_DIR,
            "portrait",
            character_id,
            character.get("icon"),
            kind="character_portrait",
            require_transparency=True,
        )
        element_path = element_paths.get(element)
        if element not in ELEMENTS:
            add_error("character_element", key, "missing_metadata")
        background = None
        if rarity is not None:
            if rarity not in character_background_paths:
                character_background_paths[rarity] = source_path(
                    SHARED_ASSETS_DIR,
                    "rarity_bg",
                    rarity,
                    character_background_urls.get(rarity),
                    kind="shared_character_background",
                )
            background = character_background_paths[rarity]
        else:
            add_error("character_rarity", key, "missing_metadata")
        prepared_characters.append({
            "character": character,
            "id": character_id,
            "element": element,
            "rarity": rarity,
            "portrait": portrait,
            "element_path": element_path,
            "background": background,
        })

    prepared_weapons: list[dict[str, object]] = []
    seen_weapon_sources: set[tuple[int, str]] = set()
    for weapon, weapon_id, rarity in wanted_weapons:
        icon_url = weapon.get("icon")
        icon_text = str(icon_url).strip() if isinstance(icon_url, str) else ""
        source_key = (weapon_id, icon_text)
        if source_key in seen_weapon_sources:
            continue
        seen_weapon_sources.add(source_key)
        icon = source_path(
            HOYOLAB_WEAPON_ASSETS_DIR,
            "weapon_icon",
            weapon_id,
            icon_url,
            kind="weapon_icon",
            require_transparency=True,
        )
        background = None
        if rarity is not None:
            if rarity not in weapon_background_paths:
                weapon_background_paths[rarity] = source_path(
                    SHARED_ASSETS_DIR,
                    "rarity_bg",
                    rarity,
                    weapon_background_urls.get(rarity),
                    kind="shared_weapon_background",
                )
            background = weapon_background_paths[rarity]
        else:
            add_error("weapon_rarity", str(weapon_id), "missing_metadata")
        prepared_weapons.append({
            "weapon": weapon,
            "id": weapon_id,
            "rarity": rarity,
            "icon": icon,
            "background": background,
        })

    source_results: dict[Path, Path | None] = {}
    downloaded_count = 0
    downloaded_response_bytes = 0
    download_request_read_seconds = 0.0
    download_cache_hits = 0
    download_cache_fallbacks = 0
    download_failures = 0
    download_completed = 0
    download_semaphore = asyncio.Semaphore(MAX_ASSET_WORKERS)
    download_total = len(source_jobs)
    download_started = time.perf_counter()
    emit_progress("download", 0, download_total)

    async def download_source(final: Path, details: dict[str, object]) -> None:
        nonlocal downloaded_count, download_cache_hits, download_cache_fallbacks
        nonlocal download_failures, download_completed, downloaded_response_bytes
        nonlocal download_request_read_seconds
        async with download_semaphore:
            require_transparency = bool(details["require_transparency"])
            cached_valid = await _run_asset_thread(
                _image_is_usable, final, require_transparency=require_transparency,
            )
            if cached_valid and not refresh_images:
                source_results[final] = final
                download_cache_hits += 1
                download_completed += 1
                emit_progress("download", download_completed, download_total)
                return

            staged = staging_root / final.relative_to(ACCOUNT_ROOT)
            _remove_staged(staged)
            last_error: Exception | None = None
            attempts = MAX_DOWNLOAD_ATTEMPTS
            for attempt in range(attempts):
                try:
                    metadata = await _run_asset_thread(
                        _download_image,
                        str(details["url"]),
                        staged,
                        require_transparency=require_transparency,
                    )
                    if isinstance(metadata, Mapping):
                        response_bytes = metadata.get("responseBytes")
                        request_seconds = metadata.get("requestReadSeconds")
                        if isinstance(response_bytes, int) and not isinstance(response_bytes, bool):
                            downloaded_response_bytes += max(0, response_bytes)
                        if isinstance(request_seconds, (int, float)) and not isinstance(request_seconds, bool):
                            download_request_read_seconds += max(0.0, float(request_seconds))
                    if not await _run_asset_thread(
                        _image_is_usable, staged, require_transparency=require_transparency,
                    ):
                        raise ValueError("Downloaded image failed validation")
                    source_results[final] = staged
                    downloaded_count += 1
                    download_completed += 1
                    emit_progress("download", download_completed, download_total)
                    return
                except Exception as exc:
                    last_error = exc
                    request_seconds = getattr(exc, "_asset_request_read_seconds", 0.0)
                    if isinstance(request_seconds, (int, float)) and not isinstance(request_seconds, bool):
                        download_request_read_seconds += max(0.0, float(request_seconds))
                    _remove_staged(staged)
                    if attempt + 1 >= attempts or not _retryable_download_error(exc):
                        break
                    await asyncio.sleep(0.1 * (attempt + 1))

            if last_error is not None:
                download_failures += 1
                reason = "invalid_image" if isinstance(last_error, (Image.UnidentifiedImageError, Image.DecompressionBombError)) else (
                    "invalid_source" if isinstance(last_error, ValueError) else "download_failed"
                )
                add_error(str(details["kind"]), str(details["key"]), reason)
            # A refresh is best-effort: keep a valid prior file if the source
            # cannot be refreshed. Invalid caches are never advertised.
            source_results[final] = final if cached_valid else None
            if cached_valid:
                download_cache_fallbacks += 1
            download_completed += 1
            emit_progress("download", download_completed, download_total)

    await _gather_asset_tasks((
        download_source(final, details)
        for final, details in source_jobs.items()
    ))
    download_elapsed = time.perf_counter() - download_started

    output_results: dict[Path, Path | None] = {}
    rendered_count = 0
    render_cache_hits = 0
    render_cache_fallbacks = 0
    render_failures = 0
    render_dependency_unavailable = 0
    render_completed = 0
    render_semaphore = asyncio.Semaphore(MAX_ASSET_WORKERS)

    async def render_output(
        final: Path,
        *,
        kind: str,
        key: str,
        render_func: Callable[..., None],
        kwargs: dict[str, object],
        dependencies: tuple[Path | None, ...],
    ) -> None:
        nonlocal rendered_count, render_cache_hits, render_cache_fallbacks
        nonlocal render_failures, render_dependency_unavailable, render_completed
        async with render_semaphore:
            cached_valid = await _run_asset_thread(_image_is_usable, final)
        if cached_valid and not refresh_images:
            output_results[final] = final
            render_cache_hits += 1
            render_completed += 1
            emit_progress("render", render_completed, render_total)
            return
        if any(path is None or source_results.get(path) is None for path in dependencies):
            add_error(kind, key, "dependency_unavailable")
            output_results[final] = final if cached_valid else None
            render_dependency_unavailable += 1
            if cached_valid:
                render_cache_fallbacks += 1
            render_completed += 1
            emit_progress("render", render_completed, render_total)
            return

        staged = staging_root / final.relative_to(ACCOUNT_ROOT)
        _remove_staged(staged)
        render_kwargs = dict(kwargs)
        render_kwargs["destination"] = staged
        try:
            async with render_semaphore:
                await _run_asset_thread(render_func, **render_kwargs)
                staged_valid = await _run_asset_thread(_image_is_usable, staged)
            if not staged_valid:
                raise ValueError("Rendered image failed validation")
            output_results[final] = staged
            rendered_count += 1
        except Exception:
            _remove_staged(staged)
            add_error(kind, key, "render_failed")
            output_results[final] = final if cached_valid else None
            render_failures += 1
            if cached_valid:
                render_cache_fallbacks += 1
        render_completed += 1
        emit_progress("render", render_completed, render_total)

    character_jobs: list[dict[str, object]] = []
    for prepared in prepared_characters:
        character = prepared["character"]
        character_id = int(prepared["id"])
        key = str(character_id)
        portrait = prepared["portrait"]
        background = prepared["background"]
        element_path = prepared["element_path"]
        paths: dict[str, Path | None] = {"history": None, "pvp": None, "browser": None}
        if isinstance(portrait, Path) and isinstance(background, Path):
            base_key = _fingerprint(portrait.name, background.name)
            paths["history"] = HOYOLAB_CHARACTER_ASSETS_DIR / (
                f"char_history_{RENDER_VERSION}_{key}_{base_key}.png"
            )
            if isinstance(element_path, Path):
                element_key = _fingerprint(base_key, element_path.name)
                paths["pvp"] = HOYOLAB_CHARACTER_ASSETS_DIR / (
                    f"char_pvp_{RENDER_VERSION}_{key}_{element_key}.png"
                )
                constellation = character.get("constellation")
                paths["browser"] = HOYOLAB_CHARACTER_ASSETS_DIR / (
                    f"char_{RENDER_VERSION}_{key}_{_fingerprint(element_key, constellation)}.png"
                )
        character_jobs.append({**prepared, "paths": paths})

    render_tasks = []
    for prepared in character_jobs:
        character = prepared["character"]
        key = str(prepared["id"])
        portrait = prepared["portrait"]
        background = prepared["background"]
        element_path = prepared["element_path"]
        paths = prepared["paths"]
        if isinstance(paths["history"], Path):
            render_tasks.append(render_output(
                paths["history"], kind="character_history", key=key,
                render_func=_render_character,
                kwargs={
                    "staging_root": staging_root, "portrait": portrait,
                    "background": background, "element": None, "constellation": None,
                },
                dependencies=(portrait, background),
            ))
        else:
            add_error("character_history", key, "dependency_unavailable")
        for variant in ("pvp", "browser"):
            if not isinstance(paths[variant], Path):
                add_error(f"character_{variant}", key, "dependency_unavailable")
                continue
            render_tasks.append(render_output(
                paths[variant], kind=f"character_{variant}", key=key,
                render_func=_render_character,
                kwargs={
                    "staging_root": staging_root, "portrait": portrait,
                    "background": background, "element": element_path,
                    "constellation": character.get("constellation") if variant == "browser" else None,
                },
                dependencies=(portrait, background, element_path),
            ))

    weapon_jobs: list[dict[str, object]] = []
    for prepared in prepared_weapons:
        weapon_id = int(prepared["id"])
        icon = prepared["icon"]
        background = prepared["background"]
        composite = None
        if isinstance(icon, Path) and isinstance(background, Path):
            composite = HOYOLAB_WEAPON_ASSETS_DIR / (
                f"weapon_{RENDER_VERSION}_{weapon_id}_{_fingerprint(icon.name, background.name)}.png"
            )
            render_tasks.append(render_output(
                composite, kind="weapon_card", key=str(weapon_id),
                render_func=_render_weapon,
                kwargs={"staging_root": staging_root, "icon": icon, "background": background},
                dependencies=(icon, background),
            ))
        else:
            add_error("weapon_card", str(weapon_id), "dependency_unavailable")
        weapon_jobs.append({**prepared, "composite": composite})

    render_total = len(render_tasks)
    render_started = time.perf_counter()
    emit_progress("render", 0, render_total)
    await _gather_asset_tasks(render_tasks)
    render_elapsed = time.perf_counter() - render_started

    def manifest_path(final: Path | None, results: Mapping[Path, Path | None]) -> str:
        if final is None:
            return ""
        actual = results.get(final)
        # Results enter this map only after validating a cache file or a staged
        # writer. Reopening here would repeat a full decode for every slot.
        if actual is None:
            return ""
        return _relative(final)

    pending_assets: set[tuple[str, str]] = set()

    def note_pending(value: str, final: Path | None, identity: str) -> None:
        if value:
            return
        pending_assets.add(
            ("path", _relative(final)) if final is not None else ("slot", identity)
        )

    character_assets = []
    for prepared in character_jobs:
        character = prepared["character"]
        paths = prepared["paths"]
        asset = {
            "assetKey": character_asset_key(character),
            "character": character,
            "crop": manifest_path(paths["browser"], output_results),
            "pvp": manifest_path(paths["pvp"], output_results),
            "history": manifest_path(paths["history"], output_results),
            "portrait": manifest_path(prepared["portrait"], source_results),
        }
        character_assets.append(asset)
        key = str(prepared["id"])
        note_pending(asset["crop"], paths["browser"], f"character:{key}:crop")
        note_pending(asset["pvp"], paths["pvp"], f"character:{key}:pvp")
        note_pending(asset["history"], paths["history"], f"character:{key}:history")
        note_pending(asset["portrait"], prepared["portrait"], f"character:{key}:portrait")

    weapon_assets = []
    for prepared in weapon_jobs:
        weapon = prepared["weapon"]
        icon_url = weapon.get("icon")
        asset = {
            "assetKey": _safe_icon_key(icon_url),
            "iconKey": _safe_icon_key(icon_url),
            "weapon": weapon,
            "crop": manifest_path(prepared["composite"], output_results),
            "icon": manifest_path(prepared["icon"], source_results),
        }
        weapon_assets.append(asset)
        key = str(prepared["id"])
        note_pending(asset["crop"], prepared["composite"], f"weapon:{key}:crop")
        note_pending(asset["icon"], prepared["icon"], f"weapon:{key}:icon")

    shared_elements = {
        key: manifest_path(path, source_results)
        for key, path in element_paths.items()
    }
    shared_character_backgrounds = {
        str(key): manifest_path(path, source_results)
        for key, path in character_background_paths.items()
    }
    shared_weapon_backgrounds = {
        str(key): manifest_path(path, source_results)
        for key, path in weapon_background_paths.items()
    }
    for key, value in shared_elements.items():
        note_pending(value, element_paths.get(key), f"shared:element:{key}")
    for key, value in shared_character_backgrounds.items():
        note_pending(value, character_background_paths.get(int(key)), f"shared:rarity_bg:{key}")
    for key, value in shared_weapon_backgrounds.items():
        note_pending(value, weapon_background_paths.get(int(key)), f"shared:rarity_bg:{key}")
    warning_matches = sum(1 for asset in character_assets if not asset["crop"])

    return {
        "version": 2,
        "source": {"method": "separate_hoyolab_layers"},
        "cardsCount": len(wanted_chars),
        "matchedCharacters": len(character_assets),
        "matchedWeapons": len(weapon_assets),
        "okMatches": len(character_assets) - warning_matches,
        "warningMatches": warning_matches,
        "characterAssets": character_assets,
        "weaponAssets": weapon_assets,
        "sharedAssets": {
            "elements": shared_elements,
            "characterBackgrounds": shared_character_backgrounds,
            "weaponBackgrounds": shared_weapon_backgrounds,
        },
        "assetsDownloaded": downloaded_count,
        "assetsRendered": rendered_count,
        "assetTimings": {
            "download": {
                "jobs": download_total,
                "completed": download_completed,
                "downloaded": downloaded_count,
                "downloadedResponseBytes": downloaded_response_bytes,
                "requestReadSeconds": round(download_request_read_seconds, 3),
                "requestReadScope": (
                    "urlopen plus response-body read/close wall time; excludes image decode, "
                    "validation, and disk writes"
                ),
                "cacheHits": download_cache_hits,
                "cacheFallbacks": download_cache_fallbacks,
                "failed": download_failures,
                "elapsedSeconds": round(download_elapsed, 3),
            },
            "render": {
                "jobs": render_total,
                "completed": render_completed,
                "rendered": rendered_count,
                "cacheHits": render_cache_hits,
                "cacheFallbacks": render_cache_fallbacks,
                "dependencyUnavailable": render_dependency_unavailable,
                "failed": render_failures,
                "elapsedSeconds": round(render_elapsed, 3),
            },
            "totalElapsedSeconds": round(time.perf_counter() - total_started, 3),
            "progressCallbackErrors": progress_callback_errors,
        },
        # Count each manifest image slot that has no usable staged or cached file.
        # Count unique missing files; shared rarity layers can serve both groups.
        "assetsPending": len(pending_assets),
        "assetErrors": sorted(errors, key=lambda item: (item["kind"], item["key"], item["reason"])),
    }


def cleanup_unused_v2_assets(manifest: Mapping[str, object]) -> list[str]:
    """Retire unused raw layers while preserving older display images.

    PvP profile slices can still refer to a previously rendered card bitmap.
    They do not carry their own image files, so those composites must survive
    later imports of the local account.
    """
    referenced = set()
    for asset in (*manifest.get("characterAssets", []), *manifest.get("weaponAssets", [])):
        if isinstance(asset, Mapping):
            referenced.update(str(value) for key, value in asset.items() if key in {"crop", "pvp", "history", "portrait", "icon"})
    shared = manifest.get("sharedAssets", {})
    if isinstance(shared, Mapping):
        for group in shared.values():
            if isinstance(group, Mapping):
                referenced.update(str(value) for value in group.values())
    failures: list[str] = []
    for folder in (HOYOLAB_CHARACTER_ASSETS_DIR, HOYOLAB_WEAPON_ASSETS_DIR, SHARED_ASSETS_DIR):
        if not folder.is_dir():
            continue
        for path in folder.glob("*.png"):
            if path.name.startswith(("char_v2_", "char_pvp_v2_", "char_history_v2_", "weapon_v2_")):
                continue
            if f"_{RENDER_VERSION}_" in path.name and _relative(path) not in referenced:
                try:
                    path.unlink()
                except OSError:
                    failures.append(_relative(path))
    return failures
