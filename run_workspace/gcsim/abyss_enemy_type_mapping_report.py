"""Backend/dev coverage report for Abyss enemy identity -> GCSIM type mapping.

This checker is intentionally narrow: it reads existing cached Abyss source-data
plus optional explicit enemy type overrides and a GCSIM enemy type registry,
then reports readiness coverage. It does not refresh Abyss network data, run
GCSIM, or use fuzzy display-name similarity as production truth. Managed Snap
fallback is cache-first and refreshes the single remote Monster.json only when
explicitly enabled and still needed after primary matching.
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
    MATCH_METHOD_SNAP_TITLE_CONTAINS_TARGET,
    MATCH_METHOD_SNAP_TITLE_FALLBACK,
    load_gcsim_enemy_type_registry_from_go_source,
)
from .snap_monster_titles import (
    DEFAULT_SNAP_MONSTER_GITHUB_URL,
    SNAP_CACHE_STATUS_REMOTE_NOT_NEEDED,
    SNAP_REFRESH_STATUS_NOT_NEEDED,
    SnapJsonFetcher,
    SnapMonsterTitleIndex,
    SnapMonsterTitleSourceError,
    load_cached_snap_monster_title_index,
    load_default_remote_snap_monster_title_index,
    load_snap_monster_title_index,
    refresh_cached_snap_monster_title_index,
)


@dataclass(frozen=True, slots=True)
class AbyssEnemyTypeCoverageReport:
    mapping_name: str
    source_count: int
    cache_file_count: int
    cache_files: tuple[str, ...]
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
    snap_source: dict[str, str] | None = None
    snap_cache: dict[str, Any] | None = None
    steps: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "mapping_name": self.mapping_name,
            "source_count": self.source_count,
            "cache_file_count": self.cache_file_count,
            "cache_files": list(self.cache_files),
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
            "snap_source": self.snap_source,
            "snap_cache": self.snap_cache,
            "steps": list(self.steps),
            "warnings": list(self.warnings),
        }


def build_abyss_enemy_type_coverage_report(
    source_data: list[AbyssFloorSourceData] | tuple[AbyssFloorSourceData, ...],
    mapping: AbyssEnemyTypeMapping | None,
    *,
    enemy_type_registry: GcsimEnemyTypeRegistry | None = None,
    snap_title_index: SnapMonsterTitleIndex | None = None,
    cache_files: tuple[str, ...] | list[str] = (),
    snap_cache: dict[str, Any] | None = None,
    steps: tuple[str, ...] | list[str] = (),
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
                snap_title_index=snap_title_index,
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
        cache_file_count=len(cache_files),
        cache_files=tuple(str(item) for item in cache_files),
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
        snap_source=None if snap_title_index is None else snap_title_index.source_report(),
        snap_cache=snap_cache,
        steps=tuple(steps),
    )


def main(
    argv: list[str] | None = None,
    *,
    stdout: TextIO | None = None,
    snap_fetcher: SnapJsonFetcher | None = None,
) -> int:
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
        source_entries = _load_source_entries(args)
        source_data = [source for _path, source in source_entries]
        direct_snap_index = _direct_snap_title_index_from_args(args, fetcher=snap_fetcher)
    except (AbyssSourceDataCacheError, ValueError, OSError, json.JSONDecodeError) as exc:
        report = {"success": False, "status": "input_error", "error": str(exc)}
        _print_report(report, format_name=args.format, stdout=output)
        return 2

    try:
        report = _build_report_with_snap_flow(
            source_data,
            mapping,
            enemy_type_registry=enemy_type_registry,
            direct_snap_title_index=direct_snap_index,
            cache_files=[str(path) for path, _source in source_entries],
            use_cached_snap=bool(args.use_cached_snap_monster_json),
            refresh_snap_if_needed=bool(args.refresh_snap_monster_json_if_needed),
            snap_cache_path=args.snap_monster_cache_path,
            snap_fetcher=snap_fetcher,
        )
    except SnapMonsterTitleSourceError as exc:
        report_payload = {
            "success": False,
            "status": "input_error",
            "error": str(exc),
            "steps": [
                "matching_enemy_names_primary",
                "refreshing_snap_metadata",
            ],
        }
        _print_report(report_payload, format_name=args.format, stdout=output)
        return 2
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
        "--snap-monster-json",
        default=None,
        help=(
            "Optional Snap Monster.json path or URL. Uses only Name -> Title as a "
            "last-resort enemy type name fallback after normal registry matching fails. "
            "GitHub blob URLs are converted to raw content URLs."
        ),
    )
    parser.add_argument(
        "--use-default-remote-snap-monster-json",
        action="store_true",
        help=(
            "Dev-only direct remote read of official Snap.Metadata Monster.json. "
            "For the managed app-style flow, prefer --use-cached-snap-monster-json "
            "with optional --refresh-snap-monster-json-if-needed."
        ),
    )
    parser.add_argument(
        "--use-cached-snap-monster-json",
        action="store_true",
        help=(
            "Use the managed cached Snap Monster.json only if primary enemy registry "
            "matching leaves missing rows."
        ),
    )
    parser.add_argument(
        "--refresh-snap-monster-json-if-needed",
        action="store_true",
        help=(
            "If cached Snap titles are missing/invalid/insufficient after primary "
            "matching, refresh the managed cache from the official online Monster.json "
            "and retry."
        ),
    )
    parser.add_argument(
        "--snap-monster-cache-path",
        default=None,
        help="Optional managed Snap Monster.json cache path for tests/dev diagnostics.",
    )
    parser.add_argument(
        "--cache-file",
        action="append",
        default=[],
        help="Cached Abyss source-data JSON file. Repeatable.",
    )
    parser.add_argument(
        "--scan-cache-dir",
        default=None,
        help="Scan all cached Abyss source-data JSON files under this root.",
    )
    parser.add_argument("--cache-dir", default=None, help="Abyss source-data cache root.")
    parser.add_argument("--period-start", default=None, help="Cached period YYYY-MM-DD.")
    parser.add_argument(
        "--floor",
        type=int,
        default=None,
        help=(
            "Abyss floor cache key. In --scan-cache-dir mode, omit to scan all "
            "floor_*.json files; in single --cache-dir/--period-start mode, "
            "omitting uses floor 12 for compatibility."
        ),
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def _load_sources(args: argparse.Namespace) -> list[AbyssFloorSourceData]:
    return [source for _path, source in _load_source_entries(args)]


def _load_source_entries(args: argparse.Namespace) -> list[tuple[Path, AbyssFloorSourceData]]:
    entries: list[tuple[Path, AbyssFloorSourceData]] = []
    seen_paths: set[Path] = set()
    for raw_path in args.cache_file:
        path = Path(raw_path)
        normalized_path = path.resolve()
        if normalized_path in seen_paths:
            continue
        seen_paths.add(normalized_path)
        entries.append((path, _load_cache_file(path)))
    if args.scan_cache_dir:
        for path in _scan_cache_files(
            Path(args.scan_cache_dir),
            period_start=args.period_start,
            floor=args.floor,
        ):
            normalized_path = path.resolve()
            if normalized_path in seen_paths:
                continue
            seen_paths.add(normalized_path)
            entries.append((path, _load_cache_file(path)))
    if args.cache_dir or (args.period_start and not args.scan_cache_dir):
        if args.scan_cache_dir:
            raise ValueError("--cache-dir/--period-start single-source mode cannot be combined with --scan-cache-dir")
        if not args.period_start:
            raise ValueError("--period-start is required when --cache-dir is used")
        cache_dir = Path(args.cache_dir) if args.cache_dir else None
        floor = args.floor if args.floor is not None else 12
        data = load_cached_abyss_floor_source_data(
            args.period_start,
            floor=floor,
            cache_dir=cache_dir,
        )
        if data is None:
            raise ValueError(
                f"Abyss source-data cache not found for {args.period_start}/floor_{floor}"
            )
        path = _cache_path_for_loaded_source(args.period_start, floor, cache_dir)
        normalized_path = path.resolve()
        if normalized_path not in seen_paths:
            entries.append((path, data))
    if not entries:
        raise ValueError(
            "Provide at least one --cache-file, --scan-cache-dir, or --cache-dir/--period-start source."
        )
    return entries


def _enemy_type_registry_from_args(args: argparse.Namespace) -> GcsimEnemyTypeRegistry | None:
    if not args.gcsim_enemy_registry_source:
        return None
    return load_gcsim_enemy_type_registry_from_go_source(
        args.gcsim_enemy_registry_source
    )


def _direct_snap_title_index_from_args(
    args: argparse.Namespace,
    *,
    fetcher: SnapJsonFetcher | None = None,
) -> SnapMonsterTitleIndex | None:
    managed_requested = bool(
        args.use_cached_snap_monster_json or args.refresh_snap_monster_json_if_needed
    )
    if managed_requested and (args.snap_monster_json or args.use_default_remote_snap_monster_json):
        raise ValueError(
            "Use either direct Snap input or managed Snap cache/refresh options, not both."
        )
    if args.snap_monster_json and args.use_default_remote_snap_monster_json:
        raise ValueError(
            "Use either --snap-monster-json or --use-default-remote-snap-monster-json, not both."
        )
    if args.use_default_remote_snap_monster_json:
        return load_default_remote_snap_monster_title_index(fetcher=fetcher)
    if not args.snap_monster_json:
        return None
    return load_snap_monster_title_index(args.snap_monster_json, fetcher=fetcher)


def _build_report_with_snap_flow(
    source_data: list[AbyssFloorSourceData],
    mapping: AbyssEnemyTypeMapping | None,
    *,
    enemy_type_registry: GcsimEnemyTypeRegistry | None,
    direct_snap_title_index: SnapMonsterTitleIndex | None,
    cache_files: list[str],
    use_cached_snap: bool,
    refresh_snap_if_needed: bool,
    snap_cache_path: str | None,
    snap_fetcher: SnapJsonFetcher | None,
) -> AbyssEnemyTypeCoverageReport:
    steps = ["matching_enemy_names_primary"]
    if direct_snap_title_index is not None:
        steps.append("checking_direct_snap_titles")
        return build_abyss_enemy_type_coverage_report(
            source_data,
            mapping,
            enemy_type_registry=enemy_type_registry,
            snap_title_index=direct_snap_title_index,
            cache_files=cache_files,
            steps=steps,
            snap_cache=_snap_flow_report(phase="direct"),
        )

    primary = build_abyss_enemy_type_coverage_report(
        source_data,
        mapping,
        enemy_type_registry=enemy_type_registry,
        cache_files=cache_files,
        steps=steps,
        snap_cache=_snap_flow_report(
            cache_status=SNAP_CACHE_STATUS_REMOTE_NOT_NEEDED,
            refresh_status=SNAP_REFRESH_STATUS_NOT_NEEDED,
            phase="primary",
        ),
    )
    if not (use_cached_snap or refresh_snap_if_needed):
        return primary
    if _report_ready(primary):
        return primary

    steps.append("checking_cached_snap_titles")
    cache_load = load_cached_snap_monster_title_index(snap_cache_path)
    cache_report = _snap_flow_report(
        cache_status=cache_load.status,
        refresh_status=SNAP_REFRESH_STATUS_NOT_NEEDED,
        cache_path=cache_load.cache_path,
        phase="cache",
        error=cache_load.error,
    )
    if cache_load.ready:
        cached_report = build_abyss_enemy_type_coverage_report(
            source_data,
            mapping,
            enemy_type_registry=enemy_type_registry,
            snap_title_index=cache_load.index,
            cache_files=cache_files,
            snap_cache=_with_snap_counts(
                cache_report,
                "cached",
                cache_load.index,
                source_data,
                mapping,
                enemy_type_registry,
            ),
            steps=steps,
        )
        if _report_ready(cached_report) or not refresh_snap_if_needed:
            return cached_report
    elif not refresh_snap_if_needed:
        return build_abyss_enemy_type_coverage_report(
            source_data,
            mapping,
            enemy_type_registry=enemy_type_registry,
            cache_files=cache_files,
            snap_cache=cache_report,
            steps=steps,
        )

    steps.append("refreshing_snap_metadata")
    refresh = refresh_cached_snap_monster_title_index(
        snap_cache_path,
        source_url=DEFAULT_SNAP_MONSTER_GITHUB_URL,
        fetcher=snap_fetcher,
    )
    refresh_report = {**cache_report, **refresh.to_dict(), "phase": "refreshed"}
    if cache_report.get("error"):
        refresh_report["cache_error"] = cache_report["error"]
    if not refresh.ready:
        raise SnapMonsterTitleSourceError(refresh.error or refresh.status)
    steps.append("rechecking_snap_titles_after_refresh")
    return build_abyss_enemy_type_coverage_report(
        source_data,
        mapping,
        enemy_type_registry=enemy_type_registry,
        snap_title_index=refresh.index,
        cache_files=cache_files,
        snap_cache=_with_snap_counts(
            refresh_report,
            "refreshed",
            refresh.index,
            source_data,
            mapping,
            enemy_type_registry,
        ),
        steps=steps,
    )


def _report_ready(report: AbyssEnemyTypeCoverageReport) -> bool:
    return report.missing_mappings == 0 and report.ambiguous_mappings == 0


def _with_snap_counts(
    report: dict[str, Any],
    prefix: str,
    snap_index: SnapMonsterTitleIndex | None,
    source_data: list[AbyssFloorSourceData],
    mapping: AbyssEnemyTypeMapping | None,
    enemy_type_registry: GcsimEnemyTypeRegistry | None,
) -> dict[str, Any]:
    if snap_index is None:
        return report
    counted = build_abyss_enemy_type_coverage_report(
        source_data,
        mapping,
        enemy_type_registry=enemy_type_registry,
        snap_title_index=snap_index,
    )
    method_counts = counted.resolved_by_method
    counts = {
        "cached_snap_title_fallback": 0,
        "cached_snap_contains_fallback": 0,
        "refreshed_snap_title_fallback": 0,
        "refreshed_snap_contains_fallback": 0,
    }
    counts[f"{prefix}_snap_title_fallback"] = method_counts.get(
        MATCH_METHOD_SNAP_TITLE_FALLBACK,
        0,
    )
    contains_key = (
        "cached_snap_contains_fallback"
        if prefix == "cached"
        else "refreshed_snap_contains_fallback"
    )
    counts[contains_key] = method_counts.get(MATCH_METHOD_SNAP_TITLE_CONTAINS_TARGET, 0)
    return {**report, "snap_resolution_counts": counts}


def _snap_flow_report(
    *,
    cache_status: str = "",
    refresh_status: str = "",
    cache_path: str = "",
    phase: str,
    error: str = "",
) -> dict[str, Any]:
    return {
        "phase": phase,
        "cache_status": cache_status,
        "refresh_status": refresh_status,
        "cache_path": cache_path,
        "error": error,
        "snap_resolution_counts": {
            "cached_snap_title_fallback": 0,
            "cached_snap_contains_fallback": 0,
            "refreshed_snap_title_fallback": 0,
            "refreshed_snap_contains_fallback": 0,
        },
    }


def _scan_cache_files(
    cache_dir: Path,
    *,
    period_start: str | None,
    floor: int | None,
) -> list[Path]:
    if not cache_dir.is_dir():
        raise ValueError(f"Abyss source-data cache root not found: {cache_dir}")
    candidates = sorted(cache_dir.glob("**/floor_*.json"))
    result: list[Path] = []
    expected_name = f"floor_{floor}.json" if floor is not None else None
    for path in candidates:
        if expected_name and path.name != expected_name:
            continue
        if period_start and path.parent.name != period_start:
            continue
        result.append(path)
    if not result:
        filters: list[str] = []
        if period_start:
            filters.append(f"period_start={period_start}")
        if floor is not None:
            filters.append(f"floor={floor}")
        suffix = " with " + ", ".join(filters) if filters else ""
        raise ValueError(f"No Abyss source-data cache files found under {cache_dir}{suffix}.")
    return result


def _cache_path_for_loaded_source(
    period_start: str,
    floor: int,
    cache_dir: Path | None,
) -> Path:
    base = cache_dir if cache_dir is not None else Path("data") / "cache" / "abyss" / "source_data"
    return base / period_start / f"floor_{floor}.json"


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
        unresolved_rows = report.get("unresolved_rows") or []
        ambiguous_rows = report.get("ambiguous_rows") or []
        lines.extend(
            [
                f"mapping={report.get('mapping_name', '')}",
                (
                    "counts="
                    f"cache_files={report.get('cache_file_count', report.get('source_count', 0))} "
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
        snap_source = report.get("snap_source")
        if isinstance(snap_source, dict) and snap_source.get("kind"):
            lines.append(
                "snap_source="
                f"kind={snap_source.get('kind', '')} "
                f"source={snap_source.get('source', '')} "
                f"resolved_url={snap_source.get('resolved_url', '')}"
            )
        snap_cache = report.get("snap_cache")
        if isinstance(snap_cache, dict):
            lines.append(
                "snap_cache="
                f"phase={snap_cache.get('phase', '')} "
                f"cache_status={snap_cache.get('cache_status', '')} "
                f"refresh_status={snap_cache.get('refresh_status', '')} "
                f"cache_path={snap_cache.get('cache_path', '')}"
            )
            counts = snap_cache.get("snap_resolution_counts")
            if isinstance(counts, dict):
                lines.append("snap_resolution_counts=" + json.dumps(counts, sort_keys=True))
        steps = report.get("steps") or []
        if steps:
            lines.append("steps=" + ",".join(str(step) for step in steps))
        if unresolved_rows:
            lines.append("unresolved_rows=" + _compact_row_list(unresolved_rows))
        if ambiguous_rows:
            lines.append("ambiguous_rows=" + _compact_row_list(ambiguous_rows))
    if payload.get("error"):
        lines.append(f"error={payload['error']}")
    return "\n".join(lines)


def _compact_row_list(rows: list[Any], *, limit: int = 5) -> str:
    compact: list[str] = []
    for raw in rows[:limit]:
        if not isinstance(raw, dict):
            continue
        location = (
            f"{raw.get('period_start', '')}/F{raw.get('floor', '')}/"
            f"C{raw.get('chamber', '')}S{raw.get('side', '')}W{raw.get('wave', '')}"
        )
        name = raw.get("enemy", "")
        candidates = raw.get("available_identities") if isinstance(raw.get("available_identities"), list) else []
        candidate_text = _compact_candidate_list(candidates)
        resolution = raw.get("resolution") if isinstance(raw.get("resolution"), dict) else {}
        ambiguous = resolution.get("ambiguous_types") if isinstance(resolution, dict) else None
        suffix = ""
        if candidate_text:
            suffix += f" candidates=[{candidate_text}]"
        if ambiguous:
            suffix += " -> [" + ",".join(str(item) for item in ambiguous) + "]"
        compact.append(f"{location}:{name}{suffix}")
    hidden = len(rows) - len(compact)
    if hidden > 0:
        compact.append(f"...(+{hidden})")
    return "; ".join(compact)


def _compact_candidate_list(candidates: list[Any], *, limit: int = 3) -> str:
    result: list[str] = []
    for raw in candidates[:limit]:
        if not isinstance(raw, dict):
            continue
        source_kind = str(raw.get("source_kind") or "")
        source_id = str(raw.get("source_id") or "")
        if source_kind and source_id:
            result.append(f"{source_kind}:{source_id}")
    hidden = len(candidates) - len(result)
    if hidden > 0:
        result.append(f"+{hidden}")
    return ",".join(result)


if __name__ == "__main__":
    raise SystemExit(main())
