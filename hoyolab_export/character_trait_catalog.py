from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .hoyowiki_client import DEFAULT_HOYOWIKI_LANGUAGE, fetch_hoyowiki_entry_page
from .paths import PROJECT_ROOT


CHARACTER_TRAIT_CATALOG_SCHEMA_VERSION = 1
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
class CharacterTraitCatalog:
    entries: tuple[CharacterTraitEntry, ...]
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


def _normalize_trait_name(value: Any) -> str:
    text = str(value or "").strip().casefold().replace("-", "_")
    text = re.sub(r"[^0-9a-z_]+", "_", text)
    return "_".join(part for part in text.split("_") if part)


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
