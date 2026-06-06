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
from hoyolab_export.artifact_stats import (
    ANEMO_DAMAGE,
    ATK_FLAT,
    ATK_PERCENT,
    CRIT_DAMAGE,
    CRIT_RATE,
    ELECTRO_DAMAGE,
    ENERGY_RECHARGE,
    HP_FLAT,
    HP_PERCENT,
    HYDRO_DAMAGE,
)
from run_workspace.gcsim.abyss_wave_scenario_smoke import run_abyss_wave_scenario_smoke
from run_workspace.gcsim.artifact_runner import (
    DEFAULT_GCSIM_RUNS_DIR,
    run_active_gcsim_artifact,
)
from run_workspace.gcsim.config_assembly import (
    CHASCA_ORORON_FURINA_BENNETT_ROTATION_SHELL_PATH,
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
WARNING_SYNTHETIC_DEV_ARTIFACT_STATS_NOT_ACCOUNT_TRUTH = (
    "synthetic_dev_artifact_stats_not_account_truth"
)
WARNING_TALENT_ORDER_SKILL_ID_DEV_ASSUMED = "dev_talent_order_skill_id_assumed"
WARNING_TALENT_LEVEL_CAPPED_TO_GCSIM_PARSER_RANGE = (
    "talent_level_capped_to_gcsim_parser_range_not_account_truth"
)
WARNING_CURRENT_ARTIFACTS_NOT_USED = "current_artifacts_seen_but_not_used"
GCSIM_MAX_PARSER_TALENT_LEVEL = 10

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
    current_equipped_artifact_count: int = 0
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
            "current_equipped_artifact_count": self.current_equipped_artifact_count,
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
) -> AccountPreparedTeamBuild:
    names = tuple(_text(name) for name in team_names if _text(name))
    used_weapon_counts: defaultdict[str, int] = defaultdict(int)
    payload_characters: list[dict[str, Any]] = []
    details: list[AccountPreparedCharacterDetail] = []

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

            talents, talent_warnings, talent_issues = _talent_input_from_account_rows(
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

            artifact_count = _current_equipped_artifact_count(
                conn,
                character.get("character_id"),
            )
            if artifact_count:
                warnings.append(WARNING_CURRENT_ARTIFACTS_NOT_USED)
            warnings.append(WARNING_SYNTHETIC_DEV_ARTIFACT_STATS_NOT_ACCOUNT_TRUTH)
            artifact_payload = _synthetic_artifact_payload_for_character(
                _text(character.get("gcsim_character_key")) or requested_name
            )

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
                    artifact_source="synthetic_dev_artifact_stats",
                    artifact_account_truth=False,
                    current_equipped_artifact_count=artifact_count,
                    warnings=_dedupe_tuple(warnings),
                    issues=tuple(issues),
                )
            )

    payload = {
        "schema_version": 1,
        "source": "account_sqlite_backend_dev_adapter",
        "source_kind": "backend_dev_account_sqlite",
        "account_truth": False,
        "account_character_truth": True,
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
            "dev_weapon_candidate_not_account_truth": True,
            "artifact_source": "synthetic_dev_artifact_stats",
            "synthetic_dev_artifact_stats_not_account_truth": True,
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
    abyss_cache_dir: str | Path | None = None,
    gcsim_enemy_registry_source: str | Path | None = None,
    snap_monster_cache_path: str | Path | None = None,
    store_dir: str | Path | None = None,
    timeout_seconds: int = DEFAULT_GO_PROBE_TIMEOUT_SECONDS,
    artifact_run_func: ArtifactRunFunc = run_active_gcsim_artifact,
    snap_fetcher: SnapJsonFetcher | None = None,
) -> AccountPreparedFullConfigReport:
    names = tuple(_text(name) for name in team_names if _text(name))
    team = build_account_prepared_team_payload(db_path=db_path, team_names=names)
    effective_run_dir = (
        run_dir
        if run_dir is not None or config_out is not None
        else _new_account_config_run_dir()
    )
    full_config = build_prepared_team_full_config_report(
        team.payload,
        rotation_shell_path=rotation_shell_path,
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
            abyss_cache_dir=abyss_cache_dir,
            gcsim_enemy_registry_source=gcsim_enemy_registry_source,
            snap_monster_cache_path=snap_monster_cache_path,
            store_dir=store_dir,
            timeout_seconds=timeout_seconds,
            artifact_run_func=artifact_run_func,
            snap_fetcher=snap_fetcher,
        )
    warnings = _dedupe_tuple([*team.warnings, *full_config.warnings])
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
            "synthetic_dev_artifact_stats_not_account_truth": True,
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
            store_dir=args.store_dir,
            timeout_seconds=args.timeout,
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
) -> tuple[dict[str, Any] | None, tuple[str, ...], tuple[AccountPreparedConfigIssue, ...]]:
    rows = conn.execute(
        """
        SELECT skill_id, skill_type, level
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
        )
    levels = [
        _optional_int(active[0]["level"]),
        _optional_int(active[1]["level"]),
        _optional_int(active[2]["level"]),
    ]
    if any(level is None or level < 1 for level in levels):
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
        )
    capped_levels = [
        min(int(level), GCSIM_MAX_PARSER_TALENT_LEVEL)
        for level in levels
        if level is not None
    ]
    warnings = [WARNING_TALENT_ORDER_SKILL_ID_DEV_ASSUMED]
    if capped_levels != [int(level) for level in levels if level is not None]:
        warnings.append(WARNING_TALENT_LEVEL_CAPPED_TO_GCSIM_PARSER_RANGE)
    return (
        {
            "normal": capped_levels[0],
            "skill": capped_levels[1],
            "burst": capped_levels[2],
            "source_order_confirmed": True,
        },
        tuple(warnings),
        (),
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


def _synthetic_artifact_payload_for_character(character_key: str) -> dict[str, Any]:
    key = _text(character_key).casefold()
    return _SYNTHETIC_ARTIFACTS_BY_CHARACTER_KEY.get(
        key,
        _SYNTHETIC_ARTIFACTS_BY_CHARACTER_KEY["default"],
    )


def _artifact_payload(
    *,
    set_uid: str,
    display_name: str,
    gcsim_key: str,
    stat_totals: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "set_counts": [
            {
                "set_uid": set_uid,
                "display_name": display_name,
                "count": 4,
                "mapping": {
                    "gcsim_key": gcsim_key,
                    "source": "synthetic_dev_artifact_fixture_registry_checked",
                },
            }
        ],
        "stat_totals": [dict(item) for item in stat_totals],
    }


def _stat(property_type: int, raw_value: float | int) -> dict[str, Any]:
    return {
        "property_type": property_type,
        "raw_value": raw_value,
        "source_kind": "synthetic_dev_artifact_stats",
    }


_SYNTHETIC_ARTIFACTS_BY_CHARACTER_KEY: dict[str, dict[str, Any]] = {
    "chasca": _artifact_payload(
        set_uid="synthetic:obsidiancodex",
        display_name="Obsidian Codex",
        gcsim_key="obsidiancodex",
        stat_totals=(
            _stat(HP_FLAT, 4780),
            _stat(ATK_FLAT, 311),
            _stat(ATK_PERCENT, 46.6),
            _stat(CRIT_RATE, 31.1),
            _stat(CRIT_DAMAGE, 62.2),
            _stat(ANEMO_DAMAGE, 46.6),
        ),
    ),
    "ororon": _artifact_payload(
        set_uid="synthetic:scrolloftheheroofcindercity",
        display_name="Scroll of the Hero of Cinder City",
        gcsim_key="scrolloftheheroofcindercity",
        stat_totals=(
            _stat(HP_FLAT, 4780),
            _stat(ATK_FLAT, 311),
            _stat(CRIT_RATE, 31.1),
            _stat(CRIT_DAMAGE, 62.2),
            _stat(ENERGY_RECHARGE, 51.8),
            _stat(ELECTRO_DAMAGE, 46.6),
        ),
    ),
    "furina": _artifact_payload(
        set_uid="synthetic:goldentroupe",
        display_name="Golden Troupe",
        gcsim_key="goldentroupe",
        stat_totals=(
            _stat(HP_FLAT, 4780),
            _stat(HP_PERCENT, 46.6),
            _stat(CRIT_RATE, 31.1),
            _stat(CRIT_DAMAGE, 62.2),
            _stat(ENERGY_RECHARGE, 20),
            _stat(HYDRO_DAMAGE, 46.6),
        ),
    ),
    "bennett": _artifact_payload(
        set_uid="synthetic:noblesseoblige",
        display_name="Noblesse Oblige",
        gcsim_key="noblesseoblige",
        stat_totals=(
            _stat(HP_FLAT, 4780),
            _stat(ATK_FLAT, 311),
            _stat(CRIT_RATE, 31.1),
            _stat(CRIT_DAMAGE, 62.2),
            _stat(ENERGY_RECHARGE, 51.8),
            _stat(ATK_PERCENT, 46.6),
        ),
    ),
    "default": _artifact_payload(
        set_uid="synthetic:noblesseoblige",
        display_name="Noblesse Oblige",
        gcsim_key="noblesseoblige",
        stat_totals=(
            _stat(HP_FLAT, 4780),
            _stat(ATK_FLAT, 311),
            _stat(CRIT_RATE, 31.1),
            _stat(CRIT_DAMAGE, 62.2),
        ),
    ),
}


def _run_optional_abyss_smoke(
    full_config: PreparedGcsimFullConfigResult,
    *,
    abyss_period_start: str,
    abyss_floor: int,
    abyss_chamber: int,
    abyss_side: int,
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
    result["smoke_case"] = {
        "period_start": _text(abyss_period_start),
        "floor": int(abyss_floor),
        "chamber": int(abyss_chamber),
        "side": int(abyss_side),
        "network_fetch": False,
        "dps_correctness_claim": False,
    }
    return result


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
                current_equipped_artifact_count=detail.current_equipped_artifact_count,
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
                f"weapon_method={item.get('weapon_selection_method', '')} "
                f"artifact_source={item.get('artifact_source', '')} "
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
    smoke = report.get("smoke")
    if isinstance(smoke, Mapping):
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
