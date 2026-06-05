"""Dev CLI for cached Abyss source-data -> GTT wave scenario smoke runs.

This command is a backend-only bridge around the provisional
`abyss_wave_scenario` adapter. It loads already-cached typed Abyss source data,
requires an explicit Abyss enemy source identity -> GCSIM enemy type mapping,
writes a schema-v1 payload, and can optionally pass that payload to the existing
active GTT-GCSIM artifact runner with a caller provided config. It does not
refresh network data, generate account/team GCSIM configs, map
character/weapon/artifact keys, or model final Abyss wave policy.
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


ArtifactRunFunc = Callable[..., GcsimArtifactRunResult]


class AbyssWaveScenarioSmokeError(ValueError):
    """Raised for controlled CLI input/load errors."""


def main(
    argv: list[str] | None = None,
    *,
    artifact_run_func: ArtifactRunFunc = run_active_gcsim_artifact,
    stdout: TextIO | None = None,
) -> int:
    output = stdout or sys.stdout
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        result = run_abyss_wave_scenario_smoke(args, artifact_run_func=artifact_run_func)
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
    build = build_abyss_wave_scenario_payload(
        data,
        chamber=args.chamber,
        side=args.side,
        enemy_type_mapping=enemy_type_mapping,
    )
    report: dict[str, Any] = {
        "success": False,
        "status": "not_ready",
        "source": _source_report(data, explicit_period_start=args.period_start),
        "audit": build.audit.to_dict(),
        "scenario_path": "",
    }
    if not build.ready or build.payload is None:
        return report

    scenario_path = _scenario_output_path(args)
    write_abyss_wave_scenario_payload(build.payload, scenario_path)
    report.update(
        {
            "success": True,
            "status": "scenario_written",
            "scenario_path": str(scenario_path),
        }
    )

    if args.config:
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
            "When omitted, the command prints audit and exits nonzero."
        ),
    )
    parser.add_argument("--scenario-out", default=None, help="Path for generated scenario JSON.")
    parser.add_argument("--config", default=None, help="Optional caller-provided GCSIM config path.")
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
