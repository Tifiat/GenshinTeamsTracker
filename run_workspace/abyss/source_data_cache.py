"""Persistent cache for production Abyss source-data models."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .source_data import (
    AbyssChamberSideSourceData,
    AbyssEnemySourceRow,
    AbyssFloorSourceData,
    AbyssPeriod,
    AbyssWaveSourceData,
)


SCHEMA_VERSION = 1
DEFAULT_ABYSS_SOURCE_DATA_CACHE_DIR = Path("data/cache/abyss/source_data")

_PERIOD_START_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


class AbyssSourceDataCacheError(ValueError):
    """Raised when a cached Abyss source-data file is malformed."""


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
        warnings=_tuple_of_str(data.get("warnings", ()), "warnings"),
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
