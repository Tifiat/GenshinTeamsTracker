"""Experiment-only batch probe for Abyss composition/HP source comparison.

This script runs the existing Fandom composition, Nanoka primary HP join, and
Fandom enemy-page fallback HP experiment paths for explicit Abyss periods. It is
research/debug output only and must not be wired into production UI/runtime
models.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from typing import Any

try:
    import abyss_join_probe as join_probe
    import fandom_composition_probe as composition_probe
    import fandom_enemy_hp_probe as fallback_probe
    import nanoka_tower_probe as nanoka_probe
except ImportError:
    from tools.experiments.abyss import abyss_join_probe as join_probe
    from tools.experiments.abyss import fandom_composition_probe as composition_probe
    from tools.experiments.abyss import fandom_enemy_hp_probe as fallback_probe
    from tools.experiments.abyss import nanoka_tower_probe as nanoka_probe


FANDOM_PERIOD_URL = "https://genshin-impact.fandom.com/wiki/Spiral_Abyss/Floors/{date}"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MATCHED_CONFIDENCES = {
    join_probe.MATCH_CONFIDENCE_HIGH,
    join_probe.MATCH_CONFIDENCE_MEDIUM,
    join_probe.MATCH_CONFIDENCE_LOW,
}
NON_STRICT_METHODS = {
    join_probe.MATCH_METHOD_MANUAL_ALIAS,
    join_probe.MATCH_METHOD_VARIANT_STRIP,
    join_probe.MATCH_METHOD_CONTEXT_UNIQUE,
}


def _parse_case(value: str) -> dict[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError(
            "--case must use DATE=TOWER_ID, for example 2026-05-16=119"
        )
    date, tower_id = [part.strip() for part in value.split("=", 1)]
    if not DATE_RE.match(date):
        raise argparse.ArgumentTypeError(f"Invalid case date: {date!r}")
    if not tower_id:
        raise argparse.ArgumentTypeError(f"Missing tower id in case: {value!r}")
    return {
        "date": date,
        "tower_id": tower_id,
        "period_url": FANDOM_PERIOD_URL.format(date=date),
    }


def _composition_counts(report: dict[str, Any]) -> list[dict[str, Any]]:
    counts: list[dict[str, Any]] = []
    for floor in report.get("floors", []):
        for chamber in floor.get("chambers", []):
            for side in chamber.get("sides", []):
                waves = side.get("waves", [])
                counts.append(
                    {
                        "floor": floor.get("floor"),
                        "chamber": chamber.get("chamber"),
                        "side": side.get("side"),
                        "side_name": side.get("side_name"),
                        "wave_count": len(waves),
                        "enemy_row_count": sum(
                            len(wave.get("enemies", [])) for wave in waves
                        ),
                        "warnings": side.get("warnings", []),
                    }
                )
    return counts


def _composition_warnings(report: dict[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for floor in report.get("floors", []):
        for warning in floor.get("warnings", []):
            warnings.append({"floor": floor.get("floor"), "warning": warning})
        for chamber in floor.get("chambers", []):
            for side in chamber.get("sides", []):
                for warning in side.get("warnings", []):
                    warnings.append(
                        {
                            "floor": floor.get("floor"),
                            "chamber": chamber.get("chamber"),
                            "side": side.get("side"),
                            "warning": warning,
                        }
                    )
    return warnings


def _primary_match_summary(joined_rows: list[dict[str, Any]]) -> dict[str, Any]:
    unmatched = [
        row
        for row in joined_rows
        if row.get("match_method") == join_probe.MATCH_METHOD_UNMATCHED
    ]
    ambiguous = [
        row
        for row in joined_rows
        if row.get("match_method") == join_probe.MATCH_METHOD_AMBIGUOUS
    ]
    return {
        "joined_row_count": len(joined_rows),
        "matched_count": sum(
            1 for row in joined_rows if row.get("match_confidence") in MATCHED_CONFIDENCES
        ),
        "unmatched_count": len(unmatched),
        "ambiguous_count": len(ambiguous),
        "non_strict_match_count": sum(
            1 for row in joined_rows if row.get("match_method") in NON_STRICT_METHODS
        ),
        "unmatched": [_compact_join_row(row) for row in unmatched],
        "ambiguous": [_compact_join_row(row) for row in ambiguous],
    }


def _compact_join_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "floor": row.get("floor"),
        "chamber": row.get("chamber"),
        "side": row.get("side"),
        "wave": row.get("wave"),
        "primary_display_name": row.get("primary_display_name"),
        "fandom_display_name": row.get("fandom_display_name"),
        "nanoka_display_name": row.get("nanoka_display_name"),
        "match_method": row.get("match_method"),
        "match_confidence": row.get("match_confidence"),
        "warnings": row.get("warnings", []),
    }


def _side_hp_totals(chamber_sides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for side in chamber_sides:
        hp_modes = side.get("fact_dps_hp_modes", {})
        result.append(
            {
                "floor": side.get("floor"),
                "chamber": side.get("chamber"),
                "side": side.get("side"),
                "side_name": side.get("side_name"),
                "solo_target_hp": hp_modes.get("solo_target_hp_display_formatted"),
                "solo_target_counted_targets": hp_modes.get(
                    "solo_target_counted_targets"
                ),
                "multi_target_hp": hp_modes.get("multi_target_hp_display_formatted"),
                "multi_target_counted_targets": hp_modes.get(
                    "multi_target_counted_targets"
                ),
                "warnings": side.get("warnings", []),
            }
        )
    return result


def _notable_non_strict_matches(joined_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        _compact_join_row(row)
        for row in joined_rows
        if row.get("match_method") in NON_STRICT_METHODS
    ]


def _notable_fallback_differences(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    differences: list[dict[str, Any]] = []
    for row in rows:
        comparison = row.get("nanoka_comparison", {})
        if comparison.get("status") != "different":
            continue
        differences.append(
            {
                "floor": row.get("floor"),
                "chamber": row.get("chamber"),
                "side": row.get("side"),
                "wave": row.get("wave"),
                "fandom_display_name": row.get("fandom_display_name"),
                "selected_table_section_heading": row.get(
                    "selected_table_section_heading"
                ),
                "fallback_resolved_hp": row.get(
                    "fallback_resolved_hp_display_formatted"
                ),
                "nanoka_hp": comparison.get("nanoka_hp_display_formatted"),
                "delta_percent": comparison.get("delta_percent"),
                "table_match_method": row.get("table_match_method"),
                "table_match_confidence": row.get("table_match_confidence"),
                "warnings": row.get("warnings", []),
            }
        )
    return differences


def _fallback_unresolved(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return list(summary.get("unresolved_fallback_rows", []))


def _check_resolution(
    *,
    date: str,
    primary_summary: dict[str, Any],
    fallback_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    if date == "2026-05-16":
        passed = (
            primary_summary.get("joined_row_count") == 10
            and primary_summary.get("matched_count") == 10
            and primary_summary.get("unmatched_count") == 0
            and primary_summary.get("ambiguous_count") == 0
            and fallback_summary.get("fallback_hp_available_count") == 10
            and fallback_summary.get("fallback_hp_unavailable_count") == 0
        )
        checks.append(
            {
                "id": "2026-05-16_tower119_floor12_primary_and_fallback_resolution",
                "passed": bool(passed),
                "expected": "Primary join 10/10 matched and fallback 10/10 resolved.",
                "observed": {
                    "primary": primary_summary,
                    "fallback": fallback_summary,
                },
            }
        )
    return checks


def _failed_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [check for check in checks if not check.get("passed")]


def _case_report(case: dict[str, str], args: argparse.Namespace) -> dict[str, Any]:
    period_url = case["period_url"]
    floor = args.floor
    composition_report = composition_probe.build_report(
        argparse.Namespace(period_url=period_url, floor=floor, indent=2)
    )
    nanoka_report = nanoka_probe.build_report(
        argparse.Namespace(
            tower_id=case["tower_id"],
            history_index=None,
            floor=floor,
            locale=args.locale,
            at=None,
            indent=2,
        )
    )
    joined_rows = join_probe._join_rows(composition_report, nanoka_report)
    chamber_sides = join_probe._chamber_side_summaries(joined_rows)
    primary_checks = join_probe._regression_checks(
        period_url=period_url,
        tower_id=case["tower_id"],
        chamber_sides=chamber_sides,
    )
    primary_summary = _primary_match_summary(joined_rows)
    fallback_rows = fallback_probe._build_fallback_rows(
        composition_report,
        {"joined_rows": joined_rows},
        hp_multiplier=float(args.hp_multiplier),
        multiplier_source="explicit_manual_batch",
    )
    fallback_summary = fallback_probe._comparison_summary(fallback_rows)
    fallback_checks = [
        check
        for check in (
            fallback_probe._composition_fisher_check(composition_report),
            fallback_probe._rock_crab_check(fallback_rows, period_url),
        )
        if check is not None
    ]
    composition_checks = composition_report.get("probe", {}).get(
        "regression_checks", []
    )
    resolution_checks = _check_resolution(
        date=case["date"],
        primary_summary=primary_summary,
        fallback_summary=fallback_summary,
    )
    checks = [
        *composition_checks,
        *primary_checks,
        *fallback_checks,
        *resolution_checks,
    ]
    composition_rows = len(composition_report.get("enemy_rows", []))
    important_warnings = _important_warnings(
        composition_warnings=_composition_warnings(composition_report),
        primary_summary=primary_summary,
        fallback_summary=fallback_summary,
        checks=checks,
    )
    return {
        "date": case["date"],
        "tower_id": case["tower_id"],
        "floor": floor,
        "period_url": period_url,
        "composition_rows": composition_rows,
        "composition": {
            "row_count": composition_rows,
            "chamber_side_wave_counts": _composition_counts(composition_report),
            "warnings": _composition_warnings(composition_report),
            "regression_checks": composition_checks,
        },
        "primary_join": {
            "matched": primary_summary.get("matched_count"),
            "unmatched": primary_summary.get("unmatched_count"),
            "ambiguous": primary_summary.get("ambiguous_count"),
            "summary": primary_summary,
            "side_hp_totals": _side_hp_totals(chamber_sides),
            "notable_non_strict_matches": _notable_non_strict_matches(joined_rows),
            "regression_checks": primary_checks,
        },
        "fallback": {
            "resolved": fallback_summary.get("fallback_hp_available_count"),
            "unresolved": fallback_summary.get("fallback_hp_unavailable_count"),
            "summary": fallback_summary,
            "unresolved_rows": _fallback_unresolved(fallback_summary),
            "regression_checks": fallback_checks,
        },
        "fallback_vs_nanoka": fallback_summary.get(
            "nanoka_comparison_status_counts", {}
        ),
        "important_warnings": important_warnings,
        "notable_differences": _notable_fallback_differences(fallback_rows),
        "regression_checks": checks,
        "failed_checks": _failed_checks(checks),
        "source_urls": join_probe._source_urls(composition_report, nanoka_report),
    }


def _important_warnings(
    *,
    composition_warnings: list[dict[str, Any]],
    primary_summary: dict[str, Any],
    fallback_summary: dict[str, Any],
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    warnings.extend(
        {"type": "composition_warning", **warning} for warning in composition_warnings
    )
    for row in primary_summary.get("unmatched", []):
        warnings.append({"type": "primary_unmatched", **row})
    for row in primary_summary.get("ambiguous", []):
        warnings.append({"type": "primary_ambiguous", **row})
    for row in fallback_summary.get("unresolved_fallback_rows", []):
        warnings.append({"type": "fallback_unresolved", **row})
    for check in _failed_checks(checks):
        warnings.append(
            {
                "type": "failed_regression_check",
                "id": check.get("id"),
                "expected": check.get("expected"),
                "observed": check.get("observed"),
            }
        )
    return warnings


def _overall_totals(cases: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: Counter[str] = Counter()
    for case in cases:
        status_counts.update(case.get("fallback_vs_nanoka", {}))
    return {
        "case_count": len(cases),
        "composition_rows": sum(int(case.get("composition_rows") or 0) for case in cases),
        "primary_join": {
            "matched": sum(
                int(case.get("primary_join", {}).get("matched") or 0) for case in cases
            ),
            "unmatched": sum(
                int(case.get("primary_join", {}).get("unmatched") or 0)
                for case in cases
            ),
            "ambiguous": sum(
                int(case.get("primary_join", {}).get("ambiguous") or 0)
                for case in cases
            ),
        },
        "fallback": {
            "resolved": sum(
                int(case.get("fallback", {}).get("resolved") or 0) for case in cases
            ),
            "unresolved": sum(
                int(case.get("fallback", {}).get("unresolved") or 0)
                for case in cases
            ),
        },
        "fallback_vs_nanoka": dict(status_counts),
        "failed_check_count": sum(len(case.get("failed_checks", [])) for case in cases),
        "warning_count": sum(len(case.get("important_warnings", [])) for case in cases),
        "notable_difference_count": sum(
            len(case.get("notable_differences", [])) for case in cases
        ),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for case in args.case:
        try:
            report = _case_report(case, args)
        except Exception as exc:  # experiment should keep batch output readable
            report = {
                "date": case["date"],
                "tower_id": case["tower_id"],
                "floor": args.floor,
                "period_url": case["period_url"],
                "error": str(exc),
                "failed_checks": [
                    {
                        "id": "case_probe_exception",
                        "passed": False,
                        "expected": "Case probe completes without exception.",
                        "observed": str(exc),
                    }
                ],
            }
        cases.append(report)
        for check in report.get("failed_checks", []):
            failures.append(
                {
                    "date": case["date"],
                    "tower_id": case["tower_id"],
                    **check,
                }
            )
        for warning in report.get("important_warnings", []):
            warnings.append(
                {
                    "date": case["date"],
                    "tower_id": case["tower_id"],
                    **warning,
                }
            )
    return {
        "probe": {
            "name": "abyss_pipeline_batch_probe",
            "experimental": True,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "warnings": [
                "Research/debug output only; do not wire this script into production UI.",
                "Fandom period pages are used for composition/waves/counts.",
                "Nanoka is the primary resolved HP source.",
                "Fandom enemy-page HP fallback is an independent backup/cross-check.",
                "Fallback-vs-Nanoka differences are reported, not treated as automatic failures.",
            ],
        },
        "inputs": {
            "cases": args.case,
            "floor": args.floor,
            "hp_multiplier": args.hp_multiplier,
            "locale": args.locale,
        },
        "cases": cases,
        "overall_totals": _overall_totals(cases),
        "failures": failures,
        "warnings": warnings,
    }


def _text_summary(report: dict[str, Any]) -> str:
    lines = [
        "Abyss pipeline batch probe",
        f"cases={report.get('overall_totals', {}).get('case_count')} "
        f"failed_checks={report.get('overall_totals', {}).get('failed_check_count')}",
    ]
    for case in report.get("cases", []):
        primary = case.get("primary_join", {})
        fallback = case.get("fallback", {})
        lines.append(
            f"- {case.get('date')} tower={case.get('tower_id')} floor={case.get('floor')}: "
            f"composition_rows={case.get('composition_rows')} "
            f"primary={primary.get('matched')}/"
            f"{primary.get('summary', {}).get('joined_row_count')} matched "
            f"unmatched={primary.get('unmatched')} ambiguous={primary.get('ambiguous')} "
            f"fallback={fallback.get('resolved')}/"
            f"{fallback.get('summary', {}).get('row_count')} resolved"
        )
        for diff in case.get("notable_differences", []):
            lines.append(
                "  diff: "
                f"{diff.get('fandom_display_name')} fallback={diff.get('fallback_resolved_hp')} "
                f"nanoka={diff.get('nanoka_hp')} delta={diff.get('delta_percent')}"
            )
        for check in case.get("regression_checks", []):
            lines.append(
                f"  check {check.get('id')}: "
                f"{'PASS' if check.get('passed') else 'FAIL'}"
            )
    return "\n".join(lines)


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Experiment-only batch runner for Fandom composition, Nanoka primary "
            "HP join, and Fandom enemy-page fallback HP probes."
        )
    )
    parser.add_argument(
        "--case",
        action="append",
        type=_parse_case,
        required=True,
        help="Explicit case as DATE=TOWER_ID, for example 2026-05-16=119.",
    )
    parser.add_argument(
        "--floor",
        action="append",
        type=int,
        help="Limit probes to one floor. May be supplied more than once.",
    )
    parser.add_argument(
        "--hp-multiplier",
        type=float,
        default=3.75,
        help="Explicit/manual fallback HP multiplier. Default: 3.75.",
    )
    parser.add_argument(
        "--locale",
        default="en",
        help="Nanoka localized static JSON folder. Default: en.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="Output format. Default: json.",
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
    if args.format == "text":
        print(_text_summary(report))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=args.indent))
    return 2 if report.get("failures") else 0


if __name__ == "__main__":
    raise SystemExit(main())
