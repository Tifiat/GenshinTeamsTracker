from __future__ import annotations

from pathlib import Path
from typing import Any

from hoyolab_export.artifact_db import (
    ARTIFACT_DB_PATH,
    calculate_raw_build_summary as db_calculate_raw_build_summary,
    connect_db,
    create_build_preset as db_create_build_preset,
    delete_build_preset as db_delete_build_preset,
    get_build_preset as db_get_build_preset,
    init_db,
    list_build_presets as db_list_build_presets,
    replace_artifact_build_slots,
    replace_artifact_build_targets,
    update_build_preset as db_update_build_preset,
)
from hoyolab_export.paths import PROJECT_ROOT

from .models import (
    ARTIFACT_POSITIONS,
    ArtifactItem,
    ArtifactSubstat,
    ArtifactTagRef,
    int_or_none,
)


def artifact_db_exists(db_path: str | Path = ARTIFACT_DB_PATH) -> bool:
    return Path(db_path).exists()


def _resolve_icon_path(local_path: str | None) -> Path | None:
    if not local_path:
        return None

    path = Path(local_path)
    path = path if path.is_absolute() else PROJECT_ROOT / path
    return path if path.exists() and path.is_file() else None


def list_all_artifacts(
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> list[ArtifactItem]:
    if not artifact_db_exists(db_path):
        return []

    with connect_db(db_path) as conn:
        init_db(conn)
        return _fetch_artifacts(conn)


def _fetch_artifacts(conn) -> list[ArtifactItem]:
    rows = conn.execute(
        """
        SELECT
            artifacts.id,
            artifacts.name,
            artifacts.set_id,
            artifacts.set_uid,
            artifacts.set_name,
            artifacts.pos,
            artifacts.pos_name,
            artifacts.rarity,
            artifacts.level,
            artifacts.main_property_type,
            artifacts.main_property_name,
            artifacts.main_property_value,
                        set_icons.icon_url AS set_icon_url,
            set_icons.local_path AS set_icon_local_path,
            set_flower_icons.local_path AS set_flower_icon_local_path,
            equipment.character_name
        FROM artifacts
        LEFT JOIN artifact_set_piece_icons AS set_icons
            ON set_icons.set_uid = artifacts.set_uid
            AND set_icons.pos = artifacts.pos
        LEFT JOIN artifact_set_piece_icons AS set_flower_icons
            ON set_flower_icons.set_uid = artifacts.set_uid
            AND set_flower_icons.pos = 1
        LEFT JOIN artifact_equipment AS equipment
            ON equipment.artifact_id = artifacts.id
        ORDER BY
            artifacts.pos,
            COALESCE(artifacts.rarity, 0) DESC,
            COALESCE(artifacts.level, 0) DESC,
            artifacts.set_name COLLATE NOCASE,
            artifacts.name COLLATE NOCASE
        """
    ).fetchall()

    artifact_ids = [int(row["id"]) for row in rows]
    substats_by_artifact = _load_substats(conn, artifact_ids)
    tags_by_artifact = _load_tags(conn, artifact_ids)

    result: list[ArtifactItem] = []

    for row in rows:
        artifact_id = int(row["id"])
        pos = int(row["pos"])
        set_uid = row["set_uid"] or ""
        icon_key = f"{set_uid}_{pos}.png" if set_uid else ""

        result.append(
            ArtifactItem(
                id=artifact_id,
                name=row["name"],
                set_id=int_or_none(row["set_id"]),
                set_uid=set_uid,
                set_name=row["set_name"],
                pos=pos,
                pos_name=row["pos_name"] or ARTIFACT_POSITIONS[pos],
                rarity=int_or_none(row["rarity"]) or 0,
                level=int_or_none(row["level"]) or 0,
                main_property_type=int(row["main_property_type"]),
                main_property_name=row["main_property_name"],
                main_property_value=row["main_property_value"],
                icon_key=icon_key,
                icon_url=row["set_icon_url"] or "",
                icon_path=_resolve_icon_path(row["set_icon_local_path"]),
                set_icon_path=_resolve_icon_path(row["set_flower_icon_local_path"]),
                character_name=row["character_name"] or "",
                tags=tags_by_artifact.get(artifact_id, []),
                substats=substats_by_artifact.get(artifact_id, []),
            )
        )

    return result


def _load_substats(conn, artifact_ids: list[int]) -> dict[int, list[ArtifactSubstat]]:
    if not artifact_ids:
        return {}

    placeholders = ",".join("?" for _ in artifact_ids)

    rows = conn.execute(
        f"""
        SELECT
            artifact_id,
            slot_index,
            property_type,
            property_name,
            value,
            times
        FROM artifact_substats
        WHERE artifact_id IN ({placeholders})
        ORDER BY artifact_id, slot_index
        """,
        artifact_ids,
    ).fetchall()

    result: dict[int, list[ArtifactSubstat]] = {
        artifact_id: []
        for artifact_id in artifact_ids
    }

    for row in rows:
        artifact_id = int(row["artifact_id"])
        result[artifact_id].append(
            ArtifactSubstat(
                slot_index=int(row["slot_index"]),
                property_type=int(row["property_type"]),
                property_name=row["property_name"],
                value=row["value"],
                times=row["times"],
            )
        )

    return result


def _load_tags(conn, artifact_ids: list[int]) -> dict[int, list[ArtifactTagRef]]:
    if not artifact_ids:
        return {}

    placeholders = ",".join("?" for _ in artifact_ids)

    rows = conn.execute(
        f"""
        SELECT
            links.artifact_id,
            tags.id AS tag_id,
            tags.name AS tag_name
        FROM artifact_tag_links AS links
        JOIN artifact_tags AS tags
            ON tags.id = links.tag_id
        WHERE links.artifact_id IN ({placeholders})
        ORDER BY tags.sort_order, tags.name COLLATE NOCASE
        """,
        artifact_ids,
    ).fetchall()

    result: dict[int, list[ArtifactTagRef]] = {
        artifact_id: []
        for artifact_id in artifact_ids
    }

    for row in rows:
        result[int(row["artifact_id"])].append(
            ArtifactTagRef(
                id=int(row["tag_id"]),
                name=row["tag_name"],
            )
        )

    return result

def list_custom_sets(
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> list[dict[str, Any]]:
    if not artifact_db_exists(db_path):
        return []

    with connect_db(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            """
            SELECT
                tags.id,
                tags.name,
                tags.color,
                tags.sort_order,
                COUNT(links.artifact_id) AS count
            FROM artifact_tags AS tags
            LEFT JOIN artifact_tag_links AS links
                ON links.tag_id = tags.id
            GROUP BY tags.id
            ORDER BY tags.sort_order, tags.name COLLATE NOCASE
            """
        ).fetchall()

    return [
        {
            "tag_id": int(row["id"]),
            "name": row["name"],
            "count": int(row["count"] or 0),
        }
        for row in rows
    ]


def create_custom_set(
    name: str,
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> int:
    name = str(name or "").strip()
    if not name:
        raise ValueError("Custom artifact set name is empty")

    with connect_db(db_path) as conn:
        init_db(conn)
        row = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order FROM artifact_tags"
        ).fetchone()
        sort_order = int(row["next_order"] or 1)

        now = __import__("hoyolab_export.artifact_db", fromlist=["utc_now"]).utc_now()
        conn.execute(
            """
            INSERT INTO artifact_tags (
                name,
                color,
                sort_order,
                created_at
            )
            VALUES (?, NULL, ?, ?)
            ON CONFLICT(name) DO NOTHING
            """,
            (name, sort_order, now),
        )

        tag_row = conn.execute(
            "SELECT id FROM artifact_tags WHERE name = ?",
            (name,),
        ).fetchone()

        conn.commit()

    return int(tag_row["id"])


def delete_custom_set(
    tag_id: int,
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> None:
    with connect_db(db_path) as conn:
        init_db(conn)
        conn.execute("DELETE FROM artifact_tags WHERE id = ?", (int(tag_id),))
        conn.commit()


def get_custom_set_artifact_ids(
    tag_id: int,
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> set[int]:
    if not artifact_db_exists(db_path):
        return set()

    with connect_db(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            """
            SELECT artifact_id
            FROM artifact_tag_links
            WHERE tag_id = ?
            """,
            (int(tag_id),),
        ).fetchall()

    return {int(row["artifact_id"]) for row in rows}


def replace_custom_set_artifacts(
    tag_id: int,
    artifact_ids: set[int],
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> None:
    tag_id = int(tag_id)
    artifact_ids = {int(artifact_id) for artifact_id in artifact_ids}

    with connect_db(db_path) as conn:
        init_db(conn)

        conn.execute(
            "DELETE FROM artifact_tag_links WHERE tag_id = ?",
            (tag_id,),
        )

        for artifact_id in sorted(artifact_ids):
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

        conn.commit()


def list_build_presets(
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> list[dict[str, Any]]:
    if not artifact_db_exists(db_path):
        return []

    with connect_db(db_path) as conn:
        init_db(conn)
        return db_list_build_presets(conn)


def get_build_preset(
    build_id: int,
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> dict[str, Any] | None:
    if not artifact_db_exists(db_path):
        return None

    with connect_db(db_path) as conn:
        init_db(conn)
        return db_get_build_preset(conn, build_id)


def save_build_preset(
    *,
    build_id: int | None,
    name: str,
    slots: dict[int, int],
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> int:
    with connect_db(db_path) as conn:
        init_db(conn)
        if build_id is None:
            build_id = db_create_build_preset(
                conn,
                name=name,
                slots=slots,
                targets=[{"target_type": "universal"}],
            )
        else:
            db_update_build_preset(conn, build_id, name=name)
            replace_artifact_build_slots(conn, build_id, slots)
            replace_artifact_build_targets(
                conn,
                build_id,
                [{"target_type": "universal"}],
            )
        conn.commit()
        return int(build_id)


def delete_build_preset(
    build_id: int,
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> None:
    with connect_db(db_path) as conn:
        init_db(conn)
        db_delete_build_preset(conn, build_id)
        conn.commit()


def calculate_build_summary(
    *,
    build_id: int | None = None,
    slots: dict[int, int] | None = None,
    artifact_ids: list[int] | None = None,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> dict[str, Any] | None:
    if not artifact_db_exists(db_path):
        return None

    with connect_db(db_path) as conn:
        init_db(conn)
        return db_calculate_raw_build_summary(
            conn,
            build_id=build_id,
            slots=slots,
            artifact_ids=artifact_ids,
        )

