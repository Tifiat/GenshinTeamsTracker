"""Selected TeamBuilder state -> production GCSIM config boundary.

This adapter consumes explicit runtime selected team/slot state. It may use
SQLite only to fill account-owned fields by stable ids such as character id or
weapon fingerprint. It must not search characters by localized display name or
choose deterministic dev weapon candidates.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from typing import Any

from hoyolab_export.account_storage import DEFAULT_ACCOUNT_DB_PATH
from hoyolab_export.artifact_build_snapshot import ARTIFACT_POSITIONS
from run_workspace.gcsim.account_prepared_config import (
    ACCOUNT_PREPARED_CONFIG_SMOKE_SKIPPED,
    ARTIFACT_SOURCE_CURRENT_EQUIPPED,
    ARTIFACT_SOURCE_MISSING,
    ARTIFACT_STATS_SOURCE_CURRENT_EQUIPPED_MAIN_SUB,
    AccountPreparedConfigIssue,
    _account_character_report,
    _artifact_set_key_resolver,
    _connect_readonly_db,
    _current_artifact_payload_from_account_rows,
    _current_equipped_weapon_stack,
    _run_optional_abyss_smoke,
    _row_dict,
    _talent_input_from_account_rows,
    _weapon_payload,
    _weapon_report,
)
from run_workspace.gcsim.artifact_runner import (
    DEFAULT_GCSIM_RUNS_DIR,
    run_active_gcsim_artifact,
)
from run_workspace.gcsim.config_assembly import (
    GcsimFullConfigAssembly,
    assemble_gcsim_full_config,
)
from run_workspace.gcsim.config_blocks import (
    GcsimArtifactConfigInput,
    GcsimArtifactSetConfigInput,
    GcsimCharacterConfigBlock,
    GcsimCharacterConfigInput,
    GcsimWeaponConfigInput,
    build_gcsim_character_config_block,
)
from run_workspace.gcsim.config_readiness import (
    GcsimMappingRef,
    GcsimTalentInput,
)
from run_workspace.gcsim.prepared_config_adapter import (
    PreparedGcsimCharacterConfigResult,
    PreparedGcsimFullConfigResult,
    PreparedGcsimTeamConfigResult,
)
from run_workspace.gcsim.runtime_probe import DEFAULT_GO_PROBE_TIMEOUT_SECONDS
from run_workspace.gcsim.settings import (
    GcsimRunSettings,
    write_shell_with_gcsim_energy_settings,
)
from run_workspace.gcsim.snap_monster_titles import SnapJsonFetcher
from run_workspace.team_builder import TeamBuilderTeamState


SELECTED_TEAM_CONFIG_READY = "ready"
SELECTED_TEAM_CONFIG_NOT_READY = "not_ready"
SELECTED_TEAM_CONFIG_INPUT_ERROR = "input_error"
SELECTED_TEAM_CONFIG_CONFIG_WRITTEN = "config_written"
SELECTED_TEAM_CONFIG_WRITE_SKIPPED_NOT_READY = "write_skipped_not_ready"
SELECTED_TEAM_CONFIG_RUN_SKIPPED = "run_skipped"

WARNING_SELECTED_TEAM_ADAPTER_BOUNDARY = "selected_runtime_team_adapter_boundary"
WARNING_SLOT_DETAILS_SNAPSHOT_USED = "slot_details_snapshot_used"
WARNING_SLOT_DB_CURRENT_EQUIPMENT_USED = "slot_db_current_equipment_used"
WARNING_GCSIM_DUMMY_TARGET_FROM_ROTATION_SHELL = (
    "gcsim_dummy_target_from_rotation_shell"
)

_TARGET_HP_RE = re.compile(r"\bhp\s*=\s*([0-9.]+)", re.IGNORECASE)
_TARGET_RESIST_RE = re.compile(r"\bresist\s*=\s*([0-9.+-]+)", re.IGNORECASE)


ArtifactRunFunc = Any


@dataclass(frozen=True, slots=True)
class SelectedTeamConfigIssue:
    status: str
    field: str
    message: str = ""
    entity_type: str = ""
    project_id: str = ""
    display_name: str = ""
    slot_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "field": self.field,
            "message": self.message,
            "entity_type": self.entity_type,
            "project_id": self.project_id,
            "display_name": self.display_name,
            "slot_index": self.slot_index,
        }


@dataclass(frozen=True, slots=True)
class SelectedTeamCharacterDetail:
    slot_index: int
    status: str
    ready: bool
    account_character: dict[str, Any] = field(default_factory=dict)
    character_found: bool = False
    character_key_ready: bool = False
    weapon: dict[str, Any] = field(default_factory=dict)
    weapon_found: bool = False
    weapon_key_ready: bool = False
    weapon_selection_method: str = ""
    artifact_source: str = ""
    artifact_account_truth: bool = False
    artifact_stats_source: str = ""
    artifact_set_counts: tuple[dict[str, Any], ...] = ()
    current_equipped_artifact_count: int = 0
    talents: dict[str, Any] = field(default_factory=dict)
    payload_character: dict[str, Any] = field(default_factory=dict)
    block_ready: bool = False
    block_status: str = ""
    warnings: tuple[str, ...] = ()
    issues: tuple[SelectedTeamConfigIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_index": self.slot_index,
            "status": self.status,
            "ready": self.ready,
            "account_character": dict(self.account_character),
            "character_found": self.character_found,
            "character_key_ready": self.character_key_ready,
            "weapon": dict(self.weapon),
            "weapon_found": self.weapon_found,
            "weapon_key_ready": self.weapon_key_ready,
            "weapon_selection_method": self.weapon_selection_method,
            "artifact_source": self.artifact_source,
            "artifact_account_truth": self.artifact_account_truth,
            "artifact_stats_source": self.artifact_stats_source,
            "artifact_set_counts": [dict(item) for item in self.artifact_set_counts],
            "current_equipped_artifact_count": self.current_equipped_artifact_count,
            "talents": dict(self.talents),
            "payload_character": dict(self.payload_character),
            "block_ready": self.block_ready,
            "block_status": self.block_status,
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class SelectedTeamBuild:
    status: str
    ready: bool
    payload: dict[str, Any] = field(default_factory=dict)
    characters: tuple[SelectedTeamCharacterDetail, ...] = ()
    warnings: tuple[str, ...] = ()
    issues: tuple[SelectedTeamConfigIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "payload": dict(self.payload),
            "characters": [character.to_dict() for character in self.characters],
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class SelectedTeamFullConfigReport:
    status: str
    ready: bool
    db_path: str
    team_index: int
    team: SelectedTeamBuild
    prepared_team: PreparedGcsimTeamConfigResult
    assembly: GcsimFullConfigAssembly
    full_config: PreparedGcsimFullConfigResult
    config_path: str = ""
    wrote_config: bool = False
    smoke: dict[str, Any] | None = None
    dps_dummy_run: dict[str, Any] | None = None
    warnings: tuple[str, ...] = ()
    issues: tuple[dict[str, Any], ...] = ()
    source_notes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "db_path": self.db_path,
            "team_index": self.team_index,
            "team": self.team.to_dict(),
            "prepared_team": self.prepared_team.to_dict(),
            "assembly": self.assembly.to_dict(),
            "full_config": self.full_config.to_dict(),
            "config_path": self.config_path,
            "wrote_config": self.wrote_config,
            "smoke": dict(self.smoke) if self.smoke is not None else None,
            "dps_dummy_run": (
                dict(self.dps_dummy_run)
                if self.dps_dummy_run is not None
                else None
            ),
            "warnings": list(self.warnings),
            "issues": [dict(issue) for issue in self.issues],
            "source_notes": dict(self.source_notes),
        }


def build_selected_team_payload(
    *,
    db_path: str | Path = DEFAULT_ACCOUNT_DB_PATH,
    selected_team: TeamBuilderTeamState | Mapping[str, Any] | Iterable[Any],
    team_index: int = 0,
    artifact_set_registry_source: str | Path | None = None,
) -> SelectedTeamBuild:
    slots = _selected_slots(selected_team)
    if not slots:
        issue = SelectedTeamConfigIssue(
            "selected_team_empty",
            "selected_team.slots",
            "Selected team has no character slots.",
        )
        return SelectedTeamBuild(
            status=SELECTED_TEAM_CONFIG_NOT_READY,
            ready=False,
            issues=(issue,),
            payload=_payload(
                team_index=team_index,
                required_slots=(),
                characters=(),
            ),
        )

    details: list[SelectedTeamCharacterDetail] = []
    payload_characters: list[dict[str, Any]] = []
    artifact_set_resolver = _artifact_set_key_resolver(artifact_set_registry_source)

    with closing(_connect_readonly_db(db_path)) as conn:
        for slot in slots:
            built = _build_slot_payload(
                conn,
                slot,
                artifact_set_resolver=artifact_set_resolver,
            )
            details.append(built)
            if built.account_character:
                payload_character = _payload_character_from_detail(built)
                if payload_character:
                    payload_characters.append(payload_character)

    warnings = _dedupe_tuple(
        warning
        for detail in details
        for warning in detail.warnings
    )
    issues = tuple(issue for detail in details for issue in detail.issues)
    ready = bool(details) and all(detail.ready for detail in details)
    payload = _payload(
        team_index=team_index,
        required_slots=tuple(detail.slot_index for detail in details),
        characters=tuple(payload_characters),
    )
    return SelectedTeamBuild(
        status=SELECTED_TEAM_CONFIG_READY if ready else SELECTED_TEAM_CONFIG_NOT_READY,
        ready=ready,
        payload=payload,
        characters=tuple(details),
        warnings=warnings,
        issues=issues,
    )


def build_selected_team_full_config_report(
    *,
    db_path: str | Path = DEFAULT_ACCOUNT_DB_PATH,
    selected_team: TeamBuilderTeamState | Mapping[str, Any] | Iterable[Any],
    team_index: int = 0,
    rotation_shell_path: str | Path,
    config_out: str | Path | None = None,
    run_dir: str | Path | None = None,
    write_config: bool = True,
    artifact_set_registry_source: str | Path | None = None,
    run_settings: GcsimRunSettings | None = None,
) -> SelectedTeamFullConfigReport:
    effective_run_dir = (
        Path(run_dir)
        if run_dir is not None or config_out is not None
        else _new_selected_config_run_dir()
    )
    settings = run_settings or GcsimRunSettings()
    effective_shell_path, energy_report = write_shell_with_gcsim_energy_settings(
        rotation_shell_path,
        run_dir=effective_run_dir,
        settings=settings,
    )
    team = build_selected_team_payload(
        db_path=db_path,
        selected_team=selected_team,
        team_index=team_index,
        artifact_set_registry_source=artifact_set_registry_source,
    )
    prepared_team = _build_selected_team_config_result(team.payload)
    blocks = tuple(
        result.block for result in prepared_team.characters if result.block is not None
    )
    try:
        shell_text = Path(effective_shell_path).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        shell_text = ""
    assembly = assemble_gcsim_full_config(
        blocks,
        shell_text,
        shell_source=str(effective_shell_path),
    )
    warnings = _dedupe_tuple(
        [
            *team.warnings,
            *prepared_team.warnings,
            *assembly.warnings,
            *energy_report.warnings,
        ]
    )
    issues = [
        *(issue.to_dict() for issue in team.issues),
        *(issue.to_dict() for issue in prepared_team.issues),
        *(issue.to_dict() for issue in assembly.issues),
    ]
    source_notes = {
        **prepared_team.source_notes,
        "adapter": "selected_runtime_team_adapter",
        "ui_state": True,
        "storage_query": True,
        "network_fetch": False,
        "right_panel_persistence": False,
        "localized_names_used_as_gcsim_identity": False,
        "dev_weapon_candidate_not_account_truth": False,
        "final_or_right_panel_stats_as_add_stats": False,
        "artifact_source": "slot_snapshot_or_current_equipped_artifacts",
        "artifact_stats_source": ARTIFACT_STATS_SOURCE_CURRENT_EQUIPPED_MAIN_SUB,
        "energy": energy_report.to_dict(),
    }

    ready = bool(team.ready and prepared_team.ready and assembly.ready)
    config_path = ""
    wrote_config = False
    if ready and write_config:
        output_path = _config_output_path(config_out=config_out, run_dir=effective_run_dir)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(assembly.config_text, encoding="utf-8")
        config_path = str(output_path)
        wrote_config = True
        source_notes["config_output_generated"] = True
        source_notes["config_output_path"] = config_path

    full_config = PreparedGcsimFullConfigResult(
        status=(
            SELECTED_TEAM_CONFIG_CONFIG_WRITTEN
            if wrote_config
            else (
                SELECTED_TEAM_CONFIG_READY
                if ready
                else SELECTED_TEAM_CONFIG_WRITE_SKIPPED_NOT_READY
            )
        ),
        ready=ready,
        team=prepared_team,
        assembly=assembly,
        config_path=config_path,
        wrote_config=wrote_config,
        warnings=warnings,
        issues=tuple(issues),
        source_notes=source_notes,
    )
    attached_team = _attach_block_statuses(team, prepared_team)
    return SelectedTeamFullConfigReport(
        status=(
            SELECTED_TEAM_CONFIG_READY
            if ready
            else SELECTED_TEAM_CONFIG_NOT_READY
        ),
        ready=ready,
        db_path=str(db_path),
        team_index=int(team_index),
        team=attached_team,
        prepared_team=prepared_team,
        assembly=assembly,
        full_config=full_config,
        config_path=config_path,
        wrote_config=wrote_config,
        warnings=warnings,
        issues=tuple(issues),
        source_notes=source_notes,
    )


def run_selected_team_abyss_smoke(
    report: SelectedTeamFullConfigReport,
    *,
    abyss_period_start: str,
    abyss_floor: int,
    abyss_chamber: int,
    abyss_side: int,
    abyss_fact_dps_multi_target_enabled: bool,
    abyss_cache_dir: str | Path | None = None,
    gcsim_enemy_registry_source: str | Path | None = None,
    snap_monster_cache_path: str | Path | None = None,
    store_dir: str | Path | None = None,
    timeout_seconds: int = DEFAULT_GO_PROBE_TIMEOUT_SECONDS,
    artifact_run_func: ArtifactRunFunc = run_active_gcsim_artifact,
    snap_fetcher: SnapJsonFetcher | None = None,
) -> dict[str, Any]:
    smoke = _run_optional_abyss_smoke(
        report.full_config,
        abyss_period_start=abyss_period_start,
        abyss_floor=abyss_floor,
        abyss_chamber=abyss_chamber,
        abyss_side=abyss_side,
        abyss_fact_dps_multi_target_enabled=abyss_fact_dps_multi_target_enabled,
        abyss_cache_dir=abyss_cache_dir,
        gcsim_enemy_registry_source=gcsim_enemy_registry_source,
        snap_monster_cache_path=snap_monster_cache_path,
        store_dir=store_dir,
        timeout_seconds=timeout_seconds,
        artifact_run_func=artifact_run_func,
        snap_fetcher=snap_fetcher,
    )
    smoke.setdefault("source_notes", {})
    if isinstance(smoke["source_notes"], dict):
        smoke["source_notes"]["selected_runtime_team_adapter"] = True
    return smoke


def run_selected_team_dps_dummy_artifact(
    report: SelectedTeamFullConfigReport,
    *,
    run_dir: str | Path | None = None,
    store_dir: str | Path | None = None,
    timeout_seconds: int = DEFAULT_GO_PROBE_TIMEOUT_SECONDS,
    artifact_run_func: ArtifactRunFunc = run_active_gcsim_artifact,
) -> dict[str, Any]:
    if not report.full_config.ready or not report.assembly.config_text:
        return {
            "success": False,
            "status": SELECTED_TEAM_CONFIG_RUN_SKIPPED,
            "reason": "config_not_ready",
        }
    actual_run_dir = (
        Path(run_dir)
        if run_dir is not None
        else Path(report.config_path).parent
        if report.config_path
        else _new_selected_config_run_dir()
    )
    run_result = artifact_run_func(
        report.assembly.config_text,
        store_dir=store_dir,
        run_dir=actual_run_dir,
        timeout_seconds=timeout_seconds,
    )
    dummy_target = _dummy_target_metadata(report)
    payload = {
        "success": bool(run_result.success),
        "status": "run_passed" if run_result.success else run_result.status,
        "run_result": run_result.to_dict(),
        "target_mode": "dps_dummy",
        "energy": dict(report.source_notes.get("energy") or {}),
        "dummy_target": dummy_target,
        "scenario_summary": {
            "mode": "dps_dummy",
            "target_source": "rotation_shell",
            "dummy_target_hp": dummy_target.get("hp"),
            "dummy_target_resist": dummy_target.get("resist"),
            "dps_correctness_claim": False,
        },
        "warnings": [WARNING_GCSIM_DUMMY_TARGET_FROM_ROTATION_SHELL],
    }
    return payload


def _dummy_target_metadata(report: SelectedTeamFullConfigReport) -> dict[str, Any]:
    target_lines: tuple[str, ...] = ()
    shell_audit = report.assembly.shell_audit
    if shell_audit is not None:
        target_lines = shell_audit.target_placeholder_lines
    line = target_lines[0] if target_lines else ""
    return {
        "source": "rotation_shell/config" if line else "unknown",
        "line": line,
        "hp": _regex_group(_TARGET_HP_RE, line),
        "resist": _regex_group(_TARGET_RESIST_RE, line),
    }


def _regex_group(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    return match.group(1) if match else ""


def report_with_smoke(
    report: SelectedTeamFullConfigReport,
    smoke: dict[str, Any],
) -> SelectedTeamFullConfigReport:
    return _replace_report(report, smoke=smoke)


def report_with_dps_dummy_run(
    report: SelectedTeamFullConfigReport,
    dps_dummy_run: dict[str, Any],
) -> SelectedTeamFullConfigReport:
    return _replace_report(report, dps_dummy_run=dps_dummy_run)


def _build_selected_team_config_result(
    payload: Mapping[str, Any] | Iterable[Mapping[str, Any]],
) -> PreparedGcsimTeamConfigResult:
    if isinstance(payload, Mapping):
        raw_characters = payload.get("characters") or ()
        source_notes = {
            "adapter": "selected_runtime_team_adapter",
            "input_source": _text(payload.get("source")),
            "input_source_kind": _text(payload.get("source_kind")),
            "account_truth": bool(payload.get("account_truth")),
            "ui_state": bool(payload.get("ui_state")),
            "production_mapping": bool(payload.get("production_mapping")),
            "storage_query": True,
            "network_fetch": False,
            "right_panel_persistence": False,
            "localized_names_used_as_gcsim_identity": False,
            "dev_weapon_candidate_not_account_truth": False,
            "final_stats_as_add_stats": False,
        }
    else:
        raw_characters = payload
        source_notes = {
            "adapter": "selected_runtime_team_adapter",
            "input_source": "selected_runtime_team",
            "input_source_kind": "selected_runtime_team",
            "account_truth": True,
            "ui_state": True,
            "production_mapping": True,
            "storage_query": True,
            "network_fetch": False,
            "right_panel_persistence": False,
            "localized_names_used_as_gcsim_identity": False,
            "dev_weapon_candidate_not_account_truth": False,
            "final_stats_as_add_stats": False,
        }

    characters: list[PreparedGcsimCharacterConfigResult] = []
    for item in raw_characters or ():
        if not isinstance(item, Mapping):
            continue
        character_input = _character_config_input_from_payload(item)
        block = build_gcsim_character_config_block(character_input)
        characters.append(
            PreparedGcsimCharacterConfigResult(
                status=(
                    SELECTED_TEAM_CONFIG_READY
                    if block.ready
                    else SELECTED_TEAM_CONFIG_NOT_READY
                ),
                ready=block.ready,
                character_input=character_input,
                block=block,
                warnings=block.warnings,
                issues=block.issues,
                source_notes=source_notes,
            )
        )

    warnings = _dedupe_tuple(
        warning for result in characters for warning in result.warnings
    )
    issues = tuple(issue for result in characters for issue in result.issues)
    ready = bool(characters) and all(result.ready for result in characters)
    return PreparedGcsimTeamConfigResult(
        status=SELECTED_TEAM_CONFIG_READY if ready else SELECTED_TEAM_CONFIG_NOT_READY,
        ready=ready,
        characters=tuple(characters),
        warnings=warnings,
        issues=issues,
        source_notes=source_notes,
    )


def _character_config_input_from_payload(
    payload: Mapping[str, Any],
) -> GcsimCharacterConfigInput:
    return GcsimCharacterConfigInput(
        project_character_id=_text(
            _first_present(payload, "project_character_id", "character_id", "id")
        ),
        display_name=_text(_first_present(payload, "display_name", "name")),
        level=_first_present(payload, "level", "current_level"),
        promote_level=_first_present(payload, "promote_level", "promote"),
        level_resolution=payload.get("level_resolution"),
        constellation=_first_present(payload, "constellation", "cons"),
        mapping=_mapping_ref_input(
            payload.get("mapping") or payload.get("gcsim_mapping")
        ),
        weapon=_weapon_config_input_from_payload(
            payload.get("weapon") or payload.get("equipped_weapon")
        ),
        artifacts=_artifact_config_input_from_payload(
            payload.get("artifact_build") or payload.get("artifacts")
        ),
        talents=_talent_input_from_payload(payload.get("talents")),
        is_traveler=bool(payload.get("is_traveler")),
    )


def _weapon_config_input_from_payload(value: Any) -> GcsimWeaponConfigInput | None:
    if value is None:
        return None
    if isinstance(value, GcsimWeaponConfigInput):
        return value
    if not isinstance(value, Mapping):
        return None
    return GcsimWeaponConfigInput(
        project_weapon_id=_text(
            _first_present(value, "project_weapon_id", "weapon_id", "id")
        ),
        display_name=_text(_first_present(value, "display_name", "name")),
        level=_first_present(value, "level", "current_level"),
        promote_level=_first_present(value, "promote_level", "promote"),
        level_resolution=value.get("level_resolution"),
        refinement=_first_present(value, "refinement", "refine", "affix_level"),
        mapping=_mapping_ref_input(value.get("mapping") or value.get("gcsim_mapping")),
    )


def _artifact_config_input_from_payload(value: Any) -> GcsimArtifactConfigInput | None:
    if value is None:
        return None
    if isinstance(value, GcsimArtifactConfigInput):
        return value
    if not isinstance(value, Mapping):
        return None
    set_counts_raw = (
        value.get("set_counts")
        or value.get("active_sets")
        or value.get("active_set_bonuses")
        or ()
    )
    stat_totals_raw = value.get("stat_totals") or value.get("total_stats") or ()
    return GcsimArtifactConfigInput(
        set_counts=tuple(
            _artifact_set_config_input_from_payload(item)
            for item in set_counts_raw
            if isinstance(item, Mapping)
        ),
        stat_totals=tuple(
            dict(item) for item in stat_totals_raw if isinstance(item, Mapping)
        ),
    )


def _artifact_set_config_input_from_payload(
    value: Mapping[str, Any],
) -> GcsimArtifactSetConfigInput:
    return GcsimArtifactSetConfigInput(
        set_uid=_text(_first_present(value, "set_uid", "project_id", "id")),
        display_name=_text(_first_present(value, "display_name", "set_name", "name")),
        count=_optional_int(_first_present(value, "count", "piece_count")) or 0,
        mapping=_mapping_ref_input(value.get("mapping") or value.get("gcsim_mapping")),
    )


def _talent_input_from_payload(value: Any) -> GcsimTalentInput | None:
    if value is None:
        return None
    if isinstance(value, GcsimTalentInput):
        return value
    if not isinstance(value, Mapping):
        return None
    return GcsimTalentInput(
        normal=_optional_int(value.get("normal")),
        skill=_optional_int(value.get("skill")),
        burst=_optional_int(value.get("burst")),
        source_order_confirmed=bool(value.get("source_order_confirmed")),
    )


def _mapping_ref_input(value: GcsimMappingRef | Mapping[str, Any] | None) -> GcsimMappingRef:
    if isinstance(value, GcsimMappingRef):
        return value
    if not isinstance(value, Mapping):
        return GcsimMappingRef()
    return GcsimMappingRef(
        gcsim_key=_text(value.get("gcsim_key") or value.get("key")),
        source=_text(value.get("source") or value.get("source_kind")),
        ambiguous=bool(value.get("ambiguous")),
    )


def _build_slot_payload(
    conn: sqlite3.Connection,
    slot: Mapping[str, Any],
    *,
    artifact_set_resolver: Any,
) -> SelectedTeamCharacterDetail:
    slot_index = _optional_int(slot.get("slot_index"))
    slot_index = int(slot_index) if slot_index is not None else -1
    character = _selected_character(slot)
    display_name = _text(character.get("catalog_english_name")) or _text(
        character.get("name")
    )
    character_id = _text(
        _first_present(character, "character_id", "id", "project_character_id")
    )
    issues: list[SelectedTeamConfigIssue] = []
    warnings: list[str] = [WARNING_SELECTED_TEAM_ADAPTER_BOUNDARY]
    if not character_id:
        issues.append(
            _issue(
                "selected_character_id_missing",
                "character.id",
                "Selected character must carry a stable account character id.",
                entity_type="character",
                display_name=display_name,
                slot_index=slot_index,
            )
        )
        return _detail(
            slot_index=slot_index,
            issues=issues,
            warnings=warnings,
        )

    db_character = _account_character_by_id(conn, character_id)
    if db_character:
        character = {**db_character, **_without_empty(character)}
    character_report = _account_character_report(character)
    character_ready = (
        _text(character.get("gcsim_character_key_status")) == "ready"
        and bool(_text(character.get("gcsim_character_key")))
    )
    if not db_character:
        issues.append(
            _issue(
                "account_character_missing",
                "account_characters",
                "Selected account character id was not found in account runtime storage.",
                entity_type="character",
                project_id=character_id,
                display_name=display_name,
                slot_index=slot_index,
            )
        )
    elif not character_ready:
        issues.append(
            _issue(
                "character_gcsim_key_not_ready",
                "account_characters.gcsim_character_key",
                "Stored account character GCSIM key is not ready.",
                entity_type="character",
                project_id=character_id,
                display_name=display_name,
                slot_index=slot_index,
            )
        )

    talents, talent_warnings, talent_issues, talent_report = (
        _talent_input_from_account_rows(conn, character_id)
    )
    warnings.extend(talent_warnings)
    issues.extend(_convert_account_issues(talent_issues, slot_index=slot_index))

    weapon, weapon_method, weapon_issues = _selected_weapon_payload(
        conn,
        slot,
        character_id=character_id,
    )
    issues.extend(weapon_issues)
    weapon_ready = (
        bool(weapon)
        and _text(weapon.get("gcsim_weapon_key_status")) == "ready"
        and bool(_text(weapon.get("gcsim_weapon_key")))
    )
    if weapon and not weapon_ready:
        issues.append(
            _issue(
                "weapon_gcsim_key_not_ready",
                "account_weapon_observed_stacks.gcsim_weapon_key",
                "Selected/current weapon GCSIM key is not ready.",
                entity_type="weapon",
                project_id=_text(weapon.get("weapon_id")),
                display_name=(
                    _text(weapon.get("catalog_english_name"))
                    or _text(weapon.get("name"))
                ),
                slot_index=slot_index,
            )
        )

    artifact_payload, artifact_report, artifact_issues, artifact_warnings = (
        _selected_artifact_payload(
            conn,
            slot,
            character_id=character_id,
            artifact_set_resolver=artifact_set_resolver,
        )
    )
    warnings.extend(artifact_warnings)
    issues.extend(artifact_issues)
    payload_character = {
        "project_character_id": character_id,
        "display_name": (
            _text(character.get("catalog_english_name"))
            or _text(character.get("gcsim_character_key"))
            or display_name
        ),
        "level": character.get("level"),
        "promote_level": character.get("promote_level"),
        "constellation": character.get("constellation"),
        "mapping": {
            "gcsim_key": _text(character.get("gcsim_character_key")),
            "source": "account_sqlite_resolved_character_key",
        },
        "talents": talents,
        "weapon": _weapon_payload(weapon) if weapon else None,
        "artifact_build": artifact_payload,
    }
    ready = not issues
    detail = SelectedTeamCharacterDetail(
        slot_index=slot_index,
        status=SELECTED_TEAM_CONFIG_READY if ready else SELECTED_TEAM_CONFIG_NOT_READY,
        ready=ready,
        account_character=character_report,
        character_found=bool(db_character),
        character_key_ready=character_ready,
        weapon=_weapon_report(weapon) if weapon else {},
        weapon_found=bool(weapon),
        weapon_key_ready=weapon_ready,
        weapon_selection_method=weapon_method,
        artifact_source=_text(artifact_report.get("artifact_source")),
        artifact_account_truth=bool(artifact_report.get("account_truth")),
        artifact_stats_source=_text(artifact_report.get("artifact_stats_source")),
        artifact_set_counts=tuple(
            dict(item)
            for item in artifact_report.get("set_counts", ())
            if isinstance(item, Mapping)
        ),
        current_equipped_artifact_count=_optional_int(
            artifact_report.get("artifact_count")
        )
        or 0,
        talents=talent_report,
        payload_character=payload_character,
        warnings=_dedupe_tuple(warnings),
        issues=tuple(issues),
    )
    return detail


def _selected_weapon_payload(
    conn: sqlite3.Connection,
    slot: Mapping[str, Any],
    *,
    character_id: str,
) -> tuple[dict[str, Any], str, tuple[SelectedTeamConfigIssue, ...]]:
    weapon = _selected_weapon(slot)
    fingerprint = _text(
        _first_present(weapon, "weapon_fingerprint", "source_key", "variant_key")
    )
    if fingerprint:
        row = _weapon_stack_by_fingerprint(conn, fingerprint)
        if row:
            return row, "selected_weapon_fingerprint", ()

    current = _current_equipped_weapon_stack(conn, _optional_int(character_id))
    if current is not None:
        return _row_dict(current), "current_equipped_weapon", ()

    issue = _issue(
        "weapon_missing",
        "account_character_equipped_weapons",
        "Selected team slot has no current/equipped weapon for GCSIM.",
        entity_type="weapon",
        project_id=_text(weapon.get("id") or weapon.get("weapon_id")),
        display_name=_text(weapon.get("catalog_english_name") or weapon.get("name")),
        slot_index=_optional_int(slot.get("slot_index")),
    )
    return {}, "missing_current_weapon", (issue,)


def _selected_artifact_payload(
    conn: sqlite3.Connection,
    slot: Mapping[str, Any],
    *,
    character_id: str,
    artifact_set_resolver: Any,
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any],
    tuple[SelectedTeamConfigIssue, ...],
    tuple[str, ...],
]:
    summary = _slot_artifact_summary(slot)
    if summary:
        payload, report, issues, warnings = _artifact_payload_from_snapshot(
            summary,
            artifact_set_resolver=artifact_set_resolver,
            slot_index=_optional_int(slot.get("slot_index")),
        )
        return payload, report, issues, warnings
    payload, report, account_issues, warnings = _current_artifact_payload_from_account_rows(
        conn,
        character_id,
        artifact_set_resolver=artifact_set_resolver,
    )
    converted = _convert_account_issues(
        account_issues,
        slot_index=_optional_int(slot.get("slot_index")),
    )
    return payload, report, converted, (
        WARNING_SLOT_DB_CURRENT_EQUIPMENT_USED,
        *warnings,
    )


def _artifact_payload_from_snapshot(
    summary: Mapping[str, Any],
    *,
    artifact_set_resolver: Any,
    slot_index: int | None,
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any],
    tuple[SelectedTeamConfigIssue, ...],
    tuple[str, ...],
]:
    artifact_ids_by_pos = _artifact_ids_by_pos(summary.get("artifact_ids_by_pos"))
    missing_positions = _missing_positions(summary, artifact_ids_by_pos)
    issues: list[SelectedTeamConfigIssue] = []
    if missing_positions:
        issues.append(
            _issue(
                "current_artifacts_missing",
                "artifact_build.missing_positions",
                "Need current or selected artifacts for all five slots.",
                entity_type="artifact",
                slot_index=slot_index,
            )
        )

    set_counts: list[dict[str, Any]] = []
    warnings: list[str] = [WARNING_SLOT_DETAILS_SNAPSHOT_USED]
    for item in summary.get("set_counts") or []:
        if not isinstance(item, Mapping):
            continue
        resolved = artifact_set_resolver.resolve(
            set_uid=_text(item.get("set_uid")),
            set_name=_text(item.get("set_name")),
        )
        count = _optional_int(item.get("count")) or 0
        if count >= 2 and not resolved["gcsim_key"]:
            issues.append(
                _issue(
                    "artifact_set_gcsim_key_not_ready",
                    "artifacts.set_uid",
                    "Current artifact set needs a ready GCSIM key mapping.",
                    entity_type="artifact_set",
                    project_id=_text(item.get("set_uid")),
                    display_name=_text(item.get("set_name")) or _text(item.get("set_uid")),
                    slot_index=slot_index,
                )
            )
        warnings.extend(resolved["warnings"])
        set_counts.append(
            {
                "set_uid": _text(item.get("set_uid")),
                "display_name": _text(item.get("set_name")) or _text(item.get("set_uid")),
                "set_name": _text(item.get("set_name")),
                "count": count,
                "mapping": {
                    "gcsim_key": resolved["gcsim_key"],
                    "source": resolved["source"],
                    "ambiguous": resolved["ambiguous"],
                },
            }
        )

    stat_totals = [
        {
            **dict(item),
            "source_kind": ARTIFACT_STATS_SOURCE_CURRENT_EQUIPPED_MAIN_SUB,
        }
        for item in summary.get("stat_totals") or summary.get("total_stats") or []
        if isinstance(item, Mapping)
    ]
    if not stat_totals:
        issues.append(
            _issue(
                "current_artifact_stats_missing",
                "artifact_build.stat_totals",
                "Current or selected artifact stats are required for GCSIM add stats.",
                entity_type="artifact",
                slot_index=slot_index,
            )
        )
    artifact_source = (
        ARTIFACT_SOURCE_MISSING
        if missing_positions
        else ARTIFACT_SOURCE_CURRENT_EQUIPPED
    )
    payload = {
        "artifact_ids_by_pos": {
            str(pos): artifact_id for pos, artifact_id in sorted(artifact_ids_by_pos.items())
        },
        "missing_positions": list(missing_positions),
        "set_counts": set_counts,
        "stat_totals": stat_totals,
        "source": artifact_source,
        "source_kind": "selected_slot_artifact_snapshot",
        "artifact_stats_source": ARTIFACT_STATS_SOURCE_CURRENT_EQUIPPED_MAIN_SUB,
        "right_panel_final_stats_used": False,
        "artifact_set_bonuses_manually_applied": False,
    }
    report = {
        "artifact_source": artifact_source,
        "artifact_stats_source": ARTIFACT_STATS_SOURCE_CURRENT_EQUIPPED_MAIN_SUB,
        "account_truth": not missing_positions,
        "artifact_count": len(artifact_ids_by_pos),
        "artifact_ids_by_pos": dict(artifact_ids_by_pos),
        "missing_positions": list(missing_positions),
        "set_counts": set_counts,
        "stat_total_count": len(stat_totals),
    }
    return payload, report, tuple(issues), _dedupe_tuple(warnings)


def _selected_slots(
    selected_team: TeamBuilderTeamState | Mapping[str, Any] | Iterable[Any],
) -> tuple[dict[str, Any], ...]:
    if isinstance(selected_team, TeamBuilderTeamState):
        return tuple(
            _slot_to_dict(slot)
            for slot in selected_team.slots
            if slot.character is not None
        )
    if isinstance(selected_team, Mapping):
        raw_slots = selected_team.get("slots") or ()
    else:
        raw_slots = selected_team
    slots: list[dict[str, Any]] = []
    for index, item in enumerate(raw_slots or ()):
        slot = _slot_to_dict(item)
        slot.setdefault("slot_index", index)
        if _selected_character(slot):
            slots.append(slot)
    return tuple(slots)


def _slot_to_dict(slot: Any) -> dict[str, Any]:
    to_dict = getattr(slot, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    return dict(slot) if isinstance(slot, Mapping) else {}


def _selected_character(slot: Mapping[str, Any]) -> dict[str, Any]:
    details = _mapping(slot.get("character_details_data"))
    character = _mapping(details.get("account_character"))
    if character:
        return character
    return _mapping(slot.get("character"))


def _selected_weapon(slot: Mapping[str, Any]) -> dict[str, Any]:
    details = _mapping(slot.get("character_details_data"))
    weapon = _mapping(details.get("account_weapon"))
    if weapon:
        return weapon
    return _mapping(slot.get("weapon"))


def _slot_artifact_summary(slot: Mapping[str, Any]) -> dict[str, Any]:
    details = _mapping(slot.get("character_details_data"))
    stat_snapshot = _mapping(details.get("stat_snapshot"))
    artifact = _mapping(stat_snapshot.get("artifact"))
    summary = _mapping(artifact.get("summary"))
    if summary:
        return summary
    build = _mapping(details.get("artifact_build_snapshot"))
    if build:
        return build
    return {}


def _account_character_by_id(conn: sqlite3.Connection, character_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT *
        FROM account_characters
        WHERE character_id = ?
        LIMIT 1
        """,
        (_optional_int(character_id),),
    ).fetchone()
    return _row_dict(row) if row is not None else {}


def _weapon_stack_by_fingerprint(conn: sqlite3.Connection, fingerprint: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT *
        FROM account_weapon_observed_stacks
        WHERE weapon_fingerprint = ?
        LIMIT 1
        """,
        (_text(fingerprint),),
    ).fetchone()
    return _row_dict(row) if row is not None else {}


def _payload_character_from_detail(detail: SelectedTeamCharacterDetail) -> dict[str, Any]:
    return dict(detail.payload_character)


def _attach_block_statuses(
    team: SelectedTeamBuild,
    prepared_team: PreparedGcsimTeamConfigResult,
) -> SelectedTeamBuild:
    prepared = tuple(prepared_team.characters)
    details: list[SelectedTeamCharacterDetail] = []
    for index, detail in enumerate(team.characters):
        block_ready = False
        block_status = detail.block_status
        block_warnings: tuple[str, ...] = ()
        if index < len(prepared):
            result = prepared[index]
            block_ready = bool(result.ready)
            block_status = result.block.status if result.block is not None else result.status
            block_warnings = result.warnings
        details.append(
            SelectedTeamCharacterDetail(
                slot_index=detail.slot_index,
                status=detail.status,
                ready=detail.ready and block_ready,
                account_character=detail.account_character,
                character_found=detail.character_found,
                character_key_ready=detail.character_key_ready,
                weapon=detail.weapon,
                weapon_found=detail.weapon_found,
                weapon_key_ready=detail.weapon_key_ready,
                weapon_selection_method=detail.weapon_selection_method,
                artifact_source=detail.artifact_source,
                artifact_account_truth=detail.artifact_account_truth,
                artifact_stats_source=detail.artifact_stats_source,
                artifact_set_counts=detail.artifact_set_counts,
                current_equipped_artifact_count=detail.current_equipped_artifact_count,
                talents=detail.talents,
                payload_character=detail.payload_character,
                block_ready=block_ready,
                block_status=block_status,
                warnings=_dedupe_tuple([*detail.warnings, *block_warnings]),
                issues=detail.issues,
            )
        )
    return SelectedTeamBuild(
        status=team.status,
        ready=team.ready and prepared_team.ready,
        payload=team.payload,
        characters=tuple(details),
        warnings=team.warnings,
        issues=team.issues,
    )


def _payload(
    *,
    team_index: int,
    required_slots: tuple[int, ...],
    characters: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source": "selected_runtime_team",
        "source_kind": "selected_runtime_team",
        "account_truth": True,
        "account_character_truth": True,
        "account_artifact_truth": True,
        "ui_state": True,
        "production_mapping": True,
        "team_index": int(team_index),
        "required_slots": list(required_slots),
        "source_notes": {
            "selected_team_source": "TeamBuilderState",
            "character_gcsim_identity": "account_characters.gcsim_character_key",
            "weapon_gcsim_identity": "account_weapon_observed_stacks.gcsim_weapon_key",
            "localized_names_used_as_gcsim_identity": False,
            "weapon_source": "selected_or_current_equipped_weapon_only",
            "dev_weapon_candidate_not_account_truth": False,
            "artifact_source": "slot_snapshot_or_current_equipped_artifacts",
            "artifact_stats_source": ARTIFACT_STATS_SOURCE_CURRENT_EQUIPPED_MAIN_SUB,
            "right_panel_final_stats_used": False,
            "artifact_set_bonuses_manually_applied": False,
            "right_panel_persistence": False,
            "final_or_right_panel_stats_as_add_stats": False,
        },
        "characters": [dict(item) for item in characters],
    }


def _detail(
    *,
    slot_index: int,
    issues: list[SelectedTeamConfigIssue],
    warnings: list[str],
) -> SelectedTeamCharacterDetail:
    return SelectedTeamCharacterDetail(
        slot_index=slot_index,
        status=SELECTED_TEAM_CONFIG_NOT_READY,
        ready=False,
        warnings=_dedupe_tuple(warnings),
        issues=tuple(issues),
    )


def _replace_report(
    report: SelectedTeamFullConfigReport,
    *,
    smoke: dict[str, Any] | None = None,
    dps_dummy_run: dict[str, Any] | None = None,
) -> SelectedTeamFullConfigReport:
    return SelectedTeamFullConfigReport(
        status=report.status,
        ready=report.ready,
        db_path=report.db_path,
        team_index=report.team_index,
        team=report.team,
        prepared_team=report.prepared_team,
        assembly=report.assembly,
        full_config=report.full_config,
        config_path=report.config_path,
        wrote_config=report.wrote_config,
        smoke=smoke if smoke is not None else report.smoke,
        dps_dummy_run=(
            dps_dummy_run if dps_dummy_run is not None else report.dps_dummy_run
        ),
        warnings=report.warnings,
        issues=report.issues,
        source_notes=report.source_notes,
    )


def _convert_account_issues(
    issues: Iterable[AccountPreparedConfigIssue],
    *,
    slot_index: int | None,
) -> tuple[SelectedTeamConfigIssue, ...]:
    return tuple(
        _issue(
            issue.status,
            issue.field,
            issue.message,
            slot_index=slot_index,
        )
        for issue in issues
    )


def _issue(
    status: str,
    field: str,
    message: str,
    *,
    entity_type: str = "",
    project_id: str = "",
    display_name: str = "",
    slot_index: int | None = None,
) -> SelectedTeamConfigIssue:
    return SelectedTeamConfigIssue(
        status=status,
        field=field,
        message=message,
        entity_type=entity_type,
        project_id=project_id,
        display_name=display_name,
        slot_index=slot_index,
    )


def _artifact_ids_by_pos(value: Any) -> dict[int, int]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[int, int] = {}
    for pos, artifact_id in value.items():
        pos_int = _optional_int(pos)
        artifact_id_int = _optional_int(artifact_id)
        if pos_int in ARTIFACT_POSITIONS and artifact_id_int is not None:
            result[int(pos_int)] = int(artifact_id_int)
    return dict(sorted(result.items()))


def _missing_positions(
    summary: Mapping[str, Any],
    artifact_ids_by_pos: Mapping[int, int],
) -> tuple[int, ...]:
    raw = summary.get("missing_positions")
    if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes)):
        result = [
            int(pos)
            for pos in (_optional_int(item) for item in raw)
            if pos in ARTIFACT_POSITIONS
        ]
        return tuple(sorted(set(result)))
    return tuple(pos for pos in ARTIFACT_POSITIONS if pos not in artifact_ids_by_pos)


def _config_output_path(
    *,
    config_out: str | Path | None,
    run_dir: str | Path,
) -> Path:
    if config_out:
        return Path(config_out)
    return Path(run_dir) / "config.txt"


def _new_selected_config_run_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return DEFAULT_GCSIM_RUNS_DIR / f"selected-team-config-{stamp}"


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _without_empty(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): item for key, item in value.items() if item not in (None, "")}


def _first_present(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return None


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe_tuple(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return tuple(result)
