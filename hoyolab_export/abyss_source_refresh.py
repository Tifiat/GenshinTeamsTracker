from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.parse import urlencode

from run_workspace.abyss.source_data_update import build_update_report

from .character_detail import ROLES_URL, browser_fetch_json, pick_genshin_role


SPIRAL_ABYSS_URL = (
    "https://sg-public-api.hoyolab.com/event/game_record/genshin/api/spiralAbyss"
)

_DATE_PATTERN = r"\d{4}[/-]\d{1,2}[/-]\d{1,2}"
_NAMED_DATE_PATTERN = r"(?P<year>\d{4})[/-](?P<month>\d{1,2})[/-](?P<day>\d{1,2})"
_PERIOD_PATTERN = re.compile(
    rf"(?P<start>{_DATE_PATTERN})\s*(?:-|--|~|to|until|through|–|—)\s*"
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "rawPeriod": self.raw_period,
            "startDate": self.start_date,
            "endDate": self.end_date,
            "sourcePath": self.source_path,
            "source": self.source,
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
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period.to_dict(),
            "floor": self.floor,
            "cacheSaved": self.cache_saved,
            "cachePath": self.cache_path,
            "matched": self.matched,
            "unmatched": self.unmatched,
            "ambiguous": self.ambiguous,
            "enemyRows": self.enemy_rows,
            "assets": dict(self.assets),
            "warnings": list(self.warnings),
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

    roles_result = await browser_fetch_json(page, ROLES_URL, language=language)
    role_id, server = pick_genshin_role(roles_result.get("json") or {})
    query = urlencode(
        {
            "server": server,
            "role_id": role_id,
            "schedule_type": int(schedule_type),
        }
    )
    response = await browser_fetch_json(
        page,
        f"{SPIRAL_ABYSS_URL}?{query}",
        language=language,
    )
    payload = response.get("json") or {}
    retcode = payload.get("retcode")
    if retcode not in (None, 0):
        message = payload.get("message") or payload.get("msg") or "unknown error"
        raise HoYoLABAbyssPeriodError(
            f"HoYoLAB Spiral Abyss overview failed: retcode={retcode} message={message}"
        )
    return extract_hoyolab_abyss_period(payload)


def update_cached_abyss_source_data_for_hoyolab_period(
    period: HoYoLABAbyssPeriod | str,
    *,
    floor: int = 12,
    cache_dir: str | None = None,
    cache_assets: bool = True,
    update_report_builder: Callable[..., Mapping[str, Any]] | None = None,
) -> AbyssSourceDataRefreshResult:
    """Update Floor 12 source-data cache from an official HoYoLAB Abyss period."""

    parsed = _coerce_period(period)
    builder = update_report_builder or build_update_report
    report = builder(
        period_start=parsed.start_date,
        period_end=parsed.end_date,
        floor=floor,
        save_cache=True,
        cache_dir=cache_dir,
        cache_assets=cache_assets,
    )
    summary = report.get("summary") if isinstance(report, Mapping) else {}
    cache = report.get("cache") if isinstance(report, Mapping) else {}
    assets = report.get("assets") if isinstance(report, Mapping) else {}
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
        warnings=tuple(warnings),
    )


def refresh_cached_abyss_source_data_for_hoyolab_period(
    period: HoYoLABAbyssPeriod | str | None,
    *,
    floor: int = 12,
    cache_dir: str | None = None,
    cache_assets: bool = True,
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
        )
    except Exception as exc:
        return None, _compact_exception_summary(exc)
    return result.to_dict(), None


def _coerce_period(period: HoYoLABAbyssPeriod | str) -> HoYoLABAbyssPeriod:
    if isinstance(period, HoYoLABAbyssPeriod):
        return period
    return parse_hoyolab_abyss_period(str(period))


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
    if not isinstance(value, str):
        return None
    match = _SINGLE_DATE_PATTERN.search(value)
    if not match:
        return None
    return _normalize_date(match.group(0))


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


def _compact_exception_summary(exc: BaseException) -> str:
    text = str(exc).split("Call log:", 1)[0].strip()
    if len(text) > 600:
        text = text[:600] + "..."
    return text or type(exc).__name__
