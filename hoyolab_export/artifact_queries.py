from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_db import (
    ARTIFACT_DB_PATH,
    connect_db,
    get_or_create_tag,
    tag_artifact,
    untag_artifact,
)
from .paths import PROJECT_ROOT


ARTIFACT_ICON_DIR = PROJECT_ROOT / "assets" / "hoyolab" / "artifacts"
ARTIFACT_POSITIONS = {
    1: "Цветок",
    2: "Перо",
    3: "Часы",
    4: "Кубок",
    5: "Корона",
}


def db_exists(db_path: str | Path = ARTIFACT_DB_PATH) -> bool:
    return Path(db_path).exists()


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _split_group(value: str | None) -> list[str]:
    if not value:
        return []
    return sorted({item for item in value.split("||") if item})


def _resolve_icon_path(icon_key: str | None, local_path: str | None) -> str | None:
    candidates: list[Path] = []

    if local_path:
        path = Path(local_path)
        candidates.append(path if path.is_absolute() else PROJECT_ROOT / path)

    if icon_key:
        candidates.append(ARTIFACT_ICON_DIR / icon_key)

    for path in candidates:
        if path.exists() and path.is_file():
            return str(path)

    return None


def list_artifact_tags(*, db_path: str | Path = ARTIFACT_DB_PATH) -> list[str]:
    if not db_exists(db_path):
        return []

    with connect_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT name
            FROM artifact_tags
            ORDER BY sort_order, name COLLATE NOCASE
            """
        ).fetchall()

    return [str(row["name"]) for row in rows]


def list_artifacts(
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
    search: str = "",
    pos: int | None = None,
    rarity: int | None = None,
    equipped: bool | None = None,
    tag: str | None = None,
) -> list[dict[str, Any]]:
    if not db_exists(db_path):
        return []

    where: list[str] = []
    params: list[Any] = []

    search = search.strip()
    if search:
        like = f"%{search}%"
        where.append(
            """
            (
                artifacts.name LIKE ?
                OR artifacts.set_name LIKE ?
                OR artifacts.main_property_name LIKE ?
                OR artifacts.main_property_value LIKE ?
                OR equipment.character_name LIKE ?
                OR EXISTS (
                    SELECT 1
                    FROM artifact_substats AS search_substats
                    WHERE search_substats.artifact_id = artifacts.id
                        AND (
                            search_substats.property_name LIKE ?
                            OR search_substats.value LIKE ?
                        )
                )
                OR EXISTS (
                    SELECT 1
                    FROM artifact_tag_links AS search_links
                    JOIN artifact_tags AS search_tags
                        ON search_tags.id = search_links.tag_id
                    WHERE search_links.artifact_id = artifacts.id
                        AND search_tags.name LIKE ?
                )
            )
            """
        )
        params.extend([like, like, like, like, like, like, like, like])

    pos = _int_or_none(pos)
    if pos is not None:
        where.append("artifacts.pos = ?")
        params.append(pos)

    rarity = _int_or_none(rarity)
    if rarity is not None:
        where.append("artifacts.rarity = ?")
        params.append(rarity)

    if equipped is True:
        where.append("equipment.artifact_id IS NOT NULL")
    elif equipped is False:
        where.append("equipment.artifact_id IS NULL")

    tag = (tag or "").strip()
    if tag:
        where.append(
            """
            EXISTS (
                SELECT 1
                FROM artifact_tag_links AS filter_links
                JOIN artifact_tags AS filter_tags
                    ON filter_tags.id = filter_links.tag_id
                WHERE filter_links.artifact_id = artifacts.id
                    AND filter_tags.name = ?
            )
            """
        )
        params.append(tag)

    where_sql = ""
    if where:
        where_sql = "WHERE " + " AND ".join(f"({item})" for item in where)

    with connect_db(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                artifacts.id,
                artifacts.relic_id,
                artifacts.name,
                artifacts.set_id,
                artifacts.set_name,
                artifacts.pos,
                artifacts.pos_name,
                artifacts.rarity,
                artifacts.level,
                artifacts.main_property_type,
                artifacts.main_property_name,
                artifacts.main_property_value,
                artifacts.first_seen_at,
                artifacts.last_seen_at,
                icons.icon_key,
                icons.icon_url,
                icons.local_path AS icon_local_path,
                equipment.character_id,
                equipment.character_name,
                GROUP_CONCAT(tags.name, '||') AS tag_names
            FROM artifacts
            LEFT JOIN artifact_icons AS icons
                ON icons.id = artifacts.icon_id
            LEFT JOIN artifact_equipment AS equipment
                ON equipment.artifact_id = artifacts.id
            LEFT JOIN artifact_tag_links AS tag_links
                ON tag_links.artifact_id = artifacts.id
            LEFT JOIN artifact_tags AS tags
                ON tags.id = tag_links.tag_id
            {where_sql}
            GROUP BY artifacts.id
            ORDER BY
                COALESCE(artifacts.rarity, 0) DESC,
                COALESCE(artifacts.level, 0) DESC,
                artifacts.set_name COLLATE NOCASE,
                artifacts.pos,
                artifacts.name COLLATE NOCASE
            """,
            params,
        ).fetchall()

        artifact_ids = [int(row["id"]) for row in rows]
        substats_by_artifact: dict[int, list[dict[str, Any]]] = {
            artifact_id: [] for artifact_id in artifact_ids
        }

        if artifact_ids:
            placeholders = ",".join("?" for _ in artifact_ids)
            substat_rows = conn.execute(
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

            for row in substat_rows:
                artifact_id = int(row["artifact_id"])
                substats_by_artifact.setdefault(artifact_id, []).append(
                    {
                        "slot_index": int(row["slot_index"]),
                        "property_type": row["property_type"],
                        "property_name": row["property_name"],
                        "value": row["value"],
                        "times": row["times"],
                    }
                )

    result: list[dict[str, Any]] = []
    for row in rows:
        artifact_id = int(row["id"])
        icon_key = row["icon_key"]
        local_path = row["icon_local_path"]
        pos_value = _int_or_none(row["pos"])

        result.append(
            {
                "id": artifact_id,
                "relic_id": row["relic_id"],
                "name": row["name"] or "",
                "set_id": row["set_id"],
                "set_name": row["set_name"] or "",
                "pos": pos_value,
                "pos_name": row["pos_name"] or ARTIFACT_POSITIONS.get(pos_value or 0, ""),
                "rarity": _int_or_none(row["rarity"]) or 0,
                "level": _int_or_none(row["level"]) or 0,
                "main_property_type": row["main_property_type"],
                "main_property_name": row["main_property_name"] or "",
                "main_property_value": row["main_property_value"] or "",
                "icon_key": icon_key or "",
                "icon_url": row["icon_url"] or "",
                "icon_path": _resolve_icon_path(icon_key, local_path),
                "character_id": row["character_id"],
                "character_name": row["character_name"] or "",
                "tags": _split_group(row["tag_names"]),
                "substats": substats_by_artifact.get(artifact_id, []),
                "first_seen_at": row["first_seen_at"],
                "last_seen_at": row["last_seen_at"],
            }
        )

    return result


def add_artifact_tag(
    artifact_id: int,
    tag_name: str,
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> None:
    tag_name = tag_name.strip()
    if not tag_name:
        return

    with connect_db(db_path) as conn:
        tag_id = get_or_create_tag(conn, tag_name)
        tag_artifact(conn, artifact_id, tag_id)
        conn.commit()


def remove_artifact_tag(
    artifact_id: int,
    tag_name: str,
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> None:
    tag_name = tag_name.strip()
    if not tag_name or not db_exists(db_path):
        return

    with connect_db(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM artifact_tags WHERE name = ?",
            (tag_name,),
        ).fetchone()
        if row is None:
            return

        untag_artifact(conn, artifact_id, int(row["id"]))
        conn.commit()
