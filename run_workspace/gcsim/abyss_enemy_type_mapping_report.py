"""Backend/dev coverage report for Abyss enemy identity -> GCSIM type mapping.

This checker is intentionally narrow: it reads existing cached Abyss source-data
plus optional explicit enemy type overrides and a GCSIM enemy type registry,
then reports readiness coverage. It does not fetch network data, mutate caches,
run GCSIM, or use fuzzy display-name similarity as production truth.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, TextIO

from run_workspace.abyss.source_data import AbyssFloorSourceData
from run_workspace.abyss.source_data_cache import (
    AbyssSourceDataCacheError,
    load_cached_abyss_floor_source_data,
)

from .abyss_wave_scenario import (
    AbyssEnemyTypeMapping,
    abyss_enemy_identity_candidates,
    load_enemy_type_mapping_from_json,
)
from .enemy_type_registry import (
    GcsimEnemyTypeRegistry,
    load_gcsim_enemy_type_registry_from_go_source,
)


@dataclass(frozen=True, slots=True)
class AbyssEnemyTypeCoverageReport:
    mapping_name: str
    source_count: int
    total_rows: int
    resolved_by_method: dict[str, int]
    resolved_by_source_kind: dict[str, int]
    missing_mappings: int
    ambiguous_mappings: int
    hp_present_type_missing: int
    type_present_hp_missing: int
    resolved_rows: tuple[dict[str, Any], ...]
    unresolved_rows: tuple[dict[str, Any], ...]
    ambiguous_rows: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "mapping_name": self.mapping_name,
            "source_count": self.source_count,
            "total_rows": self.total_rows,
            "resolved_by_method": dict(self.resolved_by_method),
            "resolved_by_source_kind": dict(self.resolved_by_source_kind),
            "missing_mappings": self.missing_mappings,
            "ambiguous_mappings": self.ambiguous_mappings,
            "hp_present_type_missing": self.hp_present_type_missing,
            "type_present_hp_missing": self.type_present_hp_missing,
            "resolved_rows": list(self.resolved_rows),
            "unresolved_rows": list(self.unresolved_rows),
            "ambiguous_rows": list(self.ambiguous_rows),
            "warnings": list(self.warnings),
        }


def build_abyss_enemy_type_coverage_report(
    source_data: list[AbyssFloorSourceData] | tuple[AbyssFloorSourceData, ...],
    mapping: AbyssEnemyTypeMapping | None,
    *,
    enemy_type_registry: GcsimEnemyTypeRegistry | None = None,
) -> AbyssEnemyTypeCoverageReport:
    resolver = mapping or AbyssEnemyTypeMapping(mapping_name="gcsim_enemy_type_registry")
    resolved_by_method: Counter[str] = Counter()
    resolved_by_kind: Counter[str] = Counter()
    resolved_rows: list[dict[str, Any]] = []
    unresolved_rows: list[dict[str, Any]] = []
    ambiguous_rows: list[dict[str, Any]] = []
    missing = 0
    ambiguous = 0
    hp_present_type_missing = 0
    type_present_hp_missing = 0
    total_rows = 0

    for data in source_data:
        for row in data.enemy_rows:
            total_rows += 1
            resolution = resolver.resolve_row(
                row,
                enemy_type_registry=enemy_type_registry,
            )
            has_hp = row.nanoka_hp is not None and row.nanoka_hp > 0
            if resolution.ready:
                resolved_by_method[resolution.method] += 1
                if resolution.selected_identity is not None:
                    resolved_by_kind[resolution.selected_identity.source_kind] += 1
                resolved_rows.append(_row_detail(data, row, resolution, hp_present=has_hp))
                if not has_hp:
                    type_present_hp_missing += 1
                continue
            detail = _row_detail(data, row, resolution, hp_present=has_hp)
            if resolution.status == "ambiguous_mapping":
                ambiguous += 1
                ambiguous_rows.append(detail)
            else:
                missing += 1
                unresolved_rows.append(detail)
                if has_hp:
                    hp_present_type_missing += 1

    return AbyssEnemyTypeCoverageReport(
        mapping_name=resolver.mapping_name,
        source_count=len(source_data),
        total_rows=total_rows,
        resolved_by_method=dict(sorted(resolved_by_method.items())),
        resolved_by_source_kind=dict(sorted(resolved_by_kind.items())),
        missing_mappings=missing,
        ambiguous_mappings=ambiguous,
        hp_present_type_missing=hp_present_type_missing,
        type_present_hp_missing=type_present_hp_missing,
        resolved_rows=tuple(resolved_rows),
        unresolved_rows=tuple(unresolved_rows),
        ambiguous_rows=tuple(ambiguous_rows),
    )


def main(argv: list[str] | None = None, *, stdout: TextIO | None = None) -> int:
    output = stdout or sys.stdout
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        mapping = (
            load_enemy_type_mapping_from_json(args.enemy_type_map)
            if args.enemy_type_map
            else None
        )
        enemy_type_registry = _enemy_type_registry_from_args(args)
        if mapping is None and enemy_type_registry is None:
            raise ValueError(
                "Provide --enemy-type-map and/or --gcsim-enemy-registry-source."
            )
        source_data = _load_sources(args)
    except (AbyssSourceDataCacheError, ValueError, OSError, json.JSONDecodeError) as exc:
        report = {"success": False, "status": "input_error", "error": str(exc)}
        _print_report(report, format_name=args.format, stdout=output)
        return 2

    report = build_abyss_enemy_type_coverage_report(
        source_data,
        mapping,
        enemy_type_registry=enemy_type_registry,
    )
    payload = {"success": True, "status": "reported", "report": report.to_dict()}
    _print_report(payload, format_name=args.format, stdout=output)
    return 0 if report.missing_mappings == 0 and report.ambiguous_mappings == 0 else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report cached Abyss source-data coverage for GCSIM enemy type mapping."
    )
    parser.add_argument(
        "--enemy-type-map",
        default=None,
        help="Optional enemy type override mapping JSON.",
    )
    parser.add_argument(
        "--gcsim-enemy-registry-source",
        default=None,
        help="Optional local GCSIM pkg/shortcut/enemies_gen.go source for known target type matching.",
    )
    parser.add_argument(
        "--cache-file",
        action="append",
        default=[],
        help="Cached Abyss source-data JSON file. Repeatable.",
    )
    parser.add_argument("--cache-dir", default=None, help="Abyss source-data cache root.")
    parser.add_argument("--period-start", default=None, help="Cached period YYYY-MM-DD.")
    parser.add_argument("--floor", type=int, default=12, help="Abyss floor cache key.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def _load_sources(args: argparse.Namespace) -> list[AbyssFloorSourceData]:
    sources: list[AbyssFloorSourceData] = []
    for raw_path in args.cache_file:
        sources.append(_load_cache_file(Path(raw_path)))
    if args.cache_dir or args.period_start:
        if not args.period_start:
            raise ValueError("--period-start is required when --cache-dir is used")
        data = load_cached_abyss_floor_source_data(
            args.period_start,
            floor=args.floor,
            cache_dir=args.cache_dir,
        )
        if data is None:
            raise ValueError(
                f"Abyss source-data cache not found for {args.period_start}/floor_{args.floor}"
            )
        sources.append(data)
    if not sources:
        raise ValueError("Provide at least one --cache-file or --cache-dir/--period-start source.")
    return sources


def _enemy_type_registry_from_args(args: argparse.Namespace) -> GcsimEnemyTypeRegistry | None:
    if not args.gcsim_enemy_registry_source:
        return None
    return load_gcsim_enemy_type_registry_from_go_source(
        args.gcsim_enemy_registry_source
    )


def _row_detail(
    data: AbyssFloorSourceData,
    row: Any,
    resolution: Any,
    *,
    hp_present: bool,
) -> dict[str, Any]:
    return {
        "period_start": data.period.start_date,
        "floor": data.floor,
        "chamber": row.chamber,
        "side": row.side,
        "wave": row.wave,
        "enemy": row.primary_display_name,
        "hp_present": hp_present,
        "hp_source": row.hp_source,
        "gcsim_type": resolution.gcsim_type,
        "method": resolution.method,
        "selected_identity": None
        if resolution.selected_identity is None
        else resolution.selected_identity.to_dict(),
        "available_identities": [
            candidate.to_dict()
            for candidate in abyss_enemy_identity_candidates(row)
        ],
        "resolution": resolution.to_dict(),
    }


def _load_cache_file(path: Path) -> AbyssFloorSourceData:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Cached source-data file is not a JSON object: {path}")
    cache_key = payload.get("cache_key")
    if not isinstance(cache_key, dict):
        raise ValueError(f"Cached source-data file has no cache_key: {path}")
    period_start = str(cache_key.get("period_start") or "")
    floor = int(cache_key.get("floor") or 0)
    data = load_cached_abyss_floor_source_data(
        period_start,
        floor=floor,
        cache_dir=path.parent.parent,
    )
    if data is None:
        raise ValueError(f"Cached source-data file could not be loaded: {path}")
    return data


def _print_report(report: dict[str, Any], *, format_name: str, stdout: TextIO) -> None:
    if format_name == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), file=stdout)
    else:
        print(_format_text(report), file=stdout)


def _format_text(payload: dict[str, Any]) -> str:
    lines = [
        "Abyss enemy type mapping coverage",
        f"success={str(bool(payload.get('success'))).lower()} status={payload.get('status', '')}",
    ]
    report = payload.get("report")
    if isinstance(report, dict):
        lines.extend(
            [
                f"mapping={report.get('mapping_name', '')}",
                (
                    "counts="
                    f"sources={report.get('source_count', 0)} "
                    f"rows={report.get('total_rows', 0)} "
                    f"missing={report.get('missing_mappings', 0)} "
                    f"ambiguous={report.get('ambiguous_mappings', 0)}"
                ),
                "resolved_by_source_kind="
                + json.dumps(report.get("resolved_by_source_kind") or {}, sort_keys=True),
                "resolved_by_method="
                + json.dumps(report.get("resolved_by_method") or {}, sort_keys=True),
                (
                    "hp_type_gaps="
                    f"hp_present_type_missing={report.get('hp_present_type_missing', 0)} "
                    f"type_present_hp_missing={report.get('type_present_hp_missing', 0)}"
                ),
            ]
        )
    if payload.get("error"):
        lines.append(f"error={payload['error']}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
