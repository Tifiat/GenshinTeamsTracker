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
    fetch_hoyowiki_entry_page_list,
    find_first_hoyowiki_component,
    normalize_hoyowiki_language,
    parse_hoyowiki_component_data,
)
from .paths import PROJECT_ROOT


WEAPON_STATS_CACHE_PATH = (
    PROJECT_ROOT / "data" / "cache" / "hoyowiki" / "weapon_stats_catalog.json"
)
WEAPON_STATS_CACHE_SCHEMA_VERSION = 1
WEAPON_STATS_PARSER_VERSION = 1
WEAPON_LIST_MENU_ID = "4"
WEAPON_ASCENSION_COMPONENT_ID = "ascension"
WEAPON_BASE_INFO_COMPONENT_ID = "baseInfo"

WEAPON_PASSIVE_HANDLING_NOTE = (
    "Weapon passive/refinement text is stored as reference data only. "
    "It is not parsed into formulas and must not be auto-applied to final stats."
)

WARNING_MISSING_ASCENSION_COMPONENT = "missing_ascension_component"
WARNING_MALFORMED_ASCENSION_COMPONENT = "malformed_ascension_component"
WARNING_NO_ASCENSION_ROWS = "no_ascension_rows"

_NON_PASSIVE_BASE_INFO_KEYS = {
    "name",
    "имя",
    "region",
    "регион",
    "source",
    "источник",
    "type",
    "тип",
    "secondary_attributes",
    "secondary_attribute",
    "дополнительные_характеристики",
    "дополнительная_характеристика",
    "version_released",
    "версия_выхода_оружия",
    "где_найти",
}


def weapon_stats_cache_path_for_language(language: str | None) -> Path:
    lang = normalize_hoyowiki_language(language)
    if lang == DEFAULT_HOYOWIKI_LANGUAGE:
        return WEAPON_STATS_CACHE_PATH
    suffix = re.sub(r"[^a-z0-9-]+", "-", lang).strip("-") or lang
    return WEAPON_STATS_CACHE_PATH.with_name(f"weapon_stats_catalog.{suffix}.json")


@dataclass(frozen=True, slots=True)
class WeaponAtkValuePair:
    before: str | None = None
    after: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "before": self.before,
            "after": self.after,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "WeaponAtkValuePair":
        if not isinstance(data, dict):
            return cls()
        return cls(
            before=_optional_string(data.get("before")),
            after=_optional_string(data.get("after")),
        )


@dataclass(frozen=True, slots=True)
class WeaponReferenceField:
    key: str
    values: tuple[str, ...] = ()
    raw_values: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "values": list(self.values),
            "raw_values": list(self.raw_values),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WeaponReferenceField":
        return cls(
            key=str(data.get("key") or ""),
            values=tuple(
                str(item)
                for item in data.get("values") or []
                if str(item or "").strip()
            ),
            raw_values=tuple(
                str(item)
                for item in data.get("raw_values") or []
                if str(item or "").strip()
            ),
        )


@dataclass(frozen=True, slots=True)
class WeaponReferenceInfo:
    weapon_type: str = ""
    secondary_attribute: str = ""
    passive_fields: tuple[WeaponReferenceField, ...] = ()
    fields: tuple[WeaponReferenceField, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "weapon_type": self.weapon_type,
            "secondary_attribute": self.secondary_attribute,
            "passive_fields": [field.to_dict() for field in self.passive_fields],
            "fields": [field.to_dict() for field in self.fields],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "WeaponReferenceInfo":
        if not isinstance(data, dict):
            return cls()
        return cls(
            weapon_type=str(data.get("weapon_type") or ""),
            secondary_attribute=str(data.get("secondary_attribute") or ""),
            passive_fields=tuple(
                WeaponReferenceField.from_dict(item)
                for item in data.get("passive_fields") or []
                if isinstance(item, dict)
            ),
            fields=tuple(
                WeaponReferenceField.from_dict(item)
                for item in data.get("fields") or []
                if isinstance(item, dict)
            ),
        )


@dataclass(frozen=True, slots=True)
class WeaponBaseStatRow:
    level_key: str
    base_atk: WeaponAtkValuePair = field(default_factory=WeaponAtkValuePair)
    secondary_stat_type: str = ""
    secondary_stat_value: str | None = None
    source_headers: tuple[str, ...] = ()
    raw_combat_rows: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "level_key": self.level_key,
            "base_atk": self.base_atk.to_dict(),
            "secondary_stat_type": self.secondary_stat_type,
            "secondary_stat_value": self.secondary_stat_value,
            "source_headers": list(self.source_headers),
            "raw_combat_rows": list(self.raw_combat_rows),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WeaponBaseStatRow":
        return cls(
            level_key=str(data.get("level_key") or ""),
            base_atk=WeaponAtkValuePair.from_dict(data.get("base_atk")),
            secondary_stat_type=str(data.get("secondary_stat_type") or ""),
            secondary_stat_value=_optional_string(data.get("secondary_stat_value")),
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
class WeaponStatsEntry:
    entry_page_id: str
    name: str
    lang: str
    rows: tuple[WeaponBaseStatRow, ...] = ()
    reference_info: WeaponReferenceInfo = field(default_factory=WeaponReferenceInfo)
    source_component_id: str = WEAPON_ASCENSION_COMPONENT_ID
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_page_id": self.entry_page_id,
            "name": self.name,
            "lang": self.lang,
            "source_component_id": self.source_component_id,
            "warnings": list(self.warnings),
            "reference_info": self.reference_info.to_dict(),
            "rows": [row.to_dict() for row in self.rows],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WeaponStatsEntry":
        return cls(
            entry_page_id=str(data.get("entry_page_id") or ""),
            name=str(data.get("name") or ""),
            lang=normalize_hoyowiki_language(data.get("lang")),
            source_component_id=str(
                data.get("source_component_id") or WEAPON_ASCENSION_COMPONENT_ID
            ),
            warnings=tuple(str(item) for item in data.get("warnings") or []),
            reference_info=WeaponReferenceInfo.from_dict(data.get("reference_info")),
            rows=tuple(
                WeaponBaseStatRow.from_dict(item)
                for item in data.get("rows") or []
                if isinstance(item, dict)
            ),
        )


@dataclass(frozen=True, slots=True)
class WeaponStatsCatalog:
    entries: tuple[WeaponStatsEntry, ...]
    lang: str = DEFAULT_HOYOWIKI_LANGUAGE
    fetched_at: str = ""
    schema_version: int = WEAPON_STATS_CACHE_SCHEMA_VERSION
    parser_version: int = WEAPON_STATS_PARSER_VERSION
    source: str = "hoyowiki"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "parser_version": self.parser_version,
            "source": self.source,
            "lang": self.lang,
            "fetched_at": self.fetched_at,
            "passive_handling": WEAPON_PASSIVE_HANDLING_NOTE,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WeaponStatsCatalog":
        return cls(
            schema_version=int(data.get("schema_version") or WEAPON_STATS_CACHE_SCHEMA_VERSION),
            parser_version=int(data.get("parser_version") or WEAPON_STATS_PARSER_VERSION),
            source=str(data.get("source") or "hoyowiki"),
            lang=normalize_hoyowiki_language(data.get("lang")),
            fetched_at=str(data.get("fetched_at") or ""),
            entries=tuple(
                WeaponStatsEntry.from_dict(item)
                for item in data.get("entries") or []
                if isinstance(item, dict)
            ),
        )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fetch_hoyowiki_weapon_list(
    *,
    language: str = DEFAULT_HOYOWIKI_LANGUAGE,
) -> list[dict[str, Any]]:
    return fetch_hoyowiki_entry_page_list(
        WEAPON_LIST_MENU_ID,
        language=language,
    )


def parse_weapon_stats_page(
    page: dict[str, Any],
    *,
    entry_page_id: str | int | None = None,
    language: str = DEFAULT_HOYOWIKI_LANGUAGE,
) -> WeaponStatsEntry:
    lang = normalize_hoyowiki_language(language)
    warnings: list[str] = []
    rows: list[WeaponBaseStatRow] = []

    component = find_first_hoyowiki_component(page, WEAPON_ASCENSION_COMPONENT_ID)
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

    return WeaponStatsEntry(
        entry_page_id=str(entry_page_id or page.get("entry_page_id") or "").strip(),
        name=str(page.get("name") or "").strip(),
        lang=lang,
        rows=tuple(rows),
        reference_info=parse_weapon_reference_info(page),
        warnings=tuple(warnings),
    )


def parse_weapon_reference_info(page: dict[str, Any]) -> WeaponReferenceInfo:
    component = find_first_hoyowiki_component(page, WEAPON_BASE_INFO_COMPONENT_ID)
    if component is None:
        return WeaponReferenceInfo()

    parsed = parse_hoyowiki_component_data(component.get("data"))
    if not isinstance(parsed, dict):
        return WeaponReferenceInfo()

    fields = _parse_base_info_fields(parsed)
    weapon_type = ""
    secondary_attribute = ""
    passive_fields: list[WeaponReferenceField] = []

    for field_item in fields:
        normalized_key = _normalize_key(field_item.key)
        if normalized_key == "type" and field_item.values:
            weapon_type = field_item.values[0]
        elif normalized_key in {"secondary_attribute", "secondary_attributes"} and field_item.values:
            secondary_attribute = field_item.values[0]
        elif normalized_key not in _NON_PASSIVE_BASE_INFO_KEYS and field_item.values:
            passive_fields.append(field_item)

    return WeaponReferenceInfo(
        weapon_type=weapon_type,
        secondary_attribute=secondary_attribute,
        passive_fields=tuple(passive_fields),
        fields=tuple(fields),
    )


def fetch_weapon_stats_entry(
    entry_page_id: str | int,
    *,
    language: str = DEFAULT_HOYOWIKI_LANGUAGE,
) -> WeaponStatsEntry:
    page = fetch_hoyowiki_entry_page(entry_page_id, language=language)
    return parse_weapon_stats_page(
        page,
        entry_page_id=entry_page_id,
        language=language,
    )


def build_weapon_stats_catalog(
    entries: list[WeaponStatsEntry] | tuple[WeaponStatsEntry, ...],
    *,
    language: str = DEFAULT_HOYOWIKI_LANGUAGE,
    fetched_at: str | None = None,
) -> WeaponStatsCatalog:
    return WeaponStatsCatalog(
        entries=tuple(entries),
        lang=normalize_hoyowiki_language(language),
        fetched_at=fetched_at or utc_now(),
    )


def build_weapon_stats_catalog_from_entry_page_ids(
    entry_page_ids: list[str | int] | tuple[str | int, ...],
    *,
    language: str = DEFAULT_HOYOWIKI_LANGUAGE,
) -> WeaponStatsCatalog:
    entries = [
        fetch_weapon_stats_entry(entry_page_id, language=language)
        for entry_page_id in entry_page_ids
    ]
    return build_weapon_stats_catalog(entries, language=language)


def read_weapon_stats_cache(
    path: str | Path = WEAPON_STATS_CACHE_PATH,
) -> WeaponStatsCatalog | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return WeaponStatsCatalog.from_dict(data)


def write_weapon_stats_cache(
    catalog: WeaponStatsCatalog,
    path: str | Path = WEAPON_STATS_CACHE_PATH,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(catalog.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _parse_ascension_rows(data: dict[str, Any]) -> list[WeaponBaseStatRow]:
    items = data.get("list") or []
    if not isinstance(items, list):
        return []

    rows: list[WeaponBaseStatRow] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = _parse_ascension_row(item)
        if row is not None:
            rows.append(row)
    return rows


def _parse_ascension_row(item: dict[str, Any]) -> WeaponBaseStatRow | None:
    level_key = _clean_text(item.get("key"))
    combat_list = item.get("combatList") or []
    if not level_key or not isinstance(combat_list, list):
        return None

    source_headers: tuple[str, ...] = ()
    stat_values: list[str] = []

    for combat_row in combat_list:
        if not isinstance(combat_row, dict):
            continue
        values = combat_row.get("values") or []
        if not isinstance(values, list):
            continue

        clean_values = _clean_values(values)
        if not clean_values:
            continue

        if _looks_like_weapon_header(clean_values):
            source_headers = tuple(clean_values)
            continue

        if not stat_values:
            stat_values = clean_values

    if not source_headers and not stat_values:
        return None

    secondary_stat_type = source_headers[2] if len(source_headers) >= 3 else ""
    secondary_stat_value = (
        _optional_string(stat_values[2])
        if len(stat_values) >= 3
        else None
    )

    return WeaponBaseStatRow(
        level_key=level_key,
        base_atk=WeaponAtkValuePair(
            before=_optional_string(stat_values[0]) if len(stat_values) >= 1 else None,
            after=_optional_string(stat_values[1]) if len(stat_values) >= 2 else None,
        ),
        secondary_stat_type=secondary_stat_type,
        secondary_stat_value=secondary_stat_value,
        source_headers=source_headers,
        raw_combat_rows=_raw_combat_rows(combat_list),
    )


def _parse_base_info_fields(data: dict[str, Any]) -> list[WeaponReferenceField]:
    items = data.get("list") or []
    if not isinstance(items, list):
        return []

    fields: list[WeaponReferenceField] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        key = _clean_text(item.get("key"))
        values = item.get("value") or []
        if not key or not isinstance(values, list):
            continue

        fields.append(
            WeaponReferenceField(
                key=key,
                values=tuple(_clean_values(values)),
                raw_values=tuple(str(value) for value in values if str(value or "").strip()),
            )
        )

    return fields


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


def _looks_like_weapon_header(values: list[str]) -> bool:
    if len(values) < 2:
        return False
    normalized = [_normalize_key(value) for value in values]
    return (
        normalized[0] in {"atk_before_ascension", "base_atk_before_ascension"}
        and normalized[1] in {"atk_after_ascension", "base_atk_after_ascension"}
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


def _normalize_key(value: str) -> str:
    text = _clean_text(value).casefold()
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace(" ", "_")
