"""Dev CLI for running a config through the active built GTT-GCSIM artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .artifact_runner import run_active_gcsim_artifact
from .runtime_probe import DEFAULT_GO_PROBE_TIMEOUT_SECONDS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run a GCSIM config through the active built gtt-gcsim.exe and "
            "print a minimal JSON result summary."
        )
    )
    parser.add_argument("--config", required=True, help="Path to a GCSIM config text file.")
    parser.add_argument(
        "--gtt-wave-scenario",
        default=None,
        help="Optional path to a GTT wave scenario JSON payload.",
    )
    parser.add_argument("--store-dir", default=None, help="Optional engine store root.")
    parser.add_argument("--run-dir", default=None, help="Optional output run directory.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_GO_PROBE_TIMEOUT_SECONDS,
        help="Timeout in seconds for the artifact process.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    config_text = config_path.read_text(encoding="utf-8-sig")
    result = run_active_gcsim_artifact(
        config_text,
        gtt_wave_scenario=args.gtt_wave_scenario,
        store_dir=args.store_dir,
        run_dir=args.run_dir,
        timeout_seconds=args.timeout,
    )
    if args.format == "json":
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, sort_keys=True))
    else:
        print(_format_text(result))
    return 0 if result.success else 1


def _format_text(result) -> str:
    summary = result.summary
    lines = [
        "GCSIM artifact smoke",
        f"success={str(result.success).lower()} status={result.status}",
        f"engine_id={result.engine_id}",
        f"artifact={result.artifact_path}",
        f"run_dir={result.run_dir}",
        f"gtt_wave_scenario={result.gtt_wave_scenario_path}",
        f"result_json={result.result_path}",
        (
            "summary="
            f"dps_mean={_format_number(summary.dps_mean)} "
            f"duration_mean={_format_number(summary.duration_mean)} "
            f"total_damage_mean={_format_number(summary.total_damage_mean)} "
            f"sim_version={summary.sim_version or ''}"
        ),
        (
            "counts="
            f"warnings={len(summary.warnings)} "
            f"failed_actions={len(summary.failed_actions)} "
            f"incomplete_characters={len(summary.incomplete_characters)}"
        ),
    ]
    if result.stdout:
        lines.append(f"stdout={result.stdout}")
    if result.stderr:
        lines.append(f"stderr={result.stderr}")
    if result.error:
        lines.append(f"error={result.error}")
    return "\n".join(lines)


def _format_number(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:g}"


if __name__ == "__main__":
    raise SystemExit(main())
