from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar

from .character_stats_catalog import (
    CHARACTER_BASE_STATS_CACHE_PATH,
    CHARACTER_BASE_STATS_CACHE_SCHEMA_VERSION,
    CHARACTER_BASE_STATS_PARSER_VERSION,
    CharacterBaseStatsCatalog,
    CharacterBaseStatsEntry,
    build_character_base_stats_catalog,
    parse_character_base_stats_page,
    read_character_base_stats_cache,
    write_character_base_stats_cache,
)
from .hoyowiki_client import (
    DEFAULT_HOYOWIKI_LANGUAGE,
    fetch_hoyowiki_entry_page,
    fetch_hoyowiki_entry_page_list,
    normalize_hoyowiki_language,
)
from .paths import PROJECT_ROOT
from .weapon_stats_catalog import (
    WEAPON_PASSIVE_HANDLING_NOTE,
    WEAPON_STATS_CACHE_PATH,
    WEAPON_STATS_CACHE_SCHEMA_VERSION,
    WEAPON_STATS_PARSER_VERSION,
    WeaponStatsCatalog,
    WeaponStatsEntry,
    build_weapon_stats_catalog,
    fetch_hoyowiki_weapon_list,
    parse_weapon_stats_page,
    read_weapon_stats_cache,
    write_weapon_stats_cache,
)


CHARACTER_LIST_MENU_ID = "2"
TRAVELER_HANDLING_NOTE = (
    "Traveler variants from HoYoWiki are catalog entries. Account Traveler mapping "
    "is special/deferred and must not be solved by aliasing to one variant."
)
STATIC_CATALOG_LIFECYCLE_NOTE = (
    "HoYoWiki character/weapon stats catalogs are static/generated data. Refresh "
    "them explicitly; do not fetch all detail pages in UI hot paths or ordinary "
    "HoYoLAB account updates."
)

DetailFetcher = Callable[[str, str], dict[str, Any]]
ListFetcher = Callable[[str], list[dict[str, Any]]]
EntryT = TypeVar("EntryT", CharacterBaseStatsEntry, WeaponStatsEntry)


@dataclass(frozen=True, slots=True)
class CatalogRefreshFailure:
    entry_page_id: str
    name: str
    error: str

    def to_dict(self) -> dict[str, str]:
        return {
            "entry_page_id": self.entry_page_id,
            "name": self.name,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class CatalogRefreshResult:
    kind: str
    list_count: int
    existing_count: int
    skipped_existing: int
    fetched: int
    failed: int
    preserved_existing_after_failure: int
    preserved_extra_existing: int
    output_path: str
    failures: tuple[CatalogRefreshFailure, ...] = ()

    def to_dict(self, *, examples: int = 5) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "list_count": self.list_count,
            "existing_count": self.existing_count,
            "skipped_existing": self.skipped_existing,
            "fetched": self.fetched,
            "failed": self.failed,
            "preserved_existing_after_failure": self.preserved_existing_after_failure,
            "preserved_extra_existing": self.preserved_extra_existing,
            "output_path": self.output_path,
            "failure_examples": [
                item.to_dict()
                for item in self.failures[: max(0, int(examples))]
            ],
        }


@dataclass(frozen=True, slots=True)
class StaticCatalogRefreshSummary:
    language: str
    force_refresh: bool
    character: CatalogRefreshResult | None = None
    weapon: CatalogRefreshResult | None = None
    notes: tuple[str, ...] = (
        STATIC_CATALOG_LIFECYCLE_NOTE,
        TRAVELER_HANDLING_NOTE,
        WEAPON_PASSIVE_HANDLING_NOTE,
    )

    def to_dict(self, *, examples: int = 5) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "language": self.language,
            "force_refresh": self.force_refresh,
            "notes": list(self.notes),
            "character": (
                self.character.to_dict(examples=examples)
                if self.character is not None
                else None
            ),
            "weapon": (
                self.weapon.to_dict(examples=examples)
                if self.weapon is not None
                else None
            ),
        }


def refresh_hoyowiki_static_stats_catalogs(
    *,
    language: str = DEFAULT_HOYOWIKI_LANGUAGE,
    force_refresh: bool = False,
    refresh_characters: bool = True,
    refresh_weapons: bool = True,
    character_cache_path: str | Path = CHARACTER_BASE_STATS_CACHE_PATH,
    weapon_cache_path: str | Path = WEAPON_STATS_CACHE_PATH,
    character_list_fetcher: ListFetcher | None = None,
    weapon_list_fetcher: ListFetcher | None = None,
    detail_fetcher: DetailFetcher | None = None,
) -> StaticCatalogRefreshSummary:
    lang = normalize_hoyowiki_language(language)
    detail_fetcher = detail_fetcher or _fetch_entry_detail

    character_result = None
    weapon_result = None

    if refresh_characters:
        character_result = refresh_character_base_stats_catalog(
            language=lang,
            force_refresh=force_refresh,
            cache_path=character_cache_path,
            list_fetcher=character_list_fetcher,
            detail_fetcher=detail_fetcher,
        )

    if refresh_weapons:
        weapon_result = refresh_weapon_stats_catalog(
            language=lang,
            force_refresh=force_refresh,
            cache_path=weapon_cache_path,
            list_fetcher=weapon_list_fetcher,
            detail_fetcher=detail_fetcher,
        )

    return StaticCatalogRefreshSummary(
        language=lang,
        force_refresh=force_refresh,
        character=character_result,
        weapon=weapon_result,
    )


def refresh_character_base_stats_catalog(
    *,
    language: str = DEFAULT_HOYOWIKI_LANGUAGE,
    force_refresh: bool = False,
    cache_path: str | Path = CHARACTER_BASE_STATS_CACHE_PATH,
    existing_catalog: CharacterBaseStatsCatalog | None = None,
    list_fetcher: ListFetcher | None = None,
    detail_fetcher: DetailFetcher | None = None,
) -> CatalogRefreshResult:
    lang = normalize_hoyowiki_language(language)
    cache_path = Path(cache_path)
    list_fetcher = list_fetcher or _fetch_character_list
    detail_fetcher = detail_fetcher or _fetch_entry_detail
    existing_catalog = (
        existing_catalog
        if existing_catalog is not None
        else read_character_base_stats_cache(cache_path)
    )

    existing_by_id = _entries_by_id(existing_catalog.entries if existing_catalog else ())
    existing_is_current = _character_catalog_metadata_is_current(existing_catalog, lang)

    list_entries = list_fetcher(lang)
    merged, result = _refresh_entries(
        kind="character",
        list_entries=list_entries,
        existing_by_id=existing_by_id,
        existing_is_current=existing_is_current,
        force_refresh=force_refresh,
        language=lang,
        output_path=cache_path,
        detail_fetcher=detail_fetcher,
        parser=_parse_character_entry,
        entry_is_valid=_character_entry_is_valid,
    )
    catalog = build_character_base_stats_catalog(merged, language=lang)
    write_character_base_stats_cache(catalog, cache_path)
    return result


def refresh_weapon_stats_catalog(
    *,
    language: str = DEFAULT_HOYOWIKI_LANGUAGE,
    force_refresh: bool = False,
    cache_path: str | Path = WEAPON_STATS_CACHE_PATH,
    existing_catalog: WeaponStatsCatalog | None = None,
    list_fetcher: ListFetcher | None = None,
    detail_fetcher: DetailFetcher | None = None,
) -> CatalogRefreshResult:
    lang = normalize_hoyowiki_language(language)
    cache_path = Path(cache_path)
    list_fetcher = list_fetcher or _fetch_weapon_list
    detail_fetcher = detail_fetcher or _fetch_entry_detail
    existing_catalog = (
        existing_catalog
        if existing_catalog is not None
        else read_weapon_stats_cache(cache_path)
    )

    existing_by_id = _entries_by_id(existing_catalog.entries if existing_catalog else ())
    existing_is_current = _weapon_catalog_metadata_is_current(existing_catalog, lang)

    list_entries = list_fetcher(lang)
    merged, result = _refresh_entries(
        kind="weapon",
        list_entries=list_entries,
        existing_by_id=existing_by_id,
        existing_is_current=existing_is_current,
        force_refresh=force_refresh,
        language=lang,
        output_path=cache_path,
        detail_fetcher=detail_fetcher,
        parser=_parse_weapon_entry,
        entry_is_valid=_weapon_entry_is_valid,
    )
    catalog = build_weapon_stats_catalog(merged, language=lang)
    write_weapon_stats_cache(catalog, cache_path)
    return result


def _refresh_entries(
    *,
    kind: str,
    list_entries: list[dict[str, Any]],
    existing_by_id: dict[str, EntryT],
    existing_is_current: bool,
    force_refresh: bool,
    language: str,
    output_path: Path,
    detail_fetcher: DetailFetcher,
    parser: Callable[[dict[str, Any], dict[str, Any], str], EntryT],
    entry_is_valid: Callable[[EntryT, str], bool],
) -> tuple[list[EntryT], CatalogRefreshResult]:
    merged: list[EntryT] = []
    failures: list[CatalogRefreshFailure] = []
    fetched = 0
    skipped_existing = 0
    preserved_existing_after_failure = 0
    seen_ids: set[str] = set()

    for list_entry in list_entries:
        entry_page_id = _entry_page_id(list_entry)
        name = _entry_name(list_entry)
        if not entry_page_id:
            failures.append(
                CatalogRefreshFailure(
                    entry_page_id="",
                    name=name,
                    error="missing_entry_page_id",
                )
            )
            continue

        seen_ids.add(entry_page_id)
        existing = existing_by_id.get(entry_page_id)
        if (
            existing is not None
            and existing_is_current
            and not force_refresh
            and entry_is_valid(existing, language)
        ):
            merged.append(existing)
            skipped_existing += 1
            continue

        try:
            page = detail_fetcher(entry_page_id, language)
            merged.append(parser(list_entry, page, language))
            fetched += 1
        except Exception as exc:
            failures.append(
                CatalogRefreshFailure(
                    entry_page_id=entry_page_id,
                    name=name,
                    error=str(exc),
                )
            )
            if existing is not None:
                merged.append(existing)
                preserved_existing_after_failure += 1

    extra_existing = [
        entry
        for entry_id, entry in existing_by_id.items()
        if entry_id not in seen_ids
    ]
    merged.extend(extra_existing)

    result = CatalogRefreshResult(
        kind=kind,
        list_count=len(list_entries),
        existing_count=len(existing_by_id),
        skipped_existing=skipped_existing,
        fetched=fetched,
        failed=len(failures),
        preserved_existing_after_failure=preserved_existing_after_failure,
        preserved_extra_existing=len(extra_existing),
        output_path=_display_path(output_path),
        failures=tuple(failures),
    )
    return merged, result


def _parse_character_entry(
    list_entry: dict[str, Any],
    page: dict[str, Any],
    language: str,
) -> CharacterBaseStatsEntry:
    entry = parse_character_base_stats_page(
        page,
        entry_page_id=_entry_page_id(list_entry),
        language=language,
    )
    if not entry.name and _entry_name(list_entry):
        entry = replace(entry, name=_entry_name(list_entry))
    return entry


def _parse_weapon_entry(
    list_entry: dict[str, Any],
    page: dict[str, Any],
    language: str,
) -> WeaponStatsEntry:
    entry = parse_weapon_stats_page(
        page,
        entry_page_id=_entry_page_id(list_entry),
        language=language,
    )
    if not entry.name and _entry_name(list_entry):
        entry = replace(entry, name=_entry_name(list_entry))
    return entry


def _fetch_character_list(language: str) -> list[dict[str, Any]]:
    return fetch_hoyowiki_entry_page_list(
        CHARACTER_LIST_MENU_ID,
        language=language,
    )


def _fetch_weapon_list(language: str) -> list[dict[str, Any]]:
    return fetch_hoyowiki_weapon_list(language=language)


def _fetch_entry_detail(entry_page_id: str, language: str) -> dict[str, Any]:
    return fetch_hoyowiki_entry_page(entry_page_id, language=language)


def _entries_by_id(entries: Iterable[EntryT]) -> dict[str, EntryT]:
    result: dict[str, EntryT] = {}
    for entry in entries:
        entry_page_id = str(entry.entry_page_id or "").strip()
        if entry_page_id:
            result[entry_page_id] = entry
    return result


def _character_catalog_metadata_is_current(
    catalog: CharacterBaseStatsCatalog | None,
    language: str,
) -> bool:
    return bool(
        catalog is not None
        and catalog.schema_version == CHARACTER_BASE_STATS_CACHE_SCHEMA_VERSION
        and catalog.parser_version == CHARACTER_BASE_STATS_PARSER_VERSION
        and normalize_hoyowiki_language(catalog.lang) == language
    )


def _weapon_catalog_metadata_is_current(
    catalog: WeaponStatsCatalog | None,
    language: str,
) -> bool:
    return bool(
        catalog is not None
        and catalog.schema_version == WEAPON_STATS_CACHE_SCHEMA_VERSION
        and catalog.parser_version == WEAPON_STATS_PARSER_VERSION
        and normalize_hoyowiki_language(catalog.lang) == language
    )


def _character_entry_is_valid(entry: CharacterBaseStatsEntry, language: str) -> bool:
    return bool(
        entry.entry_page_id
        and normalize_hoyowiki_language(entry.lang) == language
        and entry.rows
    )


def _weapon_entry_is_valid(entry: WeaponStatsEntry, language: str) -> bool:
    return bool(
        entry.entry_page_id
        and normalize_hoyowiki_language(entry.lang) == language
        and entry.rows
    )


def _entry_page_id(item: dict[str, Any]) -> str:
    return str(item.get("entry_page_id") or item.get("id") or "").strip()


def _entry_name(item: dict[str, Any]) -> str:
    return str(item.get("name") or "").strip()


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except Exception:
        return path.name


def _write_stdout(text: str) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.stdout.write(text)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Explicitly refresh static/generated HoYoWiki stats catalogs."
    )
    parser.add_argument("--language", default=DEFAULT_HOYOWIKI_LANGUAGE)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--characters-only", action="store_true")
    parser.add_argument("--weapons-only", action="store_true")
    parser.add_argument("--character-cache", default=str(CHARACTER_BASE_STATS_CACHE_PATH))
    parser.add_argument("--weapon-cache", default=str(WEAPON_STATS_CACHE_PATH))
    parser.add_argument("--examples", type=int, default=5)
    args = parser.parse_args(argv)

    if args.characters_only and args.weapons_only:
        print(
            "catalog refresh failed: choose at most one of --characters-only/--weapons-only",
            file=sys.stderr,
        )
        return 2

    try:
        summary = refresh_hoyowiki_static_stats_catalogs(
            language=args.language,
            force_refresh=bool(args.force),
            refresh_characters=not args.weapons_only,
            refresh_weapons=not args.characters_only,
            character_cache_path=args.character_cache,
            weapon_cache_path=args.weapon_cache,
        )
    except Exception as exc:
        print(f"catalog refresh failed: {exc}", file=sys.stderr)
        return 1

    _write_stdout(
        json.dumps(
            summary.to_dict(examples=args.examples),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
