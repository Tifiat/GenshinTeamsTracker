"""Backend/dev smoke case catalog for manual config + generated Abyss scenarios.

The cases in this module are control smokes for the current GTT-GCSIM backend
bridge. They intentionally use a committed hand-written config fixture and
cached Abyss source-data; they do not generate account/team configs, make DPS
benchmark claims, refresh Abyss data, or duplicate artifact runner logic.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any, TextIO

from .abyss_wave_scenario_smoke import (
    ArtifactRunFunc,
    run_abyss_wave_scenario_smoke,
)
from .artifact_runner import run_active_gcsim_artifact
from .enemy_type_registry import find_default_gcsim_enemy_shortcut_source
from .engine_store import PROJECT_ROOT
from .runtime_probe import DEFAULT_GO_PROBE_TIMEOUT_SECONDS
from .snap_monster_titles import SnapJsonFetcher


SMOKE_FIXTURE_DIR = PROJECT_ROOT / "run_workspace" / "gcsim" / "smoke_fixtures"
MANUAL_CONFIG_MINIMAL_PATH = SMOKE_FIXTURE_DIR / "manual_config_minimal.txt"
DEFAULT_ABYSS_SOURCE_CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "abyss" / "source_data"

CASE_ABYSS_2026_04_16_F12_C3_S2_MANUAL_CONFIG = (
    "abyss_2026_04_16_f12_c3_s2_manual_config"
)


@dataclass(frozen=True, slots=True)
class GcsimSmokeCase:
    case_id: str
    description: str
    period_start: str
    floor: int
    chamber: int
    side: int
    expected_enemy: str
    expected_gcsim_type: str
    expected_method: str
    manual_config_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "description": self.description,
            "period_start": self.period_start,
            "floor": self.floor,
            "chamber": self.chamber,
            "side": self.side,
            "expected_enemy": self.expected_enemy,
            "expected_gcsim_type": self.expected_gcsim_type,
            "expected_method": self.expected_method,
            "manual_config_path": str(self.manual_config_path),
        }


SMOKE_CASES: dict[str, GcsimSmokeCase] = {
    CASE_ABYSS_2026_04_16_F12_C3_S2_MANUAL_CONFIG: GcsimSmokeCase(
        case_id=CASE_ABYSS_2026_04_16_F12_C3_S2_MANUAL_CONFIG,
        description=(
            "Manual GCSIM config plus generated cached Abyss wave scenario for "
            "2026-04-16 Floor 12 Chamber 3 Side 2."
        ),
        period_start="2026-04-16",
        floor=12,
        chamber=3,
        side=2,
        expected_enemy="Tenebrous Papilla: Type II",
        expected_gcsim_type="tenebrouspapillatypei",
        expected_method="snap_title_contains_target",
        manual_config_path=MANUAL_CONFIG_MINIMAL_PATH,
    ),
}


def get_smoke_case(case_id: str) -> GcsimSmokeCase:
    try:
        return SMOKE_CASES[str(case_id)]
    except KeyError as exc:
        known = ", ".join(sorted(SMOKE_CASES))
        raise ValueError(f"Unknown GCSIM smoke case {case_id!r}. Known cases: {known}") from exc


def run_smoke_case(
    case_id: str,
    *,
    registry_source: str | Path | None = None,
    cache_dir: str | Path | None = None,
    snap_cache_path: str | Path | None = None,
    run_dir: str | Path | None = None,
    store_dir: str | Path | None = None,
    timeout_seconds: int = DEFAULT_GO_PROBE_TIMEOUT_SECONDS,
    artifact_run_func: ArtifactRunFunc = run_active_gcsim_artifact,
    snap_fetcher: SnapJsonFetcher | None = None,
) -> dict[str, Any]:
    case = get_smoke_case(case_id)
    registry_path = _registry_source_path(registry_source)
    args = argparse.Namespace(
        period_start=case.period_start,
        floor=case.floor,
        period_path=None,
        cache_dir=str(cache_dir or DEFAULT_ABYSS_SOURCE_CACHE_DIR),
        chamber=case.chamber,
        side=case.side,
        enemy_type_map=None,
        gcsim_enemy_registry_source=str(registry_path),
        snap_monster_json=None,
        use_default_remote_snap_monster_json=False,
        use_cached_snap_monster_json=True,
        refresh_snap_monster_json_if_needed=True,
        snap_monster_cache_path=None if snap_cache_path is None else str(snap_cache_path),
        scenario_out=None,
        config=str(case.manual_config_path),
        store_dir=None if store_dir is None else str(store_dir),
        run_dir=None if run_dir is None else str(run_dir),
        timeout=int(timeout_seconds),
        format="json",
    )
    result = run_abyss_wave_scenario_smoke(
        args,
        artifact_run_func=artifact_run_func,
        snap_fetcher=snap_fetcher,
    )
    return _case_report(case, registry_path=registry_path, result=result)


def main(
    argv: list[str] | None = None,
    *,
    stdout: TextIO | None = None,
    artifact_run_func: ArtifactRunFunc = run_active_gcsim_artifact,
    snap_fetcher: SnapJsonFetcher | None = None,
) -> int:
    output = stdout or sys.stdout
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        payload = run_smoke_case(
            args.case,
            registry_source=args.gcsim_enemy_registry_source,
            cache_dir=args.cache_dir,
            snap_cache_path=args.snap_monster_cache_path,
            run_dir=args.run_dir,
            store_dir=args.store_dir,
            timeout_seconds=args.timeout,
            artifact_run_func=artifact_run_func,
            snap_fetcher=snap_fetcher,
        )
    except (OSError, ValueError) as exc:
        payload = {"success": False, "status": "input_error", "error": str(exc)}
        _print_report(payload, format_name=args.format, stdout=output)
        return 2
    _print_report(payload, format_name=args.format, stdout=output)
    return 0 if payload.get("success") else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a named backend/dev GCSIM smoke case."
    )
    parser.add_argument("--case", required=True, choices=sorted(SMOKE_CASES))
    parser.add_argument(
        "--gcsim-enemy-registry-source",
        default=None,
        help="Optional local GCSIM pkg/shortcut/enemies_gen.go source.",
    )
    parser.add_argument("--cache-dir", default=None, help="Optional Abyss source-data cache dir.")
    parser.add_argument(
        "--snap-monster-cache-path",
        default=None,
        help="Optional managed Snap Monster.json cache path for tests/dev diagnostics.",
    )
    parser.add_argument("--run-dir", default=None, help="Optional output run directory.")
    parser.add_argument("--store-dir", default=None, help="Optional GCSIM engine store root.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_GO_PROBE_TIMEOUT_SECONDS,
        help="Timeout in seconds for the artifact process.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def _registry_source_path(registry_source: str | Path | None) -> Path:
    if registry_source:
        path = Path(registry_source)
    else:
        path = find_default_gcsim_enemy_shortcut_source()
        if path is None:
            raise ValueError(
                "No default GCSIM enemies_gen.go source found; pass "
                "--gcsim-enemy-registry-source."
            )
    if not path.is_file():
        raise ValueError(f"GCSIM enemy registry source not found: {path}")
    return path


def _case_report(
    case: GcsimSmokeCase,
    *,
    registry_path: Path,
    result: dict[str, Any],
) -> dict[str, Any]:
    audit = result.get("audit") if isinstance(result.get("audit"), dict) else {}
    method_counts: dict[str, int] = {}
    for detail in audit.get("type_mapping_details") or []:
        if not isinstance(detail, dict):
            continue
        method = str(detail.get("method") or "")
        if method:
            method_counts[method] = method_counts.get(method, 0) + 1
    run_result = result.get("run_result") if isinstance(result.get("run_result"), dict) else {}
    summary = run_result.get("summary") if isinstance(run_result.get("summary"), dict) else {}
    return {
        "success": bool(result.get("success")),
        "status": result.get("status", ""),
        "case": case.to_dict(),
        "registry_source": str(registry_path),
        "manual_config_path": str(case.manual_config_path),
        "source": result.get("source"),
        "scenario_path": result.get("scenario_path", ""),
        "wave_count": audit.get("wave_count"),
        "target_count": audit.get("generated_target_count"),
        "enemy_resolution_method_counts": method_counts,
        "expected": {
            "enemy": case.expected_enemy,
            "gcsim_type": case.expected_gcsim_type,
            "method": case.expected_method,
        },
        "snap_cache": result.get("snap_cache"),
        "steps": result.get("steps", []),
        "artifact": {
            "source": run_result.get("artifact_source", ""),
            "active_artifact_status": run_result.get("active_artifact_status", ""),
            "shipped_fallback_status": run_result.get("shipped_fallback_status", ""),
            "preflight_status": run_result.get("artifact_preflight_status", ""),
            "observed_gtt_patch_version": run_result.get("observed_gtt_patch_version", ""),
            "observed_gtt_capabilities": run_result.get("observed_gtt_capabilities", []),
            "run_status": run_result.get("status", ""),
            "timing_seconds": run_result.get("timing_seconds"),
        },
        "summary": {
            "schema_version": summary.get("schema_version", ""),
            "sim_version": summary.get("sim_version", ""),
            "duration_mean": summary.get("duration_mean"),
            "dps_mean": summary.get("dps_mean"),
            "total_damage_mean": summary.get("total_damage_mean"),
            "warnings": summary.get("warnings", []),
            "failed_actions": summary.get("failed_actions", []),
            "incomplete_characters": summary.get("incomplete_characters", []),
        },
        "raw_result": result,
    }


def _print_report(payload: dict[str, Any], *, format_name: str, stdout: TextIO) -> None:
    if format_name == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), file=stdout)
    else:
        print(_format_text(payload), file=stdout)


def _format_text(payload: dict[str, Any]) -> str:
    case = payload.get("case") if isinstance(payload.get("case"), dict) else {}
    artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    snap_cache = payload.get("snap_cache") if isinstance(payload.get("snap_cache"), dict) else {}
    lines = [
        "GCSIM smoke case",
        f"success={str(bool(payload.get('success'))).lower()} status={payload.get('status', '')}",
        f"case={case.get('case_id', '')}",
        (
            "selection="
            f"period_start={case.get('period_start', '')} "
            f"floor={case.get('floor', '')} "
            f"chamber={case.get('chamber', '')} "
            f"side={case.get('side', '')}"
        ),
        f"manual_config={payload.get('manual_config_path', '')}",
        f"scenario={payload.get('scenario_path', '')}",
        (
            "scenario_counts="
            f"waves={payload.get('wave_count', '')} "
            f"targets={payload.get('target_count', '')}"
        ),
        "enemy_resolution_method_counts="
        + json.dumps(payload.get("enemy_resolution_method_counts") or {}, sort_keys=True),
        (
            "snap_cache="
            f"phase={snap_cache.get('phase', '')} "
            f"cache_status={snap_cache.get('cache_status', '')} "
            f"refresh_status={snap_cache.get('refresh_status', '')}"
        ),
        (
            "artifact="
            f"source={artifact.get('source', '')} "
            f"active_status={artifact.get('active_artifact_status', '')} "
            f"preflight={artifact.get('preflight_status', '')} "
            f"run_status={artifact.get('run_status', '')}"
        ),
        (
            "summary="
            f"dps_mean={_format_number(summary.get('dps_mean'))} "
            f"duration_mean={_format_number(summary.get('duration_mean'))} "
            f"total_damage_mean={_format_number(summary.get('total_damage_mean'))} "
            f"sim_version={summary.get('sim_version') or ''}"
        ),
    ]
    steps = payload.get("steps") or []
    if steps:
        lines.append("steps=" + ",".join(str(step) for step in steps))
    if payload.get("error"):
        lines.append(f"error={payload['error']}")
    return "\n".join(lines)


def _format_number(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return f"{value:g}"
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
