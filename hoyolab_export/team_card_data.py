from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import quote

from .account_equipment import (
    ARTIFACT_POS_BY_SLOT_KEY,
    EquipmentError,
    list_equipped_artifacts_for_character,
)
from .artifact_build_snapshot import (
    ArtifactBuildSnapshot,
    build_artifact_build_snapshot,
)
from .artifact_db import (
    ARTIFACT_DB_PATH,
    calculate_raw_build_summary,
    get_build_preset,
)
from .display_stat_effects import (
    get_weapon_passive_tooltip,
    list_artifact_set_display_stat_effects_for_active_sets,
    list_weapon_display_stat_effects,
)
from .account_stat_sheet import (
    AccountCharacterStatSheet,
    parse_account_character_stat_sheet,
)
from .catalog_sanity import STATUS_SPECIAL_DEFERRED
from .character_ascension_bonus import (
    CharacterAscensionBonusInfo,
    extract_character_ascension_bonus,
)
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
from .paths import PROJECT_ROOT
from .weapon_stats_catalog import WeaponStatsEntry


TEAM_CARD_DATA_SCHEMA_VERSION = 2

DATA_STATUS_READY = "ready"
DATA_STATUS_PARTIAL = "partial"
DATA_STATUS_UNSUPPORTED = "unsupported"
DATA_STATUS_ERROR = "error"

BUILD_IDENTITY_SOURCE_BUILD_ID = "build_id"
BUILD_IDENTITY_SOURCE_CURRENT_EQUIPMENT = "current_equipment"
BUILD_IDENTITY_SOURCE_NONE = "none"

ERROR_BUILD_PRESET_NOT_FOUND = "build_preset_not_found"
ERROR_INVALID_BUILD_ID = "invalid_build_id"

WARNING_CURRENT_EQUIPMENT_ARTIFACT_MISSING = "current_equipment_artifact_missing"
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
    account_stat_sheet: AccountCharacterStatSheet | None = None
    ascension_bonus: CharacterAscensionBonusInfo | None = None
    artifact_set_display_stat_effects: tuple[dict[str, Any], ...] = ()
    weapon_display_stat_effects: tuple[dict[str, Any], ...] = ()
    weapon_passive_reference: dict[str, Any] = field(default_factory=dict)
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
            "account_stat_sheet": (
                self.account_stat_sheet.to_dict()
                if self.account_stat_sheet is not None
                else None
            ),
            "ascension_bonus": (
                self.ascension_bonus.to_dict()
                if self.ascension_bonus is not None
                else None
            ),
            "artifact_set_display_stat_effects": [
                dict(item) for item in self.artifact_set_display_stat_effects
            ],
            "weapon_display_stat_effects": [
                dict(item) for item in self.weapon_display_stat_effects
            ],
            "weapon_passive_reference": dict(self.weapon_passive_reference),
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
    account_detail_record: Mapping[str, Any] | None = None,
    character_readiness_status: str | None = None,
    artifact_set_display_stat_effects: Iterable[Mapping[str, Any]] = (),
    weapon_display_stat_effects: Iterable[Mapping[str, Any]] = (),
    weapon_passive_reference: Mapping[str, Any] | None = None,
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
    account_character_data = _runtime_account_character_dict(
        character_ref.to_dict(),
        account_character,
    )
    account_weapon_data = (
        _runtime_account_weapon_dict(weapon_ref.to_dict(), account_weapon)
        if weapon_ref is not None and account_weapon is not None
        else None
    )
    account_stat_sheet = (
        parse_account_character_stat_sheet(account_detail_record)
        if account_detail_record is not None
        else None
    )
    ascension_bonus = (
        extract_character_ascension_bonus(character_stats_entry)
        if character_stats_entry is not None
        else None
    )
    resolved_source_notes = dict(source_notes or {})
    if account_stat_sheet is not None:
        resolved_source_notes.setdefault(
            "account_stat_sheet_role",
            "base_reference_not_team_builder_final_stats",
        )
        resolved_source_notes.setdefault(
            "display_stats_source",
            "team_builder_virtual_build",
        )
    if ascension_bonus is not None:
        resolved_source_notes.setdefault(
            "ascension_bonus_source",
            "hoyowiki_character_stats_catalog",
        )
    return CharacterDetailsData(
        schema_version=TEAM_CARD_DATA_SCHEMA_VERSION,
        status=status,
        account_character=account_character_data,
        account_weapon=account_weapon_data,
        selected_build=selected_build,
        stat_snapshot=stat_snapshot,
        account_stat_sheet=account_stat_sheet,
        ascension_bonus=ascension_bonus,
        artifact_set_display_stat_effects=tuple(
            dict(item) for item in artifact_set_display_stat_effects
        ),
        weapon_display_stat_effects=tuple(
            dict(item) for item in weapon_display_stat_effects
        ),
        weapon_passive_reference=dict(weapon_passive_reference or {}),
        warnings=tuple(_dedupe(warnings)),
        source_notes=resolved_source_notes,
        gcsim_readiness=GcsimReadinessNote(
            config_generation_ready=False,
            reasons=tuple(_dedupe(gcsim_reasons)),
        ),
    )


def _runtime_account_character_dict(
    base: Mapping[str, Any],
    source: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(base)
    for key in (
        "weapon_type",
        "weapon_type_name",
        "icon_url",
        "side_icon_url",
        "portrait_path",
        "side_icon_path",
        "base_hp",
        "base_atk",
        "base_def",
        "ascension_bonus_stat_type",
        "ascension_bonus_value",
        "talents",
        "source",
        "source_key",
    ):
        value = source.get(key)
        if value is not None and value != "":
            result[key] = value
    return result


def _runtime_account_weapon_dict(
    base: Mapping[str, Any],
    source: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(base)
    for key in (
        "weapon_type",
        "weapon_type_name",
        "type_name",
        "source",
        "source_key",
        "weapon_fingerprint",
        "known_count",
        "base_atk",
        "base_atk_raw",
        "secondary_property_type",
        "secondary_stat_value",
        "secondary_stat_value_raw",
        "description",
        "icon_url",
        "icon_path",
    ):
        value = source.get(key)
        if value is not None and value != "":
            result[key] = value
    return result


def build_character_details_data_with_build_id(
    *,
    account_character: Mapping[str, Any],
    character_stats_entry: CharacterBaseStatsEntry | None = None,
    account_weapon: Mapping[str, Any] | None = None,
    weapon_stats_entry: WeaponStatsEntry | None = None,
    build_id: int | None = None,
    db_path: str | Path = ARTIFACT_DB_PATH,
    account_detail_record: Mapping[str, Any] | None = None,
    character_readiness_status: str | None = None,
    source_notes: Mapping[str, Any] | None = None,
) -> CharacterDetailsData:
    resolved_weapon_stats_entry = weapon_stats_entry
    passive_reference = _weapon_passive_reference_from_db(
        db_path,
        account_weapon,
        source_notes=source_notes,
    )
    if build_id is None:
        return build_character_details_data(
            account_character=account_character,
            character_stats_entry=character_stats_entry,
            account_weapon=account_weapon,
            weapon_stats_entry=resolved_weapon_stats_entry,
            account_detail_record=account_detail_record,
            character_readiness_status=character_readiness_status,
            weapon_passive_reference=passive_reference,
            source_notes=source_notes,
        )

    artifact_snapshot = load_artifact_build_snapshot_by_id(
        int(build_id),
        db_path=db_path,
    )
    with closing(_connect_readonly_db(db_path)) as conn:
        artifact_set_effects = list_artifact_set_display_stat_effects_for_active_sets(
            conn,
            artifact_snapshot.to_dict().get("active_set_bonuses") or [],
            preferred_lang=_content_language_from_source_notes(source_notes),
        )
        weapon_effects = list_weapon_display_stat_effects(
            conn,
            weapon_id=(account_weapon or {}).get("id") or (account_weapon or {}).get("weapon_id"),
            refinement=(account_weapon or {}).get("refinement"),
        )
    return build_character_details_data(
        account_character=account_character,
        character_stats_entry=character_stats_entry,
        account_weapon=account_weapon,
        weapon_stats_entry=resolved_weapon_stats_entry,
        artifact_build_snapshot=artifact_snapshot,
        selected_build_id=int(build_id),
        selected_build_name=artifact_snapshot.build_name,
        account_detail_record=account_detail_record,
        character_readiness_status=character_readiness_status,
        artifact_set_display_stat_effects=artifact_set_effects,
        weapon_display_stat_effects=weapon_effects,
        weapon_passive_reference=passive_reference,
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


def load_current_equipped_artifact_snapshot(
    character_id: int | str,
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
    build_name: str = "Current Equipment",
) -> ArtifactBuildSnapshot:
    with closing(_connect_readonly_db(db_path)) as conn:
        return build_current_equipment_artifact_snapshot(
            conn,
            character_id,
            build_name=build_name,
        )


def build_current_equipment_artifact_snapshot(
    conn: sqlite3.Connection,
    character_id: int | str,
    *,
    build_name: str = "Current Equipment",
) -> ArtifactBuildSnapshot:
    try:
        records = list_equipped_artifacts_for_character(conn, character_id)
    except (EquipmentError, TypeError, ValueError):
        records = ()

    slots_by_pos: dict[int, int] = {}
    for record in records:
        pos = ARTIFACT_POS_BY_SLOT_KEY.get(record.slot_key)
        if pos is None:
            continue
        slots_by_pos[int(pos)] = int(record.artifact_id)

    existing_slots, slot_rows, missing_artifact_ids = _current_equipment_slot_rows(
        conn,
        slots_by_pos,
    )
    raw_summary = calculate_raw_build_summary(conn, slots=existing_slots)
    snapshot = build_artifact_build_snapshot(
        raw_summary,
        build_preset={
            "id": None,
            "name": build_name,
            "slots": slot_rows,
        },
    )
    if missing_artifact_ids:
        snapshot = replace(
            snapshot,
            warnings=tuple(
                _dedupe(
                    [
                        *snapshot.warnings,
                        WARNING_CURRENT_EQUIPMENT_ARTIFACT_MISSING,
                    ]
                )
            ),
        )
    return snapshot


def _current_equipment_slot_rows(
    conn: sqlite3.Connection,
    slots_by_pos: Mapping[int, int],
) -> tuple[dict[int, int], list[dict[str, Any]], list[int]]:
    if not slots_by_pos:
        return {}, [], []

    artifact_ids = sorted({int(artifact_id) for artifact_id in slots_by_pos.values()})
    placeholders = ",".join("?" for _ in artifact_ids)
    rows = conn.execute(
        f"""
        SELECT
            artifacts.id AS artifact_id,
            artifacts.name,
            artifacts.set_uid,
            artifacts.set_name,
            artifacts.pos,
            artifacts.pos_name,
            artifacts.rarity,
            artifacts.level,
            artifacts.main_property_type,
            artifacts.main_property_name,
            artifacts.main_property_value,
            COALESCE(
                set_flower_icons.local_path,
                set_icons.local_path,
                ''
            ) AS set_icon_path
        FROM artifacts
        LEFT JOIN artifact_set_piece_icons AS set_icons
            ON set_icons.set_uid = artifacts.set_uid
            AND set_icons.pos = artifacts.pos
        LEFT JOIN artifact_set_piece_icons AS set_flower_icons
            ON set_flower_icons.set_uid = artifacts.set_uid
            AND set_flower_icons.pos = 1
        WHERE artifacts.id IN ({placeholders})
        ORDER BY artifacts.pos
        """,
        artifact_ids,
    ).fetchall()
    rows_by_id = {int(row["artifact_id"]): row for row in rows}
    missing_artifact_ids = [
        artifact_id
        for artifact_id in artifact_ids
        if artifact_id not in rows_by_id
    ]
    existing_slots = {
        int(pos): int(artifact_id)
        for pos, artifact_id in slots_by_pos.items()
        if int(artifact_id) in rows_by_id
    }
    slot_rows = [
        _artifact_slot_row_to_dict(rows_by_id[artifact_id])
        for _pos, artifact_id in sorted(existing_slots.items())
    ]
    return existing_slots, slot_rows, missing_artifact_ids


def _artifact_slot_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "pos": int(row["pos"]),
        "artifact_id": int(row["artifact_id"]),
        "name": row["name"] or "",
        "set_uid": row["set_uid"] or "",
        "set_name": row["set_name"] or "",
        "set_icon_path": row["set_icon_path"] or "",
        "pos_name": row["pos_name"] or "",
        "rarity": int(row["rarity"] or 0),
        "level": int(row["level"] or 0),
        "main_property_type": row["main_property_type"],
        "main_property_name": row["main_property_name"] or "",
        "main_property_value": row["main_property_value"] or "",
    }


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


def _weapon_passive_reference_from_db(
    db_path: str | Path,
    account_weapon: Mapping[str, Any] | None,
    *,
    source_notes: Mapping[str, Any] | None,
) -> dict[str, Any]:
    weapon = dict(account_weapon or {})
    weapon_id = _text(weapon.get("id") or weapon.get("weapon_id"))
    if not weapon_id:
        return {}
    language = _content_language_from_source_notes(source_notes)
    try:
        with closing(_connect_readonly_db(db_path)) as conn:
            return get_weapon_passive_tooltip(
                conn,
                weapon_id=weapon_id,
                language=language,
            )
    except sqlite3.Error:
        return {}


def _content_language_from_source_notes(
    source_notes: Mapping[str, Any] | None,
) -> str:
    return _text(
        _mapping(source_notes).get("content_language")
        or _mapping(source_notes).get("account_content_language")
    ) or _account_content_language()


def _account_content_language() -> str:
    path = PROJECT_ROOT / "data" / "hoyolab" / "account_language.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return _text(data.get("contentLanguage")) if isinstance(data, dict) else ""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


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
