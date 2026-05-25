from __future__ import annotations

import html
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .hoyowiki_client import (
    DEFAULT_HOYOWIKI_LANGUAGE,
    fetch_hoyowiki_entry_page,
    normalize_hoyowiki_language,
)
from .paths import PROJECT_ROOT


CHARACTER_TRAIT_CATALOG_SCHEMA_VERSION = 2
CHARACTER_TRAIT_CATALOG_PATH = (
    PROJECT_ROOT / "data" / "cache" / "hoyowiki" / "character_trait_catalog.json"
)

TRAIT_MOONSIGN = "moonsign"
TRAIT_HEXEREI = "hexerei"
TRAIT_STANDARD_5_STAR = "standard_5_star"

HOYOWIKI_HEXEREI_ENTRY_PAGE_ID = "9347"
HOYOWIKI_MOONSIGN_ENTRY_PAGE_ID = "8782"
HOYOWIKI_HEXEREI_SOURCE_URL = "https://wiki.hoyolab.com/pc/genshin/entry/9347"
HOYOWIKI_MOONSIGN_SOURCE_URL = "https://wiki.hoyolab.com/pc/genshin/entry/8782"
HOYOWIKI_STANDARD_5_STAR_SOURCE_URL = "https://wiki.hoyolab.com/pc/genshin/entry/2952"
HOYOWIKI_TRAIT_SOURCE_NAME = "hoyowiki_team_bonus_entry"

TraitPageFetcher = Callable[[str, str], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class CharacterTraitTooltipSection:
    trait_key: str
    character_entry_page_id: str
    required_constellation: int
    section_index: int
    language: str
    title: str
    body: str
    canonical_name: str = ""
    icon_url: str = ""
    source_entry_page_id: str = ""
    source_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "trait_key": self.trait_key,
            "character_entry_page_id": self.character_entry_page_id,
            "required_constellation": self.required_constellation,
            "section_index": self.section_index,
            "language": self.language,
            "title": self.title,
            "body": self.body,
            "canonical_name": self.canonical_name,
            "icon_url": self.icon_url,
            "source_entry_page_id": self.source_entry_page_id,
            "source_url": self.source_url,
        }


@dataclass(frozen=True, slots=True)
class HexereiPageParseResult:
    entries: tuple["CharacterTraitEntry", ...] = ()
    sections: tuple[CharacterTraitTooltipSection, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CharacterTraitEntry:
    name: str
    traits: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    source: str = HOYOWIKI_TRAIT_SOURCE_NAME
    source_url: str = ""
    source_entry_page_id: str = ""
    source_section: str = ""
    source_character_entry_page_id: str = ""
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "traits": list(self.traits),
            "aliases": list(self.aliases),
            "source": self.source,
            "source_url": self.source_url,
            "source_entry_page_id": self.source_entry_page_id,
            "source_section": self.source_section,
            "source_character_entry_page_id": self.source_character_entry_page_id,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CharacterTraitEntry":
        return cls(
            name=str(data.get("name") or ""),
            traits=tuple(
                _normalize_trait_name(item)
                for item in data.get("traits") or []
                if _normalize_trait_name(item)
            ),
            aliases=tuple(
                str(item).strip()
                for item in data.get("aliases") or []
                if str(item or "").strip()
            ),
            source=str(data.get("source") or HOYOWIKI_TRAIT_SOURCE_NAME),
            source_url=str(data.get("source_url") or ""),
            source_entry_page_id=str(data.get("source_entry_page_id") or ""),
            source_section=str(data.get("source_section") or ""),
            source_character_entry_page_id=str(
                data.get("source_character_entry_page_id") or ""
            ),
            notes=tuple(
                str(item).strip()
                for item in data.get("notes") or []
                if str(item or "").strip()
            ),
        )


@dataclass(frozen=True, slots=True)
class CharacterTraitTooltipReference:
    trait: str
    title: str
    body: str = ""
    source_url: str = ""
    source_entry_page_id: str = ""
    language: str = DEFAULT_HOYOWIKI_LANGUAGE
    member_text_by_name: tuple[tuple[str, str], ...] = ()
    member_text_by_entry_page_id: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "trait": self.trait,
            "title": self.title,
            "body": self.body,
            "source_url": self.source_url,
            "source_entry_page_id": self.source_entry_page_id,
            "language": self.language,
            "member_text_by_name": dict(self.member_text_by_name),
            "member_text_by_entry_page_id": dict(self.member_text_by_entry_page_id),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CharacterTraitTooltipReference":
        return cls(
            trait=_normalize_trait_name(data.get("trait")),
            title=str(data.get("title") or ""),
            body=str(data.get("body") or ""),
            source_url=str(data.get("source_url") or ""),
            source_entry_page_id=str(data.get("source_entry_page_id") or ""),
            language=str(data.get("language") or DEFAULT_HOYOWIKI_LANGUAGE),
            member_text_by_name=_string_mapping_items(data.get("member_text_by_name")),
            member_text_by_entry_page_id=_string_mapping_items(
                data.get("member_text_by_entry_page_id")
            ),
        )

    def text_for_member(
        self,
        *,
        name: str = "",
        entry_page_id: str = "",
    ) -> str:
        by_entry = dict(self.member_text_by_entry_page_id)
        if entry_page_id and by_entry.get(entry_page_id):
            return by_entry[entry_page_id]
        normalized_name = normalize_character_trait_name(name)
        by_name = {
            normalize_character_trait_name(key): value
            for key, value in self.member_text_by_name
        }
        return by_name.get(normalized_name, "")


@dataclass(frozen=True, slots=True)
class CharacterTraitCatalog:
    entries: tuple[CharacterTraitEntry, ...]
    tooltip_references: tuple[CharacterTraitTooltipReference, ...] = ()
    language: str = DEFAULT_HOYOWIKI_LANGUAGE
    fetched_at: str = ""
    source: str = HOYOWIKI_TRAIT_SOURCE_NAME
    schema_version: int = CHARACTER_TRAIT_CATALOG_SCHEMA_VERSION
    notes: tuple[str, ...] = (
        "Static/reference character trait catalog for resonance systems.",
        "This is not account state and does not define resonance bonuses.",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "language": self.language,
            "fetched_at": self.fetched_at,
            "source": self.source,
            "source_urls": {
                TRAIT_MOONSIGN: HOYOWIKI_MOONSIGN_SOURCE_URL,
                TRAIT_HEXEREI: HOYOWIKI_HEXEREI_SOURCE_URL,
                TRAIT_STANDARD_5_STAR: HOYOWIKI_STANDARD_5_STAR_SOURCE_URL,
            },
            "notes": list(self.notes),
            "tooltip_references": [
                reference.to_dict() for reference in self.tooltip_references
            ],
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CharacterTraitCatalog":
        return cls(
            schema_version=int(
                data.get("schema_version") or CHARACTER_TRAIT_CATALOG_SCHEMA_VERSION
            ),
            language=str(data.get("language") or DEFAULT_HOYOWIKI_LANGUAGE),
            fetched_at=str(data.get("fetched_at") or ""),
            source=str(data.get("source") or HOYOWIKI_TRAIT_SOURCE_NAME),
            notes=tuple(str(item) for item in data.get("notes") or []),
            entries=tuple(
                CharacterTraitEntry.from_dict(item)
                for item in data.get("entries") or []
                if isinstance(item, dict)
            ),
            tooltip_references=tuple(
                CharacterTraitTooltipReference.from_dict(item)
                for item in data.get("tooltip_references") or []
                if isinstance(item, dict)
            ),
        )


def list_seed_character_traits() -> tuple[CharacterTraitEntry, ...]:
    return SEEDED_CHARACTER_TRAITS


def read_character_trait_catalog_cache(
    path: str | Path = CHARACTER_TRAIT_CATALOG_PATH,
) -> CharacterTraitCatalog | None:
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return CharacterTraitCatalog.from_dict(data)


def write_character_trait_catalog_cache(
    catalog: CharacterTraitCatalog,
    path: str | Path = CHARACTER_TRAIT_CATALOG_PATH,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(catalog.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_character_trait_catalog(
    path: str | Path = CHARACTER_TRAIT_CATALOG_PATH,
) -> CharacterTraitCatalog:
    cached = read_character_trait_catalog_cache(path)
    if cached is None:
        return CharacterTraitCatalog(
            entries=SEEDED_CHARACTER_TRAITS,
            source="seed",
        )
    return CharacterTraitCatalog(
        entries=_dedupe_entries((*cached.entries, *SEEDED_CHARACTER_TRAITS)),
        tooltip_references=cached.tooltip_references,
        language=cached.language,
        fetched_at=cached.fetched_at,
        source=cached.source,
        schema_version=cached.schema_version,
        notes=cached.notes,
    )


def refresh_character_trait_catalog(
    *,
    language: str = DEFAULT_HOYOWIKI_LANGUAGE,
    cache_path: str | Path = CHARACTER_TRAIT_CATALOG_PATH,
    page_fetcher: TraitPageFetcher | None = None,
) -> CharacterTraitCatalog:
    page_fetcher = page_fetcher or _fetch_hoyowiki_trait_page
    entries: list[CharacterTraitEntry] = []
    entries.extend(
        extract_character_trait_entries_from_hoyowiki_page(
            page_fetcher(HOYOWIKI_MOONSIGN_ENTRY_PAGE_ID, language),
            trait=TRAIT_MOONSIGN,
            source_url=HOYOWIKI_MOONSIGN_SOURCE_URL,
            source_entry_page_id=HOYOWIKI_MOONSIGN_ENTRY_PAGE_ID,
            source_section="Moonsign",
        )
    )
    entries.extend(
        extract_character_trait_entries_from_hoyowiki_page(
            page_fetcher(HOYOWIKI_HEXEREI_ENTRY_PAGE_ID, language),
            trait=TRAIT_HEXEREI,
            source_url=HOYOWIKI_HEXEREI_SOURCE_URL,
            source_entry_page_id=HOYOWIKI_HEXEREI_ENTRY_PAGE_ID,
            source_section="Hexerei",
        )
    )
    entries.extend(entries_with_trait(TRAIT_STANDARD_5_STAR, entries=SEEDED_CHARACTER_TRAITS))
    catalog = CharacterTraitCatalog(
        entries=_dedupe_entries(entries),
        language=language,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
    write_character_trait_catalog_cache(catalog, cache_path)
    return catalog


def tooltip_reference_for_trait(
    trait: str,
    catalog: CharacterTraitCatalog | None = None,
) -> CharacterTraitTooltipReference:
    normalized_trait = _normalize_trait_name(trait)
    catalog = catalog or load_character_trait_catalog()
    for reference in catalog.tooltip_references:
        if reference.trait == normalized_trait:
            return reference
    return _default_tooltip_reference(normalized_trait, language=catalog.language)


def hexerei_tooltip_reference(
    catalog: CharacterTraitCatalog | None = None,
) -> CharacterTraitTooltipReference:
    return tooltip_reference_for_trait(TRAIT_HEXEREI, catalog=catalog)


def init_character_trait_reference_storage(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS character_trait_definitions (
            trait_key TEXT PRIMARY KEY,
            label TEXT,
            canonical_language TEXT,
            source_entry_page_id TEXT,
            source_url TEXT,
            icon_path TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS character_trait_memberships (
            trait_key TEXT NOT NULL,
            character_entry_page_id TEXT NOT NULL,
            canonical_name TEXT,
            icon_url TEXT,
            source_entry_page_id TEXT,
            source_language TEXT,
            updated_at TEXT,
            PRIMARY KEY (trait_key, character_entry_page_id),
            FOREIGN KEY (trait_key) REFERENCES character_trait_definitions(trait_key)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS character_trait_tooltip_sections (
            trait_key TEXT NOT NULL,
            character_entry_page_id TEXT NOT NULL,
            required_constellation INTEGER NOT NULL,
            section_index INTEGER NOT NULL,
            language TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            source_entry_page_id TEXT,
            source_url TEXT,
            updated_at TEXT,
            PRIMARY KEY (
                trait_key,
                character_entry_page_id,
                required_constellation,
                section_index,
                language
            ),
            FOREIGN KEY (trait_key, character_entry_page_id)
                REFERENCES character_trait_memberships(trait_key, character_entry_page_id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_character_trait_memberships_character
            ON character_trait_memberships(character_entry_page_id);
        CREATE INDEX IF NOT EXISTS idx_character_trait_tooltip_sections_lookup
            ON character_trait_tooltip_sections(
                trait_key,
                character_entry_page_id,
                language,
                required_constellation
            );
        """
    )


def rebuild_character_trait_reference_from_catalog(
    conn: sqlite3.Connection,
    catalog: CharacterTraitCatalog | None = None,
    *,
    updated_at: str | None = None,
) -> int:
    init_character_trait_reference_storage(conn)
    catalog = catalog or load_character_trait_catalog()
    now = updated_at or _utc_now()
    definitions = {
        TRAIT_HEXEREI: ("Hexerei", DEFAULT_HOYOWIKI_LANGUAGE, HOYOWIKI_HEXEREI_ENTRY_PAGE_ID, HOYOWIKI_HEXEREI_SOURCE_URL),
        TRAIT_MOONSIGN: ("Moonsign", DEFAULT_HOYOWIKI_LANGUAGE, HOYOWIKI_MOONSIGN_ENTRY_PAGE_ID, HOYOWIKI_MOONSIGN_SOURCE_URL),
        TRAIT_STANDARD_5_STAR: ("Standard 5-star", DEFAULT_HOYOWIKI_LANGUAGE, "2952", HOYOWIKI_STANDARD_5_STAR_SOURCE_URL),
    }
    for trait_key, (label, canonical_language, source_entry_id, source_url) in definitions.items():
        conn.execute(
            """
            INSERT INTO character_trait_definitions (
                trait_key, label, canonical_language, source_entry_page_id,
                source_url, icon_path, updated_at
            )
            VALUES (?, ?, ?, ?, ?, COALESCE((
                SELECT icon_path FROM character_trait_definitions WHERE trait_key = ?
            ), ''), ?)
            ON CONFLICT(trait_key) DO UPDATE SET
                label = excluded.label,
                canonical_language = excluded.canonical_language,
                source_entry_page_id = excluded.source_entry_page_id,
                source_url = excluded.source_url,
                updated_at = excluded.updated_at
            """,
            (
                trait_key,
                label,
                canonical_language,
                source_entry_id,
                source_url,
                trait_key,
                now,
            ),
        )

    conn.execute("DELETE FROM character_trait_memberships")
    total = 0
    for entry in catalog.entries:
        for trait in entry.traits:
            character_entry_id = str(entry.source_character_entry_page_id or "").strip()
            if not trait or not character_entry_id:
                continue
            conn.execute(
                """
                INSERT INTO character_trait_memberships (
                    trait_key,
                    character_entry_page_id,
                    canonical_name,
                    icon_url,
                    source_entry_page_id,
                    source_language,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trait_key, character_entry_page_id) DO UPDATE SET
                    canonical_name = excluded.canonical_name,
                    icon_url = excluded.icon_url,
                    source_entry_page_id = excluded.source_entry_page_id,
                    source_language = excluded.source_language,
                    updated_at = excluded.updated_at
                """,
                (
                    trait,
                    character_entry_id,
                    entry.name,
                    "",
                    entry.source_entry_page_id,
                    catalog.language,
                    now,
                ),
            )
            total += 1
    return total


def character_trait_entries_from_sqlite(
    conn: sqlite3.Connection,
) -> tuple[CharacterTraitEntry, ...]:
    init_character_trait_reference_storage(conn)
    try:
        rows = conn.execute(
            """
            SELECT
                trait_key,
                character_entry_page_id,
                canonical_name,
                source_entry_page_id
            FROM character_trait_memberships
            ORDER BY trait_key ASC, canonical_name COLLATE NOCASE ASC
            """
        ).fetchall()
    except sqlite3.Error:
        return ()
    return tuple(
        CharacterTraitEntry(
            name=str(row["canonical_name"] or ""),
            traits=(_normalize_trait_name(row["trait_key"]),),
            source_entry_page_id=str(row["source_entry_page_id"] or ""),
            source_character_entry_page_id=str(row["character_entry_page_id"] or ""),
            source_url=_source_url_for_trait(str(row["trait_key"] or "")),
        )
        for row in rows
        if str(row["trait_key"] or "").strip()
        and str(row["character_entry_page_id"] or "").strip()
    )


def upsert_character_trait_tooltip_sections(
    conn: sqlite3.Connection,
    sections: Iterable[CharacterTraitTooltipSection],
    *,
    trait_key: str = TRAIT_HEXEREI,
    language: str | None = None,
    updated_at: str | None = None,
) -> int:
    init_character_trait_reference_storage(conn)
    normalized_trait = _normalize_trait_name(trait_key)
    lang = normalize_hoyowiki_language(language)
    now = updated_at or _utc_now()
    conn.execute(
        """
        DELETE FROM character_trait_tooltip_sections
        WHERE trait_key = ? AND language = ?
        """,
        (normalized_trait, lang),
    )
    total = 0
    for section in sections:
        if section.trait_key != normalized_trait or section.language != lang:
            continue
        if not section.character_entry_page_id or not section.title or not section.body:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO character_trait_memberships (
                trait_key,
                character_entry_page_id,
                canonical_name,
                icon_url,
                source_entry_page_id,
                source_language,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_trait,
                section.character_entry_page_id,
                section.canonical_name,
                section.icon_url,
                section.source_entry_page_id,
                DEFAULT_HOYOWIKI_LANGUAGE,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO character_trait_tooltip_sections (
                trait_key,
                character_entry_page_id,
                required_constellation,
                section_index,
                language,
                title,
                body,
                source_entry_page_id,
                source_url,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(
                trait_key,
                character_entry_page_id,
                required_constellation,
                section_index,
                language
            ) DO UPDATE SET
                title = excluded.title,
                body = excluded.body,
                source_entry_page_id = excluded.source_entry_page_id,
                source_url = excluded.source_url,
                updated_at = excluded.updated_at
            """,
            (
                section.trait_key,
                section.character_entry_page_id,
                int(section.required_constellation),
                int(section.section_index),
                section.language,
                section.title,
                section.body,
                section.source_entry_page_id,
                section.source_url,
                now,
            ),
        )
        total += 1
    return total


def extract_character_trait_entries_from_hoyowiki_page(
    page: dict[str, Any],
    *,
    trait: str,
    source_url: str,
    source_entry_page_id: str,
    source_section: str,
) -> tuple[CharacterTraitEntry, ...]:
    normalized_trait = _normalize_trait_name(trait)
    entries: dict[str, CharacterTraitEntry] = {}
    for attrs in _iter_custom_entry_attrs(page):
        if str(attrs.get("menuid") or attrs.get("menu_id") or "") != "2":
            continue
        name = str(attrs.get("name") or "").strip()
        if not name:
            continue
        entry = CharacterTraitEntry(
            name=name,
            traits=(normalized_trait,),
            source_url=source_url,
            source_entry_page_id=source_entry_page_id,
            source_section=source_section,
            source_character_entry_page_id=str(attrs.get("epid") or ""),
        )
        entries.setdefault(normalize_character_trait_name(name), entry)
    return tuple(entries.values())


def parse_hexerei_sections_from_hoyowiki_page(
    page: dict[str, Any],
    *,
    language: str = DEFAULT_HOYOWIKI_LANGUAGE,
) -> HexereiPageParseResult:
    lang = normalize_hoyowiki_language(language)
    raw_html = _hexerei_detail_html(page)
    if not raw_html:
        return HexereiPageParseResult(warnings=("hexerei_detail_html_missing",))

    entries: list[CharacterTraitEntry] = []
    sections: list[CharacterTraitTooltipSection] = []
    warnings: list[str] = []
    for row_index, row_html in enumerate(_iter_table_rows(raw_html)):
        character_attrs = _first_character_custom_entry_attrs(row_html)
        if not character_attrs:
            continue
        character_entry_id = str(character_attrs.get("epid") or "").strip()
        character_name = str(character_attrs.get("name") or "").strip()
        icon_url = str(character_attrs.get("icon") or "").strip()
        if not character_entry_id or not character_name:
            warnings.append(f"row_{row_index}_missing_character_identity")
            continue
        entries.append(
            CharacterTraitEntry(
                name=character_name,
                traits=(TRAIT_HEXEREI,),
                source_url=HOYOWIKI_HEXEREI_SOURCE_URL,
                source_entry_page_id=HOYOWIKI_HEXEREI_ENTRY_PAGE_ID,
                source_section="Hexerei",
                source_character_entry_page_id=character_entry_id,
            )
        )
        paragraphs = _paragraph_texts(row_html)
        section_counters: dict[int, int] = {}
        active_heading: tuple[str, int, int] | None = None
        active_body: list[str] = []
        for paragraph in paragraphs:
            if _is_hexerei_section_stop(paragraph, lang):
                if active_heading is not None and active_body:
                    title, required_constellation, section_index = active_heading
                    sections.append(
                        _hexerei_section(
                            character_entry_id=character_entry_id,
                            character_name=character_name,
                            icon_url=icon_url,
                            language=lang,
                            title=title,
                            body="\n".join(active_body),
                            required_constellation=required_constellation,
                            section_index=section_index,
                        )
                    )
                active_heading = None
                active_body = []
                continue
            marker = _hexerei_section_marker(paragraph, lang)
            if marker is not None:
                if active_heading is not None and active_body:
                    title, required_constellation, section_index = active_heading
                    sections.append(
                        _hexerei_section(
                            character_entry_id=character_entry_id,
                            character_name=character_name,
                            icon_url=icon_url,
                            language=lang,
                            title=title,
                            body="\n".join(active_body),
                            required_constellation=required_constellation,
                            section_index=section_index,
                        )
                    )
                title, required_constellation, first_body = marker
                section_index = section_counters.get(required_constellation, 0)
                section_counters[required_constellation] = section_index + 1
                active_heading = (title, required_constellation, section_index)
                active_body = [first_body] if first_body else []
                continue
            if active_heading is not None:
                active_body.append(paragraph)
        if active_heading is not None and active_body:
            title, required_constellation, section_index = active_heading
            sections.append(
                _hexerei_section(
                    character_entry_id=character_entry_id,
                    character_name=character_name,
                    icon_url=icon_url,
                    language=lang,
                    title=title,
                    body="\n".join(active_body),
                    required_constellation=required_constellation,
                    section_index=section_index,
                )
            )
        if not any(section.character_entry_page_id == character_entry_id for section in sections):
            warnings.append(f"row_{row_index}_{character_entry_id}_no_classified_sections")

    return HexereiPageParseResult(
        entries=_dedupe_entries(entries),
        sections=tuple(sections),
        warnings=tuple(warnings),
    )


def refresh_hexerei_trait_reference(
    conn: sqlite3.Connection,
    *,
    language: str | None = None,
    page_fetcher: TraitPageFetcher | None = None,
) -> dict[str, Any]:
    from .paths import PROJECT_ROOT

    page_fetcher = page_fetcher or _fetch_hoyowiki_trait_page
    requested_language = normalize_hoyowiki_language(language or _account_content_language())
    languages = [DEFAULT_HOYOWIKI_LANGUAGE]
    if requested_language != DEFAULT_HOYOWIKI_LANGUAGE:
        languages.append(requested_language)
    now = _utc_now()

    canonical_page = page_fetcher(HOYOWIKI_HEXEREI_ENTRY_PAGE_ID, DEFAULT_HOYOWIKI_LANGUAGE)
    canonical = parse_hexerei_sections_from_hoyowiki_page(
        canonical_page,
        language=DEFAULT_HOYOWIKI_LANGUAGE,
    )
    catalog = load_character_trait_catalog()
    updated_catalog = _replace_trait_entries(
        catalog,
        trait=TRAIT_HEXEREI,
        entries=canonical.entries,
        language=DEFAULT_HOYOWIKI_LANGUAGE,
        fetched_at=now,
    )
    write_character_trait_catalog_cache(updated_catalog)
    membership_rows = rebuild_character_trait_reference_from_catalog(
        conn,
        updated_catalog,
        updated_at=now,
    )
    en_sections = upsert_character_trait_tooltip_sections(
        conn,
        canonical.sections,
        trait_key=TRAIT_HEXEREI,
        language=DEFAULT_HOYOWIKI_LANGUAGE,
        updated_at=now,
    )
    summaries: list[dict[str, Any]] = [
        {
            "language": DEFAULT_HOYOWIKI_LANGUAGE,
            "characters": len(canonical.entries),
            "sections": en_sections,
            "warnings": list(canonical.warnings),
        }
    ]

    canonical_keys = {
        (
            section.character_entry_page_id,
            section.required_constellation,
            section.section_index,
        )
        for section in canonical.sections
    }
    localized_missing = 0
    for lang in languages[1:]:
        localized_page = page_fetcher(HOYOWIKI_HEXEREI_ENTRY_PAGE_ID, lang)
        localized = parse_hexerei_sections_from_hoyowiki_page(
            localized_page,
            language=lang,
        )
        row_count = upsert_character_trait_tooltip_sections(
            conn,
            localized.sections,
            trait_key=TRAIT_HEXEREI,
            language=lang,
            updated_at=now,
        )
        localized_keys = {
            (
                section.character_entry_page_id,
                section.required_constellation,
                section.section_index,
            )
            for section in localized.sections
        }
        localized_missing = len(canonical_keys - localized_keys)
        summaries.append(
            {
                "language": lang,
                "characters": len(localized.entries),
                "sections": row_count,
                "missing_canonical_sections": localized_missing,
                "warnings": list(localized.warnings),
            }
        )

    return {
        "source_entry_page_id": HOYOWIKI_HEXEREI_ENTRY_PAGE_ID,
        "source_url": HOYOWIKI_HEXEREI_SOURCE_URL,
        "languages": languages,
        "canonical_character_count": len(canonical.entries),
        "canonical_section_count": en_sections,
        "localized_missing_count": localized_missing,
        "membership_rows": membership_rows,
        "language_summaries": summaries,
        "db_path": str(PROJECT_ROOT / "data" / "artifacts.db"),
    }


def get_hexerei_tooltip_sections(
    conn: sqlite3.Connection,
    *,
    character_entry_page_id: str,
    account_constellation: int | None,
    preferred_language: str | None = None,
    fallback_language: str | None = DEFAULT_HOYOWIKI_LANGUAGE,
) -> tuple[dict[str, Any], ...]:
    init_character_trait_reference_storage(conn)
    entry_id = str(character_entry_page_id or "").strip()
    if not entry_id:
        return ()
    constellation = max(0, int(account_constellation or 0))
    preferred = normalize_hoyowiki_language(preferred_language)
    fallback = normalize_hoyowiki_language(fallback_language)
    languages = _dedupe_text((preferred, fallback))
    placeholders = ",".join("?" for _ in languages)
    rows = conn.execute(
        f"""
        SELECT *
        FROM character_trait_tooltip_sections
        WHERE trait_key = ?
          AND character_entry_page_id = ?
          AND required_constellation <= ?
          AND language IN ({placeholders})
        ORDER BY required_constellation ASC, section_index ASC, language ASC
        """,
        (TRAIT_HEXEREI, entry_id, constellation, *languages),
    ).fetchall()
    by_key: dict[tuple[int, int], dict[str, Any]] = {}
    for row in rows:
        key = (int(row["required_constellation"]), int(row["section_index"]))
        current = by_key.get(key)
        row_lang = str(row["language"] or "")
        if current is None or (
            row_lang == preferred and current.get("resolved_language") != preferred
        ):
            by_key[key] = {
                "trait_key": row["trait_key"],
                "character_entry_page_id": row["character_entry_page_id"],
                "required_constellation": int(row["required_constellation"]),
                "section_index": int(row["section_index"]),
                "resolved_language": row_lang,
                "title": row["title"],
                "body": row["body"],
                "source_entry_page_id": row["source_entry_page_id"],
                "source_url": row["source_url"],
                "used_fallback_language": row_lang != preferred,
            }
    return tuple(by_key[key] for key in sorted(by_key))


def entries_with_trait(
    trait: str,
    entries: Iterable[CharacterTraitEntry] | None = None,
) -> tuple[CharacterTraitEntry, ...]:
    normalized_trait = _normalize_trait_name(trait)
    return tuple(
        entry
        for entry in (entries or load_character_trait_catalog().entries)
        if normalized_trait in entry.traits
    )


def character_trait_map(
    entries: Iterable[CharacterTraitEntry] | None = None,
) -> dict[str, CharacterTraitEntry]:
    result: dict[str, CharacterTraitEntry] = {}
    for entry in entries or load_character_trait_catalog().entries:
        for name in (entry.name, *entry.aliases):
            normalized = normalize_character_trait_name(name)
            if normalized:
                result[normalized] = entry
    return result


def traits_for_character_name(
    name: str,
    entries: Iterable[CharacterTraitEntry] | None = None,
) -> tuple[str, ...]:
    normalized_name = normalize_character_trait_name(name)
    traits: set[str] = set()
    for entry in entries or load_character_trait_catalog().entries:
        if any(normalize_character_trait_name(item) == normalized_name for item in (entry.name, *entry.aliases)):
            traits.update(entry.traits)
    return tuple(sorted(traits))


def character_trait_catalog_to_dict(
    entries: Iterable[CharacterTraitEntry] | None = None,
) -> dict[str, Any]:
    return CharacterTraitCatalog(
        entries=tuple(entries or load_character_trait_catalog().entries)
    ).to_dict()


def normalize_character_trait_name(value: Any) -> str:
    text = str(value or "").strip().casefold()
    text = re.sub(r"[_\W]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _fetch_hoyowiki_trait_page(entry_page_id: str, language: str) -> dict[str, Any]:
    return fetch_hoyowiki_entry_page(entry_page_id, language=language)


def _iter_custom_entry_attrs(page: dict[str, Any]) -> Iterable[dict[str, str]]:
    for module in page.get("modules") or []:
        if not isinstance(module, dict):
            continue
        for component in module.get("components") or []:
            if not isinstance(component, dict):
                continue
            data = component.get("data")
            if not data:
                continue
            data = _component_html_payload(data)
            for match in re.finditer(
                r"<custom-entry\b([^>]*)>",
                html.unescape(str(data)),
                flags=re.IGNORECASE,
            ):
                yield _parse_html_attrs(match.group(1))


def _component_html_payload(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value
    if isinstance(parsed, dict) and "data" in parsed:
        return parsed["data"]
    return value


def _parse_html_attrs(value: str) -> dict[str, str]:
    return {
        str(key).lower(): html.unescape(str(raw_value))
        for key, raw_value in re.findall(r'([a-zA-Z_:-]+)=["\']([^"\']*)["\']', value)
    }


def _hexerei_detail_html(page: dict[str, Any]) -> str:
    best = ""
    for module in page.get("modules") or []:
        if not isinstance(module, dict):
            continue
        for component in module.get("components") or []:
            if not isinstance(component, dict):
                continue
            data = _component_html_payload(component.get("data"))
            if not isinstance(data, str):
                continue
            payload = html.unescape(data)
            if "<custom-entry" in payload and "menuid" in payload:
                if str(component.get("component_id") or "") == "customize":
                    return payload
                best = best or payload
    return best


def _iter_table_rows(raw_html: str) -> Iterable[str]:
    yield from re.findall(r"<tr\b[^>]*>(.*?)</tr>", raw_html, flags=re.IGNORECASE | re.DOTALL)


def _first_character_custom_entry_attrs(row_html: str) -> dict[str, str]:
    for match in re.finditer(r"<custom-entry\b([^>]*)>", row_html, flags=re.IGNORECASE):
        attrs = _parse_html_attrs(match.group(1))
        if str(attrs.get("menuid") or attrs.get("menu_id") or "") == "2":
            return attrs
    return {}


def _paragraph_texts(row_html: str) -> list[str]:
    result: list[str] = []
    for match in re.finditer(r"<p\b[^>]*>(.*?)</p>", row_html, flags=re.IGNORECASE | re.DOTALL):
        text = _clean_html_text(match.group(1))
        if text:
            result.append(text)
    return result


def _clean_html_text(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", str(value or ""), flags=re.IGNORECASE)
    text = re.sub(r"</(?:span|strong|em|a)>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def _classify_hexerei_section_heading(text: str, language: str) -> int | None:
    source = str(text or "").strip()
    if not source:
        return None
    lowered = source.casefold()
    lang = normalize_hoyowiki_language(language)
    if lang == DEFAULT_HOYOWIKI_LANGUAGE:
        if "(passive talent)" in lowered:
            return 0
        match = re.search(r"\(constellation\s+([1-6])\)", lowered)
        if match:
            return int(match.group(1))
        return None
    if lang == "ru-ru":
        if "(пассивный талант)" in lowered:
            return 0
        match = re.search(r"\(созвездие\s+([1-6])\)", lowered)
        if match:
            return int(match.group(1))
    return None


def _hexerei_section_marker(
    text: str,
    language: str,
) -> tuple[str, int, str] | None:
    source = str(text or "").strip()
    if not source:
        return None
    lang = normalize_hoyowiki_language(language)
    lowered = source.casefold()
    if lang == DEFAULT_HOYOWIKI_LANGUAGE:
        passive = re.match(r"^(.*?)\s*\(Passive Talent\)\s*(.*)$", source, flags=re.IGNORECASE | re.DOTALL)
        if passive:
            return passive.group(1).strip(), 0, passive.group(2).strip()
        constellation = re.match(r"^(.*?)\s*\(Constellation\s+([1-6])\)\s*(.*)$", source, flags=re.IGNORECASE | re.DOTALL)
        if constellation:
            return constellation.group(1).strip(), int(constellation.group(2)), constellation.group(3).strip()
        if lowered == "activate hexerei: secret rite":
            return source, 0, ""
        match = re.match(r"constellation\s+([1-6])\s*:\s*(.*)$", source, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return f"Constellation {match.group(1)}", int(match.group(1)), match.group(2).strip()
    elif lang == "ru-ru":
        passive = re.match(r"^(.*?)\s*\(пассивный талант\)\s*(.*)$", source, flags=re.IGNORECASE | re.DOTALL)
        if passive:
            return passive.group(1).strip(), 0, passive.group(2).strip()
        constellation = re.match(r"^(.*?)\s*\(созвездие\s+([1-6])\)\s*(.*)$", source, flags=re.IGNORECASE | re.DOTALL)
        if constellation:
            return constellation.group(1).strip(), int(constellation.group(2)), constellation.group(3).strip()
    classification = _classify_hexerei_section_heading(source, lang)
    if classification is not None:
        return source, classification, ""
    return None


def _is_hexerei_section_stop(text: str, language: str) -> bool:
    source = str(text or "").strip().casefold()
    lang = normalize_hoyowiki_language(language)
    if lang == DEFAULT_HOYOWIKI_LANGUAGE:
        return source == "constellation changes"
    return False


def _hexerei_section(
    *,
    character_entry_id: str,
    character_name: str,
    icon_url: str,
    language: str,
    title: str,
    body: str,
    required_constellation: int,
    section_index: int,
) -> CharacterTraitTooltipSection:
    return CharacterTraitTooltipSection(
        trait_key=TRAIT_HEXEREI,
        character_entry_page_id=character_entry_id,
        required_constellation=int(required_constellation),
        section_index=int(section_index),
        language=normalize_hoyowiki_language(language),
        title=_clean_hexerei_section_title(title, language=language),
        body=body.strip(),
        canonical_name=character_name,
        icon_url=icon_url,
        source_entry_page_id=HOYOWIKI_HEXEREI_ENTRY_PAGE_ID,
        source_url=HOYOWIKI_HEXEREI_SOURCE_URL,
    )


def _clean_hexerei_section_title(title: str, *, language: str) -> str:
    text = str(title or "").strip()
    lang = normalize_hoyowiki_language(language)
    if lang == DEFAULT_HOYOWIKI_LANGUAGE:
        text = re.sub(r"\s*\((?:Passive Talent|Constellation\s+[1-6])\)\s*$", "", text, flags=re.IGNORECASE)
    elif lang == "ru-ru":
        text = re.sub(r"\s*\((?:пассивный талант|созвездие\s+[1-6])\)\s*$", "", text, flags=re.IGNORECASE)
    return text.strip()


def _replace_trait_entries(
    catalog: CharacterTraitCatalog,
    *,
    trait: str,
    entries: Iterable[CharacterTraitEntry],
    language: str,
    fetched_at: str,
) -> CharacterTraitCatalog:
    normalized_trait = _normalize_trait_name(trait)
    kept = [
        entry
        for entry in catalog.entries
        if normalized_trait not in set(entry.traits)
    ]
    return CharacterTraitCatalog(
        entries=_dedupe_entries((*kept, *tuple(entries))),
        tooltip_references=catalog.tooltip_references,
        language=normalize_hoyowiki_language(language),
        fetched_at=fetched_at,
        source=catalog.source,
        schema_version=catalog.schema_version,
        notes=catalog.notes,
    )


def _source_url_for_trait(trait: str) -> str:
    trait = _normalize_trait_name(trait)
    if trait == TRAIT_HEXEREI:
        return HOYOWIKI_HEXEREI_SOURCE_URL
    if trait == TRAIT_MOONSIGN:
        return HOYOWIKI_MOONSIGN_SOURCE_URL
    if trait == TRAIT_STANDARD_5_STAR:
        return HOYOWIKI_STANDARD_5_STAR_SOURCE_URL
    return ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dedupe_text(values: Iterable[str | None]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return tuple(result)


def _account_content_language() -> str:
    path = PROJECT_ROOT / "data" / "hoyolab" / "account_language.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_HOYOWIKI_LANGUAGE
    if not isinstance(data, dict):
        return DEFAULT_HOYOWIKI_LANGUAGE
    return str(data.get("contentLanguage") or DEFAULT_HOYOWIKI_LANGUAGE)


def _normalize_trait_name(value: Any) -> str:
    text = str(value or "").strip().casefold().replace("-", "_")
    text = re.sub(r"[^0-9a-z_]+", "_", text)
    return "_".join(part for part in text.split("_") if part)


def _string_mapping_items(value: Any) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, dict):
        return ()
    return tuple(
        (str(key).strip(), str(raw_value).strip())
        for key, raw_value in sorted(value.items(), key=lambda item: str(item[0]))
        if str(key).strip() and str(raw_value).strip()
    )


def _default_tooltip_reference(
    trait: str,
    *,
    language: str = DEFAULT_HOYOWIKI_LANGUAGE,
) -> CharacterTraitTooltipReference:
    if trait == TRAIT_HEXEREI:
        return CharacterTraitTooltipReference(
            trait=TRAIT_HEXEREI,
            title="Hexerei",
            source_url=HOYOWIKI_HEXEREI_SOURCE_URL,
            source_entry_page_id=HOYOWIKI_HEXEREI_ENTRY_PAGE_ID,
            language=language,
        )
    if trait == TRAIT_MOONSIGN:
        return CharacterTraitTooltipReference(
            trait=TRAIT_MOONSIGN,
            title="Moonsign",
            source_url=HOYOWIKI_MOONSIGN_SOURCE_URL,
            source_entry_page_id=HOYOWIKI_MOONSIGN_ENTRY_PAGE_ID,
            language=language,
        )
    return CharacterTraitTooltipReference(
        trait=trait,
        title=trait.replace("_", " ").title(),
        language=language,
    )


def _dedupe_entries(
    entries: Iterable[CharacterTraitEntry],
) -> tuple[CharacterTraitEntry, ...]:
    result: dict[tuple[str, str], CharacterTraitEntry] = {}
    for entry in entries:
        for trait in entry.traits:
            result.setdefault((normalize_character_trait_name(entry.name), trait), entry)
    return tuple(
        result[key]
        for key in sorted(result, key=lambda item: (item[1], result[item].name.casefold()))
    )


def _entry(
    name: str,
    trait: str,
    *,
    section: str,
    source_url: str,
    source_entry_page_id: str,
    source_character_entry_page_id: str = "",
    aliases: tuple[str, ...] = (),
) -> CharacterTraitEntry:
    return CharacterTraitEntry(
        name=name,
        traits=(_normalize_trait_name(trait),),
        aliases=aliases,
        source_url=source_url,
        source_entry_page_id=source_entry_page_id,
        source_section=section,
        source_character_entry_page_id=source_character_entry_page_id,
    )


SEEDED_MOONSIGN_CHARACTER_NAMES = (
    "Aino",
    "Columbina",
    "Flins",
    "Illuga",
    "Ineffa",
    "Jahoda",
    "Lauma",
    "Linnea",
    "Nefer",
    "Zibai",
)

SEEDED_HEXEREI_CHARACTER_NAMES = (
    "Albedo",
    "Durin",
    "Fischl",
    "Klee",
    "Mona",
    "Razor",
    "Sucrose",
    "Varka",
    "Venti",
)


SEEDED_STANDARD_5_STAR_CHARACTERS = (
    ("Traveler", "20", ("Aether", "Lumine")),
    ("Dehya", "3463", ()),
    ("Tighnari", "2265", ()),
    ("Diluc", "43", ()),
    ("Mona", "37", ()),
    ("Jean", "27", ()),
    ("Keqing", "10", ()),
    ("Qiqi", "1", ()),
)

SEEDED_CHARACTER_TRAITS = tuple(
    [
        *(
            _entry(
                name,
                TRAIT_MOONSIGN,
                section="Moonsign",
                source_url=HOYOWIKI_MOONSIGN_SOURCE_URL,
                source_entry_page_id=HOYOWIKI_MOONSIGN_ENTRY_PAGE_ID,
            )
            for name in SEEDED_MOONSIGN_CHARACTER_NAMES
        ),
        *(
            _entry(
                name,
                TRAIT_HEXEREI,
                section="Hexerei",
                source_url=HOYOWIKI_HEXEREI_SOURCE_URL,
                source_entry_page_id=HOYOWIKI_HEXEREI_ENTRY_PAGE_ID,
            )
            for name in SEEDED_HEXEREI_CHARACTER_NAMES
        ),
        *(
            _entry(
                name,
                TRAIT_STANDARD_5_STAR,
                section="Standard 5-star",
                source_url=HOYOWIKI_STANDARD_5_STAR_SOURCE_URL,
                source_entry_page_id="2952",
                source_character_entry_page_id=entry_id,
                aliases=aliases,
            )
            for name, entry_id, aliases in SEEDED_STANDARD_5_STAR_CHARACTERS
        ),
    ]
)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Refresh/read local HoYoWiki character trait reference data."
    )
    parser.add_argument(
        "--refresh-hexerei-tooltips",
        action="store_true",
        help="Fetch HoYoWiki entry 9347 and populate SQLite Hexerei tooltip sections.",
    )
    parser.add_argument(
        "--language",
        default="",
        help="Preferred localized override language, e.g. ru-ru. en-us is always refreshed.",
    )
    parser.add_argument(
        "--db-path",
        default=str(PROJECT_ROOT / "data" / "artifacts.db"),
        help="SQLite DB path to update.",
    )
    args = parser.parse_args(argv)

    if not args.refresh_hexerei_tooltips:
        parser.print_help()
        return 0

    from .artifact_db import connect_db, init_db

    with connect_db(args.db_path) as conn:
        init_db(conn)
        summary = refresh_hexerei_trait_reference(
            conn,
            language=args.language or None,
        )
        conn.commit()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
