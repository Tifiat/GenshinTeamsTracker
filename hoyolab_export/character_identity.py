from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .character_region_catalog import normalize_character_name
from .character_trait_catalog import (
    TRAIT_STANDARD_5_STAR,
    CharacterTraitEntry,
    load_character_trait_catalog,
)

TRAVELER_CHARACTER_IDS = {10000005, 10000007}


@dataclass(frozen=True, slots=True)
class CharacterIdentityRecord:
    character_id: str
    hoyowiki_entry_id: str = ""
    region_key: str = ""
    region_name: str = ""
    traits: tuple[str, ...] = ()
    is_standard_5_star: bool = False
    source_metadata: dict[str, Any] | None = None
    updated_at: str = ""


def init_character_identity_storage(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS character_identity (
            character_id INTEGER PRIMARY KEY,
            hoyowiki_entry_id TEXT,
            region_key TEXT,
            region_name TEXT,
            traits_json TEXT NOT NULL DEFAULT '[]',
            is_standard_5_star INTEGER NOT NULL DEFAULT 0,
            source_metadata_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_character_identity_region
            ON character_identity(region_key);
        CREATE INDEX IF NOT EXISTS idx_character_identity_standard
            ON character_identity(is_standard_5_star);
        """
    )


def sync_character_identity_from_account_rows(
    conn: sqlite3.Connection,
    *,
    region_entries: Iterable[Mapping[str, Any]] = (),
    trait_entries: Iterable[CharacterTraitEntry] | None = None,
    now: str = "",
) -> int:
    """Join account characters with static/reference character identity tags."""

    init_character_identity_storage(conn)
    regions_by_entry_id = {
        str(entry.get("entry_page_id") or "").strip(): entry
        for entry in region_entries
        if str(entry.get("entry_page_id") or "").strip()
    }
    regions_by_name = {
        str(entry.get("normalized_name") or "").strip(): entry
        for entry in region_entries
        if str(entry.get("normalized_name") or "").strip()
    }
    traits_by_entry_id: dict[str, set[str]] = {}
    traits_by_name: dict[str, set[str]] = {}
    for entry in trait_entries or load_character_trait_catalog().entries:
        for trait in entry.traits:
            if entry.source_character_entry_page_id:
                traits_by_entry_id.setdefault(entry.source_character_entry_page_id, set()).add(trait)
            for name in (entry.name, *entry.aliases):
                normalized = normalize_character_name(name)
                if normalized:
                    traits_by_name.setdefault(normalized, set()).add(trait)

    rows = conn.execute(
        """
        SELECT character_id, name, source_metadata_json
        FROM account_characters
        ORDER BY character_id
        """
    ).fetchall()
    count = 0
    for row in rows:
        character_id = row["character_id"]
        name = str(row["name"] or "")
        metadata = _json_dict(row["source_metadata_json"])
        entry_id = str(metadata.get("hoyowiki_character_entry_id") or "").strip()
        normalized_name = normalize_character_name(name)

        region_entry = regions_by_entry_id.get(entry_id) or regions_by_name.get(normalized_name) or {}
        traits = set(traits_by_entry_id.get(entry_id, set()))
        traits.update(traits_by_name.get(normalized_name, set()))
        if int(character_id) in TRAVELER_CHARACTER_IDS:
            traits.add(TRAIT_STANDARD_5_STAR)
        traits_tuple = tuple(sorted(traits))

        source_metadata = {
            "source": "static_character_identity_join",
            "account_character_source": "account_characters",
            "region_source": "hoyowiki_character_region_catalog",
            "trait_source": "hoyowiki_character_trait_catalog",
            "hoyowiki_entry_id_match": bool(entry_id),
            "name_fallback_match_key": normalized_name,
        }
        conn.execute(
            """
            INSERT INTO character_identity (
                character_id,
                hoyowiki_entry_id,
                region_key,
                region_name,
                traits_json,
                is_standard_5_star,
                source_metadata_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(character_id) DO UPDATE SET
                hoyowiki_entry_id = excluded.hoyowiki_entry_id,
                region_key = excluded.region_key,
                region_name = excluded.region_name,
                traits_json = excluded.traits_json,
                is_standard_5_star = excluded.is_standard_5_star,
                source_metadata_json = excluded.source_metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                character_id,
                entry_id,
                str(region_entry.get("region_key") or ""),
                str(region_entry.get("region_name") or ""),
                json.dumps(list(traits_tuple), ensure_ascii=False),
                1 if TRAIT_STANDARD_5_STAR in traits_tuple else 0,
                json.dumps(source_metadata, ensure_ascii=False, sort_keys=True),
                now,
            ),
        )
        count += 1
    return count


def identity_by_character_id(
    conn: sqlite3.Connection,
    character_ids: Iterable[int | None],
) -> dict[int, CharacterIdentityRecord]:
    init_character_identity_storage(conn)
    ids = sorted({int(item) for item in character_ids if item is not None})
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""
        SELECT *
        FROM character_identity
        WHERE character_id IN ({placeholders})
        """,
        tuple(ids),
    ).fetchall()
    return {
        int(row["character_id"]): CharacterIdentityRecord(
            character_id=str(row["character_id"]),
            hoyowiki_entry_id=str(row["hoyowiki_entry_id"] or ""),
            region_key=str(row["region_key"] or ""),
            region_name=str(row["region_name"] or ""),
            traits=tuple(str(item) for item in _json_list(row["traits_json"])),
            is_standard_5_star=bool(int(row["is_standard_5_star"] or 0)),
            source_metadata=_json_dict(row["source_metadata_json"]),
            updated_at=str(row["updated_at"] or ""),
        )
        for row in rows
    }


def _json_dict(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: Any) -> list[Any]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []
