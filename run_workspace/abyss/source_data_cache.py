"""Persistent cache for production Abyss source-data models."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import asdict
from dataclasses import replace
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from .source_data import (
    AbyssChamberSideSourceData,
    AbyssEnemySourceRow,
    AbyssFloorSourceData,
    AbyssPeriod,
    AbyssWaveSourceData,
    rebuild_abyss_floor_source_data_with_rows,
)


SCHEMA_VERSION = 1
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ABYSS_SOURCE_DATA_CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "abyss" / "source_data"
ICON_CACHE_USER_AGENT = "GenshinTeamsTracker-AbyssSourceDataIconCache/1.0"
SUPPORTED_ICON_EXTENSIONS = {".avif", ".gif", ".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_ICON_CACHE_WORKERS = 6

_PERIOD_START_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")

IconBytesFetcher = Callable[[str], bytes]


class AbyssSourceDataCacheError(ValueError):
    """Raised when a cached Abyss source-data file is malformed."""


@dataclass(frozen=True, slots=True)
class AbyssMonsterIconCacheEntry:
    row_index: int
    primary_display_name: str
    source_kind: str | None
    source_url: str | None
    cached_icon_path: str | None
    status: str
    warning: str | None = None


@dataclass(frozen=True, slots=True)
class IconCacheResult:
    data: AbyssFloorSourceData
    cache_dir: Path
    attempted: int
    saved: int
    failed: int
    downloaded: int
    cache_hits: int
    entries: tuple[AbyssMonsterIconCacheEntry, ...]
    warnings: tuple[str, ...] = ()


def cached_abyss_floor_source_data_path(
    period_start: str,
    floor: int = 12,
    *,
    cache_dir: str | Path | None = None,
) -> Path:
    """Return the cache file path for one Abyss period/floor."""

    normalized_period = _normalize_period_start(period_start)
    normalized_floor = _normalize_floor(floor)
    base_dir = Path(cache_dir) if cache_dir is not None else DEFAULT_ABYSS_SOURCE_DATA_CACHE_DIR
    return base_dir / normalized_period / f"floor_{normalized_floor}.json"


def cached_abyss_floor_monster_icon_dir(
    period_start: str,
    floor: int = 12,
    *,
    cache_dir: str | Path | None = None,
) -> Path:
    """Return the asset directory for monster icons tied to one period/floor."""

    source_path = cached_abyss_floor_source_data_path(
        period_start,
        floor,
        cache_dir=cache_dir,
    )
    return source_path.with_name(f"floor_{_normalize_floor(floor)}_assets") / "monster_icons"


def save_abyss_floor_source_data(
    data: AbyssFloorSourceData,
    *,
    cache_dir: str | Path | None = None,
) -> Path:
    """Save typed Abyss source data to the local JSON cache."""

    path = cached_abyss_floor_source_data_path(
        data.period.start_date,
        data.floor,
        cache_dir=cache_dir,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "abyss_floor_source_data",
        "cache_key": {
            "period_start": data.period.start_date,
            "floor": data.floor,
        },
        "saved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "data": asdict(data),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def cache_abyss_floor_monster_icons(
    data: AbyssFloorSourceData,
    *,
    cache_dir: str | Path | None = None,
    icon_fetcher: IconBytesFetcher | None = None,
    max_workers: int = DEFAULT_ICON_CACHE_WORKERS,
) -> IconCacheResult:
    """Cache local monster icons for source-data rows without fetching pages."""

    asset_dir = cached_abyss_floor_monster_icon_dir(
        data.period.start_date,
        data.floor,
        cache_dir=cache_dir,
    )
    asset_dir.mkdir(parents=True, exist_ok=True)
    fetcher = icon_fetcher or _fetch_url_bytes
    updated_rows: list[AbyssEnemySourceRow] = []
    entries: list[AbyssMonsterIconCacheEntry] = []
    global_warnings: list[str] = []
    downloaded = 0
    cache_hits = 0
    row_results: list[
        tuple[AbyssMonsterIconCacheEntry, AbyssEnemySourceRow, str | None] | None
    ] = [None] * len(data.enemy_rows)

    worker_count = max(1, min(int(max_workers or 1), len(data.enemy_rows) or 1))
    if worker_count == 1 or len(data.enemy_rows) <= 1:
        for row_index, row in enumerate(data.enemy_rows):
            row_results[row_index] = _cache_icon_for_row(
                row,
                row_index=row_index,
                asset_dir=asset_dir,
                fetcher=fetcher,
            )
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(
                    _cache_icon_for_row,
                    row,
                    row_index=row_index,
                    asset_dir=asset_dir,
                    fetcher=fetcher,
                ): row_index
                for row_index, row in enumerate(data.enemy_rows)
            }
            for future in as_completed(futures):
                row_results[futures[future]] = future.result()

    for row_result in row_results:
        if row_result is None:
            continue
        entry, updated_row, cache_state = row_result
        entries.append(entry)
        updated_rows.append(updated_row)
        if cache_state == "downloaded":
            downloaded += 1
        elif cache_state == "cache_hit":
            cache_hits += 1
        if entry.warning:
            global_warnings.append(entry.warning)

    saved = sum(1 for entry in entries if entry.cached_icon_path)
    failed = sum(1 for entry in entries if not entry.cached_icon_path)
    updated_data = rebuild_abyss_floor_source_data_with_rows(
        data,
        updated_rows,
        global_warnings=global_warnings,
    )
    return IconCacheResult(
        data=updated_data,
        cache_dir=asset_dir,
        attempted=len(entries),
        saved=saved,
        failed=failed,
        downloaded=downloaded,
        cache_hits=cache_hits,
        entries=tuple(entries),
        warnings=tuple(global_warnings),
    )


def load_cached_abyss_floor_source_data(
    period_start: str,
    floor: int = 12,
    *,
    cache_dir: str | Path | None = None,
) -> AbyssFloorSourceData | None:
    """Load typed Abyss source data from cache, or return None when missing."""

    path = cached_abyss_floor_source_data_path(period_start, floor, cache_dir=cache_dir)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AbyssSourceDataCacheError(f"Malformed Abyss source-data cache {path}: {exc}") from exc
    return _source_data_from_cache_payload(
        payload,
        expected_period_start=_normalize_period_start(period_start),
        expected_floor=_normalize_floor(floor),
        path=path,
    )


def has_cached_abyss_floor_source_data(
    period_start: str,
    floor: int = 12,
    *,
    cache_dir: str | Path | None = None,
) -> bool:
    """Return whether a cache file exists for one Abyss period/floor."""

    return cached_abyss_floor_source_data_path(
        period_start,
        floor,
        cache_dir=cache_dir,
    ).is_file()


def _normalize_period_start(period_start: str) -> str:
    normalized = str(period_start)
    if not _PERIOD_START_PATTERN.fullmatch(normalized):
        raise ValueError(f"Unsupported Abyss period_start for cache key: {period_start!r}")
    return normalized


def _normalize_floor(floor: int) -> int:
    try:
        normalized = int(floor)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Unsupported Abyss floor for cache key: {floor!r}") from exc
    if normalized <= 0:
        raise ValueError(f"Unsupported Abyss floor for cache key: {floor!r}")
    return normalized


def _source_data_from_cache_payload(
    payload: Any,
    *,
    expected_period_start: str,
    expected_floor: int,
    path: Path,
) -> AbyssFloorSourceData:
    if not isinstance(payload, Mapping):
        raise AbyssSourceDataCacheError(f"Malformed Abyss source-data cache {path}: root is not an object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise AbyssSourceDataCacheError(
            f"Unsupported Abyss source-data cache schema in {path}: {payload.get('schema_version')!r}"
        )
    if payload.get("kind") != "abyss_floor_source_data":
        raise AbyssSourceDataCacheError(f"Malformed Abyss source-data cache {path}: unsupported kind")
    cache_key = _require_mapping(payload.get("cache_key"), path, "cache_key")
    period_start = str(cache_key.get("period_start") or "")
    floor = _as_int(cache_key.get("floor"))
    if period_start != expected_period_start or floor != expected_floor:
        raise AbyssSourceDataCacheError(
            "Abyss source-data cache key mismatch in "
            f"{path}: expected {expected_period_start}/floor_{expected_floor}, "
            f"got {period_start}/floor_{floor}"
        )
    data = _require_mapping(payload.get("data"), path, "data")
    try:
        return _source_data_from_mapping(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise AbyssSourceDataCacheError(f"Malformed Abyss source-data cache {path}: {exc}") from exc


def _source_data_from_mapping(data: Mapping[str, Any]) -> AbyssFloorSourceData:
    floor = _as_int(data["floor"])
    if floor is None:
        raise ValueError("data.floor is missing")
    period = _period_from_mapping(_require_mapping(data["period"], None, "period"))
    enemy_rows = tuple(
        _enemy_row_from_mapping(_require_mapping(row, None, "enemy_rows[]"))
        for row in _as_sequence(data.get("enemy_rows"), "enemy_rows")
    )
    side_summaries = tuple(
        _side_summary_from_mapping(_require_mapping(summary, None, "side_summaries[]"))
        for summary in _as_sequence(data.get("side_summaries"), "side_summaries")
    )
    return AbyssFloorSourceData(
        floor=floor,
        period=period,
        source_urls=dict(_require_mapping(data.get("source_urls"), None, "source_urls")),
        enemy_rows=enemy_rows,
        side_summaries=side_summaries,
        global_warnings=_tuple_of_str(data.get("global_warnings", ()), "global_warnings"),
    )


def _period_from_mapping(data: Mapping[str, Any]) -> AbyssPeriod:
    return AbyssPeriod(
        start_date=str(data["start_date"]),
        end_date=_optional_str(data.get("end_date")),
        source=str(data["source"]),
    )


def _enemy_row_from_mapping(data: Mapping[str, Any]) -> AbyssEnemySourceRow:
    warnings = list(_tuple_of_str(data.get("warnings", ()), "warnings"))
    cached_icon_path = _validated_cached_icon_path(
        data.get("cached_icon_path"),
        warnings,
    )
    return AbyssEnemySourceRow(
        floor=_required_int(data, "floor"),
        chamber=_required_int(data, "chamber"),
        side=_required_int(data, "side"),
        side_name=str(data["side_name"]),
        wave=_required_int(data, "wave"),
        enemy_count=_required_int(data, "enemy_count"),
        display_level=_optional_int(data.get("display_level")),
        primary_display_name=str(data["primary_display_name"]),
        fandom_enemy_page_url=_optional_str(data.get("fandom_enemy_page_url")),
        fandom_icon_url=_optional_str(data.get("fandom_icon_url")),
        matched_nanoka_display_name=_optional_str(data.get("matched_nanoka_display_name")),
        nanoka_monster_id=_optional_str(data.get("nanoka_monster_id")),
        nanoka_icon_url=_optional_str(data.get("nanoka_icon_url")),
        nanoka_enemy_detail_url=_optional_str(data.get("nanoka_enemy_detail_url")),
        nanoka_hp=_optional_int(data.get("nanoka_hp")),
        hp_source=str(data["hp_source"]),
        match_method=str(data["match_method"]),
        match_confidence=str(data["match_confidence"]),
        warnings=tuple(warnings),
        cached_icon_path=cached_icon_path,
    )


def _wave_from_mapping(data: Mapping[str, Any]) -> AbyssWaveSourceData:
    return AbyssWaveSourceData(
        wave=_required_int(data, "wave"),
        enemies=tuple(
            _enemy_row_from_mapping(_require_mapping(row, None, "wave.enemies[]"))
            for row in _as_sequence(data.get("enemies"), "wave.enemies")
        ),
        solo_target_hp=_optional_int(data.get("solo_target_hp")),
        multi_target_hp=_optional_int(data.get("multi_target_hp")),
        selected_solo_enemy_name=_optional_str(data.get("selected_solo_enemy_name")),
        warnings=_tuple_of_str(data.get("warnings", ()), "wave.warnings"),
    )


def _side_summary_from_mapping(data: Mapping[str, Any]) -> AbyssChamberSideSourceData:
    return AbyssChamberSideSourceData(
        floor=_required_int(data, "floor"),
        chamber=_required_int(data, "chamber"),
        side=_required_int(data, "side"),
        side_name=str(data["side_name"]),
        waves=tuple(
            _wave_from_mapping(_require_mapping(wave, None, "side.waves[]"))
            for wave in _as_sequence(data.get("waves"), "side.waves")
        ),
        solo_target_hp=_optional_int(data.get("solo_target_hp")),
        multi_target_hp=_optional_int(data.get("multi_target_hp")),
        warnings=_tuple_of_str(data.get("warnings", ()), "side.warnings"),
    )


def _require_mapping(value: Any, path: Path | None, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        location = f" in {path}" if path is not None else ""
        raise AbyssSourceDataCacheError(f"Malformed Abyss source-data cache{location}: {field} is not an object")
    return value


def _as_sequence(value: Any, field: str) -> list[Any] | tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} is not a list")
    return value


def _tuple_of_str(value: Any, field: str) -> tuple[str, ...]:
    sequence = _as_sequence(value, field)
    return tuple(str(item) for item in sequence)


def _required_int(data: Mapping[str, Any], key: str) -> int:
    value = _as_int(data[key])
    if value is None:
        raise ValueError(f"{key} is missing")
    return value


def _optional_int(value: Any) -> int | None:
    return _as_int(value)


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _validated_cached_icon_path(value: Any, warnings: list[str]) -> str | None:
    text = _optional_str(value)
    if text is None:
        return None
    if not Path(text).is_file():
        warnings.append("cached_icon_file_missing")
        return None
    return text


def _cache_icon_for_row(
    row: AbyssEnemySourceRow,
    *,
    row_index: int,
    asset_dir: Path,
    fetcher: IconBytesFetcher,
) -> tuple[AbyssMonsterIconCacheEntry, AbyssEnemySourceRow, str | None]:
    candidates = [
        ("nanoka", row.nanoka_icon_url),
        ("fandom", row.fandom_icon_url),
    ]
    source_failures: list[str] = []
    usable_candidates = [
        (source_kind, source_url)
        for source_kind, source_url in candidates
        if source_url
    ]
    if not usable_candidates:
        warning = "monster_icon_url_missing"
        return (
            AbyssMonsterIconCacheEntry(
                row_index=row_index,
                primary_display_name=row.primary_display_name,
                source_kind=None,
                source_url=None,
                cached_icon_path=None,
                status="missing_source_url",
                warning=warning,
            ),
            _row_with_icon_cache_warning(row, warning),
            None,
        )

    for source_kind, source_url in usable_candidates:
        target_path = _monster_icon_cache_path(row, source_url, asset_dir=asset_dir)
        if target_path.is_file():
            warning = _fallback_warning(source_kind, source_failures)
            return (
                AbyssMonsterIconCacheEntry(
                    row_index=row_index,
                    primary_display_name=row.primary_display_name,
                    source_kind=source_kind,
                    source_url=source_url,
                    cached_icon_path=str(target_path),
                    status="cache_hit",
                    warning=warning,
                ),
                _row_with_cached_icon(row, target_path, warning),
                "cache_hit",
            )
        try:
            content = fetcher(source_url)
            if not content:
                raise AbyssSourceDataCacheError("Downloaded icon payload is empty")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(content)
        except Exception as exc:  # noqa: BLE001 - cache failures must not break source data.
            source_failures.append(f"{source_kind}_icon_cache_failed")
            last_error = str(exc)
            continue
        warning = _fallback_warning(source_kind, source_failures)
        return (
            AbyssMonsterIconCacheEntry(
                row_index=row_index,
                primary_display_name=row.primary_display_name,
                source_kind=source_kind,
                source_url=source_url,
                cached_icon_path=str(target_path),
                status="downloaded",
                warning=warning,
            ),
            _row_with_cached_icon(row, target_path, warning),
            "downloaded",
        )

    warning = "monster_icon_cache_failed"
    if source_failures:
        warning = f"{warning}:{','.join(source_failures)}"
    if "last_error" in locals() and last_error:
        entry_warning = f"{warning}:{last_error}"
    else:
        entry_warning = warning
    return (
        AbyssMonsterIconCacheEntry(
            row_index=row_index,
            primary_display_name=row.primary_display_name,
            source_kind=usable_candidates[-1][0],
            source_url=usable_candidates[-1][1],
            cached_icon_path=None,
            status="failed",
            warning=entry_warning,
        ),
        _row_with_icon_cache_warning(row, warning),
        None,
    )


def _row_with_cached_icon(
    row: AbyssEnemySourceRow,
    path: Path,
    warning: str | None,
) -> AbyssEnemySourceRow:
    warnings = row.warnings
    if warning:
        warnings = (*warnings, warning)
    return replace(row, cached_icon_path=str(path), warnings=warnings)


def _row_with_icon_cache_warning(
    row: AbyssEnemySourceRow,
    warning: str,
) -> AbyssEnemySourceRow:
    return replace(row, cached_icon_path=None, warnings=(*row.warnings, warning))


def _fallback_warning(source_kind: str, failures: list[str]) -> str | None:
    if source_kind == "fandom" and failures:
        return "nanoka_icon_cache_failed_used_fandom_icon"
    return None


def _monster_icon_cache_path(
    row: AbyssEnemySourceRow,
    source_url: str,
    *,
    asset_dir: Path,
) -> Path:
    stable_id = _safe_filename_part(
        row.nanoka_monster_id or row.primary_display_name or "monster"
    )
    digest = sha1(source_url.encode("utf-8")).hexdigest()[:12]
    extension = _source_url_extension(source_url)
    return asset_dir / f"{stable_id}_{digest}{extension}"


def _safe_filename_part(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._-")
    return normalized[:80] or "monster"


def _source_url_extension(source_url: str) -> str:
    suffix = Path(unquote(urlparse(source_url).path)).suffix.lower()
    return suffix if suffix in SUPPORTED_ICON_EXTENSIONS else ".img"


def _fetch_url_bytes(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*,*/*;q=0.8",
            "User-Agent": ICON_CACHE_USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise AbyssSourceDataCacheError(f"Failed to fetch icon {url}: {exc}") from exc
