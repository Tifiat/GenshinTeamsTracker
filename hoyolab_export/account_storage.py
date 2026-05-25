from __future__ import annotations

import argparse
import json
import re
import sqlite3
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import quote, urlsplit, urlunsplit

from .account_stat_sheet import (
    PROPERTY_WEAPON_BASE_ATK,
    extract_account_character_base_values,
    parse_account_character_stat_sheet,
)
from .artifact_fingerprint import normalize_stat_value_for_fingerprint, stable_hash
from .catalog_mapping_report import (
    DEFAULT_ACCOUNT_CHARACTERS_PATH,
    DEFAULT_ACCOUNT_WEAPONS_PATH,
)
from .character_ascension_bonus import extract_character_ascension_bonus_by_base_stats
from .character_identity import (
    CharacterIdentityRecord,
    identity_by_character_id,
    init_character_identity_storage,
    sync_character_identity_from_account_rows,
)
from .character_region_catalog import load_character_region_catalog
from .character_stats_catalog import (
    CHARACTER_BASE_STATS_CACHE_PATH,
    CharacterBaseStatsCatalog,
    CharacterBaseStatsEntry,
    read_character_base_stats_cache,
)
from .crop_manifest import IGNORED_CHARACTER_IDS, icon_key
from .paths import HOYOLAB_DATA_DIR, PROJECT_ROOT
from .paths import HOYOLAB_CHARACTER_ASSETS_DIR
from .character_trait_catalog import (
    load_character_trait_catalog,
    rebuild_character_trait_reference_from_catalog,
)


DEFAULT_ACCOUNT_CHARACTER_DETAILS_PATH = HOYOLAB_DATA_DIR / "account_character_details.json"
DEFAULT_CROP_MANIFEST_PATH = HOYOLAB_DATA_DIR / "crop_manifest.json"
DEFAULT_ACCOUNT_LANGUAGE_PATH = HOYOLAB_DATA_DIR / "account_language.json"
DEFAULT_ACCOUNT_DB_PATH = PROJECT_ROOT / "data" / "artifacts.db"

ACCOUNT_STORAGE_SCHEMA_VERSION = 3
DEFAULT_SIDE_ICON_CACHE_DIR = HOYOLAB_CHARACTER_ASSETS_DIR / "side_icons"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0 Safari/537.36"
)

WARNING_CHARACTER_DETAIL_MISSING = "account_character_detail_missing"
WARNING_ASCENSION_ENTRY_MISSING = "account_character_ascension_entry_missing"
WARNING_CHARACTER_SOURCE_EMPTY_PRESERVED = "account_character_source_empty_preserved"
WARNING_CHARACTER_SIDE_ICON_CACHE_FAILED = "account_character_side_icon_cache_failed"
WARNING_CHARACTER_TALENT_SKILL_ID_MISSING = "account_character_talent_skill_id_missing"
WARNING_WEAPON_DETAIL_MISSING = "account_weapon_detail_missing"
WARNING_WEAPON_IDENTITY_NO_INSTANCE_ID = "account_weapon_identity_no_source_instance_id"
WARNING_WEAPON_OBSERVED_STACK_NOT_FULL_INVENTORY = (
    "account_weapon_observed_stack_not_full_inventory"
)
WARNING_WEAPON_OBSERVATIONS_EMPTY_PRESERVED = (
    "account_weapon_observations_empty_preserved"
)
_ACCOUNT_STORAGE_HIDDEN_ASCENSION_WARNINGS = {
    "character_ascension_phase_assumed",
    "ascension_phase_unknown",
}

_ENTRY_ID_RE = re.compile(r"/entry/(\d+)")


@dataclass(frozen=True, slots=True)
class AccountStorageSyncSummary:
    characters_seen: int = 0
    characters_upserted: int = 0
    talents_seen: int = 0
    talents_upserted: int = 0
    weapon_observations_seen: int = 0
    weapon_stacks_seen: int = 0
    weapon_stacks_upserted: int = 0
    warnings: tuple[str, ...] = ()
    schema_version: int = ACCOUNT_STORAGE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "characters_seen": self.characters_seen,
            "characters_upserted": self.characters_upserted,
            "talents_seen": self.talents_seen,
            "talents_upserted": self.talents_upserted,
            "weapon_observations_seen": self.weapon_observations_seen,
            "weapon_stacks_seen": self.weapon_stacks_seen,
            "weapon_stacks_upserted": self.weapon_stacks_upserted,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class AccountCharacterTalentRecord:
    character_id: str
    skill_id: str
    skill_type: int | None = None
    name: str = ""
    level: int | None = None
    icon_url: str = ""
    is_unlock: bool | None = None
    warnings: tuple[str, ...] = ()
    source_metadata: dict[str, Any] | None = None
    first_seen_at: str = ""
    last_seen_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "skill_id": self.skill_id,
            "skill_type": self.skill_type,
            "name": self.name,
            "level": self.level,
            "icon_url": self.icon_url,
            "is_unlock": self.is_unlock,
            "warnings": list(self.warnings),
            "source_metadata": dict(self.source_metadata or {}),
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
        }


@dataclass(frozen=True, slots=True)
class AccountSideIconCacheResult:
    path: str = ""
    reused_existing: bool = False
    downloaded: bool = False
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "reused_existing": self.reused_existing,
            "downloaded": self.downloaded,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class AccountCharacterRuntimeRecord:
    character_id: str
    name: str
    element: str = ""
    rarity: int | None = None
    level: int | None = None
    constellation: int | None = None
    weapon_type: int | None = None
    weapon_type_name: str = ""
    icon_url: str = ""
    side_icon_url: str = ""
    portrait_path: str = ""
    side_icon_path: str = ""
    region_key: str = ""
    region_name: str = ""
    hoyowiki_entry_id: str = ""
    traits: tuple[str, ...] = ()
    is_standard_5_star: bool = False
    base_hp: float | None = None
    base_atk: float | None = None
    base_def: float | None = None
    ascension_bonus_stat_type: str = ""
    ascension_bonus_value: float | None = None
    warnings: tuple[str, ...] = ()
    talents: tuple[AccountCharacterTalentRecord, ...] = ()
    source_metadata: dict[str, Any] | None = None
    first_seen_at: str = ""
    last_seen_at: str = ""
    source_status: str = "sqlite_account_characters"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_key": self.character_id,
            "id": self.character_id,
            "name": self.name,
            "element": self.element,
            "rarity": self.rarity,
            "level": self.level,
            "constellation": self.constellation,
            "weapon_type": self.weapon_type,
            "weapon_type_name": self.weapon_type_name,
            "icon_url": self.icon_url,
            "side_icon_url": self.side_icon_url,
            "portrait_path": self.portrait_path,
            "side_icon_path": self.side_icon_path,
            "region_key": self.region_key,
            "region_name": self.region_name,
            "hoyowiki_entry_id": self.hoyowiki_entry_id,
            "traits": list(self.traits),
            "is_standard_5_star": self.is_standard_5_star,
            "base_hp": self.base_hp,
            "base_atk": self.base_atk,
            "base_def": self.base_def,
            "ascension_bonus_stat_type": self.ascension_bonus_stat_type,
            "ascension_bonus_value": self.ascension_bonus_value,
            "warnings": list(self.warnings),
            "talents": [talent.to_dict() for talent in self.talents],
            "source_metadata": dict(self.source_metadata or {}),
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "source_status": self.source_status,
        }

    def to_team_builder_character_ref(self) -> dict[str, Any]:
        return {
            "id": self.character_id,
            "name": self.name,
            "level": self.level,
            "element": self.element,
            "rarity": self.rarity,
            "constellation": self.constellation,
            "weapon_type": self.weapon_type,
            "weapon_type_name": self.weapon_type_name,
            "icon_url": self.icon_url,
            "side_icon_url": self.side_icon_url,
            "portrait_path": self.portrait_path,
            "side_icon_path": self.side_icon_path,
            "region_key": self.region_key,
            "region_name": self.region_name,
            "hoyowiki_entry_id": self.hoyowiki_entry_id,
            "traits": list(self.traits),
            "is_standard_5_star": self.is_standard_5_star,
            "base_hp": self.base_hp,
            "base_atk": self.base_atk,
            "base_def": self.base_def,
            "ascension_bonus_stat_type": self.ascension_bonus_stat_type,
            "ascension_bonus_value": self.ascension_bonus_value,
            "talents": [talent.to_dict() for talent in self.talents],
            "source": "account_sqlite",
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class AccountWeaponObservedStack:
    id: int | None
    weapon_fingerprint: str
    weapon_id: str
    name: str
    weapon_type: int | None = None
    weapon_type_name: str = ""
    rarity: int | None = None
    level: int | None = None
    refinement: int | None = None
    promote_level: int | None = None
    base_atk: float | None = None
    base_atk_raw: str = ""
    secondary_property_type: int | None = None
    secondary_stat_value: float | None = None
    secondary_stat_value_raw: str = ""
    description: str = ""
    icon_url: str = ""
    icon_path: str = ""
    known_count: int = 1
    warnings: tuple[str, ...] = ()
    source_metadata: dict[str, Any] | None = None
    first_seen_at: str = ""
    last_seen_at: str = ""
    source_status: str = "sqlite_account_weapon_observed_stack"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "weapon_fingerprint": self.weapon_fingerprint,
            "weapon_id": self.weapon_id,
            "name": self.name,
            "weapon_type": self.weapon_type,
            "weapon_type_name": self.weapon_type_name,
            "type_name": self.weapon_type_name,
            "rarity": self.rarity,
            "level": self.level,
            "refinement": self.refinement,
            "promote_level": self.promote_level,
            "base_atk": self.base_atk,
            "base_atk_raw": self.base_atk_raw,
            "secondary_property_type": self.secondary_property_type,
            "secondary_stat_value": self.secondary_stat_value,
            "secondary_stat_value_raw": self.secondary_stat_value_raw,
            "description": self.description,
            "icon_url": self.icon_url,
            "icon_path": self.icon_path,
            "known_count": self.known_count,
            "warnings": list(self.warnings),
            "source_metadata": dict(self.source_metadata or {}),
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "source_status": self.source_status,
        }

    def to_team_builder_weapon_ref(self) -> dict[str, Any]:
        source_metadata = dict(self.source_metadata or {})
        return {
            "id": self.weapon_id,
            "name": self.name,
            "level": self.level,
            "promote_level": self.promote_level,
            "rarity": self.rarity,
            "refinement": self.refinement,
            "weapon_type": self.weapon_type,
            "type_name": self.weapon_type_name,
            "weapon_type_name": self.weapon_type_name,
            "source_key": self.weapon_fingerprint,
            "source": "account_sqlite_observed_weapon_stack",
            "known_count": self.known_count,
            "base_atk": self.base_atk,
            "base_atk_raw": self.base_atk_raw,
            "secondary_property_type": self.secondary_property_type,
            "secondary_stat_value": self.secondary_stat_value,
            "secondary_stat_value_raw": self.secondary_stat_value_raw,
            "weapon_catalog_entry_page_id": source_metadata.get("hoyowiki_weapon_entry_id", ""),
            "description": self.description,
            "icon_url": self.icon_url,
            "icon_path": self.icon_path,
            "warnings": list(self.warnings),
            "source_metadata": source_metadata,
        }


@dataclass(frozen=True, slots=True)
class _WeaponObservation:
    observation_key: str
    weapon_fingerprint: str
    weapon_id: int | None
    name: str
    weapon_type: int | None
    weapon_type_name: str
    rarity: int | None
    level: int | None
    refinement: int | None
    promote_level: int | None
    base_atk: float | None
    base_atk_raw: str
    secondary_property_type: int | None
    secondary_stat_value: float | None
    secondary_stat_value_raw: str
    description: str
    icon_url: str
    icon_path: str
    warnings: tuple[str, ...]
    source_metadata: dict[str, Any]

    @property
    def completeness_score(self) -> int:
        fields = (
            self.weapon_id,
            self.name,
            self.weapon_type,
            self.weapon_type_name,
            self.rarity,
            self.level,
            self.refinement,
            self.promote_level,
            self.base_atk_raw,
            self.secondary_property_type,
            self.secondary_stat_value_raw,
            self.description,
            self.icon_url,
            self.icon_path,
        )
        return sum(1 for value in fields if value not in (None, ""))


@dataclass(frozen=True, slots=True)
class _WeaponIconPathMap:
    by_icon_key: Mapping[str, str]
    by_weapon_id: Mapping[str, str]


def init_account_storage(conn: sqlite3.Connection) -> None:
    """Create clean account runtime tables in the existing local SQLite DB."""

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS account_characters (
            character_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            element TEXT,
            rarity INTEGER,
            level INTEGER,
            constellation INTEGER,
            weapon_type INTEGER,
            weapon_type_name TEXT,
            icon_url TEXT,
            side_icon_url TEXT,
            portrait_path TEXT,
            side_icon_path TEXT,
            base_hp REAL,
            base_atk REAL,
            base_def REAL,
            ascension_bonus_stat_type TEXT,
            ascension_bonus_value REAL,
            source_metadata_json TEXT NOT NULL DEFAULT '{}',
            warnings_json TEXT NOT NULL DEFAULT '[]',
            first_seen_at TEXT,
            last_seen_at TEXT,
            updated_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_account_characters_name
            ON account_characters(name);

        CREATE TABLE IF NOT EXISTS account_character_talents (
            character_id INTEGER NOT NULL,
            skill_id INTEGER NOT NULL,
            skill_type INTEGER,
            name TEXT,
            level INTEGER,
            icon_url TEXT,
            is_unlock INTEGER,
            source_metadata_json TEXT NOT NULL DEFAULT '{}',
            warnings_json TEXT NOT NULL DEFAULT '[]',
            first_seen_at TEXT,
            last_seen_at TEXT,
            updated_at TEXT,

            PRIMARY KEY (character_id, skill_id),
            FOREIGN KEY (character_id) REFERENCES account_characters(character_id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_account_character_talents_character_id
            ON account_character_talents(character_id);

        CREATE TABLE IF NOT EXISTS account_weapon_observed_stacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            weapon_fingerprint TEXT NOT NULL UNIQUE,
            weapon_id INTEGER,
            name TEXT NOT NULL DEFAULT '',
            weapon_type INTEGER,
            weapon_type_name TEXT,
            rarity INTEGER,
            level INTEGER,
            refinement INTEGER,
            promote_level INTEGER,
            base_atk REAL,
            base_atk_raw TEXT,
            secondary_property_type INTEGER,
            secondary_stat_value REAL,
            secondary_stat_value_raw TEXT,
            description TEXT,
            icon_url TEXT,
            icon_path TEXT,
            known_count INTEGER NOT NULL DEFAULT 1,
            first_seen_at TEXT,
            last_seen_at TEXT,
            source_metadata_json TEXT NOT NULL DEFAULT '{}',
            warnings_json TEXT NOT NULL DEFAULT '[]'
        );

        CREATE INDEX IF NOT EXISTS idx_account_weapon_observed_stacks_weapon_id
            ON account_weapon_observed_stacks(weapon_id);
        CREATE INDEX IF NOT EXISTS idx_account_weapon_observed_stacks_name
            ON account_weapon_observed_stacks(name);
        """
    )
    _ensure_account_character_columns(conn)
    _ensure_account_character_talent_columns(conn)
    _ensure_observed_weapon_columns(conn)
    init_character_identity_storage(conn)


def sync_account_storage_from_local_files(
    *,
    db_path: str | Path = DEFAULT_ACCOUNT_DB_PATH,
    account_characters_path: str | Path = DEFAULT_ACCOUNT_CHARACTERS_PATH,
    account_weapons_path: str | Path = DEFAULT_ACCOUNT_WEAPONS_PATH,
    account_character_details_path: str | Path = DEFAULT_ACCOUNT_CHARACTER_DETAILS_PATH,
    crop_manifest_path: str | Path = DEFAULT_CROP_MANIFEST_PATH,
    account_language_path: str | Path = DEFAULT_ACCOUNT_LANGUAGE_PATH,
    character_stats_catalog_path: str | Path = CHARACTER_BASE_STATS_CACHE_PATH,
    side_icon_cache_dir: str | Path = DEFAULT_SIDE_ICON_CACHE_DIR,
    download_side_icons: bool = False,
) -> AccountStorageSyncSummary:
    """Populate account tables from already-local HoYoLAB/cache files.

    This command path is intentionally no-network. Raw JSON remains the
    source/cache input; SQLite stores normalized runtime rows.
    """

    from .artifact_db import connect_db, init_db

    account_details = _load_json_dict(account_character_details_path)
    crop_manifest = _load_json_dict(crop_manifest_path)
    account_language = _load_json_dict(account_language_path)
    character_catalog = read_character_base_stats_cache(character_stats_catalog_path)
    content_language = _text(account_language.get("contentLanguage")) or "en-us"
    region_entries = load_character_region_catalog(content_language, allow_network=False)
    trait_catalog = load_character_trait_catalog()

    with connect_db(db_path) as conn:
        init_db(conn)
        rebuild_character_trait_reference_from_catalog(conn, trait_catalog)
        summary = sync_account_storage_from_sources(
            conn,
            account_characters=_load_json_list(account_characters_path),
            account_weapons=_load_json_list(account_weapons_path),
            account_character_details=account_details,
            crop_manifest=crop_manifest,
            character_stats_catalog=character_catalog,
            character_region_entries=region_entries,
            character_trait_entries=trait_catalog.entries,
            side_icon_cache_dir=side_icon_cache_dir,
            side_icon_downloader=_download_url_to_file if download_side_icons else None,
        )
        conn.commit()
    return summary


def sync_account_storage_from_sources(
    conn: sqlite3.Connection,
    *,
    account_characters: list[dict[str, Any]],
    account_weapons: list[dict[str, Any]],
    account_character_details: Mapping[str, Any] | None = None,
    crop_manifest: Mapping[str, Any] | None = None,
    character_stats_catalog: CharacterBaseStatsCatalog | None = None,
    character_region_entries: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    character_trait_entries: tuple[Any, ...] = (),
    side_icon_cache_dir: str | Path = DEFAULT_SIDE_ICON_CACHE_DIR,
    side_icon_downloader: Callable[[str, Path], None] | None = None,
) -> AccountStorageSyncSummary:
    """Sync authoritative account characters and reconstructed weapon stacks."""

    init_account_storage(conn)

    details_data = _details_data(account_character_details or {})
    detail_rows = _detail_rows(details_data)
    details_by_id = _details_by_character_id(detail_rows)
    avatar_wiki = _string_map(details_data.get("avatar_wiki"))
    weapon_wiki = _string_map(details_data.get("weapon_wiki"))
    character_entries = _character_entries_by_id(character_stats_catalog)
    character_crops = _character_crops_by_id(crop_manifest or {})
    weapon_icon_paths = _weapon_icon_paths(crop_manifest or {})
    now = _utc_now()

    warnings: list[str] = []
    characters_seen = 0
    characters_upserted = 0
    talents_seen = 0
    talents_upserted = 0

    if account_characters:
        for account_character in account_characters:
            character_id = _optional_int(account_character.get("id"))
            if character_id is None:
                continue
            if character_id in IGNORED_CHARACTER_IDS:
                continue
            detail = details_by_id.get(str(character_id))
            row_warnings: list[str] = []
            if detail is None:
                row_warnings.append(WARNING_CHARACTER_DETAIL_MISSING)

            base_values = None
            ascension_bonus = None
            entry_id = ""
            if detail is not None:
                stat_sheet = parse_account_character_stat_sheet(detail)
                base_values = extract_account_character_base_values(stat_sheet)
                row_warnings.extend(base_values.warnings)

                entry_id = _entry_id_from_url(avatar_wiki.get(str(character_id)))
                entry = character_entries.get(entry_id)
                if entry is not None:
                    ascension_bonus = extract_character_ascension_bonus_by_base_stats(
                        entry,
                        account_level=_optional_int(account_character.get("level")),
                        base_hp=base_values.base_hp if base_values else None,
                        base_def=base_values.base_def if base_values else None,
                        base_atk=base_values.base_atk if base_values else None,
                    )
                    row_warnings.extend(
                        _account_storage_ascension_warnings(ascension_bonus.warnings)
                    )
                elif character_stats_catalog is not None:
                    row_warnings.append(WARNING_ASCENSION_ENTRY_MISSING)

            base = _mapping(detail.get("base")) if detail is not None else {}
            character = _merge_account_character(base, account_character)
            side_icon_url = _text(character.get("side_icon"))
            side_icon_result = cache_account_side_icon(
                character_id=character_id,
                side_icon_url=side_icon_url,
                cache_dir=side_icon_cache_dir,
                downloader=side_icon_downloader,
            )
            row_warnings.extend(side_icon_result.warnings)
            source_metadata = {
                "source": "hoyolab_account_character_list",
                "source_files": [
                    "data/hoyolab/account_characters.json",
                    "data/hoyolab/account_character_details.json",
                    "data/hoyolab/crop_manifest.json",
                ],
                "authoritative_character_source": "account_characters_json",
                "hoyowiki_character_entry_id": entry_id,
                "detail_record_present": detail is not None,
                "canonical_base_values": (
                    "hoyolab_base_properties_base_fields_with_character_atk_derived"
                ),
                "hoyolab_final_rows_are_non_canonical": True,
                "destructive_missing_character_pruning": False,
                "side_icon_cache": side_icon_result.to_dict(),
            }
            if base_values is not None:
                source_metadata["base_values"] = base_values.to_dict()
            if ascension_bonus is not None:
                source_metadata["ascension_bonus"] = (
                    _account_storage_ascension_bonus_dict(ascension_bonus)
                )

            _upsert_account_character(
                conn,
                character_id=character_id,
                character=character,
                portrait_path=character_crops.get(str(character_id), ""),
                side_icon_path=side_icon_result.path,
                base_hp=_number_or_none(base_values.base_hp if base_values else None),
                base_atk=_number_or_none(base_values.base_atk if base_values else None),
                base_def=_number_or_none(base_values.base_def if base_values else None),
                ascension_bonus_stat_type=(
                    ascension_bonus.stat_type if ascension_bonus else ""
                ),
                ascension_bonus_value=_number_or_none(
                    ascension_bonus.selected_value if ascension_bonus else None
                ),
                source_metadata=source_metadata,
                warnings=_dedupe(row_warnings),
                now=now,
            )
            characters_seen += 1
            characters_upserted += 1
            warnings.extend(row_warnings)
            if detail is not None:
                seen, upserted, talent_warnings = _sync_account_character_talents(
                    conn,
                    character_id=character_id,
                    detail=detail,
                    now=now,
                )
                talents_seen += seen
                talents_upserted += upserted
                warnings.extend(talent_warnings)
    else:
        warnings.append(WARNING_CHARACTER_SOURCE_EMPTY_PRESERVED)

    identity_rows = sync_character_identity_from_account_rows(
        conn,
        region_entries=character_region_entries,
        trait_entries=character_trait_entries,
        now=now,
    )

    observations = _weapon_observations(
        account_weapons=account_weapons,
        detail_rows=detail_rows,
        weapon_wiki=weapon_wiki,
        weapon_icon_paths=weapon_icon_paths,
    )
    observation_by_key: dict[str, _WeaponObservation] = {}
    for observation in observations:
        existing = observation_by_key.get(observation.observation_key)
        if existing is None or observation.completeness_score > existing.completeness_score:
            observation_by_key[observation.observation_key] = observation

    grouped: dict[str, list[_WeaponObservation]] = {}
    for observation in observation_by_key.values():
        grouped.setdefault(observation.weapon_fingerprint, []).append(observation)

    weapon_stacks_upserted = 0
    if grouped:
        for fingerprint, stack_observations in grouped.items():
            chosen = max(
                stack_observations,
                key=lambda item: (item.completeness_score, item.observation_key),
            )
            observed_character_ids = sorted(
                {
                    _text(item.source_metadata.get("equipped_character_id"))
                    for item in stack_observations
                    if _text(item.source_metadata.get("equipped_character_id"))
                }
            )
            source_metadata = dict(chosen.source_metadata)
            source_metadata.update(
                {
                    "source": "hoyolab_observed_weapon_stack",
                    "source_files": [
                        "data/hoyolab/account_weapons.json",
                        "data/hoyolab/account_character_details.json",
                        "data/hoyolab/crop_manifest.json",
                    ],
                    "weapon_id_is_type_id_not_instance_id": True,
                    "full_inventory_proven": False,
                    "known_count_policy": "non_decreasing_max_observed_count",
                    "fingerprint_identity_fields": _weapon_fingerprint_field_names(),
                    "excluded_from_fingerprint": [
                        "equipped_character_id",
                        "localized_name",
                        "description",
                        "icon_path",
                        "source_row_index",
                    ],
                    "observed_character_ids": observed_character_ids,
                    "sync_observed_count": len(stack_observations),
                }
            )
            row_warnings = _dedupe(
                list(chosen.warnings)
                + [
                    WARNING_WEAPON_IDENTITY_NO_INSTANCE_ID,
                    WARNING_WEAPON_OBSERVED_STACK_NOT_FULL_INVENTORY,
                ]
            )
            _upsert_weapon_observed_stack(
                conn,
                chosen,
                known_count=len(stack_observations),
                source_metadata=source_metadata,
                warnings=row_warnings,
                now=now,
            )
            weapon_stacks_upserted += 1
            warnings.extend(row_warnings)
    else:
        warnings.append(WARNING_WEAPON_OBSERVATIONS_EMPTY_PRESERVED)

    return AccountStorageSyncSummary(
        characters_seen=characters_seen,
        characters_upserted=characters_upserted,
        talents_seen=talents_seen,
        talents_upserted=talents_upserted,
        weapon_observations_seen=len(observation_by_key),
        weapon_stacks_seen=len(grouped),
        weapon_stacks_upserted=weapon_stacks_upserted,
        warnings=tuple(_dedupe(warnings)),
    )


def weapon_observed_stack_fingerprint(
    *,
    weapon_id: Any,
    rarity: Any,
    level: Any,
    refinement: Any,
    promote_level: Any,
    base_atk: Any,
    secondary_property_type: Any,
    secondary_stat_value: Any,
) -> str:
    """Build source-independent identity for an observed weapon stack."""

    payload = {
        "weapon_id": _optional_int(weapon_id),
        "rarity": _optional_int(rarity),
        "level": _optional_int(level),
        "refinement": _optional_int(refinement),
        "promote_level": _optional_int(promote_level),
        "base_atk": normalize_stat_value_for_fingerprint(base_atk),
        "secondary_property_type": _optional_int(secondary_property_type),
        "secondary_stat_value": normalize_stat_value_for_fingerprint(
            secondary_stat_value
        ),
    }
    return stable_hash(payload)


def account_side_icon_local_path(
    character_id: str | int,
    side_icon_url: str,
    *,
    cache_dir: str | Path = DEFAULT_SIDE_ICON_CACHE_DIR,
) -> Path:
    suffix = _url_image_suffix(side_icon_url)
    character_key = _optional_int(character_id)
    filename = f"char_{character_key if character_key is not None else _text(character_id)}{suffix}"
    return Path(cache_dir) / filename


def cache_account_side_icon(
    *,
    character_id: str | int,
    side_icon_url: str,
    cache_dir: str | Path = DEFAULT_SIDE_ICON_CACHE_DIR,
    downloader: Callable[[str, Path], None] | None = None,
    force: bool = False,
) -> AccountSideIconCacheResult:
    side_icon_url = _text(side_icon_url)
    if not side_icon_url:
        return AccountSideIconCacheResult()

    path = account_side_icon_local_path(
        character_id,
        side_icon_url,
        cache_dir=cache_dir,
    )
    if _is_valid_cached_file(path) and not force:
        return AccountSideIconCacheResult(
            path=_storage_path(path),
            reused_existing=True,
        )

    if downloader is None:
        return AccountSideIconCacheResult()

    try:
        downloader(side_icon_url, path)
    except Exception:
        return AccountSideIconCacheResult(
            warnings=(WARNING_CHARACTER_SIDE_ICON_CACHE_FAILED,),
        )

    if not _is_valid_cached_file(path):
        return AccountSideIconCacheResult(
            warnings=(WARNING_CHARACTER_SIDE_ICON_CACHE_FAILED,),
        )

    return AccountSideIconCacheResult(
        path=_storage_path(path),
        downloaded=True,
    )


def list_account_characters(
    conn: sqlite3.Connection,
) -> tuple[AccountCharacterRuntimeRecord, ...]:
    init_account_storage(conn)
    rows = conn.execute(
        """
        SELECT *
        FROM account_characters
        ORDER BY name COLLATE NOCASE ASC, character_id ASC
        """
    ).fetchall()
    identities = identity_by_character_id(
        conn,
        [_optional_int(row["character_id"]) for row in rows],
    )
    talents_by_character = _talents_by_character_id(
        conn,
        [_optional_int(row["character_id"]) for row in rows],
    )
    return tuple(
        _account_character_runtime_record(
            row,
            talents=talents_by_character.get(_optional_int(row["character_id"]), ()),
            identity=identities.get(_optional_int(row["character_id"])),
        )
        for row in rows
    )


def get_account_character(
    conn: sqlite3.Connection,
    character_id: str | int,
) -> AccountCharacterRuntimeRecord | None:
    init_account_storage(conn)
    row = conn.execute(
        """
        SELECT *
        FROM account_characters
        WHERE character_id = ?
        LIMIT 1
        """,
        (_optional_int(character_id),),
    ).fetchone()
    if row is None:
        return None
    character_id_int = _optional_int(row["character_id"])
    talents_by_character = _talents_by_character_id(conn, [character_id_int])
    identities = identity_by_character_id(conn, [character_id_int])
    return _account_character_runtime_record(
        row,
        talents=talents_by_character.get(character_id_int, ()),
        identity=identities.get(character_id_int),
    )


def list_account_character_talents(
    conn: sqlite3.Connection,
    character_id: str | int,
) -> tuple[AccountCharacterTalentRecord, ...]:
    init_account_storage(conn)
    return _talents_by_character_id(conn, [_optional_int(character_id)]).get(
        _optional_int(character_id),
        (),
    )


def list_account_weapon_observed_stacks(
    conn: sqlite3.Connection,
) -> tuple[AccountWeaponObservedStack, ...]:
    init_account_storage(conn)
    rows = conn.execute(
        """
        SELECT *
        FROM account_weapon_observed_stacks
        ORDER BY
            COALESCE(rarity, 0) DESC,
            COALESCE(level, 0) DESC,
            name COLLATE NOCASE ASC,
            weapon_fingerprint ASC
        """
    ).fetchall()
    return tuple(_account_weapon_observed_stack(row) for row in rows)


def get_account_weapon_observed_stack(
    conn: sqlite3.Connection,
    weapon_fingerprint: str,
) -> AccountWeaponObservedStack | None:
    init_account_storage(conn)
    row = conn.execute(
        """
        SELECT *
        FROM account_weapon_observed_stacks
        WHERE weapon_fingerprint = ?
        LIMIT 1
        """,
        (_text(weapon_fingerprint),),
    ).fetchone()
    return _account_weapon_observed_stack(row) if row else None


def get_account_weapon_observed_stack_by_id(
    conn: sqlite3.Connection,
    stack_id: str | int,
) -> AccountWeaponObservedStack | None:
    init_account_storage(conn)
    row = conn.execute(
        """
        SELECT *
        FROM account_weapon_observed_stacks
        WHERE id = ?
        LIMIT 1
        """,
        (_optional_int(stack_id),),
    ).fetchone()
    return _account_weapon_observed_stack(row) if row else None


def _upsert_account_character(
    conn: sqlite3.Connection,
    *,
    character_id: int,
    character: Mapping[str, Any],
    portrait_path: str,
    side_icon_path: str,
    base_hp: float | None,
    base_atk: float | None,
    base_def: float | None,
    ascension_bonus_stat_type: str,
    ascension_bonus_value: float | None,
    source_metadata: Mapping[str, Any],
    warnings: list[str],
    now: str,
) -> None:
    conn.execute(
        """
        INSERT INTO account_characters (
            character_id,
            name,
            element,
            rarity,
            level,
            constellation,
            weapon_type,
            weapon_type_name,
            icon_url,
            side_icon_url,
            portrait_path,
            side_icon_path,
            base_hp,
            base_atk,
            base_def,
            ascension_bonus_stat_type,
            ascension_bonus_value,
            source_metadata_json,
            warnings_json,
            first_seen_at,
            last_seen_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(character_id) DO UPDATE SET
            name = excluded.name,
            element = excluded.element,
            rarity = excluded.rarity,
            level = excluded.level,
            constellation = excluded.constellation,
            weapon_type = excluded.weapon_type,
            weapon_type_name = excluded.weapon_type_name,
            icon_url = excluded.icon_url,
            side_icon_url = excluded.side_icon_url,
            portrait_path = excluded.portrait_path,
            side_icon_path = excluded.side_icon_path,
            base_hp = excluded.base_hp,
            base_atk = excluded.base_atk,
            base_def = excluded.base_def,
            ascension_bonus_stat_type = excluded.ascension_bonus_stat_type,
            ascension_bonus_value = excluded.ascension_bonus_value,
            source_metadata_json = excluded.source_metadata_json,
            warnings_json = excluded.warnings_json,
            first_seen_at = COALESCE(account_characters.first_seen_at, excluded.first_seen_at),
            last_seen_at = excluded.last_seen_at,
            updated_at = excluded.updated_at
        """,
        (
            character_id,
            _text(character.get("name")),
            _text(character.get("element")),
            _optional_int(character.get("rarity")),
            _optional_int(character.get("level")),
            _optional_int(
                _first_present(character, {}, "actived_constellation_num", "constellation")
            ),
            _optional_int(character.get("weapon_type")),
            _text(character.get("weapon_type_name")),
            _text(character.get("icon")),
            _text(character.get("side_icon")),
            portrait_path,
            side_icon_path,
            base_hp,
            base_atk,
            base_def,
            ascension_bonus_stat_type,
            ascension_bonus_value,
            _json_dumps(source_metadata),
            _json_dumps(_dedupe(warnings)),
            now,
            now,
            now,
        ),
    )


def _sync_account_character_talents(
    conn: sqlite3.Connection,
    *,
    character_id: int,
    detail: Mapping[str, Any],
    now: str,
) -> tuple[int, int, list[str]]:
    skills = detail.get("skills")
    if not isinstance(skills, list):
        return 0, 0, []

    seen = 0
    upserted = 0
    warnings: list[str] = []
    for index, skill in enumerate(skills):
        if not isinstance(skill, Mapping):
            continue
        skill_id = _optional_int(skill.get("skill_id") or skill.get("id"))
        if skill_id is None:
            warnings.append(WARNING_CHARACTER_TALENT_SKILL_ID_MISSING)
            continue
        seen += 1
        source_metadata = {
            "source": "hoyolab_account_character_details_skills",
            "source_path": "account_character_details.json -> json.data.list[].skills[]",
            "source_row_index": index,
            "raw_fields_present": sorted(str(key) for key in skill.keys()),
            "account_state_only": True,
            "effects_not_stored": True,
        }
        conn.execute(
            """
            INSERT INTO account_character_talents (
                character_id,
                skill_id,
                skill_type,
                name,
                level,
                icon_url,
                is_unlock,
                source_metadata_json,
                warnings_json,
                first_seen_at,
                last_seen_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(character_id, skill_id) DO UPDATE SET
                skill_type = excluded.skill_type,
                name = excluded.name,
                level = excluded.level,
                icon_url = excluded.icon_url,
                is_unlock = excluded.is_unlock,
                source_metadata_json = excluded.source_metadata_json,
                warnings_json = excluded.warnings_json,
                first_seen_at = COALESCE(
                    account_character_talents.first_seen_at,
                    excluded.first_seen_at
                ),
                last_seen_at = excluded.last_seen_at,
                updated_at = excluded.updated_at
            """,
            (
                character_id,
                skill_id,
                _optional_int(skill.get("skill_type")),
                _text(skill.get("name")),
                _optional_int(skill.get("level")),
                _text(skill.get("icon")),
                _optional_bool_int(skill.get("is_unlock")),
                _json_dumps(source_metadata),
                _json_dumps([]),
                now,
                now,
                now,
            ),
        )
        upserted += 1
    return seen, upserted, warnings


def _upsert_weapon_observed_stack(
    conn: sqlite3.Connection,
    observation: _WeaponObservation,
    *,
    known_count: int,
    source_metadata: Mapping[str, Any],
    warnings: list[str],
    now: str,
) -> None:
    conn.execute(
        """
        INSERT INTO account_weapon_observed_stacks (
            weapon_fingerprint,
            weapon_id,
            name,
            weapon_type,
            weapon_type_name,
            rarity,
            level,
            refinement,
            promote_level,
            base_atk,
            base_atk_raw,
            secondary_property_type,
            secondary_stat_value,
            secondary_stat_value_raw,
            description,
            icon_url,
            icon_path,
            known_count,
            first_seen_at,
            last_seen_at,
            source_metadata_json,
            warnings_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(weapon_fingerprint) DO UPDATE SET
            weapon_id = excluded.weapon_id,
            name = excluded.name,
            weapon_type = excluded.weapon_type,
            weapon_type_name = excluded.weapon_type_name,
            rarity = excluded.rarity,
            level = excluded.level,
            refinement = excluded.refinement,
            promote_level = excluded.promote_level,
            base_atk = excluded.base_atk,
            base_atk_raw = excluded.base_atk_raw,
            secondary_property_type = excluded.secondary_property_type,
            secondary_stat_value = excluded.secondary_stat_value,
            secondary_stat_value_raw = excluded.secondary_stat_value_raw,
            description = excluded.description,
            icon_url = excluded.icon_url,
            icon_path = excluded.icon_path,
            known_count = CASE
                WHEN account_weapon_observed_stacks.known_count > excluded.known_count
                THEN account_weapon_observed_stacks.known_count
                ELSE excluded.known_count
            END,
            first_seen_at = COALESCE(
                account_weapon_observed_stacks.first_seen_at,
                excluded.first_seen_at
            ),
            last_seen_at = excluded.last_seen_at,
            source_metadata_json = excluded.source_metadata_json,
            warnings_json = excluded.warnings_json
        """,
        (
            observation.weapon_fingerprint,
            observation.weapon_id,
            observation.name,
            observation.weapon_type,
            observation.weapon_type_name,
            observation.rarity,
            observation.level,
            observation.refinement,
            observation.promote_level,
            observation.base_atk,
            observation.base_atk_raw,
            observation.secondary_property_type,
            observation.secondary_stat_value,
            observation.secondary_stat_value_raw,
            observation.description,
            observation.icon_url,
            observation.icon_path,
            max(1, int(known_count)),
            now,
            now,
            _json_dumps(source_metadata),
            _json_dumps(_dedupe(warnings)),
        ),
    )


def _weapon_observations(
    *,
    account_weapons: list[dict[str, Any]],
    detail_rows: list[dict[str, Any]],
    weapon_wiki: Mapping[str, str],
    weapon_icon_paths: _WeaponIconPathMap,
) -> list[_WeaponObservation]:
    observations: list[_WeaponObservation] = []
    details_by_character = _details_by_character_id(detail_rows)
    observed_detail_character_ids: set[str] = set()

    for index, account_weapon in enumerate(account_weapons):
        equipped_by = _mapping(account_weapon.get("equipped_by"))
        character_id = _text(equipped_by.get("id"))
        if _optional_int(character_id) in IGNORED_CHARACTER_IDS:
            continue
        detail = details_by_character.get(character_id)
        if detail is not None:
            observed_detail_character_ids.add(character_id)
            observations.append(
                _weapon_observation_from_detail(
                    detail,
                    account_weapon=account_weapon,
                    observation_key=f"character:{character_id}",
                    weapon_wiki=weapon_wiki,
                    icon_path=_weapon_icon_path_for_observation(
                        account_weapon=account_weapon,
                        detail=detail,
                        weapon_icon_paths=weapon_icon_paths,
                    ),
                    source_files=(
                        "data/hoyolab/account_weapons.json",
                        "data/hoyolab/account_character_details.json",
                    ),
                )
            )
            continue

        observation_key = (
            f"character:{character_id}"
            if character_id
            else f"account_weapons_source_row:{index}"
        )
        observations.append(
            _weapon_observation_from_account_weapon(
            account_weapon,
            observation_key=observation_key,
            weapon_wiki=weapon_wiki,
            source_row_index=index,
                icon_path=_weapon_icon_path_for_observation(
                    account_weapon=account_weapon,
                    detail=None,
                    weapon_icon_paths=weapon_icon_paths,
                ),
            )
        )

    for detail in detail_rows:
        base = _mapping(detail.get("base"))
        character_id = _text(base.get("id") or detail.get("id"))
        if not character_id or character_id in observed_detail_character_ids:
            continue
        if _optional_int(character_id) in IGNORED_CHARACTER_IDS:
            continue
        weapon = _mapping(detail.get("weapon"))
        if not weapon:
            continue
        observations.append(
            _weapon_observation_from_detail(
                detail,
                account_weapon=None,
                observation_key=f"character:{character_id}",
                weapon_wiki=weapon_wiki,
                icon_path=_weapon_icon_path_for_observation(
                    account_weapon=None,
                    detail=detail,
                    weapon_icon_paths=weapon_icon_paths,
                ),
                source_files=("data/hoyolab/account_character_details.json",),
            )
        )

    return observations


def _weapon_observation_from_detail(
    detail: Mapping[str, Any],
    *,
    account_weapon: Mapping[str, Any] | None,
    observation_key: str,
    weapon_wiki: Mapping[str, str],
    icon_path: str,
    source_files: tuple[str, ...],
) -> _WeaponObservation:
    base = _mapping(detail.get("base"))
    detail_weapon = _mapping(detail.get("weapon"))
    account_weapon = _mapping(account_weapon)
    sheet = parse_account_character_stat_sheet(detail)
    weapon_sheet = sheet.weapon

    main_property = weapon_sheet.main_property
    sub_property = weapon_sheet.sub_property
    base_atk_raw = (
        main_property.final
        if main_property is not None
        and main_property.property_type == PROPERTY_WEAPON_BASE_ATK
        else ""
    )
    secondary_property_type = (
        sub_property.property_type if sub_property is not None else None
    )
    secondary_stat_raw = sub_property.final if sub_property is not None else ""
    warnings: list[str] = []
    if not base_atk_raw:
        warnings.append(WARNING_WEAPON_DETAIL_MISSING)

    weapon_id = _optional_int(detail_weapon.get("id") or account_weapon.get("id"))
    rarity = _optional_int(detail_weapon.get("rarity") or account_weapon.get("rarity"))
    level = _optional_int(detail_weapon.get("level") or account_weapon.get("level"))
    refinement = _optional_int(
        detail_weapon.get("affix_level")
        or account_weapon.get("affix_level")
        or account_weapon.get("refinement")
    )
    promote_level = _optional_int(detail_weapon.get("promote_level"))
    fingerprint = weapon_observed_stack_fingerprint(
        weapon_id=weapon_id,
        rarity=rarity,
        level=level,
        refinement=refinement,
        promote_level=promote_level,
        base_atk=base_atk_raw,
        secondary_property_type=secondary_property_type,
        secondary_stat_value=secondary_stat_raw,
    )

    character_id = _text(base.get("id"))
    weapon_catalog_entry_page_id = _entry_id_from_url(weapon_wiki.get(str(weapon_id)))
    source_metadata = {
        "observation_key": observation_key,
        "equipped_character_id": character_id,
        "equipped_character_name": _text(base.get("name")),
        "hoyowiki_weapon_entry_id": weapon_catalog_entry_page_id,
        "source_files": list(source_files),
        "detail_weapon_present": True,
        "account_weapon_row_present": bool(account_weapon),
    }
    return _WeaponObservation(
        observation_key=observation_key,
        weapon_fingerprint=fingerprint,
        weapon_id=weapon_id,
        name=_text(detail_weapon.get("name") or account_weapon.get("name")),
        weapon_type=_optional_int(detail_weapon.get("type") or account_weapon.get("type")),
        weapon_type_name=_text(
            detail_weapon.get("type_name") or account_weapon.get("type_name")
        ),
        rarity=rarity,
        level=level,
        refinement=refinement,
        promote_level=promote_level,
        base_atk=_number_or_none(base_atk_raw),
        base_atk_raw=base_atk_raw,
        secondary_property_type=secondary_property_type,
        secondary_stat_value=_number_or_none(secondary_stat_raw),
        secondary_stat_value_raw=secondary_stat_raw,
        description=_text(detail_weapon.get("desc")),
        icon_url=_text(detail_weapon.get("icon") or account_weapon.get("icon")),
        icon_path=icon_path,
        warnings=tuple(_dedupe(warnings)),
        source_metadata=source_metadata,
    )


def _weapon_observation_from_account_weapon(
    account_weapon: Mapping[str, Any],
    *,
    observation_key: str,
    weapon_wiki: Mapping[str, str],
    source_row_index: int,
    icon_path: str,
) -> _WeaponObservation:
    equipped_by = _mapping(account_weapon.get("equipped_by"))
    weapon_id = _optional_int(account_weapon.get("id"))
    rarity = _optional_int(account_weapon.get("rarity"))
    level = _optional_int(account_weapon.get("level"))
    refinement = _optional_int(
        account_weapon.get("affix_level") or account_weapon.get("refinement")
    )
    promote_level = _optional_int(account_weapon.get("promote_level"))
    base_atk_raw = _text(account_weapon.get("base_atk"))
    secondary_property_type = _optional_int(account_weapon.get("secondary_property_type"))
    secondary_stat_raw = _text(account_weapon.get("secondary_stat_value"))
    fingerprint = weapon_observed_stack_fingerprint(
        weapon_id=weapon_id,
        rarity=rarity,
        level=level,
        refinement=refinement,
        promote_level=promote_level,
        base_atk=base_atk_raw,
        secondary_property_type=secondary_property_type,
        secondary_stat_value=secondary_stat_raw,
    )
    warnings = [WARNING_WEAPON_DETAIL_MISSING]
    source_metadata = {
        "observation_key": observation_key,
        "equipped_character_id": _text(equipped_by.get("id")),
        "equipped_character_name": _text(equipped_by.get("name")),
        "hoyowiki_weapon_entry_id": _entry_id_from_url(weapon_wiki.get(str(weapon_id))),
        "source_files": ["data/hoyolab/account_weapons.json"],
        "source_row_index": source_row_index,
        "detail_weapon_present": False,
        "account_weapon_row_present": True,
    }
    return _WeaponObservation(
        observation_key=observation_key,
        weapon_fingerprint=fingerprint,
        weapon_id=weapon_id,
        name=_text(account_weapon.get("name")),
        weapon_type=_optional_int(account_weapon.get("type")),
        weapon_type_name=_text(account_weapon.get("type_name")),
        rarity=rarity,
        level=level,
        refinement=refinement,
        promote_level=promote_level,
        base_atk=_number_or_none(base_atk_raw),
        base_atk_raw=base_atk_raw,
        secondary_property_type=secondary_property_type,
        secondary_stat_value=_number_or_none(secondary_stat_raw),
        secondary_stat_value_raw=secondary_stat_raw,
        description=_text(account_weapon.get("desc")),
        icon_url=_text(account_weapon.get("icon")),
        icon_path=icon_path,
        warnings=tuple(_dedupe(warnings)),
        source_metadata=source_metadata,
    )


def _details_data(account_details: Mapping[str, Any]) -> dict[str, Any]:
    payload = account_details.get("json")
    if not isinstance(payload, Mapping):
        payload = account_details
    data = payload.get("data") if isinstance(payload, Mapping) else None
    return dict(data) if isinstance(data, Mapping) else {}


def _detail_rows(details_data: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = details_data.get("list")
    if not isinstance(rows, list):
        return []
    return [dict(item) for item in rows if isinstance(item, Mapping)]


def _details_by_character_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        base = _mapping(row.get("base"))
        character_id = _text(base.get("id") or row.get("id"))
        if character_id:
            result[character_id] = row
    return result


def _account_character_runtime_record(
    row: sqlite3.Row | Mapping[str, Any],
    *,
    talents: tuple[AccountCharacterTalentRecord, ...] = (),
    identity: CharacterIdentityRecord | None = None,
) -> AccountCharacterRuntimeRecord:
    return AccountCharacterRuntimeRecord(
        character_id=_text(row["character_id"]),
        name=_text(row["name"]),
        element=_text(row["element"]),
        rarity=_optional_int(row["rarity"]),
        level=_optional_int(row["level"]),
        constellation=_optional_int(row["constellation"]),
        weapon_type=_optional_int(row["weapon_type"]),
        weapon_type_name=_text(row["weapon_type_name"]),
        icon_url=_text(row["icon_url"]),
        side_icon_url=_text(row["side_icon_url"]),
        portrait_path=_text(row["portrait_path"]),
        side_icon_path=_text(row["side_icon_path"]),
        region_key=identity.region_key if identity else "",
        region_name=identity.region_name if identity else "",
        hoyowiki_entry_id=identity.hoyowiki_entry_id if identity else "",
        traits=identity.traits if identity else (),
        is_standard_5_star=identity.is_standard_5_star if identity else False,
        base_hp=_number_or_none(row["base_hp"]),
        base_atk=_number_or_none(row["base_atk"]),
        base_def=_number_or_none(row["base_def"]),
        ascension_bonus_stat_type=_text(row["ascension_bonus_stat_type"]),
        ascension_bonus_value=_number_or_none(row["ascension_bonus_value"]),
        warnings=tuple(_json_list(row["warnings_json"])),
        talents=talents,
        source_metadata=_json_dict(row["source_metadata_json"]),
        first_seen_at=_text(row["first_seen_at"]),
        last_seen_at=_text(row["last_seen_at"]),
    )


def _talents_by_character_id(
    conn: sqlite3.Connection,
    character_ids: list[int | None],
) -> dict[int | None, tuple[AccountCharacterTalentRecord, ...]]:
    ids = sorted({item for item in character_ids if item is not None})
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT *
        FROM account_character_talents
        WHERE character_id IN ({placeholders})
        ORDER BY character_id ASC, COALESCE(skill_type, 0) ASC, skill_id ASC
        """,
        tuple(ids),
    ).fetchall()
    grouped: dict[int | None, list[AccountCharacterTalentRecord]] = {}
    for row in rows:
        character_id = _optional_int(row["character_id"])
        grouped.setdefault(character_id, []).append(_account_character_talent_record(row))
    return {key: tuple(value) for key, value in grouped.items()}


def _account_character_talent_record(
    row: sqlite3.Row | Mapping[str, Any],
) -> AccountCharacterTalentRecord:
    unlock_value = row["is_unlock"]
    is_unlock = None if unlock_value is None else bool(int(unlock_value))
    return AccountCharacterTalentRecord(
        character_id=_text(row["character_id"]),
        skill_id=_text(row["skill_id"]),
        skill_type=_optional_int(row["skill_type"]),
        name=_text(row["name"]),
        level=_optional_int(row["level"]),
        icon_url=_text(row["icon_url"]),
        is_unlock=is_unlock,
        warnings=tuple(_json_list(row["warnings_json"])),
        source_metadata=_json_dict(row["source_metadata_json"]),
        first_seen_at=_text(row["first_seen_at"]),
        last_seen_at=_text(row["last_seen_at"]),
    )


def _account_weapon_observed_stack(
    row: sqlite3.Row | Mapping[str, Any],
) -> AccountWeaponObservedStack:
    return AccountWeaponObservedStack(
        id=_optional_int(row["id"]),
        weapon_fingerprint=_text(row["weapon_fingerprint"]),
        weapon_id=_text(row["weapon_id"]),
        name=_text(row["name"]),
        weapon_type=_optional_int(row["weapon_type"]),
        weapon_type_name=_text(row["weapon_type_name"]),
        rarity=_optional_int(row["rarity"]),
        level=_optional_int(row["level"]),
        refinement=_optional_int(row["refinement"]),
        promote_level=_optional_int(row["promote_level"]),
        base_atk=_number_or_none(row["base_atk"]),
        base_atk_raw=_text(row["base_atk_raw"]),
        secondary_property_type=_optional_int(row["secondary_property_type"]),
        secondary_stat_value=_number_or_none(row["secondary_stat_value"]),
        secondary_stat_value_raw=_text(row["secondary_stat_value_raw"]),
        description=_text(row["description"]),
        icon_url=_text(row["icon_url"]),
        icon_path=_text(row["icon_path"]),
        known_count=_optional_int(row["known_count"]) or 1,
        warnings=tuple(_json_list(row["warnings_json"])),
        source_metadata=_json_dict(row["source_metadata_json"]),
        first_seen_at=_text(row["first_seen_at"]),
        last_seen_at=_text(row["last_seen_at"]),
    )


def _merge_account_character(
    base: Mapping[str, Any],
    account_record: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "id": _first_present(base, account_record, "id"),
        "name": _first_present(base, account_record, "name"),
        "element": _first_present(base, account_record, "element"),
        "rarity": _first_present(base, account_record, "rarity"),
        "level": _first_present(base, account_record, "level"),
        "constellation": _first_present(
            base,
            account_record,
            "actived_constellation_num",
            "constellation",
        ),
        "actived_constellation_num": _first_present(
            base,
            account_record,
            "actived_constellation_num",
            "constellation",
        ),
        "weapon_type": _first_present(base, account_record, "weapon_type"),
        "weapon_type_name": _first_present(base, account_record, "weapon_type_name"),
        "icon": _first_present(base, account_record, "icon"),
        "side_icon": _first_present(base, account_record, "side_icon"),
    }


def _character_entries_by_id(
    catalog: CharacterBaseStatsCatalog | None,
) -> dict[str, CharacterBaseStatsEntry]:
    if catalog is None:
        return {}
    return {entry.entry_page_id: entry for entry in catalog.entries if entry.entry_page_id}


def _character_crops_by_id(manifest: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for asset in manifest.get("characterAssets") or []:
        if not isinstance(asset, Mapping):
            continue
        character = _mapping(asset.get("character"))
        character_id = _text(character.get("id"))
        crop = _text(asset.get("crop"))
        if character_id and crop:
            result[character_id] = crop
    for card in manifest.get("cards") or []:
        if not isinstance(card, Mapping):
            continue
        character = _mapping(card.get("character"))
        crops = _mapping(card.get("crops"))
        character_id = _text(character.get("id"))
        crop = _text(crops.get("character"))
        if character_id and crop:
            result.setdefault(character_id, crop)
    return result


def _weapon_icon_paths(manifest: Mapping[str, Any]) -> _WeaponIconPathMap:
    by_icon_key: dict[str, str] = {}
    by_weapon_id: dict[str, str] = {}

    for asset in manifest.get("weaponAssets") or []:
        if not isinstance(asset, Mapping):
            continue
        weapon = _mapping(asset.get("weapon"))
        crop = _text(asset.get("crop"))
        if not crop:
            continue
        _add_weapon_icon_path(
            by_icon_key=by_icon_key,
            by_weapon_id=by_weapon_id,
            weapon=weapon,
            crop=crop,
        )

    for card in manifest.get("cards") or []:
        if not isinstance(card, Mapping):
            continue
        weapon = _mapping(card.get("weapon"))
        crops = _mapping(card.get("crops"))
        crop = _text(crops.get("weapon"))
        if not crop:
            continue
        _add_weapon_icon_path(
            by_icon_key=by_icon_key,
            by_weapon_id=by_weapon_id,
            weapon=weapon,
            crop=crop,
        )

    return _WeaponIconPathMap(by_icon_key=by_icon_key, by_weapon_id=by_weapon_id)


def _add_weapon_icon_path(
    *,
    by_icon_key: dict[str, str],
    by_weapon_id: dict[str, str],
    weapon: Mapping[str, Any],
    crop: str,
) -> None:
    key = icon_key(_text(weapon.get("icon")))
    if key:
        by_icon_key.setdefault(key, crop)
    weapon_id = _text(weapon.get("id"))
    if weapon_id:
        by_weapon_id.setdefault(weapon_id, crop)


def _weapon_icon_path_for_observation(
    *,
    account_weapon: Mapping[str, Any] | None,
    detail: Mapping[str, Any] | None,
    weapon_icon_paths: _WeaponIconPathMap,
) -> str:
    detail_weapon = _mapping((detail or {}).get("weapon"))
    path = _weapon_icon_path_for_weapon(detail_weapon, weapon_icon_paths)
    if path:
        return path
    return _weapon_icon_path_for_weapon(_mapping(account_weapon), weapon_icon_paths)


def _weapon_icon_path_for_weapon(
    weapon: Mapping[str, Any],
    weapon_icon_paths: _WeaponIconPathMap,
) -> str:
    key = icon_key(_text(weapon.get("icon")))
    if key:
        path = weapon_icon_paths.by_icon_key.get(key)
        if path:
            return path
    weapon_id = _text(weapon.get("id"))
    if weapon_id:
        return weapon_icon_paths.by_weapon_id.get(weapon_id, "")
    return ""


def _entry_id_from_url(value: str | None) -> str:
    value = _text(value)
    if not value:
        return ""
    if value.isdigit():
        return value
    match = _ENTRY_ID_RE.search(value)
    return match.group(1) if match else ""


def _ensure_account_character_columns(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "account_characters")
    additions = {
        "first_seen_at": "TEXT",
        "last_seen_at": "TEXT",
        "updated_at": "TEXT",
        "source_metadata_json": "TEXT NOT NULL DEFAULT '{}'",
        "warnings_json": "TEXT NOT NULL DEFAULT '[]'",
    }
    for column, definition in additions.items():
        if column not in columns:
            conn.execute(
                f"ALTER TABLE account_characters ADD COLUMN {column} {definition}"
            )


def _ensure_account_character_talent_columns(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "account_character_talents")
    additions = {
        "source_metadata_json": "TEXT NOT NULL DEFAULT '{}'",
        "warnings_json": "TEXT NOT NULL DEFAULT '[]'",
        "first_seen_at": "TEXT",
        "last_seen_at": "TEXT",
        "updated_at": "TEXT",
    }
    for column, definition in additions.items():
        if column not in columns:
            conn.execute(
                f"ALTER TABLE account_character_talents ADD COLUMN {column} {definition}"
            )


def _ensure_observed_weapon_columns(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "account_weapon_observed_stacks")
    additions = {
        "known_count": "INTEGER NOT NULL DEFAULT 1",
        "first_seen_at": "TEXT",
        "last_seen_at": "TEXT",
        "source_metadata_json": "TEXT NOT NULL DEFAULT '{}'",
        "warnings_json": "TEXT NOT NULL DEFAULT '[]'",
    }
    for column, definition in additions.items():
        if column not in columns:
            conn.execute(
                f"ALTER TABLE account_weapon_observed_stacks ADD COLUMN {column} {definition}"
            )


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _load_json_dict(path: str | Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return data if isinstance(data, dict) else {}


def _load_json_list(path: str | Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    if not isinstance(data, list):
        return []
    return [dict(item) for item in data if isinstance(item, Mapping)]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        _text(key): _text(item)
        for key, item in value.items()
        if _text(key) and _text(item)
    }


def _first_present(
    primary: Mapping[str, Any],
    fallback: Mapping[str, Any],
    *keys: str,
) -> Any:
    for key in keys:
        value = primary.get(key)
        if value is not None and value != "":
            return value
    for key in keys:
        value = fallback.get(key)
        if value is not None and value != "":
            return value
    return None


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_bool_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return 1 if bool(value) else 0


def _number_or_none(value: Any) -> float | None:
    text = str(value or "").replace("%", "").replace(",", ".").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_dict(value: Any) -> dict[str, Any]:
    try:
        data = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return dict(data) if isinstance(data, Mapping) else {}


def _json_list(value: Any) -> list[str]:
    try:
        data = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [_text(item) for item in data if _text(item)]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _account_storage_ascension_warnings(values: tuple[str, ...]) -> list[str]:
    return [
        value
        for value in values
        if value and value not in _ACCOUNT_STORAGE_HIDDEN_ASCENSION_WARNINGS
    ]


def _account_storage_ascension_bonus_dict(value: Any) -> dict[str, Any]:
    data = value.to_dict()
    warnings = data.get("warnings")
    if isinstance(warnings, list):
        data["warnings"] = _account_storage_ascension_warnings(tuple(warnings))
    return data


def _url_image_suffix(url: str) -> str:
    path = Path(urlsplit(str(url or "")).path)
    suffix = path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".avif"}:
        return suffix
    return ".png"


def _is_valid_cached_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _storage_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT.resolve()))
    except (OSError, ValueError):
        return str(path)


def _normalize_url(url: str) -> str:
    parts = urlsplit(url)
    safe_path = quote(parts.path, safe="/")
    safe_query = quote(parts.query, safe="=&?/:,+%")
    return urlunsplit((parts.scheme, parts.netloc, safe_path, safe_query, parts.fragment))


def _download_url_to_file(url: str, destination: Path, *, timeout: float = 20.0) -> None:
    request = urllib.request.Request(
        _normalize_url(url),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
            "Referer": "https://act.hoyolab.com",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
    if not data:
        raise RuntimeError("empty file response")

    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destination.with_suffix(destination.suffix + ".tmp")
    tmp_path.write_bytes(data)
    tmp_path.replace(destination)


def _weapon_fingerprint_field_names() -> list[str]:
    return [
        "weapon_id",
        "rarity",
        "level",
        "refinement",
        "promote_level",
        "base_atk",
        "secondary_property_type",
        "secondary_stat_value",
    ]


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Populate local SQLite account character and observed weapon stack "
            "tables from already-local HoYoLAB JSON/cache files."
        )
    )
    parser.add_argument("--db", default=str(DEFAULT_ACCOUNT_DB_PATH))
    parser.add_argument("--characters", default=str(DEFAULT_ACCOUNT_CHARACTERS_PATH))
    parser.add_argument("--weapons", default=str(DEFAULT_ACCOUNT_WEAPONS_PATH))
    parser.add_argument(
        "--character-details",
        default=str(DEFAULT_ACCOUNT_CHARACTER_DETAILS_PATH),
    )
    parser.add_argument("--crop-manifest", default=str(DEFAULT_CROP_MANIFEST_PATH))
    parser.add_argument(
        "--character-stats-catalog",
        default=str(CHARACTER_BASE_STATS_CACHE_PATH),
    )
    parser.add_argument(
        "--download-side-icons",
        action="store_true",
        help=(
            "Cache missing account character side icons from already-known "
            "HoYoLAB side_icon URLs. Off by default to keep normal sync no-network."
        ),
    )
    args = parser.parse_args(argv)

    summary = sync_account_storage_from_local_files(
        db_path=args.db,
        account_characters_path=args.characters,
        account_weapons_path=args.weapons,
        account_character_details_path=args.character_details,
        crop_manifest_path=args.crop_manifest,
        character_stats_catalog_path=args.character_stats_catalog,
        download_side_icons=args.download_side_icons,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
