"""Debug CLI for production-safe Abyss source-data updates.

This module fetches one Fandom period page and one Nanoka tower data path, then
builds `AbyssFloorSourceData`. It does not persist data, does not touch UI, and
does not fetch individual Fandom enemy pages during the normal Nanoka path.
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
from .source_data_fetchers import (
    AbyssSourceFetchError,
    fetch_fandom_composition_report,
    fetch_nanoka_tower_report,
)


def fetch_abyss_floor12_source_data(
    *,
    period_start: str,
    tower_id: str,
    floor: int = 12,
    locale: str = "en",
) -> AbyssFloorSourceData:
    """Fetch live source reports and build production Floor 12 source data."""

    period_url = period_url_for_start(period_start)
    composition_report = fetch_fandom_composition_report(period_url, floor=floor)
    try:
        nanoka_report: dict[str, Any] | None = fetch_nanoka_tower_report(
            tower_id,
            floor=floor,
            locale=locale,
        )
    except AbyssSourceFetchError as exc:
        nanoka_report = {
            "probe": {
                "name": "nanoka_abyss_tower_source_fetch",
                "production_safe_debug": True,
                "warnings": [f"nanoka_fetch_failed:{exc}"],
            },
            "towers": [],
        }
    return load_abyss_floor12_source_data(
        period_start,
        tower_id,
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
    tower_id: str,
    floor: int = 12,
    locale: str = "en",
) -> dict[str, Any]:
    data = fetch_abyss_floor12_source_data(
        period_start=period_start,
        tower_id=tower_id,
        floor=floor,
        locale=locale,
    )
    return {
        "probe": {
            "name": "abyss_source_data_update",
            "production_safe_debug": True,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "normal_path_contract": {
                "fandom_period_parse_requests": 1,
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
            "tower_id": str(tower_id),
            "floor": floor,
            "locale": locale,
        },
        "summary": _summary(data),
        "source_data": asdict(data),
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
    return "\n".join(lines)


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch Fandom composition + Nanoka tower HP into production "
            "AbyssFloorSourceData and print a debug report."
        )
    )
    parser.add_argument("--period-start", required=True, help="Abyss period start date YYYY-MM-DD.")
    parser.add_argument("--tower-id", required=True, help="Nanoka tower id, for example 119.")
    parser.add_argument("--floor", type=int, default=12, help="Floor to fetch. Default: 12.")
    parser.add_argument("--locale", default="en", help="Nanoka static JSON locale. Default: en.")
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="Output format. Default: json.",
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
