"""Account SQLite -> prepared backend/dev GCSIM config bridge.

This module is the first narrow adapter that reads real account runtime rows
and feeds the existing prepared config/block/assembly boundary. It is still
backend/dev-only: it does not read UI state, persist right-panel selections,
query network data, rebuild/run engine updates, or treat localized account
display names as GCSIM identities.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Iterable, Mapping
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any, TextIO
from urllib.parse import quote

from hoyolab_export.account_storage import DEFAULT_ACCOUNT_DB_PATH
from hoyolab_export.artifact_db import calculate_raw_build_summary
from run_workspace.gcsim.abyss_wave_scenario_smoke import run_abyss_wave_scenario_smoke
from run_workspace.gcsim.artifact_runner import (
    DEFAULT_GCSIM_RUNS_DIR,
    run_active_gcsim_artifact,
)
from run_workspace.gcsim.config_assembly import (
    CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH,
)
from run_workspace.gcsim.config_talents import (
    GcsimConstellationSource,
    GcsimTalentSource,
    prepare_gcsim_talent_levels,
)
from run_workspace.gcsim.entity_key_readiness_report import (
    DEFAULT_ARTIFACT_SET_SHORTCUT_SOURCE,
    load_gcsim_shortcut_keys,
    normalize_gcsim_key_candidate,
)
from run_workspace.gcsim.enemy_type_registry import (
    find_default_gcsim_enemy_shortcut_source,
)
from run_workspace.gcsim.prepared_config_adapter import (
    PreparedGcsimFullConfigResult,
    build_prepared_team_full_config_report,
)
from run_workspace.gcsim.runtime_probe import DEFAULT_GO_PROBE_TIMEOUT_SECONDS
from run_workspace.gcsim.snap_monster_titles import SnapJsonFetcher


ACCOUNT_PREPARED_CONFIG_READY = "ready"
ACCOUNT_PREPARED_CONFIG_NOT_READY = "not_ready"
ACCOUNT_PREPARED_CONFIG_INPUT_ERROR = "input_error"
ACCOUNT_PREPARED_CONFIG_SMOKE_SKIPPED = "smoke_skipped"

WARNING_DEV_WEAPON_CANDIDATE_NOT_ACCOUNT_TRUTH = (
    "dev_weapon_candidate_not_account_truth"
)
WARNING_TALENT_ORDER_SKILL_ID_DEV_ASSUMED = "dev_talent_order_skill_id_assumed"
WARNING_ARTIFACT_SET_AUTO_REGISTRY_MAPPING = (
    "artifact_set_auto_registry_mapping_not_curated"
)
WARNING_DEV_ENERGY_LINE_APPENDED = "dev_energy_line_appended_no_existing_energy_line"

ARTIFACT_SOURCE_CURRENT_EQUIPPED = "current_equipped_artifacts"
ARTIFACT_SOURCE_MISSING = "missing_current_equipped_artifacts"
ARTIFACT_STATS_SOURCE_CURRENT_EQUIPPED_MAIN_SUB = (
    "current_equipped_artifact_main_sub_stats"
)

DEFAULT_ACCOUNT_CHASCA_TEAM: tuple[str, ...] = (
    "Chasca",
    "Ororon",
    "Furina",
    "Bennett",
)
DEFAULT_ABYSS_SMOKE_PERIOD_START = "2026-02-16"
DEFAULT_ABYSS_SMOKE_FLOOR = 12
DEFAULT_ABYSS_SMOKE_CHAMBER = 1
DEFAULT_ABYSS_SMOKE_SIDE = 1
DEFAULT_DEV_ENERGY_OVERRIDE_LINE = "energy every interval=480,720 amount=100;"


ArtifactRunFunc = Any


@dataclass(frozen=True, slots=True)
class AccountPreparedConfigIssue:
    status: str
    field: str
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "field": self.field,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class AccountPreparedCharacterDetail:
    requested_name: str
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
    block_ready: bool = False
    block_status: str = ""
    warnings: tuple[str, ...] = ()
    issues: tuple[AccountPreparedConfigIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_name": self.requested_name,
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
            "block_ready": self.block_ready,
            "block_status": self.block_status,
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class AccountPreparedTeamBuild:
    status: str
    ready: bool
    payload: dict[str, Any] = field(default_factory=dict)
    characters: tuple[AccountPreparedCharacterDetail, ...] = ()
    warnings: tuple[str, ...] = ()
    issues: tuple[AccountPreparedConfigIssue, ...] = ()

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
class AccountPreparedFullConfigReport:
    status: str
    ready: bool
    db_path: str
    team_request: tuple[str, ...]
    team: AccountPreparedTeamBuild
    full_config: PreparedGcsimFullConfigResult
    smoke: dict[str, Any] | None = None
    warnings: tuple[str, ...] = ()
    issues: tuple[dict[str, Any], ...] = ()
    source_notes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "db_path": self.db_path,
            "team_request": list(self.team_request),
            "team": self.team.to_dict(),
            "full_config": self.full_config.to_dict(),
            "config_path": self.full_config.config_path,
            "wrote_config": self.full_config.wrote_config,
            "smoke": dict(self.smoke) if self.smoke is not None else None,
            "warnings": list(self.warnings),
            "issues": [dict(issue) for issue in self.issues],
            "source_notes": dict(self.source_notes),
        }


def build_account_prepared_team_payload(
    *,
    db_path: str | Path = DEFAULT_ACCOUNT_DB_PATH,
    team_names: Iterable[str] = DEFAULT_ACCOUNT_CHASCA_TEAM,
    artifact_set_registry_source: str | Path | None = None,
) -> AccountPreparedTeamBuild:
    names = tuple(_text(name) for name in team_names if _text(name))
    used_weapon_counts: defaultdict[str, int] = defaultdict(int)
    payload_characters: list[dict[str, Any]] = []
    details: list[AccountPreparedCharacterDetail] = []
    artifact_set_resolver = _artifact_set_key_resolver(artifact_set_registry_source)

    with closing(_connect_readonly_db(db_path)) as conn:
        for requested_name in names:
            character_row = _find_account_character(conn, requested_name)
            if character_row is None:
                issue = AccountPreparedConfigIssue(
                    "missing_account_character",
                    "account_characters",
                    f"Account character was not found by catalog English name or stored GCSIM key: {requested_name}.",
                )
                details.append(
                    AccountPreparedCharacterDetail(
                        requested_name=requested_name,
                        status=ACCOUNT_PREPARED_CONFIG_NOT_READY,
                        ready=False,
                        issues=(issue,),
                    )
                )
                continue

            character = _row_dict(character_row)
            character_ready = (
                _text(character.get("gcsim_character_key_status")) == "ready"
                and bool(_text(character.get("gcsim_character_key")))
            )
            issues: list[AccountPreparedConfigIssue] = []
            warnings: list[str] = []
            if not character_ready:
                issues.append(
                    AccountPreparedConfigIssue(
                        "character_gcsim_key_not_ready",
                        "account_characters.gcsim_character_key",
                        "Stored account character GCSIM key is not ready.",
                    )
                )

            (
                talents,
                talent_warnings,
                talent_issues,
                talent_report,
            ) = _talent_input_from_account_rows(
                conn,
                character.get("character_id"),
            )
            warnings.extend(talent_warnings)
            issues.extend(talent_issues)

            weapon_row, weapon_method, weapon_warnings = _select_weapon_stack(
                conn,
                character,
                used_weapon_counts=used_weapon_counts,
            )
            warnings.extend(weapon_warnings)
            weapon: dict[str, Any] = {}
            weapon_ready = False
            if weapon_row is None:
                issues.append(
                    AccountPreparedConfigIssue(
                        "weapon_missing",
                        "account_weapon_observed_stacks",
                        "No current or deterministic ready observed weapon stack was found.",
                    )
                )
            else:
                weapon = _row_dict(weapon_row)
                weapon_ready = (
                    _text(weapon.get("gcsim_weapon_key_status")) == "ready"
                    and bool(_text(weapon.get("gcsim_weapon_key")))
                )
                if not weapon_ready:
                    issues.append(
                        AccountPreparedConfigIssue(
                            "weapon_gcsim_key_not_ready",
                            "account_weapon_observed_stacks.gcsim_weapon_key",
                            "Selected account weapon stack GCSIM key is not ready.",
                        )
                    )

            (
                artifact_payload,
                artifact_report,
                artifact_issues,
                artifact_warnings,
            ) = _current_artifact_payload_from_account_rows(
                conn,
                character.get("character_id"),
                artifact_set_resolver=artifact_set_resolver,
            )
            warnings.extend(artifact_warnings)
            issues.extend(artifact_issues)

            character_payload = {
                "project_character_id": _text(character.get("character_id")),
                "display_name": (
                    _text(character.get("catalog_english_name"))
                    or _text(character.get("gcsim_character_key"))
                ),
                "level": character.get("level"),
                "constellation": character.get("constellation"),
                "mapping": {
                    "gcsim_key": _text(character.get("gcsim_character_key")),
                    "source": "account_sqlite_resolved_character_key",
                },
                "talents": talents,
                "weapon": _weapon_payload(weapon) if weapon else None,
                "artifact_build": artifact_payload,
            }
            payload_characters.append(character_payload)
            details.append(
                AccountPreparedCharacterDetail(
                    requested_name=requested_name,
                    status=(
                        ACCOUNT_PREPARED_CONFIG_READY
                        if not issues
                        else ACCOUNT_PREPARED_CONFIG_NOT_READY
                    ),
                    ready=not issues,
                    account_character=_account_character_report(character),
                    character_found=True,
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
                    warnings=_dedupe_tuple(warnings),
                    issues=tuple(issues),
                )
            )

    uses_dev_weapon_fallback = any(
        WARNING_DEV_WEAPON_CANDIDATE_NOT_ACCOUNT_TRUTH in detail.warnings
        for detail in details
    )
    all_artifacts_account_truth = bool(details) and all(
        detail.artifact_account_truth for detail in details
    )
    payload = {
        "schema_version": 1,
        "source": "account_sqlite_backend_dev_adapter",
        "source_kind": "backend_dev_account_sqlite",
        "account_truth": not uses_dev_weapon_fallback and all_artifacts_account_truth,
        "account_character_truth": True,
        "account_artifact_truth": all_artifacts_account_truth,
        "ui_state": False,
        "production_mapping": False,
        "required_characters": list(names),
        "source_notes": {
            "account_characters_source": "account_characters",
            "character_gcsim_identity": "account_characters.gcsim_character_key",
            "localized_names_used_as_gcsim_identity": False,
            "weapon_source": (
                "current_equipped_weapon_when_present_else_deterministic_dev_candidate"
            ),
            "dev_weapon_candidate_not_account_truth": uses_dev_weapon_fallback,
            "artifact_source": ARTIFACT_SOURCE_CURRENT_EQUIPPED,
            "artifact_stats_source": ARTIFACT_STATS_SOURCE_CURRENT_EQUIPPED_MAIN_SUB,
            "right_panel_final_stats_used": False,
            "artifact_set_bonuses_manually_applied": False,
            "right_panel_persistence": False,
            "final_or_right_panel_stats_as_add_stats": False,
        },
        "characters": payload_characters,
    }
    warnings = _dedupe_tuple(
        warning
        for detail in details
        for warning in detail.warnings
    )
    issues = tuple(
        issue
        for detail in details
        for issue in detail.issues
    )
    ready = bool(details) and all(detail.ready for detail in details)
    return AccountPreparedTeamBuild(
        status=ACCOUNT_PREPARED_CONFIG_READY if ready else ACCOUNT_PREPARED_CONFIG_NOT_READY,
        ready=ready,
        payload=payload,
        characters=tuple(details),
        warnings=warnings,
        issues=issues,
    )


def build_account_prepared_full_config_report(
    *,
    db_path: str | Path = DEFAULT_ACCOUNT_DB_PATH,
    team_names: Iterable[str] = DEFAULT_ACCOUNT_CHASCA_TEAM,
    rotation_shell_path: str | Path = CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH,
    config_out: str | Path | None = None,
    run_dir: str | Path | None = None,
    write_config: bool = True,
    run_abyss_smoke: bool = False,
    abyss_period_start: str = DEFAULT_ABYSS_SMOKE_PERIOD_START,
    abyss_floor: int = DEFAULT_ABYSS_SMOKE_FLOOR,
    abyss_chamber: int = DEFAULT_ABYSS_SMOKE_CHAMBER,
    abyss_side: int = DEFAULT_ABYSS_SMOKE_SIDE,
    abyss_fact_dps_multi_target_enabled: bool = True,
    abyss_cache_dir: str | Path | None = None,
    gcsim_enemy_registry_source: str | Path | None = None,
    snap_monster_cache_path: str | Path | None = None,
    artifact_set_registry_source: str | Path | None = None,
    store_dir: str | Path | None = None,
    timeout_seconds: int = DEFAULT_GO_PROBE_TIMEOUT_SECONDS,
    dev_energy_override_line: str = "",
    artifact_run_func: ArtifactRunFunc = run_active_gcsim_artifact,
    snap_fetcher: SnapJsonFetcher | None = None,
) -> AccountPreparedFullConfigReport:
    names = tuple(_text(name) for name in team_names if _text(name))
    team = build_account_prepared_team_payload(
        db_path=db_path,
        team_names=names,
        artifact_set_registry_source=artifact_set_registry_source,
    )
    effective_run_dir = (
        run_dir
        if run_dir is not None or config_out is not None
        else _new_account_config_run_dir()
    )
    energy_override_report: dict[str, Any] = {
        "enabled": False,
        "line": "",
        "shell_path": "",
        "replaced_existing_energy_line": False,
        "warnings": [],
    }
    effective_rotation_shell_path: str | Path = rotation_shell_path
    dev_energy_line = _text(dev_energy_override_line)
    if dev_energy_line:
        if effective_run_dir is None:
            effective_run_dir = Path(config_out).resolve().parent if config_out else _new_account_config_run_dir()
        effective_rotation_shell_path, energy_override_report = (
            _write_rotation_shell_with_energy_override(
                rotation_shell_path,
                run_dir=effective_run_dir,
                energy_line=dev_energy_line,
            )
        )
    full_config = build_prepared_team_full_config_report(
        team.payload,
        rotation_shell_path=effective_rotation_shell_path,
        config_out=config_out,
        run_dir=effective_run_dir,
        write_config=write_config,
    )
    characters = _attach_block_statuses(team.characters, full_config)
    team = AccountPreparedTeamBuild(
        status=team.status,
        ready=team.ready and full_config.team.ready,
        payload=team.payload,
        characters=characters,
        warnings=team.warnings,
        issues=team.issues,
    )
    smoke = None
    if run_abyss_smoke:
        smoke = _run_optional_abyss_smoke(
            full_config,
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
    warnings = _dedupe_tuple([*team.warnings, *full_config.warnings])
    warnings = _dedupe_tuple([*warnings, *energy_override_report.get("warnings", [])])
    status = (
        ACCOUNT_PREPARED_CONFIG_READY
        if full_config.ready
        else ACCOUNT_PREPARED_CONFIG_NOT_READY
    )
    return AccountPreparedFullConfigReport(
        status=status,
        ready=full_config.ready,
        db_path=str(db_path),
        team_request=names,
        team=team,
        full_config=full_config,
        smoke=smoke,
        warnings=warnings,
        issues=tuple(full_config.issues),
        source_notes={
            "adapter": "account_sqlite_backend_dev_adapter",
            "storage_query": True,
            "ui_access": False,
            "network_fetch": False,
            "right_panel_persistence": False,
            "localized_names_used_as_gcsim_identity": False,
            "final_or_right_panel_stats_as_add_stats": False,
            "dev_weapon_candidate_not_account_truth": True,
            "artifact_source": ARTIFACT_SOURCE_CURRENT_EQUIPPED,
            "artifact_stats_source": ARTIFACT_STATS_SOURCE_CURRENT_EQUIPPED_MAIN_SUB,
            "dev_energy_override": energy_override_report,
        },
    )


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
        report = build_account_prepared_full_config_report(
            db_path=args.db_path,
            team_names=args.team_character or DEFAULT_ACCOUNT_CHASCA_TEAM,
            rotation_shell_path=args.rotation_shell,
            config_out=args.config_out,
            run_dir=args.run_dir,
            write_config=not args.no_write,
            run_abyss_smoke=args.run_abyss_smoke,
            abyss_period_start=args.abyss_period_start,
            abyss_floor=args.abyss_floor,
            abyss_chamber=args.abyss_chamber,
            abyss_side=args.abyss_side,
            abyss_cache_dir=args.abyss_cache_dir,
            gcsim_enemy_registry_source=args.gcsim_enemy_registry_source,
            snap_monster_cache_path=args.snap_monster_cache_path,
            artifact_set_registry_source=args.artifact_set_registry_source,
            store_dir=args.store_dir,
            timeout_seconds=args.timeout,
            dev_energy_override_line=(
                args.dev_energy_line if args.dev_energy_override else ""
            ),
            artifact_run_func=artifact_run_func,
            snap_fetcher=snap_fetcher,
        )
    except (OSError, sqlite3.Error, ValueError, json.JSONDecodeError) as exc:
        payload = {
            "status": ACCOUNT_PREPARED_CONFIG_INPUT_ERROR,
            "ready": False,
            "error": str(exc),
        }
        _print_report(payload, format_name=args.format, stdout=output)
        return 2

    payload = report.to_dict()
    _print_report(payload, format_name=args.format, stdout=output)
    return 0 if report.ready else 1


def _find_account_character(
    conn: sqlite3.Connection,
    requested_name: str,
) -> sqlite3.Row | None:
    text = _text(requested_name)
    if not text:
        return None
    rows = conn.execute(
        """
        SELECT *
        FROM account_characters
        WHERE LOWER(catalog_english_name) = LOWER(?)
           OR LOWER(gcsim_character_key) = LOWER(?)
        ORDER BY character_id ASC
        LIMIT 2
        """,
        (text, text),
    ).fetchall()
    return rows[0] if len(rows) == 1 else None


def _talent_input_from_account_rows(
    conn: sqlite3.Connection,
    character_id: Any,
) -> tuple[
    dict[str, Any] | None,
    tuple[str, ...],
    tuple[AccountPreparedConfigIssue, ...],
    dict[str, Any],
]:
    rows = conn.execute(
        """
        SELECT skill_id, skill_type, name, level
        FROM account_character_talents
        WHERE character_id = ?
          AND COALESCE(skill_type, 0) = 1
          AND level IS NOT NULL
        ORDER BY skill_id ASC
        """,
        (_optional_int(character_id),),
    ).fetchall()
    active = [row for row in rows if _optional_int(row["level"]) is not None]
    if len(active) < 3:
        return (
            None,
            (),
            (
                AccountPreparedConfigIssue(
                    "talents_missing",
                    "account_character_talents",
                    "Need three active skill_type=1 talent levels ordered by skill_id.",
                ),
            ),
            {},
        )
    talents = [
        GcsimTalentSource(
            slot=slot,
            skill_id=_text(row["skill_id"]),
            name=_text(row["name"]),
            displayed_level=_optional_int(row["level"]),
        )
        for slot, row in zip(("normal", "skill", "burst"), active[:3])
    ]
    if any(talent.displayed_level is None or talent.displayed_level < 1 for talent in talents):
        return (
            None,
            (),
            (
                AccountPreparedConfigIssue(
                    "talents_invalid",
                    "account_character_talents.level",
                    "GCSIM parser talent levels must be positive.",
                ),
            ),
            {},
        )
    constellations = _constellation_sources_from_account_rows(conn, character_id)
    preparation = prepare_gcsim_talent_levels(talents, constellations)
    warnings = [
        WARNING_TALENT_ORDER_SKILL_ID_DEV_ASSUMED,
        *preparation.warnings,
    ]
    talent_input = preparation.to_talent_input_dict()
    if not preparation.ready or talent_input is None:
        return (
            None,
            _dedupe_tuple(warnings),
            (
                AccountPreparedConfigIssue(
                    "talents_invalid",
                    "account_character_talents.level",
                    "GCSIM parser talent levels must be in 1..10 after C3/C5 normalization.",
                ),
            ),
            preparation.to_dict(),
        )
    return (
        talent_input,
        _dedupe_tuple(warnings),
        (),
        preparation.to_dict(),
    )


def _constellation_sources_from_account_rows(
    conn: sqlite3.Connection,
    character_id: Any,
) -> tuple[GcsimConstellationSource, ...]:
    if not _table_exists(conn, "account_character_constellations"):
        return ()
    rows = conn.execute(
        """
        SELECT pos, name, effect, is_actived
        FROM account_character_constellations
        WHERE character_id = ?
        ORDER BY pos ASC
        """,
        (_optional_int(character_id),),
    ).fetchall()
    return tuple(
        GcsimConstellationSource(
            pos=_optional_int(row["pos"]),
            name=_text(row["name"]),
            effect=_text(row["effect"]),
            is_actived=bool(int(row["is_actived"])) if row["is_actived"] is not None else False,
        )
        for row in rows
    )


def _select_weapon_stack(
    conn: sqlite3.Connection,
    character: Mapping[str, Any],
    *,
    used_weapon_counts: defaultdict[str, int],
) -> tuple[sqlite3.Row | None, str, tuple[str, ...]]:
    character_id = _optional_int(character.get("character_id"))
    current = _current_equipped_weapon_stack(conn, character_id)
    if current is not None:
        fingerprint = _text(current["weapon_fingerprint"])
        used_weapon_counts[fingerprint] += 1
        return current, "current_equipped_weapon", ()

    weapon_type = _optional_int(character.get("weapon_type"))
    if weapon_type is None:
        return None, "weapon_type_missing", ()
    candidates = conn.execute(
        """
        SELECT *
        FROM account_weapon_observed_stacks
        WHERE weapon_type = ?
          AND gcsim_weapon_key_status = 'ready'
          AND COALESCE(gcsim_weapon_key, '') != ''
        ORDER BY
          COALESCE(rarity, 0) DESC,
          COALESCE(level, 0) DESC,
          COALESCE(refinement, 0) DESC,
          catalog_english_name COLLATE NOCASE ASC,
          weapon_id ASC,
          weapon_fingerprint ASC
        """,
        (weapon_type,),
    ).fetchall()
    for candidate in candidates:
        fingerprint = _text(candidate["weapon_fingerprint"])
        known_count = max(1, _optional_int(candidate["known_count"]) or 1)
        if used_weapon_counts[fingerprint] >= known_count:
            continue
        used_weapon_counts[fingerprint] += 1
        return (
            candidate,
            "dev_observed_stack_by_weapon_type",
            (WARNING_DEV_WEAPON_CANDIDATE_NOT_ACCOUNT_TRUTH,),
        )
    return None, "no_ready_weapon_candidate", ()


def _current_equipped_weapon_stack(
    conn: sqlite3.Connection,
    character_id: int | None,
) -> sqlite3.Row | None:
    if character_id is None or not _table_exists(conn, "account_character_equipped_weapons"):
        return None
    return conn.execute(
        """
        SELECT w.*
        FROM account_character_equipped_weapons AS equipped
        JOIN account_weapon_observed_stacks AS w
          ON w.weapon_fingerprint = equipped.weapon_fingerprint
        WHERE equipped.character_id = ?
        LIMIT 1
        """,
        (character_id,),
    ).fetchone()


def _current_equipped_artifact_count(
    conn: sqlite3.Connection,
    character_id: Any,
) -> int:
    if not _table_exists(conn, "account_character_equipped_artifacts"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM account_character_equipped_artifacts
        WHERE character_id = ?
        """,
        (_optional_int(character_id),),
    ).fetchone()
    return int(row["count"] if row is not None else 0)


def _current_artifact_payload_from_account_rows(
    conn: sqlite3.Connection,
    character_id: Any,
    *,
    artifact_set_resolver: "_ArtifactSetKeyResolver",
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any],
    tuple[AccountPreparedConfigIssue, ...],
    tuple[str, ...],
]:
    character_id_int = _optional_int(character_id)
    required_tables = (
        "account_character_equipped_artifacts",
        "artifacts",
        "artifact_substats",
    )
    missing_table = next(
        (table for table in required_tables if not _table_exists(conn, table)),
        "",
    )
    if character_id_int is None or missing_table:
        issue = AccountPreparedConfigIssue(
            "current_artifacts_missing",
            missing_table or "account_character_equipped_artifacts",
            "Current equipped artifact owner rows and artifact main/sub stat rows are required.",
        )
        return (
            None,
            {
                "artifact_source": ARTIFACT_SOURCE_MISSING,
                "artifact_stats_source": "",
                "account_truth": False,
                "artifact_count": 0,
                "set_counts": [],
                "missing_positions": [1, 2, 3, 4, 5],
            },
            (issue,),
            (),
        )

    rows = conn.execute(
        """
        SELECT
            equipped.slot_key,
            equipped.artifact_id,
            artifacts.pos,
            artifacts.set_uid,
            artifacts.set_name
        FROM account_character_equipped_artifacts AS equipped
        JOIN artifacts
          ON artifacts.id = equipped.artifact_id
        WHERE equipped.character_id = ?
        ORDER BY artifacts.pos ASC
        """,
        (character_id_int,),
    ).fetchall()
    slots = {
        int(row["pos"]): int(row["artifact_id"])
        for row in rows
        if _optional_int(row["pos"]) is not None
        and _optional_int(row["artifact_id"]) is not None
    }
    summary = calculate_raw_build_summary(conn, slots=slots)
    missing_positions = [
        int(pos)
        for pos in summary.get("missing_positions", [])
        if _optional_int(pos) is not None
    ]
    issues: list[AccountPreparedConfigIssue] = []
    if missing_positions:
        issues.append(
            AccountPreparedConfigIssue(
                "current_artifacts_missing",
                "account_character_equipped_artifacts",
                "Need current equipped artifacts for all five slots.",
            )
        )

    set_counts: list[dict[str, Any]] = []
    warnings: list[str] = []
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
                AccountPreparedConfigIssue(
                    "artifact_set_gcsim_key_not_ready",
                    "artifacts.set_uid",
                    "Current artifact set needs a ready GCSIM key mapping.",
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
        for item in summary.get("total_stats") or []
        if isinstance(item, Mapping)
    ]
    artifact_source = (
        ARTIFACT_SOURCE_MISSING
        if missing_positions
        else ARTIFACT_SOURCE_CURRENT_EQUIPPED
    )
    payload = {
        "artifact_ids_by_pos": {
            str(pos): artifact_id
            for pos, artifact_id in (summary.get("artifact_ids_by_pos") or {}).items()
        },
        "missing_positions": missing_positions,
        "set_counts": set_counts,
        "stat_totals": stat_totals,
        "source": artifact_source,
        "source_kind": "account_sqlite_current_equipped_artifacts",
        "artifact_stats_source": ARTIFACT_STATS_SOURCE_CURRENT_EQUIPPED_MAIN_SUB,
        "right_panel_final_stats_used": False,
        "artifact_set_bonuses_manually_applied": False,
    }
    report = {
        "artifact_source": artifact_source,
        "artifact_stats_source": ARTIFACT_STATS_SOURCE_CURRENT_EQUIPPED_MAIN_SUB,
        "account_truth": not missing_positions,
        "artifact_count": len(slots),
        "artifact_ids_by_pos": dict(summary.get("artifact_ids_by_pos") or {}),
        "missing_positions": missing_positions,
        "set_counts": set_counts,
        "stat_total_count": len(stat_totals),
    }
    return payload, report, tuple(issues), _dedupe_tuple(warnings)


class _ArtifactSetKeyResolver:
    def __init__(self, keys: Iterable[str]) -> None:
        self._index: dict[str, tuple[str, ...]] = {}
        grouped: defaultdict[str, list[str]] = defaultdict(list)
        for key in keys:
            normalized = normalize_gcsim_key_candidate(key)
            if normalized:
                grouped[normalized].append(_text(key))
        self._index = {key: tuple(values) for key, values in grouped.items()}

    def resolve(self, *, set_uid: str, set_name: str) -> dict[str, Any]:
        candidates: list[str] = []
        source_basis = ""
        for label, value in (("set_uid", set_uid), ("set_name", set_name)):
            normalized = normalize_gcsim_key_candidate(value)
            if not normalized:
                continue
            matches = self._index.get(normalized, ())
            if matches:
                candidates.extend(matches)
                source_basis = source_basis or label
        candidates_tuple = _dedupe_tuple(candidates)
        if len(candidates_tuple) == 1:
            return {
                "gcsim_key": candidates_tuple[0],
                "source": f"gcsim_artifact_registry_exact_{source_basis}",
                "ambiguous": False,
                "warnings": (WARNING_ARTIFACT_SET_AUTO_REGISTRY_MAPPING,),
            }
        if len(candidates_tuple) > 1:
            return {
                "gcsim_key": "",
                "source": "gcsim_artifact_registry_ambiguous",
                "ambiguous": True,
                "warnings": (),
            }
        return {
            "gcsim_key": "",
            "source": "gcsim_artifact_registry_missing",
            "ambiguous": False,
            "warnings": (),
        }


def _artifact_set_key_resolver(
    source_path: str | Path | None,
) -> _ArtifactSetKeyResolver:
    path = Path(source_path) if source_path else DEFAULT_ARTIFACT_SET_SHORTCUT_SOURCE
    if not path.is_file():
        return _ArtifactSetKeyResolver(())
    return _ArtifactSetKeyResolver(load_gcsim_shortcut_keys(path))


def _weapon_payload(weapon: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "project_weapon_id": _text(weapon.get("weapon_id")),
        "display_name": (
            _text(weapon.get("catalog_english_name"))
            or _text(weapon.get("gcsim_weapon_key"))
        ),
        "level": weapon.get("level"),
        "promote_level": weapon.get("promote_level"),
        "refinement": weapon.get("refinement"),
        "mapping": {
            "gcsim_key": _text(weapon.get("gcsim_weapon_key")),
            "source": "account_sqlite_resolved_weapon_key",
        },
    }


def override_rotation_shell_energy_line(
    shell_text: str,
    energy_line: str = DEFAULT_DEV_ENERGY_OVERRIDE_LINE,
) -> tuple[str, bool]:
    line = _text(energy_line)
    if not line.startswith("energy ") or not line.endswith(";"):
        raise ValueError("dev energy override line must be a complete GCSIM energy line")
    output_lines: list[str] = []
    replaced = False
    for existing in str(shell_text).splitlines():
        if not replaced and existing.strip().startswith("energy "):
            output_lines.append(line)
            replaced = True
        else:
            output_lines.append(existing)
    if not replaced:
        output_lines.append(line)
    return "\n".join(output_lines) + "\n", replaced


def _write_rotation_shell_with_energy_override(
    rotation_shell_path: str | Path,
    *,
    run_dir: str | Path,
    energy_line: str,
) -> tuple[Path, dict[str, Any]]:
    source_path = Path(rotation_shell_path)
    shell_text = source_path.read_text(encoding="utf-8-sig")
    replaced_text, replaced = override_rotation_shell_energy_line(
        shell_text,
        energy_line,
    )
    destination_dir = Path(run_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = destination_dir / "rotation_shell.dev_energy_override.txt"
    destination_path.write_text(replaced_text, encoding="utf-8")
    warnings = [] if replaced else [WARNING_DEV_ENERGY_LINE_APPENDED]
    return destination_path, {
        "enabled": True,
        "line": _text(energy_line),
        "shell_path": str(destination_path),
        "source_shell_path": str(source_path),
        "replaced_existing_energy_line": replaced,
        "warnings": warnings,
        "dev_only": True,
    }


def _run_optional_abyss_smoke(
    full_config: PreparedGcsimFullConfigResult,
    *,
    abyss_period_start: str,
    abyss_floor: int,
    abyss_chamber: int,
    abyss_side: int,
    abyss_fact_dps_multi_target_enabled: bool,
    abyss_cache_dir: str | Path | None,
    gcsim_enemy_registry_source: str | Path | None,
    snap_monster_cache_path: str | Path | None,
    store_dir: str | Path | None,
    timeout_seconds: int,
    artifact_run_func: ArtifactRunFunc,
    snap_fetcher: SnapJsonFetcher | None,
) -> dict[str, Any]:
    if not full_config.ready or not full_config.config_path:
        return {
            "success": False,
            "status": ACCOUNT_PREPARED_CONFIG_SMOKE_SKIPPED,
            "reason": "config_not_ready",
        }
    registry_path = _resolve_enemy_registry_source(gcsim_enemy_registry_source)
    if registry_path is None:
        return {
            "success": False,
            "status": ACCOUNT_PREPARED_CONFIG_SMOKE_SKIPPED,
            "reason": "gcsim_enemy_registry_source_missing",
        }
    run_dir = str(Path(full_config.config_path).parent)
    args = argparse.Namespace(
        period_start=_text(abyss_period_start),
        floor=int(abyss_floor),
        period_path=None,
        cache_dir=None if abyss_cache_dir is None else str(abyss_cache_dir),
        chamber=int(abyss_chamber),
        side=int(abyss_side),
        enemy_type_map=None,
        gcsim_enemy_registry_source=str(registry_path),
        snap_monster_json=None,
        use_default_remote_snap_monster_json=False,
        use_cached_snap_monster_json=True,
        refresh_snap_monster_json_if_needed=False,
        snap_monster_cache_path=(
            None if snap_monster_cache_path is None else str(snap_monster_cache_path)
        ),
        solo_target_mode=not bool(abyss_fact_dps_multi_target_enabled),
        scenario_out=str(Path(run_dir) / "gtt_wave_scenario.json"),
        config=str(full_config.config_path),
        store_dir=None if store_dir is None else str(store_dir),
        run_dir=run_dir,
        timeout=int(timeout_seconds),
        format="json",
    )
    result = run_abyss_wave_scenario_smoke(
        args,
        artifact_run_func=artifact_run_func,
        snap_fetcher=snap_fetcher,
    )
    result["enemy_mapping_method_counts"] = _enemy_mapping_method_counts(
        result.get("audit") if isinstance(result.get("audit"), Mapping) else {}
    )
    result["scenario_summary"] = _scenario_summary_from_smoke_result(result)
    result["smoke_case"] = {
        "period_start": _text(abyss_period_start),
        "floor": int(abyss_floor),
        "chamber": int(abyss_chamber),
        "side": int(abyss_side),
        "target_mode": (
            "multi_target" if abyss_fact_dps_multi_target_enabled else "solo_target"
        ),
        "network_fetch": False,
        "dps_correctness_claim": False,
    }
    return result


def _enemy_mapping_method_counts(audit: Mapping[str, Any]) -> dict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)
    for detail in audit.get("type_mapping_details") or ():
        if not isinstance(detail, Mapping):
            continue
        method = _text(detail.get("method")) or _text(detail.get("status")) or "unknown"
        counts[method] += 1
    return dict(sorted(counts.items()))


def _scenario_summary_from_smoke_result(result: Mapping[str, Any]) -> dict[str, Any]:
    path = _text(result.get("scenario_path"))
    if not path:
        return {"path": "", "wave_count": 0, "target_count": 0, "total_hp": 0, "waves": []}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "path": path,
            "wave_count": 0,
            "target_count": 0,
            "total_hp": 0,
            "waves": [],
            "error": str(exc),
        }
    waves_report: list[dict[str, Any]] = []
    target_count = 0
    total_hp = 0.0
    for index, wave in enumerate(payload.get("waves") or (), start=1):
        if not isinstance(wave, Mapping):
            continue
        targets: list[dict[str, Any]] = []
        for target in wave.get("targets") or ():
            if not isinstance(target, Mapping):
                continue
            targets.append(
                {
                    "type": _text(target.get("type")),
                    "level": target.get("level"),
                    "hp": target.get("hp"),
                }
            )
            hp = _optional_float(target.get("hp"))
            if hp is not None:
                total_hp += hp
        target_count += len(targets)
        waves_report.append(
            {
                "wave": index,
                "target_count": len(targets),
                "targets": targets,
            }
        )
    return {
        "path": path,
        "schema_version": payload.get("schema_version"),
        "spawn_policy": payload.get("spawn_policy"),
        "wave_count": len(waves_report),
        "target_count": target_count,
        "total_hp": round(total_hp, 6),
        "waves": waves_report,
    }


def _resolve_enemy_registry_source(path: str | Path | None) -> Path | None:
    if path:
        candidate = Path(path)
    else:
        candidate = find_default_gcsim_enemy_shortcut_source()
        if candidate is None:
            return None
    return candidate if candidate.is_file() else None


def _attach_block_statuses(
    details: tuple[AccountPreparedCharacterDetail, ...],
    full_config: PreparedGcsimFullConfigResult,
) -> tuple[AccountPreparedCharacterDetail, ...]:
    results = tuple(full_config.team.characters)
    attached: list[AccountPreparedCharacterDetail] = []
    for index, detail in enumerate(details):
        if index >= len(results):
            attached.append(detail)
            continue
        result = results[index]
        block_status = result.block.status if result.block is not None else result.status
        attached.append(
            AccountPreparedCharacterDetail(
                requested_name=detail.requested_name,
                status=detail.status,
                ready=detail.ready and result.ready,
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
                block_ready=result.ready,
                block_status=block_status,
                warnings=_dedupe_tuple([*detail.warnings, *result.warnings]),
                issues=detail.issues,
            )
        )
    return tuple(attached)


def _account_character_report(character: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "character_id": _text(character.get("character_id")),
        "localized_name": _text(character.get("name")),
        "catalog_english_name": _text(character.get("catalog_english_name")),
        "level": character.get("level"),
        "constellation": character.get("constellation"),
        "weapon_type": character.get("weapon_type"),
        "weapon_type_name": _text(character.get("weapon_type_name")),
        "gcsim_character_key": _text(character.get("gcsim_character_key")),
        "gcsim_character_key_status": _text(
            character.get("gcsim_character_key_status")
        ),
        "gcsim_character_key_method": _text(
            character.get("gcsim_character_key_method")
        ),
    }


def _weapon_report(weapon: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "weapon_fingerprint": _text(weapon.get("weapon_fingerprint")),
        "weapon_id": _text(weapon.get("weapon_id")),
        "localized_name": _text(weapon.get("name")),
        "catalog_english_name": _text(weapon.get("catalog_english_name")),
        "level": weapon.get("level"),
        "promote_level": weapon.get("promote_level"),
        "refinement": weapon.get("refinement"),
        "weapon_type": weapon.get("weapon_type"),
        "weapon_type_name": _text(weapon.get("weapon_type_name")),
        "gcsim_weapon_key": _text(weapon.get("gcsim_weapon_key")),
        "gcsim_weapon_key_status": _text(weapon.get("gcsim_weapon_key_status")),
        "gcsim_weapon_key_method": _text(weapon.get("gcsim_weapon_key_method")),
    }


def _connect_readonly_db(path: str | Path) -> sqlite3.Connection:
    resolved = Path(path).resolve()
    uri_path = quote(resolved.as_posix(), safe="/:")
    conn = sqlite3.connect(f"file:{uri_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _row_dict(row: sqlite3.Row | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        return {key: row[key] for key in row.keys()}
    return dict(row)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        LIMIT 1
        """,
        (_text(table_name),),
    ).fetchone()
    return row is not None


def _new_account_config_run_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return DEFAULT_GCSIM_RUNS_DIR / f"account-prepared-config-{stamp}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a backend/dev GCSIM full config for Chasca/Ororon/Furina/"
            "Bennett from real account SQLite rows plus explicit dev fallbacks."
        )
    )
    parser.add_argument("--db-path", default=str(DEFAULT_ACCOUNT_DB_PATH))
    parser.add_argument(
        "--team-character",
        action="append",
        default=None,
        help=(
            "Catalog English name or stored GCSIM key to include. Repeat for "
            "custom dev teams; defaults to Chasca/Ororon/Furina/Bennett."
        ),
    )
    parser.add_argument(
        "--rotation-shell",
        default=str(CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH),
    )
    parser.add_argument(
        "--artifact-set-registry-source",
        default=None,
        help=(
            "Optional local GCSIM pkg/shortcut/artifacts.go source for exact "
            "set_uid -> GCSIM set key readiness checks. Defaults to the "
            "prepared local v2.42.2 source path when present."
        ),
    )
    parser.add_argument("--config-out", default=None)
    parser.add_argument(
        "--run-dir",
        default=None,
        help=(
            "Run/output directory. Defaults to a new account-prepared-config-* "
            "directory under data/gcsim/runs."
        ),
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--run-abyss-smoke", action="store_true")
    parser.add_argument(
        "--dev-energy-override",
        action="store_true",
        help=(
            "Dev-only: write a temporary rotation shell copy with the energy "
            "line replaced before assembling the full config."
        ),
    )
    parser.add_argument(
        "--dev-energy-line",
        default=DEFAULT_DEV_ENERGY_OVERRIDE_LINE,
        help="Energy line used with --dev-energy-override.",
    )
    parser.add_argument("--abyss-period-start", default=DEFAULT_ABYSS_SMOKE_PERIOD_START)
    parser.add_argument("--abyss-floor", type=int, default=DEFAULT_ABYSS_SMOKE_FLOOR)
    parser.add_argument("--abyss-chamber", type=int, default=DEFAULT_ABYSS_SMOKE_CHAMBER)
    parser.add_argument("--abyss-side", type=int, default=DEFAULT_ABYSS_SMOKE_SIDE)
    parser.add_argument("--abyss-cache-dir", default=None)
    parser.add_argument("--gcsim-enemy-registry-source", default=None)
    parser.add_argument("--snap-monster-cache-path", default=None)
    parser.add_argument("--store-dir", default=None)
    parser.add_argument("--timeout", type=int, default=DEFAULT_GO_PROBE_TIMEOUT_SECONDS)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def _print_report(report: Mapping[str, Any], *, format_name: str, stdout: TextIO) -> None:
    if format_name == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), file=stdout)
        return
    print(_format_text_report(report), file=stdout)


def _format_text_report(report: Mapping[str, Any]) -> str:
    lines = [
        "Account SQLite GCSIM prepared config",
        f"ready={str(bool(report.get('ready'))).lower()} status={report.get('status', '')}",
        f"db={report.get('db_path', '')}",
        "team=" + ",".join(str(item) for item in report.get("team_request") or []),
    ]
    team = report.get("team")
    if isinstance(team, Mapping):
        for item in team.get("characters") or []:
            if not isinstance(item, Mapping):
                continue
            account = item.get("account_character") if isinstance(item.get("account_character"), Mapping) else {}
            weapon = item.get("weapon") if isinstance(item.get("weapon"), Mapping) else {}
            talents = item.get("talents") if isinstance(item.get("talents"), Mapping) else {}
            set_counts = item.get("artifact_set_counts") or []
            talent_summary = _format_talent_summary(talents)
            set_summary = _format_set_counts_summary(set_counts)
            lines.append(
                "character="
                f"requested={item.get('requested_name', '')} "
                f"id={account.get('character_id', '')} "
                f"catalog={account.get('catalog_english_name', '')} "
                f"localized={account.get('localized_name', '')} "
                f"key={account.get('gcsim_character_key', '')} "
                f"character_ready={str(bool(item.get('character_key_ready'))).lower()} "
                f"weapon={weapon.get('catalog_english_name', '') or weapon.get('localized_name', '')} "
                f"weapon_key={weapon.get('gcsim_weapon_key', '')} "
                f"weapon_refine={weapon.get('refinement', '')} "
                f"weapon_level={weapon.get('level', '')} "
                f"weapon_method={item.get('weapon_selection_method', '')} "
                f"talents={talent_summary} "
                f"artifact_source={item.get('artifact_source', '')} "
                f"artifact_stats_source={item.get('artifact_stats_source', '')} "
                f"artifact_count={item.get('current_equipped_artifact_count', '')} "
                f"sets={set_summary} "
                f"block_ready={str(bool(item.get('block_ready'))).lower()} "
                f"block_status={item.get('block_status', '')}"
            )
            warnings = item.get("warnings") or []
            if warnings:
                lines.append(
                    f"character_warnings[{item.get('requested_name', '')}]="
                    + ",".join(str(warning) for warning in warnings)
                )
    if report.get("config_path"):
        lines.append(f"config={report.get('config_path')}")
    source_notes = report.get("source_notes")
    if isinstance(source_notes, Mapping):
        energy = source_notes.get("dev_energy_override")
        if isinstance(energy, Mapping) and energy.get("enabled"):
            lines.append(
                "dev_energy_override="
                f"line={energy.get('line', '')} "
                f"shell={energy.get('shell_path', '')} "
                "dev_only=true"
            )
    smoke = report.get("smoke")
    if isinstance(smoke, Mapping):
        mapping_counts = smoke.get("enemy_mapping_method_counts")
        if isinstance(mapping_counts, Mapping):
            lines.append(
                "enemy_mapping_methods="
                + ",".join(
                    f"{method}:{count}"
                    for method, count in sorted(mapping_counts.items())
                )
            )
        scenario_summary = smoke.get("scenario_summary")
        if isinstance(scenario_summary, Mapping):
            lines.append(
                "scenario_summary="
                f"waves={scenario_summary.get('wave_count', '')} "
                f"targets={scenario_summary.get('target_count', '')} "
                f"spawn_policy={scenario_summary.get('spawn_policy', '')}"
            )
            for wave in scenario_summary.get("waves") or []:
                if not isinstance(wave, Mapping):
                    continue
                target_parts = []
                for target in wave.get("targets") or []:
                    if not isinstance(target, Mapping):
                        continue
                    target_parts.append(
                        f"{target.get('type', '')}@lvl{target.get('level', '')}:hp{target.get('hp', '')}"
                    )
                lines.append(
                    f"wave[{wave.get('wave', '')}]=" + "|".join(target_parts)
                )
        lines.append(
            "optional_smoke="
            f"success={str(bool(smoke.get('success'))).lower()} "
            f"status={smoke.get('status', '')} "
            f"scenario={smoke.get('scenario_path', '')}"
        )
        run_result = smoke.get("run_result")
        if isinstance(run_result, Mapping):
            summary = run_result.get("summary") if isinstance(run_result.get("summary"), Mapping) else {}
            lines.append(
                "smoke_summary="
                f"dps_mean={_format_number(summary.get('dps_mean'))} "
                f"duration_mean={_format_number(summary.get('duration_mean'))} "
                f"total_damage_mean={_format_number(summary.get('total_damage_mean'))} "
                f"run_status={run_result.get('status', '')}"
            )
            lines.append(
                "artifact_preflight="
                f"status={run_result.get('artifact_preflight_status', '')} "
                f"artifact_source={run_result.get('artifact_source', '')}"
            )
            failed_actions = summary.get("failed_actions") or []
            incomplete = summary.get("incomplete_characters") or []
            if failed_actions:
                lines.append("failed_action_buckets=" + _format_failed_action_buckets(failed_actions))
            if incomplete:
                lines.append(
                    "incomplete_characters="
                    + ",".join(str(item) for item in incomplete)
                )
            if run_result.get("success") and smoke.get("status") == "run_passed":
                lines.append(
                    "backend_end_to_end_compatibility_smoke=passed "
                    "dps_correctness_claim=false"
                )
        if smoke.get("reason"):
            lines.append(f"optional_smoke_reason={smoke.get('reason')}")
        if smoke.get("error"):
            lines.append(f"optional_smoke_error={smoke.get('error')}")
    warnings = report.get("warnings") or []
    if warnings:
        lines.append("warnings=" + ",".join(str(item) for item in warnings))
    if report.get("error"):
        lines.append(f"error={report.get('error')}")
    return "\n".join(lines)


def _format_talent_summary(talents: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for item in talents.get("talents") or ():
        if not isinstance(item, Mapping):
            continue
        slot = _text(item.get("slot")) or "talent"
        displayed = item.get("displayed_level")
        bonus = _optional_int(item.get("parsed_constellation_bonus")) or 0
        gcsim = item.get("gcsim_level")
        if bonus:
            parts.append(f"{slot}:{displayed}-{bonus}->{gcsim}")
        else:
            parts.append(f"{slot}:{displayed}->{gcsim}")
    return "|".join(parts)


def _format_set_counts_summary(set_counts: Iterable[Any]) -> str:
    parts: list[str] = []
    for item in set_counts:
        if not isinstance(item, Mapping):
            continue
        name = _text(item.get("set_uid")) or _text(item.get("display_name")) or "set"
        mapping = item.get("mapping") if isinstance(item.get("mapping"), Mapping) else {}
        key = _text(mapping.get("gcsim_key"))
        count = _optional_int(item.get("count")) or 0
        if key:
            parts.append(f"{name}->{key}:{count}")
        else:
            parts.append(f"{name}:missing:{count}")
    return "|".join(parts)


def _format_failed_action_buckets(buckets: Iterable[Any]) -> str:
    parts: list[str] = []
    for index, bucket in enumerate(buckets, start=1):
        if isinstance(bucket, str):
            try:
                parsed = json.loads(bucket)
            except json.JSONDecodeError:
                parsed = bucket
            bucket = parsed
        if not isinstance(bucket, Mapping):
            parts.append(f"{index}:{bucket}")
            continue
        nonzero: list[str] = []
        for name, stats in sorted(bucket.items()):
            if not isinstance(stats, Mapping):
                continue
            mean = _optional_float(stats.get("mean")) or 0.0
            maximum = _optional_float(stats.get("max")) or 0.0
            if mean or maximum:
                nonzero.append(
                    f"{name}(mean={_format_number(mean)},max={_format_number(maximum)})"
                )
        parts.append(f"{index}:{'|'.join(nonzero) if nonzero else 'none'}")
    return ";".join(parts)


def _format_number(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return f"{value:g}"
    return str(value)


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
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


if __name__ == "__main__":
    raise SystemExit(main())
