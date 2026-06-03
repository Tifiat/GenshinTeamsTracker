"""Experiment-only join probe for Fandom Abyss composition and Nanoka HP.

Fandom remains the source for floor/chamber/side/wave/count composition.
Nanoka remains the source for resolved enemy HP, monster id, level, icon, and
detail URL. This script joins those two experiment outputs for research only
and intentionally does not touch production fixtures, UI, persistence, history,
or GCSIM integration.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from typing import Any

try:
    import fandom_composition_probe as fandom_probe
    import nanoka_tower_probe as nanoka_probe
except ImportError:
    from tools.experiments.abyss import fandom_composition_probe as fandom_probe
    from tools.experiments.abyss import nanoka_tower_probe as nanoka_probe


def _normalize_enemy_name(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", ascii_value.casefold())


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _display_hp(value: float | None) -> int | None:
    if value is None:
        return None
    return int(math.floor(value + 0.5))


def _format_hp(value: float | None) -> str | None:
    display = _display_hp(value)
    return f"{display:,}" if display is not None else None


def _fandom_report(args: argparse.Namespace) -> dict[str, Any]:
    return fandom_probe.build_report(
        argparse.Namespace(
            period_url=args.period_url,
            floor=args.floor,
            indent=2,
        )
    )


def _nanoka_report(args: argparse.Namespace) -> dict[str, Any]:
    return nanoka_probe.build_report(
        argparse.Namespace(
            tower_id=str(args.tower_id),
            history_index=None,
            floor=args.floor,
            locale=args.locale,
            at=None,
            indent=2,
        )
    )


def _nanoka_candidates(
    nanoka_report: dict[str, Any],
) -> dict[tuple[int, int, int, str], list[dict[str, Any]]]:
    result: dict[tuple[int, int, int, str], list[dict[str, Any]]] = defaultdict(list)
    towers = nanoka_report.get("towers") or []
    if not towers:
        return result
    for row in towers[0].get("enemy_rows", []):
        floor = _as_int(row.get("floor"))
        chamber = _as_int(row.get("chamber"))
        side = _as_int(row.get("side"))
        normalized = _normalize_enemy_name(row.get("enemy_display_name"))
        if floor is None or chamber is None or side is None or not normalized:
            continue
        result[(floor, chamber, side, normalized)].append(row)
    return result


def _match_row(
    row: dict[str, Any],
    candidates_by_key: dict[tuple[int, int, int, str], list[dict[str, Any]]],
) -> dict[str, Any]:
    floor = _as_int(row.get("floor"))
    chamber = _as_int(row.get("chamber"))
    side = _as_int(row.get("side"))
    fandom_name = row.get("display_name")
    normalized = _normalize_enemy_name(fandom_name)
    warnings: list[str] = []
    key = (floor, chamber, side, normalized)
    candidates = candidates_by_key.get(key, [])

    base = {
        "floor": floor,
        "chamber": chamber,
        "side": side,
        "side_name": row.get("side_name"),
        "wave": _as_int(row.get("wave")),
        "fandom_enemy_display_name": fandom_name,
        "fandom_normalized_enemy_name": normalized,
        "fandom_enemy_count": _as_int(row.get("count")),
        "fandom_level": _as_int(row.get("level")),
        "fandom_enemy_page_url": row.get("enemy_page_url"),
        "fandom_icon_url": row.get("icon_url"),
        "fandom_raw_source_path": row.get("raw_source_path"),
    }

    if not candidates:
        return {
            **base,
            "matched_nanoka_enemy_display_name": None,
            "nanoka_monster_id": None,
            "nanoka_level": None,
            "nanoka_hp": None,
            "nanoka_hp_display": None,
            "nanoka_hp_display_formatted": None,
            "nanoka_icon_url": None,
            "nanoka_enemy_detail_url": None,
            "nanoka_hp_source_path": None,
            "match_method": "same_floor_chamber_side_normalized_name",
            "match_confidence": "unmatched",
            "warnings": ["nanoka_match_unavailable"],
        }

    if len(candidates) > 1:
        return {
            **base,
            "matched_nanoka_enemy_display_name": None,
            "nanoka_monster_id": None,
            "nanoka_level": None,
            "nanoka_hp": None,
            "nanoka_hp_display": None,
            "nanoka_hp_display_formatted": None,
            "nanoka_icon_url": None,
            "nanoka_enemy_detail_url": None,
            "nanoka_hp_source_path": None,
            "nanoka_candidate_count": len(candidates),
            "nanoka_candidates": [
                {
                    "enemy_display_name": candidate.get("enemy_display_name"),
                    "monster_id": candidate.get("monster_id"),
                    "level": candidate.get("level"),
                    "hp": candidate.get("hp_resolved"),
                    "hp_source_path": candidate.get("hp_source_path"),
                }
                for candidate in candidates
            ],
            "match_method": "same_floor_chamber_side_normalized_name",
            "match_confidence": "ambiguous",
            "warnings": ["nanoka_match_ambiguous"],
        }

    candidate = candidates[0]
    fandom_level = _as_int(row.get("level"))
    nanoka_level = _as_int(candidate.get("level"))
    if (
        fandom_level is not None
        and nanoka_level is not None
        and fandom_level != nanoka_level
    ):
        warnings.append(f"level_mismatch:fandom={fandom_level}:nanoka={nanoka_level}")
    hp = _as_float(candidate.get("hp_resolved"))
    if hp is None:
        warnings.append("nanoka_hp_missing")

    return {
        **base,
        "matched_nanoka_enemy_display_name": candidate.get("enemy_display_name"),
        "nanoka_monster_id": candidate.get("monster_id"),
        "nanoka_level": nanoka_level,
        "nanoka_hp": hp,
        "nanoka_hp_display": _display_hp(hp),
        "nanoka_hp_display_formatted": _format_hp(hp),
        "nanoka_icon_url": candidate.get("icon_url"),
        "nanoka_enemy_detail_url": candidate.get("enemy_detail_url"),
        "nanoka_hp_source_path": candidate.get("hp_source_path"),
        "match_method": "same_floor_chamber_side_normalized_name",
        "match_confidence": "matched"
        if not warnings
        else "matched_with_warnings",
        "warnings": warnings,
    }


def _join_rows(
    fandom_report: dict[str, Any],
    nanoka_report: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates_by_key = _nanoka_candidates(nanoka_report)
    return [
        _match_row(row, candidates_by_key)
        for row in fandom_report.get("enemy_rows", [])
    ]


def _group_rows(
    rows: list[dict[str, Any]],
) -> dict[tuple[int, int, int], list[dict[str, Any]]]:
    result: dict[tuple[int, int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        floor = _as_int(row.get("floor"))
        chamber = _as_int(row.get("chamber"))
        side = _as_int(row.get("side"))
        if floor is None or chamber is None or side is None:
            continue
        result[(floor, chamber, side)].append(row)
    return result


def _rows_by_wave(rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        wave = _as_int(row.get("wave")) or 1
        result[wave].append(row)
    return result


def _wave_breakdown(wave: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    warnings: list[str] = []
    matched_rows = [
        row for row in rows if _as_float(row.get("nanoka_hp")) is not None
    ]
    for row in rows:
        if _as_float(row.get("nanoka_hp")) is None:
            warnings.append(
                "missing_hp:"
                f"{row.get('fandom_enemy_display_name')}@{row.get('fandom_raw_source_path')}"
            )

    wave_multi_hp = 0.0
    wave_multi_count = 0
    for row in matched_rows:
        count = _as_int(row.get("fandom_enemy_count")) or 1
        hp = _as_float(row.get("nanoka_hp")) or 0.0
        wave_multi_hp += hp * count
        wave_multi_count += count

    selected_solo = None
    if matched_rows:
        selected_solo = max(
            matched_rows,
            key=lambda item: _as_float(item.get("nanoka_hp")) or 0.0,
        )
        wave_solo_hp = _as_float(selected_solo.get("nanoka_hp"))
        wave_solo_count = 1
    else:
        wave_solo_hp = None
        wave_solo_count = 0

    return {
        "wave": wave,
        "wave_solo_target_hp": wave_solo_hp,
        "wave_solo_target_hp_display": _display_hp(wave_solo_hp),
        "wave_solo_target_hp_display_formatted": _format_hp(wave_solo_hp),
        "wave_multi_target_hp": wave_multi_hp if matched_rows else None,
        "wave_multi_target_hp_display": _display_hp(wave_multi_hp)
        if matched_rows
        else None,
        "wave_multi_target_hp_display_formatted": _format_hp(wave_multi_hp)
        if matched_rows
        else None,
        "selected_solo_enemy": {
            "fandom_enemy_display_name": selected_solo.get(
                "fandom_enemy_display_name"
            ),
            "matched_nanoka_enemy_display_name": selected_solo.get(
                "matched_nanoka_enemy_display_name"
            ),
            "nanoka_monster_id": selected_solo.get("nanoka_monster_id"),
            "nanoka_hp": selected_solo.get("nanoka_hp"),
            "nanoka_hp_display": selected_solo.get("nanoka_hp_display"),
        }
        if selected_solo
        else None,
        "solo_target_counted_targets": wave_solo_count,
        "multi_target_counted_targets": wave_multi_count,
        "joined_enemies": rows,
        "warnings": warnings,
    }


def _side_summary(
    floor: int,
    chamber: int,
    side: int,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    side_name = next((row.get("side_name") for row in rows if row.get("side_name")), None)
    level = next((row.get("fandom_level") for row in rows if row.get("fandom_level")), None)
    waves = [
        _wave_breakdown(wave, wave_rows)
        for wave, wave_rows in sorted(_rows_by_wave(rows).items())
    ]
    solo_values = [
        _as_float(wave.get("wave_solo_target_hp"))
        for wave in waves
        if _as_float(wave.get("wave_solo_target_hp")) is not None
    ]
    multi_values = [
        _as_float(wave.get("wave_multi_target_hp"))
        for wave in waves
        if _as_float(wave.get("wave_multi_target_hp")) is not None
    ]
    solo_hp = sum(value for value in solo_values if value is not None)
    multi_hp = sum(value for value in multi_values if value is not None)
    missing_hp = any(wave.get("warnings") for wave in waves)
    row_warnings = [
        warning
        for row in rows
        for warning in row.get("warnings", [])
    ]
    warnings = sorted(set([*row_warnings]))
    if missing_hp:
        warnings.append("side_hp_partial_or_unavailable")
    return {
        "floor": floor,
        "chamber": chamber,
        "side": side,
        "side_name": side_name,
        "display_level": level,
        "waves": waves,
        "fact_dps_hp_modes": {
            "solo_target_hp": solo_hp if solo_values else None,
            "solo_target_hp_display": _display_hp(solo_hp)
            if solo_values
            else None,
            "solo_target_hp_display_formatted": _format_hp(solo_hp)
            if solo_values
            else None,
            "solo_target_counted_targets": sum(
                int(wave.get("solo_target_counted_targets") or 0)
                for wave in waves
            ),
            "multi_target_hp": multi_hp if multi_values else None,
            "multi_target_hp_display": _display_hp(multi_hp)
            if multi_values
            else None,
            "multi_target_hp_display_formatted": _format_hp(multi_hp)
            if multi_values
            else None,
            "multi_target_counted_targets": sum(
                int(wave.get("multi_target_counted_targets") or 0)
                for wave in waves
            ),
            "mode_notes": {
                "solo_target_hp": (
                    "For each sequential wave, counts only the highest-HP matched "
                    "enemy once."
                ),
                "multi_target_hp": (
                    "Sums every matched enemy HP multiplied by the Fandom card count."
                ),
            },
        },
        "warnings": warnings,
    }


def _chamber_side_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _side_summary(floor, chamber, side, grouped_rows)
        for (floor, chamber, side), grouped_rows in sorted(_group_rows(rows).items())
    ]


def _source_urls(
    fandom_report: dict[str, Any],
    nanoka_report: dict[str, Any],
) -> dict[str, Any]:
    tower = (nanoka_report.get("towers") or [{}])[0]
    return {
        "fandom_period_url": fandom_report.get("source", {}).get("url"),
        "fandom_mediawiki_parse_api_url": fandom_report.get("source", {}).get(
            "mediawiki_parse_api_url"
        ),
        "nanoka_page_url": tower.get("source_urls", {}).get("page_url"),
        "nanoka_manifest_json_url": tower.get("source_urls", {}).get(
            "manifest_json_url"
        ),
        "nanoka_detail_json_url": tower.get("source_urls", {}).get(
            "detail_json_url"
        ),
    }


def _find_side(
    chamber_sides: list[dict[str, Any]],
    floor: int,
    chamber: int,
    side: int,
) -> dict[str, Any] | None:
    for item in chamber_sides:
        if (
            item.get("floor") == floor
            and item.get("chamber") == chamber
            and item.get("side") == side
        ):
            return item
    return None


def _regression_checks(
    *,
    period_url: str,
    tower_id: str,
    chamber_sides: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if (
        "2026-02-16" not in period_url
        or str(tower_id) != "116"
    ):
        return []
    side = _find_side(chamber_sides, 12, 1, 1)
    observed_waves: list[dict[str, Any]] = []
    if side:
        for wave in side.get("waves", []):
            observed_waves.append(
                {
                    "wave": wave.get("wave"),
                    "enemies": [
                        {
                            "display_name": enemy.get("fandom_enemy_display_name"),
                            "count": enemy.get("fandom_enemy_count"),
                            "hp": enemy.get("nanoka_hp"),
                            "match_confidence": enemy.get("match_confidence"),
                        }
                        for enemy in wave.get("joined_enemies", [])
                    ],
                }
            )
    fisher_shape_ok = len(observed_waves) == 5 and all(
        len(wave.get("enemies", [])) == 1
        and wave["enemies"][0].get("display_name") == "Fisher of Hidden Depths"
        and wave["enemies"][0].get("count") == 3
        and wave["enemies"][0].get("match_confidence") == "matched"
        for wave in observed_waves
    )
    hp_modes = side.get("fact_dps_hp_modes", {}) if side else {}
    solo_count_ok = hp_modes.get("solo_target_counted_targets") == 5
    multi_count_ok = hp_modes.get("multi_target_counted_targets") == 15
    return [
        {
            "id": "2026-02-16_tower116_floor12_chamber1_first_half_join",
            "passed": bool(fisher_shape_ok and solo_count_ok and multi_count_ok),
            "expected": (
                "Five sequential Fisher of Hidden Depths waves, count 3 each; "
                "solo mode counts 5 targets and multi mode counts 15 targets."
            ),
            "observed_waves": observed_waves,
            "observed_hp_modes": hp_modes,
        }
    ]


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    fandom_report = _fandom_report(args)
    nanoka_report = _nanoka_report(args)
    joined_rows = _join_rows(fandom_report, nanoka_report)
    chamber_sides = _chamber_side_summaries(joined_rows)
    checks = _regression_checks(
        period_url=args.period_url,
        tower_id=str(args.tower_id),
        chamber_sides=chamber_sides,
    )
    tower = (nanoka_report.get("towers") or [{}])[0]
    unmatched = [
        row for row in joined_rows if row.get("match_confidence") == "unmatched"
    ]
    ambiguous = [
        row for row in joined_rows if row.get("match_confidence") == "ambiguous"
    ]
    return {
        "probe": {
            "name": "abyss_composition_hp_join_probe",
            "experimental": True,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "warnings": [
                "Research/debug output only; do not wire this script into production UI.",
                "Fandom is the source for floor/chamber/side/wave/count composition.",
                "Nanoka is the source for resolved HP; Nanoka wave values are ignored.",
                "No GCSIM simulation is performed here.",
            ],
            "regression_checks": checks,
        },
        "source_urls": _source_urls(fandom_report, nanoka_report),
        "period": {
            "fandom_period_date_from_url": fandom_report.get("source", {}).get(
                "period_date_from_url"
            ),
            "fandom_duration_text": fandom_report.get("source", {}).get(
                "duration_text"
            ),
            "nanoka_period": tower.get("period"),
        },
        "tower_id": str(args.tower_id),
        "floors_requested": args.floor,
        "chamber_sides": chamber_sides,
        "joined_rows": joined_rows,
        "match_summary": {
            "joined_row_count": len(joined_rows),
            "matched_count": sum(
                1 for row in joined_rows if row.get("match_confidence") == "matched"
            ),
            "matched_with_warnings_count": sum(
                1
                for row in joined_rows
                if row.get("match_confidence") == "matched_with_warnings"
            ),
            "unmatched_count": len(unmatched),
            "ambiguous_count": len(ambiguous),
            "unmatched": [
                {
                    "floor": row.get("floor"),
                    "chamber": row.get("chamber"),
                    "side": row.get("side"),
                    "wave": row.get("wave"),
                    "fandom_enemy_display_name": row.get(
                        "fandom_enemy_display_name"
                    ),
                    "fandom_normalized_enemy_name": row.get(
                        "fandom_normalized_enemy_name"
                    ),
                }
                for row in unmatched
            ],
            "ambiguous": [
                {
                    "floor": row.get("floor"),
                    "chamber": row.get("chamber"),
                    "side": row.get("side"),
                    "wave": row.get("wave"),
                    "fandom_enemy_display_name": row.get(
                        "fandom_enemy_display_name"
                    ),
                    "nanoka_candidate_count": row.get("nanoka_candidate_count"),
                }
                for row in ambiguous
            ],
        },
    }


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Experiment-only join probe for Fandom Spiral Abyss composition "
            "and Nanoka resolved HP."
        )
    )
    parser.add_argument("--period-url", required=True)
    parser.add_argument("--tower-id", required=True)
    parser.add_argument(
        "--floor",
        action="append",
        type=int,
        help="Limit both source probes to one floor. May be supplied more than once.",
    )
    parser.add_argument(
        "--locale",
        default="en",
        help="Nanoka localized static JSON folder. Default: en.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation level. Default: 2.",
    )
    return parser


def main() -> int:
    parser = _build_argument_parser()
    args = parser.parse_args()
    report = build_report(args)
    print(json.dumps(report, ensure_ascii=False, indent=args.indent))
    failed = [
        check
        for check in report["probe"].get("regression_checks", [])
        if not check.get("passed")
    ]
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
