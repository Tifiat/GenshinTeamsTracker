"""Debug CLI for production-safe Abyss source-data updates.

This module fetches one Fandom period page, resolves Nanoka's internal tower id
from the period when needed, and builds `AbyssFloorSourceData`. Cache writes
are explicit opt-in; this module does not touch UI. Fandom enemy-page HP
fallback runs only when explicitly forced or when Nanoka leaves HP unavailable.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from time import perf_counter
from typing import Any

from .source_data import (
    AbyssFloorSourceData,
    load_abyss_floor12_source_data,
    period_url_for_start,
)
from .fandom_enemy_hp_fallback import (
    DEFAULT_ABYSS_FANDOM_HP_MULTIPLIER,
    DEFAULT_FANDOM_ENEMY_PAGE_WORKERS,
    HP_FALLBACK_MODE_AUTO,
    HP_FALLBACK_MODE_CHOICES,
    HP_FALLBACK_MODE_FANDOM_ONLY,
    HP_FALLBACK_MODE_NANOKA_ONLY,
    apply_fandom_enemy_page_hp_fallback,
    normalize_hp_fallback_mode,
)
from .source_data_cache import (
    IconCacheResult,
    cache_abyss_floor_monster_icons,
    save_abyss_floor_source_data,
)
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
    hp_source_mode: str = HP_FALLBACK_MODE_AUTO,
    hp_multiplier: float = DEFAULT_ABYSS_FANDOM_HP_MULTIPLIER,
    fandom_hp_workers: int = DEFAULT_FANDOM_ENEMY_PAGE_WORKERS,
) -> AbyssFloorSourceData:
    """Fetch live source reports and build production Floor 12 source data."""

    data, _timings = _fetch_abyss_floor12_source_data_with_timings(
        period_start=period_start,
        tower_id=tower_id,
        floor=floor,
        locale=locale,
        period_end=period_end,
        hp_source_mode=hp_source_mode,
        hp_multiplier=hp_multiplier,
        fandom_hp_workers=fandom_hp_workers,
    )
    return data


def _fetch_abyss_floor12_source_data_with_timings(
    *,
    period_start: str,
    tower_id: str | None = None,
    floor: int = 12,
    locale: str = "en",
    period_end: str | None = None,
    hp_source_mode: str = HP_FALLBACK_MODE_AUTO,
    hp_multiplier: float = DEFAULT_ABYSS_FANDOM_HP_MULTIPLIER,
    fandom_hp_workers: int = DEFAULT_FANDOM_ENEMY_PAGE_WORKERS,
) -> tuple[AbyssFloorSourceData, dict[str, float]]:
    timings: dict[str, float] = {}
    normalized_hp_mode = normalize_hp_fallback_mode(hp_source_mode)
    normalized_workers = _normalize_worker_count(fandom_hp_workers)
    period_url = period_url_for_start(period_start)
    fandom_start = perf_counter()
    composition_report = fetch_fandom_composition_report(period_url, floor=floor)
    timings["fandom_composition_fetch_parse"] = _elapsed_ms(fandom_start)
    timings.update(_prefixed_timings("fandom", composition_report))
    nanoka_report: dict[str, Any] | None = None
    try:
        nanoka_start = perf_counter()
        if normalized_hp_mode == HP_FALLBACK_MODE_FANDOM_ONLY:
            nanoka_report = {
                "probe": {
                    "name": "nanoka_abyss_tower_source_fetch",
                    "production_safe_debug": True,
                    "warnings": ["nanoka_skipped_for_forced_fandom_enemy_page_hp_fallback"],
                },
                "towers": [],
            }
        elif tower_id is not None:
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
        timings["nanoka_source_fetch_parse"] = _elapsed_ms(nanoka_start)
        timings.update(_prefixed_timings("nanoka", nanoka_report))
    except NanokaTowerPeriodAmbiguous as exc:
        timings["nanoka_source_fetch_parse"] = _elapsed_ms(nanoka_start)
        if normalized_hp_mode == HP_FALLBACK_MODE_NANOKA_ONLY:
            raise
        nanoka_report = {
            "probe": {
                "name": "nanoka_abyss_tower_source_fetch",
                "production_safe_debug": True,
                "warnings": [f"nanoka_period_ambiguous_falling_back_to_fandom_enemy_page_hp:{exc}"],
            },
            "towers": [],
        }
    except AbyssSourceFetchError as exc:
        timings["nanoka_source_fetch_parse"] = _elapsed_ms(nanoka_start)
        nanoka_report = {
            "probe": {
                "name": "nanoka_abyss_tower_source_fetch",
                "production_safe_debug": True,
                "warnings": [f"nanoka_fetch_failed:{exc}"],
            },
            "towers": [],
        }
    resolved_tower_id = _resolved_nanoka_tower_id(nanoka_report) or tower_id or "unresolved"
    build_start = perf_counter()
    data = load_abyss_floor12_source_data(
        period_start,
        resolved_tower_id,
        floor=floor,
        composition_report=composition_report,
        nanoka_report=nanoka_report,
    )
    timings["join_build_source_data"] = _elapsed_ms(build_start)
    fallback_start = perf_counter()
    fallback_result = apply_fandom_enemy_page_hp_fallback(
        data,
        hp_multiplier=hp_multiplier,
        mode=normalized_hp_mode,
        enemy_page_workers=normalized_workers,
    )
    timings["fandom_enemy_page_hp_fallback"] = _elapsed_ms(fallback_start)
    timings["fandom_enemy_page_hp_fallback_requests"] = float(fallback_result.page_fetches)
    timings["fandom_enemy_page_hp_fallback_attempted"] = float(fallback_result.attempted)
    data = fallback_result.data
    return data, timings


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
    cache_assets: bool = True,
    hp_source_mode: str = HP_FALLBACK_MODE_AUTO,
    hp_multiplier: float = DEFAULT_ABYSS_FANDOM_HP_MULTIPLIER,
    fandom_hp_workers: int = DEFAULT_FANDOM_ENEMY_PAGE_WORKERS,
) -> dict[str, Any]:
    total_start = perf_counter()
    normalized_hp_mode = normalize_hp_fallback_mode(hp_source_mode)
    normalized_workers = _normalize_worker_count(fandom_hp_workers)
    data, timings = _fetch_abyss_floor12_source_data_with_timings(
        period_start=period_start,
        tower_id=tower_id,
        floor=floor,
        locale=locale,
        period_end=period_end,
        hp_source_mode=normalized_hp_mode,
        hp_multiplier=hp_multiplier,
        fandom_hp_workers=normalized_workers,
    )
    cache_report: dict[str, Any] = {"saved": False}
    asset_report: dict[str, Any] = {"enabled": False}
    report_data = data
    if save_cache:
        if cache_assets:
            asset_start = perf_counter()
            asset_result = cache_abyss_floor_monster_icons(data, cache_dir=cache_dir)
            timings["icon_asset_cache"] = _elapsed_ms(asset_start)
            report_data = asset_result.data
            asset_report = _asset_cache_report(asset_result)
        else:
            asset_report = {"enabled": False, "skipped": True}
            timings["icon_asset_cache"] = 0.0
        cache_start = perf_counter()
        saved_path = save_abyss_floor_source_data(report_data, cache_dir=cache_dir)
        timings["json_cache_save"] = _elapsed_ms(cache_start)
        cache_report = {
            "saved": True,
            "path": str(saved_path),
            "schema_version": 1,
        }
    else:
        timings["icon_asset_cache"] = 0.0
        timings["json_cache_save"] = 0.0
    timings["total"] = _elapsed_ms(total_start)
    return {
        "probe": {
            "name": "abyss_source_data_update",
            "production_safe_debug": True,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "normal_path_contract": {
                "fandom_period_parse_requests": 1,
                "nanoka_tower_manifest_requests": 1
                if tower_id is None and normalized_hp_mode != HP_FALLBACK_MODE_FANDOM_ONLY
                else 0,
                "nanoka_tower_detail_json_requests": 0
                if normalized_hp_mode == HP_FALLBACK_MODE_FANDOM_ONLY
                else 1,
                "fandom_enemy_page_requests": int(
                    timings.get("fandom_enemy_page_hp_fallback_requests", 0)
                ),
                "fandom_enemy_page_fallback_enabled": normalized_hp_mode
                != HP_FALLBACK_MODE_NANOKA_ONLY,
                "hp_source_mode": normalized_hp_mode,
                "hp_multiplier": float(hp_multiplier),
                "fandom_hp_workers": normalized_workers,
            },
            "timings_ms": timings,
            "warnings": [
                "Debug/update entrypoint only; no UI, persistence, history, Account/Data import, or GCSIM wiring.",
                "Fandom period page is the composition/wave/count source.",
                "Nanoka tower JSON is the primary resolved HP/id/icon/detail source.",
                "Fandom enemy-page HP fallback runs only for missing HP unless forced.",
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
            "hp_source_mode": normalized_hp_mode,
            "hp_multiplier": float(hp_multiplier),
            "fandom_hp_workers": normalized_workers,
        },
        "nanoka": _nanoka_debug_metadata(data),
        "summary": _summary(data),
        "cache": cache_report,
        "assets": asset_report,
        "source_data": asdict(report_data),
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


def _asset_cache_report(result: IconCacheResult) -> dict[str, Any]:
    return {
        "enabled": True,
        "cache_dir": str(result.cache_dir),
        "attempted": result.attempted,
        "saved": result.saved,
        "failed": result.failed,
        "downloaded": result.downloaded,
        "cache_hits": result.cache_hits,
        "warnings": list(result.warnings),
    }


def _prefixed_timings(prefix: str, report: dict[str, Any] | None) -> dict[str, float]:
    if not isinstance(report, dict):
        return {}
    raw = report.get("timings_ms")
    if not isinstance(raw, dict):
        return {}
    timings: dict[str, float] = {}
    for key, value in raw.items():
        try:
            timings[f"{prefix}.{key}"] = float(value)
        except (TypeError, ValueError):
            continue
    return timings


def _elapsed_ms(start: float) -> float:
    return round((perf_counter() - start) * 1000, 3)


def _normalize_worker_count(value: int | str | None) -> int:
    try:
        return max(1, int(value or DEFAULT_FANDOM_ENEMY_PAGE_WORKERS))
    except (TypeError, ValueError):
        return DEFAULT_FANDOM_ENEMY_PAGE_WORKERS


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
    timings = report.get("probe", {}).get("timings_ms", {})
    if isinstance(timings, dict) and timings:
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
    contract = report.get("probe", {}).get("normal_path_contract", {})
    if isinstance(contract, dict):
        lines.append(
            "hp_source="
            f"mode={contract.get('hp_source_mode')} "
            f"multiplier={contract.get('hp_multiplier')} "
            f"workers={contract.get('fandom_hp_workers')} "
            f"fandom_enemy_page_requests={contract.get('fandom_enemy_page_requests')}"
        )
    cache_report = report.get("cache", {})
    if cache_report.get("saved"):
        lines.append(f"cache_saved={cache_report.get('path')}")
    asset_report = report.get("assets", {})
    if asset_report.get("enabled"):
        lines.append(
            "assets="
            f"attempted={asset_report.get('attempted')} "
            f"saved={asset_report.get('saved')} "
            f"failed={asset_report.get('failed')} "
            f"dir={asset_report.get('cache_dir')}"
        )
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
    parser.add_argument(
        "--skip-assets",
        action="store_true",
        help="With --save-cache, skip monster icon asset downloads.",
    )
    parser.add_argument(
        "--hp-source",
        choices=HP_FALLBACK_MODE_CHOICES,
        default=HP_FALLBACK_MODE_AUTO,
        help=(
            "Fact HP source mode. auto=Nanoka primary plus Fandom enemy-page fallback "
            "for missing HP; nanoka-only disables enemy-page fallback; fandom-only "
            "skips Nanoka HP and forces Fandom enemy-page HP. Default: auto."
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
            "Bounded parallel Fandom enemy-page HP fetch workers. "
            f"Default: {DEFAULT_FANDOM_ENEMY_PAGE_WORKERS}."
        ),
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
            cache_assets=not args.skip_assets,
            hp_source_mode=args.hp_source,
            hp_multiplier=args.hp_multiplier,
            fandom_hp_workers=args.fandom_hp_workers,
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
