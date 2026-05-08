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
        CREATE TABLE IF NOT EXISTS artifact_icons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            icon_key TEXT NOT NULL UNIQUE,
            icon_url TEXT NOT NULL,
            local_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

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

            icon_id INTEGER,

            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,

            FOREIGN KEY (icon_id) REFERENCES artifact_icons(id)
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

        CREATE INDEX IF NOT EXISTS idx_artifact_builds_character_id
            ON artifact_builds(character_id);

        CREATE INDEX IF NOT EXISTS idx_artifact_build_slots_artifact_id
            ON artifact_build_slots(artifact_id);    
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
    conn.commit()

    conn.commit()


def upsert_icon(
    conn: sqlite3.Connection,
    *,
    icon_key: str,
    icon_url: str,
    local_path: str | None = None,
) -> int:
    now = utc_now()

    conn.execute(
        """
        INSERT INTO artifact_icons (
            icon_key,
            icon_url,
            local_path,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(icon_key) DO UPDATE SET
            icon_url = excluded.icon_url,
            local_path = COALESCE(excluded.local_path, artifact_icons.local_path),
            updated_at = excluded.updated_at
        """,
        (icon_key, icon_url, local_path, now, now),
    )

    row = conn.execute(
        "SELECT id FROM artifact_icons WHERE icon_key = ?",
        (icon_key,),
    ).fetchone()

    return int(row["id"])


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
    icon_id: int | None,
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
                icon_id = ?,
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
                icon_id,
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
            icon_id,
            first_seen_at,
            last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            icon_id,
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

    return int(cursor.lastrowid)


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
    conn.execute(
        "DELETE FROM artifact_build_slots WHERE build_id = ?",
        (build_id,),
    )

    for pos, artifact_id in sorted(slots.items()):
        if pos not in {1, 2, 3, 4, 5}:
            raise ValueError(f"Invalid artifact slot position: {pos}")

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
            artifacts.set_name,
            artifacts.pos_name,
            artifacts.rarity,
            artifacts.level,
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
        "artifact_icons",
        "artifacts",
        "artifact_substats",
        "artifact_equipment",
        "artifact_tags",
        "artifact_tag_links",
        "artifact_builds",
        "artifact_build_slots",
        "artifact_sets",
        "artifact_set_piece_icons",
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