"""Dev CLI for cached Abyss source-data -> GTT wave scenario smoke runs.

This command is a backend-only bridge around the provisional
`abyss_wave_scenario` adapter. It loads already-cached typed Abyss source data,
requires either explicit enemy type overrides or an optional GCSIM enemy type
registry matcher, writes a schema-v1 payload, and can optionally pass that
payload to the existing active GTT-GCSIM artifact runner with a caller provided
config. Managed Snap fallback is cache-first and refreshes the managed Snap
Monster title cache from official online Monster.json only when explicitly
enabled and still needed after primary matching. It does not refresh Abyss
network data, generate account/team GCSIM configs, map character/weapon/artifact
keys, or model final Abyss wave policy.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Callable, TextIO

from run_workspace.abyss.source_data import AbyssFloorSourceData
from run_workspace.abyss.source_data_cache import (
    AbyssSourceDataCacheError,
    load_cached_abyss_floor_source_data,
)
from run_workspace.abyss.source_data_runtime import (
    load_current_cached_abyss_floor_source_data,
)

from .abyss_wave_scenario import (
    build_abyss_wave_scenario_payload,
    load_enemy_type_mapping_from_json,
    write_abyss_wave_scenario_payload,
)
from .artifact_runner import (
    DEFAULT_GCSIM_RUNS_DIR,
    GcsimArtifactRunResult,
    run_active_gcsim_artifact,
)
from .runtime_probe import DEFAULT_GO_PROBE_TIMEOUT_SECONDS
from .enemy_type_registry import load_gcsim_enemy_type_registry_from_go_source
from .snap_monster_titles import (
    DEFAULT_SNAP_MONSTER_GITHUB_URL,
    SNAP_CACHE_STATUS_REMOTE_NOT_NEEDED,
    SNAP_REFRESH_STATUS_NOT_NEEDED,
    SnapJsonFetcher,
    SnapMonsterTitleIndex,
    load_cached_snap_monster_title_index,
    load_default_remote_snap_monster_title_index,
    load_snap_monster_title_index,
    refresh_cached_snap_monster_title_index,
)


ArtifactRunFunc = Callable[..., GcsimArtifactRunResult]


class AbyssWaveScenarioSmokeError(ValueError):
    """Raised for controlled CLI input/load errors."""


def main(
    argv: list[str] | None = None,
    *,
    artifact_run_func: ArtifactRunFunc = run_active_gcsim_artifact,
    snap_fetcher: SnapJsonFetcher | None = None,
    stdout: TextIO | None = None,
) -> int:
    output = stdout or sys.stdout
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        result = run_abyss_wave_scenario_smoke(
            args,
            artifact_run_func=artifact_run_func,
            snap_fetcher=snap_fetcher,
        )
    except AbyssWaveScenarioSmokeError as exc:
        report = {"success": False, "status": "input_error", "error": str(exc)}
        _print_report(report, format_name=args.format, stdout=output)
        return 2

    _print_report(result, format_name=args.format, stdout=output)
    return 0 if result.get("success") else 1


def run_abyss_wave_scenario_smoke(
    args: argparse.Namespace,
    *,
    artifact_run_func: ArtifactRunFunc = run_active_gcsim_artifact,
    snap_fetcher: SnapJsonFetcher | None = None,
) -> dict[str, Any]:
    data = _load_source_data(args)
    if data is None:
        source_label = (
            f"period_start={args.period_start} floor={args.floor}"
            if args.period_start
            else f"current cached period floor={args.floor}"
        )
        return {
            "success": False,
            "status": "source_data_missing",
            "error": f"Abyss source-data cache not found for {source_label}.",
        }

    enemy_type_mapping = _enemy_type_mapping_from_args(args)
    enemy_type_registry = _enemy_type_registry_from_args(args)
    direct_snap_title_index = _direct_snap_title_index_from_args(args, fetcher=snap_fetcher)
    build, snap_title_index, snap_cache, steps = _build_with_snap_flow(
        data,
        args,
        enemy_type_mapping=enemy_type_mapping,
        enemy_type_registry=enemy_type_registry,
        direct_snap_title_index=direct_snap_title_index,
        snap_fetcher=snap_fetcher,
    )
    report: dict[str, Any] = {
        "success": False,
        "status": "not_ready",
        "source": _source_report(data, explicit_period_start=args.period_start),
        "audit": build.audit.to_dict(),
        "scenario_path": "",
        "snap_cache": snap_cache,
        "steps": steps,
    }
    if snap_title_index is not None:
        report["snap_source"] = snap_title_index.source_report()
    if not build.ready or build.payload is None:
        return report

    scenario_path = _scenario_output_path(args)
    steps.append("building_abyss_wave_scenario")
    write_abyss_wave_scenario_payload(build.payload, scenario_path)
    report.update(
        {
            "success": True,
            "status": "scenario_written",
            "scenario_path": str(scenario_path),
        }
    )

    if args.config:
        steps.append("running_gcsim_artifact")
        config_path = Path(args.config)
        config_text = config_path.read_text(encoding="utf-8-sig")
        run_result = artifact_run_func(
            config_text,
            gtt_wave_scenario=scenario_path,
            store_dir=args.store_dir,
            run_dir=args.run_dir,
            timeout_seconds=args.timeout,
        )
        report.update(
            {
                "success": run_result.success,
                "status": "run_passed" if run_result.success else "run_failed",
                "run_result": run_result.to_dict(),
            }
        )
    report["steps"] = steps
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a provisional GTT wave scenario JSON v1 from cached Abyss "
            "source data and optionally run the active GTT-GCSIM artifact."
        )
    )
    parser.add_argument("--period-start", default=None, help="Explicit cached period YYYY-MM-DD.")
    parser.add_argument("--floor", type=int, default=12, help="Abyss floor cache key.")
    parser.add_argument(
        "--period-path",
        default=None,
        help="Optional HoYoLAB period JSON path for current-period mode.",
    )
    parser.add_argument("--cache-dir", default=None, help="Optional Abyss source-data cache dir.")
    parser.add_argument("--chamber", type=int, required=True, help="Abyss chamber number.")
    parser.add_argument("--side", type=int, required=True, help="Abyss side number.")
    parser.add_argument(
        "--enemy-type-map",
        default=None,
        help=(
            "Explicit JSON mapping from Abyss enemy source identities to GCSIM enemy type. "
            "Manual records act as overrides; use --gcsim-enemy-registry-source for automatic "
            "known target type matching."
        ),
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
    parser.add_argument("--scenario-out", default=None, help="Path for generated scenario JSON.")
    parser.add_argument("--config", default=None, help="Optional caller-provided GCSIM config path.")
    parser.add_argument(
        "--solo-target-mode",
        action="store_true",
        help="Build scenario from the selected solo target of each wave instead of all targets.",
    )
    parser.add_argument("--store-dir", default=None, help="Optional GCSIM engine store root.")
    parser.add_argument("--run-dir", default=None, help="Optional output run directory.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_GO_PROBE_TIMEOUT_SECONDS,
        help="Timeout in seconds for optional artifact run.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def _load_source_data(args: argparse.Namespace) -> AbyssFloorSourceData | None:
    try:
        if args.period_start:
            return load_cached_abyss_floor_source_data(
                args.period_start,
                floor=args.floor,
                cache_dir=args.cache_dir,
            )
        return load_current_cached_abyss_floor_source_data(
            floor=args.floor,
            period_path=args.period_path,
            cache_dir=args.cache_dir,
        )
    except (AbyssSourceDataCacheError, ValueError, OSError) as exc:
        raise AbyssWaveScenarioSmokeError(str(exc)) from exc


def _enemy_type_mapping_from_args(args: argparse.Namespace):
    if not args.enemy_type_map:
        return None
    try:
        return load_enemy_type_mapping_from_json(args.enemy_type_map)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise AbyssWaveScenarioSmokeError(str(exc)) from exc


def _enemy_type_registry_from_args(args: argparse.Namespace):
    if not args.gcsim_enemy_registry_source:
        return None
    try:
        return load_gcsim_enemy_type_registry_from_go_source(
            args.gcsim_enemy_registry_source
        )
    except (ValueError, OSError) as exc:
        raise AbyssWaveScenarioSmokeError(str(exc)) from exc


def _direct_snap_title_index_from_args(
    args: argparse.Namespace,
    *,
    fetcher: SnapJsonFetcher | None = None,
):
    managed_requested = bool(
        args.use_cached_snap_monster_json or args.refresh_snap_monster_json_if_needed
    )
    if managed_requested and (args.snap_monster_json or args.use_default_remote_snap_monster_json):
        raise AbyssWaveScenarioSmokeError(
            "Use either direct Snap input or managed Snap cache/refresh options, not both."
        )
    if args.snap_monster_json and args.use_default_remote_snap_monster_json:
        raise AbyssWaveScenarioSmokeError(
            "Use either --snap-monster-json or --use-default-remote-snap-monster-json, not both."
        )
    if args.use_default_remote_snap_monster_json:
        try:
            return load_default_remote_snap_monster_title_index(fetcher=fetcher)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            raise AbyssWaveScenarioSmokeError(str(exc)) from exc
    if not args.snap_monster_json:
        return None
    try:
        return load_snap_monster_title_index(args.snap_monster_json, fetcher=fetcher)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise AbyssWaveScenarioSmokeError(str(exc)) from exc


def _build_with_snap_flow(
    data: AbyssFloorSourceData,
    args: argparse.Namespace,
    *,
    enemy_type_mapping,
    enemy_type_registry,
    direct_snap_title_index: SnapMonsterTitleIndex | None,
    snap_fetcher: SnapJsonFetcher | None,
):
    steps = ["matching_enemy_names_primary"]
    fact_dps_multi_target_enabled = _fact_dps_multi_target_enabled_from_args(args)
    if direct_snap_title_index is not None:
        steps.append("checking_direct_snap_titles")
        build = build_abyss_wave_scenario_payload(
            data,
            chamber=args.chamber,
            side=args.side,
            enemy_type_mapping=enemy_type_mapping,
            enemy_type_registry=enemy_type_registry,
            snap_title_index=direct_snap_title_index,
            fact_dps_multi_target_enabled=fact_dps_multi_target_enabled,
        )
        return build, direct_snap_title_index, _snap_flow_report(phase="direct"), steps

    primary = build_abyss_wave_scenario_payload(
        data,
        chamber=args.chamber,
        side=args.side,
        enemy_type_mapping=enemy_type_mapping,
        enemy_type_registry=enemy_type_registry,
        fact_dps_multi_target_enabled=fact_dps_multi_target_enabled,
    )
    use_managed = bool(
        args.use_cached_snap_monster_json
        or args.refresh_snap_monster_json_if_needed
    )
    if not use_managed or not primary.audit.missing_type_mapping_rows:
        return (
            primary,
            None,
            _snap_flow_report(
                phase="primary",
                cache_status=SNAP_CACHE_STATUS_REMOTE_NOT_NEEDED,
                refresh_status=SNAP_REFRESH_STATUS_NOT_NEEDED,
            ),
            steps,
        )

    steps.append("checking_cached_snap_titles")
    cache_load = load_cached_snap_monster_title_index(args.snap_monster_cache_path)
    cache_report = _snap_flow_report(
        phase="cache",
        cache_status=cache_load.status,
        refresh_status=SNAP_REFRESH_STATUS_NOT_NEEDED,
        cache_path=cache_load.cache_path,
        error=cache_load.error,
    )
    if cache_load.ready:
        cached = build_abyss_wave_scenario_payload(
            data,
            chamber=args.chamber,
            side=args.side,
            enemy_type_mapping=enemy_type_mapping,
            enemy_type_registry=enemy_type_registry,
            snap_title_index=cache_load.index,
            fact_dps_multi_target_enabled=fact_dps_multi_target_enabled,
        )
        if cached.ready or not args.refresh_snap_monster_json_if_needed:
            return cached, cache_load.index, cache_report, steps
    elif not args.refresh_snap_monster_json_if_needed:
        return primary, None, cache_report, steps

    steps.append("refreshing_snap_metadata")
    refresh = refresh_cached_snap_monster_title_index(
        args.snap_monster_cache_path,
        source_url=DEFAULT_SNAP_MONSTER_GITHUB_URL,
        fetcher=snap_fetcher,
    )
    refresh_report = {**cache_report, **refresh.to_dict(), "phase": "refreshed"}
    if cache_report.get("error"):
        refresh_report["cache_error"] = cache_report["error"]
    if not refresh.ready:
        raise AbyssWaveScenarioSmokeError(refresh.error or refresh.status)
    steps.append("rechecking_snap_titles_after_refresh")
    refreshed = build_abyss_wave_scenario_payload(
        data,
        chamber=args.chamber,
        side=args.side,
        enemy_type_mapping=enemy_type_mapping,
        enemy_type_registry=enemy_type_registry,
        snap_title_index=refresh.index,
        fact_dps_multi_target_enabled=fact_dps_multi_target_enabled,
    )
    return refreshed, refresh.index, refresh_report, steps


def _fact_dps_multi_target_enabled_from_args(args: argparse.Namespace) -> bool:
    return not bool(getattr(args, "solo_target_mode", False))


def _snap_flow_report(
    *,
    phase: str,
    cache_status: str = "",
    refresh_status: str = "",
    cache_path: str = "",
    error: str = "",
) -> dict[str, Any]:
    return {
        "phase": phase,
        "cache_status": cache_status,
        "refresh_status": refresh_status,
        "cache_path": cache_path,
        "error": error,
    }


def _scenario_output_path(args: argparse.Namespace) -> Path:
    if args.scenario_out:
        return Path(args.scenario_out)
    run_dir = Path(args.run_dir) if args.run_dir else _new_smoke_run_dir()
    return run_dir / "gtt_wave_scenario.json"


def _new_smoke_run_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return DEFAULT_GCSIM_RUNS_DIR / f"abyss-wave-scenario-{stamp}"


def _source_report(
    data: AbyssFloorSourceData,
    *,
    explicit_period_start: str | None,
) -> dict[str, Any]:
    return {
        "mode": "explicit_period" if explicit_period_start else "current_cached_period",
        "period_start": data.period.start_date,
        "floor": data.floor,
    }


def _print_report(report: dict[str, Any], *, format_name: str, stdout: TextIO) -> None:
    if format_name == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), file=stdout)
    else:
        print(_format_text(report), file=stdout)


def _format_text(report: dict[str, Any]) -> str:
    lines = [
        "Abyss GTT wave scenario smoke",
        f"success={str(bool(report.get('success'))).lower()} status={report.get('status', '')}",
    ]
    source = report.get("source")
    if isinstance(source, dict):
        lines.append(
            "source="
            f"mode={source.get('mode', '')} "
            f"period_start={source.get('period_start', '')} "
            f"floor={source.get('floor', '')}"
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
    steps = report.get("steps") or []
    if steps:
        lines.append("steps=" + ",".join(str(step) for step in steps))
    audit = report.get("audit")
    if isinstance(audit, dict):
        lines.append(
            "audit="
            f"ready={str(bool(audit.get('ready'))).lower()} "
            f"chamber={audit.get('chamber', '')} "
            f"side={audit.get('side', '')} "
            f"waves={audit.get('wave_count', '')} "
            f"source_rows={audit.get('source_enemy_row_count', '')} "
            f"targets={audit.get('generated_target_count', '')}"
        )
        warnings = audit.get("warnings") or []
        if warnings:
            lines.append("warnings=" + ",".join(str(item) for item in warnings))
        missing_hp = audit.get("missing_hp_rows") or []
        missing_level = audit.get("missing_level_rows") or []
        missing_type = audit.get("missing_type_mapping_rows") or []
        ambiguous_type = audit.get("ambiguous_type_mapping_rows") or []
        if missing_hp:
            lines.append(f"missing_hp_rows={len(missing_hp)}")
        if missing_level:
            lines.append(f"missing_level_rows={len(missing_level)}")
        if missing_type:
            lines.append(f"missing_type_mapping_rows={len(missing_type)}")
        if ambiguous_type:
            lines.append(f"ambiguous_type_mapping_rows={len(ambiguous_type)}")
    if report.get("scenario_path"):
        lines.append(f"scenario={report['scenario_path']}")
    run_result = report.get("run_result")
    if isinstance(run_result, dict):
        summary = run_result.get("summary") if isinstance(run_result.get("summary"), dict) else {}
        lines.extend(
            [
                "artifact_run="
                f"success={str(bool(run_result.get('success'))).lower()} "
                f"status={run_result.get('status', '')}",
                (
                    "summary="
                    f"dps_mean={_format_number(summary.get('dps_mean'))} "
                    f"duration_mean={_format_number(summary.get('duration_mean'))} "
                    f"total_damage_mean={_format_number(summary.get('total_damage_mean'))} "
                    f"sim_version={summary.get('sim_version') or ''}"
                ),
            ]
        )
    if report.get("error"):
        lines.append(f"error={report['error']}")
    return "\n".join(lines)


def _format_number(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return f"{value:g}"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
