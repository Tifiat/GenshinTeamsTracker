from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


ARTIFACT_SLOT_KEYS = ("flower", "plume", "sands", "goblet", "circlet")
ARTIFACT_SLOT_KEY_BY_POS = {
    1: "flower",
    2: "plume",
    3: "sands",
    4: "goblet",
    5: "circlet",
}
ARTIFACT_POS_BY_SLOT_KEY = {
    "flower": 1,
    "plume": 2,
    "feather": 2,
    "sands": 3,
    "goblet": 4,
    "circlet": 5,
}
EQUIPMENT_SOURCES = ("manual", "hoyolab_import", "preset_equip", "future_sync")
AUTO_APPLY_HOYOLAB_EQUIPMENT_ON_IMPORT_DEFAULT = True


class EquipmentError(ValueError):
    """Base class for controlled equipment service failures."""


class EquipmentNotFoundError(EquipmentError):
    """Raised when an equipment operation references missing local data."""


class EquipmentCompatibilityError(EquipmentError):
    """Raised when a character cannot equip the requested weapon type."""


class EquipmentCapacityError(EquipmentError):
    """Raised when an observed weapon stack has no available copies."""


@dataclass(frozen=True, slots=True)
class EquippedArtifactRecord:
    character_id: int
    slot_key: str
    artifact_id: int
    source: str
    source_import_batch_id: str | None
    observed_at: str | None
    updated_at: str


@dataclass(frozen=True, slots=True)
class EquippedWeaponRecord:
    character_id: int
    weapon_fingerprint: str
    source: str
    source_import_batch_id: str | None
    observed_at: str | None
    updated_at: str


@dataclass(frozen=True, slots=True)
class EquipmentChangeResult:
    operation: str
    changed: bool
    message: str = ""
    affected_character_ids: tuple[int, ...] = ()
    affected_artifact_ids: tuple[int, ...] = ()
    affected_weapon_fingerprints: tuple[str, ...] = ()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_account_equipment_storage(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS account_character_equipped_artifacts (
            character_id INTEGER NOT NULL,
            slot_key TEXT NOT NULL,
            artifact_id INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            source_import_batch_id TEXT,
            observed_at TEXT,
            updated_at TEXT NOT NULL,

            PRIMARY KEY (character_id, slot_key),
            UNIQUE (artifact_id),
            FOREIGN KEY (character_id) REFERENCES account_characters(character_id)
                ON DELETE CASCADE,
            FOREIGN KEY (artifact_id) REFERENCES artifacts(id)
                ON DELETE CASCADE,
            CHECK (slot_key IN ('flower', 'plume', 'sands', 'goblet', 'circlet')),
            CHECK (source IN ('manual', 'hoyolab_import', 'preset_equip', 'future_sync'))
        );

        CREATE INDEX IF NOT EXISTS idx_account_character_equipped_artifacts_character
            ON account_character_equipped_artifacts(character_id);

        CREATE TABLE IF NOT EXISTS account_character_equipped_weapons (
            character_id INTEGER PRIMARY KEY,
            weapon_fingerprint TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            source_import_batch_id TEXT,
            observed_at TEXT,
            updated_at TEXT NOT NULL,

            FOREIGN KEY (character_id) REFERENCES account_characters(character_id)
                ON DELETE CASCADE,
            FOREIGN KEY (weapon_fingerprint)
                REFERENCES account_weapon_observed_stacks(weapon_fingerprint)
                ON DELETE CASCADE,
            CHECK (source IN ('manual', 'hoyolab_import', 'preset_equip', 'future_sync'))
        );

        CREATE INDEX IF NOT EXISTS idx_account_character_equipped_weapons_fingerprint
            ON account_character_equipped_weapons(weapon_fingerprint);
        """
    )


def artifact_slot_key_from_pos(pos: int | str) -> str:
    try:
        normalized_pos = int(pos)
    except (TypeError, ValueError) as exc:
        raise EquipmentError(f"Invalid artifact slot position: {pos!r}") from exc
    slot_key = ARTIFACT_SLOT_KEY_BY_POS.get(normalized_pos)
    if slot_key is None:
        raise EquipmentError(f"Invalid artifact slot position: {pos!r}")
    return slot_key


def normalize_artifact_slot_key(slot_key: int | str) -> str:
    if isinstance(slot_key, int):
        return artifact_slot_key_from_pos(slot_key)
    value = str(slot_key or "").strip().lower()
    if value.isdigit():
        return artifact_slot_key_from_pos(int(value))
    normalized = "plume" if value == "feather" else value
    if normalized not in ARTIFACT_SLOT_KEYS:
        raise EquipmentError(f"Invalid artifact slot key: {slot_key!r}")
    return normalized


def equip_artifact(
    conn: sqlite3.Connection,
    character_id: int | str,
    artifact_id: int | str,
    *,
    source: str = "manual",
    source_import_batch_id: str | None = None,
    observed_at: str | None = None,
) -> EquipmentChangeResult:
    init_account_equipment_storage(conn)
    character_id_int = _validate_character(conn, character_id)
    artifact_id_int, slot_key = _artifact_slot(conn, artifact_id)
    source = _validate_source(source)
    now = utc_now()

    current_owner = _artifact_owner_row(conn, artifact_id_int)
    target_old = _equipped_artifact_row(conn, character_id_int, slot_key)

    if (
        current_owner is not None
        and int(current_owner["character_id"]) == character_id_int
        and str(current_owner["slot_key"]) == slot_key
    ):
        _upsert_equipped_artifact(
            conn,
            character_id_int,
            slot_key,
            artifact_id_int,
            source=source,
            source_import_batch_id=source_import_batch_id,
            observed_at=observed_at,
            updated_at=now,
        )
        return EquipmentChangeResult(
            operation="equip_artifact",
            changed=False,
            message="artifact_already_equipped",
            affected_character_ids=(character_id_int,),
            affected_artifact_ids=(artifact_id_int,),
        )

    affected_characters = {character_id_int}
    affected_artifacts = {artifact_id_int}
    if current_owner is not None:
        affected_characters.add(int(current_owner["character_id"]))
    if target_old is not None:
        affected_artifacts.add(int(target_old["artifact_id"]))

    conn.execute(
        """
        DELETE FROM account_character_equipped_artifacts
        WHERE artifact_id = ?
           OR (character_id = ? AND slot_key = ?)
        """,
        (artifact_id_int, character_id_int, slot_key),
    )

    _upsert_equipped_artifact(
        conn,
        character_id_int,
        slot_key,
        artifact_id_int,
        source=source,
        source_import_batch_id=source_import_batch_id,
        observed_at=observed_at,
        updated_at=now,
    )

    if current_owner is not None and target_old is not None:
        _upsert_equipped_artifact(
            conn,
            int(current_owner["character_id"]),
            slot_key,
            int(target_old["artifact_id"]),
            source=source,
            source_import_batch_id=source_import_batch_id,
            observed_at=observed_at,
            updated_at=now,
        )

    return EquipmentChangeResult(
        operation="equip_artifact",
        changed=True,
        affected_character_ids=tuple(sorted(affected_characters)),
        affected_artifact_ids=tuple(sorted(affected_artifacts)),
    )


def unequip_artifact_slot(
    conn: sqlite3.Connection,
    character_id: int | str,
    slot_key: int | str,
    *,
    source: str = "manual",
    source_import_batch_id: str | None = None,
    observed_at: str | None = None,
) -> EquipmentChangeResult:
    del source_import_batch_id, observed_at
    init_account_equipment_storage(conn)
    character_id_int = _validate_character(conn, character_id)
    slot_key_normalized = normalize_artifact_slot_key(slot_key)
    source = _validate_source(source)
    old = _equipped_artifact_row(conn, character_id_int, slot_key_normalized)
    if old is None:
        return EquipmentChangeResult(
            operation="unequip_artifact_slot",
            changed=False,
            message="slot_already_empty",
            affected_character_ids=(character_id_int,),
        )

    conn.execute(
        """
        DELETE FROM account_character_equipped_artifacts
        WHERE character_id = ? AND slot_key = ?
        """,
        (character_id_int, slot_key_normalized),
    )
    return EquipmentChangeResult(
        operation="unequip_artifact_slot",
        changed=True,
        message=source,
        affected_character_ids=(character_id_int,),
        affected_artifact_ids=(int(old["artifact_id"]),),
    )


def unequip_artifact(
    conn: sqlite3.Connection,
    artifact_id: int | str,
    *,
    source: str = "manual",
    source_import_batch_id: str | None = None,
    observed_at: str | None = None,
) -> EquipmentChangeResult:
    del source_import_batch_id, observed_at
    init_account_equipment_storage(conn)
    source = _validate_source(source)
    artifact_id_int = _validate_artifact(conn, artifact_id)
    owner = _artifact_owner_row(conn, artifact_id_int)
    if owner is None:
        return EquipmentChangeResult(
            operation="unequip_artifact",
            changed=False,
            message="artifact_already_unequipped",
            affected_artifact_ids=(artifact_id_int,),
        )

    conn.execute(
        """
        DELETE FROM account_character_equipped_artifacts
        WHERE artifact_id = ?
        """,
        (artifact_id_int,),
    )
    return EquipmentChangeResult(
        operation="unequip_artifact",
        changed=True,
        message=source,
        affected_character_ids=(int(owner["character_id"]),),
        affected_artifact_ids=(artifact_id_int,),
    )


def equip_weapon(
    conn: sqlite3.Connection,
    character_id: int | str,
    weapon_fingerprint: str,
    *,
    source: str = "manual",
    source_import_batch_id: str | None = None,
    observed_at: str | None = None,
) -> EquipmentChangeResult:
    init_account_equipment_storage(conn)
    character = _character_row(conn, character_id)
    if character is None:
        raise EquipmentNotFoundError(f"Unknown account character: {character_id!r}")
    character_id_int = int(character["character_id"])
    weapon = _weapon_stack_row(conn, weapon_fingerprint)
    if weapon is None:
        raise EquipmentNotFoundError(
            f"Unknown observed weapon stack: {weapon_fingerprint!r}"
        )
    _validate_weapon_compatibility(character, weapon)
    source = _validate_source(source)
    now = utc_now()
    current = get_equipped_weapon_for_character(conn, character_id_int)

    if current is not None and current.weapon_fingerprint == str(weapon_fingerprint):
        _upsert_equipped_weapon(
            conn,
            character_id_int,
            str(weapon_fingerprint),
            source=source,
            source_import_batch_id=source_import_batch_id,
            observed_at=observed_at,
            updated_at=now,
        )
        return EquipmentChangeResult(
            operation="equip_weapon",
            changed=False,
            message="weapon_already_equipped",
            affected_character_ids=(character_id_int,),
            affected_weapon_fingerprints=(str(weapon_fingerprint),),
        )

    assigned_count = get_weapon_assignment_count(conn, str(weapon_fingerprint))
    known_count = max(1, int(weapon["known_count"] or 1))
    if assigned_count >= known_count:
        return _equip_occupied_weapon_stack(
            conn,
            character,
            weapon,
            current,
            source=source,
            source_import_batch_id=source_import_batch_id,
            observed_at=observed_at,
            updated_at=now,
        )

    affected_fingerprints = {str(weapon_fingerprint)}
    if current is not None:
        affected_fingerprints.add(current.weapon_fingerprint)
    _upsert_equipped_weapon(
        conn,
        character_id_int,
        str(weapon_fingerprint),
        source=source,
        source_import_batch_id=source_import_batch_id,
        observed_at=observed_at,
        updated_at=now,
    )
    return EquipmentChangeResult(
        operation="equip_weapon",
        changed=True,
        affected_character_ids=(character_id_int,),
        affected_weapon_fingerprints=tuple(sorted(affected_fingerprints)),
    )


def _equip_occupied_weapon_stack(
    conn: sqlite3.Connection,
    target_character,
    selected_weapon,
    target_current: EquippedWeaponRecord | None,
    *,
    source: str,
    source_import_batch_id: str | None,
    observed_at: str | None,
    updated_at: str,
) -> EquipmentChangeResult:
    target_id = int(target_character["character_id"])
    selected_fingerprint = str(selected_weapon["weapon_fingerprint"])
    owners = tuple(
        owner_id
        for owner_id in list_equipped_weapon_owners(conn, selected_fingerprint)
        if int(owner_id) != target_id
    )
    if len(owners) != 1:
        raise EquipmentCapacityError(
            f"No available copy for observed weapon stack {selected_fingerprint!r}"
        )

    previous_owner_id = int(owners[0])
    previous_owner = _character_row(conn, previous_owner_id)
    if previous_owner is None:
        raise EquipmentNotFoundError(f"Unknown previous owner character: {previous_owner_id!r}")

    affected_fingerprints = {selected_fingerprint}
    if target_current is not None:
        target_current_weapon = _weapon_stack_row(conn, target_current.weapon_fingerprint)
        if target_current_weapon is None:
            raise EquipmentNotFoundError(
                f"Unknown observed weapon stack: {target_current.weapon_fingerprint!r}"
            )
        _validate_weapon_compatibility(previous_owner, target_current_weapon)
        affected_fingerprints.add(target_current.weapon_fingerprint)

    conn.execute(
        """
        DELETE FROM account_character_equipped_weapons
        WHERE character_id IN (?, ?)
        """,
        (target_id, previous_owner_id),
    )
    _upsert_equipped_weapon(
        conn,
        target_id,
        selected_fingerprint,
        source=source,
        source_import_batch_id=source_import_batch_id,
        observed_at=observed_at,
        updated_at=updated_at,
    )
    if target_current is not None:
        _upsert_equipped_weapon(
            conn,
            previous_owner_id,
            target_current.weapon_fingerprint,
            source=source,
            source_import_batch_id=source_import_batch_id,
            observed_at=observed_at,
            updated_at=updated_at,
        )

    return EquipmentChangeResult(
        operation="equip_weapon",
        changed=True,
        affected_character_ids=tuple(sorted((target_id, previous_owner_id))),
        affected_weapon_fingerprints=tuple(sorted(affected_fingerprints)),
    )


def unequip_weapon(
    conn: sqlite3.Connection,
    character_id: int | str,
    *,
    source: str = "manual",
    source_import_batch_id: str | None = None,
    observed_at: str | None = None,
) -> EquipmentChangeResult:
    del source_import_batch_id, observed_at
    init_account_equipment_storage(conn)
    character_id_int = _validate_character(conn, character_id)
    source = _validate_source(source)
    current = get_equipped_weapon_for_character(conn, character_id_int)
    if current is None:
        return EquipmentChangeResult(
            operation="unequip_weapon",
            changed=False,
            message="weapon_already_empty",
            affected_character_ids=(character_id_int,),
        )

    conn.execute(
        """
        DELETE FROM account_character_equipped_weapons
        WHERE character_id = ?
        """,
        (character_id_int,),
    )
    return EquipmentChangeResult(
        operation="unequip_weapon",
        changed=True,
        message=source,
        affected_character_ids=(character_id_int,),
        affected_weapon_fingerprints=(current.weapon_fingerprint,),
    )


def move_weapon_between_characters(
    conn: sqlite3.Connection,
    source_character_id: int | str,
    target_character_id: int | str,
    *,
    source: str = "manual",
    source_import_batch_id: str | None = None,
    observed_at: str | None = None,
) -> EquipmentChangeResult:
    init_account_equipment_storage(conn)
    source_character = _character_row(conn, source_character_id)
    target_character = _character_row(conn, target_character_id)
    if source_character is None:
        raise EquipmentNotFoundError(f"Unknown source character: {source_character_id!r}")
    if target_character is None:
        raise EquipmentNotFoundError(f"Unknown target character: {target_character_id!r}")
    source_id = int(source_character["character_id"])
    target_id = int(target_character["character_id"])
    if source_id == target_id:
        return EquipmentChangeResult(
            operation="move_weapon_between_characters",
            changed=False,
            message="same_character",
            affected_character_ids=(source_id,),
        )

    source_weapon = get_equipped_weapon_for_character(conn, source_id)
    if source_weapon is None:
        raise EquipmentNotFoundError(
            f"Source character has no equipped weapon: {source_character_id!r}"
        )
    target_weapon = get_equipped_weapon_for_character(conn, target_id)
    source_weapon_row = _weapon_stack_row(conn, source_weapon.weapon_fingerprint)
    if source_weapon_row is None:
        raise EquipmentNotFoundError(
            f"Unknown observed weapon stack: {source_weapon.weapon_fingerprint!r}"
        )
    _validate_weapon_compatibility(target_character, source_weapon_row)

    if target_weapon is not None:
        target_weapon_row = _weapon_stack_row(conn, target_weapon.weapon_fingerprint)
        if target_weapon_row is None:
            raise EquipmentNotFoundError(
                f"Unknown observed weapon stack: {target_weapon.weapon_fingerprint!r}"
            )
        _validate_weapon_compatibility(source_character, target_weapon_row)

    if target_weapon is not None and (
        target_weapon.weapon_fingerprint == source_weapon.weapon_fingerprint
    ):
        return EquipmentChangeResult(
            operation="move_weapon_between_characters",
            changed=False,
            message="matching_stack_already_assigned",
            affected_character_ids=(source_id, target_id),
            affected_weapon_fingerprints=(source_weapon.weapon_fingerprint,),
        )

    source = _validate_source(source)
    now = utc_now()
    conn.execute(
        """
        DELETE FROM account_character_equipped_weapons
        WHERE character_id IN (?, ?)
        """,
        (source_id, target_id),
    )
    _upsert_equipped_weapon(
        conn,
        target_id,
        source_weapon.weapon_fingerprint,
        source=source,
        source_import_batch_id=source_import_batch_id,
        observed_at=observed_at,
        updated_at=now,
    )
    affected_fingerprints = {source_weapon.weapon_fingerprint}
    if target_weapon is not None:
        affected_fingerprints.add(target_weapon.weapon_fingerprint)
        _upsert_equipped_weapon(
            conn,
            source_id,
            target_weapon.weapon_fingerprint,
            source=source,
            source_import_batch_id=source_import_batch_id,
            observed_at=observed_at,
            updated_at=now,
        )

    return EquipmentChangeResult(
        operation="move_weapon_between_characters",
        changed=True,
        affected_character_ids=tuple(sorted((source_id, target_id))),
        affected_weapon_fingerprints=tuple(sorted(affected_fingerprints)),
    )


def apply_hoyolab_artifact_equipment_observation(
    conn: sqlite3.Connection,
    character_id: int | str,
    artifact_id: int | str,
    *,
    import_batch_id: str | None = None,
    observed_at: str | None = None,
) -> EquipmentChangeResult:
    return equip_artifact(
        conn,
        character_id,
        artifact_id,
        source="hoyolab_import",
        source_import_batch_id=import_batch_id,
        observed_at=observed_at,
    )


def apply_hoyolab_weapon_equipment_observation(
    conn: sqlite3.Connection,
    character_id: int | str,
    weapon_fingerprint: str,
    *,
    import_batch_id: str | None = None,
    observed_at: str | None = None,
) -> EquipmentChangeResult:
    return equip_weapon(
        conn,
        character_id,
        weapon_fingerprint,
        source="hoyolab_import",
        source_import_batch_id=import_batch_id,
        observed_at=observed_at,
    )


def get_equipped_artifact_owner(
    conn: sqlite3.Connection,
    artifact_id: int | str,
) -> int | None:
    init_account_equipment_storage(conn)
    row = _artifact_owner_row(conn, int(artifact_id))
    return int(row["character_id"]) if row is not None else None


def list_equipped_artifacts(
    conn: sqlite3.Connection,
) -> tuple[EquippedArtifactRecord, ...]:
    init_account_equipment_storage(conn)
    rows = conn.execute(
        """
        SELECT *
        FROM account_character_equipped_artifacts
        ORDER BY character_id ASC, slot_key ASC
        """
    ).fetchall()
    return tuple(_equipped_artifact_record(row) for row in rows)


def list_equipped_artifacts_for_character(
    conn: sqlite3.Connection,
    character_id: int | str,
) -> tuple[EquippedArtifactRecord, ...]:
    init_account_equipment_storage(conn)
    rows = conn.execute(
        """
        SELECT *
        FROM account_character_equipped_artifacts
        WHERE character_id = ?
        ORDER BY slot_key ASC
        """,
        (int(character_id),),
    ).fetchall()
    return tuple(_equipped_artifact_record(row) for row in rows)


def get_weapon_assignment_count(
    conn: sqlite3.Connection,
    weapon_fingerprint: str,
) -> int:
    init_account_equipment_storage(conn)
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM account_character_equipped_weapons
        WHERE weapon_fingerprint = ?
        """,
        (str(weapon_fingerprint),),
    ).fetchone()
    return int(row["count"] if row is not None else 0)


def list_equipped_weapon_owners(
    conn: sqlite3.Connection,
    weapon_fingerprint: str,
) -> tuple[int, ...]:
    init_account_equipment_storage(conn)
    rows = conn.execute(
        """
        SELECT character_id
        FROM account_character_equipped_weapons
        WHERE weapon_fingerprint = ?
        ORDER BY character_id ASC
        """,
        (str(weapon_fingerprint),),
    ).fetchall()
    return tuple(int(row["character_id"]) for row in rows)


def list_equipped_weapons(
    conn: sqlite3.Connection,
) -> tuple[EquippedWeaponRecord, ...]:
    init_account_equipment_storage(conn)
    rows = conn.execute(
        """
        SELECT *
        FROM account_character_equipped_weapons
        ORDER BY character_id ASC
        """
    ).fetchall()
    return tuple(_equipped_weapon_record(row) for row in rows)


def get_equipped_weapon_for_character(
    conn: sqlite3.Connection,
    character_id: int | str,
) -> EquippedWeaponRecord | None:
    init_account_equipment_storage(conn)
    row = conn.execute(
        """
        SELECT *
        FROM account_character_equipped_weapons
        WHERE character_id = ?
        LIMIT 1
        """,
        (int(character_id),),
    ).fetchone()
    return _equipped_weapon_record(row) if row is not None else None


def list_preset_current_wearers(
    conn: sqlite3.Connection,
    build_id: int | str,
) -> tuple[int, ...]:
    init_account_equipment_storage(conn)
    rows = conn.execute(
        """
        SELECT DISTINCT equipped.character_id
        FROM artifact_build_slots AS slots
        JOIN account_character_equipped_artifacts AS equipped
            ON equipped.artifact_id = slots.artifact_id
        WHERE slots.build_id = ?
        ORDER BY equipped.character_id ASC
        """,
        (int(build_id),),
    ).fetchall()
    return tuple(int(row["character_id"]) for row in rows)


def _validate_source(source: str) -> str:
    value = str(source or "").strip() or "manual"
    if value not in EQUIPMENT_SOURCES:
        raise EquipmentError(f"Invalid equipment source: {source!r}")
    return value


def _character_row(conn: sqlite3.Connection, character_id: int | str):
    return conn.execute(
        """
        SELECT character_id, weapon_type, weapon_type_name
        FROM account_characters
        WHERE character_id = ?
        LIMIT 1
        """,
        (int(character_id),),
    ).fetchone()


def _validate_character(conn: sqlite3.Connection, character_id: int | str) -> int:
    row = _character_row(conn, character_id)
    if row is None:
        raise EquipmentNotFoundError(f"Unknown account character: {character_id!r}")
    return int(row["character_id"])


def _validate_artifact(conn: sqlite3.Connection, artifact_id: int | str) -> int:
    row = conn.execute(
        """
        SELECT id
        FROM artifacts
        WHERE id = ?
        LIMIT 1
        """,
        (int(artifact_id),),
    ).fetchone()
    if row is None:
        raise EquipmentNotFoundError(f"Unknown artifact id: {artifact_id!r}")
    return int(row["id"])


def _artifact_slot(
    conn: sqlite3.Connection,
    artifact_id: int | str,
) -> tuple[int, str]:
    row = conn.execute(
        """
        SELECT id, pos
        FROM artifacts
        WHERE id = ?
        LIMIT 1
        """,
        (int(artifact_id),),
    ).fetchone()
    if row is None:
        raise EquipmentNotFoundError(f"Unknown artifact id: {artifact_id!r}")
    return int(row["id"]), artifact_slot_key_from_pos(int(row["pos"]))


def _artifact_owner_row(conn: sqlite3.Connection, artifact_id: int):
    return conn.execute(
        """
        SELECT *
        FROM account_character_equipped_artifacts
        WHERE artifact_id = ?
        LIMIT 1
        """,
        (artifact_id,),
    ).fetchone()


def _equipped_artifact_row(
    conn: sqlite3.Connection,
    character_id: int,
    slot_key: str,
):
    return conn.execute(
        """
        SELECT *
        FROM account_character_equipped_artifacts
        WHERE character_id = ? AND slot_key = ?
        LIMIT 1
        """,
        (character_id, slot_key),
    ).fetchone()


def _weapon_stack_row(conn: sqlite3.Connection, weapon_fingerprint: str):
    return conn.execute(
        """
        SELECT weapon_fingerprint, weapon_type, weapon_type_name, known_count
        FROM account_weapon_observed_stacks
        WHERE weapon_fingerprint = ?
        LIMIT 1
        """,
        (str(weapon_fingerprint),),
    ).fetchone()


def _validate_weapon_compatibility(character, weapon) -> None:
    character_weapon_type = character["weapon_type"]
    weapon_type = weapon["weapon_type"]
    if character_weapon_type is None or weapon_type is None:
        return
    if int(character_weapon_type) != int(weapon_type):
        character_label = character["weapon_type_name"] or character_weapon_type
        weapon_label = weapon["weapon_type_name"] or weapon_type
        raise EquipmentCompatibilityError(
            f"Weapon type {weapon_label!r} is incompatible with character "
            f"weapon type {character_label!r}"
        )


def _upsert_equipped_artifact(
    conn: sqlite3.Connection,
    character_id: int,
    slot_key: str,
    artifact_id: int,
    *,
    source: str,
    source_import_batch_id: str | None,
    observed_at: str | None,
    updated_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO account_character_equipped_artifacts (
            character_id,
            slot_key,
            artifact_id,
            source,
            source_import_batch_id,
            observed_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(character_id, slot_key) DO UPDATE SET
            artifact_id = excluded.artifact_id,
            source = excluded.source,
            source_import_batch_id = excluded.source_import_batch_id,
            observed_at = excluded.observed_at,
            updated_at = excluded.updated_at
        """,
        (
            character_id,
            slot_key,
            artifact_id,
            source,
            source_import_batch_id,
            observed_at,
            updated_at,
        ),
    )


def _upsert_equipped_weapon(
    conn: sqlite3.Connection,
    character_id: int,
    weapon_fingerprint: str,
    *,
    source: str,
    source_import_batch_id: str | None,
    observed_at: str | None,
    updated_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO account_character_equipped_weapons (
            character_id,
            weapon_fingerprint,
            source,
            source_import_batch_id,
            observed_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(character_id) DO UPDATE SET
            weapon_fingerprint = excluded.weapon_fingerprint,
            source = excluded.source,
            source_import_batch_id = excluded.source_import_batch_id,
            observed_at = excluded.observed_at,
            updated_at = excluded.updated_at
        """,
        (
            character_id,
            weapon_fingerprint,
            source,
            source_import_batch_id,
            observed_at,
            updated_at,
        ),
    )


def _equipped_artifact_record(row) -> EquippedArtifactRecord:
    return EquippedArtifactRecord(
        character_id=int(row["character_id"]),
        slot_key=str(row["slot_key"]),
        artifact_id=int(row["artifact_id"]),
        source=str(row["source"]),
        source_import_batch_id=row["source_import_batch_id"],
        observed_at=row["observed_at"],
        updated_at=str(row["updated_at"]),
    )


def _equipped_weapon_record(row) -> EquippedWeaponRecord:
    return EquippedWeaponRecord(
        character_id=int(row["character_id"]),
        weapon_fingerprint=str(row["weapon_fingerprint"]),
        source=str(row["source"]),
        source_import_batch_id=row["source_import_batch_id"],
        observed_at=row["observed_at"],
        updated_at=str(row["updated_at"]),
    )
