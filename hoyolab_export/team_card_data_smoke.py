from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

from .artifact_db import ARTIFACT_DB_PATH
from .catalog_mapping import normalize_catalog_name
from .catalog_mapping_report import (
    DEFAULT_ACCOUNT_CHARACTERS_PATH,
    DEFAULT_ACCOUNT_LANGUAGE_PATH,
    DEFAULT_ACCOUNT_WEAPONS_PATH,
    load_account_characters,
    load_account_language,
    load_account_weapons,
    sanitize_account_character,
    sanitize_account_weapon,
)
from .catalog_sanity import DEFAULT_SPECIAL_TRAVELER_NAMES
from .character_stat_snapshot_smoke import DEFAULT_ACCOUNT_CHARACTER_DETAILS_PATH
from .character_stats_catalog import (
    CHARACTER_BASE_STATS_CACHE_PATH,
    CharacterBaseStatsCatalog,
    CharacterBaseStatsEntry,
    read_character_base_stats_cache,
)
from .team_card_data import (
    CharacterDetailsData,
    TeamCardDataError,
    build_character_details_data_with_build_id,
)
from .weapon_stats_catalog import (
    WEAPON_STATS_CACHE_PATH,
    WeaponStatsCatalog,
    WeaponStatsEntry,
    read_weapon_stats_cache,
)


TEAM_CARD_DATA_SMOKE_SCHEMA_VERSION = 1

ERROR_AMBIGUOUS_CHARACTER_NAME = "ambiguous_character_name"
ERROR_CHARACTER_NOT_FOUND = "character_not_found"
ERROR_CHARACTER_SELECTOR_REQUIRED = "character_selector_required"
ERROR_CHARACTER_DETAIL_NOT_FOUND = "character_detail_not_found"
ERROR_CHARACTER_WIKI_MAPPING_MISSING = "character_wiki_mapping_missing"
ERROR_CHARACTER_STATS_ENTRY_MISSING = "character_stats_entry_missing"
ERROR_TRAVELER_SPECIAL_DEFERRED = "traveler_special_deferred"

WARNING_EQUIPPED_WEAPON_MISSING = "equipped_weapon_missing"
WARNING_WEAPON_WIKI_MAPPING_MISSING = "weapon_wiki_mapping_missing"
WARNING_WEAPON_STATS_ENTRY_MISSING = "weapon_stats_entry_missing"

_ENTRY_ID_RE = re.compile(r"/entry/(\d+)")


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
    build_id: int,
    account_characters_path: str | Path = DEFAULT_ACCOUNT_CHARACTERS_PATH,
    account_weapons_path: str | Path = DEFAULT_ACCOUNT_WEAPONS_PATH,
    account_character_details_path: str | Path = DEFAULT_ACCOUNT_CHARACTER_DETAILS_PATH,
    account_language_path: str | Path = DEFAULT_ACCOUNT_LANGUAGE_PATH,
    character_stats_catalog_path: str | Path = CHARACTER_BASE_STATS_CACHE_PATH,
    weapon_stats_catalog_path: str | Path = WEAPON_STATS_CACHE_PATH,
    artifact_db_path: str | Path = ARTIFACT_DB_PATH,
) -> dict[str, Any]:
    account_characters = load_account_characters(account_characters_path)
    account_weapons = load_account_weapons(account_weapons_path)
    account_details = _load_json_dict(account_character_details_path)
    language, language_warnings = load_account_language(account_language_path)
    character_catalog = read_character_base_stats_cache(character_stats_catalog_path)
    weapon_catalog = read_weapon_stats_cache(weapon_stats_catalog_path)

    report = build_team_card_data_smoke_report(
        account_characters=account_characters,
        account_weapons=account_weapons,
        account_details=account_details,
        language=language,
        character_catalog=character_catalog,
        weapon_catalog=weapon_catalog,
        character_id=character_id,
        character_name=character_name,
        build_id=build_id,
        artifact_db_path=artifact_db_path,
    )
    report["warnings"] = sorted(set([*report.get("warnings", []), *language_warnings]))
    report["source_notes"] = {
        "account_characters": _path_note(account_characters_path),
        "account_weapons": _path_note(account_weapons_path),
        "account_character_details": _path_note(account_character_details_path),
        "account_language": _path_note(account_language_path),
        "character_stats_catalog": _path_note(character_stats_catalog_path),
        "weapon_stats_catalog": _path_note(weapon_stats_catalog_path),
        "artifact_db": _path_note(artifact_db_path),
        "network_fetch": False,
        "detail_fetch": False,
        "db_read": True,
        "ui_access": False,
        "sanitized": True,
    }
    return report


def build_team_card_data_smoke_report(
    *,
    account_characters: list[dict[str, Any]],
    account_weapons: list[dict[str, Any]],
    account_details: dict[str, Any],
    language: str,
    character_catalog: CharacterBaseStatsCatalog | None,
    weapon_catalog: WeaponStatsCatalog | None,
    character_id: str | int | None = None,
    character_name: str | None = None,
    build_id: int,
    artifact_db_path: str | Path = ARTIFACT_DB_PATH,
) -> dict[str, Any]:
    details_data = _details_data(account_details)
    detail_rows = _detail_rows(details_data)
    avatar_wiki = _string_map(details_data.get("avatar_wiki"))
    weapon_wiki = _string_map(details_data.get("weapon_wiki"))
    account_character, detail = select_account_character_for_smoke(
        account_characters=account_characters,
        detail_rows=detail_rows,
        character_id=character_id,
        character_name=character_name,
    )

    if _is_special_traveler(account_character.get("name")):
        raise TeamCardDataSmokeError(
            ERROR_TRAVELER_SPECIAL_DEFERRED,
            "Account Traveler is special/deferred and is not valid for this ordinary smoke.",
            details={"character": _character_summary(account_character)},
        )

    character_entry_id = _entry_id_from_url(avatar_wiki.get(_text(account_character["id"])))
    if not character_entry_id:
        raise TeamCardDataSmokeError(
            ERROR_CHARACTER_WIKI_MAPPING_MISSING,
            "Selected character has no saved HoYoWiki entry mapping.",
            details={"character": _character_summary(account_character)},
        )
    character_entry = _entries_by_id(character_catalog).get(character_entry_id)
    if character_entry is None or not character_entry.rows:
        raise TeamCardDataSmokeError(
            ERROR_CHARACTER_STATS_ENTRY_MISSING,
            "Selected character has no usable local HoYoWiki stat entry.",
            details={
                "character": _character_summary(account_character),
                "entry_page_id": character_entry_id,
            },
        )

    account_weapon, weapon_entry, weapon_warnings = _selected_equipped_weapon(
        detail,
        weapon_wiki=weapon_wiki,
        weapon_entries=_weapon_entries_by_id(weapon_catalog),
        account_weapon_record=_weapons_by_equipped_character(account_weapons).get(
            _text(account_character["id"])
        ),
    )
    details_data_obj = build_character_details_data_with_build_id(
        account_character=account_character,
        character_stats_entry=character_entry,
        account_weapon=account_weapon,
        weapon_stats_entry=weapon_entry,
        build_id=int(build_id),
        db_path=artifact_db_path,
        source_notes={
            "account_data_source": "account_character_details + account JSON",
            "character_entry_mapping": "account_character_details avatar_wiki entry id",
            "weapon_entry_mapping": "account_character_details weapon_wiki entry id",
            "selected_build_identity": "build_id",
        },
    )
    data_dict = details_data_obj.to_dict()
    stat_snapshot = data_dict.get("stat_snapshot") or {}
    artifact = stat_snapshot.get("artifact") or {}
    artifact_summary = artifact.get("summary") or {}

    return {
        "schema_version": TEAM_CARD_DATA_SMOKE_SCHEMA_VERSION,
        "language": language,
        "warnings": sorted(set([*details_data_obj.warnings, *weapon_warnings])),
        "selection": {
            "character_id": _text(account_character.get("id")),
            "character_name": _text(account_character.get("name")),
            "build_id": int(build_id),
            "selection_note": (
                "Smoke may select character by name/id, but final UI should pass "
                "stable selected records and build_id internally."
            ),
        },
        "selected_character": _character_summary(account_character),
        "selected_weapon": (
            _weapon_summary(account_weapon)
            if account_weapon is not None
            else None
        ),
        "selected_build": data_dict["selected_build"],
        "character_catalog": {
            "entry_page_id": character_entry.entry_page_id,
            "name": character_entry.name,
            "lang": character_entry.lang,
        },
        "weapon_catalog": (
            {
                "entry_page_id": weapon_entry.entry_page_id,
                "name": weapon_entry.name,
                "lang": weapon_entry.lang,
            }
            if weapon_entry is not None
            else None
        ),
        "character_details_data": {
            "status": data_dict["status"],
            "has_stat_snapshot": data_dict["stat_snapshot"] is not None,
            "warnings": data_dict["warnings"],
            "gcsim_readiness": data_dict["gcsim_readiness"],
        },
        "stat_snapshot_summary": _stat_snapshot_summary(stat_snapshot),
        "artifact_contribution": {
            "present": bool(artifact_summary),
            "build_id": artifact_summary.get("build_id"),
            "build_name": artifact_summary.get("build_name"),
            "missing_positions": artifact_summary.get("missing_positions"),
            "active_set_bonuses": artifact_summary.get("active_set_bonuses"),
            "crit_value": artifact_summary.get("crit_value"),
            "proc_count": artifact_summary.get("proc_count"),
            "warnings": artifact.get("warnings", []),
        },
    }


def select_account_character_for_smoke(
    *,
    account_characters: list[dict[str, Any]],
    detail_rows: list[dict[str, Any]],
    character_id: str | int | None = None,
    character_name: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    selector_id = _text(character_id)
    selector_name = normalize_catalog_name(character_name)
    if not selector_id and not selector_name:
        raise TeamCardDataSmokeError(
            ERROR_CHARACTER_SELECTOR_REQUIRED,
            "Pass --character-id or --character-name for TeamCard data smoke.",
        )

    account_by_id = {
        _text(record.get("id")): sanitize_account_character(dict(record))
        for record in account_characters
        if _text(record.get("id"))
    }
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    seen_ids: set[str] = set()
    for detail in detail_rows:
        base = detail.get("base") if isinstance(detail, dict) else None
        if not isinstance(base, dict):
            continue
        account_character = _snapshot_account_character(
            base,
            account_by_id.get(_text(base.get("id"))),
        )
        if _matches_character(account_character, selector_id, selector_name):
            candidates.append((account_character, detail))
            seen_ids.add(_text(account_character.get("id")))

    for account_record in account_by_id.values():
        record_id = _text(account_record.get("id"))
        if record_id in seen_ids:
            continue
        if _matches_character(account_record, selector_id, selector_name):
            candidates.append((account_record, {}))

    if not candidates:
        raise TeamCardDataSmokeError(
            ERROR_CHARACTER_NOT_FOUND,
            "Selected account character was not found.",
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
                "matching_character_ids": [
                    _text(item[0].get("id"))
                    for item in candidates
                ],
            },
        )

    account_character, detail = candidates[0]
    if not detail:
        raise TeamCardDataSmokeError(
            ERROR_CHARACTER_DETAIL_NOT_FOUND,
            "Selected account character has no matching account_character_details row.",
            details={"character": _character_summary(account_character)},
        )
    return account_character, detail


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a sanitized no-network CharacterDetailsData smoke report from "
            "real local account/cache data and one selected Artifact Browser build id."
        )
    )
    parser.add_argument("--character-id", default=None)
    parser.add_argument("--character-name", default=None)
    parser.add_argument("--build-id", type=int, required=True)
    parser.add_argument("--characters", default=str(DEFAULT_ACCOUNT_CHARACTERS_PATH))
    parser.add_argument("--weapons", default=str(DEFAULT_ACCOUNT_WEAPONS_PATH))
    parser.add_argument(
        "--character-details",
        default=str(DEFAULT_ACCOUNT_CHARACTER_DETAILS_PATH),
    )
    parser.add_argument("--language-file", default=str(DEFAULT_ACCOUNT_LANGUAGE_PATH))
    parser.add_argument(
        "--character-stats-catalog",
        default=str(CHARACTER_BASE_STATS_CACHE_PATH),
    )
    parser.add_argument(
        "--weapon-stats-catalog",
        default=str(WEAPON_STATS_CACHE_PATH),
    )
    parser.add_argument("--artifact-db", default=str(ARTIFACT_DB_PATH))
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    try:
        report = build_team_card_data_smoke_report_from_paths(
            character_id=args.character_id,
            character_name=args.character_name,
            build_id=args.build_id,
            account_characters_path=args.characters,
            account_weapons_path=args.weapons,
            account_character_details_path=args.character_details,
            account_language_path=args.language_file,
            character_stats_catalog_path=args.character_stats_catalog,
            weapon_stats_catalog_path=args.weapon_stats_catalog,
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


def _selected_equipped_weapon(
    detail: Mapping[str, Any],
    *,
    weapon_wiki: Mapping[str, str],
    weapon_entries: Mapping[str, WeaponStatsEntry],
    account_weapon_record: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, WeaponStatsEntry | None, list[str]]:
    warnings: list[str] = []
    weapon = detail.get("weapon")
    if not isinstance(weapon, dict):
        warnings.append(WARNING_EQUIPPED_WEAPON_MISSING)
        return None, None, warnings

    sanitized_account_weapon = sanitize_account_weapon(dict(account_weapon_record or {}))
    account_weapon = {
        "id": _text(weapon.get("id") or sanitized_account_weapon.get("id")),
        "name": _text(weapon.get("name") or sanitized_account_weapon.get("name")),
        "level": _first_present(weapon, sanitized_account_weapon, "level"),
        "promote_level": weapon.get("promote_level"),
        "rarity": _first_present(weapon, sanitized_account_weapon, "rarity"),
        "refinement": (
            sanitized_account_weapon.get("refinement")
            if sanitized_account_weapon.get("refinement") is not None
            else weapon.get("affix_level")
        ),
        "type_name": _text(
            weapon.get("type_name")
            or sanitized_account_weapon.get("type_name")
            or sanitized_account_weapon.get("type")
        ),
    }
    weapon_entry_id = _entry_id_from_url(weapon_wiki.get(account_weapon["id"]))
    if not weapon_entry_id:
        warnings.append(WARNING_WEAPON_WIKI_MAPPING_MISSING)
        return account_weapon, None, warnings
    weapon_entry = weapon_entries.get(weapon_entry_id)
    if weapon_entry is None or not weapon_entry.rows:
        warnings.append(WARNING_WEAPON_STATS_ENTRY_MISSING)
        return account_weapon, None, warnings
    return account_weapon, weapon_entry, warnings


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


def _snapshot_account_character(
    base: Mapping[str, Any],
    account_record: Mapping[str, Any] | None,
) -> dict[str, Any]:
    account_record = sanitize_account_character(dict(account_record or {}))
    return {
        "id": _text(base.get("id") or account_record.get("id")),
        "name": _text(base.get("name") or account_record.get("name")),
        "level": _first_present(base, account_record, "level"),
        "element": _text(base.get("element") or account_record.get("element")),
        "rarity": _first_present(base, account_record, "rarity"),
        "constellation": _first_present(
            base,
            account_record,
            "actived_constellation_num",
            "constellation",
        ),
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
            or account_weapon.get("type")
            or account_weapon.get("weapon_type")
        ),
    }


def _details_data(account_details: Mapping[str, Any]) -> dict[str, Any]:
    json_payload = account_details.get("json")
    if not isinstance(json_payload, dict):
        return {}
    data = json_payload.get("data")
    return data if isinstance(data, dict) else {}


def _detail_rows(details_data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = details_data.get("list")
    if not isinstance(rows, list):
        return []
    return [item for item in rows if isinstance(item, dict)]


def _entries_by_id(
    catalog: CharacterBaseStatsCatalog | None,
) -> dict[str, CharacterBaseStatsEntry]:
    if catalog is None:
        return {}
    return {entry.entry_page_id: entry for entry in catalog.entries if entry.entry_page_id}


def _weapon_entries_by_id(
    catalog: WeaponStatsCatalog | None,
) -> dict[str, WeaponStatsEntry]:
    if catalog is None:
        return {}
    return {entry.entry_page_id: entry for entry in catalog.entries if entry.entry_page_id}


def _weapons_by_equipped_character(
    records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        equipped_by = record.get("equipped_by")
        if not isinstance(equipped_by, dict):
            continue
        character_id = _text(equipped_by.get("id"))
        if character_id:
            result[character_id] = dict(record)
    return result


def _string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        _text(key): _text(item)
        for key, item in value.items()
        if _text(key) and _text(item)
    }


def _entry_id_from_url(value: str | None) -> str:
    value = _text(value)
    if not value:
        return ""
    if value.isdigit():
        return value
    match = _ENTRY_ID_RE.search(value)
    return match.group(1) if match else ""


def _load_json_dict(path: str | Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return data if isinstance(data, dict) else {}


def _path_note(path: str | Path) -> str:
    return Path(path).name


def _is_special_traveler(name: Any) -> bool:
    normalized = normalize_catalog_name(name)
    return normalized in {
        normalize_catalog_name(value)
        for value in DEFAULT_SPECIAL_TRAVELER_NAMES
    }


def _first_present(
    primary: Mapping[str, Any],
    secondary: Mapping[str, Any],
    *keys: str,
) -> Any:
    for key in keys:
        value = primary.get(key)
        if value is not None and value != "":
            return value
        value = secondary.get(key)
        if value is not None and value != "":
            return value
    return None


def _text(value: Any) -> str:
    return str(value or "").strip()


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
