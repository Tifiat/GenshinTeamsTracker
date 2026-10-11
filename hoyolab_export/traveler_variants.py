"""Transactional Traveler row expansion; never copies items or equipment.

Callers prepare account schemas. Expansion joins the caller's transaction;
startup backfill owns a savepoint (atomic on its own or within an outer unit).
Neither path opens files, initializes schemas, imports sources or uses network.
"""
from __future__ import annotations

import json
import sqlite3

from .traveler import (
    TRAVELER_ELEMENTS, TRAVELER_SOURCE_IDS, traveler_catalog_name,
    traveler_element, traveler_variant_id,
)


def account_traveler_id(conn: sqlite3.Connection, source_id: int, element: object) -> int:
    if source_id not in TRAVELER_SOURCE_IDS:
        return source_id
    selected = traveler_element(source_id, element)
    if not selected:
        raise ValueError("Traveler observation has no supported explicit element")
    anchor = conn.execute(
        "SELECT element FROM account_characters WHERE character_id = ?", (source_id,),
    ).fetchone()
    if anchor is None or traveler_element(source_id, anchor["element"]) == selected:
        return source_id
    if not traveler_element(source_id, anchor["element"]):
        raise ValueError("Existing Traveler has no explicit element; migration needs source evidence")
    return traveler_variant_id(source_id, selected)


def _metadata(raw: str | None) -> dict:
    return json.loads(raw or "{}")


def ensure_traveler_variants(conn: sqlite3.Connection, *, now: str) -> int:
    """Fill only missing variants from an existing source row, idempotently."""
    created = 0
    for source_id in sorted(TRAVELER_SOURCE_IDS):
        source = conn.execute(
            "SELECT * FROM account_characters WHERE character_id = ?", (source_id,),
        ).fetchone()
        if source is None:
            continue
        selected = traveler_element(source_id, source["element"])
        if not selected:
            continue
        metadata = _metadata(source["source_metadata_json"])
        if "traveler_variant" not in metadata:
            # One bounded recovery record per source Traveler, owned by this
            # saved account's lifetime. Preserve the exact legacy rows before
            # enrichment; gear/presets/source receipts are never rewritten.
            identity = conn.execute(
                "SELECT * FROM character_identity WHERE character_id = ?", (source_id,),
            ).fetchone()
            metadata["traveler_variant"] = {
                "source_character_id": source_id, "element": selected,
                "observation": "hoyolab", "legacy_original": {
                    "account_character": dict(source),
                    "character_identity": dict(identity) if identity else None,
                },
            }
            conn.execute("UPDATE account_characters SET source_metadata_json = ? WHERE character_id = ?",
                         (json.dumps(metadata, ensure_ascii=False, sort_keys=True), source_id))
            source = conn.execute("SELECT * FROM account_characters WHERE character_id = ?", (source_id,)).fetchone()
        for element in TRAVELER_ELEMENTS:
            target_id = source_id if element == selected else traveler_variant_id(source_id, element)
            existing = conn.execute(
                "SELECT source_metadata_json FROM account_characters WHERE character_id = ?",
                (target_id,),
            ).fetchone()
            if existing is None:
                values = dict(source)
                values["character_id"] = target_id
                values["element"] = element
                metadata = _metadata(source["source_metadata_json"])
                metadata["traveler_variant"] = {
                    "source_character_id": source_id,
                    "element": element,
                    "observation": "initial_copy",
                    "copied_from_character_id": source_id,
                    "copied_from_element": selected,
                }
                values["source_metadata_json"] = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
                columns = tuple(values)
                conn.execute(
                    f"INSERT INTO account_characters ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                    tuple(values.values()),
                )
                for table in ("account_character_talents", "account_character_constellations"):
                    columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
                    projection = ["?" if column == "character_id" else column for column in columns]
                    conn.execute(
                        f"INSERT INTO {table} ({','.join(columns)}) SELECT {','.join(projection)} "
                        f"FROM {table} WHERE character_id = ?", (target_id, source_id),
                    )
                    if table == "account_character_talents":
                        for talent in conn.execute(
                            "SELECT skill_id, source_metadata_json FROM account_character_talents WHERE character_id = ?",
                            (target_id,),
                        ).fetchall():
                            talent_metadata = _metadata(talent["source_metadata_json"])
                            talent_metadata["traveler_initial_copy"] = True
                            conn.execute(
                                "UPDATE account_character_talents SET source_metadata_json = ? WHERE character_id = ? AND skill_id = ?",
                                (json.dumps(talent_metadata, ensure_ascii=False, sort_keys=True), target_id, talent["skill_id"]),
                            )
                created += 1
            # Keep every row's element-derived identity explicit, even when
            # catalogs are absent or an old generic Traveler key was cached.
            metadata = _metadata(conn.execute(
                "SELECT source_metadata_json FROM account_characters WHERE character_id = ?", (target_id,),
            ).fetchone()[0])
            metadata["gcsim_character_key_resolution"] = {
                "catalog_english_name": traveler_catalog_name(target_id, element),
                "gcsim_key": "", "status": "unsupported_traveler",
                "method": "explicit_variant_runtime_deferred", "candidates": [],
                "warnings": [], "source_paths": {},
            }
            conn.execute(
                "UPDATE account_characters SET catalog_english_name = ?, gcsim_character_key = '', "
                "gcsim_character_key_status = 'unsupported_traveler', "
                "gcsim_character_key_method = 'explicit_variant_runtime_deferred', source_metadata_json = ? WHERE character_id = ?",
                (traveler_catalog_name(target_id, element), json.dumps(metadata, ensure_ascii=False, sort_keys=True), target_id),
            )
            identity = conn.execute(
                "SELECT * FROM character_identity WHERE character_id = ?", (target_id,),
            ).fetchone()
            if identity is None:
                original = conn.execute(
                    "SELECT * FROM character_identity WHERE character_id = ?", (source_id,),
                ).fetchone()
                values = dict(original) if original is not None else {
                    "character_id": target_id, "traits_json": "[]", "source_metadata_json": "{}",
                }
                values["character_id"] = target_id
                values["is_standard_5_star"] = 1
                values["traits_json"] = json.dumps(sorted(set(json.loads(values["traits_json"])) | {"standard_5_star"}))
                values["updated_at"] = now
                columns = tuple(values)
                conn.execute(
                    f"INSERT INTO character_identity ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                    tuple(values.values()),
                )
            else:
                traits = sorted(set(json.loads(identity["traits_json"] or "[]")) | {"standard_5_star"})
                conn.execute(
                    "UPDATE character_identity SET traits_json = ?, is_standard_5_star = 1 WHERE character_id = ?",
                    (json.dumps(traits), target_id),
                )
    return created


def backfill_traveler_variants(conn: sqlite3.Connection, *, now: str) -> int:
    """Schema-startup migration, with one atomic unit and no observation replay."""
    for row in conn.execute(
        "SELECT character_id, element FROM account_characters WHERE character_id IN (10000005,10000007)",
    ).fetchall():
        source_id = row["character_id"]
        selected = traveler_element(source_id, row["element"])
        if not selected:
            continue
        expected = [source_id if e == selected else traveler_variant_id(source_id, e) for e in TRAVELER_ELEMENTS]
        count = conn.execute(
            f"SELECT COUNT(*) FROM account_characters WHERE character_id IN ({','.join('?' for _ in expected)})",
            expected,
        ).fetchone()[0]
        if count != len(expected):
            conn.execute("SAVEPOINT traveler_backfill")
            try:
                created = ensure_traveler_variants(conn, now=now)
                conn.execute("RELEASE traveler_backfill")
                return created
            except Exception:
                conn.execute("ROLLBACK TO traveler_backfill")
                conn.execute("RELEASE traveler_backfill")
                raise
    return 0
