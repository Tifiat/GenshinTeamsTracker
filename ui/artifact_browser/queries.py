from __future__ import annotations

from pathlib import Path
from typing import Any

from hoyolab_export.artifact_db import ARTIFACT_DB_PATH, connect_db
from hoyolab_export.paths import PROJECT_ROOT

from .models import (
    ARTIFACT_POSITIONS,
    ArtifactItem,
    ArtifactSubstat,
    ArtifactTagRef,
    int_or_none,
)


ARTIFACT_ICON_DIR = PROJECT_ROOT / "assets" / "hoyolab" / "artifacts"


def artifact_db_exists(db_path: str | Path = ARTIFACT_DB_PATH) -> bool:
    return Path(db_path).exists()


def _resolve_icon_path(icon_key: str | None, local_path: str | None) -> Path | None:
    candidates: list[Path] = []

    if local_path:
        path = Path(local_path)
        candidates.append(path if path.is_absolute() else PROJECT_ROOT / path)

    if icon_key:
        candidates.append(ARTIFACT_ICON_DIR / icon_key)

    for path in candidates:
        if path.exists() and path.is_file():
            return path

    return None


def list_all_artifacts(
    *,
    db_path: str | Path = ARTIFACT_DB_PATH,
) -> list[ArtifactItem]:
    if not artifact_db_exists(db_path):
        return []

    with connect_db(db_path) as conn:
        return _fetch_artifacts(conn)


def _fetch_artifacts(conn) -> list[ArtifactItem]:
    rows = conn.execute(
        """
        SELECT
            artifacts.id,
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
            icons.icon_key,
            icons.icon_url,
            icons.local_path AS icon_local_path,
            equipment.character_name
        FROM artifacts
        LEFT JOIN artifact_icons AS icons
            ON icons.id = artifacts.icon_id
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
        icon_key = row["icon_key"] or ""

        result.append(
            ArtifactItem(
                id=artifact_id,
                name=row["name"],
                set_id=int_or_none(row["set_id"]),
                set_name=row["set_name"],
                pos=pos,
                pos_name=row["pos_name"] or ARTIFACT_POSITIONS[pos],
                rarity=int_or_none(row["rarity"]) or 0,
                level=int_or_none(row["level"]) or 0,
                main_property_type=int(row["main_property_type"]),
                main_property_name=row["main_property_name"],
                main_property_value=row["main_property_value"],
                icon_key=icon_key,
                icon_url=row["icon_url"] or "",
                icon_path=_resolve_icon_path(icon_key, row["icon_local_path"]),
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