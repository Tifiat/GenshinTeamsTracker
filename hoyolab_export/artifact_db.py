import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import PROJECT_ROOT


ARTIFACT_DB_PATH = PROJECT_ROOT / "data" / "artifacts.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect_db(db_path: str | Path = ARTIFACT_DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS artifact_sets (
            set_uid TEXT PRIMARY KEY,

            hoyowiki_entry_id TEXT NOT NULL UNIQUE,
            hoyolab_set_id INTEGER UNIQUE,
            artiscan_set_key TEXT UNIQUE,

            display_name TEXT,
            fallback_name TEXT NOT NULL,

            source TEXT NOT NULL DEFAULT 'hoyowiki',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS artifact_set_piece_icons (
            set_uid TEXT NOT NULL,
            pos INTEGER NOT NULL,

            icon_url TEXT NOT NULL,
            local_path TEXT NOT NULL,
            updated_at TEXT NOT NULL,

            PRIMARY KEY (set_uid, pos),
            FOREIGN KEY (set_uid) REFERENCES artifact_sets(set_uid) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS artifact_set_names (
            set_uid TEXT NOT NULL,
            lang TEXT NOT NULL,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            updated_at TEXT NOT NULL,

            PRIMARY KEY (set_uid, lang),
            FOREIGN KEY (set_uid) REFERENCES artifact_sets(set_uid) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT NOT NULL UNIQUE,

            relic_id INTEGER,
            name TEXT NOT NULL,

            set_id INTEGER,
            set_uid TEXT,
            set_name TEXT,

            pos INTEGER NOT NULL,
            pos_name TEXT,

            rarity INTEGER,
            level INTEGER,

            main_property_type INTEGER,
            main_property_name TEXT,
            main_property_value TEXT,

            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS artifact_substats (
            artifact_id INTEGER NOT NULL,
            slot_index INTEGER NOT NULL,

            property_type INTEGER,
            property_name TEXT,
            value TEXT,
            times INTEGER,

            PRIMARY KEY (artifact_id, slot_index),
            FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS artifact_equipment (
            artifact_id INTEGER NOT NULL,

            character_id INTEGER NOT NULL,
            character_name TEXT NOT NULL,

            pos INTEGER NOT NULL,
            imported_at TEXT NOT NULL,

            PRIMARY KEY (character_id, pos),
            FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS artifact_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            color TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS artifact_tag_links (
            artifact_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,

            PRIMARY KEY (artifact_id, tag_id),
            FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES artifact_tags(id) ON DELETE CASCADE
        );
        

        CREATE INDEX IF NOT EXISTS idx_artifacts_set_id
            ON artifacts(set_id);

        CREATE INDEX IF NOT EXISTS idx_artifact_set_piece_icons_pos
            ON artifact_set_piece_icons(pos);

        CREATE INDEX IF NOT EXISTS idx_artifact_set_names_lang_normalized
            ON artifact_set_names(lang, normalized_name);
        
        CREATE INDEX IF NOT EXISTS idx_artifacts_pos
            ON artifacts(pos);

        CREATE INDEX IF NOT EXISTS idx_artifacts_main_property_type
            ON artifacts(main_property_type);

        CREATE INDEX IF NOT EXISTS idx_artifacts_last_seen_at
            ON artifacts(last_seen_at);

        CREATE INDEX IF NOT EXISTS idx_artifact_substats_property_type
            ON artifact_substats(property_type);

        CREATE INDEX IF NOT EXISTS idx_artifact_equipment_character_id
            ON artifact_equipment(character_id);
            
        CREATE TABLE IF NOT EXISTS artifact_builds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            character_id INTEGER,
            character_name TEXT,

            notes TEXT,

            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS artifact_build_slots (
            build_id INTEGER NOT NULL,
            pos INTEGER NOT NULL,
            artifact_id INTEGER NOT NULL,

            PRIMARY KEY (build_id, pos),
            FOREIGN KEY (build_id) REFERENCES artifact_builds(id) ON DELETE CASCADE,
            FOREIGN KEY (artifact_id) REFERENCES artifacts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS artifact_build_targets (
            build_id INTEGER NOT NULL,
            target_type TEXT NOT NULL,
            character_id INTEGER,
            character_name TEXT,

            PRIMARY KEY (build_id, target_type, character_id),
            FOREIGN KEY (build_id) REFERENCES artifact_builds(id) ON DELETE CASCADE,
            CHECK (target_type IN ('universal', 'character')),
            CHECK (
                (target_type = 'universal' AND character_id IS NULL)
                OR (target_type = 'character' AND character_id IS NOT NULL)
            )
        );

        CREATE INDEX IF NOT EXISTS idx_artifact_builds_character_id
            ON artifact_builds(character_id);

        CREATE INDEX IF NOT EXISTS idx_artifact_build_slots_artifact_id
            ON artifact_build_slots(artifact_id);

        CREATE INDEX IF NOT EXISTS idx_artifact_build_targets_character_id
            ON artifact_build_targets(character_id);

        CREATE UNIQUE INDEX IF NOT EXISTS idx_artifact_build_targets_universal
            ON artifact_build_targets(build_id, target_type)
            WHERE target_type = 'universal';
        """
    )
    artifact_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(artifacts)").fetchall()
    }

    if "set_uid" not in artifact_columns:
        conn.execute("ALTER TABLE artifacts ADD COLUMN set_uid TEXT")

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_artifacts_set_uid
            ON artifacts (set_uid)
        """
    )

    conn.execute(
        """
        INSERT OR IGNORE INTO artifact_build_targets (
            build_id,
            target_type,
            character_id,
            character_name
        )
        SELECT
            id,
            'character',
            character_id,
            character_name
        FROM artifact_builds
        WHERE character_id IS NOT NULL
        """
    )

    conn.commit()


def upsert_artifact(
    conn: sqlite3.Connection,
    *,
    fingerprint: str,
    relic_id: int | None,
    name: str,
    set_id: int | None,
    set_name: str | None,
    set_uid: str | None,
    pos: int,
    pos_name: str | None,
    rarity: int | None,
    level: int | None,
    main_property_type: int | None,
    main_property_name: str | None,
    main_property_value: str | None,
) -> tuple[int, bool]:
    now = utc_now()

    existing = conn.execute(
        "SELECT id FROM artifacts WHERE fingerprint = ?",
        (fingerprint,),
    ).fetchone()

    if existing:
        artifact_id = int(existing["id"])
        conn.execute(
            """
            UPDATE artifacts SET
                relic_id = ?,
                name = ?,
                set_id = ?,
                set_uid = ?,
                set_name = ?,
                pos = ?,
                pos_name = ?,
                rarity = ?,
                level = ?,
                main_property_type = ?,
                main_property_name = ?,
                main_property_value = ?,
                last_seen_at = ?
            WHERE id = ?
            """,
            (
                relic_id,
                name,
                set_id,
                set_uid,
                set_name,
                pos,
                pos_name,
                rarity,
                level,
                main_property_type,
                main_property_name,
                main_property_value,
                now,
                artifact_id,
            ),
        )
        return artifact_id, False

    cursor = conn.execute(
        """
        INSERT INTO artifacts (
            fingerprint,
            relic_id,
            name,
            set_id,
            set_uid,
            set_name,
            pos,
            pos_name,
            rarity,
            level,
            main_property_type,
            main_property_name,
            main_property_value,
            first_seen_at,
            last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fingerprint,
            relic_id,
            name,
            set_id,
            set_uid,
            set_name,
            pos,
            pos_name,
            rarity,
            level,
            main_property_type,
            main_property_name,
            main_property_value,
            now,
            now,
        ),
    )

    return int(cursor.lastrowid), True


def replace_substats(
    conn: sqlite3.Connection,
    artifact_id: int,
    substats: list[dict[str, Any]],
) -> None:
    conn.execute(
        "DELETE FROM artifact_substats WHERE artifact_id = ?",
        (artifact_id,),
    )

    for slot_index, substat in enumerate(substats):
        conn.execute(
            """
            INSERT INTO artifact_substats (
                artifact_id,
                slot_index,
                property_type,
                property_name,
                value,
                times
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                slot_index,
                substat.get("property_type"),
                substat.get("property_name"),
                substat.get("value"),
                substat.get("times"),
            ),
        )


def replace_current_equipment(
    conn: sqlite3.Connection,
    equipment_rows: list[dict[str, Any]],
) -> None:
    imported_at = utc_now()

    conn.execute("DELETE FROM artifact_equipment")

    for row in equipment_rows:
        conn.execute(
            """
            INSERT INTO artifact_equipment (
                artifact_id,
                character_id,
                character_name,
                pos,
                imported_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                row["artifact_id"],
                row["character_id"],
                row["character_name"],
                row["pos"],
                imported_at,
            ),
        )


def get_or_create_tag(
    conn: sqlite3.Connection,
    name: str,
    *,
    color: str | None = None,
    sort_order: int = 0,
) -> int:
    now = utc_now()

    conn.execute(
        """
        INSERT INTO artifact_tags (
            name,
            color,
            sort_order,
            created_at
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO NOTHING
        """,
        (name, color, sort_order, now),
    )

    row = conn.execute(
        "SELECT id FROM artifact_tags WHERE name = ?",
        (name,),
    ).fetchone()

    return int(row["id"])


def tag_artifact(conn: sqlite3.Connection, artifact_id: int, tag_id: int) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO artifact_tag_links (
            artifact_id,
            tag_id
        )
        VALUES (?, ?)
        """,
        (artifact_id, tag_id),
    )


def untag_artifact(conn: sqlite3.Connection, artifact_id: int, tag_id: int) -> None:
    conn.execute(
        """
        DELETE FROM artifact_tag_links
        WHERE artifact_id = ? AND tag_id = ?
        """,
        (artifact_id, tag_id),
    )

def create_artifact_build(
    conn: sqlite3.Connection,
    *,
    name: str,
    character_id: int | None = None,
    character_name: str | None = None,
    notes: str | None = None,
) -> int:
    now = utc_now()

    cursor = conn.execute(
        """
        INSERT INTO artifact_builds (
            name,
            character_id,
            character_name,
            notes,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            character_id,
            character_name,
            notes,
            now,
            now,
        ),
    )

    build_id = int(cursor.lastrowid)
    if character_id is not None:
        replace_artifact_build_targets(
            conn,
            build_id,
            [
                {
                    "target_type": "character",
                    "character_id": character_id,
                    "character_name": character_name or "",
                }
            ],
        )

    return build_id


def update_artifact_build(
    conn: sqlite3.Connection,
    build_id: int,
    *,
    name: str | None = None,
    character_id: int | None = None,
    character_name: str | None = None,
    notes: str | None = None,
) -> None:
    now = utc_now()

    conn.execute(
        """
        UPDATE artifact_builds SET
            name = COALESCE(?, name),
            character_id = ?,
            character_name = ?,
            notes = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            name,
            character_id,
            character_name,
            notes,
            now,
            build_id,
        ),
    )


def create_build_preset(
    conn: sqlite3.Connection,
    *,
    name: str,
    notes: str | None = None,
    slots: dict[int, int] | None = None,
    targets: list[dict[str, Any]] | None = None,
) -> int:
    build_id = create_artifact_build(conn, name=name, notes=notes)
    if slots:
        replace_artifact_build_slots(conn, build_id, slots)
    if targets is not None:
        replace_artifact_build_targets(conn, build_id, targets)
    return build_id


def update_build_preset(
    conn: sqlite3.Connection,
    build_id: int,
    *,
    name: str | None = None,
    notes: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE artifact_builds
        SET
            name = COALESCE(?, name),
            notes = COALESCE(?, notes),
            updated_at = ?
        WHERE id = ?
        """,
        (name, notes, utc_now(), int(build_id)),
    )


def delete_build_preset(conn: sqlite3.Connection, build_id: int) -> None:
    conn.execute("DELETE FROM artifact_builds WHERE id = ?", (int(build_id),))


def replace_artifact_build_slots(
    conn: sqlite3.Connection,
    build_id: int,
    slots: dict[int, int],
) -> None:
    """
    slots:
        {
            1: flower_artifact_id,
            2: feather_artifact_id,
            3: sands_artifact_id,
            4: goblet_artifact_id,
            5: circlet_artifact_id,
        }
    """
    build_id = int(build_id)
    slots = {
        int(pos): int(artifact_id)
        for pos, artifact_id in slots.items()
    }

    for pos in slots:
        if pos not in {1, 2, 3, 4, 5}:
            raise ValueError(f"Invalid artifact slot position: {pos}")

    if slots:
        placeholders = ",".join("?" for _ in slots)
        rows = conn.execute(
            f"""
            SELECT id, pos
            FROM artifacts
            WHERE id IN ({placeholders})
            """,
            list(slots.values()),
        ).fetchall()
        artifact_pos_by_id = {
            int(row["id"]): int(row["pos"])
            for row in rows
        }

        for pos, artifact_id in slots.items():
            artifact_pos = artifact_pos_by_id.get(artifact_id)
            if artifact_pos is None:
                raise ValueError(f"Unknown artifact id: {artifact_id}")
            if artifact_pos != pos:
                raise ValueError(
                    f"Artifact {artifact_id} belongs to position {artifact_pos}, "
                    f"not build slot {pos}"
                )

    conn.execute(
        "DELETE FROM artifact_build_slots WHERE build_id = ?",
        (build_id,),
    )

    for pos, artifact_id in sorted(slots.items()):
        conn.execute(
            """
            INSERT INTO artifact_build_slots (
                build_id,
                pos,
                artifact_id
            )
            VALUES (?, ?, ?)
            """,
            (
                build_id,
                pos,
                artifact_id,
            ),
        )

    conn.execute(
        """
        UPDATE artifact_builds
        SET updated_at = ?
        WHERE id = ?
        """,
        (utc_now(), build_id),
    )


def _target_display_name(target_type: str, character_name: str | None) -> str:
    if target_type == "universal":
        return character_name or "Universal"
    return character_name or ""


def _normalize_build_target(target: dict[str, Any]) -> dict[str, Any]:
    target_type = str(target.get("target_type") or "").strip().lower()
    if target_type not in {"universal", "character"}:
        raise ValueError(f"Invalid build target type: {target_type!r}")

    if target_type == "universal":
        return {
            "target_type": "universal",
            "character_id": None,
            "character_name": _target_display_name(
                "universal",
                target.get("character_name"),
            ),
        }

    character_id = target.get("character_id")
    if character_id is None or character_id == "":
        raise ValueError("Character build target requires character_id")

    return {
        "target_type": "character",
        "character_id": int(character_id),
        "character_name": str(target.get("character_name") or ""),
    }


def replace_artifact_build_targets(
    conn: sqlite3.Connection,
    build_id: int,
    targets: list[dict[str, Any]],
) -> None:
    build_id = int(build_id)
    normalized_targets = [
        _normalize_build_target(target)
        for target in targets
    ]

    conn.execute(
        "DELETE FROM artifact_build_targets WHERE build_id = ?",
        (build_id,),
    )

    for target in normalized_targets:
        conn.execute(
            """
            INSERT INTO artifact_build_targets (
                build_id,
                target_type,
                character_id,
                character_name
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                build_id,
                target["target_type"],
                target["character_id"],
                target["character_name"],
            ),
        )

    conn.execute(
        """
        UPDATE artifact_builds
        SET updated_at = ?
        WHERE id = ?
        """,
        (utc_now(), build_id),
    )


def get_artifact_build_targets(
    conn: sqlite3.Connection,
    build_id: int,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            target_type,
            character_id,
            character_name
        FROM artifact_build_targets
        WHERE build_id = ?
        ORDER BY
            CASE target_type
                WHEN 'universal' THEN 0
                ELSE 1
            END,
            character_name COLLATE NOCASE,
            character_id
        """,
        (int(build_id),),
    ).fetchall()

    return [
        {
            "target_type": row["target_type"],
            "character_id": (
                int(row["character_id"])
                if row["character_id"] is not None
                else None
            ),
            "character_name": _target_display_name(
                row["target_type"],
                row["character_name"],
            ),
        }
        for row in rows
    ]


def get_artifact_build_slots(
    conn: sqlite3.Connection,
    build_id: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT
            build_slots.pos,
            artifacts.id AS artifact_id,
            artifacts.name,
            artifacts.set_uid,
            artifacts.set_name,
            artifacts.pos_name,
            artifacts.rarity,
            artifacts.level,
            artifacts.main_property_type,
            artifacts.main_property_name,
            artifacts.main_property_value
        FROM artifact_build_slots AS build_slots
        JOIN artifacts
            ON artifacts.id = build_slots.artifact_id
        WHERE build_slots.build_id = ?
        ORDER BY build_slots.pos
        """,
        (build_id,),
    ).fetchall()


def _artifact_build_slot_dict(slot: sqlite3.Row) -> dict[str, Any]:
    return {
        "pos": int(slot["pos"]),
        "artifact_id": int(slot["artifact_id"]),
        "name": slot["name"],
        "set_uid": slot["set_uid"] or "",
        "set_name": slot["set_name"] or "",
        "pos_name": slot["pos_name"] or "",
        "rarity": int(slot["rarity"] or 0),
        "level": int(slot["level"] or 0),
        "main_property_type": slot["main_property_type"],
        "main_property_name": slot["main_property_name"],
        "main_property_value": slot["main_property_value"],
    }


def list_build_presets(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            builds.id,
            builds.name,
            builds.character_id,
            builds.character_name,
            builds.notes,
            builds.created_at,
            builds.updated_at,
            COUNT(DISTINCT slots.pos) AS slot_count,
            COUNT(DISTINCT targets.target_type || ':' || COALESCE(targets.character_id, '')) AS target_count
        FROM artifact_builds AS builds
        LEFT JOIN artifact_build_slots AS slots
            ON slots.build_id = builds.id
        LEFT JOIN artifact_build_targets AS targets
            ON targets.build_id = builds.id
        GROUP BY builds.id
        ORDER BY builds.created_at DESC, builds.id DESC, builds.name COLLATE NOCASE
        """
    ).fetchall()

    build_ids = [int(row["id"]) for row in rows]
    slots_by_build_id: dict[int, list[dict[str, Any]]] = {
        build_id: []
        for build_id in build_ids
    }
    if build_ids:
        placeholders = ",".join("?" for _ in build_ids)
        slot_rows = conn.execute(
            f"""
            SELECT
                build_slots.build_id,
                build_slots.pos,
                artifacts.id AS artifact_id,
                artifacts.name,
                artifacts.set_uid,
                artifacts.set_name,
                artifacts.pos_name,
                artifacts.rarity,
                artifacts.level,
                artifacts.main_property_type,
                artifacts.main_property_name,
                artifacts.main_property_value
            FROM artifact_build_slots AS build_slots
            JOIN artifacts
                ON artifacts.id = build_slots.artifact_id
            WHERE build_slots.build_id IN ({placeholders})
            ORDER BY build_slots.build_id, build_slots.pos
            """,
            build_ids,
        ).fetchall()
        for slot in slot_rows:
            slots_by_build_id[int(slot["build_id"])].append(
                _artifact_build_slot_dict(slot)
            )

    targets_by_build_id = {
        int(row["id"]): get_artifact_build_targets(conn, int(row["id"]))
        for row in rows
    }

    return [
        {
            "id": int(row["id"]),
            "name": row["name"],
            "notes": row["notes"],
            "legacy_character_id": (
                int(row["character_id"])
                if row["character_id"] is not None
                else None
            ),
            "legacy_character_name": row["character_name"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "slot_count": int(row["slot_count"] or 0),
            "target_count": int(row["target_count"] or 0),
            "slots": slots_by_build_id.get(int(row["id"]), []),
            "targets": targets_by_build_id.get(int(row["id"]), []),
        }
        for row in rows
    ]


def get_build_preset(
    conn: sqlite3.Connection,
    build_id: int,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT
            id,
            name,
            character_id,
            character_name,
            notes,
            created_at,
            updated_at
        FROM artifact_builds
        WHERE id = ?
        """,
        (int(build_id),),
    ).fetchone()
    if row is None:
        return None

    slots = get_artifact_build_slots(conn, build_id)
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "notes": row["notes"],
        "legacy_character_id": (
            int(row["character_id"])
            if row["character_id"] is not None
            else None
        ),
        "legacy_character_name": row["character_name"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "slots": [
            _artifact_build_slot_dict(slot)
            for slot in slots
        ],
        "targets": get_artifact_build_targets(conn, build_id),
    }


def get_build_artifact_ids(
    conn: sqlite3.Connection,
    build_id: int,
) -> list[int]:
    rows = conn.execute(
        """
        SELECT artifact_id
        FROM artifact_build_slots
        WHERE build_id = ?
        ORDER BY pos
        """,
        (build_id,),
    ).fetchall()

    return [int(row["artifact_id"]) for row in rows]


def _parse_raw_stat_value(value: Any) -> float:
    text = str(value or "").strip().replace("%", "").replace(",", ".")
    if not text:
        return 0.0
    return float(text)


def _slots_from_artifact_ids(
    conn: sqlite3.Connection,
    artifact_ids: list[int],
) -> dict[int, int]:
    artifact_ids = [int(artifact_id) for artifact_id in artifact_ids]
    if not artifact_ids:
        return {}

    placeholders = ",".join("?" for _ in artifact_ids)
    rows = conn.execute(
        f"""
        SELECT id, pos
        FROM artifacts
        WHERE id IN ({placeholders})
        """,
        artifact_ids,
    ).fetchall()
    pos_by_artifact_id = {
        int(row["id"]): int(row["pos"])
        for row in rows
    }

    missing = [
        artifact_id
        for artifact_id in artifact_ids
        if artifact_id not in pos_by_artifact_id
    ]
    if missing:
        raise ValueError(f"Unknown artifact ids: {missing}")

    slots: dict[int, int] = {}
    for artifact_id in artifact_ids:
        pos = pos_by_artifact_id[artifact_id]
        if pos in slots:
            raise ValueError(f"Multiple artifacts selected for position {pos}")
        slots[pos] = artifact_id
    return slots


def calculate_raw_build_summary(
    conn: sqlite3.Connection,
    *,
    build_id: int | None = None,
    slots: dict[int, int] | None = None,
    artifact_ids: list[int] | None = None,
) -> dict[str, Any]:
    provided = sum(
        value is not None
        for value in (build_id, slots, artifact_ids)
    )
    if provided != 1:
        raise ValueError("Provide exactly one of build_id, slots, or artifact_ids")

    if build_id is not None:
        rows = conn.execute(
            """
            SELECT pos, artifact_id
            FROM artifact_build_slots
            WHERE build_id = ?
            """,
            (int(build_id),),
        ).fetchall()
        selected_slots = {
            int(row["pos"]): int(row["artifact_id"])
            for row in rows
        }
    elif slots is not None:
        selected_slots = {
            int(pos): int(artifact_id)
            for pos, artifact_id in slots.items()
        }
    else:
        selected_slots = _slots_from_artifact_ids(conn, artifact_ids or [])

    for pos in selected_slots:
        if pos not in {1, 2, 3, 4, 5}:
            raise ValueError(f"Invalid artifact slot position: {pos}")

    artifact_ids_by_pos = {
        pos: artifact_id
        for pos, artifact_id in sorted(selected_slots.items())
    }
    selected_artifact_ids = list(artifact_ids_by_pos.values())
    missing_positions = [
        pos
        for pos in range(1, 6)
        if pos not in artifact_ids_by_pos
    ]

    if not selected_artifact_ids:
        return {
            "artifact_ids_by_pos": artifact_ids_by_pos,
            "missing_positions": missing_positions,
            "set_counts": [],
            "total_stats": [],
            "crit_value": 0.0,
            "proc_count": 0,
        }

    placeholders = ",".join("?" for _ in selected_artifact_ids)
    artifact_rows = conn.execute(
        f"""
        SELECT
            id,
            pos,
            name,
            set_uid,
            set_name,
            main_property_type,
            main_property_name,
            main_property_value
        FROM artifacts
        WHERE id IN ({placeholders})
        """,
        selected_artifact_ids,
    ).fetchall()
    artifacts_by_id = {
        int(row["id"]): row
        for row in artifact_rows
    }

    missing_artifact_ids = [
        artifact_id
        for artifact_id in selected_artifact_ids
        if artifact_id not in artifacts_by_id
    ]
    if missing_artifact_ids:
        raise ValueError(f"Unknown artifact ids: {missing_artifact_ids}")

    set_counts_by_uid: dict[str, dict[str, Any]] = {}
    stats_by_type: dict[int, dict[str, Any]] = {}
    proc_count = 0

    def add_stat(
        property_type: int | None,
        property_name: str | None,
        value: Any,
    ) -> None:
        if property_type is None:
            return

        property_type = int(property_type)
        stat = stats_by_type.setdefault(
            property_type,
            {
                "property_type": property_type,
                "property_name": property_name or "",
                "raw_value": 0.0,
            },
        )
        if not stat["property_name"] and property_name:
            stat["property_name"] = property_name
        stat["raw_value"] += _parse_raw_stat_value(value)

    for artifact_id in selected_artifact_ids:
        artifact = artifacts_by_id[artifact_id]
        set_uid = artifact["set_uid"] or ""
        set_name = artifact["set_name"] or ""
        set_key = set_uid or set_name
        set_count = set_counts_by_uid.setdefault(
            set_key,
            {
                "set_uid": set_uid,
                "set_name": set_name,
                "count": 0,
            },
        )
        set_count["count"] += 1

        add_stat(
            artifact["main_property_type"],
            artifact["main_property_name"],
            artifact["main_property_value"],
        )

    substat_rows = conn.execute(
        f"""
        SELECT
            artifact_id,
            property_type,
            property_name,
            value,
            times
        FROM artifact_substats
        WHERE artifact_id IN ({placeholders})
        """,
        selected_artifact_ids,
    ).fetchall()

    for substat in substat_rows:
        add_stat(
            substat["property_type"],
            substat["property_name"],
            substat["value"],
        )
        proc_count += int(substat["times"] or 0)

    crit_rate = stats_by_type.get(20, {}).get("raw_value", 0.0)
    crit_damage = stats_by_type.get(22, {}).get("raw_value", 0.0)

    return {
        "artifact_ids_by_pos": artifact_ids_by_pos,
        "missing_positions": missing_positions,
        "set_counts": sorted(
            set_counts_by_uid.values(),
            key=lambda item: (
                -int(item["count"]),
                str(item["set_name"]).casefold(),
                str(item["set_uid"]).casefold(),
            ),
        ),
        "total_stats": [
            {
                "property_type": stat["property_type"],
                "property_name": stat["property_name"],
                "raw_value": round(float(stat["raw_value"]), 6),
            }
            for stat in sorted(
                stats_by_type.values(),
                key=lambda item: int(item["property_type"]),
            )
        ],
        "crit_value": round(float(crit_rate) * 2 + float(crit_damage), 1),
        "proc_count": proc_count,
    }


def find_duplicate_artifacts_in_builds(
    conn: sqlite3.Connection,
    build_ids: list[int],
) -> list[dict[str, Any]]:
    """
    Проверяет конфликт: один artifact_id используется в нескольких сборках.

    Потом это пригодится для правила:
    в одном забеге 8 персонажей не могут носить один и тот же артефакт.
    """
    if not build_ids:
        return []

    placeholders = ",".join("?" for _ in build_ids)

    rows = conn.execute(
        f"""
        SELECT
            slots.artifact_id,
            artifacts.name AS artifact_name,
            artifacts.pos_name,
            GROUP_CONCAT(builds.id) AS build_ids,
            GROUP_CONCAT(builds.name) AS build_names,
            COUNT(*) AS usage_count
        FROM artifact_build_slots AS slots
        JOIN artifact_builds AS builds
            ON builds.id = slots.build_id
        JOIN artifacts
            ON artifacts.id = slots.artifact_id
        WHERE slots.build_id IN ({placeholders})
        GROUP BY slots.artifact_id
        HAVING COUNT(*) > 1
        ORDER BY usage_count DESC, artifact_name
        """,
        build_ids,
    ).fetchall()

    return [
        {
            "artifact_id": int(row["artifact_id"]),
            "artifact_name": row["artifact_name"],
            "pos_name": row["pos_name"],
            "build_ids": [
                int(value)
                for value in str(row["build_ids"]).split(",")
                if value
            ],
            "build_names": [
                value
                for value in str(row["build_names"]).split(",")
                if value
            ],
            "usage_count": int(row["usage_count"]),
        }
        for row in rows
    ]

def count_rows(conn: sqlite3.Connection) -> dict[str, int]:
    tables = [
        "artifacts",
        "artifact_substats",
        "artifact_equipment",
        "artifact_tags",
        "artifact_tag_links",
        "artifact_builds",
        "artifact_build_slots",
        "artifact_build_targets",
        "artifact_sets",
        "artifact_set_piece_icons",
        "artifact_set_names",
    ]

    result = {}

    for table in tables:
        row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        result[table] = int(row["count"])

    return result


def init_artifact_db(db_path: str | Path = ARTIFACT_DB_PATH) -> Path:
    db_path = Path(db_path)
    with connect_db(db_path) as conn:
        init_db(conn)
    return db_path


if __name__ == "__main__":
    path = init_artifact_db()
    print(f"Artifact DB initialized: {path}")

    with connect_db(path) as conn:
        print(count_rows(conn))
