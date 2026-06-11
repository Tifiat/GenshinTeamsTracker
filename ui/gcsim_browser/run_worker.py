from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from hoyolab_export.paths import PROJECT_ROOT
from run_workspace.gcsim.readiness_summary import (
    build_gcsim_readiness_summary,
    format_gcsim_readiness_summary,
)
from run_workspace.gcsim.selected_team_config import (
    build_selected_team_full_config_report,
    report_with_dps_dummy_run,
    report_with_smoke,
    run_selected_team_abyss_smoke,
    run_selected_team_dps_dummy_artifact,
)
from run_workspace.gcsim.settings import GcsimRunSettings
from run_workspace.right_panel_prototype_view_model import (
    FACT_DPS_HP_MODE_MULTI_TARGET,
    FACT_DPS_HP_MODE_SOLO,
    MODE_ABYSS,
    MODE_DPS_DUMMY,
    RightPanelGcsimChamberResult,
)


ERROR_PREPARE_NOT_READY = "prepare_not_ready"
ERROR_CONFIG_PREPARE_ERROR = "config_prepare_error"
ERROR_ARTIFACT_PREFLIGHT_FAILED = "artifact_preflight_failed"
ERROR_GCSIM_RUNTIME_ERROR = "gcsim_runtime_error"
ERROR_CONFIG_PARSE_OR_ROTATION_ERROR = "config_parse_or_rotation_error"
ERROR_UNKNOWN = "unknown_error"
WARNING_ABYSS_PREVIEW_SCENARIO_SOURCE_MISMATCH = (
    "abyss_preview_scenario_source_mismatch"
)
WARNING_ABYSS_SOURCE_IDENTITY_MISSING = "abyss_source_identity_missing_no_default_used"
EXPECTED_DEV_WARNING_IDS = frozenset(
    {
        "dev_talent_order_skill_id_assumed",
        "artifact_set_auto_registry_mapping_not_curated",
        "selected_runtime_team_adapter_boundary",
        "slot_details_snapshot_used",
        "slot_db_current_equipment_used",
        "artifact_set_count_below_two_ignored",
        "shell_target_placeholder_not_enemy_truth",
        "gcsim_boosted_energy_line_appended_no_existing_energy_line",
        "gcsim_dummy_target_from_rotation_shell",
    }
)


@dataclass(frozen=True, slots=True)
class GcsimBrowserRunRequest:
    db_path: str
    selected_team: dict[str, Any]
    team_index: int
    chamber: int
    side: int
    rotation_shell_text: str
    abyss_period_start: str = ""
    abyss_floor: int = 0
    abyss_cache_dir: str = ""
    target_mode: str = FACT_DPS_HP_MODE_MULTI_TARGET
    boosted_energy_enabled: bool = False
    run_root: str = ""


@dataclass(frozen=True, slots=True)
class GcsimBrowserBatchRunRequest:
    db_path: str
    selected_team: dict[str, Any]
    team_index: int
    side: int
    rotation_shell_text: str
    abyss_period_start: str = ""
    abyss_floor: int = 0
    abyss_cache_dir: str = ""
    target_mode: str = FACT_DPS_HP_MODE_MULTI_TARGET
    chambers: tuple[int, ...] = (1, 2, 3)
    boosted_energy_enabled: bool = False
    run_root: str = ""


@dataclass(frozen=True, slots=True)
class GcsimBrowserDpsDummyRunRequest:
    db_path: str
    selected_team: dict[str, Any]
    team_index: int
    rotation_shell_text: str
    boosted_energy_enabled: bool = False
    run_root: str = ""


class GcsimBrowserRunWorker(QObject):
    finished = Signal(dict)

    def __init__(self, request: GcsimBrowserRunRequest) -> None:
        super().__init__()
        self._request = request

    @Slot()
    def run(self) -> None:
        self.finished.emit(run_gcsim_browser_selected_chamber(self._request))


class GcsimBrowserBatchRunWorker(QObject):
    finished = Signal(dict)

    def __init__(self, request: GcsimBrowserBatchRunRequest) -> None:
        super().__init__()
        self._request = request

    @Slot()
    def run(self) -> None:
        self.finished.emit(run_gcsim_browser_three_chambers(self._request))


class GcsimBrowserDpsDummyRunWorker(QObject):
    finished = Signal(dict)

    def __init__(self, request: GcsimBrowserDpsDummyRunRequest) -> None:
        super().__init__()
        self._request = request

    @Slot()
    def run(self) -> None:
        self.finished.emit(run_gcsim_browser_dps_dummy(self._request))


def run_gcsim_browser_selected_chamber(
    request: GcsimBrowserRunRequest,
) -> dict[str, Any]:
    if _selected_slot_count(request.selected_team) <= 0:
        return _with_readiness_summary(
            _selected_team_empty_error_payload(
                selection=_selection_report(request),
            )
        )
    if not request.abyss_period_start or not request.abyss_floor:
        return {
            "success": False,
            "error_category": ERROR_PREPARE_NOT_READY,
            "error": "Current Abyss source-data identity is missing; not using backend defaults.",
            "selection": _selection_report(request),
            "warnings": [WARNING_ABYSS_SOURCE_IDENTITY_MISSING],
        }

    run_dir = _new_run_dir(request.run_root)
    rotation_shell_path = run_dir / "rotation_shell.from_editor.txt"
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        rotation_shell_path.write_text(request.rotation_shell_text, encoding="utf-8")
        report = build_selected_team_full_config_report(
            db_path=request.db_path,
            selected_team=request.selected_team,
            team_index=request.team_index,
            rotation_shell_path=rotation_shell_path,
            run_dir=run_dir,
            write_config=True,
            run_settings=GcsimRunSettings(
                boosted_energy_enabled=request.boosted_energy_enabled,
            ),
        )
        if report.ready:
            smoke = run_selected_team_abyss_smoke(
                report,
                abyss_period_start=request.abyss_period_start,
                abyss_floor=request.abyss_floor,
                abyss_chamber=request.chamber,
                abyss_side=request.side,
                abyss_fact_dps_multi_target_enabled=(
                    request.target_mode != FACT_DPS_HP_MODE_SOLO
                ),
                abyss_cache_dir=request.abyss_cache_dir or None,
            )
            report = report_with_smoke(report, smoke)
        payload = report.to_dict()
    except Exception as exc:
        return _with_readiness_summary(
            {
                "success": False,
                "error_category": ERROR_CONFIG_PREPARE_ERROR,
                "error": str(exc),
                "selection": _selection_report(request),
                "run_dir": str(run_dir),
                "rotation_shell_path": str(rotation_shell_path),
            }
        )

    payload["selection"] = _selection_report(request)
    payload["run_dir"] = str(run_dir)
    payload["rotation_shell_path"] = str(rotation_shell_path)
    mismatch_warning = _source_mismatch_warning(payload, request)
    if mismatch_warning:
        payload["warnings"] = [
            *(payload.get("warnings") or []),
            mismatch_warning,
        ]
    payload["error_category"] = classify_gcsim_browser_run_payload(payload)
    payload["success"] = bool(
        payload.get("ready")
        and isinstance(payload.get("smoke"), dict)
        and payload["smoke"].get("success")
    )
    return _with_readiness_summary(payload)


def run_gcsim_browser_dps_dummy(
    request: GcsimBrowserDpsDummyRunRequest,
) -> dict[str, Any]:
    if _selected_slot_count(request.selected_team) <= 0:
        return _with_readiness_summary(
            _selected_team_empty_error_payload(
                selection=_dps_dummy_selection_report(request),
            )
        )

    run_dir = _new_run_dir(request.run_root)
    rotation_shell_path = run_dir / "rotation_shell.from_editor.txt"
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        rotation_shell_path.write_text(request.rotation_shell_text, encoding="utf-8")
        report = build_selected_team_full_config_report(
            db_path=request.db_path,
            selected_team=request.selected_team,
            team_index=request.team_index,
            rotation_shell_path=rotation_shell_path,
            run_dir=run_dir,
            write_config=True,
            run_settings=GcsimRunSettings(
                boosted_energy_enabled=request.boosted_energy_enabled,
            ),
        )
        if report.ready:
            dps_dummy_run = run_selected_team_dps_dummy_artifact(
                report,
                run_dir=run_dir,
            )
            report = report_with_dps_dummy_run(report, dps_dummy_run)
        payload = report.to_dict()
    except Exception as exc:
        return _with_readiness_summary(
            {
                "success": False,
                "error_category": ERROR_CONFIG_PREPARE_ERROR,
                "error": str(exc),
                "selection": _dps_dummy_selection_report(request),
                "run_dir": str(run_dir),
                "rotation_shell_path": str(rotation_shell_path),
            }
        )

    payload["selection"] = _dps_dummy_selection_report(request)
    payload["run_dir"] = str(run_dir)
    payload["rotation_shell_path"] = str(rotation_shell_path)
    payload["error_category"] = classify_gcsim_browser_run_payload(payload)
    payload["success"] = bool(
        payload.get("ready")
        and isinstance(payload.get("dps_dummy_run"), dict)
        and payload["dps_dummy_run"].get("success")
    )
    return _with_readiness_summary(payload)


def run_gcsim_browser_three_chambers(
    request: GcsimBrowserBatchRunRequest,
) -> dict[str, Any]:
    if _selected_slot_count(request.selected_team) <= 0:
        return _with_readiness_summary(
            {
                **_selected_team_empty_error_payload(
                    selection=_batch_selection_report(request),
                ),
                "batch_status": "failed",
                "chambers": [],
            }
        )
    if not request.abyss_period_start or not request.abyss_floor:
        return {
            "success": False,
            "batch_status": "failed",
            "error_category": ERROR_PREPARE_NOT_READY,
            "error": "Current Abyss source-data identity is missing; not using backend defaults.",
            "selection": _batch_selection_report(request),
            "warnings": [WARNING_ABYSS_SOURCE_IDENTITY_MISSING],
            "chambers": [],
        }

    chambers: list[dict[str, Any]] = []
    for chamber in request.chambers:
        chamber_request = GcsimBrowserRunRequest(
            db_path=request.db_path,
            selected_team=request.selected_team,
            team_index=request.team_index,
            chamber=int(chamber),
            side=request.side,
            rotation_shell_text=request.rotation_shell_text,
            abyss_period_start=request.abyss_period_start,
            abyss_floor=request.abyss_floor,
            abyss_cache_dir=request.abyss_cache_dir,
            target_mode=request.target_mode,
            boosted_energy_enabled=request.boosted_energy_enabled,
            run_root=request.run_root,
        )
        chambers.append(run_gcsim_browser_selected_chamber(chamber_request))

    status = _batch_status(chambers)
    return {
        "success": status == "passed",
        "batch_status": status,
        "selection": _batch_selection_report(request),
        "chambers": chambers,
        "warnings": _dedupe(
            warning
            for chamber in chambers
            for warning in (chamber.get("warnings") or [])
        ),
    }


def classify_gcsim_browser_run_payload(payload: dict[str, Any]) -> str:
    issues = _issue_statuses(payload)
    if any("shell" in status or "rotation" in status for status in issues):
        return ERROR_CONFIG_PARSE_OR_ROTATION_ERROR

    smoke = payload.get("smoke") if isinstance(payload.get("smoke"), dict) else {}
    dps_dummy = (
        payload.get("dps_dummy_run")
        if isinstance(payload.get("dps_dummy_run"), dict)
        else {}
    )
    run_payload = smoke or dps_dummy
    run_result = (
        run_payload.get("run_result")
        if isinstance(run_payload.get("run_result"), dict)
        else {}
    )
    preflight_status = str(run_result.get("artifact_preflight_status") or "")
    run_status = str(run_result.get("status") or run_payload.get("status") or "")
    if preflight_status and preflight_status != "gtt_wave_scenario_contract_ready":
        return ERROR_ARTIFACT_PREFLIGHT_FAILED
    if "preflight" in run_status or "contract" in run_status:
        return ERROR_ARTIFACT_PREFLIGHT_FAILED

    if payload.get("ready") is False:
        return ERROR_PREPARE_NOT_READY

    if run_result and run_result.get("success") is False:
        return ERROR_GCSIM_RUNTIME_ERROR
    if run_payload and not run_payload.get("success", False):
        status = str(run_payload.get("status") or "")
        if status == "run_failed":
            return ERROR_GCSIM_RUNTIME_ERROR
        return ERROR_UNKNOWN

    if payload.get("ready") and run_payload.get("success"):
        return ""
    return ERROR_UNKNOWN


def _batch_status(chambers: list[dict[str, Any]]) -> str:
    if chambers and all(bool(chamber.get("success")) for chamber in chambers):
        return "passed"
    if any(bool(chamber.get("success")) for chamber in chambers):
        return "partial_failed"
    return "failed"


def split_gcsim_browser_warnings(warnings: Any) -> tuple[list[str], list[str]]:
    expected_notes: list[str] = []
    real_warnings: list[str] = []
    for warning in warnings or []:
        text = str(warning)
        if not text:
            continue
        if text in EXPECTED_DEV_WARNING_IDS:
            expected_notes.append(text)
        else:
            real_warnings.append(text)
    return _dedupe(expected_notes), _dedupe(real_warnings)


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
        (
            "Abyss source: "
            f"period_start={selection.get('period_start') or '-'} "
            f"floor={selection.get('floor') or '-'}"
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
            "Avg total damage/run: "
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
            f"total_hp={_format_number(scenario_summary.get('total_hp')) or '-'} "
            f"spawn_policy={scenario_summary.get('spawn_policy', '-')}"
        )

    _extend_readiness_summary(lines, payload)

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

    _extend_warning_sections(lines, payload.get("warnings") or [])
    _extend_debug_issue_summary(lines, payload)
    error = str(payload.get("error") or "")
    if error:
        lines.extend(["", f"Error: {error}"])
    return "\n".join(lines)


def format_gcsim_browser_dps_dummy_report(payload: dict[str, Any]) -> str:
    selection = payload.get("selection") if isinstance(payload.get("selection"), dict) else {}
    dps_dummy = (
        payload.get("dps_dummy_run")
        if isinstance(payload.get("dps_dummy_run"), dict)
        else {}
    )
    run_result = (
        dps_dummy.get("run_result")
        if isinstance(dps_dummy.get("run_result"), dict)
        else {}
    )
    summary = (
        run_result.get("summary")
        if isinstance(run_result.get("summary"), dict)
        else {}
    )
    energy = dps_dummy.get("energy") if isinstance(dps_dummy.get("energy"), dict) else {}
    dummy_target = (
        dps_dummy.get("dummy_target")
        if isinstance(dps_dummy.get("dummy_target"), dict)
        else {}
    )
    lines = [
        "Run DPS Dummy",
        f"Team: {selection.get('team_label', '-')}",
        f"Status: {dps_dummy.get('status') or payload.get('status') or '-'}",
        f"Error category: {payload.get('error_category') or '-'}",
        f"Config path: {payload.get('config_path') or '-'}",
        f"Energy mode: {energy.get('mode') or '-'}",
        f"Dummy target HP: {dummy_target.get('hp') or '-'}",
        f"Dummy target resist: {dummy_target.get('resist') or dummy_target.get('source') or '-'}",
        f"DPS mean: {_format_number(summary.get('dps_mean')) or '-'}",
        (
            "Avg total damage/run: "
            f"{_format_number(summary.get('total_damage_mean')) or '-'}"
        ),
        (
            "Artifact preflight: "
            f"{run_result.get('artifact_preflight_status') or '-'}"
        ),
        "Abyss source: not used",
        "History persistence: disabled",
        "DPS correctness claim: false",
    ]

    _extend_readiness_summary(lines, payload)

    team = payload.get("team") if isinstance(payload.get("team"), dict) else {}
    characters = team.get("characters") if isinstance(team.get("characters"), list) else []
    if characters:
        lines.extend(["", "Characters:"])
        for character in characters:
            if isinstance(character, dict):
                lines.append("  - " + _character_line(character))

    _extend_warning_sections(lines, payload.get("warnings") or [])
    _extend_debug_issue_summary(lines, payload)
    error = str(payload.get("error") or "")
    if error:
        lines.extend(["", f"Error: {error}"])
    return "\n".join(lines)


def format_gcsim_browser_batch_report(payload: dict[str, Any]) -> str:
    selection = payload.get("selection") if isinstance(payload.get("selection"), dict) else {}
    lines = [
        "Run 3 chambers",
        (
            f"Team: {selection.get('team_label', '-')} "
            f"/ Side {selection.get('side', '-')}"
        ),
        (
            "Abyss source: "
            f"period_start={selection.get('period_start') or '-'} "
            f"floor={selection.get('floor') or '-'}"
        ),
        f"Batch status: {payload.get('batch_status') or '-'}",
        "DPS correctness claim: false",
        "",
        "Chambers:",
    ]
    chambers = payload.get("chambers") if isinstance(payload.get("chambers"), list) else []
    for chamber_payload in chambers:
        if not isinstance(chamber_payload, dict):
            continue
        lines.extend(_batch_chamber_lines(chamber_payload))
    _extend_readiness_summary(lines, payload)
    _extend_warning_sections(lines, payload.get("warnings") or [])
    _extend_debug_issue_summary(lines, payload)
    error = str(payload.get("error") or "")
    if error:
        lines.extend(["", f"Error: {error}"])
    return "\n".join(lines)


def right_panel_gcsim_results_from_browser_batch_payload(
    payload: dict[str, Any],
    *,
    rotation_hash: str = "",
    target_mode: str = FACT_DPS_HP_MODE_SOLO,
) -> tuple[RightPanelGcsimChamberResult, ...]:
    selection = payload.get("selection") if isinstance(payload.get("selection"), dict) else {}
    side = _optional_int(selection.get("side")) or 0
    team_index = _optional_int(selection.get("team_index"))
    if team_index is None:
        team_index = max(0, side - 1) if side else 0
    period_start = str(selection.get("period_start") or "")
    floor = _optional_int(selection.get("floor")) or 0
    results: list[RightPanelGcsimChamberResult] = []
    chambers = payload.get("chambers") if isinstance(payload.get("chambers"), list) else []
    for chamber_payload in chambers:
        if not isinstance(chamber_payload, dict):
            continue
        result = _right_panel_gcsim_result_from_browser_chamber_payload(
            chamber_payload,
            fallback_team_index=team_index,
            fallback_side=side,
            fallback_period_start=period_start,
            fallback_floor=floor,
            rotation_hash=rotation_hash,
            target_mode=target_mode,
        )
        if result is not None:
            results.append(result)
    return tuple(sorted(results, key=lambda result: (result.chamber, result.side)))


def right_panel_gcsim_result_from_browser_selected_payload(
    payload: dict[str, Any],
    *,
    rotation_hash: str = "",
    target_mode: str = FACT_DPS_HP_MODE_SOLO,
) -> RightPanelGcsimChamberResult | None:
    selection = payload.get("selection") if isinstance(payload.get("selection"), dict) else {}
    team_index = _optional_int(selection.get("team_index"))
    side = _optional_int(selection.get("side")) or 0
    if team_index is None:
        team_index = max(0, side - 1) if side else 0
    return _right_panel_gcsim_result_from_browser_chamber_payload(
        payload,
        fallback_team_index=team_index,
        fallback_side=side,
        fallback_period_start=str(selection.get("period_start") or ""),
        fallback_floor=_optional_int(selection.get("floor")) or 0,
        rotation_hash=rotation_hash,
        target_mode=str(selection.get("target_mode") or target_mode),
        require_smoke=True,
    )


def _right_panel_gcsim_result_from_browser_chamber_payload(
    payload: dict[str, Any],
    *,
    fallback_team_index: int,
    fallback_side: int,
    fallback_period_start: str,
    fallback_floor: int,
    rotation_hash: str,
    target_mode: str,
    require_smoke: bool = False,
) -> RightPanelGcsimChamberResult | None:
    chamber_selection = (
        payload.get("selection") if isinstance(payload.get("selection"), dict) else {}
    )
    chamber = _optional_int(chamber_selection.get("chamber"))
    side = _optional_int(chamber_selection.get("side")) or int(fallback_side)
    if chamber is None or side not in (1, 2):
        return None
    smoke = payload.get("smoke") if isinstance(payload.get("smoke"), dict) else {}
    if require_smoke and not smoke:
        return None
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
    scenario = (
        smoke.get("scenario_summary")
        if isinstance(smoke.get("scenario_summary"), dict)
        else {}
    )
    return RightPanelGcsimChamberResult(
        chamber=chamber,
        team_index=int(fallback_team_index),
        side=side,
        status=str(smoke.get("status") or payload.get("status") or ""),
        error_category=str(payload.get("error_category") or ""),
        clear_time_seconds=_optional_float(summary.get("duration_mean")),
        dps_mean=_optional_float(summary.get("dps_mean")),
        total_damage_mean=_optional_float(summary.get("total_damage_mean")),
        scenario_total_hp=_optional_float(scenario.get("total_hp")),
        warnings=tuple(str(warning) for warning in payload.get("warnings") or []),
        issues=_issue_strings(payload.get("issues") or []),
        config_path=str(payload.get("config_path") or ""),
        scenario_path=str(smoke.get("scenario_path") or ""),
        mode=MODE_ABYSS,
        period_start=str(chamber_selection.get("period_start") or fallback_period_start),
        floor=_optional_int(chamber_selection.get("floor")) or int(fallback_floor),
        target_mode=target_mode,
        rotation_hash=rotation_hash,
    )


def _batch_chamber_lines(payload: dict[str, Any]) -> list[str]:
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
    scenario = smoke.get("scenario_summary") if isinstance(smoke.get("scenario_summary"), dict) else {}
    lines = [
        (
            f"  C{selection.get('chamber', '-')}: "
            f"status={smoke.get('status') or payload.get('status') or '-'} "
            f"error_category={payload.get('error_category') or '-'} "
            f"clear_time={_format_number(summary.get('duration_mean')) or '-'} "
            f"dps={_format_number(summary.get('dps_mean')) or '-'} "
            f"avg_total_damage_per_run={_format_number(summary.get('total_damage_mean')) or '-'} "
            f"scenario_hp={_format_number(scenario.get('total_hp')) or '-'} "
            f"waves={scenario.get('wave_count', '-')} "
            f"targets={scenario.get('target_count', '-')}"
        )
    ]
    expected_notes, real_warnings = split_gcsim_browser_warnings(
        payload.get("warnings") or []
    )
    if expected_notes:
        lines.append("    notes=" + ", ".join(expected_notes))
    if real_warnings:
        lines.append("    warnings=" + ", ".join(real_warnings))
    error = str(payload.get("error") or "")
    if error:
        lines.append(f"    error={error}")
    return lines


def _extend_warning_sections(lines: list[str], warnings: Any) -> None:
    expected_notes, real_warnings = split_gcsim_browser_warnings(warnings)
    if expected_notes:
        expected_notes = _cap_text_list(expected_notes)
        lines.extend(
            [
                "",
                "Expected/dev notes:",
                *[f"  - {warning}" for warning in expected_notes],
            ]
        )
    if real_warnings:
        real_warnings = _cap_text_list(real_warnings)
        lines.extend(
            [
                "",
                "Real warnings/issues:",
                *[f"  - {warning}" for warning in real_warnings],
            ]
        )


def _extend_debug_issue_summary(lines: list[str], payload: dict[str, Any]) -> None:
    statuses = _issue_statuses(payload)
    if not statuses:
        return
    first_codes = ", ".join(_cap_text_list(list(statuses), limit=8))
    lines.extend(
        [
            "",
            f"Debug issue count: {len(statuses)}",
            f"Debug first issue codes: {first_codes}",
        ]
    )


def _cap_text_list(values: list[str], *, limit: int = 8) -> list[str]:
    if len(values) <= limit:
        return values
    return [*values[:limit], f"... +{len(values) - limit} more"]


def _extend_readiness_summary(lines: list[str], payload: dict[str, Any]) -> None:
    summary = (
        payload.get("readiness_summary")
        if isinstance(payload.get("readiness_summary"), dict)
        else {}
    )
    text = format_gcsim_readiness_summary(summary)
    if text:
        lines.extend(["", text])


def _character_line(character: dict[str, Any]) -> str:
    account = character.get("account_character") if isinstance(character.get("account_character"), dict) else {}
    payload = character.get("payload_character") if isinstance(character.get("payload_character"), dict) else {}
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
        f"{account.get('catalog_english_name') or account.get('localized_name') or payload.get('display_name') or 'slot'}: "
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
    assembly = payload.get("assembly") if isinstance(payload.get("assembly"), dict) else {}
    for issue in assembly.get("issues") or []:
        if isinstance(issue, dict) and issue.get("status"):
            statuses.append(str(issue["status"]))
    return tuple(statuses)


def _selection_report(request: GcsimBrowserRunRequest) -> dict[str, Any]:
    return {
        "team_index": int(request.team_index),
        "team_label": f"Team {int(request.team_index) + 1}",
        "chamber": int(request.chamber),
        "side": int(request.side),
        "selected_slot_count": _selected_slot_count(request.selected_team),
        "period_start": request.abyss_period_start,
        "floor": int(request.abyss_floor or 0),
        "cache_dir": request.abyss_cache_dir,
        "target_mode": request.target_mode,
        "boosted_energy_enabled": bool(request.boosted_energy_enabled),
    }


def _batch_selection_report(request: GcsimBrowserBatchRunRequest) -> dict[str, Any]:
    return {
        "team_index": int(request.team_index),
        "team_label": f"Team {int(request.team_index) + 1}",
        "side": int(request.side),
        "selected_slot_count": _selected_slot_count(request.selected_team),
        "period_start": request.abyss_period_start,
        "floor": int(request.abyss_floor or 0),
        "cache_dir": request.abyss_cache_dir,
        "target_mode": request.target_mode,
        "boosted_energy_enabled": bool(request.boosted_energy_enabled),
        "chambers": [int(chamber) for chamber in request.chambers],
    }


def _dps_dummy_selection_report(
    request: GcsimBrowserDpsDummyRunRequest,
) -> dict[str, Any]:
    return {
        "team_index": int(request.team_index),
        "team_label": f"Team {int(request.team_index) + 1}",
        "mode": MODE_DPS_DUMMY,
        "selected_slot_count": _selected_slot_count(request.selected_team),
        "target_mode": MODE_DPS_DUMMY,
        "boosted_energy_enabled": bool(request.boosted_energy_enabled),
    }


def _source_mismatch_warning(
    payload: dict[str, Any],
    request: GcsimBrowserRunRequest,
) -> str:
    smoke = payload.get("smoke") if isinstance(payload.get("smoke"), dict) else {}
    source = smoke.get("source") if isinstance(smoke.get("source"), dict) else {}
    actual_period = str(source.get("period_start") or "")
    actual_floor = int(source.get("floor") or 0)
    if (
        request.abyss_period_start
        and actual_period
        and actual_period != request.abyss_period_start
    ):
        return WARNING_ABYSS_PREVIEW_SCENARIO_SOURCE_MISMATCH
    if request.abyss_floor and actual_floor and actual_floor != request.abyss_floor:
        return WARNING_ABYSS_PREVIEW_SCENARIO_SOURCE_MISMATCH
    return ""


def _with_readiness_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = build_gcsim_readiness_summary(payload)
    if summary.blocked:
        payload = dict(payload)
        payload["readiness_summary"] = summary.to_dict()
    return payload


def _selected_team_empty_error_payload(
    *,
    selection: dict[str, Any],
) -> dict[str, Any]:
    return {
        "success": False,
        "error_category": ERROR_PREPARE_NOT_READY,
        "error": "Selected team has no characters.",
        "selection": selection,
        "issues": [
            {
                "status": "selected_team_empty",
                "field": "selected_team.slots",
                "message": "Selected team has no character slots.",
            }
        ],
    }


def _selected_slot_count(selected_team: Any) -> int:
    if not isinstance(selected_team, dict):
        return 0
    slots = selected_team.get("slots")
    if not isinstance(slots, list):
        return 0
    count = 0
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        if slot.get("character") or _nested_character(slot):
            count += 1
    return count


def _nested_character(slot: dict[str, Any]) -> dict[str, Any]:
    details = slot.get("character_details_data")
    if isinstance(details, dict) and isinstance(details.get("account_character"), dict):
        return details["account_character"]
    return {}


def _dedupe(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


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


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _issue_strings(issues: Any) -> tuple[str, ...]:
    result: list[str] = []
    for issue in issues or []:
        if isinstance(issue, dict):
            status = issue.get("status")
            field = issue.get("field")
            text = ":".join(str(part) for part in (status, field) if part)
            if text:
                result.append(text)
            continue
        text = str(issue)
        if text:
            result.append(text)
    return tuple(_dedupe(result))
