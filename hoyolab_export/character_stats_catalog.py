from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .hoyowiki_client import (
    DEFAULT_HOYOWIKI_LANGUAGE,
    fetch_hoyowiki_entry_page,
    find_first_hoyowiki_component,
    normalize_hoyowiki_language,
    parse_hoyowiki_component_data,
)
from .paths import PROJECT_ROOT


CHARACTER_BASE_STATS_CACHE_PATH = (
    PROJECT_ROOT / "data" / "cache" / "hoyowiki" / "character_stats_catalog.json"
)
CHARACTER_BASE_STATS_CACHE_SCHEMA_VERSION = 1
CHARACTER_BASE_STATS_PARSER_VERSION = 1
CHARACTER_ASCENSION_COMPONENT_ID = "ascension"

DEFAULT_BASE_STAT_ASSUMPTIONS = {
    "crit_rate": "5%",
    "crit_damage": "50%",
    "energy_recharge": "100%",
    "other_special_stats": "0",
}

WARNING_MISSING_ASCENSION_COMPONENT = "missing_ascension_component"
WARNING_MALFORMED_ASCENSION_COMPONENT = "malformed_ascension_component"
WARNING_NO_ASCENSION_ROWS = "no_ascension_rows"


@dataclass(frozen=True, slots=True)
class StatValuePair:
    before: str | None = None
    after: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "before": self.before,
            "after": self.after,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "StatValuePair":
        if not isinstance(data, dict):
            return cls()
        return cls(
            before=_optional_string(data.get("before")),
            after=_optional_string(data.get("after")),
        )


@dataclass(frozen=True, slots=True)
class CharacterBaseStatRow:
    level_key: str
    base_hp: StatValuePair = field(default_factory=StatValuePair)
    base_atk: StatValuePair = field(default_factory=StatValuePair)
    base_def: StatValuePair = field(default_factory=StatValuePair)
    ascension_bonus_stat_type: str = ""
    ascension_bonus: StatValuePair = field(default_factory=StatValuePair)
    source_headers: tuple[str, ...] = ()
    raw_combat_rows: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "level_key": self.level_key,
            "base_hp": self.base_hp.to_dict(),
            "base_atk": self.base_atk.to_dict(),
            "base_def": self.base_def.to_dict(),
            "ascension_bonus_stat_type": self.ascension_bonus_stat_type,
            "ascension_bonus": self.ascension_bonus.to_dict(),
            "source_headers": list(self.source_headers),
            "raw_combat_rows": list(self.raw_combat_rows),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CharacterBaseStatRow":
        return cls(
            level_key=str(data.get("level_key") or ""),
            base_hp=StatValuePair.from_dict(data.get("base_hp")),
            base_atk=StatValuePair.from_dict(data.get("base_atk")),
            base_def=StatValuePair.from_dict(data.get("base_def")),
            ascension_bonus_stat_type=str(data.get("ascension_bonus_stat_type") or ""),
            ascension_bonus=StatValuePair.from_dict(data.get("ascension_bonus")),
            source_headers=tuple(
                str(value)
                for value in data.get("source_headers") or []
                if str(value or "").strip()
            ),
            raw_combat_rows=tuple(
                dict(item)
                for item in data.get("raw_combat_rows") or []
                if isinstance(item, dict)
            ),
        )


@dataclass(frozen=True, slots=True)
class CharacterBaseStatsEntry:
    entry_page_id: str
    name: str
    lang: str
    rows: tuple[CharacterBaseStatRow, ...] = ()
    source_component_id: str = CHARACTER_ASCENSION_COMPONENT_ID
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_page_id": self.entry_page_id,
            "name": self.name,
            "lang": self.lang,
            "source_component_id": self.source_component_id,
            "warnings": list(self.warnings),
            "rows": [row.to_dict() for row in self.rows],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CharacterBaseStatsEntry":
        return cls(
            entry_page_id=str(data.get("entry_page_id") or ""),
            name=str(data.get("name") or ""),
            lang=normalize_hoyowiki_language(data.get("lang")),
            source_component_id=str(
                data.get("source_component_id") or CHARACTER_ASCENSION_COMPONENT_ID
            ),
            warnings=tuple(str(item) for item in data.get("warnings") or []),
            rows=tuple(
                CharacterBaseStatRow.from_dict(item)
                for item in data.get("rows") or []
                if isinstance(item, dict)
            ),
        )


@dataclass(frozen=True, slots=True)
class CharacterBaseStatsCatalog:
    entries: tuple[CharacterBaseStatsEntry, ...]
    lang: str = DEFAULT_HOYOWIKI_LANGUAGE
    fetched_at: str = ""
    schema_version: int = CHARACTER_BASE_STATS_CACHE_SCHEMA_VERSION
    parser_version: int = CHARACTER_BASE_STATS_PARSER_VERSION
    source: str = "hoyowiki"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "parser_version": self.parser_version,
            "source": self.source,
            "lang": self.lang,
            "fetched_at": self.fetched_at,
            "default_base_stat_assumptions": dict(DEFAULT_BASE_STAT_ASSUMPTIONS),
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CharacterBaseStatsCatalog":
        return cls(
            schema_version=int(
                data.get("schema_version") or CHARACTER_BASE_STATS_CACHE_SCHEMA_VERSION
            ),
            parser_version=int(
                data.get("parser_version") or CHARACTER_BASE_STATS_PARSER_VERSION
            ),
            source=str(data.get("source") or "hoyowiki"),
            lang=normalize_hoyowiki_language(data.get("lang")),
            fetched_at=str(data.get("fetched_at") or ""),
            entries=tuple(
                CharacterBaseStatsEntry.from_dict(item)
                for item in data.get("entries") or []
                if isinstance(item, dict)
            ),
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_character_base_stats_page(
    page: dict[str, Any],
    *,
    entry_page_id: str | int | None = None,
    language: str = DEFAULT_HOYOWIKI_LANGUAGE,
) -> CharacterBaseStatsEntry:
    lang = normalize_hoyowiki_language(language)
    warnings: list[str] = []
    rows: list[CharacterBaseStatRow] = []

    component = find_first_hoyowiki_component(page, CHARACTER_ASCENSION_COMPONENT_ID)
    if component is None:
        warnings.append(WARNING_MISSING_ASCENSION_COMPONENT)
    else:
        parsed = parse_hoyowiki_component_data(component.get("data"))
        if not isinstance(parsed, dict):
            warnings.append(WARNING_MALFORMED_ASCENSION_COMPONENT)
        else:
            rows = _parse_ascension_rows(parsed)
            if not rows:
                warnings.append(WARNING_NO_ASCENSION_ROWS)

    return CharacterBaseStatsEntry(
        entry_page_id=str(entry_page_id or page.get("entry_page_id") or "").strip(),
        name=str(page.get("name") or "").strip(),
        lang=lang,
        rows=tuple(rows),
        warnings=tuple(warnings),
    )


def fetch_character_base_stats_entry(
    entry_page_id: str | int,
    *,
    language: str = DEFAULT_HOYOWIKI_LANGUAGE,
) -> CharacterBaseStatsEntry:
    page = fetch_hoyowiki_entry_page(entry_page_id, language=language)
    return parse_character_base_stats_page(
        page,
        entry_page_id=entry_page_id,
        language=language,
    )


def build_character_base_stats_catalog(
    entries: list[CharacterBaseStatsEntry] | tuple[CharacterBaseStatsEntry, ...],
    *,
    language: str = DEFAULT_HOYOWIKI_LANGUAGE,
    fetched_at: str | None = None,
) -> CharacterBaseStatsCatalog:
    return CharacterBaseStatsCatalog(
        entries=tuple(entries),
        lang=normalize_hoyowiki_language(language),
        fetched_at=fetched_at or utc_now(),
    )


def build_character_base_stats_catalog_from_entry_page_ids(
    entry_page_ids: list[str | int] | tuple[str | int, ...],
    *,
    language: str = DEFAULT_HOYOWIKI_LANGUAGE,
) -> CharacterBaseStatsCatalog:
    entries = [
        fetch_character_base_stats_entry(entry_page_id, language=language)
        for entry_page_id in entry_page_ids
    ]
    return build_character_base_stats_catalog(entries, language=language)


def read_character_base_stats_cache(
    path: str | Path = CHARACTER_BASE_STATS_CACHE_PATH,
) -> CharacterBaseStatsCatalog | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return CharacterBaseStatsCatalog.from_dict(data)


def write_character_base_stats_cache(
    catalog: CharacterBaseStatsCatalog,
    path: str | Path = CHARACTER_BASE_STATS_CACHE_PATH,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(catalog.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _parse_ascension_rows(data: dict[str, Any]) -> list[CharacterBaseStatRow]:
    items = data.get("list") or []
    if not isinstance(items, list):
        return []

    rows: list[CharacterBaseStatRow] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = _parse_ascension_row(item)
        if row is not None:
            rows.append(row)
    return rows


def _parse_ascension_row(item: dict[str, Any]) -> CharacterBaseStatRow | None:
    level_key = _clean_text(item.get("key"))
    combat_list = item.get("combatList") or []
    if not level_key or not isinstance(combat_list, list):
        return None

    base_hp = StatValuePair()
    base_atk = StatValuePair()
    base_def = StatValuePair()
    ascension_bonus_stat_type = ""
    ascension_bonus = StatValuePair()
    source_headers: tuple[str, ...] = ()

    for combat_row in combat_list:
        if not isinstance(combat_row, dict):
            continue

        key = _clean_text(combat_row.get("key"))
        values = combat_row.get("values") or []
        if not isinstance(values, list):
            values = []

        if not key:
            source_headers = tuple(
                value
                for value in (_clean_text(item) for item in values)
                if value
            )
            continue

        value_pair = _value_pair_from_values(values)
        normalized_key = _normalize_stat_key(key)

        if normalized_key == "base_hp":
            base_hp = value_pair
        elif normalized_key == "base_atk":
            base_atk = value_pair
        elif normalized_key == "base_def":
            base_def = value_pair
        elif not ascension_bonus_stat_type:
            ascension_bonus_stat_type = key
            ascension_bonus = value_pair

    return CharacterBaseStatRow(
        level_key=level_key,
        base_hp=base_hp,
        base_atk=base_atk,
        base_def=base_def,
        ascension_bonus_stat_type=ascension_bonus_stat_type,
        ascension_bonus=ascension_bonus,
        source_headers=source_headers,
        raw_combat_rows=_raw_combat_rows(combat_list),
    )


def _raw_combat_rows(combat_list: list[Any]) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for item in combat_list:
        if not isinstance(item, dict):
            continue
        values = item.get("values") or []
        rows.append(
            {
                "key": _clean_text(item.get("key")),
                "values": _clean_values(values) if isinstance(values, list) else [],
            }
        )
    return tuple(rows)


def _value_pair_from_values(values: list[Any]) -> StatValuePair:
    return StatValuePair(
        before=_optional_string(values[0]) if len(values) >= 1 else None,
        after=_optional_string(values[1]) if len(values) >= 2 else None,
    )


def _optional_string(value: Any) -> str | None:
    text = _clean_text(value)
    if not text or text == "-":
        return None
    return text


def _clean_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _clean_values(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _clean_text(value)
        if text:
            result.append(text)
    return result


def _normalize_stat_key(value: str) -> str:
    text = _clean_text(value).casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    aliases = {
        "base hp": "base_hp",
        "base atk": "base_atk",
        "base def": "base_def",
    }
    return aliases.get(text, text.replace(" ", "_"))
