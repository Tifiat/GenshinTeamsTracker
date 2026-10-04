from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from .source_data import AbyssFloorSourceData
from .source_data_cache import (
    AbyssSourceDataCacheError,
    load_cached_abyss_floor_source_data,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH = (
    PROJECT_ROOT / "data" / "hoyolab" / "spiral_abyss_period.json"
)

_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True, slots=True)
class CachedAbyssPeriodRef:
    start_date: str
    end_date: str | None = None
    raw_period: str = ""
    source_path: str = ""
    source: str = ""
    fallback: bool | None = None
    warnings: tuple[str, ...] = ()


def read_cached_hoyolab_abyss_period(
    period_path: str | Path | None = None,
) -> CachedAbyssPeriodRef | None:
    """Read the official HoYoLAB Abyss period captured by Account/Data import."""

    path = Path(period_path) if period_path is not None else DEFAULT_HOYOLAB_ABYSS_PERIOD_PATH
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    start_date = _date_text(_first_present(payload, "startDate", "start_date"))
    if not start_date:
        return None
    end_value = _first_present(payload, "endDate", "end_date")
    raw_period = _first_present(payload, "rawPeriod", "raw_period", default="")
    source_path = _first_present(payload, "sourcePath", "source_path", default="")
    source = payload.get("source", "")
    fallback = payload.get("fallback")
    raw_warnings = payload.get("warnings", ())
    warnings = _warning_texts(raw_warnings)
    return CachedAbyssPeriodRef(
        start_date=start_date,
        end_date=_date_text(end_value) if end_value is not None else None,
        raw_period=raw_period if type(raw_period) is str else "",
        source_path=source_path if type(source_path) is str else "",
        source=source if type(source) is str else "",
        fallback=fallback if type(fallback) is bool else None,
        warnings=warnings,
    )


def load_current_cached_abyss_floor_source_data(
    *,
    floor: int = 12,
    period_path: str | Path | None = None,
    cache_dir: str | Path | None = None,
) -> AbyssFloorSourceData | None:
    """Load cached source data for the latest official HoYoLAB Abyss period."""

    period = read_cached_hoyolab_abyss_period(period_path)
    if period is None:
        return None
    try:
        return load_cached_abyss_floor_source_data(
            period.start_date,
            floor=floor,
            cache_dir=cache_dir,
        )
    except (AbyssSourceDataCacheError, ValueError, OSError):
        return None


def _date_text(value: Any) -> str:
    if type(value) is not str or not _DATE_PATTERN.fullmatch(value):
        return ""
    try:
        date.fromisoformat(value)
    except ValueError:
        return ""
    return value


def _first_present(
    payload: Mapping[str, Any],
    primary_key: str,
    alternate_key: str,
    *,
    default: Any = None,
) -> Any:
    if primary_key in payload:
        return payload[primary_key]
    if alternate_key in payload:
        return payload[alternate_key]
    return default


def _warning_texts(value: Any) -> tuple[str, ...]:
    if isinstance(value, list) and all(type(item) is str for item in value):
        return tuple(value)
    if value == ():
        return ()
    return ("invalid_warnings_metadata",)
