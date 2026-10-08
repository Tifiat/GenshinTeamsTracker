"""Build a public, isolated SQLite fixture for optimizer button smoke checks.

The only database writes go to the caller-provided root. Character, weapon,
and set identities are checked against the active local GCSIM source catalogs;
the GCSIM executable is never launched here.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from hoyolab_export.artifact_db import create_build_preset, init_db
from hoyolab_export.artifact_fingerprint import artifact_content_fingerprint
from hoyolab_export.stat_normalization import STAT_MAPPINGS_BY_NORMALIZED_KEY
from run_workspace.gcsim.artifact_set_catalog import load_gcsim_artifact_set_catalog
from run_workspace.gcsim.engine_store import GcsimEngineStore
from run_workspace.gcsim.virtual_roster import (
    GcsimVirtualSetBonus,
    GcsimVirtualSlotOverride,
    compatible_weapons,
    load_active_virtual_artifact_set_choices,
    load_active_virtual_roster_catalog,
)


_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "gcsim_optimizer_go_v1"
    / "button_smoke_team_v1.json"
)
_FIXTURE_TIMESTAMP = "2026-01-01T00:00:00+00:00"
_SLOT_KEY_BY_POSITION = {
    1: "flower",
    2: "plume",
    3: "sands",
    4: "goblet",
    5: "circlet",
}


def create_button_smoke_fixture(
    root: Path,
) -> tuple[Path, dict[str, Any], str, str]:
    """Create one temporary account-shaped DB and selected team from public data.

    ``root`` belongs to the caller and is expected to be a temporary directory.
    Existing fixture DBs are preserved; use a fresh root for each invocation.
    The returned SHA-256 is over LF-normalized public JSON bytes, so Windows
    checkout line-ending conversion does not change the fixture identity.
    """

    fixture_bytes = _FIXTURE_PATH.read_bytes()
    fixture = json.loads(fixture_bytes)
    if not isinstance(fixture, dict) or fixture.get("schema_kind") != (
        "gcsim_optimizer_button_smoke_team_v1"
    ):
        raise ValueError(f"Unsupported optimizer button fixture: {_FIXTURE_PATH}")

    root_path = Path(root).expanduser().resolve()
    root_path.mkdir(parents=True, exist_ok=True)
    db_path = root_path / "button-smoke-artifacts.db"
    if db_path.exists():
        raise FileExistsError(f"Refusing to replace caller-owned fixture DB: {db_path}")

    store = GcsimEngineStore(os.environ.get("GTT_OPTIMIZER_BUTTON_ENGINE_STORE"))
    installation = store.get_active_engine()
    if installation is None:
        raise RuntimeError("Button smoke fixture requires an active local GCSIM engine.")
    roster = load_active_virtual_roster_catalog(store=store)
    characters_by_key = {
        item.gcsim_key.casefold(): item for item in roster.characters
    }
    weapons_by_key = {item.gcsim_key.casefold(): item for item in roster.weapons}
    set_catalog = load_gcsim_artifact_set_catalog(installation.path)

    inventory = fixture["artifact_inventory"]
    set_data = inventory["set"]
    set_name = str(set_data["english_name"])
    set_key = str(set_data["gcsim_key"]).casefold()
    set_capability = set_catalog.get(set_key)
    if (
        set_capability is None
        or not set_capability.registered
        or not set_capability.complete_four_piece_modeled
    ):
        raise ValueError(
            f"Active GCSIM source does not register a complete 4-piece {set_key!r} set."
        )

    character_rows = tuple(fixture["characters"])
    if len(character_rows) != 4:
        raise ValueError("Optimizer button fixture requires exactly four profiles.")

    artifact_rows: dict[int, list[int]] = {
        position: [] for position in _SLOT_KEY_BY_POSITION
    }
    selected_slots: list[dict[str, Any]] = []
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        init_db(connection)
        set_choices = load_active_virtual_artifact_set_choices(
            db_path,
            language="en-us",
            store=store,
        )
        set_choice = next(
            (
                item
                for item in set_choices
                if item.gcsim_key.casefold() == set_key
            ),
            None,
        )
        if set_choice is None or not set_choice.set_uid.strip():
            raise ValueError(
                f"Active GCSIM source has no virtual artifact-set choice for {set_key!r}."
            )
        set_uid = set_choice.set_uid
        set_bonus = GcsimVirtualSetBonus(
            set_uid=set_uid,
            display_name=set_name,
            gcsim_key=set_capability.key,
            piece_count=4,
        )

        for position, slot_key in _SLOT_KEY_BY_POSITION.items():
            main = inventory["main_stats_by_position"][str(position)]
            main_mapping = _stat_mapping(main["stat_key"])
            raw_substats = inventory["substats_by_position"][str(position)]
            for profile_index in range(4):
                artifact_id = profile_index * 5 + position
                substats = [
                    {
                        "property_type": _stat_mapping(item["stat_key"]).property_type,
                        "property_name": str(item["property_name"]),
                        "value": str(item["value"]),
                        "times": int(item.get("times", 1)),
                    }
                    for item in raw_substats
                ]
                content_fingerprint = artifact_content_fingerprint(
                    set_uid=set_uid,
                    pos=position,
                    rarity=int(inventory["rarity"]),
                    level=int(inventory["level"]),
                    main_property_type=main_mapping.property_type,
                    main_property_value=str(main["value"]),
                    substats=substats,
                )
                physical_fingerprint = hashlib.sha256(
                    f"public-button-smoke-v1:{artifact_id}".encode("utf-8")
                ).hexdigest()
                connection.execute(
                    """
                    INSERT INTO artifacts (
                        id, fingerprint, content_fingerprint, name, set_uid,
                        set_name, pos, pos_name, rarity, level,
                        main_property_type, main_property_name,
                        main_property_value, first_seen_at, last_seen_at,
                        import_source, import_format, json_imported
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        artifact_id,
                        physical_fingerprint,
                        content_fingerprint,
                        f"Synthetic button smoke artifact {artifact_id}",
                        set_uid,
                        set_name,
                        position,
                        slot_key,
                        int(inventory["rarity"]),
                        int(inventory["level"]),
                        main_mapping.property_type,
                        str(main["property_name"]),
                        str(main["value"]),
                        _FIXTURE_TIMESTAMP,
                        _FIXTURE_TIMESTAMP,
                        "public_button_smoke_fixture",
                        "gcsim_optimizer_button_smoke_v1",
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO artifact_substats (
                        artifact_id, slot_index, property_type, property_name,
                        value, times
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            artifact_id,
                            substat_index,
                            item["property_type"],
                            item["property_name"],
                            item["value"],
                            item["times"],
                        )
                        for substat_index, item in enumerate(substats)
                    ],
                )
                artifact_rows[position].append(artifact_id)

        for profile_index, profile in enumerate(character_rows):
            character_key = str(profile["gcsim_key"]).casefold()
            weapon_key = str(profile["weapon_key"]).casefold()
            character = characters_by_key.get(character_key)
            weapon = weapons_by_key.get(weapon_key)
            if character is None or weapon is None:
                raise ValueError(
                    f"Active GCSIM catalog is missing fixture profile {character_key!r} "
                    f"or weapon {weapon_key!r}."
                )
            if weapon not in compatible_weapons(character, roster.weapons):
                raise ValueError(
                    f"Fixture weapon {weapon_key!r} is incompatible with {character_key!r}."
                )

            character_id = 900_001 + profile_index
            connection.execute(
                """
                INSERT INTO account_characters (
                    character_id, name, catalog_english_name,
                    gcsim_character_key, gcsim_character_key_status,
                    gcsim_character_key_method, updated_at
                ) VALUES (?, ?, ?, ?, 'ready', 'public_fixture_catalog', ?)
                """,
                (
                    character_id,
                    str(profile["display_name"]),
                    str(profile["display_name"]),
                    character.gcsim_key,
                    _FIXTURE_TIMESTAMP,
                ),
            )
            build_slots = {
                position: artifact_rows[position][profile_index]
                for position in _SLOT_KEY_BY_POSITION
            }
            build_name = f"Button smoke {profile['display_name']}"
            build_id = create_build_preset(
                connection,
                name=build_name,
                slots=build_slots,
                targets=[
                    {
                        "target_type": "gcsim_character",
                        "gcsim_character_key": character.gcsim_key,
                        "character_name": str(profile["display_name"]),
                    }
                ],
            )
            for position, slot_key in _SLOT_KEY_BY_POSITION.items():
                connection.execute(
                    """
                    INSERT INTO account_character_equipped_artifacts (
                        character_id, slot_key, artifact_id, source, updated_at
                    ) VALUES (?, ?, ?, 'manual', ?)
                    """,
                    (
                        character_id,
                        slot_key,
                        build_slots[position],
                        _FIXTURE_TIMESTAMP,
                    ),
                )

            override = GcsimVirtualSlotOverride(
                team_index=0,
                slot_index=profile_index,
                character_key=character.gcsim_key,
                character_name=str(profile["display_name"]),
                character_weapon_type=character.weapon_type,
                constellation=int(profile["constellation"]),
                refinement=int(profile["weapon_refinement"]),
                character_level=int(profile["character_level"]),
                talent_normal=int(profile["talents"]["normal"]),
                talent_skill=int(profile["talents"]["skill"]),
                talent_burst=int(profile["talents"]["burst"]),
                weapon_level=int(profile["weapon_level"]),
                weapon_promote_level=int(profile["weapon_promote_level"]),
                artifact_build_id=build_id,
                artifact_build_name=build_name,
                artifact_set_bonuses=(set_bonus,),
            ).with_weapon(weapon)
            selected_slots.append(
                {
                    "slot_index": profile_index,
                    "gcsim_virtual_override": override.to_dict(),
                }
            )

        connection.commit()
    finally:
        connection.close()

    selected_team = {"slots": selected_slots}
    return (
        db_path,
        selected_team,
        str(fixture["rotation"]),
        hashlib.sha256(fixture_bytes.replace(b"\r\n", b"\n")).hexdigest(),
    )


def _stat_mapping(stat_key: str):
    mapping = STAT_MAPPINGS_BY_NORMALIZED_KEY.get(str(stat_key).casefold())
    if mapping is None:
        raise ValueError(f"Fixture stat key is not in the project catalog: {stat_key!r}")
    return mapping
