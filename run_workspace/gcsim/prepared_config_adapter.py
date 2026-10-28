"""Adapter boundary for explicit prepared GCSIM character config inputs.

There is not yet a single production owner for selected team + current weapon +
current artifact build + production GCSIM mappings. This module therefore
accepts explicit backend/dev dictionaries or JSON fixtures and converts them
into `GcsimCharacterConfigInput` without reading widgets, SQLite, network, or
right-panel final stat totals. Future account/team adapters should replace the
fixture shape once that source owner is confirmed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import Any, TextIO

from hoyolab_export.artifact_build_snapshot import (
    ArtifactBuildSnapshot,
    ArtifactStatTotalSnapshot,
    build_artifact_build_snapshot,
)
from run_workspace.gcsim.artifact_runner import DEFAULT_GCSIM_RUNS_DIR
from run_workspace.gcsim.config_assembly import (
    CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH,
    GcsimFullConfigAssembly,
    assemble_gcsim_full_config_from_shell_path,
)
from run_workspace.gcsim.config_blocks import (
    GcsimArtifactConfigInput,
    GcsimArtifactSetConfigInput,
    GcsimCharacterConfigBlock,
    GcsimCharacterConfigInput,
    GcsimConfigBlockIssue,
    GcsimWeaponConfigInput,
    build_gcsim_character_config_block,
)
from run_workspace.gcsim.config_readiness import (
    GcsimMappingRef,
    GcsimTalentInput,
)


PREPARED_CONFIG_READY = "ready"
PREPARED_CONFIG_NOT_READY = "not_ready"
PREPARED_CONFIG_INVALID_INPUT = "invalid_input"
PREPARED_CONFIG_MISSING_CHARACTER = "missing_character"
PREPARED_CONFIG_CONFIG_WRITTEN = "config_written"
PREPARED_CONFIG_WRITE_SKIPPED_NOT_READY = "write_skipped_not_ready"

WARNING_PREPARED_FIXTURE_BOUNDARY = "prepared_fixture_adapter_boundary"
WARNING_NO_UI_OR_STORAGE_ACCESS = "no_ui_or_storage_access"
WARNING_FINAL_STATS_IGNORED = "final_or_right_panel_stats_ignored"
WARNING_SYNTHETIC_DEV_FIXTURE = "synthetic_dev_fixture_not_account_truth"

SMOKE_FIXTURE_DIR = Path(__file__).resolve().parent / "smoke_fixtures"
DEFAULT_PREPARED_CHASCA_TEAM_FIXTURE_PATH = (
    SMOKE_FIXTURE_DIR / "prepared_team_chasca_ororon_furina_bennett.json"
)

_FINAL_STATS_KEYS = {
    "account_stat_sheet",
    "account_stat_totals",
    "character_stats",
    "display_stats",
    "final_stats",
    "right_panel_stats",
    "right_panel_total",
    "stat_sheet",
}


@dataclass(frozen=True, slots=True)
class PreparedGcsimCharacterConfigResult:
    status: str
    ready: bool
    character_input: GcsimCharacterConfigInput | None = None
    block: GcsimCharacterConfigBlock | None = None
    warnings: tuple[str, ...] = ()
    issues: tuple[GcsimConfigBlockIssue, ...] = ()
    source_notes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "character_input": (
                self.character_input.to_dict()
                if self.character_input is not None
                else None
            ),
            "block": self.block.to_dict() if self.block is not None else None,
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
            "source_notes": dict(self.source_notes),
        }


@dataclass(frozen=True, slots=True)
class PreparedGcsimTeamConfigResult:
    status: str
    ready: bool
    characters: tuple[PreparedGcsimCharacterConfigResult, ...] = ()
    warnings: tuple[str, ...] = ()
    issues: tuple[GcsimConfigBlockIssue, ...] = ()
    source_notes: dict[str, Any] = field(default_factory=dict)

    @property
    def ready_blocks(self) -> tuple[GcsimCharacterConfigBlock, ...]:
        return tuple(
            result.block
            for result in self.characters
            if result.ready and result.block is not None
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "characters": [item.to_dict() for item in self.characters],
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
            "source_notes": dict(self.source_notes),
        }


@dataclass(frozen=True, slots=True)
class PreparedGcsimFullConfigResult:
    status: str
    ready: bool
    team: PreparedGcsimTeamConfigResult
    assembly: GcsimFullConfigAssembly
    config_path: str = ""
    wrote_config: bool = False
    warnings: tuple[str, ...] = ()
    issues: tuple[dict[str, Any], ...] = ()
    source_notes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "team": self.team.to_dict(),
            "assembly": self.assembly.to_dict(),
            "config_path": self.config_path,
            "wrote_config": self.wrote_config,
            "warnings": list(self.warnings),
            "issues": [dict(issue) for issue in self.issues],
            "source_notes": dict(self.source_notes),
        }


def adapt_prepared_character_config_input(
    payload: Mapping[str, Any],
) -> PreparedGcsimCharacterConfigResult:
    if not isinstance(payload, Mapping):
        return PreparedGcsimCharacterConfigResult(
            status=PREPARED_CONFIG_INVALID_INPUT,
            ready=False,
            warnings=_default_warnings(),
            source_notes=_source_notes(),
        )

    warnings = list(_default_warnings())
    if any(key in payload for key in _FINAL_STATS_KEYS):
        warnings.append(WARNING_FINAL_STATS_IGNORED)

    character_input = GcsimCharacterConfigInput(
        project_character_id=_text(
            _first_present(payload, "project_character_id", "character_id", "id")
        ),
        display_name=_text(_first_present(payload, "display_name", "name")),
        level=_first_present(payload, "level", "current_level"),
        promote_level=_first_present(payload, "promote_level", "promote"),
        level_resolution=payload.get("level_resolution"),
        constellation=_first_present(payload, "constellation", "cons"),
        mapping=_mapping_ref(
            payload.get("mapping")
            or payload.get("gcsim_mapping")
            or _inline_mapping(payload)
        ),
        weapon=_weapon_input(payload.get("weapon") or payload.get("equipped_weapon")),
        artifacts=_artifact_input(
            payload.get("artifacts")
            or payload.get("artifact_build")
            or payload.get("artifact_build_snapshot")
        ),
        talents=_talent_input(payload.get("talents")),
        is_traveler=bool(payload.get("is_traveler")),
    )
    block = build_gcsim_character_config_block(character_input)
    warnings.extend(block.warnings)
    return PreparedGcsimCharacterConfigResult(
        status=PREPARED_CONFIG_READY if block.ready else PREPARED_CONFIG_NOT_READY,
        ready=block.ready,
        character_input=character_input,
        block=block,
        warnings=_dedupe_tuple(warnings),
        issues=block.issues,
        source_notes=_source_notes(),
    )


def adapt_prepared_team_config_inputs(
    payload: Mapping[str, Any] | Iterable[Mapping[str, Any]],
) -> PreparedGcsimTeamConfigResult:
    source_notes = _source_notes()
    team_warnings: list[str] = []
    required_characters: tuple[str, ...] = ()
    if isinstance(payload, Mapping):
        raw_characters = payload.get("characters")
        if raw_characters is None:
            raw_characters = payload.get("team")
        source_notes = {
            **source_notes,
            "input_source": _text(payload.get("source")),
            "input_source_kind": _text(payload.get("source_kind")),
            "account_truth": bool(payload.get("account_truth")),
            "ui_state": bool(payload.get("ui_state")),
            "production_mapping": bool(payload.get("production_mapping")),
        }
        required_characters = _text_tuple(
            payload.get("required_characters")
            or payload.get("expected_characters")
            or payload.get("required_character_names")
        )
        if _text(payload.get("source")) == "synthetic_dev_fixture":
            team_warnings.append(WARNING_SYNTHETIC_DEV_FIXTURE)
    else:
        raw_characters = payload

    characters_list = [
        adapt_prepared_character_config_input(item)
        for item in (raw_characters or ())
        if isinstance(item, Mapping)
    ]
    missing_required = _missing_required_characters(
        required_characters,
        characters_list,
    )
    for name in missing_required:
        characters_list.append(_missing_character_result(name))

    characters = tuple(characters_list)
    warnings = _dedupe_tuple(
        [
            *team_warnings,
            *(
                warning
                for item in characters
                for warning in item.warnings
            ),
        ]
    )
    issues = tuple(
        issue
        for item in characters
        for issue in item.issues
    )
    ready = bool(characters) and all(item.ready for item in characters)
    return PreparedGcsimTeamConfigResult(
        status=PREPARED_CONFIG_READY if ready else PREPARED_CONFIG_NOT_READY,
        ready=ready,
        characters=characters,
        warnings=warnings,
        issues=issues,
        source_notes=source_notes,
    )


def load_prepared_team_config_inputs_json(
    path: str | Path,
) -> PreparedGcsimTeamConfigResult:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, Mapping):
        return adapt_prepared_team_config_inputs(payload)
    if isinstance(payload, list):
        return adapt_prepared_team_config_inputs(payload)
    return PreparedGcsimTeamConfigResult(
        status=PREPARED_CONFIG_INVALID_INPUT,
        ready=False,
        warnings=_default_warnings(),
        issues=(
            GcsimConfigBlockIssue(
                PREPARED_CONFIG_INVALID_INPUT,
                "payload",
                "Prepared team JSON root must be an object or list.",
            ),
        ),
        source_notes=_source_notes(),
    )


def build_prepared_team_full_config_report(
    payload: Mapping[str, Any] | Iterable[Mapping[str, Any]],
    *,
    rotation_shell_path: str | Path = CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH,
    config_out: str | Path | None = None,
    run_dir: str | Path | None = None,
    write_config: bool = True,
) -> PreparedGcsimFullConfigResult:
    team = adapt_prepared_team_config_inputs(payload)
    blocks = tuple(
        result.block for result in team.characters if result.block is not None
    )
    assembly = assemble_gcsim_full_config_from_shell_path(
        blocks,
        rotation_shell_path,
    )
    warnings = _dedupe_tuple([*team.warnings, *assembly.warnings])
    issues = [
        *_issue_dicts_from_block_issues(team.issues),
        *_issue_dicts_from_assembly(assembly.issues),
    ]
    source_notes = {
        **team.source_notes,
        "rotation_shell_path": str(rotation_shell_path),
        "config_output_generated": False,
        "persistence": False,
        "ui_state_owner": False,
    }

    if not team.ready or not assembly.ready:
        return PreparedGcsimFullConfigResult(
            status=PREPARED_CONFIG_WRITE_SKIPPED_NOT_READY,
            ready=False,
            team=team,
            assembly=assembly,
            warnings=warnings,
            issues=tuple(issues),
            source_notes=source_notes,
        )

    config_path = ""
    wrote_config = False
    if write_config:
        output_path = _config_output_path(config_out=config_out, run_dir=run_dir)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(assembly.config_text, encoding="utf-8")
        config_path = str(output_path)
        wrote_config = True
        source_notes = {
            **source_notes,
            "config_output_generated": True,
            "config_output_path": config_path,
        }

    return PreparedGcsimFullConfigResult(
        status=PREPARED_CONFIG_CONFIG_WRITTEN if wrote_config else PREPARED_CONFIG_READY,
        ready=True,
        team=team,
        assembly=assembly,
        config_path=config_path,
        wrote_config=wrote_config,
        warnings=warnings,
        issues=(),
        source_notes=source_notes,
    )


def build_prepared_team_full_config_report_from_json(
    path: str | Path,
    *,
    rotation_shell_path: str | Path = CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH,
    config_out: str | Path | None = None,
    run_dir: str | Path | None = None,
    write_config: bool = True,
) -> PreparedGcsimFullConfigResult:
    payload = _load_prepared_payload_json(path)
    if not isinstance(payload, (Mapping, list)):
        team = PreparedGcsimTeamConfigResult(
            status=PREPARED_CONFIG_INVALID_INPUT,
            ready=False,
            warnings=_default_warnings(),
            issues=(
                GcsimConfigBlockIssue(
                    PREPARED_CONFIG_INVALID_INPUT,
                    "payload",
                    "Prepared team JSON root must be an object or list.",
                ),
            ),
            source_notes=_source_notes(),
        )
        assembly = assemble_gcsim_full_config_from_shell_path((), rotation_shell_path)
        return PreparedGcsimFullConfigResult(
            status=PREPARED_CONFIG_INVALID_INPUT,
            ready=False,
            team=team,
            assembly=assembly,
            warnings=team.warnings,
            issues=_issue_dicts_from_block_issues(team.issues),
            source_notes=team.source_notes,
        )
    return build_prepared_team_full_config_report(
        payload,
        rotation_shell_path=rotation_shell_path,
        config_out=config_out,
        run_dir=run_dir,
        write_config=write_config,
    )


def main(argv: list[str] | None = None, *, stdout: TextIO | None = None) -> int:
    output = stdout or sys.stdout
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = build_prepared_team_full_config_report_from_json(
            args.fixture,
            rotation_shell_path=args.rotation_shell,
            config_out=args.config_out,
            run_dir=args.run_dir,
            write_config=not args.no_write,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {
            "status": PREPARED_CONFIG_INVALID_INPUT,
            "ready": False,
            "error": str(exc),
        }
        _print_report(report, format_name=args.format, stdout=output)
        return 2

    payload = result.to_dict()
    payload["fixture_path"] = str(args.fixture)
    _print_report(payload, format_name=args.format, stdout=output)
    return 0 if result.ready else 1


def _weapon_input(value: Any) -> GcsimWeaponConfigInput | None:
    if value is None:
        return None
    if isinstance(value, GcsimWeaponConfigInput):
        return value
    if not isinstance(value, Mapping):
        return None
    return GcsimWeaponConfigInput(
        project_weapon_id=_text(_first_present(value, "project_weapon_id", "weapon_id", "id")),
        display_name=_text(_first_present(value, "display_name", "name")),
        level=_first_present(value, "level", "current_level"),
        promote_level=_first_present(value, "promote_level", "promote"),
        level_resolution=value.get("level_resolution"),
        refinement=_first_present(value, "refinement", "refine", "affix_level"),
        mapping=_mapping_ref(
            value.get("mapping")
            or value.get("gcsim_mapping")
            or _inline_mapping(value)
        ),
    )


def _artifact_input(value: Any) -> GcsimArtifactConfigInput | None:
    if value is None:
        return None
    if isinstance(value, GcsimArtifactConfigInput):
        return value
    if isinstance(value, ArtifactBuildSnapshot):
        return _artifact_snapshot_input(value)
    if not isinstance(value, Mapping):
        return None

    snapshot = None
    if value.get("schema_version") and (
        value.get("set_counts") is not None
        or value.get("stat_totals") is not None
        or value.get("artifact_ids_by_pos") is not None
    ):
        snapshot = build_artifact_build_snapshot(value)
    set_counts_raw = (
        value.get("set_counts")
        or value.get("active_sets")
        or value.get("active_set_bonuses")
        or ()
    )
    stat_totals_raw = value.get("stat_totals") or value.get("total_stats") or ()
    if snapshot is not None and not set_counts_raw:
        set_counts_raw = [item.to_dict() for item in snapshot.set_counts]
    if snapshot is not None and not stat_totals_raw:
        stat_totals_raw = [item.to_dict() for item in snapshot.stat_totals]
    return GcsimArtifactConfigInput(
        set_counts=tuple(
            _artifact_set_input(item)
            for item in set_counts_raw
            if isinstance(item, Mapping)
        ),
        stat_totals=tuple(
            item
            for item in stat_totals_raw
            if isinstance(item, (ArtifactStatTotalSnapshot, Mapping))
        ),
    )


def _artifact_snapshot_input(snapshot: ArtifactBuildSnapshot) -> GcsimArtifactConfigInput:
    return GcsimArtifactConfigInput(
        set_counts=tuple(
            GcsimArtifactSetConfigInput(
                set_uid=item.set_uid,
                display_name=item.set_name,
                count=item.count,
            )
            for item in snapshot.set_counts
        ),
        stat_totals=snapshot.stat_totals,
    )


def _artifact_set_input(value: Mapping[str, Any]) -> GcsimArtifactSetConfigInput:
    return GcsimArtifactSetConfigInput(
        set_uid=_text(_first_present(value, "set_uid", "project_id", "id")),
        display_name=_text(_first_present(value, "display_name", "set_name", "name")),
        count=_optional_int(_first_present(value, "count", "piece_count", "owned_count")) or 0,
        mapping=_mapping_ref(
            value.get("mapping")
            or value.get("gcsim_mapping")
            or _inline_mapping(value)
        ),
    )


def _talent_input(value: Any) -> GcsimTalentInput | None:
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


def _mapping_ref(value: GcsimMappingRef | Mapping[str, Any] | None) -> GcsimMappingRef:
    if isinstance(value, GcsimMappingRef):
        return value
    if not isinstance(value, Mapping):
        return GcsimMappingRef()
    return GcsimMappingRef(
        gcsim_key=_text(value.get("gcsim_key") or value.get("key")),
        source=_text(value.get("source") or value.get("source_kind")),
        ambiguous=bool(value.get("ambiguous")),
    )


def _inline_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    if "gcsim_key" not in value and "key" not in value:
        return {}
    return {
        "gcsim_key": value.get("gcsim_key") or value.get("key"),
        "source": value.get("source") or value.get("source_kind"),
        "ambiguous": value.get("ambiguous"),
    }


def _default_warnings() -> tuple[str, ...]:
    return (
        WARNING_PREPARED_FIXTURE_BOUNDARY,
        WARNING_NO_UI_OR_STORAGE_ACCESS,
    )


def _source_notes() -> dict[str, Any]:
    return {
        "adapter": "explicit_prepared_backend_input",
        "ui_access": False,
        "storage_query": False,
        "network_fetch": False,
        "final_stats_as_add_stats": False,
        "selected_team_production_owner": False,
        "current_build_production_owner": False,
    }


def _load_prepared_payload_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _missing_required_characters(
    required: Iterable[str],
    characters: Iterable[PreparedGcsimCharacterConfigResult],
) -> tuple[str, ...]:
    labels: set[str] = set()
    for result in characters:
        character = result.character_input
        if character is None:
            continue
        labels.update(
            _casefold_nonempty(
                (
                    character.display_name,
                    character.project_character_id,
                    character.mapping.gcsim_key,
                )
            )
        )
    return tuple(
        name
        for name in required
        if _text(name).casefold() not in labels
    )


def _missing_character_result(name: str) -> PreparedGcsimCharacterConfigResult:
    issue = GcsimConfigBlockIssue(
        PREPARED_CONFIG_MISSING_CHARACTER,
        "characters",
        f"Required prepared character is missing: {name}.",
    )
    return PreparedGcsimCharacterConfigResult(
        status=PREPARED_CONFIG_NOT_READY,
        ready=False,
        warnings=_default_warnings(),
        issues=(issue,),
        source_notes=_source_notes(),
    )


def _issue_dicts_from_block_issues(
    issues: Iterable[GcsimConfigBlockIssue],
) -> tuple[dict[str, Any], ...]:
    return tuple(issue.to_dict() for issue in issues)


def _issue_dicts_from_assembly(issues: Iterable[Any]) -> tuple[dict[str, Any], ...]:
    return tuple(
        issue.to_dict() if hasattr(issue, "to_dict") else dict(issue)
        for issue in issues
    )


def _config_output_path(
    *,
    config_out: str | Path | None,
    run_dir: str | Path | None,
) -> Path:
    if config_out:
        return Path(config_out)
    run_root = Path(run_dir) if run_dir else _new_prepared_config_run_dir()
    return run_root / "config.txt"


def _new_prepared_config_run_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return DEFAULT_GCSIM_RUNS_DIR / f"prepared-config-{stamp}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a backend/dev GCSIM config from an explicit prepared team "
            "fixture and a rotation shell. This does not read UI, storage, or network."
        )
    )
    parser.add_argument(
        "--fixture",
        default=str(DEFAULT_PREPARED_CHASCA_TEAM_FIXTURE_PATH),
        help="Explicit prepared team JSON fixture path.",
    )
    parser.add_argument(
        "--rotation-shell",
        default=str(CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH),
        help="Rotation/options shell path.",
    )
    parser.add_argument("--config-out", default=None, help="Output config path.")
    parser.add_argument("--run-dir", default=None, help="Output run directory.")
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Audit only; do not write generated full config.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def _print_report(report: Mapping[str, Any], *, format_name: str, stdout: TextIO) -> None:
    if format_name == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), file=stdout)
        return
    print(_format_text_report(report), file=stdout)


def _format_text_report(report: Mapping[str, Any]) -> str:
    lines = [
        "Prepared GCSIM config bridge",
        f"ready={str(bool(report.get('ready'))).lower()} status={report.get('status', '')}",
    ]
    if report.get("fixture_path"):
        lines.append(f"fixture={report.get('fixture_path')}")
    team = report.get("team")
    if isinstance(team, Mapping):
        characters = team.get("characters") or []
        lines.append(
            "team="
            f"ready={str(bool(team.get('ready'))).lower()} "
            f"characters={len(characters)}"
        )
        for index, item in enumerate(characters):
            if not isinstance(item, Mapping):
                continue
            character_input = item.get("character_input")
            block = item.get("block")
            name = ""
            key = ""
            if isinstance(character_input, Mapping):
                name = _text(character_input.get("display_name"))
                mapping = character_input.get("mapping")
                if isinstance(mapping, Mapping):
                    key = _text(mapping.get("gcsim_key"))
            block_status = ""
            if isinstance(block, Mapping):
                block_status = _text(block.get("status"))
            issues = item.get("issues") if isinstance(item.get("issues"), list) else []
            issue_statuses = ",".join(
                _text(issue.get("status"))
                for issue in issues
                if isinstance(issue, Mapping) and _text(issue.get("status"))
            )
            lines.append(
                f"character[{index}]="
                f"name={name} key={key} "
                f"ready={str(bool(item.get('ready'))).lower()} "
                f"status={block_status or item.get('status', '')} "
                f"issues={issue_statuses}"
            )
    assembly = report.get("assembly")
    if isinstance(assembly, Mapping):
        lines.append(
            "assembly="
            f"ready={str(bool(assembly.get('ready'))).lower()} "
            f"status={assembly.get('status', '')} "
            f"active={assembly.get('active_character_key', '')}"
        )
    if report.get("config_path"):
        lines.append(f"config={report.get('config_path')}")
    warnings = report.get("warnings") or []
    if warnings:
        lines.append("warnings=" + ",".join(str(item) for item in warnings))
    issues = report.get("issues") or []
    if issues:
        lines.append(
            "issues="
            + ",".join(
                _text(issue.get("status"))
                for issue in issues
                if isinstance(issue, Mapping) and _text(issue.get("status"))
            )
        )
    if report.get("error"):
        lines.append(f"error={report.get('error')}")
    return "\n".join(lines)


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


def _text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = _text(value)
        return (text,) if text else ()
    if isinstance(value, Iterable):
        return tuple(_text(item) for item in value if _text(item))
    text = _text(value)
    return (text,) if text else ()


def _casefold_nonempty(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(_text(value).casefold() for value in values if _text(value))


def _dedupe_tuple(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return tuple(result)


if __name__ == "__main__":
    raise SystemExit(main())
