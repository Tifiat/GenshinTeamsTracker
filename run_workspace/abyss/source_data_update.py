"""Debug CLI for production-safe Abyss source-data updates.

This module fetches one Fandom period page, resolves Nanoka's internal tower id
from the period when needed, and builds `AbyssFloorSourceData`. Cache writes
are explicit opt-in; this module does not touch UI and does not fetch
individual Fandom enemy pages during the normal Nanoka path.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from typing import Any

from .source_data import (
    AbyssFloorSourceData,
    load_abyss_floor12_source_data,
    period_url_for_start,
)
from .source_data_cache import save_abyss_floor_source_data
from .source_data_fetchers import (
    AbyssSourceFetchError,
    NanokaTowerPeriodAmbiguous,
    fetch_fandom_composition_report,
    fetch_nanoka_tower_report,
    fetch_nanoka_tower_report_for_period,
)


def fetch_abyss_floor12_source_data(
    *,
    period_start: str,
    tower_id: str | None = None,
    floor: int = 12,
    locale: str = "en",
    period_end: str | None = None,
) -> AbyssFloorSourceData:
    """Fetch live source reports and build production Floor 12 source data."""

    period_url = period_url_for_start(period_start)
    composition_report = fetch_fandom_composition_report(period_url, floor=floor)
    try:
        if tower_id is not None:
            nanoka_report: dict[str, Any] | None = fetch_nanoka_tower_report(
                tower_id,
                floor=floor,
                locale=locale,
            )
        else:
            nanoka_report = fetch_nanoka_tower_report_for_period(
                period_start,
                period_end=period_end,
                floor=floor,
                locale=locale,
            )
    except NanokaTowerPeriodAmbiguous:
        raise
    except AbyssSourceFetchError as exc:
        nanoka_report = {
            "probe": {
                "name": "nanoka_abyss_tower_source_fetch",
                "production_safe_debug": True,
                "warnings": [f"nanoka_fetch_failed:{exc}"],
            },
            "towers": [],
        }
    resolved_tower_id = _resolved_nanoka_tower_id(nanoka_report) or tower_id or "unresolved"
    return load_abyss_floor12_source_data(
        period_start,
        resolved_tower_id,
        floor=floor,
        composition_report=composition_report,
        nanoka_report=nanoka_report,
    )


def _summary(data: AbyssFloorSourceData) -> dict[str, Any]:
    return {
        "floor": data.floor,
        "period_start": data.period.start_date,
        "period_end": data.period.end_date,
        "enemy_rows": len(data.enemy_rows),
        "matched": data.matched_count,
        "unmatched": data.unmatched_count,
        "ambiguous": data.ambiguous_count,
        "side_count": len(data.side_summaries),
        "warnings": list(data.global_warnings),
    }


def build_update_report(
    *,
    period_start: str,
    tower_id: str | None = None,
    floor: int = 12,
    locale: str = "en",
    period_end: str | None = None,
    save_cache: bool = False,
    cache_dir: str | None = None,
) -> dict[str, Any]:
    data = fetch_abyss_floor12_source_data(
        period_start=period_start,
        tower_id=tower_id,
        floor=floor,
        locale=locale,
        period_end=period_end,
    )
    cache_report: dict[str, Any] = {"saved": False}
    if save_cache:
        saved_path = save_abyss_floor_source_data(data, cache_dir=cache_dir)
        cache_report = {
            "saved": True,
            "path": str(saved_path),
            "schema_version": 1,
        }
    return {
        "probe": {
            "name": "abyss_source_data_update",
            "production_safe_debug": True,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "normal_path_contract": {
                "fandom_period_parse_requests": 1,
                "nanoka_tower_manifest_requests": 1 if tower_id is None else 0,
                "nanoka_tower_detail_json_requests": 1,
                "fandom_enemy_page_requests": 0,
                "fandom_enemy_page_fallback_enabled": False,
            },
            "warnings": [
                "Debug/update entrypoint only; no UI, persistence, history, Account/Data import, or GCSIM wiring.",
                "Fandom period page is the composition/wave/count source.",
                "Nanoka tower JSON is the primary resolved HP/id/icon/detail source.",
                "Fandom enemy-page HP fallback is intentionally not run here.",
            ],
        },
        "inputs": {
            "period_start": period_start,
            "period_end": period_end,
            "tower_id": str(tower_id) if tower_id is not None else None,
            "tower_id_input_mode": "explicit_debug_override"
            if tower_id is not None
            else "period_lookup",
            "floor": floor,
            "locale": locale,
        },
        "nanoka": _nanoka_debug_metadata(data),
        "summary": _summary(data),
        "cache": cache_report,
        "source_data": asdict(data),
    }


def _resolved_nanoka_tower_id(nanoka_report: dict[str, Any] | None) -> str | None:
    if not isinstance(nanoka_report, dict):
        return None
    towers = nanoka_report.get("towers")
    if not isinstance(towers, list) or not towers:
        return None
    tower = towers[0]
    if not isinstance(tower, dict):
        return None
    tower_id = tower.get("tower_id")
    return str(tower_id) if tower_id not in (None, "") else None


def _nanoka_debug_metadata(data: AbyssFloorSourceData) -> dict[str, Any]:
    page_url = data.source_urls.get("nanoka_page_url")
    resolved_tower_id = None
    if page_url:
        resolved_tower_id = page_url.rstrip("/").rsplit("/", 1)[-1]
        if resolved_tower_id == "tower":
            resolved_tower_id = None
    return {
        "resolved_tower_id": resolved_tower_id,
        "source_urls": {
            key: value
            for key, value in data.source_urls.items()
            if key.startswith("nanoka_")
        },
    }


def _text_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "Abyss source-data update",
        (
            f"period={summary['period_start']} floor={summary['floor']} "
            f"rows={summary['enemy_rows']} matched={summary['matched']} "
            f"unmatched={summary['unmatched']} ambiguous={summary['ambiguous']}"
        ),
    ]
    for warning in summary.get("warnings", []):
        lines.append(f"warning: {warning}")
    cache_report = report.get("cache", {})
    if cache_report.get("saved"):
        lines.append(f"cache_saved={cache_report.get('path')}")
    return "\n".join(lines)


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch Fandom composition + Nanoka tower HP into production "
            "AbyssFloorSourceData and print a debug report."
        )
    )
    parser.add_argument("--period-start", required=True, help="Abyss period start date YYYY-MM-DD.")
    parser.add_argument(
        "--tower-id",
        help="Optional debug override for Nanoka's internal tower id, for example 119.",
    )
    parser.add_argument(
        "--period-end",
        help="Optional period end date YYYY-MM-DD for stricter Nanoka manifest lookup.",
    )
    parser.add_argument("--floor", type=int, default=12, help="Floor to fetch. Default: 12.")
    parser.add_argument("--locale", default="en", help="Nanoka static JSON locale. Default: en.")
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="Output format. Default: json.",
    )
    parser.add_argument(
        "--save-cache",
        action="store_true",
        help="Save the fetched AbyssFloorSourceData to the local source-data cache.",
    )
    parser.add_argument(
        "--cache-dir",
        help="Optional cache directory override for --save-cache.",
    )
    parser.add_argument("--indent", type=int, default=2, help="JSON indentation. Default: 2.")
    return parser


def main() -> int:
    parser = _build_argument_parser()
    args = parser.parse_args()
    try:
        report = build_update_report(
            period_start=args.period_start,
            tower_id=args.tower_id,
            floor=args.floor,
            locale=args.locale,
            period_end=args.period_end,
            save_cache=args.save_cache,
            cache_dir=args.cache_dir,
        )
    except AbyssSourceFetchError as exc:
        print(
            json.dumps(
                {
                    "probe": {
                        "name": "abyss_source_data_update",
                        "production_safe_debug": True,
                    },
                    "error": str(exc),
                },
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
