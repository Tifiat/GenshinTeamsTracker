from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .catalog_mapping import map_character_catalog, map_weapon_catalog
from .catalog_sanity import build_catalog_sanity_report
from .character_region_catalog import load_character_region_catalog
from .character_stats_catalog import (
    CHARACTER_BASE_STATS_CACHE_PATH,
    read_character_base_stats_cache,
)
from .hoyowiki_client import DEFAULT_HOYOWIKI_LANGUAGE, fetch_hoyowiki_entry_page_list
from .paths import HOYOLAB_DATA_DIR
from .weapon_stats_catalog import (
    WEAPON_STATS_CACHE_PATH,
    fetch_hoyowiki_weapon_list,
    read_weapon_stats_cache,
)


DEFAULT_ACCOUNT_CHARACTERS_PATH = HOYOLAB_DATA_DIR / "account_characters.json"
DEFAULT_ACCOUNT_WEAPONS_PATH = HOYOLAB_DATA_DIR / "account_weapons.json"
DEFAULT_ACCOUNT_LANGUAGE_PATH = HOYOLAB_DATA_DIR / "account_language.json"

WARNING_ACCOUNT_LANGUAGE_MISSING = "account_language_missing_default_en-us"
WARNING_CHARACTER_CATALOG_EMPTY = "character_catalog_empty"
WARNING_WEAPON_CATALOG_EMPTY = "weapon_catalog_empty"
WARNING_CHARACTER_STATS_CATALOG_MISSING = "character_stats_catalog_missing"
WARNING_WEAPON_STATS_CATALOG_MISSING = "weapon_stats_catalog_missing"


def load_json_file(path: str | Path) -> Any:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _path_note(path: str | Path) -> str:
    return Path(path).name


def load_account_language(
    path: str | Path = DEFAULT_ACCOUNT_LANGUAGE_PATH,
    *,
    fallback_language: str = DEFAULT_HOYOWIKI_LANGUAGE,
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    try:
        data = load_json_file(path)
        language = str(data.get("contentLanguage") or "").strip().replace("_", "-").lower()
    except Exception:
        language = ""

    if not language:
        language = fallback_language
        warnings.append(WARNING_ACCOUNT_LANGUAGE_MISSING)

    return language, warnings


def load_account_characters(
    path: str | Path = DEFAULT_ACCOUNT_CHARACTERS_PATH,
) -> list[dict[str, Any]]:
    try:
        data = load_json_file(path)
    except FileNotFoundError:
        return []
    if not isinstance(data, list):
        return []
    return [
        sanitize_account_character(item)
        for item in data
        if isinstance(item, dict)
    ]


def load_account_weapons(
    path: str | Path = DEFAULT_ACCOUNT_WEAPONS_PATH,
) -> list[dict[str, Any]]:
    try:
        data = load_json_file(path)
    except FileNotFoundError:
        return []
    if not isinstance(data, list):
        return []
    return [
        sanitize_account_weapon(item)
        for item in data
        if isinstance(item, dict)
    ]


def sanitize_account_character(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "name": record.get("name"),
        "element": record.get("element"),
        "rarity": record.get("rarity"),
        "level": record.get("level"),
        "constellation": record.get("constellation"),
        "weapon_type": record.get("weapon_type"),
        "weapon_type_name": record.get("weapon_type_name"),
    }


def sanitize_account_weapon(record: dict[str, Any]) -> dict[str, Any]:
    equipped_by = record.get("equipped_by")
    if not isinstance(equipped_by, dict):
        equipped_by = {}

    return {
        "id": record.get("id"),
        "name": record.get("name"),
        "rarity": record.get("rarity"),
        "type": record.get("type"),
        "type_name": record.get("type_name"),
        "level": record.get("level"),
        "refinement": record.get("refinement"),
        "equipped_by": {
            "id": equipped_by.get("id"),
            "name": equipped_by.get("name"),
        } if equipped_by else None,
    }


def load_catalog_records_from_file(
    path: str | Path,
    *,
    language: str | None = None,
) -> list[dict[str, Any]]:
    data = load_json_file(path)
    records = _records_from_json_payload(data, language=language)
    return [
        record
        for record in records
        if isinstance(record, dict)
    ]


def load_hoyowiki_character_catalog_records(
    *,
    language: str,
    catalog_path: str | Path | None = None,
    fetch: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    if catalog_path is not None:
        return (
            load_catalog_records_from_file(catalog_path, language=language),
            f"explicit file: {_path_note(catalog_path)}",
        )

    if fetch:
        return (
            fetch_hoyowiki_entry_page_list("2", language=language),
            "HoYoWiki list fetch: menu_id=2",
        )

    entries = load_character_region_catalog(language, allow_network=False)
    if entries:
        return (
            entries,
            "local character region cache: data/cache/hoyowiki/character_region_catalog.json",
        )

    return [], "no character catalog source; pass --fetch-hoyowiki or --character-catalog"


def load_hoyowiki_weapon_catalog_records(
    *,
    language: str,
    catalog_path: str | Path | None = None,
    fetch: bool = False,
) -> tuple[list[dict[str, Any]], str]:
    if catalog_path is not None:
        return (
            load_catalog_records_from_file(catalog_path, language=language),
            f"explicit file: {_path_note(catalog_path)}",
        )

    if fetch:
        return (
            fetch_hoyowiki_weapon_list(language=language),
            "HoYoWiki list fetch: menu_id=4",
        )

    return [], "no weapon catalog source; pass --fetch-hoyowiki or --weapon-catalog"


def build_mapping_report(
    *,
    account_characters: list[dict[str, Any]],
    account_weapons: list[dict[str, Any]],
    character_catalog: list[dict[str, Any]],
    weapon_catalog: list[dict[str, Any]],
    language: str,
    source_notes: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    examples_per_status: int = 3,
) -> dict[str, Any]:
    warnings = list(warnings or [])
    if not character_catalog:
        warnings.append(WARNING_CHARACTER_CATALOG_EMPTY)
    if not weapon_catalog:
        warnings.append(WARNING_WEAPON_CATALOG_EMPTY)

    character_result = map_character_catalog(
        account_characters,
        character_catalog,
        account_language=language,
    )
    weapon_result = map_weapon_catalog(
        account_weapons,
        weapon_catalog,
        account_language=language,
    )

    return {
        "schema_version": 1,
        "language": language,
        "warnings": sorted(set(warnings)),
        "source_notes": source_notes or {},
        "characters": character_result.to_report(
            examples_per_status=examples_per_status,
        ),
        "weapons": weapon_result.to_report(
            examples_per_status=examples_per_status,
        ),
    }


def build_account_readiness_report(
    *,
    account_characters: list[dict[str, Any]],
    account_weapons: list[dict[str, Any]],
    character_catalog: list[dict[str, Any]],
    weapon_catalog: list[dict[str, Any]],
    language: str,
    character_stats_catalog_path: str | Path = CHARACTER_BASE_STATS_CACHE_PATH,
    weapon_stats_catalog_path: str | Path = WEAPON_STATS_CACHE_PATH,
    source_notes: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    examples_per_status: int = 3,
) -> dict[str, Any]:
    warnings = list(warnings or [])
    if not character_catalog:
        warnings.append(WARNING_CHARACTER_CATALOG_EMPTY)
    if not weapon_catalog:
        warnings.append(WARNING_WEAPON_CATALOG_EMPTY)

    character_stats_catalog = read_character_base_stats_cache(
        character_stats_catalog_path
    )
    weapon_stats_catalog = read_weapon_stats_cache(weapon_stats_catalog_path)
    if character_stats_catalog is None:
        warnings.append(WARNING_CHARACTER_STATS_CATALOG_MISSING)
    if weapon_stats_catalog is None:
        warnings.append(WARNING_WEAPON_STATS_CATALOG_MISSING)

    character_result = map_character_catalog(
        account_characters,
        character_catalog,
        account_language=language,
    )
    weapon_result = map_weapon_catalog(
        account_weapons,
        weapon_catalog,
        account_language=language,
    )
    sanity = build_catalog_sanity_report(
        character_catalog=character_stats_catalog,
        weapon_catalog=weapon_stats_catalog,
        character_mapping=character_result,
        weapon_mapping=weapon_result,
    )

    return {
        "schema_version": 1,
        "language": language,
        "warnings": sorted(set(warnings)),
        "source_notes": source_notes or {},
        "mapping": {
            "characters": character_result.to_report(
                examples_per_status=examples_per_status,
            ),
            "weapons": weapon_result.to_report(
                examples_per_status=examples_per_status,
            ),
        },
        "readiness": sanity.to_dict(examples_per_status=examples_per_status),
    }


def build_mapping_report_from_paths(
    *,
    characters_path: str | Path = DEFAULT_ACCOUNT_CHARACTERS_PATH,
    weapons_path: str | Path = DEFAULT_ACCOUNT_WEAPONS_PATH,
    language_path: str | Path = DEFAULT_ACCOUNT_LANGUAGE_PATH,
    character_catalog_path: str | Path | None = None,
    weapon_catalog_path: str | Path | None = None,
    fetch_hoyowiki: bool = False,
    language: str | None = None,
    examples_per_status: int = 3,
) -> dict[str, Any]:
    warnings: list[str] = []
    if language is None:
        language, language_warnings = load_account_language(language_path)
        warnings.extend(language_warnings)
    else:
        language = str(language).strip().replace("_", "-").lower() or DEFAULT_HOYOWIKI_LANGUAGE

    account_characters = load_account_characters(characters_path)
    account_weapons = load_account_weapons(weapons_path)
    character_catalog, character_source = load_hoyowiki_character_catalog_records(
        language=language,
        catalog_path=character_catalog_path,
        fetch=fetch_hoyowiki,
    )
    weapon_catalog, weapon_source = load_hoyowiki_weapon_catalog_records(
        language=language,
        catalog_path=weapon_catalog_path,
        fetch=fetch_hoyowiki,
    )

    return build_mapping_report(
        account_characters=account_characters,
        account_weapons=account_weapons,
        character_catalog=character_catalog,
        weapon_catalog=weapon_catalog,
        language=language,
        warnings=warnings,
        examples_per_status=examples_per_status,
        source_notes={
            "account_characters": _path_note(characters_path),
            "account_weapons": _path_note(weapons_path),
            "account_language": _path_note(language_path),
            "character_catalog": character_source,
            "weapon_catalog": weapon_source,
            "network_fetch": bool(fetch_hoyowiki),
            "sanitized": True,
        },
    )


def build_account_readiness_report_from_paths(
    *,
    characters_path: str | Path = DEFAULT_ACCOUNT_CHARACTERS_PATH,
    weapons_path: str | Path = DEFAULT_ACCOUNT_WEAPONS_PATH,
    language_path: str | Path = DEFAULT_ACCOUNT_LANGUAGE_PATH,
    character_catalog_path: str | Path | None = None,
    weapon_catalog_path: str | Path | None = None,
    character_stats_catalog_path: str | Path = CHARACTER_BASE_STATS_CACHE_PATH,
    weapon_stats_catalog_path: str | Path = WEAPON_STATS_CACHE_PATH,
    fetch_hoyowiki: bool = False,
    language: str | None = None,
    examples_per_status: int = 3,
) -> dict[str, Any]:
    warnings: list[str] = []
    if language is None:
        language, language_warnings = load_account_language(language_path)
        warnings.extend(language_warnings)
    else:
        language = str(language).strip().replace("_", "-").lower() or DEFAULT_HOYOWIKI_LANGUAGE

    account_characters = load_account_characters(characters_path)
    account_weapons = load_account_weapons(weapons_path)
    character_catalog, character_source = load_hoyowiki_character_catalog_records(
        language=language,
        catalog_path=character_catalog_path,
        fetch=fetch_hoyowiki,
    )
    weapon_catalog, weapon_source = load_hoyowiki_weapon_catalog_records(
        language=language,
        catalog_path=weapon_catalog_path,
        fetch=fetch_hoyowiki,
    )

    return build_account_readiness_report(
        account_characters=account_characters,
        account_weapons=account_weapons,
        character_catalog=character_catalog,
        weapon_catalog=weapon_catalog,
        language=language,
        character_stats_catalog_path=character_stats_catalog_path,
        weapon_stats_catalog_path=weapon_stats_catalog_path,
        warnings=warnings,
        examples_per_status=examples_per_status,
        source_notes={
            "account_characters": _path_note(characters_path),
            "account_weapons": _path_note(weapons_path),
            "account_language": _path_note(language_path),
            "character_catalog": character_source,
            "weapon_catalog": weapon_source,
            "character_stats_catalog": _path_note(character_stats_catalog_path),
            "weapon_stats_catalog": _path_note(weapon_stats_catalog_path),
            "network_fetch": bool(fetch_hoyowiki),
            "detail_fetch": False,
            "sanitized": True,
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a sanitized account character/weapon to HoYoWiki catalog "
            "mapping report."
        )
    )
    parser.add_argument("--characters", default=str(DEFAULT_ACCOUNT_CHARACTERS_PATH))
    parser.add_argument("--weapons", default=str(DEFAULT_ACCOUNT_WEAPONS_PATH))
    parser.add_argument("--language-file", default=str(DEFAULT_ACCOUNT_LANGUAGE_PATH))
    parser.add_argument("--language", default=None)
    parser.add_argument("--character-catalog", default=None)
    parser.add_argument("--weapon-catalog", default=None)
    parser.add_argument(
        "--readiness",
        action="store_true",
        help="Include account-matched stats catalog readiness using local stats caches.",
    )
    parser.add_argument(
        "--character-stats-catalog",
        default=str(CHARACTER_BASE_STATS_CACHE_PATH),
    )
    parser.add_argument(
        "--weapon-stats-catalog",
        default=str(WEAPON_STATS_CACHE_PATH),
    )
    parser.add_argument(
        "--fetch-hoyowiki",
        action="store_true",
        help="Explicitly fetch HoYoWiki character/weapon list pages if catalog files are not passed.",
    )
    parser.add_argument("--examples", type=int, default=3)
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    try:
        if args.readiness:
            report = build_account_readiness_report_from_paths(
                characters_path=args.characters,
                weapons_path=args.weapons,
                language_path=args.language_file,
                language=args.language,
                character_catalog_path=args.character_catalog,
                weapon_catalog_path=args.weapon_catalog,
                character_stats_catalog_path=args.character_stats_catalog,
                weapon_stats_catalog_path=args.weapon_stats_catalog,
                fetch_hoyowiki=args.fetch_hoyowiki,
                examples_per_status=max(0, int(args.examples)),
            )
        else:
            report = build_mapping_report_from_paths(
                characters_path=args.characters,
                weapons_path=args.weapons,
                language_path=args.language_file,
                language=args.language,
                character_catalog_path=args.character_catalog,
                weapon_catalog_path=args.weapon_catalog,
                fetch_hoyowiki=args.fetch_hoyowiki,
                examples_per_status=max(0, int(args.examples)),
            )
    except Exception as exc:
        print(f"mapping report failed: {exc}", file=sys.stderr)
        return 1

    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    else:
        _write_stdout(text)
    return 0


def _write_stdout(text: str) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.stdout.write(text)
    sys.stdout.write("\n")


def _records_from_json_payload(data: Any, *, language: str | None = None) -> list[Any]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []

    entries = data.get("entries")
    if isinstance(entries, list):
        return entries

    languages = data.get("languages")
    if isinstance(languages, dict):
        lang = str(language or "").strip().replace("_", "-").lower()
        if lang and isinstance(languages.get(lang), dict):
            lang_entries = languages[lang].get("entries")
            if isinstance(lang_entries, list):
                return lang_entries
        for language_cache in languages.values():
            if isinstance(language_cache, dict) and isinstance(language_cache.get("entries"), list):
                return language_cache["entries"]

    return []


if __name__ == "__main__":
    raise SystemExit(main())
