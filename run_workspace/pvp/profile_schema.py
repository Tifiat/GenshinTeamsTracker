"""Narrow portable SQLite schema for PvP profile packages.

The packaged database deliberately keeps less data than the runtime account
database.  ``materialize_runtime_db`` expands it into a managed runtime DB
using the application's existing schema initializer and empty compatibility
fields.
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import tempfile
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from hoyolab_export.display_stat_effects import (
    STATIC_DISPLAY_STAT_KEYS,
    VALUE_TYPE_FLAT,
    VALUE_TYPE_PERCENT_POINTS,
)

from .deck import FREE_DRAFT_V0_RULESET_ID
from .deck_preset import (
    PVP_DECK_PRESET_KIND,
    PVP_DECK_PRESET_SCHEMA_VERSION,
    PvpDeckPreset,
    deck_preset_to_draft_deck,
)
from .validation import validate_draft_deck
from .weapon_identity import WeaponObservedStackRef, weapon_observed_stack_key


PROFILE_SLICE_SCHEMA_VERSION = 3


class ProfileSchemaError(ValueError):
    """Raised when a portable PvP database is malformed or incompatible."""


_TABLE_DDL: tuple[str, ...] = (
    """CREATE TABLE account_characters (
        character_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        element TEXT,
        rarity INTEGER,
        level INTEGER,
        constellation INTEGER,
        weapon_type INTEGER,
        weapon_type_name TEXT,
        base_hp REAL,
        base_atk REAL,
        base_def REAL,
        ascension_bonus_stat_type TEXT,
        ascension_bonus_value REAL,
        catalog_english_name TEXT,
        gcsim_character_key TEXT,
        gcsim_character_key_status TEXT,
        gcsim_character_key_method TEXT
    )""",
    """CREATE TABLE account_character_talents (
        character_id INTEGER NOT NULL,
        skill_id INTEGER NOT NULL,
        skill_type INTEGER,
        name TEXT,
        level INTEGER,
        is_unlock INTEGER,
        PRIMARY KEY (character_id, skill_id),
        FOREIGN KEY (character_id) REFERENCES account_characters(character_id)
            ON DELETE CASCADE
    )""",
    """CREATE TABLE account_character_constellations (
        character_id INTEGER NOT NULL,
        pos INTEGER NOT NULL,
        name TEXT,
        effect TEXT,
        is_actived INTEGER,
        PRIMARY KEY (character_id, pos),
        FOREIGN KEY (character_id) REFERENCES account_characters(character_id)
            ON DELETE CASCADE
    )""",
    """CREATE TABLE account_weapon_observed_stacks (
        id INTEGER PRIMARY KEY,
        weapon_fingerprint TEXT NOT NULL UNIQUE,
        weapon_id TEXT,
        name TEXT NOT NULL,
        weapon_type INTEGER,
        weapon_type_name TEXT,
        rarity INTEGER,
        level INTEGER,
        refinement INTEGER,
        promote_level INTEGER,
        base_atk REAL,
        secondary_property_type INTEGER,
        secondary_stat_value REAL,
        description TEXT,
        known_count INTEGER NOT NULL DEFAULT 1,
        catalog_english_name TEXT,
        gcsim_weapon_key TEXT,
        gcsim_weapon_key_status TEXT,
        gcsim_weapon_key_method TEXT
    )""",
    """CREATE TABLE weapon_display_stat_effects (
        weapon_id INTEGER NOT NULL,
        refinement INTEGER NOT NULL,
        stat_key TEXT NOT NULL,
        value REAL NOT NULL,
        value_type TEXT NOT NULL,
        PRIMARY KEY (weapon_id, refinement, stat_key),
        CHECK (refinement BETWEEN 1 AND 5),
        CHECK (value_type IN ('flat', 'percent_points'))
    )""",
    """CREATE TABLE weapon_passive_tooltips (
        weapon_id INTEGER NOT NULL,
        lang TEXT NOT NULL,
        passive_name TEXT NOT NULL DEFAULT '',
        passive_text TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (weapon_id, lang)
    )""",
    """CREATE TABLE character_identity (
        character_id INTEGER PRIMARY KEY,
        hoyowiki_entry_id TEXT,
        region_key TEXT,
        region_name TEXT,
        traits_json TEXT NOT NULL DEFAULT '[]',
        is_standard_5_star INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (character_id) REFERENCES account_characters(character_id)
            ON DELETE CASCADE
    )""",
    """CREATE TABLE artifact_sets (
        set_uid TEXT PRIMARY KEY,
        hoyowiki_entry_id TEXT NOT NULL UNIQUE,
        hoyolab_set_id INTEGER UNIQUE,
        artiscan_set_key TEXT UNIQUE,
        display_name TEXT,
        fallback_name TEXT NOT NULL
    )""",
    """CREATE TABLE artifact_set_names (
        set_uid TEXT NOT NULL,
        lang TEXT NOT NULL,
        name TEXT NOT NULL,
        normalized_name TEXT NOT NULL,
        PRIMARY KEY (set_uid, lang),
        FOREIGN KEY (set_uid) REFERENCES artifact_sets(set_uid)
            ON DELETE CASCADE
    )""",
    """CREATE TABLE artifact_set_bonus_descriptions (
        set_uid TEXT NOT NULL,
        lang TEXT NOT NULL,
        piece_count INTEGER NOT NULL CHECK (piece_count IN (2, 4)),
        description TEXT NOT NULL,
        source TEXT NOT NULL,
        PRIMARY KEY (set_uid, lang, piece_count),
        FOREIGN KEY (set_uid) REFERENCES artifact_sets(set_uid)
            ON DELETE CASCADE
    )""",
    """CREATE TABLE artifacts (
        id INTEGER PRIMARY KEY,
        relic_id INTEGER,
        name TEXT NOT NULL,
        set_id INTEGER,
        set_uid TEXT,
        set_name TEXT,
        pos INTEGER NOT NULL CHECK (pos BETWEEN 1 AND 5),
        pos_name TEXT,
        rarity INTEGER,
        level INTEGER,
        main_property_type INTEGER,
        main_property_name TEXT,
        main_property_value TEXT
    )""",
    """CREATE TABLE artifact_substats (
        artifact_id INTEGER NOT NULL,
        slot_index INTEGER NOT NULL CHECK (slot_index >= 0),
        property_type INTEGER,
        property_name TEXT,
        value TEXT,
        times INTEGER,
        PRIMARY KEY (artifact_id, slot_index),
        FOREIGN KEY (artifact_id) REFERENCES artifacts(id)
            ON DELETE CASCADE
    )""",
    """CREATE TABLE artifact_builds (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL
    )""",
    """CREATE TABLE artifact_build_slots (
        build_id INTEGER NOT NULL,
        pos INTEGER NOT NULL CHECK (pos BETWEEN 1 AND 5),
        artifact_id INTEGER NOT NULL,
        PRIMARY KEY (build_id, pos),
        FOREIGN KEY (build_id) REFERENCES artifact_builds(id)
            ON DELETE CASCADE,
        FOREIGN KEY (artifact_id) REFERENCES artifacts(id)
            ON DELETE CASCADE
    )""",
    """CREATE TABLE artifact_build_targets (
        build_id INTEGER NOT NULL,
        target_type TEXT NOT NULL CHECK (target_type = 'character'),
        character_id INTEGER NOT NULL,
        character_name TEXT,
        PRIMARY KEY (build_id, character_id),
        FOREIGN KEY (build_id) REFERENCES artifact_builds(id)
            ON DELETE CASCADE,
        FOREIGN KEY (character_id) REFERENCES account_characters(character_id)
            ON DELETE CASCADE
    )""",
    """CREATE TABLE artifact_build_gcsim_targets (
        build_id INTEGER NOT NULL,
        gcsim_character_key TEXT NOT NULL,
        character_name TEXT,
        PRIMARY KEY (build_id, gcsim_character_key),
        FOREIGN KEY (build_id) REFERENCES artifact_builds(id)
            ON DELETE CASCADE
    )""",
)

_TABLE_NAMES = tuple(
    re.search(r"CREATE TABLE\s+(\w+)", ddl, re.IGNORECASE).group(1)  # type: ignore[union-attr]
    for ddl in _TABLE_DDL
)
_ALLOWED_TRAITS = frozenset({"hexerei", "moonsign", "standard_5_star"})
_SAFE_DECK_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_SOURCE_COLUMNS: dict[str, tuple[str, ...]] = {
    "account_characters": (
        "character_id", "name", "element", "rarity", "level", "constellation",
        "weapon_type", "weapon_type_name", "base_hp",
        "base_atk", "base_def", "ascension_bonus_stat_type", "ascension_bonus_value",
        "catalog_english_name", "gcsim_character_key", "gcsim_character_key_status",
        "gcsim_character_key_method",
    ),
    "account_character_talents": (
        "character_id", "skill_id", "skill_type", "name", "level", "is_unlock",
    ),
    "account_character_constellations": (
        "character_id", "pos", "name", "effect", "is_actived",
    ),
    "account_weapon_observed_stacks": (
        "id", "weapon_fingerprint", "weapon_id", "name", "weapon_type",
        "weapon_type_name", "rarity", "level", "refinement", "promote_level",
        "base_atk", "secondary_property_type", "secondary_stat_value", "description",
        "known_count", "catalog_english_name", "gcsim_weapon_key",
        "gcsim_weapon_key_status", "gcsim_weapon_key_method",
    ),
    "character_identity": (
        "character_id", "hoyowiki_entry_id", "region_key", "region_name",
        "traits_json", "is_standard_5_star",
    ),
    "artifact_sets": (
        "set_uid", "hoyowiki_entry_id", "hoyolab_set_id", "artiscan_set_key",
        "display_name", "fallback_name",
    ),
    "artifact_set_names": ("set_uid", "lang", "name", "normalized_name"),
    "artifact_set_bonus_descriptions": (
        "set_uid", "lang", "piece_count", "description", "source",
    ),
    "artifacts": (
        "id", "relic_id", "name", "set_id", "set_uid", "set_name", "pos", "pos_name", "rarity", "level",
        "main_property_type", "main_property_name", "main_property_value",
    ),
    "artifact_substats": (
        "artifact_id", "slot_index", "property_type", "property_name", "value", "times",
    ),
    "artifact_builds": ("id", "name"),
    "artifact_build_slots": ("build_id", "pos", "artifact_id"),
    "artifact_build_targets": ("build_id", "target_type", "character_id", "character_name"),
    "artifact_build_gcsim_targets": ("build_id", "gcsim_character_key", "character_name"),
}
_OPTIONAL_SOURCE_COLUMNS: dict[str, frozenset[str]] = {
    "artifact_sets": frozenset({"hoyolab_set_id", "artiscan_set_key"}),
    "artifacts": frozenset({"relic_id", "set_id"}),
}
_WEAPON_EFFECT_COLUMNS = ("weapon_id", "refinement", "stat_key", "value", "value_type")
_WEAPON_TOOLTIP_COLUMNS = ("weapon_id", "lang", "passive_name", "passive_text")

_ROW_LIMITS = {
    "account_characters": 512,
    "account_character_talents": 8192,
    "account_character_constellations": 3072,
    "account_weapon_observed_stacks": 20000,
    "weapon_display_stat_effects": 20000,
    "weapon_passive_tooltips": 10000,
    "character_identity": 512,
    "artifact_sets": 4096,
    "artifact_set_names": 20000,
    "artifact_set_bonus_descriptions": 10000,
    "artifacts": 50000,
    "artifact_substats": 250000,
    "artifact_builds": 10000,
    "artifact_build_slots": 50000,
    "artifact_build_targets": 100000,
    "artifact_build_gcsim_targets": 100000,
}

_PORTABLE_SCHEMA_CACHE: dict[str, tuple[tuple[str, str, int, Any, int], ...]] | None = None
_TEXT_LIMITS: dict[tuple[str, str], int] = {
    ("account_characters", "name"): 256,
    ("account_characters", "element"): 64,
    ("account_characters", "weapon_type_name"): 64,
    ("account_characters", "ascension_bonus_stat_type"): 128,
    ("account_characters", "catalog_english_name"): 256,
    ("account_characters", "gcsim_character_key"): 128,
    ("account_characters", "gcsim_character_key_status"): 64,
    ("account_characters", "gcsim_character_key_method"): 64,
    ("account_character_talents", "name"): 256,
    ("account_character_constellations", "name"): 256,
    ("account_character_constellations", "effect"): 2048,
    ("account_weapon_observed_stacks", "weapon_fingerprint"): 256,
    ("account_weapon_observed_stacks", "weapon_id"): 64,
    ("account_weapon_observed_stacks", "name"): 256,
    ("account_weapon_observed_stacks", "weapon_type_name"): 64,
    ("account_weapon_observed_stacks", "description"): 4096,
    ("weapon_display_stat_effects", "stat_key"): 64,
    ("weapon_display_stat_effects", "value_type"): 32,
    ("weapon_passive_tooltips", "lang"): 32,
    ("weapon_passive_tooltips", "passive_name"): 256,
    ("weapon_passive_tooltips", "passive_text"): 4096,
    ("character_identity", "traits_json"): 256,
    ("artifact_sets", "set_uid"): 128,
    ("artifact_sets", "hoyowiki_entry_id"): 128,
    ("artifact_sets", "artiscan_set_key"): 128,
    ("artifact_sets", "display_name"): 256,
    ("artifact_sets", "fallback_name"): 256,
    ("artifact_set_names", "lang"): 32,
    ("artifact_set_names", "name"): 256,
    ("artifact_set_names", "normalized_name"): 256,
    ("artifact_set_bonus_descriptions", "lang"): 32,
    ("artifact_set_bonus_descriptions", "description"): 4096,
    ("artifact_set_bonus_descriptions", "source"): 128,
    ("artifacts", "name"): 256,
    ("artifacts", "set_uid"): 128,
    ("artifacts", "set_name"): 256,
    ("artifacts", "pos_name"): 64,
    ("artifacts", "main_property_name"): 128,
    ("artifacts", "main_property_value"): 64,
    ("artifact_substats", "property_name"): 128,
    ("artifact_substats", "value"): 64,
    ("artifact_builds", "name"): 256,
    ("artifact_build_targets", "target_type"): 32,
    ("artifact_build_targets", "character_name"): 256,
    ("artifact_build_gcsim_targets", "gcsim_character_key"): 128,
    ("artifact_build_gcsim_targets", "character_name"): 256,
}
_ABSOLUTE_LOCAL_PATH = re.compile(
    r"^(?:[a-z]:[\\/]|\\\\|/|file://)|(?:^|[\s(])(?:[a-z]:[\\/]|\\\\|/Users/|/home/)",
    re.IGNORECASE,
)


def contains_absolute_local_path(value: str) -> bool:
    """Return whether text contains an absolute local filesystem path."""
    return bool(_ABSOLUTE_LOCAL_PATH.search(value.strip()))


def create_profile_slice(
    source_path: Path,
    destination: Path,
    deck_presets: tuple[PvpDeckPreset, ...],
) -> dict[str, int]:
    """Write the exact allowlisted account/artifact slice for these PvP decks."""

    source_path = Path(source_path).resolve()
    destination = Path(destination).resolve()
    if source_path == destination:
        raise ProfileSchemaError("The profile slice destination must differ from its source.")
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    presets = _validate_deck_preset_metadata(deck_presets)
    destination.parent.mkdir(parents=True, exist_ok=True)

    source = _connect_readonly(source_path)
    staging_path: Path | None = None
    try:
        snapshot = _load_source_snapshot(source, presets)
        _validate_deck_data(snapshot, presets)
        file_descriptor, staging_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".sqlite.tmp",
            dir=destination.parent,
        )
        os.close(file_descriptor)
        staging_path = Path(staging_name)
        output = sqlite3.connect(staging_path)
        output.row_factory = sqlite3.Row
        try:
            output.execute("PRAGMA foreign_keys = ON")
            _create_schema(output)
            _insert_snapshot(output, snapshot)
            output.execute(f"PRAGMA user_version = {PROFILE_SLICE_SCHEMA_VERSION}")
            output.commit()
        except Exception:
            output.rollback()
            raise
        finally:
            output.close()

        counts = validate_profile_slice(staging_path, presets)
        source.close()
        source = None  # type: ignore[assignment]
        os.replace(staging_path, destination)
        staging_path = None
        return counts
    except ProfileSchemaError:
        raise
    except sqlite3.DatabaseError as exc:
        raise ProfileSchemaError(f"Could not create the PvP profile slice: {exc}") from exc
    except (TypeError, ValueError, OverflowError) as exc:
        raise ProfileSchemaError(f"Could not create the PvP profile slice: {exc}") from exc
    finally:
        if source is not None:
            source.close()
        if staging_path is not None:
            try:
                staging_path.unlink()
            except FileNotFoundError:
                pass


def validate_profile_slice(
    db_path: Path,
    deck_presets: tuple[PvpDeckPreset, ...],
    expected_counts: Mapping[str, int] | None = None,
) -> dict[str, int]:
    """Validate the v3 portable schema, references, deck inputs, and row counts."""

    presets = _validate_deck_preset_metadata(deck_presets)
    connection = _connect_readonly(Path(db_path).resolve())
    try:
        counts = _validate_portable_connection(connection, presets)
        if expected_counts is not None:
            if set(expected_counts) != set(counts):
                missing = set(counts).difference(expected_counts)
                unknown = set(expected_counts).difference(counts)
                raise ProfileSchemaError(
                    "Expected count keys must exactly match the profile counts; "
                    f"missing={sorted(missing)}, unknown={sorted(unknown)}."
                )
            for key, expected in expected_counts.items():
                if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
                    raise ProfileSchemaError(f"Expected count {key!r} must be a non-negative integer.")
                if counts[key] != expected:
                    raise ProfileSchemaError(
                        f"Count mismatch for {key}: expected {expected}, found {counts[key]}."
                    )
        return counts
    except ProfileSchemaError:
        raise
    except sqlite3.DatabaseError as exc:
        raise ProfileSchemaError(f"Invalid PvP profile slice database: {exc}") from exc
    except (TypeError, ValueError, OverflowError) as exc:
        raise ProfileSchemaError(f"Invalid PvP profile slice database: {exc}") from exc
    finally:
        connection.close()


def materialize_runtime_db(
    portable_path: Path,
    runtime_path: Path,
    character_paths: Mapping[str, Path],
    weapon_paths: Mapping[str, Path],
) -> None:
    """Expand a portable slice into a separate managed DB for existing readers."""

    portable_path = Path(portable_path).resolve()
    runtime_path = Path(runtime_path).resolve()
    if portable_path == runtime_path:
        raise ProfileSchemaError("The runtime database must differ from the portable slice.")

    portable = _connect_readonly(portable_path)
    staging_path: Path | None = None
    try:
        _validate_portable_connection(portable, None)
        snapshot = _read_portable_snapshot(portable)
        char_paths = _normalize_paths(character_paths, {str(row["character_id"]) for row in snapshot["account_characters"]})
        weapon_paths_by_id = _normalize_paths(
            weapon_paths,
            {str(row["weapon_id"]) for row in snapshot["account_weapon_observed_stacks"]},
        )

        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, staging_name = tempfile.mkstemp(
            prefix=f".{runtime_path.name}.",
            suffix=".sqlite.tmp",
            dir=runtime_path.parent,
        )
        os.close(file_descriptor)
        staging_path = Path(staging_name)

        from hoyolab_export.artifact_db import init_db

        runtime = sqlite3.connect(staging_path)
        runtime.row_factory = sqlite3.Row
        try:
            init_db(runtime)
            runtime.execute("PRAGMA foreign_keys = ON")
            _hydrate_runtime_db(runtime, snapshot, char_paths, weapon_paths_by_id)
            runtime.commit()
        except Exception:
            runtime.rollback()
            raise
        finally:
            runtime.close()

        os.replace(staging_path, runtime_path)
        staging_path = None
    except ProfileSchemaError:
        raise
    except sqlite3.DatabaseError as exc:
        raise ProfileSchemaError(f"Could not materialize the runtime PvP database: {exc}") from exc
    except (TypeError, ValueError, OverflowError) as exc:
        raise ProfileSchemaError(f"Could not materialize the runtime PvP database: {exc}") from exc
    finally:
        portable.close()
        if staging_path is not None:
            try:
                staging_path.unlink()
            except FileNotFoundError:
                pass


def _connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
    except Exception:
        connection.close()
        raise
    return connection


def _validate_deck_preset_metadata(
    deck_presets: tuple[PvpDeckPreset, ...],
) -> tuple[PvpDeckPreset, ...]:
    if not isinstance(deck_presets, tuple) or not deck_presets:
        raise ProfileSchemaError("At least one PvP deck preset is required.")
    if len(deck_presets) > 128:
        raise ProfileSchemaError("A PvP profile may contain at most 128 deck presets.")
    seen_deck_ids: set[str] = set()
    validated: list[PvpDeckPreset] = []
    for index, preset in enumerate(deck_presets):
        if not isinstance(preset, PvpDeckPreset):
            raise ProfileSchemaError(f"Deck preset {index} has an unsupported type.")
        deck_id = str(preset.deck_id or "").strip()
        if not deck_id or not _SAFE_DECK_ID.fullmatch(deck_id):
            raise ProfileSchemaError(f"Deck preset {index} has an empty or invalid deck id.")
        if deck_id in seen_deck_ids:
            raise ProfileSchemaError(f"Duplicate deck id: {deck_id}.")
        seen_deck_ids.add(deck_id)
        if not str(preset.name or "").strip():
            raise ProfileSchemaError(f"Deck {deck_id} has an empty name.")
        if preset.schema_version != PVP_DECK_PRESET_SCHEMA_VERSION or preset.kind != PVP_DECK_PRESET_KIND:
            raise ProfileSchemaError(f"Deck {deck_id} uses an unsupported preset schema.")
        if preset.ruleset_id != FREE_DRAFT_V0_RULESET_ID:
            raise ProfileSchemaError(f"Deck {deck_id} uses an unrecognized ruleset id.")
        if not isinstance(preset.extra, Mapping) or preset.extra:
            raise ProfileSchemaError(f"Deck {deck_id} contains unsupported free-form fields.")

        if not isinstance(preset.character_ids, tuple):
            raise ProfileSchemaError(f"Deck {deck_id} character references must be a tuple.")
        if len(preset.character_ids) > 512:
            raise ProfileSchemaError(f"Deck {deck_id} exceeds the character reference limit.")
        if not isinstance(preset.weapon_refs, tuple):
            raise ProfileSchemaError(f"Deck {deck_id} weapon references must be a tuple.")
        if len(preset.weapon_refs) > 512:
            raise ProfileSchemaError(f"Deck {deck_id} exceeds the weapon reference limit.")
        char_ids = tuple(preset.character_ids)
        if not char_ids:
            raise ProfileSchemaError(f"Deck {deck_id} has no character references.")
        normalized_chars: list[str] = []
        for value in char_ids:
            text = str(value or "")
            if not text or text != text.strip() or not text.isdecimal():
                raise ProfileSchemaError(f"Deck {deck_id} has an empty or invalid character reference.")
            if str(int(text)) != text:
                raise ProfileSchemaError(f"Deck {deck_id} has a non-canonical character reference.")
            normalized_chars.append(text)
        if len(set(normalized_chars)) != len(normalized_chars):
            raise ProfileSchemaError(f"Deck {deck_id} contains duplicate character references.")

        seen_weapon_keys: set[str] = set()
        for ref in preset.weapon_refs:
            if not isinstance(ref, WeaponObservedStackRef):
                raise ProfileSchemaError(f"Deck {deck_id} has an unsupported weapon reference.")
            key = str(ref.key or "").strip()
            if not key:
                raise ProfileSchemaError(f"Deck {deck_id} has an empty weapon reference.")
            if key in seen_weapon_keys:
                raise ProfileSchemaError(f"Deck {deck_id} contains a duplicate weapon reference.")
            seen_weapon_keys.add(key)
    return deck_presets


def _load_source_snapshot(
    source: sqlite3.Connection,
    deck_presets: tuple[PvpDeckPreset, ...],
) -> dict[str, list[dict[str, Any]]]:
    _require_source_columns(source)
    deck_character_ids = _deck_character_ids(deck_presets)
    character_rows = _select_rows_for_ids(
        source,
        "account_characters",
        _SOURCE_COLUMNS["account_characters"],
        "character_id",
        deck_character_ids,
    )
    character_by_id = {int(row["character_id"]): row for row in character_rows}
    missing_characters = sorted(set(deck_character_ids).difference(character_by_id))
    if missing_characters:
        raise ProfileSchemaError(
            "Deck references unknown account character ids: "
            + ", ".join(str(value) for value in missing_characters)
        )
    char_id_set = set(deck_character_ids)

    talents = _select_rows_for_ids(
        source, "account_character_talents", _SOURCE_COLUMNS["account_character_talents"],
        "character_id", deck_character_ids,
    )
    constellations = _select_rows_for_ids(
        source, "account_character_constellations", _SOURCE_COLUMNS["account_character_constellations"],
        "character_id", deck_character_ids,
    )
    identities = _select_rows_for_ids(
        source, "character_identity", _SOURCE_COLUMNS["character_identity"],
        "character_id", deck_character_ids,
    )

    character_rows = [_safe_account_character(row) for row in character_rows]
    talents = [_safe_talent(row) for row in talents]
    constellations = [_safe_constellation(row) for row in constellations]
    identities = [_safe_identity(row) for row in identities]

    all_weapon_rows = _select_all_rows(
        source, "account_weapon_observed_stacks", _SOURCE_COLUMNS["account_weapon_observed_stacks"]
    )
    weapon_rows = _select_weapon_stacks_for_presets(all_weapon_rows, deck_presets)
    weapon_ids = {
        int(row["weapon_id"])
        for row in weapon_rows
        if str(row["weapon_id"]).isdecimal()
        and 0 < int(row["weapon_id"]) <= 2**63 - 1
    }
    weapon_pairs = {
        (int(row["weapon_id"]), int(row["refinement"]))
        for row in weapon_rows
        if str(row["weapon_id"]).isdecimal()
        and int(row["weapon_id"]) in weapon_ids
        and row["refinement"] is not None
    }
    weapon_effects = [
        row for row in _select_optional_weapon_rows(
            source, "weapon_display_stat_effects", _WEAPON_EFFECT_COLUMNS, weapon_ids,
        )
        if (row["weapon_id"], row["refinement"]) in weapon_pairs
    ]
    weapon_tooltips = _select_optional_weapon_rows(
        source, "weapon_passive_tooltips", _WEAPON_TOOLTIP_COLUMNS, weapon_ids,
    )

    source_artifacts = _select_all_rows(source, "artifacts", _SOURCE_COLUMNS["artifacts"])
    source_substats = _select_all_rows(source, "artifact_substats", _SOURCE_COLUMNS["artifact_substats"])
    substats_by_source_id: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in source_substats:
        source_artifact_id = _positive_int(row["artifact_id"], "substat artifact id")
        substats_by_source_id[source_artifact_id].append(row)
    for rows in substats_by_source_id.values():
        rows.sort(key=lambda row: int(row["slot_index"]))

    for row in source_artifacts:
        source_id = _positive_int(row["id"], "artifact source id")
        row["_source_id"] = source_id
        row["name"] = _required_text(row["name"], "artifact name")
        row["pos"] = _bounded_int(row["pos"], 1, 5, "artifact position")
        row["relic_id"] = _optional_catalog_id(row.get("relic_id"), "artifact relic id")
        row["set_id"] = _optional_catalog_id(row.get("set_id"), "artifact set id")
        row["set_uid"] = _optional_text(row["set_uid"])
        row["set_name"] = _optional_text(row["set_name"])
        row["_substats"] = substats_by_source_id.pop(source_id, [])
        for substat in row["_substats"]:
            substat["slot_index"] = _bounded_int(substat["slot_index"], 0, 3, "substat slot index")
    if substats_by_source_id:
        raise ProfileSchemaError("Source contains substats without a matching artifact.")

    source_artifacts.sort(key=lambda row: (_artifact_sort_key(row), row["_source_id"]))
    artifact_id_by_source_id = {
        row["_source_id"]: local_id
        for local_id, row in enumerate(source_artifacts, start=1)
    }
    artifacts: list[dict[str, Any]] = []
    artifact_substats: list[dict[str, Any]] = []
    for row in source_artifacts:
        artifact_id = artifact_id_by_source_id[row["_source_id"]]
        artifacts.append({
            "id": artifact_id,
            "relic_id": row["relic_id"],
            "name": row["name"],
            "set_id": row["set_id"],
            "set_uid": row["set_uid"],
            "set_name": row["set_name"],
            "pos": row["pos"],
            "pos_name": _optional_text(row["pos_name"]),
            "rarity": _optional_int(row["rarity"], "artifact rarity"),
            "level": _optional_int(row["level"], "artifact level"),
            "main_property_type": _optional_int(row["main_property_type"], "main property type"),
            "main_property_name": _optional_text(row["main_property_name"]),
            "main_property_value": _optional_text(row["main_property_value"]),
        })
        for substat in row["_substats"]:
            artifact_substats.append({
                "artifact_id": artifact_id,
                "slot_index": substat["slot_index"],
                "property_type": _optional_int(substat["property_type"], "substat property type"),
                "property_name": _optional_text(substat["property_name"]),
                "value": _optional_text(substat["value"]),
                "times": _optional_int(substat["times"], "substat roll count"),
            })

    referenced_set_uids = {row["set_uid"] for row in artifacts if row["set_uid"]}
    artifact_sets = _select_rows_for_texts(
        source, "artifact_sets", _SOURCE_COLUMNS["artifact_sets"], "set_uid", referenced_set_uids
    )
    included_set_uids = {str(row["set_uid"]) for row in artifact_sets}
    artifact_sets = [{
        "set_uid": _required_text(row["set_uid"], "artifact set uid"),
        "hoyowiki_entry_id": _required_text(row["hoyowiki_entry_id"], "artifact set catalog id"),
        "hoyolab_set_id": _optional_catalog_id(row.get("hoyolab_set_id"), "artifact HoYoLAB set id"),
        "artiscan_set_key": _optional_text(row.get("artiscan_set_key")),
        "display_name": _optional_text(row["display_name"]),
        "fallback_name": _required_text(row["fallback_name"], "artifact set fallback name"),
    } for row in artifact_sets]
    set_names = [
        {"set_uid": row["set_uid"], "lang": str(row["lang"] or ""), "name": str(row["name"] or ""),
         "normalized_name": str(row["normalized_name"] or "")}
        for row in _select_rows_for_texts(
            source, "artifact_set_names", _SOURCE_COLUMNS["artifact_set_names"],
            "set_uid", included_set_uids,
        )
    ]
    set_bonuses = [
        {"set_uid": row["set_uid"], "lang": str(row["lang"] or ""),
         "piece_count": _bounded_int(row["piece_count"], 2, 4, "artifact set bonus piece count"),
         "description": _required_text(row["description"], "artifact set bonus description"),
         "source": _required_text(row["source"], "artifact set bonus source")}
        for row in _select_rows_for_texts(
            source, "artifact_set_bonus_descriptions", _SOURCE_COLUMNS["artifact_set_bonus_descriptions"],
            "set_uid", included_set_uids,
        )
    ]
    if any(row["piece_count"] not in {2, 4} for row in set_bonuses):
        raise ProfileSchemaError("Artifact set bonus piece count must be 2 or 4.")

    target_rows = _select_all_rows(
        source, "artifact_build_targets", _SOURCE_COLUMNS["artifact_build_targets"]
    )
    gcsim_rows = _select_all_rows(
        source, "artifact_build_gcsim_targets", _SOURCE_COLUMNS["artifact_build_gcsim_targets"]
    )
    selected_character_keys = {
        str(row["gcsim_character_key"] or "").strip()
        for row in character_rows
        if str(row["gcsim_character_key_status"] or "").strip() == "ready"
        and str(row["gcsim_character_key"] or "").strip()
    }
    selected_builds: dict[int, dict[str, Any]] = {}
    for row in target_rows:
        target_type = str(row["target_type"] or "").strip()
        if target_type == "universal":
            continue
        if target_type != "character":
            raise ProfileSchemaError(f"Source has an unsupported build target type: {target_type!r}.")
        character_id = _optional_int(row["character_id"], "build target character id")
        if character_id not in char_id_set:
            continue
        build_id = _positive_int(row["build_id"], "build source id")
        build = selected_builds.setdefault(build_id, {"targets": [], "gcsim_targets": [], "slots": []})
        build["targets"].append({
            "target_type": "character",
            "character_id": character_id,
            "character_name": _optional_text(row["character_name"]),
        })
    for row in gcsim_rows:
        key = _required_text(row["gcsim_character_key"], "build GCSIM target key")
        if key not in selected_character_keys:
            continue
        build_id = _positive_int(row["build_id"], "build source id")
        build = selected_builds.setdefault(build_id, {"targets": [], "gcsim_targets": [], "slots": []})
        build["gcsim_targets"].append({
            "gcsim_character_key": key,
            "character_name": _optional_text(row["character_name"]),
        })

    build_source_rows = _select_all_rows(source, "artifact_builds", _SOURCE_COLUMNS["artifact_builds"])
    build_names = {int(row["id"]): _required_text(row["name"], "artifact build name") for row in build_source_rows}
    unknown_build_ids = set(selected_builds).difference(build_names)
    if unknown_build_ids:
        raise ProfileSchemaError("A selected build target references a missing build.")
    selected_build_ids = sorted(selected_builds)
    source_slots = _select_rows_for_ids(
        source, "artifact_build_slots", _SOURCE_COLUMNS["artifact_build_slots"],
        "build_id", selected_build_ids,
    )
    for row in source_slots:
        build_id = _positive_int(row["build_id"], "build source id")
        old_artifact_id = _positive_int(row["artifact_id"], "build artifact id")
        if old_artifact_id not in artifact_id_by_source_id:
            raise ProfileSchemaError("A selected build references a missing artifact.")
        pos = _bounded_int(row["pos"], 1, 5, "build slot position")
        if artifacts[artifact_id_by_source_id[old_artifact_id] - 1]["pos"] != pos:
            raise ProfileSchemaError("A build slot position does not match its artifact.")
        selected_builds[build_id]["slots"].append({
            "pos": pos,
            "artifact_id": artifact_id_by_source_id[old_artifact_id],
        })

    builds_unsorted = []
    for source_id, relations in selected_builds.items():
        relations["targets"].sort(key=lambda item: item["character_id"])
        relations["gcsim_targets"].sort(key=lambda item: item["gcsim_character_key"])
        relations["slots"].sort(key=lambda item: item["pos"])
        builds_unsorted.append({"_source_id": source_id, "name": build_names[source_id], **relations})
    builds_unsorted.sort(key=lambda row: (
        row["name"].casefold(),
        tuple(item["character_id"] for item in row["targets"]),
        tuple(item["gcsim_character_key"] for item in row["gcsim_targets"]),
        tuple((item["pos"], item["artifact_id"]) for item in row["slots"]),
        row["_source_id"],
    ))
    build_id_by_source_id = {
        row["_source_id"]: local_id for local_id, row in enumerate(builds_unsorted, start=1)
    }
    builds: list[dict[str, Any]] = []
    build_slots: list[dict[str, Any]] = []
    build_targets: list[dict[str, Any]] = []
    build_gcsim_targets: list[dict[str, Any]] = []
    for row in builds_unsorted:
        local_id = build_id_by_source_id[row["_source_id"]]
        builds.append({"id": local_id, "name": row["name"]})
        build_slots.extend({"build_id": local_id, **slot} for slot in row["slots"])
        build_targets.extend({"build_id": local_id, **target} for target in row["targets"])
        build_gcsim_targets.extend({"build_id": local_id, **target} for target in row["gcsim_targets"])

    return {
        "account_characters": sorted(character_rows, key=lambda row: int(row["character_id"])),
        "account_character_talents": sorted(talents, key=lambda row: (row["character_id"], row["skill_id"])),
        "account_character_constellations": sorted(constellations, key=lambda row: (row["character_id"], row["pos"])),
        "account_weapon_observed_stacks": weapon_rows,
        "weapon_display_stat_effects": sorted(
            weapon_effects, key=lambda row: (row["weapon_id"], row["refinement"], row["stat_key"]),
        ),
        "weapon_passive_tooltips": sorted(
            weapon_tooltips, key=lambda row: (row["weapon_id"], row["lang"]),
        ),
        "character_identity": sorted(identities, key=lambda row: row["character_id"]),
        "artifact_sets": sorted(artifact_sets, key=lambda row: row["set_uid"]),
        "artifact_set_names": sorted(set_names, key=lambda row: (row["set_uid"], row["lang"])),
        "artifact_set_bonus_descriptions": sorted(set_bonuses, key=lambda row: (row["set_uid"], row["lang"], row["piece_count"])),
        "artifacts": artifacts,
        "artifact_substats": sorted(artifact_substats, key=lambda row: (row["artifact_id"], row["slot_index"])),
        "artifact_builds": builds,
        "artifact_build_slots": sorted(build_slots, key=lambda row: (row["build_id"], row["pos"])),
        "artifact_build_targets": sorted(build_targets, key=lambda row: (row["build_id"], row["character_id"])),
        "artifact_build_gcsim_targets": sorted(build_gcsim_targets, key=lambda row: (row["build_id"], row["gcsim_character_key"])),
    }


def _select_weapon_stacks_for_presets(
    all_rows: list[dict[str, Any]],
    deck_presets: tuple[PvpDeckPreset, ...],
) -> list[dict[str, Any]]:
    selected_by_source_id: dict[int, dict[str, Any]] = {}
    for preset in deck_presets:
        for ref in preset.weapon_refs:
            matches = _matching_weapon_rows(ref, all_rows)
            if len(matches) != 1:
                reason = "unknown" if not matches else "ambiguous"
                raise ProfileSchemaError(f"Deck {preset.deck_id} has an {reason} weapon reference.")
            source_row = matches[0]
            source_id = _positive_int(source_row["id"], "weapon stack source id")
            if source_id in selected_by_source_id:
                continue
            row = {
                "id": 0,
                "weapon_fingerprint": _required_text(source_row["weapon_fingerprint"], "weapon fingerprint"),
                "weapon_id": _required_text(source_row["weapon_id"], "weapon id"),
                "name": _required_text(source_row["name"], "weapon name"),
                "weapon_type": _optional_int(source_row["weapon_type"], "weapon type"),
                "weapon_type_name": _optional_text(source_row["weapon_type_name"]),
                "rarity": _optional_int(source_row["rarity"], "weapon rarity"),
                "level": _optional_int(source_row["level"], "weapon level"),
                "refinement": _optional_int(source_row["refinement"], "weapon refinement"),
                "promote_level": _optional_int(source_row["promote_level"], "weapon promote level"),
                "base_atk": _optional_finite_float(source_row["base_atk"], "weapon base attack"),
                "secondary_property_type": _optional_int(
                    source_row["secondary_property_type"], "weapon secondary property type"
                ),
                "secondary_stat_value": _optional_finite_float(
                    source_row["secondary_stat_value"], "weapon secondary stat"
                ),
                "description": _optional_text(source_row["description"]),
                "known_count": _bounded_int(source_row["known_count"], 1, 10000, "weapon known_count"),
                "catalog_english_name": _optional_text(source_row["catalog_english_name"]) or "",
                "gcsim_weapon_key": _optional_text(source_row["gcsim_weapon_key"]) or "",
                "gcsim_weapon_key_status": _optional_text(source_row["gcsim_weapon_key_status"]) or "",
                "gcsim_weapon_key_method": _optional_text(source_row["gcsim_weapon_key_method"]) or "",
            }
            _validate_weapon_ref_against_row(preset.deck_id, ref, row)
            selected_by_source_id[source_id] = row

    rows = sorted(selected_by_source_id.values(), key=lambda item: item["weapon_fingerprint"])
    fingerprints = [row["weapon_fingerprint"] for row in rows]
    if len(set(fingerprints)) != len(fingerprints):
        raise ProfileSchemaError("Selected source weapon stacks have duplicate fingerprints.")
    for local_id, row in enumerate(rows, start=1):
        row["id"] = local_id
    return rows


def _safe_account_character(row: dict[str, Any]) -> dict[str, Any]:
    result = {column: row[column] for column in _SOURCE_COLUMNS["account_characters"]}
    result["character_id"] = _positive_int(result["character_id"], "account character id")
    result["name"] = _required_text(result["name"], "account character name")
    result["element"] = _optional_text(result["element"])
    result["weapon_type_name"] = _optional_text(result["weapon_type_name"])
    for column in ("rarity", "level", "constellation", "weapon_type"):
        result[column] = _optional_int(result[column], f"character {column}")
    for column in ("base_hp", "base_atk", "base_def", "ascension_bonus_value"):
        result[column] = _optional_finite_float(result[column], f"character {column}")
    for column in (
        "ascension_bonus_stat_type", "catalog_english_name",
        "gcsim_character_key", "gcsim_character_key_status", "gcsim_character_key_method",
    ):
        result[column] = _optional_text(result[column])
    for column in (
        "catalog_english_name", "gcsim_character_key", "gcsim_character_key_status",
        "gcsim_character_key_method",
    ):
        result[column] = result[column] or ""
    return result


def _safe_talent(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "character_id": _positive_int(row["character_id"], "talent character id"),
        "skill_id": _positive_int(row["skill_id"], "talent skill id"),
        "skill_type": _optional_int(row["skill_type"], "talent skill type"),
        "name": _optional_text(row["name"]),
        "level": _optional_int(row["level"], "talent level"),
        "is_unlock": _optional_bool(row["is_unlock"], "talent unlock flag"),
    }


def _safe_constellation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "character_id": _positive_int(row["character_id"], "constellation character id"),
        "pos": _bounded_int(row["pos"], 1, 6, "constellation position"),
        "name": _optional_text(row["name"]),
        "effect": _optional_text(row["effect"]),
        "is_actived": _optional_bool(row["is_actived"], "constellation active flag"),
    }


def _safe_identity(row: dict[str, Any]) -> dict[str, Any]:
    try:
        traits = json.loads(str(row["traits_json"] or "[]"))
    except (TypeError, json.JSONDecodeError) as exc:
        raise ProfileSchemaError("Character identity traits are not valid JSON.") from exc
    if not isinstance(traits, list) or any(
        not isinstance(item, str) or item not in _ALLOWED_TRAITS for item in traits
    ):
        raise ProfileSchemaError("Character identity traits contain an unsupported value.")
    if len(set(traits)) != len(traits):
        raise ProfileSchemaError("Character identity traits contain duplicates.")
    is_standard = _optional_bool(row["is_standard_5_star"], "standard character flag")
    if is_standard is None:
        raise ProfileSchemaError("Character identity standard flag must be 0 or 1.")
    return {
        "character_id": _positive_int(row["character_id"], "identity character id"),
        "hoyowiki_entry_id": _optional_text(row["hoyowiki_entry_id"]),
        "region_key": _optional_text(row["region_key"]),
        "region_name": _optional_text(row["region_name"]),
        "traits_json": json.dumps(sorted(traits), ensure_ascii=False, separators=(",", ":")),
        "is_standard_5_star": is_standard,
    }


def _validate_deck_data(
    snapshot: dict[str, list[dict[str, Any]]],
    deck_presets: tuple[PvpDeckPreset, ...],
) -> None:
    characters = {str(row["character_id"]): row for row in snapshot["account_characters"]}
    weapons = snapshot["account_weapon_observed_stacks"]
    referenced_weapon_fingerprints: set[str] = set()
    for preset in deck_presets:
        char_assets = []
        for character_id in preset.character_ids:
            row = characters.get(character_id)
            if row is None:
                raise ProfileSchemaError(f"Deck {preset.deck_id} references an unknown character.")
            char_assets.append({
                "id": character_id,
                "metadata": {"character": {
                    "id": character_id,
                    "name": row["name"],
                    "element": row["element"] or "",
                    "weapon_type_name": row["weapon_type_name"] or row["weapon_type"] or "",
                    "weapon_type": row["weapon_type"],
                    "rarity": row["rarity"],
                    "level": row["level"],
                    "constellation": row["constellation"],
                }},
            })

        weapon_assets: list[dict[str, Any]] = []
        validation_refs: list[WeaponObservedStackRef] = []
        for ref in preset.weapon_refs:
            matches = _matching_weapon_rows(ref, weapons)
            if len(matches) != 1:
                reason = "unknown" if not matches else "ambiguous"
                raise ProfileSchemaError(f"Deck {preset.deck_id} has an {reason} weapon reference.")
            row = matches[0]
            _validate_weapon_ref_against_row(preset.deck_id, ref, row)
            referenced_weapon_fingerprints.add(str(row["weapon_fingerprint"]))
            weapon_type = ref.weapon_type or row["weapon_type_name"] or row["weapon_type"] or ""
            weapon = {
                "id": row["weapon_id"] or "",
                "weapon_id": row["weapon_id"] or "",
                "name": row["name"],
                "weapon_type": weapon_type,
                "rarity": row["rarity"],
                "level": row["level"],
                "refinement": row["refinement"],
                "known_count": row["known_count"],
            }
            weapon["weapon_fingerprint"] = (
                row["weapon_fingerprint"] if ref.weapon_fingerprint else ""
            )
            weapon_assets.append({"metadata": {"weapon": weapon}})
            validation_refs.append(WeaponObservedStackRef(
                weapon_fingerprint=str(row["weapon_fingerprint"]),
                weapon_id=str(row["weapon_id"] or ""),
                weapon_type=str(weapon_type),
                rarity=row["rarity"],
                level=row["level"],
                refinement=row["refinement"],
                count=row["known_count"],
            ))

        validation_preset = replace(preset, weapon_refs=tuple(validation_refs))
        deck = deck_preset_to_draft_deck(validation_preset, char_assets, weapon_assets)
        report = validate_draft_deck(deck)
        if not report.ready:
            codes = ", ".join(dict.fromkeys(report.issue_codes()))
            raise ProfileSchemaError(f"Deck {preset.deck_id} fails free_draft_v0 validation: {codes}.")
    if referenced_weapon_fingerprints != {
        str(row["weapon_fingerprint"]) for row in weapons
    }:
        raise ProfileSchemaError("Account weapon rows do not exactly match deck weapon references.")


def _validate_weapon_ref_against_row(
    deck_id: str,
    ref: WeaponObservedStackRef,
    row: dict[str, Any],
) -> None:
    if ref.weapon_id and str(ref.weapon_id) != str(row["weapon_id"]):
        raise ProfileSchemaError(f"Deck {deck_id} weapon reference conflicts with its source stack.")
    if ref.weapon_type:
        allowed_types = {
            str(row["weapon_type_name"] or "").strip().casefold(),
            str(row["weapon_type"] or "").strip().casefold(),
        } - {""}
        if allowed_types and str(ref.weapon_type).strip().casefold() not in allowed_types:
            raise ProfileSchemaError(f"Deck {deck_id} weapon type conflicts with its source stack.")
    for field in ("rarity", "level", "refinement", "count"):
        ref_value = getattr(ref, field)
        if ref_value is None:
            continue
        source_value = row["known_count"] if field == "count" else row[field]
        if source_value is None or int(ref_value) != int(source_value):
            raise ProfileSchemaError(f"Deck {deck_id} weapon {field} conflicts with its source stack.")


def _matching_weapon_rows(
    ref: WeaponObservedStackRef,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for row in rows:
        if ref.weapon_fingerprint and str(row["weapon_fingerprint"]) == ref.weapon_fingerprint:
            matches.append(row)
            continue
        if not ref.weapon_id:
            continue
        keys = {
            weapon_observed_stack_key(
                weapon_id=row["weapon_id"], weapon_type=row["weapon_type"], rarity=row["rarity"],
                level=row["level"], refinement=row["refinement"],
            ),
            weapon_observed_stack_key(
                weapon_id=row["weapon_id"], weapon_type=row["weapon_type_name"], rarity=row["rarity"],
                level=row["level"], refinement=row["refinement"],
            ),
        }
        if ref.key in keys:
            matches.append(row)
    return matches


def _validate_portable_connection(
    connection: sqlite3.Connection,
    deck_presets: tuple[PvpDeckPreset, ...] | None,
) -> dict[str, int]:
    if int(connection.execute("PRAGMA user_version").fetchone()[0]) != PROFILE_SLICE_SCHEMA_VERSION:
        raise ProfileSchemaError("Unsupported PvP profile slice schema version.")
    _validate_exact_schema(connection)
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ProfileSchemaError("PvP profile slice failed SQLite integrity_check.")
    foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise ProfileSchemaError("PvP profile slice contains broken foreign-key references.")

    snapshot = _read_portable_snapshot(connection)
    _validate_slice_rows(snapshot, deck_presets)
    if deck_presets is not None:
        _validate_deck_data(snapshot, deck_presets)
    return _snapshot_counts(snapshot, len(deck_presets) if deck_presets is not None else 0)


def _validate_exact_schema(connection: sqlite3.Connection) -> None:
    expected = sqlite3.connect(":memory:")
    try:
        expected.row_factory = sqlite3.Row
        _create_schema(expected)
        expected_objects = _user_objects(expected)
        actual_objects = _user_objects(connection)
        if actual_objects != expected_objects:
            raise ProfileSchemaError("PvP profile slice has unexpected tables, indexes, views, or triggers.")
        for table in _TABLE_NAMES:
            expected_columns = _column_signature(expected, table)
            actual_columns = _column_signature(connection, table)
            if actual_columns != expected_columns:
                raise ProfileSchemaError(f"Unexpected column layout for {table}.")
    finally:
        expected.close()


def _user_objects(connection: sqlite3.Connection) -> dict[tuple[str, str], str]:
    rows = connection.execute(
        "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
    ).fetchall()
    return {
        (str(row["type"]), str(row["name"])): _normalize_sql(str(row["sql"] or ""))
        for row in rows
    }


def _normalize_sql(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().rstrip(";")).casefold()


def _column_signature(connection: sqlite3.Connection, table: str) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (
            str(row["name"]),
            str(row["type"] or "").upper(),
            int(row["notnull"]),
            row["dflt_value"],
            int(row["pk"]),
        )
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    )


def _read_portable_snapshot(connection: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    schema = _portable_schema()
    snapshot: dict[str, list[dict[str, Any]]] = {}
    for table in _TABLE_NAMES:
        columns = tuple(item[0] for item in schema[table])
        limit = _ROW_LIMITS[table]
        rows = connection.execute(
            f"SELECT {', '.join(columns)} FROM {table} LIMIT {limit + 1}"
        ).fetchall()
        if len(rows) > limit:
            raise ProfileSchemaError(f"Profile table {table} exceeds the allowed row limit ({limit}).")
        snapshot[table] = [dict(row) for row in rows]
    return snapshot


def _portable_schema() -> dict[str, tuple[tuple[str, str, int, Any, int], ...]]:
    global _PORTABLE_SCHEMA_CACHE
    if _PORTABLE_SCHEMA_CACHE is not None:
        return _PORTABLE_SCHEMA_CACHE
    connection = sqlite3.connect(":memory:")
    try:
        _create_schema(connection)
        connection.row_factory = sqlite3.Row
        _PORTABLE_SCHEMA_CACHE = {
            table: tuple(
                (
                    str(row["name"]),
                    str(row["type"] or "").upper(),
                    int(row["notnull"]),
                    row["dflt_value"],
                    int(row["pk"]),
                )
                for row in _column_rows(connection, table)
            )
            for table in _TABLE_NAMES
        }
        return _PORTABLE_SCHEMA_CACHE
    finally:
        connection.close()


def _column_rows(connection: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    connection.row_factory = sqlite3.Row
    return connection.execute(f"PRAGMA table_info({table})").fetchall()


def _validate_portable_storage(snapshot: dict[str, list[dict[str, Any]]]) -> None:
    schema = _portable_schema()
    for table, rows in snapshot.items():
        columns = schema[table]
        for row_index, row in enumerate(rows):
            for column, declared_type, not_null, _default, _primary_key in columns:
                value = row[column]
                if value is None:
                    if not_null:
                        raise ProfileSchemaError(f"{table}.{column} cannot be null (row {row_index}).")
                    continue
                if declared_type == "INTEGER":
                    if type(value) is not int:
                        raise ProfileSchemaError(f"{table}.{column} must use SQLite INTEGER storage.")
                elif declared_type == "REAL":
                    if type(value) not in {int, float} or not math.isfinite(float(value)):
                        raise ProfileSchemaError(f"{table}.{column} must be a finite SQLite number.")
                elif declared_type == "TEXT":
                    if not isinstance(value, str):
                        raise ProfileSchemaError(f"{table}.{column} must use SQLite TEXT storage.")
                    max_length = _TEXT_LIMITS.get((table, column), 4096)
                    if len(value) > max_length or "\x00" in value:
                        raise ProfileSchemaError(f"{table}.{column} exceeds the text limit or contains NUL.")
                    if contains_absolute_local_path(value):
                        raise ProfileSchemaError(f"{table}.{column} contains a local filesystem path.")
                else:
                    raise ProfileSchemaError(f"Unsupported declared storage type for {table}.{column}.")


def _validate_int_range(
    value: Any,
    minimum: int,
    maximum: int,
    field: str,
    *,
    nullable: bool = False,
) -> None:
    if value is None and nullable:
        return
    if type(value) is not int or not minimum <= value <= maximum:
        raise ProfileSchemaError(f"{field} must be an integer from {minimum} through {maximum}.")


def _validate_float_range(
    value: Any,
    minimum: float,
    maximum: float,
    field: str,
    *,
    nullable: bool = False,
) -> None:
    if value is None and nullable:
        return
    if type(value) not in {int, float} or not math.isfinite(float(value)) or not minimum <= value <= maximum:
        raise ProfileSchemaError(f"{field} must be a finite number from {minimum:g} through {maximum:g}.")


def _validate_slice_rows(
    snapshot: dict[str, list[dict[str, Any]]],
    deck_presets: tuple[PvpDeckPreset, ...] | None,
) -> None:
    _validate_portable_storage(snapshot)
    for table in _TABLE_NAMES:
        ids = [row["id"] for row in snapshot[table] if "id" in row and table in {
            "account_weapon_observed_stacks", "artifacts", "artifact_builds"
        }]
        if ids and ids != list(range(1, len(ids) + 1)):
            raise ProfileSchemaError(f"{table} ids must be compact package-local ids starting at 1.")

    character_ids = {int(row["character_id"]) for row in snapshot["account_characters"]}
    weapon_fingerprints = [str(row["weapon_fingerprint"] or "") for row in snapshot["account_weapon_observed_stacks"]]
    weapon_ids = [str(row["weapon_id"] or "") for row in snapshot["account_weapon_observed_stacks"]]
    if any(not value for value in weapon_fingerprints) or len(set(weapon_fingerprints)) != len(weapon_fingerprints):
        raise ProfileSchemaError("Weapon fingerprints must be non-empty and unique.")
    if any(not value for value in weapon_ids):
        raise ProfileSchemaError("Weapon ids must be non-empty.")
    if deck_presets is not None and character_ids != set(_deck_character_ids(deck_presets)):
        raise ProfileSchemaError("Account character rows do not exactly match the exported deck characters.")

    for row in snapshot["character_identity"]:
        traits = _safe_identity(row)
        if int(row["character_id"]) not in character_ids:
            raise ProfileSchemaError("Character identity references an unknown account character.")
        if traits["traits_json"] != row["traits_json"]:
            raise ProfileSchemaError("Character identity traits must use canonical checked JSON.")
    for table in ("account_character_talents", "account_character_constellations"):
        if any(int(row["character_id"]) not in character_ids for row in snapshot[table]):
            raise ProfileSchemaError(f"{table} contains a row for an unknown character.")
    for row in snapshot["account_characters"]:
        _validate_int_range(row["rarity"], 1, 5, "character rarity", nullable=True)
        _validate_int_range(row["level"], 1, 100, "character level", nullable=True)
        _validate_int_range(row["constellation"], 0, 6, "character constellation", nullable=True)
        _validate_int_range(row["weapon_type"], 1, 5, "character weapon type", nullable=True)
        for field in ("base_hp", "base_atk", "base_def", "ascension_bonus_value"):
            _validate_float_range(row[field], 0.0, 1_000_000_000.0, f"character {field}", nullable=True)
    for row in snapshot["account_character_talents"]:
        _validate_int_range(row["skill_id"], 1, 2**63 - 1, "talent skill id")
        _validate_int_range(row["skill_type"], 0, 20, "talent type", nullable=True)
        _validate_int_range(row["level"], 0, 20, "talent level", nullable=True)
        _validate_int_range(row["is_unlock"], 0, 1, "talent unlock flag", nullable=True)
    for row in snapshot["account_character_constellations"]:
        _validate_int_range(row["pos"], 1, 6, "constellation position")
        _validate_int_range(row["is_actived"], 0, 1, "constellation active flag", nullable=True)
    for row in snapshot["account_weapon_observed_stacks"]:
        _validate_int_range(row["weapon_type"], 1, 5, "weapon type", nullable=True)
        _validate_int_range(row["rarity"], 1, 5, "weapon rarity", nullable=True)
        _validate_int_range(row["level"], 1, 100, "weapon level", nullable=True)
        _validate_int_range(row["refinement"], 1, 5, "weapon refinement", nullable=True)
        _validate_int_range(row["promote_level"], 0, 10, "weapon promotion level", nullable=True)
        _validate_float_range(row["base_atk"], 0.0, 1_000_000.0, "weapon base attack", nullable=True)
        _validate_float_range(
            row["secondary_stat_value"], 0.0, 1_000_000.0,
            "weapon secondary stat", nullable=True,
        )
        _validate_int_range(row["known_count"], 1, 10000, "weapon known count")

    weapon_ids = {
        int(row["weapon_id"])
        for row in snapshot["account_weapon_observed_stacks"]
        if str(row["weapon_id"]).isdecimal()
        and 0 < int(row["weapon_id"]) <= 2**63 - 1
    }
    weapon_pairs = {
        (int(row["weapon_id"]), int(row["refinement"]))
        for row in snapshot["account_weapon_observed_stacks"]
        if str(row["weapon_id"]).isdecimal()
        and int(row["weapon_id"]) in weapon_ids
        and row["refinement"] is not None
    }
    for row in snapshot["weapon_display_stat_effects"]:
        _validate_int_range(row["weapon_id"], 1, 2**63 - 1, "weapon effect id")
        _validate_int_range(row["refinement"], 1, 5, "weapon effect refinement")
        if (row["weapon_id"], row["refinement"]) not in weapon_pairs:
            raise ProfileSchemaError("Weapon effect does not match an exported weapon stack.")
        if row["stat_key"] not in STATIC_DISPLAY_STAT_KEYS:
            raise ProfileSchemaError("Weapon effect has an unsupported stat key.")
        if row["value_type"] not in {VALUE_TYPE_FLAT, VALUE_TYPE_PERCENT_POINTS}:
            raise ProfileSchemaError("Weapon effect has an unsupported value type.")
        _validate_float_range(row["value"], -1_000_000.0, 1_000_000.0, "weapon effect value")
    for row in snapshot["weapon_passive_tooltips"]:
        _validate_int_range(row["weapon_id"], 1, 2**63 - 1, "weapon tooltip id")
        if row["weapon_id"] not in weapon_ids:
            raise ProfileSchemaError("Weapon tooltip does not match an exported weapon stack.")
        if not re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8}){0,3}", row["lang"]):
            raise ProfileSchemaError("Weapon tooltip language is invalid.")
        if not row["passive_name"].strip() and not row["passive_text"].strip():
            raise ProfileSchemaError("Weapon tooltip has no passive text.")

    artifacts_by_id = {int(row["id"]): row for row in snapshot["artifacts"]}
    if any(int(row["artifact_id"]) not in artifacts_by_id for row in snapshot["artifact_substats"]):
        raise ProfileSchemaError("Artifact substats reference an unknown artifact.")
    for row in snapshot["artifacts"]:
        if not str(row["name"] or "").strip() or int(row["pos"]) not in {1, 2, 3, 4, 5}:
            raise ProfileSchemaError("Artifact identity or position is invalid.")
        _validate_int_range(row["relic_id"], 1, 2**63 - 1, "artifact relic id", nullable=True)
        _validate_int_range(row["set_id"], 1, 2**63 - 1, "artifact set id", nullable=True)
        _validate_int_range(row["rarity"], 1, 5, "artifact rarity", nullable=True)
        _validate_int_range(row["level"], 0, 20, "artifact level", nullable=True)
        _validate_int_range(row["main_property_type"], 0, 2**31 - 1, "artifact main stat type", nullable=True)
    for row in snapshot["artifact_substats"]:
        _validate_int_range(row["slot_index"], 0, 3, "artifact substat slot index")
        _validate_int_range(row["property_type"], 0, 2**31 - 1, "artifact substat type", nullable=True)
        _validate_int_range(row["times"], 0, 10, "artifact substat roll count", nullable=True)
    for row in snapshot["artifact_sets"]:
        _validate_int_range(row["hoyolab_set_id"], 1, 2**63 - 1, "artifact HoYoLAB set id", nullable=True)

    set_ids = {str(row["set_uid"]) for row in snapshot["artifact_sets"]}
    artifact_set_ids = {str(row["set_uid"]) for row in snapshot["artifacts"] if row["set_uid"]}
    if set_ids != artifact_set_ids:
        raise ProfileSchemaError("Artifact set catalog does not exactly match referenced artifact sets.")
    for table in ("artifact_set_names", "artifact_set_bonus_descriptions"):
        if any(str(row["set_uid"]) not in set_ids for row in snapshot[table]):
            raise ProfileSchemaError(f"{table} references a set missing from the catalog.")

    builds = {int(row["id"]) for row in snapshot["artifact_builds"]}
    targets_by_build: dict[int, int] = defaultdict(int)
    for row in snapshot["artifact_build_targets"]:
        build_id = int(row["build_id"])
        character_id = int(row["character_id"])
        if build_id not in builds or character_id not in character_ids or row["target_type"] != "character":
            raise ProfileSchemaError("Build target references an unknown build or character.")
        targets_by_build[build_id] += 1
    ready_keys = {
        str(row["gcsim_character_key"])
        for row in snapshot["account_characters"]
        if row["gcsim_character_key_status"] == "ready" and row["gcsim_character_key"]
    }
    for row in snapshot["artifact_build_gcsim_targets"]:
        build_id = int(row["build_id"])
        if build_id not in builds or row["gcsim_character_key"] not in ready_keys:
            raise ProfileSchemaError("GCSIM build target does not match an exported ready character key.")
        targets_by_build[build_id] += 1
    if builds != set(targets_by_build):
        raise ProfileSchemaError("Every saved build must target at least one exported character.")

    for row in snapshot["artifact_build_slots"]:
        build_id = int(row["build_id"])
        artifact_id = int(row["artifact_id"])
        pos = int(row["pos"])
        if build_id not in builds or artifact_id not in artifacts_by_id:
            raise ProfileSchemaError("Build slots reference an unknown build or artifact.")
        if pos != int(artifacts_by_id[artifact_id]["pos"]):
            raise ProfileSchemaError("A build slot position does not match its artifact.")


def _snapshot_counts(snapshot: dict[str, list[dict[str, Any]]], deck_count: int) -> dict[str, int]:
    return {
        "deck_count": deck_count,
        "character_count": len(snapshot["account_characters"]),
        "talent_count": len(snapshot["account_character_talents"]),
        "constellation_count": len(snapshot["account_character_constellations"]),
        "weapon_stack_count": len(snapshot["account_weapon_observed_stacks"]),
        "weapon_effect_count": len(snapshot["weapon_display_stat_effects"]),
        "weapon_tooltip_count": len(snapshot["weapon_passive_tooltips"]),
        "identity_count": len(snapshot["character_identity"]),
        "artifact_set_count": len(snapshot["artifact_sets"]),
        "artifact_set_name_count": len(snapshot["artifact_set_names"]),
        "artifact_set_bonus_count": len(snapshot["artifact_set_bonus_descriptions"]),
        "artifact_count": len(snapshot["artifacts"]),
        "artifact_substat_count": len(snapshot["artifact_substats"]),
        "build_count": len(snapshot["artifact_builds"]),
        "build_slot_count": len(snapshot["artifact_build_slots"]),
        "build_target_count": len(snapshot["artifact_build_targets"]),
        "build_gcsim_target_count": len(snapshot["artifact_build_gcsim_targets"]),
    }


def _create_schema(connection: sqlite3.Connection) -> None:
    for ddl in _TABLE_DDL:
        connection.execute(ddl)
    connection.execute(f"PRAGMA user_version = {PROFILE_SLICE_SCHEMA_VERSION}")


def _insert_snapshot(connection: sqlite3.Connection, snapshot: dict[str, list[dict[str, Any]]]) -> None:
    for table in _TABLE_NAMES:
        rows = snapshot[table]
        if not rows:
            continue
        columns = tuple(rows[0])
        placeholders = ", ".join("?" for _ in columns)
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
        connection.executemany(sql, [tuple(row[column] for column in columns) for row in rows])


def _hydrate_runtime_db(
    connection: sqlite3.Connection,
    snapshot: dict[str, list[dict[str, Any]]],
    character_paths: Mapping[str, str],
    weapon_paths: Mapping[str, str],
) -> None:
    def insert(table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        columns = tuple(rows[0])
        placeholders = ", ".join("?" for _ in columns)
        connection.executemany(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
            [tuple(row[column] for column in columns) for row in rows],
        )

    characters = []
    for row in snapshot["account_characters"]:
        characters.append({
            **row,
            "icon_url": "",
            "side_icon_url": "",
            "portrait_path": "",
            "side_icon_path": character_paths.get(str(row["character_id"]), ""),
            "source_metadata_json": "{}",
            "warnings_json": "[]",
            "first_seen_at": None,
            "last_seen_at": None,
            "updated_at": None,
        })
    insert("account_characters", characters)

    insert("account_character_talents", [{
        **row, "icon_url": "", "source_metadata_json": "{}", "warnings_json": "[]",
        "first_seen_at": None, "last_seen_at": None, "updated_at": None,
    } for row in snapshot["account_character_talents"]])
    insert("account_character_constellations", [{
        **row, "source_metadata_json": "{}", "warnings_json": "[]",
        "first_seen_at": None, "last_seen_at": None, "updated_at": None,
    } for row in snapshot["account_character_constellations"]])
    insert("character_identity", [{
        **row, "source_metadata_json": "{}", "updated_at": None,
    } for row in snapshot["character_identity"]])

    insert("account_weapon_observed_stacks", [{
        **row,
        "icon_url": "",
        "base_atk_raw": "",
        "secondary_stat_value_raw": "",
        "icon_path": weapon_paths.get(str(row["weapon_id"]), ""),
        "first_seen_at": None,
        "last_seen_at": None,
        "source_metadata_json": "{}",
        "warnings_json": "[]",
    } for row in snapshot["account_weapon_observed_stacks"]])
    insert("weapon_display_stat_effects", [{
        **row, "weapon_catalog_entry_page_id": None, "updated_at": None,
    } for row in snapshot["weapon_display_stat_effects"]])
    insert("weapon_passive_tooltips", [{
        **row, "weapon_catalog_entry_page_id": None, "updated_at": None,
        "source": "",
    } for row in snapshot["weapon_passive_tooltips"]])

    insert("artifact_sets", [{
        **row, "source": "hoyowiki", "updated_at": "",
    } for row in snapshot["artifact_sets"]])
    insert("artifact_set_names", [{**row, "updated_at": ""} for row in snapshot["artifact_set_names"]])
    insert("artifact_set_bonus_descriptions", [{
        **row, "updated_at": "",
    } for row in snapshot["artifact_set_bonus_descriptions"]])
    # Artifact set effects are reconstructed from included descriptions. Weapon
    # effects and tooltips above are the selected, validated source-derived rows.
    from hoyolab_export.display_stat_effects import rebuild_artifact_set_display_stat_effects

    rebuild_artifact_set_display_stat_effects(connection)

    insert("artifacts", [{
        "id": row["id"],
        "fingerprint": f"pvp-profile-artifact-{row['id']}",
        "content_fingerprint": None,
        "relic_id": row["relic_id"],
        "name": row["name"],
        "set_id": row["set_id"],
        "set_uid": row["set_uid"],
        "set_name": row["set_name"],
        "pos": row["pos"],
        "pos_name": row["pos_name"],
        "rarity": row["rarity"],
        "level": row["level"],
        "main_property_type": row["main_property_type"],
        "main_property_name": row["main_property_name"],
        "main_property_value": row["main_property_value"],
        "first_seen_at": "",
        "last_seen_at": "",
        "import_source": None,
        "import_format": None,
        "import_batch_id": None,
        "json_imported": 0,
    } for row in snapshot["artifacts"]])
    insert("artifact_substats", snapshot["artifact_substats"])
    insert("artifact_builds", [{
        "id": row["id"], "name": row["name"], "character_id": None,
        "character_name": None, "notes": None, "created_at": "", "updated_at": "",
    } for row in snapshot["artifact_builds"]])
    insert("artifact_build_slots", snapshot["artifact_build_slots"])
    insert("artifact_build_targets", snapshot["artifact_build_targets"])
    insert("artifact_build_gcsim_targets", snapshot["artifact_build_gcsim_targets"])


def _normalize_paths(paths: Mapping[str, Path], expected_keys: set[str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in paths.items():
        normalized_key = str(key).strip()
        if not normalized_key or normalized_key in normalized:
            raise ProfileSchemaError("Asset path mapping has an empty or duplicate key.")
        path = Path(value)
        if not str(path).strip():
            raise ProfileSchemaError(f"Asset path for {normalized_key!r} is empty.")
        if not path.is_absolute():
            raise ProfileSchemaError(f"Asset path for {normalized_key!r} must be absolute.")
        absolute = path.resolve()
        if not absolute.is_absolute():
            raise ProfileSchemaError(f"Asset path for {normalized_key!r} must be absolute.")
        if normalized_key in expected_keys:
            normalized[normalized_key] = str(absolute)
    return normalized


def _require_source_columns(connection: sqlite3.Connection) -> None:
    for table, required_columns in _SOURCE_COLUMNS.items():
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
        actual = {str(row[1]) for row in rows}
        optional = _OPTIONAL_SOURCE_COLUMNS.get(table, frozenset())
        missing = set(required_columns).difference(actual, optional)
        if missing:
            raise ProfileSchemaError(
                f"Source database is missing {table} columns: " + ", ".join(sorted(missing))
            )


def _select_optional_weapon_rows(
    connection: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
    weapon_ids: set[int],
) -> list[dict[str, Any]]:
    if not weapon_ids:
        return []
    table_row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    if table_row is None:
        return []
    available = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
    missing = set(columns) - available
    if missing:
        raise ProfileSchemaError(
            f"Source database is missing {table} columns: " + ", ".join(sorted(missing))
        )
    rows: list[dict[str, Any]] = []
    sorted_ids = sorted(weapon_ids)
    for offset in range(0, len(sorted_ids), 400):
        chunk = sorted_ids[offset:offset + 400]
        placeholders = ", ".join("?" for _ in chunk)
        rows.extend(dict(row) for row in connection.execute(
            f"SELECT {', '.join(columns)} FROM {table} WHERE weapon_id IN ({placeholders})",
            tuple(chunk),
        ))
        if len(rows) > _ROW_LIMITS[table]:
            raise ProfileSchemaError(f"Source table {table} exceeds the allowed row limit.")
    return rows


def _select_rows_for_ids(
    connection: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
    key_column: str,
    values: set[int] | tuple[int, ...] | list[int],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    values = sorted(set(values))
    for offset in range(0, len(values), 400):
        chunk = values[offset:offset + 400]
        if not chunk:
            continue
        placeholders = ", ".join("?" for _ in chunk)
        projection = _source_projection(connection, table, columns)
        rows = connection.execute(
            f"SELECT {projection} FROM {table} WHERE {key_column} IN ({placeholders})",
            tuple(chunk),
        ).fetchall()
        result.extend(dict(row) for row in rows)
        limit = _ROW_LIMITS.get(table)
        if limit is not None and len(result) > limit:
            raise ProfileSchemaError(f"Source table {table} exceeds the allowed row limit ({limit}).")
    return result


def _select_rows_for_texts(
    connection: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
    key_column: str,
    values: set[str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    values = sorted(value for value in values if value)
    for offset in range(0, len(values), 400):
        chunk = values[offset:offset + 400]
        if not chunk:
            continue
        placeholders = ", ".join("?" for _ in chunk)
        projection = _source_projection(connection, table, columns)
        rows = connection.execute(
            f"SELECT {projection} FROM {table} WHERE {key_column} IN ({placeholders})",
            tuple(chunk),
        ).fetchall()
        result.extend(dict(row) for row in rows)
        limit = _ROW_LIMITS.get(table)
        if limit is not None and len(result) > limit:
            raise ProfileSchemaError(f"Source table {table} exceeds the allowed row limit ({limit}).")
    return result


def _select_all_rows(
    connection: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
) -> list[dict[str, Any]]:
    projection = _source_projection(connection, table, columns)
    limit = _ROW_LIMITS.get(table)
    suffix = f" LIMIT {limit + 1}" if limit is not None else ""
    rows = connection.execute(f"SELECT {projection} FROM {table}{suffix}").fetchall()
    if limit is not None and len(rows) > limit:
        raise ProfileSchemaError(f"Source table {table} exceeds the allowed row limit ({limit}).")
    return [dict(row) for row in rows]


def _source_projection(
    connection: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
) -> str:
    actual = {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    optional = _OPTIONAL_SOURCE_COLUMNS.get(table, frozenset())
    projection: list[str] = []
    for column in columns:
        if column in actual:
            projection.append(column)
        elif column in optional:
            projection.append(f"NULL AS {column}")
        else:
            raise ProfileSchemaError(f"Source database is missing {table}.{column}.")
    return ", ".join(projection)


def _deck_character_ids(deck_presets: tuple[PvpDeckPreset, ...]) -> tuple[int, ...]:
    ids = {int(character_id) for preset in deck_presets for character_id in preset.character_ids}
    if len(ids) > 512:
        raise ProfileSchemaError("A PvP profile may contain at most 512 distinct deck characters.")
    return tuple(sorted(ids))


def _artifact_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    substats = tuple(
        (
            _sort_value(row2.get("property_type")), _sort_value(row2.get("property_name")),
            _sort_value(row2.get("value")), _sort_value(row2.get("times"))
        )
        for row2 in row.get("_substats", [])
    )
    return (
        str(row.get("set_uid") or ""), int(row["pos"]), _sort_value(row.get("rarity")),
        _sort_value(row.get("level")), _sort_value(row.get("main_property_type")),
        str(row.get("main_property_value") or ""), substats,
        str(row.get("name") or ""),
    )


def _sort_value(value: Any) -> tuple[bool, str]:
    return (value is not None, "" if value is None else str(value))


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ProfileSchemaError(f"{field} must be non-empty.")
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any, field: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ProfileSchemaError(f"{field} must be an integer or null.") from exc


def _optional_finite_float(value: Any, field: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ProfileSchemaError(f"{field} must be a finite number or null.") from exc
    if not math.isfinite(number):
        raise ProfileSchemaError(f"{field} must be a finite number or null.")
    return number


def _optional_catalog_id(value: Any, field: str) -> int | None:
    result = _optional_int(value, field)
    if result is None or result == 0:
        return None
    if result < 0:
        raise ProfileSchemaError(f"{field} must be positive, zero, or null.")
    return result


def _positive_int(value: Any, field: str) -> int:
    result = _optional_int(value, field)
    if result is None or result <= 0:
        raise ProfileSchemaError(f"{field} must be a positive integer.")
    return result


def _bounded_int(value: Any, minimum: int, maximum: int, field: str) -> int:
    result = _positive_int(value, field) if minimum >= 1 else _optional_int(value, field)
    if result is None or not minimum <= result <= maximum:
        raise ProfileSchemaError(f"{field} must be between {minimum} and {maximum}.")
    return result


def _optional_bool(value: Any, field: str) -> int | None:
    parsed = _optional_int(value, field)
    if parsed is None:
        return None
    if parsed not in {0, 1}:
        raise ProfileSchemaError(f"{field} must be 0, 1, or null.")
    return parsed
