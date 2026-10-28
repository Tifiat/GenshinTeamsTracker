from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

from .catalog_mapping import normalize_catalog_name
from .catalog_sanity import DEFAULT_SPECIAL_TRAVELER_NAMES
from .character_stat_snapshot import (
    CharacterStatSnapshot,
    WARNING_ARTIFACT_SUMMARY_MISSING,
    WARNING_ASCENSION_PHASE_UNKNOWN,
    WARNING_CHARACTER_ASCENSION_PHASE_ASSUMED,
    WARNING_FINAL_TOTALS_NOT_COMPUTED,
    WARNING_TRAVELER_SPECIAL_DEFERRED,
    build_character_stat_snapshot,
)
from .character_stats_catalog import (
    CHARACTER_BASE_STATS_CACHE_PATH,
    CharacterBaseStatsCatalog,
    CharacterBaseStatsEntry,
    read_character_base_stats_cache,
)
from .catalog_mapping_report import (
    DEFAULT_ACCOUNT_CHARACTERS_PATH,
    DEFAULT_ACCOUNT_LANGUAGE_PATH,
    DEFAULT_ACCOUNT_WEAPONS_PATH,
    load_account_language,
    sanitize_account_character,
    sanitize_account_weapon,
)
from .paths import HOYOLAB_DATA_DIR
from .weapon_stats_catalog import (
    WEAPON_STATS_CACHE_PATH,
    WeaponStatsCatalog,
    WeaponStatsEntry,
    read_weapon_stats_cache,
)


DEFAULT_ACCOUNT_CHARACTER_DETAILS_PATH = (
    HOYOLAB_DATA_DIR / "account_character_details.json"
)

SNAPSHOT_SMOKE_SCHEMA_VERSION = 1

WARNING_ACCOUNT_DETAILS_MISSING = "account_details_missing"
WARNING_CHARACTER_DETAIL_MISSING = "character_detail_missing"
WARNING_CHARACTER_WIKI_MAPPING_MISSING = "character_wiki_mapping_missing"
WARNING_CHARACTER_STATS_ENTRY_MISSING = "character_stats_entry_missing"
WARNING_WEAPON_WIKI_MAPPING_MISSING = "weapon_wiki_mapping_missing"
WARNING_WEAPON_STATS_ENTRY_MISSING = "weapon_stats_entry_missing"
WARNING_EQUIPPED_WEAPON_MISSING = "equipped_weapon_missing"

_ENTRY_ID_RE = re.compile(r"/entry/(\d+)")
_ASCENSION_BREAKPOINT_LEVELS = {20, 40, 50, 60, 70, 80}
_PROMOTE_FIELD_MARKERS = ("promot", "ascen", "phase", "max")


def build_character_stat_snapshot_smoke_report_from_paths(
    *,
    account_characters_path: str | Path = DEFAULT_ACCOUNT_CHARACTERS_PATH,
    account_weapons_path: str | Path = DEFAULT_ACCOUNT_WEAPONS_PATH,
    account_character_details_path: str | Path = DEFAULT_ACCOUNT_CHARACTER_DETAILS_PATH,
    account_language_path: str | Path = DEFAULT_ACCOUNT_LANGUAGE_PATH,
    character_stats_catalog_path: str | Path = CHARACTER_BASE_STATS_CACHE_PATH,
    weapon_stats_catalog_path: str | Path = WEAPON_STATS_CACHE_PATH,
    limit: int = 2,
    artifact_summary: Any | None = None,
) -> dict[str, Any]:
    account_characters = _load_json_list(account_characters_path)
    account_weapons = _load_json_list(account_weapons_path)
    account_details = _load_json_dict(account_character_details_path)
    language, language_warnings = load_account_language(account_language_path)

    character_catalog = read_character_base_stats_cache(character_stats_catalog_path)
    weapon_catalog = read_weapon_stats_cache(weapon_stats_catalog_path)

    report = build_character_stat_snapshot_smoke_report(
        account_characters=account_characters,
        account_weapons=account_weapons,
        account_details=account_details,
        character_catalog=character_catalog,
        weapon_catalog=weapon_catalog,
        language=language,
        limit=limit,
        artifact_summary=artifact_summary,
    )
    report["warnings"] = sorted(
        set([*report.get("warnings", []), *language_warnings])
    )
    report["source_notes"] = {
        "account_characters": _path_note(account_characters_path),
        "account_weapons": _path_note(account_weapons_path),
        "account_character_details": _path_note(account_character_details_path),
        "account_language": _path_note(account_language_path),
        "character_stats_catalog": _path_note(character_stats_catalog_path),
        "weapon_stats_catalog": _path_note(weapon_stats_catalog_path),
        "network_fetch": False,
        "detail_fetch": False,
        "db_read": False,
        "sanitized": True,
    }
    return report


def build_character_stat_snapshot_smoke_report(
    *,
    account_characters: list[dict[str, Any]],
    account_weapons: list[dict[str, Any]],
    account_details: dict[str, Any],
    character_catalog: CharacterBaseStatsCatalog | None,
    weapon_catalog: WeaponStatsCatalog | None,
    language: str,
    limit: int = 2,
    artifact_summary: Any | None = None,
) -> dict[str, Any]:
    details_data = _details_data(account_details)
    detail_rows = _detail_rows(details_data)
    avatar_wiki = _string_map(details_data.get("avatar_wiki"))
    weapon_wiki = _string_map(details_data.get("weapon_wiki"))

    character_entries = _character_entries_by_id(character_catalog)
    weapon_entries = _weapon_entries_by_id(weapon_catalog)
    account_characters_by_id = _records_by_id(account_characters)
    account_weapons_by_equipped_character = _weapons_by_equipped_character(account_weapons)

    promote_inspection = inspect_account_promote_phase_fields(
        account_characters=account_characters,
        account_weapons=account_weapons,
        account_details=account_details,
    )

    warnings: list[str] = []
    if not detail_rows:
        warnings.append(WARNING_ACCOUNT_DETAILS_MISSING)

    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    special_deferred = 0

    for index, detail in enumerate(detail_rows):
        base = detail.get("base") if isinstance(detail, dict) else None
        if not isinstance(base, dict):
            skipped.append(
                _skip_example(index=index, warning=WARNING_CHARACTER_DETAIL_MISSING)
            )
            continue

        account_character = _snapshot_account_character(
            base,
            account_characters_by_id.get(_text(base.get("id"))),
        )
        if _is_special_traveler(account_character.get("name")):
            special_deferred += 1
            skipped.append(
                _skip_example(
                    index=index,
                    account_character=account_character,
                    warning=WARNING_TRAVELER_SPECIAL_DEFERRED,
                )
            )
            continue

        character_entry_id = _entry_id_from_url(avatar_wiki.get(account_character["id"]))
        character_entry = character_entries.get(character_entry_id)
        if not character_entry_id:
            skipped.append(
                _skip_example(
                    index=index,
                    account_character=account_character,
                    warning=WARNING_CHARACTER_WIKI_MAPPING_MISSING,
                )
            )
            continue
        if character_entry is None or not character_entry.rows:
            skipped.append(
                _skip_example(
                    index=index,
                    account_character=account_character,
                    catalog_entry_id=character_entry_id,
                    warning=WARNING_CHARACTER_STATS_ENTRY_MISSING,
                )
            )
            continue

        account_weapon, weapon_entry, weapon_warnings = _snapshot_weapon_inputs(
            detail,
            weapon_wiki=weapon_wiki,
            weapon_entries=weapon_entries,
            account_weapon_record=account_weapons_by_equipped_character.get(
                account_character["id"]
            ),
        )
        snapshot = build_character_stat_snapshot(
            account_character=account_character,
            character_stats_entry=character_entry,
            account_weapon=account_weapon,
            weapon_stats_entry=weapon_entry,
            artifact_summary=artifact_summary,
        )
        candidates.append(
            {
                "index": index,
                "is_breakpoint_level": account_character.get("level")
                in _ASCENSION_BREAKPOINT_LEVELS,
                "snapshot": snapshot,
                "character_entry": character_entry,
                "weapon_entry": weapon_entry,
                "extra_warnings": tuple(weapon_warnings),
            }
        )

    candidates.sort(key=lambda item: (not item["is_breakpoint_level"], item["index"]))
    selected = candidates[: max(0, int(limit))]
    snapshots = [_snapshot_report_item(item) for item in selected]

    return {
        "schema_version": SNAPSHOT_SMOKE_SCHEMA_VERSION,
        "language": language,
        "warnings": sorted(set(warnings)),
        "promote_phase_inspection": promote_inspection,
        "selection": {
            "requested_limit": max(0, int(limit)),
            "detail_rows": len(detail_rows),
            "candidate_snapshots": len(candidates),
            "selected_snapshots": len(snapshots),
            "special_deferred": special_deferred,
            "selection_note": (
                "Breakpoint-level ordinary characters are preferred when present, "
                "so the MVP character ascension assumption can be observed."
            ),
            "skipped_examples": skipped[:5],
        },
        "snapshots": snapshots,
    }


def inspect_account_promote_phase_fields(
    *,
    account_characters: list[dict[str, Any]],
    account_weapons: list[dict[str, Any]],
    account_details: dict[str, Any],
) -> dict[str, Any]:
    details_data = _details_data(account_details)
    detail_rows = _detail_rows(details_data)
    detail_bases = [
        item.get("base")
        for item in detail_rows
        if isinstance(item, dict) and isinstance(item.get("base"), dict)
    ]
    detail_weapons = [
        item.get("weapon")
        for item in detail_rows
        if isinstance(item, dict) and isinstance(item.get("weapon"), dict)
    ]

    account_character_fields = _promote_like_fields(account_characters)
    account_weapon_fields = _promote_like_fields(account_weapons)
    detail_base_fields = _promote_like_fields(detail_bases)
    detail_weapon_fields = _promote_like_fields(detail_weapons)

    return {
        "account_character_records": len(account_characters),
        "account_character_promote_like_fields": account_character_fields,
        "account_character_records_with_promote_like_fields": _count_with_promote_fields(
            account_characters
        ),
        "account_weapon_records": len(account_weapons),
        "account_weapon_promote_like_fields": account_weapon_fields,
        "account_weapon_records_with_promote_like_fields": _count_with_promote_fields(
            account_weapons
        ),
        "account_detail_rows": len(detail_rows),
        "detail_base_promote_like_fields": detail_base_fields,
        "detail_base_records_with_promote_like_fields": _count_with_promote_fields(
            detail_bases
        ),
        "detail_weapon_promote_like_fields": detail_weapon_fields,
        "detail_weapon_records_with_promote_like_fields": _count_with_promote_fields(
            detail_weapons
        ),
        "character_ascension_phase_source": (
            "not_found: account character data and detail base records expose level "
            "but no promote/ascension phase field"
        ),
        "weapon_ascension_phase_source": (
            "account_character_details.json -> json.data.list[].weapon.promote_level"
            if "promote_level" in detail_weapon_fields
            else "not_found"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build sanitized CharacterStatSnapshot smoke examples from local "
            "allowlisted HoYoLAB account JSON and HoYoWiki stats caches."
        )
    )
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
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    try:
        report = build_character_stat_snapshot_smoke_report_from_paths(
            account_characters_path=args.characters,
            account_weapons_path=args.weapons,
            account_character_details_path=args.character_details,
            account_language_path=args.language_file,
            character_stats_catalog_path=args.character_stats_catalog,
            weapon_stats_catalog_path=args.weapon_stats_catalog,
            limit=args.limit,
        )
    except Exception as exc:
        print(f"character stat snapshot smoke failed: {exc}", file=sys.stderr)
        return 1

    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    else:
        _write_stdout(text)
    return 0


def _snapshot_report_item(item: dict[str, Any]) -> dict[str, Any]:
    snapshot: CharacterStatSnapshot = item["snapshot"]
    character_entry: CharacterBaseStatsEntry = item["character_entry"]
    weapon_entry: WeaponStatsEntry | None = item["weapon_entry"]
    snapshot_dict = snapshot.to_dict()
    character_base = snapshot_dict.get("character_base") or {}
    weapon = snapshot_dict.get("weapon") or {}
    extra_warnings = list(item.get("extra_warnings") or [])

    return {
        "status": snapshot.status,
        "account_character": snapshot_dict["account_character"],
        "character_catalog": {
            "entry_page_id": character_entry.entry_page_id,
            "name": character_entry.name,
            "lang": character_entry.lang,
        },
        "character_base": {
            "selected_level_key": character_base.get("selected_level_key", ""),
            "base_hp": character_base.get("base_hp"),
            "base_atk": character_base.get("base_atk"),
            "base_def": character_base.get("base_def"),
            "ascension_bonus_stat_type": character_base.get(
                "ascension_bonus_stat_type", ""
            ),
            "ascension_bonus": character_base.get("ascension_bonus"),
            "warnings": character_base.get("warnings", []),
        },
        "account_weapon": snapshot_dict.get("account_weapon"),
        "weapon_catalog": (
            {
                "entry_page_id": weapon_entry.entry_page_id,
                "name": weapon_entry.name,
                "lang": weapon_entry.lang,
            }
            if weapon_entry is not None
            else None
        ),
        "weapon": {
            "selected_level_key": weapon.get("selected_level_key", ""),
            "base_atk": weapon.get("base_atk"),
            "secondary_stat_type": weapon.get("secondary_stat_type", ""),
            "secondary_stat_value": weapon.get("secondary_stat_value"),
            "warnings": weapon.get("warnings", []),
        },
        "artifact": snapshot_dict.get("artifact"),
        "warnings": sorted(set([*snapshot.warnings, *extra_warnings])),
        "observations": {
            "ascension_phase_unknown": WARNING_ASCENSION_PHASE_UNKNOWN
            in snapshot.warnings,
            "character_ascension_phase_assumed": (
                WARNING_CHARACTER_ASCENSION_PHASE_ASSUMED in snapshot.warnings
            ),
            "artifact_summary_missing": WARNING_ARTIFACT_SUMMARY_MISSING
            in snapshot.warnings,
            "final_totals_not_computed": WARNING_FINAL_TOTALS_NOT_COMPUTED
            in snapshot.warnings,
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


def _snapshot_weapon_inputs(
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


def _character_entries_by_id(
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


def _records_by_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        record_id = _text(record.get("id"))
        if record_id:
            result[record_id] = dict(record)
    return result


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


def _promote_like_fields(records: list[Any]) -> list[str]:
    fields: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        for key in record.keys():
            lowered = str(key).lower()
            if any(marker in lowered for marker in _PROMOTE_FIELD_MARKERS):
                fields.add(str(key))
    return sorted(fields)


def _count_with_promote_fields(records: list[Any]) -> int:
    count = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        if _promote_like_fields([record]):
            count += 1
    return count


def _skip_example(
    *,
    index: int,
    warning: str,
    account_character: Mapping[str, Any] | None = None,
    catalog_entry_id: str = "",
) -> dict[str, Any]:
    item = {
        "detail_index": index,
        "warning": warning,
    }
    if account_character is not None:
        item["account_character"] = {
            "id": account_character.get("id"),
            "name": account_character.get("name"),
            "level": account_character.get("level"),
        }
    if catalog_entry_id:
        item["catalog_entry_id"] = catalog_entry_id
    return item


def _load_json_list(path: str | Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


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


def _write_stdout(text: str) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.stdout.write(text)
    sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
