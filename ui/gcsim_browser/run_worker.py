from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from hoyolab_export.paths import PROJECT_ROOT
from run_workspace.gcsim.account_prepared_config import (
    DEFAULT_DEV_ENERGY_OVERRIDE_LINE,
    build_account_prepared_full_config_report,
)


ERROR_PREPARE_NOT_READY = "prepare_not_ready"
ERROR_CONFIG_PREPARE_ERROR = "config_prepare_error"
ERROR_ARTIFACT_PREFLIGHT_FAILED = "artifact_preflight_failed"
ERROR_GCSIM_RUNTIME_ERROR = "gcsim_runtime_error"
ERROR_CONFIG_PARSE_OR_ROTATION_ERROR = "config_parse_or_rotation_error"
ERROR_UNKNOWN = "unknown_error"


@dataclass(frozen=True, slots=True)
class GcsimBrowserRunRequest:
    db_path: str
    team_names: tuple[str, ...]
    team_index: int
    chamber: int
    side: int
    rotation_shell_text: str
    run_root: str = ""


class GcsimBrowserRunWorker(QObject):
    finished = Signal(dict)

    def __init__(self, request: GcsimBrowserRunRequest) -> None:
        super().__init__()
        self._request = request

    @Slot()
    def run(self) -> None:
        self.finished.emit(run_gcsim_browser_selected_chamber(self._request))


def run_gcsim_browser_selected_chamber(
    request: GcsimBrowserRunRequest,
) -> dict[str, Any]:
    if not request.team_names:
        return {
            "success": False,
            "error_category": ERROR_PREPARE_NOT_READY,
            "error": "Selected team has no characters.",
            "selection": _selection_report(request),
        }

    run_dir = _new_run_dir(request.run_root)
    rotation_shell_path = run_dir / "rotation_shell.from_editor.txt"
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        rotation_shell_path.write_text(request.rotation_shell_text, encoding="utf-8")
        report = build_account_prepared_full_config_report(
            db_path=request.db_path,
            team_names=request.team_names,
            rotation_shell_path=rotation_shell_path,
            run_dir=run_dir,
            write_config=True,
            run_abyss_smoke=True,
            abyss_chamber=request.chamber,
            abyss_side=request.side,
            dev_energy_override_line=DEFAULT_DEV_ENERGY_OVERRIDE_LINE,
        )
        payload = report.to_dict()
    except Exception as exc:
        return {
            "success": False,
            "error_category": ERROR_CONFIG_PREPARE_ERROR,
            "error": str(exc),
            "selection": _selection_report(request),
            "run_dir": str(run_dir),
            "rotation_shell_path": str(rotation_shell_path),
        }

    payload["selection"] = _selection_report(request)
    payload["run_dir"] = str(run_dir)
    payload["rotation_shell_path"] = str(rotation_shell_path)
    payload["error_category"] = classify_gcsim_browser_run_payload(payload)
    payload["success"] = bool(
        payload.get("ready")
        and isinstance(payload.get("smoke"), dict)
        and payload["smoke"].get("success")
    )
    return payload


def classify_gcsim_browser_run_payload(payload: dict[str, Any]) -> str:
    issues = _issue_statuses(payload)
    if any("shell" in status or "rotation" in status for status in issues):
        return ERROR_CONFIG_PARSE_OR_ROTATION_ERROR

    smoke = payload.get("smoke") if isinstance(payload.get("smoke"), dict) else {}
    run_result = (
        smoke.get("run_result")
        if isinstance(smoke.get("run_result"), dict)
        else {}
    )
    preflight_status = str(run_result.get("artifact_preflight_status") or "")
    run_status = str(run_result.get("status") or smoke.get("status") or "")
    if preflight_status and preflight_status != "gtt_wave_scenario_contract_ready":
        return ERROR_ARTIFACT_PREFLIGHT_FAILED
    if "preflight" in run_status or "contract" in run_status:
        return ERROR_ARTIFACT_PREFLIGHT_FAILED

    if payload.get("ready") is False:
        return ERROR_PREPARE_NOT_READY

    if run_result and not run_result.get("success", False):
        return ERROR_GCSIM_RUNTIME_ERROR
    if smoke and not smoke.get("success", False):
        status = str(smoke.get("status") or "")
        if status == "run_failed":
            return ERROR_GCSIM_RUNTIME_ERROR
        return ERROR_UNKNOWN

    if payload.get("ready") and smoke.get("success"):
        return ""
    return ERROR_UNKNOWN


def format_gcsim_browser_run_report(payload: dict[str, Any]) -> str:
    selection = payload.get("selection") if isinstance(payload.get("selection"), dict) else {}
    smoke = payload.get("smoke") if isinstance(payload.get("smoke"), dict) else {}
    run_result = (
        smoke.get("run_result")
        if isinstance(smoke.get("run_result"), dict)
        else {}
    )
    summary = (
        run_result.get("summary")
        if isinstance(run_result.get("summary"), dict)
        else {}
    )
    lines = [
        "Run selected chamber",
        (
            f"Team: {selection.get('team_label', '-')} "
            f"/ Side {selection.get('side', '-')} "
            f"/ C{selection.get('chamber', '-')}"
        ),
        f"Status: {smoke.get('status') or payload.get('status') or '-'}",
        f"Error category: {payload.get('error_category') or '-'}",
        f"Config path: {payload.get('config_path') or '-'}",
        f"Scenario path: {smoke.get('scenario_path') or '-'}",
        (
            "Observed clear time: "
            f"{_format_number(summary.get('duration_mean')) or '-'}"
        ),
        f"DPS mean: {_format_number(summary.get('dps_mean')) or '-'}",
        (
            "Total damage mean: "
            f"{_format_number(summary.get('total_damage_mean')) or '-'}"
        ),
        (
            "Artifact preflight: "
            f"{run_result.get('artifact_preflight_status') or '-'}"
        ),
        "DPS correctness claim: false",
    ]

    mapping_counts = smoke.get("enemy_mapping_method_counts")
    if isinstance(mapping_counts, dict) and mapping_counts:
        lines.append(
            "Enemy mapping methods: "
            + ", ".join(f"{key}:{value}" for key, value in sorted(mapping_counts.items()))
        )
    scenario_summary = smoke.get("scenario_summary")
    if isinstance(scenario_summary, dict) and scenario_summary:
        lines.append(
            "Scenario: "
            f"waves={scenario_summary.get('wave_count', '-')} "
            f"targets={scenario_summary.get('target_count', '-')} "
            f"spawn_policy={scenario_summary.get('spawn_policy', '-')}"
        )

    failed_buckets = _failed_action_bucket_summary(summary.get("failed_actions") or [])
    if failed_buckets:
        lines.append(f"Failed action buckets: {failed_buckets}")
    incomplete = summary.get("incomplete_characters") or []
    if incomplete:
        lines.append(
            "Incomplete characters: " + ", ".join(str(item) for item in incomplete)
        )

    team = payload.get("team") if isinstance(payload.get("team"), dict) else {}
    characters = team.get("characters") if isinstance(team.get("characters"), list) else []
    if characters:
        lines.extend(["", "Characters:"])
        for character in characters:
            if not isinstance(character, dict):
                continue
            lines.append("  - " + _character_line(character))

    warnings = payload.get("warnings") or []
    if warnings:
        lines.extend(["", "Warnings:", *[f"  - {warning}" for warning in warnings]])
    error = str(payload.get("error") or "")
    if error:
        lines.extend(["", f"Error: {error}"])
    return "\n".join(lines)


def _character_line(character: dict[str, Any]) -> str:
    account = character.get("account_character") if isinstance(character.get("account_character"), dict) else {}
    weapon = character.get("weapon") if isinstance(character.get("weapon"), dict) else {}
    sets = []
    for item in character.get("artifact_set_counts") or []:
        if not isinstance(item, dict):
            continue
        mapping = item.get("mapping") if isinstance(item.get("mapping"), dict) else {}
        set_name = item.get("set_uid") or item.get("set_name") or item.get("display_name")
        key = mapping.get("gcsim_key") or ""
        sets.append(f"{set_name}->{key}:{item.get('count')}")
    return (
        f"{account.get('catalog_english_name') or account.get('localized_name') or character.get('requested_name')}: "
        f"weapon_source={character.get('weapon_selection_method') or '-'} "
        f"weapon={weapon.get('catalog_english_name') or weapon.get('localized_name') or '-'} "
        f"artifact_source={character.get('artifact_source') or '-'} "
        f"sets={', '.join(sets) if sets else '-'} "
        f"talents={_talent_line(character.get('talents'))}"
    )


def _talent_line(talents: Any) -> str:
    if not isinstance(talents, dict):
        return "-"
    parts = []
    for item in talents.get("talents") or []:
        if not isinstance(item, dict):
            continue
        slot = item.get("slot") or "talent"
        displayed = item.get("displayed_level")
        gcsim = item.get("gcsim_level")
        bonus = int(item.get("parsed_constellation_bonus") or 0)
        if bonus:
            parts.append(f"{slot}:{displayed}-{bonus}->{gcsim}")
        else:
            parts.append(f"{slot}:{displayed}->{gcsim}")
    return "|".join(parts) if parts else "-"


def _failed_action_bucket_summary(buckets: list[Any]) -> str:
    parts = []
    for index, bucket in enumerate(buckets, start=1):
        parsed = bucket
        if isinstance(bucket, str):
            try:
                import json

                parsed = json.loads(bucket)
            except Exception:
                parsed = bucket
        if not isinstance(parsed, dict):
            parts.append(f"{index}:{parsed}")
            continue
        nonzero = []
        for name, stats in sorted(parsed.items()):
            if not isinstance(stats, dict):
                continue
            mean = float(stats.get("mean") or 0)
            maximum = float(stats.get("max") or 0)
            if mean or maximum:
                nonzero.append(
                    f"{name}(mean={_format_number(mean)},max={_format_number(maximum)})"
                )
        parts.append(f"{index}:{'|'.join(nonzero) if nonzero else 'none'}")
    return ";".join(parts)


def _issue_statuses(payload: dict[str, Any]) -> tuple[str, ...]:
    statuses = []
    for issue in payload.get("issues") or []:
        if isinstance(issue, dict) and issue.get("status"):
            statuses.append(str(issue["status"]))
    full_config = payload.get("full_config") if isinstance(payload.get("full_config"), dict) else {}
    for issue in full_config.get("issues") or []:
        if isinstance(issue, dict) and issue.get("status"):
            statuses.append(str(issue["status"]))
    return tuple(statuses)


def _selection_report(request: GcsimBrowserRunRequest) -> dict[str, Any]:
    return {
        "team_index": int(request.team_index),
        "team_label": f"Team {int(request.team_index) + 1}",
        "chamber": int(request.chamber),
        "side": int(request.side),
        "team_names": list(request.team_names),
    }


def _new_run_dir(run_root: str) -> Path:
    root = Path(run_root) if run_root else PROJECT_ROOT / "data" / "gcsim" / "runs"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return root / f"gcsim-browser-run-{stamp}"


def _format_number(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)):
        return f"{value:g}"
    return str(value)
