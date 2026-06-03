from __future__ import annotations

import json
import re
from dataclasses import dataclass
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
    start_date = _date_text(payload.get("startDate") or payload.get("start_date"))
    if not start_date:
        return None
    return CachedAbyssPeriodRef(
        start_date=start_date,
        end_date=_date_text(payload.get("endDate") or payload.get("end_date")),
        raw_period=str(payload.get("rawPeriod") or payload.get("raw_period") or ""),
        source_path=str(payload.get("sourcePath") or payload.get("source_path") or ""),
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
    if not isinstance(value, str):
        return ""
    match = _DATE_PATTERN.search(value)
    return match.group(0) if match else ""
