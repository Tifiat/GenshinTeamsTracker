from __future__ import annotations

import argparse
import json
import sys
from contextlib import closing
from pathlib import Path
from typing import Any, Mapping

from .artifact_db import ARTIFACT_DB_PATH, connect_db
from .account_storage import (
    AccountCharacterRuntimeRecord,
    AccountWeaponObservedStack,
    list_account_characters,
    list_account_weapon_observed_stacks,
)
from .catalog_mapping import normalize_catalog_name
from .catalog_sanity import DEFAULT_SPECIAL_TRAVELER_NAMES
from .team_card_data import (
    TeamCardDataError,
    build_character_details_data_with_build_id,
)


TEAM_CARD_DATA_SMOKE_SCHEMA_VERSION = 2

ERROR_AMBIGUOUS_CHARACTER_NAME = "ambiguous_character_name"
ERROR_CHARACTER_NOT_FOUND = "character_not_found"
ERROR_CHARACTER_SELECTOR_REQUIRED = "character_selector_required"
ERROR_TRAVELER_SPECIAL_DEFERRED = "traveler_special_deferred"

WARNING_OBSERVED_WEAPON_STACK_MISSING = "observed_weapon_stack_missing_for_character"
WARNING_OBSERVED_WEAPON_STACK_EXPLICIT_SELECTOR = (
    "observed_weapon_stack_selected_by_explicit_smoke_selector"
)
WARNING_OBSERVED_WEAPON_STACK_TYPE_FALLBACK = (
    "observed_weapon_stack_selected_by_weapon_type_for_smoke_only"
)


class TeamCardDataSmokeError(RuntimeError):
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


def build_team_card_data_smoke_report_from_paths(
    *,
    character_id: str | int | None = None,
    character_name: str | None = None,
    weapon_fingerprint: str | None = None,
    weapon_id: str | int | None = None,
    weapon_level: int | None = None,
    weapon_refinement: int | None = None,
    weapon_promote_level: int | None = None,
    build_id: int,
    account_db_path: str | Path = ARTIFACT_DB_PATH,
    artifact_db_path: str | Path = ARTIFACT_DB_PATH,
) -> dict[str, Any]:
    """Build the smoke report from runtime SQLite account storage.

    The historical function name is kept for prototype callers, but it no
    longer reads account HoYoLAB JSON files. Raw JSON remains an import/sync
    source-cache input, not the runtime smoke source.
    """

    with closing(connect_db(account_db_path)) as conn:
        account_characters = [record.to_dict() for record in list_account_characters(conn)]
        weapon_stacks = [
            record.to_dict()
            for record in list_account_weapon_observed_stacks(conn)
        ]

    return build_team_card_data_smoke_report(
        account_characters=account_characters,
        weapon_stacks=weapon_stacks,
        character_id=character_id,
        character_name=character_name,
        weapon_fingerprint=weapon_fingerprint,
        weapon_id=weapon_id,
        weapon_level=weapon_level,
        weapon_refinement=weapon_refinement,
        weapon_promote_level=weapon_promote_level,
        build_id=build_id,
        artifact_db_path=artifact_db_path,
        account_db_path=account_db_path,
    )


def build_team_card_data_smoke_report(
    *,
    account_characters: list[Mapping[str, Any] | AccountCharacterRuntimeRecord],
    weapon_stacks: list[Mapping[str, Any] | AccountWeaponObservedStack],
    character_id: str | int | None = None,
    character_name: str | None = None,
    weapon_fingerprint: str | None = None,
    weapon_id: str | int | None = None,
    weapon_level: int | None = None,
    weapon_refinement: int | None = None,
    weapon_promote_level: int | None = None,
    build_id: int,
    artifact_db_path: str | Path = ARTIFACT_DB_PATH,
    account_db_path: str | Path = ARTIFACT_DB_PATH,
) -> dict[str, Any]:
    account_character = select_account_character_for_smoke(
        account_characters=account_characters,
        character_id=character_id,
        character_name=character_name,
    )

    if _is_special_traveler(account_character.get("name")):
        raise TeamCardDataSmokeError(
            ERROR_TRAVELER_SPECIAL_DEFERRED,
            "Account Traveler is special/deferred and is not valid for this ordinary smoke.",
            details={"character": _character_summary(account_character)},
        )

    account_weapon, weapon_warnings = select_observed_weapon_stack_for_smoke(
        weapon_stacks=weapon_stacks,
        weapon_fingerprint=weapon_fingerprint,
        weapon_id=weapon_id,
        weapon_level=weapon_level,
        weapon_refinement=weapon_refinement,
        weapon_promote_level=weapon_promote_level,
        weapon_type=account_character.get("weapon_type"),
    )
    selected_weapon_source = _selected_weapon_source_note(
        account_weapon,
        weapon_warnings,
    )
    details_data_obj = build_character_details_data_with_build_id(
        account_character=account_character,
        account_weapon=account_weapon,
        build_id=int(build_id),
        db_path=artifact_db_path,
        source_notes={
            "account_data_source": "account_sqlite_runtime",
            "account_db": Path(account_db_path).name,
            "selected_build_identity": "build_id",
            "selected_weapon_source": selected_weapon_source,
            "current_equipped_relation_canonical": False,
            "raw_hoyolab_json_read": False,
        },
    )
    data_dict = details_data_obj.to_dict()
    stat_snapshot = data_dict.get("stat_snapshot") or {}
    artifact = stat_snapshot.get("artifact") or {}
    artifact_summary = artifact.get("summary") or {}
    warnings = sorted(set([*data_dict.get("warnings", []), *weapon_warnings]))

    return {
        "schema_version": TEAM_CARD_DATA_SMOKE_SCHEMA_VERSION,
        "language": "account_sqlite_runtime",
        "warnings": warnings,
        "selection": {
            "character_id": _text(account_character.get("id")),
            "character_name": _text(account_character.get("name")),
            "build_id": int(build_id),
            "selection_note": (
                "Smoke may select character by name/id, but final UI should pass "
                "stable selected records, selected weapon stack, and build_id internally."
            ),
        },
        "selected_character": _character_summary(account_character),
        "selected_weapon": _weapon_summary(account_weapon) if account_weapon else None,
        "selected_build": data_dict["selected_build"],
        "character_catalog": None,
        "weapon_catalog": None,
        "character_details_data": {
            "status": data_dict["status"],
            "has_stat_snapshot": data_dict["stat_snapshot"] is not None,
            "has_account_stat_sheet": data_dict.get("account_stat_sheet") is not None,
            "warnings": data_dict["warnings"],
            "gcsim_readiness": data_dict["gcsim_readiness"],
        },
        "account_stat_sheet": data_dict.get("account_stat_sheet"),
        "ascension_bonus": _ascension_bonus_summary(account_character),
        "stat_snapshot_summary": _stat_snapshot_summary(stat_snapshot),
        "artifact_contribution": {
            "present": bool(artifact_summary),
            "build_id": artifact_summary.get("build_id"),
            "build_name": artifact_summary.get("build_name"),
            "missing_positions": artifact_summary.get("missing_positions"),
            "active_set_bonuses": artifact_summary.get("active_set_bonuses"),
            "stat_totals": artifact_summary.get("stat_totals", []),
            "crit_value": artifact_summary.get("crit_value"),
            "proc_count": artifact_summary.get("proc_count"),
            "warnings": artifact.get("warnings", []),
        },
        "character_details_full": data_dict,
        "source_notes": {
            "account_runtime_source": "sqlite_account_storage",
            "raw_hoyolab_json_read": False,
            "account_db": _path_note(account_db_path),
            "artifact_db": _path_note(artifact_db_path),
        },
    }


def select_account_character_for_smoke(
    *,
    account_characters: list[Mapping[str, Any] | AccountCharacterRuntimeRecord],
    character_id: str | int | None = None,
    character_name: str | None = None,
) -> dict[str, Any]:
    selector_id = _text(character_id)
    selector_name = normalize_catalog_name(character_name)
    if not selector_id and not selector_name:
        raise TeamCardDataSmokeError(
            ERROR_CHARACTER_SELECTOR_REQUIRED,
            "Pass --character-id or --character-name for TeamCard data smoke.",
        )

    candidates = [
        _account_character_dict(record)
        for record in account_characters
        if _matches_character(_account_character_dict(record), selector_id, selector_name)
    ]
    if not candidates:
        raise TeamCardDataSmokeError(
            ERROR_CHARACTER_NOT_FOUND,
            "Selected account character was not found in SQLite account storage.",
            details={
                "character_id": selector_id or None,
                "character_name": character_name or None,
            },
        )
    if len(candidates) > 1 and selector_name:
        raise TeamCardDataSmokeError(
            ERROR_AMBIGUOUS_CHARACTER_NAME,
            "Character name matched multiple account records.",
            details={
                "character_name": character_name,
                "matching_character_ids": [_text(item.get("id")) for item in candidates],
            },
        )
    return candidates[0]


def select_observed_weapon_stack_for_smoke(
    *,
    weapon_stacks: list[Mapping[str, Any] | AccountWeaponObservedStack],
    weapon_fingerprint: str | None = None,
    weapon_id: str | int | None = None,
    weapon_level: int | None = None,
    weapon_refinement: int | None = None,
    weapon_promote_level: int | None = None,
    weapon_type: str | int | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    stacks = [_weapon_stack_dict(stack) for stack in weapon_stacks]
    selector_fingerprint = _text(weapon_fingerprint)
    if selector_fingerprint:
        for data in stacks:
            if _text(data.get("weapon_fingerprint")) == selector_fingerprint:
                return _weapon_ref_for_team_builder(data), [
                    WARNING_OBSERVED_WEAPON_STACK_EXPLICIT_SELECTOR
                ]
        return None, [WARNING_OBSERVED_WEAPON_STACK_MISSING]

    explicit_filters = {
        "weapon_id": _optional_int(weapon_id),
        "level": _optional_int(weapon_level),
        "refinement": _optional_int(weapon_refinement),
        "promote_level": _optional_int(weapon_promote_level),
    }
    explicit_filters = {
        key: value for key, value in explicit_filters.items() if value is not None
    }
    if explicit_filters:
        candidates = [
            data
            for data in stacks
            if all(
                _optional_int(_weapon_filter_value(data, key)) == value
                for key, value in explicit_filters.items()
            )
        ]
        if candidates:
            return _weapon_ref_for_team_builder(_best_observed_weapon_stack(candidates)), [
                WARNING_OBSERVED_WEAPON_STACK_EXPLICIT_SELECTOR
            ]
        return None, [WARNING_OBSERVED_WEAPON_STACK_MISSING]

    character_weapon_type = _optional_int(weapon_type)
    if character_weapon_type is None:
        return None, [WARNING_OBSERVED_WEAPON_STACK_MISSING]

    candidates = [
        data
        for data in stacks
        if _optional_int(_weapon_filter_value(data, "weapon_type")) == character_weapon_type
    ]
    if candidates:
        return _weapon_ref_for_team_builder(_best_observed_weapon_stack(candidates)), [
            WARNING_OBSERVED_WEAPON_STACK_TYPE_FALLBACK
        ]
    return None, [WARNING_OBSERVED_WEAPON_STACK_MISSING]


def _best_observed_weapon_stack(
    stacks: list[Mapping[str, Any]],
) -> dict[str, Any]:
    return dict(
        sorted(
            stacks,
            key=lambda data: (
                -(_optional_int(data.get("rarity")) or 0),
                -(_optional_int(data.get("level")) or 0),
                -(_optional_int(data.get("refinement")) or 0),
                -(_optional_int(data.get("promote_level")) or 0),
                _text(data.get("name")).casefold(),
                _text(data.get("weapon_fingerprint")),
            ),
        )[0]
    )


def _weapon_filter_value(data: Mapping[str, Any], key: str) -> Any:
    if key == "weapon_id":
        return data.get("weapon_id") or data.get("id")
    if key == "weapon_type":
        return data.get("weapon_type") or data.get("type")
    return data.get(key)


def _selected_weapon_source_note(
    account_weapon: Mapping[str, Any] | None,
    warnings: list[str],
) -> str:
    if account_weapon is None:
        return "none"
    if WARNING_OBSERVED_WEAPON_STACK_EXPLICIT_SELECTOR in warnings:
        return "observed_stack_explicit_selector"
    if WARNING_OBSERVED_WEAPON_STACK_TYPE_FALLBACK in warnings:
        return "observed_stack_weapon_type_fallback_for_smoke_only"
    return "observed_stack_unknown_smoke_selector"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a sanitized no-network CharacterDetailsData smoke report from "
            "runtime SQLite account storage and one selected Artifact Browser build id."
        )
    )
    parser.add_argument("--character-id", default=None)
    parser.add_argument("--character-name", default=None)
    parser.add_argument("--weapon-fingerprint", default=None)
    parser.add_argument("--weapon-id", default=None)
    parser.add_argument("--weapon-level", type=int, default=None)
    parser.add_argument("--weapon-refinement", type=int, default=None)
    parser.add_argument("--weapon-promote-level", type=int, default=None)
    parser.add_argument("--build-id", type=int, required=True)
    parser.add_argument("--account-db", default=str(ARTIFACT_DB_PATH))
    parser.add_argument("--artifact-db", default=str(ARTIFACT_DB_PATH))
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    try:
        report = build_team_card_data_smoke_report_from_paths(
            character_id=args.character_id,
            character_name=args.character_name,
            weapon_fingerprint=args.weapon_fingerprint,
            weapon_id=args.weapon_id,
            weapon_level=args.weapon_level,
            weapon_refinement=args.weapon_refinement,
            weapon_promote_level=args.weapon_promote_level,
            build_id=args.build_id,
            account_db_path=args.account_db,
            artifact_db_path=args.artifact_db,
        )
    except TeamCardDataSmokeError as exc:
        _write_json(exc.to_dict(), output=args.output, stderr=True)
        return 1
    except TeamCardDataError as exc:
        _write_json(exc.to_dict(), output=args.output, stderr=True)
        return 1
    except Exception as exc:
        _write_json(
            {
                "error": "team_card_data_smoke_failed",
                "message": str(exc),
            },
            output=args.output,
            stderr=True,
        )
        return 1

    _write_json(report, output=args.output)
    return 0


def _account_character_dict(
    record: Mapping[str, Any] | AccountCharacterRuntimeRecord,
) -> dict[str, Any]:
    if isinstance(record, AccountCharacterRuntimeRecord):
        data = record.to_team_builder_character_ref()
    else:
        data = dict(record)
    if "id" not in data and "character_id" in data:
        data["id"] = data.get("character_id")
    if "constellation" not in data and "actived_constellation_num" in data:
        data["constellation"] = data.get("actived_constellation_num")
    return data


def _weapon_stack_dict(
    record: Mapping[str, Any] | AccountWeaponObservedStack,
) -> dict[str, Any]:
    if isinstance(record, AccountWeaponObservedStack):
        return record.to_dict()
    return dict(record)


def _weapon_ref_for_team_builder(stack: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _text(stack.get("weapon_id") or stack.get("id")),
        "name": _text(stack.get("name")),
        "level": stack.get("level"),
        "promote_level": stack.get("promote_level"),
        "rarity": stack.get("rarity"),
        "refinement": stack.get("refinement"),
        "weapon_type": stack.get("weapon_type"),
        "type_name": _text(stack.get("type_name") or stack.get("weapon_type_name")),
        "weapon_type_name": _text(stack.get("weapon_type_name") or stack.get("type_name")),
        "source_key": _text(stack.get("weapon_fingerprint")),
        "source": "account_sqlite_observed_weapon_stack",
        "known_count": stack.get("known_count"),
        "base_atk": stack.get("base_atk"),
        "base_atk_raw": stack.get("base_atk_raw"),
        "secondary_property_type": stack.get("secondary_property_type"),
        "secondary_stat_value": stack.get("secondary_stat_value"),
        "secondary_stat_value_raw": stack.get("secondary_stat_value_raw"),
        "description": _text(stack.get("description")),
        "icon_url": _text(stack.get("icon_url")),
        "icon_path": _text(stack.get("icon_path")),
        "warnings": list(stack.get("warnings") or []),
    }


def _matches_character(
    account_character: Mapping[str, Any],
    selector_id: str,
    selector_name: str,
) -> bool:
    if selector_id:
        return _text(account_character.get("id")) == selector_id
    return normalize_catalog_name(account_character.get("name")) == selector_name


def _character_summary(account_character: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _text(account_character.get("id")),
        "name": _text(account_character.get("name")),
        "level": account_character.get("level"),
        "constellation": account_character.get("constellation"),
        "element": _text(account_character.get("element")),
        "rarity": account_character.get("rarity"),
        "portrait_path": _text(account_character.get("portrait_path")),
        "side_icon_path": _text(account_character.get("side_icon_path")),
        "talent_count": len(account_character.get("talents") or []),
    }


def _weapon_summary(account_weapon: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _text(account_weapon.get("id")),
        "name": _text(account_weapon.get("name")),
        "level": account_weapon.get("level"),
        "promote_level": account_weapon.get("promote_level"),
        "rarity": account_weapon.get("rarity"),
        "refinement": account_weapon.get("refinement"),
        "type_name": _text(
            account_weapon.get("type_name")
            or account_weapon.get("weapon_type_name")
            or account_weapon.get("type")
        ),
        "base_atk": account_weapon.get("base_atk"),
        "secondary_property_type": account_weapon.get("secondary_property_type"),
        "secondary_stat_value": account_weapon.get("secondary_stat_value"),
        "known_count": account_weapon.get("known_count"),
        "icon_path": _text(account_weapon.get("icon_path")),
    }


def _ascension_bonus_summary(account_character: Mapping[str, Any]) -> dict[str, Any] | None:
    stat_type = _text(account_character.get("ascension_bonus_stat_type"))
    value = account_character.get("ascension_bonus_value")
    if not stat_type or value in (None, ""):
        return None
    return {
        "stat_type": stat_type,
        "selected_value": value,
        "source": "account_sqlite_character_reference",
    }


def _stat_snapshot_summary(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    character_base = snapshot.get("character_base") or {}
    weapon = snapshot.get("weapon") or {}
    return {
        "status": snapshot.get("status"),
        "warnings": snapshot.get("warnings", []),
        "character_base": {
            "selected_level_key": character_base.get("selected_level_key", ""),
            "base_hp": character_base.get("base_hp"),
            "base_atk": character_base.get("base_atk"),
            "base_def": character_base.get("base_def"),
            "ascension_bonus_stat_type": character_base.get(
                "ascension_bonus_stat_type",
                "",
            ),
            "ascension_bonus": character_base.get("ascension_bonus"),
            "warnings": character_base.get("warnings", []),
        },
        "weapon": {
            "selected_level_key": weapon.get("selected_level_key", ""),
            "base_atk": weapon.get("base_atk"),
            "secondary_stat_type": weapon.get("secondary_stat_type", ""),
            "secondary_stat_value": weapon.get("secondary_stat_value"),
            "warnings": weapon.get("warnings", []),
        },
    }


def _is_special_traveler(name: Any) -> bool:
    normalized = normalize_catalog_name(name)
    return normalized in {
        normalize_catalog_name(value)
        for value in DEFAULT_SPECIAL_TRAVELER_NAMES
    }


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _path_note(path: str | Path) -> str:
    return Path(path).name


def _text(value: Any) -> str:
    return str(value or "").strip()


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _write_json(
    data: dict[str, Any],
    *,
    output: str | None = None,
    stderr: bool = False,
) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
        return

    stream = sys.stderr if stderr else sys.stdout
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass
    stream.write(text)
    stream.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
