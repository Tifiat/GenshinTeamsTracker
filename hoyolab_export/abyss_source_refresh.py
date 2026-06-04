from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Mapping
from urllib.parse import urlencode

from playwright.async_api import BrowserContext

from run_workspace.abyss.source_data import AbyssFloorSourceData
from run_workspace.abyss.source_data_cache import (
    cached_abyss_floor_monster_icon_dir,
    cached_abyss_floor_source_data_path,
    load_cached_abyss_floor_source_data,
)
from run_workspace.abyss.fandom_enemy_hp_fallback import (
    DEFAULT_ABYSS_FANDOM_HP_MULTIPLIER,
    DEFAULT_FANDOM_ENEMY_PAGE_WORKERS,
    HP_FALLBACK_MODE_AUTO,
    HP_FALLBACK_MODE_CHOICES,
)
from run_workspace.abyss.source_data_update import build_update_report
from run_workspace.abyss.source_data_fetchers import (
    ResolvedAbyssPeriodSource,
    resolve_fandom_latest_period,
    resolve_nanoka_live_period,
)

from .auth import AuthStatus, get_auth_status
from .character_detail import ROLES_URL, pick_genshin_role
from .hoyolab_exporter import HOYOLAB_URL, HoyolabExporter, close_export_context
from .paths import (
    HOYOLAB_DATA_DIR,
    HOYOLAB_DEBUG_DIR,
    HOYOLAB_PROFILE_DIR,
    ensure_hoyolab_dirs,
)


SPIRAL_ABYSS_URL = (
    "https://sg-public-api.hoyolab.com/event/game_record/genshin/api/spiralAbyss"
)
DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH = HOYOLAB_DATA_DIR / "spiral_abyss_period.json"
DEFAULT_HOYOLAB_REQUEST_LANGUAGE = "en-us"
PERIOD_SOURCE_AUTO = "auto"
PERIOD_SOURCE_HOYOLAB = "hoyolab"
PERIOD_SOURCE_NANOKA = "nanoka"
PERIOD_SOURCE_FANDOM = "fandom"
PERIOD_SOURCE_CHOICES = (
    PERIOD_SOURCE_AUTO,
    PERIOD_SOURCE_HOYOLAB,
    PERIOD_SOURCE_NANOKA,
    PERIOD_SOURCE_FANDOM,
)

_DATE_PATTERN = r"\d{4}[/-]\d{1,2}[/-]\d{1,2}"
_NAMED_DATE_PATTERN = r"(?P<year>\d{4})[/-](?P<month>\d{1,2})[/-](?P<day>\d{1,2})"
_PERIOD_PATTERN = re.compile(
    rf"(?P<start>{_DATE_PATTERN})\s*(?:-|--|~|to|until|through)\s*"
    rf"(?P<end>{_DATE_PATTERN})",
    re.IGNORECASE,
)
_SINGLE_DATE_PATTERN = re.compile(_NAMED_DATE_PATTERN)

_START_KEYS = (
    "start",
    "start_date",
    "start_time",
    "begin",
    "begin_date",
    "begin_time",
)
_END_KEYS = (
    "end",
    "end_date",
    "end_time",
    "finish",
    "finish_date",
    "finish_time",
)


class HoYoLABAbyssPeriodError(RuntimeError):
    """Raised when HoYoLAB Spiral Abyss period data cannot be extracted."""


@dataclass(frozen=True, slots=True)
class HoYoLABAbyssPeriod:
    raw_period: str
    start_date: str
    end_date: str
    source_path: str
    source: str = "hoyolab_spiral_abyss_overview"
    warnings: tuple[str, ...] = ()
    fallback: bool = False
    source_metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rawPeriod": self.raw_period,
            "startDate": self.start_date,
            "endDate": self.end_date,
            "sourcePath": self.source_path,
            "source": self.source,
            "warnings": list(self.warnings),
            "fallback": self.fallback,
            "sourceMetadata": dict(self.source_metadata),
        }


@dataclass(frozen=True, slots=True)
class AbyssSourceDataRefreshResult:
    period: HoYoLABAbyssPeriod
    floor: int
    cache_saved: bool
    cache_path: str | None
    matched: int | None
    unmatched: int | None
    ambiguous: int | None
    enemy_rows: int | None
    assets: Mapping[str, Any]
    skipped: bool = False
    skip_reason: str = ""
    warnings: tuple[str, ...] = ()
    timings_ms: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period.to_dict(),
            "floor": self.floor,
            "cacheSaved": self.cache_saved,
            "cachePath": self.cache_path,
            "skipped": self.skipped,
            "skipReason": self.skip_reason,
            "matched": self.matched,
            "unmatched": self.unmatched,
            "ambiguous": self.ambiguous,
            "enemyRows": self.enemy_rows,
            "assets": dict(self.assets),
            "warnings": list(self.warnings),
            "timingsMs": dict(self.timings_ms),
        }


RefreshUpdateCallable = Callable[..., AbyssSourceDataRefreshResult]


def parse_hoyolab_abyss_period(value: str, *, source_path: str = "$") -> HoYoLABAbyssPeriod:
    """Parse an official HoYoLAB period string such as 2026/05/16-2026/06/16."""

    match = _PERIOD_PATTERN.search(str(value or ""))
    if not match:
        raise HoYoLABAbyssPeriodError(f"Unsupported HoYoLAB Abyss period: {value!r}")
    start = _normalize_date(match.group("start"))
    end = _normalize_date(match.group("end"))
    return HoYoLABAbyssPeriod(
        raw_period=match.group(0),
        start_date=start,
        end_date=end,
        source_path=source_path,
    )


def extract_hoyolab_abyss_period(payload: Mapping[str, Any]) -> HoYoLABAbyssPeriod:
    """Extract the official Abyss period from a HoYoLAB Spiral Abyss response."""

    for path, value in _walk_payload(payload):
        if isinstance(value, str):
            try:
                return parse_hoyolab_abyss_period(value, source_path=path)
            except HoYoLABAbyssPeriodError:
                pass

    for path, value in _walk_payload(payload):
        if not isinstance(value, Mapping):
            continue
        period = _period_from_mapping(value, source_path=path)
        if period is not None:
            return period

    raise HoYoLABAbyssPeriodError(
        "HoYoLAB Spiral Abyss response did not expose an official period string."
    )


async def fetch_hoyolab_spiral_abyss_period(
    page: Any,
    *,
    language: str | None = None,
    schedule_type: int = 1,
) -> HoYoLABAbyssPeriod:
    """Fetch the official Spiral Abyss period through the logged-in HoYoLAB page."""

    roles_result = await context_request_fetch_json(page, ROLES_URL, language=language)
    roles_payload = roles_result.get("json") or {}
    _raise_for_hoyolab_api_error(
        roles_payload,
        response=roles_result,
        label="HoYoLAB roles",
    )
    try:
        role_id, server = pick_genshin_role(roles_payload)
    except RuntimeError as exc:
        raise HoYoLABAbyssPeriodError(
            "Could not detect Genshin role_id/server from HoYoLAB roles response. "
            "HoYoLAB auth may be missing or expired."
        ) from exc
    query = urlencode(
        {
            "server": server,
            "role_id": role_id,
            "schedule_type": int(schedule_type),
        }
    )
    response = await context_request_fetch_json(
        page,
        f"{SPIRAL_ABYSS_URL}?{query}",
        language=language,
    )
    payload = response.get("json") or {}
    _raise_for_hoyolab_api_error(
        payload,
        response=response,
        label="HoYoLAB Spiral Abyss overview",
    )
    return extract_hoyolab_abyss_period(payload)


async def context_request_fetch_json(
    page: Any,
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """Fetch HoYoLAB JSON through BrowserContext.request, not page.evaluate."""

    context = getattr(page, "context", None)
    request = getattr(context, "request", None)
    if request is None:
        raise HoYoLABAbyssPeriodError(
            "HoYoLAB browser context does not expose Playwright request API."
        )
    detected_language = await _detect_hoyolab_request_language(page, language=language)
    headers = {
        "content-type": "application/json",
        "accept": "application/json, text/plain, */*",
        "x-rpc-language": detected_language,
        "accept-language": _accept_language_header(detected_language),
        "origin": "https://act.hoyolab.com",
        "referer": HOYOLAB_URL,
    }
    normalized_method = str(method or "GET").upper()
    if normalized_method == "GET":
        response = await request.get(url, headers=headers)
    elif normalized_method == "POST":
        response = await request.post(url, headers=headers, data=json.dumps(body or {}))
    else:
        raise HoYoLABAbyssPeriodError(f"Unsupported HoYoLAB request method: {method!r}")
    text = await response.text()
    parsed_json = None
    try:
        parsed_json = json.loads(text)
    except json.JSONDecodeError:
        pass
    return {
        "ok": 200 <= int(getattr(response, "status", 0)) < 300,
        "status": int(getattr(response, "status", 0)),
        "statusText": str(getattr(response, "status_text", "")),
        "url": str(getattr(response, "url", url)),
        "detectedLanguage": detected_language,
        "requestedLanguage": _normalize_hoyolab_language(language),
        "json": parsed_json,
        "textPreview": text[:1000] if parsed_json is None else None,
    }


async def fetch_hoyolab_spiral_abyss_period_with_export_context(
    *,
    language: str | None = None,
) -> HoYoLABAbyssPeriod:
    """Open the normal HoYoLAB export context and fetch the official Abyss period."""

    if get_auth_status(HOYOLAB_PROFILE_DIR) != AuthStatus.LOGGED_IN:
        raise HoYoLABAbyssPeriodError(
            "HoYoLAB profile is not logged in. Authorize in the app first."
        )

    exporter = HoyolabExporter(
        profile_dir=HOYOLAB_PROFILE_DIR,
        download_dir=HOYOLAB_DEBUG_DIR,
        browser_window_width=1280,
        browser_window_height=900,
    )
    context: BrowserContext | None = None
    try:
        context = await exporter._create_context()
        page = await _get_export_page(context)
        await page.goto(HOYOLAB_URL, wait_until="domcontentloaded", timeout=60_000)
        return await fetch_hoyolab_spiral_abyss_period(page, language=language)
    finally:
        if context is not None:
            await close_export_context(context)


async def resolve_abyss_period_with_fallbacks(
    page: Any | None,
    *,
    language: str | None = None,
    period_source: str = PERIOD_SOURCE_AUTO,
    hoyolab_fetcher: Callable[..., Any] = fetch_hoyolab_spiral_abyss_period,
    nanoka_live_resolver: Callable[[], ResolvedAbyssPeriodSource] = resolve_nanoka_live_period,
    fandom_latest_resolver: Callable[[], ResolvedAbyssPeriodSource] = resolve_fandom_latest_period,
) -> HoYoLABAbyssPeriod:
    """Resolve the current Abyss period through HoYoLAB, then fallbacks."""

    mode = _normalize_period_source(period_source)
    failures: list[str] = []
    if mode in (PERIOD_SOURCE_AUTO, PERIOD_SOURCE_HOYOLAB):
        if page is None:
            message = "HoYoLAB page is unavailable."
            if mode == PERIOD_SOURCE_HOYOLAB:
                raise HoYoLABAbyssPeriodError(message)
            failures.append(f"hoyolab_spiral_abyss_overview_failed:{message}")
        else:
            try:
                period = await hoyolab_fetcher(page, language=language)
                return _period_with_resolution_metadata(
                    period,
                    source=period.source,
                    source_path=period.source_path,
                    warnings=period.warnings,
                    fallback=False,
                    source_metadata=period.source_metadata,
                )
            except Exception as exc:
                if mode == PERIOD_SOURCE_HOYOLAB:
                    raise
                failures.append(
                    "hoyolab_spiral_abyss_overview_failed:"
                    + _compact_exception_summary(exc)
                )

    if mode in (PERIOD_SOURCE_AUTO, PERIOD_SOURCE_FANDOM):
        try:
            resolved = fandom_latest_resolver()
            return _period_from_resolved_source(
                resolved,
                prior_warnings=failures,
                fallback=(mode == PERIOD_SOURCE_AUTO),
            )
        except Exception as exc:
            if mode == PERIOD_SOURCE_FANDOM:
                raise HoYoLABAbyssPeriodError(_compact_exception_summary(exc)) from exc
            failures.append("fandom_latest_fallback_failed:" + _compact_exception_summary(exc))

    if mode in (PERIOD_SOURCE_AUTO, PERIOD_SOURCE_NANOKA):
        try:
            resolved = nanoka_live_resolver()
            return _period_from_resolved_source(
                resolved,
                prior_warnings=failures,
                fallback=(mode == PERIOD_SOURCE_AUTO),
            )
        except Exception as exc:
            if mode == PERIOD_SOURCE_NANOKA:
                raise HoYoLABAbyssPeriodError(_compact_exception_summary(exc)) from exc
            failures.append("nanoka_live_fallback_failed:" + _compact_exception_summary(exc))

    raise HoYoLABAbyssPeriodError(
        "Could not resolve Spiral Abyss period from HoYoLAB, Fandom latest, or Nanoka live. "
        + "; ".join(failures)
    )


async def resolve_abyss_period_with_export_context(
    *,
    language: str | None = None,
    period_source: str = PERIOD_SOURCE_AUTO,
) -> HoYoLABAbyssPeriod:
    """Resolve Abyss period through the normal export context when needed."""

    mode = _normalize_period_source(period_source)
    if mode not in (PERIOD_SOURCE_AUTO, PERIOD_SOURCE_HOYOLAB):
        return await resolve_abyss_period_with_fallbacks(
            None,
            language=language,
            period_source=mode,
        )
    if get_auth_status(HOYOLAB_PROFILE_DIR) != AuthStatus.LOGGED_IN:
        if mode == PERIOD_SOURCE_HOYOLAB:
            raise HoYoLABAbyssPeriodError(
                "HoYoLAB profile is not logged in. Authorize in the app first."
            )
        return await resolve_abyss_period_with_fallbacks(
            None,
            language=language,
            period_source=PERIOD_SOURCE_AUTO,
        )

    exporter = HoyolabExporter(
        profile_dir=HOYOLAB_PROFILE_DIR,
        download_dir=HOYOLAB_DEBUG_DIR,
        browser_window_width=1280,
        browser_window_height=900,
    )
    context: BrowserContext | None = None
    try:
        context = await exporter._create_context()
        page = await _get_export_page(context)
        await page.goto(HOYOLAB_URL, wait_until="domcontentloaded", timeout=60_000)
        return await resolve_abyss_period_with_fallbacks(
            page,
            language=language,
            period_source=mode,
        )
    finally:
        if context is not None:
            await close_export_context(context)


def write_hoyolab_abyss_period(
    period: HoYoLABAbyssPeriod,
    *,
    period_path: str | Path | None = None,
) -> Path:
    """Write the period reference consumed by runtime cached source-data loaders."""

    path = Path(period_path) if period_path is not None else DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH
    ensure_hoyolab_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(period.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def update_cached_abyss_source_data_for_hoyolab_period(
    period: HoYoLABAbyssPeriod | str,
    *,
    floor: int = 12,
    cache_dir: str | Path | None = None,
    cache_assets: bool = True,
    force: bool = False,
    hp_source_mode: str = HP_FALLBACK_MODE_AUTO,
    hp_multiplier: float = DEFAULT_ABYSS_FANDOM_HP_MULTIPLIER,
    fandom_hp_workers: int = DEFAULT_FANDOM_ENEMY_PAGE_WORKERS,
    update_report_builder: Callable[..., Mapping[str, Any]] | None = None,
) -> AbyssSourceDataRefreshResult:
    """Update Floor 12 source-data cache from an official HoYoLAB Abyss period."""

    total_start = perf_counter()
    timings: dict[str, float] = {}
    parsed = _coerce_period(period)
    if not force:
        lookup_start = perf_counter()
        cached = _ready_cached_source_data(
            parsed,
            floor=floor,
            cache_dir=cache_dir,
            require_assets=cache_assets,
        )
        timings["cache_ready_lookup"] = _elapsed_ms(lookup_start)
        if cached is not None:
            timings["total"] = _elapsed_ms(total_start)
            return _cached_refresh_result(
                parsed,
                cached,
                floor=floor,
                cache_dir=cache_dir,
                cache_assets=cache_assets,
                timings_ms=timings,
            )

    builder = update_report_builder or build_update_report
    report = builder(
        period_start=parsed.start_date,
        period_end=parsed.end_date,
        floor=floor,
        save_cache=True,
        cache_dir=cache_dir,
        cache_assets=cache_assets,
        hp_source_mode=hp_source_mode,
        hp_multiplier=hp_multiplier,
        fandom_hp_workers=fandom_hp_workers,
    )
    summary = report.get("summary") if isinstance(report, Mapping) else {}
    cache = report.get("cache") if isinstance(report, Mapping) else {}
    assets = report.get("assets") if isinstance(report, Mapping) else {}
    probe = report.get("probe") if isinstance(report, Mapping) else {}
    timings = probe.get("timings_ms") if isinstance(probe, Mapping) else {}
    warnings = []
    for source in (summary, assets):
        if isinstance(source, Mapping):
            warnings.extend(str(item) for item in source.get("warnings") or [])
    return AbyssSourceDataRefreshResult(
        period=parsed,
        floor=int(floor),
        cache_saved=bool(cache.get("saved")) if isinstance(cache, Mapping) else False,
        cache_path=(
            str(cache.get("path"))
            if isinstance(cache, Mapping) and cache.get("path") is not None
            else None
        ),
        matched=_optional_int(summary.get("matched")) if isinstance(summary, Mapping) else None,
        unmatched=_optional_int(summary.get("unmatched")) if isinstance(summary, Mapping) else None,
        ambiguous=_optional_int(summary.get("ambiguous")) if isinstance(summary, Mapping) else None,
        enemy_rows=_optional_int(summary.get("enemy_rows")) if isinstance(summary, Mapping) else None,
        assets=dict(assets) if isinstance(assets, Mapping) else {},
        skipped=False,
        skip_reason="",
        warnings=tuple(warnings),
        timings_ms=dict(timings) if isinstance(timings, Mapping) else {},
    )


def refresh_cached_abyss_source_data_for_hoyolab_period(
    period: HoYoLABAbyssPeriod | str | None,
    *,
    floor: int = 12,
    cache_dir: str | Path | None = None,
    cache_assets: bool = True,
    force: bool = False,
    hp_source_mode: str = HP_FALLBACK_MODE_AUTO,
    hp_multiplier: float = DEFAULT_ABYSS_FANDOM_HP_MULTIPLIER,
    fandom_hp_workers: int = DEFAULT_FANDOM_ENEMY_PAGE_WORKERS,
    updater: RefreshUpdateCallable = update_cached_abyss_source_data_for_hoyolab_period,
) -> tuple[dict[str, Any] | None, str | None]:
    """Best-effort import integration wrapper: never raises for cache refresh."""

    if period is None:
        return None, "official_abyss_period_unavailable"
    try:
        result = updater(
            period,
            floor=floor,
            cache_dir=cache_dir,
            cache_assets=cache_assets,
            force=force,
            hp_source_mode=hp_source_mode,
            hp_multiplier=hp_multiplier,
            fandom_hp_workers=fandom_hp_workers,
        )
    except Exception as exc:
        return None, _compact_exception_summary(exc)
    return result.to_dict(), None


def _normalize_period_source(value: str | None) -> str:
    normalized = str(value or PERIOD_SOURCE_AUTO).strip().lower()
    if normalized not in PERIOD_SOURCE_CHOICES:
        choices = ", ".join(PERIOD_SOURCE_CHOICES)
        raise HoYoLABAbyssPeriodError(
            f"Unsupported Abyss period source: {value!r}. Expected one of: {choices}."
        )
    return normalized


def _period_from_resolved_source(
    resolved: ResolvedAbyssPeriodSource | HoYoLABAbyssPeriod | Mapping[str, Any],
    *,
    prior_warnings: list[str],
    fallback: bool,
) -> HoYoLABAbyssPeriod:
    if isinstance(resolved, HoYoLABAbyssPeriod):
        return _period_with_resolution_metadata(
            resolved,
            source=resolved.source,
            source_path=resolved.source_path,
            warnings=(*prior_warnings, *resolved.warnings),
            fallback=fallback or resolved.fallback,
            source_metadata=resolved.source_metadata,
        )
    if isinstance(resolved, ResolvedAbyssPeriodSource):
        return HoYoLABAbyssPeriod(
            raw_period=resolved.raw_period,
            start_date=resolved.start_date,
            end_date=resolved.end_date or "",
            source_path=resolved.source_path,
            source=resolved.source,
            warnings=(*prior_warnings, *resolved.warnings),
            fallback=fallback,
            source_metadata=resolved.metadata,
        )
    return HoYoLABAbyssPeriod(
        raw_period=str(resolved.get("raw_period") or resolved.get("rawPeriod") or ""),
        start_date=str(resolved.get("start_date") or resolved.get("startDate") or ""),
        end_date=str(resolved.get("end_date") or resolved.get("endDate") or ""),
        source_path=str(resolved.get("source_path") or resolved.get("sourcePath") or ""),
        source=str(resolved.get("source") or "unknown_period_source"),
        warnings=(
            *prior_warnings,
            *[str(item) for item in resolved.get("warnings") or []],
        ),
        fallback=fallback,
        source_metadata=dict(resolved.get("metadata") or resolved.get("sourceMetadata") or {}),
    )


def _period_with_resolution_metadata(
    period: HoYoLABAbyssPeriod,
    *,
    source: str,
    source_path: str,
    warnings: tuple[str, ...] | list[str],
    fallback: bool,
    source_metadata: Mapping[str, Any],
) -> HoYoLABAbyssPeriod:
    return HoYoLABAbyssPeriod(
        raw_period=period.raw_period,
        start_date=period.start_date,
        end_date=period.end_date,
        source_path=source_path,
        source=source,
        warnings=tuple(str(item) for item in warnings),
        fallback=fallback,
        source_metadata=dict(source_metadata),
    )


async def _get_export_page(context: BrowserContext):
    for page in context.pages:
        if not page.is_closed():
            return page
    return await context.new_page()


async def _detect_hoyolab_request_language(
    page: Any,
    *,
    language: str | None,
) -> str:
    requested = _normalize_hoyolab_language(language)
    if requested:
        return requested
    context = getattr(page, "context", None)
    cookies = []
    if context is not None and hasattr(context, "cookies"):
        try:
            cookies = await context.cookies()
        except Exception:
            cookies = []
    for cookie in cookies:
        if not isinstance(cookie, Mapping):
            continue
        if cookie.get("name") == "mi18nLang":
            cookie_language = _normalize_hoyolab_language(cookie.get("value"))
            if cookie_language:
                return cookie_language
    return DEFAULT_HOYOLAB_REQUEST_LANGUAGE


def _normalize_hoyolab_language(value: Any) -> str:
    if not value:
        return ""
    return str(value).strip().replace("_", "-").lower()


def _accept_language_header(language: str) -> str:
    normalized = _normalize_hoyolab_language(language)
    if not normalized:
        return "en-US,en;q=0.9"
    parts = normalized.split("-", 1)
    primary = parts[0] or "en"
    region = parts[1] if len(parts) > 1 else primary
    browser_language = f"{primary}-{region.upper()}"
    return f"{browser_language},{primary};q=0.9,en;q=0.8"


def _raise_for_hoyolab_api_error(
    payload: Mapping[str, Any],
    *,
    response: Mapping[str, Any],
    label: str,
) -> None:
    if not response.get("ok"):
        raise HoYoLABAbyssPeriodError(
            f"{label} request failed: HTTP {response.get('status')} "
            f"{response.get('statusText') or ''}".strip()
        )
    retcode = payload.get("retcode")
    if retcode not in (None, 0):
        message = payload.get("message") or payload.get("msg") or "unknown error"
        raise HoYoLABAbyssPeriodError(
            f"{label} failed: retcode={retcode} message={message}"
        )


def _coerce_period(period: HoYoLABAbyssPeriod | str) -> HoYoLABAbyssPeriod:
    if isinstance(period, HoYoLABAbyssPeriod):
        return period
    return parse_hoyolab_abyss_period(str(period))


def _ready_cached_source_data(
    period: HoYoLABAbyssPeriod,
    *,
    floor: int,
    cache_dir: str | Path | None,
    require_assets: bool,
) -> AbyssFloorSourceData | None:
    try:
        data = load_cached_abyss_floor_source_data(
            period.start_date,
            floor=floor,
            cache_dir=cache_dir,
        )
    except Exception:
        return None
    if data is None:
        return None
    if require_assets and not _cached_assets_ready(data, cache_dir=cache_dir):
        return None
    return data


def _cached_assets_ready(
    data: AbyssFloorSourceData,
    *,
    cache_dir: str | Path | None,
) -> bool:
    if not data.enemy_rows:
        return False
    icon_dir = cached_abyss_floor_monster_icon_dir(
        data.period.start_date,
        data.floor,
        cache_dir=cache_dir,
    )
    if not icon_dir.is_dir():
        return False
    for row in data.enemy_rows:
        if not row.cached_icon_path:
            return False
        if not Path(row.cached_icon_path).is_file():
            return False
    return True


def _cached_refresh_result(
    period: HoYoLABAbyssPeriod,
    data: AbyssFloorSourceData,
    *,
    floor: int,
    cache_dir: str | Path | None,
    cache_assets: bool,
    timings_ms: Mapping[str, Any] | None = None,
) -> AbyssSourceDataRefreshResult:
    path = cached_abyss_floor_source_data_path(
        period.start_date,
        floor=floor,
        cache_dir=cache_dir,
    )
    assets: dict[str, Any] = {"enabled": bool(cache_assets), "skipped": True}
    if cache_assets:
        assets["cache_dir"] = str(
            cached_abyss_floor_monster_icon_dir(
                period.start_date,
                floor=floor,
                cache_dir=cache_dir,
            )
        )
        assets["saved"] = sum(1 for row in data.enemy_rows if row.cached_icon_path)
        assets["failed"] = sum(1 for row in data.enemy_rows if not row.cached_icon_path)
    return AbyssSourceDataRefreshResult(
        period=period,
        floor=int(floor),
        cache_saved=False,
        cache_path=str(path),
        matched=data.matched_count,
        unmatched=data.unmatched_count,
        ambiguous=data.ambiguous_count,
        enemy_rows=len(data.enemy_rows),
        assets=assets,
        skipped=True,
        skip_reason=(
            "same_period_cache_and_assets_ready"
            if cache_assets
            else "same_period_cache_ready"
        ),
        warnings=tuple(data.global_warnings),
        timings_ms=dict(timings_ms or {}),
    )


def _period_from_mapping(
    value: Mapping[str, Any],
    *,
    source_path: str,
) -> HoYoLABAbyssPeriod | None:
    start_value = _first_mapping_value(value, _START_KEYS)
    end_value = _first_mapping_value(value, _END_KEYS)
    start_date = _extract_single_date(start_value)
    end_date = _extract_single_date(end_value)
    if not start_date or not end_date:
        return None
    return HoYoLABAbyssPeriod(
        raw_period=f"{start_date}/{end_date}",
        start_date=start_date,
        end_date=end_date,
        source_path=source_path,
    )


def _first_mapping_value(value: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    lower_items = {str(key).lower(): item for key, item in value.items()}
    for key in keys:
        if key in lower_items:
            return lower_items[key]
    return None


def _walk_payload(value: Any, path: str = "$") -> list[tuple[str, Any]]:
    items = [(path, value)]
    if isinstance(value, Mapping):
        for key, child in value.items():
            items.extend(_walk_payload(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            items.extend(_walk_payload(child, f"{path}[{index}]"))
    return items


def _extract_single_date(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        return _date_from_epoch_seconds(value)
    if not isinstance(value, str):
        return None
    match = _SINGLE_DATE_PATTERN.search(value)
    if match:
        return _normalize_date(match.group(0))
    stripped = value.strip()
    if re.fullmatch(r"\d{10,13}", stripped):
        try:
            return _date_from_epoch_seconds(float(stripped))
        except ValueError:
            return None
    return None


def _date_from_epoch_seconds(value: int | float) -> str | None:
    timestamp = float(value)
    if timestamp > 10_000_000_000:
        timestamp /= 1000
    try:
        return datetime.fromtimestamp(timestamp).date().isoformat()
    except (OSError, OverflowError, ValueError):
        return None


def _normalize_date(value: str) -> str:
    match = _SINGLE_DATE_PATTERN.search(value)
    if not match:
        raise HoYoLABAbyssPeriodError(f"Unsupported HoYoLAB Abyss date: {value!r}")
    return (
        f"{int(match.group('year')):04d}-"
        f"{int(match.group('month')):02d}-"
        f"{int(match.group('day')):02d}"
    )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _elapsed_ms(start: float) -> float:
    return round((perf_counter() - start) * 1000, 3)


def _compact_exception_summary(exc: BaseException) -> str:
    text = str(exc).split("Call log:", 1)[0].strip()
    if len(text) > 600:
        text = text[:600] + "..."
    return text or type(exc).__name__


async def _run_cli(args: argparse.Namespace) -> dict[str, Any]:
    period = await resolve_abyss_period_with_export_context(
        language=args.language,
        period_source=args.period_source,
    )
    report: dict[str, Any] = {
        "period": period.to_dict(),
        "periodPath": None,
        "sourceData": None,
    }
    if args.write_period:
        report["periodPath"] = str(write_hoyolab_abyss_period(period))
    if args.update_cache:
        summary, error = refresh_cached_abyss_source_data_for_hoyolab_period(
            period,
            floor=args.floor,
            cache_assets=not args.skip_assets,
            force=args.force,
            hp_source_mode=args.hp_source,
            hp_multiplier=args.hp_multiplier,
            fandom_hp_workers=args.fandom_hp_workers,
        )
        report["sourceData"] = summary
        report["sourceDataError"] = error
    return report


def _text_report(report: Mapping[str, Any]) -> str:
    period = report.get("period") if isinstance(report, Mapping) else {}
    if not isinstance(period, Mapping):
        period = {}
    lines = [
        "HoYoLAB Abyss source refresh",
        (
            f"period={period.get('rawPeriod')} "
            f"start={period.get('startDate')} end={period.get('endDate')}"
        ),
        (
            f"period_source={period.get('source')} "
            f"fallback={period.get('fallback')}"
        ),
    ]
    for warning in period.get("warnings") or []:
        lines.append(f"period_warning={warning}")
    if report.get("periodPath"):
        lines.append(f"period_path={report.get('periodPath')}")
    source_data = report.get("sourceData")
    if isinstance(source_data, Mapping):
        lines.append(
            "source_data="
            f"rows={source_data.get('enemyRows')} "
            f"matched={source_data.get('matched')} "
            f"cache={source_data.get('cachePath')} "
            f"skipped={source_data.get('skipped')}"
        )
        timings = source_data.get("timingsMs")
        if isinstance(timings, Mapping) and timings:
            total_ms = _optional_float(timings.get("total"))
            lines.append(
                "timings_ms="
                f"total={timings.get('total')} "
                f"fandom={timings.get('fandom_composition_fetch_parse')} "
                f"nanoka={timings.get('nanoka_source_fetch_parse')} "
                f"join={timings.get('join_build_source_data')} "
                f"hp_fallback={timings.get('fandom_enemy_page_hp_fallback')} "
                f"assets={timings.get('icon_asset_cache')} "
                f"cache={timings.get('json_cache_save')}"
            )
            if total_ms is not None:
                lines.append(f"elapsed_s={total_ms / 1000:.3f}")
    if report.get("sourceDataError"):
        lines.append(f"source_data_warning={report.get('sourceDataError')}")
    return "\n".join(lines)


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch the official HoYoLAB Spiral Abyss period and optionally "
            "refresh the local Floor 12 source-data cache."
        )
    )
    parser.add_argument("--write-period", action="store_true", help="Write data/hoyolab/spiral_abyss_period.json.")
    parser.add_argument("--update-cache", action="store_true", help="Refresh or reuse cached Floor 12 source data.")
    parser.add_argument("--force", action="store_true", help="Force source-data refresh even when the same-period cache/assets are ready.")
    parser.add_argument("--skip-assets", action="store_true", help="With --update-cache, skip monster icon asset caching.")
    parser.add_argument("--floor", type=int, default=12, help="Abyss floor to update. Default: 12.")
    parser.add_argument("--language", help="Optional HoYoLAB language override.")
    parser.add_argument(
        "--hp-source",
        choices=HP_FALLBACK_MODE_CHOICES,
        default=HP_FALLBACK_MODE_AUTO,
        help=(
            "Fact HP source for --update-cache. auto=Nanoka primary plus Fandom "
            "enemy-page fallback for missing HP; nanoka-only disables enemy-page "
            "fallback; fandom-only skips Nanoka HP and forces Fandom enemy-page HP. "
            "Default: auto."
        ),
    )
    parser.add_argument(
        "--hp-multiplier",
        type=float,
        default=DEFAULT_ABYSS_FANDOM_HP_MULTIPLIER,
        help=(
            "Manual Abyss HP multiplier for Fandom enemy-page HP fallback. "
            f"Default: {DEFAULT_ABYSS_FANDOM_HP_MULTIPLIER:g}."
        ),
    )
    parser.add_argument(
        "--fandom-hp-workers",
        type=int,
        default=DEFAULT_FANDOM_ENEMY_PAGE_WORKERS,
        help=(
            "Bounded parallel Fandom enemy-page HP fetch workers for --update-cache. "
            f"Default: {DEFAULT_FANDOM_ENEMY_PAGE_WORKERS}."
        ),
    )
    parser.add_argument(
        "--period-source",
        choices=PERIOD_SOURCE_CHOICES,
        default=PERIOD_SOURCE_AUTO,
        help="Period resolver source. Default: auto (HoYoLAB -> Fandom latest -> Nanoka live).",
    )
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main() -> int:
    parser = _build_argument_parser()
    args = parser.parse_args()
    try:
        report = asyncio.run(_run_cli(args))
    except Exception as exc:
        print(
            json.dumps(
                {"error": _compact_exception_summary(exc)},
                ensure_ascii=False,
                indent=args.indent,
            ),
            file=sys.stderr,
        )
        return 1
    if args.format == "text":
        print(_text_report(report))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=args.indent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
