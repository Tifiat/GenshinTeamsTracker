from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from .artifact_build_snapshot import (
    ArtifactBuildSnapshot,
    build_artifact_build_snapshot,
)
from .artifact_db import (
    ARTIFACT_DB_PATH,
    calculate_raw_build_summary,
    get_build_preset,
)
from .catalog_sanity import STATUS_SPECIAL_DEFERRED
from .character_stat_snapshot import (
    CharacterStatSnapshot,
    SNAPSHOT_STATUS_PARTIAL,
    SNAPSHOT_STATUS_READY,
    SNAPSHOT_STATUS_UNSUPPORTED,
    WARNING_ARTIFACT_SUMMARY_MISSING,
    WARNING_FINAL_TOTALS_NOT_COMPUTED,
    WARNING_TRAVELER_SPECIAL_DEFERRED,
    account_character_ref,
    account_weapon_ref,
    build_character_stat_snapshot,
)
from .character_stats_catalog import CharacterBaseStatsEntry
from .weapon_stats_catalog import WeaponStatsEntry


TEAM_CARD_DATA_SCHEMA_VERSION = 1

DATA_STATUS_READY = "ready"
DATA_STATUS_PARTIAL = "partial"
DATA_STATUS_UNSUPPORTED = "unsupported"
DATA_STATUS_ERROR = "error"

BUILD_IDENTITY_SOURCE_BUILD_ID = "build_id"
BUILD_IDENTITY_SOURCE_NONE = "none"

ERROR_BUILD_PRESET_NOT_FOUND = "build_preset_not_found"
ERROR_INVALID_BUILD_ID = "invalid_build_id"

WARNING_ARTIFACT_BUILD_SNAPSHOT_MISSING_FOR_SELECTED_BUILD = (
    "artifact_build_snapshot_missing_for_selected_build"
)
WARNING_GCSIM_CONFIG_GENERATION_NOT_IMPLEMENTED = (
    "gcsim_config_generation_not_implemented"
)
WARNING_GCSIM_KEY_MAPPING_NOT_IMPLEMENTED = "gcsim_key_mapping_not_implemented"


class TeamCardDataError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "message": str(self),
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class SelectedBuildProvenance:
    build_id: int | None = None
    build_name: str = ""
    identity_source: str = BUILD_IDENTITY_SOURCE_NONE
    provenance_note: str = (
        "Build id/name are selection provenance only. Saved runs must snapshot "
        "actual artifact/build contents."
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "build_id": self.build_id,
            "build_name": self.build_name,
            "identity_source": self.identity_source,
            "provenance_note": self.provenance_note,
        }


@dataclass(frozen=True, slots=True)
class GcsimReadinessNote:
    config_generation_ready: bool = False
    reasons: tuple[str, ...] = (
        WARNING_GCSIM_CONFIG_GENERATION_NOT_IMPLEMENTED,
        WARNING_GCSIM_KEY_MAPPING_NOT_IMPLEMENTED,
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_generation_ready": self.config_generation_ready,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class CharacterDetailsData:
    schema_version: int
    status: str
    account_character: dict[str, Any]
    account_weapon: dict[str, Any] | None
    selected_build: SelectedBuildProvenance = field(default_factory=SelectedBuildProvenance)
    stat_snapshot: CharacterStatSnapshot | None = None
    warnings: tuple[str, ...] = ()
    source_notes: dict[str, Any] = field(default_factory=dict)
    gcsim_readiness: GcsimReadinessNote = field(default_factory=GcsimReadinessNote)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "account_character": dict(self.account_character),
            "account_weapon": (
                dict(self.account_weapon)
                if self.account_weapon is not None
                else None
            ),
            "selected_build": self.selected_build.to_dict(),
            "stat_snapshot": (
                self.stat_snapshot.to_dict()
                if self.stat_snapshot is not None
                else None
            ),
            "warnings": list(self.warnings),
            "source_notes": dict(self.source_notes),
            "gcsim_readiness": self.gcsim_readiness.to_dict(),
        }


def build_character_details_data(
    *,
    account_character: Mapping[str, Any],
    character_stats_entry: CharacterBaseStatsEntry | None = None,
    account_weapon: Mapping[str, Any] | None = None,
    weapon_stats_entry: WeaponStatsEntry | None = None,
    artifact_build_snapshot: ArtifactBuildSnapshot | Mapping[str, Any] | None = None,
    selected_build_id: int | None = None,
    selected_build_name: str = "",
    character_readiness_status: str | None = None,
    source_notes: Mapping[str, Any] | None = None,
) -> CharacterDetailsData:
    artifact_input = _artifact_input_for_snapshot(
        artifact_build_snapshot,
        selected_build_id=selected_build_id,
    )
    stat_snapshot = build_character_stat_snapshot(
        account_character=account_character,
        character_stats_entry=character_stats_entry,
        account_weapon=account_weapon,
        weapon_stats_entry=weapon_stats_entry,
        artifact_summary=artifact_input,
        character_readiness_status=character_readiness_status,
    )
    selected_build = _selected_build_provenance(
        artifact_build_snapshot,
        selected_build_id=selected_build_id,
        selected_build_name=selected_build_name,
    )
    warnings = list(stat_snapshot.warnings)
    if selected_build_id is not None and artifact_build_snapshot is None:
        warnings.append(WARNING_ARTIFACT_BUILD_SNAPSHOT_MISSING_FOR_SELECTED_BUILD)
    if stat_snapshot.status == SNAPSHOT_STATUS_UNSUPPORTED:
        status = DATA_STATUS_UNSUPPORTED
    elif stat_snapshot.status == SNAPSHOT_STATUS_READY:
        status = DATA_STATUS_READY
    else:
        status = DATA_STATUS_PARTIAL

    gcsim_reasons = [
        WARNING_GCSIM_CONFIG_GENERATION_NOT_IMPLEMENTED,
        WARNING_GCSIM_KEY_MAPPING_NOT_IMPLEMENTED,
        WARNING_FINAL_TOTALS_NOT_COMPUTED,
    ]
    if WARNING_TRAVELER_SPECIAL_DEFERRED in stat_snapshot.warnings:
        gcsim_reasons.append(WARNING_TRAVELER_SPECIAL_DEFERRED)
    if WARNING_ARTIFACT_SUMMARY_MISSING in stat_snapshot.warnings:
        gcsim_reasons.append(WARNING_ARTIFACT_SUMMARY_MISSING)

    character_ref = account_character_ref(account_character)
    weapon_ref = account_weapon_ref(account_weapon) if account_weapon is not None else None
    return CharacterDetailsData(
        schema_version=TEAM_CARD_DATA_SCHEMA_VERSION,
        status=status,
        account_character=character_ref.to_dict(),
        account_weapon=weapon_ref.to_dict() if weapon_ref is not None else None,
        selected_build=selected_build,
        stat_snapshot=stat_snapshot,
        warnings=tuple(_dedupe(warnings)),
        source_notes=dict(source_notes or {}),
        gcsim_readiness=GcsimReadinessNote(
            config_generation_ready=False,
            reasons=tuple(_dedupe(gcsim_reasons)),
        ),
    )


def build_character_details_data_with_build_id(
    *,
    account_character: Mapping[str, Any],
    character_stats_entry: CharacterBaseStatsEntry | None = None,
    account_weapon: Mapping[str, Any] | None = None,
    weapon_stats_entry: WeaponStatsEntry | None = None,
    build_id: int | None = None,
    db_path: str | Path = ARTIFACT_DB_PATH,
    character_readiness_status: str | None = None,
    source_notes: Mapping[str, Any] | None = None,
) -> CharacterDetailsData:
    if build_id is None:
        return build_character_details_data(
            account_character=account_character,
            character_stats_entry=character_stats_entry,
            account_weapon=account_weapon,
            weapon_stats_entry=weapon_stats_entry,
            character_readiness_status=character_readiness_status,
            source_notes=source_notes,
        )

    artifact_snapshot = load_artifact_build_snapshot_by_id(
        int(build_id),
        db_path=db_path,
    )
    return build_character_details_data(
        account_character=account_character,
        character_stats_entry=character_stats_entry,
        account_weapon=account_weapon,
        weapon_stats_entry=weapon_stats_entry,
        artifact_build_snapshot=artifact_snapshot,
        selected_build_id=int(build_id),
        selected_build_name=artifact_snapshot.build_name,
        character_readiness_status=character_readiness_status,
        source_notes={
            **dict(source_notes or {}),
            "artifact_db": Path(db_path).name,
            "artifact_db_read": True,
            "artifact_db_readonly": True,
        },
    )


def load_artifact_build_snapshot_by_id(
    build_id: int,
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> ArtifactBuildSnapshot:
    try:
        build_id = int(build_id)
    except (TypeError, ValueError):
        raise TeamCardDataError(
            ERROR_INVALID_BUILD_ID,
            f"Invalid build id: {build_id!r}.",
            details={"build_id": build_id},
        ) from None

    with closing(_connect_readonly_db(db_path)) as conn:
        preset = get_build_preset(conn, build_id)
        if preset is None:
            raise TeamCardDataError(
                ERROR_BUILD_PRESET_NOT_FOUND,
                f"Build preset id {build_id} was not found.",
                details={"build_id": build_id},
            )
        raw_summary = calculate_raw_build_summary(conn, build_id=build_id)

    return build_artifact_build_snapshot(raw_summary, build_preset=preset)


def unsupported_traveler_details_data(
    *,
    account_character: Mapping[str, Any],
    account_weapon: Mapping[str, Any] | None = None,
) -> CharacterDetailsData:
    return build_character_details_data(
        account_character=account_character,
        account_weapon=account_weapon,
        character_readiness_status=STATUS_SPECIAL_DEFERRED,
    )


def _artifact_input_for_snapshot(
    artifact_build_snapshot: ArtifactBuildSnapshot | Mapping[str, Any] | None,
    *,
    selected_build_id: int | None,
) -> ArtifactBuildSnapshot | Mapping[str, Any] | None:
    if artifact_build_snapshot is not None:
        return artifact_build_snapshot
    if selected_build_id is None:
        return None
    return None


def _selected_build_provenance(
    artifact_build_snapshot: ArtifactBuildSnapshot | Mapping[str, Any] | None,
    *,
    selected_build_id: int | None,
    selected_build_name: str,
) -> SelectedBuildProvenance:
    build_id = selected_build_id
    build_name = selected_build_name
    if isinstance(artifact_build_snapshot, ArtifactBuildSnapshot):
        if build_id is None:
            build_id = artifact_build_snapshot.build_id
        if not build_name:
            build_name = artifact_build_snapshot.build_name
    elif isinstance(artifact_build_snapshot, Mapping):
        if build_id is None:
            build_id = _optional_int(
                artifact_build_snapshot.get("build_id")
                or artifact_build_snapshot.get("id")
            )
        if not build_name:
            build_name = str(
                artifact_build_snapshot.get("build_name")
                or artifact_build_snapshot.get("name")
                or ""
            ).strip()

    return SelectedBuildProvenance(
        build_id=build_id,
        build_name=build_name,
        identity_source=(
            BUILD_IDENTITY_SOURCE_BUILD_ID
            if build_id is not None
            else BUILD_IDENTITY_SOURCE_NONE
        ),
    )


def _connect_readonly_db(path: str | Path) -> sqlite3.Connection:
    resolved = Path(path).resolve()
    uri_path = quote(resolved.as_posix(), safe="/:")
    conn = sqlite3.connect(f"file:{uri_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _optional_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str] | tuple[str, ...]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
