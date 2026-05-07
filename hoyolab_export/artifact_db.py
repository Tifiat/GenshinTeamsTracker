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

        CREATE TABLE IF NOT EXISTS artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT NOT NULL UNIQUE,

            relic_id INTEGER,
            name TEXT NOT NULL,

            set_id INTEGER,
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
        """
    )
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fingerprint,
            relic_id,
            name,
            set_id,
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


def count_rows(conn: sqlite3.Connection) -> dict[str, int]:
    tables = [
        "artifact_icons",
        "artifacts",
        "artifact_substats",
        "artifact_equipment",
        "artifact_tags",
        "artifact_tag_links",
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